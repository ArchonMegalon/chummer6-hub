using System.Diagnostics;
using System.Net;
using System.Text;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicSurfaceWarmupServiceTests : IDisposable
{
    private readonly string _tempRoot = Path.Combine(Path.GetTempPath(), $"public-surface-warmup-{Guid.NewGuid():N}");

    public PublicSurfaceWarmupServiceTests()
    {
        Directory.CreateDirectory(_tempRoot);
    }

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(_tempRoot))
            {
                Directory.Delete(_tempRoot, recursive: true);
            }
        }
        catch
        {
            // Test cleanup should not hide the actual assertion failure.
        }
    }

    [Fact]
    public async Task StartAsyncDoesNotWaitForParticipateSnapshotRefresh()
    {
        var httpClientFactory = new BlockingParticipateHttpClientFactory();
        using ServiceProvider services = BuildServices(httpClientFactory);
        var warmup = new PublicSurfaceWarmupService(services, NullLogger<PublicSurfaceWarmupService>.Instance);

        try
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            await warmup.StartAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(1));
            stopwatch.Stop();

            Assert.True(
                stopwatch.Elapsed < TimeSpan.FromSeconds(1),
                $"public surface warmup should not wait for participate refresh, but took {stopwatch.Elapsed}.");

            await httpClientFactory.RequestStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.False(
                httpClientFactory.AllowResponse.IsSet,
                "the participate refresh should still be in flight after warmup returns.");
            Assert.False(httpClientFactory.RequestCompleted.Task.IsCompleted);
        }
        finally
        {
            bool requestStarted = httpClientFactory.RequestStarted.Task.IsCompletedSuccessfully;
            httpClientFactory.AllowResponse.Set();
            if (requestStarted)
            {
                await httpClientFactory.RequestCompleted.Task.WaitAsync(TimeSpan.FromSeconds(10));
            }
        }
    }

    [Fact]
    public async Task StartAsyncDoesNotWaitForInstallLinkingReadinessProbe()
    {
        var httpClientFactory = new BlockingParticipateHttpClientFactory();
        var installLinkingProbe = new BlockingInstallLinkingStoreProbe();
        using ServiceProvider services = BuildServices(httpClientFactory, installLinkingProbe);
        var warmup = new PublicSurfaceWarmupService(services, NullLogger<PublicSurfaceWarmupService>.Instance);

        try
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            await warmup.StartAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(1));
            stopwatch.Stop();

            Assert.True(
                stopwatch.Elapsed < TimeSpan.FromSeconds(1),
                $"public surface warmup should not wait for install-linking readiness, but took {stopwatch.Elapsed}.");
            await installLinkingProbe.EvaluationStarted.Task.WaitAsync(TimeSpan.FromSeconds(1));
            Assert.False(installLinkingProbe.AllowEvaluation.Task.IsCompleted);
        }
        finally
        {
            installLinkingProbe.AllowEvaluation.TrySetResult(true);
            bool requestStarted = httpClientFactory.RequestStarted.Task.IsCompletedSuccessfully;
            httpClientFactory.AllowResponse.Set();
            if (requestStarted)
            {
                await httpClientFactory.RequestCompleted.Task.WaitAsync(TimeSpan.FromSeconds(10));
            }
        }
    }

    private ServiceProvider BuildServices(
        IHttpClientFactory httpClientFactory,
        IInstallLinkingStoreReadinessProbe? installLinkingStoreProbe = null)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                ["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] = "https://ideas.example.test/feedback",
                ["CHUMMER_PUBLIC_PARTICIPATE_SNAPSHOT_STORE_PATH"] = Path.Combine(_tempRoot, "public-participate-snapshot.json"),
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(_tempRoot, "billing-store.json"),
                ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(_tempRoot, "myfirstbook-usage-store.json"),
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_tempRoot, "install-linking-store.json"),
            })
            .Build();
        IWebHostEnvironment environment = new FakeWebHostEnvironment("Production");
        var canon = new PublicCanonFileLoader(configuration);
        var routes = new PublicRouteCatalogService(canon);
        var landing = new PublicLandingService(canon, new PublicActionResolver());
        var navigation = new PublicNavigationService(canon, routes);
        var releaseManifest = new PublicReleaseManifestService(configuration);
        var billingStore = new BrilliantDirectoriesBillingStore(configuration);
        var usageStore = new MyFirstBookUsageStore(configuration);
        var installLinkingStore = new InstallLinkingStore(
            configuration,
            DataProtectionProvider.Create(Path.Combine(_tempRoot, "install-linking-keys")),
            NullLogger<InstallLinkingStore>.Instance);
        var participateStore = new PublicParticipateSnapshotStore(configuration);
        var participateService = new PublicParticipateSnapshotService(
            participateStore,
            configuration,
            httpClientFactory,
            environment,
            NullLogger<PublicParticipateSnapshotService>.Instance);
        var services = new ServiceCollection();
        services.AddSingleton(configuration);
        services.AddSingleton(environment);
        services.AddSingleton(landing);
        services.AddSingleton(navigation);
        services.AddSingleton(releaseManifest);
        services.AddSingleton(billingStore);
        services.AddSingleton(usageStore);
        services.AddSingleton(installLinkingStore);
        services.AddSingleton<IInstallLinkingStoreReadinessProbe>(
            installLinkingStoreProbe ?? new ReadyInstallLinkingStoreProbe());
        services.AddSingleton(participateStore);
        services.AddSingleton(participateService);
        return services.BuildServiceProvider();
    }

    private sealed class ReadyInstallLinkingStoreProbe : IInstallLinkingStoreReadinessProbe
    {
        public InstallLinkingStoreReadiness Evaluate() => new(true, "store_activated");
    }

    private sealed class BlockingInstallLinkingStoreProbe : IInstallLinkingStoreReadinessProbe
    {
        public TaskCompletionSource<bool> EvaluationStarted { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource<bool> AllowEvaluation { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public InstallLinkingStoreReadiness Evaluate()
        {
            EvaluationStarted.TrySetResult(true);
            AllowEvaluation.Task.GetAwaiter().GetResult();
            return new InstallLinkingStoreReadiness(true, "store_activated");
        }
    }

    private sealed class FakeWebHostEnvironment(string environmentName) : IWebHostEnvironment
    {
        public string EnvironmentName { get; set; } = environmentName;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string WebRootPath { get; set; } = RepoPaths.Root;
        public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
        public string ContentRootPath { get; set; } = RepoPaths.Root;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private sealed class BlockingParticipateHttpClientFactory : IHttpClientFactory
    {
        public TaskCompletionSource<bool> RequestStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public ManualResetEventSlim AllowResponse { get; } = new(initialState: false);
        public TaskCompletionSource<bool> RequestCompleted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public HttpClient CreateClient(string name)
            => new(new BlockingParticipateHandler(this));

        private sealed class BlockingParticipateHandler(BlockingParticipateHttpClientFactory owner) : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                owner.RequestStarted.TrySetResult(true);
                try
                {
                    owner.AllowResponse.Wait(cancellationToken);
                    return Task.FromResult(
                        new HttpResponseMessage(HttpStatusCode.OK)
                        {
                            Content = new StringContent("{\"data\":[],\"total\":0}", Encoding.UTF8, "application/json")
                        });
                }
                finally
                {
                    owner.RequestCompleted.TrySetResult(true);
                }
            }
        }
    }
}
