using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerAccessTests
{
    [Fact]
    public void Lore_owner_can_read_and_write_but_same_faction_other_campaign_cannot()
    {
        using var f = new FactionAccessFixture();
        var owner = f.Accounts.EnsureUser("owner");
        var other = f.Accounts.EnsureUser("other");
        var charter = f.Factions.CreateFaction(owner, FactionAccessFixture.Charter());
        f.Factions.JoinFaction(other, charter.FactionId);
        FactionAccessFixture.AddCampaign(f.Store, owner, "campaign-owner");
        FactionAccessFixture.AddCampaign(f.Store, other, "campaign-other");
        using (f.Store.Enter())
        {
            var group = f.Store.GroupsById["group-campaign-owner"];
            f.Store.GroupsById[group.GroupId] = group with
            {
                Memberships = [.. group.Memberships, new("other-gm", group.GroupId, other.UserId, "gm", DateTimeOffset.UtcNow)]
            };
            f.Store.PersistLocked();
        }
        var overlay = f.Factions.UpsertPrivateLoreOverlay(owner, "campaign-owner", FactionAccessFixture.Lore(charter.FactionId));
        Assert.Equal(overlay, f.Factions.GetPrivateLoreOverlay(owner, "campaign-owner", charter.FactionId));
        Assert.Null(f.Factions.GetPrivateLoreOverlay(other, "campaign-other", charter.FactionId));
        Assert.False(overlay.PublicProjectionAllowed);
        var before = f.Snapshot();
        AssertLoreDenied(() => f.Factions.GetPrivateLoreOverlay(other, "campaign-owner", charter.FactionId));
        AssertLoreDenied(() => f.Factions.UpsertPrivateLoreOverlay(other, "campaign-owner", FactionAccessFixture.Lore(charter.FactionId)));
        Assert.Equal(before, f.Snapshot());
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("unknown")]
    [InlineData("unowned")]
    [InlineData("missing-group")]
    public void Lore_denial_is_uniform_and_does_not_initialize_state(string? campaignId)
    {
        using var f = new FactionAccessFixture();
        var user = f.Accounts.EnsureUser("reader");
        FactionAccessFixture.AddCampaign(f.Store, user, "unowned", ownerId: "");
        FactionAccessFixture.AddCampaign(f.Store, user, "missing-group");
        using (f.Store.Enter())
        {
            f.Store.GroupsById.Remove("group-missing-group");
            f.Store.BlackLedgerFactionOnboardingState = null;
            f.Store.PersistLocked();
        }
        var before = f.Snapshot();
        AssertLoreDenied(() => f.Factions.GetPrivateLoreOverlay(user, campaignId!, "ashline-circle"));
        AssertLoreDenied(() => f.Factions.UpsertPrivateLoreOverlay(user, campaignId!, FactionAccessFixture.Lore("ashline-circle")));
        Assert.Equal(before, f.Snapshot());
        Assert.Null(f.Store.BlackLedgerFactionOnboardingState);
    }

    [Fact]
    public void Authorized_empty_read_and_denied_wrong_faction_write_do_not_initialize_overlays()
    {
        using var f = new FactionAccessFixture();
        var owner = f.Accounts.EnsureUser("owner");
        FactionAccessFixture.AddCampaign(f.Store, owner, "owned-campaign");
        Assert.Null(f.Store.BlackLedgerFactionOnboardingState);
        var before = f.Snapshot();
        Assert.Null(f.Factions.GetPrivateLoreOverlay(owner, "owned-campaign", "ashline-circle"));
        Assert.Throws<InvalidOperationException>(() => f.Factions.UpsertPrivateLoreOverlay(owner, "owned-campaign", FactionAccessFixture.Lore("ashline-circle")));
        Assert.Equal(before, f.Snapshot());
    }

    [Fact]
    public void Lore_requires_current_account_binding_and_current_persisted_owner()
    {
        using var f = new FactionAccessFixture();
        var owner = f.Accounts.EnsureUser("owner");
        var other = f.Accounts.EnsureUser("other");
        var charter = f.Factions.CreateFaction(owner, FactionAccessFixture.Charter());
        FactionAccessFixture.AddCampaign(f.Store, owner, "campaign-owner");
        f.Factions.UpsertPrivateLoreOverlay(owner, "campaign-owner", FactionAccessFixture.Lore(charter.FactionId));
        AssertLoreDenied(() => f.Factions.GetPrivateLoreOverlay(null!, "campaign-owner", charter.FactionId));
        AssertLoreDenied(() => f.Factions.GetPrivateLoreOverlay(owner with { SubjectId = other.SubjectId }, "campaign-owner", charter.FactionId));
        using (f.Store.Enter())
        {
            var group = f.Store.GroupsById["group-campaign-owner"];
            f.Store.GroupsById[group.GroupId] = group with { OwnerUserId = other.UserId };
            f.Store.PersistLocked();
        }
        AssertLoreDenied(() => f.Factions.GetPrivateLoreOverlay(owner, "campaign-owner", charter.FactionId));
        AssertLoreDenied(() => f.Factions.UpsertPrivateLoreOverlay(owner, "campaign-owner", FactionAccessFixture.Lore(charter.FactionId)));
        Assert.NotNull(f.Factions.GetPrivateLoreOverlay(other, "campaign-owner", charter.FactionId));
    }

    [Fact]
    public async Task Lore_write_route_authenticates_and_enforces_owner_without_disclosing_existence()
    {
        using var f = new FactionAccessFixture();
        var owner = f.Accounts.EnsureUser("owner");
        var charter = f.Factions.CreateFaction(owner, FactionAccessFixture.Charter());
        FactionAccessFixture.AddCampaign(f.Store, owner, "campaign-owner");
        var request = FactionAccessFixture.Lore(charter.FactionId);
        f.IdentityHandler.SubjectId = owner.SubjectId;
        Assert.IsType<OkObjectResult>((await f.Controller.UpsertPrivateLoreOverlay("campaign-owner", request, default)).Result);
        f.IdentityHandler.SubjectId = "other";
        f.Request.Headers.Authorization = "Bearer synthetic-other-session";
        var before = f.Snapshot();
        var denied = AssertProblem((await f.Controller.UpsertPrivateLoreOverlay("campaign-owner", request, default)).Result, 404);
        var unknown = AssertProblem((await f.Controller.UpsertPrivateLoreOverlay("unknown", request, default)).Result, 404);
        Assert.Equal(denied.Detail, unknown.Detail);
        Assert.Equal(before, f.Snapshot());
        f.Request.Headers.Remove("Authorization");
        AssertProblem((await f.Controller.UpsertPrivateLoreOverlay("campaign-owner", request, default)).Result, 401);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Moderation_routes_deny_unprivileged_and_creator_even_with_asserted_roles(bool creator)
    {
        using var f = new FactionAccessFixture();
        var founder = f.Accounts.EnsureUser("founder");
        var charter = f.Factions.CreateFaction(founder, FactionAccessFixture.Charter());
        f.IdentityHandler.SubjectId = creator ? founder.SubjectId : "ordinary";
        f.IdentityHandler.Roles = creator ? ["operator"] : ["player"];
        f.Request.Headers["X-Roles"] = "operator,admin";
        f.Request.Headers["X-Moderator"] = "true";
        var before = f.Snapshot();
        AssertProblem((await f.Controller.ApproveLedgerFactionPublicProjection(charter.FactionId, default)).Result, 403);
        AssertProblem((await f.Controller.SuppressLedgerFactionPublicProjection(charter.FactionId, new("review"), default)).Result, 403);
        Assert.Equal(before, f.Snapshot());
    }

    [Fact]
    public async Task Moderation_service_requires_permission_and_independent_reviewer_and_keeps_lore_private()
    {
        using var f = new FactionAccessFixture();
        var founder = f.Accounts.EnsureUser("founder");
        var charter = f.Factions.CreateFaction(founder, FactionAccessFixture.Charter());
        FactionAccessFixture.AddCampaign(f.Store, founder, "campaign-owner");
        f.Factions.UpsertPrivateLoreOverlay(founder, "campaign-owner", FactionAccessFixture.Lore(charter.FactionId));
        var before = f.Snapshot();
        Assert.Equal(403, Assert.Throws<HubRequestAuthException>(() => f.Factions.ApproveFactionForPublicProjection(null!, charter.FactionId)).StatusCode);
        Assert.Equal(403, Assert.Throws<HubRequestAuthException>(() => f.Factions.SuppressFactionPublicProjection(null!, charter.FactionId)).StatusCode);
        var self = await FactionAccessFixture.Permission(f.Store, founder.SubjectId);
        Assert.Equal(403, Assert.Throws<HubRequestAuthException>(() => f.Factions.ApproveFactionForPublicProjection(self, charter.FactionId)).StatusCode);
        Assert.Equal(403, Assert.Throws<HubRequestAuthException>(() => f.Factions.SuppressFactionPublicProjection(self, charter.FactionId)).StatusCode);
        Assert.Equal(before, f.Snapshot());
        var reviewer = await FactionAccessFixture.Permission(f.Store);
        Assert.True(f.Factions.ApproveFactionForPublicProjection(reviewer, charter.FactionId).PublicProjectionAllowed);
        Assert.DoesNotContain("Private synthetic", JsonSerializer.Serialize(f.Factions.GetFactionDetail(charter.FactionId)), StringComparison.Ordinal);
        Assert.DoesNotContain("Private synthetic", JsonSerializer.Serialize(f.Factions.ListFactionSummaries()), StringComparison.Ordinal);
        Assert.False(f.Factions.SuppressFactionPublicProjection(reviewer, charter.FactionId).PublicProjectionAllowed);
        Assert.Null(f.Factions.GetFactionDetail(charter.FactionId));
        Assert.False(f.Factions.GetPrivateLoreOverlay(founder, "campaign-owner", charter.FactionId)!.PublicProjectionAllowed);
    }

    [Theory]
    [InlineData("operator")]
    [InlineData("admin")]
    public async Task Moderation_routes_allow_operator_and_recheck_revocation_instead_of_cached_roles(string role)
    {
        using var f = new FactionAccessFixture();
        var founder = f.Accounts.EnsureUser("founder");
        var charter = f.Factions.CreateFaction(founder, FactionAccessFixture.Charter());
        f.IdentityHandler.Roles = [role];
        await f.Identity.RequireSubjectAsync(f.Request, default); // Populate the ordinary subject cache.
        Assert.IsType<OkObjectResult>((await f.Controller.ApproveLedgerFactionPublicProjection(charter.FactionId, default)).Result);
        Assert.IsType<OkObjectResult>((await f.Controller.SuppressLedgerFactionPublicProjection(charter.FactionId, new("review"), default)).Result);
        f.IdentityHandler.Roles = ["player"];
        var before = f.Snapshot();
        AssertProblem((await f.Controller.ApproveLedgerFactionPublicProjection(charter.FactionId, default)).Result, 403);
        AssertProblem((await f.Controller.SuppressLedgerFactionPublicProjection(charter.FactionId, null, default)).Result, 403);
        Assert.Equal(before, f.Snapshot());
        f.Request.Headers.Remove("Authorization");
        AssertProblem((await f.Controller.ApproveLedgerFactionPublicProjection(charter.FactionId, default)).Result, 401);
        AssertProblem((await f.Controller.SuppressLedgerFactionPublicProjection(charter.FactionId, null, default)).Result, 401);
    }

    private static void AssertLoreDenied(Action action)
    {
        var error = Assert.Throws<HubRequestAuthException>(action);
        Assert.Equal(404, error.StatusCode);
        Assert.Equal("Private lore is unavailable.", error.Message);
    }

    private static ProblemDetails AssertProblem(ActionResult? result, int status)
    {
        var response = Assert.IsType<ObjectResult>(result);
        Assert.Equal(status, response.StatusCode);
        return Assert.IsType<ProblemDetails>(response.Value);
    }
}

internal sealed class FactionAccessFixture : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "faction-access-" + Guid.NewGuid().ToString("N"));
    private readonly HttpClient _http;
    public CommunityStore Store { get; }
    public AccountService Accounts { get; }
    public BlackLedgerFactionOnboardingService Factions { get; }
    public SyntheticFactionIdentityHandler IdentityHandler { get; } = new();
    public HubIdentityClient Identity { get; }
    public HttpRequest Request { get; } = AuthenticatedRequest();
    public LedgerController Controller { get; }

    public FactionAccessFixture()
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
            ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(_root, "support.json"),
            ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid",
            ["CHUMMER_IDENTITY_SUBJECT_CACHE_SECONDS"] = "300"
        }).Build();
        Store = new(config, NullLogger<CommunityStore>.Instance);
        Accounts = new(Store);
        var spine = new CampaignSpineService(Store, new WorkspaceLifecyclePolicyService(config), new CampaignArtifactRegistryBridge(Store), new SupportStore(config, NullLogger<SupportStore>.Instance));
        Factions = new(config, new BlackLedgerPublicStatsService(), spine, Store);
        _http = new(IdentityHandler);
        Identity = new(_http, config);
        Controller = new(Accounts, Identity, null!, null!, null!, null!, null!, null!, Factions)
        {
            ControllerContext = new ControllerContext { HttpContext = Request.HttpContext }
        };
    }

    public string Snapshot() => JsonSerializer.Serialize(new
    {
        Factions = Store.BlackLedgerFactionOnboardingState,
        Campaigns = Store.CampaignSpinesById,
        Groups = Store.GroupsById
    });

    internal static BlackLedgerCreateFactionRequest Charter() => new(
        "Synthetic Review Cell", "major", "creator_press", ["dispatch_desk", "public_trust"],
        ["overexposed", "thin_resources"], "emerald-core", null, false);

    internal static PrivateLoreOverlayRequest Lore(string factionId) => new(
        "emerald-sprawl-prelude", factionId, new Dictionary<string, string> { ["district"] = "Private synthetic label" }, ["Private synthetic note"]);

    internal static void AddCampaign(CommunityStore store, HubUserDto owner, string campaignId, string? ownerId = null)
    {
        using var scope = store.Enter();
        var now = DateTimeOffset.UtcNow;
        var groupId = "group-" + campaignId;
        store.GroupsById[groupId] = new(groupId, "campaign", "Synthetic campaign", "private", ownerId ?? owner.UserId, [],
            [new("membership-" + campaignId, groupId, owner.UserId, "owner", now)], now, now);
        store.CampaignSpinesById[campaignId] = new(campaignId, groupId, "Synthetic campaign", "active", "private", "Synthetic test",
            new("environment", "campaign", "synthetic", "approved", [], [], []), null, [], [], [], null, now, now);
        store.PersistLocked();
    }

    internal static async Task<BlackLedgerModerationPermission> Permission(CommunityStore store, string subjectId = "independent-reviewer")
    {
        new AccountService(store).EnsureUser(subjectId);
        using var http = new HttpClient(new SyntheticFactionIdentityHandler { SubjectId = subjectId, Roles = ["operator"] });
        var identity = new HubIdentityClient(http, new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid"
        }).Build());
        return await BlackLedgerModerationPermission.RequireAsync(identity, AuthenticatedRequest(), default);
    }

    private static HttpRequest AuthenticatedRequest()
    {
        var request = new DefaultHttpContext().Request;
        request.Headers.Authorization = "Bearer synthetic-faction-session";
        return request;
    }

    public void Dispose()
    {
        _http.Dispose();
        Store.Dispose();
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
    }
}

internal sealed class SyntheticFactionIdentityHandler : HttpMessageHandler
{
    public string SubjectId { get; set; } = "reviewer";
    public IReadOnlyList<string> Roles { get; set; } = ["player"];
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        object payload = request.RequestUri!.AbsolutePath.EndsWith("/introspect", StringComparison.Ordinal)
            ? new IdentityIntrospectionResponse(true, "synthetic-session", SubjectId, Roles, DateTimeOffset.UtcNow.AddHours(1))
            : new IdentitySubjectResponse(SubjectId, "Synthetic user", "synthetic@example.invalid", Roles, DateTimeOffset.UtcNow);
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = JsonContent.Create(payload) });
    }
}
