using System.Globalization;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportConciergePacketService
{
    private const string PackageId = "next90-m111-hub-support-concierge";
    private const int MilestoneId = 111;
    private const long FrontierId = 2746902416;

    private readonly PublicReleaseManifestService _releases;
    private readonly SupportCasePresentationService _supportPresentation;

    public SupportConciergePacketService(
        PublicReleaseManifestService releases,
        SupportCasePresentationService supportPresentation)
    {
        _releases = releases;
        _supportPresentation = supportPresentation;
    }

    public InstallAwareSupportConciergePacket Build(
        SupportCaseProjection supportCase,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(supportCase);

        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        SupportCasePresentationViewModel presentation = _supportPresentation.Build(supportCase, installLinking);
        ClaimedInstallationDto? installation = ResolveInstallation(supportCase, installLinking?.ClaimedInstallations);
        PublicReleaseArtifactDto? artifact = ResolveArtifact(manifest, supportCase, installation);
        string? installedBuildReceiptId = ExtractInstalledBuildReceiptId(supportCase.Detail);
        string? supportChannel = Normalize(supportCase.ReleaseChannel) ?? Normalize(installation?.Channel);
        string? supportVersion = Normalize(supportCase.ApplicationVersion) ?? Normalize(installation?.Version);
        string releaseChannel = Normalize(supportCase.FixedChannel) ?? manifest.Channel;
        string releaseVersion = Normalize(supportCase.FixedVersion) ?? manifest.Version;
        string releaseLabel = BuildReleaseLabel(releaseChannel, releaseVersion);
        string installedLabel = BuildReleaseLabel(supportChannel, supportVersion);
        bool channelAgrees = BuildChannelAgreement(supportChannel, supportCase.FixedChannel, manifest.Channel);
        bool supportCaseTruthPresent = !string.IsNullOrWhiteSpace(supportCase.CaseId)
            && !string.IsNullOrWhiteSpace(supportCase.Status)
            && !string.IsNullOrWhiteSpace(supportCase.Kind);

        InstallAwareBuildTruth installedTruth = new(
            InstallationId: Normalize(supportCase.InstallationId) ?? Normalize(installation?.InstallationId),
            ApplicationVersion: supportVersion,
            ReleaseChannel: supportChannel,
            HeadId: Normalize(supportCase.HeadId) ?? Normalize(installation?.HeadId),
            Platform: Normalize(supportCase.Platform) ?? Normalize(installation?.Platform),
            Arch: Normalize(supportCase.Arch) ?? Normalize(installation?.Arch),
            InstalledBuildReceiptId: installedBuildReceiptId,
            TruthSource: installation is null ? "support_case" : "support_case+claimed_install");

        InstallAwareReleaseTruth releaseTruth = new(
            ManifestVersion: manifest.Version,
            ManifestChannel: manifest.Channel,
            ManifestStatus: manifest.Status,
            ManifestPublishedAtUtc: manifest.PublishedAt.ToUniversalTime(),
            FixedVersion: Normalize(supportCase.FixedVersion),
            FixedChannel: Normalize(supportCase.FixedChannel),
            CurrentArtifactId: artifact?.Id,
            ArtifactHeadId: artifact?.Head,
            ArtifactPlatform: artifact?.PlatformId ?? artifact?.Platform,
            ArtifactArch: artifact?.Arch,
            ArtifactSha256: artifact?.Sha256,
            ArtifactUrl: artifact?.Url,
            ChannelAgreesWithInstalledBuild: channelAgrees);

        SupportCaseConciergeTruth supportTruth = new(
            CaseId: supportCase.CaseId,
            Kind: supportCase.Kind,
            Status: supportCase.Status,
            StageLabel: presentation.StageLabel,
            ReporterVerificationState: Normalize(supportCase.ReporterVerificationState),
            ReporterVerifiedAtUtc: supportCase.ReporterVerifiedAtUtc?.ToUniversalTime(),
            ReleasedToReporterChannelAtUtc: supportCase.ReleasedToReporterChannelAtUtc?.ToUniversalTime(),
            UserNotifiedAtUtc: supportCase.UserNotifiedAtUtc?.ToUniversalTime(),
            DetailHref: presentation.DetailHref,
            PrimaryActionHref: presentation.PrimaryActionHref,
            CanVerifyFix: presentation.CanVerifyFix,
            NeedsInstallUpdate: presentation.NeedsInstallUpdate,
            NeedsLinkedInstall: presentation.NeedsLinkedInstall);

        IReadOnlyList<string> routes = BuildRoutes(supportCase, artifact);
        string correctnessBasis = BuildCorrectnessBasis(supportCase, installedLabel, releaseLabel, installedBuildReceiptId, channelAgrees);
        SupportClosureReadiness closureReadiness = BuildClosureReadiness(presentation, installedTruth, releaseTruth, supportTruth);
        InstalledToReleaseDelta installedToReleaseDelta = BuildInstalledToReleaseDelta(installedTruth, releaseTruth);

        return new InstallAwareSupportConciergePacket(
            ContractName: "chummer6-hub.install_aware_support_concierge.v1",
            PackageId: PackageId,
            MilestoneId: MilestoneId,
            FrontierId: FrontierId,
            BuiltAtUtc: DateTimeOffset.UtcNow,
            IsInstallAware: HasInstalledBuildTruth(installedTruth) && supportCaseTruthPresent,
            InstalledBuildTruth: installedTruth,
            ReleaseTruth: releaseTruth,
            SupportCaseTruth: supportTruth,
            SupportClosure: new SupportClosureConciergePacket(
                PacketId: $"support-closure:{supportCase.CaseId}",
                Headline: presentation.StageLabel,
                Summary: presentation.ClosureSummary,
                NextSafeAction: presentation.NextSafeAction,
                VerificationSummary: presentation.VerificationSummary,
                FollowUpLaneSummary: presentation.FollowUpLaneSummary,
                ReporterActionNeeded: presentation.ReporterActionNeeded,
                ClosureReadiness: closureReadiness,
                FirstPartyRoutes: routes),
            ReleaseExplainer: new ReleaseExplainerConciergePacket(
                PacketId: $"release-explainer:{supportCase.CaseId}:{NormalizeToken(artifact?.Id ?? releaseLabel)}",
                Headline: $"Why {releaseLabel} is the next release for this case",
                Summary: BuildReleaseExplainerSummary(presentation, installedLabel, releaseLabel, artifact),
                CorrectnessBasis: correctnessBasis,
                FallbackPosture: BuildFallbackPosture(presentation, artifact),
                InstalledToReleaseDelta: installedToReleaseDelta,
                FirstPartyRoutes: routes),
            PublicTrustWrapper: new PublicConciergeTrustWrapper(
                Summary: "Public help and downloads may point to this bounded concierge packet, but installed-build truth, support history, and verification stay on signed-in first-party Hub surfaces.",
                PublicRoutes: routes.Where(static route => route.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase) || route.StartsWith("/contact", StringComparison.OrdinalIgnoreCase)).ToArray(),
                AuthenticatedRoutes: routes.Where(static route => route.StartsWith("/account", StringComparison.OrdinalIgnoreCase) || route.StartsWith("/api/", StringComparison.OrdinalIgnoreCase)).ToArray(),
                FirstPartyOnlyTruth: true));
    }

    private static ClaimedInstallationDto? ResolveInstallation(
        SupportCaseProjection supportCase,
        IReadOnlyList<ClaimedInstallationDto>? installations)
    {
        if (installations is not { Count: > 0 })
        {
            return null;
        }

        string? installationId = Normalize(supportCase.InstallationId);
        if (installationId is not null)
        {
            ClaimedInstallationDto? exact = installations.FirstOrDefault(item =>
                string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase));
            if (exact is not null)
            {
                return exact;
            }
        }

        return installations
            .Select(item => new { Installation = item, Score = ScoreInstallation(item, supportCase) })
            .OrderByDescending(static item => item.Score)
            .ThenByDescending(static item => item.Installation.UpdatedAtUtc)
            .FirstOrDefault(static item => item.Score > 0)
            ?.Installation;
    }

    private static int ScoreInstallation(ClaimedInstallationDto installation, SupportCaseProjection supportCase)
    {
        int score = 0;
        score += ScoreField(installation.Version, supportCase.ApplicationVersion, 16);
        score += ScoreField(installation.Channel, supportCase.ReleaseChannel, 8);
        score += ScoreField(installation.HeadId, supportCase.HeadId, 4);
        score += ScoreField(installation.Platform, supportCase.Platform, 2);
        score += ScoreField(installation.Arch, supportCase.Arch, 1);
        return score;
    }

    private static int ScoreField(string? left, string? right, int value)
        => !string.IsNullOrWhiteSpace(left)
           && !string.IsNullOrWhiteSpace(right)
           && string.Equals(left, right, StringComparison.OrdinalIgnoreCase)
            ? value
            : 0;

    private static PublicReleaseArtifactDto? ResolveArtifact(
        PublicReleaseManifestDto manifest,
        SupportCaseProjection supportCase,
        ClaimedInstallationDto? installation)
    {
        string? platform = Normalize(supportCase.Platform) ?? Normalize(installation?.Platform);
        string? head = Normalize(supportCase.HeadId) ?? Normalize(installation?.HeadId);
        string? arch = Normalize(supportCase.Arch) ?? Normalize(installation?.Arch);
        PublicReleaseArtifactDto? exact = manifest.Downloads.FirstOrDefault(item =>
            Matches(item.Head, head)
            && (Matches(item.PlatformId, platform) || Matches(item.Platform, platform))
            && Matches(item.Arch, arch));
        if (exact is not null)
        {
            return exact;
        }

        PublicReleaseArtifactDto? platformMatch = manifest.Downloads.FirstOrDefault(item =>
            Matches(item.PlatformId, platform) || Matches(item.Platform, platform));
        if (platformMatch is not null)
        {
            return platformMatch;
        }

        return manifest.Downloads.FirstOrDefault(item => Matches(item.Head, head));
    }

    private static bool Matches(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
           && !string.IsNullOrWhiteSpace(right)
           && string.Equals(left, right, StringComparison.OrdinalIgnoreCase);

    private static IReadOnlyList<string> BuildRoutes(SupportCaseProjection supportCase, PublicReleaseArtifactDto? artifact)
    {
        List<string> routes =
        [
            $"/api/v1/support/cases/{Uri.EscapeDataString(supportCase.CaseId)}/concierge",
            $"/account/support/{Uri.EscapeDataString(supportCase.CaseId)}",
            "/account/support",
            "/account/access",
            "/api/v1/install-linking/continuation",
            "/api/v1/install-linking/continuation/support",
            "/contact#support-intake",
            "/downloads"
        ];

        if (!string.IsNullOrWhiteSpace(artifact?.Id))
        {
            routes.Add($"/downloads/install/{Uri.EscapeDataString(artifact.Id)}");
        }

        return routes.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
    }

    private static string BuildReleaseExplainerSummary(
        SupportCasePresentationViewModel presentation,
        string installedLabel,
        string releaseLabel,
        PublicReleaseArtifactDto? artifact)
    {
        string artifactLabel = string.IsNullOrWhiteSpace(artifact?.Id)
            ? "the matching published artifact"
            : artifact.Id;
        return $"{presentation.ReleaseProgressSummary} The release explainer compares installed {installedLabel} with {releaseLabel} and points to {artifactLabel}.";
    }

    private static string BuildCorrectnessBasis(
        SupportCaseProjection supportCase,
        string installedLabel,
        string releaseLabel,
        string? installedBuildReceiptId,
        bool channelAgrees)
    {
        string receipt = string.IsNullOrWhiteSpace(installedBuildReceiptId)
            ? "no installed-build receipt id was embedded in case detail"
            : $"installed-build receipt {installedBuildReceiptId}";
        string channelPosture = channelAgrees
            ? "channel truth agrees"
            : "channel truth needs support-directed handling";
        return $"Case {supportCase.CaseId} binds {installedLabel}, {releaseLabel}, {receipt}, and support status {supportCase.Status}; {channelPosture}.";
    }

    private static bool BuildChannelAgreement(string? installedChannel, string? fixedChannel, string manifestChannel)
    {
        if (string.IsNullOrWhiteSpace(installedChannel))
        {
            return false;
        }

        string releaseChannel = Normalize(fixedChannel) ?? manifestChannel;
        return string.Equals(installedChannel, releaseChannel, StringComparison.OrdinalIgnoreCase);
    }

    private static string BuildFallbackPosture(SupportCasePresentationViewModel presentation, PublicReleaseArtifactDto? artifact)
    {
        if (presentation.NeedsLinkedInstall)
        {
            return "Do not close from public release copy alone. Reclaim the affected install before fix confirmation.";
        }

        if (presentation.NeedsInstallUpdate)
        {
            return "Keep the previous installed copy available, update on the same linked install, and verify before reopening or closing.";
        }

        return artifact is null
            ? "Release artifact truth is not published for this install yet; keep support-directed recovery as the fallback."
            : "Use the same linked install and published artifact; public help is a wrapper, not the source of closure truth.";
    }

    private static SupportClosureReadiness BuildClosureReadiness(
        SupportCasePresentationViewModel presentation,
        InstallAwareBuildTruth installedTruth,
        InstallAwareReleaseTruth releaseTruth,
        SupportCaseConciergeTruth supportTruth)
    {
        bool installedBuildComplete = HasInstalledBuildTruth(installedTruth);
        bool releaseArtifactReady = !string.IsNullOrWhiteSpace(releaseTruth.CurrentArtifactId)
            && !string.IsNullOrWhiteSpace(releaseTruth.ArtifactSha256)
            && !string.IsNullOrWhiteSpace(releaseTruth.ArtifactUrl);
        bool reporterCanClose = !presentation.NeedsLinkedInstall
            && !presentation.NeedsInstallUpdate
            && supportTruth.CanVerifyFix
            && releaseArtifactReady
            && installedBuildComplete
            && releaseTruth.ChannelAgreesWithInstalledBuild;

        return new SupportClosureReadiness(
            InstalledBuildComplete: installedBuildComplete,
            ReleaseArtifactReady: releaseArtifactReady,
            ReporterCanClose: reporterCanClose,
            BlockerSummary: BuildClosureBlockerSummary(presentation, installedBuildComplete, releaseArtifactReady, releaseTruth.ChannelAgreesWithInstalledBuild));
    }

    private static string BuildClosureBlockerSummary(
        SupportCasePresentationViewModel presentation,
        bool installedBuildComplete,
        bool releaseArtifactReady,
        bool channelAgrees)
    {
        List<string> blockers = [];
        if (!installedBuildComplete)
        {
            blockers.Add("installed build truth is incomplete");
        }

        if (!releaseArtifactReady)
        {
            blockers.Add("published artifact proof is incomplete");
        }

        if (!channelAgrees)
        {
            blockers.Add("installed channel and release channel do not agree");
        }

        if (presentation.NeedsLinkedInstall)
        {
            blockers.Add("the reporter still needs a linked install");
        }

        if (presentation.NeedsInstallUpdate)
        {
            blockers.Add("the reporter still needs to update before verification");
        }

        return blockers.Count == 0
            ? "support closure is ready for reporter verification on the linked install"
            : string.Join("; ", blockers);
    }

    private static bool HasInstalledBuildTruth(InstallAwareBuildTruth installedTruth)
        => HasConcreteInstalledValue(installedTruth.ApplicationVersion)
           && HasConcreteInstalledValue(installedTruth.ReleaseChannel)
           && !string.IsNullOrWhiteSpace(installedTruth.HeadId)
           && !string.IsNullOrWhiteSpace(installedTruth.Platform)
           && !string.IsNullOrWhiteSpace(installedTruth.Arch)
           && HasConcreteInstalledReceiptId(installedTruth.InstalledBuildReceiptId);

    private static bool HasConcreteInstalledValue(string? value)
        => !string.IsNullOrWhiteSpace(value)
           && !string.Equals(value, "unknown", StringComparison.OrdinalIgnoreCase)
           && !value.StartsWith("unknown-", StringComparison.OrdinalIgnoreCase);

    private static bool HasConcreteInstalledReceiptId(string? receiptId)
        => HasConcreteInstalledValue(receiptId)
           && !string.Equals(receiptId.Trim(), "pending", StringComparison.OrdinalIgnoreCase)
           && !string.Equals(receiptId.Trim(), "none", StringComparison.OrdinalIgnoreCase)
           && !string.Equals(receiptId.Trim(), "n/a", StringComparison.OrdinalIgnoreCase)
           && !receiptId.Trim().StartsWith("missing-", StringComparison.OrdinalIgnoreCase);

    private static InstalledToReleaseDelta BuildInstalledToReleaseDelta(
        InstallAwareBuildTruth installedTruth,
        InstallAwareReleaseTruth releaseTruth)
    {
        string installedVersion = Normalize(installedTruth.ApplicationVersion) ?? "unknown-version";
        string releaseVersion = Normalize(releaseTruth.FixedVersion) ?? releaseTruth.ManifestVersion;
        string installedChannel = Normalize(installedTruth.ReleaseChannel) ?? "unknown-channel";
        string releaseChannel = Normalize(releaseTruth.FixedChannel) ?? releaseTruth.ManifestChannel;
        bool versionChanges = !string.Equals(installedVersion, releaseVersion, StringComparison.OrdinalIgnoreCase);
        bool channelChanges = !string.Equals(installedChannel, releaseChannel, StringComparison.OrdinalIgnoreCase);
        bool artifactMatchesDevice = Matches(releaseTruth.ArtifactHeadId, installedTruth.HeadId)
            && Matches(releaseTruth.ArtifactPlatform, installedTruth.Platform)
            && Matches(releaseTruth.ArtifactArch, installedTruth.Arch);

        return new InstalledToReleaseDelta(
            InstalledVersion: installedVersion,
            ReleaseVersion: releaseVersion,
            InstalledChannel: installedChannel,
            ReleaseChannel: releaseChannel,
            VersionChanges: versionChanges,
            ChannelChanges: channelChanges,
            ArtifactMatchesInstalledDevice: artifactMatchesDevice);
    }

    private static string? ExtractInstalledBuildReceiptId(string? detail)
    {
        if (string.IsNullOrWhiteSpace(detail))
        {
            return null;
        }

        foreach (string line in detail.Split('\n', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
        {
            const string marker = "Installed build receipt:";
            if (!line.StartsWith(marker, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            return Normalize(line[marker.Length..]);
        }

        return null;
    }

    private static string BuildReleaseLabel(string? channel, string? version)
    {
        string normalizedChannel = Normalize(channel) ?? "unknown-channel";
        string normalizedVersion = Normalize(version) ?? "unknown-version";
        return string.Create(CultureInfo.InvariantCulture, $"{normalizedChannel} {normalizedVersion}");
    }

    private static string NormalizeToken(string value)
        => string.Concat(value.Select(static ch => char.IsLetterOrDigit(ch) ? char.ToLowerInvariant(ch) : '-')).Trim('-');

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}

public sealed record InstallAwareSupportConciergePacket(
    string ContractName,
    string PackageId,
    int MilestoneId,
    long FrontierId,
    DateTimeOffset BuiltAtUtc,
    bool IsInstallAware,
    InstallAwareBuildTruth InstalledBuildTruth,
    InstallAwareReleaseTruth ReleaseTruth,
    SupportCaseConciergeTruth SupportCaseTruth,
    SupportClosureConciergePacket SupportClosure,
    ReleaseExplainerConciergePacket ReleaseExplainer,
    PublicConciergeTrustWrapper PublicTrustWrapper);

public sealed record InstallAwareBuildTruth(
    string? InstallationId,
    string? ApplicationVersion,
    string? ReleaseChannel,
    string? HeadId,
    string? Platform,
    string? Arch,
    string? InstalledBuildReceiptId,
    string TruthSource);

public sealed record InstallAwareReleaseTruth(
    string ManifestVersion,
    string ManifestChannel,
    string? ManifestStatus,
    DateTimeOffset ManifestPublishedAtUtc,
    string? FixedVersion,
    string? FixedChannel,
    string? CurrentArtifactId,
    string? ArtifactHeadId,
    string? ArtifactPlatform,
    string? ArtifactArch,
    string? ArtifactSha256,
    string? ArtifactUrl,
    bool ChannelAgreesWithInstalledBuild);

public sealed record SupportCaseConciergeTruth(
    string CaseId,
    string Kind,
    string Status,
    string StageLabel,
    string? ReporterVerificationState,
    DateTimeOffset? ReporterVerifiedAtUtc,
    DateTimeOffset? ReleasedToReporterChannelAtUtc,
    DateTimeOffset? UserNotifiedAtUtc,
    string DetailHref,
    string PrimaryActionHref,
    bool CanVerifyFix,
    bool NeedsInstallUpdate,
    bool NeedsLinkedInstall);

public sealed record SupportClosureConciergePacket(
    string PacketId,
    string Headline,
    string Summary,
    string NextSafeAction,
    string VerificationSummary,
    string FollowUpLaneSummary,
    bool ReporterActionNeeded,
    SupportClosureReadiness ClosureReadiness,
    IReadOnlyList<string> FirstPartyRoutes);

public sealed record ReleaseExplainerConciergePacket(
    string PacketId,
    string Headline,
    string Summary,
    string CorrectnessBasis,
    string FallbackPosture,
    InstalledToReleaseDelta InstalledToReleaseDelta,
    IReadOnlyList<string> FirstPartyRoutes);

public sealed record SupportClosureReadiness(
    bool InstalledBuildComplete,
    bool ReleaseArtifactReady,
    bool ReporterCanClose,
    string BlockerSummary);

public sealed record InstalledToReleaseDelta(
    string InstalledVersion,
    string ReleaseVersion,
    string InstalledChannel,
    string ReleaseChannel,
    bool VersionChanges,
    bool ChannelChanges,
    bool ArtifactMatchesInstalledDevice);

public sealed record PublicConciergeTrustWrapper(
    string Summary,
    IReadOnlyList<string> PublicRoutes,
    IReadOnlyList<string> AuthenticatedRoutes,
    bool FirstPartyOnlyTruth);
