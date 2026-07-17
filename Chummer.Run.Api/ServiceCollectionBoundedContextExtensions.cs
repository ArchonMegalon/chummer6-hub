using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.Services.WindowsProof;
using Chummer.Run.Registry.Services;
using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api;

internal static class ServiceCollectionBoundedContextExtensions
{
    public static IServiceCollection AddHubPublicGuideContext(this IServiceCollection services)
    {
        services.AddHttpContextAccessor();
        services.AddSingleton<PublicCanonFileLoader>();
        services.AddSingleton<PublicRouteCatalogService>();
        services.AddSingleton<PublicActionResolver>();
        services.AddSingleton<PublicLandingService>();
        services.AddSingleton<FlipLinkDocumentPortalService>();
        services.AddSingleton<PublicPackageCatalogService>();
        services.AddSingleton<PublicFlagshipCoverageService>();
        services.AddSingleton<PublicTrustContentService>();
        services.AddSingleton<PublicPrivacyBoundaryService>();
        services.AddSingleton<PublicSignalProjectionService>();
        services.AddSingleton<PublicSignalOperationsService>();
        services.AddSingleton<PublicParticipateSnapshotStore>();
        services.AddSingleton<PublicParticipateSnapshotService>();
        services.AddSingleton<PublicConciergeStore>();
        services.AddSingleton<PublicConciergeService>();
        services.AddHostedService<PublicParticipateSnapshotWorker>();
        services.AddHostedService<PublicSignalRetryExpiryWorker>();
        services.AddHostedService<PublicSurfaceWarmupService>();
        services.AddHostedService<PublicRouteWarmupService>();
        services.AddSingleton<PublicNavigationService>();
        services.AddSingleton<HubPageChromeService>();
        services.AddSingleton<ReadyForTonightService>();
        services.AddSingleton<KnowledgeFabricService>();
        services.AddSingleton<NexusPanContinuityService>();
        services.AddSingleton<MediaArtifactHorizonsService>();
        services.AddSingleton<CommunityCreatorHorizonsService>();
        services.AddSingleton<WaveEightHorizonsService>();
        services.AddSingleton<KarmaForgeStore>();
        services.AddSingleton<KarmaForgeDiscoveryService>();
        services.AddSingleton<BuildGhostConciergeService>();
        services.AddSingleton<BlackLedgerPublicStatsService>();
        services.AddSingleton<BlackLedgerDispatchService>();
        services.AddSingleton<BlackLedgerFactionOnboardingService>();
        services.AddSingleton<BlackLedgerWorldTickBriefingService>();
        services.AddSingleton<BeHumanEventAdapterPostureService>();
        services.AddSingleton<AnarchyPreviewService>();
        services.AddSingleton<TeableKarmaForgeReviewBoardService>();
        services.AddHostedService<TeableKarmaForgeReviewBoardSyncWorker>();
        services.AddSingleton<WeeklyProductPulseArtifactService>();
        services.AddSingleton<PublicProgressService>();
        services.AddSingleton<PublicTrustPulseService>();
        services.AddSingleton<CampaignOsLocalProofService>();
        services.AddSingleton<ReleaseShelfGenerationStore>();
        services.AddSingleton(static provider => new PublicReleaseManifestService(
            provider.GetRequiredService<IConfiguration>(),
            provider.GetRequiredService<ReleaseShelfGenerationStore>()));
        services.AddSingleton<ArtifactDeliveryPolicy>();
        services.AddSingleton<WindowsProofManifestValidator>();
        services.AddSingleton<WindowsProofGenerationStore>();
        services.AddSingleton<IWindowsProofGenerationStore>(static provider =>
            provider.GetRequiredService<WindowsProofGenerationStore>());
        services.AddSingleton<WindowsProofInstallerService>();
        services.AddSingleton<AurPackageCatalogService>();
        services.AddSingleton<ReleaseSelectionService>();
        services.AddSingleton<SignedInTrustStatusService>();
        return services;
    }

    public static IServiceCollection AddHubAccountsAndCommunityContext(this IServiceCollection services)
    {
        services.AddSingleton(TimeProvider.System);
        services.AddSingleton<CommunityStore>();
        services.AddSingleton<IPlaySessionAuthorizationPersistence, CommunityStorePlaySessionAuthorizationPersistence>();
        services.AddSingleton<PlaySessionAuthorizationService>();
        services.AddSingleton<PlayAuthorizationIdempotencyCoordinator>();
        services.AddSingleton<PlayAuthorizationApiPolicy>();
        services.AddSingleton<PlayAuthorizationRequestLimiter>();
        services.AddSingleton<TeableUserProjectionService>();
        services.AddSingleton<TeableBlackLedgerWorldTickService>();
        services.AddSingleton<TeableHeyyScamChatService>();
        services.AddSingleton<TeableExecutiveAssistantChannelService>();
        services.AddSingleton<TeableImportantWorkService>();
        services.AddHostedService<TeableUserProjectionSyncWorker>();
        services.AddHostedService<TeableBlackLedgerWorldTickSyncWorker>();
        services.AddHostedService<TeableHeyyScamChatSyncWorker>();
        services.AddHostedService<TeableExecutiveAssistantChannelSyncWorker>();
        services.AddHostedService<TeableImportantWorkSyncWorker>();
        services.AddHttpClient();
        services.AddSingleton<AccountService>();
        services.AddSingleton<IdentityLinkService>();
        services.AddSingleton<UserExperienceService>();
        services.AddSingleton<GroupService>();
        services.AddSingleton<ReusableAccountFlowService>();
        services.AddSingleton<RewardService>();
        services.AddSingleton<EntitlementService>();
        services.AddSingleton<BrilliantDirectoriesBillingStore>();
        services.AddSingleton<MyFirstBookUsageStore>();
        services.AddSingleton<BrilliantDirectoriesBillingService>();
        services.AddSingleton<HorizonCapabilityService>();
        services.AddSingleton<HorizonArtifactAccessTokenService>();
        services.AddSingleton<HorizonArtifactUsageStore>();
        services.AddSingleton<HorizonArtifactQuotaService>();
        services.AddSingleton<OriginAuthoringAllowanceProjectionService>();
        services.AddSingleton<HorizonArtifactRequestReceiptStore>();
        services.AddSingleton<HorizonArtifactRequestService>();
        services.AddSingleton<SubscribrWebhookStore>();
        services.AddSingleton<SubscribrProviderWebhookService>();
        services.AddSingleton<RunsiteTourQuotaService>();
        services.AddSingleton<OriginDossierPublicationService>();
        services.AddSingleton<OriginDossierProviderCreditReservationStore>();
        services.AddSingleton<OriginDossierProviderCreditReservationService>();
        services.AddSingleton<PayFunnelsBillingStore>();
        services.AddSingleton<PayFunnelsBillingService>();
        services.AddSingleton<LeaderboardService>();
        services.AddSingleton<LedgerService>();
        services.AddHttpClient<ParticipationOperatorNotificationService>();
        services.AddHttpClient<ExecutiveAssistantChannelMessagingService>();
        services.AddHttpClient<HeyyScamChatService>();
        services.AddHostedService<HeyyScamChatDigestWorker>();
        services.AddSingleton<BlackLedgerNewsRecipientResolver>();
        services.AddHttpClient<BlackLedgerTickNewsNotificationService>();
        services.AddHttpClient<BlackLedgerAdvisoryService>();
        services.AddHostedService<BlackLedgerTickNewsDispatchWorker>();
        services.AddScoped<BoostSessionService>();
        return services;
    }

    public static IServiceCollection AddHubCampaignSpineContext(this IServiceCollection services)
    {
        services.AddSingleton<WorkspaceLifecyclePolicyService>();
        services.AddSingleton<RunsiteOrientationRequestComposerService>();
        services.AddSingleton<RunsiteOrientationArtifactRequestBridgeService>();
        services.AddSingleton<PropertyquarryApartmentVideoArtifactRequestBridgeService>();
        services.AddSingleton<IHubPublicationDraftService, HubPublicationDraftService>();
        services.AddSingleton<CampaignArtifactRegistryBridge>();
        services.AddSingleton<CreatorPublicationRegistryBridge>();
        services.AddSingleton<PublicCreatorPublicationDiscoveryService>();
        services.AddSingleton<CampaignSpineService>();
        services.AddSingleton<GmSessionVenueStore>();
        services.AddSingleton<IGmSessionVenueAdapter, BeHumanGmSessionVenueAdapter>();
        services.AddSingleton<GmSessionVenueService>();
        services.AddSingleton<GmSessionVideoFoundryStore>();
        services.AddSingleton<GmSessionVideoFoundryService>();
        services.AddSingleton<PromptFoundryStore>();
        services.AddSingleton<PromptFoundryService>();
        services.AddSingleton<CampaignFederationOrchestrationService>();
        services.AddSingleton<CampaignWorkspaceServerPlaneService>();
        services.AddSingleton<CampaignFederationOrchestrationService>();
        return services;
    }

    public static IServiceCollection AddHubControlAndSupportContext(this IServiceCollection services)
    {
        services.AddSingleton<SupportStore>();
        services.AddSingleton<SupportAttachmentStorageService>();
        services.AddSingleton<SupportCaseService>();
        services.AddSingleton<SupportCasePresentationService>();
        services.AddSingleton<SupportConciergePacketService>();
        services.AddSingleton<HostedCompanionPacketService>();
        services.AddSingleton<HostedProofContractService>();
        services.AddSingleton<HostedBoundedContextCoverageService>();
        services.AddSingleton<RegistryTruthBindingService>();
        services.AddSingleton<PrivacyBoundedSupportStatusService>();
        services.AddSingleton<PublicSignalToCanonPacketService>();
        services.AddSingleton<ExecutiveAssistantCredentialCatalogService>();
        services.AddSingleton<SupportAssistantService>();
        services.AddSingleton<IFirstPartySupportAssistant>(static provider => provider.GetRequiredService<SupportAssistantService>());
        services.AddSingleton<AnswerlyRuntimePolicy>();
        services.AddSingleton<RuleSafeOutputGate>();
        services.AddSingleton<RulesCoachRouter>();
        services.AddSingleton<AnswerlyHumanizerAdapter>();
        services.AddSingleton<RuleGhostService>();
        services.AddSingleton<AnswerlyOpenAiCompatService>();
        services.AddSingleton<IChummerAssistantAdapter, AnswerlySupportAssistantAdapter>();
        services.AddSingleton<CrashSupportService>();
        services.AddHttpClient<SupportProgressEmailWorkflowService>();
        return services;
    }

    public static IServiceCollection AddHubInstallAndOrchestrationAdapters(
        this IServiceCollection services)
    {
        services.AddSingleton<IInstallLinkingRollbackAuthorityReadinessProbe,
            UnavailableInstallLinkingRollbackAuthorityReadinessProbe>();
        return AddHubInstallAndOrchestrationAdapterCore(
            services,
            deferAuthorityActivation: false);
    }

    public static IServiceCollection AddHubInstallAndOrchestrationAdapters(
        this IServiceCollection services,
        IConfiguration configuration,
        IHostEnvironment environment)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(environment);
        if (environment.IsProduction())
        {
            services.AddSingleton(_ => new InstallLinkingPostgresRuntime(
                InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                    configuration,
                    environment)));
            services.AddSingleton(static provider =>
                new NpgsqlInstallLinkingSnapshotAuthority(
                    provider.GetRequiredService<InstallLinkingPostgresRuntime>().DataSource));
            services.AddSingleton(static provider =>
                new InstallLinkingPostgresAuthorityCoordinator(
                    provider.GetRequiredService<NpgsqlInstallLinkingSnapshotAuthority>()));
            services.AddSingleton<IInstallLinkingSnapshotAuthority>(static provider =>
                provider.GetRequiredService<InstallLinkingPostgresAuthorityCoordinator>());
            services.AddSingleton<IInstallLinkingRollbackAuthorityReadinessProbe>(static provider =>
                provider.GetRequiredService<InstallLinkingPostgresAuthorityCoordinator>());
        }
        else
        {
            services.AddSingleton<IInstallLinkingRollbackAuthorityReadinessProbe,
                UnavailableInstallLinkingRollbackAuthorityReadinessProbe>();
        }

        return AddHubInstallAndOrchestrationAdapterCore(
            services,
            deferAuthorityActivation: environment.IsProduction());
    }

    private static IServiceCollection AddHubInstallAndOrchestrationAdapterCore(
        IServiceCollection services,
        bool deferAuthorityActivation)
    {
        services.AddSingleton<InstallLinkingStoreActivation>();
        services.AddSingleton<IInstallLinkingStoreReadinessProbe>(static provider =>
            provider.GetRequiredService<InstallLinkingStoreActivation>());
        if (deferAuthorityActivation)
        {
            services.AddSingleton<InstallLinkingStoreAccess>();
            services.AddSingleton(static provider => new InstallLinkingService(
                provider.GetRequiredService<InstallLinkingStoreAccess>(),
                provider.GetRequiredService<IConfiguration>(),
                provider.GetRequiredService<IInstallLinkingStoreReadinessProbe>()));
            services.AddSingleton(static provider => new PersonalizedInstallScriptService(
                provider.GetRequiredService<InstallLinkingStoreAccess>(),
                provider.GetRequiredService<IConfiguration>(),
                provider.GetRequiredService<IInstallLinkingStoreReadinessProbe>()));
            services.AddSingleton(static provider => new NexusPanContinuityService(
                provider.GetRequiredService<InstallLinkingStoreAccess>()));
            services.AddSingleton(static provider => new CommunityCreatorHorizonsService(
                provider.GetRequiredService<CommunityStore>(),
                provider.GetRequiredService<InstallLinkingStoreAccess>(),
                provider.GetRequiredService<PublicCreatorPublicationDiscoveryService>()));
        }
        else
        {
            services.AddSingleton(static provider =>
                provider.GetRequiredService<InstallLinkingStoreActivation>().GetActivatedStoreForDependencyInjection());
            services.AddSingleton<InstallLinkingService>();
            services.AddSingleton<PersonalizedInstallScriptService>();
        }
        services.AddSingleton<InstallLinkedWorkspaceSnapshotStore>();
        services.AddSingleton<InstallLinkedWorkspaceSnapshotService>();
        services.AddSingleton<AccountDesktopLaunchTicketService>();
        services.AddSingleton<InstallBootstrapTicketService>();
        services.AddSingleton<ReleaseBundlePromotionService>();
        services.AddSingleton<ReleaseBundleUploadSessionService>();
        services.AddSingleton<ReleaseUploadTicketService>();
        services.AddSingleton<ArtifactFactoryOrchestrationService>();
        services.AddSingleton<FleetReceiptVerifier>();
        services.AddSingleton<HubEmailLinkVerificationService>();
        services.AddSingleton<HubIdentityHintCookieService>();
        services.AddSingleton<HubIdentitySubjectCache>();
        services.AddHttpClient<FleetBridgeService>();
        services.AddHttpClient<HubIdentityClient>();
        services.AddTransient<IPublicPlayIdentityResolver, HubPublicPlayIdentityResolver>();
        services.AddSingleton<IPlaySessionGrantAuthorizer, DenyAllPlaySessionGrantAuthorizer>();
        services.AddTransient<PublicPlaySessionAccessPolicy>();
        services.AddTransient<IPublicPlaySessionAccessPolicy>(static provider =>
            provider.GetRequiredService<PublicPlaySessionAccessPolicy>());
        services.AddHttpClient<HubBrowserAuthService>();
        services.AddHttpClient<HubGoogleAuthService>();
        return services;
    }
}
