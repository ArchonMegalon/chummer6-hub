using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services;

public sealed class PublicParticipateSnapshotStore
{
    private readonly ILogger<PublicParticipateSnapshotStore> _logger;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public PublicParticipateSnapshotStore(
        IConfiguration configuration,
        ILogger<PublicParticipateSnapshotStore>? logger = null)
    {
        _logger = logger ?? NullLogger<PublicParticipateSnapshotStore>.Instance;
        StoragePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();

    public string StoragePath { get; }

    public PublicParticipateSnapshot Snapshot { get; private set; } = PublicParticipateSnapshot.Empty;

    public void PersistLocked(PublicParticipateSnapshot snapshot)
    {
        Snapshot = snapshot;
        Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);

        var persistedSnapshot = new PublicParticipateSnapshotStoreSnapshot(
            snapshot.TotalCount,
            snapshot.SyncedAtUtc,
            snapshot.Posts
                .Select(static item => new PublicParticipatePostSnapshotStoreItem(
                    item.CanonicalHref,
                    item.Post.Id,
                    item.Post.Title,
                    item.Post.Summary,
                    item.Post.Score,
                    item.Post.CommentCount,
                    item.Post.Status,
                    item.Post.Category,
                    item.Post.UpdatedLabel,
                    item.Post.Href,
                    item.BodyParagraphs))
                .ToArray());

        string tempPath = $"{StoragePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(persistedSnapshot, _jsonOptions), Encoding.UTF8);
        File.Move(tempPath, StoragePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(StoragePath))
            {
                _logger.LogInformation("PublicParticipateSnapshotStore starting empty at {StoragePath}.", StoragePath);
                return;
            }

            try
            {
                string storeJson = File.ReadAllText(StoragePath, Encoding.UTF8);
                if (string.IsNullOrWhiteSpace(storeJson))
                {
                    _logger.LogInformation("PublicParticipateSnapshotStore loaded an empty durable state from {StoragePath}.", StoragePath);
                    return;
                }

                PublicParticipateSnapshotStoreSnapshot? persistedSnapshot = JsonSerializer.Deserialize<PublicParticipateSnapshotStoreSnapshot>(
                    storeJson,
                    _jsonOptions);
                Snapshot = persistedSnapshot is null
                    ? PublicParticipateSnapshot.Empty
                    : new PublicParticipateSnapshot(
                        persistedSnapshot.Posts?
                            .Select(static item => new PublicParticipatePostSnapshot(
                                item.CanonicalHref,
                                new ViewModels.FirstPartyParticipatePostViewModel(
                                    item.Id,
                                    item.Title,
                                    item.Summary,
                                    item.Score,
                                    item.CommentCount,
                                    item.Status,
                                    item.Category,
                                    item.UpdatedLabel,
                                    item.Href),
                                item.BodyParagraphs ?? Array.Empty<string>()))
                            .ToArray() ?? Array.Empty<PublicParticipatePostSnapshot>(),
                        Math.Max(0, persistedSnapshot.TotalCount),
                        persistedSnapshot.SyncedAtUtc);

                _logger.LogInformation(
                    "PublicParticipateSnapshotStore loaded {PostCount} participate posts from {StoragePath}.",
                    Snapshot.Posts.Count,
                    StoragePath);
            }
            catch (JsonException ex)
            {
                Snapshot = PublicParticipateSnapshot.Empty;
                QuarantineCorruptStoreFile();
                _logger.LogWarning(ex, "PublicParticipateSnapshotStore quarantined corrupt durable state at {StoragePath}.", StoragePath);
            }
        }
    }

    private void QuarantineCorruptStoreFile()
    {
        string quarantinePath = $"{StoragePath}.corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}";
        try
        {
            File.Move(StoragePath, quarantinePath);
        }
        catch
        {
            // Starting empty is safer than crashing on unreadable local state.
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_PUBLIC_PARTICIPATE_SNAPSHOT_STORE_PATH"]
            ?? configuration["Participate:SnapshotStorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "public-participate-snapshot.json");
    }
}

internal sealed record PublicParticipateSnapshotStoreSnapshot(
    int TotalCount,
    DateTimeOffset SyncedAtUtc,
    IReadOnlyList<PublicParticipatePostSnapshotStoreItem>? Posts);

internal sealed record PublicParticipatePostSnapshotStoreItem(
    string CanonicalHref,
    string Id,
    string Title,
    string Summary,
    int Score,
    int CommentCount,
    string Status,
    string Category,
    string UpdatedLabel,
    string? Href,
    IReadOnlyList<string>? BodyParagraphs);
