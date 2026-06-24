using System.Net;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class BrilliantDirectoriesBillingController : ControllerBase
{
    private readonly BrilliantDirectoriesBillingService _billing;

    public BrilliantDirectoriesBillingController(BrilliantDirectoriesBillingService billing)
    {
        _billing = billing;
    }

    [HttpGet("/account/billing")]
    [Produces("text/html")]
    public ContentResult BillingPage()
    {
        try
        {
            var page = _billing.GetPage();
            var free = page.Plans.Single(item => string.Equals(item.PlanKey, BrilliantDirectoriesBillingConstants.FreePlanKey, StringComparison.OrdinalIgnoreCase));
            var supporter = page.Plans.Single(item => string.Equals(item.PlanKey, BrilliantDirectoriesBillingConstants.SupporterPlanKey, StringComparison.OrdinalIgnoreCase));
            string html = $$"""
                <!doctype html>
                <html lang="en">
                <head><meta charset="utf-8"><title>{{WebUtility.HtmlEncode(page.Heading)}}</title></head>
                <body>
                  <main>
                    <h1>{{WebUtility.HtmlEncode(page.Heading)}}</h1>
                    <p>{{WebUtility.HtmlEncode(page.Summary)}}</p>
                    <section>
                      <h2>{{WebUtility.HtmlEncode(free.Name)}}</h2>
                      <p>{{WebUtility.HtmlEncode(free.Summary)}}</p>
                      <ul>
                        {{string.Join("", free.Included.Select(item => $"<li>{WebUtility.HtmlEncode(item)}</li>"))}}
                      </ul>
                      <p><a href="{{WebUtility.HtmlEncode(free.PrimaryAction.Href)}}">{{WebUtility.HtmlEncode(free.PrimaryAction.Label)}}</a></p>
                    </section>
                    <section>
                      <h2>{{WebUtility.HtmlEncode(supporter.Name)}}</h2>
                      <p>{{WebUtility.HtmlEncode(supporter.Summary)}}</p>
                      <ul>
                        {{string.Join("", supporter.Included.Select(item => $"<li>{WebUtility.HtmlEncode(item)}</li>"))}}
                      </ul>
                      <form method="post" action="/account/billing/supporter">
                        <label>User id <input type="text" name="userId"></label>
                        <label>Email <input type="email" name="email"></label>
                        <button type="submit">{{WebUtility.HtmlEncode(supporter.PrimaryAction.Label)}}</button>
                      </form>
                    </section>
                    <p><a href="{{WebUtility.HtmlEncode(page.ManageMembershipHref)}}">Manage billing</a></p>
                  </main>
                </body>
                </html>
                """;
            return Content(html, "text/html");
        }
        catch (BrilliantDirectoriesBillingUnavailableException)
        {
            const string html = """
                <!doctype html>
                <html lang="en">
                <head><meta charset="utf-8"><title>Membership temporarily unavailable</title></head>
                <body>
                  <main>
                    <h1>Membership temporarily unavailable</h1>
                    <p>Free and Supporter still share the same product access today.</p>
                    <p>The hosted billing route is not ready on this host yet. Try again later or return to your account.</p>
                    <p><a href="/account">Back to account</a></p>
                  </main>
                </body>
                </html>
                """;
            return new ContentResult
            {
                Content = html,
                ContentType = "text/html",
                StatusCode = StatusCodes.Status503ServiceUnavailable
            };
        }
    }

    [HttpGet("/api/billing")]
    [ProducesResponseType<BrilliantDirectoriesBillingPageDto>(StatusCodes.Status200OK)]
    public ActionResult<BrilliantDirectoriesBillingPageDto> BillingProjection()
    {
        try
        {
            return Ok(_billing.GetPage());
        }
        catch (BrilliantDirectoriesBillingUnavailableException)
        {
            return Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                detail: "Membership billing is temporarily unavailable while the hosted provider route is being configured.");
        }
    }

    [HttpPost("/account/billing/supporter")]
    [Consumes("application/x-www-form-urlencoded")]
    public IActionResult StartSupporterCheckout([FromForm] BrilliantDirectoriesCheckoutRequest request)
    {
        try
        {
            var checkout = _billing.CreateSupporterCheckout(request);
            return Redirect(checkout.CheckoutUrl);
        }
        catch (BrilliantDirectoriesBillingUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("/api/billing/brilliant-directories/supporter")]
    [ProducesResponseType<BrilliantDirectoriesCheckoutResponseDto>(StatusCodes.Status200OK)]
    public ActionResult<BrilliantDirectoriesCheckoutResponseDto> StartSupporterCheckoutApi([FromBody] BrilliantDirectoriesCheckoutRequest request)
    {
        try
        {
            return Ok(_billing.CreateSupporterCheckout(request));
        }
        catch (BrilliantDirectoriesBillingUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("/api/billing/brilliant-directories/sync")]
    [ProducesResponseType<BrilliantDirectoriesSyncResultDto>(StatusCodes.Status200OK)]
    public ActionResult<BrilliantDirectoriesSyncResultDto> SyncMember([FromBody] BrilliantDirectoriesMemberSyncRequest request)
    {
        try
        {
            string? secret = Request.Headers["X-Chummer-Billing-Secret"].ToString();
            return Ok(_billing.SyncMember(request, secret));
        }
        catch (UnauthorizedAccessException)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Billing sync was not authorized.");
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpGet("/api/billing/brilliant-directories/accounts/{userId}")]
    [ProducesResponseType<BrilliantDirectoriesMemberSnapshotDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public ActionResult<BrilliantDirectoriesMemberSnapshotDto> Account([FromRoute] string userId)
    {
        try
        {
            string? secret = Request.Headers["X-Chummer-Billing-Secret"].ToString();
            _billing.EnsureAuthorized(secret);
            var snapshot = _billing.GetAccount(userId);
            return snapshot is null ? NotFound() : Ok(snapshot);
        }
        catch (UnauthorizedAccessException)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Billing account lookup was not authorized.");
        }
    }
}
