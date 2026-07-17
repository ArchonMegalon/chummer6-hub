using System.Net;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicPlayProxyGatewayTests
{
    [Fact]
    public async Task DisabledProjectionIsReadyAndEveryPathFallsThroughLocally()
    {
        PublicPlayProxyGateway gateway = CreateGateway(enabled: false);
        var context = new DefaultHttpContext();
        context.Request.Path = "/mobile/player";

        PublicPlayProjectionReadiness readiness = gateway.GetReadiness();
        PublicPlayProxyDisposition disposition = await gateway.TryHandleAsync(context, CancellationToken.None);

        Assert.True(readiness.Ready);
        Assert.False(readiness.Enabled);
        Assert.Equal("disabled", readiness.Status);
        Assert.Equal(PublicPlayProxyDisposition.NotMatched, disposition);
        Assert.Empty(PublicPlayProxyGateway.PublicPaths);
    }

    [Fact]
    public async Task InvalidEnabledProjectionIsUnreadyButStillFallsThroughLocally()
    {
        PublicPlayProxyGateway gateway = CreateGateway(
            enabled: true,
            upstream: "http://127.0.0.1:8080/");
        var context = new DefaultHttpContext();
        context.Request.Path = "/mobile/gm";

        PublicPlayProjectionReadiness readiness = gateway.GetReadiness();
        PublicPlayProxyDisposition disposition = await gateway.TryHandleAsync(context, CancellationToken.None);

        Assert.False(readiness.Ready);
        Assert.Equal("projection_disabled_invalid_configuration", readiness.Status);
        Assert.Equal(PublicPlayProxyDisposition.NotMatched, disposition);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Fact]
    public void RecursiveCanonicalOriginIsRejected()
    {
        IConfiguration configuration = Configuration(
            enabled: true,
            upstream: "https://chummer.run/",
            allowedOrigins: "https://chummer.run/");
        PublicCanonicalOriginPolicy publicOrigin = PublicCanonicalOriginPolicy.CreateUnitTestDefault(configuration);

        Assert.False(DormantPublicPlayProjectionConfigurationPolicy.TryResolveDormantOriginForReadiness(
            configuration,
            publicOrigin.CanonicalOrigin,
            out _));
    }

    [Fact]
    public void NonRecursiveValidProjectionFlagIsStillUnreadyBecauseProjectionIsRetired()
    {
        PublicPlayProxyGateway gateway = CreateGateway(
            enabled: true,
            upstream: "https://play.example/",
            allowedOrigins: "https://play.example/");

        PublicPlayProjectionReadiness readiness = gateway.GetReadiness();

        Assert.False(readiness.Ready);
        Assert.Equal("projection_retired_local_mirror_only", readiness.Status);
    }

    [Theory]
    [InlineData("http://play.example/")]
    [InlineData("https://127.0.0.1/")]
    [InlineData("https://[::1]/")]
    [InlineData("https://play.example/private/")]
    [InlineData("https://user:secret@play.example/")]
    [InlineData("https://play.example/?next=private")]
    [InlineData("https://other.example/")]
    public void UpstreamMustBeAnAllowlistedQueryFreeHttpsOrigin(string upstream)
    {
        IConfiguration configuration = Configuration(
            enabled: true,
            upstream: upstream,
            allowedOrigins: "https://play.example/");

        Assert.False(DormantPublicPlayProjectionConfigurationPolicy.TryResolveDormantOriginForReadiness(configuration, out _));
    }

    [Theory]
    [InlineData("127.0.0.1")]
    [InlineData("10.0.0.1")]
    [InlineData("100.64.0.1")]
    [InlineData("169.254.169.254")]
    [InlineData("172.16.0.1")]
    [InlineData("192.168.0.1")]
    [InlineData("192.88.99.1")]
    [InlineData("198.18.0.1")]
    [InlineData("::1")]
    [InlineData("::192.0.2.1")]
    [InlineData("64:ff9b::1")]
    [InlineData("100::1")]
    [InlineData("fe80::1")]
    [InlineData("fc00::1")]
    [InlineData("2001::1")]
    [InlineData("2001:2::1")]
    [InlineData("2001:10::1")]
    [InlineData("2001:20::1")]
    [InlineData("2001:db8::1")]
    [InlineData("2002::1")]
    [InlineData("2620:4f:8000::1")]
    [InlineData("3fff::1")]
    public void PrivateSpecialAndReservedAddressesAreRejected(string value)
        => Assert.False(DormantPublicPlayProjectionConfigurationPolicy.IsPublicAddressIfTransportIsEverRestored(IPAddress.Parse(value)));

    [Theory]
    [InlineData("1.1.1.1")]
    [InlineData("8.8.8.8")]
    [InlineData("2606:4700:4700::1111")]
    public void PublicAddressesAreAccepted(string value)
        => Assert.True(DormantPublicPlayProjectionConfigurationPolicy.IsPublicAddressIfTransportIsEverRestored(IPAddress.Parse(value)));

    private static PublicPlayProxyGateway CreateGateway(
        bool enabled,
        string upstream = "https://play.example/",
        string allowedOrigins = "https://play.example/")
    {
        IConfiguration configuration = Configuration(enabled, upstream, allowedOrigins);
        return new PublicPlayProxyGateway(
            configuration,
            PublicCanonicalOriginPolicy.CreateUnitTestDefault(configuration),
            NullLogger<PublicPlayProxyGateway>.Instance);
    }

    private static IConfiguration Configuration(
        bool enabled,
        string upstream,
        string allowedOrigins)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                [PublicPlayProxyGateway.EnabledConfigurationKey] = enabled.ToString(),
                [PublicPlayProxyGateway.UpstreamConfigurationKey] = upstream,
                [DormantPublicPlayProjectionConfigurationPolicy.AllowedOriginsConfigurationKey] = allowedOrigins,
                [PublicCanonicalOriginPolicy.AllowedHostsConfigurationKey] = "chummer.run",
                [PublicCanonicalOriginPolicy.CanonicalOriginConfigurationKey] = "https://chummer.run"
            })
            .Build();
}
