using System.ComponentModel.DataAnnotations;
using CanonicalTranscriptionProvider = Chummer.Run.Contracts.Transcription.ITranscriptionProvider;
using CanonicalTranscriptionRequest = Chummer.Run.Contracts.Transcription.TranscriptionRequest;

namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Run.Contracts.Transcription.TranscriptionRequest.")]
internal sealed record TranscriptionRequest(
    [Required(AllowEmptyStrings = false), StringLength(2048)] string Source,
    string? MimeType,
    string? LanguageHint,
    bool PreserveSpeakerTurns);

[Obsolete("Use Chummer.Run.Contracts.Transcription.TranscriptionWarning.")]
internal sealed record TranscriptionWarning(
    string Code,
    string Message);

[Obsolete("Use Chummer.Run.Contracts.Transcription.TranscriptionResult.")]
internal sealed record TranscriptionResult(
    bool Accepted,
    string Transcript,
    double Confidence,
    IReadOnlyList<TranscriptionWarning> Warnings);

[Obsolete("Use Chummer.Run.Contracts.Transcription.ITranscriptionProvider through LegacyTranscriptionProviderAdapter when a legacy AI namespace dependency still exists.")]
internal interface ITranscriptionProvider
{
    Task<TranscriptionResult> TranscribeAsync(
        TranscriptionRequest request,
        CancellationToken cancellationToken = default);
}

#pragma warning disable CS0618
internal sealed class LegacyTranscriptionProviderAdapter : ITranscriptionProvider
{
    private readonly CanonicalTranscriptionProvider _inner;

    public LegacyTranscriptionProviderAdapter(CanonicalTranscriptionProvider inner)
    {
        _inner = inner;
    }

    public async Task<TranscriptionResult> TranscribeAsync(
        TranscriptionRequest request,
        CancellationToken cancellationToken = default)
    {
        var result = await _inner.TranscribeAsync(
            new CanonicalTranscriptionRequest(request.Source, request.MimeType, request.LanguageHint, request.PreserveSpeakerTurns),
            cancellationToken).ConfigureAwait(false);

        return new TranscriptionResult(
            result.Accepted,
            result.Transcript,
            result.Confidence,
            result.Warnings.Select(static warning => new TranscriptionWarning(warning.Code, warning.Message)).ToArray());
    }
}
#pragma warning restore CS0618
