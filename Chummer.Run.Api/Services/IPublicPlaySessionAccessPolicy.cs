using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

public interface IPublicPlaySessionAccessPolicy
{
    Task<bool> HasAccessAsync(HttpContext context, CancellationToken cancellationToken);
}
