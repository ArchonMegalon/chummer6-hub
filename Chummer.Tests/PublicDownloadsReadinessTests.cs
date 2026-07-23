using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicDownloadsReadinessTests
{
    [Fact]
    public void Serving_ready_returns_200_without_claiming_overall_or_publication_readiness()
    {
        HubDeepReadinessReport report = Report(
            servingReady: true,
            overallReady: false,
            publicationReady: false);

        IResult result = PublicDownloadsReadinessEndpoint.CreateResult(report);

        Assert.Equal(
            StatusCodes.Status200OK,
            Assert.IsAssignableFrom<IStatusCodeHttpResult>(result).StatusCode);
        PublicDownloadsReadinessResponse response = Assert.IsType<PublicDownloadsReadinessResponse>(
            Assert.IsAssignableFrom<IValueHttpResult>(result).Value);
        Assert.Equal(PublicDownloadsReadinessResponse.CurrentContractName, response.ContractName);
        Assert.True(response.Ready);
        Assert.True(response.ServingReady);
        Assert.Equal("pass", response.Status);
        Assert.False(response.OverallReady);
        Assert.Equal("fail", response.OverallStatus);
        Assert.False(response.PublicationReady);
        Assert.False(response.PublicationChecksConfigured);
        Assert.Same(report.Checks, response.Checks);
        Assert.Same(report.ReleaseShelf, response.ReleaseShelf);

        using JsonDocument document = JsonDocument.Parse(JsonSerializer.Serialize(
            response,
            new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        JsonElement root = document.RootElement;
        Assert.True(root.GetProperty("ready").GetBoolean());
        Assert.True(root.GetProperty("servingReady").GetBoolean());
        Assert.False(root.GetProperty("overallReady").GetBoolean());
        Assert.False(root.GetProperty("publicationReady").GetBoolean());
    }

    [Fact]
    public void Serving_not_ready_returns_503_even_when_other_report_fields_are_true()
    {
        HubDeepReadinessReport report = Report(
            servingReady: false,
            overallReady: true,
            publicationReady: true);

        IResult result = PublicDownloadsReadinessEndpoint.CreateResult(report);

        Assert.Equal(
            StatusCodes.Status503ServiceUnavailable,
            Assert.IsAssignableFrom<IStatusCodeHttpResult>(result).StatusCode);
        PublicDownloadsReadinessResponse response = Assert.IsType<PublicDownloadsReadinessResponse>(
            Assert.IsAssignableFrom<IValueHttpResult>(result).Value);
        Assert.False(response.Ready);
        Assert.False(response.ServingReady);
        Assert.Equal("fail", response.Status);
        Assert.True(response.OverallReady);
        Assert.Equal("pass", response.OverallStatus);
        Assert.True(response.PublicationReady);
    }

    private static HubDeepReadinessReport Report(
        bool servingReady,
        bool overallReady,
        bool publicationReady)
    {
        HubDeepReadinessCheck[] checks =
        [
            new(
                Name: "release_shelf",
                Passed: servingReady,
                Status: servingReady ? "pass" : "fail",
                Code: servingReady ? "generation_shelf_verified" : "release_shelf_invalid")
        ];
        ReleaseShelfReadinessState shelf = new(
            Mode: servingReady ? "generation" : "unavailable",
            ServingReady: servingReady,
            PublicationReady: publicationReady,
            PublicationChecksConfigured: false,
            Status: servingReady ? "serving" : "not_serving",
            Code: servingReady ? "generation_shelf_verified" : "release_shelf_invalid",
            GenerationId: servingReady ? "gen-test" : null,
            ActivationReceiptId: servingReady ? "activation-test" : null,
            InventoryDigest: servingReady ? new string('a', 64) : null,
            ReleaseVersion: servingReady ? "run-test" : null,
            Channel: servingReady ? "preview" : null,
            PublishedAt: servingReady ? DateTimeOffset.Parse("2026-07-23T00:00:00Z") : null,
            PublicationChecks: []);
        return new HubDeepReadinessReport(
            HubDeepReadinessService.ContractName,
            Service: "chummer.run.api",
            Ready: overallReady,
            Status: overallReady ? "pass" : "fail",
            ServingReady: servingReady,
            PublicationReady: publicationReady,
            PublicationChecksConfigured: false,
            GeneratedAt: DateTimeOffset.Parse("2026-07-23T00:00:00Z"),
            Checks: checks,
            ReleaseShelf: shelf);
    }
}
