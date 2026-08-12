namespace Chummer.Run.Api.Services;

public sealed class AccountErasureRecoveryWorker : BackgroundService
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromMinutes(1);
    private readonly AccountErasureJournalStore _journal;
    private readonly AccountErasureService _erasure;
    private readonly TimeProvider _timeProvider;
    private readonly ILogger<AccountErasureRecoveryWorker> _logger;

    public AccountErasureRecoveryWorker(
        AccountErasureJournalStore journal,
        AccountErasureService erasure,
        TimeProvider timeProvider,
        ILogger<AccountErasureRecoveryWorker> logger)
    {
        _journal = journal;
        _erasure = erasure;
        _timeProvider = timeProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            DateTimeOffset now = _timeProvider.GetUtcNow();
            IReadOnlyList<PendingIdentityAccountErasure> pending;
            try
            {
                pending = _journal.GetPendingIdentityDue(now);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Account-erasure recovery journal could not be read.");
                pending = [];
            }

            foreach (PendingIdentityAccountErasure operation in pending)
            {
                try
                {
                    await _erasure.RecoverPendingIdentityAsync(operation, stoppingToken);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    return;
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(
                        ex,
                        "Pending Identity erasure recovery remains queued for subject key {SubjectKey}.",
                        operation.Entry.SubjectKeySha256);
                    _journal.DelayIdentityRecovery(operation.Entry.SubjectKeySha256, _timeProvider.GetUtcNow());
                }
            }

            _journal.PruneExpired(_timeProvider.GetUtcNow());
            await Task.Delay(PollInterval, _timeProvider, stoppingToken);
        }
    }
}
