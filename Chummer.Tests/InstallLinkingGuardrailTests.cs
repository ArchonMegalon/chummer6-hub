using System.Reflection;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingGuardrailTests
{
    [Theory]
    [InlineData(nameof(InstallLinkingController.Redeem))]
    [InlineData(nameof(InstallLinkingController.RefreshGrant))]
    [InlineData(nameof(InstallLinkingController.RevokeGrant))]
    [InlineData(nameof(InstallLinkingController.ExchangeBrowserCallback))]
    [InlineData(nameof(InstallLinkingController.ExchangeDesktopLaunch))]
    [InlineData(nameof(InstallLinkingController.ContinueClaimedInstall))]
    [InlineData(nameof(InstallLinkingController.ListClaimedInstallWorkspaces))]
    [InlineData(nameof(InstallLinkingController.SubmitClaimedInstallSupport))]
    [InlineData(nameof(InstallLinkingController.PlanClaimedInstallUpdate))]
    [InlineData(nameof(InstallLinkingController.PlanClaimedInstallRollback))]
    public void InstallLinking_routes_cap_request_body_size(string methodName)
    {
        MethodInfo method = typeof(InstallLinkingController).GetMethod(methodName)
            ?? throw new InvalidOperationException($"InstallLinkingController.{methodName} was not found.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException($"{methodName} is missing RequestSizeLimitAttribute.");

        Assert.Equal(InstallLinkingService.MaxRequestBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    [Fact]
    public void RedeemClaim_rejects_oversized_claim_code()
    {
        using Fixture fixture = new();

        InstallLinkingOperationException exception = Assert.Throws<InstallLinkingOperationException>(() => fixture.Service.RedeemClaim(
            new RedeemInstallClaimRequestDto(
                ClaimCode: new string('C', 300),
                InstallationId: "install-native",
                HeadId: "head",
                ApplicationVersion: "6.0.1",
                ChannelId: "preview",
                Platform: "windows",
                Arch: "x64")));

        Assert.Equal(StatusCodes.Status400BadRequest, exception.StatusCode);
        Assert.Contains("claim code exceeds the maximum length", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RefreshGrant_rejects_oversized_access_token()
    {
        using Fixture fixture = new();

        InstallLinkingOperationException exception = Assert.Throws<InstallLinkingOperationException>(() => fixture.Service.RefreshGrant(
            new RefreshInstallationGrantRequestDto(
                InstallationId: "install-native",
                AccessToken: new string('t', 300))));

        Assert.Equal(StatusCodes.Status400BadRequest, exception.StatusCode);
        Assert.Contains("exceeds the maximum length of", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ExchangeBrowserCallback_rejects_oversized_callback_code()
    {
        using Fixture fixture = new();

        InstallLinkingOperationException exception = Assert.Throws<InstallLinkingOperationException>(() => fixture.Service.ExchangeBrowserCallback(
            new ExchangeInstallBrowserCallbackRequestDto(
                CallbackCode: new string('a', 300),
                InstallationId: "install-native",
                HeadId: "head",
                ApplicationVersion: "6.0.1",
                ChannelId: "preview",
                Platform: "windows",
                Arch: "x64")));

        Assert.Equal(StatusCodes.Status400BadRequest, exception.StatusCode);
        Assert.Contains("callback code exceeds the maximum length", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ResolveInstallationForGrant_returns_null_for_oversized_inputs()
    {
        using Fixture fixture = new();
        InstallationGrantDto grant = fixture.SeedClaimedInstall("install-native", "user-archon", "subject-archon");

        Assert.Null(fixture.Service.ResolveInstallationForGrant(new string('i', 300), grant.AccessToken));
        Assert.Null(fixture.Service.ResolveInstallationForGrant("install-native", new string('t', 300)));
    }

    [Theory]
    [InlineData(InstallAccessClasses.OpenPublic)]
    [InlineData(InstallAccessClasses.AccountRecommended)]
    public void Anonymous_guest_readable_download_uses_ephemeral_receipt_without_durable_store_write(
        string installAccessClass)
    {
        using Fixture fixture = new();
        var artifact = new PublicReleaseArtifactDto(
            Id: "guest-readable-artifact",
            Platform: "linux",
            Url: "/downloads/files/guest-readable-artifact.tar.gz",
            Sha256: new string('a', 64),
            InstallAccessClass: installAccessClass);
        var manifest = new PublicReleaseManifestDto(
            Version: "preview-test",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UtcNow,
            Downloads: [artifact]);

        DownloadDispatchResult[] dispatches = Enumerable.Range(0, 32)
            .Select(_ => fixture.Service.IssueDownload(
                manifest,
                artifact,
                userId: null,
                subjectId: null))
            .ToArray();

        Assert.All(dispatches, static dispatch =>
        {
            Assert.Null(dispatch.ClaimTicket);
            Assert.False(string.IsNullOrWhiteSpace(dispatch.Receipt.ReceiptId));
        });
        Assert.Equal(32, dispatches.Select(static item => item.Receipt.ReceiptId).Distinct().Count());
        Assert.Empty(fixture.Store.ReceiptsById);
        Assert.Empty(fixture.Store.ClaimTicketsById);
        Assert.Equal(0, fixture.Store.PersistenceAttempts);
        Assert.False(File.Exists(fixture.Store.StoragePath));
        Assert.True(fixture.Store.IsHealthy);
    }

    [Fact]
    public void Anonymous_account_required_download_is_denied_without_durable_store_write()
    {
        using Fixture fixture = new();
        var artifact = new PublicReleaseArtifactDto(
            Id: "account-required-artifact",
            Platform: "linux",
            Url: "/downloads/files/account-required-artifact.tar.gz",
            Sha256: new string('b', 64),
            InstallAccessClass: InstallAccessClasses.AccountRequired);
        var manifest = new PublicReleaseManifestDto(
            Version: "preview-test",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UtcNow,
            Downloads: [artifact]);

        InstallLinkingOperationException exception = Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.IssueDownload(manifest, artifact, userId: null, subjectId: null));

        Assert.Equal(StatusCodes.Status401Unauthorized, exception.StatusCode);
        Assert.Equal("Account sign-in is required for this download.", exception.Message);
        Assert.Empty(fixture.Store.ReceiptsById);
        Assert.Empty(fixture.Store.ClaimTicketsById);
        Assert.Equal(0, fixture.Store.PersistenceAttempts);
        Assert.False(File.Exists(fixture.Store.StoragePath));
    }

    [Fact]
    public void Redeeming_reused_claim_scrubs_all_receipt_codes_immediately_and_across_restart()
    {
        using Fixture fixture = new();
        var artifact = new PublicReleaseArtifactDto(
            Id: "account-recommended-artifact",
            Platform: "linux",
            Url: "/downloads/files/account-recommended-artifact.tar.gz",
            Sha256: new string('c', 64),
            InstallAccessClass: InstallAccessClasses.AccountRecommended);
        var manifest = new PublicReleaseManifestDto(
            Version: "preview-test",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UtcNow,
            Downloads: [artifact]);
        DownloadDispatchResult first = fixture.Service.IssueDownload(
            manifest,
            artifact,
            userId: "user-archon",
            subjectId: "subject-archon");
        DownloadDispatchResult second = fixture.Service.IssueDownload(
            manifest,
            artifact,
            userId: "user-archon",
            subjectId: "subject-archon");

        Assert.Equal(first.ClaimTicket?.TicketId, second.ClaimTicket?.TicketId);
        Assert.Equal(first.Receipt.ClaimCode, second.Receipt.ClaimCode);
        Assert.False(string.IsNullOrWhiteSpace(first.Receipt.ClaimCode));

        fixture.Service.RedeemClaim(new RedeemInstallClaimRequestDto(
            ClaimCode: first.Receipt.ClaimCode!,
            InstallationId: "install-native",
            HeadId: "head",
            ApplicationVersion: "6.0.1",
            ChannelId: "preview",
            Platform: "linux",
            Arch: "x64"));

        Assert.Equal(2, fixture.Store.ReceiptsById.Count);
        Assert.All(fixture.Store.ReceiptsById.Values, static receipt => Assert.Null(receipt.ClaimCode));
        Assert.All(fixture.Store.ClaimTicketsById.Values, static ticket => Assert.Empty(ticket.ClaimCode));

        fixture.Restart();

        Assert.Equal(2, fixture.Store.ReceiptsById.Count);
        Assert.All(fixture.Store.ReceiptsById.Values, static receipt => Assert.Null(receipt.ClaimCode));
        Assert.All(fixture.Store.ClaimTicketsById.Values, static ticket => Assert.Empty(ticket.ClaimCode));
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        private readonly IDataProtectionProvider _dataProtectionProvider;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-install-linking-guardrail-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json")
                })
                .Build();

            _dataProtectionProvider = DataProtectionProvider.Create(
                Path.Combine(_root, "install-linking-keys"));
            Store = CreateStore();
            Service = new InstallLinkingService(Store, Configuration);
        }

        public IConfiguration Configuration { get; }
        public InstallLinkingStore Store { get; private set; }
        public InstallLinkingService Service { get; private set; }

        public void Restart()
        {
            Store.Dispose();
            Store = CreateStore();
            Service = new InstallLinkingService(Store, Configuration);
        }

        public InstallationGrantDto SeedClaimedInstall(string installationId, string userId, string? subjectId)
        {
            lock (Store.Gate)
            {
                string normalizedInstallationId = installationId;
                InstallationGrantDto grant = new(
                    GrantId: $"grant-{normalizedInstallationId}",
                    InstallationId: normalizedInstallationId,
                    Status: InstallationGrantStates.Active,
                    AccessToken: $"token-{normalizedInstallationId}",
                    IssuedAtUtc: DateTimeOffset.UtcNow,
                    ExpiresAtUtc: DateTimeOffset.UtcNow.AddDays(30),
                    UserId: userId,
                    SubjectId: subjectId);
                Store.InstallationsById[normalizedInstallationId] = new ClaimedInstallationDto(
                    InstallationId: normalizedInstallationId,
                    ArtifactId: "avalonia-win-x64-installer",
                    Channel: "preview",
                    Version: "6.0.1",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
                    UpdatedAtUtc: DateTimeOffset.UtcNow,
                    UserId: userId,
                    SubjectId: subjectId,
                    PublicKey: "public-key",
                    ClaimTicketId: $"ticket-{normalizedInstallationId}",
                    HeadId: "desktop",
                    Platform: "windows",
                    Arch: "x64",
                    HostLabel: "Host",
                    GrantId: grant.GrantId);
                Store.GrantsById[grant.GrantId] = grant;
                Store.PersistLocked();
                return grant;
            }
        }

        public void Dispose()
        {
            Store.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private InstallLinkingStore CreateStore()
            => new(
                Configuration,
                _dataProtectionProvider,
                NullLogger<InstallLinkingStore>.Instance);
    }
}
