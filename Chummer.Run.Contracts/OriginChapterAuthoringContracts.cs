using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;

namespace Chummer.Run.Contracts.Community;

/// <summary>Player-approved narrative facts only; never a character file or rules packet.</summary>
public sealed record OriginChapterSource(
    string WorkspaceId, string ChapterId, string ChapterDigest, string AcceptedDecisionId,
    string Locale, string RunnerName, IReadOnlyList<OriginChapterSourceFact> Facts);

public sealed record OriginChapterSourceFact(string FactId, string DecisionId, string Text);

public sealed record OriginChapterAuthoringRequest(
    string RequestId, OriginChapterSource Source, bool ExternalProcessingConsent);

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
        var captured = source with { Facts = Array.AsReadOnly(facts) };
        if (JsonSerializer.SerializeToUtf8Bytes(captured, Json).Length > 32 * 1024)
            throw new ArgumentException("The narrative source is oversized.");
        return captured;
    }

    public static string Digest(OriginChapterSource source)
        => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(Capture(source), Json))).ToLowerInvariant();

    // Same approved source resumes the same subject-scoped request on every
    // device. A lost response or application restart never invents a paid retry.
    public static string RequestId(OriginChapterSource source) => "chapter-" + Digest(source);

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
    public bool RequiresReaderReview => true;
    public bool AffectsMechanics => false;
    public bool PublicationAuthorized => false;
}
