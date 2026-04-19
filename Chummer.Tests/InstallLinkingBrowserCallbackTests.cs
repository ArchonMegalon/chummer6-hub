using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingBrowserCallbackTests
{
    [Fact]
    public void Issue_and_exchange_browser_callback_links_install_without_claim_code()
    {
        using Fixture fixture = new();

        IssueInstallBrowserCallbackResponseDto issued = fixture.Service.IssueBrowserCallback(
            new IssueInstallBrowserCallbackRequestDto(
                InstallationId: "ins-browser-1",
                ArtifactId: "avalonia-win-x64-installer",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                HeadId: "avalonia",
                Platform: "windows",
                Arch: "x64",
                CallbackUri: "chummer://install-link",
                PublicKey: "public-key",
                HostLabel: "Windows Workstation",
                InstallAccessClass: InstallAccessClasses.AccountRecommended),
            userId: "user-archon",
            subjectId: "subject-archon");

        Assert.False(issued.AlreadyClaimed);
        Assert.Equal(InstallBrowserCallbackStates.Pending, issued.Callback.Status);
        Assert.Equal("ins-browser-1", issued.Callback.InstallationId);
        Assert.Equal("avalonia-win-x64-installer", issued.Callback.ArtifactId);
        InstallLinkingSummaryDto summaryAfterIssue = fixture.Service.GetSummary("user-archon", "subject-archon");
        InstallBrowserCallbackDto pendingCallback = Assert.Single(summaryAfterIssue.PendingBrowserCallbacks!);
        Assert.Equal(issued.Callback.CallbackId, pendingCallback.CallbackId);

        ExchangeInstallBrowserCallbackResponseDto exchanged = fixture.Service.ExchangeBrowserCallback(
            new ExchangeInstallBrowserCallbackRequestDto(
                CallbackCode: issued.Callback.CallbackCode,
                InstallationId: "ins-browser-1",
                HeadId: "avalonia",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                Platform: "windows",
                Arch: "x64",
                PublicKey: "public-key",
                HostLabel: "Windows Workstation"));

        Assert.False(exchanged.AlreadyClaimed);
        Assert.Equal(InstallBrowserCallbackStates.Redeemed, exchanged.Callback.Status);
        Assert.Equal(ClaimedInstallationStates.Active, exchanged.Installation.Status);
        Assert.Equal("avalonia-win-x64-installer", exchanged.Installation.ArtifactId);
        Assert.Equal("user-archon", exchanged.Installation.UserId);
        Assert.Equal("subject-archon", exchanged.Installation.SubjectId);
        Assert.Equal(InstallationGrantStates.Active, exchanged.Grant.Status);
        Assert.Equal("ins-browser-1", exchanged.Grant.InstallationId);

        ExchangeInstallBrowserCallbackResponseDto repeated = fixture.Service.ExchangeBrowserCallback(
            new ExchangeInstallBrowserCallbackRequestDto(
                CallbackCode: issued.Callback.CallbackCode,
                InstallationId: "ins-browser-1",
                HeadId: "avalonia",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                Platform: "windows",
                Arch: "x64",
                PublicKey: "public-key",
                HostLabel: "Windows Workstation"));

        Assert.True(repeated.AlreadyClaimed);
        Assert.Equal(ClaimedInstallationStates.Active, repeated.Installation.Status);
        Assert.Equal(InstallationGrantStates.Active, repeated.Grant.Status);
        InstallLinkingSummaryDto summaryAfterExchange = fixture.Service.GetSummary("user-archon", "subject-archon");
        Assert.Empty(summaryAfterExchange.PendingBrowserCallbacks ?? Array.Empty<InstallBrowserCallbackDto>());
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _tempRoot;

        public Fixture()
        {
            _tempRoot = Path.Combine(Path.GetTempPath(), "chummer-install-browser-callback-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_tempRoot);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_tempRoot, "install-linking-store.json"),
                    ["CHUMMER_INSTALL_BROWSER_CALLBACK_LIFETIME_MINUTES"] = "15"
                })
                .Build();

            Store = new InstallLinkingStore(configuration, NullLogger<InstallLinkingStore>.Instance);
            Service = new InstallLinkingService(Store, configuration);
        }

        public InstallLinkingStore Store { get; }

        public InstallLinkingService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(_tempRoot))
            {
                Directory.Delete(_tempRoot, recursive: true);
            }
        }
    }
}
