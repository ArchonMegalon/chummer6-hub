using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class BrilliantDirectoriesBillingUnavailableException : InvalidOperationException
{
    public BrilliantDirectoriesBillingUnavailableException(string message, Exception? innerException = null)
        : base(message, innerException)
    {
    }
}

public sealed class BrilliantDirectoriesBillingService
{
    private const int FreeMyFirstBookMonthlyLimit = 1;
    private const int SupporterMyFirstBookMonthlyLimit = 2;
    private static readonly BillingMembershipPlanDefinition[] PlanDefinitions =
    [
        new(
            BrilliantDirectoriesBillingConstants.FreePlanKey,
            BrilliantDirectoriesBillingConstants.FreePlanName,
            "Use Chummer normally.",
            IsDefault: true,
            IsSupporter: false,
            Included:
            [
                "Full current product access",
                "Account linking and updates",
                "Same runtime features as supporters today",
                "1 Origin Book per month"
            ],
            ExampleStoryBooks:
            [
                new BillingTierExampleStoryDto(
                    "Origin Dossier: Debt Before Dawn",
                    "Origin Dossier",
                    "A decker burns their last clean SIN, takes one bad job, and learns the loadout is not optional anymore.",
                    "Fits the free tier because it is a single concise canon-safe story book that turns one pressure line into a clean runner origin.")
            ]),
        new(
            BrilliantDirectoriesBillingConstants.SupporterPlanKey,
            BrilliantDirectoriesBillingConstants.SupporterPlanName,
            "Help pay for Chummer. The app stays the same.",
            IsDefault: false,
            IsSupporter: true,
            Included:
            [
                "Supports Chummer directly",
                "Same current product access as free users",
                "No exclusive app features today",
                "2 Origin Books per month"
            ],
            ExampleStoryBooks:
            [
                new BillingTierExampleStoryDto(
                    "Narrative Origin: The Name She Chose",
                    "Narrative Origin",
                    "A runner cuts ties with an old identity after one irreversible extraction and has to become someone sharper to survive.",
                    "Fits the supporter tier because one premium monthly slot can go to a cleaner chaptered origin instead of a short dossier."),
                new BillingTierExampleStoryDto(
                    "Runner Memoir: Becoming the Runner",
                    "Runner Memoir",
                    "A first-person street memoir that opens on the worst mistake, then tracks crew, betrayal, and the choice that made the runner.",
                    "Fits the supporter tier because the second premium monthly slot can go to a longer voice-driven memoir.")
            ])
    ];

    private readonly BrilliantDirectoriesBillingStore _store;
    private readonly MyFirstBookUsageStore _myFirstBookUsage;
    private readonly IConfiguration _configuration;

    public BrilliantDirectoriesBillingService(
        BrilliantDirectoriesBillingStore store,
        MyFirstBookUsageStore myFirstBookUsage,
        IConfiguration configuration)
    {
        _store = store;
        _myFirstBookUsage = myFirstBookUsage;
        _configuration = configuration;
    }

    public BrilliantDirectoriesBillingPageDto GetPage()
    {
        BillingProviderOptions options = ResolveOptions();
        return new BrilliantDirectoriesBillingPageDto(
            Provider: options.ProviderName,
            ProviderKey: options.ProviderKey,
            Heading: "Membership",
            Summary: "Free and Supporter use the same app. Supporter helps pay for Chummer.",
            MyFirstBookQuotaPolicy: new MyFirstBookQuotaPolicyDto(
                FreeMonthlyBooks: FreeMyFirstBookMonthlyLimit,
                SupporterMonthlyBooks: SupporterMyFirstBookMonthlyLimit),
            Capabilities: new BillingProviderCapabilitiesDto(
                options.ProviderKey,
                BrilliantDirectoriesBillingConstants.SyncMode,
                UsesHostedProviderCheckout: true,
                StoresTenantCredentials: false,
                GrantsPremiumFeatures: false,
                SupportedPlanKeys: PlanDefinitions.Select(static item => item.PlanKey).ToArray(),
                SupportedMembershipStatuses: options.SupportedMembershipStatuses),
            Plans: PlanDefinitions
                .Select(plan => ToCard(plan, options))
                .ToArray(),
            ManageMembershipHref: options.MemberPortalUrl ?? string.Empty);
    }

    public MyFirstBookQuotaSnapshotDto GetMyFirstBookQuota(string userId, DateTimeOffset? now = null, string? email = null)
    {
        string normalizedUserId = RequireValue(userId, "A user id is required before checking MyFirstBook quota.");
        DateTimeOffset effectiveNow = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        DateTimeOffset windowStartUtc = new(effectiveNow.Year, effectiveNow.Month, 1, 0, 0, 0, TimeSpan.Zero);
        DateTimeOffset windowEndUtc = windowStartUtc.AddMonths(1);

        BrilliantDirectoriesMemberSnapshotDto? membership = GetAccount(normalizedUserId)
            ?? GetAccountByEmail(email);
        bool supporterActive = membership?.SupporterActive == true;
        string planKey = supporterActive
            ? BrilliantDirectoriesBillingConstants.SupporterPlanKey
            : BrilliantDirectoriesBillingConstants.FreePlanKey;
        string planName = supporterActive
            ? BrilliantDirectoriesBillingConstants.SupporterPlanName
            : BrilliantDirectoriesBillingConstants.FreePlanName;
        int monthlyLimit = supporterActive ? SupporterMyFirstBookMonthlyLimit : FreeMyFirstBookMonthlyLimit;

        int monthlyUsed;
        lock (_myFirstBookUsage.Gate)
        {
            monthlyUsed = _myFirstBookUsage.Entries
                .Where(item => string.Equals(item.UserId, normalizedUserId, StringComparison.OrdinalIgnoreCase)
                    && item.WindowStartUtc == windowStartUtc)
                .Select(static item => item.MonthlyUsed)
                .FirstOrDefault();
        }

        return new MyFirstBookQuotaSnapshotDto(
            UserId: normalizedUserId,
            PlanKey: planKey,
            PlanName: planName,
            SupporterActive: supporterActive,
            MonthlyLimit: monthlyLimit,
            MonthlyUsed: monthlyUsed,
            MonthlyRemaining: Math.Max(0, monthlyLimit - monthlyUsed),
            WindowStartUtc: windowStartUtc,
            WindowEndUtc: windowEndUtc);
    }

    public MyFirstBookQuotaConsumeResultDto ConsumeMyFirstBookQuota(string userId, DateTimeOffset? now = null, string? email = null)
    {
        MyFirstBookQuotaSnapshotDto snapshot = GetMyFirstBookQuota(userId, now, email);
        if (snapshot.MonthlyRemaining <= 0)
        {
            throw new InvalidOperationException("Monthly MyFirstBook allowance is exhausted for this account.");
        }

        DateTimeOffset effectiveNow = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        lock (_myFirstBookUsage.Gate)
        {
            int existingIndex = _myFirstBookUsage.Entries.FindIndex(item =>
                string.Equals(item.UserId, snapshot.UserId, StringComparison.OrdinalIgnoreCase)
                && item.WindowStartUtc == snapshot.WindowStartUtc);
            MyFirstBookUsageLedgerEntry updated = existingIndex >= 0
                ? _myFirstBookUsage.Entries[existingIndex] with
                {
                    MonthlyUsed = _myFirstBookUsage.Entries[existingIndex].MonthlyUsed + 1,
                    UpdatedAtUtc = effectiveNow
                }
                : new MyFirstBookUsageLedgerEntry(snapshot.UserId, snapshot.WindowStartUtc, 1, effectiveNow);
            if (existingIndex >= 0)
            {
                _myFirstBookUsage.Entries[existingIndex] = updated;
            }
            else
            {
                _myFirstBookUsage.Entries.Add(updated);
            }

            _myFirstBookUsage.PersistLocked();
        }

        return new MyFirstBookQuotaConsumeResultDto(
            Status: "consumed",
            Quota: GetMyFirstBookQuota(userId, effectiveNow, email));
    }

    public BrilliantDirectoriesCheckoutResponseDto CreateSupporterCheckout(BrilliantDirectoriesCheckoutRequest request)
    {
        BillingProviderOptions options = ResolveOptions();
        string userId = RequireValue(request.UserId, "A user id is required before opening supporter checkout.");

        return new BrilliantDirectoriesCheckoutResponseDto(
            options.ProviderName,
            BrilliantDirectoriesBillingConstants.SupporterPlanKey,
            BuildSupporterCheckoutUrl(options, userId, TrimToNull(request.Email)));
    }

    public BrilliantDirectoriesSyncResultDto SyncMember(BrilliantDirectoriesMemberSyncRequest request, string? secret)
    {
        BillingProviderOptions options = ResolveOptions();
        EnsureAuthorized(secret, options);

        BrilliantDirectoriesMemberSnapshotDto snapshot = BuildSnapshot(request, options);
        DateTimeOffset syncedAtUtc = DateTimeOffset.UtcNow;
        snapshot = snapshot with { SyncedAtUtc = syncedAtUtc };

        lock (_store.Gate)
        {
            _store.Members.RemoveAll(item => string.Equals(item.UserId, snapshot.UserId, StringComparison.OrdinalIgnoreCase));
            _store.Members.Add(snapshot);
            _store.PersistLocked();
        }

        return new BrilliantDirectoriesSyncResultDto(
            options.ProviderName,
            options.ProviderKey,
            snapshot.UserId,
            snapshot.PlanKey,
            snapshot.SupporterActive,
            "synced",
            snapshot.SyncedAtUtc);
    }

    public BrilliantDirectoriesMemberSnapshotDto? GetAccount(string userId)
    {
        lock (_store.Gate)
        {
            return _store.Members
                .Where(item => string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(item => item.SyncedAtUtc)
                .FirstOrDefault();
        }
    }

    public BrilliantDirectoriesMemberSnapshotDto? GetAccountByEmail(string? email)
    {
        string? normalizedEmail = NormalizeEmail(email);
        if (normalizedEmail is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.Members
                .Where(item => string.Equals(NormalizeEmail(item.Email), normalizedEmail, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(item => item.SyncedAtUtc)
                .FirstOrDefault();
        }
    }

    public void EnsureAuthorized(string? secret)
    {
        BillingProviderOptions options = ResolveOptions();
        EnsureAuthorized(secret, options);
    }

    private static BillingPlanCardDto ToCard(BillingMembershipPlanDefinition plan, BillingProviderOptions options)
    {
        string href = plan.IsSupporter
            ? "/account/billing/supporter"
            : options.FreePlanUrl ?? options.MemberPortalUrl ?? "/account";
        return new BillingPlanCardDto(
            plan.PlanKey,
            plan.Name,
            plan.Summary,
            plan.IsDefault,
            plan.IsSupporter,
            UnlocksProductFeatures: false,
            BrilliantDirectoriesBillingConstants.EntitlementEffect,
            plan.Included,
            plan.ExampleStoryBooks,
            new BillingPlanActionDto(
                plan.IsSupporter ? "Become Supporter" : "Keep Free",
                href,
                plan.IsSupporter ? "post" : "get"));
    }

    private static BrilliantDirectoriesMemberSnapshotDto BuildSnapshot(
        BrilliantDirectoriesMemberSyncRequest request,
        BillingProviderOptions options)
    {
        string userId = RequireValue(request.UserId, "A user id is required before syncing membership.");
        string planKey = NormalizeKey(RequireValue(request.PlanKey, "A plan key is required before syncing membership."));
        BillingMembershipPlanDefinition plan = PlanDefinitions.FirstOrDefault(item => string.Equals(item.PlanKey, planKey, StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException($"Unsupported billing plan '{planKey}'. Supported plans are: {string.Join(", ", PlanDefinitions.Select(static item => item.PlanKey))}.");

        string status = NormalizeStatus(RequireValue(request.MembershipStatus, "A membership status is required before syncing membership."));
        if (!options.SupportedMembershipStatuses.Contains(status, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"Unsupported membership status '{status}'. Configure it before accepting this provider behavior.");
        }

        bool derivedSupporterActive = plan.IsSupporter && options.ActiveMembershipStatuses.Contains(status, StringComparer.OrdinalIgnoreCase);
        if (request.SupporterActive != derivedSupporterActive)
        {
            throw new InvalidOperationException("SupporterActive did not match the configured plan/status mapping; refusing ambiguous provider membership state.");
        }

        DateTimeOffset observedAtUtc = request.ObservedAtUtc == default
            ? DateTimeOffset.UtcNow
            : request.ObservedAtUtc.ToUniversalTime();
        var snapshot = new BrilliantDirectoriesMemberSnapshotDto(
            UserId: userId,
            MemberId: TrimToNull(request.MemberId),
            Email: TrimToNull(request.Email),
            PlanKey: plan.PlanKey,
            PlanName: plan.Name,
            MembershipStatus: status,
            SupporterActive: derivedSupporterActive,
            ObservedAtUtc: observedAtUtc,
            SyncedAtUtc: DateTimeOffset.UtcNow);
        return snapshot;
    }

    private BillingProviderOptions ResolveOptions()
    {
        string providerName = ReadOptional("BRILLIANT_DIRECTORIES_PROVIDER_NAME", "BrilliantDirectories:ProviderName")
            ?? BrilliantDirectoriesBillingConstants.Provider;
        string providerKey = NormalizeKey(ReadOptional("BRILLIANT_DIRECTORIES_PROVIDER_KEY", "BrilliantDirectories:ProviderKey")
            ?? BrilliantDirectoriesBillingConstants.ProviderKey);
        return new BillingProviderOptions(
            providerName,
            providerKey,
            ReadOptionalUrl("BRILLIANT_DIRECTORIES_FREE_PLAN_URL", "BrilliantDirectories:FreePlanUrl"),
            ReadRequiredUrl("BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL", "BrilliantDirectories:SupporterPlanUrl", "supporter checkout URL"),
            ReadOptionalUrl("BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL", "BrilliantDirectories:MemberPortalUrl"),
            ReadOptional("BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER", "BrilliantDirectories:CheckoutUserIdParameter") ?? "chummer_user_id",
            ReadOptional("BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER", "BrilliantDirectories:CheckoutEmailParameter") ?? "email",
            ReadOptional("BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER", "BrilliantDirectories:CheckoutPlanParameter") ?? "plan",
            ReadOptional("BRILLIANT_DIRECTORIES_SYNC_SECRET", "BrilliantDirectories:SyncSecret"),
            ReadCsv("BRILLIANT_DIRECTORIES_SUPPORTED_MEMBERSHIP_STATUSES", "BrilliantDirectories:SupportedMembershipStatuses", ["active", "inactive", "pending", "canceled", "cancelled", "expired", "suspended", "lifetime"]),
            ReadCsv("BRILLIANT_DIRECTORIES_ACTIVE_MEMBERSHIP_STATUSES", "BrilliantDirectories:ActiveMembershipStatuses", ["active", "lifetime"]));
    }

    private string? ReadOptional(string environmentKey, string configurationKey)
        => TrimToNull(_configuration[environmentKey]) ?? TrimToNull(_configuration[configurationKey]);

    private string ReadRequired(string environmentKey, string configurationKey, string label)
        => ReadOptional(environmentKey, configurationKey)
            ?? throw new BrilliantDirectoriesBillingUnavailableException($"BRILLIANT_DIRECTORIES_{label.ToUpperInvariant().Replace(' ', '_')} must be configured; real tenant credentials are not required or stored by Hub.");

    private string? ReadOptionalUrl(string environmentKey, string configurationKey)
    {
        string? value = ReadOptional(environmentKey, configurationKey);
        return value is null ? null : ValidateExternalUrl(value, environmentKey);
    }

    private string ReadRequiredUrl(string environmentKey, string configurationKey, string label)
    {
        try
        {
            return ValidateExternalUrl(ReadRequired(environmentKey, configurationKey, label), environmentKey);
        }
        catch (InvalidOperationException ex) when (ex is not BrilliantDirectoriesBillingUnavailableException)
        {
            throw new BrilliantDirectoriesBillingUnavailableException(
                "Membership billing is unavailable right now.",
                ex);
        }
    }

    private IReadOnlyList<string> ReadCsv(string environmentKey, string configurationKey, IReadOnlyList<string> defaults)
    {
        string? value = ReadOptional(environmentKey, configurationKey);
        string[] items = (value is null ? defaults : value.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
            .Select(NormalizeStatus)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        return items.Length == 0 ? defaults : items;
    }

    private static string ValidateExternalUrl(string value, string key)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? uri)
            || (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp))
        {
            throw new InvalidOperationException($"{key} must be an absolute http or https URL.");
        }

        if (uri.Scheme == Uri.UriSchemeHttp && !uri.IsLoopback)
        {
            throw new InvalidOperationException($"{key} must use https unless it targets a loopback host for local verification.");
        }

        return uri.ToString();
    }

    private static string BuildSupporterCheckoutUrl(BillingProviderOptions options, string userId, string? email)
    {
        string checkoutUrl = AppendQueryParameter(options.SupporterPlanUrl, options.UserIdParameter, userId);
        if (!string.IsNullOrWhiteSpace(email))
        {
            checkoutUrl = AppendQueryParameter(checkoutUrl, options.EmailParameter, email);
        }

        checkoutUrl = AppendQueryParameter(checkoutUrl, options.PlanParameter, BrilliantDirectoriesBillingConstants.SupporterPlanKey);
        return checkoutUrl;
    }

    private static string AppendQueryParameter(string url, string name, string value)
    {
        var builder = new StringBuilder(url);
        char separator = url.Contains('?', StringComparison.Ordinal) ? '&' : '?';
        if (url.EndsWith("?", StringComparison.Ordinal) || url.EndsWith("&", StringComparison.Ordinal))
        {
            separator = '\0';
        }

        if (separator != '\0')
        {
            builder.Append(separator);
        }

        builder.Append(Uri.EscapeDataString(name));
        builder.Append('=');
        builder.Append(Uri.EscapeDataString(value));
        return builder.ToString();
    }

    private static bool SecretsMatch(string? provided, string expected)
    {
        string? providedTrimmed = TrimToNull(provided);
        if (providedTrimmed is null)
        {
            return false;
        }

        byte[] providedBytes = Encoding.UTF8.GetBytes(providedTrimmed);
        byte[] expectedBytes = Encoding.UTF8.GetBytes(expected.Trim());
        return providedBytes.Length == expectedBytes.Length
            && CryptographicOperations.FixedTimeEquals(providedBytes, expectedBytes);
    }

    private static void EnsureAuthorized(string? secret, BillingProviderOptions options)
    {
        if (string.IsNullOrWhiteSpace(options.SyncSecret))
        {
            throw new BrilliantDirectoriesBillingUnavailableException("Billing sync is unavailable right now.");
        }

        if (!SecretsMatch(secret, options.SyncSecret))
        {
            throw new UnauthorizedAccessException("Billing sync secret did not match.");
        }
    }

    private static string RequireValue(string? value, string message)
        => TrimToNull(value) ?? throw new InvalidOperationException(message);

    private static string? TrimToNull(string? value)
    {
        string? trimmed = value?.Trim();
        return string.IsNullOrWhiteSpace(trimmed) ? null : trimmed;
    }

    private static string? NormalizeEmail(string? value)
        => TrimToNull(value)?.ToLower(CultureInfo.InvariantCulture);

    private static string NormalizeKey(string value)
        => value.Trim().ToLower(CultureInfo.InvariantCulture).Replace('-', '_').Replace(' ', '_');

    private static string NormalizeStatus(string value)
    {
        string status = NormalizeKey(value);
        return status == "cancelled" ? "canceled" : status;
    }
}

internal sealed record BillingMembershipPlanDefinition(
    string PlanKey,
    string Name,
    string Summary,
    bool IsDefault,
    bool IsSupporter,
    IReadOnlyList<string> Included,
    IReadOnlyList<BillingTierExampleStoryDto> ExampleStoryBooks);

internal sealed record BillingProviderOptions(
    string ProviderName,
    string ProviderKey,
    string? FreePlanUrl,
    string SupporterPlanUrl,
    string? MemberPortalUrl,
    string UserIdParameter,
    string EmailParameter,
    string PlanParameter,
    string? SyncSecret,
    IReadOnlyList<string> SupportedMembershipStatuses,
    IReadOnlyList<string> ActiveMembershipStatuses);
