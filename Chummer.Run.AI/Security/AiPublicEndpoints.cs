namespace Chummer.Run.AI.Security;

public static class AiPublicEndpoints
{
    public const string HealthPath = "/api/health";
    public const string CapabilitiesPath = "/api/v1/ai/capabilities";

    public static IEndpointRouteBuilder MapAiPublicEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapMethods(
            HealthPath,
            new[] { HttpMethods.Get, HttpMethods.Head },
            () => Results.Ok(new
            {
                service = "chummer.run.ai",
                status = "ok"
            }));

        endpoints.MapMethods(
            CapabilitiesPath,
            new[] { HttpMethods.Get, HttpMethods.Head },
            () => Results.Ok(new
            {
                service = "chummer.run.ai",
                apiVersion = "v1",
                status = "available",
                protectedRouteAuthorization = "bearer_required"
            }));

        return endpoints;
    }
}
