namespace Chummer.Run.Api.Services;

public static class WorkspaceNoticeSafety
{
    public static bool LooksLikeInternalWorkspaceLeak(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("closed workspace", StringComparison.OrdinalIgnoreCase)
            || value.Contains("workspace closed", StringComparison.OrdinalIgnoreCase)
            || value.Contains("workspace decision", StringComparison.OrdinalIgnoreCase)
            || value.Contains("workspace uuid", StringComparison.OrdinalIgnoreCase)
            || value.Contains("workspace id", StringComparison.OrdinalIgnoreCase)
            || value.Contains("uuid", StringComparison.OrdinalIgnoreCase)
            || System.Text.RegularExpressions.Regex.IsMatch(
                value,
                "\\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\b",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant);
    }
}
