using System.Text.Json;
using System.Text.Json.Nodes;
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

        Assert.Equal("What Chummer stores, hides, and still needs review", panel.Heading);
        Assert.Equal("/help", panel.PrimaryAction.Href);
        Assert.Contains(panel.Domains, static item => string.Equals(item.Label, "Help tools", StringComparison.Ordinal) && item.RetentionSummary.Contains("30 days", StringComparison.Ordinal));
        Assert.Contains(panel.Domains, static item => string.Equals(item.Label, "Install linkage", StringComparison.Ordinal) && item.RetentionSummary.Contains("365 days", StringComparison.Ordinal));
        var hostedBuild = Assert.Single(
            panel.Domains,
            static item => string.Equals(item.Label, "Hosted Build workspaces", StringComparison.Ordinal));
        Assert.Equal("chummer-presentation", hostedBuild.Owner);
        Assert.Equal("review_required", hostedBuild.Status);
        Assert.True(hostedBuild.ReviewRequired);
        Assert.False(string.IsNullOrWhiteSpace(hostedBuild.LaunchBlockingReason));
        Assert.Contains("unresolved", hostedBuild.RetentionSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("review_required", panel.Status);
        Assert.True(panel.ReviewRequired);
        Assert.False(string.IsNullOrWhiteSpace(panel.LaunchBlockingReason));
        Assert.Contains(panel.SurfaceRules, static item => string.Equals(item.Label, "Public surfaces", StringComparison.Ordinal));
        Assert.DoesNotContain("bounded", panel.Heading, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("assistant data", panel.Heading, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(panel.Domains, static item => item.Label.Contains("Provider-backed", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void LoadArtifactJsonPublishesPublicContract()
    {
        using var fixture = new PublicPrivacyBoundaryFixture();
        fixture.WriteSupportFiles();

        string json = fixture.CreateService().LoadArtifactJson();
        using var document = JsonDocument.Parse(json);

        Assert.Equal("chummer.public_privacy_boundaries", document.RootElement.GetProperty("contractName").GetString());
        Assert.Equal(2, document.RootElement.GetProperty("contractVersion").GetInt32());
        Assert.Equal("2026-03-28", document.RootElement.GetProperty("asOf").GetString());
        Assert.Equal("review_required", document.RootElement.GetProperty("status").GetString());
        Assert.True(document.RootElement.GetProperty("reviewRequired").GetBoolean());
        Assert.False(string.IsNullOrWhiteSpace(document.RootElement.GetProperty("launchBlockingReason").GetString()));
        Assert.Equal(
            "flagship_launch_and_release_supportability",
            document.RootElement.GetProperty("scope").GetString());
        Assert.Equal(
            PrivacyLaunchGate.HostedBuildCapabilityContractName,
            document.RootElement.GetProperty("capabilityContractName").GetString());
        Assert.Equal(
            PrivacyLaunchGate.HostedBuildCapabilityContractVersion,
            document.RootElement.GetProperty("capabilityContractVersion").GetInt32());
        Assert.Equal(
            PrivacyLaunchGate.HostedBuildFacts,
            document.RootElement.GetProperty("facts").EnumerateArray().Select(static item => item.GetString()));
        Assert.Equal(
            PrivacyLaunchGate.HostedBuildProhibitedClaims,
            document.RootElement.GetProperty("prohibitedClaims").EnumerateArray().Select(static item => item.GetString()));
        Assert.True(document.RootElement.GetProperty("blocksLaunch").GetBoolean());
        Assert.Contains(
            "public_release_supportability",
            document.RootElement.GetProperty("blockedClaims").EnumerateArray().Select(static item => item.GetString()));
        JsonElement domains = document.RootElement.GetProperty("domains");
        Assert.Equal(5, domains.GetArrayLength());
        JsonElement hostedBuild = Assert.Single(
            domains.EnumerateArray(),
            static item => string.Equals(
                item.GetProperty("id").GetString(),
                "hosted_build_workspaces",
                StringComparison.Ordinal));
        Assert.Equal("chummer-presentation", hostedBuild.GetProperty("owner").GetString());
        Assert.Equal("review_required", hostedBuild.GetProperty("status").GetString());
        Assert.True(hostedBuild.GetProperty("reviewRequired").GetBoolean());
        Assert.False(string.IsNullOrWhiteSpace(hostedBuild.GetProperty("launchBlockingReason").GetString()));
        Assert.All(
            domains.EnumerateArray().Where(static item => !string.Equals(
                item.GetProperty("id").GetString(),
                "hosted_build_workspaces",
                StringComparison.Ordinal)),
            static item =>
            {
                Assert.Equal("documented", item.GetProperty("status").GetString());
                Assert.False(item.GetProperty("reviewRequired").GetBoolean());
            });
        Assert.Equal(3, document.RootElement.GetProperty("surfaceRules").GetArrayLength());
    }

    [Fact]
    public void BuildPanelAlsoReadsProductionDesignPrivacyHeadings()
    {
        using var fixture = new PublicPrivacyBoundaryFixture();
        fixture.WriteSupportFiles();
        fixture.WriteProductionDesignPrivacyBoundaries();

        var panel = fixture.CreateService().BuildPanel("help");

        Assert.Equal("What Chummer stores, hides, and still needs review", panel.Heading);
        Assert.Equal("/privacy", panel.PrimaryAction.Href);
        Assert.Contains(panel.Domains, static item => string.Equals(item.Label, "Support cases", StringComparison.Ordinal) && item.RetentionSummary.Contains("18 months", StringComparison.Ordinal));
        Assert.Contains(panel.Domains, static item => string.Equals(item.Label, "Help tools", StringComparison.Ordinal) && item.RetentionSummary.Contains("30 days", StringComparison.Ordinal));
        Assert.Contains(panel.Domains, static item => string.Equals(item.Label, "Hosted Build workspaces", StringComparison.Ordinal) && item.ReviewRequired);
        Assert.Contains(panel.SurfaceRules, static item => string.Equals(item.Label, "Help tools", StringComparison.Ordinal) && item.Summary.Contains("curated canonical sources", StringComparison.Ordinal));
    }

    [Fact]
    public void MissingHostedBuildPrivacyDomainFailsClosed()
    {
        using var fixture = new PublicPrivacyBoundaryFixture();
        fixture.WriteSupportFiles();
        fixture.RemoveHostedBuildPrivacyDomain();

        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(
            () => fixture.CreateService().BuildPanel("privacy"));

        Assert.Contains("Hosted Build workspaces", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ProductionCanonKeepsHostedBuildReviewRequiredUntilPolicyIsProven()
    {
        var configuration = new ConfigurationBuilder().Build();
        var loader = new PublicCanonFileLoader(configuration);
        var routes = new PublicRouteCatalogService(loader);
        var service = new PublicPrivacyBoundaryService(loader, routes);

        using var document = JsonDocument.Parse(service.LoadArtifactJson());
        JsonElement root = document.RootElement;
        JsonElement hostedBuild = Assert.Single(
            root.GetProperty("domains").EnumerateArray(),
            static item => string.Equals(
                item.GetProperty("id").GetString(),
                "hosted_build_workspaces",
                StringComparison.Ordinal));

        Assert.Equal(2, root.GetProperty("contractVersion").GetInt32());
        Assert.Equal("review_required", root.GetProperty("status").GetString());
        Assert.True(root.GetProperty("reviewRequired").GetBoolean());
        Assert.Equal("review_required", hostedBuild.GetProperty("status").GetString());
        Assert.True(hostedBuild.GetProperty("reviewRequired").GetBoolean());
        string retention = hostedBuild.GetProperty("retentionSummary").GetString() ?? string.Empty;
        Assert.Contains("unresolved", retention, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotMatch(@"\b\d+\s*(day|days|month|months|year|years)\b", retention);
        Assert.False(string.IsNullOrWhiteSpace(hostedBuild.GetProperty("launchBlockingReason").GetString()));
    }

    [Fact]
    public void PrivacyPanelRendererMakesReviewRequiredPostureVisible()
    {
        var loader = new PublicCanonFileLoader(new ConfigurationBuilder().Build());
        string root = loader.ResolveRepoRoot("Chummer.Run.Api/Views/Shared/_PrivacyBoundaryPanel.cshtml");
        string razor = File.ReadAllText(Path.Combine(
            root,
            "Chummer.Run.Api",
            "Views",
            "Shared",
            "_PrivacyBoundaryPanel.cshtml"));

        Assert.Contains("Model.ReviewRequired", razor, StringComparison.Ordinal);
        Assert.Contains("domain.ReviewRequired", razor, StringComparison.Ordinal);
        Assert.Contains("Review required", razor, StringComparison.Ordinal);
        Assert.Contains("Launch blocker:", razor, StringComparison.Ordinal);
        Assert.Contains("domain.Owner", razor, StringComparison.Ordinal);
    }

    [Fact]
    public void PrivacyLaunchGateMachineContractMatchesPublicProjection()
    {
        var loader = new PublicCanonFileLoader(new ConfigurationBuilder().Build());
        using JsonDocument contract = JsonDocument.Parse(loader.LoadRequiredText(
            ".codex-design/product/PRIVACY_LAUNCH_GATE.json"));
        JsonElement root = contract.RootElement;

        Assert.Equal(PrivacyLaunchGate.ContractName, root.GetProperty("contractName").GetString());
        Assert.Equal(PrivacyLaunchGate.ContractVersion, root.GetProperty("contractVersion").GetInt32());
        Assert.Equal(
            PrivacyLaunchGate.Current.CapabilityContractName,
            root.GetProperty("capabilityContractName").GetString());
        Assert.Equal(
            PrivacyLaunchGate.Current.CapabilityContractVersion,
            root.GetProperty("capabilityContractVersion").GetInt32());
        Assert.Equal(PrivacyLaunchGate.Current.Status, root.GetProperty("status").GetString());
        Assert.Equal(PrivacyLaunchGate.Current.ReviewRequired, root.GetProperty("reviewRequired").GetBoolean());
        Assert.Equal(
            PrivacyLaunchGate.Current.BlocksReleaseSupportability,
            root.GetProperty("blocksLaunch").GetBoolean());
        Assert.Equal(PrivacyLaunchGate.Current.Scope, root.GetProperty("scope").GetString());
        Assert.Equal(
            PrivacyLaunchGate.Current.Facts,
            root.GetProperty("facts").EnumerateArray().Select(static item => item.GetString()));
        Assert.Equal(
            PrivacyLaunchGate.Current.ProhibitedClaims,
            root.GetProperty("prohibitedClaims").EnumerateArray().Select(static item => item.GetString()));
        Assert.Equal(PrivacyLaunchGate.Current.Reason, root.GetProperty("reason").GetString());
        Assert.Equal(
            PrivacyLaunchGate.Current.BlockedClaims,
            root.GetProperty("blockedClaims").EnumerateArray().Select(static item => item.GetString()));
        Assert.True(JsonNode.DeepEquals(
            JsonNode.Parse(root.GetRawText()),
            PrivacyLaunchGate.Current.ToJsonObject()));
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

### Support cases

Owner: `chummer6-hub`

Retention:

* case timeline and user-visible status events: retain for 18 months after the last state change

Redaction baseline:

* remove secrets, local paths, and unrelated identity data from user-visible case history

### Claim and install linkage

Owner: `chummer6-hub` plus `chummer6-hub-registry`

Retention:

* claim tickets and install-link events: retain for 365 days after last install activity

Redaction baseline:

* keep person, install, device-role, and campaign scopes explicit instead of flattening them into a single sync blob

### Hosted Build workspaces

Owner: `chummer-presentation`

Retention:

* backup and point-in-time-recovery retention is unresolved and has no approved numeric public window
* tombstone or lineage retention, deletion replay, and whole-account erasure are unresolved

Redaction baseline:

* workspace content remains owner-scoped and public copy must not promise permanent deletion

### Survey and follow-up results

Owner: `chummer6-hub`

Retention:

* post-fix follow-up invites and answer summaries: retain for 365 days
* raw free-text survey answers: summarize or redact within 180 days unless still tied to open product work

Redaction baseline:

* keep survey conclusions out of public guide copy until they are reviewed

### Help-service logs and answer notes

Owner: `chummer6-hub` plus the owning product surface

Retention:

* raw outside-service request and response logs: retain for 30 days unless a narrower service contract says less
* help summaries and review notes: retain for 180 days

Redaction baseline:

* help summaries should prefer case numbers, release numbers, and calculation records over raw user text where possible

## Surface redaction rules

### Public surfaces

* may expose support status, known issues, release status, compatibility, origin, and channel-aware fix availability
* may not expose private case notes, raw crash reports, outside-service logs, or private survey text

### Signed-in user surfaces

* may expose case timeline, install status, claimed-device state, and the user-safe slice of crash/support data
* may not expose unrelated reporter data, maintainer-only notes, or private moderation notes

### Help and assistant surfaces

* must base answers on reviewed Chummer sources, release records, or support-case records
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

        public void WriteProductionDesignPrivacyBoundaries()
        {
            string productRoot = Path.Combine(_canonRoot, ".codex-design", "product");
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

### Hosted Build workspaces

Owner: `chummer-presentation`

Retention posture:

* backup and point-in-time-recovery retention is unresolved and has no approved numeric public window
* tombstone or lineage retention, deletion replay, and whole-account erasure are unresolved

Redaction baseline:

* workspace content remains owner-scoped and public copy must not promise permanent deletion

### Survey and follow-up results

Owner: `chummer6-hub`

Retention posture:

* post-fix follow-up invites and answer summaries: retain for 365 days

Redaction baseline:

* keep survey truth out of public guide copy until synthesized into canon

### Help-service logs and answer notes

Owner: `executive-assistant` plus the owning product surface

Retention posture:

* raw outside-service request and response logs: retain for 30 days unless a narrower service contract says less
* service comparison notes and answer summaries: retain for 180 days

Redaction baseline:

* answer notes should prefer case numbers, release numbers, and calculation records over raw user text where possible

## Surface redaction rules

### Public surfaces

* may expose support status, known issues, release posture, compatibility, origin, and channel-aware fix availability
* may not expose private case notes, raw crash reports, outside-service logs, or private survey text

### Signed-in user surfaces

* may expose case timeline, install posture, claimed-device state, and the user-safe slice of crash/support data
* may not expose unrelated reporter data, maintainer-only notes, or private moderation notes

### Help tool surfaces

* must ground answers in curated canonical sources, registry truth, or support-case truth
* must not become the system of record for support or release state
""");
        }

        public void RemoveHostedBuildPrivacyDomain()
        {
            string path = Path.Combine(
                _canonRoot,
                ".codex-design",
                "product",
                "PRIVACY_AND_RETENTION_BOUNDARIES.md");
            string markdown = File.ReadAllText(path);
            const string hostedHeading = "### Hosted Build workspaces";
            const string nextHeading = "### Survey and follow-up results";
            int start = markdown.IndexOf(hostedHeading, StringComparison.Ordinal);
            int end = markdown.IndexOf(nextHeading, start, StringComparison.Ordinal);
            if (start < 0 || end <= start)
                throw new InvalidOperationException("Hosted Build privacy fixture section was not found.");

            File.WriteAllText(path, markdown.Remove(start, end - start));
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
