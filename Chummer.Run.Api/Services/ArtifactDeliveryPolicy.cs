using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public static class ArtifactDeliveryRoles
{
    public const string Primary = "primary";
    public const string Payload = "payload";
    public const string PayloadMetadata = "payload_metadata";

    public static bool IsKnown(string? role)
        => role is Primary or Payload or PayloadMetadata;
}

public enum ArtifactDeliveryFailure
{
    None,
    NotFound,
    Revoked,
    InvalidContract,
    RevocationTruthUnavailable
}

public sealed record ArtifactDeliveryBinding(
    ReleaseShelfSnapshot Snapshot,
    PublicReleaseManifestDto Manifest,
    PublicReleaseArtifactDto Artifact,
    string Role,
    string FileName,
    string Sha256,
    long SizeBytes,
    string InstallAccessClass)
{
    public string ArtifactId => Artifact.Id;
    public bool RequiresAccount => string.Equals(
        InstallAccessClass,
        InstallAccessClasses.AccountRequired,
        StringComparison.Ordinal);
}

public sealed record ArtifactDeliveryResolution(
    ArtifactDeliveryBinding? Binding,
    ArtifactDeliveryFailure Failure,
    string Code)
{
    public bool Allowed => Binding is not null && Failure == ArtifactDeliveryFailure.None;
}

public sealed record ArtifactDeliveryDecision(
    bool Allowed,
    ArtifactDeliveryFailure Failure,
    string Code);

/// <summary>
/// The sole runtime authority for mapping an artifact role to immutable bytes. It
/// combines exact manifest/inventory bindings with current global revocation truth;
/// credentials never bypass this decision.
/// </summary>
public sealed class ArtifactDeliveryPolicy
{
    private const string RevokedIdsKey = "CHUMMER_RELEASE_REVOKED_ARTIFACT_IDS";
    private const string RevokedDigestsKey = "CHUMMER_RELEASE_REVOKED_SHA256";
    private const string PublicDisabledIdsKey = "CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS";
    private const string ReleaseDisabledIdsKey = "CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS";
    private const string ForceAccountRequiredKey = "CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS";

    private readonly PublicReleaseManifestService _releases;
    private readonly IConfiguration _configuration;

    public ArtifactDeliveryPolicy(
        PublicReleaseManifestService releases,
        IConfiguration configuration)
    {
        _releases = releases;
        _configuration = configuration;
    }

    public ArtifactDeliveryResolution ResolveByArtifactId(
        ReleaseShelfSnapshot snapshot,
        string? artifactId,
        string role = ArtifactDeliveryRoles.Primary)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (string.IsNullOrWhiteSpace(artifactId) || !ArtifactDeliveryRoles.IsKnown(role))
        {
            return Denied(ArtifactDeliveryFailure.NotFound, "artifact_not_found");
        }

        PublicReleaseManifestDto manifest;
        try
        {
            manifest = _releases.LoadDeliveryManifest(snapshot);
        }
        catch
        {
            return Denied(ArtifactDeliveryFailure.InvalidContract, "artifact_manifest_invalid");
        }

        PublicReleaseArtifactDto[] matches = manifest.Downloads
            .Where(candidate => string.Equals(
                candidate.Id?.Trim(),
                artifactId.Trim(),
                StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length == 0)
        {
            return Denied(ArtifactDeliveryFailure.NotFound, "artifact_not_found");
        }

        if (matches.Length != 1)
        {
            return Denied(ArtifactDeliveryFailure.InvalidContract, "artifact_identity_ambiguous");
        }

        return Resolve(snapshot, manifest, matches[0], role);
    }

    public ArtifactDeliveryResolution ResolveByPath(
        ReleaseShelfSnapshot snapshot,
        string? requestedPath)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string? fileName = NormalizeRequestedFileName(requestedPath);
        if (fileName is null)
        {
            return Denied(ArtifactDeliveryFailure.NotFound, "artifact_not_found");
        }

        PublicReleaseManifestDto manifest;
        try
        {
            manifest = _releases.LoadDeliveryManifest(snapshot);
        }
        catch
        {
            return Denied(ArtifactDeliveryFailure.InvalidContract, "artifact_manifest_invalid");
        }

        List<(PublicReleaseArtifactDto Artifact, string Role)> matches = [];
        foreach (PublicReleaseArtifactDto artifact in manifest.Downloads)
        {
            if (string.Equals(artifact.FileName?.Trim(), fileName, StringComparison.Ordinal))
            {
                matches.Add((artifact, ArtifactDeliveryRoles.Primary));
            }

            if (!string.IsNullOrWhiteSpace(artifact.PayloadFileName))
            {
                string payloadName = artifact.PayloadFileName.Trim();
                if (string.Equals(payloadName, fileName, StringComparison.Ordinal))
                {
                    matches.Add((artifact, ArtifactDeliveryRoles.Payload));
                }

                if (string.Equals(payloadName + ".json", fileName, StringComparison.Ordinal))
                {
                    matches.Add((artifact, ArtifactDeliveryRoles.PayloadMetadata));
                }
            }
        }

        return matches.Count switch
        {
            0 => Denied(ArtifactDeliveryFailure.NotFound, "artifact_not_found"),
            1 => Resolve(snapshot, manifest, matches[0].Artifact, matches[0].Role),
            _ => Denied(ArtifactDeliveryFailure.InvalidContract, "artifact_path_ambiguous")
        };
    }

    public PublicReleaseManifestDto FilterRevokedArtifacts(
        ReleaseShelfSnapshot snapshot,
        PublicReleaseManifestDto manifest)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(manifest);
        return manifest with
        {
            Downloads = manifest.Downloads
                .Where(artifact => Resolve(snapshot, manifest, artifact, ArtifactDeliveryRoles.Primary).Allowed)
                .ToArray()
        };
    }

    public ArtifactDeliveryDecision EvaluateGlobalRevocation(
        string? artifactId,
        string? sha256)
    {
        string normalizedId = (artifactId ?? string.Empty).Trim();
        string normalizedSha256 = (sha256 ?? string.Empty).Trim().ToLowerInvariant();
        if (normalizedId.Length == 0
            || normalizedId.Length > 128
            || !normalizedId.All(static character => char.IsAsciiLetterOrDigit(character)
                || character is '-' or '_' or '.')
            || !IsSha256(normalizedSha256))
        {
            return new ArtifactDeliveryDecision(
                false,
                ArtifactDeliveryFailure.InvalidContract,
                "artifact_delivery_contract_invalid");
        }

        if (!TryLoadGlobalRevocations(out ArtifactRevocationSet? revocations))
        {
            return new ArtifactDeliveryDecision(
                false,
                ArtifactDeliveryFailure.RevocationTruthUnavailable,
                "artifact_revocation_truth_unavailable");
        }

        if (revocations!.AllArtifactsRevoked
            || revocations.ArtifactIds.Contains(normalizedId)
            || revocations.Sha256.Contains(normalizedSha256))
        {
            return new ArtifactDeliveryDecision(
                false,
                ArtifactDeliveryFailure.Revoked,
                "artifact_revoked");
        }

        return new ArtifactDeliveryDecision(true, ArtifactDeliveryFailure.None, "allowed");
    }

    public IReadOnlyList<InstallBootstrapArtifactBinding> BuildCredentialBindings(
        ReleaseShelfSnapshot snapshot,
        IEnumerable<PublicReleaseArtifactDto> artifacts)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var bindings = new List<InstallBootstrapArtifactBinding>();
        foreach (PublicReleaseArtifactDto artifact in artifacts)
        {
            ArtifactDeliveryResolution primary = ResolveByArtifactId(
                snapshot,
                artifact.Id,
                ArtifactDeliveryRoles.Primary);
            if (!primary.Allowed)
            {
                throw new InvalidOperationException(
                    $"artifact credential binding is unavailable ({primary.Code}).");
            }

            bindings.Add(new InstallBootstrapArtifactBinding(
                primary.Binding!.ArtifactId,
                primary.Binding.Sha256,
                primary.Binding.Role));
            if (string.IsNullOrWhiteSpace(artifact.PayloadFileName))
            {
                continue;
            }

            foreach (string role in new[] { ArtifactDeliveryRoles.Payload, ArtifactDeliveryRoles.PayloadMetadata })
            {
                ArtifactDeliveryResolution resolution = ResolveByArtifactId(snapshot, artifact.Id, role);
                if (!resolution.Allowed)
                {
                    throw new InvalidOperationException(
                        $"artifact credential binding is unavailable ({resolution.Code}).");
                }

                bindings.Add(new InstallBootstrapArtifactBinding(
                    resolution.Binding!.ArtifactId,
                    resolution.Binding.Sha256,
                    resolution.Binding.Role));
            }
        }

        return bindings;
    }

    public ReleaseShelfVerifiedFile? OpenVerifiedFile(ArtifactDeliveryBinding binding)
    {
        ArgumentNullException.ThrowIfNull(binding);
        ReleaseShelfVerifiedFile? verified = binding.Snapshot.OpenVerifiedFile(
            $"files/{binding.FileName}");
        if (verified is null)
        {
            return null;
        }

        try
        {
            if (verified.SizeBytes != binding.SizeBytes)
            {
                verified.Dispose();
                return null;
            }

            if (!binding.Snapshot.IsLegacy)
            {
                if (verified.ExpectedSha256 is null
                    || !FixedTimeDigestEquals(verified.ExpectedSha256, binding.Sha256)
                    || verified.Stream.Length != binding.SizeBytes)
                {
                    verified.Dispose();
                    return null;
                }

                return verified;
            }

            string actualSha256 = Convert.ToHexStringLower(SHA256.HashData(verified.Stream));
            if (!FixedTimeDigestEquals(actualSha256, binding.Sha256)
                || verified.Stream.Length != binding.SizeBytes)
            {
                verified.Dispose();
                return null;
            }

            verified.Stream.Position = 0;
            return verified;
        }
        catch
        {
            verified.Dispose();
            return null;
        }
    }

    private ArtifactDeliveryResolution Resolve(
        ReleaseShelfSnapshot snapshot,
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string role)
    {
        if (!TryBuildBinding(snapshot, manifest, artifact, role, out ArtifactDeliveryBinding? binding))
        {
            return Denied(ArtifactDeliveryFailure.InvalidContract, "artifact_delivery_contract_invalid");
        }

        if (!TryLoadGlobalRevocations(out ArtifactRevocationSet? revocations))
        {
            return Denied(
                ArtifactDeliveryFailure.RevocationTruthUnavailable,
                "artifact_revocation_truth_unavailable");
        }

        if (revocations!.AllArtifactsRevoked
            || revocations.ArtifactIds.Contains(binding!.ArtifactId)
            || revocations.Sha256.Contains(binding.Sha256))
        {
            return Denied(ArtifactDeliveryFailure.Revoked, "artifact_revoked");
        }

        return new ArtifactDeliveryResolution(binding!, ArtifactDeliveryFailure.None, "allowed");
    }

    private bool TryBuildBinding(
        ReleaseShelfSnapshot snapshot,
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string role,
        out ArtifactDeliveryBinding? binding)
    {
        binding = null;
        if (string.IsNullOrWhiteSpace(artifact.Id)
            || !ArtifactDeliveryRoles.IsKnown(role)
            || !TryNormalizeAccessClass(artifact.InstallAccessClass, out string? accessClass))
        {
            return false;
        }

        if (ParseBooleanSetting(_configuration[ForceAccountRequiredKey]))
        {
            accessClass = InstallAccessClasses.AccountRequired;
        }

        string? fileName;
        string? sha256;
        long? sizeBytes;
        if (role == ArtifactDeliveryRoles.Primary)
        {
            fileName = artifact.FileName;
            sha256 = artifact.Sha256;
            sizeBytes = artifact.SizeBytes;
        }
        else if (role == ArtifactDeliveryRoles.Payload)
        {
            fileName = artifact.PayloadFileName;
            sha256 = artifact.PayloadSha256;
            sizeBytes = artifact.PayloadSizeBytes;
        }
        else
        {
            if (string.IsNullOrWhiteSpace(artifact.PayloadFileName)
                || !TryValidatePayloadSidecar(snapshot, manifest, artifact, out string? metadataSha, out long metadataSize))
            {
                return false;
            }

            fileName = artifact.PayloadFileName.Trim() + ".json";
            sha256 = metadataSha;
            sizeBytes = metadataSize;
        }

        if (!TryNormalizeFileBinding(fileName, sha256, sizeBytes, out string? normalizedFileName, out string? normalizedSha, out long normalizedSize)
            || !TryBindInventory(snapshot, normalizedFileName!, normalizedSha!, normalizedSize))
        {
            return false;
        }

        binding = new ArtifactDeliveryBinding(
            snapshot,
            manifest,
            artifact,
            role,
            normalizedFileName!,
            normalizedSha!,
            normalizedSize,
            accessClass!);
        return true;
    }

    private static bool TryValidatePayloadSidecar(
        ReleaseShelfSnapshot snapshot,
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        out string? metadataSha256,
        out long metadataSize)
    {
        metadataSha256 = null;
        metadataSize = 0;
        string payloadFileName = (artifact.PayloadFileName ?? string.Empty).Trim();
        string metadataFileName = payloadFileName + ".json";
        byte[]? bytes = snapshot.ReadVerifiedFileBytes($"files/{metadataFileName}", 64 * 1024);
        if (bytes is null)
        {
            return false;
        }

        if (!PayloadSidecarContractValidator.TryValidate(
                bytes,
                artifact.FileName,
                payloadFileName,
                artifact.PayloadDownloadUrl,
                artifact.PayloadSha256,
                artifact.PayloadSizeBytes,
                manifest.Version,
                allowMutableIncomingUrl: snapshot.IsLegacy,
                out _))
        {
            return false;
        }

        metadataSha256 = Convert.ToHexStringLower(SHA256.HashData(bytes));
        metadataSize = bytes.LongLength;
        return true;
    }

    private bool TryLoadGlobalRevocations(out ArtifactRevocationSet? revocations)
    {
        revocations = null;
        var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var digests = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (!TryLoadConfiguredIds(_configuration[RevokedIdsKey], ids)
            || !TryLoadConfiguredIds(_configuration[PublicDisabledIdsKey], ids)
            || !TryLoadConfiguredIds(_configuration[ReleaseDisabledIdsKey], ids)
            || !TryLoadConfiguredDigests(_configuration[RevokedDigestsKey], digests))
        {
            return false;
        }

        ReleaseShelfSnapshot current;
        string? json;
        try
        {
            current = _releases.CaptureUnpinnedActiveShelfSnapshot();
            json = _releases.LoadCanonicalManifestJson(current);
        }
        catch
        {
            return false;
        }

        if (string.IsNullOrWhiteSpace(json))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(json);
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("artifacts", out JsonElement artifacts)
                || artifacts.ValueKind != JsonValueKind.Array)
            {
                return false;
            }

            var currentDigestsById = new Dictionary<string, HashSet<string>>(StringComparer.OrdinalIgnoreCase);
            bool releaseRevoked = IsRevoked(root);
            foreach (JsonElement artifact in artifacts.EnumerateArray())
            {
                if (artifact.ValueKind != JsonValueKind.Object
                    || !TryJsonString(artifact, "artifactId", out string? artifactId))
                {
                    return false;
                }

                if (!currentDigestsById.TryGetValue(artifactId!, out HashSet<string>? artifactDigests))
                {
                    artifactDigests = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    currentDigestsById[artifactId!] = artifactDigests;
                }

                AddJsonDigest(artifact, "sha256", artifactDigests);
                AddJsonDigest(artifact, "payloadSha256", artifactDigests);
                if (releaseRevoked || IsRevoked(artifact))
                {
                    ids.Add(artifactId!);
                    digests.UnionWith(artifactDigests);
                }
            }

            if (root.TryGetProperty("desktopTupleCoverage", out JsonElement coverage)
                && coverage.ValueKind == JsonValueKind.Object
                && coverage.TryGetProperty("desktopRouteTruth", out JsonElement routes)
                && routes.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement route in routes.EnumerateArray())
                {
                    if (route.ValueKind != JsonValueKind.Object || !IsRevoked(route))
                    {
                        continue;
                    }

                    if (!TryJsonString(route, "artifactId", out string? artifactId))
                    {
                        return false;
                    }

                    ids.Add(artifactId!);
                    if (currentDigestsById.TryGetValue(artifactId!, out HashSet<string>? artifactDigests))
                    {
                        digests.UnionWith(artifactDigests);
                    }
                }
            }

            revocations = new ArtifactRevocationSet(releaseRevoked, ids, digests);
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool IsRevoked(JsonElement value)
    {
        foreach (string property in new[]
                 {
                     "status", "artifactStatus", "artifactRolloutState", "rolloutState",
                     "compatibilityState", "effectiveRolloutState",
                     "revokeState", "promotionState", "publicationState"
                 })
        {
            if (TryJsonString(value, property, out string? state)
                && string.Equals(NormalizeToken(state), "revoked", StringComparison.Ordinal))
            {
                return true;
            }
        }

        return value.TryGetProperty("revoked", out JsonElement revoked)
               && revoked.ValueKind == JsonValueKind.True;
    }

    private static bool TryBindInventory(
        ReleaseShelfSnapshot snapshot,
        string fileName,
        string sha256,
        long sizeBytes)
    {
        if (snapshot.IsLegacy)
        {
            return true;
        }

        return snapshot.Inventory.TryGetValue($"files/{fileName}", out ReleaseShelfInventoryEntry? inventory)
               && inventory.SizeBytes == sizeBytes
               && FixedTimeDigestEquals(inventory.Sha256, sha256);
    }

    private static bool TryNormalizeFileBinding(
        string? fileName,
        string? sha256,
        long? sizeBytes,
        out string? normalizedFileName,
        out string? normalizedSha256,
        out long normalizedSize)
    {
        normalizedFileName = (fileName ?? string.Empty).Trim();
        normalizedSha256 = (sha256 ?? string.Empty).Trim().ToLowerInvariant();
        normalizedSize = sizeBytes ?? -1;
        return normalizedFileName.Length > 0
               && string.Equals(Path.GetFileName(normalizedFileName), normalizedFileName, StringComparison.Ordinal)
               && !normalizedFileName.Contains('/', StringComparison.Ordinal)
               && !normalizedFileName.Contains('\\', StringComparison.Ordinal)
               && IsSha256(normalizedSha256)
               && normalizedSize >= 0;
    }

    private static bool TryNormalizeAccessClass(string? value, out string? normalized)
    {
        normalized = NormalizeToken(value);
        return normalized is InstallAccessClasses.OpenPublic
            or InstallAccessClasses.AccountRecommended
            or InstallAccessClasses.AccountRequired;
    }

    private static string? NormalizeRequestedFileName(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        string normalized = path.Trim().TrimStart('/');
        return normalized.Length > 0
               && string.Equals(Path.GetFileName(normalized), normalized, StringComparison.Ordinal)
               && !normalized.Contains('\\', StringComparison.Ordinal)
               && !normalized.Contains("..", StringComparison.Ordinal)
            ? normalized
            : null;
    }

    private static bool TryLoadConfiguredIds(string? value, ISet<string> destination)
    {
        foreach (string token in SplitConfigurationList(value))
        {
            if (token.Length > 128
                || !token.All(static character => char.IsAsciiLetterOrDigit(character)
                    || character is '-' or '_' or '.'))
            {
                return false;
            }

            destination.Add(token);
        }

        return true;
    }

    private static bool TryLoadConfiguredDigests(string? value, ISet<string> destination)
    {
        foreach (string token in SplitConfigurationList(value))
        {
            string digest = token.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
                ? token[7..]
                : token;
            digest = digest.ToLowerInvariant();
            if (!IsSha256(digest))
            {
                return false;
            }

            destination.Add(digest);
        }

        return true;
    }

    private static IEnumerable<string> SplitConfigurationList(string? value)
        => (value ?? string.Empty)
            .Split([',', ';', ' ', '\r', '\n', '\t'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    private static bool ParseBooleanSetting(string? value)
        => value?.Trim().ToLowerInvariant() is "1" or "true" or "yes" or "on";

    private static void AddJsonDigest(JsonElement value, string property, ISet<string> destination)
    {
        if (TryJsonString(value, property, out string? candidate))
        {
            string digest = candidate!.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
                ? candidate[7..]
                : candidate;
            digest = digest.ToLowerInvariant();
            if (IsSha256(digest))
            {
                destination.Add(digest);
            }
        }
    }

    private static bool TryJsonString(JsonElement value, string property, out string? result)
    {
        result = null;
        if (!value.TryGetProperty(property, out JsonElement child)
            || child.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        result = child.GetString()?.Trim();
        return !string.IsNullOrWhiteSpace(result);
    }

    private static bool IsSha256(string? value)
        => value?.Length == 64
           && value.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static bool FixedTimeDigestEquals(string left, string right)
    {
        byte[] leftBytes = System.Text.Encoding.ASCII.GetBytes(left.ToLowerInvariant());
        byte[] rightBytes = System.Text.Encoding.ASCII.GetBytes(right.ToLowerInvariant());
        return leftBytes.Length == rightBytes.Length
               && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private static string NormalizeToken(string? value)
        => (value ?? string.Empty).Trim().Replace('-', '_').ToLowerInvariant();

    private static ArtifactDeliveryResolution Denied(ArtifactDeliveryFailure failure, string code)
        => new(null, failure, code);

    private sealed record ArtifactRevocationSet(
        bool AllArtifactsRevoked,
        HashSet<string> ArtifactIds,
        HashSet<string> Sha256);
}

internal static class PayloadSidecarContractValidator
{
    private static readonly string[] RequiredProperties =
    [
        "contractName",
        "fileName",
        "downloadUrl",
        "sha256",
        "sizeBytes",
        "installerFileName",
        "releaseVersion"
    ];

    public static bool TryValidate(
        byte[] bytes,
        string? installerFileName,
        string? payloadFileName,
        string? payloadDownloadUrl,
        string? payloadSha256,
        long? payloadSizeBytes,
        string? releaseVersion,
        bool allowMutableIncomingUrl,
        out string? failure)
    {
        failure = null;
        try
        {
            using JsonDocument document = JsonDocument.Parse(bytes);
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                return Fail("payload sidecar must be a JSON object", out failure);
            }

            var properties = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in root.EnumerateObject())
            {
                if (!properties.Add(property.Name))
                {
                    return Fail("payload sidecar contains duplicate properties", out failure);
                }
            }

            if (!properties.SetEquals(RequiredProperties))
            {
                return Fail("payload sidecar property set is noncanonical", out failure);
            }

            string expectedPayloadName = (payloadFileName ?? string.Empty).Trim();
            string expectedInstallerName = (installerFileName ?? string.Empty).Trim();
            string expectedDigest = (payloadSha256 ?? string.Empty).Trim().ToLowerInvariant();
            string expectedVersion = (releaseVersion ?? string.Empty).Trim();
            if (!TryString(root, "contractName", out string? contractName)
                || !string.Equals(contractName, "chummer6-ui.windows_bootstrap_payload", StringComparison.Ordinal)
                || !TryString(root, "fileName", out string? actualPayloadName)
                || !string.Equals(actualPayloadName, expectedPayloadName, StringComparison.Ordinal)
                || !TryString(root, "installerFileName", out string? actualInstallerName)
                || !string.Equals(actualInstallerName, expectedInstallerName, StringComparison.Ordinal)
                || !TryString(root, "sha256", out string? actualDigest)
                || !string.Equals(actualDigest!.ToLowerInvariant(), expectedDigest, StringComparison.Ordinal)
                || !TryString(root, "releaseVersion", out string? actualVersion)
                || !string.Equals(actualVersion, expectedVersion, StringComparison.Ordinal)
                || !root.TryGetProperty("sizeBytes", out JsonElement size)
                || !size.TryGetInt64(out long actualSize)
                || actualSize != payloadSizeBytes)
            {
                return Fail("payload sidecar identity does not match its manifests", out failure);
            }

            if (!TryString(root, "downloadUrl", out string? actualUrl)
                || !IsMatchingGovernedUrl(
                    actualUrl!,
                    payloadDownloadUrl,
                    expectedPayloadName,
                    allowMutableIncomingUrl))
            {
                return Fail("payload sidecar URL does not match its governed payload route", out failure);
            }

            return true;
        }
        catch (JsonException)
        {
            return Fail("payload sidecar JSON is malformed", out failure);
        }
    }

    private static bool IsMatchingGovernedUrl(
        string actual,
        string? manifestUrl,
        string payloadFileName,
        bool allowMutableIncomingUrl)
    {
        string expectedManifestUrl = (manifestUrl ?? string.Empty).Trim();
        if (actual.Contains('?', StringComparison.Ordinal)
            || actual.Contains('#', StringComparison.Ordinal)
            || actual.Contains('\\', StringComparison.Ordinal))
        {
            return false;
        }

        if (string.Equals(actual, expectedManifestUrl, StringComparison.Ordinal)
            && (allowMutableIncomingUrl || IsImmutablePayloadRoute(actual, payloadFileName)))
        {
            return true;
        }

        if (!Uri.TryCreate(actual, UriKind.Absolute, out Uri? absolute)
            || !string.Equals(absolute.Scheme, Uri.UriSchemeHttps, StringComparison.Ordinal)
            || !string.Equals(absolute.Host, "chummer.run", StringComparison.OrdinalIgnoreCase)
            || !string.IsNullOrEmpty(absolute.Query)
            || !string.IsNullOrEmpty(absolute.Fragment))
        {
            return false;
        }

        string incomingPath = $"/downloads/files/{payloadFileName}";
        return (allowMutableIncomingUrl
               && string.Equals(absolute.AbsolutePath, incomingPath, StringComparison.Ordinal))
               || (string.Equals(absolute.AbsolutePath, expectedManifestUrl, StringComparison.Ordinal)
                   && IsImmutablePayloadRoute(absolute.AbsolutePath, payloadFileName));
    }

    private static bool IsImmutablePayloadRoute(string value, string payloadFileName)
    {
        string path = value;
        if (Uri.TryCreate(value, UriKind.Absolute, out Uri? absolute))
        {
            path = absolute.AbsolutePath;
        }

        string[] parts = path.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 5
            || parts[0] != "downloads"
            || parts[1] != "g"
            || !IsPortableRouteSegment(parts[2]))
        {
            return false;
        }

        if (parts.Length == 5
            && parts[3] == "files"
            && string.Equals(parts[4], payloadFileName, StringComparison.Ordinal))
        {
            return true;
        }

        return parts.Length == 6
               && parts[3] == "install"
               && IsPortableRouteSegment(parts[4])
               && parts[5] == "payload";
    }

    private static bool IsPortableRouteSegment(string value)
        => value.Length is > 0 and <= 255
           && value is not "." and not ".."
           && value.All(static character =>
               character is >= 'A' and <= 'Z'
                   or >= 'a' and <= 'z'
                   or >= '0' and <= '9'
                   or '-' or '_' or '.');

    private static bool TryString(JsonElement root, string property, out string? value)
    {
        value = null;
        if (!root.TryGetProperty(property, out JsonElement child)
            || child.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        value = child.GetString()?.Trim();
        return value is not null;
    }

    private static bool Fail(string message, out string? failure)
    {
        failure = message;
        return false;
    }
}
