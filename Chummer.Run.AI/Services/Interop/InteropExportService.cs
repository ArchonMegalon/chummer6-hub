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
    private static readonly string[] CampaignSupportedExchangeFormats =
    [
        "chummer.portable-dossier.v1",
        "chummer.portable-campaign.v1"
    ];

    private static readonly string[] SessionSupportedExchangeFormats =
    [
        "chummer.portable-dossier.v1",
        "chummer.portable-campaign.v1",
        "session-runtime-bundle.v1",
        "foundry-vtt.scene-ledger.v1"
    ];

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
        var compatibility = BuildExportCompatibilityReceipt(campaignId, sessionId, request, manifest);
        return new InteropContracts.InteropExportPackage(
            PackageId: packageId,
            CampaignId: campaignId,
            SessionId: sessionId,
            ContractFamily: request.ContractFamily,
            SchemaVersion: request.SchemaVersion,
            ExportedAtUtc: exportedAtUtc,
            ExportedBy: request.RequestedBy,
            Manifest: manifest,
            Compatibility: compatibility,
            Assets: assets);
    }

    public InteropContracts.InteropImportResult Import(InteropContracts.InteropImportRequest request)
    {
        var package = request.Package;
        var importedAtUtc = DateTimeOffset.UtcNow;
        var importedBy = request.ImportedBy.Trim();
        var campaignId = package.CampaignId.Trim();
        var sessionId = NormalizeOptional(package.SessionId);

        var results = new List<InteropContracts.InteropImportAssetResult>(package.Assets.Count);
        var stagedAssets = new List<StoredAsset>(package.Assets.Count);
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

            stagedAssets.Add(new StoredAsset(
                CampaignId: campaignId,
                SessionId: sessionId,
                AssetKind: document.AssetKind,
                AssetId: document.AssetId,
                DisplayName: document.DisplayName,
                PayloadJson: document.PayloadJson));

            results.Add(new InteropContracts.InteropImportAssetResult(
                AssetKind: document.AssetKind,
                AssetId: document.AssetId,
                Outcome: request.Mode == InteropContracts.InteropImportMode.InspectOnly ? "inspected" : "imported",
                ProvenanceRoundTrip: true,
                Detail: request.Mode == InteropContracts.InteropImportMode.InspectOnly
                    ? "validated without mutating campaign truth"
                    : null));
        }

        var importedCount = results.Count(item => string.Equals(item.Outcome, "imported", StringComparison.Ordinal));
        if (request.Mode == InteropContracts.InteropImportMode.InspectOnly)
        {
            importedCount = results.Count(item => string.Equals(item.Outcome, "inspected", StringComparison.Ordinal));
        }

        var rejectedCount = results.Count(item => string.Equals(item.Outcome, "rejected", StringComparison.Ordinal));
        if (request.Mode == InteropContracts.InteropImportMode.Replace && rejectedCount > 0)
        {
            for (int i = 0; i < results.Count; i++)
            {
                InteropContracts.InteropImportAssetResult result = results[i];
                if (!string.Equals(result.Outcome, "imported", StringComparison.Ordinal))
                {
                    continue;
                }

                results[i] = result with
                {
                    Outcome = "blocked",
                    Detail = "replace cutover was blocked because at least one asset failed provenance or compatibility validation"
                };
            }

            importedCount = 0;
        }

        var canMutate = request.Mode != InteropContracts.InteropImportMode.InspectOnly
            && (request.Mode != InteropContracts.InteropImportMode.Replace || rejectedCount == 0);
        if (canMutate)
        {
            if (request.Mode == InteropContracts.InteropImportMode.Replace)
            {
                RemoveCampaignAssets(campaignId);
            }

            foreach (StoredAsset stagedAsset in stagedAssets)
            {
                UpsertAsset(stagedAsset);
            }
        }

        var mutatedCount = canMutate ? importedCount : 0;
        var compatibility = BuildImportCompatibilityReceipt(package, request.Mode, importedCount, mutatedCount, rejectedCount);
        return new InteropContracts.InteropImportResult(
            PackageId: package.PackageId,
            CampaignId: campaignId,
            SessionId: sessionId,
            ImportedBy: importedBy,
            Mode: request.Mode,
            ImportedCount: importedCount,
            MutatedCount: mutatedCount,
            RejectedCount: rejectedCount,
            ProvenanceRoundTrip: results.All(static item => item.ProvenanceRoundTrip),
            ImportedAtUtc: importedAtUtc,
            Compatibility: compatibility,
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

    private static InteropContracts.InteropCompatibilityReceipt BuildExportCompatibilityReceipt(
        string campaignId,
        string? sessionId,
        InteropContracts.InteropExportRequest request,
        InteropContracts.InteropExportManifest manifest)
    {
        string formatId = sessionId is null
            ? "chummer.portable-campaign.v1"
            : "chummer.portable-campaign-session.v1";
        string compatibilityState = sessionId is null
            ? InteropContracts.InteropCompatibilityStates.CompatibleWithWarnings
            : InteropContracts.InteropCompatibilityStates.Compatible;
        string[] supportedExchangeFormats = sessionId is null
            ? CampaignSupportedExchangeFormats
            : SessionSupportedExchangeFormats;
        string contextSummary = sessionId is null
            ? $"Campaign {campaignId} is portable with governed dossier, prep, and aftermath truth, but the package does not yet pin a live session cutover."
            : $"Campaign {campaignId} and session {sessionId} are pinned to the same portable exchange receipt.";
        string receiptSummary = sessionId is null
            ? "Portable dossier/campaign exchange is ready for inspect-only review or merge, while governed replace stays review-required until a live session export is pinned."
            : "Portable dossier/campaign exchange is ready for inspect-only review, merge, or governed replace with a pinned session receipt.";
        string nextSafeAction = sessionId is null
            ? "Open inspect-only first or export again with a pinned session before you authorize governed replace on another surface."
            : "Share the portable package or open inspect-only first if the receiving surface wants a no-mutation compatibility review.";

        List<InteropContracts.InteropCompatibilityNote> notes =
        [
            new(
                Code: "format-identity",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Info,
                Summary: $"Package format {formatId} stays on {request.ContractFamily}/{request.SchemaVersion}."),
            new(
                Code: "asset-scope",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Info,
                Summary: $"{manifest.TotalCount} portable asset(s) cover {DescribeManifest(manifest)}."),
            new(
                Code: "provenance-pointers",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Info,
                Summary: "Every asset keeps payload-hash provenance, export identity, and campaign pointers on the same governed receipt.")
        ];

        if (sessionId is null)
        {
            notes.Add(new InteropContracts.InteropCompatibilityNote(
                Code: "session-binding-required-for-replace",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Warning,
                Summary: "No live session binding was requested, so replace should wait for a session-scoped export even though inspect-only and merge remain safe."));
        }
        else
        {
            notes.Add(new InteropContracts.InteropCompatibilityNote(
                Code: "session-binding",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Info,
                Summary: $"Session {sessionId} is pinned inside the portable package, so import and export can cite the same continuity-safe exchange receipt."));
        }

        return new InteropContracts.InteropCompatibilityReceipt(
            FormatId: formatId,
            CompatibilityState: compatibilityState,
            ContextSummary: contextSummary,
            ReceiptSummary: receiptSummary,
            NextSafeAction: nextSafeAction,
            SupportedExchangeFormats: supportedExchangeFormats,
            Notes: notes);
    }

    private static InteropContracts.InteropCompatibilityReceipt BuildImportCompatibilityReceipt(
        InteropContracts.InteropExportPackage package,
        InteropContracts.InteropImportMode mode,
        int importedCount,
        int mutatedCount,
        int rejectedCount)
    {
        List<InteropContracts.InteropCompatibilityNote> notes = package.Compatibility.Notes.ToList();
        string compatibilityState = rejectedCount > 0
            ? InteropContracts.InteropCompatibilityStates.Incompatible
            : package.Compatibility.CompatibilityState;
        string receiptSummary;
        string nextSafeAction;

        if (rejectedCount > 0)
        {
            notes.Add(new InteropContracts.InteropCompatibilityNote(
                Code: "payload-integrity-mismatch",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Error,
                Summary: $"{rejectedCount} portable asset(s) were rejected because the payload hash or provenance metadata no longer matched the export receipt."));
            receiptSummary = $"{rejectedCount} portable asset(s) were rejected, so the package can no longer claim a clean ecosystem handoff.";
            nextSafeAction = "Re-export the package from the source surface, then re-run inspect-only before you retry merge or replace.";
        }
        else if (mode == InteropContracts.InteropImportMode.InspectOnly)
        {
            notes.Add(new InteropContracts.InteropCompatibilityNote(
                Code: "inspect-only",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Info,
                Summary: $"Inspect-only validated {importedCount} portable asset(s) without mutating campaign truth."));
            receiptSummary = $"Inspect-only validated {importedCount} portable asset(s) without mutating campaign truth.";
            nextSafeAction = "Promote the inspected package to merge or keep the receipt attached as a governed compatibility note on the receiving surface.";
        }
        else if (mode == InteropContracts.InteropImportMode.Replace)
        {
            notes.Add(new InteropContracts.InteropCompatibilityNote(
                Code: "governed-replace",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Warning,
                Summary: $"Governed replace mutated {mutatedCount} portable asset(s) with an explicit cutover receipt instead of silent last-write-wins."));
            receiptSummary = $"Governed replace cut over {mutatedCount} portable asset(s) with explicit provenance and compatibility receipts.";
            nextSafeAction = "Record the cutover on the destination surface and keep the replace receipt attached to the same campaign lane.";
        }
        else
        {
            notes.Add(new InteropContracts.InteropCompatibilityNote(
                Code: "merge-import",
                Severity: InteropContracts.InteropCompatibilityNoteSeverities.Info,
                Summary: $"Merge import accepted {importedCount} portable asset(s) while preserving governed identity and provenance history."));
            receiptSummary = $"Merge import accepted {importedCount} portable asset(s) with provenance and compatibility intact.";
            nextSafeAction = "Continue from the merged campaign lane or run inspect-only on a later package before the next governed replace.";
        }

        return new InteropContracts.InteropCompatibilityReceipt(
            FormatId: package.Compatibility.FormatId,
            CompatibilityState: compatibilityState,
            ContextSummary: package.Compatibility.ContextSummary,
            ReceiptSummary: receiptSummary,
            NextSafeAction: nextSafeAction,
            SupportedExchangeFormats: package.Compatibility.SupportedExchangeFormats,
            Notes: notes);
    }

    private static string DescribeManifest(InteropContracts.InteropExportManifest manifest)
    {
        List<string> parts = [];

        if (manifest.CharacterCount > 0)
        {
            parts.Add($"{manifest.CharacterCount} dossier(s)");
        }

        if (manifest.NpcCount > 0)
        {
            parts.Add($"{manifest.NpcCount} NPC(s)");
        }

        if (manifest.SessionCount > 0)
        {
            parts.Add($"{manifest.SessionCount} session bundle(s)");
        }

        if (manifest.EncounterCount > 0)
        {
            parts.Add($"{manifest.EncounterCount} encounter packet(s)");
        }

        if (manifest.PrepCount > 0)
        {
            parts.Add($"{manifest.PrepCount} governed prep packet(s)");
        }

        return parts.Count == 0 ? "no portable assets" : string.Join(", ", parts);
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
                RuntimeBundleKind = "session-runtime-bundle",
                SupportedExchangeFormats = SessionSupportedExchangeFormats
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
