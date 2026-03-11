using System.Text.Json;
using Chummer.Run.AI.Services.Gateway;
using Chummer.Run.Contracts.AI.Newspaper;

namespace Chummer.Run.AI.Services.Newspaper;

public interface INewspaperRenderService
{
    Task<NewspaperPdfRenderResult> RenderPdfAsync(
        RenderIssueHtmlRequest request,
        CancellationToken cancellationToken = default);
}

public sealed record NewspaperPdfRenderResult(
    bool Success,
    string? Error,
    byte[]? Content,
    string FileName,
    string ContentType,
    GatewayInvocation Invocation);

public sealed class NewspaperRenderService : INewspaperRenderService
{
    private readonly INewspaperHtmlRenderer _htmlRenderer;
    private readonly IAiGatewayService _gateway;

    public NewspaperRenderService(INewspaperHtmlRenderer htmlRenderer, IAiGatewayService gateway)
    {
        _htmlRenderer = htmlRenderer;
        _gateway = gateway;
    }

    public async Task<NewspaperPdfRenderResult> RenderPdfAsync(
        RenderIssueHtmlRequest request,
        CancellationToken cancellationToken = default)
    {
        var html = _htmlRenderer.Render(request.Issue).Html;
        var routeRequest = new ProviderRouteRequest(
            Purpose: "newspaper.render-pdf",
            Prompt: JsonSerializer.Serialize(new
            {
                Html = html,
                FileName = $"issue-{request.Issue.EditionNo}.pdf"
            }),
            StructuredOutput: true,
            MaxTokens: EstimateTokens(html),
            SessionId: request.Issue.IssueId,
            PreferredProvider: AiProvider.MarkupGo.ToString(),
            RequiredProvider: AiProvider.MarkupGo);
        var invocation = await _gateway.ExecuteRouteAsync(routeRequest, cancellationToken);
        if (!invocation.Success || string.IsNullOrWhiteSpace(invocation.Output))
        {
            return new NewspaperPdfRenderResult(
                Success: false,
                Error: invocation.Error ?? "Gateway did not return a render payload.",
                Content: null,
                FileName: "issue.pdf",
                ContentType: "application/pdf",
                Invocation: invocation);
        }

        try
        {
            var artifact = JsonSerializer.Deserialize<GatewayBinaryArtifact>(invocation.Output, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
            if (artifact is null || string.IsNullOrWhiteSpace(artifact.Base64Payload))
            {
                return new NewspaperPdfRenderResult(
                    Success: false,
                    Error: "Gateway returned an empty binary artifact.",
                    Content: null,
                    FileName: "issue.pdf",
                    ContentType: "application/pdf",
                    Invocation: invocation);
            }

            return new NewspaperPdfRenderResult(
                Success: true,
                Error: null,
                Content: Convert.FromBase64String(artifact.Base64Payload),
                FileName: string.IsNullOrWhiteSpace(artifact.FileName) ? "issue.pdf" : artifact.FileName,
                ContentType: string.IsNullOrWhiteSpace(artifact.ContentType) ? "application/pdf" : artifact.ContentType,
                Invocation: invocation);
        }
        catch (FormatException ex)
        {
            return new NewspaperPdfRenderResult(
                Success: false,
                Error: $"Gateway returned an invalid binary artifact: {ex.Message}",
                Content: null,
                FileName: "issue.pdf",
                ContentType: "application/pdf",
                Invocation: invocation);
        }
        catch (JsonException ex)
        {
            return new NewspaperPdfRenderResult(
                Success: false,
                Error: $"Gateway returned an invalid JSON artifact: {ex.Message}",
                Content: null,
                FileName: "issue.pdf",
                ContentType: "application/pdf",
                Invocation: invocation);
        }
    }

    private static int EstimateTokens(string html)
    {
        if (string.IsNullOrEmpty(html))
        {
            return 256;
        }

        return Math.Clamp((html.Length / 4) + 128, 256, 4_096);
    }
}
