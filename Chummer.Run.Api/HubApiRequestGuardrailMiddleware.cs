using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api;

public sealed class HubApiRequestGuardrailMiddleware
{
    private static readonly JsonSerializerOptions ProblemJsonOptions = new(JsonSerializerDefaults.Web);
    private readonly RequestDelegate _next;
    private readonly HubApiGuardrailOptions _options;

    public HubApiRequestGuardrailMiddleware(RequestDelegate next, HubApiGuardrailOptions options)
    {
        _next = next;
        _options = options;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        long? requestBodyLimit = HubApiGuardrailPolicy.ResolveRequestBodyLimit(context.Request, _options);
        if (requestBodyLimit.HasValue)
        {
            if (TrySetPerRequestBodyLimit(context, requestBodyLimit.Value) && context.Request.ContentLength is long contentLength && contentLength > requestBodyLimit.Value)
            {
                await WriteProblemAsync(
                    context,
                    StatusCodes.Status413PayloadTooLarge,
                    "Request payload exceeds the configured hub limit.",
                    "https://chummer.run/problems/request-too-large",
                    $"This route accepts at most {requestBodyLimit.Value} bytes.");
                return;
            }

            if (context.Request.ContentLength is long knownLength && knownLength > requestBodyLimit.Value)
            {
                await WriteProblemAsync(
                    context,
                    StatusCodes.Status413PayloadTooLarge,
                    "Request payload exceeds the configured hub limit.",
                    "https://chummer.run/problems/request-too-large",
                    $"This route accepts at most {requestBodyLimit.Value} bytes.");
                return;
            }
        }

        CancellationToken originalRequestAborted = context.RequestAborted;
        TimeSpan timeout = HubApiGuardrailPolicy.ResolveTimeout(context.Request, _options);
        using CancellationTokenSource timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(originalRequestAborted);
        timeoutCts.CancelAfter(timeout);
        context.RequestAborted = timeoutCts.Token;

        try
        {
            await _next(context);
        }
        catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !originalRequestAborted.IsCancellationRequested)
        {
            if (context.Response.HasStarted)
            {
                context.Abort();
                return;
            }

            context.Response.Clear();
            await WriteProblemAsync(
                context,
                StatusCodes.Status503ServiceUnavailable,
                "Hub request exceeded the operation budget.",
                "https://chummer.run/problems/request-timeout",
                $"This route must complete within {timeout.TotalSeconds:0} seconds.");
        }
        finally
        {
            context.RequestAborted = originalRequestAborted;
        }
    }

    private static bool TrySetPerRequestBodyLimit(HttpContext context, long limit)
    {
        IHttpMaxRequestBodySizeFeature? feature = context.Features.Get<IHttpMaxRequestBodySizeFeature>();
        if (feature is null || feature.IsReadOnly)
        {
            return false;
        }

        feature.MaxRequestBodySize = limit;
        return true;
    }

    private static async Task WriteProblemAsync(HttpContext context, int statusCode, string title, string type, string detail)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/problem+json";

        ProblemDetails problem = new()
        {
            Status = statusCode,
            Title = title,
            Type = type,
            Detail = detail
        };

        await JsonSerializer.SerializeAsync(context.Response.Body, problem, ProblemJsonOptions, CancellationToken.None);
    }
}
