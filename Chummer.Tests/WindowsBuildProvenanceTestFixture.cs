using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Tests;

internal static class WindowsBuildProvenanceTestFixture
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static IReadOnlyDictionary<string, byte[]> CreateFiles(
        string releaseVersion,
        string artifactId,
        string installerFileName,
        byte[] installerBytes,
        bool omitSourceMaterial = false,
        bool omitBuildInput = false)
    {
        const string targetId = "desktop-avalonia";
        string invocationId = $"{releaseVersion}.avalonia.win-x64.installer";
        string startedAt = DateTimeOffset.UtcNow.AddMinutes(-1).ToString("O");
        string generatedAt = DateTimeOffset.UtcNow.ToString("O");
        string artifactSha = Sha256For(installerBytes);
        string sourceCommit = new('d', 40);
        string sourceTree = new('e', 40);

        JsonObject sbom = new()
        {
            ["bomFormat"] = "CycloneDX",
            ["specVersion"] = "1.5",
            ["version"] = 1,
            ["metadata"] = new JsonObject
            {
                ["component"] = new JsonObject
                {
                    ["type"] = "application",
                    ["bom-ref"] = $"urn:chummer:project:{targetId}",
                    ["name"] = targetId,
                    ["version"] = releaseVersion
                }
            },
            ["components"] = new JsonArray(),
            ["dependencies"] = new JsonArray()
        };
        byte[] sbomBytes = Encoding.UTF8.GetBytes(sbom.ToJsonString(JsonOptions));
        string sbomSha = Sha256For(sbomBytes);

        JsonArray sourceMaterials = new();
        string[] requiredSourceMaterials =
                 {
                     "chummer-core-engine",
                     "chummer.run-services",
                     "chummer-ui-kit",
                     "chummer-hub-registry",
                     "chummer-media-factory",
                     "chummer5a"
                 };
        foreach (string repository in omitSourceMaterial
                     ? requiredSourceMaterials[..^1]
                     : requiredSourceMaterials)
        {
            sourceMaterials.Add(new JsonObject
            {
                ["repository"] = repository,
                ["repo_root"] = $"/source/{repository}",
                ["commit"] = new string('a', 40),
                ["tree"] = new string('b', 40),
                ["tracked_worktree_dirty"] = false
            });
        }

        JsonArray buildInputs = new();
        string[] requiredBuildInputs =
                 {
                     "windows-bootstrap-recipe",
                     "desktop-project",
                     "desktop-installer-recipe",
                     "dotnet-sdk-selection"
                 };
        foreach (string label in omitBuildInput
                     ? requiredBuildInputs[..^1]
                     : requiredBuildInputs)
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
            ["builder_id"] = "chummer-windows-release-bootstrap",
            ["build_type"] = "windows-desktop-release",
            ["invocation_id"] = invocationId,
            ["started_at_utc"] = startedAt,
            ["started_epoch_ns"] = 1,
            ["source"] = new JsonObject
            {
                ["repository"] = "chummer-presentation",
                ["repo_root"] = "/source/chummer-presentation",
                ["commit"] = sourceCommit,
                ["tree"] = sourceTree,
                ["tracked_worktree_dirty"] = false
            },
            ["source_materials"] = sourceMaterials,
            ["subject_declaration"] = new JsonObject
            {
                ["artifact_id"] = artifactId,
                ["artifact_kind"] = "desktop_download",
                ["artifact_name"] = installerFileName,
                ["artifact_binding_type"] = "file",
                ["artifact_path"] = $"/dist/files/{installerFileName}",
                ["target_id"] = targetId,
                ["prebuild"] = new JsonObject { ["exists"] = false }
            },
            ["sbom"] = new JsonObject
            {
                ["path"] = $"/proof/build-provenance/v1/sbom/{targetId}.cdx.json",
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
        JsonObject receipt = new()
        {
            ["contract_name"] = "chummer6.build_provenance.v1",
            ["receipt_kind"] = "invocation",
            ["status"] = "pass",
            ["builder_id"] = "chummer-windows-release-bootstrap",
            ["build_type"] = "windows-desktop-release",
            ["release_version"] = releaseVersion,
            ["invocation_id"] = invocationId,
            ["build_started_at_utc"] = startedAt,
            ["generated_at_utc"] = generatedAt,
            ["failures"] = new JsonArray(),
            ["assurance"] = "structural build-invocation evidence; not a signed SLSA attestation",
            ["invocation"] = new JsonObject
            {
                ["state_contract_name"] = "chummer6.build_provenance_invocation_state.v1",
                ["state_sha256"] = CanonicalJsonSha256(state),
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
                    ["artifact_name"] = installerFileName,
                    ["release_version"] = releaseVersion,
                    ["artifact_sha256"] = artifactSha,
                    ["artifact_size_bytes"] = installerBytes.LongLength,
                    ["artifact_built_mtime_ns"] = 2,
                    ["target_id"] = targetId,
                    ["source_repository"] = "chummer-presentation",
                    ["source_commit"] = sourceCommit,
                    ["source_tree"] = sourceTree,
                    ["source_tracked_worktree_dirty"] = false,
                    ["sbom_sha256"] = sbomSha,
                    ["sbom_generator"] = "deterministic_project.assets.json_inventory.v1",
                    ["invocation_id"] = invocationId,
                    ["produced_during_invocation"] = true
                }
            }
        };

        return new Dictionary<string, byte[]>(StringComparer.Ordinal)
        {
            [$"proof/build-provenance/v1/invocations/{invocationId}.json"] =
                Encoding.UTF8.GetBytes(receipt.ToJsonString(JsonOptions)),
            [$"proof/build-provenance/v1/sbom/{targetId}.cdx.json"] = sbomBytes
        };
    }

    private static string CanonicalJsonSha256(JsonNode node)
    {
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream))
        {
            WriteCanonical(writer, node);
        }
        return Sha256For(stream.ToArray());
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

    private static string Sha256For(byte[] bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes));
}
