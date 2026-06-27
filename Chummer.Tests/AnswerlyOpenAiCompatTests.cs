using System.Text.Json;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc.Routing;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using Xunit;

namespace Chummer.Tests;

public sealed class AnswerlyOpenAiCompatServiceTests
{
    [Fact]
    public void Complete_MapsLastUserMessageIntoOpenAiStyleResponse()
    {
        AnswerlyOpenAiCompatService service = CreateService();
        OpenAiCompatChatCompletionResponse response = service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: service.ModelId,
                Messages:
                [
                    Message("system", "You are a bot."),
                    Message("user", "How do I install the windows build?")
                ]));

        Assert.Equal("chat.completion", response.Object);
        Assert.Equal(service.ModelId, response.Model);
        Assert.Single(response.Choices);
        Assert.Equal("assistant", response.Choices[0].Message.Role);
        Assert.Contains("First-party answer", response.Choices[0].Message.Content);
        Assert.True(response.Usage.TotalTokens > 0);
    }

    [Fact]
    public void Complete_RejectsStreamingRequests()
    {
        AnswerlyOpenAiCompatService service = CreateService();

        var ex = Assert.Throws<InvalidDataException>(() => service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: service.ModelId,
                Messages: [Message("user", "Hello")],
                Stream: true)));

        Assert.Contains("stream=true", ex.Message);
    }

    [Fact]
    public void Complete_RejectsStreamingRequestsBeforeEaUpstreamAttempt()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ANSWERLY_ENABLED"] = "true",
                ["ANSWERLY_SUPPORT_ENABLED"] = "true",
                ["ANSWERLY_OPENAI_COMPAT_ENABLED"] = "true",
                ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = AnswerlyRuntimePolicy.VerifiedFullAdapter,
                ["ANSWERLY_OPENAI_COMPAT_API_TOKEN"] = "secret",
                ["ANSWERLY_OPENAI_COMPAT_EA_PRIMARY_ENABLED"] = "true",
                ["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL"] = "https://ea.example.test"
            })
            .Build();

        int requestCount = 0;
        var service = new AnswerlyOpenAiCompatService(
            new StubAssistantAdapter(),
            AnswerlyOpenAiCompatTestHelpers.CreateRuleGhost(configuration),
            new AnswerlyRuntimePolicy(configuration),
            configuration,
            new StaticHttpClientFactory(new HttpClient(new StubHandler(_ =>
            {
                requestCount++;
                return new HttpResponseMessage(HttpStatusCode.OK);
            }))));

        var ex = Assert.Throws<InvalidDataException>(() => service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: "openrouter/answerly-support-assistant",
                Messages: [Message("user", "Hello")],
                Stream: true)));

        Assert.Contains("stream=true", ex.Message);
        Assert.Equal(0, requestCount);
    }

    [Fact]
    public void Complete_RejectsTooManyMessages()
    {
        AnswerlyOpenAiCompatService service = CreateService();
        OpenAiCompatInputMessage[] messages = Enumerable
            .Range(0, AnswerlyOpenAiCompatService.MaxMessageCount + 1)
            .Select(index => Message("user", $"Question {index}"))
            .ToArray();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: service.ModelId,
                Messages: messages)));

        Assert.Contains("messages may contain at most", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Complete_RejectsOversizedUserMessage()
    {
        AnswerlyOpenAiCompatService service = CreateService();
        string content = new('q', AnswerlyOpenAiCompatService.MaxMessageTextLength + 1);

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: service.ModelId,
                Messages: [Message("user", content)])));

        Assert.Contains("message content exceeds the maximum length", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ExtractsTextFromArrayMessageContent()
    {
        AnswerlyOpenAiCompatService service = CreateService();
        JsonElement content = JsonSerializer.Deserialize<JsonElement>(
            """
            [
              {"type":"text","text":"How do I claim the app?"},
              {"type":"image_url","image_url":{"url":"https://example.invalid/image.png"}}
            ]
            """);

        OpenAiCompatChatCompletionResponse response = service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: service.ModelId,
                Messages: [new OpenAiCompatInputMessage("user", content)]));

        Assert.Contains("First-party answer", response.Choices[0].Message.Content);
    }

    [Fact]
    public void Complete_AcceptsOpenRouterStyleModelAlias()
    {
        AnswerlyOpenAiCompatService service = CreateService();

        OpenAiCompatChatCompletionResponse response = service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: "openrouter/answerly-support-assistant",
                Messages: [Message("user", "Can you help me install the app?")]));

        Assert.Equal("openrouter/answerly-support-assistant", response.Model);
    }

    [Fact]
    public void ListModels_AdvertisesAliasModels()
    {
        AnswerlyOpenAiCompatService service = CreateService();

        OpenAiCompatModelListResponse response = service.ListModels();

        Assert.Contains(response.Data, model => model.Id == "answerly-support-assistant");
        Assert.Contains(response.Data, model => model.Id == "openrouter/answerly-support-assistant");
        Assert.Contains(response.Data, model => model.Id == "chummer/answerly-support-assistant");
        Assert.Contains(response.Data, model => model.Id == "sr-rulebot");
        Assert.Contains(response.Data, model => model.Id == "openrouter/sr-rulebot");
    }

    [Fact]
    public void Complete_ServesRuleGhostModelFromLocalFallback()
    {
        AnswerlyOpenAiCompatService service = CreateService();

        OpenAiCompatChatCompletionResponse response = service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: "sr-rulebot",
                Messages: [Message("user", "In SR6, how should I think about Edge during a firefight?")]));

        Assert.Equal("sr-rulebot", response.Model);
        Assert.DoesNotContain("sourcebook", response.Choices[0].Message.Content, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("page", response.Choices[0].Message.Content, StringComparison.OrdinalIgnoreCase);
    }

    private static AnswerlyOpenAiCompatService CreateService()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ANSWERLY_ENABLED"] = "true",
                ["ANSWERLY_SUPPORT_ENABLED"] = "true",
                ["ANSWERLY_OPENAI_COMPAT_ENABLED"] = "true",
                ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = AnswerlyRuntimePolicy.VerifiedFullAdapter,
                ["ANSWERLY_OPENAI_COMPAT_API_TOKEN"] = "token-123",
                ["ANSWERLY_OPENAI_COMPAT_MODEL_ID"] = "answerly-support-assistant"
            })
            .Build();
        return new AnswerlyOpenAiCompatService(
            new StubAssistantAdapter(),
            AnswerlyOpenAiCompatTestHelpers.CreateRuleGhost(configuration),
            new AnswerlyRuntimePolicy(configuration),
            configuration,
            new StaticHttpClientFactory(new HttpClient(new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.BadGateway)))));
    }

    private static OpenAiCompatInputMessage Message(string role, string content)
        => new(role, JsonSerializer.Deserialize<JsonElement>(JsonSerializer.Serialize(content)));

    private sealed class StubAssistantAdapter : IChummerAssistantAdapter
    {
        public SupportAssistantResponse AskSupport(string? reporterUserId, string? reporterSubjectId, SupportAssistantRequest request)
            => new(
                $"First-party answer for: {request.Query}",
                SupportAssistantConfidenceLevels.CanonHelp,
                false,
                [new SupportAssistantCitation("canon_doc", "Install help", "Use the installer.")],
                [new SupportAssistantAction("open_support", "Open support", "/contact", "Escalate if needed.")]);

        public RuleSafeOutputGateResult HumanizeSafeRulesAnswer(RuleSafeAnswerPacket packet)
            => new(true, packet.SafeSummary, Array.Empty<string>());
    }
}

public sealed class AnswerlyOpenAiCompatControllerTests
{
    [Fact]
    public void ListModels_RequiresBearerAuth()
    {
        AnswerlyOpenAiCompatController controller = CreateController(apiToken: "secret", verificationState: AnswerlyRuntimePolicy.VerifiedFullAdapter);

        ActionResult<OpenAiCompatModelListResponse> result = controller.ListModels();

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
    }

    [Fact]
    public void ListModels_FailClosesWhenPolicyIsNotReady()
    {
        AnswerlyOpenAiCompatController controller = CreateController(apiToken: "secret", verificationState: AnswerlyRuntimePolicy.VerifiedWidgetOnly);
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer secret";

        ActionResult<OpenAiCompatModelListResponse> result = controller.ListModels();

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void ChatCompletions_ReturnsOpenAiStylePayloadWhenAuthorized()
    {
        AnswerlyOpenAiCompatController controller = CreateController(apiToken: "secret", verificationState: AnswerlyRuntimePolicy.VerifiedFullAdapter);
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer secret";

        ActionResult<OpenAiCompatChatCompletionResponse> result = controller.ChatCompletions(
            new OpenAiCompatChatCompletionRequest(
                Model: "answerly-support-assistant",
                Messages:
                [
                    new OpenAiCompatInputMessage(
                        "user",
                        JsonSerializer.Deserialize<JsonElement>(JsonSerializer.Serialize("How do I install this?")))
                ]));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        OpenAiCompatChatCompletionResponse payload = Assert.IsType<OpenAiCompatChatCompletionResponse>(ok.Value);
        Assert.Equal("chat.completion", payload.Object);
        Assert.Equal("assistant", payload.Choices[0].Message.Role);
    }

    [Fact]
    public void Complete_PrefersEaUpstreamWhenConfigured()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ANSWERLY_ENABLED"] = "true",
                ["ANSWERLY_SUPPORT_ENABLED"] = "true",
                ["ANSWERLY_OPENAI_COMPAT_ENABLED"] = "true",
                ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = AnswerlyRuntimePolicy.VerifiedFullAdapter,
                ["ANSWERLY_OPENAI_COMPAT_API_TOKEN"] = "secret",
                ["ANSWERLY_OPENAI_COMPAT_EA_PRIMARY_ENABLED"] = "true",
                ["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL"] = "https://ea.example.test",
                ["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_ID"] = "client-id",
                ["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_SECRET"] = "client-secret"
            })
            .Build();

        List<HttpRequestMessage> requests = new();
        var service = new AnswerlyOpenAiCompatService(
            new StubAssistantAdapter(),
            AnswerlyOpenAiCompatTestHelpers.CreateRuleGhost(configuration),
            new AnswerlyRuntimePolicy(configuration),
            configuration,
            new StaticHttpClientFactory(new HttpClient(new StubHandler(request =>
            {
                requests.Add(CloneRequest(request));
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        """
                        {
                          "id":"chatcmpl_upstream",
                          "object":"chat.completion",
                          "created":123,
                          "model":"openrouter/answerly-support-assistant",
                          "choices":[{"index":0,"message":{"role":"assistant","content":"EA upstream answer"},"finish_reason":"stop"}],
                          "usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":8}
                        }
                        """,
                        Encoding.UTF8,
                        "application/json")
                };
            }))));

        OpenAiCompatChatCompletionResponse response = service.Complete(
            new OpenAiCompatChatCompletionRequest(
                Model: "openrouter/answerly-support-assistant",
                Messages:
                [
                    new OpenAiCompatInputMessage("user", JsonSerializer.Deserialize<JsonElement>(JsonSerializer.Serialize("Hello from Answerly")))
                ]));

        Assert.Equal("EA upstream answer", response.Choices[0].Message.Content);
        Assert.Single(requests);
        Assert.Equal("https://ea.example.test/api/v1/chat/completions", requests[0].RequestUri!.ToString());
        Assert.Equal("client-id", requests[0].Headers.GetValues("CF-Access-Client-Id").Single());
        Assert.Equal("client-secret", requests[0].Headers.GetValues("CF-Access-Client-Secret").Single());
    }

    [Fact]
    public void Controller_ExposesOpenRouterStyleAliases()
    {
        string[] modelRoutes = typeof(AnswerlyOpenAiCompatController)
            .GetMethod(nameof(AnswerlyOpenAiCompatController.ListModels))!
            .GetCustomAttributes(typeof(HttpMethodAttribute), inherit: false)
            .Cast<HttpMethodAttribute>()
            .SelectMany(attribute => attribute.Template is null ? Array.Empty<string>() : [attribute.Template])
            .ToArray();

        string[] chatRoutes = typeof(AnswerlyOpenAiCompatController)
            .GetMethod(nameof(AnswerlyOpenAiCompatController.ChatCompletions))!
            .GetCustomAttributes(typeof(HttpMethodAttribute), inherit: false)
            .Cast<HttpMethodAttribute>()
            .SelectMany(attribute => attribute.Template is null ? Array.Empty<string>() : [attribute.Template])
            .ToArray();

        Assert.Contains("/v1/models", modelRoutes);
        Assert.Contains("/api/v1/models", modelRoutes);
        Assert.Contains("/v1/chat/completions", chatRoutes);
        Assert.Contains("/api/v1/chat/completions", chatRoutes);
    }

    [Fact]
    public void ChatCompletions_CapsRequestBodySize()
    {
        MethodInfo method = typeof(AnswerlyOpenAiCompatController)
            .GetMethod(nameof(AnswerlyOpenAiCompatController.ChatCompletions))
            ?? throw new InvalidOperationException("Missing ChatCompletions method.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException("ChatCompletions is missing RequestSizeLimitAttribute.");

        Assert.Equal(AnswerlyOpenAiCompatService.MaxRequestBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    private static AnswerlyOpenAiCompatController CreateController(string apiToken, string verificationState)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ANSWERLY_ENABLED"] = "true",
                ["ANSWERLY_SUPPORT_ENABLED"] = "true",
                ["ANSWERLY_OPENAI_COMPAT_ENABLED"] = "true",
                ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = verificationState,
                ["ANSWERLY_OPENAI_COMPAT_API_TOKEN"] = apiToken,
                ["ANSWERLY_OPENAI_COMPAT_MODEL_ID"] = "answerly-support-assistant"
            })
            .Build();
        var controller = new AnswerlyOpenAiCompatController(
            new AnswerlyOpenAiCompatService(
                new StubAssistantAdapter(),
                AnswerlyOpenAiCompatTestHelpers.CreateRuleGhost(configuration),
                new AnswerlyRuntimePolicy(configuration),
                configuration,
                new StaticHttpClientFactory(new HttpClient(new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.BadGateway))))));
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        return controller;
    }

    private sealed class StubAssistantAdapter : IChummerAssistantAdapter
    {
        public SupportAssistantResponse AskSupport(string? reporterUserId, string? reporterSubjectId, SupportAssistantRequest request)
            => new(
                $"Support answer: {request.Query}",
                SupportAssistantConfidenceLevels.CanonHelp,
                false,
                Array.Empty<SupportAssistantCitation>(),
                Array.Empty<SupportAssistantAction>());

        public RuleSafeOutputGateResult HumanizeSafeRulesAnswer(RuleSafeAnswerPacket packet)
            => new(true, packet.SafeSummary, Array.Empty<string>());
    }

    private static HttpRequestMessage CloneRequest(HttpRequestMessage request)
    {
        var clone = new HttpRequestMessage(request.Method, request.RequestUri);
        foreach (var header in request.Headers)
        {
            clone.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }

        return clone;
    }

}

internal static class AnswerlyOpenAiCompatTestHelpers
{
    public static RuleGhostService CreateRuleGhost(IConfiguration configuration)
        => new(
            new AnswerlyHumanizerAdapter(new AnswerlyRuntimePolicy(configuration), new RuleSafeOutputGate()));
}

internal sealed class StaticHttpClientFactory : IHttpClientFactory
{
    private readonly HttpClient _client;

    public StaticHttpClientFactory(HttpClient client)
    {
        _client = client;
    }

    public HttpClient CreateClient(string name) => _client;
}

internal sealed class StubHandler : HttpMessageHandler
{
    private readonly Func<HttpRequestMessage, HttpResponseMessage> _handler;

    public StubHandler(Func<HttpRequestMessage, HttpResponseMessage> handler)
    {
        _handler = handler;
    }

    protected override HttpResponseMessage Send(HttpRequestMessage request, CancellationToken cancellationToken)
        => _handler(request);

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        => Task.FromResult(_handler(request));
}
