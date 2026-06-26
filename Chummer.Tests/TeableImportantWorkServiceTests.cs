using System.Net;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class TeableImportantWorkServiceTests
{
    [Fact]
    public async Task RecordAndSyncProjectsImportantWorkIntoChummerRunTeableTable()
    {
        using Fixture fixture = new();

        ImportantWorkItemProjection item = fixture.Service.Record(new ImportantWorkItemRequest(
            Kind: "workflow",
            Scope: "chummer.run",
            Summary: "Store important user and workflow context in Teable",
            Detail: "Use the chummer.run base. Do not use the Executive Assistant base.",
            Status: "open",
            Priority: "high",
            Source: "codex",
            Tags: ["teable", "workflow"],
            ItemId: "work_teable_context"));

        TeableImportantWorkSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Equal("tbl_work", result.TableId);
        Assert.Equal("work_teable_context", item.ItemId);
        Assert.Contains(
            fixture.Handler.Requests,
            static request => request.Method == HttpMethod.Post
                && request.Path == "/api/base/base-demo/table/"
                && request.Body.Contains("Chummer Important Work", StringComparison.Ordinal)
                && request.Body.Contains("chummer_important_work", StringComparison.Ordinal));
        LoggedRequest create = Assert.Single(
            fixture.Handler.Requests,
            static request => request.Method == HttpMethod.Post && request.Path == "/api/table/tbl_work/record");
        Assert.Contains("\"Scope\":\"chummer.run\"", create.Body, StringComparison.Ordinal);
        Assert.Contains("Do not use the Executive Assistant base.", create.Body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task SyncRefusesExecutiveAssistantDestinationBeforeHttpWrite()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME"] = "Executive Assistant Work",
        });
        fixture.Service.Record(new ImportantWorkItemRequest(
            Kind: "workflow",
            Scope: "chummer.run",
            Summary: "Should not sync",
            Detail: "Wrong destination.",
            Status: "open",
            Priority: "high",
            ItemId: "work_wrong_base"));
        fixture.Handler.Requests.Clear();

        TeableImportantWorkSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("failed", result.State);
        Assert.Contains("teable_important_work_refuses_executive_assistant_destination", result.Errors);
        Assert.Empty(fixture.Handler.Requests);
    }

    [Fact]
    public async Task SyncRequiresExplicitChummerRunBaseInsteadOfFallingBackToUsersBase()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID"] = "",
            ["CHUMMER_TEABLE_USERS_BASE_ID"] = "old-executive-assistant-base",
            ["CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID"] = "",
        });
        fixture.Service.Record(new ImportantWorkItemRequest(
            Kind: "workflow",
            Scope: "chummer.run",
            Summary: "Should not fall back",
            Detail: "Important Chummer work belongs in the chummer.run base only.",
            Status: "open",
            Priority: "high",
            ItemId: "work_no_ea_fallback"));
        fixture.Handler.Requests.Clear();

        TeableImportantWorkSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("failed", result.State);
        Assert.Contains("teable_chummer_run_base_id_required", result.Errors);
        Assert.Empty(fixture.Handler.Requests);
    }

    [Fact]
    public async Task ControllerRequiresInternalAuthForImportantWorkRecord()
    {
        using Fixture fixture = new();
        var controller = new InternalTeableImportantWorkController(fixture.Service, fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<ImportantWorkItemProjection> denied = controller.Record(new ImportantWorkItemRequest(
            Kind: "workflow",
            Scope: "chummer.run",
            Summary: "No auth",
            Detail: "No auth",
            Status: "open",
            Priority: "normal"));

        Assert.IsType<ObjectResult>(denied.Result);

        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-demo-token";
        ActionResult<ImportantWorkItemProjection> allowed = controller.Record(new ImportantWorkItemRequest(
            Kind: "workflow",
            Scope: "chummer.run",
            Summary: "With auth",
            Detail: "With auth",
            Status: "open",
            Priority: "normal",
            ItemId: "work_auth"));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(allowed.Result);
        ImportantWorkItemProjection item = Assert.IsType<ImportantWorkItemProjection>(ok.Value);
        Assert.Equal("work_auth", item.ItemId);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(IReadOnlyDictionary<string, string?>? overrides = null)
        {
            _root = Path.Combine(Path.GetTempPath(), "teable-important-work-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Handler = new FakeTeableHandler();
            Dictionary<string, string?> values = new()
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                ["FLEET_INTERNAL_API_TOKEN"] = "internal-demo-token",
                ["CHUMMER_TEABLE_IMPORTANT_WORK_ENABLED"] = "true",
                ["CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY"] = "teable-demo-token",
                ["CHUMMER_TEABLE_IMPORTANT_WORK_API_BASE_URL"] = "https://app.teable.ai/api",
                ["CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID"] = "base-demo",
                ["CHUMMER_TEABLE_IMPORTANT_WORK_BASE_PURPOSE"] = "chummer.run",
                ["CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME"] = "Chummer Important Work",
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
            Service = new TeableImportantWorkService(
                Store,
                Configuration,
                new StaticHttpClientFactory(new HttpClient(Handler)),
                NullLogger<TeableImportantWorkService>.Instance);
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public TeableImportantWorkService Service { get; }
        public FakeTeableHandler Handler { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class StaticHttpClientFactory(HttpClient client) : IHttpClientFactory
    {
        public HttpClient CreateClient(string name) => client;
    }

    private sealed class FakeTeableHandler : HttpMessageHandler
    {
        private readonly HashSet<string> _fields = new(StringComparer.OrdinalIgnoreCase);
        public List<LoggedRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string path = request.RequestUri?.PathAndQuery ?? string.Empty;
            string body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add(new LoggedRequest(request.Method, path, body));

            if (request.Method == HttpMethod.Get && path == "/api/base/base-demo/table")
            {
                return Json(HttpStatusCode.OK, "[]");
            }

            if (request.Method == HttpMethod.Post && path == "/api/base/base-demo/table/")
            {
                return Json(HttpStatusCode.Created, """{"id":"tbl_work"}""");
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_work/field", StringComparison.Ordinal))
            {
                string payload = JsonSerializer.Serialize(_fields.Select(static name => new { id = $"fld_{name.Replace(" ", "_", StringComparison.Ordinal)}", name }).ToArray());
                return Json(HttpStatusCode.OK, payload);
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_work/field")
            {
                using JsonDocument document = JsonDocument.Parse(body);
                string name = document.RootElement.GetProperty("name").GetString() ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(name))
                {
                    _fields.Add(name);
                }

                return Json(HttpStatusCode.Created, $$"""{"id":"fld_{{_fields.Count}}","name":{{JsonSerializer.Serialize(name)}}}""");
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_work/record?", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.OK, """{"records":[]}""");
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_work/record")
            {
                return Json(HttpStatusCode.Created, """{"records":[{"id":"rec_work"}]}""");
            }

            if (request.Method == HttpMethod.Patch && path.StartsWith("/api/table/tbl_work/record/", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.OK, """{"id":"rec_work"}""");
            }

            return Json(HttpStatusCode.NotFound, $$"""{"error":"unexpected {{request.Method}} {{path}}"}""");
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string body)
            => new(status)
            {
                Content = new StringContent(body, System.Text.Encoding.UTF8, "application/json")
            };
    }

    private sealed record LoggedRequest(HttpMethod Method, string Path, string Body);
}
