using System.Security.Cryptography;
using Chummer.Contracts.Receipts;

namespace Chummer.Run.Api.Services;

public sealed record PublicPackageClassSummary(
    string Key,
    string Label,
    string Summary,
    IReadOnlyList<string> Rules);

public sealed record PublicPackageDefinition(
    string PackageId,
    string Title,
    string Summary,
    string PackageClassKey,
    string PackageClassLabel,
    string StatusLabel,
    IReadOnlyList<string> CompatibilityNotes,
    IReadOnlyList<string> GovernanceNotes,
    string EvidenceSummary,
    string PrimaryActionLabel,
    string PrimaryActionHref,
    string AccountSummary,
    string OperatorSummary);

public sealed record PublicPackageReceipt(
    string ReceiptId,
    string PackageId,
    string ActionKind,
    string SubjectId,
    string ActorLabel,
    DateTimeOffset RecordedAtUtc,
    string RouteSummary,
    ReceiptEnvelope? Envelope = null);

public sealed class PublicPackageCatalogService
{
    private static readonly IReadOnlyList<PublicPackageClassSummary> PackageClasses =
    [
        new(
            "desktop_install_package",
            "Desktop install package",
            "The build people install on a workstation, laptop, or travel machine.",
            [
                "Public acquisition starts on Downloads, not a raw binary shelf.",
                "Compatibility is explicit by channel, platform, and guided handoff posture.",
                "Account value starts after install with claim, recovery, and support continuity."
            ]),
        new(
            "rules_source_package",
            "Rules and source package",
            "Rules coverage and explainable source material that changes what the runtime can prove.",
            [
                "Compatibility binds to rules runtime, explain receipts, and import posture.",
                "Approval and rollback posture stay explicit before broader adoption claims.",
                "Public parity claims stay blocked until proof receipts say otherwise."
            ]),
        new(
            "house_rule_package",
            "House-rule amendment package",
            "Table or campaign-specific amendments that must stay governed and reversible.",
            [
                "Scope starts at table or campaign, not at the public front door.",
                "Rollback, portability, and disclosure posture stay attached to the package.",
                "Community demand can inform the package, but does not directly publish it."
            ]),
        new(
            "artifact_media_package",
            "Artifact and media package",
            "Artifacts, briefings, primers, and preview media that travel with provenance.",
            [
                "Artifacts never become the system of record for rules or account truth.",
                "Publication trust, provenance, and visibility posture stay attached.",
                "Preview media can support proof, but cannot outrank live product routes."
            ]),
        new(
            "community_proposal_package",
            "Community proposal package",
            "A governed proposal that stays in first-party discovery until compatibility and moderation are clear.",
            [
                "First-party vote and follow receipts stay inside Chummer-owned routes.",
                "Moderation, duplicate handling, and compatibility review block fast-publish folklore.",
                "Proposal posture must stay honest about research versus release readiness."
            ])
    ];

    private readonly object _gate = new();
    private readonly Dictionary<string, PublicPackageDefinition> _packages;
    private readonly Dictionary<string, PublicPackageReceipt> _receiptsById = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, string> _receiptIdByActorAction = new(StringComparer.OrdinalIgnoreCase);

    public PublicPackageCatalogService()
    {
        _packages = SeedPackages().ToDictionary(package => package.PackageId, StringComparer.OrdinalIgnoreCase);
    }

    public IReadOnlyList<PublicPackageClassSummary> ListPackageClasses() => PackageClasses;

    public IReadOnlyList<PublicPackageDefinition> ListPackages()
    {
        lock (_gate)
        {
            return _packages.Values
                .OrderBy(package => package.Title, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    public PublicPackageDefinition? FindPackage(string packageId)
    {
        if (string.IsNullOrWhiteSpace(packageId))
        {
            return null;
        }

        lock (_gate)
        {
            return _packages.TryGetValue(packageId.Trim(), out PublicPackageDefinition? package)
                ? package
                : null;
        }
    }

    public PublicPackageReceipt RecordVote(string packageId, string subjectId, string actorLabel)
        => RecordReceipt(packageId, "vote", subjectId, actorLabel);

    public PublicPackageReceipt RecordFollow(string packageId, string subjectId, string actorLabel)
        => RecordReceipt(packageId, "follow", subjectId, actorLabel);

    public PublicPackageReceipt RecordRevoke(string packageId, string actionKind, string subjectId, string actorLabel)
    {
        PublicPackageDefinition package = FindPackage(packageId)
            ?? throw new KeyNotFoundException($"Unknown package id '{packageId}'.");
        string normalizedActionKind = NormalizeActionKind(actionKind);
        string normalizedSubjectId = NormalizeRequired(subjectId, nameof(subjectId));
        string normalizedActorLabel = NormalizeRequired(actorLabel, nameof(actorLabel));
        string actorActionKey = BuildActorActionKey(package.PackageId, normalizedActionKind, normalizedSubjectId);

        lock (_gate)
        {
            if (!_receiptIdByActorAction.TryGetValue(actorActionKey, out string? existingReceiptId)
                || !_receiptsById.TryGetValue(existingReceiptId, out PublicPackageReceipt? existingReceipt))
            {
                throw new InvalidOperationException($"No active {normalizedActionKind} receipt exists for package '{package.PackageId}'.");
            }

            _receiptIdByActorAction.Remove(actorActionKey);
            DateTimeOffset now = DateTimeOffset.UtcNow;
            string receiptId = $"pkg_revoke_{RandomHex(4)}";
            PublicPackageReceipt created = new(
                ReceiptId: receiptId,
                PackageId: package.PackageId,
                ActionKind: $"revoke_{normalizedActionKind}",
                SubjectId: normalizedSubjectId,
                ActorLabel: normalizedActorLabel,
                RecordedAtUtc: now,
                RouteSummary: $"Package {normalizedActionKind} revoked for {package.Title}.",
                Envelope: ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "public_package",
                    ownerScope: "public.package_catalog",
                    exposureClass: ReceiptExposureClasses.PublicSafe,
                    evidenceRef: receiptId,
                    reviewState: $"revoke_{normalizedActionKind}"));
            _receiptsById[receiptId] = created;
            return created;
        }
    }

    public PublicPackageReceipt? FindReceipt(string receiptId)
    {
        if (string.IsNullOrWhiteSpace(receiptId))
        {
            return null;
        }

        lock (_gate)
        {
            return _receiptsById.TryGetValue(receiptId.Trim(), out PublicPackageReceipt? receipt)
                ? receipt
                : null;
        }
    }

    public PublicPackageReceipt? FindLatestReceiptForSubject(string packageId, string actionKind, string subjectId)
    {
        string actorActionKey = BuildActorActionKey(packageId, actionKind, subjectId);
        lock (_gate)
        {
            return _receiptIdByActorAction.TryGetValue(actorActionKey, out string? receiptId)
                && _receiptsById.TryGetValue(receiptId, out PublicPackageReceipt? receipt)
                    ? receipt
                    : null;
        }
    }

    public IReadOnlyList<PublicPackageReceipt> ListReceiptsForPackage(string packageId, int take = 12)
    {
        if (string.IsNullOrWhiteSpace(packageId) || take <= 0)
        {
            return Array.Empty<PublicPackageReceipt>();
        }

        lock (_gate)
        {
            return _receiptsById.Values
                .Where(receipt => string.Equals(receipt.PackageId, packageId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(take)
                .ToArray();
        }
    }

    public IReadOnlyList<PublicPackageReceipt> ListReceiptsForSubject(string subjectId, int take = 12)
    {
        if (string.IsNullOrWhiteSpace(subjectId) || take <= 0)
        {
            return Array.Empty<PublicPackageReceipt>();
        }

        lock (_gate)
        {
            return _receiptsById.Values
                .Where(receipt => string.Equals(receipt.SubjectId, subjectId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(take)
                .ToArray();
        }
    }

    public IReadOnlyList<PublicPackageReceipt> ListRecentReceipts(int take = 12)
    {
        if (take <= 0)
        {
            return Array.Empty<PublicPackageReceipt>();
        }

        lock (_gate)
        {
            return _receiptsById.Values
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(take)
                .ToArray();
        }
    }

    public int CountUniqueReceipts(string packageId, string actionKind)
    {
        if (string.IsNullOrWhiteSpace(packageId) || string.IsNullOrWhiteSpace(actionKind))
        {
            return 0;
        }

        string normalizedActionKind = NormalizeActionKind(actionKind);
        lock (_gate)
        {
            return _receiptIdByActorAction.Keys.Count(key =>
                key.StartsWith($"{packageId.Trim().ToLowerInvariant()}::{normalizedActionKind}::", StringComparison.OrdinalIgnoreCase));
        }
    }

    private PublicPackageReceipt RecordReceipt(string packageId, string actionKind, string subjectId, string actorLabel)
    {
        PublicPackageDefinition package = FindPackage(packageId)
            ?? throw new KeyNotFoundException($"Unknown package id '{packageId}'.");
        string normalizedActionKind = NormalizeActionKind(actionKind);
        string normalizedSubjectId = NormalizeRequired(subjectId, nameof(subjectId));
        string normalizedActorLabel = NormalizeRequired(actorLabel, nameof(actorLabel));
        string actorActionKey = BuildActorActionKey(package.PackageId, normalizedActionKind, normalizedSubjectId);

        lock (_gate)
        {
            if (_receiptIdByActorAction.TryGetValue(actorActionKey, out string? existingReceiptId)
                && _receiptsById.TryGetValue(existingReceiptId, out PublicPackageReceipt? existingReceipt))
            {
                return existingReceipt;
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            string receiptId = $"pkg_{normalizedActionKind}_{RandomHex(4)}";
            PublicPackageReceipt created = new(
                ReceiptId: receiptId,
                PackageId: package.PackageId,
                ActionKind: normalizedActionKind,
                SubjectId: normalizedSubjectId,
                ActorLabel: normalizedActorLabel,
                RecordedAtUtc: now,
                RouteSummary: normalizedActionKind == "vote"
                    ? $"Package vote recorded for {package.Title}."
                    : $"Package follow recorded for {package.Title}.",
                Envelope: ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "public_package",
                    ownerScope: "public.package_catalog",
                    exposureClass: ReceiptExposureClasses.PublicSafe,
                    evidenceRef: receiptId,
                    reviewState: normalizedActionKind));
            _receiptsById[receiptId] = created;
            _receiptIdByActorAction[actorActionKey] = receiptId;
            return created;
        }
    }

    private static string NormalizeActionKind(string actionKind)
        => actionKind.Trim().ToLowerInvariant() switch
        {
            "vote" => "vote",
            "follow" => "follow",
            _ => throw new ArgumentOutOfRangeException(nameof(actionKind), actionKind, "Supported package actions are vote and follow.")
        };

    private static string NormalizeRequired(string value, string name)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException($"{name} is required.", name);
        }

        return value.Trim();
    }

    private static string BuildActorActionKey(string packageId, string actionKind, string subjectId)
        => $"{packageId.Trim().ToLowerInvariant()}::{actionKind.Trim().ToLowerInvariant()}::{subjectId.Trim().ToLowerInvariant()}";

    private static string RandomHex(int byteCount)
        => Convert.ToHexString(RandomNumberGenerator.GetBytes(byteCount)).ToLowerInvariant();

    private static IReadOnlyList<PublicPackageDefinition> SeedPackages()
        =>
        [
            new(
                "desktop-preview",
                "Current preview desktop package",
                "The current desktop install package with the calmest first-run and account handoff posture.",
                "desktop_install_package",
                "Desktop install package",
                "Live now",
                [
                    "Matches the current release channels on Downloads across Windows, macOS, and Linux.",
                    "Guided claim, recovery, and install help stay tied to the same published build instead of a separate account-only binary.",
                    "The public package route explains the package class; Downloads still owns the actual acquisition decision."
                ],
                [
                    "Public acquisition starts at /downloads and the package browser must not compete with that shelf.",
                    "Account value begins after install through claim, recovery, updates, and support continuity.",
                    "Release truth still lives on status, downloads, and the release proof rails."
                ],
                "Downloads, status, and linked-install history already point here.",
                "Open downloads",
                "/downloads",
                "Track the linked install, recovery state, and support history from the account package rail.",
                "Keep this package as the public install anchor and compatibility reference."),
            new(
                "sr5-rules-core",
                "SR5 rules coverage package",
                "The current rules-and-source package for the explainable SR5 coverage that the proof view can already inspect.",
                "rules_source_package",
                "Rules and source package",
                "Inspectable",
                [
                    "Binds to the deterministic rules runtime, explanation trail, and current release status view.",
                    "Compatibility posture depends on the current explain receipt and import/export boundaries, not on route existence alone.",
                    "Public detail can point to current availability, but cannot overstate overall ruleset seriousness."
                ],
                [
                    "Proof must stay attached before broader parity language becomes public copy.",
                    "Rollback and boundary posture stay explicit when this package changes explainable rules behavior.",
                    "The package browser shows compatibility and status; it does not replace the rules proof audit."
                ],
                "The current release status view already points to the explanation trail and live rules posture.",
                "Open what works today",
                "/now#real-rules-truth",
                "Account package tracking keeps follows and votes attached to the same signed-in return path.",
                "Treat this package as proof-backed rules coverage, not as a blanket parity claim."),
            new(
                "campaign-amend-pack",
                "Campaign amendment package",
                "A governed table-scoped amendment package for house rules, return-path notes, and rollback-safe scope decisions.",
                "house_rule_package",
                "House-rule amendment package",
                "Preview lane",
                [
                    "Compatibility starts at table or campaign scope before broader community rollout.",
                    "Portable exchange, approvals, and rollback posture stay attached to the same package summary.",
                    "The public route explains what the package class means before any install or publication decision."
                ],
                [
                    "KARMA FORGE discovery and campaign approvals must exist before a broader release claim.",
                    "Private table context and spoilers stay out of public package receipts.",
                    "Rollback, portability, and user-visible scope remain explicit even when the package starts as a community suggestion."
                ],
                "KARMA FORGE and campaign continuity docs already point to the need for governed package posture.",
                "Open KARMA FORGE",
                "/participate/karma-forge",
                "Account package tracking keeps the follow and approval trail visible next to support and campaign work.",
                "Operator review should treat this as governed discovery first, not a fast-publish lane."),
            new(
                "artifact-brief-bundle",
                "Artifact briefing bundle",
                "A provenance-bound artifact package for primers, briefings, recaps, and shared output bundles.",
                "artifact_media_package",
                "Artifact and media package",
                "Preview lane",
                [
                    "Compatibility depends on publication trust, artifact shelf posture, and provenance receipts.",
                    "The package can travel across the proof view without becoming the source of product truth.",
                    "Creator, campaign, and public views can differ while the package lineage stays explicit."
                ],
                [
                    "Media and artifact packages may support proof, but they cannot replace route, install, or rules evidence.",
                    "Publication and moderation posture stay attached to the package before broader discovery claims.",
                    "Artifact detail and shelf routes remain the first-party surfaces for discovery and return."
                ],
                "The artifact shelf already proves that publication, recap, and preview outputs can stay first-party.",
                "Open artifacts",
                "/artifacts",
                "Account package tracking ties creator and continuity receipts back to the same return path.",
                "Keep artifact packages bounded by provenance and trust posture rather than media hype."),
            new(
                "community-proposal-sandbox",
                "Community proposal sandbox package",
                "A governed proposal package for ideas that need first-party clustering, compatibility review, and moderation before they become product work.",
                "community_proposal_package",
                "Community proposal package",
                "Research",
                [
                    "Compatibility stays advisory until first-party review promotes the proposal into a clearer package lane.",
                    "Public votes and follows can exist now without pretending the proposal is installable or approved.",
                    "The package route makes the governance boundary explicit before any roadmap or release language moves."
                ],
                [
                    "Moderation, duplicate handling, privacy, and package compatibility must stay inside Chummer-owned routes.",
                    "Follow receipts are first-party and should not leak external board or operator tooling names.",
                    "Research posture must remain honest even when interest is high."
                ],
                "The public participate and feedback rails already separate safe public signal from private support and install work.",
                "Open feedback",
                "/feedback",
                "Account package tracking keeps your follows and votes on the same signed-in rail as support and continuity.",
                "Treat this package as a governed proposal surface with explicit moderation and compatibility posture.")
        ];
}
