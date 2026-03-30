using System.Collections.Concurrent;
using SubmitObservationRequest = Chummer.Run.Contracts.Gateway.SubmitObservationRequest;
using SubmitObservationResponse = Chummer.Run.Contracts.Gateway.SubmitObservationResponse;

namespace Chummer.Run.AI.Services.Observation;

public interface IObservationSubmissionService
{
    SubmitObservationResponse Submit(SubmitObservationRequest request);
}

public sealed class InMemoryObservationSubmissionService : IObservationSubmissionService
{
    private readonly ConcurrentDictionary<string, SubmitObservationResponse> _observations = new();

    public SubmitObservationResponse Submit(SubmitObservationRequest request)
    {
        string observationId = $"obs-{Guid.NewGuid():N}";
        var receipt = new SubmitObservationResponse(
            ObservationId: observationId,
            Status: "accepted",
            AcceptedAtUtc: DateTimeOffset.UtcNow);

        _observations[observationId] = receipt;
        return receipt;
    }
}
