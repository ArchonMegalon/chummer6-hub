using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class HubRuntimePathDefaultsTests
{
    [Fact]
    public void ResolveDataProtectionKeysPath_uses_explicit_configuration_when_present()
    {
        string configuredPath = Path.Combine(Path.GetTempPath(), "chummer-run-tests", Guid.NewGuid().ToString("N"), "keys");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DATA_PROTECTION_KEYS_PATH"] = configuredPath
            })
            .Build();

        string resolved = HubRuntimePathDefaults.ResolveDataProtectionKeysPath(configuration, new StubHostEnvironment());

        Assert.Equal(Path.GetFullPath(configuredPath), resolved);
    }

    [Fact]
    public void ResolveDataProtectionKeysPath_prefers_local_app_state_over_temp_when_available()
    {
        using Fixture fixture = new();
        IConfiguration configuration = new ConfigurationBuilder().Build();

        string resolved = HubRuntimePathDefaults.ResolveDataProtectionKeysPath(configuration, fixture.Environment);

        Assert.Equal(Path.Combine(fixture.ContentRoot, ".state", "data-protection-keys"), resolved);
        Assert.True(Directory.Exists(resolved));
    }

    [Fact]
    public void UsesTempFallback_returns_true_only_for_temp_root_paths()
    {
        string tempPath = Path.Combine(Path.GetTempPath(), "chummer-run-api", "data-protection-keys");
        string durablePath = Path.Combine(Path.GetTempPath(), "chummer-run-tests", Guid.NewGuid().ToString("N"), ".state", "data-protection-keys");

        Assert.True(HubRuntimePathDefaults.UsesTempFallback(Path.GetFullPath(tempPath)));
        Assert.False(HubRuntimePathDefaults.UsesTempFallback(Path.GetFullPath(durablePath)));
    }

    private sealed class Fixture : IDisposable
    {
        public Fixture()
        {
            ContentRoot = Path.Combine(Path.GetTempPath(), "chummer-run-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(ContentRoot);
            Environment = new StubHostEnvironment
            {
                ContentRootPath = ContentRoot
            };
        }

        public string ContentRoot { get; }

        public StubHostEnvironment Environment { get; }

        public void Dispose()
        {
            if (Directory.Exists(ContentRoot))
            {
                Directory.Delete(ContentRoot, recursive: true);
            }
        }
    }

    private sealed class StubHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = "Development";

        public string ApplicationName { get; set; } = "Chummer.Tests";

        public string ContentRootPath { get; set; } = Path.GetTempPath();

        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
