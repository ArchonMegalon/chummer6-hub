using System.Text.Json;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

internal static class OriginDossierProviderAccountRegistry
{
    private static readonly IReadOnlySet<string> DisabledStatuses = new HashSet<string>(
        ["disabled", "revoked", "unavailable", "blocked", "retired"],
        StringComparer.OrdinalIgnoreCase);

    public static IReadOnlyList<string> ResolveAliases(
        IConfiguration configuration,
        string directEnvKey,
        string directConfigKey,
        string registryRole)
    {
        List<string> aliases = [];
        aliases.AddRange(SplitAliases(configuration[directEnvKey] ?? configuration[directConfigKey]));
        aliases.AddRange(ReadRegistryAliases(configuration, registryRole, enabledOnly: true));
        return aliases
            .Where(static alias => !string.IsNullOrWhiteSpace(alias))
            .Select(static alias => alias.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    public static IReadOnlyList<string> ResolveAllAliases(IConfiguration configuration, string directEnvKey, string directConfigKey)
    {
        List<string> aliases = [];
        aliases.AddRange(SplitAliases(configuration[directEnvKey] ?? configuration[directConfigKey]));
        aliases.AddRange(ReadRegistryAliases(configuration, "provider", enabledOnly: true));
        return aliases
            .Where(static alias => !string.IsNullOrWhiteSpace(alias))
            .Select(static alias => alias.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    public static bool HasConfiguredAliasSource(IConfiguration configuration, string directEnvKey, string directConfigKey)
        => !string.IsNullOrWhiteSpace(configuration[directEnvKey])
            || !string.IsNullOrWhiteSpace(configuration[directConfigKey])
            || !string.IsNullOrWhiteSpace(configuration["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"])
            || !string.IsNullOrWhiteSpace(configuration["OriginDossier:ProviderAccountRegistry"])
            || !string.IsNullOrWhiteSpace(configuration["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH"])
            || !string.IsNullOrWhiteSpace(configuration["OriginDossier:ProviderAccountRegistryPath"]);

    public static bool HasConfiguredAliasSource(
        IConfiguration configuration,
        string directEnvKey,
        string directConfigKey,
        string registryRole)
        => !string.IsNullOrWhiteSpace(configuration[directEnvKey])
            || !string.IsNullOrWhiteSpace(configuration[directConfigKey])
            || RegistrySourceIsInvalid(configuration)
            || RegistryContainsProviderForRole(configuration, registryRole)
            || ReadRegistryAliases(configuration, registryRole, enabledOnly: false).Any();

    public static IReadOnlyList<string> ResolveHosts(
        IConfiguration configuration,
        string directEnvKey,
        string directConfigKey,
        string registryRole)
    {
        List<string> hosts = [];
        hosts.AddRange(SplitAliases(configuration[directEnvKey] ?? configuration[directConfigKey]));
        hosts.AddRange(ReadRegistryHosts(configuration, registryRole, enabledOnly: true));
        return hosts
            .Select(NormalizeHost)
            .Where(static host => !string.IsNullOrWhiteSpace(host))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    public static bool HasConfiguredHostSource(
        IConfiguration configuration,
        string directEnvKey,
        string directConfigKey,
        string registryRole)
        => !string.IsNullOrWhiteSpace(configuration[directEnvKey])
            || !string.IsNullOrWhiteSpace(configuration[directConfigKey])
            || RegistrySourceIsInvalid(configuration)
            || RegistryContainsProviderForRole(configuration, registryRole)
            || ReadRegistryHosts(configuration, registryRole, enabledOnly: false).Any();

    private static IEnumerable<string> SplitAliases(string? configured)
        => string.IsNullOrWhiteSpace(configured)
            ? Array.Empty<string>()
            : configured
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Where(static alias => !string.IsNullOrWhiteSpace(alias));

    private static IEnumerable<string> ReadRegistryAliases(IConfiguration configuration, string registryRole, bool enabledOnly)
    {
        try
        {
            string? rawRegistry = ReadRawRegistry(configuration);
            if (string.IsNullOrWhiteSpace(rawRegistry))
            {
                return Array.Empty<string>();
            }

            using JsonDocument document = JsonDocument.Parse(rawRegistry);
            JsonElement accounts = ResolveAccountsArray(document.RootElement);
            if (accounts.ValueKind != JsonValueKind.Array)
            {
                return Array.Empty<string>();
            }

            List<string> aliases = [];
            foreach (JsonElement account in accounts.EnumerateArray())
            {
                if (account.ValueKind != JsonValueKind.Object
                    || (enabledOnly && !RegistryAccountIsEnabled(account)))
                {
                    continue;
                }

                if (!RegistryAccountMatchesRole(account, registryRole))
                {
                    continue;
                }

                string? alias = GetString(account, "accountAlias")
                    ?? GetString(account, "account_alias")
                    ?? GetString(account, "alias")
                    ?? GetString(account, "id");
                if (!string.IsNullOrWhiteSpace(alias))
                {
                    aliases.Add(alias.Trim());
                }
            }

            return aliases;
        }
        catch (IOException)
        {
            return Array.Empty<string>();
        }
        catch (UnauthorizedAccessException)
        {
            return Array.Empty<string>();
        }
        catch (JsonException)
        {
            return Array.Empty<string>();
        }
    }

    private static IEnumerable<string> ReadRegistryHosts(IConfiguration configuration, string registryRole, bool enabledOnly)
    {
        try
        {
            string? rawRegistry = ReadRawRegistry(configuration);
            if (string.IsNullOrWhiteSpace(rawRegistry))
            {
                return Array.Empty<string>();
            }

            using JsonDocument document = JsonDocument.Parse(rawRegistry);
            JsonElement accounts = ResolveAccountsArray(document.RootElement);
            if (accounts.ValueKind != JsonValueKind.Array)
            {
                return Array.Empty<string>();
            }

            List<string> hosts = [];
            foreach (JsonElement account in accounts.EnumerateArray())
            {
                if (account.ValueKind != JsonValueKind.Object
                    || (enabledOnly && !RegistryAccountIsEnabled(account))
                    || !RegistryAccountMatchesRole(account, registryRole))
                {
                    continue;
                }

                AddHost(hosts, GetString(account, "host"));
                AddHost(hosts, GetString(account, "shareHost"));
                AddHost(hosts, GetString(account, "share_host"));
                AddHost(hosts, GetString(account, "baseUrl"));
                AddHost(hosts, GetString(account, "base_url"));
                AddHost(hosts, GetString(account, "url"));
                AddHostArray(hosts, account, "hosts");
                AddHostArray(hosts, account, "trustedHosts");
                AddHostArray(hosts, account, "trusted_hosts");
            }

            return hosts;
        }
        catch (IOException)
        {
            return Array.Empty<string>();
        }
        catch (UnauthorizedAccessException)
        {
            return Array.Empty<string>();
        }
        catch (JsonException)
        {
            return Array.Empty<string>();
        }
    }

    private static string? ReadRawRegistry(IConfiguration configuration)
    {
        string? rawRegistry = configuration["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"]
            ?? configuration["OriginDossier:ProviderAccountRegistry"];
        string? registryPath = configuration["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH"]
            ?? configuration["OriginDossier:ProviderAccountRegistryPath"];

        if (string.IsNullOrWhiteSpace(rawRegistry) && !string.IsNullOrWhiteSpace(registryPath) && File.Exists(registryPath))
        {
            rawRegistry = File.ReadAllText(registryPath);
        }

        return rawRegistry;
    }

    private static bool RegistryContainsProviderForRole(IConfiguration configuration, string registryRole)
    {
        try
        {
            string? rawRegistry = ReadRawRegistry(configuration);
            if (string.IsNullOrWhiteSpace(rawRegistry))
            {
                return false;
            }

            using JsonDocument document = JsonDocument.Parse(rawRegistry);
            JsonElement accounts = ResolveAccountsArray(document.RootElement);
            if (accounts.ValueKind != JsonValueKind.Array)
            {
                return false;
            }

            foreach (JsonElement account in accounts.EnumerateArray())
            {
                if (account.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                string provider = GetString(account, "provider") ?? string.Empty;
                if (ProviderImpliesRegistryRole(provider, registryRole))
                {
                    return true;
                }
            }
        }
        catch (IOException)
        {
            return true;
        }
        catch (UnauthorizedAccessException)
        {
            return true;
        }
        catch (JsonException)
        {
            return true;
        }

        return false;
    }

    private static bool ProviderImpliesRegistryRole(string provider, string registryRole)
    {
        string normalizedProvider = provider.Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(normalizedProvider))
        {
            return false;
        }

        return registryRole.ToLowerInvariant() switch
        {
            "manuscript" => normalizedProvider.Contains("inkfluence", StringComparison.Ordinal)
                || normalizedProvider.Contains("youbooks", StringComparison.Ordinal)
                || normalizedProvider.Contains("first book", StringComparison.Ordinal)
                || normalizedProvider.Contains("firstbook", StringComparison.Ordinal),
            "audio" => normalizedProvider.Contains("inkfluence", StringComparison.Ordinal)
                || normalizedProvider.Contains("unmixr", StringComparison.Ordinal)
                || normalizedProvider.Contains("unmixer", StringComparison.Ordinal),
            "visual" => normalizedProvider.Contains("magicfit", StringComparison.Ordinal)
                || normalizedProvider.Contains("magic fit", StringComparison.Ordinal),
            "packaging" => normalizedProvider.Contains("fliplink", StringComparison.Ordinal)
                || normalizedProvider.Contains("runbook press", StringComparison.Ordinal)
                || normalizedProvider.Contains("book artifact", StringComparison.Ordinal)
                || normalizedProvider.Contains("packaging", StringComparison.Ordinal)
                || normalizedProvider.Contains("ebook", StringComparison.Ordinal)
                || normalizedProvider.Contains("epub", StringComparison.Ordinal)
                || normalizedProvider.Contains("pdf", StringComparison.Ordinal),
            "audiobookshelf" => normalizedProvider.Contains("audiobookshelf", StringComparison.Ordinal),
            "telegram" => normalizedProvider.Contains("telegram", StringComparison.Ordinal),
            _ => false,
        };
    }

    private static bool RegistrySourceIsInvalid(IConfiguration configuration)
    {
        string? rawRegistry = configuration["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"]
            ?? configuration["OriginDossier:ProviderAccountRegistry"];
        string? registryPath = configuration["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH"]
            ?? configuration["OriginDossier:ProviderAccountRegistryPath"];

        if (string.IsNullOrWhiteSpace(rawRegistry) && !string.IsNullOrWhiteSpace(registryPath))
        {
            if (!File.Exists(registryPath))
            {
                return true;
            }

            try
            {
                rawRegistry = File.ReadAllText(registryPath);
            }
            catch (IOException)
            {
                return true;
            }
            catch (UnauthorizedAccessException)
            {
                return true;
            }
        }

        if (string.IsNullOrWhiteSpace(rawRegistry))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(rawRegistry);
            return ResolveAccountsArray(document.RootElement).ValueKind != JsonValueKind.Array;
        }
        catch (JsonException)
        {
            return true;
        }
    }

    private static JsonElement ResolveAccountsArray(JsonElement root)
    {
        if (root.ValueKind == JsonValueKind.Array)
        {
            return root;
        }

        if (root.ValueKind != JsonValueKind.Object)
        {
            return default;
        }

        foreach (string property in new[] { "accounts", "providerAccounts", "bookAccounts", "originProviderAccounts" })
        {
            if (root.TryGetProperty(property, out JsonElement accounts) && accounts.ValueKind == JsonValueKind.Array)
            {
                return accounts;
            }
        }

        return default;
    }

    private static bool RegistryAccountIsEnabled(JsonElement account)
    {
        string? status = GetString(account, "status");
        return string.IsNullOrWhiteSpace(status) || !DisabledStatuses.Contains(status);
    }

    private static bool RegistryAccountMatchesRole(JsonElement account, string registryRole)
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase);
        AddStringToken(tokens, account, "role");
        AddStringToken(tokens, account, "accountRole");
        AddStringToken(tokens, account, "workspaceRole");
        AddStringToken(tokens, account, "lane");
        AddArrayTokens(tokens, account, "roles");
        AddArrayTokens(tokens, account, "capabilities");
        AddArrayTokens(tokens, account, "projectAffinity");
        AddArrayTokens(tokens, account, "project_affinity");

        if (tokens.Count == 0)
        {
            return string.Equals(registryRole, "provider", StringComparison.OrdinalIgnoreCase);
        }

        return registryRole.ToLowerInvariant() switch
        {
            "manuscript" => tokens.Overlaps(["manuscript", "authoring", "premium_authoring", "premium_guided_authoring", "scale_drafting", "drafting", "finishing", "narrative_editions", "runner_memoir"]),
            "audio" => tokens.Overlaps(["audio", "audiobook", "narration", "premium_narration", "audio_finishing", "origin_audio", "origin_audiobook"]),
            "visual" => tokens.Overlaps(["visual", "scene_render", "scene-render", "video_render", "video-render", "visuals", "magicfit", "origin_visual", "origin_visuals"]),
            "packaging" => tokens.Overlaps(["packaging", "package", "book_artifact", "book-artifact", "book_export", "book-export", "ebook", "epub", "pdf", "fliplink", "runbook_press", "runbook-press", "origin_packaging", "origin_package"]),
            "audiobookshelf" => tokens.Overlaps(["audiobookshelf", "ebook_shelf", "audiobook_shelf", "book_share", "share_host"]),
            "telegram" => tokens.Overlaps(["telegram", "telegram_delivery", "telegram_official_bot", "origin_delivery"]),
            "provider" => true,
            _ => tokens.Contains(registryRole),
        };
    }

    private static void AddStringToken(HashSet<string> tokens, JsonElement account, string propertyName)
    {
        string? value = GetString(account, propertyName);
        if (!string.IsNullOrWhiteSpace(value))
        {
            tokens.Add(value.Trim());
        }
    }

    private static void AddArrayTokens(HashSet<string> tokens, JsonElement account, string propertyName)
    {
        if (!account.TryGetProperty(propertyName, out JsonElement values) || values.ValueKind != JsonValueKind.Array)
        {
            return;
        }

        foreach (JsonElement value in values.EnumerateArray())
        {
            if (value.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(value.GetString()))
            {
                tokens.Add(value.GetString()!.Trim());
            }
        }
    }

    private static void AddHost(List<string> hosts, string? value)
    {
        string host = NormalizeHost(value);
        if (!string.IsNullOrWhiteSpace(host))
        {
            hosts.Add(host);
        }
    }

    private static void AddHostArray(List<string> hosts, JsonElement account, string propertyName)
    {
        if (!account.TryGetProperty(propertyName, out JsonElement values) || values.ValueKind != JsonValueKind.Array)
        {
            return;
        }

        foreach (JsonElement value in values.EnumerateArray())
        {
            if (value.ValueKind == JsonValueKind.String)
            {
                AddHost(hosts, value.GetString());
            }
        }
    }

    private static string NormalizeHost(string? value)
    {
        string text = value?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(text))
        {
            return string.Empty;
        }

        if (Uri.TryCreate(text, UriKind.Absolute, out Uri? uri))
        {
            return uri.Host.TrimEnd('.').ToLowerInvariant();
        }

        return text
            .TrimEnd('/')
            .TrimEnd('.')
            .ToLowerInvariant();
    }

    private static string? GetString(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out JsonElement value) || value.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        return value.GetString();
    }
}
