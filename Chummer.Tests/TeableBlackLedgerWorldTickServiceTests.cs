using System.Net;
using System.Text;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class TeableBlackLedgerWorldTickServiceTests
{
    [Fact]
    public async Task EndToEndWorkflow_ResolutionApprovalProjectsWorldTickIntoBlackLedgerBoard()
    {
        using Fixture fixture = new();

        var user = fixture.Accounts.EnsureUser("subject.demo", "Demo Operator", "demo@example.invalid");
        var workspace = fixture.CampaignSpine.GetStarterWorkspace(user)
            ?? throw new InvalidOperationException("Expected a starter workspace.");
        var run = workspace.Runs.First();

        fixture.CampaignSpine.UpsertRunboardContinuity(user, workspace, new RunboardContinuityUpdateRequest(
            RunId: run.RunId,
            ActiveSceneId: run.ActiveSceneId,
            TurnLedgerSummary: "Minor-action handoff stays pinned before the next opposition pass.",
            TurnLedgerEvidenceLines: ["Player lane confirmed the last spend on the governed turn ledger."],
            RunboardStateSummary: "Two blockers and the same extraction objective stay pinned on the GM runboard.",
            ObjectiveLines: ["Extract the courier without spiking public awareness."],
            Blockers: ["Resolve overwatch pressure before the courier leaves the van."],
            ResolutionReportStatus: "draft",
            ResolutionReportSummary: "ResolutionReport draft keeps the courier handoff and matrix fallout continuity on one hub lane.",
            ResolutionNotes: ["Spoiler-safe notes stay bounded to the same closeout draft."],
            NextSafeAction: "Open ResolutionReport and keep the same return lane on /account/work#runboard.",
            Note: "BLACK LEDGER Teable projection test."));

        ResolutionReportApprovalProjection approval = fixture.CampaignSpine.ApproveResolutionReport(user, workspace, new ResolutionReportApprovalRequest(
            RunId: run.RunId,
            Summary: "ResolutionReport approval closes the courier extraction on the governed hub lane.",
            WorldTickSummary: "Dockside courier fallout becomes the first BLACK LEDGER WorldTick for Tacoma.",
            ConsequenceSummary: "Heat escalates across Tacoma after the courier extraction closes out.",
            NewsTitle: "Tacoma grid rumor points to a vanished courier",
            NewsSummary: "Player-safe reports say a courier vanished after a dockside outage.",
            NewsSource: "Tacoma Shadowfeed",
            NewsUrl: "https://example.invalid/news/tacoma-courier-rumor",
            NextSafeAction: "Review the first WorldTick and player-safe news item on /account/work#campaign-memory before you reopen the runboard.",
            Note: "BLACK LEDGER Teable projection test."));

        Assert.False(string.IsNullOrWhiteSpace(approval.WorldTickId));

        TeableBlackLedgerWorldTickSyncResult syncResult = await fixture.TeableService.SyncAllAsync();
        Assert.Equal("passed", syncResult.State);
        Assert.Equal(1, syncResult.SyncedCount);
        Assert.Equal("tbl_blackledger", syncResult.TableId);

        InternalTeableBlackLedgerController controller = new(fixture.TeableService, fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-demo-token";

        ActionResult<TeableBlackLedgerWorldTickDashboard> response = await controller.GetDashboard(sync: false, CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        TeableBlackLedgerWorldTickDashboard dashboard = Assert.IsType<TeableBlackLedgerWorldTickDashboard>(ok.Value);
        TeableBlackLedgerWorldTickRow row = Assert.Single(dashboard.Rows);

        Assert.Equal($"blackledger:{approval.WorldTickId}", row.ProjectionId);
        Assert.Equal("black_ledger_world_tick_review", row.ProjectionKind);
        Assert.Equal("operator_only", row.VisibilityClass);
        Assert.Equal("teable_black_ledger_world_ticks", row.KillSwitchKey);
        Assert.Contains("Proposed Status", row.EditableFields);
        Assert.Contains("Canonical Status", row.ForbiddenFields);
        Assert.Equal(approval.WorldTickId, row.WorldTickId);
        Assert.Equal(workspace.WorkspaceId, row.WorkspaceId);
        Assert.Equal(workspace.CampaignId, row.CampaignId);
        Assert.Contains("BLACK LEDGER WorldTick", row.Summary, StringComparison.Ordinal);
        Assert.True(row.GmApproved);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/base/base-demo/table/");
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_blackledger/record");
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "teable-black-ledger-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Handler = new FakeTeableHandler();
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30",
                    ["FLEET_INTERNAL_API_TOKEN"] = "internal-demo-token",
                    ["CHUMMER_TEABLE_BLACK_LEDGER_ENABLED"] = "true",
                    ["CHUMMER_TEABLE_BLACK_LEDGER_API_KEY"] = "teable-demo-token",
                    ["CHUMMER_TEABLE_BLACK_LEDGER_API_BASE_URL"] = "https://app.teable.ai/api",
                    ["CHUMMER_TEABLE_BLACK_LEDGER_BASE_ID"] = "base-demo",
                    ["CHUMMER_TEABLE_BLACK_LEDGER_TABLE_NAME"] = "Black Ledger World Ticks"
                })
                .Build();

            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Store);
            SupportStore = new SupportStore(Configuration, NullLogger<SupportStore>.Instance);
            CampaignSpine = new CampaignSpineService(
                Store,
                new WorkspaceLifecyclePolicyService(Configuration),
                new CampaignArtifactRegistryBridge(Store),
                SupportStore);
            TeableService = new TeableBlackLedgerWorldTickService(
                Store,
                Configuration,
                new StaticHttpClientFactory(new HttpClient(Handler)),
                NullLogger<TeableBlackLedgerWorldTickService>.Instance);
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public AccountService Accounts { get; }
        public SupportStore SupportStore { get; }
        public CampaignSpineService CampaignSpine { get; }
        public TeableBlackLedgerWorldTickService TeableService { get; }
        public FakeTeableHandler Handler { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class StaticHttpClientFactory : IHttpClientFactory
    {
        private readonly HttpClient _client;

        public StaticHttpClientFactory(HttpClient client)
        {
            _client = client;
        }

        public HttpClient CreateClient(string name) => _client;
    }

    private sealed class FakeTeableHandler : HttpMessageHandler
    {
        public List<FakeRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string path = request.RequestUri?.AbsolutePath ?? string.Empty;
            string query = request.RequestUri?.Query ?? string.Empty;
            string body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add(new FakeRequest(request.Method, path, query, body));

            if (request.Method == HttpMethod.Get && path == "/api/base/base-demo/table")
            {
                return JsonResponse("[]");
            }

            if (request.Method == HttpMethod.Post && path == "/api/base/base-demo/table/")
            {
                return JsonResponse("""{"id":"tbl_blackledger"}""");
            }

            if (request.Method == HttpMethod.Get && path == "/api/table/tbl_blackledger/field")
            {
                return JsonResponse("[]");
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_blackledger/field")
            {
                return JsonResponse("""{"id":"fld"}""");
            }

            if (request.Method == HttpMethod.Get && path == "/api/table/tbl_blackledger/record")
            {
                return JsonResponse("""{"records":[]}""");
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_blackledger/record")
            {
                return JsonResponse("""{"records":[{"id":"rec_1"}]}""");
            }

            return new HttpResponseMessage(HttpStatusCode.NotFound)
            {
                Content = new StringContent($"Unhandled {request.Method} {path}{query}", Encoding.UTF8, "text/plain")
            };
        }

        private static HttpResponseMessage JsonResponse(string json)
            => new(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            };
    }

    private sealed record FakeRequest(HttpMethod Method, string Path, string Query, string Body);
}
