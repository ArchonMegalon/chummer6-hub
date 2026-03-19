using System.Text.Json;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.AI.Services.Booster;

public sealed class BoosterReceiptAuthException : Exception
{
    public BoosterReceiptAuthException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; }
}

public sealed class BoosterReceiptVerifier
{
    private readonly IConfiguration _configuration;

    public BoosterReceiptVerifier(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public ContributionReceiptDto VerifyAndDeserialize(HttpRequest request, JsonElement payload)
    {
        var secret = Normalize(_configuration["FLEET_RECEIPT_SIGNING_SECRET"]);
        if (secret is null)
        {
            throw new BoosterReceiptAuthException(
                StatusCodes.Status503ServiceUnavailable,
                "FLEET_RECEIPT_SIGNING_SECRET must be configured before booster receipts can be projected.");
        }

        var headerSignature = Normalize(request.Headers["X-Fleet-Receipt-Signature"].ToString());
        if (headerSignature is null)
        {
            throw new BoosterReceiptAuthException(StatusCodes.Status401Unauthorized, "valid Fleet receipt signature required.");
        }

        ContributionReceiptDto receipt;
        try
        {
            receipt = FleetReceiptSigning.Deserialize(payload);
        }
        catch (Exception ex) when (ex is JsonException or NotSupportedException or ArgumentException or InvalidOperationException)
        {
            throw new BoosterReceiptAuthException(StatusCodes.Status400BadRequest, "valid receipt payload required.");
        }

        var bodySignature = Normalize(receipt.SignedByFleet);
        var expectedSignature = FleetReceiptSigning.ComputeHmacSignature(payload, secret);
        if (bodySignature is null
            || !FleetReceiptSigning.SignatureEquals(headerSignature, bodySignature)
            || !FleetReceiptSigning.SignatureEquals(headerSignature, expectedSignature))
        {
            throw new BoosterReceiptAuthException(StatusCodes.Status401Unauthorized, "valid Fleet receipt signature required.");
        }

        return receipt;
    }

    private static string? Normalize(string? value)
    {
        var normalized = string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        return string.IsNullOrWhiteSpace(normalized) ? null : normalized;
    }
}
