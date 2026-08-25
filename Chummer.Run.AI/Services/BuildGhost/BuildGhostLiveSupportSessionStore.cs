using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.AI.Services.BuildGhost;

public sealed record StoredBuildGhostLiveSupportSession(
    string Schema,
    string OwnerScopeHash,
    string WorkspaceId,
    string SourceDigest,
    string RequestFingerprint,
    BuildGhostLiveSupportSessionProjection Session);

public interface IBuildGhostLiveSupportSessionStore : IBuildGhostLiveSupportDependencyReadiness
{
    Task<bool?> HasOpenReservationAsync(
        DateTimeOffset now,
        CancellationToken cancellationToken);

    Task<StoredBuildGhostLiveSupportSession?> ReadAsync(
        string ownerScopeHash,
        string requestId,
        string workspaceId,
        string sourceDigest,
        CancellationToken cancellationToken);

    Task<bool> WriteAsync(
        StoredBuildGhostLiveSupportSession stored,
        CancellationToken cancellationToken);
}

public sealed class DisabledBuildGhostLiveSupportSessionStore : IBuildGhostLiveSupportSessionStore
{
    public IReadOnlyList<string> BlockingReasons => ["live-support-durable-session-store-disabled"];

    public Task<bool?> HasOpenReservationAsync(
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult<bool?>(null);
    }

    public Task<StoredBuildGhostLiveSupportSession?> ReadAsync(
        string ownerScopeHash,
        string requestId,
        string workspaceId,
        string sourceDigest,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult<StoredBuildGhostLiveSupportSession?>(null);
    }

    public Task<bool> WriteAsync(
        StoredBuildGhostLiveSupportSession stored,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(false);
    }
}

public sealed class EncryptedFileBuildGhostLiveSupportSessionStore : IBuildGhostLiveSupportSessionStore, IDisposable
{
    public const string DirectoryConfigurationKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_PATH";
    public const string EncryptionKeyConfigurationKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY";
    public const string SingleInstanceConfigurationKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SINGLE_INSTANCE";
    public const string StoredSchema = "chummer.build_ghost.live_support_stored_session.v2";
    private const string EnvelopeSchema = "chummer.build_ghost.live_support_encrypted_envelope.v2";
    private const int MaximumEnvelopeBytes = 512 * 1024;
    private static readonly JsonSerializerOptions StrictJson = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow
    };

    private readonly string _directory;
    private readonly byte[] _encryptionKey;
    private readonly IReadOnlyList<string> _blockingReasons;

    public EncryptedFileBuildGhostLiveSupportSessionStore(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        List<string> blockers = [];
        string configuredDirectory = (configuration[DirectoryConfigurationKey] ?? string.Empty).Trim();
        _directory = ResolveDirectory(configuredDirectory, blockers);
        _encryptionKey = ResolveKey(configuration[EncryptionKeyConfigurationKey], blockers);
        if (!bool.TryParse(configuration[SingleInstanceConfigurationKey], out bool singleInstance)
            || !singleInstance)
        {
            blockers.Add("live-support-single-instance-posture-unverified");
        }
        _blockingReasons = blockers
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static blocker => blocker, StringComparer.Ordinal)
            .ToArray();
    }

    public IReadOnlyList<string> BlockingReasons => _blockingReasons;

    public async Task<bool?> HasOpenReservationAsync(
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (_blockingReasons.Count != 0)
        {
            return null;
        }

        try
        {
            foreach (FileInfo file in new DirectoryInfo(_directory)
                .EnumerateFiles("*.session", SearchOption.TopDirectoryOnly))
            {
                if (file.LinkTarget is not null
                    || file.Length <= 0
                    || file.Length > MaximumEnvelopeBytes)
                {
                    return null;
                }
                EncryptedSessionEnvelope? envelope = JsonSerializer.Deserialize<EncryptedSessionEnvelope>(
                    await File.ReadAllBytesAsync(file.FullName, cancellationToken).ConfigureAwait(false),
                    StrictJson);
                if (envelope is null)
                {
                    return null;
                }
                StoredBuildGhostLiveSupportSession? stored = await ReadAsync(
                    envelope.OwnerScopeHash,
                    envelope.RequestId,
                    envelope.WorkspaceId,
                    envelope.SourceDigest,
                    cancellationToken).ConfigureAwait(false);
                if (stored is null)
                {
                    return null;
                }
                if (ReservesProviderCapacity(stored.Session, now))
                {
                    return true;
                }
            }
            return false;
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or JsonException
            or InvalidDataException)
        {
            return null;
        }
    }

    public async Task<StoredBuildGhostLiveSupportSession?> ReadAsync(
        string ownerScopeHash,
        string requestId,
        string workspaceId,
        string sourceDigest,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (_blockingReasons.Count != 0)
        {
            return null;
        }

        string path = ResolveSessionPath(ownerScopeHash, workspaceId, requestId);
        FileInfo file = new(path);
        if (!file.Exists || file.Length <= 0 || file.Length > MaximumEnvelopeBytes || file.LinkTarget is not null)
        {
            return null;
        }

        try
        {
            byte[] envelopeBytes = await File.ReadAllBytesAsync(path, cancellationToken).ConfigureAwait(false);
            EncryptedSessionEnvelope? envelope = JsonSerializer.Deserialize<EncryptedSessionEnvelope>(
                envelopeBytes,
                StrictJson);
            if (envelope is null
                || !string.Equals(envelope.Schema, EnvelopeSchema, StringComparison.Ordinal)
                || !string.Equals(envelope.OwnerScopeHash, ownerScopeHash, StringComparison.Ordinal)
                || !string.Equals(envelope.RequestId, requestId, StringComparison.Ordinal)
                || !string.Equals(envelope.WorkspaceId, workspaceId, StringComparison.Ordinal)
                || !IsSha256(envelope.SourceDigest))
            {
                return null;
            }

            byte[] nonce = Convert.FromBase64String(envelope.Nonce);
            byte[] ciphertext = Convert.FromBase64String(envelope.Ciphertext);
            byte[] tag = Convert.FromBase64String(envelope.Tag);
            if (nonce.Length != 12 || tag.Length != 16 || ciphertext.Length == 0)
            {
                return null;
            }

            byte[] plaintext = new byte[ciphertext.Length];
            try
            {
                using AesGcm aes = new(_encryptionKey, tag.Length);
                aes.Decrypt(
                    nonce,
                    ciphertext,
                    tag,
                    plaintext,
                    BuildAssociatedData(ownerScopeHash, requestId, workspaceId, envelope.SourceDigest));
                StoredBuildGhostLiveSupportSession? stored =
                    JsonSerializer.Deserialize<StoredBuildGhostLiveSupportSession>(plaintext, StrictJson);
                return IsValidStored(
                    stored,
                    ownerScopeHash,
                    requestId,
                    workspaceId,
                    envelope.SourceDigest)
                    ? stored
                    : null;
            }
            finally
            {
                CryptographicOperations.ZeroMemory(plaintext);
                CryptographicOperations.ZeroMemory(ciphertext);
                CryptographicOperations.ZeroMemory(tag);
                CryptographicOperations.ZeroMemory(nonce);
            }
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or JsonException
            or FormatException
            or CryptographicException)
        {
            throw new InvalidDataException("live-support-session-store-read-invalid", exception);
        }
    }

    public async Task<bool> WriteAsync(
        StoredBuildGhostLiveSupportSession stored,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(stored);
        cancellationToken.ThrowIfCancellationRequested();
        if (_blockingReasons.Count != 0
            || !IsValidStored(
                stored,
                stored.OwnerScopeHash,
                stored.Session.RequestId,
                stored.WorkspaceId,
                stored.SourceDigest))
        {
            return false;
        }

        string path = ResolveSessionPath(
            stored.OwnerScopeHash,
            stored.WorkspaceId,
            stored.Session.RequestId);
        string temporaryPath = Path.Combine(
            _directory,
            $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        byte[] plaintext = JsonSerializer.SerializeToUtf8Bytes(stored, StrictJson);
        byte[] nonce = RandomNumberGenerator.GetBytes(12);
        byte[] ciphertext = new byte[plaintext.Length];
        byte[] tag = new byte[16];
        try
        {
            using AesGcm aes = new(_encryptionKey, tag.Length);
            aes.Encrypt(
                nonce,
                plaintext,
                ciphertext,
                tag,
                BuildAssociatedData(
                    stored.OwnerScopeHash,
                    stored.Session.RequestId,
                    stored.WorkspaceId,
                    stored.SourceDigest));
            EncryptedSessionEnvelope envelope = new(
                EnvelopeSchema,
                stored.OwnerScopeHash,
                stored.Session.RequestId,
                stored.WorkspaceId,
                stored.SourceDigest,
                Convert.ToBase64String(nonce),
                Convert.ToBase64String(ciphertext),
                Convert.ToBase64String(tag));
            byte[] envelopeBytes = JsonSerializer.SerializeToUtf8Bytes(envelope, StrictJson);
            if (envelopeBytes.Length > MaximumEnvelopeBytes)
            {
                return false;
            }

            await using (FileStream stream = new(
                temporaryPath,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                16 * 1024,
                FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                if (!OperatingSystem.IsWindows())
                {
                    File.SetUnixFileMode(temporaryPath, UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }
                await stream.WriteAsync(envelopeBytes, cancellationToken).ConfigureAwait(false);
                await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
            }
            File.Move(temporaryPath, path, overwrite: true);
            PruneStaleFiles(DateTimeOffset.UtcNow);
            return true;
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or CryptographicException)
        {
            return false;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plaintext);
            CryptographicOperations.ZeroMemory(ciphertext);
            CryptographicOperations.ZeroMemory(tag);
            CryptographicOperations.ZeroMemory(nonce);
            try
            {
                if (File.Exists(temporaryPath))
                {
                    File.Delete(temporaryPath);
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    public void Dispose()
        => CryptographicOperations.ZeroMemory(_encryptionKey);

    private static string ResolveDirectory(string configuredDirectory, List<string> blockers)
    {
        if (string.IsNullOrEmpty(configuredDirectory) || !Path.IsPathFullyQualified(configuredDirectory))
        {
            blockers.Add("live-support-session-store-path-missing-or-invalid");
            return string.Empty;
        }

        string directory = Path.GetFullPath(configuredDirectory);
        DirectoryInfo info = new(directory);
        if (!info.Exists || info.LinkTarget is not null)
        {
            blockers.Add("live-support-session-store-directory-missing-or-invalid");
            return string.Empty;
        }

        if (!OperatingSystem.IsWindows())
        {
            try
            {
                UnixFileMode mode = File.GetUnixFileMode(directory);
                if ((mode & (UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute
                    | UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute)) != 0)
                {
                    blockers.Add("live-support-session-store-permissions-not-private");
                }
            }
            catch (Exception exception) when (exception is IOException
                or UnauthorizedAccessException
                or PlatformNotSupportedException)
            {
                blockers.Add("live-support-session-store-permissions-unverified");
            }
        }

        return directory;
    }

    private static byte[] ResolveKey(string? configured, List<string> blockers)
    {
        try
        {
            byte[] key = Convert.FromBase64String(configured?.Trim() ?? string.Empty);
            if (key.Length == 32)
            {
                return key;
            }
            CryptographicOperations.ZeroMemory(key);
        }
        catch (FormatException)
        {
        }
        blockers.Add("live-support-session-store-key-missing-or-invalid");
        return [];
    }

    private string ResolveSessionPath(
        string ownerScopeHash,
        string workspaceId,
        string requestId)
    {
        string key = Digest($"{ownerScopeHash}\n{workspaceId}\n{requestId}");
        return Path.Combine(_directory, $"{key}.session");
    }

    private static byte[] BuildAssociatedData(
        string ownerScopeHash,
        string requestId,
        string workspaceId,
        string sourceDigest)
        => Encoding.UTF8.GetBytes(
            $"{EnvelopeSchema}\n{ownerScopeHash}\n{requestId}\n{workspaceId}\n{sourceDigest}");

    private static bool IsValidStored(
        StoredBuildGhostLiveSupportSession? stored,
        string ownerScopeHash,
        string requestId,
        string workspaceId,
        string sourceDigest)
        => stored is not null
            && string.Equals(stored.Schema, StoredSchema, StringComparison.Ordinal)
            && string.Equals(stored.OwnerScopeHash, ownerScopeHash, StringComparison.Ordinal)
            && string.Equals(stored.Session.RequestId, requestId, StringComparison.Ordinal)
            && string.Equals(stored.WorkspaceId, workspaceId, StringComparison.Ordinal)
            && string.Equals(stored.SourceDigest, sourceDigest, StringComparison.Ordinal)
            && IsSafeIdentifier(stored.WorkspaceId)
            && IsSha256(stored.SourceDigest)
            && stored.RequestFingerprint is { Length: 71 }
            && stored.RequestFingerprint.StartsWith("sha256:", StringComparison.Ordinal)
            && stored.RequestFingerprint.AsSpan(7).IndexOfAnyExcept("0123456789abcdef") < 0;

    private static bool IsSafeIdentifier(string? value)
        => value is { Length: > 0 and <= 128 }
            && char.IsAsciiLetterOrDigit(value[0])
            && value.All(static character => char.IsAsciiLetterOrDigit(character)
                || character is '-' or '_' or '.' or ':');

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).IndexOfAnyExcept("0123456789abcdef") < 0;

    public static bool ReservesProviderCapacity(
        BuildGhostLiveSupportSessionProjection session,
        DateTimeOffset now)
    {
        if ((session.BlockingReasons ?? []).Contains(
                "meeting-link-compensation-unverified",
                StringComparer.Ordinal))
        {
            return true;
        }
        bool openStatus = session.Status is BuildGhostLiveSupportStatuses.Requested
            or BuildGhostLiveSupportStatuses.ProvisioningMeeting
            or BuildGhostLiveSupportStatuses.ProvisioningAvatar;
        if (openStatus)
        {
            return true;
        }
        if (session.Status is not (BuildGhostLiveSupportStatuses.Ready
            or BuildGhostLiveSupportStatuses.Active))
        {
            return false;
        }
        return session.JoinUrlExpiresAtUtc is not DateTimeOffset expiresAt || expiresAt > now;
    }

    private void PruneStaleFiles(DateTimeOffset now)
    {
        try
        {
            FileInfo[] sessionFiles = new DirectoryInfo(_directory)
                .EnumerateFiles("*.session", SearchOption.TopDirectoryOnly)
                .Where(static file => file.LinkTarget is null)
                .OrderByDescending(static file => file.LastWriteTimeUtc)
                .ToArray();
            foreach (FileInfo file in sessionFiles
                .Where(file => now - file.LastWriteTimeUtc > TimeSpan.FromHours(48))
                .Concat(sessionFiles.Skip(4096))
                .DistinctBy(static file => file.FullName, StringComparer.Ordinal)
                .Where(file => CanPruneSession(file, now)))
            {
                file.Delete();
            }

            foreach (FileInfo temporary in new DirectoryInfo(_directory)
                .EnumerateFiles(".*.tmp", SearchOption.TopDirectoryOnly)
                .Where(static file => file.LinkTarget is null)
                .Where(file => now - file.LastWriteTimeUtc > TimeSpan.FromMinutes(15)))
            {
                temporary.Delete();
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }

    private bool CanPruneSession(FileInfo file, DateTimeOffset now)
    {
        if (file.LinkTarget is not null || file.Length <= 0 || file.Length > MaximumEnvelopeBytes)
        {
            return false;
        }

        byte[] nonce = [];
        byte[] ciphertext = [];
        byte[] tag = [];
        byte[] plaintext = [];
        try
        {
            EncryptedSessionEnvelope? envelope = JsonSerializer.Deserialize<EncryptedSessionEnvelope>(
                File.ReadAllBytes(file.FullName),
                StrictJson);
            if (envelope is null
                || !string.Equals(envelope.Schema, EnvelopeSchema, StringComparison.Ordinal)
                || !IsSha256(envelope.OwnerScopeHash)
                || !IsSafeIdentifier(envelope.RequestId)
                || !IsSafeIdentifier(envelope.WorkspaceId)
                || !IsSha256(envelope.SourceDigest))
            {
                return false;
            }

            nonce = Convert.FromBase64String(envelope.Nonce);
            ciphertext = Convert.FromBase64String(envelope.Ciphertext);
            tag = Convert.FromBase64String(envelope.Tag);
            if (nonce.Length != 12 || tag.Length != 16 || ciphertext.Length == 0)
            {
                return false;
            }
            plaintext = new byte[ciphertext.Length];
            using AesGcm aes = new(_encryptionKey, tag.Length);
            aes.Decrypt(
                nonce,
                ciphertext,
                tag,
                plaintext,
                BuildAssociatedData(
                    envelope.OwnerScopeHash,
                    envelope.RequestId,
                    envelope.WorkspaceId,
                    envelope.SourceDigest));
            StoredBuildGhostLiveSupportSession? stored =
                JsonSerializer.Deserialize<StoredBuildGhostLiveSupportSession>(plaintext, StrictJson);
            return IsValidStored(
                    stored,
                    envelope.OwnerScopeHash,
                    envelope.RequestId,
                    envelope.WorkspaceId,
                    envelope.SourceDigest)
                && !ReservesProviderCapacity(stored!.Session, now);
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or JsonException
            or FormatException
            or CryptographicException)
        {
            return false;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plaintext);
            CryptographicOperations.ZeroMemory(ciphertext);
            CryptographicOperations.ZeroMemory(tag);
            CryptographicOperations.ZeroMemory(nonce);
        }
    }

    private static string Digest(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private sealed record EncryptedSessionEnvelope(
        string Schema,
        string OwnerScopeHash,
        string RequestId,
        string WorkspaceId,
        string SourceDigest,
        string Nonce,
        string Ciphertext,
        string Tag);
}
