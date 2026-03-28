using System.Globalization;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportCasePresentationService
{
    public IReadOnlyList<SupportCaseDigestViewModel> BuildDigestList(IReadOnlyList<SupportCaseProjection>? cases)
        => BuildList(cases)
            .Select(BuildDigest)
            .ToArray();

    public IReadOnlyList<SupportCasePresentationViewModel> BuildList(IReadOnlyList<SupportCaseProjection>? cases)
        => cases is null
            ? Array.Empty<SupportCasePresentationViewModel>()
            : cases.Select(Build)
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
            CanVerifyFix: item.CanVerifyFix);
    }

    public SupportCasePresentationViewModel Build(SupportCaseProjection supportCase)
    {
        ArgumentNullException.ThrowIfNull(supportCase);

        string status = NormalizeStatus(supportCase.Status);
        string fixedReleaseLabel = BuildFixedReleaseLabel(supportCase.FixedVersion, supportCase.FixedChannel);
        string detailHref = $"/account/support/{Uri.EscapeDataString(supportCase.CaseId)}";
        string? affectedInstallSummary = BuildAffectedInstallSummary(supportCase);
        string followUpLaneSummary = BuildFollowUpLaneSummary(supportCase);
        string verificationState = NormalizeVerificationState(supportCase.ReporterVerificationState);
        string releaseProgressSummary = BuildReleaseProgressSummary(supportCase, status, fixedReleaseLabel, verificationState);
        string verificationSummary = BuildVerificationSummary(supportCase, fixedReleaseLabel, verificationState);
        bool canVerifyFix = CanVerifyFix(status, verificationState);
        IReadOnlyList<SupportCaseTimelineHighlightViewModel> timelineHighlights = BuildTimelineHighlights(supportCase);
        var (stageLabel, nextSafeAction, closureSummary, primaryActionLabel, primaryActionHref, reporterActionNeeded) = verificationState switch
        {
            SupportCaseVerificationStates.ConfirmedFixed => (
                "Closed and confirmed",
                "No further action is needed unless the same issue returns on a later update.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "The closure notice already went out, and the reporter confirmed that the fix worked on the affected install."
                    : $"The closure notice already went out for {fixedReleaseLabel}, and the reporter confirmed that the fix worked on the affected install.",
                "Open downloads",
                "/downloads",
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
                "Watch the release lane and downloads so this fix can reach your installed channel.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "The underlying issue is fixed, but the release handoff may still be moving."
                    : $"The underlying issue is fixed and is moving through {fixedReleaseLabel}.",
                "Open downloads",
                "/downloads",
                false),
            SupportCaseStatuses.ReleasedToReporterChannel => (
                "Released",
                "Open downloads or update this linked install to pick up the reporter-ready fix.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "The fix reached a reporter-ready release channel."
                    : $"The fix reached {fixedReleaseLabel}.",
                "Open downloads",
                "/downloads",
                false),
            SupportCaseStatuses.UserNotified => (
                "Closed with notice",
                "Update or reinstall if needed, then reopen support only if the same issue still reproduces.",
                string.IsNullOrWhiteSpace(fixedReleaseLabel)
                    ? "Chummer already sent the closure notice for this case."
                    : $"Chummer already sent the closure notice for {fixedReleaseLabel}.",
                "Open downloads",
                "/downloads",
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
            CanVerifyFix: canVerifyFix);
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
            return "Follow-up stays inside Account > Support for this signed-in report.";
        }

        if (!string.IsNullOrWhiteSpace(supportCase.ReporterEmail))
        {
            return "Follow-up stays on the reply email attached to this case.";
        }

        return "Follow-up stays attached to this case id until a clearer response lane exists.";
    }

    private static string BuildReleaseProgressSummary(
        SupportCaseProjection supportCase,
        string normalizedStatus,
        string fixedReleaseLabel,
        string verificationState)
    {
        if (verificationState == SupportCaseVerificationStates.ConfirmedFixed)
        {
            return "The reporter confirmed the fix on the affected install, so the visible loop is closed unless the issue returns.";
        }

        if (verificationState == SupportCaseVerificationStates.StillBroken)
        {
            return "The reporter said the fix did not hold on the affected install, so the case reopened for follow-up and fresh evidence.";
        }

        return normalizedStatus switch
        {
            SupportCaseStatuses.UserNotified => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                ? "The fix already reached the reporter lane and the closure notice went out."
                : $"The fix reached {fixedReleaseLabel}, and the closure notice already went out.",
            SupportCaseStatuses.ReleasedToReporterChannel => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                ? "The fix reached the reporter-ready release lane. Update or reinstall on the affected device to pick it up."
                : $"The fix reached {fixedReleaseLabel}. Update or reinstall on the affected device to pick it up.",
            SupportCaseStatuses.Fixed => string.IsNullOrWhiteSpace(fixedReleaseLabel)
                ? "The fix exists, but the release handoff is still moving."
                : $"The fix is already mapped to {fixedReleaseLabel}, but the closure notice has not gone out yet.",
            _ when supportCase.UserNotifiedAtUtc.HasValue => "The closure notice already went out; reopen support only if the same issue still reproduces.",
            _ when supportCase.ReleasedToReporterChannelAtUtc.HasValue => "A reporter-ready fix exists, but the final user-facing closure step is still catching up.",
            _ => "No reporter-ready release is attached yet, so the visible next step is still triage or fix work."
        };
    }

    private static string BuildVerificationSummary(
        SupportCaseProjection supportCase,
        string fixedReleaseLabel,
        string verificationState)
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
            _ when CanVerifyFix(NormalizeStatus(supportCase.Status), verificationState)
                => "After you update or reinstall on the affected device, confirm whether the fix worked here or whether the same issue still reproduces.",
            _ => "No fix confirmation is requested yet."
        };
    }

    private static bool CanVerifyFix(string normalizedStatus, string verificationState)
        => verificationState != SupportCaseVerificationStates.ConfirmedFixed
           && (normalizedStatus == SupportCaseStatuses.Fixed
               || normalizedStatus == SupportCaseStatuses.ReleasedToReporterChannel
               || normalizedStatus == SupportCaseStatuses.UserNotified);

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
                Summary: "Chummer sent the closure notice to the reporter lane.",
                OccurredLabel: $"{supportCase.UserNotifiedAtUtc.Value.ToUniversalTime():yyyy-MM-dd HH:mm} UTC"));
        }

        if (supportCase.ReleasedToReporterChannelAtUtc.HasValue
            && !highlights.Any(static item => item.Label.Equals("Released", StringComparison.OrdinalIgnoreCase)))
        {
            highlights.Add(new SupportCaseTimelineHighlightViewModel(
                Label: "Released",
                Summary: "The fix reached the reporter-ready release lane.",
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
}
