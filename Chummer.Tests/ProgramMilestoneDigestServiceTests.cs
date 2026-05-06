using Microsoft.Extensions.Configuration;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ProgramMilestoneDigestServiceTests
{
    [Fact]
    public void BuildOpenMilestonesProjectsClaimedDifficultyAndDependencies()
    {
        string repoRoot = CreateCanonRoot(
            """
            product: chummer
            version: 1
            implementation_order_milestone_ids:
              - 120
              - 121
              - 122
            milestones:
              - id: 101
                title: Desktop release truth
                wave: W6
                status: complete
              - id: 111
                title: Concierge follow-through
                wave: W9
                status: in_progress
              - id: 120
                title: Public trust refresh
                wave: W14
                owners:
                  - chummer6-hub
                  - chummer6-hub-registry
                  - fleet
                  - executive-assistant
                status: in_progress
                dependencies:
                  - 101
                  - 111
                exit_criteria:
                  - Public trust surface can launch locale-matched proof refs without governed posture drift.
                work_tasks:
                  - id: 120.1
                    owner: chummer6-hub
                  - id: 120.2
                    owner: executive-assistant
                    status: complete
              - id: 121
                title: GM Runboard
                wave: W15
                owners:
                  - chummer6-core
                  - chummer6-ui-kit
                  - chummer6-ui
                  - chummer6-mobile
                  - chummer6-hub
                  - chummer6-design
                status: not_started
                dependencies:
                  - 101
                  - 111
                  - 120
                  - 122
                exit_criteria:
                  - One player and one GM can complete one SR6 combat round with action-budget truth and source anchors visible on promoted surfaces.
                work_tasks:
                  - id: 121.1
                    owner: chummer6-core
                  - id: 121.2
                    owner: chummer6-ui
                    status: complete
                  - id: 121.3
                    owner: chummer6-mobile
              - id: 122
                title: Consequence loop
                wave: W15
                owners:
                  - chummer6-hub
                status: not_started
                exit_criteria:
                  - Campaign state can stay understandable between sessions.
                work_tasks:
                  - id: 122.1
                    owner: chummer6-hub
            """);

        try
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = repoRoot
                })
                .Build();
            var service = new ProgramMilestoneDigestService(new PublicCanonFileLoader(configuration));

            var milestones = service.BuildOpenMilestones();

            Assert.Collection(
                milestones,
                milestone => Assert.Equal("120", milestone.Id),
                milestone => Assert.Equal("121", milestone.Id),
                milestone => Assert.Equal("122", milestone.Id),
                milestone => Assert.Equal("111", milestone.Id));

            var activeMilestone = milestones[0];
            Assert.Equal("In progress", activeMilestone.StatusLabel);
            Assert.True(activeMilestone.Claimed);
            Assert.Equal("Medium", activeMilestone.DifficultyLabel);
            Assert.Equal("Depends on 2 other milestones.", activeMilestone.DependencySummary);
            Assert.Contains("localized proof references", activeMilestone.CasualSummary, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("status drift", activeMilestone.CasualSummary, StringComparison.OrdinalIgnoreCase);

            var partiallyClaimedMilestone = milestones[1];
            Assert.True(partiallyClaimedMilestone.Claimed);
            Assert.Equal("High", partiallyClaimedMilestone.DifficultyLabel);
            Assert.Equal("Claimed", partiallyClaimedMilestone.ClaimedLabel);
            Assert.Contains("1 of 3 tracked slice(s)", partiallyClaimedMilestone.ClaimedSummary, StringComparison.Ordinal);
            Assert.Equal(["101", "111", "120", "122"], partiallyClaimedMilestone.Dependencies.Select(static dependency => dependency.Id).ToArray());
            Assert.Contains("action-budget state", partiallyClaimedMilestone.CasualSummary, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("main screens", partiallyClaimedMilestone.CasualSummary, StringComparison.OrdinalIgnoreCase);

            var unclaimedMilestone = milestones[2];
            Assert.False(unclaimedMilestone.Claimed);
            Assert.Equal("Unclaimed", unclaimedMilestone.ClaimedLabel);
            Assert.Equal("No upstream milestone dependency.", unclaimedMilestone.DependencySummary);

            var appendedOpenMilestone = milestones[3];
            Assert.Equal("In progress", appendedOpenMilestone.StatusLabel);
            Assert.Equal("Low", appendedOpenMilestone.DifficultyLabel);
            Assert.True(appendedOpenMilestone.Claimed);
        }
        finally
        {
            Directory.Delete(repoRoot, recursive: true);
        }
    }

    private static string CreateCanonRoot(string yaml)
    {
        string repoRoot = Path.Combine(Path.GetTempPath(), $"program-milestone-digest-{Guid.NewGuid():N}");
        string productDirectory = Path.Combine(repoRoot, ".codex-design", "product");
        Directory.CreateDirectory(productDirectory);
        File.WriteAllText(Path.Combine(productDirectory, "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"), yaml);
        return repoRoot;
    }
}
