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
        bool recoveryMode)
        => QueryHelpers.AddQueryString(
            "/contact",
            new Dictionary<string, string?>
            {
                ["artifactId"] = artifact.Id,
                ["kind"] = SupportCaseKinds.InstallHelp,
                ["title"] = $"Install help for {BuildGuidedBootstrapArtifactTitle(artifact)}",
                ["summary"] = recoveryMode
                    ? "Setup entered recovery or needed a relink step during install."
                    : "Install, first launch, or update follow-through needs help on this device.",
                ["detail"] = recoveryMode
                    ? "The signed-in installer or recovery flow needs help on this device. Continue the fix on the same install rail."
                    : "The signed-in installer, first launch, or update handoff needs help on this device. Continue the fix on the same install rail.",
                ["installationId"] = installationId,
                ["applicationVersion"] = manifest.Version,
                ["releaseChannel"] = manifest.Channel,
                ["headId"] = artifact.Head,
                ["platform"] = NormalizeSupportPrefill(artifact.PlatformId) ?? NormalizeSupportPrefill(artifact.Platform),
                ["arch"] = artifact.Arch,
                ["recoveryMode"] = recoveryMode ? "true" : "false"
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
            ReturnLabel: recoveryMode ? "Return to recovery handoff" : "Return to guided installer",
            Summary: recoveryMode
                ? "This case stays on the same install rail. Go back to the guided handoff when you are ready to retry recovery, and only use a recovery code if Chummer entered recovery mode on that device."
                : "This case stays on the same install rail. Go back to the guided handoff when you are ready to retry install, first launch, or update follow-through on that device.",
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
                : "Continue in the installer or desktop app so the linked install can claim this account without a browser handoff.",
            UpdateAction: "Use the desktop app update lane or signed-in setup assistant for this same channel and build lineage before filing a new support case.",
            RollbackAction: "If update or setup fails, keep the previous installed copy and return to Devices and access or tracked support on this same install rail.",
            SupportContinuation: "Support follow-through stays on the same install rail with the current claim, build, channel, fallback, and recovery context attached.");
    }

    private static string BuildGuidedBootstrapArtifactTitle(PublicReleaseArtifactDto artifact)
        => string.IsNullOrWhiteSpace(artifact.Platform)
            ? artifact.Id
            : string.IsNullOrWhiteSpace(artifact.Head)
                ? artifact.Platform
                : $"{artifact.Platform} {artifact.Head}";

    private static string? NormalizeSupportPrefill(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
