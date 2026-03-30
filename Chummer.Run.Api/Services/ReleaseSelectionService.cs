using Chummer.Run.Api.ViewModels;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class ReleaseSelectionService
{
    private readonly PublicCanonFileLoader _canon;
    private const string ExperienceRelativePath = ".codex-design/product/PUBLIC_RELEASE_EXPERIENCE.yaml";
    private const string PlatformAcceptanceRelativePath = ".codex-design/product/DESKTOP_PLATFORM_ACCEPTANCE_MATRIX.yaml";
    private const string DefaultGuestReadableChannel = "stable";

    public ReleaseSelectionService(PublicCanonFileLoader canon)
    {
        _canon = canon;
    }

    public PublicReleaseManifestDto ApplyAccessPolicy(PublicReleaseManifestDto manifest)
    {
        var experience = LoadExperience();
        var platformAcceptance = LoadPlatformAcceptance();
        return ApplyAccessPolicy(manifest, experience, platformAcceptance);
    }

    public bool HasGuestReadableDownloads(PublicReleaseManifestDto manifest)
    {
        var normalizedManifest = ApplyAccessPolicy(manifest);
        return normalizedManifest.Downloads.Any(static artifact =>
            !string.Equals(artifact.InstallAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase));
    }

    public bool RequiresAccount(PublicReleaseArtifactDto artifact)
        => string.Equals(NormalizeInstallAccessClass(artifact.InstallAccessClass), InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase);

    public ReleaseExperienceViewModel BuildExperience(PublicReleaseManifestDto manifest, string userAgent, bool authenticated)
    {
        var experience = LoadExperience();
        var platformAcceptance = LoadPlatformAcceptance();
        manifest = ApplyAccessPolicy(manifest, experience, platformAcceptance);
        var requestedPlatform = DetectPreferredPlatform(userAgent);
        var shelfNotice = BuildPlatformShelfNotice(manifest, platformAcceptance, requestedPlatform);

        var installers = manifest.Downloads.Where(IsInstaller).ToArray();
        var manualDownloads = manifest.Downloads.Where(download => !IsInstaller(download)).ToArray();
        var recommended = SelectRecommendedDownload(installers.Length > 0 ? installers : manifest.Downloads, userAgent);
        var recommendedPlatform = PlatformFamily(recommended);
        var alternativeInstallers = installers
            .Where(download => !string.Equals(download.Id, recommended?.Id, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        var alternatives = alternativeInstallers
            .Where(download => string.Equals(PlatformFamily(download), recommendedPlatform, StringComparison.OrdinalIgnoreCase))
            .OrderBy(static download => HeadPriority(download))
            .ToArray();
        var otherPlatforms = alternativeInstallers
            .Where(download => !string.Equals(PlatformFamily(download), recommendedPlatform, StringComparison.OrdinalIgnoreCase))
            .OrderBy(static download => PlatformPriority(download))
            .ThenBy(static download => HeadPriority(download))
            .ThenBy(static download => PlatformLabel(download), StringComparer.OrdinalIgnoreCase)
            .ToArray();
        var recommendedRequiresAccount = recommended is not null && RequiresAccount(recommended);
        var installSteps = recommendedRequiresAccount
            ? (experience.AccountRequiredInstallSteps?.Count > 0 ? experience.AccountRequiredInstallSteps : experience.InstallSteps) ?? new List<string>()
            : experience.InstallSteps ?? new List<string>();
        var guestGateArtifactHref = recommended is null
            ? "/downloads"
            : BuildSignupDispatchHref(recommended);
        var guestGateSignInHref = recommended is null
            ? "/login?next=/downloads"
            : BuildLoginDispatchHref(recommended);

        return new ReleaseExperienceViewModel(
            Display: BuildDisplay(manifest, experience),
            Recommended: recommended is null ? null : BuildOption(manifest, recommended, authenticated, recommended: true),
            Alternatives: alternatives.Select(download => BuildOption(manifest, download, authenticated, recommended: false)).ToArray(),
            OtherPlatforms: otherPlatforms.Select(download => BuildOption(manifest, download, authenticated, recommended: false)).ToArray(),
            ManualPackages: manualDownloads.Select(download => BuildOption(manifest, download, authenticated, recommended: false)).ToArray(),
            ReleaseNotesSummary: experience.ReleaseNotesSummary,
            KnownIssuesLabel: experience.KnownIssuesLabel,
            KnownIssuesHref: experience.KnownIssuesHref,
            InstallHelpLabel: experience.InstallHelpLabel,
            InstallHelpHref: experience.InstallHelpHref,
            UpdatePostureSummary: experience.UpdatePostureSummary,
            GuestDownloadAvailable: manifest.Downloads.Any(static artifact =>
                !string.Equals(artifact.InstallAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase)),
            PlatformShelfNoticeTitle: shelfNotice?.Title,
            PlatformShelfNoticeSummary: shelfNotice?.Summary,
            RequestedPlatformLabel: RequestedPlatformLabel(requestedPlatform),
            GuestGateHeading: experience.GuestGateHeading,
            GuestGateSummary: experience.GuestGateSummary,
            GuestGatePrimaryLabel: experience.GuestGatePrimaryLabel,
            GuestGatePrimaryHref: guestGateArtifactHref,
            GuestGateSecondaryLabel: experience.GuestGateSecondaryLabel,
            GuestGateSecondaryHref: guestGateSignInHref,
            PublicPreviewPrimaryLabel: experience.PublicPreviewPrimaryLabel,
            PublicPreviewPrimaryHref: experience.PublicPreviewPrimaryHref,
            NoBuildPrimaryLabel: experience.NoBuildPrimaryLabel,
            NoBuildPrimaryHref: experience.NoBuildPrimaryHref,
            SignedInDispatchHeading: experience.SignedInDispatchHeading,
            SignedInDispatchSummary: experience.SignedInDispatchSummary,
            SignedInDispatchSteps: experience.SignedInDispatchSteps ?? new List<string>(),
            InstallSteps: installSteps,
            SystemRequirements: RequirementsFor(experience, recommended, requestedPlatform, shelfNotice is not null));
    }

    public PublicLandingActionDto BuildPublicPrimaryAction(PublicReleaseManifestDto manifest, bool authenticated)
    {
        var release = BuildExperience(manifest, string.Empty, authenticated);
        if (manifest.Downloads.Count == 0)
        {
            return new PublicLandingActionDto(release.NoBuildPrimaryLabel, release.NoBuildPrimaryHref, "primary");
        }

        if (authenticated || HasGuestReadableDownloads(manifest))
        {
            return new PublicLandingActionDto(release.PublicPreviewPrimaryLabel, release.PublicPreviewPrimaryHref, "primary");
        }

        return new PublicLandingActionDto(release.GuestGatePrimaryLabel, release.GuestGatePrimaryHref, "primary");
    }

    public ReleaseOptionViewModel BuildOption(PublicReleaseManifestDto manifest, PublicReleaseArtifactDto download, bool authenticated, bool recommended)
    {
        manifest = ApplyAccessPolicy(manifest);
        var normalized = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, download.Id, StringComparison.OrdinalIgnoreCase))
            ?? download with
            {
                InstallAccessClass = ResolveInstallAccessClass(manifest.Channel, download.InstallAccessClass, LoadExperience())
            };
        return BuildNormalizedOption(normalized, authenticated, recommended);
    }

    private PublicReleaseExperienceDocument LoadExperience()
        => _canon.LoadRequiredYaml<PublicReleaseExperienceDocument>(ExperienceRelativePath);

    private DesktopPlatformAcceptanceDocument LoadPlatformAcceptance()
        => _canon.LoadRequiredYaml<DesktopPlatformAcceptanceDocument>(PlatformAcceptanceRelativePath);

    private static PublicReleaseManifestDto ApplyAccessPolicy(
        PublicReleaseManifestDto manifest,
        PublicReleaseExperienceDocument experience,
        DesktopPlatformAcceptanceDocument platformAcceptance)
        => manifest with
        {
            Downloads = manifest.Downloads
                .Where(download => IsPublicShelfVisible(download, platformAcceptance))
                .Select(download => download with
                {
                    InstallAccessClass = ResolveInstallAccessClass(manifest.Channel, download.InstallAccessClass, experience)
                })
                .ToArray()
        };

    private static ReleaseOptionViewModel BuildNormalizedOption(PublicReleaseArtifactDto download, bool authenticated, bool recommended)
    {
        var accessClass = NormalizeInstallAccessClass(download.InstallAccessClass) ?? InstallAccessClasses.AccountRequired;
        var requiresAccount = string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase);
        var guestDownloadAllowed = !requiresAccount;
        var artifactId = Uri.EscapeDataString(download.Id);
        var dispatchHref = authenticated
            ? $"/downloads/install/{artifactId}"
            : requiresAccount
                ? BuildSignupDispatchHref(download)
                : $"/downloads/get/{artifactId}";

        return new ReleaseOptionViewModel(
            Artifact: download with { InstallAccessClass = accessClass },
            Title: OptionTitle(download, recommended),
            DispatchHref: dispatchHref,
            DirectFileHref: $"/downloads/file/{artifactId}",
            PlatformLabel: PlatformLabel(download),
            HeadLabel: HeadLabel(download),
            SizeLabel: SizeLabel(download.SizeBytes),
            SupportLine: SupportLine(download, authenticated, accessClass, recommended),
            ActionLabel: ActionLabel(download, authenticated, accessClass, recommended),
            ShaPreview: string.IsNullOrWhiteSpace(download.Sha256) ? null : $"SHA {download.Sha256[..Math.Min(download.Sha256.Length, 16)]}...",
            Installer: IsInstaller(download),
            InstallAccessClass: accessClass,
            RequiresAccount: requiresAccount,
            GuestDownloadAllowed: guestDownloadAllowed);
    }

    private static IReadOnlyList<string> RequirementsFor(
        PublicReleaseExperienceDocument experience,
        PublicReleaseArtifactDto? recommended,
        string? requestedPlatform,
        bool requestedPlatformUnavailable)
        => ResolveRequirementsPlatform(recommended, requestedPlatform, requestedPlatformUnavailable) switch
        {
            "windows" => experience.WindowsRequirements ?? new List<string>(),
            "linux" => experience.LinuxRequirements ?? new List<string>(),
            "macos" => experience.MacosRequirements ?? new List<string>(),
            _ => experience.WindowsRequirements ?? new List<string>()
        };

    private static string ResolveRequirementsPlatform(PublicReleaseArtifactDto? recommended, string? requestedPlatform, bool requestedPlatformUnavailable)
        => requestedPlatformUnavailable && !string.IsNullOrWhiteSpace(requestedPlatform)
            ? requestedPlatform
            : PlatformFamily(recommended);

    private static ReleaseDisplayViewModel BuildDisplay(PublicReleaseManifestDto manifest, PublicReleaseExperienceDocument experience)
    {
        var channelLabel = ResolveChannelLabel(manifest.Channel, experience);
        var buildLabel = ResolveBuildLabel(manifest.Version, experience);
        var publishedLabel = $"Published {manifest.PublishedAt.ToUniversalTime():yyyy-MM-dd}";
        return new ReleaseDisplayViewModel(channelLabel, buildLabel, publishedLabel);
    }

    private static string ResolveChannelLabel(string? channel, PublicReleaseExperienceDocument experience)
    {
        var normalized = (channel ?? string.Empty).Trim();
        var mapped = (experience.PublicChannelLabels ?? new List<PublicReleaseChannelLabelDocument>())
            .FirstOrDefault(item => string.Equals(item.Id, normalized, StringComparison.OrdinalIgnoreCase));
        return !string.IsNullOrWhiteSpace(mapped?.Label)
            ? mapped.Label
            : experience.DefaultPublicChannelLabel;
    }

    private static string ResolveBuildLabel(string? version, PublicReleaseExperienceDocument experience)
    {
        var normalized = (version ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(normalized) || string.Equals(normalized, "unpublished", StringComparison.OrdinalIgnoreCase))
        {
            return experience.UnpublishedBuildLabel;
        }

        return $"{experience.BuildLabelPrefix} {normalized}";
    }

    private static string BuildSignupDispatchHref(PublicReleaseArtifactDto artifact)
        => $"/signup?next={Uri.EscapeDataString($"/downloads/install/{Uri.EscapeDataString(artifact.Id)}")}";

    private static string BuildLoginDispatchHref(PublicReleaseArtifactDto artifact)
        => $"/login?next={Uri.EscapeDataString($"/downloads/install/{Uri.EscapeDataString(artifact.Id)}")}";

    private static string ResolveInstallAccessClass(string channel, string? rawAccessClass, PublicReleaseExperienceDocument experience)
    {
        var guestReadableChannels = ResolveGuestReadableChannels(experience);
        var guestReadableChannel = guestReadableChannels.Contains(channel);
        var normalized = NormalizeInstallAccessClass(rawAccessClass);
        if (normalized is not null)
        {
            return !guestReadableChannel && string.Equals(normalized, InstallAccessClasses.OpenPublic, StringComparison.OrdinalIgnoreCase)
                ? InstallAccessClasses.AccountRequired
                : normalized;
        }

        return guestReadableChannel
            ? InstallAccessClasses.OpenPublic
            : InstallAccessClasses.AccountRequired;
    }

    private static HashSet<string> ResolveGuestReadableChannels(PublicReleaseExperienceDocument experience)
        => (experience.GuestReadableChannels ?? new List<string> { DefaultGuestReadableChannel })
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value.Trim())
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

    private static string? NormalizeInstallAccessClass(string? rawAccessClass)
    {
        if (string.IsNullOrWhiteSpace(rawAccessClass))
        {
            return null;
        }

        var normalized = rawAccessClass.Trim().Replace("-", "_", StringComparison.Ordinal).ToLowerInvariant();
        return normalized switch
        {
            InstallAccessClasses.OpenPublic => InstallAccessClasses.OpenPublic,
            InstallAccessClasses.AccountRecommended => InstallAccessClasses.AccountRecommended,
            InstallAccessClasses.AccountRequired => InstallAccessClasses.AccountRequired,
            _ => null
        };
    }

    private static PublicReleaseArtifactDto? SelectRecommendedDownload(IEnumerable<PublicReleaseArtifactDto> downloads, string userAgent)
    {
        var candidates = downloads.ToArray();
        if (candidates.Length == 0)
        {
            return null;
        }

        string? preferredPlatform = DetectPreferredPlatform(userAgent);

        var pool = preferredPlatform is null
            ? candidates
            : candidates.Where(download => string.Equals(PlatformFamily(download), preferredPlatform, StringComparison.OrdinalIgnoreCase)).ToArray();

        if (pool.Length == 0)
        {
            pool = candidates;
        }

        return pool
            .OrderByDescending(IsInstaller)
            .ThenBy(HeadPriority)
            .ThenBy(PlatformPriority)
            .FirstOrDefault();
    }

    private static bool IsInstaller(PublicReleaseArtifactDto download)
    {
        var kind = (download.Kind ?? string.Empty).Trim();
        if (kind.Length > 0)
        {
            return kind.Equals("installer", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("dmg", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("pkg", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("msix", StringComparison.OrdinalIgnoreCase);
        }

        return download.Url.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
               || download.Url.EndsWith(".deb", StringComparison.OrdinalIgnoreCase)
               || download.Url.EndsWith(".msi", StringComparison.OrdinalIgnoreCase)
               || download.Url.EndsWith(".dmg", StringComparison.OrdinalIgnoreCase)
               || download.Url.EndsWith(".pkg", StringComparison.OrdinalIgnoreCase)
               || download.Id.Contains("installer", StringComparison.OrdinalIgnoreCase);
    }

    private static string RecommendedSupport(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"This is the default recommended installer for {PlatformLabel(download)}."
            : $"This is the clearest current preview package for {PlatformLabel(download)}.";

    private static string AlternativeSupport(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Alternative desktop build for {PlatformLabel(download)}. Use this only when support sends you to a different build on the same platform."
            : $"Manual package for {PlatformLabel(download)}. Use this only for advanced or support-directed install work.";

    private static string SupportLine(PublicReleaseArtifactDto download, bool authenticated, string accessClass, bool recommended)
    {
        if (authenticated)
        {
            return "Signed-in download: the same published artifact plus recovery, support, and any optional device-linking help tied back to your account.";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
        {
            return "The current preview starts with account creation so Chummer can keep the download handoff and recovery path attached from the first launch.";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRecommended, StringComparison.OrdinalIgnoreCase))
        {
            return "You can download this copy as a guest, but signing in keeps recovery, support continuity, and any available device linking attached to your account.";
        }

        return recommended ? RecommendedSupport(download) : AlternativeSupport(download);
    }

    private static string ActionLabel(PublicReleaseArtifactDto download, bool authenticated, string accessClass, bool recommended)
    {
        if (authenticated)
        {
            return "Start signed-in download";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
        {
            return recommended ? "Create account to get preview" : "Create account to download";
        }

        return recommended ? RecommendedActionLabel(download) : AlternativeActionLabel(download);
    }

    private static string RecommendedActionLabel(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Download Chummer for {PlatformLabel(download)}"
            : $"Download Chummer preview for {PlatformLabel(download)}";

    private static string AlternativeActionLabel(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Download {HeadLabel(download)}"
            : $"Download {PlatformLabel(download)} package";

    private static string OptionTitle(PublicReleaseArtifactDto download, bool recommended)
    {
        if (recommended && IsInstaller(download))
        {
            return $"Chummer for {PlatformLabel(download)}";
        }

        if (recommended)
        {
            return $"Chummer preview for {PlatformLabel(download)}";
        }

        if (IsInstaller(download))
        {
            return $"{HeadLabel(download)} for {PlatformLabel(download)}";
        }

        return $"Preview package for {PlatformLabel(download)}";
    }

    private static string HeadLabel(PublicReleaseArtifactDto download)
        => download.Head?.ToLowerInvariant() switch
        {
            "avalonia" => IsInstaller(download) ? "Recommended desktop build" : "Recommended desktop package",
            "blazor-desktop" => IsInstaller(download) ? "Alternative desktop build" : "Alternative desktop package",
            _ => IsInstaller(download) ? "Recommended desktop install" : "Manual package"
        };

    private static string PlatformFamily(PublicReleaseArtifactDto? download)
    {
        if (download is null)
        {
            return "generic";
        }

        if (!string.IsNullOrWhiteSpace(download.PlatformId))
        {
            if (download.PlatformId.Contains("win", StringComparison.OrdinalIgnoreCase))
            {
                return "windows";
            }

            if (download.PlatformId.Contains("linux", StringComparison.OrdinalIgnoreCase))
            {
                return "linux";
            }

            if (download.PlatformId.Contains("osx", StringComparison.OrdinalIgnoreCase) || download.PlatformId.Contains("mac", StringComparison.OrdinalIgnoreCase))
            {
                return "macos";
            }
        }

        if (download.Platform.Contains("Windows", StringComparison.OrdinalIgnoreCase))
        {
            return "windows";
        }

        if (download.Platform.Contains("Linux", StringComparison.OrdinalIgnoreCase))
        {
            return "linux";
        }

        if (download.Platform.Contains("mac", StringComparison.OrdinalIgnoreCase))
        {
            return "macos";
        }

        return "generic";
    }

    private static string? DetectPreferredPlatform(string userAgent)
    {
        if (userAgent.Contains("Windows", StringComparison.OrdinalIgnoreCase))
        {
            return "windows";
        }

        if (userAgent.Contains("Linux", StringComparison.OrdinalIgnoreCase))
        {
            return "linux";
        }

        if (userAgent.Contains("Mac OS", StringComparison.OrdinalIgnoreCase) || userAgent.Contains("Macintosh", StringComparison.OrdinalIgnoreCase))
        {
            return "macos";
        }

        return null;
    }

    private static bool IsPublicShelfVisible(PublicReleaseArtifactDto download, DesktopPlatformAcceptanceDocument platformAcceptance)
    {
        var platform = ResolvePlatformAcceptance(platformAcceptance, PlatformFamily(download));
        if (platform is null)
        {
            return true;
        }

        return !string.Equals(platform.PublicShelfStatus, "buildable_not_publicly_promoted", StringComparison.OrdinalIgnoreCase);
    }

    private static DesktopPlatformAcceptancePlatformDocument? ResolvePlatformAcceptance(DesktopPlatformAcceptanceDocument platformAcceptance, string? platformFamily)
    {
        if (string.IsNullOrWhiteSpace(platformFamily))
        {
            return null;
        }

        return (platformAcceptance.Platforms ?? new List<DesktopPlatformAcceptancePlatformDocument>())
            .FirstOrDefault(item => string.Equals(NormalizePlatformId(item.Id), platformFamily, StringComparison.OrdinalIgnoreCase));
    }

    private static string NormalizePlatformId(string? value)
    {
        var normalized = (value ?? string.Empty).Trim();
        if (normalized.Equals("macOS", StringComparison.OrdinalIgnoreCase))
        {
            return "macos";
        }

        return normalized.ToLowerInvariant();
    }

    private static PlatformShelfNoticeViewModel? BuildPlatformShelfNotice(
        PublicReleaseManifestDto manifest,
        DesktopPlatformAcceptanceDocument platformAcceptance,
        string? requestedPlatform)
    {
        if (string.IsNullOrWhiteSpace(requestedPlatform))
        {
            return null;
        }

        if (manifest.Downloads.Any(download => string.Equals(PlatformFamily(download), requestedPlatform, StringComparison.OrdinalIgnoreCase)))
        {
            return null;
        }

        var label = RequestedPlatformLabel(requestedPlatform) ?? "This platform";
        var platform = ResolvePlatformAcceptance(platformAcceptance, requestedPlatform);
        if (platform is not null && string.Equals(platform.PublicShelfStatus, "buildable_not_publicly_promoted", StringComparison.OrdinalIgnoreCase))
        {
            return new PlatformShelfNoticeViewModel(
                $"{label} is not on the public shelf yet",
                $"The current preview does not publish a promoted {label} download yet. Built artifacts may exist as internal release evidence, but /downloads only exposes platforms that have cleared signing, promotion, and public release-truth checks.");
        }

        return new PlatformShelfNoticeViewModel(
            $"{label} is not on the current shelf",
            $"The current preview does not publish a download for {label}. Use the release-truth and install-help surfaces before assuming this platform is currently supported.");
    }

    private static string? RequestedPlatformLabel(string? requestedPlatform)
        => requestedPlatform switch
        {
            "windows" => "Windows",
            "linux" => "Linux",
            "macos" => "macOS",
            _ => null
        };

    private sealed record PlatformShelfNoticeViewModel(string Title, string Summary);

    private static string PlatformLabel(PublicReleaseArtifactDto download)
        => PlatformFamily(download) switch
        {
            "windows" => "Windows",
            "linux" => "Linux",
            "macos" => "macOS",
            _ => download.Platform
        };

    private static int PlatformPriority(PublicReleaseArtifactDto download)
        => PlatformFamily(download) switch
        {
            "windows" => 0,
            "macos" => 1,
            "linux" => 2,
            _ => 3
        };

    private static int HeadPriority(PublicReleaseArtifactDto download)
        => download.Head?.ToLowerInvariant() switch
        {
            "avalonia" => 0,
            "blazor-desktop" => 1,
            _ => 2
        };

    private static string SizeLabel(long? sizeBytes)
        => sizeBytes is long size
            ? $"{Math.Round(size / 1024d / 1024d, 1)} MB"
            : "Unknown size";
}
