using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBundleUploadSessionServiceTests
{
    [Fact]
    public async Task WriteFileAsyncStoresRelativePathUnderBundleRoot()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();

        await fixture.Service.WriteFileAsync(
            session.SessionId,
            "files/chummer-avalonia-osx-x64-installer.dmg",
            new MemoryStream("mac"u8.ToArray()),
            CancellationToken.None);

        string filePath = Path.Combine(session.BundleRoot, "files", "chummer-avalonia-osx-x64-installer.dmg");
        Assert.True(File.Exists(filePath));
        Assert.Equal("mac", await File.ReadAllTextAsync(filePath));
    }

    [Fact]
    public void ResolveBundleRootRejectsInvalidSessionId()
    {
        using Fixture fixture = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() =>
            fixture.Service.ResolveBundleRoot("not-a-guid"));

        Assert.Contains("valid GUID", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task WriteFileAsyncRejectsInvalidSessionId()
    {
        using Fixture fixture = new();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.WriteFileAsync(
                "../bad-session-id",
                "files/chummer-avalonia-osx-x64-installer.dmg",
                new MemoryStream("mac"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("valid GUID", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task AppendChunkAsyncRejectsInvalidSessionId()
    {
        using Fixture fixture = new();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.AppendChunkAsync(
                "bad::session",
                "files/chummer-avalonia-win-x64.exe",
                0,
                1,
                new MemoryStream("hello"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("valid GUID", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task AppendChunkAsyncReassemblesChunkedFile()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();

        await fixture.Service.AppendChunkAsync(
            session.SessionId,
            "files/chummer-avalonia-win-x64.exe",
            0,
            2,
            new MemoryStream("hello "u8.ToArray()),
            CancellationToken.None);

        ReleaseUploadChunkResult result = await fixture.Service.AppendChunkAsync(
            session.SessionId,
            "files/chummer-avalonia-win-x64.exe",
            1,
            2,
            new MemoryStream("world"u8.ToArray()),
            CancellationToken.None);

        Assert.True(result.Completed);
        string filePath = Path.Combine(session.BundleRoot, "files", "chummer-avalonia-win-x64.exe");
        Assert.True(File.Exists(filePath));
        Assert.Equal("hello world", await File.ReadAllTextAsync(filePath));
    }

    [Fact]
    public async Task AppendChunkAsyncRejectsOutOfOrderChunks()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.AppendChunkAsync(
                session.SessionId,
                "files/chummer-avalonia-win-x64.exe",
                1,
                2,
                new MemoryStream("world"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("expected chunk 0", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ReadSessionMetadataRejectsExpiredSession()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();
        fixture.WriteSessionMetadata(session.SessionId, new ReleaseUploadSession(
            session.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            session.BundleRoot));

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() =>
            fixture.Service.WriteFileAsync(
                session.SessionId,
                "files/chummer-avalonia-osx-x64-installer.dmg",
                new MemoryStream("mac"u8.ToArray()),
                CancellationToken.None));

        Assert.Contains("upload session has expired", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ReadSessionMetadataRejectsTamperedSessionId()
    {
        using Fixture fixture = new();
        ReleaseUploadSession session = fixture.Service.CreateSession();
        fixture.WriteSessionMetadata(session.SessionId, new ReleaseUploadSession(
            Guid.NewGuid().ToString("N"),
            session.ExpiresAtUtc,
            session.BundleRoot));

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() =>
            fixture.Service.ResolveBundleRoot(session.SessionId));

        Assert.Contains("metadata is invalid", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "release-upload-session-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions")
                })
                .Build();
            Service = new ReleaseBundleUploadSessionService(configuration, NullLogger<ReleaseBundleUploadSessionService>.Instance);
        }

        public ReleaseBundleUploadSessionService Service { get; }

        public void WriteSessionMetadata(string sessionId, ReleaseUploadSession session)
        {
            string metadataPath = Path.Combine(_root, "sessions", sessionId, "session.json");
            Directory.CreateDirectory(Path.GetDirectoryName(metadataPath)!);
            File.WriteAllText(metadataPath, System.Text.Json.JsonSerializer.Serialize(session));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
