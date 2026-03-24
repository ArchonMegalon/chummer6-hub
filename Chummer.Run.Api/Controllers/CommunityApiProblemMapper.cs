using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

internal static class CommunityApiProblemMapper
{
    public static ActionResult FromException(ControllerBase controller, Exception ex)
        => ex switch
        {
            KeyNotFoundException => controller.NotFound(),
            ArgumentException argument => controller.BadRequest(argument.Message),
            InvalidOperationException invalid => controller.BadRequest(invalid.Message),
            _ => throw new ArgumentOutOfRangeException(nameof(ex), ex, "Unsupported community API exception type.")
        };
}
