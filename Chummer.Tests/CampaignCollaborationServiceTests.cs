using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
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

        Type[] identityDerivedRequests =
        [
            typeof(CreateCampaignCollaborationRequest),
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
            new CreateCampaignInviteRequest(ExpiresInMinutes: 60, MaxUses: 2));

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
    public void RedemptionBindsSelectedExistingOwnerDossierWithoutCreatingPlaceholderAndIsIdempotent()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            new CreateCampaignInviteRequest(60, 1));
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
            new CreateCampaignInviteRequest(60, 2));
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
            new CreateCampaignInviteRequest(60, 2));
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

        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(60, 1));
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
            new CreateCampaignInviteRequest(5, 1));
        fixture.Clock.Advance(TimeSpan.FromMinutes(6));

        CampaignInviteRejectedException expiredError = Assert.Throws<CampaignInviteRejectedException>(() =>
            fixture.Service.RedeemInvite(player, expired.InviteId, fixture.LinkRequest(expired, character, "expired")));
        CampaignInviteSecretProjection revoked = fixture.Service.CreateInvite(
            fixture.Gm,
            campaign.CampaignId,
            new CreateCampaignInviteRequest(60, 1));
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
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(60, 1));
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
            Reason: "Agreed table correction.",
            Sections: [new PublicationSafeProjection("identity", "identity", "Identity", "Razor-2 is ready.")]);

        CampaignSharedSheetEditReceipt receipt = fixture.Service.UpdateSharedSheet(
            fixture.Gm, campaign.CampaignId, joined.DossierId, request);
        CampaignSharedSheetEditReceipt replay = fixture.Service.UpdateSharedSheet(
            fixture.Gm, campaign.CampaignId, joined.DossierId, request);

        Assert.Equal(receipt, replay);
        Assert.Equal(2, receipt.Revision);
        Assert.Equal("Razor-2", fixture.Store.DossiersById[joined.DossierId].RunnerHandle);
        CampaignPlayerSafeSheetProjection persistedProjection = fixture.Service.GetSharedSheet(
            fixture.Gm, campaign.CampaignId, joined.DossierId);
        Assert.Equal("Razor-2", persistedProjection.RunnerHandle);
        Assert.Equal(
            receipt.AfterSha256,
            Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(
                persistedProjection,
                new JsonSerializerOptions(JsonSerializerDefaults.Web)))).ToLowerInvariant());
        Assert.Equal(2, fixture.Store.CampaignCharacterBindings.Count);
        Assert.Single(fixture.Service.GetSharedSheetAuditForTests(joined.DossierId));
        Assert.Throws<CampaignIdempotencyConflictException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            request with { RunnerHandle = "Different" }));
        Assert.Throws<CampaignRevisionConflictException>(() => fixture.Service.UpdateSharedSheet(
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
    public void GmCannotEditWhenOwnerDidNotGrantCharacterAuthority()
    {
        using var fixture = new CampaignFixture();
        CampaignCollaborationProjection campaign = fixture.CreateCampaign();
        HubUserDto player = fixture.CreateUser("subject.player", "Player");
        RunnerDossierProjection character = fixture.CreateCharacter(player, "Razor", "Alex Razor");
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(60, 1));
        CampaignInviteRedemptionProjection joined = fixture.Service.RedeemInvite(
            player,
            invite.InviteId,
            fixture.LinkRequest(invite, character, "no-grant") with { GrantGmEditAuthority = false });

        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => fixture.Service.UpdateSharedSheet(
            fixture.Gm,
            campaign.CampaignId,
            joined.DossierId,
            new CampaignSharedSheetUpdateRequest(1, "edit-denied", "Razor", "Alex Razor", "active", "No grant.")));
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
            new CreateCampaignInviteRequest(60, 1)));
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
            new CreateCampaignInviteRequest(60, 1)));
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
        CampaignInviteSecretProjection invite = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(60, 1));
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
        CampaignInviteSecretProjection first = fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(5, 1));
        for (int index = 1; index < 32; index++)
        {
            fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(60, 1));
        }

        Assert.Throws<InvalidOperationException>(() => fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(60, 1)));
        fixture.Clock.Advance(TimeSpan.FromDays(8));
        fixture.Service.CreateInvite(fixture.Gm, campaign.CampaignId, new(60, 1));
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
            new CampaignRunsiteDraftUpdateRequest(0, "Hidden", "Hidden", [], "player note")));

        CampaignRunsiteDraftProjection first = fixture.Service.UpsertRunsiteDraft(
            fixture.Gm,
            campaign.CampaignId,
            runId,
            new CampaignRunsiteDraftUpdateRequest(
                0,
                "Neon Vault",
                "Meet the Johnson at midnight.",
                [new RunsitePlayerSectionInput("Approach", "Use the freight entrance.")],
                "Secret ambush."));
        CampaignRunsitePlayerProjection published = fixture.Service.PublishRunsite(
            fixture.Gm,
            campaign.CampaignId,
            runId,
            new PublishCampaignRunsiteRequest(first.Revision));
        fixture.Clock.Advance(TimeSpan.FromMinutes(1));
        CampaignRunsitePlayerProjection replay = fixture.Service.PublishRunsite(
            fixture.Gm,
            campaign.CampaignId,
            runId,
            new PublishCampaignRunsiteRequest(first.Revision));

        Assert.DoesNotContain("Secret ambush", JsonSerializer.Serialize(published), StringComparison.OrdinalIgnoreCase);
        Assert.Equal(JsonSerializer.Serialize(published), JsonSerializer.Serialize(replay));
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
        var reloadedService = new CampaignCollaborationService(reloadedStore, fixture.Clock);
        HubUserDto reloadedPlayer = reloadedStore.UsersById[player.UserId];
        Assert.Equal("Razor", reloadedService.GetSharedSheet(reloadedPlayer, campaign.CampaignId, joined.DossierId).RunnerHandle);

        JsonObject root = Assert.IsType<JsonObject>(JsonNode.Parse(File.ReadAllText(fixture.StorePath)));
        JsonArray bindings = Assert.IsType<JsonArray>(root["campaignCharacterBindings"]);
        Assert.IsType<JsonObject>(bindings[0])["authenticatedOwnerUserId"] = "attacker";
        File.WriteAllText(fixture.StorePath, root.ToJsonString());
        Assert.Throws<InvalidDataException>(() =>
            new CommunityStore(fixture.Configuration, NullLogger<CommunityStore>.Instance));
    }

    private static string PadBase64Url(string value)
    {
        string padded = value.Replace('-', '+').Replace('_', '/');
        padded += (padded.Length % 4) switch { 2 => "==", 3 => "=", _ => string.Empty };
        return padded;
    }

    private sealed class CampaignFixture : IDisposable
    {
        private readonly string _directory;

        public CampaignFixture()
        {
            _directory = Path.Combine(Path.GetTempPath(), "chummer-campaign-collaboration-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_directory);
            StorePath = Path.Combine(_directory, "community-store.json");
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_COMMUNITY_STORE_PATH"] = StorePath })
                .Build();
            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Store);
            Clock = new AdjustableTimeProvider(DateTimeOffset.Parse("2026-07-20T12:00:00Z"));
            Service = new CampaignCollaborationService(Store, Clock);
            Gm = CreateUser("subject.gm", "Game Master");
        }

        public string StorePath { get; }
        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public AccountService Accounts { get; }
        public AdjustableTimeProvider Clock { get; }
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
                Store.PersistLocked();
                return dossier;
            }
        }

        public CampaignCollaborationProjection CreateCampaign(string name = "Neon Shadows")
            => Service.CreateCampaign(Gm, new CreateCampaignCollaborationRequest(name, $"{name} summary", "private", $"{name} first run"));

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
            CampaignInviteSecretProjection invite = Service.CreateInvite(Gm, campaign.CampaignId, new(60, 1));
            return Service.RedeemInvite(player, invite.InviteId, LinkRequest(invite, character, $"join-{Guid.NewGuid():N}"));
        }

        public void Dispose()
        {
            try { Directory.Delete(_directory, recursive: true); }
            catch { }
        }
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
