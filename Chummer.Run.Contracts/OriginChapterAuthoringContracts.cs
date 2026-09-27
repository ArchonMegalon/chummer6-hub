using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Contracts.Community;

/// <summary>Player-approved narrative input; never a character file or rules packet.</summary>
public sealed record OriginChapterSource(
    string WorkspaceId, string ChapterId, string ChapterDigest, string AcceptedDecisionId,
    string Locale, string RunnerName, IReadOnlyList<OriginChapterSourceFact> Facts)
{
    // Possibilities are not accepted history. Omission preserves every old
    // source digest/request ID; callers must retain an already issued source,
    // not recompute its possibilities from a later turn or changed budget.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public OriginChapterNarrativeContext? NarrativeContext { get; init; }
}

public sealed record OriginChapterSourceFact(string FactId, string DecisionId, string Text);

/// <summary>
/// Optional, player-approved hints at the next decision. These identifiers bind
/// the client's snapshot, not Hub rules authority. They never select a module,
/// promise admission/completion or grant effects. Use only when the story fits;
/// an unsuccessful attempt may be narrated without awarding its module. An
/// unavailable path is not necessarily unaffordable tuition or social rejection.
/// </summary>
public sealed record OriginChapterNarrativeContext(
    string TurnId, string DecisionDigest, IReadOnlyList<OriginChapterStoryOpportunity> Opportunities);

/// <summary>Short original label/caption only, not rulebook prose or future answers.</summary>
public sealed record OriginChapterStoryOpportunity(string ChoiceId, string Caption, string Availability);

public static class OriginChapterOpportunityAvailability
{
    public const string Available = "available";
    public const string Unavailable = "unavailable";
}

public sealed record OriginChapterAuthoringRequest(
    string RequestId, OriginChapterSource Source, bool ExternalProcessingConsent)
{
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public OriginChapterPredecessor? Previous { get; init; }
}

/// <summary>Exact reader-accepted predecessor, not provider order or spending authority.</summary>
public sealed record OriginChapterPredecessor(
    string RequestId, string SourceDigest, string ProviderReceiptDigest, string TextDigest);

/// <summary>
/// Separately edited FirstBook-origin prose. The job receipt binds the delivered
/// derivative; these digests retain its original provider input. No account or
/// model-routing details, and no claim of reader acceptance or rules authority.
/// </summary>
public sealed record OriginChapterEditorialProvenance(
    string OriginalTextDigest, string OriginalProviderReceiptDigest, string Method);

/// <summary>Shared, bounded wire identity. A digest is not Core or provider authority.</summary>
public static class OriginChapterSourceIdentity
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { MaxDepth = 16 };

    public static OriginChapterSource Capture(OriginChapterSource source)
    {
        ArgumentNullException.ThrowIfNull(source);
        RequireId(source.WorkspaceId); RequireId(source.ChapterId); RequireId(source.AcceptedDecisionId);
        if (!IsDigest(source.ChapterDigest) || !SupportedLocale(source.Locale)
            || string.IsNullOrWhiteSpace(source.RunnerName) || source.RunnerName.Length > 256
            || source.Facts is not { Count: > 0 and <= 128 }) throw new ArgumentException("The narrative source is invalid.");
        var facts = source.Facts.ToArray();
        foreach (var fact in facts)
        {
            if (fact is null) throw new ArgumentException("The narrative source is invalid.");
            RequireId(fact.FactId); RequireId(fact.DecisionId);
            if (string.IsNullOrWhiteSpace(fact.Text) || fact.Text.Length > 2048)
                throw new ArgumentException("The narrative fact is invalid.");
        }
        if (facts.Select(f => f.FactId).Distinct(StringComparer.Ordinal).Count() != facts.Length)
            throw new ArgumentException("Narrative fact IDs must be unique.");
        var captured = source with { Facts = Array.AsReadOnly(facts), NarrativeContext = CaptureNarrativeContext(source.NarrativeContext) };
        if (JsonSerializer.SerializeToUtf8Bytes(captured, Json).Length > 32 * 1024)
            throw new ArgumentException("The narrative source is oversized.");
        return captured;
    }

    private static OriginChapterNarrativeContext? CaptureNarrativeContext(OriginChapterNarrativeContext? context)
    {
        if (context is null) return null;
        RequireId(context.TurnId);
        if (!IsDigest(context.DecisionDigest) || context.Opportunities is not { Count: > 0 and <= 8 })
            throw new ArgumentException("The narrative possibilities are invalid.");
        var opportunities = context.Opportunities.ToArray();
        foreach (var opportunity in opportunities)
        {
            if (opportunity is null) throw new ArgumentException("The narrative possibility is invalid.");
            RequireId(opportunity.ChoiceId);
            if (string.IsNullOrWhiteSpace(opportunity.Caption) || opportunity.Caption.Length > 1024
                || opportunity.Caption != opportunity.Caption.Trim() || opportunity.Caption.Any(char.IsControl)
                || opportunity.Availability is not (OriginChapterOpportunityAvailability.Available
                    or OriginChapterOpportunityAvailability.Unavailable))
                throw new ArgumentException("The narrative possibility is invalid.");
        }
        if (opportunities.Select(o => o.ChoiceId).Distinct(StringComparer.Ordinal).Count() != opportunities.Length)
            throw new ArgumentException("Narrative possibility IDs must be unique.");
        return context with { Opportunities = Array.AsReadOnly(opportunities) };
    }

    public static string Digest(OriginChapterSource source)
        => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(Capture(source), Json))).ToLowerInvariant();

    // Opportunities are optional input to the same chapter, not a new paid
    // chapter identity. Legacy/no-context clients and another device must find
    // the already admitted job. Digest still binds ALL approved input; Create,
    // worker admission and reader acceptance reject any source-digest change.
    public static string RequestId(OriginChapterSource source)
    {
        var captured = Capture(source); // Validate context before omitting it from the lookup key.
        return "chapter-" + Digest(captured with { NarrativeContext = null });
    }

    public static OriginChapterPredecessor? CapturePredecessor(OriginChapterPredecessor? previous)
    {
        if (previous is null) return null;
        RequireId(previous.RequestId);
        if (!IsDigest(previous.SourceDigest) || !IsDigest(previous.ProviderReceiptDigest) || !IsDigest(previous.TextDigest))
            throw new ArgumentException("The reader-accepted predecessor is invalid.");
        return previous;
    }

    private static void RequireId(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > 256 || value != value.Trim() || value.Any(char.IsControl))
            throw new ArgumentException("The authoring identity is invalid.");
    }
    private static bool IsDigest(string? value) => value is { Length: 64 }
        && value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static bool SupportedLocale(string? locale)
    {
        if (string.IsNullOrWhiteSpace(locale) || locale.Length > 32 || locale != locale.Trim()) return false;
        try { return CultureInfo.GetCultureInfo(locale).TwoLetterISOLanguageName is "de" or "en" or "es"; }
        catch (CultureNotFoundException) { return false; }
    }
}

public static class OriginChapterAuthoringStates
{
    public const string AwaitingAuthoring = "awaiting_authoring";
    public const string ReconciliationRequired = "reconciliation_required";
    public const string ReviewRequired = "review_required";
}

/// <summary>Private readback. No provider account identifiers, secrets or public artifact URLs.</summary>
public sealed record OriginChapterAuthoringJob(
    string RequestId, string SourceDigest, OriginChapterSource Source, string State,
    string Provider, string? DraftText, string? ProviderReceiptDigest)
{
    // Omitted for old/unreviewed jobs, preserving their durable wire checksum.
    // Reading acceptance is not mechanics, publication or new spending authority.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ReaderAcceptedTextDigest { get; init; }
    // Absent on historical jobs: never infer a predecessor when restoring them.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public OriginChapterPredecessor? Previous { get; init; }
    // Provider continues to name the original draft provider. Omit on historical
    // unedited jobs so their durable checksums remain unchanged.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public OriginChapterEditorialProvenance? Editorial { get; init; }
    public bool RequiresReaderReview => true;
    public bool AffectsMechanics => false;
    public bool PublicationAuthorized => false;
}
