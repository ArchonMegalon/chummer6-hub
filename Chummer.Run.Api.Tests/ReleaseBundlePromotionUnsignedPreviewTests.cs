using Chummer.Run.Api.Services;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
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

    [Fact]
    public void ExactWindowsFreshDeltaPreservesRetainedLinuxUrlButKeepsWindowsIncomingUrlStrict()
    {
        ReleaseDesktopTupleScope scope = ReleaseDesktopTupleScope.Parse(
            "avalonia:windows:win-x64");
        const string retainedLinuxUrl =
            "/downloads/g/gen-20260802T164413Z-bf6517fa73a94b2a/files/chummer-avalonia-linux-x64-installer.deb";
        const string windowsFileName = "chummer-avalonia-win-x64-installer.exe";
        const string governedWindowsUrl =
            "/downloads/files/chummer-avalonia-win-x64-installer.exe";

        bool linuxRequiresIncomingUrl =
            ReleaseBundlePromotionService.RequiresGovernedIncomingArtifactUrls(
                scope,
                exactIncomingDesktopScopeIsFreshDelta: true,
                head: "avalonia",
                platform: "linux",
                rid: "linux-x64");
        bool windowsRequiresIncomingUrl =
            ReleaseBundlePromotionService.RequiresGovernedIncomingArtifactUrls(
                scope,
                exactIncomingDesktopScopeIsFreshDelta: true,
                head: "avalonia",
                platform: "windows",
                rid: "win-x64");

        Assert.False(linuxRequiresIncomingUrl);
        Assert.Equal(
            retainedLinuxUrl,
            ReleaseBundlePromotionService.NormalizeIncomingArtifactUrl(
                retainedLinuxUrl,
                "chummer-avalonia-linux-x64-installer.deb",
                "avalonia-linux-x64-installer",
                linuxRequiresIncomingUrl,
                "canonical downloadUrl"));
        Assert.True(windowsRequiresIncomingUrl);
        Assert.Throws<InvalidDataException>(() =>
            ReleaseBundlePromotionService.NormalizeIncomingArtifactUrl(
                retainedLinuxUrl,
                windowsFileName,
                "avalonia-win-x64-installer",
                windowsRequiresIncomingUrl,
                "canonical downloadUrl"));
        Assert.Equal(
            governedWindowsUrl,
            ReleaseBundlePromotionService.NormalizeIncomingArtifactUrl(
                governedWindowsUrl,
                windowsFileName,
                "avalonia-win-x64-installer",
                windowsRequiresIncomingUrl,
                "canonical downloadUrl"));
    }

    [Fact]
    public void AuthorityBoundCandidateAcceptsOnlyExactImmutableGenerationFileUrl()
    {
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        const string artifactId = "avalonia-win-x64-installer";
        const string immutableUrl =
            "/downloads/g/g-20260804T220108Z-d075fe4a261b4a14/files/chummer-avalonia-win-x64-installer.exe";

        Assert.Equal(
            immutableUrl,
            ReleaseBundlePromotionService.NormalizeIncomingArtifactUrl(
                immutableUrl,
                fileName,
                artifactId,
                requireGovernedIncomingUrl: true,
                nonIncomingField: "canonical downloadUrl",
                allowAuthorityBoundGenerationUrl: true));
        Assert.Throws<InvalidDataException>(() =>
            ReleaseBundlePromotionService.NormalizeIncomingArtifactUrl(
                immutableUrl,
                fileName,
                artifactId,
                requireGovernedIncomingUrl: true,
                nonIncomingField: "canonical downloadUrl"));
        Assert.Throws<InvalidDataException>(() =>
            ReleaseBundlePromotionService.NormalizeIncomingArtifactUrl(
                "/downloads/g/g-20260804T220108Z-d075fe4a261b4a14/files/other.exe",
                fileName,
                artifactId,
                requireGovernedIncomingUrl: true,
                nonIncomingField: "canonical downloadUrl",
                allowAuthorityBoundGenerationUrl: true));
        Assert.Throws<InvalidDataException>(() =>
            ReleaseBundlePromotionService.NormalizeIncomingArtifactUrl(
                immutableUrl + "?download=1",
                fileName,
                artifactId,
                requireGovernedIncomingUrl: true,
                nonIncomingField: "canonical downloadUrl",
                allowAuthorityBoundGenerationUrl: true));
    }

    [Fact]
    public void FreshDeltaAcceptsMaterializedActiveShelfWhenPublishedArtifactInventoryMatches()
    {
        string root = Path.Combine(
            Path.GetTempPath(),
            "unsigned-profile-active-shelf-tests",
            Guid.NewGuid().ToString("N"));
        string filesRoot = Path.Combine(root, "files");
        Directory.CreateDirectory(filesRoot);
        try
        {
            byte[] installerBytes = Encoding.UTF8.GetBytes("incumbent installer");
            byte[] payloadBytes = Encoding.UTF8.GetBytes("incumbent payload");
            string installerSha256 = Sha256(installerBytes);
            string payloadSha256 = Sha256(payloadBytes);
            const string installerFileName = "incumbent.exe";
            const string payloadFileName = "incumbent.zip";
            string installerUrl = $"/downloads/g/gen-test/files/{installerFileName}";
            string payloadUrl = $"/downloads/g/gen-test/files/{payloadFileName}";

            var canonical = new JsonObject
            {
                ["artifacts"] = new JsonArray
                {
                    new JsonObject
                    {
                        ["artifactId"] = "avalonia-win-x64-installer",
                        ["head"] = "avalonia",
                        ["platform"] = "windows",
                        ["arch"] = "x64",
                        ["rid"] = "win-x64",
                        ["kind"] = "installer",
                        ["fileName"] = installerFileName,
                        ["downloadUrl"] = installerUrl,
                        ["sha256"] = installerSha256,
                        ["sizeBytes"] = installerBytes.Length,
                        ["platformLabel"] = "Windows",
                        ["installAccessClass"] = "open_public",
                        ["installerMode"] = "bootstrap",
                        ["payloadFileName"] = payloadFileName,
                        ["payloadDownloadUrl"] = payloadUrl,
                        ["payloadSha256"] = payloadSha256,
                        ["payloadSizeBytes"] = payloadBytes.Length
                    }
                }
            };
            var compatibility = new JsonObject
            {
                ["version"] = "run-incumbent",
                ["channel"] = "preview",
                ["publishedAt"] = "2026-08-02T16:05:00Z",
                ["source"] = "registry",
                ["status"] = "published",
                ["downloads"] = new JsonArray
                {
                    new JsonObject
                    {
                        ["id"] = "avalonia-win-x64-installer",
                        ["artifactId"] = "avalonia-win-x64-installer",
                        ["head"] = "avalonia",
                        ["platform"] = "Windows",
                        ["platformId"] = "windows",
                        ["platformLabel"] = "Windows",
                        ["arch"] = "x64",
                        ["rid"] = "win-x64",
                        ["kind"] = "installer",
                        ["fileName"] = installerFileName,
                        ["url"] = installerUrl,
                        ["sha256"] = installerSha256,
                        ["sizeBytes"] = installerBytes.Length,
                        ["installAccessClass"] = "open_public",
                        ["installerMode"] = "bootstrap",
                        ["payloadFileName"] = payloadFileName,
                        ["payloadDownloadUrl"] = payloadUrl,
                        ["payloadSha256"] = payloadSha256,
                        ["payloadSizeBytes"] = payloadBytes.Length
                    }
                }
            };
            byte[] canonicalBytes = Encoding.UTF8.GetBytes(canonical.ToJsonString());
            byte[] compatibilityBytes = Encoding.UTF8.GetBytes(compatibility.ToJsonString());
            File.WriteAllBytes(Path.Combine(root, "RELEASE_CHANNEL.generated.json"), canonicalBytes);
            File.WriteAllBytes(Path.Combine(root, "releases.json"), compatibilityBytes);
            File.WriteAllBytes(Path.Combine(filesRoot, installerFileName), installerBytes);
            File.WriteAllBytes(Path.Combine(filesRoot, payloadFileName), payloadBytes);
            File.WriteAllText(Path.Combine(root, "retained-ancillary-proof.json"), "{}", Encoding.UTF8);

            ReleaseShelfInventoryEntry[] publishedArtifacts =
            [
                new($"files/{installerFileName}", installerSha256, installerBytes.Length),
                new($"files/{payloadFileName}", payloadSha256, payloadBytes.Length)
            ];
            var inventory = new Dictionary<string, ReleaseShelfInventoryEntry>(StringComparer.Ordinal)
            {
                ["RELEASE_CHANNEL.generated.json"] = new(
                    "RELEASE_CHANNEL.generated.json",
                    Sha256(canonicalBytes),
                    canonicalBytes.Length),
                ["releases.json"] = new(
                    "releases.json",
                    Sha256(compatibilityBytes),
                    compatibilityBytes.Length),
                [$"files/{installerFileName}"] = publishedArtifacts[0],
                [$"files/{payloadFileName}"] = publishedArtifacts[1],
                ["retained-ancillary-proof.json"] = new(
                    "retained-ancillary-proof.json",
                    Sha256(Encoding.UTF8.GetBytes("{}")),
                    2)
            };
            ReleaseShelfSnapshot shelf = ReleaseShelfSnapshot.Active(
                downloadsRoot: root,
                physicalRoot: root,
                generationId: "gen-test",
                releaseVersion: "run-incumbent",
                channel: "preview",
                publishedAt: DateTimeOffset.Parse(
                    "2026-08-02T16:05:00Z",
                    CultureInfo.InvariantCulture),
                activatedAt: DateTimeOffset.Parse(
                    "2026-08-02T16:44:13Z",
                    CultureInfo.InvariantCulture),
                activationReceiptId: "activation-test",
                canonicalManifestSha256: Sha256(canonicalBytes),
                compatibilityManifestSha256: Sha256(compatibilityBytes),
                inventoryDigest: ReleaseShelfGenerationStore.ComputeInventoryDigest(
                    inventory.Values.Where(static row => row.Path is not
                        "RELEASE_CHANNEL.generated.json" and not "releases.json")),
                pointerDigest: new string('d', 64),
                inventory,
                explicitGeneration: false);
            string publishedArtifactInventorySha256 =
                ReleaseShelfGenerationStore.ComputeInventoryDigest(publishedArtifacts);
            var binding = new ReleaseUploadCandidateSessionBinding(
                SnapshotSha256: new string('1', 64),
                AuthoritySha256: new string('2', 64),
                BundleIdentitySha256: new string('3', 64),
                CanonicalManifestSha256: new string('4', 64),
                InventorySha256: new string('5', 64),
                ExactIncomingDesktopScopeIsFreshDelta: true,
                IncumbentBinding: new ReleaseUploadCandidateIncumbentBinding(
                    SnapshotSha256: new string('6', 64),
                    FullShelfInventorySha256: new string('7', 64),
                    ActiveInventorySha256: publishedArtifactInventorySha256,
                    CanonicalManifestSha256: new string('8', 64),
                    CompatibilityManifestSha256: new string('9', 64)));

            ReleaseBundlePromotionService.ValidateCandidateIncumbentBinding(shelf, binding);

            ReleaseUploadCandidateSessionBinding drifted = binding with
            {
                IncumbentBinding = binding.IncumbentBinding! with
                {
                    ActiveInventorySha256 = new string('a', 64)
                }
            };
            Assert.Throws<ReleaseShelfMutationConcurrencyException>(() =>
                ReleaseBundlePromotionService.ValidateCandidateIncumbentBinding(
                    shelf,
                    drifted));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
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

    private static string Sha256(byte[] bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes));
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
