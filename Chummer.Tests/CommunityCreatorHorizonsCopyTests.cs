using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Registry.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CommunityCreatorHorizonsCopyTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"chummer-community-copy-{Guid.NewGuid():N}");

    [Fact]
    public void PublicMarkdown_UsesPlainUserFacingLanguage()
    {
        CommunityCreatorHorizonsService service = BuildService();

        string markdown = string.Join(
            "\n---\n",
            service.BuildCommunityMarkdown("open_run_board"),
            service.BuildCommunityMarkdown("organizer_closeout_posture"),
            service.BuildCommunityMarkdown("moderation_boundary"),
            service.BuildCreatorMarkdown("publication_board"),
            service.BuildCreatorMarkdown("publication_trust_boundary"),
            service.BuildCreatorMarkdown("campaign_return_loop"),
            service.BuildPassportMarkdown("runner_return_posture"),
            service.BuildPassportMarkdown("cross_table_identity_boundary"),
            service.BuildPassportMarkdown("privacy_safe_participation_proof"),
            service.BuildSignalDeckMarkdown("pressure_posture"),
            service.BuildSignalDeckMarkdown("command_boundary"),
            service.BuildSignalDeckMarkdown("aftermath_return_loop"),
            service.BuildLivingWorldMarkdown("watch_package_posture"),
            service.BuildLivingWorldMarkdown("command_followthrough_boundary"),
            service.BuildLivingWorldMarkdown("newsroom_aftermath_loop"));

        Assert.Contains("## What is visible now", markdown, StringComparison.Ordinal);
        Assert.Contains("## Privacy and limits", markdown, StringComparison.Ordinal);
        Assert.Contains("Linked installs", markdown, StringComparison.Ordinal);
        Assert.Contains("Participation events", markdown, StringComparison.Ordinal);
        Assert.Contains("A simple public board for open runs, seats, and scheduling.", markdown, StringComparison.Ordinal);

        foreach (string forbidden in new[]
                 {
                     "Current public-safe posture",
                     "Current first-party posture",
                     "Current governed publication posture",
                     "JSON route:",
                     " seat posture",
                     "Scheduling truth",
                     "publication truth",
                     "Trust posture",
                     "Participation receipts",
                     "claimed-install posture",
                     "continuity rail",
                     "first-party spine",
                     "bounded",
                     "governed",
                     "operator rails"
                 })
        {
            Assert.DoesNotContain(forbidden, markdown, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void HorizonCardView_DoesNotExposeRawDataAsDefaultUserPath()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "MediaArtifactHorizon.cshtml"));

        Assert.Contains("Each card opens to the readable notes.", view, StringComparison.Ordinal);
        Assert.Contains("Open notes", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Open data", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("raw data for tools", view, StringComparison.OrdinalIgnoreCase);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    private CommunityCreatorHorizonsService BuildService()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json")
            })
            .Build();

        CommunityStore communityStore = new(configuration, NullLogger<CommunityStore>.Instance);
        InstallLinkingStore installLinkingStore = new(
            configuration,
            DataProtectionProvider.Create(Path.Combine(_root, "install-linking-keys")),
            NullLogger<InstallLinkingStore>.Instance);
        AccountService accounts = new(communityStore);
        WorkspaceLifecyclePolicyService workspaceLifecycle = new(configuration);
        CampaignArtifactRegistryBridge artifactRegistry = new(communityStore);
        HubPublicationDraftService draftService = new();
        CampaignSpineService campaignSpine = new(communityStore, workspaceLifecycle, artifactRegistry, draftService);
        PublicCreatorPublicationDiscoveryService publicCreatorDiscovery = new(accounts, campaignSpine, draftService);

        return new CommunityCreatorHorizonsService(communityStore, installLinkingStore, publicCreatorDiscovery);
    }
}
