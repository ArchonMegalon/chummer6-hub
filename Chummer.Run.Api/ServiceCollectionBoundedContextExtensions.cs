using Chummer.Contracts.Workspaces;
using Chummer.Engine.GmCharacterEdits;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.Services.Teable;
using Chummer.Storage.Teable;
using Chummer.Run.Api.Services.WindowsProof;
using Chummer.Run.Registry.Services;
using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api;

internal static class ServiceCollectionBoundedContextExtensions
{
    internal const string CommunityPrimaryStoreKey = "chummer.community.primary";

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
        services.AddSingleton(static provider => new ReleaseShelfGenerationStore(
            provider.GetRequiredService<IConfiguration>(),
            provider.GetRequiredService<IHttpContextAccessor>()));
        services.AddSingleton(static provider => new PublicReleaseManifestService(
            provider.GetRequiredService<IConfiguration>(),
            provider.GetRequiredService<ReleaseShelfGenerationStore>()));
        services.AddSingleton<ArtifactDeliveryPolicy>();
        services.AddSingleton<ReleaseAuthorityRevisionStore>();
        services.AddSingleton<IReleaseTruthProjection, PublicReleaseTruthProjectionService>();
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
        services.AddKeyedSingleton<TeableRevisionStore>(CommunityPrimaryStoreKey, (provider, _) =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            if (configuration["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] != "teable")
                throw new InvalidOperationException("Community primary transport requires explicit Teable mode.");
            return TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_COMMUNITY_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary community table is required."),
                configuration["CHUMMER_COMMUNITY_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private community token file is required."));
        });
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            var logger = provider.GetRequiredService<ILogger<CommunityStore>>();
            var primary = configuration["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] == "teable"
                ? provider.GetRequiredKeyedService<TeableRevisionStore>(CommunityPrimaryStoreKey)
                : null;
            // The container owns the keyed transport. CommunityStore validates
            // the current remote schema before any account service is returned.
            return new CommunityStore(configuration, logger, primary);
        });
        services.AddSingleton<IPlaySessionAuthorizationPersistence, CommunityStorePlaySessionAuthorizationPersistence>();
        services.AddSingleton<PlaySessionAuthorizationService>();
        services.AddSingleton<PlayAuthorizationIdempotencyCoordinator>();
        services.AddSingleton<PlayAuthorizationApiPolicy>();
        services.AddSingleton<PlayAuthorizationRequestLimiter>();
        services.AddSingleton<TeableUserProjectionService>();
        services.AddSingleton<IHubUserProjectionSyncQueue>(serviceProvider =>
            serviceProvider.GetRequiredService<TeableUserProjectionService>());
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
        services.AddHttpClient<HubSessionAccountAdmissionService>(client =>
            client.Timeout = HubSessionAccountAdmissionService.RequestTimeout)
            .ConfigurePrimaryHttpMessageHandler(static () => new SocketsHttpHandler
            {
                AllowAutoRedirect = false,
                UseCookies = false,
                ConnectTimeout = TimeSpan.FromSeconds(5),
                MaxResponseHeadersLength = 16
            })
            .RemoveAllLoggers();
        services.AddSingleton<CommunityAccountErasureService>();
        services.AddSingleton<IdentityLinkService>();
        services.AddSingleton<UserExperienceService>();
        services.AddSingleton<GroupService>();
        services.AddSingleton<ReusableAccountFlowService>();
        services.AddSingleton<RewardService>();
        services.AddSingleton<EntitlementService>();
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            var logger = provider.GetService<ILogger<BrilliantDirectoriesBillingStore>>();
            if (configuration["CHUMMER_BILLING_MEMBERSHIP_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new BrilliantDirectoriesBillingStore(configuration, logger);
            var primary = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_BILLING_MEMBERSHIP_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary membership table is required."),
                configuration["CHUMMER_BILLING_MEMBERSHIP_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private membership token file is required."));
            try { return new BrilliantDirectoriesBillingStore(configuration, logger, primary, ownsPrimary: true); }
            catch { primary.Dispose(); throw; }
        });
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            var logger = provider.GetService<ILogger<MyFirstBookUsageStore>>();
            if (configuration["CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new MyFirstBookUsageStore(configuration, logger);
            var primary = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_MYFIRSTBOOK_USAGE_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary usage table is required."),
                configuration["CHUMMER_MYFIRSTBOOK_USAGE_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private usage token file is required."));
            try { return new MyFirstBookUsageStore(configuration, logger, primary, ownsPrimary: true); }
            catch { primary.Dispose(); throw; }
        });
        services.AddSingleton<BrilliantDirectoriesBillingService>();
        services.AddSingleton<HorizonCapabilityService>();
        services.AddSingleton<HorizonArtifactAccessTokenService>();
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            if (configuration["CHUMMER_HORIZON_ARTIFACT_USAGE_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new HorizonArtifactUsageStore(configuration);
            var primary = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_HORIZON_ARTIFACT_USAGE_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary artifact usage table is required."),
                configuration["CHUMMER_HORIZON_ARTIFACT_USAGE_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private artifact usage token is required."));
            try { return new HorizonArtifactUsageStore(configuration, primary, ownsPrimary: true); }
            catch { primary.Dispose(); throw; }
        });
        services.AddSingleton<HorizonArtifactQuotaService>();
        services.AddSingleton<OriginAuthoringAllowanceProjectionService>();
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            if (configuration["CHUMMER_HORIZON_REQUEST_RECEIPT_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new HorizonArtifactRequestReceiptStore(configuration);
            var primary = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_HORIZON_REQUEST_RECEIPT_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary artifact receipt table is required."),
                configuration["CHUMMER_HORIZON_REQUEST_RECEIPT_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private artifact receipt token is required."));
            try { return new HorizonArtifactRequestReceiptStore(configuration, primary, ownsPrimary: true); }
            catch { primary.Dispose(); throw; }
        });
        services.AddSingleton<HorizonArtifactRequestService>();
        services.AddSingleton<SubscribrWebhookStore>();
        services.AddSingleton<SubscribrProviderWebhookService>();
        services.AddSingleton<RunsiteTourQuotaService>();
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            var logger = provider.GetRequiredService<ILogger<OriginDossierPublicationService>>();
            var capabilities = provider.GetService<HorizonCapabilityService>();
            var media = provider.GetService<MediaArtifactHorizonsService>();
            if (configuration["CHUMMER_ORIGIN_PUBLICATION_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new OriginDossierPublicationService(configuration, capabilities, media, logger);
            var store = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_ORIGIN_PUBLICATION_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary publication table is required."),
                configuration["CHUMMER_ORIGIN_PUBLICATION_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private publication token is required."));
            try
            {
                return new OriginDossierPublicationService(configuration, capabilities, media, logger,
                    new TeableOriginPublicationStorage(store, configuration["CHUMMER_ORIGIN_PUBLICATION_IMPORT_ROOT"], ownsStore: true));
            }
            catch { store.Dispose(); throw; }
        });
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            if (configuration["CHUMMER_ORIGIN_DOCUMENT_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new OriginDossierFirstPartyDocumentService(configuration);
            var store = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_ORIGIN_DOCUMENT_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Origin document primary table is required."),
                configuration["CHUMMER_ORIGIN_DOCUMENT_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private document storage token is required."));
            try { return new OriginDossierFirstPartyDocumentService(configuration, new TeableOriginDocumentStorage(store, ownsStore: true)); }
            catch { store.Dispose(); throw; }
        });
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            if (configuration["CHUMMER_ORIGIN_CHAPTER_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new OriginChapterAuthoringService(configuration);
            var store = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_ORIGIN_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Origin primary table is required."),
                configuration["CHUMMER_ORIGIN_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private Origin storage token is required."));
            return new OriginChapterAuthoringService(configuration, new TeableOriginChapterStorage(store, ownsStore: true));
        });
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            if (configuration["CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new OriginDossierProviderCreditReservationStore(configuration);
            var primary = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_ORIGIN_PROVIDER_RESERVATION_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary reservation table is required."),
                configuration["CHUMMER_ORIGIN_PROVIDER_RESERVATION_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private reservation token file is required."));
            try { return new OriginDossierProviderCreditReservationStore(configuration, primary, ownsPrimary: true); }
            catch { primary.Dispose(); throw; }
        });
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
        services.AddSingleton<ICampaignGmCharacterEditAuthorizer>(static provider =>
            new CommunityStoreCampaignGmCharacterEditAuthorizer(
                provider.GetRequiredService<CommunityStore>(),
                provider.GetService<TimeProvider>() ?? TimeProvider.System));
        services.AddSingleton<ICoreGmCharacterEditGateway>(static provider =>
        {
            IConfiguration configuration = provider.GetRequiredService<IConfiguration>();
            string? workspaceStorePath =
                configuration["Chummer:CoreGmCharacterEdits:WorkspaceStorePath"];
            if (workspaceStorePath is null)
            {
                return new UnavailableCoreGmCharacterEditGateway();
            }

            if (string.IsNullOrWhiteSpace(workspaceStorePath))
            {
                throw new InvalidOperationException(
                    "Chummer:CoreGmCharacterEdits:WorkspaceStorePath cannot be blank when configured.");
            }

            return CoreGmCharacterEditGatewayFactory.CreateStoreBacked(
                workspaceStorePath,
                provider.GetRequiredService<ICampaignGmCharacterEditAuthorizer>(),
                provider.GetService<TimeProvider>() ?? TimeProvider.System);
        });
        services.AddSingleton<CampaignCollaborationService>();
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
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            var logger = provider.GetRequiredService<ILogger<SupportStore>>();
            if (configuration["CHUMMER_SUPPORT_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new SupportStore(configuration, logger);
            var primary = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_SUPPORT_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary support table is required."),
                configuration["CHUMMER_SUPPORT_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private support token file is required."));
            try { return new SupportStore(configuration, logger, primary, ownsPrimary: true); }
            catch { primary.Dispose(); throw; }
        });
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
        bool publicDownloadOnly = environment.IsProduction()
            && configuration.GetValue<bool>("CHUMMER_PUBLIC_DOWNLOAD_ONLY");
        string storageProvider = configuration["CHUMMER_INSTALL_LINKING_STORAGE_PROVIDER"] ?? "postgres";
        if (storageProvider is not ("postgres" or "teable"))
            throw new InvalidOperationException("Install-linking storage provider is invalid.");
        if (storageProvider == "teable")
        {
            if (!environment.IsProduction() || publicDownloadOnly
                || configuration["CHUMMER_DATA_PROTECTION_KEY_PROTECTION_MODE"]?.Trim() != TeableDataProtectionRuntime.Mode
                || !string.IsNullOrWhiteSpace(configuration["CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE"])
                || !string.IsNullOrWhiteSpace(configuration["CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING"]))
                throw new InvalidOperationException("Teable install-linking requires explicit production primary key custody and no competing PostgreSQL configuration.");
            services.AddSingleton<TeableInstallLinkingRuntime>();
            services.AddSingleton(provider => new InstallLinkingPostgresAuthorityCoordinator(
                provider.GetRequiredService<TeableInstallLinkingRuntime>().Authority, backend: "teable"));
            services.AddSingleton<IInstallLinkingSnapshotAuthority>(provider =>
                provider.GetRequiredService<InstallLinkingPostgresAuthorityCoordinator>());
            services.AddSingleton<IInstallLinkingRollbackAuthorityReadinessProbe>(provider =>
                provider.GetRequiredService<InstallLinkingPostgresAuthorityCoordinator>());
        }
        else if (environment.IsProduction() && !publicDownloadOnly)
        {
            services.AddSingleton(_ => new InstallLinkingPostgresRuntime(
                InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                    configuration,
                    environment)));
            string expectedRuntimeRole =
                InstallLinkingPostgresConnectionConfiguration
                    .LoadExpectedRuntimeRole(configuration);
            services.AddSingleton(provider =>
                new NpgsqlInstallLinkingSnapshotAuthority(
                    provider.GetRequiredService<InstallLinkingPostgresRuntime>().DataSource,
                    expectedRuntimeRole: expectedRuntimeRole));
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

        AddHubInstallAndOrchestrationAdapterCore(
            services,
            deferAuthorityActivation: environment.IsProduction());
        return services.AddHubPrivateRookRuntime(configuration, environment);
    }

    private static IServiceCollection AddHubInstallAndOrchestrationAdapterCore(
        IServiceCollection services,
        bool deferAuthorityActivation)
    {
        services.AddSingleton<InstallLinkingStoreActivation>();
        services.AddSingleton<InstallLinkingStoreAccess>();
        services.AddSingleton<IInstallLinkingStoreReadinessProbe>(static provider =>
            provider.GetRequiredService<InstallLinkingStoreActivation>());
        if (deferAuthorityActivation)
        {
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
        services.AddSingleton(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            if (configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_STORAGE_PROVIDER"]?.Trim() != "teable")
                return new InstallLinkedWorkspaceSnapshotStore(configuration);
            var primary = TeableRevisionStore.OpenFromPrivateTokenFile(
                new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
                configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Primary workspace table is required."),
                configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private workspace storage token is required."));
            try { return new InstallLinkedWorkspaceSnapshotStore(configuration, primary, ownsPrimary: true); }
            catch { primary.Dispose(); throw; }
        });
        services.AddSingleton<InstallLinkedWorkspaceSnapshotService>();
        services.AddTransient<RookWorkspaceReadAdmissionService>();
        services.AddSingleton<AndroidLinkedV2RequestProofVerifier>();
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
        services.AddHttpClient<IHostedBuildAccountErasureClient, HostedBuildAccountErasureClient>();
        services.AddSingleton<AccountErasureJournalStore>();
        services.AddTransient<IAccountAuxiliaryDataErasureService, AccountAuxiliaryDataErasureService>();
        services.AddTransient<AccountErasureService>();
        services.AddTransient<IAccountErasureService>(static provider =>
            provider.GetRequiredService<AccountErasureService>());
        services.AddHostedService<AccountErasureRecoveryWorker>();
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
