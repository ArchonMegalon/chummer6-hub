using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net;
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
    bool AccountCreated = false,
    string? ErrorTitle = null,
    string? ErrorDetail = null,
    GoogleMergeCandidate? MergeCandidate = null);

public static class HubGoogleAuthConstants
{
    public const string StateCookieName = "chummer_google_auth_state";
}

public sealed class HubGoogleAuthService
{
    private const string DefaultNextPath = "/home";
    private const int TransientRetryAttempts = 2;
    private const int MaxTrackedStateAttempts = 4;
    private static readonly TimeSpan AuthAttemptLifetime = TimeSpan.FromMinutes(10);
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly HubBrowserAuthService _browserAuth;
    private readonly IdentityLinkService _links;
    private readonly AccountService _accounts;
    private readonly IDataProtector _stateProtector;
    private readonly IDataProtector _mergeProtector;
    private readonly ILogger<HubGoogleAuthService> _logger;
    private readonly IHostEnvironment _environment;
    private readonly HubGoogleAuthReplayCoordinator _replayCoordinator;
    private readonly PublicCanonicalOriginPolicy _publicOrigin;

    public HubGoogleAuthService(
        HttpClient httpClient,
        IConfiguration configuration,
        HubBrowserAuthService browserAuth,
        IdentityLinkService links,
        AccountService accounts,
        IDataProtectionProvider dataProtectionProvider,
        ILogger<HubGoogleAuthService> logger,
        IHostEnvironment environment,
        HubGoogleAuthReplayCoordinator? replayCoordinator = null,
        PublicCanonicalOriginPolicy? publicOrigin = null)
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
        _replayCoordinator = replayCoordinator ?? HubGoogleAuthReplayCoordinator.Shared;
        _publicOrigin = publicOrigin ?? PublicCanonicalOriginPolicy.CreateUnitTestDefault(configuration);
    }

    private string ClientId => _configuration["GOOGLE_OIDC_CLIENT_ID"]?.Trim() ?? string.Empty;
    private string ClientSecret => _configuration["GOOGLE_OIDC_CLIENT_SECRET"]?.Trim() ?? string.Empty;
    private string AuthorizationEndpoint => _configuration["GOOGLE_OIDC_AUTHORIZATION_ENDPOINT"]?.Trim() ?? "https://accounts.google.com/o/oauth2/v2/auth";
    private string TokenEndpoint => _configuration["GOOGLE_OIDC_TOKEN_ENDPOINT"]?.Trim() ?? "https://oauth2.googleapis.com/token";
    private string UserInfoEndpoint => _configuration["GOOGLE_OIDC_USERINFO_ENDPOINT"]?.Trim() ?? "https://openidconnect.googleapis.com/v1/userinfo";
    private string JwksEndpoint => _configuration["GOOGLE_OIDC_JWKS_ENDPOINT"]?.Trim() ?? "https://www.googleapis.com/oauth2/v3/certs";
    private bool CookieSecureDefault => !_environment.IsDevelopment();

    public bool IsConfigured()
        => !string.IsNullOrWhiteSpace(ClientId) && !string.IsNullOrWhiteSpace(ClientSecret);

    public string? DisabledReason()
        => IsConfigured()
            ? null
            : "Google sign-in is unavailable on this host because the OIDC environment variables are missing.";

    public void ValidateProductionReadiness()
    {
        bool requireGoogleOidc = string.Equals(_configuration["CHUMMER_GOOGLE_OIDC_REQUIRED"], "true", StringComparison.OrdinalIgnoreCase);
        if (_environment.IsProduction() && requireGoogleOidc && !IsConfigured())
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

        DateTimeOffset createdAtUtc = DateTimeOffset.UtcNow;
        var attempt = new GoogleAuthAttempt(
            State: CreateOpaqueToken(24),
            CodeVerifier: CreateOpaqueToken(48),
            Nonce: CreateOpaqueToken(24),
            NextPath: HubBrowserAuthService.SanitizeNextPath(nextPath),
            CreatedAtUtc: createdAtUtc,
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
            StateCookieValue: ProtectStateCookieValue(request, attempt, createdAtUtc));
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
            Secure = _publicOrigin.UsesHttps || CookieSecureDefault,
            SameSite = SameSiteMode.Lax,
            Expires = expiresAtUtc.UtcDateTime,
            IsEssential = true,
            Path = "/",
            Domain = null
        };

    public void ClearStateCookie(HttpRequest request, HttpResponse response)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(response);

        foreach (CookieOptions options in BuildStateCookieDeletionOptions(request))
        {
            response.Cookies.Delete(HubGoogleAuthConstants.StateCookieName, options);
        }
    }

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
                NextPath: DefaultNextPath,
                ErrorTitle: "Google sign-in is unavailable",
                ErrorDetail: DisabledReason());
        }

        if (preloadedClaims is not null)
        {
            return await CompleteResolvedClaimsAsync(
                request,
                preloadedClaims,
                nextPath: HubBrowserAuthService.SanitizeNextPath(request.Query["next"]),
                mergeSubjectId,
                linkSubjectId: null,
                cancellationToken);
        }

        if (!request.Cookies.TryGetValue(HubGoogleAuthConstants.StateCookieName, out var protectedState)
            || string.IsNullOrWhiteSpace(protectedState))
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: DefaultNextPath,
                ErrorTitle: "Google sign-in state was missing",
                ErrorDetail: "Start the Google sign-in flow from Chummer again so the PKCE and state cookie can be recreated.");
        }

        IReadOnlyList<GoogleAuthAttempt> trackedAttempts;
        try
        {
            trackedAttempts = ReadStateCookieAttempts(protectedState, ignoreCorruptedCookie: false);
        }
        catch (Exception ex) when (ex is CryptographicException or JsonException or InvalidOperationException)
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: DefaultNextPath,
                ErrorTitle: "Google sign-in state could not be read",
                ErrorDetail: "The authorization state cookie was not valid anymore. Start the flow again.");
        }

        string callbackState = query["state"].ToString();
        GoogleAuthAttempt? attempt = trackedAttempts.LastOrDefault(candidate =>
            string.Equals(candidate.State, callbackState, StringComparison.Ordinal));
        if (attempt is null)
        {
            string fallbackNextPath = HubBrowserAuthService.SanitizeNextPath(
                trackedAttempts.LastOrDefault()?.NextPath,
                DefaultNextPath);
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: fallbackNextPath,
                ErrorTitle: "Google sign-in state did not match",
                ErrorDetail: "Chummer rejected the callback because the `state` value no longer matched the browser handshake.");
        }

        string nextPath = HubBrowserAuthService.SanitizeNextPath(attempt.NextPath, DefaultNextPath);

        if (trackedAttempts.Count > 1
            && !string.Equals(trackedAttempts[^1].State, attempt.State, StringComparison.Ordinal))
        {
            _logger.LogInformation(
                "Google callback matched a preserved earlier state after a newer browser challenge was issued. TrackedAttempts {TrackedAttempts}.",
                trackedAttempts.Count);
        }

        if (attempt.CreatedAtUtc.Add(AuthAttemptLifetime) <= DateTimeOffset.UtcNow)
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                ErrorTitle: "Google sign-in expired",
                ErrorDetail: "The authorization handshake took too long. Start the Google sign-in flow again.");
        }

        if (!string.IsNullOrWhiteSpace(query["error"]))
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                ErrorTitle: "Google sign-in was cancelled",
                ErrorDetail: "Return to Chummer and start the Google sign-in flow again if you still want to continue.");
        }

        GoogleAuthorizationCodeCandidate[] codeCandidates;
        try
        {
            codeCandidates = ResolveAuthorizationCodeCandidates(request, query);
        }
        catch (Exception ex) when (ex is UriFormatException or FormatException)
        {
            _logger.LogWarning(
                ex,
                "Google sign-in callback could not parse authorization code candidates for state {State}.",
                attempt.State);
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                ErrorTitle: "Google sign-in callback was malformed",
                ErrorDetail: "The Google callback parameters could not be read. Start the Google sign-in flow again.");
        }

        if (codeCandidates.Length == 0)
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                ErrorTitle: "Google sign-in callback was incomplete",
                ErrorDetail: "Google did not return an authorization code.");
        }

        return await _replayCoordinator.CompleteOnceAsync(
            attempt.State,
            attempt.CreatedAtUtc.Add(AuthAttemptLifetime),
            async () =>
            {
                try
                {
                    GoogleIdentityClaims claims = await ExchangeForClaimsAsync(codeCandidates, attempt, cancellationToken);
                    return await CompleteResolvedClaimsAsync(
                        request,
                        claims,
                        nextPath: attempt.NextPath,
                        mergeSubjectId: null,
                        linkSubjectId: AccountService.NormalizeOptional(attempt.LinkSubjectId),
                        cancellationToken);
                }
                catch (GoogleTokenExchangeException ex)
                {
                    return new GoogleAuthCompletionResult(
                        Session: null,
                        NextPath: nextPath,
                        ErrorTitle: ex.IsMalformedAuthorizationCode
                            ? "Google sign-in code was malformed"
                            : "Google sign-in code could not be redeemed",
                        ErrorDetail: ex.IsMalformedAuthorizationCode
                            ? "Google returned a malformed authorization code. Start the Google sign-in flow again."
                            : "The Google authorization code was rejected. Start a fresh Google sign-in flow and complete it in a single browser window.");
                }
                catch (HubBrowserAuthUnavailableException ex)
                {
                    _logger.LogWarning(ex, "Google sign-in could not finish issuing the Hub session for state {State}.", attempt.State);
                    return new GoogleAuthCompletionResult(
                        Session: null,
                        NextPath: nextPath,
                        ErrorTitle: "Google sign-in session unavailable",
                        ErrorDetail: "Google confirmed your account, but Chummer could not finish the Hub session right now. Start the Google sign-in flow again in a moment.");
                }
                catch (InvalidOperationException ex)
                {
                    _logger.LogWarning(
                        ex,
                        "Google sign-in could not complete token exchange for state {State}.",
                        attempt.State);
                    return new GoogleAuthCompletionResult(
                        Session: null,
                        NextPath: nextPath,
                        ErrorTitle: "Google sign-in could not be completed",
                        ErrorDetail: "Google returned an invalid sign-in response. Start a fresh Google sign-in flow and try again.");
                }
                catch (HttpRequestException ex)
                {
                    _logger.LogWarning(ex, "Google sign-in request to OAuth endpoint failed for state {State}.", attempt.State);
                    return new GoogleAuthCompletionResult(
                        Session: null,
                        NextPath: nextPath,
                        ErrorTitle: "Google sign-in service unavailable",
                        ErrorDetail: "Chummer could not contact Google right now. Start the Google sign-in flow again.");
                }
                catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
                {
                    _logger.LogWarning(ex, "Google sign-in request timed out for state {State}.", attempt.State);
                    return new GoogleAuthCompletionResult(
                        Session: null,
                        NextPath: nextPath,
                        ErrorTitle: "Google sign-in timed out",
                        ErrorDetail: "The Google sign-in response took too long. Start a fresh Google sign-in flow.");
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    _logger.LogWarning(ex, "Google sign-in callback completed with an unexpected error for state {State}.", attempt.State);
                    return new GoogleAuthCompletionResult(
                        Session: null,
                        NextPath: nextPath,
                        ErrorTitle: "Google sign-in failed",
                        ErrorDetail: "Chummer could not complete your Google sign-in right now. Start the flow again in a moment.");
                }
            },
            cancellationToken);
    }

    private string ProtectStateCookieValue(HttpRequest request, GoogleAuthAttempt latestAttempt, DateTimeOffset now)
    {
        List<GoogleAuthAttempt> trackedAttempts = ReadStateCookieAttempts(
                request.Cookies[HubGoogleAuthConstants.StateCookieName],
                ignoreCorruptedCookie: true)
            .Where(candidate =>
                candidate.CreatedAtUtc.Add(AuthAttemptLifetime) > now
                && !string.Equals(candidate.State, latestAttempt.State, StringComparison.Ordinal))
            .OrderByDescending(candidate => candidate.CreatedAtUtc)
            .Take(MaxTrackedStateAttempts - 1)
            .Reverse()
            .ToList();

        trackedAttempts.Add(latestAttempt);
        return _stateProtector.Protect(JsonSerializer.Serialize(new GoogleAuthStateEnvelope(trackedAttempts.ToArray())));
    }

    private IReadOnlyList<GoogleAuthAttempt> ReadStateCookieAttempts(string? protectedState, bool ignoreCorruptedCookie)
    {
        if (string.IsNullOrWhiteSpace(protectedState))
        {
            return Array.Empty<GoogleAuthAttempt>();
        }

        try
        {
            string payload = _stateProtector.Unprotect(protectedState);
            GoogleAuthStateEnvelope? envelope = JsonSerializer.Deserialize<GoogleAuthStateEnvelope>(payload);
            if (envelope?.Attempts is { Length: > 0 })
            {
                GoogleAuthAttempt[] validAttempts = envelope.Attempts
                    .Where(IsValidStateAttempt)
                    .ToArray();
                if (validAttempts.Length > 0)
                {
                    return validAttempts;
                }
            }

            GoogleAuthAttempt? legacyAttempt = JsonSerializer.Deserialize<GoogleAuthAttempt>(payload);
            if (IsValidStateAttempt(legacyAttempt))
            {
                return new[] { legacyAttempt! };
            }

            throw new InvalidOperationException("Google auth attempt payload was empty.");
        }
        catch (Exception ex) when (ex is CryptographicException or JsonException or InvalidOperationException)
        {
            if (!ignoreCorruptedCookie)
            {
                throw;
            }

            _logger.LogInformation(ex, "Ignoring unreadable Google auth state cookie while issuing a fresh browser challenge.");
            return Array.Empty<GoogleAuthAttempt>();
        }
    }

    private static bool IsValidStateAttempt(GoogleAuthAttempt? attempt)
        => attempt is not null
           && !string.IsNullOrWhiteSpace(attempt.State)
           && !string.IsNullOrWhiteSpace(attempt.CodeVerifier)
           && !string.IsNullOrWhiteSpace(attempt.Nonce)
           && !string.IsNullOrWhiteSpace(attempt.NextPath)
           && !string.IsNullOrWhiteSpace(attempt.RedirectUri);

    private async Task<GoogleAuthCompletionResult> CompleteResolvedClaimsAsync(
        HttpRequest request,
        GoogleIdentityClaims claims,
        string nextPath,
        string? mergeSubjectId,
        string? linkSubjectId,
        CancellationToken cancellationToken)
    {
        if (!claims.EmailVerified)
        {
            return new GoogleAuthCompletionResult(
                Session: null,
                NextPath: nextPath,
                ErrorTitle: "Google email confirmation is required",
                ErrorDetail: "Chummer only accepts Google identities that come back with a confirmed email address.");
        }

        if (!string.IsNullOrWhiteSpace(mergeSubjectId))
        {
            string mergedNextPath = HubBrowserAuthService.SanitizeNextPath(request.Query["next"], claims.NextPathHint ?? nextPath);
            return await IssueSessionForSubjectAsync(mergeSubjectId, claims, mergedNextPath, cancellationToken);
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
                return await IssueSessionForSubjectAsync(IdentitySubjectDerivation.FromGoogleSubject(claims.Subject), claims, nextPath, cancellationToken);
            }

            return await IssueSessionForSubjectAsync(linkedUser.SubjectId, claims, nextPath, cancellationToken);
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
                    NextPath: nextPath,
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
        IdentitySessionIssueResponse session;
        try
        {
            session = await _browserAuth.IssueSessionAsync(
                subjectId,
                displayName: claims.DisplayName,
                email: claims.Email,
                requestedRoles: new[] { "player" },
                cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Google sign-in could not issue a Hub session for subject {SubjectId}.", subjectId);
            throw;
        }

        string issuedSubjectId = AccountService.NormalizeOptional(session.SubjectId) ?? subjectId;
        HubUserEnsureResult ensuredUser;
        try
        {
            ensuredUser = _accounts.EnsureUserWithStatus(issuedSubjectId, claims.DisplayName, claims.Email);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Google sign-in could not persist the Hub user record for subject {SubjectId}.", issuedSubjectId);
            throw;
        }

        try
        {
            _links.LinkExternalIdentity(new LinkExternalIdentityRequest(
                SubjectId: issuedSubjectId,
                Provider: "google",
                ProviderSubject: claims.Subject,
                DisplayLabel: claims.Email,
                MakePrimary: true));
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Google sign-in could not persist the Google identity link for subject {SubjectId}.", subjectId);
            throw;
        }

        return new GoogleAuthCompletionResult(
            Session: session,
            NextPath: HubBrowserAuthService.SanitizeNextPath(nextPath),
            AccountCreated: ensuredUser.Created);
    }

    private async Task<GoogleIdentityClaims> ExchangeForClaimsAsync(
        IReadOnlyList<GoogleAuthorizationCodeCandidate> codeCandidates,
        GoogleAuthAttempt attempt,
        CancellationToken cancellationToken)
    {
        if (codeCandidates.Count == 0)
        {
            throw new InvalidOperationException("Google sign-in callback did not contain an authorization code.");
        }

        GoogleTokenExchangeException? lastFailure = null;
        for (int index = 0; index < codeCandidates.Count; index++)
        {
            GoogleAuthorizationCodeCandidate candidate = codeCandidates[index];
            try
            {
                return await ExchangeForClaimsAsync(candidate.Code, attempt, candidate.Source, cancellationToken);
            }
            catch (GoogleTokenExchangeException ex)
            {
                if (!ex.IsAuthorizationCodeRejected || index + 1 >= codeCandidates.Count)
                {
                    lastFailure = ex;
                    break;
                }

                GoogleAuthorizationCodeCandidate fallback = codeCandidates[index + 1];
                _logger.LogWarning(
                    "Google token exchange rejected the {Source} authorization code with invalid_grant. MalformedAuthorizationCode {MalformedAuthorizationCode}. Falling back to {FallbackSource}. CandidateLength {CandidateLength}. FallbackLength {FallbackLength}.",
                    candidate.Source,
                    ex.IsMalformedAuthorizationCode,
                    fallback.Source,
                    candidate.Code.Length,
                    fallback.Code.Length);
                lastFailure = ex;
            }
        }

        throw lastFailure ?? new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
    }

    private async Task<GoogleIdentityClaims> ExchangeForClaimsAsync(
        string code,
        GoogleAuthAttempt attempt,
        string source,
        CancellationToken cancellationToken)
    {
        using var tokenResponse = await SendGoogleRequestAsync(
            () => _httpClient.PostAsync(
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
                cancellationToken),
            operation: "token exchange",
            cancellationToken);

        if (!tokenResponse.IsSuccessStatusCode)
        {
            var detail = await tokenResponse.Content.ReadAsStringAsync(cancellationToken);
            bool authorizationCodeRejected = IsAuthorizationCodeRejectedFailure(tokenResponse.StatusCode, detail);
            bool malformedAuthorizationCode = authorizationCodeRejected && IsMalformedAuthorizationCodeDetail(detail);
            _logger.LogWarning(
                "Google token exchange failed with status {StatusCode} for {Source}. AuthorizationCodeRejected {AuthorizationCodeRejected}. MalformedAuthorizationCode {MalformedAuthorizationCode}. Detail: {Detail}",
                (int)tokenResponse.StatusCode,
                source,
                authorizationCodeRejected,
                malformedAuthorizationCode,
                string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
            throw new GoogleTokenExchangeException(authorizationCodeRejected, malformedAuthorizationCode);
        }

        var tokens = await tokenResponse.Content.ReadFromJsonAsync<GoogleTokenResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        if (string.IsNullOrWhiteSpace(tokens.AccessToken) || string.IsNullOrWhiteSpace(tokens.IdToken))
        {
            throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        }

        var idTokenClaims = await ValidateIdTokenAsync(tokens.IdToken, attempt, cancellationToken);

        using var userInfoResponse = await SendGoogleRequestAsync(
            () => SendGoogleUserInfoRequestAsync(tokens.AccessToken, cancellationToken),
            operation: "userinfo fetch",
            cancellationToken);
        if (!userInfoResponse.IsSuccessStatusCode)
        {
            var detail = await userInfoResponse.Content.ReadAsStringAsync(cancellationToken);
            _logger.LogWarning(
                "Google userinfo fetch failed with status {StatusCode}. Detail: {Detail}",
                (int)userInfoResponse.StatusCode,
                string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
            throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        }

        var userInfo = await userInfoResponse.Content.ReadFromJsonAsync<GoogleUserInfoResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        if (string.IsNullOrWhiteSpace(userInfo.Sub) || string.IsNullOrWhiteSpace(userInfo.Email))
        {
            throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        }

        if (!string.Equals(userInfo.Sub, idTokenClaims.Subject, StringComparison.Ordinal)
            || !string.Equals(userInfo.Email, idTokenClaims.Email, StringComparison.OrdinalIgnoreCase))
        {
            _logger.LogWarning(
                "Google userinfo/id_token mismatch for subject {UserInfoSubject} and email {UserInfoEmail}.",
                userInfo.Sub,
                userInfo.Email);
            throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        }

        return new GoogleIdentityClaims(
            Subject: idTokenClaims.Subject,
            Email: idTokenClaims.Email,
            EmailVerified: idTokenClaims.EmailVerified && userInfo.EmailVerified,
            DisplayName: string.IsNullOrWhiteSpace(idTokenClaims.DisplayName)
                ? string.IsNullOrWhiteSpace(userInfo.Name)
                    ? idTokenClaims.Email.Split('@')[0]
                    : userInfo.Name
                : idTokenClaims.DisplayName,
            NextPathHint: null);
    }

    private async Task<GoogleIdTokenClaims> ValidateIdTokenAsync(
        string idToken,
        GoogleAuthAttempt attempt,
        CancellationToken cancellationToken)
    {
        try
        {
            string[] parts = idToken.Split('.');
            if (parts.Length != 3)
            {
                throw new InvalidOperationException("Google id_token was malformed.");
            }

            using var header = JsonDocument.Parse(WebEncoders.Base64UrlDecode(parts[0]));
            using var payload = JsonDocument.Parse(WebEncoders.Base64UrlDecode(parts[1]));

            string algorithm = ReadRequiredString(header.RootElement, "alg");
            if (!string.Equals(algorithm, "RS256", StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Google id_token algorithm was not RS256.");
            }

            string keyId = ReadRequiredString(header.RootElement, "kid");
            await ValidateIdTokenSignatureAsync(parts[0], parts[1], parts[2], keyId, cancellationToken);

            string issuer = ReadRequiredString(payload.RootElement, "iss");
            if (!string.Equals(issuer, "https://accounts.google.com", StringComparison.Ordinal)
                && !string.Equals(issuer, "accounts.google.com", StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Google id_token issuer was not accepted.");
            }

            if (!AudienceContainsClientId(payload.RootElement, ClientId))
            {
                throw new InvalidOperationException("Google id_token audience did not match the configured client.");
            }

            string? authorizedParty = ReadOptionalString(payload.RootElement, "azp");
            if (!string.IsNullOrWhiteSpace(authorizedParty)
                && !string.Equals(authorizedParty, ClientId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Google id_token authorized party did not match the configured client.");
            }

            string nonce = ReadRequiredString(payload.RootElement, "nonce");
            if (!string.Equals(nonce, attempt.Nonce, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Google id_token nonce did not match the browser challenge.");
            }

            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            long expiresAt = ReadRequiredInt64(payload.RootElement, "exp");
            if (expiresAt <= now - 30)
            {
                throw new InvalidOperationException("Google id_token expired.");
            }

            long? issuedAt = ReadOptionalInt64(payload.RootElement, "iat");
            if (issuedAt is not null && issuedAt.Value > now + 300)
            {
                throw new InvalidOperationException("Google id_token issue time was not accepted.");
            }

            return new GoogleIdTokenClaims(
                Subject: ReadRequiredString(payload.RootElement, "sub"),
                Email: ReadRequiredString(payload.RootElement, "email"),
                EmailVerified: ReadOptionalBool(payload.RootElement, "email_verified") ?? false,
                DisplayName: ReadOptionalString(payload.RootElement, "name"));
        }
        catch (Exception ex) when (ex is CryptographicException or FormatException or JsonException or InvalidOperationException)
        {
            _logger.LogWarning(ex, "Google id_token validation failed.");
            throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        }
    }

    private async Task ValidateIdTokenSignatureAsync(
        string encodedHeader,
        string encodedPayload,
        string encodedSignature,
        string keyId,
        CancellationToken cancellationToken)
    {
        using var jwksResponse = await SendGoogleRequestAsync(
            () => _httpClient.GetAsync(JwksEndpoint, cancellationToken),
            operation: "JWKS fetch",
            cancellationToken);
        if (!jwksResponse.IsSuccessStatusCode)
        {
            var detail = await jwksResponse.Content.ReadAsStringAsync(cancellationToken);
            _logger.LogWarning(
                "Google JWKS fetch failed with status {StatusCode}. Detail: {Detail}",
                (int)jwksResponse.StatusCode,
                string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
            throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        }

        var jwks = await jwksResponse.Content.ReadFromJsonAsync<GoogleJwksResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.");
        GoogleJwk? key = jwks.Keys.FirstOrDefault(candidate =>
            string.Equals(candidate.KeyId, keyId, StringComparison.Ordinal)
            && string.Equals(candidate.KeyType, "RSA", StringComparison.OrdinalIgnoreCase));
        if (key is null
            || string.IsNullOrWhiteSpace(key.Modulus)
            || string.IsNullOrWhiteSpace(key.Exponent))
        {
            throw new InvalidOperationException("Google signing key could not be resolved.");
        }

        if (!string.IsNullOrWhiteSpace(key.Algorithm)
            && !string.Equals(key.Algorithm, "RS256", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Google signing key algorithm was not RS256.");
        }

        using var rsa = RSA.Create();
        rsa.ImportParameters(new RSAParameters
        {
            Modulus = WebEncoders.Base64UrlDecode(key.Modulus),
            Exponent = WebEncoders.Base64UrlDecode(key.Exponent)
        });

        byte[] signedBytes = Encoding.ASCII.GetBytes($"{encodedHeader}.{encodedPayload}");
        byte[] signatureBytes = WebEncoders.Base64UrlDecode(encodedSignature);
        if (!rsa.VerifyData(signedBytes, signatureBytes, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1))
        {
            throw new InvalidOperationException("Google id_token signature verification failed.");
        }
    }

    private async Task<HttpResponseMessage> SendGoogleUserInfoRequestAsync(string accessToken, CancellationToken cancellationToken)
    {
        using var userInfoRequest = new HttpRequestMessage(HttpMethod.Get, UserInfoEndpoint);
        userInfoRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        return await _httpClient.SendAsync(userInfoRequest, cancellationToken);
    }

    private async Task<HttpResponseMessage> SendGoogleRequestAsync(
        Func<Task<HttpResponseMessage>> sendAsync,
        string operation,
        CancellationToken cancellationToken)
    {
        for (int attempt = 1; ; attempt++)
        {
            try
            {
                HttpResponseMessage response = await sendAsync();
                if (attempt < TransientRetryAttempts && IsTransientStatusCode(response.StatusCode))
                {
                    string detail = await SafeReadBodyAsync(response, cancellationToken);
                    _logger.LogWarning(
                        "Google {Operation} returned transient status {StatusCode} on attempt {Attempt}. Retrying. Detail: {Detail}",
                        operation,
                        (int)response.StatusCode,
                        attempt,
                        string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
                    response.Dispose();
                    await DelayBeforeRetryAsync(attempt, cancellationToken);
                    continue;
                }

                return response;
            }
            catch (HttpRequestException ex) when (attempt < TransientRetryAttempts)
            {
                _logger.LogWarning(ex, "Google {Operation} failed on attempt {Attempt}. Retrying.", operation, attempt);
                await DelayBeforeRetryAsync(attempt, cancellationToken);
            }
            catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested && attempt < TransientRetryAttempts)
            {
                _logger.LogWarning(ex, "Google {Operation} timed out on attempt {Attempt}. Retrying.", operation, attempt);
                await DelayBeforeRetryAsync(attempt, cancellationToken);
            }
        }
    }

    private static bool IsTransientStatusCode(HttpStatusCode statusCode)
        => statusCode == HttpStatusCode.RequestTimeout
           || statusCode == HttpStatusCode.TooManyRequests
           || statusCode == HttpStatusCode.BadGateway
           || statusCode == HttpStatusCode.ServiceUnavailable
           || statusCode == HttpStatusCode.GatewayTimeout
           || (int)statusCode >= 500;

    private static Task DelayBeforeRetryAsync(int attempt, CancellationToken cancellationToken)
        => Task.Delay(TimeSpan.FromMilliseconds(200 * Math.Max(1, attempt)), cancellationToken);

    private static async Task<string> SafeReadBodyAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        try
        {
            return await response.Content.ReadAsStringAsync(cancellationToken);
        }
        catch
        {
            return string.Empty;
        }
    }

    private static bool AudienceContainsClientId(JsonElement payload, string clientId)
    {
        if (!payload.TryGetProperty("aud", out var audienceElement))
        {
            return false;
        }

        return audienceElement.ValueKind switch
        {
            JsonValueKind.String => string.Equals(audienceElement.GetString(), clientId, StringComparison.Ordinal),
            JsonValueKind.Array => audienceElement.EnumerateArray().Any(entry =>
                entry.ValueKind == JsonValueKind.String
                && string.Equals(entry.GetString(), clientId, StringComparison.Ordinal)),
            _ => false
        };
    }

    private static string ReadRequiredString(JsonElement element, string propertyName)
    {
        string? value = ReadOptionalString(element, propertyName);
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException($"Google token claim '{propertyName}' was missing.");
        }

        return value;
    }

    private static string? ReadOptionalString(JsonElement element, string propertyName)
    {
        return element.TryGetProperty(propertyName, out var value)
            && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    private static long ReadRequiredInt64(JsonElement element, string propertyName)
    {
        long? value = ReadOptionalInt64(element, propertyName);
        if (value is null)
        {
            throw new InvalidOperationException($"Google token claim '{propertyName}' was missing.");
        }

        return value.Value;
    }

    private static long? ReadOptionalInt64(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value))
        {
            return null;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var numeric))
        {
            return numeric;
        }

        return value.ValueKind == JsonValueKind.String && long.TryParse(value.GetString(), out numeric)
            ? numeric
            : null;
    }

    private static bool? ReadOptionalBool(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.String when bool.TryParse(value.GetString(), out var parsed) => parsed,
            _ => null
        };
    }

    private string ResolveRedirectUri(HttpRequest request)
    {
        var configured = _configuration["GOOGLE_OIDC_REDIRECT_URI"]?.Trim();
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return configured;
        }

        return _publicOrigin.BuildAbsolute("/auth/google/callback");
    }

    private IReadOnlyList<CookieOptions> BuildStateCookieDeletionOptions(HttpRequest request)
    {
        var options = new List<CookieOptions>(2);
        AddStateCookieDeletionOption(options, request, domain: null);
        AddStateCookieDeletionOption(options, request, ResolveConfiguredStateCookieDomain());
        return options;
    }

    private void AddStateCookieDeletionOption(List<CookieOptions> options, HttpRequest request, string? domain)
    {
        if (options.Any(existing => string.Equals(existing.Domain, domain, StringComparison.OrdinalIgnoreCase)))
        {
            return;
        }

        options.Add(new CookieOptions
        {
            HttpOnly = true,
            Secure = _publicOrigin.UsesHttps || CookieSecureDefault,
            SameSite = SameSiteMode.Lax,
            IsEssential = true,
            Path = "/",
            Domain = domain
        });
    }

    private string? ResolveConfiguredStateCookieDomain()
    {
        var configured = _configuration["GOOGLE_OIDC_REDIRECT_URI"]?.Trim();
        if (string.IsNullOrWhiteSpace(configured)
            || !Uri.TryCreate(configured, UriKind.Absolute, out var redirectUri))
        {
            return null;
        }

        return NormalizeCookieDomainHost(redirectUri.Host);
    }

    private static string? NormalizeCookieDomainHost(string? host)
    {
        string trimmed = host?.Trim().Trim('.') ?? string.Empty;
        if (string.IsNullOrWhiteSpace(trimmed)
            || string.Equals(trimmed, "localhost", StringComparison.OrdinalIgnoreCase)
            || IPAddress.TryParse(trimmed, out _))
        {
            return null;
        }

        return trimmed;
    }

    private static string CreateOpaqueToken(int byteCount)
    {
        return WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(byteCount));
    }

    private static string NormalizeAuthorizationCode(string code)
    {
        if (string.IsNullOrWhiteSpace(code))
        {
            return string.Empty;
        }

        string trimmed = code.Trim();
        return trimmed.Contains(' ')
            ? trimmed.Replace(' ', '+')
            : trimmed;
    }

    private GoogleAuthorizationCodeCandidate[] ResolveAuthorizationCodeCandidates(HttpRequest request, IQueryCollection query)
    {
        var candidates = new List<GoogleAuthorizationCodeCandidate>(3);
        RawAuthorizationCodeExtraction rawExtraction = ExtractRawAuthorizationCodeCandidates(request.QueryString.Value);
        if (rawExtraction.HadMalformedPercentEncoding)
        {
            AddAuthorizationCodeCandidate(candidates, query["code"].ToString(), "parsed_query");
        }
        foreach (GoogleAuthorizationCodeCandidate rawCandidate in rawExtraction.Candidates)
        {
            AddAuthorizationCodeCandidate(candidates, rawCandidate.Code, rawCandidate.Source);
        }
        if (!rawExtraction.HadMalformedPercentEncoding)
        {
            AddAuthorizationCodeCandidate(candidates, query["code"].ToString(), "parsed_query");
        }

        return candidates.ToArray();
    }

    private void AddAuthorizationCodeCandidate(List<GoogleAuthorizationCodeCandidate> candidates, string rawCode, string source)
    {
        if (string.IsNullOrWhiteSpace(rawCode))
        {
            return;
        }

        string normalizedCode = NormalizeAuthorizationCode(rawCode);
        if (string.IsNullOrWhiteSpace(normalizedCode))
        {
            return;
        }

        if (!string.Equals(normalizedCode, rawCode, StringComparison.Ordinal))
        {
            _logger.LogInformation(
                "Google authorization code candidate from {Source} was normalized before token exchange. OriginalLength {OriginalLength}. NormalizedLength {NormalizedLength}.",
                source,
                rawCode.Length,
                normalizedCode.Length);
        }

        if (candidates.Any(existing => string.Equals(existing.Code, normalizedCode, StringComparison.Ordinal)))
        {
            return;
        }

        candidates.Add(new GoogleAuthorizationCodeCandidate(source, normalizedCode));
    }

    private static RawAuthorizationCodeExtraction ExtractRawAuthorizationCodeCandidates(string? rawQueryString)
    {
        const string parameterName = "code";
        if (string.IsNullOrWhiteSpace(rawQueryString))
        {
            return new RawAuthorizationCodeExtraction(Array.Empty<GoogleAuthorizationCodeCandidate>(), HadMalformedPercentEncoding: false);
        }

        string query = rawQueryString[0] == '?'
            ? rawQueryString[1..]
            : rawQueryString;
        var candidates = new List<GoogleAuthorizationCodeCandidate>(2);

        foreach (string segment in query.Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            int separatorIndex = segment.IndexOf('=');
            string encodedName = separatorIndex >= 0
                ? segment[..separatorIndex]
                : segment;
            string name = DecodeOpaqueQueryValueLenient(encodedName);
            if (!string.Equals(name, parameterName, StringComparison.Ordinal))
            {
                continue;
            }

            string encodedValue = separatorIndex >= 0
                ? segment[(separatorIndex + 1)..]
                : string.Empty;
            bool hasMalformedPercentEncoding = ContainsMalformedPercentEncoding(encodedValue);

            string decodedValue = DecodeOpaqueQueryValueLenient(encodedValue);
            if (!string.IsNullOrWhiteSpace(decodedValue))
            {
                candidates.Add(new GoogleAuthorizationCodeCandidate("raw_query", decodedValue));
            }

            if (!string.IsNullOrWhiteSpace(encodedValue)
                && encodedValue.IndexOf('%') >= 0
                && !string.Equals(encodedValue, decodedValue, StringComparison.Ordinal))
            {
                candidates.Add(new GoogleAuthorizationCodeCandidate("raw_query_literal", encodedValue));
            }

            return new RawAuthorizationCodeExtraction(candidates, hasMalformedPercentEncoding);
        }

        return new RawAuthorizationCodeExtraction(Array.Empty<GoogleAuthorizationCodeCandidate>(), HadMalformedPercentEncoding: false);
    }

    private static string DecodeOpaqueQueryValueLenient(string encodedText)
    {
        if (string.IsNullOrEmpty(encodedText))
        {
            return string.Empty;
        }

        var builder = new StringBuilder(encodedText.Length);
        for (int i = 0; i < encodedText.Length; i++)
        {
            if (encodedText[i] == '%'
                && i + 2 < encodedText.Length
                && Uri.IsHexDigit(encodedText[i + 1])
                && Uri.IsHexDigit(encodedText[i + 2]))
            {
                int decodedByte = HexValue(encodedText[i + 1]) * 16 + HexValue(encodedText[i + 2]);
                builder.Append((char)decodedByte);
                i += 2;
                continue;
            }

            builder.Append(encodedText[i]);
        }

        return builder.ToString();
    }

    private static int HexValue(char value)
        => value <= '9'
            ? value - '0'
            : (value <= 'F'
                ? value - 'A' + 10
                : value - 'a' + 10);

    private static bool ContainsMalformedPercentEncoding(string encodedText)
    {
        for (int i = 0; i < encodedText.Length; i++)
        {
            if (encodedText[i] != '%')
            {
                continue;
            }

            if (i + 2 >= encodedText.Length
                || !Uri.IsHexDigit(encodedText[i + 1])
                || !Uri.IsHexDigit(encodedText[i + 2]))
            {
                return true;
            }

            i += 2;
        }

        return false;
    }

    private static bool IsAuthorizationCodeRejectedFailure(HttpStatusCode statusCode, string detail)
        => statusCode == HttpStatusCode.BadRequest
           && detail.Contains("invalid_grant", StringComparison.OrdinalIgnoreCase);

    private static bool IsMalformedAuthorizationCodeDetail(string detail)
        => detail.Contains("Malformed auth code", StringComparison.OrdinalIgnoreCase);

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

    private sealed record GoogleAuthorizationCodeCandidate(string Source, string Code);

    private sealed record RawAuthorizationCodeExtraction(
        IReadOnlyList<GoogleAuthorizationCodeCandidate> Candidates,
        bool HadMalformedPercentEncoding);

    private sealed record GoogleAuthStateEnvelope(GoogleAuthAttempt[] Attempts);

    private sealed class GoogleTokenExchangeException(bool isAuthorizationCodeRejected, bool isMalformedAuthorizationCode)
        : InvalidOperationException("Google sign-in could not be completed right now. Try again in a moment.")
    {
        public bool IsAuthorizationCodeRejected { get; } = isAuthorizationCodeRejected;

        public bool IsMalformedAuthorizationCode { get; } = isMalformedAuthorizationCode;
    }

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

    private sealed record GoogleJwksResponse(
        [property: JsonPropertyName("keys")] GoogleJwk[] Keys);

    private sealed record GoogleJwk(
        [property: JsonPropertyName("kid")] string KeyId,
        [property: JsonPropertyName("kty")] string KeyType,
        [property: JsonPropertyName("alg")] string? Algorithm,
        [property: JsonPropertyName("n")] string Modulus,
        [property: JsonPropertyName("e")] string Exponent);

    private sealed record GoogleUserInfoResponse(
        [property: JsonPropertyName("sub")] string Sub,
        [property: JsonPropertyName("email")] string Email,
        [property: JsonPropertyName("email_verified")] bool EmailVerified,
        [property: JsonPropertyName("name")] string? Name);

    private sealed record GoogleIdTokenClaims(
        string Subject,
        string Email,
        bool EmailVerified,
        string? DisplayName);

    private sealed record GoogleIdentityClaims(
        string Subject,
        string Email,
        bool EmailVerified,
        string DisplayName,
        string? NextPathHint);
}
