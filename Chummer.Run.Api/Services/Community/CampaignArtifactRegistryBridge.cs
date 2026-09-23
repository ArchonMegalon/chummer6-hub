using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Run.Contracts.Registry;
using Chummer.Run.Registry.Services;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignArtifactRegistryBridge
{
    private readonly HubArtifactStore _store = new();
    private readonly object _sync = new();
    private readonly CommunityStore? _primaryCommunity;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public CampaignArtifactRegistryBridge(CommunityStore communityStore)
    {
        ArgumentNullException.ThrowIfNull(communityStore);
        _primaryCommunity = communityStore.IsPrimary ? communityStore : null;
        _storagePath = communityStore.IsPrimary ? string.Empty : ResolveStoragePath(communityStore.StoragePath);
        if (_primaryCommunity is null) Load();
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
        if (_primaryCommunity is not null)
            return ExecuteAftermathRegistrationTransaction(request, static registration => registration);

        lock (_sync)
        {
            return RegisterAftermathPackageLocked(request);
        }
    }

    public TResult ExecuteAftermathRegistrationTransaction<TResult>(
        AftermathArtifactRegistrationRequest request,
        Func<CampaignArtifactRegistration, TResult> operation)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(operation);

        if (_primaryCommunity is not null)
        {
            return _primaryCommunity.ExecutePrimaryArtifactTransaction(() =>
            {
                // Always acquire Community before the private registry lock.
                // Restore from this operation's current primary revision, never
                // the previous in-process HubArtifactStore instance.
                lock (_sync)
                {
                    HubArtifactStoreBackupPackage current = _primaryCommunity.CampaignArtifactRegistry
                        ?? new HubArtifactStore().ExportBackup();
                    ValidatePrimaryBackup(current);
                    _store.RestoreBackup(current);
                    return operation(RegisterAftermathPackageLocked(request));
                }
            });
        }

        lock (_sync)
        {
            HubArtifactStoreBackupPackage storeBefore = _store.ExportBackup();
            byte[]? durableStateBefore = File.Exists(_storagePath)
                ? File.ReadAllBytes(_storagePath)
                : null;

            try
            {
                CampaignArtifactRegistration registration = RegisterAftermathPackageLocked(request);
                return operation(registration);
            }
            catch (Exception failure)
            {
                try
                {
                    _store.RestoreBackup(storeBefore);
                    RestoreDurableStateLocked(durableStateBefore);
                }
                catch (Exception rollbackFailure)
                {
                    throw new AggregateException(
                        "Aftermath artifact registration failed and its registry rollback also failed.",
                        failure,
                        rollbackFailure);
                }

                throw;
            }
        }
    }

    private CampaignArtifactRegistration RegisterAftermathPackageLocked(AftermathArtifactRegistrationRequest request)
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
        if (_primaryCommunity is not null)
        {
            _primaryCommunity.CampaignArtifactRegistry = _store.ExportBackup();
            _primaryCommunity.PersistLocked();
            return;
        }
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        string payload = JsonSerializer.Serialize(_store.ExportBackup(), _jsonOptions);
        File.WriteAllText(tempPath, payload);
        File.Move(tempPath, _storagePath, true);
    }

    internal static void ValidatePrimaryBackup(HubArtifactStoreBackupPackage? backup)
    {
        if (backup is null) return;
        if (backup.ContractFamily != "hub_state_backup_v1" || backup.Artifacts is null
            || backup.RuntimeBundleArtifacts is null || backup.RuntimeBundleHeads is null || backup.DeadLetters is null
            || backup.RuntimeBundleArtifacts.Count != 0 || backup.RuntimeBundleHeads.Count != 0
            || backup.DeadLetters.Count != 0 || backup.UpsertCount < backup.Artifacts.Count
            || backup.RuntimeIssueCount != 0 || backup.RuntimeIssueIdempotentCount != 0
            || backup.InstallCount != 0 || backup.ReviewCount != 0)
            throw new InvalidDataException("Primary campaign metadata is not a runtime/public registry authority.");
        var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var artifact in backup.Artifacts)
        {
            if (artifact is null || string.IsNullOrWhiteSpace(artifact.Id) || !ids.Add(artifact.Id)
                || artifact.Kind is not (HubArtifactKind.RecapPackage or HubArtifactKind.ReplayPackage)
                || artifact.Visibility != ArtifactVisibilityModes.CampaignShared
                || artifact.TrustTier != ArtifactTrustTiers.Curated || artifact.State != HubArtifactState.Active
                || string.IsNullOrWhiteSpace(artifact.Owner) || string.IsNullOrWhiteSpace(artifact.Version)
                || string.IsNullOrWhiteSpace(artifact.RulesetId) || string.IsNullOrWhiteSpace(artifact.Name)
                || artifact.PublisherId is not null || artifact.InstallCount != 0 || artifact.ActiveRuntimeRefCount != 0
                || artifact.ReviewScores is { Count: > 0 })
                throw new InvalidDataException("Primary campaign artifact identity or scope is invalid.");
        }
    }

    private void RestoreDurableStateLocked(byte[]? durableState)
    {
        string tempPath = $"{_storagePath}.tmp";
        if (durableState is null)
        {
            File.Delete(tempPath);
            File.Delete(_storagePath);
            return;
        }

        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        File.WriteAllBytes(tempPath, durableState);
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
            ?? "Continuity: reviewed return path remains attached to the same campaign spine.";
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
