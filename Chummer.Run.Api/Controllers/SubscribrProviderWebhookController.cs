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
    public ActionResult<SubscribrWebhookResult> Webhook([FromBody] SubscribrWebhookRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Subscribr webhook payload is required.");
        }

        try
        {
            SubscribrWebhookResult result = _webhooks.ProcessWebhook(
                request,
                Request.Headers["X-Subscribr-Signature"].ToString(),
                Request.Headers["X-Subscribr-Timestamp"].ToString());
            return result.Status == "rejected"
                ? Problem(statusCode: StatusCodes.Status400BadRequest, detail: result.RejectionReason)
                : Ok(result);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }
}
