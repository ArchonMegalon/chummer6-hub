using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.Teable;

/// <summary>
/// One revision stream per chapter, plus a bounded opaque discovery catalogue.
/// Register before creating the chapter: interrupted registration is inert and
/// may be resumed, but a worker never dispatches a missing/uncommitted chapter.
/// </summary>
public sealed class TeableOriginChapterStorage(TeableRevisionStore store, bool ownsStore = false) : IDisposable
{
    internal const string CatalogueStream = "origin-chapter-catalogue";
    private const int MaximumCatalogueBytes = 512 * 1024;
    internal const int MaximumJobBytes = 512 * 1024;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { MaxDepth = 4 };
    private sealed record Catalogue(int Version, string[] WorkIds);

    public void Dispose() { if (ownsStore) store.Dispose(); }
    internal Session OpenSession() => new(store);

    internal static void ValidateWorkId(string value)
    {
        if (value is not { Length: 129 } || value[64] != '.'
            || value.Where((_, index) => index != 64).Any(c => c is not (>= 'a' and <= 'f' or >= '0' and <= '9')))
            throw new InvalidDataException("The primary authoring work identity is invalid.");
    }

    internal static string JobStream(string workId)
    {
        ValidateWorkId(workId);
        return "origin-chapter-" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(workId)));
    }

    internal sealed class Session(TeableRevisionStore store) : IDisposable
    {
        private readonly CancellationTokenSource _deadline = new(TimeSpan.FromSeconds(30));
        private readonly Dictionary<string, TeableRevisionStore.Head?> _readHeads = new(StringComparer.Ordinal);
        private Catalogue? _catalogue;
        private TeableRevisionStore.Head? _catalogueHead;
        private bool _failed;

        public void Dispose() => _deadline.Dispose();

        internal IReadOnlyList<string> WorkIds()
        {
            EnsureUsable();
            LoadCatalogue();
            return _catalogue!.WorkIds;
        }

        internal void Register(string workId)
        {
            EnsureUsable();
            ValidateWorkId(workId);
            LoadCatalogue();
            if (_catalogue!.WorkIds.Contains(workId, StringComparer.Ordinal)) return;
            if (_catalogue.WorkIds.Length >= 2048
                || _catalogue.WorkIds.Count(id => id[..64] == workId[..64]) >= 128)
                throw new InvalidOperationException("The private authoring queue is full.");
            var next = new Catalogue(1, _catalogue.WorkIds.Append(workId).Order(StringComparer.Ordinal).ToArray());
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(next, Json);
            TeableRevisionStore.Head? written = null;
            try
            {
                if (bytes.Length > MaximumCatalogueBytes) throw new InvalidDataException("The authoring catalogue is oversized.");
                written = store.CompareExchangeAsync(CatalogueStream, _catalogueHead, Guid.NewGuid(), bytes,
                    _deadline.Token).GetAwaiter().GetResult();
                _catalogueHead = written with { Bytes = [] };
                _catalogue = next;
            }
            catch { _failed = true; throw; }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
                if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes);
            }
        }

        internal byte[]? Read(string workId)
        {
            EnsureUsable();
            var head = store.ReadAsync(JobStream(workId), _deadline.Token).GetAwaiter().GetResult();
            if (head is not null && head.Bytes.Length > MaximumJobBytes)
            {
                CryptographicOperations.ZeroMemory(head.Bytes);
                throw new InvalidDataException("The primary authoring record is oversized.");
            }
            _readHeads[workId] = head is null ? null : head with { Bytes = [] };
            return head?.Bytes; // Caller owns and clears these bytes after parsing.
        }

        internal void Write(string workId, byte[] bytes)
        {
            EnsureUsable();
            if (bytes.Length is < 1 or > MaximumJobBytes || !_readHeads.TryGetValue(workId, out var expected))
                throw new InvalidOperationException("A current authoring read is required before a mutation.");
            // Register is a separate durable step. A missing record after that
            // step never means a dispatched job; no provider work occurs here.
            if (expected is null && !WorkIds().Contains(workId, StringComparer.Ordinal))
                throw new InvalidOperationException("The new authoring record was not registered.");
            TeableRevisionStore.Head? written = null;
            try
            {
                written = store.CompareExchangeAsync(JobStream(workId), expected, Guid.NewGuid(), bytes,
                    _deadline.Token).GetAwaiter().GetResult();
                _readHeads[workId] = written with { Bytes = [] };
            }
            catch { _failed = true; throw; }
            finally { if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes); }
        }

        private void LoadCatalogue()
        {
            if (_catalogue is not null) return;
            var head = store.ReadAsync(CatalogueStream, _deadline.Token).GetAwaiter().GetResult();
            try
            {
                if (head is null) { _catalogue = new(1, []); return; }
                if (head.Bytes.Length > MaximumCatalogueBytes) throw new InvalidDataException("The authoring catalogue is oversized.");
                var catalogue = JsonSerializer.Deserialize<Catalogue>(head.Bytes, Json);
                if (catalogue is not { Version: 1, WorkIds: not null } || catalogue.WorkIds.Length > 2048
                    || catalogue.WorkIds.Distinct(StringComparer.Ordinal).Count() != catalogue.WorkIds.Length)
                    throw new InvalidDataException("The primary authoring catalogue is invalid.");
                foreach (string id in catalogue.WorkIds) ValidateWorkId(id);
                if (catalogue.WorkIds.GroupBy(id => id[..64]).Any(group => group.Count() > 128))
                    throw new InvalidDataException("The primary authoring catalogue is invalid.");
                _catalogue = catalogue;
                _catalogueHead = head with { Bytes = [] };
            }
            finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
        }

        private void EnsureUsable()
        {
            if (_failed) throw new InvalidOperationException("Reconcile the primary authoring operation before continuing.");
            _deadline.Token.ThrowIfCancellationRequested();
        }
    }
}
