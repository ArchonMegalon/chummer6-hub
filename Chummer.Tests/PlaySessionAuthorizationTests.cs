using System.Collections.Concurrent;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PlaySessionAuthorizationTests
{
    private static readonly DateTimeOffset BaselineUtc = new(2026, 7, 14, 6, 0, 0, TimeSpan.Zero);

    [Fact]
    public void CommunityStoreRoundTripsAllPlayAuthorizationRecordsWithoutRawSecrets()
    {
        using StoreFixture fixture = new();
        AddCompleteAuthorizationGraph(fixture.Store);

        fixture.Store.PersistLocked();

        CommunityStore reloaded = fixture.Reload();
        Assert.Single(reloaded.PlaySessionsById);
        Assert.Single(reloaded.PlayParticipantsById);
        Assert.Single(reloaded.PlayInvitesById);
        Assert.Single(reloaded.PlayExchangesById);
        Assert.Single(reloaded.PlayGrantsById);
        Assert.Equal(3, reloaded.PlaySessionsById["session-1"].AuthorizationVersion);
        Assert.Equal(PlaySessionRoles.Player, reloaded.PlayGrantsById["grant-1"].Role);

        string persisted = File.ReadAllText(fixture.StoragePath);
        Assert.Contains(new string('a', 64), persisted, StringComparison.Ordinal);
        Assert.Contains(new string('b', 64), persisted, StringComparison.Ordinal);
        Assert.Contains(new string('c', 64), persisted, StringComparison.Ordinal);
        Assert.DoesNotContain("raw-secret", persisted, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("\"secret\":", persisted, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("\"token\":", persisted, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LegacySnapshotLoadsWithEmptyPlayAuthorizationCollectionsAndMigratesOnWrite()
    {
        using StoreFixture fixture = new(createStore: false);
        File.WriteAllText(fixture.StoragePath, "{\"users\":[],\"groups\":[]}");

        CommunityStore migrated = fixture.Reload();

        Assert.Empty(migrated.PlaySessionsById);
        Assert.Empty(migrated.PlayParticipantsById);
        Assert.Empty(migrated.PlayInvitesById);
        Assert.Empty(migrated.PlayExchangesById);
        Assert.Empty(migrated.PlayGrantsById);
        migrated.PersistLocked();

        using JsonDocument document = JsonDocument.Parse(File.ReadAllText(fixture.StoragePath));
        Assert.Equal(JsonValueKind.Array, document.RootElement.GetProperty("playSessions").ValueKind);
        Assert.Equal(JsonValueKind.Array, document.RootElement.GetProperty("playParticipants").ValueKind);
        Assert.Equal(JsonValueKind.Array, document.RootElement.GetProperty("playInvites").ValueKind);
        Assert.Equal(JsonValueKind.Array, document.RootElement.GetProperty("playExchanges").ValueKind);
        Assert.Equal(JsonValueKind.Array, document.RootElement.GetProperty("playGrants").ValueKind);
    }

    [Fact]
    public void InvalidInMemoryAuthorizationRecordIsRejectedBeforeAnyWrite()
    {
        using StoreFixture fixture = new();
        PlaySessionBinding session = BuildSession();
        fixture.Store.PlaySessionsById[session.SessionId] = session;
        PlaySessionInvite invalid = BuildInvite() with { SecretHashSha256 = "raw-secret" };
        fixture.Store.PlayInvitesById[invalid.InviteId] = invalid;

        JsonException error = Assert.Throws<JsonException>(() => fixture.Store.PersistLocked());

        Assert.Contains("never a raw secret", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(fixture.StoragePath));
    }

    [Fact]
    public void StructurallyInvalidPersistedAuthorizationRecordIsQuarantinedAndRejected()
    {
        using StoreFixture fixture = new();
        AddCompleteAuthorizationGraph(fixture.Store);
        fixture.Store.PersistLocked();
        string persisted = File.ReadAllText(fixture.StoragePath);
        File.WriteAllText(fixture.StoragePath, persisted.Replace(new string('a', 64), "raw-secret", StringComparison.Ordinal));

        CommunityStore rejected = fixture.Reload();

        Assert.Empty(rejected.PlaySessionsById);
        Assert.Empty(rejected.PlayInvitesById);
        Assert.False(File.Exists(fixture.StoragePath));
        Assert.Single(Directory.EnumerateFiles(fixture.RootPath, "community-store.json.corrupt-*"));
    }

    [Fact]
    public void MalformedSnapshotIsQuarantinedAndRestartedEmpty()
    {
        using StoreFixture fixture = new(createStore: false);
        File.WriteAllText(fixture.StoragePath, "{not-json");

        CommunityStore rejected = fixture.Reload();

        Assert.Empty(rejected.PlaySessionsById);
        Assert.False(File.Exists(fixture.StoragePath));
        Assert.Single(Directory.EnumerateFiles(fixture.RootPath, "community-store.json.corrupt-*"));
    }

    [Fact]
    public void PersistenceIsDeterministicUnderConcurrentWritersOnOneStore()
    {
        using StoreFixture fixture = new();

        Parallel.For(0, 24, index =>
        {
            string sessionId = $"session-{index:D2}";
            lock (fixture.Store.Gate)
            {
                fixture.Store.PlaySessionsById.Add(sessionId, BuildSession(sessionId));
            }

            fixture.Store.PersistLocked();
        });

        CommunityStore reloaded = fixture.Reload();
        Assert.Equal(24, reloaded.PlaySessionsById.Count);
        string json = File.ReadAllText(fixture.StoragePath);
        int previousIndex = -1;
        for (int index = 0; index < 24; index++)
        {
            int currentIndex = json.IndexOf($"session-{index:D2}", StringComparison.Ordinal);
            Assert.True(currentIndex > previousIndex);
            previousIndex = currentIndex;
        }
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("admin")]
    [InlineData("manager")]
    [InlineData("gm")]
    public void GameMasterRequiresCanonicalGroupOperatorRole(string operatorRole)
    {
        PlaySessionAuthorizationFacts facts = BuildFacts(PlaySessionRoles.GameMaster) with
        {
            Group = BuildGroup(operatorRole)
        };

        PlaySessionRoleResolution resolution = PlaySessionRoleResolver.Resolve(facts);

        Assert.True(resolution.Authorized);
        Assert.Equal(PlaySessionRoles.GameMaster, resolution.Role);
        Assert.Equal(PlaySessionParticipantSources.GroupOperator, resolution.SourceKind);
    }

    [Theory]
    [InlineData("member")]
    [InlineData("booster")]
    [InlineData("observer")]
    public void GameMasterRejectsNonOperatorGroupRoles(string groupRole)
    {
        PlaySessionAuthorizationFacts facts = BuildFacts(PlaySessionRoles.GameMaster) with
        {
            Group = BuildGroup(groupRole)
        };

        PlaySessionRoleResolution resolution = PlaySessionRoleResolver.Resolve(facts);

        Assert.False(resolution.Authorized);
        Assert.Equal("role_not_authorized", resolution.Reason);
    }

    [Fact]
    public void GroupOwnerIsCanonicalGameMasterEvenWithoutDuplicatedMembership()
    {
        GroupDto group = BuildGroup(role: null) with { OwnerUserId = "user-1" };
        PlaySessionRoleResolution resolution = PlaySessionRoleResolver.Resolve(
            BuildFacts(PlaySessionRoles.GameMaster) with { Group = group });

        Assert.True(resolution.Authorized);
        Assert.Equal(PlaySessionParticipantSources.GroupOperator, resolution.SourceKind);
    }

    [Fact]
    public void PlayerCanResolveFromCrewAssignmentAcceptedRosterOrExplicitParticipant()
    {
        PlaySessionAuthorizationFacts crewFacts = BuildFacts(PlaySessionRoles.Player) with
        {
            Crews = [BuildCrew()]
        };
        PlaySessionAuthorizationFacts rosterFacts = BuildFacts(PlaySessionRoles.Player) with
        {
            OpenRuns = [BuildOpenRun()],
            OpenRunRoster = [BuildRosterEntry()]
        };
        PlaySessionAuthorizationFacts explicitFacts = BuildFacts(PlaySessionRoles.Player) with
        {
            Participants = [BuildParticipant()]
        };

        PlaySessionRoleResolution crew = PlaySessionRoleResolver.Resolve(crewFacts);
        PlaySessionRoleResolution roster = PlaySessionRoleResolver.Resolve(rosterFacts);
        PlaySessionRoleResolution explicitParticipant = PlaySessionRoleResolver.Resolve(explicitFacts);
        Assert.Equal(PlaySessionParticipantSources.CrewAssignment, crew.SourceKind);
        Assert.Equal("crew-1", crew.SourceId);
        Assert.Equal(PlaySessionParticipantSources.AcceptedOpenRunRoster, roster.SourceKind);
        Assert.Equal("roster-1", roster.SourceId);
        Assert.Equal(PlaySessionParticipantSources.ExplicitParticipant, explicitParticipant.SourceKind);
        Assert.Equal("participant-player", explicitParticipant.SourceId);
    }

    [Fact]
    public void PlayerRejectsMismatchedOrInactiveCrewAndUnacceptedRoster()
    {
        CrewProjection wrongGroup = BuildCrew() with { GroupId = "group-other" };
        CrewProjection wrongCampaign = BuildCrew() with { CampaignId = "campaign-other" };
        CrewProjection unlistedCrew = BuildCrew() with { CrewId = "crew-other" };
        CrewProjection unavailableCrew = BuildCrew() with
        {
            Members = [BuildCrew().Members[0] with { Availability = "removed" }]
        };
        CrewProjection unknownCrewStatus = BuildCrew() with
        {
            Members = [BuildCrew().Members[0] with { Availability = "active" }]
        };

        foreach (CrewProjection crew in new[] { wrongGroup, wrongCampaign, unlistedCrew, unavailableCrew, unknownCrewStatus })
        {
            PlaySessionRoleResolution denied = PlaySessionRoleResolver.Resolve(
                BuildFacts(PlaySessionRoles.Player) with { Crews = [crew] });
            Assert.False(denied.Authorized);
        }

        foreach (string seatStatus in new[] { "waitlisted", "rejected", "pending_review" })
        {
            PlaySessionRoleResolution denied = PlaySessionRoleResolver.Resolve(
                BuildFacts(PlaySessionRoles.Player) with
                {
                    OpenRuns = [BuildOpenRun()],
                    OpenRunRoster = [BuildRosterEntry() with { SeatStatus = seatStatus }]
                });
            Assert.False(denied.Authorized);
        }

        foreach (string listingStatus in new[] { "draft", "pending", "open", "unknown" })
        {
            PlaySessionRoleResolution denied = PlaySessionRoleResolver.Resolve(
                BuildFacts(PlaySessionRoles.Player) with
                {
                    OpenRuns = [BuildOpenRun() with { Status = listingStatus }],
                    OpenRunRoster = [BuildRosterEntry()]
                });
            Assert.False(denied.Authorized);
        }
    }

    [Fact]
    public void ObserverRequiresAnActiveExplicitParticipant()
    {
        PlaySessionRoleResolution missing = PlaySessionRoleResolver.Resolve(BuildFacts(PlaySessionRoles.Observer));
        PlaySessionRoleResolution active = PlaySessionRoleResolver.Resolve(
            BuildFacts(PlaySessionRoles.Observer) with
            {
                Participants = [BuildParticipant(role: PlaySessionRoles.Observer)]
            });

        Assert.False(missing.Authorized);
        Assert.True(active.Authorized);
        Assert.Equal(PlaySessionParticipantSources.ExplicitParticipant, active.SourceKind);
    }

    [Fact]
    public void ExplicitGameMasterParticipantCannotElevateANonOperator()
    {
        PlaySessionAuthorizationFacts facts = BuildFacts(PlaySessionRoles.GameMaster) with
        {
            Group = BuildGroup("member"),
            Participants = [BuildParticipant(role: PlaySessionRoles.GameMaster)]
        };

        PlaySessionRoleResolution resolution = PlaySessionRoleResolver.Resolve(facts);

        Assert.False(resolution.Authorized);
        Assert.Equal("role_not_authorized", resolution.Reason);
    }

    [Fact]
    public void RevokedExplicitParticipantOverridesCrewOrOperatorAuthorityForThatRole()
    {
        PlaySessionParticipant revokedPlayer = BuildParticipant() with
        {
            Status = PlaySessionStatuses.Revoked,
            UpdatedAtUtc = BaselineUtc.AddMinutes(4),
            RevokedAtUtc = BaselineUtc.AddMinutes(4)
        };
        PlaySessionParticipant revokedGm = BuildParticipant(role: PlaySessionRoles.GameMaster) with
        {
            Status = PlaySessionStatuses.Revoked,
            UpdatedAtUtc = BaselineUtc.AddMinutes(4),
            RevokedAtUtc = BaselineUtc.AddMinutes(4)
        };

        PlaySessionRoleResolution player = PlaySessionRoleResolver.Resolve(
            BuildFacts(PlaySessionRoles.Player) with
            {
                Crews = [BuildCrew()],
                Participants = [revokedPlayer]
            });
        PlaySessionRoleResolution gm = PlaySessionRoleResolver.Resolve(
            BuildFacts(PlaySessionRoles.GameMaster) with
            {
                Group = BuildGroup("owner"),
                Participants = [revokedGm]
            });

        Assert.Equal("participant_revoked", player.Reason);
        Assert.Equal("participant_revoked", gm.Reason);
    }

    [Theory]
    [InlineData(PlaySessionStatuses.Closed)]
    [InlineData(PlaySessionStatuses.Revoked)]
    public void ClosedOrRevokedSessionDeniesEveryRole(string status)
    {
        PlaySessionBinding session = BuildSession(status: status);

        foreach (string role in new[] { PlaySessionRoles.GameMaster, PlaySessionRoles.Player, PlaySessionRoles.Observer })
        {
            PlaySessionRoleResolution resolution = PlaySessionRoleResolver.Resolve(
                BuildFacts(role) with
                {
                    Session = session,
                    Group = BuildGroup("owner"),
                    Crews = [BuildCrew()],
                    Participants = [BuildParticipant(role: role, status: PlaySessionStatuses.Active)]
                });
            Assert.False(resolution.Authorized);
            Assert.Equal("session_inactive", resolution.Reason);
        }
    }

    [Theory]
    [InlineData("closed")]
    [InlineData("revoked")]
    [InlineData("archived")]
    [InlineData("completed")]
    [InlineData("draft")]
    [InlineData("pending")]
    [InlineData("")]
    [InlineData(null)]
    public void AnyNonLiveCampaignOrRunStatusDeniesAuthority(string? status)
    {
        PlaySessionRoleResolution campaign = PlaySessionRoleResolver.Resolve(
            BuildFacts(PlaySessionRoles.Player) with
            {
                Campaign = BuildCampaign(status: status),
                Crews = [BuildCrew()]
            });
        PlaySessionRoleResolution run = PlaySessionRoleResolver.Resolve(
            BuildFacts(PlaySessionRoles.Player) with
            {
                Run = BuildRun(status: status),
                Crews = [BuildCrew()]
            });

        Assert.Equal("campaign_inactive", campaign.Reason);
        Assert.Equal("run_inactive", run.Reason);
    }

    [Fact]
    public void GroupCampaignRunConsistencyIsRequiredBeforeRoleFactsAreConsidered()
    {
        PlaySessionAuthorizationFacts baseline = BuildFacts(PlaySessionRoles.Player) with { Crews = [BuildCrew()] };

        Assert.Equal("group_mismatch", PlaySessionRoleResolver.Resolve(baseline with
        {
            Group = BuildGroup("member") with { GroupId = "group-other" }
        }).Reason);
        Assert.Equal("campaign_mismatch", PlaySessionRoleResolver.Resolve(baseline with
        {
            Campaign = BuildCampaign(groupId: "group-other")
        }).Reason);
        Assert.Equal("run_mismatch", PlaySessionRoleResolver.Resolve(baseline with
        {
            Run = BuildRun(campaignId: "campaign-other")
        }).Reason);
        Assert.Equal("run_mismatch", PlaySessionRoleResolver.Resolve(baseline with
        {
            Campaign = BuildCampaign(runIds: [])
        }).Reason);
    }

    [Fact]
    public void ResolverIsDeterministicUnderConcurrentEvaluation()
    {
        PlaySessionAuthorizationFacts facts = BuildFacts(PlaySessionRoles.Player) with
        {
            Crews = [BuildCrew()],
            OpenRuns = [BuildOpenRun()],
            OpenRunRoster = [BuildRosterEntry()]
        };
        ConcurrentBag<PlaySessionRoleResolution> results = [];

        Parallel.For(0, 1000, _ => results.Add(PlaySessionRoleResolver.Resolve(facts)));

        Assert.Equal(1000, results.Count);
        Assert.All(results, result =>
        {
            Assert.True(result.Authorized);
            Assert.Equal(PlaySessionRoles.Player, result.Role);
            Assert.Equal(PlaySessionParticipantSources.CrewAssignment, result.SourceKind);
            Assert.Equal("authorized", result.Reason);
        });
    }

    [Fact]
    public void ValidatorRejectsDuplicateParticipantBindingsAndForwardVersions()
    {
        PlaySessionBinding session = BuildSession();
        PlaySessionParticipant participant = BuildParticipant();
        PlaySessionParticipant duplicate = participant with { ParticipantId = "participant-2" };

        JsonException duplicateError = Assert.Throws<JsonException>(() => PlaySessionAuthorizationValidator.ValidateSnapshot(
            [session],
            [participant, duplicate],
            [],
            [],
            []));
        JsonException versionError = Assert.Throws<JsonException>(() => PlaySessionAuthorizationValidator.ValidateSnapshot(
            [session],
            [participant],
            [],
            [],
            [BuildGrant() with { ParticipantAuthorizationVersion = participant.AuthorizationVersion + 1 }]));

        Assert.Contains("Duplicate play participant binding", duplicateError.Message, StringComparison.Ordinal);
        Assert.Contains("cannot exceed", versionError.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ValidatorRejectsCrossSessionExchangeAndDuplicateSecretHashes()
    {
        PlaySessionBinding session = BuildSession();
        PlaySessionBinding otherSession = BuildSession("session-2") with { AuthorizationVersion = 3 };
        PlaySessionParticipant participant = BuildParticipant();
        PlaySessionParticipant otherParticipant = BuildParticipant() with
        {
            ParticipantId = "participant-other",
            SessionId = otherSession.SessionId
        };
        PlaySessionInvite invite = BuildConsumedInvite() with
        {
            SessionId = otherSession.SessionId,
            ParticipantId = otherParticipant.ParticipantId
        };
        PlaySessionExchange exchange = BuildPendingExchange() with
        {
            SessionId = session.SessionId,
            ParticipantId = otherParticipant.ParticipantId
        };

        JsonException crossSession = Assert.Throws<JsonException>(() => PlaySessionAuthorizationValidator.ValidateSnapshot(
            [session, otherSession],
            [participant, otherParticipant],
            [invite],
            [exchange],
            []));
        JsonException duplicateHash = Assert.Throws<JsonException>(() => PlaySessionAuthorizationValidator.ValidateSnapshot(
            [session],
            [participant],
            [BuildInvite(), BuildInvite() with { InviteId = "invite-2" }],
            [],
            []));

        Assert.Contains("crosses play sessions", crossSession.Message, StringComparison.Ordinal);
        Assert.Contains("Duplicate play authorization secret hash", duplicateHash.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ValidatorRejectsExchangeThatChangesInviteRoleOrAuthorizationVersion()
    {
        PlaySessionBinding session = BuildSession();
        PlaySessionParticipant participant = BuildParticipant();
        PlaySessionInvite invite = BuildConsumedInvite();
        PlaySessionGrant grant = BuildGrant();
        PlaySessionExchange exchange = BuildConsumedExchange();

        JsonException roleError = Assert.Throws<JsonException>(() => PlaySessionAuthorizationValidator.ValidateSnapshot(
            [session],
            [participant],
            [invite],
            [exchange with { Role = PlaySessionRoles.Observer }],
            [grant]));
        JsonException versionError = Assert.Throws<JsonException>(() => PlaySessionAuthorizationValidator.ValidateSnapshot(
            [session],
            [participant],
            [invite],
            [exchange with { SessionAuthorizationVersion = 2 }],
            [grant]));

        Assert.Contains("role-bound authorization version", roleError.Message, StringComparison.Ordinal);
        Assert.Contains("role-bound authorization version", versionError.Message, StringComparison.Ordinal);
    }

    private static void AddCompleteAuthorizationGraph(CommunityStore store)
    {
        PlaySessionBinding session = BuildSession();
        PlaySessionParticipant participant = BuildParticipant();
        PlaySessionInvite invite = BuildConsumedInvite();
        PlaySessionGrant grant = BuildGrant();
        PlaySessionExchange exchange = BuildConsumedExchange();
        store.PlaySessionsById.Add(session.SessionId, session);
        store.PlayParticipantsById.Add(participant.ParticipantId, participant);
        store.PlayInvitesById.Add(invite.InviteId, invite);
        store.PlayGrantsById.Add(grant.GrantId, grant);
        store.PlayExchangesById.Add(exchange.ExchangeId, exchange);
    }

    private static PlaySessionBinding BuildSession(
        string sessionId = "session-1",
        string status = PlaySessionStatuses.Active)
    {
        DateTimeOffset updatedAtUtc = string.Equals(status, PlaySessionStatuses.Active, StringComparison.Ordinal)
            ? BaselineUtc.AddMinutes(5)
            : BaselineUtc.AddMinutes(6);
        return new PlaySessionBinding(
            SessionId: sessionId,
            CampaignId: "campaign-1",
            RunId: "run-1",
            GroupId: "group-1",
            Status: status,
            AuthorizationVersion: 3,
            CreatedByUserId: "owner-user",
            CreatedAtUtc: BaselineUtc,
            UpdatedAtUtc: updatedAtUtc,
            ClosedAtUtc: string.Equals(status, PlaySessionStatuses.Closed, StringComparison.Ordinal) ? updatedAtUtc : null,
            RevokedAtUtc: string.Equals(status, PlaySessionStatuses.Revoked, StringComparison.Ordinal) ? updatedAtUtc : null);
    }

    private static PlaySessionParticipant BuildParticipant(
        string role = PlaySessionRoles.Player,
        string status = PlaySessionStatuses.Active)
        => new(
            ParticipantId: $"participant-{role}",
            SessionId: "session-1",
            UserId: "user-1",
            Role: role,
            SourceKind: PlaySessionParticipantSources.ExplicitParticipant,
            SourceId: "explicit-1",
            Status: status,
            AuthorizationVersion: 2,
            AddedByUserId: "owner-user",
            CreatedAtUtc: BaselineUtc.AddMinutes(1),
            UpdatedAtUtc: BaselineUtc.AddMinutes(2),
            RevokedAtUtc: status == PlaySessionStatuses.Revoked ? BaselineUtc.AddMinutes(2) : null);

    private static PlaySessionInvite BuildInvite()
        => new(
            InviteId: "invite-1",
            SessionId: "session-1",
            RequestedRole: PlaySessionRoles.Player,
            TargetUserId: "user-1",
            SecretHashSha256: new string('a', 64),
            Status: PlaySessionStatuses.Active,
            SessionAuthorizationVersion: 3,
            CreatedByUserId: "owner-user",
            CreatedAtUtc: BaselineUtc.AddMinutes(2),
            UpdatedAtUtc: BaselineUtc.AddMinutes(2),
            ExpiresAtUtc: BaselineUtc.AddMinutes(10));

    private static PlaySessionInvite BuildConsumedInvite()
        => BuildInvite() with
        {
            Status = PlaySessionStatuses.Consumed,
            ParticipantId = "participant-player",
            ParticipantAuthorizationVersion = 2,
            ConsumedByUserId = "user-1",
            ConsumedAtUtc = BaselineUtc.AddMinutes(3),
            UpdatedAtUtc = BaselineUtc.AddMinutes(3)
        };

    private static PlaySessionGrant BuildGrant()
        => new(
            GrantId: "grant-1",
            SessionId: "session-1",
            ParticipantId: "participant-player",
            UserId: "user-1",
            Role: PlaySessionRoles.Player,
            SecretHashSha256: new string('b', 64),
            Status: PlaySessionStatuses.Active,
            SessionAuthorizationVersion: 3,
            ParticipantAuthorizationVersion: 2,
            IssuedAtUtc: BaselineUtc.AddMinutes(4),
            UpdatedAtUtc: BaselineUtc.AddMinutes(4),
            ExpiresAtUtc: BaselineUtc.AddMinutes(8),
            RefreshUntilUtc: BaselineUtc.AddMinutes(12),
            DeviceThumbprint: new string('d', 64));

    private static PlaySessionExchange BuildPendingExchange()
        => new(
            ExchangeId: "exchange-1",
            InviteId: "invite-1",
            GrantId: null,
            SecretHashSha256: new string('c', 64),
            Status: PlaySessionStatuses.Pending,
            SessionAuthorizationVersion: 3,
            CreatedAtUtc: BaselineUtc.AddMinutes(3),
            UpdatedAtUtc: BaselineUtc.AddMinutes(3),
            ExpiresAtUtc: BaselineUtc.AddMinutes(5),
            SessionId: "session-1",
            ParticipantId: "participant-player",
            UserId: "user-1",
            Role: PlaySessionRoles.Player,
            DeviceThumbprint: new string('d', 64),
            ParticipantAuthorizationVersion: 2);

    private static PlaySessionExchange BuildConsumedExchange()
        => BuildPendingExchange() with
        {
            GrantId = "grant-1",
            Status = PlaySessionStatuses.Consumed,
            ConsumedAtUtc = BaselineUtc.AddMinutes(4),
            UpdatedAtUtc = BaselineUtc.AddMinutes(4)
        };

    private static PlaySessionAuthorizationFacts BuildFacts(string requestedRole)
        => new(
            Session: BuildSession(),
            UserId: "user-1",
            RequestedRole: requestedRole,
            Group: BuildGroup(role: null),
            Campaign: BuildCampaign(),
            Run: BuildRun(),
            Crews: [],
            OpenRuns: [],
            OpenRunRoster: [],
            Participants: []);

    private static GroupDto BuildGroup(string? role)
        => new(
            GroupId: "group-1",
            GroupType: "campaign",
            Name: "Test Group",
            Visibility: "private",
            OwnerUserId: "owner-user",
            Capabilities: [],
            Memberships: role is null
                ? []
                :
                [
                    new GroupMembershipDto(
                        MembershipId: "membership-1",
                        GroupId: "group-1",
                        UserId: "user-1",
                        Role: role,
                        JoinedAtUtc: BaselineUtc)
                ],
            CreatedAtUtc: BaselineUtc,
            UpdatedAtUtc: BaselineUtc);

    private static CampaignProjection BuildCampaign(
        string? status = "active",
        string groupId = "group-1",
        IReadOnlyList<string>? runIds = null)
        => new(
            CampaignId: "campaign-1",
            GroupId: groupId,
            Name: "Test Campaign",
            Status: status!,
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
            RunIds: runIds ?? ["run-1"],
            LatestContinuity: null,
            CreatedAtUtc: BaselineUtc,
            UpdatedAtUtc: BaselineUtc);

    private static RunProjection BuildRun(
        string? status = "active",
        string campaignId = "campaign-1")
        => new(
            RunId: "run-1",
            CampaignId: campaignId,
            Title: "Test Run",
            Status: status!,
            Summary: "Test run",
            ActiveSceneId: null,
            Objectives: [],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: BaselineUtc,
            UpdatedAtUtc: BaselineUtc);

    private static CrewProjection BuildCrew()
        => new(
            CrewId: "crew-1",
            Name: "Test Crew",
            Visibility: "private",
            GroupId: "group-1",
            CampaignId: "campaign-1",
            Members:
            [
                new CrewAssignmentProjection(
                    UserId: "user-1",
                    DossierId: "dossier-1",
                    Role: "runner",
                    Availability: "available",
                    AddedAtUtc: BaselineUtc)
            ],
            CreatedAtUtc: BaselineUtc,
            UpdatedAtUtc: BaselineUtc);

    private static OpenRunListingProjection BuildOpenRun()
        => new(
            OpenRunId: "open-run-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-1",
            RunId: "run-1",
            RunTitle: "Test Run",
            ListingTitle: "Open Test Run",
            Visibility: "community",
            Status: "listed",
            Summary: "Test listing",
            TableContractSummary: "Test contract",
            JoinPolicy: new OpenRunJoinPolicyProjection(
                AdmissionMode: "request_to_join",
                SeatsTotal: 4,
                ReservedSeatRoles: [],
                RequireRunnerDossier: true,
                AllowQuickstartRunner: false,
                RuleEnvironmentFingerprint: "rules-v1",
                SchedulingMode: "manual",
                ExpectedDurationMinutes: 180,
                CommunicationPlatform: "table",
                VoiceRequired: false,
                ObserverMode: "manual",
                Summary: "Test join policy"),
            SchedulingPosture: "ready",
            QuickstartAllowed: false,
            EvidenceLines: [],
            CreatedByUserId: "owner-user",
            CreatedAtUtc: BaselineUtc,
            UpdatedAtUtc: BaselineUtc);

    private static OpenRunRosterEntryProjection BuildRosterEntry()
        => new(
            EntryId: "roster-1",
            OpenRunId: "open-run-1",
            UserId: "user-1",
            DisplayName: "Test User",
            DossierId: "dossier-1",
            RunnerHandle: "Runner",
            SeatStatus: "accepted",
            SeatSummary: "Accepted",
            UpdatedAtUtc: BaselineUtc);

    private sealed class StoreFixture : IDisposable
    {
        public StoreFixture(bool createStore = true)
        {
            RootPath = Path.Combine(Path.GetTempPath(), $"chummer-play-auth-tests-{Guid.NewGuid():N}");
            Directory.CreateDirectory(RootPath);
            StoragePath = Path.Combine(RootPath, "community-store.json");
            Store = createStore ? CreateStore(StoragePath) : null!;
        }

        public string RootPath { get; }
        public string StoragePath { get; }
        public CommunityStore Store { get; }

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
    }
}
