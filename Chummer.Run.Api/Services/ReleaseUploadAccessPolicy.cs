namespace Chummer.Run.Api.Services;

public static class ReleaseUploadAccessPolicy
{
    public const string AllowedEmail = "tibor.girschele@gmail.com";
    private const string ReleaseUploadAllowedEmailsConfigurationKey = "CHUMMER_RELEASE_UPLOAD_ALLOWED_EMAILS";
    private static readonly string[] PrivilegedIdentityRoles = ["operator", "admin"];

    public static bool CanAccess(AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            return false;
        }

        return CanAccess(subject.Email)
            || (subject.Roles?.Any(role => !string.IsNullOrWhiteSpace(role)
                    && PrivilegedIdentityRoles.Contains(
                        role.Trim(),
                        StringComparer.OrdinalIgnoreCase))
                ?? false);
    }

    public static bool CanAccess(string? email)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            return false;
        }

        var normalizedEmail = email.Trim();
        var configuredAllowedEmails = GetConfiguredEmails();
        if (configuredAllowedEmails.Length == 0)
        {
            return string.Equals(normalizedEmail, AllowedEmail, StringComparison.OrdinalIgnoreCase);
        }

        return configuredAllowedEmails.Any(allowed =>
            string.Equals(normalizedEmail, allowed, StringComparison.OrdinalIgnoreCase));
    }

    private static string[] GetConfiguredEmails()
        => (Environment.GetEnvironmentVariable(ReleaseUploadAllowedEmailsConfigurationKey) ?? string.Empty)
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}
