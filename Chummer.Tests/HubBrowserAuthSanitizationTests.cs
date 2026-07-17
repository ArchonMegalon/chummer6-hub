using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.WebUtilities;
using Xunit;

namespace Chummer.Tests;

public sealed class HubBrowserAuthSanitizationTests
{
    [Theory]
    [InlineData("//evil.example")]
    [InlineData("/\\evil.example")]
    [InlineData("/%5Cevil.example")]
    [InlineData("/%255Cevil.example")]
    [InlineData("/%2Fevil.example")]
    [InlineData("/%252Fevil.example")]
    [InlineData("/\tevil.example")]
    [InlineData("/home\r\nLocation: https://evil.example")]
    [InlineData(" /home")]
    [InlineData("/home ")]
    public void SanitizeNextPath_rejects_non_local_backslash_control_and_decoding_variants(string candidate)
    {
        Assert.Equal("/safe", HubBrowserAuthService.SanitizeNextPath(candidate, "/safe"));
    }

    [Theory]
    [InlineData("/")]
    [InlineData("/home")]
    [InlineData("/account/access?tab=installs")]
    [InlineData("/search?q=shadow%20runner&return=%2Fhome")]
    public void SanitizeNextPath_preserves_legitimate_local_paths_and_queries(string candidate)
    {
        Assert.Equal(candidate, HubBrowserAuthService.SanitizeNextPath(candidate, "/safe"));
    }

    [Fact]
    public void Install_link_next_path_drops_top_level_and_nested_credential_material()
    {
        const string callback = "http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof&accessToken=nested-access&ticket=nested-ticket&apiKey=nested-key&unknown=nested-unknown#claimCode=fragment-claim";
        string hostile = QueryHelpers.AddQueryString(
            "/account/access/install-link",
            new Dictionary<string, string?>
            {
                ["installationId"] = "installation-safe",
                ["headId"] = "avalonia",
                ["platform"] = "windows",
                ["arch"] = "x64",
                ["installLinkCallbackUri"] = callback,
                ["accessToken"] = "top-access",
                ["ticket"] = "top-ticket",
                ["claimCode"] = "top-claim",
                ["callbackCode"] = "top-callback",
                ["apiKey"] = "top-key"
            });

        string sanitized = HubBrowserAuthService.SanitizeNextPath(hostile, "/safe");
        string repeatedlyDecoded = DecodeRepeatedly(sanitized);

        Assert.StartsWith("/account/access/install-link?", sanitized, StringComparison.Ordinal);
        Assert.Contains("installation-safe", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.Contains("state=desktop", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.Contains("nonce=callback-proof", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-access", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-ticket", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-key", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-unknown", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("fragment-claim", repeatedlyDecoded, StringComparison.Ordinal);
    }

    [Fact]
    public void Install_link_next_path_fails_closed_when_callback_is_missing_or_invalid()
    {
        Assert.Equal(
            "/safe",
            HubBrowserAuthService.SanitizeNextPath(
                "/account/access/install-link?installationId=one&installLinkCallbackUri=https%3A%2F%2Fevil.example%2Fclaim",
                "/safe"));
        Assert.Equal(
            "/safe",
            HubBrowserAuthService.SanitizeNextPath(
                "/account/access/install-link?installationId=one",
                "/safe"));
    }

    [Fact]
    public void Encoded_install_link_path_is_still_rebuilt_from_the_allowlist()
    {
        string hostile = QueryHelpers.AddQueryString(
            "/account/access/%69nstall-link",
            new Dictionary<string, string?>
            {
                ["installationId"] = "installation-safe",
                ["installLinkCallbackUri"] = "chummer://install-link?state=safe&accessToken=nested-secret",
                ["accessToken"] = "top-level-secret"
            });

        string sanitized = HubBrowserAuthService.SanitizeNextPath(hostile, "/safe");
        string repeatedlyDecoded = DecodeRepeatedly(sanitized);

        Assert.StartsWith("/account/access/install-link?", sanitized, StringComparison.Ordinal);
        Assert.Contains("installation-safe", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-level-secret", repeatedlyDecoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-secret", repeatedlyDecoded, StringComparison.Ordinal);
    }

    [Fact]
    public void Decode_depth_limit_fails_closed_even_when_final_decode_becomes_network_path()
    {
        string nested = "/evil.example";
        for (int pass = 0; pass < 16; pass++)
        {
            nested = Uri.EscapeDataString(nested);
        }

        Assert.Equal("/safe", HubBrowserAuthService.SanitizeNextPath($"/{nested}", "/safe"));
    }

    private static string DecodeRepeatedly(string value)
    {
        string decoded = value;
        for (int pass = 0; pass < 8; pass++)
        {
            string next = Uri.UnescapeDataString(decoded);
            if (string.Equals(next, decoded, StringComparison.Ordinal))
            {
                break;
            }

            decoded = next;
        }

        return decoded;
    }
}
