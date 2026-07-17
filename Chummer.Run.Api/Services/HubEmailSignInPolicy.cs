using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

internal sealed record HubEmailSignInAvailability(
    bool Enabled,
    string DeliveryMode,
    string PreviewNote);

internal static class HubEmailSignInPolicy
{
    public static HubEmailSignInAvailability Resolve(IConfiguration? configuration)
    {
        if (!ResolveBool(ReadOptionalValue(configuration, "IDENTITY_EMAIL_START_ENABLED"), defaultValue: false))
        {
            return new HubEmailSignInAvailability(
                Enabled: false,
                DeliveryMode: "email_start_disabled",
                PreviewNote: "Email sign-in is disabled on this host.");
        }

        if (TryGetPausePreviewNote(configuration, out string previewNote))
        {
            return new HubEmailSignInAvailability(
                Enabled: false,
                DeliveryMode: "email_start_paused",
                PreviewNote: previewNote);
        }

        return new HubEmailSignInAvailability(
            Enabled: true,
            DeliveryMode: "email_start_enabled",
            PreviewNote: string.Empty);
    }

    private static bool TryGetPausePreviewNote(IConfiguration? configuration, out string previewNote)
    {
        previewNote = "Email sign-in is paused on this host.";

        try
        {
            string pauseFlagPath = ResolvePauseFlagPath(configuration);
            if (!File.Exists(pauseFlagPath))
            {
                return false;
            }

            previewNote = TrimToNull(File.ReadAllText(pauseFlagPath)) ?? previewNote;
            return true;
        }
        catch
        {
            return true;
        }
    }

    private static string ResolvePauseFlagPath(IConfiguration? configuration)
    {
        string? configuredPauseFlag = ReadOptionalValue(configuration, "CHUMMER_AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG");
        if (configuredPauseFlag is not null)
        {
            return Path.GetFullPath(configuredPauseFlag);
        }

        string? configuredStorePath = ReadOptionalValue(configuration, "CHUMMER_IDENTITY_STORE_PATH");
        if (configuredStorePath is not null)
        {
            string fullStorePath = Path.GetFullPath(configuredStorePath);
            string? storeDirectory = Path.GetDirectoryName(fullStorePath);
            if (!string.IsNullOrWhiteSpace(storeDirectory))
            {
                return Path.Combine(storeDirectory, "auth_signin_automation_paused.flag");
            }
        }

        string? configuredStateRoot = ReadOptionalValue(configuration, "CHUMMER_IDENTITY_STATE_ROOT")
            ?? ReadOptionalValue(configuration, "CHUMMER_RUNTIME_STATE_ROOT");
        if (configuredStateRoot is not null)
        {
            return Path.Combine(
                Path.GetFullPath(configuredStateRoot),
                "identity",
                "auth_signin_automation_paused.flag");
        }

        string? xdgStateHome = Environment.GetEnvironmentVariable("XDG_STATE_HOME");
        if (!string.IsNullOrWhiteSpace(xdgStateHome))
        {
            return Path.Combine(
                Path.GetFullPath(xdgStateHome),
                "chummer-run",
                "identity",
                "auth_signin_automation_paused.flag");
        }

        string localData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (!string.IsNullOrWhiteSpace(localData))
        {
            return Path.Combine(
                Path.GetFullPath(localData),
                "Chummer",
                "Run",
                "identity",
                "auth_signin_automation_paused.flag");
        }

        return Path.Combine(
            AppContext.BaseDirectory,
            ".chummer-state",
            "identity",
            "auth_signin_automation_paused.flag");
    }

    private static string? ReadOptionalValue(IConfiguration? configuration, string key)
    {
        string? environmentValue = TrimToNull(Environment.GetEnvironmentVariable(key));
        if (environmentValue is not null)
        {
            return environmentValue;
        }

        return TrimToNull(configuration?[key]);
    }

    private static string? TrimToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static bool ResolveBool(string? value, bool defaultValue)
        => bool.TryParse(value, out bool parsed) ? parsed : defaultValue;
}
