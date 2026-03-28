using System.Diagnostics;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api;

public sealed class HubRequestObservabilityMiddleware
{
    private readonly RequestDelegate _next;
    private readonly HubRequestObservabilityOptions _options;
    private readonly ILogger<HubRequestObservabilityMiddleware> _logger;

    public HubRequestObservabilityMiddleware(
        RequestDelegate next,
        HubRequestObservabilityOptions options,
        ILogger<HubRequestObservabilityMiddleware> logger)
    {
        _next = next;
        _options = options;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        string correlationId = ResolveCorrelationId(context);
        context.Items[HubRequestObservability.CorrelationItemKey] = correlationId;
        context.Response.Headers[_options.CorrelationHeaderName] = correlationId;

        KeyValuePair<string, object?>[] tags =
        [
            new("http.method", context.Request.Method),
            new("http.route", context.Request.Path.Value ?? "/"),
            new("chummer.correlation_id", correlationId)
        ];

        using Activity? activity = HubRequestObservability.ActivitySource.StartActivity("hub.request", ActivityKind.Server);
        activity?.SetTag("http.method", context.Request.Method);
        activity?.SetTag("url.path", context.Request.Path.Value);
        activity?.SetTag("chummer.correlation_id", correlationId);

        using IDisposable? scope = _logger.BeginScope(new Dictionary<string, object?>
        {
            ["CorrelationId"] = correlationId,
            ["RequestMethod"] = context.Request.Method,
            ["RequestPath"] = context.Request.Path.Value ?? "/"
        });

        HubRequestObservability.RequestsStarted.Add(1, tags);
        long startedTimestamp = Stopwatch.GetTimestamp();
        _logger.LogInformation("Hub request started.");

        try
        {
            await _next(context);
        }
        finally
        {
            double elapsedMs = Stopwatch.GetElapsedTime(startedTimestamp).TotalMilliseconds;
            string statusCode = context.Response.StatusCode.ToString(System.Globalization.CultureInfo.InvariantCulture);
            HubRequestObservability.RequestsCompleted.Add(
                1,
                [.. tags, new KeyValuePair<string, object?>("http.status_code", statusCode)]);
            HubRequestObservability.RequestDurationMs.Record(
                elapsedMs,
                [.. tags, new KeyValuePair<string, object?>("http.status_code", statusCode)]);

            context.Response.Headers[_options.CorrelationHeaderName] = correlationId;
            if (activity?.Id is { Length: > 0 } traceParent && !context.Response.Headers.ContainsKey("traceparent"))
            {
                context.Response.Headers["traceparent"] = traceParent;
            }

            _logger.LogInformation("Hub request completed in {ElapsedMs} ms with status {StatusCode}.", elapsedMs, context.Response.StatusCode);
        }
    }

    private string ResolveCorrelationId(HttpContext context)
    {
        string headerName = _options.CorrelationHeaderName;
        string? forwarded = context.Request.Headers[headerName].FirstOrDefault();
        if (!string.IsNullOrWhiteSpace(forwarded))
        {
            return forwarded.Trim();
        }

        return Activity.Current?.TraceId.ToString() ?? Guid.NewGuid().ToString("N");
    }
}
