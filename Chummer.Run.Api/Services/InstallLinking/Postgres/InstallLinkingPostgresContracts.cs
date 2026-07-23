using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Npgsql;

namespace Chummer.Run.Api.Services.InstallLinking.Postgres;

public static class InstallLinkingPostgresSchema
{
    public const string Name = "install_linking";
    public const int CurrentVersion = 2;
}

public static class InstallLinkingPostgresDurabilityInvariants
{
    public const int ProtectedEnvelopeVersion = 2;
    public const int Sha256SizeInBytes = SHA256.HashSizeInBytes;
    public const int MaximumProtectedEnvelopeBytes = 64 * 1024 * 1024;
    public const int MaximumConnectionStringBytes = 16 * 1024;
    public const int ConnectionTimeoutSeconds = 5;
    public const int CommandTimeoutSeconds = 15;
    public static readonly TimeSpan CommitReconciliationDeadline = TimeSpan.FromSeconds(8);
}

public static class InstallLinkingPostgresConnectionConfiguration
{
    public const string RuntimeConnectionStringFileConfigurationKey =
        "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE";
    public const string MigratorConnectionStringFileEnvironmentVariable =
        "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE";
    public const string ExpectedHostConfigurationKey =
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST";
    public const string ExpectedDatabaseConfigurationKey =
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE";
    public const string ExpectedPortConfigurationKey =
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT";
    public const string ExpectedRuntimeRoleConfigurationKey =
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE";
    public const string ExpectedRootCertificatePath =
        "/run/chummer-secrets/install-linking-postgres-server-ca.pem";
    public const string RejectedRuntimeInlineConnectionStringConfigurationKey =
        "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING";
    public const string RejectedMigratorInlineConnectionStringEnvironmentVariable =
        "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING";

    public static string LoadRuntimeConnectionString(
        IConfiguration configuration,
        IHostEnvironment environment)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(environment);

        if (!string.IsNullOrWhiteSpace(
                configuration[RejectedRuntimeInlineConnectionStringConfigurationKey]))
        {
            throw new InvalidOperationException(
                "The InstallLinking PostgreSQL runtime connection string must be supplied by an owner-only file.");
        }

        string path = RequirePath(
            configuration[RuntimeConnectionStringFileConfigurationKey],
            RuntimeConnectionStringFileConfigurationKey);
        bool production = environment.IsProduction();
        string? expectedHost = production
            ? RequireExpectedHost(configuration[ExpectedHostConfigurationKey])
            : NormalizeOptionalExpectedHost(configuration[ExpectedHostConfigurationKey]);
        string? expectedDatabase = production
            ? RequireExpectedDatabase(
                configuration[ExpectedDatabaseConfigurationKey])
            : NormalizeOptionalExpectedDatabase(
                configuration[ExpectedDatabaseConfigurationKey]);
        int? expectedPort = production
            ? RequireExpectedPort(configuration[ExpectedPortConfigurationKey])
            : NormalizeOptionalExpectedPort(
                configuration[ExpectedPortConfigurationKey]);
        return ReadConnectionStringFile(
            path,
            requireLinuxSecurity: production,
            expectedHost: expectedHost,
            expectedDatabase: expectedDatabase,
            expectedPort: expectedPort,
            expectedRootCertificatePath: production ? ExpectedRootCertificatePath : null);
    }

    public static string LoadMigratorConnectionStringFromEnvironment()
    {
        if (!string.IsNullOrWhiteSpace(
                Environment.GetEnvironmentVariable(
                    RejectedMigratorInlineConnectionStringEnvironmentVariable)))
        {
            throw new InvalidOperationException(
                "The InstallLinking PostgreSQL migrator connection string must be supplied by an owner-only file.");
        }

        string path = RequirePath(
            Environment.GetEnvironmentVariable(
                MigratorConnectionStringFileEnvironmentVariable),
            MigratorConnectionStringFileEnvironmentVariable);
        return ReadConnectionStringFile(
            path,
            requireLinuxSecurity: true,
            expectedHost: RequireExpectedHost(
                Environment.GetEnvironmentVariable(ExpectedHostConfigurationKey)),
            expectedDatabase: RequireExpectedDatabase(
                Environment.GetEnvironmentVariable(
                    ExpectedDatabaseConfigurationKey)),
            expectedPort: RequireExpectedPort(
                Environment.GetEnvironmentVariable(
                    ExpectedPortConfigurationKey)),
            expectedRootCertificatePath: ExpectedRootCertificatePath);
    }

    public static string LoadExpectedRuntimeRole(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        return RequireExpectedRuntimeRole(
            configuration[ExpectedRuntimeRoleConfigurationKey]);
    }

    public static string ReadConnectionStringFile(
        string path,
        bool requireLinuxSecurity,
        string? expectedHost = null,
        string? expectedDatabase = null,
        int? expectedPort = null,
        string? expectedRootCertificatePath = null)
    {
        string fullPath = Path.GetFullPath(
            string.IsNullOrWhiteSpace(path)
                ? throw new ArgumentException("A connection string file path is required.", nameof(path))
                : path.Trim());
        byte[] bytes;
        if (OperatingSystem.IsLinux())
        {
            bytes = LinuxSecureFile.ReadOwnerOnlyRegularFile(
                fullPath,
                InstallLinkingPostgresDurabilityInvariants.MaximumConnectionStringBytes,
                repairOwnerMode: false);
        }
        else
        {
            if (requireLinuxSecurity)
            {
                throw new PlatformNotSupportedException(
                    "Owner-only no-follow PostgreSQL credential intake requires Linux.");
            }

            FileInfo file = new(fullPath);
            if (!file.Exists
                || file.LinkTarget is not null
                || file.Length is <= 0
                or > InstallLinkingPostgresDurabilityInvariants.MaximumConnectionStringBytes)
            {
                throw new InvalidDataException("The PostgreSQL credential file is invalid.");
            }

            bytes = File.ReadAllBytes(fullPath);
        }

        try
        {
            string value = new UTF8Encoding(
                    encoderShouldEmitUTF8Identifier: false,
                    throwOnInvalidBytes: true)
                .GetString(bytes);
            if (value.EndsWith("\r\n", StringComparison.Ordinal))
            {
                value = value[..^2];
            }
            else if (value.EndsWith('\n'))
            {
                value = value[..^1];
            }

            if (value.Length is <= 0 or > InstallLinkingPostgresDurabilityInvariants.MaximumConnectionStringBytes
                || value.IndexOfAny(['\0', '\r', '\n']) >= 0)
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential file must contain exactly one non-empty UTF-8 line.");
            }

            NpgsqlConnectionStringBuilder builder;
            try
            {
                builder = new NpgsqlConnectionStringBuilder(value)
                {
                    IncludeErrorDetail = false,
                    PersistSecurityInfo = false,
                    ApplicationName = "chummer-run-install-linking",
                    Timeout = InstallLinkingPostgresDurabilityInvariants.ConnectionTimeoutSeconds,
                    CommandTimeout = InstallLinkingPostgresDurabilityInvariants.CommandTimeoutSeconds
                };
            }
            catch (ArgumentException exception)
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential file does not contain a valid connection string.",
                    exception);
            }

            if (string.IsNullOrWhiteSpace(builder.Host)
                || string.IsNullOrWhiteSpace(builder.Database)
                || string.IsNullOrWhiteSpace(builder.Username))
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential file is missing a required connection property.");
            }

            if (!string.IsNullOrWhiteSpace(builder.Options))
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential file must not set startup session options.");
            }

            if (requireLinuxSecurity
                && builder.SslMode != SslMode.VerifyFull)
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential file must require full TLS server identity verification.");
            }

            if (expectedHost is not null
                && !string.Equals(builder.Host, expectedHost, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential Host does not match the reviewed certificate identity.");
            }

            if (expectedDatabase is not null
                && !string.Equals(
                    builder.Database,
                    expectedDatabase,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential Database does not match the reviewed authority.");
            }

            if (expectedPort is not null
                && builder.Port != expectedPort.Value)
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential Port does not match the reviewed authority.");
            }

            if (expectedRootCertificatePath is not null
                && !string.Equals(
                    builder.RootCertificate,
                    expectedRootCertificatePath,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential file must use the reviewed mounted server CA bundle.");
            }

            return builder.ConnectionString;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    private static string RequirePath(string? path, string key)
        => string.IsNullOrWhiteSpace(path)
            ? throw new InvalidOperationException($"{key} is required; its value is never printed.")
            : path;

    private static string RequireExpectedHost(string? value)
        => NormalizeOptionalExpectedHost(value)
            ?? throw new InvalidOperationException(
                $"{ExpectedHostConfigurationKey} is required; its value is never printed.");

    private static string RequireExpectedDatabase(string? value)
        => NormalizeOptionalExpectedDatabase(value)
            ?? throw new InvalidOperationException(
                $"{ExpectedDatabaseConfigurationKey} is required; its value is never printed.");

    private static int RequireExpectedPort(string? value)
        => NormalizeOptionalExpectedPort(value)
            ?? throw new InvalidOperationException(
                $"{ExpectedPortConfigurationKey} is required; its value is never printed.");

    private static string RequireExpectedRuntimeRole(string? value)
    {
        string role = value?.Trim() ?? string.Empty;
        if (!IsValidRuntimeRole(role))
        {
            throw new InvalidOperationException(
                $"{ExpectedRuntimeRoleConfigurationKey} must be one safe PostgreSQL role name.");
        }

        return role;
    }

    public static bool IsValidRuntimeRole(string? value)
    {
        if (string.IsNullOrEmpty(value)
            || value.Length > 63
            || !(char.IsAsciiLetter(value[0]) || value[0] == '_'))
        {
            return false;
        }

        return value.AsSpan(1).IndexOfAnyExcept(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$")
            < 0;
    }

    private static string? NormalizeOptionalExpectedHost(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string host = value.Trim();
        if (host.EndsWith(".", StringComparison.Ordinal)
            || host.Length > 253
            || Uri.CheckHostName(host) != UriHostNameType.Dns)
        {
            throw new InvalidOperationException(
                $"{ExpectedHostConfigurationKey} must be one DNS name without a trailing dot.");
        }

        return host;
    }

    private static string? NormalizeOptionalExpectedDatabase(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string database = value.Trim();
        if (database.Length > 63
            || database.Any(
                static character =>
                    !(char.IsAsciiLetterOrDigit(character)
                      || character is '_' or '.' or '-'))
            || !char.IsAsciiLetterOrDigit(database[0])
                && database[0] != '_')
        {
            throw new InvalidOperationException(
                $"{ExpectedDatabaseConfigurationKey} must be one safe PostgreSQL database name.");
        }

        return database;
    }

    private static int? NormalizeOptionalExpectedPort(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        if (!int.TryParse(
                value,
                NumberStyles.None,
                CultureInfo.InvariantCulture,
                out int port)
            || port is < 1 or > 65535)
        {
            throw new InvalidOperationException(
                $"{ExpectedPortConfigurationKey} must be one decimal TCP port.");
        }

        return port;
    }
}

public static class InstallLinkingPostgresAuthorityIdentity
{
    public static async Task<string> ComputeSha256Async(
        NpgsqlConnection connection,
        NpgsqlTransaction? transaction = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        string host = (connection.Host ?? string.Empty)
            .Trim()
            .ToLowerInvariant();
        int port = connection.Port;
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT current_database()::text";
        string database =
            Convert.ToString(
                await command.ExecuteScalarAsync(cancellationToken),
                CultureInfo.InvariantCulture)
            ?? string.Empty;
        if (string.IsNullOrWhiteSpace(host)
            || port is < 1 or > 65535
            || string.IsNullOrWhiteSpace(database))
        {
            throw new InvalidOperationException(
                "The authenticated PostgreSQL authority identity is incomplete.");
        }

        string canonical =
            "chummer.install_linking_postgres_authority.v1\n"
            + $"host={host}\n"
            + $"port={port.ToString(CultureInfo.InvariantCulture)}\n"
            + $"database={database}\n";
        return Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(canonical)))
            .ToLowerInvariant();
    }
}

public static class InstallLinkingLocalStoreAbsenceProof
{
    public const string TrustedStateRoot = "/app/state";
    public const string CanonicalStorePath =
        "/app/state/install-linking/install-linking-store.json";

    public static bool HasRetainedEntryOrUnsafeAncestor(
        string path,
        string trustedRoot = TrustedStateRoot)
    {
        string root = Path.GetFullPath(trustedRoot);
        string candidate = Path.GetFullPath(path);
        string relative = Path.GetRelativePath(root, candidate);
        if (relative == "."
            || Path.IsPathRooted(relative)
            || relative.Equals("..", StringComparison.Ordinal)
            || relative.StartsWith(
                $"..{Path.DirectorySeparatorChar}",
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "The InstallLinking local-store proof path escaped its trusted state root.");
        }

        string current = root;
        string[] components = relative.Split(
            Path.DirectorySeparatorChar,
            StringSplitOptions.RemoveEmptyEntries);
        for (int index = 0; index < components.Length; index++)
        {
            current = Path.Combine(current, components[index]);
            if (IsSymbolicLink(current))
            {
                return true;
            }

            FileAttributes attributes;
            try
            {
                attributes = File.GetAttributes(current);
            }
            catch (FileNotFoundException)
            {
                return false;
            }
            catch (DirectoryNotFoundException)
            {
                return false;
            }

            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                return true;
            }

            bool final = index == components.Length - 1;
            if (final)
            {
                return true;
            }

            if ((attributes & FileAttributes.Directory) == 0)
            {
                return true;
            }
        }

        return false;
    }

    private static bool IsSymbolicLink(string path)
    {
        var file = new FileInfo(path);
        file.Refresh();
        if (file.LinkTarget is not null)
        {
            return true;
        }

        var directory = new DirectoryInfo(path);
        directory.Refresh();
        return directory.LinkTarget is not null;
    }
}

public sealed class InstallLinkingAuthoritativeEnvelope : IDisposable
{
    public InstallLinkingAuthoritativeEnvelope(
        long generation,
        Guid? commitId,
        int? envelopeVersion,
        byte[]? snapshotSha256,
        byte[]? envelopeSha256,
        byte[]? protectedEnvelope,
        DateTimeOffset updatedAtUtc)
    {
        Generation = generation;
        CommitId = commitId;
        EnvelopeVersion = envelopeVersion;
        SnapshotSha256 = snapshotSha256;
        EnvelopeSha256 = envelopeSha256;
        ProtectedEnvelope = protectedEnvelope;
        UpdatedAtUtc = updatedAtUtc;
    }

    public long Generation { get; }
    public Guid? CommitId { get; }
    public int? EnvelopeVersion { get; }
    public byte[]? SnapshotSha256 { get; }
    public byte[]? EnvelopeSha256 { get; }
    public byte[]? ProtectedEnvelope { get; }
    public DateTimeOffset UpdatedAtUtc { get; }
    public bool IsEmpty => Generation == 0;

    public InstallLinkingAuthoritativeEnvelope Clone()
        => new(
            Generation,
            CommitId,
            EnvelopeVersion,
            SnapshotSha256?.ToArray(),
            EnvelopeSha256?.ToArray(),
            ProtectedEnvelope?.ToArray(),
            UpdatedAtUtc);

    public void Dispose()
    {
        if (SnapshotSha256 is not null)
        {
            CryptographicOperations.ZeroMemory(SnapshotSha256);
        }

        if (EnvelopeSha256 is not null)
        {
            CryptographicOperations.ZeroMemory(EnvelopeSha256);
        }

        if (ProtectedEnvelope is not null)
        {
            CryptographicOperations.ZeroMemory(ProtectedEnvelope);
        }
    }
}

public sealed record InstallLinkingEnvelopeCompareExchangeRequest(
    long ExpectedGeneration,
    Guid? ExpectedCommitId,
    byte[]? ExpectedEnvelopeSha256,
    long NextGeneration,
    Guid CommitId,
    int EnvelopeVersion,
    byte[] SnapshotSha256,
    byte[] EnvelopeSha256,
    byte[] ProtectedEnvelope);

public enum InstallLinkingEnvelopeCommitDisposition
{
    Applied,
    AlreadyCommitted,
    Conflict,
    Unavailable,
    Ambiguous
}

public sealed class InstallLinkingEnvelopeCompareExchangeResult : IDisposable
{
    public InstallLinkingEnvelopeCompareExchangeResult(
        InstallLinkingEnvelopeCommitDisposition disposition,
        InstallLinkingAuthoritativeEnvelope? authoritativeEnvelope,
        string code)
    {
        Disposition = disposition;
        AuthoritativeEnvelope = authoritativeEnvelope;
        Code = code;
    }

    public InstallLinkingEnvelopeCommitDisposition Disposition { get; }
    public InstallLinkingAuthoritativeEnvelope? AuthoritativeEnvelope { get; }
    public string Code { get; }
    public bool Committed => Disposition is
        InstallLinkingEnvelopeCommitDisposition.Applied
        or InstallLinkingEnvelopeCommitDisposition.AlreadyCommitted;

    public void Dispose() => AuthoritativeEnvelope?.Dispose();
}

public sealed record InstallLinkingPostgresSchemaValidation(
    bool Valid,
    int AppliedVersion,
    IReadOnlyList<string> Problems);

public sealed record InstallLinkingPostgresRuntimeRoleProof(
    bool Valid,
    bool CurrentRoleMatches,
    bool LeastPrivilegeValid,
    string AuthorityIdentitySha256,
    string Code);

public sealed record InstallLinkingPostgresRuntimeAuthorityReadiness(
    bool Ready,
    string Code,
    bool CurrentRoleMatches,
    bool LeastPrivilegeValid,
    string? RuntimeRoleSha256,
    string? AuthorityIdentitySha256,
    DateTimeOffset CheckedAtUtc);

public sealed record InstallLinkingPostgresEmptyAuthorityProof(
    bool Valid,
    bool CurrentRoleMatches,
    bool LeastPrivilegeValid,
    bool SchemaValid,
    int AppliedSchemaVersion,
    long? HeadGeneration,
    long CommitCount,
    bool Empty,
    string AuthorityIdentitySha256,
    string Code);

public sealed record InstallLinkingPostgresReadiness(
    bool Ready,
    string Code,
    int ExpectedSchemaVersion,
    int AppliedSchemaVersion,
    long? Generation,
    DateTimeOffset CheckedAtUtc);

public interface IInstallLinkingSnapshotAuthority
{
    Task<InstallLinkingAuthoritativeEnvelope> ReadCurrentAsync(
        CancellationToken cancellationToken = default);

    Task<InstallLinkingEnvelopeCompareExchangeResult> CompareExchangeAsync(
        InstallLinkingEnvelopeCompareExchangeRequest request,
        CancellationToken cancellationToken = default);

    Task<InstallLinkingPostgresReadiness> CheckReadinessAsync(
        CancellationToken cancellationToken = default);
}

public interface IInstallLinkingPostgresUnitOfWork : IAsyncDisposable
{
    NpgsqlConnection Connection { get; }
    NpgsqlTransaction Transaction { get; }
    Task CommitAsync(CancellationToken cancellationToken);
    Task RollbackAsync(CancellationToken cancellationToken);
}

public interface IInstallLinkingPostgresUnitOfWorkFactory
{
    ValueTask<IInstallLinkingPostgresUnitOfWork> BeginAsync(
        CancellationToken cancellationToken);
}
