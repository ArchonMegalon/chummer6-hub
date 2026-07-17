using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;

namespace Chummer.Run.Api.Services;

public sealed class CommunityCreatorHorizonsService
{
    private static readonly IReadOnlyList<CommunityCreatorDocument> CommunityDocuments =
    [
        new(
            "open_run_board",
            "Open run board",
            "A simple public board for open runs, seats, and scheduling.",
            "/community/open-runs/open_run_board.md",
            "/community/open-runs/open_run_board.json",
            ["Open-run board", "Seats", "Scheduling"]),
        new(
            "organizer_closeout_posture",
            "Organizer closeout",
            "How scheduling, meeting details, and closeout stay clear without exposing private table details.",
            "/community/open-runs/organizer_closeout_posture.md",
            "/community/open-runs/organizer_closeout_posture.json",
            ["Organizer path", "Meeting details", "Closeout status"]),
        new(
            "moderation_boundary",
            "Moderation rules",
            "What can be shown publicly, what stays private, and why there is no hidden score.",
            "/community/open-runs/moderation_boundary.md",
            "/community/open-runs/moderation_boundary.json",
            ["Moderation", "Appeals", "No hidden scoring"])
    ];

    private static readonly IReadOnlyList<CommunityCreatorDocument> CreatorDocuments =
    [
        new(
            "publication_board",
            "Publication board",
            "Shared work people can browse from Chummer instead of chasing links across outside services.",
            "/creator/packets/publication_board.md",
            "/creator/packets/publication_board.json",
            ["Shared work", "Publication history", "Gallery"]),
        new(
            "publication_trust_boundary",
            "Publication safety",
            "Clear status and moderation notes for discoverable creator publications.",
            "/creator/packets/publication_trust_boundary.md",
            "/creator/packets/publication_trust_boundary.json",
            ["Status", "Moderation", "No hidden scoring"]),
        new(
            "campaign_return_loop",
            "Campaign return loop",
            "Shows how public creator output returns to campaign use instead of becoming dead gallery inventory.",
            "/creator/packets/campaign_return_loop.md",
            "/creator/packets/campaign_return_loop.json",
            ["Campaign return", "File history", "Update follow-through"])
    ];

    private static readonly IReadOnlyList<CommunityCreatorDocument> PassportDocuments =
    [
        new(
            "runner_return_posture",
            "Runner return",
            "How Chummer shows return, account access, and open-run readiness without exposing private account details.",
            "/passport/receipts/runner_return_posture.md",
            "/passport/receipts/runner_return_posture.json",
            ["Runner return", "Linked installs", "Participation"]),
        new(
            "cross_table_identity_boundary",
            "Cross-table identity",
            "Explains what Runner Passport can signal publicly without leaking private account state or moderation internals.",
            "/passport/receipts/cross_table_identity_boundary.md",
            "/passport/receipts/cross_table_identity_boundary.json",
            ["Cross-table trust", "Private stays private", "No fake reputation engine"]),
        new(
            "privacy_safe_participation_proof",
            "Privacy-safe participation",
            "Aggregate participation status without private identity links or surveillance-style scoring.",
            "/passport/receipts/privacy_safe_participation_proof.md",
            "/passport/receipts/privacy_safe_participation_proof.json",
            ["Aggregate status", "Public counts", "Private identity"])
    ];

    private static readonly IReadOnlyList<CommunityCreatorDocument> SignalDeckDocuments =
    [
        new(
            "pressure_posture",
            "Signal Deck pressure",
            "Consequence cues, inbox follow-up, and next steps without turning the campaign into a public scoreboard.",
            "/signal-deck/receipts/pressure_posture.md",
            "/signal-deck/receipts/pressure_posture.json",
            ["Command pressure", "Cues", "Inbox"]),
        new(
            "command_boundary",
            "Signal Deck limits",
            "What Signal Deck can show without revealing private session notes or inventing authority.",
            "/signal-deck/receipts/command_boundary.md",
            "/signal-deck/receipts/command_boundary.json",
            ["Command limits", "No hidden authority", "Private stays private"]),
        new(
            "aftermath_return_loop",
            "Signal Deck aftermath return loop",
            "Shows how command pressure survives through aftermath, Living Newsroom framing, and Runner Passport continuity.",
            "/signal-deck/receipts/aftermath_return_loop.md",
            "/signal-deck/receipts/aftermath_return_loop.json",
            ["Aftermath", "Living Newsroom", "Runner continuity"])
    ];

    private static readonly IReadOnlyList<CommunityCreatorDocument> LivingWorldDocuments =
    [
        new(
            "watch_package_posture",
            "Living World watchlist",
            "Between-session updates from the newsroom, factions, and the current turn.",
            "/living-world/receipts/watch_package_posture.md",
            "/living-world/receipts/watch_package_posture.json",
            ["Watchlist", "Between-session loop", "Current turn"]),
        new(
            "command_followthrough_boundary",
            "Living World command continuity",
            "Explains how living-world engagement stays opt-in and reviewable instead of becoming an automatic simulation.",
            "/living-world/receipts/command_followthrough_boundary.md",
            "/living-world/receipts/command_followthrough_boundary.json",
            ["Reviewed continuity", "No autonomous simulation", "Opt-in"]),
        new(
            "newsroom_aftermath_loop",
            "Living World newsroom and aftermath loop",
            "Shows how the bulletin, aftermath, and runner continuity stay connected across the same turn.",
            "/living-world/receipts/newsroom_aftermath_loop.md",
            "/living-world/receipts/newsroom_aftermath_loop.json",
            ["Living Newsroom", "Aftermath", "Runner continuity"])
    ];

    private readonly CommunityStore _communityStore;
    private readonly InstallLinkingStore? _installLinkingStore;
    private readonly InstallLinkingStoreAccess? _installLinkingStoreAccess;
    private readonly PublicCreatorPublicationDiscoveryService _publicCreatorDiscovery;

    public CommunityCreatorHorizonsService(
        CommunityStore communityStore,
        InstallLinkingStore installLinkingStore,
        PublicCreatorPublicationDiscoveryService publicCreatorDiscovery)
    {
        _communityStore = communityStore;
        _installLinkingStore = installLinkingStore;
        _publicCreatorDiscovery = publicCreatorDiscovery;
    }

    public CommunityCreatorHorizonsService(
        CommunityStore communityStore,
        InstallLinkingStoreAccess installLinkingStoreAccess,
        PublicCreatorPublicationDiscoveryService publicCreatorDiscovery)
    {
        _communityStore = communityStore;
        _installLinkingStoreAccess = installLinkingStoreAccess
            ?? throw new ArgumentNullException(nameof(installLinkingStoreAccess));
        _publicCreatorDiscovery = publicCreatorDiscovery;
    }

    public IReadOnlyList<CommunityCreatorDocument> ListCommunityDocuments() => CommunityDocuments;
    public IReadOnlyList<CommunityCreatorDocument> ListCreatorDocuments() => CreatorDocuments;
    public IReadOnlyList<CommunityCreatorDocument> ListPassportDocuments() => PassportDocuments;
    public IReadOnlyList<CommunityCreatorDocument> ListSignalDeckDocuments() => SignalDeckDocuments;
    public IReadOnlyList<CommunityCreatorDocument> ListLivingWorldDocuments() => LivingWorldDocuments;

    public CommunityCreatorDocument GetCommunityDocument(string id) => GetById(CommunityDocuments, id, "community packet");
    public CommunityCreatorDocument GetCreatorDocument(string id) => GetById(CreatorDocuments, id, "creator packet");
    public CommunityCreatorDocument GetPassportDocument(string id) => GetById(PassportDocuments, id, "passport receipt");
    public CommunityCreatorDocument GetSignalDeckDocument(string id) => GetById(SignalDeckDocuments, id, "signal deck receipt");
    public CommunityCreatorDocument GetLivingWorldDocument(string id) => GetById(LivingWorldDocuments, id, "living world receipt");

    public CommunityHubPublicSummary BuildCommunitySummary()
    {
        lock (_communityStore.Gate)
        {
            OpenRunListingProjection[] openRuns = _communityStore.OpenRuns
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Take(6)
                .ToArray();
            int quickstartCount = openRuns.Count(static item => item.QuickstartAllowed);
            int pendingJoinCount = _communityStore.OpenRunJoinRequests.Count(static item => string.Equals(item.Status, "pending", StringComparison.OrdinalIgnoreCase));
            int scheduledCount = _communityStore.OpenRunSchedules.Count;
            int closeoutCount = _communityStore.OpenRunCloseouts.Count;
            return new CommunityHubPublicSummary(openRuns, quickstartCount, pendingJoinCount, scheduledCount, closeoutCount);
        }
    }

    public CreatorOsPublicSummary BuildCreatorSummary()
    {
        IReadOnlyList<CreatorPublicationProjection> publications = _publicCreatorDiscovery.ListDiscoverable(limit: 12);
        int curatedLiveCount = publications.Count(item => string.Equals(item.TrustBand, "curated-live", StringComparison.OrdinalIgnoreCase));
        int approvalBackedCount = publications.Count(item => string.Equals(item.TrustBand, "approval-backed", StringComparison.OrdinalIgnoreCase));
        int returnLoopCount = publications.Count(item => !string.IsNullOrWhiteSpace(item.CampaignReturnSummary));
        return new CreatorOsPublicSummary(publications, curatedLiveCount, approvalBackedCount, returnLoopCount);
    }

    public RunnerPassportPublicSummary BuildPassportSummary()
    {
        CommunityHubPublicSummary community = BuildCommunitySummary();
        if (!TryGetInstallLinkingStore(out InstallLinkingStore installLinkingStore))
        {
            return new RunnerPassportPublicSummary(
                0,
                [],
                community.OpenRuns.Count,
                community.PendingJoinCount,
                _communityStore.ParticipationNotificationReceipts.Count,
                DateTimeOffset.UtcNow);
        }

        lock (installLinkingStore.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            ClaimedInstallationDto[] activeInstallations = installLinkingStore.InstallationsById.Values
                .Where(item => string.Equals(item.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            string[] platformLabels = activeInstallations
                .Select(item => string.IsNullOrWhiteSpace(item.Platform) ? "unknown" : item.Platform.Trim().ToLowerInvariant())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(static item => item, StringComparer.OrdinalIgnoreCase)
                .Take(6)
                .ToArray();

            return new RunnerPassportPublicSummary(
                ActiveInstallationCount: activeInstallations.Length,
                PlatformLabels: platformLabels,
                OpenRunCount: community.OpenRuns.Count,
                PendingJoinCount: community.PendingJoinCount,
                ParticipationNotificationCount: _communityStore.ParticipationNotificationReceipts.Count,
                LastUpdatedUtc: activeInstallations.FirstOrDefault()?.UpdatedAtUtc ?? now);
        }
    }

    public SignalDeckPublicSummary BuildSignalDeckSummary()
    {
        CommunityHubPublicSummary community = BuildCommunitySummary();
        if (!TryGetInstallLinkingStore(out InstallLinkingStore installLinkingStore))
        {
            return new SignalDeckPublicSummary(
                0,
                community.OpenRuns.Count,
                community.PendingJoinCount,
                _communityStore.ParticipationNotificationReceipts.Count,
                DateTimeOffset.UtcNow);
        }

        lock (installLinkingStore.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            int activeInstallations = installLinkingStore.InstallationsById.Values.Count(
                item => string.Equals(item.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase));
            return new SignalDeckPublicSummary(
                ActiveInstallationCount: activeInstallations,
                OpenRunCount: community.OpenRuns.Count,
                PendingJoinCount: community.PendingJoinCount,
                ParticipationNotificationCount: _communityStore.ParticipationNotificationReceipts.Count,
                LastUpdatedUtc: now);
        }
    }

    public LivingWorldPublicSummary BuildLivingWorldSummary()
    {
        CommunityHubPublicSummary community = BuildCommunitySummary();
        CreatorOsPublicSummary creator = BuildCreatorSummary();
        if (!TryGetInstallLinkingStore(out InstallLinkingStore installLinkingStore))
        {
            return new LivingWorldPublicSummary(
                0,
                community.OpenRuns.Count,
                _communityStore.ParticipationNotificationReceipts.Count,
                creator.ReturnLoopCount,
                DateTimeOffset.UtcNow);
        }

        lock (installLinkingStore.Gate)
        {
            int activeInstallations = installLinkingStore.InstallationsById.Values.Count(
                item => string.Equals(item.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase));
            return new LivingWorldPublicSummary(
                ActiveInstallationCount: activeInstallations,
                OpenRunCount: community.OpenRuns.Count,
                ParticipationNotificationCount: _communityStore.ParticipationNotificationReceipts.Count,
                ReturnLoopPublicationCount: creator.ReturnLoopCount,
                LastUpdatedUtc: DateTimeOffset.UtcNow);
        }
    }

    private bool TryGetInstallLinkingStore(out InstallLinkingStore store)
    {
        if (_installLinkingStore is not null)
        {
            store = _installLinkingStore;
            return true;
        }

        return _installLinkingStoreAccess!.TryGet(out store);
    }

    public string BuildCommunityMarkdown(string id)
    {
        CommunityCreatorDocument document = GetCommunityDocument(id);
        CommunityHubPublicSummary summary = BuildCommunitySummary();
        List<string> lines =
        [
            $"# {document.Label}",
            string.Empty,
            document.Summary,
            string.Empty,
            "## What is visible now",
            string.Empty,
            $"- Active open runs on the board: {summary.OpenRuns.Count}",
            $"- Quickstart-friendly runs: {summary.QuickstartCount}",
            $"- Pending join requests: {summary.PendingJoinCount}",
            $"- Scheduled runs: {summary.ScheduledCount}",
            $"- Closeouts on record: {summary.CloseoutCount}",
            string.Empty,
            "## Privacy and limits",
            string.Empty,
            BuildCommunityBoundary(id),
            string.Empty
        ];

        if (string.Equals(id, "open_run_board", StringComparison.OrdinalIgnoreCase) && summary.OpenRuns.Count > 0)
        {
            lines.Add("## Board sample");
            lines.Add(string.Empty);
            lines.AddRange(summary.OpenRuns.Select(item => $"- {item.ListingTitle}: {item.Status} | {item.SchedulingPosture} | quickstart {(item.QuickstartAllowed ? "yes" : "no")}"));
            lines.Add(string.Empty);
        }

        return string.Join('\n', lines) + "\n";
    }

    public string BuildCommunityJson(string id)
    {
        CommunityCreatorDocument document = GetCommunityDocument(id);
        CommunityHubPublicSummary summary = BuildCommunitySummary();
        object payload = id switch
        {
            "open_run_board" => new
            {
                document.Id,
                document.Label,
                document.Summary,
                status = "live",
                open_runs = summary.OpenRuns.Select(item => new
                {
                    item.OpenRunId,
                    item.ListingTitle,
                    item.Status,
                    item.Summary,
                    item.TableContractSummary,
                    item.SchedulingPosture,
                    item.QuickstartAllowed,
                    evidence_lines = item.EvidenceLines
                }).ToArray(),
                counts = BuildCommunityCounts(summary),
                boundary = BuildCommunityBoundary(id),
                generated_at_utc = DateTimeOffset.UtcNow
            },
            "organizer_closeout_posture" => new
            {
                document.Id,
                document.Label,
                document.Summary,
                status = "live",
                counts = BuildCommunityCounts(summary),
                organizer_factors = new[]
                {
                    "open_run_schedules",
                    "meeting_handoffs",
                    "closeouts"
                },
                boundary = BuildCommunityBoundary(id),
                generated_at_utc = DateTimeOffset.UtcNow
            },
            _ => new
            {
                document.Id,
                document.Label,
                document.Summary,
                status = "live",
                moderation_boundary = new[]
                {
                    "The public page explains moderation and appeals without exposing private cases.",
                    "Community trust does not become a hidden reputation engine.",
                    "Signed-in pages keep enforcement detail private."
                },
                counts = BuildCommunityCounts(summary),
                generated_at_utc = DateTimeOffset.UtcNow
            }
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildCreatorMarkdown(string id)
    {
        CommunityCreatorDocument document = GetCreatorDocument(id);
        CreatorOsPublicSummary summary = BuildCreatorSummary();
        List<string> lines =
        [
            $"# {document.Label}",
            string.Empty,
            document.Summary,
            string.Empty,
            "## What is visible now",
            string.Empty,
            $"- Discoverable publications: {summary.Publications.Count}",
            $"- Curated live: {summary.CuratedLiveCount}",
            $"- Approval-backed: {summary.ApprovalBackedCount}",
            $"- Publications with campaign return summaries: {summary.ReturnLoopCount}",
            string.Empty,
            "## Privacy and limits",
            string.Empty,
            BuildCreatorBoundary(id),
            string.Empty
        ];

        if (summary.Publications.Count > 0)
        {
            lines.Add("## Current examples");
            lines.Add(string.Empty);
            lines.AddRange(summary.Publications.Take(4).Select(item => $"- {item.Title}: {item.PublicationStatus} | {item.TrustBand ?? "unknown trust"} | {item.DiscoverySummary}"));
            lines.Add(string.Empty);
        }

        return string.Join('\n', lines) + "\n";
    }

    public string BuildCreatorJson(string id)
    {
        CommunityCreatorDocument document = GetCreatorDocument(id);
        CreatorOsPublicSummary summary = BuildCreatorSummary();
        object payload = id switch
        {
            "publication_board" => new
            {
                document.Id,
                document.Label,
                document.Summary,
                status = "live",
                counts = new
                {
                    discoverable_publications = summary.Publications.Count,
                    summary.CuratedLiveCount,
                    summary.ApprovalBackedCount
                },
                publications = summary.Publications.Select(item => new
                {
                    item.PublicationId,
                    item.Title,
                    item.Kind,
                    item.PublicationStatus,
                    item.TrustBand,
                    item.DiscoverySummary,
                    item.ProvenanceSummary
                }).ToArray(),
                boundary = BuildCreatorBoundary(id),
                generated_at_utc = DateTimeOffset.UtcNow
            },
            "campaign_return_loop" => new
            {
                document.Id,
                document.Label,
                document.Summary,
                status = "live",
                return_loop = summary.Publications
                    .Where(item => !string.IsNullOrWhiteSpace(item.CampaignReturnSummary) || !string.IsNullOrWhiteSpace(item.SupportClosureSummary))
                    .Select(item => new
                    {
                        item.PublicationId,
                        item.Title,
                        item.CampaignReturnSummary,
                        item.SupportClosureSummary,
                        item.NextSafeAction
                    }).ToArray(),
                counts = new
                {
                    publications = summary.Publications.Count,
                    return_loop = summary.ReturnLoopCount
                },
                boundary = BuildCreatorBoundary(id),
                generated_at_utc = DateTimeOffset.UtcNow
            },
            _ => new
            {
                document.Id,
                document.Label,
                document.Summary,
                status = "live",
                trust_bands = summary.Publications
                    .GroupBy(item => string.IsNullOrWhiteSpace(item.TrustBand) ? "unknown" : item.TrustBand!, StringComparer.OrdinalIgnoreCase)
                    .Select(group => new { trust_band = group.Key, count = group.Count() })
                    .OrderByDescending(item => item.count)
                    .ToArray(),
                boundary = BuildCreatorBoundary(id),
                generated_at_utc = DateTimeOffset.UtcNow
            }
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildPassportMarkdown(string id)
    {
        CommunityCreatorDocument document = GetPassportDocument(id);
        RunnerPassportPublicSummary summary = BuildPassportSummary();
        List<string> lines =
        [
            $"# {document.Label}",
            string.Empty,
            document.Summary,
            string.Empty,
            "## What is visible now",
            string.Empty,
            $"- Linked installs: {summary.ActiveInstallationCount}",
            $"- Open runs visible publicly: {summary.OpenRunCount}",
            $"- Pending join requests: {summary.PendingJoinCount}",
            $"- Participation events: {summary.ParticipationNotificationCount}",
            $"- Linked platforms: {(summary.PlatformLabels.Count == 0 ? "none yet" : string.Join(", ", summary.PlatformLabels))}",
            string.Empty,
            "## Privacy and limits",
            string.Empty,
            BuildPassportBoundary(id)
        ];
        return string.Join('\n', lines) + "\n";
    }

    public string BuildPassportJson(string id)
    {
        CommunityCreatorDocument document = GetPassportDocument(id);
        RunnerPassportPublicSummary summary = BuildPassportSummary();
        object payload = new
        {
            document.Id,
            document.Label,
            document.Summary,
            status = "live",
            proof_kind = "runner_passport_public_safe_receipt",
            counts = new
            {
                summary.ActiveInstallationCount,
                summary.OpenRunCount,
                summary.PendingJoinCount,
                summary.ParticipationNotificationCount
            },
            platform_labels = summary.PlatformLabels,
            boundary = BuildPassportBoundary(id),
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildSignalDeckMarkdown(string id)
    {
        CommunityCreatorDocument document = GetSignalDeckDocument(id);
        SignalDeckPublicSummary summary = BuildSignalDeckSummary();
        List<string> lines =
        [
            $"# {document.Label}",
            string.Empty,
            document.Summary,
            string.Empty,
            "## What is visible now",
            string.Empty,
            $"- Linked installs: {summary.ActiveInstallationCount}",
            $"- Open runs visible publicly: {summary.OpenRunCount}",
            $"- Pending join requests: {summary.PendingJoinCount}",
            $"- Participation events: {summary.ParticipationNotificationCount}",
            string.Empty,
            "## Privacy and limits",
            string.Empty,
            BuildSignalDeckBoundary(id)
        ];
        return string.Join('\n', lines) + "\n";
    }

    public string BuildSignalDeckJson(string id)
    {
        CommunityCreatorDocument document = GetSignalDeckDocument(id);
        SignalDeckPublicSummary summary = BuildSignalDeckSummary();
        object payload = new
        {
            document.Id,
            document.Label,
            document.Summary,
            status = "live",
            proof_kind = "signal_deck_public_safe_receipt",
            counts = new
            {
                summary.ActiveInstallationCount,
                summary.OpenRunCount,
                summary.PendingJoinCount,
                summary.ParticipationNotificationCount
            },
            boundary = BuildSignalDeckBoundary(id),
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildLivingWorldMarkdown(string id)
    {
        CommunityCreatorDocument document = GetLivingWorldDocument(id);
        LivingWorldPublicSummary summary = BuildLivingWorldSummary();
        List<string> lines =
        [
            $"# {document.Label}",
            string.Empty,
            document.Summary,
            string.Empty,
            "## What is visible now",
            string.Empty,
            $"- Linked installs: {summary.ActiveInstallationCount}",
            $"- Open runs visible publicly: {summary.OpenRunCount}",
            $"- Participation events: {summary.ParticipationNotificationCount}",
            $"- Creator publications with return-loop summaries: {summary.ReturnLoopPublicationCount}",
            string.Empty,
            "## Privacy and limits",
            string.Empty,
            BuildLivingWorldBoundary(id)
        ];
        return string.Join('\n', lines) + "\n";
    }

    public string BuildLivingWorldJson(string id)
    {
        CommunityCreatorDocument document = GetLivingWorldDocument(id);
        LivingWorldPublicSummary summary = BuildLivingWorldSummary();
        object payload = new
        {
            document.Id,
            document.Label,
            document.Summary,
            status = "live",
            proof_kind = "living_world_public_safe_receipt",
            counts = new
            {
                summary.ActiveInstallationCount,
                summary.OpenRunCount,
                summary.ParticipationNotificationCount,
                summary.ReturnLoopPublicationCount
            },
            boundary = BuildLivingWorldBoundary(id),
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    private static CommunityCreatorDocument GetById(IReadOnlyList<CommunityCreatorDocument> documents, string id, string label)
        => documents.FirstOrDefault(item => string.Equals(item.Id, id?.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown {label} '{id}'.");

    private static object BuildCommunityCounts(CommunityHubPublicSummary summary)
        => new
        {
            open_runs = summary.OpenRuns.Count,
            quickstart_runs = summary.QuickstartCount,
            pending_join_requests = summary.PendingJoinCount,
            scheduled_runs = summary.ScheduledCount,
            closeouts = summary.CloseoutCount
        };

    private static string BuildCommunityBoundary(string id)
        => id switch
        {
            "open_run_board" => "The public board can show title, seats, summary, and scheduling. Private roster notes, meeting links, and applicant detail stay signed-in.",
            "organizer_closeout_posture" => "Scheduling, meeting details, and closeout status stay in Chummer, but private meeting access stays signed-in.",
            _ => "Moderation rules and appeals stay visible. Private case handling never becomes a public reputation score."
        };

    private static string BuildCreatorBoundary(string id)
        => id switch
        {
            "publication_board" => "Discoverable creator publications use Chummer publication history, not outside dashboards.",
            "campaign_return_loop" => "Publications can show the next useful action without exposing private workspace review detail.",
            _ => "Status and moderation notes stay visible. External analytics and hidden scoring do not drive creator discovery."
        };

    private static string BuildPassportBoundary(string id)
        => id switch
        {
            "runner_return_posture" => "Runner Passport can show aggregate readiness and return paths without showing private device history or account internals.",
            "cross_table_identity_boundary" => "Cross-table trust stays explainable and non-surveillant. It is not a secret ranking engine.",
            _ => "Participation status is shown only as totals. Private moderation, identity links, and account recovery detail stay signed-in."
        };

    private static string BuildSignalDeckBoundary(string id)
        => id switch
        {
            "pressure_posture" => "Signal Deck can show command pressure and consequences, but it does not become an automatic world engine or a hidden moderation score.",
            "command_boundary" => "Signal Deck does not reveal private session transcripts, moderation details, or off-platform state.",
            _ => "Aftermath can stay connected to Signal Deck, Living Newsroom, and Runner Passport without leaking private campaign detail."
        };

    private static string BuildLivingWorldBoundary(string id)
        => id switch
        {
            "watch_package_posture" => "Living World can show the current public watchlist, but it does not promise an autonomous always-on simulation.",
            "command_followthrough_boundary" => "Living World engagement stays reviewed and opt-in. It does not change the campaign outside that loop.",
            _ => "Living Newsroom framing, aftermath, and runner continuity can stay on the same turn loop without exposing private campaign detail or pretending off-table fiction is authoritative by itself."
        };
}

public sealed record CommunityCreatorDocument(
    string Id,
    string Label,
    string Summary,
    string MarkdownRoute,
    string JsonRoute,
    IReadOnlyList<string> Highlights);

public sealed record CommunityHubPublicSummary(
    IReadOnlyList<OpenRunListingProjection> OpenRuns,
    int QuickstartCount,
    int PendingJoinCount,
    int ScheduledCount,
    int CloseoutCount);

public sealed record CreatorOsPublicSummary(
    IReadOnlyList<CreatorPublicationProjection> Publications,
    int CuratedLiveCount,
    int ApprovalBackedCount,
    int ReturnLoopCount);

public sealed record RunnerPassportPublicSummary(
    int ActiveInstallationCount,
    IReadOnlyList<string> PlatformLabels,
    int OpenRunCount,
    int PendingJoinCount,
    int ParticipationNotificationCount,
    DateTimeOffset LastUpdatedUtc);

public sealed record SignalDeckPublicSummary(
    int ActiveInstallationCount,
    int OpenRunCount,
    int PendingJoinCount,
    int ParticipationNotificationCount,
    DateTimeOffset LastUpdatedUtc);

public sealed record LivingWorldPublicSummary(
    int ActiveInstallationCount,
    int OpenRunCount,
    int ParticipationNotificationCount,
    int ReturnLoopPublicationCount,
    DateTimeOffset LastUpdatedUtc);
