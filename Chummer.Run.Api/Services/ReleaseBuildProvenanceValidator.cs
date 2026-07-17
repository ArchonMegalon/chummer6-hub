using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services;

internal static partial class ReleaseBuildProvenanceValidator
{
    private const string ContractName = "chummer6.build_provenance.v1";
    private const string StateContractName = "chummer6.build_provenance_invocation_state.v1";
    internal const long MaximumReceiptBytes = 4 * 1024 * 1024;
    internal const long MaximumSbomBytes = 16 * 1024 * 1024;
    private static readonly TimeSpan MaximumAge = TimeSpan.FromDays(7);
    private static readonly TimeSpan MaximumFutureSkew = TimeSpan.FromMinutes(5);
    private static readonly IReadOnlyDictionary<string, string> TargetByHead =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["avalonia"] = "desktop-avalonia",
            ["blazor-desktop"] = "desktop-blazor"
        };
    private static readonly IReadOnlyDictionary<string, BuildIdentity> BuildIdentityByPlatform =
        new Dictionary<string, BuildIdentity>(StringComparer.Ordinal)
        {
            ["macos"] = new("chummer-mac-hosted-bootstrap", "macos-desktop-release", "hosted-bootstrap"),
            ["windows"] = new("chummer-windows-release-bootstrap", "windows-desktop-release", "windows-bootstrap-recipe")
        };
    private static readonly HashSet<string> RequiredSourceMaterials =
    [
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a"
    ];

    public static void Validate(JsonObject canonicalManifest, string filesRoot, string? proofRoot)
    {
        ArgumentNullException.ThrowIfNull(canonicalManifest);
        Dictionary<string, ExpectedArtifact> expected = LoadExpectedDesktopArtifacts(canonicalManifest, filesRoot);
        if (expected.Count == 0)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(proofRoot) || !Directory.Exists(proofRoot))
        {
            throw new InvalidDataException("bundle is missing governed build provenance for desktop artifacts.");
        }

        string governedRoot = Path.Combine(proofRoot, "build-provenance", "v1");
        string invocationRoot = Path.Combine(governedRoot, "invocations");
        string sbomRoot = Path.Combine(governedRoot, "sbom");
        RequireDirectory(governedRoot, "proof/build-provenance/v1");
        RequireDirectory(invocationRoot, "proof/build-provenance/v1/invocations");
        RequireDirectory(sbomRoot, "proof/build-provenance/v1/sbom");
        ValidateGovernedPaths(governedRoot, invocationRoot, sbomRoot);

        Dictionary<string, SbomBinding> sboms = LoadSboms(sbomRoot);
        HashSet<string> expectedTargets = expected.Values.Select(static item => item.TargetId).ToHashSet(StringComparer.Ordinal);
        if (!sboms.Keys.ToHashSet(StringComparer.Ordinal).SetEquals(expectedTargets))
        {
            throw new InvalidDataException("governed build provenance SBOM target set does not match desktop artifact targets.");
        }

        Dictionary<string, JsonObject> subjects = new(StringComparer.Ordinal);
        string[] receiptPaths = Directory.GetFiles(invocationRoot, "*.json", SearchOption.TopDirectoryOnly);
        if (receiptPaths.Length == 0)
        {
            throw new InvalidDataException("governed build provenance has no invocation receipts.");
        }

        foreach (string receiptPath in receiptPaths.Order(StringComparer.Ordinal))
        {
            ValidateReceipt(receiptPath, expected, sboms, subjects);
        }

        if (!subjects.Keys.ToHashSet(StringComparer.Ordinal).SetEquals(expected.Keys))
        {
            string[] missing = expected.Keys.Except(subjects.Keys, StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
            throw new InvalidDataException(
                "governed build provenance subject set does not match desktop artifacts"
                + (missing.Length > 0 ? $"; missing: {string.Join(", ", missing)}" : "."));
        }
    }

    internal static bool IsGovernedUploadNamespace(string relativePath)
    {
        string normalized = relativePath.Replace('\\', '/').Trim('/');
        return string.Equals(normalized, "proof/build-provenance", StringComparison.OrdinalIgnoreCase)
            || normalized.StartsWith("proof/build-provenance/", StringComparison.OrdinalIgnoreCase);
    }

    internal static bool TryGetGovernedUploadLimit(string relativePath, out long maximumBytes)
    {
        maximumBytes = 0;
        string normalized = relativePath.Replace('\\', '/').Trim('/');
        const string invocationPrefix = "proof/build-provenance/v1/invocations/";
        const string sbomPrefix = "proof/build-provenance/v1/sbom/";
        if (normalized.StartsWith(invocationPrefix, StringComparison.Ordinal))
        {
            string fileName = normalized[invocationPrefix.Length..];
            if (fileName.EndsWith(".json", StringComparison.Ordinal)
                && !fileName.Contains('/')
                && SafeId().IsMatch(fileName[..^".json".Length]))
            {
                maximumBytes = MaximumReceiptBytes;
                return true;
            }
            return false;
        }

        if (normalized.StartsWith(sbomPrefix, StringComparison.Ordinal))
        {
            string fileName = normalized[sbomPrefix.Length..];
            if (!fileName.Contains('/')
                && fileName.EndsWith(".cdx.json", StringComparison.Ordinal)
                && TargetByHead.Values.Contains(fileName[..^".cdx.json".Length], StringComparer.Ordinal))
            {
                maximumBytes = MaximumSbomBytes;
                return true;
            }
        }
        return false;
    }

    private static Dictionary<string, ExpectedArtifact> LoadExpectedDesktopArtifacts(JsonObject manifest, string filesRoot)
    {
        if (manifest["artifacts"] is not JsonArray artifacts)
        {
            throw new InvalidDataException("canonical release manifest is missing artifacts for provenance validation.");
        }

        Dictionary<string, ExpectedArtifact> expected = new(StringComparer.Ordinal);
        foreach (JsonObject artifact in artifacts.OfType<JsonObject>())
        {
            string platform = NormalizePlatform(JsonString(artifact["platform"]));
            if (!BuildIdentityByPlatform.TryGetValue(platform, out BuildIdentity? buildIdentity)
                || buildIdentity is null)
            {
                continue;
            }

            string artifactId = JsonString(artifact["artifactId"]);
            string head = NormalizeToken(JsonString(artifact["head"]));
            string fileName = JsonString(artifact["fileName"]);
            string digest = NormalizeDigest(JsonString(artifact["sha256"]));
            long? sizeBytes = JsonInt64(artifact["sizeBytes"]);
            if (!SafeId().IsMatch(artifactId)
                || !TargetByHead.TryGetValue(head, out string? targetId)
                || string.IsNullOrWhiteSpace(fileName)
                || !string.Equals(fileName, Path.GetFileName(fileName), StringComparison.Ordinal)
                || !Sha256().IsMatch(digest)
                || sizeBytes is null or <= 0)
            {
                throw new InvalidDataException($"desktop artifact row is incomplete for governed provenance: {artifactId}.");
            }

            string artifactPath = Path.Combine(filesRoot, fileName);
            RequireRegularFile(artifactPath, $"artifact bytes for {artifactId}");
            if (new FileInfo(artifactPath).Length != sizeBytes.Value
                || !string.Equals(Sha256For(artifactPath), digest, StringComparison.Ordinal))
            {
                throw new InvalidDataException($"desktop artifact identity does not match its manifest row: {artifactId}.");
            }

            if (!expected.TryAdd(
                artifactId,
                new ExpectedArtifact(
                    artifactId,
                    fileName,
                    digest,
                    sizeBytes.Value,
                    targetId,
                    buildIdentity.BuilderId,
                    buildIdentity.BuildType,
                    buildIdentity.BootstrapInputLabel)))
            {
                throw new InvalidDataException($"desktop artifact id is duplicated: {artifactId}.");
            }
        }

        return expected;
    }

    private static void ValidateGovernedPaths(string governedRoot, string invocationRoot, string sbomRoot)
    {
        HashSet<string> allowedDirectories =
        [
            Path.GetFullPath(governedRoot),
            Path.GetFullPath(invocationRoot),
            Path.GetFullPath(sbomRoot)
        ];
        foreach (string path in Directory.EnumerateFileSystemEntries(governedRoot, "*", SearchOption.AllDirectories))
        {
            FileAttributes attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException("governed build provenance cannot contain symlinks or reparse points.");
            }

            string fullPath = Path.GetFullPath(path);
            if ((attributes & FileAttributes.Directory) != 0)
            {
                if (!allowedDirectories.Contains(fullPath))
                {
                    throw new InvalidDataException($"governed build provenance contains an unexpected directory: {Path.GetFileName(path)}.");
                }
                continue;
            }

            string? parent = Path.GetDirectoryName(fullPath);
            bool allowedReceipt = string.Equals(parent, Path.GetFullPath(invocationRoot), StringComparison.Ordinal)
                && fullPath.EndsWith(".json", StringComparison.Ordinal);
            bool allowedSbom = string.Equals(parent, Path.GetFullPath(sbomRoot), StringComparison.Ordinal)
                && fullPath.EndsWith(".cdx.json", StringComparison.Ordinal);
            if (!allowedReceipt && !allowedSbom)
            {
                throw new InvalidDataException($"governed build provenance contains an unexpected path: {Path.GetFileName(path)}.");
            }
        }
    }

    private static Dictionary<string, SbomBinding> LoadSboms(string sbomRoot)
    {
        Dictionary<string, SbomBinding> result = new(StringComparer.Ordinal);
        foreach (string path in Directory.GetFiles(sbomRoot, "*.cdx.json", SearchOption.TopDirectoryOnly).Order(StringComparer.Ordinal))
        {
            RequireRegularFile(path, "SBOM document");
            if (new FileInfo(path).Length > MaximumSbomBytes)
            {
                throw new InvalidDataException($"governed build provenance SBOM is oversized: {Path.GetFileName(path)}.");
            }

            string fileName = Path.GetFileName(path);
            string targetId = fileName[..^".cdx.json".Length];
            if (!TargetByHead.Values.Contains(targetId, StringComparer.Ordinal))
            {
                throw new InvalidDataException($"governed build provenance has an unexpected SBOM target: {targetId}.");
            }

            JsonObject payload = ParseObject(path, "SBOM");
            JsonObject component = payload["metadata"]?["component"] as JsonObject
                ?? throw new InvalidDataException($"SBOM metadata component is missing: {fileName}.");
            if (!string.Equals(JsonString(payload["bomFormat"]), "CycloneDX", StringComparison.Ordinal)
                || !string.Equals(JsonString(payload["specVersion"]), "1.5", StringComparison.Ordinal)
                || !string.Equals(JsonString(component["name"]), targetId, StringComparison.Ordinal)
                || !string.Equals(JsonString(component["bom-ref"]), $"urn:chummer:project:{targetId}", StringComparison.Ordinal))
            {
                throw new InvalidDataException($"SBOM contract or target binding is invalid: {fileName}.");
            }

            if (!result.TryAdd(targetId, new SbomBinding(targetId, path, Sha256For(path))))
            {
                throw new InvalidDataException($"governed build provenance has duplicate SBOM target: {targetId}.");
            }
        }

        return result;
    }

    private static void ValidateReceipt(
        string path,
        IReadOnlyDictionary<string, ExpectedArtifact> expected,
        IReadOnlyDictionary<string, SbomBinding> sboms,
        IDictionary<string, JsonObject> subjects)
    {
        RequireRegularFile(path, "build provenance invocation receipt");
        if (new FileInfo(path).Length > MaximumReceiptBytes)
        {
            throw new InvalidDataException($"build provenance invocation receipt is oversized: {Path.GetFileName(path)}.");
        }

        JsonObject receipt = ParseObject(path, "build provenance invocation receipt");
        string invocationId = JsonString(receipt["invocation_id"]);
        if (!string.Equals(JsonString(receipt["contract_name"]), ContractName, StringComparison.Ordinal)
            || !string.Equals(JsonString(receipt["receipt_kind"]), "invocation", StringComparison.Ordinal)
            || !string.Equals(JsonString(receipt["status"]), "pass", StringComparison.Ordinal)
            || !SafeId().IsMatch(invocationId)
            || !string.Equals(Path.GetFileName(path), $"{invocationId}.json", StringComparison.Ordinal)
            || receipt["failures"] is not JsonArray failures
            || failures.Count != 0)
        {
            throw new InvalidDataException($"build provenance invocation contract is invalid: {Path.GetFileName(path)}.");
        }

        DateTimeOffset generatedAt = RequireTimestamp(receipt["generated_at_utc"], "generated_at_utc");
        DateTimeOffset startedAt = RequireTimestamp(receipt["build_started_at_utc"], "build_started_at_utc");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        if (generatedAt < startedAt || generatedAt < now - MaximumAge || generatedAt > now + MaximumFutureSkew)
        {
            throw new InvalidDataException($"build provenance invocation timestamp is invalid or stale: {invocationId}.");
        }

        JsonObject invocation = receipt["invocation"] as JsonObject
            ?? throw new InvalidDataException($"build provenance invocation binding is missing: {invocationId}.");
        JsonObject state = invocation["state"] as JsonObject
            ?? throw new InvalidDataException($"build provenance invocation state is missing: {invocationId}.");
        string stateSha = JsonString(invocation["state_sha256"]);
        if (!string.Equals(JsonString(invocation["state_contract_name"]), StateContractName, StringComparison.Ordinal)
            || JsonBoolean(invocation["subject_declared_before_build"]) is not true
            || JsonBoolean(invocation["source_identity_stable"]) is not true
            || !Sha256().IsMatch(stateSha)
            || !string.Equals(CanonicalJsonSha256(state), stateSha, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"build provenance invocation state binding is invalid: {invocationId}.");
        }

        foreach (string field in new[] { "builder_id", "build_type", "invocation_id" })
        {
            if (!string.Equals(JsonString(state[field]), JsonString(receipt[field]), StringComparison.Ordinal))
            {
                throw new InvalidDataException($"build provenance invocation state {field} mismatch: {invocationId}.");
            }
        }
        if (!string.Equals(JsonString(state["started_at_utc"]), JsonString(receipt["build_started_at_utc"]), StringComparison.Ordinal))
        {
            throw new InvalidDataException($"build provenance invocation start timestamp mismatch: {invocationId}.");
        }

        ValidateSourceState(state, invocationId);
        ValidateBuildTools(state, invocationId);
        if (receipt["subjects"] is not JsonArray subjectRows
            || subjectRows.Count != 1
            || subjectRows[0] is not JsonObject subject)
        {
            throw new InvalidDataException($"build provenance invocation must contain exactly one subject: {invocationId}.");
        }

        string artifactId = JsonString(subject["artifact_id"]);
        if (!expected.TryGetValue(artifactId, out ExpectedArtifact? artifact))
        {
            throw new InvalidDataException($"build provenance contains an unexpected subject: {artifactId}.");
        }
        if (!string.Equals(JsonString(receipt["builder_id"]), artifact.BuilderId, StringComparison.Ordinal)
            || !string.Equals(JsonString(receipt["build_type"]), artifact.BuildType, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"build provenance invocation authority does not match the artifact platform: {artifactId}.");
        }
        ValidateBuildInputs(state, invocationId, artifact.BootstrapInputLabel);
        if (subjects.ContainsKey(artifactId))
        {
            throw new InvalidDataException($"build provenance contains duplicate subject: {artifactId}.");
        }

        JsonObject declaration = state["subject_declaration"] as JsonObject
            ?? throw new InvalidDataException($"build provenance pre-build declaration is missing: {artifactId}.");
        if (declaration["prebuild"] is not JsonObject)
        {
            throw new InvalidDataException($"build provenance pre-build artifact snapshot is missing: {artifactId}.");
        }
        JsonObject source = state["source"] as JsonObject ?? new JsonObject();
        JsonObject sbom = state["sbom"] as JsonObject ?? new JsonObject();
        long? startedEpochNs = JsonInt64(state["started_epoch_ns"]);
        if (!sboms.TryGetValue(artifact.TargetId, out SbomBinding? sbomBinding))
        {
            throw new InvalidDataException($"build provenance SBOM is missing for target: {artifact.TargetId}.");
        }

        bool identityMatches =
            string.Equals(JsonString(subject["artifact_id"]), artifact.ArtifactId, StringComparison.Ordinal)
            && string.Equals(JsonString(subject["artifact_kind"]), "desktop_download", StringComparison.Ordinal)
            && string.Equals(JsonString(subject["artifact_name"]), artifact.FileName, StringComparison.Ordinal)
            && string.Equals(NormalizeDigest(JsonString(subject["artifact_sha256"])), artifact.Sha256, StringComparison.Ordinal)
            && JsonInt64(subject["artifact_size_bytes"]) == artifact.SizeBytes
            && startedEpochNs is > 0
            && JsonInt64(subject["artifact_built_mtime_ns"]) > startedEpochNs
            && string.Equals(JsonString(subject["target_id"]), artifact.TargetId, StringComparison.Ordinal)
            && string.Equals(JsonString(subject["source_repository"]), "chummer-presentation", StringComparison.Ordinal)
            && string.Equals(JsonString(subject["source_commit"]), JsonString(source["commit"]), StringComparison.Ordinal)
            && string.Equals(JsonString(subject["source_tree"]), JsonString(source["tree"]), StringComparison.Ordinal)
            && JsonBoolean(subject["source_tracked_worktree_dirty"]) is false
            && JsonBoolean(subject["produced_during_invocation"]) is true
            && string.Equals(JsonString(subject["invocation_id"]), invocationId, StringComparison.Ordinal)
            && string.Equals(JsonString(subject["sbom_sha256"]), sbomBinding.Sha256, StringComparison.Ordinal)
            && string.Equals(JsonString(subject["sbom_generator"]), "deterministic_project.assets.json_inventory.v1", StringComparison.Ordinal)
            && string.Equals(JsonString(sbom["sha256"]), sbomBinding.Sha256, StringComparison.Ordinal)
            && string.Equals(JsonString(sbom["generator"]), "deterministic_project.assets.json_inventory.v1", StringComparison.Ordinal)
            && string.Equals(JsonString(declaration["artifact_id"]), artifact.ArtifactId, StringComparison.Ordinal)
            && string.Equals(JsonString(declaration["artifact_kind"]), "desktop_download", StringComparison.Ordinal)
            && string.Equals(JsonString(declaration["artifact_name"]), artifact.FileName, StringComparison.Ordinal)
            && string.Equals(JsonString(declaration["artifact_binding_type"]), "file", StringComparison.Ordinal)
            && string.Equals(Path.GetFileName(JsonString(declaration["artifact_path"])), artifact.FileName, StringComparison.Ordinal)
            && string.Equals(JsonString(declaration["target_id"]), artifact.TargetId, StringComparison.Ordinal);
        if (!identityMatches)
        {
            throw new InvalidDataException($"build provenance subject does not match uploaded artifact identity: {artifactId}.");
        }

        subjects[artifactId] = subject;
    }

    private static void ValidateSourceState(JsonObject state, string invocationId)
    {
        JsonObject source = state["source"] as JsonObject
            ?? throw new InvalidDataException($"build provenance source state is missing: {invocationId}.");
        if (!string.Equals(JsonString(source["repository"]), "chummer-presentation", StringComparison.Ordinal)
            || JsonBoolean(source["tracked_worktree_dirty"]) is not false
            || !GitObjectId().IsMatch(JsonString(source["commit"]))
            || !GitObjectId().IsMatch(JsonString(source["tree"])))
        {
            throw new InvalidDataException($"build provenance source binding is invalid: {invocationId}.");
        }

        if (state["source_materials"] is not JsonArray materials)
        {
            throw new InvalidDataException($"build provenance source materials are missing: {invocationId}.");
        }
        HashSet<string> names = new(StringComparer.Ordinal);
        foreach (JsonObject material in materials.OfType<JsonObject>())
        {
            string name = JsonString(material["repository"]);
            if (!RequiredSourceMaterials.Contains(name)
                || JsonBoolean(material["tracked_worktree_dirty"]) is not false
                || !GitObjectId().IsMatch(JsonString(material["commit"]))
                || !GitObjectId().IsMatch(JsonString(material["tree"]))
                || !names.Add(name))
            {
                throw new InvalidDataException($"build provenance source material binding is invalid: {invocationId}.");
            }
        }
        if (!names.SetEquals(RequiredSourceMaterials))
        {
            throw new InvalidDataException($"build provenance source-material set is incomplete: {invocationId}.");
        }
    }

    private static void ValidateBuildInputs(JsonObject state, string invocationId, string bootstrapInputLabel)
    {
        HashSet<string> required =
        [
            bootstrapInputLabel,
            "desktop-project",
            "desktop-installer-recipe",
            "dotnet-sdk-selection"
        ];
        if (state["build_inputs"] is not JsonArray inputs)
        {
            throw new InvalidDataException($"build provenance inputs are missing: {invocationId}.");
        }
        HashSet<string> names = new(StringComparer.Ordinal);
        foreach (JsonObject input in inputs.OfType<JsonObject>())
        {
            string label = JsonString(input["label"]);
            if (!required.Contains(label) || !Sha256().IsMatch(JsonString(input["sha256"])) || !names.Add(label))
            {
                throw new InvalidDataException($"build provenance input binding is invalid: {invocationId}.");
            }
        }
        if (!names.SetEquals(required))
        {
            throw new InvalidDataException($"build provenance input set is incomplete: {invocationId}.");
        }
    }

    private static void ValidateBuildTools(JsonObject state, string invocationId)
    {
        if (state["build_tools"] is not JsonObject tools
            || !Sha256().IsMatch(JsonString(tools["provenance_generator_sha256"]))
            || !Sha256().IsMatch(JsonString(tools["supply_chain_verifier_sha256"])))
        {
            throw new InvalidDataException($"build provenance tool binding is invalid: {invocationId}.");
        }
    }

    private static JsonObject ParseObject(string path, string label)
    {
        try
        {
            return JsonNode.Parse(File.ReadAllText(path)) as JsonObject
                ?? throw new InvalidDataException($"{label} must be a JSON object: {Path.GetFileName(path)}.");
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException($"{label} is malformed: {Path.GetFileName(path)}.", ex);
        }
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
                return;
            case JsonObject value:
                writer.WriteStartObject();
                foreach ((string key, JsonNode? child) in value.OrderBy(static item => item.Key, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(key);
                    WriteCanonical(writer, child);
                }
                writer.WriteEndObject();
                return;
            case JsonArray value:
                writer.WriteStartArray();
                foreach (JsonNode? child in value)
                {
                    WriteCanonical(writer, child);
                }
                writer.WriteEndArray();
                return;
            default:
                node.WriteTo(writer);
                return;
        }
    }

    private static DateTimeOffset RequireTimestamp(JsonNode? node, string field)
        => DateTimeOffset.TryParse(JsonString(node), out DateTimeOffset value)
            ? value.ToUniversalTime()
            : throw new InvalidDataException($"build provenance timestamp is invalid: {field}.");

    private static void RequireDirectory(string path, string label)
    {
        if (!Directory.Exists(path) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException($"bundle is missing a regular governed directory: {label}.");
        }
    }

    private static void RequireRegularFile(string path, string label)
    {
        if (!File.Exists(path) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException($"bundle is missing a regular {label}: {Path.GetFileName(path)}.");
        }
    }

    private static string Sha256For(string path)
    {
        using FileStream stream = new(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static string JsonString(JsonNode? node)
        => node is JsonValue value && value.TryGetValue<string>(out string? result) ? result.Trim() : string.Empty;

    private static long? JsonInt64(JsonNode? node)
        => node is JsonValue value && value.TryGetValue<long>(out long result) ? result : null;

    private static bool? JsonBoolean(JsonNode? node)
        => node is JsonValue value && value.TryGetValue<bool>(out bool result) ? result : null;

    private static string NormalizeToken(string? value) => (value ?? string.Empty).Trim().ToLowerInvariant();
    private static string NormalizeDigest(string? value) => NormalizeToken(value).Replace("sha256:", string.Empty, StringComparison.Ordinal);
    private static string NormalizePlatform(string? value)
        => NormalizeToken(value) switch
        {
            "mac" or "osx" or "darwin" => "macos",
            string normalized => normalized
        };

    [GeneratedRegex("^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$", RegexOptions.CultureInvariant)]
    private static partial Regex SafeId();

    [GeneratedRegex("^[0-9a-f]{64}$", RegexOptions.CultureInvariant)]
    private static partial Regex Sha256();

    [GeneratedRegex("^[0-9a-f]{40,64}$", RegexOptions.CultureInvariant)]
    private static partial Regex GitObjectId();

    private sealed record ExpectedArtifact(
        string ArtifactId,
        string FileName,
        string Sha256,
        long SizeBytes,
        string TargetId,
        string BuilderId,
        string BuildType,
        string BootstrapInputLabel);

    private sealed record SbomBinding(string TargetId, string Path, string Sha256);

    private sealed record BuildIdentity(string BuilderId, string BuildType, string BootstrapInputLabel);
}
