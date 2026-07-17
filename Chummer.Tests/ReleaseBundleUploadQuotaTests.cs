using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBundleUploadQuotaTests
{
    private const string AuthorizationA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string AuthorizationB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    private const string AuthorizationC = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";

    [Fact]
    public async Task ChunkPayloadAcceptsExactLimitAndRejectsLimitPlusOne()
    {
        using Fixture fixture = new(Options(maxChunk: 4));
        ReleaseUploadSession accepted = fixture.Service.CreateSession();
        ReleaseUploadChunkResult stored = await fixture.Service.AppendChunkAsync(
            accepted.SessionId,
            "files/exact.bin",
            0,
            1,
            new MemoryStream(new byte[4]),
            CancellationToken.None);
        Assert.True(stored.Completed);

        ReleaseUploadSession rejected = fixture.Service.CreateSession();
        ReleaseUploadQuotaException exception = await Assert.ThrowsAsync<ReleaseUploadQuotaException>(() =>
            fixture.Service.AppendChunkAsync(
                rejected.SessionId,
                "files/too-large.bin",
                0,
                1,
                new MemoryStream(new byte[5]),
                CancellationToken.None));
        Assert.Equal(StatusCodes.Status413PayloadTooLarge, exception.StatusCode);
    }

    [Fact]
    public async Task TotalChunksAndCumulativeFileLimitsFailAtPlusOne()
    {
        using Fixture fixture = new(Options(maxChunk: 4, maxFile: 6, maxChunks: 2));
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.AppendChunkAsync(
            session.SessionId,
            "files/cumulative.bin",
            0,
            2,
            new MemoryStream(new byte[4]),
            CancellationToken.None);

        ReleaseUploadQuotaException fileLimit = await Assert.ThrowsAsync<ReleaseUploadQuotaException>(() =>
            fixture.Service.AppendChunkAsync(
                session.SessionId,
                "files/cumulative.bin",
                1,
                2,
                new MemoryStream(new byte[3]),
                CancellationToken.None));
        Assert.Equal(StatusCodes.Status413PayloadTooLarge, fileLimit.StatusCode);

        ReleaseUploadSession chunkCountSession = fixture.Service.CreateSession();
        ReleaseUploadQuotaException chunkCount = await Assert.ThrowsAsync<ReleaseUploadQuotaException>(() =>
            fixture.Service.AppendChunkAsync(
                chunkCountSession.SessionId,
                "files/chunk-count.bin",
                0,
                3,
                new MemoryStream(new byte[1]),
                CancellationToken.None));
        Assert.Equal(StatusCodes.Status413PayloadTooLarge, chunkCount.StatusCode);
    }

    [Fact]
    public async Task FileCountAllowsExactLimitAndRejectsNextLogicalPath()
    {
        using Fixture fixture = new(Options(maxFiles: 2));
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/one.bin",
            new MemoryStream(new byte[1]),
            CancellationToken.None);
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/two.bin",
            new MemoryStream(new byte[1]),
            CancellationToken.None);

        ReleaseUploadQuotaException exception = await Assert.ThrowsAsync<ReleaseUploadQuotaException>(() =>
            fixture.Service.WriteFileAsync(
                session.SessionId,
                "files/three.bin",
                new MemoryStream(new byte[1]),
                CancellationToken.None));
        Assert.Equal(StatusCodes.Status413PayloadTooLarge, exception.StatusCode);
    }

    [Fact]
    public async Task OverwritePeakIsChargedAndPriorTargetSurvivesRejection()
    {
        ReleaseUploadQuotaOptions initialOptions = Options(maxChunk: 80, maxFile: 100, maxSession: 200, maxShared: 300);
        using Fixture fixture = new(initialOptions);
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/preserved.bin",
            new MemoryStream(Enumerable.Repeat((byte)0x2a, 80).ToArray()),
            CancellationToken.None);

        ReleaseUploadQuotaOptions constrained = initialOptions with
        {
            MaxSessionBytes = 159,
            MaxSharedBytes = 300
        };
        ReleaseBundleUploadSessionService restarted = fixture.CreateService(constrained);
        ReleaseUploadQuotaException exception = await Assert.ThrowsAsync<ReleaseUploadQuotaException>(() =>
            restarted.WriteFileAsync(
                session.SessionId,
                "files/preserved.bin",
                new MemoryStream(Enumerable.Repeat((byte)0x7f, 80).ToArray()),
                CancellationToken.None));

        Assert.Equal(StatusCodes.Status413PayloadTooLarge, exception.StatusCode);
        Assert.All(await File.ReadAllBytesAsync(Path.Combine(session.BundleRoot, "files", "preserved.bin")),
            value => Assert.Equal((byte)0x2a, value));
    }

    [Fact]
    public async Task FailedSourceStreamLeavesNoPayloadOrStagingGrowth()
    {
        using Fixture fixture = new(Options());
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await Assert.ThrowsAsync<IOException>(() => fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/aborted.bin",
            new ThrowingReadStream(new byte[] { 1, 2, 3, 4 }, throwAfterBytes: 2),
            CancellationToken.None));

        Assert.False(File.Exists(Path.Combine(session.BundleRoot, "files", "aborted.bin")));
        string stagingRoot = Path.Combine(fixture.SessionsRoot, session.SessionId, "staging");
        Assert.Empty(Directory.EnumerateFileSystemEntries(stagingRoot));
    }

    [Fact]
    public async Task DirectOverwriteFlushFailureRestoresPriorTarget()
    {
        ReleaseUploadQuotaOptions options = Options();
        using Fixture fixture = new(options);
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/replace.bin",
            new MemoryStream("old"u8.ToArray()),
            CancellationToken.None);
        string targetParent = Path.Combine(session.BundleRoot, "files");
        bool failedOnce = false;
        ReleaseBundleUploadSessionService faulting = fixture.CreateService(
            options,
            directory =>
            {
                if (string.Equals(
                        Path.GetFullPath(directory),
                        Path.GetFullPath(targetParent),
                        StringComparison.Ordinal)
                    && !failedOnce)
                {
                    failedOnce = true;
                    throw new IOException("simulated target directory fsync failure");
                }
            });

        await Assert.ThrowsAsync<IOException>(() => faulting.WriteFileAsync(
            session.SessionId,
            "files/replace.bin",
            new MemoryStream("new"u8.ToArray()),
            CancellationToken.None));

        Assert.Equal("old", await File.ReadAllTextAsync(Path.Combine(targetParent, "replace.bin")));
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/replace.bin",
            new MemoryStream("new"u8.ToArray()),
            CancellationToken.None);
        Assert.Equal("new", await File.ReadAllTextAsync(Path.Combine(targetParent, "replace.bin")));
    }

    [Fact]
    public async Task FinalChunkFlushFailureRollsBackAndRemainsRetryable()
    {
        ReleaseUploadQuotaOptions options = Options();
        using Fixture fixture = new(options);
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/chunk-replace.bin",
            new MemoryStream("old"u8.ToArray()),
            CancellationToken.None);
        string targetParent = Path.Combine(session.BundleRoot, "files");
        ReleaseBundleUploadSessionService faulting = fixture.CreateService(
            options,
            directory =>
            {
                if (string.Equals(
                        Path.GetFullPath(directory),
                        Path.GetFullPath(targetParent),
                        StringComparison.Ordinal))
                {
                    throw new IOException("simulated target directory fsync failure");
                }
            });

        await Assert.ThrowsAsync<IOException>(() => faulting.AppendChunkAsync(
            session.SessionId,
            "files/chunk-replace.bin",
            0,
            1,
            new MemoryStream("new"u8.ToArray()),
            CancellationToken.None));
        Assert.Equal("old", await File.ReadAllTextAsync(Path.Combine(targetParent, "chunk-replace.bin")));

        ReleaseUploadChunkResult retried = await fixture.Service.AppendChunkAsync(
            session.SessionId,
            "files/chunk-replace.bin",
            0,
            1,
            new MemoryStream("new"u8.ToArray()),
            CancellationToken.None);

        Assert.True(retried.Completed);
        Assert.Equal("new", await File.ReadAllTextAsync(Path.Combine(targetParent, "chunk-replace.bin")));
    }

    [Fact]
    public async Task UserFileNamesThatLookLikeLegacyStateRemainOrdinaryFinalPayloads()
    {
        using Fixture fixture = new(Options());
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/ordinary.uploading",
            new MemoryStream(new byte[] { 1 }),
            CancellationToken.None);
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/ordinary.uploadstate.json",
            new MemoryStream(new byte[] { 2 }),
            CancellationToken.None);

        Assert.True(File.Exists(Path.Combine(session.BundleRoot, "files", "ordinary.uploading")));
        Assert.True(File.Exists(Path.Combine(session.BundleRoot, "files", "ordinary.uploadstate.json")));
    }

    [Fact]
    public async Task PathMetadataLimitIsEnforcedBeforeCreatingStagingState()
    {
        using Fixture fixture = new(Options());
        ReleaseUploadSession session = fixture.Service.CreateSession();
        string oversizedPath = "files/" + new string('a', 128) + ".bin";

        ReleaseUploadQuotaException exception = await Assert.ThrowsAsync<ReleaseUploadQuotaException>(() =>
            fixture.Service.WriteFileAsync(
                session.SessionId,
                oversizedPath,
                new MemoryStream(new byte[1]),
                CancellationToken.None));

        Assert.Equal(StatusCodes.Status413PayloadTooLarge, exception.StatusCode);
        Assert.Empty(Directory.EnumerateFileSystemEntries(
            Path.Combine(fixture.SessionsRoot, session.SessionId, "staging")));
    }

    [Fact]
    public async Task SymlinkedBundleParentsAreRejectedWithoutWritingOutsideSession()
    {
        if (!(OperatingSystem.IsLinux() || OperatingSystem.IsMacOS() || OperatingSystem.IsFreeBSD()))
        {
            return;
        }

        using Fixture fixture = new(Options());
        ReleaseUploadSession session = fixture.Service.CreateSession();
        string outside = Path.Combine(fixture.Root, "outside");
        Directory.CreateDirectory(outside);
        Directory.CreateSymbolicLink(Path.Combine(session.BundleRoot, "files"), outside);

        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/escape.bin",
            new MemoryStream(new byte[1]),
            CancellationToken.None));

        Assert.False(File.Exists(Path.Combine(outside, "escape.bin")));
    }

    [Fact]
    public void ActiveSessionFanoutEnforcesPerAuthorizationAndGlobalLimits()
    {
        ReleaseUploadQuotaOptions perAuthorizationOptions = Options(
            maxActive: 4,
            maxPerAuthorization: 2);
        using (Fixture fixture = new(perAuthorizationOptions))
        {
            _ = fixture.Service.CreateSession(AuthorizationA, singleUseAuthorization: false);
            _ = fixture.Service.CreateSession(AuthorizationA, singleUseAuthorization: false);
            ReleaseUploadQuotaException perAuthorization = Assert.Throws<ReleaseUploadQuotaException>(() =>
                fixture.Service.CreateSession(AuthorizationA, singleUseAuthorization: false));
            Assert.Equal(StatusCodes.Status429TooManyRequests, perAuthorization.StatusCode);
        }

        ReleaseUploadQuotaOptions globalOptions = Options(
            maxActive: 2,
            maxPerAuthorization: 2);
        using (Fixture fixture = new(globalOptions))
        {
            _ = fixture.Service.CreateSession(AuthorizationA, singleUseAuthorization: false);
            _ = fixture.Service.CreateSession(AuthorizationB, singleUseAuthorization: false);
            ReleaseUploadQuotaException global = Assert.Throws<ReleaseUploadQuotaException>(() =>
                fixture.Service.CreateSession(AuthorizationC, singleUseAuthorization: false));
            Assert.Equal(StatusCodes.Status429TooManyRequests, global.StatusCode);
        }
    }

    [Fact]
    public async Task TwoServiceInstancesCannotRacePastSharedLastByte()
    {
        ReleaseUploadQuotaOptions setupOptions = Options(
            maxChunk: 80,
            maxFile: 100,
            maxSession: 120,
            maxShared: 4096,
            maxActive: 4,
            maxPerAuthorization: 4);
        using Fixture fixture = new(setupOptions);
        ReleaseUploadSession first = fixture.Service.CreateSession();
        ReleaseUploadSession second = fixture.Service.CreateSession();
        ReleaseUploadQuotaOptions raceOptions = setupOptions with
        {
            // The shared quota charges bundle/staging bytes, not durable session
            // metadata. One 80-byte payload plus its small path binding fits; two do not.
            MaxSharedBytes = 120
        };
        ReleaseBundleUploadSessionService firstWriter = fixture.CreateService(raceOptions);
        ReleaseBundleUploadSessionService secondWriter = fixture.CreateService(raceOptions);

        Task firstWrite = firstWriter.WriteFileAsync(
            first.SessionId,
            "files/first.bin",
            new MemoryStream(new byte[80]),
            CancellationToken.None);
        Task secondWrite = secondWriter.WriteFileAsync(
            second.SessionId,
            "files/second.bin",
            new MemoryStream(new byte[80]),
            CancellationToken.None);
        Exception? observed = await Record.ExceptionAsync(() => Task.WhenAll(firstWrite, secondWrite));

        Assert.NotNull(observed);
        int finalFiles = Directory.EnumerateFiles(
                fixture.SessionsRoot,
                "*.bin",
                SearchOption.AllDirectories)
            .Count();
        Assert.Equal(1, finalFiles);
    }

    [Fact]
    public async Task FreeSpaceReserveAcceptsBoundaryAndRejectsOneByteMore()
    {
        ReleaseUploadQuotaOptions options = Options(maxChunk: 81, maxFile: 100, maxSession: 200, maxShared: 300) with
        {
            MinimumFreeBytes = 20,
            MinimumFreeFraction = 0
        };
        using Fixture fixture = new(options, new FixedStorageProbe(total: 100, available: 100));
        ReleaseUploadSession accepted = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            accepted.SessionId,
            "files/exact-reserve.bin",
            new MemoryStream(new byte[80]),
            CancellationToken.None);

        ReleaseUploadSession rejected = fixture.Service.CreateSession();
        ReleaseUploadQuotaException exception = await Assert.ThrowsAsync<ReleaseUploadQuotaException>(() =>
            fixture.Service.WriteFileAsync(
                rejected.SessionId,
                "files/reserve-plus-one.bin",
                new MemoryStream(new byte[81]),
                CancellationToken.None));
        Assert.Equal(StatusCodes.Status507InsufficientStorage, exception.StatusCode);
    }

    [Fact]
    public void MalformedStorageCapacityProbeFailsClosed()
    {
        using Fixture fixture = new(
            Options(),
            new FixedStorageProbe(total: 100, available: 101));

        ReleaseUploadQuotaException exception = Assert.Throws<ReleaseUploadQuotaException>(() =>
            fixture.Service.CreateSession());

        Assert.Equal(StatusCodes.Status507InsufficientStorage, exception.StatusCode);
    }

    [Fact]
    public async Task PublicationReadinessFailsWhenDestinationIsMissingButUploadStorageIsHealthy()
    {
        ReleaseUploadQuotaOptions options = Options(
            maxChunk: 4,
            maxFile: 10,
            maxSession: 80,
            maxShared: 160) with
        {
            MinimumFreeBytes = 20,
            MinimumFreeFraction = 0
        };
        using Fixture fixture = new(options, new FixedStorageProbe(total: 100, available: 100));
        Assert.True(fixture.Service.EvaluateStorageReadiness(CancellationToken.None).Ready);
        string missingDestination = Path.Combine(fixture.Root, "missing-downloads");
        var publication = new ReleaseUploadStoragePublicationReadinessProbe(fixture.Service);

        ReleaseShelfPublicationReadinessProbeResult result = await publication.EvaluateAsync(
            ReleaseShelfSnapshot.Legacy(missingDestination),
            CancellationToken.None);

        Assert.False(result.Ready);
        Assert.Equal("publication_destination_unavailable", result.Code);
    }

    [Fact]
    public async Task PublicationReadinessReservesOneFullSessionOnDestinationVolume()
    {
        ReleaseUploadQuotaOptions options = Options(
            maxChunk: 4,
            maxFile: 10,
            maxSession: 80,
            maxShared: 160) with
        {
            MinimumFreeBytes = 20,
            MinimumFreeFraction = 0
        };
        long requiredAvailable = 20 + 80 + 32L * ReleaseUploadQuotaOptions.MiB;
        using Fixture fixture = new(options, new FixedStorageProbe(
            total: 100L * ReleaseUploadQuotaOptions.MiB,
            available: requiredAvailable - 1));
        Assert.True(fixture.Service.EvaluateStorageReadiness(CancellationToken.None).Ready);
        string destination = Path.Combine(fixture.Root, "downloads");
        Directory.CreateDirectory(destination);
        var publication = new ReleaseUploadStoragePublicationReadinessProbe(fixture.Service);

        ReleaseShelfPublicationReadinessProbeResult result = await publication.EvaluateAsync(
            ReleaseShelfSnapshot.Legacy(destination),
            CancellationToken.None);

        Assert.False(result.Ready);
        Assert.Equal("publication_destination_capacity_exhausted", result.Code);
    }

    [Fact]
    public async Task PublicationDestinationCapacityBoundaryIsAdmitted()
    {
        ReleaseUploadQuotaOptions options = Options(
            maxChunk: 4,
            maxFile: 10,
            maxSession: 80,
            maxShared: 160) with
        {
            MinimumFreeBytes = 20,
            MinimumFreeFraction = 0
        };
        long requiredAvailable = 20 + 80 + 32L * ReleaseUploadQuotaOptions.MiB;
        using Fixture fixture = new(options, new FixedStorageProbe(
            total: 100L * ReleaseUploadQuotaOptions.MiB,
            available: requiredAvailable));
        string destination = Path.Combine(fixture.Root, "downloads");
        Directory.CreateDirectory(destination);
        var publication = new ReleaseUploadStoragePublicationReadinessProbe(fixture.Service);

        ReleaseShelfPublicationReadinessProbeResult result = await publication.EvaluateAsync(
            ReleaseShelfSnapshot.Legacy(destination),
            CancellationToken.None);

        Assert.True(result.Ready);
        Assert.Equal("ready", result.Code);
    }

    [Fact]
    public async Task PublicationReadinessChargesActiveInventoryLargerThanIncomingLimit()
    {
        ReleaseUploadQuotaOptions options = Options(
            maxChunk: 4,
            maxFile: 10,
            maxSession: 80,
            maxShared: 160) with
        {
            MinimumFreeBytes = 20,
            MinimumFreeFraction = 0
        };
        long available = 20 + 80 + 32L * ReleaseUploadQuotaOptions.MiB + 10;
        using Fixture fixture = new(options, new FixedStorageProbe(
            total: 100L * ReleaseUploadQuotaOptions.MiB,
            available: available));
        string destination = Path.Combine(fixture.Root, "downloads");
        Directory.CreateDirectory(destination);
        ReleaseShelfSnapshot snapshot = ActiveSnapshot(destination, activeBytes: 120);
        var publication = new ReleaseUploadStoragePublicationReadinessProbe(fixture.Service);

        ReleaseShelfPublicationReadinessProbeResult result = await publication.EvaluateAsync(
            snapshot,
            CancellationToken.None);

        Assert.False(result.Ready);
        Assert.Equal("publication_destination_capacity_exhausted", result.Code);
    }

    [Fact]
    public async Task CompletionDestinationAdmissionUsesMeasuredBundleAtExactBoundary()
    {
        ReleaseUploadQuotaOptions options = Options(
            maxChunk: 4,
            maxFile: 10,
            maxSession: 80,
            maxShared: 160) with
        {
            MinimumFreeBytes = 20,
            MinimumFreeFraction = 0
        };
        long available = 20 + 4 + 32L * ReleaseUploadQuotaOptions.MiB;
        using Fixture fixture = new(options, new FixedStorageProbe(
            total: 100L * ReleaseUploadQuotaOptions.MiB,
            available: available));
        string destination = Path.Combine(fixture.Root, "downloads");
        Directory.CreateDirectory(destination);
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "a.bin",
            new MemoryStream(new byte[4]),
            CancellationToken.None);

        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
            fixture.Service.BeginCompletion(
                session.SessionId,
                "0000000000000000000000000000000000000000000000000000000000000000");
        ReleaseUploadStorageReadiness result = completion.EvaluatePublicationDestinationReadiness(
            ReleaseShelfSnapshot.Legacy(destination),
            CancellationToken.None);

        Assert.True(result.Ready);
        Assert.Equal("ready", result.Code);
    }

    [Fact]
    public async Task CompletionInventoryOverflowFailsClosedWithoutThrowing()
    {
        using Fixture fixture = new(Options(), new FixedStorageProbe(long.MaxValue, long.MaxValue));
        string destination = Path.Combine(fixture.Root, "downloads");
        Directory.CreateDirectory(destination);
        ReleaseShelfSnapshot snapshot = ActiveSnapshot(
            destination,
            activeBytes: long.MaxValue,
            secondActiveBytes: 1);
        ReleaseUploadSession session = fixture.Service.CreateSession();
        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "a.bin",
            new MemoryStream(new byte[1]),
            CancellationToken.None);

        using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
            fixture.Service.BeginCompletion(
                session.SessionId,
                "0000000000000000000000000000000000000000000000000000000000000000");
        ReleaseUploadStorageReadiness result = completion.EvaluatePublicationDestinationReadiness(
            snapshot,
            CancellationToken.None);

        Assert.False(result.Ready);
        Assert.Equal("publication_destination_capacity_exhausted", result.Code);
    }

    private static ReleaseShelfSnapshot ActiveSnapshot(
        string downloadsRoot,
        long activeBytes,
        long? secondActiveBytes = null)
    {
        var inventory = new Dictionary<string, ReleaseShelfInventoryEntry>(StringComparer.Ordinal)
        {
            ["files/active.bin"] = new(
                "files/active.bin",
                new string('a', 64),
                activeBytes)
        };
        if (secondActiveBytes is not null)
        {
            inventory["files/second.bin"] = new ReleaseShelfInventoryEntry(
                "files/second.bin",
                new string('b', 64),
                secondActiveBytes.Value);
        }

        return ReleaseShelfSnapshot.Active(
            downloadsRoot,
            downloadsRoot,
            "generation-test",
            "run-test",
            "preview",
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow,
            "receipt-test",
            new string('c', 64),
            new string('d', 64),
            new string('e', 64),
            new string('f', 64),
            inventory,
            explicitGeneration: false);
    }

    private static ReleaseUploadQuotaOptions Options(
        long maxChunk = 128,
        long maxFile = 256,
        int maxChunks = 8,
        int maxFiles = 8,
        long maxSession = 1024,
        long maxShared = 2048,
        int maxActive = 8,
        int maxPerAuthorization = 2)
        => new()
        {
            MaxChunkBytes = maxChunk,
            MaxRequestBytes = maxChunk + 64,
            MaxPathBytes = 128,
            MaxFileBytes = maxFile,
            MaxChunksPerFile = maxChunks,
            MaxFilesPerSession = maxFiles,
            MaxSessionBytes = maxSession,
            MaxActiveSessions = maxActive,
            MaxActiveSessionsPerAuthorization = maxPerAuthorization,
            MaxSharedBytes = maxShared,
            MinimumFreeBytes = 0,
            MinimumFreeFraction = 0,
            JanitorInterval = TimeSpan.FromMinutes(1),
            CompletedReceiptRetention = TimeSpan.FromMinutes(1)
        };

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        private readonly IConfiguration _configuration;
        private readonly IReleaseUploadStorageProbe _probe;

        public Fixture(
            ReleaseUploadQuotaOptions options,
            IReleaseUploadStorageProbe? probe = null)
        {
            options.Validate();
            _root = Path.Combine(Path.GetTempPath(), "release-upload-quota-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            _configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions")
                })
                .Build();
            _probe = probe ?? new FixedStorageProbe(long.MaxValue / 4, long.MaxValue / 4);
            Service = CreateService(options);
        }

        public ReleaseBundleUploadSessionService Service { get; }
        public string Root => _root;
        public string SessionsRoot => Path.Combine(_root, "sessions");

        public ReleaseBundleUploadSessionService CreateService(ReleaseUploadQuotaOptions options)
            => new(
                _configuration,
                NullLogger<ReleaseBundleUploadSessionService>.Instance,
                options,
                _probe);

        public ReleaseBundleUploadSessionService CreateService(
            ReleaseUploadQuotaOptions options,
            Action<string> flushDirectoryEntry)
            => new(
                _configuration,
                NullLogger<ReleaseBundleUploadSessionService>.Instance,
                options,
                _probe,
                flushDirectoryEntry);

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class FixedStorageProbe(long total, long available) : IReleaseUploadStorageProbe
    {
        public ReleaseUploadStorageSpace GetSpace(string path) => new(total, available);
    }

    private sealed class ThrowingReadStream : Stream
    {
        private readonly byte[] _bytes;
        private readonly int _throwAfterBytes;
        private int _position;

        public ThrowingReadStream(byte[] bytes, int throwAfterBytes)
        {
            _bytes = bytes;
            _throwAfterBytes = throwAfterBytes;
        }

        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => _position; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count)
            => Read(buffer.AsSpan(offset, count));

        public override int Read(Span<byte> buffer)
        {
            if (_position >= _throwAfterBytes)
            {
                throw new IOException("simulated source failure");
            }

            int count = Math.Min(buffer.Length, _throwAfterBytes - _position);
            _bytes.AsSpan(_position, count).CopyTo(buffer);
            _position += count;
            return count;
        }

        public override ValueTask<int> ReadAsync(
            Memory<byte> buffer,
            CancellationToken cancellationToken = default)
            => ValueTask.FromResult(Read(buffer.Span));

        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}
