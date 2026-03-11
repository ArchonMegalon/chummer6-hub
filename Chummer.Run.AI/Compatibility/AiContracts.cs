using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Run.Contracts.Gateway.SubmitObservationRequest.")]
internal sealed record SubmitObservationRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SessionId,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Source,
    [property: Required(AllowEmptyStrings = false), StringLength(8000)] string Payload,
    DateTimeOffset ObservedAtUtc);

[Obsolete("Use Chummer.Run.Contracts.Gateway.SubmitObservationResponse.")]
internal sealed record SubmitObservationResponse(
    string ObservationId,
    string Status,
    DateTimeOffset AcceptedAtUtc);
