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
        => Redirect("/participate");

    [HttpGet("/coach")]
    [HttpGet("/coach/{**path}")]
    public IActionResult Coach()
        => Redirect("/status");
}
