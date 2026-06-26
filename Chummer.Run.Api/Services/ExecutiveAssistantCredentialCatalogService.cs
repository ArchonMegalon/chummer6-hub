using System.Text.RegularExpressions;
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
        List<ExecutiveAssistantCredentialEntry> entries =
        [
            BuildDefaultEntry(),
            BuildNamedEntry(
                toolId: "blipai.app",
                tierKey: "CHUMMER_EA_BLIPAI_APP_TIER",
                emailKey: "CHUMMER_EA_BLIPAI_APP_EMAIL",
                passwordKey: "CHUMMER_EA_BLIPAI_APP_PASSWORD",
                mirrorsDefault: true),
            BuildIcanpreneurEntry(),
            BuildNamedEntry(
                toolId: "magicfit",
                tierKey: "CHUMMER_EA_MAGICFIT_TIER",
                emailKey: "CHUMMER_EA_MAGICFIT_EMAIL",
                passwordKey: "CHUMMER_EA_MAGICFIT_PASSWORD",
                mirrorsDefault: true),
            BuildMagicAiEntry(),
            BuildMagicfitSessionEntry(),
            BuildPromptArchitectsEntry(),
            BuildPayFunnelsEntry(),
            BuildSubscribrEntry(),
            BuildUnmixrEntry(),
            BuildInventoryOnlyEntry("joggai", "4", "tracked_in_discovery"),
            BuildInventoryOnlyEntry("dadan", "candidate", "inventory_only"),
            BuildSingleKeyEntry("rybbit", "analytics", "RYBBIT_CHUMMER_RUN_SCRIPT_URL", false, "bounded_public_and_desktop_analytics_lane"),
            BuildSingleKeyEntry("clickrank", "visibility", "CLICKRANK_AI_CHUMMER_RUN_SITE_ID", false, "bounded_public_visibility_lane"),
            BuildInventoryOnlyEntry("neuronwriter", "candidate", "bounded_source_packet_seo_lane"),
            BuildInventoryOnlyEntry("rafter", "qa", "auxiliary_release_qa_lane"),
            BuildInventoryOnlyEntry("pixefy", "qa", "auxiliary_visual_qa_lane")
        ];
        AppendInventoryOnlyLtdRows(entries);

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

    private ExecutiveAssistantCredentialEntry BuildIcanpreneurEntry()
    {
        const string tierKey = "CHUMMER_EA_ICANPRENEUR_TIER";
        const string emailKey = "CHUMMER_EA_ICANPRENEUR_EMAIL";
        const string passwordKey = "CHUMMER_EA_ICANPRENEUR_PASSWORD";
        const string baseUrlKey = "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL";
        const string fallbackEmailKey = "CHUMMER_EA_DEFAULT_EMAIL";
        const string fallbackPasswordKey = "CHUMMER_EA_DEFAULT_PASSWORD";

        string? email = GetValue(emailKey) ?? GetValue(fallbackEmailKey);
        bool loginConfigured = !string.IsNullOrWhiteSpace(email)
            && (!string.IsNullOrWhiteSpace(GetValue(passwordKey)) || !string.IsNullOrWhiteSpace(GetValue(fallbackPasswordKey)));
        bool baseUrlConfigured = !string.IsNullOrWhiteSpace(GetValue(baseUrlKey));
        string status = loginConfigured && baseUrlConfigured
            ? "bounded_discovery_interview_lane"
            : loginConfigured ? "login_only" : baseUrlConfigured ? "handoff_only" : "missing";

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "icanpreneur",
            Tier: GetValue(tierKey) ?? "3",
            EmailKey: emailKey,
            PasswordKey: passwordKey,
            PasswordAltKey: baseUrlKey,
            EmailMasked: MaskEmail(email),
            EmailConfigured: !string.IsNullOrWhiteSpace(email),
            PasswordConfigured: loginConfigured,
            PasswordAltConfigured: baseUrlConfigured,
            MirrorsDefault: true,
            Status: status);
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

    private ExecutiveAssistantCredentialEntry BuildMagicAiEntry()
    {
        const string tierKey = "CHUMMER_EA_MAGICAI_TIER";
        const string emailKey = "MAGICAI_ACCOUNT_*_EMAIL";
        const string passwordKey = "MAGICAI_ACCOUNT_*_PASSWORD";
        const string apiKey = "MAGICAI_ACCOUNT_*_API_KEY";

        MagicAiPoolState state = InspectMagicAiPool();
        string status = state.HasLogin
            ? state.HasApiKey ? "multi_account_pool_configured" : "login_only"
            : state.AnyDeclared ? "pool_declared_missing_credentials" : "missing";

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "magicai",
            Tier: GetValue(tierKey) ?? "4",
            EmailKey: emailKey,
            PasswordKey: passwordKey,
            PasswordAltKey: apiKey,
            EmailMasked: MaskEmail(state.FirstEmail),
            EmailConfigured: state.HasEmail,
            PasswordConfigured: state.HasPassword,
            PasswordAltConfigured: state.HasApiKey,
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

    private ExecutiveAssistantCredentialEntry BuildSubscribrEntry()
    {
        const string apiTokenKey = "SUBSCRIBR_API_TOKEN";
        const string webhookSecretKey = "SUBSCRIBR_WEBHOOK_SECRET";
        const string teamIdKey = "SUBSCRIBR_TEAM_ID";
        const string channelIdKey = "SUBSCRIBR_INTEGRATION_CHANNEL_ID";

        bool apiConfigured = !string.IsNullOrWhiteSpace(GetValue(apiTokenKey));
        bool webhookConfigured = !string.IsNullOrWhiteSpace(GetValue(webhookSecretKey));
        bool mapped = !string.IsNullOrWhiteSpace(GetValue(teamIdKey))
            && !string.IsNullOrWhiteSpace(GetValue(channelIdKey));

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "subscribr",
            Tier: "7",
            EmailKey: apiTokenKey,
            PasswordKey: webhookSecretKey,
            PasswordAltKey: channelIdKey,
            EmailMasked: null,
            EmailConfigured: apiConfigured,
            PasswordConfigured: webhookConfigured,
            PasswordAltConfigured: mapped,
            MirrorsDefault: false,
            Status: apiConfigured && mapped ? "tracked_video_script_preproduction_lane" : "missing");
    }

    private ExecutiveAssistantCredentialEntry BuildUnmixrEntry()
    {
        const string tierKey = "CHUMMER_EA_UNMIXR_TIER";
        const string emailKey = "CHUMMER_EA_UNMIXR_EMAIL";
        const string passwordKey = "CHUMMER_EA_UNMIXR_PASSWORD";
        const string apiKey = "UNMIXR_API_KEY";
        const string usernameKey = "UNMIXR_USERNAME";
        const string loginPasswordKey = "UNMIXR_PASSWORD";

        string? email = GetValue(emailKey);
        bool hasEaLogin = !string.IsNullOrWhiteSpace(email) && !string.IsNullOrWhiteSpace(GetValue(passwordKey));
        bool hasProviderLogin = !string.IsNullOrWhiteSpace(GetValue(usernameKey)) && !string.IsNullOrWhiteSpace(GetValue(loginPasswordKey));
        bool hasRuntimeVoice = HasUnmixrRuntimeConfiguration();
        bool hasRuntimeApi = HasUnmixrApiConfiguration();
        string status = hasRuntimeVoice
            ? "configured"
            : hasRuntimeApi ? "api_configured_voice_missing"
            : hasEaLogin || hasProviderLogin ? "login_only" : "missing";

        return new ExecutiveAssistantCredentialEntry(
            ToolId: "unmixr",
            Tier: GetValue(tierKey) ?? "4",
            EmailKey: emailKey,
            PasswordKey: passwordKey,
            PasswordAltKey: apiKey,
            EmailMasked: MaskEmail(email),
            EmailConfigured: !string.IsNullOrWhiteSpace(email),
            PasswordConfigured: !string.IsNullOrWhiteSpace(GetValue(passwordKey)),
            PasswordAltConfigured: hasRuntimeVoice,
            MirrorsDefault: true,
            Status: status);
    }

    private bool HasUnmixrRuntimeConfiguration()
    {
        if (!string.IsNullOrWhiteSpace(GetValue("UNMIXR_API_KEY")) && !string.IsNullOrWhiteSpace(GetValue("UNMIXR_VOICE_ID")))
        {
            return true;
        }

        foreach (string key in _configuration.AsEnumerable().Select(item => item.Key))
        {
            if (string.IsNullOrWhiteSpace(key))
            {
                continue;
            }

            Match match = Regex.Match(key, @"^UNMIXR_ACCOUNT_[A-Za-z0-9_]+_API_KEY$");
            if (!match.Success)
            {
                continue;
            }

            string account = key["UNMIXR_ACCOUNT_".Length..^"_API_KEY".Length];
            string voiceKey = $"UNMIXR_ACCOUNT_{account}_VOICE_ID";
            if (!string.IsNullOrWhiteSpace(GetValue(voiceKey)))
            {
                return true;
            }
        }

        return false;
    }

    private bool HasUnmixrApiConfiguration()
    {
        if (!string.IsNullOrWhiteSpace(GetValue("UNMIXR_API_KEY")))
        {
            return true;
        }

        foreach (string key in _configuration.AsEnumerable().Select(item => item.Key))
        {
            if (string.IsNullOrWhiteSpace(key))
            {
                continue;
            }

            Match match = Regex.Match(key, @"^UNMIXR_ACCOUNT_[A-Za-z0-9_]+_API_KEY$");
            if (match.Success && !string.IsNullOrWhiteSpace(GetValue(key)))
            {
                return true;
            }
        }

        return false;
    }

    private MagicAiPoolState InspectMagicAiPool()
    {
        string? firstEmail = null;
        bool hasEmail = false;
        bool hasPassword = false;
        bool hasLogin = false;
        bool hasApiKey = false;
        bool anyDeclared = false;

        void Consider(string? email, string? password, string? apiKey)
        {
            if (!string.IsNullOrWhiteSpace(email))
            {
                hasEmail = true;
                anyDeclared = true;
                firstEmail ??= email;
            }

            if (!string.IsNullOrWhiteSpace(password))
            {
                hasPassword = true;
                anyDeclared = true;
            }

            if (!string.IsNullOrWhiteSpace(apiKey))
            {
                hasApiKey = true;
                anyDeclared = true;
            }

            if (!string.IsNullOrWhiteSpace(email) && !string.IsNullOrWhiteSpace(password))
            {
                hasLogin = true;
            }
        }

        Consider(
            GetValue("CHUMMER_EA_MAGICAI_EMAIL"),
            GetValue("CHUMMER_EA_MAGICAI_PASSWORD"),
            GetValue("CHUMMER_EA_MAGICAI_API_KEY"));

        foreach (string key in _configuration.AsEnumerable().Select(item => item.Key).OrderBy(static item => item, StringComparer.Ordinal))
        {
            if (string.IsNullOrWhiteSpace(key))
            {
                continue;
            }

            Match match = Regex.Match(key, @"^MAGICAI_ACCOUNT_[A-Za-z0-9_]+_EMAIL$");
            if (!match.Success)
            {
                continue;
            }

            string prefix = key[..^"_EMAIL".Length];
            Consider(
                GetValue(key),
                GetValue($"{prefix}_PASSWORD"),
                GetValue($"{prefix}_API_KEY"));
        }

        return new MagicAiPoolState(
            FirstEmail: firstEmail,
            HasEmail: hasEmail,
            HasPassword: hasPassword,
            HasLogin: hasLogin,
            HasApiKey: hasApiKey,
            AnyDeclared: anyDeclared);
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

    private void AppendInventoryOnlyLtdRows(List<ExecutiveAssistantCredentialEntry> entries)
    {
        PathInfo? inventoryPath = ResolveLtdInventoryPath();
        if (inventoryPath is null)
        {
            return;
        }

        string text;
        try
        {
            text = File.ReadAllText(inventoryPath.Value.FullName);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return;
        }

        HashSet<string> existing = entries
            .Select(static entry => entry.ToolId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (Match match in Regex.Matches(text, @"^###\s+(?<toolId>.+?)\s*$", RegexOptions.CultureInvariant | RegexOptions.Multiline))
        {
            string toolId = match.Groups["toolId"].Value.Trim();
            if (string.IsNullOrWhiteSpace(toolId)
                || existing.Contains(toolId)
                || string.Equals(toolId, "default", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            entries.Add(BuildInventoryOnlyEntry(toolId, ReadLtdBlockValue(text, match.Index, "tier") ?? "inventory", ReadLtdBlockValue(text, match.Index, "status") ?? "inventory_only"));
            existing.Add(toolId);
        }
    }

    private PathInfo? ResolveLtdInventoryPath()
    {
        string? configured = GetValue("CHUMMER_EA_LTD_INVENTORY_PATH") ?? GetValue("EA:LtdInventoryPath");
        if (!string.IsNullOrWhiteSpace(configured) && File.Exists(configured))
        {
            return new PathInfo(configured);
        }

        DirectoryInfo? directory = new(AppContext.BaseDirectory);
        while (directory is not null)
        {
            string candidate = Path.Combine(directory.FullName, "ltds.md");
            if (File.Exists(candidate))
            {
                return new PathInfo(candidate);
            }

            directory = directory.Parent;
        }

        directory = new(Directory.GetCurrentDirectory());
        while (directory is not null)
        {
            string candidate = Path.Combine(directory.FullName, "ltds.md");
            if (File.Exists(candidate))
            {
                return new PathInfo(candidate);
            }

            directory = directory.Parent;
        }

        return null;
    }

    private static string? ReadLtdBlockValue(string text, int headingIndex, string key)
    {
        int nextHeading = text.IndexOf("\n### ", headingIndex + 1, StringComparison.Ordinal);
        string block = nextHeading >= 0 ? text[headingIndex..nextHeading] : text[headingIndex..];
        Match match = Regex.Match(
            block,
            @"^-\s+" + Regex.Escape(key) + @":\s+`(?<value>[^`]+)`\s*$",
            RegexOptions.CultureInvariant | RegexOptions.Multiline);
        return match.Success ? match.Groups["value"].Value.Trim() : null;
    }

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

internal readonly record struct MagicAiPoolState(
    string? FirstEmail,
    bool HasEmail,
    bool HasPassword,
    bool HasLogin,
    bool HasApiKey,
    bool AnyDeclared);

internal readonly record struct PathInfo(string FullName);
