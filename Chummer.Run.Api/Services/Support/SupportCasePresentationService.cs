using System.Globalization;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportCasePresentationService
{
    public IReadOnlyList<SupportCaseDigestViewModel> BuildDigestList(IReadOnlyList<SupportCaseProjection>? cases, InstallLinkingSummaryDto? installLinking = null)
        => BuildList(cases, installLinking)
            .Select(BuildDigest)
            .ToArray();

    public IReadOnlyList<SupportCasePresentationViewModel> BuildList(IReadOnlyList<SupportCaseProjection>? cases, InstallLinkingSummaryDto? installLinking = null)
        => cases is null
            ? Array.Empty<SupportCasePresentationViewModel>()
            : cases.Select(item => Build(item, installLinking))
                .OrderByDescending(static item => item.Case.UpdatedAtUtc)
                .ThenBy(static item => item.Case.CaseId, StringComparer.OrdinalIgnoreCase)
                .ToArray();

    public SupportCaseDigestViewModel BuildDigest(SupportCasePresentationViewModel item)
    {
        ArgumentNullException.ThrowIfNull(item);

        return new SupportCaseDigestViewModel(
            CaseId: item.Case.CaseId,
            Title: item.Case.Title,
            Summary: item.Case.Summary,
            StatusLabel: item.StatusLabel,
            StageLabel: item.StageLabel,
            NextSafeAction: item.NextSafeAction,
            ClosureSummary: item.ClosureSummary,
            VerificationSummary: item.VerificationSummary,
            DetailHref: item.DetailHref,
            PrimaryActionLabel: item.PrimaryActionLabel,
            PrimaryActionHref: item.PrimaryActionHref,
            UpdatedLabel: item.UpdatedLabel,
            FixedReleaseLabel: item.FixedReleaseLabel,
            AffectedInstallSummary: item.AffectedInstallSummary,
            FollowUpLaneSummary: item.FollowUpLaneSummary,
            ReleaseProgressSummary: item.ReleaseProgressSummary,
            ReporterActionNeeded: item.ReporterActionNeeded,
            CanVerifyFix: item.CanVerifyFix,
            InstallReadinessSummary: item.InstallReadinessSummary,
            FixReadyOnLinkedInstall: item.FixReadyOnLinkedInstall,
            NeedsInstallUpdate: item.NeedsInstallUpdate,
            NeedsLinkedInstall: item.NeedsLinkedInstall);
    }

    public SupportCasePresentationViewModel Build(SupportCaseProjection supportCase, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(supportCase);

        string status = NormalizeStatus(supportCase.Status);
        bool installRailCase = HasInstallRailContext(supportCase);
        string fixedReleaseLabel = BuildFixedReleaseLabel(supportCase.FixedVersion, supportCase.FixedChannel);
        string detailHref = $"/account/support/{Uri.EscapeDataString(supportCase.CaseId)}";
        string? affectedInstallSummary = BuildAffectedInstallSummary(supportCase);
        string followUpLaneSummary = BuildFollowUpLaneSummary(supportCase);
        string verificationState = NormalizeVerificationState(supportCase.ReporterVerificationState);
        bool verificationAvailable = CanVerifyFix(status, verificationState);
        bool allowUpdatedInstallResolution = verificationAvailable
            || verificationState == SupportCaseVerificationStates.ConfirmedFixed;
        InstallVerificationReadiness installReadiness = BuildInstallReadiness(supportCase, status, fixedReleaseLabel, installLinking, verificationAvailable, allowUpdatedInstallResolution);
        string releaseProgressSummary = BuildReleaseProgressSummary(supportCase, status, fixedReleaseLabel, verificationState, installReadiness);
        string verificationSummary = BuildVerificationSummary(supportCase, fixedReleaseLabel, verificationState, installReadiness);
        bool canVerifyFix = verificationAvailable && installReadiness.FixReadyOnLinkedInstall;
        IReadOnlyList<SupportCaseTimelineHighlightViewModel> timelineHighlights = BuildTimelineHighlights(supportCase);
        var (stageLabel, nextSafeAction, closureSummary, primaryActionLabel, primaryActionHref, reporterActionNeeded) = verificationState switch
        {
            SupportCaseVerificationStates.ConfirmedFixed => (
                "Closed and confirmed",
                installRailCase
                    ? "Update the affected claimed install normally. Reopen this same tracked case only if the same issue returns on a later update."
                    : "No further action is needed unless the same issue returns on a later update.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "The closure notice already went out, and the reporter confirmed that the fix worked on the affected install."
                    : $"The closure notice already went out for {fixedReleaseLabel}, and the reporter confirmed that the fix worked on the affected install.",
                installRailCase ? "Open Devices and access" : "Open downloads",
                installRailCase ? "/account/access" : "/downloads",
                false),
            SupportCaseVerificationStates.StillBroken => (
                "Needs follow-up",
                "Add the newest reproduction detail or log on this same tracked case so support can reopen the fix path without losing continuity.",
                "The reporter said the fix did not hold on the affected install, so the case reopened for follow-up.",
                "Open tracked case",
                detailHref,
                true),
            _ => status switch
        {
            SupportCaseStatuses.Clustered => (
                "Merged",
                "No reply is needed yet unless the case asks for more detail later.",
                "Matching reports were merged so one tracked case keeps the visible history.",
                "Open tracked case",
                detailHref,
                false),
            SupportCaseStatuses.Routed => (
                "Routed",
                "Wait for triage unless a clearer reproduction step or log becomes available.",
                "The case is already pointed at the right queue.",
                "Open tracked case",
                detailHref,
                false),
            SupportCaseStatuses.AwaitingEvidence => (
                "Needs detail",
                "Add a clearer reproduction path, screenshot, or log so the case can move again.",
                "Chummer needs more evidence before the fix path can continue.",
                "Open tracked case",
                detailHref,
                true),
            SupportCaseStatuses.Accepted => (
                "In progress",
                "Wait for a routed fix or release update. Use the case id if you need to follow up.",
                "Chummer accepted this as a real issue and is tracking the fix path.",
                "Open tracked case",
                detailHref,
                false),
            SupportCaseStatuses.Fixed => (
                "Fixed",
                installRailCase
                    ? "Open Devices and access, then continue with the same linked copy when the fixed build reaches your install."
                    : "Watch downloads so this fix can reach your installed channel.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "The underlying issue is fixed, but the release handoff may still be moving."
                    : $"The underlying issue is fixed and is moving through {fixedReleaseLabel}.",
                installRailCase ? "Open Devices and access" : "Open downloads",
                installRailCase ? "/account/access" : "/downloads",
                false),
            SupportCaseStatuses.ReleasedToReporterChannel => (
                "Released",
                installRailCase
                    ? "Open Devices and access, then update or relink the same linked install to pick up the reporter-ready fix."
                    : "Open downloads or update this linked install to pick up the reporter-ready fix.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "The fix reached a reporter-ready release channel."
                    : $"The fix reached {fixedReleaseLabel}.",
                installRailCase ? "Open Devices and access" : "Open downloads",
                installRailCase ? "/account/access" : "/downloads",
                false),
            SupportCaseStatuses.UserNotified => (
                "Closed with notice",
                installRailCase
                    ? "Open Devices and access, then update, relink, or reinstall with the same account if needed."
                    : "Update or reinstall if needed, then reopen support only if the same issue still reproduces.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "Chummer already sent the closure notice for this case."
                    : $"Chummer already sent the closure notice for {fixedReleaseLabel}.",
                installRailCase ? "Open Devices and access" : "Open downloads",
                installRailCase ? "/account/access" : "/downloads",
                false),
            SupportCaseStatuses.Deferred => (
                "Deferred",
                "Do not wait on an immediate fix. Open a new case only if the situation changes materially.",
                "Chummer kept the context, but active work is deferred for now.",
                "Open tracked case",
                detailHref,
                false),
            SupportCaseStatuses.Rejected => (
                "Closed",
                "Open a new case only if you can provide corrected context or a clearer reproduction path.",
                "Chummer closed this report without taking it forward.",
                "Open tracked case",
                detailHref,
                false),
            _ => (
                "Queued",
                "No reply is needed yet. Chummer is still recording and routing the first triage step.",
                "The report is attached to one stable case id and is waiting for first triage.",
                "Open tracked case",
                detailHref,
                false)
        }};

        if (installRailCase)
        {
            nextSafeAction = BuildInstallRailNextSafeAction(status, fixedReleaseLabel, installReadiness, nextSafeAction);
        }

        return new SupportCasePresentationViewModel(
            Case: supportCase,
            StatusLabel: HumanizeStatus(status),
            StageLabel: stageLabel,
            NextSafeAction: nextSafeAction,
            ClosureSummary: closureSummary,
            VerificationSummary: verificationSummary,
            DetailHref: detailHref,
            PrimaryActionLabel: primaryActionLabel,
            PrimaryActionHref: primaryActionHref,
            UpdatedLabel: $"{supportCase.UpdatedAtUtc.ToUniversalTime():yyyy-MM-dd HH:mm} UTC",
            FixedReleaseLabel: string.IsNullOrWhiteSpace(fixedReleaseLabel) ? null : fixedReleaseLabel,
            AffectedInstallSummary: affectedInstallSummary,
            FollowUpLaneSummary: followUpLaneSummary,
            ReleaseProgressSummary: releaseProgressSummary,
            TimelineHighlights: timelineHighlights,
            ReporterActionNeeded: reporterActionNeeded,
            CanVerifyFix: canVerifyFix,
            InstallReadinessSummary: installReadiness.Summary,
            FixReadyOnLinkedInstall: installReadiness.FixReadyOnLinkedInstall,
            NeedsInstallUpdate: installReadiness.NeedsInstallUpdate,
            NeedsLinkedInstall: installReadiness.NeedsLinkedInstall);
    }

    private static string NormalizeStatus(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? SupportCaseStatuses.New
            : value.Trim().ToLowerInvariant();

    private static string HumanizeStatus(string value)
        => value switch
        {
            SupportCaseStatuses.UserNotified => "Notified",
            SupportCaseStatuses.ReleasedToReporterChannel => "Released",
            SupportCaseStatuses.AwaitingEvidence => "Needs detail",
            _ => CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.Replace('_', ' '))
        };

    private static string NormalizeVerificationState(string? value)
    {
        string? normalized = NormalizeOptional(value, 64);
        if (normalized is null)
        {
            return string.Empty;
        }

        return normalized.ToLowerInvariant() switch
        {
            SupportCaseVerificationStates.ConfirmedFixed => SupportCaseVerificationStates.ConfirmedFixed,
            SupportCaseVerificationStates.StillBroken => SupportCaseVerificationStates.StillBroken,
            _ => string.Empty
        };
    }

    private static string BuildFixedReleaseLabel(string? version, string? channel)
    {
        string? normalizedVersion = NormalizeOptional(version, 64);
        string? normalizedChannel = NormalizeOptional(channel, 64);
        if (normalizedVersion is null && normalizedChannel is null)
        {
            return string.Empty;
        }

        if (normalizedVersion is null)
        {
            return $"{normalizedChannel} release";
        }

        if (normalizedChannel is null)
        {
            return $"version {normalizedVersion}";
        }

        return $"{normalizedChannel} {normalizedVersion}";
    }

    private static string? NormalizeOptional(string? value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string trimmed = value.Trim();
        return trimmed.Length <= maxLength ? trimmed : trimmed[..maxLength];
    }

    private static string? BuildAffectedInstallSummary(SupportCaseProjection supportCase)
    {
        string? installationId = NormalizeOptional(supportCase.InstallationId, 64);
        string? releaseChannel = NormalizeOptional(supportCase.ReleaseChannel, 64);
        string? applicationVersion = NormalizeOptional(supportCase.ApplicationVersion, 64);
        string? headId = NormalizeOptional(supportCase.HeadId, 64);
        string? platform = NormalizeOptional(supportCase.Platform, 64);
        string? arch = NormalizeOptional(supportCase.Arch, 32);
        var descriptors = new List<string>();
        if (!string.IsNullOrWhiteSpace(headId))
        {
            descriptors.Add(headId);
        }

        string? platformSummary = JoinNonEmpty(platform, arch, separator: " ");
        if (!string.IsNullOrWhiteSpace(platformSummary))
        {
            descriptors.Add(platformSummary);
        }

        string? releaseSummary = JoinNonEmpty(releaseChannel, applicationVersion, separator: " ");
        if (!string.IsNullOrWhiteSpace(releaseSummary))
        {
            descriptors.Add(releaseSummary);
        }

        if (descriptors.Count == 0 && string.IsNullOrWhiteSpace(installationId))
        {
            return null;
        }

        string target = descriptors.Count == 0
            ? "the linked install"
            : $"the linked {string.Join(" · ", descriptors)} install";

        return string.IsNullOrWhiteSpace(installationId)
            ? $"This case stays attached to {target}."
            : $"This case stays attached to {target} ({installationId}).";
    }

    private static string BuildFollowUpLaneSummary(SupportCaseProjection supportCase)
    {
        if (!string.IsNullOrWhiteSpace(supportCase.ReporterUserId) || !string.IsNullOrWhiteSpace(supportCase.ReporterSubjectId))
        {
            if (HasInstallRailContext(supportCase))
            {
                return "Follow-up stays attached to the affected claimed install. Use Account > Support for tracked history and Devices & access only when you need to relink or reclaim that copy.";
            }

            return "Follow-up stays inside Account > Support for this signed-in report.";
        }

        if (!string.IsNullOrWhiteSpace(supportCase.ReporterEmail))
        {
            return "Follow-up stays on the reply email attached to this case.";
        }

        return "Follow-up stays attached to this case id until there is a better reply path.";
    }

    private static bool HasInstallRailContext(SupportCaseProjection supportCase)
        => HasSupportCaseInstallTruth(supportCase);

    private static string BuildReleaseProgressSummary(
        SupportCaseProjection supportCase,
        string normalizedStatus,
        string fixedReleaseLabel,
        string verificationState,
        InstallVerificationReadiness installReadiness)
    {
        if (verificationState == SupportCaseVerificationStates.ConfirmedFixed)
        {
            return "The reporter confirmed the fix on the affected install, so the visible loop is closed unless the issue returns.";
        }

        if (verificationState == SupportCaseVerificationStates.StillBroken)
        {
            return "The reporter said the fix did not hold on the affected install, so the case reopened for follow-up and fresh evidence.";
        }

        string baseSummary = normalizedStatus switch
        {
            SupportCaseStatuses.UserNotified => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                ? "The fix already reached the reporter and the closure notice went out."
                : $"The fix reached {fixedReleaseLabel}, and the closure notice already went out.",
            SupportCaseStatuses.ReleasedToReporterChannel => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                ? "The fix is ready for the reporter. Update or reinstall on the affected device to pick it up."
                : $"The fix reached {fixedReleaseLabel}. Update or reinstall on the affected device to pick it up.",
            SupportCaseStatuses.Fixed => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                ? "The fix exists, but the release handoff is still moving."
                : $"The fix is already mapped to {fixedReleaseLabel}, but the closure notice has not gone out yet.",
            _ when supportCase.UserNotifiedAtUtc.HasValue => "The closure notice already went out; reopen support only if the same issue still reproduces.",
            _ when supportCase.ReleasedToReporterChannelAtUtc.HasValue => "A reporter-ready fix exists, but the final user-facing closure step is still catching up.",
            _ => "No reporter-ready release is attached yet, so the visible next step is still triage or fix work."
        };

        if (!CanVerifyFix(normalizedStatus, verificationState) || string.IsNullOrWhiteSpace(installReadiness.Summary))
        {
            return baseSummary;
        }

        return $"{baseSummary} {installReadiness.Summary}";
    }

    private static string BuildVerificationSummary(
        SupportCaseProjection supportCase,
        string fixedReleaseLabel,
        string verificationState,
        InstallVerificationReadiness installReadiness)
    {
        string verifiedAt = supportCase.ReporterVerifiedAtUtc?.ToUniversalTime().ToString("yyyy-MM-dd HH:mm") ?? "an unknown time";
        return verificationState switch
        {
            SupportCaseVerificationStates.ConfirmedFixed => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                ? $"Reporter confirmed the fix on the affected install at {verifiedAt} UTC."
                : $"Reporter confirmed {fixedReleaseLabel} on the affected install at {verifiedAt} UTC.",
            SupportCaseVerificationStates.StillBroken => string.IsNullOrWhiteSpace(supportCase.ReporterVerificationNote)
                ? $"Reporter said the fix is still broken on the affected install at {verifiedAt} UTC."
                : $"Reporter said the fix is still broken at {verifiedAt} UTC: {supportCase.ReporterVerificationNote}",
            _ when CanVerifyFix(NormalizeStatus(supportCase.Status), verificationState) && installReadiness.FixReadyOnLinkedInstall
                => $"{installReadiness.Summary} Use the buttons here to confirm whether the fix worked here or whether the same issue still reproduces.",
            _ when CanVerifyFix(NormalizeStatus(supportCase.Status), verificationState)
                => $"{installReadiness.Summary} After that update, use the buttons here to confirm whether the fix worked here or whether the same issue still reproduces.",
            _ => "No fix confirmation is requested yet."
        };
    }

    private static string BuildInstallRailNextSafeAction(
        string normalizedStatus,
        string fixedReleaseLabel,
        InstallVerificationReadiness installReadiness,
        string fallbackAction)
    {
        if (installReadiness.NeedsLinkedInstall)
        {
            return normalizedStatus switch
            {
                SupportCaseStatuses.Fixed => "Relink or reclaim the affected copy in Devices and access, then return to that claimed install before you wait for this fix to land there.",
                SupportCaseStatuses.ReleasedToReporterChannel => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "Relink or reclaim the affected copy in Devices and access, then return to that claimed install before you pick up the reporter-ready fix there."
                    : $"Relink or reclaim the affected copy in Devices and access, then return to that claimed install before you pick up {fixedReleaseLabel} there.",
                SupportCaseStatuses.UserNotified => "Relink or reclaim the affected copy in Devices and access, then return to that claimed install before you verify whether the reported fix held there.",
                _ => fallbackAction
            };
        }

        if (installReadiness.NeedsInstallUpdate)
        {
            return normalizedStatus switch
            {
                SupportCaseStatuses.Fixed => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "Update the affected claimed install, then continue the fix on that same copy."
                    : $"Update the affected claimed install to {fixedReleaseLabel}, then continue the fix on that same copy.",
                SupportCaseStatuses.ReleasedToReporterChannel => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "Update the affected claimed install to the reporter-ready build, then verify the fix on that same copy."
                    : $"Update the affected claimed install to {fixedReleaseLabel}, then verify the fix on that same copy.",
                SupportCaseStatuses.UserNotified => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "Update or reinstall the affected claimed install before you reopen this case."
                    : $"Update or reinstall the affected claimed install to {fixedReleaseLabel} before you reopen this case.",
                _ => fallbackAction
            };
        }

        if (installReadiness.FixReadyOnLinkedInstall)
        {
            return normalizedStatus switch
            {
                SupportCaseStatuses.ReleasedToReporterChannel => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "Verify the reporter-ready fix on the affected claimed install."
                    : $"Verify {fixedReleaseLabel} on the affected claimed install.",
                SupportCaseStatuses.UserNotified => "Verify the affected claimed install before you decide whether to reopen support.",
                _ => fallbackAction
            };
        }

        return fallbackAction;
    }

    private static bool CanVerifyFix(string normalizedStatus, string verificationState)
        => verificationState != SupportCaseVerificationStates.ConfirmedFixed
           && (normalizedStatus == SupportCaseStatuses.Fixed
               || normalizedStatus == SupportCaseStatuses.ReleasedToReporterChannel
               || normalizedStatus == SupportCaseStatuses.UserNotified);

    private static InstallVerificationReadiness BuildInstallReadiness(
        SupportCaseProjection supportCase,
        string normalizedStatus,
        string fixedReleaseLabel,
        InstallLinkingSummaryDto? installLinking,
        bool verificationAvailable,
        bool allowUpdatedInstallResolution)
    {
        var installations = installLinking?.ClaimedInstallations ?? Array.Empty<ClaimedInstallationDto>();
        if (installations.Count == 0)
        {
            return verificationAvailable
                ? new InstallVerificationReadiness(
                    Summary: "No linked install is attached yet. Link or reclaim the affected copy in Devices and access before you verify the fix here.",
                    FixReadyOnLinkedInstall: false,
                    NeedsInstallUpdate: false,
                    NeedsLinkedInstall: true)
                : new InstallVerificationReadiness(
                    Summary: "No linked install is attached yet, so this case is still waiting for the first claimed device.",
                    FixReadyOnLinkedInstall: false,
                    NeedsInstallUpdate: false,
                    NeedsLinkedInstall: true);
        }

        ClaimedInstallationDto? installation = ResolveRelevantInstallation(supportCase, installations, allowUpdatedInstallResolution);
        if (installation is null)
        {
            return verificationAvailable
                ? new InstallVerificationReadiness(
                    Summary: "The affected install is not linked to this account right now. Reclaim that copy in Devices and access before you verify the fix.",
                    FixReadyOnLinkedInstall: false,
                    NeedsInstallUpdate: false,
                    NeedsLinkedInstall: true)
                : new InstallVerificationReadiness(
                    Summary: "The current linked devices do not include the install this case was filed against.",
                    FixReadyOnLinkedInstall: false,
                    NeedsInstallUpdate: false,
                    NeedsLinkedInstall: true);
        }

        string installationLabel = BuildInstallationLabel(installation);
        string installationRelease = $"{installation.Channel} {installation.Version}";

        if (!verificationAvailable)
        {
            return new InstallVerificationReadiness(
                Summary: $"{installationLabel} stays linked on {installationRelease}.",
                FixReadyOnLinkedInstall: false,
                NeedsInstallUpdate: false,
                NeedsLinkedInstall: false);
        }

        string? fixedChannel = NormalizeOptional(supportCase.FixedChannel, 64);
        string? fixedVersion = NormalizeOptional(supportCase.FixedVersion, 64);
        bool channelMatches = string.IsNullOrWhiteSpace(fixedChannel)
            || string.Equals(installation.Channel, fixedChannel, StringComparison.OrdinalIgnoreCase);
        bool versionMatches = string.IsNullOrWhiteSpace(fixedVersion)
            || string.Equals(installation.Version, fixedVersion, StringComparison.OrdinalIgnoreCase);
        string releaseLabel = string.IsNullOrWhiteSpace(fixedReleaseLabel)
            ? "the reporter-ready release"
            : fixedReleaseLabel;

        if (channelMatches && versionMatches)
        {
            return new InstallVerificationReadiness(
                Summary: $"{installationLabel} is already on {installationRelease}.",
                FixReadyOnLinkedInstall: true,
                NeedsInstallUpdate: false,
                NeedsLinkedInstall: false);
        }

        if (channelMatches)
        {
            return new InstallVerificationReadiness(
                Summary: $"{installationLabel} is still on {installationRelease}. Update it to {releaseLabel} first.",
                FixReadyOnLinkedInstall: false,
                NeedsInstallUpdate: true,
                NeedsLinkedInstall: false);
        }

        return new InstallVerificationReadiness(
            Summary: $"{installationLabel} is on {installationRelease}, but this fix is staged for {releaseLabel}. Switch or update that linked copy first.",
            FixReadyOnLinkedInstall: false,
            NeedsInstallUpdate: true,
            NeedsLinkedInstall: false);
    }

    private static ClaimedInstallationDto? ResolveRelevantInstallation(
        SupportCaseProjection supportCase,
        IReadOnlyList<ClaimedInstallationDto> installations,
        bool allowUpdatedInstallForVerification)
    {
        string? installationId = NormalizeOptional(supportCase.InstallationId, 64);
        if (installationId is not null)
        {
            ClaimedInstallationDto? direct = installations
                .FirstOrDefault(item => string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase));
            if (direct is not null
                && (allowUpdatedInstallForVerification
                    ? HasCompleteDeviceTruth(
                        NormalizeOptional(supportCase.HeadId, 64),
                        NormalizeOptional(supportCase.Platform, 64),
                        NormalizeOptional(supportCase.Arch, 32))
                      && MatchesSupportCaseDeviceTruth(supportCase, direct)
                    : HasSupportCaseInstallTruth(supportCase)
                      && MatchesSupportCaseInstallTruth(supportCase, direct)))
            {
                return direct;
            }
        }

        string? releaseChannel = NormalizeOptional(supportCase.ReleaseChannel, 64);
        string? applicationVersion = NormalizeOptional(supportCase.ApplicationVersion, 64);
        string? headId = NormalizeOptional(supportCase.HeadId, 64);
        string? platform = NormalizeOptional(supportCase.Platform, 64);
        string? arch = NormalizeOptional(supportCase.Arch, 32);
        if (!HasCompleteInstalledBuildTruth(applicationVersion, releaseChannel)
            || !HasCompleteDeviceTruth(headId, platform, arch))
        {
            return null;
        }

        var best = installations
            .Where(item => allowUpdatedInstallForVerification
                ? MatchesSupportCaseDeviceTruth(supportCase, item)
                : MatchesSupportCaseInstallTruth(supportCase, item))
            .Select(item => new
            {
                Installation = item,
                Score = ScoreInstallationMatch(item, applicationVersion, releaseChannel, headId, platform, arch)
            })
            .OrderByDescending(static item => item.Score)
            .ThenByDescending(static item => item.Installation.UpdatedAtUtc)
            .FirstOrDefault();

        return best is not null && best.Score > 0
            ? best.Installation
            : null;
    }

    private static int ScoreInstallationMatch(
        ClaimedInstallationDto installation,
        string? applicationVersion,
        string? releaseChannel,
        string? headId,
        string? platform,
        string? arch)
    {
        int score = 0;
        if (!string.IsNullOrWhiteSpace(applicationVersion)
            && string.Equals(installation.Version, applicationVersion, StringComparison.OrdinalIgnoreCase))
        {
            score += 16;
        }

        if (!string.IsNullOrWhiteSpace(releaseChannel)
            && string.Equals(installation.Channel, releaseChannel, StringComparison.OrdinalIgnoreCase))
        {
            score += 8;
        }

        if (!string.IsNullOrWhiteSpace(headId)
            && string.Equals(installation.HeadId, headId, StringComparison.OrdinalIgnoreCase))
        {
            score += 4;
        }

        if (!string.IsNullOrWhiteSpace(platform)
            && string.Equals(installation.Platform, platform, StringComparison.OrdinalIgnoreCase))
        {
            score += 2;
        }

        if (!string.IsNullOrWhiteSpace(arch)
            && string.Equals(installation.Arch, arch, StringComparison.OrdinalIgnoreCase))
        {
            score += 1;
        }

        return score;
    }

    private static bool MatchesSupportCaseInstallTruth(SupportCaseProjection supportCase, ClaimedInstallationDto installation)
        => MatchesOptionalInstallField(supportCase.ApplicationVersion, installation.Version)
           && MatchesOptionalInstallField(supportCase.ReleaseChannel, installation.Channel)
           && MatchesOptionalInstallField(supportCase.HeadId, installation.HeadId)
           && MatchesOptionalInstallField(supportCase.Platform, installation.Platform)
           && MatchesOptionalInstallField(supportCase.Arch, installation.Arch);

    private static bool MatchesSupportCaseDeviceTruth(SupportCaseProjection supportCase, ClaimedInstallationDto installation)
        => MatchesOptionalInstallField(supportCase.HeadId, installation.HeadId)
           && MatchesOptionalInstallField(supportCase.Platform, installation.Platform)
           && MatchesOptionalInstallField(supportCase.Arch, installation.Arch);

    private static bool HasSupportCaseInstallTruth(SupportCaseProjection supportCase)
        => HasCompleteInstalledBuildTruth(
               NormalizeOptional(supportCase.ApplicationVersion, 64),
               NormalizeOptional(supportCase.ReleaseChannel, 64))
           && HasCompleteDeviceTruth(
               NormalizeOptional(supportCase.HeadId, 64),
               NormalizeOptional(supportCase.Platform, 64),
               NormalizeOptional(supportCase.Arch, 32));

    private static bool MatchesOptionalInstallField(string? supportValue, string? installationValue)
        => string.IsNullOrWhiteSpace(supportValue)
           || string.Equals(supportValue, installationValue, StringComparison.OrdinalIgnoreCase);

    private static bool HasCompleteInstalledBuildTruth(string? applicationVersion, string? releaseChannel)
        => !string.IsNullOrWhiteSpace(applicationVersion)
           && !string.IsNullOrWhiteSpace(releaseChannel);

    private static bool HasCompleteDeviceTruth(string? headId, string? platform, string? arch)
        => !string.IsNullOrWhiteSpace(headId)
           && !string.IsNullOrWhiteSpace(platform)
           && !string.IsNullOrWhiteSpace(arch);

    private static string BuildInstallationLabel(ClaimedInstallationDto installation)
    {
        string anchor = NormalizeOptional(installation.HostLabel, 128)
            ?? NormalizeOptional(installation.HeadId, 64)
            ?? NormalizeOptional(installation.ArtifactId, 128)
            ?? "The linked install";
        string? platformSummary = JoinNonEmpty(
            NormalizeOptional(installation.Platform, 64),
            NormalizeOptional(installation.Arch, 32),
            " ");
        return string.IsNullOrWhiteSpace(platformSummary)
            ? anchor
            : $"{anchor} ({platformSummary})";
    }

    private static IReadOnlyList<SupportCaseTimelineHighlightViewModel> BuildTimelineHighlights(SupportCaseProjection supportCase)
    {
        var highlights = new List<SupportCaseTimelineHighlightViewModel>();
        if (supportCase.Timeline is { Count: > 0 })
        {
            highlights.AddRange(
                supportCase.Timeline
                    .OrderByDescending(static item => item.OccurredAtUtc)
                    .Take(6)
                    .Select(item => new SupportCaseTimelineHighlightViewModel(
                        Label: HumanizeStatus(NormalizeStatus(item.Status)),
                        Summary: item.Summary,
                        OccurredLabel: $"{item.OccurredAtUtc.ToUniversalTime():yyyy-MM-dd HH:mm} UTC")));
        }

        if (supportCase.UserNotifiedAtUtc.HasValue
            && !highlights.Any(static item => item.Summary.Contains("closure notice", StringComparison.OrdinalIgnoreCase)))
        {
            highlights.Add(new SupportCaseTimelineHighlightViewModel(
                Label: "Notified",
                Summary: "Chummer sent the closure notice to the reporter.",
                OccurredLabel: $"{supportCase.UserNotifiedAtUtc.Value.ToUniversalTime():yyyy-MM-dd HH:mm} UTC"));
        }

        if (supportCase.ReleasedToReporterChannelAtUtc.HasValue
            && !highlights.Any(static item => item.Label.Equals("Released", StringComparison.OrdinalIgnoreCase)))
        {
            highlights.Add(new SupportCaseTimelineHighlightViewModel(
                Label: "Released",
                Summary: "The fix is ready for the reporter.",
                OccurredLabel: $"{supportCase.ReleasedToReporterChannelAtUtc.Value.ToUniversalTime():yyyy-MM-dd HH:mm} UTC"));
        }

        return highlights
            .OrderByDescending(static item => item.OccurredLabel, StringComparer.Ordinal)
            .Take(6)
            .ToArray();
    }

    private static string? JoinNonEmpty(string? left, string? right, string separator)
    {
        if (string.IsNullOrWhiteSpace(left))
        {
            return string.IsNullOrWhiteSpace(right) ? null : right;
        }

        if (string.IsNullOrWhiteSpace(right))
        {
            return left;
        }

        return $"{left}{separator}{right}";
    }

    private sealed record InstallVerificationReadiness(
        string Summary,
        bool FixReadyOnLinkedInstall,
        bool NeedsInstallUpdate,
        bool NeedsLinkedInstall);
}
