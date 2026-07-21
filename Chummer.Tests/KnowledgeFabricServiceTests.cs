using System.Text.Json;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class KnowledgeFabricServiceTests
{
    [Fact]
    public void Knowledge_fabric_receipts_emit_shared_public_safe_envelopes()
    {
        KnowledgeFabricService service = new();

        IReadOnlyList<KnowledgeFabricReceipt> receipts = service.ListReceipts();

        Assert.NotEmpty(receipts);
        Assert.All(receipts, receipt =>
        {
            Assert.NotNull(receipt.Envelope);
            Assert.Equal("knowledge_fabric", receipt.Envelope!.ReceiptKind);
            Assert.Equal("rules.knowledge_fabric", receipt.Envelope.OwnerScope);
            Assert.Equal(ReceiptExposureClasses.PublicSafe, receipt.Envelope.ExposureClass);
            Assert.Equal(ReceiptLifecycleStates.Published, receipt.Envelope.LifecycleState);
            Assert.Equal("authority_unverified", receipt.Envelope.ReviewState);
            Assert.Equal("awaiting_core_authority", receipt.Status);
            Assert.Equal(receipt.ReceiptId, receipt.Envelope.EvidenceRef);
        });
    }

    [Fact]
    public void Receipt_json_is_a_deterministic_cited_source_pack_query()
    {
        KnowledgeFabricService service = new();

        string first = service.BuildReceiptJson("kf_explain_initiative_sr5");
        string second = service.BuildReceiptJson("kf_explain_initiative_sr5");

        Assert.Equal(first, second);
        using JsonDocument document = JsonDocument.Parse(first);
        JsonElement root = document.RootElement;
        Assert.False(root.TryGetProperty("answer", out _));

        JsonElement query = root.GetProperty("query");
        Assert.Equal(KnowledgeFabricService.QueryContractName, query.GetProperty("contract").GetString());
        Assert.Equal(KnowledgeFabricService.DerivedAuthorityPosture, query.GetProperty("authorityPosture").GetString());
        Assert.False(query.GetProperty("authorityVerified").GetBoolean());
        Assert.Equal("not_performed_by_hub", query.GetProperty("authorityVerification").GetString());
        Assert.Equal("source_pack_shape_validated_authority_unverified", query.GetProperty("resolutionStatus").GetString());
        Assert.Contains("does not authenticate Core ownership", query.GetProperty("resolutionPolicy").GetString(), StringComparison.Ordinal);
        Assert.Matches("^[0-9a-f]{64}$", query.GetProperty("querySha256").GetString()!);

        JsonElement sourcePack = query.GetProperty("sourcePack");
        Assert.Equal(KnowledgeFabricService.CoreSourcePackOwnerScope, sourcePack.GetProperty("ownerScope").GetString());
        Assert.Matches("^[0-9a-f]{64}$", sourcePack.GetProperty("manifestSha256").GetString()!);

        JsonElement[] citations = query.GetProperty("citations").EnumerateArray().ToArray();
        Assert.NotEmpty(citations);
        Assert.All(citations, citation =>
        {
            Assert.Equal(sourcePack.GetProperty("sourcePackId").GetString(), citation.GetProperty("sourcePackId").GetString());
            Assert.False(string.IsNullOrWhiteSpace(citation.GetProperty("sourceRef").GetString()));
            Assert.False(string.IsNullOrWhiteSpace(citation.GetProperty("anchor").GetString()));
            Assert.False(string.IsNullOrWhiteSpace(citation.GetProperty("evidenceRef").GetString()));
        });
    }

    [Fact]
    public void Query_refuses_to_answer_without_a_source_pack()
    {
        KnowledgeFabricService service = new();
        var query = new KnowledgeFabricSourcePackQuery(
            QueryId: "query-without-pack",
            Question: "What is grounded here?",
            SourcePack: null,
            Citations: []);

        InvalidDataException exception = Assert.Throws<InvalidDataException>(() => service.Query(query));

        Assert.Contains("without a core-owned source pack", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Query_refuses_to_answer_when_the_source_pack_has_no_citations()
    {
        KnowledgeFabricService service = new();
        var sourcePack = new KnowledgeFabricSourcePackReference(
            SourcePackId: "core.rules.test.no-citations",
            OwnerScope: KnowledgeFabricService.CoreSourcePackOwnerScope,
            Version: "1",
            ManifestSha256: new string('0', 64),
            EvidenceRef: "core-source-pack:test-no-citations");

        InvalidDataException exception = Assert.Throws<InvalidDataException>(() => service.Query(new KnowledgeFabricSourcePackQuery(
            QueryId: "query-without-citations",
            Question: "What is grounded here?",
            SourcePack: sourcePack,
            Citations: [])));

        Assert.Contains("contains no citations", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Query_refuses_a_citation_bound_to_a_different_source_pack()
    {
        KnowledgeFabricService service = new();
        var sourcePack = new KnowledgeFabricSourcePackReference(
            SourcePackId: "core.rules.test.citation-binding",
            OwnerScope: KnowledgeFabricService.CoreSourcePackOwnerScope,
            Version: "1",
            ManifestSha256: new string('0', 64),
            EvidenceRef: "core-source-pack:test-citation-binding");

        InvalidDataException exception = Assert.Throws<InvalidDataException>(() => service.Query(new KnowledgeFabricSourcePackQuery(
            QueryId: "query-citation-binding",
            Question: "What is grounded here?",
            SourcePack: sourcePack,
            Citations:
            [
                new KnowledgeFabricCitation(
                    CitationId: "citation-from-another-pack",
                    SourcePackId: "core.rules.some-other-pack",
                    SourceRef: "core-explain:test",
                    Anchor: "test-anchor",
                    EvidenceRef: "runtime-receipt:test")
            ])));

        Assert.Contains("is not bound to source pack", exception.Message, StringComparison.Ordinal);
    }
}
