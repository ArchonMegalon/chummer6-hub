using System.Security.Cryptography;
using System.Text;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class PublicSignalToCanonPacketService
{
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
            Route: "/feedback",
            DestinationRoute: "/participate?productlift=feedback#productlift-feedback",
            SourceKind: "productlift_feedback",
            Audience: "public_feedback",
            ClaimSensitivity: "proposal_only",
            Owner: "product_governor",
            DecisionAuthority: "governed_signal_triage",
            CloseoutPosture: "Accepted feedback patches Chummer-owned source, metadata config, registry YAML, or guide content before regeneration.",
            Summary: "Public feedback stays bounded to the governed Participate/ProductLift lane instead of becoming shipping truth by itself.",
            EvidenceLines:
            [
                "/feedback redirects to the governed Participate feedback anchor.",
                "Public feedback may propose demand, but design and Product Governor remain the canon decision authority.",
                "Accepted improvements patch source-backed public content before any regenerated output is trusted."
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
            DestinationRoute: "/horizons?productlift=roadmap#productlift-roadmap-projection",
            SourceKind: "productlift_roadmap_projection",
            Audience: "public_roadmap_followers",
            ClaimSensitivity: "projection_only",
            Owner: "chummer6_design",
            DecisionAuthority: "source_backed_roadmap_review",
            CloseoutPosture: "Roadmap cards stay projection-only until shipped proof, source patches, or release receipts close the gap.",
            Summary: "Roadmap surfaces can project direction, but they do not become implementation, release, or support authority.",
            EvidenceLines:
            [
                "/roadmap redirects to the horizons roadmap projection.",
                "Visible roadmap maturity must stay source-backed and reuse the shared public status presenter.",
                "Support remains the honest escalation path when a roadmap item and the live surface still diverge."
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
            DestinationRoute: "/now?productlift=changelog#productlift-shipped-closeout",
            SourceKind: "productlift_shipped_closeout",
            Audience: "release_followers",
            ClaimSensitivity: "shipped_only",
            Owner: "release_ops",
            DecisionAuthority: "published_release_closeout",
            CloseoutPosture: "Changelog entries stay tied to shipped closeout and published release proof instead of open roadmap intent.",
            Summary: "The public changelog is a shipped-closeout projection, not a backlog promise or private staging note.",
            EvidenceLines:
            [
                "/changelog redirects to the public shipped-closeout anchor on /now.",
                "Release proof, installer shelf, and shipped-closeout language must agree before the public changelog can claim delivery.",
                "Unshipped or support-only fixes must not be promoted into changelog truth."
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
            ? "The public support surface routes bugs, account questions, and private feedback into first-party tracked case intake."
            : $"Tracked support case {trackedSupportCase.CaseId} proves the public contact path becomes a governed first-party case instead of disappearing into email.";
        return new SignalToCanonPacketProjection(
            PacketId: StableId("signal-support", trackedSupportCase?.CaseId ?? manifest.Version),
            SurfaceId: "support",
            Route: "/contact",
            DestinationRoute: trackedSupportCase is null
                ? "/contact"
                : $"/contact/submitted/{Uri.EscapeDataString(trackedSupportCase.CaseId)}",
            SourceKind: "support_case_public_web",
            Audience: "support_reporters",
            ClaimSensitivity: "support_private",
            Owner: "support_ops",
            DecisionAuthority: "case_triage_and_release_followthrough",
            CloseoutPosture: "Public support reports become governed tracked cases, and closeout stays attached to first-party account or reply-email follow-through.",
            Summary: summary,
            EvidenceLines:
            [
                "/contact is the first-party public support and private-feedback intake route.",
                "Tracked support routes keep the case id, status, and release follow-through visible instead of redirecting to a private vendor queue.",
                trackedSupportCase is null
                    ? "Guest support still stays first-party and bounded by tracked case intake."
                    : $"Tracked case {trackedSupportCase.CaseId} is the support-side SignalToCanon packet anchor."
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version,
            CaseId: trackedSupportCase?.CaseId);
    }

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
            Audience: "public_signal_intake",
            ClaimSensitivity: "classified_signal_only",
            Owner: "product_governor",
            DecisionAuthority: "signal_cluster_review",
            CloseoutPosture: "Repeated public-signal clusters can synthesize bounded queue candidates, but design and Product Governor remain canon authority.",
            Summary: "Participate is the governed intake lane where public feedback, survey, and hosted signal sources become classified SignalToCanon packets.",
            EvidenceLines:
            [
                "/participate is the hosted intake lane for ProductLift, survey, and adjacent public signal sources.",
                "Signal packets classify source, audience, claim sensitivity, owner, decision, and closeout posture before any queue synthesis happens.",
                "Fleet may synthesize bounded queue candidates from repeated clusters, but the packet is not canon by itself."
            ],
            EmittedAtUtc: now,
            Locale: locale,
            ReleaseChannel: manifest.Channel,
            ReleaseVersion: manifest.Version);

    private static string StableId(string prefix, string seed)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes($"{prefix}:{seed}"));
        return $"{prefix}:{Convert.ToHexString(digest[..8]).ToLowerInvariant()}";
    }
}
