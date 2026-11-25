using System.Security.Claims;
using Chummer.Run.Contracts.Publication;
using Chummer.Run.Contracts.Registry;
using Chummer.Run.Registry.Controllers;
using Chummer.Run.Registry.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Chummer.Run.Registry.PackageTests;

// In-process controller/service/persistent-store integration through the same
// PackageReferences as Hub. No sockets, production startup, provider or account data.
// Authentication middleware itself is outside this fixture's scope.
public sealed class RegistryReadIsolationTests : IDisposable
{
    private const string Owner = "synthetic-package-owner";
    private const string Other = "synthetic-package-unrelated";
    private const string Query = "synthetic-package-isolation";
    private readonly string root = Path.Combine(Path.GetTempPath(), "registry-package-" + Guid.NewGuid().ToString("N"));
    private readonly FileBackedHubArtifactStore store;
    private readonly PublicationWorkflowService workflow;
    private readonly IConfiguration configuration;
    private readonly ServiceProvider services;
    private readonly HubArtifactMetadata privateArtifact;
    private readonly HubArtifactMetadata publicArtifact;
    private readonly HubArtifactMetadata otherPrivateArtifact;
    private readonly HubArtifactMetadata pendingPublicArtifact;
    private readonly PublicationRecordResponse privatePublication;
    private readonly PublicationRecordResponse publicPublication;
    private readonly PublicationRecordResponse pendingPublication;

    public RegistryReadIsolationTests()
    {
        // The runner hashes these exact files against the admitted nupkg members
        // before and after the test process. Prove the CLR loaded those copies.
        Assert.Equal(Path.Combine(AppContext.BaseDirectory, "Chummer.Run.Registry.dll"),
            typeof(HubRegistryController).Assembly.Location);
        Assert.Equal(Path.Combine(AppContext.BaseDirectory, "Chummer.Hub.Registry.Contracts.dll"),
            typeof(HubArtifactMetadata).Assembly.Location);
        configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_REGISTRY_ARTIFACT_STORE_PATH"] = Path.Combine(root, "registry.json")
        }).Build();
        store = new FileBackedHubArtifactStore(configuration);
        workflow = new PublicationWorkflowService(store);
        privateArtifact = Artifact("a-private", ArtifactVisibilityModes.Private, Owner);
        publicArtifact = Artifact("b-public", ArtifactVisibilityModes.Public, Owner);
        otherPrivateArtifact = Artifact("c-unrelated-private", ArtifactVisibilityModes.Private, Other);
        pendingPublicArtifact = Artifact("d-pending-public", ArtifactVisibilityModes.Public, Owner);
        privatePublication = Publication(privateArtifact, publish: true);
        publicPublication = Publication(publicArtifact, publish: true);
        pendingPublication = Publication(pendingPublicArtifact, publish: false);
        var registrations = new ServiceCollection();
        registrations.AddLogging();
        registrations.AddControllersWithViews();
        registrations.AddSingleton(configuration);
        registrations.AddSingleton<IHubArtifactStore>(store);
        registrations.AddSingleton<IPublicationWorkflowService>(workflow);
        registrations.AddSingleton<IReleaseChannelManifestStore, FileReleaseChannelManifestStore>();
        services = registrations.BuildServiceProvider();
    }

    [Theory]
    [InlineData("owner", true)]
    [InlineData("unrelated", false)]
    [InlineData("anonymous", false)]
    [InlineData("unauthenticated-owner-claim", false)]
    public void Details_preview_projection_install_and_reviews_enforce_stored_ownership(string audience, bool owns)
    {
        var controller = Registry(audience);
        var hidden = new ActionResult[]
        {
            controller.GetArtifact(privateArtifact.Id).Result!,
            controller.GetPreview(privateArtifact.Id).Result!,
            controller.GetProjection(privateArtifact.Id).Result!,
            controller.GetInstallProjection(privateArtifact.Id).Result!,
            controller.GetReviews(privateArtifact.Id).Result!
        };
        foreach (var result in hidden)
        {
            if (owns) Assert.IsType<OkObjectResult>(result);
            else Assert.IsType<NotFoundResult>(result);
        }
        Assert.Equal(publicArtifact.Id, Ok(controller.GetArtifact(publicArtifact.Id)).Id);
        Assert.Equal(publicArtifact.Id, Ok(controller.GetPreview(publicArtifact.Id)).Id);
        Assert.Equal(publicArtifact.Id, Ok(controller.GetProjection(publicArtifact.Id)).Id);
        Assert.IsType<OkObjectResult>(controller.GetInstallProjection(publicArtifact.Id).Result);
        Assert.IsType<OkObjectResult>(controller.GetReviews(publicArtifact.Id).Result);
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("unrelated")]
    [InlineData("anonymous")]
    [InlineData("unauthenticated-owner-claim")]
    public void Search_list_and_projections_filter_before_counting_and_paging(string audience)
    {
        var controller = Registry(audience);
        var expected = new HashSet<string> { publicArtifact.Id, pendingPublicArtifact.Id };
        if (audience == "owner") expected.Add(privateArtifact.Id);
        if (audience == "unrelated") expected.Add(otherPrivateArtifact.Id);
        var searchIds = new List<string>();
        var projectionIds = new List<string>();
        for (int page = 1; page <= expected.Count + 1; page++)
        {
            var search = Ok(controller.SearchArtifacts(Query, page: page, pageSize: 1));
            var list = Ok(controller.ListArtifacts(Query, page: page, pageSize: 1));
            var projections = Ok(controller.ListProjections(Query, page: page, pageSize: 1));
            Assert.Equal(expected.Count, search.TotalCount);
            Assert.Equal(expected.Count, list.TotalCount);
            Assert.Equal(expected.Count, projections.TotalCount);
            Assert.Equal(search.Items.Select(x => x.Id), list.Items.Select(x => x.Id));
            Assert.Equal(page <= expected.Count ? 1 : 0, search.Items.Count);
            Assert.Equal(page <= expected.Count ? 1 : 0, projections.Items.Count);
            searchIds.AddRange(search.Items.Select(x => x.Id));
            projectionIds.AddRange(projections.Items.Select(x => x.Id));
        }
        Assert.Equal(expected.Order(), searchIds.Order());
        Assert.Equal(expected.Order(), projectionIds.Order());
        foreach (var shelf in new[] { "creator", "campaign", "owner-only", "personal" })
        {
            var search = Ok(controller.SearchArtifacts(Query, pageSize: 100, shelfAudience: shelf));
            Assert.All(search.Items, item => Assert.Contains(item.Id, expected));
            Assert.Equal(search.Items.Count, search.TotalCount);
            var projections = Ok(controller.ListProjections(Query, pageSize: 100, shelfAudience: shelf));
            Assert.All(projections.Items, item => Assert.Contains(item.Id, expected));
            Assert.Equal(projections.Items.Count, projections.TotalCount);
        }
    }

    [Theory]
    [InlineData("owner", true)]
    [InlineData("unrelated", false)]
    [InlineData("anonymous", false)]
    [InlineData("unauthenticated-owner-claim", false)]
    public void Publication_reads_and_registry_decoration_hide_private_and_pending_rows(string audience, bool owns)
    {
        var publications = Publications(audience);
        var expected = owns
            ? new[] { privatePublication.PublicationId, publicPublication.PublicationId, pendingPublication.PublicationId }
            : new[] { publicPublication.PublicationId };
        Assert.Equal(expected.Order(), Ok(publications.List()).Select(x => x.PublicationId).Order());
        foreach (var publication in new[] { privatePublication, pendingPublication })
        {
            var controller = Publications(audience); // fresh response headers for every request
            var result = controller.Get(publication.PublicationId);
            if (owns) Assert.Equal(publication.PublicationId, Ok(result).PublicationId);
            else
            {
                Assert.Equal(StatusCodes.Status404NotFound, Assert.IsType<ObjectResult>(result.Result).StatusCode);
                Assert.False(controller.Response.Headers.ContainsKey("ETag"));
                Assert.False(controller.Response.Headers.ContainsKey("Last-Modified"));
            }
        }
        Assert.Equal(publicPublication.PublicationId, Ok(publications.Get(publicPublication.PublicationId)).PublicationId);
        var registry = Registry(audience);
        string? expectedPendingId = owns ? pendingPublication.PublicationId : null;
        Assert.Equal(expectedPendingId, Ok(registry.GetPreview(pendingPublicArtifact.Id)).LatestPublicationId);
        Assert.Equal(expectedPendingId, Ok(registry.GetProjection(pendingPublicArtifact.Id)).LatestPublicationId);
        Assert.Equal(expectedPendingId, Ok(registry.SearchArtifacts(Query, pageSize: 100)).Items
            .Single(item => item.Id == pendingPublicArtifact.Id).LatestPublicationId);
        Assert.Equal(publicPublication.PublicationId, Ok(registry.GetPreview(publicArtifact.Id)).LatestPublicationId);
    }

    private HubArtifactMetadata Artifact(string suffix, string visibility, string owner) =>
        store.UpsertArtifact(new HubArtifactCreateRequest($"{Query}-{suffix}", HubArtifactKind.RulePack,
            "1.0.0", Visibility: visibility, OwnerId: owner, Summary: "Synthetic fixture only"));

    private PublicationRecordResponse Publication(HubArtifactMetadata artifact, bool publish)
    {
        var submitted = workflow.Submit(new PublicationSubmissionRequest(artifact.Id, artifact.Kind.ToString(),
            artifact.Name, Owner, "Synthetic nonpublic review notes"));
        if (!publish) return submitted;
        var reviewed = workflow.Review(submitted.PublicationId,
            new PublicationReviewRequest("synthetic-reviewer", true), submitted.ConcurrencyToken);
        Assert.Equal(PublicationMutationStatus.Success, reviewed.Status);
        var published = workflow.Publish(submitted.PublicationId,
            new PublicationPublishRequest("synthetic-publisher"), reviewed.Publication!.ConcurrencyToken);
        Assert.Equal(PublicationMutationStatus.Success, published.Status);
        return published.Publication!;
    }

    private HubRegistryController Registry(string audience)
    {
        var controller = ActivatorUtilities.CreateInstance<HubRegistryController>(services);
        controller.ControllerContext = Context(audience);
        return controller;
    }

    private PublicationsController Publications(string audience)
    {
        var controller = ActivatorUtilities.CreateInstance<PublicationsController>(services);
        controller.ControllerContext = Context(audience);
        return controller;
    }

    private ControllerContext Context(string audience)
    {
        var identity = audience switch
        {
            "owner" => new ClaimsIdentity([new Claim(ClaimTypes.NameIdentifier, Owner)], "synthetic"),
            // Control-plane scope is not ownership of somebody else's private artifact.
            "unrelated" => new ClaimsIdentity([new Claim(ClaimTypes.NameIdentifier, Other),
                new Claim("scope", RegistryAuthorization.ControlPolicy)], "synthetic"),
            "unauthenticated-owner-claim" => new ClaimsIdentity([new Claim(ClaimTypes.NameIdentifier, Owner)]),
            _ => new ClaimsIdentity()
        };
        return new ControllerContext { HttpContext = new DefaultHttpContext
            { User = new ClaimsPrincipal(identity), RequestServices = services } };
    }

    private static T Ok<T>(ActionResult<T> result) => Assert.IsAssignableFrom<T>(Assert.IsType<OkObjectResult>(result.Result).Value);

    public void Dispose()
    {
        store.Dispose();
        services.Dispose();
        if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
    }
}
