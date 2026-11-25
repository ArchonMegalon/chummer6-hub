using System.Security.Claims;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Registry.Controllers;
using Chummer.Run.Registry.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc.Controllers;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Supplies existing Hub account ownership to Registry's public reads. The
/// Registry control credential remains a service credential, never an account.
/// </summary>
public sealed class HubRegistryReadIdentityMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context)
    {
        var endpoint = context.GetEndpoint();
        var controller = endpoint?.Metadata.GetMetadata<ControllerActionDescriptor>()?.ControllerTypeInfo.AsType();
        if ((!HttpMethods.IsGet(context.Request.Method) && !HttpMethods.IsHead(context.Request.Method))
            || endpoint?.Metadata.GetMetadata<IAllowAnonymous>() is null
            || (controller != typeof(HubRegistryController) && controller != typeof(PublicationsController)))
        {
            await next(context);
            return;
        }

        // This runs after UseAuthorization: its explicit control scheme may
        // have replaced User, including on AllowAnonymous endpoints. Do not let
        // that service's NameIdentifier participate in owner checks.
        // An authenticated control request with Authorization is service-only.
        // Never forward a possible service bearer to account introspection,
        // including when the explicit control header is also present. A separate
        // browser cookie can be resolved when Authorization is absent.
        bool controlBearer = context.Request.Headers.ContainsKey("Authorization")
            && context.User.Identities.Any(identity => identity.IsAuthenticated
                && identity.AuthenticationType == RegistryAuthorization.Scheme);
        context.User = new ClaimsPrincipal(new ClaimsIdentity());
        PrivateResponseCacheHeaders.Apply(context.Response.Headers);

        if (!controlBearer && (context.Request.Headers.ContainsKey("Authorization")
            || context.Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName)))
        {
            try
            {
                var identity = context.RequestServices.GetRequiredService<HubIdentityClient>();
                var subject = await identity.RequireFreshSubjectAsync(context.Request, context.RequestAborted);
                var accounts = context.RequestServices.GetRequiredService<AccountService>();
                string? userId = accounts.GetExistingCanonicalUserIdBySubject(subject.SubjectId);
                if (string.IsNullOrWhiteSpace(userId))
                {
                    context.Response.StatusCode = StatusCodes.Status403Forbidden;
                    return;
                }

                // Artifact OwnerId is HubUserDto.UserId, not the upstream subject
                // or a caller-supplied owner/filter. Reads never create accounts.
                context.User = new ClaimsPrincipal(new ClaimsIdentity(
                    [new Claim(ClaimTypes.NameIdentifier, userId)], "HubRegistryRead"));
            }
            catch (HubRequestAuthException exception)
            {
                context.Response.StatusCode = exception.StatusCode;
                return;
            }
        }

        await next(context);
    }
}
