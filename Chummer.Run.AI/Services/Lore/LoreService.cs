
using EvidencePointer = Chummer.Play.Contracts.Spider.EvidencePointer;
using LoreChunk = Chummer.Run.Contracts.AI.LoreChunk;
using LoreChunkMatch = Chummer.Run.Contracts.AI.LoreChunkMatch;
using LoreIngestionRequest = Chummer.Run.Contracts.AI.LoreIngestionRequest;
using LoreLensQuery = Chummer.Run.Contracts.AI.LoreLensQuery;
using LoreLensResult = Chummer.Run.Contracts.AI.LoreLensResult;
using LoreSearchRequest = Chummer.Run.Contracts.AI.LoreSearchRequest;
using LoreSearchResult = Chummer.Run.Contracts.AI.LoreSearchResult;
using LoreVectorization = Chummer.Run.Contracts.AI.LoreVectorization;

namespace Chummer.Run.AI.Services.Lore;

public interface ILoreService
{
    void Ingest(LoreIngestionRequest request);
    LoreSearchResult Search(LoreSearchRequest request);
    LoreLensResult QueryLoreLens(LoreLensQuery request);
}

public interface IPersonaMemoryService
{
    PersonaMemoryResult Search(string sessionId, PersonaMemoryQuery query);
    void Upsert(string sessionId, PersonaMemoryCard card);
}

public sealed class LoreService : ILoreService, IPersonaMemoryService
{
    private const string VectorProfileName = "bag-of-words-v1";

    private sealed record LoreVectorState(
        IReadOnlyDictionary<string, double> Weights,
        double Magnitude,
        IReadOnlyList<string> Keywords,
        int TokenCount,
        DateTimeOffset VectorizedAtUtc);

    private sealed record LoreChunkState(
        LoreChunk Chunk,
        LoreVectorState Vector,
        DateTimeOffset IngestedAtUtc);

    private readonly Dictionary<string, LoreChunkState> _loreByChunkId = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, Dictionary<string, PersonaMemoryCard>> _sessionPersonaIndex = new();
    private readonly object _guard = new();

    public void Ingest(LoreIngestionRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.ChunkId) || string.IsNullOrWhiteSpace(request.Content))
        {
            return;
        }

        var lore = new LoreChunk(
            request.ChunkId.Trim(),
            request.Source.Trim(),
            request.Jurisdiction.Trim(),
            request.District.Trim(),
            request.TopicTags.Trim(),
            request.CampaignScope.Trim(),
            request.PackProfileLinkage.Trim(),
            request.Content.Trim(),
            request.Region?.Trim(),
            NormalizeApprovalState(request.ApprovalState));
        var vector = BuildVector(lore);

        lock (_guard)
        {
            _loreByChunkId[lore.ChunkId] = new LoreChunkState(
                Chunk: lore,
                Vector: vector,
                IngestedAtUtc: DateTimeOffset.UtcNow);
        }
    }

    public LoreSearchResult Search(LoreSearchRequest request)
    {
        lock (_guard)
        {
            var requestedDistrict = request.District?.Trim();
            var requestedTopic = request.TopicTag?.Trim();
            var requestedCampaign = request.CampaignScope?.Trim();
            var maxItems = Math.Max(1, request.MaxItems);
            var hasFilters = !string.IsNullOrWhiteSpace(requestedDistrict)
                || !string.IsNullOrWhiteSpace(requestedTopic)
                || !string.IsNullOrWhiteSpace(requestedCampaign);

            var chunks = _loreByChunkId.Values
                .Select(state => new
                {
                    state.Chunk,
                    state.IngestedAtUtc,
                    Score = ScoreLoreChunk(state.Chunk, requestedDistrict, requestedTopic, requestedCampaign)
                })
                .Where(candidate => IsApproved(candidate.Chunk.ApprovalState))
                .Where(candidate => !hasFilters || candidate.Score > 0)
                .OrderByDescending(candidate => candidate.Score)
                .ThenByDescending(candidate => candidate.IngestedAtUtc)
                .Take(maxItems)
                .Select(candidate => candidate.Chunk)
                .ToList();

            return new LoreSearchResult(
                Query: string.Join(" | ", new[] { requestedDistrict, requestedTopic, requestedCampaign }.Where(static item => !string.IsNullOrWhiteSpace(item))),
                Chunks: chunks,
                GeneratedAtUtc: DateTimeOffset.UtcNow);
        }
    }

    public LoreLensResult QueryLoreLens(LoreLensQuery request)
    {
        var queryText = request.QueryText?.Trim() ?? string.Empty;
        var normalizedTopK = Math.Max(1, request.TopK);
        var queryTokens = Tokenize(queryText);
        var queryVector = BuildWeightedVector(queryTokens);
        var appliedFilters = BuildAppliedFilters(request);

        lock (_guard)
        {
            var matches = _loreByChunkId.Values
                .Where(state => MatchesLoreLensFilters(state.Chunk, request))
                .Select(state => BuildLoreLensCandidate(state, request, queryText, queryTokens, queryVector))
                .Where(candidate => candidate is not null)
                .Select(static candidate => candidate!)
                .OrderByDescending(candidate => candidate.Score)
                .ThenByDescending(candidate => candidate.State.IngestedAtUtc)
                .Take(normalizedTopK)
                .Select(candidate => new LoreChunkMatch(
                    Chunk: candidate.State.Chunk,
                    Score: candidate.Score,
                    MatchedTerms: candidate.MatchedTerms,
                    Snippet: candidate.Snippet,
                    Vectorization: new LoreVectorization(
                        Profile: VectorProfileName,
                        TokenCount: candidate.State.Vector.TokenCount,
                        Keywords: candidate.State.Vector.Keywords,
                        VectorizedAtUtc: candidate.State.Vector.VectorizedAtUtc),
                    Evidence: BuildLoreEvidence(candidate.State.Chunk, candidate.Score, candidate.MatchedTerms)))
                .ToList();

            var packProfiles = matches
                .Select(match => match.Chunk.PackProfileLinkage)
                .Where(static linkage => !string.IsNullOrWhiteSpace(linkage))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(static linkage => linkage, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            var sourcePointers = matches
                .Select(match => $"{match.Chunk.Source}#{match.Chunk.ChunkId}")
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(static pointer => pointer, StringComparer.OrdinalIgnoreCase)
                .ToArray();

            return new LoreLensResult(
                QueryText: queryText,
                Retrieved: matches.Count,
                RuntimeFingerprint: $"lore-lens:{VectorProfileName}",
                VectorProfile: VectorProfileName,
                AppliedFilters: appliedFilters,
                PackProfileIds: packProfiles,
                SourcePointers: sourcePointers,
                Matches: matches,
                GeneratedAtUtc: DateTimeOffset.UtcNow);
        }
    }

    public PersonaMemoryResult Search(string sessionId, PersonaMemoryQuery query)
    {
        lock (_guard)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return EmptyPersonaResult(query);
            }

            if (!_sessionPersonaIndex.TryGetValue(sessionId, out var cardsById))
            {
                return EmptyPersonaResult(query);
            }

            var scopeRequested = HasContextScope(query);
            var byRelevance = cardsById.Values
                .Select(card => new
                {
                    Card = card,
                    Score = ScorePersonaCard(card, query),
                    MatchesScope = MatchesPersonaScope(card, query)
                })
                .Where(candidate => candidate.MatchesScope)
                .Where(candidate => !scopeRequested || candidate.Score > 0)
                .OrderByDescending(candidate => candidate.Score)
                .ThenByDescending(candidate => candidate.Card.UpdatedAtUtc)
                .ThenBy(candidate => candidate.Card.CardId ?? string.Empty, StringComparer.OrdinalIgnoreCase)
                .ThenBy(candidate => candidate.Card.PersonaId)
                .Take(Math.Max(0, query.TopK))
                .Select(candidate => candidate.Card)
                .ToList();

            return new PersonaMemoryResult(
                SessionId: query.SessionId ?? string.Empty,
                Cards: byRelevance,
                Retrieved: byRelevance.Count,
                PersonaId: query.PersonaId,
                LocationId: query.LocationId,
                Location: query.Location,
                SessionContext: NormalizeValues(query.SessionContext));
        }
    }

    public void Upsert(string sessionId, PersonaMemoryCard card)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(card.PersonaId))
        {
            return;
        }

        lock (_guard)
        {
            if (!_sessionPersonaIndex.TryGetValue(sessionId, out var cardsById))
            {
                cardsById = new Dictionary<string, PersonaMemoryCard>(StringComparer.OrdinalIgnoreCase);
                _sessionPersonaIndex[sessionId] = cardsById;
            }

            cardsById[ResolveCardKey(card)] = card with
            {
                SceneIds = NormalizeValues(card.SceneIds),
                SessionContextTags = NormalizeValues(card.SessionContextTags)
            };
        }
    }

    private sealed record LoreLensCandidate(
        LoreChunkState State,
        double Score,
        IReadOnlyList<string> MatchedTerms,
        string Snippet);

    private static LoreLensCandidate? BuildLoreLensCandidate(
        LoreChunkState state,
        LoreLensQuery request,
        string queryText,
        IReadOnlyList<string> queryTokens,
        IReadOnlyDictionary<string, double> queryVector)
    {
        var semanticScore = ComputeCosineSimilarity(queryVector, state.Vector);
        var metadataScore = ComputeMetadataBoost(state.Chunk, request, queryTokens);
        var exactMatchScore = string.IsNullOrWhiteSpace(queryText)
            ? 0d
            : MatchText(state.Chunk.Content, queryText, exactWeight: 20, containsWeight: 12) / 100d;
        var totalScore = semanticScore + metadataScore + exactMatchScore;
        if (totalScore < Math.Max(0d, request.MinimumScore))
        {
            return null;
        }

        var matchedTerms = queryTokens
            .Where(token => state.Vector.Weights.ContainsKey(token))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(8)
            .ToArray();

        return new LoreLensCandidate(
            State: state,
            Score: Math.Round(totalScore, 4),
            MatchedTerms: matchedTerms,
            Snippet: BuildSnippet(state.Chunk.Content, matchedTerms));
    }

    private static IReadOnlyList<string> BuildAppliedFilters(LoreLensQuery request)
    {
        var filters = new List<string>();
        if (request.ApprovedOnly)
        {
            filters.Add("approved-only");
        }

        AddFilter(filters, "jurisdiction", request.Jurisdiction);
        AddFilter(filters, "district", request.District);
        AddFilter(filters, "region", request.Region);
        AddFilter(filters, "topic", request.TopicTag);
        AddFilter(filters, "campaign", request.CampaignScope);
        AddFilter(filters, "pack", request.PackProfileId);
        return filters;
    }

    private static void AddFilter(List<string> filters, string label, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            filters.Add($"{label}:{value.Trim()}");
        }
    }

    private static IReadOnlyList<EvidencePointer> BuildLoreEvidence(LoreChunk chunk, double score, IReadOnlyList<string> matchedTerms)
    {
        var evidence = new List<EvidencePointer>
        {
            new(
                Kind: "lore-chunk",
                Reference: chunk.ChunkId,
                Label: $"{chunk.Source} [{chunk.District}]",
                Source: "lore-lens"),
            new(
                Kind: "lore-score",
                Reference: score.ToString("0.0000", System.Globalization.CultureInfo.InvariantCulture),
                Label: $"Retrieval score {score:0.0000}",
                Source: VectorProfileName)
        };

        if (!string.IsNullOrWhiteSpace(chunk.PackProfileLinkage))
        {
            evidence.Add(new EvidencePointer(
                Kind: "pack-profile",
                Reference: chunk.PackProfileLinkage,
                Label: chunk.PackProfileLinkage,
                Source: "lore-index"));
        }

        if (matchedTerms.Count > 0)
        {
            evidence.Add(new EvidencePointer(
                Kind: "matched-terms",
                Reference: string.Join(',', matchedTerms),
                Label: string.Join(", ", matchedTerms),
                Source: VectorProfileName));
        }

        return evidence;
    }

    private static bool MatchesLoreLensFilters(LoreChunk chunk, LoreLensQuery request)
    {
        if (request.ApprovedOnly && !IsApproved(chunk.ApprovalState))
        {
            return false;
        }

        return MatchesOptionalScope(chunk.Jurisdiction, request.Jurisdiction)
            && MatchesOptionalScope(chunk.District, request.District)
            && MatchesOptionalScope(chunk.Region, request.Region)
            && MatchesOptionalScope(chunk.TopicTags, request.TopicTag)
            && MatchesOptionalScope(chunk.CampaignScope, request.CampaignScope)
            && MatchesOptionalScope(chunk.PackProfileLinkage, request.PackProfileId);
    }

    private static bool MatchesOptionalScope(string? candidate, string? requested) =>
        string.IsNullOrWhiteSpace(requested) || MatchesScopedText(candidate, requested);

    private static bool IsApproved(string? approvalState) =>
        approvalState is not null
        && (approvalState.Equals("approved", StringComparison.OrdinalIgnoreCase)
            || approvalState.Equals("published", StringComparison.OrdinalIgnoreCase)
            || approvalState.Equals("canonized", StringComparison.OrdinalIgnoreCase));

    private static string NormalizeApprovalState(string? approvalState) =>
        string.IsNullOrWhiteSpace(approvalState)
            ? "approved"
            : approvalState.Trim();

    private static LoreVectorState BuildVector(LoreChunk chunk)
    {
        var weighted = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
        AccumulateWeightedTokens(weighted, chunk.Source, 1.25);
        AccumulateWeightedTokens(weighted, chunk.Jurisdiction, 1.5);
        AccumulateWeightedTokens(weighted, chunk.District, 1.75);
        AccumulateWeightedTokens(weighted, chunk.Region, 1.25);
        AccumulateWeightedTokens(weighted, chunk.TopicTags, 1.75);
        AccumulateWeightedTokens(weighted, chunk.CampaignScope, 1.5);
        AccumulateWeightedTokens(weighted, chunk.PackProfileLinkage, 1.5);
        AccumulateWeightedTokens(weighted, chunk.Content, 1);

        var magnitude = Math.Sqrt(weighted.Values.Sum(weight => weight * weight));
        var keywords = weighted
            .OrderByDescending(static pair => pair.Value)
            .ThenBy(static pair => pair.Key, StringComparer.OrdinalIgnoreCase)
            .Take(8)
            .Select(static pair => pair.Key)
            .ToArray();

        return new LoreVectorState(
            Weights: weighted,
            Magnitude: magnitude,
            Keywords: keywords,
            TokenCount: weighted.Count,
            VectorizedAtUtc: DateTimeOffset.UtcNow);
    }

    private static IReadOnlyDictionary<string, double> BuildWeightedVector(IEnumerable<string> tokens)
    {
        var weighted = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
        foreach (var token in tokens)
        {
            if (weighted.TryGetValue(token, out var current))
            {
                weighted[token] = current + 1;
            }
            else
            {
                weighted[token] = 1;
            }
        }

        return weighted;
    }

    private static void AccumulateWeightedTokens(IDictionary<string, double> weighted, string? source, double weight)
    {
        foreach (var token in Tokenize(source))
        {
            if (weighted.TryGetValue(token, out var current))
            {
                weighted[token] = current + weight;
            }
            else
            {
                weighted[token] = weight;
            }
        }
    }

    private static double ComputeCosineSimilarity(IReadOnlyDictionary<string, double> queryVector, LoreVectorState state)
    {
        if (queryVector.Count == 0 || state.Magnitude <= 0)
        {
            return 0;
        }

        var dot = 0d;
        var queryMagnitude = 0d;
        foreach (var pair in queryVector)
        {
            queryMagnitude += pair.Value * pair.Value;
            if (state.Weights.TryGetValue(pair.Key, out var value))
            {
                dot += pair.Value * value;
            }
        }

        if (dot <= 0 || queryMagnitude <= 0)
        {
            return 0;
        }

        return dot / (Math.Sqrt(queryMagnitude) * state.Magnitude);
    }

    private static double ComputeMetadataBoost(LoreChunk chunk, LoreLensQuery request, IReadOnlyList<string> queryTokens)
    {
        var score = 0d;
        score += MatchesOptionalScope(chunk.Jurisdiction, request.Jurisdiction) && !string.IsNullOrWhiteSpace(request.Jurisdiction) ? 0.2 : 0;
        score += MatchesOptionalScope(chunk.District, request.District) && !string.IsNullOrWhiteSpace(request.District) ? 0.25 : 0;
        score += MatchesOptionalScope(chunk.Region, request.Region) && !string.IsNullOrWhiteSpace(request.Region) ? 0.15 : 0;
        score += MatchesOptionalScope(chunk.TopicTags, request.TopicTag) && !string.IsNullOrWhiteSpace(request.TopicTag) ? 0.2 : 0;
        score += MatchesOptionalScope(chunk.CampaignScope, request.CampaignScope) && !string.IsNullOrWhiteSpace(request.CampaignScope) ? 0.15 : 0;
        score += MatchesOptionalScope(chunk.PackProfileLinkage, request.PackProfileId) && !string.IsNullOrWhiteSpace(request.PackProfileId) ? 0.15 : 0;

        foreach (var token in queryTokens)
        {
            score += MatchText(chunk.TopicTags, token, exactWeight: 6, containsWeight: 4) / 100d;
            score += MatchText(chunk.Content, token, exactWeight: 4, containsWeight: 2) / 100d;
        }

        return score;
    }

    private static string BuildSnippet(string content, IReadOnlyList<string> matchedTerms)
    {
        const int maxLength = 160;
        if (string.IsNullOrWhiteSpace(content))
        {
            return string.Empty;
        }

        if (matchedTerms.Count == 0)
        {
            return content.Length <= maxLength
                ? content
                : $"{content[..maxLength].TrimEnd()}...";
        }

        var firstMatch = matchedTerms
            .Select(term => content.IndexOf(term, StringComparison.OrdinalIgnoreCase))
            .Where(index => index >= 0)
            .DefaultIfEmpty(0)
            .Min();
        var start = Math.Max(0, firstMatch - 40);
        var length = Math.Min(maxLength, content.Length - start);
        var snippet = content.Substring(start, length).Trim();
        if (start > 0)
        {
            snippet = $"...{snippet}";
        }

        if (start + length < content.Length)
        {
            snippet = $"{snippet}...";
        }

        return snippet;
    }

    private static int ScoreLoreChunk(
        LoreChunk chunk,
        string? district,
        string? topicTag,
        string? campaignScope)
    {
        var score = 0;

        if (!string.IsNullOrWhiteSpace(district))
        {
            if (string.Equals(chunk.District, district, StringComparison.OrdinalIgnoreCase))
            {
                score += 8;
            }
            else if (chunk.District.Contains(district, StringComparison.OrdinalIgnoreCase))
            {
                score += 5;
            }
            else
            {
                return 0;
            }
        }

        if (!string.IsNullOrWhiteSpace(topicTag))
        {
            score += MatchText(chunk.TopicTags, topicTag, exactWeight: 6, containsWeight: 4);
            score += MatchText(chunk.Content, topicTag, exactWeight: 3, containsWeight: 2);
        }

        if (!string.IsNullOrWhiteSpace(campaignScope))
        {
            score += MatchText(chunk.CampaignScope, campaignScope, exactWeight: 5, containsWeight: 3);
            score += MatchText(chunk.Content, campaignScope, exactWeight: 2, containsWeight: 1);
        }

        return score == 0 && string.IsNullOrWhiteSpace(district) && string.IsNullOrWhiteSpace(topicTag) && string.IsNullOrWhiteSpace(campaignScope)
            ? 1
            : score;
    }

    private static int ScorePersonaCard(PersonaMemoryCard card, PersonaMemoryQuery query)
    {
        var score = 0;
        if (!string.IsNullOrWhiteSpace(query.PersonaId)
            && string.Equals(card.PersonaId, query.PersonaId, StringComparison.OrdinalIgnoreCase))
        {
            score += 40;
        }

        if (!string.IsNullOrWhiteSpace(query.LocationId))
        {
            score += MatchText(card.LocationId, query.LocationId, exactWeight: 18, containsWeight: 12);
        }

        if (!string.IsNullOrWhiteSpace(query.Location))
        {
            score += MatchText(card.Location, query.Location, exactWeight: 16, containsWeight: 10);
            score += MatchText(string.Join(' ', card.SceneIds ?? Array.Empty<string>()), query.Location, exactWeight: 8, containsWeight: 5);
        }

        var searchable = string.Join(' ', new[]
        {
            card.StaticCard,
            card.RelationshipState,
            card.EpisodicMemory,
            card.HiddenPlotMemory,
            card.LocationId,
            card.Location,
            string.Join(' ', card.SceneIds ?? Array.Empty<string>()),
            string.Join(' ', card.SessionContextTags ?? Array.Empty<string>())
        });
        foreach (var token in Tokenize(query.SceneId))
        {
            score += MatchText(searchable, token, exactWeight: 6, containsWeight: 4);
        }

        foreach (var token in EnumerateQueryContextTokens(query))
        {
            score += MatchText(searchable, token, exactWeight: 7, containsWeight: 5);
        }

        return score == 0 && !HasContextScope(query) ? 1 : score;
    }

    private static PersonaMemoryResult EmptyPersonaResult(PersonaMemoryQuery query) =>
        new(
            SessionId: query.SessionId ?? string.Empty,
            Cards: Array.Empty<PersonaMemoryCard>(),
            Retrieved: 0,
            PersonaId: query.PersonaId,
            LocationId: query.LocationId,
            Location: query.Location,
            SessionContext: NormalizeValues(query.SessionContext));

    private static bool MatchesPersonaScope(PersonaMemoryCard card, PersonaMemoryQuery query)
    {
        if (!string.IsNullOrWhiteSpace(query.PersonaId)
            && !string.Equals(card.PersonaId, query.PersonaId, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(query.LocationId)
            && !MatchesScopedText(card.LocationId, query.LocationId))
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(query.Location)
            && !MatchesScopedText(card.Location, query.Location)
            && !(card.SceneIds?.Any(scene => scene.Contains(query.Location, StringComparison.OrdinalIgnoreCase)) ?? false)
            && !card.EpisodicMemory.Contains(query.Location, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return true;
    }

    private static bool MatchesScopedText(string? candidate, string scope) =>
        !string.IsNullOrWhiteSpace(candidate)
        && (string.Equals(candidate.Trim(), scope, StringComparison.OrdinalIgnoreCase)
            || candidate.Contains(scope, StringComparison.OrdinalIgnoreCase));

    private static bool HasContextScope(PersonaMemoryQuery query) =>
        !string.IsNullOrWhiteSpace(query.SceneId)
        || !string.IsNullOrWhiteSpace(query.PersonaId)
        || !string.IsNullOrWhiteSpace(query.LocationId)
        || !string.IsNullOrWhiteSpace(query.Location)
        || (query.SessionContext?.Count ?? 0) > 0;

    private static string ResolveCardKey(PersonaMemoryCard card)
    {
        if (!string.IsNullOrWhiteSpace(card.CardId))
        {
            return card.CardId;
        }

        var sceneScope = string.Join('|', NormalizeValues(card.SceneIds));
        var contextScope = string.Join('|', NormalizeValues(card.SessionContextTags));
        return string.Join("::", new[]
        {
            card.PersonaId.Trim(),
            card.LocationId?.Trim() ?? string.Empty,
            card.Location?.Trim() ?? string.Empty,
            sceneScope,
            contextScope
        });
    }

    private static IReadOnlyList<string> NormalizeValues(IReadOnlyList<string>? values) =>
        values is null
            ? Array.Empty<string>()
            : values
                .Where(static value => !string.IsNullOrWhiteSpace(value))
                .Select(static value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

    private static IEnumerable<string> EnumerateQueryContextTokens(PersonaMemoryQuery query)
    {
        foreach (var token in Tokenize(query.SceneId))
        {
            yield return token;
        }

        foreach (var token in NormalizeValues(query.SessionContext).SelectMany(Tokenize))
        {
            yield return token;
        }
    }

    private static int MatchText(string? source, string target, int exactWeight, int containsWeight)
    {
        if (string.IsNullOrWhiteSpace(source) || string.IsNullOrWhiteSpace(target))
        {
            return 0;
        }

        if (string.Equals(source.Trim(), target, StringComparison.OrdinalIgnoreCase))
        {
            return exactWeight;
        }

        return source.Contains(target, StringComparison.OrdinalIgnoreCase)
            ? containsWeight
            : 0;
    }

    private static string[] Tokenize(string? source) =>
        string.IsNullOrWhiteSpace(source)
            ? Array.Empty<string>()
            : source
                .Split([' ', ',', ';', '|', '/', '\\', '-', '_', '.', ':', '(', ')', '[', ']'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(static token => token.Trim().ToLowerInvariant())
                .Where(static token => token.Length >= 3)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
}
