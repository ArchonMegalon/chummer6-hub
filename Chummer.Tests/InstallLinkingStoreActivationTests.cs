using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingStoreActivationTests
{
    [Fact]
    public void Production_required_store_enforces_external_rollback_readiness()
    {
        if (!LinuxSecureFile.IsSupportedPlatform)
        {
            return;
        }

        using Fixture fixture = new(environmentName: Environments.Production);
        using InstallLinkingStoreActivation activation = fixture.CreateActivation();

        InstallLinkingStoreReadiness readiness = activation.Evaluate();
        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(activation.GetRequiredStore);

        Assert.False(readiness.Ready);
        Assert.Equal("external_rollback_authority_unimplemented", readiness.Code);
        Assert.Equal("Install-linking durable store is unavailable.", failure.Message);
    }

    [Theory]
    [InlineData("/api/v1/install-linking/summary")]
    [InlineData("/account/access/install-link")]
    [InlineData("/downloads/install/artifact")]
    [InlineData("/install-0123456789abcdef01234567.sh")]
    public async Task Unready_durable_install_link_routes_return_fixed_503(string path)
    {
        bool nextInvoked = false;
        var middleware = new InstallLinkingRequestAdmissionMiddleware(_ =>
        {
            nextInvoked = true;
            return Task.CompletedTask;
        });
        var context = new DefaultHttpContext();
        context.Request.Path = path;
        context.Response.Body = new MemoryStream();

        await middleware.InvokeAsync(
            context,
            new StubReadinessProbe(new InstallLinkingStoreReadiness(false, "secret-internal-code")));

        context.Response.Body.Position = 0;
        string body = await new StreamReader(context.Response.Body).ReadToEndAsync();
        Assert.False(nextInvoked);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode);
        Assert.Contains("Install-linking is temporarily unavailable.", body, StringComparison.Ordinal);
        Assert.DoesNotContain("secret-internal-code", body, StringComparison.Ordinal);
        Assert.Equal("private, no-store, max-age=0", context.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task Anonymous_compatibility_download_bypasses_durable_admission_gate()
    {
        bool nextInvoked = false;
        var middleware = new InstallLinkingRequestAdmissionMiddleware(_ =>
        {
            nextInvoked = true;
            return Task.CompletedTask;
        });
        var context = new DefaultHttpContext();
        context.Request.Path = "/downloads/get/guest-readable-artifact";

        await middleware.InvokeAsync(
            context,
            new StubReadinessProbe(new InstallLinkingStoreReadiness(false, "store_unready")));

        Assert.True(nextInvoked);
    }

    [Fact]
    public void Repeated_readiness_and_resolution_reuse_one_cached_failed_activation()
    {
        using Fixture fixture = new(environmentName: Environments.Development);
        File.WriteAllText(
            fixture.StorePath,
            "{\"format\":\"chummer.install-linking-store\",\"version\":1,\"protectedPayload\":\"not-protected\"}");
        using InstallLinkingStoreActivation activation = fixture.CreateActivation();

        InstallLinkingStoreReadiness first = activation.Evaluate();
        InstallLinkingStoreReadiness second = activation.Evaluate();
        InvalidOperationException resolutionOne = Assert.Throws<InvalidOperationException>(activation.GetRequiredStore);
        InvalidOperationException resolutionTwo = Assert.Throws<InvalidOperationException>(activation.GetRequiredStore);

        Assert.Equal(new InstallLinkingStoreReadiness(false, "store_activation_failed"), first);
        Assert.Equal(first, second);
        Assert.Equal("Install-linking durable store is unavailable.", resolutionOne.Message);
        Assert.Equal(resolutionOne.Message, resolutionTwo.Message);
        Assert.Single(Directory.GetFiles(fixture.Root, ".install-linking-store.json.quarantine-*.json"));
    }

    [Fact]
    public void Production_missing_key_encryptor_fails_before_store_or_quarantine_is_touched()
    {
        using Fixture fixture = new(environmentName: Environments.Production);
        const string source = "legacy-secret-source";
        File.WriteAllText(fixture.StorePath, source);
        using InstallLinkingStoreActivation activation = fixture.CreateActivation(
            new DataProtectionKeyProtectionStatus(false, "data_protection_key_encryptor_missing"));

        InstallLinkingStoreReadiness readiness = activation.Evaluate();

        Assert.Equal("data_protection_key_encryptor_missing", readiness.Code);
        Assert.False(readiness.Ready);
        Assert.Equal(source, File.ReadAllText(fixture.StorePath));
        Assert.Empty(Directory.GetFiles(fixture.Root, ".install-linking-store.json.quarantine-*.json"));
    }

    [Fact]
    public void Production_missing_explicit_store_path_is_cached_as_fixed_readiness_failure()
    {
        using Fixture fixture = new(environmentName: Environments.Production);
        fixture.Configuration["CHUMMER_INSTALL_LINKING_STORE_PATH"] = null;
        using InstallLinkingStoreActivation activation = fixture.CreateActivation();

        InstallLinkingStoreReadiness first = activation.Evaluate();
        InstallLinkingStoreReadiness second = activation.Evaluate();
        InvalidOperationException resolution = Assert.Throws<InvalidOperationException>(activation.GetRequiredStore);

        Assert.Equal(new InstallLinkingStoreReadiness(false, "store_path_not_explicit"), first);
        Assert.Equal(first, second);
        Assert.Equal("Install-linking durable store is unavailable.", resolution.Message);
        Assert.Empty(Directory.GetFiles(fixture.Root, "*.writer.lock", SearchOption.AllDirectories));
        Assert.Empty(Directory.GetFiles(fixture.Root, "*.quarantine-*.json", SearchOption.AllDirectories));
    }

    private sealed class Fixture : IDisposable
    {
        private readonly TestHostEnvironment _environment;
        private readonly IDataProtectionProvider _dataProtection;

        public Fixture(string environmentName)
        {
            Root = Path.Combine(Path.GetTempPath(), "install-linking-activation-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Root);
            StorePath = Path.Combine(Root, "install-linking-store.json");
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = StorePath,
                    ["ASPNETCORE_ENVIRONMENT"] = environmentName
                })
                .Build();
            _environment = new TestHostEnvironment
            {
                EnvironmentName = environmentName,
                ContentRootPath = Root
            };
            _dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(Root, "keys")));
        }

        public string Root { get; }
        public string StorePath { get; }
        public IConfiguration Configuration { get; }

        public InstallLinkingStoreActivation CreateActivation(DataProtectionKeyProtectionStatus? keyProtection = null)
            => new(
                Configuration,
                _dataProtection,
                _environment,
                LoggerFactory.Create(static _ => { }),
                [new UnavailableInstallLinkingRollbackAuthorityReadinessProbe()],
                keyProtection ?? new DataProtectionKeyProtectionStatus(true, "test_key_encryptor"));

        public void Dispose()
        {
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }
    }

    private sealed class TestHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Development;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = string.Empty;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private sealed class StubReadinessProbe(InstallLinkingStoreReadiness readiness)
        : IInstallLinkingStoreReadinessProbe
    {
        public InstallLinkingStoreReadiness Evaluate() => readiness;
    }
}
