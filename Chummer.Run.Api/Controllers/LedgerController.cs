using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/ledger")]
public sealed class LedgerController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly LedgerService _ledger;
    private readonly FleetReceiptVerifier _receiptVerifier;
    private readonly RewardService _rewards;
    private readonly BlackLedgerPublicStatsService _blackLedgerPublicStats;
    private readonly BlackLedgerDispatchService _blackLedgerDispatches;
    private readonly BlackLedgerTickNewsNotificationService _blackLedgerTickNews;
    private readonly BlackLedgerFactionOnboardingService _blackLedgerFactions;

    public LedgerController(AccountService accounts, HubIdentityClient identity, LedgerService ledger, FleetReceiptVerifier receiptVerifier, RewardService rewards, BlackLedgerPublicStatsService blackLedgerPublicStats, BlackLedgerDispatchService blackLedgerDispatches, BlackLedgerTickNewsNotificationService blackLedgerTickNews, BlackLedgerFactionOnboardingService blackLedgerFactions)
    {
        _accounts = accounts;
        _identity = identity;
        _ledger = ledger;
        _receiptVerifier = receiptVerifier;
        _rewards = rewards;
        _blackLedgerPublicStats = blackLedgerPublicStats;
        _blackLedgerDispatches = blackLedgerDispatches;
        _blackLedgerTickNews = blackLedgerTickNews;
        _blackLedgerFactions = blackLedgerFactions;
    }

    [HttpPost("receipts")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<ReceiptIngestResultDto>(StatusCodes.Status200OK)]
    public ActionResult<ReceiptIngestResultDto> Ingest([FromBody] JsonElement receipt)
    {
        try
        {
            var verifiedReceipt = _receiptVerifier.VerifyAndDeserialize(Request, receipt);
            return Ok(_ledger.Ingest(verifiedReceipt));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("me")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [Produces("application/json")]
    public async Task<ActionResult<object>> GetMine([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            var user = _accounts.GetBySubject(subject.SubjectId);
            if (user is null)
            {
                return NotFound();
            }

            return Ok(new
            {
                user,
                ledger = _ledger.ListForUser(user.UserId),
                rewards = _rewards.ListRewardsForUser(user.UserId),
                badges = _rewards.ListBadgesForUser(user.UserId),
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("worlds/{worldId}")]
    [Produces("application/json")]
    public ActionResult<object> GetBlackLedgerWorld([FromRoute] string worldId, [FromQuery] int? turn)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        var seed = _blackLedgerPublicStats.LoadSeedDocument();
        var world = _blackLedgerPublicStats.LoadWorldPreview(turn);
        if (seed is null || world is null)
        {
            return NotFound();
        }

        return Ok(new
        {
            world.WorldId,
            world.PublicName,
            seed.PublicSubtitle,
            seed.LoreMode,
            world.Status,
            world.CurrentTurn,
            world.TurnHeadline,
            world.SafetyNote,
            world.MapNote,
            world.Districts,
            world.Factions,
            dispatches = _blackLedgerDispatches.ListPublishedDispatches(turn).Take(3).ToArray(),
            lastTick = world.LastTick,
        });
    }

    [HttpGet("worlds/{worldId}/turns/{turn:int}")]
    [Produces("application/json")]
    public ActionResult<object> GetBlackLedgerWorldTurn([FromRoute] string worldId, [FromRoute] int turn)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        var seed = _blackLedgerPublicStats.LoadSeedDocument();
        var turnDocument = seed?.Turns?.FirstOrDefault(item => item.Turn == turn);
        if (turnDocument is null)
        {
            return NotFound();
        }

        return Ok(turnDocument);
    }

    [HttpGet("worlds/{worldId}/dispatches")]
    [Produces("application/json")]
    public ActionResult<object> GetBlackLedgerWorldDispatches([FromRoute] string worldId, [FromQuery] int? turn = 1)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        return Ok(_blackLedgerDispatches.ListPublishedDispatches(turn));
    }

    [HttpGet("factions")]
    [Produces("application/json")]
    public ActionResult<IReadOnlyList<BlackLedgerFactionSummaryDto>> GetBlackLedgerFactions()
        => Ok(_blackLedgerFactions.ListFactionSummaries());

    [HttpGet("factions/{factionId}")]
    [Produces("application/json")]
    public ActionResult<BlackLedgerFactionDetailDto> GetBlackLedgerFaction([FromRoute] string factionId)
    {
        var detail = _blackLedgerFactions.GetFactionDetail(factionId);
        return detail is null ? NotFound() : Ok(detail);
    }

    [HttpGet("factions/{factionId}/actions")]
    [Produces("application/json")]
    public ActionResult<IReadOnlyList<BlackLedgerFactionActionDefinitionDto>> GetBlackLedgerFactionActions([FromRoute] string factionId)
        => Ok(_blackLedgerFactions.GetActionDefinitions(factionId));

    [HttpGet("/api/v1/account/ledger/allegiance")]
    [Produces("application/json")]
    public async Task<ActionResult<BlackLedgerAccountFactionAllegianceDto>> GetAccountFactionAllegiance(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var allegiance = _blackLedgerFactions.GetAllegiance(user);
            return allegiance is null ? NotFound() : Ok(allegiance);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("/api/v1/account/ledger/allegiance/join")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [Produces("application/json")]
    public async Task<ActionResult<BlackLedgerFactionJoinReceiptDto>> JoinLedgerFaction(
        [FromBody] JoinFactionRequest? body,
        [FromForm] string? factionId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var receipt = _blackLedgerFactions.JoinFaction(user, body?.FactionId ?? factionId ?? string.Empty);
            return Ok(receipt);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("/api/v1/account/ledger/factions")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [Produces("application/json")]
    public async Task<ActionResult<BlackLedgerFactionCharterDto>> CreateLedgerFaction(
        [FromBody] BlackLedgerCreateFactionRequest? body,
        [FromForm] string? publicName,
        [FromForm] string? charterType,
        [FromForm] string? archetypeId,
        [FromForm] string[]? perkIds,
        [FromForm] string[]? flawIds,
        [FromForm] string? startingDistrictId,
        [FromForm] string? rivalFactionId,
        [FromForm] bool? warningAccepted,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var charter = _blackLedgerFactions.CreateFaction(user, body ?? new BlackLedgerCreateFactionRequest(publicName, charterType, archetypeId, perkIds, flawIds, startingDistrictId, rivalFactionId, warningAccepted));
            return Ok(charter);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("/api/v1/account/ledger/factions/{factionId}/actions")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [Produces("application/json")]
    public async Task<ActionResult<BlackLedgerFactionActionReceiptDto>> ExecuteLedgerFactionAction(
        [FromRoute] string factionId,
        [FromBody] BlackLedgerFactionActionRequest? body,
        [FromForm] string? actionId,
        [FromForm] string? targetDistrictId,
        [FromForm] string? targetFactionId,
        [FromForm] string? stake,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var receipt = _blackLedgerFactions.ExecuteAction(user, factionId, body ?? new BlackLedgerFactionActionRequest(actionId, targetDistrictId, targetFactionId, stake));
            return Ok(receipt);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("/api/v1/account/ledger/factions/{factionId}/moderation/approve")]
    [Produces("application/json")]
    public async Task<ActionResult<BlackLedgerFactionModerationReceiptDto>> ApproveLedgerFactionPublicProjection(
        [FromRoute] string factionId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_blackLedgerFactions.ApproveFactionForPublicProjection(user, factionId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("/api/v1/account/ledger/factions/{factionId}/moderation/suppress")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [Produces("application/json")]
    public async Task<ActionResult<BlackLedgerFactionModerationReceiptDto>> SuppressLedgerFactionPublicProjection(
        [FromRoute] string factionId,
        [FromBody] SuppressFactionModerationRequest? body,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_blackLedgerFactions.SuppressFactionPublicProjection(user, factionId, body?.Reason));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("worlds/{worldId}/map")]
    [Produces("application/json")]
    public ActionResult<BlackLedgerMapApiDocument> GetBlackLedgerWorldMap([FromRoute] string worldId, [FromQuery] int? turn, [FromQuery] string? mode = null)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        BlackLedgerMapApiDocument? world = _blackLedgerPublicStats.LoadCommandMapDocument(turn, mode ?? "influence");
        return world is null ? NotFound() : Ok(world);
    }

    [HttpGet("worlds/{worldId}/map/turns/{turn:int}")]
    [Produces("application/json")]
    public ActionResult<BlackLedgerMapApiDocument> GetBlackLedgerWorldMapTurn([FromRoute] string worldId, [FromRoute] int turn, [FromQuery] string? mode = null)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        BlackLedgerMapApiDocument? world = _blackLedgerPublicStats.LoadCommandMapDocument(turn, mode ?? "influence");
        return world is null ? NotFound() : Ok(world);
    }

    [HttpGet("worlds/{worldId}/map/tick-delta/{fromTurn:int}/{toTurn:int}")]
    [Produces("application/json")]
    public ActionResult<BlackLedgerTickDeltaApiDocument> GetBlackLedgerWorldMapTickDelta([FromRoute] string worldId, [FromRoute] int fromTurn, [FromRoute] int toTurn)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        BlackLedgerTickDeltaApiDocument? delta = _blackLedgerPublicStats.LoadTickDelta(fromTurn, toTurn);
        return delta is null ? NotFound() : Ok(delta);
    }

    [HttpPost("worlds/{worldId}/ticks")]
    [Produces("application/json")]
    public async Task<ActionResult<object>> MaterializeDeterministicBlackLedgerTick([FromRoute] string worldId, [FromQuery] int turn = 2, CancellationToken cancellationToken = default)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        var world = _blackLedgerPublicStats.LoadWorldPreview(turn);
        if (world?.LastTick is null || !world.DeterministicPreview)
        {
            return NotFound();
        }

        string baseUrl = $"{Request.Scheme}://{Request.Host}";
        BlackLedgerWorldTickNewsEvent tickNews = _blackLedgerTickNews.BuildSeededWorldEvent(worldId, turn, baseUrl)
            ?? throw new InvalidOperationException("Deterministic world preview is missing its BLACK LEDGER tick-news event.");
        _ = await _blackLedgerTickNews.NotifyTickNewsAsync(tickNews, dryRun: false, policyOverride: null, cancellationToken);

        return Ok(new
        {
            receipt_type = "world_tick_receipt",
            world.WorldId,
            turn = world.LastTick.Turn,
            world.LastTick.ReceiptId,
            world.LastTick.Mode,
            world.LastTick.InputStateHash,
            world.LastTick.DecisionPacketHash,
            world.LastTick.PrivacyPassed,
            world.LastTick.BlockedFields,
            world.LastTick.OutputStateHash,
            world.LastTick.CreatedAtUtc,
            world.LastTick.Effects,
        });
    }

    [HttpPost("worlds/{worldId}/tick-news/send")]
    [Produces("application/json")]
    public async Task<ActionResult<object>> SendBlackLedgerTickNews(
        [FromRoute] string worldId,
        [FromQuery] int turn = 1,
        [FromQuery] bool dryRun = true,
        [FromQuery] string? policy = null,
        CancellationToken cancellationToken = default)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        string baseUrl = $"{Request.Scheme}://{Request.Host}";
        BlackLedgerWorldTickNewsEvent? tickNews = _blackLedgerTickNews.BuildSeededWorldEvent(worldId, turn, baseUrl);
        if (tickNews is null)
        {
            return NotFound();
        }

        BlackLedgerTickNewsNotificationBatchReceipt receipt = await _blackLedgerTickNews.NotifyTickNewsAsync(tickNews, dryRun, policy, cancellationToken);
        return Ok(new
        {
            receipt.BatchId,
            receipt.Policy,
            receipt.Status,
            receipt.WorldId,
            receipt.FromTurn,
            receipt.ToTurn,
            receipt.TickReceiptId,
            receipt.NewsId,
            receipt.DryRun,
            receipt.Duplicate,
            receipt.RecipientCount,
            receipt.FailureReason,
            receipt.Receipts,
        });
    }

    [HttpPost("dispatches")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [Produces("application/json")]
    public ActionResult<object> CreateBlackLedgerDispatch([FromBody] CreateLedgerDispatchApiRequest request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        BlackLedgerDispatchMutationResult result = _blackLedgerDispatches.CreateDraft(new CreateBlackLedgerDispatchRequest(
            WorldId: string.IsNullOrWhiteSpace(request.WorldId) ? "emerald-sprawl-prelude" : request.WorldId.Trim(),
            Turn: request.Turn <= 0 ? 1 : request.Turn,
            DispatchId: request.DispatchId,
            Adapter: request.Adapter,
            AutoApproveSeededPreview: request.AutoApproveSeededPreview,
            Reviewer: request.Reviewer));
        return Ok(new
        {
            result.Facts,
            result.Draft,
            result.GateReceipt,
            result.ApprovalReceipt,
            result.PublicationReceipt,
            result.PublishedDispatch,
        });
    }

    [HttpPost("dispatches/{dispatchId}/approve")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [Produces("application/json")]
    public ActionResult<object> ApproveBlackLedgerDispatch([FromRoute] string dispatchId, [FromBody] ApproveLedgerDispatchApiRequest request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        BlackLedgerDispatchMutationResult result = _blackLedgerDispatches.ApproveDispatch(dispatchId, new ApproveBlackLedgerDispatchRequest(
            Reviewer: string.IsNullOrWhiteSpace(request.Reviewer) ? "operator" : request.Reviewer.Trim(),
            HumanReviewStatus: string.IsNullOrWhiteSpace(request.HumanReviewStatus) ? "approved" : request.HumanReviewStatus.Trim(),
            Publish: request.Publish));
        return Ok(new
        {
            result.Facts,
            result.Draft,
            result.GateReceipt,
            result.ApprovalReceipt,
            result.PublicationReceipt,
            result.PublishedDispatch,
        });
    }

    [HttpPost("/api/v1/account/campaigns/{campaignId}/ledger/private-lore-overlay")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [Produces("application/json")]
    public async Task<ActionResult<object>> UpsertPrivateLoreOverlay([FromRoute] string campaignId, [FromBody] PrivateLoreOverlayRequest request, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_blackLedgerFactions.UpsertPrivateLoreOverlay(user, campaignId, request));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (HttpContext.RequestServices.GetRequiredService<IConfiguration>()["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "internal BLACK LEDGER automation auth is not configured.");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal BLACK LEDGER automation authorization is required.");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        return FixedTimeEquals(providedToken, expectedToken)
            ? null
            : Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal BLACK LEDGER automation authorization is required.");
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    public sealed record CreateLedgerDispatchApiRequest(
        string WorldId,
        int Turn,
        string? DispatchId,
        string? Adapter,
        bool AutoApproveSeededPreview = false,
        string? Reviewer = null);

    public sealed record ApproveLedgerDispatchApiRequest(
        string Reviewer,
        string HumanReviewStatus = "approved",
        bool Publish = true);

    public sealed record JoinFactionRequest(string? FactionId);
}

public sealed record SuppressFactionModerationRequest(string? Reason);
