using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class WeeklyProductPulseArtifactServiceTests
{
    [Fact]
    public void LoadWeeklyPulseJsonOverlaysEvidenceBackedSignals()
    {
        using var fixture = new WeeklyPulseFixture();
        fixture.WriteBasePulse();
        fixture.WriteProgressReport();
        fixture.WriteJourneyGates();
        fixture.WriteSupportPackets();
        fixture.WriteStatusPlane();
        fixture.WriteLocalReleaseProof();

        string json = fixture.CreateService().LoadWeeklyPulseJson();
        using JsonDocument document = JsonDocument.Parse(json);

        Assert.Equal("2026-03-29", document.RootElement.GetProperty("as_of").GetString());
        Assert.Equal("blocked", document.RootElement.GetProperty("journey_gate_health").GetProperty("state").GetString());
        Assert.Equal(1, document.RootElement.GetProperty("journey_gate_health").GetProperty("blocked_count").GetInt32());
        Assert.Equal("Public-fit polish", document.RootElement.GetProperty("supporting_signals").GetProperty("phase_label").GetString());
        Assert.Equal("Core Engine", document.RootElement.GetProperty("supporting_signals").GetProperty("longest_pole").GetString());
        Assert.Contains("route-canary validation", document.RootElement.GetProperty("supporting_signals").GetProperty("launch_readiness").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Equal("Pilot defaults are governed", document.RootElement.GetProperty("supporting_signals").GetProperty("provider_route_stewardship").GetProperty("default_status").GetString());
        Assert.Equal("clear", document.RootElement.GetProperty("supporting_signals").GetProperty("closure_health").GetProperty("state").GetString());
        Assert.Equal(0, document.RootElement.GetProperty("supporting_signals").GetProperty("closure_health").GetProperty("waiting_closure_count").GetInt32());
    }

    private sealed class WeeklyPulseFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _canonRoot;
        private readonly string _fleetArtifactsRoot;

        public WeeklyPulseFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "weekly-pulse-artifact-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(_root, "repo");
            _fleetArtifactsRoot = Path.Combine(_root, "fleet", ".codex-studio", "published");
            Directory.CreateDirectory(Path.Combine(_canonRoot, ".codex-design", "product"));
            Directory.CreateDirectory(Path.Combine(_canonRoot, ".codex-studio", "published"));
            Directory.CreateDirectory(_fleetArtifactsRoot);
        }

        public WeeklyProductPulseArtifactService CreateService()
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot,
                    ["CHUMMER_PUBLIC_FLEET_ARTIFACT_ROOT"] = _fleetArtifactsRoot
                })
                .Build();

            return new WeeklyProductPulseArtifactService(configuration, NullLogger<WeeklyProductPulseArtifactService>.Instance);
        }

        public void WriteBasePulse()
        {
            File.WriteAllText(
                Path.Combine(_canonRoot, ".codex-design", "product", "WEEKLY_PRODUCT_PULSE.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "chummer.weekly_product_pulse",
                    ["generated_at"] = "2026-03-29T08:30:00Z",
                    ["as_of"] = "2026-03-28",
                    ["active_wave"] = "Next 20 Big Wins After Post-Audit Closeout",
                    ["active_wave_status"] = "in_progress",
                    ["summary"] = "Baseline summary.",
                    ["journey_gate_health"] = new Dictionary<string, object?>
                    {
                        ["state"] = "ready",
                        ["reason"] = "Baseline journey reason.",
                        ["blocked_count"] = 0,
                        ["warning_count"] = 0
                    },
                    ["snapshot"] = new Dictionary<string, object?>
                    {
                        ["release_health"] = new Dictionary<string, object?>
                        {
                            ["state"] = "green_or_explained",
                            ["reason"] = "No red blockers are open."
                        }
                    },
                    ["next_checkpoint_question"] = "What is the smallest cross-repo slice that makes the campaign OS indispensable and turns trust, adoption, and publication depth into a real launch advantage?",
                    ["supporting_signals"] = new Dictionary<string, object?>
                    {
                        ["phase_label"] = "Scale & stabilize",
                        ["longest_pole"] = "Cloud & Publishing",
                        ["launch_readiness"] = "Hold launch expansion pending route-canary validation.",
                        ["provider_route_stewardship"] = new Dictionary<string, object?>
                        {
                            ["default_status"] = "Pilot defaults are governed",
                            ["canary_status"] = "Canary green on all active lanes",
                            ["review_due"] = "2026-06-01",
                            ["next_decision"] = "Promote once support fallout remains stable."
                        }
                    }
                }));
        }

        public void WriteProgressReport()
        {
            File.WriteAllText(
                Path.Combine(_canonRoot, ".codex-design", "product", "PROGRESS_REPORT.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.public_progress_report",
                    ["generated_at"] = "2026-03-29T08:36:12Z",
                    ["as_of"] = "2026-03-29",
                    ["active_wave"] = "Next 20 Big Wins After Post-Audit Closeout",
                    ["active_wave_status"] = "in_progress",
                    ["history_snapshot_count"] = 5,
                    ["overall_progress_percent"] = 100,
                    ["phase_label"] = "Public-fit polish",
                    ["longest_pole"] = new Dictionary<string, object?>
                    {
                        ["label"] = "Core Engine"
                    }
                }));
        }

        public void WriteJourneyGates()
        {
            File.WriteAllText(
                Path.Combine(_fleetArtifactsRoot, "JOURNEY_GATES.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.journey_gates",
                    ["generated_at"] = "2026-03-29T08:37:12Z",
                    ["summary"] = new Dictionary<string, object?>
                    {
                        ["overall_state"] = "blocked",
                        ["blocked_count"] = 1,
                        ["warning_count"] = 0,
                        ["recommended_action"] = "Resolve the blocking golden-journey gaps before widening publish claims."
                    },
                    ["journeys"] = new[]
                    {
                        new Dictionary<string, object?>
                        {
                            ["signals"] = new Dictionary<string, object?>
                            {
                                ["support_closure_waiting_count"] = 0,
                                ["support_needs_human_response_count"] = 0
                            }
                        }
                    }
                }));
        }

        public void WriteSupportPackets()
        {
            File.WriteAllText(
                Path.Combine(_fleetArtifactsRoot, "SUPPORT_CASE_PACKETS.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "fleet.support_case_packets",
                    ["generated_at"] = "2026-03-29T08:38:12Z",
                    ["source"] = new Dictionary<string, object?>
                    {
                        ["materialized_count"] = 0,
                        ["reported_count"] = 2
                    },
                    ["summary"] = new Dictionary<string, object?>
                    {
                        ["open_case_count"] = 0,
                        ["design_impact_count"] = 0
                    }
                }));
        }

        public void WriteStatusPlane()
        {
            File.WriteAllText(
                Path.Combine(_fleetArtifactsRoot, "STATUS_PLANE.generated.yaml"),
                """
contract_name: fleet.status_plane
generated_at: '2026-03-29T08:39:12Z'
deployment_posture:
  public_target_count: 6
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

        public void WriteLocalReleaseProof()
        {
            File.WriteAllText(
                Path.Combine(_canonRoot, ".codex-studio", "published", "HUB_LOCAL_RELEASE_PROOF.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "chummer6-hub.local_release_proof",
                    ["generated_at"] = "2026-03-29T08:40:12Z",
                    ["status"] = "passed"
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
