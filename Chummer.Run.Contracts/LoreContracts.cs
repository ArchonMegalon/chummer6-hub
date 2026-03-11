namespace Chummer.Run.Contracts.AI;

public sealed record LoreChunk(
    string ChunkId,
    string Source,
    string Jurisdiction,
    string District,
    string TopicTags,
    string CampaignScope,
    string PackProfileLinkage,
    string Content,
    string? Region = null,
    string ApprovalState = "approved");

public sealed record LoreIngestionRequest(
    string ChunkId,
    string Source,
    string Jurisdiction,
    string District,
    string TopicTags,
    string CampaignScope,
    string PackProfileLinkage,
    string Content,
    string? Region = null,
    string ApprovalState = "approved");

public sealed record LoreSearchRequest(
    string? District = null,
    string? TopicTag = null,
    string? CampaignScope = null,
    int MaxItems = 5);

public sealed record LoreSearchResult(
    string Query,
    IReadOnlyList<LoreChunk> Chunks,
    DateTimeOffset GeneratedAtUtc);

public sealed record LoreLensQuery(
    string QueryText,
    string? Jurisdiction = null,
    string? District = null,
    string? Region = null,
    string? TopicTag = null,
    string? CampaignScope = null,
    string? PackProfileId = null,
    int TopK = 4,
    double MinimumScore = 0.08,
    bool ApprovedOnly = true);

public sealed record LoreVectorization(
    string Profile,
    int TokenCount,
    IReadOnlyList<string> Keywords,
    DateTimeOffset VectorizedAtUtc);

public sealed record LoreChunkMatch(
    LoreChunk Chunk,
    double Score,
    IReadOnlyList<string> MatchedTerms,
    string Snippet,
    LoreVectorization Vectorization,
    IReadOnlyList<Chummer.Run.Contracts.Spider.EvidencePointer> Evidence);

public sealed record LoreLensResult(
    string QueryText,
    int Retrieved,
    string RuntimeFingerprint,
    string VectorProfile,
    IReadOnlyList<string> AppliedFilters,
    IReadOnlyList<string> PackProfileIds,
    IReadOnlyList<string> SourcePointers,
    IReadOnlyList<LoreChunkMatch> Matches,
    DateTimeOffset GeneratedAtUtc);
