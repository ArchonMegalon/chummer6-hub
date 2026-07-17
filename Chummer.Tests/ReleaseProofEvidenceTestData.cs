using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Tests;

internal static class ReleaseProofEvidenceTestData
{
    internal const long MaximumAgeSeconds = 7 * 24 * 60 * 60;

    internal static JsonObject CreateReleaseProof(
        DateTimeOffset generatedAt,
        IEnumerable<string>? installerRouteExtensions = null,
        string readinessStatus = "pass",
        bool desktopClientReady = true,
        IReadOnlyList<string>? coverageGapKeys = null,
        IReadOnlyList<string>? launchBlockers = null)
    {
        JsonObject flagshipReadiness = CreateFlagshipReadiness(
            generatedAt,
            readinessStatus,
            desktopClientReady,
            coverageGapKeys ?? [],
            launchBlockers ?? []);
        JsonArray proofRoutes = new(
            "/downloads/install/avalonia-linux-x64-installer",
            "/home/access",
            "/home/work",
            "/account/access",
            "/account/work",
            "/account/support",
            "/contact",
            "/downloads");
        foreach (string route in (installerRouteExtensions ?? []).Order(StringComparer.Ordinal))
        {
            if (!proofRoutes.Any(node => string.Equals(node?.GetValue<string>(), route, StringComparison.Ordinal)))
            {
                proofRoutes.Add(route);
            }
        }

        return new JsonObject
        {
            ["status"] = "passed",
            ["generatedAt"] = FormatUtc(generatedAt),
            ["baseUrl"] = "https://chummer.run",
            ["journeysPassed"] = new JsonArray(
                "install_claim_restore_continue",
                "build_explain_publish",
                "campaign_session_recover_recap",
                "report_cluster_release_notify",
                "organize_community_and_close_loop"),
            ["proofRoutes"] = proofRoutes,
            ["uiLocalizationReleaseGate"] = CreateLocalizationGate(generatedAt),
            ["flagshipReadiness"] = flagshipReadiness
        };
    }

    internal static JsonObject CreateFreshnessFacts(
        JsonObject releaseProof,
        DateTimeOffset publishedAt,
        long? declaredAgeSeconds = null,
        long maxAgeSeconds = MaximumAgeSeconds)
    {
        DateTimeOffset proofGeneratedAt = DateTimeOffset.Parse(
            releaseProof["generatedAt"]!.GetValue<string>());
        JsonObject localization = releaseProof["uiLocalizationReleaseGate"]!.AsObject();
        DateTimeOffset localizationGeneratedAt = DateTimeOffset.Parse(
            localization["generatedAt"]!.GetValue<string>());
        JsonObject readiness = releaseProof["flagshipReadiness"]!.AsObject();
        DateTimeOffset readinessGeneratedAt = DateTimeOffset.Parse(
            readiness["generatedAt"]!.GetValue<string>());
        long proofAge = declaredAgeSeconds ?? AgeSeconds(publishedAt, proofGeneratedAt);
        long localizationAge = declaredAgeSeconds ?? AgeSeconds(publishedAt, localizationGeneratedAt);
        long readinessAge = declaredAgeSeconds ?? AgeSeconds(publishedAt, readinessGeneratedAt);

        return new JsonObject
        {
            ["status"] = "fresh",
            ["releaseProofGeneratedAt"] = FormatUtc(proofGeneratedAt),
            ["releaseProofAgeSeconds"] = proofAge,
            ["releaseProofMaxAgeSeconds"] = maxAgeSeconds,
            ["uiLocalizationGeneratedAt"] = FormatUtc(localizationGeneratedAt),
            ["uiLocalizationAgeSeconds"] = localizationAge,
            ["uiLocalizationMaxAgeSeconds"] = maxAgeSeconds,
            ["flagshipReadinessGeneratedAt"] = FormatUtc(readinessGeneratedAt),
            ["flagshipReadinessAgeSeconds"] = readinessAge,
            ["flagshipReadinessMaxAgeSeconds"] = maxAgeSeconds,
            ["flagshipReadinessStatus"] = readiness["status"]!.GetValue<string>(),
            ["flagshipReadinessCoverageGapKeys"] = readiness["coverageGapKeys"]!.DeepClone(),
            ["flagshipDesktopClientReady"] = readiness["desktopClientReady"]!.GetValue<bool>(),
            ["flagshipReadinessSnapshotSha256"] = readiness["snapshotSha256"]!.GetValue<string>()
        };
    }

    private static JsonObject CreateLocalizationGate(DateTimeOffset generatedAt)
    {
        string[] locales = ["en-us", "de-de", "fr-fr", "ja-jp", "pt-br", "zh-cn"];
        string[] domains =
            ["app_chrome", "install_update_support", "explain_receipts", "data_rules_names", "generated_artifacts"];
        JsonObject domainCoverage = [];
        foreach (string domain in domains)
        {
            domainCoverage[domain] = "pass";
        }

        JsonObject localeDomainCoverage = [];
        JsonArray localeSummary = [];
        foreach (string locale in locales)
        {
            JsonObject localeCoverage = [];
            foreach (string domain in domains)
            {
                localeCoverage[domain] = "pass";
            }

            localeDomainCoverage[locale] = localeCoverage;
            localeSummary.Add(new JsonObject
            {
                ["locale"] = locale,
                ["untranslatedKeyCount"] = 0,
                ["overrideCount"] = 441,
                ["minimumOverrideCount"] = locale == "en-us" ? 441 : 40,
                ["missingReleaseSeedKeys"] = new JsonArray(),
                ["legacyXmlPresent"] = true,
                ["legacyDataXmlPresent"] = true
            });
        }

        return new JsonObject
        {
            ["status"] = "pass",
            ["generatedAt"] = FormatUtc(generatedAt),
            ["defaultKeyCount"] = 441,
            ["explicitFallbackRuntime"] = "pass",
            ["signoffSmokeRunnerStatus"] = "pass",
            ["shippingLocales"] = new JsonArray(locales.Select(static locale => JsonValue.Create(locale)).ToArray()),
            ["acceptanceGates"] = new JsonArray(
                "pseudo_localization",
                "missing_key_fail_fast",
                "top_surface_overflow_checks",
                "locale_smoke_first_launch",
                "locale_smoke_settings",
                "locale_smoke_explain",
                "locale_smoke_updater",
                "locale_smoke_support",
                "non_english_generated_artifact_smoke"),
            ["domainCoverage"] = domainCoverage,
            ["localeDomainCoverage"] = localeDomainCoverage,
            ["blockingFindingsCount"] = 0,
            ["blockingFindings"] = new JsonArray(),
            ["translationBacklogFindingsCount"] = 0,
            ["translationBacklogFindings"] = new JsonArray(),
            ["localeSummary"] = localeSummary
        };
    }

    private static JsonObject CreateFlagshipReadiness(
        DateTimeOffset generatedAt,
        string status,
        bool desktopClientReady,
        IReadOnlyList<string> coverageGapKeys,
        IReadOnlyList<string> launchBlockers)
    {
        const string sourceSha256 =
            "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        string reason = status.Equals("pass", StringComparison.OrdinalIgnoreCase)
            ? "Flagship product readiness proof is green."
            : "Flagship product readiness remains blocked.";
        JsonObject digestMaterial = new()
        {
            ["contractName"] = "chummer.flagship_product_readiness_gate.v1",
            ["coverageGapKeys"] = new JsonArray(coverageGapKeys.Select(static key => JsonValue.Create(key)).ToArray()),
            ["desktopClientReady"] = desktopClientReady,
            ["generatedAt"] = FormatUtc(generatedAt),
            ["launchBlockers"] = new JsonArray(launchBlockers.Select(static blocker => JsonValue.Create(blocker)).ToArray()),
            ["reason"] = reason,
            ["sourceSha256"] = sourceSha256,
            ["status"] = status
        };
        string canonical = digestMaterial.ToJsonString(new JsonSerializerOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            WriteIndented = false
        });
        string snapshotSha256 = "sha256:" + Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
        JsonObject result = digestMaterial.DeepClone().AsObject();
        result["snapshotSha256"] = snapshotSha256;
        return result;
    }

    private static long AgeSeconds(DateTimeOffset later, DateTimeOffset earlier)
        => later <= earlier ? 0 : checked((long)Math.Floor((later - earlier).TotalSeconds));

    private static string FormatUtc(DateTimeOffset value)
        => value.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
}
