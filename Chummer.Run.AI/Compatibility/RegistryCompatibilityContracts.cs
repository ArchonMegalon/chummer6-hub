namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Hub.Registry.Contracts.HubArtifactCreateRequest.")]
internal sealed record HubProjectRequest(
    string Name,
    string Type,
    string Version,
    string Owner);

[Obsolete("Use Chummer.Hub.Registry.Contracts.HubArtifactMetadata or Chummer.Run.Contracts.Registry.RegistryProjectionResponse.")]
internal sealed record HubArtifactResponse(
    string Id,
    string Name,
    string Type,
    string Version,
    string State);

[Obsolete("Use Chummer.Run.Contracts.Registry.HubInstallEvent.")]
internal sealed record HubInstallEvent(
    string ArtifactId,
    string UserId,
    DateTimeOffset InstalledAtUtc,
    bool ActiveRuntimeRef);

[Obsolete("Use Chummer.Run.Contracts.Registry.HubReviewRequest.")]
internal sealed record HubReviewRequest(
    string ArtifactId,
    int Score,
    string? Comment = null);

[Obsolete("Use Chummer.Run.Contracts.Registry.HubReviewResponse.")]
internal sealed record HubReviewResponse(
    string ArtifactId,
    double AverageScore,
    int ReviewCount);
