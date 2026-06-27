using System.Net;
using System.Reflection;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class RuleGhostControllerTests
{
    [Fact]
    public void AskCapsRequestBodySize()
    {
        MethodInfo method = typeof(RuleGhostController).GetMethod(nameof(RuleGhostController.Ask))
            ?? throw new InvalidOperationException("Missing Ask method.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException("Ask is missing RequestSizeLimitAttribute.");

        Assert.Equal(RuleGhostService.MaxRequestBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    [Fact]
    public async Task AskReturnsBadRequestForOversizedQuery()
    {
        using var fixture = new Fixture();
        RuleGhostAskRequest request = new(new string('q', RuleGhostService.MaxQueryLength + 1), PreferredRuleset: "sr6");

        ActionResult<RuleGhostResponse> result = await fixture.Controller.Ask(request, CancellationToken.None);

        BadRequestObjectResult badRequest = Assert.IsType<BadRequestObjectResult>(result.Result);
        Assert.Contains("query exceeds the maximum length", badRequest.Value?.ToString(), StringComparison.Ordinal);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-rule-ghost-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ANSWERLY_ENABLED"] = "true",
                    ["ANSWERLY_HUMANIZER_ENABLED"] = "true",
                    ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = AnswerlyRuntimePolicy.VerifiedFullAdapter,
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                    ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = "local-rule-ghost-token",
                    ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.rule-ghost",
                    ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Rule Ghost Tester",
                    ["CHUMMER_LOCAL_E2E_EMAIL"] = "rule-ghost@example.invalid"
                })
                .Build();

            Controller = new RuleGhostController(
                new HubIdentityClient(new HttpClient(), configuration, NullLogger<HubIdentityClient>.Instance),
                new AccountService(new CommunityStore(configuration, NullLogger<CommunityStore>.Instance)),
                new RuleGhostService(
                    new AnswerlyHumanizerAdapter(
                        new AnswerlyRuntimePolicy(configuration),
                        new RuleSafeOutputGate())))
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = CreateHttpContext()
                }
            };
        }

        public RuleGhostController Controller { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private static DefaultHttpContext CreateHttpContext()
        {
            DefaultHttpContext context = new();
            context.Request.Host = new HostString("localhost");
            context.Connection.RemoteIpAddress = IPAddress.Loopback;
            context.Request.Headers.Authorization = "Bearer local-rule-ghost-token";
            return context;
        }
    }
}
