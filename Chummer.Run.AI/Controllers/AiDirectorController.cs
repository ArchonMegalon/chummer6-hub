using Microsoft.AspNetCore.Mvc;
using SubmitObservationRequest = Chummer.Run.Contracts.Gateway.SubmitObservationRequest;
using SubmitObservationResponse = Chummer.Run.Contracts.Gateway.SubmitObservationResponse;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/director")]
public sealed class AiDirectorController : ControllerBase
{
    [HttpPost("observations")]
    [ProducesResponseType<SubmitObservationResponse>(StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<SubmitObservationResponse> SubmitObservation([FromBody] SubmitObservationRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Observation request is required.");
        }

        if (string.IsNullOrWhiteSpace(request.SessionId))
        {
            return BadRequest("sessionId is required.");
        }

        return Accepted(new SubmitObservationResponse(
            ObservationId: $"obs-{Guid.NewGuid():N}",
            Status: "accepted",
            AcceptedAtUtc: DateTimeOffset.UtcNow));
    }
}
