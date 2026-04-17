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

public sealed record ArtifactFactoryJobBatchLaunchRequest(
    string BatchId,
    string RequestedBy,
    IReadOnlyList<ArtifactFactoryJobLaunchRequest> Jobs,
    IReadOnlyList<string>? RequiredFamilies = null);

public sealed record ArtifactFactorySourcePackBatchLaunchRequest(
    string BatchId,
    string RequestedBy,
    IReadOnlyList<ApprovedArtifactSourcePack> SourcePacks,
    IReadOnlyList<ArtifactFactoryFamilyFormatOverride>? RequestedFormats = null,
    string? Audience = null,
    string? Locale = null,
    IReadOnlyList<string>? RequiredFamilies = null);

public sealed record ArtifactFactoryFamilyFormatOverride(
    string Family,
    IReadOnlyList<string> Formats);

public sealed record ArtifactFactoryJobBatchLaunchResult(
    string BatchId,
    string State,
    string RequestedBy,
    DateTimeOffset QueuedAtUtc,
    int JobCount,
    IReadOnlyList<string> Families,
    IReadOnlyList<string> RecipeIds,
    IReadOnlyList<string> RequiredFamilies,
    IReadOnlyList<string> JobIds,
    IReadOnlyList<string> SourcePackIds,
    IReadOnlyList<string> RequiredReceiptRefs,
    IReadOnlyList<string> PublicProofShelfRefs,
    IReadOnlyList<ArtifactFactoryJobLaunchResult> Jobs,
    IReadOnlyList<ArtifactFactoryMediaRequest> MediaFactoryRequests);

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

public sealed record ArtifactFactoryRecipeCatalogResult(
    string ContractName,
    string RecipeVersion,
    IReadOnlyList<ArtifactFactoryRecipeDefinition> Recipes);

public sealed record ArtifactFactoryRecipeDefinition(
    string Family,
    string RecipeId,
    IReadOnlyList<string> AllowedSourceKinds,
    IReadOnlyList<string> DefaultFormats,
    IReadOnlyList<string> AllowedFormats,
    IReadOnlyList<string> RequiredReceiptPrefixes,
    string RequiredAnchorDescription);

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

    public ArtifactFactoryRecipeCatalogResult ListRecipes()
    {
        ArtifactFactoryRecipeDefinition[] recipes = Recipes
            .OrderBy(static item => item.Key, StringComparer.OrdinalIgnoreCase)
            .Select(static item => new ArtifactFactoryRecipeDefinition(
                Family: item.Key,
                RecipeId: item.Value.RecipeId,
                AllowedSourceKinds: item.Value.AllowedSourceKinds.Order(StringComparer.OrdinalIgnoreCase).ToArray(),
                DefaultFormats: item.Value.DefaultFormats.Order(StringComparer.OrdinalIgnoreCase).ToArray(),
                AllowedFormats: item.Value.AllowedFormats.Order(StringComparer.OrdinalIgnoreCase).ToArray(),
                RequiredReceiptPrefixes: item.Value.RequiredReceiptPrefixes.Order(StringComparer.OrdinalIgnoreCase).ToArray(),
                RequiredAnchorDescription: item.Value.RequiredAnchorDescription))
            .ToArray();

        return new ArtifactFactoryRecipeCatalogResult(
            ContractName: ContractName,
            RecipeVersion: RecipeVersion,
            Recipes: recipes);
    }

    public ArtifactFactoryJobBatchLaunchResult LaunchJobs(ArtifactFactoryJobBatchLaunchRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (string.IsNullOrWhiteSpace(request.BatchId))
        {
            throw new InvalidDataException("batchId is required.");
        }

        RejectUnsafeBatchId(request.BatchId);

        string requestedBy = NormalizeRequestedBy(request.RequestedBy);

        if (request.Jobs is null || request.Jobs.Count == 0)
        {
            throw new InvalidDataException("at least one artifact factory job is required.");
        }

        List<ArtifactFactoryJobLaunchResult> jobs = new(request.Jobs.Count);
        HashSet<string> jobIds = new(StringComparer.OrdinalIgnoreCase);
        foreach (ArtifactFactoryJobLaunchRequest jobRequest in request.Jobs)
        {
            if (jobRequest is null)
            {
                throw new InvalidDataException($"batch '{request.BatchId.Trim()}' contains an empty artifact factory job request.");
            }

            ArtifactFactoryJobLaunchRequest normalizedRequest;
            if (string.IsNullOrWhiteSpace(jobRequest.RequestedBy))
            {
                normalizedRequest = jobRequest with { RequestedBy = requestedBy };
            }
            else
            {
                string jobRequestedBy = NormalizeRequestedBy(jobRequest.RequestedBy);
                if (!string.Equals(jobRequestedBy, requestedBy, StringComparison.Ordinal))
                {
                    throw new InvalidDataException(
                        $"artifact factory batch '{request.BatchId.Trim()}' job requestedBy '{jobRequestedBy}' must match batch requestedBy '{requestedBy}'.");
                }

                normalizedRequest = jobRequest with { RequestedBy = jobRequestedBy };
            }

            ArtifactFactoryJobLaunchResult job = LaunchJob(normalizedRequest);
            if (!jobIds.Add(job.JobId))
            {
                throw new InvalidDataException($"duplicate artifact factory job '{job.JobId}' is not allowed in batch '{request.BatchId.Trim()}'.");
            }

            jobs.Add(job);
        }

        string[] families = jobs
            .Select(static job => job.Family)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        string[] requiredFamilies = NormalizeRequiredBatchFamilies(request.RequiredFamilies);
        string[] missingRequiredFamilies = requiredFamilies
            .Where(required => !families.Contains(required, StringComparer.OrdinalIgnoreCase))
            .ToArray();
        if (missingRequiredFamilies.Length > 0)
        {
            throw new InvalidDataException(
                $"artifact factory batch '{request.BatchId.Trim()}' is missing required recipe family job(s): {string.Join(", ", missingRequiredFamilies)}.");
        }

        string[] receiptRefs = jobs
            .SelectMany(static job => job.RequiredReceiptRefs)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        string[] recipeIds = jobs
            .Select(static job => job.RecipeId)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        string[] publicProofShelfRefs = jobs
            .SelectMany(static job => job.PublicProofShelfRefs)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        string[] sourcePackIds = jobs
            .SelectMany(static job => job.SourcePackIds)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        ArtifactFactoryJobLaunchResult[] orderedJobs = jobs
            .OrderBy(static job => job.JobId, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return new ArtifactFactoryJobBatchLaunchResult(
            BatchId: request.BatchId.Trim(),
            State: "queued",
            RequestedBy: requestedBy,
            QueuedAtUtc: DateTimeOffset.UtcNow,
            JobCount: jobs.Count,
            Families: families,
            RecipeIds: recipeIds,
            RequiredFamilies: requiredFamilies,
            JobIds: orderedJobs.Select(static job => job.JobId).ToArray(),
            SourcePackIds: sourcePackIds,
            RequiredReceiptRefs: receiptRefs,
            PublicProofShelfRefs: publicProofShelfRefs,
            Jobs: orderedJobs,
            MediaFactoryRequests: orderedJobs.Select(static job => job.MediaFactoryRequest).ToArray());
    }

    public ArtifactFactoryJobBatchLaunchResult LaunchSourcePackBatch(ArtifactFactorySourcePackBatchLaunchRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (string.IsNullOrWhiteSpace(request.BatchId))
        {
            throw new InvalidDataException("source-pack batchId is required.");
        }

        RejectUnsafeBatchId(request.BatchId);

        if (request.SourcePacks is null || request.SourcePacks.Count == 0)
        {
            throw new InvalidDataException("at least one approved source pack is required for artifact factory source-pack batch launch.");
        }

        ValidateSourcePackBatchSourcePacks(request.SourcePacks);

        string[] requiredFamilies = NormalizeRequiredBatchFamilies(request.RequiredFamilies);
        IReadOnlyDictionary<string, IReadOnlyList<string>> requestedFormatsByFamily = NormalizeFamilyFormatOverrides(request.RequestedFormats);
        ArtifactFactoryJobLaunchRequest[] jobs = requiredFamilies
            .Select(family => BuildJobFromApprovedSourcePackBatch(request, family, requestedFormatsByFamily))
            .ToArray();

        return LaunchJobs(new ArtifactFactoryJobBatchLaunchRequest(
            BatchId: request.BatchId,
            RequestedBy: request.RequestedBy,
            Jobs: jobs,
            RequiredFamilies: requiredFamilies));
    }

    private static ArtifactFactoryJobLaunchRequest BuildJobFromApprovedSourcePackBatch(
        ArtifactFactorySourcePackBatchLaunchRequest request,
        string family,
        IReadOnlyDictionary<string, IReadOnlyList<string>> requestedFormatsByFamily)
    {
        ArtifactFactoryRecipe recipe = Recipes[family];
        ApprovedArtifactSourcePack[] sourcePacks = request.SourcePacks
            .Where(sourcePack => sourcePack is not null && SourcePackCanFeedRecipe(sourcePack, recipe))
            .ToArray();
        if (sourcePacks.Length == 0)
        {
            throw new InvalidDataException(
                $"artifact factory source-pack batch '{request.BatchId.Trim()}' has no approved source packs matching required recipe family '{family}'.");
        }

        requestedFormatsByFamily.TryGetValue(family, out IReadOnlyList<string>? requestedFormats);
        return new ArtifactFactoryJobLaunchRequest(
            Family: family,
            RequestedBy: request.RequestedBy,
            SourcePacks: sourcePacks,
            RequestedFormats: requestedFormats,
            Audience: request.Audience,
            Locale: request.Locale);
    }

    private static bool SourcePackCanFeedRecipe(ApprovedArtifactSourcePack sourcePack, ArtifactFactoryRecipe recipe)
    {
        string sourcePackKind = NormalizeToken(sourcePack.SourcePackKind);
        return sourcePackKind.Length > 0
            && recipe.AllowedSourceKinds.Contains(sourcePackKind, StringComparer.OrdinalIgnoreCase);
    }

    private static void ValidateSourcePackBatchSourcePacks(IReadOnlyList<ApprovedArtifactSourcePack> sourcePacks)
    {
        HashSet<string> sourcePackIds = new(StringComparer.OrdinalIgnoreCase);
        foreach (ApprovedArtifactSourcePack? sourcePack in sourcePacks)
        {
            if (sourcePack is null)
            {
                throw new InvalidDataException("artifact factory source-pack batch contains an empty approved source pack.");
            }

            if (string.IsNullOrWhiteSpace(sourcePack.SourcePackId))
            {
                throw new InvalidDataException("sourcePackId is required for every source-pack batch pack.");
            }

            RejectProviderSpecificRef(sourcePack.SourcePackId, sourcePack.SourcePackId, "sourcePackId");
            RejectUnsafeSourcePackId(sourcePack.SourcePackId);

            string normalizedSourcePackId = sourcePack.SourcePackId.Trim();
            if (!sourcePackIds.Add(normalizedSourcePackId))
            {
                throw new InvalidDataException($"duplicate source pack id '{normalizedSourcePackId}' is not allowed in source-pack batch.");
            }

            if (!string.Equals(sourcePack.ApprovalState?.Trim(), "approved", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"source pack '{normalizedSourcePackId}' is not approved for source-pack batch launch.");
            }

            if (string.IsNullOrWhiteSpace(sourcePack.ProvenanceRef))
            {
                throw new InvalidDataException($"source pack '{normalizedSourcePackId}' is missing provenanceRef.");
            }

            RejectProviderSpecificRef(normalizedSourcePackId, sourcePack.ProvenanceRef, "provenanceRef");
            foreach (string evidenceRef in sourcePack.EvidenceRefs ?? Array.Empty<string>())
            {
                if (string.IsNullOrWhiteSpace(evidenceRef))
                {
                    continue;
                }

                RejectProviderSpecificRef(normalizedSourcePackId, evidenceRef, "evidenceRef");
                RejectNonLocalPublicShelfEvidenceRef(normalizedSourcePackId, evidenceRef);
            }

            if (!string.IsNullOrWhiteSpace(sourcePack.PublicShelfRef))
            {
                RejectProviderSpecificRef(normalizedSourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");
                RejectNonLocalPublicShelfRef(normalizedSourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");
            }

            RejectUnsafePublicPathId(normalizedSourcePackId, sourcePack.ReleaseArtifactId, "releaseArtifactId");
            RejectUnsafePublicPathId(normalizedSourcePackId, sourcePack.SupportCaseId, "supportCaseId");
            RejectUnsafePublicPathId(normalizedSourcePackId, sourcePack.PublicationId, "publicationId");
        }
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> NormalizeFamilyFormatOverrides(
        IReadOnlyList<ArtifactFactoryFamilyFormatOverride>? requestedFormats)
    {
        Dictionary<string, IReadOnlyList<string>> formatsByFamily = new(StringComparer.OrdinalIgnoreCase);
        if (requestedFormats is null || requestedFormats.Count == 0)
        {
            return formatsByFamily;
        }

        foreach (ArtifactFactoryFamilyFormatOverride? overrideRequest in requestedFormats)
        {
            if (overrideRequest is null)
            {
                throw new InvalidDataException("artifact factory source-pack batch contains an empty requested format override.");
            }

            string family = NormalizeToken(overrideRequest.Family);
            RejectProviderSpecificRef("source-pack-batch", family, "requestedFormatFamily");
            RejectUnsafeJobToken(family, "requestedFormatFamily", allowComma: false);
            if (!Recipes.ContainsKey(family))
            {
                throw new InvalidDataException($"artifact factory source-pack batch requested formats for unsupported recipe family '{family}'.");
            }

            if (!formatsByFamily.TryAdd(family, overrideRequest.Formats))
            {
                throw new InvalidDataException($"artifact factory source-pack batch contains duplicate requested formats for recipe family '{family}'.");
            }
        }

        return formatsByFamily;
    }

    private static string[] NormalizeRequiredBatchFamilies(IReadOnlyList<string>? requiredFamilies)
    {
        if (requiredFamilies is null || requiredFamilies.Count == 0)
        {
            return Recipes.Keys
                .Order(StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }

        string[] families = requiredFamilies
            .Select(NormalizeToken)
            .Where(static item => item.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (families.Length == 0)
        {
            throw new InvalidDataException("artifact factory batch required recipe families cannot be empty.");
        }

        foreach (string family in families)
        {
            RejectProviderSpecificRef("batch-request", family, "requiredFamily");
            RejectUnsafeJobToken(family, "requiredFamily", allowComma: false);
            if (!Recipes.ContainsKey(family))
            {
                throw new InvalidDataException($"artifact factory batch requires unsupported recipe family '{family}'.");
            }
        }

        return families;
    }

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

        string requestedBy = NormalizeRequestedBy(request.RequestedBy);

        if (request.SourcePacks is null || request.SourcePacks.Count == 0)
        {
            throw new InvalidDataException("at least one approved source pack is required.");
        }

        List<ArtifactFactoryMediaSourcePack> sourcePacks = new(request.SourcePacks.Count);
        List<string> requiredReceiptRefs = new();
        List<string> publicProofShelfRefs = new();
        HashSet<string> sourcePackIds = new(StringComparer.OrdinalIgnoreCase);
        foreach (ApprovedArtifactSourcePack? sourcePack in request.SourcePacks)
        {
            if (sourcePack is null)
            {
                throw new InvalidDataException("artifact factory job contains an empty approved source pack.");
            }

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
                string supportCaseId = Uri.EscapeDataString(sourcePack.SupportCaseId.Trim());
                publicProofShelfRefs.Add($"/account/support/{supportCaseId}");
                if (family.Equals("fix", StringComparison.OrdinalIgnoreCase))
                {
                    publicProofShelfRefs.Add($"/account/fix-followthrough/{supportCaseId}");
                }
            }
            else if (!string.IsNullOrWhiteSpace(sourcePack.PublicationId))
            {
                publicProofShelfRefs.Add($"/artifacts/publications/{Uri.EscapeDataString(sourcePack.PublicationId.Trim())}");
            }
        }

        ValidateRecipeAnchors(family, request.SourcePacks, recipe);

        string[] missingReceiptPrefixes = recipe.RequiredReceiptPrefixes
            .Where(prefix => !requiredReceiptRefs.Any(receipt => ReceiptRefMatchesRequiredPrefix(receipt, prefix)))
            .ToArray();
        if (missingReceiptPrefixes.Length > 0)
        {
            throw new InvalidDataException(
                $"recipe {recipe.RecipeId} requires approved source-pack receipt evidence for: {string.Join(", ", missingReceiptPrefixes)}.");
        }

        string[] outputFormats = NormalizeOutputFormats(request.RequestedFormats, recipe);
        string audience = NormalizeAudience(request.Audience);
        string locale = NormalizeLocale(request.Locale);
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
            RequestedBy: requestedBy,
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

        RejectProviderSpecificRef(sourcePack.SourcePackId, sourcePack.SourcePackId, "sourcePackId");
        RejectUnsafeSourcePackId(sourcePack.SourcePackId);

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
            RejectNonLocalPublicShelfRef(sourcePack.SourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");
            RejectPublicShelfRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, sourcePack.PublicShelfRef, "publicShelfRef");
            RejectProviderSpecificRef(sourcePack.SourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");
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

    private static bool ReceiptRefMatchesRequiredPrefix(string receiptRef, string requiredPrefix)
    {
        string normalizedReceiptRef = receiptRef.Trim();
        return normalizedReceiptRef.Equals(requiredPrefix, StringComparison.OrdinalIgnoreCase)
            || normalizedReceiptRef.StartsWith($"{requiredPrefix}:", StringComparison.OrdinalIgnoreCase);
    }

    private static void RejectProviderSpecificRef(string sourcePackId, string value, string fieldName)
    {
        string normalized = value.Trim();
        int separatorIndex = FirstRefPrefixSeparatorIndex(normalized);
        string prefix = separatorIndex >= 0
            ? normalized[..separatorIndex].Trim()
            : string.Empty;
        if (IsAbsoluteHttpRef(normalized) || IsUriLikeExternalRef(normalized, fieldName))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has external absolute URI {fieldName} '{value}'; artifact factory jobs must launch from approved source-pack receipts instead of one-off provider flows.");
        }

        if (ProviderSpecificRefPrefixes.Contains(normalized)
            || ProviderSpecificRefPrefixes.Contains(prefix)
            || (!IsExternalPublicShelfEvidenceRef(normalized, fieldName) && ContainsProviderSpecificToken(normalized)))
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

    private static bool ContainsProviderSpecificToken(string normalized)
    {
        string lower = normalized.ToLowerInvariant();
        foreach (string providerToken in ProviderSpecificRefPrefixes)
        {
            string token = providerToken.ToLowerInvariant();
            if (ContainsDelimitedToken(lower, token))
            {
                return true;
            }
        }

        return false;
    }

    private static bool ContainsDelimitedToken(string value, string token)
    {
        int startIndex = 0;
        while (startIndex < value.Length)
        {
            int index = value.IndexOf(token, startIndex, StringComparison.Ordinal);
            if (index < 0)
            {
                return false;
            }

            int endIndex = index + token.Length;
            if (IsProviderTokenBoundary(value, index - 1)
                && IsProviderTokenBoundary(value, endIndex))
            {
                return true;
            }

            startIndex = index + 1;
        }

        return false;
    }

    private static bool IsProviderTokenBoundary(string value, int index)
        => index < 0
            || index >= value.Length
            || value[index] is ':' or '/' or '\\' or '-' or '_' or '.';

    private static bool IsAbsoluteHttpRef(string normalized)
        => Uri.TryCreate(normalized, UriKind.Absolute, out Uri? uri)
            && (uri.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
                || uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase));

    private static bool IsUriLikeExternalRef(string normalized, string fieldName)
        => !IsPublicShelfEvidenceRef(normalized, fieldName)
            && normalized.Contains("://", StringComparison.Ordinal);

    private static bool IsPublicShelfEvidenceRef(string normalized, string fieldName)
        => fieldName.Equals("evidenceRef", StringComparison.Ordinal)
            && normalized.StartsWith("public-shelf:", StringComparison.OrdinalIgnoreCase);

    private static bool IsExternalPublicShelfEvidenceRef(string normalized, string fieldName)
        => IsPublicShelfEvidenceRef(normalized, fieldName)
            && !normalized["public-shelf:".Length..].TrimStart().StartsWith("/", StringComparison.Ordinal);

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

        RejectRecipeShelfAnchorShape(sourcePackId, family, publicShelfRef, fieldName);
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

            if (!IsStablePublicShelfSegment(decodedSegment))
            {
                throw new InvalidDataException(
                    $"source pack '{sourcePackId}' has unsafe public proof shelf {fieldName} '{publicShelfRef}'; artifact factory bundle refs must use stable public proof shelf segment characters.");
            }
        }
    }

    private static void RejectReleaseBundleShelfAnchorShape(string sourcePackId, string publicShelfRef, string fieldName)
    {
        string[] allowedReleasePrefixes = ["/downloads/install/", "/artifacts/release-bundles/"];
        string? matchingPrefix = allowedReleasePrefixes.FirstOrDefault(prefix => publicShelfRef.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
        string releaseArtifactId = matchingPrefix is null
            ? string.Empty
            : publicShelfRef[matchingPrefix.Length..].Trim('/');

        if (string.IsNullOrWhiteSpace(releaseArtifactId)
            || releaseArtifactId.Contains('/', StringComparison.Ordinal)
            || releaseArtifactId.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe release public proof shelf {fieldName} '{publicShelfRef}'; release bundle anchors must resolve to exactly one release artifact segment.");
        }
    }

    private static void RejectRecipeShelfAnchorShape(string sourcePackId, string family, string publicShelfRef, string fieldName)
    {
        if (family.Equals("release", StringComparison.OrdinalIgnoreCase))
        {
            RejectReleaseBundleShelfAnchorShape(sourcePackId, publicShelfRef, fieldName);
            return;
        }

        if (family.Equals("publication", StringComparison.OrdinalIgnoreCase)
            && !HasResourceShelfAnchorShape(publicShelfRef, "/artifacts/publications/", allowBundlesSuffix: true))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe publication public proof shelf {fieldName} '{publicShelfRef}'; publication bundle anchors must resolve to one publication segment with an optional bundles shelf.");
        }

        if (family.Equals("support", StringComparison.OrdinalIgnoreCase)
            && !HasAnyResourceShelfAnchorShape(publicShelfRef, ["/account/support/", "/account/support-packets/"], allowBundlesSuffix: false))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe support public proof shelf {fieldName} '{publicShelfRef}'; support bundle anchors must resolve to exactly one support case segment.");
        }

        if (family.Equals("fix", StringComparison.OrdinalIgnoreCase)
            && !HasAnyResourceShelfAnchorShape(
                publicShelfRef,
                ["/account/support/", "/account/fix-followthrough/", "/downloads/install/", "/artifacts/release-bundles/"],
                allowBundlesSuffix: false))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe fix public proof shelf {fieldName} '{publicShelfRef}'; fix bundle anchors must resolve to exactly one support case or release artifact segment.");
        }
    }

    private static bool HasAnyResourceShelfAnchorShape(string publicShelfRef, IReadOnlyList<string> prefixes, bool allowBundlesSuffix)
        => prefixes.Any(prefix => HasResourceShelfAnchorShape(publicShelfRef, prefix, allowBundlesSuffix));

    private static bool HasResourceShelfAnchorShape(string publicShelfRef, string prefix, bool allowBundlesSuffix)
    {
        if (!publicShelfRef.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string remainder = publicShelfRef[prefix.Length..].Trim('/');
        if (string.IsNullOrWhiteSpace(remainder))
        {
            return false;
        }

        string[] segments = remainder.Split('/', StringSplitOptions.RemoveEmptyEntries);
        return segments.Length == 1
            || (allowBundlesSuffix
                && segments.Length == 2
                && segments[1].Equals("bundles", StringComparison.OrdinalIgnoreCase));
    }

    private static void RejectUnsafePublicPathId(string sourcePackId, string? value, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return;
        }

        RejectProviderSpecificRef(sourcePackId, value, fieldName);

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
            || decoded.Contains(':', StringComparison.Ordinal)
            || decoded.Contains('/', StringComparison.Ordinal)
            || decoded.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe {fieldName} '{value}'; artifact factory path ids must not contain traversal, encoded provider delimiters, or encoded path separators.");
        }

        if (!IsStablePublicShelfSegment(decoded))
        {
            throw new InvalidDataException(
                $"source pack '{sourcePackId}' has unsafe {fieldName} '{value}'; artifact factory path ids must use stable public proof shelf segment characters.");
        }
    }

    private static void RejectUnsafeSourcePackId(string sourcePackId)
    {
        string normalized = sourcePackId.Trim();
        if (normalized.Contains('?', StringComparison.Ordinal)
            || normalized.Contains('#', StringComparison.Ordinal)
            || normalized.Contains('/', StringComparison.Ordinal)
            || normalized.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack id '{sourcePackId}' is unsafe; approved source-pack ids must be stable receipt ids, not provider paths.");
        }

        string decoded = Uri.UnescapeDataString(normalized);
        if (decoded is "." or ".."
            || decoded.Contains(':', StringComparison.Ordinal)
            || decoded.Contains('/', StringComparison.Ordinal)
            || decoded.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"source pack id '{sourcePackId}' is unsafe; approved source-pack ids must not contain traversal, encoded provider delimiters, or encoded path separators.");
        }

        if (!IsStablePublicShelfSegment(decoded))
        {
            throw new InvalidDataException(
                $"source pack id '{sourcePackId}' is unsafe; approved source-pack ids must use stable receipt segment characters.");
        }
    }

    private static bool IsStablePublicShelfSegment(string value)
        => value.Length > 0
            && value.All(static character =>
                char.IsLetterOrDigit(character)
                || character is '-' or '_' or '.');

    private static void RejectUnsafeBatchId(string batchId)
    {
        string normalized = batchId.Trim();
        if (normalized.Contains('?', StringComparison.Ordinal)
            || normalized.Contains('#', StringComparison.Ordinal)
            || normalized.Contains('/', StringComparison.Ordinal)
            || normalized.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"artifact factory batch id '{batchId}' is unsafe; batch ids must be stable orchestration receipt ids, not provider paths.");
        }

        string decoded = Uri.UnescapeDataString(normalized);
        if (decoded is "." or ".."
            || decoded.Contains(':', StringComparison.Ordinal)
            || decoded.Contains('/', StringComparison.Ordinal)
            || decoded.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"artifact factory batch id '{batchId}' is unsafe; batch ids must not contain traversal, encoded provider delimiters, or encoded path separators.");
        }

        if (!IsStablePublicShelfSegment(decoded))
        {
            throw new InvalidDataException(
                $"artifact factory batch id '{batchId}' is unsafe; batch ids must use stable orchestration receipt segment characters.");
        }
    }

    private static string NormalizeAudience(string? value)
    {
        string audience = NormalizeOptional(value) ?? "public-proof-shelf";
        RejectProviderSpecificRef("job-request", audience, "audience");
        RejectUnsafeJobToken(audience, "audience", allowComma: true);
        return audience;
    }

    private static string NormalizeRequestedBy(string? value)
    {
        string requestedBy = NormalizeOptional(value) ?? throw new InvalidDataException("requestedBy is required.");
        RejectProviderSpecificRef("job-request", requestedBy, "requestedBy");
        RejectUnsafeJobToken(requestedBy, "requestedBy", allowComma: false);
        return requestedBy;
    }

    private static string NormalizeLocale(string? value)
    {
        string locale = NormalizeOptional(value) ?? "en-US";
        RejectProviderSpecificRef("job-request", locale, "locale");
        RejectUnsafeJobToken(locale, "locale", allowComma: false);
        return locale;
    }

    private static void RejectUnsafeJobToken(string value, string fieldName, bool allowComma)
    {
        string normalized = value.Trim();
        if (normalized.Length == 0)
        {
            throw new InvalidDataException($"artifact factory {fieldName} is required.");
        }

        if (normalized.Contains('?', StringComparison.Ordinal)
            || normalized.Contains('#', StringComparison.Ordinal)
            || normalized.Contains(':', StringComparison.Ordinal)
            || normalized.Contains('/', StringComparison.Ordinal)
            || normalized.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"artifact factory {fieldName} '{value}' is unsafe; job metadata must be stable source-pack tokens, not provider paths or URIs.");
        }

        string decoded = Uri.UnescapeDataString(normalized);
        if (decoded is "." or ".."
            || decoded.Contains(':', StringComparison.Ordinal)
            || decoded.Contains('/', StringComparison.Ordinal)
            || decoded.Contains('\\', StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"artifact factory {fieldName} '{value}' is unsafe; job metadata must not contain traversal or encoded path separators.");
        }

        foreach (char character in normalized)
        {
            if (char.IsLetterOrDigit(character)
                || character is '-' or '_' or '.'
                || (allowComma && character == ','))
            {
                continue;
            }

            throw new InvalidDataException(
                $"artifact factory {fieldName} '{value}' is unsafe; job metadata must use stable token characters.");
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
        foreach (string format in formats)
        {
            RejectProviderSpecificRef("job-request", format, "outputFormat");
            RejectUnsafeJobToken(format, "outputFormat", allowComma: false);
        }

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

            if (family.Equals("release", StringComparison.OrdinalIgnoreCase)
                && shelfRef.StartsWith("/artifacts/release-bundles/", StringComparison.OrdinalIgnoreCase))
            {
                return shelfRef;
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
