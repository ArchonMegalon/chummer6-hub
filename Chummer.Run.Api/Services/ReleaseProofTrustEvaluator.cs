using System.Buffers;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services;

internal readonly record struct ReleaseProofTrustEvaluation(
    bool IsValid,
    string Reason,
    DateTimeOffset? ReleaseProofGeneratedAt,
    DateTimeOffset? UiLocalizationGeneratedAt,
    DateTimeOffset? FlagshipReadinessGeneratedAt,
    string FlagshipReadinessStatus,
    bool FlagshipDesktopClientReady,
    IReadOnlyList<string> FlagshipReadinessCoverageGapKeys,
    IReadOnlyList<string> FlagshipReadinessLaunchBlockers,
    string? FlagshipReadinessSnapshotSha256)
{
    public bool FlagshipReadinessPasses =>
        ReleaseProofTrustEvaluator.IsPassStatus(FlagshipReadinessStatus)
        && FlagshipDesktopClientReady
        && FlagshipReadinessCoverageGapKeys.Count == 0
        && FlagshipReadinessLaunchBlockers.Count == 0;
}

/// <summary>
/// Validates the evidence that proof-freshness metrics summarize. Freshness is
/// never an independent assertion: the Registry-compatible release proof,
/// localization gate, and digest-bound flagship readiness snapshot must all be
/// present and structurally valid before their timestamps can be considered.
/// </summary>
internal static partial class ReleaseProofTrustEvaluator
{
    internal const string FlagshipReadinessContractName =
        "chummer.flagship_product_readiness_gate.v1";

    private const int FlagshipReadinessReasonMaxLength = 4096;
    private const int FlagshipReadinessBlockerMaxLength = 1024;
    private const int FlagshipReadinessMaxBlockers = 128;
    private const int FlagshipReadinessMaxCoverageGaps = 128;

    private static readonly string[] RequiredJourneys =
    [
        "install_claim_restore_continue",
        "build_explain_publish",
        "campaign_session_recover_recap",
        "report_cluster_release_notify",
        "organize_community_and_close_loop"
    ];

    private static readonly string[] RequiredRoutePrefix =
    [
        "/downloads/install/avalonia-linux-x64-installer",
        "/home/access",
        "/home/work",
        "/account/access",
        "/account/work",
        "/account/support",
        "/contact",
        "/downloads"
    ];

    private static readonly string[] RequiredShippingLocales =
        ["en-us", "de-de", "fr-fr", "ja-jp", "pt-br", "zh-cn"];

    private static readonly string[] RequiredAcceptanceGates =
    [
        "pseudo_localization",
        "missing_key_fail_fast",
        "top_surface_overflow_checks",
        "locale_smoke_first_launch",
        "locale_smoke_settings",
        "locale_smoke_explain",
        "locale_smoke_updater",
        "locale_smoke_support",
        "non_english_generated_artifact_smoke"
    ];

    private static readonly string[] RequiredLocalizationDomains =
    [
        "app_chrome",
        "install_update_support",
        "explain_receipts",
        "data_rules_names",
        "generated_artifacts"
    ];

    private static readonly HashSet<string> ReleaseProofKeys =
    [
        "status",
        "generatedAt",
        "baseUrl",
        "journeysPassed",
        "proofRoutes",
        "uiLocalizationReleaseGate",
        "flagshipReadiness"
    ];

    private static readonly HashSet<string> LocalizationGateKeys =
    [
        "status",
        "generatedAt",
        "defaultKeyCount",
        "explicitFallbackRuntime",
        "signoffSmokeRunnerStatus",
        "shippingLocales",
        "acceptanceGates",
        "domainCoverage",
        "localeDomainCoverage",
        "blockingFindingsCount",
        "blockingFindings",
        "translationBacklogFindingsCount",
        "translationBacklogFindings",
        "localeSummary"
    ];

    private static readonly HashSet<string> LocaleSummaryKeys =
    [
        "locale",
        "untranslatedKeyCount",
        "overrideCount",
        "minimumOverrideCount",
        "missingReleaseSeedKeys",
        "legacyXmlPresent",
        "legacyDataXmlPresent"
    ];

    private static readonly HashSet<string> FlagshipReadinessKeys =
    [
        "contractName",
        "generatedAt",
        "status",
        "coverageGapKeys",
        "launchBlockers",
        "desktopClientReady",
        "reason",
        "sourceSha256",
        "snapshotSha256"
    ];

    private static readonly HashSet<string> AllowedBaseUrls =
        new(StringComparer.Ordinal) { "https://chummer.run" };

    public static ReleaseProofTrustEvaluation Validate(JsonObject? releaseProof)
    {
        if (releaseProof is null)
        {
            return Invalid("releaseProof is missing");
        }

        if (!HasExactKeys(releaseProof, ReleaseProofKeys))
        {
            return Invalid("releaseProof keys do not match the Registry contract");
        }

        if (!IsPassStatus(GetString(releaseProof["status"])))
        {
            return Invalid("releaseProof status is not pass");
        }

        if (!TryGetCanonicalUtcTimestamp(releaseProof["generatedAt"], out DateTimeOffset proofGeneratedAt))
        {
            return Invalid("releaseProof generatedAt is invalid");
        }

        string baseUrl = GetString(releaseProof["baseUrl"])?.Trim() ?? string.Empty;
        if (!AllowedBaseUrls.Contains(baseUrl))
        {
            return Invalid("releaseProof baseUrl is not an allowed canonical release origin");
        }

        if (!ReadExactStringArray(releaseProof["journeysPassed"], RequiredJourneys, out _))
        {
            return Invalid("releaseProof journeysPassed does not match the canonical ordered journey contract");
        }

        if (!ValidateProofRoutes(releaseProof["proofRoutes"]))
        {
            return Invalid("releaseProof proofRoutes does not match the canonical Registry route contract");
        }

        string localizationReason = "releaseProof uiLocalizationReleaseGate is missing";
        DateTimeOffset localizationGeneratedAt = default;
        if (releaseProof["uiLocalizationReleaseGate"] is not JsonObject localizationGate
            || !ValidateLocalizationGate(localizationGate, out localizationGeneratedAt, out localizationReason))
        {
            return Invalid(localizationReason);
        }

        DateTimeOffset flagshipGeneratedAt = default;
        string flagshipStatus = string.Empty;
        bool desktopReady = false;
        IReadOnlyList<string> coverageGapKeys = [];
        IReadOnlyList<string> launchBlockers = [];
        string snapshotSha256 = string.Empty;
        string flagshipReason = "releaseProof flagshipReadiness is missing";
        if (releaseProof["flagshipReadiness"] is not JsonObject flagshipReadiness
            || !ValidateFlagshipReadiness(
                flagshipReadiness,
                out flagshipGeneratedAt,
                out flagshipStatus,
                out desktopReady,
                out coverageGapKeys,
                out launchBlockers,
                out snapshotSha256,
                out flagshipReason))
        {
            return Invalid(flagshipReason);
        }

        return new ReleaseProofTrustEvaluation(
            true,
            "release proof evidence is structurally valid and digest-bound",
            proofGeneratedAt,
            localizationGeneratedAt,
            flagshipGeneratedAt,
            flagshipStatus,
            desktopReady,
            coverageGapKeys,
            launchBlockers,
            snapshotSha256);
    }

    internal static bool IsPassStatus(string? value)
        => NormalizeToken(value) is "pass" or "passed" or "ready";

    private static bool ValidateProofRoutes(JsonNode? node)
    {
        if (node is not JsonArray routes || routes.Count < RequiredRoutePrefix.Length)
        {
            return false;
        }

        List<string> values = [];
        foreach (JsonNode? route in routes)
        {
            string? value = GetString(route);
            if (string.IsNullOrWhiteSpace(value) || value != value.Trim())
            {
                return false;
            }

            values.Add(value);
        }

        if (values.Distinct(StringComparer.Ordinal).Count() != values.Count
            || !values.Take(RequiredRoutePrefix.Length).SequenceEqual(RequiredRoutePrefix, StringComparer.Ordinal))
        {
            return false;
        }

        string[] extensions = values.Skip(RequiredRoutePrefix.Length).ToArray();
        return extensions.All(static route => ArtifactInstallRouteRegex().IsMatch(route))
               && extensions.SequenceEqual(extensions.Order(StringComparer.Ordinal), StringComparer.Ordinal);
    }

    private static bool ValidateLocalizationGate(
        JsonObject gate,
        out DateTimeOffset generatedAt,
        out string reason)
    {
        generatedAt = default;
        reason = "releaseProof uiLocalizationReleaseGate is invalid";
        if (!HasExactKeys(gate, LocalizationGateKeys)
            || !IsPassStatus(GetString(gate["status"]))
            || !TryGetCanonicalUtcTimestamp(gate["generatedAt"], out generatedAt)
            || !TryGetInt64(gate["defaultKeyCount"], out long defaultKeyCount)
            || defaultKeyCount <= 0
            || !IsPassStatus(GetString(gate["explicitFallbackRuntime"]))
            || !IsPassStatus(GetString(gate["signoffSmokeRunnerStatus"]))
            || !ReadExactStringArray(gate["shippingLocales"], RequiredShippingLocales, out _)
            || !ReadExactStringArray(gate["acceptanceGates"], RequiredAcceptanceGates, out _)
            || !ValidatePassingCoverage(gate["domainCoverage"], RequiredLocalizationDomains)
            || !ValidateLocaleCoverage(gate["localeDomainCoverage"])
            || !TryGetInt64(gate["blockingFindingsCount"], out long blockingCount)
            || blockingCount != 0
            || gate["blockingFindings"] is not JsonArray { Count: 0 }
            || !TryGetInt64(gate["translationBacklogFindingsCount"], out long backlogCount)
            || backlogCount != 0
            || gate["translationBacklogFindings"] is not JsonArray { Count: 0 }
            || !ValidateLocaleSummary(gate["localeSummary"], defaultKeyCount))
        {
            return false;
        }

        reason = string.Empty;
        return true;
    }

    private static bool ValidatePassingCoverage(JsonNode? node, IReadOnlyCollection<string> requiredKeys)
    {
        if (node is not JsonObject coverage
            || coverage.Count != requiredKeys.Count
            || !coverage.Select(static pair => pair.Key).ToHashSet(StringComparer.Ordinal).SetEquals(requiredKeys))
        {
            return false;
        }

        return requiredKeys.All(key => IsPassStatus(GetString(coverage[key])));
    }

    private static bool ValidateLocaleCoverage(JsonNode? node)
    {
        if (node is not JsonObject localeCoverage
            || localeCoverage.Count != RequiredShippingLocales.Length
            || !localeCoverage.Select(static pair => pair.Key).ToHashSet(StringComparer.Ordinal).SetEquals(RequiredShippingLocales))
        {
            return false;
        }

        return RequiredShippingLocales.All(locale =>
            ValidatePassingCoverage(localeCoverage[locale], RequiredLocalizationDomains));
    }

    private static bool ValidateLocaleSummary(JsonNode? node, long defaultKeyCount)
    {
        if (node is not JsonArray rows || rows.Count != RequiredShippingLocales.Length)
        {
            return false;
        }

        for (int index = 0; index < RequiredShippingLocales.Length; index++)
        {
            if (rows[index] is not JsonObject row
                || !HasExactKeys(row, LocaleSummaryKeys)
                || !string.Equals(GetString(row["locale"]), RequiredShippingLocales[index], StringComparison.Ordinal)
                || !TryGetInt64(row["untranslatedKeyCount"], out long untranslated)
                || untranslated != 0
                || !TryGetInt64(row["overrideCount"], out long overrideCount)
                || overrideCount < defaultKeyCount
                || !TryGetInt64(row["minimumOverrideCount"], out long minimumOverrideCount)
                || minimumOverrideCount < 0
                || overrideCount < minimumOverrideCount
                || row["missingReleaseSeedKeys"] is not JsonArray { Count: 0 }
                || !TryGetBoolean(row["legacyXmlPresent"], out bool legacyXmlPresent)
                || !legacyXmlPresent
                || !TryGetBoolean(row["legacyDataXmlPresent"], out bool legacyDataXmlPresent)
                || !legacyDataXmlPresent)
            {
                return false;
            }
        }

        return true;
    }

    private static bool ValidateFlagshipReadiness(
        JsonObject snapshot,
        out DateTimeOffset generatedAt,
        out string status,
        out bool desktopReady,
        out IReadOnlyList<string> coverageGapKeys,
        out IReadOnlyList<string> launchBlockers,
        out string snapshotSha256,
        out string reason)
    {
        generatedAt = default;
        status = string.Empty;
        desktopReady = false;
        coverageGapKeys = [];
        launchBlockers = [];
        snapshotSha256 = string.Empty;
        reason = "releaseProof flagshipReadiness is invalid";

        string contractName = GetString(snapshot["contractName"]) ?? string.Empty;
        status = GetString(snapshot["status"]) ?? string.Empty;
        string generatedAtText = GetString(snapshot["generatedAt"]) ?? string.Empty;
        string reasonText = GetString(snapshot["reason"]) ?? string.Empty;
        string sourceSha256 = GetString(snapshot["sourceSha256"]) ?? string.Empty;

        if (!HasExactKeys(snapshot, FlagshipReadinessKeys)
            || !string.Equals(contractName, FlagshipReadinessContractName, StringComparison.Ordinal)
            || !TryGetCanonicalUtcTimestamp(snapshot["generatedAt"], out generatedAt)
            || status is not ("pass" or "fail")
            || !ReadCanonicalFlagshipCoverageGapKeys(snapshot["coverageGapKeys"], out coverageGapKeys)
            || !ReadCanonicalFlagshipLaunchBlockers(snapshot["launchBlockers"], out launchBlockers)
            || !TryGetBoolean(snapshot["desktopClientReady"], out desktopReady)
            || desktopReady != (status == "pass" && coverageGapKeys.Count == 0 && launchBlockers.Count == 0)
            || !ValidateFlagshipReadinessPublicText(reasonText, FlagshipReadinessReasonMaxLength)
            || !Sha256Regex().IsMatch(sourceSha256)
            || !Sha256Regex().IsMatch(snapshotSha256 = GetString(snapshot["snapshotSha256"]) ?? string.Empty))
        {
            return false;
        }

        string expectedDigest = "sha256:" + Convert.ToHexString(
            SHA256.HashData(CanonicalFlagshipReadinessSnapshotBytes(
                contractName,
                coverageGapKeys,
                desktopReady,
                generatedAtText,
                launchBlockers,
                reasonText,
                sourceSha256,
                status)))
            .ToLowerInvariant();
        if (!string.Equals(snapshotSha256, expectedDigest, StringComparison.Ordinal))
        {
            reason = "releaseProof flagshipReadiness snapshot digest does not match its canonical fields";
            return false;
        }

        reason = string.Empty;
        return true;
    }

    private static bool ReadCanonicalFlagshipCoverageGapKeys(
        JsonNode? node,
        out IReadOnlyList<string> values)
    {
        values = [];
        if (node is not JsonArray array || array.Count > FlagshipReadinessMaxCoverageGaps)
        {
            return false;
        }

        List<string> result = [];
        foreach (JsonNode? item in array)
        {
            string? value = GetString(item);
            if (string.IsNullOrWhiteSpace(value)
                || value != value.Trim()
                || !FlagshipReadinessCoverageGapKeyRegex().IsMatch(value))
            {
                return false;
            }

            result.Add(value);
        }

        for (int index = 1; index < result.Count; index++)
        {
            if (StringComparer.Ordinal.Compare(result[index - 1], result[index]) >= 0)
            {
                return false;
            }
        }

        values = result;
        return true;
    }

    private static bool ReadCanonicalFlagshipLaunchBlockers(
        JsonNode? node,
        out IReadOnlyList<string> values)
    {
        values = [];
        if (node is not JsonArray array || array.Count > FlagshipReadinessMaxBlockers)
        {
            return false;
        }

        List<string> result = [];
        foreach (JsonNode? item in array)
        {
            string? value = GetString(item);
            if (value is null
                || !ValidateFlagshipReadinessPublicText(value, FlagshipReadinessBlockerMaxLength))
            {
                return false;
            }

            result.Add(value);
        }

        for (int index = 1; index < result.Count; index++)
        {
            if (ComparePythonUnicodeCodePoints(result[index - 1], result[index]) >= 0)
            {
                return false;
            }
        }

        values = result;
        return true;
    }

    private static bool ValidateFlagshipReadinessPublicText(string value, int maximumLength)
        => HasCanonicalPythonTrimAndBoundedUnicodeLength(value, maximumLength)
           && !FlagshipReadinessEmailRegex().IsMatch(value)
           && !FlagshipReadinessSensitivePathRegex().IsMatch(value);

    private static bool HasCanonicalPythonTrimAndBoundedUnicodeLength(string value, int maximumLength)
    {
        if (value.Length == 0)
        {
            return false;
        }

        ReadOnlySpan<char> remaining = value.AsSpan();
        Rune first = default;
        Rune last = default;
        int scalarCount = 0;
        while (!remaining.IsEmpty)
        {
            if (Rune.DecodeFromUtf16(remaining, out Rune current, out int consumed) != OperationStatus.Done)
            {
                return false;
            }

            if (scalarCount == 0)
            {
                first = current;
            }

            last = current;
            scalarCount++;
            if (scalarCount > maximumLength)
            {
                return false;
            }

            remaining = remaining[consumed..];
        }

        return !IsPythonWhitespace(first.Value) && !IsPythonWhitespace(last.Value);
    }

    private static bool IsPythonWhitespace(int scalar)
        => scalar is >= 0x0009 and <= 0x000D
            or >= 0x001C and <= 0x0020
            or 0x0085
            or 0x00A0
            or 0x1680
            or >= 0x2000 and <= 0x200A
            or 0x2028
            or 0x2029
            or 0x202F
            or 0x205F
            or 0x3000;

    private static int ComparePythonUnicodeCodePoints(string left, string right)
    {
        ReadOnlySpan<char> leftRemaining = left.AsSpan();
        ReadOnlySpan<char> rightRemaining = right.AsSpan();
        while (!leftRemaining.IsEmpty && !rightRemaining.IsEmpty)
        {
            Rune.DecodeFromUtf16(leftRemaining, out Rune leftRune, out int leftConsumed);
            Rune.DecodeFromUtf16(rightRemaining, out Rune rightRune, out int rightConsumed);
            int comparison = leftRune.Value.CompareTo(rightRune.Value);
            if (comparison != 0)
            {
                return comparison;
            }

            leftRemaining = leftRemaining[leftConsumed..];
            rightRemaining = rightRemaining[rightConsumed..];
        }

        return leftRemaining.IsEmpty
            ? rightRemaining.IsEmpty ? 0 : -1
            : 1;
    }

    private static byte[] CanonicalFlagshipReadinessSnapshotBytes(
        string contractName,
        IReadOnlyList<string> coverageGapKeys,
        bool desktopClientReady,
        string generatedAt,
        IReadOnlyList<string> launchBlockers,
        string reason,
        string sourceSha256,
        string status)
    {
        StringBuilder canonical = new();
        canonical.Append("{\"contractName\":");
        AppendPythonJsonString(canonical, contractName);
        canonical.Append(",\"coverageGapKeys\":");
        AppendPythonJsonStringArray(canonical, coverageGapKeys);
        canonical.Append(",\"desktopClientReady\":")
            .Append(desktopClientReady ? "true" : "false");
        canonical.Append(",\"generatedAt\":");
        AppendPythonJsonString(canonical, generatedAt);
        canonical.Append(",\"launchBlockers\":");
        AppendPythonJsonStringArray(canonical, launchBlockers);
        canonical.Append(",\"reason\":");
        AppendPythonJsonString(canonical, reason);
        canonical.Append(",\"sourceSha256\":");
        AppendPythonJsonString(canonical, sourceSha256);
        canonical.Append(",\"status\":");
        AppendPythonJsonString(canonical, status);
        canonical.Append('}');
        return Encoding.UTF8.GetBytes(canonical.ToString());
    }

    private static void AppendPythonJsonStringArray(StringBuilder target, IReadOnlyList<string> values)
    {
        target.Append('[');
        for (int index = 0; index < values.Count; index++)
        {
            if (index > 0)
            {
                target.Append(',');
            }

            AppendPythonJsonString(target, values[index]);
        }

        target.Append(']');
    }

    private static void AppendPythonJsonString(StringBuilder target, string value)
    {
        target.Append('"');
        foreach (char character in value)
        {
            switch (character)
            {
                case '"':
                    target.Append("\\\"");
                    break;
                case '\\':
                    target.Append("\\\\");
                    break;
                case '\b':
                    target.Append("\\b");
                    break;
                case '\f':
                    target.Append("\\f");
                    break;
                case '\n':
                    target.Append("\\n");
                    break;
                case '\r':
                    target.Append("\\r");
                    break;
                case '\t':
                    target.Append("\\t");
                    break;
                default:
                    if (character < 0x20)
                    {
                        target.Append("\\u")
                            .Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        target.Append(character);
                    }

                    break;
            }
        }

        target.Append('"');
    }

    private static bool ReadExactStringArray(
        JsonNode? node,
        IReadOnlyList<string> expected,
        out IReadOnlyList<string> values)
    {
        values = [];
        if (!ReadCanonicalStringList(node, out values))
        {
            return false;
        }

        return values.SequenceEqual(expected, StringComparer.Ordinal);
    }

    private static bool ReadCanonicalStringList(JsonNode? node, out IReadOnlyList<string> values)
    {
        values = [];
        if (node is not JsonArray array)
        {
            return false;
        }

        List<string> result = [];
        foreach (JsonNode? item in array)
        {
            string? value = GetString(item);
            if (string.IsNullOrWhiteSpace(value) || value != value.Trim())
            {
                return false;
            }

            result.Add(value);
        }

        if (result.Distinct(StringComparer.Ordinal).Count() != result.Count)
        {
            return false;
        }

        values = result;
        return true;
    }

    private static bool HasExactKeys(JsonObject value, HashSet<string> expected)
        => value.Count == expected.Count
           && value.Select(static pair => pair.Key).ToHashSet(StringComparer.Ordinal).SetEquals(expected);

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
        return node is JsonValue jsonValue
               && (jsonValue.TryGetValue(out value)
                   || (jsonValue.TryGetValue(out int intValue) && (value = intValue) == intValue));
    }

    private static bool TryGetBoolean(JsonNode? node, out bool value)
    {
        value = false;
        return node is JsonValue jsonValue && jsonValue.TryGetValue(out value);
    }

    private static string? GetString(JsonNode? node)
        => node is JsonValue value && value.TryGetValue<string>(out string? text)
            ? text
            : null;

    private static string NormalizeToken(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim().ToLowerInvariant();

    private static ReleaseProofTrustEvaluation Invalid(string reason)
        => new(false, reason, null, null, null, string.Empty, false, [], [], null);

    [GeneratedRegex("^/downloads/install/[a-z0-9][a-z0-9-]*$", RegexOptions.CultureInvariant)]
    private static partial Regex ArtifactInstallRouteRegex();

    [GeneratedRegex("^sha256:[0-9a-f]{64}$", RegexOptions.CultureInvariant)]
    private static partial Regex Sha256Regex();

    [GeneratedRegex("^[a-z0-9][a-z0-9_.:-]*$", RegexOptions.CultureInvariant)]
    private static partial Regex FlagshipReadinessCoverageGapKeyRegex();

    [GeneratedRegex(
        "(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}(?![A-Za-z0-9_%+-])",
        RegexOptions.CultureInvariant)]
    private static partial Regex FlagshipReadinessEmailRegex();

    [GeneratedRegex(
        "(?<![A-Za-z0-9:])(?:/(?:docker|users|home|root|tmp|var|etc|opt|workspace)(?:/[^\\s,;)]*)?|[A-Za-z]:[\\\\/][^\\s,;)]*)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex FlagshipReadinessSensitivePathRegex();
}
