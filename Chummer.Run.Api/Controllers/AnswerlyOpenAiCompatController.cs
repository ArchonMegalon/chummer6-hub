using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class AnswerlyOpenAiCompatController : ControllerBase
{
    private readonly AnswerlyOpenAiCompatService _compat;

    public AnswerlyOpenAiCompatController(AnswerlyOpenAiCompatService compat)
    {
        _compat = compat;
    }

    [HttpGet("/v1/models")]
    [HttpGet("/api/v1/models")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<OpenAiCompatModelListResponse>(StatusCodes.Status200OK)]
    public ActionResult<OpenAiCompatModelListResponse> ListModels()
    {
        ActionResult? denied = RequireCompatAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(_compat.ListModels());
    }

    [HttpPost("/v1/chat/completions")]
    [HttpPost("/api/v1/chat/completions")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<OpenAiCompatChatCompletionResponse>(StatusCodes.Status200OK)]
    public ActionResult<OpenAiCompatChatCompletionResponse> ChatCompletions([FromBody] OpenAiCompatChatCompletionRequest? request)
    {
        ActionResult? denied = RequireCompatAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "OpenAI-compatible request rejected",
                "chat completion request is required.",
                "https://chummer.run/problems/answerly-openai-compat/missing-request");
        }

        try
        {
            return Ok(_compat.Complete(request));
        }
        catch (InvalidDataException ex)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "OpenAI-compatible request rejected",
                ex.Message,
                "https://chummer.run/problems/answerly-openai-compat/rejected");
        }
    }

    private ActionResult? RequireCompatAuth()
    {
        if (!_compat.IsReady)
        {
            return BuildProblem(
                StatusCodes.Status503ServiceUnavailable,
                "OpenAI-compatible endpoint unavailable",
                "The Answerly OpenAI-compatible endpoint is not enabled and verified on this host.",
                "https://chummer.run/problems/answerly-openai-compat/unavailable");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return BuildProblem(
                StatusCodes.Status401Unauthorized,
                "OpenAI-compatible authorization required",
                "Bearer authorization is required.",
                "https://chummer.run/problems/answerly-openai-compat/auth-required");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (FixedTimeEquals(providedToken, _compat.ApiToken))
        {
            return null;
        }

        return BuildProblem(
            StatusCodes.Status401Unauthorized,
            "OpenAI-compatible authorization required",
            "Bearer authorization is required.",
            "https://chummer.run/problems/answerly-openai-compat/auth-required");
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private ObjectResult BuildProblem(int statusCode, string title, string detail, string type)
        => Problem(
            detail: detail,
            statusCode: statusCode,
            title: title,
            type: type,
            instance: $"{Request.Path}#{Request.HttpContext.TraceIdentifier}");
}
