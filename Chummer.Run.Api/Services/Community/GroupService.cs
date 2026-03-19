using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class GroupService
{
    private static readonly IReadOnlyList<string> DefaultBoosterCapabilities =
    [
        "can_manage_members",
        "can_issue_join_codes",
        "can_issue_boost_codes",
        "can_hold_shared_entitlements",
        "can_view_private_leaderboards"
    ];

    private readonly CommunityStore _store;
    private readonly AccountService _accounts;

    public GroupService(CommunityStore store, AccountService accounts)
    {
        _store = store;
        _accounts = accounts;
    }

    public GroupDto CreateGroup(CreateGroupRequest request)
    {
        var owner = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var now = DateTimeOffset.UtcNow;
        var groupId = AccountService.NewId("grp");
        var membership = new GroupMembershipDto(
            MembershipId: AccountService.NewId("mbr"),
            GroupId: groupId,
            UserId: owner.UserId,
            Role: "owner",
            JoinedAtUtc: now);
        var group = new GroupDto(
            GroupId: groupId,
            GroupType: AccountService.NormalizeOptional(request.GroupType) ?? "booster",
            Name: AccountService.NormalizeRequired(request.Name, nameof(request.Name)),
            Visibility: AccountService.NormalizeOptional(request.Visibility) ?? "private",
            OwnerUserId: owner.UserId,
            Capabilities: (request.Capabilities ?? DefaultBoosterCapabilities)
                .Where(static value => !string.IsNullOrWhiteSpace(value))
                .Select(static value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            Memberships: new[] { membership },
            CreatedAtUtc: now,
            UpdatedAtUtc: now);
        lock (_store.Gate)
        {
            _store.GroupsById[group.GroupId] = group;
        }
        UpdateUserGroups(owner.UserId);
        return group;
    }

    public GroupDto EnsurePersonalBoosterGroup(HubUserDto user)
    {
        lock (_store.Gate)
        {
            var existing = _store.GroupsById.Values.FirstOrDefault(group =>
                string.Equals(group.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(group.GroupType, "booster", StringComparison.OrdinalIgnoreCase)
                && group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)));
            if (existing is not null)
            {
                return existing;
            }
        }

        return CreateGroup(new CreateGroupRequest(
            SubjectId: user.SubjectId,
            Name: $"{user.DisplayName} boosters",
            GroupType: "booster",
            Visibility: "group",
            Capabilities: DefaultBoosterCapabilities));
    }

    public GroupDto? GetGroup(string groupId)
    {
        var normalized = AccountService.NormalizeOptional(groupId);
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.GroupsById.TryGetValue(normalized, out var group) ? group : null;
        }
    }

    public IReadOnlyList<GroupDto> ListGroupsForUser(string subjectId)
    {
        var user = _accounts.EnsureUser(subjectId, subjectId);
        lock (_store.Gate)
        {
            return _store.GroupsById.Values
                .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
                .OrderBy(group => group.Name, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    public JoinCodeDto CreateJoinCode(string groupId, CreateJoinCodeRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var group = RequireGroup(groupId);
        if (!IsGroupMember(group, requester.UserId))
        {
            throw new InvalidOperationException("requester must be a group member to issue join codes.");
        }

        var now = DateTimeOffset.UtcNow;
        var joinCode = new JoinCodeDto(
            JoinCodeId: AccountService.NewId("jcd"),
            Code: $"JOIN-{Guid.NewGuid():N}"[..13].ToUpperInvariant(),
            GroupId: group.GroupId,
            Role: AccountService.NormalizeOptional(request.Role) ?? "member",
            CreatedAtUtc: now,
            ExpiresAtUtc: request.Ttl is { } ttl && ttl > TimeSpan.Zero ? now.Add(ttl) : null,
            Uses: 0);
        lock (_store.Gate)
        {
            _store.JoinCodesByValue[joinCode.Code] = joinCode;
            _store.PersistLocked();
        }
        return joinCode;
    }

    public GroupDto JoinGroup(JoinGroupByCodeRequest request)
    {
        var user = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var code = AccountService.NormalizeRequired(request.Code, nameof(request.Code)).ToUpperInvariant();
        lock (_store.Gate)
        {
            if (!_store.JoinCodesByValue.TryGetValue(code, out var joinCode))
            {
                throw new KeyNotFoundException($"Unknown join code: {code}");
            }

            if (joinCode.ExpiresAtUtc is { } expiresAt && expiresAt < DateTimeOffset.UtcNow)
            {
                throw new InvalidOperationException("join code has expired.");
            }

            if (!_store.GroupsById.TryGetValue(joinCode.GroupId, out var group))
            {
                throw new KeyNotFoundException($"Unknown group: {joinCode.GroupId}");
            }

            if (group.Memberships.All(member => !string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
            {
                var memberships = group.Memberships
                    .Concat(
                    [
                        new GroupMembershipDto(
                            MembershipId: AccountService.NewId("mbr"),
                            GroupId: group.GroupId,
                            UserId: user.UserId,
                            Role: joinCode.Role,
                            JoinedAtUtc: DateTimeOffset.UtcNow)
                    ])
                    .ToArray();
                group = group with
                {
                    Memberships = memberships,
                    UpdatedAtUtc = DateTimeOffset.UtcNow,
                };
                _store.GroupsById[group.GroupId] = group;
            }

            _store.JoinCodesByValue[code] = joinCode with { Uses = joinCode.Uses + 1 };
            UpdateUserGroupsLocked(user.UserId);
            return group;
        }
    }

    public BoostCodeDto CreateBoostCode(CreateBoostCodeRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var group = RequireGroup(request.GroupId);
        if (!IsGroupMember(group, requester.UserId))
        {
            throw new InvalidOperationException("requester must be a group member to issue boost codes.");
        }

        lock (_store.Gate)
        {
            var campaignId = AccountService.NormalizeOptional(request.CampaignId)
                ?? EnsureCampaignLocked(group.GroupId, AccountService.NormalizeOptional(request.ProjectId) ?? "fleet", $"{group.Name} sponsorship").CampaignId;
            var boostCode = new BoostCodeDto(
                BoostCodeId: AccountService.NewId("bcd"),
                Code: $"BOOST-{Guid.NewGuid():N}"[..14].ToUpperInvariant(),
                GroupId: group.GroupId,
                CampaignId: campaignId,
                CreatedByUserId: requester.UserId,
                Status: "active",
                CreatedAtUtc: DateTimeOffset.UtcNow,
                RedeemedAtUtc: null,
                RedeemedByUserId: null);
            _store.BoostCodesByValue[boostCode.Code] = boostCode;
            _store.PersistLocked();
            return boostCode;
        }
    }

    public BoostCodeDto RedeemBoostCode(RedeemBoostCodeRequest request)
    {
        _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var code = AccountService.NormalizeRequired(request.Code, nameof(request.Code)).ToUpperInvariant();
        lock (_store.Gate)
        {
            if (!_store.BoostCodesByValue.TryGetValue(code, out var boostCode))
            {
                throw new KeyNotFoundException($"Unknown boost code: {code}");
            }

            if (!string.Equals(boostCode.Status, "active", StringComparison.OrdinalIgnoreCase))
            {
                return boostCode;
            }

            var user = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
            var redeemed = boostCode with
            {
                Status = "redeemed",
                RedeemedAtUtc = DateTimeOffset.UtcNow,
                RedeemedByUserId = user.UserId,
            };
            _store.BoostCodesByValue[code] = redeemed;
            if (_store.GroupsById.TryGetValue(redeemed.GroupId, out var group)
                && group.Memberships.All(member => !string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
            {
                var updated = group with
                {
                    Memberships = group.Memberships
                        .Concat(
                        [
                            new GroupMembershipDto(
                                MembershipId: AccountService.NewId("mbr"),
                                GroupId: group.GroupId,
                                UserId: user.UserId,
                                Role: "booster",
                                JoinedAtUtc: DateTimeOffset.UtcNow)
                        ])
                        .ToArray(),
                    UpdatedAtUtc = DateTimeOffset.UtcNow,
                };
                _store.GroupsById[group.GroupId] = updated;
                UpdateUserGroupsLocked(user.UserId);
            }

            return redeemed;
        }
    }

    public BoostCodeDto? GetBoostCode(string code)
    {
        var normalized = AccountService.NormalizeOptional(code)?.ToUpperInvariant();
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.BoostCodesByValue.TryGetValue(normalized, out var boostCode) ? boostCode : null;
        }
    }

    public BoostCampaignDto GetOrCreateCampaign(string groupId, string projectId, string title)
    {
        var group = RequireGroup(groupId);
        lock (_store.Gate)
        {
            return EnsureCampaignLocked(group.GroupId, projectId, title);
        }
    }

    private GroupDto RequireGroup(string groupId)
        => GetGroup(groupId) ?? throw new KeyNotFoundException($"Unknown group: {groupId}");

    private static bool IsGroupMember(GroupDto group, string userId)
        => group.Memberships.Any(member => string.Equals(member.UserId, userId, StringComparison.OrdinalIgnoreCase));

    private BoostCampaignDto EnsureCampaignLocked(string groupId, string projectId, string title)
    {
        var existing = _store.CampaignsById.Values.FirstOrDefault(campaign =>
            string.Equals(campaign.GroupId, groupId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(campaign.ProjectId, projectId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(campaign.Status, "active", StringComparison.OrdinalIgnoreCase));
        if (existing is not null)
        {
            return existing;
        }

        var created = new BoostCampaignDto(
            CampaignId: AccountService.NewId("cmp"),
            GroupId: groupId,
            ProjectId: projectId,
            Title: title,
            Status: "active",
            CreatedAtUtc: DateTimeOffset.UtcNow);
        _store.CampaignsById[created.CampaignId] = created;
        _store.PersistLocked();
        return created;
    }

    private void UpdateUserGroups(string userId)
    {
        lock (_store.Gate)
        {
            UpdateUserGroupsLocked(userId);
        }
    }

    private void UpdateUserGroupsLocked(string userId)
    {
        var groupIds = _store.GroupsById.Values
            .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, userId, StringComparison.OrdinalIgnoreCase)))
            .Select(group => group.GroupId)
            .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        _accounts.UpdateGroupMemberships(userId, groupIds);
    }
}
