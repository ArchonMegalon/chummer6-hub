using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Storage.Teable;

/// <summary>
/// Operator-only custody of explicitly selected deployment/configuration bytes.
/// No directory discovery, execution, service activation or in-place restore.
/// Use a private recovery table, not an account-facing/runtime-readable table.
/// </summary>
public sealed class TeableRecoveryBundleStore(TeableRevisionStore store)
{
    private const string Format = "chummer.hub.recovery-files/v1";
    private const int MaximumFiles = 64;
    private const int MaximumFileBytes = 1024 * 1024;
    private const int MaximumTotalBytes = 8 * 1024 * 1024;
    private const int MaximumEnvelopeBytes = 12 * 1024 * 1024;
    private const UnixFileMode PrivateDirectory = UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode PrivateFile = UnixFileMode.UserRead | UnixFileMode.UserWrite;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 8
    };
    private sealed record Entry(string Name, int Length, string Sha256, byte[] Bytes);
    private sealed record Envelope(string Schema, string Deployment, Entry[] Files);

    public sealed record Receipt(string Deployment, long Revision, Guid Commit, string Sha256, int FileCount);

    public async Task<Receipt> CaptureAsync(string deployment, string sourceDirectory,
        IReadOnlyList<string> fileNames, CancellationToken ct = default)
    {
        ValidateDeployment(deployment);
        ValidatePrivateDirectory(sourceDirectory);
        if (fileNames is null || fileNames.Count is < 1 or > MaximumFiles) throw Invalid();
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string name in fileNames)
        {
            ValidateName(name);
            if (!names.Add(name)) throw Invalid();
        }
        var files = new List<Entry>();
        TeableRevisionStore.Head? before = null, written = null;
        byte[]? encoded = null;
        try
        {
            before = await store.ReadAsync(Stream(deployment), ct);
            if (before is not null)
            {
                Envelope previous = Decode(before, deployment);
                Clear(previous.Files);
            }
            int total = 0;
            foreach (string name in fileNames.Order(StringComparer.Ordinal))
            {
                ct.ThrowIfCancellationRequested();
                byte[] bytes = LinuxSecureFile.ReadOwnerOnlyRegularFile(
                    Path.Combine(sourceDirectory, name), MaximumFileBytes, repairOwnerMode: false);
                files.Add(new(name, bytes.Length, Hash(bytes), bytes));
                total = checked(total + bytes.Length);
                if (total > MaximumTotalBytes) throw Invalid();
            }
            // Prepared inputs must remain byte-identical through capture. This is
            // not an atomic snapshot of a changing live deployment: mount a
            // reviewed staging directory read-only and exclude concurrent writers.
            foreach (Entry file in files)
            {
                ct.ThrowIfCancellationRequested();
                byte[] check = LinuxSecureFile.ReadOwnerOnlyRegularFile(
                    Path.Combine(sourceDirectory, file.Name), MaximumFileBytes, repairOwnerMode: false);
                try
                {
                    if (!check.AsSpan().SequenceEqual(file.Bytes)) throw Invalid();
                }
                finally { CryptographicOperations.ZeroMemory(check); }
            }
            encoded = JsonSerializer.SerializeToUtf8Bytes(new Envelope(Format, deployment, files.ToArray()), Json);
            if (encoded.Length > MaximumEnvelopeBytes) throw Invalid();
            if (before is not null && before.Sha256 == Hash(encoded)) return ToReceipt(before, deployment, files.Count);
            written = await store.CompareExchangeAsync(Stream(deployment), before, Guid.NewGuid(), encoded, ct);
            return ToReceipt(written, deployment, files.Count);
        }
        finally
        {
            Clear(files);
            if (encoded is not null) CryptographicOperations.ZeroMemory(encoded);
            if (before is not null) CryptographicOperations.ZeroMemory(before.Bytes);
            if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes);
        }
    }

    public async Task<Receipt> InspectAsync(string deployment, CancellationToken ct = default)
    {
        ValidateDeployment(deployment);
        TeableRevisionStore.Head head = await store.ReadAsync(Stream(deployment), ct) ?? throw Invalid();
        Envelope? envelope = null;
        try
        {
            envelope = Decode(head, deployment);
            return ToReceipt(head, deployment, envelope.Files.Length);
        }
        finally
        {
            if (envelope is not null) Clear(envelope.Files);
            CryptographicOperations.ZeroMemory(head.Bytes);
        }
    }

    public async Task<Receipt> RestoreAsync(Receipt expected, string destinationParent,
        string directoryName, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(expected);
        if (!OperatingSystem.IsLinux()) throw new PlatformNotSupportedException("Private recovery output requires Linux.");
        ValidateDeployment(expected.Deployment);
        ValidateName(directoryName);
        ValidatePrivateDirectory(destinationParent);
        string destination = Path.Combine(destinationParent, directoryName);
        RejectExisting(destination);
        TeableRevisionStore.Head head = await store.ReadAsync(Stream(expected.Deployment), ct) ?? throw Invalid();
        Envelope? envelope = null;
        try
        {
            envelope = Decode(head, expected.Deployment);
            Receipt current = ToReceipt(head, expected.Deployment, envelope.Files.Length);
            if (current != expected) throw new TeableRevisionConflictException();
            // Validate every file before creating any output. A hostile member
            // cannot leave earlier secret files in an apparently complete target.
            string staging = Path.Combine(destinationParent, ".recovery-" + Guid.NewGuid().ToString("N"));
            RejectExisting(staging);
            Directory.CreateDirectory(staging, PrivateDirectory);
            ValidatePrivateDirectory(staging);
            foreach (Entry entry in envelope.Files)
            {
                ct.ThrowIfCancellationRequested();
                using var output = new FileStream(Path.Combine(staging, entry.Name), new FileStreamOptions
                {
                    Mode = FileMode.CreateNew, Access = FileAccess.Write, Share = FileShare.None,
                    UnixCreateMode = PrivateFile, Options = FileOptions.WriteThrough
                });
                output.Write(entry.Bytes);
                output.Flush(flushToDisk: true);
            }
            foreach (Entry entry in envelope.Files)
            {
                ct.ThrowIfCancellationRequested();
                byte[] actual = LinuxSecureFile.ReadOwnerOnlyRegularFile(
                    Path.Combine(staging, entry.Name), MaximumFileBytes, repairOwnerMode: false);
                try { if (!actual.AsSpan().SequenceEqual(entry.Bytes)) throw Invalid(); }
                finally { CryptographicOperations.ZeroMemory(actual); }
            }
            ct.ThrowIfCancellationRequested();
            ValidatePrivateDirectory(destinationParent);
            RejectExisting(destination);
            Directory.Move(staging, destination);
            // Failed restores retain a private, clearly partial .recovery-* folder.
            // No cleanup can delete an unrelated destination and no process is run.
            return current;
        }
        finally
        {
            if (envelope is not null) Clear(envelope.Files);
            CryptographicOperations.ZeroMemory(head.Bytes);
        }
    }

    private static Envelope Decode(TeableRevisionStore.Head head, string deployment)
    {
        if (head.Bytes.Length > MaximumEnvelopeBytes) throw Invalid();
        // Reject duplicate/unknown properties, not last-property-wins configuration.
        using (JsonDocument document = JsonDocument.Parse(head.Bytes, new JsonDocumentOptions { MaxDepth = 8 }))
            RejectDuplicateProperties(document.RootElement);
        Envelope? envelope = null;
        try
        {
            envelope = JsonSerializer.Deserialize<Envelope>(head.Bytes, Json) ?? throw Invalid();
            if (envelope.Schema != Format || envelope.Deployment != deployment
                || envelope.Files is not { Length: >= 1 and <= MaximumFiles }) throw Invalid();
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            int total = 0;
            foreach (Entry? entry in envelope.Files)
            {
                if (entry is null) throw Invalid();
                ValidateName(entry.Name);
                if (!names.Add(entry.Name) || entry.Bytes is null || entry.Length != entry.Bytes.Length
                    || entry.Length > MaximumFileBytes || entry.Sha256 != Hash(entry.Bytes)) throw Invalid();
                total = checked(total + entry.Length);
                if (total > MaximumTotalBytes) throw Invalid();
            }
            return envelope;
        }
        catch
        {
            if (envelope?.Files is not null) Clear(envelope.Files);
            throw;
        }
    }

    internal static void RejectDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw Invalid();
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (JsonElement item in element.EnumerateArray()) RejectDuplicateProperties(item);
    }

    private static void ValidateName(string name)
    {
        if (name is null || name.Length is < 1 or > 80 || name is "." or ".."
            || name.Any(c => !(char.IsAsciiLetterOrDigit(c) || c is '.' or '_' or '-'))) throw Invalid();
    }

    private static void ValidateDeployment(string deployment)
    {
        ValidateName(deployment);
        if (deployment.Contains('.')) throw Invalid();
    }

    private static void ValidatePrivateDirectory(string path)
    {
        if (!Path.IsPathFullyQualified(path)) throw Invalid();
        LinuxSecureFile.ValidateExistingDirectory(path, ownerOnly: true, readOnlyFileSystem: false);
    }

    private static void RejectExisting(string path)
    {
        var entry = new FileInfo(path);
        entry.Refresh();
        if (File.Exists(path) || Directory.Exists(path) || entry.LinkTarget is not null) throw Invalid();
    }

    private static void Clear(IEnumerable<Entry> entries)
    {
        foreach (Entry? entry in entries)
            if (entry?.Bytes is not null) CryptographicOperations.ZeroMemory(entry.Bytes);
    }
    private static string Stream(string deployment) => "hub-recovery-" + deployment;
    private static string Hash(ReadOnlySpan<byte> bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
    private static Receipt ToReceipt(TeableRevisionStore.Head head, string deployment, int count)
        => new(deployment, head.Revision, head.Commit, head.Sha256, count);
    private static InvalidDataException Invalid() => new("Private recovery bundle or target is invalid.");
}
