using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Primitives;
using Xunit;

namespace Chummer.Tests;

public sealed class HubIdentityHintCookieServiceTests
{
    [Fact]
    public void TryGetFallbackSubjectReadsProtectedHintCookieBoundToCurrentAccessToken()
    {
        string root = Path.Combine(Path.GetTempPath(), "hub-identity-hint-cookie-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);

        try
        {
            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(root, "keys")));
            HubIdentityHintCookieService hintCookie = new(dataProtection);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test"
                })
                .Build();
            HubIdentityClient identity = new(
                new HttpClient(),
                configuration,
                NullLogger<HubIdentityClient>.Instance,
                new HubIdentitySubjectCache(),
                hintCookie);

            DefaultHttpContext writeContext = new();
            writeContext.Request.Scheme = "https";
            IdentitySessionIssueResponse session = new(
                SessionId: "session-1",
                SubjectId: "subject-1",
                DisplayName: "Tibor",
                Email: ReleaseUploadAccessPolicy.AllowedEmail,
                Roles: ["player"],
                AccessToken: "access-token-1",
                RefreshToken: "refresh-token-1",
                IssuedAtUtc: DateTimeOffset.UtcNow,
                ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(4));

            hintCookie.WriteCookie(writeContext.Request, writeContext.Response, session);
            string protectedCookie = ExtractCookieValue(writeContext, HubBrowserAuthConstants.SubjectHintCookieName);

            DefaultHttpContext readContext = new();
            readContext.Request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", session.AccessToken).ToString();
            readContext.Request.Headers.Cookie = $"{HubBrowserAuthConstants.SubjectHintCookieName}={protectedCookie}";

            bool resolved = identity.TryGetFallbackSubject(readContext.Request, out AuthenticatedHubSubject? subject);

            Assert.True(resolved);
            Assert.NotNull(subject);
            Assert.Equal(session.SubjectId, subject!.SubjectId);
            Assert.Equal(session.DisplayName, subject.DisplayName);
            Assert.Equal(session.Email, subject.Email);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void TryGetFallbackSubjectRejectsHintCookieWhenAccessTokenDoesNotMatch()
    {
        string root = Path.Combine(Path.GetTempPath(), "hub-identity-hint-cookie-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);

        try
        {
            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(root, "keys")));
            HubIdentityHintCookieService hintCookie = new(dataProtection);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test"
                })
                .Build();
            HubIdentityClient identity = new(
                new HttpClient(),
                configuration,
                NullLogger<HubIdentityClient>.Instance,
                new HubIdentitySubjectCache(),
                hintCookie);

            DefaultHttpContext writeContext = new();
            writeContext.Request.Scheme = "https";
            IdentitySessionIssueResponse session = new(
                SessionId: "session-1",
                SubjectId: "subject-1",
                DisplayName: "Tibor",
                Email: ReleaseUploadAccessPolicy.AllowedEmail,
                Roles: ["player"],
                AccessToken: "access-token-1",
                RefreshToken: "refresh-token-1",
                IssuedAtUtc: DateTimeOffset.UtcNow,
                ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(4));

            hintCookie.WriteCookie(writeContext.Request, writeContext.Response, session);
            string protectedCookie = ExtractCookieValue(writeContext, HubBrowserAuthConstants.SubjectHintCookieName);

            DefaultHttpContext readContext = new();
            readContext.Request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", "different-access-token").ToString();
            readContext.Request.Headers.Cookie = $"{HubBrowserAuthConstants.SubjectHintCookieName}={protectedCookie}";

            bool resolved = identity.TryGetFallbackSubject(readContext.Request, out AuthenticatedHubSubject? subject);

            Assert.False(resolved);
            Assert.Null(subject);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void PublicChromeFallbackControllersUseRetainedSubjectRecovery()
    {
        string publicLanding = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string publicProgress = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicProgressController.cs"));
        string leaderboards = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LeaderboardsController.cs"));

        Assert.Contains("TryBuildRetainedSignedInChrome", publicLanding, StringComparison.Ordinal);
        Assert.Contains("_identity.TryGetFallbackSubject(Request, out AuthenticatedHubSubject? subject)", publicLanding, StringComparison.Ordinal);
        Assert.Contains("TryBuildRetainedSignedInChrome", publicProgress, StringComparison.Ordinal);
        Assert.Contains("_identity.TryGetFallbackSubject(Request, out AuthenticatedHubSubject? subject)", publicProgress, StringComparison.Ordinal);
        Assert.Contains("TryBuildRetainedSignedInChrome", leaderboards, StringComparison.Ordinal);
        Assert.Contains("_identity.TryGetFallbackSubject(Request, out AuthenticatedHubSubject? subject)", leaderboards, StringComparison.Ordinal);
    }

    private static string ExtractCookieValue(DefaultHttpContext context, string cookieName)
    {
        string?[] setCookieValues = context.Response.Headers.SetCookie.ToArray();
        Assert.Single(setCookieValues);
        string setCookie = Assert.IsType<string>(setCookieValues[0]);
        string prefix = $"{cookieName}=";
        int prefixIndex = setCookie.IndexOf(prefix, StringComparison.Ordinal);
        Assert.True(prefixIndex >= 0, $"Cookie '{cookieName}' was not written.");
        string remainder = setCookie[(prefixIndex + prefix.Length)..];
        int terminator = remainder.IndexOf(';');
        return terminator >= 0 ? remainder[..terminator] : remainder;
    }
}

public sealed class HubBrowserAuthServiceTests
{
    [Fact]
    public async Task IssueSessionAsyncRetriesTransientIdentityFailure()
    {
        int sessionRequests = 0;
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                ["IDENTITY_ADMIN_KEY"] = "admin-key"
            })
            .Build();

        var handler = new RetryStubHttpMessageHandler(async request =>
        {
            if (!string.Equals(request.RequestUri?.AbsoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
            {
                throw new InvalidOperationException($"Unexpected request URI in HubBrowserAuthService test: {request.RequestUri}");
            }

            Assert.Equal("admin-key", request.Headers.GetValues("X-Identity-Admin-Key").Single());
            int attempt = Interlocked.Increment(ref sessionRequests);
            if (attempt == 1)
            {
                return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
                {
                    Content = new StringContent("identity warming up", Encoding.UTF8, "text/plain")
                };
            }

            string body = await request.Content!.ReadAsStringAsync();
            Assert.Contains("subject.retry", body, StringComparison.Ordinal);

            return JsonResponse(HttpStatusCode.Created, new
            {
                sessionId = "session-1",
                subjectId = "subject.retry",
                displayName = "Runner Prime",
                email = "runner@example.com",
                roles = new[] { "player" },
                accessToken = "issued-access-token",
                refreshToken = "issued-refresh-token",
                issuedAtUtc = DateTimeOffset.UtcNow,
                expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
            });
        });

        HubBrowserAuthService browserAuth = new(
            new HttpClient(handler),
            configuration,
            NullLogger<HubBrowserAuthService>.Instance);

        IdentitySessionIssueResponse session = await browserAuth.IssueSessionAsync(
            "subject.retry",
            "Runner Prime",
            "runner@example.com",
            ["player"],
            CancellationToken.None);

        Assert.Equal("issued-access-token", session.AccessToken);
        Assert.Equal("subject.retry", session.SubjectId);
        Assert.Equal(2, sessionRequests);
    }

    private static HttpResponseMessage JsonResponse(HttpStatusCode statusCode, object payload)
    {
        return new HttpResponseMessage(statusCode)
        {
            Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
        };
    }

    private sealed class RetryStubHttpMessageHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> responder)
        : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => responder(request);
    }
}

public sealed class HubGoogleAuthServiceTests
{
    [Fact]
    public void BuildStateCookieUsesSharedApexDomainWhenCallbackHostIsParentDomain()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = "hub-google-client",
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback"
                })
                .Build();

            HubBrowserAuthService browserAuth = new(new HttpClient(), configuration, NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment());

            DefaultHttpContext context = new();
            context.Request.Scheme = "https";
            context.Request.Host = new HostString("www.chummer.run");

            CookieOptions cookie = google.BuildStateCookie(context.Request, DateTimeOffset.UtcNow.AddMinutes(10));

            Assert.Equal("chummer.run", cookie.Domain);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public void BuildStateCookieKeepsHostOnlyCookieWhenCallbackHostMatchesRequestHost()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = "hub-google-client",
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback"
                })
                .Build();

            HubBrowserAuthService browserAuth = new(new HttpClient(), configuration, NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment());

            DefaultHttpContext context = new();
            context.Request.Scheme = "https";
            context.Request.Host = new HostString("chummer.run");

            CookieOptions cookie = google.BuildStateCookie(context.Request, DateTimeOffset.UtcNow.AddMinutes(10));

            Assert.Null(cookie.Domain);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncDeduplicatesConcurrentCallbackRedemption()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    Assert.Contains("code=shared-auth-code", formBody, StringComparison.Ordinal);
                    Assert.Contains("client_id=hub-google-client", formBody, StringComparison.Ordinal);
                    Assert.Contains("client_secret=google-secret", formBody, StringComparison.Ordinal);
                    await Task.Delay(150);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-1",
                        email: "runner@example.com",
                        emailVerified: true,
                        displayName: "Runner Prime");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    Assert.Equal("Bearer", request.Headers.Authorization?.Scheme);
                    Assert.Equal("google-access-token", request.Headers.Authorization?.Parameter);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-1",
                        email = "runner@example.com",
                        email_verified = true,
                        name = "Runner Prime"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    Assert.Equal("admin-key", request.Headers.GetValues("X-Identity-Admin-Key").Single());

                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-1",
                        subjectId = "google:google-subject-1",
                        displayName = "Runner Prime",
                        email = "runner@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-access-token",
                        refreshToken = "issued-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callbackA = BuildCallbackContext(challenge.StateCookieValue, state, "shared-auth-code");
            DefaultHttpContext callbackB = BuildCallbackContext(challenge.StateCookieValue, state, "shared-auth-code");

            GoogleAuthCompletionResult[] results = await Task.WhenAll(
                google.CompleteAsync(callbackA.Request, callbackA.Request.Query, CancellationToken.None),
                google.CompleteAsync(callbackB.Request, callbackB.Request.Query, CancellationToken.None));

            Assert.All(results, result =>
            {
                Assert.NotNull(result.Session);
                Assert.Equal("/home", result.NextPath);
            });
            Assert.NotNull(results[0].Session);
            Assert.NotNull(results[1].Session);
            Assert.Equal("issued-access-token", results[0].Session!.AccessToken);
            Assert.Equal(results[0].Session!.AccessToken, results[1].Session!.AccessToken);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
            Assert.Single(store.LinkedIdentities);
            Assert.Equal("google", store.LinkedIdentities[0].Provider);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncAcceptsEarlierPreservedStateAfterSecondStartIssuesNewChallenge()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string firstNonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    Assert.Contains("code=first-start-auth-code", formBody, StringComparison.Ordinal);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        firstNonce,
                        subject: "google-subject-preserved-state",
                        email: "preservedstate@example.com",
                        emailVerified: true,
                        displayName: "Preserved State");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-preserved-state",
                        email = "preservedstate@example.com",
                        email_verified = true,
                        name = "Preserved State"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-preserved-state",
                        subjectId = "google:google-subject-preserved-state",
                        displayName = "Preserved State",
                        email = "preservedstate@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-preserved-state-access-token",
                        refreshToken = "issued-preserved-state-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext firstStartContext = new();
            firstStartContext.Request.Scheme = "https";
            firstStartContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge firstChallenge = google.CreateChallenge(firstStartContext.Request, "/home");
            string firstState = QueryHelpers.ParseQuery(new Uri(firstChallenge.RedirectUrl).Query)["state"].ToString();
            firstNonce = ReadNonceFromProtectedState(firstChallenge.StateCookieValue, tempRoot, firstState);

            DefaultHttpContext secondStartContext = new();
            secondStartContext.Request.Scheme = "https";
            secondStartContext.Request.Host = new HostString("hub.example.test");
            secondStartContext.Request.Headers.Cookie = $"{HubGoogleAuthConstants.StateCookieName}={firstChallenge.StateCookieValue}";
            GoogleAuthChallenge secondChallenge = google.CreateChallenge(secondStartContext.Request, "/home");
            string secondState = QueryHelpers.ParseQuery(new Uri(secondChallenge.RedirectUrl).Query)["state"].ToString();

            string[] trackedStates = ReadTrackedStatesFromProtectedState(secondChallenge.StateCookieValue, tempRoot);
            Assert.Equal(new[] { firstState, secondState }, trackedStates);

            DefaultHttpContext callback = BuildCallbackContext(secondChallenge.StateCookieValue, firstState, "first-start-auth-code");
            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("issued-preserved-state-access-token", result.Session!.AccessToken);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
            Assert.Single(store.LinkedIdentities);
            Assert.Equal("google", store.LinkedIdentities[0].Provider);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncRepairsOrphanedGoogleIdentityLink()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-orphaned",
                        email: "orphaned@example.com",
                        emailVerified: true,
                        displayName: "Orphaned Google");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-orphaned",
                        email = "orphaned@example.com",
                        email_verified = true,
                        name = "Orphaned Google"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-orphaned-google",
                        subjectId = "google:google-subject-orphaned",
                        displayName = "Orphaned Google",
                        email = "orphaned@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-orphaned-google-access-token",
                        refreshToken = "issued-orphaned-google-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            lock (store.Gate)
            {
                store.LinkedIdentities.Add(new LinkedIdentityDto(
                    IdentityLinkId: "idl-orphaned-google",
                    UserId: "usr-missing-google",
                    Provider: "google",
                    LinkKind: "social_auth",
                    ProviderSubject: "google-subject-orphaned",
                    DisplayLabel: "orphaned@example.com",
                    Status: "provider_backed",
                    VerificationPolicy: "provider_backed",
                    IsPrimary: true,
                    CreatedAtUtc: DateTimeOffset.UtcNow.AddDays(-7),
                    UpdatedAtUtc: DateTimeOffset.UtcNow.AddDays(-7),
                    VerifiedAtUtc: DateTimeOffset.UtcNow.AddDays(-7),
                    Note: "orphaned google link"));
                store.PersistLocked();
            }

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "orphaned-auth-code");
            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("issued-orphaned-google-access-token", result.Session!.AccessToken);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);

            HubUserDto? user = accounts.GetBySubject("google:google-subject-orphaned");
            Assert.NotNull(user);
            Assert.Single(store.LinkedIdentities);
            Assert.Equal(user!.UserId, store.LinkedIdentities[0].UserId);
            Assert.Equal("google", store.LinkedIdentities[0].Provider);
            Assert.Equal("google-subject-orphaned", store.LinkedIdentities[0].ProviderSubject);
            Assert.Equal("orphaned@example.com", store.LinkedIdentities[0].DisplayLabel);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncRetriesTransientGoogleTokenFailure()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    int attempt = Interlocked.Increment(ref tokenRequests);
                    if (attempt == 1)
                    {
                        return new HttpResponseMessage(HttpStatusCode.BadGateway)
                        {
                            Content = new StringContent("{\"error\":\"temporarily_unavailable\"}", Encoding.UTF8, "application/json")
                        };
                    }

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-1",
                        email: "runner@example.com",
                        emailVerified: true,
                        displayName: "Runner Prime");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    Assert.Equal("Bearer", request.Headers.Authorization?.Scheme);
                    Assert.Equal("google-access-token", request.Headers.Authorization?.Parameter);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-1",
                        email = "runner@example.com",
                        email_verified = true,
                        name = "Runner Prime"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-1",
                        subjectId = "google:google-subject-1",
                        displayName = "Runner Prime",
                        email = "runner@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-access-token",
                        refreshToken = "issued-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "retryable-auth-code");
            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("issued-access-token", result.Session!.AccessToken);
            Assert.Equal(2, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncNormalizesSpaceCorruptedAuthorizationCodeBeforeTokenExchange()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    Assert.Contains("code=space%2Bcorrupted-auth-code", formBody, StringComparison.Ordinal);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-space-code",
                        email: "spacecode@example.com",
                        emailVerified: true,
                        displayName: "Space Code");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-space-code",
                        email = "spacecode@example.com",
                        email_verified = true,
                        name = "Space Code"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-space-code",
                        subjectId = "google:google-subject-space-code",
                        displayName = "Space Code",
                        email = "spacecode@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-space-code-access-token",
                        refreshToken = "issued-space-code-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContextWithRawCodeQuery(
                challenge.StateCookieValue,
                state,
                "space+corrupted-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("issued-space-code-access-token", result.Session!.AccessToken);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncFallsBackToRawQueryAuthorizationCodeWhenParsedQueryIsCorrupted()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    Assert.Contains("code=raw%2Bpreserved-auth-code", formBody, StringComparison.Ordinal);
                    Assert.DoesNotContain("corrupted-auth-code", formBody, StringComparison.Ordinal);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-raw-code",
                        email: "rawcode@example.com",
                        emailVerified: true,
                        displayName: "Raw Code");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-raw-code",
                        email = "rawcode@example.com",
                        email_verified = true,
                        name = "Raw Code"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-raw-code",
                        subjectId = "google:google-subject-raw-code",
                        displayName = "Raw Code",
                        email = "rawcode@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-raw-code-access-token",
                        refreshToken = "issued-raw-code-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContextWithParsedQueryOverride(
                challenge.StateCookieValue,
                state,
                rawCodeQueryValue: "raw+preserved-auth-code",
                parsedCode: "corrupted-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("issued-raw-code-access-token", result.Session!.AccessToken);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncFallsBackToSecondAuthorizationCodeCandidateOnGenericInvalidGrant()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    int attempt = Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    if (attempt == 1)
                    {
                        Assert.Contains("code=first-auth-code", formBody, StringComparison.Ordinal);
                        return JsonResponse(HttpStatusCode.BadRequest, new
                        {
                            error = "invalid_grant",
                            error_description = "Bad Request"
                        });
                    }

                    Assert.Equal(2, attempt);
                    Assert.Contains("code=second-auth-code", formBody, StringComparison.Ordinal);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-fallback-code",
                        email: "fallbackcode@example.com",
                        emailVerified: true,
                        displayName: "Fallback Code");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-fallback-code",
                        email = "fallbackcode@example.com",
                        email_verified = true,
                        name = "Fallback Code"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-fallback-code",
                        subjectId = "google:google-subject-fallback-code",
                        displayName = "Fallback Code",
                        email = "fallbackcode@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-fallback-code-access-token",
                        refreshToken = "issued-fallback-code-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContextWithParsedQueryOverride(
                challenge.StateCookieValue,
                state,
                rawCodeQueryValue: "first-auth-code",
                parsedCode: "second-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("issued-fallback-code-access-token", result.Session!.AccessToken);
            Assert.Equal(2, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncReturnsErrorResultForMalformedAuthorizationCode()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = "hub-google-client",
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            int tokenRequests = 0;
            var handler = new StubHttpMessageHandler(request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                if (request.RequestUri.AbsoluteUri == "https://oauth.example.test/token")
                {
                    Interlocked.Increment(ref tokenRequests);
                    return Task.FromResult(JsonResponse(HttpStatusCode.BadRequest, new
                    {
                        error = "invalid_grant",
                        error_description = "Malformed auth code"
                    }));
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {request.RequestUri.AbsoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(new HttpClient(handler), configuration, NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/downloads");
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "malformed-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.Null(result.Session);
            Assert.Equal("/downloads", result.NextPath);
            Assert.Equal("Google sign-in code was malformed", result.ErrorTitle);
            Assert.Equal("Google returned a malformed authorization code. Start the Google sign-in flow again.", result.ErrorDetail);
            Assert.Equal(1, tokenRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncFallsBackToParsedQueryAuthorizationCodeWhenRawCallbackQueryIsMalformed()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    Assert.Contains("code=parseable-auth-code", formBody, StringComparison.Ordinal);
                    Assert.DoesNotContain("malformed", formBody, StringComparison.Ordinal);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-parsed-code",
                        email: "parsedcode@example.com",
                        emailVerified: true,
                        displayName: "Parsed Code");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-parsed-code",
                        email = "parsedcode@example.com",
                        email_verified = true,
                        name = "Parsed Code"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-parsed-code",
                        subjectId = "google:google-subject-parsed-code",
                        displayName = "Parsed Code",
                        email = "parsedcode@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-parsed-code-access-token",
                        refreshToken = "issued-parsed-code-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/downloads");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContextWithParsedQueryOverride(
                challenge.StateCookieValue,
                state,
                rawCodeQueryValue: "malformed%20code%2",
                parsedCode: "parseable-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/downloads", result.NextPath);
            Assert.Equal("issued-parsed-code-access-token", result.Session!.AccessToken);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncRedeemsLenientRawAuthorizationCodeWhenPercentEncodingIsMalformed()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    Assert.Contains("code=repairable-auth-code%252", formBody, StringComparison.Ordinal);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-repairable-code",
                        email: "repairable@example.com",
                        emailVerified: true,
                        displayName: "Repairable Code");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-repairable-code",
                        email = "repairable@example.com",
                        email_verified = true,
                        name = "Repairable Code"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-repairable-code",
                        subjectId = "google:google-subject-repairable-code",
                        displayName = "Repairable Code",
                        email = "repairable@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-repairable-code-access-token",
                        refreshToken = "issued-repairable-code-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/downloads");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContextWithParsedQueryOverride(
                challenge.StateCookieValue,
                state,
                rawCodeQueryValue: "repairable-auth-code%2",
                parsedCode: string.Empty);

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/downloads", result.NextPath);
            Assert.Equal("issued-repairable-code-access-token", result.Session!.AccessToken);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncFallsBackToLiteralRawAuthorizationCodeWhenDecodedVariantIsRejected()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    int attempt = Interlocked.Increment(ref tokenRequests);
                    string formBody = await request.Content!.ReadAsStringAsync();
                    if (attempt == 1)
                    {
                        Assert.Contains("code=opaque%2Fauth-code", formBody, StringComparison.Ordinal);
                        return JsonResponse(HttpStatusCode.BadRequest, new
                        {
                            error = "invalid_grant",
                            error_description = "Malformed auth code."
                        });
                    }

                    Assert.Equal(2, attempt);
                    Assert.Contains("code=opaque%252Fauth-code", formBody, StringComparison.Ordinal);

                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-literal-code",
                        email: "literalcode@example.com",
                        emailVerified: true,
                        displayName: "Literal Code");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-literal-code",
                        email = "literalcode@example.com",
                        email_verified = true,
                        name = "Literal Code"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    return JsonResponse(HttpStatusCode.Created, new
                    {
                        sessionId = "session-literal-code",
                        subjectId = "google:google-subject-literal-code",
                        displayName = "Literal Code",
                        email = "literalcode@example.com",
                        roles = new[] { "player" },
                        accessToken = "issued-literal-code-access-token",
                        refreshToken = "issued-literal-code-refresh-token",
                        issuedAtUtc = DateTimeOffset.UtcNow,
                        expiresAtUtc = DateTimeOffset.UtcNow.AddHours(4)
                    });
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContextWithParsedQueryOverride(
                challenge.StateCookieValue,
                state,
                rawCodeQueryValue: "opaque%2Fauth-code",
                parsedCode: string.Empty);

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.NotNull(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("issued-literal-code-access-token", result.Session!.AccessToken);
            Assert.Equal(2, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(1, sessionRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncReturnsErrorResultForRejectedAuthorizationCode()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = "hub-google-client",
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            int tokenRequests = 0;
            var handler = new StubHttpMessageHandler(request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                if (request.RequestUri.AbsoluteUri == "https://oauth.example.test/token")
                {
                    Interlocked.Increment(ref tokenRequests);
                    return Task.FromResult(JsonResponse(HttpStatusCode.BadRequest, new
                    {
                        error = "invalid_grant",
                        error_description = "Invalid authorization code"
                    }));
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {request.RequestUri.AbsoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(new HttpClient(handler), configuration, NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "rejected-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.Null(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("Google sign-in code could not be redeemed", result.ErrorTitle);
            Assert.Equal("The Google authorization code was rejected. Start a fresh Google sign-in flow and complete it in a single browser window.", result.ErrorDetail);
            Assert.Equal(1, tokenRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncReturnsErrorResultForMalformedTokenPayload()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = "hub-google-client",
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            int tokenRequests = 0;
            var handler = new StubHttpMessageHandler(request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                if (request.RequestUri.AbsoluteUri == "https://oauth.example.test/token")
                {
                    Interlocked.Increment(ref tokenRequests);
                    return Task.FromResult(JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        token_type = "Bearer",
                        expires_in = 3600
                    }));
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {request.RequestUri.AbsoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(new HttpClient(handler), configuration, NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "malformed-token-payload");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.Null(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("Google sign-in could not be completed", result.ErrorTitle);
            Assert.Equal("Google returned an invalid sign-in response. Start a fresh Google sign-in flow and try again.", result.ErrorDetail);
            Assert.Equal(1, tokenRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncReturnsErrorResultWhenTokenEndpointIsUnavailable()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = "hub-google-client",
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            int tokenRequests = 0;
            var handler = new StubHttpMessageHandler(request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                if (request.RequestUri.AbsoluteUri == "https://oauth.example.test/token")
                {
                    Interlocked.Increment(ref tokenRequests);
                    throw new HttpRequestException("Google OAuth endpoint unavailable");
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {request.RequestUri.AbsoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(new HttpClient(handler), configuration, NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "temporary-network-error");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.Null(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("Google sign-in service unavailable", result.ErrorTitle);
            Assert.Equal("Chummer could not contact Google right now. Start the Google sign-in flow again.", result.ErrorDetail);
            Assert.Equal(2, tokenRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncReturnsErrorResultWhenTokenExchangeTimesOut()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = "hub-google-client",
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            int tokenRequests = 0;
            var handler = new StubHttpMessageHandler(request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                if (request.RequestUri.AbsoluteUri == "https://oauth.example.test/token")
                {
                    Interlocked.Increment(ref tokenRequests);
                    throw new TaskCanceledException("Google OAuth endpoint timed out");
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {request.RequestUri.AbsoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(new HttpClient(handler), configuration, NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "timing-out-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.Null(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("Google sign-in timed out", result.ErrorTitle);
            Assert.Equal("The Google sign-in response took too long. Start a fresh Google sign-in flow.", result.ErrorDetail);
            Assert.Equal(2, tokenRequests);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task CompleteAsyncReturnsErrorResultWhenHubSessionCannotBeIssuedAfterGoogleSucceeds()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-google-auth-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            using RSA rsa = RSA.Create(2048);
            RSAParameters rsaParameters = rsa.ExportParameters(includePrivateParameters: true);
            string clientId = "hub-google-client";
            string nonce = string.Empty;
            int tokenRequests = 0;
            int userInfoRequests = 0;
            int signingKeyRequests = 0;
            int sessionRequests = 0;

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "admin-key",
                    ["GOOGLE_OIDC_CLIENT_ID"] = clientId,
                    ["GOOGLE_OIDC_CLIENT_SECRET"] = "google-secret",
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback",
                    ["GOOGLE_OIDC_TOKEN_ENDPOINT"] = "https://oauth.example.test/token",
                    ["GOOGLE_OIDC_USERINFO_ENDPOINT"] = "https://oauth.example.test/userinfo",
                    ["GOOGLE_OIDC_JWKS_ENDPOINT"] = "https://oauth.example.test/jwks"
                })
                .Build();

            var handler = new StubHttpMessageHandler(async request =>
            {
                if (request.RequestUri is null)
                {
                    throw new InvalidOperationException("Request URI is required for the test handler.");
                }

                string absoluteUri = request.RequestUri.AbsoluteUri;
                if (string.Equals(absoluteUri, "https://oauth.example.test/token", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref tokenRequests);
                    string idToken = CreateGoogleIdToken(
                        rsa,
                        keyId: "kid-1",
                        clientId,
                        nonce,
                        subject: "google-subject-session-gap",
                        email: "sessiongap@example.com",
                        emailVerified: true,
                        displayName: "Session Gap");

                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        access_token = "google-access-token",
                        id_token = idToken,
                        token_type = "Bearer",
                        expires_in = 3600
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/userinfo", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref userInfoRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        sub = "google-subject-session-gap",
                        email = "sessiongap@example.com",
                        email_verified = true,
                        name = "Session Gap"
                    });
                }

                if (string.Equals(absoluteUri, "https://oauth.example.test/jwks", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref signingKeyRequests);
                    return JsonResponse(HttpStatusCode.OK, new
                    {
                        keys = new[]
                        {
                            new
                            {
                                kid = "kid-1",
                                kty = "RSA",
                                alg = "RS256",
                                n = WebEncoders.Base64UrlEncode(rsaParameters.Modulus!),
                                e = WebEncoders.Base64UrlEncode(rsaParameters.Exponent!)
                            }
                        }
                    });
                }

                if (string.Equals(absoluteUri, "http://identity.test/api/v1/identity/sessions", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref sessionRequests);
                    throw new HttpRequestException("Identity session issue endpoint unavailable");
                }

                throw new InvalidOperationException($"Unexpected request URI in Google auth test: {absoluteUri}");
            });

            HubBrowserAuthService browserAuth = new(
                new HttpClient(handler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            HubGoogleAuthService google = new(
                new HttpClient(handler),
                configuration,
                browserAuth,
                links,
                accounts,
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys"))),
                NullLogger<HubGoogleAuthService>.Instance,
                new TestHostEnvironment(),
                new HubGoogleAuthReplayCoordinator());

            DefaultHttpContext startContext = new();
            startContext.Request.Scheme = "https";
            startContext.Request.Host = new HostString("hub.example.test");
            GoogleAuthChallenge challenge = google.CreateChallenge(startContext.Request, "/home");
            nonce = ReadNonceFromProtectedState(challenge.StateCookieValue, tempRoot);
            string state = QueryHelpers.ParseQuery(new Uri(challenge.RedirectUrl).Query)["state"].ToString();

            DefaultHttpContext callback = BuildCallbackContext(challenge.StateCookieValue, state, "session-gap-auth-code");

            GoogleAuthCompletionResult result = await google.CompleteAsync(callback.Request, callback.Request.Query, CancellationToken.None);

            Assert.Null(result.Session);
            Assert.Equal("/home", result.NextPath);
            Assert.Equal("Google sign-in session unavailable", result.ErrorTitle);
            Assert.Equal("Google confirmed your account, but Chummer could not finish the Hub session right now. Start the Google sign-in flow again in a moment.", result.ErrorDetail);
            Assert.Equal(1, tokenRequests);
            Assert.Equal(1, userInfoRequests);
            Assert.Equal(1, signingKeyRequests);
            Assert.Equal(2, sessionRequests);
            Assert.Empty(store.LinkedIdentities);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    private static DefaultHttpContext BuildCallbackContext(string stateCookieValue, string state, string code)
    {
        DefaultHttpContext context = new();
        context.Request.Scheme = "https";
        context.Request.Host = new HostString("hub.example.test");
        context.Request.Headers.Cookie = $"{HubGoogleAuthConstants.StateCookieName}={stateCookieValue}";
        context.Request.QueryString = new QueryString($"?state={Uri.EscapeDataString(state)}&code={Uri.EscapeDataString(code)}");
        return context;
    }

    private static DefaultHttpContext BuildCallbackContextWithRawCodeQuery(string stateCookieValue, string state, string rawCodeQueryValue)
    {
        DefaultHttpContext context = new();
        context.Request.Scheme = "https";
        context.Request.Host = new HostString("hub.example.test");
        context.Request.Headers.Cookie = $"{HubGoogleAuthConstants.StateCookieName}={stateCookieValue}";
        context.Request.QueryString = new QueryString($"?state={Uri.EscapeDataString(state)}&code={rawCodeQueryValue}");
        return context;
    }

    private static DefaultHttpContext BuildCallbackContextWithParsedQueryOverride(
        string stateCookieValue,
        string state,
        string rawCodeQueryValue,
        string parsedCode)
    {
        DefaultHttpContext context = BuildCallbackContextWithRawCodeQuery(stateCookieValue, state, rawCodeQueryValue);
        context.Features.Set<IQueryFeature>(new QueryFeature(new QueryCollection(new Dictionary<string, StringValues>
        {
            ["state"] = state,
            ["code"] = parsedCode
        })));
        return context;
    }

    private static string ReadNonceFromProtectedState(string protectedState, string tempRoot, string? state = null)
    {
        IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys")));
        string payload = dataProtection
            .CreateProtector("chummer.hub.google.state")
            .Unprotect(protectedState);
        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement root = document.RootElement;
        if (root.TryGetProperty("Attempts", out JsonElement attempts))
        {
            JsonElement attempt = state is null
                ? attempts.EnumerateArray().Last()
                : attempts.EnumerateArray().Single(candidate =>
                    string.Equals(candidate.GetProperty("State").GetString(), state, StringComparison.Ordinal));
            return attempt.GetProperty("Nonce").GetString()
                ?? throw new InvalidOperationException("Protected Google auth state did not include a nonce.");
        }

        return root.GetProperty("Nonce").GetString()
            ?? throw new InvalidOperationException("Protected Google auth state did not include a nonce.");
    }

    private static string[] ReadTrackedStatesFromProtectedState(string protectedState, string tempRoot)
    {
        IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "keys")));
        string payload = dataProtection
            .CreateProtector("chummer.hub.google.state")
            .Unprotect(protectedState);
        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement root = document.RootElement;
        if (!root.TryGetProperty("Attempts", out JsonElement attempts))
        {
            return new[]
            {
                root.GetProperty("State").GetString()
                    ?? throw new InvalidOperationException("Protected Google auth state did not include a state.")
            };
        }

        return attempts.EnumerateArray()
            .Select(attempt => attempt.GetProperty("State").GetString()
                ?? throw new InvalidOperationException("Protected Google auth state did not include a state."))
            .ToArray();
    }

    private static string CreateGoogleIdToken(
        RSA rsa,
        string keyId,
        string clientId,
        string nonce,
        string subject,
        string email,
        bool emailVerified,
        string displayName)
    {
        var header = new Dictionary<string, object?>
        {
            ["alg"] = "RS256",
            ["kid"] = keyId,
            ["typ"] = "JWT"
        };
        var payload = new Dictionary<string, object?>
        {
            ["iss"] = "https://accounts.google.com",
            ["aud"] = clientId,
            ["azp"] = clientId,
            ["nonce"] = nonce,
            ["exp"] = DateTimeOffset.UtcNow.AddMinutes(5).ToUnixTimeSeconds(),
            ["iat"] = DateTimeOffset.UtcNow.AddMinutes(-1).ToUnixTimeSeconds(),
            ["sub"] = subject,
            ["email"] = email,
            ["email_verified"] = emailVerified,
            ["name"] = displayName
        };

        string encodedHeader = WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(header)));
        string encodedPayload = WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(payload)));
        byte[] signature = rsa.SignData(
            Encoding.ASCII.GetBytes($"{encodedHeader}.{encodedPayload}"),
            HashAlgorithmName.SHA256,
            RSASignaturePadding.Pkcs1);
        return $"{encodedHeader}.{encodedPayload}.{WebEncoders.Base64UrlEncode(signature)}";
    }

    private static HttpResponseMessage JsonResponse(HttpStatusCode statusCode, object payload)
    {
        return new HttpResponseMessage(statusCode)
        {
            Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
        };
    }

    private sealed class StubHttpMessageHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> responder)
        : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => responder(request);
    }

    private static HttpResponseMessage UnexpectedRequestResponse(HttpRequestMessage request)
        => throw new InvalidOperationException($"Unexpected request URI in Google auth test: {request.RequestUri}");

    private sealed class TestHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Development;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = AppContext.BaseDirectory;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
