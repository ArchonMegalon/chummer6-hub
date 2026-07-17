using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonGovernedRenderRequestComposerService
{
    public const string OrchestrationLane = "ea_governed_render";
    public const string ContractName = "chummer6-hub.horizon_governed_render_request.v1";
    public const string ContractVersion = "2026-06-30";

    private static readonly Regex StableTokenPattern = new("^[A-Za-z0-9._:-]+$", RegexOptions.Compiled);
    private static readonly Regex CategoryPattern = new("^[A-Za-z0-9._/-]+$", RegexOptions.Compiled);

    public HorizonGovernedRenderRequestCompositionResult Compose(
        HorizonCapabilityDefinition capability,
        string sourceRef,
        HorizonGovernedRenderRequestCreateRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        List<string> blocked = [];
        string normalizedSourceRef = NormalizeGovernedRef(sourceRef, "governed render source reference", blocked);
        if (!string.Equals(capability.OrchestrationLane, OrchestrationLane, StringComparison.OrdinalIgnoreCase))
        {
            blocked.Add("governed render lane");
        }

        string workItemId = NormalizeStableToken(request.WorkItemId, "governed render work item", blocked);
        string requestedBy = NormalizeStableToken(request.RequestedBy, "governed render requested by", blocked);
        string audience = NormalizeStableToken(request.Audience, "governed render audience", blocked);
        string locale = NormalizeStableToken(request.Locale, "governed render locale", blocked);
        string subject = NormalizeSubject(request.Subject, blocked);
        string? preferredProvider = NormalizeOptionalStableToken(request.PreferredProvider, "governed render preferred provider", blocked);

        string[] truthRefs = NormalizeRefList(
            request.TruthRefs,
            "governed render truth refs",
            normalizedSourceRef,
            blocked);
        string[] evidenceRefs = NormalizeRefList(
            request.EvidenceRefs,
            "governed render evidence refs",
            fallbackRef: null,
            blocked);
        if (evidenceRefs.Length == 0)
        {
            blocked.Add("governed render evidence refs");
        }

        HorizonGovernedRenderArtifactSpec[] artifacts = NormalizeArtifacts(request.Artifacts, blocked);
        if (blocked.Count > 0)
        {
            return new HorizonGovernedRenderRequestCompositionResult(false, blocked, null);
        }

        return new HorizonGovernedRenderRequestCompositionResult(
            Accepted: true,
            BlockedReasons: Array.Empty<string>(),
            Contract: new HorizonGovernedRenderRequestContract(
                ContractName: ContractName,
                ContractVersion: ContractVersion,
                OrchestrationLane: OrchestrationLane,
                HorizonId: capability.HorizonId,
                CapabilityId: capability.CapabilityId,
                ArtifactKind: capability.ArtifactKind,
                CapabilitySlot: capability.CapabilitySlot,
                SourceRef: normalizedSourceRef,
                WorkItemId: workItemId,
                RequestedBy: requestedBy,
                Subject: subject,
                Audience: audience,
                Locale: locale,
                PreferredProvider: preferredProvider,
                TruthRefs: truthRefs,
                EvidenceRefs: evidenceRefs,
                Artifacts: artifacts));
    }

    private static HorizonGovernedRenderArtifactSpec[] NormalizeArtifacts(
        IReadOnlyList<HorizonGovernedRenderArtifactSpec>? artifacts,
        List<string> blocked)
    {
        if (artifacts is null || artifacts.Count == 0)
        {
            blocked.Add("governed render artifacts");
            return Array.Empty<HorizonGovernedRenderArtifactSpec>();
        }

        HashSet<string> seenDeduplicationKeys = new(StringComparer.OrdinalIgnoreCase);
        List<HorizonGovernedRenderArtifactSpec> normalized = new(artifacts.Count);
        foreach (HorizonGovernedRenderArtifactSpec artifact in artifacts)
        {
            if (artifact is null)
            {
                blocked.Add("governed render artifacts");
                continue;
            }

            string artifactId = NormalizeStableToken(artifact.ArtifactId, "governed render artifact id", blocked);
            string role = NormalizeStableToken(artifact.Role, "governed render artifact role", blocked);
            string category = NormalizeCategory(artifact.Category, blocked);
            string payload = NormalizePayload(artifact.Payload, blocked);
            string outputFormat = NormalizeStableToken(artifact.OutputFormat, "governed render artifact output format", blocked);
            string deduplicationKey = NormalizeStableToken(artifact.DeduplicationKey, "governed render artifact deduplication key", blocked);
            string? aspectRatio = NormalizeOptionalStableToken(artifact.AspectRatio, "governed render artifact aspect ratio", blocked);
            string? durationProfile = NormalizeOptionalStableToken(artifact.DurationProfile, "governed render artifact duration profile", blocked);
            if (artifact.MaxBytes < 0)
            {
                blocked.Add("governed render artifact max bytes");
            }

            if (!string.IsNullOrWhiteSpace(deduplicationKey) && !seenDeduplicationKeys.Add(deduplicationKey))
            {
                blocked.Add("governed render artifact deduplication key");
            }

            normalized.Add(new HorizonGovernedRenderArtifactSpec(
                ArtifactId: artifactId,
                Role: role,
                Category: category,
                Payload: payload,
                OutputFormat: outputFormat,
                DeduplicationKey: deduplicationKey,
                AspectRatio: aspectRatio,
                DurationProfile: durationProfile,
                MaxBytes: artifact.MaxBytes,
                RequiresApproval: artifact.RequiresApproval,
                PersistOnApproval: artifact.PersistOnApproval,
                AllowPersistentPinning: artifact.AllowPersistentPinning));
        }

        return normalized
            .OrderBy(static item => item.Role, StringComparer.OrdinalIgnoreCase)
            .ThenBy(static item => item.ArtifactId, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string[] NormalizeRefList(
        IReadOnlyList<string>? refs,
        string blockedReason,
        string? fallbackRef,
        List<string> blocked)
    {
        List<string> normalized = [];
        if (!string.IsNullOrWhiteSpace(fallbackRef))
        {
            normalized.Add(fallbackRef.Trim());
        }

        foreach (string? value in refs ?? Array.Empty<string>())
        {
            string normalizedValue = NormalizeGovernedRef(value, blockedReason, blocked);
            if (!string.IsNullOrWhiteSpace(normalizedValue))
            {
                normalized.Add(normalizedValue);
            }
        }

        return normalized
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string NormalizeStableToken(string? value, string blockedReason, List<string> blocked)
    {
        string normalized = Clean(value);
        if (string.IsNullOrWhiteSpace(normalized) || !StableTokenPattern.IsMatch(normalized))
        {
            blocked.Add(blockedReason);
            return string.Empty;
        }

        return normalized;
    }

    private static string? NormalizeOptionalStableToken(string? value, string blockedReason, List<string> blocked)
    {
        string normalized = Clean(value);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return null;
        }

        if (!StableTokenPattern.IsMatch(normalized))
        {
            blocked.Add(blockedReason);
            return null;
        }

        return normalized;
    }

    private static string NormalizeCategory(string? value, List<string> blocked)
    {
        string normalized = Clean(value);
        if (string.IsNullOrWhiteSpace(normalized) || !CategoryPattern.IsMatch(normalized))
        {
            blocked.Add("governed render artifact category");
            return string.Empty;
        }

        return normalized;
    }

    private static string NormalizePayload(string? value, List<string> blocked)
    {
        string normalized = Clean(value);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            blocked.Add("governed render artifact payload");
            return string.Empty;
        }

        return normalized;
    }

    private static string NormalizeSubject(string? value, List<string> blocked)
    {
        string normalized = Clean(value);
        if (string.IsNullOrWhiteSpace(normalized) || normalized.Length > 160 || normalized.Contains('\n') || normalized.Contains('\r'))
        {
            blocked.Add("governed render subject");
            return string.Empty;
        }

        return normalized;
    }

    private static string NormalizeGovernedRef(string? value, string blockedReason, List<string> blocked)
    {
        string normalized = Clean(value);
        if (string.IsNullOrWhiteSpace(normalized)
            || normalized.Contains("://", StringComparison.Ordinal)
            || normalized.Contains(' '))
        {
            blocked.Add(blockedReason);
            return string.Empty;
        }

        if (normalized.StartsWith("/", StringComparison.Ordinal))
        {
            return normalized;
        }

        if (StableTokenPattern.IsMatch(normalized))
        {
            return normalized;
        }

        blocked.Add(blockedReason);
        return string.Empty;
    }

    private static string Clean(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();
}

public sealed record HorizonGovernedRenderRequestCreateRequest(
    string WorkItemId,
    string RequestedBy,
    string Subject,
    string Audience,
    string Locale,
    string? PreferredProvider = null,
    IReadOnlyList<string>? TruthRefs = null,
    IReadOnlyList<string>? EvidenceRefs = null,
    IReadOnlyList<HorizonGovernedRenderArtifactSpec>? Artifacts = null);

public sealed record HorizonGovernedRenderArtifactSpec(
    string ArtifactId,
    string Role,
    string Category,
    string Payload,
    string OutputFormat,
    string DeduplicationKey,
    string? AspectRatio = null,
    string? DurationProfile = null,
    int MaxBytes = 0,
    bool RequiresApproval = false,
    bool PersistOnApproval = false,
    bool AllowPersistentPinning = true);

public sealed record HorizonGovernedRenderRequestContract(
    string ContractName,
    string ContractVersion,
    string OrchestrationLane,
    string HorizonId,
    string CapabilityId,
    string ArtifactKind,
    string CapabilitySlot,
    string SourceRef,
    string WorkItemId,
    string RequestedBy,
    string Subject,
    string Audience,
    string Locale,
    string? PreferredProvider,
    IReadOnlyList<string> TruthRefs,
    IReadOnlyList<string> EvidenceRefs,
    IReadOnlyList<HorizonGovernedRenderArtifactSpec> Artifacts);

public sealed record HorizonGovernedRenderRequestCompositionResult(
    bool Accepted,
    IReadOnlyList<string> BlockedReasons,
    HorizonGovernedRenderRequestContract? Contract);
