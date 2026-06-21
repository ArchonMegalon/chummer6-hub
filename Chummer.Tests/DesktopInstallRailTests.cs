using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Xunit;

namespace Chummer.Tests;

public sealed class DesktopInstallRailTests
{
    [Fact]
    public void BuildSupportHref_PreservesArtifactAndRecoveryContextWithoutInventingInstallId()
    {
        PublicReleaseArtifactDto artifact = new(
            Id: "avalonia-linux-x64-installer",
            Platform: "Avalonia Linux Installer",
            Url: "/downloads/file/avalonia-linux-x64-installer",
            Sha256: "abc",
            SizeBytes: 42,
            Head: "avalonia",
            PlatformId: "linux-x64",
            Arch: "x64",
            Kind: "deb",
            FileName: "chummer-avalonia-linux-x64-installer.deb",
            InstallAccessClass: "account_required");
        PublicReleaseManifestDto manifest = new(
            Version: "0.7.0-preview",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-14T00:00:00Z"),
            Downloads: [artifact]);

        string href = DesktopInstallRail.BuildSupportHref(artifact, manifest, installationId: null, recoveryMode: true);

        Assert.Contains("artifactId=avalonia-linux-x64-installer", href, StringComparison.Ordinal);
        Assert.Contains("recoveryMode=true", href, StringComparison.Ordinal);
        Assert.DoesNotContain("installationId=", href, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildSupportHref_CanPrefillAffectedInstalledBuildForClaimedContinuation()
    {
        PublicReleaseArtifactDto artifact = new(
            Id: "avalonia-linux-x64-installer",
            Platform: "Avalonia Linux Installer",
            Url: "/downloads/file/avalonia-linux-x64-installer",
            Sha256: "abc",
            SizeBytes: 42,
            Head: "avalonia",
            PlatformId: "linux",
            Arch: "x64",
            Kind: "deb",
            FileName: "chummer-avalonia-linux-x64-installer.deb",
            InstallAccessClass: "account_required");
        PublicReleaseManifestDto manifest = new(
            Version: "0.7.1-preview",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            Downloads: [artifact]);

        string href = DesktopInstallRail.BuildSupportHref(
            artifact,
            manifest,
            installationId: "install-native",
            recoveryMode: false,
            applicationVersion: "0.7.0-preview",
            releaseChannel: "preview",
            headId: "avalonia",
            platform: "linux",
            arch: "x64");

        Assert.Contains("installationId=install-native", href, StringComparison.Ordinal);
        Assert.Contains("applicationVersion=0.7.0-preview", href, StringComparison.Ordinal);
        Assert.DoesNotContain("applicationVersion=0.7.1-preview", href, StringComparison.Ordinal);
        Assert.Contains("releaseChannel=preview", href, StringComparison.Ordinal);
        Assert.Contains("headId=avalonia", href, StringComparison.Ordinal);
        Assert.Contains("platform=linux", href, StringComparison.Ordinal);
        Assert.Contains("arch=x64", href, StringComparison.Ordinal);
    }

    [Fact]
    public void ResolveSupportIntakeRail_ReturnsGuidedInstallerContext()
    {
        DesktopInstallRailContext context = DesktopInstallRail.ResolveSupportIntakeRail("avalonia-linux-x64-installer", recoveryMode: true);

        Assert.Equal("/downloads/install/avalonia-linux-x64-installer", context.ReturnHref);
        Assert.Equal("Return to recovery", context.ReturnLabel);
        Assert.True(context.RecoveryModeOnly);
        Assert.Contains("same linked copy", context.Summary!, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("retry", context.Summary!, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("recovery mode", context.Summary!, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("install rail", context.Summary!, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildContinuationReceipt_CarriesBuildFallbackUpdateAndRollbackTruth()
    {
        PublicReleaseArtifactDto artifact = new(
            Id: "avalonia-linux-x64-installer",
            Platform: "Avalonia Linux Installer",
            Url: "/downloads/file/avalonia-linux-x64-installer",
            Sha256: "abc",
            SizeBytes: 42,
            Head: "avalonia",
            PlatformId: "linux-x64",
            Arch: "x64",
            Kind: "deb",
            FileName: "chummer-avalonia-linux-x64-installer.deb",
            InstallAccessClass: "account_required");
        PublicReleaseManifestDto manifest = new(
            Version: "0.7.1-preview",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            Downloads: [artifact]);

        DesktopInstallContinuationReceipt receipt = DesktopInstallRail.BuildContinuationReceipt(
            artifact,
            manifest,
            recoveryMode: true);

        Assert.Equal("avalonia-linux-x64-installer", receipt.ArtifactId);
        Assert.Equal("0.7.1-preview", receipt.ApplicationVersion);
        Assert.Equal("preview", receipt.ReleaseChannel);
        Assert.Equal("avalonia", receipt.HeadId);
        Assert.Equal("linux-x64", receipt.PlatformId);
        Assert.Contains("Recovery fallback only", receipt.FallbackPosture, StringComparison.Ordinal);
        Assert.Contains("desktop update screen", receipt.UpdateAction, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("update lane", receipt.UpdateAction, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("setup assistant", receipt.UpdateAction, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("previous installed copy", receipt.RollbackAction, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("same linked copy", receipt.RollbackAction, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("install rail", receipt.RollbackAction, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("continuation rail", receipt.RollbackAction, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("linked copy", receipt.SupportContinuation, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("install rail", receipt.SupportContinuation, StringComparison.OrdinalIgnoreCase);
    }
}
