using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Builds the portable release-runner authority inputs from the one Hub proof
/// authenticated through the public-projection CURRENT pointer. The handoff is
/// deliberately a projection: it preserves the authenticated source authority,
/// digest, commit, and timestamp without depending on machine-local source paths.
/// </summary>
public static class ReleaseUploadAuthorityHandoffBuilder
{
    public const string ReleaseChannelKey = "release_channel";
    public const string FlagshipReadinessKey = "flagship_readiness";
    public const string FleetQueueKey = "fleet_queue";
    public const string DesignQueueKey = "design_queue";
    public const string DesignSuccessorRegistryKey = "design_successor_registry";

    private const string HubLocalReleaseProofContract = "chummer6-hub.local_release_proof";
    private const string ReleaseChannelHandoffContract = "chummer.release-upload.release-channel-handoff/v1";
    private const string FlagshipReadinessHandoffContract = "chummer.release-upload.flagship-readiness-handoff/v1";
    private const string AuthorityCarrierContract = "chummer.release-upload.authority-carrier/v1";
    private static readonly Regex Sha256Pattern = new("^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
    private static readonly Regex CommitPattern = new("^[0-9a-f]{40}$", RegexOptions.CultureInvariant);
    private static readonly Regex AuthorityPattern = new(
        "^[a-z][a-z0-9+.-]*://\\S+$",
        RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly HashSet<string> ExpectedAuthorityKeys = new(
        [
            ReleaseChannelKey,
            FlagshipReadinessKey,
            FleetQueueKey,
            DesignQueueKey,
            DesignSuccessorRegistryKey
        ],
        StringComparer.Ordinal);

    public static ReleaseUploadAuthorityHandoff Build(PublicProjectionOutputSnapshot snapshot)
    {
        if (!snapshot.IsConfigured
            || !snapshot.IsValid
            || snapshot.Payload is not { Length: > 0 } proofBytes
            || snapshot.SnapshotId is not { Length: > 0 } snapshotId
            || snapshot.SnapshotSha256 is not { Length: > 0 } snapshotSha256
            || snapshot.Sha256 is not { Length: > 0 } proofSha256
            || !Sha256Pattern.IsMatch(snapshotSha256)
            || !Sha256Pattern.IsMatch(proofSha256))
        {
            throw new InvalidDataException("release upload authority handoff requires an authenticated CURRENT snapshot");
        }

        using JsonDocument proofDocument = ParseStrictObject(proofBytes);
        JsonElement proof = proofDocument.RootElement;
        RequireExactString(proof, "contract_name", HubLocalReleaseProofContract);
        string proofStatus = RequireString(proof, "status");
        if (proofStatus is not ("pass" or "passed"))
        {
            throw new InvalidDataException("release upload authority handoff requires a passing Hub proof");
        }

        JsonElement authorityInputs = RequireObject(proof, "authority_inputs");
        if (!ExactPropertySet(authorityInputs, ExpectedAuthorityKeys))
        {
            throw new InvalidDataException("release upload authority inventory drifted");
        }

        AuthorityMetadata releaseMetadata = ParseMetadata(
            authorityInputs,
            ReleaseChannelKey,
            requireCommitAndContract: true);
        AuthorityMetadata readinessMetadata = ParseMetadata(
            authorityInputs,
            FlagshipReadinessKey,
            requireCommitAndContract: true);
        AuthorityMetadata fleetMetadata = ParseMetadata(
            authorityInputs,
            FleetQueueKey,
            requireCommitAndContract: false);
        AuthorityMetadata designQueueMetadata = ParseMetadata(
            authorityInputs,
            DesignQueueKey,
            requireCommitAndContract: false);
        AuthorityMetadata designRegistryMetadata = ParseMetadata(
            authorityInputs,
            DesignSuccessorRegistryKey,
            requireCommitAndContract: false);

        byte[] releasePayload = BuildReleaseChannelProjection(
            proof,
            snapshotId,
            snapshotSha256,
            proofSha256,
            releaseMetadata);
        byte[] readinessPayload = BuildFlagshipReadinessProjection(
            proof,
            snapshotId,
            snapshotSha256,
            proofSha256,
            readinessMetadata);

        ReleaseUploadAuthorityInput[] inputs =
        [
            BuildInput(
                ReleaseChannelKey,
                "release-channel.json",
                "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
                "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
                "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
                snapshotSha256,
                releasePayload),
            BuildInput(
                FlagshipReadinessKey,
                "flagship-readiness.json",
                "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
                "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
                "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
                snapshotSha256,
                readinessPayload),
            BuildCarrierInput(
                FleetQueueKey,
                "fleet-queue.json",
                "CHUMMER_FLEET_QUEUE_STAGING_PATH",
                "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
                "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
                snapshotId,
                snapshotSha256,
                proofSha256,
                fleetMetadata),
            BuildCarrierInput(
                DesignQueueKey,
                "design-queue.json",
                "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
                "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
                "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
                snapshotId,
                snapshotSha256,
                proofSha256,
                designQueueMetadata),
            BuildCarrierInput(
                DesignSuccessorRegistryKey,
                "design-successor-registry.json",
                "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
                "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
                "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY",
                snapshotId,
                snapshotSha256,
                proofSha256,
                designRegistryMetadata)
        ];

        return new ReleaseUploadAuthorityHandoff(
            snapshotId,
            snapshotSha256,
            proofSha256,
            releaseMetadata.Commit!,
            readinessMetadata.Commit!,
            inputs);
    }

    private static ReleaseUploadAuthorityInput BuildCarrierInput(
        string key,
        string fileName,
        string pathEnvironmentVariable,
        string digestEnvironmentVariable,
        string authorityEnvironmentVariable,
        string snapshotId,
        string snapshotSha256,
        string proofSha256,
        AuthorityMetadata source)
    {
        byte[] payload = WriteCanonicalJson(writer =>
        {
            writer.WriteStartObject();
            writer.WriteString("contractName", AuthorityCarrierContract);
            writer.WriteString("kind", key);
            WriteHandoffLineage(writer, snapshotId, snapshotSha256, proofSha256, source);
            writer.WriteEndObject();
        });
        return BuildInput(
            key,
            fileName,
            pathEnvironmentVariable,
            digestEnvironmentVariable,
            authorityEnvironmentVariable,
            snapshotSha256,
            payload);
    }

    private static ReleaseUploadAuthorityInput BuildInput(
        string key,
        string fileName,
        string pathEnvironmentVariable,
        string digestEnvironmentVariable,
        string authorityEnvironmentVariable,
        string snapshotSha256,
        byte[] payload)
    {
        string digest = Convert.ToHexStringLower(SHA256.HashData(payload));
        string authority = $"current-snapshot://{snapshotSha256}/{key}/{digest}";
        return new ReleaseUploadAuthorityInput(
            key,
            fileName,
            pathEnvironmentVariable,
            digestEnvironmentVariable,
            authorityEnvironmentVariable,
            authority,
            digest,
            payload);
    }

    private static byte[] BuildReleaseChannelProjection(
        JsonElement proof,
        string snapshotId,
        string snapshotSha256,
        string proofSha256,
        AuthorityMetadata source)
    {
        JsonElement release = RequireObject(proof, "release_channel");
        string channel = RequireConsistentAlias(release, "channelId", "channel");
        string version = RequireConsistentAlias(release, "releaseVersion", "version");
        string rolloutState = RequireString(release, "rolloutState");
        string supportabilityState = RequireString(release, "supportabilityState");
        string publishedAt = RequireString(release, "publishedAt");
        if (!DateTimeOffset.TryParse(
                publishedAt,
                System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.RoundtripKind,
                out _))
        {
            throw new InvalidDataException("release upload publishedAt is invalid");
        }

        string[] installerIds = RequireCanonicalStringArrayWithOptionalAlias(
            proof,
            "proof_routes",
            "proofRoutes")
            .Where(static route => route.StartsWith("/downloads/install/", StringComparison.Ordinal))
            .Select(static route => route["/downloads/install/".Length..])
            .Where(static artifactId => artifactId.Length > 0 && !artifactId.Contains('/'))
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static artifactId => artifactId, StringComparer.Ordinal)
            .ToArray();
        if (installerIds.Length == 0)
        {
            throw new InvalidDataException("release upload authority handoff has no installer inventory");
        }

        return WriteCanonicalJson(writer =>
        {
            writer.WriteStartObject();
            writer.WriteString("contractName", ReleaseChannelHandoffContract);
            writer.WriteString("generatedAt", source.GeneratedAt);
            writer.WriteString("sourceCommit", source.Commit);
            writer.WriteString("status", "snapshot_projection");
            writer.WriteString("channelId", channel);
            writer.WriteString("releaseVersion", version);
            writer.WriteString("rolloutState", rolloutState);
            writer.WriteString("supportabilityState", supportabilityState);
            writer.WriteString("publishedAt", publishedAt);
            writer.WriteStartArray("artifacts");
            foreach (string installerId in installerIds)
            {
                writer.WriteStartObject();
                writer.WriteString("artifactId", installerId);
                writer.WriteString("kind", "installer");
                writer.WriteEndObject();
            }
            writer.WriteEndArray();
            WriteHandoffLineage(writer, snapshotId, snapshotSha256, proofSha256, source);
            writer.WriteEndObject();
        });
    }

    private static byte[] BuildFlagshipReadinessProjection(
        JsonElement proof,
        string snapshotId,
        string snapshotSha256,
        string proofSha256,
        AuthorityMetadata source)
    {
        JsonElement readiness = RequireObject(proof, "desktop_client_readiness");
        string status = RequireString(readiness, "status");
        string scopedStatus = RequireString(readiness, "scoped_status");
        string completionStatus = RequireString(readiness, "completion_audit_status");
        string[] gaps = RequireArray(readiness, "missing_coverage_keys")
            .EnumerateArray()
            .Select(static value => value.ValueKind == JsonValueKind.String
                ? value.GetString()?.Trim() ?? string.Empty
                : throw new InvalidDataException("release upload readiness coverage is invalid"))
            .Where(static value => value.Length > 0)
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToArray();
        string derivedReason =
            $"Projected from authenticated CURRENT snapshot {snapshotId}; full reasoning remains in Hub proof {proofSha256}.";

        return WriteCanonicalJson(writer =>
        {
            writer.WriteStartObject();
            writer.WriteString("contractName", FlagshipReadinessHandoffContract);
            writer.WriteString("generatedAt", source.GeneratedAt);
            writer.WriteString("sourceCommit", source.Commit);
            writer.WriteString("status", status);
            writer.WriteString("scoped_status", scopedStatus);
            writer.WriteStartArray("scoped_warning_keys");
            foreach (string gap in gaps)
            {
                writer.WriteStringValue(gap);
            }
            writer.WriteEndArray();
            writer.WriteStartObject("flagship_readiness_audit");
            writer.WriteString("status", status);
            writer.WriteString("reason", derivedReason);
            writer.WriteStartArray("scoped_coverage_gap_keys");
            foreach (string gap in gaps)
            {
                writer.WriteStringValue(gap);
            }
            writer.WriteEndArray();
            writer.WriteEndObject();
            writer.WriteStartObject("completion_audit");
            writer.WriteString("status", completionStatus);
            writer.WriteString("reason", derivedReason);
            writer.WriteEndObject();
            WriteHandoffLineage(writer, snapshotId, snapshotSha256, proofSha256, source);
            writer.WriteEndObject();
        });
    }

    private static void WriteHandoffLineage(
        Utf8JsonWriter writer,
        string snapshotId,
        string snapshotSha256,
        string proofSha256,
        AuthorityMetadata source)
    {
        writer.WriteStartObject("handoff");
        writer.WriteString("snapshotId", snapshotId);
        writer.WriteString("snapshotSha256", snapshotSha256);
        writer.WriteString("hubLocalReleaseProofSha256", proofSha256);
        writer.WriteString("sourceAuthority", source.Authority);
        writer.WriteString("sourceSha256", source.Sha256);
        if (source.Contract is { Length: > 0 })
        {
            writer.WriteString("sourceContract", source.Contract);
        }
        if (source.Commit is { Length: > 0 })
        {
            writer.WriteString("sourceCommit", source.Commit);
        }
        if (source.GeneratedAt is { Length: > 0 })
        {
            writer.WriteString("sourceGeneratedAt", source.GeneratedAt);
        }
        writer.WriteEndObject();
    }

    private static AuthorityMetadata ParseMetadata(
        JsonElement inputs,
        string key,
        bool requireCommitAndContract)
    {
        JsonElement metadata = RequireObject(inputs, key);
        string authority = RequireString(metadata, "authority");
        if (!AuthorityPattern.IsMatch(authority)
            || authority.StartsWith("file://", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"release upload {key} authority is invalid");
        }
        string sha256 = RequireString(metadata, "sha256");
        if (!Sha256Pattern.IsMatch(sha256))
        {
            throw new InvalidDataException($"release upload {key} digest is invalid");
        }

        string? contract = null;
        string? commit = null;
        string? generatedAt = null;
        if (requireCommitAndContract)
        {
            contract = RequireString(metadata, "contract");
            commit = RequireString(metadata, "commit");
            generatedAt = RequireString(metadata, "generated_at");
            if (!CommitPattern.IsMatch(commit)
                || !DateTimeOffset.TryParse(
                    generatedAt,
                    System.Globalization.CultureInfo.InvariantCulture,
                    System.Globalization.DateTimeStyles.RoundtripKind,
                    out _))
            {
                throw new InvalidDataException($"release upload {key} source identity is invalid");
            }
        }
        return new AuthorityMetadata(authority, sha256, contract, commit, generatedAt);
    }

    private static byte[] WriteCanonicalJson(Action<Utf8JsonWriter> write)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions { Indented = false }))
        {
            write(writer);
            writer.Flush();
        }
        stream.WriteByte((byte)'\n');
        return stream.ToArray();
    }

    private static JsonDocument ParseStrictObject(byte[] payload)
    {
        JsonDocument document = JsonDocument.Parse(
            payload,
            new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 64
            });
        if (document.RootElement.ValueKind != JsonValueKind.Object
            || !HasUniquePropertiesRecursively(document.RootElement))
        {
            document.Dispose();
            throw new InvalidDataException("release upload Hub proof is not a strict JSON object");
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

    private static JsonElement RequireObject(JsonElement parent, string propertyName)
        => parent.TryGetProperty(propertyName, out JsonElement value)
           && value.ValueKind == JsonValueKind.Object
            ? value
            : throw new InvalidDataException($"release upload {propertyName} is invalid");

    private static JsonElement RequireArray(JsonElement parent, string propertyName)
        => parent.TryGetProperty(propertyName, out JsonElement value)
           && value.ValueKind == JsonValueKind.Array
            ? value
            : throw new InvalidDataException($"release upload {propertyName} is invalid");

    private static string[] RequireCanonicalStringArrayWithOptionalAlias(
        JsonElement parent,
        string canonicalName,
        string compatibilityName)
    {
        if (!parent.TryGetProperty(canonicalName, out JsonElement canonical))
        {
            throw new InvalidDataException(
                $"release upload canonical {canonicalName} is missing");
        }

        string[] canonicalValues = RequireStrictStringArray(canonical, canonicalName);
        if (parent.TryGetProperty(compatibilityName, out JsonElement compatibility))
        {
            string[] compatibilityValues = RequireStrictStringArray(
                compatibility,
                compatibilityName);
            if (!canonicalValues.SequenceEqual(compatibilityValues, StringComparer.Ordinal))
            {
                throw new InvalidDataException(
                    $"release upload {canonicalName}/{compatibilityName} aliases disagree");
            }
        }
        return canonicalValues;
    }

    private static string[] RequireStrictStringArray(JsonElement value, string propertyName)
    {
        if (value.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException($"release upload {propertyName} is invalid");
        }

        string[] values = value.EnumerateArray()
            .Select(item => RequireUnpaddedRoute(item, propertyName))
            .ToArray();
        if (values.Length == 0
            || values.Distinct(StringComparer.Ordinal).Count() != values.Length)
        {
            throw new InvalidDataException(
                $"release upload {propertyName} route inventory is invalid");
        }
        return values;
    }

    private static string RequireUnpaddedRoute(JsonElement value, string propertyName)
    {
        if (value.ValueKind != JsonValueKind.String
            || value.GetString() is not { Length: > 0 } route
            || !string.Equals(route, route.Trim(), StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"release upload {propertyName} contains an invalid or padded route");
        }
        return route;
    }

    private static string RequireString(JsonElement parent, string propertyName)
        => parent.TryGetProperty(propertyName, out JsonElement value)
           && value.ValueKind == JsonValueKind.String
           && value.GetString()?.Trim() is { Length: > 0 } text
            ? text
            : throw new InvalidDataException($"release upload {propertyName} is invalid");

    private static string RequireConsistentAlias(JsonElement parent, string leftName, string rightName)
    {
        string left = RequireString(parent, leftName);
        string right = RequireString(parent, rightName);
        return string.Equals(left, right, StringComparison.Ordinal)
            ? left
            : throw new InvalidDataException($"release upload {leftName}/{rightName} aliases disagree");
    }

    private static void RequireExactString(JsonElement parent, string propertyName, string expected)
    {
        if (!string.Equals(RequireString(parent, propertyName), expected, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"release upload {propertyName} drifted");
        }
    }

    private static bool ExactPropertySet(JsonElement value, IReadOnlySet<string> expected)
    {
        string[] actual = value.EnumerateObject().Select(static property => property.Name).ToArray();
        return actual.Length == expected.Count && actual.All(expected.Contains);
    }

    private sealed record AuthorityMetadata(
        string Authority,
        string Sha256,
        string? Contract,
        string? Commit,
        string? GeneratedAt);
}

public sealed record ReleaseUploadAuthorityHandoff(
    string SnapshotId,
    string SnapshotSha256,
    string HubLocalReleaseProofSha256,
    string ReleaseChannelExpectedCommit,
    string FlagshipReadinessExpectedCommit,
    IReadOnlyList<ReleaseUploadAuthorityInput> Inputs);

public sealed record ReleaseUploadAuthorityInput(
    string Key,
    string FileName,
    string PathEnvironmentVariable,
    string DigestEnvironmentVariable,
    string AuthorityEnvironmentVariable,
    string Authority,
    string Sha256,
    byte[] Payload);
