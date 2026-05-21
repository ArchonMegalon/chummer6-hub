using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public interface IFirstPartySupportAssistant
{
    SupportAssistantResponse Answer(string? reporterUserId, string? reporterSubjectId, SupportAssistantRequest request);
}
