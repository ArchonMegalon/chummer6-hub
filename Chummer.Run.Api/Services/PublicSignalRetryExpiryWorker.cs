using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api.Services;

public sealed class PublicSignalRetryExpiryWorker : BackgroundService
{
    private static readonly TimeSpan DefaultInitialDelay = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan DefaultInterval = TimeSpan.FromMinutes(2);

    private readonly PublicSignalOperationsService _signalOperations;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicSignalRetryExpiryWorker> _logger;

    public PublicSignalRetryExpiryWorker(
        PublicSignalOperationsService signalOperations,
        IConfiguration configuration,
        ILogger<PublicSignalRetryExpiryWorker> logger)
    {
        _signalOperations = signalOperations;
        _configuration = configuration;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!IsEnabled())
        {
            return;
        }

        TimeSpan initialDelay = ResolveDurationSeconds("CHUMMER_PRODUCTLIFT_RETRY_EXPIRY_RECOVERY_INITIAL_DELAY_SECONDS", DefaultInitialDelay);
        TimeSpan interval = ResolveDurationSeconds("CHUMMER_PRODUCTLIFT_RETRY_EXPIRY_RECOVERY_INTERVAL_SECONDS", DefaultInterval);

        if (initialDelay > TimeSpan.Zero)
        {
            await Task.Delay(initialDelay, stoppingToken);
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                PublicSignalOperationsRecoveryResponse result = _signalOperations.RecoverExpiredRetryWindows();
                if (!string.Equals(result.Status, "noop", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogInformation(
                        "ProductLift retry expiry sweep ended in {Status} with {RecoveredCount} recovered, {SuppressedCount} suppressed, and {BlockedCount} blocked candidate(s).",
                        result.Status,
                        result.RecoveredReceiptCount,
                        result.SuppressedReceiptCount,
                        result.BlockedReceiptCount);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "ProductLift retry expiry sweep failed.");
            }

            await Task.Delay(interval, stoppingToken);
        }
    }

    private bool IsEnabled()
        => ParseBool(_configuration["CHUMMER_PRODUCTLIFT_RETRY_EXPIRY_RECOVERY_ENABLED"], defaultValue: true);

    private TimeSpan ResolveDurationSeconds(string key, TimeSpan fallback)
    {
        string? raw = Normalize(_configuration[key]);
        return int.TryParse(raw, out int seconds) && seconds >= 0
            ? TimeSpan.FromSeconds(seconds)
            : fallback;
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static bool ParseBool(string? value, bool defaultValue)
    {
        string? normalized = Normalize(value);
        return normalized is null ? defaultValue : bool.TryParse(normalized, out bool parsed) ? parsed : defaultValue;
    }
}
