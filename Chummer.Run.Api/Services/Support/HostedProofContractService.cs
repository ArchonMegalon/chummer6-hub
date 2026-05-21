using System.Security.Cryptography;
using System.Text;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class HostedProofContractService
{
    private readonly PublicReleaseManifestService _releases;

    public HostedProofContractService(PublicReleaseManifestService releases)
    {
        _releases = releases;
    }

    public HostedProofContractBundle Build(HostedProofContractContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        DateTimeOffset now = DateTimeOffset.UtcNow;
        List<HostedProofContractProjection> contracts = [];

        AddIfNotNull(contracts, BuildOpenRunsContract(context, manifest, now));
        AddIfNotNull(contracts, BuildShadowcastersContract(context, manifest, now));
        AddIfNotNull(contracts, BuildPublicSignalContract(context, manifest, now));
        AddIfNotNull(contracts, BuildCommunityHubContract(context, manifest, now));
        AddIfNotNull(contracts, BuildAccountAwareHorizonConversionContract(context, manifest, now));

        return new HostedProofContractBundle(
            BuiltAtUtc: now,
            Contracts: contracts);
    }

    private static HostedProofContractProjection? BuildOpenRunsContract(
        HostedProofContractContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        OpenRunOrchestrationProjection? openRun = context.OpenRun;
        if (openRun is null)
        {
            return null;
        }

        string route = $"/api/v1/campaign-spine/me/open-runs/{Uri.EscapeDataString(openRun.Listing.OpenRunId)}";
        string comparisonRoute = string.IsNullOrWhiteSpace(context.CommunityHubRoute)
            ? "/account/work#community-ops"
            : context.CommunityHubRoute!;
        string summary = openRun.Closeout is null
            ? $"{openRun.Listing.ListingTitle} stays on the governed open-run lane until schedule, handoff, and closeout proof all agree."
            : $"{openRun.Listing.ListingTitle} keeps listing, schedule, meeting-handoff, and closeout proof on the governed open-run lane.";

        return new HostedProofContractProjection(
            ContractId: StableId("hosted-proof-open-runs", openRun.Listing.OpenRunId),
            ContractName: "open_runs_hosted_proof_contract",
            SurfaceId: "open_runs",
            Route: route,
            ComparisonRoute: comparisonRoute,
            Audience: "community_table_joiners",
            ClaimSensitivity: "community_receipt_only",
            Owner: "campaign_spine",
            DecisionAuthority: "open_run_orchestration_receipts",
            CloseoutPosture: "Open-run proof only graduates when listing, meeting, and closeout receipts all stay on the same governed hub lane.",
            Summary: summary,
            EvidenceLines:
            [
                openRun.Listing.TableContractSummary,
                openRun.Schedule?.Summary ?? "A governed schedule receipt still has to land before the meeting-handoff can close the loop.",
                openRun.MeetingHandoff?.Summary ?? "Meeting-handoff proof is still pending on the governed open-run rail.",
                openRun.Closeout?.Summary ?? "Closeout proof stays pending until WorldTick and player-safe news receipts materialize."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_open_run_detail", "Open open-run detail", route, "Inspect the governed listing, join, schedule, handoff, and closeout receipts on the same hub route."),
                new HostedProofContractActionProjection("open_community_ops", "Open community ops", comparisonRoute, "Compare the open-run proof against the signed-in community operations rail.")
            ],
            EmittedAtUtc: now,
            Locale: context.Locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            SourceId: openRun.Listing.OpenRunId);
    }

    private static HostedProofContractProjection BuildShadowcastersContract(
        HostedProofContractContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
        => new(
            ContractId: StableId("hosted-proof-shadowcasters", manifest.Version),
            ContractName: "shadowcasters_horizon_hosted_proof_contract",
            SurfaceId: "shadowcasters",
            Route: "/roadmap/shadowcasters-network",
            ComparisonRoute: "/roadmap/black-ledger",
            Audience: "public_horizon_followers",
            ClaimSensitivity: "projection_only",
            Owner: "public_landing",
            DecisionAuthority: "horizon_detail_review",
            CloseoutPosture: "Shadowcasters stays a horizon brief until the same proof graduates onto the live published shelf and account-aware return lanes.",
            Summary: $"Shadowcasters remains a public horizon detail while {manifest.Channel} {manifest.Version} stays the live shelf that keeps the comparison honest.",
            EvidenceLines:
            [
                "/roadmap/shadowcasters-network is the named horizon brief, not the live shelf.",
                "/roadmap/black-ledger is the adjacent comparison route that keeps the roadmap posture honest before any proof promotion.",
                "The live release shelf remains the final comparison anchor when a horizon claims it has crossed into shipped truth."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_shadowcasters_brief", "Open Shadowcasters", "/roadmap/shadowcasters-network", "Read the named horizon brief before comparing it to live proof."),
                new HostedProofContractActionProjection("compare_black_ledger", "Compare Black Ledger", "/roadmap/black-ledger", "Compare the adjacent world-state horizon that already shares the same governed roadmap rail."),
                new HostedProofContractActionProjection("open_horizons", "Open roadmap browser", "/horizons", "Return to the shared horizons browser instead of inventing a horizon-only side surface.")
            ],
            EmittedAtUtc: now,
            Locale: context.Locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            SourceId: manifest.Version);

    private static HostedProofContractProjection? BuildPublicSignalContract(
        HostedProofContractContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        IReadOnlyList<SignalToCanonPacketProjection>? packets = context.PublicSignals?.Packets;
        if (packets is null || packets.Count == 0)
        {
            return null;
        }

        SignalToCanonPacketProjection? intake = packets.FirstOrDefault(item => string.Equals(item.SurfaceId, "signal_intake", StringComparison.Ordinal));
        SignalToCanonPacketProjection? feedback = packets.FirstOrDefault(item => string.Equals(item.SurfaceId, "feedback", StringComparison.Ordinal));
        SignalToCanonPacketProjection? roadmap = packets.FirstOrDefault(item => string.Equals(item.SurfaceId, "roadmap", StringComparison.Ordinal));
        SignalToCanonPacketProjection? support = packets.FirstOrDefault(item => string.Equals(item.SurfaceId, "support", StringComparison.Ordinal));

        string route = intake?.Route ?? "/participate";
        string comparisonRoute = roadmap?.DestinationRoute ?? "/horizons?source=roadmap#public-roadmap-projection";
        string summary = "Public signal proof stays governed by SignalToCanon packets that route demand through Participate, roadmap projection, and first-party support instead of promoting feedback directly into canon.";

        return new HostedProofContractProjection(
            ContractId: StableId("hosted-proof-public-signal", $"{manifest.Version}:{route}:{comparisonRoute}"),
            ContractName: "public_signal_hosted_proof_contract",
            SurfaceId: "public_signal",
            Route: route,
            ComparisonRoute: comparisonRoute,
            Audience: "public_signal_followers",
            ClaimSensitivity: "classified_signal_only",
            Owner: "product_governor",
            DecisionAuthority: "signal_to_canon_triage",
            CloseoutPosture: "Public signal proof only closes when intake, roadmap, and support lanes agree on the governed next action.",
            Summary: summary,
            EvidenceLines:
            [
                feedback is null
                    ? "Feedback packets are still missing from the governed public signal lane."
                    : $"{feedback.Route} redirects to {feedback.DestinationRoute} before canon changes are considered.",
                roadmap is null
                    ? "Roadmap projection proof is still missing from the governed public signal lane."
                    : $"Roadmap comparison stays on {roadmap.DestinationRoute}.",
                support is null
                    ? "Support escalation proof is still missing from the governed public signal lane."
                    : $"Support escalation remains first-party on {support.Route}."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_signal_intake", "Open Participate", route, "Review the governed intake lane that classifies public signal before queue synthesis."),
                new HostedProofContractActionProjection("open_roadmap_projection", "Open roadmap projection", comparisonRoute, "Compare the public signal with the governed roadmap projection."),
                new HostedProofContractActionProjection("open_support_intake", "Open support intake", support?.Route ?? "/contact", "Escalate private or release-bound issues through first-party support instead of public comments.")
            ],
            EmittedAtUtc: now,
            Locale: context.Locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            SourceId: intake?.PacketId ?? feedback?.PacketId ?? roadmap?.PacketId);
    }

    private static HostedProofContractProjection? BuildCommunityHubContract(
        HostedProofContractContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(context.CommunityHubRoute) || string.IsNullOrWhiteSpace(context.CommunityWorkspaceRoute))
        {
            return null;
        }

        string summary = context.OpenRun is null
            ? "Community hub proof stays on the signed-in work rail, where community ops and workspace continuity share the same governed account surface."
            : $"Community hub proof keeps {context.OpenRun.Listing.ListingTitle} attached to the signed-in work rail instead of inventing a separate community microsurface.";

        return new HostedProofContractProjection(
            ContractId: StableId("hosted-proof-community-hub", $"{context.CommunityHubRoute}:{context.CommunityWorkspaceRoute}"),
            ContractName: "community_hub_hosted_proof_contract",
            SurfaceId: "community_hub",
            Route: context.CommunityHubRoute!,
            ComparisonRoute: context.CommunityWorkspaceRoute!,
            Audience: "community_operators",
            ClaimSensitivity: "signed_in_community",
            Owner: "campaign_spine",
            DecisionAuthority: "community_ops_and_workspace_receipts",
            CloseoutPosture: "Community proof stays on the signed-in work rail so roster moves, open runs, and workspace receipts remain on one governed account path.",
            Summary: summary,
            EvidenceLines:
            [
                $"{context.CommunityHubRoute} is the signed-in community operations anchor.",
                $"{context.CommunityWorkspaceRoute} is the shared workspace comparison route for campaign continuity.",
                context.OpenRun is null
                    ? "Community proof remains bound to the same governed work rail even before an open-run listing is active."
                    : $"{context.OpenRun.Listing.OpenRunId} proves community discovery and campaign continuity still point back to the same work rail."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_community_hub", "Open community hub", context.CommunityHubRoute!, "Inspect the signed-in organizer and roster rail."),
                new HostedProofContractActionProjection("open_workspace_return", "Open workspace return", context.CommunityWorkspaceRoute!, "Compare community claims with the governed workspace continuity surface.")
            ],
            EmittedAtUtc: now,
            Locale: context.Locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            SourceId: context.OpenRun?.Listing.OpenRunId ?? context.CommunityWorkspaceRoute);
    }

    private static HostedProofContractProjection? BuildAccountAwareHorizonConversionContract(
        HostedProofContractContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        ClaimedInstallationDto? installation = context.InstallLinking?.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        DownloadReceiptDto? receipt = context.InstallLinking?.RecentReceipts?
            .OrderByDescending(static item => item.IssuedAtUtc)
            .FirstOrDefault();
        if (installation is null && receipt is null)
        {
            return null;
        }

        string summary = installation is not null
            ? $"{installation.Platform ?? "desktop"} {installation.Channel} {installation.Version} can move from a public horizon brief to account-aware install follow-through without changing the published build bytes."
            : $"Receipt {receipt!.ReceiptId} keeps the public horizon open while the next linked install follow-through stays on first-party access routes.";

        return new HostedProofContractProjection(
            ContractId: StableId("hosted-proof-account-aware-horizon", installation?.InstallationId ?? receipt!.ReceiptId),
            ContractName: "account_aware_horizon_conversion_hosted_proof_contract",
            SurfaceId: "account_aware_horizon_conversion",
            Route: "/roadmap/shadowcasters-network",
            ComparisonRoute: "/account/access",
            Audience: "signed_in_horizon_followers",
            ClaimSensitivity: "account_aware_continuation",
            Owner: "public_landing_and_install_linking",
            DecisionAuthority: "install_linking_and_horizon_review",
            CloseoutPosture: "Horizon conversion proof only closes when the public brief and the signed-in install continuation still describe the same published bytes.",
            Summary: summary,
            EvidenceLines:
            [
                "/roadmap/shadowcasters-network stays openly readable as the honest horizon brief.",
                "/account/access is the account-aware follow-through route when install recovery, support, or claim continuity must stay linked.",
                "The published packages stay the same; only the short-lived setup assistant and install claim become account-aware."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_shadowcasters_route", "Open Shadowcasters", "/roadmap/shadowcasters-network", "Review the public horizon brief before stepping into account-aware follow-through."),
                new HostedProofContractActionProjection("open_account_access", "Open Devices & access", "/account/access", "Inspect the signed-in install continuity and recovery path."),
                new HostedProofContractActionProjection("open_download_dispatch", "Open downloads", "/downloads", "Compare the same published bytes against the open public release shelf.")
            ],
            EmittedAtUtc: now,
            Locale: context.Locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            SourceId: installation?.InstallationId ?? receipt!.ReceiptId);
    }

    private static void AddIfNotNull(
        ICollection<HostedProofContractProjection> contracts,
        HostedProofContractProjection? contract)
    {
        if (contract is not null)
        {
            contracts.Add(contract);
        }
    }

    private static string StableId(string prefix, string seed)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes($"{prefix}:{seed}"));
        return $"{prefix}:{Convert.ToHexString(digest[..8]).ToLowerInvariant()}";
    }
}
