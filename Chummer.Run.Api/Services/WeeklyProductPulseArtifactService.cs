using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class WeeklyProductPulseArtifactService
{
    private const int MaxProgressTrendSamples = 8;
    private const int ProviderRouteReviewCadenceDays = 14;
    private const string DefaultPulseRelativePath = ".codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json";
    private const string DefaultProgressReportRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.json";
    private const string DefaultProgressHistoryRelativePath = ".codex-design/product/PROGRESS_HISTORY.generated.json";
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
            ProgressHistoryPayload? progressHistory = LoadOptionalJson<ProgressHistoryPayload>(ResolveOptionalCanonPath(DefaultProgressHistoryRelativePath));
            JourneyGatesPayload? journeyGates = LoadOptionalJson<JourneyGatesPayload>(ResolveOptionalFleetArtifactPath(JourneyGatesFileName));
            SupportPacketsPayload? supportPackets = LoadOptionalJson<SupportPacketsPayload>(ResolveOptionalFleetArtifactPath(SupportPacketsFileName));
            StatusPlanePayload? statusPlane = LoadOptionalYaml<StatusPlanePayload>(ResolveOptionalFleetArtifactPath(StatusPlaneFileName));
            LocalReleaseProofPayload? localReleaseProof = LoadOptionalJson<LocalReleaseProofPayload>(ResolveOptionalCanonPath(DefaultLocalReleaseProofRelativePath));

            ClosureHealthInfo? closureHealth = ComputeClosureHealth(journeyGates, supportPackets);
            AdoptionHealthInfo? adoptionHealth = ComputeAdoptionHealth(progressReport, localReleaseProof);
            WeeklyProgressTrendInfo? progressTrend = ComputeProgressTrend(progressHistory);
            ProviderRouteInfo providerRoute = ComputeProviderRoute(statusPlane, closureHealth, localReleaseProof, seed);
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

            if (adoptionHealth is not null)
            {
                supportingSignals["adoption_health"] = new JsonObject
                {
                    ["state"] = adoptionHealth.State,
                    ["local_release_proof_status"] = adoptionHealth.LocalReleaseProofStatus,
                    ["proven_journey_count"] = adoptionHealth.ProvenJourneyCount,
                    ["proven_route_count"] = adoptionHealth.ProvenRouteCount,
                    ["history_snapshot_count"] = adoptionHealth.HistorySnapshotCount,
                    ["summary"] = adoptionHealth.Summary
                };
            }

            if (progressTrend is not null)
            {
                supportingSignals["progress_trend"] = new JsonObject
                {
                    ["state"] = progressTrend.State,
                    ["direction"] = progressTrend.Direction,
                    ["delta_percent"] = progressTrend.DeltaPercent,
                    ["from_as_of"] = progressTrend.FromAsOf,
                    ["to_as_of"] = progressTrend.ToAsOf,
                    ["sample_count"] = progressTrend.Samples.Count,
                    ["summary"] = progressTrend.Summary,
                    ["samples"] = new JsonArray(progressTrend.Samples.Select(static sample => (JsonNode)new JsonObject
                    {
                        ["as_of"] = sample.AsOf,
                        ["overall_progress_percent"] = sample.OverallProgressPercent
                    }).ToArray())
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

    private static AdoptionHealthInfo? ComputeAdoptionHealth(
        ProgressReportPayload? progressReport,
        LocalReleaseProofPayload? localReleaseProof)
    {
        int historySnapshotCount = progressReport?.HistorySnapshotCount ?? 0;
        int provenJourneyCount = localReleaseProof?.JourneysPassed?.Count ?? 0;
        int provenRouteCount = localReleaseProof?.ProofRoutes?.Count ?? 0;
        string localReleaseProofStatus = localReleaseProof?.Status ?? "unknown";

        if (historySnapshotCount == 0
            && provenJourneyCount == 0
            && provenRouteCount == 0
            && string.Equals(localReleaseProofStatus, "unknown", StringComparison.Ordinal))
        {
            return null;
        }

        string state = string.Equals(localReleaseProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
                       && provenJourneyCount > 0
                       && provenRouteCount > 0
            ? "clear"
            : historySnapshotCount > 0
                ? "early"
                : "partial";

        string proofSegment = string.Equals(localReleaseProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
            ? "Current local edge proof passed."
            : $"Current local edge proof is {localReleaseProofStatus}.";
        string journeysSegment = provenJourneyCount > 0 && provenRouteCount > 0
            ? $"{provenJourneyCount} journey proofs and {provenRouteCount} trust routes are on record."
            : provenJourneyCount > 0
                ? $"{provenJourneyCount} journey proofs are on record."
                : provenRouteCount > 0
                    ? $"{provenRouteCount} trust routes are on record."
                    : "Journey-proof evidence is still accumulating.";
        string historySegment = historySnapshotCount > 0
            ? historySnapshotCount < 6
                ? $"{historySnapshotCount} weekly snapshots are measured so far, so adoption history is still early."
                : $"{historySnapshotCount} weekly snapshots are on record for the current public trust posture."
            : "Weekly adoption history is not materialized yet.";

        return new AdoptionHealthInfo(
            State: state,
            LocalReleaseProofStatus: localReleaseProofStatus,
            ProvenJourneyCount: provenJourneyCount,
            ProvenRouteCount: provenRouteCount,
            HistorySnapshotCount: historySnapshotCount,
            Summary: $"{proofSegment} {journeysSegment} {historySegment}");
    }

    private static WeeklyProgressTrendInfo? ComputeProgressTrend(ProgressHistoryPayload? progressHistory)
    {
        if (progressHistory?.Snapshots is null)
        {
            return null;
        }

        List<ProgressTrendSample> samples = progressHistory.Snapshots
            .Where(static snapshot => !string.IsNullOrWhiteSpace(snapshot.AsOf) && snapshot.OverallProgressPercent.HasValue)
            .Select(static snapshot => new ProgressTrendSample(snapshot.AsOf!, snapshot.OverallProgressPercent!.Value))
            .OrderBy(static snapshot => snapshot.AsOf)
            .ToList();

        if (samples.Count == 0)
        {
            return null;
        }

        if (samples.Count > MaxProgressTrendSamples)
        {
            samples = samples.Skip(samples.Count - MaxProgressTrendSamples).ToList();
        }

        if (samples.Count < 2)
        {
            return new WeeklyProgressTrendInfo(
                State: "early",
                Direction: "flat",
                DeltaPercent: 0,
                FromAsOf: samples[0].AsOf,
                ToAsOf: samples[0].AsOf,
                Summary: "Progress trend is awaiting measured history; two weekly points are required.",
                Samples: samples);
        }

        ProgressTrendSample previous = samples[^2];
        ProgressTrendSample latest = samples[^1];
        int delta = latest.OverallProgressPercent - previous.OverallProgressPercent;
        string direction = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
        string directionLabel = direction switch
        {
            "up" => "Upward momentum",
            "down" => "Regression",
            _ => "Flat trend"
        };
        string deltaText = direction switch
        {
            "up" => $"+{Math.Abs(delta)}%",
            "down" => $"-{Math.Abs(delta)}%",
            _ => $"{Math.Abs(delta)}%"
        };
        string trendWindow = string.Join(" -> ", samples.Select(static sample => $"{sample.AsOf} {sample.OverallProgressPercent}%"));

        return new WeeklyProgressTrendInfo(
            State: Math.Abs(delta) == 0 ? "steady" : "moving",
            Direction: direction,
            DeltaPercent: Math.Abs(delta),
            FromAsOf: previous.AsOf,
            ToAsOf: latest.AsOf,
            Summary: $"{directionLabel} {deltaText} from {previous.AsOf} to {latest.AsOf}. Trend window: {trendWindow}.",
            Samples: samples);
    }

    private static ProviderRouteInfo ComputeProviderRoute(
        StatusPlanePayload? statusPlane,
        ClosureHealthInfo? closureHealth,
        LocalReleaseProofPayload? localReleaseProof,
        WeeklyProductPulseSeed? seed)
    {
        if (statusPlane is null)
        {
            string fallbackDefaultStatus = seed?.SupportingSignals?.ProviderRouteStewardship?.DefaultStatus ?? "Pilot defaults are not yet governed";
            string fallbackCanaryStatus = seed?.SupportingSignals?.ProviderRouteStewardship?.CanaryStatus ?? "Canary evidence is still accumulating";
            bool fallbackCanaryHealthy = string.Equals(fallbackCanaryStatus, "Canary green on all active lanes", StringComparison.Ordinal);
            bool fallbackHubIsPublicPilot = string.Equals(fallbackDefaultStatus, "Pilot defaults are governed", StringComparison.Ordinal);
            string fallbackNextDecision = localReleaseProof is null && closureHealth is null
                ? seed?.SupportingSignals?.ProviderRouteStewardship?.NextDecision
                    ?? ComputeProviderRouteDecision(
                        fallbackHubIsPublicPilot,
                        fallbackCanaryHealthy ? 1 : 0,
                        fallbackCanaryHealthy,
                        closureHealth,
                        localReleaseProof)
                : ComputeProviderRouteDecision(
                    fallbackHubIsPublicPilot,
                    fallbackCanaryHealthy ? 1 : 0,
                    fallbackCanaryHealthy,
                    closureHealth,
                    localReleaseProof);
            return new ProviderRouteInfo(
                DefaultStatus: fallbackDefaultStatus,
                CanaryStatus: fallbackCanaryStatus,
                ReviewDue: ComputeProviderRouteReviewDue(seed?.GeneratedAt, seed?.SupportingSignals?.ProviderRouteStewardship?.ReviewDue),
                NextDecision: fallbackNextDecision);
        }

        StatusPlanePayload liveStatusPlane = statusPlane;

        bool hubIsPublicPilot = liveStatusPlane.Projects?.Any(static project =>
            string.Equals(project.Id, "hub", StringComparison.OrdinalIgnoreCase)
            && string.Equals(project.DeploymentAccessPosture, "public", StringComparison.OrdinalIgnoreCase)
            && string.Equals(project.DeploymentPromotionStage, "promoted_preview", StringComparison.OrdinalIgnoreCase)) == true;

        int publicTargetCount = liveStatusPlane.DeploymentPosture?.PublicTargetCount ?? 0;
        int degradedServiceCount = liveStatusPlane.RuntimeHealing?.Summary?.DegradedServiceCount ?? 0;
        string alertState = liveStatusPlane.RuntimeHealing?.Summary?.AlertState ?? string.Empty;
        bool canaryHealthy = degradedServiceCount == 0
            && string.Equals(alertState, "healthy", StringComparison.OrdinalIgnoreCase)
            && publicTargetCount > 0;

        string defaultStatus = hubIsPublicPilot
            ? "Pilot defaults are governed"
            : publicTargetCount > 0
                ? "Pilot defaults still need operator review"
                : "Pilot defaults are not yet governed";

        string canaryStatus = canaryHealthy
                ? "Canary green on all active lanes"
                : degradedServiceCount > 0
                    ? $"Canary watch on {degradedServiceCount} active lane(s)"
                    : "Canary evidence is still accumulating";
        string? reviewEvidenceGeneratedAt = !string.IsNullOrWhiteSpace(liveStatusPlane.GeneratedAt)
            ? liveStatusPlane.GeneratedAt
            : seed?.GeneratedAt;

        return new ProviderRouteInfo(
            DefaultStatus: defaultStatus,
            CanaryStatus: canaryStatus,
            ReviewDue: ComputeProviderRouteReviewDue(reviewEvidenceGeneratedAt, seed?.SupportingSignals?.ProviderRouteStewardship?.ReviewDue),
            NextDecision: ComputeProviderRouteDecision(
                hubIsPublicPilot,
                publicTargetCount,
                canaryHealthy,
                closureHealth,
                localReleaseProof));
    }

    private static string? ComputeProviderRouteReviewDue(string? generatedAt, string? seedReviewDue)
    {
        if (DateTimeOffset.TryParse(generatedAt, out DateTimeOffset parsed))
        {
            return parsed.ToUniversalTime().AddDays(ProviderRouteReviewCadenceDays).ToString("yyyy-MM-dd");
        }

        return seedReviewDue;
    }

    private static string ComputeProviderRouteDecision(
        bool hubIsPublicPilot,
        int publicTargetCount,
        bool canaryHealthy,
        ClosureHealthInfo? closureHealth,
        LocalReleaseProofPayload? localReleaseProof)
    {
        if (publicTargetCount == 0)
        {
            return "Hold broad promotion until public route canary coverage exists.";
        }

        if (!canaryHealthy)
        {
            return "Hold broad promotion until route canaries return to green.";
        }

        if (!string.Equals(localReleaseProof?.Status, "passed", StringComparison.OrdinalIgnoreCase))
        {
            return "Hold broad promotion until fresh local release proof passes on the public edge.";
        }

        if (closureHealth is not null
            && !string.Equals(closureHealth.State, "clear", StringComparison.Ordinal))
        {
            return "Keep the current pilot default until support closure returns to a clear posture.";
        }

        if (!hubIsPublicPilot)
        {
            return "Finish the public pilot promotion path before making this the default route.";
        }

        return "Promote once canaries stay green and support fallout remains clear through the next route review.";
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

    private sealed record ProgressHistoryPayload(
        [property: JsonPropertyName("snapshot_count")] int? SnapshotCount,
        [property: JsonPropertyName("snapshots")] IReadOnlyList<ProgressHistorySnapshot>? Snapshots);

    private sealed record ProgressHistorySnapshot(
        [property: JsonPropertyName("as_of")] string? AsOf,
        [property: JsonPropertyName("overall_progress_percent")] int? OverallProgressPercent);

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
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("journeys_passed")] IReadOnlyList<string>? JourneysPassed,
        [property: JsonPropertyName("proof_routes")] IReadOnlyList<string>? ProofRoutes);

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

    private sealed record AdoptionHealthInfo(
        string State,
        string LocalReleaseProofStatus,
        int ProvenJourneyCount,
        int ProvenRouteCount,
        int HistorySnapshotCount,
        string Summary);

    private sealed record ProviderRouteInfo(
        string DefaultStatus,
        string CanaryStatus,
        string? ReviewDue,
        string? NextDecision);

    private sealed record WeeklyProgressTrendInfo(
        string State,
        string Direction,
        int DeltaPercent,
        string FromAsOf,
        string ToAsOf,
        string Summary,
        IReadOnlyList<ProgressTrendSample> Samples);

    private sealed record ProgressTrendSample(
        string AsOf,
        int OverallProgressPercent);
}
