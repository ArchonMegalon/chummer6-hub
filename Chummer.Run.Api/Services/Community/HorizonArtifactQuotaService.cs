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
        DateTimeOffset weekStartUtc = GetWeekStartUtc(effectiveNow);
        DateTimeOffset weekEndUtc = weekStartUtc.AddDays(7);
        bool supporterActive = _billing.GetMyFirstBookQuota(userId, effectiveNow, request.Email).SupporterActive;
        int weeklyLimit = supporterActive ? capability.SupporterWeeklyLimit : capability.FreeWeeklyLimit;

        int weeklyUsed;
        lock (_store.Gate)
        {
            weeklyUsed = _store.Entries.FirstOrDefault(item => Matches(item, userId, capability, weekStartUtc))
                is HorizonArtifactUsageLedgerEntry entry
                ? entry.Used
                : 0;
        }

        return BuildSnapshot(userId, capability, supporterActive, weeklyLimit, weeklyUsed, weekStartUtc, weekEndUtc);
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
        DateTimeOffset weekStartUtc = GetWeekStartUtc(effectiveNow);
        DateTimeOffset weekEndUtc = weekStartUtc.AddDays(7);
        bool supporterActive = _billing.GetMyFirstBookQuota(userId, effectiveNow, request.Email).SupporterActive;
        int weeklyLimit = supporterActive ? capability.SupporterWeeklyLimit : capability.FreeWeeklyLimit;

        lock (_store.Gate)
        {
            int existingIndex = _store.Entries.FindIndex(item => Matches(item, userId, capability, weekStartUtc));
            int weeklyUsed = existingIndex >= 0 ? _store.Entries[existingIndex].Used : 0;
            if (weeklyUsed >= weeklyLimit)
            {
                throw new InvalidOperationException($"{capability.PublicLabel} allowance is exhausted for this week.");
            }

            HorizonArtifactUsageLedgerEntry updated = existingIndex >= 0
                ? _store.Entries[existingIndex] with
                {
                    Used = _store.Entries[existingIndex].Used + 1,
                    UpdatedAtUtc = effectiveNow
                }
                : new HorizonArtifactUsageLedgerEntry(
                    userId,
                    capability.HorizonId,
                    capability.CapabilityId,
                    capability.ArtifactKind,
                    "weekly",
                    weekStartUtc,
                    1,
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
            return BuildSnapshot(userId, capability, supporterActive, weeklyLimit, updated.Used, weekStartUtc, weekEndUtc);
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
        DateTimeOffset weekStartUtc = GetWeekStartUtc(effectiveNow);
        DateTimeOffset weekEndUtc = weekStartUtc.AddDays(7);
        bool supporterActive = _billing.GetMyFirstBookQuota(userId, effectiveNow, request.Email).SupporterActive;

        HorizonCapabilityDefinition[] capabilities = _capabilities.ListCapabilities()
            .Where(capability =>
                (normalizedHorizonId is null || string.Equals(capability.HorizonId, normalizedHorizonId, StringComparison.OrdinalIgnoreCase))
                && (normalizedSelector is null
                    || string.Equals(capability.ArtifactKind, normalizedSelector, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(capability.CapabilityId, normalizedSelector, StringComparison.OrdinalIgnoreCase))
                && (!request.PublicVisibleOnly || capability.PublicVisible))
            .OrderBy(capability => capability.HorizonId, StringComparer.OrdinalIgnoreCase)
            .ThenBy(capability => capability.CapabilityId, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        lock (_store.Gate)
        {
            return capabilities
                .Select(capability =>
                {
                    int weeklyLimit = supporterActive ? capability.SupporterWeeklyLimit : capability.FreeWeeklyLimit;
                    int weeklyUsed = _store.Entries.FirstOrDefault(item => Matches(item, userId, capability, weekStartUtc))
                        is HorizonArtifactUsageLedgerEntry entry
                        ? entry.Used
                        : 0;
                    return BuildSnapshot(userId, capability, supporterActive, weeklyLimit, weeklyUsed, weekStartUtc, weekEndUtc);
                })
                .ToArray();
        }
    }

    private static HorizonArtifactQuotaSnapshot BuildSnapshot(
        string userId,
        HorizonCapabilityDefinition capability,
        bool supporterActive,
        int weeklyLimit,
        int weeklyUsed,
        DateTimeOffset weekStartUtc,
        DateTimeOffset weekEndUtc)
    {
        string allowanceTier = supporterActive ? "supporter" : "free";
        return new(
            userId,
            capability.HorizonId,
            capability.CapabilityId,
            capability.ArtifactKind,
            capability.PublicLabel,
            supporterActive,
            allowanceTier,
            $"{allowanceTier}_weekly_allowance",
            "account",
            weeklyLimit,
            weeklyUsed,
            Math.Max(0, weeklyLimit - weeklyUsed),
            weekStartUtc,
            weekEndUtc);
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

    private static string RequireValue(string value, string message)
        => string.IsNullOrWhiteSpace(value) ? throw new InvalidOperationException(message) : value.Trim();

    private static string? CleanOrNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}

public sealed record HorizonArtifactQuotaRequest(
    string UserId,
    string HorizonId,
    string ArtifactKindOrCapabilityId,
    string? Email = null);

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
    DateTimeOffset WindowEndUtc);
