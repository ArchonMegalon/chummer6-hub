using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

public sealed record PublicDownloadsReadinessResponse(
    string ContractName,
    string Service,
    bool Ready,
    string Status,
    bool ServingReady,
    bool OverallReady,
    string OverallStatus,
    bool PublicationReady,
    bool PublicationChecksConfigured,
    DateTimeOffset GeneratedAt,
    IReadOnlyList<HubDeepReadinessCheck> Checks,
    ReleaseShelfReadinessState ReleaseShelf)
{
    public const string CurrentContractName =
        "chummer.run.api.public_downloads_readiness.v1";

    public static PublicDownloadsReadinessResponse Create(
        HubDeepReadinessReport report)
    {
        ArgumentNullException.ThrowIfNull(report);
        return new PublicDownloadsReadinessResponse(
            ContractName: CurrentContractName,
            Service: report.Service,
            Ready: report.ServingReady,
            Status: report.ServingReady ? "pass" : "fail",
            ServingReady: report.ServingReady,
            OverallReady: report.Ready,
            OverallStatus: report.Status,
            PublicationReady: report.PublicationReady,
            PublicationChecksConfigured: report.PublicationChecksConfigured,
            GeneratedAt: report.GeneratedAt,
            Checks: report.Checks,
            ReleaseShelf: report.ReleaseShelf);
    }
}

public static class PublicDownloadsReadinessEndpoint
{
    public static int ResolveGlobalStatusCode(
        bool ready,
        bool publicDownloadOnlyRuntime)
    {
        return ready && !publicDownloadOnlyRuntime
            ? StatusCodes.Status200OK
            : StatusCodes.Status503ServiceUnavailable;
    }

    public static IResult CreateResult(HubDeepReadinessReport report)
    {
        PublicDownloadsReadinessResponse response =
            PublicDownloadsReadinessResponse.Create(report);
        return Results.Json(
            response,
            statusCode: response.Ready
                ? StatusCodes.Status200OK
                : StatusCodes.Status503ServiceUnavailable);
    }
}
