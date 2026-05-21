using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Leaderboards;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Community;

public sealed class ReusableAccountFlowService
{
    private readonly PublicReleaseManifestService _releases;

    public ReusableAccountFlowService(PublicReleaseManifestService releases)
    {
        _releases = releases;
    }

    public ReusableAccountFlowBundle Build(ReusableAccountFlowContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(context.User);

        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        DateTimeOffset now = DateTimeOffset.UtcNow;
        IReadOnlyList<GroupDto> groups = context.Groups ?? [];
        GroupDto? primaryGroup = SelectPrimaryGroup(context.User, groups);
        GroupMembershipDto? primaryMembership = ResolveMembership(context.User, primaryGroup);
        IReadOnlyList<JoinCodeDto> joinCodes = OrderJoinCodes(context.JoinCodes, primaryGroup);
        IReadOnlyList<BoostCodeDto> boostCodes = OrderBoostCodes(context.BoostCodes, primaryGroup);
        IReadOnlyList<RewardJournalEntryDto> rewards = OrderRewards(context.Rewards);
        IReadOnlyList<BadgeDto> badges = OrderBadges(context.Badges);
        IReadOnlyList<EntitlementDto> entitlements = OrderEntitlements(context.Entitlements);

        return new ReusableAccountFlowBundle(
            BuiltAtUtc: now,
            Projections:
            [
                BuildAccountProfile(manifest, context.User, groups, now, context.Locale),
                BuildGroupProfile(manifest, context.User, primaryGroup, now, context.Locale),
                BuildMembershipStatus(manifest, context.User, groups, primaryGroup, primaryMembership, now, context.Locale),
                BuildJoinCodeFlow(manifest, primaryGroup, joinCodes, now, context.Locale),
                BuildBoostCodeFlow(manifest, primaryGroup, boostCodes, now, context.Locale),
                BuildRewardJournal(manifest, context.User, rewards, badges, now, context.Locale),
                BuildEntitlementJournal(manifest, context.User, entitlements, badges, rewards, now, context.Locale)
            ]);
    }

    private static ReusableAccountFlowProjection BuildAccountProfile(
        PublicReleaseManifestDto manifest,
        HubUserDto user,
        IReadOnlyList<GroupDto> groups,
        DateTimeOffset now,
        string locale)
    {
        string summary = $"{user.DisplayName} keeps reusable account-profile truth on the signed-in account rail with {groups.Count.ToString(CultureInfo.InvariantCulture)} governed group lane(s).";
        return new ReusableAccountFlowProjection(
            ProjectionId: StableId("account-profile", user.UserId),
            SurfaceId: "account_profile",
            Route: "/account",
            ComparisonRoute: $"/api/v1/accounts/me?subjectId={Uri.EscapeDataString(user.SubjectId)}",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                $"Handle @{user.Handle} stays on the {user.Visibility} visibility rail with timezone {user.Timezone}.",
                $"{user.LinkedPrincipals.Count.ToString(CultureInfo.InvariantCulture)} linked principal(s) remain attached to account {user.UserId}.",
                string.IsNullOrWhiteSpace(user.CountryCode)
                    ? "No country code has been attached to the profile yet."
                    : $"Country code {user.CountryCode} stays attached to the reusable profile flow."
            ],
            Actions:
            [
                new ReusableAccountFlowActionProjection("open_account", "Open account", "/account", "Review the signed-in account profile and linked rails."),
                new ReusableAccountFlowActionProjection("open_groups", "Open groups", "/groups", "Pivot from the account surface into governed groups."),
                new ReusableAccountFlowActionProjection("open_rewards", "Open rewards", "/rewards", "Review the reward and entitlement followthrough anchored to this account.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: user.UserId);
    }

    private static ReusableAccountFlowProjection BuildGroupProfile(
        PublicReleaseManifestDto manifest,
        HubUserDto user,
        GroupDto? primaryGroup,
        DateTimeOffset now,
        string locale)
    {
        string route = primaryGroup is null
            ? "/groups"
            : $"/groups/{Uri.EscapeDataString(primaryGroup.GroupId)}";
        string summary = primaryGroup is null
            ? "Group-profile flow stays reusable, but no governed group has been attached to the account yet."
            : $"{primaryGroup.Name} keeps the governed group rail reusable with {primaryGroup.Memberships.Count.ToString(CultureInfo.InvariantCulture)} member(s) and {primaryGroup.Capabilities.Count.ToString(CultureInfo.InvariantCulture)} declared capability lane(s).";

        return new ReusableAccountFlowProjection(
            ProjectionId: StableId("group-profile", primaryGroup?.GroupId ?? user.UserId),
            SurfaceId: "group_profile",
            Route: route,
            ComparisonRoute: "/groups",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                primaryGroup is null
                    ? "No reusable group shell exists yet, so /groups remains the safe entry lane."
                    : $"Group {primaryGroup.GroupId} stays on the {primaryGroup.Visibility} visibility rail as a {primaryGroup.GroupType} group.",
                primaryGroup is null
                    ? "Group capability truth cannot surface until a governed group exists."
                    : $"{primaryGroup.Capabilities.Count.ToString(CultureInfo.InvariantCulture)} capability marker(s) stay attached to the group flow.",
                primaryGroup is null
                    ? "No member list is attached yet."
                    : string.Equals(primaryGroup.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                        ? "This signed-in account currently owns the group."
                        : $"This signed-in account currently participates in owner group {primaryGroup.OwnerUserId}."
            ],
            Actions:
            [
                new ReusableAccountFlowActionProjection("open_group", "Open group", route, "Inspect the governed group page for member and code posture."),
                new ReusableAccountFlowActionProjection("open_group_list", "Open groups", "/groups", "Review every governed group rail attached to the account."),
                new ReusableAccountFlowActionProjection("open_account", "Return to account", "/account", "Return to the signed-in account spine.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: primaryGroup?.GroupId);
    }

    private static ReusableAccountFlowProjection BuildMembershipStatus(
        PublicReleaseManifestDto manifest,
        HubUserDto user,
        IReadOnlyList<GroupDto> groups,
        GroupDto? primaryGroup,
        GroupMembershipDto? primaryMembership,
        DateTimeOffset now,
        string locale)
    {
        string route = primaryGroup is null
            ? $"/api/v1/groups?subjectId={Uri.EscapeDataString(user.SubjectId)}"
            : $"/groups/{Uri.EscapeDataString(primaryGroup.GroupId)}";
        string summary = primaryMembership is null
            ? "Membership flow stays empty until the account is attached to a governed group rail."
            : $"{user.DisplayName} currently holds the {HumanizeToken(primaryMembership.Role).ToLowerInvariant()} membership rail in {primaryGroup!.Name}, with {groups.Count.ToString(CultureInfo.InvariantCulture)} governed group assignment(s) overall.";

        return new ReusableAccountFlowProjection(
            ProjectionId: StableId("membership-status", primaryMembership?.MembershipId ?? user.UserId),
            SurfaceId: "membership_status",
            Route: route,
            ComparisonRoute: "/account",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                primaryMembership is null
                    ? "No group membership exists yet for this account."
                    : $"Membership {primaryMembership.MembershipId} joined {DescribeAge(now - primaryMembership.JoinedAtUtc)} ago.",
                $"{groups.Count.ToString(CultureInfo.InvariantCulture)} governed group membership rail(s) remain visible for this account.",
                primaryGroup is null
                    ? "No primary group route has been selected yet."
                    : $"The reusable membership rail resolves through group {primaryGroup.GroupId}."
            ],
            Actions:
            [
                new ReusableAccountFlowActionProjection("open_membership_group", "Open membership rail", route, "Inspect the governed group membership details."),
                new ReusableAccountFlowActionProjection("open_groups_api", "Open groups api", $"/api/v1/groups?subjectId={Uri.EscapeDataString(user.SubjectId)}", "Load the reusable group membership payload."),
                new ReusableAccountFlowActionProjection("open_account", "Open account", "/account", "Return to the signed-in account rail.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: primaryMembership?.MembershipId ?? primaryGroup?.GroupId);
    }

    private static ReusableAccountFlowProjection BuildJoinCodeFlow(
        PublicReleaseManifestDto manifest,
        GroupDto? primaryGroup,
        IReadOnlyList<JoinCodeDto> joinCodes,
        DateTimeOffset now,
        string locale)
    {
        JoinCodeDto? latestJoinCode = joinCodes.FirstOrDefault();
        string route = primaryGroup is null
            ? "/api/v1/groups"
            : $"/api/v1/groups/{Uri.EscapeDataString(primaryGroup.GroupId)}/join-codes";
        string summary = latestJoinCode is null
            ? "Join-code flow stays group-scoped and reusable, but no governed join code has been issued yet."
            : $"Join code {latestJoinCode.Code} keeps reusable member entry on the {HumanizeToken(latestJoinCode.Role).ToLowerInvariant()} rail for group {latestJoinCode.GroupId}.";

        return new ReusableAccountFlowProjection(
            ProjectionId: StableId("join-code", latestJoinCode?.JoinCodeId ?? primaryGroup?.GroupId ?? "groups"),
            SurfaceId: "join_code",
            Route: route,
            ComparisonRoute: primaryGroup is null ? "/groups" : $"/groups/{Uri.EscapeDataString(primaryGroup.GroupId)}",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                latestJoinCode is null
                    ? "No join code has been issued yet for a new member."
                    : $"Join code {latestJoinCode.JoinCodeId} has been used {latestJoinCode.Uses.ToString(CultureInfo.InvariantCulture)} time(s).",
                latestJoinCode?.ExpiresAtUtc is null
                    ? "The current join code does not expire automatically."
                    : $"The current join-code rail expires {DescribeAge(latestJoinCode.ExpiresAtUtc.Value - now)} from now.",
                primaryGroup is null
                    ? "A governed group must exist before join codes can be issued."
                    : $"Join-code issuance stays pinned to group {primaryGroup.GroupId}."
            ],
            Actions:
            [
                new ReusableAccountFlowActionProjection("open_join_code_issue", "Open join codes", route, "Issue or inspect group join codes."),
                new ReusableAccountFlowActionProjection("open_groups", "Open groups", "/groups", "Return to the governed group rail that owns the join code."),
                new ReusableAccountFlowActionProjection("open_account", "Open account", "/account", "Return to the signed-in account rail.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestJoinCode?.JoinCodeId ?? primaryGroup?.GroupId);
    }

    private static ReusableAccountFlowProjection BuildBoostCodeFlow(
        PublicReleaseManifestDto manifest,
        GroupDto? primaryGroup,
        IReadOnlyList<BoostCodeDto> boostCodes,
        DateTimeOffset now,
        string locale)
    {
        BoostCodeDto? latestBoostCode = boostCodes.FirstOrDefault();
        string summary = latestBoostCode is null
            ? "Boost-code flow stays reusable but dormant until a governed sponsorship code is issued."
            : $"Boost code {latestBoostCode.Code} keeps sponsorship flow reusable on campaign {latestBoostCode.CampaignId} with {HumanizeToken(latestBoostCode.Status).ToLowerInvariant()} state.";

        return new ReusableAccountFlowProjection(
            ProjectionId: StableId("boost-code", latestBoostCode?.BoostCodeId ?? primaryGroup?.GroupId ?? "boost"),
            SurfaceId: "boost_code",
            Route: "/api/v1/boost-codes",
            ComparisonRoute: primaryGroup is null ? "/groups" : $"/groups/{Uri.EscapeDataString(primaryGroup.GroupId)}",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                latestBoostCode is null
                    ? "No reusable sponsorship code is active yet."
                    : $"Boost code {latestBoostCode.BoostCodeId} was created for group {latestBoostCode.GroupId}.",
                latestBoostCode?.RedeemedAtUtc is null
                    ? "The current boost-code rail has not been redeemed yet."
                    : $"The current boost-code rail was redeemed {DescribeAge(now - latestBoostCode.RedeemedAtUtc.Value)} ago.",
                latestBoostCode?.RedeemedByUserId is null
                    ? "No redeemer has been attached to the current sponsorship flow yet."
                    : $"Redeemer {latestBoostCode.RedeemedByUserId} stays attached to the reusable sponsorship flow."
            ],
            Actions:
            [
                new ReusableAccountFlowActionProjection("open_boost_codes", "Open boost codes", "/api/v1/boost-codes", "Inspect or issue reusable sponsorship codes."),
                new ReusableAccountFlowActionProjection("redeem_boost_code", "Redeem boost code", "/api/v1/boost-codes/redeem", "Redeem a governed sponsorship code."),
                new ReusableAccountFlowActionProjection("open_groups", "Open groups", "/groups", "Return to the sponsoring group rail.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestBoostCode?.BoostCodeId ?? primaryGroup?.GroupId);
    }

    private static ReusableAccountFlowProjection BuildRewardJournal(
        PublicReleaseManifestDto manifest,
        HubUserDto user,
        IReadOnlyList<RewardJournalEntryDto> rewards,
        IReadOnlyList<BadgeDto> badges,
        DateTimeOffset now,
        string locale)
    {
        RewardJournalEntryDto? latestReward = rewards.FirstOrDefault();
        int totalPoints = rewards.Sum(static item => item.Points);
        string summary = rewards.Count == 0
            ? "Reward-journal flow stays reusable, but no governed contribution receipts have minted points for this account yet."
            : $"{user.DisplayName} keeps {totalPoints.ToString(CultureInfo.InvariantCulture)} reward point(s) across {rewards.Count.ToString(CultureInfo.InvariantCulture)} governed journal entrie(s).";

        return new ReusableAccountFlowProjection(
            ProjectionId: StableId("reward-journal", latestReward?.RewardEntryId ?? user.UserId),
            SurfaceId: "reward_journal",
            Route: "/rewards",
            ComparisonRoute: $"/api/v1/entitlements/me?subjectId={Uri.EscapeDataString(user.SubjectId)}",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                latestReward is null
                    ? "No reward journal entry exists yet."
                    : $"Latest reward journal entry {latestReward.RewardEntryId} minted {latestReward.Points.ToString(CultureInfo.InvariantCulture)} point(s) from receipt {latestReward.SourceReceiptId}.",
                badges.Count == 0
                    ? "No badge posture is attached to the reward journal yet."
                    : $"{badges.Count.ToString(CultureInfo.InvariantCulture)} badge(s) remain attached to the reward journal followthrough.",
                latestReward?.Description ?? "The reward journal stays empty until a governed receipt lands."
            ],
            Actions:
            [
                new ReusableAccountFlowActionProjection("open_rewards", "Open rewards", "/rewards", "Review the reusable reward journal rail."),
                new ReusableAccountFlowActionProjection("open_account", "Open account", "/account", "Return to the signed-in account profile."),
                new ReusableAccountFlowActionProjection("open_entitlements", "Open entitlements", $"/api/v1/entitlements/me?subjectId={Uri.EscapeDataString(user.SubjectId)}", "Compare reward followthrough with granted entitlements.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestReward?.RewardEntryId ?? user.UserId);
    }

    private static ReusableAccountFlowProjection BuildEntitlementJournal(
        PublicReleaseManifestDto manifest,
        HubUserDto user,
        IReadOnlyList<EntitlementDto> entitlements,
        IReadOnlyList<BadgeDto> badges,
        IReadOnlyList<RewardJournalEntryDto> rewards,
        DateTimeOffset now,
        string locale)
    {
        EntitlementDto? latestEntitlement = entitlements
            .OrderByDescending(static item => item.GrantedAtUtc)
            .FirstOrDefault();
        string route = $"/api/v1/entitlements/me?subjectId={Uri.EscapeDataString(user.SubjectId)}";
        string summary = entitlements.Count == 0
            ? "Entitlement-journal flow stays reusable, but no governed entitlement has been granted to this account yet."
            : $"{entitlements.Count.ToString(CultureInfo.InvariantCulture)} entitlement(s) stay reusable on the signed-in account rail, with {badges.Count.ToString(CultureInfo.InvariantCulture)} badge posture marker(s) alongside them.";

        return new ReusableAccountFlowProjection(
            ProjectionId: StableId("entitlement-journal", latestEntitlement?.EntitlementId ?? user.UserId),
            SurfaceId: "entitlement_journal",
            Route: route,
            ComparisonRoute: "/rewards",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                latestEntitlement is null
                    ? "No entitlement grant is active yet for this account."
                    : $"Latest entitlement {latestEntitlement.Key} remains {latestEntitlement.Status} on the {latestEntitlement.Scope} rail.",
                entitlements.Count == 0
                    ? "No granted entitlement keys are available yet."
                    : $"Granted entitlement keys: {string.Join(", ", entitlements.Select(static item => item.Key).Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(static item => item, StringComparer.OrdinalIgnoreCase))}.",
                rewards.Count == 0
                    ? "No reward journal entries exist yet to explain future entitlement promotion."
                    : $"{rewards.Count.ToString(CultureInfo.InvariantCulture)} reward journal entrie(s) remain available to explain entitlement promotion."
            ],
            Actions:
            [
                new ReusableAccountFlowActionProjection("open_entitlements", "Open entitlements", route, "Review the reusable entitlement journal payload."),
                new ReusableAccountFlowActionProjection("open_rewards", "Open rewards", "/rewards", "Review the reward rail that can promote new entitlements."),
                new ReusableAccountFlowActionProjection("open_account", "Open account", "/account", "Return to the signed-in account rail.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: latestEntitlement?.EntitlementId ?? user.UserId);
    }

    private static IReadOnlyList<JoinCodeDto> OrderJoinCodes(IReadOnlyList<JoinCodeDto>? joinCodes, GroupDto? primaryGroup)
        => (joinCodes ?? [])
            .Where(item => primaryGroup is null || string.Equals(item.GroupId, primaryGroup.GroupId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .ToArray();

    private static IReadOnlyList<BoostCodeDto> OrderBoostCodes(IReadOnlyList<BoostCodeDto>? boostCodes, GroupDto? primaryGroup)
        => (boostCodes ?? [])
            .Where(item => primaryGroup is null || string.Equals(item.GroupId, primaryGroup.GroupId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.RedeemedAtUtc ?? item.CreatedAtUtc)
            .ToArray();

    private static IReadOnlyList<RewardJournalEntryDto> OrderRewards(IReadOnlyList<RewardJournalEntryDto>? rewards)
        => (rewards ?? [])
            .OrderByDescending(static item => item.GrantedAtUtc)
            .ToArray();

    private static IReadOnlyList<BadgeDto> OrderBadges(IReadOnlyList<BadgeDto>? badges)
        => (badges ?? [])
            .OrderByDescending(static item => item.AwardedAtUtc)
            .ToArray();

    private static IReadOnlyList<EntitlementDto> OrderEntitlements(IReadOnlyList<EntitlementDto>? entitlements)
        => (entitlements ?? [])
            .OrderByDescending(static item => item.GrantedAtUtc)
            .ToArray();

    private static GroupDto? SelectPrimaryGroup(HubUserDto user, IReadOnlyList<GroupDto> groups)
        => groups
            .OrderByDescending(group => string.Equals(group.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
            .ThenByDescending(group => group.Memberships
                .Where(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .Select(member => GroupRolePriority(member.Role))
                .DefaultIfEmpty(-1)
                .Max())
            .ThenByDescending(static group => group.UpdatedAtUtc)
            .ThenBy(group => group.Name, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();

    private static GroupMembershipDto? ResolveMembership(HubUserDto user, GroupDto? group)
        => group?.Memberships
            .Where(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(member => GroupRolePriority(member.Role))
            .ThenBy(static member => member.JoinedAtUtc)
            .FirstOrDefault();

    private static int GroupRolePriority(string? role)
        => AccountService.NormalizeOptional(role)?.ToLowerInvariant() switch
        {
            "owner" => 6,
            "organizer" => 5,
            "admin" => 4,
            "gm" => 3,
            "manager" => 2,
            "member" => 1,
            "booster" => 0,
            _ => -1,
        };

    private static string ResolveProofStatus(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.ProofStatus) ? "unknown" : manifest.ProofStatus;

    private static string ResolveSupportabilityState(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.SupportabilityState) ? "unknown" : manifest.SupportabilityState;

    private static string HumanizeToken(string? value)
    {
        string normalized = AccountService.NormalizeOptional(value) ?? "unknown";
        normalized = normalized.Replace('_', ' ').Replace('-', ' ');
        return CultureInfo.InvariantCulture.TextInfo.ToTitleCase(normalized);
    }

    private static string DescribeAge(TimeSpan span)
    {
        if (span < TimeSpan.Zero)
        {
            span = span.Negate();
        }

        if (span.TotalDays >= 2)
        {
            return $"{Math.Floor(span.TotalDays).ToString(CultureInfo.InvariantCulture)} days";
        }

        if (span.TotalHours >= 2)
        {
            return $"{Math.Floor(span.TotalHours).ToString(CultureInfo.InvariantCulture)} hours";
        }

        if (span.TotalMinutes >= 2)
        {
            return $"{Math.Floor(span.TotalMinutes).ToString(CultureInfo.InvariantCulture)} minutes";
        }

        return $"{Math.Max(1, Math.Floor(span.TotalSeconds)).ToString(CultureInfo.InvariantCulture)} seconds";
    }

    private static string StableId(string prefix, string seed)
    {
        using SHA256 sha256 = SHA256.Create();
        byte[] hash = sha256.ComputeHash(Encoding.UTF8.GetBytes($"{prefix}:{seed}"));
        return $"{prefix}-{Convert.ToHexString(hash)[..12].ToLowerInvariant()}";
    }
}
