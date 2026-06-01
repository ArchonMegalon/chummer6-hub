using System.Text.Json;
using Chummer.Campaign.Contracts;

namespace Chummer.Run.Api.Services.Community;

public sealed class PromptFoundryStore
{
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public PromptFoundryStore(IConfiguration configuration)
    {
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public Dictionary<string, PromptTemplateProjection> TemplatesById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PromptFoundryDraftProjection> DraftsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<PromptFoundryVersionProjection> Versions { get; } = new();
    public List<PromptUsageLedgerEntryProjection> UsageLedger { get; } = new();

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        Snapshot snapshot = new(
            TemplatesById.Values.OrderBy(static item => item.Id, StringComparer.OrdinalIgnoreCase).ToArray(),
            DraftsById.Values.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            Versions.OrderBy(static item => item.PromptDraftId, StringComparer.OrdinalIgnoreCase).ThenBy(static item => item.VersionNumber).ToArray(),
            UsageLedger.OrderByDescending(static item => item.CreatedAtUtc).ToArray());
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

            TemplatesById.Clear();
            DraftsById.Clear();
            Versions.Clear();
            UsageLedger.Clear();

            foreach (PromptTemplateProjection template in snapshot.Templates ?? Array.Empty<PromptTemplateProjection>())
            {
                TemplatesById[template.Id] = template;
            }

            foreach (PromptFoundryDraftProjection draft in snapshot.Drafts ?? Array.Empty<PromptFoundryDraftProjection>())
            {
                DraftsById[draft.Id] = draft;
            }

            Versions.AddRange(snapshot.Versions ?? Array.Empty<PromptFoundryVersionProjection>());
            UsageLedger.AddRange(snapshot.UsageLedger ?? Array.Empty<PromptUsageLedgerEntryProjection>());
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string configured =
            configuration["CHUMMER_PROMPT_FOUNDRY_STORE_PATH"]
            ?? configuration["Community:PromptFoundryStorePath"]
            ?? Path.Combine(AppContext.BaseDirectory, "App_Data", "prompt-foundry.json");
        return Path.GetFullPath(configured);
    }

    private sealed record Snapshot(
        IReadOnlyList<PromptTemplateProjection>? Templates = null,
        IReadOnlyList<PromptFoundryDraftProjection>? Drafts = null,
        IReadOnlyList<PromptFoundryVersionProjection>? Versions = null,
        IReadOnlyList<PromptUsageLedgerEntryProjection>? UsageLedger = null);
}
