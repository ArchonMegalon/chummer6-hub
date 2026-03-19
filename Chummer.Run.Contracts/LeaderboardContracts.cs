namespace Chummer.Run.Contracts.Leaderboards;

public sealed record LeaderboardRowDto(
    int Rank,
    string UserId,
    string DisplayName,
    int Points,
    int LandedSlices,
    int VerifiedSlices,
    int ActiveSessions,
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
    DateTimeOffset AwardedAtUtc);
