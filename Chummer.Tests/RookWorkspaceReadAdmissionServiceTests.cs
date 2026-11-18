using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Contracts.Workspaces;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class RookWorkspaceReadAdmissionServiceTests
{
    private const string Subject = "subject.rook.admission";
    private const string Session = "session.rook.admission";
    private const string InstallationId = "ins-rook-admission";
    private const string GrantId = "grant-rook-admission";
    private const string Token = "rook-admission-test-bearer";

    [Fact]
    public async Task ExplicitGrantBindsTheExactPersistedFullSelectionAndClampsExpiryToFreshSession()
    {
        using Fixture fixture = new();
        byte[] snapshotBefore = File.ReadAllBytes(fixture.SnapshotPath);
        byte[] accountBefore = File.ReadAllBytes(fixture.AccountsStore.StoragePath);
        fixture.Handler.ExpiresAtUtc = fixture.Clock.GetUtcNow().AddMinutes(2);

        InstallLinkingRookReadConsent consent = await fixture.Grant();

        Assert.Equal(fixture.User.UserId, consent.UserId);
        Assert.Equal(Subject, consent.SubjectId);
        Assert.Equal(InstallationId, consent.InstallationId);
        Assert.Equal(GrantId, consent.GrantId);
        Assert.Equal(fixture.Selected.WorkspaceId, consent.WorkspaceId);
        Assert.Equal(fixture.Selected.RemoteRevision, consent.RemoteRevision);
        Assert.Equal(fixture.Selected.ServerToken, consent.ServerToken);
        Assert.Equal(fixture.Selected.WorkspaceContinuationDigest, consent.ContinuationDigest);
        Assert.Equal("rook-rule-read", consent.Purpose);
        Assert.Equal(1, consent.Version);
        Assert.Null(consent.RevokedAtUtc);
        Assert.Equal(fixture.Handler.ExpiresAtUtc, consent.ExpiresAtUtc);
        Assert.Equal(consent, Assert.Single(fixture.InstallStore.RookReadConsentsById).Value);
        Assert.Equal(1, fixture.Handler.Calls);
        Assert.Equal(snapshotBefore, File.ReadAllBytes(fixture.SnapshotPath));
        Assert.Equal(accountBefore, File.ReadAllBytes(fixture.AccountsStore.StoragePath));
        Assert.DoesNotContain(Token, File.ReadAllText(fixture.InstallStore.StoragePath), StringComparison.Ordinal);

        // The encrypted store, not the returned object, must retain the decision.
        fixture.RestartInstallStore();
        Assert.Equal(consent, Assert.Single(fixture.InstallStore.RookReadConsentsById).Value);
    }

    [Fact]
    public async Task FalseConfirmationRejectsBeforeIdentityOrPersistence()
    {
        using Fixture fixture = new();
        StoreImage before = fixture.Image();

        InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => fixture.Grant(explicitConfirmation: false));

        Assert.Equal(StatusCodes.Status403Forbidden, error.StatusCode);
        Assert.Equal(0, fixture.Handler.Calls);
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("workspace", StatusCodes.Status404NotFound)]
    [InlineData("revision", StatusCodes.Status409Conflict)]
    [InlineData("token", StatusCodes.Status409Conflict)]
    [InlineData("digest", StatusCodes.Status409Conflict)]
    public async Task ChangedSelectionNeverCreatesConsent(string change, int expectedStatus)
    {
        using Fixture fixture = new();
        StoreImage before = fixture.Image();

        InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => fixture.Grant(
                workspaceId: change == "workspace" ? "ws-other" : null,
                revision: change == "revision" ? fixture.Selected.RemoteRevision + 1 : null,
                serverToken: change == "token" ? DifferentDigest(fixture.Selected.ServerToken!) : null,
                digest: change == "digest" ? DifferentDigest(fixture.Selected.WorkspaceContinuationDigest!) : null));

        Assert.Equal(expectedStatus, error.StatusCode);
        Assert.Equal(1, fixture.Handler.Calls);
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData(false, StatusCodes.Status404NotFound)]
    [InlineData(true, StatusCodes.Status409Conflict)]
    public async Task AnotherOwnersContinuationAndProjectionOnlyRowsCannotAuthorizeConsent(bool projectionOnly, int status)
    {
        using Fixture fixture = new(projectionOnly: projectionOnly, foreignSnapshot: !projectionOnly);
        StoreImage before = fixture.Image();

        InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => fixture.Grant());

        Assert.Equal(status, error.StatusCode);
        Assert.Equal(1, fixture.Handler.Calls);
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task ActiveInstallationAndFullSnapshotDoNotImplyConsent()
    {
        using Fixture fixture = new();
        StoreImage before = fixture.Image();
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);

        InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => fixture.Service.CaptureAsync(fixture.Request, InstallationId, GrantId, new string('a', 64), 1));

        Assert.Equal(StatusCodes.Status403Forbidden, error.StatusCode);
        Assert.Equal(1, fixture.Handler.Calls);
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task ValidConsentStillCannotCaptureWithoutAnAuthoritativePostgresReadFence()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = await fixture.Grant();
        Assert.True(InstallLinkingRookReadConsent.ShapeIsValid(consent));
        StoreImage before = fixture.Image();

        InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => fixture.Service.CaptureAsync(fixture.Request, InstallationId, GrantId, consent.ConsentId, consent.Version));

        Assert.Equal(StatusCodes.Status403Forbidden, error.StatusCode);
        Assert.Equal(2, fixture.Handler.Calls);
        Assert.Equal(consent, Assert.Single(fixture.InstallStore.RookReadConsentsById).Value);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("revoked_session")]
    [InlineData("subject_case")]
    [InlineData("reassigned_account")]
    [InlineData("revoked_grant")]
    public async Task GrantRequiresCurrentExactAccountAndActiveGrant(string change)
    {
        using Fixture fixture = new();
        fixture.ChangeAuthority(change);
        StoreImage before = fixture.Image();

        if (change == "revoked_session")
        {
            HubRequestAuthException error = await Assert.ThrowsAsync<HubRequestAuthException>(() => fixture.Grant());
            Assert.Equal(StatusCodes.Status401Unauthorized, error.StatusCode);
        }
        else if (change is "reassigned_account" or "revoked_grant")
        {
            // Internal consent admission has no HTTP/public envelope yet.
            InvalidOperationException error = await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Grant());
            Assert.Equal("Rook read consent is unavailable for the current owner and grant.", error.Message);
            Assert.Null(error.InnerException);
        }
        else
        {
            InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(() => fixture.Grant());
            Assert.Equal(StatusCodes.Status403Forbidden, error.StatusCode);
        }

        Assert.Equal(1, fixture.Handler.Calls);
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task OwnerCanRevokeAfterTheInstallationGrantWasRevokedAndEveryCallReintrospects()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = await fixture.Grant();
        fixture.RevokeGrant();

        InstallLinkingRookReadConsent revoked = await fixture.Service.RevokeAsync(
            fixture.Request, consent.ConsentId, consent.Version);

        Assert.Equal(2, fixture.Handler.Calls);
        Assert.Equal(consent.ConsentId, revoked.ConsentId);
        Assert.Equal(consent.Version + 1, revoked.Version);
        Assert.NotNull(revoked.RevokedAtUtc);
        Assert.Equal(consent.UserId, revoked.UserId);
        Assert.Equal(consent.SubjectId, revoked.SubjectId);
        Assert.Equal(InstallationGrantStates.Revoked, fixture.InstallStore.GrantsById[GrantId].Status);
        Assert.Equal(revoked, fixture.InstallStore.RookReadConsentsById[consent.ConsentId]);

        StoreImage beforeRetry = fixture.Image();
        Assert.Equal(revoked, await fixture.Service.RevokeAsync(fixture.Request, revoked.ConsentId, revoked.Version));
        Assert.Equal(3, fixture.Handler.Calls);
        fixture.AssertUnchanged(beforeRetry);
    }

    [Theory]
    [InlineData("revoked_session")]
    [InlineData("subject_case")]
    [InlineData("reassigned_account")]
    public async Task ConsentRevocationStillRequiresFreshExactOwnerIdentity(string change)
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = await fixture.Grant();
        fixture.ChangeAuthority(change);
        StoreImage before = fixture.Image();

        if (change == "revoked_session")
        {
            HubRequestAuthException error = await Assert.ThrowsAsync<HubRequestAuthException>(
                () => fixture.Service.RevokeAsync(fixture.Request, consent.ConsentId, consent.Version));
            Assert.Equal(StatusCodes.Status401Unauthorized, error.StatusCode);
        }
        else if (change == "reassigned_account")
        {
            InvalidOperationException error = await Assert.ThrowsAsync<InvalidOperationException>(
                () => fixture.Service.RevokeAsync(fixture.Request, consent.ConsentId, consent.Version));
            Assert.Equal("Rook read consent is unavailable for the current owner and grant.", error.Message);
            Assert.Null(error.InnerException);
        }
        else
        {
            InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(
                () => fixture.Service.RevokeAsync(fixture.Request, consent.ConsentId, consent.Version));
            Assert.Equal(StatusCodes.Status403Forbidden, error.StatusCode);
        }

        Assert.Equal(2, fixture.Handler.Calls);
        Assert.Null(fixture.InstallStore.RookReadConsentsById[consent.ConsentId].RevokedAtUtc);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task RevalidationAfterAsyncWorkReintrospectsInsteadOfUsingPreviousObservationAsAuthorization()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = await fixture.Grant();
        // Deliberately NOT a proven capture: an old server-local carrier must
        // never bypass authentication. Successful fenced capture has real-PG tests.
        RookWorkspaceReadCapture previous = fixture.PreviousCarrier(consent);
        await Task.Yield();
        fixture.Handler.Active = false;
        StoreImage before = fixture.Image();

        HubRequestAuthException error = await Assert.ThrowsAsync<HubRequestAuthException>(
            () => fixture.Service.RevalidateAsync(fixture.Request, previous));

        Assert.Equal(StatusCodes.Status401Unauthorized, error.StatusCode);
        Assert.Equal(2, fixture.Handler.Calls);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task PreviousCaptureCannotReplaceTheExplicitBearerOnRevalidation()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = await fixture.Grant();
        RookWorkspaceReadCapture previous = fixture.PreviousCarrier(consent);
        fixture.Request.Headers.Remove("Authorization");
        StoreImage before = fixture.Image();

        HubRequestAuthException error = await Assert.ThrowsAsync<HubRequestAuthException>(
            () => fixture.Service.RevalidateAsync(fixture.Request, previous));

        Assert.Equal(StatusCodes.Status401Unauthorized, error.StatusCode);
        Assert.Equal(1, fixture.Handler.Calls);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task FreshRevalidationWithoutPostgresStillRejectsRatherThanTrustingEarlierCarrier()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = await fixture.Grant();
        StoreImage before = fixture.Image();

        InstallLinkingOperationException error = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => fixture.Service.RevalidateAsync(fixture.Request, fixture.PreviousCarrier(consent)));

        Assert.Equal(StatusCodes.Status403Forbidden, error.StatusCode);
        Assert.Equal(2, fixture.Handler.Calls);
        fixture.AssertUnchanged(before);
    }

    private static string DifferentDigest(string digest) => new(digest[0] == 'a' ? 'b' : 'a', 64);

    private sealed record StoreImage(string[] Paths, string[] Digests, long[] Updated, string Consents);

    private sealed class Fixture : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "chummer-rook-admission-tests", Guid.NewGuid().ToString("N"));
        private readonly IDataProtectionProvider _protection;
        private readonly HttpClient _http;
        private readonly HubSessionAccountAdmissionService _sessions;

        public Fixture(bool projectionOnly = false, bool foreignSnapshot = false)
        {
            Directory.CreateDirectory(_root);
            try
            {
                Configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ASPNETCORE_ENVIRONMENT"] = "Testing",
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid",
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install.json"),
                    ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = Path.Combine(_root, "snapshots.json")
                }).Build();
                _protection = DataProtectionProvider.Create(Path.Combine(_root, "keys"));
                InstallStore = NewInstallStore();
                AccountsStore = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
                Accounts = new AccountService(AccountsStore);
                User = Accounts.EnsureUser(Subject, "Rook admission fixture", "rook@example.invalid");
                Clock = new ManualTimeProvider(DateTimeOffset.UtcNow);
                Handler = new IdentityHandler(Clock.GetUtcNow().AddMinutes(10));
                _http = new HttpClient(Handler);
                _sessions = new HubSessionAccountAdmissionService(_http, Configuration, Accounts, Clock);
                Request = new DefaultHttpContext().Request;
                Request.Headers.Authorization = "Bearer " + Token;
                Installations = new InstallLinkingService(InstallStore, Configuration);
                Snapshots = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(Configuration));
                DateTimeOffset now = Clock.GetUtcNow();
                using RSA key = RSA.Create(2048);
                Installation = new ClaimedInstallationDto(InstallationId, "android-play-app", "internal",
                    "0.1.0-preview.12", InstallAccessClasses.AccountRequired, ClaimedInstallationStates.Active,
                    now.AddMinutes(-2), now.AddMinutes(-1), UserId: User.UserId, SubjectId: Subject,
                    PublicKey: Convert.ToBase64String(key.ExportSubjectPublicKeyInfo()), HeadId: "android",
                    Platform: "android", Arch: "arm64", GrantId: GrantId);
                lock (InstallStore.Gate)
                {
                    InstallStore.InstallationsById[InstallationId] = Installation;
                    InstallStore.GrantsById[GrantId] = new(GrantId, InstallationId, InstallationGrantStates.Active,
                        "local-fixture-installation-token", now.AddMinutes(-1), now.AddHours(1), User.UserId, Subject);
                    InstallStore.GrantTransportAuthoritiesByGrantId[GrantId] = new(GrantId, InstallationGrantTransports.AndroidLinkedV2);
                    InstallStore.PersistLocked();
                }
                string snapshotSubject = foreignSnapshot ? "subject.someone-else" : Subject;
                WorkspaceContinuationSnapshot full = InstallLinkedWorkspaceSnapshotTransferTests.SampleContinuation(snapshotSubject);
                InstallLinkedWorkspaceSnapshotRecord incoming = projectionOnly
                    ? InstallLinkedWorkspaceSnapshotTransferTests.ToRecord(full.Workspace)
                    : InstallLinkedWorkspaceSnapshotTransferTests.ToContinuationRecord(full);
                Selected = Snapshots.UpsertForInstallation(Installation with { SubjectId = snapshotSubject }, incoming, 0);
                Assert.True(InstallStore.IsHealthy);
                Assert.Equal(1, Selected.RemoteRevision);
                Assert.NotNull(Selected.ServerToken);
                Assert.Empty(InstallStore.RookReadConsentsById);
                if (!projectionOnly)
                {
                    Assert.True(WorkspaceContinuationCodec.TryDecodeCandidate(
                        Encoding.UTF8.GetBytes(Selected.WorkspaceContinuation!.Value.GetRawText()),
                        InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes, out WorkspaceContinuationExport? decoded));
                    Assert.Equal(full.OwnerId, decoded!.Snapshot.OwnerId);
                    Assert.Equal(Selected.WorkspaceContinuationDigest, decoded.SnapshotDigest);
                    Assert.Equal(full.Workspace.Id, decoded.Snapshot.Workspace.Id);
                }
                Service = new(_sessions, Accounts, Installations, Snapshots, Clock);
            }
            catch
            {
                // A failed precondition must not leave the private writer lease
                // or generated fixture files behind before using-disposal begins.
                InstallStore?.Dispose();
                _http?.Dispose();
                (_protection as IDisposable)?.Dispose();
                if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
                throw;
            }
        }

        public IConfiguration Configuration { get; }
        public CommunityStore AccountsStore { get; }
        public AccountService Accounts { get; }
        public HubUserDto User { get; }
        public InstallLinkingStore InstallStore { get; private set; }
        public InstallLinkingService Installations { get; private set; }
        public InstallLinkedWorkspaceSnapshotService Snapshots { get; }
        public ClaimedInstallationDto Installation { get; }
        public InstallLinkedWorkspaceSnapshotRecord Selected { get; }
        public ManualTimeProvider Clock { get; }
        public IdentityHandler Handler { get; }
        public HttpRequest Request { get; }
        public RookWorkspaceReadAdmissionService Service { get; private set; }
        public string SnapshotPath => Configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!;

        public Task<InstallLinkingRookReadConsent> Grant(bool explicitConfirmation = true, string? workspaceId = null,
            long? revision = null, string? serverToken = null, string? digest = null)
            => Service.GrantAsync(Request, InstallationId, GrantId, workspaceId ?? Selected.WorkspaceId,
                revision ?? Selected.RemoteRevision, serverToken ?? Selected.ServerToken!,
                digest ?? Selected.WorkspaceContinuationDigest ?? new string('a', 64),
                explicitConfirmation, Clock.GetUtcNow().AddMinutes(5));

        public void RevokeGrant() => Installations.RevokeGrantForOwner(InstallationId, User.UserId, Subject);

        public void ChangeAuthority(string change)
        {
            switch (change)
            {
                case "revoked_session": Handler.Active = false; break;
                case "subject_case": Handler.SubjectId = Subject.ToUpperInvariant(); break;
                case "revoked_grant": RevokeGrant(); break;
                case "reassigned_account":
                    lock (AccountsStore.Gate)
                    {
                        AccountsStore.UsersById.Clear();
                        AccountsStore.UserIdBySubjectId.Clear();
                        AccountsStore.PersistLocked();
                    }
                    HubUserDto replacement = Accounts.EnsureUser(Subject, "Reassigned account", "other@example.invalid");
                    Assert.NotEqual(User.UserId, replacement.UserId);
                    break;
                default: throw new ArgumentOutOfRangeException(nameof(change));
            }
        }

        public RookWorkspaceReadCapture PreviousCarrier(InstallLinkingRookReadConsent consent)
            => new(new(User.UserId, Subject, Session, Clock.GetUtcNow(), Handler.ExpiresAtUtc),
                consent, Selected, Clock.GetUtcNow());

        public StoreImage Image()
        {
            string[] paths = Directory.GetFiles(_root, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal).ToArray();
            Assert.InRange(paths.Length, 1, 20);
            Assert.All(paths, path => Assert.InRange(new FileInfo(path).Length, 0, 1024 * 1024));
            // The active writer lease is exclusively held by the actual store.
            // Observe its path/length/time, not an impermissible second open.
            return new(paths, paths.Select(path => path == InstallStore.StoragePath + ".writer.lock"
                    ? "exclusive-writer-lease-length:" + new FileInfo(path).Length
                    : Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)))).ToArray(),
                paths.Select(path => File.GetLastWriteTimeUtc(path).Ticks).ToArray(),
                JsonSerializer.Serialize(InstallStore.RookReadConsentsById));
        }

        public void AssertUnchanged(StoreImage before)
        {
            StoreImage after = Image();
            Assert.Equal(before.Paths, after.Paths);
            Assert.Equal(before.Digests, after.Digests);
            Assert.Equal(before.Updated, after.Updated);
            Assert.Equal(before.Consents, after.Consents);
            Assert.All(Handler.Tokens, token => Assert.Equal(Token, token));
        }

        public void RestartInstallStore()
        {
            InstallStore.Dispose();
            InstallStore = NewInstallStore();
            Installations = new(InstallStore, Configuration);
            Service = new(_sessions, Accounts, Installations, Snapshots, Clock);
            Assert.True(InstallStore.IsHealthy);
        }

        private InstallLinkingStore NewInstallStore()
            => new(Configuration, _protection, NullLogger<InstallLinkingStore>.Instance);

        public void Dispose()
        {
            try { InstallStore.Dispose(); }
            finally
            {
                _http.Dispose();
                (_protection as IDisposable)?.Dispose();
                if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class ManualTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }

    private sealed class IdentityHandler(DateTimeOffset expiresAtUtc) : HttpMessageHandler
    {
        public bool Active { get; set; } = true;
        public string SubjectId { get; set; } = Subject;
        public DateTimeOffset ExpiresAtUtc { get; set; } = expiresAtUtc;
        public int Calls { get; private set; }
        public List<string> Tokens { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Calls++;
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://identity.example.invalid/api/v1/identity/introspect", request.RequestUri?.AbsoluteUri);
            IdentityIntrospectionRequest? input = JsonSerializer.Deserialize<IdentityIntrospectionRequest>(
                await request.Content!.ReadAsStringAsync(ct), new JsonSerializerOptions(JsonSerializerDefaults.Web));
            Tokens.Add(Assert.IsType<IdentityIntrospectionRequest>(input).AccessToken);
            string response = JsonSerializer.Serialize(new IdentityIntrospectionResponse(
                Active, Session, SubjectId, ["player"], ExpiresAtUtc), new JsonSerializerOptions(JsonSerializerDefaults.Web));
            return new(HttpStatusCode.OK) { Content = new StringContent(response, Encoding.UTF8, "application/json") };
        }
    }
}
