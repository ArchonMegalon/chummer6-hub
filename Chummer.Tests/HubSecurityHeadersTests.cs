using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace Chummer.Tests;

public sealed class HubSecurityHeadersTests
{
    [Fact]
    public void Apply_sets_one_exact_default_value_for_each_missing_header()
    {
        DefaultHttpContext context = new();

        HubSecurityHeaders.Apply(context.Response.Headers);
        HubSecurityHeaders.Apply(context.Response.Headers);

        Assert.Equal(
            HubSecurityHeaders.ContentSecurityPolicy,
            Assert.Single(context.Response.Headers["Content-Security-Policy"]));
        Assert.Equal(
            "same-origin-allow-popups",
            Assert.Single(context.Response.Headers["Cross-Origin-Opener-Policy"]));
        Assert.Equal(
            HubSecurityHeaders.PermissionsPolicy,
            Assert.Single(context.Response.Headers["Permissions-Policy"]));
        Assert.Equal(
            "strict-origin-when-cross-origin",
            Assert.Single(context.Response.Headers["Referrer-Policy"]));
        Assert.Equal(
            "max-age=31536000",
            Assert.Single(context.Response.Headers["Strict-Transport-Security"]));
        Assert.Equal(
            "nosniff",
            Assert.Single(context.Response.Headers["X-Content-Type-Options"]));
        Assert.Equal(
            "DENY",
            Assert.Single(context.Response.Headers["X-Frame-Options"]));
        Assert.Equal(
            "none",
            Assert.Single(context.Response.Headers["X-Permitted-Cross-Domain-Policies"]));
    }

    [Fact]
    public void Apply_preserves_route_specific_policies()
    {
        DefaultHttpContext context = new();
        const string routeCsp =
            "default-src 'none'; frame-src https://example.invalid; form-action 'self'";
        context.Response.Headers["Content-Security-Policy"] = routeCsp;
        context.Response.Headers["Referrer-Policy"] = "no-referrer";
        context.Response.Headers["X-Frame-Options"] = "SAMEORIGIN";

        HubSecurityHeaders.Apply(context.Response.Headers);

        Assert.Equal(
            routeCsp,
            Assert.Single(context.Response.Headers["Content-Security-Policy"]));
        Assert.Equal(
            "no-referrer",
            Assert.Single(context.Response.Headers["Referrer-Policy"]));
        Assert.Equal(
            "SAMEORIGIN",
            Assert.Single(context.Response.Headers["X-Frame-Options"]));
        Assert.Equal(
            "nosniff",
            Assert.Single(context.Response.Headers["X-Content-Type-Options"]));
    }

    [Fact]
    public void Content_security_policy_is_compatible_with_current_inline_scripts_without_weak_script_directives()
    {
        string policy = HubSecurityHeaders.ContentSecurityPolicy;

        Assert.Contains("base-uri 'self'", policy, StringComparison.Ordinal);
        Assert.Contains("frame-ancestors 'none'", policy, StringComparison.Ordinal);
        Assert.Contains("object-src 'none'", policy, StringComparison.Ordinal);
        Assert.DoesNotContain("script-src", policy, StringComparison.Ordinal);
        Assert.DoesNotContain("unsafe-inline", policy, StringComparison.Ordinal);
        Assert.DoesNotContain("unsafe-eval", policy, StringComparison.Ordinal);
    }

    [Fact]
    public void Hsts_does_not_claim_unreviewed_subdomains_or_preload()
    {
        DefaultHttpContext context = new();

        HubSecurityHeaders.Apply(context.Response.Headers);

        string hsts = Assert.Single(
            context.Response.Headers["Strict-Transport-Security"]);
        Assert.DoesNotContain("includeSubDomains", hsts, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("preload", hsts, StringComparison.OrdinalIgnoreCase);
    }
}
