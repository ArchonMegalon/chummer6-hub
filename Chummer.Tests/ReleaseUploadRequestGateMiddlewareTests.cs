using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
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
        context.Request.Headers[
            "X-Chummer-Release-Exact-Incoming-Scope"] =
            ReleaseUploadSnapshotAuthorityService.CandidateExactIncomingDesktopScope;
        using var body = new CountingStream(new byte[256]);
        context.Request.Body = body;

        await middleware.InvokeAsync(context, snapshot.Evaluator, admission, options);

        Assert.Equal(StatusCodes.Status403Forbidden, context.Response.StatusCode);
        Assert.Equal(0, body.ReadCount);
        Assert.False(nextCalled);
        Assert.Null(ReleaseUploadRequestGateMiddleware.RequireAuthorization(context));
    }

    [Fact]
    public async Task CandidateImportAuthorityCanStageButCannotInvokeLegacyCompletion()
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

        DefaultHttpContext Request(string operation)
        {
            var context = new DefaultHttpContext();
            context.Response.Body = new MemoryStream();
            context.Request.Method = HttpMethods.Post;
            context.Request.Path =
                $"/api/internal/releases/upload-sessions/{Guid.NewGuid():N}/{operation}";
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
            context.Request.Headers[
                "X-Chummer-Release-Exact-Incoming-Scope"] =
                ReleaseUploadSnapshotAuthorityService.CandidateExactIncomingDesktopScope;
            return context;
        }

        DefaultHttpContext stage = Request("stage");
        await middleware.InvokeAsync(stage, snapshot.Evaluator, admission, options);

        Assert.Equal(StatusCodes.Status200OK, stage.Response.StatusCode);
        Assert.True(nextCalled);
        Assert.NotNull(ReleaseUploadRequestGateMiddleware.RequireAuthorization(stage));

        nextCalled = false;
        DefaultHttpContext complete = Request("complete");
        await middleware.InvokeAsync(complete, snapshot.Evaluator, admission, options);

        Assert.Equal(StatusCodes.Status403Forbidden, complete.Response.StatusCode);
        Assert.False(nextCalled);
        Assert.Null(ReleaseUploadRequestGateMiddleware.RequireAuthorization(complete));
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

    [Fact]
    public async Task RotatedTicketReturnsExactBoundUnauthorizedProofWithoutMutation()
    {
        const string nonce =
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        using TicketProofFixture fixture = new(currentEpoch: "release-epoch-b");
        string oldTicket = fixture.IssueTicket("release-epoch-a");
        CountingStream body = fixture.PrepareRequest(oldTicket, nonce);

        await fixture.InvokeAsync();

        string expectedNonceSha256 = HashAscii(nonce);
        string expectedEpochSha256 = HashUtf8("release-epoch-b");
        Assert.Equal(StatusCodes.Status401Unauthorized, fixture.Context.Response.StatusCode);
        Assert.Equal("application/json; charset=utf-8", fixture.Context.Response.ContentType);
        Assert.Equal("no-store", fixture.Context.Response.Headers.CacheControl.ToString());
        Assert.Equal("no-cache", fixture.Context.Response.Headers.Pragma.ToString());
        Assert.Equal("0", fixture.Context.Response.Headers.Expires.ToString());
        Assert.Equal("Bearer", fixture.Context.Response.Headers.WWWAuthenticate.ToString());
        Assert.Equal(
            $$"""{"contractName":"chummer.release-upload-ticket-revocation-proof/v1","status":"pass","ticketAccepted":false,"nonceSha256":"{{expectedNonceSha256}}","revocationEpochSha256":"{{expectedEpochSha256}}"}""",
            await fixture.ReadResponseBodyAsync());
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
        Assert.Null(ReleaseUploadRequestGateMiddleware.RequireAuthorization(fixture.Context));
        Assert.False(Directory.Exists(fixture.SessionRoot));
    }

    [Fact]
    public async Task CurrentTicketReturnsDeterministicBoundSuccessWithoutMutation()
    {
        const string nonce =
            "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";
        using TicketProofFixture fixture = new(currentEpoch: "release-epoch-b");
        string currentTicket = fixture.IssueTicket("release-epoch-b");
        CountingStream body = fixture.PrepareRequest(currentTicket, nonce);

        await fixture.InvokeAsync();

        string expectedNonceSha256 = HashAscii(nonce);
        string expectedEpochSha256 = HashUtf8("release-epoch-b");
        Assert.Equal(StatusCodes.Status200OK, fixture.Context.Response.StatusCode);
        Assert.Equal("application/json; charset=utf-8", fixture.Context.Response.ContentType);
        Assert.Equal("no-store", fixture.Context.Response.Headers.CacheControl.ToString());
        Assert.Equal("no-cache", fixture.Context.Response.Headers.Pragma.ToString());
        Assert.Equal("0", fixture.Context.Response.Headers.Expires.ToString());
        Assert.False(fixture.Context.Response.Headers.ContainsKey("WWW-Authenticate"));
        Assert.Equal(
            $$"""{"contractName":"chummer.release-upload-ticket-revocation-proof/v1","status":"pass","ticketAccepted":true,"nonceSha256":"{{expectedNonceSha256}}","revocationEpochSha256":"{{expectedEpochSha256}}"}""",
            await fixture.ReadResponseBodyAsync());
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
        Assert.Null(ReleaseUploadRequestGateMiddleware.RequireAuthorization(fixture.Context));
        Assert.False(Directory.Exists(fixture.SessionRoot));
    }

    [Fact]
    public async Task FleetTokenIsNotAcceptedAsAReleaseUploadTicketProof()
    {
        const string nonce =
            "1111111111111111111111111111111111111111111111111111111111111111";
        using TicketProofFixture fixture = new(currentEpoch: "release-epoch-b");
        CountingStream body = fixture.PrepareRequest(TicketProofFixture.InternalToken, nonce);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status401Unauthorized, fixture.Context.Response.StatusCode);
        Assert.Contains(
            "\"ticketAccepted\":false",
            await fixture.ReadResponseBodyAsync(),
            StringComparison.Ordinal);
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
        Assert.False(Directory.Exists(fixture.SessionRoot));
    }

    [Theory]
    [InlineData("")]
    [InlineData("ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789")]
    [InlineData("0123456789abcdef")]
    public async Task InvalidNonceIsRejectedWithoutTicketEvaluationOrMutation(string nonce)
    {
        using TicketProofFixture fixture = new(currentEpoch: "release-epoch-b");
        string currentTicket = fixture.IssueTicket("release-epoch-b");
        CountingStream body = fixture.PrepareRequest(currentTicket, nonce);

        await fixture.InvokeAsync();

        Assert.Equal(StatusCodes.Status400BadRequest, fixture.Context.Response.StatusCode);
        Assert.Equal("no-store", fixture.Context.Response.Headers.CacheControl.ToString());
        Assert.Equal("no-cache", fixture.Context.Response.Headers.Pragma.ToString());
        Assert.Equal(0, body.ReadCount);
        Assert.False(fixture.NextCalled);
        Assert.False(Directory.Exists(fixture.SessionRoot));
    }

    private static string HashAscii(string value)
        => Convert.ToHexStringLower(SHA256.HashData(Encoding.ASCII.GetBytes(value)));

    private static string HashUtf8(string value)
        => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private sealed class TicketProofFixture : IDisposable
    {
        public const string InternalToken = "fleet-test-token";
        private readonly string _root;
        private readonly IDataProtectionProvider _provider;
        private readonly ReleaseUploadAuthorizationEvaluator _authorization;
        private readonly ReleaseUploadAdmissionService _admission;
        private readonly ReleaseUploadQuotaOptions _options;
        private readonly ReleaseUploadRequestGateMiddleware _middleware;

        public TicketProofFixture(string currentEpoch)
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                "release-upload-ticket-proof-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            SessionRoot = Path.Combine(_root, "sessions");
            _provider = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(_root, "keys")));
            IConfiguration configuration = CreateConfiguration(currentEpoch);
            var ticketService = new ReleaseUploadTicketService(_provider, configuration);
            _authorization = new ReleaseUploadAuthorizationEvaluator(
                configuration,
                ticketService);
            _options = new ReleaseUploadQuotaOptions
            {
                MaxChunkBytes = 64,
                MaxRequestBytes = 128,
                MaxPathBytes = 64,
                MaxFileBytes = 512,
                MaxChunksPerFile = 8,
                MaxFilesPerSession = 8,
                MaxSessionBytes = 1024,
                MaxActiveSessions = 1,
                MaxActiveSessionsPerAuthorization = 1,
                MaxSharedBytes = 2048,
                MinimumFreeBytes = 0,
                MinimumFreeFraction = 0,
                JanitorInterval = TimeSpan.FromMinutes(1),
                CompletedReceiptRetention = TimeSpan.FromMinutes(1)
            };
            _options.Validate();
            _admission = new ReleaseUploadAdmissionService(configuration, _options);
            _middleware = new ReleaseUploadRequestGateMiddleware(context =>
            {
                NextCalled = true;
                context.Response.StatusCode = StatusCodes.Status204NoContent;
                return Task.CompletedTask;
            });
            Context = new DefaultHttpContext();
            Context.Response.Body = new MemoryStream();
        }

        public DefaultHttpContext Context { get; }
        public string SessionRoot { get; }
        public bool NextCalled { get; private set; }

        public string IssueTicket(string epoch)
        {
            var service = new ReleaseUploadTicketService(
                _provider,
                CreateConfiguration(epoch));
            return service.Issue(new AuthenticatedHubSubject(
                SubjectId: "subject-archon",
                DisplayName: "Archon",
                Email: "archon@example.com",
                Roles: ["operator"],
                AccessToken: "token")).Ticket;
        }

        public CountingStream PrepareRequest(string bearer, string nonce)
        {
            Context.Request.Method = HttpMethods.Post;
            Context.Request.Path =
                ReleaseUploadRequestGateMiddleware.TicketRevocationProofPath;
            Context.Request.Headers.Authorization = $"Bearer {bearer}";
            if (nonce.Length > 0)
            {
                Context.Request.Headers[
                    ReleaseUploadRequestGateMiddleware.TicketRevocationNonceHeader] = nonce;
            }

            Context.Request.ContentLength = 16;
            var body = new CountingStream(new byte[16]);
            Context.Request.Body = body;
            return body;
        }

        public Task InvokeAsync()
            => _middleware.InvokeAsync(Context, _authorization, _admission, _options);

        public async Task<string> ReadResponseBodyAsync()
        {
            Context.Response.Body.Position = 0;
            using var reader = new StreamReader(
                Context.Response.Body,
                Encoding.UTF8,
                detectEncodingFromByteOrderMarks: false,
                leaveOpen: true);
            return await reader.ReadToEndAsync();
        }

        private IConfiguration CreateConfiguration(string epoch)
            => new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["FLEET_INTERNAL_API_TOKEN"] = InternalToken,
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = SessionRoot,
                    ["CHUMMER_RELEASE_UPLOAD_TICKET_REVOCATION_EPOCH"] = epoch
                })
                .Build();

        public void Dispose()
        {
            Context.Response.Body.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
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
