using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadRequestGateMiddlewareTests
{
    [Fact]
    public void DirectBundleUploadCannotBeEnabledByConfiguration()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED"] = "true"
            })
            .Build();

        Assert.Throws<InvalidOperationException>(() =>
            ReleaseUploadQuotaOptions.FromConfiguration(configuration));
    }

    [Fact]
    public void FreeSpaceReserveCanBeExplicitlyDisabledForIsolatedTestStorage()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_BYTES"] = "0"
            })
            .Build();

        ReleaseUploadQuotaOptions options = ReleaseUploadQuotaOptions.FromConfiguration(configuration);

        Assert.Equal(0, options.MinimumFreeBytes);
    }

    [Fact]
    public void FreeSpaceReserveRejectsNonFiniteFractions()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_FRACTION"] = "NaN"
            })
            .Build();

        Assert.Throws<InvalidOperationException>(() =>
            ReleaseUploadQuotaOptions.FromConfiguration(configuration));
    }

    [Fact]
    public async Task MissingBearerIsRejectedBeforeAnyBodyRead()
    {
        using Fixture fixture = new();
        CountingStream body = fixture.PrepareRequest(
            "/api/internal/releases/upload-sessions/not-a-guid/files",
            contentLength: 16);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status401Unauthorized, fixture.Context.Response.StatusCode);
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
    }

    [Fact]
    public async Task AuthorityAdvanceIsAuthenticatedByTheReleaseMutationGate()
    {
        using Fixture fixture = new();
        CountingStream anonymousBody = fixture.PrepareRequest(
            "/api/internal/releases/generations/generation-a/authority-advances",
            contentLength: 16);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status401Unauthorized, fixture.Context.Response.StatusCode);
        Assert.Equal(0, anonymousBody.ReadCount);
        Assert.False(fixture.NextCalled);

        fixture.Reset();
        CountingStream authenticatedBody = fixture.PrepareRequest(
            "/api/internal/releases/generations/generation-a/authority-advances",
            contentLength: 16,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status200OK, fixture.Context.Response.StatusCode);
        Assert.Equal(0, authenticatedBody.ReadCount);
        Assert.True(fixture.NextCalled);
        Assert.NotNull(ReleaseUploadRequestGateMiddleware.RequireAuthorization(fixture.Context));
    }

    [Fact]
    public async Task CandidateImportAuthorityCannotAdvanceReleaseAuthorityBeforeBodyRead()
    {
        using var snapshot = new ReleaseUploadSnapshotAuthorityTests.SnapshotFixture();
        snapshot.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            snapshot.Authority.Load().Candidate);
        ReleaseUploadQuotaOptions options = ReleaseUploadQuotaOptions.FromConfiguration(
            snapshot.Configuration);
        var admission = new ReleaseUploadAdmissionService(snapshot.Configuration, options);
        bool nextCalled = false;
        var middleware = new ReleaseUploadRequestGateMiddleware(context =>
        {
            nextCalled = true;
            context.Response.StatusCode = StatusCodes.Status200OK;
            return Task.CompletedTask;
        });
        var context = new DefaultHttpContext();
        context.Response.Body = new MemoryStream();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path =
            "/api/internal/releases/generations/generation-a/authority-advances";
        context.Request.ContentType = "application/json";
        context.Request.ContentLength = 16;
        context.Request.Headers.Authorization = "Bearer fleet-test-token";
        context.Request.Headers[
            ReleaseUploadAuthorizationEvaluator.CandidateManifestSha256Header] =
            candidate.Candidate.CanonicalManifestSha256;
        context.Request.Headers[
            ReleaseUploadAuthorizationEvaluator.CandidateInventorySha256Header] =
            candidate.Candidate.InventorySha256;
        context.Request.Headers[
            ReleaseUploadAuthorizationEvaluator.CandidateBundleIdentitySha256Header] =
            candidate.Candidate.BundleIdentitySha256;
        using var body = new CountingStream(new byte[256]);
        context.Request.Body = body;

        await middleware.InvokeAsync(context, snapshot.Evaluator, admission, options);

        Assert.Equal(StatusCodes.Status403Forbidden, context.Response.StatusCode);
        Assert.Equal(0, body.ReadCount);
        Assert.False(nextCalled);
        Assert.Null(ReleaseUploadRequestGateMiddleware.RequireAuthorization(context));
    }

    [Fact]
    public async Task AuthorityAdvanceRequiresKnownBoundedLengthBeforeBodyRead()
    {
        using Fixture fixture = new();
        CountingStream unknownBody = fixture.PrepareRequest(
            "/api/internal/releases/generations/generation-a/authority-advances",
            contentLength: null,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status411LengthRequired, fixture.Context.Response.StatusCode);
        Assert.Equal(0, unknownBody.ReadCount);
        Assert.False(fixture.NextCalled);

        fixture.Reset();
        CountingStream oversizedBody = fixture.PrepareRequest(
            "/api/internal/releases/generations/generation-a/authority-advances",
            contentLength: ReleaseAuthorityRevisionStore.MaximumAdvanceRequestBodyBytes + 1,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status413PayloadTooLarge, fixture.Context.Response.StatusCode);
        Assert.Equal(0, oversizedBody.ReadCount);
        Assert.False(fixture.NextCalled);
    }

    [Fact]
    public async Task AuthorityAdvanceUsesAuthenticatedAdmissionLease()
    {
        using Fixture fixture = new(maxAdmissions: 1);
        using ReleaseUploadAdmissionLease held = Assert.IsType<ReleaseUploadAdmissionLease>(
            fixture.Admission.TryAcquire(fixture.InternalAuthorizationBinding));
        CountingStream body = fixture.PrepareRequest(
            "/api/internal/releases/generations/generation-a/authority-advances",
            contentLength: 16,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status429TooManyRequests, fixture.Context.Response.StatusCode);
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
    }

    [Fact]
    public async Task DisabledDirectBundleIsRejectedBeforeLengthCheckOrBodyRead()
    {
        using Fixture fixture = new();
        CountingStream body = fixture.PrepareRequest(
            "/api/internal/releases/bundles",
            contentLength: null,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status409Conflict, fixture.Context.Response.StatusCode);
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
    }

    [Fact]
    public async Task UnknownAndOversizedLengthsAreRejectedBeforeBodyRead()
    {
        using Fixture fixture = new();
        CountingStream unknownBody = fixture.PrepareRequest(
            $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/chunks",
            contentLength: null,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status411LengthRequired, fixture.Context.Response.StatusCode);
        Assert.Equal(0, unknownBody.ReadCount);

        fixture.Reset();
        CountingStream oversizedBody = fixture.PrepareRequest(
            $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/files",
            contentLength: fixture.Options.MaxRequestBytes + 1,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status413PayloadTooLarge, fixture.Context.Response.StatusCode);
        Assert.Equal(0, oversizedBody.ReadCount);
    }

    [Fact]
    public async Task AuthenticatedBoundedCallerReachesParserUnderAdmissionLease()
    {
        using Fixture fixture = new();
        CountingStream body = fixture.PrepareRequest(
            $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/files",
            contentLength: 16,
            authenticated: true);

        await fixture.InvokeAsync(readBodyInNext: true);

        Assert.True(fixture.NextCalled);
        Assert.Equal(StatusCodes.Status200OK, fixture.Context.Response.StatusCode);
        Assert.Equal(1, body.ReadCount);
    }

    [Fact]
    public async Task ExactRequestLimitAndExistingFiftyMiBPublisherAreAdmitted()
    {
        using Fixture fixture = new(
            maxAdmissions: 2,
            maxChunkBytes: 64L * ReleaseUploadQuotaOptions.MiB,
            maxRequestBytes: 65L * ReleaseUploadQuotaOptions.MiB);
        CountingStream exactBody = fixture.PrepareRequest(
            $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/files",
            contentLength: fixture.Options.MaxRequestBytes,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.True(fixture.NextCalled);
        Assert.Equal(0, exactBody.ReadCount);

        fixture.Reset();
        CountingStream publisherBody = fixture.PrepareRequest(
            $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/chunks",
            contentLength: 50L * ReleaseUploadQuotaOptions.MiB,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.True(fixture.NextCalled);
        Assert.Equal(0, publisherBody.ReadCount);
    }

    [Fact]
    public async Task AnonymousCallerCannotOccupyOrWaitBehindAuthenticatedAdmissionSlots()
    {
        using Fixture fixture = new(maxAdmissions: 1);
        using ReleaseUploadAdmissionLease held = Assert.IsType<ReleaseUploadAdmissionLease>(
            fixture.Admission.TryAcquire(fixture.InternalAuthorizationBinding));
        CountingStream body = fixture.PrepareRequest(
            $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/chunks",
            contentLength: 16,
            authenticated: false);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status401Unauthorized, fixture.Context.Response.StatusCode);
        Assert.Equal(0, body.ReadCount);
    }

    [Fact]
    public async Task AuthenticatedCallerGets429WithoutBodyReadWhenAdmissionIsFull()
    {
        using Fixture fixture = new(maxAdmissions: 1);
        using ReleaseUploadAdmissionLease held = Assert.IsType<ReleaseUploadAdmissionLease>(
            fixture.Admission.TryAcquire(fixture.InternalAuthorizationBinding));
        CountingStream body = fixture.PrepareRequest(
            $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/files",
            contentLength: 16,
            authenticated: true);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status429TooManyRequests, fixture.Context.Response.StatusCode);
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
    }

    private sealed class Fixture : IDisposable
    {
        private const string InternalToken = "fleet-test-token";
        private readonly string _root;
        private readonly ReleaseUploadSnapshotAuthorityTests.SnapshotFixture _snapshot;
        private readonly IConfiguration _configuration;
        private readonly ReleaseUploadAuthorizationEvaluator _authorization;
        private readonly ReleaseUploadRequestGateMiddleware _middleware;

        public Fixture(
            int maxAdmissions = 2,
            long maxChunkBytes = 64,
            long maxRequestBytes = 128)
        {
            _root = Path.Combine(Path.GetTempPath(), "release-upload-gate-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            _configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["FLEET_INTERNAL_API_TOKEN"] = InternalToken,
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions"),
                    ["CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED"] = "false"
                })
                .Build();
            Options = new ReleaseUploadQuotaOptions
            {
                MaxChunkBytes = maxChunkBytes,
                MaxRequestBytes = maxRequestBytes,
                MaxPathBytes = 64,
                MaxFileBytes = Math.Max(512, maxChunkBytes),
                MaxChunksPerFile = 8,
                MaxFilesPerSession = 8,
                MaxSessionBytes = Math.Max(1024, maxChunkBytes),
                MaxActiveSessions = maxAdmissions,
                MaxActiveSessionsPerAuthorization = maxAdmissions,
                MaxSharedBytes = Math.Max(2048, maxChunkBytes),
                MinimumFreeBytes = 0,
                MinimumFreeFraction = 0,
                JanitorInterval = TimeSpan.FromMinutes(1),
                CompletedReceiptRetention = TimeSpan.FromMinutes(1)
            };
            Options.Validate();
            _snapshot = new ReleaseUploadSnapshotAuthorityTests.SnapshotFixture();
            _snapshot.Publish("pass");
            _authorization = _snapshot.Evaluator;
            Admission = new ReleaseUploadAdmissionService(_configuration, Options);
            _middleware = new ReleaseUploadRequestGateMiddleware(async context =>
            {
                NextCalled = true;
                if (ReadBodyInNext)
                {
                    byte[] one = new byte[1];
                    _ = await context.Request.Body.ReadAsync(one.AsMemory());
                }

                context.Response.StatusCode = StatusCodes.Status200OK;
            });
            Reset();

            var seedContext = new DefaultHttpContext();
            seedContext.Request.Method = HttpMethods.Post;
            seedContext.Request.Path = "/api/internal/releases/upload-sessions";
            seedContext.Request.Headers.Authorization = $"Bearer {InternalToken}";
            InternalAuthorizationBinding = Assert.IsType<ReleaseUploadAuthorizationContext>(
                _authorization.Evaluate(seedContext.Request)).AuthorizationBinding;
        }

        public DefaultHttpContext Context { get; private set; } = null!;
        public ReleaseUploadQuotaOptions Options { get; }
        public ReleaseUploadAdmissionService Admission { get; }
        public string InternalAuthorizationBinding { get; }
        public bool NextCalled { get; private set; }
        private bool ReadBodyInNext { get; set; }

        public void Reset()
        {
            Context = new DefaultHttpContext();
            Context.Response.Body = new MemoryStream();
            NextCalled = false;
            ReadBodyInNext = false;
        }

        public CountingStream PrepareRequest(string path, long? contentLength, bool authenticated = false)
        {
            Context.Request.Method = HttpMethods.Post;
            Context.Request.Path = path;
            Context.Request.ContentType = "multipart/form-data; boundary=bounded-test";
            Context.Request.ContentLength = contentLength;
            if (authenticated)
            {
                Context.Request.Headers.Authorization = $"Bearer {InternalToken}";
            }

            var body = new CountingStream(new byte[256]);
            Context.Request.Body = body;
            return body;
        }

        public async Task InvokeAsync(bool readBodyInNext = false)
        {
            ReadBodyInNext = readBodyInNext;
            await _middleware.InvokeAsync(Context, _authorization, Admission, Options);
        }

        public void Dispose()
        {
            Context.Response.Body.Dispose();
            _snapshot.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class CountingStream : MemoryStream
    {
        private bool _suppressNestedReadCount;

        public CountingStream(byte[] bytes)
            : base(bytes)
        {
        }

        public int ReadCount { get; private set; }

        public override int Read(byte[] buffer, int offset, int count)
        {
            if (!_suppressNestedReadCount)
            {
                ReadCount++;
            }
            return base.Read(buffer, offset, count);
        }

        public override int Read(Span<byte> buffer)
        {
            if (!_suppressNestedReadCount)
            {
                ReadCount++;
            }
            return base.Read(buffer);
        }

        public override ValueTask<int> ReadAsync(
            Memory<byte> buffer,
            CancellationToken cancellationToken = default)
        {
            ReadCount++;
            cancellationToken.ThrowIfCancellationRequested();
            _suppressNestedReadCount = true;
            try
            {
                return ValueTask.FromResult(base.Read(buffer.Span));
            }
            finally
            {
                _suppressNestedReadCount = false;
            }
        }
    }
}
