using System.Net;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.Mvc;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class BrilliantDirectoriesBillingController : Controller
{
    private readonly BrilliantDirectoriesBillingService _billing;

    public BrilliantDirectoriesBillingController(BrilliantDirectoriesBillingService billing)
    {
        _billing = billing;
    }

    [HttpGet("/account/billing")]
    [Produces("text/html")]
    public IActionResult BillingPage([FromQuery] string? userId = null, [FromQuery] string? email = null)
    {
        try
        {
            var page = _billing.GetPage();
            return View("~/Views/Billing/Membership.cshtml", BuildViewModel(page, userId, email));
        }
        catch (BrilliantDirectoriesBillingUnavailableException)
        {
            Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            return View("~/Views/Billing/Membership.cshtml", BuildUnavailableViewModel(userId, email));
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
                detail: "Membership billing is temporarily unavailable on this host right now.");
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

    private static BillingMembershipPageViewModel BuildViewModel(
        BrilliantDirectoriesBillingPageDto page,
        string? userId,
        string? email)
    {
        BillingPlanCardDto? free = page.Plans.SingleOrDefault(item => string.Equals(item.PlanKey, BrilliantDirectoriesBillingConstants.FreePlanKey, StringComparison.OrdinalIgnoreCase));
        BillingPlanCardDto? supporter = page.Plans.SingleOrDefault(item => string.Equals(item.PlanKey, BrilliantDirectoriesBillingConstants.SupporterPlanKey, StringComparison.OrdinalIgnoreCase));
        return new BillingMembershipPageViewModel(
            Page: page,
            FreePlan: free,
            SupporterPlan: supporter,
            UserId: TrimToNull(userId),
            Email: TrimToNull(email),
            Unavailable: false,
            Heading: page.Heading,
            Summary: page.Summary,
            ManageMembershipHref: page.ManageMembershipHref);
    }

    private static BillingMembershipPageViewModel BuildUnavailableViewModel(string? userId, string? email)
        => new(
            Page: null,
            FreePlan: null,
            SupporterPlan: null,
            UserId: TrimToNull(userId),
            Email: TrimToNull(email),
            Unavailable: true,
            Heading: "Membership temporarily unavailable",
            Summary: "Free and Supporter still unlock the same product today. Billing is not ready on this host yet.",
            ManageMembershipHref: "/account");

    private static string? TrimToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
