using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class GroupInviteFlowTests
{
    [Fact]
    public void Invite_requires_owned_runner_and_persists_consumed_ticket()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-group-invite", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string storePath = Path.Combine(tempRoot, "community-store.json");

        try
        {
            IConfiguration configuration = BuildConfiguration(storePath);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            GroupService groups = new(store, accounts);
            accounts.EnsureUser("subject.owner", "GM");
            accounts.EnsureUser("subject.player", "Player");
            accounts.EnsureUser("subject.other", "Other");

            GroupDto group = groups.CreateGroup(new CreateGroupRequest(
                "subject.owner",
                "Tuesday Shadows",
                GroupType: "campaign",
                Visibility: "private"));
            JoinCodeDto invite = groups.CreateJoinCode(group.GroupId, new CreateJoinCodeRequest("subject.owner"));
            var playerRunner = groups.CreateRunner(new CreateRunnerRequest("subject.player", "Switchback", "Switchback"));
            var otherRunner = groups.CreateRunner(new CreateRunnerRequest("subject.other", "Borrowed", "Borrowed"));

            Assert.Throws<ArgumentException>(() =>
                groups.JoinGroup(new JoinGroupByCodeRequest("subject.player", invite.Code)));
            Assert.Throws<InvalidOperationException>(() =>
                groups.JoinGroup(new JoinGroupByCodeRequest("subject.player", invite.Code, otherRunner.DossierId)));
            Assert.Single(groups.GetGroup(group.GroupId)!.Memberships);

            GroupDto joined = groups.JoinGroup(new JoinGroupByCodeRequest("subject.player", invite.Code, playerRunner.DossierId));
            GroupMembershipDto membership = Assert.Single(
                joined.Memberships,
                item => string.Equals(item.RunnerDossierId, playerRunner.DossierId, StringComparison.Ordinal));
            Assert.Equal("Switchback", membership.RunnerHandle);
            Assert.False(string.IsNullOrWhiteSpace(membership.RunnerTicketId));
            RunnerTicketDto ticket = store.RunnerTicketsById[membership.RunnerTicketId!];
            Assert.Equal("consumed", ticket.Status);
            Assert.Equal(invite.JoinCodeId, ticket.JoinCodeId);
            Assert.Equal(1, groups.GetJoinCode(invite.Code)!.Uses);

            CommunityStore reloaded = new(configuration, NullLogger<CommunityStore>.Instance);
            Assert.True(reloaded.RunnerTicketsById.ContainsKey(ticket.RunnerTicketId));
            Assert.Equal(playerRunner.DossierId, reloaded.GroupsById[group.GroupId].Memberships.Single(item => item.UserId == membership.UserId).RunnerDossierId);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public void Gm_can_edit_group_and_revoke_high_entropy_expiring_invite()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-group-manage", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            CommunityStore store = new(BuildConfiguration(Path.Combine(tempRoot, "community-store.json")), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            GroupService groups = new(store, accounts);
            GroupDto group = groups.CreateGroup(new CreateGroupRequest("subject.gm", "Old name", "campaign", "private"));

            GroupDto updated = groups.UpdateGroup(group.GroupId, new UpdateGroupRequest("subject.gm", "Neon Sundays", "unlisted"));
            Assert.Equal("Neon Sundays", updated.Name);
            Assert.Equal("unlisted", updated.Visibility);

            JoinCodeDto invite = groups.CreateJoinCode(group.GroupId, new CreateJoinCodeRequest("subject.gm"));
            Assert.True(invite.Code.Length >= 32);
            Assert.InRange(invite.ExpiresAtUtc!.Value, DateTimeOffset.UtcNow.AddDays(6), DateTimeOffset.UtcNow.AddDays(8));
            Assert.Equal(25, invite.MaxUses);
            Assert.Throws<InvalidOperationException>(() =>
                groups.CreateJoinCode(group.GroupId, new CreateJoinCodeRequest("subject.gm", MaxUses: 0)));
            Assert.Throws<InvalidOperationException>(() =>
                groups.CreateJoinCode(group.GroupId, new CreateJoinCodeRequest("subject.gm", MaxUses: 1001)));

            JoinCodeDto revoked = groups.RevokeJoinCode(group.GroupId, invite.Code, "subject.gm");
            Assert.NotNull(revoked.RevokedAtUtc);
            var runner = groups.CreateRunner(new CreateRunnerRequest("subject.player", "Static", "Static"));
            Assert.Throws<InvalidOperationException>(() =>
                groups.JoinGroup(new JoinGroupByCodeRequest("subject.player", invite.Code, runner.DossierId)));
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    private static IConfiguration BuildConfiguration(string storePath)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = storePath
            })
            .Build();
}
