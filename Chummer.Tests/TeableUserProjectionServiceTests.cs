using System.Net;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class TeableUserProjectionServiceTests
{
    [Fact]
    public async Task SyncAllCreatesTableAndProjectsStoredUsers()
    {
        using Fixture fixture = new();
        SeedUser(fixture.Store, new HubUserDto(
            UserId: "usr-demo",
            SubjectId: "subject.demo",
            DisplayName: "Demo Runner",
            Handle: "demo-runner",
            Visibility: "private",
            Timezone: "Europe/Vienna",
            CountryCode: "AT",
            LinkedPrincipals: ["subject.demo"],
            GroupIds: ["grp-alpha"],
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:15:00Z"))
        {
            Email = "demo@example.com",
        });

        TeableUserProjectionSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Equal(1, result.AttemptedCount);
        Assert.Equal(1, result.SyncedCount);
        Assert.Equal(0, result.FailedCount);
        Assert.Equal("tbl_users", result.TableId);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/base/base-demo/table/");
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
        Assert.Contains(fixture.Handler.Requests, static item => item.Body.Contains("\"Email\":\"demo@example.com\"", StringComparison.Ordinal));

        TeableUserProjectionDashboard dashboard = fixture.Service.GetDashboard();
        Assert.Equal("ready", dashboard.State);
        Assert.Equal("tbl_users", dashboard.TableId);
        Assert.Single(dashboard.Users);
        Assert.Equal("demo@example.com", dashboard.Users[0].Email);
    }

    [Fact]
    public void EnsureUserRetainsEmailInHubStore()
    {
        using Fixture fixture = new(enableTeable: false);
        AccountService accounts = new(fixture.Store, fixture.Service, NullLogger<AccountService>.Instance);

        HubUserDto user = accounts.EnsureUser("subject.demo", "Demo Runner", "demo@example.com");

        Assert.Equal("demo@example.com", user.Email);

        HubUserDto? reloaded = accounts.GetBySubject("subject.demo");
        Assert.NotNull(reloaded);
        Assert.Equal("demo@example.com", reloaded!.Email);
    }

    [Fact]
    public async Task InternalControllerReturnsDashboardAndSyncsOnDemand()
    {
        using Fixture fixture = new();
        SeedUser(fixture.Store, new HubUserDto(
            UserId: "usr-demo",
            SubjectId: "subject.demo",
            DisplayName: "Demo Runner",
            Handle: "demo-runner",
            Visibility: "private",
            Timezone: "UTC",
            CountryCode: "",
            LinkedPrincipals: ["subject.demo"],
            GroupIds: Array.Empty<string>(),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow)
        {
            Email = "demo@example.com",
        });

        InternalTeableUsersController controller = new(fixture.Service, fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-demo-token";

        ActionResult<TeableUserProjectionDashboard> response = await controller.GetDashboard(sync: true, CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        TeableUserProjectionDashboard dashboard = Assert.IsType<TeableUserProjectionDashboard>(ok.Value);
        Assert.Single(dashboard.Users);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
    }

    [Fact]
    public async Task SyncAllUpdatesExistingRecordInsteadOfCreatingDuplicate()
    {
        using Fixture fixture = new();
        fixture.Handler.ExistingRecordIdByUserId["usr-demo"] = "rec_existing";
        SeedUser(fixture.Store, new HubUserDto(
            UserId: "usr-demo",
            SubjectId: "subject.demo",
            DisplayName: "Demo Runner",
            Handle: "demo-runner",
            Visibility: "private",
            Timezone: "UTC",
            CountryCode: "",
            LinkedPrincipals: ["subject.demo"],
            GroupIds: Array.Empty<string>(),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow)
        {
            Email = "demo@example.com",
        });

        TeableUserProjectionSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Patch && item.Path == "/api/table/tbl_users/record/rec_existing");
        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
    }

    [Fact]
    public async Task BackgroundWorkerReconcilesStoredUsersWithoutManualTrigger()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_USERS_RECONCILE_ENABLED"] = "true",
            ["CHUMMER_TEABLE_USERS_RECONCILE_INITIAL_DELAY_SECONDS"] = "0",
            ["CHUMMER_TEABLE_USERS_RECONCILE_INTERVAL_MINUTES"] = "60",
        });
        SeedUser(fixture.Store, new HubUserDto(
            UserId: "usr-demo",
            SubjectId: "subject.demo",
            DisplayName: "Demo Runner",
            Handle: "demo-runner",
            Visibility: "private",
            Timezone: "UTC",
            CountryCode: "",
            LinkedPrincipals: ["subject.demo"],
            GroupIds: Array.Empty<string>(),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow)
        {
            Email = "demo@example.com",
        });

        using var worker = new TeableUserProjectionSyncWorker(
            fixture.Service,
            fixture.Configuration,
            NullLogger<TeableUserProjectionSyncWorker>.Instance);
        await worker.StartAsync(CancellationToken.None);
        try
        {
            DateTime deadline = DateTime.UtcNow.AddSeconds(2);
            while (DateTime.UtcNow < deadline
                && !fixture.Handler.Requests.Any(static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record"))
            {
                await Task.Delay(25);
            }

            Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
        }
        finally
        {
            await worker.StopAsync(CancellationToken.None);
        }
    }

    private static void SeedUser(CommunityStore store, HubUserDto user)
    {
        lock (store.Gate)
        {
            store.UsersById[user.UserId] = user;
            store.UserIdBySubjectId[user.SubjectId] = user.UserId;
            store.PersistLocked();
        }
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(bool enableTeable = true)
            : this(null, enableTeable)
        {
        }

        public Fixture(IReadOnlyDictionary<string, string?>? overrides, bool enableTeable = true)
        {
            _root = Path.Combine(Path.GetTempPath(), "teable-user-projection-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Handler = new FakeTeableHandler();
            Dictionary<string, string?> values = new()
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                    ["FLEET_INTERNAL_API_TOKEN"] = "internal-demo-token",
                    ["CHUMMER_TEABLE_USERS_ENABLED"] = enableTeable ? "true" : "false",
                    ["CHUMMER_TEABLE_USERS_API_KEY"] = "teable-demo-token",
                    ["CHUMMER_TEABLE_USERS_API_BASE_URL"] = "https://app.teable.ai/api",
                    ["CHUMMER_TEABLE_USERS_BASE_ID"] = "base-demo",
                    ["CHUMMER_TEABLE_USERS_TABLE_NAME"] = "Chummer Run Users",
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
            Service = new TeableUserProjectionService(
                Store,
                Configuration,
                new StaticHttpClientFactory(new HttpClient(Handler)),
                NullLogger<TeableUserProjectionService>.Instance);
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public TeableUserProjectionService Service { get; }
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
        private readonly HashSet<string> _fields = new(StringComparer.OrdinalIgnoreCase);

        public List<LoggedRequest> Requests { get; } = [];
        public Dictionary<string, string> ExistingRecordIdByUserId { get; } = new(StringComparer.OrdinalIgnoreCase);

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
                return Json(HttpStatusCode.Created, """
                    {
                      "id": "tbl_users"
                    }
                    """);
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_users/field", StringComparison.Ordinal))
            {
                string payload = JsonSerializer.Serialize(_fields.Select(static name => new { id = $"fld_{name.Replace(" ", "_", StringComparison.Ordinal)}", name }).ToArray());
                return Json(HttpStatusCode.OK, payload);
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_users/field")
            {
                using JsonDocument document = JsonDocument.Parse(body);
                string name = document.RootElement.GetProperty("name").GetString() ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(name))
                {
                    _fields.Add(name);
                }

                return Json(HttpStatusCode.Created, $$"""
                    {
                      "id": "fld_{{_fields.Count}}",
                      "name": {{JsonSerializer.Serialize(name)}}
                    }
                    """);
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_users/record?", StringComparison.Ordinal))
            {
                string userId = ExtractUserId(path) ?? string.Empty;
                if (ExistingRecordIdByUserId.TryGetValue(userId, out string? recordId))
                {
                    return Json(HttpStatusCode.OK, $$"""
                        {
                          "records": [
                            {
                              "id": {{JsonSerializer.Serialize(recordId)}}
                            }
                          ]
                        }
                        """);
                }

                return Json(HttpStatusCode.OK, """
                        {
                          "records": []
                        }
                        """);
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_users/record")
            {
                return Json(HttpStatusCode.Created, """
                    {
                      "records": [
                        {
                          "id": "rec_demo"
                        }
                      ]
                    }
                    """);
            }

            if (request.Method == HttpMethod.Patch && path.StartsWith("/api/table/tbl_users/record/", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.OK, """
                    {
                      "id": "rec_demo"
                    }
                    """);
            }

            return Json(HttpStatusCode.NotFound, $$"""
                {
                  "path": {{JsonSerializer.Serialize(path)}}
                }
                """);
        }

        private static HttpResponseMessage Json(HttpStatusCode statusCode, string payload)
            => new(statusCode)
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json")
            };

        private static string? ExtractUserId(string path)
        {
            int marker = path.IndexOf("filterByTql=", StringComparison.Ordinal);
            if (marker < 0)
            {
                return null;
            }

            string encoded = path[(marker + "filterByTql=".Length)..];
            int next = encoded.IndexOf('&');
            if (next >= 0)
            {
                encoded = encoded[..next];
            }

            string filter = Uri.UnescapeDataString(encoded);
            const string prefix = "{User Id} = '";
            int start = filter.IndexOf(prefix, StringComparison.Ordinal);
            if (start < 0)
            {
                return null;
            }

            start += prefix.Length;
            int end = filter.IndexOf('\'', start);
            return end <= start ? null : filter[start..end];
        }
    }

    private sealed record LoggedRequest(HttpMethod Method, string Path, string Body);
}
