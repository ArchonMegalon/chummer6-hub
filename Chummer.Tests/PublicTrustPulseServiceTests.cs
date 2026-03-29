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
        Assert.Equal("Hold launch expansion pending route-canary validation.", snapshot.LaunchReadiness);
        Assert.Equal("Pilot defaults are governed", snapshot.ProviderRouteDefault);
        Assert.Equal("Canary green on all active lanes", snapshot.ProviderRouteCanary);
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

    private sealed class PublicTrustPulseFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _canonRoot;

        public PublicTrustPulseFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "public-trust-pulse-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(_root, "repo");
            Directory.CreateDirectory(_canonRoot);
        }

        public PublicTrustPulseService CreateService()
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot
                })
                .Build();

            return new PublicTrustPulseService(configuration, NullLogger<PublicTrustPulseService>.Instance);
        }

        public void WritePulse(string contractName)
        {
            var pulseDir = Path.Combine(_canonRoot, ".codex-design", "product");
            Directory.CreateDirectory(pulseDir);
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
                    ["supporting_signals"] = new Dictionary<string, object?>
                    {
                        ["overall_progress_percent"] = 73,
                        ["phase_label"] = "Scale & stabilize",
                        ["history_snapshot_count"] = 4,
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

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
