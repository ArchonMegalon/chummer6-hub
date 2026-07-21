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
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
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

        public CampaignFixture()
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
            Service = new CampaignCollaborationService(Store, CanonicalEdits, DataProtection, Clock);
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
