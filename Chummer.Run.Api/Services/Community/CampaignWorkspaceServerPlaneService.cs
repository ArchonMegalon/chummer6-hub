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
        IReadOnlyList<DecisionNotice> decisionNotices = BuildDecisionNotices(context.Workspace, context.Digest, installLinking, context.SupportDigests);
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
            RecapShelf: BuildRecapShelf(context.Workspace),
            SupportClosures: supportClosures,
            KnownIssues: knownIssues,
            DecisionNotices: decisionNotices,
            PrepLibrary: prepLibrary,
            PrepLaunches: context.Workspace.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>(),
            TravelMode: travelMode,
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
        IReadOnlyList<GovernedPrepPacketSummary> packets = prepLibrary.Packets
            .Where(packet => MatchesPrepLibraryQuery(packet, normalizedQuery))
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
                ?? $"{workspace.RuleEnvironment.OwnerScope} · {workspace.RuleEnvironment.ApprovalState} · {workspace.RuleEnvironment.CompatibilityFingerprint}",
            SessionReadinessSummary: attentionCue is null
                ? "Session return is green across the current roster, active scene, and claimed-install restore posture."
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
                Severity: string.Equals(workspace.RuleEnvironment.ApprovalState, "approved", StringComparison.OrdinalIgnoreCase) ? "ready" : "review",
                Title: "Campaign rule environment",
                Summary: $"{workspace.RuleEnvironment.OwnerScope} scope is {workspace.RuleEnvironment.ApprovalState} on {workspace.RuleEnvironment.CompatibilityFingerprint}.")
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

    private static IReadOnlyList<RecapShelfEntry> BuildRecapShelf(CampaignWorkspaceProjection workspace)
        => workspace.RecapShelf
            .Take(6)
            .Select(item => new RecapShelfEntry(
                EntryId: item.ProjectionId,
                Kind: item.Kind,
                Label: item.Label,
                Summary: item.Summary,
                ArtifactId: item.ArtifactId,
                UpdatedAtUtc: workspace.LatestContinuity?.CapturedAtUtc ?? DateTimeOffset.UtcNow))
            .ToArray();

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
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests)
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
        if (consequences.Length == 0)
        {
            return null;
        }

        string labels = string.Join(", ", consequences.Select(static item => item.Label));
        IReadOnlyList<string> evidence = consequences
            .SelectMany(static item => item.EvidenceLines.Concat(item.Receipts.Select(static receipt => receipt.Summary)))
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

        return new GovernedPrepPacketSummary(
            PacketId: $"opposition:{workspace.WorkspaceId}",
            Kind: "opposition_packet",
            Title: $"{workspace.CampaignName} opposition packet",
            Summary: $"{consequences.Length} governed opposition signal(s) are active: {labels}.",
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
                leadRun?.Title,
                leadRun?.Objectives.Select(static item => item.Title)),
            EvidenceLines: evidence,
            UpdatedAtUtc: consequences.Max(static item => item.UpdatedAtUtc));
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

    private static bool MatchesPrepLibraryQuery(GovernedPrepPacketSummary packet, string? queryText)
    {
        if (string.IsNullOrWhiteSpace(queryText))
        {
            return true;
        }

        return new[]
            {
                packet.Title,
                packet.Summary,
                packet.BindingSummary
            }
            .Concat(packet.SearchTerms)
            .Concat(packet.EvidenceLines)
            .Any(text => text.Contains(queryText, StringComparison.OrdinalIgnoreCase));
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
