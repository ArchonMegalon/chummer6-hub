using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Run.Api.Services.Community;

public sealed record ImportantWorkItemRequest(
    string Kind,
    string Scope,
    string Summary,
    string Detail,
    string Status,
    string Priority,
    string? UserId = null,
    string? SubjectId = null,
    string? Source = null,
    string? Link = null,
    IReadOnlyList<string>? Tags = null,
    string? ItemId = null);

public sealed record TeableImportantWorkDashboard(
    bool Enabled,
    bool Configured,
    string State,
    string ApiBaseUrl,
    string? BaseId,
    string? TableId,
    string TableName,
    int StoredItemCount,
    DateTimeOffset? LastAttemptedSyncAtUtc,
    DateTimeOffset? LastSuccessfulSyncAtUtc,
    string? LastError,
    IReadOnlyList<ImportantWorkItemProjection> Items);

public sealed record TeableImportantWorkSyncResult(
    string State,
    int AttemptedCount,
    int SyncedCount,
    int FailedCount,
    string? BaseId,
    string? TableId,
    string TableName,
    DateTimeOffset OccurredAtUtc,
    IReadOnlyList<string> Errors);

public sealed class TeableImportantWorkService
{
    private const string HttpTimeoutSecondsConfigKey = "CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS";
    private const string DefaultApiBaseUrl = "https://app.teable.ai/api";
    private const string DefaultTableName = "Chummer Important Work";
    private const string DefaultDbTableName = "chummer_important_work";
    private const string StateDisabled = "disabled";
    private const string StateUnconfigured = "unconfigured";
    private const string StateReady = "ready";
    private const string StateFailed = "failed";
    private const string StatePassed = "passed";
    private static readonly TimeSpan DefaultHttpTimeout = TimeSpan.FromSeconds(15);

    private static readonly TeableFieldDefinition[] RequiredFields =
    [
        new("Item Id", "singleLineText", Description: "Stable Chummer work item id."),
        new("Kind", "singleLineText", Description: "Work category, for example goal, workflow, user, billing, release, support, or design."),
        new("Scope", "singleLineText", Description: "Product or workflow scope."),
        new("Summary", "singleLineText", Description: "Short human-readable summary."),
        new("Detail", "longText", Description: "Operational detail that needs to survive context loss."),
        new("Status", "singleLineText", Description: "Current state."),
        new("Priority", "singleLineText", Description: "Priority or urgency."),
        new("User Id", "singleLineText", Description: "Optional Chummer user id."),
        new("Subject Id", "singleLineText", Description: "Optional identity subject id."),
        new("Source", "singleLineText", Description: "Where this item came from."),
        new("Link", "url", Description: "Optional first-party link."),
        new("Tags", "longText", Description: "One tag per line."),
        new("Created At UTC", "singleLineText", Description: "Creation timestamp."),
        new("Updated At UTC", "singleLineText", Description: "Last Chummer-side update timestamp."),
        new("Last Synced At UTC", "singleLineText", Description: "Most recent Teable projection timestamp.")
    ];

    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<TeableImportantWorkService> _logger;
    private readonly SemaphoreSlim _syncGate = new(1, 1);
    private readonly object _stateGate = new();

    private string? _resolvedBaseId;
    private string? _resolvedTableId;
    private DateTimeOffset? _lastAttemptedSyncAtUtc;
    private DateTimeOffset? _lastSuccessfulSyncAtUtc;
    private string? _lastError;

    public TeableImportantWorkService(
        CommunityStore store,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory,
        ILogger<TeableImportantWorkService> logger)
    {
        _store = store;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public ImportantWorkItemProjection Record(ImportantWorkItemRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        DateTimeOffset now = DateTimeOffset.UtcNow;
        string itemId = Normalize(request.ItemId) ?? $"work_{Guid.NewGuid():N}";
        var item = new ImportantWorkItemProjection(
            ItemId: itemId,
            Kind: Normalize(request.Kind) ?? "workflow",
            Scope: Normalize(request.Scope) ?? "chummer.run",
            Summary: Truncate(Normalize(request.Summary) ?? "Important Chummer work", 240),
            Detail: Normalize(request.Detail) ?? string.Empty,
            Status: Normalize(request.Status) ?? "open",
            Priority: Normalize(request.Priority) ?? "normal",
            UserId: Normalize(request.UserId),
            SubjectId: Normalize(request.SubjectId),
            Source: Normalize(request.Source) ?? "chummer.run",
            Link: Normalize(request.Link),
            Tags: NormalizeTags(request.Tags),
            CreatedAtUtc: now,
            UpdatedAtUtc: now);

        lock (_store.Gate)
        {
            int existingIndex = _store.ImportantWorkItems.FindIndex(existing => string.Equals(existing.ItemId, item.ItemId, StringComparison.OrdinalIgnoreCase));
            if (existingIndex >= 0)
            {
                ImportantWorkItemProjection existing = _store.ImportantWorkItems[existingIndex];
                item = item with { CreatedAtUtc = existing.CreatedAtUtc };
                _store.ImportantWorkItems[existingIndex] = item;
            }
            else
            {
                _store.ImportantWorkItems.Add(item);
            }

            _store.PersistLocked();
        }

        if (ParseBool(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_AUTOSYNC_ENABLED"], defaultValue: false))
        {
            QueueSyncItem(item);
        }

        return item;
    }

    public void QueueSyncItem(ImportantWorkItemProjection item)
    {
        TeableOptions options = ResolveOptions();
        if (!options.Enabled || !options.CanAttemptSync)
        {
            return;
        }

        _ = Task.Run(async () =>
        {
            try
            {
                await SyncItemsInternalAsync([item], options, CancellationToken.None);
            }
            catch (Exception ex)
            {
                SetSyncFailure($"autosync_failed:{ShortMessage(ex)}", DateTimeOffset.UtcNow);
                _logger.LogWarning(ex, "could not auto-project important Chummer work item {ItemId} into Teable", item.ItemId);
            }
        });
    }

    public TeableImportantWorkDashboard GetDashboard()
    {
        TeableOptions options = ResolveOptions();
        IReadOnlyList<ImportantWorkItemProjection> items = GetStoredItems();
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

        return new TeableImportantWorkDashboard(
            Enabled: options.Enabled,
            Configured: options.CanAttemptSync,
            State: state,
            ApiBaseUrl: options.ApiBaseUrl,
            BaseId: baseId,
            TableId: tableId,
            TableName: options.TableName,
            StoredItemCount: items.Count,
            LastAttemptedSyncAtUtc: lastAttempted,
            LastSuccessfulSyncAtUtc: lastSuccessful,
            LastError: lastError,
            Items: items);
    }

    public Task<TeableImportantWorkSyncResult> SyncAllAsync(CancellationToken cancellationToken = default)
        => SyncItemsInternalAsync(GetStoredItems(), ResolveOptions(), cancellationToken);

    private async Task<TeableImportantWorkSyncResult> SyncItemsInternalAsync(
        IReadOnlyList<ImportantWorkItemProjection> items,
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

        string? guardError = ValidateChummerDestination(options);
        if (guardError is not null)
        {
            SetSyncFailure(guardError, now);
            return BuildResult(StateFailed, items.Count, 0, items.Count, options.TableName, options.BaseId, options.TableId, now, [guardError]);
        }

        await _syncGate.WaitAsync(cancellationToken);
        try
        {
            TeableDestination destination;
            try
            {
                destination = await EnsureDestinationAsync(options, cancellationToken);
            }
            catch (Exception ex) when (ex is InvalidOperationException or HttpRequestException or TaskCanceledException)
            {
                string error = Truncate(ex.Message, 240);
                SetSyncFailure(error, now);
                return BuildResult(StateFailed, items.Count, 0, items.Count, options.TableName, options.BaseId, options.TableId, now, [error]);
            }
            Dictionary<string, string> existingRecords = await FetchExistingRecordIdsAsync(destination.TableId, options, cancellationToken);
            int synced = 0;
            int failed = 0;
            List<string> errors = new();

            foreach (ImportantWorkItemProjection item in items)
            {
                try
                {
                    if (existingRecords.TryGetValue(item.ItemId, out string? recordId))
                    {
                        await PatchRecordAsync(destination.TableId, recordId, item, options, cancellationToken);
                    }
                    else
                    {
                        await CreateRecordAsync(destination.TableId, item, options, cancellationToken);
                    }

                    synced++;
                }
                catch (Exception ex)
                {
                    failed++;
                    errors.Add($"{item.ItemId}:{ShortMessage(ex)}");
                }
            }

            TeableImportantWorkSyncResult result = BuildResult(
                failed == 0 ? StatePassed : StateFailed,
                items.Count,
                synced,
                failed,
                options.TableName,
                destination.BaseId,
                destination.TableId,
                now,
                errors);

            if (failed == 0)
            {
                SetSyncSuccess(now, destination);
            }
            else
            {
                SetSyncFailure(string.Join(" | ", errors.Take(4)), now, destination);
            }

            return result;
        }
        finally
        {
            _syncGate.Release();
        }
    }

    private async Task<TeableDestination> EnsureDestinationAsync(TeableOptions options, CancellationToken cancellationToken)
    {
        string? baseId = Normalize(options.BaseId);
        if (string.IsNullOrWhiteSpace(baseId))
        {
            throw new InvalidOperationException("teable_chummer_run_base_id_required");
        }

        string tableId = Normalize(options.TableId) ?? await ResolveOrCreateTableIdAsync(baseId, options, cancellationToken);
        await EnsureFieldsAsync(tableId, options, cancellationToken);
        _resolvedBaseId = baseId;
        _resolvedTableId = tableId;
        return new TeableDestination(baseId, tableId, options.TableName);
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
            ["description"] = "Important chummer.run workflow and user-related notes. Chummer remains the system of record.",
            ["icon"] = "\ud83d\udccb",
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

                await SendAsync(HttpMethod.Post, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/field", requiredField.ToJson(), options.ApiKey, cancellationToken);
            }
        }
    }

    private async Task<Dictionary<string, string>> FetchExistingRecordIdsAsync(string tableId, TeableOptions options, CancellationToken cancellationToken)
    {
        Dictionary<string, string> rows = new(StringComparer.OrdinalIgnoreCase);
        JsonDocument response = await SendAsync(HttpMethod.Get, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/record?fieldKeyType=name&pageSize=1000", null, options.ApiKey, cancellationToken);
        using (response)
        {
            if (!response.RootElement.TryGetProperty("records", out JsonElement records) || records.ValueKind != JsonValueKind.Array)
            {
                return rows;
            }

            foreach (JsonElement record in records.EnumerateArray())
            {
                if (!TryGetString(record, "id", out string? recordId)
                    || !record.TryGetProperty("fields", out JsonElement fields)
                    || !TryGetString(fields, "Item Id", out string? itemId))
                {
                    continue;
                }

                rows[itemId!] = recordId!;
            }
        }

        return rows;
    }

    private Task CreateRecordAsync(string tableId, ImportantWorkItemProjection item, TeableOptions options, CancellationToken cancellationToken)
        => SendNoResultAsync(HttpMethod.Post, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/record", new JsonObject
        {
            ["fieldKeyType"] = "name",
            ["typecast"] = true,
            ["records"] = new JsonArray(new JsonObject { ["fields"] = BuildFields(item) })
        }, options.ApiKey, cancellationToken);

    private Task PatchRecordAsync(string tableId, string recordId, ImportantWorkItemProjection item, TeableOptions options, CancellationToken cancellationToken)
        => SendNoResultAsync(HttpMethod.Patch, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/record/{Uri.EscapeDataString(recordId)}", new JsonObject
        {
            ["fieldKeyType"] = "name",
            ["typecast"] = true,
            ["record"] = new JsonObject { ["fields"] = BuildFields(item) }
        }, options.ApiKey, cancellationToken);

    private static JsonObject BuildFields(ImportantWorkItemProjection item)
        => new()
        {
            ["Item Id"] = item.ItemId,
            ["Kind"] = item.Kind,
            ["Scope"] = item.Scope,
            ["Summary"] = item.Summary,
            ["Detail"] = item.Detail,
            ["Status"] = item.Status,
            ["Priority"] = item.Priority,
            ["User Id"] = item.UserId ?? string.Empty,
            ["Subject Id"] = item.SubjectId ?? string.Empty,
            ["Source"] = item.Source ?? string.Empty,
            ["Link"] = item.Link ?? string.Empty,
            ["Tags"] = string.Join('\n', item.Tags ?? Array.Empty<string>()),
            ["Created At UTC"] = item.CreatedAtUtc.UtcDateTime.ToString("O"),
            ["Updated At UTC"] = item.UpdatedAtUtc.UtcDateTime.ToString("O"),
            ["Last Synced At UTC"] = DateTimeOffset.UtcNow.UtcDateTime.ToString("O")
        };

    private IReadOnlyList<ImportantWorkItemProjection> GetStoredItems()
    {
        lock (_store.Gate)
        {
            return _store.ImportantWorkItems
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
        }
    }

    private TeableOptions ResolveOptions()
    {
        bool enabled = ParseBool(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_ENABLED"], defaultValue: true);
        string apiKey = Normalize(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_API_KEY"])
            ?? Normalize(_configuration["TEABLE_API_KEY"])
            ?? string.Empty;
        string apiBaseUrl = (Normalize(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_API_BASE_URL"]) ?? DefaultApiBaseUrl).TrimEnd('/');
        string tableName = Normalize(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME"]) ?? DefaultTableName;
        string? baseId = Normalize(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID"]);
        string? tableId = Normalize(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID"]);
        string basePurpose = Normalize(_configuration["CHUMMER_TEABLE_IMPORTANT_WORK_BASE_PURPOSE"]) ?? "chummer.run";
        return new TeableOptions(enabled, apiKey, apiBaseUrl, baseId, tableId, tableName, basePurpose);
    }

    private static string? ValidateChummerDestination(TeableOptions options)
    {
        if (!string.Equals(options.BasePurpose, "chummer.run", StringComparison.OrdinalIgnoreCase))
        {
            return "teable_important_work_requires_chummer_run_base";
        }

        string combined = $"{options.TableName} {options.BasePurpose}";
        if (combined.Contains("executive assistant", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("executive_assistant", StringComparison.OrdinalIgnoreCase))
        {
            return "teable_important_work_refuses_executive_assistant_destination";
        }

        return null;
    }

    private async Task<JsonDocument> SendAsync(HttpMethod method, string url, JsonNode? body, string apiKey, CancellationToken cancellationToken)
    {
        using HttpRequestMessage request = BuildRequest(method, url, body, apiKey);
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

    private async Task SendNoResultAsync(HttpMethod method, string url, JsonNode body, string apiKey, CancellationToken cancellationToken)
    {
        using JsonDocument _ = await SendAsync(method, url, body, apiKey, cancellationToken);
    }

    private static HttpRequestMessage BuildRequest(HttpMethod method, string url, JsonNode? body, string apiKey)
    {
        HttpRequestMessage request = new(method, url);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (body is not null)
        {
            request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        }

        return request;
    }

    private TimeSpan ResolveHttpTimeout()
    {
        string? raw = Normalize(_configuration[HttpTimeoutSecondsConfigKey]);
        return int.TryParse(raw, out int seconds) && seconds >= 1 ? TimeSpan.FromSeconds(seconds) : DefaultHttpTimeout;
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

    private static TeableImportantWorkSyncResult BuildResult(
        string state,
        int attemptedCount,
        int syncedCount,
        int failedCount,
        string tableName,
        string? baseId,
        string? tableId,
        DateTimeOffset occurredAtUtc,
        IReadOnlyList<string> errors)
        => new(state, attemptedCount, syncedCount, failedCount, baseId, tableId, tableName, occurredAtUtc, errors);

    private static bool MatchesTable(JsonElement table, string candidate)
        => (TryGetString(table, "name", out string? name) && string.Equals(name, candidate, StringComparison.OrdinalIgnoreCase))
            || (TryGetString(table, "dbTableName", out string? dbTableName) && string.Equals(dbTableName, candidate, StringComparison.OrdinalIgnoreCase));

    private static string GetRequiredString(JsonElement element, string propertyName)
        => TryGetString(element, propertyName, out string? value) ? value! : throw new InvalidOperationException($"teable_missing_{propertyName}");

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

    private static IReadOnlyList<string> NormalizeTags(IReadOnlyList<string>? tags)
        => (tags ?? Array.Empty<string>())
            .Select(Normalize)
            .Where(static tag => tag is not null)
            .Select(static tag => tag!)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(24)
            .ToArray();

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

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
        string TableName,
        string BasePurpose)
    {
        public bool CanAttemptSync => Enabled && !string.IsNullOrWhiteSpace(ApiKey);
    }

    private sealed record TeableDestination(string? BaseId, string TableId, string TableName);

    private sealed record TeableFieldDefinition(string Name, string Type, string? Description = null)
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
