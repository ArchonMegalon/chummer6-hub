using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using Chummer.Storage.Teable;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class TeableRecoveryBundleTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "teable-recovery-" + Guid.NewGuid().ToString("N"));
    private const UnixFileMode DirectoryMode = UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode FileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
    [SupportedOSPlatformGuard("linux")]
    private static bool Supported => OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.X64;
    private string Root(string name)
    {
        if (!Supported) throw new PlatformNotSupportedException();
        Directory.CreateDirectory(_root, DirectoryMode);
        string result = Path.Combine(_root, name);
        Directory.CreateDirectory(result, DirectoryMode);
        return result;
    }
    private static void Write(string root, string name, byte[] bytes)
    {
        if (!Supported) throw new PlatformNotSupportedException();
        using var file = new FileStream(Path.Combine(root, name), new FileStreamOptions
        {
            Mode = System.IO.FileMode.CreateNew, Access = FileAccess.Write, UnixCreateMode = FileMode
        });
        file.Write(bytes);
    }

    [Fact]
    public async Task Exact_configuration_and_secret_bytes_restore_on_empty_host_without_source_files()
    {
        if (!Supported) return;
        using var remote = new Remote();
        string source = Root("source"), fresh = Root("fresh-host");
        byte[] environment = "IDENTITY_ADMIN_KEY=synthetic-only\nNAME=Runner\n"u8.ToArray();
        byte[] secret = Enumerable.Range(0, 100_000).Select(i => (byte)i).ToArray();
        Write(source, "hub.env", environment);
        Write(source, "service-token", secret);
        var store = new TeableRecoveryBundleStore(remote.Store());
        var receipt = await store.CaptureAsync("fresh-hub", source, ["service-token", "hub.env"]);
        int writes = remote.HeadPosts;
        Assert.Equal(receipt, await store.CaptureAsync("fresh-hub", source, ["hub.env", "service-token"]));
        Assert.Equal(writes, remote.HeadPosts); // No extra history for unchanged prepared inputs.
        Directory.Delete(source, recursive: true); // Synthetic, exact test-owned source only.

        var newHost = new TeableRecoveryBundleStore(remote.Store());
        Assert.Equal(receipt, await newHost.InspectAsync("fresh-hub"));
        Assert.Equal(receipt, await newHost.RestoreAsync(receipt, fresh, "restored"));
        Assert.Equal(writes, remote.HeadPosts); // Restore is strictly remote-read-only.
        string destination = Path.Combine(fresh, "restored");
        Assert.Equal(DirectoryMode, File.GetUnixFileMode(destination));
        Assert.Equal(environment, File.ReadAllBytes(Path.Combine(destination, "hub.env")));
        Assert.Equal(secret, File.ReadAllBytes(Path.Combine(destination, "service-token")));
        foreach (string path in Directory.GetFiles(destination)) Assert.Equal(FileMode, File.GetUnixFileMode(path));
        await Assert.ThrowsAsync<InvalidDataException>(() => newHost.RestoreAsync(receipt, fresh, "restored"));
        Assert.Equal(secret, File.ReadAllBytes(Path.Combine(destination, "service-token")));
    }

    [Theory]
    [InlineData("../escape")]
    [InlineData("/absolute")]
    [InlineData("folder/file")]
    [InlineData("folder\\file")]
    [InlineData("..")]
    [InlineData(".")]
    [InlineData("")]
    public async Task Capture_rejects_unsafe_file_names_before_remote_writes(string name)
    {
        if (!Supported) return;
        using var remote = new Remote();
        await Assert.ThrowsAsync<InvalidDataException>(() => new TeableRecoveryBundleStore(remote.Store())
            .CaptureAsync("hub", Root("source"), [name]));
        Assert.Empty(remote.Rows);
    }

    [Theory]
    [InlineData("link")]
    [InlineData("public-file")]
    [InlineData("public-root")]
    [InlineData("duplicate")]
    [InlineData("oversized")]
    public async Task Capture_rejects_nonprivate_or_ambiguous_inputs_without_writes(string scenario)
    {
        if (!Supported) return;
        using var remote = new Remote();
        string source = Root("source");
        Write(source, "secret", new byte[scenario == "oversized" ? 1_048_577 : 7]);
        string[] names = ["secret"];
        switch (scenario)
        {
            case "link": File.CreateSymbolicLink(Path.Combine(source, "alias"), Path.Combine(source, "secret")); names = ["alias"]; break;
            case "public-file": File.SetUnixFileMode(Path.Combine(source, "secret"), FileMode | UnixFileMode.OtherRead); break;
            case "public-root": File.SetUnixFileMode(source, DirectoryMode | UnixFileMode.OtherRead); break;
            case "duplicate": names = ["secret", "SECRET"]; break;
        }
        await Assert.ThrowsAnyAsync<Exception>(() => new TeableRecoveryBundleStore(remote.Store()).CaptureAsync("hub", source, names));
        Assert.Empty(remote.Rows);
    }

    [Fact]
    public async Task Restore_rejects_changed_revision_or_outage_without_creating_a_target()
    {
        if (!Supported) return;
        using var remote = new Remote();
        string source = Root("source"), target = Root("target");
        Write(source, "secret", "first"u8.ToArray());
        var store = new TeableRecoveryBundleStore(remote.Store());
        var receipt = await store.CaptureAsync("hub", source, ["secret"]);
        File.WriteAllBytes(Path.Combine(source, "secret"), "second"u8.ToArray());
        var changed = await store.CaptureAsync("hub", source, ["secret"]);
        await Assert.ThrowsAsync<TeableRevisionConflictException>(() => store.RestoreAsync(receipt, target, "restore"));
        Assert.Empty(Directory.GetFileSystemEntries(target));
        remote.FailReads = true;
        await Assert.ThrowsAsync<HttpRequestException>(() => store.RestoreAsync(changed, target, "restore"));
        Assert.Empty(Directory.GetFileSystemEntries(target));
    }

    [Fact]
    public async Task Capture_uncertainty_is_reconciled_by_readback_without_another_commit()
    {
        if (!Supported) return;
        using var remote = new Remote();
        string source = Root("source");
        Write(source, "secret", "synthetic-secret"u8.ToArray());
        remote.CommitThenFailHard = true;
        var store = new TeableRecoveryBundleStore(remote.Store());
        await Assert.ThrowsAsync<IOException>(() => store.CaptureAsync("hub", source, ["secret"]));
        int writes = remote.HeadPosts;
        var recovered = await new TeableRecoveryBundleStore(remote.Store()).InspectAsync("hub");
        Assert.Equal(1, recovered.Revision);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Theory]
    [InlineData("path")]
    [InlineData("digest")]
    [InlineData("length")]
    [InlineData("duplicate-file")]
    [InlineData("unknown-property")]
    [InlineData("duplicate-property")]
    [InlineData("wrong-deployment")]
    public async Task Hostile_remote_bundle_is_rejected_before_any_output(string scenario)
    {
        if (!Supported) return;
        using var remote = new Remote();
        byte[] content = "synthetic"u8.ToArray();
        var file = new JsonObject
        {
            ["name"] = "hub.env", ["length"] = content.Length,
            ["sha256"] = Convert.ToHexStringLower(SHA256.HashData(content)),
            ["bytes"] = Convert.ToBase64String(content)
        };
        var files = new JsonArray(file);
        var packet = new JsonObject { ["schema"] = "chummer.hub.recovery-files/v1", ["deployment"] = "hub", ["files"] = files };
        switch (scenario)
        {
            case "path": file["name"] = "../escape"; break;
            case "digest": file["sha256"] = new string('a', 64); break;
            case "length": file["length"] = content.Length + 1; break;
            case "duplicate-file": files.Add(file.DeepClone()); break;
            case "unknown-property": file["execute"] = true; break;
            case "wrong-deployment": packet["deployment"] = "another"; break;
        }
        string json = packet.ToJsonString();
        if (scenario == "duplicate-property") json = "{\"deployment\":\"wrong\"," + json[1..];
        var head = await remote.Store().CompareExchangeAsync("hub-recovery-hub", null, Guid.NewGuid(), Encoding.UTF8.GetBytes(json));
        var expected = new TeableRecoveryBundleStore.Receipt("hub", head.Revision, head.Commit, head.Sha256, files.Count);
        string target = Root("target");
        var exception = await Record.ExceptionAsync(() => new TeableRecoveryBundleStore(remote.Store()).RestoreAsync(expected, target, "restore"));
        Assert.True(exception is InvalidDataException or JsonException);
        Assert.Empty(Directory.GetFileSystemEntries(target));
    }

    [Fact]
    public async Task Restore_rejects_a_dangling_destination_link_without_touching_its_target()
    {
        if (!Supported) return;
        using var remote = new Remote();
        string source = Root("source"), parent = Root("target");
        Write(source, "secret", "synthetic"u8.ToArray());
        var store = new TeableRecoveryBundleStore(remote.Store());
        var receipt = await store.CaptureAsync("hub", source, ["secret"]);
        string outside = Path.Combine(_root, "absent");
        Directory.CreateSymbolicLink(Path.Combine(parent, "restore"), outside);
        await Assert.ThrowsAsync<InvalidDataException>(() => store.RestoreAsync(receipt, parent, "restore"));
        Assert.False(Directory.Exists(outside));
        Assert.NotNull(new DirectoryInfo(Path.Combine(parent, "restore")).LinkTarget);
    }

    [Fact]
    public async Task Competing_capture_cannot_replace_the_other_operator_commit()
    {
        if (!Supported) return;
        using var remote = new Remote();
        string first = Root("first"), second = Root("second"), destination = Root("destination");
        Write(first, "secret", "first"u8.ToArray());
        Write(second, "secret", "winner"u8.ToArray());
        var store = new TeableRecoveryBundleStore(remote.Store());
        TeableRecoveryBundleStore.Receipt? winner = null;
        remote.BeforeHeadPost = () => winner = new TeableRecoveryBundleStore(remote.Store())
            .CaptureAsync("hub", second, ["secret"]).GetAwaiter().GetResult();
        await Assert.ThrowsAsync<TeableRevisionConflictException>(() => store.CaptureAsync("hub", first, ["secret"]));
        Assert.NotNull(winner);
        Assert.Equal(winner, await store.InspectAsync("hub"));
        await store.RestoreAsync(winner, destination, "restored");
        Assert.Equal("winner", File.ReadAllText(Path.Combine(destination, "restored", "secret")));
    }

    [Fact(Timeout = 5000)]
    public async Task Private_file_reader_rejects_fifo_without_waiting_for_a_writer()
    {
        if (!Supported) return;
        string fifo = Path.Combine(Root("source"), "not-a-secret");
        Assert.Equal(0, MkFifo(fifo, 0x180));
        await Task.Run(() => Assert.Throws<InvalidDataException>(() => LinuxSecureFile.ReadOwnerOnlyRegularFile(fifo, 1024, repairOwnerMode: false)));
    }

    [Fact]
    public async Task Capture_rejects_hardlinked_secrets_without_remote_writes()
    {
        if (!Supported) return;
        using var remote = new Remote();
        string source = Root("source");
        Write(source, "secret", "synthetic"u8.ToArray());
        Assert.Equal(0, Link(Path.Combine(source, "secret"), Path.Combine(source, "alias")));
        await Assert.ThrowsAsync<InvalidDataException>(() => new TeableRecoveryBundleStore(remote.Store())
            .CaptureAsync("hub", source, ["alias"]));
        Assert.Empty(remote.Rows);
    }

    [DllImport("libc", EntryPoint = "mkfifo", SetLastError = true)]
    private static extern int MkFifo(string path, uint mode);

    [DllImport("libc", EntryPoint = "link", SetLastError = true)]
    private static extern int Link(string source, string target);

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
