using Chummer.Run.Api.Services;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBundlePromotionUnsignedPreviewTests
{
    [Fact]
    public void UnsignedWindowsFreshDeltaDoesNotRequireAurAncillaryInputs()
    {
        string filesRoot = Path.Combine(
            Path.GetTempPath(),
            "unsigned-profile-no-aur-tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(filesRoot);
        try
        {
            IReadOnlySet<string> ancillaryFiles =
                ReleaseBundlePromotionService.ValidateAndCollectProfileAurFiles(
                    aurPackagesPath: null,
                    filesRoot);

            Assert.Empty(ancillaryFiles);
        }
        finally
        {
            Directory.Delete(filesRoot, recursive: true);
        }
    }

    [Theory]
    [InlineData("preview", "unsigned")]
    [InlineData("preview", "skipped_preview")]
    [InlineData("PREVIEW", "UNSIGNED")]
    public void PreviewAcceptsExplicitUnsignedWindowsEvidence(string channel, string signingStatus)
    {
        Assert.True(ReleaseBundlePromotionService.IsUnsignedWindowsPreviewEvidence(channel, signingStatus));
    }

    [Theory]
    [InlineData("stable", "unsigned")]
    [InlineData("preview", "unsigned_public_release")]
    [InlineData("preview", "pass")]
    [InlineData("preview", null)]
    [InlineData(null, "unsigned")]
    public void OtherChannelAndSigningCombinationsRemainOutsidePreviewException(
        string? channel,
        string? signingStatus)
    {
        Assert.False(ReleaseBundlePromotionService.IsUnsignedWindowsPreviewEvidence(channel, signingStatus));
    }
}

public sealed class ReleaseUploadSnapshotAuthorityUnsignedCanonicalIdentityTests
{
    private const string InstallerSha256 =
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string PayloadSha256 =
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    [Fact]
    public void ExactPreviewAliasesAreAccepted()
    {
        using JsonDocument document = JsonDocument.Parse(
            """{"version":"run-candidate","releaseVersion":"run-candidate","channel":"preview","channelId":"preview"}""");

        ReleaseUploadSnapshotAuthorityService.ValidateUnsignedManifestIdentity(
            document.RootElement,
            "run-candidate",
            "test manifest");
    }

    [Theory]
    [InlineData("{\"version\":\"run-candidate\",\"channel\":\"stable\"}")]
    [InlineData("{\"releaseVersion\":\"run-candidate\",\"channelId\":\"stable\"}")]
    [InlineData("{\"version\":\"run-candidate\"}")]
    [InlineData("{\"channel\":\"preview\"}")]
    [InlineData("{\"version\":\"wrong\",\"releaseVersion\":\"run-candidate\",\"channel\":\"preview\"}")]
    [InlineData("{\"version\":\"run-candidate\",\"channel\":\"preview\",\"channelId\":\"stable\"}")]
    public void MissingOrMismatchedAliasesAreRejected(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);

        Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedManifestIdentity(
                document.RootElement,
                "run-candidate",
                "test manifest"));
    }

    [Fact]
    public void RetainedCanonicalArtifactMustBindExactInventoryBytes()
    {
        const string LinuxManifestSha =
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const string LinuxInventorySha =
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        const string WindowsSha =
            "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
        const string PayloadSha =
            "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd";
        using JsonDocument canonical = JsonDocument.Parse(
            $$"""
            {
              "artifacts": [
                {
                  "platform": "linux",
                  "fileName": "retained.deb",
                  "sha256": "{{LinuxManifestSha}}",
                  "sizeBytes": 10
                },
                {
                  "platform": "windows",
                  "head": "avalonia",
                  "rid": "win-x64",
                  "kind": "installer",
                  "installerMode": "bootstrap",
                  "payloadAcquisitionMode": "download",
                  "fileName": "candidate.exe",
                  "sha256": "{{WindowsSha}}",
                  "sizeBytes": 20,
                  "payloadFileName": "candidate.zip",
                  "payloadSha256": "{{PayloadSha}}",
                  "payloadSizeBytes": 30
                }
              ]
            }
            """);
        using JsonDocument fresh = JsonDocument.Parse(
            """[{"path":"files/candidate.exe"},{"path":"files/candidate.zip"}]""");
        var inventory = new Dictionary<string, ReleaseUploadCandidateInventoryRow>(
            StringComparer.Ordinal)
        {
            ["files/retained.deb"] = new("files/retained.deb", 10, LinuxInventorySha),
            ["files/candidate.exe"] = new("files/candidate.exe", 20, WindowsSha),
            ["files/candidate.zip"] = new("files/candidate.zip", 30, PayloadSha)
        };

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedCanonicalWindows(
                canonical.RootElement,
                inventory,
                fresh.RootElement));

        Assert.Contains("canonical artifact bytes", rejected.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CurrentUnsignedNativeStartupReceiptIsAcceptedExactly()
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        using JsonDocument receipt = CurrentStartupReceipt(now);

        ReleaseUploadSnapshotAuthorityService.ValidateUnsignedStartupReceipt(
            receipt.RootElement,
            "avalonia",
            "run-candidate",
            "preview",
            "candidate.exe",
            InstallerSha256,
            "candidate.zip",
            PayloadSha256,
            42,
            now);
    }

    [Fact]
    public void CurrentUnsignedNativeStartupReceiptRejectsSchemaDrift()
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        using JsonDocument receipt = CurrentStartupReceipt(
            now,
            root => root.Remove("processPath"));

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedStartupReceipt(
                receipt.RootElement,
                "avalonia",
                "run-candidate",
                "preview",
                "candidate.exe",
                InstallerSha256,
                "candidate.zip",
                PayloadSha256,
                42,
                now));

        Assert.Contains("property set", rejected.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CurrentUnsignedNativeStartupReceiptRejectsNonLoopbackPayloadUrl()
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        using JsonDocument receipt = CurrentStartupReceipt(
            now,
            root => root["bootstrapPayloadDownloadUrl"] =
                "https://example.invalid/candidate.zip");

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedStartupReceipt(
                receipt.RootElement,
                "avalonia",
                "run-candidate",
                "preview",
                "candidate.exe",
                InstallerSha256,
                "candidate.zip",
                PayloadSha256,
                42,
                now));

        Assert.Contains("payload download URL", rejected.Message, StringComparison.Ordinal);
    }

    private static JsonDocument CurrentStartupReceipt(
        DateTimeOffset now,
        Action<JsonObject>? mutate = null)
    {
        string timestamp = now.AddMinutes(-1).ToString("O", CultureInfo.InvariantCulture);
        JsonObject root = JsonNode.Parse(
            $$"""
            {
              "arch": "x64",
              "artifactDigest": "sha256:{{InstallerSha256}}",
              "artifactDigestSource": "environment",
              "artifactFileName": "candidate.exe",
              "artifactId": "avalonia-win-x64-installer",
              "artifactInstallMode": "nsis_bootstrap_installer",
              "artifactPath": "files/candidate.exe",
              "artifactPathDisclosure": "artifact_shelf_relative_path",
              "artifactRelativePath": "files/candidate.exe",
              "artifactSha256": "{{InstallerSha256}}",
              "bootstrapPayloadAcquisitionMode": "download",
              "bootstrapPayloadDownloadUrl": "http://127.0.0.1:49152/candidate.zip",
              "bootstrapPayloadFileName": "candidate.zip",
              "bootstrapPayloadSha256": "{{PayloadSha256}}",
              "bootstrapPayloadSizeBytes": 42,
              "channelId": "preview",
              "completedAtUtc": "{{timestamp}}",
              "executionEnvironment": "native_windows",
              "fileName": "candidate.exe",
              "framework": ".NET 10.0.3",
              "headId": "avalonia",
              "hostClass": "github-hosted-windows-latest-native",
              "installLinkingInstallationId": "ins-0123456789abcdef0123456789abcdef",
              "installLinkingLaunchCount": 1,
              "installLinkingPromptReason": "claim_required",
              "installLinkingPromptRequired": true,
              "installLinkingStatus": "guest",
              "nativeHostEvidence": {
                "contractName": "chummer6-ui.native_windows_host_evidence",
                "evidenceSource": "host_kernel_and_runner_selection",
                "hostKernel": "MINGW64_NT-10.0-26100",
                "hostPlatform": "windows",
                "isNativeWindows": true,
                "runner": "pwsh",
                "status": "verified"
              },
              "operatingSystem": "Microsoft Windows 10.0.26100",
              "platform": "windows",
              "processPath": "Chummer.Avalonia.exe",
              "processPathDisclosure": "file_name_only",
              "readyCheckpoint": "pre_ui_event_loop",
              "recordedAtUtc": "{{timestamp}}",
              "releaseVersion": "run-candidate",
              "rid": "win-x64",
              "startedAtUtc": "{{timestamp}}",
              "status": "pass",
              "verificationScope": "native_windows_startup",
              "version": "run-candidate"
            }
            """)?.AsObject()
            ?? throw new InvalidOperationException("startup receipt fixture is invalid");
        mutate?.Invoke(root);
        return JsonDocument.Parse(root.ToJsonString());
    }
}
