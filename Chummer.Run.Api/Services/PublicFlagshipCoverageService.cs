using Chummer.Run.Api.ViewModels;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class PublicFlagshipCoverageService
{
    private const string ProgressPartsRelativePath = ".codex-design/product/PUBLIC_PROGRESS_PARTS.yaml";
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .IgnoreUnmatchedProperties()
        .Build();

    private static readonly IReadOnlyList<(string PartId, string CardId, string Href, string ActionLabel)> CoverageOrder =
    [
        ("community-cloud", "hub_and_registry", "/downloads", "Open install and account truth"),
        ("live-play", "mobile_play_shell", "/now#real-mobile-prep", "See continuity in preview"),
        ("workbench-ui", "ui_kit_and_flagship_polish", "/what-is-chummer", "See workbench and shared UI")
    ];

    private readonly PublicCanonFileLoader _canon;

    public PublicFlagshipCoverageService(PublicCanonFileLoader canon)
    {
        _canon = canon;
    }

    public FlagshipCoverageStripViewModel LoadStrip()
    {
        PublicProgressPartsDocument document;
        try
        {
            document = Deserializer.Deserialize<PublicProgressPartsDocument>(_canon.LoadRequiredText(ProgressPartsRelativePath))
                ?? throw new InvalidOperationException($"canon file '{ProgressPartsRelativePath}' could not be deserialized.");
        }
        catch (YamlDotNet.Core.YamlException ex)
        {
            throw new InvalidOperationException($"canon file '{ProgressPartsRelativePath}' is invalid: {ex.Message}", ex);
        }

        var parts = (document.Parts ?? [])
            .ToDictionary(static part => part.Id, StringComparer.OrdinalIgnoreCase);

        var cards = new List<FlagshipCoverageCardViewModel>(CoverageOrder.Count);
        foreach (var (partId, cardId, href, actionLabel) in CoverageOrder)
        {
            if (!parts.TryGetValue(partId, out var part))
            {
                throw new InvalidOperationException($"required public progress part missing: {partId}");
            }

            var current = FindMilestone(part, "now");
            var target = FindMilestone(part, "target");
            cards.Add(new FlagshipCoverageCardViewModel(
                Id: cardId,
                Label: part.PublicName,
                Summary: RequireText(part.Summary, $"{partId}.summary"),
                CurrentTitle: RequireText(current.Title, $"{partId}.milestones.now.title"),
                CurrentBody: RequireText(current.Body, $"{partId}.milestones.now.body"),
                TargetTitle: RequireText(target.Title, $"{partId}.milestones.target.title"),
                TargetBody: RequireText(target.Body, $"{partId}.milestones.target.body"),
                Href: href,
                ActionLabel: actionLabel));
        }

        return new FlagshipCoverageStripViewModel(
            Eyebrow: "Whole-product frontier",
            Heading: "Hub truth, mobile continuity, and shared flagship polish stay visible together.",
            Intro: "The public install path is only one rail. These three lanes keep the front door honest about the hosted account stack, weak-network session return, and the shared UI quality bar behind the real workbench.",
            Cards: cards);
    }

    private static PublicProgressPartMilestoneDocument FindMilestone(PublicProgressPartDocument part, string phase)
    {
        var milestone = (part.Milestones ?? [])
            .FirstOrDefault(item => string.Equals(item.Phase, phase, StringComparison.OrdinalIgnoreCase));
        if (milestone is null)
        {
            throw new InvalidOperationException($"required progress milestone missing: {part.Id}.{phase}");
        }

        return milestone;
    }

    private static string RequireText(string? value, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException($"required public progress field missing: {fieldName}");
        }

        return value.Trim();
    }
}
