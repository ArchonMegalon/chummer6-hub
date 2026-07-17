namespace Chummer.Run.Api.Services;

/// <summary>
/// Completes the controlled first release-shelf activation before publication
/// readiness is evaluated. Normal restarts are a no-op unless an interrupted
/// activation journal needs deterministic reconciliation.
/// </summary>
public sealed class ReleaseShelfInitialMigrationHostedService : IHostedService
{
    private readonly ReleaseBundlePromotionService _promotion;
    private readonly ILogger<ReleaseShelfInitialMigrationHostedService> _logger;

    public ReleaseShelfInitialMigrationHostedService(
        ReleaseBundlePromotionService promotion,
        ILogger<ReleaseShelfInitialMigrationHostedService> logger)
    {
        _promotion = promotion;
        _logger = logger;
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        ReleaseBundlePromotionResult? result =
            await _promotion.EnsureInitialLegacyMigrationAsync(cancellationToken);
        if (result is null)
        {
            return;
        }

        _logger.LogInformation(
            "Release shelf initial migration activated generation {GenerationId} for {Version} with receipt {ActivationReceiptId}.",
            result.GenerationId,
            result.Version,
            result.ActivationReceiptId);
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
