using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.Community;

// Shared custody for authoring ledgers and their membership inputs, not provider-dispatch
// admission or a distributed lease. A new outer scope is always a remote read.
internal sealed class TeableQuotaLedger<T>(TeableRevisionStore? primary, bool ownsPrimary,
    string stream, string schema, Action<IReadOnlyList<T>> validate, int maxDepth = 8) : IDisposable
{
    private readonly object _gate = new();
    private TeableRevisionStore.Head? _head;
    private int _depth;
    private bool _failed;
    private const int MaximumBytes = 4 * 1024 * 1024;
    private readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
        { MaxDepth = maxDepth, UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow };
    private sealed record Snapshot(string Schema, IReadOnlyList<T> Entries);

    internal List<T> Entries { get; } = [];
    internal bool IsPrimary => primary is not null;
    internal object Gate => !IsPrimary || (Monitor.IsEntered(_gate) && _depth > 0 && !_failed)
        ? _gate : throw new InvalidOperationException("Primary authoring ledger access requires a current scope.");

    internal IDisposable Enter()
    {
        Monitor.Enter(_gate);
        try
        {
            if (IsPrimary && _depth == 0) { _failed = false; Load(); }
            else if (_failed) throw new InvalidOperationException("The current authoring ledger operation failed.");
            _depth++;
            return new Scope(this);
        }
        catch
        {
            if (IsPrimary && _depth == 0) Entries.Clear();
            Monitor.Exit(_gate);
            throw;
        }
    }

    private sealed class Scope(TeableQuotaLedger<T> store) : IDisposable
    {
        private bool _disposed;
        public void Dispose()
        {
            if (_disposed) return;
            if (!Monitor.IsEntered(store._gate))
                throw new InvalidOperationException("Authoring ledger scopes cannot cross an await.");
            _disposed = true;
            if (--store._depth == 0 && store.IsPrimary) store.Entries.Clear();
            Monitor.Exit(store._gate);
        }
    }

    private void Load()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        TeableRevisionStore.Head? read = null;
        try
        {
            read = primary!.ReadAsync(stream, deadline.Token).GetAwaiter().GetResult();
            if (_head is not null && (read is null || read.Revision < _head.Revision
                || (read.Revision == _head.Revision && (read.Commit != _head.Commit || read.Sha256 != _head.Sha256))))
                throw new InvalidDataException("Primary authoring ledger revision regressed.");
            IReadOnlyList<T> rows = [];
            if (read is not null)
            {
                if (read.Bytes.Length > MaximumBytes) throw new InvalidDataException("Primary authoring ledger is oversized.");
                var snapshot = JsonSerializer.Deserialize<Snapshot>(read.Bytes, Json);
                if (snapshot?.Schema != schema || snapshot.Entries is null)
                    throw new InvalidDataException("Primary authoring ledger schema is invalid.");
                validate(snapshot.Entries);
                rows = snapshot.Entries;
            }
            Entries.Clear();
            Entries.AddRange(rows);
            if (read is not null) _head = read with { Bytes = [] };
        }
        catch { _failed = true; throw; }
        finally { if (read is not null) CryptographicOperations.ZeroMemory(read.Bytes); }
    }

    internal void Persist()
    {
        if (!IsPrimary || !Monitor.IsEntered(_gate) || _depth == 0 || _failed)
            throw new InvalidOperationException("Primary authoring ledger writes require a current read scope.");
        byte[]? bytes = null;
        TeableRevisionStore.Head? written = null;
        try
        {
            validate(Entries);
            bytes = JsonSerializer.SerializeToUtf8Bytes(new Snapshot(schema, Entries), Json);
            if (bytes.Length > MaximumBytes) throw new InvalidDataException("Primary authoring ledger is oversized.");
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            written = primary!.CompareExchangeAsync(stream, _head, Guid.NewGuid(), bytes, deadline.Token).GetAwaiter().GetResult();
            _head = written with { Bytes = [] };
        }
        catch { _failed = true; throw; }
        finally
        {
            if (bytes is not null) CryptographicOperations.ZeroMemory(bytes);
            if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes);
        }
    }

    internal void EnsureAccountErasureSupported()
    {
        if (IsPrimary) throw new InvalidOperationException("Primary authoring ledger history erasure is not enabled.");
    }

    public void Dispose() { if (ownsPrimary) primary?.Dispose(); }
}
