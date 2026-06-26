using System.Net;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.Mvc;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class BrilliantDirectoriesBillingController : Controller
{
    private readonly BrilliantDirectoriesBillingService _billing;
    private readonly HubIdentityClient? _identity;
    private readonly AccountService? _accounts;
    private readonly ILogger<BrilliantDirectoriesBillingController> _logger;

    public BrilliantDirectoriesBillingController(
        BrilliantDirectoriesBillingService billing,
        HubIdentityClient? identity = null,
        AccountService? accounts = null,
        ILogger<BrilliantDirectoriesBillingController>? logger = null)
    {
        _billing = billing;
        _identity = identity;
        _accounts = accounts;
        _logger = logger ?? NullLogger<BrilliantDirectoriesBillingController>.Instance;
    }

    [HttpGet("/account/billing")]
    [Produces("text/html")]
    public async Task<IActionResult> BillingPage([FromQuery] string? userId = null, [FromQuery] string? email = null, CancellationToken cancellationToken = default)
    {
        _ = userId;
        _ = email;
        HubUserDto? currentUser = await TryGetCurrentUserAsync(cancellationToken).ConfigureAwait(false);
        string? resolvedUserId = TrimToNull(currentUser?.UserId);
        string? resolvedEmail = TrimToNull(currentUser?.Email);

        try
        {
            var page = _billing.GetPage();
            var quota = string.IsNullOrWhiteSpace(resolvedUserId)
                ? null
                : _billing.GetMyFirstBookQuota(resolvedUserId, email: resolvedEmail);
            return View("~/Views/Billing/Membership.cshtml", BuildViewModel(page, quota, resolvedUserId, resolvedEmail, currentUser));
        }
        catch (BrilliantDirectoriesBillingUnavailableException)
        {
            Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            return View("~/Views/Billing/Membership.cshtml", BuildUnavailableViewModel(resolvedUserId, resolvedEmail, currentUser));
        }
    }

    [HttpGet("/billing")]
    [Produces("text/html")]
    public IActionResult BillingAlias()
        => Redirect("/account/billing");

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
                detail: "Membership billing is unavailable right now.");
        }
    }

    [HttpGet("/api/billing/myfirstbook-quota/{userId}")]
    [ProducesResponseType<MyFirstBookQuotaSnapshotDto>(StatusCodes.Status200OK)]
    public ActionResult<MyFirstBookQuotaSnapshotDto> MyFirstBookQuota([FromRoute] string userId)
    {
        try
        {
            _billing.EnsureAuthorized(BillingSecretHeader());
            return Ok(_billing.GetMyFirstBookQuota(userId));
        }
        catch (UnauthorizedAccessException)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Billing quota lookup was not authorized.");
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

    [HttpGet("/api/billing/myfirstbook-quota/me")]
    [ProducesResponseType<MyFirstBookQuotaSnapshotDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<MyFirstBookQuotaSnapshotDto>> MyFirstBookQuotaForCurrentUser(CancellationToken cancellationToken = default)
    {
        HubUserDto? currentUser = await TryGetCurrentUserAsync(cancellationToken).ConfigureAwait(false);
        if (currentUser is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before checking MyFirstBook allowance.");
        }

        try
        {
            return Ok(_billing.GetMyFirstBookQuota(currentUser.UserId, email: currentUser.Email));
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("/api/billing/myfirstbook-quota/{userId}/consume")]
    [ProducesResponseType<MyFirstBookQuotaConsumeResultDto>(StatusCodes.Status200OK)]
    public ActionResult<MyFirstBookQuotaConsumeResultDto> ConsumeMyFirstBookQuota([FromRoute] string userId)
    {
        try
        {
            _billing.EnsureAuthorized(BillingSecretHeader());
            return Ok(_billing.ConsumeMyFirstBookQuota(userId));
        }
        catch (UnauthorizedAccessException)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Billing quota mutation was not authorized.");
        }
        catch (BrilliantDirectoriesBillingUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status429TooManyRequests, detail: ex.Message);
        }
    }

    [HttpPost("/api/billing/myfirstbook-quota/me/consume")]
    [ProducesResponseType<MyFirstBookQuotaConsumeResultDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status429TooManyRequests)]
    public async Task<ActionResult<MyFirstBookQuotaConsumeResultDto>> ConsumeMyFirstBookQuotaForCurrentUser(CancellationToken cancellationToken = default)
    {
        HubUserDto? currentUser = await TryGetCurrentUserAsync(cancellationToken).ConfigureAwait(false);
        if (currentUser is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before creating a MyFirstBook origin book.");
        }

        try
        {
            return Ok(_billing.ConsumeMyFirstBookQuota(currentUser.UserId, email: currentUser.Email));
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status429TooManyRequests, detail: ex.Message);
        }
    }

    [HttpPost("/account/billing/supporter")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> StartSupporterCheckout([FromForm] BrilliantDirectoriesCheckoutRequest request, CancellationToken cancellationToken = default)
    {
        BrilliantDirectoriesCheckoutRequest resolvedRequest = request;
        if (string.IsNullOrWhiteSpace(resolvedRequest.UserId))
        {
            HubUserDto? currentUser = await TryGetCurrentUserAsync(cancellationToken).ConfigureAwait(false);
            if (currentUser is null)
            {
                return Redirect($"/auth/google/start?next={Uri.EscapeDataString("/account/billing")}");
            }

            resolvedRequest = new BrilliantDirectoriesCheckoutRequest(
                currentUser.UserId,
                TrimToNull(resolvedRequest.Email) ?? TrimToNull(currentUser.Email));
        }

        try
        {
            var checkout = _billing.CreateSupporterCheckout(resolvedRequest);
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

    [HttpGet("/account/billing/supporter/start")]
    public async Task<IActionResult> StartSupporterCheckoutDirect(CancellationToken cancellationToken = default)
    {
        HubUserDto? currentUser = await TryGetCurrentUserAsync(cancellationToken).ConfigureAwait(false);
        if (currentUser is null)
        {
            return Redirect("/account/billing");
        }

        try
        {
            var checkout = _billing.CreateSupporterCheckout(
                new BrilliantDirectoriesCheckoutRequest(
                    currentUser.UserId,
                    TrimToNull(currentUser.Email)));
            return Redirect(checkout.CheckoutUrl);
        }
        catch (BrilliantDirectoriesBillingUnavailableException)
        {
            return Redirect("/account/billing");
        }
        catch (InvalidOperationException)
        {
            return Redirect("/account/billing");
        }
    }

    [HttpPost("/api/billing/brilliant-directories/supporter")]
    [ProducesResponseType<BrilliantDirectoriesCheckoutResponseDto>(StatusCodes.Status200OK)]
    public ActionResult<BrilliantDirectoriesCheckoutResponseDto> StartSupporterCheckoutApi([FromBody] BrilliantDirectoriesCheckoutRequest request)
    {
        try
        {
            _billing.EnsureAuthorized(BillingSecretHeader());
            return Ok(_billing.CreateSupporterCheckout(request));
        }
        catch (UnauthorizedAccessException)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Billing checkout API was not authorized.");
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
            return Ok(_billing.SyncMember(request, BillingSecretHeader()));
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
            _billing.EnsureAuthorized(BillingSecretHeader());
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
        MyFirstBookQuotaSnapshotDto? currentMyFirstBookQuota,
        string? userId,
        string? email,
        HubUserDto? currentUser)
    {
        BillingPlanCardDto? free = page.Plans.SingleOrDefault(item => string.Equals(item.PlanKey, BrilliantDirectoriesBillingConstants.FreePlanKey, StringComparison.OrdinalIgnoreCase));
        BillingPlanCardDto? supporter = page.Plans.SingleOrDefault(item => string.Equals(item.PlanKey, BrilliantDirectoriesBillingConstants.SupporterPlanKey, StringComparison.OrdinalIgnoreCase));
        return new BillingMembershipPageViewModel(
            Page: page,
            FreePlan: free,
            SupporterPlan: supporter,
            CurrentMyFirstBookQuota: currentMyFirstBookQuota,
            UserId: TrimToNull(userId),
            Email: TrimToNull(email),
            SignedInLabel: currentUser?.DisplayName,
            UsingSignedInAccount: currentUser is not null,
            Unavailable: false,
            Heading: page.Heading,
            Summary: page.Summary,
            ManageMembershipHref: page.ManageMembershipHref);
    }

    private static BillingMembershipPageViewModel BuildUnavailableViewModel(string? userId, string? email, HubUserDto? currentUser)
        => new(
            Page: null,
            FreePlan: null,
            SupporterPlan: null,
            CurrentMyFirstBookQuota: null,
            UserId: TrimToNull(userId),
            Email: TrimToNull(email),
            SignedInLabel: currentUser?.DisplayName,
            UsingSignedInAccount: currentUser is not null,
            Unavailable: true,
            Heading: "Membership temporarily unavailable",
            Summary: "Your Chummer access is unchanged while billing is unavailable.",
            ManageMembershipHref: "/account");

    private async Task<HubUserDto?> TryGetCurrentUserAsync(CancellationToken cancellationToken)
    {
        if (_identity is null || _accounts is null)
        {
            return null;
        }

        try
        {
            AuthenticatedHubSubject subject = await _identity.RequireSubjectAsync(Request, cancellationToken).ConfigureAwait(false);
            return _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return null;
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Billing surface could not resolve the current signed-in subject.");
            return null;
        }
    }

    private static string? TrimToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private string? BillingSecretHeader()
        => HttpContext?.Request.Headers["X-Chummer-Billing-Secret"].ToString();
}
