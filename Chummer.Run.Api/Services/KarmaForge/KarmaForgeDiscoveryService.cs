using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Contracts;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.KarmaForge;

public sealed class KarmaForgeDiscoveryService
{
    private const string KarmaForgeJourneyKey = "karma_forge_discovery";
    private const string FacePopPublicInvitePathConfigKey = "CHUMMER_KARMA_FORGE_FACEPOP_PUBLIC_INVITE_PATH";
    private const string DeftformBaseUrlConfigKey = "CHUMMER_KARMA_FORGE_DEFTFORM_BASE_URL";
    private const string IcanpreneurBaseUrlConfigKey = "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL";
    private const string MetaSurveyBaseUrlConfigKey = "CHUMMER_KARMA_FORGE_METASURVEY_BASE_URL";
    private const string LunacalBaseUrlConfigKey = "CHUMMER_KARMA_FORGE_LUNACAL_BASE_URL";
    private static readonly KarmaForgeTrackDefinition[] TrackDefinitions =
    [
        new KarmaForgeTrackDefinition(
            Key: "gm_house_rule_track",
            Title: "GM house-rule track",
            Family: "gm_house_rule",
            Questions:
            [
                "What rule does your table change most often?",
                "Why does the default behavior not work?",
                "Who needs to see the change before play?",
                "Does it affect legality, cost, availability, dice pools, advancement, display text, or only GM guidance?",
                "Does it apply to one character, one campaign, one scene, one district, or all your games?",
                "Should players be blocked, warned, or simply informed?",
                "What should happen when the rule changes mid-campaign?",
                "How do you currently enforce it?",
                "Would you share it as a reusable package?"
            ]),
        new KarmaForgeTrackDefinition(
            Key: "player_trust_track",
            Title: "Player trust track",
            Family: "player_trust",
            Questions:
            [
                "What house rules have surprised or frustrated you?",
                "What do you want Chummer to show before you join a campaign?",
                "Would you accept a campaign rule change if Chummer showed a before/after build impact?",
                "What would make a custom rule feel unsafe?",
                "Do you need rollback, comparison, explanation, or approval?"
            ]),
        new KarmaForgeTrackDefinition(
            Key: "creator_publisher_track",
            Title: "Creator / publisher track",
            Family: "creator_publisher",
            Questions:
            [
                "What rule variant would you publish for other tables?",
                "What compatibility labels would you need?",
                "How would you version it?",
                "What would make you confident other GMs can use it?",
                "Should Chummer provide preview builds, example runners, or test cases?"
            ]),
        new KarmaForgeTrackDefinition(
            Key: "organizer_black_ledger_track",
            Title: "Organizer / BLACK LEDGER track",
            Family: "organizer_black_ledger",
            Questions:
            [
                "Do you need season-wide rule environments?",
                "Should faction projects unlock availability or threats?",
                "How should players see world-linked rewards?",
                "Should unlocks be temporary, campaign-scoped, or reusable packs?",
                "What prevents faction mechanics from feeling unfair?"
            ]),
        new KarmaForgeTrackDefinition(
            Key: "chummer5a_veteran_migration_track",
            Title: "Chummer5a veteran / migration track",
            Family: "veteran_migration",
            Questions:
            [
                "What custom data or amend behavior do you rely on today?",
                "Which files or package types matter most?",
                "What breaks most often?",
                "What must Chummer6 preserve?",
                "What legacy behavior should Chummer6 intentionally not preserve?"
            ])
    ];

    private static readonly IReadOnlyDictionary<string, string> CandidateDecisionMeaningsMap =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["reject"] = "Not aligned with Chummer scope or trust model.",
            ["document_only"] = "Needs guidance or help text, not engine or package work.",
            ["preset_candidate"] = "Can become a named RulesPreset.",
            ["amend_package_candidate"] = "Needs canonical AmendPackage representation.",
            ["campaign_overlay_candidate"] = "Applies at campaign or workspace level.",
            ["world_offer_candidate"] = "Belongs to BLACK LEDGER or mission-market unlocks.",
            ["scenario_modifier_candidate"] = "Applies to a mission, run, or district packet.",
            ["core_ruleset_gap"] = "Actually indicates missing or incorrect engine behavior.",
            ["legacy_import_candidate"] = "Needed for Chummer5a custom-data migration.",
            ["research_more"] = "Insufficient confidence."
        };

    private static readonly KarmaForgeOptionDefinition[] RoleOptions =
    [
        new KarmaForgeOptionDefinition("GM", "GM", "Owns rules and table approvals."),
        new KarmaForgeOptionDefinition("Player", "Player", "Feels the trust and visibility impact directly."),
        new KarmaForgeOptionDefinition("Creator / Publisher", "Creator / Publisher", "Needs a publishable and versioned pack shape."),
        new KarmaForgeOptionDefinition("Organizer", "Organizer", "Owns season, league, or community-wide rule posture."),
        new KarmaForgeOptionDefinition("Chummer5a veteran", "Chummer5a veteran", "Needs migration or legacy custom-data continuity."),
        new KarmaForgeOptionDefinition("Other", "Other", "Use when the current role does not fit cleanly.")
    ];

    private static readonly KarmaForgeOptionDefinition[] EditionOptions =
    [
        new KarmaForgeOptionDefinition("SR6", "SR6", "Current Sixth World table flow."),
        new KarmaForgeOptionDefinition("SR5", "SR5", "Fifth Edition and Chummer5A migration cases."),
        new KarmaForgeOptionDefinition("SR4A", "SR4A", "Fourth Edition Anniversary migration and legacy cases."),
        new KarmaForgeOptionDefinition("Anarchy", "Anarchy", "Narrative/Anarchy adjacency and crossover pressure."),
        new KarmaForgeOptionDefinition("Other", "Other / mixed", "Mixed tables, conversions, or non-standard forks.")
    ];

    private static readonly KarmaForgeOptionDefinition[] TableTypeOptions =
    [
        new KarmaForgeOptionDefinition("home_campaign", "Home campaign", "One table or one ongoing campaign."),
        new KarmaForgeOptionDefinition("living_community", "Living community", "Shared rules across many players or tables."),
        new KarmaForgeOptionDefinition("organized_play", "Organized play", "Standardized and repeatable event or season posture."),
        new KarmaForgeOptionDefinition("one_shot", "One-shot", "Short-lived or scene-scoped needs."),
        new KarmaForgeOptionDefinition("creator_lab", "Creator lab", "Publishing, packaging, or compatibility workbench."),
        new KarmaForgeOptionDefinition("migration_workbench", "Migration workbench", "Legacy import or custom-data preservation lane.")
    ];

    private static readonly KarmaForgeOptionDefinition[] RuleCategoryOptions =
    [
        new KarmaForgeOptionDefinition("gear_availability", "Gear availability", "Availability gates, unlocks, and legal shopping posture."),
        new KarmaForgeOptionDefinition("chargen_presets", "Character generation", "Preset, template, or alternate chargen flow."),
        new KarmaForgeOptionDefinition("advancement", "Advancement / karma / nuyen", "Progression pacing and reward variants."),
        new KarmaForgeOptionDefinition("edge_economy", "Edge economy", "Edge gain, spend, and risk posture."),
        new KarmaForgeOptionDefinition("matrix", "Matrix simplification", "Hacking, deck, or host complexity changes."),
        new KarmaForgeOptionDefinition("magic", "Magic / drain / rituals", "Spell, spirit, or ritual behavior changes."),
        new KarmaForgeOptionDefinition("lifestyle_downtime", "Lifestyle / downtime", "Downtime, licenses, SINs, and upkeep rules."),
        new KarmaForgeOptionDefinition("npc_opposition", "NPC / opposition", "Threat scaling and encounter posture."),
        new KarmaForgeOptionDefinition("black_ledger", "BLACK LEDGER", "Faction, district, world-offer, or season-linked unlocks."),
        new KarmaForgeOptionDefinition("migration", "Chummer5a migration", "Legacy custom-data or import parity needs."),
        new KarmaForgeOptionDefinition("other", "Other", "Use when the rule need does not fit the standard buckets.")
    ];

    private static readonly KarmaForgeOptionDefinition[] SeverityOptions =
    [
        new KarmaForgeOptionDefinition("nice_to_have", "Nice to have", "Helpful but not currently blocking play."),
        new KarmaForgeOptionDefinition("session_friction", "Session friction", "Creates repeated drag or manual clean-up."),
        new KarmaForgeOptionDefinition("blocks_play", "Blocks play", "Stops or materially delays the table right now."),
        new KarmaForgeOptionDefinition("trust_break", "Trust break", "Creates surprise, fairness, or join-confidence risk.")
    ];

    private static readonly string[] DiscoverySteps =
    [
        "Public invitation",
        "Structured pre-screen",
        "Guided synthesis interview",
        "Normalized HouseRuleDemandPacket",
        "Chummer-owned clustering",
        "Governed product decision"
    ];

    private static readonly string[] CanonicalOutputs =
    [
        "HouseRuleDemandPacket",
        "KarmaForgeCandidate",
        "RuleEnvironmentImpactHypothesis"
    ];

    private readonly KarmaForgeStore _store;
    private readonly IConfiguration _configuration;

    public KarmaForgeDiscoveryService(KarmaForgeStore store, IConfiguration configuration)
    {
        _store = store;
        _configuration = configuration;
    }

    public string CanonicalLane => "Public invitation -> structured pre-screen -> guided synthesis";

    public string EntryLane => "Guided synthesis interview";

    public IReadOnlyList<KarmaForgeTrackDefinition> ListTracks()
        => TrackDefinitions;

    public KarmaForgeTrackDefinition ResolveTrack(string? key)
        => TrackDefinitions.FirstOrDefault(track => string.Equals(track.Key, NormalizeCompact(key), StringComparison.OrdinalIgnoreCase))
            ?? TrackDefinitions[0];

    public IReadOnlyDictionary<string, string> GetCandidateDecisionMeanings()
        => CandidateDecisionMeaningsMap;

    public IReadOnlyList<KarmaForgeOptionDefinition> ListRoleOptions()
        => RoleOptions;

    public IReadOnlyList<KarmaForgeOptionDefinition> ListEditionOptions()
        => EditionOptions;

    public IReadOnlyList<KarmaForgeOptionDefinition> ListTableTypeOptions()
        => TableTypeOptions;

    public IReadOnlyList<KarmaForgeOptionDefinition> ListRuleCategoryOptions()
        => RuleCategoryOptions;

    public IReadOnlyList<KarmaForgeOptionDefinition> ListSeverityOptions()
        => SeverityOptions;

    public IReadOnlyList<string> GetDiscoverySteps()
        => DiscoverySteps;

    public IReadOnlyList<string> GetCanonicalOutputs()
        => CanonicalOutputs;

    public KarmaForgeDiscoveryArtifact BuildPublicDiscoveryArtifact()
    {
        const string destinationRoute = "/participate/karma-forge/discovery";
        const string contentType = "application/json; charset=utf-8";
        string content = JsonSerializer.Serialize(
            new
            {
                contract_name = "chummer.karma_forge.public_discovery_packet.v1",
                horizon_id = "karma-forge",
                capability_id = "karma-forge-discovery",
                artifact_kind = "discovery_packet",
                mime_type = "application/json",
                source_ref = "karma-forge:public-intake",
                destination_route = destinationRoute,
                intake_route = "/participate/karma-forge",
                status = "ready",
                canonical_lane = CanonicalLane,
                entry_lane = EntryLane,
                discovery_steps = GetDiscoverySteps(),
                canonical_outputs = GetCanonicalOutputs(),
                tracks = ListTracks().Select(static track => new
                {
                    key = track.Key,
                    title = track.Title,
                    family = track.Family,
                    questions = track.Questions
                }),
                boundaries = new
                {
                    canonical_truth = "chummer_owned_discovery_template",
                    contains_submission_data = false,
                    contains_personal_data = false,
                    contains_raw_rules_text = false,
                    provider_urls_included = false,
                    intake_is_not_backlog_or_rules_truth = true
                }
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }) + "\n";

        return new KarmaForgeDiscoveryArtifact(
            Content: content,
            ContentType: contentType,
            FileName: "karma-forge-discovery-packet.json",
            ArtifactKind: "discovery_packet",
            DestinationRoute: destinationRoute,
            SourceRef: "karma-forge:public-intake");
    }

    public IReadOnlyList<KarmaForgeExternalStageProjection> GetExternalStageProjections(KarmaForgeSubmissionProjection? submission = null)
    {
        string submissionId = submission?.SubmissionId ?? "pre_submission";
        string packetId = submission?.Packet.Id ?? "packet_pending";
        string trackKey = submission?.Packet.Source.TrackKey ?? TrackDefinitions[0].Key;
        string queueStatus = submission?.QueueStatus ?? "pre_submission";
        bool followUpAllowed = submission?.FollowUpAllowed ?? true;
        bool packetExists = submission is not null;
        bool queuedForReview = packetExists && !string.Equals(queueStatus, "pre_submission", StringComparison.OrdinalIgnoreCase);
        bool queuedForScheduling = string.Equals(queueStatus, "candidate_for_lunacal_followup", StringComparison.OrdinalIgnoreCase);

        return
        [
            BuildStageProjection(
                stageKey: "public_signal",
                publicLabel: "Public invitation",
                providerLabel: "Bounded public invite adapter",
                receiptId: "public_signal",
                boundary: "public_signal_only",
                summary: "Public discovery can invite a table into the governed intake, but it never becomes support, backlog, or rules truth.",
                actionLabel: "Open the first-party invite lane",
                actionHref: NormalizeConfiguredPath(_configuration[FacePopPublicInvitePathConfigKey]) ?? "/participate",
                enabled: true),
            BuildStageProjection(
                stageKey: "structured_prescreen",
                publicLabel: "Structured pre-screen",
                providerLabel: "Bounded structured intake adapter",
                receiptId: "structured_prescreen",
                boundary: "no_raw_sourcebook_text",
                summary: "Structured intake can collect bounded table pain and scope without turning raw copyrighted rules text into tool truth.",
                actionLabel: "Open pre-screen handoff",
                actionHref: BuildExternalStageUrl(_configuration[DeftformBaseUrlConfigKey], submissionId, packetId, trackKey, queueStatus),
                enabled: true),
            BuildStageProjection(
                stageKey: "adaptive_interview",
                publicLabel: "Guided synthesis interview",
                providerLabel: "Bounded interview adapter",
                receiptId: "adaptive_interview",
                boundary: "interview_signal_not_product_truth",
                summary: "Adaptive follow-up can sharpen a demand packet, but the interview stays signal only until Hub normalizes it back into Chummer-owned packets and decisions.",
                actionLabel: "Open guided interview handoff",
                actionHref: BuildExternalStageUrl(_configuration[IcanpreneurBaseUrlConfigKey], submissionId, packetId, trackKey, queueStatus),
                enabled: followUpAllowed),
            BuildStageProjection(
                stageKey: "quant_validation",
                publicLabel: "Validation survey",
                providerLabel: "Bounded validation adapter",
                receiptId: "quant_validation",
                boundary: "ranking_signal_not_priority_truth",
                summary: "Survey ranking can validate demand shape, but it never becomes the priority decision or canonical roadmap truth by itself.",
                actionLabel: "Open validation survey handoff",
                actionHref: BuildExternalStageUrl(_configuration[MetaSurveyBaseUrlConfigKey], submissionId, packetId, trackKey, queueStatus),
                enabled: followUpAllowed),
            BuildStageProjection(
                stageKey: "scheduled_followup",
                publicLabel: "Scheduled follow-up",
                providerLabel: "Bounded scheduling adapter",
                receiptId: "scheduled_followup",
                boundary: "human_followup_not_case_truth",
                summary: "Human follow-up can be scheduled when consent is explicit, but booking never becomes support-case, campaign, or product-decision truth.",
                actionLabel: "Schedule bounded follow-up",
                actionHref: BuildExternalStageUrl(_configuration[LunacalBaseUrlConfigKey], submissionId, packetId, trackKey, queueStatus),
                enabled: followUpAllowed && queuedForScheduling),
            BuildInternalStageProjection(
                stageKey: "review_board",
                publicLabel: "Governed review board",
                providerLabel: "Bounded operator projection",
                receiptId: "review_board",
                boundary: "projection_and_process_only",
                status: queuedForReview ? "bounded_ready" : "bounded_pending_packet",
                summary: queuedForReview
                    ? "The packet is ready for Teable and NextStep review handling, but those operator surfaces remain projection and process only."
                    : "Review-board routing appears only after Hub has normalized a first-party packet. Teable and NextStep never become rules truth.",
                actionLabel: null,
                actionHref: null),
            BuildInternalStageProjection(
                stageKey: "decision",
                publicLabel: "Product Governor decision",
                providerLabel: "First-party canonical decision point",
                receiptId: "decision",
                boundary: "canonical_decision_only_here",
                status: queuedForReview ? "bounded_ready" : "bounded_pending_packet",
                summary: queuedForReview
                    ? "Only Product Governor and Chummer design can turn this packet into a real product decision. No external adapter can promote itself into backlog or rules truth."
                    : "Decision stays empty until a normalized packet exists. Public signal and interviews cannot become the decision by themselves.",
                actionLabel: null,
                actionHref: null),
            BuildInternalStageProjection(
                stageKey: "closeout",
                publicLabel: "Public closeout",
                providerLabel: "First-party closeout projection",
                receiptId: "closeout",
                boundary: "closeout_must_match_design_truth",
                status: queuedForReview ? "bounded_waiting_decision" : "bounded_pending_packet",
                summary: queuedForReview
                    ? "ProductLift, Emailit, and public closeout can only speak after a governed decision exists, and the closeout must match Chummer-owned design truth."
                    : "Closeout does not exist yet. It is only created after packet review and a first-party decision, not from public votes or survey noise.",
                actionLabel: queuedForReview ? "Read first-party roadmap and closeout surfaces" : null,
                actionHref: queuedForReview ? "/roadmap" : null),
        ];
    }

    private static KarmaForgeExternalStageProjection BuildStageProjection(
        string stageKey,
        string publicLabel,
        string providerLabel,
        string receiptId,
        string boundary,
        string summary,
        string actionLabel,
        string? actionHref,
        bool enabled)
    {
        if (!enabled)
        {
            return new KarmaForgeExternalStageProjection(
                StageKey: stageKey,
                PublicLabel: publicLabel,
                ProviderLabel: providerLabel,
                ReceiptId: receiptId,
                Boundary: boundary,
                Status: "bounded_pending_consent",
                Summary: $"{summary} Follow-up stays off until the reporter explicitly allows the next stage.",
                ActionHref: null,
                ActionLabel: null);
        }

        if (string.IsNullOrWhiteSpace(actionHref))
        {
            return new KarmaForgeExternalStageProjection(
                StageKey: stageKey,
                PublicLabel: publicLabel,
                ProviderLabel: providerLabel,
                ReceiptId: receiptId,
                Boundary: boundary,
                Status: "bounded_unconfigured",
                Summary: $"{summary} The bounded handoff contract exists, but this host has not configured the external adapter yet.",
                ActionHref: null,
                ActionLabel: null);
        }

        return new KarmaForgeExternalStageProjection(
            StageKey: stageKey,
            PublicLabel: publicLabel,
            ProviderLabel: providerLabel,
            ReceiptId: receiptId,
            Boundary: boundary,
            Status: "bounded_ready",
            Summary: summary,
            ActionHref: actionHref,
            ActionLabel: actionLabel);
    }

    private static KarmaForgeExternalStageProjection BuildInternalStageProjection(
        string stageKey,
        string publicLabel,
        string providerLabel,
        string receiptId,
        string boundary,
        string status,
        string summary,
        string? actionLabel,
        string? actionHref)
        => new(
            StageKey: stageKey,
            PublicLabel: publicLabel,
            ProviderLabel: providerLabel,
            ReceiptId: receiptId,
            Boundary: boundary,
            Status: status,
            Summary: summary,
            ActionHref: actionHref,
            ActionLabel: actionLabel);

    private static string? NormalizeConfiguredPath(string? rawValue)
    {
        if (string.IsNullOrWhiteSpace(rawValue))
        {
            return null;
        }

        string value = rawValue.Trim();
        if (Uri.TryCreate(value, UriKind.Absolute, out Uri? absolute))
        {
            return absolute.ToString();
        }

        return value.StartsWith("/", StringComparison.Ordinal) ? value : $"/{value}";
    }

    private static string? BuildExternalStageUrl(
        string? baseUrl,
        string submissionId,
        string packetId,
        string trackKey,
        string queueStatus)
    {
        string? normalizedBaseUrl = NormalizeConfiguredPath(baseUrl);
        if (string.IsNullOrWhiteSpace(normalizedBaseUrl))
        {
            return null;
        }

        string separator = normalizedBaseUrl.Contains('?', StringComparison.Ordinal) ? "&" : "?";
        return string.Concat(
            normalizedBaseUrl,
            separator,
            "source=chummer",
            "&submissionId=", Uri.EscapeDataString(submissionId),
            "&packetId=", Uri.EscapeDataString(packetId),
            "&trackKey=", Uri.EscapeDataString(trackKey),
            "&queueStatus=", Uri.EscapeDataString(queueStatus));
    }

    public KarmaForgeDashboardSummary GetDashboardSummary()
    {
        lock (_store.Gate)
        {
            KarmaForgeSubmissionProjection[] submissions = _store.SubmissionsById.Values.ToArray();
            return new KarmaForgeDashboardSummary(
                TotalPackets: submissions.Length,
                GovernorQueueCount: submissions.Count(static item => string.Equals(item.QueueStatus, "queued_for_product_governor", StringComparison.OrdinalIgnoreCase)),
                FollowUpCandidateCount: submissions.Count(static item => string.Equals(item.QueueStatus, "candidate_for_lunacal_followup", StringComparison.OrdinalIgnoreCase)),
                CoreRulesetGapCount: submissions.Count(static item => string.Equals(item.QueueStatus, "queued_for_core_ruleset_review", StringComparison.OrdinalIgnoreCase)),
                ResearchQueueCount: submissions.Count(static item => string.Equals(item.QueueStatus, "queued_for_research_cluster", StringComparison.OrdinalIgnoreCase)),
                ShareablePacketCount: submissions.Count(static item => item.Packet.PrioritySignals.ShareabilityScore >= 4));
        }
    }

    public KarmaForgeSubmissionProjection Submit(KarmaForgeSubmissionRequest request, string? subjectId, string? subjectDisplayName)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        KarmaForgeTrackDefinition track = ResolveTrack(request.TrackKey);
        string normalizedRole = NormalizeCompact(request.RespondentRole) ?? "GM";
        string normalizedEdition = NormalizeCompact(request.Edition) ?? "SR6";
        string normalizedTableType = NormalizeCompact(request.TableType) ?? "home_campaign";
        string normalizedRuleCategory = NormalizeCompact(request.RuleCategory) ?? "other";
        string normalizedSeverity = NormalizeCompact(request.Severity) ?? "session_friction";
        string userWordsSummary = NormalizeCompact(request.UserWordsSummary) ?? string.Empty;
        string currentWorkaround = NormalizeCompact(request.CurrentWorkaround) ?? string.Empty;
        string interpretedNeedSummary = NormalizeCompact(request.InterpretedNeedSummary) ?? string.Empty;
        string impactNotes = NormalizeCompact(request.ImpactNotes) ?? string.Empty;
        string shareabilityNotes = NormalizeCompact(request.ShareabilityNotes) ?? string.Empty;
        string? replyEmail = NormalizeEmail(request.ReplyEmail);
        string? normalizedSubjectId = NormalizeCompact(subjectId);
        string? normalizedSubjectDisplayName = NormalizeCompact(subjectDisplayName);
        string combinedText = string.Join(
            " ",
            new[]
            {
                request.FeedbackPrompt,
                userWordsSummary,
                currentWorkaround,
                interpretedNeedSummary,
                impactNotes,
                shareabilityNotes,
                normalizedRuleCategory,
                normalizedSeverity
            }.Where(static part => !string.IsNullOrWhiteSpace(part)));

        string[] affectedDomains = ResolveAffectedDomains(combinedText, track.Family);
        string[] desiredScope = ResolveDesiredScope(combinedText, shareabilityNotes);
        (string[] likelyObjects, string[] blackLedgerObjects) = ResolveObjects(affectedDomains, desiredScope, combinedText);
        KarmaForgeTrustRequirementsProjection trustRequirements = ResolveTrustRequirements(track.Family, combinedText);
        KarmaForgePortabilityRequirementsProjection portabilityRequirements = ResolvePortabilityRequirements(desiredScope, combinedText, shareabilityNotes);
        KarmaForgePrioritySignalsProjection prioritySignals = ResolvePrioritySignals(combinedText, shareabilityNotes, track.Family);
        string candidateDecision = ResolveCandidateDecision(track.Family, combinedText);
        string candidateDecisionMeaning = CandidateDecisionMeaningsMap.TryGetValue(candidateDecision, out string? meaning)
            ? meaning
            : string.Empty;
        string proposedRoute = string.Equals(candidateDecision, "core_ruleset_gap", StringComparison.OrdinalIgnoreCase)
            ? "core_ruleset_gap_review"
            : "KARMA_FORGE";
        string interpretedSummary = string.IsNullOrWhiteSpace(interpretedNeedSummary)
            ? userWordsSummary
            : interpretedNeedSummary;
        string interpretedConfidence = string.IsNullOrWhiteSpace(interpretedNeedSummary)
            ? "low"
            : string.IsNullOrWhiteSpace(impactNotes)
                ? "medium"
                : "high";
        string titleSource = !string.IsNullOrWhiteSpace(interpretedSummary)
            ? interpretedSummary
            : userWordsSummary;
        string title = BuildTitle(titleSource);
        string submissionId = $"kf_{now:yyyyMMddHHmmss}_{RandomHex(4)}";
        string packetId = $"hrp_{now:yyyy_MM_dd_HHmmss}_{SlugKey(track.Key)}";
        string[] nextQuestions = track.Questions.Take(6).ToArray();
        string[] nextSteps = ResolveNextSteps(
            trackFamily: track.Family,
            userWordsSummary,
            currentWorkaround,
            interpretedSummary,
            candidateDecision);
        (string queueStatus, string queueSummary, string reporterNextAction) = ResolveQueueStatus(
            candidateDecision,
            prioritySignals,
            request.FollowUpAllowed,
            desiredScope);

        HouseRuleDemandPacketProjection packet = new(
            Id: packetId,
            Title: title,
            Source: new KarmaForgeSourceProjection(
                IntakeChannel: "Hub Participate -> structured pre-screen",
                CanonicalLane: CanonicalLane,
                RespondentRole: normalizedRole,
                Edition: normalizedEdition,
                TableType: normalizedTableType,
                TrackKey: track.Key,
                InterviewTrack: track.Title,
                RuleCategory: normalizedRuleCategory,
                Severity: normalizedSeverity,
                InterviewRef: $"hub_karma_forge_{track.Key}_{submissionId}",
                ConsentRef: $"hub_karma_forge_consent_{submissionId}",
                ExternalStages: Array.Empty<KarmaForgeExternalStageProjection>(),
                JourneyProofEventRefs: Array.Empty<JourneyProofEventRef>()),
            UserWords: new KarmaForgeUserWordsProjection(
                Summary: userWordsSummary,
                CurrentWorkaround: currentWorkaround),
            InterpretedNeed: new KarmaForgeInterpretedNeedProjection(
                Summary: interpretedSummary,
                Confidence: interpretedConfidence),
            AffectedDomains: affectedDomains,
            DesiredScope: desiredScope,
            LikelyChummerObjects: likelyObjects,
            PossibleBlackLedgerObjects: blackLedgerObjects,
            TrustRequirements: trustRequirements,
            PortabilityRequirements: portabilityRequirements,
            PrioritySignals: prioritySignals,
            Classification: new KarmaForgeClassificationProjection(
                CurrentStatus: "candidate",
                DecisionNeeded: true,
                CandidateDecision: candidateDecision,
                CandidateDecisionMeaning: candidateDecisionMeaning,
                ProposedRoute: proposedRoute),
            NextSteps: nextSteps,
            OperatorNotes: new KarmaForgeOperatorNotesProjection(
                FeedbackPrompt: NormalizeCompact(request.FeedbackPrompt) ?? string.Empty,
                ImpactNotes: impactNotes,
                ShareabilityNotes: shareabilityNotes));

        packet = packet with
        {
            Source = packet.Source with
            {
                ExternalStages = GetExternalStageProjections(new KarmaForgeSubmissionProjection(
                    SubmissionId: submissionId,
                    SubmittedAtUtc: now,
                    IntakeStatus: "packet_normalized",
                    QueueStatus: queueStatus,
                    QueueSummary: queueSummary,
                    ReporterNextAction: reporterNextAction,
                    ConsentSummary: string.Empty,
                    AuthenticatedSubmission: !string.IsNullOrWhiteSpace(normalizedSubjectId),
                    FollowUpAllowed: request.FollowUpAllowed,
                    QuoteAllowed: request.QuoteAllowed,
                    SubjectId: normalizedSubjectId,
                    SubjectDisplayName: normalizedSubjectDisplayName,
                    ReplyEmail: replyEmail,
                    NextQuestions: nextQuestions,
                    Packet: packet,
                    Candidate: new KarmaForgeCandidateProjection(
                        Id: $"kfc_{packetId}",
                        Title: title,
                        LinkedPacketId: packetId,
                        TrackKey: track.Key,
                        TrackTitle: track.Title,
                        CandidateDecision: candidateDecision,
                        CandidateDecisionMeaning: candidateDecisionMeaning,
                        ProposedRoute: proposedRoute,
                        GovernorDecisionRequired: true,
                        Confidence: interpretedConfidence,
                        PrioritySignals: prioritySignals),
                    ImpactHypothesis: new RuleEnvironmentImpactHypothesisProjection(
                        Id: $"reh_{packetId}",
                        Title: title,
                        Summary: interpretedSummary,
                        AffectedDomains: affectedDomains,
                        LikelyObjects: likelyObjects,
                        PossibleBlackLedgerObjects: blackLedgerObjects,
                        TrustPressure: ResolveEnabledKeys(trustRequirements),
                        PortabilityPressure: ResolveEnabledKeys(portabilityRequirements),
                        RolloutScope: desiredScope,
                        ComparisonSurface: trustRequirements.BuildDiffRequired ? "build_diff" : "notice_only",
                        PlayerVisibility: trustRequirements.PlayerVisibleBeforeJoin ? "before_join" : "in_workspace",
                        RollbackSurface: trustRequirements.RollbackRequired ? "rollback_required" : "inform_only"))),
                JourneyProofEventRefs = BuildJourneyProofEventRefs(packetId)
            }
        };

        KarmaForgeCandidateProjection candidate = new(
            Id: $"kfc_{packetId}",
            Title: title,
            LinkedPacketId: packetId,
            TrackKey: track.Key,
            TrackTitle: track.Title,
            CandidateDecision: candidateDecision,
            CandidateDecisionMeaning: candidateDecisionMeaning,
            ProposedRoute: proposedRoute,
            GovernorDecisionRequired: true,
            Confidence: interpretedConfidence,
            PrioritySignals: prioritySignals);

        RuleEnvironmentImpactHypothesisProjection impactHypothesis = new(
            Id: $"reh_{packetId}",
            Title: title,
            Summary: interpretedSummary,
            AffectedDomains: affectedDomains,
            LikelyObjects: likelyObjects,
            PossibleBlackLedgerObjects: blackLedgerObjects,
            TrustPressure: ResolveEnabledKeys(trustRequirements),
            PortabilityPressure: ResolveEnabledKeys(portabilityRequirements),
            RolloutScope: desiredScope,
            ComparisonSurface: trustRequirements.BuildDiffRequired ? "build_diff" : "notice_only",
            PlayerVisibility: trustRequirements.PlayerVisibleBeforeJoin ? "before_join" : "in_workspace",
            RollbackSurface: trustRequirements.RollbackRequired ? "rollback_required" : "inform_only");

        string consentSummary = BuildConsentSummary(request, normalizedSubjectId, replyEmail);
        KarmaForgeSubmissionProjection submission = new(
            SubmissionId: submissionId,
            SubmittedAtUtc: now,
            IntakeStatus: "packet_normalized",
            QueueStatus: queueStatus,
            QueueSummary: queueSummary,
            ReporterNextAction: reporterNextAction,
            ConsentSummary: consentSummary,
            AuthenticatedSubmission: !string.IsNullOrWhiteSpace(normalizedSubjectId),
            FollowUpAllowed: request.FollowUpAllowed,
            QuoteAllowed: request.QuoteAllowed,
            SubjectId: normalizedSubjectId,
            SubjectDisplayName: normalizedSubjectDisplayName,
            ReplyEmail: replyEmail,
            NextQuestions: nextQuestions,
            Packet: packet,
            Candidate: candidate,
            ImpactHypothesis: impactHypothesis);

        lock (_store.Gate)
        {
            _store.SubmissionsById[submissionId] = submission;
            _store.PersistLocked();
        }

        return submission;
    }

    public KarmaForgeSubmissionProjection? FindById(string submissionId)
    {
        lock (_store.Gate)
        {
            return _store.SubmissionsById.TryGetValue(submissionId, out KarmaForgeSubmissionProjection? submission)
                ? submission
                : null;
        }
    }

    public IReadOnlyList<KarmaForgeSubmissionProjection> ListRecentForSubject(string? subjectId, int take = 5)
    {
        string? normalizedSubjectId = NormalizeCompact(subjectId);
        if (string.IsNullOrWhiteSpace(normalizedSubjectId) || take <= 0)
        {
            return Array.Empty<KarmaForgeSubmissionProjection>();
        }

        lock (_store.Gate)
        {
            return _store.SubmissionsById.Values
                .Where(item => string.Equals(item.SubjectId, normalizedSubjectId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.SubmittedAtUtc)
                .Take(take)
                .ToArray();
        }
    }

    public IReadOnlyList<JourneyProofEventRef> GetJourneyProofEventRefs(string? packetId = null)
        => BuildJourneyProofEventRefs(string.IsNullOrWhiteSpace(packetId) ? "hub_karma_forge_preview" : packetId);

    private static IReadOnlyList<JourneyProofEventRef> BuildJourneyProofEventRefs(string packetId)
        =>
        [
            new(
                EventKey: "karma_request_submitted",
                JourneyKey: KarmaForgeJourneyKey,
                SourceRef: packetId,
                Summary: "The public discovery request entered the first-party KARMA FORGE intake lane."),
            new(
                EventKey: "karma_interview_completed",
                JourneyKey: KarmaForgeJourneyKey,
                SourceRef: packetId,
                Summary: "Guided follow-up completed inside the bounded KARMA FORGE discovery chain."),
            new(
                EventKey: "karma_demand_packet_created",
                JourneyKey: KarmaForgeJourneyKey,
                SourceRef: packetId,
                Summary: "The intake normalized into a Chummer-owned demand packet before Product Governor review."),
            new(
                EventKey: "karma_candidate_reviewed",
                JourneyKey: KarmaForgeJourneyKey,
                SourceRef: packetId,
                Summary: "The candidate is visible on the governed review rail instead of staying provider-owned.")
        ];

    private static string[] ResolveAffectedDomains(string text, string trackFamily)
    {
        List<string> found = [];
        (string Name, string[] Terms)[] domainMap =
        [
            ("gear", ["gear", "weapon", "armor", "cyberware"]),
            ("availability", ["availability", "restricted", "forbidden", "unlock"]),
            ("character_build_legality", ["legality", "legal", "illegal", "build", "chargen", "character creation"]),
            ("campaign_progression", ["campaign", "progression", "advance", "advancement", "karma", "nuyen", "downtime"]),
            ("dice_pools", ["dice pool", "dice pools", "pool modifier", "modifier"]),
            ("edge_economy", ["edge"]),
            ("matrix", ["matrix", "deck", "hacking", "host"]),
            ("magic", ["magic", "drain", "ritual", "spirit", "summon", "spell"]),
            ("lifestyle", ["lifestyle", "rent", "downtime", "license", "sin"]),
            ("npc_opposition", ["npc", "opposition", "enemy", "encounter", "threat"]),
            ("black_ledger", ["black ledger", "faction", "district", "job board", "world offer", "scenario"]),
            ("migration", ["chummer5a", "import", "legacy", "migration", "custom data", "amend"])
        ];

        foreach ((string name, string[] terms) in domainMap)
        {
            if (ContainsAny(text, terms))
            {
                found.Add(name);
            }
        }

        if (found.Count > 0)
        {
            return found.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        }

        return trackFamily switch
        {
            "player_trust" => ["character_build_legality", "campaign_progression"],
            "creator_publisher" => ["campaign_progression"],
            "organizer_black_ledger" => ["black_ledger", "campaign_progression"],
            "veteran_migration" => ["migration", "character_build_legality"],
            _ => ["campaign_progression"]
        };
    }

    private static string[] ResolveDesiredScope(string text, string shareabilityNotes)
    {
        string haystack = string.Join(" ", new[] { text, shareabilityNotes }.Where(static value => !string.IsNullOrWhiteSpace(value)));
        List<string> scopes = [];
        (string Name, string[] Terms)[] scopeMap =
        [
            ("character", ["one character", "single character", "my character"]),
            ("campaign", ["campaign", "table", "group", "home game"]),
            ("scene", ["scene", "run only", "single run"]),
            ("district", ["district", "neighborhood"]),
            ("all_games", ["all my games", "all games", "global"]),
            ("reusable_pack_candidate", ["reusable", "publish", "share", "other tables", "package"])
        ];

        foreach ((string name, string[] terms) in scopeMap)
        {
            if (ContainsAny(haystack, terms))
            {
                scopes.Add(name);
            }
        }

        if (scopes.Count == 0)
        {
            scopes.Add("campaign");
        }

        return scopes.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
    }

    private static (string[] LikelyObjects, string[] BlackLedgerObjects) ResolveObjects(
        IReadOnlyList<string> affectedDomains,
        IReadOnlyList<string> desiredScope,
        string text)
    {
        List<string> likely = ["RuleEnvironment"];
        if (desiredScope.Contains("reusable_pack_candidate", StringComparer.OrdinalIgnoreCase)
            || affectedDomains.Contains("migration", StringComparer.OrdinalIgnoreCase)
            || ContainsAny(text, "package", "amend", "preset"))
        {
            likely.Add("AmendPackage");
        }

        if (desiredScope.Contains("campaign", StringComparer.OrdinalIgnoreCase)
            || desiredScope.Contains("scene", StringComparer.OrdinalIgnoreCase)
            || desiredScope.Contains("district", StringComparer.OrdinalIgnoreCase))
        {
            likely.Add("CampaignOverlayPackage");
        }

        if (ContainsAny(text, "receipt", "rollback", "approval", "unlock", "before/after", "before after", "preview"))
        {
            likely.Add("ActivationReceipt");
        }

        List<string> blackLedger = [];
        if (affectedDomains.Contains("black_ledger", StringComparer.OrdinalIgnoreCase)
            || ContainsAny(text, "faction", "district", "job board", "reward", "unlock"))
        {
            blackLedger.Add("WorldOffer");
            blackLedger.Add("ScenarioModifier");
        }

        return (
            likely.Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
            blackLedger.Distinct(StringComparer.OrdinalIgnoreCase).ToArray());
    }

    private static KarmaForgeTrustRequirementsProjection ResolveTrustRequirements(string trackFamily, string text)
        => new(
            PlayerVisibleBeforeJoin: trackFamily is "player_trust" or "organizer_black_ledger"
                || ContainsAny(text, "join", "before play", "campaign invite", "player visible"),
            BuildDiffRequired: ContainsAny(text, "build", "diff", "cost", "availability", "dice", "legality", "preview"),
            RollbackRequired: ContainsAny(text, "rollback", "reversible", "mid-campaign", "undo", "revert")
                || trackFamily is "gm_house_rule" or "organizer_black_ledger",
            ApprovalRequired: ContainsAny(text, "approve", "approval", "warn", "blocked", "gm decides", "consent")
                || trackFamily != "veteran_migration",
            ReceiptRequired: true);

    private static KarmaForgePortabilityRequirementsProjection ResolvePortabilityRequirements(
        IReadOnlyList<string> desiredScope,
        string text,
        string shareabilityNotes)
    {
        string haystack = string.Join(" ", new[] { text, shareabilityNotes }.Where(static value => !string.IsNullOrWhiteSpace(value)));
        bool shareable = desiredScope.Contains("reusable_pack_candidate", StringComparer.OrdinalIgnoreCase)
            || ContainsAny(haystack, "share", "publish", "other tables", "template");
        return new KarmaForgePortabilityRequirementsProjection(
            CrossDeviceRestore: shareable || ContainsAny(haystack, "device", "phone", "sync", "restore", "laptop"),
            PackageFingerprintRequired: shareable || ContainsAny(haystack, "fingerprint", "version", "rollback", "receipt"));
    }

    private static KarmaForgePrioritySignalsProjection ResolvePrioritySignals(string text, string shareabilityNotes, string trackFamily)
    {
        string haystack = string.Join(" ", new[] { text, shareabilityNotes }.Where(static value => !string.IsNullOrWhiteSpace(value)));
        int blockerScore = ContainsAny(haystack, "blocked", "can't", "cannot", "breaks", "stops play")
            ? 5
            : ContainsAny(haystack, "need", "must", "depends on")
                ? 4
                : 3;
        string frequencySignal = ContainsAny(haystack, "every session", "most often", "constantly", "all the time")
            ? "high"
            : ContainsAny(haystack, "sometimes", "occasionally", "rare")
                ? "low"
                : "medium";
        int shareabilityScore = ContainsAny(haystack, "publish", "share", "other tables", "reusable")
            ? 5
            : ContainsAny(haystack, "campaign", "group")
                ? 3
                : 1;
        string implementationRisk = ContainsAny(haystack, "matrix", "magic", "migration", "import", "core math", "engine")
            ? "high"
            : trackFamily is "organizer_black_ledger" or "gm_house_rule"
                ? "medium"
                : "low";
        string monetizationRelevance = trackFamily is "gm_house_rule" or "creator_publisher"
            ? "possible_premium_gm_tool"
            : "unclear";
        return new KarmaForgePrioritySignalsProjection(
            BlockerScore: blockerScore,
            FrequencySignal: frequencySignal,
            ShareabilityScore: shareabilityScore,
            ImplementationRisk: implementationRisk,
            MonetizationRelevance: monetizationRelevance);
    }

    private static string ResolveCandidateDecision(string trackFamily, string text)
    {
        if (ContainsAny(text, "chummer5a", "legacy", "migration", "custom data", "import"))
        {
            return "legacy_import_candidate";
        }

        if (ContainsAny(text, "wrong math", "engine bug", "core bug", "incorrect rules", "does not work"))
        {
            return "core_ruleset_gap";
        }

        if (ContainsAny(text, "faction", "district", "world offer", "job board", "season-wide"))
        {
            return "world_offer_candidate";
        }

        if (ContainsAny(text, "scene", "scenario", "run modifier"))
        {
            return "scenario_modifier_candidate";
        }

        if (ContainsAny(text, "preset", "template", "character generation", "chargen"))
        {
            return "preset_candidate";
        }

        if (ContainsAny(text, "campaign", "availability", "unlock", "overlay", "workspace"))
        {
            return "campaign_overlay_candidate";
        }

        if (ContainsAny(text, "package", "amend", "share", "publish"))
        {
            return "amend_package_candidate";
        }

        if (string.Equals(trackFamily, "player_trust", StringComparison.OrdinalIgnoreCase))
        {
            return "document_only";
        }

        return "research_more";
    }

    private static string[] ResolveNextSteps(
        string trackFamily,
        string userWordsSummary,
        string currentWorkaround,
        string interpretedNeedSummary,
        string candidateDecision)
    {
        List<string> steps = [];
        if (string.IsNullOrWhiteSpace(userWordsSummary))
        {
            steps.Add("Capture the table's own wording before clustering.");
        }

        if (string.IsNullOrWhiteSpace(currentWorkaround))
        {
            steps.Add("Document the current workaround with one concrete session example.");
        }

        if (!string.Equals(trackFamily, "player_trust", StringComparison.OrdinalIgnoreCase))
        {
            steps.Add("Validate the packet with the player trust track before any prototype route.");
        }

        if (string.IsNullOrWhiteSpace(interpretedNeedSummary))
        {
            steps.Add("Rewrite the request into a Chummer-owned interpreted need summary.");
        }

        if (string.Equals(candidateDecision, "research_more", StringComparison.OrdinalIgnoreCase))
        {
            steps.Add("Cluster at least three similar signals before governed product classification.");
        }
        else if (string.Equals(candidateDecision, "core_ruleset_gap", StringComparison.OrdinalIgnoreCase))
        {
            steps.Add("Verify whether this is an engine correctness gap before routing it into KARMA FORGE.");
        }
        else
        {
            steps.Add("Prepare a governed product route decision with trust, rollback, and portability evidence.");
        }

        return steps.Take(4).ToArray();
    }

    private static (string QueueStatus, string QueueSummary, string ReporterNextAction) ResolveQueueStatus(
        string candidateDecision,
        KarmaForgePrioritySignalsProjection prioritySignals,
        bool followUpAllowed,
        IReadOnlyList<string> desiredScope)
    {
        if (string.Equals(candidateDecision, "core_ruleset_gap", StringComparison.OrdinalIgnoreCase))
        {
            return (
                "queued_for_core_ruleset_review",
                "Chummer normalized this as a likely rules-correctness or engine-gap signal before any KARMA FORGE packaging work.",
                "Keep one concrete before-and-after example nearby in case Chummer asks for a correctness repro.");
        }

        if (string.Equals(candidateDecision, "research_more", StringComparison.OrdinalIgnoreCase))
        {
            return (
                "queued_for_research_cluster",
                "The packet is normalized, but it still needs more repeated signal before governed product routing can be trusted.",
                "If this blocks play repeatedly, come back with one or two concrete campaign examples instead of broader feature wording.");
        }

        if (followUpAllowed && (prioritySignals.BlockerScore >= 4 || prioritySignals.ShareabilityScore >= 4))
        {
            return (
                "candidate_for_lunacal_followup",
                "The packet is strong enough for a guided follow-up before governed product routing.",
                "Watch the follow-up route you allowed; Chummer may ask for examples, receipts, or a cleaner shareable package shape.");
        }

        if (prioritySignals.ShareabilityScore >= 4 || desiredScope.Contains("reusable_pack_candidate", StringComparer.OrdinalIgnoreCase))
        {
            return (
                "queued_for_metasurvey_validation",
                "This looks reusable across tables, so clustering and quantitative validation are the next likely moves before governed product routing.",
                "If Chummer follows up, bring one table-local example and one version you would share with another table.");
        }

        return (
            "queued_for_product_governor",
            "The packet is normalized into Chummer-owned outputs and is ready for clustering plus governed product classification.",
            "Keep the receipt id nearby in case Chummer asks for one concrete before-and-after build example.");
    }

    private static string[] ResolveEnabledKeys(KarmaForgeTrustRequirementsProjection trustRequirements)
    {
        List<string> enabled = [];
        if (trustRequirements.PlayerVisibleBeforeJoin)
        {
            enabled.Add("player_visible_before_join");
        }

        if (trustRequirements.BuildDiffRequired)
        {
            enabled.Add("build_diff_required");
        }

        if (trustRequirements.RollbackRequired)
        {
            enabled.Add("rollback_required");
        }

        if (trustRequirements.ApprovalRequired)
        {
            enabled.Add("approval_required");
        }

        if (trustRequirements.ReceiptRequired)
        {
            enabled.Add("receipt_required");
        }

        return enabled.ToArray();
    }

    private static string[] ResolveEnabledKeys(KarmaForgePortabilityRequirementsProjection portabilityRequirements)
    {
        List<string> enabled = [];
        if (portabilityRequirements.CrossDeviceRestore)
        {
            enabled.Add("cross_device_restore");
        }

        if (portabilityRequirements.PackageFingerprintRequired)
        {
            enabled.Add("package_fingerprint_required");
        }

        return enabled.ToArray();
    }

    private static bool ContainsAny(string? text, params string[] terms)
        => ContainsAny(text, (IEnumerable<string>)terms);

    private static bool ContainsAny(string? text, IEnumerable<string> terms)
    {
        string haystack = (text ?? string.Empty).ToLowerInvariant();
        return terms.Any(term => haystack.Contains(term.ToLowerInvariant(), StringComparison.Ordinal));
    }

    private static string BuildConsentSummary(KarmaForgeSubmissionRequest request, string? subjectId, string? replyEmail)
    {
        List<string> parts =
        [
            "Design-informed discovery consent recorded",
            string.IsNullOrWhiteSpace(subjectId)
                ? "guest submission"
                : "signed-in Hub submission",
            request.FollowUpAllowed
                ? (string.IsNullOrWhiteSpace(replyEmail) && string.IsNullOrWhiteSpace(subjectId)
                    ? "follow-up allowed"
                    : "follow-up lane allowed")
                : "no follow-up requested",
            request.QuoteAllowed
                ? "anonymous quote allowed"
                : "quotes blocked"
        ];
        return string.Join(" · ", parts);
    }

    private static string BuildTitle(string? source)
    {
        string normalized = NormalizeCompact(source) ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return "House-rule discovery draft";
        }

        int sentenceEnd = normalized.IndexOfAny(['.', '!', '?']);
        string title = sentenceEnd > 0
            ? normalized[..sentenceEnd]
            : normalized;
        if (title.Length > 72)
        {
            title = title[..72];
        }

        return title.Trim().Trim('"', '\'', '.', ':', ';');
    }

    private static string SlugKey(string value)
    {
        StringBuilder builder = new();
        bool previousUnderscore = false;
        foreach (char character in value.Trim())
        {
            if (char.IsLetterOrDigit(character))
            {
                builder.Append(char.ToLowerInvariant(character));
                previousUnderscore = false;
            }
            else if (!previousUnderscore)
            {
                builder.Append('_');
                previousUnderscore = true;
            }
        }

        string slug = builder.ToString().Trim('_');
        return string.IsNullOrWhiteSpace(slug) ? "draft" : slug;
    }

    private static string RandomHex(int byteCount)
        => Convert.ToHexString(RandomNumberGenerator.GetBytes(byteCount)).ToLowerInvariant();

    private static string? NormalizeCompact(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? null
            : string.Join(" ", value.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));

    private static string? NormalizeEmail(string? value)
    {
        string? normalized = NormalizeCompact(value);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return null;
        }

        return normalized.ToLowerInvariant();
    }
}

public sealed record KarmaForgeOptionDefinition(
    string Value,
    string Label,
    string Description);

public sealed record KarmaForgeTrackDefinition(
    string Key,
    string Title,
    string Family,
    IReadOnlyList<string> Questions);

public sealed record KarmaForgeDashboardSummary(
    int TotalPackets,
    int GovernorQueueCount,
    int FollowUpCandidateCount,
    int CoreRulesetGapCount,
    int ResearchQueueCount,
    int ShareablePacketCount);

public sealed class KarmaForgeSubmissionRequest
{
    public string TrackKey { get; set; } = "gm_house_rule_track";
    public string RespondentRole { get; set; } = "GM";
    public string Edition { get; set; } = "SR6";
    public string TableType { get; set; } = "home_campaign";
    public string RuleCategory { get; set; } = "gear_availability";
    public string Severity { get; set; } = "session_friction";
    public string FeedbackPrompt { get; set; } = string.Empty;
    public string UserWordsSummary { get; set; } = string.Empty;
    public string CurrentWorkaround { get; set; } = string.Empty;
    public string InterpretedNeedSummary { get; set; } = string.Empty;
    public string ImpactNotes { get; set; } = string.Empty;
    public string ShareabilityNotes { get; set; } = string.Empty;
    public string ReplyEmail { get; set; } = string.Empty;
    public bool FollowUpAllowed { get; set; } = true;
    public bool QuoteAllowed { get; set; }
    public bool ConsentAccepted { get; set; }
}

public sealed record KarmaForgeSubmissionProjection(
    string SubmissionId,
    DateTimeOffset SubmittedAtUtc,
    string IntakeStatus,
    string QueueStatus,
    string QueueSummary,
    string ReporterNextAction,
    string ConsentSummary,
    bool AuthenticatedSubmission,
    bool FollowUpAllowed,
    bool QuoteAllowed,
    string? SubjectId,
    string? SubjectDisplayName,
    string? ReplyEmail,
    IReadOnlyList<string> NextQuestions,
    HouseRuleDemandPacketProjection Packet,
    KarmaForgeCandidateProjection Candidate,
    RuleEnvironmentImpactHypothesisProjection ImpactHypothesis);

public sealed record KarmaForgeDiscoveryArtifact(
    string Content,
    string ContentType,
    string FileName,
    string ArtifactKind,
    string DestinationRoute,
    string SourceRef);

public sealed record HouseRuleDemandPacketProjection(
    string Id,
    string Title,
    KarmaForgeSourceProjection Source,
    KarmaForgeUserWordsProjection UserWords,
    KarmaForgeInterpretedNeedProjection InterpretedNeed,
    IReadOnlyList<string> AffectedDomains,
    IReadOnlyList<string> DesiredScope,
    IReadOnlyList<string> LikelyChummerObjects,
    IReadOnlyList<string> PossibleBlackLedgerObjects,
    KarmaForgeTrustRequirementsProjection TrustRequirements,
    KarmaForgePortabilityRequirementsProjection PortabilityRequirements,
    KarmaForgePrioritySignalsProjection PrioritySignals,
    KarmaForgeClassificationProjection Classification,
    IReadOnlyList<string> NextSteps,
    KarmaForgeOperatorNotesProjection OperatorNotes);

public sealed record KarmaForgeSourceProjection(
    string IntakeChannel,
    string CanonicalLane,
    string RespondentRole,
    string Edition,
    string TableType,
    string TrackKey,
    string InterviewTrack,
    string RuleCategory,
    string Severity,
    string InterviewRef,
    string ConsentRef,
    IReadOnlyList<KarmaForgeExternalStageProjection> ExternalStages,
    IReadOnlyList<JourneyProofEventRef> JourneyProofEventRefs);

public sealed record KarmaForgeExternalStageProjection(
    string StageKey,
    string PublicLabel,
    string ProviderLabel,
    string ReceiptId,
    string Boundary,
    string Status,
    string Summary,
    string? ActionHref,
    string? ActionLabel);

public sealed record KarmaForgeUserWordsProjection(
    string Summary,
    string CurrentWorkaround);

public sealed record KarmaForgeInterpretedNeedProjection(
    string Summary,
    string Confidence);

public sealed record KarmaForgeTrustRequirementsProjection(
    bool PlayerVisibleBeforeJoin,
    bool BuildDiffRequired,
    bool RollbackRequired,
    bool ApprovalRequired,
    bool ReceiptRequired);

public sealed record KarmaForgePortabilityRequirementsProjection(
    bool CrossDeviceRestore,
    bool PackageFingerprintRequired);

public sealed record KarmaForgePrioritySignalsProjection(
    int BlockerScore,
    string FrequencySignal,
    int ShareabilityScore,
    string ImplementationRisk,
    string MonetizationRelevance);

public sealed record KarmaForgeClassificationProjection(
    string CurrentStatus,
    bool DecisionNeeded,
    string CandidateDecision,
    string CandidateDecisionMeaning,
    string ProposedRoute);

public sealed record KarmaForgeOperatorNotesProjection(
    string FeedbackPrompt,
    string ImpactNotes,
    string ShareabilityNotes);

public sealed record KarmaForgeCandidateProjection(
    string Id,
    string Title,
    string LinkedPacketId,
    string TrackKey,
    string TrackTitle,
    string CandidateDecision,
    string CandidateDecisionMeaning,
    string ProposedRoute,
    bool GovernorDecisionRequired,
    string Confidence,
    KarmaForgePrioritySignalsProjection PrioritySignals);

public sealed record RuleEnvironmentImpactHypothesisProjection(
    string Id,
    string Title,
    string Summary,
    IReadOnlyList<string> AffectedDomains,
    IReadOnlyList<string> LikelyObjects,
    IReadOnlyList<string> PossibleBlackLedgerObjects,
    IReadOnlyList<string> TrustPressure,
    IReadOnlyList<string> PortabilityPressure,
    IReadOnlyList<string> RolloutScope,
    string ComparisonSurface,
    string PlayerVisibility,
    string RollbackSurface);

    
