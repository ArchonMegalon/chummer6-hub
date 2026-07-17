using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class HubGoogleAuthStateCookieCleanupTests
{
    [Fact]
    public void ClearStateCookieDeletesHostOnlyAndCanonicalDomainVariants()
    {
        var service = CreateService(new Dictionary<string, string?>
        {
            ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback",
        });
        var context = new DefaultHttpContext();
        context.Request.Scheme = "https";
        context.Request.Host = new HostString("chummer.run");

        service.ClearStateCookie(context.Request, context.Response);

        string?[] setCookieValues = context.Response.Headers.SetCookie.ToArray();
        Assert.Equal(2, setCookieValues.Length);
        Assert.All(setCookieValues, value => Assert.NotNull(value));
        Assert.Contains(setCookieValues, value =>
            value is not null
            && value.Contains("chummer_google_auth_state=", StringComparison.Ordinal)
            && value.Contains("expires=Thu, 01 Jan 1970 00:00:00 GMT", StringComparison.OrdinalIgnoreCase)
            && !value.Contains("domain=", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(setCookieValues, value =>
            value is not null
            && value.Contains("chummer_google_auth_state=", StringComparison.Ordinal)
            && value.Contains("domain=chummer.run", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ClearStateCookieDoesNotEmitInvalidLocalhostDomainVariant()
    {
        var service = CreateService(new Dictionary<string, string?>
        {
            ["GOOGLE_OIDC_REDIRECT_URI"] = "http://localhost:5000/auth/google/callback",
        });
        var context = new DefaultHttpContext();
        context.Request.Scheme = "http";
        context.Request.Host = new HostString("localhost", 5000);

        service.ClearStateCookie(context.Request, context.Response);

        string?[] setCookieValues = context.Response.Headers.SetCookie.ToArray();
        Assert.Single(setCookieValues);
        Assert.All(setCookieValues, value => Assert.NotNull(value));
        Assert.DoesNotContain(setCookieValues, value =>
            value is not null
            && value.Contains("domain=", StringComparison.OrdinalIgnoreCase));
    }

    private static HubGoogleAuthService CreateService(IReadOnlyDictionary<string, string?> settings)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(settings)
            .Build();
        return new HubGoogleAuthService(
            new HttpClient(),
            configuration,
            new HubBrowserAuthService(new HttpClient(), configuration),
            links: null!,
            accounts: null!,
            new EphemeralDataProtectionProvider(),
            NullLogger<HubGoogleAuthService>.Instance,
            new FakeHostEnvironment());
    }

    private sealed class FakeHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Production;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = RepoPaths.Root;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
