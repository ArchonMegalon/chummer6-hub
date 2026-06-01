using System.Text.Json;
using Chummer.Campaign.Contracts;

namespace Chummer.Run.Api.Services.Community;

public sealed class GmSessionVideoFoundryStore
{
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public GmSessionVideoFoundryStore(IConfiguration configuration)
    {
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public Dictionary<string, FaceAssetProjection> FacesById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PromptDraftProjection> PromptDraftsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<PromptVersionProjection> PromptVersions { get; } = new();
    public Dictionary<string, SessionVideoRenderJobProjection> JobsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<RenderUsageLedgerEntryProjection> UsageLedger { get; } = new();
    public List<TablePulseMediaPacketProjection> TablePulsePackets { get; } = new();

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        var snapshot = new Snapshot(
            FacesById.Values.OrderBy(static item => item.Id, StringComparer.OrdinalIgnoreCase).ToArray(),
            PromptDraftsById.Values.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            PromptVersions.OrderBy(static item => item.PromptDraftId, StringComparer.OrdinalIgnoreCase).ThenBy(static item => item.VersionNumber).ToArray(),
            JobsById.Values.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            UsageLedger.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            TablePulsePackets.ToArray());
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

            Snapshot? snapshot = JsonSerializer.Deserialize<Snapshot>(File.ReadAllText(_storagePath), _jsonOptions);
            if (snapshot is null)
            {
                return;
            }

            FacesById.Clear();
            PromptDraftsById.Clear();
            PromptVersions.Clear();
            JobsById.Clear();
            UsageLedger.Clear();
            TablePulsePackets.Clear();

            foreach (FaceAssetProjection face in snapshot.Faces ?? Array.Empty<FaceAssetProjection>())
            {
                FacesById[face.Id] = face;
            }

            foreach (PromptDraftProjection draft in snapshot.PromptDrafts ?? Array.Empty<PromptDraftProjection>())
            {
                PromptDraftsById[draft.Id] = draft;
            }

            PromptVersions.AddRange(snapshot.PromptVersions ?? Array.Empty<PromptVersionProjection>());
            foreach (SessionVideoRenderJobProjection job in snapshot.Jobs ?? Array.Empty<SessionVideoRenderJobProjection>())
            {
                JobsById[job.Id] = job;
            }

            UsageLedger.AddRange(snapshot.UsageLedger ?? Array.Empty<RenderUsageLedgerEntryProjection>());
            TablePulsePackets.AddRange(snapshot.TablePulsePackets ?? Array.Empty<TablePulseMediaPacketProjection>());
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string configured =
            configuration["CHUMMER_GM_SESSION_VIDEO_FOUNDRY_STORE_PATH"]
            ?? configuration["Community:GmSessionVideoFoundryStorePath"]
            ?? Path.Combine(AppContext.BaseDirectory, "App_Data", "gm-session-video-foundry.json");
        return Path.GetFullPath(configured);
    }

    private sealed record Snapshot(
        IReadOnlyList<FaceAssetProjection>? Faces = null,
        IReadOnlyList<PromptDraftProjection>? PromptDrafts = null,
        IReadOnlyList<PromptVersionProjection>? PromptVersions = null,
        IReadOnlyList<SessionVideoRenderJobProjection>? Jobs = null,
        IReadOnlyList<RenderUsageLedgerEntryProjection>? UsageLedger = null,
        IReadOnlyList<TablePulseMediaPacketProjection>? TablePulsePackets = null);
}
