using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Gateway;

public interface IAiBudgetService
{
    BudgetCheckResult Check(BudgetCheckRequest request);
    BudgetCheckResult Preview(BudgetCheckRequest request);
    IReadOnlyList<GatewayBudgetStatus> AllStatuses();
    IReadOnlyList<GatewayBudgetStatus> StatusesForSession(string sessionId);
}

public sealed class AiBudgetService : IAiBudgetService
{
    private sealed class BudgetLedger
    {
        public DateTimeOffset MonthWindowStartUtc { get; set; } = RoundToMonth(DateTimeOffset.UtcNow);
        public DateTimeOffset MinuteWindowStartUtc { get; set; } = DateTimeOffset.UtcNow;
        public int MonthlyUsed { get; set; }
        public int BurstUsedThisMinute { get; set; }
    }

    private readonly ConcurrentDictionary<string, BudgetLedger> _ledgers = new();
    private readonly int _monthlyAllowance;
    private readonly int _burstAllowance;

    public AiBudgetService(IConfiguration configuration)
    {
        _monthlyAllowance = configuration.GetValue("AiGateway:MonthlyAllowance", 240);
        _burstAllowance = configuration.GetValue("AiGateway:BurstAllowancePerMinute", 40);
    }

    public BudgetCheckResult Check(BudgetCheckRequest request)
    {
        return Evaluate(request, consume: true);
    }

    public BudgetCheckResult Preview(BudgetCheckRequest request)
    {
        return Evaluate(request, consume: false);
    }

    public IReadOnlyList<GatewayBudgetStatus> StatusesForSession(string sessionId) =>
        _ledgers
            .Where(pair => pair.Key.StartsWith($"{sessionId}:", StringComparison.Ordinal))
            .Select(pair => BuildStatus(sessionId, pair.Key, pair.Value))
            .ToList();

    public IReadOnlyList<GatewayBudgetStatus> AllStatuses() =>
        _ledgers
            .Select(pair =>
            {
                var sessionId = pair.Key.Split(':', 2, StringSplitOptions.None)[0];
                return BuildStatus(sessionId, pair.Key, pair.Value);
            })
            .ToList();

    private BudgetCheckResult Evaluate(BudgetCheckRequest request, bool consume)
    {
        if (string.IsNullOrWhiteSpace(request.SessionId))
        {
            return new BudgetCheckResult(false, "sessionId is required");
        }

        var estimatedCost = Math.Max(1, request.EstimatedTokens / 512);
        var key = BuildKey(request.SessionId, request.Provider);
        var ledger = _ledgers.AddOrUpdate(
            key,
            _ => new BudgetLedger(),
            (_, existing) => existing);

        lock (ledger)
        {
            var now = DateTimeOffset.UtcNow;
            ResetIfNeeded(ledger, now);

            if (ledger.MonthlyUsed + estimatedCost > _monthlyAllowance)
            {
                return new BudgetCheckResult(false, "monthly route budget exceeded");
            }

            if (ledger.BurstUsedThisMinute + estimatedCost > _burstAllowance)
            {
                return new BudgetCheckResult(false, "burst rate budget exceeded");
            }

            if (consume)
            {
                ledger.MonthlyUsed += estimatedCost;
                ledger.BurstUsedThisMinute += estimatedCost;
            }

            return new BudgetCheckResult(true, null);
        }
    }

    private static string BuildKey(string sessionId, AiProvider provider) => $"{sessionId}:{provider}";

    private GatewayBudgetStatus BuildStatus(string sessionId, string key, BudgetLedger ledger)
    {
        lock (ledger)
        {
            var parts = key.Split(':', 2, StringSplitOptions.None);
            var provider = parts.Length == 2 && Enum.TryParse<AiProvider>(parts[1], out var parsed)
                ? parsed
                : AiProvider.AiMagicx;
            return new GatewayBudgetStatus(
                RouteType: "route",
                SessionId: sessionId,
                MonthlyAllowance: _monthlyAllowance,
                MonthlyUsed: ledger.MonthlyUsed,
                BurstAllowancePerMinute: _burstAllowance,
                BurstUsedThisMinute: ledger.BurstUsedThisMinute,
                OverMonthly: ledger.MonthlyUsed >= _monthlyAllowance,
                OverBurst: ledger.BurstUsedThisMinute >= _burstAllowance);
        }
    }

    private static void ResetIfNeeded(BudgetLedger ledger, DateTimeOffset now)
    {
        var currentMonth = RoundToMonth(now);
        if (ledger.MonthWindowStartUtc != currentMonth)
        {
            ledger.MonthWindowStartUtc = currentMonth;
            ledger.MonthlyUsed = 0;
            ledger.BurstUsedThisMinute = 0;
            ledger.MinuteWindowStartUtc = now;
            return;
        }

        if (now - ledger.MinuteWindowStartUtc > TimeSpan.FromMinutes(1))
        {
            ledger.MinuteWindowStartUtc = now;
            ledger.BurstUsedThisMinute = 0;
        }
    }

    private static DateTimeOffset RoundToMonth(DateTimeOffset value) =>
        new DateTimeOffset(value.Year, value.Month, 1, 0, 0, 0, value.Offset);
}
