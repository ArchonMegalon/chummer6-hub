using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[IgnoreAntiforgeryToken]
public sealed class InternalExecutiveAssistantChannelsController : ControllerBase
{
    private readonly ExecutiveAssistantChannelMessagingService _messaging;
    private readonly IConfiguration _configuration;

    public InternalExecutiveAssistantChannelsController(
        ExecutiveAssistantChannelMessagingService messaging,
        IConfiguration configuration)
    {
        _messaging = messaging;
        _configuration = configuration;
    }

    [HttpPost("/api/internal/executive-assistant/channels/{channelKind}/messages")]
    [ProducesResponseType<ExecutiveAssistantChannelMessageDto>(StatusCodes.Status200OK)]
    public ActionResult<ExecutiveAssistantChannelMessageDto> IngestMessage(
        string channelKind,
        [FromBody] ExecutiveAssistantChannelIncomingMessageRequest? request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BadRequest("Executive assistant incoming message payload is required.");
        }

        try
        {
            return Ok(_messaging.IngestIncomingMessage(channelKind, request));
        }
        catch (ArgumentException ex)
        {
            return Problem(
                detail: ex.Message,
                statusCode: StatusCodes.Status400BadRequest,
                title: "Executive assistant incoming message rejected");
        }
        catch (InvalidOperationException ex)
        {
            return Problem(
                detail: ex.Message,
                statusCode: StatusCodes.Status409Conflict,
                title: "Executive assistant incoming message rejected");
        }
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = Normalize(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_WEBHOOK_TOKEN"])
            ?? Normalize(_configuration["CHUMMER_EA_WEBHOOK_TOKEN"])
            ?? Normalize(_configuration["FLEET_INTERNAL_API_TOKEN"])
            ?? string.Empty;

        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(
                detail: "Executive assistant webhook authorization is not configured.",
                statusCode: StatusCodes.Status503ServiceUnavailable,
                title: "Executive assistant webhook authorization is not configured",
                type: "https://chummer.run/problems/executive-assistant/channels/auth-not-configured");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(
                detail: "Bearer authorization is required.",
                statusCode: StatusCodes.Status401Unauthorized,
                title: "Executive assistant webhook authorization required",
                type: "https://chummer.run/problems/executive-assistant/channels/auth-required");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (FixedTimeEquals(providedToken, expectedToken))
        {
            return null;
        }

        return Problem(
            detail: "Bearer authorization is required.",
            statusCode: StatusCodes.Status401Unauthorized,
            title: "Executive assistant webhook authorization required",
            type: "https://chummer.run/problems/executive-assistant/channels/auth-required");
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }
}
