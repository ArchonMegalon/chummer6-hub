using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services;

public sealed class WindowsProofInstallerService
{
    private const string ProofInstallerRootKey = "CHUMMER_WINDOWS_PROOF_INSTALLER_ROOT";
    private const string ProofInstallerRootsKey = "CHUMMER_WINDOWS_PROOF_INSTALLER_ROOTS";
    private const string DownloadsRootKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    private const string PublicDisabledArtifactIdsKey = "CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS";
    private const string ReleaseDisabledArtifactIdsKey = "CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS";
    private const string DefaultDownloadsRoot = "/downloads-source";
    private static readonly string[] PreferredFileNames =
    {
        "chummer-avalonia-win-x64-installer.exe",
        "chummer-blazor-desktop-win-x64-installer.exe"
    };
    private static readonly byte[][] RequiredEmbeddedPayloadMarkers =
    {
        Encoding.UTF8.GetBytes("ChummerInstaller.Payload.zip"),
        Encoding.UTF8.GetBytes("Samples/Legacy/Soma-Career.chum5")
    };

    private readonly IConfiguration _configuration;

    public WindowsProofInstallerService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public IReadOnlyList<WindowsProofInstallerRecord> LoadCatalog(IReadOnlyCollection<string>? publishedArtifactIds = null)
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

        if (publishedArtifactIds is { Count: > 0 })
        {
            HashSet<string> publishedSet = publishedArtifactIds
                .Where(static artifactId => !string.IsNullOrWhiteSpace(artifactId))
                .Select(static artifactId => artifactId.Trim())
                .ToHashSet(StringComparer.OrdinalIgnoreCase);

            if (publishedSet.Count > 0)
            {
                rows = rows
                    .Where(row => !publishedSet.Contains(row.ArtifactId))
                    .ToList();
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

        if (IsDisabledArtifactId(ResolveArtifactId(allowedFileName)))
        {
            return null;
        }

        var proofFilePath = ResolveProofFilePath(allowedFileName);
        if (proofFilePath is null)
        {
            return null;
        }

        if (!HasEmbeddedPayloadMarkers(proofFilePath))
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
            DownloadUrl: $"/downloads/proof/windows/{Uri.EscapeDataString(allowedFileName)}",
            ArtifactId: ResolveArtifactId(allowedFileName));
    }

    public WindowsProofInstallerRecord? FindByArtifactId(string? artifactId)
    {
        string normalizedArtifactId = NormalizeArtifactId(artifactId);
        if (string.IsNullOrWhiteSpace(normalizedArtifactId))
        {
            return null;
        }

        if (IsDisabledArtifactId(normalizedArtifactId))
        {
            return null;
        }

        string? fileName = normalizedArtifactId switch
        {
            "avalonia-win-x64-installer" => "chummer-avalonia-win-x64-installer.exe",
            "blazor-desktop-win-x64-installer" => "chummer-blazor-desktop-win-x64-installer.exe",
            _ => null,
        };

        return fileName is null ? null : FindByFileName(fileName);
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
        yield return Path.GetFullPath(Path.Combine(downloadsRoot, "files"));
        yield return Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Chummer.Portal", "downloads", "proof", "windows"));
        yield return Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Chummer.Portal", "downloads", "files"));

        var configuredRoots = _configuration[ProofInstallerRootsKey]?.Trim();
        if (!string.IsNullOrWhiteSpace(configuredRoots))
        {
            foreach (string root in configuredRoots.Split(new[] { ',', ';', Path.PathSeparator }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                yield return Path.GetFullPath(root);
            }
        }
    }

    private static string NormalizeFileName(string? fileName)
        => Path.GetFileName((fileName ?? string.Empty).Trim());

    private static string NormalizeArtifactId(string? artifactId)
        => (artifactId ?? string.Empty).Trim().ToLowerInvariant();

    private static string ResolveHeadLabel(string fileName)
        => fileName.Contains("blazor-desktop", StringComparison.OrdinalIgnoreCase)
            ? "blazor-desktop"
            : "avalonia";

    private static string ResolveArtifactId(string fileName)
        => fileName.Contains("blazor-desktop", StringComparison.OrdinalIgnoreCase)
            ? "blazor-desktop-win-x64-installer"
            : "avalonia-win-x64-installer";

    private bool IsDisabledArtifactId(string artifactId)
    {
        if (string.IsNullOrWhiteSpace(artifactId))
        {
            return false;
        }

        HashSet<string> disabledArtifactIds = new(StringComparer.OrdinalIgnoreCase);
        AddDisabledArtifacts(disabledArtifactIds, _configuration[PublicDisabledArtifactIdsKey]);
        AddDisabledArtifacts(disabledArtifactIds, _configuration[ReleaseDisabledArtifactIdsKey]);
        return disabledArtifactIds.Contains(artifactId.Trim());
    }

    private static void AddDisabledArtifacts(HashSet<string> destination, string? rawValue)
    {
        if (string.IsNullOrWhiteSpace(rawValue))
        {
            return;
        }

        foreach (string value in rawValue.Split([',', ';', '\n', '\r', ' '], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                destination.Add(value.Trim());
            }
        }
    }

    private static string ComputeSha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    private static bool HasEmbeddedPayloadMarkers(string path)
    {
        byte[] bytes = File.ReadAllBytes(path);
        return RequiredEmbeddedPayloadMarkers.All(marker => bytes.AsSpan().IndexOf(marker) >= 0);
    }
}

public sealed record WindowsProofInstallerRecord(
    string ArtifactId,
    string FileName,
    string Head,
    string Rid,
    string FilePath,
    string Sha256,
    long SizeBytes,
    DateTime UpdatedAtUtc,
    string DownloadUrl);
