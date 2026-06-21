namespace Chummer.Run.Api.Services;

public static class PublicSurfaceStatus
{
    public const string AvailableToday = "Available today";
    public const string PreviewInProgress = "Preview in progress";
    public const string PreparingNext = "Preparing next";
    public const string DesigningInPublic = "Designing in public";
    public const string ResearchTrack = "Research track";

    public static string DisplayLabel(string? badge)
        => badge?.Trim() switch
        {
            null or "" => string.Empty,
            "Live now" => AvailableToday,
            "Inspectable" => AvailableToday,
            "Available today" => AvailableToday,
            "Preview" => PreviewInProgress,
            "Preparing" => PreparingNext,
            "Designing" => DesigningInPublic,
            "Research" => ResearchTrack,
            _ => badge
        };

    public static bool IsAvailableToday(string? badge)
        => string.Equals(DisplayLabel(badge), AvailableToday, StringComparison.OrdinalIgnoreCase);

    public static bool IsPreviewInProgress(string? badge)
        => string.Equals(DisplayLabel(badge), PreviewInProgress, StringComparison.OrdinalIgnoreCase);

    public static bool IsPreparingNext(string? badge)
        => string.Equals(DisplayLabel(badge), PreparingNext, StringComparison.OrdinalIgnoreCase);

    public static bool IsDesigningInPublic(string? badge)
        => string.Equals(DisplayLabel(badge), DesigningInPublic, StringComparison.OrdinalIgnoreCase);

    public static bool IsResearchTrack(string? badge)
        => string.Equals(DisplayLabel(badge), ResearchTrack, StringComparison.OrdinalIgnoreCase);

    public static string CssTone(string? badge)
        => DisplayLabel(badge) switch
        {
            AvailableToday => string.Empty,
            PreviewInProgress => "tag--amber",
            PreparingNext => "tag--quiet",
            DesigningInPublic => "tag--amber",
            ResearchTrack => "tag--quiet",
            _ => string.Empty
        };

    public static string AudienceLabel(string? audience)
    {
        if (string.IsNullOrWhiteSpace(audience))
        {
            return "Anyone evaluating Chummer";
        }

        var rawParts = audience
            .Split([',', ';', '/'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        if (rawParts.Length == 0)
        {
            return "Anyone evaluating Chummer";
        }

        var labels = rawParts
            .Select(static part => part.Trim())
            .Where(static part => !string.IsNullOrWhiteSpace(part))
            .Select(static part => part.ToLowerInvariant() switch
            {
                "public" => "Anyone evaluating Chummer",
                "signed_in" or "signed-in" or "registered" or "account" => "Signed-in users",
                "gm" or "game_master" or "game-master" => "Game masters",
                "player" => "Players",
                "creator" => "Creators",
                "operator" or "community_operator" or "community-operator" => "Maintainers",
                _ => System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(part.Replace('_', ' ').Replace('-', ' '))
            })
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return labels.Length == 0
            ? "Anyone evaluating Chummer"
            : string.Join(", ", labels);
    }
}
