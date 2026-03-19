using System.Net;
using System.Text;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class AuthController : ControllerBase
{
    private readonly HubBrowserAuthService _browserAuth;
    private readonly HubIdentityClient _identity;
    private readonly PublicLandingService _landing;

    public AuthController(HubBrowserAuthService browserAuth, HubIdentityClient identity, PublicLandingService landing)
    {
        _browserAuth = browserAuth;
        _identity = identity;
        _landing = landing;
    }

    [HttpGet("/login")]
    [Produces("text/html")]
    public async Task<IActionResult> LoginPage([FromQuery] string? next, CancellationToken cancellationToken)
    {
        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        if (await TryIsAuthenticatedAsync(cancellationToken))
        {
            return Redirect(nextPath);
        }

        return Content(RenderAuthPage("Sign In", "Sign in to unlock follows, account settings, and the bounded participation console.", nextPath, createAccount: false), "text/html");
    }

    [HttpGet("/signup")]
    [Produces("text/html")]
    public async Task<IActionResult> SignupPage([FromQuery] string? next, CancellationToken cancellationToken)
    {
        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        if (await TryIsAuthenticatedAsync(cancellationToken))
        {
            return Redirect(nextPath);
        }

        return Content(RenderAuthPage("Create Account", "The first wave is intentionally boring: email-first browser entry now, Google when provider credentials are configured.", nextPath, createAccount: true), "text/html");
    }

    [HttpPost("/auth/email/start")]
    [Consumes("application/x-www-form-urlencoded")]
    [Produces("text/html")]
    public async Task<IActionResult> StartEmail([FromForm] string? email, [FromForm] string? displayName, [FromForm] string? next, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            return BadRequest("email is required.");
        }

        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        var started = await _browserAuth.StartEmailEntryAsync(email, displayName, nextPath, cancellationToken);
        var callback = $"/auth/email/callback?ticket={WebUtility.UrlEncode(started.TicketId)}&next={WebUtility.UrlEncode(nextPath)}";
        var previewFallback = string.Equals(started.DeliveryMode, "preview_inline_link", StringComparison.OrdinalIgnoreCase);
        var deliveryPanel = previewFallback
            ? $"""
  <p><a class="cta" href="{EncodeHref(callback)}">Continue with preview magic link</a></p>
  <p><a class="inline-link" href="/login?next={EncodeHref(nextPath)}">Start over</a></p>
"""
            : """
  <p>Open your inbox and use the sign-in link there.</p>
  <p><a class="inline-link" href="/login?next=/home">Return to sign in</a></p>
""";
        var body = $$"""
<section class="panel prose">
  <h2>Check your email</h2>
  <p>{{Encode(started.PreviewNote)}}</p>
  <ul>
    <li>Email: {{Encode(started.Email)}}</li>
    <li>Display name: {{Encode(started.DisplayName)}}</li>
    <li>Expires: {{Encode(started.ExpiresAtUtc.ToString("u"))}}</li>
  </ul>
  {{deliveryPanel}}
</section>
""";
        return Content(RenderShell("Email Entry", "Email-first entry is the current boring fallback until richer provider adapters are fully wired.", body), "text/html");
    }

    [HttpGet("/auth/email/callback")]
    public async Task<IActionResult> CompleteEmail([FromQuery] string? ticket, [FromQuery] string? next, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(ticket))
        {
            return BadRequest("ticket is required.");
        }

        var session = await _browserAuth.CompleteEmailEntryAsync(ticket, cancellationToken);
        _browserAuth.WriteCookie(Response, session);
        return Redirect(HubBrowserAuthService.SanitizeNextPath(next));
    }

    [HttpGet("/auth/google/start")]
    [Produces("text/html")]
    public ContentResult GoogleStart([FromQuery] string? next)
    {
        var nextPath = HubBrowserAuthService.SanitizeNextPath(next);
        var body = $$"""
<section class="panel prose">
  <h2>Google sign-in is not live in this build yet</h2>
  <p>Design allows Google as the next mainstream bootstrap, but this host still needs real provider credentials and callback configuration before the route can become active.</p>
  <p><a class="cta" href="/login?next={{EncodeHref(nextPath)}}">Use email-first sign in instead</a></p>
</section>
""";
        return Content(RenderShell("Google Sign-In", "The route exists so the auth story is explicit, but it should not pretend the adapter is already live.", body), "text/html");
    }

    [HttpGet("/auth/google/callback")]
    [Produces("text/html")]
    public ContentResult GoogleCallback()
    {
        var body = """
<section class="panel prose">
  <h2>Google callback is not active yet</h2>
  <p>This callback route exists so the public auth map is complete. It will stay honest until the real provider adapter is configured.</p>
  <p><a class="cta" href="/login?next=/home">Return to sign in</a></p>
</section>
""";
        return Content(RenderShell("Google Callback", "Provider routes must not overpromise their readiness.", body), "text/html");
    }

    [HttpGet("/logout")]
    public async Task<IActionResult> Logout(CancellationToken cancellationToken)
    {
        await _browserAuth.RevokeCookieSessionAsync(Request, cancellationToken);
        _browserAuth.ClearCookie(Response);
        return Redirect("/");
    }

    private async Task<bool> TryIsAuthenticatedAsync(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
            return true;
        }
        catch (HubRequestAuthException)
        {
            return false;
        }
    }

    private string RenderAuthPage(string title, string lead, string nextPath, bool createAccount)
    {
        var primaryCta = createAccount ? "Create account" : "Sign in";
        var body = $$"""
<section class="panel prose">
  <h2>{{Encode(title)}}</h2>
  <p>{{Encode(lead)}}</p>
  <form method="post" action="/auth/email/start" class="stack">
    <input type="hidden" name="next" value="{{Encode(nextPath)}}" />
    <label for="email">Email</label>
    <input id="email" name="email" type="email" placeholder="runner@example.com" required />
    <label for="displayName">Display name</label>
    <input id="displayName" name="displayName" placeholder="Runner" />
    <button class="cta" type="submit">{{Encode(primaryCta)}} with email</button>
  </form>
</section>
<section class="panel prose">
  <h2>What is live now</h2>
  <ul>
    <li>Email-first entry for the hosted shell</li>
    <li>Account, home, and participation pages behind a browser session cookie</li>
    <li>Google is allowed next, but this host should not pretend it is active before credentials exist</li>
  </ul>
  <p><a class="inline-link" href="/auth/google/start?next={{EncodeHref(nextPath)}}">See Google sign-in status</a></p>
</section>
""";
        return RenderShell(title, lead, body);
    }

    private string RenderShell(string title, string lead, string body)
    {
        var surface = _landing.LoadSurface();
        var nav = string.Join("", surface.PublicRoutes.Select(route => $"""<a href="{EncodeHref(route.Path)}">{Encode(route.Title)}</a>"""));
        return $$"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{Encode(title)}} · Chummer</title>
  <style>
    :root {
      --bg: #efe6d2;
      --paper: rgba(255, 251, 242, 0.82);
      --ink: #1a1712;
      --muted: #665d52;
      --accent: #125a58;
      --warm: #8d5932;
      --line: rgba(26, 23, 18, 0.12);
      --shadow: 0 18px 40px rgba(26, 23, 18, 0.08);
    }
    * { box-sizing: border-box; }
    body { margin: 0; color: var(--ink); background: linear-gradient(180deg, #f5eedf 0%, var(--bg) 55%, #e7dac0 100%); font-family: Georgia, \"Iowan Old Style\", \"Palatino Linotype\", serif; }
    a { color: inherit; text-decoration: none; }
    .shell { max-width: 980px; margin: 0 auto; padding: 24px 18px 64px; }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 18px; margin-bottom: 22px; padding: 14px 18px; border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,0.72); box-shadow: var(--shadow); }
    .brand { font-size: 1.1rem; letter-spacing: 0.08em; text-transform: uppercase; }
    .nav { display: flex; flex-wrap: wrap; gap: 14px; color: var(--muted); font-size: 0.95rem; }
    .intro { margin: 0 0 22px; color: var(--muted); max-width: 62ch; }
    .panel { background: var(--paper); border: 1px solid var(--line); border-radius: 24px; box-shadow: var(--shadow); padding: 18px 20px; margin-bottom: 18px; }
    .prose h2 { margin-top: 0; }
    .prose p, .prose li { color: var(--muted); }
    .stack { display: grid; gap: 10px; }
    label { font-weight: 600; }
    input { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(26, 23, 18, 0.18); background: rgba(255,255,255,0.92); }
    .cta, .inline-link { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 11px 16px; border-radius: 999px; background: var(--accent); color: white; border: 0; cursor: pointer; }
    .inline-link { background: var(--warm); }
    @media (max-width: 860px) { .topbar { border-radius: 22px; align-items: flex-start; flex-direction: column; } }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">Chummer.run</div>
      <nav class="nav">{{nav}}</nav>
    </header>
    <p class="intro">{{Encode(lead)}}</p>
    {{body}}
  </main>
</body>
</html>
""";
    }

    private static string Encode(string value) => WebUtility.HtmlEncode(value);

    private static string EncodeHref(string value) => WebUtility.HtmlEncode(value);
}
