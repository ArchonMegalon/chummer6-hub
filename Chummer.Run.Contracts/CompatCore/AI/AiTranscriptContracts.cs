namespace Chummer.Contracts.AI;

public static class AiTranscriptApiOperations
{
    public const string SubmitTranscript = "submit-transcript";
    public const string GetTranscript = "get-transcript";
}

public static class AiTranscriptStates
{
    public const string Pending = "pending";
    public const string Transcribed = "transcribed";
}

public sealed record AiTranscriptSubmissionRequest(
    string FileName,
    string ContentType,
    string? SessionId = null,
    string? CharacterId = null,
    string? Notes = null);

public sealed record AiTranscriptDocumentReceipt(
    string TranscriptId,
    string State,
    string Message,
    bool ExternalProviderConfigured = false,
    string? SessionId = null,
    string? CharacterId = null,
    string? OwnerId = null);
