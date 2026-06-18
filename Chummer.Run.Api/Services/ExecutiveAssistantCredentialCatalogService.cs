using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

public sealed class ExecutiveAssistantCredentialCatalogService
{
    private readonly IConfiguration _configuration;

    public ExecutiveAssistantCredentialCatalogService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public ExecutiveAssistantCredentialCatalogResult GetCatalog()
    {
        ExecutiveAssistantCredentialEntry[] entries =
        {
            BuildDefaultEntry(),
            BuildNamedEntry(
                toolId: "blipai.app",
                tierKey: "CHUMMER_EA_BLIPAI_APP_TIER",
                emailKey: "CHUMMER_EA_BLIPAI_APP_EMAIL",
                passwordKey: "CHUMMER_EA_BLIPAI_APP_PASSWORD",
                mirrorsDefault: true),
            BuildNamedEntry(
                toolId: "magicfit",
                tierKey: "CHUMMER_EA_MAGICFIT_TIER",
                emailKey: "CHUMMER_EA_MAGICFIT_EMAIL",
                passwordKey: "CHUMMER_EA_MAGICFIT_PASSWORD",
                mirrorsDefault: true),
            BuildMagicfitSessionEntry(),
            BuildPromptArchitectsEntry(),
            BuildPayFunnelsEntry(),
            BuildUnmixrEntry(),
            BuildInventoryOnlyEntry("joggai", "4", "tracked_in_discovery"),
            BuildInventoryOnlyEntry("dadan", "candidate", "inventory_only"),
            BuildSingleKeyEntry("rybbit", "analytics", "RYBBIT_CHUMMER_RUN_SCRIPT_URL", false, "bounded_public_and_desktop_analytics_lane"),
            BuildSingleKeyEntry("clickrank", "visibility", "CLICKRANK_AI_CHUMMER_RUN_SITE_ID", false, "bounded_public_visibility_lane"),
            BuildInventoryOnlyEntry("neuronwriter", "candidate", "bounded_source_packet_seo_lane"),
            BuildInventoryOnlyEntry("rafter", "qa", "auxiliary_release_qa_lane"),
            BuildInventoryOnlyEntry("pixefy", "qa", "auxiliary_visual_qa_lane")
        };

        return new ExecutiveAssistantCredentialCatalogResult(
            DateTimeOffset.UtcNow,
            entries);
    }

    private ExecutiveAssistantCredentialEntry BuildDefaultEntry()
    {
        string emailKey = "CHUMMER_EA_DEFAULT_EMAIL";
        string passwordKey = "CHUMMER_EA_DEFAULT_PASSWORD";
        string altPasswordKey = "CHUMMER_EA_DEFAULT_PASSWORD_ALT";
        string? email = GetValue(emailKey);

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "default",
            Tier: null,
            EmailKey: emailKey,
            PasswordKey: passwordKey,
            PasswordAltKey: altPasswordKey,
            EmailMasked: MaskEmail(email),
            EmailConfigured: !string.IsNullOrWhiteSpace(email),
            PasswordConfigured: !string.IsNullOrWhiteSpace(GetValue(passwordKey)),
            PasswordAltConfigured: !string.IsNullOrWhiteSpace(GetValue(altPasswordKey)),
            MirrorsDefault: false,
            Status: BuildStatus(emailKey, passwordKey, altPasswordKey));
    }

    private ExecutiveAssistantCredentialEntry BuildNamedEntry(
        string toolId,
        string tierKey,
        string emailKey,
        string passwordKey,
        bool mirrorsDefault)
    {
        string? email = GetValue(emailKey);

        return new ExecutiveAssistantCredentialEntry(
            ToolId: toolId,
            Tier: GetValue(tierKey),
            EmailKey: emailKey,
            PasswordKey: passwordKey,
            PasswordAltKey: null,
            EmailMasked: MaskEmail(email),
            EmailConfigured: !string.IsNullOrWhiteSpace(email),
            PasswordConfigured: !string.IsNullOrWhiteSpace(GetValue(passwordKey)),
            PasswordAltConfigured: false,
            MirrorsDefault: mirrorsDefault,
            Status: BuildStatus(emailKey, passwordKey));
    }

    private ExecutiveAssistantCredentialEntry BuildMagicfitSessionEntry()
    {
        const string emailKey = "CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL";
        const string passwordKey = "CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD";
        const string fallbackOfficialMagicfitEmail = "CHUMMER_EA_MAGICFIT_EMAIL";

        string? sessionEmail = GetValue(emailKey);
        string? officialEmail = GetValue(fallbackOfficialMagicfitEmail);
        string? sessionPassword = GetValue(passwordKey);
        string status = BuildMagicfitSessionStatus(sessionEmail, sessionPassword, officialEmail);

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "magicfit_session",
            Tier: "5",
            EmailKey: emailKey,
            PasswordKey: passwordKey,
            PasswordAltKey: null,
            EmailMasked: MaskEmail(sessionEmail),
            EmailConfigured: !string.IsNullOrWhiteSpace(sessionEmail),
            PasswordConfigured: !string.IsNullOrWhiteSpace(GetValue(passwordKey)),
            PasswordAltConfigured: false,
            MirrorsDefault: false,
            Status: status);
    }

    private ExecutiveAssistantCredentialEntry BuildPromptArchitectsEntry()
    {
        string apiKey = "PROMPTING_SYSTEMS_API_KEY";
        bool verified = ReadBoolean("PROMPT_ARCHITECTS_TIER4_VERIFIED", false);
        bool apiAvailable = ReadBoolean("PROMPT_ARCHITECTS_API_AVAILABLE", false);
        bool mcpVerified = ReadBoolean("PROMPT_ARCHITECTS_MCP_VERIFIED", false);
        bool exportAvailable = ReadBoolean("PROMPT_ARCHITECTS_EXPORT_AVAILABLE", false);
        bool retentionReviewed = ReadBoolean("PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED", false);
        bool teamPermissionsReviewed = ReadBoolean("PROMPT_ARCHITECTS_TEAM_PERMISSIONS_REVIEWED", false);
        bool runtimeReady = verified && (apiAvailable || mcpVerified) && exportAvailable && retentionReviewed && teamPermissionsReviewed;
        string? apiKeyValue = GetValue(apiKey);

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "prompt_architects",
            Tier: "4",
            EmailKey: apiKey,
            PasswordKey: string.Empty,
            PasswordAltKey: null,
            EmailMasked: null,
            EmailConfigured: !string.IsNullOrWhiteSpace(apiKeyValue),
            PasswordConfigured: false,
            PasswordAltConfigured: false,
            MirrorsDefault: false,
            Status: apiKeyValue is null ? "missing" : runtimeReady ? "configured" : "missing");
    }

    private ExecutiveAssistantCredentialEntry BuildPayFunnelsEntry()
    {
        string webhookSecret = "PAYFUNNELS_WEBHOOK_SECRET";

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "payfunnels",
            Tier: "3",
            EmailKey: webhookSecret,
            PasswordKey: string.Empty,
            PasswordAltKey: null,
            EmailMasked: null,
            EmailConfigured: !string.IsNullOrWhiteSpace(GetValue(webhookSecret)),
            PasswordConfigured: false,
            PasswordAltConfigured: false,
            MirrorsDefault: false,
            Status: string.IsNullOrWhiteSpace(GetValue(webhookSecret)) ? "missing" : "configured");
    }

    private ExecutiveAssistantCredentialEntry BuildUnmixrEntry()
    {
        const string tierKey = "CHUMMER_EA_UNMIXR_TIER";
        const string emailKey = "CHUMMER_EA_UNMIXR_EMAIL";
        const string passwordKey = "CHUMMER_EA_UNMIXR_PASSWORD";
        const string apiKey = "UNMIXR_API_KEY";
        const string voiceIdKey = "UNMIXR_VOICE_ID";
        const string usernameKey = "UNMIXR_USERNAME";
        const string loginPasswordKey = "UNMIXR_PASSWORD";

        string? email = GetValue(emailKey);
        bool hasEaLogin = !string.IsNullOrWhiteSpace(email) && !string.IsNullOrWhiteSpace(GetValue(passwordKey));
        bool hasProviderLogin = !string.IsNullOrWhiteSpace(GetValue(usernameKey)) && !string.IsNullOrWhiteSpace(GetValue(loginPasswordKey));
        bool hasRuntimeVoice = !string.IsNullOrWhiteSpace(GetValue(apiKey)) && !string.IsNullOrWhiteSpace(GetValue(voiceIdKey));

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "unmixr",
            Tier: GetValue(tierKey) ?? "4",
            EmailKey: emailKey,
            PasswordKey: passwordKey,
            PasswordAltKey: apiKey,
            EmailMasked: MaskEmail(email),
            EmailConfigured: !string.IsNullOrWhiteSpace(email),
            PasswordConfigured: !string.IsNullOrWhiteSpace(GetValue(passwordKey)),
            PasswordAltConfigured: !string.IsNullOrWhiteSpace(GetValue(apiKey)),
            MirrorsDefault: true,
            Status: hasRuntimeVoice ? "configured" : hasEaLogin || hasProviderLogin ? "login_only" : "missing");
    }

    private ExecutiveAssistantCredentialEntry BuildSingleKeyEntry(
        string toolId,
        string tier,
        string key,
        bool mirrorsDefault,
        string configuredStatus)
    {
        bool configured = !string.IsNullOrWhiteSpace(GetValue(key));
        return new ExecutiveAssistantCredentialEntry(
            ToolId: toolId,
            Tier: tier,
            EmailKey: key,
            PasswordKey: string.Empty,
            PasswordAltKey: null,
            EmailMasked: null,
            EmailConfigured: configured,
            PasswordConfigured: false,
            PasswordAltConfigured: false,
            MirrorsDefault: mirrorsDefault,
            Status: configured ? configuredStatus : "missing");
    }

    private static ExecutiveAssistantCredentialEntry BuildInventoryOnlyEntry(
        string toolId,
        string tier,
        string status)
        => new(
            ToolId: toolId,
            Tier: tier,
            EmailKey: string.Empty,
            PasswordKey: string.Empty,
            PasswordAltKey: null,
            EmailMasked: null,
            EmailConfigured: false,
            PasswordConfigured: false,
            PasswordAltConfigured: false,
            MirrorsDefault: false,
            Status: status);

    private string BuildStatus(params string[] keys)
    {
        return keys.Length > 0
            && keys.All(key => !string.IsNullOrWhiteSpace(GetValue(key)))
            ? "configured"
            : "missing";
    }

    private bool ReadBoolean(string key, bool fallback)
    {
        string? value = _configuration[key];
        if (string.IsNullOrWhiteSpace(value))
        {
            return fallback;
        }

        return value.Equals("1", StringComparison.OrdinalIgnoreCase)
            || value.Equals("true", StringComparison.OrdinalIgnoreCase)
            || value.Equals("yes", StringComparison.OrdinalIgnoreCase)
            || value.Equals("verified", StringComparison.OrdinalIgnoreCase);
    }

    private string BuildMagicfitSessionStatus(string? sessionEmail, string? sessionPassword, string? officialEmail)
    {
        if (string.IsNullOrWhiteSpace(sessionEmail) || string.IsNullOrWhiteSpace(sessionPassword))
        {
            return "missing";
        }

        if (!string.IsNullOrWhiteSpace(officialEmail)
            && string.Equals(sessionEmail.Trim(), officialEmail.Trim(), StringComparison.OrdinalIgnoreCase))
        {
            return "ready_but_not_isolated";
        }

        return "configured";
    }

    private string? GetValue(string key)
    {
        string? value = _configuration[key];
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    internal static string? MaskEmail(string? email)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            return null;
        }

        string trimmed = email.Trim();
        int atIndex = trimmed.IndexOf('@');
        if (atIndex <= 0 || atIndex == trimmed.Length - 1)
        {
            return "***";
        }

        string localPart = trimmed[..atIndex];
        string domain = trimmed[(atIndex + 1)..];
        string localPrefix = localPart[..1];
        string domainPrefix = domain[..1];
        return $"{localPrefix}***@{domainPrefix}***";
    }
}

public sealed record ExecutiveAssistantCredentialCatalogResult(
    DateTimeOffset GeneratedAt,
    IReadOnlyList<ExecutiveAssistantCredentialEntry> Entries);

public sealed record ExecutiveAssistantCredentialEntry(
    string ToolId,
    string? Tier,
    string EmailKey,
    string PasswordKey,
    string? PasswordAltKey,
    string? EmailMasked,
    bool EmailConfigured,
    bool PasswordConfigured,
    bool PasswordAltConfigured,
    bool MirrorsDefault,
    string Status);
