using System.IO;
using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace RunServicesVerification;

internal static class CampaignSpineRestoreVerification
{
    public static Task RunAsync()
    {
        VerifyClaimedDeviceRestoreSummariesNameExactPrefetchSet();
        VerifyRestoreConflictReceiptsCaptureStaleClaimAndEntitlementState();
        VerifyRestoreReceiptsSurviveCommunityStoreReload();
        VerifyAftermathArtifactMetadataSurvivesReload();
        return Task.CompletedTask;
    }

    private static void VerifyClaimedDeviceRestoreSummariesNameExactPrefetchSet()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore", "Rook", "rook@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-travel",
                        ArtifactId: "artifact-travel-kit",
                        ArtifactLabel: "Android travel kit",
                        FileName: "travel-kit.apk",
                        DownloadUrl: "/downloads/files/travel-kit.apk",
                        Channel: "preview",
                        Version: "2026.03.29-preview.1",
                        Head: "pwa",
                        Platform: "android",
                        Arch: "arm64",
                        Kind: "portable",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddMinutes(-10),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-tablet",
                        ArtifactId: "artifact-travel-kit",
                        Channel: "preview",
                        Version: "2026.03.29-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-2),
                        UpdatedAtUtc: now.AddMinutes(-5),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-tablet",
                        ClaimTicketId: "ticket-tablet",
                        HeadId: "pwa",
                        Platform: "android",
                        Arch: "arm64",
                        HostLabel: "Travel tablet",
                        GrantId: "grant-tablet"),
                    new ClaimedInstallationDto(
                        InstallationId: "install-safehouse",
                        ArtifactId: "artifact-travel-kit",
                        Channel: "stable",
                        Version: "2026.03.29-stable.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-4),
                        UpdatedAtUtc: now.AddMinutes(-3),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-safehouse",
                        ClaimTicketId: "ticket-safehouse",
                        HeadId: "offline",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Safehouse mirror",
                        GrantId: "grant-safehouse")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-tablet",
                        InstallationId: "install-tablet",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-tablet-token",
                        IssuedAtUtc: now.AddMinutes(-20),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-safehouse",
                        InstallationId: "install-safehouse",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-safehouse-token",
                        IssuedAtUtc: now.AddMinutes(-18),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-orphan",
                        InstallationId: "install-orphan",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-orphan-token",
                        IssuedAtUtc: now.AddMinutes(-16),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);
            ClaimedDeviceRestoreProjection tablet = restore.ClaimedDevices.Single(device => string.Equals(device.InstallationId, "install-tablet", StringComparison.Ordinal));
            ClaimedDeviceRestoreProjection safehouse = restore.ClaimedDevices.Single(device => string.Equals(device.InstallationId, "install-safehouse", StringComparison.Ordinal));

            VerificationAssert.True(tablet.RestoreSummary.Contains("Exact set:", StringComparison.Ordinal), "Claimed-device restore summary should name the exact prefetch set for the play tablet lane.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("Rook dossier", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded dossier.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("Rook preview campaign", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded campaign.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("sr6.preview.v1 [campaign-approved]", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded rule environment.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("Android travel kit (artifact-travel-kit)", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded reconnectable artifact set.");
            VerificationAssert.True(safehouse.DeviceRole == "travel_cache", "Offline stable safehouse installs should project as travel-cache restore lanes.");
            VerificationAssert.True(safehouse.RestoreSummary.Contains("Travel-safe cache keeps", StringComparison.Ordinal), "Travel-cache restore summaries should stay explicit about safehouse posture.");
            VerificationAssert.True(safehouse.RestoreSummary.Contains("Exact set:", StringComparison.Ordinal), "Travel-cache restore summaries should also name the exact prefetch set.");

            VerificationAssert.True((restore.ProvenanceReceipts?.Count ?? 0) >= 3, "Restore projection should emit provenance receipts for entitlement, install, and rule-posture replay.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item => string.Equals(item.Kind, "claimed_installation", StringComparison.OrdinalIgnoreCase) && string.Equals(item.SubjectId, tablet.InstallationId, StringComparison.Ordinal)) == true,
                "Restore provenance should include each claimed device as a concrete receipt.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item => string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace(item.Proof)) == true,
                "Entitlement replay should remain proof-bound in restore provenance receipts.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item =>
                    string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(item.RecoveryHint)) == true,
                "Entitlement restore provenance should name the authority plane and a concrete recovery hint.");
            VerificationAssert.True(restore.ProvenanceReceipts?.All(item => !string.IsNullOrWhiteSpace(item.Surface)) == true,
                "Restore provenance receipts should preserve an explicit workspace_restore or entitlement_sync surface.");
            VerificationAssert.True(restore.ProvenanceReceipts?.All(item => !string.IsNullOrWhiteSpace(item.Authority)) == true,
                "Restore provenance receipts should preserve the authority plane that issued the proof.");
            VerificationAssert.True(restore.ProvenanceReceipts?.All(item => !string.IsNullOrWhiteSpace(item.RecoveryHint)) == true,
                "Restore provenance receipts should preserve a concrete recovery hint for stale or disputed continuation.");
            VerificationAssert.True(restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "restore_summary_conflict", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should be emitted as structured receipts for review and recovery.");
            VerificationAssert.True(restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit orphaned entitlement receipts when sync and claimed installs drift.");
            VerificationAssert.True(restore.ConflictReceipts?.All(item => !string.IsNullOrWhiteSpace(item.Surface)) == true,
                "Restore conflict receipts should preserve an explicit workspace_restore or entitlement_sync surface.");
            VerificationAssert.True(restore.ConflictReceipts?.Any(item =>
                    string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && item.BlocksContinue) == true,
                "Entitlement drift receipts should stay explicitly classified under entitlement sync and block continue until resolved.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyAftermathArtifactMetadataSurvivesReload()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-aftermath-registry", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            HubUserDto user = accounts.EnsureUser("subject.aftermath", "Switch", "switch@example.invalid");

            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            RunProjection? run = workspace.Runs.FirstOrDefault();
            AftermathRecapPackageProjection package = campaignSpine.RecordAftermathRecapPackage(
                user,
                workspace,
                run,
                "session_recap",
                "Reload recap",
                "Governed recap package for reload proof.",
                [
                    $"Run scope: {run?.Title ?? workspace.CampaignName}.",
                    "Continuity: governed return lane remains attached to the same campaign spine.",
                    "Package kind: session_recap.",
                    "Active scene: no pinned scene."
                ]);

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            CampaignSpineService reloadedCampaignSpine = new(reloadedStore, new WorkspaceLifecyclePolicyService(configuration), new CampaignArtifactRegistryBridge(reloadedStore));
            CampaignWorkspaceProjection reloadedWorkspace = reloadedCampaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a reloaded starter workspace.");
            AftermathRecapPackageProjection reloadedPackage = reloadedWorkspace.AftermathPackages?.FirstOrDefault(item => string.Equals(item.PackageId, package.PackageId, StringComparison.Ordinal))
                ?? throw new InvalidOperationException("Expected a reloaded aftermath package.");

            VerificationAssert.Equal(package.ArtifactId, reloadedPackage.ArtifactId, "Reloaded aftermath packages should preserve the registered artifact id.");
            VerificationAssert.True(string.Equals(reloadedPackage.ArtifactKind, "RecapPackage", StringComparison.Ordinal), "Reloaded aftermath packages should preserve the recap artifact kind.");
            VerificationAssert.True(string.Equals(reloadedPackage.ArtifactVisibility, "campaign-shared", StringComparison.Ordinal), "Reloaded aftermath packages should preserve campaign-shared visibility.");
            VerificationAssert.True(string.Equals(reloadedPackage.ArtifactTrustTier, "curated", StringComparison.Ordinal), "Reloaded aftermath packages should preserve curated trust posture.");
            VerificationAssert.True(!string.IsNullOrWhiteSpace(reloadedPackage.ProvenanceSummary), "Reloaded aftermath packages should preserve provenance summaries.");
            VerificationAssert.True(!string.IsNullOrWhiteSpace(reloadedPackage.AuditSummary), "Reloaded aftermath packages should preserve audit summaries.");
            VerificationAssert.True(reloadedPackage.EvidenceLines.Any(item => item.StartsWith("Registry artifact:", StringComparison.OrdinalIgnoreCase)), "Reloaded aftermath packages should preserve registry artifact evidence.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyRestoreConflictReceiptsCaptureStaleClaimAndEntitlementState()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-stale-state", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore.stale", "Switch", "switch@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-stale",
                        ArtifactId: "artifact-stale",
                        ArtifactLabel: "Stale desktop payload",
                        FileName: "stale-linux.deb",
                        DownloadUrl: "/downloads/files/stale-linux.deb",
                        Channel: "preview",
                        Version: "2026.02.01-preview.1",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddDays(-45),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-stale",
                        ArtifactId: "artifact-stale",
                        Channel: "preview",
                        Version: "2026.02.01-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Revoked,
                        CreatedAtUtc: now.AddDays(-45),
                        UpdatedAtUtc: now.AddDays(-40),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-stale",
                        ClaimTicketId: "ticket-stale",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Stale workstation",
                        GrantId: "grant-stale")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-stale",
                        InstallationId: "install-stale",
                        Status: InstallationGrantStates.Expired,
                        AccessToken: "grant-stale-token",
                        IssuedAtUtc: now.AddDays(-45),
                        ExpiresAtUtc: now.AddDays(-15),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);

            VerificationAssert.True(
                restore.ConflictSummaries.Any(item => item.Contains("stale or expired grants", StringComparison.OrdinalIgnoreCase)),
                "Restore conflict summaries should call out stale entitlement replay posture.");
            VerificationAssert.True(
                restore.ConflictSummaries.Any(item => item.Contains("stale or inactive device state", StringComparison.OrdinalIgnoreCase)),
                "Restore conflict summaries should call out stale claimed-install posture.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "entitlement_expired", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit entitlement-expired receipts.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "entitlement_status_mismatch", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit entitlement-status-mismatch receipts.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "claimed_installation_inactive", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit claimed-installation-inactive receipts.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "claimed_installation_stale", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit claimed-installation-stale receipts.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyRestoreReceiptsSurviveCommunityStoreReload()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-reload", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore.reload", "Relay", "relay@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-reload",
                        ArtifactId: "artifact-reload",
                        ArtifactLabel: "Reload desktop payload",
                        FileName: "reload-linux.deb",
                        DownloadUrl: "/downloads/files/reload-linux.deb",
                        Channel: "preview",
                        Version: "2026.04.14-preview.1",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddMinutes(-30),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-reload",
                        ArtifactId: "artifact-reload",
                        Channel: "preview",
                        Version: "2026.04.14-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-3),
                        UpdatedAtUtc: now.AddDays(-2),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-reload",
                        ClaimTicketId: "ticket-reload",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Reload workstation",
                        GrantId: "grant-reload"),
                    new ClaimedInstallationDto(
                        InstallationId: "install-stale-reload",
                        ArtifactId: "artifact-reload-stale",
                        Channel: "stable",
                        Version: "2026.03.01-stable.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Revoked,
                        CreatedAtUtc: now.AddDays(-45),
                        UpdatedAtUtc: now.AddDays(-40),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-reload-stale",
                        ClaimTicketId: "ticket-reload-stale",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Stale reload workstation",
                        GrantId: "grant-reload-stale")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-reload",
                        InstallationId: "install-reload",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-reload-token",
                        IssuedAtUtc: now.AddMinutes(-25),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-reload-orphan",
                        InstallationId: "install-reload-orphan",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-reload-orphan-token",
                        IssuedAtUtc: now.AddMinutes(-20),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);
            VerificationAssert.True((restore.ProvenanceReceipts?.Count ?? 0) > 0, "Reload proof requires persisted restore provenance receipts.");
            VerificationAssert.True((restore.ConflictReceipts?.Count ?? 0) > 0, "Reload proof requires persisted restore conflict receipts.");

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            VerificationAssert.True(reloadedStore.RestoreByUserId.TryGetValue(user.UserId, out WorkspaceRestoreProjection? reloadedRestore), "Restore projections should survive community-store reload.");
            VerificationAssert.NotNull(reloadedRestore, "Reloaded restore projection should be available for receipt assertions.");

            WorkspaceRestoreProvenanceReceipt? entitlementReceipt = reloadedRestore!.ProvenanceReceipts?
                .FirstOrDefault(item => string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase));
            VerificationAssert.NotNull(entitlementReceipt, "Reloaded restore projection should keep active-entitlement provenance receipts.");
            VerificationAssert.True(string.Equals(entitlementReceipt!.Authority, "hub_entitlement_ledger", StringComparison.Ordinal), "Reloaded entitlement provenance should preserve its authority plane.");
            VerificationAssert.True(!string.IsNullOrWhiteSpace(entitlementReceipt.RecoveryHint), "Reloaded entitlement provenance should preserve the recovery hint.");

            WorkspaceRestoreConflictReceipt? orphanConflict = reloadedRestore.ConflictReceipts?
                .FirstOrDefault(item => string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase));
            VerificationAssert.NotNull(orphanConflict, "Reloaded restore projection should keep entitlement orphan conflict receipts.");
            VerificationAssert.True(string.Equals(orphanConflict!.Surface, "entitlement_sync", StringComparison.Ordinal), "Reloaded entitlement orphan conflicts should preserve entitlement-sync surface classification.");
            VerificationAssert.True(orphanConflict.BlocksContinue, "Reloaded entitlement orphan conflicts should preserve block-continue posture.");

            WorkspaceRestoreConflictReceipt? inactiveInstallConflict = reloadedRestore.ConflictReceipts?
                .FirstOrDefault(item => string.Equals(item.Kind, "claimed_installation_inactive", StringComparison.OrdinalIgnoreCase));
            VerificationAssert.NotNull(inactiveInstallConflict, "Reloaded restore projection should keep claimed-installation conflict receipts.");
            VerificationAssert.True(string.Equals(inactiveInstallConflict!.Surface, "workspace_restore", StringComparison.Ordinal), "Reloaded claimed-installation conflicts should preserve workspace-restore surface classification.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }
}
