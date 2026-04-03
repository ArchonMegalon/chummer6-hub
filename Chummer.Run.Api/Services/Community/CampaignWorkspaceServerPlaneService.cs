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

        if (BuildEventControlPrepPacket(workspace, leadRun) is { } eventControlPacket)
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
        string? normalizedActiveSceneSummary = NormalizeOptional(activeScene?.Summary);
        string? normalizedWorkspaceSceneSummary = NormalizeOptional(workspace.ActiveSceneSummary);
        ObjectiveProjection? leadObjective = leadRun?.Objectives.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();
        string? normalizedObjectiveSummary = NormalizeOptional(leadObjective?.Summary);
        string? normalizedLeadRunTitle = NormalizeOptional(leadRun?.Title);
        string? normalizedSceneTitle = NormalizeOptional(activeScene?.Title);
        string? normalizedObjectiveTitle = NormalizeOptional(leadObjective?.Title);

        if (activeScene is null && normalizedWorkspaceSceneSummary is null)
        {
            return null;
        }

        string sceneTitle = normalizedSceneTitle ?? "Active scene";
        string title = $"{sceneTitle} scene packet";
        IReadOnlyList<string> evidence = BuildEvidenceLines(
            normalizedActiveSceneSummary,
            normalizedWorkspaceSceneSummary,
            normalizedSceneTitle,
            normalizedObjectiveSummary,
            normalizedObjectiveTitle,
            workspace.RuleEnvironment.CompatibilityFingerprint);
        string summary = normalizedActiveSceneSummary
            ?? normalizedWorkspaceSceneSummary
            ?? (normalizedSceneTitle is null
                ? "Current scene prep is compiled from the shared campaign return lane."
                : $"{normalizedSceneTitle} scene prep is compiled from the shared campaign return lane.");
        string bindingSummary = leadRun is null
            ? $"Bound to {workspace.CampaignName} from the current shared return lane."
            : activeScene is null
                ? $"Bound to {normalizedLeadRunTitle ?? "active run"} from the current shared return lane."
                : $"Bound to {normalizedLeadRunTitle ?? "active run"} / {sceneTitle} on {workspace.RuleEnvironment.CompatibilityFingerprint}.";

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
        WorkspaceChangePacketProjection[] oppositionSignals = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsOppositionSignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        CampaignConsequenceProjection[] consequences = (workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>())
            .Where(static consequence => IsOppositionConsequenceSignal(consequence))
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
        if (oppositionSignals.Length == 0
            && consequences.Length == 0
            && objectiveSignals.Length == 0
            && string.IsNullOrWhiteSpace(activeScene?.Summary))
        {
            return null;
        }

        string labels = string.Join(", ",
            oppositionSignals
                .Select(static item => DescribeSignalLabel(item.Label, item.Kind, "opposition signal"))
                .Concat(consequences.Select(static item => DescribeSignalLabel(item.Label, item.Kind, item.State)))
                .Concat(objectiveSignals.Select(static item => DescribeSignalLabel(item.Title, item.Status, "run pressure")))
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .Distinct(StringComparer.OrdinalIgnoreCase));
        if (string.IsNullOrWhiteSpace(labels))
        {
            labels = "governed opposition cues";
        }
        int signalCount = oppositionSignals.Length + consequences.Length + objectiveSignals.Length + (string.IsNullOrWhiteSpace(activeScene?.Summary) ? 0 : 1);
        string summary = consequences.Length > 0 || oppositionSignals.Length > 0
            ? $"{signalCount} governed opposition signal(s) are active: {labels}."
            : $"{signalCount} governed opposition signal(s) are active from run pressure and active-scene cues: {labels}.";
        IReadOnlyList<string> evidence = BuildEvidenceLines(
            oppositionSignals.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "opposition signal")),
            consequences.Select(static item => DescribeSignalLabel(item.Label, item.Kind, item.State)),
            oppositionSignals.Select(static item => item.Summary),
            oppositionSignals.Select(static item => item.Label),
            consequences.Select(static item => item.Summary),
            consequences.Select(static item => item.Label),
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
                oppositionSignals.Select(static item => item.Kind),
                oppositionSignals.Select(static item => item.Label),
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
                .Concat(oppositionSignals.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
                .Concat(consequences.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
                .Concat(objectiveSignals.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
                .Where(static item => item.HasValue)
                .Select(static item => item!.Value)
                .DefaultIfEmpty(DateTimeOffset.UtcNow)
                .Max());
    }

    private static GovernedPrepPacketSummary? BuildContinuityPrepPacket(CampaignWorkspaceProjection workspace)
    {
        WorkspaceChangePacketProjection[] continuitySignals = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsContinuitySignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();

        if (workspace.LatestContinuity is null
            && workspace.RecapShelf.Count == 0
            && workspace.Dossiers.Count == 0
            && continuitySignals.Length == 0
            && workspace.NextSessionCarryForward is null)
        {
            return null;
        }

        IReadOnlyList<string> evidence = BuildEvidenceLines(
            continuitySignals.Select(static packet => DescribeSignalLabel(packet.Label, packet.Kind, "continuity signal")),
            workspace.RecapShelf.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "continuity signal")),
            workspace.LatestContinuity?.Summary,
            workspace.NextSessionCarryForward?.Label,
            workspace.NextSessionCarryForward?.Summary,
            workspace.NextSessionCarryForward?.ReturnSummary,
            workspace.NextSessionCarryForward?.NextSafeAction,
            continuitySignals.Select(static packet => packet.Summary),
            continuitySignals.Select(static packet => packet.Label),
            workspace.RecapShelf.Select(static item => item.Summary),
            workspace.RecapShelf.Select(static item => item.Label),
            workspace.Dossiers.Select(static item => item.LatestContinuity?.Summary));
        int continuitySignalCount = (workspace.LatestContinuity is null ? 0 : 1)
            + workspace.RecapShelf.Count
            + workspace.Dossiers.Count
            + continuitySignals.Length
            + (workspace.NextSessionCarryForward is null ? 0 : 1);
        string summary = workspace.RecapShelf.Count == 0 && workspace.LatestContinuity is null
            ? $"{Math.Max(1, continuitySignalCount)} continuity signal(s) stay attached to the shared return lane even before recap-safe output is published."
            : $"{workspace.RecapShelf.Count} recap-safe output(s) stay attached to the same shared continuity spine.";
        DateTimeOffset updatedAtUtc = new[]
            {
                workspace.LatestContinuity?.CapturedAtUtc,
                workspace.NextSessionCarryForward?.UpdatedAtUtc
            }
            .Concat(continuitySignals.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"continuity:{workspace.WorkspaceId}",
            Kind: "continuity_packet",
            Title: $"{workspace.CampaignName} continuity handoff",
            Summary: summary,
            BindingSummary: "Bound to the same continuity snapshot that reopens dossiers, recaps, and publication-safe follow-through.",
            Reusable: false,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                workspace.ReturnSummary,
                workspace.LatestContinuity?.Summary,
                workspace.NextSessionCarryForward?.Label,
                workspace.NextSessionCarryForward?.Summary,
                workspace.RecapShelf.Select(static item => item.Label),
                workspace.RecapShelf.Select(static item => item.Kind),
                workspace.Dossiers.Select(static item => item.RunnerHandle),
                continuitySignals.Select(static packet => packet.Kind),
                continuitySignals.Select(static packet => packet.Label)),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static bool IsContinuitySignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        return string.Equals(normalizedKind, "continuity", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "next_session_carry_forward", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "after_action_report", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "downtime_brief", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("continuity", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("carry_forward", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsContinuitySignal(WorkspaceChangePacketProjection packet)
    {
        return IsContinuitySignalKind(packet.Kind)
            || IsContinuitySignalKind(packet.Label)
            || IsContinuitySignalKind(packet.Summary)
            || ContainsCampaignReturnRecapToken(packet.Label)
            || ContainsCampaignReturnRecapToken(packet.Summary);
    }

    private static GovernedPrepPacketSummary? BuildCampaignReturnPrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        PublicationSafeProjection[] diaryRecaps = workspace.RecapShelf
            .Where(static item => IsCampaignReturnRecapSignal(item))
            .Take(4)
            .ToArray();
        AftermathRecapPackageProjection[] aftermathPackages = (workspace.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>())
            .OrderByDescending(static item => item.GeneratedAtUtc)
            .Take(4)
            .ToArray();
        CampaignConsequenceProjection[] relationshipConsequences = (workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>())
            .Where(static consequence => IsCampaignRelationshipConsequenceSignal(consequence))
            .OrderByDescending(static consequence => consequence.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        WorkspaceChangePacketProjection[] returnChanges = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsCampaignReturnSignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        WorkspaceChangePacketProjection[] aftermathChanges = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsAftermathSignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();

        if (diaryRecaps.Length == 0
            && aftermathPackages.Length == 0
            && relationshipConsequences.Length == 0
            && returnChanges.Length == 0
            && aftermathChanges.Length == 0
            && workspace.NextSessionCarryForward is null)
        {
            return null;
        }

        int diarySignalCount = diaryRecaps.Length + returnChanges.Length + aftermathPackages.Length + aftermathChanges.Length;
        int relationshipSignalCount = relationshipConsequences.Length
            + returnChanges.Count(static packet => IsCampaignRelationshipSignal(packet))
            + aftermathChanges.Count(static packet => IsCampaignRelationshipSignal(packet));
        string summary = $"{Math.Max(1, diarySignalCount)} diary/continuity signal(s) and {relationshipSignalCount} relationship signal(s) stay on one governed return lane for downtime and next-session reopen.";
        string bindingSummary = leadRun is null
            ? "Diary updates, contacts, heat, and return cues stay attached to the same campaign truth without local note-shadow models."
            : $"{leadRun.Title} and campaign return cues share the same diary/contact/heat continuity lane.";
        IReadOnlyList<string> evidence = BuildEvidenceLines(
            returnChanges.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "return signal")),
            aftermathChanges.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "aftermath signal")),
            relationshipConsequences.Select(static item => DescribeSignalLabel(item.Label, item.Kind, item.State)),
            diaryRecaps.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "diary signal")),
            aftermathPackages.Select(static item => DescribeSignalLabel(item.Title, item.PackageKind, "aftermath package")),
            relationshipConsequences.SelectMany(static item => item.EvidenceLines),
            relationshipConsequences.SelectMany(static item => item.Receipts.Select(static receipt => receipt.Summary)),
            returnChanges.Select(static item => item.Summary),
            returnChanges.Select(static item => item.Label),
            aftermathChanges.Select(static item => item.Summary),
            aftermathChanges.Select(static item => item.Label),
            diaryRecaps.Select(static item => item.Summary),
            diaryRecaps.Select(static item => item.Label),
            aftermathPackages.Select(static item => item.Summary),
            aftermathPackages.SelectMany(static item => item.EvidenceLines),
            relationshipConsequences.Select(static item => item.Summary),
            relationshipConsequences.Select(static item => item.Label),
            workspace.ReturnSummary,
            workspace.NextSessionCarryForward?.Label,
            workspace.NextSessionCarryForward?.Summary,
            workspace.NextSessionCarryForward?.ReturnSummary,
            workspace.NextSessionCarryForward?.NextSafeAction);
        DateTimeOffset updatedAtUtc = new[]
            {
                workspace.LatestContinuity?.CapturedAtUtc,
                workspace.NextSessionCarryForward?.UpdatedAtUtc
            }
            .Concat(returnChanges.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Concat(aftermathChanges.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Concat(relationshipConsequences.Select(static consequence => (DateTimeOffset?)consequence.UpdatedAtUtc))
            .Concat(aftermathPackages.Select(static package => (DateTimeOffset?)package.GeneratedAtUtc))
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
                "aftermath",
                "return",
                workspace.ReturnSummary,
                workspace.NextSessionCarryForward?.Label,
                workspace.NextSessionCarryForward?.NextSafeAction,
                diaryRecaps.Select(static item => item.Kind),
                diaryRecaps.Select(static item => item.Label),
                aftermathPackages.Select(static item => item.PackageKind),
                aftermathPackages.Select(static item => item.Title),
                aftermathPackages.Select(static item => item.RunTitle),
                returnChanges.Select(static item => item.Kind),
                returnChanges.Select(static item => item.Label),
                aftermathChanges.Select(static item => item.Kind),
                aftermathChanges.Select(static item => item.Label),
                relationshipConsequences.Select(static item => item.Kind),
                relationshipConsequences.Select(static item => item.Label),
                relationshipConsequences.Select(static item => item.State),
                relationshipConsequences.SelectMany(static item => item.Receipts.Select(static receipt => receipt.SourceKind))),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static bool IsCampaignReturnSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "campaign_return", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "return_loop", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "return_window", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "next_session_return", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        bool containsReturnLaneToken = normalizedKind.Contains("return", StringComparison.OrdinalIgnoreCase)
            && (normalizedKind.Contains("campaign", StringComparison.OrdinalIgnoreCase)
                || normalizedKind.Contains("session", StringComparison.OrdinalIgnoreCase)
                || normalizedKind.Contains("loop", StringComparison.OrdinalIgnoreCase)
                || normalizedKind.Contains("window", StringComparison.OrdinalIgnoreCase));
        if (containsReturnLaneToken)
        {
            return true;
        }

        return IsContinuitySignalKind(normalizedKind)
            || IsDiarySignalKind(normalizedKind)
            || IsCampaignRelationshipSignalKind(normalizedKind);
    }

    private static bool IsCampaignReturnSignal(WorkspaceChangePacketProjection packet)
    {
        return IsCampaignReturnSignalKind(packet.Kind)
            || IsCampaignReturnSignalKind(packet.Label)
            || IsCampaignReturnSignalKind(packet.Summary)
            || ContainsCampaignReturnRecapToken(packet.Label)
            || ContainsCampaignReturnRecapToken(packet.Summary)
            || IsDiarySignalKind(packet.Label)
            || IsDiarySignalKind(packet.Summary)
            || IsCampaignRelationshipSignal(packet);
    }

    private static bool IsDiarySignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "diary_update", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "journal_update", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "session_log_update", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        bool hasDiaryToken = normalizedKind.Contains("diary", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("journal", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("session_log", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("sessionlog", StringComparison.OrdinalIgnoreCase);
        bool hasMutationToken = normalizedKind.Contains("update", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("change", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("entry", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("note", StringComparison.OrdinalIgnoreCase);
        return hasDiaryToken && hasMutationToken;
    }

    private static bool IsCampaignReturnRecapSignal(PublicationSafeProjection item)
    {
        string kind = item.Kind.Trim();
        if (kind.Contains("diary", StringComparison.OrdinalIgnoreCase)
            || kind.Contains("downtime", StringComparison.OrdinalIgnoreCase)
            || kind.Contains("recap", StringComparison.OrdinalIgnoreCase)
            || kind.Contains("after_action", StringComparison.OrdinalIgnoreCase)
            || kind.Contains("career", StringComparison.OrdinalIgnoreCase)
            || kind.Contains("log", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return ContainsCampaignReturnRecapToken(item.Label)
            || ContainsCampaignReturnRecapToken(item.Summary);
    }

    private static bool ContainsCampaignReturnRecapToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("diary", StringComparison.OrdinalIgnoreCase)
            || value.Contains("downtime", StringComparison.OrdinalIgnoreCase)
            || value.Contains("recap", StringComparison.OrdinalIgnoreCase)
            || value.Contains("after action", StringComparison.OrdinalIgnoreCase)
            || value.Contains("after-action", StringComparison.OrdinalIgnoreCase)
            || value.Contains("career", StringComparison.OrdinalIgnoreCase)
            || value.Contains("log", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsCampaignRelationshipSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "contact_update", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "heat_update", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "reputation_update", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "faction_update", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return ContainsCampaignRelationshipToken(normalizedKind)
            && ContainsCampaignRelationshipMutationToken(normalizedKind);
    }

    private static bool IsCampaignRelationshipSignal(WorkspaceChangePacketProjection packet)
    {
        return IsCampaignRelationshipSignalKind(packet.Kind)
            || IsCampaignRelationshipSignalKind(packet.Label)
            || IsCampaignRelationshipSignalKind(packet.Summary)
            || ContainsCampaignRelationshipSplitTokenSignal(packet.Kind, packet.Label, packet.Summary);
    }

    private static bool ContainsCampaignRelationshipSplitTokenSignal(string? kind, string? label, string? summary)
    {
        string combined = string.Join(' ', new[] { kind, label, summary }.Where(static value => !string.IsNullOrWhiteSpace(value)));
        if (string.IsNullOrWhiteSpace(combined))
        {
            return false;
        }

        return ContainsCampaignRelationshipToken(combined)
            && ContainsCampaignRelationshipMutationToken(combined);
    }

    private static bool ContainsCampaignRelationshipToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("contact", StringComparison.OrdinalIgnoreCase)
            || value.Contains("heat", StringComparison.OrdinalIgnoreCase)
            || value.Contains("reputation", StringComparison.OrdinalIgnoreCase)
            || value.Contains("faction", StringComparison.OrdinalIgnoreCase);
    }

    private static bool ContainsCampaignRelationshipMutationToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("update", StringComparison.OrdinalIgnoreCase)
            || value.Contains("change", StringComparison.OrdinalIgnoreCase)
            || value.Contains("shift", StringComparison.OrdinalIgnoreCase)
            || value.Contains("delta", StringComparison.OrdinalIgnoreCase)
            || value.Contains("pressure", StringComparison.OrdinalIgnoreCase)
            || value.Contains("lane", StringComparison.OrdinalIgnoreCase)
            || value.Contains("window", StringComparison.OrdinalIgnoreCase)
            || value.Contains("state", StringComparison.OrdinalIgnoreCase)
            || value.Contains("status", StringComparison.OrdinalIgnoreCase)
            || value.Contains("fallout", StringComparison.OrdinalIgnoreCase)
            || value.Contains("escalat", StringComparison.OrdinalIgnoreCase)
            || value.Contains("spike", StringComparison.OrdinalIgnoreCase)
            || value.Contains("surge", StringComparison.OrdinalIgnoreCase)
            || value.Contains("cooldown", StringComparison.OrdinalIgnoreCase)
            || value.Contains("cooling", StringComparison.OrdinalIgnoreCase)
            || value.Contains("decline", StringComparison.OrdinalIgnoreCase)
            || value.Contains("drop", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsCampaignRelationshipConsequenceKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (IsCampaignRelationshipSignalKind(normalizedKind))
        {
            return true;
        }

        return normalizedKind.Contains("contact", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("heat", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("reputation", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("faction", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsCampaignRelationshipConsequenceSignal(CampaignConsequenceProjection consequence)
    {
        return IsCampaignRelationshipConsequenceKind(consequence.Kind)
            || ContainsCampaignRelationshipSplitTokenSignal(consequence.Kind, consequence.Label, consequence.Summary)
            || ContainsCampaignRelationshipSplitTokenSignal(consequence.Kind, consequence.Label, consequence.State)
            || consequence.EvidenceLines.Any(static line =>
                ContainsCampaignRelationshipToken(line) && ContainsCampaignRelationshipMutationToken(line))
            || consequence.Receipts.Any(static receipt =>
                ContainsCampaignRelationshipSplitTokenSignal(receipt.SourceKind, receipt.Summary, null));
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
            .Where(static packet => IsRosterMovementSignal(packet))
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

        IReadOnlyList<string> evidence = BuildEvidenceLines(
            rosterChangeSignals.Select(static packet => DescribeSignalLabel(packet.Label, packet.Kind, "roster movement signal")),
            transfers.Select(DescribeRosterTransferEvidence),
            carryForwardRosterSignal
                ? BuildEvidenceLines(
                    workspace.NextSessionCarryForward?.Label,
                    workspace.NextSessionCarryForward?.Summary,
                    workspace.NextSessionCarryForward?.ReturnSummary,
                    workspace.NextSessionCarryForward?.NextSafeAction)
                : Array.Empty<string>(),
            rosterObjectives.Select(static objective => DescribeSignalLabel(objective.Title, objective.Status, "roster objective")),
            rosterChangeSignals.Select(static packet => packet.Summary),
            rosterChangeSignals.Select(static packet => packet.Label),
            rosterObjectives.Select(static objective => objective.Summary),
            rosterObjectives.Select(static objective => $"{objective.Title} stays {objective.Status} with {objective.Pressure} pressure."),
            transfers.SelectMany(static item => item.AuditLines));
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

    private static bool IsRosterMovementSignal(WorkspaceChangePacketProjection packet)
    {
        return IsRosterMovementSignalKind(packet.Kind)
            || IsRosterMovementSignalKind(packet.Label)
            || IsRosterMovementSignalKind(packet.Summary)
            || ContainsRosterToken(packet.Label)
            || ContainsRosterToken(packet.Summary);
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

        bool hasRosterIdentityToken = value.Contains("roster", StringComparison.OrdinalIgnoreCase)
            || value.Contains("crew", StringComparison.OrdinalIgnoreCase);
        if (hasRosterIdentityToken)
        {
            return true;
        }

        bool hasBenchRotationPair = value.Contains("bench", StringComparison.OrdinalIgnoreCase)
            && value.Contains("rotation", StringComparison.OrdinalIgnoreCase);
        return hasBenchRotationPair;
    }

    private static GovernedPrepPacketSummary? BuildAftermathPrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        AftermathRecapPackageProjection[] packages = (workspace.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>())
            .OrderByDescending(static item => item.GeneratedAtUtc)
            .Take(3)
            .ToArray();
        PublicationSafeProjection[] recapSignals = workspace.RecapShelf
            .Where(static item => IsAftermathRecapSignal(item))
            .Take(4)
            .ToArray();
        WorkspaceChangePacketProjection[] aftermathSignals = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsAftermathSignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        if (packages.Length == 0 && recapSignals.Length == 0 && aftermathSignals.Length == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = BuildEvidenceLines(
            recapSignals.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "aftermath signal")),
            aftermathSignals.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "aftermath signal")),
            packages.Select(static item => DescribeSignalLabel(item.Title, item.PackageKind, "aftermath package")),
            recapSignals.Select(static item => item.Summary),
            recapSignals.Select(static item => item.Label),
            aftermathSignals.Select(static item => item.Summary),
            aftermathSignals.Select(static item => item.Label),
            packages.Select(static item => item.Summary),
            packages.Select(static item => item.Title),
            packages.SelectMany(static item => item.EvidenceLines));
        int signalCount = packages.Length + recapSignals.Length + aftermathSignals.Length;
        string summary = packages.Length > 0
            ? $"{signalCount} aftermath or downtime signal(s) stay attached for recap, recovery, and next-session return."
            : $"{signalCount} aftermath or downtime signal(s) stay governed from recap/change signals while package receipts catch up.";
        DateTimeOffset updatedAtUtc = new[]
            {
                leadRun?.UpdatedAtUtc,
                workspace.LatestContinuity?.CapturedAtUtc,
                workspace.NextSessionCarryForward?.UpdatedAtUtc
            }
            .Concat(packages.Select(static item => (DateTimeOffset?)item.GeneratedAtUtc))
            .Concat(aftermathSignals.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"aftermath:{workspace.WorkspaceId}",
            Kind: "aftermath_packet",
            Title: $"{workspace.CampaignName} aftermath and downtime packet",
            Summary: summary,
            BindingSummary: leadRun is null
                ? "Reusable across the campaign so aftermath, downtime, and return stay on governed workspace truth."
                : $"Reusable across {workspace.CampaignName} and currently anchored to {leadRun.Title} for return-loop continuity.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "aftermath",
                "downtime",
                "recap",
                packages.Select(static item => item.PackageKind),
                packages.Select(static item => item.Title),
                packages.Select(static item => item.RunTitle),
                packages.Select(static item => item.ArtifactId),
                recapSignals.Select(static item => item.Kind),
                recapSignals.Select(static item => item.Label),
                aftermathSignals.Select(static packet => packet.Kind),
                aftermathSignals.Select(static packet => packet.Label)),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static bool IsAftermathSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "aftermath", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "downtime", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "downtime_brief", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "after_action_report", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return normalizedKind.Contains("aftermath", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("downtime", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("after_action", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("recap", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("debrief", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsAftermathSignal(WorkspaceChangePacketProjection packet)
    {
        return IsAftermathSignalKind(packet.Kind)
            || ContainsAftermathRecapToken(packet.Label)
            || ContainsAftermathRecapToken(packet.Summary);
    }

    private static bool IsAftermathRecapSignal(PublicationSafeProjection item)
    {
        if (IsAftermathSignalKind(item.Kind))
        {
            return true;
        }

        return ContainsAftermathRecapToken(item.Label)
            || ContainsAftermathRecapToken(item.Summary);
    }

    private static bool ContainsAftermathRecapToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("aftermath", StringComparison.OrdinalIgnoreCase)
            || value.Contains("downtime", StringComparison.OrdinalIgnoreCase)
            || value.Contains("after action", StringComparison.OrdinalIgnoreCase)
            || value.Contains("after-action", StringComparison.OrdinalIgnoreCase)
            || value.Contains("recap", StringComparison.OrdinalIgnoreCase)
            || value.Contains("debrief", StringComparison.OrdinalIgnoreCase);
    }

    private static GovernedPrepPacketSummary? BuildPrepLaunchOpsPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        GovernedPrepLaunchProjection[] launches = (workspace.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>())
            .OrderByDescending(static item => item.LaunchedAtUtc)
            .Take(4)
            .ToArray();
        WorkspaceChangePacketProjection[] launchSignals = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsPrepLaunchSignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        if (launches.Length == 0 && launchSignals.Length == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = BuildEvidenceLines(
            launchSignals.Select(static packet => DescribeSignalLabel(packet.Label, packet.Kind, "prep launch signal")),
            launches.Select(DescribePrepLaunchEvidence),
            launches.Select(static item => item.PacketTitle),
            launchSignals.Select(static packet => packet.Summary),
            launchSignals.Select(static packet => packet.Label),
            launches.SelectMany(static item => item.AuditLines));
        int signalCount = launches.Length + launchSignals.Length;
        string summary = launches.Length > 0
            ? $"{signalCount} prep-launch signal(s) keep packet launches auditable on the same campaign lane."
            : $"{signalCount} prep-launch signal(s) stay governed from prep-launch change packets while launch receipts catch up.";
        DateTimeOffset updatedAtUtc = new[]
            {
                leadRun?.UpdatedAtUtc
            }
            .Concat(launches.Select(static item => (DateTimeOffset?)item.LaunchedAtUtc))
            .Concat(launchSignals.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"prep-launch:{workspace.WorkspaceId}",
            Kind: "prep_launch_packet",
            Title: $"{workspace.CampaignName} governed prep launches",
            Summary: summary,
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
                launches.Select(static item => item.InitiatedByUserId),
                launchSignals.Select(static item => item.Kind),
                launchSignals.Select(static item => item.Label)),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static bool IsPrepLaunchSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "prep_launch", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "prep_packet_launch", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return normalizedKind.Contains("prep", StringComparison.OrdinalIgnoreCase)
            && normalizedKind.Contains("launch", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsPrepLaunchSignal(WorkspaceChangePacketProjection packet)
    {
        return IsPrepLaunchSignalKind(packet.Kind)
            || ContainsPrepLaunchToken(packet.Label)
            || ContainsPrepLaunchToken(packet.Summary)
            || ContainsPrepLaunchToken(packet.Label, packet.Summary);
    }

    private static bool ContainsPrepLaunchToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("prep", StringComparison.OrdinalIgnoreCase)
            && value.Contains("launch", StringComparison.OrdinalIgnoreCase);
    }

    private static bool ContainsPrepLaunchToken(string? primary, string? secondary)
    {
        if (string.IsNullOrWhiteSpace(primary) && string.IsNullOrWhiteSpace(secondary))
        {
            return false;
        }

        string combined = $"{primary} {secondary}";
        return ContainsPrepLaunchToken(combined);
    }

    private static GovernedPrepPacketSummary? BuildEventControlPrepPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        WorkspaceChangePacketProjection[] eventPackets = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsEventControlSignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        CampaignConsequenceProjection[] consequences = (workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>())
            .Where(static consequence => IsCampaignRelationshipConsequenceSignal(consequence))
            .OrderByDescending(static consequence => consequence.UpdatedAtUtc)
            .Take(3)
            .ToArray();
        RosterTransferProjection[] rosterTransfers = (workspace.RosterTransfers ?? Array.Empty<RosterTransferProjection>())
            .OrderByDescending(static transfer => transfer.TransferredAtUtc)
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
        ObjectiveProjection[] eventObjectives = (leadRun?.Objectives ?? Array.Empty<ObjectiveProjection>())
            .Where(static objective => IsEventControlObjectiveSignal(objective.Title, objective.Summary))
            .OrderByDescending(static objective => objective.UpdatedAtUtc)
            .Take(3)
            .ToArray();
        SceneProjection? activeScene = leadRun?.Scenes
            .FirstOrDefault(item => string.Equals(item.SceneId, leadRun.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
            ?? leadRun?.Scenes.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();
        bool sceneSignal = IsEventControlObjectiveSignal(activeScene?.Title, activeScene?.Summary);

        NextSessionCarryForwardProjection? carryForward = workspace.NextSessionCarryForward;
        bool carryForwardSignal = IsEventControlCarryForwardSignal(carryForward);
        if (eventPackets.Length == 0
            && consequences.Length == 0
            && rosterTransfers.Length == 0
            && prepLaunches.Length == 0
            && travelPrefetches.Length == 0
            && eventObjectives.Length == 0
            && !sceneSignal
            && !carryForwardSignal)
        {
            return null;
        }

        int eventCount = eventPackets.Length
            + consequences.Length
            + rosterTransfers.Length
            + prepLaunches.Length
            + travelPrefetches.Length
            + eventObjectives.Length
            + (sceneSignal ? 1 : 0)
            + (carryForwardSignal ? 1 : 0);
        string consequenceLabels = string.Join(", ",
            consequences
                .Select(static item => DescribeSignalLabel(item.Label, item.Kind, item.State))
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .Distinct(StringComparer.OrdinalIgnoreCase));
        string consequenceSummary = consequences.Length == 0
            ? "Heat, contacts, and consequence posture stay linked to the same campaign return lane."
            : string.IsNullOrWhiteSpace(consequenceLabels)
                ? $"{consequences.Length} consequence signal(s) stay attached to event control."
                : $"{consequences.Length} consequence signal(s) ({consequenceLabels}) stay attached to event control.";
        string sourceSummary = eventPackets.Length == 0
            && prepLaunches.Length == 0
            && travelPrefetches.Length == 0
            && eventObjectives.Length > 0
            ? " Event/season controls are currently driven by run-pressure signals while receipt streams catch up."
            : string.Empty;
        IReadOnlyList<string> evidence = BuildEvidenceLines(
            consequences.Select(static consequence => DescribeSignalLabel(consequence.Label, consequence.Kind, consequence.State)),
            rosterTransfers.Select(DescribeRosterTransferEvidence),
            consequences.Select(static consequence => consequence.Summary),
            consequences.Select(static consequence => consequence.Label),
            consequences.SelectMany(static consequence => consequence.EvidenceLines),
            consequences.SelectMany(static consequence => consequence.Receipts.Select(static receipt => receipt.Summary)),
            eventPackets.Select(static packet => DescribeSignalLabel(packet.Label, packet.Kind, "event control signal")),
            eventPackets.Select(static packet => packet.Summary),
            eventPackets.Select(static packet => packet.Label),
            eventObjectives.Select(static objective => objective.Summary),
            eventObjectives.Select(static objective => $"{objective.Title} stays {objective.Status} with {objective.Pressure} pressure."),
            sceneSignal ? activeScene?.Summary : null,
            rosterTransfers.SelectMany(static transfer => transfer.AuditLines),
            prepLaunches.Select(DescribePrepLaunchEvidence),
            prepLaunches.SelectMany(static launch => launch.AuditLines),
            travelPrefetches.Select(DescribeTravelPrefetchEvidence),
            travelPrefetches.SelectMany(static receipt => receipt.Boundaries),
            travelPrefetches.SelectMany(static receipt => receipt.InventoryLines),
            workspace.ReturnSummary,
            workspace.ReturnSummary,
            carryForwardSignal ? carryForward?.Label : null,
            carryForwardSignal ? carryForward?.Summary : null,
            carryForwardSignal ? carryForward?.ReturnSummary : null,
            carryForwardSignal ? carryForward?.NextSafeAction : null);
        DateTimeOffset updatedAtUtc = new[]
            {
                carryForward?.UpdatedAtUtc,
                leadRun?.UpdatedAtUtc,
                sceneSignal ? activeScene?.UpdatedAtUtc : null
            }
            .Concat(eventPackets.Select(static packet => (DateTimeOffset?)packet.UpdatedAtUtc))
            .Concat(rosterTransfers.Select(static transfer => (DateTimeOffset?)transfer.TransferredAtUtc))
            .Concat(prepLaunches.Select(static launch => (DateTimeOffset?)launch.LaunchedAtUtc))
            .Concat(travelPrefetches.Select(static receipt => (DateTimeOffset?)receipt.StagedAtUtc))
            .Concat(consequences.Select(static consequence => (DateTimeOffset?)consequence.UpdatedAtUtc))
            .Concat(eventObjectives.Select(static objective => (DateTimeOffset?)objective.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"event-control:{workspace.WorkspaceId}",
            Kind: "event_control_packet",
            Title: $"{workspace.CampaignName} event and season controls",
            Summary: $"{eventCount} event-control receipt(s) keep season operations and return-loop governance on one lane. {consequenceSummary}{sourceSummary}",
            BindingSummary: "Reusable across GM operations so prep launches, return windows, and consequence governance stay on campaign truth.",
            Reusable: true,
            SearchTerms: BuildSearchTerms(
                workspace.CampaignName,
                "event",
                "season",
                "control",
                "opposition",
                "return",
                "operations",
                "roster",
                leadRun?.Title,
                carryForwardSignal ? carryForward?.Label : null,
                carryForwardSignal ? carryForward?.Summary : null,
                carryForwardSignal ? carryForward?.NextSafeAction : null,
                eventPackets.Select(static packet => packet.Kind),
                eventPackets.Select(static packet => packet.Label),
                rosterTransfers.Select(static transfer => transfer.RunnerHandle),
                rosterTransfers.Select(static transfer => transfer.SourceCampaignName),
                rosterTransfers.Select(static transfer => transfer.TargetCampaignName),
                rosterTransfers.Select(static transfer => transfer.SourceCrewName),
                rosterTransfers.Select(static transfer => transfer.TargetCrewName),
                eventObjectives.Select(static objective => objective.Title),
                eventObjectives.Select(static objective => objective.Status),
                eventObjectives.Select(static objective => objective.Pressure),
                sceneSignal ? activeScene?.Title : null,
                sceneSignal ? activeScene?.Summary : null,
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
                consequences.Select(static consequence => consequence.State),
                consequences.SelectMany(static consequence => consequence.Receipts.Select(static receipt => receipt.SourceKind))),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static bool IsEventControlCarryForwardSignal(NextSessionCarryForwardProjection? carryForward)
    {
        if (carryForward is null)
        {
            return false;
        }

        bool eventOrOppositionSignal = IsEventControlObjectiveSignal(carryForward.Label, carryForward.Summary)
            || IsEventControlObjectiveSignal(carryForward.ReturnSummary, carryForward.NextSafeAction);
        bool relationshipSignal = ContainsCampaignRelationshipSplitTokenSignal(carryForward.Label, carryForward.Summary, carryForward.ReturnSummary)
            || ContainsCampaignRelationshipSplitTokenSignal(carryForward.Label, carryForward.NextSafeAction, carryForward.ReturnSummary)
            || ContainsCampaignRelationshipSplitTokenSignal(carryForward.Summary, carryForward.NextSafeAction, carryForward.ReturnSummary);
        bool rosterSignal = IsRosterObjectiveSignal(carryForward.Label, carryForward.Summary)
            || IsRosterObjectiveSignal(carryForward.ReturnSummary, carryForward.NextSafeAction);
        string combinedCarryForwardText = string.Join(' ', new[]
        {
            carryForward.Label,
            carryForward.Summary,
            carryForward.ReturnSummary,
            carryForward.NextSafeAction
        }.Where(static value => !string.IsNullOrWhiteSpace(value)));
        bool prepLaunchSignal = ContainsPrepLaunchToken(combinedCarryForwardText);
        bool travelPrefetchSignal = ContainsTravelPrefetchToken(combinedCarryForwardText);

        return eventOrOppositionSignal
            || relationshipSignal
            || rosterSignal
            || prepLaunchSignal
            || travelPrefetchSignal;
    }

    private static bool IsEventControlObjectiveSignal(string? title, string? summary)
    {
        return ContainsEventControlToken(title)
            || ContainsEventControlToken(summary)
            || ContainsOppositionToken(title)
            || ContainsOppositionToken(summary);
    }

    private static bool ContainsEventControlToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("event", StringComparison.OrdinalIgnoreCase)
            || value.Contains("season", StringComparison.OrdinalIgnoreCase)
            || value.Contains("timeline", StringComparison.OrdinalIgnoreCase)
            || value.Contains("operation", StringComparison.OrdinalIgnoreCase)
            || value.Contains("checkpoint", StringComparison.OrdinalIgnoreCase);
    }

    private static bool ContainsOppositionToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("opposition", StringComparison.OrdinalIgnoreCase)
            || value.Contains("hostile", StringComparison.OrdinalIgnoreCase)
            || value.Contains("adversary", StringComparison.OrdinalIgnoreCase)
            || value.Contains("threat", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsOppositionSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "opposition", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "opposition_window", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "opposition_control", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "threat_window", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return normalizedKind.Contains("opposition", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("threat", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("hostile", StringComparison.OrdinalIgnoreCase)
            || normalizedKind.Contains("adversary", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsOppositionConsequenceSignal(CampaignConsequenceProjection consequence)
    {
        return IsOppositionSignalKind(consequence.Kind)
            || ContainsOppositionToken(consequence.Label)
            || ContainsOppositionToken(consequence.Summary)
            || consequence.EvidenceLines.Any(ContainsOppositionToken)
            || consequence.Receipts.Any(static receipt => ContainsOppositionToken(receipt.SourceKind) || ContainsOppositionToken(receipt.Summary));
    }

    private static bool IsOppositionSignal(WorkspaceChangePacketProjection packet)
    {
        return IsOppositionSignalKind(packet.Kind)
            || ContainsOppositionToken(packet.Label)
            || ContainsOppositionToken(packet.Summary);
    }

    private static bool IsEventControlSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "event_control", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "season_control", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "replay_timeline", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return IsRosterMovementSignalKind(normalizedKind)
            || IsPrepLaunchSignalKind(normalizedKind)
            || IsTravelPrefetchSignalKind(normalizedKind)
            || ContainsEventControlToken(normalizedKind)
            || IsCampaignRelationshipSignalKind(normalizedKind)
            || IsOppositionSignalKind(normalizedKind);
    }

    private static bool IsEventControlSignal(WorkspaceChangePacketProjection packet)
    {
        return IsEventControlSignalKind(packet.Kind)
            || IsRosterMovementSignal(packet)
            || ContainsEventControlFallbackToken(packet.Label)
            || ContainsEventControlFallbackToken(packet.Summary)
            || ContainsOppositionToken(packet.Label)
            || ContainsOppositionToken(packet.Summary)
            || IsCampaignRelationshipSignal(packet)
            || IsCampaignRelationshipSignalKind(packet.Label)
            || IsCampaignRelationshipSignalKind(packet.Summary);
    }

    private static bool ContainsEventControlFallbackToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("event", StringComparison.OrdinalIgnoreCase)
            || value.Contains("season", StringComparison.OrdinalIgnoreCase)
            || value.Contains("timeline", StringComparison.OrdinalIgnoreCase)
            || value.Contains("operation", StringComparison.OrdinalIgnoreCase)
            || value.Contains("checkpoint", StringComparison.OrdinalIgnoreCase);
    }

    private static GovernedPrepPacketSummary? BuildTravelPrefetchOpsPacket(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        TravelPrefetchReceiptProjection[] receipts = (workspace.TravelPrefetches ?? Array.Empty<TravelPrefetchReceiptProjection>())
            .OrderByDescending(static item => item.StagedAtUtc)
            .Take(4)
            .ToArray();
        WorkspaceChangePacketProjection[] prefetchSignals = (workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>())
            .Where(static packet => IsTravelPrefetchSignal(packet))
            .OrderByDescending(static packet => packet.UpdatedAtUtc)
            .Take(4)
            .ToArray();
        if (receipts.Length == 0 && prefetchSignals.Length == 0)
        {
            return null;
        }

        IReadOnlyList<string> evidence = BuildEvidenceLines(
            prefetchSignals.Select(static item => DescribeSignalLabel(item.Label, item.Kind, "travel prefetch signal")),
            receipts.Select(DescribeTravelPrefetchEvidence),
            receipts.SelectMany(static item => item.InventoryLines),
            receipts.SelectMany(static item => item.Boundaries),
            prefetchSignals.Select(static item => item.Summary),
            prefetchSignals.Select(static item => item.Label));
        int signalCount = receipts.Length + prefetchSignals.Length;
        string summary = receipts.Length > 0
            ? $"{signalCount} travel-prefetch signal(s) keep offline staging deliberate and reviewable per claimed device."
            : $"{signalCount} travel-prefetch signal(s) stay governed from change packets while travel receipt ingestion catches up.";
        DateTimeOffset updatedAtUtc = new[]
            {
                leadRun?.UpdatedAtUtc
            }
            .Concat(receipts.Select(static item => (DateTimeOffset?)item.StagedAtUtc))
            .Concat(prefetchSignals.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new GovernedPrepPacketSummary(
            PacketId: $"travel-prefetch:{workspace.WorkspaceId}",
            Kind: "travel_prefetch_packet",
            Title: $"{workspace.CampaignName} staged travel prefetch receipts",
            Summary: summary,
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
                receipts.Select(static item => item.InitiatedByUserId),
                prefetchSignals.Select(static item => item.Kind),
                prefetchSignals.Select(static item => item.Label)),
            EvidenceLines: evidence,
            UpdatedAtUtc: updatedAtUtc);
    }

    private static bool IsTravelPrefetchSignalKind(string? kind)
    {
        string normalizedKind = kind?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalizedKind))
        {
            return false;
        }

        if (string.Equals(normalizedKind, "travel_prefetch", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return normalizedKind.Contains("travel", StringComparison.OrdinalIgnoreCase)
            && normalizedKind.Contains("prefetch", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsTravelPrefetchSignal(WorkspaceChangePacketProjection packet)
    {
        return IsTravelPrefetchSignalKind(packet.Kind)
            || ContainsTravelPrefetchToken(packet.Label)
            || ContainsTravelPrefetchToken(packet.Summary)
            || ContainsTravelPrefetchToken(packet.Label, packet.Summary);
    }

    private static bool ContainsTravelPrefetchToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("travel", StringComparison.OrdinalIgnoreCase)
            && value.Contains("prefetch", StringComparison.OrdinalIgnoreCase);
    }

    private static bool ContainsTravelPrefetchToken(string? primary, string? secondary)
    {
        if (string.IsNullOrWhiteSpace(primary) && string.IsNullOrWhiteSpace(secondary))
        {
            return false;
        }

        string combined = $"{primary} {secondary}";
        return ContainsTravelPrefetchToken(combined);
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

        IReadOnlyList<string> evidence = BuildEvidenceLines(
            restore.ClaimedDevices.Select(DescribeClaimedDeviceTravelEvidence),
            restore.RecentArtifacts.Select(DescribeRestoreArtifactEvidence),
            restore.RecentRuleEnvironments.Select(DescribeRestoreRuleEnvironmentEvidence));

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
                restore.ClaimedDevices.Select(DescribeClaimedDeviceTravelEvidence),
                restore.RecentArtifacts.Select(static item => item.Label),
                restore.RecentArtifacts.Select(static item => item.Kind),
                restore.RecentArtifacts.Select(static item => item.Summary),
                restore.RecentRuleEnvironments.Select(static item => item.CompatibilityFingerprint),
                restore.RecentRuleEnvironments.Select(static item => item.ApprovalState),
                restore.RecentRuleEnvironments.Select(static item => item.OwnerScope)),
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

    private static string DescribeSignalLabel(string? preferredLabel, string? firstFallback, string? secondFallback)
    {
        if (!string.IsNullOrWhiteSpace(preferredLabel))
        {
            return preferredLabel.Trim();
        }

        if (!string.IsNullOrWhiteSpace(firstFallback))
        {
            return firstFallback.Trim();
        }

        return secondFallback?.Trim() ?? string.Empty;
    }

    private static string DescribeClaimedDeviceTravelEvidence(ClaimedDeviceRestoreProjection item)
    {
        string? summary = NormalizeOptional(item.RestoreSummary);
        if (summary is not null)
        {
            return summary;
        }

        string role = NormalizeOptional(item.DeviceRole) ?? "claimed device";
        string platform = NormalizeOptional(item.Platform) ?? "unknown platform";
        string? head = NormalizeOptional(item.HeadId);
        string? channel = NormalizeOptional(item.Channel);

        return head is null
            ? $"{role} on {platform}"
            : channel is null
                ? $"{role} on {platform} ({head})"
                : $"{role} on {platform} ({head}/{channel})";
    }

    private static string DescribeRosterTransferEvidence(RosterTransferProjection item)
    {
        string? summary = NormalizeOptional(item.Summary);
        if (summary is not null)
        {
            return summary;
        }

        string runner = NormalizeOptional(item.RunnerHandle) ?? "runner transfer";
        string source = NormalizeOptional(item.SourceCampaignName)
            ?? NormalizeOptional(item.SourceGroupName)
            ?? NormalizeOptional(item.SourceCrewName)
            ?? "source lane";
        string target = NormalizeOptional(item.TargetCampaignName)
            ?? NormalizeOptional(item.TargetGroupName)
            ?? NormalizeOptional(item.TargetCrewName)
            ?? "target lane";
        return $"{runner} transfer {source} -> {target}";
    }

    private static string DescribePrepLaunchEvidence(GovernedPrepLaunchProjection item)
    {
        string? summary = NormalizeOptional(item.Summary);
        if (summary is not null)
        {
            return summary;
        }

        string packetIdentity = DescribeSignalLabel(item.PacketTitle, item.PacketKind, "prep launch packet");
        string? targetRun = NormalizeOptional(item.TargetRunTitle) ?? NormalizeOptional(item.TargetRunId);
        string? targetScene = NormalizeOptional(item.TargetSceneTitle) ?? NormalizeOptional(item.TargetSceneId);
        if (targetRun is null && targetScene is null)
        {
            return packetIdentity;
        }

        if (targetRun is not null && targetScene is not null)
        {
            return $"{packetIdentity} for {targetRun} / {targetScene}";
        }

        return targetRun is not null
            ? $"{packetIdentity} for {targetRun}"
            : $"{packetIdentity} for {targetScene}";
    }

    private static string DescribeTravelPrefetchEvidence(TravelPrefetchReceiptProjection item)
    {
        string? summary = NormalizeOptional(item.PrefetchSummary);
        if (summary is not null)
        {
            return summary;
        }

        string role = NormalizeOptional(item.DeviceRole) ?? "travel device";
        string platform = NormalizeOptional(item.Platform) ?? "unknown platform";
        string? head = NormalizeOptional(item.HeadId);
        string? channel = NormalizeOptional(item.Channel);

        return head is null
            ? $"{role} on {platform}"
            : channel is null
                ? $"{role} on {platform} ({head})"
                : $"{role} on {platform} ({head}/{channel})";
    }

    private static string DescribeRestoreArtifactEvidence(RestoreArtifactProjection item)
        => DescribeSignalLabel(item.Summary, item.Label, item.Kind);

    private static string DescribeRestoreRuleEnvironmentEvidence(RuleEnvironmentRef item)
        => DescribeSignalLabel(item.CompatibilityFingerprint, item.ApprovalState, item.OwnerScope);

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
