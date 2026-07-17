using System.Net;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class HubIdentityClientFreshAuthorizationTests
{
    [Theory]
    [InlineData("admin")]
    [InlineData("operator")]
    public async Task FreshPrivilegedResolutionRejectsRevokedRoleWithoutWaitingForCacheExpiry(
        string privilegedRole)
    {
        var handler = new MutableIdentityHandler([privilegedRole]);
        using var httpClient = new HttpClient(handler);
        HubIdentityClient identity = CreateIdentityClient(httpClient);
        HttpRequest request = CreateAuthenticatedRequest();

        AuthenticatedHubSubject initial = await identity.RequireSubjectAsync(request, CancellationToken.None);
        Assert.True(ReleaseUploadAccessPolicy.CanAccess(initial));
        Assert.Equal(1, handler.IntrospectionCalls);

        handler.Roles = ["player"];
        AuthenticatedHubSubject normallyCached = await identity.RequireSubjectAsync(request, CancellationToken.None);
        Assert.True(ReleaseUploadAccessPolicy.CanAccess(normallyCached));
        Assert.Equal(1, handler.IntrospectionCalls);

        AuthenticatedHubSubject fresh = await identity.RequireFreshSubjectAsync(request, CancellationToken.None);
        Assert.False(ReleaseUploadAccessPolicy.CanAccess(fresh));
        Assert.Equal(2, handler.IntrospectionCalls);

        AuthenticatedHubSubject refreshedCache = await identity.RequireSubjectAsync(request, CancellationToken.None);
        Assert.False(ReleaseUploadAccessPolicy.CanAccess(refreshedCache));
        Assert.Equal(2, handler.IntrospectionCalls);
    }

    [Fact]
    public async Task FreshPrivilegedResolutionEvictsAnInactiveCachedSession()
    {
        var handler = new MutableIdentityHandler(["admin"]);
        using var httpClient = new HttpClient(handler);
        HubIdentityClient identity = CreateIdentityClient(httpClient);
        HttpRequest request = CreateAuthenticatedRequest();

        AuthenticatedHubSubject initial = await identity.RequireSubjectAsync(request, CancellationToken.None);
        Assert.True(ReleaseUploadAccessPolicy.CanAccess(initial));

        handler.Active = false;
        HubRequestAuthException freshFailure = await Assert.ThrowsAsync<HubRequestAuthException>(
            () => identity.RequireFreshSubjectAsync(request, CancellationToken.None));
        Assert.Equal(StatusCodes.Status401Unauthorized, freshFailure.StatusCode);

        HubRequestAuthException cachedFailure = await Assert.ThrowsAsync<HubRequestAuthException>(
            () => identity.RequireSubjectAsync(request, CancellationToken.None));
        Assert.Equal(StatusCodes.Status401Unauthorized, cachedFailure.StatusCode);
        Assert.Equal(3, handler.IntrospectionCalls);
    }

    private static HubIdentityClient CreateIdentityClient(HttpClient httpClient)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid",
                ["CHUMMER_IDENTITY_SUBJECT_CACHE_SECONDS"] = "300"
            })
            .Build();
        return new HubIdentityClient(
            httpClient,
            configuration,
            NullLogger<HubIdentityClient>.Instance,
            new HubIdentitySubjectCache());
    }

    private static HttpRequest CreateAuthenticatedRequest()
    {
        var context = new DefaultHttpContext();
        context.Request.Host = new HostString("chummer.run");
        context.Request.Headers.Authorization = string.Concat("Bear", "er ", "privileged-session-token");
        return context.Request;
    }

    private sealed class MutableIdentityHandler(IReadOnlyList<string> initialRoles) : HttpMessageHandler
    {
        private int _introspectionCalls;

        public bool Active { get; set; } = true;

        public IReadOnlyList<string> Roles { get; set; } = initialRoles;

        public int IntrospectionCalls => Volatile.Read(ref _introspectionCalls);

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.RequestUri?.AbsolutePath.EndsWith(
                    "/api/v1/identity/introspect",
                    StringComparison.Ordinal) == true)
            {
                Interlocked.Increment(ref _introspectionCalls);
                return Task.FromResult(JsonResponse(new IdentityIntrospectionResponse(
                    Active,
                    SessionId: Active ? "session.privileged" : null,
                    SubjectId: Active ? "subject.privileged" : null,
                    Roles: Active ? Roles : null,
                    ExpiresAtUtc: Active ? DateTimeOffset.UtcNow.AddHours(1) : null)));
            }

            if (request.RequestUri?.AbsolutePath.EndsWith(
                    "/api/v1/identity/subjects/subject.privileged",
                    StringComparison.Ordinal) == true)
            {
                return Task.FromResult(JsonResponse(new IdentitySubjectResponse(
                    SubjectId: "subject.privileged",
                    DisplayName: "Privileged operator",
                    Email: "operator@example.invalid",
                    Roles,
                    UpdatedAtUtc: DateTimeOffset.UtcNow)));
            }

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
        }

        private static HttpResponseMessage JsonResponse<T>(T payload)
            => new(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    JsonSerializer.Serialize(payload),
                    Encoding.UTF8,
                    "application/json")
            };
    }
}
