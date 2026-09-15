using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text.Json;
using Chummer.Infrastructure.Workspaces;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class RookPrivateRuntimeCompositionTests
{
    private const string EnabledKey = "CHUMMER_ROOK_PRIVATE_RUNTIME_ENABLED";
    private const string PrivateMarker = "PRIVATE-ROOK-CONFIGURATION-SENTINEL";

    [Theory]
    [InlineData(null)]
    [InlineData("false")]
    public void Disabled_runtime_preserves_every_existing_registration_and_ignores_unused_inputs(string? enabled)
    {
        IServiceCollection services = ExistingServices();
        ServiceDescriptor[] before = services.ToArray();
        IConfiguration configuration = Configuration(enabled);

        IServiceCollection result = services.AddHubPrivateRookRuntime(
            configuration, new TestEnvironment(Environments.Production));

        Assert.Same(services, result);
        Assert.Equal(before, services.ToArray());
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("1")]
    [InlineData("true,false")]
    [InlineData("FALSE")]
    [InlineData("TRUE")]
    [InlineData(" true ")]
    [InlineData(" false ")]
    public void Malformed_activation_flags_fail_without_partial_registration(string enabled)
    {
        IServiceCollection services = ExistingServices();
        ServiceDescriptor[] before = services.ToArray();
        (IConfiguration configuration, RecordingProvider reads) = RecordConfiguration(Configuration(enabled));

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            services.AddHubPrivateRookRuntime(
                configuration, new TestEnvironment(Environments.Production)));

        AssertSafeFailure(failure);
        Assert.Equal(before, services.ToArray());
        Assert.All(reads.Keys, key => Assert.Equal(EnabledKey, key));
    }

    [Theory]
    [InlineData("Development")]
    [InlineData("Staging")]
    [InlineData("Testing")]
    [InlineData("")]
    public void Enabled_runtime_cannot_register_on_a_nonproduction_host(string environment)
    {
        IServiceCollection services = ExistingServices();
        ServiceDescriptor[] before = services.ToArray();
        (IConfiguration configuration, RecordingProvider reads) = RecordConfiguration(Configuration("true"));

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            services.AddHubPrivateRookRuntime(configuration, new TestEnvironment(environment)));

        AssertSafeFailure(failure);
        Assert.Equal(before, services.ToArray());
        AssertOnlyActivationFlagsRead(reads);
    }

    [Fact]
    public void Public_download_only_host_cannot_register_the_private_runtime()
    {
        IServiceCollection services = ExistingServices();
        ServiceDescriptor[] before = services.ToArray();
        IConfiguration input = Configuration("true");
        input["CHUMMER_PUBLIC_DOWNLOAD_ONLY"] = "true";
        (IConfiguration configuration, RecordingProvider reads) = RecordConfiguration(input);

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            services.AddHubPrivateRookRuntime(configuration, new TestEnvironment(Environments.Production)));

        AssertSafeFailure(failure);
        Assert.Equal(before, services.ToArray());
        AssertOnlyActivationFlagsRead(reads);
    }

    [Fact]
    public void Valid_composition_adds_only_the_real_singleton_factory_and_transient_read_service()
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        IServiceCollection services = fixture.Services();
        ServiceDescriptor[] before = services.ToArray();
        string stateBefore = fixture.Snapshot();

        PrivateRookRuntimeConfiguration.AddHubPrivateRookRuntime(services, fixture.Configuration,
            new TestEnvironment(Environments.Production), fixture.Observations);

        Assert.Equal(before, services.Take(before.Length).ToArray());
        Assert.Collection(services.Skip(before.Length),
            descriptor =>
            {
                Assert.Equal(typeof(PrivateWorkspaceRuleRuntimeFactory), descriptor.ServiceType);
                Assert.Equal(ServiceLifetime.Singleton, descriptor.Lifetime);
                Assert.IsType<PrivateWorkspaceRuleRuntimeFactory>(descriptor.ImplementationInstance);
            },
            descriptor =>
            {
                Assert.Equal(typeof(RookWorkspaceRuleReadService), descriptor.ServiceType);
                Assert.Equal(ServiceLifetime.Transient, descriptor.Lifetime);
                Assert.NotNull(descriptor.ImplementationFactory);
            });
        using ServiceProvider provider = services.BuildServiceProvider();
        Assert.Same(provider.GetRequiredService<PrivateWorkspaceRuleRuntimeFactory>(),
            provider.GetRequiredService<PrivateWorkspaceRuleRuntimeFactory>());
        // Composition does not supply an authority replacement. Resolving the
        // read service still requires the normal integrated store activation.
        Assert.Throws<InvalidOperationException>(() => provider.GetRequiredService<RookWorkspaceRuleReadService>());
        Assert.Equal(fixture.PersistedFiles, fixture.Observations.PrivateFiles);
        Assert.Equal(new[] { fixture.BaseRoot, fixture.CurrentRoot,
            Path.Combine(fixture.BaseRoot, "data"), Path.Combine(fixture.CurrentRoot, "lang") },
            fixture.Observations.SourceDirectories);
        Assert.Equal(stateBefore, fixture.Snapshot());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Explicit_amend_roots_remain_separate_observed_sources(bool shareBaseAndCurrent)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        string first = fixture.CreateDirectory("first-amend");
        string second = fixture.CreateDirectory("second-amend");
        string current = shareBaseAndCurrent ? fixture.BaseRoot : fixture.CurrentRoot;
        if (shareBaseAndCurrent) fixture.CreateDirectory(Path.Combine("base-source", "lang"));
        fixture.Configuration[PrivateRookRuntimeConfiguration.CurrentDirectoryKey] = current;
        fixture.Configuration[PrivateRookRuntimeConfiguration.AmendsPathKey] = first + ";" + second;
        string before = fixture.Snapshot();

        PrivateRookRuntimeConfiguration.AddHubPrivateRookRuntime(fixture.Services(), fixture.Configuration,
            new TestEnvironment(Environments.Production), fixture.Observations);

        Assert.Equal(new[] { fixture.BaseRoot, current, first, second,
            Path.Combine(fixture.BaseRoot, "data"), Path.Combine(current, "lang") },
            fixture.Observations.SourceDirectories);
        Assert.Equal(before, fixture.Snapshot());
    }

    public static IEnumerable<object[]> RequiredInputs()
    {
        foreach (string key in new[]
        {
            "IDENTITY_SERVICE_BASE_URL", "CHUMMER_COMMUNITY_STORE_PATH",
            "CHUMMER_INSTALL_LINKING_STORE_PATH", "CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH",
            "CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH", "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE",
            "CHUMMER_DATA_PROTECTION_KEYS_PATH",
            PrivateRookRuntimeConfiguration.ScratchRootKey, PrivateRookRuntimeConfiguration.BaseDirectoryKey,
            PrivateRookRuntimeConfiguration.CurrentDirectoryKey
        }) yield return [key];
    }

    [Theory]
    [MemberData(nameof(RequiredInputs))]
    public void Each_required_input_is_needed_before_any_registration(string key)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        fixture.Configuration[key] = null;
        AssertCompositionRejectedWithoutChanges(fixture);
    }

    [Theory]
    [InlineData("")]
    [InlineData("relative-source")]
    [InlineData("/")]
    [InlineData("/tmp/../tmp")]
    [InlineData("/tmp/")]
    [InlineData(" /tmp")]
    [InlineData("/tmp\nprivate")]
    public void Noncanonical_source_paths_are_rejected(string path)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        fixture.Configuration[PrivateRookRuntimeConfiguration.BaseDirectoryKey] = path;
        AssertCompositionRejectedWithoutChanges(fixture);
    }

    [Theory]
    [InlineData("https://user:password@identity.invalid")]
    [InlineData("https://identity.invalid/another-path")]
    [InlineData("https://identity.invalid?token=private")]
    [InlineData("https://identity.invalid#private")]
    [InlineData("ftp://identity.invalid")]
    [InlineData("identity.invalid")]
    [InlineData(" https://identity.invalid")]
    public void Identity_must_be_an_explicit_origin_before_filesystem_observation(string origin)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        fixture.Configuration["IDENTITY_SERVICE_BASE_URL"] = origin;
        AssertCompositionRejectedWithoutChanges(fixture);
        Assert.Empty(fixture.Observations.PrivateFiles);
        Assert.Empty(fixture.Observations.SourceDirectories);
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData(";")]
    [InlineData("relative-amend")]
    public void An_explicit_invalid_amend_list_is_not_treated_as_absent(string amends)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        fixture.Configuration[PrivateRookRuntimeConfiguration.AmendsPathKey] = amends;
        AssertCompositionRejectedWithoutChanges(fixture);
    }

    [Theory]
    [InlineData("missing-data")]
    [InlineData("missing-lang")]
    [InlineData("missing-amend")]
    [InlineData("symlink-amend")]
    public void Missing_content_segments_and_missing_or_linked_amends_are_rejected(string scenario)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        if (scenario == "missing-data") fixture.RemoveEmptyDirectory(Path.Combine(fixture.BaseRoot, "data"));
        else if (scenario == "missing-lang") fixture.RemoveEmptyDirectory(Path.Combine(fixture.CurrentRoot, "lang"));
        else
        {
            string amend = Path.Combine(fixture.Root, "configured-amend");
            if (scenario == "symlink-amend") Directory.CreateSymbolicLink(amend, fixture.BaseRoot);
            fixture.Configuration[PrivateRookRuntimeConfiguration.AmendsPathKey] = amend;
        }
        AssertCompositionRejectedWithoutChanges(fixture);
    }

    [Theory]
    [InlineData("duplicate-stores")]
    [InlineData("scratch-state")]
    [InlineData("source-scratch")]
    [InlineData("source-state")]
    [InlineData("amend-scratch")]
    public void Mutable_custody_and_source_roots_cannot_overlap(string scenario)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        switch (scenario)
        {
            case "duplicate-stores":
                fixture.Configuration["CHUMMER_INSTALL_LINKING_STORE_PATH"] = fixture.PersistedFiles[0];
                break;
            case "scratch-state":
                fixture.Configuration[PrivateRookRuntimeConfiguration.ScratchRootKey] = fixture.StateRoot;
                break;
            case "source-scratch":
                fixture.Configuration[PrivateRookRuntimeConfiguration.BaseDirectoryKey] = fixture.ScratchRoot;
                break;
            case "source-state":
                fixture.Configuration[PrivateRookRuntimeConfiguration.CurrentDirectoryKey] = fixture.StateRoot;
                break;
            case "amend-scratch":
                fixture.Configuration[PrivateRookRuntimeConfiguration.AmendsPathKey] = fixture.ScratchRoot;
                break;
        }
        AssertCompositionRejectedWithoutChanges(fixture);
    }

    [Theory]
    [InlineData("missing-status")]
    [InlineData("unready-status")]
    [InlineData("deferred-status")]
    public void Certificate_status_must_already_be_a_ready_configurator_instance(string scenario)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        IServiceCollection services = ExistingServices();
        if (scenario == "unready-status")
            services.AddSingleton(new DataProtectionKeyProtectionStatus(false, "not-ready"));
        else if (scenario == "deferred-status")
            services.AddSingleton(_ => new DataProtectionKeyProtectionStatus(true, "not-an-observed-configurator-result"));
        ServiceDescriptor[] before = services.ToArray();
        string stateBefore = fixture.Snapshot();
        IConfiguration configuration = fixture.Configuration;
        IPrivateRookFileSystemObservation observations = fixture.Observations;

        AssertSafeFailure(Assert.Throws<InvalidOperationException>(() => PrivateRookRuntimeConfiguration.AddHubPrivateRookRuntime(
            services, configuration, new TestEnvironment(Environments.Production), observations)));

        Assert.Equal(before, services.ToArray());
        Assert.Empty(fixture.Observations.SourceDirectories);
        Assert.Equal(stateBefore, fixture.Snapshot());
    }

    [Fact]
    public void Normal_registration_rejects_writable_sources_even_when_directory_modes_are_readonly()
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        File.SetUnixFileMode(fixture.BaseRoot, UnixFileMode.UserRead | UnixFileMode.UserExecute);
        IServiceCollection services = fixture.Services();
        ServiceDescriptor[] before = services.ToArray();
        string stateBefore = fixture.Snapshot();
        try
        {
            // These configuration entries and an observer service descriptor
            // cannot replace the native observer selected by the public overload.
            fixture.Configuration["CHUMMER_ROOK_PRIVATE_SOURCE_READONLY"] = "true";
            fixture.Configuration["CHUMMER_ROOK_PRIVATE_FILESYSTEM_OBSERVER"] = "test";
            services.AddSingleton<IPrivateRookFileSystemObservation>(fixture.Observations);
            before = services.ToArray();
            IConfiguration configuration = fixture.Configuration;
            AssertSafeFailure(Assert.Throws<InvalidOperationException>(() => services.AddHubPrivateRookRuntime(
                configuration, new TestEnvironment(Environments.Production))));
            Assert.Equal(before, services.ToArray());
            Assert.Empty(fixture.Observations.PrivateFiles);
            Assert.Empty(fixture.Observations.SourceDirectories);
            Assert.Equal(stateBefore, fixture.Snapshot());
        }
        finally
        {
            File.SetUnixFileMode(fixture.BaseRoot, PrivateDirectoryMode);
        }
    }

    [Theory]
    [InlineData("missing")]
    [InlineData("file-link")]
    [InlineData("ancestor-link")]
    [InlineData("public-file-mode")]
    [InlineData("public-directory-mode")]
    public void Persisted_file_observation_rejects_invalid_inputs_without_repair(string scenario)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        string path = fixture.PersistedFiles[0];
        if (scenario == "missing") path = Path.Combine(fixture.StateRoot, "missing.json");
        else if (scenario == "file-link")
        {
            string link = Path.Combine(fixture.StateRoot, "linked.json");
            File.CreateSymbolicLink(link, path);
            path = link;
        }
        else if (scenario == "ancestor-link")
        {
            string link = Path.Combine(fixture.Root, "linked-state");
            Directory.CreateSymbolicLink(link, fixture.StateRoot);
            path = Path.Combine(link, Path.GetFileName(path));
        }
        else if (scenario == "public-file-mode")
            File.SetUnixFileMode(path, PrivateFileMode | UnixFileMode.GroupRead);
        else if (scenario == "public-directory-mode")
            File.SetUnixFileMode(fixture.StateRoot, PrivateDirectoryMode | UnixFileMode.GroupExecute);
        string before = fixture.Snapshot();

        Exception? failure = Record.Exception(() => LinuxSecureFile.ValidateExistingPrivateFile(path));

        Assert.True(failure is IOException or UnauthorizedAccessException);
        Assert.Equal(before, fixture.Snapshot());
    }

    [Theory]
    [InlineData("missing")]
    [InlineData("trailing-separator")]
    [InlineData("link")]
    [InlineData("ancestor-link")]
    [InlineData("public-mode")]
    public void Real_core_factory_rejects_invalid_scratch_without_provisioning_or_repair(string scenario)
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        string path = fixture.ScratchRoot;
        if (scenario == "missing") path = Path.Combine(fixture.Root, "missing-scratch");
        else if (scenario == "trailing-separator") path += Path.DirectorySeparatorChar;
        else if (scenario == "link")
        {
            path = Path.Combine(fixture.Root, "linked-scratch");
            Directory.CreateSymbolicLink(path, fixture.ScratchRoot);
        }
        else if (scenario == "ancestor-link")
        {
            string link = Path.Combine(fixture.Root, "linked-root");
            Directory.CreateSymbolicLink(link, fixture.Root);
            path = Path.Combine(link, "scratch");
        }
        else if (scenario == "public-mode")
            File.SetUnixFileMode(fixture.ScratchRoot, PrivateDirectoryMode | UnixFileMode.GroupRead);
        string before = fixture.Snapshot();
        string baseRoot = fixture.BaseRoot;
        string currentRoot = fixture.CurrentRoot;

        Assert.Throws<ArgumentException>(() => new PrivateWorkspaceRuleRuntimeFactory(
            path, baseRoot, currentRoot, null));

        Assert.Equal(before, fixture.Snapshot());
    }

    [Fact]
    public void Native_observation_and_core_reject_an_unowned_or_nonprivate_system_root()
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        uint uid = Native.GetEffectiveUserId();
        Assert.Equal(0, Native.Statx(-100, "/", 0x100, 0xB, out NativeMetadata root));
        Assert.Equal(0u, root.UserId);
        if (uid != 0)
            Assert.NotEqual(uid, root.UserId);
        else
            Assert.NotEqual(0x1C0, root.Mode & 0xFFF);
        Assert.Throws<UnauthorizedAccessException>(() =>
            LinuxSecureFile.ValidateExistingDirectory("/", ownerOnly: true, readOnlyFileSystem: false));
        Assert.Throws<ArgumentException>(() => new PrivateWorkspaceRuleRuntimeFactory(
            "/", Path.GetTempPath(), Path.GetTempPath(), null));
    }

    [Fact]
    public async Task Native_private_file_observation_rejects_a_fifo_without_waiting_for_a_writer()
    {
        if (!IsSupportedPlatformOrAssertClosed()) return;
        using var fixture = new Fixture();
        string fifo = Path.Combine(fixture.StateRoot, "not-a-regular-file");
        Assert.Equal(0, Native.MakeFifo(fifo, 0x180));
        Task<Exception?> observation = Task.Run<Exception?>(() => Record.Exception(() =>
            LinuxSecureFile.ValidateExistingPrivateFile(fifo)));
        Task completed = await Task.WhenAny(observation, Task.Delay(TimeSpan.FromSeconds(5)));
        if (completed != observation)
        {
            // Keep both FIFO ends open while joining a regressed blocking open,
            // so a failed assertion cannot leave a worker hung behind cleanup.
            int rescue = Native.Open(fifo, 2 | 0x800 | 0x80000);
            Assert.True(rescue >= 0);
            try { await observation.WaitAsync(TimeSpan.FromSeconds(5)); }
            finally { Native.Close(rescue); }
        }
        Assert.Same(observation, completed);
        Assert.IsType<InvalidDataException>(await observation);
    }

    [SupportedOSPlatform("linux")]
    private static void AssertCompositionRejectedWithoutChanges(Fixture fixture)
    {
        IServiceCollection services = fixture.Services();
        ServiceDescriptor[] before = services.ToArray();
        string stateBefore = fixture.Snapshot();
        AssertSafeFailure(Assert.Throws<InvalidOperationException>(() => PrivateRookRuntimeConfiguration.AddHubPrivateRookRuntime(
            services, fixture.Configuration, new TestEnvironment(Environments.Production), fixture.Observations)));
        Assert.Equal(before, services.ToArray());
        Assert.Equal(stateBefore, fixture.Snapshot());
    }

    [SupportedOSPlatformGuard("linux")]
    private static bool IsSupportedPlatformOrAssertClosed()
    {
        if (OperatingSystem.IsLinux() && LinuxSecureFile.IsSupportedPlatform) return true;
        Assert.Throws<PlatformNotSupportedException>(() => LinuxSecureFile.ValidateExistingDirectory(
            Path.GetTempPath(), ownerOnly: true, readOnlyFileSystem: false));
        return false;
    }

    private const UnixFileMode PrivateDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode PrivateFileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;

    // The internal composition seam simulates only the read-only mount observation.
    // All files, modes, ancestry and Core scratch validation below remain real.
    private sealed class ObservedFileSystem : IPrivateRookFileSystemObservation
    {
        internal List<string> PrivateFiles { get; } = [];
        internal List<string> SourceDirectories { get; } = [];
        public void ValidatePrivateFile(string path)
        {
            PrivateFiles.Add(path);
            LinuxSecureFile.ValidateExistingPrivateFile(path);
        }
        public void ValidateSourceDirectory(string path)
        {
            SourceDirectories.Add(path);
            LinuxSecureFile.ValidateExistingDirectory(path, ownerOnly: false, readOnlyFileSystem: false);
        }
    }

    [SupportedOSPlatform("linux")]
    private sealed class Fixture : IDisposable
    {
        private readonly List<string> _directories = [];
        private readonly List<string> _files = [];
        internal string Root { get; } = Directory.CreateTempSubdirectory("chummer-rook-composition-tests-").FullName;
        internal string StateRoot { get; }
        internal string BaseRoot { get; }
        internal string CurrentRoot { get; }
        internal string ScratchRoot { get; }
        internal string[] PersistedFiles { get; }
        internal IConfiguration Configuration { get; }
        internal ObservedFileSystem Observations { get; } = new();

        internal Fixture()
        {
            File.SetUnixFileMode(Root, PrivateDirectoryMode);
            _directories.Add(Root);
            StateRoot = CreateDirectory("state");
            BaseRoot = CreateDirectory("base-source");
            CurrentRoot = CreateDirectory("current-source");
            ScratchRoot = CreateDirectory("scratch");
            string keyRing = CreateDirectory("key-ring");
            CreateDirectory(Path.Combine("base-source", "data"));
            CreateDirectory(Path.Combine("current-source", "lang"));
            PersistedFiles = [WriteFile("state/community.json"), WriteFile("state/installations.json"),
                WriteFile("state/snapshots.json")];
            string certificate = WriteFile("state/certificate.pfx");
            string passwordFile = WriteFile("state/certificate-password");
            Configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                [EnabledKey] = "true",
                ["CHUMMER_PUBLIC_DOWNLOAD_ONLY"] = "false",
                ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.private.invalid",
                ["CHUMMER_COMMUNITY_STORE_PATH"] = PersistedFiles[0],
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = PersistedFiles[1],
                ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = PersistedFiles[2],
                ["CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH"] = certificate,
                ["CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE"] = passwordFile,
                ["CHUMMER_DATA_PROTECTION_KEYS_PATH"] = keyRing,
                [PrivateRookRuntimeConfiguration.BaseDirectoryKey] = BaseRoot,
                [PrivateRookRuntimeConfiguration.CurrentDirectoryKey] = CurrentRoot,
                [PrivateRookRuntimeConfiguration.ScratchRootKey] = ScratchRoot
            }).Build();
        }

        internal IServiceCollection Services()
            => ExistingServices().AddSingleton(new DataProtectionKeyProtectionStatus(true, "synthetic-configurator-result"));

        internal string CreateDirectory(string relative)
        {
            string path = Path.Combine(Root, relative);
            Directory.CreateDirectory(path, PrivateDirectoryMode);
            File.SetUnixFileMode(path, PrivateDirectoryMode);
            _directories.Add(path);
            return path;
        }

        internal void RemoveEmptyDirectory(string path)
        {
            Assert.True(_directories.Remove(path));
            Directory.Delete(path, recursive: false);
        }

        private string WriteFile(string relative)
        {
            string path = Path.Combine(Root, relative);
            File.WriteAllText(path, PrivateMarker);
            File.SetUnixFileMode(path, PrivateFileMode);
            _files.Add(path);
            return path;
        }

        internal string Snapshot() => JsonSerializer.Serialize(new
        {
            Directories = _directories.Select(path => new
            {
                Path = path, Mode = File.GetUnixFileMode(path),
                Children = Directory.EnumerateFileSystemEntries(path).Order().ToArray()
            }),
            Files = _files.Select(path => new
            {
                Path = path, Mode = File.GetUnixFileMode(path), Bytes = File.ReadAllBytes(path),
                Modified = File.GetLastWriteTimeUtc(path)
            })
        });

        public void Dispose() => Directory.Delete(Root, recursive: true);
    }

    [StructLayout(LayoutKind.Explicit, Size = 256)]
    private struct NativeMetadata
    {
        [FieldOffset(20)] public uint UserId;
        [FieldOffset(28)] public ushort Mode;
    }

    private static class Native
    {
        [DllImport("libc", EntryPoint = "geteuid")]
        internal static extern uint GetEffectiveUserId();
        [DllImport("libc", EntryPoint = "statx", SetLastError = true)]
        internal static extern int Statx(int directory, string path, int flags, uint mask, out NativeMetadata result);
        [DllImport("libc", EntryPoint = "mkfifo", SetLastError = true)]
        internal static extern int MakeFifo(string path, uint mode);
        [DllImport("libc", EntryPoint = "open", SetLastError = true)]
        internal static extern int Open(string path, int flags);
        [DllImport("libc", EntryPoint = "close", SetLastError = true)]
        internal static extern int Close(int descriptor);
    }

    private static IServiceCollection ExistingServices()
        => new ServiceCollection().AddSingleton(new ExistingRegistration());

    private static IConfiguration Configuration(string? enabled)
        => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [EnabledKey] = enabled,
            ["CHUMMER_PUBLIC_DOWNLOAD_ONLY"] = "false",
            ["CHUMMER_COMMUNITY_STORE_PATH"] = PrivateMarker + "/community.json",
            ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = PrivateMarker + "/installations.json",
            ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = PrivateMarker + "/snapshots.json",
            ["IDENTITY_SERVICE_BASE_URL"] = "https://" + PrivateMarker + ".invalid/not-an-origin",
            ["CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH"] = PrivateMarker + "/certificate.pfx",
            ["CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE"] = PrivateMarker + "/certificate-password",
            ["CHUMMER_DATA_PROTECTION_KEYS_PATH"] = PrivateMarker + "/key-ring",
            ["CHUMMER_ROOK_PRIVATE_BASE_DIRECTORY"] = PrivateMarker + "/base",
            ["CHUMMER_ROOK_PRIVATE_CURRENT_DIRECTORY"] = PrivateMarker + "/current",
            ["CHUMMER_ROOK_PRIVATE_AMENDS_PATH"] = PrivateMarker + "/amends",
            ["CHUMMER_ROOK_PRIVATE_SCRATCH_ROOT"] = PrivateMarker + "/scratch"
        }).Build();

    private static void AssertSafeFailure(InvalidOperationException failure)
    {
        Assert.Null(failure.InnerException);
        Assert.DoesNotContain(PrivateMarker, failure.Message, StringComparison.Ordinal);
    }

    private static (IConfiguration Configuration, RecordingProvider Provider) RecordConfiguration(IConfiguration input)
    {
        var source = new RecordingSource(input.AsEnumerable().ToDictionary(item => item.Key, item => item.Value));
        return (new ConfigurationBuilder().Add(source).Build(), source.Provider);
    }

    private static void AssertOnlyActivationFlagsRead(RecordingProvider reads)
        => Assert.All(reads.Keys,
            key => Assert.Contains(key, new[] { EnabledKey, "CHUMMER_PUBLIC_DOWNLOAD_ONLY" }));

    private sealed class RecordingSource(IDictionary<string, string?> values) : IConfigurationSource
    {
        internal RecordingProvider Provider { get; } = new(values);
        public IConfigurationProvider Build(IConfigurationBuilder builder) => Provider;
    }

    private sealed class RecordingProvider : ConfigurationProvider
    {
        internal RecordingProvider(IDictionary<string, string?> values) => Data = values;
        internal List<string> Keys { get; } = [];

        public override bool TryGet(string key, out string? value)
        {
            Keys.Add(key);
            return base.TryGet(key, out value);
        }
    }

    private sealed class ExistingRegistration { }

    private sealed class TestEnvironment(string environmentName) : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = environmentName;
        public string ApplicationName { get; set; } = nameof(RookPrivateRuntimeCompositionTests);
        public string ContentRootPath { get; set; } = Path.GetTempPath();
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
