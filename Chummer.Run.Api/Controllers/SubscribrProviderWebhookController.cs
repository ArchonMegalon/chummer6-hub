using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[IgnoreAntiforgeryToken]
public sealed class SubscribrProviderWebhookController : ControllerBase
{
    private readonly SubscribrProviderWebhookService _webhooks;

    public SubscribrProviderWebhookController(SubscribrProviderWebhookService webhooks)
    {
        _webhooks = webhooks;
    }

    [HttpPost("/internal/providers/subscribr/webhook")]
    [HttpPost("/api/internal/providers/subscribr/webhook")]
    [ProducesResponseType<SubscribrWebhookResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<SubscribrWebhookResult>> Webhook(CancellationToken cancellationToken)
    {
        string rawPayload;
        using (var reader = new StreamReader(Request.Body, Encoding.UTF8, detectEncodingFromByteOrderMarks: false))
        {
            rawPayload = await reader.ReadToEndAsync(cancellationToken);
        }

        if (string.IsNullOrWhiteSpace(rawPayload))
        {
            return BadRequest("Subscribr webhook payload is required.");
        }

        try
        {
            SubscribrWebhookRequest? request = JsonSerializer.Deserialize<SubscribrWebhookRequest>(
                rawPayload,
                new JsonSerializerOptions(JsonSerializerDefaults.Web));
            if (request is null)
            {
                return BadRequest("Subscribr webhook payload is required.");
            }

            SubscribrWebhookResult result = _webhooks.ProcessWebhook(
                rawPayload,
                request,
                Request.Headers["X-Subscribr-Signature"].ToString(),
                Request.Headers["X-Subscribr-Timestamp"].ToString());
            return result.Status == "rejected"
                ? Problem(statusCode: StatusCodes.Status400BadRequest, detail: result.RejectionReason)
                : Ok(result);
        }
        catch (JsonException)
        {
            return BadRequest("Subscribr webhook payload must be valid JSON.");
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }
}
