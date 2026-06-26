using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactRequestReceiptStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly string _storePath;

    public HorizonArtifactRequestReceiptStore(IConfiguration configuration)
    {
        _storePath = ResolveStorePath(configuration);
        Directory.CreateDirectory(Path.GetDirectoryName(_storePath)!);
        Load();
    }

    internal object Gate { get; } = new();

    internal List<HorizonArtifactRequestReceipt> Receipts { get; } = new();

    public IReadOnlyList<HorizonArtifactRequestReceipt> ListRecent(
        string? horizonId = null,
        string? userId = null,
        int limit = 50)
    {
        string normalizedHorizon = Clean(horizonId);
        string normalizedUser = Clean(userId);
        int boundedLimit = Math.Clamp(limit, 1, 200);
        lock (Gate)
        {
            return Receipts
                .Where(receipt => string.IsNullOrWhiteSpace(normalizedHorizon)
                    || string.Equals(receipt.HorizonId, normalizedHorizon, StringComparison.OrdinalIgnoreCase))
                .Where(receipt => string.IsNullOrWhiteSpace(normalizedUser)
                    || string.Equals(receipt.RequestedByUserId, normalizedUser, StringComparison.OrdinalIgnoreCase))
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

        lock (Gate)
        {
            return Receipts.FirstOrDefault(receipt =>
                string.Equals(receipt.RequestId, normalizedRequestId, StringComparison.OrdinalIgnoreCase));
        }
    }

    public void Append(HorizonArtifactRequestReceipt receipt)
    {
        ArgumentNullException.ThrowIfNull(receipt);
        lock (Gate)
        {
            Receipts.RemoveAll(existing => string.Equals(existing.RequestId, receipt.RequestId, StringComparison.OrdinalIgnoreCase));
            Receipts.Add(receipt);
            PersistLocked();
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
