using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.Community;

/// <summary>Private publication index and immutable bytes; not public Registry authority.</summary>
public sealed class TeableOriginPublicationStorage : IDisposable
{
    internal const string IndexStream = "origin-private-publications";
    internal const int MaximumAssetBytes = 64 * 1024 * 1024;
    private const int MaximumCachedBytes = 128 * 1024 * 1024;
    private static readonly Regex AssetReference = new("\\Ateable-origin:([a-f0-9]{64}):([a-f0-9]{64})(\\.[a-z0-9]{1,10})?\\z", RegexOptions.CultureInvariant);
    private static readonly PropertyInfo[] Paths = typeof(OriginDossierPublicationIndexEntry).GetProperties()
        .Where(p => p.PropertyType == typeof(string) && p.Name.EndsWith("Path", StringComparison.Ordinal)).ToArray();
    private readonly TeableRevisionStore _remote;
    private readonly TeableQuotaLedger<OriginDossierPublicationIndexEntry> _index;
    private readonly string? _importRoot;
    private readonly Dictionary<string, byte[]> _assets = new(StringComparer.Ordinal);
    private long _cachedBytes;
    private int _scopeDepth;

    public TeableOriginPublicationStorage(TeableRevisionStore remote, string? importRoot = null, bool ownsStore = false)
    {
        if (importRoot is not null && (!Path.IsPathFullyQualified(importRoot) || !LinuxSecureFile.IsSupportedPlatform))
            throw new InvalidOperationException("Publication imports require an absolute private Linux x64 staging root.");
        _remote = remote;
        _importRoot = importRoot is null ? null : Path.GetFullPath(importRoot);
        _index = new(remote, ownsStore, IndexStream, "chummer.origin.private-publications/v1", Validate, maxDepth: 16);
    }

    public void Dispose() { ClearAssets(); _index.Dispose(); }
    internal IDisposable Enter()
    {
        IDisposable scope = _index.Enter();
        if (_scopeDepth++ == 0) ClearAssets();
        return new Scope(this, scope);
    }
    private sealed class Scope(TeableOriginPublicationStorage owner, IDisposable inner) : IDisposable
    {
        private bool _disposed;
        private readonly int _threadId = Environment.CurrentManagedThreadId;
        public void Dispose()
        {
            if (_disposed) return;
            if (Environment.CurrentManagedThreadId != _threadId)
                throw new InvalidOperationException("Publication scopes cannot cross an await.");
            _disposed = true;
            try { if (--owner._scopeDepth == 0) owner.ClearAssets(); }
            finally { inner.Dispose(); }
        }
    }
    private void ClearAssets()
    {
        foreach (byte[] bytes in _assets.Values) CryptographicOperations.ZeroMemory(bytes);
        _assets.Clear();
        _cachedBytes = 0;
    }
    private void RequireScope() { _ = _index.Gate; }
    internal IReadOnlyList<OriginDossierPublicationIndexEntry> ReadEntries()
    {
        RequireScope();
        return _index.Entries.ToArray();
    }
    internal void Persist(IReadOnlyList<OriginDossierPublicationIndexEntry> entries)
    {
        RequireScope();
        Validate(entries);
        _index.Entries.Clear();
        _index.Entries.AddRange(entries);
        _index.Persist();
    }
    internal void EnsureAccountErasureSupported() => _index.EnsureAccountErasureSupported();
    internal static string Owner(OriginDossierPublicationIndexEntry entry)
        => Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(
            new[] { entry.OwnerUserId, entry.OwnerSubjectId ?? entry.SubjectId, entry.ProjectId })));

    internal OriginDossierPublicationIndexEntry Capture(OriginDossierPublicationIndexEntry entry)
    {
        RequireScope();
        string owner = Owner(entry);
        var result = entry with { };
        foreach (PropertyInfo property in Paths)
        {
            if (property.GetValue(entry) is not string path || string.IsNullOrWhiteSpace(path)) continue;
            Match reference = AssetReference.Match(path);
            if (reference.Success)
            {
                if (reference.Groups[1].Value != owner) throw Invalid();
                _ = ReadBytes(path); // A supplied reference is not evidence that bytes exist.
                continue;
            }
            if (_importRoot is null || !LinuxSecureFile.IsSupportedPlatform) throw Invalid();
            string ownerRoot = Path.Combine(_importRoot, owner);
            string fullPath = Path.GetFullPath(path);
            if (!Path.IsPathFullyQualified(path) || !fullPath.StartsWith(ownerRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal))
                throw Invalid();
            LinuxSecureFile.ValidateExistingDirectory(ownerRoot, ownerOnly: true, readOnlyFileSystem: false);
            LinuxSecureFile.ValidateExistingDirectory(Path.GetDirectoryName(fullPath)!, ownerOnly: true, readOnlyFileSystem: false);
            byte[] bytes = LinuxSecureFile.ReadOwnerOnlyRegularFile(fullPath, MaximumAssetBytes, repairOwnerMode: false);
            try
            {
                if (bytes.Length == 0) throw Invalid();
                byte[] recheck = LinuxSecureFile.ReadOwnerOnlyRegularFile(fullPath, MaximumAssetBytes, repairOwnerMode: false);
                try { if (!bytes.AsSpan().SequenceEqual(recheck)) throw Invalid(); }
                finally { CryptographicOperations.ZeroMemory(recheck); }
                string suffix = Path.GetExtension(fullPath).ToLowerInvariant();
                string value = "teable-origin:" + owner + ":" + Convert.ToHexStringLower(SHA256.HashData(bytes)) + suffix;
                if (!AssetReference.IsMatch(value)) throw Invalid();
                StoreBytes(value, bytes);
                property.SetValue(result, value);
            }
            finally { CryptographicOperations.ZeroMemory(bytes); }
        }
        Validate([result]);
        return result;
    }

    internal bool HasAsset(string? path) => path is not null && AssetReference.IsMatch(path) && ReadBytes(path).Length > 0;
    internal byte[] ReadBytes(string path)
    {
        RequireScope();
        if (_assets.TryGetValue(path, out byte[]? cached)) return cached;
        Match parsed = AssetReference.Match(path);
        if (!parsed.Success) throw Invalid();
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        var read = _remote.ReadAsync(Stream(parsed), deadline.Token).GetAwaiter().GetResult();
        if (read is null) throw new InvalidDataException("Committed publication bytes are unavailable.");
        try
        {
            if (read.Revision != 1 || read.Bytes.Length is <= 32 or > MaximumAssetBytes + 32
                || !read.Bytes.AsSpan(0, 32).SequenceEqual(Convert.FromHexString(parsed.Groups[1].Value))
                || Convert.ToHexStringLower(SHA256.HashData(read.Bytes.AsSpan(32))) != parsed.Groups[2].Value)
                throw Invalid();
            if (_cachedBytes + read.Bytes.Length - 32 > MaximumCachedBytes) throw Invalid();
            byte[] bytes = read.Bytes[32..];
            _cachedBytes += bytes.Length;
            _assets.Add(path, bytes);
            return bytes;
        }
        finally { CryptographicOperations.ZeroMemory(read.Bytes); }
    }
    private void StoreBytes(string reference, byte[] bytes)
    {
        Match parsed = AssetReference.Match(reference);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        var existing = _remote.ReadAsync(Stream(parsed), deadline.Token).GetAwaiter().GetResult();
        if (existing is not null)
        {
            CryptographicOperations.ZeroMemory(existing.Bytes);
            if (!ReadBytes(reference).AsSpan().SequenceEqual(bytes)) throw Invalid();
            return;
        }
        byte[] payload = new byte[bytes.Length + 32];
        Convert.FromHexString(parsed.Groups[1].Value).CopyTo(payload, 0);
        bytes.CopyTo(payload, 32);
        try
        {
            var written = _remote.CompareExchangeAsync(Stream(parsed), null, Guid.NewGuid(), payload, deadline.Token).GetAwaiter().GetResult();
            CryptographicOperations.ZeroMemory(written.Bytes);
        }
        finally { CryptographicOperations.ZeroMemory(payload); }
    }
    private static string Stream(Match reference) => "origin-pub-asset-" + Convert.ToHexStringLower(SHA256.HashData(
        Encoding.UTF8.GetBytes(reference.Groups[1].Value + ":" + reference.Groups[2].Value)));
    private static InvalidDataException Invalid() => new("The primary publication or private artifact is invalid.");
    private static void Validate(IReadOnlyList<OriginDossierPublicationIndexEntry> entries)
    {
        if (entries.Count > 2048) throw Invalid();
        var identities = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in entries)
        {
            if (entry is null || string.IsNullOrWhiteSpace(entry.OwnerUserId) || string.IsNullOrWhiteSpace(entry.ProjectId)
                || string.IsNullOrWhiteSpace(entry.OwnerSubjectId ?? entry.SubjectId)
                || !identities.Add(JsonSerializer.Serialize(new[] { entry.OwnerUserId, entry.ProjectId }))) throw Invalid();
            string owner = Owner(entry);
            foreach (var property in Paths)
            {
                if (property.GetValue(entry) is not string path || string.IsNullOrWhiteSpace(path)) continue;
                Match parsed = AssetReference.Match(path);
                if (!parsed.Success || parsed.Groups[1].Value != owner) throw Invalid();
            }
        }
    }
}
