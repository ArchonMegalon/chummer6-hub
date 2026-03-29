using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.AI.Services.Ops;
using InteropContracts = Chummer.Play.Contracts.Interop;

namespace Chummer.Run.AI.Services.Interop;

public interface IInteropExportService
{
    InteropContracts.InteropExportPackage Export(InteropContracts.InteropExportRequest request);
    InteropContracts.InteropImportResult Import(InteropContracts.InteropImportRequest request);
    InteropContracts.InteropRoundTripResult RoundTrip(InteropContracts.InteropRoundTripRequest request);
}

public sealed class InteropExportService : IInteropExportService
{
    private sealed record StoredAsset(
        string CampaignId,
        string? SessionId,
        InteropContracts.InteropAssetKind AssetKind,
        string AssetId,
        string DisplayName,
        string PayloadJson);

    private readonly ConcurrentDictionary<string, StoredAsset> _assets = new(StringComparer.OrdinalIgnoreCase);
    private readonly IGmOpsBoardService _opsBoard;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = false
    };

    public InteropExportService(IGmOpsBoardService opsBoard)
    {
        _opsBoard = opsBoard;
    }

    public InteropContracts.InteropExportPackage Export(InteropContracts.InteropExportRequest request)
    {
        var campaignId = request.CampaignId.Trim();
        var sessionId = NormalizeOptional(request.SessionId);
        EnsureSeedData(campaignId, sessionId);

        var kinds = NormalizeAssetKinds(request.AssetKinds);
        var assetIdFilter = NormalizeAssetIds(request.AssetIds);
        var exportedAtUtc = DateTimeOffset.UtcNow;
        var roundTripId = $"rt_{Guid.NewGuid():N}";
        var packageId = $"interop_{Guid.NewGuid():N}";

        var assets = ResolveAssetSelection(campaignId, sessionId, kinds)
            .Where(item => assetIdFilter is null || assetIdFilter.Contains(item.AssetId))
            .OrderBy(item => item.AssetKind)
            .ThenBy(item => item.AssetId, StringComparer.Ordinal)
            .Select(item => ToDocument(item, request, roundTripId, exportedAtUtc))
            .ToArray();

        var manifest = BuildManifest(assets);
        return new InteropContracts.InteropExportPackage(
            PackageId: packageId,
            CampaignId: campaignId,
            SessionId: sessionId,
            ContractFamily: request.ContractFamily,
            SchemaVersion: request.SchemaVersion,
            ExportedAtUtc: exportedAtUtc,
            ExportedBy: request.RequestedBy,
            Manifest: manifest,
            Assets: assets);
    }

    public InteropContracts.InteropImportResult Import(InteropContracts.InteropImportRequest request)
    {
        var package = request.Package;
        var importedAtUtc = DateTimeOffset.UtcNow;
        var importedBy = request.ImportedBy.Trim();
        var campaignId = package.CampaignId.Trim();
        var sessionId = NormalizeOptional(package.SessionId);

        if (request.Mode == InteropContracts.InteropImportMode.Replace)
        {
            RemoveCampaignAssets(campaignId);
        }

        var results = new List<InteropContracts.InteropImportAssetResult>(package.Assets.Count);
        foreach (var document in package.Assets)
        {
            var payloadSha = ComputeSha256Hex(document.PayloadJson);
            var roundTripOk = string.Equals(document.Provenance.PayloadSha256, payloadSha, StringComparison.OrdinalIgnoreCase)
                && string.Equals(document.Provenance.ContractFamily, package.ContractFamily, StringComparison.Ordinal)
                && string.Equals(document.Provenance.SchemaVersion, package.SchemaVersion, StringComparison.Ordinal);

            if (!roundTripOk)
            {
                results.Add(new InteropContracts.InteropImportAssetResult(
                    AssetKind: document.AssetKind,
                    AssetId: document.AssetId,
                    Outcome: "rejected",
                    ProvenanceRoundTrip: false,
                    Detail: "payload hash or provenance metadata mismatch"));
                continue;
            }

            UpsertAsset(new StoredAsset(
                CampaignId: campaignId,
                SessionId: sessionId,
                AssetKind: document.AssetKind,
                AssetId: document.AssetId,
                DisplayName: document.DisplayName,
                PayloadJson: document.PayloadJson));

            results.Add(new InteropContracts.InteropImportAssetResult(
                AssetKind: document.AssetKind,
                AssetId: document.AssetId,
                Outcome: "imported",
                ProvenanceRoundTrip: true));
        }

        var importedCount = results.Count(item => string.Equals(item.Outcome, "imported", StringComparison.Ordinal));
        var rejectedCount = results.Count - importedCount;
        return new InteropContracts.InteropImportResult(
            PackageId: package.PackageId,
            CampaignId: campaignId,
            SessionId: sessionId,
            ImportedBy: importedBy,
            Mode: request.Mode,
            ImportedCount: importedCount,
            RejectedCount: rejectedCount,
            ProvenanceRoundTrip: results.All(static item => item.ProvenanceRoundTrip),
            ImportedAtUtc: importedAtUtc,
            Assets: results);
    }

    public InteropContracts.InteropRoundTripResult RoundTrip(InteropContracts.InteropRoundTripRequest request)
    {
        var exported = Export(request.Export);
        var imported = Import(new InteropContracts.InteropImportRequest(exported, request.ImportedBy, request.Mode));
        return new InteropContracts.InteropRoundTripResult(
            RoundTripId: exported.Assets.FirstOrDefault()?.Provenance.RoundTripId ?? $"rt_{Guid.NewGuid():N}",
            ExportPackage: exported,
            ImportResult: imported,
            ProvenanceRoundTrip: imported.ProvenanceRoundTrip);
    }

    private IEnumerable<StoredAsset> ResolveAssetSelection(
        string campaignId,
        string? sessionId,
        HashSet<InteropContracts.InteropAssetKind> kinds)
    {
        var baseline = _assets.Values
            .Where(item => string.Equals(item.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase))
            .Where(item => sessionId is null || string.Equals(item.SessionId, sessionId, StringComparison.OrdinalIgnoreCase))
            .Where(item => kinds.Contains(item.AssetKind));

        foreach (var item in baseline)
        {
            yield return item;
        }

        if (!kinds.Contains(InteropContracts.InteropAssetKind.Prep))
        {
            yield break;
        }

        var prepFromOps = _opsBoard.ListPrepAssets(
            campaignId: campaignId,
            sessionId: sessionId,
            includeReusableCampaignAssets: true).Items;
        foreach (var item in prepFromOps)
        {
            var payload = JsonSerializer.Serialize(new
            {
                item.CampaignId,
                item.SessionId,
                item.SceneId,
                item.Kind,
                item.Audience,
                item.Status,
                item.Tags,
                item.Reusable,
                item.ChecklistItemCount,
                item.ChecklistCompletedCount,
                item.UpdatedAtUtc,
                item.LastRevealedAtUtc,
                item.GovernedProject
            }, _jsonOptions);

            yield return new StoredAsset(
                CampaignId: campaignId,
                SessionId: sessionId,
                AssetKind: InteropContracts.InteropAssetKind.Prep,
                AssetId: item.AssetId,
                DisplayName: item.Title,
                PayloadJson: payload);
        }
    }

    private InteropContracts.InteropAssetDocument ToDocument(
        StoredAsset asset,
        InteropContracts.InteropExportRequest request,
        string roundTripId,
        DateTimeOffset exportedAtUtc)
    {
        var payloadSha = ComputeSha256Hex(asset.PayloadJson);
        return new InteropContracts.InteropAssetDocument(
            AssetKind: asset.AssetKind,
            AssetId: asset.AssetId,
            DisplayName: asset.DisplayName,
            PayloadJson: asset.PayloadJson,
            Provenance: new InteropContracts.InteropRoundTripProvenance(
                ContractFamily: request.ContractFamily,
                SchemaVersion: request.SchemaVersion,
                SourceSystem: "chummer.run-services",
                SourceAssetId: asset.AssetId,
                PayloadSha256: payloadSha,
                ExportedAtUtc: exportedAtUtc,
                ExportedBy: request.RequestedBy,
                RoundTripId: roundTripId,
                Pointers:
                [
                    new InteropContracts.InteropProvenancePointer("campaign", asset.CampaignId, "campaign scope"),
                    new InteropContracts.InteropProvenancePointer("asset-kind", asset.AssetKind.ToString(), "interop export kind")
                ]));
    }

    private static InteropContracts.InteropExportManifest BuildManifest(IReadOnlyList<InteropContracts.InteropAssetDocument> assets)
    {
        var packageSha = ComputeSha256Hex(string.Join('|', assets.Select(static item => item.Provenance.PayloadSha256)));
        return new InteropContracts.InteropExportManifest(
            CharacterCount: assets.Count(static item => item.AssetKind == InteropContracts.InteropAssetKind.Character),
            NpcCount: assets.Count(static item => item.AssetKind == InteropContracts.InteropAssetKind.Npc),
            SessionCount: assets.Count(static item => item.AssetKind == InteropContracts.InteropAssetKind.Session),
            EncounterCount: assets.Count(static item => item.AssetKind == InteropContracts.InteropAssetKind.Encounter),
            PrepCount: assets.Count(static item => item.AssetKind == InteropContracts.InteropAssetKind.Prep),
            TotalCount: assets.Count,
            PackageSha256: packageSha);
    }

    private void EnsureSeedData(string campaignId, string? sessionId)
    {
        var resolvedSessionId = sessionId ?? "session_default";
        UpsertAsset(new StoredAsset(
            CampaignId: campaignId,
            SessionId: resolvedSessionId,
            AssetKind: InteropContracts.InteropAssetKind.Character,
            AssetId: "character_runner_01",
            DisplayName: "Runner Profile",
            PayloadJson: SerializePayload(new
            {
                CharacterId = "character_runner_01",
                Name = "Kestrel",
                Archetype = "Infiltrator",
                StreetName = "Kestrel",
                CampaignId = campaignId,
                SessionId = resolvedSessionId
            })));

        UpsertAsset(new StoredAsset(
            CampaignId: campaignId,
            SessionId: resolvedSessionId,
            AssetKind: InteropContracts.InteropAssetKind.Npc,
            AssetId: "npc_fixer_01",
            DisplayName: "Fixer Contact",
            PayloadJson: SerializePayload(new
            {
                NpcId = "npc_fixer_01",
                Name = "Rook",
                Role = "Fixer",
                Faction = "Redmond Brokers",
                CampaignId = campaignId
            })));

        UpsertAsset(new StoredAsset(
            CampaignId: campaignId,
            SessionId: resolvedSessionId,
            AssetKind: InteropContracts.InteropAssetKind.Session,
            AssetId: resolvedSessionId,
            DisplayName: $"Session {resolvedSessionId}",
            PayloadJson: SerializePayload(new
            {
                SessionId = resolvedSessionId,
                CampaignId = campaignId,
                CollaborationMode = "local-first",
                RuntimeBundleKind = "session-runtime-bundle"
            })));

        UpsertAsset(new StoredAsset(
            CampaignId: campaignId,
            SessionId: resolvedSessionId,
            AssetKind: InteropContracts.InteropAssetKind.Encounter,
            AssetId: $"encounter_{resolvedSessionId}",
            DisplayName: "Loading Bay Ambush",
            PayloadJson: SerializePayload(new
            {
                EncounterId = $"encounter_{resolvedSessionId}",
                SessionId = resolvedSessionId,
                SceneId = "scene_loading_bay",
                Tags = new[] { "ambush", "warehouse" }
            })));

        UpsertAsset(new StoredAsset(
            CampaignId: campaignId,
            SessionId: resolvedSessionId,
            AssetKind: InteropContracts.InteropAssetKind.Prep,
            AssetId: $"prep_{resolvedSessionId}",
            DisplayName: "Fallback extraction checklist",
            PayloadJson: SerializePayload(new
            {
                PrepAssetId = $"prep_{resolvedSessionId}",
                SessionId = resolvedSessionId,
                Checklist = new[]
                {
                    "Confirm extraction van",
                    "Spoof loading dock cameras"
                }
            })));
    }

    private void RemoveCampaignAssets(string campaignId)
    {
        var keys = _assets
            .Where(item => string.Equals(item.Value.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase))
            .Select(item => item.Key)
            .ToArray();

        foreach (var key in keys)
        {
            _assets.TryRemove(key, out _);
        }
    }

    private void UpsertAsset(StoredAsset asset)
    {
        var key = ComposeAssetKey(asset.CampaignId, asset.AssetKind, asset.AssetId);
        _assets[key] = asset;
    }

    private static string ComposeAssetKey(string campaignId, InteropContracts.InteropAssetKind kind, string assetId) =>
        $"{campaignId}::{kind}::{assetId}";

    private string SerializePayload<T>(T payload)
    {
        return JsonSerializer.Serialize(payload, _jsonOptions);
    }

    private static HashSet<InteropContracts.InteropAssetKind> NormalizeAssetKinds(IReadOnlyList<InteropContracts.InteropAssetKind>? kinds)
    {
        if (kinds is null || kinds.Count == 0)
        {
            return Enum.GetValues<InteropContracts.InteropAssetKind>().ToHashSet();
        }

        return kinds.ToHashSet();
    }

    private static HashSet<string>? NormalizeAssetIds(IReadOnlyList<string>? assetIds)
    {
        if (assetIds is null || assetIds.Count == 0)
        {
            return null;
        }

        return assetIds
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item.Trim())
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
    }

    private static string? NormalizeOptional(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string ComputeSha256Hex(string payload)
    {
        var bytes = Encoding.UTF8.GetBytes(payload);
        var hash = SHA256.HashData(bytes);
        return Convert.ToHexString(hash);
    }
}
