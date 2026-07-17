using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Globalization;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Hosting;
using Microsoft.Win32.SafeHandles;

namespace Chummer.Run.Api.Services;

public sealed class PortalDeploymentIdentityReadinessService(IHostEnvironment environment)
{
    internal const string OverlayContractName = "chummer.public_edge_portal_overlay_publish.v1";
    internal const string OverlayStatus = "pass";
    internal const string OverlayActivationStatus = "activated";
    internal const string SourceFingerprintAlgorithm = "sha256-canonical-path-content-size-v1";
    internal const string StagedPayloadFingerprintAlgorithm =
        "sha256-canonical-path-content-size-posix-mode-runtime-mount-exclusions-v3";
    internal const string PayloadModeContractName = "chummer.public_edge_payload_modes.v1";
    internal const string PayloadModeAlgorithm = "exact-posix-mode-policy-v1";
    internal const string PayloadModeEntryBindingAlgorithm =
        "sha256-canonical-json-sorted-relative-path-kind-mode-v1";
    internal const string PayloadModeExecutablePolicyAlgorithm =
        "exact-relative-path-allowlist-v1";
    internal const string FullDeploymentDigestContractName = "chummer.public_edge_full_deployment_digest.v1";
    internal const string FullDeploymentDigestAlgorithm = "sha256-canonical-json-v1";
    internal const string BoundCode = "overlay_identity_bound";
    internal const string NotRequiredCode = "overlay_identity_not_required";
    internal const string MissingCode = "overlay_identity_missing";
    internal const string InvalidCode = "overlay_identity_invalid";
    internal const int MaximumBuildInfoBytes = 1024 * 1024;
    internal const string OverlayBuildInfoRelativePath =
        ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json";
    internal static IReadOnlyList<string> RuntimeMountedPayloadRelativePaths { get; } =
    [
        "wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
    ];
    private const int AtCurrentWorkingDirectory = -100;
    private const int AtSymlinkNoFollow = 0x100;
    private const int AtEmptyPath = 0x1000;
    private const int OpenReadOnly = 0;
    private const int OpenCloseOnExec = 0x80000;
    private const int OpenNoFollow = 0x20000;
    private const uint StatxBasicStats = 0x7ff;
    private const uint RequiredStatxMask = 0x3c7;
    private const ushort FileTypeMask = 0xf000;
    private const ushort RegularFileType = 0x8000;
    private const ushort DirectoryFileType = 0x4000;

    public PortalDeploymentIdentityReadiness Evaluate()
    {
        if (!environment.IsProduction())
        {
            return new PortalDeploymentIdentityReadiness(
                Ready: true,
                Code: NotRequiredCode,
                SourceFingerprintSha256: null,
                FullDeploymentDigestSha256: null);
        }

        string path = Path.Combine(
            environment.ContentRootPath,
            OverlayBuildInfoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        try
        {
            if (!File.Exists(path))
            {
                return Failed(MissingCode);
            }

            if (HasSymlinkedOverlayComponent(environment.ContentRootPath, path))
            {
                return Failed(InvalidCode);
            }

            byte[] payload = ReadStableBuildInfo(path, environment.ContentRootPath);
            try
            {
                if (payload.Length >= 3
                    && payload[0] == 0xef
                    && payload[1] == 0xbb
                    && payload[2] == 0xbf)
                {
                    return Failed(InvalidCode);
                }

                using JsonDocument document = JsonDocument.Parse(
                    payload,
                    new JsonDocumentOptions
                    {
                        AllowTrailingCommas = false,
                        CommentHandling = JsonCommentHandling.Disallow,
                        MaxDepth = 16
                    });
                JsonElement root = document.RootElement;
                if (root.ValueKind != JsonValueKind.Object
                    || !HasUniqueObjectPropertiesRecursively(root)
                    || !TryGetUniqueString(root, "contractName", out string contractName)
                    || !string.Equals(contractName, OverlayContractName, StringComparison.Ordinal)
                    || !TryGetUniqueString(root, "status", out string status)
                    || !string.Equals(status, OverlayStatus, StringComparison.Ordinal)
                    || !TryGetUniqueString(root, "activationStatus", out string activationStatus)
                    || !string.Equals(activationStatus, OverlayActivationStatus, StringComparison.Ordinal)
                    || !TryGetUniqueProperty(root, "sourceFingerprint", JsonValueKind.Object, out JsonElement sourceFingerprint)
                    || !TryGetUniqueString(sourceFingerprint, "aggregateSha256", out string aggregateSha256)
                    || !IsSha256(aggregateSha256)
                    || sourceFingerprint.EnumerateObject().Count() != 4
                    || !TryGetUniqueProperty(sourceFingerprint, "files", JsonValueKind.Object, out _)
                    || !TryGetUniqueProperty(sourceFingerprint, "buildInputs", JsonValueKind.Object, out JsonElement buildInputs)
                    || !TryValidateFingerprintEnvelope(buildInputs, SourceFingerprintAlgorithm)
                    || !TryGetUniqueProperty(sourceFingerprint, "overlayPayloadInputs", JsonValueKind.Object, out JsonElement overlayPayloadInputs)
                    || !TryValidateFingerprintEnvelope(overlayPayloadInputs, SourceFingerprintAlgorithm)
                    || !TryGetUniqueProperty(root, "stagedPayloadFingerprint", JsonValueKind.Object, out JsonElement stagedPayloadFingerprint)
                    || !TryValidateStagedFingerprintEnvelope(
                        stagedPayloadFingerprint,
                        out string stagedPayloadAggregateSha256,
                        out int stagedPayloadFileCount)
                    || !TryGetUniqueProperty(root, "payloadModeReceipt", JsonValueKind.Object, out JsonElement payloadModeReceipt)
                    || !TryValidatePayloadModeReceipt(
                        payloadModeReceipt,
                        environment.ContentRootPath,
                        out List<PayloadModeRow> expectedPayloadModeRows)
                    || !TryComputeCurrentStagedPayloadFingerprint(
                        environment.ContentRootPath,
                        expectedPayloadModeRows,
                        out string currentStagedPayloadAggregateSha256,
                        out int currentStagedPayloadFileCount)
                    || !string.Equals(
                        stagedPayloadAggregateSha256,
                        currentStagedPayloadAggregateSha256,
                        StringComparison.Ordinal)
                    || stagedPayloadFileCount != currentStagedPayloadFileCount
                    || !TryGetUniqueProperty(root, "fullDeploymentDigest", JsonValueKind.Object, out JsonElement fullDeploymentDigest)
                    || fullDeploymentDigest.EnumerateObject().Count() != 3
                    || !TryGetUniqueString(fullDeploymentDigest, "contractName", out string fullDigestContractName)
                    || !string.Equals(fullDigestContractName, FullDeploymentDigestContractName, StringComparison.Ordinal)
                    || !TryGetUniqueString(fullDeploymentDigest, "algorithm", out string fullDigestAlgorithm)
                    || !string.Equals(fullDigestAlgorithm, FullDeploymentDigestAlgorithm, StringComparison.Ordinal)
                    || !TryGetUniqueString(fullDeploymentDigest, "sha256", out string fullDeploymentDigestSha256)
                    || !IsLowercaseSha256(fullDeploymentDigestSha256)
                    || !TryComputeFullDeploymentDigestSha256(
                        sourceFingerprint,
                        stagedPayloadFingerprint,
                        out string recomputedFullDeploymentDigestSha256)
                    || !string.Equals(
                        fullDeploymentDigestSha256,
                        recomputedFullDeploymentDigestSha256,
                        StringComparison.Ordinal))
                {
                    return Failed(InvalidCode);
                }

                return new PortalDeploymentIdentityReadiness(
                    Ready: true,
                    Code: BoundCode,
                    SourceFingerprintSha256: aggregateSha256.ToLowerInvariant(),
                    FullDeploymentDigestSha256: fullDeploymentDigestSha256);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(payload);
            }
        }
        catch (Exception exception) when (exception is IOException
                                          or InvalidDataException
                                          or UnauthorizedAccessException
                                          or JsonException
                                          or NotSupportedException)
        {
            return Failed(InvalidCode);
        }
    }

    private static PortalDeploymentIdentityReadiness Failed(string code)
        => new(
            Ready: false,
            Code: code,
            SourceFingerprintSha256: null,
            FullDeploymentDigestSha256: null);

    private static byte[] ReadStableBuildInfo(string path, string contentRootPath)
    {
        if (!OperatingSystem.IsLinux()
            || !TryReadPathMetadata(path, out LinuxStatx beforePath)
            || !IsRegularUnaliasedFile(beforePath)
            || beforePath.Size is 0 or > MaximumBuildInfoBytes)
        {
            throw new InvalidDataException("Overlay build-info metadata is invalid.");
        }

        int descriptor = NativeOpen(path, OpenReadOnly | OpenCloseOnExec | OpenNoFollow);
        if (descriptor < 0)
        {
            throw new IOException("Overlay build-info could not be opened safely.");
        }

        using var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
        if (!TryReadDescriptorMetadata(descriptor, out LinuxStatx beforeDescriptor)
            || !IsRegularUnaliasedFile(beforeDescriptor)
            || !SameStableIdentity(beforePath, beforeDescriptor))
        {
            throw new InvalidDataException("Overlay build-info changed before it was read.");
        }

        byte[] payload = GC.AllocateUninitializedArray<byte>(checked((int)beforeDescriptor.Size));
        try
        {
            using var stream = new FileStream(
                handle,
                FileAccess.Read,
                bufferSize: 64 * 1024,
                isAsync: false);
            stream.ReadExactly(payload);
            if (stream.ReadByte() != -1)
            {
                throw new InvalidDataException("Overlay build-info exceeded its byte limit.");
            }

            if (!TryReadDescriptorMetadata(descriptor, out LinuxStatx afterDescriptor)
                || !SameStableIdentity(beforeDescriptor, afterDescriptor)
                || !TryReadPathMetadata(path, out LinuxStatx afterPath)
                || !SameStableIdentity(afterDescriptor, afterPath)
                || HasSymlinkedOverlayComponent(contentRootPath, path))
            {
                throw new InvalidDataException("Overlay build-info changed while it was read.");
            }

            return payload;
        }
        catch
        {
            CryptographicOperations.ZeroMemory(payload);
            throw;
        }
    }

    private static bool TryReadPathMetadata(string path, out LinuxStatx metadata)
        => NativeStatx(
            AtCurrentWorkingDirectory,
            path,
            AtSymlinkNoFollow,
            StatxBasicStats,
            out metadata) == 0
           && (metadata.Mask & RequiredStatxMask) == RequiredStatxMask;

    private static bool TryReadDescriptorMetadata(int descriptor, out LinuxStatx metadata)
        => NativeStatx(
            descriptor,
            string.Empty,
            AtEmptyPath,
            StatxBasicStats,
            out metadata) == 0
           && (metadata.Mask & RequiredStatxMask) == RequiredStatxMask;

    private static bool IsRegularUnaliasedFile(LinuxStatx metadata)
        => (metadata.Mode & FileTypeMask) == RegularFileType
           && metadata.LinkCount == 1;

    private static bool SameStableIdentity(LinuxStatx left, LinuxStatx right)
        => left.DeviceMajor == right.DeviceMajor
           && left.DeviceMinor == right.DeviceMinor
           && left.Inode == right.Inode
           && left.Size == right.Size
           && left.LinkCount == right.LinkCount
           && left.Mode == right.Mode
           && left.Changed.Seconds == right.Changed.Seconds
           && left.Changed.Nanoseconds == right.Changed.Nanoseconds
           && left.Modified.Seconds == right.Modified.Seconds
           && left.Modified.Nanoseconds == right.Modified.Nanoseconds;

    private static bool TryValidateFingerprintEnvelope(
        JsonElement envelope,
        string expectedAlgorithm)
    {
        if (envelope.EnumerateObject().Count() != 3
            || !TryGetUniqueString(envelope, "algorithm", out string algorithm)
            || !string.Equals(algorithm, expectedAlgorithm, StringComparison.Ordinal)
            || !TryGetUniqueString(envelope, "aggregateSha256", out string aggregateSha256)
            || !IsLowercaseSha256(aggregateSha256)
            || !TryGetUniqueProperty(envelope, "fileCount", JsonValueKind.Number, out JsonElement fileCount)
            || !fileCount.TryGetInt32(out int parsedFileCount)
            || parsedFileCount < 0)
        {
            return false;
        }

        return true;
    }

    private static bool TryValidateStagedFingerprintEnvelope(
        JsonElement envelope,
        out string aggregateSha256,
        out int fileCount)
    {
        aggregateSha256 = string.Empty;
        fileCount = 0;
        if (!HasExactProperties(
                envelope,
                "algorithm",
                "aggregateSha256",
                "fileCount",
                "excludedRelativePaths")
            || !TryGetUniqueString(envelope, "algorithm", out string algorithm)
            || !string.Equals(algorithm, StagedPayloadFingerprintAlgorithm, StringComparison.Ordinal)
            || !TryGetUniqueString(envelope, "aggregateSha256", out aggregateSha256)
            || !IsLowercaseSha256(aggregateSha256)
            || !TryGetUniqueInt32(envelope, "fileCount", out fileCount)
            || !TryGetUniqueProperty(
                envelope,
                "excludedRelativePaths",
                JsonValueKind.Array,
                out JsonElement exclusions)
            || exclusions.GetArrayLength() != RuntimeMountedPayloadRelativePaths.Count)
        {
            return false;
        }

        for (int index = 0; index < RuntimeMountedPayloadRelativePaths.Count; index++)
        {
            JsonElement exclusion = exclusions[index];
            if (exclusion.ValueKind != JsonValueKind.String
                || !string.Equals(
                    exclusion.GetString(),
                    RuntimeMountedPayloadRelativePaths[index],
                    StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }

    private static bool TryValidatePayloadModeReceipt(
        JsonElement receipt,
        string contentRootPath,
        out List<PayloadModeRow> expectedRows)
    {
        expectedRows = [];
        if (!HasExactProperties(
                receipt,
                "contractName",
                "algorithm",
                "status",
                "checks",
                "entryBinding",
                "executablePolicy",
                "stateBoundary",
                "counts",
                "entries",
                "failures")
            || !TryGetUniqueString(receipt, "contractName", out string contractName)
            || !string.Equals(contractName, PayloadModeContractName, StringComparison.Ordinal)
            || !TryGetUniqueString(receipt, "algorithm", out string algorithm)
            || !string.Equals(algorithm, PayloadModeAlgorithm, StringComparison.Ordinal)
            || !TryGetUniqueString(receipt, "status", out string status)
            || !string.Equals(status, "pass", StringComparison.Ordinal)
            || !TryGetUniqueProperty(receipt, "checks", JsonValueKind.Object, out JsonElement checks)
            || !HasExactProperties(checks, "exactModes", "specialPermissionBitsClear")
            || !TryGetUniqueBoolean(checks, "exactModes", out bool exactModes)
            || !exactModes
            || !TryGetUniqueBoolean(
                checks,
                "specialPermissionBitsClear",
                out bool specialPermissionBitsClear)
            || !specialPermissionBitsClear
            || !TryGetUniqueProperty(
                receipt,
                "executablePolicy",
                JsonValueKind.Object,
                out JsonElement executablePolicy)
            || !HasExactProperties(executablePolicy, "algorithm", "relativePaths")
            || !TryGetUniqueString(executablePolicy, "algorithm", out string executableAlgorithm)
            || !string.Equals(
                executableAlgorithm,
                PayloadModeExecutablePolicyAlgorithm,
                StringComparison.Ordinal)
            || !TryGetUniqueProperty(
                executablePolicy,
                "relativePaths",
                JsonValueKind.Array,
                out JsonElement executableRelativePaths)
            || executableRelativePaths.GetArrayLength() != 0
            || !TryGetUniqueProperty(receipt, "entries", JsonValueKind.Array, out JsonElement entries)
            || !TryValidatePayloadModeEntries(entries, out expectedRows)
            || !HasRequiredRuntimeMountedPayloadRows(expectedRows)
            || !TryValidatePayloadModeEntryBinding(receipt, expectedRows)
            || !TryValidatePayloadModeCounts(receipt, expectedRows)
            || !TryValidatePayloadModeStateBoundary(receipt)
            || !TryGetUniqueProperty(receipt, "failures", JsonValueKind.Array, out JsonElement failures)
            || failures.GetArrayLength() != 0
            || !TryReadCurrentPayloadModeRows(contentRootPath, out List<PayloadModeRow> actualRows)
            || !expectedRows.SequenceEqual(actualRows))
        {
            return false;
        }

        return true;
    }

    private static bool HasRequiredRuntimeMountedPayloadRows(
        IReadOnlyCollection<PayloadModeRow> rows)
        => RuntimeMountedPayloadRelativePaths.All(requiredPath =>
            rows.Count(row =>
                string.Equals(row.RelativePath, requiredPath, StringComparison.Ordinal)
                && string.Equals(row.Kind, "file", StringComparison.Ordinal)
                && string.Equals(row.Mode, "0644", StringComparison.Ordinal)) == 1);

    private static bool TryValidatePayloadModeEntries(
        JsonElement entries,
        out List<PayloadModeRow> rows)
    {
        rows = [];
        string? previousPath = null;
        foreach (JsonElement entry in entries.EnumerateArray())
        {
            if (entry.ValueKind != JsonValueKind.Object
                || !HasExactProperties(
                    entry,
                    "relativePath",
                    "kind",
                    "modeActual",
                    "modeExpected",
                    "matches",
                    "specialPermissionBitsClear")
                || !TryGetUniqueString(entry, "relativePath", out string relativePath)
                || !IsSafePayloadRelativePath(relativePath)
                || !TryGetUniqueString(entry, "kind", out string kind)
                || !TryExpectedModeForKind(kind, out string expectedMode)
                || string.Equals(kind, "executable_file", StringComparison.Ordinal)
                || !TryGetUniqueString(entry, "modeActual", out string actualMode)
                || !TryGetUniqueString(entry, "modeExpected", out string recordedExpectedMode)
                || !string.Equals(actualMode, expectedMode, StringComparison.Ordinal)
                || !string.Equals(recordedExpectedMode, expectedMode, StringComparison.Ordinal)
                || !TryGetUniqueBoolean(entry, "matches", out bool matches)
                || !matches
                || !TryGetUniqueBoolean(
                    entry,
                    "specialPermissionBitsClear",
                    out bool entrySpecialPermissionBitsClear)
                || !entrySpecialPermissionBitsClear
                || previousPath is not null
                && ComparePythonUnicodeCodePoints(previousPath, relativePath) >= 0)
            {
                return false;
            }

            if (relativePath == ".")
            {
                if (rows.Count != 0 || !string.Equals(kind, "directory", StringComparison.Ordinal))
                {
                    return false;
                }
            }
            else if (string.Equals(kind, "state_directory", StringComparison.Ordinal)
                     != string.Equals(relativePath, "state", StringComparison.Ordinal))
            {
                return false;
            }

            rows.Add(new PayloadModeRow(relativePath, kind, actualMode));
            previousPath = relativePath;
        }

        return rows.Count > 0
               && string.Equals(rows[0].RelativePath, ".", StringComparison.Ordinal)
               && rows.Count(static row => row.Kind == "state_directory") == 1;
    }

    private static bool TryValidatePayloadModeEntryBinding(
        JsonElement receipt,
        IReadOnlyList<PayloadModeRow> rows)
    {
        if (!TryGetUniqueProperty(
                receipt,
                "entryBinding",
                JsonValueKind.Object,
                out JsonElement binding)
            || !HasExactProperties(binding, "algorithm", "rowCount", "sha256")
            || !TryGetUniqueString(binding, "algorithm", out string bindingAlgorithm)
            || !string.Equals(
                bindingAlgorithm,
                PayloadModeEntryBindingAlgorithm,
                StringComparison.Ordinal)
            || !TryGetUniqueInt32(binding, "rowCount", out int rowCount)
            || rowCount != rows.Count
            || !TryGetUniqueString(binding, "sha256", out string expectedSha256)
            || !IsLowercaseSha256(expectedSha256)
            || !TryComputePayloadModeEntryBindingSha256(rows, out string actualSha256))
        {
            return false;
        }

        return string.Equals(expectedSha256, actualSha256, StringComparison.Ordinal);
    }

    private static bool TryValidatePayloadModeCounts(
        JsonElement receipt,
        IReadOnlyCollection<PayloadModeRow> rows)
    {
        if (!TryGetUniqueProperty(receipt, "counts", JsonValueKind.Object, out JsonElement counts)
            || !HasExactProperties(
                counts,
                "entryCount",
                "directoryCount",
                "fileCount",
                "executableFileCount",
                "modeFailureCount")
            || !TryGetUniqueInt32(counts, "entryCount", out int entryCount)
            || entryCount != rows.Count
            || !TryGetUniqueInt32(counts, "directoryCount", out int directoryCount)
            || directoryCount != rows.Count(static row =>
                row.Kind is "directory" or "state_directory")
            || !TryGetUniqueInt32(counts, "fileCount", out int fileCount)
            || fileCount != rows.Count(static row => row.Kind is "file" or "executable_file")
            || !TryGetUniqueInt32(counts, "executableFileCount", out int executableFileCount)
            || executableFileCount != 0
            || !TryGetUniqueInt32(counts, "modeFailureCount", out int modeFailureCount)
            || modeFailureCount != 0)
        {
            return false;
        }

        return true;
    }

    private static bool TryValidatePayloadModeStateBoundary(JsonElement receipt)
    {
        if (!TryGetUniqueProperty(
                receipt,
                "stateBoundary",
                JsonValueKind.Object,
                out JsonElement stateBoundary)
            || !HasExactProperties(
                stateBoundary,
                "relativePath",
                "stateRootPresent",
                "stateRootModeActual",
                "stateRootModeExpected",
                "stateRootModeMatches",
                "stateContentsInspected")
            || !TryGetUniqueString(stateBoundary, "relativePath", out string relativePath)
            || !string.Equals(relativePath, "state", StringComparison.Ordinal)
            || !TryGetUniqueBoolean(stateBoundary, "stateRootPresent", out bool stateRootPresent)
            || !stateRootPresent
            || !TryGetUniqueString(stateBoundary, "stateRootModeActual", out string actualMode)
            || !string.Equals(actualMode, "0700", StringComparison.Ordinal)
            || !TryGetUniqueString(stateBoundary, "stateRootModeExpected", out string expectedMode)
            || !string.Equals(expectedMode, "0700", StringComparison.Ordinal)
            || !TryGetUniqueBoolean(stateBoundary, "stateRootModeMatches", out bool modeMatches)
            || !modeMatches
            || !TryGetUniqueBoolean(
                stateBoundary,
                "stateContentsInspected",
                out bool stateContentsInspected)
            || stateContentsInspected)
        {
            return false;
        }

        return true;
    }

    private static bool TryReadCurrentPayloadModeRows(
        string contentRootPath,
        out List<PayloadModeRow> rows)
    {
        rows = [];
        if (OperatingSystem.IsWindows())
        {
            return false;
        }

        var root = new DirectoryInfo(Path.GetFullPath(contentRootPath));
        if (!root.Exists
            || root.LinkTarget is not null
            || (root.Attributes & FileAttributes.ReparsePoint) != 0
            || !TryReadPathMetadata(root.FullName, out LinuxStatx rootMetadata)
            || (rootMetadata.Mode & FileTypeMask) != DirectoryFileType
            || !TryGetUnixMode(rootMetadata, out string rootMode)
            || !string.Equals(rootMode, "0755", StringComparison.Ordinal))
        {
            return false;
        }

        rows.Add(new PayloadModeRow(".", "directory", rootMode));
        var pending = new Stack<DirectoryInfo>();
        pending.Push(root);
        while (pending.Count > 0)
        {
            DirectoryInfo directory = pending.Pop();
            foreach (FileSystemInfo entry in directory.EnumerateFileSystemInfos())
            {
                entry.Refresh();
                if (entry.LinkTarget is not null
                    || (entry.Attributes & FileAttributes.ReparsePoint) != 0
                    || !TryReadPathMetadata(entry.FullName, out LinuxStatx metadata))
                {
                    return false;
                }

                string relativePath = Path.GetRelativePath(root.FullName, entry.FullName)
                    .Replace(Path.DirectorySeparatorChar, '/');
                if (Path.AltDirectorySeparatorChar != Path.DirectorySeparatorChar)
                {
                    relativePath = relativePath.Replace(Path.AltDirectorySeparatorChar, '/');
                }
                if (!IsSafePayloadRelativePath(relativePath)
                    || relativePath == "."
                    || !TryGetUnixMode(metadata, out string mode))
                {
                    return false;
                }

                bool isDirectory = (metadata.Mode & FileTypeMask) == DirectoryFileType;
                bool isRegularFile = (metadata.Mode & FileTypeMask) == RegularFileType;
                if (!isDirectory && (!isRegularFile || metadata.LinkCount != 1))
                {
                    return false;
                }
                bool isStateRoot = string.Equals(relativePath, "state", StringComparison.Ordinal);
                string kind;
                string expectedMode;
                if (isStateRoot)
                {
                    if (!isDirectory)
                    {
                        return false;
                    }
                    kind = "state_directory";
                    expectedMode = "0700";
                }
                else if (isDirectory)
                {
                    kind = "directory";
                    expectedMode = "0755";
                }
                else
                {
                    kind = "file";
                    expectedMode = "0644";
                }

                if (!string.Equals(mode, expectedMode, StringComparison.Ordinal))
                {
                    return false;
                }

                rows.Add(new PayloadModeRow(relativePath, kind, mode));
                if (isDirectory && !isStateRoot)
                {
                    pending.Push((DirectoryInfo)entry);
                }
            }
        }

        rows.Sort(static (left, right) =>
            ComparePythonUnicodeCodePoints(left.RelativePath, right.RelativePath));
        return rows.Count(static row => row.Kind == "state_directory") == 1;
    }

    private static bool TryGetUnixMode(LinuxStatx metadata, out string mode)
    {
        mode = string.Empty;
        if (!OperatingSystem.IsLinux())
        {
            return false;
        }
        int rawMode = metadata.Mode & 0xfff;
        mode = Convert.ToString(rawMode, 8).PadLeft(4, '0');
        return mode.Length == 4;
    }

    private static bool TryComputeCurrentStagedPayloadFingerprint(
        string contentRootPath,
        IReadOnlyList<PayloadModeRow> expectedModeRows,
        out string aggregateSha256,
        out int fileCount)
    {
        aggregateSha256 = string.Empty;
        fileCount = 0;
        var fileRows = new List<StagedPayloadFileRow>();
        foreach (PayloadModeRow modeRow in expectedModeRows)
        {
            if (modeRow.Kind is not ("file" or "executable_file")
                || string.Equals(
                    modeRow.RelativePath,
                    OverlayBuildInfoRelativePath,
                    StringComparison.Ordinal)
                || RuntimeMountedPayloadRelativePaths.Contains(
                    modeRow.RelativePath,
                    StringComparer.Ordinal))
            {
                continue;
            }

            string path = Path.Combine(
                contentRootPath,
                modeRow.RelativePath.Replace('/', Path.DirectorySeparatorChar));
            if (!TryHashStablePayloadFile(
                    path,
                    modeRow.Mode,
                    out string sha256,
                    out ulong sizeBytes))
            {
                return false;
            }
            fileRows.Add(new StagedPayloadFileRow(
                modeRow.RelativePath,
                modeRow.Mode,
                sha256,
                sizeBytes));
        }

        fileRows.Sort(static (left, right) =>
            ComparePythonUnicodeCodePoints(left.Path, right.Path));
        if (!TryReadCurrentPayloadModeRows(contentRootPath, out List<PayloadModeRow> finalModeRows)
            || !expectedModeRows.SequenceEqual(finalModeRows)
            || !TryComputePayloadModeEntryBindingSha256(
                expectedModeRows,
                out string entryBindingSha256))
        {
            return false;
        }

        var builder = new StringBuilder();
        builder.Append("{\"fileRows\":[");
        for (int index = 0; index < fileRows.Count; index++)
        {
            if (index > 0)
            {
                builder.Append(',');
            }
            StagedPayloadFileRow row = fileRows[index];
            builder.Append("{\"mode\":");
            AppendPythonJsonString(builder, row.Mode);
            builder.Append(",\"path\":");
            AppendPythonJsonString(builder, row.Path);
            builder.Append(",\"sha256\":");
            AppendPythonJsonString(builder, row.Sha256);
            builder.Append(",\"sizeBytes\":");
            builder.Append(row.SizeBytes.ToString(CultureInfo.InvariantCulture));
            builder.Append('}');
        }
        builder.Append("],\"payloadModeEntryBinding\":{\"algorithm\":");
        AppendPythonJsonString(builder, PayloadModeEntryBindingAlgorithm);
        builder.Append(",\"rowCount\":");
        builder.Append(expectedModeRows.Count.ToString(CultureInfo.InvariantCulture));
        builder.Append(",\"sha256\":");
        AppendPythonJsonString(builder, entryBindingSha256);
        builder.Append("},\"payloadModeExecutablePolicy\":{\"algorithm\":");
        AppendPythonJsonString(builder, PayloadModeExecutablePolicyAlgorithm);
        builder.Append(",\"relativePaths\":[]}}");

        aggregateSha256 = Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(builder.ToString())))
            .ToLowerInvariant();
        fileCount = fileRows.Count;
        return true;
    }

    private static bool TryHashStablePayloadFile(
        string path,
        string expectedMode,
        out string sha256,
        out ulong sizeBytes)
    {
        sha256 = string.Empty;
        sizeBytes = 0;
        if (!TryReadPathMetadata(path, out LinuxStatx beforePath)
            || !IsRegularUnaliasedFile(beforePath)
            || beforePath.Size > long.MaxValue
            || !TryGetUnixMode(beforePath, out string beforeMode)
            || !string.Equals(beforeMode, expectedMode, StringComparison.Ordinal))
        {
            return false;
        }

        int descriptor = NativeOpen(path, OpenReadOnly | OpenCloseOnExec | OpenNoFollow);
        if (descriptor < 0)
        {
            return false;
        }

        using var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
        if (!TryReadDescriptorMetadata(descriptor, out LinuxStatx beforeDescriptor)
            || !IsRegularUnaliasedFile(beforeDescriptor)
            || !SameStableIdentity(beforePath, beforeDescriptor))
        {
            return false;
        }

        using var stream = new FileStream(
            handle,
            FileAccess.Read,
            bufferSize: 64 * 1024,
            isAsync: false);
        byte[] digest = SHA256.HashData(stream);
        if ((ulong)stream.Position != beforeDescriptor.Size
            || stream.ReadByte() != -1
            || !TryReadDescriptorMetadata(descriptor, out LinuxStatx afterDescriptor)
            || !SameStableIdentity(beforeDescriptor, afterDescriptor)
            || !TryReadPathMetadata(path, out LinuxStatx afterPath)
            || !SameStableIdentity(afterDescriptor, afterPath))
        {
            CryptographicOperations.ZeroMemory(digest);
            return false;
        }

        sha256 = Convert.ToHexString(digest).ToLowerInvariant();
        CryptographicOperations.ZeroMemory(digest);
        sizeBytes = beforeDescriptor.Size;
        return true;
    }

    private static bool TryExpectedModeForKind(string kind, out string mode)
    {
        mode = kind switch
        {
            "directory" => "0755",
            "state_directory" => "0700",
            "file" => "0644",
            "executable_file" => "0755",
            _ => string.Empty
        };
        return mode.Length > 0;
    }

    private static bool TryComputePayloadModeEntryBindingSha256(
        IReadOnlyList<PayloadModeRow> rows,
        out string digest)
    {
        var builder = new StringBuilder();
        builder.Append('[');
        for (int index = 0; index < rows.Count; index++)
        {
            if (index > 0)
            {
                builder.Append(',');
            }
            PayloadModeRow row = rows[index];
            builder.Append("{\"kind\":");
            AppendPythonJsonString(builder, row.Kind);
            builder.Append(",\"mode\":");
            AppendPythonJsonString(builder, row.Mode);
            builder.Append(",\"relativePath\":");
            AppendPythonJsonString(builder, row.RelativePath);
            builder.Append('}');
        }
        builder.Append(']');

        digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(builder.ToString())))
            .ToLowerInvariant();
        return true;
    }

    private static void AppendPythonJsonString(
        StringBuilder builder,
        string value,
        bool ensureAscii = true)
    {
        builder.Append('"');
        foreach (char character in value)
        {
            switch (character)
            {
                case '"':
                    builder.Append("\\\"");
                    break;
                case '\\':
                    builder.Append("\\\\");
                    break;
                case '\b':
                    builder.Append("\\b");
                    break;
                case '\f':
                    builder.Append("\\f");
                    break;
                case '\n':
                    builder.Append("\\n");
                    break;
                case '\r':
                    builder.Append("\\r");
                    break;
                case '\t':
                    builder.Append("\\t");
                    break;
                default:
                    if (character < 0x20 || ensureAscii && character >= 0x7F)
                    {
                        builder.Append("\\u");
                        builder.Append(((int)character).ToString("x4"));
                    }
                    else
                    {
                        builder.Append(character);
                    }
                    break;
            }
        }
        builder.Append('"');
    }

    private static bool IsSafePayloadRelativePath(string value)
    {
        if (value == ".")
        {
            return true;
        }
        if (string.IsNullOrEmpty(value)
            || value.StartsWith("/", StringComparison.Ordinal)
            || value.Contains('\\'))
        {
            return false;
        }
        return value.Split('/').All(static part => part is not ("" or "." or ".."));
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LinuxStatxTimestamp
    {
        public long Seconds;
        public uint Nanoseconds;
        public int Reserved;
    }

    [StructLayout(LayoutKind.Sequential, Size = 256)]
    private struct LinuxStatx
    {
        public uint Mask;
        public uint BlockSize;
        public ulong Attributes;
        public uint LinkCount;
        public uint UserId;
        public uint GroupId;
        public ushort Mode;
        public ushort Spare0;
        public ulong Inode;
        public ulong Size;
        public ulong Blocks;
        public ulong AttributesMask;
        public LinuxStatxTimestamp Accessed;
        public LinuxStatxTimestamp Created;
        public LinuxStatxTimestamp Changed;
        public LinuxStatxTimestamp Modified;
        public uint SpecialDeviceMajor;
        public uint SpecialDeviceMinor;
        public uint DeviceMajor;
        public uint DeviceMinor;
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "statx", SetLastError = true)]
    private static extern int NativeStatx(
        int directoryDescriptor,
        string path,
        int flags,
        uint mask,
        out LinuxStatx metadata);

    private sealed record PayloadModeRow(string RelativePath, string Kind, string Mode);

    private sealed record StagedPayloadFileRow(
        string Path,
        string Mode,
        string Sha256,
        ulong SizeBytes);

    private static bool TryComputeFullDeploymentDigestSha256(
        JsonElement sourceFingerprint,
        JsonElement stagedPayloadFingerprint,
        out string digest)
    {
        digest = string.Empty;
        var builder = new StringBuilder();
        builder.Append("{\"algorithm\":");
        AppendPythonJsonString(builder, FullDeploymentDigestAlgorithm);
        builder.Append(",\"contractName\":");
        AppendPythonJsonString(builder, FullDeploymentDigestContractName);
        builder.Append(",\"sourceFingerprint\":");
        if (!TryAppendPythonCanonicalJson(builder, sourceFingerprint))
        {
            return false;
        }
        builder.Append(",\"stagedPayloadFingerprint\":");
        if (!TryAppendPythonCanonicalJson(builder, stagedPayloadFingerprint))
        {
            return false;
        }
        builder.Append('}');

        digest = Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(builder.ToString())))
            .ToLowerInvariant();
        return true;
    }

    private static bool TryAppendPythonCanonicalJson(StringBuilder builder, JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
            {
                var properties = value.EnumerateObject().ToList();
                if (properties.Select(static property => property.Name).Distinct(StringComparer.Ordinal).Count()
                    != properties.Count)
                {
                    return false;
                }

                properties.Sort(static (left, right) =>
                    ComparePythonUnicodeCodePoints(left.Name, right.Name));
                builder.Append('{');
                for (int index = 0; index < properties.Count; index++)
                {
                    if (index > 0)
                    {
                        builder.Append(',');
                    }
                    JsonProperty property = properties[index];
                    AppendPythonJsonString(builder, property.Name, ensureAscii: false);
                    builder.Append(':');
                    if (!TryAppendPythonCanonicalJson(builder, property.Value))
                    {
                        return false;
                    }
                }
                builder.Append('}');
                return true;
            }
            case JsonValueKind.Array:
            {
                builder.Append('[');
                int index = 0;
                foreach (JsonElement item in value.EnumerateArray())
                {
                    if (index++ > 0)
                    {
                        builder.Append(',');
                    }
                    if (!TryAppendPythonCanonicalJson(builder, item))
                    {
                        return false;
                    }
                }
                builder.Append(']');
                return true;
            }
            case JsonValueKind.String:
                AppendPythonJsonString(
                    builder,
                    value.GetString() ?? string.Empty,
                    ensureAscii: false);
                return true;
            case JsonValueKind.Number:
                if (!value.TryGetInt64(out long integer))
                {
                    return false;
                }
                builder.Append(integer.ToString(CultureInfo.InvariantCulture));
                return true;
            case JsonValueKind.True:
                builder.Append("true");
                return true;
            case JsonValueKind.False:
                builder.Append("false");
                return true;
            case JsonValueKind.Null:
                builder.Append("null");
                return true;
            default:
                return false;
        }
    }

    private static int ComparePythonUnicodeCodePoints(string left, string right)
    {
        var leftRunes = left.EnumerateRunes().GetEnumerator();
        var rightRunes = right.EnumerateRunes().GetEnumerator();
        while (true)
        {
            bool hasLeft = leftRunes.MoveNext();
            bool hasRight = rightRunes.MoveNext();
            if (!hasLeft || !hasRight)
            {
                return hasLeft == hasRight ? 0 : hasLeft ? 1 : -1;
            }

            int comparison = leftRunes.Current.Value.CompareTo(rightRunes.Current.Value);
            if (comparison != 0)
            {
                return comparison;
            }
        }
    }

    private static bool HasSymlinkedOverlayComponent(string contentRootPath, string buildInfoPath)
    {
        string metadataDirectory = Path.Combine(contentRootPath, ".codex-studio");
        string runtimeDirectory = Path.Combine(metadataDirectory, "runtime");
        return new DirectoryInfo(metadataDirectory).LinkTarget is not null
               || new DirectoryInfo(runtimeDirectory).LinkTarget is not null
               || new FileInfo(buildInfoPath).LinkTarget is not null;
    }

    private static bool HasExactProperties(JsonElement value, params string[] expectedNames)
    {
        if (value.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        var actualNames = value.EnumerateObject()
            .Select(static property => property.Name)
            .ToList();
        return actualNames.Count == expectedNames.Length
               && actualNames.Distinct(StringComparer.Ordinal).Count() == actualNames.Count
               && expectedNames.All(expectedName => actualNames.Contains(
                   expectedName,
                   StringComparer.Ordinal));
    }

    private static bool HasUniqueObjectPropertiesRecursively(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in value.EnumerateObject())
            {
                if (!names.Add(property.Name)
                    || !HasUniqueObjectPropertiesRecursively(property.Value))
                {
                    return false;
                }
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in value.EnumerateArray())
            {
                if (!HasUniqueObjectPropertiesRecursively(item))
                {
                    return false;
                }
            }
        }

        return true;
    }

    private static bool TryGetUniqueBoolean(
        JsonElement parent,
        string name,
        out bool value)
    {
        value = false;
        int matches = 0;
        JsonElement propertyValue = default;
        foreach (JsonProperty property in parent.EnumerateObject())
        {
            if (!property.NameEquals(name))
            {
                continue;
            }

            matches++;
            propertyValue = property.Value;
        }

        if (matches != 1
            || propertyValue.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
        {
            return false;
        }

        value = propertyValue.GetBoolean();
        return true;
    }

    private static bool TryGetUniqueInt32(
        JsonElement parent,
        string name,
        out int value)
    {
        value = 0;
        return TryGetUniqueProperty(parent, name, JsonValueKind.Number, out JsonElement property)
               && property.TryGetInt32(out value)
               && value >= 0;
    }

    private static bool TryGetUniqueString(
        JsonElement parent,
        string name,
        out string value)
    {
        value = string.Empty;
        if (!TryGetUniqueProperty(parent, name, JsonValueKind.String, out JsonElement property))
        {
            return false;
        }

        value = property.GetString() ?? string.Empty;
        return true;
    }

    private static bool TryGetUniqueProperty(
        JsonElement parent,
        string name,
        JsonValueKind expectedKind,
        out JsonElement value)
    {
        value = default;
        int matches = 0;
        foreach (JsonProperty property in parent.EnumerateObject())
        {
            if (!property.NameEquals(name))
            {
                continue;
            }

            matches++;
            value = property.Value;
        }

        return matches == 1 && value.ValueKind == expectedKind;
    }

    private static bool IsSha256(string value)
        => value.Length == 64
           && value.All(static character =>
               character is >= '0' and <= '9'
               || character is >= 'a' and <= 'f'
               || character is >= 'A' and <= 'F');

    private static bool IsLowercaseSha256(string value)
        => value.Length == 64
           && value.All(static character =>
               character is >= '0' and <= '9'
               || character is >= 'a' and <= 'f');
}

public sealed record PortalDeploymentIdentityReadiness(
    bool Ready,
    string Code,
    string? SourceFingerprintSha256,
    string? FullDeploymentDigestSha256);

public sealed record HubReadyResponse(
    bool Ready,
    string Status,
    DateTimeOffset GeneratedAt,
    HubDeepReadinessReport Hub,
    PublicPlayProjectionReadiness PlayProjection,
    PortalDeploymentIdentityReadiness DeploymentIdentity)
{
    public static HubReadyResponse Create(
        HubDeepReadinessReport hub,
        PublicPlayProjectionReadiness playProjection,
        PortalDeploymentIdentityReadiness deploymentIdentity)
    {
        bool ready = hub.Ready && playProjection.Ready && deploymentIdentity.Ready;
        return new HubReadyResponse(
            Ready: ready,
            Status: ready ? "ready" : "not_ready",
            GeneratedAt: DateTimeOffset.UtcNow,
            Hub: hub,
            PlayProjection: playProjection,
            DeploymentIdentity: deploymentIdentity);
    }
}
