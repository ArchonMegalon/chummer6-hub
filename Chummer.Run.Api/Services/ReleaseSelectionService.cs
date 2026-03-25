using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class ReleaseSelectionService
{
    private readonly PublicCanonFileLoader _canon;
    private const string ExperienceRelativePath = ".codex-design/product/PUBLIC_RELEASE_EXPERIENCE.yaml";
    private const string DefaultGuestReadableChannel = "stable";

    public ReleaseSelectionService(PublicCanonFileLoader canon)
    {
        _canon = canon;
    }

    public PublicReleaseManifestDto ApplyAccessPolicy(PublicReleaseManifestDto manifest)
    {
        var experience = LoadExperience();
        return ApplyAccessPolicy(manifest, experience);
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
        manifest = ApplyAccessPolicy(manifest, experience);

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

        return new ReleaseExperienceViewModel(
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
            GuestGateHeading: experience.GuestGateHeading,
            GuestGateSummary: experience.GuestGateSummary,
            GuestGatePrimaryLabel: experience.GuestGatePrimaryLabel,
            GuestGatePrimaryHref: experience.GuestGatePrimaryHref,
            GuestGateSecondaryLabel: experience.GuestGateSecondaryLabel,
            GuestGateSecondaryHref: experience.GuestGateSecondaryHref,
            SignedInDispatchHeading: experience.SignedInDispatchHeading,
            SignedInDispatchSummary: experience.SignedInDispatchSummary,
            SignedInDispatchSteps: experience.SignedInDispatchSteps ?? new List<string>(),
            InstallSteps: experience.InstallSteps ?? new List<string>(),
            SystemRequirements: RequirementsFor(experience, recommended));
    }

    public ReleaseOptionViewModel BuildOption(PublicReleaseManifestDto manifest, PublicReleaseArtifactDto download, bool authenticated, bool recommended)
    {
        manifest = ApplyAccessPolicy(manifest);
        var normalized = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, download.Id, StringComparison.OrdinalIgnoreCase))
            ?? download with
            {
                InstallAccessClass = ResolveInstallAccessClass(manifest.Channel, download.InstallAccessClass, LoadExperience())
            };
        return BuildNormalizedOption(manifest.Channel, normalized, authenticated, recommended);
    }

    private PublicReleaseExperienceDocument LoadExperience()
        => _canon.LoadRequiredYaml<PublicReleaseExperienceDocument>(ExperienceRelativePath);

    private static PublicReleaseManifestDto ApplyAccessPolicy(PublicReleaseManifestDto manifest, PublicReleaseExperienceDocument experience)
        => manifest with
        {
            Downloads = manifest.Downloads
                .Select(download => download with
                {
                    InstallAccessClass = ResolveInstallAccessClass(manifest.Channel, download.InstallAccessClass, experience)
                })
                .ToArray()
        };

    private static ReleaseOptionViewModel BuildNormalizedOption(string channel, PublicReleaseArtifactDto download, bool authenticated, bool recommended)
    {
        var accessClass = NormalizeInstallAccessClass(download.InstallAccessClass) ?? InstallAccessClasses.AccountRequired;
        var requiresAccount = string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase);
        var guestDownloadAllowed = !requiresAccount;
        var artifactId = Uri.EscapeDataString(download.Id);
        var dispatchHref = authenticated
            ? $"/downloads/install/{artifactId}"
            : requiresAccount
                ? $"/login?next={Uri.EscapeDataString($"/downloads/install/{artifactId}")}"
                : $"/downloads/get/{artifactId}";

        return new ReleaseOptionViewModel(
            Artifact: download with { InstallAccessClass = accessClass },
            Title: OptionTitle(download, recommended),
            DispatchHref: dispatchHref,
            DirectFileHref: $"/downloads/file/{artifactId}",
            PlatformLabel: PlatformLabel(download),
            HeadLabel: HeadLabel(download),
            SizeLabel: SizeLabel(download.SizeBytes),
            SupportLine: SupportLine(download, channel, authenticated, accessClass, recommended),
            ActionLabel: ActionLabel(download, authenticated, accessClass, recommended),
            ShaPreview: string.IsNullOrWhiteSpace(download.Sha256) ? null : $"SHA {download.Sha256[..Math.Min(download.Sha256.Length, 16)]}...",
            Installer: IsInstaller(download),
            InstallAccessClass: accessClass,
            RequiresAccount: requiresAccount,
            GuestDownloadAllowed: guestDownloadAllowed);
    }

    private static IReadOnlyList<string> RequirementsFor(PublicReleaseExperienceDocument experience, PublicReleaseArtifactDto? recommended)
        => PlatformFamily(recommended) switch
        {
            "windows" => experience.WindowsRequirements ?? new List<string>(),
            "linux" => experience.LinuxRequirements ?? new List<string>(),
            "macos" => experience.MacosRequirements ?? new List<string>(),
            _ => experience.WindowsRequirements ?? new List<string>()
        };

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

        string? preferredPlatform = null;
        if (userAgent.Contains("Windows", StringComparison.OrdinalIgnoreCase))
        {
            preferredPlatform = "windows";
        }
        else if (userAgent.Contains("Linux", StringComparison.OrdinalIgnoreCase))
        {
            preferredPlatform = "linux";
        }
        else if (userAgent.Contains("Mac OS", StringComparison.OrdinalIgnoreCase) || userAgent.Contains("Macintosh", StringComparison.OrdinalIgnoreCase))
        {
            preferredPlatform = "macos";
        }

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
        => download.Url.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
           || download.Url.EndsWith(".deb", StringComparison.OrdinalIgnoreCase)
           || download.Url.EndsWith(".msi", StringComparison.OrdinalIgnoreCase)
           || download.Url.EndsWith(".dmg", StringComparison.OrdinalIgnoreCase)
           || download.Url.EndsWith(".pkg", StringComparison.OrdinalIgnoreCase)
           || download.Id.Contains("installer", StringComparison.OrdinalIgnoreCase);

    private static string RecommendedSupport(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"This is the default recommended installer for {PlatformLabel(download)}."
            : $"A packaged installer is not published for {PlatformLabel(download)} yet. This is the cleanest current preview package for that platform.";

    private static string AlternativeSupport(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Alternative desktop head for {PlatformLabel(download)}. Use this only when you explicitly want this runtime path."
            : $"Manual package for {PlatformLabel(download)}. Use this only for advanced or support-directed install work.";

    private static string SupportLine(PublicReleaseArtifactDto download, string channel, bool authenticated, string accessClass, bool recommended)
    {
        if (authenticated)
        {
            return "Signed-in download: the canonical artifact plus a claim code you can use to link this copy on first launch.";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
        {
            return $"The current {channel} channel starts with a signed-in download so Chummer can attach the install handoff to your account from the first launch.";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRecommended, StringComparison.OrdinalIgnoreCase))
        {
            return "You can download this copy as a guest, but signing in keeps the install handoff and support continuity attached to your account.";
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
            return recommended ? "Sign in to download preview" : "Sign in to download";
        }

        return recommended ? RecommendedActionLabel(download) : AlternativeActionLabel(download);
    }

    private static string RecommendedActionLabel(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Download Chummer for {PlatformLabel(download)}"
            : $"Download preview package for {PlatformLabel(download)}";

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

        if (IsInstaller(download))
        {
            return $"{HeadLabel(download)} for {PlatformLabel(download)}";
        }

        return $"Preview package for {PlatformLabel(download)}";
    }

    private static string HeadLabel(PublicReleaseArtifactDto download)
        => download.Head?.ToLowerInvariant() switch
        {
            "avalonia" => "Avalonia desktop head",
            "blazor-desktop" => "Blazor desktop head",
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
