using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Projects the exact Registry authority envelope that was copied into, and sealed by,
/// one immutable Hub release-shelf generation. Any partial or contradictory envelope is
/// rejected rather than being interpreted as legacy release truth.
/// </summary>
internal static class PublicReleaseAuthorityEnvelopeProjection
{
    internal const string CurrentInventoryPath = "release-evidence/CURRENT.json";
    internal const string SnapshotInventoryPath = "release-evidence/SNAPSHOT.json";
    internal const string AuthorityContract = "chummer.release-authority-snapshot/v2";
    internal const string RegistryRepository = "ArchonMegalon/chummer6-hub-registry";
    internal const string ManifestPath = "RELEASE_CHANNEL.json";
    internal const string ReleaseDecisionPath = "RELEASE_DECISION.json";

    private const int MaximumCurrentBytes = 64 * 1024;
    private const int MaximumSnapshotBytes = 4 * 1024 * 1024;
    private const int MaximumDecisionBytes = 4 * 1024 * 1024;
    private const int MaximumTokenLength = 128;
    private const int MaximumSupportOwnerLength = 256;
    private const int MaximumActionLength = 512;
    private const int MaximumActionCount = 32;
    private const int MaximumPlatformCount = 16;
    private const int MaximumArtifactCount = 256;
    private const int MaximumKnownIssueSummaryLength = 512;
    private const int MaximumUrlLength = 2048;

    private static readonly HashSet<string> AllowedDecisionStatuses =
        ["review_required", "preview_ready", "stable_ready"];
    private static readonly HashSet<string> AllowedAccessClasses =
        ["open_public", "account_recommended", "account_required"];
    private static readonly HashSet<string> SentinelTokens =
        [PublicReleaseTruthProjectionDto.Unknown, PublicReleaseTruthProjectionDto.Missing, PublicReleaseTruthProjectionDto.Invalid];
    private static readonly HashSet<string> CurrentFields =
        ["releaseVersion", "snapshotSha256", "decisionSha256", "status"];
    private static readonly HashSet<string> SnapshotFields =
    [
        "authorityContract", "releaseVersion", "channel", "status", "rolloutState",
        "supportabilityState", "availablePlatforms", "primaryHeadByPlatform",
        "artifactCount", "downloadAccessPosture", "knownIssueSummary", "manifestSha256",
        "registryRepository", "registryCommit", "releaseDecisionStatus", "releaseDecisionSha256", "supportOwner",
        "nextActions", "artifacts", "manifestPath", "releaseDecisionPath"
    ];
    private static readonly HashSet<string> ArtifactFields =
    [
        "artifactId", "head", "platform", "rid", "arch", "kind", "downloadUrl", "sha256",
        "sizeBytes", "compatibilityState", "promotionState", "publicationScope", "revokeState",
        "publicInstallRoute", "installAccessClass"
    ];
    private static readonly JsonDocumentOptions JsonOptions = new()
    {
        AllowTrailingCommas = false,
        CommentHandling = JsonCommentHandling.Disallow,
        MaxDepth = 32
    };

    internal static PublicReleaseTruthProjectionDto? TryProject(
        ReleaseShelfSnapshot shelf,
        PublicReleaseManifestDto manifest,
        string? immutableManifestSha256,
        ReadOnlyMemory<byte>? immutableManifestBytes,
        out string? authoritySnapshotSha256)
    {
        authoritySnapshotSha256 = null;
        ArgumentNullException.ThrowIfNull(shelf);
        ArgumentNullException.ThrowIfNull(manifest);
        if (shelf.IsLegacy)
        {
            return null;
        }

        bool hasCurrent = HasExactInventoryPath(shelf, CurrentInventoryPath);
        bool hasSnapshot = HasExactInventoryPath(shelf, SnapshotInventoryPath);
        RejectNoncanonicalInventoryPath(shelf, CurrentInventoryPath, hasCurrent);
        RejectNoncanonicalInventoryPath(shelf, SnapshotInventoryPath, hasSnapshot);
        if (!hasCurrent && !hasSnapshot)
        {
            return null;
        }

        if (!hasCurrent || !hasSnapshot)
        {
            throw Invalid("Registry authority evidence is incomplete in the release-shelf inventory.");
        }

        byte[] currentBytes = shelf.ReadVerifiedFileBytes(CurrentInventoryPath, MaximumCurrentBytes)
            ?? throw Invalid("Registry CURRENT.json no longer matches its release-shelf inventory binding.");
        byte[] snapshotBytes = shelf.ReadVerifiedFileBytes(SnapshotInventoryPath, MaximumSnapshotBytes)
            ?? throw Invalid("Registry SNAPSHOT.json no longer matches its release-shelf inventory binding.");
        string decisionInventoryPath = ResolveSiblingInventoryPath(
            SnapshotInventoryPath,
            ReadReleaseDecisionPath(snapshotBytes));
        bool hasDecision = HasExactInventoryPath(shelf, decisionInventoryPath);
        RejectNoncanonicalInventoryPath(shelf, decisionInventoryPath, hasDecision);
        if (!hasDecision)
        {
            throw Invalid("Registry authority evidence omits the decision sibling declared by SNAPSHOT.json.");
        }

        byte[] decisionBytes = shelf.ReadVerifiedFileBytes(decisionInventoryPath, MaximumDecisionBytes)
            ?? throw Invalid("Registry RELEASE_DECISION.json no longer matches its release-shelf inventory binding.");
        PublicReleaseTruthProjectionDto projection = Project(
            currentBytes,
            snapshotBytes,
            decisionBytes,
            manifest,
            immutableManifestSha256,
            immutableManifestBytes);
        authoritySnapshotSha256 = Convert.ToHexStringLower(SHA256.HashData(snapshotBytes));
        return projection;
    }

    internal static PublicReleaseTruthProjectionDto Project(
        ReadOnlyMemory<byte> currentBytes,
        ReadOnlyMemory<byte> snapshotBytes,
        ReadOnlyMemory<byte> decisionBytes,
        PublicReleaseManifestDto manifest,
        string? immutableManifestSha256,
        ReadOnlyMemory<byte>? immutableManifestBytes)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        if (currentBytes.IsEmpty || currentBytes.Length > MaximumCurrentBytes)
        {
            throw Invalid("Registry CURRENT.json has an invalid byte length.");
        }

        if (snapshotBytes.IsEmpty || snapshotBytes.Length > MaximumSnapshotBytes)
        {
            throw Invalid("Registry SNAPSHOT.json has an invalid byte length.");
        }

        if (decisionBytes.IsEmpty || decisionBytes.Length > MaximumDecisionBytes)
        {
            throw Invalid("Registry RELEASE_DECISION.json has an invalid byte length.");
        }

        using JsonDocument currentDocument = ParseStrict(currentBytes, "Registry CURRENT.json");
        using JsonDocument snapshotDocument = ParseStrict(snapshotBytes, "Registry SNAPSHOT.json");
        JsonElement current = currentDocument.RootElement;
        JsonElement snapshot = snapshotDocument.RootElement;
        RequireExactObject(current, CurrentFields, "Registry CURRENT.json");
        RequireExactObject(snapshot, SnapshotFields, "Registry SNAPSHOT.json");

        string currentReleaseVersion = RequirePortableIdentifier(
            current,
            "releaseVersion",
            "Registry CURRENT.json");
        string currentSnapshotSha256 = RequireSha256(
            current,
            "snapshotSha256",
            "Registry CURRENT.json");
        string currentDecisionSha256 = RequireSha256(
            current,
            "decisionSha256",
            "Registry CURRENT.json");
        string currentStatus = RequireDecisionStatus(current, "status", "Registry CURRENT.json");
        RequireDigestMatchesBytes(
            currentSnapshotSha256,
            snapshotBytes.Span,
            "Registry CURRENT.json snapshotSha256");

        string authorityContract = RequireString(snapshot, "authorityContract", MaximumTokenLength, "Registry SNAPSHOT.json");
        if (!string.Equals(authorityContract, AuthorityContract, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json authorityContract must be {AuthorityContract}.");
        }

        string releaseVersion = RequirePortableIdentifier(snapshot, "releaseVersion", "Registry SNAPSHOT.json");
        string channel = RequireCanonicalToken(snapshot, "channel", "Registry SNAPSHOT.json");
        string releaseStatus = RequireCanonicalToken(snapshot, "status", "Registry SNAPSHOT.json");
        string rolloutState = RequireCanonicalToken(snapshot, "rolloutState", "Registry SNAPSHOT.json");
        string supportabilityState = RequireCanonicalToken(snapshot, "supportabilityState", "Registry SNAPSHOT.json");
        string knownIssueSummary = RequireString(
            snapshot,
            "knownIssueSummary",
            MaximumKnownIssueSummaryLength,
            "Registry SNAPSHOT.json");
        string manifestSha256 = RequireSha256(snapshot, "manifestSha256", "Registry SNAPSHOT.json");
        string registryRepository = RequireString(
            snapshot,
            "registryRepository",
            MaximumSupportOwnerLength,
            "Registry SNAPSHOT.json");
        if (!string.Equals(registryRepository, RegistryRepository, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json registryRepository must be {RegistryRepository}.");
        }
        string registryCommit = RequireLowerHex(snapshot, "registryCommit", 40, "Registry SNAPSHOT.json");
        string releaseDecisionStatus = RequireDecisionStatus(
            snapshot,
            "releaseDecisionStatus",
            "Registry SNAPSHOT.json");
        string releaseDecisionSha256 = RequireSha256(
            snapshot,
            "releaseDecisionSha256",
            "Registry SNAPSHOT.json");
        RequireDigestMatchesBytes(
            releaseDecisionSha256,
            decisionBytes.Span,
            "Registry SNAPSHOT.json releaseDecisionSha256");
        _ = RequireString(snapshot, "supportOwner", MaximumSupportOwnerLength, "Registry SNAPSHOT.json");
        int nextActionCount = RequireNextActions(snapshot.GetProperty("nextActions"));
        if (releaseDecisionStatus == "review_required" && nextActionCount == 0)
        {
            throw Invalid("Registry SNAPSHOT.json review_required decisions must publish at least one next action.");
        }
        RequireFixedPath(snapshot, "manifestPath", ManifestPath);
        RequireFixedPath(snapshot, "releaseDecisionPath", ReleaseDecisionPath);

        if (!string.Equals(currentReleaseVersion, releaseVersion, StringComparison.Ordinal)
            || !string.Equals(currentStatus, releaseDecisionStatus, StringComparison.Ordinal)
            || !FixedTimeDigestEquals(currentDecisionSha256, releaseDecisionSha256))
        {
            throw Invalid("Registry CURRENT.json does not bind the same release decision as SNAPSHOT.json.");
        }

        string normalizedManifestDigest = PublicReleaseTruthProjectionService.NormalizeSha256(
            immutableManifestSha256);
        string verifiedManifestDigest = PublicReleaseTruthProjectionService.VerifyAuthorityManifestDigest(
            normalizedManifestDigest,
            immutableManifestBytes);
        if (!FixedTimeDigestEquals(manifestSha256, verifiedManifestDigest))
        {
            throw Invalid("Registry SNAPSHOT.json manifestSha256 does not bind the immutable Hub authority manifest bytes.");
        }

        if (!string.Equals(
                releaseVersion,
                PublicReleaseTruthProjectionService.NormalizeIdentifier(manifest.Version),
                StringComparison.Ordinal)
            || !string.Equals(channel, NormalizeExactToken(manifest.Channel), StringComparison.Ordinal)
            || !string.Equals(releaseStatus, NormalizeExactToken(manifest.Status), StringComparison.Ordinal)
            || !string.Equals(rolloutState, NormalizeExactToken(manifest.RolloutState), StringComparison.Ordinal)
            || !string.Equals(supportabilityState, NormalizeExactToken(manifest.SupportabilityState), StringComparison.Ordinal)
            || !string.Equals(knownIssueSummary, PublicReleaseTruthProjectionService.NormalizeSummary(manifest.KnownIssueSummary), StringComparison.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json release fields contradict the final Hub release manifest projection.");
        }

        AuthorityArtifact[] authorityArtifacts = RequireAuthorityArtifacts(snapshot.GetProperty("artifacts"));
        int artifactCount = RequireNonnegativeInt(snapshot, "artifactCount", "Registry SNAPSHOT.json");
        if (artifactCount != authorityArtifacts.Length || artifactCount != manifest.Downloads.Count)
        {
            throw Invalid("Registry SNAPSHOT.json artifactCount contradicts its artifacts or the final Hub public shelf.");
        }

        CompareArtifactBindings(authorityArtifacts, manifest.Downloads);
        string[] availablePlatforms = RequireAvailablePlatforms(snapshot.GetProperty("availablePlatforms"));
        string[] derivedPlatforms = authorityArtifacts
            .Select(static artifact => artifact.Platform)
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static platform => platform, StringComparer.Ordinal)
            .ToArray();
        if (!availablePlatforms.SequenceEqual(derivedPlatforms, StringComparer.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json availablePlatforms does not equal the promoted artifact platform set.");
        }

        SortedDictionary<string, string> primaryHeads = RequirePrimaryHeads(
            snapshot.GetProperty("primaryHeadByPlatform"),
            availablePlatforms,
            authorityArtifacts);
        string downloadAccessPosture = RequireString(
            snapshot,
            "downloadAccessPosture",
            MaximumTokenLength,
            "Registry SNAPSHOT.json");
        string derivedPosture = DeriveAccessPosture(authorityArtifacts);
        if (!string.Equals(downloadAccessPosture, derivedPosture, StringComparison.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json downloadAccessPosture contradicts the promoted artifacts.");
        }

        if (artifactCount == 0)
        {
            if (releaseDecisionStatus != "review_required"
                || downloadAccessPosture != "unavailable"
                || availablePlatforms.Length != 0
                || primaryHeads.Count != 0)
            {
                throw Invalid("An empty public shelf is valid only as review_required with unavailable access.");
            }
        }
        else if (releaseDecisionStatus is "preview_ready" or "stable_ready"
                 && downloadAccessPosture == "unavailable")
        {
            throw Invalid("A ready release decision cannot publish an unavailable non-empty shelf.");
        }

        return new PublicReleaseTruthProjectionDto(
            ContractName: PublicReleaseTruthProjectionDto.Schema,
            ReleaseVersion: releaseVersion,
            Channel: channel,
            ReleaseStatus: releaseStatus,
            RolloutState: rolloutState,
            SupportabilityState: supportabilityState,
            AvailablePlatforms: availablePlatforms,
            PrimaryHeadByPlatform: primaryHeads,
            ArtifactCount: artifactCount,
            DownloadAccessPosture: downloadAccessPosture,
            KnownIssueSummary: knownIssueSummary,
            ManifestSha256: manifestSha256,
            RegistryCommit: registryCommit,
            ReleaseDecisionStatus: releaseDecisionStatus,
            ReleaseDecisionSha256: releaseDecisionSha256);
    }

    private static JsonDocument ParseStrict(ReadOnlyMemory<byte> bytes, string label)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(bytes, JsonOptions);
        }
        catch (JsonException error)
        {
            throw Invalid($"{label} is not strict JSON.", error);
        }

        try
        {
            RejectDuplicatePropertyNames(document.RootElement, label, 0);
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    private static string ReadReleaseDecisionPath(ReadOnlyMemory<byte> snapshotBytes)
    {
        using JsonDocument document = ParseStrict(snapshotBytes, "Registry SNAPSHOT.json");
        JsonElement snapshot = document.RootElement;
        RequireExactObject(snapshot, SnapshotFields, "Registry SNAPSHOT.json");
        string decisionPath = RequireString(
            snapshot,
            "releaseDecisionPath",
            MaximumTokenLength,
            "Registry SNAPSHOT.json");
        if (!string.Equals(decisionPath, ReleaseDecisionPath, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json releaseDecisionPath must be {ReleaseDecisionPath}.");
        }

        return decisionPath;
    }

    private static string ResolveSiblingInventoryPath(string snapshotInventoryPath, string siblingName)
    {
        if (Path.GetFileName(siblingName) != siblingName
            || siblingName.Contains('/')
            || siblingName.Contains('\\'))
        {
            throw Invalid("Registry SNAPSHOT.json releaseDecisionPath must name one sibling file.");
        }

        string? directory = Path.GetDirectoryName(snapshotInventoryPath)?.Replace('\\', '/');
        return string.IsNullOrEmpty(directory)
            ? siblingName
            : directory + "/" + siblingName;
    }

    private static void RejectDuplicatePropertyNames(JsonElement value, string label, int depth)
    {
        if (depth > JsonOptions.MaxDepth)
        {
            throw Invalid($"{label} exceeds the permitted JSON nesting depth.");
        }

        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in value.EnumerateObject())
            {
                if (!names.Add(property.Name))
                {
                    throw Invalid($"{label} contains duplicate property '{property.Name}'.");
                }

                RejectDuplicatePropertyNames(property.Value, label, depth + 1);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in value.EnumerateArray())
            {
                RejectDuplicatePropertyNames(item, label, depth + 1);
            }
        }
    }

    private static void RequireExactObject(JsonElement value, HashSet<string> expected, string label)
    {
        if (value.ValueKind != JsonValueKind.Object)
        {
            throw Invalid($"{label} must be a JSON object.");
        }

        string[] observed = value.EnumerateObject().Select(static property => property.Name).ToArray();
        string[] missing = expected.Except(observed, StringComparer.Ordinal).OrderBy(static name => name, StringComparer.Ordinal).ToArray();
        string[] unknown = observed.Except(expected, StringComparer.Ordinal).OrderBy(static name => name, StringComparer.Ordinal).ToArray();
        if (missing.Length > 0 || unknown.Length > 0)
        {
            throw Invalid($"{label} has missing [{string.Join(", ", missing)}] or unknown [{string.Join(", ", unknown)}] fields.");
        }
    }

    private static string RequireString(JsonElement source, string propertyName, int maximumLength, string label)
    {
        JsonElement property = source.GetProperty(propertyName);
        if (property.ValueKind != JsonValueKind.String)
        {
            throw Invalid($"{label} {propertyName} must be a string.");
        }

        string? value = property.GetString();
        if (string.IsNullOrWhiteSpace(value)
            || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
            || value.Length > maximumLength)
        {
            throw Invalid($"{label} {propertyName} is empty, noncanonical, or oversized.");
        }

        return value;
    }

    private static string RequirePortableIdentifier(JsonElement source, string propertyName, string label)
    {
        string value = RequireString(source, propertyName, MaximumTokenLength, label);
        if (!char.IsAsciiLetterOrDigit(value[0])
            || value.Any(static character => !char.IsAsciiLetterOrDigit(character)
                && character is not '.' and not '_' and not '-' and not '+'))
        {
            throw Invalid($"{label} {propertyName} is not a portable identifier.");
        }

        return value;
    }

    private static string RequireCanonicalToken(JsonElement source, string propertyName, string label)
    {
        string value = RequireString(source, propertyName, MaximumTokenLength, label);
        if (!char.IsAsciiLetterOrDigit(value[0])
            || value.Any(static character => !char.IsAsciiLetterOrDigit(character)
                && character is not '.' and not '_' and not '-'))
        {
            throw Invalid($"{label} {propertyName} is not a canonical token.");
        }

        if (!string.Equals(value, value.ToLowerInvariant(), StringComparison.Ordinal))
        {
            throw Invalid($"{label} {propertyName} must be lower-case.");
        }

        return value;
    }

    private static string RequireDecisionStatus(JsonElement source, string propertyName, string label)
    {
        string value = RequireCanonicalToken(source, propertyName, label);
        if (!AllowedDecisionStatuses.Contains(value))
        {
            throw Invalid($"{label} {propertyName} is not an allowed release decision status.");
        }

        return value;
    }

    private static string RequireAuthorityToken(JsonElement source, string propertyName, string label)
    {
        string value = RequireCanonicalToken(source, propertyName, label);
        if (SentinelTokens.Contains(value))
        {
            throw Invalid($"{label} {propertyName} cannot use a release-truth sentinel.");
        }

        return value;
    }

    private static string RequireSha256(JsonElement source, string propertyName, string label)
        => RequireLowerHex(source, propertyName, 64, label);

    private static string RequireLowerHex(JsonElement source, string propertyName, int length, string label)
    {
        string value = RequireString(source, propertyName, length, label);
        if (value.Length != length || value.Any(static character =>
                character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
        {
            throw Invalid($"{label} {propertyName} is not a canonical lower-case hexadecimal value.");
        }

        return value;
    }

    private static int RequireNonnegativeInt(JsonElement source, string propertyName, string label)
    {
        JsonElement property = source.GetProperty(propertyName);
        if (property.ValueKind != JsonValueKind.Number
            || !property.TryGetInt32(out int value)
            || value < 0
            || value > MaximumArtifactCount)
        {
            throw Invalid($"{label} {propertyName} must be a bounded non-negative integer.");
        }

        return value;
    }

    private static int RequireNextActions(JsonElement actions)
    {
        if (actions.ValueKind != JsonValueKind.Array
            || actions.GetArrayLength() > MaximumActionCount)
        {
            throw Invalid("Registry SNAPSHOT.json nextActions must be a bounded array.");
        }

        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement action in actions.EnumerateArray())
        {
            if (action.ValueKind != JsonValueKind.String)
            {
                throw Invalid("Registry SNAPSHOT.json nextActions entries must be strings.");
            }

            string? value = action.GetString();
            if (string.IsNullOrWhiteSpace(value)
                || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
                || value.Length > MaximumActionLength
                || !observed.Add(value))
            {
                throw Invalid("Registry SNAPSHOT.json nextActions entries must be unique, canonical, and bounded.");
            }
        }

        return actions.GetArrayLength();
    }

    private static void RequireFixedPath(JsonElement source, string propertyName, string expected)
    {
        string value = RequireString(source, propertyName, MaximumTokenLength, "Registry SNAPSHOT.json");
        if (!string.Equals(value, expected, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json {propertyName} must be {expected}.");
        }
    }

    private static AuthorityArtifact[] RequireAuthorityArtifacts(JsonElement artifacts)
    {
        if (artifacts.ValueKind != JsonValueKind.Array
            || artifacts.GetArrayLength() > MaximumArtifactCount)
        {
            throw Invalid("Registry SNAPSHOT.json artifacts must be a bounded array.");
        }

        var result = new List<AuthorityArtifact>(artifacts.GetArrayLength());
        string? priorId = null;
        foreach (JsonElement artifact in artifacts.EnumerateArray())
        {
            RequireExactObject(artifact, ArtifactFields, "Registry SNAPSHOT.json artifact");
            string artifactId = RequireAuthorityToken(artifact, "artifactId", "Registry SNAPSHOT.json artifact");
            if (priorId is not null && string.CompareOrdinal(priorId, artifactId) >= 0)
            {
                throw Invalid("Registry SNAPSHOT.json artifact IDs must be unique and in ordinal order.");
            }

            priorId = artifactId;
            string head = RequireAuthorityToken(artifact, "head", "Registry SNAPSHOT.json artifact");
            string platform = RequireAuthorityToken(artifact, "platform", "Registry SNAPSHOT.json artifact");
            string rid = RequireAuthorityToken(artifact, "rid", "Registry SNAPSHOT.json artifact");
            string arch = RequireAuthorityToken(artifact, "arch", "Registry SNAPSHOT.json artifact");
            string kind = RequireCanonicalToken(artifact, "kind", "Registry SNAPSHOT.json artifact");
            if (kind != "installer")
            {
                throw Invalid("Registry SNAPSHOT.json eligible artifact kind must be installer.");
            }
            string downloadUrl = RequireString(
                artifact,
                "downloadUrl",
                MaximumUrlLength,
                "Registry SNAPSHOT.json artifact");
            string sha256 = RequireSha256(artifact, "sha256", "Registry SNAPSHOT.json artifact");
            long sizeBytes = RequirePositiveLong(artifact, "sizeBytes", "Registry SNAPSHOT.json artifact");
            RequireExactArtifactState(artifact, "compatibilityState", "compatible");
            RequireExactArtifactState(artifact, "promotionState", "promoted");
            RequireExactArtifactState(artifact, "publicationScope", "signed-in-and-public");
            RequireExactArtifactState(artifact, "revokeState", "not_revoked");
            string publicInstallRoute = RequirePublicInstallRoute(artifact);
            if (string.Equals(publicInstallRoute, downloadUrl, StringComparison.Ordinal))
            {
                throw Invalid("Registry SNAPSHOT.json publicInstallRoute must be distinct from downloadUrl.");
            }
            string accessClass = RequireCanonicalToken(
                artifact,
                "installAccessClass",
                "Registry SNAPSHOT.json artifact");
            if (!AllowedAccessClasses.Contains(accessClass))
            {
                throw Invalid("Registry SNAPSHOT.json artifact installAccessClass is not supported.");
            }

            result.Add(new(
                artifactId,
                head,
                platform,
                rid,
                arch,
                kind,
                downloadUrl,
                sha256,
                sizeBytes,
                publicInstallRoute,
                accessClass));
        }

        return result.ToArray();
    }

    private static string[] RequireAvailablePlatforms(JsonElement platforms)
    {
        if (platforms.ValueKind != JsonValueKind.Array
            || platforms.GetArrayLength() > MaximumPlatformCount)
        {
            throw Invalid("Registry SNAPSHOT.json availablePlatforms must be a bounded array.");
        }

        var result = new List<string>(platforms.GetArrayLength());
        string? prior = null;
        foreach (JsonElement platform in platforms.EnumerateArray())
        {
            if (platform.ValueKind != JsonValueKind.String)
            {
                throw Invalid("Registry SNAPSHOT.json availablePlatforms entries must be strings.");
            }

            string? value = platform.GetString();
            if (string.IsNullOrWhiteSpace(value)
                || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
                || !string.Equals(value, value.ToLowerInvariant(), StringComparison.Ordinal)
                || value.Length > MaximumTokenLength
                || !char.IsAsciiLetterOrDigit(value[0])
                || value.Any(static character => !char.IsAsciiLetterOrDigit(character)
                    && character is not '.' and not '_' and not '-')
                || SentinelTokens.Contains(value)
                || (prior is not null && string.CompareOrdinal(prior, value) >= 0))
            {
                throw Invalid("Registry SNAPSHOT.json availablePlatforms must be unique lower-case IDs in ordinal order.");
            }

            result.Add(value);
            prior = value;
        }

        return result.ToArray();
    }

    private static long RequirePositiveLong(JsonElement source, string propertyName, string label)
    {
        JsonElement property = source.GetProperty(propertyName);
        if (property.ValueKind != JsonValueKind.Number
            || !property.TryGetInt64(out long value)
            || value <= 0)
        {
            throw Invalid($"{label} {propertyName} must be a positive integer.");
        }

        return value;
    }

    private static void RequireExactArtifactState(
        JsonElement artifact,
        string propertyName,
        string expected)
    {
        string value = RequireCanonicalToken(
            artifact,
            propertyName,
            "Registry SNAPSHOT.json artifact");
        if (!string.Equals(value, expected, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json artifact {propertyName} must be {expected}.");
        }
    }

    private static string RequirePublicInstallRoute(JsonElement artifact)
    {
        string route = RequireString(
            artifact,
            "publicInstallRoute",
            MaximumUrlLength,
            "Registry SNAPSHOT.json artifact");
        string[] segments = route.Split('/', StringSplitOptions.RemoveEmptyEntries);
        bool hasUnsafeDecodedSegment;
        try
        {
            hasUnsafeDecodedSegment = segments.Any(static segment =>
            {
                string decoded = Uri.UnescapeDataString(segment);
                return decoded is "." or ".."
                       || decoded.Contains('/')
                       || decoded.Contains('\\')
                       || decoded.Any(char.IsControl)
                       || decoded.Any(char.IsWhiteSpace);
            });
        }
        catch (UriFormatException)
        {
            hasUnsafeDecodedSegment = true;
        }

        if (!route.StartsWith("/", StringComparison.Ordinal)
            || route.StartsWith("//", StringComparison.Ordinal)
            || route.Contains("//", StringComparison.Ordinal)
            || segments.Length == 0
            || route.Contains('?')
            || route.Contains('#')
            || route.Contains('\\')
            || route.Any(char.IsWhiteSpace)
            || hasUnsafeDecodedSegment)
        {
            throw Invalid("Registry SNAPSHOT.json artifact publicInstallRoute must be a query-free, fragment-free root-relative public path.");
        }

        return route;
    }

    private static SortedDictionary<string, string> RequirePrimaryHeads(
        JsonElement primaryHeads,
        IReadOnlyList<string> availablePlatforms,
        IReadOnlyList<AuthorityArtifact> artifacts)
    {
        if (primaryHeads.ValueKind != JsonValueKind.Object)
        {
            throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform must be an object.");
        }

        var result = new SortedDictionary<string, string>(StringComparer.Ordinal);
        string? prior = null;
        foreach (JsonProperty property in primaryHeads.EnumerateObject())
        {
            if (prior is not null && string.CompareOrdinal(prior, property.Name) >= 0)
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform keys must be in ordinal order.");
            }

            if (property.Value.ValueKind != JsonValueKind.String)
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform values must be strings.");
            }

            string? head = property.Value.GetString();
            if (string.IsNullOrWhiteSpace(head)
                || !string.Equals(head, head.Trim(), StringComparison.Ordinal)
                || !string.Equals(head, head.ToLowerInvariant(), StringComparison.Ordinal)
                || head.Length > MaximumTokenLength
                || !char.IsAsciiLetterOrDigit(head[0])
                || head.Any(static character => !char.IsAsciiLetterOrDigit(character)
                    && character is not '.' and not '_' and not '-')
                || SentinelTokens.Contains(head))
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform values must be canonical lower-case heads.");
            }

            if (!artifacts.Any(artifact =>
                    string.Equals(artifact.Platform, property.Name, StringComparison.Ordinal)
                    && string.Equals(artifact.Head, head, StringComparison.Ordinal)))
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform does not resolve to a promoted artifact.");
            }

            result.Add(property.Name, head);
            prior = property.Name;
        }

        if (!result.Keys.SequenceEqual(availablePlatforms, StringComparer.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform keys must exactly equal availablePlatforms.");
        }

        return result;
    }

    private static void CompareArtifactBindings(
        IReadOnlyList<AuthorityArtifact> authorityArtifacts,
        IReadOnlyList<PublicReleaseArtifactDto> publicArtifacts)
    {
        var hubById = new Dictionary<string, PublicReleaseArtifactDto>(StringComparer.Ordinal);
        foreach (PublicReleaseArtifactDto artifact in publicArtifacts)
        {
            string id = (artifact.Id ?? string.Empty).Trim();
            if (id.Length == 0 || !hubById.TryAdd(id, artifact))
            {
                throw Invalid("The final Hub public shelf contains empty or duplicate artifact IDs.");
            }
        }

        if (!authorityArtifacts.Select(static artifact => artifact.ArtifactId)
                .SequenceEqual(hubById.Keys.OrderBy(static id => id, StringComparer.Ordinal), StringComparer.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json artifacts do not exactly equal the final Hub public artifact shelf.");
        }

        foreach (AuthorityArtifact authority in authorityArtifacts)
        {
            PublicReleaseArtifactDto hub = hubById[authority.ArtifactId];
            string hubSha256 = (hub.Sha256 ?? string.Empty).Trim().ToLowerInvariant();
            if (!string.Equals(authority.Head, NormalizeExactToken(hub.Head), StringComparison.Ordinal)
                || !string.Equals(authority.Platform, PublicReleaseTruthProjectionService.ResolvePlatformId(hub), StringComparison.Ordinal)
                || !string.Equals(authority.Rid, NormalizeExactToken(hub.Rid), StringComparison.Ordinal)
                || !string.Equals(authority.Arch, NormalizeExactToken(hub.Arch), StringComparison.Ordinal)
                || !string.Equals(authority.Kind, "installer", StringComparison.Ordinal)
                || !string.Equals(NormalizeExactToken(hub.Kind), "installer", StringComparison.Ordinal)
                || !string.Equals(authority.DownloadUrl, (hub.Url ?? string.Empty).Trim(), StringComparison.Ordinal)
                || !string.Equals(authority.Sha256, hubSha256, StringComparison.Ordinal)
                || hub.SizeBytes != authority.SizeBytes
                || !string.Equals(
                    "compatible",
                    NormalizeExactToken(hub.CompatibilityState),
                    StringComparison.Ordinal)
                || !string.Equals(authority.InstallAccessClass, NormalizeExactToken(hub.InstallAccessClass), StringComparison.Ordinal))
            {
                throw Invalid($"Registry SNAPSHOT.json artifact '{authority.ArtifactId}' contradicts the final Hub public binding.");
            }
        }
    }

    private static string NormalizeExactToken(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? PublicReleaseTruthProjectionDto.Unknown
            : value.Trim().ToLowerInvariant();

    private static string DeriveAccessPosture(IReadOnlyList<AuthorityArtifact> artifacts)
    {
        if (artifacts.Count == 0)
        {
            return "unavailable";
        }

        string[] classes = artifacts
            .Select(static artifact => artifact.InstallAccessClass)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        return classes.Length == 1 ? classes[0] : "mixed";
    }

    private static void RequireDigestMatchesBytes(string expected, ReadOnlySpan<byte> bytes, string label)
    {
        Span<byte> actual = stackalloc byte[32];
        SHA256.HashData(bytes, actual);
        byte[] expectedBytes = Convert.FromHexString(expected);
        if (!CryptographicOperations.FixedTimeEquals(expectedBytes, actual))
        {
            throw Invalid($"{label} does not match the exact authority bytes.");
        }
    }

    private static bool FixedTimeDigestEquals(string expected, string actual)
    {
        try
        {
            byte[] expectedBytes = Convert.FromHexString(expected);
            byte[] actualBytes = Convert.FromHexString(actual);
            return expectedBytes.Length == 32
                   && actualBytes.Length == 32
                   && CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static bool HasExactInventoryPath(ReleaseShelfSnapshot shelf, string expected)
        => shelf.Inventory.ContainsKey(expected);

    private static void RejectNoncanonicalInventoryPath(
        ReleaseShelfSnapshot shelf,
        string expected,
        bool hasExact)
    {
        if (hasExact)
        {
            return;
        }

        if (shelf.Inventory.Keys.Any(path => string.Equals(path, expected, StringComparison.OrdinalIgnoreCase)))
        {
            throw Invalid($"Release-shelf authority evidence path must use exact casing: {expected}.");
        }
    }

    private static InvalidDataException Invalid(string message, Exception? inner = null)
        => inner is null ? new InvalidDataException(message) : new InvalidDataException(message, inner);

    private sealed record AuthorityArtifact(
        string ArtifactId,
        string Head,
        string Platform,
        string Rid,
        string Arch,
        string Kind,
        string DownloadUrl,
        string Sha256,
        long SizeBytes,
        string PublicInstallRoute,
        string InstallAccessClass);
}
