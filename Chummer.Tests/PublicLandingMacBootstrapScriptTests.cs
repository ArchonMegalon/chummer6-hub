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
        Assert.Contains("Bootstrap digest mismatch; re-open the signed-in downloads handoff and copy a fresh install command.", command, StringComparison.Ordinal);
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
        Assert.Contains("export CHUMMER_UI_REF='main'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_UI_EXPECTED_COMMIT='ee693310b35a0574e000eabdf86461b7c1f2664e'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_CORE_REF='main'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_CORE_EXPECTED_COMMIT='ae55923f1cb6c8fdf40748f7e2600815be123e1e'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_HUB_REF='release-upload-hub-proof-routes-20260419'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_HUB_EXPECTED_COMMIT='5dcde8a9746ecb2f02c70e8181be662f198af84d'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_UI_KIT_REF='fleet/ui-kit'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_UI_KIT_EXPECTED_COMMIT='7fe7265d84b5574b7a02fb56dd1015efadf44312'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_HUB_REGISTRY_REF='main'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT='6efcceb44dc1cafe4d5d141f402f79c35d15b1ef'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_MEDIA_FACTORY_REF='main'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT='e16286ca8c9bad84ff217466c72721ebcdbf48b5'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_LEGACY_REF='Docker'", script, StringComparison.Ordinal);
        Assert.Contains("export CHUMMER_LEGACY_EXPECTED_COMMIT='0b8636d5a852e375409bf565b9ac9b4180ba4524'", script, StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseUploadBootstrapCommandPinsDigestAndEmbedsTheCurrentHandoffCode()
    {
        MethodInfo buildMethod = typeof(PublicLandingController).GetMethod(
            "BuildReleaseUploadBootstrapCommand",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("missing BuildReleaseUploadBootstrapCommand");

        string command = (string)(buildMethod.Invoke(
            obj: null,
            parameters: ["https://chummer.run/downloads/release-upload/bootstrap.sh", "abc123", "ticket-123"]) ?? throw new InvalidOperationException("command build returned null"));

        Assert.Contains("CHUMMER_BOOTSTRAP_EXPECTED_SHA256='abc123'", command, StringComparison.Ordinal);
        Assert.Contains("ACTUAL_BOOTSTRAP_SHA256", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_TICKET='ticket-123'", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS='0'", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK='0'", command, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE='0'", command, StringComparison.Ordinal);
        Assert.DoesNotContain("bootstrap.sh?ticket=", command, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("apiToken=", command, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("CHUMMER_RELEASE_UPLOAD_TOKEN=", command, StringComparison.Ordinal);
        Assert.DoesNotContain("export CHUMMER_RELEASE_UPLOAD_TICKET=", command, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK='1'", command, StringComparison.Ordinal);
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
    public void ReleaseUploadBootstrapTemplatePinsCheckedOutRefsAndKeepsUploadAuthOutOfCurlArgv()
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
        Assert.Contains("local ui_expected_commit=\"${CHUMMER_UI_EXPECTED_COMMIT:-}\"", template, StringComparison.Ordinal);
        Assert.Contains("local fetch_target=\"$ref\"", template, StringComparison.Ordinal);
        Assert.Contains("fetch_target=\"$expected_commit\"", template, StringComparison.Ordinal);
        Assert.Contains("fetch --depth 1 origin \"$fetch_target\"", template, StringComparison.Ordinal);
        Assert.Contains("remote set-url origin \"$repo_url\"", template, StringComparison.Ordinal);
        Assert.Contains("git -C \"$target_dir\" init -q", template, StringComparison.Ordinal);
        Assert.Contains("git -C \"$target_dir\" remote add origin \"$repo_url\"", template, StringComparison.Ordinal);
        Assert.Contains("cloning $(basename \"$target_dir\") -> $ref (pinned $expected_commit)", template, StringComparison.Ordinal);
        Assert.Contains("umask 077", template, StringComparison.Ordinal);
        Assert.Contains("request_common=(", template, StringComparison.Ordinal);
        Assert.Contains("\"--config\"", template, StringComparison.Ordinal);
        Assert.Contains("write_release_upload_curl_config()", template, StringComparison.Ordinal);
        Assert.Contains("Authorization: Bearer {escaped}", template, StringComparison.Ordinal);
        Assert.Contains("token = sys.stdin.read()", template, StringComparison.Ordinal);
        Assert.Contains("python3 -c", template, StringComparison.Ordinal);
        Assert.Contains("log_release_upload_response()", template, StringComparison.Ordinal);
        Assert.Contains(".claimCode = \"[redacted]\"", template, StringComparison.Ordinal);
        Assert.DoesNotContain("python3 - \"$config_path\" <<'PY'", template, StringComparison.Ordinal);
        Assert.DoesNotContain("token = sys.argv[2]", template, StringComparison.Ordinal);
        Assert.DoesNotContain("local upload_token=\"$3\"", template, StringComparison.Ordinal);
        Assert.Contains("local keep_upload_response=\"${CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE:-0}\"", template, StringComparison.Ordinal);
        Assert.Contains("BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH=\"$response_path\"", template, StringComparison.Ordinal);
        Assert.Contains("BOOTSTRAP_KEEP_UPLOAD_RESPONSE=\"$keep_upload_response\"", template, StringComparison.Ordinal);
        Assert.Contains("removed sensitive release upload response file", template, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-0", template, StringComparison.Ordinal);
        Assert.Contains("local fallback_release_proof_url=\"${CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL:-}\"", template, StringComparison.Ordinal);
        Assert.Contains("local fallback_ui_localization_release_gate_url=\"${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL:-}\"", template, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \\", template, StringComparison.Ordinal);
        Assert.Contains("bash scripts/verify-releases-manifest.sh \"$dist_dir/releases.json\"", template, StringComparison.Ordinal);
        Assert.Contains("bash scripts/verify-releases-manifest.sh \"$verify_url\"", template, StringComparison.Ordinal);
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
}
