using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class ReleaseSelectionService
{
    private readonly PublicCanonFileLoader _canon;
    private const string ExperienceRelativePath = ".codex-design/product/PUBLIC_RELEASE_EXPERIENCE.yaml";

    public ReleaseSelectionService(PublicCanonFileLoader canon)
    {
        _canon = canon;
    }

    public ReleaseExperienceViewModel BuildExperience(PublicReleaseManifestDto manifest, string userAgent, bool authenticated)
    {
        var experience = _canon.LoadRequiredYaml<PublicReleaseExperienceDocument>(ExperienceRelativePath);
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
            Recommended: recommended is null ? null : BuildOption(recommended, authenticated, true),
            Alternatives: alternatives.Select(download => BuildOption(download, authenticated, false)).ToArray(),
            OtherPlatforms: otherPlatforms.Select(download => BuildOption(download, authenticated, false)).ToArray(),
            ManualPackages: manualDownloads.Select(download => BuildOption(download, authenticated, false)).ToArray(),
            ReleaseNotesSummary: experience.ReleaseNotesSummary,
            KnownIssuesLabel: experience.KnownIssuesLabel,
            KnownIssuesHref: experience.KnownIssuesHref,
            InstallHelpLabel: experience.InstallHelpLabel,
            InstallHelpHref: experience.InstallHelpHref,
            UpdatePostureSummary: experience.UpdatePostureSummary,
            InstallSteps: experience.InstallSteps ?? new List<string>(),
            SystemRequirements: RequirementsFor(experience, recommended));
    }

    private static ReleaseOptionViewModel BuildOption(PublicReleaseArtifactDto download, bool authenticated, bool recommended)
        => new(
            Artifact: download,
            DispatchHref: $"/downloads/get/{Uri.EscapeDataString(download.Id)}",
            PlatformLabel: PlatformLabel(download),
            HeadLabel: HeadLabel(download),
            SizeLabel: SizeLabel(download.SizeBytes),
            SupportLine: recommended ? RecommendedSupport(download) : AlternativeSupport(download),
            ActionLabel: recommended ? RecommendedActionLabel(download, authenticated) : AlternativeActionLabel(download, authenticated),
            ShaPreview: string.IsNullOrWhiteSpace(download.Sha256) ? null : $"SHA {download.Sha256[..Math.Min(download.Sha256.Length, 16)]}...",
            Installer: IsInstaller(download));

    private static IReadOnlyList<string> RequirementsFor(PublicReleaseExperienceDocument experience, PublicReleaseArtifactDto? recommended)
        => PlatformFamily(recommended) switch
        {
            "windows" => experience.WindowsRequirements ?? new List<string>(),
            "linux" => experience.LinuxRequirements ?? new List<string>(),
            "macos" => experience.MacosRequirements ?? new List<string>(),
            _ => experience.WindowsRequirements ?? new List<string>()
        };

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

    private static string RecommendedActionLabel(PublicReleaseArtifactDto download, bool authenticated)
        => authenticated
            ? "Download and link this copy"
            : IsInstaller(download)
                ? $"Download Chummer for {PlatformLabel(download)}"
                : $"Download preview package for {PlatformLabel(download)}";

    private static string AlternativeActionLabel(PublicReleaseArtifactDto download, bool authenticated)
        => authenticated
            ? "Download and link this copy"
            : IsInstaller(download)
                ? $"Download {HeadLabel(download)}"
                : $"Download {PlatformLabel(download)} package";

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
