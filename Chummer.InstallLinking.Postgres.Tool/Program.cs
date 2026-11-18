using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Npgsql;

if (!HasValidArguments(args))
{
    Console.Error.WriteLine(
        "Usage: Chummer.InstallLinking.Postgres.Tool "
        + "<migrate|validate|grant-runtime|prepare> [runtime-role], "
        + "transport-proof, prove-authority-ready [runtime-role], "
        + "prove-empty-authority [runtime-role], "
        + "prove-runtime-role [runtime-role], prove-local-store-state, "
        + "prove-local-store-absent, preflight-local-recovery, "
        + "prove-local-import-acknowledged, "
        + "or import-local --confirm-empty-authority");
    return 64;
}

if (args[0] == "preflight-local-recovery")
{
    return PreflightLocalRecovery();
}

if (args[0] == "prove-local-import-acknowledged")
{
    return await ProveLocalImportAcknowledgedAsync();
}

if (args[0] == "import-local")
{
    return await ImportLocalAsync();
}

if (args[0] == "prove-local-store-absent")
{
    return ProveLocalStoreAbsent();
}

if (args[0] == "prove-local-store-state")
{
    return ProveLocalStoreState();
}

string? runtimeRole = null;
if (args[0] is "grant-runtime"
        or "prepare"
        or "prove-authority-ready"
        or "prove-empty-authority"
        or "prove-runtime-role"
    && !InstallLinkingPostgresToolArguments.TryResolveRuntimeRole(
        args,
        Environment.GetEnvironmentVariable,
        out runtimeRole))
{
    Console.Error.WriteLine(
        "The InstallLinking PostgreSQL runtime role is unavailable or invalid.");
    return 78;
}

if (args[0] is "prove-authority-ready"
        or "prove-empty-authority"
        or "prove-runtime-role")
{
    return await ProveRuntimeAuthorityAsync(args[0], runtimeRole!);
}

string migratorConnectionString;
try
{
    migratorConnectionString = InstallLinkingPostgresConnectionConfiguration
        .LoadMigratorConnectionStringFromEnvironment();
}
catch (Exception exception) when (
    exception is InvalidOperationException
        or InvalidDataException
        or IOException
        or UnauthorizedAccessException
        or PlatformNotSupportedException)
{
    Console.Error.WriteLine(
        "The owner-only InstallLinking PostgreSQL migrator credential file is unavailable or invalid.");
    return 78;
}

await using NpgsqlDataSource migratorDataSource =
    NpgsqlDataSource.Create(migratorConnectionString);
var migrator = new InstallLinkingPostgresMigrator(migratorDataSource);
try
{
    switch (args[0])
    {
        case "migrate":
            await migrator.MigrateAsync();
            Console.WriteLine(
                $"install_linking schema migrated to version {InstallLinkingPostgresSchema.CurrentVersion}.");
            return 0;
        case "validate":
        {
            InstallLinkingPostgresSchemaValidation validation =
                await migrator.ValidateAsync();
            if (validation.Valid)
            {
                string authorityIdentitySha256 =
                    await ReadAuthorityIdentitySha256Async(
                        migratorDataSource);
                WriteCanonicalJson(
                    new SortedDictionary<string, object?>(StringComparer.Ordinal)
                    {
                        ["appliedSchemaVersion"] = validation.AppliedVersion,
                        ["authorityIdentitySha256"] =
                            authorityIdentitySha256,
                        ["contractName"] =
                            "chummer.install_linking_postgres_schema_validation.v1",
                        ["status"] = "pass"
                    });
                return 0;
            }

            Console.Error.WriteLine(
                $"install_linking schema validation failed: {string.Join(',', validation.Problems)}");
            return 1;
        }
        case "grant-runtime":
            await migrator.GrantRuntimePrivilegesAsync(runtimeRole!);
            if (!await migrator.ValidateRuntimePrivilegesAsync(runtimeRole!))
            {
                Console.Error.WriteLine(
                    "install_linking runtime privilege validation failed.");
                return 1;
            }

            Console.WriteLine(
                "install_linking least-privilege runtime grants validated.");
            return 0;
        case "prepare":
            await migrator.MigrateAsync();
            await migrator.GrantRuntimePrivilegesAsync(runtimeRole!);
            InstallLinkingPostgresSchemaValidation prepared =
                await migrator.ValidateAsync();
            if (!prepared.Valid
                || !await migrator.ValidateRuntimePrivilegesAsync(runtimeRole!))
            {
                Console.Error.WriteLine(
                    "install_linking schema or runtime privilege validation failed.");
                return 1;
            }

            WriteCanonicalJson(
                new SortedDictionary<string, object?>(StringComparer.Ordinal)
                {
                    ["appliedSchemaVersion"] = prepared.AppliedVersion,
                    ["authorityIdentitySha256"] =
                        await ReadAuthorityIdentitySha256Async(
                            migratorDataSource),
                    ["contractName"] =
                        "chummer.install_linking_postgres_prepare.v1",
                    ["leastPrivilegeValid"] = true,
                    ["runtimeRoleSha256"] =
                        ComputeRuntimeRoleSha256(runtimeRole!),
                    ["status"] = "pass"
                });
            return 0;
        case "transport-proof":
            return await VerifyTransportAsync(
                migratorDataSource,
                migratorConnectionString);
        default:
            return 64;
    }
}
catch (Exception exception) when (
    exception is NpgsqlException
        or InvalidOperationException
        or ArgumentException)
{
    Console.Error.WriteLine(
        $"install_linking migration command failed ({exception.GetType().Name}).");
    return 1;
}

static bool HasValidArguments(string[] values)
    => values switch
    {
        ["migrate" or "validate"] => true,
        ["transport-proof"] => true,
        ["prove-local-store-state"] => true,
        ["prove-local-store-absent"] => true,
        ["preflight-local-recovery"] => true,
        ["prove-local-import-acknowledged"] => true,
        ["grant-runtime" or "prepare"] => true,
        ["grant-runtime" or "prepare", _] => true,
        ["prove-authority-ready" or "prove-empty-authority" or "prove-runtime-role"] => true,
        ["prove-authority-ready" or "prove-empty-authority" or "prove-runtime-role", _] => true,
        ["import-local", "--confirm-empty-authority"] => true,
        _ => false
    };

static int PreflightLocalRecovery()
{
    try
    {
        IConfiguration configuration = RecoveryConfiguration();
        var environment = new ImportHostEnvironment();
        using ServiceProvider services = BuildRecoveryDataProtection(
            configuration,
            environment);
        string storagePath = InstallLinkingStore.ResolveStoragePath(configuration);
        if (!string.Equals(
                storagePath,
                InstallLinkingLocalStoreAbsenceProof.CanonicalStorePath,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "The InstallLinking local recovery preflight requires the canonical state path.");
        }

        InstallLinkingLocalRecoveryPreflightProof proof =
            InstallLinkingLocalRecoveryInspector.Inspect(
                storagePath,
                services.GetRequiredService<IDataProtectionProvider>());
        WriteCanonicalJson(
            new SortedDictionary<string, object?>(StringComparer.Ordinal)
            {
                ["contractName"] =
                    "chummer.install_linking_local_recovery_preflight.v1",
                ["dataProtectionReady"] = true,
                ["floorGeneration"] = proof.FloorGeneration,
                ["floorPresent"] = proof.FloorPresent,
                ["floorSnapshotSha256"] = proof.FloorSnapshotSha256,
                ["intentPresent"] = proof.IntentPresent,
                ["intentSha256"] = proof.IntentSha256,
                ["intentState"] = proof.IntentState,
                ["localStorePresent"] = true,
                ["retainedSnapshotSha256"] = proof.RetainedSnapshotSha256,
                ["sourceEnvelopeSha256"] = proof.SourceEnvelopeSha256,
                ["sourceGeneration"] = proof.SourceGeneration,
                ["sourceSnapshotSha256"] = proof.SourceSnapshotSha256,
                ["status"] = "pass"
            });
        return 0;
    }
    catch (Exception exception) when (exception is
        InvalidOperationException or InvalidDataException or CryptographicException
        or IOException or UnauthorizedAccessException or JsonException
        or FormatException or NotSupportedException)
    {
        Console.Error.WriteLine(
            $"InstallLinking local recovery preflight failed ({exception.GetType().Name}).");
        return 1;
    }
}

static async Task<int> ProveLocalImportAcknowledgedAsync()
{
    try
    {
        IConfiguration configuration = RecoveryConfiguration();
        var environment = new ImportHostEnvironment();
        using ServiceProvider services = BuildRecoveryDataProtection(
            configuration,
            environment);
        string storagePath = InstallLinkingStore.ResolveStoragePath(configuration);
        if (!string.Equals(
                storagePath,
                InstallLinkingLocalStoreAbsenceProof.CanonicalStorePath,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "The InstallLinking local recovery acknowledgement requires the canonical state path.");
        }

        string runtimeConnectionString =
            InstallLinkingPostgresConnectionConfiguration
                .LoadRuntimeConnectionString(configuration, environment);
        await using NpgsqlDataSource dataSource =
            NpgsqlDataSource.Create(runtimeConnectionString);
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(dataSource);
        using InstallLinkingAuthoritativeEnvelope envelope =
            await authority.ReadCurrentAsync();
        InstallLinkingLocalRecoveryAcknowledgementProof proof =
            InstallLinkingLocalRecoveryInspector.ProveAcknowledged(
                storagePath,
                services.GetRequiredService<IDataProtectionProvider>(),
                envelope);
        await using NpgsqlConnection connection = await dataSource.OpenConnectionAsync();
        string authorityIdentitySha256 =
            await InstallLinkingPostgresAuthorityIdentity.ComputeSha256Async(connection);
        WriteCanonicalJson(
            new SortedDictionary<string, object?>(StringComparer.Ordinal)
            {
                ["authorityIdentitySha256"] = authorityIdentitySha256,
                ["contractName"] =
                    "chummer.install_linking_local_recovery_acknowledgement.v1",
                ["envelopeSha256"] = proof.EnvelopeSha256,
                ["floorSnapshotSha256"] = proof.FloorSnapshotSha256,
                ["generation"] = proof.Generation,
                ["localAcknowledged"] = true,
                ["localStoreSha256"] = proof.LocalStoreSha256,
                ["snapshotSha256"] = proof.SnapshotSha256,
                ["status"] = "pass"
            });
        return 0;
    }
    catch (Exception exception) when (exception is
        NpgsqlException or InvalidOperationException or InvalidDataException
        or CryptographicException or IOException or UnauthorizedAccessException
        or JsonException or FormatException or NotSupportedException)
    {
        Console.Error.WriteLine(
            $"InstallLinking local recovery acknowledgement failed ({exception.GetType().Name}).");
        return 1;
    }
}

static IConfiguration RecoveryConfiguration()
    => new ConfigurationBuilder()
        .AddEnvironmentVariables()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["ASPNETCORE_ENVIRONMENT"] = Environments.Production
        })
        .Build();

static ServiceProvider BuildRecoveryDataProtection(
    IConfiguration configuration,
    IHostEnvironment environment)
{
    if (string.IsNullOrWhiteSpace(
            configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]))
    {
        throw new InvalidOperationException(
            "The recovery probe requires an explicit data-protection key-ring path.");
    }

    var services = new ServiceCollection();
    string keyRingPath = HubRuntimePathDefaults.ResolveDataProtectionKeysPath(
        configuration,
        environment);
    DataProtectionKeyProtectionStatus protection =
        DataProtectionKeyProtectionConfigurator.Configure(
            services,
            configuration,
            environment,
            keyRingPath);
    if (!protection.Ready)
    {
        throw new CryptographicException(
            "The recovery probe could not open the encrypted data-protection key ring.");
    }

    return services.BuildServiceProvider();
}

static async Task<int> ProveRuntimeAuthorityAsync(
    string command,
    string runtimeRole)
{
    IConfiguration configuration = new ConfigurationBuilder()
        .AddEnvironmentVariables()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["ASPNETCORE_ENVIRONMENT"] = Environments.Production
        })
        .Build();
    string runtimeConnectionString;
    try
    {
        runtimeConnectionString = InstallLinkingPostgresConnectionConfiguration
            .LoadRuntimeConnectionString(
                configuration,
                new ImportHostEnvironment());
    }
    catch (Exception exception) when (
        exception is InvalidOperationException
            or InvalidDataException
            or IOException
            or UnauthorizedAccessException
            or PlatformNotSupportedException)
    {
        Console.Error.WriteLine(
            "The owner-only InstallLinking PostgreSQL runtime credential file is unavailable or invalid.");
        return 78;
    }

    await using NpgsqlDataSource runtimeDataSource =
        NpgsqlDataSource.Create(runtimeConnectionString);
    var migrator = new InstallLinkingPostgresMigrator(runtimeDataSource);
    try
    {
        string roleSha256 = ComputeRuntimeRoleSha256(runtimeRole);
        if (command == "prove-runtime-role")
        {
            InstallLinkingPostgresRuntimeRoleProof proof =
                await migrator.ProveCurrentRuntimeRoleAsync(runtimeRole);
            if (!proof.Valid)
            {
                Console.Error.WriteLine(
                    "InstallLinking PostgreSQL runtime-role proof failed.");
                return 1;
            }

            WriteCanonicalJson(
                new SortedDictionary<string, object?>(StringComparer.Ordinal)
                {
                    ["contractName"] =
                        "chummer.install_linking_postgres_runtime_role_proof.v1",
                    ["authorityIdentitySha256"] =
                        proof.AuthorityIdentitySha256,
                    ["currentRoleMatches"] = proof.CurrentRoleMatches,
                    ["leastPrivilegeValid"] = proof.LeastPrivilegeValid,
                    ["runtimeRoleSha256"] = roleSha256,
                    ["status"] = "pass"
                });
            return 0;
        }

        if (command == "prove-authority-ready")
        {
            InstallLinkingPostgresAuthorityReadyProof proof =
                await migrator.ProveRuntimeAuthorityReadyAsync(runtimeRole);
            if (!proof.Valid)
            {
                Console.Error.WriteLine(
                    "InstallLinking PostgreSQL authority-readiness proof failed.");
                return 1;
            }

            WriteCanonicalJson(
                new SortedDictionary<string, object?>(StringComparer.Ordinal)
                {
                    ["appliedSchemaVersion"] = proof.AppliedSchemaVersion,
                    ["authorityIdentitySha256"] =
                        proof.AuthorityIdentitySha256,
                    ["authorityStateSha256"] = proof.AuthorityStateSha256,
                    ["commitCount"] = proof.CommitCount,
                    ["contractName"] =
                        "chummer.install_linking_postgres_authority_readiness_proof.v1",
                    ["currentRoleMatches"] = proof.CurrentRoleMatches,
                    ["empty"] = proof.Empty,
                    ["headGeneration"] = proof.HeadGeneration,
                    ["leastPrivilegeValid"] = proof.LeastPrivilegeValid,
                    ["runtimeRoleSha256"] = roleSha256,
                    ["schemaValid"] = proof.SchemaValid,
                    ["status"] = "pass"
                });
            return 0;
        }

        InstallLinkingPostgresEmptyAuthorityProof emptyProof =
            await migrator.ProveEmptyRuntimeAuthorityAsync(runtimeRole);
        if (!emptyProof.Valid)
        {
            Console.Error.WriteLine(
                "InstallLinking PostgreSQL empty-authority proof failed.");
            return 1;
        }

        WriteCanonicalJson(
            new SortedDictionary<string, object?>(StringComparer.Ordinal)
            {
                ["appliedSchemaVersion"] = emptyProof.AppliedSchemaVersion,
                ["authorityIdentitySha256"] =
                    emptyProof.AuthorityIdentitySha256,
                ["commitCount"] = emptyProof.CommitCount,
                ["contractName"] =
                    "chummer.install_linking_postgres_empty_authority_proof.v1",
                ["currentRoleMatches"] = emptyProof.CurrentRoleMatches,
                ["empty"] = emptyProof.Empty,
                ["headGeneration"] = emptyProof.HeadGeneration,
                ["leastPrivilegeValid"] = emptyProof.LeastPrivilegeValid,
                ["runtimeRoleSha256"] = roleSha256,
                ["schemaValid"] = emptyProof.SchemaValid,
                ["status"] = "pass"
            });
        return 0;
    }
    catch (Exception exception) when (
        exception is NpgsqlException
            or InvalidOperationException
            or ArgumentException
            or TimeoutException)
    {
        Console.Error.WriteLine(
            $"InstallLinking PostgreSQL runtime proof failed ({exception.GetType().Name}).");
        return 1;
    }
}

static int ProveLocalStoreAbsent()
{
    try
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddEnvironmentVariables()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = Environments.Production
            })
            .Build();
        string storagePath = InstallLinkingStore.ResolveStoragePath(configuration);
        if (!string.Equals(
                storagePath,
                InstallLinkingLocalStoreAbsenceProof.CanonicalStorePath,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "InstallLinking local-store absence proof requires the canonical state path.");
        }

        string[] paths =
        [
            storagePath,
            $"{storagePath}.floor",
            $"{storagePath}.postgres-import.intent"
        ];
        foreach (string path in paths)
        {
            if (InstallLinkingLocalStoreAbsenceProof
                .HasRetainedEntryOrUnsafeAncestor(path))
            {
                Console.Error.WriteLine(
                    "InstallLinking local-store absence proof found retained state.");
                return 1;
            }
        }

        WriteCanonicalJson(
            new SortedDictionary<string, object?>(StringComparer.Ordinal)
            {
                ["checkedPathCount"] = paths.Length,
                ["contractName"] =
                    "chummer.install_linking_local_store_absence_proof.v1",
                ["localStorePresent"] = false,
                ["status"] = "pass"
            });
        return 0;
    }
    catch (Exception exception) when (
        exception is InvalidOperationException
            or ArgumentException
            or IOException
            or UnauthorizedAccessException
            or NotSupportedException)
    {
        Console.Error.WriteLine(
            $"InstallLinking local-store absence proof failed ({exception.GetType().Name}).");
        return 1;
    }
}

static int ProveLocalStoreState()
{
    try
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddEnvironmentVariables()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = Environments.Production
            })
            .Build();
        string storagePath = InstallLinkingStore.ResolveStoragePath(configuration);
        if (!string.Equals(
                storagePath,
                InstallLinkingLocalStoreAbsenceProof.CanonicalStorePath,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "InstallLinking local-store state proof requires the canonical state path.");
        }

        string[] paths =
        [
            storagePath,
            $"{storagePath}.floor",
            $"{storagePath}.postgres-import.intent"
        ];
        int presentPathCount = 0;
        foreach (string path in paths)
        {
            InstallLinkingLocalStoreEntryState state =
                InstallLinkingLocalStoreAbsenceProof
                    .InspectRetainedEntry(path);
            if (state == InstallLinkingLocalStoreEntryState.Unsafe)
            {
                Console.Error.WriteLine(
                    "InstallLinking local-store state proof found an unsafe path.");
                return 1;
            }

            if (state == InstallLinkingLocalStoreEntryState.Present)
            {
                presentPathCount++;
            }
        }

        WriteCanonicalJson(
            new SortedDictionary<string, object?>(StringComparer.Ordinal)
            {
                ["checkedPathCount"] = paths.Length,
                ["contractName"] =
                    "chummer.install_linking_local_store_state_proof.v1",
                ["localStorePresent"] = presentPathCount > 0,
                ["presentPathCount"] = presentPathCount,
                ["status"] = "pass"
            });
        return 0;
    }
    catch (Exception exception) when (
        exception is InvalidOperationException
            or ArgumentException
            or IOException
            or UnauthorizedAccessException
            or NotSupportedException)
    {
        Console.Error.WriteLine(
            $"InstallLinking local-store state proof failed ({exception.GetType().Name}).");
        return 1;
    }
}

static void WriteCanonicalJson(
    SortedDictionary<string, object?> payload)
{
    Console.Out.Write(
        JsonSerializer.Serialize(
            payload,
            new JsonSerializerOptions
            {
                IndentCharacter = ' ',
                IndentSize = 2,
                NewLine = "\n",
                WriteIndented = true
            }));
    Console.Out.Write('\n');
}

static string ComputeRuntimeRoleSha256(string runtimeRole)
    => Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(runtimeRole)))
        .ToLowerInvariant();

static async Task<string> ReadAuthorityIdentitySha256Async(
    NpgsqlDataSource dataSource)
{
    await using NpgsqlConnection connection =
        await dataSource.OpenConnectionAsync();
    return await InstallLinkingPostgresAuthorityIdentity.ComputeSha256Async(
        connection);
}

static async Task<int> VerifyTransportAsync(
    NpgsqlDataSource tlsDataSource,
    string tlsConnectionString)
{
    try
    {
        string authorityIdentitySha256;
        await using (NpgsqlConnection tlsConnection =
                     await tlsDataSource.OpenConnectionAsync())
        {
            authorityIdentitySha256 =
                await InstallLinkingPostgresAuthorityIdentity
                    .ComputeSha256Async(tlsConnection);
            await using var sslCommand = new NpgsqlCommand(
                "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()",
                tlsConnection);
            object? observedSsl = await sslCommand.ExecuteScalarAsync();
            if (observedSsl is not true)
            {
                Console.Error.WriteLine(
                    "PostgreSQL transport proof did not observe an authenticated TLS session.");
                return 1;
            }
        }

        var plaintext = new NpgsqlConnectionStringBuilder(tlsConnectionString)
        {
            SslMode = SslMode.Disable,
            GssEncryptionMode = GssEncryptionMode.Disable,
            Pooling = false,
            Timeout = 5,
            CommandTimeout = 5,
            RootCertificate = null
        };
        await using var plaintextConnection =
            new NpgsqlConnection(plaintext.ConnectionString);
        try
        {
            await plaintextConnection.OpenAsync();
        }
        catch (PostgresException exception) when (
            string.Equals(
                exception.SqlState,
                PostgresErrorCodes.InvalidAuthorizationSpecification,
                StringComparison.Ordinal))
        {
            WriteCanonicalJson(
                new SortedDictionary<string, object?>(StringComparer.Ordinal)
                {
                    ["authenticated"] = true,
                    ["authorityIdentitySha256"] =
                        authorityIdentitySha256,
                    ["contractName"] = "chummer.postgres_transport_proof.v1",
                    ["gssEncryptionDisabled"] = true,
                    ["pgStatSsl"] = true,
                    ["plaintextAttempted"] = true,
                    ["plaintextRejected"] = true,
                    ["plaintextSqlState"] = "28000",
                    ["status"] = "pass"
                });
            return 0;
        }
        catch (Exception exception) when (
            exception is NpgsqlException
                or InvalidOperationException
                or ArgumentException
                or TimeoutException)
        {
            Console.Error.WriteLine(
                "PostgreSQL plaintext transport probe failed without an explicit server rejection.");
            return 1;
        }

        Console.Error.WriteLine(
            "PostgreSQL unexpectedly accepted an authenticated plaintext session.");
        return 1;
    }
    catch (Exception exception) when (
        exception is NpgsqlException
            or InvalidOperationException
            or ArgumentException
            or TimeoutException)
    {
        Console.Error.WriteLine(
            "PostgreSQL authenticated TLS transport proof failed.");
        return 1;
    }
}

static async Task<int> ImportLocalAsync()
{
    IConfiguration configuration = new ConfigurationBuilder()
        .AddEnvironmentVariables()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["ASPNETCORE_ENVIRONMENT"] = Environments.Production
        })
        .Build();
    if (string.IsNullOrWhiteSpace(
            configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]))
    {
        Console.Error.WriteLine(
            "The one-shot import requires an explicit data-protection key-ring path.");
        return 78;
    }

    var environment = new ImportHostEnvironment();
    var services = new ServiceCollection();
    string keyRingPath = HubRuntimePathDefaults.ResolveDataProtectionKeysPath(
        configuration,
        environment);
    DataProtectionKeyProtectionStatus keyProtection =
        DataProtectionKeyProtectionConfigurator.Configure(
            services,
            configuration,
            environment,
            keyRingPath);
    if (!keyProtection.Ready)
    {
        Console.Error.WriteLine(
            "The one-shot import could not open the encrypted data-protection key ring.");
        return 78;
    }

    string runtimeConnectionString;
    try
    {
        runtimeConnectionString = InstallLinkingPostgresConnectionConfiguration
            .LoadRuntimeConnectionString(configuration, environment);
    }
    catch (Exception exception) when (
        exception is InvalidOperationException
            or InvalidDataException
            or IOException
            or UnauthorizedAccessException
            or PlatformNotSupportedException)
    {
        Console.Error.WriteLine(
            "The owner-only InstallLinking PostgreSQL runtime credential file is unavailable or invalid.");
        return 78;
    }

    await using ServiceProvider serviceProvider = services.BuildServiceProvider();
    IDataProtectionProvider dataProtectionProvider =
        serviceProvider.GetRequiredService<IDataProtectionProvider>();
    try
    {
        await using NpgsqlDataSource runtimeDataSource =
            NpgsqlDataSource.Create(runtimeConnectionString);
        var authority = new NpgsqlInstallLinkingSnapshotAuthority(runtimeDataSource);
        var import = new InstallLinkingPostgresImportCoordinator(
            authority,
            () => InstallLinkingOneShotImportSession.Open(
                configuration,
                dataProtectionProvider,
                environment));
        InstallLinkingPostgresImportResult result = await import.ExecuteAsync();
        switch (result.Disposition)
        {
            case InstallLinkingPostgresImportDisposition.Imported:
                Console.WriteLine(
                    "install_linking local snapshot imported once and reconciled to PostgreSQL generation 1.");
                return 0;
            case InstallLinkingPostgresImportDisposition.Reconciled:
                Console.WriteLine(
                    "install_linking committed import intent and local mirror were reconciled.");
                return 0;
            case InstallLinkingPostgresImportDisposition.AlreadyMirrored:
                Console.WriteLine(
                    "install_linking generation 1 was already imported and exactly mirrored.");
                return 0;
            case InstallLinkingPostgresImportDisposition.AuthorityUnavailable:
                Console.Error.WriteLine(
                    "The InstallLinking PostgreSQL authority is unavailable or has not been prepared.");
                return 1;
            case InstallLinkingPostgresImportDisposition.PreparedNotCommitted:
                Console.Error.WriteLine(
                    "The InstallLinking import intent is durable but PostgreSQL did not commit it; rerun the same command to retry the exact intent.");
                return 1;
            case InstallLinkingPostgresImportDisposition.CommittedPendingMirror:
                Console.Error.WriteLine(
                    "PostgreSQL committed the exact InstallLinking import intent, but the local mirror acknowledgement is incomplete; rerun to repair it.");
                return 1;
            case InstallLinkingPostgresImportDisposition.RefusedNonEmpty:
            default:
                Console.Error.WriteLine(
                    "The InstallLinking PostgreSQL authority is nonempty and does not exactly match the durable import intent; import was refused.");
                return 1;
        }
    }
    catch (Exception exception) when (exception is
        NpgsqlException or
        InvalidOperationException or
        InvalidDataException or
        CryptographicException or
        IOException or
        UnauthorizedAccessException)
    {
        Console.Error.WriteLine(
            $"install_linking one-shot import failed ({exception.GetType().Name}).");
        return 1;
    }
}

internal sealed class ImportHostEnvironment : IHostEnvironment
{
    public string EnvironmentName { get; set; } = Environments.Production;
    public string ApplicationName { get; set; } =
        "Chummer.InstallLinking.Postgres.Tool";
    public string ContentRootPath { get; set; } = Directory.GetCurrentDirectory();
    public IFileProvider ContentRootFileProvider { get; set; } =
        new NullFileProvider();
}

internal static class InstallLinkingPostgresToolArguments
{
    private const string RuntimeRoleEnvironmentVariable =
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE";
    private static readonly Regex RuntimeRolePattern = new(
        "^[a-z_][a-z0-9_]{0,62}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    public static bool TryResolveRuntimeRole(
        string[] arguments,
        Func<string, string?> readEnvironmentVariable,
        out string? runtimeRole)
    {
        ArgumentNullException.ThrowIfNull(arguments);
        ArgumentNullException.ThrowIfNull(readEnvironmentVariable);
        runtimeRole = arguments.Length == 2
            ? arguments[1]
            : readEnvironmentVariable(RuntimeRoleEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(runtimeRole)
            || !RuntimeRolePattern.IsMatch(runtimeRole))
        {
            runtimeRole = null;
            return false;
        }

        return true;
    }
}
