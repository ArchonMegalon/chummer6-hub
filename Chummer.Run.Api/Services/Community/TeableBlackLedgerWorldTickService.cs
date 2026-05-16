using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;

namespace Chummer.Run.Api.Services.Community;

public sealed record TeableBlackLedgerWorldTickRow(
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
    string WorldTickId,
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string WorldRef,
    string TickRef,
    string Summary,
    IReadOnlyList<string> CauseRefs,
    IReadOnlyList<string> Changes,
    int HeatDelta,
    string SpoilerPolicy,
    bool GmApproved,
    string? WorldFrameId,
    string? WorldReceiptRef,
    string? ShadowfeedBulletinId,
    string? ShadowfeedBulletinReceiptRef,
    DateTimeOffset CreatedAtUtc);

public sealed record TeableBlackLedgerWorldTickDashboard(
    bool Enabled,
    bool Configured,
    string State,
    string ApiBaseUrl,
    string? BaseId,
    string? TableId,
    string TableName,
    int ProjectedRowCount,
    int GmApprovedCount,
    DateTimeOffset? LastAttemptedSyncAtUtc,
    DateTimeOffset? LastSuccessfulSyncAtUtc,
    string? LastError,
    IReadOnlyList<TeableBlackLedgerWorldTickRow> Rows);

public sealed record TeableBlackLedgerWorldTickSyncResult(
    string State,
    int AttemptedCount,
    int SyncedCount,
    int FailedCount,
    string? BaseId,
    string? TableId,
    string TableName,
    DateTimeOffset OccurredAtUtc,
    IReadOnlyList<string> Errors);

public sealed class TeableBlackLedgerWorldTickService
{
    private const string DefaultApiBaseUrl = "https://app.teable.ai/api";
    private const string DefaultTableName = "Black Ledger World Ticks";
    private const string DefaultDbTableName = "black_ledger_world_ticks";
    private const string ProjectionKind = "black_ledger_world_tick_review";
    private const string SourceSystem = "chummer6-hub";
    private const string SourceContract = "Chummer.Run.Api.Contracts.CampaignAdoptionWorldTickProjection";
    private const string VisibilityClass = "operator_only";
    private const string KillSwitchKey = "teable_black_ledger_world_ticks";
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
        "Faction Secret State",
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
        new("World Tick Id", "singleLineText", Description: "Canonical BLACK LEDGER world tick id."),
        new("Workspace Id", "singleLineText", Description: "Owning workspace id."),
        new("Campaign Id", "singleLineText", Description: "Owning campaign id."),
        new("Campaign Name", "singleLineText", Description: "Campaign display name."),
        new("World Ref", "singleLineText", Description: "World reference key."),
        new("Tick Ref", "singleLineText", Description: "Tick reference key."),
        new("Summary", "longText", Description: "Operator-facing world tick summary."),
        new("Cause Refs", "longText", Description: "Cause references that grounded the tick."),
        new("Changes", "longText", Description: "Structured delta summaries for the tick."),
        new("Heat Delta", "singleLineText", Description: "Heat delta carried by the world tick."),
        new("Spoiler Policy", "singleLineText", Description: "Hub-owned spoiler policy."),
        new("GM Approved", "singleLineText", Description: "Whether the tick is GM-approved."),
        new("World Frame Id", "singleLineText", Description: "World-frame projection ref when available."),
        new("World Receipt Ref", "singleLineText", Description: "Canonical world receipt ref."),
        new("Shadowfeed Bulletin Id", "singleLineText", Description: "Player-safe bulletin ref when available."),
        new("Shadowfeed Bulletin Receipt Ref", "singleLineText", Description: "Player-safe bulletin receipt ref."),
        new("Created At UTC", "singleLineText", Description: "Original canonical creation timestamp."),
        new("Proposed Status", "singleLineText", Description: "Operator-entered proposed status. Intent only until Hub accepts it."),
        new("Curator Note", "longText", Description: "Operator note. Intent only until Hub accepts it."),
        new("Reviewer Assignment", "singleLineText", Description: "Operator reviewer assignment. Intent only until Hub accepts it."),
        new("Last Synced At UTC", "singleLineText", Description: "Most recent Teable projection timestamp.")
    ];

    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<TeableBlackLedgerWorldTickService> _logger;
    private readonly SemaphoreSlim _syncGate = new(1, 1);
    private readonly object _stateGate = new();

    private string? _resolvedBaseId;
    private string? _resolvedTableId;
    private DateTimeOffset? _lastAttemptedSyncAtUtc;
    private DateTimeOffset? _lastSuccessfulSyncAtUtc;
    private string? _lastError;

    public TeableBlackLedgerWorldTickService(
        CommunityStore store,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory,
        ILogger<TeableBlackLedgerWorldTickService> logger)
    {
        _store = store;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public TeableBlackLedgerWorldTickDashboard GetDashboard()
    {
        TeableOptions options = ResolveOptions();
        IReadOnlyList<TeableBlackLedgerWorldTickRow> rows = GetRows();
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
            GmApprovedCount: rows.Count(static row => row.GmApproved),
            LastAttemptedSyncAtUtc: lastAttempted,
            LastSuccessfulSyncAtUtc: lastSuccessful,
            LastError: lastError,
            Rows: rows);
    }

    public Task<TeableBlackLedgerWorldTickSyncResult> SyncAllAsync(CancellationToken cancellationToken = default)
        => SyncRowsInternalAsync(GetRows(), ResolveOptions(), cancellationToken);

    private async Task<TeableBlackLedgerWorldTickSyncResult> SyncRowsInternalAsync(
        IReadOnlyList<TeableBlackLedgerWorldTickRow> rows,
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
            foreach (TeableBlackLedgerWorldTickRow row in rows)
            {
                try
                {
                    await UpsertRowAsync(destination, row, options, cancellationToken);
                    synced++;
                }
                catch (Exception ex)
                {
                    string error = $"{row.WorldTickId}:{ShortMessage(ex)}";
                    errors.Add(error);
                    _logger.LogWarning(ex, "could not project BLACK LEDGER world tick {WorldTickId} into Teable table {TableId}", row.WorldTickId, destination.TableId);
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
            _logger.LogWarning(ex, "could not resolve Teable destination for BLACK LEDGER world tick projection");
            return BuildResult(StateFailed, rows.Count, 0, rows.Count, options.TableName, _resolvedBaseId ?? options.BaseId, _resolvedTableId ?? options.TableId, now, [ShortMessage(ex)]);
        }
        finally
        {
            _syncGate.Release();
        }
    }

    private IReadOnlyList<TeableBlackLedgerWorldTickRow> GetRows()
    {
        lock (_store.Gate)
        {
            return _store.WorldTicks
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Select(BuildRow)
                .ToArray();
        }
    }

    private static TeableBlackLedgerWorldTickRow BuildRow(WorldTickProjection tick)
    {
        string json = JsonSerializer.Serialize(tick);
        string sourceHash = $"sha256:{Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(json))).ToLowerInvariant()}";
        string sourceVersion = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(
            $"{tick.WorldTickId}|{tick.WorldFrameId}|{tick.WorldReceiptRef}|{tick.ShadowfeedBulletinId}|{tick.UpdatedAtUtc:O}")))[..16].ToLowerInvariant();

        return new(
            ProjectionId: $"blackledger:{tick.WorldTickId}",
            ProjectionKind: ProjectionKind,
            SourceSystem: SourceSystem,
            SourceContract: SourceContract,
            SourceId: tick.WorldTickId,
            SourceVersion: sourceVersion,
            SourceHash: sourceHash,
            ProjectionGeneratedAtUtc: DateTimeOffset.UtcNow,
            VisibilityClass: VisibilityClass,
            EditableFields: EditableFields,
            ForbiddenFields: ForbiddenFields,
            KillSwitchKey: KillSwitchKey,
            LastIntentId: null,
            WorldTickId: tick.WorldTickId,
            WorkspaceId: tick.WorkspaceId,
            CampaignId: tick.CampaignId,
            CampaignName: tick.CampaignId,
            WorldRef: tick.CampaignId,
            TickRef: tick.RunId,
            Summary: tick.Summary,
            CauseRefs: [tick.RunId, tick.RunTitle],
            Changes: [$"world_tick: {tick.RunTitle} (0) - {tick.ConsequenceSummary}"],
            HeatDelta: 0,
            SpoilerPolicy: "player_safe_preview_only",
            GmApproved: true,
            WorldFrameId: tick.WorldFrameId,
            WorldReceiptRef: tick.WorldReceiptRef,
            ShadowfeedBulletinId: tick.ShadowfeedBulletinId,
            ShadowfeedBulletinReceiptRef: tick.ShadowfeedBulletinReceiptRef,
            CreatedAtUtc: tick.UpdatedAtUtc);
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
            ["description"] = "Administrative BLACK LEDGER world-tick projection. Chummer Hub remains the system of record.",
            ["icon"] = "\ud83c\udf06",
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
        TeableBlackLedgerWorldTickRow row,
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
                new JsonObject { ["fields"] = fields }
            }
        };
        JsonDocument created = await SendAsync(HttpMethod.Post, $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(destination.TableId)}/record", createPayload, options.ApiKey, cancellationToken);
        created.Dispose();
    }

    private async Task<string?> FindExistingRecordIdAsync(string tableId, string projectionId, TeableOptions options, CancellationToken cancellationToken)
    {
        string escapedProjectionId = projectionId.Replace("'", "\\'", StringComparison.Ordinal);
        string filter = Uri.EscapeDataString($"{{Projection Id}} = '{escapedProjectionId}'");
        string path = $"{options.ApiBaseUrl}/table/{Uri.EscapeDataString(tableId)}/record?fieldKeyType=name&take=1&filterByTql={filter}";
        JsonDocument response = await SendAsync(HttpMethod.Get, path, null, options.ApiKey, cancellationToken);
        using (response)
        {
            if (!response.RootElement.TryGetProperty("records", out JsonElement records) || records.ValueKind != JsonValueKind.Array)
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

    private static JsonObject BuildFields(TeableBlackLedgerWorldTickRow row)
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
            ["World Tick Id"] = row.WorldTickId,
            ["Workspace Id"] = row.WorkspaceId,
            ["Campaign Id"] = row.CampaignId,
            ["Campaign Name"] = row.CampaignName,
            ["World Ref"] = row.WorldRef,
            ["Tick Ref"] = row.TickRef,
            ["Summary"] = row.Summary,
            ["Cause Refs"] = string.Join('\n', row.CauseRefs),
            ["Changes"] = string.Join('\n', row.Changes),
            ["Heat Delta"] = row.HeatDelta.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["Spoiler Policy"] = row.SpoilerPolicy,
            ["GM Approved"] = row.GmApproved ? "true" : "false",
            ["World Frame Id"] = Normalize(row.WorldFrameId) ?? string.Empty,
            ["World Receipt Ref"] = Normalize(row.WorldReceiptRef) ?? string.Empty,
            ["Shadowfeed Bulletin Id"] = Normalize(row.ShadowfeedBulletinId) ?? string.Empty,
            ["Shadowfeed Bulletin Receipt Ref"] = Normalize(row.ShadowfeedBulletinReceiptRef) ?? string.Empty,
            ["Created At UTC"] = row.CreatedAtUtc.ToString("O"),
            ["Proposed Status"] = string.Empty,
            ["Curator Note"] = string.Empty,
            ["Reviewer Assignment"] = string.Empty,
            ["Last Synced At UTC"] = DateTimeOffset.UtcNow.ToString("O"),
        };

    private TeableOptions ResolveOptions()
    {
        bool enabled = ParseBool(_configuration["CHUMMER_TEABLE_BLACK_LEDGER_ENABLED"], defaultValue: true);
        string apiKey = Normalize(_configuration["CHUMMER_TEABLE_BLACK_LEDGER_API_KEY"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_API_KEY"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_API_KEY"])
            ?? Normalize(_configuration["TEABLE_API_KEY"])
            ?? string.Empty;
        string apiBaseUrl = (Normalize(_configuration["CHUMMER_TEABLE_BLACK_LEDGER_API_BASE_URL"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_API_BASE_URL"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_API_BASE_URL"])
            ?? DefaultApiBaseUrl).TrimEnd('/');
        string tableName = Normalize(_configuration["CHUMMER_TEABLE_BLACK_LEDGER_TABLE_NAME"]) ?? DefaultTableName;
        string? baseId = Normalize(_configuration["CHUMMER_TEABLE_BLACK_LEDGER_BASE_ID"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_KARMA_FORGE_BASE_ID"])
            ?? Normalize(_configuration["CHUMMER_TEABLE_USERS_BASE_ID"]);
        string? tableId = Normalize(_configuration["CHUMMER_TEABLE_BLACK_LEDGER_TABLE_ID"]);
        return new(enabled, apiKey, apiBaseUrl, baseId, tableId, tableName);
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

    private static TeableBlackLedgerWorldTickSyncResult BuildResult(string state, int attemptedCount, int syncedCount, int failedCount, string tableName, string? baseId, string? tableId, DateTimeOffset occurredAtUtc, IReadOnlyList<string> errors)
        => new(state, attemptedCount, syncedCount, failedCount, baseId, tableId, tableName, occurredAtUtc, errors);

    private static bool MatchesTable(JsonElement table, string candidate)
        => (TryGetString(table, "name", out string? name) && string.Equals(name, candidate, StringComparison.OrdinalIgnoreCase))
            || (TryGetString(table, "dbTableName", out string? dbTableName) && string.Equals(dbTableName, candidate, StringComparison.OrdinalIgnoreCase));

    private static string GetRequiredString(JsonElement element, string propertyName)
        => TryGetString(element, propertyName, out string? value) ? value! : throw new InvalidOperationException($"teable_missing_{propertyName}");

    private static bool TryGetString(JsonElement element, string propertyName, out string? value)
    {
        value = null;
        if (!element.TryGetProperty(propertyName, out JsonElement property) || property.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
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
            if (Unique)
            {
                node["unique"] = true;
            }

            if (NotNull)
            {
                node["notNull"] = true;
            }

            if (!string.IsNullOrWhiteSpace(Description))
            {
                node["description"] = Description;
            }

            return node;
        }
    }
}
