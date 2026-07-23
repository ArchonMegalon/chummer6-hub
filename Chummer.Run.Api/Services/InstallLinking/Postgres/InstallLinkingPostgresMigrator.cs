using System.Data;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Npgsql;

namespace Chummer.Run.Api.Services.InstallLinking.Postgres;

public sealed record InstallLinkingPostgresMigration(
    int Version,
    string Name,
    string Sql,
    string ChecksumSha256);

public static class InstallLinkingPostgresMigrationCatalog
{
    private static readonly (int Version, string Name)[] MigrationNames =
    [
        (1, "V001__install_linking_snapshot_authority.sql"),
        (2, "V002__install_linking_snapshot_authority_contract.sql")
    ];

    public static IReadOnlyList<InstallLinkingPostgresMigration> Load()
    {
        Assembly assembly = typeof(InstallLinkingPostgresMigrationCatalog).Assembly;
        string[] resources = assembly.GetManifestResourceNames();
        return MigrationNames.Select(item =>
        {
            string resourceName = resources.Single(
                name => name.EndsWith(item.Name, StringComparison.Ordinal));
            using Stream stream = assembly.GetManifestResourceStream(resourceName)
                ?? throw new InvalidOperationException(
                    $"Embedded InstallLinking migration {item.Name} is unavailable.");
            using StreamReader reader = new(
                stream,
                Encoding.UTF8,
                detectEncodingFromByteOrderMarks: true);
            string sql = reader.ReadToEnd();
            string checksum = Convert.ToHexString(
                    SHA256.HashData(Encoding.UTF8.GetBytes(sql)))
                .ToLowerInvariant();
            return new InstallLinkingPostgresMigration(
                item.Version,
                item.Name,
                sql,
                checksum);
        }).ToArray();
    }
}

/// <summary>
/// Release-job migration boundary. The supplied identity owns the dedicated schema; the API
/// runtime identity receives only the explicitly validated CAS privileges.
/// </summary>
public sealed partial class InstallLinkingPostgresMigrator
{
    private const long AdvisoryLockKey = 0x494E53544C494E4B;
    private const int RequiredPostgresMajorVersion = 17;
    private const string CommitGuardBody = """
        DECLARE
            current_head install_linking.snapshot_head%ROWTYPE;
        BEGIN
            SELECT * INTO current_head
            FROM install_linking.snapshot_head
            WHERE singleton = true
            FOR UPDATE;

            IF NOT FOUND
               OR NEW.generation <> current_head.generation + 1
               OR NEW.parent_generation <> current_head.generation
               OR NEW.parent_commit_id IS DISTINCT FROM current_head.commit_id
               OR NEW.parent_envelope_sha256 IS DISTINCT FROM current_head.envelope_sha256 THEN
                RAISE EXCEPTION 'install-linking authority commit must append to the current head'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        """;
    private const string HeadGuardBody = """
        DECLARE
            committed install_linking.snapshot_commits%ROWTYPE;
        BEGIN
            IF NEW.singleton IS DISTINCT FROM OLD.singleton
               OR NEW.generation <> OLD.generation + 1 THEN
                RAISE EXCEPTION 'install-linking authority head must advance exactly one generation'
                    USING ERRCODE = '23514';
            END IF;

            SELECT * INTO committed
            FROM install_linking.snapshot_commits
            WHERE commit_id = NEW.commit_id;

            IF NOT FOUND
               OR committed.generation <> NEW.generation
               OR committed.parent_generation <> OLD.generation
               OR committed.parent_commit_id IS DISTINCT FROM OLD.commit_id
               OR committed.parent_envelope_sha256 IS DISTINCT FROM OLD.envelope_sha256
               OR committed.envelope_version <> NEW.envelope_version
               OR committed.snapshot_sha256 <> NEW.snapshot_sha256
               OR committed.envelope_sha256 <> NEW.envelope_sha256 THEN
                RAISE EXCEPTION 'install-linking authority head does not match its append-only commit'
                    USING ERRCODE = '23514';
            END IF;

            IF sha256(NEW.protected_envelope) <> NEW.envelope_sha256 THEN
                RAISE EXCEPTION 'install-linking protected envelope digest does not match'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        """;
    private readonly NpgsqlDataSource _dataSource;
    private readonly IReadOnlyList<InstallLinkingPostgresMigration> _migrations;

    public InstallLinkingPostgresMigrator(NpgsqlDataSource dataSource)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
        _migrations = InstallLinkingPostgresMigrationCatalog.Load();
    }

    public async Task MigrateAsync(CancellationToken cancellationToken = default)
    {
        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        await AcquireMigrationLockAsync(connection, cancellationToken);
        try
        {
            await BootstrapAsync(connection, cancellationToken);
            foreach (InstallLinkingPostgresMigration migration in _migrations)
            {
                await ApplyMigrationAsync(connection, migration, cancellationToken);
            }
        }
        finally
        {
            await ReleaseMigrationLockAsync(connection, cancellationToken);
        }
    }

    public async Task<InstallLinkingPostgresSchemaValidation> ValidateAsync(
        CancellationToken cancellationToken = default)
    {
        try
        {
            await using NpgsqlConnection connection =
                await _dataSource.OpenConnectionAsync(cancellationToken);
            return await ValidateOnConnectionAsync(
                connection,
                transaction: null,
                cancellationToken);
        }
        catch (PostgresException exception)
        {
            return new(false, 0, [$"postgres_{exception.SqlState}"]);
        }
        catch (NpgsqlException)
        {
            return new(false, 0, ["postgres_unavailable"]);
        }
    }

    private async Task<InstallLinkingPostgresSchemaValidation>
        ValidateOnConnectionAsync(
            NpgsqlConnection connection,
            NpgsqlTransaction? transaction,
            CancellationToken cancellationToken)
    {
        var problems = new List<string>();
        int appliedVersion = 0;
        await using NpgsqlCommand exists = connection.CreateCommand();
        exists.Transaction = transaction;
        exists.CommandText =
            "SELECT to_regclass('install_linking.schema_migrations') IS NOT NULL";
        if (!Convert.ToBoolean(await exists.ExecuteScalarAsync(cancellationToken)))
        {
            return new(false, 0, ["schema_migrations_missing"]);
        }

        await using (NpgsqlCommand appliedCommand = connection.CreateCommand())
        {
            appliedCommand.Transaction = transaction;
            appliedCommand.CommandText = """
                SELECT
                    COALESCE(version, 0)::integer,
                    COALESCE(name, '')::text,
                    COALESCE(checksum_sha256, '')::text
                FROM install_linking.schema_migrations
                ORDER BY version, name, checksum_sha256
                """;
            var applied =
                new Dictionary<int, (string Name, string Checksum)>();
            var appliedNames = new HashSet<string>(StringComparer.Ordinal);
            int appliedRowCount = 0;
            bool duplicateHistory = false;
            await using NpgsqlDataReader reader =
                await appliedCommand.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                appliedRowCount++;
                int version = reader.GetInt32(0);
                string name = reader.GetString(1);
                string checksum = reader.GetString(2);
                duplicateHistory |= !applied.TryAdd(
                    version,
                    (name, checksum));
                duplicateHistory |= !appliedNames.Add(name);
                appliedVersion = Math.Max(appliedVersion, version);
            }

            if (duplicateHistory
                || appliedRowCount != _migrations.Count)
            {
                problems.Add("migration_history_multiplicity_invalid");
            }

            foreach (InstallLinkingPostgresMigration migration in _migrations)
            {
                if (!applied.TryGetValue(
                        migration.Version,
                        out (string Name, string Checksum) appliedMigration))
                {
                    problems.Add($"migration_{migration.Version}_missing");
                }
                else if (!string.Equals(
                             appliedMigration.Name,
                             migration.Name,
                             StringComparison.Ordinal))
                {
                    problems.Add($"migration_{migration.Version}_name_mismatch");
                }
                else if (!string.Equals(
                             appliedMigration.Checksum,
                             migration.ChecksumSha256,
                             StringComparison.Ordinal))
                {
                    problems.Add($"migration_{migration.Version}_checksum_mismatch");
                }
            }

            foreach (int unexpected in applied.Keys.Except(
                         _migrations.Select(static item => item.Version)))
            {
                problems.Add($"migration_{unexpected}_unknown");
            }
        }

        await using (NpgsqlCommand objects = connection.CreateCommand())
        {
            objects.Transaction = transaction;
            objects.CommandText = """
                SELECT COUNT(*)
                FROM (VALUES
                    (to_regclass('install_linking.snapshot_head')),
                    (to_regclass('install_linking.snapshot_commits'))
                ) AS expected(object_name)
                WHERE object_name IS NULL
                """;
            if (Convert.ToInt32(
                    await objects.ExecuteScalarAsync(cancellationToken)) != 0)
            {
                problems.Add("required_objects_missing");
            }
        }

        if (!problems.Contains("required_objects_missing", StringComparer.Ordinal))
        {
            await using (NpgsqlCommand relations = connection.CreateCommand())
            {
                relations.Transaction = transaction;
                relations.CommandText = """
                    SELECT COUNT(*) = 3
                       AND bool_and(
                           relation.relkind = 'r'
                           AND relation.relpersistence = 'p'
                           AND NOT relation.relrowsecurity
                           AND NOT relation.relforcerowsecurity)
                    FROM pg_catalog.pg_class AS relation
                    WHERE relation.relnamespace = 'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                    """;
                if (!Convert.ToBoolean(
                        await relations.ExecuteScalarAsync(cancellationToken)))
                {
                    problems.Add("authority_relation_posture_invalid");
                }
            }

            await using NpgsqlCommand head = connection.CreateCommand();
            head.Transaction = transaction;
            head.CommandText = """
                SELECT COUNT(*) = 1
                   AND bool_and(singleton)
                   AND bool_and(
                        (generation = 0
                            AND commit_id IS NULL
                            AND envelope_version IS NULL
                            AND snapshot_sha256 IS NULL
                            AND envelope_sha256 IS NULL
                            AND protected_envelope IS NULL)
                        OR
                        (generation > 0
                            AND commit_id IS NOT NULL
                            AND envelope_version = 2
                            AND octet_length(snapshot_sha256) = 32
                            AND octet_length(envelope_sha256) = 32
                            AND octet_length(protected_envelope) BETWEEN 1 AND 67108864))
                FROM install_linking.snapshot_head
                """;
            if (!Convert.ToBoolean(
                    await head.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_head_invalid");
            }

            await ValidateLiveAuthorityContractAsync(
                connection,
                transaction,
                problems,
                cancellationToken);
        }

        return new(
            problems.Count == 0,
            appliedVersion,
            problems);
    }

    public async Task GrantRuntimePrivilegesAsync(
        string runtimeRole,
        CancellationToken cancellationToken = default)
    {
        if (!RuntimeRolePattern().IsMatch(runtimeRole))
        {
            throw new ArgumentException(
                "The PostgreSQL runtime role name is invalid.",
                nameof(runtimeRole));
        }

        string quotedRole;
        using (var builder = new NpgsqlCommandBuilder())
        {
            quotedRole = builder.QuoteIdentifier(runtimeRole);
        }

        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlTransaction transaction =
            await connection.BeginTransactionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = $"""
            REVOKE ALL ON SCHEMA install_linking FROM {quotedRole};
            GRANT USAGE ON SCHEMA install_linking TO {quotedRole};

            REVOKE ALL ON ALL TABLES IN SCHEMA install_linking FROM {quotedRole};
            REVOKE SELECT (version, name, checksum_sha256, applied_at_utc),
                   INSERT (version, name, checksum_sha256, applied_at_utc),
                   UPDATE (version, name, checksum_sha256, applied_at_utc),
                   REFERENCES (version, name, checksum_sha256, applied_at_utc)
                ON install_linking.schema_migrations FROM {quotedRole};
            REVOKE SELECT (
                       singleton,
                       generation,
                       commit_id,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       protected_envelope,
                       updated_at_utc),
                   INSERT (
                       singleton,
                       generation,
                       commit_id,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       protected_envelope,
                       updated_at_utc),
                   UPDATE (
                       singleton,
                       generation,
                       commit_id,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       protected_envelope,
                       updated_at_utc),
                   REFERENCES (
                       singleton,
                       generation,
                       commit_id,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       protected_envelope,
                       updated_at_utc)
                ON install_linking.snapshot_head FROM {quotedRole};
            REVOKE SELECT (
                       generation,
                       commit_id,
                       parent_generation,
                       parent_commit_id,
                       parent_envelope_sha256,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       committed_at_utc),
                   INSERT (
                       generation,
                       commit_id,
                       parent_generation,
                       parent_commit_id,
                       parent_envelope_sha256,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       committed_at_utc),
                   UPDATE (
                       generation,
                       commit_id,
                       parent_generation,
                       parent_commit_id,
                       parent_envelope_sha256,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       committed_at_utc),
                   REFERENCES (
                       generation,
                       commit_id,
                       parent_generation,
                       parent_commit_id,
                       parent_envelope_sha256,
                       envelope_version,
                       snapshot_sha256,
                       envelope_sha256,
                       committed_at_utc)
                ON install_linking.snapshot_commits FROM {quotedRole};
            GRANT SELECT ON install_linking.schema_migrations TO {quotedRole};
            GRANT SELECT, UPDATE ON install_linking.snapshot_head TO {quotedRole};
            GRANT SELECT, INSERT ON install_linking.snapshot_commits TO {quotedRole};

            REVOKE CREATE ON SCHEMA install_linking FROM {quotedRole};
            REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
                ON ALL TABLES IN SCHEMA install_linking FROM {quotedRole};
            REVOKE INSERT, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
                ON install_linking.snapshot_head FROM {quotedRole};
            REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
                ON install_linking.snapshot_commits FROM {quotedRole};
            REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
                ON install_linking.schema_migrations FROM {quotedRole};
            REVOKE ALL ON ALL FUNCTIONS IN SCHEMA install_linking FROM {quotedRole};
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

        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        return await ValidateRuntimePrivilegesOnConnectionAsync(
            connection,
            runtimeRole,
            cancellationToken);
    }

    public async Task<bool> ValidateCurrentRuntimePrivilegesAsync(
        CancellationToken cancellationToken = default)
    {
        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        (string SessionRole, string CurrentRole) identity =
            await ReadCurrentIdentityAsync(
                connection,
                transaction: null,
                cancellationToken);
        return string.Equals(
                   identity.SessionRole,
                   identity.CurrentRole,
                   StringComparison.Ordinal)
            && RuntimeRolePattern().IsMatch(identity.CurrentRole)
            && await ValidateRuntimePrivilegesOnConnectionAsync(
                connection,
                identity.CurrentRole,
                cancellationToken);
    }

    public async Task<bool> ValidateCurrentRuntimePrivilegesAsync(
        string expectedRuntimeRole,
        CancellationToken cancellationToken = default)
    {
        if (!RuntimeRolePattern().IsMatch(expectedRuntimeRole))
        {
            return false;
        }

        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        (string SessionRole, string CurrentRole) identity =
            await ReadCurrentIdentityAsync(
                connection,
                transaction: null,
                cancellationToken);
        return string.Equals(
                   identity.SessionRole,
                   expectedRuntimeRole,
                   StringComparison.Ordinal)
            && string.Equals(
                identity.CurrentRole,
                expectedRuntimeRole,
                StringComparison.Ordinal)
            && await ValidateRuntimePrivilegesOnConnectionAsync(
                connection,
                expectedRuntimeRole,
                cancellationToken);
    }

    public async Task<InstallLinkingPostgresRuntimeRoleProof>
        ProveCurrentRuntimeRoleAsync(
            string expectedRuntimeRole,
            CancellationToken cancellationToken = default)
    {
        if (!RuntimeRolePattern().IsMatch(expectedRuntimeRole))
        {
            return new(false, false, false, string.Empty, "runtime_role_invalid");
        }

        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlTransaction transaction =
            await connection.BeginTransactionAsync(
                IsolationLevel.RepeatableRead,
                cancellationToken);
        await SetTransactionReadOnlyAsync(
            connection,
            transaction,
            cancellationToken);
        string authorityIdentitySha256 =
            await InstallLinkingPostgresAuthorityIdentity.ComputeSha256Async(
                connection,
                transaction,
                cancellationToken);
        (string SessionRole, string CurrentRole) identity =
            await ReadCurrentIdentityAsync(
                connection,
                transaction,
                cancellationToken);
        bool roleMatches =
            string.Equals(
                identity.SessionRole,
                expectedRuntimeRole,
                StringComparison.Ordinal)
            && string.Equals(
                identity.CurrentRole,
                expectedRuntimeRole,
                StringComparison.Ordinal);
        bool privilegesValid = roleMatches
            && await ValidateRuntimePrivilegesOnConnectionAsync(
                connection,
                expectedRuntimeRole,
                cancellationToken,
                transaction);
        await transaction.RollbackAsync(cancellationToken);
        return new(
            roleMatches && privilegesValid,
            roleMatches,
            privilegesValid,
            authorityIdentitySha256,
            roleMatches && privilegesValid
                ? "runtime_role_least_privilege"
                : "runtime_role_privileges_invalid");
    }

    public async Task<InstallLinkingPostgresEmptyAuthorityProof>
        ProveEmptyRuntimeAuthorityAsync(
            string expectedRuntimeRole,
            CancellationToken cancellationToken = default)
    {
        if (!RuntimeRolePattern().IsMatch(expectedRuntimeRole))
        {
            return new(
                false,
                false,
                false,
                false,
                0,
                null,
                0,
                false,
                string.Empty,
                "runtime_role_invalid");
        }

        await using NpgsqlConnection connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlTransaction transaction =
            await connection.BeginTransactionAsync(
                IsolationLevel.RepeatableRead,
                cancellationToken);
        await SetTransactionReadOnlyAsync(
            connection,
            transaction,
            cancellationToken);
        string authorityIdentitySha256 =
            await InstallLinkingPostgresAuthorityIdentity.ComputeSha256Async(
                connection,
                transaction,
                cancellationToken);
        (string SessionRole, string CurrentRole) identity =
            await ReadCurrentIdentityAsync(
                connection,
                transaction,
                cancellationToken);
        bool roleMatches =
            string.Equals(
                identity.SessionRole,
                expectedRuntimeRole,
                StringComparison.Ordinal)
            && string.Equals(
                identity.CurrentRole,
                expectedRuntimeRole,
                StringComparison.Ordinal);
        InstallLinkingPostgresSchemaValidation schema =
            await ValidateOnConnectionAsync(
                connection,
                transaction,
                cancellationToken);
        if (!schema.Valid
            || schema.AppliedVersion != InstallLinkingPostgresSchema.CurrentVersion)
        {
            await transaction.RollbackAsync(cancellationToken);
            return new(
                false,
                roleMatches,
                false,
                false,
                schema.AppliedVersion,
                null,
                0,
                false,
                authorityIdentitySha256,
                "schema_invalid");
        }

        bool privilegesValid = roleMatches
            && await ValidateRuntimePrivilegesOnConnectionAsync(
                connection,
                expectedRuntimeRole,
                cancellationToken,
                transaction);

        string expectedMigrationValues = string.Join(
            ", ",
            _migrations.Select(
                (_, index) =>
                    $"(@version{index}, @name{index}, @checksum{index})"));
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = $"""
            WITH expected_migrations(version, name, checksum_sha256) AS (
                VALUES {expectedMigrationValues}
            ),
            actual_migrations AS (
                SELECT version, name, checksum_sha256
                FROM install_linking.schema_migrations
            ),
            relation_proof AS (
                SELECT
                    COUNT(*) = 3
                    AND bool_and(
                        relation.relkind = 'r'
                        AND relation.relpersistence = 'p'
                        AND NOT relation.relrowsecurity
                        AND NOT relation.relforcerowsecurity) AS exact
                FROM pg_catalog.pg_class AS relation
                WHERE relation.relnamespace = 'install_linking'::regnamespace
                  AND relation.relname IN (
                      'schema_migrations',
                      'snapshot_head',
                      'snapshot_commits')
            ),
            migration_proof AS (
                SELECT
                    NOT EXISTS (
                        SELECT * FROM expected_migrations
                        EXCEPT ALL
                        SELECT * FROM actual_migrations)
                    AND NOT EXISTS (
                        SELECT * FROM actual_migrations
                        EXCEPT ALL
                        SELECT * FROM expected_migrations) AS exact,
                    COALESCE(MAX(version), 0)::integer AS applied_version
                FROM actual_migrations
            ),
            head_proof AS (
                SELECT
                    COUNT(*) = 1
                    AND bool_and(
                        singleton
                        AND generation = 0
                        AND commit_id IS NULL
                        AND envelope_version IS NULL
                        AND snapshot_sha256 IS NULL
                        AND envelope_sha256 IS NULL
                        AND protected_envelope IS NULL
                        AND updated_at_utc =
                            TIMESTAMPTZ '1970-01-01 00:00:00+00') AS empty,
                    CASE
                        WHEN COUNT(*) = 1 THEN MAX(generation)
                        ELSE NULL
                    END AS generation
                FROM install_linking.snapshot_head
            ),
            commit_proof AS (
                SELECT COUNT(*)::bigint AS commit_count
                FROM install_linking.snapshot_commits
            )
            SELECT
                migration_proof.exact,
                migration_proof.applied_version,
                relation_proof.exact,
                head_proof.empty,
                head_proof.generation,
                commit_proof.commit_count
            FROM migration_proof
            CROSS JOIN relation_proof
            CROSS JOIN head_proof
            CROSS JOIN commit_proof
            """;
        for (int index = 0; index < _migrations.Count; index++)
        {
            InstallLinkingPostgresMigration migration = _migrations[index];
            command.Parameters.AddWithValue($"version{index}", migration.Version);
            command.Parameters.AddWithValue($"name{index}", migration.Name);
            command.Parameters.AddWithValue(
                $"checksum{index}",
                migration.ChecksumSha256);
        }

        bool schemaExact;
        bool relationPostureExact;
        int appliedVersion;
        bool headEmpty;
        long? headGeneration;
        long commitCount;
        await using (NpgsqlDataReader reader =
                     await command.ExecuteReaderAsync(cancellationToken))
        {
            if (!await reader.ReadAsync(cancellationToken))
            {
                throw new InvalidOperationException(
                    "The InstallLinking empty-authority proof returned no row.");
            }

            schemaExact = reader.GetBoolean(0);
            appliedVersion = reader.GetInt32(1);
            relationPostureExact = reader.GetBoolean(2);
            headEmpty = reader.GetBoolean(3);
            headGeneration = reader.IsDBNull(4) ? null : reader.GetInt64(4);
            commitCount = reader.GetInt64(5);
            if (await reader.ReadAsync(cancellationToken))
            {
                throw new InvalidOperationException(
                    "The InstallLinking empty-authority proof returned multiple rows.");
            }
        }

        await transaction.RollbackAsync(cancellationToken);
        bool empty = headEmpty
            && headGeneration == 0
            && commitCount == 0;
        bool valid = roleMatches
            && privilegesValid
            && schemaExact
            && relationPostureExact
            && appliedVersion == InstallLinkingPostgresSchema.CurrentVersion
            && empty;
        string code = valid
            ? "empty_generation_zero"
            : !roleMatches || !privilegesValid
                ? "runtime_role_privileges_invalid"
                : !schemaExact
                    || !relationPostureExact
                    || appliedVersion != InstallLinkingPostgresSchema.CurrentVersion
                    ? "schema_invalid"
                    : "authority_nonempty";
        return new(
            valid,
            roleMatches,
            privilegesValid,
            schemaExact && relationPostureExact,
            appliedVersion,
            headGeneration,
            commitCount,
            empty,
            authorityIdentitySha256,
            code);
    }

    private static async Task<bool> ValidateRuntimePrivilegesOnConnectionAsync(
        NpgsqlConnection connection,
        string runtimeRole,
        CancellationToken cancellationToken,
        NpgsqlTransaction? transaction = null)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_roles
                    WHERE rolname = @role
                      AND rolcanlogin
                      AND NOT rolsuper
                      AND NOT rolcreaterole
                      AND NOT rolcreatedb
                      AND NOT rolreplication
                      AND NOT rolbypassrls)
                AND current_setting('session_replication_role') = 'origin'
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_parameter_acl
                    WHERE parname = 'session_replication_role')
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_db_role_setting AS role_setting
                    CROSS JOIN LATERAL
                        unnest(role_setting.setconfig) AS setting(value)
                    LEFT JOIN pg_catalog.pg_roles AS configured_role
                        ON configured_role.oid = role_setting.setrole
                    WHERE role_setting.setdatabase IN (
                              0,
                              (
                                  SELECT oid
                                  FROM pg_catalog.pg_database
                                  WHERE datname = current_database()))
                      AND (
                          role_setting.setrole = 0
                          OR configured_role.rolname = @role)
                      AND split_part(setting.value, '=', 1) IN (
                          'role',
                          'session_replication_role'))
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    INNER JOIN pg_catalog.pg_roles AS member
                        ON member.oid = membership.member
                    INNER JOIN pg_catalog.pg_roles AS granted_role
                        ON granted_role.oid = membership.roleid
                    WHERE member.rolname = @role
                       OR granted_role.rolname = @role)
                AND has_schema_privilege(@role, 'install_linking', 'USAGE')
                AND NOT has_schema_privilege(@role, 'install_linking', 'CREATE')
                AND NOT has_schema_privilege(
                    @role,
                    'install_linking',
                    'USAGE WITH GRANT OPTION')
                AND has_table_privilege(@role, 'install_linking.schema_migrations', 'SELECT')
                AND NOT has_table_privilege(
                    @role,
                    'install_linking.schema_migrations',
                    'SELECT WITH GRANT OPTION')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'INSERT')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'UPDATE')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'DELETE')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'TRUNCATE')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'REFERENCES')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'TRIGGER')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'MAINTAIN')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.schema_migrations',
                    'SELECT WITH GRANT OPTION')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.schema_migrations',
                    'INSERT')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.schema_migrations',
                    'UPDATE')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.schema_migrations',
                    'REFERENCES')
                AND has_table_privilege(@role, 'install_linking.snapshot_head', 'SELECT')
                AND has_table_privilege(@role, 'install_linking.snapshot_head', 'UPDATE')
                AND NOT has_table_privilege(
                    @role,
                    'install_linking.snapshot_head',
                    'SELECT WITH GRANT OPTION')
                AND NOT has_table_privilege(
                    @role,
                    'install_linking.snapshot_head',
                    'UPDATE WITH GRANT OPTION')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'INSERT')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'DELETE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'TRUNCATE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'REFERENCES')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'TRIGGER')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'MAINTAIN')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_head',
                    'SELECT WITH GRANT OPTION')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_head',
                    'INSERT')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_head',
                    'REFERENCES')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_head',
                    'UPDATE WITH GRANT OPTION')
                AND has_table_privilege(@role, 'install_linking.snapshot_commits', 'SELECT')
                AND has_table_privilege(@role, 'install_linking.snapshot_commits', 'INSERT')
                AND NOT has_table_privilege(
                    @role,
                    'install_linking.snapshot_commits',
                    'SELECT WITH GRANT OPTION')
                AND NOT has_table_privilege(
                    @role,
                    'install_linking.snapshot_commits',
                    'INSERT WITH GRANT OPTION')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'UPDATE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'DELETE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'TRUNCATE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'REFERENCES')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'TRIGGER')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'MAINTAIN')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_commits',
                    'SELECT WITH GRANT OPTION')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_commits',
                    'UPDATE')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_commits',
                    'REFERENCES')
                AND NOT has_any_column_privilege(
                    @role,
                    'install_linking.snapshot_commits',
                    'INSERT WITH GRANT OPTION')
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_attribute AS attribute
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = attribute.attrelid
                    CROSS JOIN LATERAL
                        pg_catalog.aclexplode(attribute.attacl) AS column_acl
                    INNER JOIN pg_catalog.pg_roles AS grantee
                        ON grantee.oid = column_acl.grantee
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                      AND attribute.attnum > 0
                      AND NOT attribute.attisdropped
                      AND grantee.rolname = @role)
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_proc AS procedure
                    WHERE procedure.pronamespace = 'install_linking'::regnamespace
                      AND has_function_privilege(@role, procedure.oid, 'EXECUTE'))
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_proc AS procedure
                    WHERE procedure.pronamespace =
                            'install_linking'::regnamespace
                      AND pg_has_role(@role, procedure.proowner, 'MEMBER'))
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_class AS relation
                    WHERE relation.relnamespace = 'install_linking'::regnamespace
                      AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
                      AND relation.relname NOT IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                      AND (
                          has_table_privilege(@role, relation.oid, 'SELECT')
                          OR has_table_privilege(@role, relation.oid, 'INSERT')
                          OR has_table_privilege(@role, relation.oid, 'UPDATE')
                          OR has_table_privilege(@role, relation.oid, 'DELETE')
                          OR has_table_privilege(@role, relation.oid, 'TRUNCATE')
                          OR has_table_privilege(@role, relation.oid, 'REFERENCES')
                          OR has_table_privilege(@role, relation.oid, 'TRIGGER')
                          OR has_table_privilege(@role, relation.oid, 'MAINTAIN')
                          OR has_any_column_privilege(@role, relation.oid, 'SELECT')
                          OR has_any_column_privilege(@role, relation.oid, 'INSERT')
                          OR has_any_column_privilege(@role, relation.oid, 'UPDATE')
                          OR has_any_column_privilege(@role, relation.oid, 'REFERENCES')))
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_class AS sequence
                    WHERE sequence.relnamespace = 'install_linking'::regnamespace
                      AND sequence.relkind = 'S'
                      AND (
                          has_sequence_privilege(@role, sequence.oid, 'USAGE')
                          OR has_sequence_privilege(@role, sequence.oid, 'SELECT')
                          OR has_sequence_privilege(@role, sequence.oid, 'UPDATE')))
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_namespace AS namespace
                    WHERE namespace.oid = 'install_linking'::regnamespace
                      AND pg_has_role(@role, namespace.nspowner, 'MEMBER'))
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_database AS database_record
                    WHERE database_record.datname = current_database()
                      AND pg_has_role(@role, database_record.datdba, 'MEMBER'))
                AND NOT has_database_privilege(
                    @role,
                    current_database(),
                    'CREATE')
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_class AS relation
                    WHERE relation.relnamespace = 'install_linking'::regnamespace
                      AND pg_has_role(@role, relation.relowner, 'MEMBER'))
            """;
        command.Parameters.AddWithValue("role", runtimeRole);
        return Convert.ToBoolean(
            await command.ExecuteScalarAsync(cancellationToken));
    }

    private static async Task SetTransactionReadOnlyAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SET TRANSACTION READ ONLY";
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task<(string SessionRole, string CurrentRole)>
        ReadCurrentIdentityAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction? transaction,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT session_user, current_user";
        await using NpgsqlDataReader reader =
            await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException(
                "The PostgreSQL identity proof returned no row.");
        }

        string sessionRole = reader.GetString(0);
        string currentRole = reader.GetString(1);
        if (await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException(
                "The PostgreSQL identity proof returned multiple rows.");
        }

        return (sessionRole, currentRole);
    }

    private static async Task ValidateLiveAuthorityContractAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction? transaction,
        ICollection<string> problems,
        CancellationToken cancellationToken)
    {
        await using (NpgsqlCommand version = connection.CreateCommand())
        {
            version.Transaction = transaction;
            version.CommandText =
                "SELECT current_setting('server_version_num')::integer / 10000 = @major";
            version.Parameters.AddWithValue("major", RequiredPostgresMajorVersion);
            if (!Convert.ToBoolean(await version.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("postgres_major_version_invalid");
            }
        }

        await using (NpgsqlCommand sessionPosture = connection.CreateCommand())
        {
            sessionPosture.Transaction = transaction;
            sessionPosture.CommandText = """
                SELECT
                    current_setting('session_replication_role') = 'origin'
                    AND NOT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_parameter_acl
                        WHERE parname = 'session_replication_role')
                    AND NOT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_db_role_setting AS role_setting
                        CROSS JOIN LATERAL
                            unnest(role_setting.setconfig) AS setting(value)
                        WHERE role_setting.setdatabase IN (
                                  0,
                                  (
                                      SELECT oid
                                      FROM pg_catalog.pg_database
                                      WHERE datname = current_database()))
                          AND split_part(setting.value, '=', 1) IN (
                              'role',
                              'session_replication_role'))
                """;
            if (!Convert.ToBoolean(
                    await sessionPosture.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_session_posture_invalid");
            }
        }

        await using (NpgsqlCommand ownership = connection.CreateCommand())
        {
            ownership.Transaction = transaction;
            ownership.CommandText = """
                WITH database_owner AS (
                    SELECT datdba AS owner_oid
                    FROM pg_catalog.pg_database
                    WHERE datname = current_database()
                ), object_owners(object_kind, object_name, owner_oid) AS (
                    SELECT
                        'schema'::text,
                        namespace.nspname::text,
                        namespace.nspowner
                    FROM pg_catalog.pg_namespace AS namespace
                    WHERE namespace.nspname = 'install_linking'
                    UNION ALL
                    SELECT
                        'table'::text,
                        relation.relname::text,
                        relation.relowner
                    FROM pg_catalog.pg_class AS relation
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                    UNION ALL
                    SELECT
                        'function'::text,
                        procedure.proname::text,
                        procedure.proowner
                    FROM pg_catalog.pg_proc AS procedure
                    WHERE procedure.pronamespace =
                            'install_linking'::regnamespace
                      AND procedure.proname IN (
                          'guard_snapshot_commit_append_v2',
                          'guard_snapshot_head_advance_v2')
                      AND procedure.pronargs = 0
                ), current_role_record AS (
                    SELECT oid
                    FROM pg_catalog.pg_roles
                    WHERE rolname = current_user
                ), runtime_acl_grantees AS (
                    SELECT DISTINCT expanded_acl.grantee
                    FROM pg_catalog.pg_class AS relation
                    CROSS JOIN LATERAL pg_catalog.aclexplode(
                        COALESCE(
                            relation.relacl,
                            pg_catalog.acldefault(
                                'r',
                                relation.relowner))) AS expanded_acl
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                      AND expanded_acl.grantee <> relation.relowner
                    UNION
                    SELECT DISTINCT expanded_acl.grantee
                    FROM pg_catalog.pg_namespace AS namespace
                    CROSS JOIN LATERAL pg_catalog.aclexplode(
                        COALESCE(
                            namespace.nspacl,
                            pg_catalog.acldefault(
                                'n',
                                namespace.nspowner))) AS expanded_acl
                    WHERE namespace.nspname = 'install_linking'
                      AND expanded_acl.grantee <> namespace.nspowner
                ), ownership_summary AS (
                    SELECT
                        COUNT(*) AS object_count,
                        COUNT(DISTINCT object_owners.owner_oid)
                            AS distinct_owner_count,
                        MIN(object_owners.owner_oid) AS shared_owner_oid
                    FROM object_owners
                )
                SELECT
                    ownership_summary.object_count = 6
                    AND ownership_summary.distinct_owner_count = 1
                    AND ownership_summary.shared_owner_oid =
                        database_owner.owner_oid
                    AND (
                        EXISTS (
                            SELECT 1
                            FROM current_role_record
                            WHERE current_role_record.oid =
                                database_owner.owner_oid)
                        OR pg_catalog.pg_has_role(
                            session_user,
                            database_owner.owner_oid,
                            'SET')
                        OR (
                            session_user = current_user
                            AND EXISTS (
                                SELECT 1
                                FROM runtime_acl_grantees
                                INNER JOIN current_role_record
                                    ON current_role_record.oid =
                                        runtime_acl_grantees.grantee)))
                FROM ownership_summary
                CROSS JOIN database_owner
                """;
            if (!Convert.ToBoolean(
                    await ownership.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_ownership_invalid");
            }
        }

        await using (NpgsqlCommand accessControl = connection.CreateCommand())
        {
            accessControl.Transaction = transaction;
            accessControl.CommandText = """
                WITH owner_anchor AS (
                    SELECT datdba AS owner_oid
                    FROM pg_catalog.pg_database
                    WHERE datname = current_database()
                ), expected_tables(
                    relation_name,
                    runtime_privileges) AS (
                    VALUES
                        (
                            'schema_migrations',
                            ARRAY['SELECT']::text[]),
                        (
                            'snapshot_head',
                            ARRAY['SELECT', 'UPDATE']::text[]),
                        (
                            'snapshot_commits',
                            ARRAY['SELECT', 'INSERT']::text[])
                ), actual_acl(
                    object_kind,
                    object_name,
                    column_name,
                    grantee,
                    privilege_type,
                    is_grantable) AS (
                    SELECT
                        'schema'::text,
                        namespace.nspname::text,
                        NULL::text,
                        expanded_acl.grantee,
                        expanded_acl.privilege_type::text,
                        expanded_acl.is_grantable
                    FROM pg_catalog.pg_namespace AS namespace
                    CROSS JOIN LATERAL pg_catalog.aclexplode(
                        COALESCE(
                            namespace.nspacl,
                            pg_catalog.acldefault(
                                'n',
                                namespace.nspowner))) AS expanded_acl
                    WHERE namespace.nspname = 'install_linking'
                    UNION ALL
                    SELECT
                        'table'::text,
                        relation.relname::text,
                        NULL::text,
                        expanded_acl.grantee,
                        expanded_acl.privilege_type::text,
                        expanded_acl.is_grantable
                    FROM pg_catalog.pg_class AS relation
                    CROSS JOIN LATERAL pg_catalog.aclexplode(
                        COALESCE(
                            relation.relacl,
                            pg_catalog.acldefault(
                                'r',
                                relation.relowner))) AS expanded_acl
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                    UNION ALL
                    SELECT
                        'column'::text,
                        relation.relname::text,
                        attribute.attname::text,
                        expanded_acl.grantee,
                        expanded_acl.privilege_type::text,
                        expanded_acl.is_grantable
                    FROM pg_catalog.pg_attribute AS attribute
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = attribute.attrelid
                    CROSS JOIN LATERAL pg_catalog.aclexplode(
                        attribute.attacl) AS expanded_acl
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                      AND attribute.attnum > 0
                      AND NOT attribute.attisdropped
                    UNION ALL
                    SELECT
                        'function'::text,
                        procedure.proname::text,
                        NULL::text,
                        expanded_acl.grantee,
                        expanded_acl.privilege_type::text,
                        expanded_acl.is_grantable
                    FROM pg_catalog.pg_proc AS procedure
                    CROSS JOIN LATERAL pg_catalog.aclexplode(
                        COALESCE(
                            procedure.proacl,
                            pg_catalog.acldefault(
                                'f',
                                procedure.proowner))) AS expanded_acl
                    WHERE procedure.pronamespace =
                            'install_linking'::regnamespace
                      AND procedure.proname IN (
                          'guard_snapshot_commit_append_v2',
                          'guard_snapshot_head_advance_v2')
                      AND procedure.pronargs = 0
                ), runtime_candidates AS (
                    SELECT DISTINCT actual_acl.grantee
                    FROM actual_acl
                    CROSS JOIN owner_anchor
                    WHERE actual_acl.grantee <> owner_anchor.owner_oid
                      AND actual_acl.grantee <> 0
                ), expected_acl(
                    object_kind,
                    object_name,
                    column_name,
                    grantee,
                    privilege_type,
                    is_grantable) AS (
                    SELECT
                        'schema'::text,
                        'install_linking'::text,
                        NULL::text,
                        owner_anchor.owner_oid,
                        owner_privilege.privilege_type,
                        false
                    FROM owner_anchor
                    CROSS JOIN LATERAL unnest(
                        ARRAY['CREATE', 'USAGE']::text[])
                        AS owner_privilege(privilege_type)
                    UNION ALL
                    SELECT
                        'table'::text,
                        expected_tables.relation_name,
                        NULL::text,
                        owner_anchor.owner_oid,
                        owner_privilege.privilege_type,
                        false
                    FROM expected_tables
                    CROSS JOIN owner_anchor
                    CROSS JOIN LATERAL unnest(
                        ARRAY[
                            'DELETE',
                            'INSERT',
                            'MAINTAIN',
                            'REFERENCES',
                            'SELECT',
                            'TRIGGER',
                            'TRUNCATE',
                            'UPDATE']::text[])
                        AS owner_privilege(privilege_type)
                    UNION ALL
                    SELECT
                        'function'::text,
                        function_name.name,
                        NULL::text,
                        owner_anchor.owner_oid,
                        'EXECUTE'::text,
                        false
                    FROM owner_anchor
                    CROSS JOIN (
                        VALUES
                            ('guard_snapshot_commit_append_v2'),
                            ('guard_snapshot_head_advance_v2'))
                        AS function_name(name)
                    UNION ALL
                    SELECT
                        'schema'::text,
                        'install_linking'::text,
                        NULL::text,
                        runtime_candidates.grantee,
                        'USAGE'::text,
                        false
                    FROM runtime_candidates
                    UNION ALL
                    SELECT
                        'table'::text,
                        expected_tables.relation_name,
                        NULL::text,
                        runtime_candidates.grantee,
                        runtime_privilege.privilege_type,
                        false
                    FROM expected_tables
                    CROSS JOIN runtime_candidates
                    CROSS JOIN LATERAL unnest(
                        expected_tables.runtime_privileges)
                        AS runtime_privilege(privilege_type)
                )
                SELECT
                    (SELECT COUNT(*) FROM runtime_candidates) <= 1
                    AND NOT EXISTS (
                        SELECT * FROM expected_acl
                        EXCEPT ALL
                        SELECT * FROM actual_acl)
                    AND NOT EXISTS (
                        SELECT * FROM actual_acl
                        EXCEPT ALL
                        SELECT * FROM expected_acl)
                    AND NOT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_default_acl)
                """;
            if (!Convert.ToBoolean(
                    await accessControl.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_acl_invalid");
            }
        }

        await using (NpgsqlCommand columns = connection.CreateCommand())
        {
            columns.Transaction = transaction;
            columns.CommandText = """
                WITH expected(
                    table_name,
                    column_name,
                    ordinal_position,
                    udt_name,
                    is_nullable,
                    column_default,
                    is_identity,
                    is_generated) AS (
                    VALUES
                        ('schema_migrations', 'version', 1, 'int4', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('schema_migrations', 'name', 2, 'text', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('schema_migrations', 'checksum_sha256', 3, 'text', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('schema_migrations', 'applied_at_utc', 4, 'timestamptz', 'NO', 'clock_timestamp()', 'NO', 'NEVER'),
                        ('snapshot_commits', 'generation', 1, 'int8', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'commit_id', 2, 'uuid', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'parent_generation', 3, 'int8', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'parent_commit_id', 4, 'uuid', 'YES', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'parent_envelope_sha256', 5, 'bytea', 'YES', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'envelope_version', 6, 'int4', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'snapshot_sha256', 7, 'bytea', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'envelope_sha256', 8, 'bytea', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_commits', 'committed_at_utc', 9, 'timestamptz', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_head', 'singleton', 1, 'bool', 'NO', 'true', 'NO', 'NEVER'),
                        ('snapshot_head', 'generation', 2, 'int8', 'NO', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_head', 'commit_id', 3, 'uuid', 'YES', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_head', 'envelope_version', 4, 'int4', 'YES', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_head', 'snapshot_sha256', 5, 'bytea', 'YES', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_head', 'envelope_sha256', 6, 'bytea', 'YES', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_head', 'protected_envelope', 7, 'bytea', 'YES', NULL::text, 'NO', 'NEVER'),
                        ('snapshot_head', 'updated_at_utc', 8, 'timestamptz', 'NO', NULL::text, 'NO', 'NEVER')
                ), actual AS (
                    SELECT
                        table_name,
                        column_name,
                        ordinal_position,
                        udt_name,
                        is_nullable,
                        column_default,
                        is_identity,
                        is_generated
                    FROM information_schema.columns
                    WHERE table_schema = 'install_linking'
                      AND table_name IN (
                          'schema_migrations',
                          'snapshot_commits',
                          'snapshot_head')
                )
                SELECT NOT EXISTS (SELECT * FROM expected EXCEPT SELECT * FROM actual)
                   AND NOT EXISTS (SELECT * FROM actual EXCEPT SELECT * FROM expected)
                """;
            if (!Convert.ToBoolean(await columns.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_columns_invalid");
            }
        }

        await using (NpgsqlCommand constraints = connection.CreateCommand())
        {
            constraints.Transaction = transaction;
            constraints.CommandText = """
                WITH expected(
                    relation_name,
                    constraint_name,
                    constraint_type,
                    constrained_columns,
                    referenced_relation,
                    referenced_columns,
                    update_action,
                    delete_action,
                    match_type,
                    is_deferrable,
                    is_initially_deferred,
                    is_validated,
                    is_no_inherit,
                    nulls_not_distinct,
                    definition) AS (
                    VALUES
                        (
                            'schema_migrations',
                            'schema_migrations_pkey',
                            'p',
                            ARRAY[1]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            true,
                            false,
                            'PRIMARY KEY (version)'),
                        (
                            'schema_migrations',
                            'schema_migrations_name_key',
                            'u',
                            ARRAY[2]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            true,
                            false,
                            'UNIQUE (name)'),
                        (
                            'schema_migrations',
                            'schema_migrations_version_check',
                            'c',
                            ARRAY[1]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            false,
                            NULL::boolean,
                            'CHECK ((version > 0))'),
                        (
                            'schema_migrations',
                            'schema_migrations_name_check',
                            'c',
                            ARRAY[2]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            false,
                            NULL::boolean,
                            'CHECK (((char_length(name) >= 1) AND (char_length(name) <= 256)))'),
                        (
                            'schema_migrations',
                            'schema_migrations_checksum_sha256_check',
                            'c',
                            ARRAY[3]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            false,
                            NULL::boolean,
                            'CHECK ((checksum_sha256 ~ ''^[0-9a-f]{64}$''::text))'),
                        (
                            'snapshot_commits',
                            'pk_snapshot_commits_v2',
                            'p',
                            ARRAY[1]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            true,
                            false,
                            'PRIMARY KEY (generation)'),
                        (
                            'snapshot_commits',
                            'uq_snapshot_commits_commit_id_v2',
                            'u',
                            ARRAY[2]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            true,
                            false,
                            'UNIQUE (commit_id)'),
                        (
                            'snapshot_commits',
                            'ck_snapshot_commits_contract_v2',
                            'c',
                            ARRAY[1,2,3,6,7,8,4,5]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            false,
                            NULL::boolean,
                            'CHECK (((generation > 0) AND (commit_id <> ''00000000-0000-0000-0000-000000000000''::uuid) AND (parent_generation >= 0) AND (envelope_version = 2) AND (octet_length(snapshot_sha256) = 32) AND (octet_length(envelope_sha256) = 32) AND (generation = (parent_generation + 1)) AND (((parent_generation = 0) AND (parent_commit_id IS NULL) AND (parent_envelope_sha256 IS NULL)) OR ((parent_generation > 0) AND (parent_commit_id IS NOT NULL) AND (parent_envelope_sha256 IS NOT NULL) AND (octet_length(parent_envelope_sha256) = 32)))))'),
                        (
                            'snapshot_head',
                            'pk_snapshot_head_v2',
                            'p',
                            ARRAY[1]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            true,
                            false,
                            'PRIMARY KEY (singleton)'),
                        (
                            'snapshot_head',
                            'uq_snapshot_head_commit_id_v2',
                            'u',
                            ARRAY[3]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            true,
                            false,
                            'UNIQUE (commit_id)'),
                        (
                            'snapshot_head',
                            'fk_snapshot_head_commit_v2',
                            'f',
                            ARRAY[3]::smallint[],
                            'install_linking.snapshot_commits',
                            ARRAY[2]::smallint[],
                            'a',
                            'r',
                            's',
                            false,
                            false,
                            true,
                            true,
                            NULL::boolean,
                            NULL::text),
                        (
                            'snapshot_head',
                            'ck_snapshot_head_contract_v2',
                            'c',
                            ARRAY[1,2,3,4,5,6,7]::smallint[],
                            NULL::text,
                            NULL::smallint[],
                            NULL::text,
                            NULL::text,
                            NULL::text,
                            false,
                            false,
                            true,
                            false,
                            NULL::boolean,
                            'CHECK ((singleton AND (generation >= 0) AND (((generation = 0) AND (commit_id IS NULL) AND (envelope_version IS NULL) AND (snapshot_sha256 IS NULL) AND (envelope_sha256 IS NULL) AND (protected_envelope IS NULL)) OR ((generation > 0) AND (commit_id IS NOT NULL) AND (envelope_version = 2) AND (snapshot_sha256 IS NOT NULL) AND (octet_length(snapshot_sha256) = 32) AND (envelope_sha256 IS NOT NULL) AND (octet_length(envelope_sha256) = 32) AND (protected_envelope IS NOT NULL) AND ((octet_length(protected_envelope) >= 1) AND (octet_length(protected_envelope) <= 67108864))))))')
                ), actual AS (
                    SELECT
                           relation.relname::text,
                           constraint_record.conname::text,
                           constraint_record.contype::text,
                           constraint_record.conkey,
                           CASE
                               WHEN constraint_record.contype = 'f'
                               THEN referenced_namespace.nspname::text
                                   || '.'
                                   || referenced_relation.relname::text
                               ELSE NULL
                           END,
                           CASE
                               WHEN constraint_record.contype = 'f'
                               THEN constraint_record.confkey
                               ELSE NULL
                           END,
                           CASE
                               WHEN constraint_record.contype = 'f'
                               THEN constraint_record.confupdtype::text
                               ELSE NULL
                           END,
                           CASE
                               WHEN constraint_record.contype = 'f'
                               THEN constraint_record.confdeltype::text
                               ELSE NULL
                           END,
                           CASE
                               WHEN constraint_record.contype = 'f'
                               THEN constraint_record.confmatchtype::text
                               ELSE NULL
                           END,
                           constraint_record.condeferrable,
                           constraint_record.condeferred,
                           constraint_record.convalidated,
                           constraint_record.connoinherit,
                           CASE
                               WHEN constraint_record.contype IN ('p', 'u')
                               THEN constraint_index.indnullsnotdistinct
                               ELSE NULL
                           END,
                           CASE
                               WHEN constraint_record.contype = 'f'
                               THEN NULL
                               ELSE pg_catalog.pg_get_constraintdef(
                                   constraint_record.oid,
                                   false)
                           END
                    FROM pg_catalog.pg_constraint AS constraint_record
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = constraint_record.conrelid
                    LEFT JOIN pg_catalog.pg_class AS referenced_relation
                        ON referenced_relation.oid =
                            constraint_record.confrelid
                    LEFT JOIN pg_catalog.pg_namespace AS referenced_namespace
                        ON referenced_namespace.oid =
                            referenced_relation.relnamespace
                    LEFT JOIN pg_catalog.pg_index AS constraint_index
                        ON constraint_index.indexrelid =
                            constraint_record.conindid
                       AND constraint_record.contype IN ('p', 'u')
                    WHERE relation.relnamespace = 'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_commits',
                          'snapshot_head')
                )
                SELECT NOT EXISTS (SELECT * FROM expected EXCEPT SELECT * FROM actual)
                   AND NOT EXISTS (SELECT * FROM actual EXCEPT SELECT * FROM expected)
                """;
            if (!Convert.ToBoolean(await constraints.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_constraints_invalid");
            }
        }

        await using (NpgsqlCommand indexes = connection.CreateCommand())
        {
            indexes.Transaction = transaction;
            indexes.CommandText = """
                WITH expected(
                    relation_name,
                    index_name,
                    constraint_name,
                    constraint_type,
                    indexed_column,
                    column_number,
                    operator_class,
                    is_primary,
                    metadata_valid) AS (
                    VALUES
                        (
                            'schema_migrations',
                            'schema_migrations_pkey',
                            'schema_migrations_pkey',
                            'p',
                            'version',
                            1,
                            'int4_ops',
                            true,
                            true),
                        (
                            'schema_migrations',
                            'schema_migrations_name_key',
                            'schema_migrations_name_key',
                            'u',
                            'name',
                            2,
                            'text_ops',
                            false,
                            true),
                        (
                            'snapshot_commits',
                            'pk_snapshot_commits_v2',
                            'pk_snapshot_commits_v2',
                            'p',
                            'generation',
                            1,
                            'int8_ops',
                            true,
                            true),
                        (
                            'snapshot_commits',
                            'uq_snapshot_commits_commit_id_v2',
                            'uq_snapshot_commits_commit_id_v2',
                            'u',
                            'commit_id',
                            2,
                            'uuid_ops',
                            false,
                            true),
                        (
                            'snapshot_head',
                            'pk_snapshot_head_v2',
                            'pk_snapshot_head_v2',
                            'p',
                            'singleton',
                            1,
                            'bool_ops',
                            true,
                            true),
                        (
                            'snapshot_head',
                            'uq_snapshot_head_commit_id_v2',
                            'uq_snapshot_head_commit_id_v2',
                            'u',
                            'commit_id',
                            3,
                            'uuid_ops',
                            false,
                            true)
                ), actual AS (
                    SELECT
                        relation.relname::text,
                        index_relation.relname::text,
                        constraint_record.conname::text,
                        constraint_record.contype::text,
                        attribute.attname::text,
                        attribute.attnum::integer,
                        operator_class.opcname::text,
                        index_metadata.indisprimary,
                        (
                            index_relation.relkind = 'i'
                            AND index_relation.relpersistence = 'p'
                            AND index_relation.reltablespace = 0
                            AND index_relation.reloptions IS NULL
                            AND access_method.amname = 'btree'
                            AND index_metadata.indnatts = 1
                            AND index_metadata.indnkeyatts = 1
                            AND index_metadata.indisunique
                            AND NOT index_metadata.indisexclusion
                            AND index_metadata.indimmediate
                            AND index_metadata.indisvalid
                            AND index_metadata.indisready
                            AND index_metadata.indislive
                            AND NOT index_metadata.indcheckxmin
                            AND NOT index_metadata.indisclustered
                            AND NOT index_metadata.indisreplident
                            AND NOT index_metadata.indnullsnotdistinct
                            AND index_metadata.indexprs IS NULL
                            AND index_metadata.indpred IS NULL
                            AND index_metadata.indoption[0] = 0
                            AND index_metadata.indcollation[0] =
                                attribute.attcollation
                            AND operator_class_namespace.nspname =
                                'pg_catalog'
                            AND constraint_record.oid IS NOT NULL
                            AND constraint_record.conindid =
                                index_relation.oid
                            AND constraint_record.conrelid =
                                relation.oid
                        ) AS metadata_valid
                    FROM pg_catalog.pg_index AS index_metadata
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = index_metadata.indrelid
                    INNER JOIN pg_catalog.pg_class AS index_relation
                        ON index_relation.oid = index_metadata.indexrelid
                    INNER JOIN pg_catalog.pg_am AS access_method
                        ON access_method.oid = index_relation.relam
                    LEFT JOIN pg_catalog.pg_constraint AS constraint_record
                        ON constraint_record.conindid =
                            index_metadata.indexrelid
                       AND constraint_record.conrelid =
                            index_metadata.indrelid
                       AND constraint_record.contype IN ('p', 'u')
                    LEFT JOIN pg_catalog.pg_attribute AS attribute
                        ON attribute.attrelid = relation.oid
                       AND attribute.attnum = index_metadata.indkey[0]
                    LEFT JOIN pg_catalog.pg_opclass AS operator_class
                        ON operator_class.oid = index_metadata.indclass[0]
                    LEFT JOIN pg_catalog.pg_namespace
                        AS operator_class_namespace
                        ON operator_class_namespace.oid =
                            operator_class.opcnamespace
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_commits',
                          'snapshot_head')
                )
                SELECT
                    NOT EXISTS (
                        SELECT * FROM expected
                        EXCEPT ALL
                        SELECT * FROM actual)
                    AND NOT EXISTS (
                        SELECT * FROM actual
                        EXCEPT ALL
                        SELECT * FROM expected)
                """;
            if (!Convert.ToBoolean(
                    await indexes.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_indexes_invalid");
            }
        }

        await using (NpgsqlCommand rewriteRules = connection.CreateCommand())
        {
            rewriteRules.Transaction = transaction;
            rewriteRules.CommandText = """
                SELECT NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_rewrite AS rewrite_rule
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = rewrite_rule.ev_class
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits'))
                """;
            if (!Convert.ToBoolean(
                    await rewriteRules.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_rewrite_rules_invalid");
            }
        }

        await using (NpgsqlCommand inheritance = connection.CreateCommand())
        {
            inheritance.Transaction = transaction;
            inheritance.CommandText = """
                WITH authority_relations AS (
                    SELECT relation.oid
                    FROM pg_catalog.pg_class AS relation
                    WHERE relation.relnamespace =
                            'install_linking'::regnamespace
                      AND relation.relname IN (
                          'schema_migrations',
                          'snapshot_head',
                          'snapshot_commits')
                )
                SELECT NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_inherits AS inheritance_edge
                    WHERE inheritance_edge.inhrelid IN (
                              SELECT oid FROM authority_relations)
                       OR inheritance_edge.inhparent IN (
                              SELECT oid FROM authority_relations))
                """;
            if (!Convert.ToBoolean(
                    await inheritance.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_inheritance_invalid");
            }
        }

        await using (NpgsqlCommand functions = connection.CreateCommand())
        {
            functions.Transaction = transaction;
            functions.CommandText = """
                SELECT procedure.proname,
                       NOT procedure.prosecdef
                           AND procedure.provolatile = 'v'
                           AND procedure.prokind = 'f'
                           AND procedure.pronargs = 0
                           AND procedure.prorettype = 'trigger'::regtype
                           AND language.lanname = 'plpgsql'
                           AND procedure.proconfig =
                               ARRAY['search_path=pg_catalog, install_linking']::text[] AS metadata_valid,
                       procedure.prosrc
                FROM pg_catalog.pg_proc AS procedure
                INNER JOIN pg_catalog.pg_language AS language
                    ON language.oid = procedure.prolang
                WHERE procedure.pronamespace = 'install_linking'::regnamespace
                ORDER BY procedure.proname
                """;
            var actualFunctions = new Dictionary<string, (bool MetadataValid, string Body)>(
                StringComparer.Ordinal);
            bool duplicateFunctionName = false;
            await using NpgsqlDataReader reader =
                await functions.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                duplicateFunctionName |= !actualFunctions.TryAdd(
                    reader.GetString(0),
                    (reader.GetBoolean(1), reader.GetString(2)));
            }

            bool functionsValid = !duplicateFunctionName
                && actualFunctions.Count == 2
                && actualFunctions.TryGetValue(
                    "guard_snapshot_commit_append_v2",
                    out (bool MetadataValid, string Body) commitGuard)
                && commitGuard.MetadataValid
                && string.Equals(
                    NormalizeFunctionBody(commitGuard.Body),
                    NormalizeFunctionBody(CommitGuardBody),
                    StringComparison.Ordinal)
                && actualFunctions.TryGetValue(
                    "guard_snapshot_head_advance_v2",
                    out (bool MetadataValid, string Body) headGuard)
                && headGuard.MetadataValid
                && string.Equals(
                    NormalizeFunctionBody(headGuard.Body),
                    NormalizeFunctionBody(HeadGuardBody),
                    StringComparison.Ordinal);
            if (!functionsValid)
            {
                problems.Add("authority_functions_invalid");
            }
        }

        await using (NpgsqlCommand triggers = connection.CreateCommand())
        {
            triggers.Transaction = transaction;
            triggers.CommandText = """
                WITH expected(
                    relation_name,
                    trigger_name,
                    function_schema,
                    function_name,
                    trigger_type,
                    enabled,
                    internal,
                    unconditional,
                    argument_bytes,
                    old_transition_table,
                    new_transition_table,
                    constraint_oid,
                    is_deferrable,
                    is_initially_deferred) AS (
                    VALUES
                        (
                            'snapshot_commits',
                            'snapshot_commit_monotonic_append_v2',
                            'install_linking',
                            'guard_snapshot_commit_append_v2',
                            7,
                            'A',
                            false,
                            true,
                            0,
                            NULL::text,
                            NULL::text,
                            0::oid,
                            false,
                            false),
                        (
                            'snapshot_head',
                            'snapshot_head_monotonic_advance_v2',
                            'install_linking',
                            'guard_snapshot_head_advance_v2',
                            19,
                            'A',
                            false,
                            true,
                            0,
                            NULL::text,
                            NULL::text,
                            0::oid,
                            false,
                            false)
                ), actual AS (
                    SELECT
                           relation.relname::text,
                           trigger_record.tgname::text,
                           function_namespace.nspname::text,
                           procedure.proname::text,
                           trigger_record.tgtype::integer,
                           trigger_record.tgenabled::text,
                           trigger_record.tgisinternal,
                           trigger_record.tgqual IS NULL,
                           octet_length(trigger_record.tgargs),
                           trigger_record.tgoldtable::text,
                           trigger_record.tgnewtable::text,
                           trigger_record.tgconstraint,
                           trigger_record.tgdeferrable,
                           trigger_record.tginitdeferred
                    FROM pg_catalog.pg_trigger AS trigger_record
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = trigger_record.tgrelid
                    INNER JOIN pg_catalog.pg_proc AS procedure
                        ON procedure.oid = trigger_record.tgfoid
                    INNER JOIN pg_catalog.pg_namespace AS function_namespace
                        ON function_namespace.oid = procedure.pronamespace
                    WHERE relation.relnamespace = 'install_linking'::regnamespace
                      AND relation.relname IN ('snapshot_commits', 'snapshot_head')
                      AND NOT trigger_record.tgisinternal
                )
                SELECT NOT EXISTS (SELECT * FROM expected EXCEPT SELECT * FROM actual)
                   AND NOT EXISTS (SELECT * FROM actual EXCEPT SELECT * FROM expected)
                """;
            if (!Convert.ToBoolean(await triggers.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_triggers_invalid");
            }
        }

        await using (NpgsqlCommand chain = connection.CreateCommand())
        {
            chain.Transaction = transaction;
            chain.CommandText = """
                WITH ordered AS (
                    SELECT commit_record.*,
                           row_number() OVER (ORDER BY generation) AS sequence_number,
                           lag(commit_id) OVER (ORDER BY generation) AS previous_commit_id,
                           lag(envelope_sha256) OVER (ORDER BY generation) AS previous_envelope_sha256
                    FROM install_linking.snapshot_commits AS commit_record
                ), aggregate_chain AS (
                    SELECT COUNT(*)::bigint AS commit_count,
                           COALESCE(bool_and(generation = sequence_number), true) AS generations_contiguous,
                           COALESCE(bool_and(
                               (generation = 1
                                   AND parent_generation = 0
                                   AND parent_commit_id IS NULL
                                   AND parent_envelope_sha256 IS NULL)
                               OR
                               (generation > 1
                                   AND parent_generation = generation - 1
                                   AND parent_commit_id = previous_commit_id
                                   AND parent_envelope_sha256 = previous_envelope_sha256)), true) AS parents_contiguous
                    FROM ordered
                )
                SELECT CASE
                    WHEN head.generation = 0 THEN
                        aggregate_chain.commit_count = 0
                    ELSE
                        aggregate_chain.commit_count = head.generation
                        AND aggregate_chain.generations_contiguous
                        AND aggregate_chain.parents_contiguous
                        AND current_commit.generation = head.generation
                        AND current_commit.commit_id = head.commit_id
                        AND current_commit.envelope_version = head.envelope_version
                        AND current_commit.snapshot_sha256 = head.snapshot_sha256
                        AND current_commit.envelope_sha256 = head.envelope_sha256
                    END
                FROM install_linking.snapshot_head AS head
                CROSS JOIN aggregate_chain
                LEFT JOIN install_linking.snapshot_commits AS current_commit
                    ON current_commit.commit_id = head.commit_id
                WHERE head.singleton = true
                """;
            if (!Convert.ToBoolean(await chain.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_chain_invalid");
            }
        }
    }

    private static async Task BootstrapAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            CREATE SCHEMA IF NOT EXISTS install_linking;
            REVOKE ALL ON SCHEMA install_linking FROM PUBLIC;
            CREATE TABLE IF NOT EXISTS install_linking.schema_migrations (
                version integer PRIMARY KEY CHECK (version > 0),
                name text NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 256),
                checksum_sha256 text NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
                applied_at_utc timestamptz NOT NULL DEFAULT clock_timestamp()
            );
            REVOKE ALL ON install_linking.schema_migrations FROM PUBLIC;
            """;
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task ApplyMigrationAsync(
        NpgsqlConnection connection,
        InstallLinkingPostgresMigration migration,
        CancellationToken cancellationToken)
    {
        await using NpgsqlTransaction transaction =
            await connection.BeginTransactionAsync(cancellationToken);
        await using NpgsqlCommand read = connection.CreateCommand();
        read.Transaction = transaction;
        read.CommandText = """
            SELECT checksum_sha256
            FROM install_linking.schema_migrations
            WHERE version = @version
            """;
        read.Parameters.AddWithValue("version", migration.Version);
        object? existing = await read.ExecuteScalarAsync(cancellationToken);
        if (existing is string checksum)
        {
            if (!string.Equals(
                    checksum,
                    migration.ChecksumSha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"InstallLinking migration {migration.Version} checksum does not match the applied migration.");
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
            INSERT INTO install_linking.schema_migrations(
                version, name, checksum_sha256)
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

    [GeneratedRegex("\\s+", RegexOptions.CultureInvariant)]
    private static partial Regex FunctionWhitespacePattern();

    private static string NormalizeFunctionBody(string body)
        => FunctionWhitespacePattern().Replace(body.Trim(), " ");
}
