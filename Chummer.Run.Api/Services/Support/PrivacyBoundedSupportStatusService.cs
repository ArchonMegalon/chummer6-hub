using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class PrivacyBoundedSupportStatusService
{
    private readonly PublicReleaseManifestService _releases;
    private readonly SupportConciergePacketService _supportConciergePackets;

    public PrivacyBoundedSupportStatusService(
        PublicReleaseManifestService releases,
        SupportConciergePacketService supportConciergePackets)
    {
        _releases = releases;
        _supportConciergePackets = supportConciergePackets;
    }

    public PrivacyBoundedSupportStatusBundle Build(PrivacyBoundedSupportStatusContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        DateTimeOffset now = DateTimeOffset.UtcNow;
        SupportCaseProjection? latestSupportCase = context.SupportCases?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        CrashWorkItemProjection? latestCrashWorkItem = context.CrashWorkItems?
            .OrderByDescending(static item => item.LastSeenAtUtc)
            .FirstOrDefault();
        SignalToCanonPacketProjection? feedbackPacket = context.PublicSignals?.Packets
            .FirstOrDefault(item => string.Equals(item.SurfaceId, "feedback", StringComparison.Ordinal));
        InstallAwareSupportConciergePacket? concierge = latestSupportCase is null
            ? null
            : _supportConciergePackets.Build(latestSupportCase, context.InstallLinking);

        return new PrivacyBoundedSupportStatusBundle(
            BuiltAtUtc: now,
            Projections:
            [
                BuildSupportStatus(manifest, latestSupportCase, concierge, now, context.Locale),
                BuildCrashStatus(manifest, latestCrashWorkItem, now, context.Locale),
                BuildFeedbackStatus(manifest, feedbackPacket, latestSupportCase, now, context.Locale),
                BuildTelemetryRollup(manifest, context, feedbackPacket, latestCrashWorkItem, now, context.Locale),
                BuildRetentionClocks(manifest, latestSupportCase, latestCrashWorkItem, now, context.Locale),
                BuildCaseStatusFollowthrough(manifest, latestSupportCase, concierge, now, context.Locale)
            ]);
    }

    private static PrivacyBoundedSupportStatusProjection BuildSupportStatus(
        PublicReleaseManifestDto manifest,
        SupportCaseProjection? latestSupportCase,
        InstallAwareSupportConciergePacket? concierge,
        DateTimeOffset now,
        string locale)
    {
        string route = latestSupportCase is null
            ? "/account/support"
            : concierge?.SupportCaseTruth.DetailHref ?? $"/account/support/{Uri.EscapeDataString(latestSupportCase.CaseId)}";
        string summary = latestSupportCase is null
            ? "Support status stays first-party and install-aware; when no tracked case exists yet, the account support page remains the safe place to continue."
            : $"{HumanizeStatus(latestSupportCase.Status)} support case {latestSupportCase.CaseId} keeps release and install follow-up visible on the account support page.";

        return new PrivacyBoundedSupportStatusProjection(
            ProjectionId: StableId("privacy-support-status", latestSupportCase?.CaseId ?? manifest.Version),
            SurfaceId: "support_status",
            Route: route,
            ComparisonRoute: "/contact#support-intake",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                latestSupportCase is null
                    ? "No tracked support case is active yet, so the support intake page remains the safe place to start."
                    : $"Case {latestSupportCase.CaseId} is currently {HumanizeStatus(latestSupportCase.Status).ToLowerInvariant()}.",
                concierge?.ReleaseExplainer.CorrectnessBasis ?? "Support status stays grounded in the same release status that powers downloads, install help, and fix availability.",
                ResolveFixAvailabilitySummary(manifest)
            ],
            Actions:
            [
                new PrivacyBoundedSupportStatusActionProjection("open_account_support", "Open account support", route, "Review the tracked case or the account support page."),
                new PrivacyBoundedSupportStatusActionProjection("open_support_intake", "Open support intake", "/contact#support-intake", "Start first-party intake when no tracked case exists yet."),
                new PrivacyBoundedSupportStatusActionProjection("open_current_release", "Open current release", "/now", "Compare support posture with the same current release status.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestSupportCase?.CaseId);
    }

    private static PrivacyBoundedSupportStatusProjection BuildCrashStatus(
        PublicReleaseManifestDto manifest,
        CrashWorkItemProjection? latestCrashWorkItem,
        DateTimeOffset now,
        string locale)
    {
        string summary = latestCrashWorkItem is null
            ? "Crash status stays privacy-bounded; user surfaces only show routed work-item state, not raw crash envelopes or telemetry blobs."
            : $"{HumanizeStatus(latestCrashWorkItem.Status)} crash work item {latestCrashWorkItem.WorkItemId} keeps bounded triage state visible without exposing raw diagnostics.";

        return new PrivacyBoundedSupportStatusProjection(
            ProjectionId: StableId("privacy-crash-status", latestCrashWorkItem?.WorkItemId ?? manifest.Version),
            SurfaceId: "crash_status",
            Route: "/api/v1/support/crashes/work-items",
            ComparisonRoute: "/account/support",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                latestCrashWorkItem is null
                    ? "Crash status remains empty until a bounded work item exists."
                    : $"Work item {latestCrashWorkItem.WorkItemId} is owned by {latestCrashWorkItem.CandidateOwnerRepo} and currently tracks {latestCrashWorkItem.OccurrenceCount.ToString(CultureInfo.InvariantCulture)} occurrences.",
                "Crash surfaces may expose status, repo ownership, and bounded release context, but not raw crash envelopes or log tails.",
                latestCrashWorkItem is null
                    ? "No bounded crash work item is active yet."
                    : $"The crash work item still reports {latestCrashWorkItem.RegistryContext.ReleaseChannel ?? "unknown"} {latestCrashWorkItem.RegistryContext.ApplicationVersion ?? "unknown"}."
            ],
            Actions:
            [
                new PrivacyBoundedSupportStatusActionProjection("open_crash_work_items", "Open crash work items", "/api/v1/support/crashes/work-items", "Inspect bounded crash triage state."),
                new PrivacyBoundedSupportStatusActionProjection("open_account_support", "Open account support", "/account/support", "Compare crash routing with tracked support followthrough."),
                new PrivacyBoundedSupportStatusActionProjection("open_privacy", "Open privacy", "/privacy", "Check the privacy boundary that keeps raw diagnostics off user surfaces.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestCrashWorkItem?.WorkItemId);
    }

    private static PrivacyBoundedSupportStatusProjection BuildFeedbackStatus(
        PublicReleaseManifestDto manifest,
        SignalToCanonPacketProjection? feedbackPacket,
        SupportCaseProjection? latestSupportCase,
        DateTimeOffset now,
        string locale)
    {
        string route = feedbackPacket?.DestinationRoute ?? "/participate?productlift=feedback#productlift-feedback";
        if (string.Equals(route, "/participate?source=feedback#public-feedback", StringComparison.OrdinalIgnoreCase)
            || string.Equals(route, "/participate?productlift=feedback#productlift-feedback", StringComparison.OrdinalIgnoreCase))
        {
            route = "/participate?productlift=feedback#productlift-feedback";
        }
        string summary = feedbackPacket is null
            ? "Feedback stays privacy-bounded until it is classified on the Participate page and reviewed for product work."
            : "Feedback stays bounded to the Participate page instead of becoming support folklore or telemetry surveillance.";

        return new PrivacyBoundedSupportStatusProjection(
            ProjectionId: StableId("privacy-feedback-status", feedbackPacket?.PacketId ?? latestSupportCase?.CaseId ?? manifest.Version),
            SurfaceId: "feedback_status",
            Route: route,
            ComparisonRoute: "/contact#support-intake",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                feedbackPacket?.Summary ?? "Feedback should be classified before it influences queue or release decisions.",
                feedbackPacket is null
                    ? "Private or account-linked follow-up still belongs on the first-party support route."
                    : feedbackPacket.CloseoutPosture,
                latestSupportCase is null
                    ? "No private follow-up case is active right now."
                    : $"Private follow-up can still attach to support case {latestSupportCase.CaseId} when the feedback needs account-linked closure."
            ],
            Actions:
            [
                new PrivacyBoundedSupportStatusActionProjection("open_feedback_lane", "Open feedback", route, "Review the first-party feedback path."),
                new PrivacyBoundedSupportStatusActionProjection("open_participate", "Open Participate", "/participate", "Inspect the broader public feedback intake."),
                new PrivacyBoundedSupportStatusActionProjection("open_support_intake", "Open support intake", "/contact#support-intake", "Escalate private or account-linked feedback through first-party support.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: feedbackPacket?.PacketId ?? latestSupportCase?.CaseId);
    }

    private static PrivacyBoundedSupportStatusProjection BuildTelemetryRollup(
        PublicReleaseManifestDto manifest,
        PrivacyBoundedSupportStatusContext context,
        SignalToCanonPacketProjection? feedbackPacket,
        CrashWorkItemProjection? latestCrashWorkItem,
        DateTimeOffset now,
        string locale)
    {
        int supportCount = context.SupportCases?.Count ?? 0;
        int crashCount = context.CrashWorkItems?.Count ?? 0;
        int installCount = context.InstallLinking?.ClaimedInstallations?.Count ?? 0;
        int feedbackCount = feedbackPacket is null ? 0 : 1;
        string summary = $"Telemetry rollups stay privacy-bounded to counts and route-safe state: {supportCount} support cases, {crashCount} crash work items, {feedbackCount} reviewed feedback item, and {installCount} claimed installs.";

        return new PrivacyBoundedSupportStatusProjection(
            ProjectionId: StableId("privacy-telemetry-rollup", $"{supportCount}:{crashCount}:{installCount}:{feedbackCount}:{manifest.Version}"),
            SurfaceId: "telemetry_rollup",
            Route: "/progress",
            ComparisonRoute: "/privacy",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                "Telemetry rollups may expose counts, statuses, and queue-safe summaries, but not raw crash envelopes, provider traces, or account-internal survey payloads.",
                latestCrashWorkItem is null
                    ? "No crash work item is active, so the rollup only reports bounded support and install state."
                    : $"The latest bounded crash rollup points at {latestCrashWorkItem.WorkItemId}, not the raw incident envelope.",
                feedbackPacket is null
                    ? "No reviewed feedback item is active yet."
                    : $"The reviewed feedback rollup stays on {feedbackPacket.DestinationRoute}."
            ],
            Actions:
            [
                new PrivacyBoundedSupportStatusActionProjection("open_progress", "Open progress", "/progress", "Review public program telemetry that stays customer-safe."),
                new PrivacyBoundedSupportStatusActionProjection("open_privacy", "Open privacy", "/privacy", "Inspect the privacy boundary that explains what telemetry may and may not surface."),
                new PrivacyBoundedSupportStatusActionProjection("open_account_support", "Open account support", "/account/support", "Compare the rollup with tracked case followthrough when deeper status is needed.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: manifest.Version);
    }

    private static PrivacyBoundedSupportStatusProjection BuildRetentionClocks(
        PublicReleaseManifestDto manifest,
        SupportCaseProjection? latestSupportCase,
        CrashWorkItemProjection? latestCrashWorkItem,
        DateTimeOffset now,
        string locale)
    {
        string supportClock = latestSupportCase is null
            ? "No tracked support case clock is running yet."
            : $"Support case {latestSupportCase.CaseId} was updated {DescribeAge(now - latestSupportCase.UpdatedAtUtc)} ago.";
        string crashClock = latestCrashWorkItem is null
            ? "No crash work-item clock is running yet."
            : $"Crash work item {latestCrashWorkItem.WorkItemId} was updated {DescribeAge(now - latestCrashWorkItem.LastSeenAtUtc)} ago.";

        return new PrivacyBoundedSupportStatusProjection(
            ProjectionId: StableId("privacy-retention-clocks", $"{latestSupportCase?.CaseId}:{latestCrashWorkItem?.WorkItemId}:{manifest.Version}"),
            SurfaceId: "retention_clocks",
            Route: "/privacy",
            ComparisonRoute: "/account/support",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: "Retention clocks stay explicit: public routes expose bounded status and help, while account routes carry the user-safe slice of support and crash followthrough on a controlled clock.",
            EvidenceLines:
            [
                "Public surfaces may not expose private case notes, raw crash envelopes, provider traces, or account-internal survey payloads.",
                "Signed-in surfaces may expose case timeline, install posture, claimed-device state, and the user-safe slice of crash/support data.",
                $"{supportClock} {crashClock}"
            ],
            Actions:
            [
                new PrivacyBoundedSupportStatusActionProjection("open_privacy", "Open privacy", "/privacy", "Review the privacy and retention boundary."),
                new PrivacyBoundedSupportStatusActionProjection("open_account_support", "Open account support", "/account/support", "Inspect the signed-in support continuity that stays on the bounded clock."),
                new PrivacyBoundedSupportStatusActionProjection("open_status", "Open status", "/status", "Compare privacy and retention posture with the public release status.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestSupportCase?.CaseId ?? latestCrashWorkItem?.WorkItemId);
    }

    private static PrivacyBoundedSupportStatusProjection BuildCaseStatusFollowthrough(
        PublicReleaseManifestDto manifest,
        SupportCaseProjection? latestSupportCase,
        InstallAwareSupportConciergePacket? concierge,
        DateTimeOffset now,
        string locale)
    {
        string route = latestSupportCase is null
            ? "/account/support"
            : concierge?.SupportCaseTruth.DetailHref ?? $"/account/support/{Uri.EscapeDataString(latestSupportCase.CaseId)}";
        string comparisonRoute = "/api/v1/install-linking/continuation/support";
        string summary = latestSupportCase is null
            ? "Case-status followthrough starts on the first-party support rail and only becomes install-aware once a tracked case exists."
            : concierge?.SupportClosure.Summary ?? $"Case {latestSupportCase.CaseId} keeps first-party followthrough attached to the same install and release status.";

        return new PrivacyBoundedSupportStatusProjection(
            ProjectionId: StableId("privacy-case-followthrough", latestSupportCase?.CaseId ?? manifest.Version),
            SurfaceId: "case_status_followthrough",
            Route: route,
            ComparisonRoute: comparisonRoute,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                concierge?.SupportClosure.NextSafeAction ?? "Case followthrough stays on the first-party support rail until a concrete next action exists.",
                concierge?.SupportClosure.FollowUpLaneSummary ?? "Install-aware followthrough should stay on the support continuation lane rather than splitting into detached browser ritual.",
                concierge?.ReleaseExplainer.CorrectnessBasis ?? ResolveFixAvailabilitySummary(manifest)
            ],
            Actions:
            [
                new PrivacyBoundedSupportStatusActionProjection("open_case_followthrough", "Open tracked support", route, "Inspect the tracked case and next safe action."),
                new PrivacyBoundedSupportStatusActionProjection("open_support_continuation", "Open support continuation", comparisonRoute, "Keep install-aware followthrough on the same first-party support rail."),
                new PrivacyBoundedSupportStatusActionProjection("open_downloads", "Open downloads", "/downloads", "Compare case followthrough with the current release and installer shelf.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestSupportCase?.CaseId);
    }

    private static string ResolveProofStatus(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.ProofStatus) ? "unknown" : manifest.ProofStatus!;

    private static string ResolveSupportabilityState(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.SupportabilityState) ? "unknown" : manifest.SupportabilityState!;

    private static string ResolveFixAvailabilitySummary(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary)
            ? "Fix-availability guidance has not been published yet."
            : manifest.FixAvailabilitySummary!;

    private static string HumanizeStatus(string? status)
    {
        if (string.IsNullOrWhiteSpace(status))
        {
            return "Unknown";
        }

        return status
            .Replace('_', ' ')
            .Trim();
    }

    private static string DescribeAge(TimeSpan age)
    {
        if (age < TimeSpan.Zero)
        {
            age = TimeSpan.Zero;
        }

        if (age.TotalMinutes < 1)
        {
            return "under a minute";
        }

        if (age.TotalHours < 1)
        {
            return $"{Math.Max(1, (int)Math.Round(age.TotalMinutes, MidpointRounding.AwayFromZero))} minutes";
        }

        if (age.TotalDays < 1)
        {
            return $"{Math.Max(1, (int)Math.Round(age.TotalHours, MidpointRounding.AwayFromZero))} hours";
        }

        return $"{Math.Max(1, (int)Math.Round(age.TotalDays, MidpointRounding.AwayFromZero))} days";
    }

    private static string StableId(string prefix, string seed)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes($"{prefix}:{seed}"));
        return $"{prefix}:{Convert.ToHexString(digest[..8]).ToLowerInvariant()}";
    }
}
