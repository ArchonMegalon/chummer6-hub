using System.Security.Cryptography;
using System.Text;
using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.Support;

public sealed class HostedCompanionPacketService
{
    private const string TriggerVersion = "hosted_domains.v1";

    private readonly PublicReleaseManifestService _releases;
    private readonly SupportConciergePacketService _supportConciergePackets;

    public HostedCompanionPacketService(
        PublicReleaseManifestService releases,
        SupportConciergePacketService supportConciergePackets)
    {
        _releases = releases;
        _supportConciergePackets = supportConciergePackets;
    }

    public HostedCompanionPacketBundle Build(HostedCompanionPacketContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        DateTimeOffset now = DateTimeOffset.UtcNow;
        List<HostedCompanionPacketProjection> accountPackets = [];

        AddIfNotNull(accountPackets, BuildInstallPacket(context, manifest, now));
        AddIfNotNull(accountPackets, BuildUpdatePacket(context, manifest, now));
        AddIfNotNull(accountPackets, BuildSupportPacket(context, manifest, now));
        AddIfNotNull(accountPackets, BuildRestorePacket(context, manifest, now));
        AddIfNotNull(accountPackets, BuildCampaignPacket(context, manifest, now));
        AddIfNotNull(accountPackets, BuildPublicationPacket(context, manifest, now));

        return new HostedCompanionPacketBundle(
            BuiltAtUtc: now,
            AccountPackets: accountPackets,
            PublicHubPackets:
            [
                BuildPublicHubPacket(context, manifest, now)
            ]);
    }

    private HostedCompanionPacketProjection? BuildInstallPacket(
        HostedCompanionPacketContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        ClaimedInstallationDto? installation = context.InstallLinking?.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        InstallClaimTicketDto? claimTicket = context.InstallLinking?.PendingClaimTickets
            .OrderByDescending(static item => item.CreatedAtUtc)
            .FirstOrDefault();
        DownloadReceiptDto? receipt = context.InstallLinking?.RecentReceipts
            .OrderByDescending(static item => item.IssuedAtUtc)
            .FirstOrDefault();

        if (installation is null && claimTicket is null && receipt is null)
        {
            return null;
        }

        PublicReleaseArtifactDto? artifact = ResolveArtifact(manifest, installation?.ArtifactId ?? claimTicket?.ArtifactId, installation?.Platform, installation?.Arch);
        string installRole = ResolveInstallRole(context.InstallLinking);
        string deviceRole = ResolveDeviceRole(installation?.Platform, installation?.HeadId);
        string artifactLabel = artifact?.Id ?? claimTicket?.ArtifactId ?? installation?.ArtifactId ?? "current-release";
        string summary = installation is not null
            ? $"Claimed install {installation.Platform ?? "desktop"} {installation.Version} on {installation.Channel} can continue through Chummer install and account routes."
            : $"Claim {claimTicket?.ClaimCode ?? receipt?.ReceiptId ?? "pending"} stays with Chummer until the claimed device finishes.";

        List<string> routes =
        [
            "/downloads",
            "/account/access",
            "/api/v1/install-linking/continuation"
        ];
        if (!string.IsNullOrWhiteSpace(artifact?.Id))
        {
            routes.Add($"/downloads/install/{Uri.EscapeDataString(artifact.Id)}");
        }

        return new HostedCompanionPacketProjection(
            PacketId: StableId("install", installation?.InstallationId ?? claimTicket?.TicketId ?? receipt?.ReceiptId ?? manifest.Version),
            TriggerClass: "install_bootstrap_ready",
            EventType: "install_bootstrap_route",
            TriggerVersion: TriggerVersion,
            EmittedAtUtc: now,
            OwningDomain: "install",
            Severity: "info",
            Urgency: "suggested",
            Locale: context.Locale,
            SurfaceAllowlist:
            [
                "home_cockpit",
                "install_continuation"
            ],
            DeviceRole: deviceRole,
            InstallRole: installRole,
            MaskId: "concierge",
            PersonaModeDefault: "practical",
            AllowedJokeBudget: "light",
            EvidenceDrawerRequired: true,
            FactRefs:
            [
                new HostedCompanionFactRefProjection(
                    FactId: StableId("install-fact", installation?.InstallationId ?? claimTicket?.TicketId ?? receipt?.ReceiptId ?? "install"),
                    Kind: "install_linking_state",
                    Label: installation is null ? "Install claim" : "Claimed installation",
                    Summary: summary,
                    Route: "/api/v1/install-linking/continuation",
                    ReceiptId: receipt?.ReceiptId),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("install-manifest", artifactLabel),
                    Kind: "release_manifest",
                    Label: "Current release",
                    Summary: $"{manifest.Channel} {manifest.Version} currently publishes {artifactLabel}.",
                    Route: string.IsNullOrWhiteSpace(artifact?.Id) ? "/downloads" : $"/downloads/install/{Uri.EscapeDataString(artifact!.Id)}")
            ],
            FactSummary: summary,
            AllowedActions:
            [
                new HostedCompanionActionProjection("continue_install", "Continue install", "/api/v1/install-linking/continuation", "Resume the install from the claimed device."),
                new HostedCompanionActionProjection("open_downloads", "Open downloads", string.IsNullOrWhiteSpace(artifact?.Id) ? "/downloads" : $"/downloads/install/{Uri.EscapeDataString(artifact!.Id)}", "Inspect the current installer and release status."),
                new HostedCompanionActionProjection("open_account_access", "Review account access", "/account/access", "Confirm the same account and linked install before you continue.")
            ],
            Suppression: BuildSuppression("trigger_class_per_install", 21600, 1, true),
            EaCompile: BuildEaCompile(true, "line_variant_pack", ["line_variant_pack"], runtimeBlocking: false),
            MediaEligibility: BuildMediaEligibility(false),
            PrivacyClass: "signed_in",
            RequiresUserGestureForVoice: true,
            SuppressUntilUtc: null,
            ExpiryUtc: now.AddHours(12),
            ForbiddenClaims:
            [
                "Do not claim the installer files are newer than the current release shows.",
                "Do not replace first-party install continuation with browser ritual or chat-only recovery."
            ],
            Summary: summary,
            FallbackPackId: "install_linking_shell",
            SourceId: installation?.InstallationId ?? claimTicket?.TicketId ?? receipt?.ReceiptId);
    }

    private HostedCompanionPacketProjection? BuildUpdatePacket(
        HostedCompanionPacketContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        ClaimedInstallationDto? installation = context.InstallLinking?.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        if (installation is null)
        {
            return null;
        }

        PublicReleaseArtifactDto? artifact = ResolveArtifact(manifest, installation.ArtifactId, installation.Platform, installation.Arch);
        bool versionMatches = string.Equals(Normalize(installation.Version), Normalize(manifest.Version), StringComparison.OrdinalIgnoreCase);
        bool channelMatches = string.Equals(Normalize(installation.Channel), Normalize(manifest.Channel), StringComparison.OrdinalIgnoreCase);
        bool previewPosture = string.Equals(Normalize(manifest.Channel), "preview", StringComparison.OrdinalIgnoreCase);
        string summary = !versionMatches || !channelMatches
            ? $"{installation.Platform ?? "desktop"} is on {installation.Channel} {installation.Version} while chummer.run promotes {manifest.Channel} {manifest.Version}."
            : $"{installation.Platform ?? "desktop"} already matches the hosted {manifest.Channel} {manifest.Version}, but preview status still needs visible update caution.";

        return new HostedCompanionPacketProjection(
            PacketId: StableId("update", installation.InstallationId),
            TriggerClass: "preview_scout_warning",
            EventType: "update_ready",
            TriggerVersion: TriggerVersion,
            EmittedAtUtc: now,
            OwningDomain: "update",
            Severity: previewPosture || !versionMatches || !channelMatches ? "caution" : "info",
            Urgency: "suggested",
            Locale: context.Locale,
            SurfaceAllowlist:
            [
                "home_cockpit",
                "update_flow",
                "install_continuation"
            ],
            DeviceRole: ResolveDeviceRole(installation.Platform, installation.HeadId),
            InstallRole: ResolveInstallRole(context.InstallLinking),
            MaskId: "concierge",
            PersonaModeDefault: "practical",
            AllowedJokeBudget: "light",
            EvidenceDrawerRequired: true,
            FactRefs:
            [
                new HostedCompanionFactRefProjection(
                    FactId: StableId("update-install", installation.InstallationId),
                    Kind: "install_linking_state",
                    Label: "Installed build status",
                    Summary: $"{installation.Platform ?? "desktop"} / {installation.Channel} / {installation.Version}",
                    Route: "/api/v1/install-linking/continuation",
                    ReceiptId: installation.GrantId),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("update-release", manifest.Version),
                    Kind: "update_ready",
                    Label: "Hosted release status",
                    Summary: $"{manifest.Channel} {manifest.Version} is the promoted hosted update.",
                    Route: string.IsNullOrWhiteSpace(artifact?.Id) ? "/downloads" : $"/downloads/install/{Uri.EscapeDataString(artifact!.Id)}")
            ],
            FactSummary: summary,
            AllowedActions:
            [
                new HostedCompanionActionProjection("show_risk", "Show release status", "/downloads", "Inspect the promoted release, support state, and current installer."),
                new HostedCompanionActionProjection("open_safe_install", "Open safe install", string.IsNullOrWhiteSpace(artifact?.Id) ? "/downloads" : $"/downloads/install/{Uri.EscapeDataString(artifact!.Id)}", "Jump to the Chummer installer path for the promoted release."),
                new HostedCompanionActionProjection("open_support_lane", "Open support", "/api/v1/install-linking/continuation/support", "Keep recovery and update follow-up attached to the linked copy.")
            ],
            Suppression: BuildSuppression("trigger_class_per_install", 21600, 1, true),
            EaCompile: BuildEaCompile(true, "line_variant_pack", ["line_variant_pack"], runtimeBlocking: false),
            MediaEligibility: BuildMediaEligibility(false),
            PrivacyClass: "signed_in",
            RequiresUserGestureForVoice: true,
            SuppressUntilUtc: null,
            ExpiryUtc: now.AddHours(12),
            ForbiddenClaims:
            [
                "Do not claim an update is safe unless the Chummer release status, support state, and install routes agree.",
                "Do not imply the update feed outranks Chummer support or recovery status."
            ],
            Summary: summary,
            FallbackPackId: "preview_scout_warning",
            SourceId: installation.InstallationId);
    }

    private HostedCompanionPacketProjection? BuildSupportPacket(
        HostedCompanionPacketContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        SupportCaseProjection? supportCase = context.SupportCases
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        if (supportCase is null)
        {
            return null;
        }

        InstallAwareSupportConciergePacket concierge = _supportConciergePackets.Build(supportCase, context.InstallLinking);
        bool reporterCanClose = concierge.SupportClosure.ClosureReadiness.ReporterCanClose;
        string detailRoute = concierge.SupportCaseTruth.DetailHref ?? $"/account/support/{Uri.EscapeDataString(supportCase.CaseId)}";
        string summary = reporterCanClose
            ? concierge.SupportClosure.Summary
            : $"{concierge.SupportClosure.Summary} {concierge.ReleaseExplainer.CorrectnessBasis}";

        return new HostedCompanionPacketProjection(
            PacketId: StableId("support", supportCase.CaseId),
            TriggerClass: reporterCanClose ? "support_fix_confirmation" : "support_case_status_update",
            EventType: reporterCanClose ? "fix_closure" : "support_case_state",
            TriggerVersion: TriggerVersion,
            EmittedAtUtc: now,
            OwningDomain: "support",
            Severity: reporterCanClose ? "celebration" : concierge.SupportCaseTruth.NeedsInstallUpdate ? "caution" : "info",
            Urgency: reporterCanClose ? "suggested" : "interrupting",
            Locale: context.Locale,
            SurfaceAllowlist:
            [
                "home_cockpit",
                "support_case_detail",
                "install_continuation"
            ],
            DeviceRole: ResolveDeviceRole(concierge.InstalledBuildTruth.Platform, concierge.InstalledBuildTruth.HeadId),
            InstallRole: ResolveInstallRole(context.InstallLinking),
            MaskId: "concierge",
            PersonaModeDefault: "practical",
            AllowedJokeBudget: reporterCanClose ? "light" : "none",
            EvidenceDrawerRequired: true,
            FactRefs:
            [
                new HostedCompanionFactRefProjection(
                    FactId: StableId("support-case", supportCase.CaseId),
                    Kind: "support_case_status",
                    Label: concierge.SupportCaseTruth.StageLabel,
                    Summary: concierge.SupportClosure.Summary,
                    Route: detailRoute),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("support-release", supportCase.CaseId),
                    Kind: "release_channel_confirmation",
                    Label: "Release correctness basis",
                    Summary: concierge.ReleaseExplainer.CorrectnessBasis,
                    Route: concierge.ReleaseExplainer.FirstPartyRoutes.FirstOrDefault(static route => route.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase))),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("support-install", supportCase.CaseId),
                    Kind: "install_linking_truth",
                    Label: "Linked-copy support",
                    Summary: concierge.IsInstallAware
                        ? "The installed build is linked, so support stays tied to the claimed device."
                        : "Support stays in Chummer, but this case needs a linked device before it can be closed cleanly.",
                    Route: "/api/v1/install-linking/continuation/support",
                    ReceiptId: concierge.InstalledBuildTruth.InstalledBuildReceiptId)
            ],
            FactSummary: summary,
            AllowedActions:
            [
                new HostedCompanionActionProjection("open_support_case", "Open support case", detailRoute, "Inspect the support case, next-safe action, and closure timeline."),
                new HostedCompanionActionProjection("show_fix_receipt", "Show fix record", concierge.ReleaseExplainer.FirstPartyRoutes.FirstOrDefault(static route => route.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase)) ?? "/downloads", "Open the same Chummer release path that support says fixes the issue."),
                new HostedCompanionActionProjection("open_install_support", "Open install support", "/api/v1/install-linking/continuation/support", "Keep support and install follow-up on the same linked copy.")
            ],
            Suppression: BuildSuppression("trigger_class_per_support_case", reporterCanClose ? 28800 : 14400, 1, true),
            EaCompile: BuildEaCompile(true, reporterCanClose ? "line_variant_pack_and_rare_media_brief" : "line_variant_pack", reporterCanClose ? ["line_variant_pack", "rare_media_brief"] : ["line_variant_pack"], runtimeBlocking: false),
            MediaEligibility: BuildMediaEligibility(reporterCanClose, reporterCanClose ? ["companion_scene"] : null),
            PrivacyClass: "support_private",
            RequiresUserGestureForVoice: true,
            SuppressUntilUtc: null,
            ExpiryUtc: now.AddDays(1),
            ForbiddenClaims:
            [
                "Do not claim the issue is fixed on a different release channel than the first-party release explainer proves.",
                "Do not route support closure through third-party tooling or public replies instead of the tracked first-party case."
            ],
            Summary: summary,
            FallbackPackId: "install_aware_support_concierge",
            SourceId: supportCase.CaseId);
    }

    private HostedCompanionPacketProjection? BuildRestorePacket(
        HostedCompanionPacketContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        WorkspaceRestoreProjection restore = context.Restore;
        bool hasConflict = (restore.ConflictReceipts?.Count ?? 0) > 0 || restore.ConflictSummaries.Count > 0;
        if (!hasConflict && restore.ClaimedDevices.Count == 0 && restore.RecentCampaigns.Count == 0 && restore.RecentDossiers.Count == 0)
        {
            return null;
        }

        string summary = hasConflict
            ? restore.ConflictSummaries.FirstOrDefault()
                ?? restore.ConflictReceipts?.FirstOrDefault()?.Summary
                ?? "Restore needs an explicit choice before the hosted path can continue safely."
            : $"Restore keeps {restore.ClaimedDevices.Count} claimed device(s), {restore.RecentCampaigns.Count} campaign(s), and {restore.RecentDossiers.Count} dossier(s) available on the Chummer return path.";
        WorkspaceRestoreConflictReceipt? conflict = restore.ConflictReceipts?.FirstOrDefault();
        WorkspaceRestoreProvenanceReceipt? provenance = restore.ProvenanceReceipts?.FirstOrDefault();
        ClaimedDeviceRestoreProjection? claimedDevice = restore.ClaimedDevices.FirstOrDefault();

        return new HostedCompanionPacketProjection(
            PacketId: StableId("restore", restore.RestoreId),
            TriggerClass: hasConflict ? "restore_conflict_warning" : "restore_continuation_ready",
            EventType: "restore_conflict_state",
            TriggerVersion: TriggerVersion,
            EmittedAtUtc: now,
            OwningDomain: "restore",
            Severity: hasConflict ? "blocking" : "info",
            Urgency: hasConflict ? "interrupting" : "suggested",
            Locale: context.Locale,
            SurfaceAllowlist:
            [
                "home_cockpit",
                "restore_flow",
                "install_continuation"
            ],
            DeviceRole: ResolveDeviceRole(claimedDevice?.Platform, claimedDevice?.HeadId),
            InstallRole: ResolveInstallRole(context.InstallLinking),
            MaskId: "concierge",
            PersonaModeDefault: "practical",
            AllowedJokeBudget: "none",
            EvidenceDrawerRequired: true,
            FactRefs:
            [
                new HostedCompanionFactRefProjection(
                    FactId: StableId("restore-conflict", restore.RestoreId),
                    Kind: "restore_conflict_receipt",
                    Label: hasConflict ? "Restore conflict" : "Restore status",
                    Summary: summary,
                    Route: "/account/access",
                    ReceiptId: conflict?.ReceiptId),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("restore-provenance", restore.RestoreId),
                    Kind: "provenance_receipt",
                    Label: "Restore provenance",
                    Summary: provenance?.Summary ?? $"{restore.RecentArtifacts.Count} recent files and {restore.Entitlements.Count} entitlements remain visible on the restore path.",
                    Route: "/api/v1/install-linking/continuation",
                    ReceiptId: provenance?.ReceiptId)
            ],
            FactSummary: summary,
            AllowedActions:
            [
                new HostedCompanionActionProjection("resolve_conflict", "Review restore", "/account/access", "Inspect restore conflicts, provenance, and the next safe route."),
                new HostedCompanionActionProjection("inspect_versions", "Inspect linked copy", "/api/v1/install-linking/continuation", "Keep restore and the claimed device on the same Chummer path."),
                new HostedCompanionActionProjection("open_support", "Open support intake", "/contact#support-intake", "Escalate restore drift through Chummer support when the hosted path is not enough.")
            ],
            Suppression: BuildSuppression("trigger_class_per_restore_session", hasConflict ? 0 : 21600, hasConflict ? 6 : 1, !hasConflict),
            EaCompile: BuildEaCompile(false, hasConflict ? "first_party_only" : "line_variant_pack", hasConflict ? [] : ["line_variant_pack"], runtimeBlocking: false),
            MediaEligibility: BuildMediaEligibility(false),
            PrivacyClass: "signed_in",
            RequiresUserGestureForVoice: true,
            SuppressUntilUtc: null,
            ExpiryUtc: now.AddHours(12),
            ForbiddenClaims:
            [
                "Do not auto-resolve restore drift without the Chummer restore records staying visible.",
                "Do not imply restore can outrank claimed-install, entitlement, or support continuity."
            ],
            Summary: summary,
            FallbackPackId: "restore_conflict_warning",
            SourceId: restore.RestoreId);
    }

    private HostedCompanionPacketProjection? BuildCampaignPacket(
        HostedCompanionPacketContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        CampaignWorkspaceProjection? workspace = context.Workspaces
            .OrderByDescending(ResolveWorkspaceFreshnessUtc)
            .FirstOrDefault();
        if (workspace is null)
        {
            return null;
        }

        WorkspaceChangePacketProjection? changePacket = workspace.ChangePackets?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        string summary = changePacket?.Summary
            ?? workspace.CampaignAdoptionLoop?.ResolutionReportApproval?.Summary
            ?? workspace.NextSessionCarryForward?.Summary
            ?? workspace.ReturnSummary;

        return new HostedCompanionPacketProjection(
            PacketId: StableId("campaign", workspace.WorkspaceId),
            TriggerClass: "campaign_rules_changed",
            EventType: "campaign_drift_alert",
            TriggerVersion: TriggerVersion,
            EmittedAtUtc: now,
            OwningDomain: "campaign_workspace",
            Severity: "caution",
            Urgency: "suggested",
            Locale: context.Locale,
            SurfaceAllowlist:
            [
                "home_cockpit",
                "campaign_workspace",
                "runboard"
            ],
            DeviceRole: ResolveDeviceRole(context.Restore.ClaimedDevices.FirstOrDefault()?.Platform, context.Restore.ClaimedDevices.FirstOrDefault()?.HeadId),
            InstallRole: ResolveInstallRole(context.InstallLinking),
            MaskId: "handler",
            PersonaModeDefault: "practical",
            AllowedJokeBudget: "light",
            EvidenceDrawerRequired: true,
            FactRefs:
            [
                new HostedCompanionFactRefProjection(
                    FactId: StableId("campaign-change", workspace.WorkspaceId),
                    Kind: "campaign_workspace_change",
                    Label: workspace.CampaignName,
                    Summary: summary,
                    Route: "/account/work",
                    ReceiptId: changePacket?.PacketId),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("campaign-world", workspace.WorkspaceId),
                    Kind: "campaign_memory",
                    Label: "Campaign memory follow-through",
                    Summary: workspace.CampaignMemory?.Summary ?? workspace.NextSessionCarryForward?.Summary ?? workspace.ReturnSummary,
                    Route: "/account/work#campaign-memory")
            ],
            FactSummary: summary,
            AllowedActions:
            [
                new HostedCompanionActionProjection("open_campaign_workspace", "Open campaign workspace", "/account/work", "See what changed and pick up the same campaign workspace."),
                new HostedCompanionActionProjection("review_impacts", "Review impacts", "/account/work#campaign-memory", "Inspect world-tick, player-safe news, and next-session follow-through."),
                new HostedCompanionActionProjection("open_runboard", "Open runboard", "/account/work#runboard", "Resume the runboard without recreating the session state.")
            ],
            Suppression: BuildSuppression("trigger_class_per_campaign", 43200, 1, true),
            EaCompile: BuildEaCompile(true, "line_variant_pack", ["line_variant_pack"], runtimeBlocking: false),
            MediaEligibility: BuildMediaEligibility(true, ["companion_scene"]),
            PrivacyClass: "campaign_private",
            RequiresUserGestureForVoice: true,
            SuppressUntilUtc: null,
            ExpiryUtc: now.AddDays(1),
            ForbiddenClaims:
            [
                "Do not fabricate campaign, rules, or world consequences beyond Chummer's saved campaign state.",
                "Do not hide campaign state behind a detached community or recap story."
            ],
            Summary: summary,
            FallbackPackId: "campaign_workspace_change",
            SourceId: workspace.WorkspaceId);
    }

    private HostedCompanionPacketProjection? BuildPublicationPacket(
        HostedCompanionPacketContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        CreatorPublicationProjection? publication = context.Publications
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        if (publication is null)
        {
            return null;
        }

        bool discoverable = publication.Discoverable || string.Equals(publication.Visibility, "public", StringComparison.OrdinalIgnoreCase);
        string publicRoute = $"/artifacts/publications/{Uri.EscapeDataString(publication.PublicationId)}";
        string summary = publication.Summary;

        return new HostedCompanionPacketProjection(
            PacketId: StableId("publication", publication.PublicationId),
            TriggerClass: "creator_publication_ready",
            EventType: "publication_ready",
            TriggerVersion: TriggerVersion,
            EmittedAtUtc: now,
            OwningDomain: "publication",
            Severity: "info",
            Urgency: "suggested",
            Locale: context.Locale,
            SurfaceAllowlist:
            [
                "home_cockpit",
                "campaign_workspace",
                "publication_detail"
            ],
            DeviceRole: ResolveDeviceRole(context.Restore.ClaimedDevices.FirstOrDefault()?.Platform, context.Restore.ClaimedDevices.FirstOrDefault()?.HeadId),
            InstallRole: ResolveInstallRole(context.InstallLinking),
            MaskId: "handler",
            PersonaModeDefault: "practical",
            AllowedJokeBudget: "light",
            EvidenceDrawerRequired: true,
            FactRefs:
            [
                new HostedCompanionFactRefProjection(
                    FactId: StableId("publication-fact", publication.PublicationId),
                    Kind: "publication_receipt",
                    Label: publication.Title,
                    Summary: summary,
                    Route: discoverable ? publicRoute : "/account/publications"),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("publication-trust", publication.PublicationId),
                    Kind: "published_artifact_ref",
                    Label: "Publication status",
                    Summary: publication.TrustSummary ?? publication.ProvenanceSummary ?? publication.DiscoverySummary,
                    Route: discoverable ? publicRoute : "/account/publications")
            ],
            FactSummary: summary,
            AllowedActions:
            [
                new HostedCompanionActionProjection("open_publication", discoverable ? "Open publication" : "Open publication detail", discoverable ? publicRoute : "/account/publications", "Review the publication and its current status."),
                new HostedCompanionActionProjection("review_workspace", "Open campaign workspace", "/account/work", "Return to the workspace that created the publication."),
                new HostedCompanionActionProjection("review_support", "Review support status", "/account/support", "Keep publication, support, and rollout follow-up inside Chummer when more work is needed.")
            ],
            Suppression: BuildSuppression("trigger_class_per_campaign", 86400, 1, true),
            EaCompile: BuildEaCompile(true, "line_variant_pack_and_rare_media_brief", ["line_variant_pack", "rare_media_brief"], runtimeBlocking: false),
            MediaEligibility: BuildMediaEligibility(true, ["companion_scene"]),
            PrivacyClass: discoverable ? "public_safe" : "signed_in",
            RequiresUserGestureForVoice: true,
            SuppressUntilUtc: null,
            ExpiryUtc: now.AddDays(2),
            ForbiddenClaims:
            [
                "Do not claim discoverability, compatibility, or moderation status that Chummer does not show.",
                "Do not detach publication status from the underlying campaign and support state."
            ],
            Summary: summary,
            FallbackPackId: "creator_publication_ready",
            SourceId: publication.PublicationId);
    }

    private HostedCompanionPacketProjection BuildPublicHubPacket(
        HostedCompanionPacketContext context,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        string summary = manifest.SupportabilitySummary
            ?? manifest.Message
            ?? $"{manifest.Channel} {manifest.Version} keeps downloads and support status aligned on chummer.run.";
        string severity = string.Equals(Normalize(manifest.Channel), "preview", StringComparison.OrdinalIgnoreCase)
            || string.Equals(Normalize(manifest.SupportabilityState), "watch", StringComparison.OrdinalIgnoreCase)
            ? "caution"
            : "info";

        return new HostedCompanionPacketProjection(
            PacketId: StableId("public-hub", $"{manifest.Channel}:{manifest.Version}"),
            TriggerClass: "public_hub_release_posture",
            EventType: "public_hub_state",
            TriggerVersion: TriggerVersion,
            EmittedAtUtc: now,
            OwningDomain: "public_hub",
            Severity: severity,
            Urgency: "suggested",
            Locale: context.Locale,
            SurfaceAllowlist:
            [
                "public_hub",
                "downloads",
                "contact"
            ],
            DeviceRole: "preview_scout",
            InstallRole: "anonymous_public",
            MaskId: "concierge",
            PersonaModeDefault: "practical",
            AllowedJokeBudget: "light",
            EvidenceDrawerRequired: true,
            FactRefs:
            [
                new HostedCompanionFactRefProjection(
                    FactId: StableId("public-release", manifest.Version),
                    Kind: "public_release_truth",
                    Label: "Hosted release",
                    Summary: $"{manifest.Channel} {manifest.Version} / {manifest.Status}",
                    Route: "/downloads"),
                new HostedCompanionFactRefProjection(
                    FactId: StableId("public-support", manifest.Version),
                    Kind: "public_support_truth",
                    Label: "Public support",
                    Summary: manifest.SupportabilitySummary ?? manifest.KnownIssueSummary ?? "Public support stays on Chummer downloads and contact routes.",
                    Route: "/contact#support-intake")
            ],
            FactSummary: summary,
            AllowedActions:
            [
                new HostedCompanionActionProjection("open_downloads", "Open downloads", "/downloads", "See the current installers and release notes."),
                new HostedCompanionActionProjection("open_support_intake", "Open support intake", "/contact#support-intake", "Use Chummer support when the public page still needs help."),
                new HostedCompanionActionProjection("open_account_access", "Create account for guided install", "/account/access", "Move from the public page into a linked install and restore path.")
            ],
            Suppression: BuildSuppression("trigger_class_per_surface", 43200, 1, true),
            EaCompile: BuildEaCompile(true, "line_variant_pack", ["line_variant_pack"], runtimeBlocking: false),
            MediaEligibility: BuildMediaEligibility(false),
            PrivacyClass: "public_safe",
            RequiresUserGestureForVoice: true,
            SuppressUntilUtc: null,
            ExpiryUtc: now.AddHours(12),
            ForbiddenClaims:
            [
                "Do not let public page copy outrank the installer files, release channel, or Chummer support status.",
                "Do not imply public pages can check private install or support state without an account-linked copy."
            ],
            Summary: summary,
            FallbackPackId: "public_hub_release_posture",
            SourceId: manifest.Version);
    }

    private static void AddIfNotNull(List<HostedCompanionPacketProjection> packets, HostedCompanionPacketProjection? packet)
    {
        if (packet is not null)
        {
            packets.Add(packet);
        }
    }

    private static PublicReleaseArtifactDto? ResolveArtifact(
        PublicReleaseManifestDto manifest,
        string? artifactId,
        string? platform,
        string? arch)
    {
        string? normalizedArtifactId = Normalize(artifactId);
        if (normalizedArtifactId is not null)
        {
            PublicReleaseArtifactDto? exact = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, normalizedArtifactId, StringComparison.OrdinalIgnoreCase));
            if (exact is not null)
            {
                return exact;
            }
        }

        string? normalizedPlatform = Normalize(platform);
        string? normalizedArch = Normalize(arch);
        return manifest.Downloads.FirstOrDefault(item =>
                   Matches(item.PlatformId, normalizedPlatform) || Matches(item.Platform, normalizedPlatform))
               ?? manifest.Downloads.FirstOrDefault(item => Matches(item.Arch, normalizedArch))
               ?? manifest.Downloads.FirstOrDefault();
    }

    private static string ResolveInstallRole(InstallLinkingSummaryDto? installLinking)
    {
        if ((installLinking?.ClaimedInstallations?.Count ?? 0) > 0)
        {
            return "claimed_primary";
        }

        if ((installLinking?.PendingClaimTickets.Count ?? 0) > 0 || (installLinking?.RecentReceipts.Count ?? 0) > 0)
        {
            return "claimed_secondary";
        }

        return "anonymous_public";
    }

    private static string ResolveDeviceRole(string? platform, string? headId)
    {
        if (!string.IsNullOrWhiteSpace(platform))
        {
            return "desktop_primary";
        }

        if (!string.IsNullOrWhiteSpace(headId))
        {
            return "preview_scout";
        }

        return "desktop_primary";
    }

    private static bool Matches(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
           && !string.IsNullOrWhiteSpace(right)
           && string.Equals(left, right, StringComparison.OrdinalIgnoreCase);

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string StableId(string prefix, string seed)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes($"{prefix}:{seed}"));
        return $"{prefix}:{Convert.ToHexString(digest[..8]).ToLowerInvariant()}";
    }

    private static DateTimeOffset ResolveWorkspaceFreshnessUtc(CampaignWorkspaceProjection workspace)
    {
        DateTimeOffset? changePacket = workspace.ChangePackets?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Select(static item => (DateTimeOffset?)item.UpdatedAtUtc)
            .FirstOrDefault();
        DateTimeOffset? consequence = workspace.Consequences?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Select(static item => (DateTimeOffset?)item.UpdatedAtUtc)
            .FirstOrDefault();
        return changePacket
            ?? consequence
            ?? workspace.CampaignAdoptionLoop?.ResolutionReportApproval?.UpdatedAtUtc
            ?? workspace.LatestContinuity?.CapturedAtUtc
            ?? DateTimeOffset.MinValue;
    }

    private static HostedCompanionSuppressionProjection BuildSuppression(
        string cooldownScope,
        int cooldownSeconds,
        int maxImpressionsPerDay,
        bool requiresMaterialChange)
        => new(
            CooldownScope: cooldownScope,
            CooldownSeconds: cooldownSeconds,
            MaxImpressionsPerDay: maxImpressionsPerDay,
            RequiresMaterialChange: requiresMaterialChange,
            ResetOnAction:
            [
                "clicked_primary_action",
                "opened_evidence_drawer"
            ]);

    private static HostedCompanionEaCompileProjection BuildEaCompile(
        bool eligible,
        string mode,
        IReadOnlyList<string> allowedOutputs,
        bool runtimeBlocking)
        => new(
            Eligible: eligible,
            Mode: mode,
            AllowedOutputs: allowedOutputs,
            RuntimeBlocking: runtimeBlocking);

    private static HostedCompanionMediaEligibilityProjection BuildMediaEligibility(
        bool eligible,
        IReadOnlyList<string>? modes = null)
        => new(
            Eligible: eligible,
            Modes: modes ?? Array.Empty<string>());
}
