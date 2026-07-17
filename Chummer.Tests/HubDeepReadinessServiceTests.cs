using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class HubDeepReadinessServiceTests
{
    [Fact]
    public void Evaluate_keeps_legacy_serving_but_never_claims_atomic_publication_readiness()
    {
        using Fixture fixture = new();
        fixture.WritePublishedManifest();

        HubDeepReadinessReport report = fixture.CreateService().Evaluate();

        Assert.True(report.Ready);
        Assert.True(report.ServingReady);
        Assert.False(report.PublicationReady);
        Assert.True(report.PublicationChecksConfigured);
        Assert.Equal("pass", report.Status);
        Assert.All(report.Checks, static check => Assert.True(check.Passed));
        Assert.Equal("legacy", report.ReleaseShelf.Mode);
        Assert.Null(report.ReleaseShelf.GenerationId);
        Assert.Contains(
            report.ReleaseShelf.PublicationChecks,
            static check => check.Code == "layout_v1_activation_required");
    }

    [Fact]
    public void Evaluate_fails_when_canonical_manifest_is_missing()
    {
        using Fixture fixture = new();

        HubDeepReadinessReport report = fixture.CreateService().Evaluate();

        Assert.False(report.Ready);
        HubDeepReadinessCheck check = Assert.Single(
            report.Checks,
            static item => item.Name == "canonical_release_manifest");
        Assert.Equal("canonical_manifest_missing", check.Code);
    }

    [Fact]
    public void Evaluate_fails_when_canonical_manifest_is_malformed()
    {
        using Fixture fixture = new();
        File.WriteAllText(fixture.ManifestPath, "{not-json");

        HubDeepReadinessReport report = fixture.CreateService().Evaluate();

        Assert.False(report.Ready);
        HubDeepReadinessCheck check = Assert.Single(
            report.Checks,
            static item => item.Name == "canonical_release_manifest");
        Assert.Equal("canonical_manifest_invalid", check.Code);
    }

    [Fact]
    public void Evaluate_fails_when_durable_storage_cannot_be_opened_as_a_directory()
    {
        using Fixture fixture = new();
        fixture.WritePublishedManifest();
        File.WriteAllText(fixture.StoragePath, "not-a-directory");

        HubDeepReadinessReport report = fixture.CreateService().Evaluate();

        Assert.False(report.Ready);
        HubDeepReadinessCheck check = Assert.Single(
            report.Checks,
            static item => item.Name == "data_protection_storage");
        Assert.Equal("storage_probe_failed", check.Code);
    }

    [Fact]
    public void Evaluate_reports_cached_install_linking_store_failure_without_exception_detail()
    {
        using Fixture fixture = new();
        fixture.WritePublishedManifest();

        HubDeepReadinessReport report = fixture.CreateService(
            installLinkingStore: new StubInstallLinkingReadinessProbe(
                new InstallLinkingStoreReadiness(false, "store_activation_failed"))).Evaluate();

        Assert.False(report.Ready);
        Assert.True(report.ServingReady);
        Assert.False(report.PublicationReady);
        HubDeepReadinessCheck check = Assert.Single(
            report.Checks,
            static item => item.Name == "install_linking_store");
        Assert.Equal("store_activation_failed", check.Code);
        ReleaseShelfPublicationReadinessCheck publicationCheck = Assert.Single(
            report.ReleaseShelf.PublicationChecks,
            static item => item.Name == "install_linking_store");
        Assert.False(publicationCheck.Ready);
        Assert.Equal("store_activation_failed", publicationCheck.Code);
        Assert.DoesNotContain(fixture.Root, JsonSerializer.Serialize(report), StringComparison.Ordinal);
    }

    [Fact]
    public async Task EvaluatePublicationReadiness_fails_closed_when_install_linking_store_is_not_ready()
    {
        using Fixture fixture = new();
        HubDeepReadinessService service = fixture.CreateService(
            ReadyPublicationProbes(),
            ResolveSharedFixtureRoot(),
            new StubInstallLinkingReadinessProbe(
                new InstallLinkingStoreReadiness(false, "store_activation_failed")));

        ReleaseShelfPublicationReadinessState publication =
            await service.EvaluatePublicationReadinessAsync();
        HubDeepReadinessReport report = service.Evaluate();

        Assert.False(report.Ready);
        Assert.True(report.ServingReady);
        Assert.False(report.PublicationReady);
        Assert.False(publication.Ready);
        ReleaseShelfPublicationReadinessCheck check = Assert.Single(
            publication.Checks,
            static item => item.Name == "install_linking_store");
        Assert.False(check.Ready);
        Assert.Equal("store_activation_failed", check.Code);
    }

    [Fact]
    public void Evaluate_fails_closed_when_layout_marker_has_no_pointer()
    {
        using Fixture fixture = new();
        fixture.WritePublishedManifest();
        File.WriteAllText(
            Path.Combine(fixture.Root, ReleaseShelfGenerationStore.LayoutMarkerFileName),
            "layout-v1\n");

        HubDeepReadinessReport report = fixture.CreateService().Evaluate();

        Assert.False(report.Ready);
        Assert.False(report.ServingReady);
        Assert.False(report.PublicationReady);
        Assert.True(report.PublicationChecksConfigured);
        HubDeepReadinessCheck check = Assert.Single(
            report.Checks,
            static item => item.Name == "release_shelf");
        Assert.Equal("release_shelf_invalid", check.Code);
        Assert.Equal("unavailable", report.ReleaseShelf.Mode);
        Assert.Null(report.ReleaseShelf.GenerationId);
        Assert.DoesNotContain(fixture.Root, JsonSerializer.Serialize(report), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Evaluate_keeps_serving_ready_when_publication_probe_blocks()
    {
        using Fixture fixture = new();
        string shelfRoot = ResolveSharedFixtureRoot();
        IReleaseShelfPublicationReadinessProbe[] probes =
        [
            new StubPublicationProbe(
                HubDeepReadinessService.ActivationProtocolProbeName,
                new ReleaseShelfPublicationReadinessProbeResult(false, "activation_unresolved")),
            ReadyPublicationProbe(HubDeepReadinessService.StorageAdmissionProbeName)
        ];

        HubDeepReadinessService service = fixture.CreateService(probes, shelfRoot);
        ReleaseShelfPublicationReadinessState publication =
            await service.EvaluatePublicationReadinessAsync();
        HubDeepReadinessReport report = service.Evaluate();

        Assert.True(report.Ready);
        Assert.True(report.ServingReady);
        Assert.False(report.PublicationReady);
        Assert.True(report.PublicationChecksConfigured);
        Assert.False(publication.Ready);
        ReleaseShelfPublicationReadinessCheck check = Assert.Single(
            report.ReleaseShelf.PublicationChecks,
            static item => item.Name == HubDeepReadinessService.ActivationProtocolProbeName);
        Assert.False(check.Ready);
        Assert.Equal("activation_unresolved", check.Code);
    }

    [Fact]
    public async Task Evaluate_fails_publication_probe_without_leaking_exception_detail()
    {
        using Fixture fixture = new();
        string shelfRoot = ResolveSharedFixtureRoot();
        IReleaseShelfPublicationReadinessProbe[] probes =
        [
            ReadyPublicationProbe(HubDeepReadinessService.ActivationProtocolProbeName),
            new ThrowingPublicationProbe(
                HubDeepReadinessService.StorageAdmissionProbeName,
                $"secret-path:{fixture.Root}")
        ];

        HubDeepReadinessService service = fixture.CreateService(probes, shelfRoot);
        await service.EvaluatePublicationReadinessAsync();
        HubDeepReadinessReport report = service.Evaluate();

        Assert.True(report.ServingReady);
        Assert.False(report.PublicationReady);
        ReleaseShelfPublicationReadinessCheck check = Assert.Single(
            report.ReleaseShelf.PublicationChecks,
            static item => item.Name == HubDeepReadinessService.StorageAdmissionProbeName);
        Assert.Equal("probe_failed", check.Code);
        Assert.DoesNotContain(fixture.Root, JsonSerializer.Serialize(report), StringComparison.Ordinal);
    }

    [Fact]
    public void Evaluate_never_claims_publication_ready_without_required_probes()
    {
        using Fixture fixture = new();
        string shelfRoot = ResolveSharedFixtureRoot();

        HubDeepReadinessReport report = fixture.CreateService([], shelfRoot).Evaluate();

        Assert.True(report.Ready);
        Assert.True(report.ServingReady);
        Assert.False(report.PublicationChecksConfigured);
        Assert.False(report.PublicationReady);
        ReleaseShelfPublicationReadinessCheck check = Assert.Single(
            report.ReleaseShelf.PublicationChecks,
            static item => item.Name == "publication_probe_contract");
        Assert.Equal("required_probes_missing", check.Code);
    }

    [Fact]
    public async Task Layout_v1_shelf_is_serving_ready_and_uses_cached_bounded_publication_assessment()
    {
        using Fixture fixture = new();
        HubDeepReadinessService service = fixture.CreateService(
            ReadyPublicationProbes(),
            ResolveSharedFixtureRoot());

        HubDeepReadinessReport before = service.Evaluate();
        ReleaseShelfPublicationReadinessState publication =
            await service.EvaluatePublicationReadinessAsync();
        HubDeepReadinessReport after = service.Evaluate();

        Assert.True(before.Ready);
        Assert.True(before.ServingReady);
        Assert.False(before.PublicationReady);
        Assert.Equal("publication_checks_pending", before.ReleaseShelf.PublicationChecks.Single(
            static check => !check.Ready).Code);
        Assert.True(publication.Ready);
        Assert.True(after.Ready);
        Assert.True(after.ServingReady);
        Assert.True(after.PublicationReady);
        Assert.Equal("generation", after.ReleaseShelf.Mode);
        Assert.Equal("gen-20260715T160912Z-0123456789ab", after.ReleaseShelf.GenerationId);
        Assert.Equal("activation-fixture-20260715-160915", after.ReleaseShelf.ActivationReceiptId);
        Assert.Equal(
            "47c07b4a56faf5213f2bcab7707b0330d74821311bfa30683bcddca54c795a83",
            after.ReleaseShelf.InventoryDigest);
    }

    [Fact]
    public void Layout_v1_corruption_fails_serving_without_leaking_paths()
    {
        using Fixture fixture = new();
        string shelfRoot = Path.Combine(fixture.Root, "corrupt-shelf");
        CopyDirectory(ResolveSharedFixtureRoot(), shelfRoot);
        File.AppendAllText(
            Path.Combine(
                shelfRoot,
                "generations",
                "gen-20260715T160912Z-0123456789ab",
                "files",
                "chummer-fixture.dmg"),
            "corrupt");

        HubDeepReadinessReport report = fixture.CreateService(
            ReadyPublicationProbes(),
            shelfRoot).Evaluate();

        Assert.False(report.Ready);
        Assert.False(report.ServingReady);
        Assert.False(report.PublicationReady);
        Assert.Equal("unavailable", report.ReleaseShelf.Mode);
        Assert.DoesNotContain(shelfRoot, JsonSerializer.Serialize(report), StringComparison.Ordinal);
    }

    [Fact]
    public void Serving_evaluate_never_executes_a_stuck_publication_probe()
    {
        using Fixture fixture = new();
        var stuck = new HangingPublicationProbe(HubDeepReadinessService.ActivationProtocolProbeName);
        IReleaseShelfPublicationReadinessProbe[] probes =
        [
            stuck,
            ReadyPublicationProbe(HubDeepReadinessService.StorageAdmissionProbeName)
        ];
        HubDeepReadinessService service = fixture.CreateService(probes, ResolveSharedFixtureRoot());

        HubDeepReadinessReport report = service.Evaluate();

        Assert.True(report.Ready);
        Assert.True(report.ServingReady);
        Assert.False(report.PublicationReady);
        Assert.Equal(0, stuck.CallCount);
    }

    private sealed class Fixture : IDisposable
    {
        public Fixture()
        {
            Root = Path.Combine(Path.GetTempPath(), "hub-deep-readiness-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Root);
            StoragePath = Path.Combine(Root, "data-protection-keys");
            ManifestPath = Path.Combine(Root, "RELEASE_CHANNEL.generated.json");
        }

        public string Root { get; }

        public string StoragePath { get; }

        public string ManifestPath { get; }

        public HubDeepReadinessService CreateService(
            IEnumerable<IReleaseShelfPublicationReadinessProbe>? publicationProbes = null,
            string? downloadsRoot = null,
            IInstallLinkingStoreReadinessProbe? installLinkingStore = null)
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DATA_PROTECTION_KEYS_PATH"] = StoragePath,
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot ?? Root,
                    ["CHUMMER_RELEASE_REGISTRY_MANIFEST_FILE"] = ManifestPath,
                    ["ASPNETCORE_ENVIRONMENT"] = "Development"
                })
                .Build();
            StubHostEnvironment environment = new()
            {
                EnvironmentName = Environments.Development,
                ContentRootPath = Root
            };
            var shelf = new ReleaseShelfGenerationStore(configuration);
            PublicReleaseManifestService releases = new(configuration, shelf);
            return new HubDeepReadinessService(
                configuration,
                environment,
                releases,
                shelf,
                publicationProbes ?? ReadyPublicationProbes(),
                installLinkingStore ?? new StubInstallLinkingReadinessProbe(
                    new InstallLinkingStoreReadiness(true, "store_activated")),
                new DataProtectionKeyProtectionStatus(true, "certificate_key_encryptor_configured"));
        }

        public void WritePublishedManifest()
        {
            var payload = new Dictionary<string, object?>
            {
                ["contractName"] = "Chummer.Hub.Registry.Contracts",
                ["product"] = "chummer",
                ["channelId"] = "preview",
                ["version"] = "run-readiness-test",
                ["publishedAt"] = "2026-07-13T00:00:00Z",
                ["status"] = "published",
                ["artifacts"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["artifactId"] = "avalonia-linux-x64-installer",
                        ["head"] = "avalonia",
                        ["platform"] = "linux",
                        ["rid"] = "linux-x64",
                        ["arch"] = "x64",
                        ["kind"] = "installer",
                        ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                        ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                        ["sha256"] = new string('a', 64),
                        ["sizeBytes"] = 1234L
                    }
                }
            };
            File.WriteAllText(ManifestPath, JsonSerializer.Serialize(payload));
        }

        public void Dispose()
        {
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }
    }

    private static string ResolveSharedFixtureRoot()
    {
        string? cursor = Path.GetFullPath(Directory.GetCurrentDirectory());
        for (int depth = 0; depth < 8 && cursor is not null; depth++)
        {
            string candidate = Path.Combine(cursor, "tests", "fixtures", "atomic_release_shelf_v1");
            if (File.Exists(Path.Combine(candidate, ReleaseShelfGenerationStore.CurrentPointerFileName)))
            {
                return candidate;
            }

            cursor = Directory.GetParent(cursor)?.FullName;
        }

        throw new DirectoryNotFoundException("Shared atomic release shelf fixture was not found.");
    }

    private static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (string directory in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(Path.Combine(destination, Path.GetRelativePath(source, directory)));
        }

        foreach (string file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            string target = Path.Combine(destination, Path.GetRelativePath(source, file));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private static IReleaseShelfPublicationReadinessProbe ReadyPublicationProbe(string name)
        => new StubPublicationProbe(
            name,
            new ReleaseShelfPublicationReadinessProbeResult(true, "ready"));

    private static IReleaseShelfPublicationReadinessProbe[] ReadyPublicationProbes()
        =>
        [
            ReadyPublicationProbe(HubDeepReadinessService.ActivationProtocolProbeName),
            ReadyPublicationProbe(HubDeepReadinessService.StorageAdmissionProbeName)
        ];

    private sealed class StubPublicationProbe(
        string name,
        ReleaseShelfPublicationReadinessProbeResult result)
        : IReleaseShelfPublicationReadinessProbe
    {
        public string Name { get; } = name;

        public ValueTask<ReleaseShelfPublicationReadinessProbeResult> EvaluateAsync(
            ReleaseShelfSnapshot snapshot,
            CancellationToken cancellationToken)
        {
            Assert.NotNull(snapshot);
            cancellationToken.ThrowIfCancellationRequested();
            return ValueTask.FromResult(result);
        }
    }

    private sealed class StubInstallLinkingReadinessProbe(InstallLinkingStoreReadiness result)
        : IInstallLinkingStoreReadinessProbe
    {
        public InstallLinkingStoreReadiness Evaluate() => result;
    }

    private sealed class ThrowingPublicationProbe(string name, string message)
        : IReleaseShelfPublicationReadinessProbe
    {
        public string Name { get; } = name;

        public ValueTask<ReleaseShelfPublicationReadinessProbeResult> EvaluateAsync(
            ReleaseShelfSnapshot snapshot,
            CancellationToken cancellationToken)
            => throw new InvalidOperationException(message);
    }

    private sealed class HangingPublicationProbe(string name)
        : IReleaseShelfPublicationReadinessProbe
    {
        public string Name { get; } = name;
        public int CallCount { get; private set; }

        public ValueTask<ReleaseShelfPublicationReadinessProbeResult> EvaluateAsync(
            ReleaseShelfSnapshot snapshot,
            CancellationToken cancellationToken)
        {
            CallCount++;
            var completion = new TaskCompletionSource<ReleaseShelfPublicationReadinessProbeResult>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            return new ValueTask<ReleaseShelfPublicationReadinessProbeResult>(completion.Task);
        }
    }

    private sealed class StubHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Development;

        public string ApplicationName { get; set; } = "Chummer.Tests";

        public string ContentRootPath { get; set; } = Path.GetTempPath();

        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
