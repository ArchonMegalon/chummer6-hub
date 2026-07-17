using Chummer.Run.Api.Services.Community.Postgres;
using Npgsql;

const string ConnectionStringEnvironmentVariable = "CHUMMER_PLAY_AUTH_MIGRATOR_CONNECTION_STRING";

if (args.Length is < 1 or > 2
    || args[0] is not ("migrate" or "validate" or "grant-runtime"))
{
    Console.Error.WriteLine("Usage: Chummer.PlayAuth.Postgres.Tool <migrate|validate|grant-runtime> [runtime-role]");
    return 64;
}

string? connectionString = Environment.GetEnvironmentVariable(ConnectionStringEnvironmentVariable);
if (string.IsNullOrWhiteSpace(connectionString))
{
    Console.Error.WriteLine($"{ConnectionStringEnvironmentVariable} is required; its value is never printed.");
    return 78;
}

if (args[0] == "grant-runtime" && args.Length != 2)
{
    Console.Error.WriteLine("grant-runtime requires the pre-created PostgreSQL runtime role name.");
    return 64;
}

await using NpgsqlDataSource dataSource = NpgsqlDataSource.Create(connectionString);
var migrator = new PlayAuthorizationPostgresMigrator(dataSource);
try
{
    switch (args[0])
    {
        case "migrate":
            await migrator.MigrateAsync();
            Console.WriteLine($"play_auth schema migrated to version {PlayAuthorizationPostgresSchema.CurrentVersion}.");
            return 0;
        case "validate":
            PlayAuthorizationPostgresSchemaValidation validation = await migrator.ValidateAsync();
            if (validation.Valid)
            {
                Console.WriteLine($"play_auth schema version {validation.AppliedVersion} is valid.");
                return 0;
            }

            Console.Error.WriteLine($"play_auth schema validation failed: {string.Join(',', validation.Problems)}");
            return 1;
        case "grant-runtime":
            await migrator.GrantRuntimePrivilegesAsync(args[1]);
            if (!await migrator.ValidateRuntimePrivilegesAsync(args[1]))
            {
                Console.Error.WriteLine("play_auth runtime privilege validation failed.");
                return 1;
            }

            Console.WriteLine("play_auth least-privilege runtime grants validated.");
            return 0;
        default:
            return 64;
    }
}
catch (Exception exception) when (exception is NpgsqlException or InvalidOperationException)
{
    Console.Error.WriteLine($"play_auth migration command failed ({exception.GetType().Name}).");
    return 1;
}
