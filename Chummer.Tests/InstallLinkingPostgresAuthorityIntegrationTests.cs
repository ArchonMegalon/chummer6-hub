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
            Assert.Equal("runtime_privileges_invalid", readiness.Code);
        }
        finally
        {
            await _fixture.DropRoleAsync(role);
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
