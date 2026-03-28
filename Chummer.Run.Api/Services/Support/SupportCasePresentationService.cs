using System.Globalization;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportCasePresentationService
{
    public IReadOnlyList<SupportCasePresentationViewModel> BuildList(IReadOnlyList<SupportCaseProjection>? cases)
        => cases is null
            ? Array.Empty<SupportCasePresentationViewModel>()
            : cases.Select(Build)
                .OrderByDescending(static item => item.Case.UpdatedAtUtc)
                .ThenBy(static item => item.Case.CaseId, StringComparer.OrdinalIgnoreCase)
                .ToArray();

    public SupportCasePresentationViewModel Build(SupportCaseProjection supportCase)
    {
        ArgumentNullException.ThrowIfNull(supportCase);

        string status = NormalizeStatus(supportCase.Status);
        string fixedReleaseLabel = BuildFixedReleaseLabel(supportCase.FixedVersion, supportCase.FixedChannel);
        string detailHref = $"/account/support/{Uri.EscapeDataString(supportCase.CaseId)}";
        var (stageLabel, nextSafeAction, closureSummary, primaryActionLabel, primaryActionHref, reporterActionNeeded) = status switch
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
        };

        return new SupportCasePresentationViewModel(
            Case: supportCase,
            StatusLabel: HumanizeStatus(status),
            StageLabel: stageLabel,
            NextSafeAction: nextSafeAction,
            ClosureSummary: closureSummary,
            DetailHref: detailHref,
            PrimaryActionLabel: primaryActionLabel,
            PrimaryActionHref: primaryActionHref,
            UpdatedLabel: $"{supportCase.UpdatedAtUtc.ToUniversalTime():yyyy-MM-dd HH:mm} UTC",
            FixedReleaseLabel: string.IsNullOrWhiteSpace(fixedReleaseLabel) ? null : fixedReleaseLabel,
            ReporterActionNeeded: reporterActionNeeded);
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
}
