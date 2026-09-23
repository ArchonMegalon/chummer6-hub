using System.Text;
using System.Text.Json;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactRequestReceiptStore : IDisposable
{
    private readonly TeableQuotaLedger<HorizonArtifactRequestReceipt> _ledger;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly string _storePath;

    public HorizonArtifactRequestReceiptStore(IConfiguration configuration, TeableRevisionStore? primary = null, bool ownsPrimary = false)
    {
        string mode = configuration["CHUMMER_HORIZON_REQUEST_RECEIPT_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (primary is not null))
            throw new InvalidOperationException("Artifact receipts require an explicit matching primary configuration.");
        _ledger = new(primary, ownsPrimary, "horizon-request-receipts", "chummer.hub.horizon-request-receipts-primary/v1", ValidatePrimary);
        _storePath = primary is null ? ResolveStorePath(configuration) : string.Empty;
        if (primary is null)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_storePath)!);
            Load();
        }
    }

    internal object Gate => _ledger.Gate;

    internal List<HorizonArtifactRequestReceipt> Receipts => _ledger.Entries;
    public void Dispose() => _ledger.Dispose();
    internal void EnsureAccountErasureSupported() => _ledger.EnsureAccountErasureSupported();

    public IReadOnlyList<HorizonArtifactRequestReceipt> ListRecent(
        string? horizonId = null,
        string? userId = null,
        string? artifactKindOrCapabilityId = null,
        int limit = 50)
    {
        string normalizedHorizon = Clean(horizonId);
        string normalizedUser = Clean(userId);
        string normalizedSelector = Clean(artifactKindOrCapabilityId);
        int boundedLimit = Math.Clamp(limit, 1, 200);
        using (_ledger.Enter())
        {
            return Receipts
                .Where(receipt => string.IsNullOrWhiteSpace(normalizedHorizon)
                    || string.Equals(receipt.HorizonId, normalizedHorizon, StringComparison.OrdinalIgnoreCase))
                .Where(receipt => string.IsNullOrWhiteSpace(normalizedUser)
                    || string.Equals(receipt.RequestedByUserId, normalizedUser, StringComparison.OrdinalIgnoreCase))
                .Where(receipt => string.IsNullOrWhiteSpace(normalizedSelector)
                    || string.Equals(receipt.ArtifactKind, normalizedSelector, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(receipt.CapabilityId, normalizedSelector, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(receipt => receipt.CreatedAtUtc)
                .ThenBy(receipt => receipt.RequestId, StringComparer.OrdinalIgnoreCase)
                .Take(boundedLimit)
                .ToArray();
        }
    }

    public HorizonArtifactRequestReceipt? FindByRequestId(string requestId)
    {
        string normalizedRequestId = Clean(requestId);
        if (string.IsNullOrWhiteSpace(normalizedRequestId))
        {
            return null;
        }

        using (_ledger.Enter())
        {
            return Receipts.FirstOrDefault(receipt =>
                string.Equals(receipt.RequestId, normalizedRequestId, StringComparison.OrdinalIgnoreCase));
        }
    }

    public void Append(HorizonArtifactRequestReceipt receipt)
    {
        ArgumentNullException.ThrowIfNull(receipt);
        using (_ledger.Enter())
        {
            var before = Receipts.ToArray();
            Receipts.RemoveAll(existing => string.Equals(existing.RequestId, receipt.RequestId, StringComparison.OrdinalIgnoreCase));
            Receipts.Add(receipt);
            try { PersistLocked(); }
            catch { Receipts.Clear(); Receipts.AddRange(before); throw; }
        }
    }

    private static void ValidatePrimary(IReadOnlyList<HorizonArtifactRequestReceipt> receipts)
    {
        var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in receipts)
        {
            if (row is null || !ids.Add(row.RequestId)
                || new[] { row.RequestId, row.HorizonId, row.CapabilityId, row.ArtifactKind, row.PublicLabel, row.CapabilitySlot }
                    .Any(string.IsNullOrWhiteSpace)
                || row.SourceRef is null || row.RequestedByUserId is null || row.Visibility is null
                || row.SourceRef != row.SourceRef.Trim() || row.RequestedByUserId != row.RequestedByUserId.Trim()
                || row.CreatedAtUtc == default || row.CreatedAtUtc.Offset != TimeSpan.Zero
                || row.BlockedReasons is null || row.BlockedReasons.Any(string.IsNullOrWhiteSpace)
                || row.Status is not ("accepted" or "blocked")
                || (row.Status == "blocked") != (row.BlockedReasons.Count > 0)
                || row.RequestId != HorizonArtifactRequestService.BuildRequestId(row.HorizonId, row.CapabilityId,
                    row.RequestedByUserId, row.SourceRef, row.CreatedAtUtc))
                throw new InvalidDataException("Primary artifact receipt identity or status is invalid.");
            if (row.Status == "accepted" && (!row.ExternalProcessingConsent
                || !row.SourceRef.StartsWith(row.HorizonId + ":", StringComparison.OrdinalIgnoreCase)
                || !new[] { "private", "campaign_safe", "public_safe" }.Contains(row.Visibility, StringComparer.OrdinalIgnoreCase)))
                throw new InvalidDataException("Primary artifact receipt consent or source is invalid.");
            if (row.Quota is { } quota && (!row.QuotaTracked
                || !string.Equals(quota.UserId, row.RequestedByUserId, StringComparison.OrdinalIgnoreCase)
                || quota.HorizonId != row.HorizonId || quota.CapabilityId != row.CapabilityId || quota.ArtifactKind != row.ArtifactKind
                || quota.WindowLimit < 0 || quota.WindowUsed < 0
                || quota.WindowRemaining != Math.Max(0, quota.WindowLimit - quota.WindowUsed)
                || quota.WindowStartUtc == default || quota.WindowEndUtc <= quota.WindowStartUtc))
                throw new InvalidDataException("Primary artifact receipt allowance is inconsistent.");
            if (row.GovernedRenderRequest is { } render && (render.HorizonId != row.HorizonId || render.CapabilityId != row.CapabilityId
                || render.ArtifactKind != row.ArtifactKind || render.CapabilitySlot != row.CapabilitySlot || render.SourceRef != row.SourceRef
                || render.ContractName != HorizonGovernedRenderRequestComposerService.ContractName
                || render.ContractVersion != HorizonGovernedRenderRequestComposerService.ContractVersion
                || render.OrchestrationLane != HorizonGovernedRenderRequestComposerService.OrchestrationLane
                || render.TruthRefs is null || render.EvidenceRefs is null || render.Artifacts is null))
                throw new InvalidDataException("Primary artifact receipt render binding is inconsistent.");
        }
    }

    private void Load()
    {
        if (!File.Exists(_storePath))
        {
            return;
        }

        string json = File.ReadAllText(_storePath, Encoding.UTF8);
        if (string.IsNullOrWhiteSpace(json))
        {
            return;
        }

        var snapshot = JsonSerializer.Deserialize<HorizonArtifactRequestReceiptStoreSnapshot>(json, _jsonOptions);
        if (snapshot?.Receipts is { Count: > 0 })
        {
            Receipts.AddRange(snapshot.Receipts.Where(static receipt => receipt is not null)!);
        }
    }

    internal void PersistLocked()
    {
        if (_ledger.IsPrimary) { _ledger.Persist(); return; }
        var snapshot = new HorizonArtifactRequestReceiptStoreSnapshot(
            Receipts
                .OrderByDescending(static receipt => receipt.CreatedAtUtc)
                .ThenBy(static receipt => receipt.RequestId, StringComparer.OrdinalIgnoreCase)
                .ToArray());
        string tempPath = $"{_storePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), Encoding.UTF8);
        File.Move(tempPath, _storePath, overwrite: true);
    }

    private static string ResolveStorePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_HORIZON_ARTIFACT_REQUEST_RECEIPT_STORE_PATH"]
            ?? configuration["HorizonArtifacts:RequestReceiptStorePath"];
        return string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(Path.GetTempPath(), "chummer6-hub", "horizon-artifact-request-receipts.json")
            : Path.GetFullPath(configured.Trim());
    }

    private static string Clean(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();
}

internal sealed record HorizonArtifactRequestReceiptStoreSnapshot(
    IReadOnlyList<HorizonArtifactRequestReceipt>? Receipts);
