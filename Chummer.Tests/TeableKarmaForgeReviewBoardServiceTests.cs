using System.Net;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.KarmaForge;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class TeableKarmaForgeReviewBoardServiceTests
{
    [Fact]
    public async Task SyncAllCreatesTableAndProjectsReviewBoardRows()
    {
        using Fixture fixture = new();
        fixture.Service.Submit(new KarmaForgeSubmissionRequest
        {
            TrackKey = "gm_house_rule_track",
            RespondentRole = "GM",
            Edition = "SR6",
            TableType = "home_campaign",
            RuleCategory = "gear_availability",
            Severity = "blocks_play",
            FeedbackPrompt = "We need a campaign unlock lane for restricted gear.",
            UserWordsSummary = "I want to mark gear unavailable until our campaign unlocks it.",
            CurrentWorkaround = "We track unlocks manually.",
            InterpretedNeedSummary = "Campaign-scoped availability overlay with build-impact preview.",
            ImpactNotes = "Players need to see the change before they join.",
            ShareabilityNotes = "We would share this as a reusable pack.",
            ReplyEmail = "gm@example.invalid",
            FollowUpAllowed = true,
            QuoteAllowed = true,
            ConsentAccepted = true
        }, "subject-kf-1", "Switch");

        TeableKarmaForgeReviewBoardSyncResult result = await fixture.TeableService.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Equal(1, result.AttemptedCount);
        Assert.Equal(1, result.SyncedCount);
        Assert.Equal(0, result.FailedCount);
        Assert.Equal("tbl_kf", result.TableId);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/base/base-demo/table/");
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_kf/record");
        Assert.Contains(fixture.Handler.Requests, static item => item.Body.Contains("\"Projection Kind\":\"karma_forge_candidate_review\"", StringComparison.Ordinal));
        Assert.Contains(fixture.Handler.Requests, static item => item.Body.Contains("\"Queue Status\":\"candidate_for_lunacal_followup\"", StringComparison.Ordinal));
        Assert.Contains(fixture.Handler.Requests, static item => item.Body.Contains("\"Editable Fields\":\"Proposed Status\\nCurator Note\\nReviewer Assignment\"", StringComparison.Ordinal));

        TeableKarmaForgeReviewBoardDashboard dashboard = fixture.TeableService.GetDashboard();
        Assert.Equal("ready", dashboard.State);
        Assert.Equal("tbl_kf", dashboard.TableId);
        Assert.Single(dashboard.Rows);
        Assert.Equal("karma_forge_candidate_review", dashboard.Rows[0].ProjectionKind);
        Assert.Contains("Proposed Status", dashboard.Rows[0].EditableFields);
        Assert.Contains("Canonical Status", dashboard.Rows[0].ForbiddenFields);
        Assert.Contains("karma_forge_discovery:karma_candidate_reviewed", dashboard.Rows[0].JourneyProofEventRefs);
    }

    [Fact]
    public async Task InternalControllerReturnsDashboardAndSyncsOnDemand()
    {
        using Fixture fixture = new();
        fixture.Service.Submit(new KarmaForgeSubmissionRequest
        {
            TrackKey = "chummer5a_veteran_migration_track",
            RespondentRole = "Chummer5a veteran",
            Edition = "SR5 to SR6",
            TableType = "migration_workbench",
            RuleCategory = "migration",
            Severity = "session_friction",
            FeedbackPrompt = "Our legacy import still drops amend behavior.",
            UserWordsSummary = "Custom data from Chummer5a does not survive the import.",
            CurrentWorkaround = "We hand-edit exports after every import.",
            ShareabilityNotes = "This matters to every migration pass.",
            ReplyEmail = "veteran@example.invalid",
            FollowUpAllowed = false,
            QuoteAllowed = false,
            ConsentAccepted = true
        }, null, null);

        InternalTeableKarmaForgeController controller = new(fixture.TeableService, fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-demo-token";

        ActionResult<TeableKarmaForgeReviewBoardDashboard> response = await controller.GetDashboard(sync: true, CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        TeableKarmaForgeReviewBoardDashboard dashboard = Assert.IsType<TeableKarmaForgeReviewBoardDashboard>(ok.Value);
        Assert.Single(dashboard.Rows);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_kf/record");
    }

    [Fact]
    public async Task EndToEndWorkflow_SubmissionProjectsIntoReviewBoardDashboardWithDesignMetadata()
    {
        using Fixture fixture = new();

        KarmaForgeSubmissionProjection submission = fixture.Service.Submit(new KarmaForgeSubmissionRequest
        {
            TrackKey = "gm_house_rule_track",
            RespondentRole = "GM",
            Edition = "SR6",
            TableType = "home_campaign",
            RuleCategory = "gear_availability",
            Severity = "blocks_play",
            FeedbackPrompt = "We need campaign unlock review and before-join trust proof.",
            UserWordsSummary = "Restricted gear should unlock at campaign milestones.",
            CurrentWorkaround = "We track unlocks in chat and hand-review every sheet.",
            InterpretedNeedSummary = "A governed campaign overlay with player-visible receipts.",
            ImpactNotes = "Before-join trust needs visibility and rollback.",
            ShareabilityNotes = "This should become a reusable rules package candidate.",
            ReplyEmail = "gm@example.invalid",
            FollowUpAllowed = true,
            QuoteAllowed = true,
            ConsentAccepted = true
        }, "subject-kf-1", "Switch");

        Assert.Equal("candidate_for_lunacal_followup", submission.QueueStatus);
        Assert.Contains(submission.Packet.Source.ExternalStages, static stage =>
            stage.StageKey == "review_board" && stage.Status == "bounded_ready");

        TeableKarmaForgeReviewBoardSyncResult syncResult = await fixture.TeableService.SyncAllAsync();
        Assert.Equal("passed", syncResult.State);
        Assert.Equal(1, syncResult.SyncedCount);

        InternalTeableKarmaForgeController controller = new(fixture.TeableService, fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-demo-token";

        ActionResult<TeableKarmaForgeReviewBoardDashboard> response = await controller.GetDashboard(sync: false, CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        TeableKarmaForgeReviewBoardDashboard dashboard = Assert.IsType<TeableKarmaForgeReviewBoardDashboard>(ok.Value);
        TeableKarmaForgeReviewBoardRow row = Assert.Single(dashboard.Rows);

        Assert.Equal($"karmaforge:{submission.SubmissionId}", row.ProjectionId);
        Assert.Equal("karma_forge_candidate_review", row.ProjectionKind);
        Assert.Equal("chummer6-hub", row.SourceSystem);
        Assert.Equal(submission.SubmissionId, row.SourceId);
        Assert.Equal("operator_only", row.VisibilityClass);
        Assert.Equal("teable_karma_forge_review_board", row.KillSwitchKey);
        Assert.Contains("Proposed Status", row.EditableFields);
        Assert.Contains("Reviewer Assignment", row.EditableFields);
        Assert.Contains("Canonical Status", row.ForbiddenFields);
        Assert.Contains("Support Case State", row.ForbiddenFields);
        Assert.Equal(submission.Packet.Id, row.PacketId);
        Assert.Equal(submission.Packet.Title, row.Title);
        Assert.Equal(submission.Candidate.CandidateDecision, row.CandidateDecision);
        Assert.Equal(submission.Packet.Source.RuleCategory, row.RuleCategory);
        Assert.Equal(submission.Packet.Source.RespondentRole, row.ReporterRole);
        Assert.Contains("karma_forge_discovery:karma_request_submitted", row.JourneyProofEventRefs);
        Assert.Contains("karma_forge_discovery:karma_candidate_reviewed", row.JourneyProofEventRefs);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_kf/record");
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "teable-karma-forge-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Handler = new FakeTeableHandler();
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_KARMA_FORGE_STORE_PATH"] = Path.Combine(_root, "karma-forge-store.json"),
                    ["FLEET_INTERNAL_API_TOKEN"] = "internal-demo-token",
                    ["CHUMMER_TEABLE_KARMA_FORGE_ENABLED"] = "true",
                    ["CHUMMER_TEABLE_KARMA_FORGE_API_KEY"] = "teable-demo-token",
                    ["CHUMMER_TEABLE_KARMA_FORGE_API_BASE_URL"] = "https://app.teable.ai/api",
                    ["CHUMMER_TEABLE_KARMA_FORGE_BASE_ID"] = "base-demo",
                    ["CHUMMER_TEABLE_KARMA_FORGE_TABLE_NAME"] = "Karma Forge Review Board",
                    ["CHUMMER_KARMA_FORGE_DEFTFORM_BASE_URL"] = "https://forms.example.invalid/deftform",
                    ["CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL"] = "https://discover.example.invalid/icanpreneur",
                    ["CHUMMER_KARMA_FORGE_METASURVEY_BASE_URL"] = "https://surveys.example.invalid/metasurvey",
                    ["CHUMMER_KARMA_FORGE_LUNACAL_BASE_URL"] = "https://schedule.example.invalid/lunacal"
                })
                .Build();

            Store = new KarmaForgeStore(Configuration, NullLogger<KarmaForgeStore>.Instance);
            Service = new KarmaForgeDiscoveryService(Store, Configuration);
            TeableService = new TeableKarmaForgeReviewBoardService(
                Store,
                Configuration,
                new StaticHttpClientFactory(new HttpClient(Handler)),
                NullLogger<TeableKarmaForgeReviewBoardService>.Instance);
        }

        public IConfiguration Configuration { get; }
        public KarmaForgeStore Store { get; }
        public KarmaForgeDiscoveryService Service { get; }
        public TeableKarmaForgeReviewBoardService TeableService { get; }
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
                return JsonResponse("""{"id":"tbl_kf"}""");
            }

            if (request.Method == HttpMethod.Get && path == "/api/table/tbl_kf/field")
            {
                return JsonResponse("[]");
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_kf/field")
            {
                return JsonResponse("""{"id":"fld"}""");
            }

            if (request.Method == HttpMethod.Get && path == "/api/table/tbl_kf/record")
            {
                return JsonResponse("""{"records":[]}""");
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_kf/record")
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
