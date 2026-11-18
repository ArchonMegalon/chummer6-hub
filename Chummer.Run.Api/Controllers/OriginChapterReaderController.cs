using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ResponseCache(NoStore = true, Location = ResponseCacheLocation.None)]
public sealed class OriginChapterReaderController(
    HubIdentityClient identity,
    AccountService accounts,
    OriginChapterAuthoringService chapters,
    HubPageChromeService chrome) : Controller
{
    public const string LibraryPath = "/account/work/origin-chapters";

    [HttpGet(LibraryPath)]
    [Produces("text/html")]
    public Task<IActionResult> Library(CancellationToken cancellationToken)
        => WithOwner(LibraryPath, cancellationToken, (subject, displayName, email) =>
        {
            var entries = chapters.ListForReader(subject);
            var cards = entries.Select(entry => new AccountHubCardViewModel(
                "Life Modules",
                entry.Job.Source.RunnerName,
                CanRead(entry.Job) ? ChapterTitle(entry.Job.DraftText!) : Status(entry.Job),
                CanRead(entry.Job) ? "Read full chapter" : "View chapter status",
                $"{LibraryPath}/{entry.Reference}", null, null)).ToArray();
            return View("~/Views/Accounts/Section.cshtml", new AccountSectionPageViewModel(
                Chrome: chrome.BuildAuthenticatedChrome("Life Modules chapters", "Your private growing stories.", LibraryPath, displayName, email),
                Eyebrow: "Origin library", Heading: "Life Modules chapters",
                Summary: "Read the full chapters already written for your runners. Continue your story and confirm reading in the app.",
                Highlights: cards.Length == 0 ? ["No chapters have been sent from this account yet."] : [],
                Cards: cards, BackLabel: "Back to my books", BackHref: "/account/work/origin-dossiers"));
        });

    [HttpGet(LibraryPath + "/{reference}")]
    [Produces("text/html")]
    public Task<IActionResult> Read([FromRoute] string reference, CancellationToken cancellationToken)
        => WithOwner(LibraryPath + "/" + Uri.EscapeDataString(reference), cancellationToken, (subject, displayName, email) =>
        {
            var chapter = chapters.GetForReader(subject, reference);
            if (chapter is null) return Unavailable(StatusCodes.Status404NotFound,
                "Chapter unavailable", "This chapter is not available for this account.", LibraryPath);
            return View("~/Views/Accounts/OriginChapter.cshtml", new OriginChapterReadingPageViewModel(
                chrome.BuildAuthenticatedChrome("Read your story", "Your private Origin chapter.",
                    LibraryPath, displayName, email), chapter.Source.RunnerName, chapter.Source.Locale,
                CanRead(chapter) ? chapter.DraftText : null, Status(chapter)));
        });

    private async Task<IActionResult> WithOwner(string currentPath, CancellationToken ct,
        Func<string, string, string?, IActionResult> read)
    {
        global::Chummer.Run.Api.PrivateResponseCacheHeaders.Apply(Response.Headers);
        Response.Headers["Referrer-Policy"] = "no-referrer";
        try
        {
            var subject = await identity.RequireFreshSubjectAsync(Request, ct);
            var user = accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            IActionResult result = read(subject.SubjectId, user.DisplayName, user.Email);
            ct.ThrowIfCancellationRequested();
            // A storage read can block. Do not return private prose after a
            // revoked session or a different principal is observed.
            var fresh = await identity.RequireFreshSubjectAsync(Request, ct);
            if (fresh.SubjectId != subject.SubjectId)
                return Unavailable(StatusCodes.Status403Forbidden, "Account changed",
                    "Open your library again with the intended account.", LibraryPath);
            return result;
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            return Unavailable(ex.StatusCode, "Library unavailable",
                "Your account could not be confirmed. Your stories were not changed.", currentPath);
        }
        catch (Exception ex) when (ex is IOException or InvalidOperationException or HttpRequestException
            or TimeoutException or System.Text.Json.JsonException
            || ex is OperationCanceledException && !ct.IsCancellationRequested)
        {
            return Unavailable(StatusCodes.Status503ServiceUnavailable, "Library unavailable",
                "Your chapters could not be loaded right now. No story was restarted or marked as read.", currentPath);
        }
    }

    private ViewResult Unavailable(int status, string heading, string message, string retryPath)
    {
        Response.StatusCode = status;
        return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
            Chrome: chrome.BuildPublicChrome(heading, message, LibraryPath), Heading: heading,
            SupportLine: message, Notice: null, PrimaryLabel: "Open chapters", PrimaryHref: retryPath,
            SecondaryLabel: "Back to my books", SecondaryHref: "/account/work/origin-dossiers"));
    }

    private static bool CanRead(OriginChapterAuthoringJob chapter)
        => chapter.State == OriginChapterAuthoringStates.ReviewRequired && !string.IsNullOrWhiteSpace(chapter.DraftText);

    private static string Status(OriginChapterAuthoringJob chapter)
        => CanRead(chapter) ? "The full generated chapter is available below."
            : chapter.State == OriginChapterAuthoringStates.ReconciliationRequired
                ? "Chapter preparation is being checked. A reliable completion time is not available yet."
                : "Your chapter is waiting to be written. A reliable completion time is not available yet.";

    private static string ChapterTitle(string text)
    {
        string firstLine = text.Split('\n', 2)[0].Trim().TrimStart('#').Trim();
        return firstLine.Length == 0 ? "Your full chapter is ready." : firstLine.Length <= 100 ? firstLine : firstLine[..100] + "…";
    }
}
