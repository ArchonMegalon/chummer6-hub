using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicReleaseManifestServiceTests
{
    [Fact]
    public void LoadManifestUsesLocalHubProofWhenRegistryProofIsAbsent()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("passed", manifest.ProofStatus);
        Assert.Equal("http://127.0.0.1:8091", manifest.ProofBaseUrl);
        Assert.NotNull(manifest.ProofGeneratedAt);
        Assert.Equal(["install_claim_restore_continue", "build_explain_publish"], manifest.ProofJourneys);
        Assert.Equal(["/downloads/install/avalonia-linux-x64-installer", "/account/support"], manifest.ProofRoutes);
    }

    [Fact]
    public void LoadManifestDoesNotOverrideRegistryProof()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: true);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("registry-passed", manifest.ProofStatus);
        Assert.Equal("https://registry.chummer.run", manifest.ProofBaseUrl);
        Assert.Equal(["registry_journey"], manifest.ProofJourneys);
        Assert.Equal(["/downloads"], manifest.ProofRoutes);
    }

    [Fact]
    public void ManifestSerializationKeepsLegacyReleaseProofObject()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "https://chummer.run");

        var manifest = fixture.CreateService().LoadManifest();
        var json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using var document = JsonDocument.Parse(json);

        JsonElement releaseProof = document.RootElement.GetProperty("releaseProof");
        Assert.Equal("passed", releaseProof.GetProperty("status").GetString());
        Assert.Equal("https://chummer.run", releaseProof.GetProperty("baseUrl").GetString());
        Assert.Equal("install_claim_restore_continue", releaseProof.GetProperty("journeysPassed")[0].GetString());
        Assert.Equal("/downloads/install/avalonia-linux-x64-installer", releaseProof.GetProperty("proofRoutes")[0].GetString());
    }

    [Fact]
    public void LoadManifestPrefersCanonicalFileWhenRuntimeEndpointIsStale()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(
            version: "run-20260402-203858",
            downloads:
            [
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 987654321L,
                    ["installAccessClass"] = "account_required"
                }
            ]);

        using var httpClient = new HttpClient(new StaticJsonHandler(
            """
            {
              "product": "chummer",
              "channelId": "preview",
              "version": "run-older",
              "publishedAt": "2026-04-02T19:00:00Z",
              "status": "published",
              "artifacts": [
                {
                  "artifactId": "avalonia-win-x64-installer",
                  "head": "avalonia",
                  "platform": "windows",
                  "arch": "x64",
                  "kind": "installer",
                  "platformLabel": "Avalonia Desktop Windows X64 Installer",
                  "fileName": "chummer-avalonia-win-x64-installer.exe",
                  "downloadUrl": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                  "sha256": "win123",
                  "sizeBytes": 123456789,
                  "installAccessClass": "open_public"
                }
              ]
            }
            """));

        var manifest = fixture.CreateService(httpClient, includeRuntimeUrl: true).LoadManifest();

        Assert.Equal("run-20260402-203858", manifest.Version);
        Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "avalonia-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(manifest.Downloads, item => string.Equals(item.Id, "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));
    }

    private sealed class PublicReleaseManifestFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _downloadsRoot;
        private readonly string _canonRoot;

        public PublicReleaseManifestFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "public-release-manifest-tests", Guid.NewGuid().ToString("N"));
            _downloadsRoot = Path.Combine(_root, "downloads");
            _canonRoot = Path.Combine(_root, "repo");
            Directory.CreateDirectory(_downloadsRoot);
            Directory.CreateDirectory(_canonRoot);
        }

        public PublicReleaseManifestService CreateService(HttpClient? httpClient = null, bool includeRuntimeUrl = false)
        {
            Dictionary<string, string?> settings = new()
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot
            };
            if (includeRuntimeUrl)
            {
                settings["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "https://registry.local/api/v1/registry/release-channel/current";
            }

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();

            return new PublicReleaseManifestService(configuration, httpClient);
        }

        public void WriteRegistryManifest(bool includeProof)
        {
            var payload = new Dictionary<string, object?>
            {
                ["product"] = "chummer",
                ["channelId"] = "docker",
                ["version"] = "1.0.0-preview",
                ["publishedAt"] = "2026-03-25T15:23:09Z",
                ["status"] = "published",
                ["artifacts"] = new[]
                {
                    new Dictionary<string, object?>
                    {
                        ["artifactId"] = "avalonia-linux-x64-installer",
                        ["head"] = "avalonia",
                        ["platform"] = "linux",
                        ["arch"] = "x64",
                        ["kind"] = "installer",
                        ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                        ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                        ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                        ["sha256"] = "abc123",
                        ["sizeBytes"] = 123456789L,
                        ["installAccessClass"] = "account_required"
                    }
                }
            };

            if (includeProof)
            {
                payload["releaseProof"] = new Dictionary<string, object?>
                {
                    ["status"] = "registry-passed",
                    ["generatedAt"] = "2026-03-28T21:00:00Z",
                    ["baseUrl"] = "https://registry.chummer.run",
                    ["journeysPassed"] = new[] { "registry_journey" },
                    ["proofRoutes"] = new[] { "/downloads" }
                };
            }

            WriteRegistryManifestRaw(payload);
        }

        public void WriteRegistryManifestRaw(string version, IReadOnlyList<Dictionary<string, object?>> downloads)
        {
            Dictionary<string, object?> payload = new()
            {
                ["product"] = "chummer",
                ["channelId"] = "preview",
                ["version"] = version,
                ["publishedAt"] = "2026-04-02T20:38:58Z",
                ["status"] = "published",
                ["artifacts"] = downloads
            };
            WriteRegistryManifestRaw(payload);
        }

        private void WriteRegistryManifestRaw(Dictionary<string, object?> payload)
        {
            var manifestPath = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
            File.WriteAllText(manifestPath, JsonSerializer.Serialize(payload));
        }

        public void WriteLocalProof(string status, string baseUrl)
        {
            var proofDir = Path.Combine(_canonRoot, ".codex-studio", "published");
            Directory.CreateDirectory(proofDir);
            File.WriteAllText(
                Path.Combine(proofDir, "HUB_LOCAL_RELEASE_PROOF.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "chummer6-hub.local_release_proof",
                    ["status"] = status,
                    ["base_url"] = baseUrl,
                    ["generated_at"] = "2026-03-28T21:03:08Z",
                    ["journeys_passed"] = new[] { "install_claim_restore_continue", "build_explain_publish" },
                    ["proof_routes"] = new[] { "/downloads/install/avalonia-linux-x64-installer", "/account/support" }
                }));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class StaticJsonHandler : HttpMessageHandler
    {
        private readonly string _payload;

        public StaticJsonHandler(string payload)
        {
            _payload = payload;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = new StringContent(_payload)
            });
    }
}
