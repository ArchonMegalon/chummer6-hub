using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Net;
using System.Reflection;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.WindowsProof;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class WindowsProofUploadProtocolTests
{
    [Fact]
    public void TicketScopesAreCryptographicallyDisjoint()
    {
        using ProtocolFixture fixture = new();
        AuthenticatedHubSubject subject = fixture.Subject;
        WindowsProofUploadTicketIssueResult proofTicket = fixture.ProofTickets.Issue(subject);
        ReleaseUploadTicketIssueResult canonicalTicket = fixture.CanonicalTickets.Issue(subject);

        Assert.True(fixture.ProofTickets.TryValidate(proofTicket.Ticket, out WindowsProofUploadTicketClaims? proofClaims));
        Assert.NotNull(proofClaims);
        Assert.False(fixture.CanonicalTickets.TryValidate(proofTicket.Ticket, out _));
        Assert.True(fixture.CanonicalTickets.TryValidate(canonicalTicket.Ticket, out ReleaseUploadTicketClaims? canonicalClaims));
        Assert.NotNull(canonicalClaims);
        Assert.False(fixture.ProofTickets.TryValidate(canonicalTicket.Ticket, out _));

        DefaultHttpContext canonicalContext = BuildBearerContext(
            "/api/internal/releases/upload-sessions",
            proofTicket.Ticket);
        DefaultHttpContext proofContext = BuildBearerContext(
            "/api/internal/windows-proof/upload-sessions",
            canonicalTicket.Ticket);
        Assert.Null(fixture.CanonicalAuthorization.Evaluate(canonicalContext.Request));
        Assert.Null(fixture.ProofAuthorization.Evaluate(proofContext.Request));
    }

    [Fact]
    public async Task UploadGateDefaultsClosedAndRequiresExplicitCfBoundary()
    {
        using ProtocolFixture fixture = new();
        WindowsProofUploadRequestGateMiddleware disabled = new(_ =>
            throw new Xunit.Sdk.XunitException("disabled lane reached downstream middleware"));
        DefaultHttpContext context = BuildBearerContext(
            "/api/internal/windows-proof/upload-sessions",
            fixture.InternalToken);

        await disabled.InvokeAsync(
            context,
            fixture.ProofAuthorization,
            fixture.Options with { Enabled = false, CfAccessGated = true });

        Assert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode);

        context = BuildBearerContext(
            "/api/internal/windows-proof/upload-sessions",
            fixture.InternalToken);
        await disabled.InvokeAsync(
            context,
            fixture.ProofAuthorization,
            fixture.Options with { Enabled = true, CfAccessGated = false });
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode);
    }

    [Fact]
    public async Task GateRejectsUnknownAndOversizedBodiesBeforeDownstreamRead()
    {
        using ProtocolFixture fixture = new();
        bool nextCalled = false;
        WindowsProofUploadRequestGateMiddleware middleware = new(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = BuildBearerContext(
            $"/api/internal/windows-proof/upload-sessions/{Guid.NewGuid():N}/files",
            fixture.InternalToken);
        context.Request.ContentLength = null;

        await middleware.InvokeAsync(context, fixture.ProofAuthorization, fixture.Options);

        Assert.Equal(StatusCodes.Status411LengthRequired, context.Response.StatusCode);
        Assert.False(nextCalled);

        context = BuildBearerContext(
            $"/api/internal/windows-proof/upload-sessions/{Guid.NewGuid():N}/chunks",
            fixture.InternalToken);
        context.Request.ContentLength = fixture.Options.MaxRequestBytes + 1;
        await middleware.InvokeAsync(context, fixture.ProofAuthorization, fixture.Options);
        Assert.Equal(StatusCodes.Status413PayloadTooLarge, context.Response.StatusCode);
        Assert.False(nextCalled);
    }

    [Fact]
    public async Task ManifestMustBeFirstAndBindsEveryAcceptedPathDigestAndSize()
    {
        using ProtocolFixture fixture = new();
        WindowsProofUploadSession session = fixture.CreateTicketSession();
        ProofFixtureData data = ProofFixtureData.Create();

        await Assert.ThrowsAsync<FileNotFoundException>(() => fixture.UploadAsync(
            session,
            data.SigningPath,
            data.Files[data.SigningPath]));
        await fixture.UploadManifestAsync(session, data.ManifestBytes);
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.UploadAsync(
            session,
            "files/not-declared.exe",
            [1, 2, 3]));
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.UploadAsync(
            session,
            "../escape.exe",
            [1]));
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.UploadAsync(
            session,
            data.SigningPath,
            [9, 9]));

        long stored = await fixture.UploadAsync(session, data.SigningPath, data.Files[data.SigningPath]);
        Assert.Equal(data.Files[data.SigningPath].Length, stored);
        long replay = await fixture.UploadAsync(session, data.SigningPath, data.Files[data.SigningPath]);
        Assert.Equal(stored, replay);
        await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.UploadAsync(
            session,
            data.SigningPath,
            [8, 8]));
    }

    [Fact]
    public async Task StableOrOptimisticManifestIsRejectedBeforeInventoryUpload()
    {
        using ProtocolFixture fixture = new();
        WindowsProofUploadSession session = fixture.CreateTicketSession();
        ProofFixtureData data = ProofFixtureData.Create();
        JsonNode root = JsonNode.Parse(data.ManifestBytes)!
            ?? throw new InvalidOperationException("fixture manifest missing");
        root["channel"] = "stable";
        root["releaseScope"] = "public_stable";
        root["supportabilityState"] = "preview_supported";
        byte[] optimistic = Encoding.UTF8.GetBytes(root.ToJsonString());

        await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.UploadManifestAsync(session, optimistic));
    }

    [Fact]
    public async Task NewUploadRejectsLegacyOrExpiredProofManifest()
    {
        using ProtocolFixture fixture = new();
        ProofFixtureData data = ProofFixtureData.Create();

        WindowsProofUploadSession legacySession = fixture.CreateTicketSession();
        JsonNode legacy = JsonNode.Parse(data.ManifestBytes)!;
        legacy["schemaVersion"] = "chummer.windows-proof.manifest/v1";
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.UploadManifestAsync(
            legacySession,
            Encoding.UTF8.GetBytes(legacy.ToJsonString())));

        WindowsProofUploadSession expiredSession = fixture.CreateTicketSession();
        JsonNode expired = JsonNode.Parse(data.ManifestBytes)!;
        expired["generatedAt"] = "2026-01-01T00:00:00Z";
        expired["expiresAt"] = "2026-01-01T12:00:00Z";
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.UploadManifestAsync(
            expiredSession,
            Encoding.UTF8.GetBytes(expired.ToJsonString())));
    }

    [Fact]
    public async Task ChunksAreBoundedReplaySafeAndAssembledOnlyAfterEveryChunkMatches()
    {
        using ProtocolFixture fixture = new();
        WindowsProofUploadSession session = fixture.CreateTicketSession();
        ProofFixtureData data = ProofFixtureData.Create();
        await fixture.UploadManifestAsync(session, data.ManifestBytes);
        byte[] installer = data.Files[data.InstallerPath];
        byte[] first = installer[..6];
        byte[] second = installer[6..];

        WindowsProofUploadChunkResult partial = await fixture.ChunkAsync(
            session,
            data.InstallerPath,
            0,
            2,
            first);
        Assert.False(partial.Completed);
        WindowsProofUploadChunkResult replay = await fixture.ChunkAsync(
            session,
            data.InstallerPath,
            0,
            2,
            first);
        Assert.False(replay.Completed);
        await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.ChunkAsync(
            session,
            data.InstallerPath,
            0,
            2,
            [7, 7, 7, 7, 7, 7]));

        WindowsProofUploadChunkResult complete = await fixture.ChunkAsync(
            session,
            data.InstallerPath,
            1,
            2,
            second);
        Assert.True(complete.Completed);
    }

    [Fact]
    public async Task DurableLifecycleIsIdempotentAndConsumesTicketOnce()
    {
        using ProtocolFixture fixture = new();
        WindowsProofUploadTicketIssueResult issued = fixture.ProofTickets.Issue(fixture.Subject);
        WindowsProofUploadAuthorizationContext authorization = fixture.AuthorizeProofTicket(issued.Ticket);
        WindowsProofUploadSession session = fixture.Sessions.CreateSession(
            authorization.AuthorizationBinding,
            singleUseAuthorization: true,
            authorization.AuthorizationExpiresAtUtc);
        ProofFixtureData data = ProofFixtureData.Create();
        await fixture.UploadAllAsync(session, authorization.AuthorizationBinding, data);

        using (WindowsProofUploadCompletionLease lease = fixture.Sessions.BeginCompletion(
                   session.SessionId,
                   authorization.AuthorizationBinding))
        {
            Assert.Equal(WindowsProofUploadSessionStates.RequestStarted, lease.State);
            var prepared = new WindowsProofPreparedGeneration(
                "sha256-" + new string('b', 64),
                data.CandidateVersion,
                new string('c', 64),
                DateTimeOffset.UtcNow);
            lease.RecordPrepared(prepared, expectedCurrentGenerationId: null);
            var result = new WindowsProofUploadCompletionResult(
                session.SessionId,
                prepared.GenerationId,
                prepared.CandidateVersion,
                lease.ManifestSha256,
                prepared.InventoryDigest,
                DateTimeOffset.UtcNow,
                new Dictionary<string, string> { ["manifest"] = "/proof/manifest" });
            lease.MarkCompleted(result);
        }

        using (WindowsProofUploadCompletionLease replay = fixture.Sessions.BeginCompletion(
                   session.SessionId,
                   authorization.AuthorizationBinding))
        {
            Assert.Equal(WindowsProofUploadSessionStates.Completed, replay.State);
            Assert.NotNull(replay.CompletionResult);
        }
        Assert.Throws<InvalidOperationException>(() => fixture.Sessions.CreateSession(
            authorization.AuthorizationBinding,
            singleUseAuthorization: true,
            authorization.AuthorizationExpiresAtUtc));
    }

    [Fact]
    public async Task MissingEvidenceAndMixedSessionKindFailClosed()
    {
        using ProtocolFixture fixture = new();
        WindowsProofUploadSession session = fixture.CreateTicketSession();
        ProofFixtureData data = ProofFixtureData.Create();
        await fixture.UploadManifestAsync(session, data.ManifestBytes);
        await fixture.UploadAsync(session, data.SigningPath, data.Files[data.SigningPath]);
        Assert.Throws<InvalidOperationException>(() => fixture.Sessions.BeginCompletion(
            session.SessionId,
            fixture.CurrentBinding));

        string metadataPath = Path.Combine(fixture.SessionRoot, session.SessionId, "session.json");
        JsonNode metadata = JsonNode.Parse(File.ReadAllText(metadataPath))!;
        metadata["sessionKind"] = "canonical_release";
        File.WriteAllText(metadataPath, metadata.ToJsonString());
        Assert.Throws<InvalidDataException>(() => fixture.Sessions.BeginCompletion(
            session.SessionId,
            fixture.CurrentBinding));
    }

    [Fact]
    public async Task SymlinkedBundleParentIsRejected()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using ProtocolFixture fixture = new();
        WindowsProofUploadSession session = fixture.CreateTicketSession();
        ProofFixtureData data = ProofFixtureData.Create();
        await fixture.UploadManifestAsync(session, data.ManifestBytes);
        string external = Path.Combine(fixture.Root, "external");
        Directory.CreateDirectory(external);
        string bundle = Path.Combine(fixture.SessionRoot, session.SessionId, "bundle");
        Directory.CreateSymbolicLink(Path.Combine(bundle, "signing"), external);

        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.UploadAsync(
            session,
            data.SigningPath,
            data.Files[data.SigningPath]));
    }

    [Fact]
    public void SessionStorageCannotOverlapEitherProofShelf()
    {
        using ProtocolFixture fixture = new();
        string proofRoot = Path.Combine(fixture.Root, "proof-store-overlap");
        string canonicalRoot = Path.Combine(fixture.Root, "canonical-overlap");
        IConfiguration proofOverlap = BuildStorageConfiguration(
            Path.Combine(proofRoot, "upload-sessions"),
            proofRoot,
            canonicalRoot);
        var proofService = new WindowsProofUploadSessionService(
            proofOverlap,
            fixture.Options,
            TimeProvider.System);
        Assert.Throws<InvalidOperationException>(() => proofService.CreateSession(
            new string('a', 64),
            singleUseAuthorization: false,
            authorizationExpiresAtUtc: null));

        IConfiguration canonicalOverlap = BuildStorageConfiguration(
            Path.Combine(canonicalRoot, "upload-sessions"),
            proofRoot,
            canonicalRoot);
        var canonicalService = new WindowsProofUploadSessionService(
            canonicalOverlap,
            fixture.Options,
            TimeProvider.System);
        Assert.Throws<InvalidOperationException>(() => canonicalService.CreateSession(
            new string('b', 64),
            singleUseAuthorization: false,
            authorizationExpiresAtUtc: null));
    }

    [Fact]
    public void SessionStorageRejectsSymlinkedAncestors()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using ProtocolFixture fixture = new();
        string external = Path.Combine(fixture.Root, "external-session-root");
        string link = Path.Combine(fixture.Root, "linked-session-parent");
        Directory.CreateDirectory(external);
        Directory.CreateSymbolicLink(link, external);
        IConfiguration configuration = BuildStorageConfiguration(
            Path.Combine(link, "sessions"),
            Path.Combine(fixture.Root, "separate-proof-store"),
            Path.Combine(fixture.Root, "separate-canonical-store"));
        var service = new WindowsProofUploadSessionService(
            configuration,
            fixture.Options,
            TimeProvider.System);

        Assert.Throws<InvalidDataException>(() => service.CreateSession(
            new string('c', 64),
            singleUseAuthorization: false,
            authorizationExpiresAtUtc: null));
    }

    [Fact]
    public async Task SignedInReleaseAuthorityCanMintOnlyProofScopedTicket()
    {
        using ProtocolFixture fixture = new();
        const string localToken = "local-proof-authority";
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = localToken,
                ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.windows-proof-authority",
                ["CHUMMER_LOCAL_E2E_EMAIL"] = ReleaseUploadAccessPolicy.AllowedEmail,
                ["CHUMMER_LOCAL_E2E_ROLES"] = "operator"
            })
            .Build();
        var serviceCollection = new ServiceCollection();
        serviceCollection.AddLogging();
        serviceCollection.AddDataProtection();
        serviceCollection.AddAntiforgery();
        using ServiceProvider services = serviceCollection.BuildServiceProvider();
        var identity = new HubIdentityClient(
            new HttpClient(new RejectingHandler()),
            configuration);
        var controller = new WindowsProofUploadAuthorityController(
            identity,
            fixture.ProofTickets,
            fixture.Options,
            services.GetRequiredService<IAntiforgery>(),
            NullLogger<WindowsProofUploadAuthorityController>.Instance);
        var context = new DefaultHttpContext
        {
            RequestServices = services
        };
        context.Connection.RemoteIpAddress = IPAddress.Loopback;
        context.Request.Host = new HostString("localhost");
        context.Request.Headers.Authorization = $"Bearer {localToken}";
        controller.ControllerContext = new ControllerContext { HttpContext = context };

        OkObjectResult ok = Assert.IsType<OkObjectResult>(
            await controller.IssueUploadTicket(CancellationToken.None));
        using JsonDocument response = JsonSerializer.SerializeToDocument(ok.Value);
        string ticket = response.RootElement.GetProperty("ticket").GetString()!;
        Assert.Equal(
            WindowsProofUploadTicketService.TicketScope,
            response.RootElement.GetProperty("scope").GetString());
        Assert.True(fixture.ProofTickets.TryValidate(ticket, out _));
        Assert.False(fixture.CanonicalTickets.TryValidate(ticket, out _));
        MethodInfo method = typeof(WindowsProofUploadAuthorityController)
            .GetMethod(nameof(WindowsProofUploadAuthorityController.IssueUploadTicket))!;
        Assert.NotNull(method.GetCustomAttribute<ValidateAntiForgeryTokenAttribute>());
    }

    private static IConfiguration BuildStorageConfiguration(
        string sessionRoot,
        string proofRoot,
        string canonicalRoot)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_WINDOWS_PROOF_UPLOAD_SESSION_ROOT"] = sessionRoot,
                ["CHUMMER_WINDOWS_PROOF_ROOT"] = proofRoot,
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = canonicalRoot
            })
            .Build();

    private static DefaultHttpContext BuildBearerContext(string path, string bearer)
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = path;
        context.Request.Headers.Authorization = $"Bearer {bearer}";
        context.Response.Body = new MemoryStream();
        return context;
    }

    private sealed class ProtocolFixture : IDisposable
    {
        public ProtocolFixture()
        {
            Root = Path.Combine(Path.GetTempPath(), "windows-proof-upload-tests", Guid.NewGuid().ToString("N"));
            SessionRoot = Path.Combine(Root, "sessions");
            Directory.CreateDirectory(Root);
            InternalToken = "windows-proof-internal-token";
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["FLEET_INTERNAL_API_TOKEN"] = InternalToken,
                    ["CHUMMER_WINDOWS_PROOF_UPLOAD_ENABLED"] = "true",
                    ["CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED"] = "true",
                    ["CHUMMER_WINDOWS_PROOF_UPLOAD_SESSION_ROOT"] = SessionRoot,
                    ["CHUMMER_WINDOWS_PROOF_ROOT"] = Path.Combine(Root, "proof-store"),
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = Path.Combine(Root, "canonical-downloads")
                })
                .Build();
            Options = new WindowsProofUploadOptions
            {
                MaxChunkBytes = 8,
                MaxRequestBytes = 128,
                MaxFileBytes = 1024 * 1024,
                MaxSessionBytes = 4 * 1024 * 1024,
                MaxFilesPerSession = 8,
                MaxChunksPerFile = 16,
                MaxPathBytes = 512,
                SessionLifetime = TimeSpan.FromHours(1),
                CompletedReceiptRetention = TimeSpan.FromDays(1),
                Enabled = true,
                CfAccessGated = true
            };
            Options.Validate();
            IDataProtectionProvider provider = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(Root, "keys")));
            ProofTickets = new WindowsProofUploadTicketService(provider, Configuration);
            CanonicalTickets = new ReleaseUploadTicketService(provider, Configuration);
            ProofAuthorization = new WindowsProofUploadAuthorizationEvaluator(Configuration, ProofTickets);
            CanonicalAuthorization = new ReleaseUploadAuthorizationEvaluator(Configuration, CanonicalTickets);
            Sessions = new WindowsProofUploadSessionService(Configuration, Options, TimeProvider.System);
            Subject = new AuthenticatedHubSubject(
                "windows-proof-operator",
                "Windows Proof Operator",
                "operator@example.com",
                ["operator"],
                "subject-token");
        }

        public string Root { get; }
        public string SessionRoot { get; }
        public string InternalToken { get; }
        public IConfiguration Configuration { get; }
        public WindowsProofUploadOptions Options { get; }
        public WindowsProofUploadTicketService ProofTickets { get; }
        public ReleaseUploadTicketService CanonicalTickets { get; }
        public WindowsProofUploadAuthorizationEvaluator ProofAuthorization { get; }
        public ReleaseUploadAuthorizationEvaluator CanonicalAuthorization { get; }
        public WindowsProofUploadSessionService Sessions { get; }
        public AuthenticatedHubSubject Subject { get; }
        public string CurrentBinding { get; private set; } = string.Empty;

        public WindowsProofUploadSession CreateTicketSession()
        {
            WindowsProofUploadTicketIssueResult ticket = ProofTickets.Issue(Subject);
            WindowsProofUploadAuthorizationContext authorization = AuthorizeProofTicket(ticket.Ticket);
            CurrentBinding = authorization.AuthorizationBinding;
            return Sessions.CreateSession(
                authorization.AuthorizationBinding,
                singleUseAuthorization: true,
                authorization.AuthorizationExpiresAtUtc);
        }

        public WindowsProofUploadAuthorizationContext AuthorizeProofTicket(string ticket)
        {
            DefaultHttpContext context = BuildBearerContext(
                "/api/internal/windows-proof/upload-sessions",
                ticket);
            return Assert.IsType<WindowsProofUploadAuthorizationContext>(
                ProofAuthorization.Evaluate(context.Request));
        }

        public Task<long> UploadManifestAsync(WindowsProofUploadSession session, byte[] bytes)
            => UploadAsync(session, WindowsProofUploadSessionService.ManifestFileName, bytes);

        public Task<long> UploadAsync(WindowsProofUploadSession session, string path, byte[] bytes)
            => Sessions.WriteFileAsync(
                session.SessionId,
                path,
                new MemoryStream(bytes, writable: false),
                CurrentBinding,
                CancellationToken.None);

        public Task<WindowsProofUploadChunkResult> ChunkAsync(
            WindowsProofUploadSession session,
            string path,
            int index,
            int total,
            byte[] bytes)
            => Sessions.AppendChunkAsync(
                session.SessionId,
                path,
                index,
                total,
                new MemoryStream(bytes, writable: false),
                CurrentBinding,
                CancellationToken.None);

        public async Task UploadAllAsync(
            WindowsProofUploadSession session,
            string binding,
            ProofFixtureData data)
        {
            CurrentBinding = binding;
            await UploadManifestAsync(session, data.ManifestBytes);
            foreach ((string path, byte[] bytes) in data.Files.Where(pair => pair.Key != data.InstallerPath))
            {
                await UploadAsync(session, path, bytes);
            }
            byte[] installer = data.Files[data.InstallerPath];
            await ChunkAsync(session, data.InstallerPath, 0, 2, installer[..6]);
            await ChunkAsync(session, data.InstallerPath, 1, 2, installer[6..]);
        }

        public void Dispose()
        {
            try
            {
                Directory.Delete(Root, recursive: true);
            }
            catch
            {
                // Test cleanup is best effort.
            }
        }
    }

    private sealed record ProofFixtureData(
        string CandidateVersion,
        string InstallerPath,
        string SigningPath,
        IReadOnlyDictionary<string, byte[]> Files,
        byte[] ManifestBytes)
    {
        public static ProofFixtureData Create()
        {
            const string version = "run-20260716-115521";
            const string installerPath = "files/chummer-avalonia-win-x64-installer.exe";
            const string signingPath = "signing/signing-avalonia-win-x64.receipt.json";
            const string smokePath = "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json";
            const string provenancePath = "proof/build-provenance/v1/invocations/run-20260716-115521.avalonia.win-x64.installer.json";
            const string sbomPath = "proof/build-provenance/v1/sbom/desktop-avalonia.cdx.json";
            const string handoffPath = "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json";
            IReadOnlyDictionary<string, byte[]> files = new Dictionary<string, byte[]>(StringComparer.Ordinal)
            {
                [installerPath] = Encoding.ASCII.GetBytes("installer!"),
                [signingPath] = Encoding.ASCII.GetBytes("{}"),
                [smokePath] = Encoding.ASCII.GetBytes("{}"),
                [provenancePath] = Encoding.ASCII.GetBytes("{}"),
                [sbomPath] = Encoding.ASCII.GetBytes("{}"),
                [handoffPath] = Encoding.ASCII.GetBytes("{}")
            };
            object Artifact(string kind, string id, string path, string contentType) => new
            {
                kind,
                artifactId = id,
                head = "avalonia",
                rid = "win-x64",
                fileName = Path.GetFileName(path),
                relativePath = path,
                contentType,
                size = files[path].Length,
                sha256 = Convert.ToHexStringLower(SHA256.HashData(files[path]))
            };
            object[] artifacts =
            [
                Artifact("installer", "installer", installerPath, "application/vnd.microsoft.portable-executable"),
                Artifact("signing_receipt", "signing", signingPath, "application/json"),
                Artifact("startup_smoke_receipt", "smoke", smokePath, "application/json"),
                Artifact("build_provenance_receipt", "provenance", provenancePath, "application/json"),
                Artifact("sbom", "sbom", sbomPath, "application/vnd.cyclonedx+json"),
                Artifact("visual_handoff", "handoff", handoffPath, "application/json")
            ];
            byte[] manifest = JsonSerializer.SerializeToUtf8Bytes(new
            {
                schemaVersion = "chummer.windows-proof.manifest/v2",
                candidateVersion = version,
                channel = "preview",
                releaseScope = "proof_only",
                supportabilityState = "review_required",
                publicTrustPosture = "blocked",
                cfAccessGated = true,
                revoked = false,
                generatedAt = DateTimeOffset.UtcNow.AddMinutes(-1).ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'"),
                expiresAt = DateTimeOffset.UtcNow.AddHours(23).ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'"),
                proofOnlyPolicy = new
                {
                    enabled = true,
                    unsignedPreviewAllowed = true,
                    nativeWindowsValidationRequired = true
                },
                signing = new
                {
                    status = "skipped_preview",
                    proofOnlyPolicyRecorded = true,
                    receiptArtifactId = "signing"
                },
                compatibilitySmoke = new
                {
                    status = "pass",
                    executionEnvironment = "wine_compatibility",
                    nativeWindows = false,
                    receiptArtifactId = "smoke",
                    payloadAcquisitionMode = "embedded"
                },
                visualExitGate = new { status = "external_only", evidenceArtifactId = (string?)null },
                nativeHostHandoff = new
                {
                    status = "ready_for_windows_host",
                    onlyBlocker = "visual_proof",
                    onlyBlockerIsVisualProof = true,
                    handoffArtifactId = "handoff"
                },
                artifacts
            });
            return new ProofFixtureData(version, installerPath, signingPath, files, manifest);
        }
    }

    private sealed class RejectingHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => throw new InvalidOperationException("local seeded identity must not call the network");
    }
}
