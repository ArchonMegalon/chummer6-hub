using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignSpineRestoreReceiptTests
{
    [Fact]
    public void RestoreProjectionEmitsAuthorityBackedProvenanceAndSurfaceBoundConflicts()
    {
        string tempRoot = CreateTempRoot("campaign-spine-restore");

        try
        {
            IConfiguration configuration = CreateConfiguration(tempRoot);
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
            ClaimedDeviceRestoreProjection tablet = Assert.Single(
                restore.ClaimedDevices,
                device => string.Equals(device.InstallationId, "install-tablet", StringComparison.Ordinal));
            ClaimedDeviceRestoreProjection safehouse = Assert.Single(
                restore.ClaimedDevices,
                device => string.Equals(device.InstallationId, "install-safehouse", StringComparison.Ordinal));

            Assert.Contains("Exact set:", tablet.RestoreSummary, StringComparison.Ordinal);
            Assert.Contains("Rook dossier", tablet.RestoreSummary, StringComparison.Ordinal);
            Assert.Contains("Rook preview campaign", tablet.RestoreSummary, StringComparison.Ordinal);
            Assert.Contains("sr6.preview.v1 [campaign-approved]", tablet.RestoreSummary, StringComparison.Ordinal);
            Assert.Contains("Android travel kit (artifact-travel-kit)", tablet.RestoreSummary, StringComparison.Ordinal);
            Assert.Equal("travel_cache", safehouse.DeviceRole);
            Assert.Contains("Travel-safe cache keeps", safehouse.RestoreSummary, StringComparison.Ordinal);
            Assert.Contains("Exact set:", safehouse.RestoreSummary, StringComparison.Ordinal);

            Assert.True((restore.ProvenanceReceipts?.Count ?? 0) >= 3);
            Assert.Contains(
                restore.ProvenanceReceipts ?? [],
                item => string.Equals(item.Kind, "claimed_installation", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.SubjectId, tablet.InstallationId, StringComparison.Ordinal));
            Assert.Contains(
                restore.ProvenanceReceipts ?? [],
                item => string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(item.RecoveryHint));

            Assert.Contains(
                restore.ConflictReceipts ?? [],
                item => string.Equals(item.Kind, "restore_summary_conflict", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(
                restore.ConflictReceipts ?? [],
                item => string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && item.BlocksContinue);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void RestoreProjectionCapturesStaleClaimAndEntitlementConflictReceipts()
    {
        string tempRoot = CreateTempRoot("campaign-spine-restore-stale-state");

        try
        {
            IConfiguration configuration = CreateConfiguration(tempRoot);
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

            Assert.Contains(
                restore.ConflictSummaries,
                item => item.Contains("stale or expired grants", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(
                restore.ConflictSummaries,
                item => item.Contains("stale or inactive device state", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(restore.ConflictReceipts ?? [], item => string.Equals(item.Kind, "entitlement_expired", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(restore.ConflictReceipts ?? [], item => string.Equals(item.Kind, "entitlement_status_mismatch", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(restore.ConflictReceipts ?? [], item => string.Equals(item.Kind, "claimed_installation_inactive", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(restore.ConflictReceipts ?? [], item => string.Equals(item.Kind, "claimed_installation_stale", StringComparison.OrdinalIgnoreCase));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void RestoreProjectionCapturesBlockingArtifactReplayDriftForClaimedInstall()
    {
        string tempRoot = CreateTempRoot("campaign-spine-restore-artifact-drift");

        try
        {
            IConfiguration configuration = CreateConfiguration(tempRoot);
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore.drift", "Switch", "switch@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-current",
                        ArtifactId: "artifact-linux",
                        ArtifactLabel: "Linux installer",
                        FileName: "chummer-linux.deb",
                        DownloadUrl: "/downloads/files/chummer-linux.deb",
                        Channel: "preview",
                        Version: "0.6.1-smoke",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddMinutes(-20),
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
                        InstallationId: "install-linux",
                        ArtifactId: "artifact-linux",
                        Channel: "preview",
                        Version: "0.6.2-smoke",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-2),
                        UpdatedAtUtc: now.AddMinutes(-3),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-linux",
                        ClaimTicketId: "ticket-linux",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Linux workstation",
                        GrantId: "grant-linux")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-linux",
                        InstallationId: "install-linux",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-linux-token",
                        IssuedAtUtc: now.AddMinutes(-10),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);

            Assert.Contains(
                restore.ConflictReceipts ?? [],
                item => string.Equals(item.Kind, "entitlement_artifact_drift", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && item.BlocksContinue
                    && item.Summary.Contains("0.6.2-smoke", StringComparison.Ordinal)
                    && item.Summary.Contains("0.6.1-smoke", StringComparison.Ordinal));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void RestoreReceiptsSurviveCommunityStoreReload()
    {
        string tempRoot = CreateTempRoot("campaign-spine-restore-reload");

        try
        {
            IConfiguration configuration = CreateConfiguration(tempRoot);
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
            Assert.NotEmpty(restore.ProvenanceReceipts ?? []);
            Assert.NotEmpty(restore.ConflictReceipts ?? []);

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            Assert.True(reloadedStore.RestoreByUserId.TryGetValue(user.UserId, out WorkspaceRestoreProjection? reloadedRestore));
            Assert.NotNull(reloadedRestore);

            WorkspaceRestoreProvenanceReceipt entitlementReceipt = Assert.Single(
                reloadedRestore!.ProvenanceReceipts ?? [],
                item => string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase));
            Assert.Equal("hub_entitlement_ledger", entitlementReceipt.Authority);
            Assert.False(string.IsNullOrWhiteSpace(entitlementReceipt.RecoveryHint));

            WorkspaceRestoreConflictReceipt orphanConflict = Assert.Single(
                reloadedRestore.ConflictReceipts ?? [],
                item => string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase));
            Assert.Equal("entitlement_sync", orphanConflict.Surface);
            Assert.True(orphanConflict.BlocksContinue);

            WorkspaceRestoreConflictReceipt inactiveInstallConflict = Assert.Single(
                reloadedRestore.ConflictReceipts ?? [],
                item => string.Equals(item.Kind, "claimed_installation_inactive", StringComparison.OrdinalIgnoreCase));
            Assert.Equal("workspace_restore", inactiveInstallConflict.Surface);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    private static IConfiguration CreateConfiguration(string tempRoot)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
            })
            .Build();

    private static string CreateTempRoot(string name)
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-tests", name, Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        return tempRoot;
    }

    private static void DeleteTempRoot(string tempRoot)
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }
}
