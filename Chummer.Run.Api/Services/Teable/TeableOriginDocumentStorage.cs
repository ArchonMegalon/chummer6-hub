using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.Teable;

/// <summary>Primary bytes for private first-party documents, not publication or provider authority.</summary>
public sealed class TeableOriginDocumentStorage(TeableRevisionStore store, bool ownsStore = false) : IDisposable
{
    internal const string CatalogueStream = "origin-document-catalogue";
    internal const string StoragePosture = "teable_primary_private_storage";
    private const int MaximumCatalogueBytes = 4 * 1024 * 1024;
    private const int MaximumDocumentBytes = 8 * 1024 * 1024;
    private const int AbsoluteMaxRevisions = 16_384;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { MaxDepth = 8 };
    internal sealed record Document(string MetadataJson, string Markdown, string DocumentJson,
        string PreviewReceiptJson, string? ExportReceiptJson = null);
    private sealed record Entry(string Owner, string Id);
    private sealed record Catalogue(int Version, Entry[] Entries);
    private sealed record Envelope(int Version, string Owner, string Project, string Revision, Document Document);

    public void Dispose() { if (ownsStore) store.Dispose(); }
    internal Session OpenSession() => new(store);
    internal static string DocumentId(string owner, string project, string revision)
        => Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new[] { owner, project, revision })));
    internal static string DocumentStream(string id) => "origin-document-" + id;
    private static bool Digest(string? value) => value is { Length: 64 }
        && value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static InvalidDataException Invalid() => new("The primary private document is invalid.");

    internal sealed class Session(TeableRevisionStore store) : IDisposable
    {
        private readonly CancellationTokenSource _deadline = new(TimeSpan.FromSeconds(30));
        private readonly Dictionary<string, (TeableRevisionStore.Head? Head, Document? Value)> _reads = new(StringComparer.Ordinal);
        private TeableRevisionStore.Head? _catalogueHead;
        private Catalogue? _catalogue;
        private bool _failed;
        public void Dispose() => _deadline.Dispose();

        internal Document? Read(string owner, string project, string revision)
        {
            EnsureUsable();
            if (!Digest(owner)) throw Invalid();
            string id = DocumentId(owner, project, revision);
            TeableRevisionStore.Head? head = null;
            try
            {
                LoadCatalogue();
                head = store.ReadAsync(DocumentStream(id), _deadline.Token).GetAwaiter().GetResult();
                Document? value = null;
                if (head is not null)
                {
                    if (head.Bytes.Length > MaximumDocumentBytes) throw Invalid();
                    var envelope = JsonSerializer.Deserialize<Envelope>(head.Bytes, Json);
                    if (envelope is not { Version: 1, Document: not null }
                        || envelope.Owner != owner || envelope.Project != project || envelope.Revision != revision
                        || !_catalogue!.Entries.Contains(new Entry(owner, id))) throw Invalid();
                    value = envelope.Document;
                    if (string.IsNullOrEmpty(value.MetadataJson) || string.IsNullOrEmpty(value.Markdown)
                        || string.IsNullOrEmpty(value.DocumentJson) || string.IsNullOrEmpty(value.PreviewReceiptJson)) throw Invalid();
                }
                _reads[id] = (head is null ? null : head with { Bytes = [] }, value);
                return value;
            }
            catch { _failed = true; throw; }
            finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
        }

        internal void Register(string owner, string project, string revision, int ownerLimit, int globalLimit)
        {
            EnsureUsable();
            if (!Digest(owner) || ownerLimit < 1 || globalLimit < ownerLimit || globalLimit > AbsoluteMaxRevisions) throw Invalid();
            LoadCatalogue();
            var entry = new Entry(owner, DocumentId(owner, project, revision));
            if (_catalogue!.Entries.Contains(entry)) return; // Inert reservation can be resumed.
            if (_catalogue.Entries.Length >= globalLimit || _catalogue.Entries.Count(e => e.Owner == owner) >= ownerLimit)
                throw new InvalidOperationException("The primary private document revision capacity is reached.");
            var next = new Catalogue(1, _catalogue.Entries.Append(entry).OrderBy(e => e.Id, StringComparer.Ordinal).ToArray());
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(next, Json);
            TeableRevisionStore.Head? written = null;
            try
            {
                if (bytes.Length > MaximumCatalogueBytes) throw Invalid();
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

        internal void Write(string owner, string project, string revision, Document document)
        {
            EnsureUsable();
            string id = DocumentId(owner, project, revision);
            if (!_reads.TryGetValue(id, out var expected) || _catalogue is null
                || !_catalogue.Entries.Contains(new Entry(owner, id)))
                throw new InvalidOperationException("Primary document mutation requires its current read and reservation.");
            if (expected.Value is not null)
            {
                if (expected.Value == document) return;
                // The only legal transition is adding the export receipt once.
                if (expected.Value.ExportReceiptJson is not null || document.ExportReceiptJson is null
                    || expected.Value != document with { ExportReceiptJson = null })
                    throw new InvalidOperationException("A private document revision is immutable.");
            }
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(new Envelope(1, owner, project, revision, document), Json);
            TeableRevisionStore.Head? written = null;
            try
            {
                if (bytes.Length > MaximumDocumentBytes) throw Invalid();
                written = store.CompareExchangeAsync(DocumentStream(id), expected.Head, Guid.NewGuid(), bytes,
                    _deadline.Token).GetAwaiter().GetResult();
                _reads[id] = (written with { Bytes = [] }, document);
            }
            catch { _failed = true; throw; }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
                if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes);
            }
        }

        private void LoadCatalogue()
        {
            if (_catalogue is not null) return;
            TeableRevisionStore.Head? head = null;
            try
            {
                head = store.ReadAsync(CatalogueStream, _deadline.Token).GetAwaiter().GetResult();
                if (head is null) { _catalogue = new(1, []); return; }
                if (head.Bytes.Length > MaximumCatalogueBytes) throw Invalid();
                var catalogue = JsonSerializer.Deserialize<Catalogue>(head.Bytes, Json);
                if (catalogue is not { Version: 1, Entries: not null } || catalogue.Entries.Length > AbsoluteMaxRevisions
                    || catalogue.Entries.Any(e => e is null || !Digest(e.Owner) || !Digest(e.Id))
                    || catalogue.Entries.Select(e => e.Id).Distinct(StringComparer.Ordinal).Count() != catalogue.Entries.Length)
                    throw Invalid();
                _catalogue = catalogue;
                _catalogueHead = head with { Bytes = [] };
            }
            catch { _failed = true; throw; }
            finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
        }

        private void EnsureUsable()
        {
            if (_failed) throw new InvalidOperationException("Reconcile the primary document operation before continuing.");
            _deadline.Token.ThrowIfCancellationRequested();
        }
    }
}
