using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed record TeableUserProjectionRow(
    string UserId,
    string SubjectId,
    string Email,
    string DisplayName,
    string Handle,
    string Visibility,
    string Timezone,
    string CountryCode,
    IReadOnlyList<string> LinkedPrincipals,
    IReadOnlyList<string> GroupIds,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string WorkspacePrepLibrarySearchHistory,
    string WhatsappAiSupportPhone,
    string WhatsappAiSupportPhoneLast4,
    bool WhatsappAiSupportEnabled,
    bool WhatsappNotificationsEnabled,
    string WhatsappAiSupportPurpose,
    string WhatsappAiSupportOpeningPrompt);

public sealed record TeableUserProjectionDashboard(
    bool Enabled,
    bool Configured,
    string State,
    string ApiBaseUrl,
    string? BaseId,
    string? TableId,
    string TableName,
    int StoredUserCount,
    DateTimeOffset? LastAttemptedSyncAtUtc,
    DateTimeOffset? LastSuccessfulSyncAtUtc,
    string? LastError,
    IReadOnlyList<TeableUserProjectionRow> Users);

public sealed record TeableUserProjectionSyncResult(
    string State,
    int AttemptedCount,
    int SyncedCount,
    int FailedCount,
    string? BaseId,
    string? TableId,
    string TableName,
    DateTimeOffset OccurredAtUtc,
    IReadOnlyList<string> Errors);

public sealed class TeableUserProjectionService
{
    private const string HttpTimeoutSecondsConfigKey = "CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS";
    private static readonly TimeSpan DefaultHttpTimeout = TimeSpan.FromSeconds(15);
    private const string DefaultApiBaseUrl = "https://app.teable.ai/api";
    private const string DefaultTableName = "Chummer Run Users";
    private const string DefaultDbTableName = "chummer_run_users";
    private const string StateDisabled = "disabled";
    private const string StateUnconfigured = "unconfigured";
    private const string StateReady = "ready";
    private const string StateFailed = "failed";
    private const string StatePassed = "passed";
    private const int RecordPageSize = 1000;
    private const int CreateRecordBatchSize = 20;
    private const int PatchConcurrency = 8;
    private const string WhatsappAiSupportPurpose = "ai_support_only";
    private const string WhatsappAiSupportOpeningPrompt = "Ask what questions the user has before giving product guidance.";
    private const string WhatsappAiSupportPurposeConfigKey = "CHUMMER_IDENTITY_LINK_WHATSAPP_SUPPORT_PURPOSE";
    private const string WhatsappAiSupportOpeningPromptConfigKey = "CHUMMER_IDENTITY_LINK_WHATSAPP_SUPPORT_OPENING_PROMPT";

    private static readonly TeableFieldDefinition[] RequiredFields =
    [
        new("Display Name", "singleLineText", Description: "Human-facing display name from chummer.run."),
        new("User Id", "singleLineText", Unique: true, NotNull: true, Description: "Stable Chummer hub user id."),
        new("Subject Id", "singleLineText", Description: "Identity subject id."),
        new("Email", "singleLineText", Description: "Reporter or identity email when available."),
        new("Handle", "singleLineText", Description: "Normalized user handle."),
        new("Visibility", "singleLineText", Description: "Hub profile visibility."),
        new("Timezone", "singleLineText", Description: "Preferred timezone."),
        new("Country Code", "singleLineText", Description: "ISO country code."),
        new("Linked Principals", "longText", Description: "All linked principal ids, one per line."),
        new("Group Ids", "longText", Description: "All joined group ids, one per line."),
        new("Workspace Prep Library Search History", "longText", Description: "Recent workspace prep search queries with last-used timestamps."),
        new("WhatsApp Support Phone", "singleLineText", Description: "Normalized WhatsApp support handle for routing only."),
        new("WhatsApp Support Phone Last4", "singleLineText", Description: "Masked support handle suffix for support review."),
        new("WhatsApp Support Enabled", "checkbox", Description: "True when a WhatsApp support handle is linked."),
        new("WhatsApp Notifications Enabled", "checkbox", Description: "True when the user opted into WhatsApp notices."),
        new("WhatsApp Support Purpose", "singleLineText", Description: "Support-only routing purpose."),
        new("WhatsApp Support Opening Prompt", "longText", Description: "First-turn guidance for WhatsApp support."),
        new("Created At UTC", "singleLineText", Description: "Initial account creation timestamp."),
        new("Updated At UTC", "singleLineText", Description: "Most recent hub-side account update timestamp."),
        new("Last Synced At UTC", "singleLineText", Description: "Most recent Teable projection timestamp.")
    ];

    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<TeableUserProjectionService> _logger;
    private readonly SemaphoreSlim _syncGate = new(1, 1);
    private readonly object _stateGate = new();

    private string? _resolvedBaseId;
    private string? _resolvedTableId;
    private DateTimeOffset? _lastAttemptedSyncAtUtc;
    private DateTimeOffset? _lastSuccessfulSyncAtUtc;
    private string? _lastError;

    public TeableUserProjectionService(
        CommunityStore store,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory,
        ILogger<TeableUserProjectionService> logger)
    {
        _store = store;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public void QueueSyncUser(HubUserDto user)
    {
        ArgumentNullException.ThrowIfNull(user);

        TeableOptions options = ResolveOptions();
        if (!options.Enabled || !options.CanAttemptSync)
        {
            return;
        }

        _ = Task.Run(async () =>
        {
            try
            {
                TeableUserProjectionRow? row = GetStoredUsers().FirstOrDefault(item => string.Equals(item.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
                if (row is null)
                {
                    SetSyncFailure($"autosync_failed:user_not_found:{user.UserId}", DateTimeOffset.UtcNow);
                    return;
                }

                await SyncUsersInternalAsync([row], options, CancellationToken.None);
            }
            catch (Exception ex)
            {
                SetSyncFailure($"autosync_failed:{ShortMessage(ex)}", DateTimeOffset.UtcNow);
                _logger.LogWarning(ex, "could not auto-project hub user {UserId} into Teable", user.UserId);
            }
        });
    }

    public TeableUserProjectionDashboard GetDashboard()
    {
        TeableOptions options = ResolveOptions();
        IReadOnlyList<TeableUserProjectionRow> users = GetStoredUsers();
        string? baseId;
        string? tableId;
        DateTimeOffset? lastAttempted;
        DateTimeOffset? lastSuccessful;
        string? lastError;

        lock (_stateGate)
        {
            baseId = _resolvedBaseId ?? options.BaseId;
            tableId = _resolvedTableId ?? options.TableId;
            lastAttempted = _lastAttemptedSyncAtUtc;
            lastSuccessful = _lastSuccessfulSyncAtUtc;
            lastError = _lastError;
        }

        string state = !options.Enabled
            ? StateDisabled
            : options.CanAttemptSync
                ? (string.IsNullOrWhiteSpace(lastError) ? StateReady : StateFailed)
                : StateUnconfigured;

        return new TeableUserProjectionDashboard(
            Enabled: options.Enabled,
            Configured: options.CanAttemptSync,
            State: state,
            ApiBaseUrl: options.ApiBaseUrl,
            BaseId: baseId,
            TableId: tableId,
            TableName: options.TableName,
            StoredUserCount: users.Count,
            LastAttemptedSyncAtUtc: lastAttempted,
            LastSuccessfulSyncAtUtc: lastSuccessful,
            LastError: lastError,
            Users: users);
    }

    public Task<TeableUserProjectionSyncResult> SyncAllAsync(CancellationToken cancellationToken = default)
        => SyncUsersInternalAsync(GetStoredUsers(), ResolveOptions(), cancellationToken);

    private async Task<TeableUserProjectionSyncResult> SyncUsersInternalAsync(
        IReadOnlyList<TeableUserProjectionRow> users,
        TeableOptions options,
        CancellationToken cancellationToken)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        SetSyncAttempt(now);

        if (!options.Enabled)
        {
            return BuildResult(StateDisabled, 0, 0, 0, options.TableName, options.BaseId, options.TableId, now, []);
        }

        if (!options.CanAttemptSync)
        {
            return BuildResult(StateUnconfigured, 0, 0, 0, options.TableName, options.BaseId, options.TableId, now, ["teable_destination_unconfigured"]);
        }

        await _syncGate.WaitAsync(cancellationToken);
        try
        {
            TeableDestination destination = await EnsureDestinationAsync(options, cancellationToken);
            int synced = 0;
            List<string> errors = new();
            Dictionary<string, ExistingTeableRecord> existingRecords = await FetchExistingRecordsAsync(destination.TableId, options, cancellationToken);
            List<TeableUserProjectionRow> usersToCreate = new();
            List<PendingTeableUserUpdate> usersToUpdate = new();
            foreach (TeableUserProjectionRow user in users)
            {
                JsonObject fields = BuildFields(user);
                if (!existingRecords.TryGetValue(user.UserId, out ExistingTeableRecord? existing))
                {
                    usersToCreate.Add(user);
                    continue;
                }

                if (FieldsNeedUpdate(fields, existing.Fields))
                {
                    usersToUpdate.Add(new PendingTeableUserUpdate(user, existing.RecordId));
                    continue;
                }

                synced++;
            }

            foreach (List<TeableUserProjectionRow> chunk in Chunk(usersToCreate, CreateRecordBatchSize))
            {
                try
                {
                    await CreateUserRecordsAsync(destination, chunk, options, cancellationToken);
                    synced += chunk.Count;
                }
                catch (Exception ex)
                {
                    foreach (TeableUserProjectionRow user in chunk)
                    {
                        errors.Add($"{user.UserId}:{ShortMessage(ex)}");
                    }
                    _logger.LogWarning(ex, "could not batch-create {Count} hub users into Teable table {TableId}", chunk.Count, destination.TableId);
                }
            }

            if (usersToUpdate.Count > 0)
            {
                int patched = await PatchChangedUserRecordsAsync(destination, usersToUpdate, options, errors, cancellationToken);
                synced += patched;
            }

            if (errors.Count == 0)
            {
                SetSyncSuccess(now, destination);
                return BuildResult(StatePassed, users.Count, synced, 0, destination.TableName, destination.BaseId, destination.TableId, now, errors);
            }

            SetSyncFailure(string.Join(" | ", errors.Take(4)), now, destination);
            return BuildResult(StateFailed, users.Count, synced, errors.Count, destination.TableName, destination.BaseId, destination.TableId, now, errors);
        }
        catch (Exception ex)
        {
            SetSyncFailure(ShortMessage(ex), now);
            _logger.LogWarning(ex, "could not resolve Teable destination for hub user projection");
            return BuildResult(StateFailed, users.Count, 0, users.Count, options.TableName, _resolvedBaseId ?? options.BaseId, _resolvedTableId ?? options.TableId, now, [ShortMessage(ex)]);
        }
        finally
        {
            _syncGate.Release();
        }
    }

    private async Task<TeableDestination> EnsureDestinationAsync(TeableOptions options, CancellationToken cancellationToken)
    {
        string? baseId = Normalize(options.BaseId);
        string? tableId = Normalize(options.TableId);
        if (!string.IsNullOrWhiteSpace(tableId))
        {
            await EnsureFieldsAsync(tableId, options, cancellationToken);
            _resolvedBaseId = baseId;
            _resolvedTableId = tableId;
            return new TeableDestination(baseId, tableId, options.TableName);
        }

        baseId ??= await DiscoverBaseIdAsync(options, cancellationToken);
        if (string.IsNullOrWhiteSpace(baseId))
        {
            throw new InvalidOperationException("teable_base_id_required");
        }

        tableId = await ResolveOrCreateTableIdAsync(baseId, options, cancellationToken);
        await EnsureFieldsAsync(tableId, options, cancellationToken);
        _resolvedBaseId = baseId;
        _resolvedTableId = tableId;
        return new TeableDestination(baseId, tableId, options.TableName);
    }

    private async Task<string?> DiscoverBaseIdAsync(TeableOptions options, CancellationToken cancellationToken)
    {
        JsonDocument response = await SendAsync(HttpMethod.Get, $"{options.ApiBaseUrl}/base/access/all", null, options.ApiKey, cancellationToken);
        using (response)
        {
            if (response.RootElement.ValueKind != JsonValueKind.Array)
            {
                return null;
            }

            List<string> ids = new();
            foreach (JsonElement entry in response.RootElement.EnumerateArray())
            {
                if (TryGetString(entry, "id", out string? id))
                {
                    ids.Add(id!);
                }
            }

            return ids.Count == 1 ? ids[0] : null;
        }
    }

    private async Task<string> ResolveOrCreateTableIdAsync(string baseId, TeableOptions options, CancellationToken cancellationToken)
    {
        JsonDocument response = await SendAsync(HttpMethod.Get, $"{options.ApiBaseUrl}/base/{Uri.EscapeDataString(baseId)}/table", null, options.ApiKey, cancellationToken);
        using (response)
        {
            if (response.RootElement.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement table in response.RootElement.EnumerateArray())
                {
                    if (TryGetString(table, "id", out string? tableId)
                        && (MatchesTable(table, options.TableName) || MatchesTable(table, DefaultDbTableName)))
                    {
                        return tableId!;
                    }
                }
            }
        }

        JsonObject payload = new()
        {
            ["name"] = options.TableName,
            ["dbTableName"] = DefaultDbTableName,
            ["description"] = "Administrative projection of chummer.run users. Chummer Hub remains the system of record.",
            ["icon"] = "\ud83d\udc65",
            ["fieldKeyType"] = "name",
            ["fields"] = new JsonArray(RequiredFields.Select(static field => field.ToJson()).ToArray())
        };
        JsonDocument created = await SendAsync(HttpMethod.Post, $"{options.ApiBaseUrl}/base/{Uri.EscapeDataString(baseId)}/table/", payload, options.ApiKey, cancellationToken);
        using (created)
        {
            return GetRequiredString(created.RootElement, "id");
        }
    }

    private async Task EnsureFieldsAsync(string tableId, TeableOptions options, CancellationToken cancellationToken)
    {
        JsonDocument response = await SendAsync(HttpMethod.Get, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/field?filterHidden=false", null, options.ApiKey, cancellationToken);
        using (response)
        {
            HashSet<string> existingNames = new(StringComparer.OrdinalIgnoreCase);
            if (response.RootElement.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement field in response.RootElement.EnumerateArray())
                {
                    if (TryGetString(field, "name", out string? name))
                    {
                        existingNames.Add(name!);
                    }
                }
            }

            foreach (TeableFieldDefinition requiredField in RequiredFields)
            {
                if (existingNames.Contains(requiredField.Name))
                {
                    continue;
                }

                await SendAsync(
                    HttpMethod.Post,
                    $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/field",
                    requiredField.ToJson(),
                    options.ApiKey,
                    cancellationToken);
            }
        }
    }

    private async Task CreateUserRecordsAsync(
        TeableDestination destination,
        IReadOnlyList<TeableUserProjectionRow> users,
        TeableOptions options,
        CancellationToken cancellationToken)
    {
        if (users.Count == 0)
        {
            return;
        }

        JsonArray records = new();
        foreach (TeableUserProjectionRow user in users)
        {
            records.Add(new JsonObject
            {
                ["fields"] = BuildFields(user)
            });
        }

        JsonObject createPayload = new()
        {
            ["fieldKeyType"] = "name",
            ["typecast"] = true,
            ["records"] = records
        };
        JsonDocument created = await SendAsync(
            HttpMethod.Post,
            $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(destination.TableId)}/record",
            createPayload,
            options.ApiKey,
            cancellationToken);
        created.Dispose();
    }

    private async Task<int> PatchChangedUserRecordsAsync(
        TeableDestination destination,
        IReadOnlyList<PendingTeableUserUpdate> users,
        TeableOptions options,
        List<string> errors,
        CancellationToken cancellationToken)
    {
        int patched = 0;
        using SemaphoreSlim gate = new(PatchConcurrency, PatchConcurrency);
        object errorsGate = new();
        List<Task> tasks = new();
        foreach (PendingTeableUserUpdate pending in users)
        {
            await gate.WaitAsync(cancellationToken);
            tasks.Add(Task.Run(
                async () =>
                {
                    try
                    {
                        await PatchUserRecordAsync(destination, pending, options, cancellationToken);
                        Interlocked.Increment(ref patched);
                    }
                    catch (Exception ex)
                    {
                        lock (errorsGate)
                        {
                            errors.Add($"{pending.User.UserId}:{ShortMessage(ex)}");
                        }
                        _logger.LogWarning(ex, "could not patch hub user {UserId} in Teable table {TableId}", pending.User.UserId, destination.TableId);
                    }
                    finally
                    {
                        gate.Release();
                    }
                },
                cancellationToken));
        }

        await Task.WhenAll(tasks);
        return patched;
    }

    private async Task PatchUserRecordAsync(
        TeableDestination destination,
        PendingTeableUserUpdate pending,
        TeableOptions options,
        CancellationToken cancellationToken)
    {
        JsonObject payload = new()
        {
            ["fieldKeyType"] = "name",
            ["typecast"] = true,
            ["record"] = new JsonObject
            {
                ["fields"] = BuildFields(pending.User)
            }
        };
        JsonDocument ignored = await SendAsync(
            HttpMethod.Patch,
            $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(destination.TableId)}/record/{Uri.EscapeDataString(pending.RecordId)}",
            payload,
            options.ApiKey,
            cancellationToken);
        ignored.Dispose();
    }

    private async Task<Dictionary<string, ExistingTeableRecord>> FetchExistingRecordsAsync(
        string tableId,
        TeableOptions options,
        CancellationToken cancellationToken)
    {
        Dictionary<string, ExistingTeableRecord> rows = new(StringComparer.OrdinalIgnoreCase);
        int skip = 0;
        while (true)
        {
            string query = $"fieldKeyType=name&cellFormat=json&take={RecordPageSize}&skip={skip}";
            string path = $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/record?{query}";
            JsonDocument response = await SendAsync(HttpMethod.Get, path, null, options.ApiKey, cancellationToken);
            using (response)
            {
                if (!response.RootElement.TryGetProperty("records", out JsonElement records)
                    || records.ValueKind != JsonValueKind.Array)
                {
                    return rows;
                }

                int count = 0;
                foreach (JsonElement record in records.EnumerateArray())
                {
                    count++;
                    if (!TryGetString(record, "id", out string? recordId)
                        || !record.TryGetProperty("fields", out JsonElement fields)
                        || fields.ValueKind != JsonValueKind.Object
                        || !TryGetString(fields, "User Id", out string? userId))
                    {
                        continue;
                    }

                    rows[userId!] = new ExistingTeableRecord(recordId!, ReadComparableFields(fields));
                }

                if (count < RecordPageSize)
                {
                    return rows;
                }

                skip += RecordPageSize;
            }
        }
    }

    private static JsonObject BuildFields(TeableUserProjectionRow user)
        => new()
        {
            ["Display Name"] = user.DisplayName,
            ["User Id"] = user.UserId,
            ["Subject Id"] = user.SubjectId,
            ["Email"] = Normalize(user.Email) ?? string.Empty,
            ["Handle"] = user.Handle,
            ["Visibility"] = user.Visibility,
            ["Timezone"] = user.Timezone,
            ["Country Code"] = user.CountryCode,
            ["Linked Principals"] = string.Join('\n', user.LinkedPrincipals ?? Array.Empty<string>()),
            ["Group Ids"] = string.Join('\n', user.GroupIds ?? Array.Empty<string>()),
            ["Workspace Prep Library Search History"] = user.WorkspacePrepLibrarySearchHistory,
            ["WhatsApp Support Phone"] = user.WhatsappAiSupportPhone,
            ["WhatsApp Support Phone Last4"] = user.WhatsappAiSupportPhoneLast4,
            ["WhatsApp Support Enabled"] = user.WhatsappAiSupportEnabled,
            ["WhatsApp Notifications Enabled"] = user.WhatsappNotificationsEnabled,
            ["WhatsApp Support Purpose"] = user.WhatsappAiSupportPurpose,
            ["WhatsApp Support Opening Prompt"] = user.WhatsappAiSupportOpeningPrompt,
            ["Created At UTC"] = user.CreatedAtUtc.ToString("O"),
            ["Updated At UTC"] = user.UpdatedAtUtc.ToString("O"),
            ["Last Synced At UTC"] = DateTimeOffset.UtcNow.ToString("O"),
        };

    private IReadOnlyList<TeableUserProjectionRow> GetStoredUsers()
    {
        string defaultWhatsappAiSupportPurpose = ResolveWhatsappAiSupportPurpose();
        string defaultWhatsappAiSupportOpeningPrompt = ResolveWhatsappAiSupportOpeningPrompt();
        lock (_store.Gate)
        {
            return _store.UsersById.Values
                .OrderBy(static item => item.DisplayName, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                .Select(item =>
                {
                    ChannelLinkDto? whatsapp = _store.ChannelLinks.FirstOrDefault(link =>
                        string.Equals(link.UserId, item.UserId, StringComparison.OrdinalIgnoreCase)
                        && string.Equals(link.ChannelKind, "whatsapp_official_business", StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(link.Status, "revoked", StringComparison.OrdinalIgnoreCase));
                    var phone = Normalize(whatsapp?.DisplayLabel) ?? string.Empty;
                    var digits = DigitsOnly(phone);
                    var hasWhatsappSupportPhone = !string.IsNullOrWhiteSpace(phone);
                    return new TeableUserProjectionRow(
                        UserId: item.UserId,
                        SubjectId: item.SubjectId,
                        Email: Normalize(item.Email) ?? string.Empty,
                        DisplayName: item.DisplayName,
                        Handle: item.Handle,
                        Visibility: item.Visibility,
                        Timezone: item.Timezone,
                        CountryCode: item.CountryCode,
                        LinkedPrincipals: item.LinkedPrincipals,
                        GroupIds: item.GroupIds,
                        CreatedAtUtc: item.CreatedAtUtc,
                        UpdatedAtUtc: item.UpdatedAtUtc,
                        WorkspacePrepLibrarySearchHistory: BuildWorkspacePrepHistory(
                            _store.UserExperienceByUserId.TryGetValue(item.UserId, out var experience)
                                ? experience.WorkspacePrepLibrarySearchHistory
                                : Array.Empty<WorkspacePrepLibrarySearchHistoryItem>()),
                        WhatsappAiSupportPhone: phone,
                        WhatsappAiSupportPhoneLast4: digits.Length >= 4 ? digits[^4..] : digits,
                        WhatsappAiSupportEnabled: hasWhatsappSupportPhone,
                        WhatsappNotificationsEnabled: whatsapp?.NotificationsEnabled ?? false,
                        WhatsappAiSupportPurpose: hasWhatsappSupportPhone
                            ? Normalize(whatsapp?.Purpose) ?? defaultWhatsappAiSupportPurpose
                            : string.Empty,
                        WhatsappAiSupportOpeningPrompt: hasWhatsappSupportPhone
                            ? Normalize(whatsapp?.AiSupportOpeningPrompt) ?? defaultWhatsappAiSupportOpeningPrompt
                            : string.Empty);
                })
                .ToArray();
        }
    }

    private string ResolveWhatsappAiSupportPurpose()
        => Normalize(_configuration[WhatsappAiSupportPurposeConfigKey]) ?? WhatsappAiSupportPurpose;

    private string ResolveWhatsappAiSupportOpeningPrompt()
        => Normalize(_configuration[WhatsappAiSupportOpeningPromptConfigKey]) ?? WhatsappAiSupportOpeningPrompt;

    private static string BuildWorkspacePrepHistory(IReadOnlyList<WorkspacePrepLibrarySearchHistoryItem>? history)
    {
        if (history is null || history.Count == 0)
        {
            return string.Empty;
        }

        return JsonSerializer.Serialize(
            history
                .Select(static item => new
                {
                    item.WorkspaceId,
                    item.Query,
                    item.LastUsedUtc,
                })
                .ToArray());
    }

    private TeableOptions ResolveOptions()
    {
        bool enabled = ParseBool(_configuration["CHUMMER_TEABLE_USERS_ENABLED"], defaultValue: true);
        string apiKey = Normalize(_configuration["CHUMMER_TEABLE_USERS_API_KEY"])
            ?? Normalize(_configuration["TEABLE_API_KEY"])
            ?? string.Empty;
        string apiBaseUrl = (Normalize(_configuration["CHUMMER_TEABLE_USERS_API_BASE_URL"]) ?? DefaultApiBaseUrl).TrimEnd('/');
        string tableName = Normalize(_configuration["CHUMMER_TEABLE_USERS_TABLE_NAME"]) ?? DefaultTableName;
        string? baseId = Normalize(_configuration["CHUMMER_TEABLE_USERS_BASE_ID"]);
        string? tableId = Normalize(_configuration["CHUMMER_TEABLE_USERS_TABLE_ID"]);
        return new TeableOptions(
            Enabled: enabled,
            ApiKey: apiKey,
            ApiBaseUrl: apiBaseUrl,
            BaseId: baseId,
            TableId: tableId,
            TableName: tableName);
    }

    private async Task<JsonDocument> SendAsync(
        HttpMethod method,
        string url,
        JsonNode? body,
        string apiKey,
        CancellationToken cancellationToken)
    {
        using HttpRequestMessage request = new(method, url);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (body is not null)
        {
            request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        }

        using CancellationTokenSource timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(ResolveHttpTimeout());

        using HttpResponseMessage response = await _httpClientFactory.CreateClient().SendAsync(request, timeoutCts.Token);
        string content = await response.Content.ReadAsStringAsync(timeoutCts.Token);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"teable_http_{(int)response.StatusCode}:{Truncate(content, 240)}");
        }

        return JsonDocument.Parse(string.IsNullOrWhiteSpace(content) ? "{}" : content);
    }

    private TimeSpan ResolveHttpTimeout()
    {
        string? raw = Normalize(_configuration[HttpTimeoutSecondsConfigKey]);
        return int.TryParse(raw, out int seconds) && seconds >= 1
            ? TimeSpan.FromSeconds(seconds)
            : DefaultHttpTimeout;
    }

    private void SetSyncAttempt(DateTimeOffset occurredAtUtc)
    {
        lock (_stateGate)
        {
            _lastAttemptedSyncAtUtc = occurredAtUtc;
            _lastError = null;
        }
    }

    private void SetSyncSuccess(DateTimeOffset occurredAtUtc, TeableDestination destination)
    {
        lock (_stateGate)
        {
            _lastAttemptedSyncAtUtc = occurredAtUtc;
            _lastSuccessfulSyncAtUtc = occurredAtUtc;
            _lastError = null;
            _resolvedBaseId = destination.BaseId;
            _resolvedTableId = destination.TableId;
        }
    }

    private void SetSyncFailure(string error, DateTimeOffset occurredAtUtc, TeableDestination? destination = null)
    {
        lock (_stateGate)
        {
            _lastAttemptedSyncAtUtc = occurredAtUtc;
            _lastError = error;
            if (destination is not null)
            {
                _resolvedBaseId = destination.BaseId;
                _resolvedTableId = destination.TableId;
            }
        }
    }

    private static TeableUserProjectionSyncResult BuildResult(
        string state,
        int attemptedCount,
        int syncedCount,
        int failedCount,
        string tableName,
        string? baseId,
        string? tableId,
        DateTimeOffset occurredAtUtc,
        IReadOnlyList<string> errors)
        => new(
            State: state,
            AttemptedCount: attemptedCount,
            SyncedCount: syncedCount,
            FailedCount: failedCount,
            BaseId: baseId,
            TableId: tableId,
            TableName: tableName,
            OccurredAtUtc: occurredAtUtc,
            Errors: errors);

    private static bool MatchesTable(JsonElement table, string candidate)
        => (TryGetString(table, "name", out string? name) && string.Equals(name, candidate, StringComparison.OrdinalIgnoreCase))
            || (TryGetString(table, "dbTableName", out string? dbTableName) && string.Equals(dbTableName, candidate, StringComparison.OrdinalIgnoreCase));

    private static string GetRequiredString(JsonElement element, string propertyName)
        => TryGetString(element, propertyName, out string? value)
            ? value!
            : throw new InvalidOperationException($"teable_missing_{propertyName}");

    private static bool TryGetString(JsonElement element, string propertyName, out string? value)
    {
        value = null;
        if (!element.TryGetProperty(propertyName, out JsonElement property)
            || property.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            return false;
        }

        value = property.GetString();
        return !string.IsNullOrWhiteSpace(value);
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static List<List<T>> Chunk<T>(IReadOnlyList<T> values, int chunkSize)
    {
        List<List<T>> chunks = new();
        for (int start = 0; start < values.Count; start += chunkSize)
        {
            chunks.Add(values.Skip(start).Take(chunkSize).ToList());
        }

        return chunks;
    }

    private static Dictionary<string, string> ReadComparableFields(JsonElement fields)
    {
        Dictionary<string, string> result = new(StringComparer.OrdinalIgnoreCase);
        foreach (JsonProperty field in fields.EnumerateObject())
        {
            result[field.Name] = ComparableValue(field.Value);
        }

        return result;
    }

    private static bool FieldsNeedUpdate(JsonObject desired, IReadOnlyDictionary<string, string> current)
    {
        foreach (KeyValuePair<string, JsonNode?> field in desired)
        {
            if (string.Equals(field.Key, "Last Synced At UTC", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            string desiredValue = ComparableValue(field.Value);
            if (!current.TryGetValue(field.Key, out string? currentValue))
            {
                if (MissingCellMatchesDesiredValue(field.Key, desiredValue))
                {
                    continue;
                }

                return true;
            }

            if (!string.Equals(currentValue, desiredValue, StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }

    private static bool MissingCellMatchesDesiredValue(string fieldName, string desiredValue)
        => string.IsNullOrEmpty(desiredValue)
            || (string.Equals(desiredValue, "false", StringComparison.Ordinal)
                && RequiredFields.Any(field =>
                    string.Equals(field.Name, fieldName, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(field.Type, "checkbox", StringComparison.OrdinalIgnoreCase)));

    private static string ComparableValue(JsonNode? value)
    {
        if (value is null)
        {
            return string.Empty;
        }

        if (value is JsonValue jsonValue)
        {
            if (jsonValue.TryGetValue(out string? stringValue))
            {
                return Normalize(stringValue) ?? string.Empty;
            }

            if (jsonValue.TryGetValue(out bool boolValue))
            {
                return boolValue ? "true" : "false";
            }
        }

        return value.ToJsonString();
    }

    private static string ComparableValue(JsonElement value)
        => value.ValueKind switch
        {
            JsonValueKind.String => Normalize(value.GetString()) ?? string.Empty,
            JsonValueKind.True => "true",
            JsonValueKind.False => "false",
            JsonValueKind.Null or JsonValueKind.Undefined => string.Empty,
            _ => value.GetRawText(),
        };

    private static string DigitsOnly(string? value)
        => new((value ?? string.Empty).Where(char.IsDigit).ToArray());

    private static bool ParseBool(string? value, bool defaultValue)
    {
        string? normalized = Normalize(value);
        return normalized is null ? defaultValue : bool.TryParse(normalized, out bool parsed) ? parsed : defaultValue;
    }

    private static string Truncate(string? value, int maxLength)
    {
        string normalized = Normalize(value) ?? string.Empty;
        return normalized.Length <= maxLength ? normalized : normalized[..maxLength];
    }

    private static string ShortMessage(Exception ex)
        => Truncate(ex.Message, 240);

    private sealed record TeableOptions(
        bool Enabled,
        string ApiKey,
        string ApiBaseUrl,
        string? BaseId,
        string? TableId,
        string TableName)
    {
        public bool CanAttemptSync => Enabled && !string.IsNullOrWhiteSpace(ApiKey);
    }

    private sealed record TeableDestination(string? BaseId, string TableId, string TableName);

    private sealed record ExistingTeableRecord(string RecordId, IReadOnlyDictionary<string, string> Fields);

    private sealed record PendingTeableUserUpdate(TeableUserProjectionRow User, string RecordId);

    private sealed record TeableFieldDefinition(
        string Name,
        string Type,
        bool Unique = false,
        bool NotNull = false,
        string? Description = null)
    {
        public JsonObject ToJson()
        {
            JsonObject node = new()
            {
                ["type"] = Type,
                ["name"] = Name,
            };
            if (!string.IsNullOrWhiteSpace(Description))
            {
                node["description"] = Description;
            }

            return node;
        }
    }
}
