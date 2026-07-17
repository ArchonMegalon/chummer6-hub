using System.IO.Compression;
using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBundlePromotionServiceTests
{
    private static readonly JsonSerializerOptions TestJsonOptions = new(JsonSerializerDefaults.Web);

    [Fact]
    public async Task InitialLegacyMigrationCommitsGenerationOnceAndRemainsReadyAfterRestart()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-initial-cutover",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-linux-x64-installer", "avalonia", "linux", "x64", "installer",
                    "chummer-avalonia-linux-x64-installer.deb", "linux-cutover"u8.ToArray(),
                    false, false, "not_applicable", "not_applicable"),
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "windows-cutover"u8.ToArray(),
                    false, false, "skipped_preview", "not_applicable"),
                new BundleArtifact(
                    "avalonia-osx-arm64-installer", "avalonia", "macos", "arm64", "dmg",
                    "chummer-avalonia-osx-arm64-installer.dmg", "mac-cutover"u8.ToArray(),
                    false, false, "skipped_preview", "skipped_preview")
            ],
            publishedAt: "2026-07-17T20:00:00Z",
            proofGeneratedAt: "2026-07-17T19:55:00Z");
        fixture.ExtractBundleAsLegacyShelf(bundlePath);
        byte[] compatibilityBefore = File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "releases.json"));
        byte[] canonicalBefore = File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json"));
        Assert.True(fixture.CaptureActiveShelf().IsLegacy);

        ReleaseBundlePromotionResult? migrated = await fixture.EnsureInitialLegacyMigrationAsync();

        Assert.NotNull(migrated);
        Assert.False(string.IsNullOrWhiteSpace(migrated!.GenerationId));
        Assert.False(fixture.CaptureActiveShelf().IsLegacy);
        Assert.Equal(migrated.GenerationId, fixture.CaptureActiveShelf().GenerationId);
        Assert.Equal(compatibilityBefore, fixture.ReadGenerationBytes(migrated.GenerationId!, "releases.json"));
        Assert.Equal(canonicalBefore, fixture.ReadGenerationBytes(migrated.GenerationId!, "RELEASE_CHANNEL.generated.json"));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-layout-v1")));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-writer-policy.json")));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-intent.json")));
        Assert.Equal(
            new ReleaseShelfPublicationReadinessProbeResult(true, "ready"),
            fixture.EvaluateActivationReadiness());

        ReleaseBundlePromotionResult? restarted = await fixture.EnsureInitialLegacyMigrationAsync();

        Assert.Null(restarted);
        Assert.Equal(migrated.GenerationId, fixture.CaptureActiveShelf().GenerationId);
        Assert.Single(fixture.FindGenerationDirectories());
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-intent.json")));
        Assert.Equal(
            new ReleaseShelfPublicationReadinessProbeResult(true, "ready"),
            fixture.EvaluateActivationReadiness());
    }

    [Fact]
    public async Task PromoteAsyncRejectsShelfReplacementThatDropsExistingDesktopInstallTuple()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-linux-x64-installer",
            fileName: "chummer-avalonia-linux-x64-installer.deb",
            platform: "linux",
            arch: "x64",
            kind: "installer",
            bytes: "linux-live");
        IReadOnlyDictionary<string, byte[]> before = fixture.SnapshotManagedShelf();

        string macFileName = "chummer-avalonia-osx-arm64-installer.dmg";
        byte[] macBytes = "mac-live"u8.ToArray();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-215500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: macFileName,
                    Bytes: macBytes,
                    RequiresSigning: true,
                    RequiresNotarization: true)
            ]);

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(() => fixture.PromoteAsync(bundlePath));

        Assert.Contains("would drop existing desktop install tuple", error.Message, StringComparison.Ordinal);
        Assert.Contains("avalonia:linux:linux-x64", error.Message, StringComparison.Ordinal);
        Assert.Contains("Scoped updates and explicit removals are not supported yet", error.Message, StringComparison.Ordinal);
        AssertManagedShelfMatches(before, fixture.SnapshotManagedShelf());
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", macFileName)));
        Assert.Empty(fixture.FindPromotionTransactionDirectories());
    }

    [Fact]
    public async Task PromoteAsyncValidatesCompleteStagedShelfBeforeMutatingLiveShelf()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-win-x64-installer",
            fileName: "chummer-avalonia-win-x64-installer.exe",
            platform: "windows",
            arch: "x64",
            kind: "installer",
            bytes: "windows-live");
        fixture.WriteManagedShelfFile("startup-smoke/original.receipt.json", "original-smoke");
        fixture.WriteManagedShelfFile("proof/original/proof.json", "original-proof");
        IReadOnlyDictionary<string, byte[]> before = fixture.SnapshotManagedShelf();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-staged-validation",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "replacement-windows"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);
        bool stagedShelfValidated = false;

        IOException error = await Assert.ThrowsAsync<IOException>(() => fixture.PromoteAsync(
            bundlePath,
            checkpoint =>
            {
                if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.StagedShelfValidated)
                {
                    stagedShelfValidated = true;
                    AssertManagedShelfMatches(before, fixture.SnapshotManagedShelf());
                    throw new IOException("stop after staged shelf validation");
                }
            }));

        Assert.True(stagedShelfValidated);
        Assert.Contains("stop after staged shelf validation", error.Message, StringComparison.Ordinal);
        AssertManagedShelfMatches(before, fixture.SnapshotManagedShelf());
        Assert.Empty(fixture.FindPromotionTransactionDirectories());
    }

    [Fact]
    public async Task PromoteAsyncLeavesPreviousShelfActiveWhenGenerationPreparationFails()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-osx-arm64-installer",
            fileName: "chummer-avalonia-osx-arm64-installer.dmg",
            platform: "macos",
            arch: "arm64",
            kind: "dmg",
            bytes: "mac-live");
        fixture.WriteManagedShelfFile("startup-smoke/original.receipt.json", "original-smoke");
        fixture.WriteManagedShelfFile("proof/original/proof.json", "original-proof");
        IReadOnlyDictionary<string, byte[]> before = fixture.SnapshotManagedShelf();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260713-rollback",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "replacement-mac"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        ReleaseActivationAbortedException error = await Assert.ThrowsAsync<ReleaseActivationAbortedException>(() => fixture.PromoteAsync(
            bundlePath,
            checkpoint =>
            {
                if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.GenerationPrepared)
                {
                    throw new IOException("injected generation preparation failure");
                }
            }));

        Assert.Equal("injected generation preparation failure", error.InnerException?.Message);
        AssertManagedShelfMatches(before, fixture.SnapshotManagedShelf());
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.Empty(fixture.FindGenerationDirectories());
        Assert.Empty(fixture.FindPromotionTransactionDirectories());

        ReleaseBundlePromotionResult retry = await fixture.PromoteAsync(bundlePath);
        Assert.Equal("run-20260713-rollback", retry.Version);
        Assert.Single(fixture.FindGenerationDirectories());
    }

    [Fact]
    public async Task PromoteAsyncLeavesPreviousShelfActiveWhenPointerPreparationFails()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-win-x64-installer",
            fileName: fileName,
            platform: "windows",
            arch: "x64",
            kind: "installer",
            bytes: "windows-live");
        fixture.WriteManagedShelfFile("startup-smoke/original.receipt.json", "original-smoke");
        fixture.WriteManagedShelfFile("proof/original/proof.json", "original-proof");
        IReadOnlyDictionary<string, byte[]> before = fixture.SnapshotManagedShelf();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-final-validation-rollback",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "replacement-windows"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseActivationAbortedException error = await Assert.ThrowsAsync<ReleaseActivationAbortedException>(() => fixture.PromoteAsync(
            bundlePath,
            checkpoint =>
            {
                if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.PointerPrepared)
                {
                    throw new IOException("injected current pointer preparation failure");
                }
            }));

        Assert.Equal(
            "injected current pointer preparation failure",
            error.InnerException?.Message);
        AssertManagedShelfMatches(before, fixture.SnapshotManagedShelf());
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-layout-v1")));
        Assert.Empty(fixture.FindGenerationDirectories());
        Assert.Empty(fixture.FindPromotionTransactionDirectories());

        ReleaseBundlePromotionResult retry = await fixture.PromoteAsync(bundlePath);
        Assert.Equal("run-20260715-final-validation-rollback", retry.Version);
    }

    [Fact]
    public async Task PromoteAsyncRestoresByteIdenticalShelfWhenCommitIsCancelled()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-win-x64-installer",
            fileName: "chummer-avalonia-win-x64-installer.exe",
            platform: "windows",
            arch: "x64",
            kind: "installer",
            bytes: "windows-live");
        fixture.WriteManagedShelfFile("startup-smoke/original.receipt.json", "original-smoke");
        fixture.WriteManagedShelfFile("proof/original/proof.json", "original-proof");
        IReadOnlyDictionary<string, byte[]> before = fixture.SnapshotManagedShelf();
        using var cancellation = new CancellationTokenSource();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260713-cancel",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "replacement-windows"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseActivationAbortedException error = await Assert.ThrowsAsync<ReleaseActivationAbortedException>(() => fixture.PromoteAsync(
            bundlePath,
            checkpoint =>
            {
                if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.GenerationPrepared)
                {
                    cancellation.Cancel();
                }
            },
            cancellation.Token));

        Assert.IsAssignableFrom<OperationCanceledException>(error.InnerException);
        AssertManagedShelfMatches(before, fixture.SnapshotManagedShelf());
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.Empty(fixture.FindGenerationDirectories());
        Assert.Empty(fixture.FindPromotionTransactionDirectories());
    }

    [Fact]
    public async Task PromoteAsyncCannotTurnCommittedPointerIntoRetryableFailure()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-post-activation",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "post-activation"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(
            bundlePath,
            checkpoint =>
            {
                if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.PointerActivated)
                {
                    throw new IOException("post-activation callback failure");
                }
            });

        Assert.False(string.IsNullOrWhiteSpace(result.GenerationId));
        Assert.False(string.IsNullOrWhiteSpace(result.ActivationReceiptId));
        using JsonDocument pointer = fixture.ReadCurrentPointer();
        Assert.Equal(result.GenerationId, pointer.RootElement.GetProperty("generationId").GetString());
        Assert.Equal(result.ActivationReceiptId, pointer.RootElement.GetProperty("activationReceiptId").GetString());
    }

    [Fact]
    public async Task DurableActivationJournalReconcilesAcrossRestartAndRetainsReceiptHistory()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundleA = fixture.CreateBundle(
            version: "run-20260715-journal-a",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "journal-a"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult resultA = await fixture.PromoteAsync(bundleA);
        string bundleB = fixture.CreateBundle(
            version: "run-20260715-journal-b",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "journal-b"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);

        ReleaseActivationIntent? capturedIntent = null;
        ReleaseActivationOutcomeUnknownException unknown = await Assert.ThrowsAsync<ReleaseActivationOutcomeUnknownException>(
            () => fixture.PromoteDirectoryWithActivationCallbackAsync(
                bundleB,
                intent => capturedIntent = intent,
                _ => throw new IOException("simulated parent-directory fsync failure")));
        Assert.NotNull(capturedIntent);
        Assert.Equal(capturedIntent, unknown.Intent);
        using (JsonDocument current = fixture.ReadCurrentPointer())
        {
            Assert.Equal(capturedIntent!.GenerationId, current.RootElement.GetProperty("generationId").GetString());
        }

        string receiptRoot = fixture.ActivationJournalReceiptRoot(capturedIntent!.ActivationReceiptId);
        string intentPath = Path.Combine(receiptRoot, "intent.json");
        Assert.True(File.Exists(intentPath));
        Assert.False(File.Exists(Path.Combine(receiptRoot, "outcome.json")));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-intent.json")));
        ReleaseShelfPublicationReadinessProbeResult preparedReadiness = fixture.EvaluateActivationReadiness();
        Assert.False(preparedReadiness.Ready);
        Assert.Equal("activation_journal_unresolved", preparedReadiness.Code);
        if (!OperatingSystem.IsWindows())
        {
            Assert.Equal(
                UnixFileMode.UserRead | UnixFileMode.UserWrite,
                File.GetUnixFileMode(intentPath));
        }

        await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.PromoteAsync(bundleA));
        Assert.True(fixture.TryReconcileActivation(capturedIntent, out ReleaseBundlePromotionResult? reconciled));
        Assert.Equal(capturedIntent.GenerationId, reconciled!.GenerationId);
        Assert.True(File.Exists(Path.Combine(receiptRoot, "outcome.json")));
        ReleaseShelfPublicationReadinessProbeResult committedReadiness = fixture.EvaluateActivationReadiness();
        Assert.False(committedReadiness.Ready);
        Assert.Equal("activation_ack_pending", committedReadiness.Code);
        await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.PromoteAsync(bundleA));

        fixture.AcknowledgeActivationCompletion(capturedIntent);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-intent.json")));
        Assert.Equal(
            new ReleaseShelfPublicationReadinessProbeResult(true, "ready"),
            fixture.EvaluateActivationReadiness());
        ReleaseBundlePromotionResult resultC = await fixture.PromoteAsync(bundleA);
        Assert.NotEqual(capturedIntent.GenerationId, resultC.GenerationId);
        Assert.True(fixture.TryReconcileActivation(capturedIntent, out ReleaseBundlePromotionResult? historical));
        Assert.Equal(capturedIntent.GenerationId, historical!.GenerationId);
        Assert.Equal("run-20260715-journal-a", resultA.Version);
    }

    [Fact]
    public async Task ActivationCallbackFailureRemovesUnjournaledGenerationBeforePointerRename()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundleA = fixture.CreateBundle(
            version: "run-20260715-abort-a",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "abort-a"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult resultA = await fixture.PromoteAsync(bundleA);
        string bundleB = fixture.CreateBundle(
            version: "run-20260715-abort-b",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "abort-b"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);

        ReleaseActivationIntent? capturedIntent = null;
        IOException aborted = await Assert.ThrowsAsync<IOException>(
            () => fixture.PromoteDirectoryWithActivationCallbackAsync(
                bundleB,
                intent =>
                {
                    capturedIntent = intent;
                    throw new IOException("simulated session intent persistence failure");
                }));
        Assert.Equal("simulated session intent persistence failure", aborted.Message);
        using (JsonDocument current = fixture.ReadCurrentPointer())
        {
            Assert.Equal(resultA.GenerationId, current.RootElement.GetProperty("generationId").GetString());
        }

        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-intent.json")));
        Assert.False(fixture.TryReconcileActivation(capturedIntent!, out _));
        Assert.False(Directory.Exists(
            fixture.ActivationJournalReceiptRoot(capturedIntent!.ActivationReceiptId)));
        ReleaseBundlePromotionResult retry = await fixture.PromoteAsync(bundleB);
        Assert.Equal("run-20260715-abort-b", retry.Version);
    }

    [Fact]
    public async Task SessionIntentWithoutJournalReconcilesExactNeverActivatedGenerationAcrossRestart()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundle = fixture.CreateBundle(
            version: "run-20260715-session-journal-seam",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "session-journal-seam"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);

        ReleaseActivationIntent? recordedIntent = null;
        IOException interrupted = await Assert.ThrowsAsync<IOException>(
            () => fixture.PromoteDirectoryWithActivationCallbackAsync(
                bundle,
                intent => recordedIntent = intent,
                promotionCheckpoint: checkpoint =>
                {
                    if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.ActivationIntentRecorded)
                    {
                        throw new IOException("simulated process termination before activation journal");
                    }
                }));

        Assert.Equal("simulated process termination before activation journal", interrupted.Message);
        Assert.NotNull(recordedIntent);
        Assert.Null(recordedIntent!.PreviousPointerBase64);
        Assert.NotNull(recordedIntent.TargetPointerBase64);
        Assert.False(Directory.Exists(
            fixture.ActivationJournalReceiptRoot(recordedIntent.ActivationReceiptId)));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-intent.json")));
        Assert.Empty(fixture.FindGenerationDirectories());
        Assert.False(fixture.TryReconcileActivation(recordedIntent, out _));
        Assert.Empty(fixture.FindGenerationDirectories());

        ReleaseBundlePromotionResult retry = await fixture.PromoteAsync(bundle);
        Assert.Equal("run-20260715-session-journal-seam", retry.Version);
    }

    [Fact]
    public async Task ActiveIntentWithoutHistoryIsRepairedAndAbortedAcrossRestart()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundle = fixture.CreateBundle(
            version: "run-20260715-active-only-seam",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "active-only-seam"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);
        ReleaseActivationIntent? recordedIntent = null;

        await Assert.ThrowsAsync<ReleaseActivationProcessTerminationSimulationException>(
            () => fixture.PromoteDirectoryWithActivationCallbackAsync(
                bundle,
                intent => recordedIntent = intent,
                activationJournalCheckpoint: checkpoint =>
                {
                    if (checkpoint == ReleaseBundlePromotionService.ActivationJournalCheckpoint.ActiveIntentDurable)
                    {
                        throw new ReleaseActivationProcessTerminationSimulationException(
                            "simulated death after active intent fsync");
                    }
                }));

        Assert.NotNull(recordedIntent);
        Assert.True(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-activation-intent.json")));
        Assert.False(Directory.Exists(
            fixture.ActivationJournalReceiptRoot(recordedIntent!.ActivationReceiptId)));
        Assert.False(fixture.TryReconcileActivation(recordedIntent, out _));
        string receiptRoot = fixture.ActivationJournalReceiptRoot(recordedIntent.ActivationReceiptId);
        Assert.True(File.Exists(Path.Combine(receiptRoot, "intent.json")));
        Assert.True(File.Exists(Path.Combine(receiptRoot, "outcome.json")));
        Assert.False(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-activation-intent.json")));
        Assert.Empty(fixture.FindGenerationDirectories());

        ReleaseBundlePromotionResult retry = await fixture.PromoteAsync(bundle);
        Assert.Equal("run-20260715-active-only-seam", retry.Version);
    }

    [Fact]
    public async Task PreparedJournalAndGenerationAreAbortedAndRemovedAcrossRestart()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundle = fixture.CreateBundle(
            version: "run-20260715-generation-durable-seam",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "generation-durable-seam"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);
        ReleaseActivationIntent? recordedIntent = null;

        await Assert.ThrowsAsync<ReleaseActivationProcessTerminationSimulationException>(
            () => fixture.PromoteDirectoryWithActivationCallbackAsync(
                bundle,
                intent => recordedIntent = intent,
                promotionCheckpoint: checkpoint =>
                {
                    if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.GenerationDirectoryDurable)
                    {
                        throw new ReleaseActivationProcessTerminationSimulationException(
                            "simulated death after generation parent fsync");
                    }
                }));

        Assert.NotNull(recordedIntent);
        Assert.Single(fixture.FindGenerationDirectories());
        Assert.True(File.Exists(Path.Combine(
            fixture.ActivationJournalReceiptRoot(recordedIntent!.ActivationReceiptId),
            "intent.json")));
        Assert.False(fixture.TryReconcileActivation(recordedIntent, out _));
        Assert.Empty(fixture.FindGenerationDirectories());
        Assert.True(File.Exists(Path.Combine(
            fixture.ActivationJournalReceiptRoot(recordedIntent.ActivationReceiptId),
            "outcome.json")));

        ReleaseBundlePromotionResult retry = await fixture.PromoteAsync(bundle);
        Assert.Equal("run-20260715-generation-durable-seam", retry.Version);
    }

    [Fact]
    public async Task SessionOnlyIntentRemovesExactLegacyOrphanGenerationWithoutBroadCleanup()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundle = fixture.CreateBundle(
            version: "run-20260715-exact-orphan-seam",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "exact-orphan-seam"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);
        ReleaseActivationIntent? recordedIntent = null;
        await Assert.ThrowsAsync<ReleaseActivationProcessTerminationSimulationException>(
            () => fixture.PromoteDirectoryWithActivationCallbackAsync(
                bundle,
                intent => recordedIntent = intent,
                promotionCheckpoint: checkpoint =>
                {
                    if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.GenerationDirectoryDurable)
                    {
                        throw new ReleaseActivationProcessTerminationSimulationException(
                            "materialize legacy pre-journal orphan state");
                    }
                }));

        Assert.NotNull(recordedIntent);
        string unrelated = Path.Combine(fixture.DownloadsRoot, "generations", "foreign-generation");
        Directory.CreateDirectory(unrelated);
        File.WriteAllText(Path.Combine(unrelated, "sentinel.txt"), "must remain");
        File.Delete(Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-intent.json"));
        Directory.Delete(
            fixture.ActivationJournalReceiptRoot(recordedIntent!.ActivationReceiptId),
            recursive: true);

        Assert.False(fixture.TryReconcileActivation(recordedIntent, out _));
        Assert.False(Directory.Exists(Path.Combine(
            fixture.DownloadsRoot,
            "generations",
            recordedIntent.GenerationId)));
        Assert.True(File.Exists(Path.Combine(unrelated, "sentinel.txt")));
    }

    [Theory]
    [InlineData((int)ReleaseBundlePromotionService.ActivationJournalCheckpoint.ActiveIntentDurable)]
    [InlineData((int)ReleaseBundlePromotionService.ActivationJournalCheckpoint.ReceiptTempDirectoryDurable)]
    [InlineData((int)ReleaseBundlePromotionService.ActivationJournalCheckpoint.ReceiptIntentDurable)]
    [InlineData((int)ReleaseBundlePromotionService.ActivationJournalCheckpoint.ReceiptHistoryPublished)]
    [InlineData((int)ReleaseBundlePromotionService.ActivationJournalCheckpoint.ReceiptHistoryParentDurable)]
    public async Task PartialActivationJournalPreparationConvergesWithoutExposingPartialReceipt(
        int failurePointValue)
    {
        var failurePoint = (ReleaseBundlePromotionService.ActivationJournalCheckpoint)failurePointValue;
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundleA = fixture.CreateBundle(
            version: "run-20260715-journal-fault-a",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "journal-fault-a"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult active = await fixture.PromoteAsync(bundleA);
        string bundleB = fixture.CreateBundle(
            version: "run-20260715-journal-fault-b",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "journal-fault-b"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);

        await Assert.ThrowsAnyAsync<IOException>(() => fixture.PromoteDirectoryWithActivationCallbackAsync(
            bundleB,
            _ => { },
            activationJournalCheckpoint: checkpoint =>
            {
                if (checkpoint == failurePoint)
                {
                    if (checkpoint == ReleaseBundlePromotionService.ActivationJournalCheckpoint.ReceiptHistoryPublished)
                    {
                        string publishedHistoryRoot = Path.Combine(
                            fixture.DownloadsRoot,
                            ".release-shelf-activation-journal");
                        string publishedReceipt = Assert.Single(
                            Directory.EnumerateDirectories(publishedHistoryRoot),
                            receipt => !File.Exists(Path.Combine(receipt, "outcome.json")));
                        Assert.True(File.Exists(Path.Combine(publishedReceipt, "intent.json")));
                        Assert.Empty(Directory.EnumerateDirectories(
                            fixture.DownloadsRoot,
                            ".release-shelf-activation-receipt-*.tmp",
                            SearchOption.TopDirectoryOnly));
                    }

                    throw new IOException("simulated activation journal crash boundary");
                }
            }));

        using (JsonDocument current = fixture.ReadCurrentPointer())
        {
            Assert.Equal(active.GenerationId, current.RootElement.GetProperty("generationId").GetString());
        }

        string historyRoot = Path.Combine(fixture.DownloadsRoot, ".release-shelf-activation-journal");
        Assert.DoesNotContain(
            Directory.Exists(historyRoot) ? Directory.EnumerateDirectories(historyRoot) : [],
            receipt => !File.Exists(Path.Combine(receipt, "intent.json")));

        ReleaseBundlePromotionResult retry = await fixture.PromoteAsync(bundleB);
        Assert.Equal("run-20260715-journal-fault-b", retry.Version);
        Assert.Empty(Directory.EnumerateDirectories(
            fixture.DownloadsRoot,
            ".release-shelf-activation-receipt-*.tmp",
            SearchOption.TopDirectoryOnly));
    }

    [Theory]
    [InlineData("swapped_file")]
    [InlineData("wrong_sha")]
    [InlineData("missing_sha")]
    [InlineData("platform")]
    [InlineData("rid")]
    [InlineData("payload")]
    [InlineData("external_url")]
    public async Task ManifestArtifactContractMismatchCannotActivate(string mutation)
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string initialBundle = fixture.CreateBundle(
            version: "run-20260715-contract-a",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "contract-a"u8.ToArray(),
                    false, false, "skipped_preview")
            ]);
        await fixture.PromoteAsync(initialBundle);
        byte[] pointerBefore = File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "current.json"));
        string replacementBundle = fixture.CreateBundle(
            version: "run-20260715-contract-b",
            artifacts:
            [
                new BundleArtifact(
                    "avalonia-win-x64-installer", "avalonia", "windows", "x64", "installer",
                    "chummer-avalonia-win-x64-installer.exe", "contract-b-win"u8.ToArray(),
                    false, false, "skipped_preview"),
                new BundleArtifact(
                    "avalonia-linux-x64-archive", "avalonia", "linux", "x64", "archive",
                    "chummer-avalonia-linux-x64.tar.gz", "contract-b-linux"u8.ToArray(),
                    false, false)
            ]);

        if (mutation == "external_url")
        {
            foreach (string manifestName in new[] { "releases.json", "RELEASE_CHANNEL.generated.json" })
            {
                fixture.RewriteBundleManifest(replacementBundle, manifestName, root =>
                {
                    JsonObject row = root[manifestName == "releases.json" ? "downloads" : "artifacts"]![0]!.AsObject();
                    row[manifestName == "releases.json" ? "url" : "downloadUrl"] = "https://evil.invalid/payload.exe";
                });
            }
        }
        else
        {
            fixture.RewriteBundleManifest(replacementBundle, "releases.json", root =>
            {
                JsonObject row = root["downloads"]![0]!.AsObject();
                JsonObject other = root["downloads"]![1]!.AsObject();
                switch (mutation)
                {
                    case "swapped_file":
                        foreach (string field in new[] { "fileName", "url", "sha256", "sizeBytes" })
                        {
                            row[field] = other[field]?.DeepClone();
                        }
                        break;
                    case "wrong_sha":
                        row["sha256"] = new string('0', 64);
                        break;
                    case "missing_sha":
                        row.Remove("sha256");
                        break;
                    case "platform":
                        row["platformId"] = "linux-x64";
                        break;
                    case "rid":
                        row["rid"] = "linux-x64";
                        break;
                    case "payload":
                        row["payloadFileName"] = "unexpected.payload";
                        row["payloadDownloadUrl"] = "/downloads/files/unexpected.payload";
                        row["payloadSha256"] = new string('1', 64);
                        row["payloadSizeBytes"] = 1;
                        break;
                }
            });
        }

        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.PromoteAsync(replacementBundle));
        Assert.Equal(pointerBefore, File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "current.json")));
    }

    [Fact]
    public async Task PromoteAsyncEmitsReaderValidatedImmutableGenerationContract()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-win-x64-installer";
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-generation-contract",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: artifactId,
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "generation-contract"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.NotNull(result.GenerationId);
        Assert.NotNull(result.ActivationReceiptId);
        if (!OperatingSystem.IsWindows())
        {
            Assert.Equal(
                UnixFileMode.UserRead | UnixFileMode.UserWrite,
                File.GetUnixFileMode(Path.Combine(fixture.DownloadsRoot, ".release-shelf-promotion.lock")));
        }
        Assert.All(result.InstallDispatchUrls, url => Assert.Contains(
            $"/downloads/g/{result.GenerationId}/install/",
            url,
            StringComparison.Ordinal));
        Assert.All(result.DirectFileUrls, url => Assert.Contains(
            $"/downloads/g/{result.GenerationId}/install/",
            url,
            StringComparison.Ordinal));
        ReleaseShelfSnapshot snapshot = fixture.CaptureActiveShelf();
        Assert.Equal(result.GenerationId, snapshot.GenerationId);
        Assert.Equal(result.ActivationReceiptId, snapshot.ActivationReceiptId);
        Assert.False(snapshot.IsLegacy);

        using JsonDocument pointer = fixture.ReadCurrentPointer();
        JsonElement pointerRoot = pointer.RootElement;
        Assert.Equal("chummer.release-shelf.current/v1", pointerRoot.GetProperty("schemaVersion").GetString());
        Assert.Equal($"sha256:{snapshot.InventoryDigest}", pointerRoot.GetProperty("inventoryDigest").GetString());
        JsonElement bindings = pointerRoot.GetProperty("manifests");
        Assert.Equal(
            $"/downloads/g/{result.GenerationId}/RELEASE_CHANNEL.generated.json",
            bindings.GetProperty("canonical").GetProperty("path").GetString());
        Assert.Equal(
            $"/downloads/g/{result.GenerationId}/releases.json",
            bindings.GetProperty("compatibility").GetProperty("path").GetString());

        using JsonDocument candidate = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(snapshot.PhysicalRoot, "activation-candidate.json")));
        Assert.Equal(
            "chummer.release-shelf.activation-candidate/v1",
            candidate.RootElement.GetProperty("schemaVersion").GetString());
        Assert.Equal(result.GenerationId, candidate.RootElement.GetProperty("generationId").GetString());
        Assert.Equal(result.Version, candidate.RootElement.GetProperty("releaseVersion").GetString());
        Assert.Equal(result.Channel, candidate.RootElement.GetProperty("channel").GetString());
        Assert.Equal(result.PublishedAt, candidate.RootElement.GetProperty("publishedAt").GetDateTimeOffset());
        Assert.Equal(
            bindings.GetProperty("canonical").GetProperty("path").GetString(),
            candidate.RootElement.GetProperty("manifests").GetProperty("canonical").GetProperty("path").GetString());
        Assert.Equal(
            bindings.GetProperty("canonical").GetProperty("sha256").GetString(),
            candidate.RootElement.GetProperty("manifests").GetProperty("canonical").GetProperty("sha256").GetString());
        Assert.Equal(
            bindings.GetProperty("compatibility").GetProperty("sha256").GetString(),
            candidate.RootElement.GetProperty("manifests").GetProperty("compatibility").GetProperty("sha256").GetString());
        Assert.Equal($"sha256:{snapshot.InventoryDigest}", candidate.RootElement.GetProperty("inventoryDigest").GetString());
        string[] inventoryPaths = candidate.RootElement.GetProperty("inventory")
            .EnumerateArray()
            .Select(row => row.GetProperty("path").GetString()!)
            .ToArray();
        Assert.Equal(inventoryPaths.OrderBy(static path => path, StringComparer.Ordinal).ToArray(), inventoryPaths);
        Assert.DoesNotContain("RELEASE_CHANNEL.generated.json", inventoryPaths);
        Assert.DoesNotContain("releases.json", inventoryPaths);

        using JsonDocument canonical = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(snapshot.PhysicalRoot, "RELEASE_CHANNEL.generated.json")));
        using JsonDocument compatibility = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(snapshot.PhysicalRoot, "releases.json")));
        Assert.False(canonical.RootElement.TryGetProperty("generationId", out _));
        Assert.False(compatibility.RootElement.TryGetProperty("generationId", out _));
        Assert.Equal(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe",
            canonical.RootElement.GetProperty("artifacts")[0].GetProperty("downloadUrl").GetString());
        Assert.Equal(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe",
            compatibility.RootElement.GetProperty("downloads")[0].GetProperty("url").GetString());
        string[] proofRoutes = canonical.RootElement.GetProperty("releaseProof").GetProperty("proofRoutes")
            .EnumerateArray()
            .Select(static route => route.GetString()!)
            .ToArray();
        Assert.Contains($"/downloads/install/{artifactId}", proofRoutes);
        Assert.DoesNotContain(
            proofRoutes,
            route => route.StartsWith($"/downloads/g/{result.GenerationId}/", StringComparison.Ordinal));
        JsonObject retainedReleaseProof = JsonNode.Parse(
            canonical.RootElement.GetProperty("releaseProof").GetRawText())!.AsObject();
        ReleaseProofTrustEvaluation proofTrust = ReleaseProofTrustEvaluator.Validate(retainedReleaseProof);
        Assert.True(proofTrust.IsValid, proofTrust.Reason);
    }

    [Fact]
    public async Task PromoteAsyncPreservesNestedRegistryExtensionBytes()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-win-x64-installer";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-nested-proof-route",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: artifactId,
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "nested-proof-route"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);
        fixture.RewriteBundleManifest(
            bundlePath,
            "RELEASE_CHANNEL.generated.json",
            manifest => manifest["extension"] = new JsonObject
            {
                ["releaseProof"] = new JsonObject
                {
                    ["proofRoutes"] = new JsonArray($"/downloads/install/{artifactId}")
                }
            });

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);
        ReleaseShelfSnapshot snapshot = fixture.CaptureActiveShelf();
        using JsonDocument canonical = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(snapshot.PhysicalRoot, "RELEASE_CHANNEL.generated.json")));
        string nestedRoute = canonical.RootElement
            .GetProperty("extension")
            .GetProperty("releaseProof")
            .GetProperty("proofRoutes")[0]
            .GetString()!;

        Assert.Equal($"/downloads/install/{artifactId}", nestedRoute);
    }

    [Fact]
    public async Task PromoteAsyncUsesGenerationFilesOnlyForExplicitOpenPublicArtifact()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-linux-x64-installer";
        const string fileName = "chummer-avalonia-linux-x64-installer.deb";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-open-public-generation",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: artifactId,
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "open-public-generation"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    InstallAccessClass: "open_public")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Single(result.DirectFileUrls);
        Assert.Equal(
            $"https://chummer.run/downloads/g/{result.GenerationId}/files/{fileName}",
            result.DirectFileUrls[0]);
        Assert.Single(result.InstallDispatchUrls);
        Assert.Equal(
            $"https://chummer.run/downloads/g/{result.GenerationId}/files/{fileName}",
            result.InstallDispatchUrls[0]);
        using JsonDocument canonical = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            fixture.DownloadsRoot,
            "generations",
            result.GenerationId!,
            "RELEASE_CHANNEL.generated.json")));
        Assert.Equal(
            $"/downloads/files/{fileName}",
            canonical.RootElement.GetProperty("artifacts")[0].GetProperty("downloadUrl").GetString());

        string replacementBundle = fixture.CreateBundle(
            version: "run-20260715-open-public-generation-replaced",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: artifactId,
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "account-required-replacement"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    InstallAccessClass: "account_required")
            ]);
        await fixture.PromoteAsync(replacementBundle);

        ReleaseBundlePromotionResult rollback = await fixture.RollbackAsync(result.GenerationId!);

        Assert.Single(rollback.InstallDispatchUrls);
        Assert.Equal(
            $"https://chummer.run/downloads/g/{result.GenerationId}/files/{fileName}",
            rollback.InstallDispatchUrls[0]);
    }

    [Theory]
    [InlineData("files/nested/shadow.exe", "not bound")]
    [InlineData("files/CHUMMER-AVALONIA-WIN-X64-INSTALLER.EXE", "case-colliding")]
    [InlineData("files/über.exe", "non-portable")]
    [InlineData("files/.hidden.exe", "non-portable")]
    [InlineData("files/bad name.exe", "non-portable")]
    [InlineData("files/bad$thing.exe", "non-portable")]
    public async Task PromoteAsyncRejectsNonCanonicalArtifactPathsBeforeChangingActiveGeneration(
        string maliciousRelativePath,
        string expectedMessage)
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-win-x64-installer";
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        string initialBundle = fixture.CreateBundle(
            version: "run-20260715-path-guard-a",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: artifactId,
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "path-guard-a"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);
        ReleaseBundlePromotionResult active = await fixture.PromoteAsync(initialBundle);
        byte[] pointerBefore = File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "current.json"));
        string[] generationsBefore = fixture.FindGenerationDirectories()
            .OrderBy(static path => path, StringComparer.Ordinal)
            .ToArray();

        string maliciousBundle = fixture.CreateBundle(
            version: "run-20260715-path-guard-b",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: artifactId,
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "path-guard-b"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);
        fixture.AddBundleEntry(maliciousBundle, maliciousRelativePath, "shadow"u8.ToArray());

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(maliciousBundle));

        Assert.Contains(expectedMessage, error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(active.GenerationId, fixture.ReadCurrentPointer().RootElement.GetProperty("generationId").GetString());
        Assert.Equal(pointerBefore, File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.Equal(
            generationsBefore,
            fixture.FindGenerationDirectories().OrderBy(static path => path, StringComparer.Ordinal).ToArray());
        Assert.Empty(fixture.FindPromotionTransactionDirectories());
    }

    [Fact]
    public async Task PromoteAsyncAtomicPointerReadersObserveOnlyCompleteGenerationAOrB()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-win-x64-installer";
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        string bundleA = fixture.CreateBundle(
            version: "run-20260715-atomic-a",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "atomic-a"u8.ToArray(), false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult resultA = await fixture.PromoteAsync(bundleA);
        string bundleB = fixture.CreateBundle(
            version: "run-20260715-atomic-b",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "atomic-b"u8.ToArray(), false, false, "skipped_preview")
            ]);

        var failures = new ConcurrentQueue<Exception>();
        using var stopReaders = new CancellationTokenSource();
        int reads = 0;
        Task reader = Task.Run(() =>
        {
            while (!stopReaders.IsCancellationRequested)
            {
                try
                {
                    using JsonDocument pointer = fixture.ReadCurrentPointer();
                    string generationId = pointer.RootElement.GetProperty("generationId").GetString()!;
                    string generationRoot = Path.Combine(fixture.DownloadsRoot, "generations", generationId);
                    using JsonDocument manifest = JsonDocument.Parse(File.ReadAllText(
                        Path.Combine(generationRoot, "RELEASE_CHANNEL.generated.json")));
                    JsonElement artifact = manifest.RootElement.GetProperty("artifacts")[0];
                    string downloadUrl = artifact.GetProperty("downloadUrl").GetString()!;
                    Assert.Equal($"/downloads/files/{fileName}", downloadUrl);
                    string bytes = File.ReadAllText(Path.Combine(generationRoot, "files", fileName));
                    string version = manifest.RootElement.GetProperty("version").GetString()!;
                    Assert.True(
                        (version == "run-20260715-atomic-a" && bytes == "atomic-a")
                        || (version == "run-20260715-atomic-b" && bytes == "atomic-b"));
                    Interlocked.Increment(ref reads);
                }
                catch (Exception ex)
                {
                    failures.Enqueue(ex);
                    return;
                }
            }
        });

        ReleaseBundlePromotionResult resultB = await fixture.PromoteAsync(
            bundleB,
            checkpoint =>
            {
                if (checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.PointerPrepared)
                {
                    Assert.True(SpinWait.SpinUntil(() => Volatile.Read(ref reads) >= 100, TimeSpan.FromSeconds(10)));
                }
            });
        stopReaders.Cancel();
        await reader;

        Assert.Empty(failures);
        Assert.NotEqual(resultA.GenerationId, resultB.GenerationId);
        using JsonDocument current = fixture.ReadCurrentPointer();
        Assert.Equal(resultB.GenerationId, current.RootElement.GetProperty("generationId").GetString());
    }

    [Fact]
    public async Task RollbackToGenerationAsyncChangesOnlyPointerAuthority()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-win-x64-installer";
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        string bundleA = fixture.CreateBundle(
            version: "run-20260715-rollback-a",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "rollback-a"u8.ToArray(), false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult resultA = await fixture.PromoteAsync(bundleA);
        string generationARoot = Path.Combine(fixture.DownloadsRoot, "generations", resultA.GenerationId!);
        IReadOnlyDictionary<string, byte[]> generationABefore = SnapshotTree(generationARoot);

        string bundleB = fixture.CreateBundle(
            version: "run-20260715-rollback-b",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "rollback-b"u8.ToArray(), false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult resultB = await fixture.PromoteAsync(bundleB);
        string generationBRoot = Path.Combine(fixture.DownloadsRoot, "generations", resultB.GenerationId!);
        IReadOnlyDictionary<string, byte[]> generationBBefore = SnapshotTree(generationBRoot);

        ReleaseBundlePromotionResult rollback = await fixture.RollbackAsync(resultA.GenerationId!);

        Assert.Equal(resultA.GenerationId, rollback.GenerationId);
        Assert.NotEqual(resultA.ActivationReceiptId, rollback.ActivationReceiptId);
        AssertManagedShelfMatches(generationABefore, SnapshotTree(generationARoot));
        AssertManagedShelfMatches(generationBBefore, SnapshotTree(generationBRoot));
        using JsonDocument current = fixture.ReadCurrentPointer();
        Assert.Equal(resultA.GenerationId, current.RootElement.GetProperty("generationId").GetString());
    }

    [Fact]
    public async Task RollbackRejectsInactiveManifestRouteMutationBoundByCandidate()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-win-x64-installer";
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        string bundleA = fixture.CreateBundle(
            version: "run-20260715-bound-candidate-a",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "candidate-a"u8.ToArray(), false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult resultA = await fixture.PromoteAsync(bundleA);
        string bundleB = fixture.CreateBundle(
            version: "run-20260715-bound-candidate-b",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "candidate-b"u8.ToArray(), false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult resultB = await fixture.PromoteAsync(bundleB);
        fixture.MutateGenerationJson(
            resultA.GenerationId!,
            "RELEASE_CHANNEL.generated.json",
            root => root["artifacts"]![0]!["downloadUrl"] =
                $"/downloads/g/{resultA.GenerationId}/files/{fileName}");

        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.RollbackAsync(resultA.GenerationId!));

        using JsonDocument current = fixture.ReadCurrentPointer();
        Assert.Equal(resultB.GenerationId, current.RootElement.GetProperty("generationId").GetString());
    }

    [Fact]
    public async Task CandidateEvidenceNamespacesReplacePriorInvocationWithoutAmbientCarry()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string windowsId = "avalonia-win-x64-installer";
        const string windowsFile = "chummer-avalonia-win-x64-installer.exe";
        string initialBundle = fixture.CreateBundle(
            version: "run-20260715-evidence-a",
            artifacts:
            [
                new BundleArtifact(
                    windowsId, "avalonia", "windows", "x64", "installer", windowsFile,
                    "windows-a"u8.ToArray(), false, false, "skipped_preview")
            ]);
        fixture.AddBundleEntry(
            initialBundle,
            "startup-smoke/startup-smoke-prior-invocation.receipt.json",
            "{\"headId\":\"old\",\"platform\":\"windows\",\"arch\":\"x64\"}"u8.ToArray());
        fixture.AddBundleEntry(
            initialBundle,
            "proof/prior-invocation.receipt.json",
            "{\"receiptId\":\"prior-proof\"}"u8.ToArray());
        fixture.AddBundleEntry(
            initialBundle,
            "release-evidence/prior-invocation.json",
            "{\"receiptId\":\"prior-evidence\"}"u8.ToArray());
        ReleaseBundlePromotionResult initial = await fixture.PromoteAsync(initialBundle);
        string initialRoot = Path.Combine(fixture.DownloadsRoot, "generations", initial.GenerationId!);
        Assert.True(File.Exists(Path.Combine(
            initialRoot,
            "startup-smoke",
            "startup-smoke-prior-invocation.receipt.json")));

        string replacementBundle = fixture.CreateBundle(
            version: "run-20260715-evidence-b",
            artifacts:
            [
                new BundleArtifact(
                    windowsId, "avalonia", "windows", "x64", "installer", windowsFile,
                    "windows-b"u8.ToArray(), false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult replacement = await fixture.PromoteAsync(replacementBundle);
        string replacementRoot = Path.Combine(fixture.DownloadsRoot, "generations", replacement.GenerationId!);

        Assert.False(File.Exists(Path.Combine(
            replacementRoot,
            "startup-smoke",
            "startup-smoke-prior-invocation.receipt.json")));
        Assert.False(File.Exists(Path.Combine(
            replacementRoot,
            "proof",
            "prior-invocation.receipt.json")));
        Assert.False(File.Exists(Path.Combine(
            replacementRoot,
            "release-evidence",
            "prior-invocation.json")));

        string missingReceiptBundle = fixture.CreateBundle(
            version: "run-20260715-evidence-missing",
            artifacts:
            [
                new BundleArtifact(
                    windowsId, "avalonia", "windows", "x64", "installer", windowsFile,
                    "windows-c"u8.ToArray(), false, false, "skipped_preview")
            ]);
        fixture.DeleteBundleEntries(
            missingReceiptBundle,
            static entry => entry.StartsWith("startup-smoke/", StringComparison.Ordinal));

        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.PromoteAsync(missingReceiptBundle));
        using JsonDocument current = fixture.ReadCurrentPointer();
        Assert.Equal(replacement.GenerationId, current.RootElement.GetProperty("generationId").GetString());
    }

    [Fact]
    public async Task SigningReceiptNamespaceIsGenerationBoundAndDoesNotAmbientlyCarryForward()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string artifactId = "avalonia-win-x64-installer";
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        const string receiptRelativePath = "signing/signing-avalonia-win-x64.receipt.json";
        byte[] receiptBytes = "{\"contractName\":\"chummer6-ui.desktop_artifact_signing\",\"signingStatus\":\"pass\"}"u8.ToArray();

        string signedBundle = fixture.CreateBundle(
            version: "run-20260716-signing-a",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "windows-signed-a"u8.ToArray(), false, false, "pass")
            ]);
        fixture.AddBundleEntry(signedBundle, receiptRelativePath, receiptBytes);

        ReleaseBundlePromotionResult signed = await fixture.PromoteAsync(signedBundle);
        string signedGenerationReceipt = Path.Combine(
            fixture.DownloadsRoot,
            "generations",
            signed.GenerationId!,
            receiptRelativePath.Replace('/', Path.DirectorySeparatorChar));
        string compatibilityMirrorReceipt = Path.Combine(
            fixture.DownloadsRoot,
            receiptRelativePath.Replace('/', Path.DirectorySeparatorChar));
        Assert.Equal(receiptBytes, File.ReadAllBytes(signedGenerationReceipt));
        Assert.Equal(receiptBytes, File.ReadAllBytes(compatibilityMirrorReceipt));

        string unsignedReplacementBundle = fixture.CreateBundle(
            version: "run-20260716-signing-b",
            artifacts:
            [
                new BundleArtifact(
                    artifactId, "avalonia", "windows", "x64", "installer", fileName,
                    "windows-unsigned-b"u8.ToArray(), false, false, "skipped_preview")
            ]);
        ReleaseBundlePromotionResult unsignedReplacement = await fixture.PromoteAsync(unsignedReplacementBundle);
        string replacementGenerationReceipt = Path.Combine(
            fixture.DownloadsRoot,
            "generations",
            unsignedReplacement.GenerationId!,
            receiptRelativePath.Replace('/', Path.DirectorySeparatorChar));

        Assert.False(File.Exists(replacementGenerationReceipt));
        Assert.False(File.Exists(compatibilityMirrorReceipt));
    }

    private static IReadOnlyDictionary<string, byte[]> SnapshotTree(string root)
        => Directory.GetFiles(root, "*", SearchOption.AllDirectories)
            .ToDictionary(
                path => Path.GetRelativePath(root, path).Replace(Path.DirectorySeparatorChar, '/'),
                File.ReadAllBytes,
                StringComparer.Ordinal);

    [Fact]
    public async Task PromoteAsyncRejectsMacBundleWithoutGovernedBuildProvenance()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string fileName = "chummer-avalonia-osx-arm64-installer.dmg";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260713-missing-provenance",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: fileName,
                    Bytes: "mac-without-provenance"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            includeBuildProvenance: false);

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("missing governed build provenance", failure.Message, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", fileName)));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json")));
    }

    [Fact]
    public async Task PromoteAsyncRejectsWindowsBundleWithoutGovernedBuildProvenance()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-windows-missing-provenance",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "windows-without-provenance"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ],
            includeBuildProvenance: false);

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("missing governed build provenance", failure.Message, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", fileName)));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json")));
    }

    [Fact]
    public async Task ValidateDirectoryAsyncRejectsDeterministicInvalidBundleBeforePublishingMutation()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-prevalidation",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "invalid-before-publishing"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            includeBuildProvenance: false);

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.ValidateBundleAsync(bundlePath));

        Assert.Contains("missing governed build provenance", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, ".release-shelf-layout-v1")));
        Assert.Empty(fixture.FindGenerationDirectories());
    }

    [Fact]
    public async Task PromoteAsyncReplacesStaleProofAndPreservesIncomingGovernedBuildProvenance()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-osx-arm64-installer",
            fileName: "chummer-avalonia-osx-arm64-installer.dmg",
            platform: "macos",
            arch: "arm64",
            kind: "dmg",
            bytes: "mac-live");
        fixture.WriteManagedShelfFile("startup-smoke/stale.receipt.json", "stale-smoke");
        fixture.WriteManagedShelfFile("proof/stale/proof.json", "stale-proof");

        string bundlePath = fixture.CreateBundle(
            version: "run-20260713-clean",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "replacement-mac"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);
        IReadOnlyDictionary<string, byte[]> incomingGovernedProof = ReadBundleSubtree(
            bundlePath,
            "proof/build-provenance/v1/");

        await fixture.PromoteAsync(bundlePath);

        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "startup-smoke", "stale.receipt.json")));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "proof", "stale", "proof.json")));
        Assert.True(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            "startup-smoke",
            "startup-smoke-avalonia-macos-arm64.receipt.json")));
        Assert.Equal(2, incomingGovernedProof.Count);
        foreach ((string relativePath, byte[] expectedBytes) in incomingGovernedProof)
        {
            Assert.Equal(
                expectedBytes,
                File.ReadAllBytes(Path.Combine(
                    fixture.DownloadsRoot,
                    relativePath.Replace('/', Path.DirectorySeparatorChar))));
        }

        using JsonDocument compatibility = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(fixture.DownloadsRoot, "releases.json")));
        using JsonDocument canonical = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json")));
        JsonElement compatibilityReadiness = compatibility.RootElement
            .GetProperty("releaseProof")
            .GetProperty("flagshipReadiness");
        JsonElement canonicalReadiness = canonical.RootElement
            .GetProperty("releaseProof")
            .GetProperty("flagshipReadiness");
        Assert.Equal(9, compatibilityReadiness.EnumerateObject().Count());
        Assert.True(JsonNode.DeepEquals(
            JsonNode.Parse(compatibilityReadiness.GetRawText()),
            JsonNode.Parse(canonicalReadiness.GetRawText())));
    }

    private static void AssertManagedShelfMatches(
        IReadOnlyDictionary<string, byte[]> expected,
        IReadOnlyDictionary<string, byte[]> actual)
    {
        Assert.Equal(
            expected.Keys.OrderBy(static key => key, StringComparer.Ordinal).ToArray(),
            actual.Keys.OrderBy(static key => key, StringComparer.Ordinal).ToArray());
        foreach ((string path, byte[] expectedBytes) in expected)
        {
            Assert.Equal(expectedBytes, actual[path]);
        }
    }

    private static IReadOnlyDictionary<string, byte[]> ReadBundleSubtree(string bundlePath, string prefix)
    {
        using ZipArchive archive = ZipFile.OpenRead(bundlePath);
        Dictionary<string, byte[]> files = new(StringComparer.Ordinal);
        foreach (ZipArchiveEntry entry in archive.Entries.Where(entry =>
                     entry.FullName.StartsWith(prefix, StringComparison.Ordinal)
                     && !string.IsNullOrEmpty(entry.Name)))
        {
            using Stream input = entry.Open();
            using MemoryStream output = new();
            input.CopyTo(output);
            files.Add(entry.FullName, output.ToArray());
        }
        return files;
    }

    [Fact]
    public async Task PromoteAsyncKeepsPublishedArtifactCountsAlignedWithRegistryBoundaryCoverage()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260525-204932",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-installer"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-installer",
                    Head: "blazor-desktop",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    Bytes: "mac-installer-blazor"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-archive",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "archive",
                    FileName: "chummer-avalonia-osx-arm64.zip",
                    Bytes: "mac-archive"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false),
                new BundleArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-archive",
                    Head: "blazor-desktop",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "archive",
                    FileName: "chummer-blazor-desktop-osx-arm64.zip",
                    Bytes: "mac-archive-blazor"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false)
            ],
            publishedAt: "2026-05-25T20:51:10Z",
            proofGeneratedAt: "2026-05-25T20:49:32Z");

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        using JsonDocument canonical = fixture.ReadCanonicalManifest();

        Assert.Equal(4, canonical.RootElement.GetProperty("artifacts").GetArrayLength());
        Assert.Equal(4, compatibility.RootElement.GetProperty("downloads").GetArrayLength());
        Assert.Equal(4, canonical.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("persistence").GetProperty("artifactCount").GetInt32());
        Assert.Equal(4, canonical.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("compatibility").GetProperty("compatibleArtifactCount").GetInt32());
    }

    [Fact]
    public async Task PromoteAsyncRejectsMacArtifactWithoutPromotionEvidence()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-220500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-live"u8.ToArray(),
                    RequiresSigning: true,
                    RequiresNotarization: true)
            ],
            includePromotionEvidence: false);

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() => fixture.PromoteAsync(bundlePath));
        Assert.Contains("public-promotion.json", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task PromoteAsyncAllowsUnsignedMacPreviewArtifactWhenEvidenceMarksSkippedPreview()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-221500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-221500", result.Version);
        Assert.Contains("avalonia-osx-arm64-dmg", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-osx-arm64-installer.dmg")));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "startup-smoke", "startup-smoke-avalonia-macos-arm64.receipt.json")));
    }

    [Fact]
    public async Task PromoteAsyncAllowsArtifactSha256ReceiptFieldAndPlatformAlias()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-223000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "osx",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview",
                    UseArtifactSha256ReceiptField: true,
                    ReceiptPlatformOverride: "darwin")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-223000", result.Version);
        Assert.Contains("avalonia-osx-arm64-dmg", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-osx-arm64-installer.dmg")));
    }

    [Fact]
    public async Task PromoteAsyncAllowsRidStylePlatformTokens()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-224000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview",
                    ReceiptPlatformOverride: "osx-arm64")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-224000", result.Version);
        Assert.Contains("avalonia-osx-arm64-dmg", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-osx-arm64-installer.dmg")));
    }

    [Fact]
    public async Task PromoteAsyncAllowsUnsignedWindowsPreviewArtifactWhenEvidenceMarksSkippedPreview()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-222500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-222500", result.Version);
        Assert.Contains("avalonia-win-x64-installer", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-win-x64-installer.exe")));
    }

    [Fact]
    public async Task PromoteAsyncAcceptsFullyBoundNativeWindowsStartupSmokeReceipt()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-native-windows-smoke",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "native-windows-smoke"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260717-native-windows-smoke", result.Version);
        Assert.Contains("avalonia-win-x64-installer", result.PromotedArtifactIds);
    }

    [Fact]
    public async Task PromoteAsyncAcceptsProducerReceiptWithChannelIdAndNoChannelAlias()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-channel-id-only-smoke",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "channel-id-only-smoke"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false)
            ]);
        fixture.RewriteOnlyStartupSmokeReceipt(
            bundlePath,
            receipt => receipt.Remove("channel"));

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260717-channel-id-only-smoke", result.Version);
    }

    [Theory]
    [InlineData("status", "fail", "status")]
    [InlineData("releaseVersion", "run-wrong", "releaseVersion")]
    [InlineData("version", "run-wrong", "version")]
    [InlineData("channel", "stable", "channel")]
    [InlineData("channelId", "stable", "channelId")]
    [InlineData("artifactId", "different-installer", "artifactId")]
    [InlineData("artifactFileName", "different.exe", "artifactFileName")]
    [InlineData("fileName", "different.exe", "fileName")]
    [InlineData("artifactPath", "/tmp/files/different.exe", "artifactPath")]
    [InlineData("artifactRelativePath", "files/different.exe", "artifactRelativePath")]
    [InlineData("rid", "win-arm64", "rid")]
    [InlineData("readyCheckpoint", "post_ui_event_loop", "readyCheckpoint")]
    [InlineData("hostClass", "local-linux-x64", "hostClass")]
    [InlineData("operatingSystem", "", "operatingSystem")]
    [InlineData("completedAtUtc", "not-a-timestamp", "completedAtUtc")]
    public async Task PromoteAsyncRejectsStartupSmokeReceiptContractDrift(
        string field,
        string replacement,
        string expectedErrorField)
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string fileName = "chummer-avalonia-win-x64-installer.exe";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-smoke-contract-drift",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: fileName,
                    Bytes: "smoke-contract-drift"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);
        fixture.RewriteOnlyStartupSmokeReceipt(
            bundlePath,
            receipt => receipt[field] = replacement);

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains(expectedErrorField, failure.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", fileName)));
    }

    [Fact]
    public async Task PromoteAsyncRejectsStaleStartupSmokeReceipt()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string publishedAt = "2026-07-17T12:00:00Z";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-stale-startup-smoke",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "stale-startup-smoke"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false)
            ],
            publishedAt: publishedAt,
            proofGeneratedAt: publishedAt);
        fixture.RewriteOnlyStartupSmokeReceipt(
            bundlePath,
            receipt =>
            {
                const string stale = "2026-07-10T11:59:59Z";
                receipt["startedAtUtc"] = stale;
                receipt["recordedAtUtc"] = stale;
                receipt["completedAtUtc"] = stale;
                receipt["sourceUpdatedAtUtc"] = stale;
            });

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("stale", failure.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task PromoteAsyncRejectsWineCompatibilityReceiptForCanonicalWindowsPromotion()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-wine-is-not-canonical",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "wine-compatibility"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);
        fixture.RewriteOnlyStartupSmokeReceipt(
            bundlePath,
            receipt =>
            {
                receipt["hostClass"] = "wine64-linux-x64-container";
                receipt["operatingSystem"] = "Microsoft Windows 10.0";
                receipt["executionEnvironment"] = "wine_compatibility";
                receipt["nativeHostEvidence"] = new JsonObject
                {
                    ["contractName"] = "chummer6-ui.native_windows_host_evidence",
                    ["status"] = "not_native",
                    ["isNativeWindows"] = false,
                    ["hostPlatform"] = "linux",
                    ["hostKernel"] = "Linux",
                    ["runner"] = "wine64",
                    ["evidenceSource"] = "wine_runner_selection"
                };
            });

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("native Windows startup smoke", failure.Message, StringComparison.Ordinal);
        Assert.Contains("compatibility execution is insufficient", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task PromoteAsyncAllowsExplicitUnsignedWindowsReleaseArtifactWhenEvidenceMarksUnsignedPublicRelease()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260618-142358",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-stable"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "unsigned_public_release",
                    StartupSmokeStatusOverride: "skipped_incompatible_host")
            ],
            channel: "stable",
            publicTrustMetrics: BuildProofFreshnessMetrics(
                DateTimeOffset.Parse("2026-04-01T20:00:00Z"),
                ageSeconds: 0,
                maxAgeSeconds: 604800));

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260618-142358", result.Version);
        Assert.Contains("avalonia-win-x64-installer", result.PromotedArtifactIds);
        Assert.Contains(
            $"https://chummer.run/downloads/g/{result.GenerationId}/install/avalonia-win-x64-installer",
            result.DirectFileUrls);
        Assert.DoesNotContain(
            "https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe",
            result.DirectFileUrls);
        Assert.DoesNotContain(result.DirectFileUrls, static url => url.Contains("https://chummer.run/https://", StringComparison.OrdinalIgnoreCase));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-win-x64-installer.exe")));
    }

    [Fact]
    public async Task PromoteAsyncCopiesWindowsProofPayloadWhenBundleProvidesIt()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260412-192500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            proofArtifacts:
            [
                new ProofArtifact(
                    RelativePath: "windows/chummer-avalonia-win-x64-installer.exe",
                    Bytes: "win-proof"u8.ToArray()),
                new ProofArtifact(
                    RelativePath: "windows/chummer-blazor-desktop-win-x64-installer.exe",
                    Bytes: "win-proof-blazor"u8.ToArray())
            ]);

        await fixture.PromoteAsync(bundlePath);

        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "proof", "windows", "chummer-avalonia-win-x64-installer.exe")));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "proof", "windows", "chummer-blazor-desktop-win-x64-installer.exe")));
    }

    [Fact]
    public async Task PromoteAsyncMakesPromotedMacPreviewVisibleOnDownloadsAsInstallCommand()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260409-061506",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-installer",
                    Head: "blazor-desktop",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    Bytes: "mac-preview-alt"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);

        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = fixture.DownloadsRoot,
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        PublicReleaseManifestDto manifest = new PublicReleaseManifestService(configuration).LoadManifest();
        ReleaseSelectionService selection = new(new PublicCanonFileLoader(configuration));

        ReleaseExperienceViewModel experience = selection.BuildExperience(
            manifest,
            userAgent: "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_4) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15 arm64",
            authenticated: true);

        Assert.Null(experience.Recommended);
        Assert.False(experience.RequestedPlatformHasPublicDownload);
        Assert.NotNull(experience.PlatformShelfNoticeTitle);
        Assert.Contains(experience.PlatformAvailability, item => item.PlatformId == "macos" && !item.PubliclyAvailable);
        Assert.DoesNotContain(experience.Alternatives, item => item.Artifact.Id == "blazor-desktop-osx-arm64-installer");
    }

    [Fact]
    public async Task PromoteAsyncKeepsFixedDesktopRequirementFloorForFirstShelfPartialPreview()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string macBundle = fixture.CreateBundle(
            version: "run-20260419-201110",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(macBundle);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement coverage = compatibility.RootElement.GetProperty("desktopTupleCoverage");
        Assert.False(coverage.GetProperty("complete").GetBoolean());
        string[] promotedTupleIds = coverage.GetProperty("promotedInstallerTuples")
            .EnumerateArray()
            .Select(item => item.GetProperty("tupleId").GetString()!)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToArray();
        Assert.Equal(["avalonia:macos:osx-arm64"], promotedTupleIds);
        Assert.Equal(
            ["linux", "windows", "macos"],
            coverage.GetProperty("requiredDesktopPlatforms")
                .EnumerateArray()
                .Select(item => item.GetString()!)
                .ToArray());
        Assert.Equal(
            ["avalonia"],
            coverage.GetProperty("requiredDesktopHeads")
                .EnumerateArray()
                .Select(item => item.GetString()!)
                .ToArray());
        Assert.Equal(
            ["avalonia:linux-x64:linux", "avalonia:osx-arm64:macos", "avalonia:win-x64:windows"],
            coverage.GetProperty("requiredDesktopPlatformHeadRidTuples")
                .EnumerateArray()
                .Select(item => item.GetString()!)
                .ToArray());
        Assert.Equal(
            ["linux", "windows"],
            coverage.GetProperty("missingRequiredPlatforms")
                .EnumerateArray()
                .Select(item => item.GetString()!)
                .ToArray());
        Assert.Equal(
            ["avalonia:linux-x64:linux", "avalonia:win-x64:windows"],
            coverage.GetProperty("missingRequiredPlatformHeadRidTuples")
                .EnumerateArray()
                .Select(item => item.GetString()!)
                .ToArray());
        Assert.Equal("coverage_incomplete", compatibility.RootElement.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", compatibility.RootElement.GetProperty("supportabilityState").GetString());
        Assert.Equal("coverage_incomplete", canonical.RootElement.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", canonical.RootElement.GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "review_required",
            canonical.RootElement.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.False(
            canonical.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("desktopTupleComplete").GetBoolean());
    }

    [Fact]
    public async Task PromoteAsyncFiltersExternalProofRequestsAgainstIncomingShelfCoverage()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string initialBundle = fixture.CreateBundle(
            version: "run-20260419-180000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "linux"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false)
            ]);
        await fixture.PromoteAsync(initialBundle);

        string macBundle = fixture.CreateBundle(
            version: "run-20260419-201110",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "linux-updated"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false),
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(macBundle);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        JsonElement coverage = compatibility.RootElement.GetProperty("desktopTupleCoverage");
        string[] promotedTupleIds = coverage.GetProperty("promotedInstallerTuples")
            .EnumerateArray()
            .Select(item => item.GetProperty("tupleId").GetString()!)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToArray();
        Assert.Equal(["avalonia:linux:linux-x64", "avalonia:macos:osx-arm64"], promotedTupleIds);
        Assert.Empty(coverage.GetProperty("externalProofRequests")
            .EnumerateArray()
            .ToArray());
    }

    [Fact]
    public async Task PromoteAsyncPreservesRegistryPromotedInstallerTupleTruth()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260502-214500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-route-truth"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement[] rows = canonical.RootElement
            .GetProperty("desktopTupleCoverage")
            .GetProperty("promotedInstallerTuples")
            .EnumerateArray()
            .ToArray();

        JsonElement row = Assert.Single(rows);
        Assert.Equal("avalonia-osx-arm64-installer", row.GetProperty("artifactId").GetString());
        Assert.Equal("avalonia:macos:osx-arm64", row.GetProperty("tupleId").GetString());
    }

    [Fact]
    public async Task PromoteAsyncPreservesRegistryStableDesktopFloorPosture()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260618-142358",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "linux-stable"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false),
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-stable"u8.ToArray(),
                    RequiresSigning: true,
                    RequiresNotarization: false),
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-stable"u8.ToArray(),
                    RequiresSigning: true,
                    RequiresNotarization: true)
            ],
            channel: "stable",
            publicTrustMetrics: BuildProofFreshnessMetrics(
                DateTimeOffset.Parse("2026-04-01T20:00:00Z"),
                ageSeconds: 0,
                maxAgeSeconds: 604800));

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement root = canonical.RootElement;
        Assert.Equal("public_stable", root.GetProperty("rolloutState").GetString());
        Assert.Equal("gold_supported", root.GetProperty("supportabilityState").GetString());
        Assert.True(root.GetProperty("desktopTupleCoverage").GetProperty("complete").GetBoolean());
        Assert.Equal(
            3,
            root.GetProperty("desktopTupleCoverage").GetProperty("promotedInstallerTuples").GetArrayLength());
        Assert.Equal(
            "live",
            root.GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("publicTrustPosture")
                .GetString());
    }

    [Fact]
    public async Task PromoteAsyncRejectsRegistryMetricsThatContradictRegistryPosture()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260705-181500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-installer",
                    Head: "blazor-desktop",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    Bytes: "mac-preview-alt"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            publicTrustMetrics: new
            {
                releaseChannel = new
                {
                    channelId = "preview",
                    posture = "preview",
                    publicationStatus = "published",
                    rolloutState = "promoted_preview",
                    supportabilityState = "preview_supported",
                    recommendedRouteCount = 0,
                    blockedRouteCount = 9,
                    revokedRouteCount = 4,
                    summary = "stale release-channel metrics"
                },
                adoptionHealth = new
                {
                    status = "limited",
                    primaryPromotedCount = 0,
                    publicInstallCount = 0,
                    accountLinkedInstallCount = 0,
                    fallbackRecoveryCount = 0,
                    blockedRouteCount = 9,
                    revokedRouteCount = 4,
                    summary = "stale adoption metrics"
                },
                proofFreshness = new
                {
                    status = "fresh",
                    releaseProofGeneratedAt = "2026-07-05T18:15:00Z",
                    releaseProofAgeSeconds = 0,
                    releaseProofMaxAgeSeconds = 600,
                    uiLocalizationGeneratedAt = "2026-07-05T18:15:00Z",
                    uiLocalizationAgeSeconds = 0,
                    uiLocalizationMaxAgeSeconds = 600,
                    summary = "fresh proof metrics"
                },
                revocationFacts = new
                {
                    status = "revoked",
                    channelRevoked = false,
                    activeRevocationCount = 4,
                    activeRevocations = new object[]
                    {
                        new
                        {
                            tupleId = "stale:tuple",
                            head = "avalonia",
                            platform = "macos",
                            rid = "osx-arm64",
                            artifactId = "stale-artifact",
                            revokeSource = "manual",
                            revokeReasonCode = "stale",
                            revokeReason = "stale revocation",
                            publicInstallRoute = "/downloads/install/stale-artifact",
                        }
                    },
                    summary = "stale revocation metrics"
                }
            });

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("supportabilityState", failure.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
    }

    [Fact]
    public async Task PromoteAsyncDoesNotInventAnInstallAwareRegistryProjection()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260522-201500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-install-aware"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        Assert.False(canonical.RootElement.TryGetProperty("installAwareArtifactRegistry", out _));
    }

    [Theory]
    [InlineData("stale")]
    [InlineData("missing")]
    [InlineData("")]
    [InlineData("future_status")]
    [InlineData(null)]
    public async Task PromoteAsyncFailsClosedUnlessEmbeddedFlagshipProofFreshnessIsExplicitlyFresh(
        string? proofFreshnessStatus)
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        object publicTrustMetrics = proofFreshnessStatus is null
            ? new
            {
                proofFreshness = new { status = (string?)null }
            }
            : new
            {
                proofFreshness = new
                {
                    status = proofFreshnessStatus,
                    releaseProofGeneratedAt = "2026-07-13T09:16:19Z",
                    releaseProofAgeSeconds = 8278,
                    releaseProofMaxAgeSeconds = 604800,
                    uiLocalizationGeneratedAt = "2026-07-13T11:34:14Z",
                    uiLocalizationAgeSeconds = 3,
                    uiLocalizationMaxAgeSeconds = 604800,
                    flagshipReadinessGeneratedAt = "2026-07-02T07:57:05Z",
                    flagshipReadinessAgeSeconds = 963432,
                    flagshipReadinessMaxAgeSeconds = 604800,
                    flagshipReadinessStatus = "pass",
                    flagshipDesktopClientReady = true,
                    summary = "Flagship readiness proof is stale."
                }
            };

        string bundlePath = fixture.CreateBundle(
            version: "run-20260713-113227",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "linux-stale-flagship-proof"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-stale-flagship-proof"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-stale-flagship-proof"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            publishedAt: "2026-07-13T11:34:17Z",
            proofGeneratedAt: "2026-07-13T09:16:19Z",
            publicTrustMetrics: publicTrustMetrics,
            seedReviewRequiredPosture: true);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        using JsonDocument generationCompatibility = fixture.ReadGenerationJson(result.GenerationId!, "releases.json");
        using JsonDocument generationCanonical = fixture.ReadGenerationJson(
            result.GenerationId!,
            "RELEASE_CHANNEL.generated.json");
        Assert.True(JsonElement.DeepEquals(compatibility.RootElement, generationCompatibility.RootElement));
        Assert.True(JsonElement.DeepEquals(canonical.RootElement, generationCanonical.RootElement));

        foreach (JsonElement root in new[]
                 {
                     compatibility.RootElement,
                     canonical.RootElement,
                     generationCompatibility.RootElement,
                     generationCanonical.RootElement
                 })
        {
            Assert.True(root.GetProperty("desktopTupleCoverage").GetProperty("complete").GetBoolean());
            Assert.Equal("public_release_review_required", root.GetProperty("rolloutState").GetString());
            Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
            foreach (string fieldName in new[]
                     {
                         "rolloutReason",
                         "supportabilitySummary",
                         "knownIssueSummary",
                         "fixAvailabilitySummary"
                     })
            {
                Assert.Contains(
                    "stale or incomplete proof receipts",
                    root.GetProperty(fieldName).GetString(),
                    StringComparison.OrdinalIgnoreCase);
            }
        }

        JsonElement metrics = canonical.RootElement.GetProperty("publicTrustMetrics");
        string expectedFreshnessStatus = string.IsNullOrWhiteSpace(proofFreshnessStatus)
            || string.Equals(proofFreshnessStatus, "missing", StringComparison.OrdinalIgnoreCase)
                ? "missing"
                : "stale";
        Assert.Equal(
            expectedFreshnessStatus,
            metrics.GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal(
            "review_required",
            metrics.GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "blocked",
            metrics.GetProperty("releaseChannel").GetProperty("posture").GetString());
        Assert.Equal(
            "review_required",
            canonical.RootElement
                .GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("supportabilityState")
                .GetString());
        Assert.Equal(
            "blocked",
            canonical.RootElement
                .GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("publicTrustPosture")
                .GetString());
        Assert.Equal("limited", metrics.GetProperty("adoptionHealth").GetProperty("status").GetString());
    }

    [Fact]
    public async Task PromoteAsyncKeepsFreshProofReviewGatedWhileHostedBuildPrivacyPolicyIsUnresolved()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        DateTimeOffset publishedAt = DateTimeOffset.Parse("2026-07-15T07:30:00Z");
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-privacy-review",
            artifacts: CompletePrimaryShelfArtifacts("privacy-review"),
            publishedAt: publishedAt.ToString("O"),
            proofGeneratedAt: publishedAt.ToString("O"),
            publicTrustMetrics: BuildProofFreshnessMetrics(
                publishedAt,
                ageSeconds: 0,
                maxAgeSeconds: ReleaseProofEvidenceTestData.MaximumAgeSeconds),
            privacyLaunchGate: PrivacyLaunchGate.Current);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(
            bundlePath,
            evaluationInstant: publishedAt,
            privacyLaunchGate: PrivacyLaunchGate.Current);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        using JsonDocument generationCompatibility = fixture.ReadGenerationJson(result.GenerationId!, "releases.json");
        using JsonDocument generationCanonical = fixture.ReadGenerationJson(
            result.GenerationId!,
            "RELEASE_CHANNEL.generated.json");
        Assert.True(JsonElement.DeepEquals(compatibility.RootElement, generationCompatibility.RootElement));
        Assert.True(JsonElement.DeepEquals(canonical.RootElement, generationCanonical.RootElement));
        foreach (JsonElement root in new[]
                 {
                     compatibility.RootElement,
                     canonical.RootElement,
                     generationCompatibility.RootElement,
                     generationCanonical.RootElement
                 })
        {
            Assert.Equal("public_release_review_required", root.GetProperty("rolloutState").GetString());
            Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
            Assert.Contains("Hosted Build", root.GetProperty("rolloutReason").GetString(), StringComparison.Ordinal);
        }

        JsonElement metrics = canonical.RootElement.GetProperty("publicTrustMetrics");
        Assert.Equal("fresh", metrics.GetProperty("proofFreshness").GetProperty("status").GetString());
        JsonElement privacyReadiness = metrics.GetProperty("privacyReadiness");
        Assert.Equal(PrivacyLaunchGate.ContractName, privacyReadiness.GetProperty("contractName").GetString());
        Assert.Equal(PrivacyLaunchGate.ContractVersion, privacyReadiness.GetProperty("contractVersion").GetInt32());
        Assert.Equal("review_required", privacyReadiness.GetProperty("status").GetString());
        Assert.True(privacyReadiness.GetProperty("reviewRequired").GetBoolean());
        Assert.Contains(
            "public_release_supportability",
            privacyReadiness.GetProperty("blockedClaims").EnumerateArray().Select(static item => item.GetString()));
        Assert.Equal(
            "blocked",
            metrics.GetProperty("releaseChannel").GetProperty("posture").GetString());
        Assert.Equal("limited", metrics.GetProperty("adoptionHealth").GetProperty("status").GetString());
        Assert.Equal(
            "blocked",
            canonical.RootElement
                .GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("publicTrustPosture")
                .GetString());
        Assert.True(JsonElement.DeepEquals(
            compatibility.RootElement.GetProperty("publicTrustMetrics").GetProperty("privacyReadiness"),
            privacyReadiness));
    }

    [Fact]
    public async Task PromoteAsyncRejectsPassedReleaseProofThatPredatesCurrentPublicationWindow()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260501-040136",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            publishedAt: "2026-05-01T04:01:36Z",
            proofGeneratedAt: "2026-04-25T22:43:00Z");

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("publication window", failure.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
    }

    [Fact]
    public async Task PromoteAsyncRejectsPassedReleaseProofThatIsTooFarAfterPublication()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260501-040136-future-proof",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-future-proof"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            publishedAt: "2026-05-01T04:01:36Z",
            proofGeneratedAt: "2026-05-01T05:01:36Z");

        InvalidDataException failure = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("publication window", failure.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
    }

    [Theory]
    [InlineData("bare", "missing", 0)]
    [InlineData("inconsistent", "stale", 0)]
    [InlineData("exact_max_age", "fresh", 604800)]
    [InlineData("expired_at_commit", "stale", 604801)]
    [InlineData("exact_future_skew", "fresh", 0)]
    [InlineData("future_skew_exceeded", "stale", 0)]
    public async Task PromoteAsyncPreservesRegistryEvaluatedFreshnessFactsAtCommitInstant(
        string scenario,
        string expectedFreshnessStatus,
        int evaluationOffsetSeconds)
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        DateTimeOffset publishedAt = DateTimeOffset.Parse("2026-07-14T04:11:58Z");
        DateTimeOffset generatedAt = scenario switch
        {
            "exact_max_age" or "expired_at_commit" => publishedAt,
            "exact_future_skew" => publishedAt.AddMinutes(5),
            "future_skew_exceeded" => publishedAt.AddMinutes(5).AddSeconds(1),
            _ => publishedAt
        };
        long ageSeconds = 0;
        Dictionary<string, object?> publicTrustMetrics = scenario == "bare"
            ? new Dictionary<string, object?>
            {
                ["proofFreshness"] = new JsonObject { ["status"] = expectedFreshnessStatus }
            }
            : BuildProofFreshnessMetrics(
                generatedAt,
                scenario == "inconsistent" ? ageSeconds + 1 : ageSeconds,
                maxAgeSeconds: ReleaseProofEvidenceTestData.MaximumAgeSeconds);
        if (publicTrustMetrics["proofFreshness"] is JsonObject proofFreshness)
        {
            proofFreshness["status"] = expectedFreshnessStatus;
        }

        string bundlePath = fixture.CreateBundle(
            version: $"run-20260714-{scenario}",
            artifacts: CompletePrimaryShelfArtifacts(scenario),
            publishedAt: publishedAt.ToString("O"),
            proofGeneratedAt: generatedAt.ToString("O"),
            publicTrustMetrics: publicTrustMetrics,
            seedReviewRequiredPosture: expectedFreshnessStatus != "fresh",
            startupSmokeRecordedAt: publishedAt.AddSeconds(evaluationOffsetSeconds).ToString("O"));

        await fixture.PromoteAsync(
            bundlePath,
            evaluationInstant: publishedAt.AddSeconds(evaluationOffsetSeconds));

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        Assert.Equal(
            expectedFreshnessStatus,
            canonical.RootElement.GetProperty("publicTrustMetrics").GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal(
            expectedFreshnessStatus == "fresh" ? "preview_supported" : "review_required",
            canonical.RootElement.GetProperty("supportabilityState").GetString());
    }

    private static Dictionary<string, object?> BuildProofFreshnessMetrics(
        DateTimeOffset generatedAt,
        long ageSeconds,
        long maxAgeSeconds)
    {
        JsonObject proof = ReleaseProofEvidenceTestData.CreateReleaseProof(generatedAt);
        JsonObject facts = ReleaseProofEvidenceTestData.CreateFreshnessFacts(
            proof,
            generatedAt.AddSeconds(ageSeconds),
            declaredAgeSeconds: ageSeconds,
            maxAgeSeconds: maxAgeSeconds);
        return new Dictionary<string, object?> { ["proofFreshness"] = facts };
    }

    private static BundleArtifact[] CompletePrimaryShelfArtifacts(string marker)
        =>
        [
            new BundleArtifact(
                "avalonia-linux-x64-installer",
                "avalonia",
                "linux",
                "x64",
                "installer",
                "chummer-avalonia-linux-x64-installer.deb",
                System.Text.Encoding.UTF8.GetBytes($"linux-{marker}"),
                RequiresSigning: false,
                RequiresNotarization: false),
            new BundleArtifact(
                "avalonia-win-x64-installer",
                "avalonia",
                "windows",
                "x64",
                "installer",
                "chummer-avalonia-win-x64-installer.exe",
                System.Text.Encoding.UTF8.GetBytes($"windows-{marker}"),
                RequiresSigning: false,
                RequiresNotarization: false,
                SigningStatusOverride: "skipped_preview"),
            new BundleArtifact(
                "avalonia-osx-arm64-installer",
                "avalonia",
                "macos",
                "arm64",
                "dmg",
                "chummer-avalonia-osx-arm64-installer.dmg",
                System.Text.Encoding.UTF8.GetBytes($"mac-{marker}"),
                RequiresSigning: false,
                RequiresNotarization: false,
                SigningStatusOverride: "skipped_preview",
                NotarizationStatusOverride: "skipped_preview")
        ];

    [Fact]
    public async Task PromoteAsyncNormalizesExistingCanonicalArtifactsToIncomingChannelAndVersion()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-osx-arm64-installer",
            fileName: "chummer-avalonia-osx-arm64-installer.dmg",
            platform: "macos",
            arch: "arm64",
            kind: "dmg",
            bytes: "mac-live");
        fixture.SetCanonicalMetadata(
            channelId: "public_stable",
            version: "run-20260401-200000");

        string bundlePath = fixture.CreateBundle(
            version: "run-20260420-090000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);
        using JsonDocument canonical = fixture.ReadCanonicalManifest();

        foreach (JsonElement artifact in canonical.RootElement.GetProperty("artifacts").EnumerateArray())
        {
            Assert.Equal("preview", artifact.GetProperty("channel").GetString());
            Assert.Equal("preview", artifact.GetProperty("channelId").GetString());
            Assert.Equal("run-20260420-090000", artifact.GetProperty("version").GetString());
            Assert.Equal("run-20260420-090000", artifact.GetProperty("releaseVersion").GetString());
        }
    }

    [Theory]
    [InlineData("version", "disagree about version")]
    [InlineData("channel", "disagree about channel")]
    [InlineData("channelId", "channel and channelId disagree")]
    [InlineData("status", "disagree about status")]
    [InlineData("publishedAt", "disagree about publishedAt")]
    [InlineData("releaseProofStatus", "disagree about normalized releaseProof.status")]
    [InlineData("releaseProofEvidence", "semantically identical releaseProof evidence")]
    public async Task PromoteAsyncRejectsCrossManifestIdentityAndProofStatusDrift(
        string mismatch,
        string expectedMessage)
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260714-cross-manifest",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-cross-manifest"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ],
            publishedAt: "2026-07-14T04:11:58Z",
            proofGeneratedAt: "2026-07-14T04:11:58Z");

        fixture.RewriteBundleManifest(
            bundlePath,
            "RELEASE_CHANNEL.generated.json",
            canonical =>
            {
                switch (mismatch)
                {
                    case "version":
                        canonical["version"] = "run-contradictory-version";
                        break;
                    case "channel":
                        canonical["channel"] = "stable";
                        canonical["channelId"] = "stable";
                        break;
                    case "channelId":
                        canonical["channelId"] = "stable";
                        break;
                    case "status":
                        canonical["status"] = "revoked";
                        break;
                    case "publishedAt":
                        canonical["publishedAt"] = "2026-07-14T04:12:00Z";
                        break;
                    case "releaseProofStatus":
                        canonical["releaseProof"]!["status"] = "review_required";
                        break;
                    case "releaseProofEvidence":
                        canonical["releaseProof"]!["flagshipReadiness"]!["reason"] =
                            "Canonical evidence was changed after the compatibility manifest was written.";
                        break;
                    default:
                        throw new InvalidOperationException($"Unknown mismatch {mismatch}.");
                }
            });

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains(expectedMessage, error.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json")));
    }

    [Fact]
    public async Task PromoteAsyncRejectsBundleWhenBothManifestsOmitReleaseProof()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260714-missing-release-proof",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-missing-proof"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        fixture.RewriteBundleManifest(bundlePath, "releases.json", manifest => manifest.Remove("releaseProof"));
        fixture.RewriteBundleManifest(
            bundlePath,
            "RELEASE_CHANNEL.generated.json",
            manifest => manifest.Remove("releaseProof"));

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));

        Assert.Contains("must contain semantically identical releaseProof evidence", error.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json")));
    }

    [Fact]
    public async Task PromotionRewritesPayloadSidecarToExactImmutableGenerationRoute()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-payload-sidecar",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-installer"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    InstallerMode: "bootstrap_payload",
                    PayloadFileName: "chummer-avalonia-win-x64-payload.zip",
                    PayloadBytes: "windows-payload"u8.ToArray())
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);
        string expectedUrl =
            $"/downloads/g/{result.GenerationId}/install/avalonia-win-x64-installer/payload";
        using JsonDocument sidecar = fixture.ReadGenerationJson(
            result.GenerationId!,
            "files/chummer-avalonia-win-x64-payload.zip.json");
        Assert.Equal(expectedUrl, sidecar.RootElement.GetProperty("downloadUrl").GetString());
        using JsonDocument compatibility = fixture.ReadGenerationJson(result.GenerationId!, "releases.json");
        Assert.Equal(
            "/downloads/files/chummer-avalonia-win-x64-payload.zip",
            compatibility.RootElement.GetProperty("downloads")[0].GetProperty("payloadDownloadUrl").GetString());
        using JsonDocument canonical = fixture.ReadGenerationJson(
            result.GenerationId!,
            "RELEASE_CHANNEL.generated.json");
        Assert.Equal(
            "/downloads/files/chummer-avalonia-win-x64-payload.zip",
            canonical.RootElement.GetProperty("artifacts")[0].GetProperty("payloadDownloadUrl").GetString());
    }

    [Theory]
    [InlineData("unknown_property")]
    [InlineData("duplicate_property")]
    [InlineData("wrong_digest")]
    [InlineData("wrong_version")]
    [InlineData("wrong_url")]
    public async Task PromotionRejectsNoncanonicalPayloadSidecarBeforeActivation(string mutation)
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        const string payloadFileName = "chummer-avalonia-win-x64-payload.zip";
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-invalid-payload-sidecar",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-installer"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    InstallerMode: "bootstrap_payload",
                    PayloadFileName: payloadFileName,
                    PayloadBytes: "windows-payload"u8.ToArray())
            ]);

        byte[] original = fixture.ReadBundleEntry(bundlePath, $"files/{payloadFileName}.json");
        JsonObject sidecar = JsonNode.Parse(original)!.AsObject();
        byte[] replacement = mutation switch
        {
            "unknown_property" => Encoding.UTF8.GetBytes(
                sidecar.ToJsonString(TestJsonOptions).TrimEnd('}') + ",\"unexpected\":true}"),
            "duplicate_property" => Encoding.UTF8.GetBytes(
                sidecar.ToJsonString(TestJsonOptions).TrimEnd('}')
                + $",\"sha256\":\"{sidecar["sha256"]!.GetValue<string>()}\"}}"),
            "wrong_digest" => Encoding.UTF8.GetBytes(
                MutateSidecar(sidecar, "sha256", new string('0', 64))),
            "wrong_version" => Encoding.UTF8.GetBytes(
                MutateSidecar(sidecar, "releaseVersion", "run-other")),
            "wrong_url" => Encoding.UTF8.GetBytes(
                MutateSidecar(
                    sidecar,
                    "downloadUrl",
                    "/downloads/g/forged-generation/install/avalonia-win-x64-installer/payload")),
            _ => throw new InvalidOperationException("unknown payload sidecar mutation")
        };
        fixture.ReplaceBundleEntry(bundlePath, $"files/{payloadFileName}.json", replacement);

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.PromoteAsync(bundlePath));
        Assert.Contains("payload metadata", error.Message, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
    }

    [Fact]
    public async Task PreparedGenerationUsesIncomingAuthoritativeShelfInsteadOfRetainingInvalidObsoleteArtifact()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "legacy-support-archive",
            fileName: "legacy-support.tar.gz",
            platform: "linux",
            arch: "x64",
            kind: "archive",
            bytes: "legacy-support");
        fixture.MutateLiveJson(
            "RELEASE_CHANNEL.generated.json",
            root => root["artifacts"]![0]!["sha256"] = new string('0', 64));
        string bundlePath = fixture.CreateBundle(
            version: "run-20260715-full-prepared-validation",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-installer"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.False(string.IsNullOrWhiteSpace(result.GenerationId));
        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement artifact = Assert.Single(canonical.RootElement.GetProperty("artifacts").EnumerateArray());
        Assert.Equal("avalonia-win-x64-installer", artifact.GetProperty("artifactId").GetString());
        Assert.DoesNotContain(
            canonical.RootElement.GetProperty("artifacts").EnumerateArray(),
            static row => string.Equals(
                row.GetProperty("artifactId").GetString(),
                "legacy-support-archive",
                StringComparison.Ordinal));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
    }

    private static string MutateSidecar(JsonObject sidecar, string property, string value)
    {
        sidecar[property] = value;
        return sidecar.ToJsonString(TestJsonOptions);
    }

    internal sealed class ReleaseBundlePromotionFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _downloadsRoot;

        public ReleaseBundlePromotionFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "release-bundle-promotion-tests", Guid.NewGuid().ToString("N"));
            _downloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(Path.Combine(_downloadsRoot, "files"));
        }

        public string DownloadsRoot => _downloadsRoot;

        public async Task<ReleaseBundlePromotionResult> PromoteAsync(
            string bundlePath,
            Action<ReleaseBundlePromotionService.PromotionCheckpoint>? promotionCheckpoint = null,
            CancellationToken cancellationToken = default,
            DateTimeOffset? evaluationInstant = null,
            PrivacyLaunchGateSnapshot? privacyLaunchGate = null)
        {
            IConfiguration configuration = CreateConfiguration();

            var service = new ReleaseBundlePromotionService(
                configuration,
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint,
                new FixedTimeProvider(evaluationInstant ?? ReadBundlePublishedAt(bundlePath)),
                privacyLaunchGate ?? PrivacyLaunchGate.ClearForTests);

            await using FileStream stream = File.OpenRead(bundlePath);
            return await service.PromoteAsync(Path.GetFileName(bundlePath), stream, cancellationToken);
        }

        public async Task<ReleaseBundlePromotionResult> PromoteDirectoryWithActivationCallbackAsync(
            string bundlePath,
            Action<ReleaseActivationIntent> activationCallback,
            Action<string>? postActivationDirectoryFlush = null,
            Action<ReleaseBundlePromotionService.ActivationJournalCheckpoint>? activationJournalCheckpoint = null,
            Action<ReleaseBundlePromotionService.PromotionCheckpoint>? promotionCheckpoint = null)
        {
            string extractRoot = Path.Combine(_root, "activation-" + Guid.NewGuid().ToString("N"));
            ZipFile.ExtractToDirectory(bundlePath, extractRoot);
            var service = new ReleaseBundlePromotionService(
                CreateConfiguration(),
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint,
                new FixedTimeProvider(ReadBundlePublishedAt(bundlePath)),
                PrivacyLaunchGate.ClearForTests,
                postActivationDirectoryFlush,
                activationJournalCheckpoint);
            return await service.PromoteDirectoryAsync(
                extractRoot,
                activationCallback,
                CancellationToken.None);
        }

        public bool TryReconcileActivation(
            ReleaseActivationIntent intent,
            out ReleaseBundlePromotionResult? result)
        {
            var service = new ReleaseBundlePromotionService(
                CreateConfiguration(),
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null,
                new FixedTimeProvider(DateTimeOffset.Parse("2026-07-15T23:59:59Z")),
                PrivacyLaunchGate.ClearForTests);
            return service.TryReconcileActivation(intent, out result);
        }

        public void AcknowledgeActivationCompletion(ReleaseActivationIntent intent)
        {
            var service = new ReleaseBundlePromotionService(
                CreateConfiguration(),
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null,
                new FixedTimeProvider(DateTimeOffset.Parse("2026-07-15T23:59:59Z")),
                PrivacyLaunchGate.ClearForTests);
            service.AcknowledgeActivationCompletion(intent);
        }

        public string ActivationJournalReceiptRoot(string activationReceiptId)
            => Path.Combine(
                _downloadsRoot,
                ".release-shelf-activation-journal",
                activationReceiptId);

        public ReleaseShelfPublicationReadinessProbeResult EvaluateActivationReadiness()
        {
            var service = new ReleaseBundlePromotionService(
                CreateConfiguration(),
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null,
                new FixedTimeProvider(DateTimeOffset.Parse("2026-07-15T23:59:59Z")),
                PrivacyLaunchGate.ClearForTests);
            return service.EvaluateActivationProtocolReadiness(
                CaptureActiveShelf(),
                CancellationToken.None);
        }

        public ReleaseShelfSnapshot CaptureActiveShelf()
            => new ReleaseShelfGenerationStore(CreateConfiguration()).Capture();

        public async Task ValidateBundleAsync(string bundlePath)
        {
            string extractRoot = Path.Combine(_root, "validate-" + Guid.NewGuid().ToString("N"));
            ZipFile.ExtractToDirectory(bundlePath, extractRoot);
            var service = new ReleaseBundlePromotionService(
                CreateConfiguration(),
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null,
                new FixedTimeProvider(ReadBundlePublishedAt(bundlePath)),
                PrivacyLaunchGate.ClearForTests);
            await service.ValidateDirectoryAsync(extractRoot, CancellationToken.None);
        }

        public Task<ReleaseBundlePromotionResult> RollbackAsync(string generationId)
        {
            var service = new ReleaseBundlePromotionService(
                CreateConfiguration(),
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null,
                new FixedTimeProvider(DateTimeOffset.Parse("2026-07-15T23:59:59Z")),
                PrivacyLaunchGate.ClearForTests);
            return service.RollbackToGenerationAsync(generationId, CancellationToken.None);
        }

        private IConfiguration CreateConfiguration(bool initialMigrationAllowed = false)
            => new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback",
                    ["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = initialMigrationAllowed.ToString()
                })
                .Build();

        public void ExtractBundleAsLegacyShelf(string bundlePath)
            => ZipFile.ExtractToDirectory(bundlePath, _downloadsRoot, overwriteFiles: true);

        public Task<ReleaseBundlePromotionResult?> EnsureInitialLegacyMigrationAsync()
        {
            var service = new ReleaseBundlePromotionService(
                CreateConfiguration(initialMigrationAllowed: true),
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null,
                new FixedTimeProvider(DateTimeOffset.Parse("2026-07-17T20:00:00Z")),
                PrivacyLaunchGate.ClearForTests);
            return service.EnsureInitialLegacyMigrationAsync(CancellationToken.None);
        }

        public byte[] ReadGenerationBytes(string generationId, string relativePath)
            => File.ReadAllBytes(Path.Combine(
                _downloadsRoot,
                "generations",
                generationId,
                relativePath.Replace('/', Path.DirectorySeparatorChar)));

        private static DateTimeOffset ReadBundlePublishedAt(string bundlePath)
        {
            using ZipArchive archive = ZipFile.OpenRead(bundlePath);
            ZipArchiveEntry manifestEntry = archive.Entries.Single(entry =>
                string.Equals(entry.FullName, "releases.json", StringComparison.Ordinal));
            using Stream stream = manifestEntry.Open();
            using JsonDocument manifest = JsonDocument.Parse(stream);
            return manifest.RootElement.GetProperty("publishedAt").GetDateTimeOffset();
        }

        private sealed class FixedTimeProvider(DateTimeOffset utcNow) : TimeProvider
        {
            public override DateTimeOffset GetUtcNow() => utcNow;
        }

        public void RewriteBundleManifest(
            string bundlePath,
            string manifestName,
            Action<JsonObject> rewrite)
        {
            using ZipArchive archive = ZipFile.Open(bundlePath, ZipArchiveMode.Update);
            ZipArchiveEntry entry = archive.Entries.Single(candidate =>
                string.Equals(candidate.FullName, manifestName, StringComparison.Ordinal));
            string json;
            using (StreamReader reader = new(entry.Open()))
            {
                json = reader.ReadToEnd();
            }

            JsonObject manifest = JsonNode.Parse(json)?.AsObject()
                ?? throw new InvalidDataException($"Expected {manifestName} to contain a JSON object.");
            rewrite(manifest);
            entry.Delete();
            ZipArchiveEntry replacement = archive.CreateEntry(manifestName);
            using StreamWriter writer = new(replacement.Open());
            writer.Write(manifest.ToJsonString(TestJsonOptions));
        }

        public void RewriteOnlyStartupSmokeReceipt(
            string bundlePath,
            Action<JsonObject> rewrite)
        {
            using ZipArchive archive = ZipFile.Open(bundlePath, ZipArchiveMode.Update);
            ZipArchiveEntry entry = archive.Entries.Single(candidate =>
                candidate.FullName.StartsWith("startup-smoke/startup-smoke-", StringComparison.Ordinal)
                && candidate.FullName.EndsWith(".receipt.json", StringComparison.Ordinal));
            string json;
            using (StreamReader reader = new(entry.Open()))
            {
                json = reader.ReadToEnd();
            }

            JsonObject receipt = JsonNode.Parse(json)?.AsObject()
                ?? throw new InvalidDataException("Expected startup smoke receipt to contain a JSON object.");
            rewrite(receipt);
            string relativePath = entry.FullName;
            entry.Delete();
            ZipArchiveEntry replacement = archive.CreateEntry(relativePath);
            using StreamWriter writer = new(replacement.Open());
            writer.Write(receipt.ToJsonString(TestJsonOptions));
        }

        public void DeleteBundleEntries(string bundlePath, Func<string, bool> predicate)
        {
            using ZipArchive archive = ZipFile.Open(bundlePath, ZipArchiveMode.Update);
            foreach (ZipArchiveEntry entry in archive.Entries
                         .Where(entry => predicate(entry.FullName))
                         .ToArray())
            {
                entry.Delete();
            }
        }

        public void AddBundleEntry(string bundlePath, string relativePath, byte[] bytes)
        {
            using ZipArchive archive = ZipFile.Open(bundlePath, ZipArchiveMode.Update);
            ZipArchiveEntry entry = archive.CreateEntry(relativePath);
            using Stream stream = entry.Open();
            stream.Write(bytes);
        }

        public byte[] ReadBundleEntry(string bundlePath, string relativePath)
        {
            using ZipArchive archive = ZipFile.OpenRead(bundlePath);
            ZipArchiveEntry entry = archive.GetEntry(relativePath)
                ?? throw new InvalidDataException($"bundle entry is missing: {relativePath}");
            using Stream stream = entry.Open();
            using var memory = new MemoryStream();
            stream.CopyTo(memory);
            return memory.ToArray();
        }

        public void ReplaceBundleEntry(string bundlePath, string relativePath, byte[] bytes)
        {
            DeleteBundleEntries(bundlePath, path => string.Equals(path, relativePath, StringComparison.Ordinal));
            AddBundleEntry(bundlePath, relativePath, bytes);
        }

        public JsonDocument ReadGenerationJson(string generationId, string relativePath)
            => JsonDocument.Parse(File.ReadAllBytes(Path.Combine(
                _downloadsRoot,
                "generations",
                generationId,
                relativePath.Replace('/', Path.DirectorySeparatorChar))));

        public void WriteManagedShelfFile(string relativePath, string contents)
        {
            string path = Path.Combine(_downloadsRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, contents);
        }

        public void MutateGenerationJson(
            string generationId,
            string relativePath,
            Action<JsonNode> mutation)
        {
            string path = Path.Combine(
                _downloadsRoot,
                "generations",
                generationId,
                relativePath.Replace('/', Path.DirectorySeparatorChar));
            if (OperatingSystem.IsWindows())
            {
                File.SetAttributes(path, File.GetAttributes(path) & ~FileAttributes.ReadOnly);
            }
            else
            {
                File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            }

            JsonNode root = JsonNode.Parse(File.ReadAllText(path))
                ?? throw new InvalidDataException("generation JSON fixture is malformed.");
            mutation(root);
            File.WriteAllText(path, root.ToJsonString(TestJsonOptions));
        }

        public void MutateLiveJson(string relativePath, Action<JsonNode> mutation)
        {
            string path = Path.Combine(
                _downloadsRoot,
                relativePath.Replace('/', Path.DirectorySeparatorChar));
            JsonNode root = JsonNode.Parse(File.ReadAllText(path))
                ?? throw new InvalidDataException("live JSON fixture is malformed.");
            mutation(root);
            File.WriteAllText(path, root.ToJsonString(TestJsonOptions));
        }

        public IReadOnlyDictionary<string, byte[]> SnapshotManagedShelf()
        {
            string[] managedEntries = ["files", "startup-smoke", "signing", "proof", "releases.json", "RELEASE_CHANNEL.generated.json"];
            Dictionary<string, byte[]> snapshot = new(StringComparer.Ordinal);
            foreach (string managedEntry in managedEntries)
            {
                string path = Path.Combine(_downloadsRoot, managedEntry);
                if (File.Exists(path))
                {
                    snapshot[managedEntry] = File.ReadAllBytes(path);
                    continue;
                }

                if (!Directory.Exists(path))
                {
                    continue;
                }

                foreach (string filePath in Directory.GetFiles(path, "*", SearchOption.AllDirectories))
                {
                    string relativePath = Path.GetRelativePath(_downloadsRoot, filePath)
                        .Replace(Path.DirectorySeparatorChar, '/');
                    snapshot[relativePath] = File.ReadAllBytes(filePath);
                }
            }

            return snapshot;
        }

        public IReadOnlyList<string> FindPromotionTransactionDirectories()
            => Directory.GetDirectories(_downloadsRoot, ".release-promotion-transaction-*", SearchOption.TopDirectoryOnly);

        public IReadOnlyList<string> FindGenerationDirectories()
        {
            string generationsRoot = Path.Combine(_downloadsRoot, "generations");
            return Directory.Exists(generationsRoot)
                ? Directory.GetDirectories(generationsRoot, "*", SearchOption.TopDirectoryOnly)
                : [];
        }

        public void WriteLiveArtifact(
            string artifactId,
            string fileName,
            string platform,
            string arch,
            string kind,
            string bytes)
        {
            string path = Path.Combine(_downloadsRoot, "files", fileName);
            File.WriteAllText(path, bytes);
            string sha = Sha256For(path);
            long size = new FileInfo(path).Length;

            WriteCompatibilityManifest(
                Path.Combine(_downloadsRoot, "releases.json"),
                version: "run-20260401-200000",
                downloads:
                [
                    new CompatibilityArtifact(
                        Id: artifactId,
                        Platform: platform,
                        Url: $"/downloads/files/{fileName}",
                        Sha256: sha,
                        SizeBytes: size,
                        Head: "avalonia",
                        PlatformId: $"{platform}-{arch}",
                        Rid: ArtifactRid(platform, arch),
                        Arch: arch,
                        Kind: kind,
                        FileName: fileName,
                        InstallAccessClass: "account_required")
                ]);

            WriteCanonicalManifest(
                Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json"),
                version: "run-20260401-200000",
                artifacts:
                [
                    new CanonicalArtifact(
                        ArtifactId: artifactId,
                        Head: "avalonia",
                        Rid: ArtifactRid(platform, arch),
                        Platform: platform,
                        Arch: arch,
                        Kind: kind,
                        FileName: fileName,
                        DownloadUrl: $"/downloads/files/{fileName}",
                        Sha256: sha,
                        SizeBytes: size,
                        PlatformLabel: $"Avalonia Desktop {platform} {arch}",
                        InstallAccessClass: "account_required")
                ]);
        }

        public void AppendLiveArtifact(
            string artifactId,
            string fileName,
            string platform,
            string arch,
            string kind,
            string bytes,
            string head = "avalonia")
        {
            string path = Path.Combine(_downloadsRoot, "files", fileName);
            File.WriteAllText(path, bytes);
            string sha = Sha256For(path);
            long size = new FileInfo(path).Length;

            string compatibilityPath = Path.Combine(_downloadsRoot, "releases.json");
            JsonObject compatibility = JsonNode.Parse(File.ReadAllText(compatibilityPath))!.AsObject();
            JsonArray downloads = compatibility["downloads"]!.AsArray();
            downloads.Add(JsonSerializer.SerializeToNode(new CompatibilityArtifact(
                Id: artifactId,
                Platform: $"Avalonia Desktop {platform} {arch}",
                Url: $"/downloads/files/{fileName}",
                Sha256: sha,
                SizeBytes: size,
                Head: head,
                PlatformId: $"{platform}-{arch}",
                Rid: ArtifactRid(platform, arch),
                Arch: arch,
                Kind: kind,
                FileName: fileName,
                InstallAccessClass: "account_required"), TestJsonOptions));
            File.WriteAllText(compatibilityPath, compatibility.ToJsonString(TestJsonOptions));

            string canonicalPath = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
            JsonObject canonical = JsonNode.Parse(File.ReadAllText(canonicalPath))!.AsObject();
            JsonArray artifacts = canonical["artifacts"]!.AsArray();
            artifacts.Add(JsonSerializer.SerializeToNode(new CanonicalArtifact(
                ArtifactId: artifactId,
                Head: head,
                Rid: ArtifactRid(platform, arch),
                Platform: platform,
                Arch: arch,
                Kind: kind,
                FileName: fileName,
                DownloadUrl: $"/downloads/files/{fileName}",
                Sha256: sha,
                SizeBytes: size,
                PlatformLabel: $"Avalonia Desktop {platform} {arch}",
                InstallAccessClass: "account_required"), TestJsonOptions));
            File.WriteAllText(canonicalPath, canonical.ToJsonString(TestJsonOptions));
        }

        public string CreateBundle(
            string version,
            IReadOnlyList<BundleArtifact> artifacts,
            bool includePromotionEvidence = true,
            IReadOnlyList<ProofArtifact>? proofArtifacts = null,
            string publishedAt = "2026-04-01T20:00:00Z",
            string proofGeneratedAt = "2026-04-01T20:00:00Z",
            string channel = "preview",
            object? publicTrustMetrics = null,
            bool seedReviewRequiredPosture = false,
            bool includeBuildProvenance = true,
            string? startupSmokeRecordedAt = null,
            PrivacyLaunchGateSnapshot? privacyLaunchGate = null)
        {
            string bundleRoot = Path.Combine(_root, "bundle-" + Guid.NewGuid().ToString("N"));
            string filesRoot = Path.Combine(bundleRoot, "files");
            string smokeRoot = Path.Combine(bundleRoot, "startup-smoke");
            string evidenceRoot = Path.Combine(bundleRoot, "release-evidence");
            Directory.CreateDirectory(filesRoot);
            Directory.CreateDirectory(smokeRoot);
            Directory.CreateDirectory(evidenceRoot);
            string smokeTimestamp = startupSmokeRecordedAt ?? publishedAt;

            List<CompatibilityArtifact> compatibilityArtifacts = new(artifacts.Count);
            List<CanonicalArtifact> canonicalArtifacts = new(artifacts.Count);
            List<PromotionEvidenceArtifact> evidenceArtifacts = new(artifacts.Count);

            foreach (BundleArtifact artifact in artifacts)
            {
                string filePath = Path.Combine(filesRoot, artifact.FileName);
                File.WriteAllBytes(filePath, artifact.Bytes);
                string sha = Sha256For(filePath);
                long size = new FileInfo(filePath).Length;
                string downloadUrl = $"/downloads/files/{artifact.FileName}";
                string? payloadSha = null;
                long? payloadSize = null;
                string? payloadDownloadUrl = null;
                if (!string.IsNullOrWhiteSpace(artifact.PayloadFileName))
                {
                    if (artifact.PayloadBytes is null)
                    {
                        throw new InvalidOperationException("payload bytes are required when payloadFileName is set.");
                    }

                    string payloadPath = Path.Combine(filesRoot, artifact.PayloadFileName);
                    File.WriteAllBytes(payloadPath, artifact.PayloadBytes);
                    payloadSha = Sha256For(payloadPath);
                    payloadSize = artifact.PayloadBytes.LongLength;
                    payloadDownloadUrl = $"/downloads/files/{artifact.PayloadFileName}";
                    File.WriteAllText(
                        payloadPath + ".json",
                        JsonSerializer.Serialize(new Dictionary<string, object?>
                        {
                            ["contractName"] = "chummer6-ui.windows_bootstrap_payload",
                            ["fileName"] = artifact.PayloadFileName,
                            ["downloadUrl"] = payloadDownloadUrl,
                            ["sha256"] = payloadSha,
                            ["sizeBytes"] = payloadSize,
                            ["installerFileName"] = artifact.FileName,
                            ["releaseVersion"] = version
                        }, TestJsonOptions));
                }

                compatibilityArtifacts.Add(new CompatibilityArtifact(
                    Id: artifact.ArtifactId,
                    Platform: artifact.Platform,
                    Url: downloadUrl,
                    Sha256: sha,
                    SizeBytes: size,
                    Head: artifact.Head,
                    PlatformId: $"{artifact.Platform}-{artifact.Arch}",
                    Rid: ArtifactRid(artifact.Platform, artifact.Arch),
                    Arch: artifact.Arch,
                    Kind: artifact.Kind,
                    FileName: artifact.FileName,
                    InstallAccessClass: artifact.InstallAccessClass,
                    InstallerMode: artifact.InstallerMode,
                    PayloadFileName: artifact.PayloadFileName,
                    PayloadDownloadUrl: payloadDownloadUrl,
                    PayloadSha256: payloadSha,
                    PayloadSizeBytes: payloadSize));

                canonicalArtifacts.Add(new CanonicalArtifact(
                    ArtifactId: artifact.ArtifactId,
                    Head: artifact.Head,
                    Rid: ArtifactRid(artifact.Platform, artifact.Arch),
                    Platform: artifact.Platform,
                    Arch: artifact.Arch,
                    Kind: artifact.Kind,
                    FileName: artifact.FileName,
                    DownloadUrl: downloadUrl,
                    Sha256: sha,
                    SizeBytes: size,
                    PlatformLabel: $"Avalonia Desktop {artifact.Platform} {artifact.Arch}",
                    InstallAccessClass: artifact.InstallAccessClass,
                    InstallerMode: artifact.InstallerMode,
                    PayloadFileName: artifact.PayloadFileName,
                    PayloadDownloadUrl: payloadDownloadUrl,
                    PayloadSha256: payloadSha,
                    PayloadSizeBytes: payloadSize));

                if (artifact.Kind is "installer" or "dmg" or "pkg" or "msix")
                {
                    File.WriteAllText(
                        Path.Combine(smokeRoot, $"startup-smoke-{artifact.Head}-{artifact.Platform}-{artifact.Arch}.receipt.json"),
                        JsonSerializer.Serialize(new
                        {
                            status = "pass",
                            headId = artifact.Head,
                            version,
                            releaseVersion = version,
                            channel,
                            channelId = channel,
                            platform = artifact.ReceiptPlatformOverride ?? artifact.Platform,
                            arch = artifact.Arch,
                            rid = ArtifactRid(artifact.Platform, artifact.Arch),
                            readyCheckpoint = "pre_ui_event_loop",
                            hostClass = StartupSmokeHostClass(artifact.Platform, artifact.Arch),
                            operatingSystem = StartupSmokeOperatingSystem(artifact.Platform),
                            artifactDigest = artifact.UseArtifactSha256ReceiptField ? null : $"sha256:{sha}",
                            artifactSha256 = artifact.UseArtifactSha256ReceiptField ? sha : null,
                            artifactId = artifact.ArtifactId,
                            artifactFileName = artifact.FileName,
                            fileName = artifact.FileName,
                            artifactPath = filePath,
                            artifactRelativePath = $"files/{artifact.FileName}",
                            startedAtUtc = smokeTimestamp,
                            recordedAtUtc = smokeTimestamp,
                            completedAtUtc = smokeTimestamp,
                            sourceUpdatedAtUtc = smokeTimestamp,
                            executionEnvironment = FixturePlatformFamily(artifact.Platform) == "windows"
                                ? "native_windows"
                                : null,
                            nativeHostEvidence = FixturePlatformFamily(artifact.Platform) == "windows"
                                ? new
                                {
                                    contractName = "chummer6-ui.native_windows_host_evidence",
                                    status = "verified",
                                    isNativeWindows = true,
                                    hostPlatform = "windows",
                                    hostKernel = "Windows_NT",
                                    runner = "powershell.exe",
                                    evidenceSource = "powershell_runtime_os_probe"
                                }
                                : null
                        }, TestJsonOptions));
                }

                evidenceArtifacts.Add(new PromotionEvidenceArtifact(
                    ArtifactId: artifact.ArtifactId,
                    FileName: artifact.FileName,
                    Platform: artifact.Platform,
                    PromotionStatus: "pass",
                    StartupSmokeStatus: artifact.StartupSmokeStatusOverride ?? "pass",
                    SigningStatus: artifact.SigningStatusOverride ?? (artifact.RequiresSigning ? "pass" : null),
                    NotarizationStatus: artifact.NotarizationStatusOverride ?? (artifact.RequiresNotarization ? "pass" : null)));
            }

            DateTimeOffset proofInstant = DateTimeOffset.Parse(proofGeneratedAt);
            JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
                proofInstant,
                artifacts.Select(static artifact => $"/downloads/install/{artifact.ArtifactId}"));

            WriteCompatibilityManifest(
                Path.Combine(bundleRoot, "releases.json"),
                version,
                compatibilityArtifacts,
                publishedAt,
                channel,
                publicTrustMetrics,
                privacyLaunchGate,
                releaseProof);
            WriteCanonicalManifest(
                Path.Combine(bundleRoot, "RELEASE_CHANNEL.generated.json"),
                version,
                canonicalArtifacts,
                publishedAt,
                channel,
                publicTrustMetrics,
                privacyLaunchGate,
                releaseProof);

            if (seedReviewRequiredPosture)
            {
                SeedReviewRequiredPosture(
                    Path.Combine(bundleRoot, "releases.json"),
                    includeCanonicalProjection: false);
                SeedReviewRequiredPosture(
                    Path.Combine(bundleRoot, "RELEASE_CHANNEL.generated.json"),
                    includeCanonicalProjection: true);
            }

            if (includePromotionEvidence)
            {
                File.WriteAllText(
                    Path.Combine(evidenceRoot, "public-promotion.json"),
                    JsonSerializer.Serialize(new
                    {
                        contractName = "chummer.run.desktop_release_publication",
                        generatedAt = "2026-04-01T21:55:00Z",
                        artifacts = evidenceArtifacts
                    }, TestJsonOptions));
            }

            if (includeBuildProvenance)
            {
                MacBuildProvenanceTestFixture.WriteFiles(
                    bundleRoot,
                    artifacts
                        .Where(artifact => MacBuildProvenanceTestFixture.IsGovernedDesktopPlatform(
                            FixturePlatformFamily(artifact.Platform)))
                        .Select(artifact => new MacBuildProvenanceSubject(
                            artifact.ArtifactId,
                            artifact.Head,
                            artifact.FileName,
                            artifact.Bytes,
                            FixturePlatformFamily(artifact.Platform))));
            }

            if (proofArtifacts is { Count: > 0 })
            {
                string proofRoot = Path.Combine(bundleRoot, "proof");
                foreach (ProofArtifact proofArtifact in proofArtifacts)
                {
                    string targetPath = Path.Combine(proofRoot, proofArtifact.RelativePath.Replace('/', Path.DirectorySeparatorChar));
                    string? targetDirectory = Path.GetDirectoryName(targetPath);
                    if (!string.IsNullOrWhiteSpace(targetDirectory))
                    {
                        Directory.CreateDirectory(targetDirectory);
                    }

                    File.WriteAllBytes(targetPath, proofArtifact.Bytes);
                }
            }

            string zipPath = Path.Combine(_root, $"{Path.GetFileName(bundleRoot)}.zip");
            ZipFile.CreateFromDirectory(bundleRoot, zipPath);
            return zipPath;
        }

        public JsonDocument ReadCompatibilityManifest()
            => JsonDocument.Parse(File.ReadAllText(Path.Combine(_downloadsRoot, "releases.json")));

        public JsonDocument ReadCanonicalManifest()
            => JsonDocument.Parse(File.ReadAllText(Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json")));

        public JsonDocument ReadCurrentPointer()
            => JsonDocument.Parse(File.ReadAllText(Path.Combine(_downloadsRoot, "current.json")));

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                MakeTreeWritable(_root);
                Directory.Delete(_root, recursive: true);
            }
        }

        private static void MakeTreeWritable(string root)
        {
            if (OperatingSystem.IsWindows())
            {
                foreach (string file in Directory.GetFiles(root, "*", SearchOption.AllDirectories))
                {
                    File.SetAttributes(file, File.GetAttributes(file) & ~FileAttributes.ReadOnly);
                }

                return;
            }

            UnixFileMode fileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
            UnixFileMode directoryMode = fileMode | UnixFileMode.UserExecute;
            File.SetUnixFileMode(root, directoryMode);
            foreach (string directory in Directory.GetDirectories(root, "*", SearchOption.AllDirectories))
            {
                File.SetUnixFileMode(directory, directoryMode);
            }

            foreach (string file in Directory.GetFiles(root, "*", SearchOption.AllDirectories))
            {
                File.SetUnixFileMode(file, fileMode);
            }
        }

        public void SetCanonicalMetadata(string channelId, string version)
        {
            string path = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
            JsonNode? root = JsonNode.Parse(File.ReadAllText(path));
            if (root is not JsonObject canonical)
            {
                return;
            }

            canonical["channel"] = channelId;
            canonical["channelId"] = channelId;
            canonical["version"] = version;

            if (canonical["artifacts"] is JsonArray artifacts)
            {
                foreach (JsonObject artifact in artifacts.OfType<JsonObject>())
                {
                    artifact["channel"] = channelId;
                    artifact["channelId"] = channelId;
                    artifact["version"] = version;
                    artifact["releaseVersion"] = version;
                }
            }

            File.WriteAllText(path, canonical.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }

        private static void WriteCompatibilityManifest(
            string path,
            string version,
            IReadOnlyList<CompatibilityArtifact> downloads,
            string publishedAt = "2026-04-01T20:00:00Z",
            string channel = "preview",
            object? publicTrustMetrics = null,
            PrivacyLaunchGateSnapshot? privacyLaunchGate = null,
            JsonObject? releaseProof = null)
        {
            RegistryArtifactProjection[] projections = downloads
                .Select(download => ToRegistryProjection(
                    download.Id,
                    download.Head,
                    download.Platform,
                    download.Arch,
                    download.Kind,
                    download.FileName,
                    download.Url,
                    download.Sha256,
                    download.SizeBytes,
                    download.InstallAccessClass,
                    version,
                    channel,
                    download.InstallerMode,
                    download.PayloadFileName,
                    download.PayloadDownloadUrl,
                    download.PayloadSha256,
                    download.PayloadSizeBytes))
                .ToArray();
            PrivacyLaunchGateSnapshot gate = privacyLaunchGate ?? PrivacyLaunchGate.ClearForTests;
            RegistryPosture posture = gate.BlocksReleaseSupportability
                ? BuildPrivacyRegistryPosture(gate)
                : BuildRegistryPosture(projections, channel);
            bool complete = IsDesktopFloorComplete(projections);
            JsonObject metrics = BuildPublicTrustMetrics(posture, publicTrustMetrics, gate);

            var manifest = new JsonObject
            {
                ["contractName"] = "Chummer.Hub.Registry.Contracts",
                ["contract_name"] = "Chummer.Hub.Registry.Contracts",
                ["source"] = "registry",
                ["schemaVersion"] = 1,
                ["version"] = version,
                ["releaseVersion"] = version,
                ["channel"] = channel,
                ["channelId"] = channel,
                ["publishedAt"] = publishedAt,
                ["status"] = "published",
                ["rolloutState"] = posture.RolloutState,
                ["rolloutReason"] = posture.RolloutReason,
                ["supportabilityState"] = posture.SupportabilityState,
                ["supportabilitySummary"] = posture.SupportabilitySummary,
                ["knownIssueSummary"] = posture.KnownIssueSummary,
                ["fixAvailabilitySummary"] = posture.FixAvailabilitySummary,
                ["releaseProof"] = releaseProof?.DeepClone() ?? BuildReleaseProof(projections, publishedAt),
                ["desktopTupleCoverage"] = BuildDesktopTupleCoverage(projections),
                ["downloads"] = BuildCompatibilityArtifacts(projections),
                ["publicTrustMetrics"] = metrics,
                ["registryBoundaryCoverage"] = BuildRegistryBoundaryCoverage(
                    projections.Length,
                    posture,
                    complete)
            };
            File.WriteAllText(path, manifest.ToJsonString(TestJsonOptions));
        }

        private static void WriteCanonicalManifest(
            string path,
            string version,
            IReadOnlyList<CanonicalArtifact> artifacts,
            string publishedAt = "2026-04-01T20:00:00Z",
            string channel = "preview",
            object? publicTrustMetrics = null,
            PrivacyLaunchGateSnapshot? privacyLaunchGate = null,
            JsonObject? releaseProof = null)
        {
            RegistryArtifactProjection[] projections = artifacts
                .Select(artifact => ToRegistryProjection(
                    artifact.ArtifactId,
                    artifact.Head,
                    artifact.Platform,
                    artifact.Arch,
                    artifact.Kind,
                    artifact.FileName,
                    artifact.DownloadUrl,
                    artifact.Sha256,
                    artifact.SizeBytes,
                    artifact.InstallAccessClass,
                    version,
                    channel,
                    artifact.InstallerMode,
                    artifact.PayloadFileName,
                    artifact.PayloadDownloadUrl,
                    artifact.PayloadSha256,
                    artifact.PayloadSizeBytes))
                .ToArray();
            PrivacyLaunchGateSnapshot gate = privacyLaunchGate ?? PrivacyLaunchGate.ClearForTests;
            RegistryPosture posture = gate.BlocksReleaseSupportability
                ? BuildPrivacyRegistryPosture(gate)
                : BuildRegistryPosture(projections, channel);
            bool complete = IsDesktopFloorComplete(projections);
            JsonObject metrics = BuildPublicTrustMetrics(posture, publicTrustMetrics, gate);

            var manifest = new JsonObject
            {
                ["contractName"] = "Chummer.Hub.Registry.Contracts",
                ["contract_name"] = "Chummer.Hub.Registry.Contracts",
                ["schemaVersion"] = 1,
                ["product"] = "chummer",
                ["version"] = version,
                ["releaseVersion"] = version,
                ["channel"] = channel,
                ["channelId"] = channel,
                ["publishedAt"] = publishedAt,
                ["status"] = "published",
                ["rolloutState"] = posture.RolloutState,
                ["rolloutReason"] = posture.RolloutReason,
                ["supportabilityState"] = posture.SupportabilityState,
                ["supportabilitySummary"] = posture.SupportabilitySummary,
                ["knownIssueSummary"] = posture.KnownIssueSummary,
                ["fixAvailabilitySummary"] = posture.FixAvailabilitySummary,
                ["releaseProof"] = releaseProof?.DeepClone() ?? BuildReleaseProof(projections, publishedAt),
                ["desktopTupleCoverage"] = BuildDesktopTupleCoverage(projections),
                ["artifacts"] = BuildCanonicalArtifacts(projections),
                ["publicTrustMetrics"] = metrics,
                ["registryBoundaryCoverage"] = BuildRegistryBoundaryCoverage(
                    projections.Length,
                    posture,
                    complete)
            };
            File.WriteAllText(path, manifest.ToJsonString(TestJsonOptions));
        }

        private static JsonObject BuildPublicTrustMetrics(
            RegistryPosture posture,
            object? customMetrics,
            PrivacyLaunchGateSnapshot privacyLaunchGate)
        {
            var metrics = new JsonObject
            {
                ["releaseChannel"] = new JsonObject
                {
                    ["posture"] = posture.PublicTrustPosture,
                    ["supportabilityState"] = posture.SupportabilityState
                },
                ["proofFreshness"] = new JsonObject
                {
                    ["status"] = "fresh"
                },
                ["privacyReadiness"] = privacyLaunchGate.ToJsonObject(),
                ["adoptionHealth"] = new JsonObject
                {
                    ["status"] = posture.SupportabilityState == "review_required" ? "limited" : "healthy"
                }
            };
            if (customMetrics is null)
            {
                return metrics;
            }

            JsonObject custom = JsonSerializer.SerializeToNode(customMetrics, TestJsonOptions)?.AsObject()
                ?? throw new InvalidDataException("publicTrustMetrics fixture must serialize to a JSON object.");
            foreach ((string name, JsonNode? value) in custom)
            {
                metrics[name] = value?.DeepClone();
            }

            metrics["privacyReadiness"] = privacyLaunchGate.ToJsonObject();

            return metrics;
        }

        private static RegistryPosture BuildPrivacyRegistryPosture(PrivacyLaunchGateSnapshot privacyLaunchGate)
            => new(
                "public_release_review_required",
                privacyLaunchGate.Reason,
                "review_required",
                privacyLaunchGate.Reason,
                privacyLaunchGate.Reason,
                privacyLaunchGate.Reason,
                "blocked");

        private static JsonObject BuildRegistryBoundaryCoverage(
            int artifactCount,
            RegistryPosture posture,
            bool complete)
            => new()
            {
                ["owner"] = "chummer6-hub-registry",
                ["status"] = "closed",
                ["persistence"] = new JsonObject
                {
                    ["artifactCount"] = artifactCount
                },
                ["compatibility"] = new JsonObject
                {
                    ["compatibleArtifactCount"] = artifactCount
                },
                ["releaseChannel"] = new JsonObject
                {
                    ["supportabilityState"] = posture.SupportabilityState,
                    ["desktopTupleComplete"] = complete,
                    ["publicTrustPosture"] = posture.PublicTrustPosture
                }
            };

        private static RegistryArtifactProjection ToRegistryProjection(
            string artifactId,
            string head,
            string platform,
            string arch,
            string kind,
            string fileName,
            string downloadUrl,
            string sha256,
            long sizeBytes,
            string installAccessClass,
            string version,
            string channel,
            string? installerMode,
            string? payloadFileName,
            string? payloadDownloadUrl,
            string? payloadSha256,
            long? payloadSizeBytes)
        {
            string normalizedPlatform = NormalizePlatform(platform);
            return new RegistryArtifactProjection(
                artifactId,
                head,
                normalizedPlatform,
                RidFor(normalizedPlatform, arch),
                arch,
                kind,
                fileName,
                downloadUrl,
                sha256,
                sizeBytes,
                installAccessClass,
                version,
                channel,
                installerMode,
                payloadFileName,
                payloadDownloadUrl,
                payloadSha256,
                payloadSizeBytes);
        }

        private static JsonObject BuildReleaseProof(
            IReadOnlyList<RegistryArtifactProjection> artifacts,
            string generatedAt)
            => new()
            {
                ["status"] = "passed",
                ["generatedAt"] = generatedAt,
                ["baseUrl"] = "https://chummer.run",
                ["journeysPassed"] = JsonStrings(["build_explain_publish"]),
                ["proofRoutes"] = JsonStrings(
                    artifacts.Select(static artifact => $"/downloads/install/{artifact.ArtifactId}"))
            };

        private static JsonArray BuildCompatibilityArtifacts(
            IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            var rows = new JsonArray();
            foreach (RegistryArtifactProjection artifact in artifacts)
            {
                rows.Add(BuildRegistryArtifact(artifact, compatibility: true));
            }

            return rows;
        }

        private static JsonArray BuildCanonicalArtifacts(
            IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            var rows = new JsonArray();
            foreach (RegistryArtifactProjection artifact in artifacts)
            {
                rows.Add(BuildRegistryArtifact(artifact, compatibility: false));
            }

            return rows;
        }

        private static JsonObject BuildRegistryArtifact(
            RegistryArtifactProjection artifact,
            bool compatibility)
        {
            var row = new JsonObject
            {
                ["artifactId"] = artifact.ArtifactId,
                ["head"] = artifact.Head,
                ["platform"] = artifact.Platform,
                ["rid"] = artifact.Rid,
                ["arch"] = artifact.Arch,
                ["kind"] = artifact.Kind,
                ["fileName"] = artifact.FileName,
                [compatibility ? "url" : "downloadUrl"] = artifact.DownloadUrl,
                ["sha256"] = artifact.Sha256,
                ["sizeBytes"] = artifact.SizeBytes,
                ["installAccessClass"] = artifact.InstallAccessClass,
                ["version"] = artifact.Version,
                ["releaseVersion"] = artifact.Version,
                ["channel"] = artifact.Channel,
                ["channelId"] = artifact.Channel,
                ["status"] = "available"
            };
            if (compatibility)
            {
                row["id"] = artifact.ArtifactId;
                row["platformId"] = artifact.Platform;
                row["platformLabel"] = $"Avalonia Desktop {artifact.Platform} {artifact.Arch}";
            }
            else
            {
                row["platformLabel"] = $"Avalonia Desktop {artifact.Platform} {artifact.Arch}";
                row["rolloutState"] = "promoted";
            }

            if (!string.IsNullOrWhiteSpace(artifact.InstallerMode))
            {
                row["installerMode"] = artifact.InstallerMode;
            }

            if (!string.IsNullOrWhiteSpace(artifact.PayloadFileName))
            {
                row["payloadFileName"] = artifact.PayloadFileName;
                row["payloadDownloadUrl"] = artifact.PayloadDownloadUrl;
                row["payloadSha256"] = artifact.PayloadSha256;
                row["payloadSizeBytes"] = artifact.PayloadSizeBytes;
            }

            return row;
        }

        private static JsonObject BuildDesktopTupleCoverage(
            IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            const string requiredHead = "avalonia";
            string[] requiredPlatforms = ["linux", "windows", "macos"];
            string[] requiredTuples =
            [
                "avalonia:linux-x64:linux",
                "avalonia:osx-arm64:macos",
                "avalonia:win-x64:windows"
            ];
            RegistryArtifactProjection[] installers = artifacts
                .Where(IsPromotedDesktopInstaller)
                .ToArray();
            HashSet<string> promotedPlatforms = installers
                .Select(static artifact => artifact.Platform)
                .ToHashSet(StringComparer.Ordinal);
            HashSet<string> promotedHeads = installers
                .Select(static artifact => artifact.Head)
                .ToHashSet(StringComparer.Ordinal);
            HashSet<string> promotedPairs = installers
                .Select(static artifact => $"{artifact.Head}:{artifact.Platform}")
                .ToHashSet(StringComparer.Ordinal);
            HashSet<string> promotedRequiredTuples = installers
                .Where(static artifact => artifact.Head == requiredHead)
                .Select(static artifact => $"{artifact.Head}:{artifact.Rid}:{artifact.Platform}")
                .ToHashSet(StringComparer.Ordinal);
            string[] missingPlatforms = requiredPlatforms
                .Where(platform => !promotedPlatforms.Contains(platform))
                .ToArray();
            string[] missingHeads = promotedHeads.Contains(requiredHead) ? [] : [requiredHead];
            string[] missingPairs = requiredPlatforms
                .Select(platform => $"{requiredHead}:{platform}")
                .Where(pair => !promotedPairs.Contains(pair))
                .ToArray();
            string[] missingTuples = requiredTuples
                .Where(tuple => !promotedRequiredTuples.Contains(tuple))
                .ToArray();
            var promotedInstallerTuples = new JsonArray();
            foreach (RegistryArtifactProjection artifact in installers.OrderBy(
                         static artifact => $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}",
                         StringComparer.Ordinal))
            {
                promotedInstallerTuples.Add(new JsonObject
                {
                    ["tupleId"] = $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}",
                    ["artifactId"] = artifact.ArtifactId,
                    ["head"] = artifact.Head,
                    ["platform"] = artifact.Platform,
                    ["rid"] = artifact.Rid,
                    ["arch"] = artifact.Arch,
                    ["kind"] = artifact.Kind
                });
            }

            return new JsonObject
            {
                ["requiredDesktopPlatforms"] = JsonStrings(requiredPlatforms),
                ["requiredDesktopHeads"] = JsonStrings([requiredHead]),
                ["requiredDesktopPlatformHeadRidTuples"] = JsonStrings(requiredTuples),
                ["promotedInstallerTuples"] = promotedInstallerTuples,
                ["promotedPlatformHeadRidTuples"] = JsonStrings(
                    installers
                        .Select(static artifact => $"{artifact.Head}:{artifact.Rid}:{artifact.Platform}")
                        .Distinct(StringComparer.Ordinal)
                        .Order(StringComparer.Ordinal)),
                ["missingRequiredPlatforms"] = JsonStrings(missingPlatforms),
                ["missingRequiredHeads"] = JsonStrings(missingHeads),
                ["missingRequiredPlatformHeadPairs"] = JsonStrings(missingPairs),
                ["missingRequiredPlatformHeadRidTuples"] = JsonStrings(missingTuples),
                ["externalProofRequests"] = new JsonArray(),
                ["complete"] = missingTuples.Length == 0
            };
        }

        private static RegistryPosture BuildRegistryPosture(
            IReadOnlyList<RegistryArtifactProjection> artifacts,
            string channel)
        {
            if (!IsDesktopFloorComplete(artifacts))
            {
                return new RegistryPosture(
                    "coverage_incomplete",
                    "Registry requires Linux, Windows, and macOS desktop installer coverage.",
                    "review_required",
                    "Registry review is required until the desktop platform floor is complete.",
                    "The desktop platform floor is incomplete.",
                    "Publish the missing Registry-validated desktop installers.",
                    "preview");
            }

            bool stable = string.Equals(channel, "stable", StringComparison.OrdinalIgnoreCase);
            return new RegistryPosture(
                stable ? "public_stable" : "promoted_preview",
                "Registry verified the complete desktop release shelf.",
                stable ? "gold_supported" : "preview_supported",
                "Registry verified the release supportability posture.",
                "No blocking release issue is known.",
                "No corrective publication is required.",
                stable ? "live" : "preview");
        }

        private static bool IsDesktopFloorComplete(IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            HashSet<string> tuples = artifacts
                .Where(IsPromotedDesktopInstaller)
                .Where(static artifact => artifact.Head == "avalonia")
                .Select(static artifact => $"{artifact.Head}:{artifact.Rid}:{artifact.Platform}")
                .ToHashSet(StringComparer.Ordinal);
            return tuples.Contains("avalonia:linux-x64:linux")
                   && tuples.Contains("avalonia:osx-arm64:macos")
                   && tuples.Contains("avalonia:win-x64:windows");
        }

        private static bool IsPromotedDesktopInstaller(RegistryArtifactProjection artifact)
            => artifact.Platform == "macos"
                ? artifact.Kind is "installer" or "dmg" or "pkg"
                : artifact.Kind == "installer";

        private static string NormalizePlatform(string platform)
        {
            string token = platform.Trim().ToLowerInvariant().Replace('_', '-');
            if (token.StartsWith("mac", StringComparison.Ordinal)
                || token.StartsWith("osx", StringComparison.Ordinal)
                || token.StartsWith("darwin", StringComparison.Ordinal))
            {
                return "macos";
            }

            if (token.StartsWith("win", StringComparison.Ordinal))
            {
                return "windows";
            }

            return token.StartsWith("linux", StringComparison.Ordinal) ? "linux" : token;
        }

        private static string RidFor(string platform, string arch)
            => (platform, arch.ToLowerInvariant()) switch
            {
                ("linux", "arm64") => "linux-arm64",
                ("linux", _) => "linux-x64",
                ("windows", "arm64") => "win-arm64",
                ("windows", _) => "win-x64",
                ("macos", "x64") => "osx-x64",
                ("macos", _) => "osx-arm64",
                _ => string.Empty
            };

        private static JsonArray JsonStrings(IEnumerable<string> values)
        {
            var result = new JsonArray();
            foreach (string value in values)
            {
                result.Add(value);
            }

            return result;
        }

        private static void SeedReviewRequiredPosture(string path, bool includeCanonicalProjection)
        {
            JsonObject root = JsonNode.Parse(File.ReadAllText(path))?.AsObject()
                ?? throw new InvalidDataException($"Expected a JSON object at {path}.");
            const string reviewReason =
                "Current shelf remains review-required because stale or incomplete proof receipts must be refreshed.";
            root["rolloutState"] = "public_release_review_required";
            root["rolloutReason"] = reviewReason;
            root["supportabilityState"] = "review_required";
            root["supportabilitySummary"] = reviewReason;
            root["knownIssueSummary"] = reviewReason;
            root["fixAvailabilitySummary"] = reviewReason;
            if (root["releaseProof"] is JsonObject releaseProof)
            {
                releaseProof["status"] = "review_required";
            }

            if (root["publicTrustMetrics"] is not JsonObject metrics)
            {
                metrics = new JsonObject();
                root["publicTrustMetrics"] = metrics;
            }

            if (metrics["releaseChannel"] is not JsonObject releaseChannel)
            {
                releaseChannel = new JsonObject();
                metrics["releaseChannel"] = releaseChannel;
            }

            releaseChannel["supportabilityState"] = "review_required";
            releaseChannel["posture"] = "blocked";
            metrics["adoptionHealth"] = new JsonObject { ["status"] = "limited" };
            if (metrics["proofFreshness"] is not JsonObject proofFreshness)
            {
                proofFreshness = new JsonObject();
                metrics["proofFreshness"] = proofFreshness;
            }

            string freshness = proofFreshness["status"]?.GetValue<string?>()?.Trim().ToLowerInvariant()
                ?? string.Empty;
            proofFreshness["status"] = freshness is "" or "missing" ? "missing" : "stale";

            if (root["registryBoundaryCoverage"] is not JsonObject boundary)
            {
                boundary = new JsonObject();
                root["registryBoundaryCoverage"] = boundary;
            }

            if (boundary["releaseChannel"] is not JsonObject boundaryReleaseChannel)
            {
                boundaryReleaseChannel = new JsonObject();
                boundary["releaseChannel"] = boundaryReleaseChannel;
            }

            boundaryReleaseChannel["supportabilityState"] = "review_required";
            boundaryReleaseChannel["publicTrustPosture"] = "blocked";

            File.WriteAllText(path, root.ToJsonString(TestJsonOptions));
        }

        private static string Sha256For(string path)
        {
            using var sha = SHA256.Create();
            using FileStream stream = File.OpenRead(path);
            return Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant();
        }

        private static string ArtifactRid(string platform, string arch)
            => FixturePlatformFamily(platform) switch
            {
                "windows" => $"win-{arch}",
                "macos" => $"osx-{arch}",
                _ => $"linux-{arch}"
            };

        private static string FixturePlatformFamily(string platform)
        {
            string normalized = platform.Trim().ToLowerInvariant();
            int separator = normalized.IndexOfAny(['-', '_', '/', ' ']);
            if (separator >= 0)
            {
                normalized = normalized[..separator];
            }

            return normalized switch
            {
                "win" or "windows" => "windows",
                "mac" or "macos" or "osx" or "darwin" => "macos",
                _ => "linux"
            };
        }

        private static string StartupSmokeHostClass(string platform, string arch)
            => FixturePlatformFamily(platform) switch
            {
                "windows" => $"windows-{arch}-host",
                "macos" => $"local-osx-{arch}",
                _ => $"local-linux-{arch}"
            };

        private static string StartupSmokeOperatingSystem(string platform)
            => FixturePlatformFamily(platform) switch
            {
                "windows" => "Microsoft Windows 11",
                "macos" => "macOS 15",
                _ => "Linux"
            };
    }

    internal sealed record BundleArtifact(
        string ArtifactId,
        string Head,
        string Platform,
        string Arch,
        string Kind,
        string FileName,
        byte[] Bytes,
        bool RequiresSigning,
        bool RequiresNotarization,
        string? SigningStatusOverride = null,
        string? NotarizationStatusOverride = null,
        string? StartupSmokeStatusOverride = null,
        bool UseArtifactSha256ReceiptField = false,
        string? ReceiptPlatformOverride = null,
        string InstallAccessClass = "account_required",
        string? InstallerMode = null,
        string? PayloadFileName = null,
        byte[]? PayloadBytes = null);

    private sealed record CompatibilityArtifact(
        string Id,
        string Platform,
        string Url,
        string Sha256,
        long SizeBytes,
        string Head,
        string PlatformId,
        string Rid,
        string Arch,
        string Kind,
        string FileName,
        string InstallAccessClass,
        string? InstallerMode = null,
        string? PayloadFileName = null,
        string? PayloadDownloadUrl = null,
        string? PayloadSha256 = null,
        long? PayloadSizeBytes = null);

    private sealed record CanonicalArtifact(
        string ArtifactId,
        string Head,
        string Rid,
        string Platform,
        string Arch,
        string Kind,
        string FileName,
        string DownloadUrl,
        string Sha256,
        long SizeBytes,
        string PlatformLabel,
        string InstallAccessClass,
        string? InstallerMode = null,
        string? PayloadFileName = null,
        string? PayloadDownloadUrl = null,
        string? PayloadSha256 = null,
        long? PayloadSizeBytes = null);

    private sealed record RegistryArtifactProjection(
        string ArtifactId,
        string Head,
        string Platform,
        string Rid,
        string Arch,
        string Kind,
        string FileName,
        string DownloadUrl,
        string Sha256,
        long SizeBytes,
        string InstallAccessClass,
        string Version,
        string Channel,
        string? InstallerMode,
        string? PayloadFileName,
        string? PayloadDownloadUrl,
        string? PayloadSha256,
        long? PayloadSizeBytes);

    private sealed record RegistryPosture(
        string RolloutState,
        string RolloutReason,
        string SupportabilityState,
        string SupportabilitySummary,
        string KnownIssueSummary,
        string FixAvailabilitySummary,
        string PublicTrustPosture);

    private sealed record PromotionEvidenceArtifact(
        string ArtifactId,
        string FileName,
        string Platform,
        string PromotionStatus,
        string StartupSmokeStatus,
        string? SigningStatus,
        string? NotarizationStatus);

    internal sealed record ProofArtifact(
        string RelativePath,
        byte[] Bytes);
}
