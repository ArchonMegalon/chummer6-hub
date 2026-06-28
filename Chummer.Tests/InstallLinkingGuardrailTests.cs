using System.Reflection;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.InstallLinking;
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

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

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

            Store = new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance);
            Service = new InstallLinkingService(Store, Configuration);
        }

        public IConfiguration Configuration { get; }
        public InstallLinkingStore Store { get; }
        public InstallLinkingService Service { get; }

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
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
