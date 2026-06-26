using System.Text.Json;
using Chummer.Contracts.Receipts;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Chummer.Run.Api.Services;

public sealed class PublicConciergeStore
{
    private readonly ILogger<PublicConciergeStore> _logger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public PublicConciergeStore(IConfiguration configuration, ILogger<PublicConciergeStore> logger)
    {
        _logger = logger;
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath => _storagePath;
    public Dictionary<string, PublicConciergeBranchReceipt> BranchReceiptsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PublicConciergeWebhookReceipt> WebhookReceiptsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PublicConciergeModerationItem> ModerationItemsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> WebhookReceiptIdByDedupKey { get; } = new(StringComparer.OrdinalIgnoreCase);

    public void PersistLocked()
    {
        PublicConciergeStoreSnapshot snapshot = new(
            BranchReceipts: BranchReceiptsById.Values
                .OrderByDescending(static item => item.RecordedAtUtc)
                .ToArray(),
            WebhookReceipts: WebhookReceiptsById.Values
                .OrderByDescending(static item => item.ReceivedAtUtc)
                .ToArray(),
            ModerationItems: ModerationItemsById.Values
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            WebhookReceiptIdByDedupKey: WebhookReceiptIdByDedupKey);

        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), System.Text.Encoding.UTF8);
        File.Move(tempPath, _storagePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(_storagePath))
            {
                _logger.LogInformation("PublicConciergeStore starting with an empty durable state at {StoragePath}.", _storagePath);
                return;
            }

            try
            {
                string snapshotJson = File.ReadAllText(_storagePath, System.Text.Encoding.UTF8);
                PublicConciergeStoreSnapshot snapshot = JsonSerializer.Deserialize<PublicConciergeStoreSnapshot>(snapshotJson, _jsonOptions)
                    ?? throw new InvalidOperationException($"Unable to deserialize public concierge store snapshot: {_storagePath}");
                ApplySnapshotLocked(snapshot);
                _logger.LogInformation(
                    "PublicConciergeStore loaded {BranchReceiptCount} branch receipts, {WebhookReceiptCount} webhook receipts, and {ModerationItemCount} moderation items from {StoragePath}.",
                    BranchReceiptsById.Count,
                    WebhookReceiptsById.Count,
                    ModerationItemsById.Count,
                    _storagePath);
            }
            catch (JsonException ex)
            {
                ApplySnapshotLocked(new PublicConciergeStoreSnapshot(null, null, null, null));
                QuarantineCorruptStoreFile();
                _logger.LogWarning(ex, "PublicConciergeStore quarantined corrupt durable state at {StoragePath} and restarted empty.", _storagePath);
            }
        }
    }

    private void QuarantineCorruptStoreFile()
    {
        string quarantinePath = $"{_storagePath}.corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}";
        try
        {
            File.Move(_storagePath, quarantinePath);
        }
        catch
        {
            // Starting empty is safer than crashing when a local concierge store file is unreadable.
        }
    }

    private void ApplySnapshotLocked(PublicConciergeStoreSnapshot snapshot)
    {
        BranchReceiptsById.Clear();
        WebhookReceiptsById.Clear();
        ModerationItemsById.Clear();
        WebhookReceiptIdByDedupKey.Clear();

        foreach (PublicConciergeBranchReceipt receipt in snapshot.BranchReceipts ?? Array.Empty<PublicConciergeBranchReceipt>())
        {
            BranchReceiptsById[receipt.ReceiptId] = receipt;
        }

        foreach (PublicConciergeWebhookReceipt receipt in snapshot.WebhookReceipts ?? Array.Empty<PublicConciergeWebhookReceipt>())
        {
            WebhookReceiptsById[receipt.ReceiptId] = receipt;
        }

        foreach (PublicConciergeModerationItem item in snapshot.ModerationItems ?? Array.Empty<PublicConciergeModerationItem>())
        {
            ModerationItemsById[item.ItemId] = item;
        }

        foreach ((string key, string value) in snapshot.WebhookReceiptIdByDedupKey ?? new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase))
        {
            WebhookReceiptIdByDedupKey[key] = value;
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_PUBLIC_CONCIERGE_STORE_PATH"] ?? configuration["PublicConcierge:StorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "public-concierge-store.json");
    }
}

public sealed record PublicConciergeBranchReceipt(
    string ReceiptId,
    string SurfaceKey,
    string FlowId,
    string BranchId,
    string EntrySurface,
    string Locale,
    string CorrelationId,
    string TargetHref,
    string TargetKind,
    DateTimeOffset RecordedAtUtc,
    ReceiptEnvelope? Envelope = null);

public sealed record PublicConciergeWebhookReceipt(
    string ReceiptId,
    string ProviderKey,
    string FlowId,
    string? BranchId,
    string CorrelationId,
    string Locale,
    string EventType,
    string Status,
    string VerificationState,
    string? ProviderReceiptId,
    string Summary,
    string? FirstPartyCaseId,
    string? BookingId,
    string? AssetRef,
    string? PublicationRef,
    string? MediaKind,
    DateTimeOffset ReceivedAtUtc,
    IReadOnlyDictionary<string, string>? Metadata,
    ReceiptEnvelope? Envelope = null);

public sealed record PublicConciergeModerationItem(
    string ItemId,
    string SourceReceiptId,
    string CorrelationId,
    string Status,
    string MediaKind,
    string Summary,
    string? AssetRef,
    string? PublicationRef,
    DateTimeOffset CreatedAtUtc);

internal sealed record PublicConciergeStoreSnapshot(
    IReadOnlyList<PublicConciergeBranchReceipt>? BranchReceipts,
    IReadOnlyList<PublicConciergeWebhookReceipt>? WebhookReceipts,
    IReadOnlyList<PublicConciergeModerationItem>? ModerationItems,
    IReadOnlyDictionary<string, string>? WebhookReceiptIdByDedupKey);
