using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

internal static class CommunityApiProblemMapper
{
    public static ActionResult FromException(ControllerBase controller, Exception ex)
        => ex switch
        {
            KeyNotFoundException missing => FromMissing(controller, missing),
            ArgumentException argument => controller.BadRequest(argument.Message),
            InvalidOperationException invalid => FromInvalidOperation(controller, invalid),
            _ => throw new ArgumentOutOfRangeException(nameof(ex), ex, "Unsupported community API exception type.")
        };

    private static ActionResult FromMissing(ControllerBase controller, KeyNotFoundException ex)
        => ex.Message switch
        {
            var message when message.Contains("Unknown join code:", StringComparison.OrdinalIgnoreCase)
                => controller.NotFound(new ProblemDetails
                {
                    Title = "Join code is not active",
                    Detail = "That join code is not active anymore. Ask the organizer for a fresh join code and reuse the member guidance rail for downloads, help, and closure."
                }),
            var message when message.Contains("Unknown boost code:", StringComparison.OrdinalIgnoreCase)
                => controller.NotFound(new ProblemDetails
                {
                    Title = "Boost code is not active",
                    Detail = "That boost code is not active anymore. Ask the organizer for a fresh sponsorship code on the same governed operator rail."
                }),
            _ => controller.NotFound()
        };

    private static ActionResult FromInvalidOperation(ControllerBase controller, InvalidOperationException ex)
        => ex.Message switch
        {
            var message when message.Contains("join code has expired", StringComparison.OrdinalIgnoreCase)
                => controller.BadRequest(new ProblemDetails
                {
                    Title = "Join code expired",
                    Detail = "That join code expired. Ask the organizer for a fresh join code and resend the same member guidance rail so recovery stays grounded."
                }),
            _ => controller.BadRequest(ex.Message)
        };
}
