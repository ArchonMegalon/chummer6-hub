using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.KarmaForge;

public sealed record TeableKarmaForgeReviewBoardRow(
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
    string? LastIntentId,
    string SubmissionId,
    string PacketId,
    string Title,
    string QueueStatus,
    string QueueSummary,
    string CandidateDecision,
    string CandidateDecisionMeaning,
    string ReporterRole,
    string RuleCategory,
    string Severity,
    bool FollowUpAllowed,
    string ConsentSummary,
    string ReporterNextAction,
    IReadOnlyList<string> JourneyProofEventRefs,
    string ImpactNotes,
    string FeedbackPrompt,
    string ShareabilityNotes,
    DateTimeOffset SubmittedAtUtc);

public sealed record TeableKarmaForgeReviewBoardDashboard(
    bool Enabled,
    bool Configured,
    string State,
    string ApiBaseUrl,
    string? BaseId,
    string? TableId,
    string TableName,
    int ProjectedRowCount,
    int GovernorQueueCount,
    int FollowUpCandidateCount,
    DateTimeOffset? LastAttemptedSyncAtUtc,
    DateTimeOffset? LastSuccessfulSyncAtUtc,
    string? LastError,
    IReadOnlyList<TeableKarmaForgeReviewBoardRow> Rows);

public sealed record TeableKarmaForgeReviewBoardSyncResult(
    string State,
    int AttemptedCount,
    int SyncedCount,
    int FailedCount,
    string? BaseId,
    string? TableId,
    string TableName,
    DateTimeOffset OccurredAtUtc,
    IReadOnlyList<string> Errors);

public sealed class TeableKarmaForgeReviewBoardService
{
    private const string HttpTimeoutSecondsConfigKey = "CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS";
    private static readonly TimeSpan DefaultHttpTimeout = TimeSpan.FromSeconds(15);
    private const string DefaultApiBaseUrl = "https://app.teable.ai/api";
    private const string DefaultTableName = "Karma Forge Review Board";
    private const string DefaultDbTableName = "karma_forge_review_board";
    private const string ProjectionKind = "karma_forge_candidate_review";
    private const string SourceSystem = "chummer6-hub";
    private const string SourceContract = "Chummer.Run.Api.Services.KarmaForge.KarmaForgeSubmissionProjection";
    private const string VisibilityClass = "operator_only";
    private const string KillSwitchKey = "teable_karma_forge_review_board";
    private const string StateDisabled = "disabled";
    private const string StateUnconfigured = "unconfigured";
    private const string StateReady = "ready";
    private const string StateFailed = "failed";
    private const string StatePassed = "passed";

    private static readonly string[] EditableFields =
    [
        "Proposed Status",
        "Curator Note",
        "Reviewer Assignment"
    ];

    private static readonly string[] ForbiddenFields =
    [
        "Canonical Status",
        "Support Case State",
        "Private Runner State"
    ];

    private static readonly TeableFieldDefinition[] RequiredFields =
    [
        new("Projection Id", "singleLineText", Unique: true, NotNull: true, Description: "Stable Teable projection row id. Teable is never canonical truth."),
        new("Projection Kind", "singleLineText", Description: "Hub-owned projection contract family."),
        new("Source System", "singleLineText", Description: "Canonical system that owns the truth."),
        new("Source Contract", "singleLineText", Description: "Canonical source type for the projected row."),
        new("Source Id", "singleLineText", Description: "Canonical source object id."),
        new("Source Version", "singleLineText", Description: "Hub-owned source revision fingerprint for stale-row detection."),
        new("Source Hash", "singleLineText", Description: "Hash of the canonical projection payload."),
        new("Projection Generated At", "singleLineText", Description: "UTC timestamp when Hub generated this projection row."),
        new("Visibility Class", "singleLineText", Description: "Hub-owned visibility scope."),
        new("Editable Fields", "longText", Description: "Fields operators may edit in Teable as intent only."),
        new("Forbidden Fields", "longText", Description: "Canonical fields that Teable may never edit."),
        new("Kill Switch Key", "singleLineText", Description: "Hub kill-switch key that controls this projection lane."),
        new("Last Intent Id", "singleLineText", Description: "Most recent AdminIntent id associated with the row, when available."),
        new("Submission Id", "singleLineText", Description: "KARMA FORGE submission id."),
        new("Packet Id", "singleLineText", Description: "Normalized HouseRuleDemandPacket id."),
        new("Title", "singleLineText", Description: "Hub-owned submission title."),
        new("Queue Status", "singleLineText", Description: "Current Hub queue state."),
        new("Queue Summary", "longText", Description: "Operator-facing bounded queue explanation."),
        new("Candidate Decision", "singleLineText", Description: "Current candidate decision hypothesis from Hub."),
        new("Candidate Meaning", "longText", Description: "Human-readable meaning for the candidate decision."),
        new("Reporter Role", "singleLineText", Description: "Bounded reporter role summary."),
        new("Rule Category", "singleLineText", Description: "Hub-owned rule category."),
        new("Severity", "singleLineText", Description: "Hub-owned severity signal."),
        new("Follow-Up Allowed", "singleLineText", Description: "Whether bounded follow-up is allowed."),
        new("Consent Summary", "singleLineText", Description: "Reporter consent posture."),
        new("Reporter Next Action", "longText", Description: "Hub-owned reporter next action."),
        new("Journey Proof Event Refs", "longText", Description: "Journey proof event refs carried by the packet."),
        new("Impact Notes", "longText", Description: "Operator impact notes from the normalized packet."),
        new("Feedback Prompt", "longText", Description: "Reporter feedback prompt."),
        new("Shareability Notes", "longText", Description: "Shareability and packaging notes."),
        new("Submitted At UTC", "singleLineText", Description: "Original Hub submission timestamp."),
        new("Proposed Status", "singleLineText", Description: "Operator-entered proposed status. Intent only until Hub accepts it."),
        new("Curator Note", "longText", Description: "Operator note. Intent only until Hub accepts it."),
        new("Reviewer Assignment", "singleLineText", Description: "Operator reviewer assignment. Intent only until Hub accepts it."),
        new("Last Synced At UTC", "singleLineText", Description: "Most recent Teable projection timestamp.")
    ];

    private readonly KarmaForgeStore _store;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<TeableKarmaForgeReviewBoardService> _logger;
    private readonly SemaphoreSlim _syncGate = new(1, 1);
    private readonly object _stateGate = new();

    private string? _resolvedBaseId;
    private string? _resolvedTableId;
    private DateTimeOffset? _lastAttemptedSyncAtUtc;
    private DateTimeOffset? _lastSuccessfulSyncAtUtc;
    private string? _lastError;

    public TeableKarmaForgeReviewBoardService(
        KarmaForgeStore store,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory,
        ILogger<TeableKarmaForgeReviewBoardService> logger)
    {
        _store = store;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public TeableKarmaForgeReviewBoardDashboard GetDashboard()
    {
        TeableOptions options = ResolveOptions();
        IReadOnlyList<TeableKarmaForgeReviewBoardRow> rows = GetRows();
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
            GovernorQueueCount: rows.Count(static row => string.Equals(row.QueueStatus, "queued_for_product_governor", StringComparison.OrdinalIgnoreCase)),
            FollowUpCandidateCount: rows.Count(static row => string.Equals(row.QueueStatus, "candidate_for_lunacal_followup", StringComparison.OrdinalIgnoreCase)),
            LastAttemptedSyncAtUtc: lastAttempted,
            LastSuccessfulSyncAtUtc: lastSuccessful,
            LastError: lastError,
            Rows: rows);
    }

    public Task<TeableKarmaForgeReviewBoardSyncResult> SyncAllAsync(CancellationToken cancellationToken = default)
        => SyncRowsInternalAsync(GetRows(), ResolveOptions(), cancellationToken);

    private async Task<TeableKarmaForgeReviewBoardSyncResult> SyncRowsInternalAsync(
        IReadOnlyList<TeableKarmaForgeReviewBoardRow> rows,
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
            foreach (TeableKarmaForgeReviewBoardRow row in rows)
            {
                try
                {
                    await UpsertRowAsync(destination, row, options, cancellationToken);
                    synced++;
                }
                catch (Exception ex)
                {
                    string error = $"{row.SubmissionId}:{ShortMessage(ex)}";
                    errors.Add(error);
                    _logger.LogWarning(ex, "could not project KARMA FORGE submission {SubmissionId} into Teable table {TableId}", row.SubmissionId, destination.TableId);
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
            _logger.LogWarning(ex, "could not resolve Teable destination for KARMA FORGE review board projection");
            return BuildResult(StateFailed, rows.Count, 0, rows.Count, options.TableName, _resolvedBaseId ?? options.BaseId, _resolvedTableId ?? options.TableId, now, [ShortMessage(ex)]);
        }
        finally
        {
            _syncGate.Release();
        }
    }

    private IReadOnlyList<TeableKarmaForgeReviewBoardRow> GetRows()
    {
        lock (_store.Gate)
        {
            return _store.SubmissionsById.Values
                .Where(ShouldProjectSubmission)
                .OrderByDescending(static item => item.SubmittedAtUtc)
                .Select(BuildRow)
                .ToArray();
        }
    }

    private static bool ShouldProjectSubmission(KarmaForgeSubmissionProjection submission)
        => submission.Packet.Source.ExternalStages.Any(static stage =>
            string.Equals(stage.StageKey, "review_board", StringComparison.OrdinalIgnoreCase)
            && string.Equals(stage.Status, "bounded_ready", StringComparison.OrdinalIgnoreCase));

    private static TeableKarmaForgeReviewBoardRow BuildRow(KarmaForgeSubmissionProjection submission)
    {
        string sourceVersion = BuildSourceVersion(submission);
        string sourceHash = BuildSourceHash(submission);
        string projectionId = $"karmaforge:{submission.SubmissionId}";
        return new(
            ProjectionId: projectionId,
            ProjectionKind: ProjectionKind,
            SourceSystem: SourceSystem,
            SourceContract: SourceContract,
            SourceId: submission.SubmissionId,
            SourceVersion: sourceVersion,
            SourceHash: sourceHash,
            ProjectionGeneratedAtUtc: DateTimeOffset.UtcNow,
            VisibilityClass: VisibilityClass,
            EditableFields: EditableFields,
            ForbiddenFields: ForbiddenFields,
            KillSwitchKey: KillSwitchKey,
            LastIntentId: null,
            SubmissionId: submission.SubmissionId,
            PacketId: submission.Packet.Id,
            Title: submission.Packet.Title,
            QueueStatus: submission.QueueStatus,
            QueueSummary: submission.QueueSummary,
            CandidateDecision: submission.Candidate.CandidateDecision,
            CandidateDecisionMeaning: submission.Candidate.CandidateDecisionMeaning,
            ReporterRole: submission.Packet.Source.RespondentRole,
            RuleCategory: submission.Packet.Source.RuleCategory,
            Severity: submission.Packet.Source.Severity,
            FollowUpAllowed: submission.FollowUpAllowed,
            ConsentSummary: submission.ConsentSummary,
            ReporterNextAction: submission.ReporterNextAction,
            JourneyProofEventRefs: submission.Packet.Source.JourneyProofEventRefs
                .Select(static item => $"{item.JourneyKey}:{item.EventKey}")
                .ToArray(),
            ImpactNotes: submission.Packet.OperatorNotes.ImpactNotes,
            FeedbackPrompt: submission.Packet.OperatorNotes.FeedbackPrompt,
            ShareabilityNotes: submission.Packet.OperatorNotes.ShareabilityNotes,
            SubmittedAtUtc: submission.SubmittedAtUtc);
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
            return new(baseId, tableId, options.TableName);
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
        return new(baseId, tableId, options.TableName);
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
            ["description"] = "Administrative KARMA FORGE review-board projection. Chummer Hub remains the system of record.",
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

    private async Task UpsertRowAsync(
        TeableDestination destination,
        TeableKarmaForgeReviewBoardRow row,
        TeableOptions options,
        CancellationToken cancellationToken)
    {
        string? recordId = await FindExistingRecordIdAsync(destination.TableId, row.ProjectionId, options, cancellationToken);
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
            JsonDocument ignored = await SendAsync(
                HttpMethod.Patch,
                $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(destination.TableId)}/record/{Uri.EscapeDataString(recordId)}",
                payload,
                options.ApiKey,
                cancellationToken);
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
        JsonDocument created = await SendAsync(
            HttpMethod.Post,
            $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(destination.TableId)}/record",
            createPayload,
            options.ApiKey,
            cancellationToken);
        created.Dispose();
    }

    private async Task<string?> FindExistingRecordIdAsync(
        string tableId,
        string projectionId,
        TeableOptions options,
        CancellationToken cancellationToken)
    {
        string escapedProjectionId = projectionId.Replace("'", "\\'", StringComparison.Ordinal);
        string filter = Uri.EscapeDataString($"{{Projection Id}} = '{escapedProjectionId}'");
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

    private static JsonObject BuildFields(TeableKarmaForgeReviewBoardRow row)
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
            ["Last Intent Id"] = Normalize(row.LastIntentId) ?? string.Empty,
            ["Submission Id"] = row.SubmissionId,
            ["Packet Id"] = row.PacketId,
            ["Title"] = row.Title,
            ["Queue Status"] = row.QueueStatus,
            ["Queue Summary"] = row.QueueSummary,
            ["Candidate Decision"] = row.CandidateDecision,
            ["Candidate Meaning"] = row.CandidateDecisionMeaning,
            ["Reporter Role"] = row.ReporterRole,
            ["Rule Category"] = row.RuleCategory,
            ["Severity"] = row.Severity,
            ["Follow-Up Allowed"] = row.FollowUpAllowed ? "true" : "false",
            ["Consent Summary"] = row.ConsentSummary,
            ["Reporter Next Action"] = row.ReporterNextAction,
            ["Journey Proof Event Refs"] = string.Join('\n', row.JourneyProofEventRefs),
            ["Impact Notes"] = row.ImpactNotes,
            ["Feedback Prompt"] = row.FeedbackPrompt,
            ["Shareability Notes"] = row.ShareabilityNotes,
            ["Submitted At UTC"] = row.SubmittedAtUtc.ToString("O"),
            ["Proposed Status"] = string.Empty,
            ["Curator Note"] = string.Empty,
            ["Reviewer Assignment"] = string.Empty,
            ["Last Synced At UTC"] = DateTimeOffset.UtcNow.ToString("O"),
        };

    private TeableOptions ResolveOptions()
    {
        bool enabled = ParseBool(_configuration["CHUMMER_TEABLE_KARMA_FORGE_ENABLED"], defaultValue: false);
        string apiKey = Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_API_KEY"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_API_KEY"])
            ?? Normalize(_configuration["TEABLE_API_KEY"])
            ?? string.Empty;
        string apiBaseUrl = (Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_API_BASE_URL"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_API_BASE_URL"])
            ?? DefaultApiBaseUrl).TrimEnd('/');
        string tableName = Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_TABLE_NAME"]) ?? DefaultTableName;
        string? baseId = Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_BASE_ID"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_BASE_ID"]);
        string? tableId = Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_TABLE_ID"]);
        return new(
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

    private static TeableKarmaForgeReviewBoardSyncResult BuildResult(
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

    private static string BuildSourceVersion(KarmaForgeSubmissionProjection submission)
    {
        string basis = string.Join('|',
            submission.SubmissionId,
            submission.QueueStatus,
            submission.Candidate.CandidateDecision,
            submission.Packet.Id,
            submission.Packet.Classification.CurrentStatus,
            submission.SubmittedAtUtc.ToString("O"));
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(basis));
        return Convert.ToHexString(bytes)[..16].ToLowerInvariant();
    }

    private static string BuildSourceHash(KarmaForgeSubmissionProjection submission)
    {
        string json = JsonSerializer.Serialize(submission);
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(json));
        return $"sha256:{Convert.ToHexString(bytes).ToLowerInvariant()}";
    }

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
