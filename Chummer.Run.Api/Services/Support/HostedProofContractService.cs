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
            ? $"{openRun.Listing.ListingTitle} stays on the reviewed open-run page until schedule, meeting details, and closeout status agree."
            : $"{openRun.Listing.ListingTitle} keeps listing, schedule, meeting details, and closeout status on the reviewed open-run page.";

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
            CloseoutPosture: "Open-run status only graduates when listing, meeting, and closeout records all stay on the same reviewed hub page.",
            Summary: summary,
            EvidenceLines:
            [
                openRun.Listing.TableContractSummary,
                openRun.Schedule?.Summary ?? "A reviewed schedule record still has to land before the meeting details can close the loop.",
                openRun.MeetingHandoff?.Summary ?? "Meeting details are still pending on the reviewed open-run page.",
                openRun.Closeout?.Summary ?? "Closeout status stays pending until WorldTick and player-safe news records exist."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_open_run_detail", "Open open-run detail", route, "Inspect the reviewed listing, join request, schedule, meeting details, and closeout records on the same hub route."),
                new HostedProofContractActionProjection("open_community_ops", "Open community ops", comparisonRoute, "Compare the open-run status against the signed-in community operations page.")
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
            CloseoutPosture: "Shadowcasters stays a horizon brief until the same work graduates onto the live downloads page and account-aware return paths.",
            Summary: $"Shadowcasters remains a public horizon detail while {manifest.Channel} {manifest.Version} stays the live release that keeps the comparison honest.",
            EvidenceLines:
            [
                "/roadmap/shadowcasters-network is the named horizon brief, not the live release.",
                "/roadmap/black-ledger is the adjacent comparison route that keeps the roadmap status honest before promotion.",
                "The live downloads page remains the final comparison anchor when a horizon claims it has shipped."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_shadowcasters_brief", "Open Shadowcasters", "/roadmap/shadowcasters-network", "Read the named horizon brief before comparing it to current release status."),
                new HostedProofContractActionProjection("compare_black_ledger", "Compare Black Ledger", "/roadmap/black-ledger", "Compare the adjacent world-state horizon that already shares the same reviewed roadmap page."),
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
        string summary = "Public signals stay reviewed by product packets that route demand through Participate, roadmap projection, and first-party support instead of promoting feedback directly into product copy.";

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
            CloseoutPosture: "Public signal status only closes when intake, roadmap, and support paths agree on the reviewed next action.",
            Summary: summary,
            EvidenceLines:
            [
                feedback is null
                    ? "Feedback packets are still missing from the reviewed public signal path."
                    : $"{feedback.Route} redirects to {feedback.DestinationRoute} before public copy changes are considered.",
                roadmap is null
                    ? "Roadmap projection status is still missing from the reviewed public signal path."
                    : $"Roadmap comparison stays on {roadmap.DestinationRoute}.",
                support is null
                    ? "Support escalation status is still missing from the reviewed public signal path."
                    : $"Support escalation remains first-party on {support.Route}."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_signal_intake", "Open Participate", route, "Review the intake page that classifies public signal before queue synthesis."),
                new HostedProofContractActionProjection("open_roadmap_projection", "Open roadmap projection", comparisonRoute, "Compare the public signal with the reviewed roadmap projection."),
                new HostedProofContractActionProjection("open_contact", "Open contact", support?.Route ?? "/contact", "Use Contact for private or release-bound issues instead of public comments.")
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
            ? "Community hub status stays on the signed-in work page, where community operations and workspace continuity share the same reviewed account surface."
            : $"Community hub status keeps {context.OpenRun.Listing.ListingTitle} attached to the signed-in work page instead of inventing a separate community microsurface.";

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
            CloseoutPosture: "Community status stays on the signed-in work page so roster moves, open runs, and workspace records remain on one reviewed account path.",
            Summary: summary,
            EvidenceLines:
            [
                $"{context.CommunityHubRoute} is the signed-in community operations anchor.",
                $"{context.CommunityWorkspaceRoute} is the shared workspace comparison route for campaign continuity.",
                context.OpenRun is null
                    ? "Community status remains bound to the same reviewed work page even before an open-run listing is active."
                    : $"{context.OpenRun.Listing.OpenRunId} keeps community discovery and campaign continuity pointed back to the same work page."
            ],
            Actions:
            [
                new HostedProofContractActionProjection("open_community_hub", "Open community hub", context.CommunityHubRoute!, "Inspect the signed-in organizer and roster page."),
                new HostedProofContractActionProjection("open_workspace_return", "Open workspace return", context.CommunityWorkspaceRoute!, "Compare community claims with the reviewed workspace continuity surface.")
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
            CloseoutPosture: "Horizon conversion status only closes when the public brief and the signed-in install continuation still describe the same published bytes.",
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
                new HostedProofContractActionProjection("open_account_access", "Open Devices & access", "/account/access", "Inspect the signed-in account-return and recovery path."),
                new HostedProofContractActionProjection("open_download_dispatch", "Open downloads", "/downloads", "Compare the same published bytes against the public downloads page.")
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
