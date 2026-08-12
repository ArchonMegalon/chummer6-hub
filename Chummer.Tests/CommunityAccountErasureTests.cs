using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CommunityAccountErasureTests
{
    private static readonly DateTimeOffset Baseline = new(2026, 8, 12, 12, 0, 0, TimeSpan.Zero);

    [Fact]
    public void Erase_removes_owned_and_personal_graph_but_preserves_unrelated_members()
    {
        using Fixture fixture = new();
        HubUserDto erasedUser = User("user-delete", "subject-delete", ["group-owned", "group-shared"]);
        HubUserDto keeper = User("user-keep", "subject-keep", ["group-owned", "group-shared"]);
        fixture.Store.UsersById[erasedUser.UserId] = erasedUser;
        fixture.Store.UsersById[keeper.UserId] = keeper;
        fixture.Store.UserIdBySubjectId[erasedUser.SubjectId] = erasedUser.UserId;
        fixture.Store.UserIdBySubjectId[keeper.SubjectId] = keeper.UserId;
        fixture.Store.GroupsById["group-owned"] = Group(
            "group-owned",
            erasedUser.UserId,
            [Membership("member-owner", "group-owned", erasedUser.UserId), Membership("member-keeper", "group-owned", keeper.UserId)]);
        fixture.Store.GroupsById["group-shared"] = Group(
            "group-shared",
            keeper.UserId,
            [Membership("member-delete", "group-shared", erasedUser.UserId), Membership("member-shared-owner", "group-shared", keeper.UserId)]);
        fixture.Store.LinkedIdentities.Add(new LinkedIdentityDto(
            "link-delete", erasedUser.UserId, "google", "login", "provider-subject", "Email", "verified", "oauth", true,
            Baseline, Baseline, Baseline));
        fixture.Store.UserExperienceByUserId[erasedUser.UserId] = new HubUserExperienceDto(
            erasedUser.UserId, [], false, false, false, null, Baseline);
        fixture.Store.DossiersById["dossier-delete"] = new RunnerDossierProjection(
            "dossier-delete", "Ghost", "Ghost", "active", erasedUser.UserId, null, null, null, null,
            new RuleEnvironmentRef("sr5", "1", "core", "fingerprint", [], [], []), null, [], [], [], Baseline, Baseline);
        fixture.Store.PlaySessionsById["session-delete"] = new PlaySessionBinding(
            "session-delete", "campaign-shared", "run-shared", "group-shared", PlaySessionStatuses.Active, 1,
            erasedUser.UserId, Baseline, Baseline);
        fixture.Store.PlayParticipantsById["participant-delete"] = new PlaySessionParticipant(
            "participant-delete", "session-delete", erasedUser.UserId, PlaySessionRoles.GameMaster,
            PlaySessionParticipantSources.ExplicitParticipant, erasedUser.UserId, PlaySessionStatuses.Active, 1,
            erasedUser.UserId, Baseline, Baseline);
        fixture.Store.PersistLocked();

        CommunityAccountErasureResult result = fixture.Service.Erase(erasedUser.SubjectId);

        Assert.True(result.Erased);
        Assert.Equal(1, result.OwnedGroupsRemoved);
        Assert.Equal(1, result.SharedMembershipsRemoved);
        Assert.Equal(2, result.PlayAuthorizationRecordsRemoved);
        Assert.DoesNotContain(erasedUser.UserId, fixture.Store.UsersById.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.DoesNotContain(erasedUser.SubjectId, fixture.Store.UserIdBySubjectId.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.DoesNotContain("group-owned", fixture.Store.GroupsById.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.Single(fixture.Store.GroupsById["group-shared"].Memberships);
        Assert.Equal(keeper.UserId, fixture.Store.GroupsById["group-shared"].Memberships[0].UserId);
        Assert.DoesNotContain("group-owned", fixture.Store.UsersById[keeper.UserId].GroupIds, StringComparer.OrdinalIgnoreCase);
        Assert.Empty(fixture.Store.LinkedIdentities);
        Assert.Empty(fixture.Store.DossiersById);
        Assert.Empty(fixture.Store.PlaySessionsById);
        Assert.Empty(fixture.Store.PlayParticipantsById);

        CommunityStore reloaded = fixture.Reload();
        Assert.Single(reloaded.UsersById);
        Assert.Single(reloaded.GroupsById);
        Assert.Single(reloaded.GroupsById["group-shared"].Memberships);

        CommunityAccountErasureResult repeated = fixture.Service.Erase(erasedUser.SubjectId);
        Assert.False(repeated.Erased);
        Assert.Equal(0, repeated.RecordsRemoved);
    }

    [Fact]
    public void Erase_restores_the_validated_snapshot_when_persistence_fails()
    {
        using Fixture fixture = new();
        HubUserDto erasedUser = User("user-delete", "subject-delete", ["group-owned"]);
        fixture.Store.UsersById[erasedUser.UserId] = erasedUser;
        fixture.Store.UserIdBySubjectId[erasedUser.SubjectId] = erasedUser.UserId;
        fixture.Store.GroupsById["group-owned"] = Group(
            "group-owned",
            erasedUser.UserId,
            [Membership("member-owner", "group-owned", erasedUser.UserId)]);
        fixture.Store.AccountErasurePersistenceFaultInjector =
            () => throw new IOException("simulated durable write failure");

        Assert.Throws<IOException>(() => fixture.Service.Erase(erasedUser.SubjectId));

        Assert.Contains(erasedUser.UserId, fixture.Store.UsersById.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("group-owned", fixture.Store.GroupsById.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.Equal(erasedUser.UserId, fixture.Store.UserIdBySubjectId[erasedUser.SubjectId]);
        CommunityStore reloaded = fixture.Reload();
        Assert.Contains(erasedUser.UserId, reloaded.UsersById.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("group-owned", reloaded.GroupsById.Keys, StringComparer.OrdinalIgnoreCase);
    }

    private static HubUserDto User(string userId, string subjectId, IReadOnlyList<string> groups)
        => new(
            userId, subjectId, userId, userId, "private", "UTC", "", [subjectId], groups, Baseline, Baseline);

    private static GroupMembershipDto Membership(string membershipId, string groupId, string userId)
        => new(membershipId, groupId, userId, "member", Baseline);

    private static GroupDto Group(
        string groupId,
        string ownerUserId,
        IReadOnlyList<GroupMembershipDto> memberships)
        => new(groupId, "campaign", groupId, "private", ownerUserId, [], memberships, Baseline, Baseline);

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(
            Path.GetTempPath(),
            "chummer-community-erasure-tests",
            Guid.NewGuid().ToString("N"));

        public Fixture()
        {
            Directory.CreateDirectory(_directory);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = StoragePath
                })
                .Build();
            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Service = new CommunityAccountErasureService(Store);
        }

        public IConfiguration Configuration { get; }
        public string StoragePath => Path.Combine(_directory, "community.json");
        public CommunityStore Store { get; }
        public CommunityAccountErasureService Service { get; }

        public CommunityStore Reload()
            => new(Configuration, NullLogger<CommunityStore>.Instance);

        public void Dispose()
        {
            try
            {
                Directory.Delete(_directory, recursive: true);
            }
            catch
            {
                // Best-effort cleanup for test temp files.
            }
        }
    }
}
