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
}
