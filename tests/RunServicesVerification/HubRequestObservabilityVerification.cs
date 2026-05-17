using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.IO;
using Chummer.Run.Api;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;

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
        List<(string InstrumentName, long Value)> counters = [];
        List<(string InstrumentName, double Value)> histograms = [];

        using MeterListener meterListener = new();
        meterListener.InstrumentPublished = (instrument, listener) =>
        {
            if (string.Equals(instrument.Meter.Name, HubRequestObservability.MeterName, StringComparison.Ordinal))
            {
                listener.EnableMeasurementEvents(instrument);
            }
        };
        meterListener.SetMeasurementEventCallback<long>((instrument, measurement, _, _) =>
        {
            counters.Add((instrument.Name, measurement));
        });
        meterListener.SetMeasurementEventCallback<double>((instrument, measurement, _, _) =>
        {
            histograms.Add((instrument.Name, measurement));
        });
        meterListener.Start();

        Activity? observedActivity = null;
        using ActivityListener activityListener = new()
        {
            ShouldListenTo = source => string.Equals(source.Name, HubRequestObservability.ActivitySourceName, StringComparison.Ordinal),
            Sample = static (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activity => observedActivity = activity
        };
        ActivitySource.AddActivityListener(activityListener);

        HubRequestObservabilityMiddleware middleware = new(async context =>
        {
            VerificationAssert.NotNull(context.Items[HubRequestObservability.CorrelationItemKey] as string, "Middleware should stamp a correlation id before controller execution.");
            context.Response.StatusCode = StatusCodes.Status202Accepted;
            await context.Response.StartAsync();
            await context.Response.WriteAsync("ok");
        }, options, NullLogger<HubRequestObservabilityMiddleware>.Instance);

        DefaultHttpContext context = new();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = "/api/v1/support/cases";
        context.Request.Headers[options.CorrelationHeaderName] = "corr-test-001";
        context.Response.Body = new MemoryStream();

        await middleware.InvokeAsync(context);

        VerificationAssert.Equal("corr-test-001", context.Response.Headers[options.CorrelationHeaderName].ToString(), "Response should echo the correlation header.");
        VerificationAssert.True(context.Response.Headers.ContainsKey("traceparent"), "Response should expose the W3C traceparent header.");
        VerificationAssert.NotNull(observedActivity, "Observability middleware should emit a traced Activity when a listener is attached.");
        VerificationAssert.True(counters.Any(static item => item.InstrumentName == "chummer.run.api.requests.started" && item.Value == 1), "Observability middleware should record a request-started counter.");
        VerificationAssert.True(counters.Any(static item => item.InstrumentName == "chummer.run.api.requests.completed" && item.Value == 1), "Observability middleware should record a request-completed counter.");
        VerificationAssert.True(histograms.Any(static item => item.InstrumentName == "chummer.run.api.requests.duration.ms" && item.Value >= 0), "Observability middleware should record a request-duration histogram.");
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
