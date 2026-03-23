using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.WebUtilities;

namespace Chummer.Run.Api.Services;

public sealed record GoogleAuthChallenge(
    string RedirectUrl,
    string StateCookieValue);

public sealed record GoogleMergeCandidate(
    string ExistingDisplayName,
    string VerifiedEmail,
    string NextPath,
    string MergeToken);

public sealed record GoogleAuthCompletionResult(
    IdentitySessionIssueResponse? Session,
    string NextPath,
    string? ErrorTitle = null,
    string? ErrorDetail = null,
    GoogleMergeCandidate? MergeCandidate = null);

public static class HubGoogleAuthConstants
{
    public const string StateCookieName = "chummer_google_auth_state";
}

public sealed class HubGoogleAuthService
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly HubBrowserAuthService _browserAuth;
    private readonly IdentityLinkService _links;
    private readonly AccountService _accounts;
    private readonly IDataProtector _stateProtector;
    private readonly IDataProtector _mergeProtector;
    private readonly ILogger<HubGoogleAuthService> _logger;
    private readonly IHostEnvironment _environment;

    public HubGoogleAuthService(
        HttpClient httpClient,
        IConfiguration configuration,
        HubBrowserAuthService browserAuth,
        IdentityLinkService links,
        AccountService accounts,
        IDataProtectionProvider dataProtectionProvider,
        ILogger<HubGoogleAuthService> logger,
        IHostEnvironment environment)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _browserAuth = browserAuth;
        _links = links;
        _accounts = accounts;
        _stateProtector = dataProtectionProvider.CreateProtector("chummer.hub.google.state");
        _mergeProtector = dataProtectionProvider.CreateProtector("chummer.hub.google.merge");
        _logger = logger;
        _environment = environment;
    }

    private string ClientId => _configuration["GOOGLE_OIDC_CLIENT_ID"]?.Trim() ?? string.Empty;
    private string ClientSecret => _configuration["GOOGLE_OIDC_CLIENT_SECRET"]?.Trim() ?? string.Empty;
    private string AuthorizationEndpoint => _configuration["GOOGLE_OIDC_AUTHORIZATION_ENDPOINT"]?.Trim() ?? "https://accounts.google.com/o/oauth2/v2/auth";
    private string TokenEndpoint => _configuration["GOOGLE_OIDC_TOKEN_ENDPOINT"]?.Trim() ?? "https://oauth2.googleapis.com/token";
    private string UserInfoEndpoint => _configuration["GOOGLE_OIDC_USERINFO_ENDPOINT"]?.Trim() ?? "https://openidconnect.googleapis.com/v1/userinfo";
    private bool CookieSecureDefault => !_environment.IsDevelopment();

    public bool IsConfigured()
        => !string.IsNullOrWhiteSpace(ClientId) && !string.IsNullOrWhiteSpace(ClientSecret);

    public string? DisabledReason()
        => IsConfigured()
            ? null
            : "Google sign-in is unavailable on this host because the OIDC environment variables are missing.";

    public void ValidateProductionReadiness()
    {
        if (_environment.IsProduction() && !IsConfigured())
        {
            throw new InvalidOperationException("Google OIDC must be configured before starting Hub in Production.");
        }
    }

    public GoogleAuthChallenge CreateChallenge(HttpRequest request, string nextPath)
        => CreateChallengeInternal(request, nextPath, linkSubjectId: null);

    public GoogleAuthChallenge CreateLinkChallenge(HttpRequest request, string linkSubjectId, string nextPath)
        => CreateChallengeInternal(request, nextPath, AccountService.NormalizeRequired(linkSubjectId, nameof(linkSubjectId)));

    private GoogleAuthChallenge CreateChallengeInternal(HttpRequest request, string nextPath, string? linkSubjectId)
    {
        if (!IsConfigured())
        {
            throw new InvalidOperationException("Google sign-in is not configured for this host.");
        }

        var attempt = new GoogleAuthAttempt(
            State: CreateOpaqueToken(24),
            CodeVerifier: CreateOpaqueToken(48),
            Nonce: CreateOpaqueToken(24),
            NextPath: HubBrowserAuthService.SanitizeNextPath(nextPath),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            RedirectUri: ResolveRedirectUri(request),
            LinkSubjectId: linkSubjectId);

        var challenge = QueryHelpers.AddQueryString(
            AuthorizationEndpoint,
            new Dictionary<string, string?>
            {
                ["client_id"] = ClientId,
                ["redirect_uri"] = attempt.RedirectUri,
                ["response_type"] = "code",
                ["scope"] = "openid profile email",
                ["state"] = attempt.State,
                ["nonce"] = attempt.Nonce,
                ["code_challenge"] = CreateCodeChallenge(attempt.CodeVerifier),
                ["code_challenge_method"] = "S256",
                ["prompt"] = "select_account"
            });

        return new GoogleAuthChallenge(
            RedirectUrl: challenge,
            StateCookieValue: _stateProtector.Protect(JsonSerializer.Serialize(attempt)));
    }

    public Task<GoogleAuthCompletionResult> CompleteAsync(HttpRequest request, IQueryCollection query, CancellationToken cancellationToken)
        => CompleteInternalAsync(request, query, mergeSubjectId: null, cancellationToken);

    public async Task<GoogleAuthCompletionResult> ConfirmMergeAsync(HttpRequest request, string mergeToken, CancellationToken cancellationToken)
    {
        GoogleMergePayload payload;
        try
        {
            payload = JsonSerializer.Deserialize<GoogleMergePayload>(_mergeProtector.Unprotect(mergeToken))
                ?? throw new InvalidOperationException("Google merge token payload was empty.");
        }
        catch (Exception ex) when (ex is CryptographicException or JsonException or InvalidOperationException)
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: "/login?next=/home",
                ErrorTitle: "Google sign-in could not be resumed",
                ErrorDetail: "The account-link confirmation expired or was not valid anymore.");
        }

        if (payload.ExpiresAtUtc <= DateTimeOffset.UtcNow)
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: "/login?next=/home",
                ErrorTitle: "Google sign-in confirmation expired",
                ErrorDetail: "Start the Google sign-in flow again and confirm the merge from the fresh callback.");
        }

        return await CompleteInternalAsync(request, QueryCollection.Empty, payload.SubjectId, cancellationToken, payload.Claims);
    }

    public CookieOptions BuildStateCookie(HttpRequest request, DateTimeOffset expiresAtUtc)
        => new()
        {
            HttpOnly = true,
            Secure = request.IsHttps || CookieSecureDefault,
            SameSite = SameSiteMode.Lax,
            Expires = expiresAtUtc.UtcDateTime,
            IsEssential = true,
            Path = "/"
        };

    private async Task<GoogleAuthCompletionResult> CompleteInternalAsync(
        HttpRequest request,
        IQueryCollection query,
        string? mergeSubjectId,
        CancellationToken cancellationToken,
        GoogleIdentityClaims? preloadedClaims = null)
    {
        if (!IsConfigured())
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: "/login?next=/home",
                ErrorTitle: "Google sign-in is unavailable",
                ErrorDetail: DisabledReason());
        }

        GoogleIdentityClaims claims;
        string nextPath;
        string? linkSubjectId = null;
        if (preloadedClaims is not null)
        {
            claims = preloadedClaims;
            nextPath = HubBrowserAuthService.SanitizeNextPath(request.Query["next"]);
        }
        else
        {
            if (!string.IsNullOrWhiteSpace(query["error"]))
            {
                return new GoogleAuthCompletionResult(
                    Session: null,
                    NextPath: "/login?next=/home",
                    ErrorTitle: "Google sign-in was cancelled",
                    ErrorDetail: query["error_description"].ToString() is { Length: > 0 } description
                        ? description
                        : "Google returned an authorization error before Chummer could complete the sign-in.");
            }

            if (!request.Cookies.TryGetValue(HubGoogleAuthConstants.StateCookieName, out var protectedState)
                || string.IsNullOrWhiteSpace(protectedState))
            {
                return new GoogleAuthCompletionResult(
                    Session: null,
                    NextPath: "/login?next=/home",
                    ErrorTitle: "Google sign-in state was missing",
                    ErrorDetail: "Start the Google sign-in flow from Chummer again so the PKCE and state cookie can be recreated.");
            }

            GoogleAuthAttempt attempt;
            try
            {
                attempt = JsonSerializer.Deserialize<GoogleAuthAttempt>(_stateProtector.Unprotect(protectedState))
                    ?? throw new InvalidOperationException("Google auth attempt payload was empty.");
            }
            catch (Exception ex) when (ex is CryptographicException or JsonException or InvalidOperationException)
            {
                return new GoogleAuthCompletionResult(
                    Session: null,
                    NextPath: "/login?next=/home",
                    ErrorTitle: "Google sign-in state could not be read",
                    ErrorDetail: "The authorization state cookie was not valid anymore. Start the flow again.");
            }

            if (attempt.CreatedAtUtc.AddMinutes(10) <= DateTimeOffset.UtcNow)
            {
                return new GoogleAuthCompletionResult(
                    Session: null,
                    NextPath: "/login?next=/home",
                    ErrorTitle: "Google sign-in expired",
                    ErrorDetail: "The authorization handshake took too long. Start the Google sign-in flow again.");
            }

            if (!string.Equals(attempt.State, query["state"], StringComparison.Ordinal))
            {
                return new GoogleAuthCompletionResult(
                    Session: null,
                    NextPath: "/login?next=/home",
                    ErrorTitle: "Google sign-in state did not match",
                    ErrorDetail: "Chummer rejected the callback because the `state` value no longer matched the browser handshake.");
            }

            var code = query["code"].ToString();
            if (string.IsNullOrWhiteSpace(code))
            {
                return new GoogleAuthCompletionResult(
                    Session: null,
                    NextPath: "/login?next=/home",
                    ErrorTitle: "Google sign-in callback was incomplete",
                    ErrorDetail: "Google did not return an authorization code.");
            }

            claims = await ExchangeForClaimsAsync(code, attempt, cancellationToken);
            nextPath = attempt.NextPath;
            linkSubjectId = AccountService.NormalizeOptional(attempt.LinkSubjectId);
        }

        if (!claims.EmailVerified)
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: "/login?next=/home",
                ErrorTitle: "Google email verification is required",
                ErrorDetail: "Chummer only accepts Google identities that come back with a verified email address.");
        }

        if (!string.IsNullOrWhiteSpace(mergeSubjectId))
        {
            return await IssueSessionForSubjectAsync(mergeSubjectId, claims, HubBrowserAuthService.SanitizeNextPath(request.Query["next"], claims.NextPathHint ?? "/home"), cancellationToken);
        }

        if (!string.IsNullOrWhiteSpace(linkSubjectId))
        {
            return await LinkGoogleToExistingUserAsync(linkSubjectId, claims, nextPath, cancellationToken);
        }

        var linkedGoogle = _links.FindLinkedIdentity("google", claims.Subject);
        if (linkedGoogle is not null)
        {
            var linkedUser = _accounts.GetById(linkedGoogle.UserId);
            if (linkedUser is null)
            {
                _logger.LogWarning("Google identity {ProviderSubject} was linked to missing user {UserId}.", claims.Subject, linkedGoogle.UserId);
            }
            else
            {
                return await IssueSessionForSubjectAsync(linkedUser.SubjectId, claims, nextPath, cancellationToken);
            }
        }

        var emailSubjectId = IdentitySubjectDerivation.FromEmail(claims.Email);
        var emailUser = _accounts.GetBySubject(emailSubjectId);
        if (emailUser is not null)
        {
            var conflictingGoogle = _links.FindLinkedIdentityForUser(emailUser.UserId, "google");
            if (conflictingGoogle is not null
                && !string.Equals(conflictingGoogle.ProviderSubject, claims.Subject, StringComparison.OrdinalIgnoreCase))
            {
                return new GoogleAuthCompletionResult(
                    Session: null,
                    NextPath: "/login?next=/home",
                    ErrorTitle: "Google account conflict detected",
                    ErrorDetail: "This verified Google email maps to an existing Chummer account that is already linked to a different Google sign-in.");
            }

            var mergeToken = _mergeProtector.Protect(JsonSerializer.Serialize(new GoogleMergePayload(
                SubjectId: emailUser.SubjectId,
                NextPath: nextPath,
                ExpiresAtUtc: DateTimeOffset.UtcNow.AddMinutes(10),
                Claims: claims with { NextPathHint = nextPath })));
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                MergeCandidate: new GoogleMergeCandidate(
                    ExistingDisplayName: emailUser.DisplayName,
                    VerifiedEmail: claims.Email,
                    NextPath: nextPath,
                    MergeToken: mergeToken));
        }

        return await IssueSessionForSubjectAsync(IdentitySubjectDerivation.FromGoogleSubject(claims.Subject), claims, nextPath, cancellationToken);
    }

    private async Task<GoogleAuthCompletionResult> LinkGoogleToExistingUserAsync(
        string linkSubjectId,
        GoogleIdentityClaims claims,
        string nextPath,
        CancellationToken cancellationToken)
    {
        var currentUser = _accounts.GetBySubject(linkSubjectId) ?? _accounts.EnsureUser(linkSubjectId);
        var linkedGoogle = _links.FindLinkedIdentity("google", claims.Subject);
        if (linkedGoogle is not null
            && !string.Equals(linkedGoogle.UserId, currentUser.UserId, StringComparison.OrdinalIgnoreCase))
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                ErrorTitle: "Google account already linked elsewhere",
                ErrorDetail: "That Google sign-in already belongs to a different Chummer account. Sign in with it directly if that is the account you want.");
        }

        var emailSubjectId = IdentitySubjectDerivation.FromEmail(claims.Email);
        var emailUser = _accounts.GetBySubject(emailSubjectId);
        if (emailUser is not null
            && !string.Equals(emailUser.UserId, currentUser.UserId, StringComparison.OrdinalIgnoreCase))
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                ErrorTitle: "Verified Google email belongs to another account",
                ErrorDetail: "That verified Google email already maps to a different Chummer account, so Hub will not silently merge or relink it here.");
        }

        return await IssueSessionForSubjectAsync(linkSubjectId, claims, nextPath, cancellationToken);
    }

    private async Task<GoogleAuthCompletionResult> IssueSessionForSubjectAsync(
        string subjectId,
        GoogleIdentityClaims claims,
        string nextPath,
        CancellationToken cancellationToken)
    {
        var session = await _browserAuth.IssueSessionAsync(
            subjectId,
            displayName: claims.DisplayName,
            email: claims.Email,
            requestedRoles: new[] { "player" },
            cancellationToken);

        _accounts.EnsureUser(subjectId, claims.DisplayName, claims.Email);
        _links.LinkExternalIdentity(new LinkExternalIdentityRequest(
            SubjectId: subjectId,
            Provider: "google",
            ProviderSubject: claims.Subject,
            DisplayLabel: claims.Email,
            MakePrimary: true));

        return new GoogleAuthCompletionResult(
            Session: session,
            NextPath: HubBrowserAuthService.SanitizeNextPath(nextPath));
    }

    private async Task<GoogleIdentityClaims> ExchangeForClaimsAsync(
        string code,
        GoogleAuthAttempt attempt,
        CancellationToken cancellationToken)
    {
        using var tokenResponse = await _httpClient.PostAsync(
            TokenEndpoint,
            new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["code"] = code,
                ["client_id"] = ClientId,
                ["client_secret"] = ClientSecret,
                ["redirect_uri"] = attempt.RedirectUri,
                ["grant_type"] = "authorization_code",
                ["code_verifier"] = attempt.CodeVerifier
            }),
            cancellationToken);

        if (!tokenResponse.IsSuccessStatusCode)
        {
            var detail = await tokenResponse.Content.ReadAsStringAsync(cancellationToken);
            throw new InvalidOperationException($"Google token exchange failed: {(int)tokenResponse.StatusCode} {detail}");
        }

        var tokens = await tokenResponse.Content.ReadFromJsonAsync<GoogleTokenResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Google token payload was empty.");
        if (string.IsNullOrWhiteSpace(tokens.AccessToken))
        {
            throw new InvalidOperationException("Google token payload was missing the access token.");
        }

        using var userInfoRequest = new HttpRequestMessage(HttpMethod.Get, UserInfoEndpoint);
        userInfoRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", tokens.AccessToken);
        using var userInfoResponse = await _httpClient.SendAsync(userInfoRequest, cancellationToken);
        if (!userInfoResponse.IsSuccessStatusCode)
        {
            var detail = await userInfoResponse.Content.ReadAsStringAsync(cancellationToken);
            throw new InvalidOperationException($"Google userinfo failed: {(int)userInfoResponse.StatusCode} {detail}");
        }

        var userInfo = await userInfoResponse.Content.ReadFromJsonAsync<GoogleUserInfoResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Google userinfo payload was empty.");
        if (string.IsNullOrWhiteSpace(userInfo.Sub) || string.IsNullOrWhiteSpace(userInfo.Email))
        {
            throw new InvalidOperationException("Google userinfo did not include the required subject and email fields.");
        }

        return new GoogleIdentityClaims(
            Subject: userInfo.Sub,
            Email: userInfo.Email,
            EmailVerified: userInfo.EmailVerified,
            DisplayName: string.IsNullOrWhiteSpace(userInfo.Name)
                ? userInfo.Email.Split('@')[0]
                : userInfo.Name,
            NextPathHint: null);
    }

    private string ResolveRedirectUri(HttpRequest request)
    {
        var configured = _configuration["GOOGLE_OIDC_REDIRECT_URI"]?.Trim();
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return configured;
        }

        var host = request.Host.HasValue ? request.Host.Value : "localhost";
        return $"{request.Scheme}://{host}/auth/google/callback";
    }

    private static string CreateOpaqueToken(int byteCount)
    {
        return WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(byteCount));
    }

    private static string CreateCodeChallenge(string verifier)
    {
        var bytes = SHA256.HashData(Encoding.ASCII.GetBytes(verifier));
        return WebEncoders.Base64UrlEncode(bytes);
    }

    private sealed record GoogleAuthAttempt(
        string State,
        string CodeVerifier,
        string Nonce,
        string NextPath,
        DateTimeOffset CreatedAtUtc,
        string RedirectUri,
        string? LinkSubjectId);

    private sealed record GoogleMergePayload(
        string SubjectId,
        string NextPath,
        DateTimeOffset ExpiresAtUtc,
        GoogleIdentityClaims Claims);

    private sealed record GoogleTokenResponse(
        [property: JsonPropertyName("access_token")] string AccessToken,
        [property: JsonPropertyName("id_token")] string? IdToken,
        [property: JsonPropertyName("token_type")] string TokenType,
        [property: JsonPropertyName("expires_in")] int ExpiresIn);

    private sealed record GoogleUserInfoResponse(
        [property: JsonPropertyName("sub")] string Sub,
        [property: JsonPropertyName("email")] string Email,
        [property: JsonPropertyName("email_verified")] bool EmailVerified,
        [property: JsonPropertyName("name")] string? Name);

    private sealed record GoogleIdentityClaims(
        string Subject,
        string Email,
        bool EmailVerified,
        string DisplayName,
        string? NextPathHint);
}
