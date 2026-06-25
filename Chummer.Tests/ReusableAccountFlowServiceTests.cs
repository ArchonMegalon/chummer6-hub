using System.Text.Json;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Leaderboards;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ReusableAccountFlowServiceTests
{
    [Fact]
    public void ReusableAccountFlowCoversAccountGroupMembershipJoinBoostRewardAndEntitlementJournals()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "reusable-account-flow", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, "releases.json"),
                JsonSerializer.Serialize(new PublicReleaseManifestDto(
                    Version: "0.8.7",
                    Channel: "preview",
                    PublishedAt: DateTimeOffset.UtcNow,
                    Downloads:
                    [
                        new PublicReleaseArtifactDto(
                            Id: "avalonia-linux-x64-installer",
                            Platform: "linux",
                            Url: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                            Sha256: new string('f', 64),
                            SizeBytes: 2048,
                            Head: "avalonia",
                            PlatformId: "linux",
                            Arch: "x64",
                            Kind: "installer",
                            FileName: "avalonia-linux-x64-installer.exe",
                            InstallAccessClass: "claimed")
                    ],
                    Source: "registry",
                    ProofStatus: "passed",
                    SupportabilityState: "local_docker_proven",
                    FixAvailabilitySummary: "The account and group rails stay on the current preview channel."),
                new JsonSerializerOptions(JsonSerializerDefaults.Web)),
                encoding: System.Text.Encoding.UTF8);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = tempRoot
                })
                .Build();

            DateTimeOffset now = DateTimeOffset.UtcNow;
            PublicReleaseManifestService releases = new(configuration);
            ReusableAccountFlowService service = new(releases);
            HubUserDto user = new(
                UserId: "usr-demo-001",
                SubjectId: "subject-demo",
                DisplayName: "Runner Demo",
                Handle: "runner-demo",
                Visibility: "private",
                Timezone: "UTC",
                CountryCode: "AT",
                LinkedPrincipals:
                [
                    "subject-demo"
                ],
                GroupIds:
                [
                    "grp-demo-001"
                ],
                CreatedAtUtc: now.AddDays(-8),
                UpdatedAtUtc: now.AddMinutes(-5))
            {
                Email = "runner@example.invalid"
            };
            GroupDto group = new(
                GroupId: "grp-demo-001",
                GroupType: "booster",
                Name: "Tuesday Boosters",
                Visibility: "group",
                OwnerUserId: user.UserId,
                Capabilities:
                [
                    "can_manage_members",
                    "can_issue_join_codes",
                    "can_issue_boost_codes"
                ],
                Memberships:
                [
                    new GroupMembershipDto(
                        MembershipId: "mbr-demo-001",
                        GroupId: "grp-demo-001",
                        UserId: user.UserId,
                        Role: "owner",
                        JoinedAtUtc: now.AddDays(-4))
                ],
                CreatedAtUtc: now.AddDays(-4),
                UpdatedAtUtc: now.AddMinutes(-2));
            JoinCodeDto joinCode = new(
                JoinCodeId: "jcd-demo-001",
                Code: "JOIN-DEMO001",
                GroupId: group.GroupId,
                Role: "member",
                CreatedAtUtc: now.AddHours(-3),
                ExpiresAtUtc: now.AddDays(5),
                Uses: 1);
            BoostCodeDto boostCode = new(
                BoostCodeId: "bcd-demo-001",
                Code: "BOOST-DEMO001",
                GroupId: group.GroupId,
                CampaignId: "camp-demo-001",
                CreatedByUserId: user.UserId,
                Status: "redeemed",
                CreatedAtUtc: now.AddHours(-2),
                RedeemedAtUtc: now.AddMinutes(-20),
                RedeemedByUserId: user.UserId);
            RewardJournalEntryDto reward = new(
                RewardEntryId: "rwd-demo-001",
                UserId: user.UserId,
                GroupId: group.GroupId,
                RewardKind: "impact_points",
                Points: 23,
                SourceReceiptId: "receipt-demo-001",
                Description: "slice_landed on fleet minted 23 points.",
                GrantedAtUtc: now.AddMinutes(-30));
            BadgeDto badge = new(
                BadgeId: "badge-demo-001",
                UserId: user.UserId,
                Key: "jury-finisher",
                Label: "Jury Finisher",
                AwardedAtUtc: now.AddMinutes(-25));
            EntitlementDto entitlement = new(
                EntitlementId: "ent-demo-001",
                Scope: "user",
                ScopeId: user.UserId,
                Key: "contributor-marker",
                Status: "active",
                Source: "verified landed slice",
                SponsorSessionId: null,
                GrantedAtUtc: now.AddMinutes(-15));

            ReusableAccountFlowBundle bundle = service.Build(new ReusableAccountFlowContext(
                User: user,
                Groups:
                [
                    group
                ],
                JoinCodes:
                [
                    joinCode
                ],
                BoostCodes:
                [
                    boostCode
                ],
                Rewards:
                [
                    reward
                ],
                Badges:
                [
                    badge
                ],
                Entitlements:
                [
                    entitlement
                ],
                Locale: "en-US"));

            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "account_profile", StringComparison.Ordinal) && string.Equals(item.Route, "/account", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "group_profile", StringComparison.Ordinal) && string.Equals(item.Route, "/groups/grp-demo-001", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "membership_status", StringComparison.Ordinal) && string.Equals(item.Route, "/groups/grp-demo-001", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "join_code", StringComparison.Ordinal) && string.Equals(item.Route, "/api/v1/groups/grp-demo-001/join-codes", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "boost_code", StringComparison.Ordinal) && string.Equals(item.Route, "/api/v1/boost-codes", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "reward_journal", StringComparison.Ordinal) && string.Equals(item.Route, "/rewards", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "entitlement_journal", StringComparison.Ordinal) && string.Equals(item.Route, "/api/v1/entitlements/me?subjectId=subject-demo", StringComparison.Ordinal));
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }
}
