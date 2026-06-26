namespace Chummer.Run.Api.Services;

public static class UndetectableHumanizerCopyAdapter
{
    private static readonly Dictionary<string, string> PublicStatusLabels = new(StringComparer.OrdinalIgnoreCase)
    {
        ["active"] = "Ready",
        ["linked"] = "Ready",
        ["pending"] = "Pending",
        ["pending_verification"] = "Confirmation sent",
        ["verified"] = "Confirmed",
        ["approved"] = "Approved",
        ["published"] = "Published",
        ["self_service"] = "Self-service",
        ["review"] = "Needs attention",
        ["warning"] = "Needs attention",
        ["attention"] = "Needs attention",
        ["ready"] = "Ready",
        ["revoked"] = "Revoked",
        ["campaign_approved"] = "Campaign-approved",
        ["sandbox"] = "Sandbox",
        ["current"] = "Current",
        ["next"] = "Next",
        ["completed"] = "Completed",
    };

    private static readonly (string Source, string Target)[] HomeRules =
    [
        ("proof", "status"),
        ("receipt", "record"),
        ("artifact", "file"),
        ("operator", "maintainer"),
        ("canonical", "main"),
        ("truth", "state"),
        ("provider", "service"),
    ];

    private static readonly (string Source, string Target)[] KarmaForgeIntakeRules =
    [
        ("Product Governor", "product decision"),
        ("FacePop", "public invitation"),
        ("Deftform", "structured pre-screen"),
        ("Icanpreneur", "guided request path"),
        ("Teable", "shared board"),
        ("NextStep", "next step"),
        ("operator projections", "saved projections"),
        ("operator projection", "saved projection"),
    ];

    private static readonly (string Source, string Target)[] KarmaForgeSubmittedRules =
    [
        ("Product Governor", "product decision"),
        ("FacePop", "public invitation"),
        ("Deftform", "structured pre-screen"),
        ("Icanpreneur", "guided request path"),
        ("Teable", "shared board"),
        ("NextStep", "next step"),
        ("OperatorNotes", "TeamNotes"),
        ("bounded", "limited"),
        ("normalized", "saved"),
        ("packet", "request"),
        ("receipt", "note"),
        ("governed", "guided"),
        ("HouseRuleDemandPacket", "rules request"),
        ("KarmaForgeCandidate", "saved request"),
    ];

    private static readonly (string Source, string Target)[] FeedbackOperationsRules =
    [
        ("source item", "original item"),
        ("source details", "related details"),
        ("source", "related"),
        ("record(s)", "update(s)"),
        ("records", "updates"),
        ("record", "update"),
    ];

    private static readonly (string Source, string Target)[] RoadmapRules =
    [
        ("product threads", "planned work"),
        ("product thread", "planned work"),
        ("planned work", "future work"),
        ("maintenance", "future work"),
        ("Claimed", "Started"),
        ("claim", "start"),
        ("implementation tranche", "work item"),
        ("implementation slice", "work item"),
        ("implementation", "work"),
    ];

    private static readonly (string Source, string Target)[] PublicationRules =
    [
        ("provenance", "origin"),
        ("lineage", "history"),
        ("route", "page"),
        ("creator" + " concierge", "creator help"),
        ("testimonial" + " wrapper", "testimonial page"),
        ("discovery family", "gallery"),
        ("publication packet", "publication"),
    ];

    private static readonly (string Source, string Target)[] PackageRules =
    [
        ("provenance", "history"),
        ("records", "updates"),
    ];

    private static readonly (string Source, string Target)[] LedgerRules =
    [
        ("MysAd Density", "Awakened pressure"),
        ("MysAd", "Awakened"),
        ("proof routing", "status routing"),
        ("proof", "status"),
        ("receipts", "details"),
        ("receipt", "detail"),
        ("SourceReceipt", "turn detail"),
        ("source receipt", "turn detail"),
        ("clean room", "review desk"),
        ("package truth", "package status"),
        ("source-clarity", "source clarity"),
        ("operator", "maintainer"),
        ("provider", "service"),
        ("artifact", "file"),
        ("generated", "prepared"),
        ("flagship seeded", "current"),
        ("preseeded", "current"),
        ("seeded", "current"),
    ];

    public static string Humanize(string? value)
        => PublicFacingCopyHumanizer.Clean(value);

    public static IReadOnlyList<string> HumanizeLines(IEnumerable<string>? values)
        => PublicFacingCopyHumanizer.CleanLines(values);

    public static string HumanizeHome(string? value)
        => Humanize(ApplyRules(value, HomeRules));

    public static string HumanizeKarmaForgeIntake(string? value)
        => Humanize(ApplyRules(value, KarmaForgeIntakeRules));

    public static string HumanizeKarmaForgeSubmitted(string? value)
        => Humanize(ApplyRules(value, KarmaForgeSubmittedRules));

    public static string HumanizeFeedbackOperations(string? value)
        => Humanize(ApplyRules(value, FeedbackOperationsRules));

    public static string HumanizeRoadmap(string? value)
        => Humanize(ApplyRules(value, RoadmapRules));

    public static string HumanizePublication(string? value)
        => Humanize(ApplyRules(value, PublicationRules));

    public static string HumanizePackage(string? value)
        => Humanize(ApplyRules(value, PackageRules));

    public static string HumanizeLedger(string? value)
    {
        string cleaned = Humanize(ApplyRules(value, LedgerRules));
        cleaned = System.Text.RegularExpressions.Regex.Replace(
            cleaned,
            @"\bledger[_ -]?tick[_ -]?\d+(?:[_ -][a-z0-9]+)*\b",
            "current turn",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(50));
        cleaned = System.Text.RegularExpressions.Regex.Replace(
            cleaned,
            @"\bledger[_ -]?dispatch[_ -][a-z0-9_-]+\b",
            "current dispatch",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(50));
        return cleaned;
    }

    public static string HumanizeStatusLabel(string? value, string fallback = "Not connected")
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return fallback;
        }

        string normalized = value.Trim();
        if (PublicStatusLabels.TryGetValue(normalized, out string? label))
        {
            return label;
        }

        return System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(normalized.Replace('_', ' '));
    }

    private static string ApplyRules(string? value, ReadOnlySpan<(string Source, string Target)> rules)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string cleaned = value;
        foreach (var (source, target) in rules)
        {
            cleaned = cleaned.Replace(source, target, StringComparison.OrdinalIgnoreCase);
        }

        return cleaned;
    }
}
