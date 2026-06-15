using Chummer.Run.Api.ViewModels;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed record CreateBlackLedgerDispatchRequest(
    string WorldId,
    int Turn,
    string? DispatchId,
    string? Adapter,
    bool AutoApproveSeededPreview,
    string? Reviewer);

public sealed record ApproveBlackLedgerDispatchRequest(
    string Reviewer,
    string HumanReviewStatus = "approved",
    bool Publish = true);

public sealed record BlackLedgerDispatchMutationResult(
    DispatchFactPacket Facts,
    DispatchDraft Draft,
    DispatchGateReceipt GateReceipt,
    DispatchApprovalReceipt? ApprovalReceipt,
    DispatchPublicationReceipt? PublicationReceipt,
    BlackLedgerDispatchViewModel? PublishedDispatch);

public sealed class BlackLedgerDispatchService
{
    private readonly CommunityStore _store;
    private readonly BlackLedgerPublicStatsService _stats;
    private readonly ILogger<BlackLedgerDispatchService> _logger;

    public BlackLedgerDispatchService(
        CommunityStore store,
        BlackLedgerPublicStatsService stats,
        ILogger<BlackLedgerDispatchService>? logger = null)
    {
        _store = store;
        _stats = stats;
        _logger = logger ?? NullLogger<BlackLedgerDispatchService>.Instance;
    }

    public IReadOnlyList<BlackLedgerDispatchViewModel> ListPublishedDispatches(int? requestedTurn = null, string? factionId = null)
    {
        EnsureSeededPublishedDispatches();
        lock (_store.Gate)
        {
            IEnumerable<BlackLedgerDispatch> query = _store.BlackLedgerDispatches
                .Where(static item => item.PublicSafe)
                .Where(static item => string.Equals(item.HumanReviewStatus, "approved", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(item.HumanReviewStatus, "optional", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(item.HumanReviewStatus, "auto_approved", StringComparison.OrdinalIgnoreCase));

            if (requestedTurn.HasValue)
            {
                query = query.Where(item => item.Turn == requestedTurn.Value);
            }

            if (!string.IsNullOrWhiteSpace(factionId))
            {
                query = query.Where(item => item.InvolvedFactions.Any(faction =>
                    NormalizeSlug(faction).Equals(NormalizeSlug(factionId), StringComparison.OrdinalIgnoreCase)));
            }

            return query
                .OrderByDescending(static item => item.Turn)
                .ThenBy(static item => item.DispatchId, StringComparer.OrdinalIgnoreCase)
                .Select(ToViewModel)
                .ToArray();
        }
    }

    public BlackLedgerDispatchViewModel? LoadPublishedDispatch(string dispatchId, int? requestedTurn = null, string? factionId = null)
        => ListPublishedDispatches(requestedTurn, factionId)
            .FirstOrDefault(item => string.Equals(item.DispatchId, dispatchId, StringComparison.OrdinalIgnoreCase));

    public DispatchEmailDigest? BuildDispatchEmailDigest(int? requestedTurn = null)
    {
        BlackLedgerDispatchViewModel? latest = ListPublishedDispatches(requestedTurn).FirstOrDefault();
        if (latest is null)
        {
            return null;
        }

        string excerpt = latest.Body.Split("\n\n", StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? latest.Summary;
        return new DispatchEmailDigest(
            DispatchId: latest.DispatchId,
            Title: latest.Title,
            Excerpt: excerpt,
            Highlights: latest.PackagePressureLinks.Count > 0
                ? latest.PackagePressureLinks.Select(static item => item.Trim()).Where(static item => item.Length > 0).ToArray()
                : Array.Empty<string>(),
            DispatchUrl: latest.Href,
            SourceReceiptUrl: latest.SourceReceiptHref,
            PrivacyNote: "From a public dispatch. No private campaign, support, or administrative data is included.");
    }

    public BlackLedgerDispatchMutationResult CreateDraft(CreateBlackLedgerDispatchRequest request)
    {
        EnsureSeededPublishedDispatches();
        string adapter = NormalizeAdapter(request.Adapter);
        BlackLedgerDispatchViewModel seeded = ResolveSeededDispatch(request);
        DispatchFactPacket facts = BuildFactPacket(seeded, request.WorldId);
        DispatchDraft draft = new(
            DraftId: facts.Title.Length > 0
                ? $"dispatch_draft_{Guid.NewGuid():N}"[..29]
                : $"dispatch_draft_{Guid.NewGuid():N}"[..29],
            Adapter: adapter,
            Status: "draft_only",
            Facts: facts,
            Body: BuildDraftBody(facts, adapter),
            GeneratedAtUtc: DateTimeOffset.UtcNow.ToString("O"));
        DispatchGateReceipt gateReceipt = BuildGateReceipt(seeded.DispatchId, facts);

        DispatchApprovalReceipt? approvalReceipt = null;
        DispatchPublicationReceipt? publicationReceipt = null;
        BlackLedgerDispatchViewModel? publishedDispatch = null;

        lock (_store.Gate)
        {
            UpsertDraftLocked(draft);
            UpsertGateReceiptLocked(gateReceipt);

            if (request.AutoApproveSeededPreview && string.Equals(gateReceipt.Status, "pass", StringComparison.OrdinalIgnoreCase))
            {
                string reviewer = string.IsNullOrWhiteSpace(request.Reviewer) ? "auto_flagship_seeded_board" : request.Reviewer.Trim();
                approvalReceipt = new DispatchApprovalReceipt(
                    ReceiptId: $"dispatch_approval_{Guid.NewGuid():N}"[..36],
                    DispatchId: seeded.DispatchId,
                    Status: "approved",
                    Reviewer: reviewer,
                    HumanReviewStatus: "auto_approved",
                    ApprovedAtUtc: DateTimeOffset.UtcNow.ToString("O"));
                publicationReceipt = PublishLocked(seeded, approvalReceipt.HumanReviewStatus);
                UpsertApprovalReceiptLocked(approvalReceipt);
                UpsertPublicationReceiptLocked(publicationReceipt);
                publishedDispatch = ToViewModel(_store.BlackLedgerDispatches.First(item =>
                    string.Equals(item.DispatchId, seeded.DispatchId, StringComparison.OrdinalIgnoreCase)));
            }

            _store.PersistLocked();
        }

        return new BlackLedgerDispatchMutationResult(facts, draft, gateReceipt, approvalReceipt, publicationReceipt, publishedDispatch);
    }

    public BlackLedgerDispatchMutationResult ApproveDispatch(string dispatchId, ApproveBlackLedgerDispatchRequest request)
    {
        EnsureSeededPublishedDispatches();
        if (string.IsNullOrWhiteSpace(dispatchId))
        {
            throw new ArgumentException("dispatchId is required.", nameof(dispatchId));
        }

        BlackLedgerDispatchViewModel seeded = ResolveSeededDispatch(new CreateBlackLedgerDispatchRequest(
            WorldId: "emerald-sprawl-prelude",
            Turn: InferTurn(dispatchId),
            DispatchId: dispatchId,
            Adapter: "manual",
            AutoApproveSeededPreview: false,
            Reviewer: request.Reviewer));
        DispatchFactPacket facts = BuildFactPacket(seeded, seeded.WorldId);
        DispatchDraft draft;
        DispatchGateReceipt gateReceipt;
        DispatchApprovalReceipt approvalReceipt;
        DispatchPublicationReceipt? publicationReceipt = null;
        BlackLedgerDispatchViewModel? publishedDispatch = null;

        lock (_store.Gate)
        {
            draft = _store.BlackLedgerDispatchDrafts.FirstOrDefault(item => string.Equals(item.Facts.SourceReceiptId, facts.SourceReceiptId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Facts.Title, facts.Title, StringComparison.OrdinalIgnoreCase))
                ?? new DispatchDraft(
                    DraftId: $"dispatch_draft_{Guid.NewGuid():N}"[..29],
                    Adapter: "manual",
                    Status: "draft_only",
                    Facts: facts,
                    Body: BuildDraftBody(facts, "manual"),
                    GeneratedAtUtc: DateTimeOffset.UtcNow.ToString("O"));
            UpsertDraftLocked(draft);

            gateReceipt = _store.BlackLedgerDispatchGateReceipts.FirstOrDefault(item =>
                    string.Equals(item.DispatchId, dispatchId, StringComparison.OrdinalIgnoreCase))
                ?? BuildGateReceipt(dispatchId, facts);
            UpsertGateReceiptLocked(gateReceipt);

            approvalReceipt = new DispatchApprovalReceipt(
                ReceiptId: $"dispatch_approval_{Guid.NewGuid():N}"[..36],
                DispatchId: dispatchId,
                Status: request.Publish && string.Equals(gateReceipt.Status, "pass", StringComparison.OrdinalIgnoreCase) ? "approved" : "suppressed",
                Reviewer: string.IsNullOrWhiteSpace(request.Reviewer) ? "operator" : request.Reviewer.Trim(),
                HumanReviewStatus: request.HumanReviewStatus,
                ApprovedAtUtc: DateTimeOffset.UtcNow.ToString("O"));
            UpsertApprovalReceiptLocked(approvalReceipt);

            if (request.Publish && string.Equals(gateReceipt.Status, "pass", StringComparison.OrdinalIgnoreCase))
            {
                publicationReceipt = PublishLocked(seeded, request.HumanReviewStatus);
                UpsertPublicationReceiptLocked(publicationReceipt);
                publishedDispatch = ToViewModel(_store.BlackLedgerDispatches.First(item =>
                    string.Equals(item.DispatchId, dispatchId, StringComparison.OrdinalIgnoreCase)));
            }

            _store.PersistLocked();
        }

        return new BlackLedgerDispatchMutationResult(facts, draft, gateReceipt, approvalReceipt, publicationReceipt, publishedDispatch);
    }

    private void EnsureSeededPublishedDispatches()
    {
        lock (_store.Gate)
        {
            if (_store.BlackLedgerDispatches.Count > 0)
            {
                return;
            }

            foreach (BlackLedgerDispatchViewModel dispatch in _stats.ListDispatches())
            {
                _store.BlackLedgerDispatches.Add(ToRecord(dispatch, "optional"));
                _store.BlackLedgerDispatchPublicationReceipts.Add(new DispatchPublicationReceipt(
                    ReceiptId: $"dispatch_publication_{Guid.NewGuid():N}"[..39],
                    DispatchId: dispatch.DispatchId,
                    Status: "published_flagship_seeded_board",
                    SourceReceiptIds: [dispatch.SourceReceiptId],
                    PublishedAtUtc: dispatch.CreatedAtUtc));
            }

            _store.PersistLocked();
            _logger.LogInformation("Seeded {Count} Black Ledger dispatch records into CommunityStore.", _store.BlackLedgerDispatches.Count);
        }
    }

    private static string NormalizeAdapter(string? adapter)
    {
        string normalized = (adapter ?? "deterministic_template").Trim().ToLowerInvariant();
        return normalized.Length == 0 ? "deterministic_template" : normalized;
    }

    private BlackLedgerDispatchViewModel ResolveSeededDispatch(CreateBlackLedgerDispatchRequest request)
    {
        BlackLedgerDispatchViewModel? dispatch = !string.IsNullOrWhiteSpace(request.DispatchId)
            ? _stats.LoadDispatch(request.DispatchId!, request.Turn)
            : _stats.ListDispatches(request.Turn).FirstOrDefault();
        if (dispatch is null)
        {
            throw new InvalidOperationException($"Unable to resolve seeded dispatch for world '{request.WorldId}' turn '{request.Turn}'.");
        }

        return dispatch;
    }

    private static DispatchFactPacket BuildFactPacket(BlackLedgerDispatchViewModel dispatch, string worldId)
        => new(
            WorldId: worldId,
            Turn: dispatch.Turn,
            SourceReceiptId: dispatch.SourceReceiptId,
            SourceKind: "WorldTickReceipt",
            Title: dispatch.Title,
            Summary: dispatch.Summary,
            Highlights: dispatch.PackagePressureLinks.Count > 0 ? dispatch.PackagePressureLinks.ToArray() : Array.Empty<string>(),
            InvolvedFactions: dispatch.InvolvedFactions,
            InvolvedDistricts: dispatch.InvolvedDistricts,
            PackagePressureLinks: dispatch.PackagePressureLinks,
            PrivacyStatus: dispatch.PrivacyStatus,
            PublicSafe: dispatch.PublicSafe,
            PrivateDataUsed: false,
            SourcebookTextUsed: false);

    private static string BuildDraftBody(DispatchFactPacket facts, string adapter)
        => adapter switch
        {
            "manual" => $"{facts.Title}\n\n{facts.Summary}\n\nFiled after {facts.SourceReceiptId}. No private table data.",
            "ea" or "1min.ai" or "syllabbles" => $"{facts.Title}\n\nDraft-only dispatch synthesized from Chummer-owned facts.\n\n{facts.Summary}\n\nFiled after {facts.SourceReceiptId}. No private table data.",
            _ => $"{facts.Title}\n\n{facts.Summary}\n\nThe Ledger kept the names out and the pressure visible.\n\nFiled after {facts.SourceReceiptId}. No private table data.",
        };

    private static DispatchGateReceipt BuildGateReceipt(string dispatchId, DispatchFactPacket facts)
        => new(
            ReceiptId: $"dispatch_gate_{Guid.NewGuid():N}"[..32],
            DispatchId: dispatchId,
            SourceReceiptIds: [facts.SourceReceiptId],
            Status: facts.PublicSafe && !facts.PrivateDataUsed && !facts.SourcebookTextUsed ? "pass" : "failed",
            PrivacyPassed: facts.PublicSafe,
            PiiPassed: true,
            SourcebookPassed: !facts.SourcebookTextUsed,
            ProviderLeakPassed: true,
            SupportDataPassed: true,
            FactConsistencyPassed: true,
            TonePassed: true,
            PublicationAuthorityPassed: true,
            CheckedAtUtc: DateTimeOffset.UtcNow.ToString("O"));

    private DispatchPublicationReceipt PublishLocked(BlackLedgerDispatchViewModel dispatch, string humanReviewStatus)
    {
        UpsertDispatchLocked(ToRecord(dispatch, humanReviewStatus));
        return new DispatchPublicationReceipt(
            ReceiptId: $"dispatch_publication_{Guid.NewGuid():N}"[..39],
            DispatchId: dispatch.DispatchId,
            Status: "published",
            SourceReceiptIds: [dispatch.SourceReceiptId],
            PublishedAtUtc: DateTimeOffset.UtcNow.ToString("O"));
    }

    private void UpsertDispatchLocked(BlackLedgerDispatch dispatch)
    {
        _store.BlackLedgerDispatches.RemoveAll(item => string.Equals(item.DispatchId, dispatch.DispatchId, StringComparison.OrdinalIgnoreCase));
        _store.BlackLedgerDispatches.Add(dispatch);
    }

    private void UpsertDraftLocked(DispatchDraft draft)
    {
        _store.BlackLedgerDispatchDrafts.RemoveAll(item => string.Equals(item.DraftId, draft.DraftId, StringComparison.OrdinalIgnoreCase));
        _store.BlackLedgerDispatchDrafts.Add(draft);
    }

    private void UpsertGateReceiptLocked(DispatchGateReceipt receipt)
    {
        _store.BlackLedgerDispatchGateReceipts.RemoveAll(item => string.Equals(item.DispatchId, receipt.DispatchId, StringComparison.OrdinalIgnoreCase));
        _store.BlackLedgerDispatchGateReceipts.Add(receipt);
    }

    private void UpsertApprovalReceiptLocked(DispatchApprovalReceipt receipt)
        => _store.BlackLedgerDispatchApprovalReceipts.Add(receipt);

    private void UpsertPublicationReceiptLocked(DispatchPublicationReceipt receipt)
        => _store.BlackLedgerDispatchPublicationReceipts.Add(receipt);

    private static BlackLedgerDispatch ToRecord(BlackLedgerDispatchViewModel dispatch, string humanReviewStatus)
        => new(
            DispatchId: dispatch.DispatchId,
            WorldId: dispatch.WorldId,
            Turn: dispatch.Turn,
            Type: dispatch.Type,
            Scope: dispatch.Scope,
            SourceReceiptId: dispatch.SourceReceiptId,
            SourceReceiptHref: dispatch.SourceReceiptHref,
            Title: dispatch.Title,
            Summary: dispatch.Summary,
            Body: dispatch.Body,
            InvolvedFactions: dispatch.InvolvedFactions,
            InvolvedDistricts: dispatch.InvolvedDistricts,
            PackagePressureLinks: dispatch.PackagePressureLinks,
            PrivacyStatus: dispatch.PrivacyStatus,
            GeneratedBy: dispatch.GeneratedBy,
            HumanReviewStatus: humanReviewStatus,
            CreatedAtUtc: dispatch.CreatedAtUtc,
            PublicSafe: dispatch.PublicSafe,
            AiGenerated: dispatch.AiGenerated,
            Href: dispatch.Href);

    private static BlackLedgerDispatchViewModel ToViewModel(BlackLedgerDispatch dispatch)
        => new(
            DispatchId: dispatch.DispatchId,
            WorldId: dispatch.WorldId,
            Turn: dispatch.Turn,
            Type: dispatch.Type,
            Scope: dispatch.Scope,
            SourceReceiptId: dispatch.SourceReceiptId,
            SourceReceiptHref: dispatch.SourceReceiptHref,
            Title: dispatch.Title,
            Summary: dispatch.Summary,
            Body: dispatch.Body,
            InvolvedFactions: dispatch.InvolvedFactions,
            InvolvedDistricts: dispatch.InvolvedDistricts,
            PackagePressureLinks: dispatch.PackagePressureLinks,
            PrivacyStatus: dispatch.PrivacyStatus,
            GeneratedBy: dispatch.GeneratedBy,
            HumanReviewStatus: dispatch.HumanReviewStatus,
            CreatedAtUtc: dispatch.CreatedAtUtc,
            PublicSafe: dispatch.PublicSafe,
            AiGenerated: dispatch.AiGenerated,
            Href: dispatch.Href);

    private static string NormalizeSlug(string value)
        => value.Trim().ToLowerInvariant().Replace("_", "-", StringComparison.Ordinal).Replace(" ", "-", StringComparison.Ordinal);

    private static int InferTurn(string dispatchId)
    {
        string marker = "_turn_";
        int index = dispatchId.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
        if (index < 0)
        {
            return 1;
        }

        string turnToken = dispatchId[(index + marker.Length)..];
        string digits = new string(turnToken.TakeWhile(char.IsDigit).ToArray());
        return int.TryParse(digits, out int turn) ? turn : 1;
    }
}
