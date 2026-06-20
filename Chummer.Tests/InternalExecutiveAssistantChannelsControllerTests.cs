using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InternalExecutiveAssistantChannelsControllerTests
{
    [Fact]
    public void IngestMessage_returnsServiceUnavailable_whenTokenNotConfigured()
    {
        Fixture fixture = new();

        ActionResult<ExecutiveAssistantChannelMessageDto> result = fixture.Controller.IngestMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: null,
                RecipientHandle: null,
                CounterpartyHandle: "+436647916419",
                MessageText: "hello",
                MessageId: null));

        var problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void IngestMessage_rejectsMissingOrInvalidAuthorizationToken()
    {
        Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_WEBHOOK_TOKEN"] = "internal-token"
        });

        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "";
        ActionResult<ExecutiveAssistantChannelMessageDto> missingHeader = fixture.Controller.IngestMessage(
            "whatsapp_official_business",
            BuildIncomingRequest(fixture.SubjectId, "+436647916419", "hello"));
        var missingHeaderResult = Assert.IsType<ObjectResult>(missingHeader.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, missingHeaderResult.StatusCode);

        fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_WEBHOOK_TOKEN"] = "internal-token"
        });
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer wrong";
        ActionResult<ExecutiveAssistantChannelMessageDto> invalidToken = fixture.Controller.IngestMessage(
            "whatsapp_official_business",
            BuildIncomingRequest(fixture.SubjectId, "+436647916419", "hello"));
        var invalidTokenResult = Assert.IsType<ObjectResult>(invalidToken.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, invalidTokenResult.StatusCode);
    }

    [Fact]
    public void IngestMessage_storesMessage_whenAuthorizedAndLinked()
    {
        Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_WEBHOOK_TOKEN"] = "internal-token"
        });

        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-token";
        ActionResult<ExecutiveAssistantChannelMessageDto> result = fixture.Controller.IngestMessage(
            "whatsapp_official_business",
            BuildIncomingRequest(fixture.SubjectId, "+436647916419", "hello"));

        var ok = Assert.IsType<OkObjectResult>(result.Result);
        var message = Assert.IsType<ExecutiveAssistantChannelMessageDto>(ok.Value);
        Assert.Equal("incoming", message.Direction);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelConversations);
        Assert.Equal("incoming", fixture.Store.ExecutiveAssistantChannelMessages[0].Direction);
    }

    [Fact]
    public void IngestMessage_rejectsUnlinkedIncomingRouteAsConflict()
    {
        Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_WEBHOOK_TOKEN"] = "internal-token"
        });

        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-token";
        ActionResult<ExecutiveAssistantChannelMessageDto> result = fixture.Controller.IngestMessage(
            "telegram_official_bot",
            BuildIncomingRequest(fixture.SubjectId, "+436647916419", "hello"));

        var problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status409Conflict, problem.StatusCode);
    }

    private static ExecutiveAssistantChannelIncomingMessageRequest BuildIncomingRequest(
        string subjectId,
        string counterpartyHandle,
        string messageText)
    {
        return new ExecutiveAssistantChannelIncomingMessageRequest(
            SubjectId: subjectId,
            RecipientHandle: null,
            CounterpartyHandle: counterpartyHandle,
            MessageText: messageText,
            MessageId: null);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        public Fixture(IReadOnlyDictionary<string, string?>? overrides = null)
        {
            _root = Path.Combine(Path.GetTempPath(), "executive-assistant-channel-ingest-controller-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            var values = new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json")
            };

            if (overrides is not null)
            {
                foreach ((string key, string? value) in overrides)
                {
                    values[key] = value;
                }
            }

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(values)
                .Build();
            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Store);
            Links = new IdentityLinkService(Store, Accounts);
            SubjectId = "subject.ea.channel.ingest";
            Accounts.EnsureUserWithStatus(SubjectId, "EA Reader", "reader@example.com");
            Links.LinkChannel(new LinkChannelRequest(SubjectId, "whatsapp_official_business", "+43 664 791 6419", true));
            Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(SubjectId, null));
            Service = new ExecutiveAssistantChannelMessagingService(
                new System.Net.Http.HttpClient(),
                Store,
                Accounts,
                Configuration,
                NullLogger<ExecutiveAssistantChannelMessagingService>.Instance);
            Controller = new InternalExecutiveAssistantChannelsController(Service, Configuration)
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = new DefaultHttpContext()
                }
            };
            Controller.ControllerContext.HttpContext.Request.Path = "/api/internal/executive-assistant/channels/whatsapp_official_business/messages";
        }

        public string SubjectId { get; }
        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public AccountService Accounts { get; }
        public IdentityLinkService Links { get; }
        public ExecutiveAssistantChannelMessagingService Service { get; }
        public InternalExecutiveAssistantChannelsController Controller { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
