using System.Security.Cryptography;
using System.Text;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class RegistryTruthBindingService
{
    private readonly PublicReleaseManifestService _releases;
    private readonly SupportConciergePacketService _supportConciergePackets;

    public RegistryTruthBindingService(
        PublicReleaseManifestService releases,
        SupportConciergePacketService supportConciergePackets)
    {
        _releases = releases;
        _supportConciergePackets = supportConciergePackets;
    }

    public RegistryTruthBindingBundle Build(RegistryTruthBindingContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        DateTimeOffset now = DateTimeOffset.UtcNow;
        List<RegistryTruthBindingProjection> bindings = [];
        SupportCaseProjection? supportCase = context.SupportCases?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        ClaimedInstallationDto? installation = context.InstallLinking?.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        DownloadReceiptDto? receipt = context.InstallLinking?.RecentReceipts?
            .OrderByDescending(static item => item.IssuedAtUtc)
            .FirstOrDefault();
        PublicReleaseArtifactDto? artifact = ResolveArtifact(manifest, installation, receipt);

        bindings.Add(BuildDownloadsBinding(manifest, artifact, now, context.Locale));
        bindings.Add(BuildInstallHelpBinding(manifest, artifact, now, context.Locale));
        AddIfNotNull(bindings, BuildAccountAwareGuidanceBinding(manifest, artifact, installation, receipt, now, context.Locale));
        AddIfNotNull(bindings, BuildSupportRecoveryBinding(manifest, artifact, supportCase, context.InstallLinking, now, context.Locale));
        bindings.Add(BuildPublicReleaseShelfBinding(manifest, artifact, now, context.Locale));

        return new RegistryTruthBindingBundle(
            BuiltAtUtc: now,
            Bindings: bindings);
    }

    private static RegistryTruthBindingProjection BuildDownloadsBinding(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? artifact,
        DateTimeOffset now,
        string locale)
    {
        string summary = $"Downloads stays bound to registry-owned {manifest.Channel} {manifest.Version}, so the installer shelf, proof posture, and supportability lane cannot drift apart.";
        return new RegistryTruthBindingProjection(
            BindingId: StableId("registry-truth-downloads", manifest.Version),
            SurfaceId: "downloads",
            Route: "/downloads",
            ComparisonRoute: "/now",
            RegistrySource: ResolveRegistrySource(manifest),
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            FixAvailabilitySummary: ResolveFixAvailabilitySummary(manifest),
            Summary: summary,
            EvidenceLines:
            [
                artifact is null
                    ? "Downloads has no current promoted artifact yet, so the shelf must stay quiet about install posture."
                    : $"{artifact.Id} is the current promoted release artifact on the downloads shelf.",
                $"{ResolveProofStatus(manifest)} proof and {ResolveSupportabilityState(manifest)} supportability come from the same registry manifest chain.",
                ResolveFixAvailabilitySummary(manifest)
            ],
            Actions:
            [
                new RegistryTruthBindingActionProjection("open_downloads", "Open downloads", "/downloads", "Inspect the live installer shelf tied to the current registry manifest."),
                new RegistryTruthBindingActionProjection("open_current_release", "Open current release", "/now", "Compare the same registry release truth on the public current-release shelf."),
                new RegistryTruthBindingActionProjection("open_status", "Open status", "/status", "Check the mirrored proof and caution lane without inventing a second release story.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: artifact?.Id ?? manifest.Version);
    }

    private static RegistryTruthBindingProjection BuildInstallHelpBinding(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? artifact,
        DateTimeOffset now,
        string locale)
    {
        string summary = "Known issues and install help stays on the downloads rail, but every caution, fix note, and supportability line still comes from registry truth.";
        return new RegistryTruthBindingProjection(
            BindingId: StableId("registry-truth-install-help", manifest.Version),
            SurfaceId: "install_help",
            Route: "/downloads",
            ComparisonRoute: "/status",
            RegistrySource: ResolveRegistrySource(manifest),
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            FixAvailabilitySummary: ResolveFixAvailabilitySummary(manifest),
            Summary: summary,
            EvidenceLines:
            [
                "Known issues stay on downloads.",
                $"Current supportability posture is {ResolveSupportabilityState(manifest)}.",
                ResolveFixAvailabilitySummary(manifest)
            ],
            Actions:
            [
                new RegistryTruthBindingActionProjection("open_downloads_help", "Open install help", "/downloads", "Keep install questions on the downloads rail where registry-backed cautions already live."),
                new RegistryTruthBindingActionProjection("open_status", "Open status", "/status", "Inspect deeper proof and caution evidence when install help needs more than the page summary."),
                new RegistryTruthBindingActionProjection("open_current_release", "Open current release", "/now", "Compare the current release page before escalating into support.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: artifact?.Id ?? manifest.Version);
    }

    private static RegistryTruthBindingProjection? BuildAccountAwareGuidanceBinding(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? artifact,
        ClaimedInstallationDto? installation,
        DownloadReceiptDto? receipt,
        DateTimeOffset now,
        string locale)
    {
        if (installation is null && receipt is null)
        {
            return null;
        }

        string sourceId = installation?.InstallationId ?? receipt!.ReceiptId;
        string comparisonRoute = string.IsNullOrWhiteSpace(artifact?.Id)
            ? "/downloads"
            : $"/downloads/install/{Uri.EscapeDataString(artifact.Id)}";
        string summary = installation is not null
            ? $"Account-aware guidance keeps claimed install {installation.Platform ?? "desktop"} {installation.Version} on registry-backed release truth without changing the published bytes."
            : $"Receipt {receipt!.ReceiptId} keeps the public download path open while account-linked return stays attached to first-party install truth.";

        return new RegistryTruthBindingProjection(
            BindingId: StableId("registry-truth-account-aware", sourceId),
            SurfaceId: "account_aware_guidance",
            Route: "/account/access",
            ComparisonRoute: comparisonRoute,
            RegistrySource: ResolveRegistrySource(manifest),
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            FixAvailabilitySummary: ResolveFixAvailabilitySummary(manifest),
            Summary: summary,
            EvidenceLines:
            [
                "The published packages stay the same for every user; only the short-lived setup assistant and install claims become account-aware.",
                installation is null
                    ? $"Download receipt {receipt!.ReceiptId} is the first-party install anchor."
                    : $"Claimed installation {installation.InstallationId} keeps continuity on /account/access.",
                $"{ResolveProofStatus(manifest)} proof and {ResolveSupportabilityState(manifest)} supportability still come from the release registry."
            ],
            Actions:
            [
                new RegistryTruthBindingActionProjection("open_account_access", "Open Devices & access", "/account/access", "Review the signed-in account-return rail."),
                new RegistryTruthBindingActionProjection("open_install_handoff", "Open install route", comparisonRoute, "Compare account-linked return with the same published installer route."),
                new RegistryTruthBindingActionProjection("open_downloads", "Open downloads", "/downloads", "Return to the public downloads page that still points at the same bytes.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: sourceId);
    }

    private RegistryTruthBindingProjection? BuildSupportRecoveryBinding(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? artifact,
        SupportCaseProjection? supportCase,
        InstallLinkingSummaryDto? installLinking,
        DateTimeOffset now,
        string locale)
    {
        if (supportCase is null && installLinking is null)
        {
            return null;
        }

        if (supportCase is not null)
        {
            var concierge = _supportConciergePackets.Build(supportCase, installLinking);
            string detailRoute = concierge.SupportCaseTruth.DetailHref ?? "/account/support";
            string summary = $"{concierge.SupportClosure.Summary} Support recovery stays tied to registry-backed release truth before any recovery step is suggested.";
            return new RegistryTruthBindingProjection(
                BindingId: StableId("registry-truth-support-recovery", supportCase.CaseId),
                SurfaceId: "support_recovery",
                Route: "/api/v1/install-linking/continuation/support",
                ComparisonRoute: detailRoute,
                RegistrySource: ResolveRegistrySource(manifest),
                ReleaseChannel: manifest.Channel,
                ReleaseVersion: manifest.Version,
                ProofStatus: ResolveProofStatus(manifest),
                SupportabilityState: ResolveSupportabilityState(manifest),
                FixAvailabilitySummary: ResolveFixAvailabilitySummary(manifest),
                Summary: summary,
                EvidenceLines:
                [
                    concierge.ReleaseExplainer.CorrectnessBasis,
                    concierge.SupportClosure.FollowUpLaneSummary,
                    artifact is null
                        ? "Support recovery has no promoted artifact route yet, so recovery must stay on first-party support surfaces."
                        : $"{artifact.Id} is the promoted release artifact named by the same recovery lane."
                ],
                Actions:
                [
                    new RegistryTruthBindingActionProjection("open_support_continuation", "Open support continuation", "/api/v1/install-linking/continuation/support", "Keep install-aware recovery on the first-party continuation rail."),
                    new RegistryTruthBindingActionProjection("open_tracked_support", "Open tracked support", detailRoute, "Inspect the support case that carries the same install and release truth."),
                    new RegistryTruthBindingActionProjection("open_downloads", "Open downloads", string.IsNullOrWhiteSpace(artifact?.Id) ? "/downloads" : $"/downloads/install/{Uri.EscapeDataString(artifact!.Id)}", "Compare the recovery lane against the promoted installer shelf.")
                ],
                EmittedAtUtc: now,
                Locale: locale,
                SourceId: supportCase.CaseId);
        }

        string genericSummary = "Support recovery stays first-party and install-aware; when release truth is missing, the recovery lane must say so instead of inventing a detached workaround.";
        return new RegistryTruthBindingProjection(
            BindingId: StableId("registry-truth-support-recovery", manifest.Version),
            SurfaceId: "support_recovery",
            Route: "/api/v1/install-linking/continuation/support",
            ComparisonRoute: "/contact#support-intake",
            RegistrySource: ResolveRegistrySource(manifest),
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            FixAvailabilitySummary: ResolveFixAvailabilitySummary(manifest),
            Summary: genericSummary,
            EvidenceLines:
            [
                "Support recovery remains on the first-party install continuation rail.",
                $"{ResolveProofStatus(manifest)} proof and {ResolveSupportabilityState(manifest)} supportability still come from the registry manifest chain.",
                ResolveFixAvailabilitySummary(manifest)
            ],
            Actions:
            [
                new RegistryTruthBindingActionProjection("open_support_continuation", "Open support continuation", "/api/v1/install-linking/continuation/support", "Start first-party support recovery with install identity attached."),
                new RegistryTruthBindingActionProjection("open_contact", "Open support intake", "/contact#support-intake", "Escalate into first-party support intake when the install rail cannot resolve the issue."),
                new RegistryTruthBindingActionProjection("open_downloads", "Open downloads", string.IsNullOrWhiteSpace(artifact?.Id) ? "/downloads" : $"/downloads/install/{Uri.EscapeDataString(artifact!.Id)}", "Compare support recovery with the promoted installer shelf.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: manifest.Version);
    }

    private static RegistryTruthBindingProjection BuildPublicReleaseShelfBinding(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? artifact,
        DateTimeOffset now,
        string locale)
    {
        string summary = $"The public release shelf keeps /now, /status, and /downloads on the same registry-owned {manifest.Channel} {manifest.Version} truth chain.";
        return new RegistryTruthBindingProjection(
            BindingId: StableId("registry-truth-public-shelf", manifest.Version),
            SurfaceId: "public_release_shelf",
            Route: "/now",
            ComparisonRoute: "/status",
            RegistrySource: ResolveRegistrySource(manifest),
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            FixAvailabilitySummary: ResolveFixAvailabilitySummary(manifest),
            Summary: summary,
            EvidenceLines:
            [
                artifact is null
                    ? "The current release shelf does not yet name a promoted artifact."
                    : $"{artifact.Id} is the promoted artifact shared by the public release shelf and downloads.",
                $"Public release proof is {ResolveProofStatus(manifest)}.",
                ResolveFixAvailabilitySummary(manifest)
            ],
            Actions:
            [
                new RegistryTruthBindingActionProjection("open_current_release", "Open current release", "/now", "Inspect the public release shelf backed by the registry manifest."),
                new RegistryTruthBindingActionProjection("open_status", "Open status", "/status", "Compare proof and caution posture on the mirrored status route."),
                new RegistryTruthBindingActionProjection("open_downloads", "Open downloads", "/downloads", "Check the same release truth on the install shelf.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: artifact?.Id ?? manifest.Version);
    }

    private static PublicReleaseArtifactDto? ResolveArtifact(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto? installation,
        DownloadReceiptDto? receipt)
    {
        string? artifactId = installation?.ArtifactId ?? receipt?.ArtifactId;
        if (!string.IsNullOrWhiteSpace(artifactId))
        {
            PublicReleaseArtifactDto? exact = manifest.Downloads.FirstOrDefault(item =>
                string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
            if (exact is not null)
            {
                return exact;
            }
        }

        string? platform = installation?.Platform ?? receipt?.Platform;
        string? arch = installation?.Arch ?? receipt?.Arch;
        PublicReleaseArtifactDto? platformMatch = manifest.Downloads.FirstOrDefault(item =>
            (!string.IsNullOrWhiteSpace(item.PlatformId) && string.Equals(item.PlatformId, platform, StringComparison.OrdinalIgnoreCase)
             || !string.IsNullOrWhiteSpace(item.Platform) && string.Equals(item.Platform, platform, StringComparison.OrdinalIgnoreCase))
            && string.Equals(item.Arch, arch, StringComparison.OrdinalIgnoreCase));
        return platformMatch ?? manifest.Downloads.FirstOrDefault();
    }

    private static string ResolveRegistrySource(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.Source)
            ? "registry"
            : manifest.Source!;

    private static string ResolveProofStatus(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.ProofStatus)
            ? "unknown"
            : manifest.ProofStatus!;

    private static string ResolveSupportabilityState(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.SupportabilityState)
            ? "unknown"
            : manifest.SupportabilityState!;

    private static string ResolveFixAvailabilitySummary(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary)
            ? "Registry truth has not published a fix-availability summary yet."
            : manifest.FixAvailabilitySummary!;

    private static void AddIfNotNull(
        ICollection<RegistryTruthBindingProjection> bindings,
        RegistryTruthBindingProjection? binding)
    {
        if (binding is not null)
        {
            bindings.Add(binding);
        }
    }

    private static string StableId(string prefix, string seed)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes($"{prefix}:{seed}"));
        return $"{prefix}:{Convert.ToHexString(digest[..8]).ToLowerInvariant()}";
    }
}
