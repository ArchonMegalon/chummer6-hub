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
        Assert.Contains(panel.Domains, static item => string.Equals(item.Label, "Install linkage", StringComparison.Ordinal) && item.RetentionSummary.Contains("365 days", StringComparison.Ordinal));
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
                Path.Combine(productRoot, "PRIVACY_AND_RETENTION_BOUNDARIES.md"),
                """
# Privacy and retention boundaries

## Retention domains

### Support-case truth

Owner: `chummer6-hub`

Retention posture:

* case timeline and user-visible status events: retain for 18 months after the last state change

Redaction baseline:

* remove secrets, local paths, and unrelated identity data from user-visible case history

### Claim and install linkage

Owner: `chummer6-hub` plus `chummer6-hub-registry`

Retention posture:

* claim tickets and install-link events: retain for 365 days after last install activity

Redaction baseline:

* keep person, install, device-role, and campaign scopes explicit instead of flattening them into a single sync blob

### Survey and follow-up results

Owner: `chummer6-hub`

Retention posture:

* post-fix follow-up invites and answer summaries: retain for 365 days
* raw free-text survey payloads: summarize or redact within 180 days unless still tied to an open product-governor packet

Redaction baseline:

* keep survey truth out of public guide copy until synthesized into canon

### Provider traces and assistant grounding packs

Owner: `executive-assistant` plus the owning product surface

Retention posture:

* raw provider request/response traces: retain for 30 days unless a narrower provider contract says less
* lane-level scorecards, challenger briefs, and grounding-pack summaries: retain for 180 days

Redaction baseline:

* grounding packs should prefer case IDs, release IDs, and rule receipt IDs over raw user text where possible

## Surface redaction rules

### Public surfaces

* may expose support status, known issues, release posture, compatibility, provenance, and channel-aware fix availability
* may not expose private case notes, raw crash envelopes, provider traces, or account-internal survey payloads

### Signed-in user surfaces

* may expose case timeline, install posture, claimed-device state, and the user-safe slice of crash/support data
* may not expose unrelated reporter data, operator-only packet deliberation, or private moderation notes

### Provider-backed assistant surfaces

* must ground answers in curated canonical sources, registry truth, or support-case truth
* must not become the system of record for support or release state
""");
            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_TRUST_CONTENT.yaml"),
                """
product: chummer
surface: chummer.run
version: 1
trust_pages:
  - id: privacy
    eyebrow: "Privacy"
    heading: "What Chummer stores, and what it does not"
    intro: "This is the practical hosted-product posture right now."
    effective_date: "2026-03-25"
    updated_date: "2026-03-28"
    summary_points:
      - "The published package stays the same for everyone"
      - "Hub stores account and support state"
      - "Provider secrets stay out of Hub"
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
