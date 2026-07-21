using System.Net;
using System.Collections.Immutable;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Campaign.Contracts;
using Chummer.Contracts.Owners;
using Chummer.Contracts.Workspaces;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignCollaborationServiceTests
{
    [Fact]
    public void ControllerContractUsesIdentityAntiforgeryPutAndNoCallerIdentityFields()
    {
        Type controller = typeof(CampaignCollaborationController);
        Assert.NotNull(controller.GetCustomAttribute<AutoValidateAntiforgeryTokenAttribute>());
        Assert.Equal("api/v1/campaigns", controller.GetCustomAttribute<RouteAttribute>()?.Template);
        MethodInfo update = Assert.Single(controller.GetMethods(), method => method.Name == "UpdateSharedSheet");
        Assert.NotNull(update.GetCustomAttribute<HttpPutAttribute>());
        Assert.Null(update.GetCustomAttribute<HttpPatchAttribute>());
        MethodInfo delete = Assert.Single(controller.GetMethods(), method => method.Name == "Delete");
        Assert.Equal("{campaignId}", delete.GetCustomAttribute<HttpDeleteAttribute>()?.Template);

        Type[] identityDerivedRequests =
        [
            typeof(CreateCampaignCollaborationRequest),
            typeof(DeleteCampaignCollaborationRequest),
            typeof(CreateCampaignInviteRequest),
            typeof(RedeemCampaignInviteRequest),
            typeof(RedeemCampaignJoinCodeRequest),
            typeof(CampaignSharedSheetUpdateRequest),
            typeof(CampaignGmAuthorityUpdateRequest),
            typeof(CampaignRunsiteDraftUpdateRequest),
            typeof(PublishCampaignRunsiteRequest)
        ];
        Assert.All(identityDerivedRequests, requestType => Assert.DoesNotContain(
            requestType.GetProperties(BindingFlags.Public | BindingFlags.Instance),
            property => string.Equals(property.Name, "SubjectId", StringComparison.OrdinalIgnoreCase)
                || string.Equals(property.Name, "UserId", StringComparison.OrdinalIgnoreCase)));
    }

    [Fact]
    public void ControllerMapsPreservedReferenceTeardownConflictToAdvertised409()
    {
        using var fixture = new CampaignFixture();
        var controller = new CampaignCollaborationController(
            fixture.Service,
            fixture.Accounts,
            new HubIdentityClient(new HttpClient(), new ConfigurationBuilder().Build()))
        {
            ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() }
        };
        var conflict = new CampaignTeardownConflictException(
            "Campaign teardown refused preserved state.");
        var corruption = new InvalidDataException(
            "Invalid campaign collaboration snapshot: secret internal invariant.");
        MethodInfo isMapped = typeof(CampaignCollaborationController).GetMethod(
            "IsMapped",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("IsMapped was not found.");
        MethodInfo mapException = typeof(CampaignCollaborationController).GetMethod(
            "MapException",
            BindingFlags.NonPublic | BindingFlags.Instance)
            ?? throw new InvalidOperationException("MapException was not found.");

        Assert.True(Assert.IsType<bool>(isMapped.Invoke(null, [conflict])));
        ActionResult result = Assert.IsAssignableFrom<ActionResult>(mapException.Invoke(controller, [conflict]));
        ObjectResult problem = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status409Conflict, problem.StatusCode);
        Assert.False(Assert.IsType<bool>(isMapped.Invoke(null, [corruption])));
        ActionResult corruptionResult = Assert.IsAssignableFrom<ActionResult>(
            mapException.Invoke(controller, [corruption]));
        ObjectResult internalProblem = Assert.IsType<ObjectResult>(corruptionResult);
        Assert.Equal(StatusCodes.Status500InternalServerError, internalProblem.StatusCode);
        Assert.DoesNotContain(
            "secret internal invariant",
            JsonSerializer.Serialize(internalProblem.Value),
            StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("/api/v1/campaigns")]
    [InlineData("/api/v1/campaigns/campaign-1/sheets/dossier-1")]
    [InlineData("/api/v1/antiforgery")]
    [InlineData("/join/campaign/invite-1")]
    public void CollaborationRoutesRequirePrivateNoReferrerPolicy(string path)
    {
        Assert.True(CampaignCollaborationRoutePrivacyPolicy.RequiresPrivateHeaders(new PathString(path)));
        Assert.False(CampaignCollaborationRoutePrivacyPolicy.RequiresPrivateHeaders(new PathString("/downloads")));
    }

    [Fact]
    public async Task AntiforgeryEndpointAuthenticatesThenGetsAndStoresTokenWithPrivateHeaders()
    {
        using var fixture = new CampaignFixture();
        var antiforgery = new RecordingAntiforgery();
        IConfiguration identityConfiguration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = "local-token",
                ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.antiforgery",
                ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Token User"
            })
            .Build();
        var identity = new HubIdentityClient(new HttpClient(), identityConfiguration);
        var controller = new AntiforgeryController(antiforgery, fixture.Accounts, identity)
        {
            ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() }
        };
        controller.HttpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
        controller.Request.Host = new HostString("localhost");
        controller.Request.Headers.Authorization = "Bearer local-token";

        ActionResult<AntiforgeryTokenProjection> action = await controller.Get(CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(action.Result);
        AntiforgeryTokenProjection projection = Assert.IsType<AntiforgeryTokenProjection>(ok.Value);
        Assert.Equal("request-token", projection.RequestToken);
        Assert.Equal("X-CSRF-TOKEN", projection.HeaderName);
        Assert.True(antiforgery.GetAndStoreCalled);
        Assert.Contains(fixture.Store.UsersById.Values, user => user.SubjectId == "subject.antiforgery");
        Assert.Contains("no-store", controller.Response.Headers.CacheControl.ToString(), StringComparison.OrdinalIgnoreCase);
        Assert.Equal("no-referrer", controller.Response.Headers["Referrer-Policy"].ToString());
    }

    [Fact]
    public async Task AntiforgeryEndpointDoesNotIssueTokenBeforeAuthentication()
    {
        using var fixture = new CampaignFixture();
        var antiforgery = new RecordingAntiforgery();
        var identity = new HubIdentityClient(new HttpClient(), new ConfigurationBuilder().Build());
        var controller = new AntiforgeryController(antiforgery, fixture.Accounts, identity)
        {
            ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() }
        };

        ActionResult<AntiforgeryTokenProjection> action = await controller.Get(CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(action.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
        Assert.False(antiforgery.GetAndStoreCalled);
        Assert.Contains("no-store", controller.Response.Headers.CacheControl.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InviteSecretsAreStrongHashedIndexedAndNeverPersistedInPlaintext()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();

        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            InviteRequest(ExpiresInMinutes: 60, MaxUses: 2));

        CampaignCollaborationInviteState state = Assert.Single(fixture.Store.CampaignCollaborationInvitesById.Values);
        Assert.Equal(64, state.LinkSecretSha256.Length);
        Assert.Equal(64, state.ShortCodeSha256.Length);
        Assert.Equal(64, state.ShortCodeLookupSha256.Length);
        Assert.Equal(state.InviteId, fixture.Store.CampaignInviteIdByCodeLookupSha256[state.ShortCodeLookupSha256]);
        Assert.DoesNotContain(invite.LinkSecret, state.LinkSecretSha256, StringComparison.Ordinal);
        Assert.DoesNotContain(invite.ShortCode, state.ShortCodeSha256, StringComparison.Ordinal);
        Assert.StartsWith($"/join/campaign/{invite.InviteId}#secret=", invite.JoinPath, StringComparison.Ordinal);
        Assert.True(Convert.FromBase64String(PadBase64Url(invite.LinkSecret)).Length >= 32);

        string persisted = File.ReadAllText(fixture.StorePath);
        Assert.DoesNotContain(invite.LinkSecret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(invite.ShortCode, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(invite.ShortCode.Replace("-", string.Empty, StringComparison.Ordinal), persisted, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignCreationIsDurablyIdempotentAndRejectsKeyReuseForChangedPayload()
    {
        using var fixture = new CampaignFixture();
        CreateCampaignCollaborationRequest request = CampaignRequest(
            "Response Safe Campaign",
            "Campaign creation response-loss test.",
            "private",
            "Opening Run",
            "campaign-create-response-loss");

        CampaignCollaborationProjection first = fixture.Service.CreateCampaign(fixture.Gm, request);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("replay must not persist");
        CampaignCollaborationProjection replay = fixture.Service.CreateCampaign(fixture.Gm, request);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;

        Assert.Equal(first, replay);
        Assert.Single(fixture.Store.CampaignSpinesById);
        Assert.Single(fixture.Store.CampaignCreationsByIdempotencyKey);
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.CreateCampaign(
            fixture.Gm,
            request with { Name = "Changed Campaign" }));

        var reloadedStore = new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        IDataProtectionProvider reloadedProtection = DataProtectionProvider.Create(
            new DirectoryInfo(fixture.DataProtectionPath));
        var reloadedService = new CampaignCollaborationService(
            reloadedStore,
            new RecordingCanonicalGmCharacterEditGateway(reloadedStore, fixture.Clock),
            reloadedProtection,
            fixture.Clock);

        Assert.Equal(
            JsonSerializer.Serialize(first),
            JsonSerializer.Serialize(reloadedService.CreateCampaign(fixture.Gm, request)));
        Assert.Single(reloadedStore.CampaignSpinesById);
        Assert.Single(reloadedStore.CampaignCreationsByIdempotencyKey);
    }

    [Fact]
    public void InviteCreationReplaySurvivesRestartWithoutPersistingOrProjectingSecrets()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CreateCampaignInviteRequest request = InviteRequest(
            ExpiresInMinutes: 60,
            MaxUses: 2,
            IdempotencyKey: "invite-create-response-loss");

        CampaignInviteSecretProjection first = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            request);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("replay must not persist");
        CampaignInviteSecretProjection replay = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId.ToUpperInvariant(),
            request);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;

        Assert.Equal(first, replay);
        Assert.Single(fixture.Store.CampaignCollaborationInvitesById);
        CampaignInviteCreationIdempotencyState replayState =
            Assert.Single(fixture.Store.CampaignInviteCreationsByIdempotencyKey.Values);
        Assert.DoesNotContain(
            replayState.GetType().GetProperties(),
            property => property.Name.Contains("LinkSecret", StringComparison.OrdinalIgnoreCase)
                || property.Name.Contains("ShortCode", StringComparison.OrdinalIgnoreCase));
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            request with { MaxUses = 3 }));

        string persisted = File.ReadAllText(fixture.StorePath);
        Assert.DoesNotContain(first.LinkSecret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(first.ShortCode, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(
            first.ShortCode.Replace("-", string.Empty, StringComparison.Ordinal),
            persisted,
            StringComparison.Ordinal);

        var reloadedStore = new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        IDataProtectionProvider reloadedProtection = DataProtectionProvider.Create(
            new DirectoryInfo(fixture.DataProtectionPath));
        var reloadedService = new CampaignCollaborationService(
            reloadedStore,
            new RecordingCanonicalGmCharacterEditGateway(reloadedStore, fixture.Clock),
            reloadedProtection,
            fixture.Clock);
        CampaignInviteSecretProjection restartedReplay = reloadedService.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            request);

        Assert.Equal(first, restartedReplay);
        Assert.Single(reloadedStore.CampaignCollaborationInvitesById);
        Assert.Single(reloadedStore.CampaignInviteCreationsByIdempotencyKey);
        HubUserDto player = fixture.CreateUser("subject.invite-replay-player", "Invite Replay Player");
        Assert.Throws<KeyNotFoundException>(() => reloadedService.CreateInvite(
            player,
            campaign.CampaignId,
            request));

        fixture.Clock.Advance(TimeSpan.FromDays(8));
        CampaignInviteSecretProjection afterRetention = reloadedService.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            request);
        Assert.NotEqual(first.InviteId, afterRetention.InviteId);
        Assert.NotEqual(first.LinkSecret, afterRetention.LinkSecret);
        Assert.Single(reloadedStore.CampaignCollaborationInvitesById);
        Assert.Single(reloadedStore.CampaignInviteCreationsByIdempotencyKey);
    }

    [Fact]
    public void RedemptionBindsSelectedExistingOwnerDossierWithoutCreatingPlaceholderAndIsIdempotent()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            InviteRequest(60, 1));
        HubUserDto player = fixture.CreateUser("subject.player-a", "Player A");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        int dossierCountBefore = fixture.Store.DossiersById.Count;
        var request = fixture.LinkRequest(invite, character, "join-a");

        CampaignInviteRedemptionProjection first = fixture.Service.RedeemInvite(player, invite.InviteId, request);
        CampaignInviteRedemptionProjection replay = fixture.Service.RedeemInvite(player, invite.InviteId, request);
        CampaignCollaborationProjection playerCampaign = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(player, campaign.CampaignId));

        Assert.Equal("gm_owner", campaign.Role);
        Assert.Equal("player", playerCampaign.Role);
        Assert.False(first.AlreadyJoined);
        Assert.True(replay.AlreadyJoined);
        Assert.Equal(character.DossierId, first.DossierId);
        Assert.Equal("hub_runner_dossier", first.Binding.AuthorityKind);
        Assert.Equal(character.DossierId, first.Binding.AuthoritativeCharacterId);
        Assert.Equal(player.UserId, Assert.Single(fixture.Store.CampaignCharacterBindings).AuthenticatedOwnerUserId);
        Assert.Equal("gm_character_editor", first.Binding.GmAuthorityRole);
        Assert.Equal("player", first.Role);
        Assert.Equal(dossierCountBefore, fixture.Store.DossiersById.Count);
        Assert.Equal(1, fixture.Store.CampaignCollaborationInvitesById[invite.InviteId].Uses);
        Assert.Single(fixture.Store.CampaignCharacterBindings);
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            request with { DossierId = "dossier-different" }));
        Assert.Throws<CampaignInviteRejectedException>(() => fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            request with { IdempotencyKey = "join-a-new-command" }));

        HubUserDto playerB = fixture.CreateUser("subject.player-b", "Player B");
        RunnerDossierProjection characterB = fixture.CreateCharacter(playerB, "Cipher", "Blake Cipher");
        Assert.Throws<CampaignInviteRejectedException>(() => fixture.Service.RedeemInvite(
            playerB,
            invite.InviteId,
            fixture.LinkRequest(invite, characterB, "join-b")));
        Assert.DoesNotContain(fixture.Store.GroupsById[campaign.GroupId].Memberships, item => item.UserId == playerB.UserId);

        fixture.Store.DossiersById[character.DossierId] = character with { OwnerUserId = playerB.UserId };
        Assert.Throws<CampaignInviteRejectedException>(() => fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            request));
    }

    [Fact]
    public void RedemptionRejectsForeignOrMissingDossierWithoutMutatingCampaignAuthority()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            InviteRequest(60, 2));
        HubUserDto playerA = fixture.CreateUser("subject.player-a", "Player A");
        HubUserDto playerB = fixture.CreateUser("subject.player-b", "Player B");
        RunnerDossierProjection foreign = fixture.CreateCharacter(playerB, "Cipher", "Blake Cipher");

        Assert.Throws<CampaignInviteRejectedException>(() => fixture.Service.RedeemInvite(
            playerA,
            invite.InviteId,
            new RedeemCampaignInviteRequest(invite.LinkSecret, foreign.DossierId, foreign.DossierId, 1, true, "foreign")));

        Assert.DoesNotContain(fixture.Store.GroupsById[campaign.GroupId].Memberships, item => item.UserId == playerA.UserId);
        Assert.Empty(fixture.Store.CampaignCharacterBindings);
        Assert.Empty(fixture.Store.CrewsById[campaign.CrewId].Members);
        Assert.Equal(0, fixture.Store.CampaignCollaborationInvitesById[invite.InviteId].Uses);
    }

    [Fact]
    public void JoinCodeSupportsMutualPlayerSafeReadsWithoutIdor()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            InviteRequest(60, 2));
        HubUserDto playerA = fixture.CreateUser("subject.player-a", "Player A");
        HubUserDto playerB = fixture.CreateUser("subject.player-b", "Player B");
        HubUserDto outsider = fixture.CreateUser("subject.outsider", "Outsider");
        RunnerDossierProjection characterA = fixture.CreateCharacter(playerA, "Razor", "Alex Razor");
        RunnerDossierProjection characterB = fixture.CreateCharacter(playerB, "Cipher", "Blake Cipher");

        CampaignInviteRedemptionProjection joinedA = fixture.Service.RedeemJoinCode(
            playerA,
            fixture.CodeRequest(invite, characterA, "code-a"));
        CampaignInviteRedemptionProjection joinedB = fixture.Service.RedeemJoinCode(
            playerB,
            fixture.CodeRequest(invite, characterB, "code-b") with { Code = invite.ShortCode.ToLowerInvariant() });

        CampaignPlayerSafeSheetProjection otherSheet = fixture.Service.GetSharedSheet(playerA, campaign.CampaignId, joinedB.DossierId);
        Assert.Equal("Cipher", otherSheet.RunnerHandle);
        Assert.DoesNotContain(JsonSerializer.Serialize(otherSheet), playerB.SubjectId, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(2, fixture.Service.GetRoster(playerA, campaign.CampaignId).Count);
        Assert.Null(fixture.Service.GetCampaign(outsider, campaign.CampaignId));
        Assert.Throws<KeyNotFoundException>(() => fixture.Service.GetSharedSheet(outsider, campaign.CampaignId, joinedA.DossierId));
    }

    [Fact]
    public void PlayerSheetProjectionSanitizesCanonicalDossierMetadata()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        lock (fixture.Store.Gate)
        {
            fixture.Store.DossiersById[character.DossierId] = character with
            {
                Projections =
                [
                    new PublicationSafeProjection(
                        "identity",
                        "identity",
                        "Identity",
                        "Player-safe summary.",
                        ArtifactId: "private-artifact",
                        Audience: "private",
                        OwnershipSummary: player.UserId,
                        PublicationState: "draft",
                        TrustBand: "internal",
                        Discoverable: true,
                        AuditSummary: "private audit")
                ]
            };
            fixture.Store.PersistLocked();
        }

        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(60, 1));
        fixture.Service.RedeemInvite(player, invite.InviteId, fixture.LinkRequest(invite, character, "sanitize"));
        PublicationSafeProjection section = Assert.Single(
            fixture.Service.GetSharedSheet(player, campaign.CampaignId, character.DossierId).Sections);
        Assert.Null(section.ArtifactId);
        Assert.Null(section.OwnershipSummary);
        Assert.Null(section.AuditSummary);
        Assert.Equal("campaign", section.Audience);
        Assert.Equal("player_safe", section.PublicationState);
        Assert.False(section.Discoverable);
    }

    [Fact]
    public void ExpiredRevokedMalformedAndUnknownInvitesShareGenericFailure()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        CampaignInviteSecretProjection expired = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            InviteRequest(5, 1));
        fixture.Clock.Advance(TimeSpan.FromMinutes(6));

        CampaignInviteRejectedException expiredError = Assert.Throws<CampaignInviteRejectedException>(() =>
            fixture.Service.RedeemInvite(player, expired.InviteId, fixture.LinkRequest(expired, character, "expired")));
        CampaignInviteSecretProjection revoked = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            InviteRequest(60, 1));
        fixture.Service.RevokeInvite(fixture.Gm, campaign.CampaignId, revoked.InviteId);
        CampaignInviteRejectedException revokedError = Assert.Throws<CampaignInviteRejectedException>(() =>
            fixture.Service.RedeemInvite(player, revoked.InviteId, fixture.LinkRequest(revoked, character, "revoked")));
        CampaignInviteRejectedException unknownError = Assert.Throws<CampaignInviteRejectedException>(() =>
            fixture.Service.RedeemInvite(
                player,
                revoked.InviteId,
                fixture.LinkRequest(revoked, character, "unknown") with { Secret = "wrong-but-well-formed" }));

        Assert.Equal("Campaign invite is invalid or unavailable.", expiredError.Message);
        Assert.Equal(expiredError.Message, revokedError.Message);
        Assert.Equal(revokedError.Message, unknownError.Message);
    }

    [Fact]
    public void InviteRedemptionThrottlesRepeatedFailuresAndRecoversAfterWindow()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(60, 1));
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        RedeemCampaignInviteRequest request = fixture.LinkRequest(invite, character, "throttle") with { Secret = "wrong-secret" };
        for (int attempt = 0; attempt < 10; attempt++)
        {
            Assert.Throws<CampaignInviteRejectedException>(() => fixture.Service.RedeemInvite(player, invite.InviteId, request));
        }

        Assert.Throws<CampaignInviteThrottledException>(() => fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            fixture.LinkRequest(invite, character, "valid-after-throttle")));
        fixture.Clock.Advance(TimeSpan.FromMinutes(11));
        CampaignInviteRedemptionProjection joined = fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            fixture.LinkRequest(invite, character, "valid-after-window"));
        Assert.Equal(character.DossierId, joined.DossierId);
    }

    [Fact]
    public void GmPutEditsCanonicalDossierWithCasAuditAuthorityAndIdempotency()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        var request = new CampaignSharedSheetUpdateRequest(
            ExpectedRevision: 1,
            IdempotencyKey: "edit-1",
            RunnerHandle: "Razor-2",
            DisplayName: "Alex Razor",
            Status: "active",
            Reason: "Agreed table correction.");

        CampaignSharedSheetEditReceipt receipt = fixture.Service.UpdateSharedSheet(
            fixture.Gm, campaign.CampaignId, joined.DossierId, request);
        CampaignSharedSheetEditReceipt replay = fixture.Service.UpdateSharedSheet(
            fixture.Gm, campaign.CampaignId, joined.DossierId, request);

        Assert.Equal(receipt, replay);
        Assert.Equal(2, receipt.Revision);
        Assert.Equal(1, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal(1, fixture.CanonicalEdits.CallCount);
        Assert.StartsWith("gm-edit-", receipt.ReceiptId, StringComparison.Ordinal);
        DelegatedGmCharacterEditCommand canonicalCommand = Assert.Single(fixture.CanonicalEdits.Commands);
        Assert.Equal(campaign.CampaignId, canonicalCommand.CampaignId);
        Assert.Equal(fixture.Gm.UserId, canonicalCommand.ActorId);
        Assert.Equal(player.UserId, canonicalCommand.CharacterOwner.Value);
        Assert.Equal(joined.Binding.AuthoritativeCharacterId, canonicalCommand.CharacterId.Value);
        Assert.Equal(
            "Razor-2",
            Assert.Single(canonicalCommand.Operations, operation =>
                operation.Path == DelegatedGmCharacterEditContract.ProfileAliasPath).Value);
        Assert.Equal(
            "Alex Razor",
            Assert.Single(canonicalCommand.Operations, operation =>
                operation.Path == DelegatedGmCharacterEditContract.ProfileNamePath).Value);
        Assert.DoesNotContain(
            typeof(DelegatedGmCharacterEditCommand).GetProperties(),
            property => property.Name is "Status" or "Sections" or "Balance" or "Quota");
        Assert.Equal("Razor-2", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        CampaignPlayerSafeSheetProjection persistedProjection = fixture.Service.GetSharedSheet(
            fixture.Gm, campaign.CampaignId, joined.DossierId);
        Assert.Equal("Razor-2", persistedProjection.RunnerHandle);
        Assert.Equal(
            receipt.AfterSha256,
            Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(
                persistedProjection,
                new JsonSerializerOptions(JsonSerializerDefaults.Web)))).ToLowerInvariant());
        Assert.Single(fixture.Store.CampaignCharacterBindings);
        Assert.Single(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            request with { RunnerHandle = "Different" }));
        Assert.Throws<CampaignCanonicalEditConflictException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            request with { IdempotencyKey = "edit-stale" }));
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.UpdateSharedSheet(
            player,
            campaign.CampaignId,
            joined.DossierId,
            request with { ExpectedRevision = 2, IdempotencyKey = "self-edit" }));
    }

    [Fact]
    public void HubIdempotencyReplayReadsLaterOwnerProfileWithoutReapplyingGmEdit()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(
            campaign,
            player,
            "Razor",
            "Alex Razor");
        var request = new CampaignSharedSheetUpdateRequest(
            1,
            "stored-replay-owner-wins",
            "GM Razor",
            "GM Alex",
            "active",
            "Prove replay never rolls back a later owner edit.");

        CampaignSharedSheetEditReceipt applied = fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            request);
        DelegatedGmCharacterProfile ownerProfile = fixture.CanonicalEdits.ApplyOwnerEdit(
            player.UserId,
            joined.Binding.AuthoritativeCharacterId,
            "Owner Razor",
            "Owner Alex");

        CampaignSharedSheetEditReceipt replay = fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            request);
        CampaignPlayerSafeSheetProjection current = fixture.Service.GetSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId);

        Assert.Equal(applied.Revision, replay.Revision);
        Assert.Equal(ownerProfile.Revision, replay.CurrentRevision);
        Assert.Equal(ownerProfile.Revision, current.Revision);
        Assert.Equal("Owner Razor", current.RunnerHandle);
        Assert.Equal("Owner Alex", current.DisplayName);
        Assert.Equal(1, fixture.CanonicalEdits.CallCount);
        Assert.Equal(1, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal(3, fixture.CanonicalEdits.ReadCount);
        Assert.Single(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
    }

    [Fact]
    public void StoreAuthorizerRechecksCurrentManagerOwnerGrantAndBindingOnEveryDecision()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(
            campaign,
            player,
            "Razor",
            "Alex Razor");
        var authorizer = new CommunityStoreCampaignGmCharacterEditAuthorizer(
            fixture.Store,
            fixture.Clock);
        var request = new CampaignGmCharacterEditAuthorizationRequest(
            campaign.CampaignId,
            fixture.Gm.UserId,
            new OwnerScope(player.UserId),
            new CharacterWorkspaceId(joined.Binding.AuthoritativeCharacterId),
            ImmutableArray.Create(
                DelegatedGmCharacterEditContract.ProfileAliasPath,
                DelegatedGmCharacterEditContract.ProfileNamePath));

        CampaignGmCharacterEditAuthorization granted = authorizer.Authorize(request);
        CampaignCharacterBindingState binding = Assert.Single(
            fixture.Store.CampaignCharacterBindings);

        Assert.True(granted.Authorized);
        Assert.Equal(binding.BindingId, granted.DelegationId);
        Assert.Equal(binding.BindingVersionId, granted.AuthorityReceiptId);
        Assert.Equal(binding.BindingRevision, granted.AuthorityRevision);
        Assert.Equal(player.UserId, granted.GrantedByCharacterOwnerId);
        Assert.False(authorizer.Authorize(request with { ActorId = player.UserId }).Authorized);
        Assert.False(authorizer.Authorize(request with
        {
            RequestedPatchPaths = ImmutableArray.Create(
                DelegatedGmCharacterEditContract.ProfileNotesPath)
        }).Authorized);

        _ = fixture.Service.UpdateGmAuthority(
            player,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignGmAuthorityUpdateRequest(
                joined.Binding.BindingRevision,
                GrantGmEditAuthority: false,
                IdempotencyKey: "revoke-before-next-core-call",
                Reason: "Character owner revoked GM edit authority."));

        Assert.False(authorizer.Authorize(request).Authorized);
    }

    [Fact]
    public void PackageGatewayRegistrationIsUnavailableWithoutPathAndRejectsBlankConfiguration()
    {
        using var fixture = new CampaignFixture();
        ServiceProvider unavailableProvider = BuildCampaignGatewayProvider(
            fixture.Store,
            fixture.Clock,
            new ConfigurationBuilder().Build());
        using (unavailableProvider)
        {
            Assert.IsType<UnavailableCoreGmCharacterEditGateway>(
                unavailableProvider.GetRequiredService<ICoreGmCharacterEditGateway>());
        }

        IConfiguration blankConfiguration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Chummer:CoreGmCharacterEdits:WorkspaceStorePath"] = " "
            })
            .Build();
        using ServiceProvider blankProvider = BuildCampaignGatewayProvider(
            fixture.Store,
            fixture.Clock,
            blankConfiguration);
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            blankProvider.GetRequiredService<ICoreGmCharacterEditGateway>());
        Assert.Contains("cannot be blank", exception.Message, StringComparison.Ordinal);

        string coreStorePath = Path.Combine(
            Path.GetDirectoryName(fixture.StorePath)!,
            "core-workspaces");
        Directory.CreateDirectory(coreStorePath);
        IConfiguration configured = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Chummer:CoreGmCharacterEdits:WorkspaceStorePath"] = coreStorePath
            })
            .Build();
        using ServiceProvider configuredProvider = BuildCampaignGatewayProvider(
            fixture.Store,
            fixture.Clock,
            configured);
        ICoreGmCharacterEditGateway configuredGateway =
            configuredProvider.GetRequiredService<ICoreGmCharacterEditGateway>();
        Assert.IsNotType<UnavailableCoreGmCharacterEditGateway>(configuredGateway);
        Assert.Equal(
            "Chummer.Application.Workspaces.DelegatedGmCharacterEditService",
            configuredGateway.GetType().FullName);
    }

    [Fact]
    public void UnsupportedStatusAndSectionMutationsFailBeforeCanonicalEdit()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        var request = new CampaignSharedSheetUpdateRequest(
            1,
            "unsupported-status",
            "Razor-2",
            "Alex Razor",
            "archived",
            "Attempt unsupported status mutation.");

        Assert.Throws<ArgumentException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            request));
        Assert.Throws<ArgumentException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            request with
            {
                IdempotencyKey = "unsupported-sections",
                Status = "active",
                Sections = [new PublicationSafeProjection("identity", "identity", "Identity", "Changed outside Core.")]
            }));

        Assert.Equal(0, fixture.CanonicalEdits.CallCount);
        Assert.Equal("Razor", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        Assert.Empty(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
    }

    [Fact]
    public void StaleRevisionIsDecidedByCanonicalCoreWithoutApplyingAnEdit()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");

        CampaignCanonicalEditConflictException conflict = Assert.Throws<CampaignCanonicalEditConflictException>(() =>
            fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(
                2,
                "stale-before-core",
                "Razor-2",
                "Alex Razor",
                "active",
                "Stale command.")));

        Assert.Equal(1, conflict.CurrentRevision);
        Assert.Equal(2, fixture.CanonicalEdits.ReadCount);
        Assert.Equal(1, fixture.CanonicalEdits.CallCount);
        Assert.Equal(0, fixture.CanonicalEdits.ApplyCount);
        Assert.Empty(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
    }

    [Fact]
    public void CanonicalConflictSynchronizesLaterOwnerProfileWithoutRewritingConsent()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        CampaignCharacterBindingState consentBefore = Assert.Single(fixture.Store.CampaignCharacterBindings);
        DelegatedGmCharacterProfile ownerProfile = fixture.CanonicalEdits.ApplyOwnerEdit(
            player.UserId,
            joined.Binding.AuthoritativeCharacterId,
            "Owner Razor",
            "Owner Alex");

        CampaignCanonicalEditConflictException conflict = Assert.Throws<CampaignCanonicalEditConflictException>(() =>
            fixture.Service.UpdateSharedSheet(
                fixture.Gm,
                campaign.CampaignId,
                joined.DossierId,
                new CampaignSharedSheetUpdateRequest(
                    1,
                    "owner-won-race",
                    "GM Razor",
                    "GM Alex",
                    "active",
                    "Do not overwrite the owner's later edit.")));

        CampaignPlayerSafeSheetProjection current = fixture.Service.GetSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId);
        CampaignCharacterBindingState consentAfter = Assert.Single(fixture.Store.CampaignCharacterBindings);
        Assert.Equal(ownerProfile.Revision, conflict.CurrentRevision);
        Assert.Equal(ownerProfile.Revision, current.Revision);
        Assert.Equal("Owner Razor", current.RunnerHandle);
        Assert.Equal("Owner Alex", current.DisplayName);
        Assert.Equal(consentBefore.BindingId, consentAfter.BindingId);
        Assert.Equal(consentBefore.BindingVersionId, consentAfter.BindingVersionId);
        Assert.Equal(consentBefore.BindingRevision, consentAfter.BindingRevision);
        Assert.Equal(consentBefore.RecordedAtUtc, consentAfter.RecordedAtUtc);
        Assert.Equal(1, fixture.CanonicalEdits.CallCount);
        Assert.Equal(0, fixture.CanonicalEdits.ApplyCount);
        Assert.Empty(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
    }

    [Fact]
    public void CrossCampaignGmAndCharacterBindingsFailBeforeCanonicalEdit()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection firstCampaign = fixture.CreateCampaign("First");
        HubUserDto secondGm = fixture.CreateUser("subject.gm-two", "Second GM");
        CampaignCollaborationProjection secondCampaign = fixture.Service.CreateCampaign(
            secondGm,
            CampaignRequest("Second"));
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        CampaignInviteSecretProjection firstInvite = fixture.Service.CreateInvite(
            fixture.Gm,
            firstCampaign.CampaignId,
            InviteRequest(60, 1));
        CampaignInviteRedemptionProjection firstJoined = fixture.Service.RedeemInvite(
            player,
            firstInvite.InviteId,
            fixture.LinkRequest(firstInvite, character, "join-first"));
        CampaignInviteSecretProjection secondInvite = fixture.Service.CreateInvite(
            secondGm,
            secondCampaign.CampaignId,
            InviteRequest(60, 1));
        _ = fixture.Service.RedeemInvite(
            player,
            secondInvite.InviteId,
            fixture.LinkRequest(secondInvite, character, "join-second"));
        RunnerDossierProjection unboundCharacter = fixture.CreateCharacter(player, "Ghost", "Ghost Runner");
        var edit = new CampaignSharedSheetUpdateRequest(
            1,
            "cross-scope",
            "Razor-2",
            "Alex Razor",
            "active",
            "Cross-scope attempt.");

        Assert.Throws<KeyNotFoundException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            secondCampaign.CampaignId,
            firstJoined.DossierId,
            edit));
        Assert.Throws<KeyNotFoundException>(() => fixture.Service.UpdateSharedSheet(
            secondGm,
            firstCampaign.CampaignId,
            firstJoined.DossierId,
            edit));
        Assert.Throws<KeyNotFoundException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            firstCampaign.CampaignId,
            unboundCharacter.DossierId,
            edit));

        Assert.Equal(0, fixture.CanonicalEdits.CallCount);
        Assert.Empty(fixture.Service.GetSharedSheetAuditForTests(firstJoined.DossierId));
    }

    [Fact]
    public void CoreFailureDoesNotCreateFalseHubSuccess()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        int bindingCount = fixture.Store.CampaignCharacterBindings.Count;
        fixture.CanonicalEdits.ForcedOutcome = DelegatedGmCharacterEditOutcome.Unavailable;

        Assert.Throws<CampaignCanonicalEditUnavailableException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(
                1,
                "core-unavailable",
                "Razor-2",
                "Alex Razor",
                "active",
                "Core unavailable.")));

        Assert.Equal(1, fixture.CanonicalEdits.CallCount);
        Assert.Equal(0, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal(bindingCount, fixture.Store.CampaignCharacterBindings.Count);
        Assert.Equal("Razor", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        Assert.Empty(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
        Assert.Empty(fixture.Store.CampaignSheetEditsByIdempotencyKey);
    }

    [Fact]
    public void InvalidCoreReceiptDoesNotCreateFalseHubSuccess()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        fixture.CanonicalEdits.ReceiptMutator = receipt => receipt with
        {
            CommandSha256 = new string('0', 64)
        };

        Assert.Throws<CampaignCanonicalEditUnavailableException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(
                1,
                "invalid-core-receipt",
                "Razor-2",
                "Alex Razor",
                "active",
                "Reject forged canonical receipt.")));

        Assert.Equal(1, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal("Razor", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        Assert.Empty(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
        Assert.Empty(fixture.Store.CampaignSheetEditsByIdempotencyKey);
    }

    [Fact]
    public void HubPersistenceFailureRetriesCoreIdempotentlyAndRecoversProjection()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        var edit = new CampaignSharedSheetUpdateRequest(
            1,
            "persist-recovery",
            "Razor Recovered",
            "Alex Razor",
            "active",
            "Recover projection after Hub persistence failure.");
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("injected sheet persistence failure");

        Assert.Throws<IOException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            edit));
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;
        Assert.Equal(1, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal("Razor", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        Assert.Empty(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
        Assert.Empty(fixture.Store.CampaignSheetEditsByIdempotencyKey);

        CampaignSharedSheetEditReceipt recovered = fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            edit);

        Assert.Equal(2, fixture.CanonicalEdits.CallCount);
        Assert.Equal(1, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal(2, recovered.Revision);
        Assert.Equal("Razor Recovered", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        Assert.Single(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
        Assert.Single(fixture.Store.CampaignSheetEditsByIdempotencyKey);
    }

    [Fact]
    public void ReplayAfterLaterOwnerEditReconcilesCurrentProfileWithoutRollingItBack()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        var edit = new CampaignSharedSheetUpdateRequest(
            1,
            "persist-owner-recovery",
            "GM Razor",
            "GM Alex",
            "active",
            "Recover a committed GM edit without replacing a later owner edit.");
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("injected sheet persistence failure");

        Assert.Throws<IOException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            edit));
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;
        DelegatedGmCharacterProfile ownerProfile = fixture.CanonicalEdits.ApplyOwnerEdit(
            player.UserId,
            joined.Binding.AuthoritativeCharacterId,
            "Owner Razor",
            "Owner Alex");

        CampaignSharedSheetEditReceipt recovered = fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            edit);
        CampaignPlayerSafeSheetProjection current = fixture.Service.GetSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId);

        Assert.Equal(2, recovered.Revision);
        Assert.Equal(ownerProfile.Revision, recovered.CurrentRevision);
        Assert.Equal(3, current.Revision);
        Assert.Equal("Owner Razor", current.RunnerHandle);
        Assert.Equal("Owner Alex", current.DisplayName);
        Assert.Equal(2, fixture.CanonicalEdits.CallCount);
        Assert.Equal(1, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal(
            recovered.AfterSha256,
            Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(
                current,
                new JsonSerializerOptions(JsonSerializerDefaults.Web)))).ToLowerInvariant());
        Assert.Single(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
        Assert.Single(fixture.Store.CampaignSheetEditsByIdempotencyKey);
    }

    [Fact]
    public void CanonicalEditSynchronizesEveryCampaignWithoutChangingOwnerConsentVersions()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection firstCampaign = fixture.CreateCampaign("First");
        HubUserDto secondGm = fixture.CreateUser("subject.gm-two", "Second GM");
        CampaignCollaborationProjection secondCampaign = fixture.Service.CreateCampaign(
            secondGm,
            CampaignRequest("Second"));
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        CampaignInviteSecretProjection firstInvite = fixture.Service.CreateInvite(
            fixture.Gm,
            firstCampaign.CampaignId,
            InviteRequest(60, 1));
        CampaignInviteRedemptionProjection firstJoined = fixture.Service.RedeemInvite(
            player,
            firstInvite.InviteId,
            fixture.LinkRequest(firstInvite, character, "join-first-consent"));
        CampaignInviteSecretProjection secondInvite = fixture.Service.CreateInvite(
            secondGm,
            secondCampaign.CampaignId,
            InviteRequest(60, 1));
        _ = fixture.Service.RedeemInvite(
            player,
            secondInvite.InviteId,
            fixture.LinkRequest(secondInvite, character, "join-second-consent"));
        var before = fixture.Store.CampaignCharacterBindings
            .Where(binding => string.Equals(binding.DossierId, character.DossierId, StringComparison.OrdinalIgnoreCase))
            .ToDictionary(binding => binding.CampaignId, StringComparer.OrdinalIgnoreCase);

        CampaignSharedSheetEditReceipt receipt = fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            firstCampaign.CampaignId,
            firstJoined.DossierId,
            new CampaignSharedSheetUpdateRequest(
                1,
                "cross-campaign-profile-sync",
                "Razor Shared",
                "Alex Shared",
                "active",
                "Synchronize canonical profile without rewriting consent."));

        var after = fixture.Store.CampaignCharacterBindings
            .Where(binding => string.Equals(binding.DossierId, character.DossierId, StringComparison.OrdinalIgnoreCase))
            .ToDictionary(binding => binding.CampaignId, StringComparer.OrdinalIgnoreCase);
        Assert.Equal(before.Count, after.Count);
        Assert.Equal(2, receipt.CurrentRevision);
        foreach ((string campaignId, CampaignCharacterBindingState beforeBinding) in before)
        {
            CampaignCharacterBindingState afterBinding = after[campaignId];
            Assert.Equal(beforeBinding.BindingId, afterBinding.BindingId);
            Assert.Equal(beforeBinding.BindingVersionId, afterBinding.BindingVersionId);
            Assert.Equal(beforeBinding.BindingRevision, afterBinding.BindingRevision);
            Assert.Equal(beforeBinding.GmAuthorityRole, afterBinding.GmAuthorityRole);
            Assert.Equal(beforeBinding.GrantedByUserId, afterBinding.GrantedByUserId);
            Assert.Equal(beforeBinding.GrantedAtUtc, afterBinding.GrantedAtUtc);
            Assert.Equal(beforeBinding.RecordedAtUtc, afterBinding.RecordedAtUtc);
            Assert.Equal(2, afterBinding.CurrentRevision);
        }

        CampaignPlayerSafeSheetProjection secondSheet = fixture.Service.GetSharedSheet(
            secondGm,
            secondCampaign.CampaignId,
            character.DossierId);
        Assert.Equal(2, secondSheet.Revision);
        Assert.Equal("Razor Shared", secondSheet.RunnerHandle);
        Assert.Equal("Alex Shared", secondSheet.DisplayName);
    }

    [Fact]
    public void DefaultPackageGatewayFailsClosedWithoutMutatingHubProjection()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        var failClosedService = new CampaignCollaborationService(fixture.Store);

        Assert.Throws<CampaignCanonicalEditUnavailableException>(() => failClosedService.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(
                1,
                "missing-package",
                "Razor-2",
                "Alex Razor",
                "active",
                "Package adapter not installed.")));

        Assert.Equal("Razor", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        Assert.Empty(failClosedService.GetSharedSheetAuditForTests(joined.DossierId));
    }

    [Fact]
    public void GmCannotEditWhenOwnerDidNotGrantCharacterAuthority()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(60, 1));
        CampaignInviteRedemptionProjection joined = fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            fixture.LinkRequest(invite, character, "no-grant") with { GrantGmEditAuthority = false });

        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(1, "edit-denied", "Razor", "Alex Razor", "active", "No grant.")));
        Assert.Equal(0, fixture.CanonicalEdits.CallCount);
        Assert.Equal("Razor", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
    }

    [Fact]
    public void RevokedGmAuthorityRejectsReplayOfPreviouslyAuthorizedSheetEdit()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        var edit = new CampaignSharedSheetUpdateRequest(
            1,
            "edit-before-revoke",
            "Razor Prime",
            "Alex Razor",
            "active",
            "Approved before revocation.");

        _ = fixture.Service.UpdateSharedSheet(fixture.Gm, campaign.CampaignId, joined.DossierId, edit);
        CampaignPlayerSafeSheetProjection afterEdit = fixture.Service.GetSharedSheet(
            player,
            campaign.CampaignId,
            joined.DossierId);
        _ = fixture.Service.UpdateGmAuthority(
            player,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignGmAuthorityUpdateRequest(
                afterEdit.GmAuthorityBindingRevision,
                false,
                "revoke-after-edit",
                "Withdraw edit consent."));

        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            edit));
        Assert.Equal(1, fixture.CanonicalEdits.ApplyCount);
        Assert.Equal(1, fixture.CanonicalEdits.CallCount);
    }

    [Fact]
    public void UnmappedAdministrativeLabelsDoNotAcquireGmAuthority()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        HubUserDto user = fixture.CreateUser("subject.admin-label", "Admin Label");
        lock (fixture.Store.Gate)
        {
            GroupDto group = fixture.Store.GroupsById[campaign.GroupId];
            fixture.Store.GroupsById[campaign.GroupId] = group with
            {
                Memberships = group.Memberships.Append(new GroupMembershipDto(
                    $"membership-{Guid.NewGuid():N}",
                    group.GroupId,
                    user.UserId,
                    "admin",
                    fixture.Clock.GetUtcNow())).ToArray()
            };
            fixture.Store.PersistLocked();
        }

        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.CreateInvite(
            user,
            campaign.CampaignId,
            InviteRequest(60, 1)));
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.GetSharedSheet(
            user,
            campaign.CampaignId,
            joined.DossierId));
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.GetPublishedRunsite(
            user,
            campaign.CampaignId,
            Assert.Single(campaign.RunIds)));
        Assert.Throws<InvalidDataException>(() => fixture.Service.GetCampaign(user, campaign.CampaignId));
    }

    [Fact]
    public void PlayerAndOwnerLabelsWithoutMatchingAuthorityBindingsStayFailClosed()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto rosterPlayer = fixture.CreateUser("subject.roster-player", "Roster Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(
            campaign,
            rosterPlayer,
            "Razor",
            "Alex Razor");
        HubUserDto unboundPlayer = fixture.CreateUser("subject.unbound-player", "Unbound Player");
        HubUserDto falseOwner = fixture.CreateUser("subject.false-owner", "False Owner");
        lock (fixture.Store.Gate)
        {
            GroupDto group = fixture.Store.GroupsById[campaign.GroupId];
            fixture.Store.GroupsById[campaign.GroupId] = group with
            {
                Memberships = group.Memberships.Concat(
                [
                    new GroupMembershipDto(
                        $"membership-{Guid.NewGuid():N}",
                        group.GroupId,
                        unboundPlayer.UserId,
                        "player",
                        fixture.Clock.GetUtcNow()),
                    new GroupMembershipDto(
                        $"membership-{Guid.NewGuid():N}",
                        group.GroupId,
                        falseOwner.UserId,
                        "owner",
                        fixture.Clock.GetUtcNow())
                ]).ToArray()
            };
            fixture.Store.PersistLocked();
        }

        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.GetSharedSheet(
            unboundPlayer,
            campaign.CampaignId,
            joined.DossierId));
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.GetPublishedRunsite(
            unboundPlayer,
            campaign.CampaignId,
            Assert.Single(campaign.RunIds)));
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.CreateInvite(
            falseOwner,
            campaign.CampaignId,
            InviteRequest(60, 1)));
        Assert.Throws<InvalidDataException>(() => fixture.Service.GetCampaign(falseOwner, campaign.CampaignId));
    }

    [Fact]
    public void CharacterOwnerCanRevokeAndRegrantGmAuthorityWithCasIdempotencyAndAudit()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        CampaignPlayerSafeSheetProjection initialPlayerSheet = fixture.Service.GetSharedSheet(
            player, campaign.CampaignId, joined.DossierId);
        CampaignPlayerSafeSheetProjection initialGmSheet = fixture.Service.GetSharedSheet(
            fixture.Gm, campaign.CampaignId, joined.DossierId);
        Assert.False(initialPlayerSheet.CanManage);
        Assert.True(initialGmSheet.CanManage);
        Assert.True(initialPlayerSheet.GmEditAuthorityGranted);

        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("injected authority persistence failure");
        Assert.Throws<IOException>(() => fixture.Service.UpdateGmAuthority(
            player,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignGmAuthorityUpdateRequest(1, false, "fault-revoke", "Injected rollback.")));
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;
        Assert.True(fixture.Service.GetSharedSheet(player, campaign.CampaignId, joined.DossierId).GmEditAuthorityGranted);
        Assert.Single(fixture.Store.CampaignCharacterBindings);
        Assert.Empty(fixture.Service.GetGmAuthorityAuditForTests(joined.DossierId));

        var revoke = new CampaignGmAuthorityUpdateRequest(
            ExpectedBindingRevision: joined.Binding.BindingRevision,
            GrantGmEditAuthority: false,
            IdempotencyKey: "revoke-1",
            Reason: "Player withdrew durable edit consent.");
        CampaignGmAuthorityUpdateReceipt revoked = fixture.Service.UpdateGmAuthority(
            player, campaign.CampaignId, joined.DossierId, revoke);
        CampaignGmAuthorityUpdateReceipt replay = fixture.Service.UpdateGmAuthority(
            player, campaign.CampaignId, joined.DossierId, revoke);
        Assert.Equal(revoked, replay);
        Assert.True(revoked.Changed);
        Assert.False(revoked.GmEditAuthorityGranted);
        Assert.False(fixture.Service.GetSharedSheet(player, campaign.CampaignId, joined.DossierId).GmEditAuthorityGranted);
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(1, "blocked-edit", "Razor", "Alex Razor", "active", "No consent.")));
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.UpdateGmAuthority(
            player,
            campaign.CampaignId,
            joined.DossierId,
            revoke with { GrantGmEditAuthority = true }));

        CampaignGmAuthorityUpdateReceipt regranted = fixture.Service.UpdateGmAuthority(
            player,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignGmAuthorityUpdateRequest(
                revoked.BindingRevision,
                true,
                "regrant-1",
                "Player explicitly restored GM edit consent."));
        Assert.True(regranted.GmEditAuthorityGranted);
        Assert.Equal(3, regranted.BindingRevision);
        Assert.Equal(2, fixture.Service.GetGmAuthorityAuditForTests(joined.DossierId).Count);
        Assert.Throws<CampaignBindingRevisionConflictException>(() => fixture.Service.UpdateGmAuthority(
            player,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignGmAuthorityUpdateRequest(1, false, "stale-revoke", "Stale consent command.")));

        CampaignSharedSheetEditReceipt edit = fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(1, "edit-after-regrant", "Razor-2", "Alex Razor", "active", "Consent restored."));
        Assert.Equal(2, edit.Revision);
        CampaignPlayerSafeSheetProjection afterEdit = fixture.Service.GetSharedSheet(
            player, campaign.CampaignId, joined.DossierId);
        CampaignGmAuthorityUpdateReceipt revokedAfterEdit = fixture.Service.UpdateGmAuthority(
            player,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignGmAuthorityUpdateRequest(
                afterEdit.GmAuthorityBindingRevision,
                false,
                "revoke-after-edit",
                "Player withdrew consent after reviewing the GM edit."));
        Assert.False(revokedAfterEdit.GmEditAuthorityGranted);
        Assert.Equal(3, fixture.Service.GetGmAuthorityAuditForTests(joined.DossierId).Count);

        string getProjectionJson = JsonSerializer.Serialize(new
        {
            Campaign = fixture.Service.GetCampaign(player, campaign.CampaignId),
            Sheet = fixture.Service.GetSharedSheet(player, campaign.CampaignId, joined.DossierId)
        });
        Assert.DoesNotContain(player.UserId, getProjectionJson, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(player.SubjectId, getProjectionJson, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PersistenceFailureRollsBackAllLiveCampaignAuthorizationAndState()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(60, 1));
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        string durableBefore = File.ReadAllText(fixture.StorePath);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("injected persistence failure");

        Assert.Throws<IOException>(() => fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            fixture.LinkRequest(invite, character, "fault")));
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;

        Assert.Equal(durableBefore, File.ReadAllText(fixture.StorePath));
        Assert.Empty(fixture.Store.CampaignCharacterBindings);
        Assert.Empty(fixture.Store.CrewsById[campaign.CrewId].Members);
        Assert.DoesNotContain(fixture.Store.GroupsById[campaign.GroupId].Memberships, item => item.UserId == player.UserId);
        Assert.Equal(0, fixture.Store.CampaignCollaborationInvitesById[invite.InviteId].Uses);
        var reloaded = new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        Assert.Empty(reloaded.CampaignCharacterBindings);
    }

    [Fact]
    public void InviteQuotaIsBoundedAndExpiredHistoryIsPrunedFromIndexedLookup()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CampaignInviteSecretProjection first = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(5, 1));
        for (int index = 1; index < 32; index++)
        {
            fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(60, 1));
        }

        Assert.Throws<InvalidOperationException>(() => fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(60, 1)));
        fixture.Clock.Advance(TimeSpan.FromDays(8));
        fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, InviteRequest(60, 1));
        Assert.False(fixture.Store.CampaignCollaborationInvitesById.ContainsKey(first.InviteId));
        Assert.DoesNotContain(first.InviteId, fixture.Store.CampaignInviteIdByCodeLookupSha256.Values);
    }

    [Fact]
    public void CampaignOwnershipQuotaIsBounded()
    {
        using var fixture = new CampaignFixture();
        for (int index = 0; index < 32; index++)
        {
            fixture.CreateCampaign($"Campaign {index + 1}");
        }

        Assert.Throws<InvalidOperationException>(() => fixture.CreateCampaign("Campaign 33"));
        Assert.Equal(32, fixture.Service.ListCampaigns(fixture.Gm).Count);
    }

    [Fact]
    public void CampaignTeardownRequiresOwnerExactNameCurrentUtcPreconditionAndBoundedIdempotency()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign("Exact Name Campaign");
        HubUserDto player = fixture.CreateUser("subject.teardown-player", "Teardown Player");
        fixture.Join(campaign, player, "Razor", "Alex Razor");
        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, campaign.CampaignId));
        var request = new DeleteCampaignCollaborationRequest(
            current.Name,
            current.UpdatedAtUtc,
            "teardown-owner-only");

        Assert.Throws<CampaignCollaborationAccessDeniedException>(() =>
            fixture.Service.DeleteCampaign(player, current.CampaignId, request));
        Assert.Throws<ArgumentException>(() => fixture.Service.DeleteCampaign(
            fixture.Gm,
            current.CampaignId,
            request with { ConfirmCampaignName = current.Name.ToUpperInvariant() }));
        CampaignUpdatedAtConflictException conflict = Assert.Throws<CampaignUpdatedAtConflictException>(() =>
            fixture.Service.DeleteCampaign(
                fixture.Gm,
                current.CampaignId,
                request with { ExpectedUpdatedAtUtc = current.UpdatedAtUtc.AddTicks(-1) }));
        Assert.Equal(current.UpdatedAtUtc, conflict.CurrentUpdatedAtUtc);
        Assert.Throws<ArgumentException>(() => fixture.Service.DeleteCampaign(
            fixture.Gm,
            current.CampaignId,
            request with { ExpectedUpdatedAtUtc = current.UpdatedAtUtc.ToOffset(TimeSpan.FromHours(1)) }));
        Assert.Throws<ArgumentOutOfRangeException>(() => fixture.Service.DeleteCampaign(
            fixture.Gm,
            current.CampaignId,
            request with { IdempotencyKey = new string('x', 129) }));

        Assert.NotNull(fixture.Service.GetCampaign(fixture.Gm, current.CampaignId));
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Fact]
    public void CampaignTeardownRemovesOnlyOwnedCollaborationStateAndReturnsSecretFreeCounts()
    {
        var projectionSync = new RecordingUserProjectionSyncQueue();
        using var fixture = new CampaignFixture(projectionSync);
        CampaignCollaborationProjection target = fixture.CreateCampaign("Disposable Campaign");
        CampaignCollaborationProjection unrelated = fixture.CreateCampaign("Preserved Campaign");
        HubUserDto player = fixture.CreateUser("subject.teardown-shared-player", "Shared Player");
        RunnerDossierProjection targetCharacter = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        CampaignInviteSecretProjection targetInvite = fixture.Service.CreateInvite(
            fixture.Gm,
            target.CampaignId,
            InviteRequest(60, 1, "target-join-invite"));
        CampaignInviteRedemptionProjection targetJoin = fixture.Service.RedeemInvite(
            player,
            targetInvite.InviteId,
            fixture.LinkRequest(targetInvite, targetCharacter, "target-join"));
        CampaignInviteSecretProjection unusedTargetInvite = fixture.Service.CreateInvite(
            fixture.Gm,
            target.CampaignId,
            InviteRequest(60, 1, "target-unused-invite"));
        CampaignInviteRedemptionProjection unrelatedJoin = fixture.Join(
            unrelated,
            player,
            "Cipher",
            "Blake Cipher");

        _ = fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            target.CampaignId,
            targetJoin.DossierId,
            new CampaignSharedSheetUpdateRequest(
                1,
                "target-gm-edit",
                "Razor Prime",
                "Alex Razor",
                "active",
                "Prepare deterministic cleanup coverage."));
        CampaignPlayerSafeSheetProjection targetSheet = fixture.Service.GetSharedSheet(
            player,
            target.CampaignId,
            targetJoin.DossierId);
        _ = fixture.Service.UpdateGmAuthority(
            player,
            target.CampaignId,
            targetJoin.DossierId,
            new CampaignGmAuthorityUpdateRequest(
                targetSheet.GmAuthorityBindingRevision,
                false,
                "target-revoke-gm",
                "Exercise campaign-scoped consent cleanup."));
        string targetRunId = Assert.Single(target.RunIds);
        CampaignRunsiteDraftProjection draft = fixture.Service.UpsertRunsiteDraft(
            fixture.Gm,
            target.CampaignId,
            targetRunId,
            new CampaignRunsiteDraftUpdateRequest(
                0,
                "target-runsite-draft",
                "Disposable Runsite",
                "This runsite must be removed with only its campaign.",
                [new RunsitePlayerSectionInput("Entry", "North door")],
                "Never leave this GM note behind."));
        _ = fixture.Service.PublishRunsite(
            fixture.Gm,
            target.CampaignId,
            targetRunId,
            new PublishCampaignRunsiteRequest(draft.Revision, "target-runsite-publish"));

        CampaignCollaborationProjection currentTarget = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        string dossiersBefore = JsonSerializer.Serialize(
            fixture.Store.DossiersById.Values.OrderBy(static item => item.DossierId, StringComparer.OrdinalIgnoreCase));
        string unrelatedBefore = JsonSerializer.Serialize(
            fixture.Service.GetCampaign(fixture.Gm, unrelated.CampaignId));
        int usersBefore = fixture.Store.UsersById.Count;
        var coreRead = new DelegatedGmCharacterProfileReadCommand(
            target.CampaignId,
            fixture.Gm.UserId,
            new OwnerScope(player.UserId),
            new CharacterWorkspaceId(targetJoin.Binding.AuthoritativeCharacterId));
        string coreBefore = JsonSerializer.Serialize(fixture.CanonicalEdits.ReadCurrentProfile(coreRead));
        int coreCallsBefore = fixture.CanonicalEdits.CallCount;

        CampaignTeardownReceipt receipt = fixture.Service.DeleteCampaign(
            fixture.Gm,
            target.CampaignId,
            new DeleteCampaignCollaborationRequest(
                currentTarget.Name,
                currentTarget.UpdatedAtUtc,
                "target-teardown"));

        Assert.Equal(target.CampaignId, receipt.CampaignId);
        Assert.Equal(1, receipt.Removed.Campaigns);
        Assert.Equal(1, receipt.Removed.Groups);
        Assert.Equal(1, receipt.Removed.Crews);
        Assert.Equal(1, receipt.Removed.Runs);
        Assert.Equal(2, receipt.Removed.Invites);
        Assert.Equal(2, receipt.Removed.InviteCodeIndexes);
        Assert.Equal(2, receipt.Removed.CharacterBindings);
        Assert.Equal(1, receipt.Removed.Runsites);
        Assert.Equal(8, receipt.Removed.CommandRecords);
        Assert.Equal(2, receipt.Removed.AuditRecords);
        Assert.Equal(2, receipt.Removed.UserGroupMemberships);
        Assert.Equal(32, Convert.FromHexString(receipt.CampaignNameSha256).Length);
        Assert.Equal(32, Convert.FromHexString(receipt.CleanupSha256).Length);
        string receiptJson = JsonSerializer.Serialize(receipt);
        Assert.DoesNotContain(targetInvite.LinkSecret, receiptJson, StringComparison.Ordinal);
        Assert.DoesNotContain(targetInvite.ShortCode, receiptJson, StringComparison.Ordinal);
        Assert.DoesNotContain(unusedTargetInvite.LinkSecret, receiptJson, StringComparison.Ordinal);
        Assert.DoesNotContain(unusedTargetInvite.ShortCode, receiptJson, StringComparison.Ordinal);
        Assert.DoesNotContain(currentTarget.Name, receiptJson, StringComparison.Ordinal);
        Assert.DoesNotContain(
            typeof(CampaignTeardownReceipt).GetProperties(),
            property => property.Name.Contains("Secret", StringComparison.OrdinalIgnoreCase)
                || property.Name.Contains("Token", StringComparison.OrdinalIgnoreCase));

        Assert.Null(fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        Assert.Null(fixture.Service.GetCampaign(player, target.CampaignId));
        Assert.Equal(unrelatedBefore, JsonSerializer.Serialize(
            fixture.Service.GetCampaign(fixture.Gm, unrelated.CampaignId)));
        Assert.NotNull(fixture.Service.GetSharedSheet(player, unrelated.CampaignId, unrelatedJoin.DossierId));
        Assert.Equal(dossiersBefore, JsonSerializer.Serialize(
            fixture.Store.DossiersById.Values.OrderBy(static item => item.DossierId, StringComparer.OrdinalIgnoreCase)));
        Assert.Equal(usersBefore, fixture.Store.UsersById.Count);
        Assert.DoesNotContain(target.GroupId, fixture.Store.UsersById[fixture.Gm.UserId].GroupIds);
        Assert.Contains(unrelated.GroupId, fixture.Store.UsersById[fixture.Gm.UserId].GroupIds);
        Assert.DoesNotContain(target.GroupId, fixture.Store.UsersById[player.UserId].GroupIds);
        Assert.Contains(unrelated.GroupId, fixture.Store.UsersById[player.UserId].GroupIds);
        Assert.Equal(2, projectionSync.Users.Count);
        Assert.All(projectionSync.Users, user => Assert.DoesNotContain(target.GroupId, user.GroupIds));
        Assert.Contains(projectionSync.Users, user => user.UserId == fixture.Gm.UserId);
        Assert.Contains(projectionSync.Users, user => user.UserId == player.UserId);
        Assert.Equal(coreCallsBefore, fixture.CanonicalEdits.CallCount);
        Assert.Equal(coreBefore, JsonSerializer.Serialize(fixture.CanonicalEdits.ReadCurrentProfile(coreRead)));
        Assert.DoesNotContain(fixture.Store.CampaignCollaborationInvitesById.Values,
            item => item.CampaignId == target.CampaignId);
        Assert.DoesNotContain(fixture.Store.CampaignCharacterBindings,
            item => item.CampaignId == target.CampaignId);
        Assert.DoesNotContain(fixture.Store.CampaignRunsitesByRunId.Values,
            item => item.CampaignId == target.CampaignId);
        Assert.Single(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Fact]
    public void CampaignTeardownReplaySurvivesRestartRejectsDriftAndPrunesExpiredReceipts()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign("Restart Teardown");
        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, campaign.CampaignId));
        var request = new DeleteCampaignCollaborationRequest(
            current.Name,
            current.UpdatedAtUtc,
            "restart-teardown");
        CampaignTeardownReceipt first = fixture.Service.DeleteCampaign(
            fixture.Gm,
            campaign.CampaignId,
            request);

        var reloadedStore = new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        IDataProtectionProvider reloadedProtection = DataProtectionProvider.Create(
            new DirectoryInfo(fixture.DataProtectionPath));
        var reloadedService = new CampaignCollaborationService(
            reloadedStore,
            fixture.CanonicalEdits,
            reloadedProtection,
            fixture.Clock);
        HubUserDto reloadedGm = reloadedStore.UsersById[fixture.Gm.UserId];
        reloadedStore.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("replay must not persist");

        Assert.Equal(first, reloadedService.DeleteCampaign(reloadedGm, campaign.CampaignId, request));
        Assert.Throws<CampaignIdempotencyConflictException>(() => reloadedService.DeleteCampaign(
            reloadedGm,
            campaign.CampaignId,
            request with { ConfirmCampaignName = "Changed Restart Teardown" }));
        Assert.Throws<CampaignIdempotencyConflictException>(() => reloadedService.DeleteCampaign(
            reloadedGm,
            campaign.CampaignId,
            request with { ExpectedUpdatedAtUtc = request.ExpectedUpdatedAtUtc.AddTicks(-1) }));
        reloadedStore.CampaignCollaborationPersistenceFaultInjector = null;

        fixture.Clock.Advance(CampaignCollaborationService.CampaignTeardownRetention + TimeSpan.FromMinutes(1));
        CampaignCollaborationProjection next = reloadedService.CreateCampaign(
            reloadedGm,
            CampaignRequest("Next Teardown", "Next teardown summary", "private", "Next run", "next-create"));
        CampaignCollaborationProjection currentNext = Assert.IsType<CampaignCollaborationProjection>(
            reloadedService.GetCampaign(reloadedGm, next.CampaignId));
        _ = reloadedService.DeleteCampaign(
            reloadedGm,
            next.CampaignId,
            new DeleteCampaignCollaborationRequest(
                currentNext.Name,
                currentNext.UpdatedAtUtc,
                "next-teardown"));

        CampaignTeardownIdempotencyState onlyLedgerEntry = Assert.Single(
            reloadedStore.CampaignTeardownsByIdempotencyKey.Values);
        Assert.NotEqual(first.ReceiptId, onlyLedgerEntry.Response.ReceiptId);
        Assert.Throws<KeyNotFoundException>(() =>
            reloadedService.DeleteCampaign(reloadedGm, campaign.CampaignId, request));
    }

    [Fact]
    public void CampaignTeardownReplayLedgerDeterministicallyPrunesOldestEntryAtCapacity()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign("Capacity Teardown");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        var emptyCounts = new CampaignTeardownCleanupCounts(
            Campaigns: 1,
            Groups: 1,
            Crews: 0,
            Runs: 0,
            Invites: 0,
            InviteCodeIndexes: 0,
            CharacterBindings: 0,
            Runsites: 0,
            CommandRecords: 0,
            AuditRecords: 0,
            UserGroupMemberships: 0);
        lock (fixture.Store.Gate)
        {
            for (int index = 0; index < CampaignCollaborationService.MaxCampaignTeardownReceipts; index++)
            {
                DateTimeOffset createdAtUtc = now.AddSeconds(
                    index - CampaignCollaborationService.MaxCampaignTeardownReceipts);
                string key = $"seed-teardown-key-{index:D4}";
                fixture.Store.CampaignTeardownsByIdempotencyKey[key] = new CampaignTeardownIdempotencyState(
                    Key: key,
                    UserId: fixture.Gm.UserId,
                    IdempotencyKey: $"seed-teardown-{index:D4}",
                    RequestSha256: new string('a', 64),
                    Response: new CampaignTeardownReceipt(
                        ReceiptId: $"seed-teardown-receipt-{index:D4}",
                        CampaignId: $"deleted-seed-campaign-{index:D4}",
                        CampaignNameSha256: new string('b', 64),
                        PreviousUpdatedAtUtc: createdAtUtc.AddMinutes(-1),
                        Removed: emptyCounts,
                        CleanupSha256: new string('c', 64),
                        DeletedAtUtc: createdAtUtc),
                    CreatedAtUtc: createdAtUtc);
            }
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, campaign.CampaignId));
        CampaignTeardownReceipt receipt = fixture.Service.DeleteCampaign(
            fixture.Gm,
            campaign.CampaignId,
            new DeleteCampaignCollaborationRequest(
                current.Name,
                current.UpdatedAtUtc,
                "capacity-teardown"));

        Assert.Equal(
            CampaignCollaborationService.MaxCampaignTeardownReceipts,
            fixture.Store.CampaignTeardownsByIdempotencyKey.Count);
        Assert.False(fixture.Store.CampaignTeardownsByIdempotencyKey.ContainsKey("seed-teardown-key-0000"));
        Assert.True(fixture.Store.CampaignTeardownsByIdempotencyKey.ContainsKey("seed-teardown-key-0001"));
        Assert.Contains(
            fixture.Store.CampaignTeardownsByIdempotencyKey.Values,
            item => item.Response.ReceiptId == receipt.ReceiptId);
    }

    [Fact]
    public void CampaignTeardownPersistenceFailureRollsBackResourcesUsersAndReplayLedger()
    {
        var projectionSync = new RecordingUserProjectionSyncQueue();
        using var fixture = new CampaignFixture(projectionSync);
        CampaignCollaborationProjection campaign = fixture.CreateCampaign("Rollback Teardown");
        HubUserDto player = fixture.CreateUser("subject.teardown-rollback", "Rollback Player");
        fixture.Join(campaign, player, "Razor", "Alex Razor");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        string campaignWorkspaceId = "workspace-" + Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(campaign.CampaignId)))[..12]
            .ToLowerInvariant();
        const string preservedWorkspaceId = "workspace-preserved-after-rollback";
        lock (fixture.Store.Gate)
        {
            fixture.Store.RestoreByUserId[fixture.Gm.UserId] = new WorkspaceRestoreProjection(
                RestoreId: "restore-rollback",
                UserId: fixture.Gm.UserId,
                RecentDossiers: [],
                RecentCampaigns: [fixture.Store.CampaignSpinesById[campaign.CampaignId]],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: ["preserve until the transaction commits"],
                GeneratedAtUtc: now);
            fixture.Store.UserExperienceByUserId[player.UserId] = new HubUserExperienceDto(
                UserId: player.UserId,
                LaneInterests: ["living_world"],
                FollowHorizons: true,
                BetaInterest: true,
                OnboardingCompleted: true,
                OnboardingCompletedAtUtc: now,
                UpdatedAtUtc: now,
                WorkspacePrepLibrarySearchHistory:
                [
                    new WorkspacePrepLibrarySearchHistoryItem(campaignWorkspaceId, "runsite", now),
                    new WorkspacePrepLibrarySearchHistoryItem(preservedWorkspaceId, "prep", now)
                ]);
            fixture.Store.PersistLocked();
        }
        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, campaign.CampaignId));
        var request = new DeleteCampaignCollaborationRequest(
            current.Name,
            current.UpdatedAtUtc,
            "rollback-teardown");
        string durableBefore = File.ReadAllText(fixture.StorePath);
        string campaignBefore = JsonSerializer.Serialize(current);
        string[] gmGroupsBefore = fixture.Store.UsersById[fixture.Gm.UserId].GroupIds.ToArray();
        string[] playerGroupsBefore = fixture.Store.UsersById[player.UserId].GroupIds.ToArray();
        string restoreBefore = JsonSerializer.Serialize(
            fixture.Store.RestoreByUserId.Values.OrderBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase));
        string experienceBefore = JsonSerializer.Serialize(
            fixture.Store.UserExperienceByUserId.Values.OrderBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase));
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("injected teardown persistence failure");

        Assert.Throws<IOException>(() =>
            fixture.Service.DeleteCampaign(fixture.Gm, campaign.CampaignId, request));
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;

        Assert.Equal(durableBefore, File.ReadAllText(fixture.StorePath));
        Assert.Equal(campaignBefore, JsonSerializer.Serialize(
            fixture.Service.GetCampaign(fixture.Gm, campaign.CampaignId)));
        Assert.Equal(gmGroupsBefore, fixture.Store.UsersById[fixture.Gm.UserId].GroupIds);
        Assert.Equal(playerGroupsBefore, fixture.Store.UsersById[player.UserId].GroupIds);
        Assert.Equal(restoreBefore, JsonSerializer.Serialize(
            fixture.Store.RestoreByUserId.Values.OrderBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)));
        Assert.Equal(experienceBefore, JsonSerializer.Serialize(
            fixture.Store.UserExperienceByUserId.Values.OrderBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)));
        Assert.True(fixture.Store.GroupsById.ContainsKey(campaign.GroupId));
        Assert.True(fixture.Store.CrewsById.ContainsKey(campaign.CrewId));
        Assert.True(fixture.Store.RunsById.ContainsKey(Assert.Single(campaign.RunIds)));
        Assert.NotEmpty(fixture.Store.CampaignCharacterBindings);
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
        Assert.Empty(projectionSync.Users);

        CampaignTeardownReceipt retry = fixture.Service.DeleteCampaign(
            fixture.Gm,
            campaign.CampaignId,
            request);
        Assert.Equal(campaign.CampaignId, retry.CampaignId);
        Assert.Equal(1, retry.Removed.RestoreProjections);
        Assert.Equal(1, retry.Removed.WorkspacePrepLibrarySearchHistoryItems);
        Assert.False(fixture.Store.RestoreByUserId.ContainsKey(fixture.Gm.UserId));
        HubUserExperienceDto experience = fixture.Store.UserExperienceByUserId[player.UserId];
        WorkspacePrepLibrarySearchHistoryItem remainingHistory = Assert.Single(
            experience.WorkspacePrepLibrarySearchHistory ?? []);
        Assert.Equal(preservedWorkspaceId, remainingHistory.WorkspaceId);
        Assert.Equal(retry.DeletedAtUtc, experience.UpdatedAtUtc);
        Assert.Equal(2, projectionSync.Users.Select(static user => user.UserId)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Count());
        Assert.Contains(projectionSync.Users, user => user.UserId == fixture.Gm.UserId);
        Assert.Contains(projectionSync.Users, user => user.UserId == player.UserId);
    }

    [Theory]
    [InlineData("group")]
    [InlineData("crew")]
    [InlineData("run")]
    public void CampaignTeardownFailsClosedWhenUnrelatedCampaignReferencesSelectedResource(string coupling)
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Coupling Target");
        CampaignCollaborationProjection unrelated = fixture.CreateCampaign("Coupling Unrelated");
        lock (fixture.Store.Gate)
        {
            CampaignProjection state = fixture.Store.CampaignSpinesById[unrelated.CampaignId];
            fixture.Store.CampaignSpinesById[unrelated.CampaignId] = coupling switch
            {
                "group" => state with { GroupId = target.GroupId },
                "crew" => state with { CrewIds = state.CrewIds.Append(target.CrewId).ToArray() },
                "run" => state with { RunIds = state.RunIds.Append(Assert.Single(target.RunIds)).ToArray() },
                _ => throw new InvalidOperationException("Unknown coupling test case.")
            };
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        Assert.Throws<CampaignTeardownConflictException>(() => fixture.Service.DeleteCampaign(
            fixture.Gm,
            target.CampaignId,
            new DeleteCampaignCollaborationRequest(
                current.Name,
                current.UpdatedAtUtc,
                $"coupled-{coupling}")));

        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(unrelated.CampaignId));
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Theory]
    [InlineData("campaign")]
    [InlineData("crew")]
    [InlineData("run")]
    public void CampaignTeardownFailsClosedWhenPreservedDossierReferencesSelectedResource(string coupling)
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Dossier Coupling Target");
        RunnerDossierProjection dossier = fixture.CreateCharacter(
            fixture.Gm,
            "Archive",
            "Preserved Archive");
        lock (fixture.Store.Gate)
        {
            fixture.Store.DossiersById[dossier.DossierId] = coupling switch
            {
                "campaign" => dossier with { CampaignId = target.CampaignId },
                "crew" => dossier with { CrewId = target.CrewId },
                "run" => dossier with { CurrentRunId = Assert.Single(target.RunIds) },
                _ => throw new InvalidOperationException("Unknown dossier coupling test case.")
            };
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        Assert.Throws<CampaignTeardownConflictException>(() => fixture.Service.DeleteCampaign(
            fixture.Gm,
            target.CampaignId,
            new DeleteCampaignCollaborationRequest(
                current.Name,
                current.UpdatedAtUtc,
                $"dossier-coupled-{coupling}")));

        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.True(fixture.Store.DossiersById.ContainsKey(dossier.DossierId));
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Theory]
    [InlineData("campaign")]
    [InlineData("run")]
    public void CampaignTeardownFailsClosedWhenOpenRunReferencesSelectedResource(string coupling)
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Open Run Coupling Target");
        string targetRunId = Assert.Single(target.RunIds);
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        var joinPolicy = new OpenRunJoinPolicyProjection(
            AdmissionMode: "request_to_join",
            SeatsTotal: 4,
            ReservedSeatRoles: [],
            RequireRunnerDossier: true,
            AllowQuickstartRunner: false,
            RuleEnvironmentFingerprint: "open-run-coupling-fingerprint",
            SchedulingMode: "manual",
            ExpectedDurationMinutes: 240,
            CommunicationPlatform: "discord",
            VoiceRequired: false,
            ObserverMode: "manual_markers",
            Summary: "Preserved open-run teardown guard fixture.");
        var listing = new OpenRunListingProjection(
            OpenRunId: $"open-run-coupling-{coupling}",
            WorkspaceId: "workspace-preserved-open-run",
            CampaignId: coupling == "campaign" ? target.CampaignId : "campaign-preserved-open-run",
            RunId: coupling == "run" ? targetRunId : "run-preserved-open-run",
            RunTitle: "Preserved Open Run",
            ListingTitle: "Preserved Open Run",
            Visibility: "public",
            Status: "listed",
            Summary: "This public listing must not outlive its campaign references.",
            TableContractSummary: "Fail closed before campaign teardown.",
            JoinPolicy: joinPolicy,
            SchedulingPosture: "unscheduled",
            QuickstartAllowed: false,
            EvidenceLines: ["Preserved open-run teardown guard fixture."],
            CreatedByUserId: fixture.Gm.UserId,
            CreatedAtUtc: now,
            UpdatedAtUtc: now);
        lock (fixture.Store.Gate)
        {
            fixture.Store.OpenRuns.Add(listing);
            fixture.Store.PersistLocked();
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        CampaignTeardownConflictException error = Assert.Throws<CampaignTeardownConflictException>(() =>
            fixture.Service.DeleteCampaign(
                fixture.Gm,
                target.CampaignId,
                new DeleteCampaignCollaborationRequest(
                    current.Name,
                    current.UpdatedAtUtc,
                    $"open-run-coupled-{coupling}")));

        Assert.Contains("open-run", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.Contains(fixture.Store.OpenRuns, item => item.OpenRunId == listing.OpenRunId);
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Theory]
    [InlineData("join-code")]
    [InlineData("boost-campaign")]
    [InlineData("boost-code")]
    [InlineData("sponsor-session")]
    public void CampaignTeardownFailsClosedWhenSponsorshipStateReferencesItsGroup(
        string stateKind)
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Sponsorship Coupling Target");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        lock (fixture.Store.Gate)
        {
            switch (stateKind)
            {
                case "join-code":
                    fixture.Store.JoinCodesByValue["TARGET-CODE"] = new JoinCodeDto(
                        "join-code-target",
                        "TARGET-CODE",
                        target.GroupId,
                        "member",
                        now,
                        now.AddHours(1),
                        0);
                    break;
                case "boost-campaign":
                    fixture.Store.CampaignsById["boost-campaign-target"] = new BoostCampaignDto(
                        "boost-campaign-target",
                        target.GroupId,
                        "project-target",
                        "Target Boost Campaign",
                        "active",
                        now);
                    break;
                case "boost-code":
                    fixture.Store.BoostCodesByValue["BOOST-TARGET"] = new BoostCodeDto(
                        "boost-code-target",
                        "BOOST-TARGET",
                        target.GroupId,
                        "boost-campaign-target",
                        fixture.Gm.UserId,
                        "active",
                        now,
                        null,
                        null);
                    break;
                case "sponsor-session":
                    fixture.Store.SponsorSessionsById["sponsor-session-target"] = new SponsorSessionState
                    {
                        SponsorSessionId = "sponsor-session-target",
                        UserId = fixture.Gm.UserId,
                        GroupId = target.GroupId,
                        ProjectId = "project-target",
                        Status = "intent_created",
                        CreatedAtUtc = now,
                        UpdatedAtUtc = now
                    };
                    break;
                default:
                    throw new InvalidOperationException("Unknown sponsorship coupling test case.");
            }
            fixture.Store.PersistLocked();
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        CampaignTeardownConflictException error = Assert.Throws<CampaignTeardownConflictException>(() =>
            fixture.Service.DeleteCampaign(
                fixture.Gm,
                target.CampaignId,
                new DeleteCampaignCollaborationRequest(
                    current.Name,
                    current.UpdatedAtUtc,
                    $"sponsorship-coupled-{stateKind}")));

        Assert.Contains("sponsorship", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Theory]
    [InlineData("contribution")]
    [InlineData("ledger")]
    [InlineData("reward")]
    [InlineData("entitlement")]
    public void CampaignTeardownFailsClosedWhenRecognitionStateReferencesItsGroup(
        string stateKind)
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Recognition Coupling Target");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        lock (fixture.Store.Gate)
        {
            switch (stateKind)
            {
                case "contribution":
                    fixture.Store.Receipts.Add(new ContributionReceiptDto(
                        ReceiptId: "contribution-target",
                        EventKind: "slice_landed",
                        LaneId: "lane-target",
                        ProjectId: "project-target",
                        UserId: fixture.Gm.UserId,
                        GroupId: target.GroupId,
                        SponsorSessionId: null,
                        ParticipantCodexCode: null,
                        AuthClass: "group",
                        LaneType: "participant_burst"));
                    break;
                case "ledger":
                    fixture.Store.LedgerEntries.Add(new LedgerEntryDto(
                        "ledger-target",
                        "contribution",
                        fixture.Gm.UserId,
                        target.GroupId,
                        "source-target",
                        1,
                        "point",
                        "Preserved group ledger fixture.",
                        now));
                    break;
                case "reward":
                    fixture.Store.RewardEntries.Add(new RewardJournalEntryDto(
                        "reward-target",
                        fixture.Gm.UserId,
                        target.GroupId,
                        "contribution",
                        1,
                        "source-target",
                        "Preserved group reward fixture.",
                        now));
                    break;
                case "entitlement":
                    fixture.Store.EntitlementEntries.Add(new EntitlementGrantDto(
                        "entitlement-target",
                        "group",
                        target.GroupId,
                        "preview_access",
                        "source-target",
                        "Preserved group entitlement fixture.",
                        now));
                    break;
                default:
                    throw new InvalidOperationException("Unknown recognition coupling test case.");
            }
            fixture.Store.PersistLocked();
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        CampaignTeardownConflictException error = Assert.Throws<CampaignTeardownConflictException>(() =>
            fixture.Service.DeleteCampaign(
                fixture.Gm,
                target.CampaignId,
                new DeleteCampaignCollaborationRequest(
                    current.Name,
                    current.UpdatedAtUtc,
                    $"recognition-coupled-{stateKind}")));

        Assert.Contains("sponsorship", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Fact]
    public void CampaignTeardownFailsClosedWhenWorkspaceHistoryReferencesCampaign()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Workspace History Target");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        lock (fixture.Store.Gate)
        {
            fixture.Store.CampaignAdoptions.Add(new CampaignAdoptionProjection(
                AdoptionId: "adoption-target",
                WorkspaceId: "workspace-target",
                CampaignId: target.CampaignId,
                SafeToPlay: false,
                ConfidencePercent: 50,
                RunnerCount: 0,
                ActiveJobCount: 0,
                ContactCount: 0,
                HouseRuleCount: 0,
                ExplicitUnknowns: ["test fixture"],
                RecommendedNextActions: ["preserve history"],
                Summary: "Preserved workspace history teardown guard fixture.",
                NextSafeAction: "Refuse teardown.",
                EvidenceLines: ["Campaign reference remains live."],
                UpdatedByUserId: fixture.Gm.UserId,
                UpdatedAtUtc: now));
            fixture.Store.PersistLocked();
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        CampaignTeardownConflictException error = Assert.Throws<CampaignTeardownConflictException>(() =>
            fixture.Service.DeleteCampaign(
                fixture.Gm,
                target.CampaignId,
                new DeleteCampaignCollaborationRequest(
                    current.Name,
                    current.UpdatedAtUtc,
                    "workspace-history-coupled")));

        Assert.Contains("workspace history", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(fixture.Store.CampaignAdoptions, item => item.CampaignId == target.CampaignId);
        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Fact]
    public void CampaignTeardownFailsClosedWhenPlaySessionReferencesCampaignResources()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Play Session Target");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        string runId = Assert.Single(target.RunIds);
        lock (fixture.Store.Gate)
        {
            fixture.Store.PlaySessionsById["play-session-target"] = new PlaySessionBinding(
                SessionId: "play-session-target",
                CampaignId: target.CampaignId,
                RunId: runId,
                GroupId: target.GroupId,
                Status: PlaySessionStatuses.Active,
                AuthorizationVersion: 1,
                CreatedByUserId: fixture.Gm.UserId,
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
            fixture.Store.PersistLocked();
        }

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        CampaignTeardownConflictException error = Assert.Throws<CampaignTeardownConflictException>(() =>
            fixture.Service.DeleteCampaign(
                fixture.Gm,
                target.CampaignId,
                new DeleteCampaignCollaborationRequest(
                    current.Name,
                    current.UpdatedAtUtc,
                    "play-session-coupled")));

        Assert.Contains("play session", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.True(fixture.Store.PlaySessionsById.ContainsKey("play-session-target"));
        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.Empty(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Fact]
    public void CampaignTeardownRemovesDerivedRestoreProjectionsForAffectedUsersAndTargetReferences()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection target = fixture.CreateCampaign("Restore Projection Target");
        CampaignCollaborationProjection unrelated = fixture.CreateCampaign("Restore Projection Preserved");
        HubUserDto targetReferenceUser = fixture.CreateUser(
            "subject.restore-target-reference",
            "Target Restore Reference");
        HubUserDto unrelatedReferenceUser = fixture.CreateUser(
            "subject.restore-unrelated-reference",
            "Unrelated Restore Reference");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        lock (fixture.Store.Gate)
        {
            fixture.Store.RestoreByUserId[fixture.Gm.UserId] = new WorkspaceRestoreProjection(
                RestoreId: "restore-affected-owner",
                UserId: fixture.Gm.UserId,
                RecentDossiers: [],
                RecentCampaigns: [fixture.Store.CampaignSpinesById[unrelated.CampaignId]],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: ["The whole projection belongs to an affected group member."],
                GeneratedAtUtc: now);
            fixture.Store.RestoreByUserId[targetReferenceUser.UserId] = new WorkspaceRestoreProjection(
                RestoreId: "restore-target-reference",
                UserId: targetReferenceUser.UserId,
                RecentDossiers: [],
                RecentCampaigns: [fixture.Store.CampaignSpinesById[target.CampaignId]],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: ["Derived target reference must be discarded."],
                GeneratedAtUtc: now);
            fixture.Store.RestoreByUserId[unrelatedReferenceUser.UserId] = new WorkspaceRestoreProjection(
                RestoreId: "restore-unrelated-reference",
                UserId: unrelatedReferenceUser.UserId,
                RecentDossiers: [],
                RecentCampaigns: [fixture.Store.CampaignSpinesById[unrelated.CampaignId]],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: ["Unrelated restore projection must survive."],
                GeneratedAtUtc: now);
            fixture.Store.PersistLocked();
        }
        string unrelatedRestoreBefore = JsonSerializer.Serialize(
            fixture.Store.RestoreByUserId[unrelatedReferenceUser.UserId]);

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        CampaignTeardownReceipt receipt = fixture.Service.DeleteCampaign(
            fixture.Gm,
            target.CampaignId,
            new DeleteCampaignCollaborationRequest(
                current.Name,
                current.UpdatedAtUtc,
                "restore-projection-cleanup"));

        Assert.Equal(2, receipt.Removed.RestoreProjections);
        Assert.False(fixture.Store.RestoreByUserId.ContainsKey(fixture.Gm.UserId));
        Assert.False(fixture.Store.RestoreByUserId.ContainsKey(targetReferenceUser.UserId));
        Assert.Equal(unrelatedRestoreBefore, JsonSerializer.Serialize(
            fixture.Store.RestoreByUserId[unrelatedReferenceUser.UserId]));
        Assert.False(fixture.Store.CampaignSpinesById.ContainsKey(target.CampaignId));
        Assert.True(fixture.Store.CampaignSpinesById.ContainsKey(unrelated.CampaignId));
        Assert.Single(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Fact]
    public void CampaignTeardownScrubsOnlyTargetWorkspaceHistoryAndSyncsUxOnlyUsers()
    {
        var projectionSync = new RecordingUserProjectionSyncQueue();
        using var fixture = new CampaignFixture(projectionSync);
        CampaignCollaborationProjection target = fixture.CreateCampaign("User Experience Target");
        HubUserDto uxOnlyUser = fixture.CreateUser("subject.ux-only-sync", "UX Only Sync");
        HubUserDto unaffectedUser = fixture.CreateUser("subject.ux-unaffected", "UX Unaffected");
        DateTimeOffset now = fixture.Clock.GetUtcNow();
        string workspaceId = "workspace-" + Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(target.CampaignId)))[..12]
            .ToLowerInvariant();
        const string preservedOwnerWorkspaceId = "workspace-owner-preserved";
        const string preservedUxOnlyWorkspaceId = "workspace-ux-only-preserved";
        const string unaffectedWorkspaceId = "workspace-unaffected";
        var ownerExperience = new HubUserExperienceDto(
            UserId: fixture.Gm.UserId,
            LaneInterests: ["gm_tools", "living_world"],
            FollowHorizons: true,
            BetaInterest: false,
            OnboardingCompleted: true,
            OnboardingCompletedAtUtc: now.AddDays(-2),
            UpdatedAtUtc: now,
            WorkspacePrepLibrarySearchHistory:
            [
                new WorkspacePrepLibrarySearchHistoryItem(workspaceId, "runsite", now.AddMinutes(-2)),
                new WorkspacePrepLibrarySearchHistoryItem(preservedOwnerWorkspaceId, "prep", now.AddMinutes(-1))
            ]);
        var uxOnlyExperience = new HubUserExperienceDto(
            UserId: uxOnlyUser.UserId,
            LaneInterests: ["runner_tools"],
            FollowHorizons: false,
            BetaInterest: true,
            OnboardingCompleted: false,
            OnboardingCompletedAtUtc: null,
            UpdatedAtUtc: now,
            WorkspacePrepLibrarySearchHistory:
            [
                new WorkspacePrepLibrarySearchHistoryItem(workspaceId.ToUpperInvariant(), "recap", now.AddMinutes(-3)),
                new WorkspacePrepLibrarySearchHistoryItem(preservedUxOnlyWorkspaceId, "prep", now.AddMinutes(-1))
            ]);
        var unaffectedExperience = new HubUserExperienceDto(
            UserId: unaffectedUser.UserId,
            LaneInterests: ["news"],
            FollowHorizons: true,
            BetaInterest: true,
            OnboardingCompleted: true,
            OnboardingCompletedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now,
            WorkspacePrepLibrarySearchHistory:
            [
                new WorkspacePrepLibrarySearchHistoryItem(unaffectedWorkspaceId, "news", now)
            ]);
        lock (fixture.Store.Gate)
        {
            fixture.Store.UserExperienceByUserId[fixture.Gm.UserId] = ownerExperience;
            fixture.Store.UserExperienceByUserId[uxOnlyUser.UserId] = uxOnlyExperience;
            fixture.Store.UserExperienceByUserId[unaffectedUser.UserId] = unaffectedExperience;
            fixture.Store.PersistLocked();
        }
        string unaffectedBefore = JsonSerializer.Serialize(unaffectedExperience);

        CampaignCollaborationProjection current = Assert.IsType<CampaignCollaborationProjection>(
            fixture.Service.GetCampaign(fixture.Gm, target.CampaignId));
        CampaignTeardownReceipt receipt = fixture.Service.DeleteCampaign(
            fixture.Gm,
            target.CampaignId,
            new DeleteCampaignCollaborationRequest(
                current.Name,
                current.UpdatedAtUtc,
                "user-experience-cleanup"));

        Assert.Equal(2, receipt.Removed.WorkspacePrepLibrarySearchHistoryItems);
        HubUserExperienceDto currentOwnerExperience = fixture.Store.UserExperienceByUserId[fixture.Gm.UserId];
        WorkspacePrepLibrarySearchHistoryItem ownerHistory = Assert.Single(
            currentOwnerExperience.WorkspacePrepLibrarySearchHistory ?? []);
        Assert.Equal(preservedOwnerWorkspaceId, ownerHistory.WorkspaceId);
        Assert.Equal(ownerExperience.LaneInterests, currentOwnerExperience.LaneInterests);
        Assert.Equal(ownerExperience.FollowHorizons, currentOwnerExperience.FollowHorizons);
        Assert.Equal(ownerExperience.BetaInterest, currentOwnerExperience.BetaInterest);
        Assert.Equal(ownerExperience.OnboardingCompleted, currentOwnerExperience.OnboardingCompleted);
        Assert.Equal(ownerExperience.OnboardingCompletedAtUtc, currentOwnerExperience.OnboardingCompletedAtUtc);
        Assert.Equal(receipt.DeletedAtUtc, currentOwnerExperience.UpdatedAtUtc);

        HubUserExperienceDto currentUxOnlyExperience = fixture.Store.UserExperienceByUserId[uxOnlyUser.UserId];
        WorkspacePrepLibrarySearchHistoryItem uxOnlyHistory = Assert.Single(
            currentUxOnlyExperience.WorkspacePrepLibrarySearchHistory ?? []);
        Assert.Equal(preservedUxOnlyWorkspaceId, uxOnlyHistory.WorkspaceId);
        Assert.Equal(uxOnlyExperience.LaneInterests, currentUxOnlyExperience.LaneInterests);
        Assert.Equal(uxOnlyExperience.FollowHorizons, currentUxOnlyExperience.FollowHorizons);
        Assert.Equal(uxOnlyExperience.BetaInterest, currentUxOnlyExperience.BetaInterest);
        Assert.Equal(uxOnlyExperience.OnboardingCompleted, currentUxOnlyExperience.OnboardingCompleted);
        Assert.Equal(uxOnlyExperience.OnboardingCompletedAtUtc, currentUxOnlyExperience.OnboardingCompletedAtUtc);
        Assert.Equal(receipt.DeletedAtUtc, currentUxOnlyExperience.UpdatedAtUtc);

        Assert.Equal(unaffectedBefore, JsonSerializer.Serialize(
            fixture.Store.UserExperienceByUserId[unaffectedUser.UserId]));
        Assert.Equal(2, projectionSync.Users.Select(static user => user.UserId)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Count());
        Assert.Contains(projectionSync.Users, user => user.UserId == fixture.Gm.UserId);
        Assert.Contains(projectionSync.Users, user => user.UserId == uxOnlyUser.UserId);
        Assert.DoesNotContain(projectionSync.Users, user => user.UserId == unaffectedUser.UserId);
        Assert.Empty(uxOnlyUser.GroupIds);
        Assert.Single(fixture.Store.CampaignTeardownsByIdempotencyKey);
    }

    [Fact]
    public void RunsiteDraftIsGmOnlyAndPublishedSnapshotNeverContainsGmNotes()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        fixture.Join(campaign, player, "Razor", "Alex Razor");
        string runId = Assert.Single(campaign.RunIds);
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.UpsertRunsiteDraft(
            player,
            campaign.CampaignId,
            runId,
            new CampaignRunsiteDraftUpdateRequest(
                0,
                "runsite-draft-player-denied",
                "Hidden",
                "Hidden",
                [],
                "player note")));

        var draftRequest = new CampaignRunsiteDraftUpdateRequest(
            0,
            "runsite-draft-response-loss",
            "Neon Vault",
            "Meet the Johnson at midnight.",
            [new RunsitePlayerSectionInput("Approach", "Use the freight entrance.")],
            "Secret ambush.");
        CampaignRunsiteDraftProjection first = fixture.Service.UpsertRunsiteDraft(
            fixture.Gm,
            campaign.CampaignId,
            runId,
            draftRequest);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("replay must not persist");
        CampaignRunsiteDraftProjection draftReplay = fixture.Service.UpsertRunsiteDraft(
            fixture.Gm,
            campaign.CampaignId.ToUpperInvariant(),
            runId.ToUpperInvariant(),
            draftRequest);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;
        Assert.Equal(first, draftReplay);
        Assert.Single(fixture.Store.CampaignRunsiteDraftCommandsByIdempotencyKey);
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.UpsertRunsiteDraft(
            fixture.Gm,
            campaign.CampaignId,
            runId,
            draftRequest with { Title = "Changed after response loss" }));

        var publishRequest = new PublishCampaignRunsiteRequest(
            first.Revision,
            "runsite-publish-response-loss");
        CampaignRunsitePlayerProjection published = fixture.Service.PublishRunsite(
            fixture.Gm,
            campaign.CampaignId,
            runId,
            publishRequest);
        fixture.Clock.Advance(TimeSpan.FromMinutes(1));
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = static () =>
            throw new IOException("replay must not persist");
        CampaignRunsitePlayerProjection replay = fixture.Service.PublishRunsite(
            fixture.Gm,
            campaign.CampaignId.ToUpperInvariant(),
            runId.ToUpperInvariant(),
            publishRequest);
        fixture.Store.CampaignCollaborationPersistenceFaultInjector = null;

        Assert.DoesNotContain("Secret ambush", JsonSerializer.Serialize(published), StringComparison.OrdinalIgnoreCase);
        Assert.Equal(JsonSerializer.Serialize(published), JsonSerializer.Serialize(replay));
        Assert.Single(fixture.Store.CampaignRunsitePublishCommandsByIdempotencyKey);
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.PublishRunsite(
            fixture.Gm,
            campaign.CampaignId,
            runId,
            publishRequest with { ExpectedRevision = first.Revision + 1 }));
        Assert.Equal("Neon Vault", fixture.Service.GetPublishedRunsite(player, campaign.CampaignId, runId)?.Title);
    }

    [Fact]
    public void CollaborationStateReloadsAndSemanticCorruptionFailsClosed()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        CampaignInviteRedemptionProjection joined = fixture.Join(campaign, player, "Razor", "Alex Razor");
        var reloadedStore = new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        var reloadedService = new CampaignCollaborationService(
            reloadedStore,
            fixture.CanonicalEdits,
            fixture.Clock);
        HubUserDto reloadedPlayer = reloadedStore.UsersById[player.UserId];
        Assert.Equal("Razor", reloadedService.GetSharedSheet(reloadedPlayer, campaign.CampaignId, joined.DossierId).RunnerHandle);

        JsonObject root = Assert.IsType<JsonObject>(JsonNode.Parse(File.ReadAllText(fixture.StorePath)));
        JsonArray bindings = Assert.IsType<JsonArray>(root["campaignCharacterBindings"]);
        Assert.IsType<JsonObject>(bindings[0])["authenticatedOwnerUserId"] = "attacker";
        File.WriteAllText(fixture.StorePath, root.ToJsonString());
        Assert.Throws<InvalidDataException>(() =>
            new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance));
    }

    [Theory]
    [InlineData("restoreProjections")]
    [InlineData("workspacePrepLibrarySearchHistoryItems")]
    public void CollaborationStateReloadRejectsNegativeDerivedCacheTeardownCount(string countProperty)
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign("Derived Cache Count Guard");
        _ = fixture.Service.DeleteCampaign(
            fixture.Gm,
            campaign.CampaignId,
            new DeleteCampaignCollaborationRequest(
                campaign.Name,
                campaign.UpdatedAtUtc,
                $"negative-derived-cache-count-{countProperty}"));

        JsonObject root = Assert.IsType<JsonObject>(JsonNode.Parse(File.ReadAllText(fixture.StorePath)));
        JsonArray teardowns = Assert.IsType<JsonArray>(root["campaignTeardowns"]);
        JsonObject teardown = Assert.IsType<JsonObject>(Assert.Single(teardowns));
        JsonObject response = Assert.IsType<JsonObject>(teardown["response"]);
        JsonObject removed = Assert.IsType<JsonObject>(response["removed"]);
        removed[countProperty] = -1;
        File.WriteAllText(fixture.StorePath, root.ToJsonString());

        Assert.Throws<InvalidDataException>(() =>
            new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance));
    }

    private static CreateCampaignCollaborationRequest CampaignRequest(
        string Name,
        string? Summary = null,
        string? Visibility = null,
        string? InitialRunTitle = null,
        string? IdempotencyKey = null)
        => new(
            Name,
            IdempotencyKey ?? $"campaign-create-{Guid.NewGuid():N}",
            Summary,
            Visibility,
            InitialRunTitle);

    private static CreateCampaignInviteRequest InviteRequest(
        int ExpiresInMinutes = 1440,
        int MaxUses = 1,
        string? IdempotencyKey = null)
        => new(
            IdempotencyKey ?? $"invite-create-{Guid.NewGuid():N}",
            ExpiresInMinutes,
            MaxUses);

    private static string PadBase64Url(string value)
    {
        string padded = value.Replace('-', '+').Replace('_', '/');
        padded += (padded.Length % 4) switch { 2 => "==", 3 => "=", _ => string.Empty };
        return padded;
    }

    private static ServiceProvider BuildCampaignGatewayProvider(
        CommunityStore store,
        TimeProvider timeProvider,
        IConfiguration configuration)
    {
        var services = new ServiceCollection();
        services.AddDataProtection();
        services.AddSingleton(configuration);
        services.AddSingleton(store);
        services.AddSingleton(timeProvider);
        services.AddHubCampaignSpineContext();
        return services.BuildServiceProvider();
    }

    private sealed class CampaignFixture : IDisposable
    {
        private readonly string _directory;

        public CampaignFixture(IHubUserProjectionSyncQueue? userProjectionSync = null)
        {
            _directory = Path.Combine(Path.GetTempPath(), "chummer-campaign-collaboration-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_directory);
            StorePath = Path.Combine(_directory, "community-store.json");
            DataProtectionPath = Path.Combine(_directory, "data-protection-keys");
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_COMMUNITY_STORE_PATH"] = StorePath })
                .Build();
            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Store);
            Clock = new AdjustableTimeProvider(DateTimeOffset.Parse("2026-07-20T12:00:00Z"));
            CanonicalEdits = new RecordingCanonicalGmCharacterEditGateway(Store, Clock);
            DataProtection = DataProtectionProvider.Create(
                new DirectoryInfo(DataProtectionPath));
            Service = new CampaignCollaborationService(
                Store,
                CanonicalEdits,
                DataProtection,
                Clock,
                userProjectionSync);
            Gm = CreateUser("subject.gm", "Game Master");
        }

        public string StorePath { get; }
        public string DataProtectionPath { get; }
        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public AccountService Accounts { get; }
        public AdjustableTimeProvider Clock { get; }
        public RecordingCanonicalGmCharacterEditGateway CanonicalEdits { get; }
        public IDataProtectionProvider DataProtection { get; }
        public CampaignCollaborationService Service { get; }
        public HubUserDto Gm { get; }

        public HubUserDto CreateUser(string subjectId, string displayName)
            => Accounts.EnsureUser(subjectId, displayName, $"{subjectId.Replace('.', '-')}@example.invalid");

        public RunnerDossierProjection CreateCharacter(HubUserDto owner, string handle, string displayName)
        {
            lock (Store.Gate)
            {
                string dossierId = $"dossier-{Guid.NewGuid():N}";
                var dossier = new RunnerDossierProjection(
                    DossierId: dossierId,
                    RunnerHandle: handle,
                    DisplayName: displayName,
                    Status: DossierStatuses.Active,
                    OwnerUserId: owner.UserId,
                    CrewId: null,
                    CampaignId: null,
                    CurrentRunId: null,
                    CurrentSceneId: null,
                    RuleEnvironment: new RuleEnvironmentRef(
                        $"environment:{dossierId}",
                        $"owner:{owner.UserId}",
                        $"fingerprint-{dossierId}",
                        "draft",
                        [],
                        [],
                        []),
                    LatestContinuity: null,
                    BuildReceiptIds: [],
                    SnapshotIds: [],
                    Projections: [new PublicationSafeProjection("identity", "identity", "Identity", $"{handle} character sheet.")],
                    CreatedAtUtc: Clock.GetUtcNow(),
                    UpdatedAtUtc: Clock.GetUtcNow());
                Store.DossiersById[dossierId] = dossier;
                CanonicalEdits.RegisterCharacter(
                    owner.UserId,
                    dossierId,
                    handle,
                    displayName);
                Store.PersistLocked();
                return dossier;
            }
        }

        public CampaignCollaborationProjection CreateCampaign(string name = "Neon Shadows")
            => Service.CreateCampaign(Gm, CampaignRequest(name, $"{name} summary", "private", $"{name} first run"));

        public RedeemCampaignInviteRequest LinkRequest(
            CampaignInviteSecretProjection invite,
            RunnerDossierProjection character,
            string idempotencyKey)
            => new(invite.LinkSecret, character.DossierId, character.DossierId, 1, true, idempotencyKey);

        public RedeemCampaignJoinCodeRequest CodeRequest(
            CampaignInviteSecretProjection invite,
            RunnerDossierProjection character,
            string idempotencyKey)
            => new(invite.ShortCode, character.DossierId, character.DossierId, 1, true, idempotencyKey);

        public CampaignInviteRedemptionProjection Join(
            CampaignCollaborationProjection campaign,
            HubUserDto player,
            string runnerHandle,
            string displayName)
        {
            RunnerDossierProjection character = CreateCharacter(player, runnerHandle, displayName);
            CampaignInviteSecretProjection invite = Service.CreateInvite(Gm, campaign.CampaignId, InviteRequest(60, 1));
            return Service.RedeemInvite(player, invite.InviteId, LinkRequest(invite, character, $"join-{Guid.NewGuid():N}"));
        }

        public void Dispose()
        {
            try { Directory.Delete(_directory, recursive: true); }
            catch { }
        }
    }

    private sealed class RecordingUserProjectionSyncQueue : IHubUserProjectionSyncQueue
    {
        public List<HubUserDto> Users { get; } = new();

        public void QueueSyncUser(HubUserDto user) => Users.Add(user);
    }

    internal sealed class RecordingCanonicalGmCharacterEditGateway : ICoreGmCharacterEditGateway
    {
        private readonly CommunityStore _store;
        private readonly TimeProvider _clock;
        private readonly Dictionary<string, (string RequestSha256, DelegatedGmCharacterEditAuditReceipt Receipt)> _ledger =
            new(StringComparer.Ordinal);
        private readonly Dictionary<string, DelegatedGmCharacterProfile> _profiles =
            new(StringComparer.Ordinal);

        public RecordingCanonicalGmCharacterEditGateway(CommunityStore store, TimeProvider clock)
        {
            _store = store;
            _clock = clock;
        }

        public int CallCount { get; private set; }
        public int ReadCount { get; private set; }
        public int ApplyCount { get; private set; }
        public DelegatedGmCharacterEditOutcome? ForcedOutcome { get; set; }
        public Exception? ExceptionToThrow { get; set; }
        public Func<DelegatedGmCharacterEditAuditReceipt, DelegatedGmCharacterEditAuditReceipt>? ReceiptMutator { get; set; }
        public IReadOnlyList<DelegatedGmCharacterEditCommand> Commands => _commands;

        private readonly List<DelegatedGmCharacterEditCommand> _commands = new();

        public void RegisterCharacter(
            string characterOwnerUserId,
            string authoritativeCharacterId,
            string runnerHandle,
            string displayName,
            long revision = 1)
        {
            _profiles[ProfileKey(characterOwnerUserId, authoritativeCharacterId)] = new(
                revision,
                displayName,
                runnerHandle);
        }

        public DelegatedGmCharacterProfile ApplyOwnerEdit(
            string characterOwnerUserId,
            string authoritativeCharacterId,
            string runnerHandle,
            string displayName)
        {
            string key = ProfileKey(characterOwnerUserId, authoritativeCharacterId);
            DelegatedGmCharacterProfile current = _profiles[key];
            var next = new DelegatedGmCharacterProfile(
                current.Revision + 1,
                displayName,
                runnerHandle);
            _profiles[key] = next;
            return next;
        }

        public DelegatedGmCharacterProfileReadResult ReadCurrentProfile(
            DelegatedGmCharacterProfileReadCommand command)
        {
            ReadCount++;
            return _profiles.TryGetValue(
                ProfileKey(command.CharacterOwner.NormalizedValue, command.CharacterId.Value),
                out DelegatedGmCharacterProfile? profile)
                    ? new DelegatedGmCharacterProfileReadResult(
                        DelegatedGmCharacterProfileReadOutcome.Available,
                        profile)
                    : new DelegatedGmCharacterProfileReadResult(
                        DelegatedGmCharacterProfileReadOutcome.Missing);
        }

        public DelegatedGmCharacterEditResult Execute(DelegatedGmCharacterEditCommand command)
        {
            CallCount++;
            _commands.Add(command);
            if (ExceptionToThrow is not null)
            {
                throw ExceptionToThrow;
            }

            if (ForcedOutcome is DelegatedGmCharacterEditOutcome forced)
            {
                return new DelegatedGmCharacterEditResult(forced);
            }

            string profileKey = ProfileKey(
                command.CharacterOwner.NormalizedValue,
                command.CharacterId.Value);
            if (!_profiles.TryGetValue(profileKey, out DelegatedGmCharacterProfile? currentProfile))
            {
                return new DelegatedGmCharacterEditResult(
                    DelegatedGmCharacterEditOutcome.Missing);
            }

            string ledgerKey = $"{profileKey}\0{command.IdempotencyKey}";
            string requestSha256 = Digest(command);
            if (_ledger.TryGetValue(ledgerKey, out var replay))
            {
                if (!string.Equals(replay.RequestSha256, requestSha256, StringComparison.Ordinal))
                {
                    return new DelegatedGmCharacterEditResult(
                        DelegatedGmCharacterEditOutcome.Conflict);
                }

                return new DelegatedGmCharacterEditResult(
                    DelegatedGmCharacterEditOutcome.Replayed,
                    replay.Receipt);
            }

            if (currentProfile.Revision != command.ExpectedRevision)
            {
                return new DelegatedGmCharacterEditResult(
                    DelegatedGmCharacterEditOutcome.Conflict);
            }

            ApplyCount++;
            string idempotencyKeySha256 = Convert.ToHexString(
                    SHA256.HashData(Encoding.UTF8.GetBytes(command.IdempotencyKey)))
                .ToLowerInvariant();
            string runnerHandle = OperationValue(
                command,
                DelegatedGmCharacterEditContract.ProfileAliasPath);
            string displayName = OperationValue(
                command,
                DelegatedGmCharacterEditContract.ProfileNamePath);
            DelegatedGmCharacterEditAuditOperation[] operations =
            [
                AuditOperation(DelegatedGmCharacterEditContract.ProfileAliasPath, runnerHandle),
                AuditOperation(DelegatedGmCharacterEditContract.ProfileNamePath, displayName)
            ];
            CampaignCharacterBindingState binding = _store.CampaignCharacterBindings
                .Where(item => string.Equals(item.CampaignId, command.CampaignId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.AuthoritativeCharacterId, command.CharacterId.Value, StringComparison.Ordinal))
                .OrderByDescending(static item => item.BindingRevision)
                .ThenByDescending(static item => item.RecordedAtUtc)
                .First();
            CampaignProjection campaign = _store.CampaignSpinesById[command.CampaignId];
            GroupDto group = _store.GroupsById[campaign.GroupId];
            string receiptSeed = string.Join(
                "\n",
                requestSha256,
                binding.BindingId,
                binding.BindingVersionId,
                idempotencyKeySha256);
            var receipt = new DelegatedGmCharacterEditAuditReceipt(
                Contract: DelegatedGmCharacterEditContract.Name,
                ReceiptId: $"gm-edit-{Sha256(receiptSeed)[..24]}",
                CampaignId: command.CampaignId,
                DelegationId: binding.BindingId,
                GrantedByCampaignOwnerId: group.OwnerUserId,
                GrantedByCharacterOwnerId: command.CharacterOwner.NormalizedValue,
                AuthorityReceiptId: binding.BindingVersionId,
                AuthorityRevision: binding.BindingRevision,
                ActorId: command.ActorId,
                ActorRole: DelegatedGmCharacterEditContract.GameMasterRole,
                CharacterOwnerId: command.CharacterOwner.NormalizedValue,
                CharacterId: command.CharacterId,
                Reason: command.Reason,
                IdempotencyKeySha256: idempotencyKeySha256,
                CommandSha256: requestSha256,
                PreviousRevision: command.ExpectedRevision,
                NewRevision: command.ExpectedRevision + 1,
                AppliedAtUtc: _clock.GetUtcNow(),
                Operations: operations.ToImmutableArray());
            currentProfile = new DelegatedGmCharacterProfile(
                receipt.NewRevision,
                displayName,
                runnerHandle);
            _profiles[profileKey] = currentProfile;
            receipt = ReceiptMutator?.Invoke(receipt) ?? receipt;
            _ledger[ledgerKey] = (requestSha256, receipt);
            return new DelegatedGmCharacterEditResult(
                DelegatedGmCharacterEditOutcome.Applied,
                receipt);
        }

        private static DelegatedGmCharacterEditAuditOperation AuditOperation(string path, string value)
            => new(
                DelegatedGmCharacterPatchOperationKind.Replace,
                path,
                Sha256(value),
                value.Length);

        private static string OperationValue(DelegatedGmCharacterEditCommand command, string path)
            => Assert.Single(command.Operations, operation => operation.Path == path).Value!;

        private static string Digest(DelegatedGmCharacterEditCommand command)
        {
            StringBuilder builder = new();
            Append(builder, DelegatedGmCharacterEditContract.Name);
            Append(builder, command.CampaignId.Trim());
            Append(builder, command.ActorId.Trim());
            Append(builder, command.CharacterOwner.NormalizedValue);
            Append(builder, command.CharacterId.Value.Trim());
            Append(builder, command.ExpectedRevision.ToString(System.Globalization.CultureInfo.InvariantCulture));
            Append(builder, command.Reason.Trim());
            foreach (DelegatedGmCharacterPatchOperation operation in command.Operations
                         .OrderBy(static item => item.Path?.Trim().ToLowerInvariant(), StringComparer.Ordinal))
            {
                Append(builder, ((int)operation.Operation).ToString(System.Globalization.CultureInfo.InvariantCulture));
                Append(builder, operation.Path.Trim().ToLowerInvariant());
                Append(builder, operation.Value!);
            }

            return Sha256(builder.ToString());
        }

        private static void Append(StringBuilder builder, string value)
            => builder.Append(value.Length.ToString(System.Globalization.CultureInfo.InvariantCulture))
                .Append(':')
                .Append(value)
                .Append('\n');

        private static string Sha256(string value)
            => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))
                .ToLowerInvariant();

        private static string ProfileKey(string characterOwnerUserId, string authoritativeCharacterId)
            => $"{characterOwnerUserId.Trim().ToLowerInvariant()}\0{authoritativeCharacterId}";
    }

    private sealed class RecordingAntiforgery : IAntiforgery
    {
        public bool GetAndStoreCalled { get; private set; }

        public AntiforgeryTokenSet GetAndStoreTokens(HttpContext httpContext)
        {
            GetAndStoreCalled = true;
            return new AntiforgeryTokenSet("request-token", "cookie-token", "__RequestVerificationToken", "X-CSRF-TOKEN");
        }

        public AntiforgeryTokenSet GetTokens(HttpContext httpContext)
            => new("request-token", "cookie-token", "__RequestVerificationToken", "X-CSRF-TOKEN");

        public Task<bool> IsRequestValidAsync(HttpContext httpContext) => Task.FromResult(true);
        public Task ValidateRequestAsync(HttpContext httpContext) => Task.CompletedTask;
        public void SetCookieTokenAndHeader(HttpContext httpContext) { }
    }

    internal sealed class AdjustableTimeProvider : TimeProvider
    {
        private DateTimeOffset _utcNow;
        public AdjustableTimeProvider(DateTimeOffset utcNow) => _utcNow = utcNow;
        public override DateTimeOffset GetUtcNow() => _utcNow;
        public void Advance(TimeSpan elapsed) => _utcNow = _utcNow.Add(elapsed);
    }
}
