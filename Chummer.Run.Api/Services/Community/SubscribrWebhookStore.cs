using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class SubscribrWebhookStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public SubscribrWebhookStore(IConfiguration configuration)
    {
        StoragePath = ResolveStoragePath(configuration);
        ReceiptRoot = ResolveReceiptRoot(configuration, StoragePath);
        Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
        Directory.CreateDirectory(ReceiptRoot);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath { get; }
    public string ReceiptRoot { get; }
    internal List<SubscribrWebhookLedgerEntry> Entries { get; } = new();

    public void PersistLocked()
    {
        var snapshot = new SubscribrWebhookStoreSnapshot(
            Entries
                .OrderByDescending(static entry => entry.ProcessedAtUtc)
                .ThenBy(static entry => entry.EventId, StringComparer.OrdinalIgnoreCase)
                .ToArray());
        string tempPath = $"{StoragePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), Encoding.UTF8);
        File.Move(tempPath, StoragePath, overwrite: true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(StoragePath))
            {
                return;
            }

            string json = File.ReadAllText(StoragePath, Encoding.UTF8);
            if (string.IsNullOrWhiteSpace(json))
            {
                return;
            }

            var snapshot = JsonSerializer.Deserialize<SubscribrWebhookStoreSnapshot>(json, _jsonOptions);
            Entries.Clear();
            Entries.AddRange(snapshot?.Entries ?? []);
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_SUBSCRIBR_WEBHOOK_STORE_PATH"]
            ?? configuration["Subscribr:WebhookStorePath"];
        return string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(Path.GetTempPath(), "chummer6-hub", "subscribr-webhook-store.json")
            : Path.GetFullPath(configured.Trim());
    }

    private static string ResolveReceiptRoot(IConfiguration configuration, string storagePath)
    {
        string? configured = configuration["CHUMMER_SUBSCRIBR_WEBHOOK_RECEIPT_ROOT"]
            ?? configuration["Subscribr:WebhookReceiptRoot"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured.Trim());
        }

        string directory = Path.GetDirectoryName(storagePath) ?? Path.GetTempPath();
        return Path.Combine(directory, "subscribr-webhook-receipts");
    }
}

internal sealed record SubscribrWebhookStoreSnapshot(
    IReadOnlyList<SubscribrWebhookLedgerEntry>? Entries);

internal sealed record SubscribrWebhookLedgerEntry(
    string EventId,
    string EventType,
    string Status,
    string SignatureStatus,
    string ReplayStatus,
    string ValidationStatus,
    string? PacketId,
    string? ReceiptPath,
    string? RejectionReason,
    DateTimeOffset ProcessedAtUtc);
