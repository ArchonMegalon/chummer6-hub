using System.Security.Cryptography;
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
        + "transport-proof, "
        + "or import-local --confirm-empty-authority");
    return 64;
}

if (args[0] == "import-local")
{
    return await ImportLocalAsync();
}

string? runtimeRole = null;
if (args[0] is "grant-runtime" or "prepare"
    && !InstallLinkingPostgresToolArguments.TryResolveRuntimeRole(
        args,
        Environment.GetEnvironmentVariable,
        out runtimeRole))
{
    Console.Error.WriteLine(
        "The InstallLinking PostgreSQL runtime role is unavailable or invalid.");
    return 78;
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
                Console.WriteLine(
                    $"install_linking schema version {validation.AppliedVersion} is valid.");
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

            Console.WriteLine(
                $"install_linking schema version {prepared.AppliedVersion} and least-privilege runtime grants are ready.");
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
        ["grant-runtime" or "prepare"] => true,
        ["grant-runtime" or "prepare", _] => true,
        ["import-local", "--confirm-empty-authority"] => true,
        _ => false
    };

static async Task<int> VerifyTransportAsync(
    NpgsqlDataSource tlsDataSource,
    string tlsConnectionString)
{
    try
    {
        await using (NpgsqlConnection tlsConnection =
                     await tlsDataSource.OpenConnectionAsync())
        await using (var sslCommand = new NpgsqlCommand(
                         "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()",
                         tlsConnection))
        {
            object? observed = await sslCommand.ExecuteScalarAsync();
            if (observed is not true)
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
            Console.WriteLine(
                "{\"contractName\":\"chummer.postgres_transport_proof.v1\","
                + "\"authenticated\":true,\"pgStatSsl\":true,"
                + "\"plaintextAttempted\":true,\"plaintextRejected\":true,"
                + "\"plaintextSqlState\":\"28000\","
                + "\"gssEncryptionDisabled\":true}");
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
