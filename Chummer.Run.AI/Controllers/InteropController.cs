using Chummer.Run.AI.Services.Interop;
using InteropContracts = Chummer.Play.Contracts.Interop;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/interop")]
public sealed class InteropController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly IInteropExportService _interop;

    public InteropController(IInteropExportService interop)
    {
        _interop = interop;
    }

    [HttpPost("export")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<InteropContracts.InteropExportPackage>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<InteropContracts.InteropExportPackage> Export([FromBody] InteropContracts.InteropExportRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.CampaignId) || string.IsNullOrWhiteSpace(request.RequestedBy))
        {
            return BadRequest("campaignId and requestedBy are required.");
        }

        return Ok(_interop.Export(request));
    }

    [HttpPost("import")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<InteropContracts.InteropImportResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<InteropContracts.InteropImportResult> Import([FromBody] InteropContracts.InteropImportRequest? request)
    {
        if (request is null || request.Package is null || string.IsNullOrWhiteSpace(request.ImportedBy))
        {
            return BadRequest("package and importedBy are required.");
        }

        return Ok(_interop.Import(request));
    }

    [HttpPost("round-trip")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<InteropContracts.InteropRoundTripResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<InteropContracts.InteropRoundTripResult> RoundTrip([FromBody] InteropContracts.InteropRoundTripRequest? request)
    {
        if (request is null || request.Export is null || string.IsNullOrWhiteSpace(request.ImportedBy))
        {
            return BadRequest("export and importedBy are required.");
        }

        if (string.IsNullOrWhiteSpace(request.Export.CampaignId) || string.IsNullOrWhiteSpace(request.Export.RequestedBy))
        {
            return BadRequest("export.campaignId and export.requestedBy are required.");
        }

        return Ok(_interop.RoundTrip(request));
    }
}
