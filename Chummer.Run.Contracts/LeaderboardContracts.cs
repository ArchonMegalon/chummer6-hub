namespace Chummer.Run.Contracts.Leaderboards;

public sealed record LeaderboardRowDto(
    int Rank,
    string UserId,
    string DisplayName,
    int Points,
    int ContributionCount,
    int LandedSlices,
    int VerifiedSlices,
    int ParticipantTotalTokens,
    string? ParticipantCodexCode,
    int BadgeCount,
    int ActiveSessions,
    string Visibility);

public sealed record SponsorRankLeaderboardRowDto(
    int Rank,
    string UserId,
    string DisplayName,
    int LifetimePoints,
    int ContributionCount,
    string CurrentAuthorizationTier,
    int CurrentSponsorBonus,
    int CurrentRankScore,
    int ActiveSponsorSessions,
    int LandedSlices,
    int VerifiedSlices,
    int ParticipantTotalTokens,
    string? ParticipantCodexCode,
    IReadOnlyList<string> CurrentStatusBadges,
    IReadOnlyList<string> PersistentBadges,
    string Visibility);

public sealed record CodexUsageLeaderboardRowDto(
    int Rank,
    string UserId,
    string DisplayName,
    string? ParticipantCodexCode,
    int ParticipantTotalTokens,
    int ReceiptCount,
    int LandedSlices,
    string Visibility);

public sealed record GroupLeaderboardRowDto(
    int Rank,
    string GroupId,
    string GroupName,
    int Points,
    int LandedSlices,
    int ActiveSessions);

public sealed record QuestDto(
    string QuestId,
    string Title,
    string Description,
    int CurrentProgress,
    int TargetProgress,
    string Status);

public sealed record BadgeDto(
    string BadgeId,
    string UserId,
    string Key,
    string Label,
    DateTimeOffset AwardedAtUtc,
    string BadgeScope = "user",
    string BadgeKind = "persistent",
    string Status = "active",
    DateTimeOffset? RevokedAtUtc = null,
    string? RevocationReason = null,
    string? SourceSponsorSessionId = null);

public sealed record UserRecognitionSummaryDto(
    string UserId,
    int LifetimePoints,
    int ContributionCount,
    int CurrentSponsorRankScore,
    string CurrentAuthorizationTier,
    string CurrentTierSource,
    int CurrentSponsorBonus,
    int LandedSlices,
    int VerifiedSlices,
    int ParticipantTotalTokens,
    string? ParticipantCodexCode,
    int ActiveSessionCount,
    IReadOnlyList<BadgeDto> CurrentStatusBadges,
    IReadOnlyList<BadgeDto> PersistentBadges,
    IReadOnlyList<BadgeDto> RevokedBadges);
