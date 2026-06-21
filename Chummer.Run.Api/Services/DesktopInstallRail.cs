using Chummer.Control.Contracts.Support;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.WebUtilities;

namespace Chummer.Run.Api.Services;

internal sealed record DesktopInstallRailContext(
    string? ReturnHref,
    string? ReturnLabel,
    string? Summary,
    bool RecoveryModeOnly)
{
    public static DesktopInstallRailContext None { get; } = new(null, null, null, false);
}

internal sealed record DesktopInstallContinuationReceipt(
    string ArtifactId,
    string ApplicationVersion,
    string ReleaseChannel,
    string? HeadId,
    string? Platform,
    string? PlatformId,
    string? Arch,
    string FallbackPosture,
    string NextSafeAction,
    string UpdateAction,
    string RollbackAction,
    string SupportContinuation);

internal static class DesktopInstallRail
{
    internal static string BuildSupportHref(
        PublicReleaseArtifactDto artifact,
        PublicReleaseManifestDto manifest,
        string? installationId,
        bool recoveryMode,
        string? applicationVersion = null,
        string? releaseChannel = null,
        string? headId = null,
        string? platform = null,
        string? arch = null,
        string? installedBuildReceiptId = null)
        => QueryHelpers.AddQueryString(
            "/contact",
            new Dictionary<string, string?>
            {
                ["artifactId"] = artifact.Id,
                ["kind"] = SupportCaseKinds.InstallHelp,
                ["title"] = $"Install help for {BuildGuidedBootstrapArtifactTitle(artifact)}",
                ["summary"] = recoveryMode
                    ? "Setup entered recovery or needed a relink step during install."
                    : "Install, first launch, or update needs help on this device.",
                ["detail"] = BuildSupportDetail(recoveryMode, installedBuildReceiptId),
                ["installationId"] = installationId,
                ["applicationVersion"] = NormalizeSupportPrefill(applicationVersion) ?? manifest.Version,
                ["releaseChannel"] = NormalizeSupportPrefill(releaseChannel) ?? manifest.Channel,
                ["headId"] = NormalizeSupportPrefill(headId) ?? artifact.Head,
                ["platform"] = NormalizeSupportPrefill(platform)
                    ?? NormalizeSupportPrefill(artifact.PlatformId)
                    ?? NormalizeSupportPrefill(artifact.Platform),
                ["arch"] = NormalizeSupportPrefill(arch) ?? artifact.Arch,
                ["installedBuildReceiptId"] = NormalizeSupportPrefill(installedBuildReceiptId),
                ["recoveryMode"] = recoveryMode ? "true" : "false"
            });

    internal static string BuildAccountSupportHref(
        string? installationId,
        string? applicationVersion,
        string? releaseChannel,
        string? headId,
        string? platform,
        string? arch,
        string? installedBuildReceiptId = null)
        => QueryHelpers.AddQueryString(
            "/account/support",
            new Dictionary<string, string?>
            {
                ["kind"] = SupportCaseKinds.InstallHelp,
                ["title"] = "Install help for claimed desktop install",
                ["summary"] = "Install, update, rollback, or support needs help on this linked device.",
                ["detail"] = BuildAccountSupportDetail(installedBuildReceiptId),
                ["installationId"] = NormalizeSupportPrefill(installationId),
                ["applicationVersion"] = NormalizeSupportPrefill(applicationVersion),
                ["releaseChannel"] = NormalizeSupportPrefill(releaseChannel),
                ["headId"] = NormalizeSupportPrefill(headId),
                ["platform"] = NormalizeSupportPrefill(platform),
                ["arch"] = NormalizeSupportPrefill(arch),
                ["installedBuildReceiptId"] = NormalizeSupportPrefill(installedBuildReceiptId)
            });

    internal static DesktopInstallRailContext ResolveSupportIntakeRail(string? artifactId, bool recoveryMode)
    {
        string? normalizedArtifactId = NormalizeSupportPrefill(artifactId);
        if (normalizedArtifactId is null)
        {
            return DesktopInstallRailContext.None;
        }

        return new DesktopInstallRailContext(
            ReturnHref: $"/downloads/install/{Uri.EscapeDataString(normalizedArtifactId)}",
            ReturnLabel: recoveryMode ? "Return to recovery" : "Return to installer",
            Summary: recoveryMode
                ? "This case stays with the same linked copy. Go back to recovery when you are ready to retry, and only use a recovery code if Chummer entered recovery mode on that device."
                : "This case stays with the same linked copy. Go back to the installer when you are ready to retry install, first launch, or update on that device.",
            RecoveryModeOnly: recoveryMode);
    }

    internal static DesktopInstallContinuationReceipt BuildContinuationReceipt(
        PublicReleaseArtifactDto artifact,
        PublicReleaseManifestDto manifest,
        bool recoveryMode)
    {
        ArgumentNullException.ThrowIfNull(artifact);
        ArgumentNullException.ThrowIfNull(manifest);

        return new DesktopInstallContinuationReceipt(
            ArtifactId: artifact.Id,
            ApplicationVersion: manifest.Version,
            ReleaseChannel: manifest.Channel,
            HeadId: NormalizeSupportPrefill(artifact.Head),
            Platform: NormalizeSupportPrefill(artifact.Platform),
            PlatformId: NormalizeSupportPrefill(artifact.PlatformId),
            Arch: NormalizeSupportPrefill(artifact.Arch),
            FallbackPosture: recoveryMode
                ? "Recovery fallback only. Continue the guided setup or in-app update first, and use this claim code only if Chummer says the device entered recovery mode."
                : "Guided setup and in-app update are the default path. Claim codes are a recovery fallback, not a browser redemption step.",
            NextSafeAction: recoveryMode
                ? "Finish setup in Chummer. Only use the recovery code if setup explicitly enters recovery mode."
                : "Continue in the installer or desktop app so the linked copy can claim this account without another browser step.",
            UpdateAction: "Use the desktop update screen or signed-in installer for this same channel and build before filing a new support case.",
            RollbackAction: "If update or setup fails, keep the previous installed copy and return to Devices and access or tracked support for this same linked copy. Keep the fix, update, rollback, and verification on this same linked install.",
            SupportContinuation: "Support stays with this linked copy, including its current claim, build, channel, fallback, and recovery context.");
    }

    private static string BuildGuidedBootstrapArtifactTitle(PublicReleaseArtifactDto artifact)
        => string.IsNullOrWhiteSpace(artifact.PlatformLabel ?? artifact.Platform)
            ? artifact.Id
            : string.IsNullOrWhiteSpace(artifact.Head)
                ? artifact.PlatformLabel ?? artifact.Platform
                : $"{artifact.PlatformLabel ?? artifact.Platform} {artifact.Head}";

    private static string BuildSupportDetail(bool recoveryMode, string? installedBuildReceiptId)
    {
        string baseDetail = recoveryMode
            ? "The signed-in installer or recovery flow needs help on this device. Continue the fix on the same linked copy."
            : "The signed-in installer, first launch, or update step needs help on this device. Continue the fix on the same linked copy.";
        string? receiptId = NormalizeSupportPrefill(installedBuildReceiptId);
        return receiptId is null
            ? baseDetail
            : $"{baseDetail}\n\nInstalled build record: {receiptId}";
    }

    private static string BuildAccountSupportDetail(string? installedBuildReceiptId)
    {
        const string baseDetail = "The desktop app requested help for this linked copy. Keep the fix, update, rollback, and follow-up on this same device.";
        string? receiptId = NormalizeSupportPrefill(installedBuildReceiptId);
        return receiptId is null
            ? baseDetail
            : $"{baseDetail}\n\nInstalled build record: {receiptId}";
    }

    private static string? NormalizeSupportPrefill(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
