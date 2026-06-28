using System.Net.Http.Headers;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
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
