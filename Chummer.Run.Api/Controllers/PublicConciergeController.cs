using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.WebUtilities;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public/concierge")]
public sealed class PublicConciergeController : Controller
{
    private readonly PublicConciergeService _concierge;
    private readonly HubPageChromeService _chrome;
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly PublicCreatorPublicationDiscoveryService _publicCreatorDiscovery;
    private readonly ILogger<PublicConciergeController> _logger;

    public PublicConciergeController(
        PublicConciergeService concierge,
        HubPageChromeService chrome,
        HubIdentityClient identity,
        AccountService accounts,
        PublicCreatorPublicationDiscoveryService publicCreatorDiscovery,
        ILogger<PublicConciergeController> logger)
    {
        _concierge = concierge;
        _chrome = chrome;
        _identity = identity;
        _accounts = accounts;
        _publicCreatorDiscovery = publicCreatorDiscovery;
        _logger = logger;
    }

    [HttpGet("/downloads/concierge")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadsConcierge(CancellationToken cancellationToken)
        => await RenderSurfaceAsync(
            surfaceKey: "downloads",
            title: "Downloads concierge",
            description: "Humanized setup routing on a bounded first-party wrapper.",
            currentPath: "/downloads/concierge",
            cancellationToken);

    [HttpGet("/now/concierge")]
    [Produces("text/html")]
    public async Task<IActionResult> NowConcierge(CancellationToken cancellationToken)
        => await RenderSurfaceAsync(
            surfaceKey: "now",
            title: "Release concierge",
            description: "Short guided release routing without surrendering first-party truth.",
            currentPath: "/now/concierge",
            cancellationToken);

    [HttpGet("/contact/concierge")]
    [Produces("text/html")]
    public async Task<IActionResult> ContactConcierge(CancellationToken cancellationToken)
        => await RenderSurfaceAsync(
            surfaceKey: "contact",
            title: "Support routing concierge",
            description: "Choose the safe support lane before the issue gets louder.",
            currentPath: "/contact/concierge",
            cancellationToken);

    [HttpGet("/join/concierge")]
    [Produces("text/html")]
    public async Task<IActionResult> CampaignInviteConcierge([FromQuery] string? code, CancellationToken cancellationToken)
    {
        string? inviteCode = NormalizeInviteCode(code);
        SiteChromeViewModel chrome = await BuildChromeAsync(
            "Campaign invite concierge",
            "Continue the invite, review the primer, or ask for onboarding help without losing the first-party lane.",
            "/join/concierge",
            cancellationToken);
        PublicConciergePageViewModel model = _concierge.BuildPage(
            "campaign-invite",
            chrome,
            Request.Query["locale"].ToString(),
            Request.Headers.AcceptLanguage.ToString(),
            entryRouteOverride: ResolveInviteContinuationRoute(inviteCode, chrome.Authenticated),
            contextId: inviteCode);
        if (!string.IsNullOrWhiteSpace(model.Widget.ContentSecurityPolicy))
        {
            Response.Headers["Content-Security-Policy"] = model.Widget.ContentSecurityPolicy;
        }

        return View("~/Views/PublicLanding/Concierge.cshtml", model);
    }

    [HttpGet("/join/primer")]
    [Produces("text/html")]
    public async Task<IActionResult> CampaignInvitePrimer([FromQuery] string? code, [FromQuery] string? mode, CancellationToken cancellationToken)
    {
        string? inviteCode = NormalizeInviteCode(code);
        bool packetMode = string.Equals(mode, "packet", StringComparison.OrdinalIgnoreCase);
        SiteChromeViewModel chrome = await BuildChromeAsync(
            packetMode ? "Campaign primer packet" : "Campaign primer",
            "First-session orientation, expectations, and the next safe invite step on one first-party page.",
            "/join/primer",
            cancellationToken);
        string continueInviteHref = ResolveInviteContinuationRoute(inviteCode, chrome.Authenticated);
        string inviteWrapperHref = string.IsNullOrWhiteSpace(inviteCode)
            ? "/join/concierge"
            : QueryHelpers.AddQueryString("/join/concierge", new Dictionary<string, string?> { ["code"] = inviteCode });
        CampaignInvitePrimerPageViewModel model = new(
            Chrome: chrome,
            InviteCode: inviteCode ?? string.Empty,
            InviteCodePresent: !string.IsNullOrWhiteSpace(inviteCode),
            Heading: packetMode
                ? "Use the primer packet to align expectations before the table moves."
                : "Use the primer guide to reduce first-session friction before you click deeper.",
            Intro: packetMode
                ? "This packet view keeps expectations, setup prep, and session-zero continuity together instead of scattering them between support, downloads, and campaign lore."
                : "This primer view keeps orientation, prep, and the next invite step together instead of forcing a new player or GM to guess which page matters first.",
            ProofPoints:
            [
                inviteCode is null ? "No invite code is attached yet" : $"Invite code attached: {inviteCode}",
                "Primer and join remain first-party",
                "Session-zero help stays separate from support and installs"
            ],
            Sections:
            [
                new CampaignInvitePrimerSectionViewModel(
                    Id: "continue",
                    Eyebrow: "Join rail",
                    Heading: "Continue the governed invite on purpose.",
                    Summary: chrome.Authenticated
                        ? "You already have a signed-in return lane, so the safest next step is the invite-capable community work rail."
                        : "Create the account only when you are ready to continue the governed invite and keep the return lane attached.",
                    Bullets:
                    [
                        "Invite continuation stays on first-party account rails.",
                        "Join-code continuity should not hide behind a booking or support provider.",
                        "The wrapper can be replayed safely if the first pass is interrupted."
                    ],
                    PrimaryAction: new TrustPageActionViewModel(
                        chrome.Authenticated ? "Open invite tools" : "Claim your copy",
                        continueInviteHref,
                        "primary"),
                    SecondaryAction: new TrustPageActionViewModel("Back to invite concierge", inviteWrapperHref, "secondary")),
                new CampaignInvitePrimerSectionViewModel(
                    Id: "primer",
                    Eyebrow: "Primer",
                    Heading: packetMode ? "Packet-first orientation" : "Video-first orientation",
                    Summary: packetMode
                        ? "Use the packet posture when the player or GM needs expectations, prep, and table etiquette in one calmer read."
                        : "Use the video posture when the quickest win is a short orientation before anyone reads a longer packet.",
                    Bullets:
                    [
                        "Prep the install path before the session rather than during it.",
                        "Confirm table expectations, spoiler boundaries, and recovery posture up front.",
                        "Route unresolved questions into the invite help lane instead of guessing in chat."
                    ],
                    PrimaryAction: new TrustPageActionViewModel(
                        packetMode ? "Open video posture" : "Open packet posture",
                        QueryHelpers.AddQueryString("/join/primer", new Dictionary<string, string?> { ["mode"] = packetMode ? "video" : "packet", ["code"] = inviteCode }),
                        "secondary"),
                    SecondaryAction: new TrustPageActionViewModel(
                        "Ask invite questions",
                        "/contact?kind=campaign_invite&title=Need%20campaign%20invite%20help&summary=Need%20invite%20or%20primer%20follow-up#support-intake",
                        "ghost")),
                new CampaignInvitePrimerSectionViewModel(
                    Id: "session-zero",
                    Eyebrow: "Session zero",
                    Heading: "Escalate to a session-zero handoff only when the primer is not enough.",
                    Summary: "The session-zero lane exists for questions that need a human checkpoint. It should not become the hidden owner of the invite, account, or install truth.",
                    Bullets:
                    [
                        "Use help when the blocker is understanding, not a broken install.",
                        "Keep private support on the private support rail.",
                        "Keep campaign orientation separate from release and download truth."
                    ],
                    PrimaryAction: new TrustPageActionViewModel(
                        "Request session-zero help",
                        "/contact?kind=session_zero&title=Request%20session%20zero%20help&summary=Need%20a%20short%20session%20zero%20or%20invite%20briefing#support-intake",
                        "ghost"),
                    SecondaryAction: new TrustPageActionViewModel("Open help", "/help", "secondary"))
            ],
            Actions:
            [
                new TrustPageActionViewModel("Back to invite concierge", inviteWrapperHref, "primary"),
                new TrustPageActionViewModel(chrome.Authenticated ? "Open account work" : "Claim your copy", continueInviteHref, "secondary"),
                new TrustPageActionViewModel("Open downloads", "/downloads", "ghost")
            ]);
        return View("~/Views/PublicLanding/JoinPrimer.cshtml", model);
    }

    [HttpGet("/artifacts/publications/{publicationId}/concierge")]
    [Produces("text/html")]
    public async Task<IActionResult> CreatorPublicationConcierge([FromRoute] string publicationId, CancellationToken cancellationToken)
    {
        if (_publicCreatorDiscovery.GetDiscoverable(publicationId) is null)
        {
            return NotFound();
        }

        string currentPath = $"/artifacts/publications/{Uri.EscapeDataString(publicationId)}/concierge";
        SiteChromeViewModel chrome = await BuildChromeAsync(
            "Creator concierge",
            "Bounded creator consult and publication follow-up routing.",
            currentPath,
            cancellationToken);
        PublicConciergePageViewModel model = _concierge.BuildPage(
            "creator-publication",
            chrome,
            Request.Query["locale"].ToString(),
            Request.Headers.AcceptLanguage.ToString(),
            entryRouteOverride: $"/artifacts/publications/{Uri.EscapeDataString(publicationId)}",
            contextId: publicationId);
        if (!string.IsNullOrWhiteSpace(model.Widget.ContentSecurityPolicy))
        {
            Response.Headers["Content-Security-Policy"] = model.Widget.ContentSecurityPolicy;
        }

        return View("~/Views/PublicLanding/Concierge.cshtml", model);
    }

    [HttpGet("/testimonials/concierge")]
    [Produces("text/html")]
    public async Task<IActionResult> TestimonialConcierge([FromQuery] string? publicationId, CancellationToken cancellationToken)
    {
        string? returnRoute = ResolvePublicationReturnRoute(publicationId);
        SiteChromeViewModel chrome = await BuildChromeAsync(
            "Public stories",
            "Share a moderated note for the publication page.",
            "/testimonials/concierge",
            cancellationToken);
        PublicConciergePageViewModel model = _concierge.BuildPage(
            "testimonials",
            chrome,
            Request.Query["locale"].ToString(),
            Request.Headers.AcceptLanguage.ToString(),
            entryRouteOverride: returnRoute,
            contextId: publicationId);
        if (!string.IsNullOrWhiteSpace(model.Widget.ContentSecurityPolicy))
        {
            Response.Headers["Content-Security-Policy"] = model.Widget.ContentSecurityPolicy;
        }

        return View("~/Views/PublicLanding/Concierge.cshtml", model);
    }

    [HttpGet("/downloads/concierge/{branchId}")]
    public async Task<IActionResult> DownloadsBranch([FromRoute] string branchId, CancellationToken cancellationToken)
        => await RedirectBranchAsync("downloads", branchId, cancellationToken);

    [HttpGet("/now/concierge/{branchId}")]
    public async Task<IActionResult> NowBranch([FromRoute] string branchId, CancellationToken cancellationToken)
        => await RedirectBranchAsync("now", branchId, cancellationToken);

    [HttpGet("/contact/concierge/{branchId}")]
    public async Task<IActionResult> ContactBranch([FromRoute] string branchId, CancellationToken cancellationToken)
        => await RedirectBranchAsync("contact", branchId, cancellationToken);

    [HttpGet("/join/concierge/{branchId}")]
    public async Task<IActionResult> CampaignInviteBranch([FromRoute] string branchId, [FromQuery] string? code, CancellationToken cancellationToken)
        => await RedirectBranchAsync("campaign-invite", branchId, cancellationToken, NormalizeInviteCode(code));

    [HttpGet("/artifacts/publications/{publicationId}/concierge/{branchId}")]
    public async Task<IActionResult> CreatorPublicationBranch([FromRoute] string publicationId, [FromRoute] string branchId, CancellationToken cancellationToken)
    {
        if (_publicCreatorDiscovery.GetDiscoverable(publicationId) is null)
        {
            return NotFound();
        }

        return await RedirectBranchAsync("creator-publication", branchId, cancellationToken, publicationId);
    }

    [HttpGet("/testimonials/concierge/{branchId}")]
    public async Task<IActionResult> TestimonialBranch([FromRoute] string branchId, [FromQuery] string? publicationId, CancellationToken cancellationToken)
        => await RedirectBranchAsync("testimonials", branchId, cancellationToken, publicationId);

    [HttpPost("providers/{provider}/webhook")]
    [HttpPost("/api/v1/public/concierge/providers/{provider}/webhook")]
    [IgnoreAntiforgeryToken]
    [Consumes("application/json")]
    public ActionResult ReceiveWebhook([FromRoute] string provider, [FromBody] JsonElement payload)
    {
        try
        {
            ConciergeWebhookResult result = _concierge.RecordWebhook(
                provider,
                payload,
                Request.Headers,
                HttpContext.Connection.RemoteIpAddress?.ToString());
            return Accepted(new
            {
                result.ReceiptId,
                result.VerificationState,
                result.Summary,
                result.ModerationItemId
            });
        }
        catch (UnauthorizedAccessException ex)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: ex.Message);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    private async Task<IActionResult> RenderSurfaceAsync(
        string surfaceKey,
        string title,
        string description,
        string currentPath,
        CancellationToken cancellationToken)
    {
        SiteChromeViewModel chrome = await BuildChromeAsync(title, description, currentPath, cancellationToken);
        PublicConciergePageViewModel model = _concierge.BuildPage(
            surfaceKey,
            chrome,
            Request.Query["locale"].ToString(),
            Request.Headers.AcceptLanguage.ToString());
        if (!string.IsNullOrWhiteSpace(model.Widget.ContentSecurityPolicy))
        {
            Response.Headers["Content-Security-Policy"] = model.Widget.ContentSecurityPolicy;
        }

        return View("~/Views/PublicLanding/Concierge.cshtml", model);
    }

    private async Task<IActionResult> RedirectBranchAsync(string surfaceKey, string branchId, CancellationToken cancellationToken, string? contextId = null)
    {
        try
        {
            bool authenticated = await TryIsAuthenticatedAsync(cancellationToken);
            ConciergeRedirectResolution resolution = _concierge.ResolveBranchRedirect(
                surfaceKey,
                branchId,
                authenticated,
                Request.Query["locale"].ToString(),
                Request.Headers.AcceptLanguage.ToString(),
                contextId);
            return Redirect(resolution.RedirectHref);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    private async Task<bool> TryIsAuthenticatedAsync(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
            return true;
        }
        catch
        {
            return false;
        }
    }

    private async Task<SiteChromeViewModel> BuildChromeAsync(
        string title,
        string description,
        string currentPath,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return _chrome.BuildAuthenticatedChrome(title, description, currentPath, user.DisplayName, user.Email);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Falling back to public chrome while rendering concierge surface {CurrentPath}.", currentPath);
            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
    }

    private string? ResolvePublicationReturnRoute(string? publicationId)
    {
        if (string.IsNullOrWhiteSpace(publicationId))
        {
            return null;
        }

        return _publicCreatorDiscovery.GetDiscoverable(publicationId) is null
            ? null
            : $"/artifacts/publications/{Uri.EscapeDataString(publicationId)}";
    }

    private static string? NormalizeInviteCode(string? code)
        => string.IsNullOrWhiteSpace(code) ? null : code.Trim().ToUpperInvariant();

    private static string ResolveInviteContinuationRoute(string? inviteCode, bool authenticated)
    {
        if (authenticated)
        {
            return "/account/work#community-op-invites";
        }

        Dictionary<string, string?> nextQuery = new(StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(inviteCode))
        {
            nextQuery["code"] = inviteCode;
        }

        string next = nextQuery.Count == 0
            ? "/join/concierge"
            : QueryHelpers.AddQueryString("/join/concierge", nextQuery);
        return "/signup?next=" + Uri.EscapeDataString(next);
    }
}
