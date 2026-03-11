
namespace Chummer.Run.AI.Services.Spider;

public interface IFastSignalDetector
{
    FastSignal? Detect(SpiderObservation observation);
}

public sealed class FastSignalDetector : IFastSignalDetector
{
    private static readonly string[] SceneShiftMarkers =
    [
        "scene:",
        "scene shift",
        "transfer to",
        "new location",
        "cut to",
        "fade out"
    ];

    private static readonly string[] ThreatKeywords =
    [
        "edge",
        "god",
        "overwatch",
        "alarm",
        "drone",
        "fireball",
        "matrix",
        "attunement",
        "hosted"
    ];

    public FastSignal? Detect(SpiderObservation observation)
    {
        if (string.IsNullOrWhiteSpace(observation.Payload))
        {
            return null;
        }

        var payload = observation.Payload.ToLowerInvariant();
        var hits = ThreatKeywords.Count(keyword => payload.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            + SceneShiftMarkers.Count(keyword => payload.Contains(keyword, StringComparison.OrdinalIgnoreCase)) * 2;
        if (hits == 0)
        {
            return null;
        }

        var confidence = Math.Min(100, 32 + hits * 18);
        var shouldEscalate = confidence >= 45 || payload.Contains("god", StringComparison.OrdinalIgnoreCase);

        return new FastSignal(
            SessionId: observation.SessionId,
            Signal: $"{hits} matching trigger(s)",
            Confidence: confidence,
            Escalate: shouldEscalate);
    }
}
