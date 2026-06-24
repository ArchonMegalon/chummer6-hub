using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Billing;

public static class BrilliantDirectoriesBillingConstants
{
    public const string Provider = "Brilliant Directories";
    public const string ProviderKey = "brilliant_directories";
    public const string SyncMode = "signed_membership_snapshot";
    public const string EntitlementEffect = "supporter_membership_marker";
    public const string FreePlanKey = "free";
    public const string FreePlanName = "Free";
    public const string SupporterPlanKey = "supporter";
    public const string SupporterPlanName = "Supporter";
}

public sealed record BillingPlanActionDto(
    string Label,
    string Href,
    string Method);

public sealed record BillingPlanCardDto(
    string PlanKey,
    string Name,
    string Summary,
    bool IsDefault,
    bool IsSupporter,
    bool UnlocksProductFeatures,
    string EntitlementEffect,
    IReadOnlyList<string> Included,
    BillingPlanActionDto PrimaryAction);

public sealed record BillingProviderCapabilitiesDto(
    string ProviderKey,
    string SyncMode,
    bool UsesHostedProviderCheckout,
    bool StoresTenantCredentials,
    bool GrantsPremiumFeatures,
    IReadOnlyList<string> SupportedPlanKeys,
    IReadOnlyList<string> SupportedMembershipStatuses);

public sealed record BrilliantDirectoriesBillingPageDto(
    string Provider,
    string ProviderKey,
    string Heading,
    string Summary,
    BillingProviderCapabilitiesDto Capabilities,
    IReadOnlyList<BillingPlanCardDto> Plans,
    string ManageMembershipHref);

public sealed record BrilliantDirectoriesCheckoutRequest(
    string UserId,
    string? Email);

public sealed record BrilliantDirectoriesCheckoutResponseDto(
    string Provider,
    string PlanKey,
    string CheckoutUrl);

public sealed record BrilliantDirectoriesMemberSyncRequest(
    [Required(AllowEmptyStrings = false)] string UserId,
    string? MemberId,
    string? Email,
    [Required(AllowEmptyStrings = false)] string PlanKey,
    [Required(AllowEmptyStrings = false)] string PlanName,
    [Required(AllowEmptyStrings = false)] string MembershipStatus,
    bool SupporterActive,
    DateTimeOffset ObservedAtUtc);

public sealed record BrilliantDirectoriesMemberSnapshotDto(
    string UserId,
    string? MemberId,
    string? Email,
    string PlanKey,
    string PlanName,
    string MembershipStatus,
    bool SupporterActive,
    DateTimeOffset ObservedAtUtc,
    DateTimeOffset SyncedAtUtc);

public sealed record BrilliantDirectoriesSyncResultDto(
    string Provider,
    string ProviderKey,
    string UserId,
    string PlanKey,
    bool SupporterActive,
    string Status,
    DateTimeOffset SyncedAtUtc);
