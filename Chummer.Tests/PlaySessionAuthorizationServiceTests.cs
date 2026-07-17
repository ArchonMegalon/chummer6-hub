using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PlaySessionAuthorizationServiceTests
{
    private const string SessionId = "session-1";
    private const string GameMasterUserId = "gm-user";
    private const string PlayerUserId = "player-user";
    private static readonly string DeviceThumbprint = new('d', 64);
    private static readonly DateTimeOffset BaselineUtc = new(2026, 7, 14, 8, 0, 0, TimeSpan.Zero);

    [Fact]
    public void FullFlowReturnsEachOpaqueSecretOnceAndPersistsOnlyHashes()
    {
        using ServiceFixture fixture = new();

        IssuedPlaySessionInvite invite = fixture.IssueInvite();
        IssuedPlaySessionExchange exchange = fixture.Redeem(invite);
        IssuedPlaySessionGrant grant = fixture.Consume(exchange);
        PlaySessionAuthorizationResult<PlaySessionGrantContext> introspection = fixture.Service.IntrospectGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.True(introspection.Succeeded);
        Assert.Equal(43, invite.Secret.Length);
        Assert.Equal(43, exchange.Secret.Length);
        Assert.Equal(43, grant.Secret.Length);
        Assert.Equal(3, new[] { invite.Secret, exchange.Secret, grant.Secret }.Distinct(StringComparer.Ordinal).Count());
        Assert.Equal(Hash(invite.Secret), invite.Invite.SecretHashSha256);
        Assert.Equal(Hash(exchange.Secret), exchange.Exchange.SecretHashSha256);
        Assert.Equal(Hash(grant.Secret), grant.Grant.SecretHashSha256);

        string persisted = File.ReadAllText(fixture.StoragePath);
        Assert.DoesNotContain(invite.Secret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(exchange.Secret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(grant.Secret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain("persistence_failed", persisted, StringComparison.Ordinal);
    }

    [Fact]
    public void CredentialsAreStrictlyBoundToTargetSessionRoleAndDevice()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite invite = fixture.IssueInvite();

        PlaySessionAuthorizationResult<IssuedPlaySessionExchange> wrongTarget = fixture.Service.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            "other-user",
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.False(wrongTarget.Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.BindingMismatch, wrongTarget.Reason);
        Assert.Equal(PlaySessionStatuses.Active, fixture.Store.PlayInvitesById[invite.Invite.InviteId].Status);

        IssuedPlaySessionExchange exchange = fixture.Redeem(invite);
        PlaySessionAuthorizationResult<IssuedPlaySessionGrant> wrongDevice = fixture.Service.ConsumeExchange(
            exchange.Exchange.ExchangeId,
            exchange.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            new string('e', 64));

        Assert.False(wrongDevice.Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.BindingMismatch, wrongDevice.Reason);
        Assert.Equal(PlaySessionStatuses.Revoked, fixture.Store.PlayExchangesById[exchange.Exchange.ExchangeId].Status);
    }

    [Fact]
    public void InviteExchangeAndGrantExpiryArePersistedAndCannotBeReplayed()
    {
        using ServiceFixture inviteFixture = new();
        IssuedPlaySessionInvite invite = inviteFixture.IssueInvite(TimeSpan.FromMinutes(1));
        inviteFixture.Time.Advance(TimeSpan.FromMinutes(1));
        PlaySessionAuthorizationResult<IssuedPlaySessionExchange> expiredInvite = inviteFixture.Service.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);
        Assert.Equal(PlaySessionAuthorizationReasons.InviteExpired, expiredInvite.Reason);
        Assert.Equal(PlaySessionStatuses.Expired, inviteFixture.Store.PlayInvitesById[invite.Invite.InviteId].Status);

        using ServiceFixture exchangeFixture = new();
        IssuedPlaySessionExchange exchange = exchangeFixture.Redeem(exchangeFixture.IssueInvite(), TimeSpan.FromSeconds(10));
        exchangeFixture.Time.Advance(TimeSpan.FromSeconds(10));
        PlaySessionAuthorizationResult<IssuedPlaySessionGrant> expiredExchange = exchangeFixture.Service.ConsumeExchange(
            exchange.Exchange.ExchangeId,
            exchange.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);
        Assert.Equal(PlaySessionAuthorizationReasons.ExchangeExpired, expiredExchange.Reason);
        Assert.Equal(PlaySessionStatuses.Expired, exchangeFixture.Store.PlayExchangesById[exchange.Exchange.ExchangeId].Status);

        using ServiceFixture grantFixture = new();
        IssuedPlaySessionGrant grant = grantFixture.Consume(grantFixture.Redeem(grantFixture.IssueInvite()), TimeSpan.FromSeconds(30));
        grantFixture.Time.Advance(TimeSpan.FromSeconds(30));
        PlaySessionAuthorizationResult<PlaySessionGrantContext> expiredGrant = grantFixture.Service.IntrospectGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);
        Assert.Equal(PlaySessionAuthorizationReasons.GrantExpired, expiredGrant.Reason);
        Assert.Equal(PlaySessionStatuses.Expired, grantFixture.Store.PlayGrantsById[grant.Grant.GrantId].Status);
    }

    [Fact]
    public void ConcurrentInviteRedemptionHasExactlyOneWinner()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite invite = fixture.IssueInvite();
        ConcurrentBag<PlaySessionAuthorizationResult<IssuedPlaySessionExchange>> results = [];

        Parallel.For(0, 32, _ => results.Add(fixture.Service.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint)));

        Assert.Single(results, static result => result.Succeeded);
        Assert.Equal(31, results.Count(result => result.Reason == PlaySessionAuthorizationReasons.InviteReplayed));
        Assert.Single(fixture.Store.PlayExchangesById);
    }

    [Fact]
    public void ConcurrentExchangeConsumptionHasExactlyOneWinner()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionExchange exchange = fixture.Redeem(fixture.IssueInvite());
        ConcurrentBag<PlaySessionAuthorizationResult<IssuedPlaySessionGrant>> results = [];

        Parallel.For(0, 32, _ => results.Add(fixture.Service.ConsumeExchange(
            exchange.Exchange.ExchangeId,
            exchange.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint)));

        Assert.Single(results, static result => result.Succeeded);
        Assert.Equal(31, results.Count(result => result.Reason == PlaySessionAuthorizationReasons.ExchangeReplayed));
        Assert.Single(fixture.Store.PlayGrantsById);
    }

    [Fact]
    public void RefreshRotatesTheSecretAndTheOldSecretImmediatelyFails()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionGrant grant = fixture.Consume(fixture.Redeem(fixture.IssueInvite()));

        PlaySessionAuthorizationResult<IssuedPlaySessionGrant> refreshed = fixture.Service.RefreshGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.True(refreshed.Succeeded);
        Assert.NotEqual(grant.Secret, refreshed.Value!.Secret);
        Assert.Equal(Hash(refreshed.Value.Secret), fixture.Store.PlayGrantsById[grant.Grant.GrantId].SecretHashSha256);
        Assert.Equal(PlaySessionAuthorizationReasons.GrantInvalid, fixture.Service.IntrospectGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Reason);
        Assert.True(fixture.Service.IntrospectGrant(
            grant.Grant.GrantId,
            refreshed.Value.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Succeeded);
    }

    [Fact]
    public void SessionAndParticipantVersionDriftRevokeExistingGrants()
    {
        using ServiceFixture sessionFixture = new();
        IssuedPlaySessionGrant sessionGrant = sessionFixture.Consume(sessionFixture.Redeem(sessionFixture.IssueInvite()));
        Assert.True(sessionFixture.Service.BumpSessionAuthorizationVersion(SessionId, GameMasterUserId).Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.VersionDrift, sessionFixture.Service.IntrospectGrant(
            sessionGrant.Grant.GrantId,
            sessionGrant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Reason);

        using ServiceFixture participantFixture = new();
        IssuedPlaySessionGrant participantGrant = participantFixture.Consume(participantFixture.Redeem(participantFixture.IssueInvite()));
        string participantId = participantGrant.Grant.ParticipantId;
        Assert.True(participantFixture.Service.BumpParticipantAuthorizationVersion(participantId, GameMasterUserId).Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.VersionDrift, participantFixture.Service.IntrospectGrant(
            participantGrant.Grant.GrantId,
            participantGrant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Reason);
    }

    [Fact]
    public void ParticipantVersionBumpInvalidatesAnAlreadyIssuedInvite()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite invite = fixture.IssueInvite();
        Assert.True(fixture.Service.BumpParticipantAuthorizationVersion(
            invite.Invite.ParticipantId!,
            GameMasterUserId).Succeeded);

        PlaySessionAuthorizationResult<IssuedPlaySessionExchange> denied = fixture.Service.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.False(denied.Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.VersionDrift, denied.Reason);
        Assert.Equal(PlaySessionStatuses.Revoked, fixture.Store.PlayInvitesById[invite.Invite.InviteId].Status);
    }

    [Fact]
    public void CanonicalMembershipDriftAndExplicitRevocationInvalidateExistingGrants()
    {
        using ServiceFixture membershipFixture = new();
        IssuedPlaySessionGrant membershipGrant = membershipFixture.Consume(
            membershipFixture.Redeem(membershipFixture.IssueInvite()));
        CrewProjection crew = membershipFixture.Store.CrewsById["crew-1"];
        membershipFixture.Store.CrewsById[crew.CrewId] = crew with { Members = [] };
        membershipFixture.Store.PersistLocked();

        PlaySessionAuthorizationResult<PlaySessionGrantContext> membershipDenied =
            membershipFixture.Service.IntrospectGrant(
                membershipGrant.Grant.GrantId,
                membershipGrant.Secret,
                SessionId,
                PlayerUserId,
                PlaySessionRoles.Player,
                DeviceThumbprint);
        Assert.Equal(PlaySessionAuthorizationReasons.MembershipDrift, membershipDenied.Reason);
        Assert.Equal(
            PlaySessionStatuses.Revoked,
            membershipFixture.Store.PlayGrantsById[membershipGrant.Grant.GrantId].Status);

        using ServiceFixture revocationFixture = new();
        IssuedPlaySessionGrant revokedGrant = revocationFixture.Consume(
            revocationFixture.Redeem(revocationFixture.IssueInvite()));
        Assert.True(revocationFixture.Service.RevokeParticipant(
            revokedGrant.Grant.ParticipantId,
            GameMasterUserId).Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.MembershipDrift, revocationFixture.Service.IntrospectGrant(
            revokedGrant.Grant.GrantId,
            revokedGrant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Reason);
    }

    [Fact]
    public void UserOrGameMasterCanRevokeAGrantAndItCannotBeUsedAgain()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionGrant grant = fixture.Consume(fixture.Redeem(fixture.IssueInvite()));

        PlaySessionAuthorizationResult<PlaySessionGrant> revoked = fixture.Service.RevokeGrant(
            grant.Grant.GrantId,
            SessionId,
            PlayerUserId);

        Assert.True(revoked.Succeeded);
        Assert.Equal(PlaySessionStatuses.Revoked, revoked.Value!.Status);
        Assert.Equal(PlaySessionAuthorizationReasons.GrantRevoked, fixture.Service.IntrospectGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Reason);
    }

    [Fact]
    public void SessionClosureRevokesEveryLiveChildAuthority()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionGrant grant = fixture.Consume(fixture.Redeem(fixture.IssueInvite()));
        IssuedPlaySessionInvite spareInvite = fixture.IssueInvite();

        PlaySessionAuthorizationResult<PlaySessionBinding> closed = fixture.Service.CloseSession(
            SessionId,
            GameMasterUserId);

        Assert.True(closed.Succeeded);
        Assert.Equal(PlaySessionStatuses.Closed, closed.Value!.Status);
        Assert.All(fixture.Store.PlayParticipantsById.Values, participant =>
            Assert.Equal(PlaySessionStatuses.Revoked, participant.Status));
        Assert.Equal(PlaySessionStatuses.Revoked, fixture.Store.PlayInvitesById[spareInvite.Invite.InviteId].Status);
        Assert.Equal(PlaySessionStatuses.Revoked, fixture.Store.PlayGrantsById[grant.Grant.GrantId].Status);
    }

    [Fact]
    public void RestartPreservesGrantValidityAndInviteAndExchangeReplayState()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite invite = fixture.IssueInvite();
        IssuedPlaySessionExchange exchange = fixture.Redeem(invite);
        IssuedPlaySessionGrant grant = fixture.Consume(exchange);

        CommunityStore reloaded = fixture.Reload();
        PlaySessionAuthorizationService restarted = new(reloaded, fixture.Time);

        Assert.True(restarted.IntrospectGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.InviteReplayed, restarted.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Reason);
        Assert.Equal(PlaySessionAuthorizationReasons.ExchangeReplayed, restarted.ConsumeExchange(
            exchange.Exchange.ExchangeId,
            exchange.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Reason);
    }

    [Fact]
    public void InviteRedemptionPersistenceFailureRollsBackFileAndAllMapsAndLeavesSecretReusable()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite invite = fixture.IssueInvite();
        AuthorizationState before = Capture(fixture);
        PlaySessionAuthorizationService failing = fixture.WithPersistence(new PersistThenThrow());

        PlaySessionAuthorizationResult<IssuedPlaySessionExchange> failed = failing.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.False(failed.Succeeded);
        Assert.Null(failed.Value);
        Assert.Equal(PlaySessionAuthorizationReasons.PersistenceFailed, failed.Reason);
        AssertStateEqual(before, Capture(fixture));
        Assert.Equal(PlaySessionStatuses.Active, fixture.Store.PlayInvitesById[invite.Invite.InviteId].Status);
        Assert.True(fixture.Service.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Succeeded);
    }

    [Fact]
    public void ExchangeConsumptionPersistenceFailureRollsBackFileAndAllMapsAndLeavesSecretReusable()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionExchange exchange = fixture.Redeem(fixture.IssueInvite());
        AuthorizationState before = Capture(fixture);
        PlaySessionAuthorizationService failing = fixture.WithPersistence(new PersistThenThrow());

        PlaySessionAuthorizationResult<IssuedPlaySessionGrant> failed = failing.ConsumeExchange(
            exchange.Exchange.ExchangeId,
            exchange.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.False(failed.Succeeded);
        Assert.Null(failed.Value);
        Assert.Equal(PlaySessionAuthorizationReasons.PersistenceFailed, failed.Reason);
        AssertStateEqual(before, Capture(fixture));
        Assert.Equal(PlaySessionStatuses.Pending, fixture.Store.PlayExchangesById[exchange.Exchange.ExchangeId].Status);
        Assert.True(fixture.Service.ConsumeExchange(
            exchange.Exchange.ExchangeId,
            exchange.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Succeeded);
    }

    [Theory]
    [InlineData("grant_revoke")]
    [InlineData("session_version")]
    [InlineData("participant_version")]
    [InlineData("participant_revoke")]
    [InlineData("session_close")]
    public void AdministrativeMutationPersistenceFailureRollsBackFileAndAllFiveMaps(string operation)
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionGrant grant = fixture.Consume(fixture.Redeem(fixture.IssueInvite()));
        AuthorizationState before = Capture(fixture);
        PlaySessionAuthorizationService failing = fixture.WithPersistence(new PersistThenThrow());

        (bool succeeded, string reason) = operation switch
        {
            "grant_revoke" => Summarize(failing.RevokeGrant(grant.Grant.GrantId, SessionId, GameMasterUserId)),
            "session_version" => Summarize(failing.BumpSessionAuthorizationVersion(SessionId, GameMasterUserId)),
            "participant_version" => Summarize(failing.BumpParticipantAuthorizationVersion(
                grant.Grant.ParticipantId,
                GameMasterUserId)),
            "participant_revoke" => Summarize(failing.RevokeParticipant(
                grant.Grant.ParticipantId,
                GameMasterUserId)),
            "session_close" => Summarize(failing.CloseSession(SessionId, GameMasterUserId)),
            _ => throw new ArgumentOutOfRangeException(nameof(operation))
        };

        Assert.False(succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.PersistenceFailed, reason);
        AssertStateEqual(before, Capture(fixture));
        Assert.True(fixture.Service.IntrospectGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Succeeded);
    }

    [Theory]
    [InlineData("session_create")]
    [InlineData("participant_add")]
    [InlineData("invite_issue")]
    [InlineData("grant_refresh")]
    public void CreationIssuanceAndRefreshPersistenceFailureAlsoRollBackEveryAuthorityMap(string operation)
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionGrant grant = fixture.Consume(fixture.Redeem(fixture.IssueInvite()));
        AuthorizationState before = Capture(fixture);
        PlaySessionAuthorizationService failing = fixture.WithPersistence(new PersistThenThrow());

        (bool succeeded, string reason) = operation switch
        {
            "session_create" => Summarize(failing.CreateSessionBinding(
                "session-rollback",
                "campaign-1",
                "run-1",
                "group-1",
                GameMasterUserId)),
            "participant_add" => Summarize(failing.AddParticipant(
                SessionId,
                GameMasterUserId,
                "observer-user",
                PlaySessionRoles.Observer)),
            "invite_issue" => Summarize(failing.IssueInvite(
                SessionId,
                GameMasterUserId,
                PlayerUserId,
                PlaySessionRoles.Player)),
            "grant_refresh" => Summarize(failing.RefreshGrant(
                grant.Grant.GrantId,
                grant.Secret,
                SessionId,
                PlayerUserId,
                PlaySessionRoles.Player,
                DeviceThumbprint)),
            _ => throw new ArgumentOutOfRangeException(nameof(operation))
        };

        Assert.False(succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.PersistenceFailed, reason);
        AssertStateEqual(before, Capture(fixture));
        Assert.True(fixture.Service.IntrospectGrant(
            grant.Grant.GrantId,
            grant.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint).Succeeded);
    }

    [Fact]
    public void LegacyExchangeWithoutAuthorityBindingsIsRejectedBeforePersistence()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite invite = fixture.IssueInvite();
        fixture.Store.PlayInvitesById[invite.Invite.InviteId] = invite.Invite with
        {
            ParticipantId = null,
            ParticipantAuthorizationVersion = 0
        };
        string raw = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');
        PlaySessionExchange legacy = new(
            ExchangeId: "legacy-exchange",
            InviteId: invite.Invite.InviteId,
            GrantId: null,
            SecretHashSha256: Hash(raw),
            Status: PlaySessionStatuses.Pending,
            SessionAuthorizationVersion: 1,
            CreatedAtUtc: fixture.Time.GetUtcNow(),
            UpdatedAtUtc: fixture.Time.GetUtcNow(),
            ExpiresAtUtc: fixture.Time.GetUtcNow().AddMinutes(1));
        fixture.Store.PlayExchangesById.Add(legacy.ExchangeId, legacy);
        JsonException error = Assert.Throws<JsonException>(() => fixture.Store.PersistLocked());

        Assert.Contains("SessionId", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void LifetimesOutsideHardBoundsAreRejectedWithoutMutation()
    {
        using ServiceFixture fixture = new();
        int before = fixture.Store.PlayInvitesById.Count;

        PlaySessionAuthorizationResult<IssuedPlaySessionInvite> denied = fixture.Service.IssueInvite(
            SessionId,
            GameMasterUserId,
            PlayerUserId,
            PlaySessionRoles.Player,
            TimeSpan.FromHours(1));

        Assert.False(denied.Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.InvalidRequest, denied.Reason);
        Assert.Equal(before, fixture.Store.PlayInvitesById.Count);
    }

    [Fact]
    public void CorruptExpectedSecretHashFailsClosedWithoutThrowing()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite invite = fixture.IssueInvite();
        fixture.Store.PlayInvitesById[invite.Invite.InviteId] = invite.Invite with
        {
            SecretHashSha256 = "not-a-canonical-sha256"
        };

        PlaySessionAuthorizationResult<IssuedPlaySessionExchange> denied = fixture.Service.RedeemInvite(
            invite.Invite.InviteId,
            invite.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.False(denied.Succeeded);
        Assert.Equal(PlaySessionAuthorizationReasons.InviteInvalid, denied.Reason);
        Assert.Empty(fixture.Store.PlayExchangesById);
    }

    [Fact]
    public void PersistedHighWaterAndMonotonicElapsedTimePreventBackwardClockExpiryExtension()
    {
        using ServiceFixture fixture = new();
        IssuedPlaySessionInvite expiring = fixture.IssueInvite(TimeSpan.FromMinutes(1));
        fixture.Time.Advance(TimeSpan.FromSeconds(50));
        _ = fixture.IssueInvite(TimeSpan.FromMinutes(1));

        fixture.Time.SetUtcNow(BaselineUtc.AddHours(-1));
        CommunityStore reloaded = fixture.Reload();
        PlaySessionAuthorizationService restarted = new(reloaded, fixture.Time);
        fixture.Time.Advance(TimeSpan.FromSeconds(10));

        PlaySessionAuthorizationResult<IssuedPlaySessionExchange> denied = restarted.RedeemInvite(
            expiring.Invite.InviteId,
            expiring.Secret,
            SessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            DeviceThumbprint);

        Assert.Equal(PlaySessionAuthorizationReasons.InviteExpired, denied.Reason);
        Assert.Equal(BaselineUtc.AddMinutes(1), reloaded.PlayAuthorizationTimeHighWaterUtc);
    }

    private static AuthorizationState Capture(ServiceFixture fixture)
    {
        string maps = JsonSerializer.Serialize(new
        {
            Sessions = fixture.Store.PlaySessionsById.Values.OrderBy(static value => value.SessionId).ToArray(),
            Participants = fixture.Store.PlayParticipantsById.Values.OrderBy(static value => value.ParticipantId).ToArray(),
            Invites = fixture.Store.PlayInvitesById.Values.OrderBy(static value => value.InviteId).ToArray(),
            Exchanges = fixture.Store.PlayExchangesById.Values.OrderBy(static value => value.ExchangeId).ToArray(),
            Grants = fixture.Store.PlayGrantsById.Values.OrderBy(static value => value.GrantId).ToArray(),
            TimeHighWaterUtc = fixture.Store.PlayAuthorizationTimeHighWaterUtc
        });
        return new AuthorizationState(maps, File.ReadAllBytes(fixture.StoragePath));
    }

    private static void AssertStateEqual(AuthorizationState expected, AuthorizationState actual)
    {
        Assert.Equal(expected.MapsJson, actual.MapsJson);
        Assert.True(expected.FileBytes.SequenceEqual(actual.FileBytes));
    }

    private static (bool Succeeded, string Reason) Summarize<T>(PlaySessionAuthorizationResult<T> result)
        where T : class
        => (result.Succeeded, result.Reason);

    private static string Hash(string raw)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(raw))).ToLowerInvariant();

    private sealed record AuthorizationState(string MapsJson, byte[] FileBytes);

    private sealed class PersistThenThrow : IPlaySessionAuthorizationPersistence
    {
        public void PersistLocked(CommunityStore store)
        {
            store.PersistLocked();
            throw new IOException("injected persistence failure");
        }
    }

    private sealed class ManualTimeProvider(DateTimeOffset initialUtc) : TimeProvider
    {
        private DateTimeOffset _utcNow = initialUtc;
        private long _timestamp;

        public override DateTimeOffset GetUtcNow() => _utcNow;

        public override long GetTimestamp() => _timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public void Advance(TimeSpan duration)
        {
            _utcNow = _utcNow.Add(duration);
            _timestamp = checked(_timestamp + duration.Ticks);
        }

        public void SetUtcNow(DateTimeOffset value) => _utcNow = value;
    }

    private sealed class ServiceFixture : IDisposable
    {
        public ServiceFixture()
        {
            RootPath = Path.Combine(Path.GetTempPath(), $"chummer-play-service-{Guid.NewGuid():N}");
            Directory.CreateDirectory(RootPath);
            StoragePath = Path.Combine(RootPath, "community-store.json");
            Store = CreateStore(StoragePath);
            SeedCanonicalAuthority(Store);
            Store.PersistLocked();
            Time = new ManualTimeProvider(BaselineUtc);
            Service = new PlaySessionAuthorizationService(Store, Time);

            PlaySessionAuthorizationResult<PlaySessionBindingCreated> session = Service.CreateSessionBinding(
                SessionId,
                "campaign-1",
                "run-1",
                "group-1",
                GameMasterUserId);
            Assert.True(session.Succeeded, session.Reason);
            PlaySessionAuthorizationResult<PlaySessionParticipant> participant = Service.AddParticipant(
                SessionId,
                GameMasterUserId,
                PlayerUserId,
                PlaySessionRoles.Player);
            Assert.True(participant.Succeeded, participant.Reason);
        }

        public string RootPath { get; }
        public string StoragePath { get; }
        public CommunityStore Store { get; }
        public ManualTimeProvider Time { get; }
        public PlaySessionAuthorizationService Service { get; }

        public IssuedPlaySessionInvite IssueInvite(TimeSpan? lifetime = null)
        {
            PlaySessionAuthorizationResult<IssuedPlaySessionInvite> result = Service.IssueInvite(
                SessionId,
                GameMasterUserId,
                PlayerUserId,
                PlaySessionRoles.Player,
                lifetime);
            Assert.True(result.Succeeded, result.Reason);
            return result.Value!;
        }

        public IssuedPlaySessionExchange Redeem(
            IssuedPlaySessionInvite invite,
            TimeSpan? lifetime = null)
        {
            PlaySessionAuthorizationResult<IssuedPlaySessionExchange> result = Service.RedeemInvite(
                invite.Invite.InviteId,
                invite.Secret,
                SessionId,
                PlayerUserId,
                PlaySessionRoles.Player,
                DeviceThumbprint,
                lifetime);
            Assert.True(result.Succeeded, result.Reason);
            return result.Value!;
        }

        public IssuedPlaySessionGrant Consume(
            IssuedPlaySessionExchange exchange,
            TimeSpan? lifetime = null)
        {
            PlaySessionAuthorizationResult<IssuedPlaySessionGrant> result = Service.ConsumeExchange(
                exchange.Exchange.ExchangeId,
                exchange.Secret,
                SessionId,
                PlayerUserId,
                PlaySessionRoles.Player,
                DeviceThumbprint,
                lifetime);
            Assert.True(result.Succeeded, result.Reason);
            return result.Value!;
        }

        public PlaySessionAuthorizationService WithPersistence(IPlaySessionAuthorizationPersistence persistence)
            => new(Store, Time, persistence);

        public CommunityStore Reload() => CreateStore(StoragePath);

        public void Dispose()
        {
            if (Directory.Exists(RootPath))
            {
                Directory.Delete(RootPath, recursive: true);
            }
        }

        private static CommunityStore CreateStore(string storagePath)
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = storagePath
                })
                .Build();
            return new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
        }

        private static void SeedCanonicalAuthority(CommunityStore store)
        {
            GroupDto group = new(
                GroupId: "group-1",
                GroupType: "campaign",
                Name: "Play Test Group",
                Visibility: "private",
                OwnerUserId: GameMasterUserId,
                Capabilities: [],
                Memberships: [],
                CreatedAtUtc: BaselineUtc,
                UpdatedAtUtc: BaselineUtc);
            CampaignProjection campaign = new(
                CampaignId: "campaign-1",
                GroupId: group.GroupId,
                Name: "Play Test Campaign",
                Status: "active",
                Visibility: "private",
                Summary: "Test campaign",
                RuleEnvironment: new RuleEnvironmentRef(
                    EnvironmentId: "rules-1",
                    OwnerScope: "campaign",
                    CompatibilityFingerprint: "rules-v1",
                    ApprovalState: "approved",
                    SourcePacks: [],
                    HouseRulePacks: [],
                    OptionToggles: []),
                ActiveRunId: "run-1",
                CrewIds: ["crew-1"],
                DossierIds: [],
                RunIds: ["run-1"],
                LatestContinuity: null,
                CreatedAtUtc: BaselineUtc,
                UpdatedAtUtc: BaselineUtc);
            RunProjection run = new(
                RunId: "run-1",
                CampaignId: campaign.CampaignId,
                Title: "Play Test Run",
                Status: "active",
                Summary: "Test run",
                ActiveSceneId: null,
                Objectives: [],
                Scenes: [],
                LatestContinuity: null,
                CreatedAtUtc: BaselineUtc,
                UpdatedAtUtc: BaselineUtc);
            CrewProjection crew = new(
                CrewId: "crew-1",
                Name: "Play Test Crew",
                Visibility: "private",
                GroupId: group.GroupId,
                CampaignId: campaign.CampaignId,
                Members:
                [
                    new CrewAssignmentProjection(
                        UserId: PlayerUserId,
                        DossierId: "dossier-1",
                        Role: "runner",
                        Availability: "available",
                        AddedAtUtc: BaselineUtc)
                ],
                CreatedAtUtc: BaselineUtc,
                UpdatedAtUtc: BaselineUtc);

            store.GroupsById.Add(group.GroupId, group);
            store.CampaignSpinesById.Add(campaign.CampaignId, campaign);
            store.RunsById.Add(run.RunId, run);
            store.CrewsById.Add(crew.CrewId, crew);
        }
    }
}
