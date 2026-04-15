using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed record ArtifactFactoryJobLaunchRequest(
    string Family,
    string RequestedBy,
    IReadOnlyList<ApprovedArtifactSourcePack> SourcePacks,
    IReadOnlyList<string>? RequestedFormats = null,
    string? Audience = null,
    string? Locale = null);

public sealed record ApprovedArtifactSourcePack(
    string SourcePackId,
    string SourcePackKind,
    string ApprovalState,
    string ProvenanceRef,
    IReadOnlyList<string>? EvidenceRefs = null,
    string? ReleaseArtifactId = null,
    string? SupportCaseId = null,
    string? PublicationId = null,
    string? PublicShelfRef = null);

public sealed record ArtifactFactoryJobLaunchResult(
    string JobId,
    string State,
    string Family,
    string RecipeId,
    string RecipeVersion,
    string RequestedBy,
    string Audience,
    string Locale,
    DateTimeOffset QueuedAtUtc,
    IReadOnlyList<string> SourcePackIds,
    IReadOnlyList<string> OutputFormats,
    IReadOnlyList<string> RequiredReceiptRefs,
    IReadOnlyList<string> PublicProofShelfRefs,
    IReadOnlyList<ArtifactFactoryOutputBinding> OutputBindings,
    ArtifactFactoryMediaRequest MediaFactoryRequest);

public sealed record ArtifactFactoryMediaRequest(
    string ContractName,
    string RecipeId,
    string RecipeVersion,
    IReadOnlyList<ArtifactFactoryMediaSourcePack> ApprovedSourcePacks,
    IReadOnlyList<string> OutputFormats,
    IReadOnlyList<string> RequiredReceiptRefs,
    IReadOnlyList<string> PublicProofShelfRefs,
    IReadOnlyList<ArtifactFactoryOutputBinding> OutputBindings);

public sealed record ArtifactFactoryOutputBinding(
    string Format,
    string PublicRef,
    string ReceiptRef,
    string? ReleaseArtifactId,
    string? SupportCaseId,
    string? PublicationId);

public sealed record ArtifactFactoryMediaSourcePack(
    string SourcePackId,
    string SourcePackKind,
    string ProvenanceRef,
    IReadOnlyList<string> EvidenceRefs,
    string? ReleaseArtifactId,
    string? SupportCaseId,
    string? PublicationId,
    string? PublicShelfRef);

public sealed class ArtifactFactoryOrchestrationService
{
    private const string ContractName = "chummer.run.artifact_factory.recipe_job.v1";
    private const string RecipeVersion = "2026-04-15";
    private static readonly IReadOnlySet<string> ProviderSpecificRefPrefixes =
        new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "provider",
            "vendor",
            "one_off",
            "one-off",
            "heygen",
            "elevenlabs",
            "runway",
            "replicate",
            "veo"
        };

    private static readonly JsonSerializerOptions HashJsonOptions = new(JsonSerializerDefaults.Web);
    private static readonly IReadOnlyDictionary<string, ArtifactFactoryRecipe> Recipes =
        new Dictionary<string, ArtifactFactoryRecipe>(StringComparer.OrdinalIgnoreCase)
        {
            ["release"] = new(
                RecipeId: "release-proof-shelf-bundle",
                AllowedSourceKinds: ["release", "release_evidence", "desktop_release", "install_receipt"],
                DefaultFormats: ["preview_card", "caption", "packet", "short_video", "audio"],
                AllowedFormats: ["preview_card", "caption", "packet", "short_video", "audio"],
                RequiredReceiptPrefixes: ["release", "promotion", "public-shelf"],
                RequiredAnchorDescription: "a release artifact id or public proof shelf ref"),
            ["fix"] = new(
                RecipeId: "fix-followthrough-bundle",
                AllowedSourceKinds: ["fix_receipt", "support_case", "install_receipt", "release"],
                DefaultFormats: ["preview_card", "caption", "packet", "audio"],
                AllowedFormats: ["preview_card", "caption", "packet", "short_video", "audio"],
                RequiredReceiptPrefixes: ["fix", "install", "support"],
                RequiredAnchorDescription: "a support case id or release artifact id"),
            ["support"] = new(
                RecipeId: "support-case-proof-packet",
                AllowedSourceKinds: ["support_case", "crash_report", "install_receipt", "release"],
                DefaultFormats: ["preview_card", "caption", "packet", "audio"],
                AllowedFormats: ["preview_card", "caption", "packet", "short_video", "audio"],
                RequiredReceiptPrefixes: ["support", "privacy", "install"],
                RequiredAnchorDescription: "a support case id"),
            ["publication"] = new(
                RecipeId: "publication-proof-shelf-bundle",
                AllowedSourceKinds: ["publication", "creator_publication", "campaign_recap", "runtime_bundle"],
                DefaultFormats: ["preview_card", "caption", "packet", "short_video", "audio"],
                AllowedFormats: ["preview_card", "caption", "packet", "short_video", "audio"],
                RequiredReceiptPrefixes: ["publication", "moderation", "public-shelf"],
                RequiredAnchorDescription: "a publication id or public proof shelf ref")
        };

    public ArtifactFactoryJobLaunchResult LaunchJob(ArtifactFactoryJobLaunchRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (string.IsNullOrWhiteSpace(request.Family))
        {
            throw new InvalidDataException("artifact job family is required.");
        }

        string family = NormalizeToken(request.Family);
        if (!Recipes.TryGetValue(family, out ArtifactFactoryRecipe? recipe))
        {
            throw new InvalidDataException($"artifact job family '{request.Family}' is not supported.");
        }

        if (string.IsNullOrWhiteSpace(request.RequestedBy))
        {
            throw new InvalidDataException("requestedBy is required.");
        }

        if (request.SourcePacks is null || request.SourcePacks.Count == 0)
        {
            throw new InvalidDataException("at least one approved source pack is required.");
        }

        List<ArtifactFactoryMediaSourcePack> sourcePacks = new(request.SourcePacks.Count);
        List<string> requiredReceiptRefs = new();
        List<string> publicProofShelfRefs = new();
        HashSet<string> sourcePackIds = new(StringComparer.OrdinalIgnoreCase);
        foreach (ApprovedArtifactSourcePack sourcePack in request.SourcePacks)
        {
            ValidateSourcePack(sourcePack, family, recipe);
            string normalizedSourcePackId = sourcePack.SourcePackId.Trim();
            if (!sourcePackIds.Add(normalizedSourcePackId))
            {
                throw new InvalidDataException($"duplicate source pack id '{normalizedSourcePackId}' is not allowed.");
            }

            IReadOnlyList<string> evidenceRefs = NormalizeEvidenceRefs(sourcePack, family);
            sourcePacks.Add(new ArtifactFactoryMediaSourcePack(
                SourcePackId: normalizedSourcePackId,
                SourcePackKind: NormalizeToken(sourcePack.SourcePackKind),
                ProvenanceRef: sourcePack.ProvenanceRef.Trim(),
                EvidenceRefs: evidenceRefs,
                ReleaseArtifactId: NormalizeOptional(sourcePack.ReleaseArtifactId),
                SupportCaseId: NormalizeOptional(sourcePack.SupportCaseId),
                PublicationId: NormalizeOptional(sourcePack.PublicationId),
                PublicShelfRef: NormalizeOptional(sourcePack.PublicShelfRef)));

            foreach (string evidenceRef in evidenceRefs)
            {
                requiredReceiptRefs.Add(evidenceRef);
            }

            if (!string.IsNullOrWhiteSpace(sourcePack.PublicShelfRef))
            {
                publicProofShelfRefs.Add(sourcePack.PublicShelfRef.Trim());
            }
            else if (!string.IsNullOrWhiteSpace(sourcePack.ReleaseArtifactId))
            {
                publicProofShelfRefs.Add($"/downloads/install/{Uri.EscapeDataString(sourcePack.ReleaseArtifactId.Trim())}");
            }
            else if (!string.IsNullOrWhiteSpace(sourcePack.SupportCaseId))
            {
                publicProofShelfRefs.Add($"/account/support/{Uri.EscapeDataString(sourcePack.SupportCaseId.Trim())}");
            }
            else if (!string.IsNullOrWhiteSpace(sourcePack.PublicationId))
            {
                publicProofShelfRefs.Add($"/artifacts/publications/{Uri.EscapeDataString(sourcePack.PublicationId.Trim())}");
            }
        }

        ValidateRecipeAnchors(family, request.SourcePacks, recipe);

        string[] missingReceiptPrefixes = recipe.RequiredReceiptPrefixes
            .Where(prefix => !requiredReceiptRefs.Any(receipt => receipt.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)))
            .ToArray();
        if (missingReceiptPrefixes.Length > 0)
        {
            throw new InvalidDataException(
                $"recipe {recipe.RecipeId} requires approved source-pack receipt evidence for: {string.Join(", ", missingReceiptPrefixes)}.");
        }

        string[] outputFormats = NormalizeOutputFormats(request.RequestedFormats, recipe);
        string audience = NormalizeOptional(request.Audience) ?? "public-proof-shelf";
        string locale = NormalizeOptional(request.Locale) ?? "en-US";
        string jobId = BuildJobId(family, sourcePacks, outputFormats, audience, locale);
        string[] receiptRefs = requiredReceiptRefs.Distinct(StringComparer.OrdinalIgnoreCase).Order(StringComparer.OrdinalIgnoreCase).ToArray();
        ArtifactFactoryOutputBinding[] outputBindings = BuildOutputBindings(family, jobId, sourcePacks, outputFormats);
        publicProofShelfRefs.AddRange(BuildOutputShelfRefs(outputBindings));
        string[] proofShelfRefs = publicProofShelfRefs.Distinct(StringComparer.OrdinalIgnoreCase).Order(StringComparer.OrdinalIgnoreCase).ToArray();

        return new ArtifactFactoryJobLaunchResult(
            JobId: jobId,
            State: "queued",
            Family: family,
            RecipeId: recipe.RecipeId,
            RecipeVersion: RecipeVersion,
            RequestedBy: request.RequestedBy.Trim(),
            Audience: audience,
            Locale: locale,
            QueuedAtUtc: DateTimeOffset.UtcNow,
            SourcePackIds: sourcePackIds.Order(StringComparer.OrdinalIgnoreCase).ToArray(),
            OutputFormats: outputFormats,
            RequiredReceiptRefs: receiptRefs,
            PublicProofShelfRefs: proofShelfRefs,
            OutputBindings: outputBindings,
            MediaFactoryRequest: new ArtifactFactoryMediaRequest(
                ContractName: ContractName,
                RecipeId: recipe.RecipeId,
                RecipeVersion: RecipeVersion,
                ApprovedSourcePacks: sourcePacks,
                OutputFormats: outputFormats,
                RequiredReceiptRefs: receiptRefs,
                PublicProofShelfRefs: proofShelfRefs,
                OutputBindings: outputBindings));
    }

    private static void ValidateSourcePack(ApprovedArtifactSourcePack sourcePack, string family, ArtifactFactoryRecipe recipe)
    {
        if (string.IsNullOrWhiteSpace(sourcePack.SourcePackId))
        {
            throw new InvalidDataException("sourcePackId is required for every source pack.");
        }

        if (string.IsNullOrWhiteSpace(sourcePack.SourcePackKind))
        {
            throw new InvalidDataException($"source pack '{sourcePack.SourcePackId}' is missing sourcePackKind.");
        }

        string sourcePackKind = NormalizeToken(sourcePack.SourcePackKind);
        if (!recipe.AllowedSourceKinds.Contains(sourcePackKind, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"source pack '{sourcePack.SourcePackId}' has unsupported kind '{sourcePack.SourcePackKind}' for recipe {recipe.RecipeId}.");
        }

        if (!string.Equals(sourcePack.ApprovalState?.Trim(), "approved", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"source pack '{sourcePack.SourcePackId}' is not approved.");
        }

        if (string.IsNullOrWhiteSpace(sourcePack.ProvenanceRef))
        {
            throw new InvalidDataException($"source pack '{sourcePack.SourcePackId}' is missing provenanceRef.");
        }

        RejectProviderSpecificRef(sourcePack.SourcePackId, sourcePack.ProvenanceRef, "provenanceRef");
        if (!string.IsNullOrWhiteSpace(sourcePack.PublicShelfRef))
        {
            RejectProviderSpecificRef(sourcePack.SourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");
            RejectNonLocalPublicShelfRef(sourcePack.SourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");
            RejectPublicShelfRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, sourcePack.PublicShelfRef, "publicShelfRef");
        }

        RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.ReleaseArtifactId, "releaseArtifactId");
        RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.SupportCaseId, "supportCaseId");
        RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.PublicationId, "publicationId");
    }

    private static void ValidateRecipeAnchors(
        string family,
        IReadOnlyList<ApprovedArtifactSourcePack> sourcePacks,
        ArtifactFactoryRecipe recipe)
    {
        bool hasRequiredAnchor = family switch
        {
            "release" => sourcePacks.Any(static pack =>
                !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId)
                || !string.IsNullOrWhiteSpace(pack.PublicShelfRef)),
            "fix" => sourcePacks.Any(static pack =>
                !string.IsNullOrWhiteSpace(pack.SupportCaseId)
                || !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId)),
            "support" => sourcePacks.Any(static pack =>
                !string.IsNullOrWhiteSpace(pack.SupportCaseId)),
            "publication" => sourcePacks.Any(static pack =>
                !string.IsNullOrWhiteSpace(pack.PublicationId)
                || !string.IsNullOrWhiteSpace(pack.PublicShelfRef)),
            _ => false
        };

        if (!hasRequiredAnchor)
        {
            throw new InvalidDataException($"recipe {recipe.RecipeId} requires {recipe.RequiredAnchorDescription} from an approved source pack.");
        }
    }

    private static IReadOnlyList<string> NormalizeEvidenceRefs(ApprovedArtifactSourcePack sourcePack, string family)
    {
        string[] evidenceRefs = (sourcePack.EvidenceRefs ?? Array.Empty<string>())
            .Select(static item => item.Trim())
            .Where(static item => item.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        foreach (string evidenceRef in evidenceRefs)
        {
            RejectProviderSpecificRef(sourcePack.SourcePackId, evidenceRef, "evidenceRef");
            RejectNonLocalPublicShelfEvidenceRef(sourcePack.SourcePackId, evidenceRef);
            RejectPublicShelfEvidenceRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, evidenceRef);
        }

        return evidenceRefs.Length > 0
            ? evidenceRefs
            : [$"provenance:{sourcePack.ProvenanceRef.Trim()}"];
    }

    private static void RejectProviderSpecificRef(string sourcePackId, string value, string fieldName)
    {
        string normalized = value.Trim();
        int separatorIndex = FirstRefPrefixSeparatorIndex(normalized);
        string prefix = separatorIndex >= 0
            ? normalized[..separatorIndex].Trim()
            : string.Empty;
        if (ProviderSpecificRefPrefixes.Contains(prefix))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has provider-specific {fieldName} '{value}'; artifact factory jobs must launch from approved source-pack receipts instead of one-off provider flows.");
        }
    }

    private static int FirstRefPrefixSeparatorIndex(string normalized)
    {
        if (normalized.StartsWith("/", StringComparison.Ordinal))
        {
            return -1;
        }

        int colonIndex = normalized.IndexOf(':');
        int slashIndex = normalized.IndexOf('/');
        if (colonIndex < 0)
        {
            return slashIndex;
        }

        if (slashIndex < 0)
        {
            return colonIndex;
        }

        return Math.Min(colonIndex, slashIndex);
    }

    private static void RejectNonLocalPublicShelfEvidenceRef(string sourcePackId, string evidenceRef)
    {
        const string publicShelfPrefix = "public-shelf:";
        if (!evidenceRef.StartsWith(publicShelfPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        string publicShelfRef = evidenceRef[publicShelfPrefix.Length..];
        RejectNonLocalPublicShelfRef(sourcePackId, publicShelfRef, "evidenceRef");
    }

    private static void RejectPublicShelfEvidenceRefOutsideRecipeRoutes(string sourcePackId, string family, string evidenceRef)
    {
        const string publicShelfPrefix = "public-shelf:";
        if (!evidenceRef.StartsWith(publicShelfPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        string publicShelfRef = evidenceRef[publicShelfPrefix.Length..];
        RejectPublicShelfRefOutsideRecipeRoutes(sourcePackId, family, publicShelfRef, "evidenceRef");
    }

    private static void RejectNonLocalPublicShelfRef(string sourcePackId, string value, string fieldName)
    {
        string publicShelfRef = value.Trim();
        if (!publicShelfRef.StartsWith("/", StringComparison.Ordinal) || publicShelfRef.StartsWith("//", StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has non-local public proof shelf {fieldName} '{value}'; artifact factory output refs must stay on the Chummer public proof shelf.");
        }

        RejectUnsafePublicShelfRef(sourcePackId, publicShelfRef, fieldName);
    }

    private static void RejectPublicShelfRefOutsideRecipeRoutes(string sourcePackId, string family, string value, string fieldName)
    {
        string publicShelfRef = value.Trim();
        string[] allowedPrefixes = family switch
        {
            "release" => ["/downloads/install/", "/artifacts/release-bundles/"],
            "fix" => ["/account/support/", "/account/fix-followthrough/", "/downloads/install/", "/artifacts/release-bundles/"],
            "support" => ["/account/support/", "/account/support-packets/"],
            "publication" => ["/artifacts/publications/"],
            _ => []
        };

        if (allowedPrefixes.Length == 0 || !allowedPrefixes.Any(prefix => publicShelfRef.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has public proof shelf {fieldName} '{value}' outside recipe {family} shelf routes; artifact factory bundle refs must stay on approved release, support, fix, or publication shelves.");
        }
    }

    private static void RejectUnsafePublicShelfRef(string sourcePackId, string publicShelfRef, string fieldName)
    {
        if (publicShelfRef.Contains('?', StringComparison.Ordinal) || publicShelfRef.Contains('#', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe public proof shelf {fieldName} '{publicShelfRef}'; artifact factory bundle refs must be stable shelf paths without query strings or fragments.");
        }

        foreach (string segment in publicShelfRef.Split('/', StringSplitOptions.RemoveEmptyEntries))
        {
            string decodedSegment = Uri.UnescapeDataString(segment);
            if (decodedSegment is "." or ".." || decodedSegment.Contains('/', StringComparison.Ordinal) || decodedSegment.Contains('\\', StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"source pack '{sourcePackId}' has unsafe public proof shelf {fieldName} '{publicShelfRef}'; artifact factory bundle refs must not contain traversal or encoded path separators.");
            }
        }
    }

    private static void RejectUnsafePublicPathId(string sourcePackId, string? value, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return;
        }

        string pathId = value.Trim();
        if (pathId.Contains('?', StringComparison.Ordinal)
            || pathId.Contains('#', StringComparison.Ordinal)
            || pathId.Contains('/', StringComparison.Ordinal)
            || pathId.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe {fieldName} '{value}'; artifact factory path ids must be stable public proof shelf segments.");
        }

        string decoded = Uri.UnescapeDataString(pathId);
        if (decoded is "." or ".."
            || decoded.Contains('/', StringComparison.Ordinal)
            || decoded.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe {fieldName} '{value}'; artifact factory path ids must not contain traversal or encoded path separators.");
        }
    }

    private static string[] NormalizeOutputFormats(IReadOnlyList<string>? requestedFormats, ArtifactFactoryRecipe recipe)
    {
        string[] formats = (requestedFormats is { Count: > 0 } ? requestedFormats : recipe.DefaultFormats)
            .Select(NormalizeToken)
            .Where(static item => item.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (formats.Length == 0)
        {
            throw new InvalidDataException("at least one output format is required.");
        }

        string[] unsupportedFormats = formats
            .Where(format => !recipe.AllowedFormats.Contains(format, StringComparer.OrdinalIgnoreCase))
            .ToArray();
        if (unsupportedFormats.Length > 0)
        {
            throw new InvalidDataException($"recipe {recipe.RecipeId} does not allow output format(s): {string.Join(", ", unsupportedFormats)}.");
        }

        return formats;
    }

    private static string BuildJobId(
        string family,
        IReadOnlyList<ArtifactFactoryMediaSourcePack> sourcePacks,
        IReadOnlyList<string> outputFormats,
        string audience,
        string locale)
    {
        var hashPayload = new
        {
            family,
            sourcePacks = sourcePacks
                .OrderBy(static item => item.SourcePackId, StringComparer.OrdinalIgnoreCase)
                .Select(static item => new
                {
                    item.SourcePackId,
                    item.SourcePackKind,
                    item.ProvenanceRef,
                    item.EvidenceRefs,
                    item.ReleaseArtifactId,
                    item.SupportCaseId,
                    item.PublicationId,
                    item.PublicShelfRef
                }),
            outputFormats,
            audience,
            locale
        };
        byte[] payload = JsonSerializer.SerializeToUtf8Bytes(hashPayload, HashJsonOptions);
        byte[] hash = SHA256.HashData(payload);
        return $"artifact-job-{family}-{Convert.ToHexString(hash)[..16].ToLowerInvariant()}";
    }

    private static ArtifactFactoryOutputBinding[] BuildOutputBindings(
        string family,
        string jobId,
        IReadOnlyList<ArtifactFactoryMediaSourcePack> sourcePacks,
        IReadOnlyList<string> outputFormats)
    {
        ArtifactFactoryMediaSourcePack anchor = SelectOutputAnchor(family, sourcePacks);
        string baseRef = BuildPublicOutputBaseRef(family, jobId, anchor);

        return outputFormats
            .Select(format => new ArtifactFactoryOutputBinding(
                Format: format,
                PublicRef: $"{baseRef}/{Uri.EscapeDataString(format)}",
                ReceiptRef: $"artifact-factory:{jobId}:{format}",
                ReleaseArtifactId: anchor.ReleaseArtifactId,
                SupportCaseId: anchor.SupportCaseId,
                PublicationId: anchor.PublicationId))
            .OrderBy(static item => item.Format, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static IEnumerable<string> BuildOutputShelfRefs(IReadOnlyList<ArtifactFactoryOutputBinding> outputBindings)
    {
        foreach (ArtifactFactoryOutputBinding binding in outputBindings)
        {
            int separatorIndex = binding.PublicRef.LastIndexOf('/');
            if (separatorIndex > 0)
            {
                yield return binding.PublicRef[..separatorIndex];
            }
        }
    }

    private static ArtifactFactoryMediaSourcePack SelectOutputAnchor(
        string family,
        IReadOnlyList<ArtifactFactoryMediaSourcePack> sourcePacks)
    {
        return sourcePacks
            .Where(pack => family switch
            {
                "release" => !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId)
                    || !string.IsNullOrWhiteSpace(pack.PublicShelfRef),
                "fix" => !string.IsNullOrWhiteSpace(pack.SupportCaseId)
                    || !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId),
                "support" => !string.IsNullOrWhiteSpace(pack.SupportCaseId),
                "publication" => !string.IsNullOrWhiteSpace(pack.PublicationId)
                    || !string.IsNullOrWhiteSpace(pack.PublicShelfRef),
                _ => false
            })
            .OrderBy(pack => family switch
            {
                "release" when !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId) => 0,
                "publication" when !string.IsNullOrWhiteSpace(pack.PublicationId) => 0,
                _ => 1
            })
            .ThenBy(static item => item.SourcePackId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault()
            ?? sourcePacks.OrderBy(static item => item.SourcePackId, StringComparer.OrdinalIgnoreCase).First();
    }

    private static string BuildPublicOutputBaseRef(
        string family,
        string jobId,
        ArtifactFactoryMediaSourcePack anchor)
    {
        if (!string.IsNullOrWhiteSpace(anchor.ReleaseArtifactId))
        {
            return $"/artifacts/release-bundles/{Uri.EscapeDataString(anchor.ReleaseArtifactId)}";
        }

        if (!string.IsNullOrWhiteSpace(anchor.SupportCaseId))
        {
            string supportPath = family.Equals("fix", StringComparison.OrdinalIgnoreCase)
                ? "fix-followthrough"
                : "support-packets";
            return $"/account/{supportPath}/{Uri.EscapeDataString(anchor.SupportCaseId)}";
        }

        if (!string.IsNullOrWhiteSpace(anchor.PublicationId))
        {
            return $"/artifacts/publications/{Uri.EscapeDataString(anchor.PublicationId)}/bundles";
        }

        if (!string.IsNullOrWhiteSpace(anchor.PublicShelfRef))
        {
            string shelfRef = anchor.PublicShelfRef.Trim().TrimEnd('/');
            if (family.Equals("release", StringComparison.OrdinalIgnoreCase)
                && TryBuildReleaseBundleRefFromDownloadShelfRef(shelfRef, out string? releaseBundleRef))
            {
                return releaseBundleRef;
            }

            return shelfRef.EndsWith("/bundles", StringComparison.OrdinalIgnoreCase)
                ? shelfRef
                : $"{shelfRef}/bundles";
        }

        return $"/artifacts/release-bundles/{Uri.EscapeDataString(jobId)}";
    }

    private static bool TryBuildReleaseBundleRefFromDownloadShelfRef(string shelfRef, out string releaseBundleRef)
    {
        const string downloadInstallPrefix = "/downloads/install/";
        releaseBundleRef = string.Empty;
        if (!shelfRef.StartsWith(downloadInstallPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string releaseArtifactId = shelfRef[downloadInstallPrefix.Length..].Trim('/');
        if (string.IsNullOrWhiteSpace(releaseArtifactId))
        {
            return false;
        }

        releaseBundleRef = $"/artifacts/release-bundles/{Uri.EscapeDataString(releaseArtifactId)}";
        return true;
    }

    private static string NormalizeToken(string? value)
        => (value ?? string.Empty).Trim().Replace('-', '_').ToLowerInvariant();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record ArtifactFactoryRecipe(
        string RecipeId,
        IReadOnlyList<string> AllowedSourceKinds,
        IReadOnlyList<string> DefaultFormats,
        IReadOnlyList<string> AllowedFormats,
        IReadOnlyList<string> RequiredReceiptPrefixes,
        string RequiredAnchorDescription);
}
