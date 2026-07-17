using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.IO;
using Chummer.Run.Api;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Routing.Patterns;
using Microsoft.Extensions.Logging;

namespace RunServicesVerification;

internal static class HubRequestObservabilityVerification
{
    public static async Task RunAsync()
    {
        VerifyObservabilityProgressNote();
        await VerifyMiddlewareEmitsCorrelationTraceAndMetricsAsync();
    }

    private static void VerifyObservabilityProgressNote()
    {
        string backlogPath = Path.Combine(ResolveRepoRoot(), "docs", "MIGRATION_BACKLOG.md");
        string backlog = File.ReadAllText(backlogPath);

        VerificationAssert.True(backlog.Contains("MIG-091", StringComparison.Ordinal), "Migration backlog should keep the observability lane tracked.");
    }

    private static async Task VerifyMiddlewareEmitsCorrelationTraceAndMetricsAsync()
    {
        HubRequestObservabilityOptions options = new();
        List<MetricMeasurement> measurements = [];

        using MeterListener meterListener = new();
        meterListener.InstrumentPublished = (instrument, listener) =>
        {
            if (string.Equals(instrument.Meter.Name, HubRequestObservability.MeterName, StringComparison.Ordinal))
            {
                listener.EnableMeasurementEvents(instrument);
            }
        };
        meterListener.SetMeasurementEventCallback<long>((instrument, measurement, tags, _) =>
        {
            measurements.Add(new MetricMeasurement(instrument.Name, measurement, CopyTags(tags)));
        });
        meterListener.SetMeasurementEventCallback<double>((instrument, measurement, tags, _) =>
        {
            measurements.Add(new MetricMeasurement(instrument.Name, measurement, CopyTags(tags)));
        });
        meterListener.Start();

        List<Activity> observedActivities = [];
        using ActivityListener activityListener = new()
        {
            ShouldListenTo = source => string.Equals(source.Name, HubRequestObservability.ActivitySourceName, StringComparison.Ordinal),
            Sample = static (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activity => observedActivities.Add(activity)
        };
        ActivitySource.AddActivityListener(activityListener);

        RecordingLogger<HubRequestObservabilityMiddleware> logger = new();
        HubRequestObservabilityMiddleware middleware = new(async context =>
        {
            VerificationAssert.NotNull(context.Items[HubRequestObservability.CorrelationItemKey] as string, "Middleware should stamp a correlation id before controller execution.");
            context.Response.StatusCode = StatusCodes.Status202Accepted;
            await context.Response.StartAsync();
            await context.Response.WriteAsync("ok");
        }, options, logger);

        const string routeTemplate = "/downloads/release-evidence/{**path}";
        RouteEndpoint releaseEvidenceEndpoint = new(
            _ => Task.CompletedTask,
            RoutePatternFactory.Parse(routeTemplate),
            order: 0,
            EndpointMetadataCollection.Empty,
            displayName: "release evidence test endpoint");

        DefaultHttpContext firstContext = CreateContext(
            HttpMethods.Get,
            "/downloads/release-evidence/alice/private-token-a.json",
            "?secret=query-a",
            "0123456789abcdef0123456789abcdef",
            options,
            releaseEvidenceEndpoint);
        DefaultHttpContext secondContext = CreateContext(
            HttpMethods.Get,
            "/downloads/release-evidence/bob/private-token-b.json",
            "?secret=query-b",
            "9f8e7d6c5b4a32109f8e7d6c5b4a3210",
            options,
            releaseEvidenceEndpoint);
        DefaultHttpContext unknownContext = CreateContext(
            "PURGE-private-tenant",
            "/unknown/private-user-a/token-a",
            "?secret=query-c",
            "private-user-a@example.com/secret",
            options);
        DefaultHttpContext secondUnknownContext = CreateContext(
            "PURGE-private-tenant-2",
            "/another-unknown/private-user-b/token-b",
            "?secret=query-d",
            "private-user-b",
            options);

        await middleware.InvokeAsync(firstContext);
        await middleware.InvokeAsync(secondContext);
        await middleware.InvokeAsync(unknownContext);
        await middleware.InvokeAsync(secondUnknownContext);

        VerificationAssert.Equal("0123456789abcdef0123456789abcdef", firstContext.Response.Headers[options.CorrelationHeaderName].ToString(), "Response should echo a standard opaque trace id.");
        VerificationAssert.True(
            !string.Equals("private-user-a@example.com/secret", unknownContext.Response.Headers[options.CorrelationHeaderName].ToString(), StringComparison.Ordinal),
            "Unsafe client-provided correlation ids should be replaced before entering logs or response telemetry.");
        VerificationAssert.True(
            !string.Equals("private-user-b", secondUnknownContext.Response.Headers[options.CorrelationHeaderName].ToString(), StringComparison.Ordinal),
            "Human-readable client identifiers should not be forwarded into logs as correlation ids.");
        VerificationAssert.True(firstContext.Response.Headers.ContainsKey("traceparent"), "Response should expose the W3C traceparent header.");
        VerificationAssert.Equal(4, observedActivities.Count, "Observability middleware should emit one traced Activity per request when a listener is attached.");
        VerificationAssert.True(measurements.Any(static item => item.InstrumentName == "chummer.run.api.requests.started" && item.Value == 1), "Observability middleware should record a request-started counter.");
        VerificationAssert.True(measurements.Any(static item => item.InstrumentName == "chummer.run.api.requests.completed" && item.Value == 1), "Observability middleware should record a request-completed counter.");
        VerificationAssert.True(measurements.Any(static item => item.InstrumentName == "chummer.run.api.requests.duration.ms" && item.Value >= 0), "Observability middleware should record a request-duration histogram.");

        string[] observedRoutes = measurements
            .Select(item => item.Tags.GetValueOrDefault("http.route")?.ToString())
            .Where(static value => value is not null)
            .Cast<string>()
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToArray();
        VerificationAssert.Equal(2, observedRoutes.Length, "Dynamic and unknown request paths should collapse to two bounded route labels.");
        VerificationAssert.True(observedRoutes.Contains(routeTemplate, StringComparer.Ordinal), "Matched requests should use the stable route template label.");
        VerificationAssert.True(observedRoutes.Contains(HubRequestObservability.MetricRouteFallback, StringComparer.Ordinal), "Unknown requests should share the fixed unmatched-route label.");

        string[] observedMethods = measurements
            .Select(item => item.Tags.GetValueOrDefault("http.method")?.ToString())
            .Where(static value => value is not null)
            .Cast<string>()
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        VerificationAssert.True(observedMethods.Contains(HttpMethods.Get, StringComparer.Ordinal), "Standard methods should remain useful metric labels.");
        VerificationAssert.True(observedMethods.Contains(HubRequestObservability.MetricMethodFallback, StringComparer.Ordinal), "Unknown methods should share the fixed fallback label.");

        VerificationAssert.True(
            measurements.All(static item => !item.Tags.ContainsKey("chummer.correlation_id") && !item.Tags.ContainsKey("url.path")),
            "Metric attributes must exclude correlation ids and raw paths.");
        string allMetricTagValues = string.Join("\n", measurements.SelectMany(static item => item.Tags.Values).Select(static value => value?.ToString()));
        AssertDoesNotContainPrivateRequestContent(allMetricTagValues, "Metric labels");

        VerificationAssert.True(
            observedActivities.All(static activity => activity.TagObjects.All(tag => tag.Key != "url.path" && tag.Key != "chummer.correlation_id")),
            "Traces must exclude raw paths and client correlation ids from attributes.");
        string allActivityTagValues = string.Join("\n", observedActivities.SelectMany(static activity => activity.TagObjects).Select(static tag => tag.Value?.ToString()));
        AssertDoesNotContainPrivateRequestContent(allActivityTagValues, "Trace attributes");

        string allLogs = string.Join("\n", logger.Messages.Concat(logger.Scopes.SelectMany(static scope => scope.Values).Select(static value => value?.ToString() ?? string.Empty)));
        AssertDoesNotContainPrivateRequestContent(allLogs, "Structured logs");
    }

    private static DefaultHttpContext CreateContext(
        string method,
        string path,
        string query,
        string correlationId,
        HubRequestObservabilityOptions options,
        Endpoint? endpoint = null)
    {
        DefaultHttpContext context = new();
        context.Request.Method = method;
        context.Request.Path = path;
        context.Request.QueryString = new QueryString(query);
        context.Request.Headers[options.CorrelationHeaderName] = correlationId;
        context.Response.Body = new MemoryStream();
        if (endpoint is not null)
        {
            context.SetEndpoint(endpoint);
        }

        return context;
    }

    private static Dictionary<string, object?> CopyTags(ReadOnlySpan<KeyValuePair<string, object?>> tags)
    {
        Dictionary<string, object?> copy = new(StringComparer.Ordinal);
        foreach (KeyValuePair<string, object?> tag in tags)
        {
            copy[tag.Key] = tag.Value;
        }

        return copy;
    }

    private static void AssertDoesNotContainPrivateRequestContent(string observed, string surface)
    {
        string[] forbiddenFragments =
        [
            "private-token-a",
            "private-token-b",
            "private-user-a",
            "private-user-b",
            "query-a",
            "query-b",
            "query-c",
            "query-d",
            "PURGE-private-tenant"
        ];
        VerificationAssert.True(
            forbiddenFragments.All(fragment => !observed.Contains(fragment, StringComparison.Ordinal)),
            $"{surface} must not contain raw path, query, or unknown-method content.");
    }

    private sealed record MetricMeasurement(
        string InstrumentName,
        double Value,
        Dictionary<string, object?> Tags);

    private sealed class RecordingLogger<T> : ILogger<T>
    {
        public List<string> Messages { get; } = [];
        public List<Dictionary<string, object?>> Scopes { get; } = [];

        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull
        {
            if (state is IEnumerable<KeyValuePair<string, object?>> values)
            {
                Scopes.Add(values.ToDictionary(static item => item.Key, static item => item.Value, StringComparer.Ordinal));
            }

            return EmptyScope.Instance;
        }

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter)
            => Messages.Add(formatter(state, exception));

        private sealed class EmptyScope : IDisposable
        {
            public static EmptyScope Instance { get; } = new();

            public void Dispose()
            {
            }
        }
    }

    private static string ResolveRepoRoot()
    {
        foreach (string seed in EnumerateRepoRootSeeds())
        {
            string current = seed;
            while (!string.IsNullOrWhiteSpace(current))
            {
                if (File.Exists(Path.Combine(current, "WORKLIST.md")) && Directory.Exists(Path.Combine(current, "Chummer.Run.Api")))
                {
                    return current;
                }

                string? parent = Directory.GetParent(current)?.FullName;
                if (string.Equals(parent, current, StringComparison.Ordinal))
                {
                    break;
                }

                current = parent ?? string.Empty;
            }
        }

        throw new InvalidOperationException("Unable to resolve the chummer6-hub repo root for observability verification.");
    }

    private static IEnumerable<string> EnumerateRepoRootSeeds()
    {
        string? explicitRoot = Environment.GetEnvironmentVariable("CHUMMER_HUB_REPO_ROOT");
        if (!string.IsNullOrWhiteSpace(explicitRoot))
        {
            yield return explicitRoot;
        }

        yield return Directory.GetCurrentDirectory();
        yield return AppContext.BaseDirectory;
    }
}
