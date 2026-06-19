using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Heyy;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[IgnoreAntiforgeryToken]
public sealed class HeyyScamChatController : ControllerBase
{
    private readonly HeyyScamChatService _scamChat;
    private readonly TeableHeyyScamChatService _teable;
    private readonly IConfiguration _configuration;

    public HeyyScamChatController(
        HeyyScamChatService scamChat,
        TeableHeyyScamChatService teable,
        IConfiguration configuration)
    {
        _scamChat = scamChat;
        _teable = teable;
        _configuration = configuration;
    }

    [HttpPost("/api/internal/heyy/scam-chat/messages")]
    [ProducesResponseType<HeyyScamChatDraftResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<HeyyScamChatDraftResponse>> IngestMessage([FromBody] HeyyScamChatIngestRequest? request, CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BadRequest("Heyy scam-chat message payload is required.");
        }

        try
        {
            return Ok(await _scamChat.IngestIncomingAsync(request, cancellationToken));
        }
        catch (ArgumentException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, title: "Heyy scam-chat request rejected", detail: ex.Message);
        }
    }

    [HttpGet("/api/internal/heyy/scam-chat/conversations")]
    [ProducesResponseType<IReadOnlyList<HeyyScamChatConversationResponse>>(StatusCodes.Status200OK)]
    public ActionResult<IReadOnlyList<HeyyScamChatConversationResponse>> ListConversations([FromQuery] int take = 24)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(_scamChat.ListConversations(take));
    }

    [HttpGet("/api/internal/heyy/scam-chat/conversations/{conversationId}")]
    [ProducesResponseType<HeyyScamChatConversationResponse>(StatusCodes.Status200OK)]
    public ActionResult<HeyyScamChatConversationResponse> GetConversation([FromRoute] string conversationId)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        HeyyScamChatConversationResponse? conversation = _scamChat.GetConversation(conversationId);
        return conversation is null ? NotFound() : Ok(conversation);
    }

    [HttpPost("/api/internal/heyy/scam-chat/conversations/{conversationId}/approve")]
    [ProducesResponseType<HeyyScamChatApprovalResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<HeyyScamChatApprovalResponse>> ApproveDraft(
        [FromRoute] string conversationId,
        [FromBody] HeyyScamChatApproveDraftRequest? request,
        CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BadRequest("Heyy scam-chat approval payload is required.");
        }

        try
        {
            return Ok(await _scamChat.ApproveDraftAsync(conversationId, request, cancellationToken));
        }
        catch (ArgumentException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, title: "Heyy scam-chat approval rejected", detail: ex.Message);
        }
    }

    [HttpPost("/api/internal/heyy/scam-chat/digest")]
    [ProducesResponseType<HeyyScamChatDigestResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<HeyyScamChatDigestResponse>> DispatchDigest([FromBody] HeyyScamChatDigestRequest? request, CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        DateOnly date = request?.Date ?? DateOnly.FromDateTime(DateTime.UtcNow.Date);
        bool dryRun = request?.DryRun ?? false;
        return Ok(await _scamChat.DispatchDailyDigestAsync(date, dryRun, cancellationToken));
    }

    [HttpGet("/api/internal/heyy/scam-chat/teable")]
    [ProducesResponseType<TeableHeyyScamChatDashboard>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableHeyyScamChatDashboard>> GetTeableDashboard([FromQuery] bool sync, CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (sync)
        {
            await _teable.SyncAllAsync(cancellationToken);
        }

        return Ok(_teable.GetDashboard());
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = Normalize(_configuration["CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN"])
            ?? Normalize(_configuration["FLEET_INTERNAL_API_TOKEN"])
            ?? string.Empty;
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(
                detail: "Heyy scam-chat internal authorization is not configured.",
                statusCode: StatusCodes.Status503ServiceUnavailable,
                title: "Heyy scam-chat authorization is not configured",
                type: "https://chummer.run/problems/heyy-scam-chat/auth-not-configured");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(
                detail: "Bearer authorization is required.",
                statusCode: StatusCodes.Status401Unauthorized,
                title: "Heyy scam-chat authorization required",
                type: "https://chummer.run/problems/heyy-scam-chat/auth-required");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (FixedTimeEquals(providedToken, expectedToken))
        {
            return null;
        }

        return Problem(
            detail: "Bearer authorization is required.",
            statusCode: StatusCodes.Status401Unauthorized,
            title: "Heyy scam-chat authorization required",
            type: "https://chummer.run/problems/heyy-scam-chat/auth-required");
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
