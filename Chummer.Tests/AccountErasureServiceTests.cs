using System.Net;
using System.Net.Http.Json;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Contracts.Privacy;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AccountErasureServiceTests
{
    [Fact]
    public async Task Erase_completes_first_party_planes_before_revoking_identity()
    {
        using Fixture fixture = new();
        bool identityObservedLocalErasure = false;
        HubIdentityClient identity = fixture.CreateIdentityClient(request =>
        {
            Assert.Equal(HttpMethod.Delete, request.Method);
            Assert.Equal("identity-admin", request.Headers.GetValues("X-Identity-Admin-Key").Single());
            identityObservedLocalErasure = fixture.Community.UsersById.Count == 0
                                           && fixture.Support.CasesById.Count == 0;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = JsonContent.Create(new IdentitySubjectErasureResponse(
                    Erased: true,
                    SubjectKeySha256: new string('b', 64),
                    RevokedSessionCount: 2,
                    DeletedEmailTicketCount: 1,
                    ErasedAtUtc: DateTimeOffset.UtcNow))
            };
        });
        var hosted = new RecordingHostedBuildEraser();
        var service = new AccountErasureService(
            fixture.Accounts,
            new CommunityAccountErasureService(fixture.Community),
            fixture.Support,
            new EmptyAuxiliaryEraser(),
            hosted,
            identity,
            fixture.Journal,
            fixture.Configuration);

        CurrentAccountErasureResponse result =
            await service.EraseAsync("subject-delete", CancellationToken.None);

        Assert.True(result.Erased);
        Assert.True(hosted.Called);
        Assert.True(identityObservedLocalErasure);
        Assert.Equal(5, result.Components.Count);
        Assert.All(result.Components, static component => Assert.True(component.Completed));
        Assert.Equal(64, result.SubjectKeySha256.Length);
        Assert.Equal(64, result.UserKeySha256?.Length);
        Assert.Equal(64, result.ReceiptSha256.Length);
        Assert.Empty(fixture.Community.UsersById);
        Assert.Empty(fixture.Support.CasesById);
    }

    [Fact]
    public async Task Hosted_build_failure_leaves_local_account_and_identity_untouched()
    {
        using Fixture fixture = new();
        int identityCalls = 0;
        HubIdentityClient identity = fixture.CreateIdentityClient(_ =>
        {
            identityCalls++;
            return new HttpResponseMessage(HttpStatusCode.InternalServerError);
        });
        var service = new AccountErasureService(
            fixture.Accounts,
            new CommunityAccountErasureService(fixture.Community),
            fixture.Support,
            new EmptyAuxiliaryEraser(),
            new FailingHostedBuildEraser(),
            identity,
            fixture.Journal,
            fixture.Configuration);

        await Assert.ThrowsAsync<HubRequestAuthException>(
            () => service.EraseAsync("subject-delete", CancellationToken.None));

        Assert.Equal(0, identityCalls);
        Assert.Single(fixture.Community.UsersById);
        Assert.Single(fixture.Support.CasesById);
    }

    [Fact]
    public async Task Identity_failure_is_recovered_from_independent_journal_without_retaining_plaintext()
    {
        using Fixture fixture = new();
        int identityCalls = 0;
        HubIdentityClient identity = fixture.CreateIdentityClient(_ =>
        {
            identityCalls++;
            if (identityCalls == 1)
            {
                return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable);
            }

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = JsonContent.Create(new IdentitySubjectErasureResponse(
                    Erased: true,
                    SubjectKeySha256: new string('c', 64),
                    RevokedSessionCount: 1,
                    DeletedEmailTicketCount: 0,
                    ErasedAtUtc: DateTimeOffset.UtcNow))
            };
        });
        var hosted = new RecordingHostedBuildEraser();
        var service = new AccountErasureService(
            fixture.Accounts,
            new CommunityAccountErasureService(fixture.Community),
            fixture.Support,
            new EmptyAuxiliaryEraser(),
            hosted,
            identity,
            fixture.Journal,
            fixture.Configuration);

        await Assert.ThrowsAsync<HubRequestAuthException>(
            () => service.EraseAsync("subject-delete", CancellationToken.None));

        Assert.Empty(fixture.Community.UsersById);
        Assert.Empty(fixture.Support.CasesById);
        PendingIdentityAccountErasure pending = Assert.Single(
            fixture.Journal.GetPendingIdentityDue(DateTimeOffset.UtcNow.AddMinutes(2)));
        Assert.Equal("subject-delete", pending.SubjectId);

        await service.RecoverPendingIdentityAsync(pending, CancellationToken.None);

        AccountErasureJournalEntry completed = Assert.IsType<AccountErasureJournalEntry>(
            fixture.Journal.Find(pending.Entry.SubjectKeySha256));
        Assert.Equal(AccountErasureJournalStage.Completed, completed.Stage);
        Assert.Null(completed.PendingSubjectCiphertext);
        Assert.Equal(5, completed.Components.Count);
        Assert.Equal(2, identityCalls);
        string persisted = File.ReadAllText(fixture.Journal.StoragePath);
        Assert.DoesNotContain("subject-delete", persisted, StringComparison.Ordinal);
        Assert.DoesNotContain("delete@example.invalid", persisted, StringComparison.Ordinal);

        var reloaded = new AccountErasureJournalStore(
            fixture.Configuration,
            new Microsoft.AspNetCore.DataProtection.EphemeralDataProtectionProvider(),
            NullLogger<AccountErasureJournalStore>.Instance);
        Assert.Equal(AccountErasureJournalStage.Completed, reloaded.Find(completed.SubjectKeySha256)?.Stage);

        CurrentAccountErasureResponse replay =
            await service.EraseAsync("subject-delete", CancellationToken.None);
        Assert.Equal(completed.ReceiptSha256, replay.ReceiptSha256);
        Assert.Equal(2, identityCalls);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(
            Path.GetTempPath(),
            "chummer-account-erasure-tests",
            Guid.NewGuid().ToString("N"));

        public Fixture()
        {
            Directory.CreateDirectory(_directory);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_directory, "community.json"),
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(_directory, "support.json"),
                    ["CHUMMER_ACCOUNT_ERASURE_JOURNAL_PATH"] = Path.Combine(_directory, "account-erasure-journal.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.test",
                    ["IDENTITY_ADMIN_KEY"] = "identity-admin",
                    ["CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"] = Convert.ToBase64String(Enumerable.Repeat((byte)0x5a, 32).ToArray())
                })
                .Build();
            Community = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Support = new SupportStore(Configuration, NullLogger<SupportStore>.Instance);
            Accounts = new AccountService(Community);
            Journal = new AccountErasureJournalStore(
                Configuration,
                new Microsoft.AspNetCore.DataProtection.EphemeralDataProtectionProvider(),
                NullLogger<AccountErasureJournalStore>.Instance);
            HubUserDto user = Accounts.EnsureUser("subject-delete", "Delete Me", "delete@example.invalid");
            Support.CasesById["case-delete"] = new SupportCaseProjection(
                "case-delete", "cluster-delete", "account", "open", "Private request", "Private summary",
                "Private detail", "chummer6-hub", false, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                "account", ReporterUserId: user.UserId, ReporterSubjectId: user.SubjectId);
            Support.CaseIdByClusterKey["cluster-delete"] = "case-delete";
            Support.PersistLocked();
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Community { get; }
        public SupportStore Support { get; }
        public AccountService Accounts { get; }
        public AccountErasureJournalStore Journal { get; }

        public HubIdentityClient CreateIdentityClient(Func<HttpRequestMessage, HttpResponseMessage> response)
            => new(
                new HttpClient(new DelegateHandler(response)),
                Configuration,
                NullLogger<HubIdentityClient>.Instance,
                new HubIdentitySubjectCache());

        public void Dispose()
        {
            try
            {
                Directory.Delete(_directory, recursive: true);
            }
            catch
            {
                // Best-effort cleanup for test temp files.
            }
        }
    }

    private sealed class RecordingHostedBuildEraser : IHostedBuildAccountErasureClient
    {
        public bool Called { get; private set; }

        public Task<HostedBuildAccountErasureResult> EraseOwnerWorkspacesAsync(
            string subjectId,
            CancellationToken cancellationToken)
        {
            Assert.Equal("subject-delete", subjectId);
            Called = true;
            return Task.FromResult(new HostedBuildAccountErasureResult(true, 3, new string('a', 64)));
        }
    }

    private sealed class FailingHostedBuildEraser : IHostedBuildAccountErasureClient
    {
        public Task<HostedBuildAccountErasureResult> EraseOwnerWorkspacesAsync(
            string subjectId,
            CancellationToken cancellationToken)
            => throw new HubRequestAuthException(StatusCodes.Status503ServiceUnavailable, "hosted build unavailable");
    }

    private sealed class EmptyAuxiliaryEraser : IAccountAuxiliaryDataErasureService
    {
        public AccountAuxiliaryDataErasureResult Erase(string? userId, string subjectId)
            => new(0, new Dictionary<string, int>(StringComparer.Ordinal));
    }

    private sealed class DelegateHandler(Func<HttpRequestMessage, HttpResponseMessage> response) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => Task.FromResult(response(request));
    }
}
