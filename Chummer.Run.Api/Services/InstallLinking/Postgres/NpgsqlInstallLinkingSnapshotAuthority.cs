using System.Data;
using System.Security.Cryptography;
using Npgsql;
using NpgsqlTypes;

namespace Chummer.Run.Api.Services.InstallLinking.Postgres;

public sealed class NpgsqlInstallLinkingPostgresUnitOfWorkFactory :
    IInstallLinkingPostgresUnitOfWorkFactory
{
    private readonly NpgsqlDataSource _dataSource;

    public NpgsqlInstallLinkingPostgresUnitOfWorkFactory(NpgsqlDataSource dataSource)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
    }

    public async ValueTask<IInstallLinkingPostgresUnitOfWork> BeginAsync(
        CancellationToken cancellationToken)
    {
        NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        try
        {
            NpgsqlTransaction transaction = await connection.BeginTransactionAsync(
                IsolationLevel.ReadCommitted,
                cancellationToken);
            return new NpgsqlInstallLinkingPostgresUnitOfWork(connection, transaction);
        }
        catch
        {
            await connection.DisposeAsync();
            throw;
        }
    }
}

internal sealed class NpgsqlInstallLinkingPostgresUnitOfWork :
    IInstallLinkingPostgresUnitOfWork
{
    private bool _completed;

    public NpgsqlInstallLinkingPostgresUnitOfWork(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction)
    {
        Connection = connection;
        Transaction = transaction;
    }

    public NpgsqlConnection Connection { get; }
    public NpgsqlTransaction Transaction { get; }

    public async Task CommitAsync(CancellationToken cancellationToken)
    {
        await Transaction.CommitAsync(cancellationToken);
        _completed = true;
    }

    public async Task RollbackAsync(CancellationToken cancellationToken)
    {
        if (_completed)
        {
            return;
        }

        await Transaction.RollbackAsync(cancellationToken);
        _completed = true;
    }

    public async ValueTask DisposeAsync()
    {
        await Transaction.DisposeAsync();
        await Connection.DisposeAsync();
    }
}

/// <summary>
/// PostgreSQL is the source of truth for both the monotonic generation and the complete protected
/// envelope. A filesystem copy may be repaired from this authority, but is never allowed to
/// advance or lower its head.
/// </summary>
public sealed class NpgsqlInstallLinkingSnapshotAuthority : IInstallLinkingSnapshotAuthority
{
    private readonly NpgsqlDataSource _dataSource;
    private readonly IInstallLinkingPostgresUnitOfWorkFactory _unitOfWorkFactory;
    private readonly InstallLinkingPostgresMigrator _migrator;
    private readonly TimeProvider _timeProvider;

    public NpgsqlInstallLinkingSnapshotAuthority(
        NpgsqlDataSource dataSource,
        IInstallLinkingPostgresUnitOfWorkFactory? unitOfWorkFactory = null,
        InstallLinkingPostgresMigrator? migrator = null,
        TimeProvider? timeProvider = null)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
        _unitOfWorkFactory = unitOfWorkFactory
            ?? new NpgsqlInstallLinkingPostgresUnitOfWorkFactory(dataSource);
        _migrator = migrator ?? new InstallLinkingPostgresMigrator(dataSource);
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public async Task<InstallLinkingAuthoritativeEnvelope> ReadCurrentAsync(
        CancellationToken cancellationToken = default)
    {
        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        InstallLinkingAuthoritativeEnvelope envelope = await ReadHeadAsync(
            connection,
            transaction: null,
            forUpdate: false,
            cancellationToken);
        try
        {
            ValidateAuthoritativeEnvelope(envelope);
            return envelope;
        }
        catch
        {
            envelope.Dispose();
            throw;
        }
    }

    public async Task<InstallLinkingEnvelopeCompareExchangeResult> CompareExchangeAsync(
        InstallLinkingEnvelopeCompareExchangeRequest request,
        CancellationToken cancellationToken = default)
    {
        ValidateRequest(request);
        bool commitAttempted = false;
        try
        {
            await using IInstallLinkingPostgresUnitOfWork unitOfWork =
                await _unitOfWorkFactory.BeginAsync(cancellationToken);
            using InstallLinkingAuthoritativeEnvelope current = await ReadHeadAsync(
                unitOfWork.Connection,
                unitOfWork.Transaction,
                forUpdate: true,
                cancellationToken);
            ValidateAuthoritativeEnvelope(current);

            if (MatchesCommittedRequest(current, request))
            {
                await unitOfWork.RollbackAsync(cancellationToken);
                return Result(
                    InstallLinkingEnvelopeCommitDisposition.AlreadyCommitted,
                    current,
                    "already_committed");
            }

            if (!MatchesExpectedParent(current, request))
            {
                await unitOfWork.RollbackAsync(cancellationToken);
                return Result(
                    InstallLinkingEnvelopeCommitDisposition.Conflict,
                    current,
                    "compare_exchange_conflict");
            }

            await InsertCommitAsync(unitOfWork, current, request, cancellationToken);
            DateTimeOffset updatedAtUtc = await AdvanceHeadAsync(
                unitOfWork,
                request,
                cancellationToken);
            commitAttempted = true;
            await unitOfWork.CommitAsync(cancellationToken);
            return new InstallLinkingEnvelopeCompareExchangeResult(
                InstallLinkingEnvelopeCommitDisposition.Applied,
                FromRequest(request, updatedAtUtc),
                "committed");
        }
        catch (Exception exception) when (
            commitAttempted && IsAmbiguousPersistenceFailure(exception))
        {
            return await ReconcileAmbiguousCommitAsync(request);
        }
        catch (Exception exception) when (IsUnavailablePersistenceFailure(exception))
        {
            return new InstallLinkingEnvelopeCompareExchangeResult(
                InstallLinkingEnvelopeCommitDisposition.Unavailable,
                authoritativeEnvelope: null,
                "postgres_unavailable");
        }
    }

    public async Task<InstallLinkingPostgresReadiness> CheckReadinessAsync(
        CancellationToken cancellationToken = default)
    {
        DateTimeOffset checkedAt = _timeProvider.GetUtcNow();
        InstallLinkingPostgresSchemaValidation schema;
        try
        {
            schema = await _migrator.ValidateAsync(cancellationToken);
        }
        catch (Exception exception) when (IsUnavailablePersistenceFailure(exception))
        {
            return new(
                false,
                "postgres_unavailable",
                InstallLinkingPostgresSchema.CurrentVersion,
                0,
                null,
                checkedAt);
        }

        if (!schema.Valid)
        {
            string code = schema.Problems.Contains(
                "postgres_unavailable",
                StringComparer.Ordinal)
                ? "postgres_unavailable"
                : "schema_invalid";
            return new(
                false,
                code,
                InstallLinkingPostgresSchema.CurrentVersion,
                schema.AppliedVersion,
                null,
                checkedAt);
        }

        try
        {
            if (!await _migrator.ValidateCurrentRuntimePrivilegesAsync(
                    cancellationToken))
            {
                return new(
                    false,
                    "runtime_privileges_invalid",
                    InstallLinkingPostgresSchema.CurrentVersion,
                    schema.AppliedVersion,
                    null,
                    checkedAt);
            }
        }
        catch (Exception exception) when (IsUnavailablePersistenceFailure(exception))
        {
            return new(
                false,
                "postgres_unavailable",
                InstallLinkingPostgresSchema.CurrentVersion,
                schema.AppliedVersion,
                null,
                checkedAt);
        }

        try
        {
            using InstallLinkingAuthoritativeEnvelope head =
                await ReadCurrentAsync(cancellationToken);
            return new(
                true,
                head.IsEmpty ? "empty_authority_ready" : "ready",
                InstallLinkingPostgresSchema.CurrentVersion,
                schema.AppliedVersion,
                head.Generation,
                checkedAt);
        }
        catch (Exception exception) when (IsUnavailablePersistenceFailure(exception))
        {
            return new(
                false,
                "postgres_unavailable",
                InstallLinkingPostgresSchema.CurrentVersion,
                schema.AppliedVersion,
                null,
                checkedAt);
        }
        catch (Exception exception) when (
            exception is InvalidDataException or CryptographicException)
        {
            return new(
                false,
                "authority_invalid",
                InstallLinkingPostgresSchema.CurrentVersion,
                schema.AppliedVersion,
                null,
                checkedAt);
        }
    }

    private async Task<InstallLinkingEnvelopeCompareExchangeResult>
        ReconcileAmbiguousCommitAsync(InstallLinkingEnvelopeCompareExchangeRequest request)
    {
        using CancellationTokenSource deadline = new(
            InstallLinkingPostgresDurabilityInvariants.CommitReconciliationDeadline,
            _timeProvider);
        try
        {
            using InstallLinkingAuthoritativeEnvelope head =
                await ReadCurrentAsync(deadline.Token);
            if (MatchesCommittedRequest(head, request))
            {
                return Result(
                    InstallLinkingEnvelopeCommitDisposition.AlreadyCommitted,
                    head,
                    "commit_reconciled");
            }

            bool commitExists = await CommitLogExistsAsync(
                request.CommitId,
                deadline.Token);
            if (commitExists)
            {
                // A committed log row without the exact matching head violates the atomic schema
                // contract. Never guess whether a protected snapshot should be promoted.
                return new InstallLinkingEnvelopeCompareExchangeResult(
                    InstallLinkingEnvelopeCommitDisposition.Ambiguous,
                    head.Clone(),
                    "commit_log_head_mismatch");
            }

            if (MatchesExpectedParent(head, request))
            {
                return Result(
                    InstallLinkingEnvelopeCommitDisposition.Unavailable,
                    head,
                    "commit_not_applied");
            }

            return Result(
                InstallLinkingEnvelopeCommitDisposition.Conflict,
                head,
                "compare_exchange_conflict");
        }
        catch (Exception exception) when (IsUnavailablePersistenceFailure(exception))
        {
            return new InstallLinkingEnvelopeCompareExchangeResult(
                InstallLinkingEnvelopeCommitDisposition.Ambiguous,
                authoritativeEnvelope: null,
                "commit_outcome_ambiguous");
        }
    }

    private async Task<bool> CommitLogExistsAsync(
        Guid commitId,
        CancellationToken cancellationToken)
    {
        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT EXISTS (
                SELECT 1
                FROM install_linking.snapshot_commits
                WHERE commit_id = @commit_id)
            """;
        command.Parameters.AddWithValue("commit_id", commitId);
        return Convert.ToBoolean(await command.ExecuteScalarAsync(cancellationToken));
    }

    private static async Task<InstallLinkingAuthoritativeEnvelope> ReadHeadAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction? transaction,
        bool forUpdate,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT generation, commit_id, envelope_version, snapshot_sha256,
                   envelope_sha256, protected_envelope, updated_at_utc
            FROM install_linking.snapshot_head
            WHERE singleton = true
            """ + (forUpdate ? " FOR UPDATE" : string.Empty);
        await using NpgsqlDataReader reader =
            await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidDataException(
                "The InstallLinking PostgreSQL authority head is missing.");
        }

        return new InstallLinkingAuthoritativeEnvelope(
            reader.GetInt64(0),
            reader.IsDBNull(1) ? null : reader.GetGuid(1),
            reader.IsDBNull(2) ? null : reader.GetInt32(2),
            reader.IsDBNull(3) ? null : ((byte[])reader[3]).ToArray(),
            reader.IsDBNull(4) ? null : ((byte[])reader[4]).ToArray(),
            reader.IsDBNull(5) ? null : ((byte[])reader[5]).ToArray(),
            reader.GetFieldValue<DateTimeOffset>(6));
    }

    private static async Task InsertCommitAsync(
        IInstallLinkingPostgresUnitOfWork unitOfWork,
        InstallLinkingAuthoritativeEnvelope current,
        InstallLinkingEnvelopeCompareExchangeRequest request,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = Command(unitOfWork, """
            INSERT INTO install_linking.snapshot_commits(
                generation, commit_id, parent_generation, parent_commit_id,
                parent_envelope_sha256, envelope_version, snapshot_sha256,
                envelope_sha256, committed_at_utc)
            VALUES (
                @generation, @commit_id, @parent_generation, @parent_commit_id,
                @parent_envelope_sha256, @envelope_version, @snapshot_sha256,
                @envelope_sha256, clock_timestamp())
            """);
        command.Parameters.AddWithValue("generation", request.NextGeneration);
        command.Parameters.AddWithValue("commit_id", request.CommitId);
        command.Parameters.AddWithValue("parent_generation", request.ExpectedGeneration);
        command.Parameters.AddWithValue(
            "parent_commit_id",
            NpgsqlDbType.Uuid,
            (object?)current.CommitId ?? DBNull.Value);
        command.Parameters.AddWithValue(
            "parent_envelope_sha256",
            NpgsqlDbType.Bytea,
            (object?)current.EnvelopeSha256 ?? DBNull.Value);
        command.Parameters.AddWithValue("envelope_version", request.EnvelopeVersion);
        AddBytea(command, "snapshot_sha256", request.SnapshotSha256);
        AddBytea(command, "envelope_sha256", request.EnvelopeSha256);
        if (await command.ExecuteNonQueryAsync(cancellationToken) != 1)
        {
            throw new InvalidOperationException(
                "The InstallLinking authority commit record was not inserted atomically.");
        }
    }

    private static async Task<DateTimeOffset> AdvanceHeadAsync(
        IInstallLinkingPostgresUnitOfWork unitOfWork,
        InstallLinkingEnvelopeCompareExchangeRequest request,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = Command(unitOfWork, """
            UPDATE install_linking.snapshot_head
            SET generation = @next_generation,
                commit_id = @commit_id,
                envelope_version = @envelope_version,
                snapshot_sha256 = @snapshot_sha256,
                envelope_sha256 = @envelope_sha256,
                protected_envelope = @protected_envelope,
                updated_at_utc = clock_timestamp()
            WHERE singleton = true
              AND generation = @expected_generation
              AND commit_id IS NOT DISTINCT FROM @expected_commit_id
              AND envelope_sha256 IS NOT DISTINCT FROM @expected_envelope_sha256
            RETURNING updated_at_utc
            """);
        command.Parameters.AddWithValue("next_generation", request.NextGeneration);
        command.Parameters.AddWithValue("commit_id", request.CommitId);
        command.Parameters.AddWithValue("envelope_version", request.EnvelopeVersion);
        AddBytea(command, "snapshot_sha256", request.SnapshotSha256);
        AddBytea(command, "envelope_sha256", request.EnvelopeSha256);
        AddBytea(command, "protected_envelope", request.ProtectedEnvelope);
        command.Parameters.AddWithValue("expected_generation", request.ExpectedGeneration);
        command.Parameters.AddWithValue(
            "expected_commit_id",
            NpgsqlDbType.Uuid,
            (object?)request.ExpectedCommitId ?? DBNull.Value);
        command.Parameters.AddWithValue(
            "expected_envelope_sha256",
            NpgsqlDbType.Bytea,
            (object?)request.ExpectedEnvelopeSha256 ?? DBNull.Value);
        await using NpgsqlDataReader reader =
            await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException(
                "The InstallLinking authority head did not advance atomically.");
        }

        return reader.GetFieldValue<DateTimeOffset>(0);
    }

    private static NpgsqlCommand Command(
        IInstallLinkingPostgresUnitOfWork unitOfWork,
        string sql)
    {
        NpgsqlCommand command = unitOfWork.Connection.CreateCommand();
        command.Transaction = unitOfWork.Transaction;
        command.CommandText = sql;
        return command;
    }

    private static void AddBytea(NpgsqlCommand command, string name, byte[] value)
        => command.Parameters.AddWithValue(name, NpgsqlDbType.Bytea, value);

    private static InstallLinkingEnvelopeCompareExchangeResult Result(
        InstallLinkingEnvelopeCommitDisposition disposition,
        InstallLinkingAuthoritativeEnvelope authoritative,
        string code)
        => new(disposition, authoritative.Clone(), code);

    private static InstallLinkingAuthoritativeEnvelope FromRequest(
        InstallLinkingEnvelopeCompareExchangeRequest request,
        DateTimeOffset updatedAtUtc)
        => new(
            request.NextGeneration,
            request.CommitId,
            request.EnvelopeVersion,
            request.SnapshotSha256.ToArray(),
            request.EnvelopeSha256.ToArray(),
            request.ProtectedEnvelope.ToArray(),
            updatedAtUtc);

    private static bool MatchesExpectedParent(
        InstallLinkingAuthoritativeEnvelope head,
        InstallLinkingEnvelopeCompareExchangeRequest request)
        => head.Generation == request.ExpectedGeneration
           && head.CommitId == request.ExpectedCommitId
           && FixedEquals(head.EnvelopeSha256, request.ExpectedEnvelopeSha256);

    private static bool MatchesCommittedRequest(
        InstallLinkingAuthoritativeEnvelope head,
        InstallLinkingEnvelopeCompareExchangeRequest request)
        => head.Generation == request.NextGeneration
           && head.CommitId == request.CommitId
           && head.EnvelopeVersion == request.EnvelopeVersion
           && FixedEquals(head.SnapshotSha256, request.SnapshotSha256)
           && FixedEquals(head.EnvelopeSha256, request.EnvelopeSha256)
           && FixedEquals(head.ProtectedEnvelope, request.ProtectedEnvelope);

    private static bool FixedEquals(byte[]? left, byte[]? right)
    {
        if (left is null || right is null)
        {
            return left is null && right is null;
        }

        return left.Length == right.Length
               && CryptographicOperations.FixedTimeEquals(left, right);
    }

    private static void ValidateRequest(
        InstallLinkingEnvelopeCompareExchangeRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (request.ExpectedGeneration < 0
            || request.NextGeneration != checked(request.ExpectedGeneration + 1)
            || request.CommitId == Guid.Empty
            || request.EnvelopeVersion
                != InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion
            || request.SnapshotSha256 is not
                { Length: InstallLinkingPostgresDurabilityInvariants.Sha256SizeInBytes }
            || request.EnvelopeSha256 is not
                { Length: InstallLinkingPostgresDurabilityInvariants.Sha256SizeInBytes }
            || request.ProtectedEnvelope is not
                { Length: > 0 and <= InstallLinkingPostgresDurabilityInvariants.MaximumProtectedEnvelopeBytes }
            || (request.ExpectedGeneration == 0
                && (request.ExpectedCommitId is not null
                    || request.ExpectedEnvelopeSha256 is not null))
            || (request.ExpectedGeneration > 0
                && (request.ExpectedCommitId is null
                    || request.ExpectedCommitId == Guid.Empty
                    || request.ExpectedEnvelopeSha256 is not
                        { Length: InstallLinkingPostgresDurabilityInvariants.Sha256SizeInBytes })))
        {
            throw new ArgumentException(
                "The InstallLinking authoritative-envelope compare-and-swap request is invalid.",
                nameof(request));
        }

        byte[] actualEnvelopeDigest = SHA256.HashData(request.ProtectedEnvelope);
        try
        {
            if (!CryptographicOperations.FixedTimeEquals(
                    actualEnvelopeDigest,
                    request.EnvelopeSha256))
            {
                throw new ArgumentException(
                    "The InstallLinking protected-envelope digest is invalid.",
                    nameof(request));
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(actualEnvelopeDigest);
        }
    }

    private static void ValidateAuthoritativeEnvelope(
        InstallLinkingAuthoritativeEnvelope envelope)
    {
        if (envelope.Generation < 0)
        {
            throw new InvalidDataException(
                "The InstallLinking PostgreSQL authority generation is invalid.");
        }

        if (envelope.Generation == 0)
        {
            if (envelope.CommitId is not null
                || envelope.EnvelopeVersion is not null
                || envelope.SnapshotSha256 is not null
                || envelope.EnvelopeSha256 is not null
                || envelope.ProtectedEnvelope is not null)
            {
                throw new InvalidDataException(
                    "The empty InstallLinking PostgreSQL authority head is invalid.");
            }

            return;
        }

        if (envelope.CommitId is null
            || envelope.CommitId == Guid.Empty
            || envelope.EnvelopeVersion
                != InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion
            || envelope.SnapshotSha256 is not
                { Length: InstallLinkingPostgresDurabilityInvariants.Sha256SizeInBytes }
            || envelope.EnvelopeSha256 is not
                { Length: InstallLinkingPostgresDurabilityInvariants.Sha256SizeInBytes }
            || envelope.ProtectedEnvelope is not
                { Length: > 0 and <= InstallLinkingPostgresDurabilityInvariants.MaximumProtectedEnvelopeBytes })
        {
            throw new InvalidDataException(
                "The InstallLinking PostgreSQL authority head is invalid.");
        }

        byte[] actualDigest = SHA256.HashData(envelope.ProtectedEnvelope);
        try
        {
            if (!CryptographicOperations.FixedTimeEquals(
                    actualDigest,
                    envelope.EnvelopeSha256))
            {
                throw new CryptographicException(
                    "The InstallLinking PostgreSQL protected-envelope digest does not match.");
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(actualDigest);
        }
    }

    private static bool IsAmbiguousPersistenceFailure(Exception exception)
        => exception is NpgsqlException
            or IOException
            or TimeoutException
            or OperationCanceledException;

    private static bool IsUnavailablePersistenceFailure(Exception exception)
        => IsAmbiguousPersistenceFailure(exception)
           || exception is PostgresException;

}
