namespace Chummer.Run.Api.Services.Community;

internal static class SponsorStatusPolicy
{
    public const int ActiveSessionBonus = 3;

    private static readonly HashSet<string> CurrentStatuses = new(StringComparer.OrdinalIgnoreCase)
    {
        "auth_ready",
        "lane_pending",
        "active",
    };

    private static readonly HashSet<string> TerminalStatuses = new(StringComparer.OrdinalIgnoreCase)
    {
        "stopped",
        "revoked",
    };

    public static string NormalizeAuthorizationTier(string? value)
        => (value ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "free" => "free",
            "go" => "go",
            "plus" => "plus",
            "pro" => "pro",
            "business" => "business",
            "edu" => "edu",
            "enterprise" => "enterprise",
            _ => "unknown",
        };

    public static string NormalizeTierSource(string? value)
        => (value ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "fleet_detected" => "fleet_detected",
            "user_declared" => "user_declared",
            "operator_verified" => "operator_verified",
            _ => "unknown",
        };

    public static bool IsCurrentSponsorSession(string? status, DateTimeOffset? authorizedAtUtc)
    {
        var normalized = (status ?? string.Empty).Trim();
        if (CurrentStatuses.Contains(normalized))
        {
            return true;
        }

        return authorizedAtUtc is not null && !TerminalStatuses.Contains(normalized);
    }

    public static int TierPriority(string? value)
        => NormalizeAuthorizationTier(value) switch
        {
            "enterprise" => 6,
            "business" => 5,
            "edu" => 4,
            "pro" => 3,
            "plus" => 2,
            "go" => 1,
            "free" => 0,
            _ => -1,
        };

    public static int TierBonus(string? value)
        => NormalizeAuthorizationTier(value) switch
        {
            "plus" => 5,
            "pro" => 15,
            "business" => 20,
            "edu" => 20,
            "enterprise" => 25,
            _ => 0,
        };

    public static IReadOnlyList<string> ActiveTierBadgeKeys { get; } =
    [
        "plus-sponsor-active",
        "pro-sponsor-active",
        "business-sponsor-active",
        "edu-sponsor-active",
        "enterprise-sponsor-active",
    ];

    public static (string Key, string Label)? ActiveTierBadge(string? value)
        => NormalizeAuthorizationTier(value) switch
        {
            "plus" => ("plus-sponsor-active", "Plus Sponsor Active"),
            "pro" => ("pro-sponsor-active", "Pro Sponsor Active"),
            "business" => ("business-sponsor-active", "Business Sponsor Active"),
            "edu" => ("edu-sponsor-active", "Edu Sponsor Active"),
            "enterprise" => ("enterprise-sponsor-active", "Enterprise Sponsor Active"),
            _ => null,
        };
}
