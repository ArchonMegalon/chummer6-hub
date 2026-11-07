using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.WebUtilities;
using System.Security.Cryptography;
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
    public void Preview11_proof_poll_transport_survives_login_return_sanitization_exactly()
    {
        using RSA key = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(key.ExportSubjectPublicKeyInfo());
        string nextPath = HubBrowserAuthService.BuildInstallLinkingNextPath(
            "android-preview11",
            "android",
            "0.1.0-preview.11",
            "preview",
            "android",
            "arm64",
            "https://chummer.run/app/install-link?state=preview11-state",
            "proof_poll_v2",
            publicKey);

        string sanitized = HubBrowserAuthService.SanitizeNextPath(nextPath, "/safe");
        IReadOnlyDictionary<string, Microsoft.Extensions.Primitives.StringValues> query =
            QueryHelpers.ParseQuery(new Uri($"https://chummer.run{sanitized}").Query);

        Assert.Equal("proof_poll_v2", Assert.Single(query["installLinkTransport"]));
        Assert.Equal(publicKey, Assert.Single(query["publicKey"]));
    }

    [Fact]
    public void Desktop_proof_poll_transport_survives_login_return_sanitization_exactly()
    {
        using RSA key = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(key.ExportSubjectPublicKeyInfo());
        string nextPath = HubBrowserAuthService.BuildInstallLinkingNextPath(
            "desktop-preview11",
            "avalonia",
            "6.0.1-preview",
            "preview",
            "windows",
            "x64",
            "chummer://install-link?state=desktop-state",
            "proof_poll",
            publicKey);

        string sanitized = HubBrowserAuthService.SanitizeNextPath(nextPath, "/safe");
        IReadOnlyDictionary<string, Microsoft.Extensions.Primitives.StringValues> query =
            QueryHelpers.ParseQuery(new Uri($"https://chummer.run{sanitized}").Query);

        Assert.Equal("proof_poll", Assert.Single(query["installLinkTransport"]));
        Assert.Equal(publicKey, Assert.Single(query["publicKey"]));
    }

    [Theory]
    [InlineData("chummer://install-link")]
    [InlineData("http://127.0.0.1:47761/install-link/callback")]
    [InlineData("https://localhost:47761/install-link/callback")]
    public void Desktop_proof_poll_callback_preserves_bounded_state_and_drops_credentials(string callbackBase)
    {
        string callback = callbackBase
            + "?state=desktop-state&nonce=callback-proof&accessToken=prior-access&callbackCode=foreign-code"
            + "&authorization=prior-auth&apiKey=prior-key&ticket=prior-ticket&unknown=prior-unknown";
        string sanitized = Assert.IsType<string>(HubBrowserAuthService.SanitizeProofPollCallbackUri(callback));
        var query = QueryHelpers.ParseQuery(new Uri(sanitized).Query);

        Assert.Equal(2, query.Count);
        Assert.Equal("desktop-state", Assert.Single(query["state"]));
        Assert.Equal("callback-proof", Assert.Single(query["nonce"]));
        Assert.DoesNotContain("prior-", sanitized, StringComparison.Ordinal);
        Assert.DoesNotContain("foreign-code", sanitized, StringComparison.Ordinal);

        using RSA key = RSA.Create(2048);
        string next = QueryHelpers.AddQueryString("/account/access/install-link", new Dictionary<string, string?>
        {
            ["installationId"] = "desktop-state-install",
            ["installLinkCallbackUri"] = callback,
            ["installLinkTransport"] = "proof_poll",
            ["publicKey"] = Convert.ToBase64String(key.ExportSubjectPublicKeyInfo())
        });
        string safeNext = HubBrowserAuthService.SanitizeNextPath(next, "/safe");
        var nextQuery = QueryHelpers.ParseQuery(new Uri("https://chummer.run" + safeNext).Query);
        Assert.Equal(sanitized, Assert.Single(nextQuery["installLinkCallbackUri"]));
        Assert.DoesNotContain("prior-", DecodeRepeatedly(safeNext), StringComparison.Ordinal);
        Assert.DoesNotContain("foreign-code", DecodeRepeatedly(safeNext), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("state=a&state=b")]
    [InlineData("state=a&STATE=b")]
    [InlineData("state=")]
    [InlineData("state=unsafe%20state")]
    [InlineData("state=unsafe%26token%3Dvalue")]
    [InlineData("state=unsafe%0Astate")]
    [InlineData("state=unsafe%5Cstate")]
    [InlineData("state=safe&nonce=a&nonce=b")]
    [InlineData("state=safe&nonce=unsafe%20nonce")]
    public void Desktop_proof_poll_callback_rejects_duplicate_or_unsafe_state(string query)
    {
        foreach (string callbackBase in new[] { "chummer://install-link", "http://127.0.0.1:47761/install-link/callback" })
        {
            Assert.Null(HubBrowserAuthService.SanitizeProofPollCallbackUri(callbackBase + "?" + query));
        }
    }

    [Theory]
    [InlineData("chummer://install-link")]
    [InlineData("http://127.0.0.1:47761/install-link/callback")]
    public void Desktop_proof_poll_callback_enforces_existing_state_length_limit(string callbackBase)
    {
        string state = new('a', 128);
        string sanitized = Assert.IsType<string>(HubBrowserAuthService.SanitizeProofPollCallbackUri(callbackBase + "?state=" + state));
        Assert.Equal(state, Assert.Single(QueryHelpers.ParseQuery(new Uri(sanitized).Query)["state"]));
        Assert.Null(HubBrowserAuthService.SanitizeProofPollCallbackUri(callbackBase + "?state=" + state + "a"));
    }

    [Theory]
    [InlineData("chummer://install-link", "chummer://install-link/")]
    [InlineData("http://127.0.0.1:47761/install-link/callback", "http://127.0.0.1:47761/install-link/callback")]
    public void Desktop_proof_poll_callback_keeps_current_no_state_client_contract(string callback, string expected)
    {
        Assert.Equal(expected, HubBrowserAuthService.SanitizeProofPollCallbackUri(callback));
        Assert.Equal(expected, HubBrowserAuthService.SanitizeProofPollCallbackUri(callback + "?accessToken=prior&callbackCode=foreign"));
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
