using System.Globalization;
using System.Text.Json.Nodes;

namespace Chummer.Run.Api.Services;

internal readonly record struct ReleaseProofFreshnessEvaluation(
    bool IsFresh,
    string MaterializedStatus,
    string Reason);

internal static class ReleaseProofFreshnessEvaluator
{
    internal static readonly TimeSpan MaximumFutureClockSkew = TimeSpan.FromMinutes(5);
    internal static readonly TimeSpan MaximumDeclaredProofAge = TimeSpan.FromDays(7);

    public static ReleaseProofFreshnessEvaluation Evaluate(
        JsonObject? proofFreshness,
        JsonObject? releaseProofPayload,
        DateTimeOffset? publishedAt,
        DateTimeOffset evaluatedAt)
    {
        ReleaseProofTrustEvaluation evidence = ReleaseProofTrustEvaluator.Validate(releaseProofPayload);
        if (!evidence.IsValid)
        {
            return Missing(evidence.Reason);
        }

        if (proofFreshness is null || publishedAt is null)
        {
            return Missing("proof freshness facts or the publication timestamp are missing");
        }

        if (publishedAt.Value - evaluatedAt > MaximumFutureClockSkew)
        {
            return Stale("the publication timestamp is more than five minutes in the future");
        }

        string sourceStatus = NormalizeToken(GetString(proofFreshness["status"]));
        if (!string.Equals(sourceStatus, "fresh", StringComparison.Ordinal))
        {
            return sourceStatus.Length == 0 || string.Equals(sourceStatus, "missing", StringComparison.Ordinal)
                ? Missing("proof freshness status is missing")
                : Stale($"proof freshness status is {sourceStatus}");
        }

        string[] requiredFields =
        [
            "releaseProofGeneratedAt",
            "releaseProofAgeSeconds",
            "releaseProofMaxAgeSeconds",
            "uiLocalizationGeneratedAt",
            "uiLocalizationAgeSeconds",
            "uiLocalizationMaxAgeSeconds",
            "flagshipReadinessGeneratedAt",
            "flagshipReadinessAgeSeconds",
            "flagshipReadinessMaxAgeSeconds",
            "flagshipReadinessStatus",
            "flagshipReadinessCoverageGapKeys",
            "flagshipDesktopClientReady",
            "flagshipReadinessSnapshotSha256"
        ];
        if (requiredFields.Any(field => !proofFreshness.ContainsKey(field) || proofFreshness[field] is null))
        {
            return Missing("the fresh proof claim omits required generated-at, age, max-age, or flagship readiness facts");
        }

        if (!TryReadFact(proofFreshness, "releaseProof", out ProofAgeFact releaseProof)
            || !TryReadFact(proofFreshness, "uiLocalization", out ProofAgeFact uiLocalization)
            || !TryReadFact(proofFreshness, "flagshipReadiness", out ProofAgeFact flagshipReadiness))
        {
            return Stale("one or more proof freshness facts are malformed");
        }

        DateTimeOffset publicationInstant = publishedAt.Value;
        DateTimeOffset effectiveInstant = evaluatedAt < publicationInstant
            ? publicationInstant
            : evaluatedAt;
        foreach (ProofAgeFact fact in new[] { releaseProof, uiLocalization, flagshipReadiness })
        {
            if (fact.MaxAgeSeconds != checked((long)MaximumDeclaredProofAge.TotalSeconds))
            {
                return Stale($"{fact.Name} maximum age does not match the server's seven-day release-proof policy");
            }

            if (!FactMatchesPublicationSnapshot(fact, publicationInstant))
            {
                return Stale($"{fact.Name} age does not match its generated-at timestamp and publication instant");
            }

            if (fact.GeneratedAt - effectiveInstant > MaximumFutureClockSkew)
            {
                return Stale($"{fact.Name} timestamp is more than five minutes in the future");
            }

            long effectiveAgeSeconds = AgeSeconds(effectiveInstant, fact.GeneratedAt);
            if (effectiveAgeSeconds > fact.MaxAgeSeconds)
            {
                return Stale($"{fact.Name} proof is older than its declared maximum age");
            }
        }

        if (evidence.ReleaseProofGeneratedAt is not DateTimeOffset releaseProofEvidenceGeneratedAt
            || releaseProof.GeneratedAt.ToUniversalTime() != releaseProofEvidenceGeneratedAt.ToUniversalTime())
        {
            return Stale("releaseProof freshness timestamp is not bound to releaseProof.generatedAt");
        }

        if (evidence.UiLocalizationGeneratedAt is not DateTimeOffset uiLocalizationEvidenceGeneratedAt
            || uiLocalization.GeneratedAt.ToUniversalTime() != uiLocalizationEvidenceGeneratedAt.ToUniversalTime())
        {
            return Stale("uiLocalization freshness timestamp is not bound to releaseProof.uiLocalizationReleaseGate.generatedAt");
        }

        if (evidence.FlagshipReadinessGeneratedAt is not DateTimeOffset flagshipEvidenceGeneratedAt
            || flagshipReadiness.GeneratedAt.ToUniversalTime() != flagshipEvidenceGeneratedAt.ToUniversalTime())
        {
            return Stale("flagshipReadiness freshness timestamp is not bound to releaseProof.flagshipReadiness.generatedAt");
        }

        string flagshipStatus = NormalizeToken(GetString(proofFreshness["flagshipReadinessStatus"]));
        if (!string.Equals(flagshipStatus, "pass", StringComparison.Ordinal))
        {
            return Stale("flagship readiness status is not pass");
        }

        if (!TryGetBoolean(proofFreshness["flagshipDesktopClientReady"], out bool desktopReady) || !desktopReady)
        {
            return Stale("flagship desktop client readiness is not true");
        }

        if (!string.Equals(flagshipStatus, evidence.FlagshipReadinessStatus, StringComparison.Ordinal)
            || desktopReady != evidence.FlagshipDesktopClientReady
            || !TryGetStringArray(proofFreshness["flagshipReadinessCoverageGapKeys"], out IReadOnlyList<string> coverageGapKeys)
            || !coverageGapKeys.SequenceEqual(evidence.FlagshipReadinessCoverageGapKeys, StringComparer.Ordinal)
            || !string.Equals(
                GetString(proofFreshness["flagshipReadinessSnapshotSha256"]),
                evidence.FlagshipReadinessSnapshotSha256,
                StringComparison.Ordinal))
        {
            return Stale("flagship readiness freshness facts do not match the digest-bound embedded readiness snapshot");
        }

        if (!evidence.FlagshipReadinessPasses)
        {
            return Stale("the embedded flagship readiness snapshot is not passing");
        }

        return new ReleaseProofFreshnessEvaluation(true, "fresh", "all proof freshness facts are current and internally consistent");
    }

    private static bool TryReadFact(JsonObject proofFreshness, string prefix, out ProofAgeFact fact)
    {
        fact = default;
        if (!TryGetCanonicalUtcTimestamp(proofFreshness[$"{prefix}GeneratedAt"], out DateTimeOffset generatedAt)
            || !TryGetInt64(proofFreshness[$"{prefix}AgeSeconds"], out long ageSeconds)
            || !TryGetInt64(proofFreshness[$"{prefix}MaxAgeSeconds"], out long maxAgeSeconds)
            || ageSeconds < 0
            || maxAgeSeconds < 0)
        {
            return false;
        }

        fact = new ProofAgeFact(prefix, generatedAt, ageSeconds, maxAgeSeconds);
        return true;
    }

    private static bool FactMatchesPublicationSnapshot(ProofAgeFact fact, DateTimeOffset publishedAt)
    {
        if (fact.GeneratedAt - publishedAt > MaximumFutureClockSkew)
        {
            return false;
        }

        return fact.AgeSeconds == AgeSeconds(publishedAt, fact.GeneratedAt);
    }

    private static long AgeSeconds(DateTimeOffset later, DateTimeOffset earlier)
        => later <= earlier
            ? 0
            : checked((long)Math.Floor((later - earlier).TotalSeconds));

    private static bool TryGetDateTimeOffset(JsonNode? node, out DateTimeOffset value)
        => DateTimeOffset.TryParse(
            GetString(node),
            CultureInfo.InvariantCulture,
            DateTimeStyles.RoundtripKind,
            out value);

    private static bool TryGetCanonicalUtcTimestamp(JsonNode? node, out DateTimeOffset value)
    {
        string? text = GetString(node);
        if (!TryGetDateTimeOffset(node, out value) || text is null)
        {
            return false;
        }

        return string.Equals(
            text,
            value.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture),
            StringComparison.Ordinal);
    }

    private static bool TryGetInt64(JsonNode? node, out long value)
    {
        value = 0;
        if (node is not JsonValue jsonValue)
        {
            return false;
        }

        if (jsonValue.TryGetValue<long>(out value))
        {
            return true;
        }

        if (jsonValue.TryGetValue<int>(out int intValue))
        {
            value = intValue;
            return true;
        }

        return long.TryParse(GetString(node), NumberStyles.Integer, CultureInfo.InvariantCulture, out value);
    }

    private static bool TryGetBoolean(JsonNode? node, out bool value)
    {
        value = false;
        return node is JsonValue jsonValue && jsonValue.TryGetValue(out value);
    }

    private static bool TryGetStringArray(JsonNode? node, out IReadOnlyList<string> values)
    {
        values = [];
        if (node is not JsonArray array)
        {
            return false;
        }

        List<string> parsed = [];
        foreach (JsonNode? item in array)
        {
            string? value = GetString(item);
            if (string.IsNullOrWhiteSpace(value) || value != value.Trim())
            {
                return false;
            }

            parsed.Add(value);
        }

        if (parsed.Distinct(StringComparer.Ordinal).Count() != parsed.Count)
        {
            return false;
        }

        values = parsed;
        return true;
    }

    private static string? GetString(JsonNode? node)
        => node switch
        {
            null => null,
            JsonValue value => value.TryGetValue<string>(out string? text)
                ? text
                : value.ToJsonString().Trim('"'),
            _ => node.ToJsonString()
        };

    private static string NormalizeToken(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim().ToLowerInvariant();

    private static ReleaseProofFreshnessEvaluation Missing(string reason)
        => new(false, "missing", reason);

    private static ReleaseProofFreshnessEvaluation Stale(string reason)
        => new(false, "stale", reason);

    private readonly record struct ProofAgeFact(
        string Name,
        DateTimeOffset GeneratedAt,
        long AgeSeconds,
        long MaxAgeSeconds);
}
