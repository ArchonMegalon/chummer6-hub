using System.Net;
using System.Reflection;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PromptFoundryControllerTests
{
    [Theory]
    [InlineData(nameof(PromptFoundryController.CreateDraft), PromptFoundryService.MaxDraftRequestBodyBytes)]
    [InlineData(nameof(PromptFoundryController.EditDraft), PromptFoundryService.MaxDraftRequestBodyBytes)]
    [InlineData(nameof(PromptFoundryController.ApproveDraft), PromptFoundryService.MaxApprovalRequestBodyBytes)]
    public void DraftRoutesCapRequestBodySize(string methodName, long expectedMaxRequestBodySize)
    {
        MethodInfo method = typeof(PromptFoundryController).GetMethod(methodName)
            ?? throw new InvalidOperationException($"PromptFoundryController.{methodName} was not found.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException($"{methodName} is missing RequestSizeLimitAttribute.");

        Assert.Equal(expectedMaxRequestBodySize, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    [Fact]
    public async Task CreateDraftReturnsBadRequestForOversizedSummary()
    {
        using var fixture = new Fixture();

        IActionResult result = await fixture.Controller.CreateDraft(
            new PromptFoundryCreateDraftRequest(
                TemplateId: "magicfit_video_bridge_v1",
                CampaignId: null,
                GroupId: null,
                VideoType: "matrix_alert",
                Audience: "campaign_players",
                Tone: "glitchy tactical",
                PublicSafeSummary: new string('s', PromptFoundryService.MaxPublicSafeSummaryLength + 1),
                LocationAlias: "Kestrel",
                ProviderMode: PromptFoundryProviderModes.PromptArchitectsTemplateSeed),
            CancellationToken.None);

        BadRequestObjectResult badRequest = Assert.IsType<BadRequestObjectResult>(result);
        Assert.Contains("PublicSafeSummary exceeds the maximum length", badRequest.Value?.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task EditDraftReturnsBadRequestForOversizedEnhancedPrompt()
    {
        using var fixture = new Fixture();
        PromptFoundryDraftProjection draft = fixture.CreateOperatorDraft();

        IActionResult result = await fixture.Controller.EditDraft(
            draft.Id,
            new PromptFoundryEditDraftRequest(
                new string('e', PromptFoundryService.MaxEnhancedPromptLength + 1),
                draft.NegativePrompt),
            CancellationToken.None);

        BadRequestObjectResult badRequest = Assert.IsType<BadRequestObjectResult>(result);
        Assert.Contains("EnhancedPrompt exceeds the maximum length", badRequest.Value?.ToString(), StringComparison.Ordinal);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-prompt-foundry-controller-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_PROMPT_FOUNDRY_STORE_PATH"] = Path.Combine(_root, "prompt-foundry.json"),
                    ["PROMPT_ARCHITECTS_TIER4_VERIFIED"] = "true",
                    ["PROMPT_ARCHITECTS_EXPORT_AVAILABLE"] = "true",
                    ["PROMPT_ARCHITECTS_API_AVAILABLE"] = "false",
                    ["PROMPT_ARCHITECTS_MCP_VERIFIED"] = "false",
                    ["PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED"] = "false",
                    ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = "local-prompt-foundry-token",
                    ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.prompt-foundry",
                    ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Prompt Foundry Tester",
                    ["CHUMMER_LOCAL_E2E_EMAIL"] = "prompt-foundry@example.invalid"
                })
                .Build();

            Community = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Community);
            Foundry = new PromptFoundryService(new PromptFoundryStore(Configuration), Community, Configuration);
            Controller = new PromptFoundryController(
                new HubIdentityClient(new HttpClient(), Configuration, NullLogger<HubIdentityClient>.Instance),
                Accounts,
                Foundry)
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = CreateHttpContext()
                }
            };

            SeedCommunity();
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Community { get; }
        public AccountService Accounts { get; }
        public PromptFoundryService Foundry { get; }
        public PromptFoundryController Controller { get; }

        public PromptFoundryDraftProjection CreateOperatorDraft()
        {
            HubUserDto user = Accounts.EnsureUser("subject.prompt-foundry", "Prompt Foundry Tester", "prompt-foundry@example.invalid");
            return Foundry.CreateDraft(user.UserId, new PromptFoundryCreateDraftRequest(
                TemplateId: "gm_session_video_aftermath_v1",
                CampaignId: null,
                GroupId: null,
                VideoType: "newsreel",
                Audience: "campaign_players",
                Tone: "noir",
                PublicSafeSummary: "A public-safe summary.",
                LocationAlias: "Kestrel",
                ProviderMode: PromptFoundryProviderModes.PromptArchitectsTemplateSeed));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private void SeedCommunity()
        {
            HubUserDto user = Accounts.EnsureUser("subject.prompt-foundry", "Prompt Foundry Tester", "prompt-foundry@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;
            lock (Community.Gate)
            {
                Community.GroupsById["group-1"] = new GroupDto(
                    "group-1",
                    "campaign",
                    "Campaign Group",
                    "private",
                    user.UserId,
                    [],
                    [new GroupMembershipDto("membership-a", "group-1", user.UserId, "gm", now)],
                    now,
                    now);
                Community.CampaignsById["campaign-1"] = new BoostCampaignDto("campaign-1", "group-1", "project-1", "Campaign One", "active", now);
            }
        }

        private static DefaultHttpContext CreateHttpContext()
        {
            DefaultHttpContext context = new();
            context.Request.Host = new HostString("localhost");
            context.Connection.RemoteIpAddress = IPAddress.Loopback;
            context.Request.Headers.Authorization = "Bearer local-prompt-foundry-token";
            return context;
        }
    }
}
