using System.Text.Json;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services;

public enum RunsiteOrientationArtifactRole
{
    HostClip,
    RoutePreview,
    AudioCompanion,
    TourSibling
}

public sealed record RunsiteOrientationArtifactTemplate(
    string TemplateId,
    RunsiteOrientationArtifactRole Role,
    string Category,
    string Payload,
    string OutputFormat,
    string RouteSegmentId,
    string DeduplicationKey,
    TimeSpan? CacheTtl = null,
    int MaxBytes = 0,
    bool RequiresApproval = false,
    bool PersistOnApproval = false,
    bool AllowPersistentPinning = true);

public sealed record ApprovedRunsiteOrientationPack(
    string SourcePackId,
    string ApprovalState,
    string ProvenanceRef,
    IReadOnlyList<string> EvidenceRefs,
    string RouteSummaryId,
    IReadOnlyList<RunsiteOrientationArtifactTemplate> ArtifactTemplates,
    string? Audience = null,
    string? Locale = null);

public sealed record RunsiteRouteSummarySegment(
    string RouteSegmentId,
    string InspectableTruthRef,
    string PreviewPayload,
    string OutputFormat = "png",
    string Category = "runsite/orientation/route-preview");

public sealed record RunsiteRouteSummary(
    string RouteSummaryId,
    IReadOnlyList<RunsiteRouteSummarySegment> Segments);

public sealed record RunsitePreviewSafePreSessionTruth(
    string PreviewTruthPosture,
    string Summary,
    IReadOnlyList<string> InspectableTruthRefs);

public sealed record RunsiteOrientationRequestComposeRequest(
    string RequestedBy,
    string BundleId,
    ApprovedRunsiteOrientationPack RunsitePack,
    RunsiteRouteSummary RouteSummary,
    RunsitePreviewSafePreSessionTruth PreviewSafeTruth,
    string? Audience = null,
    string? Locale = null,
    DateTimeOffset? RequestedAtUtc = null);

public sealed record RunsiteOrientationArtifactRenderRequest(
    RunsiteOrientationArtifactRole Role,
    string Category,
    string Payload,
    string OutputFormat,
    string RouteSegmentId,
    string DeduplicationKey,
    TimeSpan? CacheTtl = null,
    int MaxBytes = 0,
    bool RequiresApproval = false,
    bool PersistOnApproval = false,
    bool AllowPersistentPinning = true);

public sealed record RunsiteOrientationBundleRequest(
    string BundleId,
    string ApprovedRunsitePackId,
    string RouteSummaryId,
    string Source,
    DateTimeOffset RequestedAtUtc,
    IReadOnlyList<RunsiteOrientationArtifactRenderRequest> Artifacts);

public sealed record RunsiteRouteSummaryArtifactLaunch(
    string ApprovedRunsitePackId,
    string RouteSummaryId,
    string RouteSegmentId,
    string InspectableTruthRef,
    string Category,
    string OutputFormat,
    string DeduplicationKey,
    string PreviewTruthPosture,
    string PreviewSafeTruthSummary,
    IReadOnlyList<string> PreviewSafeInspectableTruthRefs,
    IReadOnlyList<string> EvidenceRefs,
    string Audience,
    string Locale);

public sealed record RunsiteOrientationRequestCompositionResult(
    string ContractName,
    string ContractVersion,
    string RequestedBy,
    string Audience,
    string Locale,
    RunsitePreviewSafePreSessionTruth PreviewSafeTruth,
    RunsiteOrientationBundleRequest BundleRequest,
    IReadOnlyList<RunsiteRouteSummaryArtifactLaunch> RouteSummaryArtifactLaunches);

public sealed class RunsiteOrientationRequestComposerService
{
    public const string ContractName = "chummer6-hub.runsite_orientation_request.v1";
    public const string ContractVersion = "2026-04-23";
    public const string PreviewTruthPosture = "pre-session-orientation-only-not-tactical-truth";
    public const string RoutePreviewCategory = "runsite/orientation/route-preview";

    private static readonly Regex StableTokenPattern = new("^[A-Za-z0-9._-]+$", RegexOptions.Compiled);
    private static readonly Regex StableAudiencePattern = new("^[A-Za-z0-9._,-]+$", RegexOptions.Compiled);

    public RunsiteOrientationRequestCompositionResult Compose(RunsiteOrientationRequestComposeRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string requestedBy = NormalizeToken(request.RequestedBy, nameof(request.RequestedBy), allowComma: false);
        string bundleId = NormalizeToken(request.BundleId, nameof(request.BundleId), allowComma: false);
        string audience = ResolveAudience(request.Audience, request.RunsitePack);
        string locale = ResolveLocale(request.Locale, request.RunsitePack);
        ApprovedRunsiteOrientationPack pack = NormalizeApprovedRunsitePack(request.RunsitePack, audience, locale);
        RunsiteRouteSummary routeSummary = NormalizeRouteSummary(request.RouteSummary);
        RunsitePreviewSafePreSessionTruth previewSafeTruth = NormalizePreviewSafeTruth(request.PreviewSafeTruth, routeSummary);
        ValidateEvidenceRefs(pack, routeSummary.RouteSummaryId);

        if (!pack.RouteSummaryId.Equals(routeSummary.RouteSummaryId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException(
                $"approved runsite pack '{pack.SourcePackId}' routeSummaryId '{pack.RouteSummaryId}' must match route summary '{routeSummary.RouteSummaryId}'.");
        }

        Dictionary<string, RunsiteRouteSummarySegment> segmentsById = routeSummary.Segments
            .ToDictionary(segment => segment.RouteSegmentId, StringComparer.OrdinalIgnoreCase);
        List<RunsiteOrientationArtifactRenderRequest> artifacts = new(routeSummary.Segments.Count + pack.ArtifactTemplates.Count);
        HashSet<string> emittedDeduplicationKeys = new(StringComparer.OrdinalIgnoreCase);

        foreach (RunsiteOrientationArtifactTemplate template in pack.ArtifactTemplates)
        {
            if (template.Role == RunsiteOrientationArtifactRole.RoutePreview)
            {
                throw new InvalidDataException(
                    $"approved runsite pack '{pack.SourcePackId}' must not pre-compose route previews; route_summary:artifact_launch stays governed by the route summary.");
            }

            if (!segmentsById.TryGetValue(template.RouteSegmentId, out RunsiteRouteSummarySegment? segment))
            {
                throw new InvalidDataException(
                    $"approved runsite pack '{pack.SourcePackId}' references unknown route segment '{template.RouteSegmentId}'.");
            }

            string deduplicationKey = BuildDeduplicationKey(
                bundleId,
                pack.SourcePackId,
                routeSummary.RouteSummaryId,
                template.Role,
                template.RouteSegmentId,
                template.DeduplicationKey);

            AddArtifact(
                artifacts,
                emittedDeduplicationKeys,
                new RunsiteOrientationArtifactRenderRequest(
                Role: template.Role,
                Category: template.Category,
                Payload: BuildGovernedPayload(pack, routeSummary.RouteSummaryId, segment, previewSafeTruth, audience, locale, template.TemplateId, template.Payload),
                OutputFormat: template.OutputFormat,
                RouteSegmentId: template.RouteSegmentId,
                DeduplicationKey: deduplicationKey,
                CacheTtl: template.CacheTtl,
                MaxBytes: template.MaxBytes,
                RequiresApproval: template.RequiresApproval,
                PersistOnApproval: template.PersistOnApproval,
                AllowPersistentPinning: template.AllowPersistentPinning),
                $"approved runsite pack '{pack.SourcePackId}' artifact template '{template.TemplateId}'");
        }

        if (!artifacts.Any(static artifact => artifact.Role == RunsiteOrientationArtifactRole.HostClip))
        {
            throw new InvalidDataException(
                $"approved runsite pack '{pack.SourcePackId}' must contribute at least one host clip template.");
        }

        List<RunsiteRouteSummaryArtifactLaunch> routeSummaryArtifactLaunches = new(routeSummary.Segments.Count);
        foreach (RunsiteRouteSummarySegment segment in routeSummary.Segments)
        {
            string deduplicationKey = BuildDeduplicationKey(
                bundleId,
                pack.SourcePackId,
                routeSummary.RouteSummaryId,
                RunsiteOrientationArtifactRole.RoutePreview,
                segment.RouteSegmentId,
                $"route-preview-{segment.RouteSegmentId}");

            AddArtifact(
                artifacts,
                emittedDeduplicationKeys,
                new RunsiteOrientationArtifactRenderRequest(
                Role: RunsiteOrientationArtifactRole.RoutePreview,
                Category: segment.Category,
                Payload: BuildGovernedPayload(pack, routeSummary.RouteSummaryId, segment, previewSafeTruth, audience, locale, "route-preview", segment.PreviewPayload),
                OutputFormat: segment.OutputFormat,
                RouteSegmentId: segment.RouteSegmentId,
                DeduplicationKey: deduplicationKey,
                CacheTtl: TimeSpan.FromMinutes(15),
                MaxBytes: 4 * 1024 * 1024,
                RequiresApproval: false,
                PersistOnApproval: false,
                AllowPersistentPinning: false),
                $"route summary '{routeSummary.RouteSummaryId}' route segment '{segment.RouteSegmentId}'");

            routeSummaryArtifactLaunches.Add(new RunsiteRouteSummaryArtifactLaunch(
                ApprovedRunsitePackId: pack.SourcePackId,
                RouteSummaryId: routeSummary.RouteSummaryId,
                RouteSegmentId: segment.RouteSegmentId,
                InspectableTruthRef: segment.InspectableTruthRef,
                Category: segment.Category,
                OutputFormat: segment.OutputFormat,
                DeduplicationKey: deduplicationKey,
                PreviewTruthPosture: PreviewTruthPosture,
                PreviewSafeTruthSummary: previewSafeTruth.Summary,
                PreviewSafeInspectableTruthRefs: previewSafeTruth.InspectableTruthRefs,
                EvidenceRefs: pack.EvidenceRefs,
                Audience: audience,
                Locale: locale));
        }

        RunsiteOrientationBundleRequest bundleRequest = new(
            BundleId: bundleId,
            ApprovedRunsitePackId: pack.SourcePackId,
            RouteSummaryId: routeSummary.RouteSummaryId,
            Source: $"runsite-orientation-request:{requestedBy}",
            RequestedAtUtc: request.RequestedAtUtc ?? DateTimeOffset.UtcNow,
            Artifacts: artifacts
                .OrderBy(static artifact => artifact.Role.ToString(), StringComparer.OrdinalIgnoreCase)
                .ThenBy(static artifact => artifact.RouteSegmentId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static artifact => artifact.Category, StringComparer.OrdinalIgnoreCase)
                .ToArray());

        return new RunsiteOrientationRequestCompositionResult(
            ContractName: ContractName,
            ContractVersion: ContractVersion,
            RequestedBy: requestedBy,
            Audience: audience,
            Locale: locale,
            PreviewSafeTruth: previewSafeTruth,
            BundleRequest: bundleRequest,
            RouteSummaryArtifactLaunches: routeSummaryArtifactLaunches
                .OrderBy(static launch => launch.RouteSegmentId, StringComparer.OrdinalIgnoreCase)
                .ToArray());
    }

    private static void AddArtifact(
        List<RunsiteOrientationArtifactRenderRequest> artifacts,
        HashSet<string> emittedDeduplicationKeys,
        RunsiteOrientationArtifactRenderRequest artifact,
        string sourceDescription)
    {
        if (!emittedDeduplicationKeys.Add(artifact.DeduplicationKey))
        {
            throw new InvalidDataException(
                $"{sourceDescription} must not emit duplicate deduplication key '{artifact.DeduplicationKey}'.");
        }

        artifacts.Add(artifact);
    }

    private static ApprovedRunsiteOrientationPack NormalizeApprovedRunsitePack(ApprovedRunsiteOrientationPack pack, string audience, string locale)
    {
        ArgumentNullException.ThrowIfNull(pack);
        string sourcePackId = NormalizeToken(pack.SourcePackId, nameof(pack.SourcePackId), allowComma: false);
        string approvalState = NormalizeToken(pack.ApprovalState, nameof(pack.ApprovalState), allowComma: false);
        if (!approvalState.Equals("approved", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"runsite pack '{sourcePackId}' is not approved.");
        }

        string provenanceRef = RequireRouteLikeRef(pack.ProvenanceRef, nameof(pack.ProvenanceRef));
        string routeSummaryId = NormalizeToken(pack.RouteSummaryId, nameof(pack.RouteSummaryId), allowComma: false);
        string? packAudience = NormalizeOptionalToken(pack.Audience, nameof(pack.Audience), allowComma: true);
        string? packLocale = NormalizeOptionalToken(pack.Locale, nameof(pack.Locale), allowComma: false);
        ValidateAudienceAllowance(packAudience, audience, sourcePackId);
        if (packLocale is not null && !packLocale.Equals(locale, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException(
                $"runsite pack '{sourcePackId}' locale '{packLocale}' does not match requested locale '{locale}'.");
        }

        string[] evidenceRefs = (pack.EvidenceRefs ?? Array.Empty<string>())
            .Select(evidence => RequireRouteLikeRef(evidence, nameof(pack.EvidenceRefs)))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (!evidenceRefs.Any())
        {
            throw new InvalidDataException($"runsite pack '{sourcePackId}' must include evidence refs.");
        }

        RunsiteOrientationArtifactTemplate[] templates = (pack.ArtifactTemplates ?? Array.Empty<RunsiteOrientationArtifactTemplate>())
            .Select(NormalizeArtifactTemplate)
            .ToArray();
        if (templates.Length == 0)
        {
            throw new InvalidDataException($"runsite pack '{sourcePackId}' must include artifact templates.");
        }

        return new ApprovedRunsiteOrientationPack(
            SourcePackId: sourcePackId,
            ApprovalState: approvalState,
            ProvenanceRef: provenanceRef,
            EvidenceRefs: evidenceRefs,
            RouteSummaryId: routeSummaryId,
            ArtifactTemplates: templates,
            Audience: packAudience,
            Locale: packLocale);
    }

    private static RunsiteOrientationArtifactTemplate NormalizeArtifactTemplate(RunsiteOrientationArtifactTemplate template)
    {
        ArgumentNullException.ThrowIfNull(template);
        return template with
        {
            TemplateId = NormalizeToken(template.TemplateId, nameof(template.TemplateId), allowComma: false),
            Category = RequireCategory(template.Category, nameof(template.Category)),
            Payload = RequireJsonishPayload(template.Payload, nameof(template.Payload)),
            OutputFormat = NormalizeToken(template.OutputFormat, nameof(template.OutputFormat), allowComma: false),
            RouteSegmentId = NormalizeToken(template.RouteSegmentId, nameof(template.RouteSegmentId), allowComma: false),
            DeduplicationKey = NormalizeToken(template.DeduplicationKey, nameof(template.DeduplicationKey), allowComma: false)
        };
    }

    private static RunsiteRouteSummary NormalizeRouteSummary(RunsiteRouteSummary routeSummary)
    {
        ArgumentNullException.ThrowIfNull(routeSummary);
        string routeSummaryId = NormalizeToken(routeSummary.RouteSummaryId, nameof(routeSummary.RouteSummaryId), allowComma: false);
        if (routeSummary.Segments is null || routeSummary.Segments.Count == 0)
        {
            throw new InvalidDataException("route summary must include at least one segment.");
        }

        HashSet<string> seenRouteSegmentIds = new(StringComparer.OrdinalIgnoreCase);
        RunsiteRouteSummarySegment[] segments = routeSummary.Segments
            .Select(segment =>
            {
                ArgumentNullException.ThrowIfNull(segment);
                string routeSegmentId = NormalizeToken(segment.RouteSegmentId, nameof(segment.RouteSegmentId), allowComma: false);
                if (!seenRouteSegmentIds.Add(routeSegmentId))
                {
                    throw new InvalidDataException($"route summary '{routeSummaryId}' has duplicate route segment '{routeSegmentId}'.");
                }

                return new RunsiteRouteSummarySegment(
                    RouteSegmentId: routeSegmentId,
                    InspectableTruthRef: RequireRouteLikeRef(segment.InspectableTruthRef, nameof(segment.InspectableTruthRef)),
                    PreviewPayload: RequireJsonishPayload(segment.PreviewPayload, nameof(segment.PreviewPayload)),
                    OutputFormat: NormalizeToken(segment.OutputFormat, nameof(segment.OutputFormat), allowComma: false),
                    Category: RequireRoutePreviewCategory(segment.Category, nameof(segment.Category)));
            })
            .ToArray();

        return new RunsiteRouteSummary(
            RouteSummaryId: routeSummaryId,
            Segments: segments);
    }

    private static RunsitePreviewSafePreSessionTruth NormalizePreviewSafeTruth(
        RunsitePreviewSafePreSessionTruth previewSafeTruth,
        RunsiteRouteSummary routeSummary)
    {
        ArgumentNullException.ThrowIfNull(previewSafeTruth);
        if (!string.Equals(previewSafeTruth.PreviewTruthPosture?.Trim(), PreviewTruthPosture, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"preview-safe truth posture must stay '{PreviewTruthPosture}'.");
        }

        string summary = previewSafeTruth.Summary?.Trim()
            ?? throw new InvalidDataException("preview-safe truth summary is required.");
        if (!summary.Contains("inspectable", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("preview-safe truth summary must keep route preview or tour truth inspectable.");
        }

        string[] inspectableTruthRefs = (previewSafeTruth.InspectableTruthRefs ?? Array.Empty<string>())
            .Select(item => RequireRouteLikeRef(item, nameof(previewSafeTruth.InspectableTruthRefs)))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (inspectableTruthRefs.Length == 0)
        {
            throw new InvalidDataException("preview-safe truth must include inspectable truth refs.");
        }

        foreach (RunsiteRouteSummarySegment segment in routeSummary.Segments)
        {
            if (!inspectableTruthRefs.Contains(segment.InspectableTruthRef, StringComparer.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    $"preview-safe truth must include inspectable route ref '{segment.InspectableTruthRef}' for route segment '{segment.RouteSegmentId}'.");
            }
        }

        return new RunsitePreviewSafePreSessionTruth(
            PreviewTruthPosture: PreviewTruthPosture,
            Summary: summary,
            InspectableTruthRefs: inspectableTruthRefs);
    }

    private static string ResolveAudience(string? requestedAudience, ApprovedRunsiteOrientationPack pack)
    {
        string audience = NormalizeOptionalToken(requestedAudience, nameof(requestedAudience), allowComma: true)
            ?? NormalizeOptionalToken(pack?.Audience, nameof(pack.Audience), allowComma: true)
            ?? "campaign-members";
        return audience;
    }

    private static string ResolveLocale(string? requestedLocale, ApprovedRunsiteOrientationPack pack)
    {
        return NormalizeOptionalToken(requestedLocale, nameof(requestedLocale), allowComma: false)
            ?? NormalizeOptionalToken(pack?.Locale, nameof(pack.Locale), allowComma: false)
            ?? "en-US";
    }

    private static void ValidateEvidenceRefs(ApprovedRunsiteOrientationPack pack, string routeSummaryId)
    {
        if (!HasEvidenceAnchor(pack.EvidenceRefs, $"route-summary:{routeSummaryId}"))
        {
            throw new InvalidDataException(
                $"runsite pack '{pack.SourcePackId}' evidence refs must include route-summary:{routeSummaryId}.");
        }

        if (!HasEvidenceAnchor(pack.EvidenceRefs, "preview-safe"))
        {
            throw new InvalidDataException(
                $"runsite pack '{pack.SourcePackId}' evidence refs must include a preview-safe:* anchor.");
        }

        if (!HasEvidenceAnchor(pack.EvidenceRefs, "pre-session"))
        {
            throw new InvalidDataException(
                $"runsite pack '{pack.SourcePackId}' evidence refs must include a pre-session:* anchor.");
        }
    }

    private static void ValidateAudienceAllowance(string? packAudience, string requestedAudience, string sourcePackId)
    {
        if (string.IsNullOrWhiteSpace(packAudience))
        {
            return;
        }

        string[] allowedAudiences = packAudience
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        string[] requestedAudiences = requestedAudience
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (requestedAudiences.Any(requested => !allowedAudiences.Contains(requested, StringComparer.OrdinalIgnoreCase)))
        {
            throw new InvalidDataException(
                $"runsite pack '{sourcePackId}' audience '{packAudience}' does not allow requested audience '{requestedAudience}'.");
        }
    }

    private static string BuildGovernedPayload(
        ApprovedRunsiteOrientationPack pack,
        string routeSummaryId,
        RunsiteRouteSummarySegment segment,
        RunsitePreviewSafePreSessionTruth previewSafeTruth,
        string audience,
        string locale,
        string templateId,
        string payload)
    {
        JsonElement artifactPayload = ParseJsonishPayload(payload, nameof(payload));
        return JsonSerializer.Serialize(new
        {
            sourcePackId = pack.SourcePackId,
            provenanceRef = pack.ProvenanceRef,
            evidenceRefs = pack.EvidenceRefs,
            routeSummaryId,
            routeSegmentId = segment.RouteSegmentId,
            inspectableTruthRef = segment.InspectableTruthRef,
            previewTruthPosture = previewSafeTruth.PreviewTruthPosture,
            previewSafeTruthSummary = previewSafeTruth.Summary,
            previewSafeInspectableTruthRefs = previewSafeTruth.InspectableTruthRefs,
            audience,
            locale,
            templateId,
            payload = artifactPayload
        });
    }

    private static string BuildDeduplicationKey(
        string bundleId,
        string sourcePackId,
        string routeSummaryId,
        RunsiteOrientationArtifactRole role,
        string routeSegmentId,
        string callerDedupeKey)
        => string.Join(
            ".",
            "runsite-orientation",
            bundleId,
            sourcePackId,
            routeSummaryId,
            role.ToString().ToLowerInvariant(),
            routeSegmentId,
            callerDedupeKey);

    private static string NormalizeToken(string? value, string fieldName, bool allowComma)
    {
        string trimmed = value?.Trim()
            ?? throw new InvalidDataException($"{fieldName} is required.");
        if (trimmed.Length == 0)
        {
            throw new InvalidDataException($"{fieldName} is required.");
        }

        Regex pattern = allowComma ? StableAudiencePattern : StableTokenPattern;
        if (!pattern.IsMatch(trimmed))
        {
            throw new InvalidDataException($"{fieldName} '{value}' must use stable token characters.");
        }

        return trimmed;
    }

    private static bool HasEvidenceAnchor(IReadOnlyList<string> evidenceRefs, string requiredPrefix)
        => (evidenceRefs ?? Array.Empty<string>())
            .Any(item => ReceiptRefMatchesRequiredPrefix(item, requiredPrefix));

    private static bool ReceiptRefMatchesRequiredPrefix(string receiptRef, string requiredPrefix)
    {
        string normalizedReceiptRef = receiptRef.Trim();
        return normalizedReceiptRef.Equals(requiredPrefix, StringComparison.OrdinalIgnoreCase)
            || normalizedReceiptRef.StartsWith($"{requiredPrefix}:", StringComparison.OrdinalIgnoreCase);
    }

    private static string? NormalizeOptionalToken(string? value, string fieldName, bool allowComma)
        => string.IsNullOrWhiteSpace(value) ? null : NormalizeToken(value, fieldName, allowComma);

    private static string RequireRouteLikeRef(string? value, string fieldName)
    {
        string trimmed = value?.Trim()
            ?? throw new InvalidDataException($"{fieldName} is required.");
        if (!trimmed.StartsWith("/", StringComparison.Ordinal) && !trimmed.Contains(':', StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{fieldName} '{value}' must stay on first-party route refs or governed receipt refs.");
        }

        if (trimmed.Contains("://", StringComparison.Ordinal) || trimmed.StartsWith("//", StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{fieldName} '{value}' must not use external absolute URLs.");
        }

        return trimmed;
    }

    private static string RequireCategory(string? value, string fieldName)
    {
        string trimmed = value?.Trim()
            ?? throw new InvalidDataException($"{fieldName} is required.");
        if (!trimmed.StartsWith("runsite/orientation/", StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{fieldName} '{value}' must stay inside runsite/orientation categories.");
        }

        return trimmed;
    }

    private static string RequireRoutePreviewCategory(string? value, string fieldName)
    {
        string trimmed = RequireCategory(value, fieldName);
        if (!trimmed.Equals(RoutePreviewCategory, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{fieldName} '{value}' must stay '{RoutePreviewCategory}' so route_summary:artifact_launch remains route-summary governed.");
        }

        return trimmed;
    }

    private static string RequireJsonishPayload(string? value, string fieldName)
    {
        string trimmed = value?.Trim()
            ?? throw new InvalidDataException($"{fieldName} is required.");
        return JsonSerializer.Serialize(ParseJsonishPayload(trimmed, fieldName));
    }

    private static JsonElement ParseJsonishPayload(string value, string fieldName)
    {
        string trimmed = value.Trim();
        if (!(trimmed.StartsWith("{", StringComparison.Ordinal) || trimmed.StartsWith("[", StringComparison.Ordinal)))
        {
            throw new InvalidDataException($"{fieldName} must be JSON-shaped preview-safe content.");
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(trimmed);
            return document.RootElement.Clone();
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException($"{fieldName} must be valid JSON-shaped preview-safe content.", ex);
        }
    }
}
