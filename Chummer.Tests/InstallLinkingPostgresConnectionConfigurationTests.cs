using System.Runtime.InteropServices;
using System.Text;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Npgsql;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingPostgresConnectionConfigurationTests
{
    private const string ExpectedHost = "db.example.net";
    private const string ExpectedDatabase = "chummer";
    private const string ExpectedPort = "5432";
    private const string ExpectedRuntimeRole = "install_linking_runtime";
    private const string ExpectedRootCertificate =
        InstallLinkingPostgresConnectionConfiguration.ExpectedRootCertificatePath;
    private const UnixFileMode OwnerFileMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite;

    [Fact]
    public void Runtime_inline_connection_string_is_rejected_without_disclosure()
    {
        const string secret = "inline-secret-must-not-be-disclosed";
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RejectedRuntimeInlineConnectionStringConfigurationKey,
                $"Host=db;Database=chummer;Username=runtime;Password={secret}"),
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                "/credential-file-is-not-read"));

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment()));

        Assert.DoesNotContain(secret, failure.ToString(), StringComparison.Ordinal);
        Assert.Contains("owner-only file", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Runtime_missing_connection_file_path_is_rejected()
    {
        IConfiguration configuration = Configuration();

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment()));

        Assert.Contains(
            InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
            failure.Message,
            StringComparison.Ordinal);
    }

    [Fact]
    public void Runtime_missing_connection_file_is_rejected()
    {
        using CredentialFileFixture fixture = new();
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path),
            (InstallLinkingPostgresConnectionConfiguration.ExpectedHostConfigurationKey,
                ExpectedHost));

        Assert.ThrowsAny<IOException>(() =>
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment()));
    }

    [Fact]
    public void Unsafe_connection_file_mode_is_rejected()
    {
        if (!OperatingSystem.IsLinux()
            || RuntimeInformation.ProcessArchitecture != Architecture.X64)
        {
            return;
        }

        using CredentialFileFixture fixture = new();
        fixture.Write(
            "Host=db;Database=chummer;Username=runtime;Password=secret",
            OwnerFileMode | UnixFileMode.GroupRead);

        Assert.Throws<UnauthorizedAccessException>(() =>
            InstallLinkingPostgresConnectionConfiguration.ReadConnectionStringFile(
                fixture.Path,
                requireLinuxSecurity: true));
    }

    [Fact]
    public void Multiline_connection_file_is_rejected()
    {
        using CredentialFileFixture fixture = new();
        fixture.Write(
            "Host=db;Database=chummer;Username=runtime\nPassword=secret",
            OwnerFileMode);

        InvalidDataException failure = Assert.Throws<InvalidDataException>(() =>
            InstallLinkingPostgresConnectionConfiguration.ReadConnectionStringFile(
                fixture.Path,
                requireLinuxSecurity: OperatingSystem.IsLinux()));

        Assert.Contains("exactly one", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Valid_owner_only_file_forces_safe_runtime_normalization()
    {
        using CredentialFileFixture fixture = new();
        fixture.Write(
            "Host=db.example.net;Database=chummer;Username=runtime;Password=secret;"
            + "SSL Mode=VerifyFull;Timeout=120;Command Timeout=0;"
            + $"Root Certificate={ExpectedRootCertificate};"
            + "Include Error Detail=true;Persist Security Info=true;Application Name=untrusted",
            OwnerFileMode);
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path),
            (InstallLinkingPostgresConnectionConfiguration.ExpectedHostConfigurationKey,
                ExpectedHost));

        string normalized =
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment());
        var builder = new NpgsqlConnectionStringBuilder(normalized);

        Assert.Equal("db.example.net", builder.Host);
        Assert.Equal("chummer", builder.Database);
        Assert.Equal("runtime", builder.Username);
        Assert.False(builder.IncludeErrorDetail);
        Assert.False(builder.PersistSecurityInfo);
        Assert.Equal("chummer-run-install-linking", builder.ApplicationName);
        Assert.Equal(SslMode.VerifyFull, builder.SslMode);
        Assert.Equal(ExpectedRootCertificate, builder.RootCertificate);
        Assert.Equal(
            InstallLinkingPostgresDurabilityInvariants.ConnectionTimeoutSeconds,
            builder.Timeout);
        Assert.Equal(
            InstallLinkingPostgresDurabilityInvariants.CommandTimeoutSeconds,
            builder.CommandTimeout);
    }

    [Fact]
    public void Production_runtime_rejects_weak_transport_without_disclosure()
    {
        const string secret = "weak-transport-secret-must-not-be-disclosed";
        using CredentialFileFixture fixture = new();
        fixture.Write(
            $"Host=db.example.net;Database=chummer;Username=runtime;Password={secret};SSL Mode=Disable",
            OwnerFileMode);
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path),
            (InstallLinkingPostgresConnectionConfiguration.ExpectedHostConfigurationKey,
                ExpectedHost));

        InvalidDataException failure = Assert.Throws<InvalidDataException>(() =>
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment()));

        Assert.DoesNotContain(secret, failure.ToString(), StringComparison.Ordinal);
        Assert.Contains("full TLS", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Production_runtime_requires_reviewed_host_without_disclosure()
    {
        using CredentialFileFixture fixture = new();
        fixture.Write(
            $"Host={ExpectedHost};Database=chummer;Username=runtime;Password=secret;"
            + $"SSL Mode=VerifyFull;Root Certificate={ExpectedRootCertificate}",
            OwnerFileMode);
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path));

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment()));

        Assert.Contains(
            InstallLinkingPostgresConnectionConfiguration.ExpectedHostConfigurationKey,
            failure.Message,
            StringComparison.Ordinal);
        Assert.DoesNotContain("Password=secret", failure.ToString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("203.0.113.7")]
    [InlineData("db.example.net.")]
    [InlineData("db..example.net")]
    public void Production_runtime_rejects_non_dns_expected_host(string expectedHost)
    {
        using CredentialFileFixture fixture = new();
        fixture.Write(
            $"Host={ExpectedHost};Database=chummer;Username=runtime;Password=secret;"
            + $"SSL Mode=VerifyFull;Root Certificate={ExpectedRootCertificate}",
            OwnerFileMode);
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path),
            (InstallLinkingPostgresConnectionConfiguration.ExpectedHostConfigurationKey,
                expectedHost));

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment()));

        Assert.Contains("DNS name", failure.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("Password=secret", failure.ToString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("other.example.net", "/run/chummer-secrets/install-linking-postgres-server-ca.pem", "certificate identity")]
    [InlineData("db.example.net", "/tmp/unreviewed-ca.pem", "mounted server CA")]
    public void Production_runtime_rejects_host_or_ca_substitution(
        string host,
        string rootCertificate,
        string expectedMessage)
    {
        const string secret = "substitution-secret-must-not-be-disclosed";
        using CredentialFileFixture fixture = new();
        fixture.Write(
            $"Host={host};Database=chummer;Username=runtime;Password={secret};"
            + $"SSL Mode=VerifyFull;Root Certificate={rootCertificate}",
            OwnerFileMode);
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path),
            (InstallLinkingPostgresConnectionConfiguration.ExpectedHostConfigurationKey,
                ExpectedHost));

        InvalidDataException failure = Assert.Throws<InvalidDataException>(() =>
            InstallLinkingPostgresConnectionConfiguration.LoadRuntimeConnectionString(
                configuration,
                new ProductionHostEnvironment()));

        Assert.Contains(expectedMessage, failure.Message, StringComparison.Ordinal);
        Assert.DoesNotContain(secret, failure.ToString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("other_database", "5432")]
    [InlineData("chummer", "5433")]
    public void Production_runtime_rejects_database_or_port_substitution(
        string database,
        string port)
    {
        using CredentialFileFixture fixture = new();
        fixture.Write(
            $"Host={ExpectedHost};Database={database};Port={port};"
            + "Username=runtime;Password=secret;"
            + $"SSL Mode=VerifyFull;Root Certificate={ExpectedRootCertificate}",
            OwnerFileMode);
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path),
            (InstallLinkingPostgresConnectionConfiguration
                .ExpectedHostConfigurationKey,
                ExpectedHost));

        InvalidDataException failure = Assert.Throws<InvalidDataException>(() =>
            InstallLinkingPostgresConnectionConfiguration
                .LoadRuntimeConnectionString(
                    configuration,
                    new ProductionHostEnvironment()));

        Assert.Contains(
            "reviewed authority",
            failure.Message,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "Password=secret",
            failure.ToString(),
            StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("-c session_replication_role=replica")]
    [InlineData("--search_path=public")]
    public void Runtime_connection_rejects_startup_session_options(
        string options)
    {
        using CredentialFileFixture fixture = new();
        fixture.Write(
            $"Host={ExpectedHost};Database={ExpectedDatabase};Port={ExpectedPort};"
            + "Username=runtime;Password=secret;"
            + $"Options={options};SSL Mode=VerifyFull;"
            + $"Root Certificate={ExpectedRootCertificate}",
            OwnerFileMode);
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .RuntimeConnectionStringFileConfigurationKey,
                fixture.Path),
            (InstallLinkingPostgresConnectionConfiguration
                .ExpectedHostConfigurationKey,
                ExpectedHost));

        InvalidDataException failure = Assert.Throws<InvalidDataException>(() =>
            InstallLinkingPostgresConnectionConfiguration
                .LoadRuntimeConnectionString(
                    configuration,
                    new ProductionHostEnvironment()));

        Assert.Contains("session options", failure.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("Password=secret", failure.ToString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("")]
    [InlineData("other-role")]
    [InlineData("role with spaces")]
    [InlineData("0starts_with_digit")]
    public void Expected_runtime_role_rejects_missing_or_unsafe_names(
        string value)
    {
        IConfiguration configuration = Configuration(
            (InstallLinkingPostgresConnectionConfiguration
                .ExpectedRuntimeRoleConfigurationKey,
                value));

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            InstallLinkingPostgresConnectionConfiguration
                .LoadExpectedRuntimeRole(configuration));

        Assert.Contains(
            InstallLinkingPostgresConnectionConfiguration
                .ExpectedRuntimeRoleConfigurationKey,
            failure.Message,
            StringComparison.Ordinal);
    }

    [Fact]
    public void Expected_runtime_role_is_loaded_as_an_exact_safe_name()
    {
        IConfiguration configuration = Configuration();

        Assert.Equal(
            ExpectedRuntimeRole,
            InstallLinkingPostgresConnectionConfiguration
                .LoadExpectedRuntimeRole(configuration));
    }

    [Theory]
    [InlineData("leaf-dangling")]
    [InlineData("ancestor-dangling")]
    [InlineData("symlink-directory")]
    public void Local_absence_proof_rejects_symlinked_leaf_or_ancestor(
        string posture)
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        string root = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(),
            $"install-linking-absence-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            string parent = System.IO.Path.Combine(root, "install-linking");
            string store = System.IO.Path.Combine(parent, "store.json");
            switch (posture)
            {
                case "leaf-dangling":
                    Directory.CreateDirectory(parent);
                    File.CreateSymbolicLink(
                        store,
                        System.IO.Path.Combine(root, "missing-store"));
                    break;
                case "ancestor-dangling":
                    Directory.CreateSymbolicLink(
                        parent,
                        System.IO.Path.Combine(root, "missing-directory"));
                    break;
                case "symlink-directory":
                    string target = System.IO.Path.Combine(root, "empty-target");
                    Directory.CreateDirectory(target);
                    Directory.CreateSymbolicLink(parent, target);
                    break;
            }

            Assert.True(
                InstallLinkingLocalStoreAbsenceProof
                    .HasRetainedEntryOrUnsafeAncestor(store, root));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void Local_state_proof_distinguishes_absent_and_present_files()
    {
        string root = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(),
            $"install-linking-state-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            string parent = System.IO.Path.Combine(root, "install-linking");
            string store = System.IO.Path.Combine(parent, "store.json");

            Assert.Equal(
                InstallLinkingLocalStoreEntryState.Absent,
                InstallLinkingLocalStoreAbsenceProof
                    .InspectRetainedEntry(store, root));

            Directory.CreateDirectory(parent);
            File.WriteAllText(store, "retained");

            Assert.Equal(
                InstallLinkingLocalStoreEntryState.Present,
                InstallLinkingLocalStoreAbsenceProof
                    .InspectRetainedEntry(store, root));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void Local_state_proof_rejects_a_directory_at_the_store_path()
    {
        string root = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(),
            $"install-linking-state-unsafe-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            string store = System.IO.Path.Combine(
                root,
                "install-linking",
                "store.json");
            Directory.CreateDirectory(store);

            Assert.Equal(
                InstallLinkingLocalStoreEntryState.Unsafe,
                InstallLinkingLocalStoreAbsenceProof
                    .InspectRetainedEntry(store, root));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    private static IConfiguration Configuration(
        params (string Key, string? Value)[] values)
    {
        var selected = new Dictionary<string, string?>(StringComparer.Ordinal)
        {
            [InstallLinkingPostgresConnectionConfiguration
                .ExpectedDatabaseConfigurationKey] = ExpectedDatabase,
            [InstallLinkingPostgresConnectionConfiguration
                .ExpectedPortConfigurationKey] = ExpectedPort,
            [InstallLinkingPostgresConnectionConfiguration
                .ExpectedRuntimeRoleConfigurationKey] = ExpectedRuntimeRole
        };
        foreach ((string key, string? value) in values)
        {
            selected[key] = value;
        }

        return new ConfigurationBuilder()
            .AddInMemoryCollection(selected)
            .Build();
    }

    private sealed class CredentialFileFixture : IDisposable
    {
        private readonly string _root = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(),
            $"chummer-install-linking-postgres-credential-{Guid.NewGuid():N}");

        public CredentialFileFixture()
        {
            Directory.CreateDirectory(_root);
            Path = System.IO.Path.Combine(_root, "connection-string");
        }

        public string Path { get; }

        public void Write(string value, UnixFileMode mode)
        {
            File.WriteAllText(Path, value, new UTF8Encoding(false, true));
            if (OperatingSystem.IsLinux())
            {
                File.SetUnixFileMode(Path, mode);
            }
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class ProductionHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Production;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = AppContext.BaseDirectory;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
