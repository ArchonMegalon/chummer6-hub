using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class GoldReadinessArtifactServiceTests
{
    [Fact]
    public void LoadSnapshotReadsFailingRuleAuthorityBlockers()
    {
        string root = Path.Combine(Path.GetTempPath(), "gold-readiness-artifact-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string artifactPath = Path.Combine(root, "FINAL_GOLD_JANITOR.generated.json");

        try
        {
            File.WriteAllText(artifactPath, JsonSerializer.Serialize(new
            {
                contract_name = "chummer.final_gold_janitor",
                generated_at_utc = "2026-06-09T12:56:31Z",
                status = "fail",
                verdict = "NOT_GOLD",
                required_gates = new
                {
                    rule_authority_minimum_coverage = new
                    {
                        rulesets = new
                        {
                            sr4 = new
                            {
                                status = "fail",
                                rulefact_count = 285,
                                final_verdict = "NOT_READY",
                                row_level_mapping_status = "pending_human_review",
                                errata_posture_status = "pending_reviewed_application",
                                human_review_status = new
                                {
                                    pending_review = true,
                                    review_ready = false,
                                    source_baseline_required = true
                                },
                                verification_matrix_status = "blocked",
                                verification_matrix_failed_gates = new[] { "SR4-G013" },
                                verification_matrix_unexpected_failed_gates = Array.Empty<string>(),
                                remaining_gates = new[]
                                {
                                    "human-reviewed row-level mapping from indexed table evidence into normalized records",
                                    "errata profile applied and reviewed",
                                    "human rule review signoff"
                                }
                            },
                            sr5 = new
                            {
                                status = "pass",
                                rulefact_count = 375,
                                final_verdict = "SR5_RULE_AUTHORITY_READY",
                                remaining_gates = Array.Empty<string>()
                            }
                        }
                    }
                },
                failures = new[] { "sr4 final_verdict is not ready" }
            }));

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_FINAL_GOLD_JANITOR_FILE"] = artifactPath
                })
                .Build();

            var snapshot = new GoldReadinessArtifactService(configuration).LoadSnapshot();

            Assert.NotNull(snapshot);
            Assert.Equal("NOT_GOLD", snapshot!.Verdict);
            Assert.Single(snapshot.RuleAuthorityBlockers);
            GoldReadinessRuleAuthorityBlocker blocker = Assert.Single(snapshot.RuleAuthorityBlockers);
            Assert.Equal("sr4", blocker.RulesetId);
            Assert.Equal(285, blocker.RulefactCount);
            Assert.Equal("pending_human_review", blocker.RowLevelMappingStatus);
            Assert.Equal("pending_reviewed_application", blocker.ErrataPostureStatus);
            Assert.True(blocker.HumanReviewPending);
            Assert.False(blocker.HumanReviewReady);
            Assert.True(blocker.SourceBaselineRequired);
            Assert.Equal("blocked", blocker.VerificationMatrixStatus);
            Assert.Equal(new[] { "SR4-G013" }, blocker.VerificationMatrixFailedGates);
            Assert.Empty(blocker.VerificationMatrixUnexpectedFailedGates);
            Assert.Contains("human rule review signoff", blocker.RemainingGates);
        }
        finally
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }
}
