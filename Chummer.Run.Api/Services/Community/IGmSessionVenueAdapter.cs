using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Chummer.Campaign.Contracts;

namespace Chummer.Run.Api.Services.Community;

public sealed record GmSessionVenuePlan(
    string CampaignId,
    string SessionId,
    string PublicSafeSessionTitle,
    DateTimeOffset ScheduledStartUtc,
    DateTimeOffset? ScheduledEndUtc,
    string Visibility,
    int? RegistrationCapacity,
    bool ConsentToShareAttendeeEmails);

public sealed record GmSessionVenuePatch(
    string? PublicSafeSessionTitle = null,
    DateTimeOffset? ScheduledStartUtc = null,
    DateTimeOffset? ScheduledEndUtc = null,
    string? Visibility = null);

public sealed record GmSessionVenueAdapterAvailability(
    bool CreateModeAvailable,
    string? FailureReason);

public sealed record GmSessionVenueAdapterCreateResult(
    string ProviderEventId,
    string ProviderEventUrl,
    string ProviderRoomUrl,
    string PrivacyStatus,
    int? Capacity);

public sealed record GmSessionVenueAttendanceSyncResult(
    string AttendanceSyncStatus,
    int? AttendeeCount);

public interface IGmSessionVenueAdapter
{
    GmSessionVenueAdapterAvailability GetAvailability();

    Task<string> ValidateVenueUrlAsync(string url, CancellationToken cancellationToken = default);

    Task<GmSessionVenueAdapterCreateResult> CreateSessionVenueAsync(
        GmSessionVenuePlan plan,
        CancellationToken cancellationToken = default);

    Task UpdateSessionVenueAsync(
        string venueId,
        GmSessionVenuePatch patch,
        CancellationToken cancellationToken = default);

    Task DisableSessionVenueAsync(
        string venueId,
        CancellationToken cancellationToken = default);

    Task<GmSessionVenueAttendanceSyncResult> SyncAttendanceAsync(
        string venueId,
        CancellationToken cancellationToken = default);
}

public sealed class BeHumanGmSessionVenueAdapter : IGmSessionVenueAdapter
{
    private static readonly string[] SuspiciousSchemes = ["javascript:", "data:", "vbscript:"];
    private static readonly string[] SuspiciousQueryKeys = ["access_token", "token", "api_key", "apikey", "secret", "sig", "signature"];

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;
    private readonly BeHumanEventAdapterPostureService _postureService;

    public BeHumanGmSessionVenueAdapter(
        IHttpClientFactory httpClientFactory,
        IConfiguration configuration,
        BeHumanEventAdapterPostureService postureService)
    {
        _httpClientFactory = httpClientFactory;
        _configuration = configuration;
        _postureService = postureService;
    }

    public GmSessionVenueAdapterAvailability GetAvailability()
    {
        BeHumanEventAdapterPosture posture = _postureService.Build();
        if (posture.Verdict != "BEHUMAN_EVENT_ADAPTER_READY")
        {
            return new(false, "Create BeHuman venue is unavailable until service setup and operating status are ready.");
        }

        if (string.Equals(posture.OperatingMode, "manual", StringComparison.OrdinalIgnoreCase)
            || string.Equals(posture.OperatingMode, "manual_link_mode", StringComparison.OrdinalIgnoreCase))
        {
            return new(false, "Create BeHuman venue is unavailable while the adapter stays in manual-link mode.");
        }

        if (string.IsNullOrWhiteSpace(GetVenueApiBaseUrl()))
        {
            return new(false, "Create BeHuman venue is unavailable until an adapter transport base URL exists.");
        }

        return new(true, null);
    }

    public Task<string> ValidateVenueUrlAsync(string url, CancellationToken cancellationToken = default)
        => Task.FromResult(ValidateVenueUrl(url));

    public async Task<GmSessionVenueAdapterCreateResult> CreateSessionVenueAsync(
        GmSessionVenuePlan plan,
        CancellationToken cancellationToken = default)
    {
        GmSessionVenueAdapterAvailability availability = GetAvailability();
        if (!availability.CreateModeAvailable)
        {
            throw new InvalidOperationException(availability.FailureReason);
        }

        HttpClient client = CreateHttpClient();
        using HttpRequestMessage request = new(HttpMethod.Post, new Uri(new Uri(GetVenueApiBaseUrl()!), "/api/chummer/venues"));
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Content = new StringContent(JsonSerializer.Serialize(new
        {
            campaign_id = plan.CampaignId,
            session_id = plan.SessionId,
            title = plan.PublicSafeSessionTitle,
            scheduled_start_utc = plan.ScheduledStartUtc,
            scheduled_end_utc = plan.ScheduledEndUtc,
            visibility = plan.Visibility,
            registration_capacity = plan.RegistrationCapacity,
            consent_to_share_attendee_emails = plan.ConsentToShareAttendeeEmails
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();

        using JsonDocument json = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false));
        JsonElement root = json.RootElement;
        string providerEventId = root.GetProperty("venue_id").GetString() ?? throw new InvalidOperationException("Provider create response is missing venue_id.");
        string providerEventUrl = ValidateVenueUrl(root.GetProperty("event_url").GetString() ?? throw new InvalidOperationException("Provider create response is missing event_url."));
        string providerRoomUrl = ValidateVenueUrl(root.GetProperty("room_url").GetString() ?? providerEventUrl);
        string privacyStatus = NormalizeOptional(root.TryGetProperty("privacy_status", out JsonElement privacy) ? privacy.GetString() : null) ?? "pass";
        int? capacity = root.TryGetProperty("capacity", out JsonElement cap) && cap.ValueKind == JsonValueKind.Number
            ? cap.GetInt32()
            : plan.RegistrationCapacity;

        return new(providerEventId, providerEventUrl, providerRoomUrl, privacyStatus, capacity);
    }

    public async Task UpdateSessionVenueAsync(string venueId, GmSessionVenuePatch patch, CancellationToken cancellationToken = default)
    {
        HttpClient client = CreateHttpClient();
        using HttpRequestMessage request = new(HttpMethod.Patch, new Uri(new Uri(GetVenueApiBaseUrl()!), $"/api/chummer/venues/{Uri.EscapeDataString(venueId)}"));
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Content = new StringContent(JsonSerializer.Serialize(new
        {
            title = patch.PublicSafeSessionTitle,
            scheduled_start_utc = patch.ScheduledStartUtc,
            scheduled_end_utc = patch.ScheduledEndUtc,
            visibility = patch.Visibility
        }), Encoding.UTF8, "application/json");
        using HttpResponseMessage response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
    }

    public async Task DisableSessionVenueAsync(string venueId, CancellationToken cancellationToken = default)
    {
        HttpClient client = CreateHttpClient();
        using HttpRequestMessage request = new(HttpMethod.Post, new Uri(new Uri(GetVenueApiBaseUrl()!), $"/api/chummer/venues/{Uri.EscapeDataString(venueId)}/disable"));
        using HttpResponseMessage response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
    }

    public async Task<GmSessionVenueAttendanceSyncResult> SyncAttendanceAsync(string venueId, CancellationToken cancellationToken = default)
    {
        HttpClient client = CreateHttpClient();
        using HttpRequestMessage request = new(HttpMethod.Get, new Uri(new Uri(GetVenueApiBaseUrl()!), $"/api/chummer/venues/{Uri.EscapeDataString(venueId)}/attendance"));
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        using HttpResponseMessage response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();

        using JsonDocument json = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false));
        JsonElement root = json.RootElement;
        int? attendeeCount = root.TryGetProperty("attendee_count", out JsonElement count) && count.ValueKind == JsonValueKind.Number
            ? count.GetInt32()
            : null;
        return new("complete", attendeeCount);
    }

    private HttpClient CreateHttpClient()
    {
        HttpClient client = _httpClientFactory.CreateClient(nameof(BeHumanGmSessionVenueAdapter));
        string? apiKey = NormalizeOptional(_configuration["Community:BeHuman:ApiKey"]) ?? NormalizeOptional(_configuration["BEHUMAN_API_KEY"]);
        if (!string.IsNullOrWhiteSpace(apiKey))
        {
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        }

        return client;
    }

    private string ValidateVenueUrl(string venueUrl)
    {
        string normalized = NormalizeOptional(venueUrl)
            ?? throw new ArgumentException("venue_url is required.", nameof(venueUrl));

        foreach (string scheme in SuspiciousSchemes)
        {
            if (normalized.StartsWith(scheme, StringComparison.OrdinalIgnoreCase))
            {
                throw new ArgumentException("venue_url uses a forbidden scheme.", nameof(venueUrl));
            }
        }

        if (!Uri.TryCreate(normalized, UriKind.Absolute, out Uri? uri))
        {
            throw new ArgumentException("venue_url must be an absolute URL.", nameof(venueUrl));
        }

        if (!string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("venue_url must use https.", nameof(venueUrl));
        }

        if (!string.IsNullOrWhiteSpace(uri.UserInfo))
        {
            throw new ArgumentException("venue_url may not include embedded credentials.", nameof(venueUrl));
        }

        string host = uri.Host.Trim().ToLowerInvariant();
        string[] allowedDomains = (_configuration["Community:BeHuman:AllowedDomains"] ?? "behuman.online")
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (!allowedDomains.Any(domain => host.Equals(domain, StringComparison.OrdinalIgnoreCase) || host.EndsWith($".{domain}", StringComparison.OrdinalIgnoreCase)))
        {
            throw new ArgumentException("venue_url host is not an allowed BeHuman domain.", nameof(venueUrl));
        }

        if (host is "bit.ly" or "t.co" or "tinyurl.com")
        {
            throw new ArgumentException("venue_url may not use a shortened domain.", nameof(venueUrl));
        }

        if (uri.Fragment.Length > 0)
        {
            throw new ArgumentException("venue_url may not include fragments.", nameof(venueUrl));
        }

        string query = uri.Query.TrimStart('?');
        if (!string.IsNullOrWhiteSpace(query))
        {
            foreach (string pair in query.Split('&', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                string key = pair.Split('=', 2)[0].Trim();
                if (SuspiciousQueryKeys.Any(suspicious => key.Equals(suspicious, StringComparison.OrdinalIgnoreCase)))
                {
                    throw new ArgumentException("venue_url may not include suspicious query payloads.", nameof(venueUrl));
                }
            }
        }

        return uri.ToString();
    }

    private string? GetVenueApiBaseUrl()
        => NormalizeOptional(_configuration["Community:BeHuman:VenueApiBaseUrl"]);

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
