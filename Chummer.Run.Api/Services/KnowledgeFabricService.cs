using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Contracts.Receipts;

namespace Chummer.Run.Api.Services;

public sealed class KnowledgeFabricService
{
    public const string QueryContractName = "chummer.knowledge-fabric.source-pack-query/v1";
    public const string CoreSourcePackOwnerScope = "chummer6-core.rules";
    public const string DerivedAuthorityPosture = "source_pack_claim_unverified_no_answer";

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private static readonly IReadOnlyList<KnowledgeFabricReceipt> Receipts =
    [
        CreateReceipt(
            receiptId: "kf_explain_initiative_sr5",
            topic: "SR5 initiative explain",
            summary: "Shows the bounded modifier trail for initiative posture without copying official sourcebook text.",
            provenance: "Chummer rules runtime + public-safe explain summary",
            route: "/rules/explanations/kf_explain_initiative_sr5.json",
            question: "Why is this initiative posture ready for tonight?",
            sourcePackId: "core.rules.sr5.initiative.explain.v1",
            sourceRef: "core-explain:sr5-initiative"),
        CreateReceipt(
            receiptId: "kf_provenance_armor_stack",
            topic: "Armor stack provenance",
            summary: "Names where the answer came from and where the public-safe boundary stops.",
            provenance: "Capability receipt + provenance label",
            route: "/rules/explanations/kf_provenance_armor_stack.json",
            question: "Why does this armor posture need review?",
            sourcePackId: "core.rules.armor-stack.explain.v1",
            sourceRef: "core-explain:armor-stack"),
        CreateReceipt(
            receiptId: "kf_house_rule_boundary",
            topic: "House-rule boundary",
            summary: "Shows how Chummer distinguishes canon-facing runtime truth from a table-local amendment package.",
            provenance: "Package posture + explain receipt",
            route: "/rules/explanations/kf_house_rule_boundary.json",
            question: "What is the boundary here?",
            sourcePackId: "core.rules.rule-environment-boundary.explain.v1",
            sourceRef: "core-explain:rule-environment")
    ];

    public IReadOnlyList<KnowledgeFabricReceipt> ListReceipts()
    {
        foreach (KnowledgeFabricReceipt receipt in Receipts)
        {
            _ = ResolveQuery(receipt);
        }

        return Receipts;
    }

    public KnowledgeFabricReceipt GetReceipt(string receiptId)
        => Receipts.FirstOrDefault(item => string.Equals(item.ReceiptId, receiptId?.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown Knowledge Fabric receipt '{receiptId}'.");

    public KnowledgeFabricQueryContract Query(KnowledgeFabricSourcePackQuery query)
    {
        ArgumentNullException.ThrowIfNull(query);

        string queryId = RequireCanonicalValue(query.QueryId, "query id");
        string question = RequireCanonicalValue(query.Question, "query question");
        KnowledgeFabricSourcePackReference sourcePack = query.SourcePack
            ?? throw new InvalidDataException("Knowledge Fabric refuses to answer without a core-owned source pack.");
        IReadOnlyList<KnowledgeFabricCitation> citations = query.Citations
            ?? throw new InvalidDataException("Knowledge Fabric refuses to answer without citations from the source pack.");

        ValidateSourcePack(sourcePack, citations);

        KnowledgeFabricCitation[] canonicalCitations = citations
            .OrderBy(item => item.CitationId, StringComparer.Ordinal)
            .ToArray();
        string querySha256 = ComputeQuerySha256(queryId, question, sourcePack, canonicalCitations);
        return new KnowledgeFabricQueryContract(
            Contract: QueryContractName,
            QueryId: queryId,
            Question: question,
            SourcePack: sourcePack,
            Citations: canonicalCitations,
            QuerySha256: querySha256,
            ResolutionStatus: "source_pack_shape_validated_authority_unverified",
            AuthorityPosture: DerivedAuthorityPosture,
            AuthorityVerified: false,
            AuthorityVerification: "not_performed_by_hub",
            ResolutionPolicy: "This contract validates shape and digest consistency only. Hub does not authenticate Core ownership and must not compute, complete, or invent mechanics or emit an answer until an external Core authority handoff is verified.");
    }

    public string BuildReceiptJson(string receiptId)
    {
        KnowledgeFabricReceipt receipt = GetReceipt(receiptId);
        KnowledgeFabricQueryContract query = ResolveQuery(receipt);
        var payload = new
        {
            receipt.ReceiptId,
            receipt.Topic,
            receipt.Summary,
            receipt.Provenance,
            receipt.Status,
            Query = query,
            proof_kind = "source_safe_explain_receipt"
        };

        return JsonSerializer.Serialize(payload, JsonOptions);
    }

    public string BuildIndexJson()
        => JsonSerializer.Serialize(
            new
            {
                receipts = Receipts.Select(item =>
                {
                    KnowledgeFabricQueryContract query = ResolveQuery(item);
                    return new
                    {
                        item.ReceiptId,
                        item.Topic,
                        item.Summary,
                        item.Provenance,
                        item.Route,
                        item.Status,
                        query.Contract,
                        query.SourcePack.SourcePackId,
                        query.SourcePack.ManifestSha256,
                        citation_count = query.Citations.Count
                    };
                }).ToArray(),
                boundary = "Public route stays source-safe and provenance-first. Official sourcebook text and private campaign data remain out of this lane. Hub refuses uncited or source-pack-free answers."
            },
            JsonOptions);

    public static string ComputeSourcePackManifestSha256(
        KnowledgeFabricSourcePackReference sourcePack,
        IReadOnlyList<KnowledgeFabricCitation> citations)
    {
        ArgumentNullException.ThrowIfNull(sourcePack);
        ArgumentNullException.ThrowIfNull(citations);

        string canonicalJson = JsonSerializer.Serialize(new
        {
            sourcePack.SourcePackId,
            sourcePack.OwnerScope,
            sourcePack.Version,
            sourcePack.EvidenceRef,
            citations = citations
                .OrderBy(item => item.CitationId, StringComparer.Ordinal)
                .Select(item => new
                {
                    item.CitationId,
                    item.SourcePackId,
                    item.SourceRef,
                    item.Anchor,
                    item.EvidenceRef
                })
                .ToArray()
        });

        return Sha256(canonicalJson);
    }

    private KnowledgeFabricQueryContract ResolveQuery(KnowledgeFabricReceipt receipt)
        => Query(receipt.Query
            ?? throw new InvalidDataException($"Knowledge Fabric receipt '{receipt.ReceiptId}' has no source-pack query; no answer was emitted."));

    private static void ValidateSourcePack(
        KnowledgeFabricSourcePackReference sourcePack,
        IReadOnlyList<KnowledgeFabricCitation> citations)
    {
        string sourcePackId = RequireCanonicalValue(sourcePack.SourcePackId, "source pack id");
        string ownerScope = RequireCanonicalValue(sourcePack.OwnerScope, "source pack owner scope");
        _ = RequireCanonicalValue(sourcePack.Version, "source pack version");
        string manifestSha256 = RequireCanonicalValue(sourcePack.ManifestSha256, "source pack manifest SHA-256");
        _ = RequireCanonicalValue(sourcePack.EvidenceRef, "source pack evidence reference");

        if (!string.Equals(ownerScope, CoreSourcePackOwnerScope, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Knowledge Fabric source pack '{sourcePackId}' does not claim the expected owner scope '{CoreSourcePackOwnerScope}'.");
        }

        if (citations.Count == 0)
        {
            throw new InvalidDataException($"Knowledge Fabric source pack '{sourcePackId}' contains no citations; no answer was emitted.");
        }

        if (manifestSha256.Length != 64 || manifestSha256.Any(character => !Uri.IsHexDigit(character)))
        {
            throw new InvalidDataException($"Knowledge Fabric source pack '{sourcePackId}' has an invalid manifest SHA-256 digest.");
        }

        if (citations.GroupBy(item => item.CitationId, StringComparer.Ordinal).Any(group => group.Count() > 1))
        {
            throw new InvalidDataException($"Knowledge Fabric source pack '{sourcePackId}' contains duplicate citation ids.");
        }

        foreach (KnowledgeFabricCitation citation in citations)
        {
            _ = RequireCanonicalValue(citation.CitationId, "citation id");
            _ = RequireCanonicalValue(citation.SourceRef, "citation source reference");
            _ = RequireCanonicalValue(citation.Anchor, "citation anchor");
            _ = RequireCanonicalValue(citation.EvidenceRef, "citation evidence reference");

            if (!string.Equals(citation.SourcePackId, sourcePackId, StringComparison.Ordinal))
            {
                throw new InvalidDataException($"Knowledge Fabric citation '{citation.CitationId}' is not bound to source pack '{sourcePackId}'.");
            }
        }

        string expectedSha256 = ComputeSourcePackManifestSha256(sourcePack, citations);
        if (!string.Equals(manifestSha256, expectedSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"Knowledge Fabric source pack '{sourcePackId}' failed its manifest SHA-256 integrity check.");
        }
    }

    private static string ComputeQuerySha256(
        string queryId,
        string question,
        KnowledgeFabricSourcePackReference sourcePack,
        IReadOnlyList<KnowledgeFabricCitation> citations)
        => Sha256(JsonSerializer.Serialize(new
        {
            contract = QueryContractName,
            queryId,
            question,
            sourcePack,
            citations,
            authorityPosture = DerivedAuthorityPosture
        }));

    private static string Sha256(string value)
        => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private static string RequireCanonicalValue(string? value, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidDataException($"Knowledge Fabric {fieldName} is required.");
        }

        string normalized = value.Trim();
        if (!string.Equals(value, normalized, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Knowledge Fabric {fieldName} must not contain leading or trailing whitespace.");
        }

        return normalized;
    }

    private static KnowledgeFabricReceipt CreateReceipt(
        string receiptId,
        string topic,
        string summary,
        string provenance,
        string route,
        string question,
        string sourcePackId,
        string sourceRef)
        => new(
            ReceiptId: receiptId,
            Topic: topic,
            Summary: summary,
            Provenance: provenance,
            Route: route,
            Status: "awaiting_core_authority",
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "knowledge_fabric",
                ownerScope: "rules.knowledge_fabric",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                lifecycleState: ReceiptLifecycleStates.Published,
                evidenceRef: receiptId,
                reviewState: "authority_unverified"),
            Query: CreateSourcePackQuery(receiptId, question, sourcePackId, sourceRef));

    private static KnowledgeFabricSourcePackQuery CreateSourcePackQuery(
        string receiptId,
        string question,
        string sourcePackId,
        string sourceRef)
    {
        KnowledgeFabricCitation[] citations =
        [
            new(
                CitationId: $"{receiptId}.source",
                SourcePackId: sourcePackId,
                SourceRef: sourceRef,
                Anchor: "public-safe-explain-projection",
                EvidenceRef: $"runtime-receipt:{receiptId}")
        ];
        var sourcePack = new KnowledgeFabricSourcePackReference(
            SourcePackId: sourcePackId,
            OwnerScope: CoreSourcePackOwnerScope,
            Version: "1",
            ManifestSha256: string.Empty,
            EvidenceRef: $"core-source-pack:{sourcePackId}");
        sourcePack = sourcePack with
        {
            ManifestSha256 = ComputeSourcePackManifestSha256(sourcePack, citations)
        };

        return new KnowledgeFabricSourcePackQuery(receiptId, question, sourcePack, citations);
    }
}

public sealed record KnowledgeFabricReceipt(
    string ReceiptId,
    string Topic,
    string Summary,
    string Provenance,
    string Route,
    string Status,
    ReceiptEnvelope? Envelope = null,
    KnowledgeFabricSourcePackQuery? Query = null);

public sealed record KnowledgeFabricSourcePackQuery(
    string QueryId,
    string Question,
    KnowledgeFabricSourcePackReference? SourcePack,
    IReadOnlyList<KnowledgeFabricCitation>? Citations);

public sealed record KnowledgeFabricSourcePackReference(
    string SourcePackId,
    string OwnerScope,
    string Version,
    string ManifestSha256,
    string EvidenceRef);

public sealed record KnowledgeFabricCitation(
    string CitationId,
    string SourcePackId,
    string SourceRef,
    string Anchor,
    string EvidenceRef);

public sealed record KnowledgeFabricQueryContract(
    string Contract,
    string QueryId,
    string Question,
    KnowledgeFabricSourcePackReference SourcePack,
    IReadOnlyList<KnowledgeFabricCitation> Citations,
    string QuerySha256,
    string ResolutionStatus,
    string AuthorityPosture,
    bool AuthorityVerified,
    string AuthorityVerification,
    string ResolutionPolicy);
