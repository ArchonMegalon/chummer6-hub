using System.Text;
using System.Text.Json;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class OriginDossierProviderCreditReservationStore : IDisposable
{
    private readonly TeableQuotaLedger<OriginDossierProviderCreditReservationLedgerEntry> _ledger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public OriginDossierProviderCreditReservationStore(IConfiguration configuration,
        TeableRevisionStore? primary = null, bool ownsPrimary = false)
    {
        string mode = configuration["CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (primary is not null))
            throw new InvalidOperationException("Origin reservations require an explicit matching primary configuration.");
        _ledger = new(primary, ownsPrimary, "origin-credit-reservations", "chummer.hub.origin-credit-reservations-primary/v1", ValidatePrimary);
        _storagePath = primary is null ? ResolveStoragePath(configuration) : string.Empty;
        if (primary is null) Load();
    }

    public object Gate => _ledger.Gate;
    public string StoragePath => !_ledger.IsPrimary ? _storagePath
        : throw new InvalidOperationException("Primary Origin reservations have no authoritative local file.");
    internal List<OriginDossierProviderCreditReservationLedgerEntry> Entries => _ledger.Entries;
    public IDisposable Enter() => _ledger.Enter();
    public void Dispose() => _ledger.Dispose();
    internal void EnsureAccountErasureSupported() => _ledger.EnsureAccountErasureSupported();

    private static void ValidatePrimary(IReadOnlyList<OriginDossierProviderCreditReservationLedgerEntry> entries)
    {
        var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in entries)
        {
            if (entry is null || string.IsNullOrWhiteSpace(entry.ReservationId) || !ids.Add(entry.ReservationId)
                || string.IsNullOrWhiteSpace(entry.UserId) || entry.UserId != entry.UserId.Trim()
                || string.IsNullOrWhiteSpace(entry.ProjectId) || entry.ProjectId != entry.ProjectId.Trim()
                || string.IsNullOrWhiteSpace(entry.Provider) || entry.Provider != entry.Provider.Trim()
                || string.IsNullOrWhiteSpace(entry.ProviderAccountAlias) || entry.ProviderAccountAlias != entry.ProviderAccountAlias.Trim()
                || entry.ReservationId != OriginDossierProviderCreditReservationService.BuildReservationId(
                    entry.UserId, entry.ProjectId, entry.Provider, entry.ProviderAccountAlias)
                || entry.Status != "reserved" || entry.CreditsReserved <= 0
                || entry.CreatedAtUtc == default || entry.UpdatedAtUtc < entry.CreatedAtUtc)
                throw new InvalidDataException("Primary Origin credit reservation is invalid or ambiguous.");
        }
    }

    public void PersistLocked()
    {
        if (_ledger.IsPrimary) { _ledger.Persist(); return; }
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
