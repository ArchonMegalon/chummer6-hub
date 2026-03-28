using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicPrivacyBoundaryServiceTests
{
    [Fact]
    public void BuildPanelReadsPrivacyBoundaryMirror()
    {
        using var fixture = new PublicPrivacyBoundaryFixture();
        fixture.WriteSupportFiles();

        var panel = fixture.CreateService().BuildPanel("privacy");

        Assert.Equal("Support, survey, and assistant data stay on a bounded clock", panel.Heading);
        Assert.Equal("/help", panel.PrimaryAction.Href);
        Assert.Contains(panel.Domains, static item => string.Equals(item.Label, "Provider-backed help", StringComparison.Ordinal) && item.RetentionSummary.Contains("30 days", StringComparison.Ordinal));
        Assert.Contains(panel.SurfaceRules, static item => string.Equals(item.Label, "Public surfaces", StringComparison.Ordinal));
    }

    [Fact]
    public void LoadArtifactJsonPublishesPublicContract()
    {
        using var fixture = new PublicPrivacyBoundaryFixture();
        fixture.WriteSupportFiles();

        string json = fixture.CreateService().LoadArtifactJson();
        using var document = JsonDocument.Parse(json);

        Assert.Equal("chummer.public_privacy_boundaries", document.RootElement.GetProperty("contractName").GetString());
        Assert.Equal("2026-03-28", document.RootElement.GetProperty("asOf").GetString());
        Assert.Equal(4, document.RootElement.GetProperty("domains").GetArrayLength());
        Assert.Equal(3, document.RootElement.GetProperty("surfaceRules").GetArrayLength());
    }

    private sealed class PublicPrivacyBoundaryFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _canonRoot;

        public PublicPrivacyBoundaryFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "public-privacy-boundary-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(_root, "repo");
            Directory.CreateDirectory(_canonRoot);
        }

        public PublicPrivacyBoundaryService CreateService()
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot
                })
                .Build();

            var loader = new PublicCanonFileLoader(configuration);
            var routes = new PublicRouteCatalogService(loader);
            return new PublicPrivacyBoundaryService(loader, routes);
        }

        public void WriteSupportFiles()
        {
            string productRoot = Path.Combine(_canonRoot, ".codex-design", "product");
            Directory.CreateDirectory(productRoot);
            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_PRIVACY_BOUNDARIES.yaml"),
                """
product: chummer
surface: public_privacy_boundaries
version: 1
contract_name: chummer.public_privacy_boundaries
as_of: 2026-03-28
eyebrow: Privacy boundary
heading: Support, survey, and assistant data stay on a bounded clock
summary: Chummer keeps support, install, survey, and provider-backed help surfaces on explicit retention windows and redaction rules instead of stockpiling raw payloads.
micro_proof:
  - Public routes show status and provenance, not private notes or provider transcripts.
domains:
  - id: support_case_truth
    label: Support cases
    owner: chummer6-hub
    retention_summary: 18 months plus 90 day attachment cleanup.
    redaction_summary: Remove secrets and unrelated identity data.
    public_projection: Public routes may show known issues and fix availability.
    signed_in_projection: Signed-in routes may show the reporter-safe timeline.
  - id: claim_install_linkage
    label: Install linkage
    owner: chummer6-hub + chummer6-hub-registry
    retention_summary: 365 days after the last activity.
    redaction_summary: Keep install scope explicit.
    public_projection: Public routes may show release and install posture.
    signed_in_projection: Signed-in routes may show claimed-install state.
  - id: survey_follow_up
    label: Survey follow-up
    owner: chummer6-hub
    retention_summary: 365 days with 180 day raw text cleanup.
    redaction_summary: Keep survey truth out of public guide copy until synthesized.
    public_projection: Public routes may summarize learned product changes.
    signed_in_projection: Signed-in routes may show that follow-up happened.
  - id: provider_traces
    label: Provider-backed help
    owner: executive-assistant + owning surface
    retention_summary: 30 days for raw traces and 180 days for grounded summaries.
    redaction_summary: Prefer case IDs and release IDs over raw user text.
    public_projection: Public help may show grounded answers and cited truth.
    signed_in_projection: Signed-in help may show the curated answer path.
surface_rules:
  - id: public_surfaces
    label: Public surfaces
    summary: Public routes may show support status and provenance.
    blocked_summary: No private case notes or provider traces.
  - id: signed_in_user_surfaces
    label: Signed-in user surfaces
    summary: Signed-in routes may show case timeline and install posture.
    blocked_summary: No unrelated reporter data or operator-only deliberation.
  - id: provider_backed_assistant_surfaces
    label: Provider-backed help
    summary: Provider-backed help must stay grounded in curated truth.
    blocked_summary: It may not become the system of record for support or release state.
""");

            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_LANDING_MANIFEST.yaml"),
                """
product: chummer
surface: public_landing
version: 1
headline: Test
subhead: Test
proof_line: Test
no_provider_names: true
no_ltd_names: true
footer_canonical_source: test
footer_generated_note: test
public_routes:
  - path: /help
  - path: /privacy
  - path: /contact
registered_routes:
  - path: /progress
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
