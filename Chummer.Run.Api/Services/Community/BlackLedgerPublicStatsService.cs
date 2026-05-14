using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services.Community;

public sealed class BlackLedgerPublicStatsService
{
    private static readonly BlackLedgerPublicStatViewModel[] SeededPreviewStats =
    [
        new(
            Id: "mysad-density",
            Title: "MysAd density",
            Value: "Barrens adepts 34%",
            Scope: "Public aggregate",
            Period: "Current season",
            SampleSize: "47 opted-in runners",
            Confidence: "Preview",
            PrivacyNote: "Opt-in aggregate only",
            Source: "seeded_preview",
            Status: "preview",
            Href: "/ledger/stats#mysad-density"),
        new(
            Id: "debt-heat",
            Title: "Debt Heat",
            Value: "128,400Y active favors",
            Scope: "Public aggregate",
            Period: "This month",
            SampleSize: "12 crews",
            Confidence: "Enough data",
            PrivacyNote: "Fictional runner/campaign statistics only",
            Source: "seeded_preview",
            Status: "preview",
            Href: "/ledger/stats#debt-heat"),
        new(
            Id: "package-pressure",
            Title: "Package pressure",
            Value: "7 hot package candidates",
            Scope: "Public aggregate",
            Period: "Current release train",
            SampleSize: "31 followed requests",
            Confidence: "Preview",
            PrivacyNote: "Proof-backed demand, not roadmap truth",
            Source: "package_registry",
            Status: "preview",
            Href: "/ledger/packages"),
        new(
            Id: "chaos-index",
            Title: "Chaos index",
            Value: "Touristville crews +18",
            Scope: "Public aggregate",
            Period: "Current season",
            SampleSize: "19 opted-in tables",
            Confidence: "Low sample",
            PrivacyNote: "Playful fictional labels only; never point at real people.",
            Source: "seeded_preview",
            Status: "preview",
            Href: "/ledger/factions#chaos-index"),
    ];

    private static readonly BlackLedgerModuleViewModel[] Modules =
    [
        new("faction-intel", "Faction Intel", "Read public-safe faction pressure without exposing private tables or runner identities.", "/ledger/factions", "Opt-in aggregate"),
        new("runner-archetypes", "Runner Archetype Stats", "See archetype pressure, chrome load, and role-shift signals as public-safe aggregates.", "/ledger/stats", "Preview"),
        new("package-pressure", "Package Pressure", "Track followed package demand and compatibility heat without claiming shipped status early.", "/ledger/packages", "Governed preview"),
        new("karma-forge-candidates", "Karma Forge Candidate Feed", "See which discovery lanes are generating governed package candidates and closeout motion.", "/karma-forge", "Discovery-linked"),
        new("closeout-feed", "Closeout Feed", "Follow proof-backed closeout motion after public-safe review, not before.", "/ledger/closeouts", "Proof-backed only"),
    ];

    private static readonly BlackLedgerCloseoutViewModel[] Closeouts =
    [
        new("Closeout witness feed", "Proof-backed closeout updates only appear after package, route, and release receipts all agree.", "/ledger/closeouts", "Proof-backed"),
        new("Package recovery watch", "Recovery and rollback posture stays visible without implying promoted shipment.", "/packages", "Governed preview"),
        new("Karma Forge dispatch", "Discovery packets can point at candidate motion, but not shipped status, until release proof is real.", "/karma-forge", "Signal only"),
    ];

    public IReadOnlyList<BlackLedgerPublicStatViewModel> ListHomepageStats()
        => ListPublicStats().Take(4).ToArray();

    public IReadOnlyList<BlackLedgerPublicStatViewModel> ListPublicStats()
        => SeededPreviewStats.Where(IsPublicSafe).ToArray();

    public IReadOnlyList<BlackLedgerModuleViewModel> ListModules()
        => Modules;

    public IReadOnlyList<BlackLedgerCloseoutViewModel> ListCloseouts()
        => Closeouts;

    private static bool IsPublicSafe(BlackLedgerPublicStatViewModel stat)
        => !string.IsNullOrWhiteSpace(stat.Id)
           && !string.IsNullOrWhiteSpace(stat.Title)
           && !string.IsNullOrWhiteSpace(stat.Value)
           && string.Equals(stat.Scope, "Public aggregate", StringComparison.Ordinal)
           && !string.IsNullOrWhiteSpace(stat.Period)
           && !string.IsNullOrWhiteSpace(stat.SampleSize)
           && !string.IsNullOrWhiteSpace(stat.Confidence)
           && !string.IsNullOrWhiteSpace(stat.PrivacyNote)
           && !string.IsNullOrWhiteSpace(stat.Source)
           && !string.IsNullOrWhiteSpace(stat.Status)
           && !string.IsNullOrWhiteSpace(stat.Href);
}
