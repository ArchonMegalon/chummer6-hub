using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Api.Services;

public sealed class PublicTrustPulseService
{
    private const int MaxProgressTrendSamples = 8;
    private const string DefaultProgressHistoryRelativePath = ".codex-design/product/PROGRESS_HISTORY.generated.json";
    private const string DefaultProgressReportRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.json";
    private const string DefaultLocalReleaseProofRelativePath = ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json";
    private const string ProgressHistoryFileKey = "CHUMMER_PUBLIC_PROGRESS_HISTORY_FILE";
    private const string ProgressReportFileKey = "CHUMMER_PUBLIC_PROGRESS_REPORT_FILE";
    private const string LocalReleaseProofFileKey = "CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE";
    private readonly WeeklyProductPulseArtifactService _weeklyPulse;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicTrustPulseService> _logger;

    public PublicTrustPulseService(
        WeeklyProductPulseArtifactService weeklyPulse,
        IConfiguration configuration,
        ILogger<PublicTrustPulseService> logger)
    {
        _weeklyPulse = weeklyPulse;
        _configuration = configuration;
        _logger = logger;
    }

    public PublicTrustPulseSnapshot? LoadSnapshot()
    {
        string pulseJson = _weeklyPulse.LoadWeeklyPulseJson();
        if (string.IsNullOrWhiteSpace(pulseJson))
        {
            return null;
        }

        try
        {
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
            var payload = JsonSerializer.Deserialize<WeeklyProductPulsePayload>(pulseJson, options);
            if (payload is null
                || !string.Equals(payload.ContractName, "chummer.weekly_product_pulse", StringComparison.Ordinal))
            {
                return null;
            }

            var progressReport = LoadOptionalArtifact<ProgressReportPayload>(
                ResolveProgressReportPath(),
                options,
                static payload => string.Equals(payload.ContractName, "fleet.public_progress_report", StringComparison.Ordinal),
                "public progress report");
            var progressHistory = LoadOptionalArtifact<ProgressHistoryPayload>(
                ResolveProgressHistoryPath(),
                options,
                static payload => string.Equals(payload.ContractName, "fleet.public_progress_history", StringComparison.Ordinal),
                "public progress history");
            var progressTrend = ComputeProgressTrend(progressHistory);
            var progressTrendSamples = ExtractProgressTrendSamples(progressHistory);
            var localReleaseProof = LoadOptionalArtifact<LocalReleaseProofPayload>(
                ResolveLocalReleaseProofPath(),
                options,
                static payload => string.Equals(payload.ContractName, "chummer6-hub.local_release_proof", StringComparison.Ordinal),
                "hub local release proof");

            return new PublicTrustPulseSnapshot(
                AsOf: payload.AsOf ?? string.Empty,
                Summary: payload.Summary ?? string.Empty,
                ActiveWave: payload.ActiveWave ?? string.Empty,
                ActiveWaveStatus: payload.ActiveWaveStatus,
                ActiveCheckpointId: payload.ActiveCheckpoint?.Id,
                ActiveCheckpointTitle: payload.ActiveCheckpoint?.Title,
                ActiveCheckpointStatus: payload.ActiveCheckpoint?.Status,
                JourneyGateState: payload.JourneyGateHealth?.State,
                JourneyGateReason: payload.JourneyGateHealth?.Reason,
                BlockedJourneyCount: payload.JourneyGateHealth?.BlockedCount,
                WarningJourneyCount: payload.JourneyGateHealth?.WarningCount,
                ReleaseHealthState: payload.Snapshot?.ReleaseHealth?.State,
                ReleaseHealthReason: payload.Snapshot?.ReleaseHealth?.Reason,
                OverallProgressPercent: payload.SupportingSignals?.OverallProgressPercent,
                PhaseLabel: payload.SupportingSignals?.PhaseLabel,
                HistorySnapshotCount: payload.SupportingSignals?.HistorySnapshotCount ?? progressReport?.HistorySnapshotCount,
                ProgressHistorySnapshotCount: progressHistory?.SnapshotCount,
                ProgressTrendDirection: progressTrend?.Direction,
                ProgressTrendDeltaPercent: progressTrend?.DeltaPercent,
                ProgressTrendFromAsOf: progressTrend?.FromAsOf,
                ProgressTrendToAsOf: progressTrend?.ToAsOf,
                ProgressTrendSamples: progressTrendSamples.Count > 0 ? progressTrendSamples : null,
                LongestPoleLabel: payload.SupportingSignals?.LongestPole,
                LaunchReadiness: payload.SupportingSignals?.LaunchReadiness,
                ProviderRouteDefault: payload.SupportingSignals?.ProviderRouteStewardship?.DefaultStatus,
                ProviderRouteCanary: payload.SupportingSignals?.ProviderRouteStewardship?.CanaryStatus,
                ProviderRouteReviewDue: payload.SupportingSignals?.ProviderRouteStewardship?.ReviewDue,
                ProviderRouteNextDecision: payload.SupportingSignals?.ProviderRouteStewardship?.NextDecision,
                ClosureHealthState: payload.SupportingSignals?.ClosureHealth?.State,
                ClosureHealthOpenCaseCount: payload.SupportingSignals?.ClosureHealth?.OpenCaseCount,
                ClosureHealthWaitingCount: payload.SupportingSignals?.ClosureHealth?.WaitingClosureCount,
                ClosureHealthPendingHumanResponseCount: payload.SupportingSignals?.ClosureHealth?.PendingHumanResponseCount,
                ClosureHealthSummary: payload.SupportingSignals?.ClosureHealth?.Summary,
                NextCheckpointQuestion: payload.NextCheckpointQuestion,
                LocalReleaseProofStatus: localReleaseProof?.Status,
                ProvenJourneyCount: localReleaseProof?.JourneysPassed?.Count,
                ProvenRouteCount: localReleaseProof?.ProofRoutes?.Count);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Skipping public trust pulse after load failure from synthesized weekly pulse.");
            return null;
        }
    }

    private TPayload? LoadOptionalArtifact<TPayload>(
        string? path,
        JsonSerializerOptions options,
        Func<TPayload, bool> validator,
        string label)
        where TPayload : class
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return null;
        }

        try
        {
            var payload = JsonSerializer.Deserialize<TPayload>(File.ReadAllText(path), options);
            return payload is not null && validator(payload) ? payload : null;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Skipping optional {Label} after load failure from {Path}.", label, path);
            return null;
        }
    }

    private string? ResolveProgressReportPath() => ResolveExistingPath(ProgressReportFileKey, DefaultProgressReportRelativePath);

    private string? ResolveProgressHistoryPath() => ResolveExistingPath(ProgressHistoryFileKey, DefaultProgressHistoryRelativePath);

    private string? ResolveLocalReleaseProofPath() => ResolveExistingPath(LocalReleaseProofFileKey, DefaultLocalReleaseProofRelativePath);

    private static ProgressTrendInfo? ComputeProgressTrend(ProgressHistoryPayload? payload)
    {
        if (payload?.Snapshots is null)
        {
            return null;
        }

        var points = ExtractProgressTrendSamples(payload);

        if (points.Count < 2)
        {
            return null;
        }

        var previous = points[^2];
        var latest = points[^1];
        var delta = latest.OverallProgressPercent - previous.OverallProgressPercent;
        return new ProgressTrendInfo(
            Direction: delta > 0 ? "up" : delta < 0 ? "down" : "flat",
            DeltaPercent: Math.Abs(delta),
            FromAsOf: previous.AsOf,
            ToAsOf: latest.AsOf);
    }

    private static List<ProgressHistoryTrendPoint> ExtractProgressTrendSamples(ProgressHistoryPayload? payload)
    {
        if (payload?.Snapshots is null)
        {
            return new List<ProgressHistoryTrendPoint>(0);
        }

        var points = payload.Snapshots
            .Where(static snapshot =>
                !string.IsNullOrWhiteSpace(snapshot.AsOf)
                && snapshot.OverallProgressPercent.HasValue)
            .Select(static snapshot => new ProgressHistoryTrendPoint(snapshot.AsOf!, snapshot.OverallProgressPercent!.Value))
            .OrderBy(static item => item.AsOf)
            .ToList();

        if (points.Count <= MaxProgressTrendSamples)
        {
            return points;
        }

        return points.Skip(points.Count - MaxProgressTrendSamples).ToList();
    }

    private string? ResolveExistingPath(string configKey, string defaultRelativePath)
    {
        if (_configuration[configKey]?.Trim() is { Length: > 0 } configuredPath)
        {
            return configuredPath;
        }

        var relativePath = defaultRelativePath.Replace('/', Path.DirectorySeparatorChar);
        string? canonRoot = _configuration["CHUMMER_PUBLIC_CANON_ROOT"]?.Trim();
        return new[]
            {
                !string.IsNullOrWhiteSpace(canonRoot) ? Path.Combine(canonRoot, relativePath) : null,
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath)),
                Path.GetFullPath(Path.Combine("/docker/chummercomplete/chummer.run-services", relativePath))
            }
            .Where(static candidate => !string.IsNullOrWhiteSpace(candidate))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(static candidate => File.Exists(candidate));
    }

    private sealed record WeeklyProductPulsePayload(
        [property: JsonPropertyName("contract_name")] string? ContractName,
        [property: JsonPropertyName("as_of")] string? AsOf,
        [property: JsonPropertyName("summary")] string? Summary,
        [property: JsonPropertyName("active_wave")] string? ActiveWave,
        [property: JsonPropertyName("active_wave_status")] string? ActiveWaveStatus,
        [property: JsonPropertyName("active_nine_month_checkpoint")] WeeklyProductPulseCheckpoint? ActiveCheckpoint,
        [property: JsonPropertyName("journey_gate_health")] WeeklyProductPulseHealth? JourneyGateHealth,
        [property: JsonPropertyName("next_checkpoint_question")] string? NextCheckpointQuestion,
        [property: JsonPropertyName("snapshot")] WeeklyProductPulseSnapshotPayload? Snapshot,
        [property: JsonPropertyName("supporting_signals")] WeeklyProductPulseSupportingSignals? SupportingSignals);

    private sealed record WeeklyProductPulseCheckpoint(
        [property: JsonPropertyName("id")] string? Id,
        [property: JsonPropertyName("title")] string? Title,
        [property: JsonPropertyName("status")] string? Status);

    private sealed record WeeklyProductPulseHealth(
        [property: JsonPropertyName("state")] string? State,
        [property: JsonPropertyName("reason")] string? Reason,
        [property: JsonPropertyName("blocked_count")] int? BlockedCount,
        [property: JsonPropertyName("warning_count")] int? WarningCount);

    private sealed record WeeklyProductPulseSnapshotPayload(
        [property: JsonPropertyName("release_health")] WeeklyProductPulseHealth? ReleaseHealth);

    private sealed record WeeklyProductPulseSupportingSignals(
        [property: JsonPropertyName("overall_progress_percent")] int? OverallProgressPercent,
        [property: JsonPropertyName("phase_label")] string? PhaseLabel,
        [property: JsonPropertyName("history_snapshot_count")] int? HistorySnapshotCount,
        [property: JsonPropertyName("longest_pole")] string? LongestPole,
        [property: JsonPropertyName("launch_readiness")] string? LaunchReadiness,
        [property: JsonPropertyName("provider_route_stewardship")] WeeklyProductPulseProviderRouteStewardship? ProviderRouteStewardship,
        [property: JsonPropertyName("closure_health")] WeeklyProductPulseClosureHealth? ClosureHealth);

    private sealed record WeeklyProductPulseProviderRouteStewardship(
        [property: JsonPropertyName("default_status")] string? DefaultStatus,
        [property: JsonPropertyName("canary_status")] string? CanaryStatus,
        [property: JsonPropertyName("review_due")] string? ReviewDue,
        [property: JsonPropertyName("next_decision")] string? NextDecision);

    private sealed record WeeklyProductPulseClosureHealth(
        [property: JsonPropertyName("state")] string? State,
        [property: JsonPropertyName("open_case_count")] int? OpenCaseCount,
        [property: JsonPropertyName("waiting_closure_count")] int? WaitingClosureCount,
        [property: JsonPropertyName("pending_human_response_count")] int? PendingHumanResponseCount,
        [property: JsonPropertyName("summary")] string? Summary);

    private sealed record ProgressReportPayload(
        [property: JsonPropertyName("contract_name")] string? ContractName,
        [property: JsonPropertyName("history_snapshot_count")] int? HistorySnapshotCount);

    private sealed record ProgressHistoryPayload(
        [property: JsonPropertyName("contract_name")] string? ContractName,
        [property: JsonPropertyName("snapshot_count")] int? SnapshotCount,
        [property: JsonPropertyName("snapshots")] IReadOnlyList<ProgressHistorySnapshot>? Snapshots);

    private sealed record ProgressHistorySnapshot(
        [property: JsonPropertyName("as_of")] string? AsOf,
        [property: JsonPropertyName("overall_progress_percent")] int? OverallProgressPercent);

    private sealed record LocalReleaseProofPayload(
        [property: JsonPropertyName("contract_name")] string? ContractName,
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("journeys_passed")] IReadOnlyList<string>? JourneysPassed,
        [property: JsonPropertyName("proof_routes")] IReadOnlyList<string>? ProofRoutes);

    private sealed record ProgressTrendInfo(
        string Direction,
        int DeltaPercent,
        string FromAsOf,
        string ToAsOf);
}

public sealed record PublicTrustPulseSnapshot(
    string AsOf,
    string Summary,
    string ActiveWave,
    string? ActiveWaveStatus,
    string? ActiveCheckpointId,
    string? ActiveCheckpointTitle,
    string? ActiveCheckpointStatus,
    string? JourneyGateState,
    string? JourneyGateReason,
    int? BlockedJourneyCount,
    int? WarningJourneyCount,
    string? ReleaseHealthState,
    string? ReleaseHealthReason,
    int? OverallProgressPercent,
    string? PhaseLabel,
    int? HistorySnapshotCount,
    int? ProgressHistorySnapshotCount,
    string? ProgressTrendDirection,
    int? ProgressTrendDeltaPercent,
    string? ProgressTrendFromAsOf,
    string? ProgressTrendToAsOf,
    IReadOnlyList<ProgressHistoryTrendPoint>? ProgressTrendSamples,
    string? LongestPoleLabel,
    string? NextCheckpointQuestion,
    string? LocalReleaseProofStatus,
    string? LaunchReadiness,
    string? ProviderRouteDefault,
    string? ProviderRouteCanary,
    string? ProviderRouteReviewDue,
    string? ProviderRouteNextDecision,
    string? ClosureHealthState,
    int? ClosureHealthOpenCaseCount,
    int? ClosureHealthWaitingCount,
    int? ClosureHealthPendingHumanResponseCount,
    string? ClosureHealthSummary,
    int? ProvenJourneyCount,
    int? ProvenRouteCount);

public sealed record ProgressHistoryTrendPoint(string AsOf, int OverallProgressPercent);
