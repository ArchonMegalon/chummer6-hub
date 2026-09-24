using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Services;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class IdentityTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "identity-teable-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration(string host) => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["CHUMMER_IDENTITY_STORAGE_PROVIDER"] = "teable",
        ["CHUMMER_IDENTITY_STORE_PATH"] = Path.Combine(_root, host, "identity.json"),
        ["IDENTITY_EMAIL_START_ENABLED"] = "true",
        ["IDENTITY_EMAIL_START_MIN_SECONDS_BETWEEN_RECIPIENT_ATTEMPTS"] = "120"
    }).Build();
    private IdentityAccessService Service(Remote remote, string host = "host-a", Mail? mail = null)
        => new(Configuration(host), NullLogger<IdentityAccessService>.Instance, mail ?? new(), remote.Store());
    private static IdentitySessionIssueRequest Request(string subject = "subject-a") => new(subject, "Synthetic runner", "runner@example.invalid", ["player"]);

    [Fact]
    public void Issued_session_and_roles_restore_from_primary_without_local_account_files()
    {
        using var remote = new Remote();
        var issued = Service(remote).IssueSession(Request());
        var restored = Service(remote, "new-host");
        Assert.True(restored.Introspect(new(issued.AccessToken)).Active);
        Assert.Equal(issued.SubjectId, restored.GetSubject(issued.SubjectId)!.SubjectId);
        Assert.False(Directory.Exists(_root));
        foreach (var row in remote.Rows.Values.Where(row => row["kind"]!.GetValue<string>() == "chunk"))
        {
            string payload = Encoding.UTF8.GetString(Convert.FromBase64String(row["payload"]!.GetValue<string>()));
            Assert.DoesNotContain(issued.AccessToken, payload);
            Assert.DoesNotContain(issued.RefreshToken, payload);
        }
    }

    [Fact]
    public void Existing_reader_observes_remote_revocation_and_role_removal_before_authorizing()
    {
        using var remote = new Remote();
        var first = Service(remote);
        var issued = first.IssueSession(Request() with { RequestedRoles = ["player", "admin"] });
        var second = Service(remote, "host-b");
        Assert.Contains("admin", second.Introspect(new(issued.AccessToken)).Roles!);
        first.SetRoles(issued.SubjectId, new(["player"]));
        Assert.DoesNotContain("admin", second.Introspect(new(issued.AccessToken)).Roles!);
        first.RevokeSession(new(issued.AccessToken));
        Assert.False(second.Introspect(new(issued.AccessToken)).Active);
        Assert.False(Service(remote, "cold-host").Introspect(new(issued.AccessToken)).Active);
    }

    [Fact]
    public void Backend_outage_never_uses_cached_or_local_authorization()
    {
        using var remote = new Remote();
        var service = Service(remote);
        var issued = service.IssueSession(Request());
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => service.Introspect(new(issued.AccessToken)));
        Assert.Throws<HttpRequestException>(() => service.GetSubject(issued.SubjectId));
        Assert.Throws<HttpRequestException>(() => Service(remote, "new-host"));
        Assert.False(service.IsStorageReady());
        remote.FailReads = false;
        Assert.True(service.IsStorageReady());
        Assert.True(service.Introspect(new(issued.AccessToken)).Active);
    }

    [Fact]
    public void Conflict_after_refresh_does_not_revive_a_revoked_session_or_serve_uncommitted_memory()
    {
        using var remote = new Remote();
        var first = Service(remote);
        var issued = first.IssueSession(Request());
        var other = Service(remote, "host-b");
        remote.BeforeHeadPost = () => other.RevokeSession(new(issued.AccessToken));
        Assert.Throws<TeableRevisionConflictException>(() => first.SetRoles(issued.SubjectId, new(["admin"])));
        Assert.Throws<InvalidOperationException>(() => first.Introspect(new(issued.AccessToken)));
        Assert.False(first.IsStorageReady());
        var cold = Service(remote, "cold-host");
        Assert.False(cold.Introspect(new(issued.AccessToken)).Active);
        Assert.DoesNotContain("admin", cold.GetSubject(issued.SubjectId)!.Roles);
    }

    [Fact]
    public void Uncertain_write_requires_cold_reconciliation_and_does_not_replay()
    {
        using var remote = new Remote();
        var first = Service(remote);
        var issued = first.IssueSession(Request());
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => first.RevokeSession(new(issued.AccessToken)));
        int posts = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => first.Introspect(new(issued.AccessToken)));
        Assert.Equal(posts, remote.HeadPosts);
        Assert.False(Service(remote, "recovery").Introspect(new(issued.AccessToken)).Active);
        Assert.Equal(posts, remote.HeadPosts);
    }

    [Fact]
    public void Email_ticket_is_consumed_once_in_one_commit_and_delivery_is_not_replayed()
    {
        using var remote = new Remote();
        var mail = new Mail();
        var entry = Service(remote, mail: mail).StartEmailEntry(new("email@example.invalid", "Synthetic"));
        Assert.Equal(1, mail.Deliveries);
        Assert.False(string.IsNullOrEmpty(entry.TicketId));
        int posts = remote.HeadPosts;
        var issue = Service(remote, "new-host", mail).CompleteEmailEntry(new(entry.TicketId));
        Assert.Equal(posts + 1, remote.HeadPosts);
        Assert.Throws<KeyNotFoundException>(() => Service(remote).CompleteEmailEntry(new(entry.TicketId)));
        Assert.True(Service(remote).Introspect(new(issue.AccessToken)).Active);
        Assert.Equal(1, mail.Deliveries);
        Service(remote, "another-host", mail).StartEmailEntry(new("email@example.invalid", "Synthetic"));
        Assert.Equal(1, mail.Deliveries); // Recipient cooldown also survived loss of the first host.
    }

    [Fact]
    public void Competing_email_completion_cannot_issue_two_sessions()
    {
        using var remote = new Remote();
        var first = Service(remote);
        var entry = first.StartEmailEntry(new("race@example.invalid", "Synthetic"));
        var second = Service(remote, "host-b");
        IdentitySessionIssueResponse? winner = null;
        remote.BeforeHeadPost = () => winner = second.CompleteEmailEntry(new(entry.TicketId));
        Assert.Throws<TeableRevisionConflictException>(() => first.CompleteEmailEntry(new(entry.TicketId)));
        Assert.NotNull(winner);
        Assert.True(Service(remote, "cold-host").Introspect(new(winner.AccessToken)).Active);
        Assert.Throws<KeyNotFoundException>(() => Service(remote).CompleteEmailEntry(new(entry.TicketId)));
        Assert.False(first.IsStorageReady());
    }

    [Fact]
    public void Teable_configuration_never_silently_falls_back_or_imports_a_local_file()
    {
        Assert.Throws<InvalidOperationException>(() => new IdentityAccessService(Configuration("missing"), NullLogger<IdentityAccessService>.Instance, new Mail()));
        using var remote = new Remote();
        string path = Path.Combine(_root, "host-a", "identity.json");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "stale-local-account-data");
        Assert.Null(Service(remote).GetSubject("subject-a"));
        Assert.Equal("stale-local-account-data", File.ReadAllText(path));
    }

    [Fact]
    public async Task Malformed_remote_snapshot_is_not_reset_or_accepted()
    {
        using var remote = new Remote();
        await remote.Store().CompareExchangeAsync("identity", null, Guid.NewGuid(), "{}"u8.ToArray());
        Assert.Throws<InvalidDataException>(() => Service(remote));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Runtime_token_file_is_private_bounded_and_never_followed_through_a_link()
    {
        if (!OperatingSystem.IsLinux() || System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture != System.Runtime.InteropServices.Architecture.X64) return;
        Directory.CreateDirectory(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string file = Path.Combine(_root, "teable-token");
        File.WriteAllText(file, "synthetic-token\n");
        File.SetUnixFileMode(file, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        using var store = TeableRevisionStore.OpenFromPrivateTokenFile(new Uri("https://teable.example/"), "tbl1234567890123456", file);
        string link = Path.Combine(_root, "token-link");
        File.CreateSymbolicLink(link, file);
        Assert.Throws<IOException>(() => TeableRevisionStore.OpenFromPrivateTokenFile(new Uri("https://teable.example/"), "tbl1234567890123456", link));
        File.SetUnixFileMode(file, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.OtherRead);
        Assert.Throws<UnauthorizedAccessException>(() => TeableRevisionStore.OpenFromPrivateTokenFile(new Uri("https://teable.example/"), "tbl1234567890123456", file));
        Assert.Throws<InvalidDataException>(() => TeableRevisionStore.Open(new Uri("http://teable.example/"), "tbl1234567890123456", "synthetic"));
    }

    [Fact]
    public void Historical_erasure_is_not_misreported_as_complete()
    {
        using var remote = new Remote();
        var service = Service(remote);
        var issued = service.IssueSession(Request());
        int posts = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => service.EraseSubject(issued.SubjectId));
        Assert.Equal(posts, remote.HeadPosts);
        Assert.NotNull(service.GetSubject(issued.SubjectId));
    }

    private sealed class Mail : IIdentityEmailDeliveryService
    {
        public int Deliveries { get; private set; }
        public IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
        {
            Deliveries++;
            return new("preview_inline_link", "Synthetic test only", true, ExposeInlinePreviewTicket: true);
        }
        public IdentityEmailDeliveryStatusResponse GetStatus() => new([], [], DateTimeOffset.UtcNow);
        public void RecordStartGuardrailBlock(string email, string deliveryMode, string previewNote) { }
        public IdentityEmailWebhookAckResponse RecordEmailitWebhook(JsonElement payload) => throw new NotSupportedException();
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
}
