using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

public sealed class FleetReceiptVerifier
{
    private readonly IConfiguration _configuration;

    public FleetReceiptVerifier(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public ContributionReceiptDto VerifyAndDeserialize(HttpRequest request, JsonElement payload)
    {
        var secret = AccountService.NormalizeOptional(_configuration["FLEET_RECEIPT_SIGNING_SECRET"]);
        if (secret is null)
        {
            throw new HubRequestAuthException(
                StatusCodes.Status503ServiceUnavailable,
                "FLEET_RECEIPT_SIGNING_SECRET must be configured before Hub can ingest contribution receipts.");
        }

        var headerSignature = AccountService.NormalizeOptional(request.Headers["X-Fleet-Receipt-Signature"].ToString());
        if (headerSignature is null)
        {
            throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "valid Fleet receipt signature required.");
        }

        ContributionReceiptDto receipt;
        try
        {
            receipt = FleetReceiptSigning.Deserialize(payload);
        }
        catch (Exception ex) when (ex is JsonException or NotSupportedException or ArgumentException or InvalidOperationException)
        {
            throw new HubRequestAuthException(StatusCodes.Status400BadRequest, "valid receipt payload required.");
        }

        var bodySignature = AccountService.NormalizeOptional(receipt.SignedByFleet);
        var expectedSignature = FleetReceiptSigning.ComputeHmacSignature(payload, secret);
        if (bodySignature is null
            || !FleetReceiptSigning.SignatureEquals(headerSignature, bodySignature)
            || !FleetReceiptSigning.SignatureEquals(headerSignature, expectedSignature))
        {
            throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "valid Fleet receipt signature required.");
        }

        return receipt;
    }
}
