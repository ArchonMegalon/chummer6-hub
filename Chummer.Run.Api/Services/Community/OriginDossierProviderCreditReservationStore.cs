using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class OriginDossierProviderCreditReservationStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public OriginDossierProviderCreditReservationStore(IConfiguration configuration)
    {
        StoragePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath { get; }
    internal List<OriginDossierProviderCreditReservationLedgerEntry> Entries { get; } = new();

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
        var snapshot = new OriginDossierProviderCreditReservationStoreSnapshot(
            Entries
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ThenBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                .ToArray());
        string tempPath = $"{StoragePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), Encoding.UTF8);
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

            string storeJson = File.ReadAllText(StoragePath, Encoding.UTF8);
            if (string.IsNullOrWhiteSpace(storeJson))
            {
                return;
            }

            var snapshot = JsonSerializer.Deserialize<OriginDossierProviderCreditReservationStoreSnapshot>(storeJson, _jsonOptions);
            Entries.Clear();
            Entries.AddRange(snapshot?.Entries ?? []);
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORE_PATH"]
            ?? configuration["OriginDossier:ProviderReservationStorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "origin-provider-credit-reservations.json");
    }
}

internal sealed record OriginDossierProviderCreditReservationStoreSnapshot(
    IReadOnlyList<OriginDossierProviderCreditReservationLedgerEntry>? Entries);

internal sealed record OriginDossierProviderCreditReservationLedgerEntry(
    string ReservationId,
    string UserId,
    string ProjectId,
    string Provider,
    string ProviderAccountAlias,
    int CreditsReserved,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);
