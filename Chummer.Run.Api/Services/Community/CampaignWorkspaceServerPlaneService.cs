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
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests = _supportPresentation.BuildDigestList(relevantCases);

        DateTimeOffset generatedAtUtc = new[]
            {
                digest?.UpdatedAtUtc,
                accountSummary.Restore.GeneratedAtUtc,
                workspace.LatestContinuity?.CapturedAtUtc,
                leadRun?.UpdatedAtUtc
            }
            .Concat(relevantCases.Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new CampaignWorkspaceServerPlaneProjection(
            Workspace: BuildWorkspaceSummary(workspace, digest, accountSummary.Restore),
            CampaignSummary: BuildCampaignWorkspaceSummary(workspace, digest, accountSummary.Restore),
            RosterReadiness: BuildRosterReadinessSummary(workspace),
            ReadinessCues: workspace.ReadinessCues,
            ChangePackets: workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>(),
            DossierFreshness: BuildDossierFreshness(workspace),
            RuleEnvironmentHealth: BuildRuleEnvironmentHealth(workspace, accountSummary.Restore),
            Runboard: BuildRunboardSummary(workspace, leadRun),
            ContinuityConflicts: BuildContinuityConflicts(workspace, accountSummary.Restore),
            RecapShelf: BuildRecapShelf(workspace),
            SupportClosures: BuildSupportClosures(supportDigests),
            KnownIssues: BuildKnownIssues(supportDigests),
            DecisionNotices: BuildDecisionNotices(workspace, digest, installLinking, supportDigests),
            NextSafeAction: BuildNextSafeActionCue(workspace, installLinking, supportDigests),
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
        string restoreSummary = restore.ConflictSummaries.FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item))
            ?? restore.LocalOnlyNotes.FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item))
            ?? "Restore posture is attached to claimed installs and continuity snapshots instead of a local-only guess.";
        string publicationSummary = workspace.RecapShelf.Count == 0
            ? "No recap-safe output is pinned yet, so the workspace still needs its first publication-safe continuity handoff."
            : $"{workspace.RecapShelf.Count} publication-safe output(s) are attached to the same campaign continuity spine.";

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
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        HashSet<string> platforms = installations
            .Select(static item => item.Platform)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
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

    private static string StableCueId(string value)
    {
        string normalized = value.Trim().ToLowerInvariant();
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(normalized)))[..12].ToLowerInvariant();
    }
}
