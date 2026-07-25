namespace Chummer.Run.Api.Services;

/// <summary>
/// Background-only publication probe for the durable shelf activation protocol.
/// It performs bounded local reads and returns stable non-identifying codes.
/// </summary>
public sealed class ReleaseShelfActivationProtocolReadinessProbe
    : IReleaseShelfPublicationReadinessProbe
{
    private readonly ReleaseBundlePromotionService _promotion;
    private readonly ReleaseBundleUploadSessionService _sessions;

    public ReleaseShelfActivationProtocolReadinessProbe(
        ReleaseBundlePromotionService promotion,
        ReleaseBundleUploadSessionService sessions)
    {
        _promotion = promotion;
        _sessions = sessions;
    }

    public string Name => HubDeepReadinessService.ActivationProtocolProbeName;

    public ValueTask<ReleaseShelfPublicationReadinessProbeResult> EvaluateAsync(
        ReleaseShelfSnapshot snapshot,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        cancellationToken.ThrowIfCancellationRequested();
        ReleaseShelfPublicationReadinessProbeResult journal =
            _promotion.EvaluateActivationProtocolReadiness(snapshot, cancellationToken);
        if (!journal.Ready)
        {
            return ValueTask.FromResult(journal);
        }

        ReleaseUploadStorageReadiness sessions =
            _sessions.EvaluateActivationProtocolReadiness(cancellationToken);
        return ValueTask.FromResult(new ReleaseShelfPublicationReadinessProbeResult(
            sessions.Ready,
            sessions.Code));
    }
}
