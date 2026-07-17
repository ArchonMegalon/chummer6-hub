using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PersonalizedInstallScriptSecurityTests : IDisposable
{
    private readonly string _root = Path.Combine(
        Path.GetTempPath(),
        "personalized-install-security-tests",
        Guid.NewGuid().ToString("N"));

    public PersonalizedInstallScriptSecurityTests() => Directory.CreateDirectory(_root);

    [Fact]
    public void Per_principal_pending_limit_is_bounded_and_secret_safe()
    {
        IConfiguration configuration = Configuration(maxPending: 2, maxHourly: 3);
        using InstallLinkingStore store = Store(configuration);
        var service = new PersonalizedInstallScriptService(store, configuration);

        service.IssueMacScript("artifact-one", null, "user-one", "subject-one", "script-one");
        service.IssueMacScript("artifact-two", null, "user-one", "subject-one", "script-two");

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            service.IssueMacScript("artifact-three", null, "user-one", "subject-one", "script-secret-three"));

        Assert.Equal("Personalized install script issuance limit reached.", failure.Message);
        Assert.Equal(2, store.PersonalizedInstallScriptsById.Count);
        Assert.DoesNotContain(
            store.PersonalizedInstallScriptsById.Values,
            static item => string.Equals(item.RenderedScript, "script-secret-three", StringComparison.Ordinal));
    }

    [Fact]
    public void Expiration_clears_rendered_script_from_live_and_durable_state()
    {
        IConfiguration configuration = Configuration(maxPending: 4, maxHourly: 8);
        using InstallLinkingStore store = Store(configuration);
        var service = new PersonalizedInstallScriptService(store, configuration);
        PersonalizedInstallScriptIssueResult issued = service.IssueMacScript(
            "artifact-one",
            null,
            "user-one",
            "subject-one",
            "rendered-script-secret");
        lock (store.Gate)
        {
            store.PersonalizedInstallScriptsById[issued.ScriptId] = issued.Link with
            {
                IssuedAtUtc = DateTimeOffset.UtcNow.AddDays(-1),
                ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1)
            };
            store.PersistLocked();
        }

        PersonalizedInstallScriptConsumeResult result = service.Resolve(issued.ScriptId);

        Assert.Equal(PersonalizedInstallScriptConsumeStatus.Expired, result.Status);
        Assert.Null(store.PersonalizedInstallScriptsById[issued.ScriptId].RenderedScript);
        Assert.Null(result.Link?.RenderedScript);
    }

    [Fact]
    public void Oversized_identifier_is_rejected_before_mutation_without_poisoning_store()
    {
        IConfiguration configuration = Configuration(maxPending: 4, maxHourly: 8);
        using InstallLinkingStore store = Store(configuration);
        var service = new PersonalizedInstallScriptService(store, configuration);

        Assert.Throws<ArgumentException>(() =>
            service.IssueMacScript(new string('a', 257), null, "user-one", "subject-one", "secret-script"));

        Assert.True(store.IsHealthy);
        Assert.Empty(store.PersonalizedInstallScriptsById);
        PersonalizedInstallScriptIssueResult valid = service.IssueMacScript(
            "artifact-one",
            null,
            "user-one",
            "subject-one",
            "safe-script");
        Assert.Equal("artifact-one", valid.Link.ArtifactId);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Tampered_rendered_script_fails_closed_for_legacy_and_digest_routes(bool includeRouteDigest)
    {
        IConfiguration configuration = Configuration(maxPending: 4, maxHourly: 8);
        using InstallLinkingStore store = Store(configuration);
        var service = new PersonalizedInstallScriptService(store, configuration);
        PersonalizedInstallScriptIssueResult issued = service.IssueMacScript(
            "artifact-one",
            null,
            "user-one",
            "subject-one",
            "expected-script");
        lock (store.Gate)
        {
            store.PersonalizedInstallScriptsById[issued.ScriptId] = issued.Link with
            {
                RenderedScript = "tampered-script"
            };
            store.PersistLocked();
        }

        PersonalizedInstallScriptConsumeResult result = service.Resolve(
            issued.ScriptId,
            includeRouteDigest ? issued.Link.RenderedScriptSha256 : null);

        Assert.Equal(PersonalizedInstallScriptConsumeStatus.DigestMismatch, result.Status);
        Assert.Null(result.Link);
        Assert.Equal("tampered-script", store.PersonalizedInstallScriptsById[issued.ScriptId].RenderedScript);
    }

    private IConfiguration Configuration(int maxPending, int maxHourly)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json"),
                ["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_MAX_PENDING_PER_PRINCIPAL"] = maxPending.ToString(),
                ["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_MAX_ISSUED_PER_PRINCIPAL_PER_HOUR"] = maxHourly.ToString()
            })
            .Build();

    private InstallLinkingStore Store(IConfiguration configuration)
        => new(
            configuration,
            DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys"))),
            NullLogger<InstallLinkingStore>.Instance);

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }
}
