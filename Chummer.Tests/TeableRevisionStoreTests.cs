using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services.Teable;
using Chummer.Storage.Teable;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using System.Security.Cryptography;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.DataProtection.KeyManagement;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class TeableRevisionStoreTests
{
    [Fact]
    public void Real_account_store_and_keyring_recover_from_remote_bytes_with_a_new_empty_local_root()
    {
        using var remote = new Remote();
        string root = Path.Combine(Path.GetTempPath(), "teable-account-restore-" + Guid.NewGuid().ToString("N"));
        ServiceProvider Services()
        {
            var services = new ServiceCollection();
            services.AddDataProtection().SetApplicationName("Chummer.Run.Api");
            services.Configure<KeyManagementOptions>(options =>
            {
                options.XmlRepository = new TeableDataProtectionKeyRepository(remote.Store());
                options.XmlEncryptor = null;
            });
            return services.BuildServiceProvider();
        }
        InstallLinkingStore AccountStore(string host, IServiceProvider services)
        {
            var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
                { ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(root, host, "install-linking-store.json") }).Build();
            var authority = new InstallLinkingPostgresAuthorityCoordinator(new TeableInstallLinkingSnapshotAuthority(remote.Store()), "teable");
            return new(configuration, services.GetRequiredService<IDataProtectionProvider>(),
                NullLogger<InstallLinkingStore>.Instance, authority);
        }
        try
        {
            using (var firstServices = Services())
            using (var first = AccountStore("host-a", firstServices))
            {
                lock (first.Gate)
                {
                    first.GrantsById["grant"] = new InstallationGrantDto("grant", "installation", InstallationGrantStates.Active,
                        "private-synthetic-token", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddHours(1), "user", "subject");
                    first.PersistLocked();
                }
            }
            Assert.False(Directory.Exists(Path.Combine(root, "host-b")));
            using var recoveredServices = Services();
            using var recovered = AccountStore("host-b", recoveredServices);
            Assert.Equal("private-synthetic-token", Assert.Single(recovered.GrantsById.Values).AccessToken);
            Assert.DoesNotContain("private-synthetic-token", File.ReadAllText(Path.Combine(root, "host-b", "install-linking-store.json")));
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, recursive: true); }
    }

    [Fact]
    public async Task Account_authority_preserves_exact_protected_bytes_and_rejects_old_generation()
    {
        using var remote = new Remote();
        var authority = new TeableInstallLinkingSnapshotAuthority(remote.Store());
        using var empty = await authority.ReadCurrentAsync();
        Assert.True(empty.IsEmpty);
        byte[] envelope = "synthetic-protected-envelope"u8.ToArray();
        var request = new InstallLinkingEnvelopeCompareExchangeRequest(0, null, null, 1, Guid.NewGuid(),
            InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion, SHA256.HashData("snapshot"u8), SHA256.HashData(envelope), envelope);
        using var committed = await authority.CompareExchangeAsync(request);
        Assert.Equal(InstallLinkingEnvelopeCommitDisposition.Applied, committed.Disposition);
        var restarted = new TeableInstallLinkingSnapshotAuthority(remote.Store());
        using var restored = await restarted.ReadCurrentAsync();
        Assert.Equal(envelope, restored.ProtectedEnvelope);
        Assert.Equal(request.SnapshotSha256, restored.SnapshotSha256);
        Assert.Equal(request.EnvelopeSha256, restored.EnvelopeSha256);
        using var repeated = await restarted.CompareExchangeAsync(request);
        Assert.Equal(InstallLinkingEnvelopeCommitDisposition.AlreadyCommitted, repeated.Disposition);
        using var conflict = await restarted.CompareExchangeAsync(request with { CommitId = Guid.NewGuid() });
        Assert.Equal(InstallLinkingEnvelopeCommitDisposition.Conflict, conflict.Disposition);
        await Assert.ThrowsAsync<InvalidDataException>(() => restarted.CompareExchangeAsync(request with { EnvelopeSha256 = new byte[32] }));
        Assert.True((await restarted.CheckReadinessAsync()).Ready);
        Assert.False((object)restarted is IInstallLinkingSnapshotReadFence);
    }

    [Fact]
    public async Task Multi_chunk_primary_state_reopens_in_a_new_client_without_local_files()
    {
        using var remote = new Remote();
        byte[] original = Enumerable.Range(0, 100_000).Select(i => (byte)(i % 251)).ToArray();
        var first = await remote.Store().CompareExchangeAsync("accounts", null, Guid.NewGuid(), original);
        var reopened = await remote.Store().ReadAsync("accounts");
        Assert.Equal(1, first.Revision);
        Assert.NotNull(reopened);
        Assert.Equal(original, reopened.Bytes);
        Assert.Equal(first.Commit, reopened.Commit);
        Assert.Null(await remote.Store().ReadAsync("other-owner"));
    }

    [Fact]
    public async Task Stale_revision_cannot_overwrite_a_revocation_or_dispatch_fence()
    {
        using var remote = new Remote();
        var first = await remote.Store().CompareExchangeAsync("grant", null, Guid.NewGuid(), "active"u8.ToArray());
        var revoked = await remote.Store().CompareExchangeAsync("grant", first, Guid.NewGuid(), "revoked"u8.ToArray());
        await Assert.ThrowsAsync<TeableRevisionConflictException>(() => remote.Store()
            .CompareExchangeAsync("grant", first, Guid.NewGuid(), "active"u8.ToArray()));
        Assert.Equal(revoked.Commit, (await remote.Store().ReadAsync("grant"))!.Commit);
    }

    [Fact]
    public async Task Competing_writers_with_the_same_expected_head_get_one_winner()
    {
        using var remote = new Remote { HoldTwoEmptyHeadReads = true };
        async Task<bool> Attempt(string value)
        {
            try { await remote.Store().CompareExchangeAsync("race", null, Guid.NewGuid(), Encoding.UTF8.GetBytes(value)); return true; }
            catch (TeableRevisionConflictException) { return false; }
        }
        bool[] results = await Task.WhenAll(Attempt("a"), Attempt("b"));
        Assert.Single(results, result => result);
        Assert.Single(remote.Rows.Values, row => row["kind"]!.GetValue<string>() == "head");
    }

    [Fact]
    public async Task Lost_commit_response_is_reconciled_without_a_second_post()
    {
        using var remote = new Remote { LoseCommitResponse = true };
        Guid commit = Guid.NewGuid();
        var first = await remote.Store().CompareExchangeAsync("book-job", null, commit, "dispatched"u8.ToArray());
        var replay = await remote.Store().CompareExchangeAsync("book-job", null, commit, "dispatched"u8.ToArray());
        Assert.Equal(first.Commit, replay.Commit);
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public async Task Missing_constraint_rejects_before_any_write()
    {
        using var remote = new Remote { Unique = false };
        await Assert.ThrowsAsync<InvalidDataException>(() => remote.Store()
            .CompareExchangeAsync("accounts", null, Guid.NewGuid(), "payload"u8.ToArray()));
        Assert.Empty(remote.Rows);
    }

    [Fact]
    public async Task Small_head_reads_exact_remote_bytes_in_one_request_without_caching_authority()
    {
        using var remote = new Remote();
        using var store = remote.Store();
        var first = await store.CompareExchangeAsync("grant", null, Guid.NewGuid(), "active"u8.ToArray());
        int reads = remote.GetRequests;
        Assert.Equal(first.Bytes, (await store.ReadAsync("grant"))!.Bytes);
        Assert.Equal(1, remote.GetRequests - reads);
        var revoked = await remote.Store().CompareExchangeAsync("grant", first, Guid.NewGuid(), "revoked"u8.ToArray());
        reads = remote.GetRequests;
        Assert.Equal(revoked.Bytes, (await store.ReadAsync("grant"))!.Bytes);
        Assert.Equal(1, remote.GetRequests - reads);
        remote.FailReads = true;
        await Assert.ThrowsAsync<HttpRequestException>(() => store.ReadAsync("grant"));
    }

    [Fact]
    public async Task Inline_head_keeps_complete_legacy_chunks_for_rollback_and_reads_old_manifests()
    {
        using var remote = new Remote();
        byte[] bytes = Enumerable.Range(0, 32 * 1024).Select(i => (byte)(i % 251)).ToArray();
        var written = await remote.Store().CompareExchangeAsync("compat", null, Guid.NewGuid(), bytes);
        JsonObject row = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
        JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
        Assert.Equal(1, manifest["version"]!.GetValue<int>());
        Assert.Equal(bytes, Convert.FromBase64String(manifest["inlineBase64"]!.GetValue<string>()));
        Assert.Equal(bytes, Convert.FromBase64String(remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "chunk")["payload"]!.GetValue<string>()));
        manifest.Remove("inlineBase64"); // The existing v1 reader ignores unknown fields and follows these chunks.
        row["payload"] = manifest.ToJsonString();
        int reads = remote.GetRequests;
        var reopened = await remote.Store().ReadAsync("compat");
        Assert.Equal(written.Commit, reopened!.Commit);
        Assert.Equal(bytes, reopened.Bytes);
        Assert.Equal(2, remote.GetRequests - reads);
    }

    [Theory]
    [InlineData("")]
    [InlineData("not-base64")]
    [InlineData("Y2hhbmdl")]
    public async Task Invalid_inline_bytes_fail_closed_even_with_valid_legacy_chunks(string inline)
    {
        using var remote = new Remote();
        await remote.Store().CompareExchangeAsync("accounts", null, Guid.NewGuid(), "secret"u8.ToArray());
        JsonObject row = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
        JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
        manifest["inlineBase64"] = inline;
        row["payload"] = manifest.ToJsonString();
        int reads = remote.GetRequests;
        await Assert.ThrowsAsync<InvalidDataException>(() => remote.Store().ReadAsync("accounts"));
        Assert.Equal(1, remote.GetRequests - reads); // No fallback to a second representation after corruption.
    }

    [Fact]
    public async Task Large_heads_remain_chunked_and_cannot_admit_inline_payloads()
    {
        using var remote = new Remote();
        byte[] bytes = new byte[32 * 1024 + 1];
        await remote.Store().CompareExchangeAsync("large", null, Guid.NewGuid(), bytes);
        JsonObject row = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
        JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
        Assert.Null(manifest["inlineBase64"]);
        manifest["inlineBase64"] = Convert.ToBase64String(bytes);
        row["payload"] = manifest.ToJsonString();
        await Assert.ThrowsAsync<InvalidDataException>(() => remote.Store().ReadAsync("large"));
    }

    [Fact]
    public async Task Corrupt_chunk_is_not_replaced_with_an_empty_or_local_state()
    {
        using var remote = new Remote();
        await remote.Store().CompareExchangeAsync("accounts", null, Guid.NewGuid(), "secret"u8.ToArray());
        JsonObject head = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
        JsonObject manifest = JsonNode.Parse(head["payload"]!.GetValue<string>())!.AsObject();
        manifest.Remove("inlineBase64"); // Exercise the retained legacy chunk reader.
        head["payload"] = manifest.ToJsonString();
        remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "chunk")["payload"] = "Y2hhbmdl";
        await Assert.ThrowsAsync<InvalidDataException>(() => remote.Store().ReadAsync("accounts"));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Oversized_response_is_rejected_before_materialization(bool contentLength)
    {
        using var remote = new Remote { Oversized = true, ContentLength = contentLength };
        await Assert.ThrowsAsync<InvalidDataException>(() => remote.Store().ReadAsync("accounts"));
    }

    [Fact]
    public async Task Rejected_credentials_do_not_leak_response_bodies()
    {
        using var remote = new Remote { Unauthorized = true };
        var error = await Assert.ThrowsAsync<IOException>(() => remote.Store().ReadAsync("accounts"));
        Assert.DoesNotContain("secret-provider-message", error.ToString());
        Assert.DoesNotContain("synthetic-token", error.ToString());
    }

    internal sealed class Remote : HttpMessageHandler
    {
        public Dictionary<string, JsonObject> Rows { get; } = new();
        public bool Unique { get; set; } = true;
        public bool LoseCommitResponse { get; set; }
        public bool HoldTwoEmptyHeadReads { get; set; }
        public bool Oversized { get; set; }
        public bool ContentLength { get; set; }
        public bool Unauthorized { get; set; }
        public bool FailReads { get; set; }
        public bool CommitThenFailHard { get; set; }
        public Action? BeforeHeadPost { get; set; }
        public Action? BeforeHeadReadResponse { get; set; }
        public int HeadPosts { get; private set; }
        private int _getRequests;
        public int GetRequests => Volatile.Read(ref _getRequests);
        private int _headReads;
        private readonly TaskCompletionSource _headBarrier = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TeableRevisionStore Store() => new(new HttpClient(this, disposeHandler: false)
            { BaseAddress = new Uri("https://teable.example/") }, "tbl1234567890123456", "synthetic-token");

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (request.Method == HttpMethod.Get) Interlocked.Increment(ref _getRequests);
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("synthetic-token", request.Headers.Authorization.Parameter);
            if (FailReads && request.Method == HttpMethod.Get) throw new HttpRequestException("synthetic outage");
            if (Unauthorized) return new(HttpStatusCode.Unauthorized) { Content = new StringContent("secret-provider-message") };
            if (Oversized)
            {
                HttpContent content = ContentLength ? new StringContent(new string('x', 300_000))
                    : new StreamContent(new NonSeekStream(300_000));
                return new(HttpStatusCode.OK) { Content = content };
            }
            if (request.RequestUri!.AbsolutePath.EndsWith("/field", StringComparison.Ordinal))
                return Response(new[] { new { name = "revision_key", type = "singleLineText", unique = Unique, notNull = true },
                    new { name = "stream", type = "singleLineText", unique = false, notNull = false },
                    new { name = "kind", type = "singleLineText", unique = false, notNull = false },
                    new { name = "revision", type = "number", unique = false, notNull = false },
                    new { name = "payload", type = "longText", unique = false, notNull = false } });
            if (request.Method == HttpMethod.Post)
            {
                string body = await request.Content!.ReadAsStringAsync(ct);
                Assert.DoesNotContain("synthetic-token", body);
                var fields = JsonNode.Parse(body)!["records"]![0]!["fields"]!.AsObject();
                string key = fields["revision_key"]!.GetValue<string>();
                if (fields["kind"]!.GetValue<string>() == "head" && BeforeHeadPost is { } before)
                {
                    BeforeHeadPost = null;
                    before();
                }
                lock (Rows)
                {
                    if (!Rows.TryAdd(key, (JsonObject)fields.DeepClone())) return new(HttpStatusCode.BadRequest);
                    if (fields["kind"]!.GetValue<string>() == "head")
                    {
                        HeadPosts++;
                        if (CommitThenFailHard) { CommitThenFailHard = false; return new(HttpStatusCode.ServiceUnavailable); }
                        if (LoseCommitResponse) { LoseCommitResponse = false; throw new HttpRequestException("synthetic lost response"); }
                    }
                }
                return Response(new { records = Array.Empty<object>() }, HttpStatusCode.Created);
            }
            string filterJson = Uri.UnescapeDataString(request.RequestUri.Query.Split('&')
                .Single(pair => pair.TrimStart('?').StartsWith("filter=", StringComparison.Ordinal)).Split('=', 2)[1]);
            var predicates = JsonNode.Parse(filterJson)!["filterSet"]!.AsArray();
            bool headRead = predicates.Any(p => p!["fieldId"]!.GetValue<string>() == "kind");
            JsonObject[] rows;
            lock (Rows)
            {
                rows = Rows.Values.Where(row => predicates.All(p => row[p!["fieldId"]!.GetValue<string>()]!.GetValue<string>()
                        == p["value"]!.GetValue<string>())).OrderByDescending(row => row["revision"]!.GetValue<long>())
                    .Take(headRead ? 1 : 2).Select(row => (JsonObject)row.DeepClone()).ToArray();
            }
            if (headRead && HoldTwoEmptyHeadReads)
            {
                if (Interlocked.Increment(ref _headReads) == 2) { HoldTwoEmptyHeadReads = false; _headBarrier.SetResult(); }
                await _headBarrier.Task.WaitAsync(TimeSpan.FromSeconds(5), ct);
            }
            if (headRead && BeforeHeadReadResponse is { } beforeResponse)
            {
                BeforeHeadReadResponse = null;
                beforeResponse();
            }
            return Response(new { records = rows.Select(row => new { fields = row }).ToArray() });
        }

        private static HttpResponseMessage Response(object value, HttpStatusCode status = HttpStatusCode.OK)
            => new(status) { Content = new StringContent(JsonSerializer.Serialize(value), Encoding.UTF8, "application/json") };
    }

    private sealed class NonSeekStream(int length) : Stream
    {
        private int _remaining = length;
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count)
        {
            int read = Math.Min(count, _remaining);
            buffer.AsSpan(offset, read).Fill((byte)'x');
            _remaining -= read;
            return read;
        }
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}
