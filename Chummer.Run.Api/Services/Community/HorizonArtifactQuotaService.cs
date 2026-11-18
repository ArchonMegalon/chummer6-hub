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
        => Consume(request, now, null);

    internal HorizonArtifactQuotaSnapshot Consume(HorizonArtifactQuotaRequest request,
        DateTimeOffset? now, HorizonArtifactRequestReceipt? requestReceipt)
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
            if (requestReceipt is null && available.WindowRemaining < unitsRequested)
            {
                throw new InvalidOperationException($"{capability.PublicLabel} allowance is exhausted for this {available.WindowKind}.");
            }

            // One requested batch is one allowance commit, never a partially
            // charged loop if another instance consumes a slot between writes.
            MyFirstBookQuotaSnapshotDto quota = _billing.ConsumeMyFirstBookQuota(
                userId, effectiveNow, request.Email, unitsRequested, requestReceipt is null ? null : quota => requestReceipt with
                {
                    Quota = BuildSnapshot(userId, capability, new ResolvedQuotaWindow(quota.SupporterActive,
                        quota.MonthlyLimit, quota.MonthlyUsed, quota.WindowStartUtc, quota.WindowEndUtc, capability.AllowanceWindowKind))
                }).Quota;
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

        using (_store.Enter())
        {
            // The same accepted Origin chapter scene must not consume another
            // allowance when a phone reconnects, even in a later quota window.
            if (requestReceipt is { CapabilityId: "origin-dossier-media" }
                && requestReceipt.SourceRef.StartsWith("origin-dossier:scene:", StringComparison.Ordinal)
                && _store.Entries.SelectMany(row => row.RequestReceipts ?? []).Any(row =>
                    row.CapabilityId == requestReceipt.CapabilityId && row.SourceRef == requestReceipt.SourceRef
                    && string.Equals(row.RequestedByUserId, userId, StringComparison.OrdinalIgnoreCase)))
                throw new InvalidOperationException("This private scene was already admitted; read its receipt.");
            if (requestReceipt is not null)
                HorizonQuotaReceipts.RejectDuplicate(_store.Entries.SelectMany(row => row.RequestReceipts ?? []), requestReceipt.RequestId);
            int existingIndex = _store.Entries.FindIndex(item => Matches(item, userId, capability, weekStartUtc));
            HorizonArtifactUsageLedgerEntry? previous = existingIndex >= 0 ? _store.Entries[existingIndex] : null;
            int weeklyUsed = previous?.Used ?? 0;
            bool privateScene = requestReceipt is { Visibility: "private", ExternalProcessingConsent: true,
                CapabilityId: "origin-dossier-media", GovernedRenderRequest.Audience: "private" }
                && requestReceipt.SourceRef.StartsWith("origin-dossier:scene:", StringComparison.Ordinal);
            int weeklyLimit = ResolveWeeklyLimit(userId, capability, effectiveNow, request.Email,
                privateScene, out bool supporterActive, out bool sponsored);
            if (weeklyUsed < 0 || weeklyLimit < 0 || unitsRequested > (long)weeklyLimit - weeklyUsed)
            {
                throw new InvalidOperationException($"{capability.PublicLabel} allowance is exhausted for this week.");
            }

            HorizonArtifactUsageLedgerEntry updated = existingIndex >= 0
                ? _store.Entries[existingIndex] with
                {
                    Used = checked(weeklyUsed + unitsRequested),
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

            HorizonArtifactQuotaSnapshot committedQuota = BuildSnapshot(userId, capability,
                new ResolvedQuotaWindow(supporterActive, weeklyLimit, updated.Used,
                    weekStartUtc, weekStartUtc.AddDays(7), capability.AllowanceWindowKind, sponsored));
            if (requestReceipt is not null)
            {
                if (unitsRequested != 1) throw new InvalidOperationException("A request receipt must bind one consumption.");
                updated = updated with { RequestReceipts = HorizonQuotaReceipts.Append(previous?.RequestReceipts,
                    requestReceipt with { Quota = committedQuota }) };
                HorizonQuotaReceipts.Validate(updated.RequestReceipts, updated.UserId, weekStartUtc, weekStartUtc.AddDays(7),
                    updated.Used, "weekly", new(StringComparer.OrdinalIgnoreCase), updated.HorizonId, updated.CapabilityId, updated.ArtifactKind);
            }

            if (existingIndex >= 0)
            {
                _store.Entries[existingIndex] = updated;
            }
            else
            {
                _store.Entries.Add(updated);
            }

            try { _store.PersistLocked(); }
            catch
            {
                if (previous is null) _store.Entries.RemoveAt(_store.Entries.Count - 1);
                else _store.Entries[existingIndex] = previous;
                throw;
            }
            return committedQuota;
        }
    }

    internal IReadOnlyList<HorizonArtifactRequestReceipt> ListChargedRequests()
    {
        HorizonArtifactRequestReceipt[] weekly;
        using (_store.Enter())
        {
            var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var row in _store.Entries.Where(row => row.RequestReceipts is not null))
                HorizonQuotaReceipts.Validate(row.RequestReceipts, row.UserId, row.WindowStartUtc,
                    row.WindowStartUtc.AddDays(7), row.Used, "weekly", ids, row.HorizonId, row.CapabilityId, row.ArtifactKind);
            weekly = _store.Entries.SelectMany(row => row.RequestReceipts ?? []).ToArray();
        }
        return HorizonQuotaReceipts.Merge(weekly, _billing.ListChargedArtifactRequests());
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
        string allowanceTier = quota.Sponsored ? "sponsored_test" : quota.SupporterActive ? "supporter" : "free";
        return new(
            userId,
            capability.HorizonId,
            capability.CapabilityId,
            capability.ArtifactKind,
            capability.PublicLabel,
            quota.SupporterActive,
            allowanceTier,
            quota.Sponsored ? "operator_approved_private_scene_trial" : $"{allowanceTier}_{capability.EntitlementBasisSuffix}",
            quota.Sponsored ? "private_origin_scene" : capability.EntitlementScope,
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
        int weeklyLimit = ResolveWeeklyLimit(userId, capability, effectiveNow, email,
            true, out bool supporterActive, out bool sponsored);
        int weeklyUsed;
        using (_store.Enter())
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
            capability.AllowanceWindowKind, sponsored);
    }

    private int ResolveWeeklyLimit(
        string userId,
        HorizonCapabilityDefinition capability,
        DateTimeOffset effectiveNow,
        string? email,
        bool privateScene,
        out bool supporterActive,
        out bool sponsored)
    {
        supporterActive = _billing.GetMyFirstBookQuota(userId, effectiveNow, email).SupporterActive;
        int limit = supporterActive ? capability.SupporterWeeklyLimit : capability.FreeWeeklyLimit;
        int? trial = privateScene && capability.HorizonId == "origin-dossier" && capability.CapabilityId == "origin-dossier-media"
            ? _capabilities.PrivateOriginSceneSponsoredLimit(userId, effectiveNow) : null;
        sponsored = trial > limit;
        return sponsored ? trial!.Value : limit;
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
    string WindowKind,
    bool Sponsored = false);
