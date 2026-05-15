namespace Chummer.Run.Api.Services.Community;

public sealed record DispatchFactPacket(
    string WorldId,
    int Turn,
    string SourceReceiptId,
    string SourceKind,
    string Title,
    string Summary,
    IReadOnlyList<string> Highlights,
    IReadOnlyList<string> InvolvedFactions,
    IReadOnlyList<string> InvolvedDistricts,
    IReadOnlyList<string> PackagePressureLinks,
    string PrivacyStatus,
    bool PublicSafe,
    bool PrivateDataUsed,
    bool SourcebookTextUsed);

public sealed record DispatchDraft(
    string DraftId,
    string Adapter,
    string Status,
    DispatchFactPacket Facts,
    string Body,
    string GeneratedAtUtc);

public sealed record DispatchGateReceipt(
    string ReceiptId,
    string DispatchId,
    IReadOnlyList<string> SourceReceiptIds,
    string Status,
    bool PrivacyPassed,
    bool PiiPassed,
    bool SourcebookPassed,
    bool ProviderLeakPassed,
    bool SupportDataPassed,
    bool FactConsistencyPassed,
    bool TonePassed,
    bool PublicationAuthorityPassed,
    string CheckedAtUtc);

public sealed record DispatchApprovalReceipt(
    string ReceiptId,
    string DispatchId,
    string Status,
    string Reviewer,
    string HumanReviewStatus,
    string ApprovedAtUtc);

public sealed record DispatchPublicationReceipt(
    string ReceiptId,
    string DispatchId,
    string Status,
    IReadOnlyList<string> SourceReceiptIds,
    string PublishedAtUtc);

public sealed record DispatchEmailDigest(
    string DispatchId,
    string Title,
    string Excerpt,
    IReadOnlyList<string> Highlights,
    string DispatchUrl,
    string SourceReceiptUrl,
    string PrivacyNote);

public sealed record BlackLedgerDispatch(
    string DispatchId,
    string WorldId,
    int Turn,
    string Type,
    string Scope,
    string SourceReceiptId,
    string SourceReceiptHref,
    string Title,
    string Summary,
    string Body,
    IReadOnlyList<string> InvolvedFactions,
    IReadOnlyList<string> InvolvedDistricts,
    IReadOnlyList<string> PackagePressureLinks,
    string PrivacyStatus,
    string GeneratedBy,
    string HumanReviewStatus,
    string CreatedAtUtc,
    bool PublicSafe,
    bool AiGenerated,
    string Href);
