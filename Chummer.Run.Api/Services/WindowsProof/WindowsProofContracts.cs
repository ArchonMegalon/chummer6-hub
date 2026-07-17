namespace Chummer.Run.Api.Services.WindowsProof;

public interface IWindowsProofGenerationStore
{
    Task<WindowsProofPreparedGeneration> PrepareAsync(
        WindowsProofPrepareRequest request,
        CancellationToken cancellationToken = default);

    Task<WindowsProofActivationReceipt> ActivateAsync(
        WindowsProofActivationRequest request,
        CancellationToken cancellationToken = default);

    WindowsProofGenerationSnapshot? CaptureCurrent();

    WindowsProofGenerationSnapshot? CaptureGeneration(string generationId);

    WindowsProofGenerationSnapshot? CaptureCandidate(string candidateVersion);

    Task<WindowsProofGenerationSnapshot?> CaptureCurrentAsync(
        CancellationToken cancellationToken = default);

    Task<WindowsProofGenerationSnapshot?> CaptureGenerationAsync(
        string generationId,
        CancellationToken cancellationToken = default);

    Task<WindowsProofGenerationSnapshot?> CaptureCandidateAsync(
        string candidateVersion,
        CancellationToken cancellationToken = default);
}

public sealed record WindowsProofPrepareRequest(
    string RequestId,
    string SourceRoot,
    string ExpectedManifestSha256);

public sealed record WindowsProofActivationRequest(
    string RequestId,
    string GenerationId,
    string InventoryDigest,
    string? ExpectedCurrentGenerationId);

public sealed record WindowsProofPreparedGeneration(
    string GenerationId,
    string CandidateVersion,
    string InventoryDigest,
    DateTimeOffset CreatedAt);

public sealed record WindowsProofActivationReceipt(
    string ActivationId,
    string GenerationId,
    string CandidateVersion,
    string InventoryDigest,
    DateTimeOffset ActivatedAt,
    string? PreviousGenerationId);

public enum WindowsProofArtifactKind
{
    Installer,
    BootstrapPayload,
    BootstrapMetadata,
    SigningReceipt,
    StartupSmokeReceipt,
    BuildProvenanceReceipt,
    Sbom,
    VisualHandoff,
    VisualExitEvidence
}

public sealed record WindowsProofInventoryEntry(
    WindowsProofArtifactKind Kind,
    string ArtifactId,
    string Head,
    string Rid,
    string FileName,
    string RelativePath,
    string ContentType,
    long Size,
    string Sha256);

public sealed record WindowsProofOnlyPolicy(
    bool Enabled,
    bool UnsignedPreviewAllowed,
    bool NativeWindowsValidationRequired);

public sealed record WindowsProofSigningEvidence(
    string Status,
    bool ProofOnlyPolicyRecorded,
    string ReceiptArtifactId);

public sealed record WindowsProofCompatibilitySmokeEvidence(
    string Status,
    string ExecutionEnvironment,
    bool NativeWindows,
    string ReceiptArtifactId,
    string PayloadAcquisitionMode);

public sealed record WindowsProofVisualExitGate(
    string Status,
    string? EvidenceArtifactId);

public sealed record WindowsProofNativeHostHandoff(
    string Status,
    string OnlyBlocker,
    bool OnlyBlockerIsVisualProof,
    string HandoffArtifactId);

public sealed record WindowsProofManifest(
    string SchemaVersion,
    string CandidateVersion,
    string Channel,
    string ReleaseScope,
    string SupportabilityState,
    string PublicTrustPosture,
    bool CfAccessGated,
    bool Revoked,
    WindowsProofOnlyPolicy ProofOnlyPolicy,
    WindowsProofSigningEvidence Signing,
    WindowsProofCompatibilitySmokeEvidence CompatibilitySmoke,
    WindowsProofVisualExitGate VisualExitGate,
    WindowsProofNativeHostHandoff NativeHostHandoff,
    IReadOnlyList<WindowsProofInventoryEntry> Artifacts,
    DateTimeOffset? GeneratedAt = null,
    DateTimeOffset? ExpiresAt = null);

public sealed record WindowsProofDeliveryState(
    string SchemaVersion,
    bool Revoked,
    long RevocationGeneration,
    string? Reason,
    DateTimeOffset UpdatedAt);

public sealed class WindowsProofGenerationSnapshot
{
    private readonly Func<WindowsProofInventoryEntry, Stream> _openVerifiedArtifact;

    internal WindowsProofGenerationSnapshot(
        string generationId,
        WindowsProofManifest manifest,
        IReadOnlyList<WindowsProofInventoryEntry> inventory,
        DateTimeOffset createdAt,
        DateTimeOffset? activatedAt,
        long revocationGeneration,
        Func<WindowsProofInventoryEntry, Stream> openVerifiedArtifact)
    {
        GenerationId = generationId;
        Manifest = manifest;
        Inventory = inventory;
        CreatedAt = createdAt;
        ActivatedAt = activatedAt;
        RevocationGeneration = revocationGeneration;
        _openVerifiedArtifact = openVerifiedArtifact;
    }

    public string GenerationId { get; }

    public string CandidateVersion => Manifest.CandidateVersion;

    public WindowsProofManifest Manifest { get; }

    public IReadOnlyList<WindowsProofInventoryEntry> Inventory { get; }

    public DateTimeOffset CreatedAt { get; }

    public DateTimeOffset? ActivatedAt { get; }

    public long RevocationGeneration { get; }

    public Stream OpenVerifiedArtifact(WindowsProofInventoryEntry entry)
    {
        ArgumentNullException.ThrowIfNull(entry);
        return _openVerifiedArtifact(entry);
    }

    public Task<Stream> OpenVerifiedArtifactAsync(
        WindowsProofInventoryEntry entry,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(OpenVerifiedArtifact(entry));
    }
}
