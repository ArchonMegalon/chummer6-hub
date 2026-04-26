using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Chummer.Run.Api.Services.KarmaForge;

public sealed class KarmaForgeStore
{
    private readonly ILogger<KarmaForgeStore> _logger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public KarmaForgeStore(IConfiguration configuration, ILogger<KarmaForgeStore> logger)
    {
        _logger = logger;
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();

    public string StoragePath => _storagePath;

    public Dictionary<string, KarmaForgeSubmissionProjection> SubmissionsById { get; } = new(StringComparer.OrdinalIgnoreCase);

    public void PersistLocked()
    {
        KarmaForgeStoreSnapshot snapshot = new(
            Submissions: SubmissionsById.Values
                .OrderByDescending(static item => item.SubmittedAtUtc)
                .ToArray());

        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(_storagePath))
            {
                _logger.LogInformation("KarmaForgeStore starting with an empty durable state at {StoragePath}.", _storagePath);
                return;
            }

            string snapshotJson = File.ReadAllText(_storagePath);
            KarmaForgeStoreSnapshot snapshot = JsonSerializer.Deserialize<KarmaForgeStoreSnapshot>(snapshotJson, _jsonOptions)
                ?? throw new InvalidOperationException($"Unable to deserialize KARMA FORGE store snapshot: {_storagePath}");
            ApplySnapshotLocked(snapshot);
            _logger.LogInformation(
                "KarmaForgeStore loaded {SubmissionCount} submissions from {StoragePath}.",
                SubmissionsById.Count,
                _storagePath);
        }
    }

    private void ApplySnapshotLocked(KarmaForgeStoreSnapshot snapshot)
    {
        SubmissionsById.Clear();
        foreach (KarmaForgeSubmissionProjection submission in snapshot.Submissions ?? Array.Empty<KarmaForgeSubmissionProjection>())
        {
            SubmissionsById[submission.SubmissionId] = submission;
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_KARMA_FORGE_STORE_PATH"] ?? configuration["KarmaForge:StorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "karma-forge-store.json");
    }
}

internal sealed record KarmaForgeStoreSnapshot(
    IReadOnlyList<KarmaForgeSubmissionProjection>? Submissions);
