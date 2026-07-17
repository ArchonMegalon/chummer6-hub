using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Globalization;
using Chummer.Run.Api.Services.WindowsProof;

namespace Chummer.Run.Api.Services;

public static class WindowsProofUploadSessionStates
{
    public const string Created = "created";
    public const string Uploaded = "uploaded";
    public const string RequestStarted = "request_started";
    public const string Completed = "completed";
}

public sealed record WindowsProofUploadSession(
    string SessionId,
    string State,
    DateTimeOffset ExpiresAtUtc,
    bool SingleUseAuthorization,
    string? ManifestSha256 = null,
    WindowsProofUploadCompletionResult? CompletionResult = null);

public sealed record WindowsProofUploadChunkResult(
    string RelativePath,
    int ChunkIndex,
    int TotalChunks,
    long BytesReceived,
    bool Completed);

public sealed record WindowsProofUploadCompletionResult(
    string SessionId,
    string GenerationId,
    string CandidateVersion,
    string ManifestSha256,
    string InventoryDigest,
    DateTimeOffset ActivatedAtUtc,
    IReadOnlyDictionary<string, string> Routes);

internal sealed record WindowsProofUploadManifestArtifact(
    string Kind,
    string ArtifactId,
    string RelativePath,
    string FileName,
    long Size,
    string Sha256);

internal sealed record WindowsProofUploadManifestDescriptor(
    string CandidateVersion,
    string ManifestSha256,
    IReadOnlyList<WindowsProofUploadManifestArtifact> Artifacts)
{
    public IReadOnlyDictionary<string, WindowsProofUploadManifestArtifact> ByPath { get; } =
        Artifacts.ToDictionary(static item => item.RelativePath, StringComparer.Ordinal);
}

/// <summary>
/// Durable, proof-lane-only staged upload storage. This service deliberately has
/// no dependency on ReleaseBundlePromotionService or the canonical shelf store.
/// </summary>
public sealed class WindowsProofUploadSessionService
{
    public const string ManifestFileName = "WINDOWS_PROOF_MANIFEST.generated.json";
    public const string SessionKind = "windows_proof";

    private const string SessionSchemaVersion = "chummer.windows-proof.upload-session/v1";
    private const string ManifestSchemaVersion = WindowsProofManifestValidator.ManifestSchemaVersion;
    private const string SessionsRootKey = "CHUMMER_WINDOWS_PROOF_UPLOAD_SESSION_ROOT";
    private const int MaximumManifestBytes = 1024 * 1024;
    private static readonly Regex CandidateVersionPattern = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex ArtifactIdPattern = new(
        "\\A[a-z0-9][a-z0-9._-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex Sha256Pattern = new(
        "\\A[0-9a-f]{64}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly HashSet<string> AllowedKinds = new(StringComparer.Ordinal)
    {
        "installer",
        "bootstrap_payload",
        "bootstrap_metadata",
        "signing_receipt",
        "startup_smoke_receipt",
        "build_provenance_receipt",
        "sbom",
        "visual_handoff",
        "visual_exit_evidence"
    };
    private static readonly HashSet<string> RequiredKinds = new(StringComparer.Ordinal)
    {
        "installer",
        "signing_receipt",
        "startup_smoke_receipt",
        "build_provenance_receipt",
        "sbom",
        "visual_handoff"
    };
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        WriteIndented = true
    };
    private const UnixFileMode OwnerDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode OwnerFileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;

    private readonly IConfiguration _configuration;
    private readonly WindowsProofUploadOptions _options;
    private readonly TimeProvider _timeProvider;

    public WindowsProofUploadSessionService(
        IConfiguration configuration,
        WindowsProofUploadOptions options,
        TimeProvider timeProvider)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _options.Validate();
    }

    public WindowsProofUploadSession CreateSession(
        string authorizationBinding,
        bool singleUseAuthorization,
        DateTimeOffset? authorizationExpiresAtUtc)
    {
        authorizationBinding = NormalizeAuthorizationBinding(authorizationBinding);
        DateTimeOffset now = _timeProvider.GetUtcNow();
        if (singleUseAuthorization
            && (authorizationExpiresAtUtc is null || authorizationExpiresAtUtc <= now))
        {
            throw new InvalidDataException("Windows proof upload ticket expiry must be in the future.");
        }

        string root = ResolveSessionsRoot();
        using FileStream rootLock = AcquireExclusiveLock(Path.Combine(root, ".sessions.lock"));
        PurgeExpiredSessionsUnderLock(root, now);

        WindowsProofUploadSessionMetadata? bound = FindByAuthorization(root, authorizationBinding);
        if (singleUseAuthorization && bound is not null)
        {
            if (bound.State == WindowsProofUploadSessionStates.Completed || bound.ExpiresAtUtc <= now)
            {
                throw new InvalidOperationException("Windows proof upload ticket has already been consumed.");
            }

            return ToPublic(bound);
        }

        string sessionId = Guid.NewGuid().ToString("N");
        string sessionRoot = Path.Combine(root, sessionId);
        string bundleRoot = Path.Combine(sessionRoot, "bundle");
        string stagingRoot = Path.Combine(sessionRoot, "staging");
        EnsureOwnerOnlyDirectory(sessionRoot);
        EnsureOwnerOnlyDirectory(bundleRoot);
        EnsureOwnerOnlyDirectory(stagingRoot);

        DateTimeOffset expires = now.Add(_options.SessionLifetime);
        if (authorizationExpiresAtUtc is not null && authorizationExpiresAtUtc < expires)
        {
            expires = authorizationExpiresAtUtc.Value;
        }

        var metadata = new WindowsProofUploadSessionMetadata(
            SchemaVersion: SessionSchemaVersion,
            SessionKind,
            SessionId: sessionId,
            State: WindowsProofUploadSessionStates.Created,
            CreatedAtUtc: now,
            ExpiresAtUtc: expires,
            BundleRoot: bundleRoot,
            AuthorizationBinding: authorizationBinding,
            SingleUseAuthorization: singleUseAuthorization,
            AuthorizationExpiresAtUtc: authorizationExpiresAtUtc,
            ManifestSha256: null,
            RequestId: null,
            PreparedGenerationId: null,
            PreparedCandidateVersion: null,
            PreparedInventoryDigest: null,
            ExpectedCurrentGenerationId: null,
            CompletionResult: null);
        PersistMetadata(sessionRoot, metadata);
        return ToPublic(metadata);
    }

    public async Task<long> WriteFileAsync(
        string sessionId,
        string relativePath,
        Stream content,
        string authorizationBinding,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(content);
        sessionId = CanonicalizeSessionId(sessionId);
        relativePath = NormalizeRelativePath(relativePath);
        string root = ResolveSessionsRoot();
        string sessionRoot = Path.Combine(root, sessionId);
        using FileStream sessionLock = AcquireSessionLock(sessionRoot);
        WindowsProofUploadSessionMetadata metadata = ReadMetadata(
            sessionRoot,
            authorizationBinding,
            allowCompleted: false);
        EnsureUploadMutable(metadata);

        WindowsProofUploadManifestArtifact? declaration = null;
        long maximumBytes;
        if (string.Equals(relativePath, ManifestFileName, StringComparison.Ordinal))
        {
            if (Directory.EnumerateFiles(metadata.BundleRoot, "*", SearchOption.AllDirectories).Any())
            {
                return await ValidateIdempotentExistingFileAsync(
                    metadata,
                    relativePath,
                    content,
                    expectedSize: null,
                    expectedSha256: metadata.ManifestSha256,
                    MaximumManifestBytes,
                    cancellationToken);
            }

            maximumBytes = MaximumManifestBytes;
        }
        else
        {
            WindowsProofUploadManifestDescriptor descriptor = LoadManifestDescriptor(metadata.BundleRoot);
            if (!descriptor.ByPath.TryGetValue(relativePath, out declaration))
            {
                throw new InvalidDataException("Upload path is not declared by the Windows proof manifest.");
            }

            if (declaration.Size > _options.MaxChunkBytes)
            {
                throw new InvalidDataException("Declared file requires the bounded chunk upload endpoint.");
            }

            maximumBytes = Math.Min(_options.MaxChunkBytes, declaration.Size);
        }

        string target = ResolveBundleTarget(metadata.BundleRoot, relativePath);
        if (File.Exists(target))
        {
            return await ValidateIdempotentExistingFileAsync(
                metadata,
                relativePath,
                content,
                declaration?.Size,
                declaration?.Sha256 ?? metadata.ManifestSha256,
                maximumBytes,
                cancellationToken);
        }

        EnsureSafeParentPath(metadata.BundleRoot, target, create: true);
        string temporary = Path.Combine(
            Path.GetDirectoryName(target)!,
            $".{Path.GetFileName(target)}.{Guid.NewGuid():N}.upload");
        try
        {
            (long size, string digest) = await CopyBoundedAsync(
                content,
                temporary,
                maximumBytes,
                cancellationToken);
            if (size <= 0)
            {
                throw new InvalidDataException("Windows proof upload files must not be empty.");
            }

            if (declaration is not null)
            {
                ValidateDeclaredContent(declaration, size, digest);
            }

            if (string.Equals(relativePath, ManifestFileName, StringComparison.Ordinal))
            {
                WindowsProofUploadManifestDescriptor descriptor = ParseManifest(temporary, digest);
                if (descriptor.Artifacts.Sum(static item => item.Size) > _options.MaxSessionBytes)
                {
                    throw new InvalidDataException("Declared Windows proof inventory exceeds the session byte limit.");
                }
            }

            File.Move(temporary, target, overwrite: false);
            EnsureOwnerOnlyFile(target);
            if (string.Equals(relativePath, ManifestFileName, StringComparison.Ordinal))
            {
                metadata = metadata with { ManifestSha256 = digest };
            }

            metadata = RefreshUploadedState(metadata);
            PersistMetadata(sessionRoot, metadata);
            return size;
        }
        finally
        {
            TryDeleteFile(temporary);
        }
    }

    public async Task<WindowsProofUploadChunkResult> AppendChunkAsync(
        string sessionId,
        string relativePath,
        int chunkIndex,
        int totalChunks,
        Stream content,
        string authorizationBinding,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(content);
        sessionId = CanonicalizeSessionId(sessionId);
        relativePath = NormalizeRelativePath(relativePath);
        if (string.Equals(relativePath, ManifestFileName, StringComparison.Ordinal))
        {
            throw new InvalidDataException("The bounded manifest must be uploaded atomically before artifact chunks.");
        }

        if (chunkIndex < 0 || totalChunks <= 0 || chunkIndex >= totalChunks
            || totalChunks > _options.MaxChunksPerFile)
        {
            throw new InvalidDataException("Invalid Windows proof chunk coordinates.");
        }

        string root = ResolveSessionsRoot();
        string sessionRoot = Path.Combine(root, sessionId);
        using FileStream sessionLock = AcquireSessionLock(sessionRoot);
        WindowsProofUploadSessionMetadata metadata = ReadMetadata(
            sessionRoot,
            authorizationBinding,
            allowCompleted: false);
        EnsureUploadMutable(metadata);
        WindowsProofUploadManifestDescriptor descriptor = LoadManifestDescriptor(metadata.BundleRoot);
        if (!descriptor.ByPath.TryGetValue(relativePath, out WindowsProofUploadManifestArtifact? declaration))
        {
            throw new InvalidDataException("Chunk path is not declared by the Windows proof manifest.");
        }

        if (declaration.Size > _options.MaxFileBytes)
        {
            throw new InvalidDataException("Declared Windows proof file exceeds the per-file limit.");
        }

        string target = ResolveBundleTarget(metadata.BundleRoot, relativePath);
        if (File.Exists(target))
        {
            throw new InvalidOperationException("Declared Windows proof file has already completed upload.");
        }

        string stagingRoot = ResolveChunkStagingRoot(sessionRoot, relativePath);
        EnsureOwnerOnlyDirectory(stagingRoot);
        string bindingPath = Path.Combine(stagingRoot, "binding.json");
        WindowsProofChunkBinding binding = ReadOrCreateChunkBinding(
            bindingPath,
            relativePath,
            totalChunks,
            declaration);
        if (binding.TotalChunks != totalChunks)
        {
            throw new InvalidOperationException("Chunk total conflicts with the existing upload binding.");
        }

        string chunkPath = Path.Combine(stagingRoot, $"{chunkIndex:D4}.chunk");
        string temporary = Path.Combine(stagingRoot, $".{chunkIndex:D4}.{Guid.NewGuid():N}.upload");
        try
        {
            (long bytes, string digest) = await CopyBoundedAsync(
                content,
                temporary,
                _options.MaxChunkBytes,
                cancellationToken);
            if (bytes <= 0)
            {
                throw new InvalidDataException("Windows proof chunks must not be empty.");
            }

            if (File.Exists(chunkPath))
            {
                (long existingBytes, string existingDigest) = HashRegularFile(chunkPath, _options.MaxChunkBytes);
                if (existingBytes != bytes || !FixedTimeDigestEquals(existingDigest, digest))
                {
                    throw new InvalidOperationException("Chunk replay content differs from the durable chunk.");
                }
            }
            else
            {
                File.Move(temporary, chunkPath, overwrite: false);
                EnsureOwnerOnlyFile(chunkPath);
            }

            bool complete = TryAssembleChunks(
                metadata.BundleRoot,
                target,
                stagingRoot,
                declaration,
                totalChunks);
            if (complete)
            {
                metadata = RefreshUploadedState(metadata);
                PersistMetadata(sessionRoot, metadata);
            }

            return new WindowsProofUploadChunkResult(
                relativePath,
                chunkIndex,
                totalChunks,
                bytes,
                complete);
        }
        finally
        {
            TryDeleteFile(temporary);
        }
    }

    public WindowsProofUploadCompletionLease BeginCompletion(
        string sessionId,
        string authorizationBinding)
    {
        sessionId = CanonicalizeSessionId(sessionId);
        string root = ResolveSessionsRoot();
        string sessionRoot = Path.Combine(root, sessionId);
        FileStream sessionLock = AcquireSessionLock(sessionRoot);
        try
        {
            WindowsProofUploadSessionMetadata metadata = ReadMetadata(
                sessionRoot,
                authorizationBinding,
                allowCompleted: true);
            if (metadata.State == WindowsProofUploadSessionStates.Completed)
            {
                return new WindowsProofUploadCompletionLease(this, sessionRoot, sessionLock, metadata);
            }

            if (metadata.State != WindowsProofUploadSessionStates.RequestStarted)
            {
                metadata = RefreshUploadedState(metadata);
                if (metadata.State != WindowsProofUploadSessionStates.Uploaded)
                {
                    throw new InvalidOperationException("Windows proof upload is incomplete.");
                }

                ValidateCompleteInventory(metadata.BundleRoot);
                metadata = metadata with
                {
                    State = WindowsProofUploadSessionStates.RequestStarted,
                    RequestId = metadata.SessionId
                };
                PersistMetadata(sessionRoot, metadata);
            }

            return new WindowsProofUploadCompletionLease(this, sessionRoot, sessionLock, metadata);
        }
        catch
        {
            sessionLock.Dispose();
            throw;
        }
    }

    public void PurgeExpiredSessions()
    {
        string root = ResolveSessionsRoot();
        using FileStream rootLock = AcquireExclusiveLock(Path.Combine(root, ".sessions.lock"));
        PurgeExpiredSessionsUnderLock(root, _timeProvider.GetUtcNow());
    }

    internal WindowsProofUploadManifestDescriptor LoadDescriptor(WindowsProofUploadSessionMetadata metadata)
        => LoadManifestDescriptor(metadata.BundleRoot);

    internal void RecordPrepared(
        string sessionRoot,
        WindowsProofUploadCompletionLease lease,
        WindowsProofPreparedGeneration prepared,
        string? expectedCurrentGenerationId)
    {
        WindowsProofUploadSessionMetadata metadata = lease.Metadata;
        if (metadata.State != WindowsProofUploadSessionStates.RequestStarted)
        {
            throw new InvalidOperationException("Windows proof session is not in request_started state.");
        }

        if (metadata.PreparedGenerationId is not null
            && (!string.Equals(metadata.PreparedGenerationId, prepared.GenerationId, StringComparison.Ordinal)
                || !string.Equals(metadata.PreparedInventoryDigest, prepared.InventoryDigest, StringComparison.Ordinal)
                || !string.Equals(metadata.PreparedCandidateVersion, prepared.CandidateVersion, StringComparison.Ordinal)))
        {
            throw new InvalidOperationException("Prepared Windows proof generation conflicts with durable session state.");
        }

        metadata = metadata with
        {
            PreparedGenerationId = prepared.GenerationId,
            PreparedCandidateVersion = prepared.CandidateVersion,
            PreparedInventoryDigest = prepared.InventoryDigest,
            ExpectedCurrentGenerationId = metadata.PreparedGenerationId is null
                ? expectedCurrentGenerationId
                : metadata.ExpectedCurrentGenerationId
        };
        PersistMetadata(sessionRoot, metadata);
        lease.ReplaceMetadata(metadata);
    }

    internal void MarkCompleted(
        string sessionRoot,
        WindowsProofUploadCompletionLease lease,
        WindowsProofUploadCompletionResult result)
    {
        WindowsProofUploadSessionMetadata metadata = lease.Metadata;
        if (metadata.State == WindowsProofUploadSessionStates.Completed)
        {
            if (metadata.CompletionResult != result)
            {
                throw new InvalidOperationException("Completed Windows proof result conflicts with durable receipt.");
            }
            return;
        }

        if (metadata.State != WindowsProofUploadSessionStates.RequestStarted
            || !string.Equals(metadata.PreparedGenerationId, result.GenerationId, StringComparison.Ordinal)
            || !string.Equals(metadata.PreparedInventoryDigest, result.InventoryDigest, StringComparison.Ordinal)
            || !string.Equals(metadata.PreparedCandidateVersion, result.CandidateVersion, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Windows proof activation result does not match the prepared session.");
        }

        metadata = metadata with
        {
            State = WindowsProofUploadSessionStates.Completed,
            CompletionResult = result
        };
        PersistMetadata(sessionRoot, metadata);
        lease.ReplaceMetadata(metadata);
    }

    private WindowsProofUploadSessionMetadata RefreshUploadedState(WindowsProofUploadSessionMetadata metadata)
    {
        if (metadata.State is WindowsProofUploadSessionStates.RequestStarted or WindowsProofUploadSessionStates.Completed)
        {
            return metadata;
        }

        string manifestPath = Path.Combine(metadata.BundleRoot, ManifestFileName);
        if (!File.Exists(manifestPath))
        {
            return metadata with { State = WindowsProofUploadSessionStates.Created };
        }

        WindowsProofUploadManifestDescriptor descriptor = LoadManifestDescriptor(metadata.BundleRoot);
        foreach (WindowsProofUploadManifestArtifact artifact in descriptor.Artifacts)
        {
            string path = ResolveBundleTarget(metadata.BundleRoot, artifact.RelativePath);
            if (!File.Exists(path))
            {
                return metadata with { State = WindowsProofUploadSessionStates.Created };
            }

            (long size, string digest) = HashRegularFile(path, _options.MaxFileBytes);
            ValidateDeclaredContent(artifact, size, digest);
        }

        return metadata with
        {
            State = WindowsProofUploadSessionStates.Uploaded,
            ManifestSha256 = descriptor.ManifestSha256
        };
    }

    private void ValidateCompleteInventory(string bundleRoot)
    {
        WindowsProofUploadManifestDescriptor descriptor = LoadManifestDescriptor(bundleRoot);
        var allowed = descriptor.Artifacts
            .Select(static item => item.RelativePath)
            .Append(ManifestFileName)
            .ToHashSet(StringComparer.Ordinal);
        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (string path in Directory.EnumerateFileSystemEntries(bundleRoot, "*", SearchOption.AllDirectories))
        {
            FileAttributes attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException("Windows proof bundle must not contain links or reparse points.");
            }

            if ((attributes & FileAttributes.Directory) != 0)
            {
                continue;
            }

            string relative = Path.GetRelativePath(bundleRoot, path).Replace('\\', '/');
            if (!allowed.Contains(relative) || !observed.Add(relative))
            {
                throw new InvalidDataException("Windows proof bundle contains an undeclared or duplicate file.");
            }
        }

        if (!observed.SetEquals(allowed))
        {
            throw new InvalidDataException("Windows proof bundle inventory is incomplete.");
        }
    }

    private WindowsProofUploadManifestDescriptor LoadManifestDescriptor(string bundleRoot)
    {
        string path = ResolveBundleTarget(bundleRoot, ManifestFileName);
        (long _, string digest) = HashRegularFile(path, MaximumManifestBytes);
        return ParseManifest(path, digest);
    }

    private WindowsProofUploadManifestDescriptor ParseManifest(string path, string manifestDigest)
    {
        using FileStream stream = OpenRegularFile(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        using JsonDocument document = JsonDocument.Parse(stream, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 32
        });
        JsonElement root = document.RootElement;
        RequireString(root, "schemaVersion", ManifestSchemaVersion);
        string candidateVersion = RequireString(root, "candidateVersion");
        if (!CandidateVersionPattern.IsMatch(candidateVersion))
        {
            throw new InvalidDataException("Windows proof candidateVersion is invalid.");
        }

        RequireString(root, "channel", "preview");
        RequireString(root, "releaseScope", "proof_only");
        RequireString(root, "supportabilityState", "review_required");
        RequireString(root, "publicTrustPosture", "blocked");
        RequireBoolean(root, "cfAccessGated", expected: true);
        RequireBoolean(root, "revoked", expected: false);
        ValidateManifestFreshness(root);
        ValidateProofOnlyEvidence(root);

        JsonElement artifacts = RequireProperty(root, "artifacts");
        if (artifacts.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("Windows proof artifacts must be an array.");
        }

        var parsed = new List<WindowsProofUploadManifestArtifact>();
        var paths = new HashSet<string>(StringComparer.Ordinal);
        var kinds = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement element in artifacts.EnumerateArray())
        {
            string kind = RequireString(element, "kind");
            string artifactId = RequireString(element, "artifactId");
            string relativePath = NormalizeRelativePath(RequireString(element, "relativePath"));
            string fileName = RequireString(element, "fileName");
            long size = RequireInt64(element, "size");
            string sha256 = RequireString(element, "sha256");
            if (!AllowedKinds.Contains(kind)
                || !ArtifactIdPattern.IsMatch(artifactId)
                || size <= 0
                || size > _options.MaxFileBytes
                || !Sha256Pattern.IsMatch(sha256)
                || !string.Equals(Path.GetFileName(relativePath), fileName, StringComparison.Ordinal)
                || !paths.Add(relativePath)
                || !kinds.Add(kind))
            {
                throw new InvalidDataException("Windows proof artifact declaration is invalid or duplicated.");
            }

            ValidateKindPath(kind, relativePath);
            parsed.Add(new WindowsProofUploadManifestArtifact(
                kind,
                artifactId,
                relativePath,
                fileName,
                size,
                sha256));
        }

        if (parsed.Count > _options.MaxFilesPerSession || !RequiredKinds.IsSubsetOf(kinds))
        {
            throw new InvalidDataException("Windows proof manifest is missing required evidence or exceeds its file limit.");
        }

        return new WindowsProofUploadManifestDescriptor(candidateVersion, manifestDigest, parsed);
    }

    private void ValidateManifestFreshness(JsonElement root)
    {
        DateTimeOffset generatedAt = RequireUtcDateTimeOffset(root, "generatedAt");
        DateTimeOffset expiresAt = RequireUtcDateTimeOffset(root, "expiresAt");
        DateTimeOffset now = _timeProvider.GetUtcNow();
        if (generatedAt > now.Add(WindowsProofManifestValidator.MaximumClockSkew))
        {
            throw new InvalidDataException(
                "Windows proof generatedAt is unreasonably far in the future.");
        }

        if (expiresAt <= generatedAt
            || expiresAt - generatedAt > WindowsProofManifestValidator.MaximumProofLifetime)
        {
            throw new InvalidDataException(
                "Windows proof freshness lifetime must be positive and no longer than 24 hours.");
        }

        if (expiresAt <= now)
        {
            throw new InvalidDataException("Windows proof manifest has expired.");
        }
    }

    private static void ValidateProofOnlyEvidence(JsonElement root)
    {
        JsonElement proofOnly = RequireProperty(root, "proofOnlyPolicy");
        RequireBoolean(proofOnly, "enabled", true);
        RequireBoolean(proofOnly, "unsignedPreviewAllowed", true);
        RequireBoolean(proofOnly, "nativeWindowsValidationRequired", true);

        JsonElement signing = RequireProperty(root, "signing");
        string signingStatus = RequireString(signing, "status");
        if (signingStatus is not "skipped_preview" and not "pass")
        {
            throw new InvalidDataException("Windows proof signing status is invalid.");
        }
        RequireBoolean(signing, "proofOnlyPolicyRecorded", true);

        JsonElement smoke = RequireProperty(root, "compatibilitySmoke");
        RequireString(smoke, "status", "pass");
        RequireString(smoke, "executionEnvironment", "wine_compatibility");
        RequireBoolean(smoke, "nativeWindows", false);

        JsonElement visual = RequireProperty(root, "visualExitGate");
        RequireString(visual, "status", "external_only");
        if (visual.TryGetProperty("evidenceArtifactId", out JsonElement visualEvidence)
            && visualEvidence.ValueKind is not JsonValueKind.Null)
        {
            throw new InvalidDataException("Proof-only visual exit evidence must remain external until native capture.");
        }

        JsonElement handoff = RequireProperty(root, "nativeHostHandoff");
        RequireString(handoff, "status", "ready_for_windows_host");
        RequireString(handoff, "onlyBlocker", "visual_proof");
        RequireBoolean(handoff, "onlyBlockerIsVisualProof", true);
    }

    private static void ValidateKindPath(string kind, string path)
    {
        bool accepted = kind switch
        {
            "installer" => path.StartsWith("files/", StringComparison.Ordinal) && path.EndsWith("-installer.exe", StringComparison.Ordinal),
            "bootstrap_payload" => path.StartsWith("files/", StringComparison.Ordinal) && path.EndsWith("-payload.zip", StringComparison.Ordinal),
            "bootstrap_metadata" => path.StartsWith("files/", StringComparison.Ordinal) && path.EndsWith("-payload.zip.json", StringComparison.Ordinal),
            "signing_receipt" => path.StartsWith("signing/", StringComparison.Ordinal) && path.EndsWith(".receipt.json", StringComparison.Ordinal),
            "startup_smoke_receipt" => path.StartsWith("startup-smoke/", StringComparison.Ordinal) && path.EndsWith(".receipt.json", StringComparison.Ordinal),
            "build_provenance_receipt" => path.StartsWith("proof/build-provenance/v1/invocations/", StringComparison.Ordinal) && path.EndsWith(".json", StringComparison.Ordinal),
            "sbom" => path.StartsWith("proof/build-provenance/v1/sbom/", StringComparison.Ordinal) && path.EndsWith(".cdx.json", StringComparison.Ordinal),
            "visual_handoff" => path.EndsWith("WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json", StringComparison.Ordinal),
            "visual_exit_evidence" => path.EndsWith("WINDOWS_INSTALLER_VISUAL_PROOF.generated.json", StringComparison.Ordinal),
            _ => false
        };
        if (!accepted)
        {
            throw new InvalidDataException($"Windows proof artifact path is not allowlisted for kind '{kind}'.");
        }
    }

    private bool TryAssembleChunks(
        string bundleRoot,
        string target,
        string stagingRoot,
        WindowsProofUploadManifestArtifact declaration,
        int totalChunks)
    {
        string[] chunks = Enumerable.Range(0, totalChunks)
            .Select(index => Path.Combine(stagingRoot, $"{index:D4}.chunk"))
            .ToArray();
        if (chunks.Any(static path => !File.Exists(path)))
        {
            return false;
        }

        long totalBytes = chunks.Sum(path => new FileInfo(path).Length);
        if (totalBytes != declaration.Size || totalBytes > _options.MaxFileBytes)
        {
            TryDeleteDirectory(stagingRoot);
            throw new InvalidDataException("Chunk inventory size does not match the declared Windows proof file.");
        }

        EnsureSafeParentPath(bundleRoot, target, create: true);
        string temporary = Path.Combine(
            Path.GetDirectoryName(target)!,
            $".{Path.GetFileName(target)}.{Guid.NewGuid():N}.assemble");
        try
        {
            using (FileStream output = OpenRegularFile(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                foreach (string chunk in chunks)
                {
                    using FileStream input = OpenRegularFile(chunk, FileMode.Open, FileAccess.Read, FileShare.Read);
                    input.CopyTo(output);
                }
                output.Flush(flushToDisk: true);
            }

            (long size, string digest) = HashRegularFile(temporary, _options.MaxFileBytes);
            ValidateDeclaredContent(declaration, size, digest);
            File.Move(temporary, target, overwrite: false);
            EnsureOwnerOnlyFile(target);
            TryDeleteDirectory(stagingRoot);
            return true;
        }
        finally
        {
            TryDeleteFile(temporary);
        }
    }

    private WindowsProofChunkBinding ReadOrCreateChunkBinding(
        string path,
        string relativePath,
        int totalChunks,
        WindowsProofUploadManifestArtifact declaration)
    {
        if (File.Exists(path))
        {
            using FileStream existing = OpenRegularFile(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            WindowsProofChunkBinding? binding = JsonSerializer.Deserialize<WindowsProofChunkBinding>(existing, JsonOptions);
            if (binding is null
                || !string.Equals(binding.RelativePath, relativePath, StringComparison.Ordinal)
                || !string.Equals(binding.ExpectedSha256, declaration.Sha256, StringComparison.Ordinal)
                || binding.ExpectedSize != declaration.Size)
            {
                throw new InvalidDataException("Chunk staging binding is invalid.");
            }
            return binding;
        }

        var created = new WindowsProofChunkBinding(
            relativePath,
            totalChunks,
            declaration.Size,
            declaration.Sha256);
        PersistJsonAtomically(path, created);
        return created;
    }

    private static void ValidateDeclaredContent(
        WindowsProofUploadManifestArtifact declaration,
        long size,
        string digest)
    {
        if (size != declaration.Size || !FixedTimeDigestEquals(digest, declaration.Sha256))
        {
            throw new InvalidDataException("Uploaded Windows proof file does not match its declared size and SHA-256.");
        }
    }

    private static async Task<(long Size, string Sha256)> CopyBoundedAsync(
        Stream source,
        string destination,
        long maximumBytes,
        CancellationToken cancellationToken)
    {
        using FileStream output = OpenRegularFile(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[128 * 1024];
        long total = 0;
        while (true)
        {
            int read = await source.ReadAsync(buffer, cancellationToken);
            if (read == 0)
            {
                break;
            }

            total += read;
            if (total > maximumBytes)
            {
                throw new InvalidDataException("Windows proof upload exceeds its bounded byte limit.");
            }
            hash.AppendData(buffer, 0, read);
            await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
        }
        output.Flush(flushToDisk: true);
        EnsureOwnerOnlyFile(destination);
        return (total, Convert.ToHexStringLower(hash.GetHashAndReset()));
    }

    private static (long Size, string Sha256) HashRegularFile(string path, long maximumBytes)
    {
        using FileStream stream = OpenRegularFile(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length <= 0 || stream.Length > maximumBytes)
        {
            throw new InvalidDataException("Windows proof file size is outside its allowed bounds.");
        }
        return (stream.Length, Convert.ToHexStringLower(SHA256.HashData(stream)));
    }

    private static async Task<long> ValidateIdempotentExistingFileAsync(
        WindowsProofUploadSessionMetadata metadata,
        string relativePath,
        Stream content,
        long? expectedSize,
        string? expectedSha256,
        long maximumBytes,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(expectedSha256))
        {
            throw new InvalidOperationException("Existing upload cannot be rebound without its durable digest.");
        }

        string temporary = Path.Combine(
            Path.GetDirectoryName(metadata.BundleRoot)!,
            $".{metadata.SessionId}.{Guid.NewGuid():N}.replay");
        try
        {
            (long size, string digest) = await CopyBoundedAsync(content, temporary, maximumBytes, cancellationToken);
            if ((expectedSize is not null && expectedSize != size)
                || !FixedTimeDigestEquals(digest, expectedSha256))
            {
                throw new InvalidOperationException("Upload replay content differs from the durable file.");
            }
            return size;
        }
        finally
        {
            TryDeleteFile(temporary);
        }
    }

    private WindowsProofUploadSessionMetadata ReadMetadata(
        string sessionRoot,
        string authorizationBinding,
        bool allowCompleted)
    {
        EnsureRegularDirectory(sessionRoot, "Windows proof upload session");
        string path = Path.Combine(sessionRoot, "session.json");
        using FileStream stream = OpenRegularFile(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        WindowsProofUploadSessionMetadata? metadata =
            JsonSerializer.Deserialize<WindowsProofUploadSessionMetadata>(stream, JsonOptions);
        if (metadata is null
            || !string.Equals(metadata.SchemaVersion, SessionSchemaVersion, StringComparison.Ordinal)
            || !string.Equals(metadata.SessionKind, SessionKind, StringComparison.Ordinal)
            || !string.Equals(metadata.SessionId, Path.GetFileName(sessionRoot), StringComparison.Ordinal)
            || !FixedTimeDigestEquals(metadata.AuthorizationBinding, NormalizeAuthorizationBinding(authorizationBinding)))
        {
            throw new InvalidDataException("Windows proof upload session metadata or authorization binding is invalid.");
        }

        if (metadata.ExpiresAtUtc <= _timeProvider.GetUtcNow()
            && metadata.State != WindowsProofUploadSessionStates.Completed)
        {
            throw new InvalidOperationException("Windows proof upload session has expired.");
        }
        if (!allowCompleted && metadata.State == WindowsProofUploadSessionStates.Completed)
        {
            throw new InvalidOperationException("Windows proof upload session is already completed.");
        }
        return metadata;
    }

    private static void EnsureUploadMutable(WindowsProofUploadSessionMetadata metadata)
    {
        if (metadata.State is WindowsProofUploadSessionStates.RequestStarted or WindowsProofUploadSessionStates.Completed)
        {
            throw new InvalidOperationException("Windows proof upload is immutable after completion starts.");
        }
    }

    private WindowsProofUploadSessionMetadata? FindByAuthorization(string root, string binding)
    {
        foreach (string directory in Directory.EnumerateDirectories(root))
        {
            string name = Path.GetFileName(directory);
            if (!Guid.TryParseExact(name, "N", out _))
            {
                continue;
            }
            try
            {
                string path = Path.Combine(directory, "session.json");
                using FileStream stream = OpenRegularFile(path, FileMode.Open, FileAccess.Read, FileShare.Read);
                WindowsProofUploadSessionMetadata? metadata =
                    JsonSerializer.Deserialize<WindowsProofUploadSessionMetadata>(stream, JsonOptions);
                if (metadata is not null
                    && string.Equals(metadata.SessionKind, SessionKind, StringComparison.Ordinal)
                    && FixedTimeDigestEquals(metadata.AuthorizationBinding, binding))
                {
                    return metadata;
                }
            }
            catch (FileNotFoundException)
            {
                // Concurrently purged before the root lock was acquired by an older process.
            }
        }
        return null;
    }

    private void PurgeExpiredSessionsUnderLock(string root, DateTimeOffset now)
    {
        foreach (string directory in Directory.EnumerateDirectories(root))
        {
            string name = Path.GetFileName(directory);
            if (!Guid.TryParseExact(name, "N", out _))
            {
                continue;
            }

            try
            {
                EnsureRegularDirectory(directory, "Windows proof upload session");
                string path = Path.Combine(directory, "session.json");
                using FileStream stream = OpenRegularFile(path, FileMode.Open, FileAccess.Read, FileShare.Read);
                WindowsProofUploadSessionMetadata? metadata =
                    JsonSerializer.Deserialize<WindowsProofUploadSessionMetadata>(stream, JsonOptions);
                if (metadata is null || !string.Equals(metadata.SessionKind, SessionKind, StringComparison.Ordinal))
                {
                    continue;
                }

                DateTimeOffset deleteAfter = metadata.State == WindowsProofUploadSessionStates.Completed
                    ? metadata.CompletionResult!.ActivatedAtUtc.Add(_options.CompletedReceiptRetention)
                    : metadata.ExpiresAtUtc;
                if (deleteAfter <= now)
                {
                    TryDeleteDirectory(directory);
                }
            }
            catch (IOException)
            {
                // An active operation owns the session; leave it for the next sweep.
            }
        }
    }

    private string ResolveSessionsRoot()
    {
        string configured = (_configuration[SessionsRootKey] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(configured))
        {
            throw new InvalidOperationException(
                $"{SessionsRootKey} must name durable storage before Windows proof uploads can be enabled.");
        }

        string root = Path.GetFullPath(configured);
        string proofRootValue = (_configuration[WindowsProofGenerationStore.RootConfigurationKey] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(proofRootValue))
        {
            throw new InvalidOperationException(
                $"{WindowsProofGenerationStore.RootConfigurationKey} must be configured before Windows proof uploads can be enabled.");
        }

        string proofRoot = Path.GetFullPath(proofRootValue);
        string canonicalRoot = Path.GetFullPath(new ReleaseShelfGenerationStore(_configuration).ResolveDownloadsRoot());
        EnsureRootsDoNotOverlap(root, proofRoot, "Windows proof upload and proof generation roots");
        EnsureRootsDoNotOverlap(root, canonicalRoot, "Windows proof upload and canonical release shelf roots");
        EnsureAncestorChainWithoutLinks(root);
        EnsureOwnerOnlyDirectory(root);
        EnsureAncestorChainWithoutLinks(root);
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
                    "Windows proof upload storage must not traverse symbolic links or reparse points.");
            }
            current = current.Parent;
        }
    }

    private static string CanonicalizeSessionId(string sessionId)
    {
        if (!Guid.TryParseExact((sessionId ?? string.Empty).Trim(), "N", out Guid parsed))
        {
            throw new InvalidDataException("Windows proof upload sessionId must be a canonical 32-character GUID.");
        }
        return parsed.ToString("N");
    }

    private string NormalizeRelativePath(string relativePath)
    {
        string value = (relativePath ?? string.Empty).Trim();
        if (value.Length == 0
            || Encoding.UTF8.GetByteCount(value) > _options.MaxPathBytes
            || value.StartsWith('/')
            || value.Contains('\\')
            || value.Contains('\0')
            || value.Any(char.IsControl))
        {
            throw new InvalidDataException("Windows proof upload path must be a bounded portable relative path.");
        }

        string[] segments = value.Split('/', StringSplitOptions.None);
        if (segments.Any(static segment => segment.Length == 0 || segment is "." or ".."))
        {
            throw new InvalidDataException("Windows proof upload path contains an invalid segment.");
        }
        return string.Join('/', segments);
    }

    private static string ResolveBundleTarget(string bundleRoot, string relativePath)
    {
        string root = Path.GetFullPath(bundleRoot);
        string target = Path.GetFullPath(Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        string prefix = root.EndsWith(Path.DirectorySeparatorChar)
            ? root
            : root + Path.DirectorySeparatorChar;
        if (!target.StartsWith(prefix, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Windows proof upload path escapes the session bundle.");
        }
        return target;
    }

    private static string ResolveChunkStagingRoot(string sessionRoot, string relativePath)
    {
        string digest = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(relativePath)));
        return Path.Combine(sessionRoot, "staging", digest);
    }

    private static void EnsureSafeParentPath(string bundleRoot, string target, bool create)
    {
        EnsureRegularDirectory(bundleRoot, "Windows proof bundle");
        string root = Path.GetFullPath(bundleRoot);
        string? parent = Path.GetDirectoryName(target);
        if (parent is null)
        {
            throw new InvalidDataException("Windows proof target parent is invalid.");
        }

        string relative = Path.GetRelativePath(root, parent);
        string current = root;
        foreach (string segment in relative.Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, segment);
            if (Directory.Exists(current))
            {
                EnsureRegularDirectory(current, "Windows proof bundle directory");
            }
            else if (create)
            {
                EnsureOwnerOnlyDirectory(current);
            }
            else
            {
                throw new DirectoryNotFoundException("Windows proof bundle directory is missing.");
            }
        }

        if (File.Exists(target))
        {
            EnsureRegularFile(target, "Windows proof bundle file");
        }
    }

    private static FileStream AcquireSessionLock(string sessionRoot)
    {
        EnsureRegularDirectory(sessionRoot, "Windows proof upload session");
        return AcquireExclusiveLock(Path.Combine(sessionRoot, ".lock"));
    }

    private static FileStream AcquireExclusiveLock(string path)
        => OpenRegularFile(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);

    private static FileStream OpenRegularFile(
        string path,
        FileMode mode,
        FileAccess access,
        FileShare share)
    {
        if (File.Exists(path))
        {
            EnsureRegularFile(path, "Windows proof storage file");
        }

        var options = new FileStreamOptions
        {
            Mode = mode,
            Access = access,
            Share = share,
            Options = FileOptions.SequentialScan
        };
        if (!OperatingSystem.IsWindows() && mode is FileMode.CreateNew or FileMode.OpenOrCreate)
        {
            options.UnixCreateMode = OwnerFileMode;
        }
        return new FileStream(path, options);
    }

    private static void PersistMetadata(string sessionRoot, WindowsProofUploadSessionMetadata metadata)
        => PersistJsonAtomically(Path.Combine(sessionRoot, "session.json"), metadata);

    private static void PersistJsonAtomically<T>(string path, T value)
    {
        string directory = Path.GetDirectoryName(path)
            ?? throw new InvalidDataException("Windows proof metadata path is invalid.");
        EnsureOwnerOnlyDirectory(directory);
        string temporary = Path.Combine(directory, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            using (FileStream stream = OpenRegularFile(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                JsonSerializer.Serialize(stream, value, JsonOptions);
                stream.Flush(flushToDisk: true);
            }
            File.Move(temporary, path, overwrite: true);
            EnsureOwnerOnlyFile(path);
        }
        finally
        {
            TryDeleteFile(temporary);
        }
    }

    private static void EnsureOwnerOnlyDirectory(string path)
    {
        if (Directory.Exists(path))
        {
            EnsureRegularDirectory(path, "Windows proof storage directory");
        }
        else
        {
            Directory.CreateDirectory(path);
        }
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerDirectoryMode);
        }
    }

    private static void EnsureRegularDirectory(string path, string label)
    {
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.Directory) == 0
            || (attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException($"{label} must be a regular directory.");
        }
    }

    private static void EnsureRegularFile(string path, string label)
    {
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
        {
            throw new InvalidDataException($"{label} must be a regular file.");
        }
    }

    private static void EnsureOwnerOnlyFile(string path)
    {
        EnsureRegularFile(path, "Windows proof storage file");
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerFileMode);
        }
    }

    private static string NormalizeAuthorizationBinding(string binding)
    {
        string value = (binding ?? string.Empty).Trim().ToLowerInvariant();
        if (!Sha256Pattern.IsMatch(value))
        {
            throw new InvalidDataException("Windows proof authorization binding must be a SHA-256 digest.");
        }
        return value;
    }

    private static bool FixedTimeDigestEquals(string left, string right)
    {
        if (left.Length != right.Length)
        {
            return false;
        }
        return CryptographicOperations.FixedTimeEquals(
            Encoding.ASCII.GetBytes(left),
            Encoding.ASCII.GetBytes(right));
    }

    private static JsonElement RequireProperty(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value))
        {
            throw new InvalidDataException($"Windows proof manifest is missing '{name}'.");
        }
        return value;
    }

    private static string RequireString(JsonElement element, string name)
    {
        JsonElement value = RequireProperty(element, name);
        string? text = value.ValueKind == JsonValueKind.String ? value.GetString() : null;
        if (string.IsNullOrWhiteSpace(text))
        {
            throw new InvalidDataException($"Windows proof manifest '{name}' must be a non-empty string.");
        }
        return text;
    }

    private static void RequireString(JsonElement element, string name, string expected)
    {
        if (!string.Equals(RequireString(element, name), expected, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Windows proof manifest '{name}' must be '{expected}'.");
        }
    }

    private static void RequireBoolean(JsonElement element, string name, bool expected)
    {
        JsonElement value = RequireProperty(element, name);
        if (value.ValueKind is not (JsonValueKind.True or JsonValueKind.False)
            || value.GetBoolean() != expected)
        {
            throw new InvalidDataException($"Windows proof manifest '{name}' must be {expected.ToString().ToLowerInvariant()}.");
        }
    }

    private static DateTimeOffset RequireUtcDateTimeOffset(JsonElement element, string name)
    {
        string raw = RequireString(element, name);
        if (!raw.EndsWith('Z')
            || !DateTimeOffset.TryParse(
                raw,
                CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind,
                out DateTimeOffset value)
            || value.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException(
                $"Windows proof manifest '{name}' must be an RFC 3339 UTC timestamp ending in Z.");
        }

        return value;
    }

    private static long RequireInt64(JsonElement element, string name)
    {
        JsonElement value = RequireProperty(element, name);
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt64(out long result))
        {
            throw new InvalidDataException($"Windows proof manifest '{name}' must be an integer.");
        }
        return result;
    }

    private static WindowsProofUploadSession ToPublic(WindowsProofUploadSessionMetadata metadata)
        => new(
            metadata.SessionId,
            metadata.State,
            metadata.ExpiresAtUtc,
            metadata.SingleUseAuthorization,
            metadata.ManifestSha256,
            metadata.CompletionResult);

    private static bool TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static bool TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                EnsureRegularDirectory(path, "Windows proof cleanup directory");
                Directory.Delete(path, recursive: true);
            }
            return true;
        }
        catch
        {
            return false;
        }
    }

    internal sealed record WindowsProofUploadSessionMetadata(
        string SchemaVersion,
        string SessionKind,
        string SessionId,
        string State,
        DateTimeOffset CreatedAtUtc,
        DateTimeOffset ExpiresAtUtc,
        string BundleRoot,
        string AuthorizationBinding,
        bool SingleUseAuthorization,
        DateTimeOffset? AuthorizationExpiresAtUtc,
        string? ManifestSha256,
        string? RequestId,
        string? PreparedGenerationId,
        string? PreparedCandidateVersion,
        string? PreparedInventoryDigest,
        string? ExpectedCurrentGenerationId,
        WindowsProofUploadCompletionResult? CompletionResult);

    private sealed record WindowsProofChunkBinding(
        string RelativePath,
        int TotalChunks,
        long ExpectedSize,
        string ExpectedSha256);
}

public sealed class WindowsProofUploadCompletionLease : IDisposable
{
    private readonly WindowsProofUploadSessionService _owner;
    private readonly string _sessionRoot;
    private FileStream? _sessionLock;

    internal WindowsProofUploadCompletionLease(
        WindowsProofUploadSessionService owner,
        string sessionRoot,
        FileStream sessionLock,
        WindowsProofUploadSessionService.WindowsProofUploadSessionMetadata metadata)
    {
        _owner = owner;
        _sessionRoot = sessionRoot;
        _sessionLock = sessionLock;
        Metadata = metadata;
    }

    internal WindowsProofUploadSessionService.WindowsProofUploadSessionMetadata Metadata { get; private set; }

    public string SessionId => Metadata.SessionId;

    public string State => Metadata.State;

    public string BundleRoot => Metadata.BundleRoot;

    public string ManifestSha256 => Metadata.ManifestSha256
        ?? throw new InvalidOperationException("Windows proof manifest digest is not recorded.");

    public string RequestId => Metadata.RequestId
        ?? throw new InvalidOperationException("Windows proof completion request is not recorded.");

    public string? PreparedGenerationId => Metadata.PreparedGenerationId;

    public string? PreparedInventoryDigest => Metadata.PreparedInventoryDigest;

    public string? PreparedCandidateVersion => Metadata.PreparedCandidateVersion;

    public string? ExpectedCurrentGenerationId => Metadata.ExpectedCurrentGenerationId;

    public WindowsProofUploadCompletionResult? CompletionResult => Metadata.CompletionResult;

    internal WindowsProofUploadManifestDescriptor Descriptor => _owner.LoadDescriptor(Metadata);

    public void RecordPrepared(WindowsProofPreparedGeneration prepared, string? expectedCurrentGenerationId)
        => _owner.RecordPrepared(_sessionRoot, this, prepared, expectedCurrentGenerationId);

    public void MarkCompleted(WindowsProofUploadCompletionResult result)
        => _owner.MarkCompleted(_sessionRoot, this, result);

    internal void ReplaceMetadata(WindowsProofUploadSessionService.WindowsProofUploadSessionMetadata metadata)
        => Metadata = metadata;

    public void Dispose()
    {
        _sessionLock?.Dispose();
        _sessionLock = null;
    }
}
