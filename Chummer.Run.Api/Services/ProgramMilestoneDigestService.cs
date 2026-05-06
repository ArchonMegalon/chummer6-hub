using Chummer.Run.Api.ViewModels;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class ProgramMilestoneDigestService
{
    private const string RegistryRelativePath = ".codex-design/product/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml";
    private readonly PublicCanonFileLoader _canon;
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .IgnoreUnmatchedProperties()
        .Build();

    public ProgramMilestoneDigestService(PublicCanonFileLoader canon)
    {
        _canon = canon;
    }

    public IReadOnlyList<ProgramMilestoneSummaryViewModel> BuildOpenMilestones()
    {
        var document = Deserializer.Deserialize<ProgramMilestoneRegistryDocument>(_canon.LoadRequiredText(RegistryRelativePath))
            ?? throw new InvalidOperationException($"canon file '{RegistryRelativePath}' could not be deserialized.");
        var milestones = document.Milestones ?? [];
        var milestoneById = milestones
            .Where(static milestone => milestone.Id > 0)
            .GroupBy(static milestone => milestone.Id)
            .ToDictionary(static group => group.Key, static group => group.First());

        var orderedIds = (document.ImplementationOrderMilestoneIds ?? [])
            .Where(milestoneById.ContainsKey)
            .ToList();

        foreach (var milestoneId in milestoneById.Keys.OrderBy(static id => id))
        {
            if (!orderedIds.Contains(milestoneId))
            {
                orderedIds.Add(milestoneId);
            }
        }

        return orderedIds
            .Select(id => milestoneById[id])
            .Where(static milestone => !string.Equals(milestone.Status, "complete", StringComparison.OrdinalIgnoreCase))
            .Select(milestone => BuildSummary(milestone, milestoneById))
            .ToArray();
    }

    private static ProgramMilestoneSummaryViewModel BuildSummary(
        ProgramMilestoneRecord milestone,
        IReadOnlyDictionary<int, ProgramMilestoneRecord> milestoneById)
    {
        var owners = milestone.Owners ?? [];
        var dependencies = (milestone.Dependencies ?? [])
            .Where(milestoneById.ContainsKey)
            .Select(id =>
            {
                var dependency = milestoneById[id];
                return new ProgramMilestoneDependencyViewModel(
                    Id: id.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    Title: dependency.Title ?? $"Milestone {id}",
                    StatusLabel: HumanizeStatus(dependency.Status));
            })
            .ToArray();
        var workTasks = milestone.WorkTasks ?? [];
        var claimedTaskCount = workTasks.Count(static task => IsClaimedTaskStatus(task.Status));
        var claimed = !string.Equals(milestone.Status, "not_started", StringComparison.OrdinalIgnoreCase) || claimedTaskCount > 0;
        var difficulty = DescribeDifficulty(owners.Count, dependencies.Length, workTasks.Count);
        var claimedSummary = DescribeClaimedState(milestone.Status, workTasks.Count, claimedTaskCount);

        return new ProgramMilestoneSummaryViewModel(
            Id: milestone.Id.ToString(System.Globalization.CultureInfo.InvariantCulture),
            Title: milestone.Title ?? $"Milestone {milestone.Id}",
            WaveLabel: string.IsNullOrWhiteSpace(milestone.Wave) ? "Program" : milestone.Wave!,
            StatusKey: NormalizeKey(milestone.Status),
            StatusLabel: HumanizeStatus(milestone.Status),
            CasualSummary: BuildCasualSummary(milestone),
            DifficultyLabel: difficulty.Label,
            DifficultySummary: difficulty.Summary,
            Claimed: claimed,
            ClaimedLabel: claimed ? "Claimed" : "Unclaimed",
            ClaimedSummary: claimedSummary,
            DependencySummary: DescribeDependencies(dependencies),
            Dependencies: dependencies);
    }

    private static string BuildCasualSummary(ProgramMilestoneRecord milestone)
    {
        var baseText = (milestone.ExitCriteria ?? [])
            .FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item))
            ?? milestone.Title
            ?? "This milestone is waiting for a clearer public summary.";
        var simplified = SimplifyCasualSummary(baseText);
        var prefix = NormalizeKey(milestone.Status) switch
        {
            "in_progress" => "Already moving: ",
            "not_started" => "Next up: ",
            "blocked" => "Blocked right now: ",
            _ => string.Empty
        };

        return EnsureSentence($"{prefix}{simplified}".Trim());
    }

    private static string SimplifyCasualSummary(string value)
    {
        var simplified = value
            .Replace("can emit", "can create", StringComparison.OrdinalIgnoreCase)
            .Replace("can launch", "can open", StringComparison.OrdinalIgnoreCase)
            .Replace("locale-matched", "localized", StringComparison.OrdinalIgnoreCase)
            .Replace("governed ", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("promoted surfaces", "main screens", StringComparison.OrdinalIgnoreCase)
            .Replace("truth", "state", StringComparison.OrdinalIgnoreCase)
            .Replace("followthrough", "follow-through", StringComparison.OrdinalIgnoreCase)
            .Replace("refs", "references", StringComparison.OrdinalIgnoreCase)
            .Replace("posture", "status", StringComparison.OrdinalIgnoreCase)
            .Replace("  ", " ", StringComparison.Ordinal);

        if (simplified.Length <= 220)
        {
            return simplified;
        }

        var shortened = simplified[..220];
        var lastSpace = shortened.LastIndexOf(' ');
        return $"{(lastSpace > 0 ? shortened[..lastSpace] : shortened).TrimEnd('.', ' ')}...";
    }

    private static (string Label, string Summary) DescribeDifficulty(int ownerCount, int dependencyCount, int workTaskCount)
    {
        var score = ownerCount + dependencyCount + workTaskCount;
        var summary = $"{ownerCount} owner lane(s), {dependencyCount} dependency(ies), {workTaskCount} tracked slice(s).";
        return score switch
        {
            >= 13 => ("High", summary),
            >= 8 => ("Medium", summary),
            _ => ("Low", summary)
        };
    }

    private static string DescribeClaimedState(string? milestoneStatus, int workTaskCount, int claimedTaskCount)
    {
        if (claimedTaskCount > 0)
        {
            return $"{claimedTaskCount} of {workTaskCount} tracked slice(s) already show progress or completion.";
        }

        if (!string.Equals(milestoneStatus, "not_started", StringComparison.OrdinalIgnoreCase))
        {
            return "The milestone is already marked active even though the task slices are not annotated yet.";
        }

        return "No tracked slice shows started work yet.";
    }

    private static string DescribeDependencies(IReadOnlyList<ProgramMilestoneDependencyViewModel> dependencies)
        => dependencies.Count switch
        {
            0 => "No upstream milestone dependency.",
            1 => $"Depends on M{dependencies[0].Id}.",
            _ => $"Depends on {dependencies.Count} other milestones."
        };

    private static bool IsClaimedTaskStatus(string? status)
        => NormalizeKey(status) switch
        {
            "complete" => true,
            "in_progress" => true,
            "blocked" => true,
            _ => false
        };

    private static string HumanizeStatus(string? status)
        => NormalizeKey(status) switch
        {
            "in_progress" => "In progress",
            "not_started" => "Not started",
            "complete" => "Complete",
            "blocked" => "Blocked",
            _ => "Unknown"
        };

    private static string NormalizeKey(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : value.Trim().ToLowerInvariant();

    private static string EnsureSentence(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "Summary not available.";
        }

        return value.EndsWith(".", StringComparison.Ordinal) || value.EndsWith("!", StringComparison.Ordinal) || value.EndsWith("?", StringComparison.Ordinal)
            ? value
            : $"{value}.";
    }

    private sealed class ProgramMilestoneRegistryDocument
    {
        public List<int>? ImplementationOrderMilestoneIds { get; init; }
        public List<ProgramMilestoneRecord>? Milestones { get; init; }
    }

    private sealed class ProgramMilestoneRecord
    {
        public int Id { get; init; }
        public string? Title { get; init; }
        public string? Wave { get; init; }
        public string? Status { get; init; }
        public List<string>? Owners { get; init; }
        public List<int>? Dependencies { get; init; }
        public List<string>? ExitCriteria { get; init; }
        public List<ProgramMilestoneTask>? WorkTasks { get; init; }
    }

    private sealed class ProgramMilestoneTask
    {
        public string? Status { get; init; }
    }
}
