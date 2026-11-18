namespace Chummer.Run.Api.ViewModels;

// Presentation only: no source packet, provider admission, worker identity or
// acceptance command is exposed by the read-only account route.
public sealed record OriginChapterReadingPageViewModel(
    SiteChromeViewModel Chrome,
    string RunnerName,
    string Locale,
    string? Text,
    string Status);
