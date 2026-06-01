using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class PayFunnelsBillingController : ControllerBase
{
    private readonly PayFunnelsBillingService _billing;

    public PayFunnelsBillingController(PayFunnelsBillingService billing)
    {
        _billing = billing;
    }

    [HttpGet("/account/billing/test")]
    [Produces("text/html")]
    public ContentResult TestBillingPage([FromQuery] string userId = "")
    {
        PayFunnelsTestBillingPageDto page = _billing.GetTestPage();
        string html = $$"""
            <!doctype html>
            <html lang="en">
            <head><meta charset="utf-8"><title>{{page.Product.Name}}</title></head>
            <body>
              <main>
                <h1>{{page.Product.Name}}</h1>
                <h2>Help us test payment processing</h2>
                <p>This is a $1 test payment.</p>
                <p>It currently unlocks no benefits, no premium features, no render credits, and no special access.</p>
                <p>It only helps us test payment processing.</p>
                <form method="post" action="/account/billing/test">
                  <input type="hidden" name="userId" value="{{System.Net.WebUtility.HtmlEncode(userId)}}">
                  <label><input type="checkbox" name="benefitAcknowledged" value="true" required> {{page.AcknowledgementCopy}}</label>
                  <button type="submit">{{page.CheckoutButtonCopy}}</button>
                </form>
              </main>
            </body>
            </html>
            """;
        return Content(html, "text/html");
    }

    [HttpGet("/api/billing/payfunnels/test")]
    [ProducesResponseType<PayFunnelsTestBillingPageDto>(StatusCodes.Status200OK)]
    public ActionResult<PayFunnelsTestBillingPageDto> TestBillingProjection() => Ok(_billing.GetTestPage());

    [HttpPost("/account/billing/test")]
    [Consumes("application/x-www-form-urlencoded")]
    public IActionResult CreateIntentFromForm([FromForm] PaymentIntentCreateRequest request)
    {
        try
        {
            PaymentIntentDto intent = _billing.CreateIntent(request);
            return Redirect(intent.CheckoutUrl);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("/api/billing/payfunnels/test-intents")]
    [ProducesResponseType<PaymentIntentDto>(StatusCodes.Status200OK)]
    public ActionResult<PaymentIntentDto> CreateIntent([FromBody] PaymentIntentCreateRequest request)
    {
        try
        {
            return Ok(_billing.CreateIntent(request));
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("/api/billing/payfunnels/webhook")]
    [ProducesResponseType<PayFunnelsWebhookResultDto>(StatusCodes.Status200OK)]
    public ActionResult<PayFunnelsWebhookResultDto> Webhook([FromBody] PayFunnelsWebhookRequest request)
    {
        string signature = Request.Headers["X-PayFunnels-Signature"].ToString();
        PayFunnelsWebhookResultDto result = _billing.ProcessWebhook(request, signature);
        return result.Status == "rejected"
            ? Problem(statusCode: StatusCodes.Status400BadRequest, detail: result.RejectionReason)
            : Ok(result);
    }

    [HttpGet("/account/billing/success")]
    [Produces("text/html")]
    public ContentResult SuccessPage([FromQuery] string receiptId = "")
        => Content($"""
            <!doctype html>
            <html lang="en">
            <head><meta charset="utf-8"><title>Billing test successful</title></head>
            <body>
              <main>
                <h1>Billing test successful.</h1>
                <p>This is a $1 test payment.</p>
                <p>It currently unlocks no benefits, no premium features, no render credits, and no special access.</p>
                <p>It only helps us test payment processing.</p>
                <p>Receipt: {System.Net.WebUtility.HtmlEncode(receiptId)}</p>
              </main>
            </body>
            </html>
            """, "text/html");

    [HttpGet("/api/billing/payfunnels/accounts/{userId}")]
    [ProducesResponseType<BillingAccountSummaryDto>(StatusCodes.Status200OK)]
    public ActionResult<BillingAccountSummaryDto> AccountSummary([FromRoute] string userId)
        => Ok(_billing.GetAccountSummary(userId));
}
