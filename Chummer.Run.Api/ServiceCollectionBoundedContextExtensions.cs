using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;

namespace Chummer.Run.Api;

internal static class ServiceCollectionBoundedContextExtensions
{
    public static IServiceCollection AddHubPublicGuideContext(this IServiceCollection services)
    {
        services.AddSingleton<PublicCanonFileLoader>();
        services.AddSingleton<PublicRouteCatalogService>();
        services.AddSingleton<PublicActionResolver>();
        services.AddSingleton<PublicLandingService>();
        services.AddSingleton<PublicTrustContentService>();
        services.AddSingleton<PublicPrivacyBoundaryService>();
        services.AddSingleton<PublicNavigationService>();
        services.AddSingleton<HubPageChromeService>();
        services.AddSingleton<WeeklyProductPulseArtifactService>();
        services.AddSingleton<PublicProgressService>();
        services.AddSingleton<PublicTrustPulseService>();
        services.AddSingleton<CampaignOsLocalProofService>();
        services.AddSingleton<PublicReleaseManifestService>();
        services.AddSingleton<ReleaseSelectionService>();
        return services;
    }

    public static IServiceCollection AddHubAccountsAndCommunityContext(this IServiceCollection services)
    {
        services.AddSingleton<CommunityStore>();
        services.AddSingleton<AccountService>();
        services.AddSingleton<IdentityLinkService>();
        services.AddSingleton<UserExperienceService>();
        services.AddSingleton<GroupService>();
        services.AddSingleton<RewardService>();
        services.AddSingleton<EntitlementService>();
        services.AddSingleton<LeaderboardService>();
        services.AddSingleton<LedgerService>();
        services.AddScoped<BoostSessionService>();
        return services;
    }

    public static IServiceCollection AddHubCampaignSpineContext(this IServiceCollection services)
    {
        services.AddSingleton<WorkspaceLifecyclePolicyService>();
        services.AddSingleton<CampaignSpineService>();
        services.AddSingleton<CampaignWorkspaceServerPlaneService>();
        return services;
    }

    public static IServiceCollection AddHubControlAndSupportContext(this IServiceCollection services)
    {
        services.AddSingleton<SupportStore>();
        services.AddSingleton<SupportAttachmentStorageService>();
        services.AddSingleton<SupportCaseService>();
        services.AddSingleton<SupportCasePresentationService>();
        services.AddSingleton<SupportAssistantService>();
        services.AddSingleton<CrashSupportService>();
        return services;
    }

    public static IServiceCollection AddHubInstallAndOrchestrationAdapters(this IServiceCollection services)
    {
        services.AddSingleton<InstallLinkingStore>();
        services.AddSingleton<InstallLinkingService>();
        services.AddSingleton<FleetReceiptVerifier>();
        services.AddSingleton<HubEmailLinkVerificationService>();
        services.AddHttpClient<FleetBridgeService>();
        services.AddHttpClient<HubIdentityClient>();
        services.AddHttpClient<HubBrowserAuthService>();
        services.AddHttpClient<HubGoogleAuthService>();
        return services;
    }
}
