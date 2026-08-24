using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Text.Json;

namespace Chummer.Run.AI.Services.BuildGhost;

public interface IBuildGhostPersonaReleaseRegistry
{
    BuildGhostPersonaReleaseProjection ResolveRook();
}

public sealed class BuildGhostPersonaReleaseRegistry : IBuildGhostPersonaReleaseRegistry
{
    private readonly IReadOnlyList<BuildGhostPersonaMediaRelease> _releases;
    private readonly BuildGhostToughTongueStockAvatarBindingValidation _avatarBindingValidation;

    public BuildGhostPersonaReleaseRegistry(IEnumerable<BuildGhostPersonaMediaRelease> releases)
        : this(
            releases,
            new BuildGhostToughTongueStockAvatarBindingValidation(
                false,
                null,
                ["stock-avatar-provider-id-missing-or-invalid"]))
    {
    }

    public BuildGhostPersonaReleaseRegistry(
        IEnumerable<BuildGhostPersonaMediaRelease> releases,
        BuildGhostToughTongueStockAvatarBinding avatarBinding)
        : this(
            releases,
            new BuildGhostToughTongueStockAvatarBindingValidation(
                BuildGhostToughTongueStockAvatarBindingContract.Validate(avatarBinding).Count == 0,
                avatarBinding,
                BuildGhostToughTongueStockAvatarBindingContract.Validate(avatarBinding)))
    {
    }

    private BuildGhostPersonaReleaseRegistry(
        IEnumerable<BuildGhostPersonaMediaRelease> releases,
        BuildGhostToughTongueStockAvatarBindingValidation avatarBindingValidation)
    {
        _releases = releases?.ToArray() ?? throw new ArgumentNullException(nameof(releases));
        _avatarBindingValidation = avatarBindingValidation
            ?? throw new ArgumentNullException(nameof(avatarBindingValidation));
    }

    public BuildGhostPersonaReleaseRegistry(IConfiguration configuration)
        : this(
            LoadConfiguredReleases(configuration),
            BuildGhostToughTongueStockAvatarBindingContract.FromConfiguration(configuration))
    {
    }

    public BuildGhostPersonaReleaseProjection ResolveRook()
    {
        BuildGhostPersonaMediaRelease? voice = Latest(ToughTongueBuildGhostPersonaIds.RookVoice, "synthetic-voice");
        List<string> blockers = [.. _avatarBindingValidation.RejectionReasons];
        bool avatarReady = _avatarBindingValidation.Accepted
            && _avatarBindingValidation.Binding is not null;
        bool voiceReady = IsReady(voice, "synthetic-voice", blockers);
        if (voice is not null
            && !voice.Provenance.Contains("synthetic", StringComparison.OrdinalIgnoreCase))
        {
            voiceReady = false;
            blockers.Add("voice-provenance-is-not-declared-synthetic");
        }

        return new BuildGhostPersonaReleaseProjection(
            ToughTongueBuildGhostPersonaIds.Rook,
            _avatarBindingValidation.Binding?.AvatarAlias ?? ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
            ToughTongueBuildGhostPersonaIds.RookVoice,
            avatarReady ? "provider-managed-default" : "invalid",
            voice?.ReleaseState ?? "missing",
            avatarReady,
            voiceReady,
            avatarReady && voiceReady ? "provider-managed-avatar-and-voice" : avatarReady ? "provider-managed-avatar-and-text-only" : "local-text-only",
            blockers.Distinct(StringComparer.Ordinal).OrderBy(static blocker => blocker, StringComparer.Ordinal).ToArray());
    }

    private BuildGhostPersonaMediaRelease? Latest(string assetId, string assetKind)
        => _releases
            .Where(release => string.Equals(release.Schema, ToughTongueBuildGhostContractVersions.PersonaReleaseV1, StringComparison.Ordinal)
                && string.Equals(release.PersonaId, ToughTongueBuildGhostPersonaIds.Rook, StringComparison.Ordinal)
                && string.Equals(release.AssetId, assetId, StringComparison.Ordinal)
                && string.Equals(release.AssetKind, assetKind, StringComparison.Ordinal))
            .OrderByDescending(static release => release.ReviewedAtUtc)
            .FirstOrDefault();

    private static IReadOnlyList<BuildGhostPersonaMediaRelease> LoadConfiguredReleases(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        string? configuredPath = configuration["CHUMMER_BUILD_GHOST_PERSONA_RELEASE_REGISTRY_PATH"];
        if (string.IsNullOrWhiteSpace(configuredPath))
        {
            return [];
        }

        string path = Path.GetFullPath(configuredPath.Trim());
        FileInfo file = new(path);
        if (!file.Exists || file.Length <= 0 || file.Length > 512 * 1024)
        {
            return [];
        }

        try
        {
            return JsonSerializer.Deserialize<BuildGhostPersonaMediaRelease[]>(
                    File.ReadAllText(path),
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? [];
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            return [];
        }
    }

    private static bool IsReady(
        BuildGhostPersonaMediaRelease? release,
        string expectedKind,
        List<string> blockers)
    {
        if (release is null)
        {
            blockers.Add($"{expectedKind}-release-missing");
            return false;
        }

        bool ready = true;
        if (!string.Equals(release.Owner, "Chummer", StringComparison.Ordinal))
        {
            blockers.Add($"{expectedKind}-owner-not-chummer");
            ready = false;
        }

        if (string.IsNullOrWhiteSpace(release.ContentDigest)
            || !release.ContentDigest.StartsWith("sha256:", StringComparison.Ordinal))
        {
            blockers.Add($"{expectedKind}-digest-invalid");
            ready = false;
        }

        if (string.IsNullOrWhiteSpace(release.Provenance))
        {
            blockers.Add($"{expectedKind}-provenance-missing");
            ready = false;
        }

        if (string.IsNullOrWhiteSpace(release.ConsentReceiptId))
        {
            blockers.Add($"{expectedKind}-consent-receipt-missing");
            ready = false;
        }

        if (!string.Equals(release.LicensePosture, "chummer-owned", StringComparison.Ordinal)
            || !string.Equals(release.ProviderVerificationState, "verified", StringComparison.Ordinal)
            || !string.Equals(release.ReleaseState, "approved", StringComparison.Ordinal))
        {
            blockers.Add($"{expectedKind}-release-not-approved");
            ready = false;
        }

        return ready;
    }
}
