namespace Chummer.Run.Api.Services.Community;

internal static class SponsorLaneRolePolicy
{
    public static string Normalize(string? value)
        => (value ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "review" => "review",
            "deep_review" => "deep_review",
            _ => "coding",
        };

    public static string MinimumTier(string? role)
        => Normalize(role) switch
        {
            "review" => "plus",
            "deep_review" => "pro",
            _ => "free",
        };

    public static bool IsEligible(string? role, string? authorizationTier)
    {
        var normalizedRole = Normalize(role);
        var normalizedTier = SponsorStatusPolicy.NormalizeAuthorizationTier(authorizationTier);
        if (normalizedRole == "coding" && normalizedTier == "unknown")
        {
            return true;
        }

        return SponsorStatusPolicy.TierPriority(normalizedTier) >= SponsorStatusPolicy.TierPriority(MinimumTier(normalizedRole));
    }

    public static string Label(string? role)
        => Normalize(role) switch
        {
            "review" => "Boost Review",
            "deep_review" => "Boost Deep Review",
            _ => "Boost Coding",
        };

    public static string Summary(string? role)
        => Normalize(role) switch
        {
            "review" => "Use your sponsor lane to help review and acceptance throughput.",
            "deep_review" => "Reserve your sponsor lane for tough final checks and jury-grade review.",
            _ => "Use your sponsor lane to accelerate implementation throughput on premium-eligible slices.",
        };
}
