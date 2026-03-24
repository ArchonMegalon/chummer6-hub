using System.Net;
using System.Net.Http.Json;
using System.Net.Http.Headers;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services;

public sealed class ParticipationUnavailableException : InvalidOperationException
{
    public ParticipationUnavailableException(string message, Exception? innerException = null)
        : base(message, innerException)
    {
    }
}

public sealed class FleetBridgeService
{
    private const string ParticipationUnavailableMessage = "Participation is unavailable on this host right now. Try again later.";
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<FleetBridgeService> _logger;
    private static readonly TimeSpan DefaultRequestTimeout = TimeSpan.FromSeconds(15);
    private static readonly TimeSpan DeviceAuthStartTimeout = TimeSpan.FromSeconds(25);

    public FleetBridgeService(HttpClient httpClient, IConfiguration configuration, ILogger<FleetBridgeService>? logger = null)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger ?? NullLogger<FleetBridgeService>.Instance;
    }

    private string BaseUrl =>
        (_configuration["FLEET_CONTROLLER_BASE_URL"] ?? "http://fleet-controller:8090").TrimEnd('/');

    private string InternalApiToken =>
        (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();

    public Task<JsonObject> CreateParticipantLaneAsync(
        string subjectId,
        string subjectLabel,
        string projectId,
        string hubUserId,
        string hubGroupId,
        string boostCampaignId,
        string sponsorSessionId,
        string publicContributionVisibility,
        string laneRole,
        string authorizationTier,
        string tierSource,
        CancellationToken cancellationToken)
    {
        var payload = new
        {
            subject_id = subjectId,
            subject_label = subjectLabel,
            project_id = projectId,
            backend = "chatgpt_participant",
            hub_user_id = hubUserId,
            hub_group_id = hubGroupId,
            boost_campaign_id = boostCampaignId,
            sponsor_session_id = sponsorSessionId,
            public_contribution_visibility = publicContributionVisibility,
            lane_role = laneRole,
            authorization_tier = authorizationTier,
            tier_source = tierSource,
        };
        return SendAsync(HttpMethod.Post, "/api/internal/participant-lanes", payload, cancellationToken);
    }

    public Task<JsonObject> StartDeviceAuthAsync(string laneId, CancellationToken cancellationToken)
        => SendAsync(HttpMethod.Post, $"/api/internal/participant-lanes/{Uri.EscapeDataString(laneId)}/device-auth/start", null, cancellationToken);

    public Task<JsonObject> GetParticipantLaneAsync(string laneId, CancellationToken cancellationToken)
        => SendAsync(HttpMethod.Get, $"/api/internal/participant-lanes/{Uri.EscapeDataString(laneId)}", null, cancellationToken);

    public Task<JsonObject> ActivateParticipantLaneAsync(string laneId, CancellationToken cancellationToken)
        => SendAsync(HttpMethod.Post, $"/api/internal/participant-lanes/{Uri.EscapeDataString(laneId)}/activate", null, cancellationToken);

    public Task<JsonObject> StopParticipantLaneAsync(string laneId, CancellationToken cancellationToken)
        => SendAsync(HttpMethod.Post, $"/api/internal/participant-lanes/{Uri.EscapeDataString(laneId)}/stop", null, cancellationToken);

    public Task<JsonObject> DeleteParticipantLaneAsync(string laneId, CancellationToken cancellationToken)
        => SendAsync(HttpMethod.Delete, $"/api/internal/participant-lanes/{Uri.EscapeDataString(laneId)}", null, cancellationToken);

    private async Task<JsonObject> SendAsync(HttpMethod method, string path, object? payload, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(InternalApiToken))
        {
            _logger.LogWarning("Fleet bridge is unavailable because FLEET_INTERNAL_API_TOKEN is not configured for {Path}.", path);
            throw new ParticipationUnavailableException(ParticipationUnavailableMessage);
        }

        using var request = new HttpRequestMessage(method, $"{BaseUrl}{path}");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", InternalApiToken);
        if (payload is not null)
        {
            request.Content = JsonContent.Create(payload);
        }

        HttpResponseMessage response;
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(ResolveRequestTimeout(path));
        try
        {
            response = await _httpClient.SendAsync(request, timeoutCts.Token);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Fleet bridge request failed for {Method} {Path}.", method, path);
            throw new ParticipationUnavailableException(ParticipationUnavailableMessage, ex);
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Fleet bridge request timed out for {Method} {Path}.", method, path);
            throw new ParticipationUnavailableException(ParticipationUnavailableMessage, ex);
        }

        using (response)
        {
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            var json = string.IsNullOrWhiteSpace(body)
                ? new JsonObject()
                : JsonNode.Parse(body)?.AsObject() ?? new JsonObject();

            if (!response.IsSuccessStatusCode)
            {
                var detail = json["detail"]?.GetValue<string>() ?? body;
                if (ShouldMaskAsParticipationUnavailable(response.StatusCode, detail))
                {
                    _logger.LogWarning(
                        "Masking Fleet bridge failure for {Method} {Path} with status {StatusCode}. Detail: {Detail}",
                        method,
                        path,
                        (int)response.StatusCode,
                        string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
                    throw new ParticipationUnavailableException(ParticipationUnavailableMessage);
                }

                throw new InvalidOperationException($"Fleet bridge request failed ({(int)response.StatusCode}): {detail}");
            }

            return json;
        }
    }

    private static bool ShouldMaskAsParticipationUnavailable(HttpStatusCode statusCode, string? detail)
        => statusCode switch
        {
            HttpStatusCode.Conflict => !IsCapacityConflict(detail),
            HttpStatusCode.BadRequest
                or HttpStatusCode.Unauthorized
                or HttpStatusCode.Forbidden
                or HttpStatusCode.NotFound
                or HttpStatusCode.TooManyRequests
                or HttpStatusCode.BadGateway
                or HttpStatusCode.ServiceUnavailable
                or HttpStatusCode.GatewayTimeout
                or HttpStatusCode.InternalServerError => true,
            _ => ((int)statusCode >= 500) || ContainsInternalBridgeDetail(detail)
        };

    private static bool IsCapacityConflict(string? detail)
        => !string.IsNullOrWhiteSpace(detail)
            && detail.Contains("capacity reached", StringComparison.OrdinalIgnoreCase);

    private static bool ContainsInternalBridgeDetail(string? detail)
        => !string.IsNullOrWhiteSpace(detail)
            && (detail.Contains("participant lane internal auth is not configured", StringComparison.OrdinalIgnoreCase)
                || detail.Contains("participant-lane bridge", StringComparison.OrdinalIgnoreCase)
                || detail.Contains("FLEET_INTERNAL_API_TOKEN", StringComparison.OrdinalIgnoreCase));

    private static TimeSpan ResolveRequestTimeout(string path)
        => path.Contains("/device-auth/start", StringComparison.OrdinalIgnoreCase)
            ? DeviceAuthStartTimeout
            : DefaultRequestTimeout;
}
