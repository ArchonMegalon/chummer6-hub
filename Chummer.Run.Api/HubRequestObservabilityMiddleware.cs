using System.Diagnostics;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;

namespace Chummer.Run.Api;

public sealed class HubRequestObservabilityMiddleware
{
    private const int W3CTraceIdLength = 32;
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
        string method = ResolveMetricMethod(context.Request.Method);
        string route = ResolveMetricRoute(context);
        context.Items[HubRequestObservability.CorrelationItemKey] = correlationId;

        KeyValuePair<string, object?>[] tags =
        [
            new("http.method", method),
            new("http.route", route)
        ];

        using Activity? activity = HubRequestObservability.ActivitySource.StartActivity("hub.request", ActivityKind.Server);
        activity?.SetTag("http.request.method", method);
        activity?.SetTag("http.route", route);
        context.Response.Headers[_options.CorrelationHeaderName] = correlationId;
        if (activity?.Id is { Length: > 0 } traceParent && !context.Response.Headers.ContainsKey("traceparent"))
        {
            context.Response.Headers["traceparent"] = traceParent;
        }

        context.Response.OnStarting(static state =>
        {
            ResponseHeaderRegistration registration = (ResponseHeaderRegistration)state;
            registration.Context.Response.Headers[registration.HeaderName] = registration.CorrelationId;
            if (registration.TraceParent is { Length: > 0 } traceParent && !registration.Context.Response.Headers.ContainsKey("traceparent"))
            {
                registration.Context.Response.Headers["traceparent"] = traceParent;
            }

            return Task.CompletedTask;
        }, new ResponseHeaderRegistration(context, _options.CorrelationHeaderName, correlationId, activity?.Id));

        using IDisposable? scope = _logger.BeginScope(new Dictionary<string, object?>
        {
            ["CorrelationId"] = correlationId,
            ["RequestMethod"] = method,
            ["RequestRoute"] = route
        });

        HubRequestObservability.RequestsStarted.Add(1, tags);
        long startedTimestamp = Stopwatch.GetTimestamp();
        _logger.LogInformation(
            "Hub request started: {Method} {Route} ({CorrelationId}).",
            method,
            route,
            correlationId);

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

            _logger.LogInformation(
                "Hub request completed: {Method} {Route} -> {StatusCode} in {ElapsedMs} ms ({CorrelationId}).",
                method,
                route,
                context.Response.StatusCode,
                elapsedMs,
                correlationId);
        }
    }

    private static string ResolveMetricRoute(HttpContext context)
    {
        string? routeTemplate = (context.GetEndpoint() as RouteEndpoint)?.RoutePattern.RawText;
        return string.IsNullOrWhiteSpace(routeTemplate)
            ? HubRequestObservability.MetricRouteFallback
            : routeTemplate;
    }

    private static string ResolveMetricMethod(string? method)
        => method?.ToUpperInvariant() switch
        {
            "CONNECT" => "CONNECT",
            "DELETE" => "DELETE",
            "GET" => "GET",
            "HEAD" => "HEAD",
            "OPTIONS" => "OPTIONS",
            "PATCH" => "PATCH",
            "POST" => "POST",
            "PUT" => "PUT",
            "TRACE" => "TRACE",
            _ => HubRequestObservability.MetricMethodFallback
        };

    private string ResolveCorrelationId(HttpContext context)
    {
        string headerName = _options.CorrelationHeaderName;
        string? forwarded = context.Request.Headers[headerName].FirstOrDefault();
        string? candidate = forwarded?.Trim();
        if (IsSafeForwardedCorrelationId(candidate))
        {
            return candidate!;
        }

        return Activity.Current?.TraceId.ToString() ?? Guid.NewGuid().ToString("N");
    }

    private static bool IsSafeForwardedCorrelationId(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        if (Guid.TryParseExact(value, "D", out Guid guid))
        {
            return guid != Guid.Empty;
        }

        return value.Length == W3CTraceIdLength
            && value.Any(static character => character != '0')
            && value.All(static character =>
                (character >= 'a' && character <= 'f')
                || (character >= 'A' && character <= 'F')
                || (character >= '0' && character <= '9'));
    }

    private sealed record ResponseHeaderRegistration(
        HttpContext Context,
        string HeaderName,
        string CorrelationId,
        string? TraceParent);
}
