using System.ComponentModel;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.WindowsProof;

/// <summary>
/// Owns an independent, preview-only Windows proof shelf. It never reads or
/// writes the canonical release-shelf pointer or generations.
/// </summary>
public sealed class WindowsProofGenerationStore : IWindowsProofGenerationStore
{
    public const string RootConfigurationKey = "CHUMMER_WINDOWS_PROOF_ROOT";
    public const string CfAccessGatedConfigurationKey = "CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED";
    public const string CanonicalDownloadsRootConfigurationKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    public const string CurrentPointerFileName = "current.json";
    public const string DeliveryStateFileName = "delivery-state.json";
    public const string InventoryFileName = "inventory.json";
    public const string GenerationsDirectoryName = "generations";
    public const string CandidatesDirectoryName = "candidates";

    private const string InventorySchemaVersion = "chummer.windows-proof.inventory/v1";
    private const string CandidateIndexSchemaVersion = "chummer.windows-proof.candidate-index/v1";
    private const string CurrentPointerSchemaVersion = "chummer.windows-proof.current/v1";
    private const string DeliveryStateSchemaVersion = "chummer.windows-proof.delivery-state/v1";
    private const string PrepareReceiptSchemaVersion = "chummer.windows-proof.prepare-receipt/v1";
    private const string ActivationReceiptSchemaVersion = "chummer.windows-proof.activation-receipt/v1";
    private const string ActivationOutcomeSchemaVersion = "chummer.windows-proof.activation-outcome/v1";
    private const int MaximumControlFileBytes = 1024 * 1024;

    private static readonly JsonSerializerOptions JsonOptions = CreateJsonOptions();
    private static readonly SemaphoreSlim ProcessMutationLock = new(1, 1);

    private readonly IConfiguration _configuration;
    private readonly WindowsProofManifestValidator _validator;

    public WindowsProofGenerationStore(
        IConfiguration configuration,
        TimeProvider? timeProvider = null)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _validator = new WindowsProofManifestValidator(timeProvider);
    }

    public async Task<WindowsProofPreparedGeneration> PrepareAsync(
        WindowsProofPrepareRequest request,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        ValidateRequestId(request.RequestId);
        WindowsProofManifestValidator.RequireSha256(
            request.ExpectedManifestSha256,
            nameof(request.ExpectedManifestSha256));
        cancellationToken.ThrowIfCancellationRequested();

        string root = EnsureStoreRoot();
        await ProcessMutationLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            using FileStream mutationLock = AcquireMutationLock(root);
            WindowsProofPrepareReceiptDocument? existingReceipt = TryLoadPrepareReceipt(
                root,
                request.RequestId);
            if (existingReceipt is not null)
            {
                if (!WindowsProofManifestValidator.FixedTimeHexEquals(
                        existingReceipt.ManifestSha256,
                        request.ExpectedManifestSha256))
                {
                    throw new InvalidDataException(
                        "Windows proof prepare request id was replayed with a different manifest digest.");
                }

                LoadedGeneration existing = LoadGeneration(root, existingReceipt.GenerationId);
                if (existing.Manifest.CandidateVersion != existingReceipt.CandidateVersion
                    || !WindowsProofManifestValidator.FixedTimeHexEquals(
                        existing.InventoryDigest,
                        existingReceipt.InventoryDigest))
                {
                    throw new InvalidDataException(
                        "Windows proof prepare receipt no longer matches its immutable generation.");
                }

                return new WindowsProofPreparedGeneration(
                    existing.GenerationId,
                    existing.Manifest.CandidateVersion,
                    existing.InventoryDigest,
                    existingReceipt.CreatedAt);
            }

            string preparingRoot = Path.Combine(
                root,
                ".preparing",
                $"{request.RequestId}-{Guid.NewGuid():N}");
            try
            {
                WindowsProofValidatedSource source = _validator.ValidateSource(
                    request.SourceRoot,
                    request.ExpectedManifestSha256);
                EnsureRootsDoNotOverlap(root, source.SourceRoot, "proof store and upload source");
                CopyValidatedSource(source, preparingRoot);
                WindowsProofValidatedSource copy = _validator.ValidateSource(
                    preparingRoot,
                    request.ExpectedManifestSha256);
                DateTimeOffset createdAt = DateTimeOffset.UtcNow;
                IReadOnlyList<WindowsProofStoredFile> files = BuildStoredInventory(copy);
                string inventoryDigest = ComputeInventoryDigest(files);
                string generationId = $"sha256-{inventoryDigest}";
                string generationRoot = Path.Combine(root, GenerationsDirectoryName, generationId);
                var inventory = new WindowsProofInventoryDocument(
                    InventorySchemaVersion,
                    copy.Manifest.CandidateVersion,
                    inventoryDigest,
                    files);
                WriteCanonicalJsonFile(
                    Path.Combine(preparingRoot, InventoryFileName),
                    inventory,
                    overwrite: false);
                FlushTreeDurably(preparingRoot);

                if (Directory.Exists(generationRoot))
                {
                    LoadedGeneration existing = LoadGeneration(root, generationId);
                    if (existing.Manifest.CandidateVersion != copy.Manifest.CandidateVersion
                        || !WindowsProofManifestValidator.FixedTimeHexEquals(
                            existing.InventoryDigest,
                            inventoryDigest))
                    {
                        throw new InvalidDataException(
                            "Content-addressed Windows proof generation collision detected.");
                    }

                    DeleteDirectoryBestEffort(preparingRoot);
                }
                else
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(generationRoot)!);
                    FlushDirectoryDurably(Path.GetDirectoryName(generationRoot)!);
                    Directory.Move(preparingRoot, generationRoot);
                    FlushDirectoryDurably(Path.GetDirectoryName(generationRoot)!);
                    MakeGenerationReadOnly(generationRoot);
                }

                WindowsProofCandidateIndexDocument candidate = EnsureCandidateIndex(
                    root,
                    copy.Manifest.CandidateVersion,
                    generationId,
                    inventoryDigest,
                    createdAt);
                EnsureInitialDeliveryState(root);
                var receipt = new WindowsProofPrepareReceiptDocument(
                    PrepareReceiptSchemaVersion,
                    request.RequestId,
                    generationId,
                    copy.Manifest.CandidateVersion,
                    inventoryDigest,
                    copy.ManifestSha256,
                    candidate.CreatedAt);
                WriteControlJsonCreateNew(
                    PrepareReceiptPath(root, request.RequestId),
                    receipt);
                return new WindowsProofPreparedGeneration(
                    generationId,
                    copy.Manifest.CandidateVersion,
                    inventoryDigest,
                    candidate.CreatedAt);
            }
            finally
            {
                DeleteDirectoryBestEffort(preparingRoot);
            }
        }
        finally
        {
            ProcessMutationLock.Release();
        }
    }

    public async Task<WindowsProofActivationReceipt> ActivateAsync(
        WindowsProofActivationRequest request,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        ValidateRequestId(request.RequestId);
        ValidateGenerationId(request.GenerationId);
        WindowsProofManifestValidator.RequireSha256(request.InventoryDigest, nameof(request.InventoryDigest));
        if (request.ExpectedCurrentGenerationId is not null)
        {
            ValidateGenerationId(request.ExpectedCurrentGenerationId);
        }

        cancellationToken.ThrowIfCancellationRequested();
        string root = EnsureStoreRoot();
        await ProcessMutationLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            using FileStream mutationLock = AcquireMutationLock(root);
            WindowsProofActivationReceiptDocument? existing = TryLoadActivationReceipt(
                root,
                request.RequestId);
            WindowsProofCurrentPointerDocument? current = TryLoadCurrentPointer(root);
            if (existing is not null)
            {
                ValidateActivationReplay(existing, request);
                if (current?.ActivationReceiptId == request.RequestId)
                {
                    EnsureActivationOutcome(root, existing);
                    return ToActivationReceipt(existing);
                }

                LoadedGeneration replayGeneration = LoadGeneration(root, existing.GenerationId);
                RequireV2Activation(replayGeneration);

                if (current?.GenerationId != existing.PreviousGenerationId)
                {
                    throw new InvalidDataException(
                        "Windows proof activation replay cannot be resumed because current truth changed.");
                }

                WriteCurrentPointer(root, existing);
                EnsureActivationOutcome(root, existing);
                return ToActivationReceipt(existing);
            }

            EnsureNoUnresolvedActivation(root, current);
            string? actualCurrent = current?.GenerationId;
            if (!string.Equals(
                    actualCurrent,
                    request.ExpectedCurrentGenerationId,
                    StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    "Windows proof activation compare-and-swap precondition failed.");
            }

            LoadedGeneration generation = LoadGeneration(root, request.GenerationId);
            RequireV2Activation(generation);
            if (!WindowsProofManifestValidator.FixedTimeHexEquals(
                    generation.InventoryDigest,
                    request.InventoryDigest))
            {
                throw new InvalidDataException(
                    "Windows proof activation inventory digest does not match its immutable generation.");
            }

            WindowsProofCandidateIndexDocument candidate = LoadCandidateIndex(
                root,
                generation.Manifest.CandidateVersion);
            ValidateCandidateBinding(candidate, generation);
            if (FindCommittedActivationForGeneration(root, request.GenerationId) is not null)
            {
                throw new InvalidOperationException(
                    "Windows proof generation has already been activated; replay or rollback is forbidden.");
            }

            WindowsProofDeliveryState state = LoadDeliveryState(root, requireExists: true);
            if (state.Revoked)
            {
                throw new InvalidOperationException(
                    "Windows proof delivery is revoked; activation is forbidden.");
            }

            DateTimeOffset activatedAt = DateTimeOffset.UtcNow;
            var receipt = new WindowsProofActivationReceiptDocument(
                ActivationReceiptSchemaVersion,
                request.RequestId,
                generation.GenerationId,
                generation.Manifest.CandidateVersion,
                generation.InventoryDigest,
                activatedAt,
                actualCurrent,
                state.RevocationGeneration);
            WriteControlJsonCreateNew(
                ActivationReceiptPath(root, request.RequestId),
                receipt);
            WriteCurrentPointer(root, receipt);
            EnsureActivationOutcome(root, receipt);
            return ToActivationReceipt(receipt);
        }
        finally
        {
            ProcessMutationLock.Release();
        }
    }

    public WindowsProofGenerationSnapshot? CaptureCurrent()
    {
        string root = EnsureStoreRoot(create: false);
        if (!Directory.Exists(root))
        {
            return null;
        }

        WindowsProofCurrentPointerDocument? pointer = TryLoadCurrentPointer(root);
        if (pointer is null)
        {
            return null;
        }

        LoadedGeneration generation = LoadGeneration(root, pointer.GenerationId);
        WindowsProofCandidateIndexDocument candidate = LoadCandidateIndex(
            root,
            generation.Manifest.CandidateVersion);
        ValidateCandidateBinding(candidate, generation);
        generation = generation with { CreatedAt = candidate.CreatedAt };
        ValidatePointerBinding(root, pointer, generation);
        WindowsProofDeliveryState state = LoadDeliveryState(root, requireExists: true);
        EnsureDeliveryAllowed(state);
        return CreateSnapshot(
            root,
            generation,
            pointer.ActivatedAt,
            state.RevocationGeneration);
    }

    public WindowsProofGenerationSnapshot? CaptureGeneration(string generationId)
    {
        ValidateGenerationId(generationId);
        string root = EnsureStoreRoot(create: false);
        if (!Directory.Exists(root))
        {
            return null;
        }

        string generationRoot = Path.Combine(root, GenerationsDirectoryName, generationId);
        if (!Directory.Exists(generationRoot))
        {
            return null;
        }

        LoadedGeneration generation = LoadGeneration(root, generationId);
        WindowsProofCandidateIndexDocument candidate = LoadCandidateIndex(
            root,
            generation.Manifest.CandidateVersion);
        ValidateCandidateBinding(candidate, generation);
        generation = generation with { CreatedAt = candidate.CreatedAt };
        WindowsProofDeliveryState state = LoadDeliveryState(root, requireExists: true);
        EnsureDeliveryAllowed(state);
        WindowsProofActivationReceiptDocument? activation = FindCommittedActivationForGeneration(
            root,
            generationId);
        if (activation is null)
        {
            return null;
        }
        return CreateSnapshot(
            root,
            generation,
            activation?.ActivatedAt,
            state.RevocationGeneration);
    }

    public WindowsProofGenerationSnapshot? CaptureCandidate(string candidateVersion)
    {
        WindowsProofManifestValidator.RequirePortableId(candidateVersion, nameof(candidateVersion));
        string root = EnsureStoreRoot(create: false);
        if (!Directory.Exists(root))
        {
            return null;
        }

        string indexPath = CandidateIndexPath(root, candidateVersion);
        if (!File.Exists(indexPath))
        {
            return null;
        }

        WindowsProofCandidateIndexDocument candidate = LoadCandidateIndex(root, candidateVersion);
        LoadedGeneration generation = LoadGeneration(root, candidate.GenerationId);
        ValidateCandidateBinding(candidate, generation);
        generation = generation with { CreatedAt = candidate.CreatedAt };
        WindowsProofDeliveryState state = LoadDeliveryState(root, requireExists: true);
        EnsureDeliveryAllowed(state);
        WindowsProofActivationReceiptDocument? activation = FindCommittedActivationForGeneration(
            root,
            generation.GenerationId);
        if (activation is null)
        {
            return null;
        }
        return CreateSnapshot(
            root,
            generation,
            activation?.ActivatedAt,
            state.RevocationGeneration);
    }

    public Task<WindowsProofGenerationSnapshot?> CaptureCurrentAsync(
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(CaptureCurrent());
    }

    public Task<WindowsProofGenerationSnapshot?> CaptureGenerationAsync(
        string generationId,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(CaptureGeneration(generationId));
    }

    public Task<WindowsProofGenerationSnapshot?> CaptureCandidateAsync(
        string candidateVersion,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(CaptureCandidate(candidateVersion));
    }

    public static string ComputeInventoryDigest(IEnumerable<WindowsProofStoredFile> files)
    {
        ArgumentNullException.ThrowIfNull(files);
        using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        hash.AppendData(Encoding.UTF8.GetBytes($"{InventorySchemaVersion}\n"));
        foreach (WindowsProofStoredFile file in files.OrderBy(static row => row.Path, StringComparer.Ordinal))
        {
            ValidateStoredFile(file);
            hash.AppendData(Encoding.UTF8.GetBytes(
                string.Create(
                    CultureInfo.InvariantCulture,
                    $"{file.Path}\0{file.Size}\0{file.Sha256}\n")));
        }

        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    private WindowsProofGenerationSnapshot CreateSnapshot(
        string root,
        LoadedGeneration generation,
        DateTimeOffset? activatedAt,
        long revocationGeneration)
        => new(
            generation.GenerationId,
            generation.Manifest,
            generation.Manifest.Artifacts.ToArray(),
            generation.CreatedAt,
            activatedAt,
            revocationGeneration,
            entry => OpenVerifiedArtifact(
                root,
                generation.GenerationId,
                generation.InventoryDigest,
                revocationGeneration,
                entry));

    private Stream OpenVerifiedArtifact(
        string root,
        string generationId,
        string expectedInventoryDigest,
        long expectedRevocationGeneration,
        WindowsProofInventoryEntry requested)
    {
        EnsureRuntimeCfGate();
        WindowsProofDeliveryState state = LoadDeliveryState(root, requireExists: true);
        EnsureDeliveryAllowed(state);
        if (state.RevocationGeneration != expectedRevocationGeneration)
        {
            throw new InvalidOperationException(
                "Windows proof delivery state changed; recapture the generation before opening bytes.");
        }

        LoadedGeneration current = LoadGeneration(root, generationId);
        if (!WindowsProofManifestValidator.FixedTimeHexEquals(
                current.InventoryDigest,
                expectedInventoryDigest))
        {
            throw new InvalidDataException("Windows proof generation changed after capture.");
        }

        WindowsProofInventoryEntry[] matches = current.Manifest.Artifacts
            .Where(entry => entry == requested)
            .ToArray();
        if (matches.Length != 1)
        {
            throw new InvalidDataException(
                "Requested Windows proof artifact is not an exact member of the captured inventory.");
        }

        string generationRoot = GenerationRoot(root, generationId);
        string path = WindowsProofManifestValidator.ResolveContainedPath(
            generationRoot,
            requested.RelativePath);
        WindowsProofManifestValidator.EnsureRegularFileWithoutLinks(
            path,
            generationRoot,
            "Windows proof delivery artifact");
        var stream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            1024 * 1024,
            FileOptions.SequentialScan);
        try
        {
            if (stream.Length != requested.Size)
            {
                throw new InvalidDataException("Windows proof delivery artifact size changed after capture.");
            }

            string digest = Convert.ToHexStringLower(SHA256.HashData(stream));
            if (!WindowsProofManifestValidator.FixedTimeHexEquals(digest, requested.Sha256))
            {
                throw new InvalidDataException("Windows proof delivery artifact digest changed after capture.");
            }

            stream.Position = 0;
            return stream;
        }
        catch
        {
            stream.Dispose();
            throw;
        }
    }

    private LoadedGeneration LoadGeneration(string root, string generationId)
    {
        ValidateGenerationId(generationId);
        string generationRoot = GenerationRoot(root, generationId);
        EnsureDirectoryWithoutLinks(generationRoot, "Windows proof generation");
        IReadOnlyList<string> physicalFiles = WindowsProofManifestValidator
            .EnumerateRegularFilesWithoutLinks(generationRoot);
        var relativeFiles = physicalFiles
            .Select(path => Path.GetRelativePath(generationRoot, path)
                .Replace(Path.DirectorySeparatorChar, '/'))
            .ToArray();
        EnsureCaseUnique(relativeFiles, "Windows proof generation inventory");

        string inventoryPath = RequireExactRootFile(
            generationRoot,
            relativeFiles,
            InventoryFileName,
            "Windows proof inventory");
        string manifestPath = RequireExactRootFile(
            generationRoot,
            relativeFiles,
            WindowsProofManifestValidator.ManifestFileName,
            "Windows proof manifest");
        WindowsProofInventoryDocument inventory = ReadControlJson<WindowsProofInventoryDocument>(
            inventoryPath,
            "Windows proof inventory");
        if (inventory.SchemaVersion != InventorySchemaVersion)
        {
            throw new InvalidDataException("Windows proof inventory schema is unsupported.");
        }

        WindowsProofManifest manifest = _validator.ParseAndValidate(
            ReadBoundedFile(
                manifestPath,
                WindowsProofManifestValidator.MaximumManifestBytes,
                "Windows proof generation manifest"),
            allowLegacyV1Delivery: true);
        if (manifest.CandidateVersion != inventory.CandidateVersion)
        {
            throw new InvalidDataException(
                "Windows proof inventory candidate version does not match its manifest.");
        }

        if (inventory.Files is null || inventory.Files.Count == 0)
        {
            throw new InvalidDataException("Windows proof stored inventory files are required.");
        }

        EnsureCaseUnique(inventory.Files.Select(static row => row.Path), "Windows proof stored inventory");
        string computedDigest = ComputeInventoryDigest(inventory.Files);
        if (!WindowsProofManifestValidator.FixedTimeHexEquals(
                computedDigest,
                inventory.InventoryDigest))
        {
            throw new InvalidDataException("Windows proof stored inventory digest is invalid.");
        }

        string expectedGenerationId = $"sha256-{computedDigest}";
        if (generationId != expectedGenerationId)
        {
            throw new InvalidDataException(
                "Windows proof generation id is not its content-addressed inventory digest.");
        }

        var expectedPaths = new HashSet<string>(
            inventory.Files.Select(static row => row.Path),
            StringComparer.Ordinal)
        {
            InventoryFileName
        };
        if (!expectedPaths.SetEquals(relativeFiles))
        {
            throw new InvalidDataException(
                "Windows proof generation physical files do not exactly match its immutable inventory.");
        }

        foreach (WindowsProofStoredFile row in inventory.Files)
        {
            ValidateStoredFile(row);
            // The immutable manifest is the only root-level stored file. Artifact
            // paths still pass through the stricter multi-segment resolver used
            // for admitted bundle inventory.
            string path = row.Path == WindowsProofManifestValidator.ManifestFileName
                ? Path.Combine(generationRoot, WindowsProofManifestValidator.ManifestFileName)
                : WindowsProofManifestValidator.ResolveContainedPath(generationRoot, row.Path);
            WindowsProofManifestValidator.EnsureRegularFileWithoutLinks(
                path,
                generationRoot,
                $"Windows proof stored file '{row.Path}'");
            var info = new FileInfo(path);
            if (info.Length != row.Size
                || !WindowsProofManifestValidator.FixedTimeHexEquals(
                    WindowsProofManifestValidator.ComputeSha256(path),
                    row.Sha256))
            {
                throw new InvalidDataException(
                    $"Windows proof stored file '{row.Path}' failed size or SHA-256 verification.");
            }
        }

        var expectedManifestFiles = new Dictionary<string, (long Size, string Sha256)>(StringComparer.Ordinal)
        {
            [WindowsProofManifestValidator.ManifestFileName] = (
                new FileInfo(manifestPath).Length,
                WindowsProofManifestValidator.ComputeSha256(manifestPath))
        };
        foreach (WindowsProofInventoryEntry row in manifest.Artifacts)
        {
            expectedManifestFiles.Add(row.RelativePath, (row.Size, row.Sha256));
        }

        if (expectedManifestFiles.Count != inventory.Files.Count)
        {
            throw new InvalidDataException(
                "Windows proof stored inventory contains files not bound by its manifest.");
        }

        foreach (WindowsProofStoredFile stored in inventory.Files)
        {
            if (!expectedManifestFiles.TryGetValue(stored.Path, out (long Size, string Sha256) binding)
                || stored.Size != binding.Size
                || !WindowsProofManifestValidator.FixedTimeHexEquals(stored.Sha256, binding.Sha256))
            {
                throw new InvalidDataException(
                    "Windows proof stored inventory disagrees with its manifest bindings.");
            }
        }

        // Re-run semantic evidence validation against the immutable generation,
        // not only during admission, so receipt tampering always fails closed.
        _validator.ValidateSource(
            generationRoot,
            expectedManifestFiles[WindowsProofManifestValidator.ManifestFileName].Sha256,
            allowStoreInventory: true,
            allowLegacyV1Delivery: true);

        return new LoadedGeneration(
            generationId,
            generationRoot,
            manifest,
            inventory.Files,
            computedDigest,
            DateTimeOffset.UnixEpoch);
    }

    private static void RequireV2Activation(LoadedGeneration generation)
    {
        if (!string.Equals(
                generation.Manifest.SchemaVersion,
                WindowsProofManifestValidator.ManifestSchemaVersion,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "Legacy Windows proof v1 generations are delivery-only and cannot be newly activated.");
        }
    }

    private static IReadOnlyList<WindowsProofStoredFile> BuildStoredInventory(
        WindowsProofValidatedSource source)
    {
        var rows = new List<WindowsProofStoredFile>(source.Manifest.Artifacts.Count + 1)
        {
            new(
                WindowsProofManifestValidator.ManifestFileName,
                source.ManifestBytes.LongLength,
                source.ManifestSha256)
        };
        rows.AddRange(source.Manifest.Artifacts.Select(static entry => new WindowsProofStoredFile(
            entry.RelativePath,
            entry.Size,
            entry.Sha256)));
        return rows.OrderBy(static row => row.Path, StringComparer.Ordinal).ToArray();
    }

    private static void CopyValidatedSource(
        WindowsProofValidatedSource source,
        string destinationRoot)
    {
        if (Directory.Exists(destinationRoot) || File.Exists(destinationRoot))
        {
            throw new InvalidOperationException("Windows proof preparation destination already exists.");
        }

        Directory.CreateDirectory(destinationRoot);
        CopyFileBound(
            Path.Combine(source.SourceRoot, WindowsProofManifestValidator.ManifestFileName),
            Path.Combine(destinationRoot, WindowsProofManifestValidator.ManifestFileName),
            source.ManifestBytes.LongLength,
            source.ManifestSha256);
        foreach (WindowsProofInventoryEntry entry in source.Manifest.Artifacts)
        {
            string sourcePath = source.ArtifactFiles[entry.RelativePath];
            string destinationPath = WindowsProofManifestValidator.ResolveContainedPath(
                destinationRoot,
                entry.RelativePath);
            Directory.CreateDirectory(Path.GetDirectoryName(destinationPath)!);
            CopyFileBound(sourcePath, destinationPath, entry.Size, entry.Sha256);
        }
    }

    private static void CopyFileBound(
        string sourcePath,
        string destinationPath,
        long expectedSize,
        string expectedSha256)
    {
        using var source = new FileStream(
            sourcePath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            1024 * 1024,
            FileOptions.SequentialScan);
        var options = new FileStreamOptions
        {
            Mode = FileMode.CreateNew,
            Access = FileAccess.Write,
            Share = FileShare.None,
            BufferSize = 1024 * 1024,
            Options = FileOptions.WriteThrough
        };
        if (!OperatingSystem.IsWindows())
        {
            options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        }

        using var destination = new FileStream(destinationPath, options);
        using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[1024 * 1024];
        long size = 0;
        while (true)
        {
            int read = source.Read(buffer, 0, buffer.Length);
            if (read == 0)
            {
                break;
            }

            destination.Write(buffer, 0, read);
            hash.AppendData(buffer, 0, read);
            size += read;
        }

        destination.Flush(flushToDisk: true);
        string digest = Convert.ToHexStringLower(hash.GetHashAndReset());
        if (size != expectedSize
            || !WindowsProofManifestValidator.FixedTimeHexEquals(digest, expectedSha256))
        {
            throw new InvalidDataException(
                "Windows proof source file changed while it was copied.");
        }
    }

    private WindowsProofCandidateIndexDocument EnsureCandidateIndex(
        string root,
        string candidateVersion,
        string generationId,
        string inventoryDigest,
        DateTimeOffset createdAt)
    {
        string path = CandidateIndexPath(root, candidateVersion);
        if (File.Exists(path))
        {
            WindowsProofCandidateIndexDocument existing = LoadCandidateIndex(root, candidateVersion);
            if (existing.GenerationId != generationId
                || !WindowsProofManifestValidator.FixedTimeHexEquals(
                    existing.InventoryDigest,
                    inventoryDigest))
            {
                throw new InvalidDataException(
                    "Windows proof candidate version is already bound to different immutable bytes.");
            }

            return existing;
        }

        var candidate = new WindowsProofCandidateIndexDocument(
            CandidateIndexSchemaVersion,
            candidateVersion,
            generationId,
            inventoryDigest,
            createdAt);
        WriteControlJsonCreateNew(path, candidate);
        return candidate;
    }

    private WindowsProofCandidateIndexDocument LoadCandidateIndex(
        string root,
        string candidateVersion)
    {
        WindowsProofManifestValidator.RequirePortableId(candidateVersion, nameof(candidateVersion));
        string directory = Path.Combine(root, CandidatesDirectoryName);
        string path = CandidateIndexPath(root, candidateVersion);
        EnsureRegularControlFile(path, directory, "Windows proof candidate index");
        WindowsProofCandidateIndexDocument candidate = ReadControlJson<WindowsProofCandidateIndexDocument>(
            path,
            "Windows proof candidate index");
        if (candidate.SchemaVersion != CandidateIndexSchemaVersion
            || candidate.CandidateVersion != candidateVersion)
        {
            throw new InvalidDataException("Windows proof candidate index contract is invalid.");
        }

        ValidateGenerationId(candidate.GenerationId);
        WindowsProofManifestValidator.RequireSha256(
            candidate.InventoryDigest,
            "candidate index inventoryDigest");
        return candidate;
    }

    private static void ValidateCandidateBinding(
        WindowsProofCandidateIndexDocument candidate,
        LoadedGeneration generation)
    {
        if (candidate.CandidateVersion != generation.Manifest.CandidateVersion
            || candidate.GenerationId != generation.GenerationId
            || !WindowsProofManifestValidator.FixedTimeHexEquals(
                candidate.InventoryDigest,
                generation.InventoryDigest))
        {
            throw new InvalidDataException(
                "Windows proof candidate index does not match its immutable generation.");
        }
    }

    private WindowsProofCurrentPointerDocument? TryLoadCurrentPointer(string root)
    {
        string path = Path.Combine(root, CurrentPointerFileName);
        if (!File.Exists(path))
        {
            RejectCaseVariantControlFile(root, CurrentPointerFileName);
            return null;
        }

        EnsureRegularControlFile(path, root, "Windows proof current pointer");
        WindowsProofCurrentPointerDocument pointer = ReadControlJson<WindowsProofCurrentPointerDocument>(
            path,
            "Windows proof current pointer");
        if (pointer.SchemaVersion != CurrentPointerSchemaVersion)
        {
            throw new InvalidDataException("Windows proof current pointer schema is unsupported.");
        }

        ValidateGenerationId(pointer.GenerationId);
        WindowsProofManifestValidator.RequirePortableId(
            pointer.CandidateVersion,
            "current pointer candidateVersion");
        WindowsProofManifestValidator.RequireSha256(
            pointer.InventoryDigest,
            "current pointer inventoryDigest");
        ValidateRequestId(pointer.ActivationReceiptId);
        return pointer;
    }

    private void ValidatePointerBinding(
        string root,
        WindowsProofCurrentPointerDocument pointer,
        LoadedGeneration generation)
    {
        if (pointer.CandidateVersion != generation.Manifest.CandidateVersion
            || !WindowsProofManifestValidator.FixedTimeHexEquals(
                pointer.InventoryDigest,
                generation.InventoryDigest))
        {
            throw new InvalidDataException(
                "Windows proof current pointer does not match its immutable generation.");
        }

        WindowsProofActivationReceiptDocument receipt = LoadActivationReceipt(
            root,
            pointer.ActivationReceiptId);
        if (receipt.GenerationId != pointer.GenerationId
            || receipt.CandidateVersion != pointer.CandidateVersion
            || receipt.ActivatedAt != pointer.ActivatedAt
            || receipt.RevocationGeneration != pointer.RevocationGeneration
            || !WindowsProofManifestValidator.FixedTimeHexEquals(
                receipt.InventoryDigest,
                pointer.InventoryDigest))
        {
            throw new InvalidDataException(
                "Windows proof current pointer does not match its durable activation receipt.");
        }
    }

    private void WriteCurrentPointer(
        string root,
        WindowsProofActivationReceiptDocument receipt)
    {
        var pointer = new WindowsProofCurrentPointerDocument(
            CurrentPointerSchemaVersion,
            receipt.GenerationId,
            receipt.CandidateVersion,
            receipt.InventoryDigest,
            receipt.ActivatedAt,
            receipt.ActivationId,
            receipt.PreviousGenerationId,
            receipt.RevocationGeneration);
        WriteControlJsonAtomic(
            Path.Combine(root, CurrentPointerFileName),
            pointer,
            overwrite: true);
    }

    private WindowsProofPrepareReceiptDocument? TryLoadPrepareReceipt(
        string root,
        string requestId)
    {
        string directory = Path.Combine(root, "prepare-receipts");
        string path = PrepareReceiptPath(root, requestId);
        if (!File.Exists(path))
        {
            RejectCaseVariantControlFile(directory, $"{requestId}.json");
            return null;
        }

        EnsureRegularControlFile(path, directory, "Windows proof prepare receipt");
        WindowsProofPrepareReceiptDocument receipt = ReadControlJson<WindowsProofPrepareReceiptDocument>(
            path,
            "Windows proof prepare receipt");
        if (receipt.SchemaVersion != PrepareReceiptSchemaVersion
            || receipt.RequestId != requestId)
        {
            throw new InvalidDataException("Windows proof prepare receipt contract is invalid.");
        }

        ValidateGenerationId(receipt.GenerationId);
        WindowsProofManifestValidator.RequirePortableId(
            receipt.CandidateVersion,
            "prepare receipt candidateVersion");
        WindowsProofManifestValidator.RequireSha256(
            receipt.InventoryDigest,
            "prepare receipt inventoryDigest");
        WindowsProofManifestValidator.RequireSha256(
            receipt.ManifestSha256,
            "prepare receipt manifestSha256");
        return receipt;
    }

    private WindowsProofActivationReceiptDocument? TryLoadActivationReceipt(
        string root,
        string activationId)
    {
        string directory = Path.Combine(root, "activation-receipts");
        string path = ActivationReceiptPath(root, activationId);
        if (!File.Exists(path))
        {
            RejectCaseVariantControlFile(directory, $"{activationId}.json");
            return null;
        }

        return LoadActivationReceipt(root, activationId);
    }

    private WindowsProofActivationReceiptDocument LoadActivationReceipt(
        string root,
        string activationId)
    {
        ValidateRequestId(activationId);
        string directory = Path.Combine(root, "activation-receipts");
        string path = ActivationReceiptPath(root, activationId);
        EnsureRegularControlFile(path, directory, "Windows proof activation receipt");
        WindowsProofActivationReceiptDocument receipt = ReadControlJson<WindowsProofActivationReceiptDocument>(
            path,
            "Windows proof activation receipt");
        if (receipt.SchemaVersion != ActivationReceiptSchemaVersion
            || receipt.ActivationId != activationId)
        {
            throw new InvalidDataException("Windows proof activation receipt contract is invalid.");
        }

        ValidateGenerationId(receipt.GenerationId);
        if (receipt.PreviousGenerationId is not null)
        {
            ValidateGenerationId(receipt.PreviousGenerationId);
        }

        WindowsProofManifestValidator.RequirePortableId(
            receipt.CandidateVersion,
            "activation receipt candidateVersion");
        WindowsProofManifestValidator.RequireSha256(
            receipt.InventoryDigest,
            "activation receipt inventoryDigest");
        return receipt;
    }

    private WindowsProofActivationReceiptDocument? FindCommittedActivationForGeneration(
        string root,
        string generationId)
    {
        string outcomesRoot = Path.Combine(root, "activation-outcomes");
        if (!Directory.Exists(outcomesRoot))
        {
            return null;
        }

        EnsureDirectoryWithoutLinks(outcomesRoot, "Windows proof activation outcomes");
        WindowsProofActivationReceiptDocument? match = null;
        foreach (string outcomePath in WindowsProofManifestValidator
                     .EnumerateRegularFilesWithoutLinks(outcomesRoot))
        {
            WindowsProofActivationOutcomeDocument outcome = ReadControlJson<WindowsProofActivationOutcomeDocument>(
                outcomePath,
                "Windows proof activation outcome");
            if (outcome.SchemaVersion != ActivationOutcomeSchemaVersion
                || outcome.Status != "committed")
            {
                throw new InvalidDataException("Windows proof activation outcome contract is invalid.");
            }

            ValidateRequestId(outcome.ActivationId);
            WindowsProofActivationReceiptDocument receipt = LoadActivationReceipt(
                root,
                outcome.ActivationId);
            if (receipt.GenerationId != outcome.GenerationId
                || receipt.ActivatedAt != outcome.ActivatedAt)
            {
                throw new InvalidDataException(
                    "Windows proof activation outcome does not match its receipt.");
            }

            if (receipt.GenerationId == generationId)
            {
                if (match is not null)
                {
                    throw new InvalidDataException(
                        "Windows proof generation has multiple committed activations.");
                }

                match = receipt;
            }
        }

        return match;
    }

    private void EnsureNoUnresolvedActivation(
        string root,
        WindowsProofCurrentPointerDocument? current)
    {
        string receiptsRoot = Path.Combine(root, "activation-receipts");
        if (!Directory.Exists(receiptsRoot))
        {
            return;
        }

        EnsureDirectoryWithoutLinks(receiptsRoot, "Windows proof activation receipts");
        foreach (string path in WindowsProofManifestValidator.EnumerateRegularFilesWithoutLinks(receiptsRoot))
        {
            string fileName = Path.GetFileName(path);
            if (!fileName.EndsWith(".json", StringComparison.Ordinal))
            {
                throw new InvalidDataException("Windows proof activation receipt filename is invalid.");
            }

            string activationId = fileName[..^".json".Length];
            WindowsProofActivationReceiptDocument receipt = LoadActivationReceipt(root, activationId);
            string outcomePath = ActivationOutcomePath(root, activationId);
            bool committed = File.Exists(outcomePath);
            bool pointerCommitted = current?.ActivationReceiptId == activationId;
            if (!committed && !pointerCommitted)
            {
                throw new InvalidOperationException(
                    "Windows proof store has an unresolved activation receipt; only its original request may resume it.");
            }

            if (pointerCommitted && !committed)
            {
                EnsureActivationOutcome(root, receipt);
            }
        }
    }

    private void EnsureActivationOutcome(
        string root,
        WindowsProofActivationReceiptDocument receipt)
    {
        string path = ActivationOutcomePath(root, receipt.ActivationId);
        var expected = new WindowsProofActivationOutcomeDocument(
            ActivationOutcomeSchemaVersion,
            receipt.ActivationId,
            receipt.GenerationId,
            receipt.ActivatedAt,
            "committed");
        if (File.Exists(path))
        {
            WindowsProofActivationOutcomeDocument existing = ReadControlJson<WindowsProofActivationOutcomeDocument>(
                path,
                "Windows proof activation outcome");
            if (existing != expected)
            {
                throw new InvalidDataException(
                    "Windows proof activation outcome was replayed with different data.");
            }

            return;
        }

        WriteControlJsonCreateNew(path, expected);
    }

    private static void ValidateActivationReplay(
        WindowsProofActivationReceiptDocument existing,
        WindowsProofActivationRequest request)
    {
        if (existing.GenerationId != request.GenerationId
            || existing.PreviousGenerationId != request.ExpectedCurrentGenerationId
            || !WindowsProofManifestValidator.FixedTimeHexEquals(
                existing.InventoryDigest,
                request.InventoryDigest))
        {
            throw new InvalidDataException(
                "Windows proof activation request id was replayed with different data.");
        }
    }

    private static WindowsProofPreparedGeneration ToPrepared(LoadedGeneration generation)
        => new(
            generation.GenerationId,
            generation.Manifest.CandidateVersion,
            generation.InventoryDigest,
            generation.CreatedAt);

    private static WindowsProofActivationReceipt ToActivationReceipt(
        WindowsProofActivationReceiptDocument receipt)
        => new(
            receipt.ActivationId,
            receipt.GenerationId,
            receipt.CandidateVersion,
            receipt.InventoryDigest,
            receipt.ActivatedAt,
            receipt.PreviousGenerationId);

    private WindowsProofDeliveryState LoadDeliveryState(string root, bool requireExists)
    {
        string path = Path.Combine(root, DeliveryStateFileName);
        if (!File.Exists(path))
        {
            RejectCaseVariantControlFile(root, DeliveryStateFileName);
            if (!requireExists)
            {
                return new WindowsProofDeliveryState(
                    DeliveryStateSchemaVersion,
                    Revoked: false,
                    RevocationGeneration: 0,
                    Reason: null,
                    UpdatedAt: DateTimeOffset.UnixEpoch);
            }

            throw new InvalidDataException(
                "Windows proof delivery state is missing; delivery fails closed.");
        }

        EnsureRegularControlFile(path, root, "Windows proof delivery state");
        WindowsProofDeliveryState state = ReadControlJson<WindowsProofDeliveryState>(
            path,
            "Windows proof delivery state");
        if (state.SchemaVersion != DeliveryStateSchemaVersion
            || state.RevocationGeneration < 0
            || (state.Revoked && string.IsNullOrWhiteSpace(state.Reason)))
        {
            throw new InvalidDataException("Windows proof delivery state contract is invalid.");
        }

        return state;
    }

    private void EnsureInitialDeliveryState(string root)
    {
        string path = Path.Combine(root, DeliveryStateFileName);
        if (File.Exists(path))
        {
            _ = LoadDeliveryState(root, requireExists: true);
            return;
        }

        var state = new WindowsProofDeliveryState(
            DeliveryStateSchemaVersion,
            Revoked: false,
            RevocationGeneration: 0,
            Reason: null,
            UpdatedAt: DateTimeOffset.UtcNow);
        WriteControlJsonCreateNew(path, state);
    }

    private void EnsureDeliveryAllowed(WindowsProofDeliveryState state)
    {
        EnsureRuntimeCfGate();
        if (state.Revoked)
        {
            throw new InvalidOperationException(
                $"Windows proof delivery is revoked at generation {state.RevocationGeneration}.");
        }
    }

    private void EnsureRuntimeCfGate()
    {
        if (!bool.TryParse(
                _configuration[CfAccessGatedConfigurationKey],
                out bool gated)
            || !gated)
        {
            throw new InvalidOperationException(
                $"Windows proof delivery requires {CfAccessGatedConfigurationKey}=true.");
        }
    }

    private string EnsureStoreRoot(bool create = true)
    {
        EnsureRuntimeCfGate();
        string? configured = _configuration[RootConfigurationKey];
        if (string.IsNullOrWhiteSpace(configured))
        {
            throw new InvalidOperationException(
                $"Windows proof store requires an explicit {RootConfigurationKey}.");
        }

        string root = Path.GetFullPath(configured);
        string canonical = Path.GetFullPath(
            new ReleaseShelfGenerationStore(_configuration).ResolveDownloadsRoot());
        EnsureRootsDoNotOverlap(root, canonical, "Windows proof and canonical release shelf roots");

        if (!Directory.Exists(root))
        {
            if (!create)
            {
                return root;
            }

            Directory.CreateDirectory(root);
            FlushDirectoryDurably(Path.GetDirectoryName(root)!);
        }

        EnsureDirectoryWithoutLinks(root, "Windows proof store root");
        EnsureAncestorChainWithoutLinks(root);
        if (create)
        {
            foreach (string directoryName in new[]
                     {
                         GenerationsDirectoryName,
                         CandidatesDirectoryName,
                         "prepare-receipts",
                         "activation-receipts",
                         "activation-outcomes",
                         ".preparing"
                     })
            {
                string directory = Path.Combine(root, directoryName);
                if (!Directory.Exists(directory))
                {
                    Directory.CreateDirectory(directory);
                    FlushDirectoryDurably(root);
                }

                EnsureDirectoryWithoutLinks(directory, $"Windows proof {directoryName} directory");
            }
        }

        return root;
    }

    private static void EnsureRootsDoNotOverlap(string first, string second, string label)
    {
        string left = Path.GetFullPath(first).TrimEnd(Path.DirectorySeparatorChar);
        string right = Path.GetFullPath(second).TrimEnd(Path.DirectorySeparatorChar);
        StringComparison comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        string leftPrefix = left + Path.DirectorySeparatorChar;
        string rightPrefix = right + Path.DirectorySeparatorChar;
        if (string.Equals(left, right, comparison)
            || left.StartsWith(rightPrefix, comparison)
            || right.StartsWith(leftPrefix, comparison))
        {
            throw new InvalidOperationException($"{label} must be physically separate.");
        }
    }

    private static void EnsureAncestorChainWithoutLinks(string path)
    {
        DirectoryInfo? current = new(Path.GetFullPath(path));
        while (current is not null)
        {
            if (current.Exists
                && (current.LinkTarget is not null
                    || (current.Attributes & FileAttributes.ReparsePoint) != 0))
            {
                throw new InvalidDataException(
                    "Windows proof store root must not traverse symbolic links or reparse points.");
            }

            current = current.Parent;
        }
    }

    private static FileStream AcquireMutationLock(string root)
    {
        string path = Path.Combine(root, ".mutation.lock");
        var options = new FileStreamOptions
        {
            Mode = FileMode.OpenOrCreate,
            Access = FileAccess.ReadWrite,
            Share = FileShare.None,
            Options = FileOptions.WriteThrough
        };
        if (!OperatingSystem.IsWindows() && !File.Exists(path))
        {
            options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        }

        return new FileStream(path, options);
    }

    private static string GenerationRoot(string root, string generationId)
        => Path.Combine(root, GenerationsDirectoryName, generationId);

    private static string CandidateIndexPath(string root, string candidateVersion)
        => Path.Combine(root, CandidatesDirectoryName, $"{candidateVersion}.json");

    private static string PrepareReceiptPath(string root, string requestId)
        => Path.Combine(root, "prepare-receipts", $"{requestId}.json");

    private static string ActivationReceiptPath(string root, string activationId)
        => Path.Combine(root, "activation-receipts", $"{activationId}.json");

    private static string ActivationOutcomePath(string root, string activationId)
        => Path.Combine(root, "activation-outcomes", $"{activationId}.json");

    private static void ValidateRequestId(string requestId)
    {
        WindowsProofManifestValidator.RequirePortableId(requestId, "requestId");
        if (requestId.Length < 8)
        {
            throw new InvalidDataException("Windows proof requestId must contain at least eight characters.");
        }
    }

    private static void ValidateGenerationId(string generationId)
    {
        const string prefix = "sha256-";
        if (!generationId.StartsWith(prefix, StringComparison.Ordinal)
            || generationId.Length != prefix.Length + 64)
        {
            throw new InvalidDataException(
                "Windows proof generation id must be sha256- followed by a lowercase digest.");
        }

        WindowsProofManifestValidator.RequireSha256(
            generationId[prefix.Length..],
            "generationId");
    }

    private static void ValidateStoredFile(WindowsProofStoredFile file)
    {
        if (file is null)
        {
            throw new InvalidDataException("Windows proof stored inventory contains a null row.");
        }

        if (file.Path == InventoryFileName)
        {
            throw new InvalidDataException(
                "Windows proof inventory cannot recursively include its own control file.");
        }

        if (file.Path != WindowsProofManifestValidator.ManifestFileName)
        {
            // ResolveContainedPath performs the same portable-segment validation.
            _ = WindowsProofManifestValidator.ResolveContainedPath("/", file.Path);
        }
        if (file.Size < 0)
        {
            throw new InvalidDataException("Windows proof stored file size cannot be negative.");
        }

        WindowsProofManifestValidator.RequireSha256(file.Sha256, "stored file sha256");
    }

    private static void EnsureCaseUnique(IEnumerable<string> paths, string label)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string path in paths)
        {
            if (!seen.Add(path))
            {
                throw new InvalidDataException($"{label} contains a portable case collision.");
            }
        }
    }

    private static string RequireExactRootFile(
        string root,
        IReadOnlyList<string> relativeFiles,
        string name,
        string label)
    {
        string[] matches = relativeFiles
            .Where(path => string.Equals(path, name, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length != 1 || matches[0] != name)
        {
            throw new InvalidDataException($"{label} is missing, duplicated, nested, or case-ambiguous.");
        }

        string path = Path.Combine(root, name);
        EnsureRegularControlFile(path, root, label);
        return path;
    }

    private static void EnsureRegularControlFile(string path, string root, string label)
    {
        WindowsProofManifestValidator.EnsureRegularFileWithoutLinks(path, root, label);
        string expectedName = Path.GetFileName(path);
        string[] matches = Directory.EnumerateFileSystemEntries(Path.GetDirectoryName(path)!)
            .Where(entry => string.Equals(
                Path.GetFileName(entry),
                expectedName,
                StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length != 1
            || !string.Equals(Path.GetFileName(matches[0]), expectedName, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} has ambiguous or noncanonical casing.");
        }
    }

    private static void RejectCaseVariantControlFile(string directory, string expectedName)
    {
        if (!Directory.Exists(directory))
        {
            return;
        }

        string[] matches = Directory.EnumerateFileSystemEntries(directory)
            .Where(entry => string.Equals(
                Path.GetFileName(entry),
                expectedName,
                StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length > 0)
        {
            throw new InvalidDataException(
                $"Windows proof control file '{expectedName}' has noncanonical or ambiguous casing.");
        }
    }

    private static T ReadControlJson<T>(string path, string label)
    {
        byte[] bytes = ReadBoundedFile(path, MaximumControlFileBytes, label);
        try
        {
            using JsonDocument document = JsonDocument.Parse(
                bytes,
                new JsonDocumentOptions { MaxDepth = 32 });
            RejectDuplicateProperties(document.RootElement, label);
            return JsonSerializer.Deserialize<T>(bytes, JsonOptions)
                   ?? throw new InvalidDataException($"{label} is empty.");
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception ex) when (ex is JsonException or NotSupportedException)
        {
            throw new InvalidDataException($"{label} is invalid JSON.", ex);
        }
    }

    private static byte[] ReadBoundedFile(string path, int maximumBytes, string label)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length <= 0 || info.Length > maximumBytes)
        {
            throw new InvalidDataException($"{label} size is invalid.");
        }

        byte[] bytes = File.ReadAllBytes(path);
        if (bytes.LongLength != info.Length)
        {
            throw new InvalidDataException($"{label} changed while it was read.");
        }

        return bytes;
    }

    private static void RejectDuplicateProperties(JsonElement element, string label)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!names.Add(property.Name))
                {
                    throw new InvalidDataException(
                        $"{label} contains a duplicate or case-colliding JSON property.");
                }

                RejectDuplicateProperties(property.Value, label);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement child in element.EnumerateArray())
            {
                RejectDuplicateProperties(child, label);
            }
        }
    }

    private static void WriteCanonicalJsonFile<T>(string path, T value, bool overwrite)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, JsonOptions);
        WriteBytesDurably(path, bytes, overwrite ? FileMode.Create : FileMode.CreateNew);
    }

    private static void WriteControlJsonCreateNew<T>(string path, T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        WriteControlJsonAtomic(path, value, overwrite: false);
    }

    private static void WriteControlJsonAtomic<T>(string path, T value, bool overwrite)
    {
        string directory = Path.GetDirectoryName(path)
                           ?? throw new InvalidDataException("Windows proof control path has no parent.");
        Directory.CreateDirectory(directory);
        EnsureDirectoryWithoutLinks(directory, "Windows proof control directory");
        string tempPath = Path.Combine(
            directory,
            $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, JsonOptions);
            WriteBytesDurably(tempPath, bytes, FileMode.CreateNew);
            FlushDirectoryDurably(directory);
            File.Move(tempPath, path, overwrite);
            FlushDirectoryDurably(directory);
        }
        finally
        {
            TryDeleteFile(tempPath);
        }
    }

    private static void WriteBytesDurably(string path, byte[] bytes, FileMode mode)
    {
        var options = new FileStreamOptions
        {
            Mode = mode,
            Access = FileAccess.Write,
            Share = FileShare.None,
            Options = FileOptions.WriteThrough
        };
        if (!OperatingSystem.IsWindows() && mode == FileMode.CreateNew)
        {
            options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        }

        using var stream = new FileStream(path, options);
        stream.Write(bytes);
        stream.WriteByte((byte)'\n');
        stream.Flush(flushToDisk: true);
    }

    private static void FlushTreeDurably(string root)
    {
        foreach (string file in WindowsProofManifestValidator.EnumerateRegularFilesWithoutLinks(root))
        {
            using var stream = new FileStream(file, FileMode.Open, FileAccess.ReadWrite, FileShare.Read);
            stream.Flush(flushToDisk: true);
        }

        foreach (string directory in Directory.EnumerateDirectories(root, "*", SearchOption.AllDirectories)
                     .OrderByDescending(static path => path.Length))
        {
            FlushDirectoryDurably(directory);
        }

        FlushDirectoryDurably(root);
    }

    private static void MakeGenerationReadOnly(string root)
    {
        if (OperatingSystem.IsWindows())
        {
            foreach (string file in WindowsProofManifestValidator.EnumerateRegularFilesWithoutLinks(root))
            {
                File.SetAttributes(file, File.GetAttributes(file) | FileAttributes.ReadOnly);
            }

            return;
        }

        UnixFileMode fileMode = UnixFileMode.UserRead
                                | UnixFileMode.GroupRead
                                | UnixFileMode.OtherRead;
        UnixFileMode directoryMode = fileMode
                                     | UnixFileMode.UserExecute
                                     | UnixFileMode.GroupExecute
                                     | UnixFileMode.OtherExecute;
        foreach (string file in WindowsProofManifestValidator.EnumerateRegularFilesWithoutLinks(root))
        {
            File.SetUnixFileMode(file, fileMode);
        }

        foreach (string directory in Directory.EnumerateDirectories(root, "*", SearchOption.AllDirectories)
                     .OrderByDescending(static path => path.Length))
        {
            File.SetUnixFileMode(directory, directoryMode);
        }

        File.SetUnixFileMode(root, directoryMode);
    }

    private static void FlushDirectoryDurably(string path)
    {
        if (OperatingSystem.IsWindows() || string.IsNullOrWhiteSpace(path) || !Directory.Exists(path))
        {
            return;
        }

        int descriptor = NativeOpen(path, 0);
        if (descriptor < 0)
        {
            throw new IOException(
                $"Could not open Windows proof directory for fsync: {path}",
                new Win32Exception(Marshal.GetLastWin32Error()));
        }

        try
        {
            if (NativeFsync(descriptor) != 0)
            {
                throw new IOException(
                    $"Could not fsync Windows proof directory: {path}",
                    new Win32Exception(Marshal.GetLastWin32Error()));
            }
        }
        finally
        {
            _ = NativeClose(descriptor);
        }
    }

    private static void DeleteDirectoryBestEffort(string path)
    {
        try
        {
            if (!Directory.Exists(path))
            {
                return;
            }

            if (!OperatingSystem.IsWindows())
            {
                foreach (string file in WindowsProofManifestValidator.EnumerateRegularFilesWithoutLinks(path))
                {
                    File.SetUnixFileMode(file, UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }

                foreach (string directory in Directory.EnumerateDirectories(path, "*", SearchOption.AllDirectories))
                {
                    File.SetUnixFileMode(
                        directory,
                        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
                }

                File.SetUnixFileMode(
                    path,
                    UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            }

            Directory.Delete(path, recursive: true);
        }
        catch
        {
            // Best effort cleanup of a non-authoritative preparation directory.
        }
    }

    private static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
            // Best effort cleanup of a non-authoritative temporary file.
        }
    }

    private static void EnsureDirectoryWithoutLinks(string path, string label)
    {
        if (!Directory.Exists(path))
        {
            throw new InvalidDataException($"{label} does not exist.");
        }

        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.Directory) == 0
            || (attributes & FileAttributes.ReparsePoint) != 0
            || new DirectoryInfo(path).LinkTarget is not null)
        {
            throw new InvalidDataException($"{label} must be a non-symlink directory.");
        }
    }

    private static JsonSerializerOptions CreateJsonOptions()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = false,
            UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
            MaxDepth = 32,
            WriteIndented = false
        };
        options.Converters.Add(new JsonStringEnumConverter(
            JsonNamingPolicy.SnakeCaseLower,
            allowIntegerValues: false));
        return options;
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "fsync", SetLastError = true)]
    private static extern int NativeFsync(int fileDescriptor);

    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int NativeClose(int fileDescriptor);

    private sealed record LoadedGeneration(
        string GenerationId,
        string PhysicalRoot,
        WindowsProofManifest Manifest,
        IReadOnlyList<WindowsProofStoredFile> Files,
        string InventoryDigest,
        DateTimeOffset CreatedAt);

    private sealed record WindowsProofInventoryDocument(
        string SchemaVersion,
        string CandidateVersion,
        string InventoryDigest,
        IReadOnlyList<WindowsProofStoredFile> Files);

    private sealed record WindowsProofCandidateIndexDocument(
        string SchemaVersion,
        string CandidateVersion,
        string GenerationId,
        string InventoryDigest,
        DateTimeOffset CreatedAt);

    private sealed record WindowsProofPrepareReceiptDocument(
        string SchemaVersion,
        string RequestId,
        string GenerationId,
        string CandidateVersion,
        string InventoryDigest,
        string ManifestSha256,
        DateTimeOffset CreatedAt);

    private sealed record WindowsProofCurrentPointerDocument(
        string SchemaVersion,
        string GenerationId,
        string CandidateVersion,
        string InventoryDigest,
        DateTimeOffset ActivatedAt,
        string ActivationReceiptId,
        string? PreviousGenerationId,
        long RevocationGeneration);

    private sealed record WindowsProofActivationReceiptDocument(
        string SchemaVersion,
        string ActivationId,
        string GenerationId,
        string CandidateVersion,
        string InventoryDigest,
        DateTimeOffset ActivatedAt,
        string? PreviousGenerationId,
        long RevocationGeneration);

    private sealed record WindowsProofActivationOutcomeDocument(
        string SchemaVersion,
        string ActivationId,
        string GenerationId,
        DateTimeOffset ActivatedAt,
        string Status);
}

public sealed record WindowsProofStoredFile(
    string Path,
    long Size,
    string Sha256);
