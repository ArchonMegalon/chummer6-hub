using Chummer.Run.Api.Services.WindowsProof;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed class WindowsProofInstallerService
{
    private const string LegacyShelfFallbackKey = "CHUMMER_WINDOWS_PROOF_LEGACY_SHELF_FALLBACK";
    private const string ProofInstallerRootKey = "CHUMMER_WINDOWS_PROOF_INSTALLER_ROOT";
    private const string ProofInstallerRootsKey = "CHUMMER_WINDOWS_PROOF_INSTALLER_ROOTS";
    private const string DownloadsRootKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    private const string PublicDisabledArtifactIdsKey = "CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS";
    private const string ReleaseDisabledArtifactIdsKey = "CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS";
    private const string ReleaseRevokedSha256Key = "CHUMMER_RELEASE_REVOKED_SHA256";
    private const string DefaultDownloadsRoot = "/downloads-source";
    private const string SigningReceiptContractName = "chummer6-ui.desktop_artifact_signing";
    private const int MaximumSigningReceiptBytes = 128 * 1024;
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
    private readonly ReleaseShelfGenerationStore _shelfStore;
    private readonly IWindowsProofGenerationStore? _proofStore;

    public bool LegacyShelfFallbackEnabled
        => string.Equals(
            _configuration[LegacyShelfFallbackKey]?.Trim(),
            "true",
            StringComparison.OrdinalIgnoreCase);

    public WindowsProofInstallerService(IConfiguration configuration)
        : this(configuration, new ReleaseShelfGenerationStore(configuration), proofStore: null)
    {
    }

    public WindowsProofInstallerService(
        IConfiguration configuration,
        ReleaseShelfGenerationStore shelfStore)
        : this(configuration, shelfStore, proofStore: null)
    {
    }

    public WindowsProofInstallerService(
        IConfiguration configuration,
        ReleaseShelfGenerationStore shelfStore,
        IWindowsProofGenerationStore? proofStore)
    {
        _configuration = configuration;
        _shelfStore = shelfStore ?? throw new ArgumentNullException(nameof(shelfStore));
        _proofStore = proofStore;
    }

    public WindowsProofDeliverySnapshot? CaptureCurrentProof()
        => TryCaptureProof(static store => store.CaptureCurrent());

    public WindowsProofDeliverySnapshot? CaptureProofGeneration(string? generationId)
    {
        string normalizedGenerationId = (generationId ?? string.Empty).Trim();
        if (!IsPortableIdentifier(normalizedGenerationId)
            || !string.Equals(normalizedGenerationId, generationId, StringComparison.Ordinal))
        {
            return null;
        }

        return TryCaptureProof(store => store.CaptureGeneration(normalizedGenerationId));
    }

    public WindowsProofDeliverySnapshot? CaptureProofCandidate(string? candidateVersion)
    {
        string normalizedCandidateVersion = (candidateVersion ?? string.Empty).Trim();
        if (!IsPortableIdentifier(normalizedCandidateVersion)
            || !string.Equals(normalizedCandidateVersion, candidateVersion, StringComparison.Ordinal))
        {
            return null;
        }

        WindowsProofDeliverySnapshot? snapshot = TryCaptureProof(
            store => store.CaptureCandidate(normalizedCandidateVersion));
        return snapshot is not null
            && string.Equals(snapshot.CandidateVersion, normalizedCandidateVersion, StringComparison.Ordinal)
                ? snapshot
                : null;
    }

    private WindowsProofDeliverySnapshot? TryCaptureProof(
        Func<IWindowsProofGenerationStore, WindowsProofGenerationSnapshot?> capture)
    {
        if (_proofStore is null)
        {
            return null;
        }

        try
        {
            return TryCreateDeliverySnapshot(capture(_proofStore));
        }
        catch (InvalidDataException)
        {
            return null;
        }
        catch (InvalidOperationException)
        {
            return null;
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    public WindowsProofDeliveryArtifact? FindProofArtifact(
        WindowsProofDeliverySnapshot snapshot,
        string? artifactId,
        string? role)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string normalizedArtifactId = (artifactId ?? string.Empty).Trim();
        string normalizedRole = NormalizeProofRole(role);
        if (normalizedArtifactId.Length == 0
            || normalizedRole.Length == 0
            || IsDisabledArtifactId(normalizedArtifactId))
        {
            return null;
        }

        WindowsProofDeliveryArtifact? match = null;
        foreach (WindowsProofDeliveryArtifact artifact in snapshot.Artifacts)
        {
            if (!string.Equals(artifact.ArtifactId, normalizedArtifactId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(artifact.Role, normalizedRole, StringComparison.Ordinal))
            {
                continue;
            }

            if (match is not null)
            {
                return null;
            }

            match = artifact;
        }

        return match;
    }

    public WindowsProofDeliveryArtifact? FindProofInstallerByFileName(
        WindowsProofDeliverySnapshot snapshot,
        string? fileName)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string normalizedFileName = NormalizeFileName(fileName);
        if (normalizedFileName.Length == 0)
        {
            return null;
        }

        WindowsProofDeliveryArtifact? match = null;
        foreach (WindowsProofDeliveryArtifact artifact in snapshot.Artifacts)
        {
            if (!string.Equals(artifact.Role, WindowsProofDeliveryRoles.Installer, StringComparison.Ordinal)
                || !string.Equals(artifact.FileName, normalizedFileName, StringComparison.OrdinalIgnoreCase)
                || IsDisabledArtifactId(artifact.ArtifactId))
            {
                continue;
            }

            if (match is not null)
            {
                return null;
            }

            match = artifact;
        }

        return match;
    }

    public WindowsProofDeliveryArtifact? FindUniqueProofArtifactByRole(
        WindowsProofDeliverySnapshot snapshot,
        string? role)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string normalizedRole = NormalizeProofRole(role);
        if (normalizedRole.Length == 0)
        {
            return null;
        }

        WindowsProofDeliveryArtifact? match = null;
        foreach (WindowsProofDeliveryArtifact artifact in snapshot.Artifacts)
        {
            if (!string.Equals(artifact.Role, normalizedRole, StringComparison.Ordinal)
                || IsDisabledArtifactId(artifact.ArtifactId))
            {
                continue;
            }

            if (match is not null)
            {
                return null;
            }

            match = artifact;
        }

        return match;
    }

    public WindowsProofDeliveryArtifact? FindProofArtifactByFileName(
        WindowsProofDeliverySnapshot snapshot,
        string? fileName)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string normalizedFileName = NormalizeFileName(fileName);
        if (normalizedFileName.Length == 0
            || !string.Equals(normalizedFileName, fileName, StringComparison.Ordinal))
        {
            return null;
        }

        WindowsProofDeliveryArtifact? match = null;
        foreach (WindowsProofDeliveryArtifact artifact in snapshot.Artifacts)
        {
            if (!string.Equals(artifact.FileName, normalizedFileName, StringComparison.OrdinalIgnoreCase)
                || IsDisabledArtifactId(artifact.ArtifactId))
            {
                continue;
            }

            if (match is not null)
            {
                return null;
            }

            match = artifact;
        }

        return match;
    }

    public Stream? OpenVerifiedProofArtifact(
        WindowsProofDeliverySnapshot snapshot,
        WindowsProofDeliveryArtifact artifact)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(artifact);
        WindowsProofDeliveryArtifact? bound = null;
        foreach (WindowsProofDeliveryArtifact candidate in snapshot.Artifacts)
        {
            if (!ReferenceEquals(candidate.InventoryEntry, artifact.InventoryEntry)
                || !string.Equals(candidate.Sha256, artifact.Sha256, StringComparison.Ordinal)
                || candidate.SizeBytes != artifact.SizeBytes)
            {
                continue;
            }

            if (bound is not null)
            {
                return null;
            }

            bound = candidate;
        }
        if (bound is null || IsDisabledArtifactId(bound.ArtifactId))
        {
            return null;
        }

        try
        {
            Stream stream = snapshot.Source.OpenVerifiedArtifact(bound.InventoryEntry);
            if (!stream.CanRead || stream.Length != bound.SizeBytes)
            {
                stream.Dispose();
                return null;
            }

            return stream;
        }
        catch (InvalidDataException)
        {
            return null;
        }
        catch (InvalidOperationException)
        {
            return null;
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    private WindowsProofDeliverySnapshot? TryCreateDeliverySnapshot(
        WindowsProofGenerationSnapshot? snapshot)
    {
        if (snapshot is null
            || !IsProofDeliveryRuntimeEnabled()
            || !IsProofOnlyManifest(snapshot.Manifest))
        {
            return null;
        }

        if (!TryLoadRevokedDigests(out HashSet<string>? revokedDigests))
        {
            return null;
        }

        var artifacts = new List<WindowsProofDeliveryArtifact>(snapshot.Inventory.Count);
        var uniqueBindings = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (WindowsProofInventoryEntry entry in snapshot.Inventory)
        {
            string role = ResolveProofRole(entry.Kind);
            string artifactId = entry.ArtifactId.Trim();
            string fileName = NormalizeFileName(entry.FileName);
            string sha256 = NormalizeSha256(entry.Sha256);
            if (role.Length == 0
                || artifactId.Length == 0
                || fileName.Length == 0
                || !string.Equals(fileName, entry.FileName, StringComparison.Ordinal)
                || sha256.Length != 64
                || revokedDigests!.Contains(sha256)
                || entry.Size <= 0
                || IsDisabledArtifactId(artifactId)
                || !uniqueBindings.Add($"{artifactId}\n{role}"))
            {
                return null;
            }

            string escapedGenerationId = Uri.EscapeDataString(snapshot.GenerationId);
            string escapedCandidateVersion = Uri.EscapeDataString(snapshot.CandidateVersion);
            string escapedArtifactId = Uri.EscapeDataString(artifactId);
            string escapedRole = Uri.EscapeDataString(role);
            artifacts.Add(new WindowsProofDeliveryArtifact(
                ArtifactId: artifactId,
                Head: entry.Head,
                Rid: entry.Rid,
                Role: role,
                FileName: fileName,
                ContentType: ResolveProofContentType(entry.Kind),
                Sha256: sha256,
                SizeBytes: entry.Size,
                CurrentDownloadUrl: $"/downloads/proof/windows/current/artifacts/{escapedArtifactId}/{escapedRole}",
                GenerationDownloadUrl: $"/downloads/proof/windows/generations/{escapedGenerationId}/artifacts/{escapedArtifactId}/{escapedRole}",
                CandidateDownloadUrl: $"/downloads/proof/windows/candidates/{escapedCandidateVersion}/artifacts/{escapedArtifactId}/{escapedRole}",
                InventoryEntry: entry));
        }

        if (!HasRequiredProofInventory(
                artifacts,
                requireBuildProvenance: string.Equals(
                    snapshot.Manifest.SchemaVersion,
                    WindowsProofManifestValidator.ManifestSchemaVersion,
                    StringComparison.Ordinal)))
        {
            return null;
        }

        return new WindowsProofDeliverySnapshot(
            snapshot.GenerationId,
            snapshot.CandidateVersion,
            snapshot.CreatedAt,
            snapshot.ActivatedAt,
            snapshot.RevocationGeneration,
            artifacts,
            snapshot);
    }

    private bool IsProofDeliveryRuntimeEnabled()
        => string.Equals(
            _configuration["CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED"]?.Trim(),
            "true",
            StringComparison.OrdinalIgnoreCase);

    private static bool IsProofOnlyManifest(WindowsProofManifest manifest)
    {
        if (manifest.SchemaVersion is not (
                WindowsProofManifestValidator.ManifestSchemaVersion
                or WindowsProofManifestValidator.LegacyManifestSchemaVersion)
            || !TokenEquals(manifest.Channel, "preview")
            || !TokenEquals(manifest.ReleaseScope, "proof_only")
            || !TokenEquals(manifest.SupportabilityState, "review_required")
            || !TokenEquals(manifest.PublicTrustPosture, "blocked")
            || !manifest.CfAccessGated
            || manifest.Revoked
            || !manifest.ProofOnlyPolicy.Enabled
            || !manifest.ProofOnlyPolicy.NativeWindowsValidationRequired)
        {
            return false;
        }

        bool signed = TokenEquals(manifest.Signing.Status, "pass");
        bool explicitUnsignedPreview = manifest.ProofOnlyPolicy.UnsignedPreviewAllowed
            && manifest.Signing.ProofOnlyPolicyRecorded
            && (TokenEquals(manifest.Signing.Status, "skipped_preview")
                || TokenEquals(manifest.Signing.Status, "unsigned_preview"));
        return signed || explicitUnsignedPreview;
    }

    private static bool HasRequiredProofInventory(
        IReadOnlyCollection<WindowsProofDeliveryArtifact> artifacts,
        bool requireBuildProvenance)
    {
        foreach (IGrouping<string, WindowsProofDeliveryArtifact> group in artifacts.GroupBy(
            static artifact => artifact.ArtifactId,
            StringComparer.OrdinalIgnoreCase))
        {
            HashSet<string> roles = group
                .Select(static artifact => artifact.Role)
                .ToHashSet(StringComparer.Ordinal);
            bool hasPayload = roles.Contains(WindowsProofDeliveryRoles.BootstrapPayload);
            bool hasMetadata = roles.Contains(WindowsProofDeliveryRoles.BootstrapMetadata);
            if (roles.Contains(WindowsProofDeliveryRoles.Installer)
                && hasPayload == hasMetadata
                && roles.Contains(WindowsProofDeliveryRoles.Signing)
                && roles.Contains(WindowsProofDeliveryRoles.StartupSmoke)
                && (!requireBuildProvenance
                    || (roles.Contains(WindowsProofDeliveryRoles.BuildProvenance)
                        && roles.Contains(WindowsProofDeliveryRoles.Sbom)))
                && roles.Contains(WindowsProofDeliveryRoles.VisualHandoff))
            {
                return true;
            }
        }

        return false;
    }

    private static string ResolveProofRole(WindowsProofArtifactKind kind)
        => kind switch
        {
            WindowsProofArtifactKind.Installer => WindowsProofDeliveryRoles.Installer,
            WindowsProofArtifactKind.BootstrapPayload => WindowsProofDeliveryRoles.BootstrapPayload,
            WindowsProofArtifactKind.BootstrapMetadata => WindowsProofDeliveryRoles.BootstrapMetadata,
            WindowsProofArtifactKind.SigningReceipt => WindowsProofDeliveryRoles.Signing,
            WindowsProofArtifactKind.StartupSmokeReceipt => WindowsProofDeliveryRoles.StartupSmoke,
            WindowsProofArtifactKind.BuildProvenanceReceipt => WindowsProofDeliveryRoles.BuildProvenance,
            WindowsProofArtifactKind.Sbom => WindowsProofDeliveryRoles.Sbom,
            WindowsProofArtifactKind.VisualHandoff => WindowsProofDeliveryRoles.VisualHandoff,
            WindowsProofArtifactKind.VisualExitEvidence => WindowsProofDeliveryRoles.VisualExit,
            _ => string.Empty,
        };

    private static string NormalizeProofRole(string? role)
    {
        string normalized = (role ?? string.Empty).Trim().ToLowerInvariant();
        return normalized switch
        {
            WindowsProofDeliveryRoles.Installer => WindowsProofDeliveryRoles.Installer,
            WindowsProofDeliveryRoles.BootstrapPayload => WindowsProofDeliveryRoles.BootstrapPayload,
            "bootstrap-payload" => WindowsProofDeliveryRoles.BootstrapPayload,
            WindowsProofDeliveryRoles.BootstrapMetadata => WindowsProofDeliveryRoles.BootstrapMetadata,
            "bootstrap-metadata" => WindowsProofDeliveryRoles.BootstrapMetadata,
            WindowsProofDeliveryRoles.Signing => WindowsProofDeliveryRoles.Signing,
            WindowsProofDeliveryRoles.StartupSmoke => WindowsProofDeliveryRoles.StartupSmoke,
            WindowsProofDeliveryRoles.BuildProvenance => WindowsProofDeliveryRoles.BuildProvenance,
            WindowsProofDeliveryRoles.Sbom => WindowsProofDeliveryRoles.Sbom,
            WindowsProofDeliveryRoles.VisualHandoff => WindowsProofDeliveryRoles.VisualHandoff,
            WindowsProofDeliveryRoles.VisualExit => WindowsProofDeliveryRoles.VisualExit,
            _ => string.Empty,
        };
    }

    private static string ResolveProofContentType(WindowsProofArtifactKind kind)
        => kind switch
        {
            WindowsProofArtifactKind.Installer => "application/vnd.microsoft.portable-executable",
            WindowsProofArtifactKind.BootstrapPayload => "application/zip",
            WindowsProofArtifactKind.Sbom => "application/vnd.cyclonedx+json",
            _ => "application/json; charset=utf-8",
        };

    private static bool TokenEquals(string? actual, string expected)
        => string.Equals(
            (actual ?? string.Empty).Trim(),
            expected,
            StringComparison.OrdinalIgnoreCase);

    private static string NormalizeSha256(string? sha256)
    {
        string normalized = (sha256 ?? string.Empty).Trim().ToLowerInvariant();
        if (normalized.Length != 64)
        {
            return string.Empty;
        }

        try
        {
            return Convert.FromHexString(normalized).Length == 32
                ? normalized
                : string.Empty;
        }
        catch (FormatException)
        {
            return string.Empty;
        }
    }

    private static bool IsPortableIdentifier(string value)
        => value.Length is >= 1 and <= 128
            && char.IsAsciiLetterOrDigit(value[0])
            && !value.Contains("..", StringComparison.Ordinal)
            && value.All(static character => char.IsAsciiLetterOrDigit(character)
                || character is '.' or '_' or '-');

    public IReadOnlyList<WindowsProofInstallerRecord> LoadCatalog(IReadOnlyCollection<string>? publishedArtifactIds = null)
        => LoadCatalog(_shelfStore.CaptureForCurrentRequest(), publishedArtifactIds);

    public IReadOnlyList<WindowsProofInstallerRecord> LoadCatalog(
        ReleaseShelfSnapshot snapshot,
        IReadOnlyCollection<string>? publishedArtifactIds = null)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var rows = new List<WindowsProofInstallerRecord>();
        foreach (var fileName in PreferredFileNames)
        {
            var row = FindByFileName(snapshot, fileName);
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
        => FindByFileName(_shelfStore.CaptureForCurrentRequest(), fileName);

    public WindowsProofInstallerRecord? FindByFileName(
        ReleaseShelfSnapshot snapshot,
        string? fileName)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
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

        string head = ResolveHeadLabel(allowedFileName);
        string artifactId = ResolveArtifactId(allowedFileName);
        string relativePath = $"proof/windows/{allowedFileName}";
        if (!snapshot.IsLegacy)
        {
            using ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile(relativePath);
            if (verified is null
                || string.IsNullOrWhiteSpace(verified.ExpectedSha256)
                || !HasEmbeddedPayloadMarkers(verified.Stream)
                || !HasCurrentSigningProof(
                    snapshot,
                    allowedFileName,
                    head,
                    verified.ExpectedSha256))
            {
                return null;
            }

            return new WindowsProofInstallerRecord(
                FileName: allowedFileName,
                Head: head,
                Rid: "win-x64",
                RelativePath: relativePath,
                LegacyFilePath: null,
                Sha256: verified.ExpectedSha256!,
                SizeBytes: verified.SizeBytes,
                UpdatedAtUtc: snapshot.PublishedAt?.UtcDateTime ?? DateTime.UnixEpoch,
                DownloadUrl: $"/downloads/proof/windows/generations/{Uri.EscapeDataString(snapshot.GenerationId!)}/files/{Uri.EscapeDataString(allowedFileName)}",
                ArtifactId: artifactId);
        }

        var proofFilePath = ResolveLegacyProofFilePath(snapshot, allowedFileName);
        if (proofFilePath is null || !HasEmbeddedPayloadMarkers(proofFilePath))
        {
            return null;
        }
        string sha256 = ComputeSha256(proofFilePath);
        if (!HasCurrentSigningProof(snapshot, allowedFileName, head, sha256))
        {
            return null;
        }
        var info = new FileInfo(proofFilePath);
        return new WindowsProofInstallerRecord(
            FileName: allowedFileName,
            Head: head,
            Rid: "win-x64",
            RelativePath: relativePath,
            LegacyFilePath: proofFilePath,
            Sha256: sha256,
            SizeBytes: info.Length,
            UpdatedAtUtc: info.LastWriteTimeUtc,
            DownloadUrl: $"/downloads/proof/windows/{Uri.EscapeDataString(allowedFileName)}",
            ArtifactId: artifactId);
    }

    public WindowsProofInstallerRecord? FindByArtifactId(string? artifactId)
        => FindByArtifactId(_shelfStore.CaptureForCurrentRequest(), artifactId);

    public WindowsProofInstallerRecord? FindByArtifactId(
        ReleaseShelfSnapshot snapshot,
        string? artifactId)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
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

        return fileName is null ? null : FindByFileName(snapshot, fileName);
    }

    public ReleaseShelfVerifiedFile? OpenVerifiedInstaller(
        ReleaseShelfSnapshot snapshot,
        WindowsProofInstallerRecord installer)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(installer);
        if (snapshot.IsLegacy)
        {
            if (string.IsNullOrWhiteSpace(installer.LegacyFilePath))
            {
                return null;
            }

            FileStream? stream = null;
            try
            {
                stream = new FileStream(
                    installer.LegacyFilePath,
                    FileMode.Open,
                    FileAccess.Read,
                    FileShare.Read,
                    bufferSize: 64 * 1024,
                    FileOptions.SequentialScan);
                if (stream.Length != installer.SizeBytes)
                {
                    stream.Dispose();
                    return null;
                }

                string actualSha256 = Convert.ToHexStringLower(SHA256.HashData(stream));
                stream.Position = 0;
                if (!FixedTimeSha256Equals(installer.Sha256, actualSha256)
                    || !HasEmbeddedPayloadMarkers(stream)
                    || !HasCurrentSigningProof(
                        snapshot,
                        installer.FileName,
                        installer.Head,
                        actualSha256))
                {
                    stream.Dispose();
                    return null;
                }

                return new ReleaseShelfVerifiedFile(
                    installer.LegacyFilePath,
                    installer.RelativePath,
                    actualSha256,
                    stream.Length,
                    stream);
            }
            catch (IOException)
            {
                stream?.Dispose();
                return null;
            }
            catch (UnauthorizedAccessException)
            {
                stream?.Dispose();
                return null;
            }
        }

        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile(installer.RelativePath);
        if (verified is null
            || !string.Equals(verified.ExpectedSha256, installer.Sha256, StringComparison.Ordinal)
            || verified.SizeBytes != installer.SizeBytes
            || !HasEmbeddedPayloadMarkers(verified.Stream)
            || !HasCurrentSigningProof(
                snapshot,
                installer.FileName,
                installer.Head,
                installer.Sha256))
        {
            verified?.Dispose();
            return null;
        }

        return verified;
    }

    private string? ResolveLegacyProofFilePath(ReleaseShelfSnapshot snapshot, string fileName)
    {
        foreach (var root in ResolveCandidateRoots(snapshot))
        {
            var candidate = Path.Combine(root, fileName);
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private IEnumerable<string> ResolveCandidateRoots(ReleaseShelfSnapshot snapshot)
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

    private bool TryLoadRevokedDigests(out HashSet<string>? digests)
    {
        digests = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        string raw = _configuration[ReleaseRevokedSha256Key] ?? string.Empty;
        foreach (string token in raw.Split(
            [',', ';', '\n', '\r', '\t', ' '],
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            string digest = token.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
                ? token["sha256:".Length..]
                : token;
            digest = NormalizeSha256(digest);
            if (digest.Length == 0)
            {
                digests = null;
                return false;
            }

            digests.Add(digest);
        }

        return true;
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

    private bool HasCurrentSigningProof(
        ReleaseShelfSnapshot snapshot,
        string fileName,
        string head,
        string expectedSha256)
    {
        if (!TryResolveReleaseIdentity(snapshot, out string releaseVersion, out string releaseChannel))
        {
            return false;
        }

        string relativeReceiptPath = $"signing/signing-{head}-win-x64.receipt.json";
        byte[]? receiptBytes = snapshot.ReadVerifiedFileBytes(
            relativeReceiptPath,
            MaximumSigningReceiptBytes);
        if (receiptBytes is null)
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(receiptBytes);
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !StringPropertyEquals(root, "contractName", SigningReceiptContractName)
                || !TokenPropertyEquals(root, "platform", "windows")
                || !TokenPropertyEquals(root, "app", head)
                || !TokenPropertyEquals(root, "rid", "win-x64")
                || !StringPropertyEquals(root, "releaseVersion", releaseVersion)
                || !TokenPropertyEquals(root, "releaseChannel", releaseChannel)
                || !TokenPropertyEquals(root, "signingStatus", "pass")
                || !root.TryGetProperty("artifacts", out JsonElement artifacts)
                || artifacts.ValueKind != JsonValueKind.Array)
            {
                return false;
            }

            JsonElement? matchingArtifact = null;
            foreach (JsonElement artifact in artifacts.EnumerateArray())
            {
                if (artifact.ValueKind != JsonValueKind.Object
                    || !StringPropertyEquals(artifact, "fileName", fileName))
                {
                    continue;
                }

                if (matchingArtifact is not null)
                {
                    return false;
                }
                matchingArtifact = artifact;
            }

            if (matchingArtifact is not JsonElement match
                || !TokenPropertyEquals(match, "kind", "installer")
                || !TokenPropertyEquals(match, "signingStatus", "pass")
                || !TryGetRequiredString(match, "sha256", out string receiptSha256)
                || !FixedTimeSha256Equals(receiptSha256, expectedSha256))
            {
                return false;
            }

            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool TryResolveReleaseIdentity(
        ReleaseShelfSnapshot snapshot,
        out string releaseVersion,
        out string releaseChannel)
    {
        releaseVersion = (snapshot.ReleaseVersion ?? string.Empty).Trim();
        releaseChannel = NormalizeToken(snapshot.Channel);
        if (!string.IsNullOrWhiteSpace(releaseVersion)
            && !string.IsNullOrWhiteSpace(releaseChannel))
        {
            return true;
        }

        byte[]? manifestBytes = snapshot.ReadVerifiedFileBytes(
            ReleaseShelfGenerationStore.CanonicalManifestFileName,
            ReleaseShelfGenerationStore.MaximumManifestBytes);
        if (manifestBytes is null)
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(manifestBytes);
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !TryResolveRequiredAlias(root, "version", "releaseVersion", out releaseVersion)
                || !TryResolveRequiredAlias(root, "channelId", "channel", out releaseChannel)
                || !TokenPropertyEquals(root, "status", "published"))
            {
                releaseVersion = string.Empty;
                releaseChannel = string.Empty;
                return false;
            }

            releaseChannel = NormalizeToken(releaseChannel);
            return !string.IsNullOrWhiteSpace(releaseVersion)
                && !string.IsNullOrWhiteSpace(releaseChannel);
        }
        catch (JsonException)
        {
            releaseVersion = string.Empty;
            releaseChannel = string.Empty;
            return false;
        }
    }

    private static bool TryResolveRequiredAlias(
        JsonElement source,
        string primaryName,
        string secondaryName,
        out string value)
    {
        bool hasPrimary = TryGetRequiredString(source, primaryName, out string primary);
        bool hasSecondary = TryGetRequiredString(source, secondaryName, out string secondary);
        if (!hasPrimary && !hasSecondary)
        {
            value = string.Empty;
            return false;
        }

        if (hasPrimary && hasSecondary
            && !string.Equals(primary, secondary, StringComparison.Ordinal))
        {
            value = string.Empty;
            return false;
        }

        value = hasPrimary ? primary : secondary;
        return true;
    }

    private static bool StringPropertyEquals(
        JsonElement source,
        string propertyName,
        string expected)
        => TryGetRequiredString(source, propertyName, out string actual)
            && string.Equals(actual, expected, StringComparison.Ordinal);

    private static bool TokenPropertyEquals(
        JsonElement source,
        string propertyName,
        string expected)
        => TryGetRequiredString(source, propertyName, out string actual)
            && string.Equals(NormalizeToken(actual), NormalizeToken(expected), StringComparison.Ordinal);

    private static bool TryGetRequiredString(
        JsonElement source,
        string propertyName,
        out string value)
    {
        value = string.Empty;
        if (!source.TryGetProperty(propertyName, out JsonElement element)
            || element.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        string raw = element.GetString() ?? string.Empty;
        string trimmed = raw.Trim();
        if (trimmed.Length == 0 || !string.Equals(raw, trimmed, StringComparison.Ordinal))
        {
            return false;
        }

        value = trimmed;
        return true;
    }

    private static string NormalizeToken(string? value)
        => (value ?? string.Empty).Trim().ToLowerInvariant();

    private static bool FixedTimeSha256Equals(string expected, string actual)
    {
        try
        {
            byte[] expectedBytes = Convert.FromHexString(expected);
            byte[] actualBytes = Convert.FromHexString(actual);
            return expectedBytes.Length == 32
                && actualBytes.Length == 32
                && CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static bool HasEmbeddedPayloadMarkers(string path)
    {
        byte[] bytes = File.ReadAllBytes(path);
        return RequiredEmbeddedPayloadMarkers.All(marker => bytes.AsSpan().IndexOf(marker) >= 0);
    }

    private static bool HasEmbeddedPayloadMarkers(Stream stream)
    {
        if (!stream.CanSeek || stream.Length > int.MaxValue)
        {
            return false;
        }

        byte[] bytes = new byte[checked((int)stream.Length)];
        stream.ReadExactly(bytes);
        stream.Position = 0;
        return RequiredEmbeddedPayloadMarkers.All(marker => bytes.AsSpan().IndexOf(marker) >= 0);
    }
}

public sealed record WindowsProofInstallerRecord(
    string ArtifactId,
    string FileName,
    string Head,
    string Rid,
    string RelativePath,
    string? LegacyFilePath,
    string Sha256,
    long SizeBytes,
    DateTime UpdatedAtUtc,
    string DownloadUrl);

public static class WindowsProofDeliveryRoles
{
    public const string Installer = "installer";
    public const string BootstrapPayload = "payload";
    public const string BootstrapMetadata = "metadata";
    public const string Signing = "signing";
    public const string StartupSmoke = "startup-smoke";
    public const string BuildProvenance = "build-provenance";
    public const string Sbom = "sbom";
    public const string VisualHandoff = "visual-handoff";
    public const string VisualExit = "visual-exit";
}

public sealed record WindowsProofDeliverySnapshot(
    string GenerationId,
    string CandidateVersion,
    DateTimeOffset CreatedAt,
    DateTimeOffset? ActivatedAt,
    long RevocationGeneration,
    IReadOnlyList<WindowsProofDeliveryArtifact> Artifacts,
    WindowsProofGenerationSnapshot Source);

public sealed record WindowsProofDeliveryArtifact(
    string ArtifactId,
    string Head,
    string Rid,
    string Role,
    string FileName,
    string ContentType,
    string Sha256,
    long SizeBytes,
    string CurrentDownloadUrl,
    string GenerationDownloadUrl,
    string CandidateDownloadUrl,
    WindowsProofInventoryEntry InventoryEntry);
