using System.Net.Http.Json;
using System.Net.Http.Headers;
using System.Text.Json.Nodes;

namespace Chummer.Run.Api.Services;

public sealed class FleetBridgeService
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;

    public FleetBridgeService(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _configuration = configuration;
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
            throw new InvalidOperationException("FLEET_INTERNAL_API_TOKEN is required for Fleet participant-lane bridge calls.");
        }

        using var request = new HttpRequestMessage(method, $"{BaseUrl}{path}");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", InternalApiToken);
        if (payload is not null)
        {
            request.Content = JsonContent.Create(payload);
        }

        using var response = await _httpClient.SendAsync(request, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        var json = string.IsNullOrWhiteSpace(body)
            ? new JsonObject()
            : JsonNode.Parse(body)?.AsObject() ?? new JsonObject();

        if (!response.IsSuccessStatusCode)
        {
            var detail = json["detail"]?.GetValue<string>() ?? body;
            throw new InvalidOperationException($"Fleet bridge request failed ({(int)response.StatusCode}): {detail}");
        }

        return json;
    }
}
