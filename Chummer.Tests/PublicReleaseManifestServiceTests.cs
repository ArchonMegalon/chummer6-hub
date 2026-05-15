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
    public void LoadManifestFailsClosedWhenDesktopClientCoverageIsMissing()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");
        fixture.WriteFlagshipReadiness(status: "fail", missingCoverageKeys: ["desktop_client"]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Equal("desktop_proof_review_required", manifest.RolloutState);
        Assert.Contains("desktop_client", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("parity-sensitive routes", manifest.KnownIssueSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("support lane", manifest.FixAvailabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("passed", manifest.ProofStatus);
    }

    [Fact]
    public void LoadManifestFailsClosedWhenDesktopClientCoverageIsOnlyWarningScoped()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");
        fixture.WriteFlagshipReadiness(status: "fail", warningCoverageKeys: ["desktop_client"]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Equal("desktop_proof_review_required", manifest.RolloutState);
        Assert.Contains("desktop_client", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("review-required lane", manifest.KnownIssueSummary, StringComparison.OrdinalIgnoreCase);
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

    [Theory]
    [InlineData("pass")]
    [InlineData("ready")]
    public void LoadManifestNormalizesRegistryProofAliasesToPassed(string proofStatus)
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestWithProofStatus(proofStatus);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("passed", manifest.ProofStatus);
    }

    [Theory]
    [InlineData("pass")]
    [InlineData("ready")]
    public void LoadManifestNormalizesLocalProofAliasesToPassed(string proofStatus)
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof(proofStatus, "http://127.0.0.1:8091");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("passed", manifest.ProofStatus);
    }

    [Fact]
    public void LoadCanonicalManifestJsonRewritesDesktopSurfaceRefsWhenDownloadsAreForceGated()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260513-221500",
            ["publishedAt"] = "2026-05-13T00:36:30Z",
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
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "open_public"
                }
            },
            ["desktopSurfaceRefs"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["registryId"] = "desktop-surface:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["channelId"] = "public_stable",
                    ["releaseVersion"] = "run-20260513-221500",
                    ["tupleId"] = "avalonia:linux:linux-x64",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["installAccessClass"] = "open_public",
                    ["desktopChannelRef"] = "desktop-channel:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["installGuidanceRef"] = "install-guidance:public_stable:run-20260513-221500:avalonia-linux-x64-installer",
                    ["participationReceiptRef"] = "participation-receipt:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["rewardPublicationRef"] = "reward-publication:binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicationBindingId"] = "binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer",
                    ["rationale"] = "public_stable keeps avalonia:linux:linux-x64 guest-readable so desktop channel, install guidance, participation, and reward refs stay governed without exposing provider internals."
                }
            },
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["complete"] = true,
                ["desktopRouteTruth"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["tupleId"] = "avalonia:linux:linux-x64",
                        ["head"] = "avalonia",
                        ["platform"] = "linux",
                        ["rid"] = "linux-x64",
                        ["arch"] = "x64",
                        ["artifactId"] = "avalonia-linux-x64-installer",
                        ["installPosture"] = "installer_first",
                        ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer"
                    }
                }
            }
        });

        string json = fixture.CreateService(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "true"
        }).LoadCanonicalManifestJson()!;

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement artifact = document.RootElement.GetProperty("artifacts")[0];
        JsonElement surface = document.RootElement.GetProperty("desktopSurfaceRefs")[0];

        Assert.Equal("account_required", artifact.GetProperty("installAccessClass").GetString());
        Assert.Equal("account_required", surface.GetProperty("installAccessClass").GetString());
        Assert.Contains("entitlement-backed", surface.GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("guest-readable", surface.GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadCanonicalManifestJsonKeepsFallbackDesktopSurfaceOpenWhenNoArtifactExists()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260513-221500",
            ["publishedAt"] = "2026-05-13T00:36:30Z",
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
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "open_public"
                }
            },
            ["desktopSurfaceRefs"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["registryId"] = "desktop-surface:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["channelId"] = "public_stable",
                    ["releaseVersion"] = "run-20260513-221500",
                    ["tupleId"] = "avalonia:linux:linux-x64",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["installAccessClass"] = "open_public",
                    ["desktopChannelRef"] = "desktop-channel:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["installGuidanceRef"] = "install-guidance:public_stable:run-20260513-221500:avalonia-linux-x64-installer",
                    ["participationReceiptRef"] = "participation-receipt:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["rewardPublicationRef"] = "reward-publication:binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicationBindingId"] = "binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer",
                    ["rationale"] = "public_stable keeps avalonia:linux:linux-x64 guest-readable so desktop channel, install guidance, participation, and reward refs stay governed without exposing provider internals."
                },
                new Dictionary<string, object?>
                {
                    ["registryId"] = "desktop-surface:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["artifactId"] = "blazor-desktop-linux-x64-installer",
                    ["channelId"] = "public_stable",
                    ["releaseVersion"] = "run-20260513-221500",
                    ["tupleId"] = "blazor-desktop:linux:linux-x64",
                    ["head"] = "blazor-desktop",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["installAccessClass"] = "open_public",
                    ["desktopChannelRef"] = "desktop-channel:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["installGuidanceRef"] = "install-guidance:public_stable:run-20260513-221500:blazor-desktop-linux-x64-installer",
                    ["participationReceiptRef"] = "participation-receipt:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["rewardPublicationRef"] = "reward-publication:binding:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["publicationBindingId"] = "binding:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["publicInstallRoute"] = "/downloads/install/blazor-desktop-linux-x64-installer",
                    ["rationale"] = "public_stable keeps fallback tuple blazor-desktop:linux:linux-x64 retained with guest-readable install guidance so recovery participation and reward refs stay governed."
                }
            }
        });

        string json = fixture.CreateService(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "true"
        }).LoadCanonicalManifestJson()!;

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement surfaces = document.RootElement.GetProperty("desktopSurfaceRefs");

        Assert.Equal("account_required", surfaces[0].GetProperty("installAccessClass").GetString());
        Assert.Equal("open_public", surfaces[1].GetProperty("installAccessClass").GetString());
        Assert.Contains("entitlement-backed", surfaces[0].GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains("guest-readable", surfaces[1].GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
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

    [Fact]
    public void LoadManifestPrefersCanonicalFileWhenRuntimeEndpointMatchesTimestampButDropsCanonicalArtifacts()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260423-201931",
            ["publishedAt"] = "2026-04-23T20:22:05Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
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
                    ["sizeBytes"] = 1L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "blazor-desktop-osx-arm64-installer",
                    ["head"] = "blazor-desktop",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Blazor Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-blazor-desktop-osx-arm64-installer.dmg",
                    ["sha256"] = "mac456",
                    ["sizeBytes"] = 2L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        using var httpClient = new HttpClient(new StaticJsonHandler(
            """
            {
              "product": "chummer",
              "channelId": "preview",
              "version": "run-20260423-201931",
              "publishedAt": "2026-04-23T20:22:05Z",
              "status": "published",
              "artifacts": [
                {
                  "artifactId": "avalonia-osx-arm64-installer",
                  "head": "avalonia",
                  "platform": "macos",
                  "arch": "arm64",
                  "kind": "installer",
                  "platformLabel": "Avalonia Desktop macOS ARM64 Installer",
                  "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
                  "downloadUrl": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                  "sha256": "mac123",
                  "sizeBytes": 1,
                  "installAccessClass": "account_required"
                }
              ]
            }
            """));

        var manifest = fixture.CreateService(httpClient, includeRuntimeUrl: true).LoadManifest();

        Assert.Equal("run-20260423-201931", manifest.Version);
        Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "avalonia-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "blazor-desktop-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
    }
    [Fact]
    public void LoadManifestPreservesTopLevelGeneratedTimestampFromCanonicalRegistryManifest()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260416-212019",
            ["generatedAt"] = "2026-04-16T21:23:00Z",
            ["publishedAt"] = "2026-04-16T21:21:44Z",
            ["status"] = "published",
            ["artifacts"] = new[]
            {
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
            }
        });

        var manifest = fixture.CreateService().LoadManifest();
        Assert.Equal(DateTimeOffset.Parse("2026-04-16T21:23:00Z"), manifest.GeneratedAt);

        string json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(json);
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contractName").GetString());
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contract_name").GetString());
        Assert.Equal("2026-04-16T21:23:00+00:00", document.RootElement.GetProperty("generatedAt").GetString());
        Assert.Equal("2026-04-16T21:23:00+00:00", document.RootElement.GetProperty("generated_at").GetString());
    }

    [Fact]
    public void LoadManifestPreservesDesktopTupleCoverageFromCanonicalRegistryManifest()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260419-201110",
            ["generatedAt"] = "2026-04-19T20:14:00Z",
            ["publishedAt"] = "2026-04-19T20:14:00Z",
            ["status"] = "published",
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["requiredPlatformIds"] = new[] { "linux", "windows" },
                ["missingPlatformIds"] = Array.Empty<string>(),
                ["missingHeadPlatformPairs"] = Array.Empty<string>(),
                ["missingRidPlatformTuples"] = Array.Empty<string>()
            },
            ["artifacts"] = new[]
            {
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
            }
        });

        var manifest = fixture.CreateService().LoadManifest();
        JsonElement coverage = Assert.IsType<JsonElement>(manifest.DesktopTupleCoverage);
        Assert.Equal(JsonValueKind.Object, coverage.ValueKind);
        Assert.Equal("linux", coverage.GetProperty("requiredPlatformIds")[0].GetString());
        Assert.Equal("windows", coverage.GetProperty("requiredPlatformIds")[1].GetString());

        string json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement serializedCoverage = document.RootElement.GetProperty("desktopTupleCoverage");
        Assert.Equal("linux", serializedCoverage.GetProperty("requiredPlatformIds")[0].GetString());
        Assert.Equal("windows", serializedCoverage.GetProperty("requiredPlatformIds")[1].GetString());
    }

    [Fact]
    public void LoadManifestPreservesCanonicalRidAsCompatibilityPlatformId()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260421-000001",
            ["generatedAt"] = "2026-04-21T00:00:01Z",
            ["publishedAt"] = "2026-04-21T00:00:01Z",
            ["status"] = "published",
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["requiredDesktopPlatforms"] = new[] { "linux", "windows", "macos" },
                ["requiredDesktopHeads"] = new[] { "avalonia" },
                ["requiredDesktopPlatformHeadRidTuples"] = new[] { "avalonia:linux-x64:linux", "avalonia:win-x64:windows", "avalonia:osx-arm64:macos" },
                ["promotedInstallerTuples"] = new object[]
                {
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["artifactId"] = "avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:macos:osx-arm64", ["head"] = "avalonia", ["platform"] = "macos", ["rid"] = "osx-arm64", ["arch"] = "arm64", ["kind"] = "installer", ["artifactId"] = "avalonia-osx-arm64-installer" }
                },
                ["promotedPlatformHeads"] = new Dictionary<string, object?> { ["linux"] = new[] { "avalonia" }, ["windows"] = Array.Empty<string>(), ["macos"] = new[] { "avalonia" } },
                ["promotedPlatformHeadRidTuples"] = new[] { "avalonia:linux-x64:linux", "avalonia:osx-arm64:macos" },
                ["missingRequiredPlatforms"] = new[] { "windows" },
                ["missingRequiredHeads"] = Array.Empty<string>(),
                ["missingRequiredPlatformHeadPairs"] = new[] { "avalonia:windows" },
                ["missingRequiredPlatformHeadRidTuples"] = new[] { "avalonia:win-x64:windows" },
                ["externalProofRequests"] = Array.Empty<object>(),
                ["desktopRouteTruth"] = Array.Empty<object>(),
                ["complete"] = false
            },
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
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "linux123",
                    ["sizeBytes"] = 1L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["rid"] = "osx-arm64",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 2L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Contains(manifest.Downloads, item => item.Id == "avalonia-linux-x64-installer" && item.PlatformId == "linux-x64");
        Assert.Contains(manifest.Downloads, item => item.Id == "avalonia-osx-arm64-installer" && item.PlatformId == "osx-arm64");
    }

    [Fact]
    public void LoadManifestDefaultsContractNameWhenSourceManifestOmitsIt()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("Chummer.Hub.Registry.Contracts", manifest.ContractName);

        string json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(json);
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contractName").GetString());
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contract_name").GetString());
    }

    [Fact]
    public void LoadManifestSuppressesDisabledArtifactsAndRebuildsCoverage()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260420-010101",
            ["publishedAt"] = "2026-04-20T01:01:01Z",
            ["status"] = "published",
            ["releaseProof"] = new Dictionary<string, object?>
            {
                ["status"] = "passed",
                ["proofRoutes"] = new[]
                {
                    "/downloads/install/avalonia-linux-x64-installer",
                    "/downloads/install/avalonia-win-x64-installer"
                }
            },
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["requiredDesktopPlatforms"] = new[] { "linux", "windows", "macos" },
                ["requiredDesktopHeads"] = new[] { "avalonia" },
                ["requiredDesktopPlatformHeadRidTuples"] = new[] { "avalonia:linux-x64:linux", "avalonia:win-x64:windows", "avalonia:osx-arm64:macos" },
                ["missingRequiredPlatforms"] = Array.Empty<string>(),
                ["missingRequiredHeads"] = Array.Empty<string>(),
                ["missingRequiredPlatformHeadPairs"] = Array.Empty<string>(),
                ["missingRequiredPlatformHeadRidTuples"] = Array.Empty<string>(),
                ["promotedInstallerTuples"] = new object[]
                {
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["artifactId"] = "avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["kind"] = "installer", ["artifactId"] = "avalonia-win-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:macos:osx-arm64", ["head"] = "avalonia", ["platform"] = "macos", ["rid"] = "osx-arm64", ["arch"] = "arm64", ["kind"] = "installer", ["artifactId"] = "avalonia-osx-arm64-installer" }
                },
                ["promotedPlatformHeads"] = new Dictionary<string, object?> { ["linux"] = new[] { "avalonia" }, ["windows"] = new[] { "avalonia" }, ["macos"] = new[] { "avalonia" } },
                ["promotedPlatformHeadRidTuples"] = new[] { "avalonia:linux-x64:linux", "avalonia:win-x64:windows", "avalonia:osx-arm64:macos" },
                ["externalProofRequests"] = Array.Empty<object>(),
                ["desktopRouteTruth"] = new object[]
                {
                    new Dictionary<string, object?> { ["artifactId"] = "avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["artifactId"] = "avalonia-win-x64-installer" }
                },
                ["complete"] = true
            },
            ["artifacts"] = new object[]
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
                    ["sha256"] = "linux123",
                    ["sizeBytes"] = 1L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = "win123",
                    ["sizeBytes"] = 2L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "dmg",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 3L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        var manifest = fixture.CreateService(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS"] = "avalonia-win-x64-installer"
        }).LoadManifest();

        Assert.DoesNotContain(manifest.Downloads, item => string.Equals(item.Id, "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(manifest.ProofRoutes ?? [], route => route.Contains("avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));

        JsonElement coverage = Assert.IsType<JsonElement>(manifest.DesktopTupleCoverage);
        Assert.True(coverage.GetProperty("complete").GetBoolean());
        Assert.DoesNotContain(
            coverage.GetProperty("promotedPlatformHeadRidTuples")
                .EnumerateArray()
                .Select(static value => value.GetString()),
            tupleId => tupleId is not null && tupleId.Contains("win-x64", StringComparison.OrdinalIgnoreCase));
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

        public PublicReleaseManifestService CreateService(
            HttpClient? httpClient = null,
            bool includeRuntimeUrl = false,
            IReadOnlyDictionary<string, string?>? additionalSettings = null)
        {
            Dictionary<string, string?> settings = new()
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot,
                ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE"] = Path.Combine(_root, "fleet", ".codex-studio", "published", "FLAGSHIP_PRODUCT_READINESS.generated.json")
            };
            if (includeRuntimeUrl)
            {
                settings["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "https://registry.local/api/v1/registry/release-channel/current";
            }

            if (additionalSettings is not null)
            {
                foreach ((string key, string? value) in additionalSettings)
                {
                    settings[key] = value;
                }
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
                payload["releaseProof"] = BuildRegistryProof("registry-passed");
            }

            WriteRegistryManifestRaw(payload);
        }

        public void WriteRegistryManifestWithProofStatus(string proofStatus)
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
                },
                ["releaseProof"] = BuildRegistryProof(proofStatus)
            };

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

        public void WriteRegistryManifestRaw(Dictionary<string, object?> payload)
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

        public void WriteFlagshipReadiness(
            string status,
            IReadOnlyList<string>? missingCoverageKeys = null,
            IReadOnlyList<string>? warningCoverageKeys = null)
        {
            string readinessDir = Path.Combine(_root, "fleet", ".codex-studio", "published");
            Directory.CreateDirectory(readinessDir);
            missingCoverageKeys ??= Array.Empty<string>();
            warningCoverageKeys ??= Array.Empty<string>();
            File.WriteAllText(
                Path.Combine(readinessDir, "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.flagship_product_readiness",
                    ["status"] = status,
                    ["completion_audit"] = new Dictionary<string, object?>
                    {
                        ["reason"] = "Flagship product readiness planes are not green."
                    },
                    ["flagship_readiness_audit"] = new Dictionary<string, object?>
                    {
                        ["reason"] = "flagship product readiness proof is not green: missing coverage: desktop_client",
                        ["warning_coverage_keys"] = warningCoverageKeys,
                        ["scoped_warning_coverage_keys"] = warningCoverageKeys,
                        ["missing_coverage_keys"] = missingCoverageKeys,
                        ["scoped_missing_coverage_keys"] = missingCoverageKeys
                    }
                }));
        }

        private static Dictionary<string, object?> BuildRegistryProof(string status)
            => new()
            {
                ["status"] = status,
                ["generatedAt"] = "2026-03-28T21:00:00Z",
                ["baseUrl"] = "https://registry.chummer.run",
                ["journeysPassed"] = new[] { "registry_journey" },
                ["proofRoutes"] = new[] { "/downloads" }
            };

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
