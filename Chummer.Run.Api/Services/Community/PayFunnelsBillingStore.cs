using System.Text.Json;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class PayFunnelsBillingStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public PayFunnelsBillingStore(IConfiguration configuration)
    {
        StoragePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath { get; }
    public List<PaymentIntentDto> Intents { get; } = new();
    public List<PaymentEventDto> Events { get; } = new();
    public List<PaymentReceiptDto> Receipts { get; } = new();
    public List<BillingEntitlementLedgerEntryDto> EntitlementLedger { get; } = new();

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
        var tempPath = $"{StoragePath}.tmp";
        var snapshot = new PayFunnelsBillingStoreSnapshot(
            Intents.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            Events.OrderByDescending(static item => item.ProcessedAtUtc).ToArray(),
            Receipts.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            EntitlementLedger.OrderByDescending(static item => item.CreatedAtUtc).ToArray());
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, StoragePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(StoragePath))
            {
                return;
            }

            var snapshot = JsonSerializer.Deserialize<PayFunnelsBillingStoreSnapshot>(File.ReadAllText(StoragePath), _jsonOptions)
                ?? new PayFunnelsBillingStoreSnapshot([], [], [], []);
            Intents.Clear();
            Events.Clear();
            Receipts.Clear();
            EntitlementLedger.Clear();
            Intents.AddRange(snapshot.Intents ?? []);
            Events.AddRange(snapshot.Events ?? []);
            Receipts.AddRange(snapshot.Receipts ?? []);
            EntitlementLedger.AddRange(snapshot.EntitlementLedger ?? []);
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        var configured = configuration["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] ?? configuration["PayFunnels:BillingStorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "payfunnels-billing-store.json");
    }
}

internal sealed record PayFunnelsBillingStoreSnapshot(
    IReadOnlyList<PaymentIntentDto>? Intents,
    IReadOnlyList<PaymentEventDto>? Events,
    IReadOnlyList<PaymentReceiptDto>? Receipts,
    IReadOnlyList<BillingEntitlementLedgerEntryDto>? EntitlementLedger);
