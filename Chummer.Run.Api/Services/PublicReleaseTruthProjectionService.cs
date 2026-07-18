using System.Security.Cryptography;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public interface IReleaseTruthProjection
{
    PublicReleaseTruthCapture CaptureWithAuthority();

    PublicReleaseTruthCapture CaptureGenerationWithAuthority(string generationId);

    PublicReleaseTruthProjectionDto Capture();

    PublicReleaseTruthProjectionDto CaptureGeneration(string generationId);

    PublicReleaseTruthProjectionDto Project(
        PublicReleaseManifestDto manifest,
        string? immutableManifestSha256,
        ReadOnlyMemory<byte>? immutableAuthorityManifestBytes);
}

public sealed record PublicReleaseTruthCapture(
    PublicReleaseTruthProjectionDto Projection,
    string AuthoritySnapshotSha256);

public sealed class PublicReleaseTruthProjectionService : IReleaseTruthProjection
{
    private const int MaximumTokenLength = 128;
    private const int MaximumPlatformCount = 16;
    private const int MaximumKnownIssueSummaryLength = 512;
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly ArtifactDeliveryPolicy _artifactDelivery;

    public PublicReleaseTruthProjectionService(
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        ArtifactDeliveryPolicy artifactDelivery)
    {
        _releases = releases;
        _releaseSelection = releaseSelection;
        _artifactDelivery = artifactDelivery;
    }

    public PublicReleaseTruthProjectionDto Capture()
        => CaptureWithAuthority().Projection;

    public PublicReleaseTruthProjectionDto CaptureGeneration(string generationId)
        => CaptureGenerationWithAuthority(generationId).Projection;

    public PublicReleaseTruthCapture CaptureWithAuthority()
        => CaptureSnapshot(_releases.CaptureShelfSnapshot());

    public PublicReleaseTruthCapture CaptureGenerationWithAuthority(string generationId)
        => CaptureSnapshot(_releases.CaptureShelfGeneration(generationId));

    private PublicReleaseTruthCapture CaptureSnapshot(ReleaseShelfSnapshot snapshot)
    {
        PublicReleaseManifestDto manifest = _artifactDelivery.FilterRevokedArtifacts(
            snapshot,
            _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest(snapshot)));
        ReadOnlyMemory<byte>? authorityBytes = snapshot.IsLegacy
            ? null
            : _releases.LoadGenerationCanonicalManifestBytes(snapshot);
        string? authorityDigest = snapshot.IsLegacy
            ? null
            : snapshot.CanonicalManifestSha256;
        PublicReleaseTruthProjectionDto? authorityProjection =
            PublicReleaseAuthorityEnvelopeProjection.TryProject(
                snapshot,
                manifest,
                authorityDigest,
                authorityBytes,
                out string? authoritySnapshotSha256);
        if (authorityProjection is not null)
        {
            return new(authorityProjection, authoritySnapshotSha256!);
        }

        return new(
            Project(manifest, authorityDigest, authorityBytes),
            PublicReleaseTruthProjectionDto.Missing);
    }

    public PublicReleaseTruthProjectionDto Project(
        PublicReleaseManifestDto manifest,
        string? immutableManifestSha256,
        ReadOnlyMemory<byte>? immutableAuthorityManifestBytes)
        => BuildProjection(manifest, immutableManifestSha256, immutableAuthorityManifestBytes);

    internal static PublicReleaseTruthProjectionDto BuildProjection(
        PublicReleaseManifestDto manifest,
        string? immutableManifestSha256,
        ReadOnlyMemory<byte>? immutableAuthorityManifestBytes)
    {
        ArgumentNullException.ThrowIfNull(manifest);

        string manifestSha256 = NormalizeSha256(immutableManifestSha256);
        manifestSha256 = VerifyAuthorityManifestDigest(
            manifestSha256,
            immutableAuthorityManifestBytes);

        string[] platforms = manifest.Downloads
            .Select(ResolvePlatformId)
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .Take(MaximumPlatformCount + 1)
            .ToArray();
        if (platforms.Length > MaximumPlatformCount)
        {
            platforms = [PublicReleaseTruthProjectionDto.Invalid];
        }
        var primaryHeads = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (string platform in platforms)
        {
            string[] heads = manifest.Downloads
                .Where(artifact => string.Equals(ResolvePlatformId(artifact), platform, StringComparison.Ordinal))
                .Select(static artifact => NormalizeToken(artifact.Head))
                .Where(static head => head is not PublicReleaseTruthProjectionDto.Unknown)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(static head => string.Equals(head, "avalonia", StringComparison.Ordinal) ? 0 : 1)
                .ThenBy(static head => head, StringComparer.Ordinal)
                .ToArray();
            primaryHeads[platform] = heads.FirstOrDefault() ?? PublicReleaseTruthProjectionDto.Unknown;
        }

        return new PublicReleaseTruthProjectionDto(
            ContractName: PublicReleaseTruthProjectionDto.Schema,
            ReleaseVersion: NormalizeIdentifier(manifest.Version),
            Channel: NormalizeToken(manifest.Channel),
            ReleaseStatus: NormalizeToken(manifest.Status),
            RolloutState: NormalizeToken(manifest.RolloutState),
            SupportabilityState: NormalizeToken(manifest.SupportabilityState),
            AvailablePlatforms: platforms,
            PrimaryHeadByPlatform: primaryHeads,
            ArtifactCount: manifest.Downloads.Count,
            DownloadAccessPosture: ResolveDownloadAccessPosture(manifest.Downloads),
            KnownIssueSummary: NormalizeSummary(manifest.KnownIssueSummary),
            ManifestSha256: manifestSha256,
            RegistryCommit: PublicReleaseTruthProjectionDto.Missing,
            ReleaseDecisionStatus: PublicReleaseTruthProjectionDto.Missing,
            ReleaseDecisionSha256: PublicReleaseTruthProjectionDto.Missing);
    }

    internal static string NormalizeSha256(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return PublicReleaseTruthProjectionDto.Missing;
        }

        string normalized = value.Trim();
        return normalized.Length == 64 && normalized.All(static character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f')
                ? normalized
                : PublicReleaseTruthProjectionDto.Invalid;
    }

    internal static string VerifyAuthorityManifestDigest(
        string normalizedDigest,
        ReadOnlyMemory<byte>? authorityManifestBytes)
    {
        if (authorityManifestBytes is not { } bytes || bytes.IsEmpty)
        {
            return normalizedDigest == PublicReleaseTruthProjectionDto.Missing
                ? normalizedDigest
                : PublicReleaseTruthProjectionDto.Invalid;
        }

        if (normalizedDigest is PublicReleaseTruthProjectionDto.Missing
            or PublicReleaseTruthProjectionDto.Invalid)
        {
            return normalizedDigest;
        }

        byte[] expected = Convert.FromHexString(normalizedDigest);
        Span<byte> actual = stackalloc byte[32];
        SHA256.HashData(bytes.Span, actual);
        return CryptographicOperations.FixedTimeEquals(expected, actual)
            ? normalizedDigest
            : PublicReleaseTruthProjectionDto.Invalid;
    }

    internal static string ResolvePlatformId(PublicReleaseArtifactDto artifact)
    {
        string[] candidates =
        [
            artifact.PlatformId ?? string.Empty,
            artifact.Rid ?? string.Empty,
            artifact.Platform ?? string.Empty
        ];
        foreach (string candidate in candidates)
        {
            string normalized = candidate.Trim().ToLowerInvariant();
            if (normalized.Contains("osx", StringComparison.Ordinal)
                || normalized.Contains("mac", StringComparison.Ordinal)
                || normalized.Contains("darwin", StringComparison.Ordinal))
            {
                return "macos";
            }

            if (normalized.Equals("win", StringComparison.Ordinal)
                || normalized.StartsWith("win-", StringComparison.Ordinal)
                || normalized.Contains("windows", StringComparison.Ordinal))
            {
                return "windows";
            }

            if (normalized.Contains("linux", StringComparison.Ordinal))
            {
                return "linux";
            }
        }

        return NormalizeToken(candidates.FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value)));
    }

    internal static string ResolveDownloadAccessPosture(IReadOnlyList<PublicReleaseArtifactDto> artifacts)
    {
        if (artifacts.Count == 0)
        {
            return "unavailable";
        }

        var accessClasses = new HashSet<string>(StringComparer.Ordinal);
        foreach (PublicReleaseArtifactDto artifact in artifacts)
        {
            string accessClass = NormalizeToken(artifact.InstallAccessClass);
            if (accessClass is not "open_public" and not "account_recommended" and not "account_required")
            {
                return PublicReleaseTruthProjectionDto.Unknown;
            }

            accessClasses.Add(accessClass);
        }

        return accessClasses.Count == 1
            ? accessClasses.Single()
            : "mixed";
    }

    internal static string NormalizeToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return PublicReleaseTruthProjectionDto.Unknown;
        }

        string normalized = value.Trim().ToLowerInvariant();
        if (normalized.Length > MaximumTokenLength)
        {
            return PublicReleaseTruthProjectionDto.Invalid;
        }

        Span<char> buffer = stackalloc char[normalized.Length];
        int length = 0;
        bool previousSeparator = false;
        foreach (char character in normalized)
        {
            if (char.IsAsciiLetterOrDigit(character))
            {
                buffer[length++] = character;
                previousSeparator = false;
            }
            else if (!previousSeparator && length > 0)
            {
                buffer[length++] = '_';
                previousSeparator = true;
            }
        }

        while (length > 0 && buffer[length - 1] == '_')
        {
            length--;
        }

        return length == 0
            ? PublicReleaseTruthProjectionDto.Unknown
            : new string(buffer[..length]);
    }

    internal static string NormalizeSummary(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return PublicReleaseTruthProjectionDto.Unknown;
        }

        string normalized = value.Trim();
        return normalized.Length <= MaximumKnownIssueSummaryLength
            ? normalized
            : PublicReleaseTruthProjectionDto.Invalid;
    }

    internal static string NormalizeIdentifier(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return PublicReleaseTruthProjectionDto.Unknown;
        }

        string normalized = value.Trim();
        return normalized.Length <= MaximumTokenLength
            ? normalized
            : PublicReleaseTruthProjectionDto.Invalid;
    }
}
