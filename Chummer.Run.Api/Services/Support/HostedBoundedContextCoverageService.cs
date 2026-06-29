using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class HostedBoundedContextCoverageService
{
    private readonly PublicReleaseManifestService _releases;

    public HostedBoundedContextCoverageService(PublicReleaseManifestService releases)
    {
        _releases = releases;
    }

    public HostedBoundedContextCoverageBundle Build(HostedBoundedContextCoverageContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        DateTimeOffset now = DateTimeOffset.UtcNow;
        IReadOnlyList<GroupDto> groups = context.Groups ?? [];
        GroupDto? primaryGroup = groups
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        string communityHubRoute = string.IsNullOrWhiteSpace(context.CommunityHubRoute)
            ? "/account/work#community-ops"
            : context.CommunityHubRoute!;
        SignalToCanonPacketProjection? feedbackPacket = context.PublicSignals?.Packets
            .FirstOrDefault(item => string.Equals(item.SurfaceId, "feedback", StringComparison.Ordinal));
        ClaimedInstallationDto? installation = context.InstallLinking?.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        DownloadReceiptDto? receipt = context.InstallLinking?.RecentReceipts?
            .OrderByDescending(static item => item.IssuedAtUtc)
            .FirstOrDefault();

        return new HostedBoundedContextCoverageBundle(
            BuiltAtUtc: now,
            Projections:
            [
                BuildPublicContext(manifest, feedbackPacket, now, context.Locale),
                BuildAccountContext(manifest, context.User, groups, now, context.Locale),
                BuildCommunityContext(manifest, primaryGroup, context.OpenRun, communityHubRoute, now, context.Locale),
                BuildCampaignContext(manifest, context.OpenRun, communityHubRoute, now, context.Locale),
                BuildSupportContext(manifest, context.SupportCase, now, context.Locale),
                BuildOrchestrationBoundary(manifest, installation, receipt, now, context.Locale),
                BuildBoundedContextClosure(manifest, communityHubRoute, now, context.Locale)
            ]);
    }

    private static HostedBoundedContextCoverageProjection BuildPublicContext(
        PublicReleaseManifestDto manifest,
        SignalToCanonPacketProjection? feedbackPacket,
        DateTimeOffset now,
        string locale)
    {
        return new HostedBoundedContextCoverageProjection(
            ProjectionId: StableId("hosted-bounded-context-public", manifest.Version),
            SurfaceId: "public_context",
            Route: "/",
            ComparisonRoute: feedbackPacket?.Route ?? "/participate",
            BoundaryOwner: "public_guide_context",
            DecisionAuthority: "public_release_manifest_and_navigation",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: "Public landing, downloads, roadmap, and Participate stay openly readable and release-backed instead of leaking signed-in account, support, or campaign internals.",
            EvidenceLines:
            [
                "/, /downloads, /now, and /horizons remain openly readable public pages.",
                feedbackPacket is null
                    ? "Public signal still enters through /participate before any account-linked followthrough is attached."
                    : $"{feedbackPacket.Route} keeps reviewed public feedback separate from account support and account pages.",
                "Public routes compare against the published release status rather than worker-local helper state."
            ],
            Actions:
            [
                new HostedBoundedContextCoverageActionProjection("open_public_landing", "Open public landing", "/", "Inspect the openly readable product entry page."),
                new HostedBoundedContextCoverageActionProjection("open_downloads", "Open downloads", "/downloads", "Compare public release and install entry status."),
                new HostedBoundedContextCoverageActionProjection("open_participate", "Open Participate", feedbackPacket?.Route ?? "/participate", "Inspect the reviewed public feedback page.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: manifest.Version);
    }

    private static HostedBoundedContextCoverageProjection BuildAccountContext(
        PublicReleaseManifestDto manifest,
        HubUserDto? user,
        IReadOnlyList<GroupDto> groups,
        DateTimeOffset now,
        string locale)
    {
        string summary = user is null
            ? "Account context stays closed until an account identity exists, keeping profile, access, rewards, and entitlements off guest routes."
            : $"{user.DisplayName} keeps profile, access, rewards, and entitlements on the account page with {groups.Count.ToString(CultureInfo.InvariantCulture)} reviewed group attachment(s).";

        return new HostedBoundedContextCoverageProjection(
            ProjectionId: StableId("hosted-bounded-context-account", user?.UserId ?? manifest.Version),
            SurfaceId: "account_context",
            Route: "/account",
            ComparisonRoute: "/account/access",
            BoundaryOwner: "accounts_and_community_context",
            DecisionAuthority: "account_profile_and_install_claim_truth",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                user is null
                    ? "No account is active, so /account remains protected."
                    : $"Account {user.UserId} keeps {user.LinkedPrincipals.Count.ToString(CultureInfo.InvariantCulture)} linked sign-in method(s) on the account page.",
                "/account/access is the comparison route for claimed-install and recovery posture.",
                "Account routes may summarize support, community, or campaign posture, but those details stay owned by their home contexts."
            ],
            Actions:
            [
                new HostedBoundedContextCoverageActionProjection("open_account", "Open account", "/account", "Inspect the account page."),
                new HostedBoundedContextCoverageActionProjection("open_account_access", "Open devices & access", "/account/access", "Inspect claimed-install and access continuity."),
                new HostedBoundedContextCoverageActionProjection("open_rewards", "Open rewards", "/rewards", "Compare account status with reusable reward followthrough.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: user?.UserId);
    }

    private static HostedBoundedContextCoverageProjection BuildCommunityContext(
        PublicReleaseManifestDto manifest,
        GroupDto? primaryGroup,
        OpenRunOrchestrationProjection? openRun,
        string communityHubRoute,
        DateTimeOffset now,
        string locale)
    {
        string groupRoute = primaryGroup is null
            ? "/groups"
            : $"/groups/{Uri.EscapeDataString(primaryGroup.GroupId)}";
        string summary = primaryGroup is null
            ? "Community context stays on the signed-in work page even before a reviewed group or table is attached."
            : $"{primaryGroup.Name} keeps group membership, open-run discovery, and community operations on the signed-in work page instead of inventing a public community microsurface.";

        return new HostedBoundedContextCoverageProjection(
            ProjectionId: StableId("hosted-bounded-context-community", primaryGroup?.GroupId ?? openRun?.Listing.OpenRunId ?? manifest.Version),
            SurfaceId: "community_context",
            Route: communityHubRoute,
            ComparisonRoute: groupRoute,
            BoundaryOwner: "accounts_and_community_context",
            DecisionAuthority: "group_membership_and_open_run_access",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                $"{communityHubRoute} is the account community operations anchor.",
                primaryGroup is null
                    ? "No reviewed group is active yet, so /groups remains the safe comparison route."
                    : $"Group {primaryGroup.GroupId} keeps {primaryGroup.Memberships.Count.ToString(CultureInfo.InvariantCulture)} member link(s) on the reviewed group page.",
                openRun is null
                    ? "No open-run listing is active yet, but community operations still stay on the same account page."
                    : $"Open run {openRun.Listing.OpenRunId} still routes through the same account community page."
            ],
            Actions:
            [
                new HostedBoundedContextCoverageActionProjection("open_community_hub", "Open community hub", communityHubRoute, "Inspect the account community operations page."),
                new HostedBoundedContextCoverageActionProjection("open_groups", "Open groups", groupRoute, "Compare community operations against the reviewed group page."),
                new HostedBoundedContextCoverageActionProjection("open_open_runs", "Open open runs", "/account/work#community-ops", "Return to the community page that owns discovery and join status.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: primaryGroup?.GroupId ?? openRun?.Listing.OpenRunId);
    }

    private static HostedBoundedContextCoverageProjection BuildCampaignContext(
        PublicReleaseManifestDto manifest,
        OpenRunOrchestrationProjection? openRun,
        string communityHubRoute,
        DateTimeOffset now,
        string locale)
    {
        string route = openRun is null
            ? "/account/work"
            : $"/account/work/workspaces/{Uri.EscapeDataString(openRun.Listing.WorkspaceId)}";
        string comparisonRoute = openRun is null
            ? communityHubRoute
            : $"/api/v1/campaign-spine/me/open-runs/{Uri.EscapeDataString(openRun.Listing.OpenRunId)}";
        string summary = openRun is null
            ? "Campaign context keeps workspace continuity and run return on the signed-in work page even when no reviewed open run is active."
            : $"{openRun.Listing.ListingTitle} keeps workspace continuity, schedule, meeting details, and closeout status on the reviewed campaign workspace.";

        return new HostedBoundedContextCoverageProjection(
            ProjectionId: StableId("hosted-bounded-context-campaign", openRun?.Listing.WorkspaceId ?? manifest.Version),
            SurfaceId: "campaign_context",
            Route: route,
            ComparisonRoute: comparisonRoute,
            BoundaryOwner: "campaign_spine_context",
            DecisionAuthority: "campaign_workspace_and_open_run_receipts",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                openRun is null
                    ? "No open-run projection is active yet, so the signed-in work page remains the safe campaign return route."
                    : $"Workspace {openRun.Listing.WorkspaceId} and open run {openRun.Listing.OpenRunId} stay linked on the reviewed campaign workspace.",
                openRun?.Schedule?.Summary ?? "Scheduling status stays with the campaign when it appears.",
                openRun?.Closeout?.Summary ?? "Closeout status remains with the campaign instead of drifting into community or support routes."
            ],
            Actions:
            [
                new HostedBoundedContextCoverageActionProjection("open_campaign_workspace", "Open campaign workspace", route, "Inspect the signed-in campaign continuity page."),
                new HostedBoundedContextCoverageActionProjection("open_campaign_open_run", "Open open-run details", comparisonRoute, "Compare the campaign workspace with reviewed open-run details."),
                new HostedBoundedContextCoverageActionProjection("open_community_hub", "Return to community hub", communityHubRoute, "Return to the account community page without leaving the campaign workspace.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: openRun?.Listing.WorkspaceId ?? openRun?.Listing.OpenRunId);
    }

    private static HostedBoundedContextCoverageProjection BuildSupportContext(
        PublicReleaseManifestDto manifest,
        SupportCaseProjection? supportCase,
        DateTimeOffset now,
        string locale)
    {
        string route = supportCase is null
            ? "/account/support"
            : $"/account/support/{Uri.EscapeDataString(supportCase.CaseId)}";
        string summary = supportCase is null
            ? "Support context stays first-party and account-aware even when no support case exists yet."
            : $"{supportCase.Status} support case {supportCase.CaseId} keeps crash, feedback, fix-availability, and reporter followthrough on the account support page.";

        return new HostedBoundedContextCoverageProjection(
            ProjectionId: StableId("hosted-bounded-context-support", supportCase?.CaseId ?? manifest.Version),
            SurfaceId: "support_context",
            Route: route,
            ComparisonRoute: "/contact",
            BoundaryOwner: "control_and_support_context",
            DecisionAuthority: "support_case_and_privacy_bounded_status",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                supportCase is null
                    ? "No support case exists yet, so Contact remains the safe public route."
                    : $"Support case {supportCase.CaseId} currently reports {supportCase.Status} on the account support page.",
                "Support status, crash routing, and reporter followthrough stay first-party and privacy-bounded instead of becoming public folklore.",
                "/contact is the public comparison route when a user needs help before a support case exists."
            ],
            Actions:
            [
                new HostedBoundedContextCoverageActionProjection("open_account_support", "Open account support", route, "Inspect signed-in support status."),
                new HostedBoundedContextCoverageActionProjection("open_contact", "Open contact", "/contact", "Compare account support status with the public contact path."),
                new HostedBoundedContextCoverageActionProjection("open_privacy", "Open privacy", "/privacy", "Inspect the privacy boundary that keeps raw diagnostics out of the wrong context.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: supportCase?.CaseId);
    }

    private static HostedBoundedContextCoverageProjection BuildOrchestrationBoundary(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto? installation,
        DownloadReceiptDto? receipt,
        DateTimeOffset now,
        string locale)
    {
        string summary = installation is null
            ? "Install and orchestration adapters stay boundary-owned: they help downloads, claim, artifact launch, and Fleet release steps without replacing public, account, or campaign status."
            : $"{installation.Platform ?? "desktop"} {installation.Channel} {installation.Version} keeps install claim, release upload, and Fleet release steps as adapter seams rather than standalone product decisions.";

        return new HostedBoundedContextCoverageProjection(
            ProjectionId: StableId("hosted-bounded-context-orchestration", installation?.InstallationId ?? receipt?.ReceiptId ?? manifest.Version),
            SurfaceId: "orchestration_boundary",
            Route: "/downloads/install",
            ComparisonRoute: "/account/access",
            BoundaryOwner: "install_and_orchestration_adapters",
            DecisionAuthority: "install_linking_release_upload_and_fleet_bridge",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: summary,
            EvidenceLines:
            [
                receipt is null
                    ? "No recent download record is active, but the install boundary still routes through first-party downloads and signed-in access."
                    : $"Download record {receipt.ReceiptId} keeps published bytes on the public downloads page while claim followthrough stays signed-in.",
                installation is null
                    ? "No claimed installation is active yet, so orchestration stays a boundary-only seam."
                    : $"Installation {installation.InstallationId} remains visible on /account/access instead of creating a separate orchestration product surface.",
                "Release upload sessions, artifact-factory requests, and Fleet bridge calls stay adapter-owned and may not replace public downloads, account, community, campaign, or support status."
            ],
            Actions:
            [
                new HostedBoundedContextCoverageActionProjection("open_install_entry", "Open install entry", "/downloads/install", "Inspect the first-party install entry route."),
                new HostedBoundedContextCoverageActionProjection("open_account_access", "Open devices & access", "/account/access", "Compare orchestration followthrough with claimed-install status."),
                new HostedBoundedContextCoverageActionProjection("open_downloads", "Open downloads", "/downloads", "Return to the public downloads page.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: installation?.InstallationId ?? receipt?.ReceiptId);
    }

    private static HostedBoundedContextCoverageProjection BuildBoundedContextClosure(
        PublicReleaseManifestDto manifest,
        string communityHubRoute,
        DateTimeOffset now,
        string locale)
    {
        return new HostedBoundedContextCoverageProjection(
            ProjectionId: StableId("hosted-bounded-context-closure", manifest.Version),
            SurfaceId: "bounded_context_closure",
            Route: "/progress",
            ComparisonRoute: communityHubRoute,
            BoundaryOwner: "hub_api_runtime_context",
            DecisionAuthority: "service_collection_bounded_context_registration",
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            ProofStatus: ResolveProofStatus(manifest),
            SupportabilityState: ResolveSupportabilityState(manifest),
            Summary: "Hub keeps hosted context coverage clear only when public, account/community, campaign, support, and orchestration routes stay on separate owned paths with explicit comparison pages.",
            EvidenceLines:
            [
                "AddHubPublicGuideContext owns openly readable landing, downloads, roadmap, progress, and trust content.",
                "AddHubAccountsAndCommunityContext owns signed-in account, group, membership, reward, entitlement, and community lanes.",
                "AddHubCampaignSpineContext owns workspaces, open-run orchestration, creator-publication return lanes, and campaign continuity.",
                "AddHubControlAndSupportContext owns support, crash, feedback, privacy-bounded status, and support followthrough.",
                "AddHubInstallAndOrchestrationAdapters owns install linking, release upload, artifact-factory adapter, and Fleet bridge seams without becoming product decisions."
            ],
            Actions:
            [
                new HostedBoundedContextCoverageActionProjection("open_progress", "Open progress", "/progress", "Inspect the public summary that compares the product areas."),
                new HostedBoundedContextCoverageActionProjection("open_community_hub", "Open community hub", communityHubRoute, "Compare the public summary against the account community page."),
                new HostedBoundedContextCoverageActionProjection("open_account", "Open account", "/account", "Return to the signed-in customer spine when a boundary question needs deeper followthrough.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            SourceId: manifest.Version);
    }

    private static string ResolveProofStatus(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.ProofStatus) ? "unknown" : manifest.ProofStatus;

    private static string ResolveSupportabilityState(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.SupportabilityState) ? "unknown" : manifest.SupportabilityState;

    private static string StableId(string prefix, string? sourceId)
    {
        string effectiveSource = string.IsNullOrWhiteSpace(sourceId) ? "unknown" : sourceId;
        using var sha = SHA256.Create();
        byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes($"{prefix}:{effectiveSource}"));
        return $"{prefix}:{Convert.ToHexString(hash[..8]).ToLowerInvariant()}";
    }
}
