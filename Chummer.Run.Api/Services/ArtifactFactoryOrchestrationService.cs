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
    ArtifactFactoryMediaRequest MediaFactoryRequest);

public sealed record ArtifactFactoryMediaRequest(
    string ContractName,
    string RecipeId,
    string RecipeVersion,
    IReadOnlyList<ArtifactFactoryMediaSourcePack> ApprovedSourcePacks,
    IReadOnlyList<string> OutputFormats,
    IReadOnlyList<string> RequiredReceiptRefs,
    IReadOnlyList<string> PublicProofShelfRefs);

public sealed record ArtifactFactoryMediaSourcePack(
    string SourcePackId,
    string SourcePackKind,
    string ProvenanceRef,
    IReadOnlyList<string> EvidenceRefs,
    string? ReleaseArtifactId,
    string? SupportCaseId,
    string? PublicationId);

public sealed class ArtifactFactoryOrchestrationService
{
    private const string ContractName = "chummer.run.artifact_factory.recipe_job.v1";
    private const string RecipeVersion = "2026-04-15";
    private static readonly JsonSerializerOptions HashJsonOptions = new(JsonSerializerDefaults.Web);
    private static readonly IReadOnlyDictionary<string, ArtifactFactoryRecipe> Recipes =
        new Dictionary<string, ArtifactFactoryRecipe>(StringComparer.OrdinalIgnoreCase)
        {
            ["release"] = new(
                RecipeId: "release-proof-shelf-bundle",
                AllowedSourceKinds: ["release", "release_evidence", "desktop_release", "install_receipt"],
                DefaultFormats: ["preview_card", "caption", "packet", "short_video"],
                RequiredReceiptPrefixes: ["release", "promotion", "public-shelf"]),
            ["fix"] = new(
                RecipeId: "fix-followthrough-bundle",
                AllowedSourceKinds: ["fix_receipt", "support_case", "install_receipt", "release"],
                DefaultFormats: ["preview_card", "caption", "packet"],
                RequiredReceiptPrefixes: ["fix", "install", "support"]),
            ["support"] = new(
                RecipeId: "support-case-proof-packet",
                AllowedSourceKinds: ["support_case", "crash_report", "install_receipt", "release"],
                DefaultFormats: ["preview_card", "caption", "packet"],
                RequiredReceiptPrefixes: ["support", "privacy", "install"]),
            ["publication"] = new(
                RecipeId: "publication-proof-shelf-bundle",
                AllowedSourceKinds: ["publication", "creator_publication", "campaign_recap", "runtime_bundle"],
                DefaultFormats: ["preview_card", "caption", "packet", "short_video"],
                RequiredReceiptPrefixes: ["publication", "moderation", "public-shelf"])
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
            ValidateSourcePack(sourcePack, recipe);
            if (!sourcePackIds.Add(sourcePack.SourcePackId))
            {
                throw new InvalidDataException($"duplicate source pack id '{sourcePack.SourcePackId}' is not allowed.");
            }

            IReadOnlyList<string> evidenceRefs = NormalizeEvidenceRefs(sourcePack);
            sourcePacks.Add(new ArtifactFactoryMediaSourcePack(
                SourcePackId: sourcePack.SourcePackId.Trim(),
                SourcePackKind: NormalizeToken(sourcePack.SourcePackKind),
                ProvenanceRef: sourcePack.ProvenanceRef.Trim(),
                EvidenceRefs: evidenceRefs,
                ReleaseArtifactId: NormalizeOptional(sourcePack.ReleaseArtifactId),
                SupportCaseId: NormalizeOptional(sourcePack.SupportCaseId),
                PublicationId: NormalizeOptional(sourcePack.PublicationId)));

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
            else if (!string.IsNullOrWhiteSpace(sourcePack.PublicationId))
            {
                publicProofShelfRefs.Add($"/artifacts/publications/{Uri.EscapeDataString(sourcePack.PublicationId.Trim())}");
            }
        }

        foreach (string prefix in recipe.RequiredReceiptPrefixes)
        {
            if (!requiredReceiptRefs.Any(receipt => receipt.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)))
            {
                requiredReceiptRefs.Add($"{prefix}:pending-receipt");
            }
        }

        string[] outputFormats = NormalizeOutputFormats(request.RequestedFormats, recipe.DefaultFormats);
        string audience = NormalizeOptional(request.Audience) ?? "public-proof-shelf";
        string locale = NormalizeOptional(request.Locale) ?? "en-US";
        string jobId = BuildJobId(family, sourcePacks, outputFormats, audience, locale);
        string[] receiptRefs = requiredReceiptRefs.Distinct(StringComparer.OrdinalIgnoreCase).Order(StringComparer.OrdinalIgnoreCase).ToArray();
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
            MediaFactoryRequest: new ArtifactFactoryMediaRequest(
                ContractName: ContractName,
                RecipeId: recipe.RecipeId,
                RecipeVersion: RecipeVersion,
                ApprovedSourcePacks: sourcePacks,
                OutputFormats: outputFormats,
                RequiredReceiptRefs: receiptRefs,
                PublicProofShelfRefs: proofShelfRefs));
    }

    private static void ValidateSourcePack(ApprovedArtifactSourcePack sourcePack, ArtifactFactoryRecipe recipe)
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
    }

    private static IReadOnlyList<string> NormalizeEvidenceRefs(ApprovedArtifactSourcePack sourcePack)
    {
        string[] evidenceRefs = (sourcePack.EvidenceRefs ?? Array.Empty<string>())
            .Select(static item => item.Trim())
            .Where(static item => item.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        return evidenceRefs.Length > 0
            ? evidenceRefs
            : [$"provenance:{sourcePack.ProvenanceRef.Trim()}"];
    }

    private static string[] NormalizeOutputFormats(IReadOnlyList<string>? requestedFormats, IReadOnlyList<string> defaultFormats)
    {
        string[] formats = (requestedFormats is { Count: > 0 } ? requestedFormats : defaultFormats)
            .Select(NormalizeToken)
            .Where(static item => item.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (formats.Length == 0)
        {
            throw new InvalidDataException("at least one output format is required.");
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
                    item.PublicationId
                }),
            outputFormats,
            audience,
            locale
        };
        byte[] payload = JsonSerializer.SerializeToUtf8Bytes(hashPayload, HashJsonOptions);
        byte[] hash = SHA256.HashData(payload);
        return $"artifact-job-{family}-{Convert.ToHexString(hash)[..16].ToLowerInvariant()}";
    }

    private static string NormalizeToken(string? value)
        => (value ?? string.Empty).Trim().Replace('-', '_').ToLowerInvariant();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record ArtifactFactoryRecipe(
        string RecipeId,
        IReadOnlyList<string> AllowedSourceKinds,
        IReadOnlyList<string> DefaultFormats,
        IReadOnlyList<string> RequiredReceiptPrefixes);
}
