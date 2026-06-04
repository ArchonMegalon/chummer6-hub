using Chummer.Run.Api.Controllers;
using Microsoft.AspNetCore.Mvc;
using Xunit;

namespace Chummer.Tests;

public sealed class LegacySurfaceRedirectControllerTests
{
    [Theory]
    [InlineData("support", "/contact")]
    public void PublicConvenienceRoutesRedirectToLiveFlagshipSurfaces(string route, string expectedUrl)
    {
        var controller = new LegacySurfaceRedirectController();

        IActionResult result = route switch
        {
            "support" => controller.Support(),
            _ => throw new ArgumentOutOfRangeException(nameof(route), route, null)
        };

        var redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal(expectedUrl, redirect.Url);
    }
}
