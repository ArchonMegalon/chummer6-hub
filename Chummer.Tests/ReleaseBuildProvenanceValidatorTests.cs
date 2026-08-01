using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBuildProvenanceValidatorTests
{
    [Fact]
    public void ValidateAcceptsLinuxWindowsAndArtifactSpecificWindowsPayloadProvenance()
    {
        using TemporaryDirectory temporary = new();
        string filesRoot = Path.Combine(temporary.Path, "files");
        Directory.CreateDirectory(filesRoot);

        byte[] linuxBytes = "linux-installer"u8.ToArray();
        byte[] windowsBytes = "windows-bootstrap"u8.ToArray();
        byte[] payloadBytes = "windows-payload"u8.ToArray();
        File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-linux-x64-installer.deb"), linuxBytes);
        File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-win-x64-installer.exe"), windowsBytes);
        File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-win-x64-payload.zip"), payloadBytes);

        JsonObject manifest = new()
        {
            ["artifacts"] = new JsonArray
            {
                Artifact(
                    "avalonia-linux-x64-installer",
                    "linux",
                    "chummer-avalonia-linux-x64-installer.deb",
                    linuxBytes),
                Artifact(
                    "avalonia-win-x64-installer",
                    "windows",
                    "chummer-avalonia-win-x64-installer.exe",
                    windowsBytes,
                    "chummer-avalonia-win-x64-payload.zip",
                    payloadBytes)
            }
        };
        MacBuildProvenanceTestFixture.WriteFiles(
            temporary.Path,
            [
                new MacBuildProvenanceSubject(
                    "avalonia-linux-x64-installer",
                    "avalonia",
                    "chummer-avalonia-linux-x64-installer.deb",
                    linuxBytes,
                    "linux"),
                new MacBuildProvenanceSubject(
                    "avalonia-win-x64-installer",
                    "avalonia",
                    "chummer-avalonia-win-x64-installer.exe",
                    windowsBytes,
                    "windows"),
                new MacBuildProvenanceSubject(
                    "avalonia-win-x64-installer-payload",
                    "avalonia",
                    "chummer-avalonia-win-x64-payload.zip",
                    payloadBytes,
                    "windows",
                    "desktop_payload")
            ]);

        ReleaseBuildProvenanceValidator.Validate(
            manifest,
            filesRoot,
            Path.Combine(temporary.Path, "proof"));
    }

    private static JsonObject Artifact(
        string artifactId,
        string platform,
        string fileName,
        byte[] bytes,
        string? payloadFileName = null,
        byte[]? payloadBytes = null)
    {
        JsonObject result = new()
        {
            ["artifactId"] = artifactId,
            ["head"] = "avalonia",
            ["platform"] = platform,
            ["fileName"] = fileName,
            ["sha256"] = Sha256For(bytes),
            ["sizeBytes"] = bytes.LongLength
        };
        if (payloadFileName is not null && payloadBytes is not null)
        {
            result["payloadFileName"] = payloadFileName;
            result["payloadSha256"] = Sha256For(payloadBytes);
            result["payloadSizeBytes"] = payloadBytes.LongLength;
        }
        return result;
    }

    private static string Sha256For(byte[] bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes));

    private sealed class TemporaryDirectory : IDisposable
    {
        public TemporaryDirectory()
        {
            Path = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(),
                $"chummer-release-build-provenance-{Guid.NewGuid():N}");
            Directory.CreateDirectory(Path);
        }

        public string Path { get; }

        public void Dispose()
            => Directory.Delete(Path, recursive: true);
    }
}
