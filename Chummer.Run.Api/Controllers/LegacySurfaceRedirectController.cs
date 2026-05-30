using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class LegacySurfaceRedirectController : ControllerBase
{
    [HttpGet("/hub")]
    [HttpGet("/hub/{**path}")]
    public IActionResult Hub()
        => Redirect("/account");

    [HttpGet("/blazor")]
    [HttpGet("/blazor/{**path}")]
    [HttpGet("/avalonia")]
    [HttpGet("/avalonia/{**path}")]
    public IActionResult Workbench()
        => Redirect("/downloads");

    [HttpGet("/session")]
    [HttpGet("/session/{**path}")]
    public IActionResult Session()
        => Redirect("/play");

    [HttpGet("/support")]
    [HttpGet("/support/{**path}")]
    public IActionResult Support()
        => Redirect("/contact");

    [HttpGet("/table-pulse")]
    [HttpGet("/table-pulse/{**path}")]
    public IActionResult TablePulse()
        => Redirect("/account/ledger/notifications");

    [HttpGet("/coach")]
    [HttpGet("/coach/{**path}")]
    public IActionResult Coach()
        => Redirect("/status");
}
