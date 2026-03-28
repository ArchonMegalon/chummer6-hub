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

        var snapshot = fixture.CreateService().LoadSnapshot();

        Assert.NotNull(snapshot);
        Assert.Equal("2026-03-28", snapshot!.AsOf);
        Assert.Null(snapshot.ActiveCheckpointTitle);
        Assert.Equal("ready", snapshot.JourneyGateState);
        Assert.Equal("Cloud & Publishing", snapshot.LongestPoleLabel);
        Assert.Equal(73, snapshot.OverallProgressPercent);
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
                        ["longest_pole"] = "Cloud & Publishing"
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
