using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Api.Services;

public sealed class PublicTrustPulseService
{
    private const string DefaultPulseRelativePath = ".codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json";
    private const string PulseFileKey = "CHUMMER_PUBLIC_WEEKLY_PULSE_FILE";
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicTrustPulseService> _logger;

    public PublicTrustPulseService(IConfiguration configuration, ILogger<PublicTrustPulseService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public PublicTrustPulseSnapshot? LoadSnapshot()
    {
        string? pulsePath = ResolvePulsePath();
        if (string.IsNullOrWhiteSpace(pulsePath) || !File.Exists(pulsePath))
        {
            return null;
        }

        try
        {
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
            var payload = JsonSerializer.Deserialize<WeeklyProductPulsePayload>(File.ReadAllText(pulsePath), options);
            if (payload is null
                || !string.Equals(payload.ContractName, "chummer.weekly_product_pulse", StringComparison.Ordinal))
            {
                return null;
            }

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
                HistorySnapshotCount: payload.SupportingSignals?.HistorySnapshotCount,
                LongestPoleLabel: payload.SupportingSignals?.LongestPole,
                NextCheckpointQuestion: payload.NextCheckpointQuestion);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Skipping public trust pulse after load failure from {Path}.", pulsePath);
            return null;
        }
    }

    private string? ResolvePulsePath()
    {
        if (_configuration[PulseFileKey]?.Trim() is { Length: > 0 } configuredPulsePath)
        {
            return configuredPulsePath;
        }

        var relativePath = DefaultPulseRelativePath.Replace('/', Path.DirectorySeparatorChar);
        string? canonRoot = _configuration["CHUMMER_PUBLIC_CANON_ROOT"]?.Trim();
        var candidates = new[]
        {
            !string.IsNullOrWhiteSpace(canonRoot) ? Path.Combine(canonRoot, relativePath) : null,
            Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
            Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath)),
            Path.GetFullPath(Path.Combine("/docker/chummercomplete/chummer.run-services", relativePath))
        };

        return candidates
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
        [property: JsonPropertyName("longest_pole")] string? LongestPole);
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
    string? LongestPoleLabel,
    string? NextCheckpointQuestion);
