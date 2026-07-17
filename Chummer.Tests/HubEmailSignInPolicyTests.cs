using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HubEmailSignInPolicyTests
{
    [Fact]
    public void Resolve_defaults_to_disabled_when_email_start_is_not_configured()
    {
        IConfiguration configuration = new ConfigurationBuilder().Build();

        HubEmailSignInAvailability availability = HubEmailSignInPolicy.Resolve(configuration);

        Assert.False(availability.Enabled);
        Assert.Equal("email_start_disabled", availability.DeliveryMode);
        Assert.Equal("Email sign-in is disabled on this host.", availability.PreviewNote);
    }

    [Fact]
    public void Resolve_uses_environment_email_start_flag_when_configuration_is_missing()
    {
        const string key = "IDENTITY_EMAIL_START_ENABLED";
        string? original = Environment.GetEnvironmentVariable(key);
        Environment.SetEnvironmentVariable(key, "false");

        try
        {
            IConfiguration configuration = new ConfigurationBuilder().Build();

            HubEmailSignInAvailability availability = HubEmailSignInPolicy.Resolve(configuration);

            Assert.False(availability.Enabled);
            Assert.Equal("email_start_disabled", availability.DeliveryMode);
            Assert.Equal("Email sign-in is disabled on this host.", availability.PreviewNote);
        }
        finally
        {
            Environment.SetEnvironmentVariable(key, original);
        }
    }

    [Fact]
    public void Resolve_uses_pause_flag_when_email_start_is_enabled()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-email-signin-policy", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string pauseFlagPath = Path.Combine(tempRoot, "auth_signin_automation_paused.flag");
        File.WriteAllText(pauseFlagPath, "paused by user request");

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["IDENTITY_EMAIL_START_ENABLED"] = "true",
                    ["CHUMMER_AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG"] = pauseFlagPath
                })
                .Build();

            HubEmailSignInAvailability availability = HubEmailSignInPolicy.Resolve(configuration);

            Assert.False(availability.Enabled);
            Assert.Equal("email_start_paused", availability.DeliveryMode);
            Assert.Equal("paused by user request", availability.PreviewNote);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }
}
