using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicSignalProjectionServiceTests
{
    [Fact]
    public void BuildPacketLoadsFeedbackProjectionBoundary()
    {
        using var fixture = new PublicSignalProjectionFixture();
        fixture.WriteSupportFiles();

        var packet = fixture.CreateService().BuildPacket("/feedback");

        Assert.NotNull(packet);
        Assert.Equal("Hosted public mirror", packet!.Vendor);
        Assert.Equal("/feedback", packet.PublicPath);
        Assert.Equal("/help/feedback", packet.FallbackPath);
        Assert.Equal("Projection Only", packet.TruthPosture);
        Assert.Equal("Public signal is input. Canon is decided by Chummer.", packet.CoreRule);
        Assert.Contains("Do not post private logs", packet.PublicWarning, StringComparison.Ordinal);
        Assert.Contains(packet.BoardTargets, item => string.Equals(item, "Desktop Preview", StringComparison.Ordinal));
        Assert.Contains(packet.AuthorityFlow, item => string.Equals(item, "Public signal posts / votes / comments", StringComparison.Ordinal));
        Assert.Contains(packet.DecisionRoutes, item => string.Equals(item, "Product Governor", StringComparison.Ordinal));
        Assert.Contains(packet.Forbidden, item => string.Equals(item, "Support Case Truth", StringComparison.Ordinal));
        Assert.Contains(packet.JourneyProofEventRefs, item => string.Equals(item.EventKey, "productlift_idea_clustered", StringComparison.Ordinal));
    }

    [Fact]
    public void BuildPacketLoadsChangelogCloseoutRequirements()
    {
        using var fixture = new PublicSignalProjectionFixture();
        fixture.WriteSupportFiles();

        var packet = fixture.CreateService().BuildPacket("/changelog");

        Assert.NotNull(packet);
        Assert.Equal("/now", packet!.FallbackPath);
        Assert.Contains(packet.CloseoutRequirements, item => string.Equals(item, "Closeout Packet", StringComparison.Ordinal));
        Assert.Contains(packet.CloseoutRequirements, item => string.Equals(item, "Public Changelog Entry Or No Entry Reason", StringComparison.Ordinal));
        Assert.Contains(packet.CanonicalSources, item => string.Equals(item, "public_closeout_packets", StringComparison.Ordinal));
        Assert.Contains(packet.JourneyProofEventRefs, item => string.Equals(item.EventKey, "voter_notified", StringComparison.Ordinal));
    }

    [Fact]
    public void BuildPacketReturnsNullForNonProjectionRoute()
    {
        using var fixture = new PublicSignalProjectionFixture();
        fixture.WriteSupportFiles();

        var packet = fixture.CreateService().BuildPacket("/partizipate");

        Assert.Null(packet);
    }

    private sealed class PublicSignalProjectionFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _canonRoot;

        public PublicSignalProjectionFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "public-signal-projection-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(_root, "repo");
            Directory.CreateDirectory(_canonRoot);
        }

        public PublicSignalProjectionService CreateService()
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot
                })
                .Build();

            var loader = new PublicCanonFileLoader(configuration);
            var routes = new PublicRouteCatalogService(loader);
            var releases = new PublicReleaseManifestService(configuration);
            var packets = new PublicSignalToCanonPacketService(releases);
            return new PublicSignalProjectionService(loader, routes, packets);
        }

        public void WriteSupportFiles()
        {
            string productRoot = Path.Combine(_canonRoot, "products", "chummer");
            Directory.CreateDirectory(productRoot);
            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml"),
                """
version: 1
surfaces:
  - key: public_feedback
    vendor: Hosted public mirror
    policy_source: products/chummer/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md
    public_path: /feedback
    fallback_path: /help/feedback
    role: public_feedback_and_voting
    truth_posture: projection_only
    routes_to:
      - executive-assistant
      - product_governor
    forbidden:
      - support_case_truth
      - release_truth
  - key: public_roadmap
    vendor: Hosted public mirror
    policy_source: products/chummer/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md
    public_path: /roadmap
    fallback_path: /horizons
    role: roadmap_projection
    truth_posture: projection_only
    canonical_source:
      - products/chummer/PROGRAM_MILESTONES.yaml
      - products/chummer/HORIZON_REGISTRY.yaml
  - key: public_changelog
    vendor: Hosted public mirror
    policy_source: products/chummer/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md
    public_path: /changelog
    fallback_path: /now
    role: changelog_projection_and_voter_notification
    truth_posture: projection_only
    canonical_source:
      - products/chummer/PUBLIC_RELEASE_EXPERIENCE.yaml
      - public_closeout_packets
closeout_requirements:
  public_shipped_item:
    required:
      - closeout_packet
      - public_changelog_entry_or_no_entry_reason
""");
            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md"),
                """
# Public signal feedback, roadmap, and changelog bridge

## Status

Accepted design posture; implementation remains gated by Chummer-owned routes, adapters, closeout evidence, and validators.

## Authority rule

```text
Public signal posts / votes / comments
  -> EA synthesis
  -> Product Governor decision
  -> chummer6-design canonical patch or milestone
  -> implementation / release / public guide proof
  -> hosted roadmap, changelog, and voter closeout projection
```

Required public warning:

> Do not post private logs, account data, campaign spoilers, copyrighted source text, or private table details. For crashes, bugs, install problems, account issues, or private support, use Chummer Help.

## First board set

Initial public signal boards:

- Desktop Preview
- Build & Explain
- KARMA FORGE
- BLACK LEDGER
- Community Hub
- Mobile Companion
- Creator Publishing
- Guide and Help
""");
            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_SIGNAL_TO_CANON_PIPELINE.md"),
                """
# Public signal to canon pipeline

## Core rule

Public signal is input. Canon is decided by Chummer.
""");
            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_RELEASE_EXPERIENCE.yaml"),
                """
channel: rolling
version: test-run
generated_at_utc: 2026-05-12T00:00:00Z
display:
  channel_label: Rolling
  build_label: Build test-run
  published_label: Published 2026-05-12
artifacts:
  - artifact_id: avalonia-win-x64-installer
    title: Chummer for Windows
    dispatch_href: /downloads/install/avalonia-win-x64-installer
    direct_file_href: /downloads/files/chummer-win.exe
    platform_label: Windows
    head_label: Installer
    size_label: 1 MB
    support_line: Supported
    action_label: Install
    installer: true
    install_access_class: account_required
    requires_account: true
    guest_download_allowed: false
""");

            string manifestRoot = Path.Combine(_canonRoot, ".codex-design", "product");
            Directory.CreateDirectory(manifestRoot);
            File.WriteAllText(
                Path.Combine(manifestRoot, "PUBLIC_LANDING_MANIFEST.yaml"),
                """
product: chummer
surface: chummer.run
version: 1
headline: Test
subhead: Test
proof_line: Test
no_provider_names: true
no_ltd_names: true
public_routes:
  - path: /feedback
  - path: /roadmap
  - path: /changelog
  - path: /help/feedback
  - path: /horizons
  - path: /now
registered_routes:
  - path: /status
""");
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
