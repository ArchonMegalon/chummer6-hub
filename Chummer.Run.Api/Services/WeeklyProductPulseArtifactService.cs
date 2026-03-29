using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class WeeklyProductPulseArtifactService
{
    private const string DefaultPulseRelativePath = ".codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json";
    private const string DefaultProgressReportRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.json";
    private const string DefaultLocalReleaseProofRelativePath = ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json";
    private const string DefaultFleetArtifactRoot = "/docker/fleet/.codex-studio/published";
    private const string FleetArtifactRootKey = "CHUMMER_PUBLIC_FLEET_ARTIFACT_ROOT";
    private const string JourneyGatesFileName = "JOURNEY_GATES.generated.json";
    private const string SupportPacketsFileName = "SUPPORT_CASE_PACKETS.generated.json";
    private const string StatusPlaneFileName = "STATUS_PLANE.generated.yaml";
    private static readonly JsonSerializerOptions ReadOptions = new(JsonSerializerDefaults.Web);
    private static readonly JsonSerializerOptions WriteOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };
    private static readonly IDeserializer YamlDeserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .Build();

    private readonly IConfiguration _configuration;
    private readonly ILogger<WeeklyProductPulseArtifactService> _logger;

    public WeeklyProductPulseArtifactService(
        IConfiguration configuration,
        ILogger<WeeklyProductPulseArtifactService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public string LoadWeeklyPulseJson()
    {
        string pulsePath = ResolveRequiredCanonPath(DefaultPulseRelativePath);
        string baseJson = File.ReadAllText(pulsePath);

        try
        {
            JsonObject pulse = JsonNode.Parse(baseJson)?.AsObject()
                ?? throw new InvalidOperationException("weekly pulse artifact could not be parsed.");

            WeeklyProductPulseSeed? seed = JsonSerializer.Deserialize<WeeklyProductPulseSeed>(baseJson, ReadOptions);
            ProgressReportPayload? progressReport = LoadOptionalJson<ProgressReportPayload>(ResolveOptionalCanonPath(DefaultProgressReportRelativePath));
            JourneyGatesPayload? journeyGates = LoadOptionalJson<JourneyGatesPayload>(ResolveOptionalFleetArtifactPath(JourneyGatesFileName));
            SupportPacketsPayload? supportPackets = LoadOptionalJson<SupportPacketsPayload>(ResolveOptionalFleetArtifactPath(SupportPacketsFileName));
            StatusPlanePayload? statusPlane = LoadOptionalYaml<StatusPlanePayload>(ResolveOptionalFleetArtifactPath(StatusPlaneFileName));
            LocalReleaseProofPayload? localReleaseProof = LoadOptionalJson<LocalReleaseProofPayload>(ResolveOptionalCanonPath(DefaultLocalReleaseProofRelativePath));

            ClosureHealthInfo? closureHealth = ComputeClosureHealth(journeyGates, supportPackets);
            ProviderRouteInfo providerRoute = ComputeProviderRoute(statusPlane, seed);
            string launchReadiness = ComputeLaunchReadiness(journeyGates, localReleaseProof, providerRoute, closureHealth, seed);

            JsonObject journeyGateHealth = EnsureObject(pulse, "journey_gate_health");
            if (journeyGates?.Summary is not null)
            {
                journeyGateHealth["state"] = journeyGates.Summary.OverallState;
                journeyGateHealth["reason"] = journeyGates.Summary.RecommendedAction;
                journeyGateHealth["blocked_count"] = journeyGates.Summary.BlockedCount;
                journeyGateHealth["warning_count"] = journeyGates.Summary.WarningCount;
            }

            JsonObject snapshot = EnsureObject(pulse, "snapshot");
            JsonObject supportingSignals = EnsureObject(pulse, "supporting_signals");

            if (!string.IsNullOrWhiteSpace(progressReport?.AsOf))
            {
                pulse["as_of"] = progressReport.AsOf;
            }

            if (!string.IsNullOrWhiteSpace(progressReport?.ActiveWave))
            {
                pulse["active_wave"] = progressReport.ActiveWave;
            }

            if (!string.IsNullOrWhiteSpace(progressReport?.ActiveWaveStatus))
            {
                pulse["active_wave_status"] = progressReport.ActiveWaveStatus;
            }

            if (progressReport?.OverallProgressPercent is int overallProgressPercent)
            {
                supportingSignals["overall_progress_percent"] = overallProgressPercent;
            }

            if (!string.IsNullOrWhiteSpace(progressReport?.PhaseLabel))
            {
                supportingSignals["phase_label"] = progressReport.PhaseLabel;
            }

            if (progressReport?.HistorySnapshotCount is int historySnapshotCount)
            {
                supportingSignals["history_snapshot_count"] = historySnapshotCount;
            }

            if (!string.IsNullOrWhiteSpace(progressReport?.LongestPole?.Label))
            {
                supportingSignals["longest_pole"] = progressReport.LongestPole.Label;
            }

            supportingSignals["launch_readiness"] = launchReadiness;
            supportingSignals["provider_route_stewardship"] = new JsonObject
            {
                ["default_status"] = providerRoute.DefaultStatus,
                ["canary_status"] = providerRoute.CanaryStatus,
                ["review_due"] = providerRoute.ReviewDue,
                ["next_decision"] = providerRoute.NextDecision
            };

            if (closureHealth is not null)
            {
                supportingSignals["closure_health"] = new JsonObject
                {
                    ["state"] = closureHealth.State,
                    ["open_case_count"] = closureHealth.OpenCaseCount,
                    ["waiting_closure_count"] = closureHealth.WaitingClosureCount,
                    ["pending_human_response_count"] = closureHealth.PendingHumanResponseCount,
                    ["reported_case_count"] = closureHealth.ReportedCaseCount,
                    ["materialized_packet_count"] = closureHealth.MaterializedPacketCount,
                    ["design_impact_count"] = closureHealth.DesignImpactCount,
                    ["summary"] = closureHealth.Summary
                };
            }

            if (journeyGates?.Summary is not null)
            {
                snapshot["journey_gate_health"] = new JsonObject
                {
                    ["state"] = journeyGates.Summary.OverallState,
                    ["reason"] = journeyGates.Summary.RecommendedAction,
                    ["blocked_count"] = journeyGates.Summary.BlockedCount,
                    ["warning_count"] = journeyGates.Summary.WarningCount
                };
            }

            string activeWave = JsonStringOrFallback(pulse["active_wave"], seed?.ActiveWave, "Current wave");
            string journeyState = JsonStringOrFallback(journeyGateHealth["state"], seed?.JourneyGateHealth?.State, "unknown");
            string phaseLabel = JsonStringOrFallback(supportingSignals["phase_label"], seed?.SupportingSignals?.PhaseLabel, "current phase");
            string longestPole = JsonStringOrFallback(supportingSignals["longest_pole"], seed?.SupportingSignals?.LongestPole, "current caution");
            string progressSummary = supportingSignals["overall_progress_percent"] is JsonValue progressNode
                && progressNode.TryGetValue<int>(out int currentProgress)
                ? $"{currentProgress}%"
                : "unknown";
            string closureSummary = closureHealth?.State switch
            {
                "clear" => "support closure is clear",
                "watch" => "support closure still needs follow-through",
                "monitor" => "support closure needs monitoring",
                _ => "support closure evidence is partial"
            };

            pulse["summary"] = $"{activeWave} remains the active wave; journey proof is {journeyState}; overall progress is {progressSummary} in '{phaseLabel}'; the longest pole remains {longestPole}; {closureSummary}.";
            pulse["generated_at"] = SelectLatestGeneratedAt(
                seed?.GeneratedAt,
                progressReport?.GeneratedAt,
                journeyGates?.GeneratedAt,
                supportPackets?.GeneratedAt,
                statusPlane?.GeneratedAt,
                localReleaseProof?.GeneratedAt);

            return pulse.ToJsonString(WriteOptions);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Falling back to mirrored weekly pulse artifact without evidence overlay.");
            return baseJson;
        }
    }

    private TPayload? LoadOptionalJson<TPayload>(string? path)
        where TPayload : class
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<TPayload>(File.ReadAllText(path), ReadOptions);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Skipping optional JSON artifact from {Path}.", path);
            return null;
        }
    }

    private TPayload? LoadOptionalYaml<TPayload>(string? path)
        where TPayload : class
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return null;
        }

        try
        {
            using var reader = File.OpenText(path);
            return YamlDeserializer.Deserialize<TPayload>(reader);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Skipping optional YAML artifact from {Path}.", path);
            return null;
        }
    }

    private string ResolveRequiredCanonPath(string relativePath)
    {
        string? path = ResolveOptionalCanonPath(relativePath);
        return !string.IsNullOrWhiteSpace(path) && File.Exists(path)
            ? path
            : throw new FileNotFoundException($"weekly pulse source artifact not found: {relativePath}");
    }

    private string? ResolveOptionalCanonPath(string relativePath)
    {
        string normalizedRelativePath = relativePath.Replace('/', Path.DirectorySeparatorChar);
        string? canonRoot = _configuration["CHUMMER_PUBLIC_CANON_ROOT"]?.Trim();
        if (!string.IsNullOrWhiteSpace(canonRoot))
        {
            string configuredPath = Path.Combine(canonRoot, normalizedRelativePath);
            return File.Exists(configuredPath) ? configuredPath : null;
        }

        return new[]
            {
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), normalizedRelativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", normalizedRelativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, normalizedRelativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", normalizedRelativePath)),
                Path.GetFullPath(Path.Combine("/docker/chummercomplete/chummer.run-services", normalizedRelativePath))
            }
            .Where(static candidate => !string.IsNullOrWhiteSpace(candidate))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(static candidate => File.Exists(candidate));
    }

    private string? ResolveOptionalFleetArtifactPath(string fileName)
    {
        string? configuredRoot = _configuration[FleetArtifactRootKey]?.Trim();
        if (!string.IsNullOrWhiteSpace(configuredRoot))
        {
            string configuredPath = Path.Combine(configuredRoot, fileName);
            return File.Exists(configuredPath) ? configuredPath : null;
        }

        return new[]
            {
                Path.Combine(DefaultFleetArtifactRoot, fileName)
            }
            .Where(static candidate => !string.IsNullOrWhiteSpace(candidate))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(static candidate => File.Exists(candidate));
    }

    private static ClosureHealthInfo? ComputeClosureHealth(
        JourneyGatesPayload? journeyGates,
        SupportPacketsPayload? supportPackets)
    {
        if (journeyGates is null && supportPackets is null)
        {
            return null;
        }

        int waitingClosureCount = journeyGates?.Journeys?.Sum(static item => item.Signals?.SupportClosureWaitingCount ?? 0) ?? 0;
        int pendingHumanResponseCount = journeyGates?.Journeys?.Sum(static item => item.Signals?.SupportNeedsHumanResponseCount ?? 0) ?? 0;
        int openCaseCount = supportPackets?.Summary?.OpenCaseCount ?? 0;
        int reportedCaseCount = supportPackets?.Source?.ReportedCount ?? 0;
        int materializedPacketCount = supportPackets?.Source?.MaterializedCount ?? 0;
        int designImpactCount = supportPackets?.Summary?.DesignImpactCount ?? 0;

        string state = waitingClosureCount == 0 && pendingHumanResponseCount == 0 && openCaseCount == 0
            ? "clear"
            : waitingClosureCount > 0 || pendingHumanResponseCount > 0
                ? "watch"
                : "monitor";

        string summary = state switch
        {
            "clear" => $"{waitingClosureCount} waiting closure / {pendingHumanResponseCount} pending human response. {openCaseCount} open support packets across {reportedCaseCount} reported cases.",
            "watch" => $"{waitingClosureCount} waiting closure / {pendingHumanResponseCount} pending human response. {openCaseCount} open support packets still need closure follow-through.",
            _ => $"{waitingClosureCount} waiting closure / {pendingHumanResponseCount} pending human response. {openCaseCount} open support packets and {designImpactCount} design-impact packet(s) remain under review."
        };

        return new ClosureHealthInfo(
            State: state,
            OpenCaseCount: openCaseCount,
            WaitingClosureCount: waitingClosureCount,
            PendingHumanResponseCount: pendingHumanResponseCount,
            ReportedCaseCount: reportedCaseCount,
            MaterializedPacketCount: materializedPacketCount,
            DesignImpactCount: designImpactCount,
            Summary: summary);
    }

    private static ProviderRouteInfo ComputeProviderRoute(StatusPlanePayload? statusPlane, WeeklyProductPulseSeed? seed)
    {
        if (statusPlane is null)
        {
            return new ProviderRouteInfo(
                DefaultStatus: seed?.SupportingSignals?.ProviderRouteStewardship?.DefaultStatus ?? "Pilot defaults are not yet governed",
                CanaryStatus: seed?.SupportingSignals?.ProviderRouteStewardship?.CanaryStatus ?? "Canary evidence is still accumulating",
                ReviewDue: seed?.SupportingSignals?.ProviderRouteStewardship?.ReviewDue,
                NextDecision: seed?.SupportingSignals?.ProviderRouteStewardship?.NextDecision);
        }

        bool hubIsPublicPilot = statusPlane?.Projects?.Any(static project =>
            string.Equals(project.Id, "hub", StringComparison.OrdinalIgnoreCase)
            && string.Equals(project.DeploymentAccessPosture, "public", StringComparison.OrdinalIgnoreCase)
            && string.Equals(project.DeploymentPromotionStage, "promoted_preview", StringComparison.OrdinalIgnoreCase)) == true;

        int publicTargetCount = statusPlane?.DeploymentPosture?.PublicTargetCount ?? 0;
        int degradedServiceCount = statusPlane?.RuntimeHealing?.Summary?.DegradedServiceCount ?? 0;
        string alertState = statusPlane?.RuntimeHealing?.Summary?.AlertState ?? string.Empty;

        string defaultStatus = hubIsPublicPilot
            ? "Pilot defaults are governed"
            : publicTargetCount > 0
                ? "Pilot defaults still need operator review"
                : "Pilot defaults are not yet governed";

        string canaryStatus = degradedServiceCount == 0
            && string.Equals(alertState, "healthy", StringComparison.OrdinalIgnoreCase)
            && publicTargetCount > 0
                ? "Canary green on all active lanes"
                : degradedServiceCount > 0
                    ? $"Canary watch on {degradedServiceCount} active lane(s)"
                    : "Canary evidence is still accumulating";

        return new ProviderRouteInfo(
            DefaultStatus: defaultStatus,
            CanaryStatus: canaryStatus,
            ReviewDue: seed?.SupportingSignals?.ProviderRouteStewardship?.ReviewDue,
            NextDecision: seed?.SupportingSignals?.ProviderRouteStewardship?.NextDecision
                ?? (degradedServiceCount == 0
                    ? "Promote once support fallout remains stable."
                    : "Hold broad promotion until route canaries return to green."));
    }

    private static string ComputeLaunchReadiness(
        JourneyGatesPayload? journeyGates,
        LocalReleaseProofPayload? localReleaseProof,
        ProviderRouteInfo providerRoute,
        ClosureHealthInfo? closureHealth,
        WeeklyProductPulseSeed? seed)
    {
        if (journeyGates is null && localReleaseProof is null && closureHealth is null)
        {
            return seed?.SupportingSignals?.LaunchReadiness
                ?? "Launch posture is still waiting on provider-route evidence.";
        }

        int blockedJourneyCount = journeyGates?.Summary?.BlockedCount ?? 0;
        if (blockedJourneyCount > 0)
        {
            return $"Hold launch expansion pending route-canary validation. {blockedJourneyCount} golden journey(s) remain blocked.";
        }

        if (!string.Equals(localReleaseProof?.Status, "passed", StringComparison.OrdinalIgnoreCase))
        {
            return "Hold launch expansion pending fresh local release proof on the public edge.";
        }

        if (closureHealth is not null
            && !string.Equals(closureHealth.State, "clear", StringComparison.Ordinal))
        {
            return "Hold launch expansion until support closure returns to a clear posture on the public edge.";
        }

        return string.Equals(providerRoute.CanaryStatus, "Canary green on all active lanes", StringComparison.Ordinal)
            ? "Route-canary validation is green; widen launch only while support fallout remains stable."
            : seed?.SupportingSignals?.LaunchReadiness
                ?? "Launch posture is still waiting on provider-route evidence.";
    }

    private static string SelectLatestGeneratedAt(params string?[] candidates)
    {
        DateTimeOffset latest = DateTimeOffset.MinValue;

        foreach (string? candidate in candidates)
        {
            if (DateTimeOffset.TryParse(candidate, out DateTimeOffset parsed) && parsed > latest)
            {
                latest = parsed;
            }
        }

        return latest == DateTimeOffset.MinValue
            ? DateTimeOffset.UtcNow.ToString("O")
            : latest.ToString("O");
    }

    private static JsonObject EnsureObject(JsonObject root, string propertyName)
    {
        if (root[propertyName] is JsonObject existing)
        {
            return existing;
        }

        var created = new JsonObject();
        root[propertyName] = created;
        return created;
    }

    private static string JsonStringOrFallback(JsonNode? node, string? fallback, string defaultValue)
        => node is JsonValue value && value.TryGetValue<string>(out string? parsed) && !string.IsNullOrWhiteSpace(parsed)
            ? parsed
            : !string.IsNullOrWhiteSpace(fallback)
                ? fallback
                : defaultValue;

    private sealed record WeeklyProductPulseSeed(
        [property: JsonPropertyName("generated_at")] string? GeneratedAt,
        [property: JsonPropertyName("active_wave")] string? ActiveWave,
        [property: JsonPropertyName("journey_gate_health")] WeeklyProductPulseHealthSeed? JourneyGateHealth,
        [property: JsonPropertyName("supporting_signals")] WeeklyProductPulseSupportingSignalsSeed? SupportingSignals);

    private sealed record WeeklyProductPulseHealthSeed(
        [property: JsonPropertyName("state")] string? State);

    private sealed record WeeklyProductPulseSupportingSignalsSeed(
        [property: JsonPropertyName("phase_label")] string? PhaseLabel,
        [property: JsonPropertyName("longest_pole")] string? LongestPole,
        [property: JsonPropertyName("launch_readiness")] string? LaunchReadiness,
        [property: JsonPropertyName("provider_route_stewardship")] WeeklyPulseProviderRouteSeed? ProviderRouteStewardship);

    private sealed record WeeklyPulseProviderRouteSeed(
        [property: JsonPropertyName("default_status")] string? DefaultStatus,
        [property: JsonPropertyName("canary_status")] string? CanaryStatus,
        [property: JsonPropertyName("review_due")] string? ReviewDue,
        [property: JsonPropertyName("next_decision")] string? NextDecision);

    private sealed record ProgressReportPayload(
        [property: JsonPropertyName("generated_at")] string? GeneratedAt,
        [property: JsonPropertyName("as_of")] string? AsOf,
        [property: JsonPropertyName("active_wave")] string? ActiveWave,
        [property: JsonPropertyName("active_wave_status")] string? ActiveWaveStatus,
        [property: JsonPropertyName("history_snapshot_count")] int? HistorySnapshotCount,
        [property: JsonPropertyName("overall_progress_percent")] int? OverallProgressPercent,
        [property: JsonPropertyName("phase_label")] string? PhaseLabel,
        [property: JsonPropertyName("longest_pole")] ProgressReportLongestPole? LongestPole);

    private sealed record ProgressReportLongestPole(
        [property: JsonPropertyName("label")] string? Label);

    private sealed record JourneyGatesPayload(
        [property: JsonPropertyName("generated_at")] string? GeneratedAt,
        [property: JsonPropertyName("summary")] JourneyGateSummary? Summary,
        [property: JsonPropertyName("journeys")] IReadOnlyList<JourneyGateJourney>? Journeys);

    private sealed record JourneyGateSummary(
        [property: JsonPropertyName("overall_state")] string? OverallState,
        [property: JsonPropertyName("blocked_count")] int? BlockedCount,
        [property: JsonPropertyName("warning_count")] int? WarningCount,
        [property: JsonPropertyName("recommended_action")] string? RecommendedAction);

    private sealed record JourneyGateJourney(
        [property: JsonPropertyName("signals")] JourneyGateSignals? Signals);

    private sealed record JourneyGateSignals(
        [property: JsonPropertyName("support_closure_waiting_count")] int? SupportClosureWaitingCount,
        [property: JsonPropertyName("support_needs_human_response_count")] int? SupportNeedsHumanResponseCount);

    private sealed record SupportPacketsPayload(
        [property: JsonPropertyName("generated_at")] string? GeneratedAt,
        [property: JsonPropertyName("source")] SupportPacketsSource? Source,
        [property: JsonPropertyName("summary")] SupportPacketsSummary? Summary);

    private sealed record SupportPacketsSource(
        [property: JsonPropertyName("materialized_count")] int? MaterializedCount,
        [property: JsonPropertyName("reported_count")] int? ReportedCount);

    private sealed record SupportPacketsSummary(
        [property: JsonPropertyName("design_impact_count")] int? DesignImpactCount,
        [property: JsonPropertyName("open_case_count")] int? OpenCaseCount);

    private sealed record LocalReleaseProofPayload(
        [property: JsonPropertyName("generated_at")] string? GeneratedAt,
        [property: JsonPropertyName("status")] string? Status);

    private sealed record StatusPlanePayload(
        string? GeneratedAt,
        StatusPlaneDeploymentPosture? DeploymentPosture,
        StatusPlaneRuntimeHealing? RuntimeHealing,
        IReadOnlyList<StatusPlaneProject>? Projects);

    private sealed record StatusPlaneDeploymentPosture(
        int? PublicTargetCount);

    private sealed record StatusPlaneRuntimeHealing(
        StatusPlaneRuntimeHealingSummary? Summary);

    private sealed record StatusPlaneRuntimeHealingSummary(
        int? DegradedServiceCount,
        string? AlertState);

    private sealed record StatusPlaneProject(
        string? Id,
        string? DeploymentPromotionStage,
        string? DeploymentAccessPosture);

    private sealed record ClosureHealthInfo(
        string State,
        int OpenCaseCount,
        int WaitingClosureCount,
        int PendingHumanResponseCount,
        int ReportedCaseCount,
        int MaterializedPacketCount,
        int DesignImpactCount,
        string Summary);

    private sealed record ProviderRouteInfo(
        string DefaultStatus,
        string CanaryStatus,
        string? ReviewDue,
        string? NextDecision);
}
