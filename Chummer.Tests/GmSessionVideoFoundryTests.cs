using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class GmSessionVideoFoundryTests
{
    [Fact]
    public void FaceVaultDoesNotListFetchOrUseAnotherGmFace()
    {
        TestFoundryContext ctx = CreateContext();
        FaceAssetProjection gmBFace = ctx.Service.CreateFace("gm-b", "campaign-1", new CreateFaceAssetRequest(
            DisplayName: "Private Anchor",
            Metatype: "ork",
            RoleTags: ["news_anchor"]));

        Assert.Empty(ctx.Service.ListFaces("gm-a", "campaign-1", "Private"));
        Assert.Throws<KeyNotFoundException>(() => ctx.Service.GetFace("gm-a", "campaign-1", gmBFace.Id));
        Assert.Throws<CommunityAccessDeniedException>(() => ctx.Service.CreatePromptDraft("gm-a", "campaign-1", null, new CreatePromptDraftRequest(
            VideoType: "newsreel",
            Audience: "campaign_players",
            SpoilerLevel: "known_table_facts",
            Tone: "corporate propaganda",
            SelectedFaceAssetIds: [gmBFace.Id],
            AllowedFacts: ["A safe campaign incident summary."],
            DurationSeconds: 20)));
    }

    [Fact]
    public void PromptOnlyRegenerationDoesNotReserveOrConsumeRenderUnits()
    {
        TestFoundryContext ctx = CreateContext();
        PromptDraftProjection draft = ctx.Service.CreatePromptDraft("gm-a", "campaign-1", "session-1", new CreatePromptDraftRequest(
            VideoType: "player_teaser",
            Audience: "campaign_players",
            SpoilerLevel: "none",
            Tone: "noir rain",
            AllowedFacts: ["A runner team approaches an unnamed research site."],
            DurationSeconds: 30));

        PromptDraftProjection regenerated = ctx.Service.RegeneratePromptOnly("gm-a", "campaign-1", draft.Id);

        Assert.Equal("gm_prompt_review", regenerated.Status);
        Assert.Empty(ctx.Service.GetHome("gm-a", "campaign-1").RenderJobs);
        Assert.Equal(0, ctx.Service.GetUsage("gm-a", "campaign-1").GmMonthlyReserved);
        Assert.Equal(0, ctx.Service.GetUsage("gm-a", "campaign-1").GmMonthlyConsumed);
    }

    [Fact]
    public void EditedPromptRerunsPrivacyScanAndBlocksApprovalUntilClean()
    {
        TestFoundryContext ctx = CreateContext();
        PromptDraftProjection draft = ctx.Service.CreatePromptDraft("gm-a", "campaign-1", null, new CreatePromptDraftRequest(
            VideoType: "newsreel",
            Audience: "public_share",
            SpoilerLevel: "none",
            Tone: "in-universe news",
            AllowedFacts: ["Authorities reported an incident at an unnamed research center."],
            DurationSeconds: 20));

        PromptDraftProjection dirty = ctx.Service.EditPromptDraft("gm-a", "campaign-1", draft.Id, new EditPromptDraftRequest(
            GeneratedPrompt: "Publish directly with player email runner@example.com and gm-only secrets.",
            NegativePrompt: draft.NegativePrompt));

        Assert.Equal("fail", dirty.PrivacyScanStatus);
        Assert.Throws<InvalidOperationException>(() => ctx.Service.ApprovePrompt("gm-a", "campaign-1", draft.Id, new ApprovePromptDraftRequest(true)));
    }

    [Fact]
    public void RenderCannotStartBeforeExplicitApprovalAndUsesSessionAccount()
    {
        TestFoundryContext ctx = CreateContext();
        PromptDraftProjection draft = ctx.Service.CreatePromptDraft("gm-a", "campaign-1", "session-1", new CreatePromptDraftRequest(
            VideoType: "security_breach_report",
            Audience: "campaign_players",
            SpoilerLevel: "known_table_facts",
            Tone: "tactical security report",
            AllowedFacts: ["Security heat crossed a threshold."],
            DurationSeconds: 12));

        Assert.Throws<KeyNotFoundException>(() => ctx.Service.StartApprovedRender("gm-a", "campaign-1", "missing-job"));

        SessionVideoRenderJobProjection job = ctx.Service.ApprovePrompt("gm-a", "campaign-1", draft.Id, new ApprovePromptDraftRequest(true));
        SessionVideoRenderJobProjection queued = ctx.Service.StartApprovedRender("gm-a", "campaign-1", job.Id);

        Assert.Equal("queued", queued.Status);
        Assert.Equal("gm_session_video", queued.Origin);
        Assert.Equal(GmSessionVideoFoundryService.ProviderAccountId, queued.ProviderAccountId);
        Assert.Equal(1, ctx.Service.GetUsage("gm-a", "campaign-1").GmMonthlyReserved);
    }

    [Fact]
    public void TablePulsePacketSanitizesCanonicalNamesBeforePrompting()
    {
        TestFoundryContext ctx = CreateContext();
        TablePulseMediaPacketProjection packet = ctx.Service.BuildTablePulseMediaPacket(
            "gm-a",
            "campaign-1",
            "session-1",
            new CreatePromptDraftRequest(
                VideoType: "matrix_alert",
                Audience: "campaign_players",
                SpoilerLevel: "known_table_facts",
                Tone: "glitchy",
                AllowedFacts: ["Renraku lab breach by runner@example.com"],
                DurationSeconds: 12),
            heatSummary: "Renraku trace started",
            factionSummary: "Ares patrol reacted",
            locationAlias: "Kestrel");

        Assert.DoesNotContain("Renraku", packet.HeatSummary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("@", string.Join(" ", packet.AllowedFacts), StringComparison.OrdinalIgnoreCase);
        Assert.Equal("pass", packet.PrivacyScanStatus);
    }

    private static TestFoundryContext CreateContext()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-foundry-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json"),
                ["CHUMMER_GM_SESSION_VIDEO_FOUNDRY_STORE_PATH"] = Path.Combine(root, "foundry.json"),
                ["CHUMMER_GM_VIDEO_QUOTA_PER_GM"] = "20",
                ["CHUMMER_GM_VIDEO_QUOTA_PER_GROUP"] = "60",
                ["CHUMMER_GM_VIDEO_QUOTA_PER_CAMPAIGN"] = "30",
                ["CHUMMER_EA_MAGICFIT_EMAIL"] = "session-account@example.invalid"
            })
            .Build();
        CommunityStore community = new(configuration, NullLogger<CommunityStore>.Instance);
        DateTimeOffset now = DateTimeOffset.UtcNow;
        lock (community.Gate)
        {
            community.UsersById["gm-a"] = new HubUserDto("gm-a", "subject-a", "GM A", "gm-a", "private", "UTC", "US", [], ["group-1"], now, now);
            community.UsersById["gm-b"] = new HubUserDto("gm-b", "subject-b", "GM B", "gm-b", "private", "UTC", "US", [], ["group-1"], now, now);
            community.GroupsById["group-1"] = new GroupDto(
                "group-1",
                "campaign",
                "Campaign Group",
                "private",
                "gm-a",
                [],
                [
                    new GroupMembershipDto("membership-a", "group-1", "gm-a", "gm", now),
                    new GroupMembershipDto("membership-b", "group-1", "gm-b", "gm", now)
                ],
                now,
                now);
            community.CampaignsById["campaign-1"] = new BoostCampaignDto("campaign-1", "group-1", "project-1", "Campaign One", "active", now);
        }

        GmSessionVideoFoundryStore store = new(configuration);
        return new TestFoundryContext(new GmSessionVideoFoundryService(store, community, configuration));
    }

    private sealed record TestFoundryContext(GmSessionVideoFoundryService Service);
}
