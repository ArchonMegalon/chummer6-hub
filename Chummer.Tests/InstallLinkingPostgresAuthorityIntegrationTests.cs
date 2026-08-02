using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Npgsql;
using Testcontainers.PostgreSql;
using Xunit;

namespace Chummer.Tests;

[Trait("Category", "PostgreSQLIntegration")]
public sealed class InstallLinkingPostgresAuthorityIntegrationTests :
    IClassFixture<InstallLinkingPostgresAuthorityFixture>
{
    private readonly InstallLinkingPostgresAuthorityFixture _fixture;

    public InstallLinkingPostgresAuthorityIntegrationTests(
        InstallLinkingPostgresAuthorityFixture fixture)
    {
        _fixture = fixture;
    }

    [Fact]
    public async Task Migrations_head_and_monotonic_trigger_validate()
    {
        await _fixture.ResetAsync();
        var migrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);

        InstallLinkingPostgresSchemaValidation validation =
            await migrator.ValidateAsync();
        Assert.True(
            validation.Valid,
            string.Join(',', validation.Problems));
        Assert.Equal(
            InstallLinkingPostgresSchema.CurrentVersion,
            validation.AppliedVersion);

        await using NpgsqlConnection connection =
            await _fixture.AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand skip = connection.CreateCommand();
        skip.CommandText = """
            UPDATE install_linking.snapshot_head
            SET generation = 2,
                updated_at_utc = clock_timestamp()
            WHERE singleton = true
            """;
        PostgresException rejected = await Assert.ThrowsAsync<PostgresException>(
            () => skip.ExecuteNonQueryAsync());
        Assert.Equal("23514", rejected.SqlState);
    }

    [Fact]
    public async Task Admin_or_migrator_identity_is_rejected_as_a_runtime_authority()
    {
        await _fixture.ResetAsync();
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(
            _fixture.AdminDataSource);

        InstallLinkingPostgresReadiness readiness =
            await authority.CheckReadinessAsync();

        Assert.False(readiness.Ready);
        Assert.Equal("runtime_privileges_invalid", readiness.Code);
    }

    [Fact]
    public async Task Runtime_identity_with_one_extra_effective_privilege_is_rejected()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var migrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await migrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync(
                $"GRANT DELETE ON install_linking.snapshot_commits TO {QuoteIdentifier(role)}");

            var builder = new NpgsqlConnectionStringBuilder(
                _fixture.ConnectionString)
            {
                Username = role,
                Password = password,
                Pooling = false
            };
            await using NpgsqlDataSource runtimeDataSource =
                NpgsqlDataSource.Create(builder.ConnectionString);
            var authority = new NpgsqlInstallLinkingSnapshotAuthority(
                runtimeDataSource);

            InstallLinkingPostgresReadiness readiness =
                await authority.CheckReadinessAsync();

            Assert.False(readiness.Ready);
            Assert.Equal("schema_invalid", readiness.Code);
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Runtime_credential_proves_exact_role_and_pristine_generation_zero()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            var builder = new NpgsqlConnectionStringBuilder(
                _fixture.ConnectionString)
            {
                Username = role,
                Password = password,
                Pooling = false
            };
            await using NpgsqlDataSource runtimeDataSource =
                NpgsqlDataSource.Create(builder.ConnectionString);
            var runtimeMigrator = new InstallLinkingPostgresMigrator(
                runtimeDataSource);

            InstallLinkingPostgresRuntimeRoleProof roleProof =
                await runtimeMigrator.ProveCurrentRuntimeRoleAsync(role);
            InstallLinkingPostgresEmptyAuthorityProof emptyProof =
                await runtimeMigrator.ProveEmptyRuntimeAuthorityAsync(role);
            InstallLinkingPostgresAuthorityReadyProof readyProof =
                await runtimeMigrator.ProveRuntimeAuthorityReadyAsync(role);
            await using NpgsqlConnection adminConnection =
                await _fixture.AdminDataSource.OpenConnectionAsync();
            string adminAuthorityIdentitySha256 =
                await InstallLinkingPostgresAuthorityIdentity
                    .ComputeSha256Async(adminConnection);

            Assert.True(roleProof.Valid, roleProof.Code);
            Assert.True(roleProof.CurrentRoleMatches);
            Assert.True(roleProof.LeastPrivilegeValid);
            Assert.True(emptyProof.Valid, emptyProof.Code);
            Assert.True(emptyProof.SchemaValid);
            Assert.Equal(
                InstallLinkingPostgresSchema.CurrentVersion,
                emptyProof.AppliedSchemaVersion);
            Assert.Equal(0, emptyProof.HeadGeneration);
            Assert.Equal(0, emptyProof.CommitCount);
            Assert.True(emptyProof.Empty);
            Assert.True(readyProof.Valid, readyProof.Code);
            Assert.True(readyProof.Empty);
            Assert.Equal(0, readyProof.HeadGeneration);
            Assert.Equal(0, readyProof.CommitCount);
            Assert.Matches("^[0-9a-f]{64}$", readyProof.AuthorityStateSha256);
            Assert.Equal(
                adminAuthorityIdentitySha256,
                roleProof.AuthorityIdentitySha256);
            Assert.Equal(
                adminAuthorityIdentitySha256,
                emptyProof.AuthorityIdentitySha256);
            Assert.Matches(
                "^[0-9a-f]{64}$",
                roleProof.AuthorityIdentitySha256);

            InstallLinkingPostgresRuntimeRoleProof wrongRole =
                await runtimeMigrator.ProveCurrentRuntimeRoleAsync(
                    $"{role}_other");
            Assert.False(wrongRole.Valid);
            Assert.False(wrongRole.CurrentRoleMatches);
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Readiness_rejects_valid_credentials_for_a_different_expected_runtime_role()
    {
        await _fixture.ResetAsync();
        string expectedRole = $"install_link_runtime_{Guid.NewGuid():N}";
        string connectedRole = $"install_link_runtime_{Guid.NewGuid():N}";
        string expectedPassword =
            Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        string connectedPassword =
            Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(expectedRole, expectedPassword);
        await _fixture.CreateLoginRoleAsync(connectedRole, connectedPassword);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(expectedRole);
            await using (NpgsqlDataSource expectedDataSource =
                         CreateRuntimeDataSource(
                             expectedRole,
                             expectedPassword))
            {
                Assert.True(
                    (await new InstallLinkingPostgresMigrator(
                            expectedDataSource)
                        .ProveCurrentRuntimeRoleAsync(expectedRole)).Valid);
            }

            string quotedExpectedRole = QuoteIdentifier(expectedRole);
            await _fixture.ExecuteAdminAsync($"""
                REVOKE ALL ON SCHEMA install_linking
                    FROM {quotedExpectedRole};
                REVOKE ALL ON ALL TABLES IN SCHEMA install_linking
                    FROM {quotedExpectedRole};
                REVOKE ALL ON ALL FUNCTIONS IN SCHEMA install_linking
                    FROM {quotedExpectedRole};
                """);
            await adminMigrator.GrantRuntimePrivilegesAsync(connectedRole);
            await using NpgsqlDataSource connectedDataSource =
                CreateRuntimeDataSource(
                    connectedRole,
                    connectedPassword);
            Assert.True(
                (await new InstallLinkingPostgresMigrator(connectedDataSource)
                    .ProveCurrentRuntimeRoleAsync(connectedRole)).Valid);
            var authority = new NpgsqlInstallLinkingSnapshotAuthority(
                connectedDataSource,
                expectedRuntimeRole: expectedRole);

            InstallLinkingPostgresReadiness readiness =
                await authority.CheckReadinessAsync();

            Assert.False(readiness.Ready);
            Assert.Equal("runtime_privileges_invalid", readiness.Code);
        }
        finally
        {
            await _fixture.DropRoleAsync(expectedRole);
            await _fixture.DropRoleAsync(connectedRole);
        }
    }

    [Fact]
    public async Task Runtime_empty_proof_rejects_populated_authority_without_writing()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            var builder = new NpgsqlConnectionStringBuilder(
                _fixture.ConnectionString)
            {
                Username = role,
                Password = password,
                Pooling = false
            };
            await using NpgsqlDataSource runtimeDataSource =
                NpgsqlDataSource.Create(builder.ConnectionString);
            var runtimeAuthority = new NpgsqlInstallLinkingSnapshotAuthority(
                runtimeDataSource);
            using InstallLinkingEnvelopeCompareExchangeResult committed =
                await runtimeAuthority.CompareExchangeAsync(
                    RequestForEmptyHead("runtime-empty-proof-populated"));
            Assert.True(committed.Committed, committed.Code);
            byte[] headBefore = await _fixture.ScalarBytesAsync(
                "SELECT envelope_sha256 FROM install_linking.snapshot_head WHERE singleton = true");

            InstallLinkingPostgresEmptyAuthorityProof proof =
                await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveEmptyRuntimeAuthorityAsync(role);
            InstallLinkingPostgresAuthorityReadyProof readyProof =
                await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveRuntimeAuthorityReadyAsync(role);

            Assert.False(proof.Valid);
            Assert.Equal("authority_nonempty", proof.Code);
            Assert.Equal(1, proof.HeadGeneration);
            Assert.Equal(1, proof.CommitCount);
            Assert.False(proof.Empty);
            Assert.True(readyProof.Valid, readyProof.Code);
            Assert.False(readyProof.Empty);
            Assert.Equal(1, readyProof.HeadGeneration);
            Assert.Equal(1, readyProof.CommitCount);
            Assert.Matches("^[0-9a-f]{64}$", readyProof.AuthorityStateSha256);
            Assert.Equal(
                headBefore,
                await _fixture.ScalarBytesAsync(
                    "SELECT envelope_sha256 FROM install_linking.snapshot_head WHERE singleton = true"));
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public Task Runtime_role_proof_rejects_column_update_grant()
        => AssertRuntimeRoleProofRejectsAsync(
            static quotedRole =>
                $"GRANT UPDATE (committed_at_utc) ON install_linking.snapshot_commits TO {quotedRole}");

    [Fact]
    public Task Runtime_role_proof_rejects_column_insert_grant()
        => AssertRuntimeRoleProofRejectsAsync(
            static quotedRole =>
                $"GRANT INSERT (version) ON install_linking.schema_migrations TO {quotedRole}");

    [Fact]
    public Task Runtime_role_proof_rejects_column_references_grant()
        => AssertRuntimeRoleProofRejectsAsync(
            static quotedRole =>
                $"GRANT REFERENCES (generation) ON install_linking.snapshot_commits TO {quotedRole}");

    [Fact]
    public Task Runtime_role_proof_rejects_column_select_grant_option()
        => AssertRuntimeRoleProofRejectsAsync(
            static quotedRole =>
                $"GRANT SELECT (version) ON install_linking.schema_migrations TO {quotedRole} WITH GRANT OPTION");

    [Fact]
    public Task Runtime_role_proof_rejects_maintain()
        => AssertRuntimeRoleProofRejectsAsync(
            static quotedRole =>
                $"GRANT MAINTAIN ON install_linking.snapshot_head TO {quotedRole}");

    [Fact]
    public async Task Grant_runtime_removes_existing_column_ACL_entries()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync(
                "GRANT UPDATE (committed_at_utc) "
                + "ON install_linking.snapshot_commits TO "
                + QuoteIdentifier(role));
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);

            InstallLinkingPostgresRuntimeRoleProof proof =
                await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveCurrentRuntimeRoleAsync(role);

            Assert.True(proof.Valid, proof.Code);
            Assert.True(proof.LeastPrivilegeValid);
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Runtime_role_proof_rejects_database_create()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        string quotedRole = QuoteIdentifier(role);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync(
                $"GRANT CREATE ON DATABASE chummer_install_linking TO {quotedRole}");

            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);
            Assert.False(
                (await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveCurrentRuntimeRoleAsync(role)).Valid);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(
                $"REVOKE CREATE ON DATABASE chummer_install_linking FROM {quotedRole}");
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Runtime_role_proof_rejects_database_ownership()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        string quotedRole = QuoteIdentifier(role);
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync(
                $"ALTER DATABASE chummer_install_linking OWNER TO {quotedRole}");
            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);

            Assert.False(
                (await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveCurrentRuntimeRoleAsync(role)).Valid);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(
                "ALTER DATABASE chummer_install_linking OWNER TO postgres");
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Runtime_role_proof_rejects_schema_ownership()
    {
        await AssertRuntimeOwnershipRejectedAsync(
            static quotedRole =>
                $"ALTER SCHEMA install_linking OWNER TO {quotedRole}",
            "ALTER SCHEMA install_linking OWNER TO postgres");
    }

    [Fact]
    public async Task Runtime_role_proof_rejects_table_ownership()
    {
        await AssertRuntimeOwnershipRejectedAsync(
            static quotedRole =>
                $"ALTER TABLE install_linking.snapshot_head OWNER TO {quotedRole}",
            "ALTER TABLE install_linking.snapshot_head OWNER TO postgres");
    }

    [Fact]
    public async Task Runtime_role_proof_rejects_function_ownership()
    {
        await AssertRuntimeOwnershipRejectedAsync(
            static quotedRole =>
                "ALTER FUNCTION install_linking.guard_snapshot_head_advance_v2() "
                + $"OWNER TO {quotedRole}",
            "ALTER FUNCTION install_linking.guard_snapshot_head_advance_v2() "
            + "OWNER TO postgres");
    }

    [Fact]
    public async Task Runtime_role_proof_rejects_membership_in_function_owner()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string ownerRole = $"install_link_owner_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        string quotedRole = QuoteIdentifier(role);
        string quotedOwnerRole = QuoteIdentifier(ownerRole);
        await _fixture.CreateLoginRoleAsync(role, password);
        await _fixture.ExecuteAdminAsync($"CREATE ROLE {quotedOwnerRole}");
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync(
                "ALTER FUNCTION install_linking.guard_snapshot_head_advance_v2() "
                + $"OWNER TO {quotedOwnerRole}; "
                + $"GRANT {quotedOwnerRole} TO {quotedRole}");
            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);

            Assert.False(
                (await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveCurrentRuntimeRoleAsync(role)).Valid);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(
                $"REVOKE {quotedOwnerRole} FROM {quotedRole}; "
                + "ALTER FUNCTION install_linking.guard_snapshot_head_advance_v2() "
                + "OWNER TO postgres");
            await _fixture.DropRoleAsync(role);
            await _fixture.DropRoleAsync(ownerRole);
        }
    }

    [Fact]
    public async Task Replaced_no_op_guard_function_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            CREATE OR REPLACE FUNCTION install_linking.guard_snapshot_head_advance_v2()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY INVOKER
            SET search_path = pg_catalog, install_linking
            AS $guard$
            BEGIN
                RETURN NEW;
            END;
            $guard$;
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_functions_invalid", validation.Problems);
    }

    [Fact]
    public async Task Dropped_consolidated_constraint_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.snapshot_head
            DROP CONSTRAINT ck_snapshot_head_contract_v2
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_constraints_invalid", validation.Problems);
    }

    [Fact]
    public async Task Same_named_no_op_check_constraint_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.snapshot_head
                DROP CONSTRAINT ck_snapshot_head_contract_v2;
            ALTER TABLE install_linking.snapshot_head
                ADD CONSTRAINT ck_snapshot_head_contract_v2 CHECK (true);
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_constraints_invalid", validation.Problems);
    }

    [Fact]
    public async Task Same_named_foreign_key_with_cascade_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.snapshot_head
                DROP CONSTRAINT fk_snapshot_head_commit_v2;
            ALTER TABLE install_linking.snapshot_head
                ADD CONSTRAINT fk_snapshot_head_commit_v2
                FOREIGN KEY (commit_id)
                REFERENCES install_linking.snapshot_commits(commit_id)
                ON DELETE CASCADE;
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_constraints_invalid", validation.Problems);
    }

    [Fact]
    public async Task Same_named_unique_constraint_on_wrong_key_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.snapshot_head
                DROP CONSTRAINT uq_snapshot_head_commit_id_v2;
            ALTER TABLE install_linking.snapshot_head
                ADD CONSTRAINT uq_snapshot_head_commit_id_v2
                UNIQUE (generation);
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_constraints_invalid", validation.Problems);
    }

    [Fact]
    public async Task Trigger_with_false_when_clause_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            DROP TRIGGER snapshot_head_monotonic_advance_v2
                ON install_linking.snapshot_head;
            CREATE TRIGGER snapshot_head_monotonic_advance_v2
            BEFORE UPDATE ON install_linking.snapshot_head
            FOR EACH ROW
            WHEN (false)
            EXECUTE FUNCTION install_linking.guard_snapshot_head_advance_v2();
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_triggers_invalid", validation.Problems);
    }

    [Fact]
    public async Task Origin_only_trigger_fails_exact_trigger_posture_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.snapshot_head
                ENABLE TRIGGER snapshot_head_monotonic_advance_v2
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_triggers_invalid", validation.Problems);
    }

    [Fact]
    public Task Dml_rewrite_rule_fails_live_schema_attestation()
        => AssertLiveSchemaProblemAsync(
            """
            CREATE RULE unexpected_snapshot_head_update AS
            ON UPDATE TO install_linking.snapshot_head
            DO INSTEAD NOTHING
            """,
            "authority_rewrite_rules_invalid");

    [Fact]
    public Task Inheritance_edge_fails_live_schema_attestation()
        => AssertLiveSchemaProblemAsync(
            """
            CREATE TABLE install_linking.unexpected_snapshot_head_child ()
            INHERITS (install_linking.snapshot_head)
            """,
            "authority_inheritance_invalid");

    [Fact]
    public Task Partition_edge_fails_live_schema_attestation()
        => AssertLiveSchemaProblemAsync(
            """
            CREATE TABLE install_linking.unexpected_head_parent (
                singleton boolean NOT NULL,
                generation bigint NOT NULL,
                commit_id uuid,
                envelope_version integer,
                snapshot_sha256 bytea,
                envelope_sha256 bytea,
                protected_envelope bytea,
                updated_at_utc timestamptz NOT NULL
            ) PARTITION BY LIST (singleton);
            ALTER TABLE install_linking.unexpected_head_parent
                ATTACH PARTITION install_linking.snapshot_head
                FOR VALUES IN (true);
            """,
            "authority_inheritance_invalid");

    [Fact]
    public Task Standalone_unique_index_fails_live_schema_attestation()
        => AssertLiveSchemaProblemAsync(
            """
            CREATE UNIQUE INDEX unexpected_snapshot_commit_timestamp
            ON install_linking.snapshot_commits (committed_at_utc)
            """,
            "authority_indexes_invalid");

    [Fact]
    public Task Expression_index_fails_live_schema_attestation()
        => AssertLiveSchemaProblemAsync(
            """
            CREATE INDEX unexpected_snapshot_commit_expression
            ON install_linking.snapshot_commits ((generation + 1000))
            """,
            "authority_indexes_invalid");

    [Theory]
    [InlineData(
        "GRANT SELECT ON install_linking.schema_migrations TO $ROLE$")]
    [InlineData(
        "GRANT INSERT ON install_linking.snapshot_commits TO $ROLE$")]
    [InlineData(
        "GRANT UPDATE ON install_linking.snapshot_head TO $ROLE$")]
    [InlineData(
        "GRANT SELECT (generation) ON install_linking.snapshot_commits TO $ROLE$")]
    [InlineData(
        "GRANT USAGE ON SCHEMA install_linking TO $ROLE$")]
    [InlineData(
        "GRANT EXECUTE ON FUNCTION install_linking.guard_snapshot_head_advance_v2() TO $ROLE$")]
    public Task Unrelated_acl_grant_fails_exact_acl_attestation(
        string grantSql)
        => AssertUnrelatedAclRejectedAsync(grantSql);

    [Fact]
    public async Task Owner_default_acl_fails_exact_acl_attestation()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_unrelated_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        try
        {
            await _fixture.ExecuteAdminAsync(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres "
                + "IN SCHEMA install_linking GRANT SELECT ON TABLES TO "
                + QuoteIdentifier(role));

            InstallLinkingPostgresSchemaValidation validation =
                await new InstallLinkingPostgresMigrator(
                        _fixture.AdminDataSource)
                    .ValidateAsync();

            Assert.False(validation.Valid);
            Assert.Contains("authority_acl_invalid", validation.Problems);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres "
                + "IN SCHEMA install_linking REVOKE SELECT ON TABLES FROM "
                + QuoteIdentifier(role));
            await _fixture.DropRoleAsync(role);
        }
    }

    [Theory]
    [InlineData("")]
    [InlineData("IN SCHEMA install_linking ")]
    public async Task Unrelated_role_default_acl_fails_exact_acl_attestation(
        string schemaClause)
    {
        await _fixture.ResetAsync();
        string role = $"install_link_default_owner_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(
            RandomNumberGenerator.GetBytes(32));
        string quotedRole = QuoteIdentifier(role);
        await _fixture.CreateLoginRoleAsync(role, password);
        try
        {
            await _fixture.ExecuteAdminAsync(
                $"ALTER DEFAULT PRIVILEGES FOR ROLE {quotedRole} "
                + schemaClause
                + "GRANT SELECT ON TABLES TO PUBLIC");

            InstallLinkingPostgresSchemaValidation validation =
                await new InstallLinkingPostgresMigrator(
                        _fixture.AdminDataSource)
                    .ValidateAsync();

            Assert.False(validation.Valid);
            Assert.Contains("authority_acl_invalid", validation.Problems);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(
                $"ALTER DEFAULT PRIVILEGES FOR ROLE {quotedRole} "
                + schemaClause
                + "REVOKE SELECT ON TABLES FROM PUBLIC");
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public Task Schema_owner_mismatch_fails_owner_topology_attestation()
        => AssertOwnerTopologyRejectedAsync(
            static quotedRole =>
                $"ALTER SCHEMA install_linking OWNER TO {quotedRole}",
            "ALTER SCHEMA install_linking OWNER TO postgres");

    [Fact]
    public Task Table_owner_mismatch_fails_owner_topology_attestation()
        => AssertOwnerTopologyRejectedAsync(
            static quotedRole =>
                $"ALTER TABLE install_linking.snapshot_head OWNER TO {quotedRole}",
            "ALTER TABLE install_linking.snapshot_head OWNER TO postgres");

    [Fact]
    public Task Function_owner_mismatch_fails_owner_topology_attestation()
        => AssertOwnerTopologyRejectedAsync(
            static quotedRole =>
                "ALTER FUNCTION "
                + "install_linking.guard_snapshot_head_advance_v2() "
                + $"OWNER TO {quotedRole}",
            "ALTER FUNCTION "
            + "install_linking.guard_snapshot_head_advance_v2() "
            + "OWNER TO postgres");

    [Fact]
    public Task Database_owner_mismatch_fails_owner_topology_attestation()
        => AssertOwnerTopologyRejectedAsync(
            static quotedRole =>
                $"ALTER DATABASE chummer_install_linking OWNER TO {quotedRole}",
            "ALTER DATABASE chummer_install_linking OWNER TO postgres");

    [Fact]
    public Task All_authority_objects_transferred_to_unrelated_owner_fail_attestation()
        => AssertOwnerTopologyRejectedAsync(
            static quotedRole => $"""
                ALTER SCHEMA install_linking OWNER TO {quotedRole};
                ALTER TABLE install_linking.schema_migrations
                    OWNER TO {quotedRole};
                ALTER TABLE install_linking.snapshot_head
                    OWNER TO {quotedRole};
                ALTER TABLE install_linking.snapshot_commits
                    OWNER TO {quotedRole};
                ALTER FUNCTION
                    install_linking.guard_snapshot_commit_append_v2()
                    OWNER TO {quotedRole};
                ALTER FUNCTION
                    install_linking.guard_snapshot_head_advance_v2()
                    OWNER TO {quotedRole};
                """,
            """
            ALTER SCHEMA install_linking OWNER TO postgres;
            ALTER TABLE install_linking.schema_migrations OWNER TO postgres;
            ALTER TABLE install_linking.snapshot_head OWNER TO postgres;
            ALTER TABLE install_linking.snapshot_commits OWNER TO postgres;
            ALTER FUNCTION
                install_linking.guard_snapshot_commit_append_v2()
                OWNER TO postgres;
            ALTER FUNCTION
                install_linking.guard_snapshot_head_advance_v2()
                OWNER TO postgres;
            """);

    [Fact]
    public async Task Replica_session_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        var builder = new NpgsqlConnectionStringBuilder(
            _fixture.ConnectionString)
        {
            Options = "-c session_replication_role=replica",
            Pooling = false
        };
        await using NpgsqlDataSource replicaDataSource =
            NpgsqlDataSource.Create(builder.ConnectionString);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(replicaDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains(
            "authority_session_posture_invalid",
            validation.Problems);
    }

    [Fact]
    public async Task Parameter_acl_for_session_replication_role_fails_attestation()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_unrelated_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        string quotedRole = QuoteIdentifier(role);
        try
        {
            await _fixture.ExecuteAdminAsync(
                "GRANT SET ON PARAMETER session_replication_role TO "
                + quotedRole);

            InstallLinkingPostgresSchemaValidation validation =
                await new InstallLinkingPostgresMigrator(
                        _fixture.AdminDataSource)
                    .ValidateAsync();

            Assert.False(validation.Valid);
            Assert.Contains(
                "authority_session_posture_invalid",
                validation.Problems);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(
                "REVOKE ALL ON PARAMETER session_replication_role FROM "
                + quotedRole);
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Dangerous_role_database_default_fails_attestation()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_unrelated_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        string quotedRole = QuoteIdentifier(role);
        try
        {
            await _fixture.ExecuteAdminAsync(
                $"ALTER ROLE {quotedRole} "
                + "IN DATABASE chummer_install_linking "
                + "SET session_replication_role = replica");

            InstallLinkingPostgresSchemaValidation validation =
                await new InstallLinkingPostgresMigrator(
                        _fixture.AdminDataSource)
                    .ValidateAsync();

            Assert.False(validation.Valid);
            Assert.Contains(
                "authority_session_posture_invalid",
                validation.Problems);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(
                $"ALTER ROLE {quotedRole} "
                + "IN DATABASE chummer_install_linking "
                + "RESET session_replication_role");
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Prepared_runtime_role_cannot_set_replication_role_to_replica()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var migrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await migrator.GrantRuntimePrivilegesAsync(role);
            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);
            await using NpgsqlConnection connection =
                await runtimeDataSource.OpenConnectionAsync();
            await using NpgsqlCommand setReplica = connection.CreateCommand();
            setReplica.CommandText =
                "SET session_replication_role = replica";

            PostgresException rejected =
                await Assert.ThrowsAsync<PostgresException>(
                    () => setReplica.ExecuteNonQueryAsync());

            Assert.Equal("42501", rejected.SqlState);
            await using NpgsqlCommand readReplicationRole =
                connection.CreateCommand();
            readReplicationRole.CommandText =
                "SELECT current_setting('session_replication_role')";
            Assert.Equal(
                "origin",
                Convert.ToString(
                    await readReplicationRole.ExecuteScalarAsync(),
                    System.Globalization.CultureInfo.InvariantCulture));
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Altered_schema_migration_default_fails_live_schema_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.schema_migrations
                ALTER COLUMN applied_at_utc
                SET DEFAULT statement_timestamp()
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_columns_invalid", validation.Problems);
    }

    [Fact]
    public async Task Same_named_schema_migration_check_fails_exact_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.schema_migrations
                DROP CONSTRAINT schema_migrations_checksum_sha256_check;
            ALTER TABLE install_linking.schema_migrations
                ADD CONSTRAINT schema_migrations_checksum_sha256_check
                CHECK (true);
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_constraints_invalid", validation.Problems);
    }

    [Fact]
    public async Task Duplicate_migration_history_row_fails_multiplicity_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.schema_migrations
                DROP CONSTRAINT schema_migrations_pkey;
            ALTER TABLE install_linking.schema_migrations
                DROP CONSTRAINT schema_migrations_name_key;
            INSERT INTO install_linking.schema_migrations(
                version,
                name,
                checksum_sha256,
                applied_at_utc)
            SELECT
                version,
                name,
                checksum_sha256,
                applied_at_utc
            FROM install_linking.schema_migrations
            WHERE version = 1;
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains(
            "migration_history_multiplicity_invalid",
            validation.Problems);
        Assert.Contains("authority_constraints_invalid", validation.Problems);
    }

    [Fact]
    public async Task Unlogged_authority_table_fails_relation_posture_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.schema_migrations SET UNLOGGED
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains(
            "authority_relation_posture_invalid",
            validation.Problems);
    }

    [Fact]
    public async Task Runtime_empty_proof_rejects_RLS_that_hides_an_orphan_commit()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        string quotedRole = QuoteIdentifier(role);
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync($"""
                ALTER TABLE install_linking.snapshot_commits
                    DISABLE TRIGGER snapshot_commit_monotonic_append_v2;
                INSERT INTO install_linking.snapshot_commits(
                    generation,
                    commit_id,
                    parent_generation,
                    parent_commit_id,
                    parent_envelope_sha256,
                    envelope_version,
                    snapshot_sha256,
                    envelope_sha256,
                    committed_at_utc)
                VALUES (
                    1,
                    '22222222-2222-2222-2222-222222222222'::uuid,
                    0,
                    NULL,
                    NULL,
                    2,
                    decode(repeat('ab', 32), 'hex'),
                    decode(repeat('cd', 32), 'hex'),
                    clock_timestamp());
                ALTER TABLE install_linking.snapshot_commits
                    ENABLE TRIGGER snapshot_commit_monotonic_append_v2;
                ALTER TABLE install_linking.snapshot_commits
                    ENABLE ROW LEVEL SECURITY;
                CREATE POLICY hide_install_linking_commits
                    ON install_linking.snapshot_commits
                    FOR SELECT
                    TO {quotedRole}
                    USING (false);
                """);
            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);

            InstallLinkingPostgresEmptyAuthorityProof proof =
                await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveEmptyRuntimeAuthorityAsync(role);

            Assert.False(proof.Valid);
            Assert.Equal("schema_invalid", proof.Code);
            Assert.Equal(
                1,
                await _fixture.ScalarLongAsync(
                    "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        }
        finally
        {
            await _fixture.ExecuteAdminAsync("""
                DROP POLICY IF EXISTS hide_install_linking_commits
                    ON install_linking.snapshot_commits;
                ALTER TABLE install_linking.snapshot_commits
                    DISABLE ROW LEVEL SECURITY;
                """);
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Head_tampering_outside_its_commit_fails_chain_attestation()
    {
        await _fixture.ResetAsync();
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(
            _fixture.AdminDataSource);
        InstallLinkingEnvelopeCompareExchangeRequest request =
            RequestForEmptyHead("tamper-detection-envelope");
        using InstallLinkingEnvelopeCompareExchangeResult committed =
            await authority.CompareExchangeAsync(request);
        Assert.True(committed.Committed, committed.Code);
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.snapshot_head
                DISABLE TRIGGER snapshot_head_monotonic_advance_v2;
            UPDATE install_linking.snapshot_head
            SET snapshot_sha256 = decode(repeat('ab', 32), 'hex')
            WHERE singleton = true;
            ALTER TABLE install_linking.snapshot_head
                ENABLE TRIGGER snapshot_head_monotonic_advance_v2;
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_chain_invalid", validation.Problems);
    }

    [Fact]
    public async Task Orphan_commit_fails_chain_attestation()
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync("""
            ALTER TABLE install_linking.snapshot_commits
                DISABLE TRIGGER snapshot_commit_monotonic_append_v2;
            INSERT INTO install_linking.snapshot_commits(
                generation,
                commit_id,
                parent_generation,
                parent_commit_id,
                parent_envelope_sha256,
                envelope_version,
                snapshot_sha256,
                envelope_sha256,
                committed_at_utc)
            VALUES (
                1,
                '11111111-1111-1111-1111-111111111111'::uuid,
                0,
                NULL,
                NULL,
                2,
                decode(repeat('ab', 32), 'hex'),
                decode(repeat('cd', 32), 'hex'),
                clock_timestamp());
            ALTER TABLE install_linking.snapshot_commits
                ENABLE TRIGGER snapshot_commit_monotonic_append_v2;
            """);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains("authority_chain_invalid", validation.Problems);
    }

    [Fact]
    public async Task Thirty_two_independent_data_sources_have_exactly_one_CAS_winner()
    {
        await _fixture.ResetAsync();
        var dataSources = Enumerable.Range(0, 32)
            .Select(_ => NpgsqlDataSource.Create(_fixture.ConnectionString))
            .ToArray();
        try
        {
            InstallLinkingEnvelopeCompareExchangeRequest[] requests = Enumerable
                .Range(0, dataSources.Length)
                .Select(index => RequestForEmptyHead($"concurrent-envelope-{index}"))
                .ToArray();
            Task<InstallLinkingEnvelopeCompareExchangeResult>[] attempts = dataSources
                .Select((dataSource, index) =>
                    new NpgsqlInstallLinkingSnapshotAuthority(dataSource)
                        .CompareExchangeAsync(requests[index]))
                .ToArray();

            InstallLinkingEnvelopeCompareExchangeResult[] results =
                await Task.WhenAll(attempts);
            try
            {
                Assert.Single(results, static result =>
                    result.Disposition == InstallLinkingEnvelopeCommitDisposition.Applied);
                Assert.Equal(
                    31,
                    results.Count(static result =>
                        result.Disposition == InstallLinkingEnvelopeCommitDisposition.Conflict));
            }
            finally
            {
                foreach (InstallLinkingEnvelopeCompareExchangeResult result in results)
                {
                    result.Dispose();
                }
            }

            var authority = new NpgsqlInstallLinkingSnapshotAuthority(
                _fixture.AdminDataSource);
            using InstallLinkingAuthoritativeEnvelope head =
                await authority.ReadCurrentAsync();
            Assert.Equal(1, head.Generation);
            Assert.Contains(requests, request => request.CommitId == head.CommitId);
            Assert.Equal(
                1,
                await _fixture.ScalarLongAsync(
                    "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        }
        finally
        {
            foreach (NpgsqlDataSource dataSource in dataSources)
            {
                await dataSource.DisposeAsync();
            }
        }
    }

    [Fact]
    public async Task Commit_then_connection_loss_reconciles_by_commit_id_without_double_advance()
    {
        await _fixture.ResetAsync();
        var inner = new NpgsqlInstallLinkingPostgresUnitOfWorkFactory(
            _fixture.AdminDataSource);
        var ambiguous = new InstallLinkingCommitThenThrowOnceUnitOfWorkFactory(
            inner);
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(
            _fixture.AdminDataSource,
            ambiguous);
        InstallLinkingEnvelopeCompareExchangeRequest request =
            RequestForEmptyHead("ambiguous-envelope");

        using InstallLinkingEnvelopeCompareExchangeResult result =
            await authority.CompareExchangeAsync(request);

        Assert.Equal(
            InstallLinkingEnvelopeCommitDisposition.AlreadyCommitted,
            result.Disposition);
        Assert.Equal("commit_reconciled", result.Code);
        Assert.Equal(1, result.AuthoritativeEnvelope?.Generation);
        Assert.Equal(request.CommitId, result.AuthoritativeEnvelope?.CommitId);
        Assert.Equal(1, ambiguous.BeginCount);
        Assert.Equal(
            1,
            await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
    }

    [Fact]
    public async Task Runtime_role_can_CAS_but_cannot_rewrite_commit_history_or_delete_head()
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var migrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await migrator.GrantRuntimePrivilegesAsync(role);
            Assert.True(await migrator.ValidateRuntimePrivilegesAsync(role));

            var builder = new NpgsqlConnectionStringBuilder(
                _fixture.ConnectionString)
            {
                Username = role,
                Password = password,
                Pooling = false
            };
            await using NpgsqlDataSource runtimeDataSource =
                NpgsqlDataSource.Create(builder.ConnectionString);
            var runtimeAuthority = new NpgsqlInstallLinkingSnapshotAuthority(
                runtimeDataSource);
            InstallLinkingPostgresReadiness readiness =
                await runtimeAuthority.CheckReadinessAsync();
            Assert.True(readiness.Ready, readiness.Code);
            Assert.Equal("empty_authority_ready", readiness.Code);
            InstallLinkingEnvelopeCompareExchangeRequest request =
                RequestForEmptyHead("runtime-envelope");
            using InstallLinkingEnvelopeCompareExchangeResult committed =
                await runtimeAuthority.CompareExchangeAsync(request);
            Assert.True(committed.Committed, committed.Code);

            await using NpgsqlConnection runtimeConnection =
                await runtimeDataSource.OpenConnectionAsync();
            await using NpgsqlCommand rewrite =
                runtimeConnection.CreateCommand();
            rewrite.CommandText = """
                UPDATE install_linking.snapshot_commits
                SET committed_at_utc = clock_timestamp()
                WHERE generation = 1
                """;
            PostgresException rewriteRejected =
                await Assert.ThrowsAsync<PostgresException>(
                    () => rewrite.ExecuteNonQueryAsync());
            Assert.Equal("42501", rewriteRejected.SqlState);

            await using NpgsqlCommand delete =
                runtimeConnection.CreateCommand();
            delete.CommandText =
                "DELETE FROM install_linking.snapshot_head WHERE singleton = true";
            PostgresException deleteRejected =
                await Assert.ThrowsAsync<PostgresException>(
                    () => delete.ExecuteNonQueryAsync());
            Assert.Equal("42501", deleteRejected.SqlState);
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    [Fact]
    public async Task Database_retains_the_exact_protected_envelope_and_no_plaintext_marker()
    {
        await _fixture.ResetAsync();
        const string plaintextMarker = "install-linking-plaintext-must-not-appear";
        byte[] protectedEnvelope = Encoding.UTF8.GetBytes(
            "{\"format\":\"chummer.install-linking-store\",\"protectedPayload\":\"opaque-ciphertext\"}");
        byte[] logicalSnapshotDigest = SHA256.HashData(
            Encoding.UTF8.GetBytes(plaintextMarker));
        byte[] envelopeDigest = SHA256.HashData(protectedEnvelope);
        var request = new InstallLinkingEnvelopeCompareExchangeRequest(
            ExpectedGeneration: 0,
            ExpectedCommitId: null,
            ExpectedEnvelopeSha256: null,
            NextGeneration: 1,
            CommitId: Guid.NewGuid(),
            EnvelopeVersion:
                InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion,
            SnapshotSha256: logicalSnapshotDigest,
            EnvelopeSha256: envelopeDigest,
            ProtectedEnvelope: protectedEnvelope);
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(
            _fixture.AdminDataSource);

        using InstallLinkingEnvelopeCompareExchangeResult result =
            await authority.CompareExchangeAsync(request);

        Assert.True(result.Committed, result.Code);
        byte[] stored = await _fixture.ScalarBytesAsync(
            "SELECT protected_envelope FROM install_linking.snapshot_head WHERE singleton = true");
        Assert.Equal(protectedEnvelope, stored);
        Assert.Equal(
            -1,
            stored.AsSpan().IndexOf(Encoding.UTF8.GetBytes(plaintextMarker)));
    }

    private async Task AssertLiveSchemaProblemAsync(
        string sql,
        string expectedProblem)
    {
        await _fixture.ResetAsync();
        await _fixture.ExecuteAdminAsync(sql);

        InstallLinkingPostgresSchemaValidation validation =
            await new InstallLinkingPostgresMigrator(_fixture.AdminDataSource)
                .ValidateAsync();

        Assert.False(validation.Valid);
        Assert.Contains(expectedProblem, validation.Problems);
    }

    private async Task AssertUnrelatedAclRejectedAsync(string grantSql)
    {
        await _fixture.ResetAsync();
        string role = $"install_link_unrelated_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        try
        {
            await _fixture.ExecuteAdminAsync(
                grantSql.Replace(
                    "$ROLE$",
                    QuoteIdentifier(role),
                    StringComparison.Ordinal));

            InstallLinkingPostgresSchemaValidation validation =
                await new InstallLinkingPostgresMigrator(
                        _fixture.AdminDataSource)
                    .ValidateAsync();

            Assert.False(validation.Valid);
            Assert.Contains("authority_acl_invalid", validation.Problems);
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    private async Task AssertOwnerTopologyRejectedAsync(
        Func<string, string> transferSql,
        string restoreSql)
    {
        await _fixture.ResetAsync();
        string role = $"install_link_owner_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        try
        {
            await _fixture.ExecuteAdminAsync(
                transferSql(QuoteIdentifier(role)));

            InstallLinkingPostgresSchemaValidation validation =
                await new InstallLinkingPostgresMigrator(
                        _fixture.AdminDataSource)
                    .ValidateAsync();

            Assert.False(validation.Valid);
            Assert.Contains("authority_ownership_invalid", validation.Problems);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(restoreSql);
            await _fixture.DropRoleAsync(role);
        }
    }

    private async Task AssertRuntimeRoleProofRejectsAsync(
        Func<string, string> grantSql)
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync(grantSql(QuoteIdentifier(role)));
            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);

            InstallLinkingPostgresRuntimeRoleProof proof =
                await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveCurrentRuntimeRoleAsync(role);

            Assert.False(proof.Valid);
            Assert.False(proof.LeastPrivilegeValid);
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
        }
    }

    private async Task AssertRuntimeOwnershipRejectedAsync(
        Func<string, string> transferSql,
        string restoreSql)
    {
        await _fixture.ResetAsync();
        string role = $"install_link_runtime_{Guid.NewGuid():N}";
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await _fixture.CreateLoginRoleAsync(role, password);
        var adminMigrator = new InstallLinkingPostgresMigrator(
            _fixture.AdminDataSource);
        try
        {
            await adminMigrator.GrantRuntimePrivilegesAsync(role);
            await _fixture.ExecuteAdminAsync(
                transferSql(QuoteIdentifier(role)));
            await using NpgsqlDataSource runtimeDataSource =
                CreateRuntimeDataSource(role, password);

            InstallLinkingPostgresRuntimeRoleProof proof =
                await new InstallLinkingPostgresMigrator(runtimeDataSource)
                    .ProveCurrentRuntimeRoleAsync(role);

            Assert.False(proof.Valid);
            Assert.False(proof.LeastPrivilegeValid);
        }
        finally
        {
            await _fixture.ExecuteAdminAsync(restoreSql);
            await _fixture.DropRoleAsync(role);
        }
    }

    private NpgsqlDataSource CreateRuntimeDataSource(
        string role,
        string password)
    {
        var builder = new NpgsqlConnectionStringBuilder(
            _fixture.ConnectionString)
        {
            Username = role,
            Password = password,
            Pooling = false
        };
        return NpgsqlDataSource.Create(builder.ConnectionString);
    }

    private static InstallLinkingEnvelopeCompareExchangeRequest RequestForEmptyHead(
        string value)
    {
        byte[] protectedEnvelope = Encoding.UTF8.GetBytes(value);
        return new(
            ExpectedGeneration: 0,
            ExpectedCommitId: null,
            ExpectedEnvelopeSha256: null,
            NextGeneration: 1,
            CommitId: Guid.NewGuid(),
            EnvelopeVersion:
                InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion,
            SnapshotSha256: SHA256.HashData(
                Encoding.UTF8.GetBytes($"snapshot:{value}")),
            EnvelopeSha256: SHA256.HashData(protectedEnvelope),
            ProtectedEnvelope: protectedEnvelope);
    }

    private static string QuoteIdentifier(string value)
    {
        using var builder = new NpgsqlCommandBuilder();
        return builder.QuoteIdentifier(value);
    }
}

public sealed class InstallLinkingPostgresAuthorityFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _container;

    public InstallLinkingPostgresAuthorityFixture()
    {
        string password = Convert.ToHexString(
            RandomNumberGenerator.GetBytes(32));
        _container = new PostgreSqlBuilder("postgres:17-alpine")
            .WithDatabase("chummer_install_linking")
            .WithUsername("postgres")
            .WithPassword(password)
            .Build();
    }

    public NpgsqlDataSource AdminDataSource { get; private set; } = null!;
    public string ConnectionString => _container.GetConnectionString();

    public async Task InitializeAsync()
    {
        await _container.StartAsync();
        AdminDataSource = NpgsqlDataSource.Create(ConnectionString);
        await new InstallLinkingPostgresMigrator(AdminDataSource).MigrateAsync();
    }

    public async Task DisposeAsync()
    {
        if (AdminDataSource is not null)
        {
            await AdminDataSource.DisposeAsync();
        }

        await _container.DisposeAsync();
    }

    public async Task ResetAsync()
    {
        await using NpgsqlConnection connection =
            await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            DROP SCHEMA IF EXISTS install_linking CASCADE
            """;
        await command.ExecuteNonQueryAsync();
        await new InstallLinkingPostgresMigrator(AdminDataSource).MigrateAsync();
    }

    public async Task ExecuteAdminAsync(string sql)
    {
        await using NpgsqlConnection connection =
            await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = sql;
        await command.ExecuteNonQueryAsync();
    }

    public async Task<long> ScalarLongAsync(string sql)
    {
        await using NpgsqlConnection connection =
            await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt64(await command.ExecuteScalarAsync());
    }

    public async Task<byte[]> ScalarBytesAsync(string sql)
    {
        await using NpgsqlConnection connection =
            await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = sql;
        return ((byte[])(await command.ExecuteScalarAsync()
            ?? throw new InvalidOperationException("Expected a bytea result."))).ToArray();
    }

    public async Task CreateLoginRoleAsync(string role, string password)
    {
        string quotedRole;
        using (var builder = new NpgsqlCommandBuilder())
        {
            quotedRole = builder.QuoteIdentifier(role);
        }
        string quotedPassword = $"'{password.Replace("'", "''", StringComparison.Ordinal)}'";

        await using NpgsqlConnection connection =
            await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = $"CREATE ROLE {quotedRole} LOGIN PASSWORD {quotedPassword}";
        await command.ExecuteNonQueryAsync();
    }

    public async Task DropRoleAsync(string role)
    {
        string quotedRole;
        using (var builder = new NpgsqlCommandBuilder())
        {
            quotedRole = builder.QuoteIdentifier(role);
        }

        await using NpgsqlConnection connection =
            await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = $"DROP OWNED BY {quotedRole}; DROP ROLE {quotedRole}";
        await command.ExecuteNonQueryAsync();
    }
}

public sealed class InstallLinkingCommitThenThrowOnceUnitOfWorkFactory :
    IInstallLinkingPostgresUnitOfWorkFactory
{
    private readonly IInstallLinkingPostgresUnitOfWorkFactory _inner;
    private int _remaining = 1;
    private int _beginCount;

    public InstallLinkingCommitThenThrowOnceUnitOfWorkFactory(
        IInstallLinkingPostgresUnitOfWorkFactory inner)
    {
        _inner = inner;
    }

    public int BeginCount => Volatile.Read(ref _beginCount);

    public async ValueTask<IInstallLinkingPostgresUnitOfWork> BeginAsync(
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _beginCount);
        return new CommitThenThrowUnitOfWork(
            await _inner.BeginAsync(cancellationToken),
            this);
    }

    private bool TakeFailure()
        => Interlocked.Exchange(ref _remaining, 0) == 1;

    private sealed class CommitThenThrowUnitOfWork :
        IInstallLinkingPostgresUnitOfWork
    {
        private readonly IInstallLinkingPostgresUnitOfWork _inner;
        private readonly InstallLinkingCommitThenThrowOnceUnitOfWorkFactory _owner;

        public CommitThenThrowUnitOfWork(
            IInstallLinkingPostgresUnitOfWork inner,
            InstallLinkingCommitThenThrowOnceUnitOfWorkFactory owner)
        {
            _inner = inner;
            _owner = owner;
        }

        public NpgsqlConnection Connection => _inner.Connection;
        public NpgsqlTransaction Transaction => _inner.Transaction;

        public async Task CommitAsync(CancellationToken cancellationToken)
        {
            await _inner.CommitAsync(cancellationToken);
            if (_owner.TakeFailure())
            {
                throw new IOException(
                    "simulated connection loss after durable InstallLinking CAS commit");
            }
        }

        public Task RollbackAsync(CancellationToken cancellationToken)
            => _inner.RollbackAsync(cancellationToken);

        public ValueTask DisposeAsync() => _inner.DisposeAsync();
    }
}
