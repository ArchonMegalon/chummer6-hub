using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Avatar;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Abstractions;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class AvatarGatewayCredentialPolicyTests
{
    private const string ProviderToken = "provider-token-abcdefghijklmnopqrstuvwxyz-123456";
    private const string MintToken = "mint-token-abcdefghijklmnopqrstuvwxyz-123456789";

    [TestMethod]
    public void DistinctExactCredentialsAuthorizeOnlyTheirOwnLane()
    {
        AvatarGatewayCredentialPolicy policy = Policy(ProviderToken, MintToken);
        HttpRequest provider = Request(ProviderToken);
        HttpRequest mint = Request(MintToken);

        Assert.IsTrue(policy.ProviderReady);
        Assert.IsTrue(policy.ContextMintReady);
        Assert.IsTrue(policy.IsProviderAuthorized(provider));
        Assert.IsFalse(policy.IsContextMintAuthorized(provider));
        Assert.IsTrue(policy.IsContextMintAuthorized(mint));
        Assert.IsFalse(policy.IsProviderAuthorized(mint));
    }

    [TestMethod]
    public void ReusedCredentialFailsBothLanesClosed()
    {
        AvatarGatewayCredentialPolicy policy = Policy(ProviderToken, ProviderToken);

        Assert.IsFalse(policy.ProviderReady);
        Assert.IsFalse(policy.ContextMintReady);
        Assert.IsFalse(policy.IsProviderAuthorized(Request(ProviderToken)));
        Assert.IsFalse(policy.IsContextMintAuthorized(Request(ProviderToken)));
    }

    [TestMethod]
    public void CookieQueryOrMissingNoStoreRejectsProviderCall()
    {
        AvatarGatewayCredentialPolicy policy = Policy(ProviderToken, MintToken);
        HttpRequest cookie = Request(ProviderToken);
        cookie.Headers.Cookie = "session=forbidden";
        HttpRequest query = Request(ProviderToken);
        query.QueryString = new QueryString("?leak=true");
        HttpRequest cached = Request(ProviderToken);
        cached.Headers.Remove("Cache-Control");

        Assert.IsFalse(policy.IsProviderAuthorized(cookie));
        Assert.IsFalse(policy.IsProviderAuthorized(query));
        Assert.IsFalse(policy.IsProviderAuthorized(cached));
    }

    [TestMethod]
    public void Process_local_gateway_fails_ready_closed_without_an_explicit_single_replica_contract()
    {
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [AvatarGatewayCredentialPolicy.ProviderServiceTokenConfigurationKey] = ProviderToken,
            [AvatarGatewayCredentialPolicy.ContextMintServiceTokenConfigurationKey] = MintToken,
            [AvatarGatewayCredentialPolicy.ContextStoreModeConfigurationKey] =
                AvatarGatewayCredentialPolicy.ProcessLocalSingleReplicaMode,
            [AvatarGatewayCredentialPolicy.ReplicaCountConfigurationKey] = "2"
        }).Build();
        AvatarGatewayCredentialPolicy policy = new(configuration);

        Assert.IsFalse(policy.ProviderReady);
        Assert.IsFalse(policy.ContextMintReady);
        Assert.IsFalse(policy.IsProviderAuthorized(Request(ProviderToken)));
    }

    [TestMethod]
    public async Task Authorization_filter_runs_before_binding_and_sets_private_error_headers()
    {
        AvatarGatewayCredentialPolicy policy = Policy(ProviderToken, MintToken);
        DefaultHttpContext http = new();
        http.Request.Path = "/api/v1/avatar/rules/resolve";
        http.Request.Headers.Authorization = "Bearer wrong-token-abcdefghijklmnopqrstuvwxyz-123456";
        http.Request.Headers.CacheControl = "no-store";
        AuthorizationFilterContext context = FilterContext(http);

        await new AvatarGatewayAuthorizationFilter(policy).OnAuthorizationAsync(context);

        Assert.IsInstanceOfType<ObjectResult>(context.Result);
        Assert.AreEqual(StatusCodes.Status401Unauthorized, ((ObjectResult)context.Result).StatusCode);
        Assert.AreEqual("no-store, max-age=0", http.Response.Headers.CacheControl.ToString());
        Assert.AreEqual("no-referrer", http.Response.Headers["Referrer-Policy"].ToString());
    }

    [TestMethod]
    public async Task Authorization_filter_allows_only_the_correct_credential_lane()
    {
        AvatarGatewayCredentialPolicy policy = Policy(ProviderToken, MintToken);
        DefaultHttpContext provider = new();
        provider.Request.Path = "/api/v1/avatar/context";
        provider.Request.Headers.Authorization = "Bearer " + ProviderToken;
        provider.Request.Headers.CacheControl = "no-store";
        AuthorizationFilterContext providerContext = FilterContext(provider);
        DefaultHttpContext administration = new();
        administration.Request.Path = "/api/internal/avatar/contexts";
        administration.Request.Headers.Authorization = "Bearer " + ProviderToken;
        administration.Request.Headers.CacheControl = "no-store";
        AuthorizationFilterContext administrationContext = FilterContext(administration);

        AvatarGatewayAuthorizationFilter filter = new(policy);
        await filter.OnAuthorizationAsync(providerContext);
        await filter.OnAuthorizationAsync(administrationContext);

        Assert.IsNull(providerContext.Result);
        Assert.AreEqual(StatusCodes.Status401Unauthorized, ((ObjectResult)administrationContext.Result!).StatusCode);
    }

    private static AvatarGatewayCredentialPolicy Policy(string provider, string mint)
        => new(new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [AvatarGatewayCredentialPolicy.ProviderServiceTokenConfigurationKey] = provider,
            [AvatarGatewayCredentialPolicy.ContextMintServiceTokenConfigurationKey] = mint,
            [AvatarGatewayCredentialPolicy.ContextStoreModeConfigurationKey] =
                AvatarGatewayCredentialPolicy.ProcessLocalSingleReplicaMode,
            [AvatarGatewayCredentialPolicy.ReplicaCountConfigurationKey] = "1"
        }).Build());

    private static HttpRequest Request(string token)
    {
        DefaultHttpContext context = new();
        context.Request.Headers.Authorization = "Bearer " + token;
        context.Request.Headers.CacheControl = "no-store";
        return context.Request;
    }

    private static AuthorizationFilterContext FilterContext(HttpContext http)
        => new(
            new ActionContext(
                http,
                new RouteData(),
                new ActionDescriptor(),
                new ModelStateDictionary()),
            new List<IFilterMetadata>());
}
