using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Xunit;

namespace Chummer.Tests;

public sealed class SupportCasePresentationServiceTests
{
    [Fact]
    public void Build_InstallRailCaseKeepsClaimedInstallAsPrimaryContinuationWhenFixIsReady()
    {
        var service = new SupportCasePresentationService();
        var supportCase = new SupportCaseProjection(
            CaseId: "case-install",
            ClusterKey: "cluster-install",
            Kind: SupportCaseKinds.InstallHelp,
            Status: SupportCaseStatuses.ReleasedToReporterChannel,
            Title: "Linux installer needs follow-through",
            Summary: "The fix is ready on the linked install rail.",
            Detail: "Release now carries the fix.",
            CandidateOwnerRepo: "chummer6-hub",
            DesignImpactSuspected: false,
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
            Source: SupportCaseSourceKinds.HubAccount,
            ReporterUserId: "usr-1",
            ReporterSubjectId: "subject-1",
            InstallationId: "install-1",
            ApplicationVersion: "0.7.0-preview",
            ReleaseChannel: "preview",
            HeadId: "avalonia",
            Platform: "linux",
            Arch: "x64",
            FixedVersion: "0.7.1-preview",
            FixedChannel: "preview");
        var installLinking = new InstallLinkingSummaryDto(
            RecentReceipts: Array.Empty<DownloadReceiptDto>(),
            PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
            ClaimedInstallations:
            [
                new ClaimedInstallationDto(
                    InstallationId: "install-1",
                    ArtifactId: "avalonia-linux-x64-installer",
                    Channel: "preview",
                    Version: "0.7.0-preview",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: DateTimeOffset.Parse("2026-04-14T10:00:00Z"),
                    UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
                    UserId: "usr-1",
                    SubjectId: "subject-1",
                    PublicKey: "pub-1",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    HostLabel: "Table Linux"),
            ],
            ActiveGrants: Array.Empty<InstallationGrantDto>());

        var presentation = service.Build(supportCase, installLinking);

        Assert.Equal("Open installs", presentation.PrimaryActionLabel);
        Assert.Equal("/account/access", presentation.PrimaryActionHref);
        Assert.Contains("Update the affected claimed install to preview 0.7.1-preview", presentation.NextSafeAction, StringComparison.Ordinal);
        Assert.DoesNotContain("Open installs", presentation.NextSafeAction, StringComparison.Ordinal);
        Assert.Contains("affected claimed install", presentation.FollowUpLaneSummary, StringComparison.Ordinal);
        Assert.Contains("Installs only when you need to relink or reclaim", presentation.FollowUpLaneSummary, StringComparison.Ordinal);
    }

    [Fact]
    public void Build_NonInstallSignedInCaseKeepsReporterInsideAccountSupport()
    {
        var service = new SupportCasePresentationService();
        var supportCase = new SupportCaseProjection(
            CaseId: "case-bug",
            ClusterKey: "cluster-bug",
            Kind: SupportCaseKinds.BugReport,
            Status: SupportCaseStatuses.Accepted,
            Title: "Character save fails",
            Summary: "Desktop save still fails.",
            Detail: "The save path still throws.",
            CandidateOwnerRepo: "chummer6-ui",
            DesignImpactSuspected: false,
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
            Source: SupportCaseSourceKinds.HubAccount,
            ReporterUserId: "usr-1",
            ReporterSubjectId: "subject-1");

        var presentation = service.Build(supportCase);

        Assert.Equal("Open case", presentation.PrimaryActionLabel);
        Assert.Equal("/account/support/case-bug", presentation.PrimaryActionHref);
        Assert.Equal("Follow-up stays inside Account > Support for this signed-in report.", presentation.FollowUpLaneSummary);
    }

    [Fact]
    public void Build_OrphanedInstallRailCaseTellsReporterToRelinkBeforePickup()
    {
        var service = new SupportCasePresentationService();
        var supportCase = new SupportCaseProjection(
            CaseId: "case-orphaned-install",
            ClusterKey: "cluster-orphaned-install",
            Kind: SupportCaseKinds.InstallHelp,
            Status: SupportCaseStatuses.ReleasedToReporterChannel,
            Title: "Preview fix needs relinked install",
            Summary: "The affected install is no longer linked.",
            Detail: "Relink is required before the fix can be picked up.",
            CandidateOwnerRepo: "chummer6-hub",
            DesignImpactSuspected: false,
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
            Source: SupportCaseSourceKinds.HubAccount,
            ReporterUserId: "usr-1",
            ReporterSubjectId: "subject-1",
            InstallationId: "install-missing",
            ApplicationVersion: "0.7.0-preview",
            ReleaseChannel: "preview",
            HeadId: "avalonia",
            Platform: "linux",
            Arch: "x64",
            FixedVersion: "0.7.1-preview",
            FixedChannel: "preview");
        var installLinking = new InstallLinkingSummaryDto(
            RecentReceipts: Array.Empty<DownloadReceiptDto>(),
            PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
            ClaimedInstallations:
            [
                new ClaimedInstallationDto(
                    InstallationId: "install-other",
                    ArtifactId: "avalonia-linux-x64-installer",
                    Channel: "preview",
                    Version: "0.7.0-preview",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: DateTimeOffset.Parse("2026-04-14T10:00:00Z"),
                    UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
                    UserId: "usr-1",
                    SubjectId: "subject-1",
                    PublicKey: "pub-1",
                    HeadId: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    HostLabel: "Other Windows"),
            ],
            ActiveGrants: Array.Empty<InstallationGrantDto>());

        var presentation = service.Build(supportCase, installLinking);

        Assert.Equal("Open installs", presentation.PrimaryActionLabel);
        Assert.Equal("/account/access", presentation.PrimaryActionHref);
        Assert.True(presentation.NeedsLinkedInstall);
        Assert.Contains("Relink or reclaim the affected copy in Installs", presentation.NextSafeAction, StringComparison.Ordinal);
        Assert.Contains("return to that claimed install", presentation.NextSafeAction, StringComparison.Ordinal);
        Assert.DoesNotContain("same linked install", presentation.NextSafeAction, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Build_ConfirmedFixedInstallRailCaseKeepsUpdateAndReopenGuidanceVisible()
    {
        var service = new SupportCasePresentationService();
        var supportCase = new SupportCaseProjection(
            CaseId: "case-confirmed-install",
            ClusterKey: "cluster-confirmed-install",
            Kind: SupportCaseKinds.InstallHelp,
            Status: SupportCaseStatuses.UserNotified,
            Title: "Preview fix already confirmed",
            Summary: "The linked install already verified the fix.",
            Detail: "Reporter confirmed the install-aware fix.",
            CandidateOwnerRepo: "chummer6-hub",
            DesignImpactSuspected: false,
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
            Source: SupportCaseSourceKinds.HubAccount,
            ReporterUserId: "usr-1",
            ReporterSubjectId: "subject-1",
            InstallationId: "install-1",
            ApplicationVersion: "0.7.0-preview",
            ReleaseChannel: "preview",
            HeadId: "avalonia",
            Platform: "linux",
            Arch: "x64",
            FixedVersion: "0.7.1-preview",
            FixedChannel: "preview",
            ReporterVerificationState: SupportCaseVerificationStates.ConfirmedFixed,
            ReporterVerifiedAtUtc: DateTimeOffset.Parse("2026-04-15T02:00:00Z"));
        var installLinking = new InstallLinkingSummaryDto(
            RecentReceipts: Array.Empty<DownloadReceiptDto>(),
            PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
            ClaimedInstallations:
            [
                new ClaimedInstallationDto(
                    InstallationId: "install-1",
                    ArtifactId: "avalonia-linux-x64-installer",
                    Channel: "preview",
                    Version: "0.7.1-preview",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: DateTimeOffset.Parse("2026-04-14T10:00:00Z"),
                    UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T02:00:00Z"),
                    UserId: "usr-1",
                    SubjectId: "subject-1",
                    PublicKey: "pub-1",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    HostLabel: "Table Linux"),
            ],
            ActiveGrants: Array.Empty<InstallationGrantDto>());

        var presentation = service.Build(supportCase, installLinking);

        Assert.Equal("Closed and confirmed", presentation.StageLabel);
        Assert.False(presentation.NeedsLinkedInstall);
        Assert.Contains("Update the affected claimed install normally", presentation.NextSafeAction, StringComparison.Ordinal);
        Assert.Contains("Reopen this same case", presentation.NextSafeAction, StringComparison.Ordinal);
        Assert.DoesNotContain("Open installs", presentation.NextSafeAction, StringComparison.Ordinal);
        Assert.Contains("stays linked on preview 0.7.1-preview", presentation.InstallReadinessSummary, StringComparison.Ordinal);
    }
}
