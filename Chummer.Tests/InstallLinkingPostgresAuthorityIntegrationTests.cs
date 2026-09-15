using System.Net;
using System.Runtime.Versioning;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Application.Workspaces;
using Chummer.Contracts.BuildGhost;
using Chummer.Contracts.Characters;
using Chummer.Contracts.Owners;
using Chummer.Contracts.Rulesets;
using Chummer.Contracts.Workspaces;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Infrastructure.Owners;
using Chummer.Infrastructure.Workspaces;
using Chummer.Rulesets.Sr5;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Chummer.Run.Contracts.Identity;
using Docker.DotNet.Models;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
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

    [Theory]
    [InlineData("success")]
    [InlineData("throw")]
    [InlineData("cancel")]
    public async Task Read_fence_blocks_real_CAS_until_callback_exit_and_clears_borrowed_bytes(
        string callbackExit)
    {
        await _fixture.ResetAsync();
        var seedAuthority = new NpgsqlInstallLinkingSnapshotAuthority(_fixture.AdminDataSource);
        InstallLinkingEnvelopeCompareExchangeRequest seed = RequestForEmptyHead("fenced-parent");
        using InstallLinkingEnvelopeCompareExchangeResult seeded =
            await seedAuthority.CompareExchangeAsync(seed);
        Assert.True(seeded.Committed, seeded.Code);
        InstallLinkingEnvelopeCompareExchangeRequest next = RequestAfter(seed, "fenced-next");
        string readerName = $"fence_reader_{Guid.NewGuid():N}";
        string writerName = $"fence_writer_{Guid.NewGuid():N}";
        await using NpgsqlDataSource readerSource = CreateNamedDataSource(readerName);
        await using NpgsqlDataSource writerSource = CreateNamedDataSource(writerName);
        var reader = new NpgsqlInstallLinkingSnapshotAuthority(readerSource);
        var writer = new NpgsqlInstallLinkingSnapshotAuthority(writerSource);
        using var callbackEntered = new ManualResetEventSlim();
        using var releaseCallback = new ManualResetEventSlim();
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        InstallLinkingAuthoritativeEnvelope? borrowed = null;
        var callbackFailure = new InvalidOperationException("test callback failed");
        Task<Exception?> readCompletion = Record.ExceptionAsync(() => Task.Run(() =>
            reader.ReadFencedAsync(envelope =>
            {
                borrowed = envelope;
                Assert.Equal(seed.ProtectedEnvelope, envelope.ProtectedEnvelope);
                callbackEntered.Set();
                entered.TrySetResult();
                if (!releaseCallback.Wait(TimeSpan.FromSeconds(10)))
                {
                    throw new TimeoutException("The test did not release the read callback.");
                }

                if (callbackExit == "throw")
                {
                    throw callbackFailure;
                }

                if (callbackExit == "cancel")
                {
                    cancellation.Cancel();
                }
            }, cancellation.Token)));
        Task<InstallLinkingEnvelopeCompareExchangeResult>? writeTask = null;
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.True(callbackEntered.IsSet);
            writeTask = writer.CompareExchangeAsync(next, cancellationToken: CancellationToken.None);
            await AssertDatabaseBlockedByAsync(writerName, readerName);
            Assert.False(writeTask.IsCompleted);
            Assert.Equal(1, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));

            releaseCallback.Set();
            Exception? failure = await readCompletion.WaitAsync(TimeSpan.FromSeconds(10));
            if (callbackExit == "throw")
            {
                Assert.Same(callbackFailure, failure);
            }
            else if (callbackExit == "cancel")
            {
                Assert.IsAssignableFrom<OperationCanceledException>(failure);
            }
            else
            {
                Assert.Null(failure);
            }

            AssertCleared(borrowed);
            InstallLinkingEnvelopeCompareExchangeResult written =
                await writeTask.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.Equal(InstallLinkingEnvelopeCommitDisposition.Applied, written.Disposition);
            using InstallLinkingAuthoritativeEnvelope head = await seedAuthority.ReadCurrentAsync();
            Assert.Equal(next.CommitId, head.CommitId);
            Assert.Equal(2, head.Generation);
            Assert.Equal(2, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        }
        finally
        {
            releaseCallback.Set();
            await readCompletion.WaitAsync(TimeSpan.FromSeconds(15));
            if (writeTask is not null)
            {
                using InstallLinkingEnvelopeCompareExchangeResult drained =
                    await writeTask.WaitAsync(TimeSpan.FromSeconds(15));
            }
        }
    }

    [Fact]
    public async Task Read_fence_waits_for_actual_earlier_CAS_and_captures_its_committed_head()
    {
        await _fixture.ResetAsync();
        string readerName = $"fence_reader_{Guid.NewGuid():N}";
        string writerName = $"fence_writer_{Guid.NewGuid():N}";
        await using NpgsqlDataSource readerSource = CreateNamedDataSource(readerName);
        await using NpgsqlDataSource writerSource = CreateNamedDataSource(writerName);
        var pausedCommit = new PausedCommitUnitOfWorkFactory(writerSource);
        var writer = new NpgsqlInstallLinkingSnapshotAuthority(writerSource, pausedCommit);
        var reader = new NpgsqlInstallLinkingSnapshotAuthority(readerSource);
        InstallLinkingEnvelopeCompareExchangeRequest request = RequestForEmptyHead("earlier-writer");
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        Task<InstallLinkingEnvelopeCompareExchangeResult> writeTask =
            writer.CompareExchangeAsync(request, cancellation.Token);
        Task? readTask = null;
        InstallLinkingAuthoritativeEnvelope? borrowed = null;
        int callbackCount = 0;
        try
        {
            await pausedCommit.BeforeCommit.Task.WaitAsync(TimeSpan.FromSeconds(5));
            readTask = reader.ReadFencedAsync(envelope =>
            {
                Interlocked.Increment(ref callbackCount);
                borrowed = envelope;
                Assert.Equal(1, envelope.Generation);
                Assert.Equal(request.CommitId, envelope.CommitId);
                Assert.Equal(request.SnapshotSha256, envelope.SnapshotSha256);
                Assert.Equal(request.EnvelopeSha256, envelope.EnvelopeSha256);
                Assert.Equal(request.ProtectedEnvelope, envelope.ProtectedEnvelope);
            }, cancellation.Token);
            await AssertDatabaseBlockedByAsync(readerName, writerName);
            Assert.Equal(0, Volatile.Read(ref callbackCount));
            Assert.False(readTask.IsCompleted);
            // Independent MVCC observer still sees the pre-commit empty authority.
            Assert.Equal(0, await _fixture.ScalarLongAsync(
                "SELECT generation FROM install_linking.snapshot_head WHERE singleton = true"));

            pausedCommit.Release.TrySetResult();
            InstallLinkingEnvelopeCompareExchangeResult written =
                await writeTask.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.Equal(InstallLinkingEnvelopeCommitDisposition.Applied, written.Disposition);
            await readTask.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.Equal(1, Volatile.Read(ref callbackCount));
            AssertCleared(borrowed);
            Assert.Equal(1, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        }
        finally
        {
            pausedCommit.Release.TrySetResult();
            using InstallLinkingEnvelopeCompareExchangeResult drained =
                await writeTask.WaitAsync(TimeSpan.FromSeconds(15));
            if (readTask is not null)
            {
                await readTask.WaitAsync(TimeSpan.FromSeconds(15));
            }
        }
    }

    [Fact]
    public async Task Cancellation_while_database_lock_waiting_never_invokes_capture_or_leaves_a_fence()
    {
        await _fixture.ResetAsync();
        string readerName = $"fence_reader_{Guid.NewGuid():N}";
        string writerName = $"fence_writer_{Guid.NewGuid():N}";
        await using NpgsqlDataSource readerSource = CreateNamedDataSource(readerName);
        await using NpgsqlDataSource writerSource = CreateNamedDataSource(writerName);
        var pausedCommit = new PausedCommitUnitOfWorkFactory(writerSource);
        var writer = new NpgsqlInstallLinkingSnapshotAuthority(writerSource, pausedCommit);
        var reader = new NpgsqlInstallLinkingSnapshotAuthority(readerSource);
        InstallLinkingEnvelopeCompareExchangeRequest request = RequestForEmptyHead("cancel-wait");
        using var cancellation = new CancellationTokenSource();
        Task<InstallLinkingEnvelopeCompareExchangeResult> writeTask = writer.CompareExchangeAsync(request);
        Task<Exception?>? readCompletion = null;
        int callbackCount = 0;
        try
        {
            await pausedCommit.BeforeCommit.Task.WaitAsync(TimeSpan.FromSeconds(5));
            readCompletion = Record.ExceptionAsync(() => reader.ReadFencedAsync(
                _ => Interlocked.Increment(ref callbackCount), cancellation.Token));
            await AssertDatabaseBlockedByAsync(readerName, writerName);
            cancellation.Cancel();
            Exception? failure = await readCompletion.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.IsAssignableFrom<OperationCanceledException>(failure);
            Assert.Equal(0, Volatile.Read(ref callbackCount));
            Assert.False(writeTask.IsCompleted);

            pausedCommit.Release.TrySetResult();
            InstallLinkingEnvelopeCompareExchangeResult written =
                await writeTask.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.True(written.Committed, written.Code);
            await reader.ReadFencedAsync(envelope =>
            {
                Interlocked.Increment(ref callbackCount);
                Assert.Equal(request.CommitId, envelope.CommitId);
            }).WaitAsync(TimeSpan.FromSeconds(10));
            Assert.Equal(1, Volatile.Read(ref callbackCount));
        }
        finally
        {
            cancellation.Cancel();
            pausedCommit.Release.TrySetResult();
            using InstallLinkingEnvelopeCompareExchangeResult drained =
                await writeTask.WaitAsync(TimeSpan.FromSeconds(15));
            if (readCompletion is not null)
            {
                await readCompletion.WaitAsync(TimeSpan.FromSeconds(15));
            }
        }
    }

    [Fact]
    public async Task Coordinator_rejects_stale_bound_mirror_before_local_capture_after_real_CAS()
    {
        await _fixture.ResetAsync();
        await using NpgsqlDataSource readerSource = CreateNamedDataSource($"mirror_reader_{Guid.NewGuid():N}");
        await using NpgsqlDataSource writerSource = CreateNamedDataSource($"mirror_writer_{Guid.NewGuid():N}");
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(readerSource);
        var writer = new NpgsqlInstallLinkingSnapshotAuthority(writerSource);
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);
        InstallLinkingEnvelopeCompareExchangeRequest seed = RequestForEmptyHead("local-mirror");
        using InstallLinkingEnvelopeCompareExchangeResult seeded = await writer.CompareExchangeAsync(seed);
        Assert.True(seeded.Committed, seeded.Code);
        using (InstallLinkingAuthoritativeEnvelope localMirror = await authority.ReadCurrentAsync())
        {
            coordinator.BindValidatedLocalMirror(localMirror);
        }

        int callbackCount = 0;
        var localWriterGate = new object();
        InstallLinkingRollbackAuthorityReadiness matching;
        lock (localWriterGate)
        {
            matching = coordinator.ReadBoundLocalMirror(() => callbackCount++);
        }
        Assert.True(matching.Ready, matching.Code);
        Assert.Equal("postgres_authority_fenced", matching.Code);
        Assert.Equal(1, callbackCount);
        // The bytes and both digests are unchanged: generation/commit identity must fence this out.
        InstallLinkingEnvelopeCompareExchangeRequest next = RequestAfter(seed, "local-mirror");
        Assert.Equal(seed.SnapshotSha256, next.SnapshotSha256);
        Assert.Equal(seed.EnvelopeSha256, next.EnvelopeSha256);
        Assert.Equal(seed.ProtectedEnvelope, next.ProtectedEnvelope);
        Assert.NotEqual(seed.CommitId, next.CommitId);
        using InstallLinkingEnvelopeCompareExchangeResult advanced = await writer.CompareExchangeAsync(next);
        Assert.True(advanced.Committed, advanced.Code);

        InstallLinkingRollbackAuthorityReadiness stale;
        lock (localWriterGate)
        {
            stale = coordinator.ReadBoundLocalMirror(() => callbackCount++);
        }

        Assert.False(stale.Ready);
        Assert.Equal("postgres_authority_head_mismatch", stale.Code);
        Assert.Equal(1, callbackCount);
        using InstallLinkingAuthoritativeEnvelope current = await authority.ReadCurrentAsync();
        Assert.Equal(next.CommitId, current.CommitId);
        Assert.Equal(next.ProtectedEnvelope, current.ProtectedEnvelope);
        Assert.Equal(2, await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
    }

    [Fact]
    public async Task Synchronous_coordinator_under_nonpumping_context_completes_after_real_row_lock_wait()
    {
        await _fixture.ResetAsync();
        string readerName = $"context_reader_{Guid.NewGuid():N}";
        string blockerName = $"context_blocker_{Guid.NewGuid():N}";
        await using NpgsqlDataSource readerSource = CreateNamedDataSource(readerName);
        await using NpgsqlDataSource blockerSource = CreateNamedDataSource(blockerName);
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(readerSource);
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);
        using InstallLinkingEnvelopeCompareExchangeResult seeded =
            await authority.CompareExchangeAsync(RequestForEmptyHead("context-head"));
        Assert.True(seeded.Committed, seeded.Code);
        using (InstallLinkingAuthoritativeEnvelope mirror = await authority.ReadCurrentAsync())
        {
            coordinator.BindValidatedLocalMirror(mirror);
        }

        await using NpgsqlConnection blocker = await blockerSource.OpenConnectionAsync();
        await using NpgsqlTransaction transaction = await blocker.BeginTransactionAsync();
        await using (NpgsqlCommand lockHead = blocker.CreateCommand())
        {
            lockHead.Transaction = transaction;
            lockHead.CommandText = """
                SELECT generation FROM install_linking.snapshot_head
                WHERE singleton = true FOR UPDATE
                """;
            Assert.Equal(1L, Convert.ToInt64(await lockHead.ExecuteScalarAsync()));
        }

        var context = new NonPumpingSynchronizationContext();
        var completion = new TaskCompletionSource<InstallLinkingRollbackAuthorityReadiness>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var localWriterGate = new object();
        int callbackCount = 0;
        var thread = new Thread(() =>
        {
            SynchronizationContext.SetSynchronizationContext(context);
            try
            {
                lock (localWriterGate)
                {
                    completion.TrySetResult(coordinator.ReadBoundLocalMirror(
                        () => Interlocked.Increment(ref callbackCount)));
                }
            }
            catch (Exception exception)
            {
                completion.TrySetException(exception);
            }
            finally
            {
                SynchronizationContext.SetSynchronizationContext(null);
            }
        })
        {
            // A synchronization-context regression must fail within a bound, never hang the runner.
            IsBackground = true,
            Name = "install-linking-nonpumping-read-fence"
        };
        bool released = false;
        thread.Start();
        try
        {
            await AssertDatabaseBlockedByAsync(readerName, blockerName);
            Assert.False(completion.Task.IsCompleted);
            Assert.Equal(0, Volatile.Read(ref callbackCount));
            await transaction.RollbackAsync();
            released = true;

            InstallLinkingRollbackAuthorityReadiness readiness =
                await completion.Task.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.True(readiness.Ready, readiness.Code);
            Assert.Equal("postgres_authority_fenced", readiness.Code);
            Assert.Equal(1, Volatile.Read(ref callbackCount));
            Assert.Equal(0, context.PostCount);
            Assert.True(thread.Join(TimeSpan.FromSeconds(1)));
        }
        finally
        {
            if (!released)
            {
                await transaction.RollbackAsync();
            }

            await completion.Task.WaitAsync(TimeSpan.FromSeconds(10));
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Read_fence_never_mutates_empty_or_committed_head_or_commit_count(bool committed)
    {
        await _fixture.ResetAsync();
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(_fixture.AdminDataSource);
        if (committed)
        {
            using InstallLinkingEnvelopeCompareExchangeResult seeded =
                await authority.CompareExchangeAsync(RequestForEmptyHead("read-only-head"));
            Assert.True(seeded.Committed, seeded.Code);
        }

        using InstallLinkingAuthoritativeEnvelope before = await authority.ReadCurrentAsync();
        long commitsBefore = await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits");
        InstallLinkingAuthoritativeEnvelope? borrowed = null;
        int callbacks = 0;
        await authority.ReadFencedAsync(envelope =>
        {
            callbacks++;
            borrowed = envelope;
            AssertSameHead(before, envelope);
        });
        using InstallLinkingAuthoritativeEnvelope after = await authority.ReadCurrentAsync();

        Assert.Equal(1, callbacks);
        AssertSameHead(before, after);
        Assert.Equal(commitsBefore, await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        if (committed)
        {
            AssertCleared(borrowed);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Corrupt_or_missing_authority_head_rejects_fenced_capture(bool missing)
    {
        await _fixture.ResetAsync();
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(_fixture.AdminDataSource);
        using InstallLinkingEnvelopeCompareExchangeResult seeded =
            await authority.CompareExchangeAsync(RequestForEmptyHead("valid-before-corruption"));
        Assert.True(seeded.Committed, seeded.Code);
        await _fixture.ExecuteAdminAsync(missing
            ? "DELETE FROM install_linking.snapshot_head WHERE singleton = true"
            : """
              ALTER TABLE install_linking.snapshot_head
                  DISABLE TRIGGER snapshot_head_monotonic_advance_v2;
              UPDATE install_linking.snapshot_head
              SET protected_envelope = decode('636f7272757074', 'hex')
              WHERE singleton = true;
              ALTER TABLE install_linking.snapshot_head
                  ENABLE TRIGGER snapshot_head_monotonic_advance_v2;
              """);
        int callbacks = 0;

        Exception? failure = await Record.ExceptionAsync(() => authority.ReadFencedAsync(
            _ => callbacks++)).WaitAsync(TimeSpan.FromSeconds(10));
        if (missing)
        {
            Assert.IsType<InvalidDataException>(failure);
        }
        else
        {
            Assert.IsType<CryptographicException>(failure);
        }

        Assert.Equal(0, callbacks);
        Assert.Equal(1, await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        // A fresh independent transaction can immediately own the singleton relation/row.
        await using NpgsqlConnection probe = await _fixture.AdminDataSource.OpenConnectionAsync();
        await using NpgsqlTransaction transaction = await probe.BeginTransactionAsync();
        await using NpgsqlCommand command = probe.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT generation FROM install_linking.snapshot_head
            WHERE singleton = true FOR UPDATE NOWAIT
            """;
        await command.ExecuteScalarAsync();
        await transaction.RollbackAsync();
    }

    [Theory]
    [InlineData("grant")]
    [InlineData("consent")]
    public async Task Rook_service_capture_excludes_external_revocation_and_rejects_its_stale_mirror(
        string revokedAuthority)
    {
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        var reader = await Task.Run(stores.OpenStore);
        await Task.Run(() => RookConsentPostgresStores.SeedInstallation(reader.Store));
        InstallLinkingRookReadConsent consent = await Task.Run(() => GrantRookConsent(reader.Service));
        var writer = await Task.Run(stores.OpenStore);
        using InstallLinkingAuthoritativeEnvelope before = await reader.Authority.ReadCurrentAsync();
        long commitsBefore = await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits");
        using var releaseCapture = new ManualResetEventSlim();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int captures = 0;
        Task<bool> captureTask = Task.Run(() => CaptureRookConsent(reader.Service, consent,
            (current, installation) =>
            {
                AssertRookConsentSelection(consent, current, installation);
                Interlocked.Increment(ref captures);
                entered.TrySetResult();
                if (!releaseCapture.Wait(TimeSpan.FromSeconds(10)))
                {
                    throw new TimeoutException("The test did not release the Rook capture.");
                }
            }));
        Task? revokeTask = null;
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            revokeTask = Task.Run(() =>
            {
                if (revokedAuthority == "grant")
                {
                    writer.Service.RevokeGrantForOwner(RookConsentPostgresStores.InstallationId,
                        RookConsentPostgresStores.UserId, RookConsentPostgresStores.SubjectId);
                }
                else
                {
                    InstallLinkingRookReadConsent revoked = writer.Service.RevokeRookReadConsent(
                        RookConsentPostgresStores.UserId, RookConsentPostgresStores.SubjectId,
                        consent.ConsentId, consent.Version);
                    Assert.Equal(consent.Version + 1, revoked.Version);
                    Assert.NotNull(revoked.RevokedAtUtc);
                }
            });
            await AssertDatabaseBlockedByAsync(writer.ApplicationName, reader.ApplicationName);
            Assert.False(captureTask.IsCompleted);
            Assert.False(revokeTask.IsCompleted);
            Assert.Equal(commitsBefore, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));

            releaseCapture.Set();
            Assert.True(await captureTask.WaitAsync(TimeSpan.FromSeconds(10)));
            await revokeTask.WaitAsync(TimeSpan.FromSeconds(10));
            using InstallLinkingAuthoritativeEnvelope after = await reader.Authority.ReadCurrentAsync();
            Assert.Equal(before.Generation + 1, after.Generation);
            Assert.NotEqual(before.CommitId, after.CommitId);
            Assert.Equal(commitsBefore + 1, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));

            // This process still holds the once-valid consent and active grant. Only the
            // real service's database-bound mirror check can prevent their stale reuse.
            Assert.Equal(consent, reader.Store.RookReadConsentsById[consent.ConsentId]);
            Assert.Equal(InstallationGrantStates.Active,
                reader.Store.GrantsById[RookConsentPostgresStores.GrantId].Status);
            Assert.False(CaptureRookConsent(reader.Service, consent,
                (_, _) => Interlocked.Increment(ref captures)));
            Assert.Equal(1, Volatile.Read(ref captures));

            var reloaded = await Task.Run(stores.OpenStore);
            Assert.False(CaptureRookConsent(reloaded.Service, consent,
                (_, _) => Interlocked.Increment(ref captures)));
            Assert.Equal(1, Volatile.Read(ref captures));
            if (revokedAuthority == "grant")
            {
                Assert.Equal(InstallationGrantStates.Revoked,
                    reloaded.Store.GrantsById[RookConsentPostgresStores.GrantId].Status);
            }
            else
            {
                InstallLinkingRookReadConsent revoked =
                    reloaded.Store.RookReadConsentsById[consent.ConsentId];
                Assert.Equal(consent.Version + 1, revoked.Version);
                Assert.NotNull(revoked.RevokedAtUtc);
                Assert.False(CaptureRookConsent(reloaded.Service, revoked,
                    (_, _) => Interlocked.Increment(ref captures)));
                Assert.Equal(1, Volatile.Read(ref captures));
            }
        }
        finally
        {
            releaseCapture.Set();
            await captureTask.WaitAsync(TimeSpan.FromSeconds(15));
            if (revokeTask is not null)
            {
                await revokeTask.WaitAsync(TimeSpan.FromSeconds(15));
            }
        }
    }

    [Fact]
    public async Task Rook_service_rejects_byte_identical_authority_generation_advance_before_capture()
    {
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        var reader = await Task.Run(stores.OpenStore);
        await Task.Run(() => RookConsentPostgresStores.SeedInstallation(reader.Store));
        InstallLinkingRookReadConsent consent = await Task.Run(() => GrantRookConsent(reader.Service));
        var writer = await Task.Run(stores.OpenStore);
        using InstallLinkingAuthoritativeEnvelope before = await reader.Authority.ReadCurrentAsync();
        long commitsBefore = await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits");
        int captures = 0;
        Assert.True(CaptureRookConsent(reader.Service, consent, (_, _) => captures++));
        var next = new InstallLinkingEnvelopeCompareExchangeRequest(
            ExpectedGeneration: before.Generation,
            ExpectedCommitId: before.CommitId,
            ExpectedEnvelopeSha256: before.EnvelopeSha256!.ToArray(),
            NextGeneration: before.Generation + 1,
            CommitId: Guid.NewGuid(),
            EnvelopeVersion: before.EnvelopeVersion!.Value,
            SnapshotSha256: before.SnapshotSha256!.ToArray(),
            EnvelopeSha256: before.EnvelopeSha256!.ToArray(),
            ProtectedEnvelope: before.ProtectedEnvelope!.ToArray());
        try
        {
            using InstallLinkingEnvelopeCompareExchangeResult committed =
                await writer.Authority.CompareExchangeAsync(next);
            Assert.True(committed.Committed, committed.Code);
            using InstallLinkingAuthoritativeEnvelope after = await reader.Authority.ReadCurrentAsync();
            Assert.Equal(before.ProtectedEnvelope, after.ProtectedEnvelope);
            Assert.Equal(before.SnapshotSha256, after.SnapshotSha256);
            Assert.Equal(before.EnvelopeSha256, after.EnvelopeSha256);
            Assert.Equal(before.Generation + 1, after.Generation);
            Assert.NotEqual(before.CommitId, after.CommitId);

            Assert.False(CaptureRookConsent(reader.Service, consent, (_, _) => captures++));
            Assert.Equal(1, captures);
            using InstallLinkingAuthoritativeEnvelope afterRejectedRead = await reader.Authority.ReadCurrentAsync();
            AssertSameHead(after, afterRejectedRead);
            Assert.Equal(commitsBefore + 1, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(next.ExpectedEnvelopeSha256!);
            CryptographicOperations.ZeroMemory(next.SnapshotSha256);
            CryptographicOperations.ZeroMemory(next.EnvelopeSha256);
            CryptographicOperations.ZeroMemory(next.ProtectedEnvelope);
        }
    }

    [Theory]
    [InlineData("throw")]
    [InlineData("cancel")]
    public async Task Rook_service_never_accepts_failed_or_canceled_capture_and_releases_the_real_row(
        string callbackExit)
    {
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        var reader = await Task.Run(stores.OpenStore);
        await Task.Run(() => RookConsentPostgresStores.SeedInstallation(reader.Store));
        InstallLinkingRookReadConsent consent = await Task.Run(() => GrantRookConsent(reader.Service));
        var writer = await Task.Run(stores.OpenStore);
        using InstallLinkingAuthoritativeEnvelope before = await reader.Authority.ReadCurrentAsync();
        long commitsBefore = await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits");
        using var releaseCapture = new ManualResetEventSlim();
        using var cancellation = new CancellationTokenSource();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        bool? accepted = null;
        int captures = 0;
        Task<Exception?> captureCompletion = Record.ExceptionAsync(() => Task.Run(() =>
        {
            accepted = CaptureRookConsent(reader.Service, consent, (current, installation) =>
            {
                AssertRookConsentSelection(consent, current, installation);
                Interlocked.Increment(ref captures);
                entered.TrySetResult();
                if (!releaseCapture.Wait(TimeSpan.FromSeconds(10)))
                {
                    throw new TimeoutException("The test did not release the failing Rook capture.");
                }

                if (callbackExit == "throw")
                {
                    throw new InvalidOperationException("The consent selection capture failed.");
                }

                cancellation.Cancel();
            }, cancellation.Token);
        }));
        Task? revokeTask = null;
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            revokeTask = Task.Run(() => writer.Service.RevokeGrantForOwner(
                RookConsentPostgresStores.InstallationId,
                RookConsentPostgresStores.UserId, RookConsentPostgresStores.SubjectId));
            await AssertDatabaseBlockedByAsync(writer.ApplicationName, reader.ApplicationName);
            Assert.False(revokeTask.IsCompleted);
            Assert.False(captureCompletion.IsCompleted);
            Assert.Equal(commitsBefore, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));

            releaseCapture.Set();
            Exception? failure = await captureCompletion.WaitAsync(TimeSpan.FromSeconds(10));
            if (callbackExit == "cancel")
            {
                Assert.IsAssignableFrom<OperationCanceledException>(failure);
                Assert.Null(accepted);
            }
            else
            {
                Assert.Null(failure);
                Assert.Equal(false, accepted);
            }

            Assert.Equal(1, Volatile.Read(ref captures));
            await revokeTask.WaitAsync(TimeSpan.FromSeconds(10));
            using InstallLinkingAuthoritativeEnvelope after = await reader.Authority.ReadCurrentAsync();
            Assert.Equal(before.Generation + 1, after.Generation);
            Assert.Equal(commitsBefore + 1, await _fixture.ScalarLongAsync(
                "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
            var reloaded = await Task.Run(stores.OpenStore);
            Assert.False(CaptureRookConsent(reloaded.Service, consent,
                (_, _) => Interlocked.Increment(ref captures)));
            Assert.Equal(1, Volatile.Read(ref captures));
        }
        finally
        {
            releaseCapture.Set();
            await captureCompletion.WaitAsync(TimeSpan.FromSeconds(15));
            if (revokeTask is not null)
            {
                await revokeTask.WaitAsync(TimeSpan.FromSeconds(15));
            }
        }
    }

    [Fact]
    public async Task Rook_service_captures_exact_consent_selection_without_mutating_authority_or_mirror()
    {
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        var reader = await Task.Run(stores.OpenStore);
        await Task.Run(() => RookConsentPostgresStores.SeedInstallation(reader.Store));
        InstallLinkingRookReadConsent consent = await Task.Run(() => GrantRookConsent(reader.Service));
        using InstallLinkingAuthoritativeEnvelope before = await reader.Authority.ReadCurrentAsync();
        long commitsBefore = await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits");
        long persistenceAttempts = reader.Store.PersistenceAttempts;
        byte[] mirrorBefore = File.ReadAllBytes(reader.Store.StoragePath);
        int captures = 0;

        Assert.True(CaptureRookConsent(reader.Service, consent, (current, installation) =>
        {
            AssertRookConsentSelection(consent, current, installation);
            captures++;
        }));

        using InstallLinkingAuthoritativeEnvelope after = await reader.Authority.ReadCurrentAsync();
        Assert.Equal(1, captures);
        AssertSameHead(before, after);
        Assert.Equal(commitsBefore, await _fixture.ScalarLongAsync(
            "SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        Assert.Equal(persistenceAttempts, reader.Store.PersistenceAttempts);
        Assert.Equal(mirrorBefore, File.ReadAllBytes(reader.Store.StoragePath));
        Assert.Equal(consent, Assert.Single(reader.Store.RookReadConsentsById.Values));
    }

    [Theory]
    [InlineData("new_session")]
    [InlineData("revoked_consent")]
    public async Task Rook_orchestrator_captures_and_revalidates_the_exact_persisted_selection_then_denies_changed_authority(
        string change)
    {
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        var reader = await Task.Run(stores.OpenStore);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = "Testing",
                ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid",
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(stores.Root, "community.json"),
                ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] =
                    Path.Combine(stores.Root, "selected-workspace.json")
            })
            .Build();
        var community = new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
        var accounts = new AccountService(community);
        var user = accounts.EnsureUser(RookConsentPostgresStores.SubjectId,
            "Rook PostgreSQL owner", "rook-postgres@example.invalid");
        await Task.Run(() => RookConsentPostgresStores.SeedInstallation(reader.Store, user.UserId));
        ClaimedInstallationDto installation = reader.Store.InstallationsById[RookConsentPostgresStores.InstallationId];
        string owner = InstallLinkedWorkspaceSnapshotTransfer.ComputeContinuationOwnerId(user.SubjectId);
        var workspace = new WorkspaceDocumentSnapshot(
            new CharacterWorkspaceId("rook-postgres-selected-workspace"),
            new WorkspaceDocument(new WorkspaceDocumentState("sr5", 1, "workspace",
                "<character><name>Selected Rook transport fixture</name></character>")),
            DateTimeOffset.UtcNow, 1, 0);
        // A minimal Core transport document, with no claimed rules execution or GM history.
        var continuation = new WorkspaceContinuationSnapshot(owner, workspace, []);
        string digest = WorkspaceContinuationSnapshotDigest.Compute(continuation);
        using JsonDocument encoded = JsonDocument.Parse(WorkspaceContinuationCodec.Encode(
            new(continuation, digest), InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes));
        var incoming = new InstallLinkedWorkspaceSnapshotRecord(
            "", workspace.Id.Value, workspace.Document.RulesetId, "NativeXml",
            workspace.Document.SchemaVersion, workspace.Document.PayloadKind, workspace.Document.Content,
            workspace.LastUpdatedUtc, installation.InstallationId, "Selected Rook transport fixture",
            null, null, null, null, null, 0, 0, false,
            WorkspaceContinuation: encoded.RootElement.Clone(), WorkspaceContinuationDigest: digest);
        var snapshotWriter = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(configuration));
        InstallLinkedWorkspaceSnapshotRecord selected = snapshotWriter.UpsertForInstallation(installation, incoming, 0);
        Assert.Equal(1, selected.RemoteRevision);
        Assert.Equal(digest, selected.WorkspaceContinuationDigest);
        // Exercise the on-disk row through a fresh actual snapshot store.
        var snapshotStore = new InstallLinkedWorkspaceSnapshotStore(configuration);
        Assert.Single(snapshotStore.SnapshotsByKey);
        var snapshots = new InstallLinkedWorkspaceSnapshotService(snapshotStore);
        using var identity = new RookPostgresIdentityTransport(DateTimeOffset.UtcNow.AddMinutes(10));
        using var http = new HttpClient(identity);
        var sessions = new HubSessionAccountAdmissionService(http, configuration, accounts, TimeProvider.System);
        var admission = new RookWorkspaceReadAdmissionService(
            sessions, accounts, reader.Service, snapshots, TimeProvider.System);
        HttpRequest request = new DefaultHttpContext().Request;
        request.Headers.Authorization = "Bearer " + RookPostgresIdentityTransport.Bearer;
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));

        InstallLinkingRookReadConsent consent = await Task.Run(() => admission.GrantAsync(request,
            installation.InstallationId, installation.GrantId!, selected.WorkspaceId,
            selected.RemoteRevision, selected.ServerToken!, selected.WorkspaceContinuationDigest!,
            explicitConfirmation: true, expiresAtUtc: DateTimeOffset.UtcNow.AddMinutes(2), ct: deadline.Token))
            .WaitAsync(deadline.Token);
        Assert.Equal(1, identity.Calls);
        Assert.Equal(consent, Assert.Single(reader.Store.RookReadConsentsById.Values));
        using InstallLinkingAuthoritativeEnvelope grantedHead = await reader.Authority.ReadCurrentAsync(deadline.Token);
        long commitsAfterGrant = await _fixture.ScalarLongAsync("SELECT COUNT(*) FROM install_linking.snapshot_commits");
        byte[] persistedSnapshot = File.ReadAllBytes(configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!);

        string blockerName = $"rook_orchestrator_blocker_{Guid.NewGuid():N}";
        await using NpgsqlDataSource blockerSource = CreateNamedDataSource(blockerName);
        await using NpgsqlConnection blocker = await blockerSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlTransaction transaction = await blocker.BeginTransactionAsync(deadline.Token);
        await using (NpgsqlCommand holdHead = blocker.CreateCommand())
        {
            holdHead.Transaction = transaction;
            holdHead.CommandText = "SELECT generation FROM install_linking.snapshot_head WHERE singleton = true FOR UPDATE";
            Assert.Equal(grantedHead.Generation, Convert.ToInt64(await holdHead.ExecuteScalarAsync(deadline.Token)));
        }

        Task<RookWorkspaceReadCapture> captureTask = Task.Run(() => admission.CaptureAsync(request,
            installation.InstallationId, installation.GrantId!, consent.ConsentId, consent.Version, deadline.Token));
        try
        {
            await AssertDatabaseBlockedByAsync(reader.ApplicationName, blockerName);
            Assert.Equal(2, identity.Calls);
            Assert.False(captureTask.IsCompleted);
        }
        finally
        {
            // Force an actual awaited PostgreSQL continuation while account/install gates
            // belong to the caller. The capture must then reach the actual snapshot gate.
            using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            await transaction.RollbackAsync(cleanup.Token);
        }

        RookWorkspaceReadCapture captured = await captureTask.WaitAsync(deadline.Token);
        Assert.Equal(2, identity.Calls);
        Assert.Equal(user.UserId, captured.Account.UserId);
        Assert.Equal(user.SubjectId, captured.Account.SubjectId);
        Assert.Equal(RookPostgresIdentityTransport.InitialSessionId, captured.Account.SessionId);
        Assert.Equal(consent, captured.Consent);
        Assert.Equal(user.UserId, captured.Consent.UserId);
        Assert.Equal(selected.OwnerKey, captured.Snapshot.OwnerKey);
        Assert.Equal(selected.WorkspaceId, captured.Snapshot.WorkspaceId);
        Assert.Equal(selected.RemoteRevision, captured.Snapshot.RemoteRevision);
        Assert.Equal(selected.ServerToken, captured.Snapshot.ServerToken);
        Assert.Equal(digest, captured.Snapshot.WorkspaceContinuationDigest);
        Assert.Equal(workspace.Document.Content, captured.Snapshot.Payload);
        Assert.True(WorkspaceContinuationCodec.TryDecodeCandidate(
            Encoding.UTF8.GetBytes(captured.Snapshot.WorkspaceContinuation!.Value.GetRawText()),
            InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes, out WorkspaceContinuationExport? decoded));
        Assert.Equal(owner, decoded!.Snapshot.OwnerId);
        Assert.Equal(workspace.Id, decoded.Snapshot.Workspace.Id);
        Assert.Equal(digest, decoded.SnapshotDigest);
        Assert.Empty(decoded.Snapshot.DelegatedGmCharacterEdits);
        Assert.Empty(decoded.Snapshot.DelegatedGmHistorySegmentStarts);
        Assert.Single(snapshotStore.SnapshotsByKey);

        await Task.Yield();
        await Task.Run(() => admission.RevalidateAsync(request, captured, deadline.Token)).WaitAsync(deadline.Token);
        Assert.Equal(3, identity.Calls);
        using (InstallLinkingAuthoritativeEnvelope afterRevalidation = await reader.Authority.ReadCurrentAsync(deadline.Token))
        {
            AssertSameHead(grantedHead, afterRevalidation);
        }
        Assert.Equal(commitsAfterGrant, await _fixture.ScalarLongAsync("SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        Assert.Equal(persistedSnapshot,
            File.ReadAllBytes(configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!));

        if (change == "new_session")
        {
            identity.SessionId = "rook-postgres-another-active-session";
        }
        else
        {
            InstallLinkingRookReadConsent revoked = await Task.Run(() => admission.RevokeAsync(
                request, consent.ConsentId, consent.Version, deadline.Token)).WaitAsync(deadline.Token);
            Assert.Equal(4, identity.Calls);
            Assert.Equal(consent.Version + 1, revoked.Version);
            Assert.NotNull(revoked.RevokedAtUtc);
            Assert.Equal(InstallationGrantStates.Active, reader.Store.GrantsById[installation.GrantId!].Status);
        }

        using InstallLinkingAuthoritativeEnvelope beforeDeniedRevalidation = await reader.Authority.ReadCurrentAsync(deadline.Token);
        InstallLinkingOperationException denied = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => Task.Run(() => admission.RevalidateAsync(request, captured, deadline.Token)).WaitAsync(deadline.Token));
        Assert.Equal(StatusCodes.Status403Forbidden, denied.StatusCode);
        Assert.Equal(change == "new_session" ? 4 : 5, identity.Calls);
        Assert.Equal(user.SubjectId, identity.SubjectId);
        using InstallLinkingAuthoritativeEnvelope afterDeniedRevalidation = await reader.Authority.ReadCurrentAsync(deadline.Token);
        AssertSameHead(beforeDeniedRevalidation, afterDeniedRevalidation);
        Assert.Equal(persistedSnapshot,
            File.ReadAllBytes(configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!));
    }

    [Theory]
    [InlineData("unchanged")]
    [InlineData("revoked_consent")]
    [InlineData("revoked_grant")]
    [InlineData("new_session")]
    [InlineData("snapshot_generation")]
    [InlineData("authority_generation")]
    [InlineData("canceled")]
    [InlineData("expired_session")]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_Core_result_requires_fresh_authority_after_runtime_disposal(string change)
    {
        Assert.True(OperatingSystem.IsLinux(), "The actual request-private scratch allocator requires Linux.");
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        using var requestCancellation = CancellationTokenSource.CreateLinkedTokenSource(deadline.Token);
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        using RookRuntimeScenario scenario = await Task.Run(() => new RookRuntimeScenario(stores), deadline.Token)
            .WaitAsync(deadline.Token);
        InstallLinkingRookReadConsent consent = await scenario.GrantAsync(deadline.Token).WaitAsync(deadline.Token);
        Assert.Equal(1, scenario.Identity.Calls);
        using InstallLinkingAuthoritativeEnvelope granted = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        byte[] mirror = File.ReadAllBytes(scenario.Reader.Store.StoragePath);
        byte[] snapshots = File.ReadAllBytes(scenario.SnapshotPath);
        long commits = await _fixture.ScalarLongAsync("SELECT COUNT(*) FROM install_linking.snapshot_commits");
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        scenario.Identity.BeforeResponse = async (call, ct) =>
        {
            if (call != 3) return;
            entered.TrySetResult();
            await release.Task.WaitAsync(ct);
        };

        Task<WorkspaceRuleQuestionResult> pending = Task.Run(
            () => scenario.ResolveAsync(consent, requestCancellation.Token), deadline.Token);
        try
        {
            // The real adapter reached its second Identity call only after actual
            // Core restore/query and disposal. Nothing has been released yet.
            await entered.Task.WaitAsync(deadline.Token);
            Assert.False(pending.IsCompleted);
            Assert.Equal(3, scenario.Identity.Calls);
            Assert.True(scenario.RuntimeClock.SawOwnedScratch,
                "Core's actual restore receipt clock did not observe its allocated private child before revalidation.");
            scenario.AssertPrivateWorkCleanedAndInputsUnchanged();
            using (InstallLinkingAuthoritativeEnvelope readOnly = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token))
                AssertSameHead(granted, readOnly);
            Assert.Equal(commits, await _fixture.ScalarLongAsync("SELECT COUNT(*) FROM install_linking.snapshot_commits"));
            Assert.Equal(snapshots, File.ReadAllBytes(scenario.SnapshotPath));

            if (change is "revoked_consent" or "revoked_grant" or "authority_generation")
            {
                var writer = await Task.Run(stores.OpenStore, deadline.Token).WaitAsync(deadline.Token);
                if (change == "revoked_consent")
                {
                    InstallLinkingRookReadConsent revoked = await Task.Run(() => writer.Service.RevokeRookReadConsent(
                        scenario.UserId, RookConsentPostgresStores.SubjectId, consent.ConsentId, consent.Version,
                        deadline.Token), deadline.Token).WaitAsync(deadline.Token);
                    Assert.NotNull(revoked.RevokedAtUtc);
                }
                else if (change == "revoked_grant")
                {
                    await Task.Run(() => writer.Service.RevokeGrantForOwner(RookConsentPostgresStores.InstallationId,
                        scenario.UserId, RookConsentPostgresStores.SubjectId), deadline.Token).WaitAsync(deadline.Token);
                }
                else
                {
                    var next = new InstallLinkingEnvelopeCompareExchangeRequest(granted.Generation, granted.CommitId,
                        granted.EnvelopeSha256!.ToArray(), granted.Generation + 1, Guid.NewGuid(),
                        granted.EnvelopeVersion!.Value, granted.SnapshotSha256!.ToArray(),
                        granted.EnvelopeSha256!.ToArray(), granted.ProtectedEnvelope!.ToArray());
                    try
                    {
                        using InstallLinkingEnvelopeCompareExchangeResult committed =
                            await writer.Authority.CompareExchangeAsync(next, deadline.Token);
                        Assert.True(committed.Committed, committed.Code);
                        using InstallLinkingAuthoritativeEnvelope advanced = await writer.Authority.ReadCurrentAsync(deadline.Token);
                        Assert.Equal(granted.ProtectedEnvelope, advanced.ProtectedEnvelope);
                        Assert.Equal(granted.EnvelopeSha256, advanced.EnvelopeSha256);
                        Assert.Equal(granted.Generation + 1, advanced.Generation);
                        Assert.NotEqual(granted.CommitId, advanced.CommitId);
                    }
                    finally
                    {
                        CryptographicOperations.ZeroMemory(next.ExpectedEnvelopeSha256!);
                        CryptographicOperations.ZeroMemory(next.SnapshotSha256);
                        CryptographicOperations.ZeroMemory(next.EnvelopeSha256);
                        CryptographicOperations.ZeroMemory(next.ProtectedEnvelope);
                    }
                }
                // The caller's once-valid mirror remains byte-identical and active:
                // only the real PostgreSQL fence can detect this external writer.
                Assert.Equal(mirror, File.ReadAllBytes(scenario.Reader.Store.StoragePath));
                Assert.Equal(consent, scenario.Reader.Store.RookReadConsentsById[consent.ConsentId]);
                Assert.Equal(InstallationGrantStates.Active, scenario.Reader.Store.GrantsById[consent.GrantId].Status);
            }
            else if (change == "snapshot_generation")
            {
                InstallLinkedWorkspaceSnapshotRecord changed = scenario.Snapshots.UpsertForInstallation(
                    scenario.Installation, scenario.Selected with { Name = "Explicit concurrent remote metadata update" },
                    scenario.Selected.RemoteRevision, scenario.Selected.ServerToken);
                Assert.Equal(scenario.Selected.RemoteRevision + 1, changed.RemoteRevision);
                Assert.Equal(scenario.Selected.WorkspaceContinuationDigest, changed.WorkspaceContinuationDigest);
            }
            else if (change == "new_session") scenario.Identity.SessionId = "another-active-owner-session";
            else if (change == "expired_session") scenario.Identity.ExpiresAtUtc = DateTimeOffset.UtcNow.AddSeconds(-1);
            else if (change == "canceled") requestCancellation.Cancel();
            using InstallLinkingAuthoritativeEnvelope beforeRelease = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
            byte[] snapshotBeforeRelease = File.ReadAllBytes(scenario.SnapshotPath);
            release.TrySetResult();
            if (change == "unchanged")
            {
                WorkspaceRuleQuestionResult result = await pending.WaitAsync(deadline.Token);
                Assert.True(result.Resolved, result.FailureReason);
                Assert.Equal(1, result.Level);
                Assert.Equal(4, result.MaximumLevel);
                Assert.Equal(WorkspaceRuleQuestionIntegrity.ComputeResultDigest(result), result.ResultDigest);
                WorkspaceRuleQuestionBinding binding = Assert.IsType<WorkspaceRuleQuestionBinding>(result.Binding);
                Assert.Equal(scenario.Owner.Value, binding.OwnerId);
                Assert.False(binding.TrustedLocalOwner);
                Assert.NotEqual(scenario.ExportIssuerId, binding.OwnerAuthorityInstanceId);
                Assert.Equal(scenario.Exported.Snapshot.Workspace.Id, binding.WorkspaceId);
                Assert.Equal(2, binding.ContentRevision);
                Assert.Equal(1, binding.SavedRevision);
                Assert.NotEqual(scenario.Selected.RemoteRevision, binding.ContentRevision);
                Assert.Equal(RookRuntimeScenario.SavedQualityId, binding.SubjectId);
                Assert.NotEmpty(binding.ExecutingModules);
                WorkspaceRuleSourceAnchor anchor = Assert.Single(result.SourceAnchors);
                Assert.Equal("HUBTEST", anchor.SourceBook);
                Assert.Equal(12, anchor.Page);
                Assert.Equal(RookRuntimeScenario.QualitySourceId, anchor.QualitySourceId);
                Assert.NotEmpty(anchor.CalculationTrace);
                Assert.DoesNotContain(RookRuntimeScenario.PrivateNotes, JsonSerializer.Serialize(result));
            }
            else if (change == "canceled")
                await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending.WaitAsync(deadline.Token));
            else if (change == "expired_session")
            {
                HubRequestAuthException denied = await Assert.ThrowsAsync<HubRequestAuthException>(
                    () => pending.WaitAsync(deadline.Token));
                Assert.Equal(StatusCodes.Status401Unauthorized, denied.StatusCode);
            }
            else
            {
                InstallLinkingOperationException denied = await Assert.ThrowsAsync<InstallLinkingOperationException>(
                    () => pending.WaitAsync(deadline.Token));
                Assert.Equal(change == "snapshot_generation" ? StatusCodes.Status409Conflict : StatusCodes.Status403Forbidden,
                    denied.StatusCode);
            }
            using InstallLinkingAuthoritativeEnvelope afterRelease = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
            AssertSameHead(beforeRelease, afterRelease);
            Assert.Equal(snapshotBeforeRelease, File.ReadAllBytes(scenario.SnapshotPath));
            scenario.AssertPrivateWorkCleanedAndInputsUnchanged();
        }
        finally
        {
            release.TrySetResult();
            requestCancellation.Cancel();
            // Never dispose the real stores beneath an abandoned asynchronous read
            // when an assertion fails. Its expected denial/cancellation may be drained;
            // failure to terminate within this separate cleanup bound fails the test.
            try { await pending.WaitAsync(TimeSpan.FromSeconds(5)); }
            catch (Exception) when (pending.IsCompleted) { }
        }
    }

    [Fact]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_Core_unsupported_intent_returns_only_its_actual_unresolved_result_after_revalidation()
    {
        Assert.True(OperatingSystem.IsLinux());
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        using RookRuntimeScenario scenario = await Task.Run(() => new RookRuntimeScenario(stores), deadline.Token)
            .WaitAsync(deadline.Token);
        InstallLinkingRookReadConsent consent = await scenario.GrantAsync(deadline.Token).WaitAsync(deadline.Token);
        using InstallLinkingAuthoritativeEnvelope before = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        byte[] snapshot = File.ReadAllBytes(scenario.SnapshotPath);
        WorkspaceRuleQuestionResult result = await Task.Run(() => scenario.ResolveAsync(consent, deadline.Token,
            intent: "unsupported-read-intent"), deadline.Token).WaitAsync(deadline.Token);
        Assert.Equal(3, scenario.Identity.Calls);
        Assert.Equal(WorkspaceRuleQuestionSchemas.ResultV1, result.Schema);
        Assert.Equal(WorkspaceRuleQuestionStatuses.Unresolved, result.Status);
        Assert.False(result.Resolved);
        Assert.Null(result.Binding);
        Assert.Null(result.Level);
        Assert.Null(result.MaximumLevel);
        Assert.Empty(result.SourceAnchors);
        Assert.Empty(result.Explanation.SourceAnchorIds);
        Assert.Equal(WorkspaceRuleQuestionIntegrity.ComputeResultDigest(result), result.ResultDigest);
        Assert.DoesNotContain(RookRuntimeScenario.PrivateNotes, JsonSerializer.Serialize(result));
        Assert.True(scenario.RuntimeClock.SawOwnedScratch);
        using InstallLinkingAuthoritativeEnvelope after = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        AssertSameHead(before, after);
        Assert.Equal(snapshot, File.ReadAllBytes(scenario.SnapshotPath));
        scenario.AssertPrivateWorkCleanedAndInputsUnchanged();
    }

    [Fact]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_Core_restore_rejects_a_complete_but_invalid_character_without_releasing_projection()
    {
        Assert.True(OperatingSystem.IsLinux());
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        using RookRuntimeScenario scenario = await Task.Run(() => new RookRuntimeScenario(stores, malformed: true), deadline.Token)
            .WaitAsync(deadline.Token);
        InstallLinkingRookReadConsent consent = await scenario.GrantAsync(deadline.Token).WaitAsync(deadline.Token);
        using InstallLinkingAuthoritativeEnvelope before = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        byte[] selected = File.ReadAllBytes(scenario.SnapshotPath);
        InstallLinkingOperationException failure = await Assert.ThrowsAsync<InstallLinkingOperationException>(
            () => Task.Run(() => scenario.ResolveAsync(consent, deadline.Token), deadline.Token).WaitAsync(deadline.Token));
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, failure.StatusCode);
        Assert.Equal("The selected Rook rule read is unavailable.", failure.Message);
        Assert.Null(failure.InnerException);
        Assert.Equal(2, scenario.Identity.Calls); // Grant + capture; no result reaches revalidation.
        using InstallLinkingAuthoritativeEnvelope after = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        AssertSameHead(before, after);
        Assert.Equal(selected, File.ReadAllBytes(scenario.SnapshotPath));
        scenario.AssertPrivateWorkCleanedAndInputsUnchanged();
    }

    [Fact]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_Core_read_canceled_before_capture_performs_no_identity_or_private_work()
    {
        Assert.True(OperatingSystem.IsLinux());
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        using RookRuntimeScenario scenario = await Task.Run(() => new RookRuntimeScenario(stores), deadline.Token)
            .WaitAsync(deadline.Token);
        InstallLinkingRookReadConsent consent = await scenario.GrantAsync(deadline.Token).WaitAsync(deadline.Token);
        using var canceled = new CancellationTokenSource();
        canceled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => scenario.ResolveAsync(consent, canceled.Token).WaitAsync(deadline.Token));
        Assert.Equal(1, scenario.Identity.Calls);
        scenario.AssertPrivateWorkCleanedAndInputsUnchanged();
    }

    [Fact]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_HTTP_owner_grants_reads_and_revokes_actual_Core_consent()
    {
        Assert.True(OperatingSystem.IsLinux());
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        // Do not abandon a synchronous constructor with Task.Run/WaitAsync: it
        // owns real file and database work until it returns or throws.
        using RookRuntimeScenario scenario = new(stores);
        await using RookRuntimeHttpHost host = await RookRuntimeHttpHost.StartAsync(scenario, stores.Root, deadline.Token);
        byte[] originalAccount = File.ReadAllBytes(scenario.AccountPath);
        byte[] originalSnapshot = File.ReadAllBytes(scenario.SnapshotPath);
        InstallLinkingRookReadConsent consent = await host.GrantAsync(scenario, deadline.Token);
        Assert.Equal(1, scenario.Identity.Calls);
        using (InstallLinkingAuthoritativeEnvelope before = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token))
        {
            RookHttpReadOnlyImage image = await CaptureRookHttpImageAsync(scenario);
            using HttpResponseMessage response = await host.ReadAsync(scenario, consent, deadline.Token);
            JsonElement body = await ReadRookHttpJsonAsync(response, scenario, deadline.Token);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            AssertResolvedRookHttpProjection(body, scenario);
            Assert.Equal(3, scenario.Identity.Calls);
            Assert.True(scenario.RuntimeClock.SawOwnedScratch);
            await AssertRookHttpReadOnlyAsync(scenario, before, image, deadline.Token);
        }

        using (HttpResponseMessage response = await host.SendAsync("consents/revoke",
            new { consentId = consent.ConsentId, expectedVersion = consent.Version }, deadline.Token))
        {
            JsonElement body = await ReadRookHttpJsonAsync(response, scenario, deadline.Token);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            AssertRookHttpConsentProjection(body, scenario.Reader.Store.RookReadConsentsById[consent.ConsentId]);
        }
        InstallLinkingRookReadConsent revoked = scenario.Reader.Store.RookReadConsentsById[consent.ConsentId];
        Assert.Equal(consent.Version + 1, revoked.Version);
        Assert.NotNull(revoked.RevokedAtUtc);
        Assert.Equal(4, scenario.Identity.Calls);
        using (InstallLinkingAuthoritativeEnvelope before = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token))
        {
            RookHttpReadOnlyImage image = await CaptureRookHttpImageAsync(scenario);
            // Even the current revoked version cannot become a fresh read grant.
            using HttpResponseMessage response = await host.ReadAsync(scenario, revoked, deadline.Token);
            JsonElement body = await ReadRookHttpJsonAsync(response, scenario, deadline.Token);
            Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
            AssertRookHttpFailure(body);
            Assert.Equal(5, scenario.Identity.Calls);
            await AssertRookHttpReadOnlyAsync(scenario, before, image, deadline.Token);
        }
        Assert.Equal(originalAccount, File.ReadAllBytes(scenario.AccountPath));
        Assert.Equal(originalSnapshot, File.ReadAllBytes(scenario.SnapshotPath));
    }

    [Theory]
    [InlineData("unchanged")]
    [InlineData("revoked_consent")]
    [InlineData("new_session")]
    [InlineData("expired_session")]
    [InlineData("snapshot_generation")]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_HTTP_releases_no_headers_before_fresh_revalidation_after_Core_disposal(string change)
    {
        Assert.True(OperatingSystem.IsLinux());
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var requestCancellation = CancellationTokenSource.CreateLinkedTokenSource(deadline.Token);
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        using RookRuntimeScenario scenario = new(stores);
        await using RookRuntimeHttpHost host = await RookRuntimeHttpHost.StartAsync(scenario, stores.Root, deadline.Token);
        InstallLinkingRookReadConsent consent = await host.GrantAsync(scenario, deadline.Token);
        using InstallLinkingAuthoritativeEnvelope granted = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        RookHttpReadOnlyImage grantedImage = await CaptureRookHttpImageAsync(scenario);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        scenario.Identity.BeforeResponse = async (call, ct) =>
        {
            if (call != 3) return;
            entered.TrySetResult();
            await release.Task.WaitAsync(ct);
        };
        Task<HttpResponseMessage> pending = host.ReadAsync(scenario, consent, requestCancellation.Token);
        try
        {
            await entered.Task.WaitAsync(deadline.Token);
            // ReadAsync uses ResponseHeadersRead: incompletion means no HTTP
            // headers escaped, not merely that the client is buffering a body.
            Assert.False(pending.IsCompleted);
            Assert.Equal(3, scenario.Identity.Calls);
            Assert.True(scenario.RuntimeClock.SawOwnedScratch);
            await AssertRookHttpReadOnlyAsync(scenario, granted, grantedImage, deadline.Token);

            if (change == "revoked_consent")
            {
                // Independent actual PostgreSQL writer, as in the service-level
                // fence test. The reader's still-active local mirror is unchanged.
                var writer = stores.OpenStore();
                InstallLinkingRookReadConsent revoked = writer.Service.RevokeRookReadConsent(
                    scenario.UserId, RookConsentPostgresStores.SubjectId, consent.ConsentId, consent.Version, deadline.Token);
                Assert.NotNull(revoked.RevokedAtUtc);
                Assert.Equal(grantedImage.Mirror, File.ReadAllBytes(scenario.Reader.Store.StoragePath));
                Assert.Equal(consent, scenario.Reader.Store.RookReadConsentsById[consent.ConsentId]);
            }
            else if (change == "snapshot_generation")
            {
                InstallLinkedWorkspaceSnapshotRecord changed = scenario.Snapshots.UpsertForInstallation(
                    scenario.Installation, scenario.Selected with { Name = "Explicit concurrent HTTP fixture update" },
                    scenario.Selected.RemoteRevision, scenario.Selected.ServerToken);
                Assert.Equal(scenario.Selected.RemoteRevision + 1, changed.RemoteRevision);
                Assert.Equal(scenario.Selected.WorkspaceContinuationDigest, changed.WorkspaceContinuationDigest);
            }
            else if (change == "new_session") scenario.Identity.SessionId = "another-active-http-owner-session";
            else if (change == "expired_session") scenario.Identity.ExpiresAtUtc = DateTimeOffset.UtcNow.AddSeconds(-1);

            using InstallLinkingAuthoritativeEnvelope beforeRelease = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
            RookHttpReadOnlyImage releaseImage = await CaptureRookHttpImageAsync(scenario);
            Assert.False(pending.IsCompleted);
            release.TrySetResult();
            using HttpResponseMessage response = await pending.WaitAsync(deadline.Token);
            JsonElement body = await ReadRookHttpJsonAsync(response, scenario, deadline.Token);
            if (change == "unchanged")
            {
                Assert.Equal(HttpStatusCode.OK, response.StatusCode);
                AssertResolvedRookHttpProjection(body, scenario);
            }
            else
            {
                Assert.Equal(change switch
                {
                    "expired_session" => HttpStatusCode.Unauthorized,
                    "snapshot_generation" => HttpStatusCode.Conflict,
                    _ => HttpStatusCode.Forbidden
                }, response.StatusCode);
                AssertRookHttpFailure(body);
            }
            Assert.Equal(3, scenario.Identity.Calls);
            Assert.Equal(grantedImage.Account, File.ReadAllBytes(scenario.AccountPath));
            await AssertRookHttpReadOnlyAsync(scenario, beforeRelease, releaseImage, deadline.Token);
        }
        finally
        {
            release.TrySetResult();
            requestCancellation.Cancel();
            // The cleanup bound is independent of the request's expired token.
            // Host shutdown subsequently drains server requests before stores close.
            try { using HttpResponseMessage drained = await pending.WaitAsync(TimeSpan.FromSeconds(5)); }
            catch (Exception) when (pending.IsFaulted || pending.IsCanceled) { }
        }
    }

    [Fact]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_HTTP_unsupported_intent_returns_actual_unbound_Core_result()
    {
        Assert.True(OperatingSystem.IsLinux());
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        using RookRuntimeScenario scenario = new(stores);
        await using RookRuntimeHttpHost host = await RookRuntimeHttpHost.StartAsync(scenario, stores.Root, deadline.Token);
        InstallLinkingRookReadConsent consent = await host.GrantAsync(scenario, deadline.Token);
        using InstallLinkingAuthoritativeEnvelope before = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        RookHttpReadOnlyImage image = await CaptureRookHttpImageAsync(scenario);
        using HttpResponseMessage response = await host.ReadAsync(scenario, consent, deadline.Token, "unsupported-read-intent");
        JsonElement body = await ReadRookHttpJsonAsync(response, scenario, deadline.Token);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        AssertRookHttpResultFields(body);
        Assert.Equal(WorkspaceRuleQuestionStatuses.Unresolved, body.GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, body.GetProperty("ruleContext").ValueKind);
        Assert.Equal(JsonValueKind.Null, body.GetProperty("level").ValueKind);
        Assert.Equal(JsonValueKind.Null, body.GetProperty("maximumLevel").ValueKind);
        Assert.Empty(body.GetProperty("sourceAnchors").EnumerateArray());
        Assert.Empty(body.GetProperty("explanation").GetProperty("sourceAnchorIds").EnumerateArray());
        Assert.Equal(3, scenario.Identity.Calls);
        Assert.True(scenario.RuntimeClock.SawOwnedScratch);
        await AssertRookHttpReadOnlyAsync(scenario, before, image, deadline.Token);
    }

    [Fact]
    [SupportedOSPlatform("linux")]
    public async Task Rook_private_HTTP_complete_invalid_character_returns_only_safe_unavailable()
    {
        Assert.True(OperatingSystem.IsLinux());
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await using RookConsentPostgresStores stores = await RookConsentPostgresStores.CreateAsync(_fixture);
        using RookRuntimeScenario scenario = new(stores, malformed: true);
        await using RookRuntimeHttpHost host = await RookRuntimeHttpHost.StartAsync(scenario, stores.Root, deadline.Token);
        InstallLinkingRookReadConsent consent = await host.GrantAsync(scenario, deadline.Token);
        using InstallLinkingAuthoritativeEnvelope before = await scenario.Reader.Authority.ReadCurrentAsync(deadline.Token);
        RookHttpReadOnlyImage image = await CaptureRookHttpImageAsync(scenario);
        using HttpResponseMessage response = await host.ReadAsync(scenario, consent, deadline.Token);
        JsonElement body = await ReadRookHttpJsonAsync(response, scenario, deadline.Token);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        AssertRookHttpFailure(body);
        Assert.Equal(2, scenario.Identity.Calls); // Grant and capture, no result to revalidate.
        await AssertRookHttpReadOnlyAsync(scenario, before, image, deadline.Token);
    }

    private sealed record RookHttpReadOnlyImage(byte[] Account, byte[] Snapshot, byte[] Mirror, long Commits);

    [SupportedOSPlatform("linux")]
    private async Task<RookHttpReadOnlyImage> CaptureRookHttpImageAsync(RookRuntimeScenario scenario)
        => new(File.ReadAllBytes(scenario.AccountPath), File.ReadAllBytes(scenario.SnapshotPath),
            File.ReadAllBytes(scenario.Reader.Store.StoragePath),
            await _fixture.ScalarLongAsync("SELECT COUNT(*) FROM install_linking.snapshot_commits"));

    [SupportedOSPlatform("linux")]
    private async Task AssertRookHttpReadOnlyAsync(RookRuntimeScenario scenario, InstallLinkingAuthoritativeEnvelope expected,
        RookHttpReadOnlyImage image, CancellationToken ct)
    {
        using InstallLinkingAuthoritativeEnvelope current = await scenario.Reader.Authority.ReadCurrentAsync(ct);
        AssertSameHead(expected, current);
        Assert.Equal(image.Commits, await _fixture.ScalarLongAsync("SELECT COUNT(*) FROM install_linking.snapshot_commits"));
        Assert.Equal(image.Account, File.ReadAllBytes(scenario.AccountPath));
        Assert.Equal(image.Snapshot, File.ReadAllBytes(scenario.SnapshotPath));
        Assert.Equal(image.Mirror, File.ReadAllBytes(scenario.Reader.Store.StoragePath));
        scenario.AssertPrivateWorkCleanedAndInputsUnchanged();
    }

    private static void AssertRookHttpResultFields(JsonElement body)
        => Assert.Equal(new[] { "explanation", "failureReason", "level", "maximumLevel", "ruleContext", "sourceAnchors", "status" },
            body.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToArray());

    [SupportedOSPlatform("linux")]
    private static void AssertResolvedRookHttpProjection(JsonElement body, RookRuntimeScenario scenario)
    {
        AssertRookHttpResultFields(body);
        Assert.Equal(WorkspaceRuleQuestionStatuses.Resolved, body.GetProperty("status").GetString());
        Assert.Equal(1, body.GetProperty("level").GetInt32());
        Assert.Equal(4, body.GetProperty("maximumLevel").GetInt32());
        Assert.Equal(JsonValueKind.Null, body.GetProperty("failureReason").ValueKind);
        JsonElement context = body.GetProperty("ruleContext");
        Assert.Equal(new[] { "contentRevision", "engineFingerprint", "engineIdentityKind", "executingModules", "intent", "locale",
            "rulesetId", "savedRevision", "settingsProfileId", "sourceNodeDigest", "sourceProfileDigest", "subjectId",
            "workspaceDocumentDigest", "workspaceId" },
            context.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToArray());
        Assert.Equal(scenario.Exported.Snapshot.Workspace.Id.Value, context.GetProperty("workspaceId").GetString());
        Assert.Equal("sr5", context.GetProperty("rulesetId").GetString());
        Assert.Equal(2, context.GetProperty("contentRevision").GetInt64());
        Assert.Equal(1, context.GetProperty("savedRevision").GetInt64());
        Assert.NotEqual(scenario.Selected.RemoteRevision, context.GetProperty("contentRevision").GetInt64());
        Assert.Equal(WorkspaceRuleQuestionIntents.QualityLevel, context.GetProperty("intent").GetString());
        Assert.Equal(RookRuntimeScenario.SavedQualityId, context.GetProperty("subjectId").GetString());
        Assert.Equal("en", context.GetProperty("locale").GetString());
        Assert.NotEmpty(context.GetProperty("executingModules").EnumerateArray());
        Assert.False(string.IsNullOrWhiteSpace(context.GetProperty("engineFingerprint").GetString()));
        JsonElement anchor = Assert.Single(body.GetProperty("sourceAnchors").EnumerateArray());
        Assert.Equal("HUBTEST", anchor.GetProperty("sourceBook").GetString());
        Assert.Equal(12, anchor.GetProperty("page").GetInt32());
        Assert.Equal(RookRuntimeScenario.QualitySourceId, anchor.GetProperty("qualitySourceId").GetString());
        Assert.NotEmpty(anchor.GetProperty("calculationTrace").EnumerateArray());
        Assert.Equal(context.GetProperty("sourceNodeDigest").GetString(), anchor.GetProperty("sourceNodeDigest").GetString());
        Assert.Equal(context.GetProperty("sourceProfileDigest").GetString(), anchor.GetProperty("sourceProfileDigest").GetString());
        Assert.Contains(anchor.GetProperty("anchorId").GetString(), body.GetProperty("explanation")
            .GetProperty("sourceAnchorIds").EnumerateArray().Select(item => item.GetString()));
    }

    private static void AssertRookHttpConsentProjection(JsonElement body, InstallLinkingRookReadConsent consent)
    {
        Assert.Equal(new[] { "consentId", "expiresAtUtc", "issuedAtUtc", "purpose", "revokedAtUtc", "version", "workspaceId" },
            body.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToArray());
        Assert.Equal(consent.ConsentId, body.GetProperty("consentId").GetString());
        Assert.Equal(consent.Version, body.GetProperty("version").GetInt64());
        Assert.Equal(consent.WorkspaceId, body.GetProperty("workspaceId").GetString());
        Assert.Equal(consent.Purpose, body.GetProperty("purpose").GetString());
        Assert.Equal(consent.IssuedAtUtc, body.GetProperty("issuedAtUtc").GetDateTimeOffset());
        Assert.Equal(consent.ExpiresAtUtc, body.GetProperty("expiresAtUtc").GetDateTimeOffset());
        Assert.Equal(consent.RevokedAtUtc, body.GetProperty("revokedAtUtc").ValueKind == JsonValueKind.Null
            ? (DateTimeOffset?)null : body.GetProperty("revokedAtUtc").GetDateTimeOffset());
    }

    private static void AssertRookHttpFailure(JsonElement body)
    {
        Assert.Equal(new[] { "error" }, body.EnumerateObject().Select(property => property.Name).ToArray());
        Assert.Equal("The private Rook workspace operation could not be completed.", body.GetProperty("error").GetString());
    }

    [SupportedOSPlatform("linux")]
    private static async Task<JsonElement> ReadRookHttpJsonAsync(HttpResponseMessage response, RookRuntimeScenario scenario,
        CancellationToken ct)
    {
        Assert.True(response.Headers.CacheControl?.NoStore);
        Assert.True(response.Headers.CacheControl?.Private);
        Assert.Equal("application/json", response.Content.Headers.ContentType?.MediaType);
        byte[] bytes = new byte[RookWorkspaceToolController.MaxResponseBytes + 1];
        int length = 0;
        using Stream stream = await response.Content.ReadAsStreamAsync(ct);
        while (length < bytes.Length)
        {
            int count = await stream.ReadAsync(bytes.AsMemory(length), ct);
            if (count == 0) break;
            length += count;
        }
        Assert.InRange(length, 1, RookWorkspaceToolController.MaxResponseBytes);
        string wire = Encoding.UTF8.GetString(bytes, 0, length);
        foreach (string forbidden in new[] { RookRuntimeScenario.PrivateNotes, scenario.Owner.Value, scenario.UserId,
            scenario.ExportIssuerId, scenario.Selected.ServerToken!, scenario.Selected.WorkspaceContinuationDigest!,
            "rook-runtime-test-session", "ownerId", "trustedLocalOwner", "ownerAuthorityInstanceId", "ownerTransitionRevision",
            "rawBinding", "resultDigest", "rawResultDigest", "workspaceContinuation", "continuationDigest", "serverToken", "carrier" })
            Assert.DoesNotContain(forbidden, wire, StringComparison.OrdinalIgnoreCase);
        using JsonDocument document = JsonDocument.Parse(bytes.AsMemory(0, length));
        return document.RootElement.Clone();
    }

    [SupportedOSPlatform("linux")]
    private sealed class RookRuntimeHttpHost(WebApplication application, HttpClient client) : IAsyncDisposable
    {
        private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

        public static async Task<RookRuntimeHttpHost> StartAsync(RookRuntimeScenario scenario, string root, CancellationToken ct)
        {
            WebApplication? app = null;
            try
            {
                var builder = WebApplication.CreateBuilder(new WebApplicationOptions
                {
                    EnvironmentName = Environments.Production, ContentRootPath = root
                });
                builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_ROOK_PRIVATE_RUNTIME_ENABLED"] = "true", ["CHUMMER_PUBLIC_DOWNLOAD_ONLY"] = "false"
                });
                builder.Logging.ClearProviders();
                builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
                builder.Services.AddControllers().AddApplicationPart(typeof(RookWorkspaceToolController).Assembly);
                // Actual PG/Core instances, not a substitute activation or green
                // authority. This test does not qualify Production host activation.
                scenario.RegisterHttpServices(builder.Services);
                app = builder.Build();
                app.MapControllers();
                using var startup = CancellationTokenSource.CreateLinkedTokenSource(ct);
                startup.CancelAfter(TimeSpan.FromSeconds(10));
                await app.StartAsync(startup.Token);
                IServerAddressesFeature addresses = app.Services.GetRequiredService<IServer>().Features
                    .Get<IServerAddressesFeature>() ?? throw new InvalidOperationException("No loopback test listener.");
                var client = new HttpClient(new HttpClientHandler { UseCookies = false, UseProxy = false, AllowAutoRedirect = false })
                {
                    BaseAddress = new Uri(Assert.Single(addresses.Addresses)), Timeout = TimeSpan.FromSeconds(10)
                };
                return new(app, client);
            }
            catch
            {
                if (app is not null) await app.DisposeAsync();
                throw;
            }
        }

        public async Task<InstallLinkingRookReadConsent> GrantAsync(RookRuntimeScenario scenario, CancellationToken ct)
        {
            using HttpResponseMessage response = await SendAsync("consents", new
            {
                installationId = scenario.Installation.InstallationId, grantId = scenario.Installation.GrantId,
                workspaceId = scenario.Selected.WorkspaceId, remoteRevision = scenario.Selected.RemoteRevision,
                serverToken = scenario.Selected.ServerToken, continuationDigest = scenario.Selected.WorkspaceContinuationDigest,
                explicitConfirmation = true, expiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(2)
            }, ct);
            JsonElement body = await ReadRookHttpJsonAsync(response, scenario, ct);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            InstallLinkingRookReadConsent consent = Assert.Single(scenario.Reader.Store.RookReadConsentsById).Value;
            AssertRookHttpConsentProjection(body, consent);
            return consent;
        }

        public Task<HttpResponseMessage> ReadAsync(RookRuntimeScenario scenario, InstallLinkingRookReadConsent consent,
            CancellationToken ct, string intent = WorkspaceRuleQuestionIntents.QualityLevel)
            => SendAsync("read", new
            {
                installationId = scenario.Installation.InstallationId, grantId = scenario.Installation.GrantId,
                consentId = consent.ConsentId, expectedVersion = consent.Version,
                intent, savedSubjectId = RookRuntimeScenario.SavedQualityId, locale = "en"
            }, ct);

        public async Task<HttpResponseMessage> SendAsync(string action, object body, CancellationToken ct)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, "/api/internal/rook/workspace/" + action)
            {
                Content = new StringContent(JsonSerializer.Serialize(body, Json), Encoding.UTF8, "application/json")
            };
            request.Headers.Authorization = new("Bearer", "rook-runtime-test-session");
            return await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        }

        public async ValueTask DisposeAsync()
        {
            client.Dispose();
            try
            {
                using var shutdown = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                await application.StopAsync(shutdown.Token);
            }
            finally { await application.DisposeAsync(); }
        }
    }

    [SupportedOSPlatform("linux")]
    private sealed class RookRuntimeScenario : IDisposable
    {
        public const string SavedQualityId = "42424242-1111-4111-8111-111111111111";
        public const string QualitySourceId = "42424242-2222-4222-8222-222222222222";
        public const string PrivateNotes = "PRIVATE-HUB-RUNTIME-NOTES-MUST-NOT-LEAVE-THE-CARRIER";
        private const string SettingsId = "42424242-3333-4333-8333-333333333333";
        private readonly HttpClient _http;
        private readonly RookWorkspaceReadAdmissionService _admission;
        private readonly RookWorkspaceRuleReadService _reads;
        private readonly string _coreRoot;
        private readonly Dictionary<string, byte[]> _coreInputs;
        private readonly string _scratch;
        private readonly HttpRequest _request;
        public (InstallLinkingStore Store, InstallLinkingService Service,
            NpgsqlInstallLinkingSnapshotAuthority Authority, string ApplicationName) Reader { get; }
        public string UserId { get; }
        public OwnerScope Owner { get; }
        public string ExportIssuerId { get; }
        public WorkspaceContinuationExport Exported { get; }
        public RookRuntimeIdentityTransport Identity { get; }
        public RookRuntimeClock RuntimeClock { get; }
        public ClaimedInstallationDto Installation { get; }
        public InstallLinkedWorkspaceSnapshotRecord Selected { get; }
        public InstallLinkedWorkspaceSnapshotService Snapshots { get; }
        public string SnapshotPath { get; }
        public string AccountPath { get; }

        public RookRuntimeScenario(RookConsentPostgresStores stores, bool malformed = false)
        {
            Reader = stores.OpenStore();
            SnapshotPath = Path.Combine(stores.Root, "rook-runtime-snapshots.json");
            AccountPath = Path.Combine(stores.Root, "rook-runtime-community.json");
            IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = "Testing",
                ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid",
                ["CHUMMER_COMMUNITY_STORE_PATH"] = AccountPath,
                ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = SnapshotPath
            }).Build();
            var accounts = new AccountService(new CommunityStore(configuration, NullLogger<CommunityStore>.Instance));
            var user = accounts.EnsureUser(RookConsentPostgresStores.SubjectId, "Runtime owner", "runtime@example.invalid");
            UserId = user.UserId;
            RookConsentPostgresStores.SeedInstallation(Reader.Store, UserId);
            Installation = Reader.Store.InstallationsById[RookConsentPostgresStores.InstallationId];
            Owner = new(InstallLinkedWorkspaceSnapshotTransfer.ComputeContinuationOwnerId(user.SubjectId));
            _coreRoot = Path.Combine(stores.Root, "core-fixture");
            string data = Path.Combine(_coreRoot, "data");
            Directory.CreateDirectory(data);
            // Synthetic fixture content, not sourcebook or production rule authority.
            // The actual packaged Core resolver interprets these ordinary source files.
            File.WriteAllText(Path.Combine(data, "settings.xml"), $"""
                <chummer><settings><setting><id>{SettingsId}</id><buildmethod>Priority</buildmethod>
                <buildpoints>25</buildpoints><books><book>SR5</book><book>HUBTEST</book></books>
                <customdatadirectorynames/></setting></settings></chummer>
                """);
            File.WriteAllText(Path.Combine(data, "books.xml"), """
                <chummer><books><book><code>SR5</code><name>Fixture base</name></book>
                <book><code>HUBTEST</code><name>Hub integration fixture</name></book></books></chummer>
                """);
            File.WriteAllText(Path.Combine(data, "qualities.xml"), $"""
                <chummer><qualities><quality><id>{QualitySourceId}</id><name>Hub fixture quality</name>
                <category>Positive</category><limit>4</limit><source>HUBTEST</source><page>12</page>
                </quality></qualities></chummer>
                """);
            File.WriteAllText(Path.Combine(data, "lifemodules.xml"),
                "<chummer><stages><stage order=\"0\">Nationality</stage></stages><modules/></chummer>");
            string xml = malformed ? "<character><notes>" + PrivateNotes : $"""
                <character><name>Hub rule fixture</name><alias>Before</alias><metatype>Human</metatype>
                <settings>{SettingsId}</settings><buildmethod>Priority</buildmethod><createdversion>5.225.0</createdversion>
                <appversion>5.225.0</appversion><created>False</created><karma>0</karma><nuyen>0</nuyen>
                <notes>{PrivateNotes}</notes><qualities><quality><guid>{SavedQualityId}</guid>
                <sourceid>{QualitySourceId}</sourceid><name>Hub fixture quality</name><qualitytype>Positive</qualitytype>
                <qualitysource>Selected</qualitysource><bp>0</bp><extra/><sourcename/><notes/>
                <source>SR5</source><page>999</page><bonus/></quality></qualities></character>
                """;
            var workspaceId = new CharacterWorkspaceId("hub-rook-runtime-selected");
            var envelope = new WorkspacePayloadEnvelope("sr5", Sr5WorkspaceCodec.SchemaVersion, Sr5WorkspaceCodec.Sr5PayloadKind, xml);
            var sourceStore = new FileWorkspaceStore(Path.Combine(_coreRoot, "original-workspaces"));
            using (var sourceOwner = new RequestOwnerContextAccessor(Owner))
            {
                ExportIssuerId = sourceOwner.Capture().AuthorityInstanceId;
                Assert.True(sourceStore.CreateWorkspaceDocument(Owner, workspaceId, new WorkspaceDocument(envelope)).Success);
                Assert.True(sourceStore.SaveCheckpoint(Owner, workspaceId, 1).Success);
                Assert.True(sourceStore.ReplaceWorkspaceDocument(Owner, workspaceId, 1,
                    new WorkspaceDocument(envelope with { Payload = xml.Replace("Before", "After", StringComparison.Ordinal) })).Success);
                var exported = new WorkspaceContinuationExportService(sourceStore, sourceOwner)
                    .Export(sourceOwner.Capture(), workspaceId);
                Assert.True(exported.Success, exported.Error);
                Exported = Assert.IsType<WorkspaceContinuationExport>(exported.Value);
            }
            WorkspaceDocumentSnapshot workspace = Exported.Snapshot.Workspace;
            Assert.Equal(2, workspace.ContentRevision);
            Assert.Equal(1, workspace.SavedRevision);
            using JsonDocument encoded = JsonDocument.Parse(WorkspaceContinuationCodec.Encode(
                Exported, InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes));
            var incoming = new InstallLinkedWorkspaceSnapshotRecord("", workspaceId.Value, workspace.Document.RulesetId,
                "NativeXml", workspace.Document.SchemaVersion, workspace.Document.PayloadKind, workspace.Document.Content,
                workspace.LastUpdatedUtc, Installation.InstallationId, "Hub rule fixture", null, null, null, null, null,
                0, 0, false, WorkspaceContinuation: encoded.RootElement.Clone(), WorkspaceContinuationDigest: Exported.SnapshotDigest);
            Selected = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(configuration))
                .UpsertForInstallation(Installation, incoming, 0);
            Assert.Equal(1, Selected.RemoteRevision);
            // Actual persisted carrier read through a fresh store, not a DTO-only fake.
            Snapshots = new(new InstallLinkedWorkspaceSnapshotStore(configuration));
            _scratch = Path.Combine(stores.Root, "private-rule-runtime");
            Directory.CreateDirectory(_scratch, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            File.WriteAllText(Path.Combine(_scratch, "unrelated-sentinel"), "keep");
            RuntimeClock = new(_scratch);
            var factory = new PrivateWorkspaceRuleRuntimeFactory(_scratch, _coreRoot, _coreRoot, null, RuntimeClock);
            Identity = new RookRuntimeIdentityTransport();
            _http = new(Identity);
            var sessions = new HubSessionAccountAdmissionService(_http, configuration, accounts, TimeProvider.System);
            _admission = new(sessions, accounts, Reader.Service, Snapshots, TimeProvider.System);
            _reads = new(_admission, factory);
            _request = new DefaultHttpContext().Request;
            _request.Headers.Authorization = "Bearer rook-runtime-test-session";
            _coreInputs = ReadCoreInputs();
        }

        public Task<InstallLinkingRookReadConsent> GrantAsync(CancellationToken ct) => _admission.GrantAsync(_request,
            Installation.InstallationId, Installation.GrantId!, Selected.WorkspaceId, Selected.RemoteRevision,
            Selected.ServerToken!, Selected.WorkspaceContinuationDigest!, true, DateTimeOffset.UtcNow.AddMinutes(2), ct);

        public void RegisterHttpServices(IServiceCollection services)
        {
            services.AddSingleton(_admission);
            services.AddSingleton(_reads);
        }

        public Task<WorkspaceRuleQuestionResult> ResolveAsync(InstallLinkingRookReadConsent consent, CancellationToken ct,
            string intent = WorkspaceRuleQuestionIntents.QualityLevel)
            => _reads.ResolveAsync(_request, Installation.InstallationId, Installation.GrantId!, consent.ConsentId,
                consent.Version, intent, SavedQualityId, "en", ct);

        public void AssertPrivateWorkCleanedAndInputsUnchanged()
        {
            Assert.Empty(Directory.GetDirectories(_scratch));
            Assert.Equal(new[] { Path.Combine(_scratch, "unrelated-sentinel") }, Directory.GetFiles(_scratch));
            Assert.Equal("keep", File.ReadAllText(Path.Combine(_scratch, "unrelated-sentinel")));
            Dictionary<string, byte[]> after = ReadCoreInputs();
            Assert.Equal(_coreInputs.Keys.OrderBy(path => path), after.Keys.OrderBy(path => path));
            foreach ((string path, byte[] bytes) in _coreInputs) Assert.Equal(bytes, after[path]);
        }

        private Dictionary<string, byte[]> ReadCoreInputs() => Directory.GetFiles(_coreRoot, "*", SearchOption.AllDirectories)
            .ToDictionary(path => Path.GetRelativePath(_coreRoot, path), File.ReadAllBytes, StringComparer.Ordinal);

        public void Dispose() => _http.Dispose(); // Outer owned fixture closes stores, role and exact temporary tree.
    }

    private sealed class RookRuntimeClock(string scratch) : TimeProvider
    {
        private int _sawOwnedScratch;
        public bool SawOwnedScratch => Volatile.Read(ref _sawOwnedScratch) != 0;

        public override DateTimeOffset GetUtcNow()
        {
            // Read-only observation at the genuine Core restore-receipt producer,
            // not a substituted factory, restore result, rule answer or filesystem.
            if (Directory.GetDirectories(scratch).Length == 1)
                Volatile.Write(ref _sawOwnedScratch, 1);
            return DateTimeOffset.UtcNow;
        }
    }

    private sealed class RookRuntimeIdentityTransport : HttpMessageHandler
    {
        private int _calls;
        public int Calls => Volatile.Read(ref _calls);
        public string SessionId { get; set; } = "rook-runtime-initial-session";
        public DateTimeOffset ExpiresAtUtc { get; set; } = DateTimeOffset.UtcNow.AddMinutes(10);
        public Func<int, CancellationToken, Task>? BeforeResponse { get; set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            int call = Interlocked.Increment(ref _calls);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://identity.example.invalid/api/v1/identity/introspect", request.RequestUri?.AbsoluteUri);
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
            IdentityIntrospectionRequest? input = JsonSerializer.Deserialize<IdentityIntrospectionRequest>(
                await request.Content!.ReadAsStringAsync(ct), options);
            Assert.Equal("rook-runtime-test-session", Assert.IsType<IdentityIntrospectionRequest>(input).AccessToken);
            if (BeforeResponse is { } before) await before(call, ct);
            ct.ThrowIfCancellationRequested();
            return new(HttpStatusCode.OK)
            {
                Content = new StringContent(JsonSerializer.Serialize(new IdentityIntrospectionResponse(true, SessionId,
                    RookConsentPostgresStores.SubjectId, ["player"], ExpiresAtUtc), options), Encoding.UTF8, "application/json")
            };
        }
    }

    private sealed class RookPostgresIdentityTransport(DateTimeOffset expiresAtUtc) : HttpMessageHandler
    {
        public const string Bearer = "rook-postgres-explicit-session-token";
        public const string InitialSessionId = "rook-postgres-initial-session";
        private int _calls;
        public int Calls => Volatile.Read(ref _calls);
        public string SessionId { get; set; } = InitialSessionId;
        public string SubjectId => RookConsentPostgresStores.SubjectId;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Interlocked.Increment(ref _calls);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://identity.example.invalid/api/v1/identity/introspect", request.RequestUri?.AbsoluteUri);
            IdentityIntrospectionRequest? input = JsonSerializer.Deserialize<IdentityIntrospectionRequest>(
                await request.Content!.ReadAsStringAsync(ct), new JsonSerializerOptions(JsonSerializerDefaults.Web));
            Assert.Equal(Bearer, Assert.IsType<IdentityIntrospectionRequest>(input).AccessToken);
            await Task.Yield();
            ct.ThrowIfCancellationRequested();
            string response = JsonSerializer.Serialize(new IdentityIntrospectionResponse(
                true, SessionId, SubjectId, ["player"], expiresAtUtc), new JsonSerializerOptions(JsonSerializerDefaults.Web));
            return new(HttpStatusCode.OK)
            {
                Content = new StringContent(response, Encoding.UTF8, "application/json")
            };
        }
    }

    private static InstallLinkingRookReadConsent GrantRookConsent(InstallLinkingService service)
        => service.GrantRookReadConsent(
            RookConsentPostgresStores.UserId, RookConsentPostgresStores.SubjectId,
            RookConsentPostgresStores.InstallationId, RookConsentPostgresStores.GrantId,
            RookConsentPostgresStores.WorkspaceId, RookConsentPostgresStores.RemoteRevision,
            RookConsentPostgresStores.ServerToken, RookConsentPostgresStores.ContinuationDigest,
            explicitConfirmation: true, expiresAtUtc: DateTimeOffset.UtcNow.AddMinutes(2),
            validateSelection: installation =>
            {
                Assert.Equal(RookConsentPostgresStores.InstallationId, installation.InstallationId);
                Assert.Equal(RookConsentPostgresStores.UserId, installation.UserId);
                Assert.Equal(RookConsentPostgresStores.SubjectId, installation.SubjectId);
                Assert.Equal(RookConsentPostgresStores.GrantId, installation.GrantId);
            });

    private static bool CaptureRookConsent(InstallLinkingService service,
        InstallLinkingRookReadConsent consent,
        Action<InstallLinkingRookReadConsent, ClaimedInstallationDto> capture,
        CancellationToken cancellationToken = default)
        => service.CaptureRookReadConsent(
            RookConsentPostgresStores.UserId, RookConsentPostgresStores.SubjectId,
            RookConsentPostgresStores.InstallationId, RookConsentPostgresStores.GrantId,
            consent.ConsentId, consent.Version, capture, cancellationToken);

    private static void AssertRookConsentSelection(InstallLinkingRookReadConsent expected,
        InstallLinkingRookReadConsent current, ClaimedInstallationDto installation)
    {
        Assert.Equal(expected, current);
        Assert.Equal(RookConsentPostgresStores.UserId, current.UserId);
        Assert.Equal(RookConsentPostgresStores.SubjectId, current.SubjectId);
        Assert.Equal(RookConsentPostgresStores.InstallationId, current.InstallationId);
        Assert.Equal(RookConsentPostgresStores.GrantId, current.GrantId);
        Assert.Equal(RookConsentPostgresStores.WorkspaceId, current.WorkspaceId);
        Assert.Equal(RookConsentPostgresStores.RemoteRevision, current.RemoteRevision);
        Assert.Equal(RookConsentPostgresStores.ServerToken, current.ServerToken);
        Assert.Equal(RookConsentPostgresStores.ContinuationDigest, current.ContinuationDigest);
        Assert.Equal(InstallLinkingRookReadConsent.RequiredPurpose, current.Purpose);
        Assert.Null(current.RevokedAtUtc);
        Assert.Equal(current.InstallationId, installation.InstallationId);
        Assert.Equal(current.GrantId, installation.GrantId);
        Assert.Equal(current.UserId, installation.UserId);
        Assert.Equal(current.SubjectId, installation.SubjectId);
    }

    private sealed class RookConsentPostgresStores : IAsyncDisposable
    {
        public const string UserId = "rook-postgres-user";
        public const string SubjectId = "rook-postgres-subject";
        public const string InstallationId = "rook-postgres-android";
        public const string GrantId = "rook-postgres-grant";
        public const string WorkspaceId = "rook-postgres-workspace";
        public const long RemoteRevision = 7;
        public static readonly string ServerToken = new('a', 64);
        public static readonly string ContinuationDigest = new('b', 64);

        private readonly InstallLinkingPostgresAuthorityFixture _fixture;
        private readonly string _root;
        private readonly string _role = $"install_link_runtime_{Guid.NewGuid():N}";
        private readonly string _password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        private readonly IDataProtectionProvider _provider;
        private readonly List<InstallLinkingStore> _stores = [];
        private readonly List<NpgsqlDataSource> _dataSources = [];
        private bool _roleCreated;

        public string Root => _root;

        private RookConsentPostgresStores(InstallLinkingPostgresAuthorityFixture fixture)
        {
            _fixture = fixture;
            _root = Directory.CreateTempSubdirectory("chummer-rook-consent-postgres-").FullName;
            _provider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
        }

        public static async Task<RookConsentPostgresStores> CreateAsync(
            InstallLinkingPostgresAuthorityFixture fixture)
        {
            await fixture.ResetAsync();
            var stores = new RookConsentPostgresStores(fixture);
            try
            {
                await fixture.CreateLoginRoleAsync(stores._role, stores._password);
                stores._roleCreated = true;
                await new InstallLinkingPostgresMigrator(fixture.AdminDataSource)
                    .GrantRuntimePrivilegesAsync(stores._role);
                return stores;
            }
            catch
            {
                await stores.DisposeAsync();
                throw;
            }
        }

        public (InstallLinkingStore Store, InstallLinkingService Service,
            NpgsqlInstallLinkingSnapshotAuthority Authority, string ApplicationName) OpenStore()
        {
            string applicationName = $"rook_consent_{Guid.NewGuid():N}";
            var connection = new NpgsqlConnectionStringBuilder(_fixture.ConnectionString)
            {
                Username = _role,
                Password = _password,
                ApplicationName = applicationName,
                Pooling = false
            };
            NpgsqlDataSource dataSource = NpgsqlDataSource.Create(connection.ConnectionString);
            _dataSources.Add(dataSource);
            var authority = new NpgsqlInstallLinkingSnapshotAuthority(
                dataSource, expectedRuntimeRole: _role);
            var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] =
                        Path.Combine(_root, applicationName, "install-linking-store.json"),
                    ["ASPNETCORE_ENVIRONMENT"] = "Testing"
                })
                .Build();
            var store = new InstallLinkingStore(configuration, _provider,
                NullLogger<InstallLinkingStore>.Instance, coordinator);
            _stores.Add(store);
            return (store, new InstallLinkingService(store, configuration), authority, applicationName);
        }

        public static void SeedInstallation(InstallLinkingStore store, string? ownerUserId = null)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            using RSA key = RSA.Create(2048);
            var installation = new ClaimedInstallationDto(
                InstallationId: InstallationId,
                ArtifactId: "android-play-app",
                Channel: "internal",
                Version: "0.1.0-preview.12",
                InstallAccessClass: InstallAccessClasses.AccountRequired,
                Status: ClaimedInstallationStates.Active,
                CreatedAtUtc: now.AddMinutes(-2),
                UpdatedAtUtc: now.AddMinutes(-1),
                UserId: ownerUserId ?? UserId,
                SubjectId: SubjectId,
                PublicKey: Convert.ToBase64String(key.ExportSubjectPublicKeyInfo()),
                ClaimTicketId: null,
                HeadId: "android",
                Platform: "android",
                Arch: "arm64",
                HostLabel: "PostgreSQL consent test",
                GrantId: GrantId);
            var grant = new InstallationGrantDto(
                GrantId, InstallationId, InstallationGrantStates.Active,
                "rook-postgres-installation-token", now.AddMinutes(-1), now.AddHours(1),
                ownerUserId ?? UserId, SubjectId);
            lock (store.Gate)
            {
                store.InstallationsById[InstallationId] = installation;
                store.GrantsById[GrantId] = grant;
                store.GrantTransportAuthoritiesByGrantId[GrantId] =
                    new InstallationGrantTransportAuthority(GrantId, InstallationGrantTransports.AndroidLinkedV2);
                store.PersistLocked();
            }
        }

        public async ValueTask DisposeAsync()
        {
            try
            {
                foreach (InstallLinkingStore store in _stores)
                {
                    store.Dispose();
                }

                foreach (NpgsqlDataSource dataSource in _dataSources)
                {
                    await dataSource.DisposeAsync();
                }
            }
            finally
            {
                try
                {
                    if (_roleCreated)
                    {
                        await _fixture.DropRoleAsync(_role);
                    }
                }
                finally
                {
                    (_provider as IDisposable)?.Dispose();
                    Directory.Delete(_root, recursive: true);
                }
            }
        }
    }

    private NpgsqlDataSource CreateNamedDataSource(string applicationName)
    {
        var builder = new NpgsqlConnectionStringBuilder(_fixture.ConnectionString)
        {
            ApplicationName = applicationName,
            Pooling = false
        };
        return NpgsqlDataSource.Create(builder.ConnectionString);
    }

    private async Task AssertDatabaseBlockedByAsync(string waitingApplication, string blockingApplication)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        await using NpgsqlConnection observer =
            await _fixture.AdminDataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlCommand command = observer.CreateCommand();
        command.CommandText = """
            SELECT EXISTS (
                SELECT 1
                FROM pg_stat_activity AS waiter
                JOIN pg_stat_activity AS blocker
                  ON blocker.pid = ANY(pg_blocking_pids(waiter.pid))
                WHERE waiter.application_name = @waiting
                  AND blocker.application_name = @blocking
                  AND waiter.wait_event_type = 'Lock'
                  AND waiter.pid <> blocker.pid)
            """;
        command.Parameters.AddWithValue("waiting", waitingApplication);
        command.Parameters.AddWithValue("blocking", blockingApplication);
        try
        {
            while (!Convert.ToBoolean(await command.ExecuteScalarAsync(deadline.Token)))
            {
                await Task.Delay(TimeSpan.FromMilliseconds(20), deadline.Token);
            }
        }
        catch (OperationCanceledException)
        {
            Assert.Fail("PostgreSQL did not report the expected distinct waiting/blocking backends within three seconds.");
        }
    }

    private static InstallLinkingEnvelopeCompareExchangeRequest RequestAfter(
        InstallLinkingEnvelopeCompareExchangeRequest parent,
        string value)
    {
        InstallLinkingEnvelopeCompareExchangeRequest next = RequestForEmptyHead(value);
        return next with
        {
            ExpectedGeneration = parent.NextGeneration,
            ExpectedCommitId = parent.CommitId,
            ExpectedEnvelopeSha256 = parent.EnvelopeSha256.ToArray(),
            NextGeneration = parent.NextGeneration + 1
        };
    }

    private static void AssertCleared(InstallLinkingAuthoritativeEnvelope? envelope)
    {
        Assert.NotNull(envelope);
        Assert.NotNull(envelope.SnapshotSha256);
        Assert.NotNull(envelope.EnvelopeSha256);
        Assert.NotNull(envelope.ProtectedEnvelope);
        Assert.All(envelope.SnapshotSha256, value => Assert.Equal((byte)0, value));
        Assert.All(envelope.EnvelopeSha256, value => Assert.Equal((byte)0, value));
        Assert.All(envelope.ProtectedEnvelope, value => Assert.Equal((byte)0, value));
    }

    private static void AssertSameHead(
        InstallLinkingAuthoritativeEnvelope expected,
        InstallLinkingAuthoritativeEnvelope actual)
    {
        Assert.Equal(expected.Generation, actual.Generation);
        Assert.Equal(expected.CommitId, actual.CommitId);
        Assert.Equal(expected.EnvelopeVersion, actual.EnvelopeVersion);
        Assert.Equal(expected.SnapshotSha256, actual.SnapshotSha256);
        Assert.Equal(expected.EnvelopeSha256, actual.EnvelopeSha256);
        Assert.Equal(expected.ProtectedEnvelope, actual.ProtectedEnvelope);
        Assert.Equal(expected.UpdatedAtUtc, actual.UpdatedAtUtc);
    }

    private sealed class NonPumpingSynchronizationContext : SynchronizationContext
    {
        private int _postCount;

        public int PostCount => Volatile.Read(ref _postCount);

        public override void Post(SendOrPostCallback callback, object? state)
        {
            Interlocked.Increment(ref _postCount);
            // Intentionally never dispatch: a sync coordinator cannot depend on this queue.
        }
    }

    private sealed class PausedCommitUnitOfWorkFactory : IInstallLinkingPostgresUnitOfWorkFactory
    {
        private readonly NpgsqlInstallLinkingPostgresUnitOfWorkFactory _inner;

        public PausedCommitUnitOfWorkFactory(NpgsqlDataSource dataSource)
        {
            _inner = new(dataSource);
        }

        public TaskCompletionSource BeforeCommit { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public async ValueTask<IInstallLinkingPostgresUnitOfWork> BeginAsync(CancellationToken cancellationToken)
            => new PausedCommitUnitOfWork(await _inner.BeginAsync(cancellationToken), this);

        private sealed class PausedCommitUnitOfWork(
            IInstallLinkingPostgresUnitOfWork inner,
            PausedCommitUnitOfWorkFactory owner) : IInstallLinkingPostgresUnitOfWork
        {
            public NpgsqlConnection Connection => inner.Connection;
            public NpgsqlTransaction Transaction => inner.Transaction;

            public async Task CommitAsync(CancellationToken cancellationToken)
            {
                // All real CAS commands already ran on this independent real transaction.
                owner.BeforeCommit.TrySetResult();
                await owner.Release.Task.WaitAsync(TimeSpan.FromSeconds(15), cancellationToken);
                await inner.CommitAsync(cancellationToken);
            }

            public Task RollbackAsync(CancellationToken cancellationToken)
                => inner.RollbackAsync(cancellationToken);

            public ValueTask DisposeAsync() => inner.DisposeAsync();
        }
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
            .WithName($"chummer-read-fence-tests-{Guid.NewGuid():N}")
            .WithDatabase("chummer_install_linking")
            .WithUsername("postgres")
            .WithPassword(password)
            .WithCreateParameterModifier(parameters =>
            {
                HostConfig hostConfig = parameters.HostConfig
                    ?? throw new InvalidOperationException("The PostgreSQL test host configuration is missing.");
                // Replace the module's default wildcard publication, do not add another binding.
                hostConfig.PortBindings = new Dictionary<string, IList<PortBinding>>
                {
                    ["5432/tcp"] = new[]
                    {
                        new PortBinding { HostIP = "127.0.0.1", HostPort = string.Empty }
                    }
                };
                hostConfig.NanoCPUs = 1_000_000_000L;
                hostConfig.Memory = 512L * 1024 * 1024;
                hostConfig.MemorySwap = hostConfig.Memory;
                hostConfig.PidsLimit = 128;
            })
            .Build();
    }

    public NpgsqlDataSource AdminDataSource { get; private set; } = null!;
    public string ConnectionString => _container.GetConnectionString();

    public async Task InitializeAsync()
    {
        try
        {
            await _container.StartAsync();
            AdminDataSource = NpgsqlDataSource.Create(ConnectionString);
            await new InstallLinkingPostgresMigrator(AdminDataSource).MigrateAsync();
        }
        catch
        {
            // Do not depend on the test framework invoking fixture disposal after
            // initialization fails, especially when the external reaper is disabled.
            await DisposeAsync();
            throw;
        }
    }

    public async Task DisposeAsync()
    {
        try
        {
            if (AdminDataSource is not null)
            {
                await AdminDataSource.DisposeAsync();
            }
        }
        finally
        {
            await _container.DisposeAsync();
        }
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
