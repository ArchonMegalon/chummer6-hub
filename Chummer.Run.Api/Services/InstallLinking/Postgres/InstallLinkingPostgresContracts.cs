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
        return ReadConnectionStringFile(path, requireLinuxSecurity: environment.IsProduction());
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
        return ReadConnectionStringFile(path, requireLinuxSecurity: true);
    }

    public static string ReadConnectionStringFile(
        string path,
        bool requireLinuxSecurity)
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

            if (requireLinuxSecurity
                && builder.SslMode != SslMode.VerifyFull)
            {
                throw new InvalidDataException(
                    "The PostgreSQL credential file must require full TLS server identity verification.");
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
