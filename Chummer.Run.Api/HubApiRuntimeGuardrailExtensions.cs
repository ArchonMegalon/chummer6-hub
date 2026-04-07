using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http.Features;

namespace Chummer.Run.Api;

internal static class HubApiRuntimeGuardrailExtensions
{
    public static WebApplicationBuilder AddHubApiRuntimeGuardrails(this WebApplicationBuilder builder)
    {
        HubApiGuardrailOptions options = HubApiGuardrailOptions.FromConfiguration(builder.Configuration);

        builder.Services.AddSingleton(options);
        builder.Services.Configure<FormOptions>(formOptions =>
        {
            formOptions.MultipartBodyLengthLimit = Math.Max(options.MaxMultipartBodyBytes, options.MaxReleaseBundleBodyBytes);
            formOptions.ValueLengthLimit = (int)Math.Min(options.MaxJsonBodyBytes, int.MaxValue);
        });
        builder.WebHost.ConfigureKestrel(kestrel =>
        {
            kestrel.Limits.MaxRequestBodySize = Math.Max(options.MaxRequestBodyBytes, options.MaxReleaseBundleBodyBytes);
        });
        builder.Services.AddRateLimiter(rateLimiter =>
        {
            rateLimiter.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            rateLimiter.GlobalLimiter = HubApiRateLimiterFactory.Create(options);
            rateLimiter.OnRejected = static async (context, cancellationToken) =>
            {
                context.HttpContext.Response.ContentType = "application/problem+json";
                if (context.Lease.TryGetMetadata(MetadataName.RetryAfter, out TimeSpan retryAfter))
                {
                    context.HttpContext.Response.Headers.RetryAfter = Math.Ceiling(retryAfter.TotalSeconds).ToString(System.Globalization.CultureInfo.InvariantCulture);
                }

                await context.HttpContext.Response.WriteAsJsonAsync(
                    new
                    {
                        type = "https://chummer.run/problems/rate-limit",
                        title = "Hub request rate limit exceeded.",
                        status = StatusCodes.Status429TooManyRequests,
                        detail = "Slow the caller down before retrying this route."
                    },
                    cancellationToken);
            };
        });

        return builder;
    }

    public static WebApplication UseHubApiRuntimeGuardrails(this WebApplication app)
    {
        app.UseRateLimiter();
        app.UseMiddleware<HubApiRequestGuardrailMiddleware>();
        return app;
    }
}
