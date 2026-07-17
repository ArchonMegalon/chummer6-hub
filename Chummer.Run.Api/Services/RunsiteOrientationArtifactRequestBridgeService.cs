using Chummer.Run.Api.Services.Community;

namespace Chummer.Run.Api.Services;

public sealed class RunsiteOrientationArtifactRequestBridgeService
{
    private const string DefaultPreferredProvider = "magicai";

    private readonly RunsiteOrientationRequestComposerService _composer;

    public RunsiteOrientationArtifactRequestBridgeService(RunsiteOrientationRequestComposerService composer)
    {
        _composer = composer;
    }

    public RunsiteOrientationArtifactRequestBridgePayload Compose(RunsiteOrientationArtifactRequestBridgeRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(request.OrientationRequest);

        RunsiteOrientationRequestCompositionResult orientationRequest = _composer.Compose(request.OrientationRequest);
        string preferredProvider = string.IsNullOrWhiteSpace(request.PreferredProvider)
            ? DefaultPreferredProvider
            : request.PreferredProvider.Trim();

        HorizonArtifactRequestCreateRequest artifactRequest = new(
            HorizonId: "runsite",
            ArtifactKindOrCapabilityId: "runsite-scene-render",
            UserId: request.UserId,
            SourceRef: BuildSourceRef(orientationRequest.BundleRequest),
            Visibility: request.Visibility,
            ExternalProcessingConsent: request.ExternalProcessingConsent,
            Email: request.Email,
            GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(
                WorkItemId: orientationRequest.BundleRequest.BundleId,
                RequestedBy: orientationRequest.RequestedBy,
                Subject: ResolveSubject(request.Subject, orientationRequest.BundleRequest),
                Audience: orientationRequest.Audience,
                Locale: orientationRequest.Locale,
                PreferredProvider: preferredProvider,
                TruthRefs: BuildTruthRefs(orientationRequest),
                EvidenceRefs: BuildEvidenceRefs(orientationRequest),
                Artifacts: BuildArtifacts(orientationRequest)));

        return new RunsiteOrientationArtifactRequestBridgePayload(
            OrientationRequest: orientationRequest,
            ArtifactRequest: artifactRequest,
            ConsumeQuota: request.ConsumeQuota);
    }

    private static string BuildSourceRef(RunsiteOrientationBundleRequest bundleRequest)
        => $"runsite:orientation:{bundleRequest.ApprovedRunsitePackId}:{bundleRequest.RouteSummaryId}:{bundleRequest.BundleId}";

    private static string ResolveSubject(string? subject, RunsiteOrientationBundleRequest bundleRequest)
        => string.IsNullOrWhiteSpace(subject)
            ? $"{bundleRequest.ApprovedRunsitePackId} orientation {bundleRequest.RouteSummaryId}"
            : subject.Trim();

    private static IReadOnlyList<string> BuildTruthRefs(RunsiteOrientationRequestCompositionResult orientationRequest)
        => orientationRequest.RouteSummaryArtifactLaunches
            .Select(static launch => launch.InspectableTruthRef)
            .Concat(orientationRequest.PreviewSafeTruth.InspectableTruthRefs ?? Array.Empty<string>())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static IReadOnlyList<string> BuildEvidenceRefs(RunsiteOrientationRequestCompositionResult orientationRequest)
        => orientationRequest.RouteSummaryArtifactLaunches
            .SelectMany(static launch => launch.EvidenceRefs ?? Array.Empty<string>())
            .Append($"route-summary:{orientationRequest.BundleRequest.RouteSummaryId}")
            .Append($"runsite:{orientationRequest.BundleRequest.ApprovedRunsitePackId}")
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static IReadOnlyList<HorizonGovernedRenderArtifactSpec> BuildArtifacts(RunsiteOrientationRequestCompositionResult orientationRequest)
        => orientationRequest.BundleRequest.Artifacts
            .Select(MapArtifact)
            .ToArray();

    private static HorizonGovernedRenderArtifactSpec MapArtifact(RunsiteOrientationArtifactRenderRequest artifact)
    {
        string role = artifact.Role switch
        {
            RunsiteOrientationArtifactRole.HostClip => "host_clip",
            RunsiteOrientationArtifactRole.RoutePreview => "route_preview",
            RunsiteOrientationArtifactRole.AudioCompanion => "audio_companion",
            RunsiteOrientationArtifactRole.TourSibling => "tour_sibling",
            _ => "orientation_artifact"
        };

        return new HorizonGovernedRenderArtifactSpec(
            ArtifactId: $"{role}-{artifact.RouteSegmentId}",
            Role: role,
            Category: artifact.Category,
            Payload: artifact.Payload,
            OutputFormat: artifact.OutputFormat,
            DeduplicationKey: artifact.DeduplicationKey,
            MaxBytes: artifact.MaxBytes,
            RequiresApproval: artifact.RequiresApproval,
            PersistOnApproval: artifact.PersistOnApproval,
            AllowPersistentPinning: artifact.AllowPersistentPinning);
    }
}

public sealed record RunsiteOrientationArtifactRequestBridgeRequest(
    string UserId,
    RunsiteOrientationRequestComposeRequest OrientationRequest,
    string Visibility = "private",
    bool ExternalProcessingConsent = true,
    string? Email = null,
    string? PreferredProvider = "magicai",
    bool ConsumeQuota = true,
    string? Subject = null);

public sealed record RunsiteOrientationArtifactRequestBridgePayload(
    RunsiteOrientationRequestCompositionResult OrientationRequest,
    HorizonArtifactRequestCreateRequest ArtifactRequest,
    bool ConsumeQuota);

public sealed record RunsiteOrientationArtifactRequestBridgeResult(
    RunsiteOrientationRequestCompositionResult OrientationRequest,
    HorizonArtifactRequestReceipt ArtifactRequestReceipt);
