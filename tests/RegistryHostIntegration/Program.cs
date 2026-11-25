using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Publication;
using Chummer.Run.Contracts.Registry;
using Chummer.Run.Registry.Controllers;
using Chummer.Run.Registry.Services;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.ApplicationParts;
using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.AspNetCore.Mvc.Infrastructure;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Http;
using Microsoft.Extensions.Logging;

// Dedicated process, launched with an empty environment by run-isolated.sh.
// No substitute Program, routing, authentication, policies, controllers or stores.
string root = Environment.GetEnvironmentVariable("CHUMMER_REGISTRY_HOST_TEST_ROOT")
    ?? throw new InvalidOperationException("Use run-isolated.sh with a built verifier.");
Directory.SetCurrentDirectory(root);
Directory.CreateDirectory(Path.Combine(root, "wwwroot"));
if (typeof(HubRegistryController).Assembly.GetType("Chummer.Run.Registry.Services.RegistryReadAccess") is null)
    throw new InvalidOperationException("Fixed Registry packages are required before executing this verifier.");

var configuration = IsolatedConfiguration.Create(root);
await File.WriteAllTextAsync("appsettings.json", JsonSerializer.Serialize(configuration));
await using var app = new HubFactory(root, configuration);
using HttpClient client = app.CreateClient(new WebApplicationFactoryClientOptions
{
    BaseAddress = new Uri("http://localhost"), AllowAutoRedirect = false, HandleCookies = false
});
client.Timeout = TimeSpan.FromSeconds(15);

var parts = app.Services.GetRequiredService<ApplicationPartManager>();
Check(parts.ApplicationParts.OfType<AssemblyPart>().Any(p => p.Assembly == typeof(HubRegistryController).Assembly),
    "Registry runtime assembly is an MVC application part");
var actions = app.Services.GetRequiredService<IActionDescriptorCollectionProvider>().ActionDescriptors.Items
    .OfType<ControllerActionDescriptor>().ToArray();
foreach (Type type in new[] { typeof(HubRegistryController), typeof(PublicationsController), typeof(HubPublicationDraftsController) })
    Check(actions.Any(a => a.ControllerTypeInfo.AsType() == type), $"Real host exposes {type.Name}");
Check(app.Services.GetRequiredService<IHubArtifactStore>() is FileBackedHubArtifactStore, "Real persistent Registry store");
Check(app.Services.GetRequiredService<IPublicationWorkflowService>() is PublicationWorkflowService, "Real publication workflow");
Check(app.Services.GetRequiredService<IHubPublicationDraftService>() is HubPublicationDraftService, "Real draft workflow");

var accounts = app.Services.GetRequiredService<AccountService>();
string owner = accounts.EnsureUser("subject.owner", "Synthetic owner").UserId;
string other = accounts.EnsureUser("subject.other", "Synthetic other").UserId;
Check(owner != "subject.owner", "Owner identifier differs from upstream subject");
app.Identity.AccountId = owner;

string publicId = await CreateArtifact("public", owner, ArtifactVisibilityModes.Public);
string privateId = await CreateArtifact("private", owner, ArtifactVisibilityModes.Private);
string otherId = await CreateArtifact("other", other, ArtifactVisibilityModes.Private);
string campaignId = await CreateArtifact("campaign", owner, ArtifactVisibilityModes.CampaignShared);
string serviceId = await CreateArtifact("service-collision", "registry-control", ArtifactVisibilityModes.Private);
string subjectId = await CreateArtifact("subject-collision", "subject.owner", ArtifactVisibilityModes.Private);
string hiddenId = await CreateArtifact("hidden", owner, ArtifactVisibilityModes.Public);
await Send(HttpMethod.Patch, $"/api/v1/registry/artifacts/{hiddenId}/state", HttpStatusCode.OK,
    new HubArtifactStateChangeRequest("synthetic-control", HubArtifactState.Delisted, null, "fixture"), control: true);

// All public artifact detail/projection aliases must use the authenticated account.
foreach (string suffix in new[] { "", "/preview", "/projection", "/install-projection" })
{
    string path = $"/api/v1/registry/artifacts/{privateId}{suffix}";
    await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{publicId}{suffix}", HttpStatusCode.OK);
    await Send(HttpMethod.Get, path, HttpStatusCode.NotFound);
    await Send(HttpMethod.Get, path, HttpStatusCode.OK, bearer: "owner-session");
    await Send(HttpMethod.Get, path, HttpStatusCode.OK, cookie: "owner-session");
    await Send(HttpMethod.Get, path, HttpStatusCode.NotFound, bearer: "other-session");
    await Send(HttpMethod.Get, path, HttpStatusCode.Unauthorized, bearer: "invalid-session");
    await Send(HttpMethod.Get, path + $"?ownerId={owner}", HttpStatusCode.NotFound, forgedOwner: owner);
}
await Send(HttpMethod.Get, $"/api/v1/registry/{privateId}/preview", HttpStatusCode.OK, bearer: "owner-session");
await Send(HttpMethod.Get, $"/api/v1/registry/{privateId}/preview", HttpStatusCode.NotFound);
foreach (string id in new[] { serviceId, subjectId, otherId })
    await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{id}", HttpStatusCode.NotFound, bearer: "owner-session");
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{serviceId}", HttpStatusCode.NotFound, control: true);
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.OK, control: true, cookie: "owner-session");
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{publicId}", HttpStatusCode.OK, bearer: HubFactory.ControlKey);
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.NotFound, bearer: HubFactory.ControlKey);
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{serviceId}", HttpStatusCode.NotFound, bearer: HubFactory.ControlKey);
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{publicId}", HttpStatusCode.OK, control: true, bearer: HubFactory.ControlKey);
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.NotFound, control: true, bearer: "owner-session");
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.Unauthorized, cookie: "invalid-session");
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.Forbidden, bearer: "unlinked-session");
Check(accounts.GetBySubject("subject.unlinked") is null, "Reads do not create an account");
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.Forbidden, bearer: "account-as-subject");
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.ServiceUnavailable, bearer: "identity-unavailable");
app.Identity.OwnerRevoked = true;
await Send(HttpMethod.Get, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.Unauthorized, bearer: "owner-session");
app.Identity.OwnerRevoked = false;

foreach (string path in new[] { "/api/v1/registry/search", "/api/v1/registry/artifacts", "/api/v1/registry/projections" })
{
    await CheckList(path + "?pageSize=1", null, [publicId], total: 1);
    await CheckList(path + "?pageSize=100", "owner-session", [publicId, privateId, campaignId, hiddenId], total: 4);
    await CheckList(path + "?pageSize=100", "other-session", [publicId, otherId], total: 2);
    await CheckList(path + "?shelfAudience=owner-only", null, [], total: 0);
    await CheckList(path + "?shelfAudience=campaign", null, [], total: 0);
}
await CheckList("/api/v1/registry/artifacts/state/Active", null, [publicId], total: 1);
await CheckList("/api/v1/registry/artifacts/state/Delisted", null, [], total: 0);
await CheckList("/api/v1/registry/artifacts/state/Delisted", "owner-session", [hiddenId], total: 1);

// Publication owner access derives from stored artifact ownership, not SubmittedBy.
string privatePublication = await Submit(privateId, other);
string publicPublication = await Submit(publicId, owner);
await Send(HttpMethod.Get, $"/api/v1/publications/{publicPublication}", HttpStatusCode.NotFound);
using (var pending = await Send(HttpMethod.Get, $"/api/v1/publications/{publicPublication}", HttpStatusCode.OK, bearer: "owner-session"))
using (var reviewed = await Send(HttpMethod.Post, $"/api/v1/publications/{publicPublication}/review", HttpStatusCode.OK,
    new PublicationReviewRequest("synthetic-reviewer", true), control: true,
    ifMatch: pending.RootElement.GetProperty("concurrencyToken").GetString()))
{
    await Send(HttpMethod.Post, $"/api/v1/publications/{publicPublication}/publish", HttpStatusCode.OK,
        new PublicationPublishRequest("synthetic-publisher"), control: true,
        ifMatch: reviewed.RootElement.GetProperty("concurrencyToken").GetString());
}
await Send(HttpMethod.Get, $"/api/v1/publications/{publicPublication}", HttpStatusCode.OK);
await Send(HttpMethod.Get, $"/api/v1/publications/{privatePublication}", HttpStatusCode.NotFound);
await Send(HttpMethod.Get, $"/api/v1/publications/{privatePublication}", HttpStatusCode.OK, bearer: "owner-session");
await Send(HttpMethod.Get, $"/api/v1/publications/{privatePublication}", HttpStatusCode.NotFound, bearer: "other-session");
using (JsonDocument anonymous = await Send(HttpMethod.Get, "/api/v1/publications", HttpStatusCode.OK))
    Check(anonymous.RootElement.GetArrayLength() == 1, "Anonymous publication list excludes private workflow");
using (JsonDocument owned = await Send(HttpMethod.Get, "/api/v1/publications", HttpStatusCode.OK, bearer: "owner-session"))
    Check(owned.RootElement.GetArrayLength() == 2, "Owner publication list includes private workflow");

// Exercise control boundaries through actual middleware, not forged principals.
foreach (string? token in new string?[] { null, "owner-session", "invalid-session" })
{
    await Send(HttpMethod.Get, "/api/v1/publication-drafts", HttpStatusCode.Unauthorized, bearer: token);
    await Send(HttpMethod.Get, "/api/v1/registry/projections/pipelines", HttpStatusCode.Unauthorized, bearer: token);
    await Send(HttpMethod.Get, "/api/v1/registry/runtime-bundles/heads/test/test", HttpStatusCode.Unauthorized, bearer: token);
    await Send(HttpMethod.Post, "/api/v1/registry/artifacts", HttpStatusCode.Unauthorized,
        new HubArtifactCreateRequest("denied", HubArtifactKind.BuildKit, "1"), bearer: token);
    await Send(HttpMethod.Patch, $"/api/v1/registry/artifacts/{privateId}/state", HttpStatusCode.Unauthorized,
        new HubArtifactStateChangeRequest(owner, HubArtifactState.Delisted, null, "denied"), bearer: token);
    await Send(HttpMethod.Delete, $"/api/v1/registry/artifacts/{privateId}", HttpStatusCode.Unauthorized, bearer: token);
    await Send(HttpMethod.Post, $"/api/v1/publications/{privatePublication}/review", HttpStatusCode.Unauthorized,
        new PublicationReviewRequest(owner, true), bearer: token);
}
await Send(HttpMethod.Get, "/api/v1/publication-drafts", HttpStatusCode.OK, control: true);
await Send(HttpMethod.Get, "/api/v1/registry/projections/pipelines", HttpStatusCode.OK, control: true);
await Send(HttpMethod.Delete, $"/api/v1/registry/artifacts/{otherId}", HttpStatusCode.OK, control: true);
Check(app.Identity.Introspections > 0, "Normal HubIdentityClient used upstream introspection");
Console.WriteLine("PASS: real packaged Hub entry point; Registry reads, owner mapping, revocation and control boundaries.");

async Task<string> CreateArtifact(string name, string ownerId, string visibility)
{
    using var body = await Send(HttpMethod.Post, "/api/v1/registry/artifacts", HttpStatusCode.Created,
        new HubArtifactCreateRequest(name, HubArtifactKind.BuildKit, "1", Visibility: visibility, OwnerId: ownerId), control: true);
    return body.RootElement.GetProperty("id").GetString()!;
}

async Task<string> Submit(string artifactId, string submittedBy)
{
    using var body = await Send(HttpMethod.Post, "/api/v1/publications", HttpStatusCode.Created,
        new PublicationSubmissionRequest(artifactId, "BuildKit", "Synthetic publication", submittedBy), control: true);
    return body.RootElement.GetProperty("publicationId").GetString()!;
}

async Task CheckList(string path, string? bearer, string[] expected, int total)
{
    using var body = await Send(HttpMethod.Get, path, HttpStatusCode.OK, bearer: bearer);
    Check(body.RootElement.GetProperty("totalCount").GetInt32() == total, $"Filtered count: {path}");
    string[] actual = body.RootElement.GetProperty("items").EnumerateArray()
        .Select(item => item.GetProperty("id").GetString()!).Order().ToArray();
    Check(actual.SequenceEqual(expected.Order()), $"Filtered items: {path}");
}

async Task<JsonDocument> Send(HttpMethod method, string path, HttpStatusCode expected,
    object? payload = null, string? bearer = null, string? cookie = null, bool control = false, string? forgedOwner = null,
    string? ifMatch = null)
{
    using var request = new HttpRequestMessage(method, path);
    if (payload is not null) request.Content = JsonContent.Create(payload, payload.GetType());
    if (bearer is not null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
    if (cookie is not null) request.Headers.Add("Cookie", $"{HubBrowserAuthConstants.AccessTokenCookieName}={cookie}");
    if (control) request.Headers.Add(RegistryAuthorization.HeaderName, HubFactory.ControlKey);
    if (ifMatch is not null) request.Headers.TryAddWithoutValidation("If-Match", ifMatch);
    if (forgedOwner is not null)
    {
        request.Headers.Add("X-Owner-Id", forgedOwner);
        request.Headers.Add("X-User-Id", forgedOwner);
    }
    using var response = await client.SendAsync(request);
    Check(response.StatusCode == expected, $"{method} {path}: expected {(int)expected}, got {(int)response.StatusCode}");
    if (method == HttpMethod.Get && (path.Contains("/artifacts") || path.Contains("/publications") || path.Contains("/search")))
        Check(response.Headers.CacheControl?.NoStore == true, "Owner-dependent reads are no-store");
    string content = await response.Content.ReadAsStringAsync();
    return JsonDocument.Parse(string.IsNullOrWhiteSpace(content) ? "null" : content);
}

static void Check(bool passed, string message)
{
    if (!passed) throw new InvalidOperationException(message);
}

sealed class HubFactory(string root, Dictionary<string, string?> configuration) : WebApplicationFactory<HubIdentityClient>
{
    public const string ControlKey = "synthetic-registry-control-credential-for-local-test-only";
    public IdentityHandler Identity { get; } = new();

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("RegistryHostTest").UseContentRoot(root);
        builder.ConfigureAppConfiguration((_, config) =>
        {
            config.Sources.Clear();
            config.AddInMemoryCollection(configuration);
        });
        builder.ConfigureLogging(logging => logging.ClearProviders());
        // Keep all real services/hosted services. Only identity HTTP returns fake
        // data; every other factory HTTP transport throws rather than contacting
        // a provider. No successful replacement responses for other services.
        builder.ConfigureServices(services => services.AddSingleton<IHttpMessageHandlerBuilderFilter>(
            new IsolatedTransportFilter(Identity)));
    }
}

sealed class IsolatedTransportFilter(IdentityHandler identity) : IHttpMessageHandlerBuilderFilter
{
    public Action<HttpMessageHandlerBuilder> Configure(Action<HttpMessageHandlerBuilder> next) => builder =>
    {
        next(builder);
        builder.PrimaryHandler = builder.Name == nameof(HubIdentityClient) ? identity : new DenyNetworkHandler();
    };
}

sealed class DenyNetworkHandler : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        => throw new InvalidOperationException("External HTTP is disabled in Registry host integration.");
}

sealed class IdentityHandler : HttpMessageHandler
{
    public bool OwnerRevoked { get; set; }
    public string AccountId { get; set; } = "";
    public int Introspections { get; private set; }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        if (request.RequestUri?.Host != "identity.test") throw new InvalidOperationException("Unexpected identity target.");
        if (request.Method == HttpMethod.Get && request.RequestUri.AbsolutePath.StartsWith("/api/v1/identity/subjects/"))
            return new HttpResponseMessage(HttpStatusCode.NotFound); // Profile is not read authority.
        if (request.Method != HttpMethod.Post || request.RequestUri.AbsolutePath != "/api/v1/identity/introspect")
            throw new InvalidOperationException("Unexpected identity operation.");
        Introspections++;
        using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
        string? token = body.RootElement.GetProperty("accessToken").GetString();
        if (token == HubFactory.ControlKey)
            throw new InvalidOperationException("Registry service credential reached account introspection.");
        if (token == "identity-unavailable") return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable);
        string? subject = token switch
        {
            "owner-session" when !OwnerRevoked => "subject.owner",
            "other-session" => "subject.other",
            "unlinked-session" => "subject.unlinked",
            "account-as-subject" => AccountId,
            _ => null
        };
        return new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = JsonContent.Create(new { active = subject is not null, subjectId = subject,
                sessionId = "synthetic-session", expiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(10), roles = new[] { "player" } })
        };
    }
}
