using System.Text;
using System.Text.Json;
using Chummer.Contracts.Presentation;

namespace Chummer.Run.Api.Services;

public sealed class DesktopAnalyticsBridgeService : IDisposable
{
    private static readonly HashSet<string> AllowedEvents = new(StringComparer.Ordinal)
    {
        "desktop_shell_opened",
        "desktop_open_home",
        "desktop_open_horizons",
        "desktop_open_campaign_workspace",
        "desktop_open_update_status",
        "desktop_open_install_linking",
        "desktop_open_support",
        "desktop_open_report_issue",
        "desktop_open_settings"
    };

    private readonly IConfiguration _configuration;
    private readonly ILogger<DesktopAnalyticsBridgeService> _logger;
    private readonly HttpClient _httpClient;
    private static readonly HashSet<string> AllowedLocalOrigins = new(StringComparer.OrdinalIgnoreCase)
    {
        "localhost",
        "127.0.0.1",
        "host.docker.internal"
    };

    public DesktopAnalyticsBridgeService(IConfiguration configuration, ILogger<DesktopAnalyticsBridgeService> logger)
    {
        _configuration = configuration;
        _logger = logger;
        _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(10)
        };
    }

    public async Task<DesktopAnalyticsTrackResult> TrackAsync(
        DesktopAnalyticsTrackRequest request,
        string? remoteIpAddress,
        string? userAgent,
        CancellationToken ct)
    {
        if (!request.OptIn)
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "opt_in_required");
        }

        if (!AllowedEvents.Contains(request.EventName))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "event_not_allowed");
        }

        string siteId = (_configuration["RYBBIT_CHUMMER_DESKTOP_SITE_ID"] ?? string.Empty).Trim();
        string apiKey = (_configuration["RYBBIT_CHUMMER_DESKTOP_API_KEY"] ?? string.Empty).Trim();
        string origin = (_configuration["RYBBIT_CHUMMER_DESKTOP_API_ORIGIN"] ?? "https://app.rybbit.io").Trim().TrimEnd('/');

        if (string.IsNullOrWhiteSpace(siteId))
        {
            return new DesktopAnalyticsTrackResult(Accepted: true, Forwarded: false, Status: "provider_not_configured");
        }

        if (!Uri.TryCreate($"{origin}/api/track", UriKind.Absolute, out Uri? trackUri)
            || !IsAllowedTrackUri(trackUri))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "provider_origin_invalid");
        }

        Dictionary<string, string> normalizedProperties = new(StringComparer.Ordinal);
        if (request.Properties is not null)
        {
            foreach ((string key, string value) in request.Properties)
            {
                if (string.IsNullOrWhiteSpace(key) || string.IsNullOrWhiteSpace(value))
                {
                    continue;
                }

                normalizedProperties[key.Trim()] = value.Trim();
            }
        }

        string normalizedSurface = NormalizeSegment(request.Surface, "desktop");
        string normalizedHeadId = NormalizeSegment(request.HeadId, "desktop");
        Dictionary<string, string> analyticsProperties = new(StringComparer.Ordinal)
        {
            ["surface"] = request.Surface.Trim(),
            ["head_id"] = request.HeadId.Trim(),
            ["ui_mode"] = request.UiMode?.Trim() ?? string.Empty,
            ["language"] = request.Language?.Trim() ?? string.Empty,
            ["release_version"] = request.ReleaseVersion.Trim(),
            ["release_channel"] = request.ReleaseChannel.Trim(),
            ["occurred_at_utc"] = (request.OccurredAtUtc ?? DateTimeOffset.UtcNow).ToUniversalTime().ToString("O")
        };
        foreach ((string key, string value) in normalizedProperties)
        {
            analyticsProperties[key] = value;
        }

        string propertiesJson = JsonSerializer.Serialize(analyticsProperties);

        using HttpRequestMessage outbound = new(HttpMethod.Post, trackUri)
        {
            Content = new StringContent(
                JsonSerializer.Serialize(new
                {
                    site_id = siteId,
                    type = "custom_event",
                    pathname = $"/desktop/{normalizedHeadId}/{normalizedSurface}",
                    hostname = "desktop.chummer.run",
                    event_name = request.EventName,
                    user_agent = string.IsNullOrWhiteSpace(userAgent) ? $"ChummerDesktop/{request.ReleaseVersion}" : userAgent,
                    ip_address = string.IsNullOrWhiteSpace(remoteIpAddress) ? null : remoteIpAddress,
                    properties = propertiesJson
                }),
                Encoding.UTF8,
                "application/json")
        };
        if (!string.IsNullOrWhiteSpace(apiKey))
        {
            outbound.Headers.TryAddWithoutValidation("Authorization", $"Bearer {apiKey}");
        }

        try
        {
            using HttpResponseMessage response = await _httpClient.SendAsync(outbound, ct).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                string error = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
                _logger.LogWarning(
                    "Desktop analytics forwarding failed for {EventName} with HTTP {StatusCode}: {Error}",
                    request.EventName,
                    (int)response.StatusCode,
                    error);
                return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: $"provider_http_{(int)response.StatusCode}");
            }

            return new DesktopAnalyticsTrackResult(
                Accepted: true,
                Forwarded: true,
                Status: string.IsNullOrWhiteSpace(apiKey) ? "forwarded_public" : "forwarded");
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Desktop analytics forwarding failed for {EventName}.", request.EventName);
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "provider_error");
        }
    }

    public void Dispose()
    {
        _httpClient.Dispose();
    }

    private static string NormalizeSegment(string? value, string fallback)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return fallback;
        }

        StringBuilder builder = new(value.Length);
        foreach (char character in value.Trim())
        {
            builder.Append(char.IsLetterOrDigit(character) ? char.ToLowerInvariant(character) : '-');
        }

        string normalized = builder.ToString().Trim('-');
        return string.IsNullOrWhiteSpace(normalized) ? fallback : normalized;
    }

    private static bool IsAllowedTrackUri(Uri trackUri)
    {
        if (trackUri.Scheme == Uri.UriSchemeHttps)
        {
            return true;
        }

        return trackUri.Scheme == Uri.UriSchemeHttp
            && AllowedLocalOrigins.Contains(trackUri.Host);
    }
}
