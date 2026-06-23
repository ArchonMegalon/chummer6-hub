using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicTrustPulseServiceTests
{
    [Fact]
    public void LoadSnapshotReadsWeeklyPulseFromCanonRoot()
    {
        using var fixture = new PublicTrustPulseFixture();
        fixture.WritePulse("chummer.weekly_product_pulse");
        fixture.WriteProgressHistory();

        var snapshot = fixture.CreateService().LoadSnapshot();

        Assert.NotNull(snapshot);
        Assert.Equal("2026-03-28", snapshot!.AsOf);
        Assert.Null(snapshot.ActiveCheckpointTitle);
        Assert.Equal("ready", snapshot.JourneyGateState);
        Assert.Equal("Cloud & Publishing", snapshot.LongestPoleLabel);
        Assert.Equal(73, snapshot.OverallProgressPercent);
        Assert.NotNull(snapshot.ProgressTrendSamples);
        Assert.Equal(5, snapshot.ProgressTrendSamples.Count);
        Assert.Equal("2026-03-23", snapshot.ProgressTrendSamples[0].AsOf);
        Assert.Equal(73, snapshot.ProgressTrendSamples[0].OverallProgressPercent);
        Assert.Equal("Hold launch expansion while route canaries are still being checked.", snapshot.LaunchReadiness);
        Assert.Equal("Pilot defaults are settled", snapshot.ProviderRouteDefault);
        Assert.Equal("Canary green across all active routes", snapshot.ProviderRouteCanary);
        Assert.Equal("2026-06-01", snapshot.ProviderRouteReviewDue);
        Assert.Equal("Promote once support fallout remains stable.", snapshot.ProviderRouteNextDecision);
        Assert.Equal("What is the smallest cross-repo slice that makes the campaign OS indispensable and turns trust, adoption, and publication depth into a real launch advantage?", snapshot.NextCheckpointQuestion);
    }

    [Fact]
    public void LoadSnapshotIgnoresUnexpectedContract()
    {
        using var fixture = new PublicTrustPulseFixture();
        fixture.WritePulse("unexpected.contract");

        var snapshot = fixture.CreateService().LoadSnapshot();

        Assert.Null(snapshot);
    }

    [Fact]
    public void LoadSnapshotComputesProgressTrendFromHistory()
    {
        using var fixture = new PublicTrustPulseFixture();
        fixture.WritePulse("chummer.weekly_product_pulse");
        fixture.WriteProgressHistoryWithTwoPoints();

        var snapshot = fixture.CreateService().LoadSnapshot();

        Assert.NotNull(snapshot);
        Assert.Equal(2, snapshot!.ProgressHistorySnapshotCount);
        Assert.Equal("up", snapshot.ProgressTrendDirection);
        Assert.Equal(22, snapshot.ProgressTrendDeltaPercent);
        Assert.Equal("2026-03-22", snapshot.ProgressTrendFromAsOf);
        Assert.Equal("2026-03-29", snapshot.ProgressTrendToAsOf);
    }

    [Fact]
    public void LoadSnapshotReadsClosureHealthFromSynthesizedWeeklyPulse()
    {
        using var fixture = new PublicTrustPulseFixture();
        fixture.WritePulse("chummer.weekly_product_pulse");
        fixture.WriteJourneyGates(waitingClosureCount: 2, pendingHumanResponseCount: 1, blockedCount: 1, warningCount: 0);
        fixture.WriteSupportPackets(openCaseCount: 3, reportedCaseCount: 5, materializedCount: 4, designImpactCount: 1);
        fixture.WriteStatusPlane();
        fixture.WriteLocalReleaseProof("passed");

        var snapshot = fixture.CreateService().LoadSnapshot();

        Assert.NotNull(snapshot);
        Assert.Equal("watch", snapshot!.ClosureHealthState);
        Assert.Equal(3, snapshot.ClosureHealthOpenCaseCount);
        Assert.Equal(2, snapshot.ClosureHealthWaitingCount);
        Assert.Equal(1, snapshot.ClosureHealthPendingHumanResponseCount);
        Assert.Contains("waiting closure", snapshot.ClosureHealthSummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadSnapshotPrefersSynthesizedPulseSignalsWhenFallbackArtifactsAreMissing()
    {
        using var fixture = new PublicTrustPulseFixture();
        fixture.WritePulseWithSynthesizedSignals("chummer.weekly_product_pulse");

        var snapshot = fixture.CreateService().LoadSnapshot();

        Assert.NotNull(snapshot);
        Assert.Equal(6, snapshot!.HistorySnapshotCount);
        Assert.Equal(6, snapshot.ProgressHistorySnapshotCount);
        Assert.Equal("up", snapshot.ProgressTrendDirection);
        Assert.Equal(9, snapshot.ProgressTrendDeltaPercent);
        Assert.Equal("2026-03-24", snapshot.ProgressTrendFromAsOf);
        Assert.Equal("2026-03-30", snapshot.ProgressTrendToAsOf);
        Assert.NotNull(snapshot.ProgressTrendSamples);
        Assert.Equal(3, snapshot.ProgressTrendSamples.Count);
        Assert.Equal("2026-03-24", snapshot.ProgressTrendSamples[0].AsOf);
        Assert.Equal(72, snapshot.ProgressTrendSamples[0].OverallProgressPercent);
        Assert.Equal("passed", snapshot.LocalReleaseProofStatus);
        Assert.Equal(4, snapshot.ProvenJourneyCount);
        Assert.Equal(6, snapshot.ProvenRouteCount);
    }

    [Fact]
    public void LoadSnapshotFailsClosedWhenDesktopClientCoverageIsMissing()
    {
        using var fixture = new PublicTrustPulseFixture();
        fixture.WritePulseWithSynthesizedSignals("chummer.weekly_product_pulse");
        fixture.WriteFlagshipReadiness(status: "fail", missingCoverageKeys: ["desktop_client"]);

        var snapshot = fixture.CreateService().LoadSnapshot();

        Assert.NotNull(snapshot);
        Assert.True(snapshot!.MissingDesktopClientCoverage);
        Assert.Equal("fail", snapshot.FlagshipReadinessStatus);
        Assert.Equal("review_required", snapshot.LocalReleaseProofStatus);
        Assert.Contains("desktop_client", snapshot.FlagshipReadinessReason, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("public routes and support surfaces", snapshot.LaunchReadiness, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("review-required", snapshot.Summary, StringComparison.OrdinalIgnoreCase);
    }

    private sealed class PublicTrustPulseFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _canonRoot;
        private readonly string _fleetArtifactsRoot;

        public PublicTrustPulseFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "public-trust-pulse-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(_root, "repo");
            _fleetArtifactsRoot = Path.Combine(_root, "fleet", ".codex-studio", "published");
            Directory.CreateDirectory(_canonRoot);
            Directory.CreateDirectory(_fleetArtifactsRoot);
        }

        public PublicTrustPulseService CreateService()
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot,
                    ["CHUMMER_PUBLIC_FLEET_ARTIFACT_ROOT"] = _fleetArtifactsRoot,
                    ["CHUMMER_PUBLIC_PROGRESS_REPORT_FILE"] = Path.Combine(_canonRoot, ".codex-design", "product", "PROGRESS_REPORT.generated.json"),
                    ["CHUMMER_PUBLIC_PROGRESS_HISTORY_FILE"] = Path.Combine(_canonRoot, ".codex-design", "product", "PROGRESS_HISTORY.generated.json"),
                    ["CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE"] = Path.Combine(_canonRoot, ".codex-studio", "published", "HUB_LOCAL_RELEASE_PROOF.generated.json"),
                    ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE"] = Path.Combine(_fleetArtifactsRoot, "FLAGSHIP_PRODUCT_READINESS.generated.json")
                })
                .Build();

            var weeklyPulse = new WeeklyProductPulseArtifactService(configuration, NullLogger<WeeklyProductPulseArtifactService>.Instance);
            return new PublicTrustPulseService(weeklyPulse, configuration, NullLogger<PublicTrustPulseService>.Instance);
        }

        public void WritePulse(string contractName)
        {
            WritePulse(contractName, extraSupportingSignals: null);
        }

        public void WritePulseWithSynthesizedSignals(string contractName)
        {
            WritePulse(
                contractName,
                new Dictionary<string, object?>
                {
                    ["history_snapshot_count"] = 6,
                    ["adoption_health"] = new Dictionary<string, object?>
                    {
                        ["state"] = "clear",
                        ["local_release_proof_status"] = "passed",
                        ["proven_journey_count"] = 4,
                        ["proven_route_count"] = 6,
                        ["history_snapshot_count"] = 6,
                        ["summary"] = "Current local verification passed with multi-route evidence."
                    },
                    ["progress_trend"] = new Dictionary<string, object?>
                    {
                        ["state"] = "moving",
                        ["direction"] = "up",
                        ["delta_percent"] = 9,
                        ["from_as_of"] = "2026-03-24",
                        ["to_as_of"] = "2026-03-30",
                        ["sample_count"] = 3,
                        ["summary"] = "Upward momentum across the last three measured snapshots.",
                        ["samples"] = new[]
                        {
                            new Dictionary<string, object?>
                            {
                                ["as_of"] = "2026-03-24",
                                ["overall_progress_percent"] = 72
                            },
                            new Dictionary<string, object?>
                            {
                                ["as_of"] = "2026-03-27",
                                ["overall_progress_percent"] = 77
                            },
                            new Dictionary<string, object?>
                            {
                                ["as_of"] = "2026-03-30",
                                ["overall_progress_percent"] = 81
                            }
                        }
                    }
                });
        }

        private void WritePulse(string contractName, Dictionary<string, object?>? extraSupportingSignals)
        {
            var pulseDir = Path.Combine(_canonRoot, ".codex-design", "product");
            Directory.CreateDirectory(pulseDir);
            var supportingSignals = new Dictionary<string, object?>
            {
                ["overall_progress_percent"] = 73,
                ["phase_label"] = "Scale & stabilize",
                ["history_snapshot_count"] = 4,
                ["longest_pole"] = "Cloud & Publishing",
                ["launch_readiness"] = "Hold launch expansion while route canaries are still being checked.",
                ["provider_route_stewardship"] = new Dictionary<string, object?>
                {
                    ["default_status"] = "Pilot defaults are settled",
                    ["canary_status"] = "Canary green across all active routes",
                    ["review_due"] = "2026-06-01",
                    ["next_decision"] = "Promote once support fallout remains stable."
                }
            };

            if (extraSupportingSignals is not null)
            {
                foreach ((string key, object? value) in extraSupportingSignals)
                {
                    supportingSignals[key] = value;
                }
            }

            File.WriteAllText(
                Path.Combine(pulseDir, "WEEKLY_PRODUCT_PULSE.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = contractName,
                    ["as_of"] = "2026-03-28",
                    ["summary"] = "Journey proof is ready and the longest pole remains Cloud & Publishing.",
                    ["active_wave"] = "Next 20 Big Wins After Post-Audit Closeout",
                    ["active_wave_status"] = "in_progress",
                    ["journey_gate_health"] = new Dictionary<string, object?>
                    {
                        ["state"] = "ready",
                        ["reason"] = "Journey proof is steady on current published evidence.",
                        ["blocked_count"] = 0,
                        ["warning_count"] = 0
                    },
                    ["next_checkpoint_question"] = "What is the smallest cross-repo slice that makes the campaign OS indispensable and turns trust, adoption, and publication depth into a real launch advantage?",
                    ["snapshot"] = new Dictionary<string, object?>
                    {
                        ["release_health"] = new Dictionary<string, object?>
                        {
                            ["state"] = "green_or_explained",
                            ["reason"] = "No red blockers are open."
                        }
                    },
                    ["supporting_signals"] = supportingSignals
                }));
        }

        public void WriteProgressHistory()
        {
            var historyDir = Path.Combine(_canonRoot, ".codex-design", "product");
            Directory.CreateDirectory(historyDir);
            File.WriteAllText(
                Path.Combine(historyDir, "PROGRESS_HISTORY.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.public_progress_history",
                    ["snapshot_count"] = 5,
                    ["snapshots"] = new[]
                    {
                        new Dictionary<string, object?>
                        {
                            ["as_of"] = "2026-03-23",
                            ["overall_progress_percent"] = 73
                        },
                        new Dictionary<string, object?>
                        {
                            ["as_of"] = "2026-03-25",
                            ["overall_progress_percent"] = 73
                        },
                        new Dictionary<string, object?>
                        {
                            ["as_of"] = "2026-03-27",
                            ["overall_progress_percent"] = 73
                        },
                        new Dictionary<string, object?>
                        {
                            ["as_of"] = "2026-03-28",
                            ["overall_progress_percent"] = 100
                        },
                        new Dictionary<string, object?>
                        {
                            ["as_of"] = "2026-03-29",
                            ["overall_progress_percent"] = 100
                    }
                    }
                }));
        }

        public void WriteFlagshipReadiness(string status, IReadOnlyList<string> missingCoverageKeys)
        {
            Directory.CreateDirectory(_fleetArtifactsRoot);
            File.WriteAllText(
                Path.Combine(_fleetArtifactsRoot, "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.flagship_product_readiness",
                    ["status"] = status,
                    ["completion_audit"] = new Dictionary<string, object?>
                    {
                        ["reason"] = "Flagship product readiness planes are not green."
                    },
                    ["flagship_readiness_audit"] = new Dictionary<string, object?>
                    {
                        ["reason"] = "flagship product readiness proof is not green: missing coverage: desktop_client",
                        ["missing_coverage_keys"] = missingCoverageKeys,
                        ["scoped_missing_coverage_keys"] = missingCoverageKeys
                    }
                }));
        }

        public void WriteProgressHistoryWithTwoPoints()
        {
            var historyDir = Path.Combine(_canonRoot, ".codex-design", "product");
            Directory.CreateDirectory(historyDir);
            File.WriteAllText(
                Path.Combine(historyDir, "PROGRESS_HISTORY.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.public_progress_history",
                    ["snapshot_count"] = 2,
                    ["snapshots"] = new[]
                    {
                        new Dictionary<string, object?>
                        {
                            ["as_of"] = "2026-03-22",
                            ["overall_progress_percent"] = 69
                        },
                        new Dictionary<string, object?>
                        {
                            ["as_of"] = "2026-03-29",
                            ["overall_progress_percent"] = 91
                        }
                    }
                }));
        }

        public void WriteJourneyGates(int waitingClosureCount, int pendingHumanResponseCount, int blockedCount, int warningCount)
        {
            File.WriteAllText(
                Path.Combine(_fleetArtifactsRoot, "JOURNEY_GATES.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.journey_gates",
                    ["generated_at"] = "2026-03-29T09:01:00Z",
                    ["summary"] = new Dictionary<string, object?>
                    {
                        ["overall_state"] = blockedCount > 0 ? "blocked" : "ready",
                        ["blocked_count"] = blockedCount,
                        ["warning_count"] = warningCount,
                        ["recommended_action"] = "Resolve the blocking golden-journey gaps before widening publish claims."
                    },
                    ["journeys"] = new[]
                    {
                        new Dictionary<string, object?>
                        {
                            ["signals"] = new Dictionary<string, object?>
                            {
                                ["support_closure_waiting_count"] = waitingClosureCount,
                                ["support_needs_human_response_count"] = pendingHumanResponseCount
                            }
                        }
                    }
                }));
        }

        public void WriteSupportPackets(int openCaseCount, int reportedCaseCount, int materializedCount, int designImpactCount)
        {
            File.WriteAllText(
                Path.Combine(_fleetArtifactsRoot, "SUPPORT_CASE_PACKETS.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.support_case_packets",
                    ["generated_at"] = "2026-03-29T09:02:00Z",
                    ["source"] = new Dictionary<string, object?>
                    {
                        ["materialized_count"] = materializedCount,
                        ["reported_count"] = reportedCaseCount
                    },
                    ["summary"] = new Dictionary<string, object?>
                    {
                        ["open_case_count"] = openCaseCount,
                        ["design_impact_count"] = designImpactCount
                    }
                }));
        }

        public void WriteStatusPlane()
        {
            File.WriteAllText(
                Path.Combine(_fleetArtifactsRoot, "STATUS_PLANE.generated.yaml"),
                """
contract_name: fleet.status_plane
generated_at: '2026-03-29T09:03:00Z'
deployment_posture:
  public_target_count: 4
runtime_healing:
  summary:
    degraded_service_count: 0
    alert_state: healthy
projects:
  - id: hub
    deployment_promotion_stage: promoted_preview
    deployment_access_posture: public
""");
        }

        public void WriteLocalReleaseProof(string status)
        {
            var proofDir = Path.Combine(_canonRoot, ".codex-studio", "published");
            Directory.CreateDirectory(proofDir);
            File.WriteAllText(
                Path.Combine(proofDir, "HUB_LOCAL_RELEASE_PROOF.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "chummer6-hub.local_release_proof",
                    ["generated_at"] = "2026-03-29T09:04:00Z",
                    ["status"] = status,
                    ["journeys_passed"] = new[] { "install_claim_restore_continue", "build_explain_publish" },
                    ["proof_routes"] = new[] { "/", "/downloads", "/help" }
                }));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
