using System.Text.Json;
using Chummer.Campaign.Contracts;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class GmSessionVenueStore
{
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public GmSessionVenueStore(IConfiguration configuration)
    {
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public Dictionary<string, GmSessionVenueProjection> VenuesBySessionKey { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<VenueLinkReceiptProjection> VenueLinkReceipts { get; } = new();
    public List<VenueCreatedReceiptProjection> VenueCreatedReceipts { get; } = new();
    public List<SessionVenueCloseoutReceiptProjection> CloseoutReceipts { get; } = new();
    public List<NonverbiaDebriefReceiptProjection> NonverbiaDebriefReceipts { get; } = new();

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        var snapshot = new GmSessionVenueStoreSnapshot(
            VenuesBySessionKey.Values.OrderBy(static item => item.UpdatedAtUtc).ToArray(),
            VenueLinkReceipts.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            VenueCreatedReceipts.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            CloseoutReceipts.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            NonverbiaDebriefReceipts.OrderByDescending(static item => item.CreatedAtUtc).ToArray());
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(_storagePath))
            {
                return;
            }

            GmSessionVenueStoreSnapshot? snapshot = JsonSerializer.Deserialize<GmSessionVenueStoreSnapshot>(
                File.ReadAllText(_storagePath),
                _jsonOptions);
            if (snapshot is null)
            {
                return;
            }

            VenuesBySessionKey.Clear();
            VenueLinkReceipts.Clear();
            VenueCreatedReceipts.Clear();
            CloseoutReceipts.Clear();
            NonverbiaDebriefReceipts.Clear();

            foreach (GmSessionVenueProjection venue in snapshot.Venues ?? Array.Empty<GmSessionVenueProjection>())
            {
                VenuesBySessionKey[BuildSessionKey(venue.OwnerAccountId, venue.CampaignId, venue.SessionId)] = venue;
            }

            VenueLinkReceipts.AddRange(snapshot.VenueLinkReceipts ?? Array.Empty<VenueLinkReceiptProjection>());
            VenueCreatedReceipts.AddRange(snapshot.VenueCreatedReceipts ?? Array.Empty<VenueCreatedReceiptProjection>());
            CloseoutReceipts.AddRange(snapshot.CloseoutReceipts ?? Array.Empty<SessionVenueCloseoutReceiptProjection>());
            NonverbiaDebriefReceipts.AddRange(snapshot.NonverbiaDebriefReceipts ?? Array.Empty<NonverbiaDebriefReceiptProjection>());
        }
    }

    public static string BuildSessionKey(string ownerAccountId, string campaignId, string sessionId)
        => $"{ownerAccountId.Trim()}::{campaignId.Trim()}::{sessionId.Trim()}";

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string configured =
            configuration["CHUMMER_GM_SESSION_VENUE_STORE_PATH"]
            ?? configuration["Community:GmSessionVenueStorePath"]
            ?? Path.Combine(AppContext.BaseDirectory, "App_Data", "gm-session-venues.json");
        return Path.GetFullPath(configured);
    }

    private sealed record GmSessionVenueStoreSnapshot(
        IReadOnlyList<GmSessionVenueProjection>? Venues = null,
        IReadOnlyList<VenueLinkReceiptProjection>? VenueLinkReceipts = null,
        IReadOnlyList<VenueCreatedReceiptProjection>? VenueCreatedReceipts = null,
        IReadOnlyList<SessionVenueCloseoutReceiptProjection>? CloseoutReceipts = null,
        IReadOnlyList<NonverbiaDebriefReceiptProjection>? NonverbiaDebriefReceipts = null);
}
