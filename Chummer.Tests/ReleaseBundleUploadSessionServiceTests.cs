using Chummer.Run.Api.Services;
using System.Security.Cryptography;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBundleUploadSessionServiceTests
{
    private const string AuthorizationA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string AuthorizationB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    [Fact]
    public async Task WriteFileAsyncStoresRelativePathUnderBundleRoot()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();

        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/chummer-avalonia-osx-x64-installer.dmg",
            new MemoryStream("mac"u8.ToArray()),
            CancellationToken.None);

        string filePath = Path.Combine(session.BundleRoot, "files", "chummer-avalonia-osx-x64-installer.dmg");
        Assert.True(File.Exists(filePath));
        Assert.Equal("mac", await File.ReadAllTextAsync(filePath));
    }

    [Fact]
    public void ResolveBundleRootRejectsInvalidSessionId()
    {
        using Fixture fixture = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() =>
            fixture.Service.ResolveBundleRoot("not-a-guid"));

        Assert.Contains("valid GUID", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task WriteFileAsyncRejectsInvalidSessionId()
    {
        using Fixture fixture = new();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.WriteFileAsync(
                "../bad-session-id",
                "files/chummer-avalonia-osx-x64-installer.dmg",
                new MemoryStream("mac"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("valid GUID", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task AppendChunkAsyncRejectsInvalidSessionId()
    {
        using Fixture fixture = new();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.AppendChunkAsync(
                "bad::session",
                "files/chummer-avalonia-win-x64.exe",
                0,
                1,
                new MemoryStream("hello"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("valid GUID", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task AppendChunkAsyncReassemblesChunkedFile()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();

        await fixture.Service.AppendChunkAsync(
            session.SessionId,
            "files/chummer-avalonia-win-x64.exe",
            0,
            2,
            new MemoryStream("hello "u8.ToArray()),
            CancellationToken.None);

        ReleaseUploadChunkResult result = await fixture.Service.AppendChunkAsync(
            session.SessionId,
            "files/chummer-avalonia-win-x64.exe",
            1,
            2,
            new MemoryStream("world"u8.ToArray()),
            CancellationToken.None);

        Assert.True(result.Completed);
        string filePath = Path.Combine(session.BundleRoot, "files", "chummer-avalonia-win-x64.exe");
        Assert.True(File.Exists(filePath));
        Assert.Equal("hello world", await File.ReadAllTextAsync(filePath));
    }

    [Fact]
    public async Task AppendChunkAsyncRejectsOutOfOrderChunks()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.AppendChunkAsync(
                session.SessionId,
                "files/chummer-avalonia-win-x64.exe",
                1,
                2,
                new MemoryStream("world"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("expected chunk 0", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ReadSessionMetadataRejectsExpiredSession()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();
        fixture.WriteSessionMetadata(session.SessionId, new ReleaseUploadSession(
            session.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            session.BundleRoot));

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.WriteFileAsync(
                session.SessionId,
                "files/chummer-avalonia-osx-x64-installer.dmg",
                new MemoryStream("mac"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("upload session has expired", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ReadSessionMetadataRejectsTamperedSessionId()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();
        fixture.WriteSessionMetadata(session.SessionId, new ReleaseUploadSession(
            Guid.NewGuid().ToString("N"),
            session.ExpiresAtUtc,
            session.BundleRoot));

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() =>
            fixture.Service.ResolveBundleRoot(session.SessionId));

        Assert.Contains("metadata is invalid", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task BoundSessionRejectsAValidDifferentAuthorization()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.WriteFileAsync(
                session.SessionId,
                "releases.json",
                new MemoryStream("{}"u8.ToArray()),
                AuthorizationB,
                CancellationToken.None));

        Assert.Contains("authorization does not match", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SingleUseAuthorizationReusesActiveSessionThenRejectsNewSessionAfterCompletion()
    {
        using Fixture fixture = new();
        DateTimeOffset authorizationExpiry = DateTimeOffset.UtcNow.AddHours(12);
        ReleaseUploadSession created = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            authorizationExpiry);
        ReleaseUploadSession retried = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            authorizationExpiry);
        Assert.Equal(created.SessionId, retried.SessionId);

        ReleaseBundlePromotionResult result = BuildPromotionResult();
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.Service.BeginCompletion(created.SessionId, AuthorizationA))
        {
            Assert.Null(completion.CompletedResult);
            completion.RecordActivationIntent(BuildActivationIntent(result));
            completion.MarkCompleted(result);
        }

        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease retry =
               fixture.Service.BeginCompletion(created.SessionId, AuthorizationA))
        {
            Assert.NotNull(retry.CompletedResult);
            Assert.Equal(result.Version, retry.CompletedResult!.Version);
            Assert.Equal(result.PublishedAt, retry.CompletedResult.PublishedAt);
        }

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            fixture.Service.CreateSession(AuthorizationA, singleUseAuthorization: true, authorizationExpiry));
        Assert.Contains("already been consumed", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CandidateImportAuthorizationIsOneShotAndCannotCrossCandidateBindings()
    {
        using Fixture fixture = new();
        DateTimeOffset authorizationExpiry = DateTimeOffset.UtcNow.AddHours(2);
        var candidate = new ReleaseUploadCandidateSessionBinding(
            SnapshotSha256: new string('1', 64),
            AuthoritySha256: new string('2', 64),
            BundleIdentitySha256: new string('3', 64),
            CanonicalManifestSha256: new string('4', 64),
            InventorySha256: new string('5', 64));
        ReleaseUploadSession created = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            authorizationExpiry,
            candidate);
        ReleaseUploadSession durableRetry = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            authorizationExpiry,
            candidate);
        Assert.Equal(created.SessionId, durableRetry.SessionId);
        Assert.Equal(candidate, durableRetry.CandidateImportBinding);

        ReleaseUploadCandidateSessionBinding differentCandidate = candidate with
        {
            BundleIdentitySha256 = new string('6', 64)
        };
        InvalidOperationException crossCandidate = Assert.Throws<InvalidOperationException>(() =>
            fixture.Service.CreateSession(
                AuthorizationA,
                singleUseAuthorization: true,
                authorizationExpiry,
                differentCandidate));
        Assert.Contains("candidate binding changed", crossCandidate.Message, StringComparison.OrdinalIgnoreCase);

        ReleaseBundlePromotionResult result = BuildPromotionResult();
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.Service.BeginCompletion(created.SessionId, AuthorizationA))
        {
            completion.RecordActivationIntent(BuildActivationIntent(result));
            completion.MarkCompleted(result);
        }

        InvalidOperationException consumed = Assert.Throws<InvalidOperationException>(() =>
            fixture.Service.CreateSession(
                AuthorizationA,
                singleUseAuthorization: true,
                authorizationExpiry,
                candidate));
        Assert.Contains("already been consumed", consumed.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CompletedSessionRejectsFurtherWrites()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));
        ReleaseBundlePromotionResult result = BuildPromotionResult();
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.Service.BeginCompletion(session.SessionId, AuthorizationA))
        {
            completion.RecordActivationIntent(BuildActivationIntent(result));
            completion.MarkCompleted(result);
        }

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.WriteFileAsync(
                session.SessionId,
                "releases.json",
                new MemoryStream("{}"u8.ToArray()),
                AuthorizationA,
                CancellationToken.None));
        Assert.Contains("already been completed", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ActivationIntentPointerBytesMustMatchTheirDurableDigestBinding()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();
        ReleaseActivationIntent valid = BuildActivationIntent(BuildPromotionResult());
        ReleaseActivationIntent tampered = valid with
        {
            TargetPointerBase64 = Convert.ToBase64String("different-pointer"u8.ToArray())
        };

        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
            fixture.Service.BeginCompletion(session.SessionId, session.AuthorizationBinding);
        InvalidDataException ex = Assert.Throws<InvalidDataException>(() =>
            completion.RecordActivationIntent(tampered));

        Assert.Contains("digest bindings", ex.Message, StringComparison.Ordinal);
        Assert.Null(completion.ActivationIntent);
        Assert.False(completion.PublicationOutcomeUnknown);
    }

    [Fact]
    public void SingleUseAuthorizationRequiresExplicitDurableSessionRoot()
    {
        IConfiguration configuration = new ConfigurationBuilder().Build();
        var service = new ReleaseBundleUploadSessionService(
            configuration,
            NullLogger<ReleaseBundleUploadSessionService>.Instance);

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            service.CreateSession(
                AuthorizationA,
                singleUseAuthorization: true,
                DateTimeOffset.UtcNow.AddHours(12)));

        Assert.Contains("CHUMMER_RELEASE_UPLOAD_SESSION_ROOT", ex.Message, StringComparison.Ordinal);
        Assert.Contains("durable shared storage", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PublishingStateSurvivesRestartAndPreventsBlindRetry()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.Service.BeginCompletion(session.SessionId, AuthorizationA))
        {
            completion.RecordActivationIntent(BuildActivationIntent(BuildPromotionResult()));
        }

        ReleaseBundleUploadSessionService restarted = fixture.CreateService();
        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease retry =
            restarted.BeginCompletion(session.SessionId, AuthorizationA);

        Assert.True(retry.PublicationOutcomeUnknown);
        Assert.Null(retry.CompletedResult);
        Assert.NotNull(retry.ActivationIntent);
    }

    [Fact]
    public void PublishingStateSurvivesSessionAndAuthorizationExpiryUntilReconciled()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));
        ReleaseActivationIntent intent = BuildActivationIntent(BuildPromotionResult());
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.Service.BeginCompletion(session.SessionId, AuthorizationA))
        {
            completion.RecordActivationIntent(intent);
        }

        fixture.WriteSessionMetadata(
            session.SessionId,
            session with
            {
                ExpiresAtUtc = DateTimeOffset.UtcNow.AddDays(-2),
                AuthorizationExpiresAtUtc = DateTimeOffset.UtcNow.AddDays(-1),
                Publishing = true,
                ActivationIntent = intent
            });
        fixture.Service.PurgeExpiredSessions();

        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease retry =
            fixture.CreateService().BeginCompletion(session.SessionId, AuthorizationA);
        Assert.True(retry.PublicationOutcomeUnknown);
        Assert.Equal(intent, retry.ActivationIntent);
    }

    [Fact]
    public void CompletedUnacknowledgedReceiptSurvivesExpiryUntilPromotionAcknowledgesIt()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));
        ReleaseBundlePromotionResult result = BuildPromotionResult();
        ReleaseActivationIntent intent = BuildActivationIntent(result);
        fixture.WriteSessionMetadata(
            session.SessionId,
            session with
            {
                ExpiresAtUtc = DateTimeOffset.UtcNow.AddDays(-2),
                AuthorizationExpiresAtUtc = DateTimeOffset.UtcNow.AddDays(-1),
                Completed = true,
                CompletionResult = result,
                ActivationIntent = intent,
                CompletedAtUtc = DateTimeOffset.UtcNow.AddDays(-1)
            });

        fixture.Service.PurgeExpiredSessions();

        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease retry =
            fixture.CreateService().BeginCompletion(session.SessionId, AuthorizationA);
        Assert.Equal(result.Version, retry.CompletedResult?.Version);
        Assert.Equal(intent, retry.ActivationIntent);
    }

    [Fact]
    public void JanitorRemovesAcknowledgedCompletionReceiptAfterRetention()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));
        ReleaseBundlePromotionResult result = BuildPromotionResult();
        ReleaseActivationIntent intent = BuildActivationIntent(result);
        fixture.WriteSessionMetadata(
            session.SessionId,
            session with
            {
                Completed = true,
                CompletionResult = result,
                ActivationIntent = intent,
                CompletedAtUtc = DateTimeOffset.UtcNow.AddDays(-9),
                ActivationAcknowledgedAtUtc = DateTimeOffset.UtcNow.AddDays(-8),
                AuthorizationExpiresAtUtc = DateTimeOffset.UtcNow.AddDays(-8)
            });

        fixture.Service.PurgeExpiredSessions();

        Assert.False(Directory.Exists(Path.Combine(fixture.SessionsRoot, session.SessionId)));
    }

    [Fact]
    public void SingleUseCompletionTombstoneSurvivesShortRetentionUntilAuthorizationExpiry()
    {
        using Fixture fixture = new(completedReceiptRetentionSeconds: 1);
        DateTimeOffset authorizationExpiry = DateTimeOffset.UtcNow.AddMinutes(30);
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            authorizationExpiry);
        ReleaseBundlePromotionResult result = BuildPromotionResult();
        ReleaseActivationIntent intent = BuildActivationIntent(result);
        ReleaseUploadSession completed = session with
        {
            ExpiresAtUtc = DateTimeOffset.UtcNow.AddHours(-2),
            AuthorizationExpiresAtUtc = authorizationExpiry,
            Completed = true,
            CompletionResult = result,
            ActivationIntent = intent,
            CompletedAtUtc = DateTimeOffset.UtcNow.AddHours(-1),
            ActivationAcknowledgedAtUtc = DateTimeOffset.UtcNow.AddHours(-1)
        };
        fixture.WriteSessionMetadata(session.SessionId, completed);

        fixture.Service.PurgeExpiredSessions();

        Assert.True(Directory.Exists(Path.Combine(fixture.SessionsRoot, session.SessionId)));
        InvalidOperationException replay = Assert.Throws<InvalidOperationException>(() =>
            fixture.CreateService().CreateSession(
                AuthorizationA,
                singleUseAuthorization: true,
                authorizationExpiry));
        Assert.Contains("already been consumed", replay.Message, StringComparison.OrdinalIgnoreCase);

        fixture.WriteSessionMetadata(
            session.SessionId,
            completed with { AuthorizationExpiresAtUtc = DateTimeOffset.UtcNow.AddSeconds(-1) });
        fixture.Service.PurgeExpiredSessions();
        Assert.False(Directory.Exists(Path.Combine(fixture.SessionsRoot, session.SessionId)));
    }

    [Fact]
    public void JanitorRetainsUnverifiableSessionMetadataAndAdmissionFailsClosed()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();
        string sessionRoot = Path.Combine(fixture.SessionsRoot, session.SessionId);
        File.WriteAllText(Path.Combine(sessionRoot, "session.json"), "{not-json");

        fixture.Service.PurgeExpiredSessions();
        ReleaseUploadStorageReadiness readiness =
            fixture.Service.EvaluateStorageReadiness(CancellationToken.None);

        Assert.True(Directory.Exists(sessionRoot));
        Assert.False(readiness.Ready);
        Assert.Equal("upload_session_root_unavailable", readiness.Code);
        Assert.Throws<InvalidDataException>(() => fixture.Service.CreateSession());
    }

    [Fact]
    public void IndependentServicesSharingRootReuseTheSameSingleUseAuthorizationSession()
    {
        using Fixture fixture = new();
        ReleaseBundleUploadSessionService secondService = fixture.CreateService();
        DateTimeOffset authorizationExpiry = DateTimeOffset.UtcNow.AddHours(12);

        ReleaseUploadSession first = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            authorizationExpiry);
        ReleaseUploadSession second = secondService.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            authorizationExpiry);

        Assert.Equal(first.SessionId, second.SessionId);
    }

    [Fact]
    public void PurgeRetainsCompletedInternalAuthorizationReceiptUntilSessionExpiry()
    {
        using Fixture fixture = new();
        ReleaseUploadSession completedSession = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: false);
        ReleaseBundlePromotionResult result = BuildPromotionResult();
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.Service.BeginCompletion(completedSession.SessionId, AuthorizationA))
        {
            completion.RecordActivationIntent(BuildActivationIntent(result));
            completion.MarkCompleted(result);
        }

        _ = fixture.Service.CreateSession(AuthorizationB, singleUseAuthorization: false);

        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease retry =
            fixture.CreateService().BeginCompletion(completedSession.SessionId, AuthorizationA);
        Assert.NotNull(retry.CompletedResult);
        Assert.Equal("run-test", retry.CompletedResult!.Version);
    }

    [Fact]
    public void PurgeSkipsSessionWhoseCompletionLockIsHeld()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: false);
        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease heldCompletion =
            fixture.Service.BeginCompletion(session.SessionId, AuthorizationA);
        fixture.WriteSessionMetadata(
            session.SessionId,
            session with { ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1) });

        fixture.CreateService().PurgeExpiredSessions();

        Assert.True(Directory.Exists(Path.Combine(fixture.SessionsRoot, session.SessionId)));
    }

    [Fact]
    public async Task SessionStateAndLockFilesAreOwnerOnlyOnUnix()
    {
        if (!(OperatingSystem.IsLinux() || OperatingSystem.IsMacOS() || OperatingSystem.IsFreeBSD()))
        {
            return;
        }

        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));
        await fixture.Service.AppendChunkAsync(
            session.SessionId,
            "files/chummer-avalonia-win-x64.exe",
            0,
            2,
            new MemoryStream("hello "u8.ToArray()),
            AuthorizationA,
            CancellationToken.None);

        string sessionRoot = Path.Combine(fixture.SessionsRoot, session.SessionId);
        Assert.Equal(OwnerDirectoryMode, File.GetUnixFileMode(sessionRoot));
        Assert.Equal(OwnerDirectoryMode, File.GetUnixFileMode(session.BundleRoot));
        Assert.Equal(OwnerFileMode, File.GetUnixFileMode(Path.Combine(sessionRoot, "session.json")));
        Assert.Equal(OwnerFileMode, File.GetUnixFileMode(Path.Combine(sessionRoot, ".session.lock")));
        Assert.Equal(
            OwnerFileMode,
            File.GetUnixFileMode(Path.Combine(
                fixture.SessionsRoot,
                ".authorization-locks",
                AuthorizationA + ".lock")));
        string chunkStatePath = Assert.Single(Directory.EnumerateFiles(
            Path.Combine(sessionRoot, "staging"),
            "chunk-state.json",
            SearchOption.AllDirectories));
        Assert.Equal(OwnerFileMode, File.GetUnixFileMode(chunkStatePath));
    }

    [Fact]
    public void AtomicMetadataRenameFlushesItsParentDirectory()
    {
        using Fixture fixture = new();
        var flushedDirectories = new List<string>();
        ReleaseBundleUploadSessionService service = fixture.CreateService(
            directory => flushedDirectories.Add(Path.GetFullPath(directory)));

        ReleaseUploadSession session = service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));
        string expectedSessionRoot = Path.GetFullPath(Path.Combine(fixture.SessionsRoot, session.SessionId));
        Assert.Contains(expectedSessionRoot, flushedDirectories);

        int beforePublishing = flushedDirectories.Count;
        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
            service.BeginCompletion(session.SessionId, AuthorizationA);
        completion.RecordActivationIntent(BuildActivationIntent(BuildPromotionResult()));

        Assert.True(flushedDirectories.Count > beforePublishing);
        Assert.Equal(expectedSessionRoot, flushedDirectories[^1]);
    }

    [Fact]
    public void PublishingStopsBeforePromotionWhenDirectoryDurabilityCannotBeConfirmed()
    {
        using Fixture fixture = new();
        int flushCount = 0;
        ReleaseBundleUploadSessionService service = fixture.CreateService(_ =>
        {
            flushCount++;
            if (flushCount >= 2)
            {
                throw new IOException("simulated directory fsync failure");
            }
        });
        ReleaseUploadSession session = service.CreateSession(
            AuthorizationA,
            singleUseAuthorization: true,
            DateTimeOffset.UtcNow.AddHours(12));

        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               service.BeginCompletion(session.SessionId, AuthorizationA))
        {
            IOException exception = Assert.Throws<IOException>(() =>
                completion.RecordActivationIntent(BuildActivationIntent(BuildPromotionResult())));
            Assert.Contains("fsync", exception.Message, StringComparison.OrdinalIgnoreCase);
        }

        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease retry =
            fixture.CreateService().BeginCompletion(session.SessionId, AuthorizationA);
        Assert.True(retry.PublicationOutcomeUnknown);
    }

    private const UnixFileMode OwnerDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode OwnerFileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;

    private static ReleaseBundlePromotionResult BuildPromotionResult()
        => new(
            Version: "run-test",
            Channel: "preview",
            PublishedAt: new DateTimeOffset(2026, 7, 15, 12, 0, 0, TimeSpan.Zero),
            PromotedArtifactIds: [],
            DownloadsUrl: "https://chummer.run/downloads/",
            InstallDispatchUrls: [],
            DirectFileUrls: [],
            GenerationId: "generation-test",
            ActivationReceiptId: "activation-test",
            InventoryDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");

    private static ReleaseActivationIntent BuildActivationIntent(ReleaseBundlePromotionResult result)
    {
        byte[] targetPointerBytes = "test-target-pointer"u8.ToArray();
        return new ReleaseActivationIntent(
            Operation: "promotion",
            PreviousGenerationId: null,
            PreviousPointerSha256: null,
            GenerationId: result.GenerationId!,
            ActivationReceiptId: result.ActivationReceiptId!,
            ReleaseVersion: result.Version,
            Channel: result.Channel,
            PublishedAt: result.PublishedAt,
            InventoryDigest: result.InventoryDigest!,
            PointerSha256: $"sha256:{Convert.ToHexStringLower(SHA256.HashData(targetPointerBytes))}",
            PreparedAtUtc: DateTimeOffset.UtcNow,
            PreviousPointerBase64: null,
            TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        private readonly IConfiguration _configuration;

        public Fixture(int? completedReceiptRetentionSeconds = null)
        {
            _root = Path.Combine(Path.GetTempPath(), "release-upload-session-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            var values = new Dictionary<string, string?>
            {
                ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions"),
                ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_BYTES"] = "0",
                ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_FRACTION"] = "0"
            };
            if (completedReceiptRetentionSeconds is not null)
            {
                values["CHUMMER_RELEASE_UPLOAD_COMPLETED_RECEIPT_RETENTION_SECONDS"] =
                    completedReceiptRetentionSeconds.Value.ToString(
                        System.Globalization.CultureInfo.InvariantCulture);
            }
            _configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(values)
                .Build();
            Service = CreateService();
        }

        public ReleaseBundleUploadSessionService Service { get; }

        public string SessionsRoot => Path.Combine(_root, "sessions");

        public ReleaseBundleUploadSessionService CreateService()
            => new(_configuration, NullLogger<ReleaseBundleUploadSessionService>.Instance);

        public ReleaseBundleUploadSessionService CreateService(Action<string> flushDirectoryEntry)
            => new(
                _configuration,
                NullLogger<ReleaseBundleUploadSessionService>.Instance,
                flushDirectoryEntry);

        public void WriteSessionMetadata(string sessionId, ReleaseUploadSession session)
        {
            string metadataPath = Path.Combine(_root, "sessions", sessionId, "session.json");
            Directory.CreateDirectory(Path.GetDirectoryName(metadataPath)!);
            File.WriteAllText(metadataPath, System.Text.Json.JsonSerializer.Serialize(session));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
