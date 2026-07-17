using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Tests;

internal sealed record MacBuildProvenanceSubject(
    string ArtifactId,
    string Head,
    string FileName,
    byte[] Bytes,
    string Platform = "macos");

internal static class MacBuildProvenanceTestFixture
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static bool IsMacPlatform(string platform)
        => platform.Trim().ToLowerInvariant() is "mac" or "macos" or "osx" or "darwin";

    public static bool IsGovernedDesktopPlatform(string platform)
        => IsMacPlatform(platform)
           || platform.Trim().ToLowerInvariant() is "win" or "windows";

    public static IReadOnlyDictionary<string, byte[]> CreateFiles(
        IEnumerable<MacBuildProvenanceSubject> subjects)
    {
        MacBuildProvenanceSubject[] subjectRows = subjects.ToArray();
        Dictionary<string, byte[]> files = new(StringComparer.Ordinal);
        Dictionary<string, (byte[] Bytes, string Sha256)> sboms = new(StringComparer.Ordinal);

        foreach (string targetId in subjectRows.Select(ResolveTargetId).Distinct(StringComparer.Ordinal))
        {
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
                        ["version"] = "1.0.0"
                    }
                },
                ["components"] = new JsonArray(),
                ["dependencies"] = new JsonArray()
            };
            byte[] bytes = Encoding.UTF8.GetBytes(sbom.ToJsonString(JsonOptions));
            string relativePath = $"proof/build-provenance/v1/sbom/{targetId}.cdx.json";
            files.Add(relativePath, bytes);
            sboms.Add(targetId, (bytes, Sha256For(bytes)));
        }

        foreach (MacBuildProvenanceSubject subject in subjectRows)
        {
            string targetId = ResolveTargetId(subject);
            BuildIdentity buildIdentity = ResolveBuildIdentity(subject.Platform);
            string invocationId = $"test.{subject.ArtifactId}";
            string startedAt = DateTimeOffset.UtcNow.AddMinutes(-1).ToString("O");
            string sourceCommit = new('d', 40);
            string sourceTree = new('e', 40);
            string artifactSha = Sha256For(subject.Bytes);
            string sbomSha = sboms[targetId].Sha256;

            JsonArray sourceMaterials = new();
            foreach (string repository in new[]
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
                    ["repository"] = repository,
                    ["repo_root"] = $"/source/{repository}",
                    ["commit"] = new string('a', 40),
                    ["tree"] = new string('b', 40),
                    ["tracked_worktree_dirty"] = false
                });
            }

            JsonArray buildInputs = new();
            foreach (string label in new[]
                     {
                         buildIdentity.BootstrapInputLabel,
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
                ["builder_id"] = buildIdentity.BuilderId,
                ["build_type"] = buildIdentity.BuildType,
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
                    ["artifact_id"] = subject.ArtifactId,
                    ["artifact_kind"] = "desktop_download",
                    ["artifact_name"] = subject.FileName,
                    ["artifact_binding_type"] = "file",
                    ["artifact_path"] = $"/dist/files/{subject.FileName}",
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
            JsonObject receipt = new()
            {
                ["contract_name"] = "chummer6.build_provenance.v1",
                ["receipt_kind"] = "invocation",
                ["status"] = "pass",
                ["builder_id"] = buildIdentity.BuilderId,
                ["build_type"] = buildIdentity.BuildType,
                ["invocation_id"] = invocationId,
                ["build_started_at_utc"] = startedAt,
                ["generated_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
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
                        ["artifact_id"] = subject.ArtifactId,
                        ["artifact_kind"] = "desktop_download",
                        ["artifact_name"] = subject.FileName,
                        ["artifact_sha256"] = artifactSha,
                        ["artifact_size_bytes"] = subject.Bytes.LongLength,
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
            files.Add(
                $"proof/build-provenance/v1/invocations/{invocationId}.json",
                Encoding.UTF8.GetBytes(receipt.ToJsonString(JsonOptions)));
        }

        return files;
    }

    public static void WriteFiles(string bundleRoot, IEnumerable<MacBuildProvenanceSubject> subjects)
    {
        foreach ((string relativePath, byte[] bytes) in CreateFiles(subjects))
        {
            string path = Path.Combine(bundleRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllBytes(path, bytes);
        }
    }

    private static string ResolveTargetId(MacBuildProvenanceSubject subject)
        => subject.Head.Trim().ToLowerInvariant() switch
        {
            "avalonia" => "desktop-avalonia",
            "blazor-desktop" => "desktop-blazor",
            _ => throw new InvalidDataException($"Unsupported desktop provenance fixture head: {subject.Head}.")
        };

    private static BuildIdentity ResolveBuildIdentity(string platform)
        => platform.Trim().ToLowerInvariant() switch
        {
            "mac" or "macos" or "osx" or "darwin" =>
                new BuildIdentity("chummer-mac-hosted-bootstrap", "macos-desktop-release", "hosted-bootstrap"),
            "win" or "windows" =>
                new BuildIdentity("chummer-windows-release-bootstrap", "windows-desktop-release", "windows-bootstrap-recipe"),
            _ => throw new InvalidDataException($"Unsupported desktop provenance fixture platform: {platform}.")
        };

    private static string CanonicalJsonSha256(JsonNode node)
    {
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream, new JsonWriterOptions { Indented = false }))
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
        => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private sealed record BuildIdentity(string BuilderId, string BuildType, string BootstrapInputLabel);
}
