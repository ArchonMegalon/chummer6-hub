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
        var problems = new List<string>();
        int appliedVersion = 0;
        try
        {
            await using NpgsqlConnection connection =
                await _dataSource.OpenConnectionAsync(cancellationToken);
            await using NpgsqlCommand exists = connection.CreateCommand();
            exists.CommandText =
                "SELECT to_regclass('install_linking.schema_migrations') IS NOT NULL";
            if (!Convert.ToBoolean(await exists.ExecuteScalarAsync(cancellationToken)))
            {
                return new(false, 0, ["schema_migrations_missing"]);
            }

            await using (NpgsqlCommand appliedCommand = connection.CreateCommand())
            {
                appliedCommand.CommandText = """
                    SELECT version, checksum_sha256
                    FROM install_linking.schema_migrations
                    ORDER BY version
                    """;
                var applied = new Dictionary<int, string>();
                await using NpgsqlDataReader reader =
                    await appliedCommand.ExecuteReaderAsync(cancellationToken);
                while (await reader.ReadAsync(cancellationToken))
                {
                    int version = reader.GetInt32(0);
                    applied[version] = reader.GetString(1);
                    appliedVersion = Math.Max(appliedVersion, version);
                }

                foreach (InstallLinkingPostgresMigration migration in _migrations)
                {
                    if (!applied.TryGetValue(migration.Version, out string? checksum))
                    {
                        problems.Add($"migration_{migration.Version}_missing");
                    }
                    else if (!string.Equals(
                                 checksum,
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
                await using NpgsqlCommand head = connection.CreateCommand();
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
                    problems,
                    cancellationToken);
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
            GRANT SELECT ON install_linking.schema_migrations TO {quotedRole};
            GRANT SELECT, UPDATE ON install_linking.snapshot_head TO {quotedRole};
            GRANT SELECT, INSERT ON install_linking.snapshot_commits TO {quotedRole};

            REVOKE CREATE ON SCHEMA install_linking FROM {quotedRole};
            REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
                ON ALL TABLES IN SCHEMA install_linking FROM {quotedRole};
            REVOKE INSERT, DELETE, TRUNCATE, REFERENCES, TRIGGER
                ON install_linking.snapshot_head FROM {quotedRole};
            REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
                ON install_linking.snapshot_commits FROM {quotedRole};
            REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
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
        await using NpgsqlCommand identity = connection.CreateCommand();
        identity.CommandText = "SELECT current_user";
        string runtimeRole = Convert.ToString(
                await identity.ExecuteScalarAsync(cancellationToken),
                System.Globalization.CultureInfo.InvariantCulture)
            ?? string.Empty;
        return RuntimeRolePattern().IsMatch(runtimeRole)
            && await ValidateRuntimePrivilegesOnConnectionAsync(
                connection,
                runtimeRole,
                cancellationToken);
    }

    private static async Task<bool> ValidateRuntimePrivilegesOnConnectionAsync(
        NpgsqlConnection connection,
        string runtimeRole,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
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
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    INNER JOIN pg_catalog.pg_roles AS member
                        ON member.oid = membership.member
                    WHERE member.rolname = @role)
                AND has_schema_privilege(@role, 'install_linking', 'USAGE')
                AND NOT has_schema_privilege(@role, 'install_linking', 'CREATE')
                AND has_table_privilege(@role, 'install_linking.schema_migrations', 'SELECT')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'INSERT')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'UPDATE')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'DELETE')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'TRUNCATE')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'REFERENCES')
                AND NOT has_table_privilege(@role, 'install_linking.schema_migrations', 'TRIGGER')
                AND has_table_privilege(@role, 'install_linking.snapshot_head', 'SELECT')
                AND has_table_privilege(@role, 'install_linking.snapshot_head', 'UPDATE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'INSERT')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'DELETE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'TRUNCATE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'REFERENCES')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_head', 'TRIGGER')
                AND has_table_privilege(@role, 'install_linking.snapshot_commits', 'SELECT')
                AND has_table_privilege(@role, 'install_linking.snapshot_commits', 'INSERT')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'UPDATE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'DELETE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'TRUNCATE')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'REFERENCES')
                AND NOT has_table_privilege(@role, 'install_linking.snapshot_commits', 'TRIGGER')
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_proc AS procedure
                    WHERE procedure.pronamespace = 'install_linking'::regnamespace
                      AND has_function_privilege(@role, procedure.oid, 'EXECUTE'))
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
                          OR has_table_privilege(@role, relation.oid, 'TRIGGER')))
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
            """;
        command.Parameters.AddWithValue("role", runtimeRole);
        return Convert.ToBoolean(
            await command.ExecuteScalarAsync(cancellationToken));
    }

    private static async Task ValidateLiveAuthorityContractAsync(
        NpgsqlConnection connection,
        ICollection<string> problems,
        CancellationToken cancellationToken)
    {
        await using (NpgsqlCommand version = connection.CreateCommand())
        {
            version.CommandText =
                "SELECT current_setting('server_version_num')::integer / 10000 = @major";
            version.Parameters.AddWithValue("major", RequiredPostgresMajorVersion);
            if (!Convert.ToBoolean(await version.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("postgres_major_version_invalid");
            }
        }

        await using (NpgsqlCommand columns = connection.CreateCommand())
        {
            columns.CommandText = """
                WITH expected(table_name, column_name, ordinal_position, udt_name, is_nullable) AS (
                    VALUES
                        ('snapshot_commits', 'generation', 1, 'int8', 'NO'),
                        ('snapshot_commits', 'commit_id', 2, 'uuid', 'NO'),
                        ('snapshot_commits', 'parent_generation', 3, 'int8', 'NO'),
                        ('snapshot_commits', 'parent_commit_id', 4, 'uuid', 'YES'),
                        ('snapshot_commits', 'parent_envelope_sha256', 5, 'bytea', 'YES'),
                        ('snapshot_commits', 'envelope_version', 6, 'int4', 'NO'),
                        ('snapshot_commits', 'snapshot_sha256', 7, 'bytea', 'NO'),
                        ('snapshot_commits', 'envelope_sha256', 8, 'bytea', 'NO'),
                        ('snapshot_commits', 'committed_at_utc', 9, 'timestamptz', 'NO'),
                        ('snapshot_head', 'singleton', 1, 'bool', 'NO'),
                        ('snapshot_head', 'generation', 2, 'int8', 'NO'),
                        ('snapshot_head', 'commit_id', 3, 'uuid', 'YES'),
                        ('snapshot_head', 'envelope_version', 4, 'int4', 'YES'),
                        ('snapshot_head', 'snapshot_sha256', 5, 'bytea', 'YES'),
                        ('snapshot_head', 'envelope_sha256', 6, 'bytea', 'YES'),
                        ('snapshot_head', 'protected_envelope', 7, 'bytea', 'YES'),
                        ('snapshot_head', 'updated_at_utc', 8, 'timestamptz', 'NO')
                ), actual AS (
                    SELECT table_name, column_name, ordinal_position, udt_name, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'install_linking'
                      AND table_name IN ('snapshot_commits', 'snapshot_head')
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
            constraints.CommandText = """
                WITH expected(relation_name, constraint_name, constraint_type) AS (
                    VALUES
                        ('snapshot_commits', 'pk_snapshot_commits_v2', 'p'),
                        ('snapshot_commits', 'uq_snapshot_commits_commit_id_v2', 'u'),
                        ('snapshot_commits', 'ck_snapshot_commits_contract_v2', 'c'),
                        ('snapshot_head', 'pk_snapshot_head_v2', 'p'),
                        ('snapshot_head', 'uq_snapshot_head_commit_id_v2', 'u'),
                        ('snapshot_head', 'fk_snapshot_head_commit_v2', 'f'),
                        ('snapshot_head', 'ck_snapshot_head_contract_v2', 'c')
                ), actual AS (
                    SELECT relation.relname::text,
                           constraint_record.conname::text,
                           constraint_record.contype::text
                    FROM pg_catalog.pg_constraint AS constraint_record
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = constraint_record.conrelid
                    WHERE relation.relnamespace = 'install_linking'::regnamespace
                      AND relation.relname IN ('snapshot_commits', 'snapshot_head')
                      AND constraint_record.convalidated
                )
                SELECT NOT EXISTS (SELECT * FROM expected EXCEPT SELECT * FROM actual)
                   AND NOT EXISTS (SELECT * FROM actual EXCEPT SELECT * FROM expected)
                """;
            if (!Convert.ToBoolean(await constraints.ExecuteScalarAsync(cancellationToken)))
            {
                problems.Add("authority_constraints_invalid");
            }
        }

        await using (NpgsqlCommand functions = connection.CreateCommand())
        {
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
            triggers.CommandText = """
                WITH expected(relation_name, trigger_name, function_name, trigger_type) AS (
                    VALUES
                        ('snapshot_commits', 'snapshot_commit_monotonic_append_v2', 'guard_snapshot_commit_append_v2', 7),
                        ('snapshot_head', 'snapshot_head_monotonic_advance_v2', 'guard_snapshot_head_advance_v2', 19)
                ), actual AS (
                    SELECT relation.relname::text,
                           trigger_record.tgname::text,
                           procedure.proname::text,
                           trigger_record.tgtype::integer
                    FROM pg_catalog.pg_trigger AS trigger_record
                    INNER JOIN pg_catalog.pg_class AS relation
                        ON relation.oid = trigger_record.tgrelid
                    INNER JOIN pg_catalog.pg_proc AS procedure
                        ON procedure.oid = trigger_record.tgfoid
                    WHERE relation.relnamespace = 'install_linking'::regnamespace
                      AND relation.relname IN ('snapshot_commits', 'snapshot_head')
                      AND NOT trigger_record.tgisinternal
                      AND trigger_record.tgenabled IN ('O', 'A')
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
