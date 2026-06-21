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
        LoggedRequest createTable = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/base/base-demo/table/");
        Assert.DoesNotContain("\"unique\"", createTable.Body, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("\"notNull\"", createTable.Body, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
        Assert.Contains(fixture.Handler.Requests, static item => item.Body.Contains("\"Email\":\"demo@example.com\"", StringComparison.Ordinal));

        TeableUserProjectionDashboard dashboard = fixture.Service.GetDashboard();
        Assert.Equal("ready", dashboard.State);
        Assert.Equal("tbl_users", dashboard.TableId);
        Assert.Single(dashboard.Users);
        Assert.Equal("demo@example.com", dashboard.Users[0].Email);
    }

    [Fact]
    public async Task SyncAllProjectsWhatsappAiSupportChannelForRouteImport()
    {
        using Fixture fixture = new();
        HubUserDto user = new(
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
        };
        SeedUser(fixture.Store, user);
        lock (fixture.Store.Gate)
        {
            fixture.Store.ChannelLinks.Add(new ChannelLinkDto(
                ChannelLinkId: "chn-whatsapp-demo",
                UserId: user.UserId,
                ChannelKind: "whatsapp_official_business",
                DisplayLabel: "+436647916419",
                Status: "ea_linked",
                OfficialChannel: true,
                NotificationsEnabled: true,
                CreatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:20:00Z"),
                UpdatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:21:00Z"),
                Note: "WhatsApp AI support")
            {
                Purpose = "ai_support_only",
                AiSupportOpeningPrompt = "Ask what questions the user has before giving product guidance."
            });
            fixture.Store.PersistLocked();
        }

        TeableUserProjectionSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("passed", result.State);
        LoggedRequest create = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
        using JsonDocument created = JsonDocument.Parse(create.Body);
        JsonElement fields = created.RootElement.GetProperty("records")[0].GetProperty("fields");
        Assert.Equal("+436647916419", fields.GetProperty("WhatsApp AI Support Phone").GetString());
        Assert.Equal("6419", fields.GetProperty("WhatsApp AI Support Phone Last4").GetString());
        Assert.True(fields.GetProperty("WhatsApp AI Support Enabled").GetBoolean());
        Assert.True(fields.GetProperty("WhatsApp Notifications Enabled").GetBoolean());
        Assert.Equal("ai_support_only", fields.GetProperty("WhatsApp AI Support Purpose").GetString());
        Assert.Contains("what questions the user has", fields.GetProperty("WhatsApp AI Support Opening Prompt").GetString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task SyncAllDefaultsLegacyWhatsappSupportChannelPurposeForRouteImport()
    {
        using Fixture fixture = new();
        HubUserDto user = new(
            UserId: "usr-demo",
            SubjectId: "subject.demo",
            DisplayName: "Demo Runner",
            Handle: "demo-runner",
            Visibility: "private",
            Timezone: "Europe/Vienna",
            CountryCode: "AT",
            LinkedPrincipals: ["subject.demo"],
            GroupIds: Array.Empty<string>(),
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:15:00Z"));
        SeedUser(fixture.Store, user);
        lock (fixture.Store.Gate)
        {
            fixture.Store.ChannelLinks.Add(new ChannelLinkDto(
                ChannelLinkId: "chn-whatsapp-demo",
                UserId: user.UserId,
                ChannelKind: "whatsapp_official_business",
                DisplayLabel: "+436647916419",
                Status: "linked",
                OfficialChannel: true,
                NotificationsEnabled: false,
                CreatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:20:00Z"),
                UpdatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:21:00Z"),
                Note: "Legacy WhatsApp support link"));
            fixture.Store.PersistLocked();
        }

        TeableUserProjectionSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("passed", result.State);
        LoggedRequest create = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
        using JsonDocument created = JsonDocument.Parse(create.Body);
        JsonElement fields = created.RootElement.GetProperty("records")[0].GetProperty("fields");
        Assert.True(fields.GetProperty("WhatsApp AI Support Enabled").GetBoolean());
        Assert.False(fields.GetProperty("WhatsApp Notifications Enabled").GetBoolean());
        Assert.Equal("ai_support_only", fields.GetProperty("WhatsApp AI Support Purpose").GetString());
        Assert.Contains("what questions the user has", fields.GetProperty("WhatsApp AI Support Opening Prompt").GetString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task SyncAllBatchCreatesMissingUsersAfterSingleExistingRecordScan()
    {
        using Fixture fixture = new();
        SeedUser(fixture.Store, new HubUserDto(
            UserId: "usr-demo-1",
            SubjectId: "subject.demo.1",
            DisplayName: "Demo Runner 1",
            Handle: "demo-runner-1",
            Visibility: "private",
            Timezone: "UTC",
            CountryCode: "",
            LinkedPrincipals: ["subject.demo.1"],
            GroupIds: Array.Empty<string>(),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow)
        {
            Email = "demo1@example.com",
        });
        SeedUser(fixture.Store, new HubUserDto(
            UserId: "usr-demo-2",
            SubjectId: "subject.demo.2",
            DisplayName: "Demo Runner 2",
            Handle: "demo-runner-2",
            Visibility: "private",
            Timezone: "UTC",
            CountryCode: "",
            LinkedPrincipals: ["subject.demo.2"],
            GroupIds: Array.Empty<string>(),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow)
        {
            Email = "demo2@example.com",
        });

        TeableUserProjectionSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Equal(2, result.SyncedCount);
        Assert.Single(fixture.Handler.Requests, static item => item.Method == HttpMethod.Get && item.Path.StartsWith("/api/table/tbl_users/record?", StringComparison.Ordinal));
        LoggedRequest create = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
        using JsonDocument created = JsonDocument.Parse(create.Body);
        Assert.Equal(2, created.RootElement.GetProperty("records").GetArrayLength());
    }

    [Fact]
    public async Task SyncAllWritesWorkspacePrepLibrarySearchHistoryField()
    {
        using Fixture fixture = new();
        HubUserDto user = new(
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
        };
        SeedUser(fixture.Store, user);
        fixture.Store.UserExperienceByUserId[user.UserId] = new HubUserExperienceDto(
            UserId: user.UserId,
            LaneInterests: Array.Empty<string>(),
            FollowHorizons: false,
            BetaInterest: false,
            OnboardingCompleted: false,
            OnboardingCompletedAtUtc: null,
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-12T10:15:00Z"),
            ImpactCloseoutNotifications: false,
            PublicContributionProfileOptIn: false,
            BlackLedgerNewsEmail: false,
            WorkspacePrepLibrarySearchHistory:
            [
                new WorkspacePrepLibrarySearchHistoryItem("ws-demo", "opposition", DateTimeOffset.Parse("2026-04-12T10:01:00Z")),
                new WorkspacePrepLibrarySearchHistoryItem("ws-demo", "scene", DateTimeOffset.Parse("2026-04-12T10:02:00Z")),
            ],
            BlackLedgerWorldsFollowed: Array.Empty<string>());

        TeableUserProjectionSyncResult result = await fixture.Service.SyncAllAsync();
        Assert.Equal("passed", result.State);

        LoggedRequest create = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record");
        using JsonDocument created = JsonDocument.Parse(create.Body);
        JsonElement records = created.RootElement.GetProperty("records");
        using JsonDocument history = JsonDocument.Parse(records[0].GetProperty("fields").GetProperty("Workspace Prep Library Search History").GetString() ?? "[]");

        Assert.Equal(JsonValueKind.Array, history.RootElement.ValueKind);
        Assert.Equal(2, history.RootElement.GetArrayLength());
        Assert.Equal("ws-demo", history.RootElement[0].GetProperty("WorkspaceId").GetString());
        Assert.Equal("scene", history.RootElement[1].GetProperty("Query").GetString());
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
    public async Task SyncAllDoesNotPatchWhenTeableOmitsEmptyOptionalCells()
    {
        using Fixture fixture = new();
        DateTimeOffset createdAt = DateTimeOffset.Parse("2026-04-12T10:00:00Z");
        DateTimeOffset updatedAt = DateTimeOffset.Parse("2026-04-12T10:15:00Z");
        fixture.Handler.ExistingRecordIdByUserId["usr-demo"] = "rec_existing";
        fixture.Handler.ExistingFieldsByUserId["usr-demo"] = new Dictionary<string, object>
        {
            ["Display Name"] = "Demo Runner",
            ["User Id"] = "usr-demo",
            ["Subject Id"] = "subject.demo",
            ["Handle"] = "demo-runner",
            ["Visibility"] = "private",
            ["Timezone"] = "UTC",
            ["Linked Principals"] = "subject.demo",
            ["Created At UTC"] = createdAt.ToString("O"),
            ["Updated At UTC"] = updatedAt.ToString("O"),
        };
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
            CreatedAtUtc: createdAt,
            UpdatedAtUtc: updatedAt));

        TeableUserProjectionSyncResult result = await fixture.Service.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Equal(1, result.SyncedCount);
        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Method == HttpMethod.Patch);
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
        public Dictionary<string, Dictionary<string, object>> ExistingFieldsByUserId { get; } = new(StringComparer.OrdinalIgnoreCase);

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
                if (path.Contains("filterByTql=", StringComparison.Ordinal))
                {
                    string userId = ExtractUserId(path) ?? string.Empty;
                    if (ExistingRecordIdByUserId.TryGetValue(userId, out string? recordId))
                    {
                        Dictionary<string, object> fields = BuildExistingRecordFields(userId);
                        return Json(HttpStatusCode.OK, $$"""
                            {
                              "records": [
                                {
                                  "id": {{JsonSerializer.Serialize(recordId)}},
                                  "fields": {{JsonSerializer.Serialize(fields)}}
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

                object[] records = ExistingRecordIdByUserId
                    .Select(item => new
                    {
                        id = item.Value,
                        fields = BuildExistingRecordFields(item.Key),
                    })
                    .ToArray();
                return Json(HttpStatusCode.OK, JsonSerializer.Serialize(new { records }));
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

        private Dictionary<string, object> BuildExistingRecordFields(string userId)
        {
            if (ExistingFieldsByUserId.TryGetValue(userId, out Dictionary<string, object>? fields))
            {
                return fields;
            }

            return new Dictionary<string, object>
            {
                ["User Id"] = userId,
            };
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
