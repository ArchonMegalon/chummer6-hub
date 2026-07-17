using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Run.Api.Tests;

public sealed class ReleaseBuildProvenanceValidatorTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"chummer-provenance-test-{Guid.NewGuid():N}");

    [Fact]
    public void AcceptsExactArtifactReceiptAndSbomIdentity()
    {
        BundleFixture fixture = CreateBundle();

        ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot);
    }

    [Fact]
    public void AcceptsExactWindowsArtifactReceiptAndSbomIdentity()
    {
        BundleFixture fixture = CreateWindowsBundle();

        ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot);
    }

    [Fact]
    public void RejectsWindowsArtifactWithoutGovernedProvenance()
    {
        BundleFixture fixture = CreateWindowsBundle();

        InvalidDataException failure = Assert.Throws<InvalidDataException>(
            () => ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, proofRoot: null));

        Assert.Contains("missing governed build provenance for desktop artifacts", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RejectsWindowsReceiptFromMacBuildAuthority()
    {
        BundleFixture fixture = CreateWindowsBundle();
        JsonObject receipt = ParseObject(fixture.ReceiptPath);
        receipt["builder_id"] = "chummer-mac-hosted-bootstrap";
        receipt["build_type"] = "macos-desktop-release";
        JsonObject invocation = receipt["invocation"]!.AsObject();
        JsonObject state = invocation["state"]!.AsObject();
        state["builder_id"] = "chummer-mac-hosted-bootstrap";
        state["build_type"] = "macos-desktop-release";
        invocation["state_sha256"] = CanonicalJsonSha256(state);
        File.WriteAllText(fixture.ReceiptPath, receipt.ToJsonString());

        InvalidDataException failure = Assert.Throws<InvalidDataException>(
            () => ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot));

        Assert.Contains("authority does not match the artifact platform", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RejectsWindowsReceiptAfterSbomBytesDrift()
    {
        BundleFixture fixture = CreateWindowsBundle();
        JsonObject sbom = ParseObject(fixture.SbomPath);
        sbom["serialNumber"] = $"urn:uuid:{Guid.NewGuid()}";
        File.WriteAllText(fixture.SbomPath, sbom.ToJsonString());

        InvalidDataException failure = Assert.Throws<InvalidDataException>(
            () => ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot));

        Assert.Contains("does not match uploaded artifact identity", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RejectsWindowsReceiptWithMacBootstrapInput()
    {
        BundleFixture fixture = CreateWindowsBundle();
        JsonObject receipt = ParseObject(fixture.ReceiptPath);
        JsonObject invocation = receipt["invocation"]!.AsObject();
        JsonObject state = invocation["state"]!.AsObject();
        JsonArray buildInputs = state["build_inputs"]!.AsArray();
        buildInputs[0]!.AsObject()["label"] = "hosted-bootstrap";
        invocation["state_sha256"] = CanonicalJsonSha256(state);
        File.WriteAllText(fixture.ReceiptPath, receipt.ToJsonString());

        InvalidDataException failure = Assert.Throws<InvalidDataException>(
            () => ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot));

        Assert.Contains("input binding is invalid", failure.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("proof/build-provenance/v1/invocations/run-1.avalonia.json", 4 * 1024 * 1024)]
    [InlineData("proof/build-provenance/v1/sbom/desktop-avalonia.cdx.json", 16 * 1024 * 1024)]
    [InlineData("proof/build-provenance/v1/sbom/desktop-blazor.cdx.json", 16 * 1024 * 1024)]
    public void AllowsOnlyBoundedGovernedUploadPaths(string relativePath, long expectedLimit)
    {
        Assert.True(ReleaseBuildProvenanceValidator.IsGovernedUploadNamespace(relativePath));
        Assert.True(ReleaseBuildProvenanceValidator.TryGetGovernedUploadLimit(relativePath, out long actualLimit));
        Assert.Equal(expectedLimit, actualLimit);
    }

    [Theory]
    [InlineData("proof/build-provenance/v1/arbitrary.json")]
    [InlineData("proof/build-provenance/v1/invocations/../escape.json")]
    [InlineData("proof/build-provenance/v1/sbom/unexpected.cdx.json")]
    [InlineData("proof/build-provenance/v2/invocations/run.json")]
    [InlineData("proof/BUILD-PROVENANCE/v1/invocations/run.json")]
    public void RejectsArbitraryGovernedUploadPaths(string relativePath)
    {
        Assert.True(ReleaseBuildProvenanceValidator.IsGovernedUploadNamespace(relativePath));
        Assert.False(ReleaseBuildProvenanceValidator.TryGetGovernedUploadLimit(relativePath, out _));
    }

    [Fact]
    public void RejectsReceiptWhoseSubjectDigestDoesNotMatchUploadedArtifact()
    {
        BundleFixture fixture = CreateBundle();
        JsonObject receipt = ParseObject(fixture.ReceiptPath);
        ((JsonObject)((JsonArray)receipt["subjects"]!)[0]!)["artifact_sha256"] = new string('0', 64);
        File.WriteAllText(fixture.ReceiptPath, receipt.ToJsonString());

        InvalidDataException failure = Assert.Throws<InvalidDataException>(
            () => ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot));

        Assert.Contains("does not match uploaded artifact identity", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RejectsEmptyMacArtifactEvenWhenManifestDigestMatches()
    {
        BundleFixture fixture = CreateBundle();
        JsonObject artifact = ((JsonArray)fixture.Manifest["artifacts"]!)[0]!.AsObject();
        string artifactPath = Path.Combine(fixture.FilesRoot, artifact["fileName"]!.GetValue<string>());
        File.WriteAllBytes(artifactPath, Array.Empty<byte>());
        artifact["sha256"] = Sha256For(artifactPath);
        artifact["sizeBytes"] = 0;

        InvalidDataException failure = Assert.Throws<InvalidDataException>(
            () => ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot));

        Assert.Contains("artifact row is incomplete", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RejectsArbitraryPathsInsideGovernedProofSubtree()
    {
        BundleFixture fixture = CreateBundle();
        File.WriteAllText(Path.Combine(fixture.ProofRoot, "build-provenance", "v1", "arbitrary.txt"), "not governed");

        InvalidDataException failure = Assert.Throws<InvalidDataException>(
            () => ReleaseBuildProvenanceValidator.Validate(fixture.Manifest, fixture.FilesRoot, fixture.ProofRoot));

        Assert.Contains("unexpected path", failure.Message, StringComparison.Ordinal);
    }

    private BundleFixture CreateWindowsBundle()
        => CreateBundle(
            artifactId: "avalonia-win-x64-installer",
            artifactName: "chummer-avalonia-win-x64-installer.exe",
            platform: "windows",
            rid: "win-x64",
            builderId: "chummer-windows-release-bootstrap",
            buildType: "windows-desktop-release",
            bootstrapInputLabel: "windows-bootstrap-recipe");

    private BundleFixture CreateBundle(
        string artifactId = "avalonia-osx-arm64-installer",
        string artifactName = "chummer-avalonia-osx-arm64-installer.dmg",
        string platform = "macos",
        string rid = "osx-arm64",
        string builderId = "chummer-mac-hosted-bootstrap",
        string buildType = "macos-desktop-release",
        string bootstrapInputLabel = "hosted-bootstrap")
    {
        string filesRoot = Path.Combine(_root, "files");
        string proofRoot = Path.Combine(_root, "proof");
        string invocationRoot = Path.Combine(proofRoot, "build-provenance", "v1", "invocations");
        string sbomRoot = Path.Combine(proofRoot, "build-provenance", "v1", "sbom");
        Directory.CreateDirectory(filesRoot);
        Directory.CreateDirectory(invocationRoot);
        Directory.CreateDirectory(sbomRoot);

        const string targetId = "desktop-avalonia";
        string invocationId = $"run-test.avalonia.{rid}.installer";
        string artifactPath = Path.Combine(filesRoot, artifactName);
        File.WriteAllBytes(artifactPath, "final-desktop-artifact-bytes"u8.ToArray());
        string artifactSha = Sha256For(artifactPath);

        JsonObject sbom = new()
        {
            ["bomFormat"] = "CycloneDX",
            ["specVersion"] = "1.5",
            ["serialNumber"] = $"urn:uuid:{Guid.NewGuid()}",
            ["version"] = 1,
            ["metadata"] = new JsonObject
            {
                ["component"] = new JsonObject
                {
                    ["type"] = "application",
                    ["bom-ref"] = $"urn:chummer:project:{targetId}",
                    ["name"] = targetId,
                    ["version"] = "1.0.0"
                }
            },
            ["components"] = new JsonArray(),
            ["dependencies"] = new JsonArray()
        };
        string sbomPath = Path.Combine(sbomRoot, $"{targetId}.cdx.json");
        File.WriteAllText(sbomPath, sbom.ToJsonString());
        string sbomSha = Sha256For(sbomPath);

        string startedAt = DateTimeOffset.UtcNow.AddMinutes(-1).ToString("O");
        JsonArray sourceMaterials = new();
        foreach (string name in new[]
        {
            "chummer-core-engine",
            "chummer.run-services",
            "chummer-ui-kit",
            "chummer-hub-registry",
            "chummer-media-factory",
            "chummer5a"
        })
        {
            sourceMaterials.Add(new JsonObject
            {
                ["repository"] = name,
                ["repo_root"] = $"/source/{name}",
                ["commit"] = new string('a', 40),
                ["tree"] = new string('b', 40),
                ["tracked_worktree_dirty"] = false
            });
        }

        JsonArray buildInputs = new();
        foreach (string label in new[]
        {
            bootstrapInputLabel,
            "desktop-project",
            "desktop-installer-recipe",
            "dotnet-sdk-selection"
        })
        {
            buildInputs.Add(new JsonObject
            {
                ["label"] = label,
                ["path"] = $"/source/{label}",
                ["sha256"] = new string('c', 64)
            });
        }

        JsonObject state = new()
        {
            ["state_contract_name"] = "chummer6.build_provenance_invocation_state.v1",
            ["state_path"] = "/private/state.json",
            ["output_path"] = "/private/receipt.json",
            ["builder_id"] = builderId,
            ["build_type"] = buildType,
            ["invocation_id"] = invocationId,
            ["started_at_utc"] = startedAt,
            ["started_epoch_ns"] = 1,
            ["source"] = new JsonObject
            {
                ["repository"] = "chummer-presentation",
                ["repo_root"] = "/source/chummer-presentation",
                ["commit"] = new string('d', 40),
                ["tree"] = new string('e', 40),
                ["tracked_worktree_dirty"] = false
            },
            ["source_materials"] = sourceMaterials,
            ["subject_declaration"] = new JsonObject
            {
                ["artifact_id"] = artifactId,
                ["artifact_kind"] = "desktop_download",
                ["artifact_name"] = artifactName,
                ["artifact_binding_type"] = "file",
                ["artifact_path"] = $"/dist/files/{artifactName}",
                ["target_id"] = targetId,
                ["prebuild"] = new JsonObject { ["exists"] = false }
            },
            ["sbom"] = new JsonObject
            {
                ["path"] = $"/proof/sbom/{targetId}.cdx.json",
                ["sha256"] = sbomSha,
                ["source_assets_path"] = "/source/App/obj/project.assets.json",
                ["source_assets_sha256"] = new string('f', 64),
                ["dependency_inventory_sha256"] = new string('1', 64),
                ["generator"] = "deterministic_project.assets.json_inventory.v1"
            },
            ["build_tools"] = new JsonObject
            {
                ["provenance_generator_sha256"] = new string('2', 64),
                ["supply_chain_verifier_sha256"] = new string('3', 64)
            },
            ["build_inputs"] = buildInputs
        };
        string stateSha = CanonicalJsonSha256(state);
        JsonObject receipt = new()
        {
            ["contract_name"] = "chummer6.build_provenance.v1",
            ["receipt_kind"] = "invocation",
            ["status"] = "pass",
            ["builder_id"] = builderId,
            ["build_type"] = buildType,
            ["invocation_id"] = invocationId,
            ["build_started_at_utc"] = startedAt,
            ["generated_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
            ["failures"] = new JsonArray(),
            ["assurance"] = "structural build-invocation evidence; not a signed SLSA attestation",
            ["invocation"] = new JsonObject
            {
                ["state_contract_name"] = "chummer6.build_provenance_invocation_state.v1",
                ["state_sha256"] = stateSha,
                ["state"] = state,
                ["subject_declared_before_build"] = true,
                ["source_identity_stable"] = true
            },
            ["subjects"] = new JsonArray
            {
                new JsonObject
                {
                    ["artifact_id"] = artifactId,
                    ["artifact_kind"] = "desktop_download",
                    ["artifact_name"] = artifactName,
                    ["artifact_sha256"] = artifactSha,
                    ["artifact_size_bytes"] = new FileInfo(artifactPath).Length,
                    ["artifact_built_mtime_ns"] = 2,
                    ["target_id"] = targetId,
                    ["source_repository"] = "chummer-presentation",
                    ["source_commit"] = new string('d', 40),
                    ["source_tree"] = new string('e', 40),
                    ["source_tracked_worktree_dirty"] = false,
                    ["sbom_sha256"] = sbomSha,
                    ["sbom_generator"] = "deterministic_project.assets.json_inventory.v1",
                    ["invocation_id"] = invocationId,
                    ["produced_during_invocation"] = true
                }
            }
        };
        string receiptPath = Path.Combine(invocationRoot, $"{invocationId}.json");
        File.WriteAllText(receiptPath, receipt.ToJsonString());

        JsonObject manifest = new()
        {
            ["artifacts"] = new JsonArray
            {
                new JsonObject
                {
                    ["artifactId"] = artifactId,
                    ["head"] = "avalonia",
                    ["platform"] = platform,
                    ["rid"] = rid,
                    ["kind"] = "installer",
                    ["fileName"] = artifactName,
                    ["sha256"] = artifactSha,
                    ["sizeBytes"] = new FileInfo(artifactPath).Length
                }
            }
        };
        return new BundleFixture(manifest, filesRoot, proofRoot, receiptPath, sbomPath);
    }

    private static string CanonicalJsonSha256(JsonNode node)
    {
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream, new JsonWriterOptions { Indented = false }))
        {
            WriteCanonical(writer, node);
        }
        return Convert.ToHexString(SHA256.HashData(stream.ToArray())).ToLowerInvariant();
    }

    private static void WriteCanonical(Utf8JsonWriter writer, JsonNode? node)
    {
        switch (node)
        {
            case null:
                writer.WriteNullValue();
                break;
            case JsonObject value:
                writer.WriteStartObject();
                foreach ((string key, JsonNode? child) in value.OrderBy(static item => item.Key, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(key);
                    WriteCanonical(writer, child);
                }
                writer.WriteEndObject();
                break;
            case JsonArray value:
                writer.WriteStartArray();
                foreach (JsonNode? child in value)
                {
                    WriteCanonical(writer, child);
                }
                writer.WriteEndArray();
                break;
            default:
                node.WriteTo(writer);
                break;
        }
    }

    private static JsonObject ParseObject(string path)
        => JsonNode.Parse(File.ReadAllText(path))!.AsObject();

    private static string Sha256For(string path)
        => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    private sealed record BundleFixture(
        JsonObject Manifest,
        string FilesRoot,
        string ProofRoot,
        string ReceiptPath,
        string SbomPath);
}
