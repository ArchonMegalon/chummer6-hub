using System.Security.Cryptography;
using System.Text;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class PublicSignalToCanonPacketService
{
    private const string DownloadClaimLaunchJourneyKey = "download_claim_launch_update";
    private const string ProductLiftJourneyKey = "productlift_to_ship";
    private const string KarmaForgeJourneyKey = "karma_forge_discovery";

    private readonly PublicReleaseManifestService _releases;

    public PublicSignalToCanonPacketService(PublicReleaseManifestService releases)
    {
        _releases = releases;
    }

    public SignalToCanonPacketBundle Build(
        SupportCaseProjection? trackedSupportCase = null,
        string locale = "en-US")
    {
        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        DateTimeOffset now = DateTimeOffset.UtcNow;

        return new SignalToCanonPacketBundle(
            BuiltAtUtc: now,
            Packets:
            [
                BuildFeedbackPacket(manifest, now, locale),
                BuildRoadmapPacket(manifest, now, locale),
                BuildChangelogPacket(manifest, now, locale),
                BuildSupportPacket(manifest, trackedSupportCase, now, locale),
                BuildProductLiftSignalPacket(manifest, now, locale),
                BuildKattebSignalPacket(manifest, now, locale),
                BuildClickRankSignalPacket(manifest, now, locale),
                BuildMetaSurveySignalPacket(manifest, now, locale),
                BuildSignalIntakePacket(manifest, now, locale)
            ]);
    }

    private static SignalToCanonPacketProjection BuildFeedbackPacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-feedback", manifest.Version),
            SurfaceId: "feedback",
            Route: "/participate",
            DestinationRoute: "/participate",
            SourceKind: "productlift_feedback",
            SourceClassification: "public_feedback_signal",
            Audience: "public_feedback",
            ClaimSensitivity: "proposal_only",
            Owner: "product_governor",
            DecisionAuthority: "governed_signal_triage",
            UpstreamPatchRequirement: "accepted_feedback_must_patch_chummer_owned_source_before_public_output_changes",
            NoChangeRationalePolicy: "allowed_only_with_explicit_governor_or_design_rationale",
            CloseoutPosture: "Accepted feedback patches Chummer-owned source, metadata config, registry YAML, or guide content before regeneration.",
            Summary: "Public feedback stays on Participate instead of changing release status by itself.",
            EvidenceLines:
            [
                "/participate is the reviewed public feedback surface.",
                "Public feedback may propose demand, but product decisions still need review.",
                "Accepted improvements patch reviewed public content before regenerated output is published."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "productlift_idea_clustered",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "/participate",
                    summary: "Public feedback clusters must resolve into a first-party review step before queue or design interpretation.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static SignalToCanonPacketProjection BuildRoadmapPacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-roadmap", manifest.Version),
            SurfaceId: "roadmap",
            Route: "/roadmap",
            DestinationRoute: "/horizons?source=roadmap#public-roadmap-projection",
            SourceKind: "productlift_roadmap_projection",
            SourceClassification: "public_projection_signal",
            Audience: "public_roadmap_followers",
            ClaimSensitivity: "projection_only",
            Owner: "chummer6_design",
            DecisionAuthority: "source_backed_roadmap_review",
            UpstreamPatchRequirement: "projection_changes_must_follow_reviewed_design_or_release_source",
            NoChangeRationalePolicy: "allowed_only_when_public_projection_stays_honest_about_live_state",
            CloseoutPosture: "Roadmap cards stay projection-only until shipped status, source patches, or release records close the gap.",
            Summary: "Roadmap surfaces can project direction, but they do not become implementation, release, or support authority.",
            EvidenceLines:
            [
                "/roadmap redirects to the horizons roadmap projection.",
                "Visible roadmap maturity must stay source-backed and reuse the shared public status presenter.",
                "Support remains the honest escalation path when a roadmap item and the live surface still diverge."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "productlift_idea_clustered",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "/roadmap",
                    summary: "Roadmap projection stays downstream of Chummer-owned ProductLift clustering and decision review.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static SignalToCanonPacketProjection BuildChangelogPacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-changelog", manifest.Version),
            SurfaceId: "changelog",
            Route: "/changelog",
            DestinationRoute: "/now?source=changelog#public-shipped-closeout",
            SourceKind: "productlift_shipped_closeout",
            SourceClassification: "shipped_closeout_signal",
            Audience: "release_followers",
            ClaimSensitivity: "shipped_only",
            Owner: "release_ops",
            DecisionAuthority: "published_release_closeout",
            UpstreamPatchRequirement: "closeout_claims_must_match_release_status_and_public_downloads",
            NoChangeRationalePolicy: "disallowed_for_shipped_claims_without_release_status",
            CloseoutPosture: "Changelog entries stay tied to shipped closeout and published release status instead of open roadmap intent.",
            Summary: "The public changelog is a shipped-closeout projection, not a backlog promise or private staging note.",
            EvidenceLines:
            [
                "/changelog redirects to the public shipped-closeout anchor on /now.",
                "Release status, installer shelf, and shipped-closeout language must agree before the public changelog can claim delivery.",
                "Unshipped or support-only fixes must not be promoted into the public changelog."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "voter_notified",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "/changelog",
                    summary: "Shipped closeout must stay attached to the first-party voter notification record before public delivery claims resolve.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static SignalToCanonPacketProjection BuildSupportPacket(
        PublicReleaseManifestDto manifest,
        SupportCaseProjection? trackedSupportCase,
        DateTimeOffset now,
        string locale)
    {
        string summary = trackedSupportCase is null
            ? "The public support surface routes bugs, account questions, and private feedback into first-party support intake."
            : $"Support case {trackedSupportCase.CaseId} keeps the public contact path first-party instead of disappearing into email.";
        return new SignalToCanonPacketProjection(
            PacketId: StableId("signal-support", trackedSupportCase?.CaseId ?? manifest.Version),
            SurfaceId: "support",
            Route: "/contact",
            DestinationRoute: trackedSupportCase is null
                ? "/contact"
                : $"/contact/submitted/{Uri.EscapeDataString(trackedSupportCase.CaseId)}",
            SourceKind: "support_case_public_web",
            SourceClassification: "private_support_signal",
            Audience: "support_reporters",
            ClaimSensitivity: "support_private",
            Owner: "support_ops",
            DecisionAuthority: "case_triage_and_release_followthrough",
            UpstreamPatchRequirement: "support_findings_must_patch_help_release_or_runtime_source_before_public_help_copy_changes",
            NoChangeRationalePolicy: "allowed_only_when_private_case_context_does_not_require_public_claim_changes",
            CloseoutPosture: "Public support reports become support cases, and closeout stays attached to first-party account or reply-email follow-through.",
            Summary: summary,
            EvidenceLines:
            [
                "/contact is the first-party public support and private-feedback intake route.",
                "Support routes keep the case id, status, and release follow-through visible instead of redirecting to a private vendor queue.",
                trackedSupportCase is null
                    ? "Guest support still stays first-party through support-case intake."
                    : $"Support case {trackedSupportCase.CaseId} is the support-side SignalToCanon packet anchor."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "download_started",
                    journeyKey: DownloadClaimLaunchJourneyKey,
                    sourceRef: trackedSupportCase?.CaseId ?? "/contact",
                    summary: "Support escalation on install and release surfaces stays linked to a first-party install record before public help copy changes.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            CaseId: trackedSupportCase?.CaseId);
    }

    private static SignalToCanonPacketProjection BuildProductLiftSignalPacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-productlift", manifest.Version),
            SurfaceId: "productlift_signal",
            Route: "/participate",
            DestinationRoute: "/participate",
            SourceKind: "productlift_feedback_and_closeout",
            SourceClassification: "public_feedback_signal",
            Audience: "public_feedback_followers",
            ClaimSensitivity: "proposal_only",
            Owner: "product_governor",
            DecisionAuthority: "signal_cluster_review",
            UpstreamPatchRequirement: "accepted_findings_must_patch_chummer_owned_source_before_public_feedback_projection_changes",
            NoChangeRationalePolicy: "required_for_review_threshold_items_that_do_not_change_source_or_release_state",
            CloseoutPosture: "Repeated ProductLift findings can synthesize queue candidates and shipped closeout, but only after Chummer-owned source and status move first.",
            Summary: "ProductLift signal is classified before it becomes queue, roadmap, or closeout input.",
            EvidenceLines:
            [
                "Public feedback boards collect demand, but release decisions still live in Chummer routes and release status.",
                "Review-threshold ideas need either source-backed movement or an explicit no-change rationale.",
                "Voter closeout must cite shipped status before public delivery can claim resolution."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "productlift_idea_clustered",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "productlift_signal",
                    summary: "ProductLift demand stays downstream of a first-party clustering review before queue or roadmap interpretation."),
                BuildJourneyProofEventRef(
                    eventKey: "voter_notified",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "productlift_signal",
                    summary: "Any shipped closeout tied to ProductLift must resolve through the bounded voter notification record.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static SignalToCanonPacketProjection BuildKattebSignalPacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-katteb", manifest.Version),
            SurfaceId: "katteb_signal",
            Route: "/help",
            DestinationRoute: "/participate?source=help#public-feedback",
            SourceKind: "katteb_public_content_review",
            SourceClassification: "content_improvement",
            Audience: "public_guide_readers",
            ClaimSensitivity: "source_sensitive_copy",
            Owner: "chummer6_design",
            DecisionAuthority: "approved_source_packet_review",
            UpstreamPatchRequirement: "accepted_katteb_recommendations_must_patch_design_or_public_guide_source_before_regeneration",
            NoChangeRationalePolicy: "required_when_readability_or_claim_changes_are_rejected",
            CloseoutPosture: "Guide and article improvements stay upstream-first; generated output only changes after approved source packets move.",
            Summary: "Katteb findings are content-improvement proposals, not direct edits to public output.",
            EvidenceLines:
            [
                "Guide optimization can draft from approved source packets only.",
                "Accepted copy changes must land in reviewed source registries before public regeneration.",
                "Human review remains required before publication."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "productlift_idea_clustered",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "katteb_signal",
                    summary: "Public content changes can only graduate after a reviewed Chummer source packet or clustered demand review exists.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static SignalToCanonPacketProjection BuildClickRankSignalPacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-clickrank", manifest.Version),
            SurfaceId: "clickrank_signal",
            Route: "/downloads",
            DestinationRoute: "/participate?source=downloads#public-feedback",
            SourceKind: "clickrank_visibility_audit",
            SourceClassification: "site_visibility_audit",
            Audience: "public_launch_operators",
            ClaimSensitivity: "technical_visibility_only",
            Owner: "chummer6_design",
            DecisionAuthority: "search_visibility_review",
            UpstreamPatchRequirement: "critical_clickrank_findings_must_patch_chummer_owned_source_or_record_explicit_no_change_rationale",
            NoChangeRationalePolicy: "required_for_unfixed_launch_critical_findings",
            CloseoutPosture: "Visibility audits can recommend crawl, metadata, schema, and navigation fixes, but public copy only changes through reviewed Chummer source or explicit no-change review.",
            Summary: "ClickRank findings are classified visibility work, not direct authority over public claims or route posture.",
            EvidenceLines:
            [
                "Critical launch-page findings need a source fix or explicit no-change rationale.",
                "Keyword opportunities should be classified as technical, content, source-sensitive, navigation, schema, or blocked work.",
                "Search audits must not leave stale release, roadmap, or support claims behind."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "productlift_idea_clustered",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "clickrank_signal",
                    summary: "Search and visibility findings must attach to a Chummer-owned review packet before Product Governor interpretation.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static SignalToCanonPacketProjection BuildMetaSurveySignalPacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-metasurvey", manifest.Version),
            SurfaceId: "metasurvey_signal",
            Route: "/participate",
            DestinationRoute: "/participate/karma-forge",
            SourceKind: "survey_validation_signal",
            SourceClassification: "quant_validation",
            Audience: "followup_participants",
            ClaimSensitivity: "ranking_only",
            Owner: "product_governor",
            DecisionAuthority: "signal_cluster_review",
            UpstreamPatchRequirement: "survey_results_must_feed_chummer_owned_packets_before_queue_or_closeout_changes",
            NoChangeRationalePolicy: "required_when_survey_signal_does_not_justify_product_or_copy_changes",
            CloseoutPosture: "Survey ranking can validate repeated demand, but it never becomes priority or a release decision without packet and design review.",
            Summary: "MetaSurvey-style followup remains a ranking signal, not the priority decision itself.",
            EvidenceLines:
            [
                "Survey output can strengthen a repeated signal cluster but cannot set the backlog by itself.",
                "Quant validation must flow back into reviewed Chummer packets before decisions move.",
                "Public followthrough stays on first-party Participate and KARMA FORGE paths."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "karma_interview_completed",
                    journeyKey: KarmaForgeJourneyKey,
                    sourceRef: "metasurvey_signal",
                    summary: "Quant validation remains downstream of a first-party KARMA FORGE interview and packet chain before decisions move."),
                BuildJourneyProofEventRef(
                    eventKey: "karma_demand_packet_created",
                    journeyKey: KarmaForgeJourneyKey,
                    sourceRef: "metasurvey_signal",
                    summary: "Survey ranking must re-enter a reviewed Chummer demand packet before product interpretation.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static SignalToCanonPacketProjection BuildSignalIntakePacket(
        PublicReleaseManifestDto manifest,
        DateTimeOffset now,
        string locale)
        => new(
            PacketId: StableId("signal-intake", manifest.Version),
            SurfaceId: "signal_intake",
            Route: "/participate",
            DestinationRoute: "/participate",
            SourceKind: "productlift_katteb_clickrank_support_survey",
            SourceClassification: "classified_signal_intake",
            Audience: "public_signal_intake",
            ClaimSensitivity: "classified_signal_only",
            Owner: "product_governor",
            DecisionAuthority: "signal_cluster_review",
            UpstreamPatchRequirement: "repeated_clusters_must_become_source_patch_or_queue_candidates_through_chummer_owned_review",
            NoChangeRationalePolicy: "required_when_repeated_clusters_do_not_change_queue_or_source",
            CloseoutPosture: "Repeated public-signal clusters can synthesize queue candidates, but design and product review remain the decision point.",
            Summary: "Participate is the intake page where public feedback, survey, and hosted signal sources become classified product signals.",
            EvidenceLines:
            [
                "/participate is the hosted intake lane for public-board, survey, and adjacent public signal sources.",
                "Signal packets classify source, audience, claim sensitivity, owner, decision, and closeout posture before any queue synthesis happens.",
                "Repeated clusters may create queue candidates, but the packet is not a product decision by itself."
            ],
            JourneyProofEventRefs:
            [
                BuildJourneyProofEventRef(
                    eventKey: "productlift_idea_clustered",
                    journeyKey: ProductLiftJourneyKey,
                    sourceRef: "signal_intake",
                    summary: "Repeated public feedback must become a clustered Chummer packet before roadmap or shipped interpretation."),
                BuildJourneyProofEventRef(
                    eventKey: "karma_demand_packet_created",
                    journeyKey: KarmaForgeJourneyKey,
                    sourceRef: "signal_intake",
                    summary: "Discovery and follow-up demand must become a Chummer-owned KARMA FORGE packet before deeper product review.")
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static JourneyProofEventRef BuildJourneyProofEventRef(
        string eventKey,
        string journeyKey,
        string sourceRef,
        string summary)
        => new(
            EventKey: eventKey,
            JourneyKey: journeyKey,
            SourceRef: sourceRef,
            Summary: summary);

    private static string StableId(string prefix, string seed)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes($"{prefix}:{seed}"));
        return $"{prefix}:{Convert.ToHexString(digest[..8]).ToLowerInvariant()}";
    }
}
