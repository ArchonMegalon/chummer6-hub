using System.Text;
using System.Text.Json;
using System.Net;
using Chummer.Contracts.Presentation;

namespace Chummer.Run.Api.Services;

public sealed class DesktopAnalyticsBridgeService : IDisposable
{
    public const long MaxRequestBodyBytes = 16 * 1024;
    internal const int MaxHeadIdLength = 128;
    internal const int MaxSurfaceLength = 128;
    internal const int MaxReleaseVersionLength = 64;
    internal const int MaxReleaseChannelLength = 32;
    internal const int MaxUiModeLength = 32;
    internal const int MaxLanguageLength = 32;
    internal const int MaxPropertyCount = 16;
    internal const int MaxPropertyKeyLength = 64;
    internal const int MaxPropertyValueLength = 256;
    private const int MaxUserAgentLength = 256;
    private static readonly HashSet<string> AllowedEvents = new(StringComparer.Ordinal)
    {
        "desktop_shell_opened",
        "desktop_open_home",
        "desktop_open_horizons",
        "desktop_open_auto_alice",
        "desktop_open_origin_dossier",
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
    private static readonly HashSet<string> ReservedPropertyKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        "surface",
        "head_id",
        "ui_mode",
        "language",
        "release_version",
        "release_channel",
        "occurred_at_utc"
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

        if (!IsBounded(request.HeadId, MaxHeadIdLength))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "head_id_invalid");
        }

        if (!IsBounded(request.Surface, MaxSurfaceLength))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "surface_invalid");
        }

        if (!IsBounded(request.ReleaseVersion, MaxReleaseVersionLength))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "release_version_invalid");
        }

        if (!IsBounded(request.ReleaseChannel, MaxReleaseChannelLength))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "release_channel_invalid");
        }

        if (!IsOptionalBounded(request.UiMode, MaxUiModeLength))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "ui_mode_invalid");
        }

        if (!IsOptionalBounded(request.Language, MaxLanguageLength))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: "language_invalid");
        }

        if (!TryNormalizeProperties(request.Properties, out Dictionary<string, string> normalizedProperties, out string? rejectedStatus))
        {
            return new DesktopAnalyticsTrackResult(Accepted: false, Forwarded: false, Status: rejectedStatus ?? "properties_invalid");
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
                    user_agent = NormalizeUserAgent(userAgent, request.ReleaseVersion),
                    ip_address = NormalizeIpAddress(remoteIpAddress),
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

    private static bool TryNormalizeProperties(
        IReadOnlyDictionary<string, string>? properties,
        out Dictionary<string, string> normalizedProperties,
        out string? rejectedStatus)
    {
        normalizedProperties = new Dictionary<string, string>(StringComparer.Ordinal);
        rejectedStatus = null;

        if (properties is null || properties.Count == 0)
        {
            return true;
        }

        if (properties.Count > MaxPropertyCount)
        {
            rejectedStatus = "properties_limit_exceeded";
            return false;
        }

        foreach ((string key, string value) in properties)
        {
            string? normalizedKey = TrimToNull(key);
            string? normalizedValue = TrimToNull(value);
            if (normalizedKey is null || normalizedValue is null)
            {
                continue;
            }

            if (normalizedKey.Length > MaxPropertyKeyLength)
            {
                rejectedStatus = "property_key_invalid";
                return false;
            }

            if (normalizedValue.Length > MaxPropertyValueLength)
            {
                rejectedStatus = "property_value_invalid";
                return false;
            }

            if (ReservedPropertyKeys.Contains(normalizedKey))
            {
                rejectedStatus = "property_key_reserved";
                return false;
            }

            normalizedProperties[normalizedKey] = normalizedValue;
        }

        return true;
    }

    private static string NormalizeUserAgent(string? userAgent, string releaseVersion)
    {
        string fallback = $"ChummerDesktop/{releaseVersion.Trim()}";
        string candidate = TrimToNull(userAgent) ?? fallback;
        return candidate.Length <= MaxUserAgentLength ? candidate : candidate[..MaxUserAgentLength];
    }

    private static string? NormalizeIpAddress(string? remoteIpAddress)
    {
        string? candidate = TrimToNull(remoteIpAddress);
        return candidate is not null && IPAddress.TryParse(candidate, out _) ? candidate : null;
    }

    private static bool IsBounded(string? value, int maxLength)
    {
        string? normalized = TrimToNull(value);
        return normalized is not null && normalized.Length <= maxLength;
    }

    private static bool IsOptionalBounded(string? value, int maxLength)
    {
        string? normalized = TrimToNull(value);
        return normalized is null || normalized.Length <= maxLength;
    }

    private static string? TrimToNull(string? value)
    {
        string? trimmed = value?.Trim();
        return string.IsNullOrWhiteSpace(trimmed) ? null : trimmed;
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
