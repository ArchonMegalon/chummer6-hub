using System.Text.Json;
using System.Text.Json.Serialization;
using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Contracts.Privacy;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public enum AccountErasureJournalStage
{
    Started,
    IdentityPending,
    Completed
}

public sealed record AccountErasureJournalEntry(
    string SubjectKeySha256,
    string? UserKeySha256,
    AccountErasureJournalStage Stage,
    IReadOnlyList<AccountErasureComponentReceipt> Components,
    string? PendingSubjectCiphertext,
    DateTimeOffset StartedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? IdentityRetryNotBeforeUtc,
    int IdentityRecoveryAttempts,
    DateTimeOffset? CompletedAtUtc,
    DateTimeOffset? RestoreFenceUntilUtc,
    DateTimeOffset RetainUntilUtc,
    string? ReceiptSha256);

public sealed record PendingIdentityAccountErasure(
    AccountErasureJournalEntry Entry,
    string SubjectId);

/// <summary>
/// Independent progress and audit journal for whole-account erasure. Completed rows retain only
/// HMAC-derived identifiers, counts, and receipts. The raw Identity subject is data-protected only
/// while Identity revocation is pending, then removed from the durable row.
/// </summary>
public sealed class AccountErasureJournalStore
{
    internal const string Contract = "chummer.account-erasure-journal/v1";
    internal static readonly TimeSpan AuditRetention = TimeSpan.FromDays(365);
    internal static readonly TimeSpan RestoreFence = TimeSpan.FromDays(35);
    internal static readonly TimeSpan InitialIdentityRecoveryDelay = TimeSpan.FromMinutes(1);
    private const string PathConfig = "CHUMMER_ACCOUNT_ERASURE_JOURNAL_PATH";
    private const string HmacKeyConfig = "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY";
    private const string ProtectionPurpose = "Chummer.Run.Api.AccountErasureJournal.pending-subject.v1";
    private readonly object _gate = new();
    private readonly string _storagePath;
    private readonly IDataProtector _protector;
    private readonly ILogger<AccountErasureJournalStore> _logger;
    private readonly byte[] _hmacKey;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() }
    };
    private readonly Dictionary<string, AccountErasureJournalEntry> _entries =
        new(StringComparer.Ordinal);

    public AccountErasureJournalStore(
        IConfiguration configuration,
        IDataProtectionProvider dataProtectionProvider,
        ILogger<AccountErasureJournalStore> logger)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(dataProtectionProvider);
        ArgumentNullException.ThrowIfNull(logger);
        _storagePath = ResolveStoragePath(configuration);
        _hmacKey = ResolveHmacKey(configuration);
        _protector = dataProtectionProvider.CreateProtector(ProtectionPurpose);
        _logger = logger;
        Load();
    }

    public string StoragePath => _storagePath;

    public AccountErasureJournalEntry Begin(
        string subjectKeySha256,
        string? userKeySha256,
        DateTimeOffset now)
    {
        ValidateDigest(subjectKeySha256, nameof(subjectKeySha256));
        ValidateOptionalDigest(userKeySha256, nameof(userKeySha256));
        lock (_gate)
        {
            if (_entries.TryGetValue(subjectKeySha256, out AccountErasureJournalEntry? existing))
            {
                if (existing.UserKeySha256 is not null
                    && userKeySha256 is not null
                    && !string.Equals(existing.UserKeySha256, userKeySha256, StringComparison.Ordinal))
                {
                    throw new InvalidDataException("Account-erasure journal user binding changed.");
                }

                return existing;
            }

            var entry = new AccountErasureJournalEntry(
                subjectKeySha256,
                userKeySha256,
                AccountErasureJournalStage.Started,
                [],
                PendingSubjectCiphertext: null,
                StartedAtUtc: now,
                UpdatedAtUtc: now,
                IdentityRetryNotBeforeUtc: null,
                IdentityRecoveryAttempts: 0,
                CompletedAtUtc: null,
                RestoreFenceUntilUtc: null,
                RetainUntilUtc: now.Add(AuditRetention),
                ReceiptSha256: null);
            _entries.Add(subjectKeySha256, entry);
            PersistLocked();
            return entry;
        }
    }

    public AccountErasureJournalEntry RecordComponent(
        string subjectKeySha256,
        AccountErasureComponentReceipt component,
        DateTimeOffset now)
    {
        ValidateComponent(component);
        lock (_gate)
        {
            AccountErasureJournalEntry entry = RequireEntryLocked(subjectKeySha256);
            AccountErasureComponentReceipt? existing = entry.Components.FirstOrDefault(
                item => string.Equals(item.Component, component.Component, StringComparison.Ordinal));
            if (existing is not null)
            {
                return entry;
            }

            AccountErasureComponentReceipt[] components = [.. entry.Components, component];
            entry = entry with { Components = components, UpdatedAtUtc = now };
            _entries[subjectKeySha256] = entry;
            PersistLocked();
            return entry;
        }
    }

    public AccountErasureJournalEntry MarkIdentityPending(
        string subjectKeySha256,
        string subjectId,
        DateTimeOffset now)
    {
        string normalizedSubject = string.IsNullOrWhiteSpace(subjectId)
            ? throw new ArgumentException("subjectId is required.", nameof(subjectId))
            : subjectId.Trim();
        lock (_gate)
        {
            AccountErasureJournalEntry entry = RequireEntryLocked(subjectKeySha256);
            if (entry.Stage == AccountErasureJournalStage.Completed)
            {
                return entry;
            }

            string ciphertext = entry.PendingSubjectCiphertext ?? _protector.Protect(normalizedSubject);
            entry = entry with
            {
                Stage = AccountErasureJournalStage.IdentityPending,
                PendingSubjectCiphertext = ciphertext,
                UpdatedAtUtc = now,
                IdentityRetryNotBeforeUtc = now.Add(InitialIdentityRecoveryDelay)
            };
            _entries[subjectKeySha256] = entry;
            PersistLocked();
            return entry;
        }
    }

    public AccountErasureJournalEntry Complete(
        string subjectKeySha256,
        AccountErasureComponentReceipt identityComponent,
        DateTimeOffset completedAtUtc,
        string receiptSha256)
    {
        ValidateComponent(identityComponent);
        ValidateDigest(receiptSha256, nameof(receiptSha256));
        lock (_gate)
        {
            AccountErasureJournalEntry entry = RequireEntryLocked(subjectKeySha256);
            if (entry.Stage == AccountErasureJournalStage.Completed)
            {
                return entry;
            }

            AccountErasureComponentReceipt[] components =
            [
                .. entry.Components.Where(item => !string.Equals(
                    item.Component,
                    identityComponent.Component,
                    StringComparison.Ordinal)),
                identityComponent
            ];
            entry = entry with
            {
                Stage = AccountErasureJournalStage.Completed,
                Components = components,
                PendingSubjectCiphertext = null,
                UpdatedAtUtc = completedAtUtc,
                IdentityRetryNotBeforeUtc = null,
                CompletedAtUtc = completedAtUtc,
                RestoreFenceUntilUtc = completedAtUtc.Add(RestoreFence),
                RetainUntilUtc = completedAtUtc.Add(AuditRetention),
                ReceiptSha256 = receiptSha256
            };
            _entries[subjectKeySha256] = entry;
            PersistLocked();
            return entry;
        }
    }

    public IReadOnlyList<PendingIdentityAccountErasure> GetPendingIdentityDue(DateTimeOffset now)
    {
        lock (_gate)
        {
            return _entries.Values
                .Where(entry => entry.Stage == AccountErasureJournalStage.IdentityPending
                                && entry.IdentityRetryNotBeforeUtc <= now
                                && !string.IsNullOrWhiteSpace(entry.PendingSubjectCiphertext))
                .OrderBy(static entry => entry.StartedAtUtc)
                .Select(entry => new PendingIdentityAccountErasure(
                    entry,
                    _protector.Unprotect(entry.PendingSubjectCiphertext!)))
                .ToArray();
        }
    }

    public void DelayIdentityRecovery(string subjectKeySha256, DateTimeOffset now)
    {
        lock (_gate)
        {
            AccountErasureJournalEntry entry = RequireEntryLocked(subjectKeySha256);
            if (entry.Stage != AccountErasureJournalStage.IdentityPending)
            {
                return;
            }

            int attempts = checked(entry.IdentityRecoveryAttempts + 1);
            double delayMinutes = Math.Min(60, Math.Pow(2, Math.Min(attempts, 6)));
            _entries[subjectKeySha256] = entry with
            {
                IdentityRecoveryAttempts = attempts,
                IdentityRetryNotBeforeUtc = now.AddMinutes(delayMinutes),
                UpdatedAtUtc = now
            };
            PersistLocked();
        }
    }

    public AccountErasureJournalEntry? Find(string subjectKeySha256)
    {
        lock (_gate)
        {
            return _entries.GetValueOrDefault(subjectKeySha256);
        }
    }

    public int PruneExpired(DateTimeOffset now)
    {
        lock (_gate)
        {
            string[] expired = _entries.Values
                .Where(entry => entry.Stage == AccountErasureJournalStage.Completed
                                && entry.RetainUntilUtc <= now)
                .Select(static entry => entry.SubjectKeySha256)
                .ToArray();
            foreach (string subjectKey in expired)
            {
                _entries.Remove(subjectKey);
            }

            if (expired.Length > 0)
            {
                PersistLocked();
            }

            return expired.Length;
        }
    }

    private void Load()
    {
        lock (_gate)
        {
            _entries.Clear();
            if (!File.Exists(_storagePath))
            {
                return;
            }

            AccountErasureJournalEnvelope envelope;
            try
            {
                envelope = JsonSerializer.Deserialize<AccountErasureJournalEnvelope>(
                               File.ReadAllBytes(_storagePath),
                               _jsonOptions)
                           ?? throw new InvalidDataException("Account-erasure journal is empty.");
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
            {
                throw new InvalidDataException("Account-erasure journal could not be loaded safely.", ex);
            }

            if (!string.Equals(envelope.Contract, Contract, StringComparison.Ordinal)
                || envelope.Version != 1)
            {
                throw new InvalidDataException("Account-erasure journal contract is unsupported.");
            }

            string expectedHmac = ComputeHmac(envelope.Entries ?? []);
            if (!FixedDigestEquals(expectedHmac, envelope.HmacSha256))
            {
                throw new InvalidDataException("Account-erasure journal authentication failed.");
            }

            foreach (AccountErasureJournalEntry entry in envelope.Entries ?? [])
            {
                ValidateEntry(entry);
                if (!_entries.TryAdd(entry.SubjectKeySha256, entry))
                {
                    throw new InvalidDataException("Account-erasure journal contains duplicate subject keys.");
                }
            }
        }
    }

    private void PersistLocked()
    {
        string directory = Path.GetDirectoryName(_storagePath)
                           ?? throw new InvalidOperationException("Account-erasure journal path has no directory.");
        Directory.CreateDirectory(directory);
        string temporaryPath = $"{_storagePath}.{Guid.NewGuid():N}.tmp";
        try
        {
            AccountErasureJournalEntry[] entries = _entries.Values
                .OrderBy(static entry => entry.SubjectKeySha256, StringComparer.Ordinal)
                .ToArray();
            var envelope = new AccountErasureJournalEnvelope(
                Contract,
                1,
                entries,
                ComputeHmac(entries));
            using (var stream = new FileStream(
                       temporaryPath,
                       FileMode.CreateNew,
                       FileAccess.Write,
                       FileShare.None,
                       bufferSize: 16 * 1024,
                       FileOptions.WriteThrough))
            {
                JsonSerializer.Serialize(stream, envelope, _jsonOptions);
                stream.Flush(flushToDisk: true);
            }

            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(
                    temporaryPath,
                    UnixFileMode.UserRead | UnixFileMode.UserWrite);
            }

            File.Move(temporaryPath, _storagePath, overwrite: true);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Account-erasure journal persistence failed closed.");
            throw;
        }
        finally
        {
            try
            {
                File.Delete(temporaryPath);
            }
            catch
            {
                // The committed path is authoritative; stale temp cleanup is best-effort.
            }
        }
    }

    private AccountErasureJournalEntry RequireEntryLocked(string subjectKeySha256)
    {
        ValidateDigest(subjectKeySha256, nameof(subjectKeySha256));
        return _entries.TryGetValue(subjectKeySha256, out AccountErasureJournalEntry? entry)
            ? entry
            : throw new InvalidOperationException("Account-erasure journal entry is missing.");
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration[PathConfig] ?? configuration["Privacy:AccountErasureJournalPath"];
        bool production = string.Equals(
            configuration["ASPNETCORE_ENVIRONMENT"],
            Environments.Production,
            StringComparison.OrdinalIgnoreCase);
        if (production && string.IsNullOrWhiteSpace(configured))
        {
            throw new InvalidOperationException(
                $"{PathConfig} must name an independent durable path in production.");
        }

        string resolved = string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(Path.GetTempPath(), "chummer6-hub", "account-erasure-journal.json")
            : Path.GetFullPath(configured.Trim());
        string[] mutableStorePaths =
        [
            configuration["CHUMMER_COMMUNITY_STORE_PATH"] ?? configuration["Community:StorePath"] ?? "",
            configuration["CHUMMER_SUPPORT_STORE_PATH"] ?? configuration["Support:StorePath"] ?? ""
        ];
        if (mutableStorePaths
            .Where(static path => !string.IsNullOrWhiteSpace(path))
            .Select(static path => Path.GetFullPath(path.Trim()))
            .Any(path => string.Equals(path, resolved, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException(
                "The account-erasure journal cannot share a mutable application-store file.");
        }

        return resolved;
    }

    private static byte[] ResolveHmacKey(IConfiguration configuration)
    {
        string? configured = configuration[HmacKeyConfig];
        if (string.IsNullOrWhiteSpace(configured))
        {
            throw new InvalidOperationException($"{HmacKeyConfig} is required for the erasure journal.");
        }

        byte[] key;
        try
        {
            key = Convert.FromBase64String(configured.Trim());
        }
        catch (FormatException)
        {
            key = Encoding.UTF8.GetBytes(configured.Trim());
        }

        if (key.Length < 32)
        {
            CryptographicOperations.ZeroMemory(key);
            throw new InvalidOperationException($"{HmacKeyConfig} must contain at least 32 bytes.");
        }

        return key;
    }

    private string ComputeHmac(IReadOnlyList<AccountErasureJournalEntry> entries)
    {
        var payload = new AccountErasureJournalAuthenticatedPayload(Contract, 1, entries);
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(payload, _jsonOptions);
        byte[] digest = HMACSHA256.HashData(_hmacKey, bytes);
        try
        {
            return Convert.ToHexString(digest).ToLowerInvariant();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
            CryptographicOperations.ZeroMemory(digest);
        }
    }

    private static bool FixedDigestEquals(string? left, string? right)
    {
        if (left is null || right is null || left.Length != 64 || right.Length != 64)
        {
            return false;
        }

        byte[] leftBytes = Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = Encoding.ASCII.GetBytes(right);
        try
        {
            return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(leftBytes);
            CryptographicOperations.ZeroMemory(rightBytes);
        }
    }

    private static void ValidateEntry(AccountErasureJournalEntry entry)
    {
        ValidateDigest(entry.SubjectKeySha256, nameof(entry.SubjectKeySha256));
        ValidateOptionalDigest(entry.UserKeySha256, nameof(entry.UserKeySha256));
        ValidateOptionalDigest(entry.ReceiptSha256, nameof(entry.ReceiptSha256));
        foreach (AccountErasureComponentReceipt component in entry.Components)
        {
            ValidateComponent(component);
        }

        bool completed = entry.Stage == AccountErasureJournalStage.Completed;
        if (completed != (entry.CompletedAtUtc is not null && entry.ReceiptSha256 is not null)
            || (completed && entry.PendingSubjectCiphertext is not null)
            || (entry.Stage == AccountErasureJournalStage.IdentityPending
                && string.IsNullOrWhiteSpace(entry.PendingSubjectCiphertext)))
        {
            throw new InvalidDataException("Account-erasure journal state is inconsistent.");
        }
    }

    private static void ValidateComponent(AccountErasureComponentReceipt component)
    {
        if (string.IsNullOrWhiteSpace(component.Component)
            || !component.Completed
            || component.RecordsRemoved < 0)
        {
            throw new InvalidDataException("Account-erasure component receipt is invalid.");
        }

        ValidateDigest(component.ReceiptSha256, nameof(component.ReceiptSha256));
    }

    private static void ValidateOptionalDigest(string? value, string name)
    {
        if (value is not null)
        {
            ValidateDigest(value, name);
        }
    }

    private static void ValidateDigest(string value, string name)
    {
        if (value.Length != 64 || value.Any(static character => !Uri.IsHexDigit(character)))
        {
            throw new InvalidDataException($"{name} must be one SHA-256 value.");
        }
    }
}

internal sealed record AccountErasureJournalEnvelope(
    string Contract,
    int Version,
    IReadOnlyList<AccountErasureJournalEntry>? Entries,
    string HmacSha256);

internal sealed record AccountErasureJournalAuthenticatedPayload(
    string Contract,
    int Version,
    IReadOnlyList<AccountErasureJournalEntry> Entries);
