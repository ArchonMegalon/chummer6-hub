using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AccountCanonicalCaptureTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Exact_primary_or_linked_subject_captures_without_writing(bool linked)
    {
        using var fixture = new Fixture();
        string subject = linked ? "Linked.Case" : Fixture.Subject;
        if (linked)
        {
            lock (fixture.Store.Gate)
            {
                fixture.Store.UsersById[fixture.User.UserId] = fixture.User with
                { LinkedPrincipals = [Fixture.Subject, subject] };
                fixture.Store.UserIdBySubjectId[subject] = fixture.User.UserId;
                fixture.Store.PersistLocked();
            }
        }
        byte[] before = File.ReadAllBytes(fixture.Store.StoragePath);
        int callbacks = 0;

        Assert.True(fixture.Service.CaptureExistingCanonicalAccount(subject, fixture.User.UserId, () =>
        {
            Assert.True(Monitor.IsEntered(fixture.Store.Gate));
            callbacks++;
        }));

        Assert.Equal(1, callbacks);
        Assert.Equal(before, File.ReadAllBytes(fixture.Store.StoragePath));
        Assert.Single(fixture.Store.UsersById);
    }

    [Theory]
    [InlineData("subject-case")]
    [InlineData("user-case")]
    [InlineData("missing-index")]
    [InlineData("missing-row")]
    [InlineData("reassigned-index")]
    [InlineData("reassigned-row")]
    [InlineData("membership-removed")]
    public void Ambiguous_stale_or_reassigned_mapping_never_invokes_capture(string change)
    {
        using var fixture = new Fixture();
        string subject = Fixture.Subject;
        string userId = fixture.User.UserId;
        switch (change)
        {
            case "subject-case": subject = subject.ToLowerInvariant(); break;
            case "user-case": userId = userId.ToUpperInvariant(); break;
            case "missing-index": fixture.Store.UserIdBySubjectId.Clear(); break;
            case "missing-row": fixture.Store.UsersById.Clear(); break;
            case "reassigned-index": fixture.Store.UserIdBySubjectId[subject] = "usr-other"; break;
            case "reassigned-row": fixture.Store.UsersById[userId] = fixture.User with { UserId = "usr-other" }; break;
            case "membership-removed": fixture.Store.UsersById[userId] = fixture.User with
                { SubjectId = "Other.Subject", LinkedPrincipals = [] }; break;
        }
        byte[] before = File.ReadAllBytes(fixture.Store.StoragePath);
        int callbacks = 0;

        Assert.False(fixture.Service.CaptureExistingCanonicalAccount(subject, userId, () => callbacks++));

        Assert.Equal(0, callbacks);
        Assert.Equal(before, File.ReadAllBytes(fixture.Store.StoragePath));
    }

    [Theory]
    [InlineData("null")]
    [InlineData("empty")]
    [InlineData("whitespace")]
    [InlineData("control")]
    [InlineData("oversize")]
    [InlineData("multibyte-oversize")]
    [InlineData("surrogate")]
    public void Malformed_identity_is_rejected_without_callback_or_creation(string kind)
    {
        using var fixture = new Fixture();
        string malformed = kind switch
        {
            "null" => null!,
            "empty" => string.Empty,
            "whitespace" => " Subject.Case",
            "control" => "Subject\0Case",
            "oversize" => new string('x', 129),
            "multibyte-oversize" => new string('é', 65),
            _ => "\ud800"
        };
        int callbacks = 0;

        Assert.False(fixture.Service.CaptureExistingCanonicalAccount(malformed, fixture.User.UserId, () => callbacks++));
        Assert.False(fixture.Service.CaptureExistingCanonicalAccount(Fixture.Subject, malformed, () => callbacks++));

        Assert.Equal(0, callbacks);
        Assert.Single(fixture.Store.UsersById);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Async_void_members_are_rejected_before_any_callback(bool multicast)
    {
        using var fixture = new Fixture();
        int callbacks = 0;
        Action asynchronous = async () => { callbacks++; await Task.Yield(); };
        Action capture = multicast ? new Action(() => callbacks++) + asynchronous : asynchronous;

        Assert.Throws<ArgumentException>(() => fixture.Service.CaptureExistingCanonicalAccount(
            Fixture.Subject, fixture.User.UserId, capture));
        Assert.Equal(0, callbacks);
    }

    [Fact]
    public async Task Account_writer_is_excluded_during_capture_then_actual_erasure_prevents_recapture()
    {
        using var fixture = new Fixture();
        var eraser = new CommunityAccountErasureService(fixture.Store);
        using var probed = new ManualResetEventSlim();
        bool writerEnteredEarly = true;
        Task? writer = null;
        try
        {
            Assert.True(fixture.Service.CaptureExistingCanonicalAccount(Fixture.Subject, fixture.User.UserId, () =>
            {
                writer = Task.Run(() =>
                {
                    bool entered = Monitor.TryEnter(fixture.Store.Gate);
                    writerEnteredEarly = entered;
                    if (entered) Monitor.Exit(fixture.Store.Gate);
                    probed.Set();
                    eraser.Erase(Fixture.Subject, fixture.User.UserId);
                });
                Assert.True(probed.Wait(TimeSpan.FromSeconds(5)));
                Assert.False(writerEnteredEarly);
                Assert.False(writer.IsCompleted);
                Assert.True(fixture.Store.UsersById.ContainsKey(fixture.User.UserId));
            }));
        }
        finally
        {
            if (writer is not null)
                await writer.WaitAsync(TimeSpan.FromSeconds(10));
        }
        Assert.False(fixture.Service.CaptureExistingCanonicalAccount(
            Fixture.Subject, fixture.User.UserId, () => Assert.Fail("Erased account reached capture.")));
    }

    [Fact]
    public async Task Callback_failure_releases_the_actual_account_gate()
    {
        using var fixture = new Fixture();
        var failure = new InvalidOperationException("capture fixture failure");
        Assert.Same(failure, Assert.Throws<InvalidOperationException>(() =>
            fixture.Service.CaptureExistingCanonicalAccount(Fixture.Subject, fixture.User.UserId, () => throw failure)));

        Assert.True(await Task.Run(() =>
        {
            bool entered = Monitor.TryEnter(fixture.Store.Gate);
            if (entered) Monitor.Exit(fixture.Store.Gate);
            return entered;
        }).WaitAsync(TimeSpan.FromSeconds(5)));
    }

    private sealed class Fixture : IDisposable
    {
        internal const string Subject = "Subject.Case";
        private readonly string _directory = Path.Combine(Path.GetTempPath(), "hub-account-capture-tests", Guid.NewGuid().ToString("N"));
        public Fixture()
        {
            var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            { ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_directory, "community.json") }).Build();
            Store = new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
            Service = new AccountService(Store);
            User = Service.EnsureUser(Subject, "Fixture Runner");
        }
        public CommunityStore Store { get; }
        public AccountService Service { get; }
        public HubUserDto User { get; }
        public void Dispose() { if (Directory.Exists(_directory)) Directory.Delete(_directory, recursive: true); }
    }
}
