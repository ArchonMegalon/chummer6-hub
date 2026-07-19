using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Resolves one public projection output through the digest-bound CURRENT pointer.
/// A configured snapshot root is an authority boundary: consumers never fall back
/// to an independently mounted or repository-local proof when it is invalid.
/// </summary>
public sealed class PublicProjectionSnapshotService
{
    public const string SnapshotRootConfigurationKey = "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT";
    public const string SnapshotRequiredConfigurationKey = "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_REQUIRED";
    public const string HubLocalReleaseProofFileName = "HUB_LOCAL_RELEASE_PROOF.generated.json";
    public const string HubServedReleaseProofFileName = "HUB_SERVED_RELEASE_PROOF.generated.json";

    private const string CurrentFileName = "CURRENT.json";
    private const string ManifestFileName = "PUBLIC_PROJECTION_SNAPSHOT.generated.json";
    private const string CurrentContractName = "chummer.public_projection_current/v1";
    private const string SnapshotContractName = "chummer.public_projection_snapshot/v1";
    private const int MaximumPointerBytes = 256 * 1024;
    private const int MaximumManifestBytes = 2 * 1024 * 1024;
    private const int MaximumOutputBytes = 32 * 1024 * 1024;
    private static readonly Regex Sha256Pattern = new("^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
    private static readonly Regex SnapshotIdPattern = new(
        "^public-projection-[0-9a-f]{64}$",
        RegexOptions.CultureInvariant);
    private static readonly string[] OutputNames =
    [
        HubLocalReleaseProofFileName,
        HubServedReleaseProofFileName,
        "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
        "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
        "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json"
    ];
    private static readonly HashSet<string> OutputNameSet = new(OutputNames, StringComparer.Ordinal);

    private readonly IConfiguration _configuration;
    private readonly Action? _afterRootOpenedForTests;

    public PublicProjectionSnapshotService(IConfiguration configuration)
        : this(configuration, afterRootOpenedForTests: null)
    {
    }

    internal PublicProjectionSnapshotService(
        IConfiguration configuration,
        Action? afterRootOpenedForTests)
    {
        _configuration = configuration;
        _afterRootOpenedForTests = afterRootOpenedForTests;
    }

    public PublicProjectionOutputSnapshot LoadHubLocalReleaseProof()
        => LoadOutput(HubLocalReleaseProofFileName);

    public PublicProjectionOutputSnapshot LoadOutput(string outputName)
    {
        if (!OutputNameSet.Contains(outputName))
        {
            return PublicProjectionOutputSnapshot.Invalid(
                isConfigured: true,
                "requested public projection output is outside the authenticated inventory");
        }

        SnapshotRootResolution rootResolution = ResolveSnapshotRoot();
        if (!rootResolution.IsConfigured)
        {
            return PublicProjectionOutputSnapshot.Unconfigured();
        }
        if (string.IsNullOrWhiteSpace(rootResolution.Path))
        {
            return PublicProjectionOutputSnapshot.Invalid(
                isConfigured: true,
                "current public projection snapshot is unavailable");
        }

        try
        {
            string root = Path.GetFullPath(rootResolution.Path);
            using PublicProjectionDescriptorReader descriptorReader =
                PublicProjectionDescriptorReader.Open(root);
            _afterRootOpenedForTests?.Invoke();
            byte[] pointerBytes = descriptorReader.ReadRootFile(
                CurrentFileName,
                MaximumPointerBytes,
                "current public projection pointer");
            using JsonDocument pointerDocument = ParseStrictObject(
                pointerBytes,
                "current public projection pointer");
            JsonElement pointer = pointerDocument.RootElement;

            RequireExactString(pointer, "contractName", CurrentContractName);
            RequireExactString(pointer, "status", "pass");
            string snapshotId = RequireString(pointer, "snapshotId");
            string snapshotSha256 = RequireLowercaseSha256(pointer, "snapshotSha256");
            string manifestSha256 = RequireLowercaseSha256(pointer, "manifestSha256");
            if (!SnapshotIdPattern.IsMatch(snapshotId)
                || !string.Equals(
                    snapshotId,
                    $"public-projection-{snapshotSha256}",
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("current public projection pointer digest binding drifted");
            }
            RequireExactString(
                pointer,
                "manifestRelativePath",
                $"{snapshotId}/{ManifestFileName}");
            ValidatePointerOutputs(pointer, snapshotId);

            using PublicProjectionDescriptorReader.PublicProjectionDescriptorDirectory snapshot =
                descriptorReader.OpenDirectory(
                    snapshotId,
                    "current public projection snapshot");
            byte[] manifestBytes = snapshot.ReadFile(
                ManifestFileName,
                MaximumManifestBytes,
                "current public projection manifest");
            RequireDigest(manifestBytes, manifestSha256, "current public projection manifest");
            using JsonDocument manifestDocument = ParseStrictObject(
                manifestBytes,
                "current public projection manifest");
            JsonElement manifest = manifestDocument.RootElement;
            RequireExactString(manifest, "contractName", SnapshotContractName);
            RequireExactString(manifest, "status", "pass");
            RequireExactString(manifest, "snapshotId", snapshotId);
            RequireExactString(manifest, "snapshotSha256", snapshotSha256);

            JsonElement manifestOutputs = RequireObject(manifest, "outputs");
            if (!ExactPropertySet(manifestOutputs, OutputNameSet))
            {
                throw new InvalidDataException("current public projection output inventory drifted");
            }

            var outputDigests = new Dictionary<string, string>(StringComparer.Ordinal);
            var outputSizes = new Dictionary<string, long>(StringComparer.Ordinal);
            foreach (string name in OutputNames)
            {
                JsonElement entry = RequireObject(manifestOutputs, name);
                RequireExactString(entry, "relativePath", name);
                outputDigests[name] = RequireLowercaseSha256(entry, "sha256");
                outputSizes[name] = RequireNonNegativeInt64(entry, "sizeBytes");
            }
            if (!string.Equals(
                    ComputeSnapshotDigest(outputDigests),
                    snapshotSha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("current public projection aggregate digest drifted");
            }
            if (!string.Equals(
                    outputDigests[HubLocalReleaseProofFileName],
                    outputDigests[HubServedReleaseProofFileName],
                    StringComparison.Ordinal)
                || outputSizes[HubLocalReleaseProofFileName]
                != outputSizes[HubServedReleaseProofFileName])
            {
                throw new InvalidDataException("current local and served Hub proofs disagree");
            }

            byte[] outputBytes = snapshot.ReadFile(
                outputName,
                MaximumOutputBytes,
                $"current {outputName}");
            if (outputBytes.LongLength != outputSizes[outputName])
            {
                throw new InvalidDataException("current public projection output size drifted");
            }
            RequireDigest(outputBytes, outputDigests[outputName], "current public projection output");

            // CURRENT may advance atomically while an immutable generation is read.
            // A consumer either sees one stable current pointer or fails closed.
            byte[] pointerAfter = descriptorReader.ReadRootFile(
                CurrentFileName,
                MaximumPointerBytes,
                "current public projection pointer");
            if (!CryptographicOperations.FixedTimeEquals(pointerBytes, pointerAfter))
            {
                throw new InvalidDataException("current public projection pointer advanced during resolution");
            }
            snapshot.VerifyPathIdentity();
            descriptorReader.VerifyRootPathIdentity();

            return PublicProjectionOutputSnapshot.Valid(
                snapshotId,
                snapshotSha256,
                Path.Combine(root, snapshotId, outputName),
                outputDigests[outputName],
                outputBytes);
        }
        catch (Exception exception) when (exception is InvalidDataException
                                          or IOException
                                          or UnauthorizedAccessException
                                          or JsonException
                                          or NotSupportedException
                                          or ArgumentException
                                          or CryptographicException)
        {
            return PublicProjectionOutputSnapshot.Invalid(
                isConfigured: true,
                "current public projection snapshot failed authentication");
        }
    }

    private SnapshotRootResolution ResolveSnapshotRoot()
    {
        if (_configuration[SnapshotRootConfigurationKey]?.Trim() is { Length: > 0 } configured)
        {
            return new SnapshotRootResolution(true, configured);
        }

        bool required = ParseBoolean(_configuration[SnapshotRequiredConfigurationKey]);
        string relative = Path.Combine(".codex-studio", "published");
        string? canonRoot = _configuration["CHUMMER_PUBLIC_CANON_ROOT"]?.Trim();
        string? discovered = new[]
            {
                !string.IsNullOrWhiteSpace(canonRoot) ? Path.Combine(canonRoot, relative) : null,
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relative)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relative)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relative)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relative))
            }
            .Where(static candidate => !string.IsNullOrWhiteSpace(candidate))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(static candidate => File.Exists(Path.Combine(candidate!, CurrentFileName)));
        return discovered is not null
            ? new SnapshotRootResolution(true, discovered)
            : new SnapshotRootResolution(required, null);
    }

    private static JsonDocument ParseStrictObject(byte[] payload, string label)
    {
        JsonDocument document = JsonDocument.Parse(
            payload,
            new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 32
            });
        if (document.RootElement.ValueKind != JsonValueKind.Object
            || !HasUniquePropertiesRecursively(document.RootElement))
        {
            document.Dispose();
            throw new InvalidDataException($"{label} is not a strict JSON object");
        }
        return document;
    }

    private static bool HasUniquePropertiesRecursively(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!names.Add(property.Name) || !HasUniquePropertiesRecursively(property.Value))
                {
                    return false;
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in element.EnumerateArray())
            {
                if (!HasUniquePropertiesRecursively(item))
                {
                    return false;
                }
            }
        }
        return true;
    }

    private static void ValidatePointerOutputs(JsonElement pointer, string snapshotId)
    {
        JsonElement outputs = RequireObject(pointer, "outputs");
        if (!ExactPropertySet(outputs, OutputNameSet))
        {
            throw new InvalidDataException("current public projection pointer inventory drifted");
        }
        foreach (string name in OutputNames)
        {
            RequireExactString(outputs, name, $"{snapshotId}/{name}");
        }
    }

    private static string ComputeSnapshotDigest(IReadOnlyDictionary<string, string> outputDigests)
    {
        using IncrementalHash digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (string name in OutputNames)
        {
            digest.AppendData(Encoding.UTF8.GetBytes(name));
            digest.AppendData([0]);
            digest.AppendData(Encoding.ASCII.GetBytes(outputDigests[name]));
            digest.AppendData([(byte)'\n']);
        }
        return Convert.ToHexString(digest.GetHashAndReset()).ToLowerInvariant();
    }

    private static void RequireDigest(byte[] payload, string expectedSha256, string label)
    {
        byte[] expected = Convert.FromHexString(expectedSha256);
        byte[] actual = SHA256.HashData(payload);
        if (!CryptographicOperations.FixedTimeEquals(actual, expected))
        {
            throw new InvalidDataException($"{label} digest drifted");
        }
    }

    private static JsonElement RequireObject(JsonElement parent, string propertyName)
        => parent.TryGetProperty(propertyName, out JsonElement value)
           && value.ValueKind == JsonValueKind.Object
            ? value
            : throw new InvalidDataException($"public projection {propertyName} is invalid");

    private static string RequireString(JsonElement parent, string propertyName)
        => parent.TryGetProperty(propertyName, out JsonElement value)
           && value.ValueKind == JsonValueKind.String
           && value.GetString()?.Trim() is { Length: > 0 } text
            ? text
            : throw new InvalidDataException($"public projection {propertyName} is invalid");

    private static string RequireLowercaseSha256(JsonElement parent, string propertyName)
    {
        string value = RequireString(parent, propertyName);
        return Sha256Pattern.IsMatch(value)
            ? value
            : throw new InvalidDataException($"public projection {propertyName} is invalid");
    }

    private static long RequireNonNegativeInt64(JsonElement parent, string propertyName)
        => parent.TryGetProperty(propertyName, out JsonElement value)
           && value.ValueKind == JsonValueKind.Number
           && value.TryGetInt64(out long parsed)
           && parsed >= 0
            ? parsed
            : throw new InvalidDataException($"public projection {propertyName} is invalid");

    private static void RequireExactString(JsonElement parent, string propertyName, string expected)
    {
        if (!string.Equals(RequireString(parent, propertyName), expected, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"public projection {propertyName} drifted");
        }
    }

    private static bool ExactPropertySet(JsonElement value, IReadOnlySet<string> expected)
    {
        string[] actual = value.EnumerateObject().Select(static property => property.Name).ToArray();
        return actual.Length == expected.Count && actual.All(expected.Contains);
    }

    private static bool ParseBoolean(string? value)
        => value?.Trim().ToLowerInvariant() is "1" or "true" or "yes" or "on";

    private sealed record SnapshotRootResolution(bool IsConfigured, string? Path);
}

public sealed record PublicProjectionOutputSnapshot(
    bool IsConfigured,
    bool IsValid,
    string? FailureReason,
    string? SnapshotId,
    string? SnapshotSha256,
    string? Path,
    string? Sha256,
    byte[]? Payload)
{
    internal static PublicProjectionOutputSnapshot Unconfigured()
        => new(false, false, null, null, null, null, null, null);

    internal static PublicProjectionOutputSnapshot Invalid(bool isConfigured, string reason)
        => new(isConfigured, false, reason, null, null, null, null, null);

    internal static PublicProjectionOutputSnapshot Valid(
        string snapshotId,
        string snapshotSha256,
        string path,
        string sha256,
        byte[] payload)
        => new(true, true, null, snapshotId, snapshotSha256, path, sha256, payload);
}
