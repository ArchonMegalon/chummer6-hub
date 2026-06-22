using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api.Services.Community;

public sealed record TeableHeyyScamChatRow(
    string ProjectionId,
    string ProjectionKind,
    string SourceSystem,
    string SourceContract,
    string SourceId,
    string SourceVersion,
    string SourceHash,
    DateTimeOffset ProjectionGeneratedAtUtc,
    string VisibilityClass,
    IReadOnlyList<string> EditableFields,
    IReadOnlyList<string> ForbiddenFields,
    string KillSwitchKey,
    string ConversationId,
    string Channel,
    string Counterparty,
    string Mode,
    string PersonaId,
    string SafetyStatus,
    string ScamPattern,
    string ReplyObjective,
    string OperatorNextAction,
    IReadOnlyList<string> RiskSignals,
    IReadOnlyList<string> MissingContextChecks,
    IReadOnlyList<string> ForbiddenActions,
    int SuggestedDelaySeconds,
    string Transcript,
    string LatestDraft,
    string LatestPacingHint,
    bool ManualApprovalRequired,
    bool AutoSendAllowed,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record TeableHeyyScamChatDashboard(
    bool Enabled,
    bool Configured,
    string State,
    string ApiBaseUrl,
    string? BaseId,
    string? TableId,
    string TableName,
    int ProjectedRowCount,
    DateTimeOffset? LastAttemptedSyncAtUtc,
    DateTimeOffset? LastSuccessfulSyncAtUtc,
    string? LastError,
    IReadOnlyList<TeableHeyyScamChatRow> Rows);

public sealed record TeableHeyyScamChatSyncResult(
    string State,
    int AttemptedCount,
    int SyncedCount,
    int FailedCount,
    string? BaseId,
    string? TableId,
    string TableName,
    DateTimeOffset OccurredAtUtc,
    IReadOnlyList<string> Errors);

public sealed class TeableHeyyScamChatService
{
    private const string DefaultApiBaseUrl = "https://app.teable.ai/api";
    private const string DefaultTableName = "Heyy Scam Chat Conversations";
    private const string DefaultDbTableName = "heyy_scam_chat_conversations";
    private const string ProjectionKind = "heyy_scam_chat_conversation";
    private const string SourceSystem = "chummer6-hub";
    private const string SourceContract = "Chummer.Run.Api.Services.Community.HeyyScamChatConversationState";
    private const string VisibilityClass = "operator_only";
    private const string KillSwitchKey = "teable_heyy_scam_chat";
    private const string StateDisabled = "disabled";
    private const string StateUnconfigured = "unconfigured";
    private const string StateReady = "ready";
    private const string StateFailed = "failed";
    private const string StatePassed = "passed";

    private static readonly string[] EditableFields =
    [
        "Operator Status",
        "Operator Note",
        "Manual Reply Sent At UTC"
    ];

    private static readonly string[] ForbiddenFields =
    [
        "Mode",
        "Auto Send Allowed",
        "Manual Approval Required",
        "Counterparty Hash",
        "Canonical Transcript"
    ];

    private static readonly TeableFieldDefinition[] RequiredFields =
    [
        new("Projection Id", "singleLineText", Unique: true, NotNull: true, Description: "Stable Teable projection row id. Hub remains canonical truth."),
        new("Projection Kind", "singleLineText", Description: "Hub-owned projection contract family."),
        new("Source System", "singleLineText", Description: "Canonical system that owns the truth."),
        new("Source Contract", "singleLineText", Description: "Canonical source type for the projected row."),
        new("Source Id", "singleLineText", Description: "Canonical conversation id."),
        new("Source Version", "singleLineText", Description: "Hub-owned source revision fingerprint for stale-row detection."),
        new("Source Hash", "singleLineText", Description: "Hash of the canonical projection payload."),
        new("Projection Generated At", "singleLineText", Description: "UTC timestamp when Hub generated this projection row."),
        new("Visibility Class", "singleLineText", Description: "Hub-owned visibility scope."),
        new("Editable Fields", "longText", Description: "Fields operators may edit in Teable as intent only."),
        new("Forbidden Fields", "longText", Description: "Canonical fields that Teable may never edit."),
        new("Kill Switch Key", "singleLineText", Description: "Hub kill-switch key that controls this projection lane."),
        new("Conversation Id", "singleLineText", Unique: true, NotNull: true, Description: "Stable Heyy scam-chat conversation id."),
        new("Channel", "singleLineText", Description: "Source channel, e.g. heyy or manual import."),
        new("Counterparty", "singleLineText", Description: "Counterparty handle as allowed by runtime redaction settings."),
        new("Mode", "singleLineText", Description: "Always draft_only for this lane."),
        new("Persona Id", "singleLineText", Description: "Draft persona policy id."),
        new("Safety Status", "singleLineText", Description: "Manual approval and safety posture."),
        new("Scam Pattern", "singleLineText", Description: "Detected scam pattern."),
        new("Reply Objective", "longText", Description: "Operator-facing draft objective."),
        new("Operator Next Action", "longText", Description: "Recommended next action before any manual reply."),
        new("Risk Signals", "longText", Description: "Detected risk signals, one per line."),
        new("Missing Context Checks", "longText", Description: "What the operator should verify outside the scam chat."),
        new("Forbidden Actions", "longText", Description: "Actions the bot and operator flow must not perform."),
        new("Suggested Delay Seconds", "singleLineText", Description: "Old-lady slow typing delay suggestion."),
        new("Transcript", "longText", Description: "Conversation transcript according to configured redaction policy."),
        new("Latest Draft", "longText", Description: "Latest manual-approval draft."),
        new("Latest Pacing Hint", "longText", Description: "How slowly to reply if manually approved."),
        new("Manual Approval Required", "singleLineText", Description: "Always true for this lane."),
        new("Auto Send Allowed", "singleLineText", Description: "Always false for this lane."),
        new("Created At UTC", "singleLineText", Description: "Conversation creation timestamp."),
        new("Updated At UTC", "singleLineText", Description: "Most recent conversation update timestamp."),
        new("Operator Status", "singleLineText", Description: "Operator-entered status. Intent only until Hub accepts it."),
        new("Operator Note", "longText", Description: "Operator note. Intent only until Hub accepts it."),
        new("Manual Reply Sent At UTC", "singleLineText", Description: "Operator-entered send timestamp. Intent only until Hub accepts it."),
        new("Last Synced At UTC", "singleLineText", Description: "Most recent Teable projection timestamp.")
    ];

    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<TeableHeyyScamChatService> _logger;
    private readonly SemaphoreSlim _syncGate = new(1, 1);
    private readonly object _stateGate = new();

    private string? _resolvedBaseId;
    private string? _resolvedTableId;
    private DateTimeOffset? _lastAttemptedSyncAtUtc;
    private DateTimeOffset? _lastSuccessfulSyncAtUtc;
    private string? _lastError;

    public TeableHeyyScamChatService(
        CommunityStore store,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory,
        ILogger<TeableHeyyScamChatService> logger)
    {
        _store = store;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public void QueueSyncConversation(HeyyScamChatConversationState conversation)
    {
        ArgumentNullException.ThrowIfNull(conversation);

        TeableOptions options = ResolveOptions();
        if (!options.Enabled || !options.CanAttemptSync)
        {
            return;
        }

        _ = Task.Run(async () =>
        {
            try
            {
                await SyncRowsInternalAsync([BuildRow(conversation)], options, CancellationToken.None);
            }
            catch (Exception ex)
            {
                SetSyncFailure($"autosync_failed:{ShortMessage(ex)}", DateTimeOffset.UtcNow);
                _logger.LogWarning(ex, "could not auto-project Heyy scam-chat conversation {ConversationId} into Teable", conversation.ConversationId);
            }
        });
    }

    public TeableHeyyScamChatDashboard GetDashboard()
    {
        TeableOptions options = ResolveOptions();
        IReadOnlyList<TeableHeyyScamChatRow> rows = GetRows();
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

        return new(
            Enabled: options.Enabled,
            Configured: options.CanAttemptSync,
            State: state,
            ApiBaseUrl: options.ApiBaseUrl,
            BaseId: baseId,
            TableId: tableId,
            TableName: options.TableName,
            ProjectedRowCount: rows.Count,
            LastAttemptedSyncAtUtc: lastAttempted,
            LastSuccessfulSyncAtUtc: lastSuccessful,
            LastError: lastError,
            Rows: rows);
    }

    public Task<TeableHeyyScamChatSyncResult> SyncAllAsync(CancellationToken cancellationToken = default)
        => SyncRowsInternalAsync(GetRows(), ResolveOptions(), cancellationToken);

    private async Task<TeableHeyyScamChatSyncResult> SyncRowsInternalAsync(
        IReadOnlyList<TeableHeyyScamChatRow> rows,
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
            foreach (TeableHeyyScamChatRow row in rows)
            {
                try
                {
                    await UpsertRowAsync(destination, row, options, cancellationToken);
                    synced++;
                }
                catch (Exception ex)
                {
                    string error = $"{row.ConversationId}:{ShortMessage(ex)}";
                    errors.Add(error);
                    _logger.LogWarning(ex, "could not project Heyy scam-chat conversation {ConversationId} into Teable table {TableId}", row.ConversationId, destination.TableId);
                }
            }

            if (errors.Count == 0)
            {
                SetSyncSuccess(now, destination);
                return BuildResult(StatePassed, rows.Count, synced, 0, destination.TableName, destination.BaseId, destination.TableId, now, errors);
            }

            SetSyncFailure(string.Join(" | ", errors.Take(4)), now, destination);
            return BuildResult(StateFailed, rows.Count, synced, errors.Count, destination.TableName, destination.BaseId, destination.TableId, now, errors);
        }
        catch (Exception ex)
        {
            SetSyncFailure(ShortMessage(ex), now);
            _logger.LogWarning(ex, "could not resolve Teable destination for Heyy scam-chat projection");
            return BuildResult(StateFailed, rows.Count, 0, rows.Count, options.TableName, _resolvedBaseId ?? options.BaseId, _resolvedTableId ?? options.TableId, now, [ShortMessage(ex)]);
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
            ["description"] = "Administrative projection of Heyy scam-chat conversations. Chummer Hub remains the system of record.",
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

                JsonDocument ignored = await SendAsync(HttpMethod.Post, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/field", requiredField.ToJson(), options.ApiKey, cancellationToken);
                ignored.Dispose();
            }
        }
    }

    private async Task UpsertRowAsync(TeableDestination destination, TeableHeyyScamChatRow row, TeableOptions options, CancellationToken cancellationToken)
    {
        string? recordId = await FindExistingRecordIdAsync(destination.TableId, row.ConversationId, options, cancellationToken);
        JsonObject fields = BuildFields(row);
        if (!string.IsNullOrWhiteSpace(recordId))
        {
            JsonObject payload = new()
            {
                ["fieldKeyType"] = "name",
                ["typecast"] = true,
                ["record"] = new JsonObject
                {
                    ["fields"] = fields
                }
            };
            JsonDocument ignored = await SendAsync(HttpMethod.Patch, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(destination.TableId)}/record/{Uri.EscapeDataString(recordId)}", payload, options.ApiKey, cancellationToken);
            ignored.Dispose();
            return;
        }

        JsonObject createPayload = new()
        {
            ["fieldKeyType"] = "name",
            ["typecast"] = true,
            ["records"] = new JsonArray
            {
                new JsonObject
                {
                    ["fields"] = fields
                }
            }
        };
        JsonDocument created = await SendAsync(HttpMethod.Post, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(destination.TableId)}/record", createPayload, options.ApiKey, cancellationToken);
        created.Dispose();
    }

    private async Task<string?> FindExistingRecordIdAsync(string tableId, string conversationId, TeableOptions options, CancellationToken cancellationToken)
    {
        string filter = Uri.EscapeDataString($"{{Conversation Id}} = '{conversationId}'");
        string path = $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/record?fieldKeyType=name&take=1&filterByTql={filter}";
        JsonDocument response = await SendAsync(HttpMethod.Get, path, null, options.ApiKey, cancellationToken);
        using (response)
        {
            if (!response.RootElement.TryGetProperty("records", out JsonElement records)
                || records.ValueKind != JsonValueKind.Array)
            {
                return null;
            }

            foreach (JsonElement record in records.EnumerateArray())
            {
                if (TryGetString(record, "id", out string? recordId))
                {
                    return recordId;
                }
            }

            return null;
        }
    }

    private static JsonObject BuildFields(TeableHeyyScamChatRow row)
        => new()
        {
            ["Projection Id"] = row.ProjectionId,
            ["Projection Kind"] = row.ProjectionKind,
            ["Source System"] = row.SourceSystem,
            ["Source Contract"] = row.SourceContract,
            ["Source Id"] = row.SourceId,
            ["Source Version"] = row.SourceVersion,
            ["Source Hash"] = row.SourceHash,
            ["Projection Generated At"] = row.ProjectionGeneratedAtUtc.ToString("O"),
            ["Visibility Class"] = row.VisibilityClass,
            ["Editable Fields"] = string.Join('\n', row.EditableFields),
            ["Forbidden Fields"] = string.Join('\n', row.ForbiddenFields),
            ["Kill Switch Key"] = row.KillSwitchKey,
            ["Conversation Id"] = row.ConversationId,
            ["Channel"] = row.Channel,
            ["Counterparty"] = row.Counterparty,
            ["Mode"] = row.Mode,
            ["Persona Id"] = row.PersonaId,
            ["Safety Status"] = row.SafetyStatus,
            ["Scam Pattern"] = row.ScamPattern,
            ["Reply Objective"] = row.ReplyObjective,
            ["Operator Next Action"] = row.OperatorNextAction,
            ["Risk Signals"] = string.Join('\n', row.RiskSignals),
            ["Missing Context Checks"] = string.Join('\n', row.MissingContextChecks),
            ["Forbidden Actions"] = string.Join('\n', row.ForbiddenActions),
            ["Suggested Delay Seconds"] = row.SuggestedDelaySeconds.ToString(),
            ["Transcript"] = row.Transcript,
            ["Latest Draft"] = row.LatestDraft,
            ["Latest Pacing Hint"] = row.LatestPacingHint,
            ["Manual Approval Required"] = row.ManualApprovalRequired ? "true" : "false",
            ["Auto Send Allowed"] = row.AutoSendAllowed ? "true" : "false",
            ["Created At UTC"] = row.CreatedAtUtc.ToString("O"),
            ["Updated At UTC"] = row.UpdatedAtUtc.ToString("O"),
            ["Last Synced At UTC"] = DateTimeOffset.UtcNow.ToString("O"),
        };

    private IReadOnlyList<TeableHeyyScamChatRow> GetRows()
    {
        lock (_store.Gate)
        {
            return _store.HeyyScamChatConversations
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Select(BuildRow)
                .ToArray();
        }
    }

    private static TeableHeyyScamChatRow BuildRow(HeyyScamChatConversationState conversation)
    {
        string sourceVersion = conversation.UpdatedAtUtc.ToString("O");
        string transcript = BuildTranscript(conversation);
        string sourceHash = HashProjection(string.Join("|", conversation.ConversationId, sourceVersion, transcript, conversation.LatestDraft?.DraftText ?? string.Empty));
        return new TeableHeyyScamChatRow(
            ProjectionId: $"heyy-scam-chat:{conversation.ConversationId}",
            ProjectionKind: ProjectionKind,
            SourceSystem: SourceSystem,
            SourceContract: SourceContract,
            SourceId: conversation.ConversationId,
            SourceVersion: sourceVersion,
            SourceHash: sourceHash,
            ProjectionGeneratedAtUtc: DateTimeOffset.UtcNow,
            VisibilityClass: VisibilityClass,
            EditableFields: EditableFields,
            ForbiddenFields: ForbiddenFields,
            KillSwitchKey: KillSwitchKey,
            ConversationId: conversation.ConversationId,
            Channel: conversation.Channel,
            Counterparty: conversation.CounterpartyMasked,
            Mode: conversation.Mode,
            PersonaId: conversation.PersonaId,
            SafetyStatus: conversation.SafetyStatus,
            ScamPattern: conversation.Enrichment.ScamPattern,
            ReplyObjective: conversation.Enrichment.ReplyObjective,
            OperatorNextAction: conversation.Enrichment.OperatorNextAction,
            RiskSignals: conversation.Enrichment.RiskSignals,
            MissingContextChecks: conversation.Enrichment.MissingContextChecks,
            ForbiddenActions: conversation.Enrichment.ForbiddenActions,
            SuggestedDelaySeconds: conversation.Enrichment.SuggestedDelaySeconds,
            Transcript: transcript,
            LatestDraft: conversation.LatestDraft?.DraftText ?? string.Empty,
            LatestPacingHint: conversation.LatestDraft?.PacingHint ?? string.Empty,
            ManualApprovalRequired: true,
            AutoSendAllowed: false,
            CreatedAtUtc: conversation.CreatedAtUtc,
            UpdatedAtUtc: conversation.UpdatedAtUtc);
    }

    private static string BuildTranscript(HeyyScamChatConversationState conversation)
    {
        StringBuilder builder = new();
        foreach (HeyyScamChatMessage message in conversation.Messages.OrderBy(static item => item.CreatedAtUtc))
        {
            builder.Append(message.CreatedAtUtc.ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss 'UTC'"))
                .Append(' ')
                .Append(message.Direction)
                .Append(": ")
                .AppendLine(message.Text);
            if (message.Direction == "draft")
            {
                builder.Append("  pacing: ").AppendLine(message.PacingHint);
            }
        }

        return builder.ToString().Trim();
    }

    private TeableOptions ResolveOptions()
    {
        bool enabled = ParseBool(_configuration["CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED"], defaultValue: true);
        string apiKey = Normalize(_configuration["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_KEY"])
            ?? Normalize(_configuration["TEABLE_API_KEY"])
            ?? string.Empty;
        string apiBaseUrl = (Normalize(_configuration["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_BASE_URL"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_API_BASE_URL"])
            ?? DefaultApiBaseUrl).TrimEnd('/');
        string tableName = Normalize(_configuration["CHUMMER_TEABLE_HEYY_SCAM_CHAT_TABLE_NAME"]) ?? DefaultTableName;
        string? baseId = Normalize(_configuration["CHUMMER_TEABLE_HEYY_SCAM_CHAT_BASE_ID"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_BASE_ID"]);
        string? tableId = Normalize(_configuration["CHUMMER_TEABLE_HEYY_SCAM_CHAT_TABLE_ID"]);
        return new TeableOptions(enabled, apiKey, apiBaseUrl, baseId, tableId, tableName);
    }

    private async Task<JsonDocument> SendAsync(HttpMethod method, string url, JsonNode? body, string apiKey, CancellationToken cancellationToken)
    {
        using HttpRequestMessage request = new(method, url);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (body is not null)
        {
            request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        }

        using HttpResponseMessage response = await _httpClientFactory.CreateClient().SendAsync(request, cancellationToken);
        string content = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"teable_http_{(int)response.StatusCode}:{Truncate(content, 240)}");
        }

        return JsonDocument.Parse(string.IsNullOrWhiteSpace(content) ? "{}" : content);
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

    private static TeableHeyyScamChatSyncResult BuildResult(string state, int attemptedCount, int syncedCount, int failedCount, string tableName, string? baseId, string? tableId, DateTimeOffset occurredAtUtc, IReadOnlyList<string> errors)
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

    private static string HashProjection(string value)
    {
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }

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

    private sealed record TeableOptions(bool Enabled, string ApiKey, string ApiBaseUrl, string? BaseId, string? TableId, string TableName)
    {
        public bool CanAttemptSync => Enabled && !string.IsNullOrWhiteSpace(ApiKey);
    }

    private sealed record TeableDestination(string? BaseId, string TableId, string TableName);

    private sealed record TeableFieldDefinition(string Name, string Type, bool Unique = false, bool NotNull = false, string? Description = null)
    {
        public JsonObject ToJson()
        {
            JsonObject node = new()
            {
                ["type"] = Type,
                ["name"] = Name,
            };
            if (Unique && SupportsFieldValidation(Type))
            {
                node["unique"] = true;
            }

            if (NotNull && SupportsFieldValidation(Type))
            {
                node["notNull"] = true;
            }

            if (!string.IsNullOrWhiteSpace(Description))
            {
                node["description"] = Description;
            }

            return node;
        }

        private static bool SupportsFieldValidation(string fieldType)
            => !string.Equals(fieldType, "singleLineText", StringComparison.OrdinalIgnoreCase);
    }
}

public sealed class TeableHeyyScamChatSyncWorker : BackgroundService
{
    private static readonly TimeSpan DefaultInitialDelay = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan DefaultInterval = TimeSpan.FromMinutes(30);

    private readonly TeableHeyyScamChatService _teableHeyyScamChat;
    private readonly IConfiguration _configuration;
    private readonly ILogger<TeableHeyyScamChatSyncWorker> _logger;

    public TeableHeyyScamChatSyncWorker(
        TeableHeyyScamChatService teableHeyyScamChat,
        IConfiguration configuration,
        ILogger<TeableHeyyScamChatSyncWorker> logger)
    {
        _teableHeyyScamChat = teableHeyyScamChat;
        _configuration = configuration;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!IsEnabled())
        {
            return;
        }

        TimeSpan initialDelay = ResolveDurationSeconds("CHUMMER_TEABLE_HEYY_SCAM_CHAT_RECONCILE_INITIAL_DELAY_SECONDS", DefaultInitialDelay);
        TimeSpan interval = ResolveDurationMinutes("CHUMMER_TEABLE_HEYY_SCAM_CHAT_RECONCILE_INTERVAL_MINUTES", DefaultInterval);

        if (initialDelay > TimeSpan.Zero)
        {
            await Task.Delay(initialDelay, stoppingToken);
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                TeableHeyyScamChatSyncResult result = await _teableHeyyScamChat.SyncAllAsync(stoppingToken);
                if (string.Equals(result.State, "passed", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogInformation(
                        "Teable Heyy scam-chat reconciliation synced {SyncedCount}/{AttemptedCount} rows into {TableId}.",
                        result.SyncedCount,
                        result.AttemptedCount,
                        result.TableId ?? "(unresolved)");
                }
                else if (!string.Equals(result.State, "disabled", StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(result.State, "unconfigured", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogWarning(
                        "Teable Heyy scam-chat reconciliation ended in {State} with {FailedCount} failed rows: {Errors}",
                        result.State,
                        result.FailedCount,
                        string.Join(" | ", result.Errors.Take(4)));
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Teable Heyy scam-chat reconciliation loop failed.");
            }

            await Task.Delay(interval, stoppingToken);
        }
    }

    private bool IsEnabled()
        => ParseBool(_configuration["CHUMMER_TEABLE_HEYY_SCAM_CHAT_RECONCILE_ENABLED"], defaultValue: true);

    private TimeSpan ResolveDurationMinutes(string key, TimeSpan fallback)
    {
        string? raw = Normalize(_configuration[key]);
        return int.TryParse(raw, out int minutes) && minutes > 0 ? TimeSpan.FromMinutes(minutes) : fallback;
    }

    private TimeSpan ResolveDurationSeconds(string key, TimeSpan fallback)
    {
        string? raw = Normalize(_configuration[key]);
        return int.TryParse(raw, out int seconds) && seconds >= 0 ? TimeSpan.FromSeconds(seconds) : fallback;
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static bool ParseBool(string? value, bool defaultValue)
    {
        string? normalized = Normalize(value);
        return normalized is null ? defaultValue : bool.TryParse(normalized, out bool parsed) ? parsed : defaultValue;
    }
}
