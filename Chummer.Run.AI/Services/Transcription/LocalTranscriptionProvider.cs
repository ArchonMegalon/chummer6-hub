using Chummer.Run.Contracts.Transcription;

namespace Chummer.Run.AI.Services.Transcription;

public sealed class LocalTranscriptionProvider : ITranscriptionProvider
{
    public Task<TranscriptionResult> TranscribeAsync(
        TranscriptionRequest request,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(request.Source))
        {
            var resultEmpty = new TranscriptionResult(
                Accepted: false,
                Transcript: "Transcript unavailable.",
                Confidence: 0.0d,
                Warnings: new[]
                {
                    new TranscriptionWarning("missing_source", "No source content was provided.")
                });

            return Task.FromResult(resultEmpty);
        }

        var source = request.Source.Trim();
        var preservedTurns = request.PreserveSpeakerTurns
            ? "speaker-preserved"
            : "single-speaker-stream";
        var warningList = new List<TranscriptionWarning>();
        var normalized = source.Length > 4_000
            ? $"{source[..4_000]}..."
            : source;
        var transcript = $"[{preservedTurns}] {normalized}";

        var confidence = source.Contains("[unverified]", StringComparison.OrdinalIgnoreCase)
            ? 0.52d
            : Math.Clamp(source.Length switch
            {
                <= 80 => 0.64d,
                <= 320 => 0.76d,
                _ => 0.89d
            }, 0.2d, 0.99d);

        if (!request.PreserveSpeakerTurns)
        {
            warningList.Add(new TranscriptionWarning(
                "speaker_turns_merged",
                "Request disabled speaker-turn preservation. Canonical downstream may require manual review."));
        }

        if (source.Contains("http", StringComparison.OrdinalIgnoreCase))
        {
            warningList.Add(new TranscriptionWarning(
                "hallucination_risk",
                "Source appears to be URL-like metadata; confidence reduced and transcript may include placeholders."));
        }

        if (warningList.Count == 0)
        {
            warningList.Add(new TranscriptionWarning("clean_room_stub", "Local transcription provider is a scaffold and should be approved before canon writes."));
        }

        var result = new TranscriptionResult(
            Accepted: true,
            Transcript: transcript,
            Confidence: confidence,
            Warnings: warningList);

        return Task.FromResult(result);
    }

}
