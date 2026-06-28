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

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        try
        {
            _services.GetRequiredService<BrilliantDirectoriesBillingStore>();
            _services.GetRequiredService<MyFirstBookUsageStore>();
            _services.GetRequiredService<InstallLinkingStore>();
            _services.GetRequiredService<PublicLandingService>().LoadSurface();
            _services.GetRequiredService<PublicNavigationService>().LoadNavigation();
            _services.GetRequiredService<PublicReleaseManifestService>().LoadManifest();
            using CancellationTokenSource timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeoutCts.CancelAfter(TimeSpan.FromSeconds(3));
            await _services.GetRequiredService<PublicParticipateSnapshotService>().RefreshAsync(timeoutCts.Token).ConfigureAwait(false);
            _logger.LogInformation("Public surface warmup completed.");
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Public surface warmup failed; the first request may pay the initialization cost.");
        }
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        return Task.CompletedTask;
    }
}
