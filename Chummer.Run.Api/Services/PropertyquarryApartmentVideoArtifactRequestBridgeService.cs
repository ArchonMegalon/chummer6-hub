using System.Text;
using Chummer.Run.Api.Services.Community;

namespace Chummer.Run.Api.Services;

public sealed class PropertyquarryApartmentVideoArtifactRequestBridgeService
{
    private const string DefaultPreferredProvider = "magicai";

    private readonly MediaArtifactHorizonsService _mediaHorizons;

    public PropertyquarryApartmentVideoArtifactRequestBridgeService(MediaArtifactHorizonsService mediaHorizons)
    {
        _mediaHorizons = mediaHorizons;
    }

    public PropertyquarryApartmentVideoArtifactRequestBridgePayload Compose(PropertyquarryApartmentVideoArtifactRequestBridgeRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        MediaArtifactDocument property = _mediaHorizons.GetPropertyquarryProperty(request.PropertyId);
        string workItemId = Clean(request.WorkItemId);
        string preferredProvider = string.IsNullOrWhiteSpace(request.PreferredProvider)
            ? DefaultPreferredProvider
            : request.PreferredProvider.Trim();

        HorizonArtifactRequestCreateRequest artifactRequest = new(
            HorizonId: "propertyquarry",
            ArtifactKindOrCapabilityId: "propertyquarry-apartment-video",
            UserId: request.UserId,
            SourceRef: BuildSourceRef(property, workItemId),
            Visibility: request.Visibility,
            ExternalProcessingConsent: request.ExternalProcessingConsent,
            Email: request.Email,
            GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(
                WorkItemId: workItemId,
                RequestedBy: ResolveRequestedBy(request.RequestedBy),
                Subject: ResolveSubject(request.Subject, property),
                Audience: ResolveAudience(request.Audience),
                Locale: ResolveLocale(request.Locale),
                PreferredProvider: preferredProvider,
                TruthRefs: BuildTruthRefs(property, request.TruthRefs),
                EvidenceRefs: BuildEvidenceRefs(property, request.EvidenceRefs),
                Artifacts: BuildArtifacts(property, workItemId, request.Artifacts)));

        return new PropertyquarryApartmentVideoArtifactRequestBridgePayload(
            Property: property,
            ArtifactRequest: artifactRequest,
            ConsumeQuota: request.ConsumeQuota);
    }

    private static string BuildSourceRef(MediaArtifactDocument property, string workItemId)
    {
        string sourceRef = $"propertyquarry:apartment-video:{property.Id}:{workItemId}";
        return sourceRef.TrimEnd(':');
    }

    private static string ResolveRequestedBy(string? value)
        => string.IsNullOrWhiteSpace(value) ? "ea.ops" : value.Trim();

    private static string ResolveSubject(string? value, MediaArtifactDocument property)
        => string.IsNullOrWhiteSpace(value)
            ? $"{property.Label} apartment video"
            : value.Trim();

    private static string ResolveAudience(string? value)
        => string.IsNullOrWhiteSpace(value) ? "players" : value.Trim();

    private static string ResolveLocale(string? value)
        => string.IsNullOrWhiteSpace(value) ? "en-US" : value.Trim();

    private static IReadOnlyList<string> BuildTruthRefs(MediaArtifactDocument property, IReadOnlyList<string>? extras)
        => MergeRefs(
            extras,
            $"propertyquarry:{property.Id}",
            property.MarkdownRoute,
            property.JsonRoute);

    private static IReadOnlyList<string> BuildEvidenceRefs(MediaArtifactDocument property, IReadOnlyList<string>? extras)
    {
        List<string> refs =
        [
            $"propertyquarry:property-packet:{property.Id}",
            $"propertyquarry:account-route:{property.Id}",
            $"propertyquarry:property-continuity:{property.Id}"
        ];
        string? styleToken = NormalizeStableFragment(property.Style);
        if (!string.IsNullOrWhiteSpace(styleToken))
        {
            refs.Add($"propertyquarry:style:{styleToken}");
        }

        return MergeRefs(extras, refs.ToArray());
    }

    private static IReadOnlyList<string> MergeRefs(IReadOnlyList<string>? extras, params string[] defaults)
        => defaults
            .Concat(extras ?? Array.Empty<string>())
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static IReadOnlyList<HorizonGovernedRenderArtifactSpec> BuildArtifacts(
        MediaArtifactDocument property,
        string workItemId,
        IReadOnlyList<PropertyquarryApartmentVideoArtifactRenderRequest>? artifacts)
        => (artifacts ?? Array.Empty<PropertyquarryApartmentVideoArtifactRenderRequest>())
            .Select(item => MapArtifact(property, workItemId, item))
            .ToArray();

    private static HorizonGovernedRenderArtifactSpec MapArtifact(
        MediaArtifactDocument property,
        string workItemId,
        PropertyquarryApartmentVideoArtifactRenderRequest artifact)
    {
        string role = Clean(artifact.Role);
        string roleToken = NormalizeStableFragment(role) ?? "artifact";
        string dedupBase = string.IsNullOrWhiteSpace(workItemId) ? property.Id : workItemId;
        return new HorizonGovernedRenderArtifactSpec(
            ArtifactId: string.IsNullOrWhiteSpace(artifact.ArtifactId) ? roleToken : artifact.ArtifactId.Trim(),
            Role: role,
            Category: string.IsNullOrWhiteSpace(artifact.Category)
                ? $"propertyquarry/apartment-video/{roleToken}"
                : artifact.Category.Trim(),
            Payload: artifact.Payload,
            OutputFormat: artifact.OutputFormat,
            DeduplicationKey: string.IsNullOrWhiteSpace(artifact.DeduplicationKey) ? $"{dedupBase}:{roleToken}" : artifact.DeduplicationKey.Trim(),
            AspectRatio: CleanToNull(artifact.AspectRatio),
            DurationProfile: CleanToNull(artifact.DurationProfile),
            MaxBytes: artifact.MaxBytes,
            RequiresApproval: artifact.RequiresApproval,
            PersistOnApproval: artifact.PersistOnApproval,
            AllowPersistentPinning: artifact.AllowPersistentPinning);
    }

    private static string? NormalizeStableFragment(string? value)
    {
        string normalized = Clean(value);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return null;
        }

        StringBuilder builder = new(normalized.Length);
        bool previousWasDash = false;
        foreach (char character in normalized)
        {
            if (char.IsLetterOrDigit(character))
            {
                builder.Append(char.ToLowerInvariant(character));
                previousWasDash = false;
                continue;
            }

            if (!previousWasDash)
            {
                builder.Append('-');
                previousWasDash = true;
            }
        }

        return builder.ToString().Trim('-');
    }

    private static string Clean(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();

    private static string? CleanToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}

public sealed record PropertyquarryApartmentVideoArtifactRequestBridgeRequest(
    string UserId,
    string PropertyId,
    string WorkItemId,
    IReadOnlyList<PropertyquarryApartmentVideoArtifactRenderRequest> Artifacts,
    string RequestedBy = "ea.ops",
    string Visibility = "private",
    bool ExternalProcessingConsent = true,
    string? Email = null,
    string? PreferredProvider = "magicai",
    bool ConsumeQuota = true,
    string? Subject = null,
    string Audience = "players",
    string Locale = "en-US",
    IReadOnlyList<string>? TruthRefs = null,
    IReadOnlyList<string>? EvidenceRefs = null);

public sealed record PropertyquarryApartmentVideoArtifactRenderRequest(
    string Role,
    string Payload,
    string OutputFormat,
    string? ArtifactId = null,
    string? Category = null,
    string? DeduplicationKey = null,
    string? AspectRatio = null,
    string? DurationProfile = null,
    int MaxBytes = 0,
    bool RequiresApproval = true,
    bool PersistOnApproval = true,
    bool AllowPersistentPinning = true);

public sealed record PropertyquarryApartmentVideoArtifactRequestBridgePayload(
    MediaArtifactDocument Property,
    HorizonArtifactRequestCreateRequest ArtifactRequest,
    bool ConsumeQuota);

public sealed record PropertyquarryApartmentVideoArtifactRequestBridgeResult(
    PropertyquarryApartmentVideoArtifactRequestBridgePayload Payload,
    HorizonArtifactRequestReceipt ArtifactRequestReceipt);
