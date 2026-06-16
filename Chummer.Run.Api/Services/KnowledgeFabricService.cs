using System.Text.Json;
using Chummer.Contracts.Receipts;

namespace Chummer.Run.Api.Services;

public sealed class KnowledgeFabricService
{
    private static readonly IReadOnlyList<KnowledgeFabricReceipt> Receipts =
    [
        new(
            ReceiptId: "kf_explain_initiative_sr5",
            Topic: "SR5 initiative explain",
            Summary: "Shows the bounded modifier trail for initiative posture without copying official sourcebook text.",
            Provenance: "Chummer rules runtime + public-safe explain summary",
            Route: "/rules/receipts/kf_explain_initiative_sr5.json",
            Status: "live",
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "knowledge_fabric",
                ownerScope: "rules.knowledge_fabric",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                lifecycleState: ReceiptLifecycleStates.Published,
                evidenceRef: "kf_explain_initiative_sr5",
                reviewState: "live")),
        new(
            ReceiptId: "kf_provenance_armor_stack",
            Topic: "Armor stack provenance",
            Summary: "Names where the answer came from and where the public-safe boundary stops.",
            Provenance: "Capability receipt + provenance label",
            Route: "/rules/receipts/kf_provenance_armor_stack.json",
            Status: "live",
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "knowledge_fabric",
                ownerScope: "rules.knowledge_fabric",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                lifecycleState: ReceiptLifecycleStates.Published,
                evidenceRef: "kf_provenance_armor_stack",
                reviewState: "live")),
        new(
            ReceiptId: "kf_house_rule_boundary",
            Topic: "House-rule boundary",
            Summary: "Shows how Chummer distinguishes canon-facing runtime truth from a table-local amendment package.",
            Provenance: "Package posture + explain receipt",
            Route: "/rules/receipts/kf_house_rule_boundary.json",
            Status: "live",
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "knowledge_fabric",
                ownerScope: "rules.knowledge_fabric",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                lifecycleState: ReceiptLifecycleStates.Published,
                evidenceRef: "kf_house_rule_boundary",
                reviewState: "live"))
    ];

    public IReadOnlyList<KnowledgeFabricReceipt> ListReceipts() => Receipts;

    public KnowledgeFabricReceipt GetReceipt(string receiptId)
        => Receipts.FirstOrDefault(item => string.Equals(item.ReceiptId, receiptId?.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown Knowledge Fabric receipt '{receiptId}'.");

    public string BuildReceiptJson(string receiptId)
    {
        KnowledgeFabricReceipt receipt = GetReceipt(receiptId);
        var payload = new
        {
            receipt.ReceiptId,
            receipt.Topic,
            receipt.Summary,
            receipt.Provenance,
            receipt.Status,
            Answer = BuildSampleAnswer(receipt.ReceiptId),
            proof_kind = "source_safe_explain_receipt",
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildIndexJson()
        => JsonSerializer.Serialize(
            new
            {
                receipts = Receipts.Select(item => new
                {
                    item.ReceiptId,
                    item.Topic,
                    item.Summary,
                    item.Provenance,
                    item.Route,
                    item.Status
                }).ToArray(),
                boundary = "Public route stays source-safe and provenance-first. Official sourcebook text and private campaign data remain out of this lane.",
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });

    private static object BuildSampleAnswer(string receiptId)
        => receiptId switch
        {
            "kf_explain_initiative_sr5" => new
            {
                question = "Why is this initiative posture ready for tonight?",
                bounded_summary = "Reaction, intuition, and temporary prep state all contribute. The public-safe answer names the factor families, not book text.",
                factor_families = new[] { "reaction", "intuition", "temporary_status" }
            },
            "kf_provenance_armor_stack" => new
            {
                question = "Why does this armor posture need review?",
                bounded_summary = "The answer comes from current runtime capability plus the package boundary. The route does not pretend a private table override is public canon.",
                factor_families = new[] { "armor_stack", "package_boundary", "compatibility_review" }
            },
            _ => new
            {
                question = "What is the boundary here?",
                bounded_summary = "Canon-facing runtime truth and table-local amendment posture stay distinct.",
                factor_families = new[] { "runtime_truth", "table_local_package", "provenance" }
            }
        };
}

public sealed record KnowledgeFabricReceipt(
    string ReceiptId,
    string Topic,
    string Summary,
    string Provenance,
    string Route,
    string Status,
    ReceiptEnvelope? Envelope = null);
