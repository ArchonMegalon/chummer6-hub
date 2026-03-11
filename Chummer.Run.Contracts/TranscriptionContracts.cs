using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Transcription;

public sealed record TranscriptionRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(2048)] string Source,
    string? MimeType,
    string? LanguageHint,
    bool PreserveSpeakerTurns);

public sealed record TranscriptionWarning(
    string Code,
    string Message);

public sealed record TranscriptionResult(
    bool Accepted,
    string Transcript,
    double Confidence,
    IReadOnlyList<TranscriptionWarning> Warnings);

public interface ITranscriptionProvider
{
    Task<TranscriptionResult> TranscribeAsync(
        TranscriptionRequest request,
        CancellationToken cancellationToken = default);
}
