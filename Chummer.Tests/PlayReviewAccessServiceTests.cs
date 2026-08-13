using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PlayReviewAccessServiceTests
{
    [Fact]
    public void AccessIsDisabledByDefault()
    {
        PlayReviewAccessService service = new(new ConfigurationBuilder().Build());

        PlayReviewAuthenticationResult result = service.Authenticate(
            "reviewer",
            "password",
            "client-a",
            DateTimeOffset.UtcNow);

        Assert.False(service.Enabled);
        Assert.Equal(PlayReviewAuthenticationStatus.Disabled, result.Status);
    }

    [Fact]
    public void EnabledAccessRequiresExactSha256Configuration()
    {
        IConfiguration configuration = BuildConfiguration(passwordDigest: "not-a-sha256");

        InvalidOperationException error = Assert.Throws<InvalidOperationException>(
            () => new PlayReviewAccessService(configuration));

        Assert.Contains("64 hexadecimal", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ExactCredentialReturnsBoundPlayerPrincipal()
    {
        PlayReviewAccessService service = new(BuildConfiguration());

        PlayReviewAuthenticationResult result = service.Authenticate(
            "chummer-play-review",
            "correct horse battery staple",
            "client-a",
            DateTimeOffset.UtcNow);

        Assert.Equal(PlayReviewAuthenticationStatus.Succeeded, result.Status);
        Assert.NotNull(result.Principal);
        Assert.Equal("play-review-2026", result.Principal!.SubjectId);
        Assert.Equal("Play Reviewer", result.Principal.DisplayName);
        Assert.Equal(["player"], result.Principal.Roles);
    }

    [Fact]
    public void RepeatedFailuresThrottleOnlyTheCallingClientForTheWindow()
    {
        PlayReviewAccessService service = new(BuildConfiguration());
        DateTimeOffset now = new(2026, 8, 13, 12, 0, 0, TimeSpan.Zero);

        for (int attempt = 0; attempt < 5; attempt++)
        {
            Assert.Equal(
                PlayReviewAuthenticationStatus.Rejected,
                service.Authenticate("chummer-play-review", "wrong", "client-a", now).Status);
        }

        PlayReviewAuthenticationResult throttled = service.Authenticate(
            "chummer-play-review",
            "correct horse battery staple",
            "client-a",
            now);
        PlayReviewAuthenticationResult otherClient = service.Authenticate(
            "chummer-play-review",
            "correct horse battery staple",
            "client-b",
            now);
        PlayReviewAuthenticationResult afterWindow = service.Authenticate(
            "chummer-play-review",
            "correct horse battery staple",
            "client-a",
            now.AddMinutes(16));

        Assert.Equal(PlayReviewAuthenticationStatus.Throttled, throttled.Status);
        Assert.True(throttled.RetryAfter > TimeSpan.Zero);
        Assert.Equal(PlayReviewAuthenticationStatus.Succeeded, otherClient.Status);
        Assert.Equal(PlayReviewAuthenticationStatus.Succeeded, afterWindow.Status);
    }

    [Fact]
    public void ReviewFormNeverContainsConfiguredCredentials()
    {
        string view = File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory,
            "Fixtures",
            "AuthEntry.cshtml"));

        Assert.Contains("Use the review access details from Play Console.", view, StringComparison.Ordinal);
        Assert.Contains("type=\"password\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("correct horse battery staple", view, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PLAY_REVIEW_ACCESS_PASSWORD_SHA256", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AndroidProofPollReturnPathPreservesOnlyCanonicalPublicState()
    {
        using RSA rsa = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        string callback = "https://chummer.run/app/install-link?state=android_state-7";
        string untrustedPath = Microsoft.AspNetCore.WebUtilities.QueryHelpers.AddQueryString(
            "/account/access/install-link",
            new Dictionary<string, string?>
            {
                ["installationId"] = "android-install-7",
                ["headId"] = "android",
                ["applicationVersion"] = "0.1.0-preview.7",
                ["releaseChannel"] = "preview",
                ["platform"] = "android",
                ["arch"] = "arm64",
                ["installLinkCallbackUri"] = callback,
                ["installLinkTransport"] = "proof_poll",
                ["publicKey"] = publicKey,
                ["accessToken"] = "must-not-survive"
            });

        string sanitized = HubBrowserAuthService.SanitizeNextPath(untrustedPath);
        IReadOnlyDictionary<string, Microsoft.Extensions.Primitives.StringValues> query =
            Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(new Uri($"https://chummer.run{sanitized}").Query);

        Assert.Equal("/account/access/install-link", new Uri($"https://chummer.run{sanitized}").AbsolutePath);
        Assert.Equal("proof_poll", query["installLinkTransport"].ToString());
        Assert.Equal(publicKey, query["publicKey"].ToString());
        Assert.Equal(callback, query["installLinkCallbackUri"].ToString());
        Assert.False(query.ContainsKey("accessToken"));
    }

    [Fact]
    public void AndroidProofPollReturnPathFailsClosedForAnInvalidKey()
    {
        string path = Microsoft.AspNetCore.WebUtilities.QueryHelpers.AddQueryString(
            "/account/access/install-link",
            new Dictionary<string, string?>
            {
                ["installationId"] = "android-install-7",
                ["headId"] = "android",
                ["platform"] = "android",
                ["installLinkCallbackUri"] = "https://chummer.run/app/install-link?state=android_state-7",
                ["installLinkTransport"] = "proof_poll",
                ["publicKey"] = "not-a-public-key"
            });

        Assert.Equal("/home", HubBrowserAuthService.SanitizeNextPath(path));
    }

    private static IConfiguration BuildConfiguration(string? passwordDigest = null)
    {
        string digest = passwordDigest ?? Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes("correct horse battery staple")));
        return new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PLAY_REVIEW_ACCESS_ENABLED"] = "true",
                ["CHUMMER_PLAY_REVIEW_ACCESS_USERNAME"] = "chummer-play-review",
                ["CHUMMER_PLAY_REVIEW_ACCESS_PASSWORD_SHA256"] = digest,
                ["CHUMMER_PLAY_REVIEW_ACCESS_SUBJECT_ID"] = "play-review-2026",
                ["CHUMMER_PLAY_REVIEW_ACCESS_DISPLAY_NAME"] = "Play Reviewer"
            })
            .Build();
    }
}
