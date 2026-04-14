using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api.Services.Community;

public sealed class TeableUserProjectionSyncWorker : BackgroundService
{
    private static readonly TimeSpan DefaultInitialDelay = TimeSpan.FromSeconds(15);
    private static readonly TimeSpan DefaultInterval = TimeSpan.FromMinutes(30);

    private readonly TeableUserProjectionService _teableUsers;
    private readonly IConfiguration _configuration;
    private readonly ILogger<TeableUserProjectionSyncWorker> _logger;

    public TeableUserProjectionSyncWorker(
        TeableUserProjectionService teableUsers,
        IConfiguration configuration,
        ILogger<TeableUserProjectionSyncWorker> logger)
    {
        _teableUsers = teableUsers;
        _configuration = configuration;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!IsEnabled())
        {
            return;
        }

        TimeSpan initialDelay = ResolveDurationSeconds("CHUMMER_TEABLE_USERS_RECONCILE_INITIAL_DELAY_SECONDS", DefaultInitialDelay);
        TimeSpan interval = ResolveDurationMinutes("CHUMMER_TEABLE_USERS_RECONCILE_INTERVAL_MINUTES", DefaultInterval);

        if (initialDelay > TimeSpan.Zero)
        {
            await Task.Delay(initialDelay, stoppingToken);
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                TeableUserProjectionSyncResult result = await _teableUsers.SyncAllAsync(stoppingToken);
                if (string.Equals(result.State, "passed", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogInformation(
                        "Teable user reconciliation synced {SyncedCount}/{AttemptedCount} hub users into {TableId}.",
                        result.SyncedCount,
                        result.AttemptedCount,
                        result.TableId ?? "(unresolved)");
                }
                else if (!string.Equals(result.State, "disabled", StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(result.State, "unconfigured", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogWarning(
                        "Teable user reconciliation ended in {State} with {FailedCount} failed rows: {Errors}",
                        result.State,
                        result.FailedCount,
                        string.Join(" | ", result.Errors.Take(4)));
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Teable user reconciliation loop failed.");
            }

            await Task.Delay(interval, stoppingToken);
        }
    }

    private bool IsEnabled()
        => ParseBool(_configuration["CHUMMER_TEABLE_USERS_RECONCILE_ENABLED"], defaultValue: true);

    private TimeSpan ResolveDurationMinutes(string key, TimeSpan fallback)
    {
        string? raw = Normalize(_configuration[key]);
        return int.TryParse(raw, out int minutes) && minutes > 0
            ? TimeSpan.FromMinutes(minutes)
            : fallback;
    }

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
