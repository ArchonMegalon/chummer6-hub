using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignWorkspaceServerPlaneService
{
    private sealed record WorkspaceContext(
        CampaignWorkspaceProjection Workspace,
        CampaignWorkspaceDigestProjection? Digest,
        WorkspaceRestoreProjection Restore,
        IReadOnlyList<CreatorPublicationProjection> CreatorPublications,
        RunProjection? LeadRun,
        IReadOnlyList<SupportCaseDigestViewModel> SupportDigests,
        DateTimeOffset GeneratedAtUtc);

    private static readonly char[] SearchSeparators =
    [
        ' ',
        ',',
        '.',
        ';',
        ':',
        '/',
        '\\',
        '(',
        ')',
        '[',
        ']',
        '{',
        '}',
        '-',
        '_',
        '\r',
        '\n',
        '\t'
    ];

    private readonly CampaignSpineService _campaignSpine;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;

    public CampaignWorkspaceServerPlaneService(
        CampaignSpineService campaignSpine,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation)
    {
        _campaignSpine = campaignSpine;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
    }

    public CampaignWorkspaceServerPlaneProjection? GetWorkspaceServerPlane(
        HubUserDto user,
        string workspaceId,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);

        WorkspaceContext? context = ResolveWorkspaceContext(user, workspaceId, installLinking);
        if (context is null)
        {
            return null;
        }

        CampaignPrepLibrarySummary prepLibrary = BuildPrepLibrary(context.Workspace, context.Restore, context.LeadRun);
        TravelModeReadinessSummary travelMode = BuildTravelMode(context.Workspace, context.Restore, prepLibrary);
        IReadOnlyList<DossierFreshnessCue> dossierFreshness = BuildDossierFreshness(context.Workspace);
        IReadOnlyList<RuleEnvironmentHealthCue> ruleEnvironmentHealth = BuildRuleEnvironmentHealth(context.Workspace, context.Restore);
        IReadOnlyList<ContinuityConflictCue> continuityConflicts = BuildContinuityConflicts(context.Workspace, context.Restore);
        IReadOnlyList<SupportClosureCue> supportClosures = BuildSupportClosures(context.SupportDigests);
        IReadOnlyList<KnownIssueAffectingInstall> knownIssues = BuildKnownIssues(context.SupportDigests);
        IReadOnlyList<DecisionNotice> decisionNotices = BuildDecisionNotices(context.Workspace, context.Digest, installLinking, context.SupportDigests, prepLibrary, context.LeadRun);
        NextSafeActionCue nextSafeAction = BuildNextSafeActionCue(context.Workspace, installLinking, context.SupportDigests);
        WorkspaceStateSummary workspaceState = BuildWorkspaceStateSummary(
            context.Workspace,
            installLinking,
            ruleEnvironmentHealth,
            continuityConflicts,
            context.SupportDigests,
            travelMode,
            nextSafeAction);

        return new CampaignWorkspaceServerPlaneProjection(
            Workspace: BuildWorkspaceSummary(context.Workspace, context.Digest, context.Restore),
            CampaignSummary: BuildCampaignWorkspaceSummary(context.Workspace, context.Digest, context.Restore),
            WorkspaceState: workspaceState,
            RosterReadiness: BuildRosterReadinessSummary(context.Workspace),
            ReadinessCues: context.Workspace.ReadinessCues,
            ChangePackets: context.Workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>(),
            Consequences: context.Workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>(),
            RosterTransfers: context.Workspace.RosterTransfers ?? Array.Empty<RosterTransferProjection>(),
            DossierFreshness: dossierFreshness,
            RuleEnvironmentHealth: ruleEnvironmentHealth,
            Runboard: BuildRunboardSummary(context.Workspace, context.LeadRun),
            ContinuityConflicts: continuityConflicts,
            RecapShelf: BuildRecapShelf(context.Workspace, context.CreatorPublications),
            SupportClosures: supportClosures,
            KnownIssues: knownIssues,
            DecisionNotices: decisionNotices,
            PrepLibrary: prepLibrary,
            PrepLaunches: context.Workspace.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>(),
            TravelMode: travelMode,
            TravelPrefetches: context.Workspace.TravelPrefetches ?? Array.Empty<TravelPrefetchReceiptProjection>(),
            AftermathPackages: context.Workspace.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>(),
            FirstPlayableSession: context.Workspace.FirstPlayableSession,
            CampaignMemory: context.Workspace.CampaignMemory,
            NextSessionCarryForward: context.Workspace.NextSessionCarryForward,
            NextSafeAction: nextSafeAction,
            GeneratedAtUtc: context.GeneratedAtUtc);
    }

    public CampaignPrepLibrarySearchResponse? GetWorkspacePrepLibrary(
        HubUserDto user,
        string workspaceId,
        InstallLinkingSummaryDto? installLinking = null,
        string? queryText = null)
    {
        ArgumentNullException.ThrowIfNull(user);

        WorkspaceContext? context = ResolveWorkspaceContext(user, workspaceId, installLinking);
        if (context is null)
        {
            return null;
        }

        CampaignPrepLibrarySummary prepLibrary = BuildPrepLibrary(context.Workspace, context.Restore, context.LeadRun);
        string? normalizedQuery = NormalizeOptional(queryText);
        IReadOnlyList<string> queryTokens = BuildPrepLibraryQueryTokens(normalizedQuery);
        IReadOnlyList<GovernedPrepPacketSummary> packets = prepLibrary.Packets
            .Where(packet => MatchesPrepLibraryQuery(packet, queryTokens))
            .ToArray();

        return new CampaignPrepLibrarySearchResponse(
            WorkspaceId: context.Workspace.WorkspaceId,
            CampaignId: context.Workspace.CampaignId,
            QueryText: normalizedQuery,
            Items: packets,
            TotalCount: packets.Count);
    }

    public GovernedPrepLaunchProjection? LaunchWorkspacePrepPacket(
        HubUserDto user,
        string workspaceId,
        GovernedPrepLaunchRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(request);

        WorkspaceContext? context = ResolveWorkspaceContext(user, workspaceId, installLinking);
        if (context is null)
        {
            return null;
        }

        CampaignPrepLibrarySummary prepLibrary = BuildPrepLibrary(context.Workspace, context.Restore, context.LeadRun);
        GovernedPrepPacketSummary packet = prepLibrary.Packets
            .FirstOrDefault(item => string.Equals(item.PacketId, request.PacketId, StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown governed prep packet: {request.PacketId}");

        RunProjection? targetRun = ResolvePrepLaunchRun(context.Workspace, context.LeadRun, request.TargetRunId);
        SceneProjection? targetScene = ResolvePrepLaunchScene(targetRun, request.TargetSceneId);
        return _campaignSpine.RecordPrepLaunch(
            user,
            context.Workspace,
            packet.PacketId,
            packet.Kind,
            packet.Title,
            packet.Summary,
            targetRun,
            targetScene,
            request.Note);
    }

    public TravelPrefetchReceiptProjection? StageTravelPrefetch(
        HubUserDto user,
        string workspaceId,
        TravelPrefetchStageRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(request);

        WorkspaceContext? context = ResolveWorkspaceContext(user, workspaceId, installLinking);
        if (context is null)
        {
            return null;
        }

        ClaimedDeviceRestoreProjection device = context.Restore.ClaimedDevices
            .FirstOrDefault(item => string.Equals(item.InstallationId, request.InstallationId, StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown claimed device: {request.InstallationId}");
        CampaignPrepLibrarySummary prepLibrary = BuildPrepLibrary(context.Workspace, context.Restore, context.LeadRun);
        IReadOnlyList<string> inventoryLines = BuildTravelPrefetchInventoryLines(context.Workspace, context.Restore, prepLibrary, device);
        string prefetchSummary = BuildTravelPrefetchSummary(context.Workspace, device, prepLibrary);
        return _campaignSpine.RecordTravelPrefetch(
            user,
            context.Workspace,
            device,
            prefetchSummary,
            inventoryLines,
            context.Restore.LocalOnlyNotes.Concat(
            [
                "Install-local caches, secrets, and runtime state stay local even when travel packets are staged for bounded offline use."
            ]).ToArray(),
            request.Note);
    }

    public AftermathRecapPackageProjection? GenerateAftermathRecapPackage(
        HubUserDto user,
        string workspaceId,
        AftermathRecapPackageRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(request);

        WorkspaceContext? context = ResolveWorkspaceContext(user, workspaceId, installLinking);
        if (context is null)
        {
            return null;
        }

        RunProjection? targetRun = ResolvePrepLaunchRun(context.Workspace, context.LeadRun, request.RunId);
        string packageKind = NormalizeAftermathPackageKind(request.PackageKind);
        string title = BuildAftermathPackageTitle(context.Workspace, targetRun, packageKind, request.Title);
        string summary = BuildAftermathPackageSummary(context.Workspace, targetRun, packageKind);
        IReadOnlyList<string> evidenceLines = BuildAftermathPackageEvidenceLines(context.Workspace, context.Restore, targetRun, packageKind, request.Note);
        return _campaignSpine.RecordAftermathRecapPackage(
            user,
            context.Workspace,
            targetRun,
            packageKind,
            title,
            summary,
            evidenceLines);
    }

    private WorkspaceContext? ResolveWorkspaceContext(
        HubUserDto user,
        string workspaceId,
        InstallLinkingSummaryDto? installLinking)
    {
        if (string.IsNullOrWhiteSpace(workspaceId))
        {
            return null;
        }

        AccountCampaignSummary accountSummary = _campaignSpine.GetAccountSummary(user, installLinking);
        CampaignWorkspaceProjection? workspace = accountSummary.Workspaces
            .FirstOrDefault(item => string.Equals(item.WorkspaceId, workspaceId.Trim(), StringComparison.OrdinalIgnoreCase));
        if (workspace is null)
        {
            return null;
        }

        IReadOnlyList<CreatorPublicationProjection> creatorPublications = accountSummary.CreatorPublications
            .Where(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase)
                || (!string.IsNullOrWhiteSpace(item.ArtifactId)
                    && workspace.RecapShelf.Any(recap => string.Equals(recap.ArtifactId, item.ArtifactId, StringComparison.OrdinalIgnoreCase)))
                || (!string.IsNullOrWhiteSpace(item.PublicationId)
                    && workspace.RecapShelf.Any(recap => string.Equals(recap.CreatorPublicationId, item.PublicationId, StringComparison.OrdinalIgnoreCase))))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();

        CampaignWorkspaceDigestProjection? digest = _campaignSpine.GetWorkspaceDigests(user, installLinking)
            .FirstOrDefault(item => string.Equals(item.WorkspaceId, workspace.WorkspaceId, StringComparison.OrdinalIgnoreCase));
        RunProjection? leadRun = workspace.Runs
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        IReadOnlyList<SupportCaseProjection> relevantCases = SelectRelevantSupportCases(
            _supportCases.ListForReporter(user.UserId, user.SubjectId).Items,
            installLinking);
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests = _supportPresentation.BuildDigestList(relevantCases, installLinking);

        DateTimeOffset generatedAtUtc = new[]
            {
                digest?.UpdatedAtUtc,
                accountSummary.Restore.GeneratedAtUtc,
                workspace.LatestContinuity?.CapturedAtUtc,
                workspace.RosterTransfers?.FirstOrDefault()?.TransferredAtUtc,
                workspace.PrepLaunches?.FirstOrDefault()?.LaunchedAtUtc,
                workspace.TravelPrefetches?.FirstOrDefault()?.StagedAtUtc,
                workspace.AftermathPackages?.FirstOrDefault()?.GeneratedAtUtc,
                workspace.NextSessionCarryForward?.UpdatedAtUtc,
                creatorPublications.FirstOrDefault()?.UpdatedAtUtc,
                leadRun?.UpdatedAtUtc
            }
            .Concat(relevantCases.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new WorkspaceContext(
            Workspace: workspace,
            Digest: digest,
            Restore: accountSummary.Restore,
            CreatorPublications: creatorPublications,
            LeadRun: leadRun,
            SupportDigests: supportDigests,
            GeneratedAtUtc: generatedAtUtc);
    }

    private static WorkspaceSummary BuildWorkspaceSummary(
        CampaignWorkspaceProjection workspace,
        CampaignWorkspaceDigestProjection? digest,
        WorkspaceRestoreProjection restore)
        => new(
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            CampaignName: workspace.CampaignName,
            Visibility: workspace.Visibility,
            ReturnSummary: workspace.ReturnSummary,
            DeviceRoleSummary: digest?.DeviceRoleSummary
                ?? DescribeDeviceRoleSummary(restore),
            SupportClosureSummary: digest?.SupportClosureSummary
                ?? "Support closure stays anchored to the linked install and release lane that reopen this shared campaign view.",
            ActiveSceneSummary: workspace.ActiveSceneSummary,
            UpdatedAtUtc: digest?.UpdatedAtUtc
                ?? workspace.LatestContinuity?.CapturedAtUtc
                ?? restore.GeneratedAtUtc);

    private static CampaignWorkspaceSummary BuildCampaignWorkspaceSummary(
        CampaignWorkspaceProjection workspace,
        CampaignWorkspaceDigestProjection? digest,
        WorkspaceRestoreProjection restore)
    {
        CampaignReadinessCue? attentionCue = workspace.ReadinessCues.FirstOrDefault(static cue => NeedsAttention(cue.Severity));
        string restorePrefetchSummary = DescribeRestorePrefetchSummary(restore);
        string restoreSummary = restore.ConflictSummaries.FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item)) is { } conflictSummary
            ? $"{conflictSummary} {restorePrefetchSummary}"
            : restore.LocalOnlyNotes.FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item)) is { } localOnlySummary
                ? $"{restorePrefetchSummary} {localOnlySummary}"
                : $"{restorePrefetchSummary} Restore posture is attached to claimed installs and continuity snapshots instead of a local-only guess.";
        string publicationSummary = workspace.RecapShelf.Count == 0
            ? "No recap-safe output is pinned yet, so the workspace still needs its first publication-safe continuity handoff."
            : $"{workspace.RecapShelf.Count} publication-safe output(s) are attached to the same campaign continuity spine.";
        if (workspace.Consequences is { Count: > 0 })
        {
            publicationSummary = $"{publicationSummary} {workspace.Consequences.Count} governed consequence signal(s) stay attached to the same workspace.";
        }
        if (workspace.RosterTransfers is { Count: > 0 })
        {
            publicationSummary = $"{publicationSummary} {workspace.RosterTransfers.Count} roster-transfer receipt(s) keep source, target, and ownership changes reviewable from the same workspace.";
        }

        return new CampaignWorkspaceSummary(
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            CampaignName: workspace.CampaignName,
            RuleEnvironmentSummary: digest?.RuleEnvironmentSummary
                ?? $"{workspace.RuleEnvironment.OwnerScope} · {DescribeRuleEnvironmentLifecycleStage(workspace.RuleEnvironment)} · {workspace.RuleEnvironment.CompatibilityFingerprint}",
            SessionReadinessSummary: attentionCue is null
                ? workspace.FirstPlayableSession?.Summary
                  ?? "Session return is green across the current roster, active scene, and claimed-install restore posture."
                : $"{attentionCue.Title}: {attentionCue.Summary}",
            RestoreSummary: restoreSummary,
            PublicationSummary: publicationSummary,
            NextSafeAction: workspace.NextSafeAction ?? "Open the shared campaign view from the latest continuity snapshot before you fork any local-only state.",
            UpdatedAtUtc: digest?.UpdatedAtUtc
                ?? workspace.LatestContinuity?.CapturedAtUtc
                ?? restore.GeneratedAtUtc);
    }

    private static WorkspaceStateSummary BuildWorkspaceStateSummary(
        CampaignWorkspaceProjection workspace,
        InstallLinkingSummaryDto? installLinking,
        IReadOnlyList<RuleEnvironmentHealthCue> ruleEnvironmentHealth,
        IReadOnlyList<ContinuityConflictCue> continuityConflicts,
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests,
        TravelModeReadinessSummary travelMode,
        NextSafeActionCue nextSafeAction)
    {
        ContinuityConflictCue? blockingConflict = continuityConflicts.FirstOrDefault(static cue => NeedsAttention(cue.Severity));
        if (blockingConflict is not null)
        {
            return new WorkspaceStateSummary(
                Status: "restore_conflict_present",
                Label: "Restore review before play",
                Summary: $"{blockingConflict.Summary} {nextSafeAction.Summary}",
                EvidenceLines: BuildEvidenceLines(
                    blockingConflict.Summary,
                    blockingConflict.ResolutionAction,
                    travelMode.Summary,
                    travelMode.PrefetchInventorySummary));
        }

        if (string.Equals(nextSafeAction.SourceKind, "install_linking", StringComparison.OrdinalIgnoreCase))
        {
            return new WorkspaceStateSummary(
                Status: "blocked_before_play",
                Label: "Finish install claim first",
                Summary: $"{nextSafeAction.Summary} {travelMode.Summary}",
                EvidenceLines: BuildEvidenceLines(
                    nextSafeAction.Summary,
                    travelMode.Summary,
                    travelMode.PrefetchInventorySummary));
        }

        RuleEnvironmentHealthCue? ruleAttention = ruleEnvironmentHealth.FirstOrDefault(static cue => NeedsAttention(cue.Severity));
        if (ruleAttention is not null)
        {
            return new WorkspaceStateSummary(
                Status: "rule_environment_mismatch",
                Label: "Rules need review",
                Summary: $"{ruleAttention.Summary} {nextSafeAction.Summary}",
                EvidenceLines: BuildEvidenceLines(
                    ruleAttention.Title,
                    ruleAttention.Summary,
                    nextSafeAction.Summary));
        }

        SupportCaseDigestViewModel? supportAction = supportDigests.FirstOrDefault(static item => item.ReporterActionNeeded)
            ?? supportDigests.FirstOrDefault(static item => item.CanVerifyFix);
        if (supportAction is not null)
        {
            return new WorkspaceStateSummary(
                Status: "support_closure_pending",
                Label: "Support closure pending",
                Summary: $"{supportAction.ClosureSummary} {supportAction.NextSafeAction}",
                EvidenceLines: BuildEvidenceLines(
                    supportAction.ReleaseProgressSummary,
                    supportAction.ClosureSummary,
                    supportAction.AffectedInstallSummary,
                    supportAction.NextSafeAction));
        }

        ClaimedInstallationDto[] claimedInstallations = installLinking?.ClaimedInstallations?.ToArray() ?? Array.Empty<ClaimedInstallationDto>();
        if (claimedInstallations.Any(static item => string.Equals(item.Channel, "preview", StringComparison.OrdinalIgnoreCase))
            && claimedInstallations.Any(static item => !string.Equals(item.Channel, "preview", StringComparison.OrdinalIgnoreCase)))
        {
            return new WorkspaceStateSummary(
                Status: "preview_diverged",
                Label: "Preview differs across devices",
                Summary: "Claimed devices do not currently share one channel posture, so preview fixes and install trust can diverge by machine.",
                EvidenceLines: BuildEvidenceLines(
                    claimedInstallations
                        .Select(static item => $"{ResolveDeviceRole(item)} on {item.Platform}/{item.HeadId} stays on {item.Channel}."),
                    nextSafeAction.Summary));
        }

        CampaignReadinessCue? readinessAttention = workspace.ReadinessCues.FirstOrDefault(static cue => NeedsAttention(cue.Severity));
        if (readinessAttention is not null)
        {
            return new WorkspaceStateSummary(
                Status: "attention_needed",
                Label: "Attention needed",
                Summary: $"{readinessAttention.Summary} {nextSafeAction.Summary}",
                EvidenceLines: BuildEvidenceLines(
                    readinessAttention.Title,
                    readinessAttention.Summary,
                    travelMode.Summary,
                    nextSafeAction.Summary));
        }

        if (travelMode.TravelReadyDeviceCount > 0 && travelMode.TravelReadyDeviceCount < travelMode.ClaimedDeviceCount)
        {
            return new WorkspaceStateSummary(
                Status: "offline_but_usable",
                Label: "Offline-safe on some devices",
                Summary: $"{travelMode.Summary} {nextSafeAction.Summary}",
                EvidenceLines: BuildEvidenceLines(
                    travelMode.Summary,
                    travelMode.PrefetchInventorySummary,
                    nextSafeAction.Summary));
        }

        if (workspace.FirstPlayableSession is not null)
        {
            return new WorkspaceStateSummary(
                Status: "first_playable_ready",
                Label: "First playable session ready",
                Summary: $"{workspace.FirstPlayableSession.Summary} {nextSafeAction.Summary}",
                EvidenceLines: BuildEvidenceLines(
                    workspace.FirstPlayableSession.EvidenceLines,
                    travelMode.Summary,
                    nextSafeAction.Summary));
        }

        return new WorkspaceStateSummary(
            Status: "healthy",
            Label: "Ready to continue",
            Summary: $"{workspace.CampaignName} can reopen from the shared return lane without a blocking restore, rules, or support conflict right now.",
            EvidenceLines: BuildEvidenceLines(
                workspace.ReturnSummary,
                travelMode.Summary,
                nextSafeAction.Summary));
    }

    private static RosterReadinessSummary BuildRosterReadinessSummary(CampaignWorkspaceProjection workspace)
    {
        int needsAttentionCount = workspace.Dossiers.Count(static dossier => dossier.LatestContinuity is null)
            + workspace.ReadinessCues.Count(static cue => NeedsAttention(cue.Severity));
        int readyCount = Math.Max(0, workspace.Dossiers.Count - workspace.Dossiers.Count(static dossier => dossier.LatestContinuity is null));
        string summary = needsAttentionCount > 0
            ? $"{needsAttentionCount} readiness item(s) still need attention across {workspace.Dossiers.Count} dossier(s), {workspace.Crews.Count} crew(s), and {workspace.Runs.Count} run(s)."
            : $"{workspace.Dossiers.Count} dossier(s), {workspace.Crews.Count} crew(s), and {workspace.Runs.Count} run(s) are ready to reopen from the same continuity spine.";
        IReadOnlyList<string> highlights = workspace.ReadinessCues
            .Take(4)
            .Select(static cue => $"{cue.Title} — {cue.Summary}")
            .Concat(
                workspace.Consequences?
                    .Take(2)
                    .Select(static consequence => $"{consequence.Label} — {consequence.Summary}")
                ?? Array.Empty<string>())
            .Concat(
                workspace.RosterTransfers?
                    .Take(2)
                    .Select(static transfer => $"Roster transfer — {transfer.Summary}")
                ?? Array.Empty<string>())
            .Take(4)
            .ToArray();

        return new RosterReadinessSummary(
            Summary: summary,
            ReadyDossierCount: readyCount,
            NeedsAttentionCount: needsAttentionCount,
            CrewCount: workspace.Crews.Count,
            RunCount: workspace.Runs.Count,
            Highlights: highlights);
    }

    private static IReadOnlyList<DossierFreshnessCue> BuildDossierFreshness(CampaignWorkspaceProjection workspace)
        => workspace.Dossiers
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Take(6)
            .Select(dossier =>
            {
                bool missingContinuity = dossier.LatestContinuity is null;
                bool ruleMismatch = !string.Equals(
                    dossier.RuleEnvironment.CompatibilityFingerprint,
                    workspace.RuleEnvironment.CompatibilityFingerprint,
                    StringComparison.OrdinalIgnoreCase);
                string status = missingContinuity
                    ? "stale"
                    : ruleMismatch
                        ? "review"
                        : "fresh";
                string severity = missingContinuity
                    ? "warning"
                    : ruleMismatch
                        ? "review"
                        : "ready";
                string summary = missingContinuity
                    ? $"{dossier.DisplayName} is missing the latest continuity snapshot for safe shared-campaign return."
                    : ruleMismatch
                        ? $"{dossier.DisplayName} is pinned to {dossier.RuleEnvironment.CompatibilityFingerprint} while the campaign expects {workspace.RuleEnvironment.CompatibilityFingerprint}."
                        : $"{dossier.DisplayName} is current on {workspace.RuleEnvironment.CompatibilityFingerprint} and ready to reopen from this workspace.";

                return new DossierFreshnessCue(
                    DossierId: dossier.DossierId,
                    RunnerHandle: dossier.RunnerHandle,
                    Status: status,
                    Severity: severity,
                    Summary: summary);
            })
            .ToArray();

    private static IReadOnlyList<RuleEnvironmentHealthCue> BuildRuleEnvironmentHealth(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore)
    {
        List<RuleEnvironmentHealthCue> cues =
        [
            new(
                EnvironmentId: workspace.RuleEnvironment.EnvironmentId,
                Severity: IsGovernedRuleEnvironmentReady(workspace.RuleEnvironment) ? "ready" : "review",
                Title: "Campaign rule environment",
                Summary: $"{workspace.RuleEnvironment.OwnerScope} scope is on the {DescribeRuleEnvironmentLifecycleStage(workspace.RuleEnvironment).ToLowerInvariant()} rail for {workspace.RuleEnvironment.CompatibilityFingerprint}.")
        ];

        bool restoreMatches = restore.RecentRuleEnvironments.Any(env =>
            string.Equals(env.CompatibilityFingerprint, workspace.RuleEnvironment.CompatibilityFingerprint, StringComparison.OrdinalIgnoreCase));
        cues.Add(new RuleEnvironmentHealthCue(
            EnvironmentId: $"{workspace.RuleEnvironment.EnvironmentId}:restore",
            Severity: restoreMatches ? "ready" : "warning",
            Title: "Restore rule posture",
            Summary: restoreMatches
                ? "The restore packet already includes the same rule fingerprint as the shared campaign view."
                : "The restore packet does not yet show the same rule fingerprint as the shared campaign view."));

        bool dossierMismatch = workspace.Dossiers.Any(dossier =>
            !string.Equals(dossier.RuleEnvironment.CompatibilityFingerprint, workspace.RuleEnvironment.CompatibilityFingerprint, StringComparison.OrdinalIgnoreCase));
        if (dossierMismatch)
        {
            cues.Add(new RuleEnvironmentHealthCue(
                EnvironmentId: $"{workspace.RuleEnvironment.EnvironmentId}:dossiers",
                Severity: "attention",
                Title: "Dossier rule mismatch",
                Summary: "At least one dossier still needs rule-environment repair before this workspace is fully table-safe."));
        }

        return cues;
    }

    private static bool IsGovernedRuleEnvironmentReady(RuleEnvironmentRef environment)
    {
        return string.Equals(environment.ApprovalState, "approved", StringComparison.OrdinalIgnoreCase)
            || string.Equals(environment.ApprovalState, "published", StringComparison.OrdinalIgnoreCase);
    }

    private static string DescribeRuleEnvironmentLifecycleStage(RuleEnvironmentRef environment)
    {
        return environment.ApprovalState.Trim().ToLowerInvariant() switch
        {
            "published" => "Published",
            "approved" => "Campaign-approved",
            "self_service" => "Sandbox",
            _ => environment.ApprovalState
        };
    }

    private static RunboardSummary? BuildRunboardSummary(CampaignWorkspaceProjection workspace, RunProjection? leadRun)
    {
        if (leadRun is null)
        {
            return null;
        }

        IReadOnlyList<ObjectiveProjection> openObjectives = leadRun.Objectives
            .Where(static item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        string objectiveSummary = openObjectives.Count == 0
            ? "No open objective is pinned right now."
            : $"{openObjectives.Count} objective(s) still need attention before the next recap-safe handoff.";

        return new RunboardSummary(
            RunId: leadRun.RunId,
            Title: leadRun.Title,
            Status: leadRun.Status,
            ActiveSceneId: leadRun.ActiveSceneId,
            ActiveSceneSummary: workspace.ActiveSceneSummary,
            ObjectiveSummary: objectiveSummary,
            Blockers: openObjectives
                .Take(4)
                .Select(static item => $"{item.Title} stays {item.Status} with {item.Pressure} pressure.")
                .ToArray(),
            ReturnSummary: workspace.ReturnSummary);
    }

    private static IReadOnlyList<ContinuityConflictCue> BuildContinuityConflicts(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore)
    {
        List<ContinuityConflictCue> cues = restore.ConflictSummaries
            .Select(summary => new ContinuityConflictCue(
                CueId: $"conflict:{workspace.WorkspaceId}:{StableCueId(summary)}",
                Severity: "warning",
                Summary: summary,
                ResolutionAction: $"Resolve restore review before you reopen {workspace.CampaignName} on another device."))
            .ToList();

        cues.AddRange(restore.LocalOnlyNotes.Select(summary => new ContinuityConflictCue(
            CueId: $"local-only:{workspace.WorkspaceId}:{StableCueId(summary)}",
            Severity: "info",
            Summary: summary,
            ResolutionAction: "Keep this install local-only until the claimed device and restore rail are back in sync.")));

        return cues.Take(6).ToArray();
    }

    private static IReadOnlyList<RecapShelfEntry> BuildRecapShelf(
        CampaignWorkspaceProjection workspace,
        IReadOnlyList<CreatorPublicationProjection> creatorPublications)
    {
        Dictionary<string, DateTimeOffset> aftermathTimes = (workspace.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>())
            .ToDictionary(static item => item.PackageId, static item => item.GeneratedAtUtc, StringComparer.OrdinalIgnoreCase);
        DateTimeOffset defaultUpdatedAtUtc = workspace.LatestContinuity?.CapturedAtUtc ?? DateTimeOffset.UtcNow;
        var publicationsById = creatorPublications.ToDictionary(static item => item.PublicationId, StringComparer.OrdinalIgnoreCase);
        var publicationsByArtifactId = creatorPublications
            .Where(item => !string.IsNullOrWhiteSpace(item.ArtifactId))
            .GroupBy(item => item.ArtifactId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .First(),
                StringComparer.OrdinalIgnoreCase);
        return SelectBoundedRecapShelfItems(workspace.RecapShelf, aftermathTimes, defaultUpdatedAtUtc)
            .Select(item =>
            {
                CreatorPublicationProjection? creatorPublication = ResolveCreatorPublicationForRecapItem(item, publicationsById, publicationsByArtifactId);
                bool creatorLinked = creatorPublication is not null;
                return new RecapShelfEntry(
                    EntryId: item.ProjectionId,
                    Kind: item.Kind,
                    Label: item.Label,
                    Summary: item.Summary,
                    ArtifactId: item.ArtifactId,
                    UpdatedAtUtc: aftermathTimes.TryGetValue(item.ProjectionId, out DateTimeOffset updatedAtUtc)
                        ? updatedAtUtc
                        : defaultUpdatedAtUtc,
                    Audience: creatorLinked
                        ? DescribeRecapShelfAudience(item, creatorLinked)
                        : string.IsNullOrWhiteSpace(item.Audience)
                            ? DescribeRecapShelfAudience(item, creatorLinked)
                            : item.Audience,
                    OwnershipSummary: creatorLinked
                        ? DescribeRecapShelfOwnershipSummary(workspace, item)
                        : string.IsNullOrWhiteSpace(item.OwnershipSummary)
                            ? DescribeRecapShelfOwnershipSummary(workspace, item)
                            : item.OwnershipSummary,
                    PublicationState: creatorLinked
                        ? creatorPublication!.PublicationStatus
                        : string.IsNullOrWhiteSpace(item.PublicationState)
                            ? DescribeRecapShelfPublicationState(item)
                            : item.PublicationState,
                    TrustBand: creatorLinked ? creatorPublication!.TrustBand : item.TrustBand,
                    Discoverable: creatorLinked ? creatorPublication!.Discoverable : item.Discoverable,
                    PublicationSummary: creatorLinked
                        ? DescribeRecapShelfPublicationSummary(workspace, item, creatorPublication!, true)
                        : string.IsNullOrWhiteSpace(item.PublicationSummary)
                            ? DescribeSharedPublicationSummary(workspace, item)
                            : item.PublicationSummary,
                    CreatorPublicationId: creatorLinked ? creatorPublication!.PublicationId : item.CreatorPublicationId,
                    NextSafeAction: creatorLinked
                        ? creatorPublication!.NextSafeAction ?? workspace.NextSafeAction
                        : string.IsNullOrWhiteSpace(item.NextSafeAction)
                            ? DescribeRecapShelfNextSafeAction(workspace, item)
                            : item.NextSafeAction,
                    ProvenanceSummary: DescribeRecapShelfProvenanceSummary(workspace, item, creatorPublication, creatorLinked),
                    AuditSummary: DescribeRecapShelfAuditSummary(workspace, item, creatorPublication, creatorLinked));
            })
            .ToArray();
    }

    private static IReadOnlyList<PublicationSafeProjection> SelectBoundedRecapShelfItems(
        IReadOnlyList<PublicationSafeProjection> items,
        IReadOnlyDictionary<string, DateTimeOffset> aftermathTimes,
        DateTimeOffset defaultUpdatedAtUtc)
    {
        var rankedItems = items
            .Select(item => new
            {
                Item = item,
                Category = BoundedRecapShelfCategory(item),
                UpdatedAtUtc = ResolveBoundedRecapShelfUpdatedAt(item, aftermathTimes, defaultUpdatedAtUtc)
            })
            .ToArray();

        var selected = rankedItems
            .GroupBy(item => item.Category, StringComparer.OrdinalIgnoreCase)
            .OrderByDescending(group => BoundedRecapShelfCategoryPriority(group.Key))
            .ThenByDescending(group => group.Max(item => item.UpdatedAtUtc))
            .Select(group => group
                .OrderByDescending(item => item.UpdatedAtUtc)
                .ThenBy(item => item.Item.Label, StringComparer.OrdinalIgnoreCase)
                .First())
            .Take(6)
            .ToList();

        if (selected.Count < 6)
        {
            HashSet<string> selectedIds = selected
                .Select(item => item.Item.ProjectionId)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            selected.AddRange(rankedItems
                .Where(item => selectedIds.Add(item.Item.ProjectionId))
                .OrderByDescending(item => BoundedRecapShelfPriority(item.Item))
                .ThenByDescending(item => item.UpdatedAtUtc)
                .ThenBy(item => item.Item.Label, StringComparer.OrdinalIgnoreCase)
                .Take(6 - selected.Count));
        }

        return selected
            .OrderByDescending(item => BoundedRecapShelfCategoryPriority(item.Category))
            .ThenByDescending(item => item.UpdatedAtUtc)
            .ThenBy(item => item.Item.Label, StringComparer.OrdinalIgnoreCase)
            .Select(item => item.Item)
            .ToArray();
    }

    private static DateTimeOffset ResolveBoundedRecapShelfUpdatedAt(
        PublicationSafeProjection item,
        IReadOnlyDictionary<string, DateTimeOffset> aftermathTimes,
        DateTimeOffset defaultUpdatedAtUtc)
        => aftermathTimes.TryGetValue(item.ProjectionId, out DateTimeOffset updatedAtUtc)
            ? updatedAtUtc
            : defaultUpdatedAtUtc;

    private static string BoundedRecapShelfCategory(PublicationSafeProjection item)
    {
        string normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("campaign_recap", StringComparison.Ordinal)
            || normalizedKind == "campaign")
        {
            return "campaign";
        }

        if (normalizedKind.Contains("primer", StringComparison.Ordinal))
        {
            return "primer";
        }

        if (normalizedKind.Contains("runboard", StringComparison.Ordinal)
            || normalizedKind.Contains("module", StringComparison.Ordinal))
        {
            return "run_module";
        }

        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return "dossier";
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return "replay";
        }

        if (normalizedKind.Contains("session_recap", StringComparison.Ordinal)
            || normalizedKind.Contains("after_action", StringComparison.Ordinal)
            || normalizedKind.Contains("recap", StringComparison.Ordinal))
        {
            return "aftermath";
        }

        if (normalizedKind.Contains("downtime", StringComparison.Ordinal))
        {
            return "downtime";
        }

        return "other";
    }

    private static int BoundedRecapShelfCategoryPriority(string category)
        => category switch
        {
            "campaign" => 6,
            "primer" => 5,
            "run_module" => 4,
            "dossier" => 3,
            "replay" => 2,
            "aftermath" => 1,
            "downtime" => 0,
            _ => -1
        };

    private static int BoundedRecapShelfPriority(PublicationSafeProjection item)
        => BoundedRecapShelfCategoryPriority(BoundedRecapShelfCategory(item));

    private static bool SupportsCreatorShelfProjection(PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        return normalizedKind.Contains("recap", StringComparison.Ordinal)
            || normalizedKind.Contains("after", StringComparison.Ordinal)
            || normalizedKind.Contains("downtime", StringComparison.Ordinal)
            || normalizedKind.Contains("replay", StringComparison.Ordinal)
            || normalizedKind.Contains("dossier", StringComparison.Ordinal)
            || normalizedKind.Contains("runboard", StringComparison.Ordinal)
            || normalizedKind.Contains("campaign", StringComparison.Ordinal);
    }

    private static CreatorPublicationProjection? ResolveCreatorPublicationForRecapItem(
        PublicationSafeProjection item,
        IReadOnlyDictionary<string, CreatorPublicationProjection> publicationsById,
        IReadOnlyDictionary<string, CreatorPublicationProjection> publicationsByArtifactId)
    {
        if (!string.IsNullOrWhiteSpace(item.CreatorPublicationId)
            && publicationsById.TryGetValue(item.CreatorPublicationId, out CreatorPublicationProjection? creatorPublicationById))
        {
            return creatorPublicationById;
        }

        if (!string.IsNullOrWhiteSpace(item.ArtifactId)
            && publicationsByArtifactId.TryGetValue(item.ArtifactId, out CreatorPublicationProjection? creatorPublicationByArtifact))
        {
            return creatorPublicationByArtifact;
        }

        return null;
    }

    private static string DescribeRecapShelfAudience(PublicationSafeProjection item, bool creatorLinked)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (creatorLinked)
        {
            return normalizedKind.Contains("dossier", StringComparison.Ordinal)
                ? "personal,campaign,creator"
                : "campaign,creator";
        }

        if (normalizedKind.Contains("dossier", StringComparison.Ordinal)
            || normalizedKind.Contains("campaign_recap", StringComparison.Ordinal))
        {
            return "personal,campaign";
        }

        return "campaign";
    }

    private static string DescribeRecapShelfOwnershipSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return $"{workspace.CampaignName} reuses the same governed dossier artifact on the signed-in account path instead of forking a shadow copy.";
        }

        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return $"{workspace.CampaignName} keeps this GM-facing packet on the shared campaign rail so organizer follow-through stays reviewable.";
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return $"{workspace.CampaignName} keeps this replay-safe artifact pinned to the shared continuity lane so contested turns can be reviewed without forking campaign truth.";
        }

        return $"{workspace.CampaignName} keeps this recap-safe artifact pinned to the shared continuity lane for return, audit, and reuse.";
    }

    private static string DescribeRecapShelfPublicationState(PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return "personal_ready";
        }

        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return "campaign_ready";
        }

        return "publication_safe";
    }

    private static string DescribeRecapShelfPublicationSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection? creatorPublication,
        bool creatorLinked)
    {
        if (creatorLinked && creatorPublication is not null)
        {
            var visibility = string.IsNullOrWhiteSpace(creatorPublication.Visibility)
                ? "shared"
                : creatorPublication.Visibility;
            var nextSafeAction = string.IsNullOrWhiteSpace(creatorPublication.NextSafeAction)
                ? "Open publication status before you widen the audience."
                : creatorPublication.NextSafeAction!;
            return $"{creatorPublication.Title} is already attached on the publication shelf with {visibility} visibility. {nextSafeAction}";
        }

        return DescribeSharedPublicationSummary(workspace, item);
    }

    private static string DescribeRecapShelfProvenanceSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection? creatorPublication,
        bool creatorLinked)
    {
        if (!string.IsNullOrWhiteSpace(item.ProvenanceSummary))
        {
            return item.ProvenanceSummary!;
        }

        if (creatorLinked && !string.IsNullOrWhiteSpace(creatorPublication?.ProvenanceSummary))
        {
            return creatorPublication.ProvenanceSummary;
        }

        return $"{workspace.RuleEnvironment.CompatibilityFingerprint} keeps {item.Label} attached to {workspace.CampaignName} without a shadow export lane.";
    }

    private static string DescribeRecapShelfAuditSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection? creatorPublication,
        bool creatorLinked)
    {
        if (!string.IsNullOrWhiteSpace(item.AuditSummary))
        {
            return item.AuditSummary!;
        }

        DateTimeOffset updatedAtUtc = creatorLinked
            ? creatorPublication?.UpdatedAtUtc ?? DateTimeOffset.UtcNow
            : workspace.LatestContinuity?.CapturedAtUtc
                ?? workspace.AftermathPackages?.FirstOrDefault()?.GeneratedAtUtc
                ?? DateTimeOffset.UtcNow;
        string auditSource = creatorLinked
            ? "publication review and campaign return"
            : "campaign return";
        return $"Updated {updatedAtUtc:yyyy-MM-dd HH:mm} UTC on the governed {auditSource} lane for {workspace.CampaignName}.";
    }

    private static string DescribeSharedPublicationSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return $"Personal and campaign views already share this {workspace.CampaignName} artifact without requiring a second export lane.";
        }

        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return "Campaign return and GM prep reuse the same packet before shared publication opens.";
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return "Campaign return and contested-turn review reuse the same replay-safe packet before shared publication opens.";
        }

        return "Campaign return already trusts this recap-safe artifact, and shared publication can promote the same truth without rebuilding it.";
    }

    private static string DescribeRecapShelfNextSafeAction(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return "Keep prep, aftermath, and next-session follow-through on the shared campaign rail before you branch into another export lane.";
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return "Keep contested-turn review on the shared campaign rail before you widen the replay artifact audience or publish another copy.";
        }

        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return "Reopen the shared campaign view before you move this runner artifact into another campaign, shelf, or publication step.";
        }

        return workspace.NextSafeAction
            ?? "Open the shared campaign view before you widen the artifact audience or trust a second copy.";
    }

    private static IReadOnlyList<SupportClosureCue> BuildSupportClosures(IReadOnlyList<SupportCaseDigestViewModel> digests)
        => digests
            .Take(4)
            .Select(item => new SupportClosureCue(
                CaseId: item.CaseId,
                Status: item.StatusLabel,
                StageLabel: item.StageLabel,
                Summary: item.ClosureSummary,
                NextSafeAction: item.NextSafeAction,
                FixedReleaseLabel: item.FixedReleaseLabel,
                AffectedInstallSummary: item.AffectedInstallSummary))
            .ToArray();

    private static IReadOnlyList<KnownIssueAffectingInstall> BuildKnownIssues(IReadOnlyList<SupportCaseDigestViewModel> digests)
        => digests
            .Where(static item => item.ReporterActionNeeded || item.CanVerifyFix || !string.Equals(item.StageLabel, "Closed and confirmed", StringComparison.Ordinal))
            .Take(4)
            .Select(item => new KnownIssueAffectingInstall(
                CaseId: item.CaseId,
                Severity: item.ReporterActionNeeded ? "warning" : item.CanVerifyFix ? "attention" : "info",
                Summary: item.ReleaseProgressSummary,
                AffectedInstallSummary: item.AffectedInstallSummary,
                DetailHref: item.DetailHref))
            .ToArray();

    private static IReadOnlyList<DecisionNotice> BuildDecisionNotices(
        CampaignWorkspaceProjection workspace,
        CampaignWorkspaceDigestProjection? digest,
        InstallLinkingSummaryDto? installLinking,
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests,
        CampaignPrepLibrarySummary prepLibrary,
        RunProjection? leadRun)
    {
        List<DecisionNotice> notices = [];
        ClaimedInstallationDto? installation = installLinking?.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        if (installation is not null)
        {
            notices.Add(new DecisionNotice(
                NoticeId: $"install:{installation.InstallationId}",
                Kind: "install_role",
                Summary: $"{ResolveDeviceRole(installation)} stays attached to {installation.Platform}/{installation.HeadId} on {installation.Channel}.",
                ActionLabel: "Open account",
                ActionHref: "/account"));
        }
        else if ((installLinking?.PendingClaimTickets.Count ?? 0) > 0)
        {
            notices.Add(new DecisionNotice(
                NoticeId: $"claim:{workspace.WorkspaceId}",
                Kind: "install_claim",
                Summary: "Finish the pending install claim before you trust restore, support, or update truth from this device.",
                ActionLabel: "Open downloads",
                ActionHref: "/downloads"));
        }

        notices.Add(BuildPortableExchangeDecisionNotice(workspace, prepLibrary, leadRun));

        if ((digest?.Watchouts.Count ?? 0) > 0)
        {
            notices.Add(new DecisionNotice(
                NoticeId: $"workspace:{workspace.WorkspaceId}:watchout",
                Kind: "workspace_watchout",
                Summary: digest!.Watchouts[0],
                ActionLabel: "Open shared campaign view",
                ActionHref: $"/account/work/workspaces/{Uri.EscapeDataString(workspace.WorkspaceId)}"));
        }

        if (supportDigests.Count > 0)
        {
            SupportCaseDigestViewModel leadCase = supportDigests[0];
            notices.Add(new DecisionNotice(
                NoticeId: $"support:{leadCase.CaseId}",
                Kind: "support_follow_through",
                Summary: leadCase.ReleaseProgressSummary,
                ActionLabel: leadCase.PrimaryActionLabel,
                ActionHref: leadCase.PrimaryActionHref));
        }

        return notices
            .DistinctBy(static item => item.NoticeId, StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();
    }

    private static DecisionNotice BuildPortableExchangeDecisionNotice(
        CampaignWorkspaceProjection workspace,
        CampaignPrepLibrarySummary prepLibrary,
        RunProjection? leadRun)
    {
        bool hasPinnedRun = leadRun is not null && !string.IsNullOrWhiteSpace(leadRun.RunId);
        string scopeSummary = BuildPortableExchangeScopeSummary(workspace, prepLibrary);
        string formatSummary = hasPinnedRun
            ? "Formats include chummer.portable-dossier.v1, chummer.portable-campaign.v1, session-runtime-bundle.v1, and foundry-vtt.scene-ledger.v1."
            : "Formats include chummer.portable-dossier.v1 and chummer.portable-campaign.v1.";
        string summary = hasPinnedRun
            ? $"Portable exchange is ready for inspect-only, merge, or governed replace across {scopeSummary}; run {leadRun!.Title} stays pinned on the same receipt. {formatSummary}"
            : $"Portable exchange is ready for inspect-only or merge across {scopeSummary}; governed replace stays review-required until a live run is pinned. {formatSummary}";

        return new DecisionNotice(
            NoticeId: $"portable-exchange:{workspace.WorkspaceId}",
            Kind: "portable_exchange",
            Summary: summary,
            ActionLabel: "Review portable exchange",
            ActionHref: $"/account/work/workspaces/{Uri.EscapeDataString(workspace.WorkspaceId)}#portable-exchange");
    }

    private static string BuildPortableExchangeScopeSummary(
        CampaignWorkspaceProjection workspace,
        CampaignPrepLibrarySummary prepLibrary)
    {
        List<string> parts = [];

        if (workspace.Dossiers.Count > 0)
        {
            parts.Add($"{workspace.Dossiers.Count} dossier(s)");
        }

        if (prepLibrary.Packets.Count > 0)
        {
            parts.Add($"{prepLibrary.Packets.Count} prep packet(s)");
        }

        int aftermathPackageCount = workspace.AftermathPackages?.Count ?? 0;
        if (aftermathPackageCount > 0)
        {
            parts.Add($"{aftermathPackageCount} aftermath package(s)");
        }

        if (workspace.Runs.Count > 0)
        {
            parts.Add($"{workspace.Runs.Count} run receipt(s)");
        }

        return parts.Count == 0
            ? "the current shared campaign truth"
            : string.Join(", ", parts);
    }

    private static NextSafeActionCue BuildNextSafeActionCue(
        CampaignWorkspaceProjection workspace,
        InstallLinkingSummaryDto? installLinking,
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests)
    {
        SupportCaseDigestViewModel? actionCase = supportDigests.FirstOrDefault(static item => item.ReporterActionNeeded)
            ?? supportDigests.FirstOrDefault(static item => item.CanVerifyFix);
        if (actionCase is not null)
        {
            return new NextSafeActionCue(
                ActionId: $"support:{actionCase.CaseId}",
                Label: actionCase.PrimaryActionLabel,
                Summary: actionCase.NextSafeAction,
                SourceKind: "support");
        }

        if ((installLinking?.ClaimedInstallations?.Count ?? 0) == 0 && (installLinking?.PendingClaimTickets.Count ?? 0) > 0)
        {
            return new NextSafeActionCue(
                ActionId: $"claim:{workspace.WorkspaceId}",
                Label: "Finish install claim",
                Summary: "Redeem the pending claim code on this device before you trust restore, update, or support posture.",
                SourceKind: "install_linking");
        }

        return new NextSafeActionCue(
            ActionId: $"workspace:{workspace.WorkspaceId}",
            Label: "Open shared campaign view",
            Summary: workspace.NextSafeAction ?? "Open the shared campaign view and continue from the latest continuity snapshot.",
            SourceKind: "workspace");
    }

    private static CampaignPrepLibrarySummary BuildPrepLibrary(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        RunProjection? leadRun)
    {
        IReadOnlyList<GovernedPrepPacketSummary> packets = BuildPrepPackets(workspace, restore, leadRun);
        int reusableCount = packets.Count(static item => item.Reusable);
        IReadOnlyList<string> searchTerms = packets
            .SelectMany(static item => item.SearchTerms)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(8)
            .ToArray();

        string summary = packets.Count == 0
            ? "No governed prep packet is compiled yet for this shared campaign view."
            : $"{packets.Count} governed prep packet(s) stay attached to {workspace.CampaignName} without recreating local shadow prep notes.";
        string bindingSummary = leadRun is null
            ? "Packets stay bound to the shared campaign return lane so the next scene can reopen from governed truth."
            : $"{packets.Count} packet(s) stay bound to {leadRun.Title}, the active return lane, and the campaign rule posture.";
        string searchSummary = searchTerms.Count == 0
            ? "Search tokens compile from the campaign, run, rule, recap, and restore spine."
            : $"Search from {string.Join(", ", searchTerms.Take(6))}.";

        return new CampaignPrepLibrarySummary(
            Summary: summary,
            BindingSummary: bindingSummary,
            SearchSummary: searchSummary,
            ReusablePacketCount: reusableCount,
            SearchablePacketCount: packets.Count,
            Packets: packets);
    }

    private static IReadOnlyList<GovernedPrepPacketSummary> BuildPrepPackets(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        RunProjection? leadRun)
    {
        List<GovernedPrepPacketSummary> packets = [];

        if (BuildScenePrepPacket(workspace, leadRun) is { } scenePacket)
        {
            packets.Add(scenePacket);
        }

        if (BuildOppositionPrepPacket(workspace, leadRun) is { } oppositionPacket)
        {
            packets.Add(oppositionPacket);
        }

        if (BuildContinuityPrepPacket(workspace) is { } continuityPacket)
        {
            packets.Add(continuityPacket);
        }

        if (BuildCampaignReturnPrepPacket(workspace, leadRun) is { } campaignReturnPacket)
        {
            packets.Add(campaignReturnPacket);
        }

        if (BuildRosterMovementPrepPacket(workspace, leadRun) is { } rosterPacket)
        {
            packets.Add(rosterPacket);
        }

        if (BuildEventControlPrepPacket(workspace) is { } eventControlPacket)
        {
            packets.Add(eventControlPacket);
        }

        if (BuildAftermathPrepPacket(workspace, leadRun) is { } aftermathPacket)
        {
            packets.Add(aftermathPacket);
        }

        if (BuildPrepLaunchOpsPacket(workspace, leadRun) is { } prepLaunchOpsPacket)
        {
            packets.Add(prepLaunchOpsPacket);
        }

        if (BuildTravelPrefetchOpsPacket(workspace, leadRun) is { } travelPrefetchOpsPacket)
        {
            packets.Add(travelPrefetchOpsPacket);
        }

        if (BuildTravelPrepPacket(workspace, restore) is { } travelPacket)
        {
            packets.Add(travelPacket);
        }

        return packets
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ThenBy(static item => item.Title, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static GovernedPrepPacketSummary? BuildScenePrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        SceneProjection? activeScene = leadRun?.Scenes
            .FirstOrDefault(item => string.Equals(item.SceneId, leadRun.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
            ?? leadRun?.Scenes.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();
        if (activeScene is null && string.IsNullOrWhiteSpace(workspace.ActiveSceneSummary))
        {
            return null;
        }

        IReadOnlyList<string> evidence = new[]
            {
                activeScene?.Summary,
                workspace.ActiveSceneSummary,
                leadRun?.Objectives.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault()?.Summary,
                workspace.RuleEnvironment.CompatibilityFingerprint
            }
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item!.Trim())
            .Take(4)
            .ToArray();
        string sceneTitle = activeScene?.Title ?? "Active scene";
        string title = $"{sceneTitle} scene packet";
        string summary = activeScene?.Summary
            ?? workspace.ActiveSceneSummary
            ?? "Current scene prep is compiled from the shared campaign return lane.";
        string bindingSummary = leadRun is null
            ? $"Bound to {workspace.CampaignName} from the current shared return lane."
            : activeScene is null
                ? $"Bound to {leadRun.Title} from the current shared return lane."
                : $"Bound to {leadRun.Title} / {activeScene.Title} on {workspace.RuleEnvironment.CompatibilityFingerprint}.";

        return new GovernedPrepPacketSummary(
            PacketId: $"scene:{workspace.WorkspaceId}",
            Kind: "scene_packet",
            Title: title,
            Summary: summary,
            BindingSummary: bindingSummary,
            Reusable: false,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                sceneTitle,
                workspace.ActiveSceneSummary,
                leadRun?.Title,
                leadRun?.Objectives.Select(static item => item.Title),
                workspace.RuleEnvironment.CompatibilityFingerprint,
                workspace.RuleEnvironment.SourcePacks),
            EvidenceLines: evidence,
            UpdatedAtUtc: activeScene?.UpdatedAtUtc
                ?? leadRun?.UpdatedAtUtc
                ?? workspace.LatestContinuity?.CapturedAtUtc
                ?? DateTimeOffset.UtcNow);
    }

    private static GovernedPrepPacketSummary? BuildOppositionPrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        CampaignConsequenceProjection[] consequences = (workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>())
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Take(3)
            .ToArray();
        ObjectiveProjection[] objectiveSignals = (leadRun?.Objectives ?? Array.Empty<ObjectiveProjection>())
            .Where(static item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Take(3)
            .ToArray();
        SceneProjection? activeScene = leadRun?.Scenes
            .FirstOrDefault(item => string.Equals(item.SceneId, leadRun.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
            ?? leadRun?.Scenes.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();
        if (consequences.Length == 0
            && objectiveSignals.Length == 0
            && string.IsNullOrWhiteSpace(activeScene?.Summary))
        {
            return null;
        }

        string labels = string.Join(", ",
            consequences.Select(static item => item.Label)
                .Concat(objectiveSignals.Select(static item => item.Title))
                .Distinct(StringComparer.OrdinalIgnoreCase));
        int signalCount = consequences.Length + objectiveSignals.Length + (string.IsNullOrWhiteSpace(activeScene?.Summary) ? 0 : 1);
        string summary = consequences.Length > 0
            ? $"{signalCount} governed opposition signal(s) are active: {labels}."
            : $"{signalCount} governed opposition signal(s) are active from run pressure and active-scene cues: {labels}.";
        IReadOnlyList<string> evidence = BuildEvidenceLines(
            consequences.SelectMany(static item => item.EvidenceLines.Concat(item.Receipts.Select(static receipt => receipt.Summary))),
            objectiveSignals.Select(static item => item.Summary),
            objectiveSignals.Select(static item => $"{item.Title} stays {item.Status} with {item.Pressure} pressure."),
            activeScene?.Summary);

        return new GovernedPrepPacketSummary(
            PacketId: $"opposition:{workspace.WorkspaceId}",
            Kind: "opposition_packet",
            Title: $"{workspace.CampaignName} opposition packet",
            Summary: summary,
            BindingSummary: leadRun is null
                ? "Reusable across the campaign so the next scene can bind real opposition truth without local shadow packet models."
                : $"Reusable across {workspace.CampaignName}; currently bound to {leadRun.Title} and the active return lane.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                labels,
                consequences.Select(static item => item.Kind),
                consequences.Select(static item => item.State),
                consequences.SelectMany(static item => item.Receipts.Select(static receipt => receipt.SourceKind)),
                objectiveSignals.Select(static item => item.Title),
                objectiveSignals.Select(static item => item.Status),
                objectiveSignals.Select(static item => item.Pressure),
                activeScene?.Title,
                activeScene?.Summary,
                leadRun?.Title,
                leadRun?.Objectives.Select(static item => item.Title)),
            EvidenceLines: evidence,
            UpdatedAtUtc: new[]
                {
                    activeScene?.UpdatedAtUtc,
                    leadRun?.UpdatedAtUtc
                }
                .Concat(consequences.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
                .Concat(objectiveSignals.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
                .Where(static item => item.HasValue)
                .Select(static item => item!.Value)
                .DefaultIfEmpty(DateTimeOffset.UtcNow)
                .Max());
    }

    private static GovernedPrepPacketSummary? BuildContinuityPrepPacket(CampaignWorkspaceProjection workspace)
    {
        if (workspace.LatestContinuity is null
            && workspace.RecapShelf.Count == 0
            && workspace.Dossiers.Count == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = new[]
            {
                workspace.LatestContinuity?.Summary
            }
            .Concat(workspace.RecapShelf.Select(static item => item.Summary))
            .Concat(workspace.Dossiers.Select(static item => item.LatestContinuity?.Summary))
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item!.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

        return new GovernedPrepPacketSummary(
            PacketId: $"continuity:{workspace.WorkspaceId}",
            Kind: "continuity_packet",
            Title: $"{workspace.CampaignName} continuity handoff",
            Summary: workspace.RecapShelf.Count == 0
                ? "Continuity is pinned to the current shared return lane even before the first recap-safe output is published."
                : $"{workspace.RecapShelf.Count} recap-safe output(s) stay attached to the same shared continuity spine.",
            BindingSummary: "Bound to the same continuity snapshot that reopens dossiers, recaps, and publication-safe follow-through.",
            Reusable: false,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                workspace.ReturnSummary,
                workspace.LatestContinuity?.Summary,
                workspace.RecapShelf.Select(static item => item.Label),
                workspace.RecapShelf.Select(static item => item.Kind),
                workspace.Dossiers.Select(static item => item.RunnerHandle)),
            EvidenceLines: evidence,
            UpdatedAtUtc: workspace.LatestContinuity?.CapturedAtUtc
                ?? DateTimeOffset.UtcNow);
    }

    private static GovernedPrepPacketSummary? BuildCampaignReturnPrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        PublicationSafeProjection[] diaryRecaps = workspace.RecapShelf
            .Where(static item =>
            {
                string kind = item.Kind.Trim();
                return kind.Contains("diary", StringComparison.OrdinalIgnoreCase)
                    || kind.Contains("downtime", StringComparison.OrdinalIgnoreCase)
                    || kind.Contains("recap", StringComparison.OrdinalIgnoreCase)
                    || kind.Contains("after_action", StringComparison.OrdinalIgnoreCase)
                    || kind.Contains("career", StringComparison.OrdinalIgnoreCase)
                    || kind.Contains("log", StringComparison.OrdinalIgnoreCase);
            })
            .Take(4)
            .ToArray();
        CampaignConsequenceProjection[] relationshipConsequences = (workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>())
            .Where(static consequence => string.Equals(consequence.Kind, "contact", StringComparison.OrdinalIgnoreCase)
                || string.Equals(consequence.Kind, "heat", StringComparison.OrdinalIgnoreCase)
                || string.Equals(consequence.Kind, "reputation", StringComparison.OrdinalIgnoreCase)
                || string.Equals(consequence.Kind, "faction", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static consequence => consequence.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        WorkspaceChangePacketProjection[] returnChanges = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => string.Equals(packet.Kind, "next_session_carry_forward", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "after_action_report", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "downtime_brief", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "continuity", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "contact_update", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();

        if (diaryRecaps.Length == 0
            && relationshipConsequences.Length == 0
            && returnChanges.Length == 0
            && workspace.NextSessionCarryForward is null)
        {
            return null;
        }

        int diarySignalCount = diaryRecaps.Length + returnChanges.Length;
        int relationshipSignalCount = relationshipConsequences.Length;
        string summary = $"{Math.Max(1, diarySignalCount)} diary/continuity signal(s) and {relationshipSignalCount} relationship signal(s) stay on one governed return lane for downtime and next-session reopen.";
        string bindingSummary = leadRun is null
            ? "Diary updates, contacts, heat, and return cues stay attached to the same campaign truth without local note-shadow models."
            : $"{leadRun.Title} and campaign return cues share the same diary/contact/heat continuity lane.";
        IReadOnlyList<string> evidence = BuildEvidenceLines(
            workspace.ReturnSummary,
            workspace.NextSessionCarryForward?.Summary,
            workspace.NextSessionCarryForward?.ReturnSummary,
            diaryRecaps.Select(static item => item.Summary),
            returnChanges.Select(static item => item.Summary),
            relationshipConsequences.Select(static item => item.Summary),
            relationshipConsequences.SelectMany(static item => item.EvidenceLines));
        DateTimeOffset updatedAtUtc = new[]
            {
                workspace.LatestContinuity?.CapturedAtUtc,
                workspace.NextSessionCarryForward?.UpdatedAtUtc
            }
            .Concat(returnChanges.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Concat(relationshipConsequences.Select(static consequence => (DateTimeOffset?)consequence.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"campaign-return:{workspace.WorkspaceId}",
            Kind: "campaign_return_packet",
            Title: $"{workspace.CampaignName} diary, contacts, and heat return packet",
            Summary: summary,
            BindingSummary: bindingSummary,
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "diary",
                "contacts",
                "heat",
                "downtime",
                "return",
                workspace.ReturnSummary,
                workspace.NextSessionCarryForward?.Label,
                diaryRecaps.Select(static item => item.Kind),
                diaryRecaps.Select(static item => item.Label),
                returnChanges.Select(static item => item.Kind),
                returnChanges.Select(static item => item.Label),
                relationshipConsequences.Select(static item => item.Kind),
                relationshipConsequences.Select(static item => item.Label),
                relationshipConsequences.Select(static item => item.State)),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static GovernedPrepPacketSummary? BuildRosterMovementPrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        RosterTransferProjection[] transfers = (workspace.RosterTransfers ?? Array.Empty<RosterTransferProjection>())
            .OrderByDescending(static item => item.TransferredAtUtc)
            .Take(3)
            .ToArray();
        WorkspaceChangePacketProjection[] rosterChangeSignals = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsRosterMovementSignalKind(packet.Kind))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        ObjectiveProjection[] rosterObjectives = (leadRun?.Objectives ?? Array.Empty<ObjectiveProjection>())
            .Where(static objective => IsRosterObjectiveSignal(objective.Title, objective.Summary))
            .OrderByDescending(static objective => objective.UpdatedAtUtc)
            .Take(3)
            .ToArray();
        bool carryForwardRosterSignal = IsRosterObjectiveSignal(
            workspace.NextSessionCarryForward?.Label,
            workspace.NextSessionCarryForward?.Summary)
            || IsRosterObjectiveSignal(
                workspace.NextSessionCarryForward?.ReturnSummary,
                workspace.NextSessionCarryForward?.NextSafeAction);
        if (transfers.Length == 0
            && rosterChangeSignals.Length == 0
            && rosterObjectives.Length == 0
            && !carryForwardRosterSignal)
        {
            return null;
        }

        IReadOnlyList<string> evidence = transfers
            .Select(static item => item.Summary)
            .Concat(transfers.SelectMany(static item => item.AuditLines))
            .Concat(rosterChangeSignals.Select(static packet => packet.Summary))
            .Concat(rosterObjectives.Select(static objective => objective.Summary))
            .Concat(rosterObjectives.Select(static objective => $"{objective.Title} stays {objective.Status} with {objective.Pressure} pressure."))
            .Concat(
                carryForwardRosterSignal
                    ? BuildEvidenceLines(
                        workspace.NextSessionCarryForward?.Summary,
                        workspace.NextSessionCarryForward?.ReturnSummary,
                        workspace.NextSessionCarryForward?.NextSafeAction)
                    : Array.Empty<string>())
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();
        int signalCount = transfers.Length + rosterChangeSignals.Length + rosterObjectives.Length + (carryForwardRosterSignal ? 1 : 0);
        string summary = transfers.Length > 0
            ? $"{signalCount} roster movement signal(s) keep ownership and campaign movement on the same governed lane."
            : $"{signalCount} roster movement signal(s) stay governed from roster-change packets, run pressure, and carry-forward signals while transfer receipts catch up.";
        DateTimeOffset updatedAtUtc = new[]
            {
                workspace.NextSessionCarryForward?.UpdatedAtUtc,
                leadRun?.UpdatedAtUtc
            }
            .Concat(transfers.Select(static item => (DateTimeOffset?)item.TransferredAtUtc))
            .Concat(rosterChangeSignals.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Concat(rosterObjectives.Select(static objective => (DateTimeOffset?)objective.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"roster:{workspace.WorkspaceId}",
            Kind: "roster_movement_packet",
            Title: $"{workspace.CampaignName} roster movement packet",
            Summary: summary,
            BindingSummary: "Reusable across campaign and season operations so roster movement stays auditable without shadow notes.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "roster",
                "movement",
                "crew",
                "assignment",
                transfers.Select(static item => item.RunnerHandle),
                transfers.Select(static item => item.SourceCampaignName),
                transfers.Select(static item => item.TargetCampaignName),
                transfers.Select(static item => item.SourceGroupName),
                transfers.Select(static item => item.TargetGroupName),
                transfers.Select(static item => item.SourceCrewName),
                transfers.Select(static item => item.TargetCrewName),
                rosterChangeSignals.Select(static item => item.Kind),
                rosterChangeSignals.Select(static item => item.Label),
                rosterObjectives.Select(static item => item.Title),
                rosterObjectives.Select(static item => item.Status),
                rosterObjectives.Select(static item => item.Pressure),
                workspace.NextSessionCarryForward?.Label,
                workspace.NextSessionCarryForward?.Summary),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static bool IsRosterMovementSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        return string.Equals(normalizedKind, "roster_transfer", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "roster_assignment", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "roster_move", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "crew_assignment", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "crew_handoff", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("roster", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("crew", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsRosterObjectiveSignal(string? title, string? summary)
    {
        return ContainsRosterToken(title) || ContainsRosterToken(summary);
    }

    private static bool ContainsRosterToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("roster", StringComparison.OrdinalIgnoreCase)
            || value.Contains("crew", StringComparison.OrdinalIgnoreCase)
            || value.Contains("assignment", StringComparison.OrdinalIgnoreCase)
            || value.Contains("handoff", StringComparison.OrdinalIgnoreCase)
            || value.Contains("bench", StringComparison.OrdinalIgnoreCase)
            || value.Contains("rotation", StringComparison.OrdinalIgnoreCase);
    }

    private static GovernedPrepPacketSummary? BuildAftermathPrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        AftermathRecapPackageProjection[] packages = (workspace.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>())
            .OrderByDescending(static item => item.GeneratedAtUtc)
            .Take(3)
            .ToArray();
        if (packages.Length == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = packages
            .Select(static item => item.Summary)
            .Concat(packages.SelectMany(static item => item.EvidenceLines))
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

        return new GovernedPrepPacketSummary(
            PacketId: $"aftermath:{workspace.WorkspaceId}",
            Kind: "aftermath_packet",
            Title: $"{workspace.CampaignName} aftermath and downtime packet",
            Summary: $"{packages.Length} aftermath or downtime package(s) stay attached for recap, recovery, and next-session return.",
            BindingSummary: leadRun is null
                ? "Reusable across the campaign so aftermath, downtime, and return stay on governed workspace truth."
                : $"Reusable across {workspace.CampaignName} and currently anchored to {leadRun.Title} for return-loop continuity.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "aftermath",
                "downtime",
                packages.Select(static item => item.PackageKind),
                packages.Select(static item => item.Title),
                packages.Select(static item => item.RunTitle),
                packages.Select(static item => item.ArtifactId)),
            EvidenceLines: evidence,
            UpdatedAtUtc: packages.Max(static item => item.GeneratedAtUtc));
    }

    private static GovernedPrepPacketSummary? BuildPrepLaunchOpsPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        GovernedPrepLaunchProjection[] launches = (workspace.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>())
            .OrderByDescending(static item => item.LaunchedAtUtc)
            .Take(4)
            .ToArray();
        if (launches.Length == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = launches
            .Select(static item => item.Summary)
            .Concat(launches.SelectMany(static item => item.AuditLines))
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

        return new GovernedPrepPacketSummary(
            PacketId: $"prep-launch:{workspace.WorkspaceId}",
            Kind: "prep_launch_packet",
            Title: $"{workspace.CampaignName} governed prep launches",
            Summary: $"{launches.Length} prep-launch receipt(s) keep packet launches auditable on the same campaign lane.",
            BindingSummary: leadRun is null
                ? "Launch actions stay attached to campaign truth so GM prep operations do not fork into local-only notes."
                : $"Launch actions stay attached to {leadRun.Title} and the same account-audit campaign backbone.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "prep",
                "launch",
                "governed",
                "audit",
                launches.Select(static item => item.PacketKind),
                launches.Select(static item => item.PacketTitle),
                launches.Select(static item => item.TargetRunTitle),
                launches.Select(static item => item.TargetSceneTitle),
                launches.Select(static item => item.InitiatedByUserId)),
            EvidenceLines: evidence,
            UpdatedAtUtc: launches.Max(static item => item.LaunchedAtUtc));
    }

    private static GovernedPrepPacketSummary? BuildEventControlPrepPacket(CampaignWorkspaceProjection workspace)
    {
        WorkspaceChangePacketProjection[] eventPackets = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => string.Equals(packet.Kind, "next_session_carry_forward", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "prep_launch", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "roster_transfer", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "aftermath", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "downtime", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "replay_timeline", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "travel_prefetch", StringComparison.OrdinalIgnoreCase)
                || string.Equals(packet.Kind, "continuity", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        CampaignConsequenceProjection[] consequences = (workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>())
            .Where(static consequence => string.Equals(consequence.Kind, "heat", StringComparison.OrdinalIgnoreCase)
                || string.Equals(consequence.Kind, "contact", StringComparison.OrdinalIgnoreCase)
                || string.Equals(consequence.Kind, "reputation", StringComparison.OrdinalIgnoreCase)
                || string.Equals(consequence.Kind, "faction", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static consequence => consequence.UpdatedAtUtc)
            .Take(3)
            .ToArray();
        GovernedPrepLaunchProjection[] prepLaunches = (workspace.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>())
            .OrderByDescending(static launch => launch.LaunchedAtUtc)
            .Take(3)
            .ToArray();
        TravelPrefetchReceiptProjection[] travelPrefetches = (workspace.TravelPrefetches ?? Array.Empty<TravelPrefetchReceiptProjection>())
            .OrderByDescending(static receipt => receipt.StagedAtUtc)
            .Take(3)
            .ToArray();

        NextSessionCarryForwardProjection? carryForward = workspace.NextSessionCarryForward;
        if (eventPackets.Length == 0
            && consequences.Length == 0
            && prepLaunches.Length == 0
            && travelPrefetches.Length == 0
            && carryForward is null)
        {
            return null;
        }

        int eventCount = eventPackets.Length
            + prepLaunches.Length
            + travelPrefetches.Length
            + (carryForward is null ? 0 : 1);
        string consequenceSummary = consequences.Length == 0
            ? "Heat, contacts, and consequence posture stay linked to the same campaign return lane."
            : $"{consequences.Length} consequence signal(s) ({string.Join(", ", consequences.Select(static item => item.Label))}) stay attached to event control.";
        IReadOnlyList<string> evidence = BuildEvidenceLines(
            carryForward?.Summary,
            carryForward?.ReturnSummary,
            workspace.ReturnSummary,
            eventPackets.Select(static packet => packet.Summary),
            prepLaunches.Select(static launch => launch.Summary),
            prepLaunches.SelectMany(static launch => launch.AuditLines),
            travelPrefetches.Select(static receipt => receipt.PrefetchSummary),
            travelPrefetches.SelectMany(static receipt => receipt.InventoryLines),
            consequences.Select(static consequence => consequence.Summary),
            consequences.SelectMany(static consequence => consequence.EvidenceLines));
        DateTimeOffset updatedAtUtc = new[]
            {
                carryForward?.UpdatedAtUtc
            }
            .Concat(eventPackets.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Concat(prepLaunches.Select(static launch => (DateTimeOffset?)launch.LaunchedAtUtc))
            .Concat(travelPrefetches.Select(static receipt => (DateTimeOffset?)receipt.StagedAtUtc))
            .Concat(consequences.Select(static consequence => (DateTimeOffset?)consequence.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"event-control:{workspace.WorkspaceId}",
            Kind: "event_control_packet",
            Title: $"{workspace.CampaignName} event and season controls",
            Summary: $"{eventCount} event-control receipt(s) keep season operations and return-loop governance on one lane. {consequenceSummary}",
            BindingSummary: "Reusable across GM operations so prep launches, return windows, and consequence governance stay on campaign truth.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "event",
                "season",
                "control",
                "return",
                "operations",
                carryForward?.Label,
                carryForward?.Summary,
                eventPackets.Select(static packet => packet.Kind),
                eventPackets.Select(static packet => packet.Label),
                prepLaunches.Select(static launch => launch.PacketKind),
                prepLaunches.Select(static launch => launch.PacketTitle),
                prepLaunches.Select(static launch => launch.TargetRunTitle),
                prepLaunches.Select(static launch => launch.TargetSceneTitle),
                travelPrefetches.Select(static receipt => receipt.InstallationId),
                travelPrefetches.Select(static receipt => receipt.DeviceRole),
                travelPrefetches.Select(static receipt => receipt.Platform),
                travelPrefetches.Select(static receipt => receipt.HeadId),
                travelPrefetches.Select(static receipt => receipt.Channel),
                consequences.Select(static consequence => consequence.Kind),
                consequences.Select(static consequence => consequence.Label),
                consequences.Select(static consequence => consequence.State)),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static GovernedPrepPacketSummary? BuildTravelPrefetchOpsPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        TravelPrefetchReceiptProjection[] receipts = (workspace.TravelPrefetches ?? Array.Empty<TravelPrefetchReceiptProjection>())
            .OrderByDescending(static item => item.StagedAtUtc)
            .Take(4)
            .ToArray();
        if (receipts.Length == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = receipts
            .Select(static item => item.PrefetchSummary)
            .Concat(receipts.SelectMany(static item => item.InventoryLines))
            .Concat(receipts.SelectMany(static item => item.Boundaries))
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

        return new GovernedPrepPacketSummary(
            PacketId: $"travel-prefetch:{workspace.WorkspaceId}",
            Kind: "travel_prefetch_packet",
            Title: $"{workspace.CampaignName} staged travel prefetch receipts",
            Summary: $"{receipts.Length} travel-prefetch receipt(s) keep offline staging deliberate and reviewable per claimed device.",
            BindingSummary: leadRun is null
                ? "Travel staging actions stay attached to campaign truth so safehouse/travel operations are auditable."
                : $"Travel staging actions stay attached to {leadRun.Title} and the same account-audit campaign backbone.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "travel",
                "prefetch",
                "offline",
                "safehouse",
                "device",
                receipts.Select(static item => item.InstallationId),
                receipts.Select(static item => item.DeviceRole),
                receipts.Select(static item => item.Platform),
                receipts.Select(static item => item.HeadId),
                receipts.Select(static item => item.Channel),
                receipts.Select(static item => item.InitiatedByUserId)),
            EvidenceLines: evidence,
            UpdatedAtUtc: receipts.Max(static item => item.StagedAtUtc));
    }

    private static GovernedPrepPacketSummary? BuildTravelPrepPacket(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore)
    {
        if (restore.ClaimedDevices.Count == 0
            && restore.RecentArtifacts.Count == 0
            && restore.RecentRuleEnvironments.Count == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = restore.ClaimedDevices
            .Select(static item => item.RestoreSummary)
            .Concat(restore.RecentArtifacts.Select(static item => item.Summary))
            .Concat(restore.RecentRuleEnvironments.Select(static item => item.CompatibilityFingerprint))
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

        return new GovernedPrepPacketSummary(
            PacketId: $"travel:{workspace.WorkspaceId}",
            Kind: "travel_packet",
            Title: $"{workspace.CampaignName} travel cache packet",
            Summary: $"{restore.RecentArtifacts.Count} reconnectable artifact(s) and {restore.RecentRuleEnvironments.Count} rule snapshot(s) stay staged for bounded offline return.",
            BindingSummary: restore.ClaimedDevices.Count == 0
                ? "The packet is compiled, but a claimed travel lane still needs to be linked before you trust it on another device."
                : $"Reusable across {restore.ClaimedDevices.Count} claimed device(s) without moving install-local secrets into the roaming restore packet.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "safehouse",
                "travel",
                restore.ClaimedDevices.Select(static item => item.DeviceRole),
                restore.ClaimedDevices.Select(static item => item.Platform),
                restore.ClaimedDevices.Select(static item => item.HeadId),
                restore.ClaimedDevices.Select(static item => item.Channel),
                restore.RecentArtifacts.Select(static item => item.Label),
                restore.RecentRuleEnvironments.Select(static item => item.CompatibilityFingerprint)),
            EvidenceLines: evidence,
            UpdatedAtUtc: restore.GeneratedAtUtc);
    }

    private static TravelModeReadinessSummary BuildTravelMode(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        CampaignPrepLibrarySummary prepLibrary)
    {
        int claimedDeviceCount = restore.ClaimedDevices.Count;
        int travelReadyDeviceCount = restore.ClaimedDevices.Count(IsTravelReadyDevice);
        string prefetchInventorySummary = $"{DescribeRestorePrefetchInventory(restore.RecentDossiers.Count, restore.RecentCampaigns.Count, restore.RecentRuleEnvironments.Count, restore.RecentArtifacts.Count)} plus {prepLibrary.Packets.Count} governed prep packet(s)";
        string status = claimedDeviceCount == 0
            ? "warning"
            : restore.ConflictSummaries.Count > 0
                ? "attention"
                : travelReadyDeviceCount > 0
                    ? "ready"
                    : "review";
        string summary = claimedDeviceCount == 0
            ? $"Prefetch inventory is ready for {workspace.CampaignName}, but no claimed device return lane is linked yet."
            : travelReadyDeviceCount > 0
                ? $"{travelReadyDeviceCount} claimed device(s) can reopen {workspace.CampaignName} from a bounded travel/safehouse lane."
                : $"{claimedDeviceCount} claimed device(s) can reopen {workspace.CampaignName}, but travel posture is not explicit yet.";
        IReadOnlyList<string> boundaries = restore.LocalOnlyNotes
            .Concat(new[]
            {
                "Install-local caches, secrets, and runtime state stay local even when travel packets are staged for bounded offline use."
            })
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

        return new TravelModeReadinessSummary(
            Status: status,
            Summary: summary,
            PrefetchInventorySummary: prefetchInventorySummary,
            ClaimedDeviceCount: claimedDeviceCount,
            TravelReadyDeviceCount: travelReadyDeviceCount,
            Devices: restore.ClaimedDevices
                .Take(4)
                .Select(device => new TravelModeDeviceReadinessCue(
                    InstallationId: device.InstallationId,
                    DeviceRole: device.DeviceRole,
                    Platform: device.Platform,
                    HeadId: device.HeadId,
                    Channel: device.Channel,
                    Status: ResolveTravelDeviceStatus(device, restore.ConflictSummaries.Count > 0),
                    Summary: device.RestoreSummary))
                .ToArray(),
            Boundaries: boundaries);
    }

    private static IReadOnlyList<string> BuildSearchTerms(params object?[] values)
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase);

        foreach (string text in FlattenValues(values))
        {
            foreach (string rawToken in text.Split(SearchSeparators, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                string normalized = NormalizeSearchToken(rawToken);
                if (normalized.Length >= 3)
                {
                    tokens.Add(normalized);
                }
            }
        }

        return tokens.Take(10).ToArray();
    }

    private static IReadOnlyList<string> BuildEvidenceLines(params object?[] values)
        => FlattenValues(values)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

    private static IEnumerable<string> FlattenValues(IEnumerable<object?> values)
    {
        foreach (object? value in values)
        {
            switch (value)
            {
                case null:
                    continue;
                case string text when !string.IsNullOrWhiteSpace(text):
                    yield return text;
                    break;
                case IEnumerable<string> lines:
                    foreach (string line in lines.Where(static item => !string.IsNullOrWhiteSpace(item)))
                    {
                        yield return line;
                    }

                    break;
            }
        }
    }

    private static string NormalizeSearchToken(string token)
    {
        char[] filtered = token.Where(char.IsLetterOrDigit).ToArray();
        return filtered.Length == 0 ? string.Empty : new string(filtered);
    }

    private static IReadOnlyList<string> BuildPrepLibraryQueryTokens(string? queryText)
    {
        if (string.IsNullOrWhiteSpace(queryText))
        {
            return Array.Empty<string>();
        }

        HashSet<string> tokens = queryText
            .Split(SearchSeparators, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(NormalizeSearchToken)
            .Where(static token => token.Length >= 2)
            .Select(static token => token.ToLowerInvariant())
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        if (tokens.Count == 0)
        {
            string normalized = NormalizeSearchToken(queryText).ToLowerInvariant();
            if (normalized.Length >= 2)
            {
                tokens.Add(normalized);
            }
        }

        return tokens.ToArray();
    }

    private static bool MatchesPrepLibraryQuery(
        GovernedPrepPacketSummary packet,
        IReadOnlyList<string> queryTokens)
    {
        if (queryTokens.Count == 0)
        {
            return true;
        }

        string searchable = string.Join(
            " ",
            new[]
            {
                packet.Title,
                packet.Summary,
                packet.BindingSummary
            }
            .Concat(packet.SearchTerms)
            .Concat(packet.EvidenceLines)
            .Where(static text => !string.IsNullOrWhiteSpace(text)))
            .ToLowerInvariant();

        return queryTokens.All(token => searchable.Contains(token, StringComparison.OrdinalIgnoreCase));
    }

    private static RunProjection? ResolvePrepLaunchRun(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun,
        string? targetRunId)
    {
        string? normalized = NormalizeOptional(targetRunId);
        if (normalized is null)
        {
            return leadRun;
        }

        return workspace.Runs.FirstOrDefault(item => string.Equals(item.RunId, normalized, StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown target run: {normalized}");
    }

    private static SceneProjection? ResolvePrepLaunchScene(RunProjection? run, string? targetSceneId)
    {
        if (run is null)
        {
            return null;
        }

        string? normalized = NormalizeOptional(targetSceneId);
        if (normalized is null)
        {
            return run.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, run.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
                ?? run.Scenes.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();
        }

        return run.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, normalized, StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown target scene: {normalized}");
    }

    private static string BuildTravelPrefetchSummary(
        CampaignWorkspaceProjection workspace,
        ClaimedDeviceRestoreProjection device,
        CampaignPrepLibrarySummary prepLibrary)
    {
        string deviceLabel = $"{device.DeviceRole} on {device.Platform}/{device.HeadId}";
        return $"Staged the exact offline prefetch set for {deviceLabel} on {device.Channel} with {prepLibrary.Packets.Count} governed prep packet(s) attached to {workspace.CampaignName}.";
    }

    private static IReadOnlyList<string> BuildTravelPrefetchInventoryLines(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        CampaignPrepLibrarySummary prepLibrary,
        ClaimedDeviceRestoreProjection device)
    {
        List<string> lines =
        [
            $"Device lane: {device.DeviceRole} on {device.Platform}/{device.HeadId} via {device.Channel}.",
            $"Campaign: {workspace.CampaignName}.",
            $"Dossiers: {(restore.RecentDossiers.Count == 0 ? "none" : string.Join(", ", restore.RecentDossiers.Take(3).Select(static item => item.DisplayName)))}.",
            $"Rule environments: {(restore.RecentRuleEnvironments.Count == 0 ? "none" : string.Join(", ", restore.RecentRuleEnvironments.Take(2).Select(static item => item.CompatibilityFingerprint)))}.",
            $"Artifacts: {(restore.RecentArtifacts.Count == 0 ? "none" : string.Join(", ", restore.RecentArtifacts.Take(3).Select(static item => item.Label)))}.",
            $"Governed prep packets: {(prepLibrary.Packets.Count == 0 ? "none" : string.Join(", ", prepLibrary.Packets.Take(3).Select(static item => item.Title)))}."
        ];

        if (restore.RecentCampaigns.Count > 0)
        {
            lines.Insert(3, $"Campaign returns: {string.Join(", ", restore.RecentCampaigns.Take(2).Select(static item => item.Name))}.");
        }

        return lines;
    }

    private static string NormalizeAftermathPackageKind(string? packageKind)
        => NormalizeOptional(packageKind)?.ToLowerInvariant() switch
        {
            "session_recap" => "session_recap",
            "session_replay" => "replay_timeline",
            "replay_timeline" => "replay_timeline",
            "after_action_report" => "after_action_report",
            "downtime_brief" => "downtime_brief",
            null => throw new InvalidOperationException("aftermath package kind is required."),
            _ => throw new InvalidOperationException($"Unsupported aftermath package kind: {packageKind}")
        };

    private static string BuildAftermathPackageTitle(
        CampaignWorkspaceProjection workspace,
        RunProjection? run,
        string packageKind,
        string? requestedTitle)
    {
        string? normalizedTitle = NormalizeOptional(requestedTitle);
        if (normalizedTitle is not null)
        {
            return normalizedTitle;
        }

        string runTitle = run?.Title ?? workspace.CampaignName;
        return packageKind switch
        {
            "replay_timeline" => $"{runTitle} replay timeline",
            "after_action_report" => $"{runTitle} after-action report",
            "downtime_brief" => $"{workspace.CampaignName} downtime brief",
            _ => $"{runTitle} session recap"
        };
    }

    private static string BuildAftermathPackageSummary(
        CampaignWorkspaceProjection workspace,
        RunProjection? run,
        string packageKind)
    {
        int openObjectiveCount = run?.Objectives.Count(item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase) && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase)) ?? 0;
        int consequenceCount = workspace.Consequences?.Count ?? 0;
        string subject = run?.Title ?? workspace.CampaignName;
        return packageKind switch
        {
            "replay_timeline" => $"Generated a replay timeline for {subject} so contested turns, continuity, and consequence carry-forward stay reviewable on the same governed package.",
            "after_action_report" => $"Generated an after-action report for {subject} with {openObjectiveCount} open objective(s) and {consequenceCount} consequence signal(s) carried into the shared return lane.",
            "downtime_brief" => $"Generated a downtime brief for {workspace.CampaignName} so the next session return keeps aftermath, carry-forward obligations, and publication-safe continuity in one packet.",
            _ => $"Generated a session recap package for {subject} with {openObjectiveCount} open objective(s) and {consequenceCount} consequence signal(s) pinned for safe return and creator follow-through."
        };
    }

    private static IReadOnlyList<string> BuildAftermathPackageEvidenceLines(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        RunProjection? run,
        string packageKind,
        string? note)
    {
        SceneProjection? activeScene = run is null
            ? null
            : run.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, run.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
              ?? run.Scenes.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();
        int openObjectiveCount = run?.Objectives.Count(item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase) && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase)) ?? 0;
        return new[]
        {
            $"Package kind: {packageKind}.",
            $"Campaign: {workspace.CampaignName}.",
            run is null ? "Run scope: campaign-wide aftermath." : $"Run scope: {run.Title} ({run.Status}).",
            activeScene is null ? "Active scene: no pinned scene." : $"Active scene: {activeScene.Title} ({activeScene.Revision}).",
            $"Open objectives: {openObjectiveCount}.",
            $"Continuity: {workspace.LatestContinuity?.Summary ?? workspace.ReturnSummary}.",
            packageKind == "replay_timeline"
                ? "Replay posture: governed contested-turn review stays attached to the same campaign return lane."
                : string.Empty,
            $"Governed prep launches: {workspace.PrepLaunches?.Count ?? 0}.",
            $"Travel prefetch receipts: {workspace.TravelPrefetches?.Count ?? 0}.",
            $"Restore artifacts in scope: {restore.RecentArtifacts.Count}.",
            string.IsNullOrWhiteSpace(note) ? string.Empty : $"Operator note: {note.Trim()}."
        }
        .Where(static item => !string.IsNullOrWhiteSpace(item))
        .Take(8)
        .ToArray();
    }

    private static bool IsTravelReadyDevice(ClaimedDeviceRestoreProjection device)
        => string.Equals(device.DeviceRole, "travel_cache", StringComparison.OrdinalIgnoreCase)
            || string.Equals(device.DeviceRole, "play_tablet", StringComparison.OrdinalIgnoreCase)
            || device.RestoreSummary.Contains("bounded offline use", StringComparison.OrdinalIgnoreCase)
            || device.RestoreSummary.Contains("prefetch", StringComparison.OrdinalIgnoreCase);

    private static string ResolveTravelDeviceStatus(ClaimedDeviceRestoreProjection device, bool hasConflicts)
    {
        if (hasConflicts)
        {
            return "attention";
        }

        return IsTravelReadyDevice(device) ? "ready" : "review";
    }

    private static IReadOnlyList<SupportCaseProjection> SelectRelevantSupportCases(
        IReadOnlyList<SupportCaseProjection> supportCases,
        InstallLinkingSummaryDto? installLinking)
    {
        if (supportCases.Count == 0)
        {
            return Array.Empty<SupportCaseProjection>();
        }

        var installations = installLinking?.ClaimedInstallations ?? Array.Empty<ClaimedInstallationDto>();
        HashSet<string> installationIds = installations
            .Select(static item => item.InstallationId)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        HashSet<string> channels = installations
            .Select(static item => item.Channel)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        HashSet<string> heads = installations
            .Select(static item => item.HeadId)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item!)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        HashSet<string> platforms = installations
            .Select(static item => item.Platform)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item!)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        SupportCaseProjection[] matched = supportCases
            .Where(item =>
                installationIds.Contains(item.InstallationId ?? string.Empty)
                || channels.Contains(item.ReleaseChannel ?? string.Empty)
                || heads.Contains(item.HeadId ?? string.Empty)
                || platforms.Contains(item.Platform ?? string.Empty))
            .Take(4)
            .ToArray();

        return matched.Length > 0 ? matched : supportCases.Take(4).ToArray();
    }

    private static bool NeedsAttention(string? severity)
        => !string.IsNullOrWhiteSpace(severity)
           && !severity.Equals("healthy", StringComparison.OrdinalIgnoreCase)
           && !severity.Equals("info", StringComparison.OrdinalIgnoreCase)
           && !severity.Equals("ok", StringComparison.OrdinalIgnoreCase)
           && !severity.Equals("ready", StringComparison.OrdinalIgnoreCase);

    private static string DescribeDeviceRoleSummary(WorkspaceRestoreProjection restore)
        => restore.ClaimedDevices.Count == 0
            ? "No claimed device role is attached yet."
            : string.Join(
                "; ",
                restore.ClaimedDevices
                    .Take(2)
                    .Select(static item => $"{item.DeviceRole} on {item.Platform}/{item.HeadId} ({item.Channel})"));

    private static string DescribeRestorePrefetchSummary(WorkspaceRestoreProjection restore)
    {
        string inventory = DescribeRestorePrefetchInventory(
            restore.RecentDossiers.Count,
            restore.RecentCampaigns.Count,
            restore.RecentRuleEnvironments.Count,
            restore.RecentArtifacts.Count);
        return restore.ClaimedDevices.Count == 0
            ? $"Prefetch inventory: {inventory} are attached to the restore packet, but no claimed-device return lane is linked yet."
            : $"Prefetch inventory: {inventory} are staged for bounded offline use across {restore.ClaimedDevices.Count} claimed device(s).";
    }

    private static string DescribeRestorePrefetchInventory(
        int dossierCount,
        int campaignCount,
        int ruleEnvironmentCount,
        int artifactCount)
        => $"{dossierCount} dossier(s), {campaignCount} campaign(s), {ruleEnvironmentCount} rule snapshot(s), and {artifactCount} reconnectable artifact(s)";

    private static string ResolveDeviceRole(ClaimedInstallationDto installation)
    {
        if (string.Equals(installation.Platform, "android", StringComparison.OrdinalIgnoreCase)
            || string.Equals(installation.Platform, "ios", StringComparison.OrdinalIgnoreCase))
        {
            return "play_tablet";
        }

        if ((installation.HeadId?.Contains("observer", StringComparison.OrdinalIgnoreCase) ?? false)
            || (installation.HostLabel?.Contains("observer", StringComparison.OrdinalIgnoreCase) ?? false))
        {
            return "observer_screen";
        }

        if (string.Equals(installation.Channel, "preview", StringComparison.OrdinalIgnoreCase))
        {
            return "preview_scout";
        }

        if (string.Equals(installation.HeadId, "offline", StringComparison.OrdinalIgnoreCase))
        {
            return "travel_cache";
        }

        return "workstation";
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string StableCueId(string value)
    {
        string normalized = value.Trim().ToLowerInvariant();
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(normalized)))[..12].ToLowerInvariant();
    }
}
