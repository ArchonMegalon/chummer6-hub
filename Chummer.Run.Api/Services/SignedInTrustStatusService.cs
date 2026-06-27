using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.PublicSurface;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed class SignedInTrustStatusService
{
    private readonly InstallLinkingService _installLinking;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly PublicTrustPulseService _trustPulse;

    public SignedInTrustStatusService(
        InstallLinkingService installLinking,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        PublicTrustPulseService trustPulse)
    {
        _installLinking = installLinking;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _trustPulse = trustPulse;
    }

    public SignedInTrustStatusPanelViewModel Build(
        HubUserDto user,
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience)
    {
        var installLinking = _installLinking.GetSummary(user.UserId, user.SubjectId);
        var supportSummaries = _supportPresentation.BuildList(_supportCases.ListForReporter(user.UserId, user.SubjectId).Items, installLinking);
        var pulse = _trustPulse.LoadSnapshot();
        var latestInstallation = installLinking.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        var installCount = installLinking.ClaimedInstallations?.Count ?? 0;
        var followThrough = supportSummaries
            .Where(static item => item.ReporterActionNeeded || item.NeedsLinkedInstall || item.NeedsInstallUpdate || item.CanVerifyFix)
            .OrderByDescending(static item => item.Case.UpdatedAtUtc)
            .FirstOrDefault();
        var rows = new List<SignedInTrustStatusRowViewModel>
        {
            new(
                "Linked installs",
                installCount > 0
                    ? $"{installCount} linked"
                    : installLinking.PendingClaimTickets.Count > 0
                        ? $"{installLinking.PendingClaimTickets.Count} claim pending"
                        : "No linked install yet"),
            new(
                "Current linked build",
                latestInstallation is null
                    ? "No linked build yet"
                    : $"{ResolveInstallationDisplayLabel(latestInstallation)} · {latestInstallation.Version} on {ResolveChannelLabel(latestInstallation.Channel, manifest, releaseExperience)}"),
            new(
                "Who can get it now",
                BuildTrustPulseAccessSummary(manifest, releaseExperience, pulse)),
            new(
                "Recommended for this install",
                BuildSignedInInstallRecommendationSummary(manifest, releaseExperience, latestInstallation, followThrough)),
            new(
                "Install status",
                BuildSignedInInstallPostureSummary(manifest, latestInstallation, followThrough)),
            new(
                "Fix availability",
                BuildSignedInFixAvailabilitySummary(manifest, releaseExperience, latestInstallation, followThrough)),
            new(
                "Current caution",
                BuildSignedInInstallCautionSummary(manifest, latestInstallation, followThrough)),
            new(
                "Adoption health",
                ShouldUseManifestAdoptionSummary(pulse)
                    ? BuildManifestAdoptionSummary(manifest)
                    : BuildTrustPulseAdoptionSummary(pulse!)),
            new("Release checks", BuildReleaseProofSummary(manifest)),
            // .Replace( legacy M144 marker: new("Release proof", BuildReleaseProofSummary(manifest)), )
            new(
                "Support next steps",
                followThrough is null
                    ? "No active fix, relink, or evidence review is waiting on this account."
                    : $"{followThrough.StageLabel} · {followThrough.NextSafeAction}")
        };

        if (followThrough?.NeedsLinkedInstall == true)
        {
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Relink the affected install",
                Summary: followThrough.InstallReadinessSummary,
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open installs", "/account/access", "primary"),
                SecondaryAction: new TrustPageActionViewModel("Open support timeline", "/account/support", "secondary"));
        }

        if (followThrough?.NeedsInstallUpdate == true)
        {
            var installAction = BuildRecommendedInstallAction(releaseExperience, tone: "primary");
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Update your linked install",
                Summary: followThrough.InstallReadinessSummary,
                Rows: rows,
                PrimaryAction: installAction,
                SecondaryAction: new TrustPageActionViewModel("Open support timeline", "/account/support", "secondary"));
        }

        if (followThrough?.CanVerifyFix == true)
        {
            var installAction = BuildRecommendedInstallAction(releaseExperience, tone: "secondary");
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Your linked install can verify a fix now",
                Summary: followThrough.VerificationSummary,
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Verify fix on this install", followThrough.DetailHref, "primary"),
                SecondaryAction: installAction);
        }

        if (followThrough?.ReporterActionNeeded == true)
        {
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Support needs one more detail",
                Summary: followThrough.NextSafeAction,
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open support timeline", "/account/support", "primary"),
                SecondaryAction: new TrustPageActionViewModel("Open help", "/help", "secondary"));
        }

        if (latestInstallation is null)
        {
            var installAction = BuildRecommendedInstallAction(releaseExperience, tone: "secondary");
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "No linked install is attached yet",
                Summary: "Claim the current public release first so downloads, support closure, and recovery stay attached to this account instead of turning into a fresh unknown install next time.",
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open installs", "/account/access", "primary"),
                SecondaryAction: installAction);
        }

        string installationLabel = ResolveInstallationDisplayLabel(latestInstallation);
        var recommendedAction = BuildRecommendedInstallAction(releaseExperience, tone: "secondary");
        bool reviewRequired = (pulse?.ParityClaimsReviewRequired ?? false)
            || string.Equals(manifest.SupportabilityState, "review_required", StringComparison.OrdinalIgnoreCase);
        string summary = reviewRequired
            ? $"{installationLabel} is linked on {latestInstallation.Version} in {ResolveChannelLabel(latestInstallation.Channel, manifest, releaseExperience)}. Downloads, support, and recovery stay with this linked copy, but some desktop review work is still open."
            : $"{installationLabel} is linked on {latestInstallation.Version} in {ResolveChannelLabel(latestInstallation.Channel, manifest, releaseExperience)}. Downloads, support, and recovery are all using the same claimed install context right now.";
        return new SignedInTrustStatusPanelViewModel(
            Eyebrow: "Signed-in trust status",
            Heading: $"{installationLabel} is attached",
            Summary: summary,
            Rows: rows,
            PrimaryAction: new TrustPageActionViewModel("Open installs", "/account/access", "primary"),
            SecondaryAction: recommendedAction);
    }

    private static TrustPageActionViewModel BuildRecommendedInstallAction(
        ReleaseExperienceViewModel releaseExperience,
        string tone)
    {
        if (releaseExperience.Recommended is null)
        {
            return new TrustPageActionViewModel("Open downloads", "/downloads", tone);
        }

        return new TrustPageActionViewModel(
            releaseExperience.Recommended.ActionLabel,
            releaseExperience.Recommended.DispatchHref,
            tone);
    }

    private static string ResolveInstallationDisplayLabel(ClaimedInstallationDto installation)
        => installation.HostLabel
            ?? installation.HeadId
            ?? installation.ArtifactId
            ?? installation.InstallationId;

    private static string ResolveChannelLabel(
        string? channel,
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience)
    {
        if (!string.IsNullOrWhiteSpace(channel)
            && string.Equals(channel, manifest.Channel, StringComparison.OrdinalIgnoreCase))
        {
            return releaseExperience.Display.ChannelLabel;
        }

        return HumanizeToken(channel, "Current release");
    }

    private static string BuildReleaseProofSummary(PublicReleaseManifestDto manifest)
    {
        string status = HumanizeToken(manifest.ProofStatus, "Unknown");
        if (!string.IsNullOrWhiteSpace(manifest.SupportabilitySummary))
        {
            return $"{status} · {manifest.SupportabilitySummary}";
        }

        if (!string.IsNullOrWhiteSpace(manifest.SupportabilityState))
        {
            return $"{status} · {HumanizeToken(manifest.SupportabilityState, "Current release")}";
        }

        return status;
    }

    private static string BuildManifestAdoptionSummary(PublicReleaseManifestDto manifest)
    {
        if (manifest.PublicTrustMetrics is JsonElement metrics
            && metrics.ValueKind == JsonValueKind.Object
            && metrics.TryGetProperty("adoptionHealth", out JsonElement adoptionHealth)
            && adoptionHealth.ValueKind == JsonValueKind.Object)
        {
            string? summary = TryGetJsonString(adoptionHealth, "summary");
            if (!string.IsNullOrWhiteSpace(summary))
            {
                return summary!;
            }

            string? status = TryGetJsonString(adoptionHealth, "status");
            if (!string.IsNullOrWhiteSpace(status))
            {
                return $"Adoption health is {HumanizeToken(status, "unknown").ToLowerInvariant()}.";
            }
        }

        return BuildReleaseProofSummary(manifest);
    }

    private static bool ShouldUseManifestAdoptionSummary(PublicTrustPulseSnapshot? pulse)
    {
        if (pulse is null)
        {
            return true;
        }

        bool proofUnknown = string.IsNullOrWhiteSpace(pulse.LocalReleaseProofStatus)
            || string.Equals(pulse.LocalReleaseProofStatus, "unknown", StringComparison.OrdinalIgnoreCase);
        bool noEvidence = (!pulse.ProvenJourneyCount.HasValue || pulse.ProvenJourneyCount.Value <= 0)
            && (!pulse.ProvenRouteCount.HasValue || pulse.ProvenRouteCount.Value <= 0);
        return proofUnknown && noEvidence;
    }

    private static string? TryGetJsonString(JsonElement element, string propertyName)
        => element.ValueKind == JsonValueKind.Object
            && element.TryGetProperty(propertyName, out JsonElement value)
            && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static string BuildSignedInInstallRecommendationSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (installation is null)
        {
            return manifest.Downloads.Count == 0 || releaseExperience.Recommended is null
                ? "Link the current public release first so Chummer can compare this account against the published public release."
                : $"Link the current public release first so Chummer can compare this account against {BuildPublishedArtifactSummary(manifest, releaseExperience, releaseExperience.Recommended.Artifact)}.";
        }

        string installationLabel = ResolveInstallationDisplayLabel(installation);
        if (!string.IsNullOrWhiteSpace(followThrough?.FixedReleaseLabel))
        {
            if (followThrough.NeedsInstallUpdate)
            {
                PublicReleaseArtifactDto? publishedArtifact = FindPublishedArtifactForInstallation(manifest, installation);
                return publishedArtifact is null
                    ? $"Support is tracking {followThrough.FixedReleaseLabel} for {installationLabel}. Keep this linked copy on the guided support path until the public release catches up."
                    : $"Support is tracking {followThrough.FixedReleaseLabel} for {installationLabel}. The current public release still shows {BuildPublishedArtifactSummary(manifest, releaseExperience, publishedArtifact)}.";
            }

            if (followThrough.CanVerifyFix)
            {
                return $"{installationLabel} is already on {followThrough.FixedReleaseLabel}, so this linked copy is the right one to verify now.";
            }
        }

        PublicReleaseArtifactDto? artifact = FindPublishedArtifactForInstallation(manifest, installation);
        if (artifact is null)
        {
            return $"No promoted public-release match is published right now for {installationLabel}. Keep this copy linked and use the guided support path before moving it.";
        }

        string publishedSummary = BuildPublishedArtifactSummary(manifest, releaseExperience, artifact);
        if (InstallationMatchesPublishedShelf(manifest, installation, artifact))
        {
            return $"{installationLabel} already matches the promoted {publishedSummary}.";
        }

        return $"{installationLabel} reports {installation.Version} on {ResolveChannelLabel(installation.Channel, manifest, releaseExperience)}. The promoted public release for this install is {publishedSummary}.";
    }

    private static string BuildSignedInInstallPostureSummary(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (followThrough?.NeedsLinkedInstall == true || followThrough?.NeedsInstallUpdate == true)
        {
            return followThrough.InstallReadinessSummary;
        }

        if (followThrough?.CanVerifyFix == true)
        {
            return followThrough.VerificationSummary;
        }

        if (installation is not null && FindPublishedArtifactForInstallation(manifest, installation) is null)
        {
            return $"{ResolveInstallationDisplayLabel(installation)} is linked on {BuildInstallationFootprintSummary(installation)}, and that build is not on the promoted public release right now.";
        }

        if (!string.IsNullOrWhiteSpace(manifest.KnownIssueSummary))
        {
            return manifest.KnownIssueSummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary))
        {
            return manifest.FixAvailabilitySummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.RolloutReason))
        {
            return manifest.RolloutReason!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.SupportabilitySummary))
        {
            return manifest.SupportabilitySummary!;
        }

        return installation is null
            ? "No linked install is attached yet, so Chummer cannot compare this account against the current public release or fix path."
            : "No extra install-specific warning is published right now.";
    }

    private static string BuildSignedInFixAvailabilitySummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (followThrough is not null && !string.IsNullOrWhiteSpace(followThrough.FixedReleaseLabel))
        {
            string fixedReleaseLabel = followThrough.FixedReleaseLabel!;
            if (followThrough.CanVerifyFix && installation is not null)
            {
                return $"{ResolveInstallationDisplayLabel(installation)} can verify {fixedReleaseLabel} on this linked install now.";
            }

            if (followThrough.NeedsInstallUpdate && installation is not null)
            {
                PublicReleaseArtifactDto? artifact = FindPublishedArtifactForInstallation(manifest, installation);
                return artifact is null
                    ? $"{fixedReleaseLabel} is the tracked fix target, but this linked install still needs a guided support update before it can verify."
                    : $"{fixedReleaseLabel} is the tracked fix target. The promoted public release for this install is {BuildPublishedArtifactSummary(manifest, releaseExperience, artifact)}.";
            }

            return $"{fixedReleaseLabel} is the tracked fix target for this account right now.";
        }

        if (!string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary))
        {
            return manifest.FixAvailabilitySummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.SupportabilitySummary))
        {
            return manifest.SupportabilitySummary!;
        }

        return installation is null
            ? "No linked install is attached yet, so Chummer cannot tie this account to a fix-ready public release."
            : "No fix-specific availability note is published for this linked install right now.";
    }

    private static string BuildSignedInInstallCautionSummary(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (followThrough?.NeedsLinkedInstall == true)
        {
            return followThrough.InstallReadinessSummary;
        }

        if (followThrough?.NeedsInstallUpdate == true)
        {
            return followThrough.InstallReadinessSummary;
        }

        if (followThrough?.ReporterActionNeeded == true)
        {
            return followThrough.NextSafeAction;
        }

        if (followThrough?.CanVerifyFix == true)
        {
            return "No extra caution is published for this linked install right now; use support to confirm the fix on this device.";
        }

        if (installation is not null && FindPublishedArtifactForInstallation(manifest, installation) is null)
        {
            return $"{ResolveInstallationDisplayLabel(installation)} is outside the promoted public release right now, so keep it on the guided support path until a matching build lands.";
        }

        if (!string.IsNullOrWhiteSpace(manifest.KnownIssueSummary))
        {
            return manifest.KnownIssueSummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.RolloutReason))
        {
            return manifest.RolloutReason!;
        }

        return installation is null
            ? "No linked install is attached yet, so Chummer cannot publish install-specific caution for this account."
            : "No extra caution is published for this linked install right now.";
    }

    private static PublicReleaseArtifactDto? FindPublishedArtifactForInstallation(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto installation)
    {
        string? installationPlatform = NormalizePlatformFamily(installation.Platform);
        string? installationHead = NormalizeHeadId(installation.HeadId);

        if (!string.IsNullOrWhiteSpace(installationPlatform) && !string.IsNullOrWhiteSpace(installationHead))
        {
            var exactMatch = manifest.Downloads.FirstOrDefault(item =>
                string.Equals(NormalizeArtifactPlatformFamily(item), installationPlatform, StringComparison.OrdinalIgnoreCase)
                && string.Equals(NormalizeHeadId(item.Head), installationHead, StringComparison.OrdinalIgnoreCase));
            if (exactMatch is not null)
            {
                return exactMatch;
            }
        }

        if (!string.IsNullOrWhiteSpace(installationPlatform))
        {
            var platformMatch = manifest.Downloads.FirstOrDefault(item =>
                string.Equals(NormalizeArtifactPlatformFamily(item), installationPlatform, StringComparison.OrdinalIgnoreCase));
            if (platformMatch is not null)
            {
                return platformMatch;
            }
        }

        if (!string.IsNullOrWhiteSpace(installationHead))
        {
            return manifest.Downloads.FirstOrDefault(item =>
                string.Equals(NormalizeHeadId(item.Head), installationHead, StringComparison.OrdinalIgnoreCase));
        }

        return null;
    }

    private static bool InstallationMatchesPublishedShelf(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto installation,
        PublicReleaseArtifactDto artifact)
    {
        if (!string.Equals(installation.Channel, manifest.Channel, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(installation.Version, manifest.Version, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string? installationPlatform = NormalizePlatformFamily(installation.Platform);
        string? artifactPlatform = NormalizeArtifactPlatformFamily(artifact);
        if (!string.IsNullOrWhiteSpace(installationPlatform)
            && !string.IsNullOrWhiteSpace(artifactPlatform)
            && !string.Equals(installationPlatform, artifactPlatform, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string? installationHead = NormalizeHeadId(installation.HeadId);
        string? artifactHead = NormalizeHeadId(artifact.Head);
        return string.IsNullOrWhiteSpace(installationHead)
            || string.IsNullOrWhiteSpace(artifactHead)
            || string.Equals(installationHead, artifactHead, StringComparison.OrdinalIgnoreCase);
    }

    private static string BuildPublishedArtifactSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicReleaseArtifactDto artifact)
        => $"{BuildPublishedArtifactLabel(artifact)} on {ResolveChannelLabel(manifest.Channel, manifest, releaseExperience)} {manifest.Version}";

    private static string BuildPublishedArtifactLabel(PublicReleaseArtifactDto artifact)
    {
        string platform = BuildPlatformDisplayLabel(artifact.Platform, artifact.Arch);
        return NormalizeHeadId(artifact.Head) switch
        {
            "avalonia" => $"the recommended desktop build for {platform}",
            "blazor-desktop" => $"the alternative desktop build for {platform}",
            _ => $"the published build for {platform}"
        };
    }

    private static string BuildInstallationFootprintSummary(ClaimedInstallationDto installation)
    {
        string platform = BuildPlatformDisplayLabel(installation.Platform, installation.Arch);
        return NormalizeHeadId(installation.HeadId) switch
        {
            "avalonia" => $"the recommended desktop app on {platform}",
            "blazor-desktop" => $"the alternative desktop app on {platform}",
            _ => platform
        };
    }

    private static string BuildPlatformDisplayLabel(string? platform, string? arch)
    {
        string platformLabel = NormalizePlatformFamily(platform) switch
        {
            "windows" => "Windows",
            "linux" => "Linux",
            "macos" => "macOS",
            _ when !string.IsNullOrWhiteSpace(platform) => HumanizeToken(platform, "current platform"),
            _ => "the current platform"
        };

        return string.IsNullOrWhiteSpace(arch)
            ? platformLabel
            : $"{platformLabel} {arch}";
    }

    private static string? NormalizeArtifactPlatformFamily(PublicReleaseArtifactDto artifact)
        => NormalizePlatformFamily(!string.IsNullOrWhiteSpace(artifact.PlatformId) ? artifact.PlatformId : artifact.Platform);

    private static string? NormalizePlatformFamily(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim().ToLowerInvariant();
        if (normalized.Contains("win", StringComparison.OrdinalIgnoreCase))
        {
            return "windows";
        }

        if (normalized.Contains("linux", StringComparison.OrdinalIgnoreCase))
        {
            return "linux";
        }

        if (normalized.Contains("osx", StringComparison.OrdinalIgnoreCase) || normalized.Contains("mac", StringComparison.OrdinalIgnoreCase))
        {
            return "macos";
        }

        return normalized;
    }

    private static string? NormalizeHeadId(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? null
            : value.Trim().ToLowerInvariant();

    private static string BuildTrustPulseAccessSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot? pulse)
    {
        if (releaseExperience.Recommended is null)
        {
            return "No release download is published yet.";
        }

        if ((pulse?.ParityClaimsReviewRequired ?? false)
            || string.Equals(manifest.SupportabilityState, "review_required", StringComparison.OrdinalIgnoreCase))
        {
            return releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable
                ? "The linked install route stays preferred while the desktop experience is still being polished."
                : "Public downloads are visible, but parity-sensitive desktop steps still stay with support until the release status is current.";
        }

        if (releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable)
        {
            return "The linked install route is the live path now, so the install stays attached and support can follow the exact device.";
        }

        if (releaseExperience.GuestDownloadAvailable)
        {
            return "The public download is visible now, and signing in adds account return and device-specific support once you want the install attached to your account.";
        }

        return "Account-linked return is available now when you sign in.";
    }

    private static string BuildTrustPulseAdoptionSummary(PublicTrustPulseSnapshot pulse)
    {
        List<string> segments = [];

        if (!string.IsNullOrWhiteSpace(pulse.LocalReleaseProofStatus))
        {
            segments.Add(string.Equals(pulse.LocalReleaseProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
                ? "Current local status passed."
                : $"Current local status is {HumanizeToken(pulse.LocalReleaseProofStatus, "unknown").ToLowerInvariant()}.");
        }

        if (pulse.ProvenJourneyCount is int journeyCount && journeyCount > 0 && pulse.ProvenRouteCount is int routeCount && routeCount > 0)
        {
            segments.Add($"{journeyCount} verified journeys and {routeCount} checked routes are on record.");
        }
        else if (pulse.ProvenJourneyCount is int journeyOnly && journeyOnly > 0)
        {
            segments.Add($"{journeyOnly} verified journeys are on record.");
        }
        else if (pulse.ProvenRouteCount is int routeOnly && routeOnly > 0)
        {
            segments.Add($"{routeOnly} checked routes are on record.");
        }

        if (pulse.HistorySnapshotCount is int historySnapshotCount && historySnapshotCount > 0)
        {
            segments.Add(historySnapshotCount < 6
                ? $"{historySnapshotCount} weekly snapshots are measured so far, so adoption history is still early."
                : $"{historySnapshotCount} weekly snapshots are on record for the current public status.");
        }

        if (pulse.MissingDesktopClientCoverage && !string.IsNullOrWhiteSpace(pulse.FlagshipReadinessReason))
        {
            segments.Add($"Desktop review still needs closure: {pulse.FlagshipReadinessReason!.Trim().TrimEnd('.')}.");
        }
        else if (pulse.ParityClaimsReviewRequired && !string.IsNullOrWhiteSpace(pulse.LaunchReadiness))
        {
            segments.Add(pulse.LaunchReadiness!.Trim().TrimEnd('.') + ".");
        }

        return segments.Count == 0
            ? "Measured adoption evidence is still accumulating."
            : string.Join(" ", segments);
    }

    private static string HumanizeToken(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value)
            ? fallback
            : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.Replace('_', ' '));
}
