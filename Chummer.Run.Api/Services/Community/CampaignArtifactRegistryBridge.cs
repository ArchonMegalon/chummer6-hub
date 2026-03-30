using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Run.Contracts.Registry;
using Chummer.Run.Registry.Services;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignArtifactRegistryBridge
{
    private readonly HubArtifactStore _store = new();
    private readonly object _sync = new();
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public CampaignArtifactRegistryBridge(CommunityStore communityStore)
        : this(communityStore.StoragePath)
    {
    }

    public CampaignArtifactRegistryBridge(string communityStorePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(communityStorePath);
        _storagePath = ResolveStoragePath(communityStorePath);
        Load();
    }

    public CampaignArtifactRegistration RegisterAftermathPackage(AftermathArtifactRegistrationRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        lock (_sync)
        {
            string normalizedPackageKind = NormalizeToken(request.PackageKind, "session_recap");
            string version = ComposeArtifactVersion(request.GeneratedAtUtc, normalizedPackageKind);
            string runtimeFingerprint = $"sha256:{ComputeFingerprint(request)}";
            HubArtifactKind artifactKind = ResolveArtifactKind(normalizedPackageKind);
            HubArtifactMetadata artifact = _store.UpsertArtifact(new HubArtifactCreateRequest(
                Name: BuildArtifactName(request),
                Kind: artifactKind,
                Version: version,
                RulesetId: NormalizeToken(request.RulesetId, "sr5"),
                Visibility: ArtifactVisibilityModes.CampaignShared,
                TrustTier: ArtifactTrustTiers.Curated,
                OwnerId: NormalizeToken(request.OwnerUserId, "unknown"),
                PublisherId: null,
                Summary: NormalizeToken(request.Summary, request.Title),
                Description: BuildArtifactDescription(request),
                RuntimeFingerprint: runtimeFingerprint,
                StateReason: $"Bound to campaign {NormalizeToken(request.CampaignId, "unknown")} package {NormalizeToken(request.PackageId, "unknown")}.",
                EngineApiVersion: null));
            PersistLocked();

            string packageLabel = artifactKind == HubArtifactKind.ReplayPackage ? "replay" : "recap";
            string runScope = string.IsNullOrWhiteSpace(request.RunTitle)
                ? $"{NormalizeToken(request.CampaignName, "Campaign")} campaign lane"
                : $"{request.RunTitle} run";
            return new CampaignArtifactRegistration(
                ArtifactId: artifact.Id,
                ArtifactKind: artifact.Kind.ToString(),
                ArtifactVersion: artifact.Version,
                ArtifactVisibility: artifact.Visibility,
                ArtifactTrustTier: artifact.TrustTier,
                ArtifactRulesetId: artifact.RulesetId,
                ProvenanceSummary: $"{NormalizeToken(request.RuleEnvironmentFingerprint, artifact.RulesetId)} + {packageLabel} artifact {artifact.Id} v{artifact.Version} keeps {runScope} attached to package {NormalizeToken(request.PackageId, "unknown")}.",
                AuditSummary: $"Artifact {artifact.Id} is active on the {artifact.Visibility} shelf with {artifact.TrustTier} trust for {artifact.RulesetId}; generated {request.GeneratedAtUtc:yyyy-MM-dd HH:mm} UTC by {NormalizeToken(request.OwnerUserId, "unknown")}.");
        }
    }

    private void Load()
    {
        lock (_sync)
        {
            if (!File.Exists(_storagePath))
            {
                return;
            }

            string json = File.ReadAllText(_storagePath);
            HubArtifactStoreBackupPackage backup = JsonSerializer.Deserialize<HubArtifactStoreBackupPackage>(json, _jsonOptions)
                ?? throw new InvalidOperationException($"Unable to deserialize campaign artifact registry backup: {_storagePath}");
            _store.RestoreBackup(backup);
        }
    }

    private void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        string payload = JsonSerializer.Serialize(_store.ExportBackup(), _jsonOptions);
        File.WriteAllText(tempPath, payload);
        File.Move(tempPath, _storagePath, true);
    }

    private static string ResolveStoragePath(string communityStorePath)
    {
        string fullPath = Path.GetFullPath(communityStorePath);
        string directory = Path.GetDirectoryName(fullPath) ?? Path.GetTempPath();
        return Path.Combine(directory, "campaign-artifact-registry.json");
    }

    private static HubArtifactKind ResolveArtifactKind(string packageKind)
        => packageKind.Contains("replay", StringComparison.OrdinalIgnoreCase)
            ? HubArtifactKind.ReplayPackage
            : HubArtifactKind.RecapPackage;

    private static string BuildArtifactName(AftermathArtifactRegistrationRequest request)
    {
        string runScope = string.IsNullOrWhiteSpace(request.RunTitle)
            ? NormalizeToken(request.CampaignName, "Campaign")
            : request.RunTitle!;
        string packageLabel = HumanizePackageKind(request.PackageKind);
        return $"{runScope} {packageLabel}";
    }

    private static string BuildArtifactDescription(AftermathArtifactRegistrationRequest request)
    {
        string campaignName = NormalizeToken(request.CampaignName, "campaign");
        string workspaceId = NormalizeToken(request.WorkspaceId, "workspace");
        string packageKind = HumanizePackageKind(request.PackageKind);
        string continuity = request.EvidenceLines.FirstOrDefault(static line => line.StartsWith("Continuity:", StringComparison.OrdinalIgnoreCase))
            ?? "Continuity: governed return lane remains attached to the same campaign spine.";
        return $"{packageKind} artifact for {campaignName} on {workspaceId}. {continuity}";
    }

    private static string ComposeArtifactVersion(DateTimeOffset generatedAtUtc, string packageKind)
    {
        string normalizedKind = NormalizeToken(packageKind, "session_recap")
            .Replace('_', '-')
            .ToLowerInvariant();
        return $"{generatedAtUtc:yyyy.MM.dd.HHmmss}.{normalizedKind}";
    }

    private static string ComputeFingerprint(AftermathArtifactRegistrationRequest request)
    {
        byte[] payload = JsonSerializer.SerializeToUtf8Bytes(new
        {
            request.PackageId,
            request.WorkspaceId,
            request.CampaignId,
            request.RunId,
            request.PackageKind,
            request.Title,
            request.Summary,
            request.OwnerUserId,
            request.RulesetId,
            request.RuleEnvironmentFingerprint,
            request.GeneratedAtUtc,
            EvidenceLines = request.EvidenceLines
        });
        return Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
    }

    private static string HumanizePackageKind(string packageKind)
        => NormalizeToken(packageKind, "session recap")
            .Replace('_', ' ')
            .Replace('-', ' ');

    private static string NormalizeToken(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
}

public sealed record AftermathArtifactRegistrationRequest(
    string PackageId,
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string? RunId,
    string? RunTitle,
    string PackageKind,
    string Title,
    string Summary,
    string OwnerUserId,
    string RulesetId,
    string RuleEnvironmentFingerprint,
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<string> EvidenceLines);

public sealed record CampaignArtifactRegistration(
    string ArtifactId,
    string ArtifactKind,
    string ArtifactVersion,
    string ArtifactVisibility,
    string ArtifactTrustTier,
    string ArtifactRulesetId,
    string ProvenanceSummary,
    string AuditSummary);
