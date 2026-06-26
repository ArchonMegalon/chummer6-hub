using Chummer.Run.Contracts.Billing;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactQuotaService
{
    private readonly HorizonArtifactUsageStore _store;
    private readonly HorizonCapabilityService _capabilities;
    private readonly BrilliantDirectoriesBillingService _billing;

    public HorizonArtifactQuotaService(
        HorizonArtifactUsageStore store,
        HorizonCapabilityService capabilities,
        BrilliantDirectoriesBillingService billing)
    {
        _store = store;
        _capabilities = capabilities;
        _billing = billing;
    }

    public HorizonArtifactQuotaSnapshot GetQuota(
        HorizonArtifactQuotaRequest request,
        DateTimeOffset? now = null)
    {
        ArgumentNullException.ThrowIfNull(request);

        string userId = RequireValue(request.UserId, "A user id is required before checking artifact allowance.");
        HorizonCapabilityDefinition capability = _capabilities.GetCapability(request.HorizonId, request.ArtifactKindOrCapabilityId);
        DateTimeOffset effectiveNow = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        ResolvedQuotaWindow quota = ResolveQuotaWindow(userId, capability, effectiveNow, request.Email);
        return BuildSnapshot(userId, capability, quota);
    }

    public HorizonArtifactQuotaSnapshot Consume(
        HorizonArtifactQuotaRequest request,
        DateTimeOffset? now = null)
    {
        ArgumentNullException.ThrowIfNull(request);

        string userId = RequireValue(request.UserId, "A user id is required before consuming artifact allowance.");
        HorizonCapabilityDefinition capability = _capabilities.GetCapability(request.HorizonId, request.ArtifactKindOrCapabilityId);
        if (!capability.Enabled)
        {
            throw new InvalidOperationException("This horizon artifact capability is not enabled.");
        }

        DateTimeOffset effectiveNow = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        int unitsRequested = RequirePositiveUnits(request.UnitsRequested);
        if (string.Equals(capability.QuotaAuthority, "myfirstbook_monthly", StringComparison.OrdinalIgnoreCase))
        {
            HorizonArtifactQuotaSnapshot available = GetQuota(request, effectiveNow);
            if (available.WindowRemaining < unitsRequested)
            {
                throw new InvalidOperationException($"{capability.PublicLabel} allowance is exhausted for this {available.WindowKind}.");
            }

            MyFirstBookQuotaConsumeResultDto? consumed = null;
            for (int index = 0; index < unitsRequested; index += 1)
            {
                consumed = _billing.ConsumeMyFirstBookQuota(userId, effectiveNow, request.Email);
            }

            MyFirstBookQuotaSnapshotDto quota = consumed?.Quota ?? _billing.GetMyFirstBookQuota(userId, effectiveNow, request.Email);
            return BuildSnapshot(
                userId,
                capability,
                new ResolvedQuotaWindow(
                    quota.SupporterActive,
                    quota.MonthlyLimit,
                    quota.MonthlyUsed,
                    quota.WindowStartUtc,
                    quota.WindowEndUtc,
                    capability.AllowanceWindowKind));
        }

        DateTimeOffset weekStartUtc = GetWeekStartUtc(effectiveNow);

        lock (_store.Gate)
        {
            int existingIndex = _store.Entries.FindIndex(item => Matches(item, userId, capability, weekStartUtc));
            int weeklyUsed = existingIndex >= 0 ? _store.Entries[existingIndex].Used : 0;
            int weeklyLimit = ResolveWeeklyLimit(userId, capability, effectiveNow, request.Email, out bool supporterActive);
            if (weeklyUsed + unitsRequested > weeklyLimit)
            {
                throw new InvalidOperationException($"{capability.PublicLabel} allowance is exhausted for this week.");
            }

            HorizonArtifactUsageLedgerEntry updated = existingIndex >= 0
                ? _store.Entries[existingIndex] with
                {
                    Used = _store.Entries[existingIndex].Used + unitsRequested,
                    UpdatedAtUtc = effectiveNow
                }
                : new HorizonArtifactUsageLedgerEntry(
                    userId,
                    capability.HorizonId,
                    capability.CapabilityId,
                    capability.ArtifactKind,
                    "weekly",
                    weekStartUtc,
                    unitsRequested,
                    effectiveNow);

            if (existingIndex >= 0)
            {
                _store.Entries[existingIndex] = updated;
            }
            else
            {
                _store.Entries.Add(updated);
            }

            _store.PersistLocked();
            return BuildSnapshot(
                userId,
                capability,
                new ResolvedQuotaWindow(
                    supporterActive,
                    weeklyLimit,
                    updated.Used,
                    weekStartUtc,
                    weekStartUtc.AddDays(7),
                    capability.AllowanceWindowKind));
        }
    }

    public IReadOnlyList<HorizonArtifactQuotaSnapshot> ListQuotas(
        HorizonArtifactQuotaCatalogRequest request,
        DateTimeOffset? now = null)
    {
        ArgumentNullException.ThrowIfNull(request);

        string userId = RequireValue(request.UserId, "A user id is required before checking artifact allowance.");
        string? normalizedHorizonId = CleanOrNull(request.HorizonId);
        string? normalizedSelector = CleanOrNull(request.ArtifactKindOrCapabilityId);
        DateTimeOffset effectiveNow = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();

        HorizonCapabilityDefinition[] capabilities = _capabilities.ListCapabilities()
            .Where(capability =>
                (normalizedHorizonId is null || string.Equals(capability.HorizonId, normalizedHorizonId, StringComparison.OrdinalIgnoreCase))
                && (normalizedSelector is null
                    || string.Equals(capability.ArtifactKind, normalizedSelector, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(capability.CapabilityId, normalizedSelector, StringComparison.OrdinalIgnoreCase))
                && capability.QuotaTracked
                && (!request.PublicVisibleOnly || capability.PublicVisible))
            .OrderBy(capability => capability.HorizonId, StringComparer.OrdinalIgnoreCase)
            .ThenBy(capability => capability.CapabilityId, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return capabilities
            .Select(capability => BuildSnapshot(
                userId,
                capability,
                ResolveQuotaWindow(userId, capability, effectiveNow, request.Email)))
            .ToArray();
    }

    private static HorizonArtifactQuotaSnapshot BuildSnapshot(
        string userId,
        HorizonCapabilityDefinition capability,
        ResolvedQuotaWindow quota)
    {
        string allowanceTier = quota.SupporterActive ? "supporter" : "free";
        return new(
            userId,
            capability.HorizonId,
            capability.CapabilityId,
            capability.ArtifactKind,
            capability.PublicLabel,
            quota.SupporterActive,
            allowanceTier,
            $"{allowanceTier}_{capability.EntitlementBasisSuffix}",
            capability.EntitlementScope,
            quota.Limit,
            quota.Used,
            Math.Max(0, quota.Limit - quota.Used),
            quota.WindowStartUtc,
            quota.WindowEndUtc)
        {
            WindowKind = quota.WindowKind
        };
    }

    private ResolvedQuotaWindow ResolveQuotaWindow(
        string userId,
        HorizonCapabilityDefinition capability,
        DateTimeOffset effectiveNow,
        string? email)
    {
        if (string.Equals(capability.QuotaAuthority, "myfirstbook_monthly", StringComparison.OrdinalIgnoreCase))
        {
            MyFirstBookQuotaSnapshotDto quota = _billing.GetMyFirstBookQuota(userId, effectiveNow, email);
            return new ResolvedQuotaWindow(
                quota.SupporterActive,
                quota.MonthlyLimit,
                quota.MonthlyUsed,
                quota.WindowStartUtc,
                quota.WindowEndUtc,
                capability.AllowanceWindowKind);
        }

        DateTimeOffset weekStartUtc = GetWeekStartUtc(effectiveNow);
        int weeklyLimit = ResolveWeeklyLimit(userId, capability, effectiveNow, email, out bool supporterActive);
        int weeklyUsed;
        lock (_store.Gate)
        {
            weeklyUsed = _store.Entries.FirstOrDefault(item => Matches(item, userId, capability, weekStartUtc))
                is HorizonArtifactUsageLedgerEntry entry
                ? entry.Used
                : 0;
        }

        return new ResolvedQuotaWindow(
            supporterActive,
            weeklyLimit,
            weeklyUsed,
            weekStartUtc,
            weekStartUtc.AddDays(7),
            capability.AllowanceWindowKind);
    }

    private int ResolveWeeklyLimit(
        string userId,
        HorizonCapabilityDefinition capability,
        DateTimeOffset effectiveNow,
        string? email,
        out bool supporterActive)
    {
        supporterActive = _billing.GetMyFirstBookQuota(userId, effectiveNow, email).SupporterActive;
        return supporterActive ? capability.SupporterWeeklyLimit : capability.FreeWeeklyLimit;
    }

    private static bool Matches(
        HorizonArtifactUsageLedgerEntry item,
        string userId,
        HorizonCapabilityDefinition capability,
        DateTimeOffset weekStartUtc)
        => string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.HorizonId, capability.HorizonId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.CapabilityId, capability.CapabilityId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.ArtifactKind, capability.ArtifactKind, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.WindowKind, "weekly", StringComparison.OrdinalIgnoreCase)
            && item.WindowStartUtc == weekStartUtc;

    private static DateTimeOffset GetWeekStartUtc(DateTimeOffset now)
    {
        DateTimeOffset utc = new(now.UtcDateTime.Date.Ticks, TimeSpan.Zero);
        int offset = ((int)utc.DayOfWeek - (int)DayOfWeek.Monday + 7) % 7;
        return utc.AddDays(-offset);
    }

    private static int RequirePositiveUnits(int unitsRequested)
        => unitsRequested > 0
            ? unitsRequested
            : throw new InvalidOperationException("A positive artifact allowance unit count is required.");

    private static string RequireValue(string value, string message)
        => string.IsNullOrWhiteSpace(value) ? throw new InvalidOperationException(message) : value.Trim();

    private static string? CleanOrNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}

public sealed record HorizonArtifactQuotaRequest(
    string UserId,
    string HorizonId,
    string ArtifactKindOrCapabilityId,
    string? Email = null,
    int UnitsRequested = 1);

public sealed record HorizonArtifactQuotaCatalogRequest(
    string UserId,
    string? HorizonId = null,
    string? ArtifactKindOrCapabilityId = null,
    string? Email = null,
    bool PublicVisibleOnly = false);

public sealed record HorizonArtifactQuotaCatalog(
    string UserId,
    string? HorizonId,
    string? ArtifactKindOrCapabilityId,
    bool PublicVisibleOnly,
    IReadOnlyList<HorizonArtifactQuotaSnapshot> Quotas);

public sealed record HorizonArtifactQuotaSnapshot(
    string UserId,
    string HorizonId,
    string CapabilityId,
    string ArtifactKind,
    string PublicLabel,
    bool SupporterActive,
    string AllowanceTier,
    string EntitlementBasis,
    string EntitlementScope,
    int WeeklyLimit,
    int WeeklyUsed,
    int WeeklyRemaining,
    DateTimeOffset WindowStartUtc,
    DateTimeOffset WindowEndUtc)
{
    public string WindowKind { get; init; } = "weekly";

    public int WindowLimit => WeeklyLimit;

    public int WindowUsed => WeeklyUsed;

    public int WindowRemaining => WeeklyRemaining;
}

internal sealed record ResolvedQuotaWindow(
    bool SupporterActive,
    int Limit,
    int Used,
    DateTimeOffset WindowStartUtc,
    DateTimeOffset WindowEndUtc,
    string WindowKind);
