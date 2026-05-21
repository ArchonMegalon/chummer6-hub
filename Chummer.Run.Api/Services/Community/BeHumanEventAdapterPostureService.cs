using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed record BeHumanEventAdapterPosture(
    string Verdict,
    bool AdapterEnabled,
    bool ProviderVerified,
    bool SecretsConfigured,
    bool CapacityClaimAllowed,
    int? VerifiedRegistrationCapacity,
    string OperatingMode,
    string? VerificationReceiptPath,
    string? FailureReason,
    IReadOnlyList<string> AllowedEventFamilies,
    IReadOnlyList<string> ForbiddenTruthDomains);

public sealed class BeHumanEventAdapterPostureService
{
    private static readonly string[] AllowedEventFamilies =
    [
        "black_ledger_faction_events",
        "turn_reveal_watch_parties",
        "karma_forge_workshops",
        "creator_gm_onboarding_events",
        "install_import_clinics",
        "chummer_launch_events",
        "community_hub_convention_layer"
    ];

    private static readonly string[] ForbiddenTruthDomains =
    [
        "account_identity_truth",
        "rules_truth",
        "package_truth",
        "release_truth",
        "support_case_truth",
        "roadmap_truth",
        "world_tick_truth",
        "private_runner_campaign_truth",
        "sourcebook_rules_content_processing"
    ];

    private readonly IConfiguration _configuration;

    public BeHumanEventAdapterPostureService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public BeHumanEventAdapterPosture Build()
    {
        bool adapterEnabled = _configuration.GetValue<bool>("Community:BeHuman:Enabled");
        string operatingMode = NormalizeOptional(_configuration["Community:BeHuman:Mode"]) ?? "disabled";
        string? receiptPath = NormalizeOptional(_configuration["Community:BeHuman:ProviderVerificationReceiptPath"]);
        bool providerVerified = ResolveProviderVerified(receiptPath);
        bool secretsConfigured =
            !string.IsNullOrWhiteSpace(_configuration["BEHUMAN_API_KEY"])
            || !string.IsNullOrWhiteSpace(_configuration["BEHUMAN_WEBHOOK_SECRET"])
            || !string.IsNullOrWhiteSpace(_configuration["Community:BeHuman:ApiKey"])
            || !string.IsNullOrWhiteSpace(_configuration["Community:BeHuman:WebhookSecret"]);

        int? verifiedCapacity = providerVerified
            ? _configuration.GetValue<int?>("Community:BeHuman:VerifiedRegistrationCapacity")
            : null;
        bool capacityClaimAllowed = providerVerified && verifiedCapacity is > 0;

        if (!adapterEnabled)
        {
            return new BeHumanEventAdapterPosture(
                Verdict: "NOT_READY",
                AdapterEnabled: false,
                ProviderVerified: providerVerified,
                SecretsConfigured: secretsConfigured,
                CapacityClaimAllowed: false,
                VerifiedRegistrationCapacity: verifiedCapacity,
                OperatingMode: "disabled",
                VerificationReceiptPath: receiptPath,
                FailureReason: "BeHuman adapter is disabled by default.",
                AllowedEventFamilies: AllowedEventFamilies,
                ForbiddenTruthDomains: ForbiddenTruthDomains);
        }

        if (!providerVerified)
        {
            return new BeHumanEventAdapterPosture(
                Verdict: "NOT_READY",
                AdapterEnabled: true,
                ProviderVerified: false,
                SecretsConfigured: secretsConfigured,
                CapacityClaimAllowed: false,
                VerifiedRegistrationCapacity: null,
                OperatingMode: operatingMode,
                VerificationReceiptPath: receiptPath,
                FailureReason: "Provider verification receipt is missing or invalid.",
                AllowedEventFamilies: AllowedEventFamilies,
                ForbiddenTruthDomains: ForbiddenTruthDomains);
        }

        if (!secretsConfigured && !string.Equals(operatingMode, "manual", StringComparison.OrdinalIgnoreCase))
        {
            return new BeHumanEventAdapterPosture(
                Verdict: "NOT_READY",
                AdapterEnabled: true,
                ProviderVerified: true,
                SecretsConfigured: false,
                CapacityClaimAllowed: capacityClaimAllowed,
                VerifiedRegistrationCapacity: verifiedCapacity,
                OperatingMode: operatingMode,
                VerificationReceiptPath: receiptPath,
                FailureReason: "Verified provider usage requires configured secrets unless mode is manual.",
                AllowedEventFamilies: AllowedEventFamilies,
                ForbiddenTruthDomains: ForbiddenTruthDomains);
        }

        return new BeHumanEventAdapterPosture(
            Verdict: "BEHUMAN_EVENT_ADAPTER_READY",
            AdapterEnabled: true,
            ProviderVerified: true,
            SecretsConfigured: secretsConfigured,
            CapacityClaimAllowed: capacityClaimAllowed,
            VerifiedRegistrationCapacity: verifiedCapacity,
            OperatingMode: operatingMode,
            VerificationReceiptPath: receiptPath,
            FailureReason: null,
            AllowedEventFamilies: AllowedEventFamilies,
            ForbiddenTruthDomains: ForbiddenTruthDomains);
    }

    private static bool ResolveProviderVerified(string? receiptPath)
    {
        if (string.IsNullOrWhiteSpace(receiptPath) || !File.Exists(receiptPath))
        {
            return false;
        }

        string text = File.ReadAllText(receiptPath);
        return text.Contains("provider: behuman.online", StringComparison.OrdinalIgnoreCase)
            && text.Contains("verified: true", StringComparison.OrdinalIgnoreCase);
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
