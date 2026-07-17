using Chummer.Run.Api;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace Chummer.Tests;

public sealed class PrivateResponseCacheHeadersTests
{
    [Theory]
    [InlineData("/account")]
    [InlineData("/account/")]
    [InlineData("/account/access")]
    [InlineData("/account/billing/supporter/start")]
    [InlineData("/ACCOUNT/WORK")]
    [InlineData("/api/v1/accounts")]
    [InlineData("/api/v1/accounts/me")]
    [InlineData("/API/V1/ACCOUNTS/ME/PREFERENCES")]
    public void PrivateAccountSurfacesAreClassifiedForNoStore(string path)
    {
        Assert.True(PrivateResponseCacheHeaders.IsPrivateAccountSurface(new PathString(path)));
    }

    [Theory]
    [InlineData("/")]
    [InlineData("/accounting")]
    [InlineData("/api/v1/account")]
    [InlineData("/downloads")]
    [InlineData("/downloads/install/avalonia-win-x64-installer")]
    [InlineData("/css/site.css")]
    [InlineData("/js/site.js")]
    public void PublicAndStaticSurfacesAreNotReclassifiedAsPrivateAccounts(string path)
    {
        Assert.False(PrivateResponseCacheHeaders.IsPrivateAccountSurface(new PathString(path)));
    }

    [Theory]
    [InlineData("/admin")]
    [InlineData("/admin/packages")]
    [InlineData("/admin/providers/clickrank")]
    [InlineData("/ADMIN/VISIBILITY")]
    public void PrivateAdminSurfacesAreClassifiedForNoStore(string path)
    {
        Assert.True(PrivateResponseCacheHeaders.IsPrivateAdminSurface(new PathString(path)));
    }

    [Theory]
    [InlineData("/administrator")]
    [InlineData("/api/v1/admin")]
    [InlineData("/downloads")]
    public void UnrelatedSurfacesAreNotReclassifiedAsPrivateAdmin(string path)
    {
        Assert.False(PrivateResponseCacheHeaders.IsPrivateAdminSurface(new PathString(path)));
    }

    [Fact]
    public void ApplySetsTheCompletePrivateNoStoreBoundary()
    {
        HeaderDictionary headers = new();

        PrivateResponseCacheHeaders.Apply(headers);

        Assert.Equal("private, no-store, max-age=0", headers["Cache-Control"].ToString());
        Assert.Equal("no-store, max-age=0", headers["CDN-Cache-Control"].ToString());
        Assert.Equal("no-store, max-age=0", headers["Cloudflare-CDN-Cache-Control"].ToString());
        Assert.Equal("no-store", headers["Surrogate-Control"].ToString());
        Assert.Equal("no-cache", headers["Pragma"].ToString());
        Assert.Equal("0", headers["Expires"].ToString());
    }

    [Fact]
    public void PrivateHeaderMiddlewareRunsBeforeHttpsRedirection()
    {
        string program = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));
        int privateHeaders = program.IndexOf(
            "bool requiresNoStore = RequiresNoStoreHeaders(context.Request.Path);",
            StringComparison.Ordinal);
        int httpsRedirection = program.IndexOf("app.UseHttpsRedirection();", StringComparison.Ordinal);

        Assert.True(privateHeaders >= 0, "Private response header middleware is missing.");
        Assert.True(httpsRedirection > privateHeaders,
            "HTTPS redirects must pass through the private no-store/referrer middleware.");
        Assert.Contains(
            "if (RequiresNoReferrerHeaders(context.Request.Path))",
            program,
            StringComparison.Ordinal);
        Assert.True(
            program.Split("if (RequiresNoReferrerHeaders(context.Request.Path))", StringSplitOptions.None).Length >= 3,
            "Both invalid-host and normal responses must enforce the private referrer boundary.");
        Assert.Contains("PrivateResponseCacheHeaders.IsPrivateAccountSurface(path)", program, StringComparison.Ordinal);
        Assert.Contains("PrivateResponseCacheHeaders.IsPrivateAdminSurface(path)", program, StringComparison.Ordinal);
    }
}
