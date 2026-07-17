using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Npgsql;

namespace Chummer.Run.Api.Services.Community.Postgres;

public sealed record PlayAuthorizationPostgresMigration(
    int Version,
    string Name,
    string Sql,
    string ChecksumSha256);

public sealed record PlayAuthorizationPostgresSchemaValidation(
    bool Valid,
    int AppliedVersion,
    IReadOnlyList<string> Problems);

public static class PlayAuthorizationPostgresMigrationCatalog
{
    private static readonly (int Version, string Name)[] MigrationNames =
    [
        (1, "V001__play_auth_foundation.sql"),
        (2, "V002__durable_idempotency.sql"),
        (3, "V003__lifecycle_guards.sql"),
        (4, "V004__checkpoint_publication_outbox.sql")
    ];

    public static IReadOnlyList<PlayAuthorizationPostgresMigration> Load()
    {
        Assembly assembly = typeof(PlayAuthorizationPostgresMigrationCatalog).Assembly;
        string[] resources = assembly.GetManifestResourceNames();
        return MigrationNames.Select(item =>
        {
            string resourceName = resources.Single(name => name.EndsWith(item.Name, StringComparison.Ordinal));
            using Stream stream = assembly.GetManifestResourceStream(resourceName)
                ?? throw new InvalidOperationException($"Embedded Play authorization migration {item.Name} is unavailable.");
            using StreamReader reader = new(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
            string sql = reader.ReadToEnd();
            string checksum = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sql))).ToLowerInvariant();
            return new PlayAuthorizationPostgresMigration(item.Version, item.Name, sql, checksum);
        }).ToArray();
    }
}

/// <summary>
/// Release-job entrypoint for the dedicated Play authorization schema. It requires a migration
/// identity that owns the schema; the runtime identity is granted only explicit DML privileges.
/// </summary>
public sealed partial class PlayAuthorizationPostgresMigrator
{
    private const long AdvisoryLockKey = 0x504C415941555448;
    private readonly NpgsqlDataSource _dataSource;
    private readonly IReadOnlyList<PlayAuthorizationPostgresMigration> _migrations;

    public PlayAuthorizationPostgresMigrator(NpgsqlDataSource dataSource)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
        _migrations = PlayAuthorizationPostgresMigrationCatalog.Load();
    }

    public async Task MigrateAsync(CancellationToken cancellationToken = default)
    {
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await AcquireMigrationLockAsync(connection, cancellationToken);
        try
        {
            await BootstrapAsync(connection, cancellationToken);
            foreach (PlayAuthorizationPostgresMigration migration in _migrations)
            {
                await ApplyMigrationAsync(connection, migration, cancellationToken);
            }
        }
        finally
        {
            await ReleaseMigrationLockAsync(connection, cancellationToken);
        }
    }

    public async Task<PlayAuthorizationPostgresSchemaValidation> ValidateAsync(
        CancellationToken cancellationToken = default)
    {
        var problems = new List<string>();
        int appliedVersion = 0;
        try
        {
            await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
            await using NpgsqlCommand exists = connection.CreateCommand();
            exists.CommandText = "SELECT to_regclass('play_auth.schema_migrations') IS NOT NULL";
            if (!Convert.ToBoolean(await exists.ExecuteScalarAsync(cancellationToken)))
            {
                return new PlayAuthorizationPostgresSchemaValidation(false, 0, ["schema_migrations_missing"]);
            }

            await using NpgsqlCommand command = connection.CreateCommand();
            command.CommandText = """
                SELECT version, checksum_sha256
                FROM play_auth.schema_migrations
                ORDER BY version
                """;
            var applied = new Dictionary<int, string>();
            await using (NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken))
            {
                while (await reader.ReadAsync(cancellationToken))
                {
                    int version = reader.GetInt32(0);
                    applied[version] = reader.GetString(1);
                    appliedVersion = Math.Max(appliedVersion, version);
                }
            }

            foreach (PlayAuthorizationPostgresMigration migration in _migrations)
            {
                if (!applied.TryGetValue(migration.Version, out string? checksum))
                {
                    problems.Add($"migration_{migration.Version}_missing");
                }
                else if (!string.Equals(checksum, migration.ChecksumSha256, StringComparison.Ordinal))
                {
                    problems.Add($"migration_{migration.Version}_checksum_mismatch");
                }
            }

            foreach (int unexpected in applied.Keys.Except(_migrations.Select(static item => item.Version)))
            {
                problems.Add($"migration_{unexpected}_unknown");
            }

            await using NpgsqlCommand objects = connection.CreateCommand();
            objects.CommandText = """
                SELECT COUNT(*)
                FROM (VALUES
                    (to_regclass('play_auth.authority_state')),
                    (to_regclass('play_auth.sessions')),
                    (to_regclass('play_auth.participants')),
                    (to_regclass('play_auth.invites')),
                    (to_regclass('play_auth.exchanges')),
                    (to_regclass('play_auth.grants')),
                    (to_regclass('play_auth.capability_verifiers')),
                    (to_regclass('play_auth.idempotency_receipts')),
                    (to_regclass('play_auth.checkpoint_baseline')),
                    (to_regclass('play_auth.checkpoint_publications')),
                    (to_regclass('play_auth.audit_log'))
                ) AS expected(object_name)
                WHERE object_name IS NULL
                """;
            if (Convert.ToInt32(await objects.ExecuteScalarAsync(cancellationToken)) != 0)
            {
                problems.Add("required_objects_missing");
            }
        }
        catch (PostgresException exception)
        {
            problems.Add($"postgres_{exception.SqlState}");
        }
        catch (NpgsqlException)
        {
            problems.Add("postgres_unavailable");
        }

        return new PlayAuthorizationPostgresSchemaValidation(problems.Count == 0, appliedVersion, problems);
    }

    public async Task GrantRuntimePrivilegesAsync(
        string runtimeRole,
        CancellationToken cancellationToken = default)
    {
        if (!RuntimeRolePattern().IsMatch(runtimeRole))
        {
            throw new ArgumentException("The PostgreSQL runtime role name is invalid.", nameof(runtimeRole));
        }

        string quotedRole;
        using (var builder = new NpgsqlCommandBuilder())
        {
            quotedRole = builder.QuoteIdentifier(runtimeRole);
        }

        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = $"""
            REVOKE ALL ON SCHEMA play_auth FROM {quotedRole};
            GRANT USAGE ON SCHEMA play_auth TO {quotedRole};

            REVOKE ALL ON ALL TABLES IN SCHEMA play_auth FROM {quotedRole};
            GRANT SELECT ON play_auth.schema_migrations TO {quotedRole};
            GRANT SELECT, UPDATE ON play_auth.authority_state TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.capability_verifiers TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.sessions TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.participants TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.invites TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.exchanges TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.grants TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.idempotency_receipts TO {quotedRole};
            GRANT SELECT, UPDATE ON play_auth.checkpoint_baseline TO {quotedRole};
            GRANT SELECT, INSERT, UPDATE ON play_auth.checkpoint_publications TO {quotedRole};
            GRANT SELECT, INSERT ON play_auth.audit_log TO {quotedRole};

            REVOKE CREATE ON SCHEMA play_auth FROM {quotedRole};
            REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA play_auth FROM {quotedRole};
            REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
                ON play_auth.schema_migrations FROM {quotedRole};
            REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
                ON play_auth.audit_log FROM {quotedRole};
            """;
        await command.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<bool> ValidateRuntimePrivilegesAsync(
        string runtimeRole,
        CancellationToken cancellationToken = default)
    {
        if (!RuntimeRolePattern().IsMatch(runtimeRole))
        {
            return false;
        }

        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT
                has_schema_privilege(@role, 'play_auth', 'USAGE')
                AND NOT has_schema_privilege(@role, 'play_auth', 'CREATE')
                AND has_table_privilege(@role, 'play_auth.sessions', 'SELECT,UPDATE')
                AND has_table_privilege(@role, 'play_auth.idempotency_receipts', 'SELECT,INSERT,UPDATE')
                AND has_table_privilege(@role, 'play_auth.checkpoint_baseline', 'SELECT,UPDATE')
                AND has_table_privilege(@role, 'play_auth.checkpoint_publications', 'SELECT,INSERT,UPDATE')
                AND has_table_privilege(@role, 'play_auth.audit_log', 'SELECT,INSERT')
                AND NOT has_table_privilege(@role, 'play_auth.audit_log', 'UPDATE')
                AND NOT has_table_privilege(@role, 'play_auth.audit_log', 'DELETE')
                AND NOT has_table_privilege(@role, 'play_auth.sessions', 'DELETE')
                AND NOT has_table_privilege(@role, 'play_auth.idempotency_receipts', 'DELETE')
            """;
        command.Parameters.AddWithValue("role", runtimeRole);
        return Convert.ToBoolean(await command.ExecuteScalarAsync(cancellationToken));
    }

    private static async Task BootstrapAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            CREATE SCHEMA IF NOT EXISTS play_auth;
            REVOKE ALL ON SCHEMA play_auth FROM PUBLIC;
            CREATE TABLE IF NOT EXISTS play_auth.schema_migrations (
                version integer PRIMARY KEY CHECK (version > 0),
                name text NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 256),
                checksum_sha256 text NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
                applied_at_utc timestamptz NOT NULL DEFAULT clock_timestamp()
            );
            REVOKE ALL ON play_auth.schema_migrations FROM PUBLIC;
            """;
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task ApplyMigrationAsync(
        NpgsqlConnection connection,
        PlayAuthorizationPostgresMigration migration,
        CancellationToken cancellationToken)
    {
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using NpgsqlCommand read = connection.CreateCommand();
        read.Transaction = transaction;
        read.CommandText = "SELECT checksum_sha256 FROM play_auth.schema_migrations WHERE version = @version";
        read.Parameters.AddWithValue("version", migration.Version);
        object? existing = await read.ExecuteScalarAsync(cancellationToken);
        if (existing is string checksum)
        {
            if (!string.Equals(checksum, migration.ChecksumSha256, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"Play authorization migration {migration.Version} checksum does not match the applied migration.");
            }

            await transaction.CommitAsync(cancellationToken);
            return;
        }

        await using NpgsqlCommand apply = connection.CreateCommand();
        apply.Transaction = transaction;
        apply.CommandText = migration.Sql;
        await apply.ExecuteNonQueryAsync(cancellationToken);

        await using NpgsqlCommand record = connection.CreateCommand();
        record.Transaction = transaction;
        record.CommandText = """
            INSERT INTO play_auth.schema_migrations(version, name, checksum_sha256)
            VALUES (@version, @name, @checksum)
            """;
        record.Parameters.AddWithValue("version", migration.Version);
        record.Parameters.AddWithValue("name", migration.Name);
        record.Parameters.AddWithValue("checksum", migration.ChecksumSha256);
        await record.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    private static async Task AcquireMigrationLockAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = "SELECT pg_advisory_lock(@key)";
        command.Parameters.AddWithValue("key", AdvisoryLockKey);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task ReleaseMigrationLockAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = "SELECT pg_advisory_unlock(@key)";
        command.Parameters.AddWithValue("key", AdvisoryLockKey);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    [GeneratedRegex("^[a-z_][a-z0-9_]{0,62}$", RegexOptions.CultureInvariant)]
    private static partial Regex RuntimeRolePattern();
}

public sealed class PlayAuthorizationPostgresReadinessProbe
{
    private const int MaximumSnapshotAttempts = 4;
    public const int MaximumLineageProofRows = 10_000;
    private static readonly TimeSpan LineageProofDeadline = TimeSpan.FromSeconds(5);
    private readonly NpgsqlDataSource _dataSource;
    private readonly PlayAuthorizationPostgresMigrator _migrator;
    private readonly IPlayAuthorizationEpochAuthority _epochAuthority;
    private readonly PlayAuthorizationCheckpointProviderActivation _checkpointProvider;
    private readonly PlayAuthorizationCheckpointProviderCapabilities _checkpointCapabilities;
    private readonly IPlayAuthorizationCheckpointPublicationReconciler _checkpointReconciler;
    private readonly PlayAuthorizationReplaySafetyPolicy _replaySafetyPolicy;
    private readonly TimeProvider _timeProvider;

    private PlayAuthorizationPostgresReadinessProbe(
        NpgsqlDataSource dataSource,
        PlayAuthorizationPostgresMigrator migrator,
        IPlayAuthorizationEpochAuthority epochAuthority,
        PlayAuthorizationCheckpointProviderActivation checkpointProvider,
        IPlayAuthorizationCheckpointPublicationReconciler checkpointReconciler,
        PlayAuthorizationReplaySafetyPolicy replaySafetyPolicy,
        TimeProvider timeProvider)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
        _migrator = migrator ?? throw new ArgumentNullException(nameof(migrator));
        _epochAuthority = epochAuthority ?? throw new ArgumentNullException(nameof(epochAuthority));
        _checkpointProvider = checkpointProvider
            ?? throw new ArgumentNullException(nameof(checkpointProvider));
        _checkpointCapabilities = _checkpointProvider.Capabilities;
        _checkpointReconciler = checkpointReconciler
            ?? throw new ArgumentNullException(nameof(checkpointReconciler));
        _replaySafetyPolicy = replaySafetyPolicy
            ?? throw new ArgumentNullException(nameof(replaySafetyPolicy));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        PlayAuthorizationCheckpointProviderDeadline.Validate(_checkpointCapabilities);
        if (_replaySafetyPolicy.MinimumQuarantine > TimeSpan.FromDays(365))
        {
            throw new InvalidOperationException(
                "The required receipt replay quarantine exceeds the bounded schema contract.");
        }
    }

    internal static PlayAuthorizationPostgresReadinessProbe Create(
        object factoryLease,
        PlayAuthorizationCheckpointProviderActivation checkpointProvider,
        NpgsqlDataSource dataSource,
        PlayAuthorizationPostgresMigrator migrator,
        IPlayAuthorizationEpochAuthority epochAuthority,
        NpgsqlPlayAuthorizationCheckpointPublicationReconciler checkpointReconciler,
        PlayAuthorizationReplaySafetyPolicy replaySafetyPolicy,
        TimeProvider timeProvider)
    {
        PlayAuthorizationPostgresDormantFactory.DemandOwnedReconciler(
            factoryLease,
            checkpointProvider,
            checkpointReconciler);
        return new(
            dataSource,
            migrator,
            epochAuthority,
            checkpointProvider,
            checkpointReconciler,
            replaySafetyPolicy,
            timeProvider);
    }

    public async Task<PlayAuthorizationPostgresReadiness> CheckAsync(
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        DateTimeOffset checkedAt = _timeProvider.GetUtcNow();
        PlayAuthorizationPostgresSchemaValidation schema = await _migrator.ValidateAsync(cancellationToken);
        if (!schema.Valid)
        {
            return new(false, "schema_invalid", PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion, null, null, checkedAt);
        }

        if (_checkpointProvider.Diagnostics.ValidationCallsInFlight != 0)
        {
            return new(false, "checkpoint_provider_validation_in_flight",
                PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion,
                null,
                null,
                checkedAt);
        }

        try
        {
            for (int attempt = 0; attempt < MaximumSnapshotAttempts; attempt++)
            {
                using ReadinessSnapshot before = await ReadSnapshotAsync(cancellationToken);
                if (before.State.Epoch <= 0 || before.State.Generation <= 0)
                {
                    return new(false, "authority_unprovisioned", PlayAuthorizationPostgresSchema.CurrentVersion,
                        schema.AppliedVersion, before.State.Epoch, before.State.Generation, checkedAt);
                }

                PlayAuthorizationCheckpointReconciliationResult reconciliation =
                    await _checkpointReconciler.ReconcileAsync(32, cancellationToken);
                if (!reconciliation.Complete)
                {
                    string status = reconciliation.Code is
                        "baseline_provider_call_in_flight"
                        or "publication_provider_call_in_flight"
                            ? "checkpoint_provider_call_in_flight"
                            : "checkpoint_pending";
                    return new(false, status, PlayAuthorizationPostgresSchema.CurrentVersion,
                        schema.AppliedVersion, before.State.Epoch, before.State.Generation, checkedAt);
                }

                using ReadinessSnapshot validated = await ReadSnapshotAsync(cancellationToken);
                if (!validated.BaselineVerified || validated.PendingPublications != 0)
                {
                    continue;
                }

                DescendantProofResult proof =
                    await VerifyDescendantProofAsync(validated.State, cancellationToken);
                if (proof != DescendantProofResult.Valid)
                {
                    string code = proof == DescendantProofResult.CapacityBlocked
                        ? "checkpoint_lineage_capacity_blocked"
                        : "checkpoint_lineage_invalid";
                    return new(false, code,
                        PlayAuthorizationPostgresSchema.CurrentVersion,
                        schema.AppliedVersion,
                        validated.State.Epoch,
                        validated.State.Generation,
                        checkedAt);
                }

                PlayAuthorizationExternalEpoch external =
                    await _epochAuthority.ReadCurrentAsync(cancellationToken);
                if (external.Epoch != validated.State.Epoch
                    || external.Generation != validated.State.Generation)
                {
                    return new(false, "epoch_mismatch", PlayAuthorizationPostgresSchema.CurrentVersion,
                        schema.AppliedVersion, validated.State.Epoch, validated.State.Generation, checkedAt);
                }

                if (!CryptographicOperations.FixedTimeEquals(
                        external.Checkpoint,
                        validated.State.ExternalCheckpoint))
                {
                    return new(false, "checkpoint_mismatch", PlayAuthorizationPostgresSchema.CurrentVersion,
                        schema.AppliedVersion, validated.State.Epoch, validated.State.Generation, checkedAt);
                }

                await _checkpointProvider.ValidateAsync(
                    external,
                    validated.State,
                    _timeProvider,
                    cancellationToken);

                using ReadinessSnapshot final = await ReadSnapshotAsync(cancellationToken);
                if (!SnapshotsEqual(validated, final))
                {
                    continue;
                }

                return new(true, "ready", PlayAuthorizationPostgresSchema.CurrentVersion,
                    schema.AppliedVersion, final.State.Epoch, final.State.Generation, checkedAt);
            }

            return new(false, "authority_changed_during_probe", PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion, null, null, checkedAt);
        }
        catch (PlayAuthorizationExternalAuthorityUnavailableException)
        {
            return new(false, "external_authority_unavailable", PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion, null, null, checkedAt);
        }
        catch (PlayAuthorizationProviderDeadlineExceededException)
        {
            return new(false, "external_authority_timeout", PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion, null, null, checkedAt);
        }
        catch (PlayAuthorizationCheckpointProviderCallInFlightException exception)
            when (exception.Lane == PlayAuthorizationCheckpointProviderLaneKind.Validation)
        {
            return new(false, "checkpoint_provider_validation_in_flight",
                PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion,
                null,
                null,
                checkedAt);
        }
        catch (Exception exception) when (exception is NpgsqlException or IOException or TimeoutException)
        {
            return new(false, "postgres_unavailable", PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion, null, null, checkedAt);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return new(false, "checkpoint_recovery_timeout", PlayAuthorizationPostgresSchema.CurrentVersion,
                schema.AppliedVersion, null, null, checkedAt);
        }
    }

    public static bool ExceedsLineageProofCapacity(long baselineSequence, long headSequence)
    {
        if (baselineSequence < 0 || headSequence < baselineSequence)
        {
            throw new ArgumentOutOfRangeException(nameof(headSequence));
        }

        return headSequence - baselineSequence > MaximumLineageProofRows;
    }

    private async Task<ReadinessSnapshot> ReadSnapshotAsync(CancellationToken cancellationToken)
    {
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT authority.epoch, authority.generation, authority.clock_high_water_utc,
                   authority.audit_head_sequence, authority.audit_head_hmac,
                   authority.external_checkpoint,
                   EXISTS (
                       SELECT 1
                       FROM play_auth.checkpoint_baseline AS baseline
                       WHERE baseline.singleton = true AND baseline.state = 'verified'),
                   (SELECT COUNT(*)
                    FROM play_auth.checkpoint_publications AS publication
                    WHERE publication.state = 'pending')
            FROM play_auth.authority_state AS authority
            WHERE authority.singleton = true
            """;
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("The Play authorization authority state row is missing.");
        }

        return new ReadinessSnapshot(
            new PlayAuthorizationPostgresState(
                reader.GetInt64(0),
                reader.GetInt64(1),
                reader.GetFieldValue<DateTimeOffset>(2),
                reader.GetInt64(3),
                ((byte[])reader[4]).ToArray(),
                ((byte[])reader[5]).ToArray()),
            reader.GetBoolean(6),
            reader.GetInt64(7));
    }

    private async Task<DescendantProofResult> VerifyDescendantProofAsync(
        PlayAuthorizationPostgresState expectedHead,
        CancellationToken cancellationToken)
    {
        using CancellationTokenSource timeout = new(LineageProofDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        VerifiedBaseline? baseline = null;
        var rows = new List<LineageProofRow>();
        try
        {
            await using (NpgsqlConnection connection =
                         await _dataSource.OpenConnectionAsync(deadline.Token))
            await using (NpgsqlTransaction transaction = await connection.BeginTransactionAsync(
                             System.Data.IsolationLevel.RepeatableRead,
                             deadline.Token))
            {
                await using (NpgsqlCommand statementTimeout = connection.CreateCommand())
                {
                    statementTimeout.Transaction = transaction;
                    statementTimeout.CommandText =
                        "SELECT set_config('statement_timeout', @timeout, true)";
                    statementTimeout.Parameters.AddWithValue(
                        "timeout",
                        $"{checked((long)LineageProofDeadline.TotalMilliseconds)}ms");
                    await statementTimeout.ExecuteNonQueryAsync(deadline.Token);
                }

                await using (NpgsqlCommand readBaseline = connection.CreateCommand())
                {
                    readBaseline.Transaction = transaction;
                    readBaseline.CommandText = """
                        SELECT baseline.baseline_id, baseline.epoch, baseline.generation,
                               baseline.clock_high_water_utc, baseline.audit_head_sequence,
                               baseline.audit_head_hmac, baseline.external_checkpoint,
                               baseline.digest_algorithm, baseline.canonical_version,
                               baseline.payload_digest_sha256,
                               authority.epoch, authority.generation,
                               authority.clock_high_water_utc, authority.audit_head_sequence,
                               authority.audit_head_hmac, authority.external_checkpoint
                        FROM play_auth.checkpoint_baseline AS baseline
                        CROSS JOIN play_auth.authority_state AS authority
                        WHERE baseline.singleton = true
                          AND baseline.state = 'verified'
                          AND authority.singleton = true
                        """;
                    await using NpgsqlDataReader reader =
                        await readBaseline.ExecuteReaderAsync(deadline.Token);
                    if (!await reader.ReadAsync(deadline.Token))
                    {
                        return DescendantProofResult.Invalid;
                    }

                    var observedHead = new PlayAuthorizationPostgresState(
                        reader.GetInt64(10),
                        reader.GetInt64(11),
                        reader.GetFieldValue<DateTimeOffset>(12),
                        reader.GetInt64(13),
                        ((byte[])reader[14]).ToArray(),
                        ((byte[])reader[15]).ToArray());
                    if (!NpgsqlPlayAuthorizationCheckpointPublicationReconciler.StatesEqual(
                            observedHead,
                            expectedHead))
                    {
                        CryptographicOperations.ZeroMemory(observedHead.AuditHeadHmac);
                        CryptographicOperations.ZeroMemory(observedHead.ExternalCheckpoint);
                        return DescendantProofResult.Invalid;
                    }

                    CryptographicOperations.ZeroMemory(observedHead.AuditHeadHmac);
                    CryptographicOperations.ZeroMemory(observedHead.ExternalCheckpoint);
                    if (reader.IsDBNull(9))
                    {
                        return DescendantProofResult.Invalid;
                    }

                    baseline = new VerifiedBaseline(
                        reader.GetGuid(0),
                        new PlayAuthorizationPostgresState(
                            reader.GetInt64(1),
                            reader.GetInt64(2),
                            reader.GetFieldValue<DateTimeOffset>(3),
                            reader.GetInt64(4),
                            ((byte[])reader[5]).ToArray(),
                            ((byte[])reader[6]).ToArray()),
                        reader.GetString(7),
                        reader.GetInt32(8),
                        ((byte[])reader[9]).ToArray());
                }

                VerifiedBaseline capturedBaseline = baseline
                    ?? throw new InvalidOperationException("The verified checkpoint baseline is missing.");
                long distance = expectedHead.AuditHeadSequence
                    - capturedBaseline.State.AuditHeadSequence;
                if (capturedBaseline.State.Epoch != expectedHead.Epoch
                    || capturedBaseline.State.Generation != expectedHead.Generation
                    || distance < 0)
                {
                    await transaction.RollbackAsync(deadline.Token);
                    return DescendantProofResult.Invalid;
                }

                if (ExceedsLineageProofCapacity(
                        capturedBaseline.State.AuditHeadSequence,
                        expectedHead.AuditHeadSequence))
                {
                    await transaction.RollbackAsync(deadline.Token);
                    return DescendantProofResult.CapacityBlocked;
                }

                await using (NpgsqlCommand readRows = connection.CreateCommand())
                {
                    readRows.Transaction = transaction;
                    readRows.CommandText = """
                        SELECT audit.sequence, audit.epoch, audit.generation,
                               audit.previous_hmac, audit.entry_hmac,
                               publication.publication_id, publication.epoch,
                               publication.generation, publication.clock_high_water_utc,
                               publication.audit_head_hmac, publication.external_checkpoint,
                               publication.digest_algorithm, publication.canonical_version,
                               publication.payload_digest_sha256, publication.state
                        FROM play_auth.audit_log AS audit
                        JOIN play_auth.checkpoint_publications AS publication
                          ON publication.audit_sequence = audit.sequence
                        WHERE audit.sequence > @baseline_sequence
                          AND audit.sequence <= @head_sequence
                        ORDER BY audit.sequence
                        LIMIT @maximum
                        """;
                    readRows.Parameters.AddWithValue(
                        "baseline_sequence",
                        capturedBaseline.State.AuditHeadSequence);
                    readRows.Parameters.AddWithValue("head_sequence", expectedHead.AuditHeadSequence);
                    readRows.Parameters.AddWithValue("maximum", MaximumLineageProofRows + 1);
                    await using NpgsqlDataReader reader =
                        await readRows.ExecuteReaderAsync(deadline.Token);
                    while (await reader.ReadAsync(deadline.Token))
                    {
                        rows.Add(new LineageProofRow(
                            reader.GetInt64(0),
                            reader.GetInt64(1),
                            reader.GetInt64(2),
                            ((byte[])reader[3]).ToArray(),
                            ((byte[])reader[4]).ToArray(),
                            reader.GetGuid(5),
                            new PlayAuthorizationPostgresState(
                                reader.GetInt64(6),
                                reader.GetInt64(7),
                                reader.GetFieldValue<DateTimeOffset>(8),
                                reader.GetInt64(0),
                                ((byte[])reader[9]).ToArray(),
                                ((byte[])reader[10]).ToArray()),
                            reader.GetString(11),
                            reader.GetInt32(12),
                            ((byte[])reader[13]).ToArray(),
                            reader.GetString(14)));
                    }
                }

                await transaction.CommitAsync(deadline.Token);
            }

            try
            {
                return baseline is not null && ValidateDescendantProof(baseline, rows, expectedHead)
                    ? DescendantProofResult.Valid
                    : DescendantProofResult.Invalid;
            }
            catch (Exception exception) when (exception is ArgumentException
                                                   or InvalidOperationException
                                                   or CryptographicException)
            {
                return DescendantProofResult.Invalid;
            }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return DescendantProofResult.Invalid;
        }
        finally
        {
            baseline?.Dispose();
            foreach (LineageProofRow row in rows)
            {
                row.Dispose();
            }
        }
    }

    private static bool ValidateDescendantProof(
        VerifiedBaseline baseline,
        IReadOnlyList<LineageProofRow> rows,
        PlayAuthorizationPostgresState expectedHead)
    {
        byte[] baselineDigest = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
            baseline.BaselineId,
            baseline.State,
            baseline.DigestAlgorithm,
            baseline.CanonicalVersion);
        bool baselineValid = CryptographicOperations.FixedTimeEquals(
            baselineDigest,
            baseline.PayloadDigestSha256);
        CryptographicOperations.ZeroMemory(baselineDigest);
        if (!baselineValid
            || baseline.State.Epoch != expectedHead.Epoch
            || baseline.State.Generation != expectedHead.Generation
            || !CryptographicOperations.FixedTimeEquals(
                baseline.State.ExternalCheckpoint,
                expectedHead.ExternalCheckpoint))
        {
            return false;
        }

        long expectedCount = expectedHead.AuditHeadSequence - baseline.State.AuditHeadSequence;
        if (expectedCount != rows.Count)
        {
            return false;
        }

        byte[] previousHmac = baseline.State.AuditHeadHmac;
        DateTimeOffset previousClock = baseline.State.ClockHighWaterUtc;
        long expectedSequence = baseline.State.AuditHeadSequence;
        foreach (LineageProofRow row in rows)
        {
            expectedSequence++;
            if (row.Sequence != expectedSequence
                || row.Epoch != expectedHead.Epoch
                || row.Generation != expectedHead.Generation
                || row.PublicationState.Epoch != row.Epoch
                || row.PublicationState.Generation != row.Generation
                || row.PublicationState.AuditHeadSequence != row.Sequence
                || row.PublicationState.ClockHighWaterUtc < previousClock
                || !string.Equals(row.State, "published", StringComparison.Ordinal)
                || !CryptographicOperations.FixedTimeEquals(row.PreviousHmac, previousHmac)
                || !CryptographicOperations.FixedTimeEquals(
                    row.EntryHmac,
                    row.PublicationState.AuditHeadHmac)
                || !CryptographicOperations.FixedTimeEquals(
                    row.PublicationState.ExternalCheckpoint,
                    expectedHead.ExternalCheckpoint))
            {
                return false;
            }

            byte[] canonical = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                row.PublicationId,
                row.PublicationState,
                row.DigestAlgorithm,
                row.CanonicalVersion);
            bool canonicalMatches = CryptographicOperations.FixedTimeEquals(
                canonical,
                row.PayloadDigestSha256);
            CryptographicOperations.ZeroMemory(canonical);
            if (!canonicalMatches)
            {
                return false;
            }

            previousHmac = row.EntryHmac;
            previousClock = row.PublicationState.ClockHighWaterUtc;
        }

        if (rows.Count == 0)
        {
            return NpgsqlPlayAuthorizationCheckpointPublicationReconciler.StatesEqual(
                baseline.State,
                expectedHead);
        }

        LineageProofRow last = rows[^1];
        return last.Sequence == expectedHead.AuditHeadSequence
            && NpgsqlPlayAuthorizationCheckpointPublicationReconciler.StatesEqual(
                last.PublicationState,
                expectedHead)
            && CryptographicOperations.FixedTimeEquals(last.EntryHmac, expectedHead.AuditHeadHmac);
    }

    private static bool SnapshotsEqual(ReadinessSnapshot left, ReadinessSnapshot right)
        => left.BaselineVerified == right.BaselineVerified
           && left.PendingPublications == right.PendingPublications
           && NpgsqlPlayAuthorizationCheckpointPublicationReconciler.StatesEqual(
               left.State,
               right.State);

    private enum DescendantProofResult
    {
        Valid,
        Invalid,
        CapacityBlocked
    }

    private sealed class ReadinessSnapshot : IDisposable
    {
        public ReadinessSnapshot(
            PlayAuthorizationPostgresState state,
            bool baselineVerified,
            long pendingPublications)
        {
            State = state;
            BaselineVerified = baselineVerified;
            PendingPublications = pendingPublications;
        }

        public PlayAuthorizationPostgresState State { get; }
        public bool BaselineVerified { get; }
        public long PendingPublications { get; }

        public void Dispose()
        {
            CryptographicOperations.ZeroMemory(State.AuditHeadHmac);
            CryptographicOperations.ZeroMemory(State.ExternalCheckpoint);
        }
    }

    private sealed class VerifiedBaseline : IDisposable
    {
        public VerifiedBaseline(
            Guid baselineId,
            PlayAuthorizationPostgresState state,
            string digestAlgorithm,
            int canonicalVersion,
            byte[] payloadDigestSha256)
        {
            BaselineId = baselineId;
            State = state;
            DigestAlgorithm = digestAlgorithm;
            CanonicalVersion = canonicalVersion;
            PayloadDigestSha256 = payloadDigestSha256;
        }

        public Guid BaselineId { get; }
        public PlayAuthorizationPostgresState State { get; }
        public string DigestAlgorithm { get; }
        public int CanonicalVersion { get; }
        public byte[] PayloadDigestSha256 { get; }

        public void Dispose()
        {
            CryptographicOperations.ZeroMemory(State.AuditHeadHmac);
            CryptographicOperations.ZeroMemory(State.ExternalCheckpoint);
            CryptographicOperations.ZeroMemory(PayloadDigestSha256);
        }
    }

    private sealed class LineageProofRow : IDisposable
    {
        public LineageProofRow(
            long sequence,
            long epoch,
            long generation,
            byte[] previousHmac,
            byte[] entryHmac,
            Guid publicationId,
            PlayAuthorizationPostgresState publicationState,
            string digestAlgorithm,
            int canonicalVersion,
            byte[] payloadDigestSha256,
            string state)
        {
            Sequence = sequence;
            Epoch = epoch;
            Generation = generation;
            PreviousHmac = previousHmac;
            EntryHmac = entryHmac;
            PublicationId = publicationId;
            PublicationState = publicationState;
            DigestAlgorithm = digestAlgorithm;
            CanonicalVersion = canonicalVersion;
            PayloadDigestSha256 = payloadDigestSha256;
            State = state;
        }

        public long Sequence { get; }
        public long Epoch { get; }
        public long Generation { get; }
        public byte[] PreviousHmac { get; }
        public byte[] EntryHmac { get; }
        public Guid PublicationId { get; }
        public PlayAuthorizationPostgresState PublicationState { get; }
        public string DigestAlgorithm { get; }
        public int CanonicalVersion { get; }
        public byte[] PayloadDigestSha256 { get; }
        public string State { get; }

        public void Dispose()
        {
            CryptographicOperations.ZeroMemory(PreviousHmac);
            CryptographicOperations.ZeroMemory(EntryHmac);
            CryptographicOperations.ZeroMemory(PublicationState.AuditHeadHmac);
            CryptographicOperations.ZeroMemory(PublicationState.ExternalCheckpoint);
            CryptographicOperations.ZeroMemory(PayloadDigestSha256);
        }
    }

    internal static async Task<PlayAuthorizationPostgresState> ReadStateAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken,
        NpgsqlTransaction? transaction = null,
        bool forUpdate = false)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT epoch, generation, clock_high_water_utc, audit_head_sequence,
                   audit_head_hmac, external_checkpoint
            FROM play_auth.authority_state
            WHERE singleton = true
            """ + (forUpdate ? " FOR UPDATE" : string.Empty);
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("The Play authorization authority state row is missing.");
        }

        return new(
            reader.GetInt64(0),
            reader.GetInt64(1),
            reader.GetFieldValue<DateTimeOffset>(2),
            reader.GetInt64(3),
            (byte[])reader[4],
            (byte[])reader[5]);
    }
}
