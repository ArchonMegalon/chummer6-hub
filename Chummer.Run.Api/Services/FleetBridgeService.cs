using System.Net.Http.Json;
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

    public Task<JsonObject> CreateParticipantLaneAsync(string subjectId, string subjectLabel, string projectId, CancellationToken cancellationToken)
    {
        var payload = new
        {
            subject_id = subjectId,
            subject_label = subjectLabel,
            project_id = projectId,
            backend = "chatgpt_participant"
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
        using var request = new HttpRequestMessage(method, $"{BaseUrl}{path}");
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
