using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Storage.Teable;
using Xunit;

namespace Chummer.Tests;

// Shared HTTP fixture for revision-store tests and focused persistence test targets.
public sealed partial class TeableRevisionStoreTests
{
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
        public Func<JsonObject, CancellationToken, Task>? BeforeChunkWriteResponse { get; set; }
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
                if (fields["kind"]!.GetValue<string>() == "chunk" && BeforeChunkWriteResponse is { } beforeWrite)
                    await beforeWrite(fields, ct);
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
