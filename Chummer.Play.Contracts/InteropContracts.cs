namespace Chummer.Play.Contracts.Interop;

public enum InteropAssetKind
{
    Character,
    Npc,
    Session,
    Encounter,
    Prep
}

public static class InteropCompatibilityStates
{
    public const string Compatible = "compatible";
    public const string CompatibleWithWarnings = "compatible-with-warnings";
    public const string Incompatible = "incompatible";
}

public static class InteropCompatibilityNoteSeverities
{
    public const string Info = "info";
    public const string Warning = "warning";
    public const string Error = "error";
}

public sealed record InteropCompatibilityNote(
    string Code,
    string Severity,
    string Summary);

public sealed record InteropCompatibilityReceipt(
    string FormatId,
    string CompatibilityState,
    string ContextSummary,
    string ReceiptSummary,
    string NextSafeAction,
    IReadOnlyList<string> SupportedExchangeFormats,
    IReadOnlyList<InteropCompatibilityNote> Notes);

public sealed record InteropProvenancePointer(
    string Kind,
    string Reference,
    string Detail);

public sealed record InteropRoundTripProvenance(
    string ContractFamily,
    string SchemaVersion,
    string SourceSystem,
    string SourceAssetId,
    string PayloadSha256,
    DateTimeOffset ExportedAtUtc,
    string ExportedBy,
    string RoundTripId,
    IReadOnlyList<InteropProvenancePointer> Pointers);

public sealed record InteropAssetDocument(
    InteropAssetKind AssetKind,
    string AssetId,
    string DisplayName,
    string PayloadJson,
    InteropRoundTripProvenance Provenance);

public sealed record InteropExportRequest(
    string CampaignId,
    string? SessionId = null,
    IReadOnlyList<InteropAssetKind>? AssetKinds = null,
    IReadOnlyList<string>? AssetIds = null,
    string RequestedBy = "system",
    string SchemaVersion = "1.0.0",
    string ContractFamily = "interop_export_v1");

public sealed record InteropExportManifest(
    int CharacterCount,
    int NpcCount,
    int SessionCount,
    int EncounterCount,
    int PrepCount,
    int TotalCount,
    string PackageSha256);

public sealed record InteropExportPackage(
    string PackageId,
    string CampaignId,
    string? SessionId,
    string ContractFamily,
    string SchemaVersion,
    DateTimeOffset ExportedAtUtc,
    string ExportedBy,
    InteropExportManifest Manifest,
    InteropCompatibilityReceipt Compatibility,
    IReadOnlyList<InteropAssetDocument> Assets);

public enum InteropImportMode
{
    InspectOnly,
    Merge,
    Replace
}

public sealed record InteropImportRequest(
    InteropExportPackage Package,
    string ImportedBy,
    InteropImportMode Mode = InteropImportMode.Merge);

public sealed record InteropImportAssetResult(
    InteropAssetKind AssetKind,
    string AssetId,
    string Outcome,
    bool ProvenanceRoundTrip,
    string? Detail = null);

public sealed record InteropImportResult(
    string PackageId,
    string CampaignId,
    string? SessionId,
    string ImportedBy,
    InteropImportMode Mode,
    int ImportedCount,
    int MutatedCount,
    int RejectedCount,
    bool ProvenanceRoundTrip,
    DateTimeOffset ImportedAtUtc,
    InteropCompatibilityReceipt Compatibility,
    IReadOnlyList<InteropImportAssetResult> Assets);

public sealed record InteropRoundTripRequest(
    InteropExportRequest Export,
    string ImportedBy,
    InteropImportMode Mode = InteropImportMode.Merge);

public sealed record InteropRoundTripResult(
    string RoundTripId,
    InteropExportPackage ExportPackage,
    InteropImportResult ImportResult,
    bool ProvenanceRoundTrip);
