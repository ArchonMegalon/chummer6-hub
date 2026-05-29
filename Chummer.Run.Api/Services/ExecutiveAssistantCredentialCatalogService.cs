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
                mirrorsDefault: true)
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

    private string BuildStatus(params string[] keys)
    {
        return keys.Length > 0
            && keys.All(key => !string.IsNullOrWhiteSpace(GetValue(key)))
            ? "configured"
            : "missing";
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
