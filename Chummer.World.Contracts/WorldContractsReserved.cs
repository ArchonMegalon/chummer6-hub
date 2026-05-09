namespace Chummer.World.Contracts;

public static class WorldContractPackage
{
    public const string PackageId = "Chummer.World.Contracts";
    public const string Status = "reserved_for_black_ledger";
}

public static class WorldCapabilityIds
{
    public const string WorldOperator = "world_operator";
    public const string SeasonOperator = "season_operator";
    public const string FactionSeat = "faction_seat";
    public const string CampaignConsumerOfWorldPacket = "campaign_consumer_of_world_packet";
    public const string ConsequenceReviewer = "consequence_reviewer";
}

public sealed record WorldOffer(
    string OfferId,
    string Label,
    string AvailabilitySummary,
    string ReceiptRef);

public sealed record ThreatTag(
    string ThreatTagId,
    string Label,
    string Summary);

public sealed record ScenarioModifier(
    string ModifierId,
    string Label,
    string Summary,
    string ReceiptRef);

public sealed record CampaignOverlayPackage(
    string OverlayPackageId,
    string Label,
    string Summary,
    string ReceiptRef);

public sealed record WorldFrame(
    string WorldFrameId,
    string Label,
    string Summary,
    IReadOnlyList<string> DistrictRefs,
    IReadOnlyList<string> FactionRefs);

public sealed record MissionMarketPacket(
    string MissionMarketPacketId,
    string WorldFrameId,
    string Summary,
    IReadOnlyList<JobSeed> JobSeeds);

public sealed record JobSeed(
    string JobSeedId,
    string Title,
    string Summary,
    IReadOnlyList<WorldOffer> Offers,
    IReadOnlyList<ThreatTag> ThreatTags);

public sealed record JobPacket(
    string JobPacketId,
    string JobSeedId,
    string Title,
    string Summary,
    IReadOnlyList<ScenarioModifier> ScenarioModifiers,
    string? CampaignOverlayPackageId = null);

public sealed record ResolutionReport(
    string ResolutionReportId,
    string RunId,
    string Summary,
    IReadOnlyList<string> ConsequenceMarkers,
    DateTimeOffset ResolvedAtUtc,
    string? ApprovalReceiptRef = null,
    string? WorldFrameId = null,
    string? MissionMarketPacketId = null,
    string? JobPacketId = null);

public sealed record WorldTick(
    string WorldTickId,
    string WorldFrameId,
    string Summary,
    IReadOnlyList<string> ConsequenceMarkers,
    string ReceiptRef,
    DateTimeOffset IssuedAtUtc);

public sealed record ShadowfeedBulletin(
    string BulletinId,
    string WorldTickId,
    string Audience,
    string Summary,
    IReadOnlyList<string> TopicTags,
    IReadOnlyList<string> FactionTags,
    string ReceiptRef);

public sealed record ResolutionConsequenceBridge(
    string BridgeId,
    string ResolutionReportId,
    string WorldTickId,
    string BulletinId,
    string Summary,
    string ReceiptRef);
