using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api.Services;

public static class HubRuntimePathDefaults
{
    public static bool IsExplicitlyConfigured(IConfiguration configuration)
        => !string.IsNullOrWhiteSpace(configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]?.Trim());

    public static string ResolveDataProtectionKeysPath(IConfiguration configuration, IHostEnvironment environment)
    {
        var configured = configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]?.Trim();
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        foreach (var candidate in BuildDefaultCandidates(environment))
        {
            if (TryPrepareDirectory(candidate))
            {
                return Path.GetFullPath(candidate);
            }
        }

        return Path.GetFullPath(Path.Combine(Path.GetTempPath(), "chummer-run-api", "data-protection-keys"));
    }

    public static bool UsesTempFallback(string resolvedPath)
        => string.Equals(
            Path.GetFullPath(resolvedPath),
            Path.GetFullPath(Path.Combine(Path.GetTempPath(), "chummer-run-api", "data-protection-keys")),
            StringComparison.Ordinal);

    private static IEnumerable<string> BuildDefaultCandidates(IHostEnvironment environment)
    {
        if (Directory.Exists("/app")
            || AppContext.BaseDirectory.StartsWith("/app/", StringComparison.Ordinal)
            || string.Equals(AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar), "/app", StringComparison.Ordinal))
        {
            yield return "/app/state/data-protection-keys";
        }

        if (!string.IsNullOrWhiteSpace(environment.ContentRootPath))
        {
            yield return Path.Combine(environment.ContentRootPath, ".state", "data-protection-keys");
        }

        yield return Path.Combine(Path.GetTempPath(), "chummer-run-api", "data-protection-keys");
    }

    private static bool TryPrepareDirectory(string path)
    {
        try
        {
            Directory.CreateDirectory(path);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
