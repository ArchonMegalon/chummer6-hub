using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api.Services;

public sealed class PublicSurfaceWarmupService : IHostedService
{
    private readonly IServiceProvider _services;
    private readonly ILogger<PublicSurfaceWarmupService> _logger;

    public PublicSurfaceWarmupService(IServiceProvider services, ILogger<PublicSurfaceWarmupService> logger)
    {
        _services = services;
        _logger = logger;
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        _ = Task.Run(WarmPublicSurface, CancellationToken.None);
        return Task.CompletedTask;
    }

    private void WarmPublicSurface()
    {
        WarmComponent(
            "participate_snapshot",
            () => _services.GetRequiredService<PublicParticipateSnapshotService>().QueueRefreshIfDue());
        WarmComponent(
            "billing_store",
            () => _services.GetRequiredService<BrilliantDirectoriesBillingStore>());
        WarmComponent(
            "usage_store",
            () => _services.GetRequiredService<MyFirstBookUsageStore>());
        WarmComponent("install_linking", () =>
        {
            InstallLinkingStoreReadiness installLinking = _services
                .GetRequiredService<IInstallLinkingStoreReadinessProbe>()
                .Evaluate();
            if (!installLinking.Ready)
            {
                _logger.LogError(
                    "Install-linking durable store warmup is blocked with code {ReadinessCode}.",
                    installLinking.Code);
            }
        });
        WarmComponent(
            "landing",
            () => _services.GetRequiredService<PublicLandingService>().LoadSurface());
        WarmComponent(
            "navigation",
            () => _services.GetRequiredService<PublicNavigationService>().LoadNavigation());
        WarmComponent(
            "release_manifest",
            () => _services.GetRequiredService<PublicReleaseManifestService>().LoadManifest());
        _logger.LogInformation("Public surface warmup completed.");
    }

    private void WarmComponent(string component, Action action)
    {
        try
        {
            action();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(
                ex,
                "Public surface warmup component {WarmupComponent} failed; its first request may pay the initialization cost.",
                component);
        }
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        return Task.CompletedTask;
    }
}
