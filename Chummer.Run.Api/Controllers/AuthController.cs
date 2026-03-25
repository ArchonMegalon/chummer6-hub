using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
public sealed class AuthController : Controller
{
    private readonly HubBrowserAuthService _browserAuth;
    private readonly HubIdentityClient _identity;
    private readonly PublicLandingService _landing;
    private readonly HubPageChromeService _chrome;
    private readonly HubGoogleAuthService _google;
    private readonly AccountService _accounts;
    private readonly IdentityLinkService _links;
    private readonly HubEmailLinkVerificationService _emailLinks;
    private readonly ILogger<AuthController> _logger;

    public AuthController(
        HubBrowserAuthService browserAuth,
        HubIdentityClient identity,
        PublicLandingService landing,
        HubPageChromeService chrome,
        HubGoogleAuthService google,
        AccountService accounts,
        IdentityLinkService links,
        HubEmailLinkVerificationService emailLinks,
        ILogger<AuthController> logger)
    {
        _browserAuth = browserAuth;
        _identity = identity;
        _landing = landing;
        _chrome = chrome;
        _google = google;
        _accounts = accounts;
        _links = links;
        _emailLinks = emailLinks;
        _logger = logger;
    }

    [HttpGet("/login")]
    [Produces("text/html")]
    public async Task<IActionResult> LoginPage([FromQuery] string? next, CancellationToken cancellationToken)
    {
        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        var sessionState = await ResolveAuthEntrySessionStateAsync(cancellationToken);
        if (sessionState == AuthEntrySessionState.Authenticated)
        {
            return Redirect(nextPath);
        }
        if (sessionState == AuthEntrySessionState.Unavailable)
        {
            return BuildAuthMessage(
                chromeTitle: "Sign-in unavailable",
                chromeDescription: "Hub could not confirm the current browser session right now.",
                currentPath: "/login",
                heading: "Sign-in is unavailable right now",
                supportLine: "Chummer could not confirm the current browser session. Try again in a moment.",
                notice: null,
                primaryLabel: "Return home",
                primaryHref: "/",
                secondaryLabel: "Try sign-in again",
                secondaryHref: $"/login?next={Uri.EscapeDataString(nextPath)}");
        }

        return View("~/Views/Auth/Entry.cshtml", BuildAuthModel(
            heading: "Sign in",
            supportLine: "Return to your account, linked downloads, and current release in one browser flow.",
            nextPath,
            createAccount: false));
    }

    [HttpGet("/signup")]
    [Produces("text/html")]
    public async Task<IActionResult> SignupPage([FromQuery] string? next, CancellationToken cancellationToken)
    {
        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        var sessionState = await ResolveAuthEntrySessionStateAsync(cancellationToken);
        if (sessionState == AuthEntrySessionState.Authenticated)
        {
            return Redirect(nextPath);
        }
        if (sessionState == AuthEntrySessionState.Unavailable)
        {
            return BuildAuthMessage(
                chromeTitle: "Account creation unavailable",
                chromeDescription: "Hub could not confirm the current browser session right now.",
                currentPath: "/signup",
                heading: "Account creation is unavailable right now",
                supportLine: "Chummer could not confirm the current browser session. Try again in a moment.",
                notice: null,
                primaryLabel: "Return home",
                primaryHref: "/",
                secondaryLabel: "Try account creation again",
                secondaryHref: $"/signup?next={Uri.EscapeDataString(nextPath)}");
        }

        return View("~/Views/Auth/Entry.cshtml", BuildAuthModel(
            heading: "Create account",
            supportLine: "Create the account that unlocks preview installs, linked devices, and support follow-up.",
            nextPath,
            createAccount: true));
    }

    [HttpPost("/auth/email/start")]
    [ValidateAntiForgeryToken]
    [Consumes("application/x-www-form-urlencoded")]
    [Produces("text/html")]
    public async Task<IActionResult> StartEmail([FromForm] string? email, [FromForm] string? displayName, [FromForm] string? next, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            return BadRequest("email is required.");
        }

        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        var started = default(Chummer.Run.Contracts.Identity.EmailAuthStartResponse)!;
        try
        {
            started = await _browserAuth.StartEmailEntryAsync(email, displayName, nextPath, cancellationToken);
        }
        catch (HubBrowserAuthUnavailableException ex)
        {
            _logger.LogWarning(ex, "Email sign-in could not be started for {Email}.", email);
            return BuildAuthMessage(
                chromeTitle: "Email sign-in unavailable",
                chromeDescription: "The email sign-in flow could not be started right now.",
                currentPath: "/login",
                heading: "Email sign-in is unavailable",
                supportLine: "Chummer could not start the email sign-in step right now. Try again in a moment or use Google if it is available on this host.",
                notice: null,
                primaryLabel: _google.IsConfigured() ? "Continue with Google" : "Return to sign in",
                primaryHref: _google.IsConfigured()
                    ? $"/auth/google/start?next={Uri.EscapeDataString(nextPath)}"
                    : $"/login?next={Uri.EscapeDataString(nextPath)}",
                secondaryLabel: "Use a different email",
                secondaryHref: $"/login?next={Uri.EscapeDataString(nextPath)}");
        }

        var callback = $"/auth/email/callback?ticket={Uri.EscapeDataString(started.TicketId)}&next={Uri.EscapeDataString(nextPath)}";
        var model = new AuthMessagePageViewModel(
            Chrome: _chrome.BuildPublicChrome("Check your email", "Finish the magic-link step and come back to your account.", "/login"),
            Heading: "Check your email",
            SupportLine: started.PreviewNote,
            Notice: $"Email: {started.Email} · expires {started.ExpiresAtUtc:yyyy-MM-dd HH:mm} UTC",
            PrimaryLabel: string.Equals(started.DeliveryMode, "preview_inline_link", StringComparison.OrdinalIgnoreCase)
                ? "Continue with preview link"
                : "Return to sign in",
            PrimaryHref: string.Equals(started.DeliveryMode, "preview_inline_link", StringComparison.OrdinalIgnoreCase)
                ? callback
                : $"/login?next={Uri.EscapeDataString(nextPath)}",
            SecondaryLabel: "Use a different email",
            SecondaryHref: $"/login?next={Uri.EscapeDataString(nextPath)}");
        return View("~/Views/Auth/Message.cshtml", model);
    }

    [HttpGet("/auth/email/callback")]
    public async Task<IActionResult> CompleteEmail([FromQuery] string? ticket, [FromQuery] string? next, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(ticket))
        {
            return BadRequest("ticket is required.");
        }

        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        var session = default(Chummer.Run.Contracts.Identity.IdentitySessionIssueResponse)!;
        try
        {
            session = await _browserAuth.CompleteEmailEntryAsync(ticket, cancellationToken);
        }
        catch (HubBrowserAuthUnavailableException ex)
        {
            _logger.LogWarning(ex, "Email sign-in callback could not be completed for next path {NextPath}.", nextPath);
            return BuildAuthMessage(
                chromeTitle: "Email sign-in unavailable",
                chromeDescription: "The email sign-in callback could not be completed right now.",
                currentPath: "/login",
                heading: "Email sign-in could not be completed",
                supportLine: "Chummer could not finish the email sign-in step right now. Start again from sign in and use a fresh link.",
                notice: null,
                primaryLabel: "Return to sign in",
                primaryHref: $"/login?next={Uri.EscapeDataString(nextPath)}",
                secondaryLabel: "Create account",
                secondaryHref: $"/signup?next={Uri.EscapeDataString(nextPath)}");
        }

        _browserAuth.WriteCookie(Request, Response, session);
        var isRecoveryVerification = nextPath.StartsWith("/auth/email/link/callback", StringComparison.OrdinalIgnoreCase);
        if (!isRecoveryVerification)
        {
            _accounts.EnsureUser(session.SubjectId, session.DisplayName, session.Email);
            if (!string.IsNullOrWhiteSpace(session.Email))
            {
                var emailLink = _links.LinkEmail(new LinkEmailIdentityRequest(
                    SubjectId: session.SubjectId,
                    Email: session.Email,
                    MakePrimary: true));
                _links.ConfirmIdentityLink(new ConfirmIdentityLinkRequest(session.SubjectId, emailLink.IdentityLinkId));
            }
        }

        return Redirect(nextPath);
    }

    [HttpGet("/auth/email/link/callback")]
    public async Task<IActionResult> CompleteRecoveryEmailLink([FromQuery] string? token, CancellationToken cancellationToken)
    {
        HubEmailLinkVerificationPayload payload;
        try
        {
            payload = _emailLinks.ReadVerificationToken(token ?? string.Empty);
        }
        catch (InvalidOperationException)
        {
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Recovery email verification expired", "The recovery-email verification token was missing, expired, or invalid.", "/account"),
                Heading: "Recovery email verification expired",
                SupportLine: "Start the recovery-email step again from your signed-in account settings.",
                Notice: null,
                PrimaryLabel: "Open account",
                PrimaryHref: "/account",
                SecondaryLabel: "Return home",
                SecondaryHref: "/home"));
        }

        AuthenticatedHubSubject verifiedEmailSubject;
        try
        {
            verifiedEmailSubject = await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Recovery email verification failed", "The verification email was opened without an active verified-email session.", "/login"),
                Heading: "Recovery email verification failed",
                SupportLine: "Open the verification email again from the same browser so Chummer can finish linking the recovery address.",
                Notice: null,
                PrimaryLabel: "Open account",
                PrimaryHref: "/account",
                SecondaryLabel: "Sign in",
                SecondaryHref: "/login?next=/account"));
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Recovery email verification could not confirm the active identity session.");
            return BuildAuthMessage(
                chromeTitle: "Recovery email unavailable",
                chromeDescription: "The recovery-email verification flow could not confirm the active identity session right now.",
                currentPath: "/account",
                heading: "Recovery email verification is unavailable",
                supportLine: "Chummer could not confirm the active sign-in session for recovery-email verification right now. Start again from Account.",
                notice: null,
                primaryLabel: "Open account",
                primaryHref: "/account",
                secondaryLabel: "Return home",
                secondaryHref: "/home");
        }

        if (!_emailLinks.MatchesVerifiedEmailSubject(payload, verifiedEmailSubject.SubjectId))
        {
            await TryClearBrowserSessionAsync(cancellationToken);
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Recovery email verification failed", "The browser session did not match the recovery email that was verified.", "/account"),
                Heading: "Recovery email verification failed",
                SupportLine: "That verification link was completed under a different email identity than the one Chummer expected.",
                Notice: null,
                PrimaryLabel: "Open account",
                PrimaryHref: "/account",
                SecondaryLabel: "Return home",
                SecondaryHref: "/home"));
        }

        var accountUser = _accounts.GetBySubject(payload.AccountSubjectId) ?? _accounts.EnsureUser(payload.AccountSubjectId);
        var existingEmailLink = _links.FindLinkedIdentity("email", payload.Email);
        if (existingEmailLink is not null
            && !string.Equals(existingEmailLink.UserId, accountUser.UserId, StringComparison.OrdinalIgnoreCase))
        {
            await TryClearBrowserSessionAsync(cancellationToken);
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Recovery email already linked", "That recovery email now belongs to a different Chummer account.", "/account"),
                Heading: "Recovery email already linked",
                SupportLine: "Chummer will not relink that verified email because it is already attached to another account.",
                Notice: null,
                PrimaryLabel: "Open account",
                PrimaryHref: "/account",
                SecondaryLabel: "Return home",
                SecondaryHref: "/home"));
        }

        var linked = _links.LinkEmail(new LinkEmailIdentityRequest(
            SubjectId: payload.AccountSubjectId,
            Email: payload.Email,
            MakePrimary: false));
        _links.ConfirmIdentityLink(new ConfirmIdentityLinkRequest(payload.AccountSubjectId, linked.IdentityLinkId));

        try
        {
            await _browserAuth.RevokeCookieSessionAsync(Request, cancellationToken);
            var restoredSession = await _browserAuth.IssueSessionAsync(
                payload.AccountSubjectId,
                displayName: accountUser.DisplayName,
                email: null,
                requestedRoles: null,
                cancellationToken);
            _browserAuth.WriteCookie(Request, Response, restoredSession);
        }
        catch (HubBrowserAuthUnavailableException ex)
        {
            _logger.LogWarning(ex, "Recovery email verification could not restore the primary Hub session for {SubjectId}.", payload.AccountSubjectId);
            return BuildAuthMessage(
                chromeTitle: "Recovery email unavailable",
                chromeDescription: "The recovery-email verification flow could not finish the signed-in browser session right now.",
                currentPath: "/account",
                heading: "Recovery email verification is unavailable",
                supportLine: "Chummer verified the recovery email but could not finish the signed-in browser session right now. Return to Account and try the final step again.",
                notice: null,
                primaryLabel: "Open account",
                primaryHref: "/account",
                secondaryLabel: "Return home",
                secondaryHref: "/home");
        }

        return Redirect(payload.NextPath);
    }

    [HttpGet("/auth/google/start")]
    public IActionResult GoogleStart([FromQuery] string? next)
    {
        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        if (!_google.IsConfigured())
        {
            var model = new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Google unavailable", _google.DisabledReason() ?? "Google sign-in is unavailable on this host.", "/login"),
                Heading: "Google sign-in is unavailable",
                SupportLine: _google.DisabledReason() ?? "Google sign-in is unavailable on this host.",
                Notice: null,
                PrimaryLabel: "Continue with email",
                PrimaryHref: $"/login?next={Uri.EscapeDataString(nextPath)}",
                SecondaryLabel: "Create account",
                SecondaryHref: $"/signup?next={Uri.EscapeDataString(nextPath)}");
            return View("~/Views/Auth/Message.cshtml", model);
        }

        var challenge = _google.CreateChallenge(Request, nextPath);
        Response.Cookies.Append(
            HubGoogleAuthConstants.StateCookieName,
            challenge.StateCookieValue,
            _google.BuildStateCookie(Request, DateTimeOffset.UtcNow.AddMinutes(10)));
        return Redirect(challenge.RedirectUrl);
    }

    [HttpGet("/auth/google/link")]
    public async Task<IActionResult> GoogleLinkStart([FromQuery] string? next, CancellationToken cancellationToken)
    {
        var nextPath = HubBrowserAuthService.SanitizeNextPath(next, "/account");
        AuthenticatedHubSubject subject;
        try
        {
            subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(nextPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Google account linking could not confirm the current Hub session.");
            return BuildAuthMessage(
                chromeTitle: "Google link unavailable",
                chromeDescription: "Hub could not confirm the current signed-in session for Google linking.",
                currentPath: "/account",
                heading: "Google account linking is unavailable",
                supportLine: "Chummer could not confirm the current signed-in session for Google linking right now. Open Account and try again in a moment.",
                notice: null,
                primaryLabel: "Open account",
                primaryHref: nextPath,
                secondaryLabel: "Return home",
                secondaryHref: "/home");
        }

        if (!_google.IsConfigured())
        {
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Google unavailable", _google.DisabledReason() ?? "Google sign-in is unavailable on this host.", "/account"),
                Heading: "Google sign-in is unavailable",
                SupportLine: _google.DisabledReason() ?? "Google sign-in is unavailable on this host.",
                Notice: null,
                PrimaryLabel: "Open account",
                PrimaryHref: nextPath,
                SecondaryLabel: "Continue with email",
                SecondaryHref: "/account"));
        }

        var challenge = _google.CreateLinkChallenge(Request, subject.SubjectId, nextPath);
        Response.Cookies.Append(
            HubGoogleAuthConstants.StateCookieName,
            challenge.StateCookieValue,
            _google.BuildStateCookie(Request, DateTimeOffset.UtcNow.AddMinutes(10)));
        return Redirect(challenge.RedirectUrl);
    }

    [HttpGet("/auth/google/callback")]
    public async Task<IActionResult> GoogleCallback(CancellationToken cancellationToken)
    {
        GoogleAuthCompletionResult result;
        try
        {
            result = await _google.CompleteAsync(Request, Request.Query, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Google sign-in callback failed.");
            result = new GoogleAuthCompletionResult(
                Session: null,
                NextPath: "/login?next=/home",
                ErrorTitle: "Google sign-in failed",
                ErrorDetail: "Chummer could not complete the Google sign-in handshake right now. Start the flow again in a moment.");
        }

        Response.Cookies.Delete(HubGoogleAuthConstants.StateCookieName, _google.BuildStateCookie(Request, DateTimeOffset.UtcNow));

        if (result.MergeCandidate is not null)
        {
            var mergeModel = new GoogleMergePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Confirm account link", "Google found a verified email that already belongs to a Chummer account.", "/login"),
                ExistingDisplayName: result.MergeCandidate.ExistingDisplayName,
                VerifiedEmail: result.MergeCandidate.VerifiedEmail,
                NextPath: result.MergeCandidate.NextPath,
                MergeToken: result.MergeCandidate.MergeToken);
            return View("~/Views/Auth/GoogleMerge.cshtml", mergeModel);
        }

        if (result.Session is not null)
        {
            _browserAuth.WriteCookie(Request, Response, result.Session);
            return Redirect(result.NextPath);
        }

        return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
            Chrome: _chrome.BuildPublicChrome(result.ErrorTitle ?? "Google sign-in", result.ErrorDetail ?? "Google sign-in did not complete.", "/login"),
            Heading: result.ErrorTitle ?? "Google sign-in failed",
            SupportLine: result.ErrorDetail ?? "Google sign-in did not complete.",
            Notice: null,
            PrimaryLabel: "Continue with email",
            PrimaryHref: $"/login?next={Uri.EscapeDataString(result.NextPath)}",
            SecondaryLabel: "Return to account creation",
            SecondaryHref: $"/signup?next={Uri.EscapeDataString(result.NextPath)}"));
    }

    [HttpPost("/auth/google/merge")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> ConfirmGoogleMerge([FromForm] string? mergeToken, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(mergeToken))
        {
            return BadRequest("mergeToken is required.");
        }

        GoogleAuthCompletionResult result;
        try
        {
            result = await _google.ConfirmMergeAsync(Request, mergeToken, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Google account merge confirmation failed.");
            result = new GoogleAuthCompletionResult(
                Session: null,
                NextPath: "/login?next=/home",
                ErrorTitle: "Google account link failed",
                ErrorDetail: "Chummer could not complete the Google account link right now. Start the flow again in a moment.");
        }

        if (result.Session is not null)
        {
            _browserAuth.WriteCookie(Request, Response, result.Session);
            return Redirect(result.NextPath);
        }

        return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
            Chrome: _chrome.BuildPublicChrome(result.ErrorTitle ?? "Google account link failed", result.ErrorDetail ?? "The Google account could not be linked.", "/login"),
            Heading: result.ErrorTitle ?? "Google account link failed",
            SupportLine: result.ErrorDetail ?? "The Google account could not be linked.",
            Notice: null,
            PrimaryLabel: "Start over",
            PrimaryHref: "/login?next=/home",
            SecondaryLabel: "Use email instead",
            SecondaryHref: "/login?next=/home"));
    }

    [HttpGet("/logout")]
    public IActionResult LogoutRedirect()
        => Redirect("/");

    [HttpPost("/logout")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> Logout(CancellationToken cancellationToken)
    {
        try
        {
            await _browserAuth.RevokeCookieSessionAsync(Request, cancellationToken);
        }
        catch (Exception ex) when (
            ex is HttpRequestException
            or TaskCanceledException
            or InvalidOperationException)
        {
            _logger.LogWarning(ex, "Identity session revoke failed during logout. Clearing the browser cookie locally.");
        }

        _browserAuth.ClearCookie(Request, Response);
        return Redirect("/");
    }

    private async Task<AuthEntrySessionState> ResolveAuthEntrySessionStateAsync(CancellationToken cancellationToken)
    {
        var hasAccessCookie = Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName);
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
            return AuthEntrySessionState.Authenticated;
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            if (hasAccessCookie)
            {
                _browserAuth.ClearCookie(Request, Response);
            }

            return AuthEntrySessionState.Guest;
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Identity check failed while rendering the auth entry page.");
            return hasAccessCookie ? AuthEntrySessionState.Unavailable : AuthEntrySessionState.Guest;
        }
    }

    private ViewResult BuildAuthMessage(
        string chromeTitle,
        string chromeDescription,
        string currentPath,
        string heading,
        string supportLine,
        string? notice,
        string primaryLabel,
        string primaryHref,
        string secondaryLabel,
        string secondaryHref)
        => View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
            Chrome: _chrome.BuildPublicChrome(chromeTitle, chromeDescription, currentPath),
            Heading: heading,
            SupportLine: supportLine,
            Notice: notice,
            PrimaryLabel: primaryLabel,
            PrimaryHref: primaryHref,
            SecondaryLabel: secondaryLabel,
            SecondaryHref: secondaryHref));

    private async Task TryClearBrowserSessionAsync(CancellationToken cancellationToken)
    {
        try
        {
            await _browserAuth.RevokeCookieSessionAsync(Request, cancellationToken);
        }
        catch (HubBrowserAuthUnavailableException ex)
        {
            _logger.LogWarning(ex, "Hub could not revoke the browser session while rendering an auth failure page. Clearing the cookie locally.");
        }

        _browserAuth.ClearCookie(Request, Response);
    }

    private AuthPageViewModel BuildAuthModel(string heading, string supportLine, string nextPath, bool createAccount)
    {
        _landing.LoadSurface();
        return new AuthPageViewModel(
            Chrome: _chrome.BuildPublicChrome(heading, supportLine, createAccount ? "/signup" : "/login"),
            Heading: heading,
            SupportLine: supportLine,
            NextPath: nextPath,
            CreateAccount: createAccount,
            GoogleAvailable: _google.IsConfigured(),
            GoogleUnavailableReason: _google.DisabledReason(),
            GoogleStartHref: $"/auth/google/start?next={Uri.EscapeDataString(nextPath)}");
    }

    private enum AuthEntrySessionState
    {
        Guest,
        Authenticated,
        Unavailable
    }
}
