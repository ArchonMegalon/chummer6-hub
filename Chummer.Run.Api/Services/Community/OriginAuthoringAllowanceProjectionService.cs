using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Billing;

namespace Chummer.Run.Api.Services.Community;

public sealed class OriginAuthoringAllowanceProjectionService
{
    private readonly BrilliantDirectoriesBillingService? _billing;
    private readonly HorizonArtifactQuotaService? _quota;

    public OriginAuthoringAllowanceProjectionService(
        BrilliantDirectoriesBillingService? billing = null,
        HorizonArtifactQuotaService? quota = null)
    {
        _billing = billing;
        _quota = quota;
    }

    public HorizonArtifactAllowanceViewModel? TryGetAllowance(string userId, string? email = null)
    {
        try
        {
            return GetAllowance(userId, email);
        }
        catch (BrilliantDirectoriesBillingUnavailableException)
        {
            return null;
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    public HorizonArtifactAllowanceViewModel GetAllowance(string userId, string? email = null)
    {
        string normalizedUserId = RequireUserId(userId);
        if (_quota is not null)
        {
            HorizonArtifactQuotaSnapshot quota = _quota.GetQuota(
                new HorizonArtifactQuotaRequest(
                    UserId: normalizedUserId,
                    HorizonId: "origin-dossier",
                    ArtifactKindOrCapabilityId: "premium_authoring_credit",
                    Email: email));
            return Map(quota);
        }

        if (_billing is null)
        {
            throw new InvalidOperationException("Origin authoring allowance projection is not available.");
        }

        return Map(_billing.GetMyFirstBookQuota(normalizedUserId, email: email));
    }

    public HorizonArtifactAllowanceViewModel ConsumeAllowance(string userId, string? email = null)
    {
        string normalizedUserId = RequireUserId(userId);
        if (_quota is not null)
        {
            HorizonArtifactQuotaSnapshot quota = _quota.Consume(
                new HorizonArtifactQuotaRequest(
                    UserId: normalizedUserId,
                    HorizonId: "origin-dossier",
                    ArtifactKindOrCapabilityId: "premium_authoring_credit",
                    Email: email));
            return Map(quota);
        }

        if (_billing is null)
        {
            throw new InvalidOperationException("Origin authoring allowance projection is not available.");
        }

        return Map(_billing.ConsumeMyFirstBookQuota(normalizedUserId, email: email).Quota);
    }

    public MyFirstBookQuotaSnapshotDto GetLegacyQuota(string userId, string? email = null)
        => MapLegacy(RequireUserId(userId), GetAllowance(userId, email));

    public MyFirstBookQuotaConsumeResultDto ConsumeLegacyQuota(string userId, string? email = null)
        => new(
            "consumed",
            MapLegacy(RequireUserId(userId), ConsumeAllowance(userId, email)));

    private static HorizonArtifactAllowanceViewModel Map(HorizonArtifactQuotaSnapshot quota)
        => new(
            HorizonId: quota.HorizonId,
            CapabilityId: quota.CapabilityId,
            ArtifactKind: quota.ArtifactKind,
            PublicLabel: quota.PublicLabel,
            SupporterActive: quota.SupporterActive,
            AllowanceTier: quota.AllowanceTier,
            AllowanceTierLabel: quota.SupporterActive
                ? BrilliantDirectoriesBillingConstants.SupporterPlanName
                : BrilliantDirectoriesBillingConstants.FreePlanName,
            WindowKind: quota.WindowKind,
            WindowLimit: quota.WindowLimit,
            WindowUsed: quota.WindowUsed,
            WindowRemaining: quota.WindowRemaining,
            WindowStartUtc: quota.WindowStartUtc,
            WindowEndUtc: quota.WindowEndUtc);

    private static HorizonArtifactAllowanceViewModel Map(MyFirstBookQuotaSnapshotDto quota)
        => new(
            HorizonId: "origin-dossier",
            CapabilityId: "origin-dossier-premium-authoring",
            ArtifactKind: "premium_authoring_credit",
            PublicLabel: "Premium Authoring Credit",
            SupporterActive: quota.SupporterActive,
            AllowanceTier: quota.SupporterActive
                ? BrilliantDirectoriesBillingConstants.SupporterPlanKey
                : BrilliantDirectoriesBillingConstants.FreePlanKey,
            AllowanceTierLabel: quota.PlanName,
            WindowKind: "monthly",
            WindowLimit: quota.MonthlyLimit,
            WindowUsed: quota.MonthlyUsed,
            WindowRemaining: quota.MonthlyRemaining,
            WindowStartUtc: quota.WindowStartUtc,
            WindowEndUtc: quota.WindowEndUtc);

    private static MyFirstBookQuotaSnapshotDto MapLegacy(string userId, HorizonArtifactAllowanceViewModel quota)
        => new(
            UserId: userId,
            PlanKey: quota.AllowanceTier,
            PlanName: quota.AllowanceTierLabel,
            SupporterActive: quota.SupporterActive,
            MonthlyLimit: quota.WindowLimit,
            MonthlyUsed: quota.WindowUsed,
            MonthlyRemaining: quota.WindowRemaining,
            WindowStartUtc: quota.WindowStartUtc,
            WindowEndUtc: quota.WindowEndUtc);

    private static string RequireUserId(string userId)
        => string.IsNullOrWhiteSpace(userId)
            ? throw new InvalidOperationException("A user id is required before resolving origin authoring allowance.")
            : userId.Trim();
}
