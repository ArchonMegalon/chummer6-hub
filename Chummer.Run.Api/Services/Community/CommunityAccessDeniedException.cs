namespace Chummer.Run.Api.Services.Community;

public sealed class CommunityAccessDeniedException : Exception
{
    public CommunityAccessDeniedException(string message)
        : base(message)
    {
    }
}
