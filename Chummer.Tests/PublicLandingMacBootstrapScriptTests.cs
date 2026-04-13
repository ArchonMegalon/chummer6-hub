using System.Reflection;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingMacBootstrapScriptTests
{
    [Fact]
    public void ResolveMacBootstrapArtifactsIncludesAllMatchingMacDesktopHeadsForTheAccessClass()
    {
        PublicReleaseManifestDto manifest = new(
            Version: "run-20260402-220000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-02T22:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "a1",
                    SizeBytes: 100,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "blazor-desktop-osx-arm64-installer",
                    Platform: "Blazor Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-blazor-desktop-osx-arm64-installer.dmg",
                    Sha256: "b2",
                    SizeBytes: 200,
                    Head: "blazor-desktop",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-x64-installer",
                    Platform: "Avalonia Desktop macOS X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
                    Sha256: "c3",
                    SizeBytes: 300,
                    Head: "avalonia",
                    PlatformId: "osx-x64",
                    Arch: "x64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-x64-installer.dmg",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "manual-osx-arm64-portable",
                    Platform: "Manual macOS ARM64 Portable",
                    Url: "/downloads/files/chummer-osx-arm64.tar.gz",
                    Sha256: "d4",
                    SizeBytes: 400,
                    Head: "portable",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "archive",
                    FileName: "chummer-osx-arm64.tar.gz",
                    InstallAccessClass: "open_public")
            ]);

        IReadOnlyList<PublicReleaseArtifactDto> artifacts = PublicLandingController.ResolveMacBootstrapArtifacts(
            manifest,
            manifest.Downloads[0]);

        Assert.Collection(
            artifacts,
            item => Assert.Equal("avalonia-osx-arm64-installer", item.Id),
            item => Assert.Equal("blazor-desktop-osx-arm64-installer", item.Id),
            item => Assert.Equal("avalonia-osx-x64-installer", item.Id));
    }

    [Fact]
    public void ResolveMacBootstrapArtifactsKeepsMatchingAccessClassButExcludesDifferentAccessClasses()
    {
        PublicReleaseManifestDto manifest = new(
            Version: "run-20260402-220000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-02T22:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-x64-installer",
                    Platform: "Avalonia Desktop macOS X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
                    Sha256: "a1",
                    SizeBytes: 100,
                    Head: "avalonia",
                    PlatformId: "osx-x64",
                    Arch: "x64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-x64-installer.dmg",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "blazor-desktop-osx-x64-installer",
                    Platform: "Blazor Desktop macOS X64 Installer",
                    Url: "/downloads/files/chummer-blazor-desktop-osx-x64-installer.dmg",
                    Sha256: "b2",
                    SizeBytes: 200,
                    Head: "blazor-desktop",
                    PlatformId: "osx-x64",
                    Arch: "x64",
                    Kind: "dmg",
                    FileName: "chummer-blazor-desktop-osx-x64-installer.dmg",
                    InstallAccessClass: "open_public"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "c3",
                    SizeBytes: 300,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required")
            ]);

        IReadOnlyList<PublicReleaseArtifactDto> artifacts = PublicLandingController.ResolveMacBootstrapArtifacts(
            manifest,
            manifest.Downloads[0]);

        Assert.Collection(
            artifacts,
            item => Assert.Equal("avalonia-osx-x64-installer", item.Id),
            item => Assert.Equal("avalonia-osx-arm64-installer", item.Id));
    }

    [Fact]
    public void RenderMacInstallBootstrapScriptIncludesEmbeddedClaimsForDownloadsAndFirstLaunch()
    {
        string script = PublicLandingController.RenderMacInstallBootstrapScript(
            [
                new PublicLandingController.MacInstallBootstrapArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    HeadId: "avalonia",
                    Title: "Avalonia Desktop macOS ARM64 Installer",
                    ShortLabel: "Chummer Avalonia (Apple Silicon)",
                    DownloadUrl: "https://chummer.run/downloads/file/avalonia-osx-arm64-installer",
                    ClaimCode: "AAAAA-BBBBB-CCCCC-DDDDD",
                    Sha256: "sha-a",
                    DmgName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Architecture: "arm64",
                    LaunchAfterInstall: true),
                new PublicLandingController.MacInstallBootstrapArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-installer",
                    HeadId: "blazor-desktop",
                    Title: "Blazor Desktop macOS ARM64 Installer",
                    ShortLabel: "Chummer Blazor Desktop (Apple Silicon)",
                    DownloadUrl: "https://chummer.run/downloads/file/blazor-desktop-osx-arm64-installer",
                    ClaimCode: "EEEEE-FFFFF-GGGGG-HHHHH",
                    Sha256: "sha-b",
                    DmgName: "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    Architecture: "arm64",
                    LaunchAfterInstall: false)
            ],
            publicBaseUrl: "https://chummer.run/",
            accountUrl: "https://chummer.run/account/access",
            downloadsUrl: "https://chummer.run/downloads",
            helpUrl: "https://chummer.run/help");

        Assert.Contains("Avalonia Desktop macOS ARM64 Installer", script, StringComparison.Ordinal);
        Assert.Contains("Blazor Desktop macOS ARM64 Installer", script, StringComparison.Ordinal);
        Assert.Contains("Chummer Avalonia (Apple Silicon)", script, StringComparison.Ordinal);
        Assert.Contains("Chummer Blazor Desktop (Apple Silicon)", script, StringComparison.Ordinal);
        Assert.Contains("https://chummer.run/downloads/file/avalonia-osx-arm64-installer", script, StringComparison.Ordinal);
        Assert.Contains("CLAIM_CODES", script, StringComparison.Ordinal);
        Assert.Contains("AAAAA-BBBBB-CCCCC-DDDDD", script, StringComparison.Ordinal);
        Assert.Contains("build_claim_download_url()", script, StringComparison.Ordinal);
        Assert.Contains("claimCode=", script, StringComparison.Ordinal);
        Assert.Contains("HEAD_IDS", script, StringComparison.Ordinal);
        Assert.Contains("chummer-avalonia-osx-arm64-installer.dmg", script, StringComparison.Ordinal);
        Assert.Contains("chummer-blazor-desktop-osx-arm64-installer.dmg", script, StringComparison.Ordinal);
        Assert.Contains("choose from list choiceItems", script, StringComparison.Ordinal);
        Assert.Contains("default items defaultItems", script, StringComparison.Ordinal);
        Assert.Contains("buttons {\"Choose manually\", \"Auto select\"}", script, StringComparison.Ordinal);
        Assert.Contains("default button \"Auto select\"", script, StringComparison.Ordinal);
        Assert.Contains("display dialog \"Choose where to install the selected apps.\"", script, StringComparison.Ordinal);
        Assert.Contains("display dialog \"After Chummer finishes installing", script, StringComparison.Ordinal);
        Assert.Contains("display dialog \"Where should Chummer leave quick access after setup?\"", script, StringComparison.Ordinal);
        Assert.Contains("Applications Folder", script, StringComparison.Ordinal);
        Assert.Contains("render_progress_bar()", script, StringComparison.Ordinal);
        Assert.Contains("run_privileged_script()", script, StringComparison.Ordinal);
        Assert.Contains("perform_staged_install()", script, StringComparison.Ordinal);
        Assert.Contains("launch_bundle_binary_with_claim()", script, StringComparison.Ordinal);
        Assert.Contains("create_desktop_link()", script, StringComparison.Ordinal);
        Assert.Contains("verify_download_digest()", script, StringComparison.Ordinal);
        Assert.Contains("SHA256_DIGESTS", script, StringComparison.Ordinal);
        Assert.Contains("Current Mac architecture", script, StringComparison.Ordinal);
        Assert.Contains("Rosetta", script, StringComparison.Ordinal);
        Assert.Contains("Quick access: $SHORTCUT_DESCRIPTION", script, StringComparison.Ordinal);
        Assert.Contains("INSTALL_SCOPE_DESCRIPTION", script, StringComparison.Ordinal);
        Assert.Contains("SELECTED_INDEXES", script, StringComparison.Ordinal);
        Assert.Contains("DEFAULT_SELECTED_INDEXES", script, StringComparison.Ordinal);
        Assert.Contains("DEFAULT_APP_CHOICES", script, StringComparison.Ordinal);
        Assert.Contains("seed_default_selected_indexes()", script, StringComparison.Ordinal);
        Assert.Contains("default_app_choices_summary()", script, StringComparison.Ordinal);
        Assert.Contains("run_gui_dialog select-app-mode", script, StringComparison.Ordinal);
        Assert.Contains("resolve_install_state_root()", script, StringComparison.Ordinal);
        Assert.Contains("build_install_state_path()", script, StringComparison.Ordinal);
        Assert.Contains("read_install_state_field()", script, StringComparison.Ordinal);
        Assert.Contains("run_gui_dialog select-apps \"${#DEFAULT_APP_CHOICES[@]}\" \"${DEFAULT_APP_CHOICES[@]}\" \"${APP_CHOICES[@]}\"", script, StringComparison.Ordinal);
        Assert.Contains("wait_for_claim_success \"$state_path\" 25", script, StringComparison.Ordinal);
        Assert.Contains("claimed_at=\"$(read_install_state_field \"$state_path\" claimedAtUtc || true)\"", script, StringComparison.Ordinal);
        Assert.Contains("Selected build: ${APP_CHOICES[$idx]}", script, StringComparison.Ordinal);
        Assert.Contains("Published artifact: ${ARTIFACT_TITLES[$idx]}", script, StringComparison.Ordinal);
        Assert.Contains("Confirmed linked installs: $LINKED_CONFIRMED_COUNT / ${#INSTALLED_APPS[@]}", script, StringComparison.Ordinal);
        Assert.Contains("COMPLETION_MESSAGE=", script, StringComparison.Ordinal);
        Assert.Contains("Installed Mac desktop builds:", script, StringComparison.Ordinal);
        Assert.Contains("launch_installed_app()", script, StringComparison.Ordinal);
        Assert.Contains("PUBLIC_BASE_URL='https://chummer.run/'", script, StringComparison.Ordinal);
        Assert.Contains("env CHUMMER_INSTALL_CLAIM_CODE=\"$claim_code\" CHUMMER_API_BASE_URL=\"$PUBLIC_BASE_URL\" CHUMMER_WEB_BASE_URL=\"$PUBLIC_BASE_URL\" \"$executable_path\"", script, StringComparison.Ordinal);
        Assert.Contains("printf '%s' \"$!\"", script, StringComparison.Ordinal);
        Assert.Contains("kill \"$launch_pid\"", script, StringComparison.Ordinal);
        Assert.Contains("wait \"$launch_pid\" >/dev/null 2>&1 || true", script, StringComparison.Ordinal);
        Assert.Contains("open -n \"$target_app\" >/dev/null 2>&1 || true", script, StringComparison.Ordinal);
        Assert.DoesNotContain("xattr -dr com.apple.quarantine", script, StringComparison.Ordinal);
        Assert.DoesNotContain("rm -rf \"$target_app\"", script, StringComparison.Ordinal);
        Assert.DoesNotContain("--install-claim-code", script, StringComparison.Ordinal);
        Assert.DoesNotContain("pkill -f \"$target_app/Contents/MacOS\"", script, StringComparison.Ordinal);
        Assert.DoesNotContain("pbcopy", script, StringComparison.Ordinal);
        Assert.DoesNotContain("Claim codes copied to clipboard", script, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildMacBootstrapTerminalCommandUsesPipefailCurlAndBash()
    {
        string command = PublicLandingController.BuildMacBootstrapTerminalCommand(
            "https://chummer.run/install-abc123def456.sh");

        Assert.Equal(
            "set -o pipefail; curl -fsSL 'https://chummer.run/install-abc123def456.sh' | /bin/bash",
            command);
    }

    [Theory]
    [InlineData(nameof(PublicLandingController.ReleaseUploadBootstrapScript))]
    [InlineData(nameof(PublicLandingController.DownloadDispatchBootstrapScript))]
    [InlineData(nameof(PublicLandingController.DownloadDispatchPersonalizedMacBootstrapScript))]
    [InlineData(nameof(PublicLandingController.DownloadDispatchWindowsBootstrapScript))]
    [InlineData(nameof(PublicLandingController.DownloadDispatchLinuxBootstrapScript))]
    public void BootstrapEndpointsAdvertiseProblemJsonForFailureNegotiation(string methodName)
    {
        MethodInfo method = typeof(PublicLandingController).GetMethod(methodName)
            ?? throw new InvalidOperationException($"missing controller method {methodName}");

        ProducesAttribute produces = method.GetCustomAttribute<ProducesAttribute>()
            ?? throw new InvalidOperationException($"missing ProducesAttribute on {methodName}");

        Assert.Contains("application/problem+json", produces.ContentTypes, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void ReleaseUploadBootstrapTemplateUsesStrictSafeStartupSmokeHostClassDefault()
    {
        string templatePath = Path.GetFullPath(Path.Combine(
            AppContext.BaseDirectory,
            "..",
            "..",
            "..",
            "..",
            "Chummer.Run.Api",
            "wwwroot",
            "artifacts",
            "mac-codex-release-pipeline",
            "bootstrap.sh"));

        string template = File.ReadAllText(templatePath);

        Assert.Contains(
            "local startup_host_class=\"${CHUMMER_DESKTOP_STARTUP_SMOKE_HOST_CLASS:-}\"",
            template,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "local startup_host_class=\"$CHUMMER_DESKTOP_STARTUP_SMOKE_HOST_CLASS\"",
            template,
            StringComparison.Ordinal);
    }

    [Fact]
    public void ResolveGuidedBootstrapArtifactsIncludesMatchingWindowsDesktopHeadsForTheAccessClass()
    {
        PublicReleaseManifestDto manifest = new(
            Version: "run-20260403-150000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-03T15:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "w1",
                    SizeBytes: 101,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "blazor-desktop-win-x64-installer",
                    Platform: "Blazor Desktop Windows x64 Installer",
                    Url: "/downloads/files/chummer-blazor-desktop-win-x64-installer.exe",
                    Sha256: "w2",
                    SizeBytes: 202,
                    Head: "blazor-desktop",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-blazor-desktop-win-x64-installer.exe",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-arm64-installer",
                    Platform: "Avalonia Desktop Windows ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-arm64-installer.exe",
                    Sha256: "w3",
                    SizeBytes: 303,
                    Head: "avalonia",
                    PlatformId: "win-arm64",
                    Arch: "arm64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-arm64-installer.exe",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "l1",
                    SizeBytes: 404,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "account_required")
            ]);

        IReadOnlyList<PublicReleaseArtifactDto> artifacts = PublicLandingController.ResolveGuidedBootstrapArtifacts(
            manifest,
            manifest.Downloads[0]);

        Assert.Collection(
            artifacts,
            item => Assert.Equal("avalonia-win-x64-installer", item.Id),
            item => Assert.Equal("blazor-desktop-win-x64-installer", item.Id),
            item => Assert.Equal("avalonia-win-arm64-installer", item.Id));
    }

    [Fact]
    public void RenderWindowsInstallBootstrapScriptIncludesGuidedSelectionAndShortcutChoices()
    {
        string script = PublicLandingController.RenderWindowsInstallBootstrapScript(
            [
                new PublicLandingController.GuidedBootstrapArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    HeadId: "avalonia",
                    Title: "Avalonia Desktop Windows x64 Installer",
                    ShortLabel: "Chummer Avalonia (x64)",
                    DownloadUrl: "https://chummer.run/downloads/file/avalonia-win-x64-installer?ticket=T-1",
                    ClaimUrl: "https://chummer.run/downloads/install/avalonia-win-x64-installer/claim.json?ticket=T-1",
                    Sha256: "sha-a",
                    PackageName: "chummer-avalonia-win-x64-installer.exe",
                    Architecture: "x64",
                    LaunchAfterInstall: true,
                    InstallFolderName: "avalonia-win-x64",
                    ExecutableName: "Chummer.Avalonia.exe",
                    LauncherName: "chummer6-avalonia",
                    DesktopEntryName: "chummer6-avalonia.desktop"),
                new PublicLandingController.GuidedBootstrapArtifact(
                    ArtifactId: "blazor-desktop-win-x64-installer",
                    HeadId: "blazor-desktop",
                    Title: "Blazor Desktop Windows x64 Installer",
                    ShortLabel: "Chummer Blazor Desktop (x64)",
                    DownloadUrl: "https://chummer.run/downloads/file/blazor-desktop-win-x64-installer?ticket=T-1",
                    ClaimUrl: "https://chummer.run/downloads/install/blazor-desktop-win-x64-installer/claim.json?ticket=T-1",
                    Sha256: "sha-b",
                    PackageName: "chummer-blazor-desktop-win-x64-installer.exe",
                    Architecture: "x64",
                    LaunchAfterInstall: false,
                    InstallFolderName: "blazor-desktop-win-x64",
                    ExecutableName: "Chummer.Blazor.Desktop.exe",
                    LauncherName: "chummer6-blazor-desktop",
                    DesktopEntryName: "chummer6-blazor-desktop.desktop")
            ],
            publicBaseUrl: "https://chummer.run/",
            accountUrl: "https://chummer.run/account/access",
            downloadsUrl: "https://chummer.run/downloads",
            helpUrl: "https://chummer.run/help");

        Assert.Contains("ConvertFrom-Json", script, StringComparison.Ordinal);
        Assert.Contains("Auto select", script, StringComparison.Ordinal);
        Assert.Contains("Choose manually", script, StringComparison.Ordinal);
        Assert.Contains("Show-ChecklistDialog", script, StringComparison.Ordinal);
        Assert.Contains("Resolve-InstallRoot", script, StringComparison.Ordinal);
        Assert.Contains("Start menu only", script, StringComparison.Ordinal);
        Assert.Contains("Desktop links", script, StringComparison.Ordinal);
        Assert.Contains("--bootstrap-install", script, StringComparison.Ordinal);
        Assert.Contains("--start-menu-shortcut", script, StringComparison.Ordinal);
        Assert.Contains("--desktop-shortcut", script, StringComparison.Ordinal);
        Assert.Contains("--install-claim-code", script, StringComparison.Ordinal);
        Assert.Contains("ClaimUrl", script, StringComparison.Ordinal);
        Assert.Contains("Get-InstallClaimCode", script, StringComparison.Ordinal);
        Assert.Contains("$env:PROCESSOR_ARCHITEW6432", script, StringComparison.Ordinal);
        Assert.Contains("Prepared first-open account linking", script, StringComparison.Ordinal);
        Assert.Contains("Installed Windows desktop builds:", script, StringComparison.Ordinal);
        Assert.Contains("Chummer Avalonia (x64)", script, StringComparison.Ordinal);
        Assert.Contains("Chummer Blazor Desktop (x64)", script, StringComparison.Ordinal);
        Assert.Contains("Chummer.Avalonia.exe", script, StringComparison.Ordinal);
        Assert.Contains("Chummer.Blazor.Desktop.exe", script, StringComparison.Ordinal);
        Assert.DoesNotContain("Artifact.ClaimCode", script, StringComparison.Ordinal);
        Assert.DoesNotContain("??", script, StringComparison.Ordinal);
    }

    [Fact]
    public void RenderLinuxInstallBootstrapScriptIncludesGuidedSelectionAndDesktopLinkChoices()
    {
        string script = PublicLandingController.RenderLinuxInstallBootstrapScript(
            [
                new PublicLandingController.GuidedBootstrapArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    HeadId: "avalonia",
                    Title: "Avalonia Desktop Linux x64 Installer",
                    ShortLabel: "Chummer Avalonia (x64)",
                    DownloadUrl: "https://chummer.run/downloads/file/avalonia-linux-x64-installer?ticket=T-1",
                    ClaimUrl: "https://chummer.run/downloads/install/avalonia-linux-x64-installer/claim.json?ticket=T-1",
                    Sha256: "sha-a",
                    PackageName: "chummer-avalonia-linux-x64-installer.deb",
                    Architecture: "x64",
                    LaunchAfterInstall: true,
                    InstallFolderName: "avalonia-linux-x64",
                    ExecutableName: "Chummer.Avalonia",
                    LauncherName: "chummer6-avalonia",
                    DesktopEntryName: "chummer6-avalonia.desktop"),
                new PublicLandingController.GuidedBootstrapArtifact(
                    ArtifactId: "blazor-desktop-linux-x64-installer",
                    HeadId: "blazor-desktop",
                    Title: "Blazor Desktop Linux x64 Installer",
                    ShortLabel: "Chummer Blazor Desktop (x64)",
                    DownloadUrl: "https://chummer.run/downloads/file/blazor-desktop-linux-x64-installer?ticket=T-1",
                    ClaimUrl: "https://chummer.run/downloads/install/blazor-desktop-linux-x64-installer/claim.json?ticket=T-1",
                    Sha256: "sha-b",
                    PackageName: "chummer-blazor-desktop-linux-x64-installer.deb",
                    Architecture: "x64",
                    LaunchAfterInstall: false,
                    InstallFolderName: "blazor-desktop-linux-x64",
                    ExecutableName: "Chummer.Blazor.Desktop",
                    LauncherName: "chummer6-blazor-desktop",
                    DesktopEntryName: "chummer6-blazor-desktop.desktop")
            ],
            publicBaseUrl: "https://chummer.run/",
            accountUrl: "https://chummer.run/account/access",
            downloadsUrl: "https://chummer.run/downloads",
            helpUrl: "https://chummer.run/help");

        Assert.Contains("choose_mode", script, StringComparison.Ordinal);
        Assert.Contains("choose_manual_indexes", script, StringComparison.Ordinal);
        Assert.Contains("Applications menu only", script, StringComparison.Ordinal);
        Assert.Contains("Desktop links", script, StringComparison.Ordinal);
        Assert.Contains("verify_download_digest", script, StringComparison.Ordinal);
        Assert.Contains("dpkg-deb -x", script, StringComparison.Ordinal);
        Assert.Contains("build_install_state_path", script, StringComparison.Ordinal);
        Assert.Contains("build_pending_claim_code_path", script, StringComparison.Ordinal);
        Assert.Contains("persist_pending_claim_code", script, StringComparison.Ordinal);
        Assert.Contains("CLAIM_URLS=()", script, StringComparison.Ordinal);
        Assert.Contains("fetch_install_claim_code()", script, StringComparison.Ordinal);
        Assert.Contains("Icon=${icon_target}", script, StringComparison.Ordinal);
        Assert.Contains("Prepared first-open account linking", script, StringComparison.Ordinal);
        Assert.Contains("Installed Linux desktop builds:", script, StringComparison.Ordinal);
        Assert.Contains("chummer6-avalonia.desktop", script, StringComparison.Ordinal);
        Assert.Contains("chummer6-blazor-desktop.desktop", script, StringComparison.Ordinal);
        Assert.DoesNotContain("claimCode=", script, StringComparison.Ordinal);
    }
}
