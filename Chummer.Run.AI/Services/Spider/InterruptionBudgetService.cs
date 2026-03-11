
namespace Chummer.Run.AI.Services.Spider;

public sealed record InterruptionBudgetProfile(
    string SessionId,
    int LimitPerMinute,
    int UsedThisMinute,
    DateTimeOffset WindowStartUtc,
    int RemainingThisMinute,
    bool Allowed);

public interface IInterruptionBudgetService
{
    InterruptionBudgetProfile Evaluate(string sessionId, InterruptionLevel level, DateTimeOffset nowUtc);
    InterruptionBudgetProfile Peek(string sessionId, InterruptionLevel level, DateTimeOffset nowUtc);
}

public sealed class InterruptionBudgetService : IInterruptionBudgetService
{
    private sealed class SessionBudgetWindow
    {
        public int LimitPerMinute;
        public int UsedThisMinute;
        public DateTimeOffset WindowStartUtc;
    }

    private readonly Dictionary<string, SessionBudgetWindow> _windows = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _guard = new();

    public InterruptionBudgetProfile Evaluate(string sessionId, InterruptionLevel level, DateTimeOffset nowUtc)
    {
        var limit = MaxPerMinute(level);
        if (limit <= 0)
        {
            return new InterruptionBudgetProfile(sessionId, 0, 0, nowUtc, 0, false);
        }

        lock (_guard)
        {
            if (!_windows.TryGetValue(sessionId, out var window))
            {
                window = new SessionBudgetWindow
                {
                    LimitPerMinute = limit,
                    WindowStartUtc = nowUtc,
                    UsedThisMinute = 0
                };
                _windows[sessionId] = window;
            }

            if ((nowUtc - window.WindowStartUtc).TotalMinutes >= 1)
            {
                window.WindowStartUtc = nowUtc;
                window.UsedThisMinute = 0;
                window.LimitPerMinute = limit;
            }

            if (window.LimitPerMinute != limit)
            {
                window.LimitPerMinute = limit;
            }

            var remaining = Math.Max(0, limit - window.UsedThisMinute);
            if (remaining <= 0)
            {
                return new InterruptionBudgetProfile(
                    sessionId,
                    limit,
                    window.UsedThisMinute,
                    window.WindowStartUtc,
                    0,
                    false);
            }

            window.UsedThisMinute++;
            return new InterruptionBudgetProfile(
                sessionId,
                limit,
                window.UsedThisMinute,
                window.WindowStartUtc,
                Math.Max(0, limit - window.UsedThisMinute),
                true);
        }
    }

    public InterruptionBudgetProfile Peek(string sessionId, InterruptionLevel level, DateTimeOffset nowUtc)
    {
        var limit = MaxPerMinute(level);
        if (limit <= 0)
        {
            return new InterruptionBudgetProfile(sessionId, 0, 0, nowUtc, 0, false);
        }

        lock (_guard)
        {
            if (!_windows.TryGetValue(sessionId, out var window))
            {
                window = new SessionBudgetWindow
                {
                    LimitPerMinute = limit,
                    WindowStartUtc = nowUtc,
                    UsedThisMinute = 0
                };
                _windows[sessionId] = window;
            }

            if ((nowUtc - window.WindowStartUtc).TotalMinutes >= 1)
            {
                return new InterruptionBudgetProfile(
                    sessionId,
                    limit,
                    0,
                    nowUtc,
                    limit,
                    limit > 0);
            }

            if (window.LimitPerMinute != limit)
            {
                window.LimitPerMinute = limit;
            }

            var remaining = Math.Max(0, limit - window.UsedThisMinute);
            return new InterruptionBudgetProfile(
                sessionId,
                limit,
                window.UsedThisMinute,
                window.WindowStartUtc,
                remaining,
                remaining > 0);
        }
    }

    private static int MaxPerMinute(InterruptionLevel level) =>
        level switch
        {
            InterruptionLevel.Low => 3,
            InterruptionLevel.Tactical => 2,
            InterruptionLevel.Narrative => 1,
            InterruptionLevel.High => 1,
            _ => 0
        };
}
