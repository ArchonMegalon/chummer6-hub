using System.Security.Cryptography;

namespace Chummer.Run.Api.Services;

public sealed class WindowsProofInstallerService
{
    private const string ProofInstallerRootKey = "CHUMMER_WINDOWS_PROOF_INSTALLER_ROOT";
    private const string DownloadsRootKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    private const string DefaultDownloadsRoot = "/downloads-source";
    private static readonly string[] PreferredFileNames =
    {
        "chummer-avalonia-win-x64-installer.exe",
        "chummer-blazor-desktop-win-x64-installer.exe"
    };

    private readonly IConfiguration _configuration;

    public WindowsProofInstallerService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public IReadOnlyList<WindowsProofInstallerRecord> LoadCatalog()
    {
        var rows = new List<WindowsProofInstallerRecord>();
        foreach (var fileName in PreferredFileNames)
        {
            var row = FindByFileName(fileName);
            if (row is not null)
            {
                rows.Add(row);
            }
        }

        return rows;
    }

    public WindowsProofInstallerRecord? FindByFileName(string? fileName)
    {
        var normalizedFileName = NormalizeFileName(fileName);
        if (string.IsNullOrWhiteSpace(normalizedFileName))
        {
            return null;
        }

        var allowedFileName = PreferredFileNames.FirstOrDefault(candidate =>
            string.Equals(candidate, normalizedFileName, StringComparison.OrdinalIgnoreCase));
        if (allowedFileName is null)
        {
            return null;
        }

        var proofFilePath = ResolveProofFilePath(allowedFileName);
        if (proofFilePath is null)
        {
            return null;
        }

        var info = new FileInfo(proofFilePath);
        return new WindowsProofInstallerRecord(
            FileName: allowedFileName,
            Head: ResolveHeadLabel(allowedFileName),
            Rid: "win-x64",
            FilePath: proofFilePath,
            Sha256: ComputeSha256(proofFilePath),
            SizeBytes: info.Length,
            UpdatedAtUtc: info.LastWriteTimeUtc,
            DownloadUrl: $"/downloads/proof/windows/{Uri.EscapeDataString(allowedFileName)}");
    }

    private string? ResolveProofFilePath(string fileName)
    {
        foreach (var root in ResolveCandidateRoots())
        {
            var candidate = Path.Combine(root, fileName);
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private IEnumerable<string> ResolveCandidateRoots()
    {
        var configuredRoot = _configuration[ProofInstallerRootKey]?.Trim();
        if (!string.IsNullOrWhiteSpace(configuredRoot))
        {
            yield return Path.GetFullPath(configuredRoot);
        }

        var downloadsRoot = _configuration[DownloadsRootKey]?.Trim();
        if (string.IsNullOrWhiteSpace(downloadsRoot))
        {
            downloadsRoot = DefaultDownloadsRoot;
        }

        yield return Path.GetFullPath(Path.Combine(downloadsRoot, "proof", "windows"));
        yield return Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Chummer.Portal", "downloads", "proof", "windows"));
        yield return "/docker/chummercomplete/chummer-presentation/Chummer.Portal/downloads/proof/windows";
        yield return "/docker/chummercomplete/chummer-presentation/dist-proof";
    }

    private static string NormalizeFileName(string? fileName)
        => Path.GetFileName((fileName ?? string.Empty).Trim());

    private static string ResolveHeadLabel(string fileName)
        => fileName.Contains("blazor-desktop", StringComparison.OrdinalIgnoreCase)
            ? "blazor-desktop"
            : "avalonia";

    private static string ComputeSha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }
}

public sealed record WindowsProofInstallerRecord(
    string FileName,
    string Head,
    string Rid,
    string FilePath,
    string Sha256,
    long SizeBytes,
    DateTime UpdatedAtUtc,
    string DownloadUrl);
