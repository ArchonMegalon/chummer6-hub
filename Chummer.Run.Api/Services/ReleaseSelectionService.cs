using Chummer.Run.Api.ViewModels;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class ReleaseSelectionService
{
    private readonly PublicCanonFileLoader _canon;
    private readonly Lazy<PublicReleaseExperienceDocument> _experience;
    private readonly Lazy<DesktopPlatformAcceptanceDocument> _platformAcceptance;
    private const string ExperienceRelativePath = ".codex-design/product/PUBLIC_RELEASE_EXPERIENCE.yaml";
    private const string PlatformAcceptanceRelativePath = ".codex-design/product/DESKTOP_PLATFORM_ACCEPTANCE_MATRIX.yaml";
    private const string DefaultGuestReadableChannel = "stable";

    public ReleaseSelectionService(PublicCanonFileLoader canon)
    {
        _canon = canon;
        _experience = new Lazy<PublicReleaseExperienceDocument>(LoadExperienceDocument, LazyThreadSafetyMode.ExecutionAndPublication);
        _platformAcceptance = new Lazy<DesktopPlatformAcceptanceDocument>(LoadPlatformAcceptanceDocument, LazyThreadSafetyMode.ExecutionAndPublication);
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

    public bool UsesMacBootstrapScript(PublicReleaseArtifactDto artifact)
        => UsesMacBootstrapFlow(artifact);

    public bool UsesGuidedBootstrapScript(PublicReleaseArtifactDto artifact)
        => UsesGuidedBootstrapFlow(artifact);

    public ReleaseExperienceViewModel BuildExperience(PublicReleaseManifestDto manifest, string userAgent, bool authenticated)
    {
        var experience = LoadExperience();
        var platformAcceptance = LoadPlatformAcceptance();
        manifest = ApplyAccessPolicy(manifest, experience, platformAcceptance);
        var requestedPlatform = DetectPreferredPlatform(userAgent);
        var requestedPlatformHasPublicDownload = string.IsNullOrWhiteSpace(requestedPlatform)
            || manifest.Downloads.Any(download => string.Equals(PlatformFamily(download), requestedPlatform, StringComparison.OrdinalIgnoreCase));
        var shelfNotice = BuildPlatformShelfNotice(manifest, platformAcceptance, requestedPlatform);
        var platformAvailability = BuildPlatformAvailability(manifest, platformAcceptance, requestedPlatform);

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
        var guestDownloadAvailable = manifest.Downloads.Any(static artifact =>
            !string.Equals(artifact.InstallAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase));
        // macOS preview posture stays on one Terminal command instead of a raw DMG download.
        // The guided setup path verifies the published DMG digest before install continuity is claimed.
        var guestGateArtifactHref = recommended is null || guestDownloadAvailable
            ? "/downloads"
            : BuildSignupDispatchHref(recommended);
        var guestGateSignInHref = recommended is null
            ? "/login?next=%2Fdownloads"
            : BuildLoginDispatchHref(recommended);
        var guestGateSecondaryLabel = experience.GuestGateSecondaryLabel;

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
            GuestDownloadAvailable: guestDownloadAvailable,
            RequestedPlatformHasPublicDownload: requestedPlatformHasPublicDownload,
            PlatformShelfNoticeTitle: shelfNotice?.Title,
            PlatformShelfNoticeSummary: shelfNotice?.Summary,
            RequestedPlatformLabel: RequestedPlatformLabel(requestedPlatform),
            PlatformAvailability: platformAvailability,
            GuestGateHeading: experience.GuestGateHeading,
            GuestGateSummary: experience.GuestGateSummary,
            GuestGatePrimaryLabel: experience.GuestGatePrimaryLabel,
            GuestGatePrimaryHref: guestGateArtifactHref,
            GuestGateSecondaryLabel: guestGateSecondaryLabel,
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

    public IReadOnlyList<ReleaseOptionViewModel> BuildSignedInOnlyWindowsOptions(PublicReleaseManifestDto manifest)
    {
        var experience = LoadExperience();
        var platformAcceptance = LoadPlatformAcceptance();
        var publicManifest = ApplyAccessPolicy(manifest, experience, platformAcceptance);
        var publicIds = publicManifest.Downloads
            .Where(static download => !string.IsNullOrWhiteSpace(download.Id))
            .Select(static download => download.Id.Trim())
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        return manifest.Downloads
            .Where(static download => !string.IsNullOrWhiteSpace(download.Id))
            .Where(download => !publicIds.Contains(download.Id.Trim()))
            .Where(download => string.Equals(PlatformFamily(download), "windows", StringComparison.OrdinalIgnoreCase))
            .Where(IsInstaller)
            .Select(download => download with
            {
                InstallAccessClass = NormalizeInstallAccessClass(download.InstallAccessClass) ?? InstallAccessClasses.AccountRequired
            })
            .OrderBy(HeadPriority)
            .ThenBy(static download => string.Equals((download.Arch ?? string.Empty).Trim(), "x64", StringComparison.OrdinalIgnoreCase) ? 0 : 1)
            .ThenBy(static download => download.Platform, StringComparer.OrdinalIgnoreCase)
            .Select(static download => BuildNormalizedOption(download, authenticated: true, recommended: false))
            .ToArray();
    }

    public PublicLandingActionDto BuildPublicPrimaryAction(PublicReleaseManifestDto manifest, string userAgent, bool authenticated)
    {
        var release = BuildExperience(manifest, userAgent, authenticated);
        if (manifest.Downloads.Count == 0)
        {
            return new PublicLandingActionDto(release.NoBuildPrimaryLabel, release.NoBuildPrimaryHref, "primary");
        }

        if (release.Recommended is not null
            && (authenticated || !release.Recommended.RequiresAccount))
        {
            return new PublicLandingActionDto(release.Recommended.ActionLabel, release.Recommended.DispatchHref, "primary");
        }

        return new PublicLandingActionDto(release.GuestGatePrimaryLabel, release.GuestGatePrimaryHref, "primary");
    }

    public PublicAccessPostureViewModel BuildPublicAccessPosture(PublicReleaseManifestDto manifest, string userAgent, bool authenticated)
    {
        var releaseExperience = BuildExperience(manifest, userAgent, authenticated);
        return BuildPublicAccessPosture(manifest, releaseExperience);
    }

    public PublicAccessPostureViewModel BuildPublicAccessPosture(PublicReleaseManifestDto manifest, ReleaseExperienceViewModel releaseExperience)
    {
        manifest = ApplyAccessPolicy(manifest);
        var publicPlatforms = DistinctPlatformFamilies(manifest.Downloads);
        var guestPlatforms = DistinctPlatformFamilies(manifest.Downloads.Where(download => !RequiresAccount(download)));
        var accountPlatforms = DistinctPlatformFamilies(manifest.Downloads.Where(download => RequiresAccount(download)));
        var guestInstallAvailable = releaseExperience.GuestDownloadAvailable || guestPlatforms.Count > 0;
        var accountRequiredInstallAvailable = accountPlatforms.Count > 0;

        string availabilitySummary;
        string accountValueSummary;
        string createAccountSummary;
        string signInSummary;
        string downloadFaqAnswer;
        string accountFaqAnswer;

        if (guestInstallAvailable && accountRequiredInstallAvailable)
        {
            availabilitySummary = $"{PublicDownloadSentence(publicPlatforms)} {GatedInstallSentence(accountPlatforms)}";
            accountValueSummary = "The account does not change the published file. It keeps recovery, tracked support, and linked install history on the same return path, and it unlocks the routes that still attach account return after the first launch link.";
            createAccountSummary = "Some platforms are published directly now. Create an account only when you want guided recovery, tracked support, or linked install history on the same return path.";
            signInSummary = "Sign in to reopen linked installs, recovery history, and support history.";
            downloadFaqAnswer = $"It depends on the platform. {PublicDownloadSentence(publicPlatforms)} {GatedInstallSentence(accountPlatforms)}";
            accountFaqAnswer = "Account creation does not change the published file. It gives you recovery, tracked support, linked install history, and access to routes that keep account return attached after linking.";
        }
        else if (guestInstallAvailable)
        {
            availabilitySummary = $"{PublicDownloadSentence(guestPlatforms)} Create an account when you want recovery, tracked support, or linked install history on the same return path.";
            accountValueSummary = "The account does not change the published file. It adds recovery, tracked support, and linked install history when you want a calmer return path.";
            createAccountSummary = "Create an account when you want recovery, tracked support, and linked install history on the same return path. The download file stays the same for everyone.";
            signInSummary = "Sign in to reopen your recovery history, support history, and linked installs.";
            downloadFaqAnswer = availabilitySummary;
            accountFaqAnswer = "Account creation gives you recovery, tracked support, and linked install history. It does not change the published file.";
        }
        else if (accountRequiredInstallAvailable)
        {
            availabilitySummary = $"{GatedInstallSentence(accountPlatforms)} Sign in when you want recovery, support, and install return attached to the same account.";
            accountValueSummary = "The account does not change the published file. It is part of the current install route, and it keeps recovery, tracked support, and linked install history on the same return path.";
            createAccountSummary = "Create an account only when you want the guided handoff, recovery, support history, and linked install return attached.";
            signInSummary = "Sign in to continue the current install route and reopen the same recovery and support path.";
            downloadFaqAnswer = $"Yes for the current route. {GatedInstallSentence(accountPlatforms)} Signing in keeps recovery, support, and install return attached.";
            accountFaqAnswer = "Account creation starts the current install route, and it keeps recovery, tracked support, and linked install history on the same return path.";
        }
        else
        {
            availabilitySummary = "No public download is available right now. Create an account if you want release updates and support when the next build lands.";
            accountValueSummary = "The account keeps recovery, tracked support, and release updates together when the next build lands.";
            createAccountSummary = "Create an account if you want release updates, tracked support, and a calmer return path when the next build lands.";
            signInSummary = "Sign in to reopen your linked release history and support history.";
            downloadFaqAnswer = "Not right now. No public download is available yet.";
            accountFaqAnswer = "Account creation gives you recovery, tracked support, and release updates when the next build lands.";
        }

        return new PublicAccessPostureViewModel(
            GuestInstallAvailable: guestInstallAvailable,
            AccountRequiredInstallAvailable: accountRequiredInstallAvailable,
            AvailabilitySummary: availabilitySummary,
            AccountValueSummary: accountValueSummary,
            CreateAccountSummary: createAccountSummary,
            SignInSummary: signInSummary,
            DownloadFaqAnswer: downloadFaqAnswer,
            AccountFaqAnswer: accountFaqAnswer);
    }

    public ReleaseOptionViewModel BuildOption(PublicReleaseManifestDto manifest, PublicReleaseArtifactDto download, bool authenticated, bool recommended)
    {
        manifest = ApplyAccessPolicy(manifest);
        var normalized = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, download.Id, StringComparison.OrdinalIgnoreCase))
            ?? download with
            {
                InstallAccessClass = ResolveEffectiveInstallAccessClass(manifest.Channel, manifest.RolloutState, download, LoadExperience())
            };
        return BuildNormalizedOption(normalized, authenticated, recommended);
    }

    private PublicReleaseExperienceDocument LoadExperience() => _experience.Value;

    private DesktopPlatformAcceptanceDocument LoadPlatformAcceptance() => _platformAcceptance.Value;

    private PublicReleaseExperienceDocument LoadExperienceDocument()
        => _canon.LoadRequiredYaml<PublicReleaseExperienceDocument>(ExperienceRelativePath);

    private DesktopPlatformAcceptanceDocument LoadPlatformAcceptanceDocument()
        => _canon.LoadRequiredYaml<DesktopPlatformAcceptanceDocument>(PlatformAcceptanceRelativePath);

    private static PublicReleaseManifestDto ApplyAccessPolicy(
        PublicReleaseManifestDto manifest,
        PublicReleaseExperienceDocument experience,
        DesktopPlatformAcceptanceDocument platformAcceptance)
        => manifest with
        {
            Downloads = manifest.Downloads
                .Where(download => IsPublicShelfVisible(download, manifest, experience, platformAcceptance))
                .Select(download => download with
                {
                    InstallAccessClass = ResolveEffectiveInstallAccessClass(manifest.Channel, manifest.RolloutState, download, experience)
                })
                .ToArray()
        };

    private static ReleaseOptionViewModel BuildNormalizedOption(PublicReleaseArtifactDto download, bool authenticated, bool recommended)
    {
        var accessClass = NormalizeInstallAccessClass(download.InstallAccessClass) ?? InstallAccessClasses.AccountRequired;
        var requiresAccount = string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase);
        var guestDownloadAllowed = !requiresAccount;
        var artifactId = Uri.EscapeDataString(download.Id);
        var usesMacBootstrap = UsesMacBootstrapFlow(download);
        var usesDirectInstallerDownload = UsesDirectPublicInstallerDownload(download, accessClass);
        var directFileHref = $"/downloads/file/{artifactId}";
        var dispatchHref = usesDirectInstallerDownload
            ? $"/downloads/get/{artifactId}"
            : authenticated
            ? $"/downloads/install/{artifactId}"
            : usesMacBootstrap
                ? requiresAccount
                    ? BuildSignupDispatchHref(download)
                    : $"/downloads/install/{artifactId}"
                : requiresAccount
                    ? BuildSignupDispatchHref(download)
                    : $"/downloads/get/{artifactId}";

        return new ReleaseOptionViewModel(
            Artifact: download with { InstallAccessClass = accessClass },
            Title: OptionTitle(download, recommended),
            DispatchHref: dispatchHref,
            DirectFileHref: directFileHref,
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
        var buildLabel = ResolveBuildLabel(manifest.Version, manifest.Channel, manifest.RolloutState, experience);
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

    private static string ResolveBuildLabel(string? version, string? channel, string? rolloutState, PublicReleaseExperienceDocument experience)
    {
        if (string.Equals((channel ?? string.Empty).Trim(), "docker", StringComparison.OrdinalIgnoreCase)
            && string.Equals((rolloutState ?? string.Empty).Trim(), "public_stable", StringComparison.OrdinalIgnoreCase))
        {
            return experience.UnpublishedBuildLabel;
        }

        var normalized = (version ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(normalized) || string.Equals(normalized, "unpublished", StringComparison.OrdinalIgnoreCase))
        {
            return experience.UnpublishedBuildLabel;
        }

        return $"{experience.BuildLabelPrefix} {normalized}";
    }

    private static string BuildSignupDispatchHref(PublicReleaseArtifactDto artifact)
        => $"/signup?next={Uri.EscapeDataString(BuildSignedInDispatchTarget(artifact))}";

    private static string BuildLoginDispatchHref(PublicReleaseArtifactDto artifact)
        => $"/login?next={Uri.EscapeDataString(BuildSignedInDispatchTarget(artifact))}";

    private static string BuildGoogleDispatchHref(PublicReleaseArtifactDto artifact)
        => BuildLoginDispatchHref(artifact);

    private static string BuildSignedInDispatchTarget(PublicReleaseArtifactDto artifact)
        => $"/downloads/install/{Uri.EscapeDataString(artifact.Id)}";

    private static string ResolveInstallAccessClass(
        string channel,
        string? rolloutState,
        string? rawAccessClass,
        PublicReleaseExperienceDocument experience)
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

    private static string ResolveEffectiveInstallAccessClass(
        string channel,
        string? rolloutState,
        PublicReleaseArtifactDto download,
        PublicReleaseExperienceDocument experience)
    {
        if (IsInstaller(download)
            && PlatformFamily(download) is "windows" or "linux")
        {
            return InstallAccessClasses.OpenPublic;
        }

        return ResolveInstallAccessClass(channel, rolloutState, download.InstallAccessClass, experience);
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
        string? preferredArch = DetectPreferredArchitecture(userAgent);

        var pool = preferredPlatform is null
            ? candidates
            : candidates.Where(download => string.Equals(PlatformFamily(download), preferredPlatform, StringComparison.OrdinalIgnoreCase)).ToArray();

        if (pool.Length == 0)
        {
            pool = candidates;
        }

        return pool
            .OrderByDescending(IsInstaller)
            .ThenBy(download => ArchitecturePriority(download, preferredArch))
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

    private static bool UsesMacBootstrapFlow(PublicReleaseArtifactDto download)
        => string.Equals(PlatformFamily(download), "macos", StringComparison.OrdinalIgnoreCase)
           && ((download.Kind ?? string.Empty).Trim().Equals("dmg", StringComparison.OrdinalIgnoreCase)
               || download.Url.EndsWith(".dmg", StringComparison.OrdinalIgnoreCase)
               || (download.FileName ?? string.Empty).EndsWith(".dmg", StringComparison.OrdinalIgnoreCase));

    private static bool UsesWindowsBootstrapFlow(PublicReleaseArtifactDto download)
        => string.Equals(PlatformFamily(download), "windows", StringComparison.OrdinalIgnoreCase)
           && ((download.Kind ?? string.Empty).Trim().Equals("installer", StringComparison.OrdinalIgnoreCase)
               || download.Url.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
               || (download.FileName ?? string.Empty).EndsWith(".exe", StringComparison.OrdinalIgnoreCase));

    private static bool UsesLinuxBootstrapFlow(PublicReleaseArtifactDto download)
        => string.Equals(PlatformFamily(download), "linux", StringComparison.OrdinalIgnoreCase)
           && ((download.Kind ?? string.Empty).Trim().Equals("installer", StringComparison.OrdinalIgnoreCase)
               || download.Url.EndsWith(".deb", StringComparison.OrdinalIgnoreCase)
               || (download.FileName ?? string.Empty).EndsWith(".deb", StringComparison.OrdinalIgnoreCase));

    private static bool UsesGuidedBootstrapFlow(PublicReleaseArtifactDto download)
        => UsesMacBootstrapFlow(download)
           || UsesLinuxBootstrapFlow(download);

    private static bool UsesDirectPublicInstallerDownload(PublicReleaseArtifactDto download, string accessClass)
        => IsInstaller(download)
           && !string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase)
           && PlatformFamily(download) is "windows" or "linux";

    private static string RecommendedSupport(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"This is the default recommended installer for {PlatformLabel(download)}."
            : $"This is the clearest current public-release package for {PlatformLabel(download)}.";

    private static string AlternativeSupport(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Alternative desktop build for {PlatformLabel(download)}. Use this only when support sends you to a different build on the same platform."
            : AlternativePackageSupport(download);

    private static string SupportLine(PublicReleaseArtifactDto download, bool authenticated, string accessClass, bool recommended)
    {
        if (UsesDirectPublicInstallerDownload(download, accessClass))
        {
            return recommended ? RecommendedSupport(download) : AlternativeSupport(download);
        }

        if (authenticated && UsesWindowsBootstrapFlow(download))
        {
            return "Open the Windows setup path, download the published setup .exe, and finish account linking in your default browser after setup starts the browser callback.";
        }

        if (authenticated && UsesLinuxBootstrapFlow(download))
        {
            return "Open the Linux setup path. It gives you a short-lived shell command that offers Auto select for the matching Linux desktop builds, lets you choose which Chummer apps to install, where to place them, whether quick access should stay in the applications menu or add Desktop links, verifies the published package digest, and confirms the selected apps linked back successfully.";
        }

        if (UsesMacBootstrapFlow(download))
        {
            return authenticated
                ? "Open the guided Mac support path when support has sent you a Mac installer."
                : string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase)
                    ? "Open guided Mac support. You can create an account there if support needs install history attached later."
                    : "Open guided Mac support when support has sent you a Mac installer.";
        }

        if (authenticated)
        {
            return "Start the published download.";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
        {
            return "Open the account-assisted install path when you want sign-in, support, and install return attached without changing the published file.";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRecommended, StringComparison.OrdinalIgnoreCase))
        {
            return "You can download this copy as a guest, but signing in keeps recovery, support history, and any available device linking attached to your account.";
        }

        return recommended ? RecommendedSupport(download) : AlternativeSupport(download);
    }

    private static string ActionLabel(PublicReleaseArtifactDto download, bool authenticated, string accessClass, bool recommended)
    {
        if (UsesDirectPublicInstallerDownload(download, accessClass))
        {
            return recommended ? RecommendedActionLabel(download) : AlternativeActionLabel(download);
        }

        if (authenticated && UsesWindowsBootstrapFlow(download))
        {
            return "Install on Windows";
        }

        if (authenticated && UsesLinuxBootstrapFlow(download))
        {
            return "Install on Linux";
        }

        if (UsesMacBootstrapFlow(download))
        {
            if (authenticated)
            {
                return "Open Mac support";
            }

            return string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase)
                ? "Open Mac support"
                : "Open Mac support";
        }

        if (authenticated)
        {
            return IsInstaller(download) ? "Install now" : "Download package";
        }

        if (string.Equals(accessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
        {
            return recommended ? "Open install path" : "Open download path";
        }

        return recommended ? RecommendedActionLabel(download) : AlternativeActionLabel(download);
    }

    private static string RecommendedActionLabel(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Install Chummer on {PlatformLabel(download)}"
            : $"Download Chummer package for {PlatformLabel(download)}";

    private static string AlternativeActionLabel(PublicReleaseArtifactDto download)
        => IsInstaller(download)
            ? $"Install {HeadLabel(download)}"
            : AlternativePackageActionLabel(download);

    private static string OptionTitle(PublicReleaseArtifactDto download, bool recommended)
    {
        if (recommended && IsInstaller(download))
        {
            return $"Chummer for {PlatformLabel(download)}";
        }

        if (recommended)
        {
            return $"Chummer for {PlatformLabel(download)}";
        }

        if (IsInstaller(download))
        {
            return $"{HeadLabel(download)} for {PlatformLabel(download)}";
        }

        return AlternativePackageTitle(download);
    }

    private static string AlternativePackageTitle(PublicReleaseArtifactDto download)
        => NormalizePackageKind(download.Kind) switch
        {
            "portable_exe" => $"Support package for {PlatformLabel(download)}",
            "archive" => $"Support package for {PlatformLabel(download)}",
            _ => $"Support package for {PlatformLabel(download)}"
        };

    private static string AlternativePackageSupport(PublicReleaseArtifactDto download)
        => NormalizePackageKind(download.Kind) switch
        {
            "portable_exe" => $"Support-only package for {PlatformLabel(download)}. Use the main installer unless support gives you this link.",
            "archive" => $"Support-only package for {PlatformLabel(download)}. Use the main installer unless support gives you this link.",
            _ => $"Support-only package for {PlatformLabel(download)}. Use this only when support gives you this link."
        };

    private static string AlternativePackageActionLabel(PublicReleaseArtifactDto download)
        => NormalizePackageKind(download.Kind) switch
        {
            "portable_exe" => $"Download {PlatformLabel(download)} support package",
            "archive" => $"Download {PlatformLabel(download)} support package",
            _ => $"Download {PlatformLabel(download)} package"
        };

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

    private static string? DetectPreferredArchitecture(string userAgent)
    {
        if (userAgent.Contains("arm64", StringComparison.OrdinalIgnoreCase)
            || userAgent.Contains("aarch64", StringComparison.OrdinalIgnoreCase)
            || userAgent.Contains("Apple Silicon", StringComparison.OrdinalIgnoreCase))
        {
            return "arm64";
        }

        if (userAgent.Contains("x86_64", StringComparison.OrdinalIgnoreCase)
            || userAgent.Contains("Win64", StringComparison.OrdinalIgnoreCase)
            || userAgent.Contains("x64", StringComparison.OrdinalIgnoreCase)
            || userAgent.Contains("amd64", StringComparison.OrdinalIgnoreCase)
            || userAgent.Contains("Intel", StringComparison.OrdinalIgnoreCase))
        {
            return "x64";
        }

        return null;
    }

    private static int ArchitecturePriority(PublicReleaseArtifactDto download, string? preferredArch)
    {
        if (string.IsNullOrWhiteSpace(preferredArch))
        {
            return 0;
        }

        var arch = (download.Arch ?? string.Empty).Trim();
        if (arch.Length == 0)
        {
            return 1;
        }

        return string.Equals(arch, preferredArch, StringComparison.OrdinalIgnoreCase) ? 0 : 1;
    }

    private static bool IsPublicShelfVisible(
        PublicReleaseArtifactDto download,
        PublicReleaseManifestDto manifest,
        PublicReleaseExperienceDocument experience,
        DesktopPlatformAcceptanceDocument platformAcceptance)
    {
        if (!IsInstaller(download))
        {
            return false;
        }

        if (UsesMacBootstrapFlow(download) && !HasExplicitArtifactProof(manifest, download))
        {
            return false;
        }

        var platform = ResolvePlatformAcceptance(platformAcceptance, PlatformFamily(download));
        if (platform is null)
        {
            return true;
        }

        if (string.Equals(platform.PublicShelfStatus, "buildable_not_publicly_promoted", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (UsesMacBootstrapFlow(download)
            && string.Equals((manifest.RolloutState ?? string.Empty).Trim(), "public_stable", StringComparison.OrdinalIgnoreCase)
            && string.Equals(manifest.ProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
            && HasExplicitArtifactProof(manifest, download))
        {
            return true;
        }

        if (string.Equals(platform.PublicManifestVisibility, "visible_as_account_gated_setup_script_release", StringComparison.OrdinalIgnoreCase)
            || string.Equals(platform.PublicManifestVisibility, "visible_as_account_gated_setup_script_preview", StringComparison.OrdinalIgnoreCase))
        {
            return string.Equals(manifest.Status, "published", StringComparison.OrdinalIgnoreCase)
                   && UsesMacBootstrapFlow(download)
                   && (string.Equals((manifest.RolloutState ?? string.Empty).Trim(), "public_stable", StringComparison.OrdinalIgnoreCase)
                       || string.Equals(
                           ResolveEffectiveInstallAccessClass(manifest.Channel, manifest.RolloutState, download, experience),
                           InstallAccessClasses.AccountRequired,
                           StringComparison.OrdinalIgnoreCase))
                   && HasExplicitArtifactProof(manifest, download);
        }

        if (string.Equals(platform.PublicManifestVisibility, "visible_after_signed_notarized_promotion", StringComparison.OrdinalIgnoreCase))
        {
            return string.Equals(manifest.ProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
                && HasExplicitArtifactProof(manifest, download);
        }

        if (string.Equals(platform.PublicManifestVisibility, "visible_as_public_archive_preview", StringComparison.OrdinalIgnoreCase))
        {
            return string.Equals(manifest.ProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
                   && HasExplicitArtifactProof(manifest, download);
        }

        return true;
    }

    private static bool HasExplicitArtifactProof(PublicReleaseManifestDto manifest, PublicReleaseArtifactDto download)
    {
        if (manifest.ProofRoutes is null || manifest.ProofRoutes.Count == 0)
        {
            return false;
        }

        var artifactId = download.Id.Trim();
        var fileName = (download.FileName ?? string.Empty).Trim();

        return manifest.ProofRoutes.Any(route =>
        {
            if (string.IsNullOrWhiteSpace(route))
            {
                return false;
            }

            return route.Contains($"/downloads/install/{artifactId}", StringComparison.OrdinalIgnoreCase)
                   || route.Contains($"/downloads/file/{artifactId}", StringComparison.OrdinalIgnoreCase)
                   || route.Contains(artifactId, StringComparison.OrdinalIgnoreCase)
                   || (!string.IsNullOrWhiteSpace(fileName) && route.Contains(fileName, StringComparison.OrdinalIgnoreCase));
        });
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
                $"{label} is not on the downloads page yet",
                $"The current release does not include a public {label} installer yet. Use the current public build when it fits your system, or contact support if you need help with this platform.");
        }

        return new PlatformShelfNoticeViewModel(
            $"{label} is not on the current downloads page",
            $"The current release does not include a public {label} installer. Use the platforms listed on this page.");
    }

    private static string? RequestedPlatformLabel(string? requestedPlatform)
        => requestedPlatform switch
        {
            "windows" => "Windows",
            "linux" => "Linux",
            "macos" => "macOS",
            _ => null
        };

    private static IReadOnlyList<string> DistinctPlatformFamilies(IEnumerable<PublicReleaseArtifactDto> downloads)
        => downloads.Select(PlatformFamily)
            .Where(static family => !string.IsNullOrWhiteSpace(family))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(static family => family switch
            {
                "windows" => 0,
                "macos" => 1,
                "linux" => 2,
                _ => 9
            })
            .ThenBy(static family => family, StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static string PublicDownloadSentence(IReadOnlyList<string> platforms)
    {
        if (platforms.Count == 0)
        {
            return "No public download is available right now.";
        }

        var labels = FormatPlatformList(platforms);
        return platforms.Count == 1
            ? $"A public download is available now on {labels}."
            : $"Public downloads are available now on {labels}.";
    }

    private static string GatedInstallSentence(IReadOnlyList<string> platforms)
    {
        if (platforms.Count == 0)
        {
            return "An optional account-return install path is available when you want sign-in and support attached from the first launch.";
        }

        var labels = FormatPlatformList(platforms);
        return platforms.Count == 1
            ? $"{labels} also has an optional account-return install path when you want sign-in and support attached from the first launch."
            : $"{labels} also have optional account-return install paths when you want sign-in and support attached from the first launch.";
    }

    private static string FormatPlatformList(IReadOnlyList<string> platforms)
    {
        var labels = platforms
            .Select(static family => RequestedPlatformLabel(family) ?? "the current public-release route")
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return labels.Length switch
        {
            0 => "the current public-release route",
            1 => labels[0],
            2 => $"{labels[0]} and {labels[1]}",
            _ => $"{string.Join(", ", labels.Take(labels.Length - 1))}, and {labels[^1]}"
        };
    }

    private sealed record PlatformShelfNoticeViewModel(string Title, string Summary);

    private static IReadOnlyList<ReleasePlatformAvailabilityViewModel> BuildPlatformAvailability(
        PublicReleaseManifestDto manifest,
        DesktopPlatformAcceptanceDocument platformAcceptance,
        string? requestedPlatform)
    {
        var platformIds = (platformAcceptance.Platforms ?? new List<DesktopPlatformAcceptancePlatformDocument>())
            .Select(static item => NormalizePlatformId(item.Id))
            .Concat(manifest.Downloads.Select(PlatformFamily))
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(static item => PlatformSortKey(item))
            .ThenBy(static item => item, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return platformIds.Select(platformId =>
        {
            var platform = ResolvePlatformAcceptance(platformAcceptance, platformId);
            var currentDevice = string.Equals(platformId, requestedPlatform, StringComparison.OrdinalIgnoreCase);
            var publishedDownloads = manifest.Downloads
                .Where(download => string.Equals(PlatformFamily(download), platformId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(IsInstaller)
                .ThenBy(HeadPriority)
                .ToArray();
            var promotedDownload = publishedDownloads.FirstOrDefault();
            var publiclyAvailable = promotedDownload is not null;
            var label = RequestedPlatformLabel(platformId) ?? platformId;
            var normalizedPlatformId = NormalizePlatformId(platformId);

            return new ReleasePlatformAvailabilityViewModel(
                PlatformId: platformId,
                PlatformLabel: label,
                StatusLabel: publiclyAvailable
                    ? (currentDevice ? "Available on this device" : "Available now")
                    : normalizedPlatformId == "macos"
                        ? "Guided support only"
                        : "Not on downloads page",
                Summary: publiclyAvailable
                    ? BuildAvailablePlatformSummary(promotedDownload!, platform)
                    : BuildUnavailablePlatformSummary(label, platform),
                PrimaryPackageLabel: PrimaryPackageLabel(platform),
                SupportabilityLabel: $"Support: {SupportabilityLabel(platform)}",
                PubliclyAvailable: publiclyAvailable,
                CurrentDevice: currentDevice);
        }).ToArray();
    }

    private static string BuildAvailablePlatformSummary(
        PublicReleaseArtifactDto promotedDownload,
        DesktopPlatformAcceptancePlatformDocument? platform)
    {
        if (UsesMacBootstrapFlow(promotedDownload))
        {
            return "macOS is available through guided setup only.";
        }

        var packageKind = PackageKindLabel(platform?.PrimaryPackageKind ?? promotedDownload.Kind);
        var platformLabel = RequestedPlatformLabel(PlatformFamily(promotedDownload)) ?? promotedDownload.Platform;
        return $"Download the current {platformLabel} {packageKind}.";
    }

    private static string BuildUnavailablePlatformSummary(
        string platformLabel,
        DesktopPlatformAcceptancePlatformDocument? platform)
    {
        if (platform is null)
        {
            return $"{platformLabel} is not on the public downloads page right now.";
        }

        return NormalizePlatformId(platform.Id) switch
        {
            "macos" => "macOS is guided setup only today.",
            "windows" => "Windows is not on the public downloads page right now.",
            "linux" => "Linux is not on the public downloads page right now.",
            _ => $"{platformLabel} is not on the public downloads page right now."
        };
    }

    private static string PrimaryPackageLabel(DesktopPlatformAcceptancePlatformDocument? platform)
        => PackageKindLabel(platform?.PrimaryPackageKind);

    private static string PackageKindLabel(string? packageKind)
        => NormalizePackageKind(packageKind) switch
        {
            "deb" => "DEB package",
            "dmg" => "DMG installer",
            "pkg" => "PKG installer",
            "setup_script" => "setup script",
            "installer" => "installer",
            "portable_exe" => "support package",
            "archive" => "support package",
            "none" => "no public fallback",
            _ => string.IsNullOrWhiteSpace(packageKind) ? "package not specified" : packageKind.Replace('_', ' ')
        };

    private static string NormalizePackageKind(string? packageKind)
    {
        var normalized = (packageKind ?? string.Empty).Trim().ToLowerInvariant();
        return normalized switch
        {
            "portable" => "portable_exe",
            _ => normalized
        };
    }

    private static string SupportabilityLabel(DesktopPlatformAcceptancePlatformDocument? platform)
        => (platform?.Supportability ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "primary" => "primary",
            "secondary" => "secondary",
            "account_gated_setup_script_preview" => "account-gated setup continuity",
            "account_gated_setup_script_release" => "account-gated setup-script release",
            "signed_notarized_preview" => "signed and notarized track",
            "public_archive_preview" => "guided support track",
            "signed_notarized_release" => "signed and notarized release",
            _ => string.IsNullOrWhiteSpace(platform?.Supportability) ? "not specified" : platform!.Supportability.Replace('_', ' ')
        };

    private static int PlatformSortKey(string? platformId)
        => (platformId ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "windows" => 0,
            "linux" => 1,
            "macos" => 2,
            _ => 9
        };

    private static string PlatformLabel(PublicReleaseArtifactDto download)
        => PlatformFamily(download) switch
        {
            "macos" when string.Equals((download.Arch ?? string.Empty).Trim(), "arm64", StringComparison.OrdinalIgnoreCase)
                => "macOS (Apple Silicon)",
            "macos" when string.Equals((download.Arch ?? string.Empty).Trim(), "x64", StringComparison.OrdinalIgnoreCase)
                => "macOS (Intel)",
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
