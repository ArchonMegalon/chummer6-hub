using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class RunsiteOrientationRequestComposerServiceTests
{
    [Fact]
    public void ComposeRejectsRunsitePacksThatTryToOwnRoutePreviewArtifacts()
    {
        RunsiteOrientationRequestComposerService service = new();

        InvalidDataException error = Assert.Throws<InvalidDataException>(() => service.Compose(BuildRequest(
            artifactTemplates:
            [
                new RunsiteOrientationArtifactTemplate(
                    TemplateId: "route-preview-pack",
                    Role: RunsiteOrientationArtifactRole.RoutePreview,
                    Category: "runsite/orientation/route-preview",
                    Payload: "{\"frame\":\"pack-owned\"}",
                    OutputFormat: "png",
                    RouteSegmentId: "segment-a",
                    DeduplicationKey: "route-preview-pack"),
                new RunsiteOrientationArtifactTemplate(
                    TemplateId: "host-intro",
                    Role: RunsiteOrientationArtifactRole.HostClip,
                    Category: "runsite/orientation/host-clip",
                    Payload: "{\"script\":\"Stay on the marked lane.\"}",
                    OutputFormat: "mp4",
                    RouteSegmentId: "segment-a",
                    DeduplicationKey: "host-intro")
            ])));

        Assert.Contains("route_summary:artifact_launch stays governed by the route summary", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ComposeRejectsRunsitePacksWithoutHostClips()
    {
        RunsiteOrientationRequestComposerService service = new();

        InvalidDataException error = Assert.Throws<InvalidDataException>(() => service.Compose(BuildRequest(
            artifactTemplates:
            [
                new RunsiteOrientationArtifactTemplate(
                    TemplateId: "tour-sibling",
                    Role: RunsiteOrientationArtifactRole.TourSibling,
                    Category: "runsite/orientation/tour",
                    Payload: "{\"tour\":\"catwalk\"}",
                    OutputFormat: "json",
                    RouteSegmentId: "segment-a",
                    DeduplicationKey: "tour-sibling")
            ])));

        Assert.Contains("must contribute at least one host clip template", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ComposeBuildsRouteSummaryArtifactLaunchesFromRouteSegments()
    {
        RunsiteOrientationRequestComposerService service = new();

        RunsiteOrientationRequestCompositionResult result = service.Compose(BuildRequest());

        Assert.Equal(RunsiteOrientationRequestComposerService.ContractName, result.ContractName);
        Assert.Equal("players", result.Audience);
        Assert.Equal("de-AT", result.Locale);
        Assert.Equal(["segment-a", "segment-b"], result.RouteSummaryArtifactLaunches.Select(static launch => launch.RouteSegmentId).ToArray());
        Assert.All(
            result.RouteSummaryArtifactLaunches,
            launch =>
            {
                Assert.Equal("runsite-pack-redmond", launch.ApprovedRunsitePackId);
                Assert.Equal("redmond-docks-route", launch.RouteSummaryId);
                Assert.Equal(
                    RunsiteOrientationRequestComposerService.PreviewTruthPosture,
                    launch.PreviewTruthPosture);
                Assert.Equal("Inspectable route previews stay inspectable before session start.", launch.PreviewSafeTruthSummary);
                Assert.Equal(
                    [
                        "/artifacts/routes/redmond-docks-route/segment-a",
                        "/artifacts/routes/redmond-docks-route/segment-b"
                    ],
                    launch.PreviewSafeInspectableTruthRefs);
                Assert.Equal(
                    [
                        "pre-session:approved",
                        "preview-safe:pre-session",
                        "route-summary:redmond-docks-route",
                        "runsite:redmond-docks"
                    ],
                    launch.EvidenceRefs);
                Assert.Equal("players", launch.Audience);
                Assert.Equal("de-AT", launch.Locale);
            });

        RunsiteOrientationArtifactRenderRequest[] routePreviewArtifacts = result.BundleRequest.Artifacts
            .Where(static artifact => artifact.Role == RunsiteOrientationArtifactRole.RoutePreview)
            .ToArray();
        Assert.Equal(2, routePreviewArtifacts.Length);
        Assert.All(
            routePreviewArtifacts,
            artifact =>
            {
                Assert.StartsWith("runsite-orientation.", artifact.DeduplicationKey, StringComparison.Ordinal);
                Assert.False(artifact.AllowPersistentPinning);
            });
    }

    [Fact]
    public void ComposeRejectsDuplicateArtifactDeduplicationKeys()
    {
        RunsiteOrientationRequestComposerService service = new();

        InvalidDataException error = Assert.Throws<InvalidDataException>(() => service.Compose(BuildRequest(
            artifactTemplates:
            [
                new RunsiteOrientationArtifactTemplate(
                    TemplateId: "host-intro-a",
                    Role: RunsiteOrientationArtifactRole.HostClip,
                    Category: "runsite/orientation/host-clip",
                    Payload: "{\"script\":\"Stay on the marked lane.\"}",
                    OutputFormat: "mp4",
                    RouteSegmentId: "segment-a",
                    DeduplicationKey: "host-intro"),
                new RunsiteOrientationArtifactTemplate(
                    TemplateId: "host-intro-b",
                    Role: RunsiteOrientationArtifactRole.HostClip,
                    Category: "runsite/orientation/host-clip",
                    Payload: "{\"script\":\"Do not split the party.\"}",
                    OutputFormat: "mp4",
                    RouteSegmentId: "segment-a",
                    DeduplicationKey: "host-intro")
            ])));

        Assert.Contains("must not emit duplicate deduplication key", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ComposeRejectsRouteSummarySegmentsOutsideRoutePreviewCategory()
    {
        RunsiteOrientationRequestComposerService service = new();

        InvalidDataException error = Assert.Throws<InvalidDataException>(() => service.Compose(BuildRequest(
            routeSummary: new RunsiteRouteSummary(
                RouteSummaryId: "redmond-docks-route",
                Segments:
                [
                    new RunsiteRouteSummarySegment(
                        RouteSegmentId: "segment-a",
                        InspectableTruthRef: "/artifacts/routes/redmond-docks-route/segment-a",
                        PreviewPayload: "{\"frame\":\"alpha\"}",
                        Category: "runsite/orientation/host-clip"),
                    new RunsiteRouteSummarySegment(
                        RouteSegmentId: "segment-b",
                        InspectableTruthRef: "/artifacts/routes/redmond-docks-route/segment-b",
                        PreviewPayload: "{\"frame\":\"beta\"}")
                ]))));

        Assert.Contains("route_summary:artifact_launch remains route-summary governed", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void InternalControllerRequiresBearerAuthorization()
    {
        InternalRunsiteOrientationController controller = BuildController(expectedToken: "approved-token");
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        ActionResult<RunsiteOrientationRequestCompositionResult> response = controller.Compose(BuildRequest());

        ObjectResult denied = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails details = Assert.IsType<ProblemDetails>(denied.Value);
        Assert.Equal(StatusCodes.Status401Unauthorized, denied.StatusCode);
        Assert.Equal("Runsite orientation authorization required", details.Title);
        Assert.Contains("authorization is required", details.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InternalControllerRejectsMissingRequestEvenWhenAuthorized()
    {
        InternalRunsiteOrientationController controller = BuildController(expectedToken: "approved-token");
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer approved-token";

        ActionResult<RunsiteOrientationRequestCompositionResult> response = controller.Compose(request: null);

        ObjectResult rejected = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails details = Assert.IsType<ProblemDetails>(rejected.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, rejected.StatusCode);
        Assert.Equal("Runsite orientation request rejected", details.Title);
        Assert.Contains("request is required", details.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InternalControllerReturnsComposedOrientationRequestWhenAuthorized()
    {
        InternalRunsiteOrientationController controller = BuildController(expectedToken: "approved-token");
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer approved-token";

        ActionResult<RunsiteOrientationRequestCompositionResult> response = controller.Compose(BuildRequest());

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        RunsiteOrientationRequestCompositionResult payload = Assert.IsType<RunsiteOrientationRequestCompositionResult>(ok.Value);
        Assert.Equal(StatusCodes.Status200OK, ok.StatusCode);
        Assert.Equal("runsite-redmond-bundle", payload.BundleRequest.BundleId);
        Assert.Equal("redmond-docks-route", payload.BundleRequest.RouteSummaryId);
        Assert.Equal(
            RunsiteOrientationRequestComposerService.PreviewTruthPosture,
            payload.PreviewSafeTruth.PreviewTruthPosture);
    }

    private static InternalRunsiteOrientationController BuildController(string expectedToken)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["FLEET_INTERNAL_API_TOKEN"] = expectedToken
            })
            .Build();
        return new InternalRunsiteOrientationController(
            new RunsiteOrientationRequestComposerService(),
            configuration);
    }

    private static RunsiteOrientationRequestComposeRequest BuildRequest(
        IReadOnlyList<RunsiteOrientationArtifactTemplate>? artifactTemplates = null,
        RunsiteRouteSummary? routeSummary = null)
    {
        return new RunsiteOrientationRequestComposeRequest(
            RequestedBy: "campaign.ops",
            BundleId: "runsite-redmond-bundle",
            RunsitePack: new ApprovedRunsiteOrientationPack(
                SourcePackId: "runsite-pack-redmond",
                ApprovalState: "approved",
                ProvenanceRef: "runsite:redmond-docks:orientation:v1",
                EvidenceRefs:
                [
                    "runsite:redmond-docks",
                    "route-summary:redmond-docks-route",
                    "preview-safe:pre-session",
                    "pre-session:approved"
                ],
                RouteSummaryId: "redmond-docks-route",
                ArtifactTemplates: artifactTemplates ??
                [
                    new RunsiteOrientationArtifactTemplate(
                        TemplateId: "host-intro",
                        Role: RunsiteOrientationArtifactRole.HostClip,
                        Category: "runsite/orientation/host-clip",
                        Payload: "{\"script\":\"Stay on the marked lane.\"}",
                        OutputFormat: "mp4",
                        RouteSegmentId: "segment-a",
                        DeduplicationKey: "host-intro"),
                    new RunsiteOrientationArtifactTemplate(
                        TemplateId: "tour-sibling",
                        Role: RunsiteOrientationArtifactRole.TourSibling,
                        Category: "runsite/orientation/tour",
                        Payload: "{\"tour\":\"catwalk\"}",
                        OutputFormat: "json",
                        RouteSegmentId: "segment-b",
                        DeduplicationKey: "tour-sibling")
                ],
                Audience: "players,gm",
                Locale: "de-AT"),
            RouteSummary: routeSummary ?? new RunsiteRouteSummary(
                RouteSummaryId: "redmond-docks-route",
                Segments:
                [
                    new RunsiteRouteSummarySegment(
                        RouteSegmentId: "segment-a",
                        InspectableTruthRef: "/artifacts/routes/redmond-docks-route/segment-a",
                        PreviewPayload: "{\"frame\":\"alpha\"}"),
                    new RunsiteRouteSummarySegment(
                        RouteSegmentId: "segment-b",
                        InspectableTruthRef: "/artifacts/routes/redmond-docks-route/segment-b",
                        PreviewPayload: "{\"frame\":\"beta\"}")
                ]),
            PreviewSafeTruth: new RunsitePreviewSafePreSessionTruth(
                PreviewTruthPosture: RunsiteOrientationRequestComposerService.PreviewTruthPosture,
                Summary: "Inspectable route previews stay inspectable before session start.",
                InspectableTruthRefs:
                [
                    "/artifacts/routes/redmond-docks-route/segment-a",
                    "/artifacts/routes/redmond-docks-route/segment-b"
                ]),
            Audience: "players",
            Locale: "de-AT",
            RequestedAtUtc: DateTimeOffset.Parse("2026-04-23T21:31:27Z"));
    }
}
