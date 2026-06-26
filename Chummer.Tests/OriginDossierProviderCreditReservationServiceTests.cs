using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginDossierProviderCreditReservationServiceTests
{
    [Fact]
    public void ReserveBlocksProviderBurnUntilPacketApprovalsAccountAndCreditAreReady()
    {
        using Fixture fixture = new();
        OriginDossierProviderCreditReservationResult result = fixture.Service.Reserve(
            ValidRequest() with
            {
                SourcePacketApproved = false,
                ExternalProcessingConsent = false,
                OutlineApproved = false,
                VoiceSampleApproved = false,
                ProviderAccountAlias = "INK02_COMMERCIAL"
            },
            Fixture.Now);

        Assert.Equal("blocked", result.Status);
        Assert.False(result.ProviderBurnAllowed);
        Assert.Null(result.ReservationId);
        Assert.Contains("approved source packet", result.BlockedRequirements);
        Assert.Contains("external processing consent", result.BlockedRequirements);
        Assert.Contains("outline approval", result.BlockedRequirements);
        Assert.Contains("voice sample approval", result.BlockedRequirements);
        Assert.Contains("configured provider account alias", result.BlockedRequirements);
        Assert.Empty(fixture.Store.Entries);
    }

    [Fact]
    public void ReserveRecordsCreditHoldWithoutConsumingMyFirstBookQuota()
    {
        using Fixture fixture = new();

        OriginDossierProviderCreditReservationResult result = fixture.Service.Reserve(ValidRequest(), Fixture.Now);
        var quota = fixture.Billing.GetMyFirstBookQuota("user-origin", Fixture.Now);

        Assert.Equal("reserved", result.Status);
        Assert.True(result.ProviderBurnAllowed);
        Assert.NotNull(result.ReservationId);
        Assert.Equal(1, result.CreditsReserved);
        Assert.Single(fixture.Store.Entries);
        Assert.Equal(0, quota.MonthlyUsed);
        Assert.Equal(1, quota.MonthlyRemaining);
    }

    [Fact]
    public void ReserveAcceptsProviderAccountAliasFromRegistryWithoutDirectAliasEnv()
    {
        using Fixture fixture = new(useDirectAliases: false);

        OriginDossierProviderCreditReservationResult result = fixture.Service.Reserve(ValidRequest(), Fixture.Now);

        Assert.Equal("reserved", result.Status);
        Assert.True(result.ProviderBurnAllowed);
        Assert.Equal("FIRSTBOOK_PREMIUM", result.ProviderAccountAlias);
        Assert.Single(fixture.Store.Entries);
    }

    [Fact]
    public void ReserveAcceptsProviderAccountAliasFromRegistryFilePath()
    {
        using Fixture fixture = new(useDirectAliases: false, useRegistryPath: true);

        OriginDossierProviderCreditReservationResult result = fixture.Service.Reserve(ValidRequest(), Fixture.Now);

        Assert.Equal("reserved", result.Status);
        Assert.True(result.ProviderBurnAllowed);
        Assert.Equal("FIRSTBOOK_PREMIUM", result.ProviderAccountAlias);
        Assert.Single(fixture.Store.Entries);
    }

    [Fact]
    public void ReserveFailsClosedWhenProviderAccountRegistryFileIsMalformed()
    {
        using Fixture fixture = new(useDirectAliases: false, useRegistryPath: true, malformedRegistry: true);

        OriginDossierProviderCreditReservationResult result = fixture.Service.Reserve(ValidRequest(), Fixture.Now);

        Assert.Equal("blocked", result.Status);
        Assert.False(result.ProviderBurnAllowed);
        Assert.Contains("configured provider account alias", result.BlockedRequirements);
        Assert.Empty(fixture.Store.Entries);
    }

    [Fact]
    public void ReserveFailsClosedWhenRegistryOnlyProviderAccountIsDisabled()
    {
        using Fixture fixture = new(useDirectAliases: false, registryAccountStatus: "disabled");

        OriginDossierProviderCreditReservationResult result = fixture.Service.Reserve(ValidRequest(), Fixture.Now);

        Assert.Equal("blocked", result.Status);
        Assert.False(result.ProviderBurnAllowed);
        Assert.Contains("configured provider account alias", result.BlockedRequirements);
        Assert.Empty(fixture.Store.Entries);
    }

    [Fact]
    public void ReserveFailsClosedWhenPremiumAuthoringQuotaIsUnavailable()
    {
        using Fixture fixture = new();
        fixture.Billing.ConsumeMyFirstBookQuota("user-origin", Fixture.Now);

        OriginDossierProviderCreditReservationResult result = fixture.Service.Reserve(ValidRequest(), Fixture.Now);

        Assert.Equal("blocked", result.Status);
        Assert.False(result.ProviderBurnAllowed);
        Assert.Contains("available premium authoring quota", result.BlockedRequirements);
        Assert.Empty(fixture.Store.Entries);
    }

    [Fact]
    public void ReserveCapsActiveReservationsPerUser()
    {
        using Fixture fixture = new(maxActiveReservations: 1);
        OriginDossierProviderCreditReservationResult first = fixture.Service.Reserve(ValidRequest(projectId: "origin-one"), Fixture.Now);
        OriginDossierProviderCreditReservationResult second = fixture.Service.Reserve(ValidRequest(projectId: "origin-two"), Fixture.Now);

        Assert.Equal("reserved", first.Status);
        Assert.Equal("blocked", second.Status);
        Assert.Contains("active provider credit reservation limit", second.BlockedRequirements);
        Assert.Single(fixture.Store.Entries);
    }

    private static OriginDossierProviderCreditReservationRequest ValidRequest(string projectId = "origin-reserve-1")
        => new(
            UserId: "user-origin",
            Email: "runner@example.invalid",
            ProjectId: projectId,
            BookKind: "runner_memoir",
            PrivacyClassification: "runner_private",
            Provider: "First Book AI",
            ProviderAccountAlias: "FIRSTBOOK_PREMIUM",
            CreditsRequested: 1,
            SourcePacketApproved: true,
            ExternalProcessingConsent: true,
            ChronologyValidated: true,
            OutlineApproved: true,
            VoiceSampleApproved: true,
            CanonPreflightPassed: true,
            HumanReviewAssigned: true);

    private sealed class Fixture : IDisposable
    {
        public static readonly DateTimeOffset Now = new(2026, 6, 25, 12, 0, 0, TimeSpan.Zero);
        private readonly string _root;

        public Fixture(
            int maxActiveReservations = 5,
            bool useDirectAliases = true,
            string registryAccountStatus = "available",
            bool useRegistryPath = false,
            bool malformedRegistry = false)
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-origin-provider-reservations", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            string registryPayload = """
                    {
                      "accounts": [
                        {
                          "accountAlias": "FIRSTBOOK_PREMIUM",
                          "provider": "First Book AI",
                          "status": "%REGISTRY_ACCOUNT_STATUS%",
                          "roles": ["premium_guided_authoring", "runner_memoir", "origin"]
                        },
                        {
                          "accountAlias": "INK01_ORIGIN",
                          "provider": "Inkfluence",
                          "status": "%REGISTRY_ACCOUNT_STATUS%",
                          "roles": ["manuscript", "audio", "origin"]
                        },
                        {
                          "accountAlias": "YB02_CHUMMER_PRIVATE",
                          "provider": "Youbooks",
                          "status": "%REGISTRY_ACCOUNT_STATUS%",
                          "roles": ["scale_drafting", "origin"]
                        }
                      ]
                    }
                    """.Replace("%REGISTRY_ACCOUNT_STATUS%", registryAccountStatus, StringComparison.Ordinal);
            string registryPath = Path.Combine(_root, "ea-origin-provider-accounts.json");
            if (useRegistryPath)
            {
                File.WriteAllText(registryPath, malformedRegistry ? "{ malformed provider account registry" : registryPayload);
            }
            Dictionary<string, string?> values = new()
                {
                    ["CHUMMER_BILLING_SYNC_SECRET"] = "sync-secret",
                    ["CHUMMER_BRILLIANT_DIRECTORIES_MEMBER_STORE_PATH"] = Path.Combine(_root, "billing-members.json"),
                    ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(_root, "myfirstbook-usage.json"),
                    ["CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORE_PATH"] = Path.Combine(_root, "origin-reservations.json"),
                    ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_ALIASES"] = useDirectAliases ? "FIRSTBOOK_PREMIUM,INK01_ORIGIN,YB02_CHUMMER_PRIVATE" : null,
                    ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = useRegistryPath ? null : registryPayload,
                    ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH"] = useRegistryPath ? registryPath : null,
                    ["CHUMMER_ORIGIN_MAX_ACTIVE_PROVIDER_RESERVATIONS"] = maxActiveReservations.ToString()
                };
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(values)
                .Build();
            BrilliantDirectoriesBillingStore billingStore = new(configuration);
            MyFirstBookUsageStore usageStore = new(configuration);
            Billing = new BrilliantDirectoriesBillingService(billingStore, usageStore, configuration);
            Store = new OriginDossierProviderCreditReservationStore(configuration);
            Service = new OriginDossierProviderCreditReservationService(Store, Billing, configuration);
        }

        public BrilliantDirectoriesBillingService Billing { get; }
        public OriginDossierProviderCreditReservationStore Store { get; }
        public OriginDossierProviderCreditReservationService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
