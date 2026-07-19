using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
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
    public void BuildMacBootstrapTerminalCommandDownloadsToATempFileBeforeExecution()
    {
        string command = PublicLandingController.BuildMacBootstrapTerminalCommand(
            "https://chummer.run/install-abc123def456-0123456789abcdef.sh");

        Assert.Contains("set -euo pipefail", command, StringComparison.Ordinal);
        Assert.Contains("TMP_BOOTSTRAP_SCRIPT", command, StringComparison.Ordinal);
        Assert.Contains("curl -fsSL 'https://chummer.run/install-abc123def456-0123456789abcdef.sh' -o \"$TMP_BOOTSTRAP_SCRIPT\"", command, StringComparison.Ordinal);
        Assert.Contains("/bin/bash \"$TMP_BOOTSTRAP_SCRIPT\"", command, StringComparison.Ordinal);
        Assert.DoesNotContain("| /bin/bash", command, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildMacBootstrapTerminalCommandPinsDigestWhenProvided()
    {
        string command = PublicLandingController.BuildMacBootstrapTerminalCommand(
            "https://chummer.run/install-abc123def456-0123456789abcdef.sh",
            "abc123");

        Assert.Contains("ACTUAL_BOOTSTRAP_SHA256", command, StringComparison.Ordinal);
        Assert.Contains("shasum -a 256", command, StringComparison.Ordinal);
        Assert.Contains("'abc123'", command, StringComparison.Ordinal);
        Assert.Contains("Setup script check failed; open the signed-in Downloads page and copy a fresh install command.", command, StringComparison.Ordinal);
        Assert.DoesNotContain("downloads handoff", command, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildPersonalizedMacBootstrapScriptPathIncludesRenderedDigestWhenAvailable()
    {
        string path = PublicLandingController.BuildPersonalizedMacBootstrapScriptPath("abc123def456", "0123456789ABCDEF");

        Assert.Equal("/install-abc123def456-0123456789abcdef.sh", path);
    }

    [Fact]
    public void ReleaseUploadBootstrapWrapperDoesNotForceHostedProofOverridesOrEmbedSecrets()
    {
        string script = File.ReadAllText(
            RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "artifacts", "mac-codex-release-pipeline", "bootstrap.sh"));

        Assert.DoesNotContain("export CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_RELEASE_UPLOAD_TOKEN='", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_UI_REF=\"${CHUMMER_UI_REF:-main}\"", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_CORE_REF=\"${CHUMMER_CORE_REF:-main}\"", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_HUB_REF=\"${CHUMMER_HUB_REF:-main}\"", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_UI_KIT_REF=\"${CHUMMER_UI_KIT_REF:-main}\"", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_HUB_REGISTRY_REF=\"${CHUMMER_HUB_REGISTRY_REF:-main}\"", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_MEDIA_FACTORY_REF=\"${CHUMMER_MEDIA_FACTORY_REF:-main}\"", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_LEGACY_REF=\"${CHUMMER_LEGACY_REF:-Docker}\"", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_HUB_REF='main'", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_UI_EXPECTED_COMMIT=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_CORE_EXPECTED_COMMIT=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_HUB_EXPECTED_COMMIT=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_UI_KIT_EXPECTED_COMMIT=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT=", script, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_LEGACY_EXPECTED_COMMIT=", script, StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseUploadBootstrapCommandPinsBothDigestsAndPromptsWithoutEmbeddingAuthorization()
    {
        MethodInfo buildMethod = typeof(PublicLandingController).GetMethod(
            "BuildReleaseUploadBootstrapCommand",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("missing BuildReleaseUploadBootstrapCommand");

        string command = (string)(buildMethod.Invoke(
            obj: null,
            parameters: [
                "https://chummer.run/downloads/release-upload/bootstrap.sh",
                "abc123",
                "https://chummer.run/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
                "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                BuildAuthorityHandoff()]) ?? throw new InvalidOperationException("command build returned null"));

        Assert.StartsWith("set +x; set -euo pipefail;", command, StringComparison.Ordinal);
        Assert.Contains("curl -q -fsSL", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_BOOTSTRAP_EXPECTED_SHA256='abc123'", command, StringComparison.Ordinal);
        Assert.Contains("ACTUAL_BOOTSTRAP_SHA256", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS='1'", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL='https://chummer.run/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json'", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256='dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd'", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK='0'", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE='0'", command, StringComparison.Ordinal);
        Assert.Contains("printf 'Release upload access code: ' >&2; IFS= read -r -s RELEASE_UPLOAD_AUTH", command, StringComparison.Ordinal);
        Assert.DoesNotContain("read -r -s -p", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_TICKET_FILE", command, StringComparison.Ordinal);
        Assert.Contains("current-owner, regular, non-symlink file with mode 600", command, StringComparison.Ordinal);
        Assert.Contains("must contain exactly one UTF-8 line", command, StringComparison.Ordinal);
        Assert.Contains("os.O_NOFOLLOW", command, StringComparison.Ordinal);
        Assert.Contains("AUTHORITY_HANDOFF_B64=", command, StringComparison.Ordinal);
        Assert.Contains("TMP_AUTHORITY_DIR=\"$(mktemp -d)\"", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_TICKET=\"$RELEASE_UPLOAD_AUTH\"", command, StringComparison.Ordinal);
        Assert.DoesNotContain("ticket-xyz", command, StringComparison.Ordinal);
        Assert.DoesNotContain("bootstrap.sh?ticket=", command, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("apiToken=", command, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("CHUMMER_RELEASE_UPLOAD_TOKEN=", command, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_RELEASE_UPLOAD_TICKET=", command, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK='1'", command, StringComparison.Ordinal);
        Assert.DoesNotContain(
            buildMethod.GetParameters(),
            parameter => string.Equals(parameter.Name, "releaseUploadAuth", StringComparison.Ordinal));

        string[] expectedCommitSettings =
        [
            "CHUMMER_UI_EXPECTED_COMMIT",
            "CHUMMER_CORE_EXPECTED_COMMIT",
            "CHUMMER_HUB_EXPECTED_COMMIT",
            "CHUMMER_UI_KIT_EXPECTED_COMMIT",
            "CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT",
            "CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT",
            "CHUMMER_LEGACY_EXPECTED_COMMIT"
        ];
        foreach (string setting in expectedCommitSettings)
        {
            Assert.Contains(setting, command, StringComparison.Ordinal);
        }

        string[] authenticatedAuthoritySettings =
        [
            "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
            "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
            "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
            "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
            "CHUMMER_FLEET_QUEUE_STAGING_PATH",
            "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
            "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
            "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
            "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
            "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY"
        ];
        foreach (string setting in authenticatedAuthoritySettings)
        {
            Assert.Contains(setting + "=", command, StringComparison.Ordinal);
        }

        Assert.Contains("Set reviewed full 40-hex commit pins before running", command, StringComparison.Ordinal);
        Assert.True(
            command.IndexOf("CHUMMER_UI_EXPECTED_COMMIT", StringComparison.Ordinal)
                < command.IndexOf("TMP_BOOTSTRAP_SCRIPT", StringComparison.Ordinal),
            "commit-pin preflight must run before the bootstrap is downloaded");
    }

    [Fact]
    public void ReleaseUploadAuthorityHandoffProjectsAuthenticatedLineageWithoutLocalPaths()
    {
        ReleaseUploadAuthorityHandoff handoff = BuildAuthorityHandoff();

        Assert.StartsWith("public-projection-", handoff.SnapshotId, StringComparison.Ordinal);
        Assert.Equal(5, handoff.Inputs.Count);
        Assert.All(handoff.Inputs, input =>
        {
            Assert.StartsWith(
                $"current-snapshot://{handoff.SnapshotSha256}/{input.Key}/",
                input.Authority,
                StringComparison.Ordinal);
            Assert.Equal(
                Convert.ToHexStringLower(SHA256.HashData(input.Payload)),
                input.Sha256);
            string text = Encoding.UTF8.GetString(input.Payload);
            Assert.Contains(handoff.SnapshotId, text, StringComparison.Ordinal);
            Assert.Contains("sourceAuthority", text, StringComparison.Ordinal);
            Assert.Contains("sourceSha256", text, StringComparison.Ordinal);
            Assert.DoesNotContain("/tmp/", text, StringComparison.Ordinal);
            Assert.DoesNotContain("/docker/", text, StringComparison.Ordinal);
            Assert.DoesNotContain("/Users/", text, StringComparison.Ordinal);
        });

        ReleaseUploadAuthorityInput release = Assert.Single(
            handoff.Inputs,
            static input => input.Key == ReleaseUploadAuthorityHandoffBuilder.ReleaseChannelKey);
        using JsonDocument releaseDocument = JsonDocument.Parse(release.Payload);
        Assert.Equal(
            "chummer.release-upload.release-channel-handoff/v1",
            releaseDocument.RootElement.GetProperty("contractName").GetString());
        Assert.Equal(3, releaseDocument.RootElement.GetProperty("artifacts").GetArrayLength());
    }

    [Fact]
    public void ReleaseUploadCommandRejectsStaleProofAndReachesLocalHubGeneratorWithNoAmbientAuthorityVariables()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        string tempRoot = Path.Combine(
            Path.GetTempPath(),
            "chummer-release-authority-handoff-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        try
        {
            ReleaseUploadAuthorityHandoff handoff = BuildAuthorityHandoff();
            string actualBootstrap = RepoPaths.FromRoot(
                "Chummer.Run.Api",
                "wwwroot",
                "artifacts",
                "mac-codex-release-pipeline",
                "bootstrap.sh");
            string hubAlias = Path.Combine(tempRoot, "hub-alias");
            string hubRepo = Path.Combine(tempRoot, "hub-repo");
            string generator = Path.Combine(
                hubAlias,
                "scripts",
                "materialize_hub_local_release_proof.py");
            string generatedProof = Path.Combine(tempRoot, "generated-proof.json");
            string observedPaths = Path.Combine(tempRoot, "observed-authority-paths.txt");
            string staleProof = Path.Combine(tempRoot, "stale-remote-proof.json");
            string staleProofRejected = Path.Combine(tempRoot, "stale-proof-rejected.txt");
            Directory.CreateDirectory(Path.GetDirectoryName(generator)!);
            Directory.CreateDirectory(hubRepo);
            File.WriteAllText(
                staleProof,
                JsonSerializer.Serialize(new
                {
                    contract_name = "chummer6-hub.local_release_proof",
                    status = "passed",
                    generatedAt = "2000-01-01T00:00:00Z"
                }) + "\n",
                Encoding.UTF8);
            File.WriteAllText(
                generator,
                """
                import datetime
                import hashlib
                import json
                import os
                import pathlib
                import re
                import sys

                commit_names = (
                    "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
                    "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
                )
                handoffs = (
                    ("CHUMMER_HUB_RELEASE_CHANNEL_PATH", "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256", "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY"),
                    ("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH", "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256", "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY"),
                    ("CHUMMER_FLEET_QUEUE_STAGING_PATH", "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256", "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY"),
                    ("CHUMMER_DESIGN_QUEUE_STAGING_PATH", "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256", "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY"),
                    ("CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH", "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256", "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY"),
                )
                assert os.environ.get("CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS") == "1"
                assert all(re.fullmatch(r"[0-9a-f]{40}", os.environ[name]) for name in commit_names)
                for path_name, digest_name, authority_name in handoffs:
                    raw = pathlib.Path(os.environ[path_name]).read_bytes()
                    assert hashlib.sha256(raw).hexdigest() == os.environ[digest_name]
                    assert os.environ[authority_name].startswith("current-snapshot://")
                payload = {
                    "status": "pass",
                    "generatedAt": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "journeysPassed": [
                        "install_claim_restore_continue",
                        "build_explain_publish",
                        "campaign_session_recover_recap",
                        "report_cluster_release_notify",
                        "organize_community_and_close_loop",
                    ],
                    "proof_routes": [
                        "/downloads/install/avalonia-linux-x64-installer",
                        "/home/access", "/home/work", "/account/access", "/account/work",
                        "/account/support", "/contact", "/downloads",
                        "/downloads/install/avalonia-osx-arm64-installer",
                        "/downloads/install/avalonia-win-x64-installer",
                    ],
                }
                pathlib.Path(sys.argv[1]).write_text(json.dumps(payload) + "\n", encoding="utf-8")
                """,
                Encoding.UTF8);

            string wrapper = $$"""
                #!/usr/bin/env bash
                set -euo pipefail
                source {{SingleQuoteForTest(actualBootstrap)}}
                trap cleanup_bootstrap_tmp_paths EXIT
                resolved_proof="$(resolve_hub_local_release_proof_path "${CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL:-}")"
                test -f "$resolved_proof"
                if json_generated_at_health "$resolved_proof" "remote release proof" 86400 300 >/dev/null 2>&1; then
                  echo "stale remote release proof unexpectedly passed freshness" >&2
                  exit 91
                fi
                printf 'rejected\n' > {{SingleQuoteForTest(staleProofRejected)}}
                generate_hub_local_release_proof \
                  {{SingleQuoteForTest(hubAlias)}} \
                  {{SingleQuoteForTest(hubRepo)}} \
                  {{SingleQuoteForTest(generatedProof)}}
                json_generated_at_health \
                  {{SingleQuoteForTest(generatedProof)}} \
                  "generated release proof" \
                  86400 \
                  300
                printf '%s\n' \
                  "$CHUMMER_HUB_RELEASE_CHANNEL_PATH" \
                  "$CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH" \
                  "$CHUMMER_FLEET_QUEUE_STAGING_PATH" \
                  "$CHUMMER_DESIGN_QUEUE_STAGING_PATH" \
                  "$CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH" \
                  > {{SingleQuoteForTest(observedPaths)}}
                """;
            string wrapperPath = Path.Combine(tempRoot, "bootstrap-wrapper.sh");
            File.WriteAllText(wrapperPath, wrapper, Encoding.UTF8);
            string ticketPath = Path.Combine(tempRoot, "release-ticket.txt");
            File.WriteAllText(ticketPath, "fixture-ticket\n", Encoding.UTF8);
            File.SetUnixFileMode(ticketPath, UnixFileMode.UserRead | UnixFileMode.UserWrite);

            MethodInfo buildMethod = typeof(PublicLandingController).GetMethod(
                "BuildReleaseUploadBootstrapCommand",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("missing BuildReleaseUploadBootstrapCommand");
            byte[] wrapperBytes = File.ReadAllBytes(wrapperPath);
            string command = (string)(buildMethod.Invoke(
                obj: null,
                parameters:
                [
                    new Uri(wrapperPath).AbsoluteUri,
                    Convert.ToHexStringLower(SHA256.HashData(wrapperBytes)),
                    staleProof,
                    Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(staleProof))),
                    handoff
                ]) ?? throw new InvalidOperationException("command build returned null"));

            var startInfo = new ProcessStartInfo("/bin/bash")
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false
            };
            startInfo.ArgumentList.Add("-c");
            startInfo.ArgumentList.Add(command);
            string[] authorityNames =
            [
                "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
                "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
                .. handoff.Inputs.SelectMany(static input => new[]
                {
                    input.PathEnvironmentVariable,
                    input.DigestEnvironmentVariable,
                    input.AuthorityEnvironmentVariable
                })
            ];
            foreach (string authorityName in authorityNames)
            {
                startInfo.Environment.Remove(authorityName);
            }
            foreach (string sourcePin in new[]
                     {
                         "CHUMMER_UI_EXPECTED_COMMIT",
                         "CHUMMER_CORE_EXPECTED_COMMIT",
                         "CHUMMER_HUB_EXPECTED_COMMIT",
                         "CHUMMER_UI_KIT_EXPECTED_COMMIT",
                         "CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT",
                         "CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT",
                         "CHUMMER_LEGACY_EXPECTED_COMMIT"
                     })
            {
                startInfo.Environment[sourcePin] = new string('a', 40);
            }
            startInfo.Environment["CHUMMER_RELEASE_UPLOAD_TICKET_FILE"] = ticketPath;
            startInfo.Environment["CHUMMER_RELEASE_PYTHON"] = "/usr/bin/python3";
            startInfo.Environment["TMPDIR"] = tempRoot;

            using Process process = Process.Start(startInfo)
                ?? throw new InvalidOperationException("release command did not start");
            string stdout = process.StandardOutput.ReadToEnd();
            string stderr = process.StandardError.ReadToEnd();
            Assert.True(process.WaitForExit(30_000), "release command timed out");
            Assert.True(
                process.ExitCode == 0,
                $"release command failed ({process.ExitCode})\nstdout:\n{stdout}\nstderr:\n{stderr}");
            Assert.True(File.Exists(generatedProof), "local Hub generator was not reached");
            Assert.True(File.Exists(staleProofRejected), "stale remote proof did not reach the local generator fallback");
            string[] temporaryAuthorityPaths = File.ReadAllLines(observedPaths);
            Assert.Equal(5, temporaryAuthorityPaths.Length);
            Assert.All(temporaryAuthorityPaths, path => Assert.False(File.Exists(path)));
            Assert.False(Directory.Exists(Path.GetDirectoryName(temporaryAuthorityPaths[0])));
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public void ReleaseUploadPageMintsTicketOnDemandWithoutRenderingItIntoHtml()
    {
        string view = File.ReadAllText(
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ReleaseUpload.cshtml"));
        string controller = File.ReadAllText(
            RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        MethodInfo bootstrapScriptEndpoint = typeof(PublicLandingController).GetMethod(
            nameof(PublicLandingController.ReleaseUploadBootstrapScript))
            ?? throw new InvalidOperationException("missing release upload bootstrap script endpoint");
        MethodInfo bootstrapCommandEndpoint = typeof(PublicLandingController).GetMethod(
            nameof(PublicLandingController.ReleaseUploadBootstrapCommand))
            ?? throw new InvalidOperationException("missing release upload bootstrap command endpoint");
        MethodInfo ticketEndpoint = typeof(PublicLandingController).GetMethod(
            nameof(PublicLandingController.ReleaseUploadTicket))
            ?? throw new InvalidOperationException("missing release upload ticket endpoint");

        Assert.Contains("data-ticket-url=\"@Model.TicketUrl\"", view, StringComparison.Ordinal);
        Assert.Contains("method: \"POST\"", view, StringComparison.Ordinal);
        Assert.Contains("RequestVerificationToken", view, StringComparison.Ordinal);
        Assert.Contains("pins for all seven source repositories", view, StringComparison.Ordinal);
        Assert.Contains("supplies all 17 Hub-proof authority variables itself", view, StringComparison.Ordinal);
        Assert.Contains("Model.AuthoritySnapshotSha256", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Model.HandoffCode", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Model.TicketExpiresAtUtc", view, StringComparison.Ordinal);
        Assert.Null(typeof(ReleaseUploadPageViewModel).GetProperty("HandoffCode"));
        Assert.NotNull(ticketEndpoint.GetCustomAttribute<ValidateAntiForgeryTokenAttribute>());
        Assert.Empty(bootstrapScriptEndpoint.GetParameters());
        Assert.DoesNotContain(
            bootstrapCommandEndpoint.GetParameters(),
            parameter => string.Equals(parameter.Name, "ticket", StringComparison.OrdinalIgnoreCase)
                || string.Equals(parameter.Name, "apiToken", StringComparison.OrdinalIgnoreCase));

        int commandAction = controller.IndexOf(
            "public async Task<IActionResult> ReleaseUploadBootstrapCommand(",
            StringComparison.Ordinal);
        Assert.True(commandAction >= 0, "release upload command action is missing");
        int authenticatedSubject = controller.IndexOf(
            "_identity.RequireSubjectAsync(Request, cancellationToken)",
            commandAction,
            StringComparison.Ordinal);
        Assert.True(authenticatedSubject >= 0, "release upload command authentication is missing");
        int authenticatedHandoff = controller.IndexOf(
            "TryBuildReleaseUploadCommand(",
            authenticatedSubject,
            StringComparison.Ordinal);
        Assert.True(
            commandAction < authenticatedSubject && authenticatedSubject < authenticatedHandoff,
            "the signed-in command must authenticate before loading the CURRENT authority handoff");
    }

    [Theory]
    [InlineData(nameof(PublicLandingController.ReleaseUploadBootstrapScript))]
    [InlineData(nameof(PublicLandingController.DownloadDispatchBootstrapScript))]
    [InlineData(nameof(PublicLandingController.DownloadDispatchPersonalizedMacBootstrapScript))]
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
    public void PersonalizedMacBootstrapRoutesConstrainScriptAndDigestSegments()
    {
        MethodInfo method = typeof(PublicLandingController).GetMethod(
            nameof(PublicLandingController.DownloadDispatchPersonalizedMacBootstrapScript))
            ?? throw new InvalidOperationException("missing personalized bootstrap route");

        HttpGetAttribute[] routes = method
            .GetCustomAttributes<HttpGetAttribute>()
            .ToArray();

        Assert.Contains(
            routes,
            route => string.Equals(
                route.Template,
                "/install-{scriptId:minlength(24):maxlength(24)}.sh",
                StringComparison.Ordinal));
        Assert.Contains(
            routes,
            route => string.Equals(
                route.Template,
                "/install-{scriptId:minlength(24):maxlength(24)}-{renderedScriptSha256:minlength(64):maxlength(64)}.sh",
                StringComparison.Ordinal));
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
    public void ReleaseUploadBootstrapTemplateFailsClosedWhenLocalizationGateGeneratorScriptIsMissing()
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
            "write_bootstrap_fallback_ui_localization_release_gate",
            template,
            StringComparison.Ordinal);
        Assert.Contains(
            "bootstrap synthetic UI localization release-gate fallback is disabled",
            template,
            StringComparison.Ordinal);
        Assert.Contains(
            "ui localization release gate repo root could not be resolved",
            template,
            StringComparison.Ordinal);
        Assert.Contains(
            "ui localization release gate generator failed at $script_path; fix the gate or set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH",
            template,
            StringComparison.Ordinal);
        Assert.Contains(
            "ui localization release gate generator is missing at $script_path; set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH or restore the gate script",
            template,
            StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseUploadBootstrapTemplateTracksMainRefsByDefaultAndKeepsUploadAuthOutOfCurlArgv()
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

        Assert.Contains("verify_checkout_expected_commit", template, StringComparison.Ordinal);
        Assert.Contains("local expected_commit=\"${4:-}\"", template, StringComparison.Ordinal);
        Assert.Contains("local fetch_target=\"$ref\"", template, StringComparison.Ordinal);
        Assert.Contains("fetch_target=\"$expected_commit\"", template, StringComparison.Ordinal);
        Assert.Contains("fetch --depth 1 origin \"$fetch_target\"", template, StringComparison.Ordinal);
        Assert.Contains("remote set-url origin \"$repo_url\"", template, StringComparison.Ordinal);
        Assert.Contains("git -C \"$target_dir\" init -q", template, StringComparison.Ordinal);
        Assert.Contains("git -C \"$target_dir\" remote add origin \"$repo_url\"", template, StringComparison.Ordinal);
        Assert.Contains("cloning $(basename \"$target_dir\") -> $ref (pinned $expected_commit)", template, StringComparison.Ordinal);
        Assert.Contains("local ui_ref=\"${CHUMMER_UI_REF:-main}\"", template, StringComparison.Ordinal);
        Assert.Contains("local core_ref=\"${CHUMMER_CORE_REF:-main}\"", template, StringComparison.Ordinal);
        Assert.Contains("local hub_ref=\"${CHUMMER_HUB_REF:-main}\"", template, StringComparison.Ordinal);
        Assert.Contains("local ui_kit_ref=\"${CHUMMER_UI_KIT_REF:-main}\"", template, StringComparison.Ordinal);
        Assert.Contains("local registry_ref=\"${CHUMMER_HUB_REGISTRY_REF:-main}\"", template, StringComparison.Ordinal);
        Assert.Contains("umask 077", template, StringComparison.Ordinal);
        Assert.Contains("request_common=(", template, StringComparison.Ordinal);
        Assert.Contains("curl -q --config -", template, StringComparison.Ordinal);
        Assert.Contains("write_release_upload_curl_config()", template, StringComparison.Ordinal);
        Assert.Contains("Authorization: Bearer {escaped}", template, StringComparison.Ordinal);
        Assert.Contains("token = sys.stdin.read()", template, StringComparison.Ordinal);
        Assert.Contains("python3 -c", template, StringComparison.Ordinal);
        Assert.DoesNotContain("release_upload_curl_config=\"$(mktemp)\"", template, StringComparison.Ordinal);
        Assert.Contains("log_release_upload_response()", template, StringComparison.Ordinal);
        Assert.Contains("render_sanitized_release_upload_response()", template, StringComparison.Ordinal);
        Assert.Contains("allowed_scalars = (", template, StringComparison.Ordinal);
        Assert.Contains("suppressedFieldCount", template, StringComparison.Ordinal);
        Assert.Contains("printing signed install claim credentials is permanently disabled", template, StringComparison.Ordinal);
        Assert.Contains("release_upload_attempt_receipt.py", template, StringComparison.Ordinal);
        Assert.Contains("record_upload_attempt_state created", template, StringComparison.Ordinal);
        Assert.Contains("record_upload_attempt_state request_started", template, StringComparison.Ordinal);
        Assert.Contains("BOOTSTRAP_RELEASE_UPLOAD_ACCEPTED=1", template, StringComparison.Ordinal);
        Assert.Contains("Do not create or publish another session", template, StringComparison.Ordinal);
        Assert.Contains("validate_release_response_probe_url", template, StringComparison.Ordinal);
        Assert.Contains("candidate_authority != canonical_authority", template, StringComparison.Ordinal);
        Assert.Contains("release upload response contained an unsafe install handoff URL", template, StringComparison.Ordinal);
        Assert.DoesNotContain("claim code: ", template, StringComparison.Ordinal);
        Assert.DoesNotContain("python3 - \"$config_path\" <<'PY'", template, StringComparison.Ordinal);
        Assert.DoesNotContain("token = sys.argv[2]", template, StringComparison.Ordinal);
        Assert.DoesNotContain("local upload_token=\"$3\"", template, StringComparison.Ordinal);
        Assert.Contains("local keep_upload_response=\"${CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE:-0}\"", template, StringComparison.Ordinal);
        Assert.Contains("BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH=\"$response_path\"", template, StringComparison.Ordinal);
        Assert.Contains("BOOTSTRAP_KEEP_UPLOAD_RESPONSE=\"$keep_upload_response\"", template, StringComparison.Ordinal);
        Assert.Contains("removed sanitized release upload response summary", template, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-0", template, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION", template, StringComparison.Ordinal);
        Assert.Contains("local fallback_release_proof_url=\"${CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL:-}\"", template, StringComparison.Ordinal);
        Assert.Contains("local fallback_ui_localization_release_gate_url=\"${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL:-}\"", template, StringComparison.Ordinal);
        Assert.Contains("validate_hub_local_release_proof_with_registry()", template, StringComparison.Ordinal);
        Assert.Contains("proof = module.load_release_proof(proof_path)", template, StringComparison.Ordinal);
        Assert.Contains("hub local release proof generation produced a Registry-incompatible receipt", template, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \\", template, StringComparison.Ordinal);
        Assert.Contains("bash scripts/verify-releases-manifest.sh \"$dist_dir/releases.json\"", template, StringComparison.Ordinal);
        Assert.Contains("bash scripts/verify-releases-manifest.sh \"$canonical_verify_url\"", template, StringComparison.Ordinal);
        Assert.Contains("resolve_live_release_verify_urls \"$verify_url\"", template, StringComparison.Ordinal);
        Assert.Contains("compatibility release projection is still missing installer tuples after promotion", template, StringComparison.Ordinal);
        Assert.Contains("canonical release truth is already live", template, StringComparison.Ordinal);
        Assert.Contains("curl --fail-with-body -sS \"$compatibility_url\"", template, StringComparison.Ordinal);
        Assert.Contains("curl --fail-with-body -sS \"$canonical_url\"", template, StringComparison.Ordinal);
        Assert.DoesNotContain("curl --fail-with-body -fsS \"$compatibility_url\"", template, StringComparison.Ordinal);
        Assert.DoesNotContain("curl --fail-with-body -fsS \"$canonical_url\"", template, StringComparison.Ordinal);
        Assert.DoesNotContain("log_json_or_text \"$response_path\"", template, StringComparison.Ordinal);
    }

    [Fact]
    public void ResolveGuidedBootstrapArtifactsKeepsGuidedInstallPathOnPlatformWithoutDroppingFallbackHead()
    {
        PublicReleaseManifestDto manifest = new(
            Version: "run-20260403-150000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-03T15:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "l1",
                    SizeBytes: 101,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "blazor-desktop-linux-x64-installer",
                    Platform: "Blazor Desktop Linux x64 Installer",
                    Url: "/downloads/files/chummer-blazor-desktop-linux-x64-installer.deb",
                    Sha256: "l2",
                    SizeBytes: 202,
                    Head: "blazor-desktop",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-blazor-desktop-linux-x64-installer.deb",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-arm64-installer",
                    Platform: "Avalonia Desktop Linux ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-arm64-installer.deb",
                    Sha256: "l3",
                    SizeBytes: 303,
                    Head: "avalonia",
                    PlatformId: "linux-arm64",
                    Arch: "arm64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-arm64-installer.deb",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "m1",
                    SizeBytes: 404,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required")
            ]);

        IReadOnlyList<PublicReleaseArtifactDto> artifacts = PublicLandingController.ResolveGuidedBootstrapArtifacts(
            manifest,
            manifest.Downloads[0]);

        Assert.Collection(
            artifacts,
            item => Assert.Equal("avalonia-linux-x64-installer", item.Id),
            item => Assert.Equal("blazor-desktop-linux-x64-installer", item.Id),
            item => Assert.Equal("avalonia-linux-arm64-installer", item.Id));
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
                    ClaimUrl: "https://chummer.run/downloads/install/avalonia-linux-x64-installer/continue.json?ticket=T-1",
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
                    ClaimUrl: "https://chummer.run/downloads/install/blazor-desktop-linux-x64-installer/continue.json?ticket=T-1",
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

    private static ReleaseUploadAuthorityHandoff BuildAuthorityHandoff()
    {
        string generatedAt = DateTimeOffset.UtcNow
            .ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", System.Globalization.CultureInfo.InvariantCulture);
        object proof = new
        {
            contract_name = "chummer6-hub.local_release_proof",
            status = "passed",
            release_channel = new
            {
                status = "available",
                path = "registry://release/run-fixture",
                channelId = "preview",
                channel = "preview",
                version = "run-fixture",
                releaseVersion = "run-fixture",
                rolloutState = "promoted_preview",
                supportabilityState = "preview_supported",
                publishedAt = generatedAt
            },
            desktop_client_readiness = new
            {
                status = "pass",
                scoped_status = "pass",
                generated_at = generatedAt,
                missing_coverage_keys = Array.Empty<string>(),
                desktop_client_missing = false,
                reason = "fixture readiness is current",
                completion_audit_status = "pass",
                completion_audit_reason = "fixture completion is current",
                source_path = "fleet://readiness/run-fixture"
            },
            proof_routes = new[]
            {
                "/downloads/install/avalonia-linux-x64-installer",
                "/downloads/install/avalonia-osx-arm64-installer",
                "/downloads/install/avalonia-win-x64-installer",
                "/home/access",
                "/home/work",
                "/account/access",
                "/account/work",
                "/account/support",
                "/contact",
                "/downloads"
            },
            authority_inputs = new Dictionary<string, object>(StringComparer.Ordinal)
            {
                [ReleaseUploadAuthorityHandoffBuilder.ReleaseChannelKey] = new
                {
                    authority = "registry://release/run-fixture",
                    sha256 = new string('1', 64),
                    contract = "chummer.registry.release-channel/v1",
                    commit = new string('1', 40),
                    generated_at = generatedAt
                },
                [ReleaseUploadAuthorityHandoffBuilder.FlagshipReadinessKey] = new
                {
                    authority = "fleet://readiness/run-fixture",
                    sha256 = new string('2', 64),
                    contract = "chummer.flagship-product-readiness/v1",
                    commit = new string('2', 40),
                    generated_at = generatedAt
                },
                [ReleaseUploadAuthorityHandoffBuilder.FleetQueueKey] = new
                {
                    authority = "fleet://queue/run-fixture",
                    sha256 = new string('3', 64)
                },
                [ReleaseUploadAuthorityHandoffBuilder.DesignQueueKey] = new
                {
                    authority = "repo://design/run-fixture/queue",
                    sha256 = new string('4', 64)
                },
                [ReleaseUploadAuthorityHandoffBuilder.DesignSuccessorRegistryKey] = new
                {
                    authority = "repo://design/run-fixture/registry",
                    sha256 = new string('5', 64)
                }
            },
            generated_at = generatedAt,
            generatedAt
        };
        byte[] proofBytes = JsonSerializer.SerializeToUtf8Bytes(proof);
        string proofSha256 = Convert.ToHexStringLower(SHA256.HashData(proofBytes));
        string snapshotSha256 = new string('a', 64);
        var snapshot = new PublicProjectionOutputSnapshot(
            IsConfigured: true,
            IsValid: true,
            FailureReason: null,
            SnapshotId: "public-projection-" + snapshotSha256,
            SnapshotSha256: snapshotSha256,
            Path: null,
            Sha256: proofSha256,
            Payload: proofBytes);
        return ReleaseUploadAuthorityHandoffBuilder.Build(snapshot);
    }

    private static string SingleQuoteForTest(string value)
        => "'" + value.Replace("'", "'\"'\"'", StringComparison.Ordinal) + "'";
}
