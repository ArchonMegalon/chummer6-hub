using System.Diagnostics;
using System.Net;
using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api.Services;

public sealed class PublicRouteWarmupService : IHostedService
{
    private static readonly string[] DefaultRoutes =
    [
        "/",
        "/what-is-chummer",
        "/now",
        "/roadmap",
        "/changelog",
        "/docs",
        "/docs/chummer6-quickstart",
        "/help",
        "/faq",
        "/privacy",
        "/terms",
        "/contact",
        "/participate",
        "/participate/karma-forge",
        "/ready",
        "/play/continuity",
        "/rules",
        "/jackpoint",
        "/runsites",
        "/runbook",
        "/community",
        "/creator",
        "/run-control",
        "/ghostwire",
        "/onramp",
        "/edition-studio",
        "/passport",
        "/table-pulse",
        "/propertyquarry",
        "/origin-dossier",
        "/artifacts",
        "/artifacts/current-preview-build",
        "/artifacts/mac-release-pipeline",
        "/artifacts/runsite-pack",
        "/artifacts/dossier-brief",
        "/artifacts/campaign-primer",
        "/artifacts/campaign-primer-video",
        "/artifacts/mission-brief-video",
        "/artifacts/replay-after-action",
        "/mobile",
        "/play",
        "/packages",
        "/packages/desktop-preview",
        "/ledger/map",
        "/ledger/factions",
        "/ledger/factions/ashline-circle",
        "/ledger/factions/ashline-circle/promo",
        "/ledger/newsroom/turn-1-newsreel",
        "/ledger/newsroom/turn-2-newsreel"
    ];

    private readonly IHostApplicationLifetime _lifetime;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicRouteWarmupService> _logger;
    private readonly CancellationTokenSource _stopCts = new();
    private Task? _warmupTask;

    public PublicRouteWarmupService(
        IHostApplicationLifetime lifetime,
        IConfiguration configuration,
        ILogger<PublicRouteWarmupService> logger)
    {
        _lifetime = lifetime;
        _configuration = configuration;
        _logger = logger;
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        if (!_configuration.GetValue("CHUMMER_PUBLIC_ROUTE_WARMUP_ENABLED", true))
        {
            _logger.LogInformation("Public route warmup is disabled.");
            return Task.CompletedTask;
        }

        _lifetime.ApplicationStarted.Register(() =>
        {
            _warmupTask = Task.Run(() => WarmRoutesAsync(_stopCts.Token));
        });
        return Task.CompletedTask;
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        _stopCts.Cancel();
        if (_warmupTask is null)
        {
            return;
        }

        try
        {
            await Task.WhenAny(_warmupTask, Task.Delay(TimeSpan.FromSeconds(2), cancellationToken)).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // Shutdown should not be delayed by best-effort public route warmup.
        }
    }

    private async Task WarmRoutesAsync(CancellationToken cancellationToken)
    {
        Uri baseUri = ResolveBaseUri();
        string[] routes = ResolveRoutes();
        if (routes.Length == 0)
        {
            _logger.LogInformation("Public route warmup skipped because no routes are configured.");
            return;
        }

        int timeoutSeconds = Math.Clamp(_configuration.GetValue("CHUMMER_PUBLIC_ROUTE_WARMUP_TIMEOUT_SECONDS", 20), 1, 120);
        int successCount = 0;
        int failureCount = 0;
        Stopwatch total = Stopwatch.StartNew();

        using HttpClientHandler handler = new()
        {
            AllowAutoRedirect = true,
            AutomaticDecompression = DecompressionMethods.All
        };
        using HttpClient client = new(handler)
        {
            BaseAddress = baseUri,
            Timeout = TimeSpan.FromSeconds(timeoutSeconds)
        };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("ChummerPublicRouteWarmup/1.0");

        foreach (string route in routes)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Stopwatch routeTimer = Stopwatch.StartNew();
            try
            {
                using HttpResponseMessage response = await client.GetAsync(route, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
                    .ConfigureAwait(false);
                _ = await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
                if ((int)response.StatusCode >= 200 && (int)response.StatusCode < 400)
                {
                    successCount++;
                    _logger.LogInformation(
                        "Public route warmup rendered {Route} -> {StatusCode} in {ElapsedMs} ms.",
                        route,
                        (int)response.StatusCode,
                        routeTimer.Elapsed.TotalMilliseconds);
                    continue;
                }

                failureCount++;
                _logger.LogWarning(
                    "Public route warmup received {StatusCode} from {Route} in {ElapsedMs} ms.",
                    (int)response.StatusCode,
                    route,
                    routeTimer.Elapsed.TotalMilliseconds);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                failureCount++;
                _logger.LogWarning(ex, "Public route warmup failed for {Route}.", route);
            }
        }

        _logger.LogInformation(
            "Public route warmup completed: {SuccessCount} succeeded, {FailureCount} failed in {ElapsedMs} ms.",
            successCount,
            failureCount,
            total.Elapsed.TotalMilliseconds);
    }

    private Uri ResolveBaseUri()
    {
        string configured = (_configuration["CHUMMER_PUBLIC_ROUTE_WARMUP_BASE_URL"] ?? "http://127.0.0.1:8080").Trim();
        return Uri.TryCreate(configured, UriKind.Absolute, out Uri? parsed)
            ? parsed
            : new Uri("http://127.0.0.1:8080");
    }

    private string[] ResolveRoutes()
    {
        string? configured = _configuration["CHUMMER_PUBLIC_ROUTE_WARMUP_ROUTES"];
        if (string.IsNullOrWhiteSpace(configured))
        {
            return DefaultRoutes;
        }

        return configured
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(static route => route.StartsWith('/'))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }
}
