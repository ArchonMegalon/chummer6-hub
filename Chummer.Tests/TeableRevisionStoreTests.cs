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
    public async Task Production_request_pacing_is_shared_across_clients_and_does_not_replay_posts()
    {
        var starts = new System.Collections.Concurrent.ConcurrentQueue<long>();
        using var first = new HttpClient(new TeableRequestPacingHandler(new PacedTransport(starts)));
        using var second = new HttpClient(new TeableRequestPacingHandler(new PacedTransport(starts)));
        var origin = new Uri("https://" + Guid.NewGuid().ToString("N") + ".example/");
        var requests = Enumerable.Range(0, 8).Select(async i =>
        {
            using var request = new HttpRequestMessage(i % 2 == 0 ? HttpMethod.Get : HttpMethod.Post, origin);
            using var response = await (i % 2 == 0 ? first : second).SendAsync(request);
            Assert.Equal(HttpStatusCode.TooManyRequests, response.StatusCode);
        });
        await Task.WhenAll(requests);
        long[] ticks = starts.ToArray();
        Assert.Equal(8, ticks.Length); // A 429, including POST, is never replayed.
        for (int i = 1; i < ticks.Length; i++)
            Assert.True(System.Diagnostics.Stopwatch.GetElapsedTime(ticks[i - 1], ticks[i]) >= TimeSpan.FromMilliseconds(245));
    }

    [Fact]
    public async Task Cancellation_while_waiting_for_a_request_slot_never_sends_it()
    {
        var starts = new System.Collections.Concurrent.ConcurrentQueue<long>();
        using var client = new HttpClient(new TeableRequestPacingHandler(new PacedTransport(starts)));
        var origin = new Uri("https://" + Guid.NewGuid().ToString("N") + ".example/");
        using var first = await client.GetAsync(origin);
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(25));
        using var request = new HttpRequestMessage(HttpMethod.Post, origin);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => client.SendAsync(request, cancellation.Token));
        Assert.Single(starts);
    }

    private sealed class PacedTransport(System.Collections.Concurrent.ConcurrentQueue<long> starts) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            starts.Enqueue(System.Diagnostics.Stopwatch.GetTimestamp());
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.TooManyRequests));
        }
    }

    [Theory]
    [InlineData(false, HttpStatusCode.TooManyRequests, "teable_read_rate_limited")]
    [InlineData(true, HttpStatusCode.TooManyRequests, "teable_commit_rate_limited")]
    [InlineData(false, HttpStatusCode.ServiceUnavailable, "teable_read_http_failure")]
    [InlineData(true, HttpStatusCode.ServiceUnavailable, "teable_commit_http_failure")]
    public async Task Account_write_diagnostics_preserve_safe_phase_without_retry_or_response_data(
        bool writing, HttpStatusCode status, string code)
    {
        using var remote = new Remote();
        using var handler = new DiagnosticFailureHandler(remote, writing, status);
        using var client = new HttpClient(handler) { BaseAddress = new Uri("https://teable.example/") };
        using var store = new TeableRevisionStore(client, "tbl1234567890123456", "synthetic-token");
        var authority = new TeableInstallLinkingSnapshotAuthority(store);
        byte[] envelope = "synthetic-protected-envelope"u8.ToArray();
        var request = new InstallLinkingEnvelopeCompareExchangeRequest(0, null, null, 1, Guid.NewGuid(), 2,
            SHA256.HashData(envelope), SHA256.HashData(envelope), envelope);
        using var result = await authority.CompareExchangeAsync(request);
        Assert.False(result.Committed);
        Assert.Null(result.AuthoritativeEnvelope);
        Assert.Equal(code, result.Code);
        Assert.Equal(1, handler.Failures);
        Assert.Equal(writing ? 1 : 0, handler.Posts);
        Assert.Empty(remote.Rows);
        Assert.DoesNotContain("secret-provider-message", result.Code);
        Assert.DoesNotContain("synthetic-token", result.Code);
    }

    private sealed class DiagnosticFailureHandler(HttpMessageHandler inner, bool writing, HttpStatusCode status)
        : DelegatingHandler(inner)
    {
        public int Failures { get; private set; }
        public int Posts { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            bool post = request.Method == HttpMethod.Post;
            if (post) Posts++;
            if (post == writing)
            {
                Failures++;
                return Task.FromResult(new HttpResponseMessage(status)
                    { Content = new StringContent("secret-provider-message synthetic-token") });
            }
            return base.SendAsync(request, ct);
        }
    }

    [Theory]
    [InlineData("success")]
    [InlineData("schema")]
    [InlineData("head")]
    [InlineData("cancel")]
    public async Task Commit_admission_overlaps_fresh_schema_and_head_but_waits_for_both(string outcome)
    {
        using var remote = new Remote();
        using var store = remote.Store();
        var first = await store.CompareExchangeAsync("accounts", null, Guid.NewGuid(), "original"u8.ToArray());
        int posts = remote.HeadPosts, entered = 0, active = 0;
        var both = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var schemaRelease = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var headRelease = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var schemaReturned = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var headReturned = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        async Task Hold(Task release, TaskCompletionSource returned, CancellationToken ct)
        {
            Interlocked.Increment(ref active);
            if (Interlocked.Increment(ref entered) == 2) both.TrySetResult();
            try { await release.WaitAsync(ct); }
            finally { Interlocked.Decrement(ref active); returned.TrySetResult(); }
        }
        remote.BeforeSchemaReadResponse = ct => Hold(schemaRelease.Task, schemaReturned, ct);
        remote.BeforeRecordReadResponse = (row, ct) => row["kind"]!.GetValue<string>() == "head"
            ? Hold(headRelease.Task, headReturned, ct) : Task.CompletedTask;
        if (outcome == "schema") remote.Unique = false;
        if (outcome == "head")
        {
            JsonObject row = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
            JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
            manifest["inlineBase64"] = "Y2hhbmdl";
            row["payload"] = manifest.ToJsonString();
        }
        using var caller = new CancellationTokenSource();
        Task<TeableRevisionStore.Head> write = store.CompareExchangeAsync(
            "accounts", first, Guid.NewGuid(), "successor"u8.ToArray(), caller.Token);
        try
        {
            await both.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(posts, remote.HeadPosts);
            Assert.False(write.IsCompleted);
            if (outcome == "cancel")
            {
                caller.Cancel();
                await Assert.ThrowsAnyAsync<OperationCanceledException>(() => write);
            }
            else
            {
                // A successful or failed first observation must not detach the
                // still-running peer, or admit any POST before both are valid.
                if (outcome == "head")
                {
                    headRelease.TrySetResult();
                    await headReturned.Task.WaitAsync(TimeSpan.FromSeconds(5));
                }
                else
                {
                    schemaRelease.TrySetResult();
                    await schemaReturned.Task.WaitAsync(TimeSpan.FromSeconds(5));
                }
                Assert.False(write.IsCompleted);
                Assert.Equal(posts, remote.HeadPosts);
                schemaRelease.TrySetResult();
                headRelease.TrySetResult();
                if (outcome == "success")
                {
                    var committed = await write;
                    Assert.Equal(2, committed.Revision);
                    Assert.Equal("successor"u8.ToArray(), committed.Bytes);
                }
                else await Assert.ThrowsAsync<InvalidDataException>(() => write);
            }
        }
        finally
        {
            caller.Cancel();
            schemaRelease.TrySetResult();
            headRelease.TrySetResult();
            try { await write; } catch (Exception error) when (error is InvalidDataException or OperationCanceledException) { }
        }
        Assert.Equal(0, active);
        Assert.Equal(posts + (outcome == "success" ? 1 : 0), remote.HeadPosts);
        Assert.Equal(outcome == "success" ? 4 : 2, remote.Rows.Count);
    }

    [Fact]
    public async Task Teable_reads_and_writes_prefer_http2_with_tls_http1_fallback()
    {
        using var remote = new Remote();
        int observed = 0;
        remote.ObserveRequest = request =>
        {
            Assert.Equal("https", request.RequestUri!.Scheme);
            Assert.Equal(HttpVersion.Version20, request.Version);
            Assert.Equal(HttpVersionPolicy.RequestVersionOrLower, request.VersionPolicy);
            observed++;
        };
        await remote.Store().CompareExchangeAsync("transport", null, Guid.NewGuid(), "synthetic"u8.ToArray());
        Assert.True(observed >= 5); // Includes schema/head reads, chunks, head POST and commit readback.
    }

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

    [Theory]
    [InlineData(3)] // The current protected account envelope requires three chunks.
    [InlineData(5)] // A larger envelope must not start an unbounded fan-out.
    public async Task Chunk_reads_use_bounded_remote_batches_and_preserve_exact_order_without_writes(int chunks)
    {
        using var remote = new Remote();
        byte[] bytes = Enumerable.Range(0, (chunks - 1) * 32 * 1024 + 7).Select(i => (byte)(i % 251)).ToArray();
        await remote.Store().CompareExchangeAsync("accounts", null, Guid.NewGuid(), bytes);
        UseLegacyChunkHeads(remote);
        int posts = remote.HeadPosts, reads = remote.GetRequests, calls = 0;
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        remote.BeforeChunkBatchReadResponse = async (rows, ct) =>
        {
            Assert.InRange(rows.Length, 1, 4);
            calls++;
            Array.Reverse(rows); // Provider ordering must never change reconstructed bytes.
            entered.TrySetResult();
            await release.Task.WaitAsync(ct);
        };
        Task<TeableRevisionStore.Head?> read = remote.Store().ReadAsync("accounts");
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(1, calls);
            Assert.False(read.IsCompleted);
        }
        finally { release.TrySetResult(); await read; }
        Assert.Equal(bytes, (await read)!.Bytes);
        Assert.Equal((chunks + 3) / 4, calls);
        Assert.Equal(1 + calls, remote.GetRequests - reads); // One fresh head, then one GET per batch.
        Assert.Equal(posts, remote.HeadPosts);
    }

    [Theory]
    [InlineData(false, 2)]
    [InlineData(true, 2)]
    [InlineData(false, 5)]
    [InlineData(true, 5)]
    public async Task Failed_or_canceled_chunk_batch_never_starts_a_later_batch_or_write(bool cancel, int chunks)
    {
        using var remote = new Remote();
        byte[] bytes = new byte[(chunks - 1) * 32 * 1024 + 7];
        await remote.Store().CompareExchangeAsync("accounts", null, Guid.NewGuid(), bytes);
        UseLegacyChunkHeads(remote);
        int posts = remote.HeadPosts, reads = remote.GetRequests, active = 0;
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        remote.BeforeChunkBatchReadResponse = async (_, ct) =>
        {
            Interlocked.Increment(ref active);
            entered.TrySetResult();
            try
            {
                await release.Task.WaitAsync(ct);
                throw new HttpRequestException("synthetic chunk outage");
            }
            finally { Interlocked.Decrement(ref active); }
        };
        using var cancellation = new CancellationTokenSource();
        Task<TeableRevisionStore.Head?> read = remote.Store().ReadAsync("accounts", cancellation.Token);
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.False(read.IsCompleted);
            if (cancel)
            {
                cancellation.Cancel();
                await Assert.ThrowsAnyAsync<OperationCanceledException>(() => read);
            }
            else
            {
                release.TrySetResult();
                await Assert.ThrowsAsync<HttpRequestException>(() => read);
            }
        }
        finally
        {
            cancellation.Cancel();
            release.TrySetResult();
            try { await read; } catch (Exception error) when (error is HttpRequestException or OperationCanceledException) { }
        }
        Assert.Equal(0, active);
        Assert.Equal(posts, remote.HeadPosts);
        Assert.Equal(2, remote.GetRequests - reads); // No detached peer, later batch or automatic retry.
        remote.BeforeChunkBatchReadResponse = null;
        Assert.Equal(bytes, (await remote.Store().ReadAsync("accounts"))!.Bytes);
    }

    [Theory]
    [InlineData("missing")]
    [InlineData("duplicate")]
    [InlineData("extra")]
    [InlineData("key")]
    [InlineData("stream")]
    [InlineData("kind")]
    [InlineData("revision")]
    [InlineData("length")]
    [InlineData("hash")]
    public async Task Invalid_chunk_batch_is_rejected_without_fallback_or_replay(string fault)
    {
        using var remote = new Remote();
        using var store = remote.Store();
        byte[] bytes = new byte[2 * 32 * 1024 + 7];
        await store.CompareExchangeAsync("accounts", null, Guid.NewGuid(), bytes);
        UseLegacyChunkHeads(remote);
        Assert.Equal(bytes, (await store.ReadAsync("accounts"))!.Bytes); // A prior success is never a fallback.
        int posts = remote.HeadPosts, reads = remote.GetRequests;
        remote.TransformChunkBatch = rows =>
        {
            switch (fault)
            {
                case "missing": return rows[..^1];
                case "duplicate": rows[1] = (JsonObject)rows[0].DeepClone(); break;
                case "extra": return [.. rows, (JsonObject)rows[0].DeepClone()];
                case "key": rows[0]["revision_key"] = "wrong-commit:0"; break;
                case "stream": rows[0]["stream"] = "other-owner"; break;
                case "kind": rows[0]["kind"] = "head"; break;
                case "revision": rows[0]["revision"] = 99L; break;
                case "length": rows[0]["payload"] = "AA=="; break;
                case "hash":
                    byte[] changed = Convert.FromBase64String(rows[0]["payload"]!.GetValue<string>());
                    changed[0] ^= 1;
                    rows[0]["payload"] = Convert.ToBase64String(changed);
                    break;
            }
            return rows;
        };
        await Assert.ThrowsAsync<InvalidDataException>(() => store.ReadAsync("accounts"));
        Assert.Equal(2, remote.GetRequests - reads);
        Assert.Equal(posts, remote.HeadPosts);
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

    private static void UseLegacyChunkHeads(Remote remote)
    {
        foreach (JsonObject row in remote.Rows.Values.Where(row => row["kind"]!.GetValue<string>() == "head"))
        {
            JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
            manifest.Remove("inlinePayloadBase64");
            row["payload"] = manifest.ToJsonString();
        }
    }

    [Theory]
    [InlineData(66_341)] // Current protected account envelope, including its authority header.
    [InlineData(96 * 1024)]
    public async Task Medium_head_reads_once_and_preserves_legacy_rollback_and_fresh_revocation(int length)
    {
        using var remote = new Remote();
        byte[] bytes = Enumerable.Range(0, length).Select(i => (byte)(i % 251)).ToArray();
        using var store = remote.Store();
        var first = await store.CompareExchangeAsync("medium", null, Guid.NewGuid(), bytes);
        int reads = remote.GetRequests;
        Assert.Equal(bytes, (await remote.Store().ReadAsync("medium"))!.Bytes);
        Assert.Equal(1, remote.GetRequests - reads);
        JsonObject row = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
        JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
        Assert.Equal(1, manifest["version"]!.GetValue<int>());
        Assert.Null(manifest["inlineBase64"]); // Old readers retain their 32 KiB contract.
        Assert.Equal(bytes, Convert.FromBase64String(manifest["inlinePayloadBase64"]!.GetValue<string>()));
        // Emulate the old reader ignoring the new optional field, using exactly
        // the chunks retained by this write. No replacement/rebuild is needed.
        manifest.Remove("inlinePayloadBase64");
        row["payload"] = manifest.ToJsonString();
        Assert.Equal(bytes, (await remote.Store().ReadAsync("medium"))!.Bytes);
        bytes[0] ^= 1;
        var revoked = await store.CompareExchangeAsync("medium", first, Guid.NewGuid(), bytes);
        reads = remote.GetRequests;
        Assert.Equal(revoked.Bytes, (await remote.Store().ReadAsync("medium"))!.Bytes);
        Assert.Equal(1, remote.GetRequests - reads);
        remote.FailReads = true;
        await Assert.ThrowsAsync<HttpRequestException>(() => store.ReadAsync("medium"));
    }

    [Theory]
    [InlineData("base64")]
    [InlineData("length")]
    [InlineData("hash")]
    [InlineData("both")]
    [InlineData("oversized")]
    public async Task Invalid_medium_inline_head_never_falls_back_to_valid_chunks(string fault)
    {
        using var remote = new Remote();
        byte[] bytes = new byte[66_341];
        await remote.Store().CompareExchangeAsync("medium", null, Guid.NewGuid(), bytes);
        JsonObject row = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
        JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
        if (fault == "base64") manifest["inlinePayloadBase64"] = "not base64";
        if (fault == "length") manifest["inlinePayloadBase64"] = "AA==";
        if (fault == "hash") { bytes[0] = 1; manifest["inlinePayloadBase64"] = Convert.ToBase64String(bytes); }
        if (fault == "both") manifest["inlineBase64"] = Convert.ToBase64String(bytes);
        if (fault == "oversized") manifest["length"] = 96 * 1024 + 1;
        row["payload"] = manifest.ToJsonString();
        int reads = remote.GetRequests, posts = remote.HeadPosts;
        await Assert.ThrowsAsync<InvalidDataException>(() => remote.Store().ReadAsync("medium"));
        Assert.Equal(1, remote.GetRequests - reads);
        Assert.Equal(posts, remote.HeadPosts);
    }

    [Fact]
    public async Task Large_heads_remain_chunked_and_cannot_admit_legacy_inline_payloads()
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
    public async Task Above_medium_limit_retains_chunked_format_and_rejects_extended_inline()
    {
        using var remote = new Remote();
        byte[] bytes = new byte[96 * 1024 + 1];
        await remote.Store().CompareExchangeAsync("large", null, Guid.NewGuid(), bytes);
        JsonObject row = remote.Rows.Values.Single(row => row["kind"]!.GetValue<string>() == "head");
        JsonObject manifest = JsonNode.Parse(row["payload"]!.GetValue<string>())!.AsObject();
        Assert.Null(manifest["inlineBase64"]);
        Assert.Null(manifest["inlinePayloadBase64"]);
        int reads = remote.GetRequests;
        Assert.Equal(bytes, (await remote.Store().ReadAsync("large"))!.Bytes);
        Assert.Equal(2, remote.GetRequests - reads);
        manifest["inlinePayloadBase64"] = Convert.ToBase64String(bytes);
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
        var error = await Assert.ThrowsAsync<TeableRequestFailureException>(() => remote.Store().ReadAsync("accounts"));
        Assert.Equal(HttpStatusCode.Unauthorized, error.StatusCode);
        Assert.False(error.Writing);
        Assert.DoesNotContain("secret-provider-message", error.ToString());
        Assert.DoesNotContain("synthetic-token", error.ToString());
    }

    [Theory]
    [InlineData("schema", false)]
    [InlineData("head", false)]
    [InlineData("chunk", false)]
    [InlineData("chunk-write", false)]
    [InlineData("head-write", false)]
    [InlineData("head", true)]
    [InlineData("head-write", true)]
    public async Task Stalled_response_body_obeys_request_deadline_or_caller_cancellation_without_replay(
        string phase, bool callerCancels)
    {
        using var remote = new Remote();
        byte[] payload = new byte[32 * 1024 + 7];
        if (phase == "chunk")
        {
            await remote.Store().CompareExchangeAsync("accounts", null, Guid.NewGuid(), payload);
            UseLegacyChunkHeads(remote);
        }
        using var handler = new StalledResponseHandler(remote, phase);
        using var client = new HttpClient(handler)
        {
            BaseAddress = new Uri("https://teable.example/"),
            Timeout = callerCancels ? Timeout.InfiniteTimeSpan : TimeSpan.FromMilliseconds(250)
        };
        using var store = new TeableRevisionStore(client, "tbl1234567890123456", "synthetic-token");
        using var caller = new CancellationTokenSource();
        Guid commit = Guid.NewGuid();
        Task operation = phase switch
        {
            "schema" => store.VerifySchemaAsync(caller.Token),
            "chunk-write" or "head-write" => store.CompareExchangeAsync("accounts", null, commit, "synthetic"u8.ToArray(), caller.Token),
            _ => store.ReadAsync("accounts", caller.Token)
        };
        try
        {
            await handler.Body.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            int admittedRequests = handler.Requests;
            if (callerCancels) caller.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => operation.WaitAsync(TimeSpan.FromSeconds(2)));
            Assert.True(handler.Body.Disposed);
            Assert.Equal(admittedRequests, handler.Requests); // Neither a write nor a read is automatically replayed.
            if (phase == "head-write")
            {
                Assert.Equal(1, remote.HeadPosts); // Timeout does not mean the write was uncommitted.
                handler.Enabled = false;
                var recovered = await store.ReadAsync("accounts");
                Assert.Equal(commit, recovered!.Commit);
                Assert.Equal("synthetic"u8.ToArray(), recovered.Bytes);
                Assert.Equal(1, remote.HeadPosts);
            }
        }
        finally
        {
            caller.Cancel();
            try { await operation; } catch (OperationCanceledException) { }
        }
    }

    private sealed class StalledResponseHandler(HttpMessageHandler inner, string phase) : DelegatingHandler(inner)
    {
        public StalledBody Body { get; } = new();
        public int Requests { get; private set; }
        public bool Enabled { get; set; } = true;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Requests++;
            var response = await base.SendAsync(request, ct);
            string content = request.Content is null ? "" : await request.Content.ReadAsStringAsync(ct);
            string query = Uri.UnescapeDataString(request.RequestUri!.Query);
            bool matches = phase switch
            {
                "schema" => request.RequestUri.AbsolutePath.EndsWith("/field", StringComparison.Ordinal),
                "head" => request.Method == HttpMethod.Get && query.Contains("\"kind\"", StringComparison.Ordinal),
                "chunk" => request.Method == HttpMethod.Get && query.Contains(":chunk:", StringComparison.Ordinal),
                "chunk-write" => request.Method == HttpMethod.Post && content.Contains("\"kind\":\"chunk\"", StringComparison.Ordinal),
                "head-write" => request.Method == HttpMethod.Post && content.Contains("\"kind\":\"head\"", StringComparison.Ordinal),
                _ => throw new InvalidOperationException("Unknown synthetic phase.")
            };
            if (Enabled && matches)
            {
                Enabled = false;
                response.Content.Dispose();
                response.Content = new StreamContent(Body);
            }
            return response;
        }
    }

    private sealed class StalledBody : Stream
    {
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool Disposed { get; private set; }
        private bool _prefixRead;
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            if (!_prefixRead)
            {
                _prefixRead = true;
                buffer.Span[0] = (byte)'{';
                return 1;
            }
            Entered.TrySetResult();
            await Task.Delay(Timeout.InfiniteTimeSpan, ct);
            return 0;
        }
        protected override void Dispose(bool disposing) { Disposed = true; base.Dispose(disposing); }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
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
        public Func<CancellationToken, Task>? BeforeSchemaReadResponse { get; set; }
        public Func<JsonObject, CancellationToken, Task>? BeforeChunkReadResponse { get; set; }
        public Func<JsonObject[], CancellationToken, Task>? BeforeChunkBatchReadResponse { get; set; }
        public Func<JsonObject[], JsonObject[]>? TransformChunkBatch { get; set; }
        public Func<JsonObject, CancellationToken, Task>? BeforeRecordReadResponse { get; set; }
        public Action<HttpRequestMessage>? ObserveRequest { get; set; }
        public int HeadPosts { get; private set; }
        private int _getRequests;
        public int GetRequests => Volatile.Read(ref _getRequests);
        private int _headReads;
        private readonly TaskCompletionSource _headBarrier = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TeableRevisionStore Store() => new(new HttpClient(this, disposeHandler: false)
            { BaseAddress = new Uri("https://teable.example/") }, "tbl1234567890123456", "synthetic-token");

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            ObserveRequest?.Invoke(request);
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
            {
                if (BeforeSchemaReadResponse is { } beforeSchema) await beforeSchema(ct);
                return Response(new[] { new { name = "revision_key", type = "singleLineText", unique = Unique, notNull = true },
                    new { name = "stream", type = "singleLineText", unique = false, notNull = false },
                    new { name = "kind", type = "singleLineText", unique = false, notNull = false },
                    new { name = "revision", type = "number", unique = false, notNull = false },
                    new { name = "payload", type = "longText", unique = false, notNull = false } });
            }
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
            var filter = JsonNode.Parse(filterJson)!;
            var predicates = filter["filterSet"]!.AsArray();
            bool any = filter["conjunction"]!.GetValue<string>() == "or";
            int take = int.Parse(request.RequestUri.Query.Split('&')
                .Single(pair => pair.TrimStart('?').StartsWith("take=", StringComparison.Ordinal)).Split('=', 2)[1],
                System.Globalization.CultureInfo.InvariantCulture);
            bool headRead = predicates.Any(p => p!["fieldId"]!.GetValue<string>() == "kind");
            JsonObject[] rows;
            lock (Rows)
            {
                bool Matches(JsonObject row, JsonNode? p) => row[p!["fieldId"]!.GetValue<string>()]!.GetValue<string>()
                    == p["value"]!.GetValue<string>();
                rows = Rows.Values.Where(row => any ? predicates.Any(p => Matches(row, p)) : predicates.All(p => Matches(row, p)))
                    .OrderByDescending(row => row["revision"]!.GetValue<long>())
                    .Take(take).Select(row => (JsonObject)row.DeepClone()).ToArray();
            }
            if (rows is [var record] && BeforeRecordReadResponse is { } beforeRecord)
                await beforeRecord(record, ct);
            if (headRead && HoldTwoEmptyHeadReads)
            {
                if (Interlocked.Increment(ref _headReads) == 2) { HoldTwoEmptyHeadReads = false; _headBarrier.SetResult(); }
                await _headBarrier.Task.WaitAsync(TimeSpan.FromSeconds(5), ct);
            }
            if (!headRead && rows is [var chunk] && chunk["kind"]!.GetValue<string>() == "chunk"
                && BeforeChunkReadResponse is { } beforeChunk)
                await beforeChunk(chunk, ct);
            if (any)
            {
                if (BeforeChunkBatchReadResponse is { } beforeBatch) await beforeBatch(rows, ct);
                if (TransformChunkBatch is { } transform) rows = transform(rows);
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
