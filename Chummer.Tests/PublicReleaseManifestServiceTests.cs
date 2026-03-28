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

        public PublicReleaseManifestService CreateService()
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot
                })
                .Build();

            return new PublicReleaseManifestService(configuration);
        }

        public void WriteRegistryManifest(bool includeProof)
        {
            var manifestPath = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
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
}
