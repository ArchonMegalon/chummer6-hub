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
            "Public-safe board view over Chummer-owned open run truth, seat posture, and scheduling stance.",
            "/community/open-runs/open_run_board.md",
            "/community/open-runs/open_run_board.json",
            ["Open-run board", "Seat posture", "Scheduling truth"]),
        new(
            "organizer_closeout_posture",
            "Organizer closeout posture",
            "How organizer-owned scheduling, handoff, and closeout rails stay visible without pretending public chat tools own the workflow.",
            "/community/open-runs/organizer_closeout_posture.md",
            "/community/open-runs/organizer_closeout_posture.json",
            ["Organizer path", "Meeting handoff", "Closeout status"]),
        new(
            "moderation_boundary",
            "Moderation boundary",
            "Names the public moderation and appeals boundary so community trust never turns into hidden private scoring.",
            "/community/open-runs/moderation_boundary.md",
            "/community/open-runs/moderation_boundary.json",
            ["Moderation boundary", "Appeals posture", "No hidden scoring"])
    ];

    private static readonly IReadOnlyList<CommunityCreatorDocument> CreatorDocuments =
    [
        new(
            "publication_board",
            "Publication board",
            "Governed publication discovery backed by Chummer-owned publication truth instead of loose external shelves.",
            "/creator/packets/publication_board.md",
            "/creator/packets/publication_board.json",
            ["Governed discovery", "Publication truth", "Public-safe gallery"]),
        new(
            "publication_trust_boundary",
            "Publication trust boundary",
            "Visible trust posture and moderation limits for discoverable creator publications.",
            "/creator/packets/publication_trust_boundary.md",
            "/creator/packets/publication_trust_boundary.json",
            ["Trust posture", "Moderation limits", "No provider-owned truth"]),
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
            "Runner return posture",
            "Public-safe identity posture for runner return, account return, and open-run readiness.",
            "/passport/receipts/runner_return_posture.md",
            "/passport/receipts/runner_return_posture.json",
            ["Runner return", "Install continuity", "Participation posture"]),
        new(
            "cross_table_identity_boundary",
            "Cross-table identity boundary",
            "Explains what Runner Passport can signal publicly without leaking private account state or moderation internals.",
            "/passport/receipts/cross_table_identity_boundary.md",
            "/passport/receipts/cross_table_identity_boundary.json",
            ["Cross-table trust", "Private stays private", "No fake reputation engine"]),
        new(
            "privacy_safe_participation_proof",
            "Privacy-safe participation",
            "Aggregate status that participation identity remains first-party, bounded, and non-surveillant.",
            "/passport/receipts/privacy_safe_participation_proof.md",
            "/passport/receipts/privacy_safe_participation_proof.json",
            ["Aggregate status", "Public-safe counts", "Bounded identity"])
    ];

    private static readonly IReadOnlyList<CommunityCreatorDocument> SignalDeckDocuments =
    [
        new(
            "pressure_posture",
            "Signal Deck pressure posture",
            "Public-safe command-deck posture for governed consequence cues, inbox continuity, and next-step pressure.",
            "/signal-deck/receipts/pressure_posture.md",
            "/signal-deck/receipts/pressure_posture.json",
            ["Command pressure", "Governed cues", "Inbox continuity"]),
        new(
            "command_boundary",
            "Signal Deck command boundary",
            "Explains how Signal Deck stays first-party, bounded, and consequence-backed without turning into private world authority.",
            "/signal-deck/receipts/command_boundary.md",
            "/signal-deck/receipts/command_boundary.json",
            ["Command boundary", "No hidden authority", "First-party only"]),
        new(
            "aftermath_return_loop",
            "Signal Deck aftermath return loop",
            "Shows how command pressure survives through aftermath, Living Newsroom framing, and Runner Passport continuity.",
            "/signal-deck/receipts/aftermath_return_loop.md",
            "/signal-deck/receipts/aftermath_return_loop.json",
            ["Aftermath rail", "Living Newsroom", "Runner continuity"])
    ];

    private static readonly IReadOnlyList<CommunityCreatorDocument> LivingWorldDocuments =
    [
        new(
            "watch_package_posture",
            "Living World watch package posture",
            "Public-safe between-session posture showing how Living Newsroom framing, faction command, and governed continuity stay attached to the same turn.",
            "/living-world/receipts/watch_package_posture.md",
            "/living-world/receipts/watch_package_posture.json",
            ["Watch package", "Between-session loop", "First-party framing"]),
        new(
            "command_followthrough_boundary",
            "Living World command continuity boundary",
            "Explains how living-world engagement stays governed, opt-in, and bounded instead of becoming autonomous world simulation.",
            "/living-world/receipts/command_followthrough_boundary.md",
            "/living-world/receipts/command_followthrough_boundary.json",
            ["Governed continuity", "No autonomous simulation", "Bounded engagement"]),
        new(
            "newsroom_aftermath_loop",
            "Living World newsroom and aftermath loop",
            "Shows how the public-safe bulletin, aftermath rail, and runner continuity stay stitched together across the same turn.",
            "/living-world/receipts/newsroom_aftermath_loop.md",
            "/living-world/receipts/newsroom_aftermath_loop.json",
            ["Living Newsroom", "Aftermath rail", "Runner continuity"])
    ];

    private readonly CommunityStore _communityStore;
    private readonly InstallLinkingStore _installLinkingStore;
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
        lock (_installLinkingStore.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            ClaimedInstallationDto[] activeInstallations = _installLinkingStore.InstallationsById.Values
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
        lock (_installLinkingStore.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            int activeInstallations = _installLinkingStore.InstallationsById.Values.Count(
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
        lock (_installLinkingStore.Gate)
        {
            int activeInstallations = _installLinkingStore.InstallationsById.Values.Count(
                item => string.Equals(item.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase));
            return new LivingWorldPublicSummary(
                ActiveInstallationCount: activeInstallations,
                OpenRunCount: community.OpenRuns.Count,
                ParticipationNotificationCount: _communityStore.ParticipationNotificationReceipts.Count,
                ReturnLoopPublicationCount: creator.ReturnLoopCount,
                LastUpdatedUtc: DateTimeOffset.UtcNow);
        }
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
            "## Current public-safe posture",
            string.Empty,
            $"- Active open runs on the board: {summary.OpenRuns.Count}",
            $"- Quickstart-friendly runs: {summary.QuickstartCount}",
            $"- Pending join requests: {summary.PendingJoinCount}",
            $"- Scheduled runs: {summary.ScheduledCount}",
            $"- Closeouts on record: {summary.CloseoutCount}",
            string.Empty,
            "## Boundary",
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

        lines.Add($"JSON route: {document.JsonRoute}");
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
                    "open_run_schedule_receipts",
                    "meeting_handoff_receipts",
                    "closeout_receipts"
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
                    "Public route explains moderation and appeals posture without exposing private case detail.",
                    "Community trust does not become a hidden reputation engine.",
                    "Signed-in operator rails keep enforcement detail off the public lane."
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
            "## Current governed publication posture",
            string.Empty,
            $"- Discoverable publications: {summary.Publications.Count}",
            $"- Curated live: {summary.CuratedLiveCount}",
            $"- Approval-backed: {summary.ApprovalBackedCount}",
            $"- Publications with campaign return summaries: {summary.ReturnLoopCount}",
            string.Empty,
            "## Boundary",
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

        lines.Add($"JSON route: {document.JsonRoute}");
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
            "## Current public-safe posture",
            string.Empty,
            $"- Active claimed installs: {summary.ActiveInstallationCount}",
            $"- Open runs visible to the public lane: {summary.OpenRunCount}",
            $"- Pending join requests: {summary.PendingJoinCount}",
            $"- Participation receipts on the community spine: {summary.ParticipationNotificationCount}",
            $"- Platforms in claimed-install posture: {(summary.PlatformLabels.Count == 0 ? "none yet" : string.Join(", ", summary.PlatformLabels))}",
            string.Empty,
            "## Boundary",
            string.Empty,
            BuildPassportBoundary(id),
            string.Empty,
            $"JSON route: {document.JsonRoute}"
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
            "## Current first-party posture",
            string.Empty,
            $"- Active claimed installs on the continuity rail: {summary.ActiveInstallationCount}",
            $"- Open runs visible to the shared command rail: {summary.OpenRunCount}",
            $"- Pending join requests waiting on follow-through: {summary.PendingJoinCount}",
            $"- Participation receipts on the first-party spine: {summary.ParticipationNotificationCount}",
            string.Empty,
            "## Boundary",
            string.Empty,
            BuildSignalDeckBoundary(id),
            string.Empty,
            $"JSON route: {document.JsonRoute}"
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
            "## Current first-party posture",
            string.Empty,
            $"- Active claimed installs on the continuity rail: {summary.ActiveInstallationCount}",
            $"- Open runs on the shared turn rail: {summary.OpenRunCount}",
            $"- Participation receipts on the first-party spine: {summary.ParticipationNotificationCount}",
            $"- Creator publications with return-loop summaries: {summary.ReturnLoopPublicationCount}",
            string.Empty,
            "## Boundary",
            string.Empty,
            BuildLivingWorldBoundary(id),
            string.Empty,
            $"JSON route: {document.JsonRoute}"
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
            "open_run_board" => "The public board can show title, seat posture, summary, and scheduling stance. Private roster notes, meeting links, and applicant detail stay signed-in.",
            "organizer_closeout_posture" => "Organizer scheduling, handoff, and closeout truth stays first-party, but account-linked mutations and private meeting access stay off the guest rail.",
            _ => "Moderation posture stays explicit, appeals remain bounded, and no public reputation score is invented from private case handling."
        };

    private static string BuildCreatorBoundary(string id)
        => id switch
        {
            "publication_board" => "Discoverable creator publication truth comes from Chummer-owned publication history, not external service dashboards.",
            "campaign_return_loop" => "Public publication can point at return posture and next safe action without exposing private workspace review detail.",
            _ => "Trust bands and moderation posture stay visible. External service analytics and hidden scoring do not become creator truth."
        };

    private static string BuildPassportBoundary(string id)
        => id switch
        {
            "runner_return_posture" => "Runner Passport can expose aggregate readiness posture and continuity rails without showing private device history or account internals.",
            "cross_table_identity_boundary" => "Cross-table trust stays bounded, explainable, and non-surveillant. It is not a secret ranking engine.",
            _ => "Participation status remains aggregate and first-party. Private moderation, private identity links, and account recovery detail stay signed-in."
        };

    private static string BuildSignalDeckBoundary(string id)
        => id switch
        {
            "pressure_posture" => "Signal Deck can expose governed command pressure and consequence posture on first-party rails, but it does not become automatic world authority or a hidden moderation score.",
            "command_boundary" => "Signal Deck stays bounded to first-party command and continuity. It does not reveal private session transcript detail, moderation internals, or off-platform operator state.",
            _ => "Aftermath return loops can stay attached to Signal Deck posture, Living Newsroom framing, and Runner Passport continuity without leaking private campaign detail."
        };

    private static string BuildLivingWorldBoundary(string id)
        => id switch
        {
            "watch_package_posture" => "Living World can expose the current public-safe watch package and first-party follow-through posture, but it does not claim an autonomous always-on simulation.",
            "command_followthrough_boundary" => "Living World engagement stays reviewed, opt-in, and bounded to Chummer-owned command, aftermath, and continuity paths. It does not mutate world truth outside that loop.",
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
