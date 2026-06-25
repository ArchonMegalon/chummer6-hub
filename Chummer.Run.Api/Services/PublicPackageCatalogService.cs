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
                "Get it from Downloads, not from a loose file shelf.",
                "Compatibility is clear by channel, platform, and account claim path.",
                "Account value starts after install with claim, recovery, and support continuity."
            ]),
        new(
            "rules_source_package",
            "Rules data package",
            "Rules coverage and explanation data that changes what Chummer can show.",
            [
                "Compatibility comes from the rules runtime, explanations, and import status.",
                "Changes need a clear review path before they are described as broadly ready.",
                "Parity claims stay quiet until the current status supports them."
            ]),
        new(
            "house_rule_package",
            "House-rule amendment package",
            "Table or campaign-specific amendments that must stay reviewed and reversible.",
            [
                "Scope starts at table or campaign, not at the public front door.",
                "Rollback, portability, and disclosure stay attached to the package.",
                "Community demand can inform the package, but does not directly publish it."
            ]),
        new(
            "artifact_media_package",
            "File and media package",
            "Briefings, primers, recaps, and media files that travel with a clear history.",
            [
                "Files never become the source for rules or account records.",
                "Publication status, history, and visibility stay attached.",
                "Preview media can support a page, but cannot outrank the working product routes."
            ]),
        new(
            "community_proposal_package",
            "Community proposal package",
            "A reviewed proposal that stays in Chummer until compatibility and moderation are clear.",
            [
                "Votes and follows stay inside Chummer pages.",
                "Moderation, duplicate handling, and compatibility review block fast-publish folklore.",
                "Proposal status must stay honest about research versus release readiness."
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
                "Current desktop installer",
                "The current desktop install path with the calmest first launch and account claim flow.",
                "desktop_install_package",
                "Desktop install package",
                "Live now",
                [
                    "Matches the current release channels on Downloads: public installers and platform notes stay on the downloads page.",
                    "Claim, recovery, and install help stay tied to the same published build instead of a separate account-only binary.",
                    "This page explains the choice. Downloads is still where you get the app."
                ],
                [
                    "Public download starts at /downloads.",
                    "Account value begins after install through claim, recovery, updates, and support continuity.",
                    "Status and Downloads remain the source of what is current."
                ],
                "Downloads, Status, and account claim history already point here.",
                "Open downloads",
                "/downloads",
                "Track the linked install, recovery state, and support history from your account page.",
                "Keep this package as the public install anchor and compatibility reference."),
            new(
                "sr5-rules-core",
                "SR5 rules data",
                "The current rules data for the SR5 coverage Chummer can explain today.",
                "rules_source_package",
                "Rules data package",
                "Inspectable",
                [
                    "Works with Chummer's rules engine, explanation path, and current release status view.",
                    "Compatibility depends on current explanations and import/export boundaries, not on route existence alone.",
                    "Public detail can point to current availability, but cannot overstate overall ruleset seriousness."
                ],
                [
                    "Current status must be visible before broader parity language becomes public copy.",
                    "Rollback and boundaries stay explicit when this package changes rules behavior.",
                    "This page shows compatibility and status; it does not replace rules review."
                ],
                "The current release status view already points to the explanation path and current rules state.",
                "Open current release",
                "/now",
                "Account package tracking keeps follows and votes attached to the same signed-in return path.",
                "Treat this package as current rules coverage, not as a blanket parity claim."),
            new(
                "campaign-amend-pack",
                "Campaign amendment package",
                "A table-scoped package for house rules, return notes, and reversible scope decisions.",
                "house_rule_package",
                "House-rule amendment package",
                "Preview",
                [
                    "Compatibility starts at table or campaign scope before broader community rollout.",
                    "Portable exchange, approvals, and rollback stay attached to the same package summary.",
                    "The public route explains what the package class means before any install or publication decision."
                ],
                [
                    "KARMA FORGE discovery and campaign approvals must exist before a broader release promise.",
                    "Private table context and spoilers stay out of public package history.",
                    "Rollback, portability, and user-visible scope remain explicit even when the package starts as a community suggestion."
                ],
                "KARMA FORGE and campaign continuity docs already point to the need for reviewed package limits.",
                "Open KARMA FORGE",
                "/participate/karma-forge",
                "Account package tracking keeps the follow and approval history visible next to support and campaign work.",
                "Review should treat this as discovery first, not a fast-publish path."),
            new(
                "artifact-brief-bundle",
                "Briefing bundle",
                "A file package for primers, briefings, recaps, and shared output bundles.",
                "artifact_media_package",
                "File and media package",
                "Preview",
                [
                    "Compatibility depends on publication trust, the file shelf, and clear history.",
                    "The package can be shown in review pages without becoming the source of product decisions.",
                    "Creator, campaign, and public views can differ while the package history stays clear."
                ],
                [
                    "Media and file packages may support a page, but they cannot replace route, install, or rules status.",
                    "Publication status and moderation notes stay attached to the package before broader discovery claims.",
                    "File detail and library pages remain the Chummer surfaces for discovery and return."
                ],
                "The file library already shows that publication, recap, and preview outputs can stay inside Chummer.",
                "Open files",
                "/artifacts",
                "Account package tracking ties creator and continuity records back to the same return path.",
                "Keep file packages grounded in history and usefulness rather than media hype."),
            new(
                "community-proposal-sandbox",
                "Community proposal sandbox package",
                "A proposal package for ideas that need clustering, compatibility review, and moderation before they become product work.",
                "community_proposal_package",
                "Community proposal package",
                "Research",
                [
                    "Compatibility stays advisory until Chummer review moves the proposal into a clearer package path.",
                    "Public votes and follows can exist now without pretending the proposal is installable or approved.",
                    "The package route makes the review boundary explicit before any roadmap or release language moves."
                ],
                [
                    "Moderation, duplicate handling, privacy, and package compatibility must stay inside Chummer pages.",
                    "Follow records are Chummer-owned and should not leak external board or maintainer tooling names.",
                    "Research status must remain honest even when interest is high."
                ],
                "The public participate and feedback pages already separate safe public signal from private support and install work.",
                "Open feedback",
                "/feedback",
                "Account package tracking keeps your follows and votes on the same account page as support and continuity.",
                "Treat this package as a reviewed proposal surface with clear moderation and compatibility status.")
        ];
}
