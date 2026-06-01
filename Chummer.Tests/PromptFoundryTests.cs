using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PromptFoundryTests
{
    [Fact]
    public void TemplateSeedSyncProvidesRequiredMediaAndSupportTemplates()
    {
        TestPromptFoundryContext ctx = CreateContext();

        IReadOnlyList<PromptTemplateProjection> templates = ctx.Service.SyncSeedTemplates("gm-a");

        Assert.Contains(templates, item => item.Type == "gm_session_video");
        Assert.Contains(templates, item => item.Type == "magicfit_video");
        Assert.Contains(templates, item => item.Type == "black_ledger_newsreel");
        Assert.Contains(templates, item => item.Type == "rules_safe_humanizer");
        Assert.All(templates, item => Assert.Contains("sourcebook_text", item.ForbiddenDataClasses));
    }

    [Fact]
    public void RuntimeModeFallsBackUntilApiMcpPrivacyAndExportAreVerified()
    {
        TestPromptFoundryContext ctx = CreateContext();

        PromptFoundryDraftProjection draft = ctx.Service.CreateDraft("gm-a", new PromptFoundryCreateDraftRequest(
            TemplateId: "gm_session_video_aftermath_v1",
            CampaignId: "campaign-1",
            GroupId: "group-1",
            VideoType: "newsreel",
            Audience: "campaign_players",
            Tone: "corporate news",
            PublicSafeSummary: "A team triggered a security incident and escaped.",
            LocationAlias: "Kestrel",
            ProviderMode: PromptFoundryProviderModes.PromptArchitectsRuntime));

        Assert.Equal(PromptFoundryProviderModes.LocalTemplate, draft.ProviderMode);
        Assert.Equal("pass", draft.PrivacyScanStatus);
    }

    [Fact]
    public void TemplateSeedEnhancementProducesDiffAndPromptUnitsWithoutRenderUnits()
    {
        TestPromptFoundryContext ctx = CreateContext();

        PromptFoundryDraftProjection draft = ctx.Service.CreateDraft("gm-a", new PromptFoundryCreateDraftRequest(
            TemplateId: "magicfit_video_bridge_v1",
            CampaignId: "campaign-1",
            GroupId: "group-1",
            VideoType: "matrix_alert",
            Audience: "campaign_players",
            Tone: "glitchy tactical",
            PublicSafeSummary: "A public-safe alert reports heat escalation.",
            LocationAlias: "Kestrel",
            StyleTags: ["photoreal", "AR overlays", "visible cyberware"],
            GenericCharacterDescriptors: ["ork security analyst", "elf decker silhouette"],
            FaceReferencePlaceholders: ["cast-placeholder-1"],
            ProviderMode: PromptFoundryProviderModes.PromptArchitectsTemplateSeed));

        Assert.Equal("pass", draft.PrivacyScanStatus);
        Assert.NotEmpty(draft.DiffSummary);
        Assert.True(draft.PromptUnitsEstimated > 0);
        Assert.Contains("AR overlay", draft.EnhancedPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(ctx.Service.GetHome("gm-a", "campaign-1").UsageLedger, item => item.EventType == "estimate" && item.Units == draft.PromptUnitsEstimated);
    }

    [Fact]
    public void SourcebookProseAndPrivateDataBlockApproval()
    {
        TestPromptFoundryContext ctx = CreateContext();

        PromptFoundryDraftProjection draft = ctx.Service.CreateDraft("gm-a", new PromptFoundryCreateDraftRequest(
            TemplateId: "rules_safe_humanizer_v1",
            CampaignId: "campaign-1",
            GroupId: "group-1",
            VideoType: "support",
            Audience: "campaign_players",
            Tone: "plain",
            PublicSafeSummary: "Please copy the rulebook and include runner@example.com.",
            LocationAlias: "support",
            ProviderMode: PromptFoundryProviderModes.PromptArchitectsTemplateSeed));

        Assert.Equal("fail", draft.PrivacyScanStatus);
        Assert.Throws<InvalidOperationException>(() => ctx.Service.ApproveDraft("gm-a", draft.Id, new PromptFoundryApproveDraftRequest(true)));
        Assert.Throws<InvalidOperationException>(() => ctx.Service.HumanizeRulesSafeSupport("sourcebook prose with page text", ["rulefact.sr6.test"], ["explain.test"]));
    }

    [Fact]
    public void CrossGmPromptDraftsAreIsolated()
    {
        TestPromptFoundryContext ctx = CreateContext();
        PromptFoundryDraftProjection draft = ctx.Service.CreateDraft("gm-a", new PromptFoundryCreateDraftRequest(
            TemplateId: "gm_session_video_aftermath_v1",
            CampaignId: "campaign-1",
            GroupId: "group-1",
            VideoType: "newsreel",
            Audience: "campaign_players",
            Tone: "noir",
            PublicSafeSummary: "A public-safe summary.",
            LocationAlias: "Kestrel",
            ProviderMode: PromptFoundryProviderModes.PromptArchitectsTemplateSeed));

        Assert.DoesNotContain(ctx.Service.GetHome("gm-b", "campaign-1").Drafts, item => item.Id == draft.Id);
        Assert.Throws<KeyNotFoundException>(() => ctx.Service.EditDraft("gm-b", draft.Id, new PromptFoundryEditDraftRequest("stolen", draft.NegativePrompt)));
    }

    [Fact]
    public void ApprovalConsumesPromptUnitsButStillDoesNotRender()
    {
        TestPromptFoundryContext ctx = CreateContext();
        PromptFoundryDraftProjection draft = ctx.Service.CreateDraft("gm-a", new PromptFoundryCreateDraftRequest(
            TemplateId: "black_ledger_newsroom_v1",
            CampaignId: "campaign-1",
            GroupId: "group-1",
            VideoType: "newsreel",
            Audience: "campaign_players",
            Tone: "satirical newsroom",
            PublicSafeSummary: "District heat changed after a public incident.",
            LocationAlias: "district-alias",
            ProviderMode: PromptFoundryProviderModes.PromptArchitectsTemplateSeed));

        PromptFoundryDraftProjection approved = ctx.Service.ApproveDraft("gm-a", draft.Id, new PromptFoundryApproveDraftRequest(true));

        Assert.Equal("approved", approved.Status);
        Assert.Contains(ctx.Service.GetHome("gm-a", "campaign-1").UsageLedger, item => item.EventType == "consume");
    }

    private static TestPromptFoundryContext CreateContext()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-prompt-foundry-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json"),
                ["CHUMMER_PROMPT_FOUNDRY_STORE_PATH"] = Path.Combine(root, "prompt-foundry.json"),
                ["PROMPT_ARCHITECTS_TIER4_VERIFIED"] = "true",
                ["PROMPT_ARCHITECTS_EXPORT_AVAILABLE"] = "true",
                ["PROMPT_ARCHITECTS_API_AVAILABLE"] = "false",
                ["PROMPT_ARCHITECTS_MCP_VERIFIED"] = "false",
                ["PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED"] = "false"
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

        PromptFoundryStore store = new(configuration);
        return new TestPromptFoundryContext(new PromptFoundryService(store, community, configuration));
    }

    private sealed record TestPromptFoundryContext(PromptFoundryService Service);
}
