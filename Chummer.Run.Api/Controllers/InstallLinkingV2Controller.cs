using Chummer.Contracts.Characters;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v2/install-linking")]
public sealed class InstallLinkingV2Controller : ControllerBase
{
    private readonly InstallLinkingService _installLinking;
    private readonly InstallLinkedWorkspaceSnapshotService _workspaceSnapshots;
    private readonly TimeProvider _timeProvider;

    public InstallLinkingV2Controller(
        InstallLinkingService installLinking,
        InstallLinkedWorkspaceSnapshotService workspaceSnapshots,
        TimeProvider timeProvider)
    {
        _installLinking = installLinking;
        _workspaceSnapshots = workspaceSnapshots;
        _timeProvider = timeProvider;
    }

    [HttpPost("callbacks/poll")]
    [RequestSizeLimit(InstallLinkingService.MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidInstallLinkV2ExchangeResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType<AndroidInstallLinkProofPollStatus>(StatusCodes.Status202Accepted)]
    public ActionResult<AndroidInstallLinkV2ExchangeResponse> PollBrowserCallback(
        [FromBody] AndroidInstallLinkProofPollV2Request? request)
    {
        ApplyPrivateResponseHeaders();
        if (Request.QueryString.HasValue)
        {
            return Problem(
                statusCode: StatusCodes.Status400BadRequest,
                detail: "Android v2 callback polling does not accept query parameters.");
        }
        if (request is null)
        {
            return Problem(
                statusCode: StatusCodes.Status400BadRequest,
                detail: "remote proof payload is required.");
        }

        try
        {
            PollInstallBrowserCallbackResult result = _installLinking.PollBrowserCallbackV2(request);
            if (result.Exchange is null)
            {
                return Accepted(result.Status);
            }

            InstallationGrantDto grant = result.Exchange.Grant;
            Response.Headers["Authorization"] = $"Bearer {grant.AccessToken}";
            Response.Headers[AndroidLinkedV2RequestProof.GrantHeader] = grant.GrantId;
            return Ok(new AndroidInstallLinkV2ExchangeResponse(
                result.Exchange.Installation,
                new AndroidLinkedV2GrantMetadata(
                    grant.GrantId,
                    grant.InstallationId,
                    grant.Status,
                    grant.IssuedAtUtc,
                    grant.ExpiresAtUtc),
                result.Exchange.AlreadyClaimed));
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(
                statusCode: ex.StatusCode,
                detail: "The Android install-link proof could not be accepted.");
        }
    }

    [HttpPost("grants/status")]
    [RequestSizeLimit(InstallLinkingService.MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedV2GrantStatusResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedV2GrantStatusResponse> GetGrantStatus(
        [FromBody] AndroidLinkedV2GrantRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolvePrincipal(request, out AndroidLinkedV2GrantPrincipal? principal, out _, out ObjectResult? denied))
        {
            return denied!;
        }

        return Ok(new AndroidLinkedV2GrantStatusResponse(
            principal!.Installation.InstallationId,
            principal.GrantId,
            principal.Installation.Status,
            principal.IssuedAtUtc,
            principal.ExpiresAtUtc,
            _timeProvider.GetUtcNow()));
    }

    [HttpPost("grants/refresh")]
    [RequestSizeLimit(InstallLinkingService.MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedV2GrantRefreshResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedV2GrantRefreshResponse> RefreshGrant(
        [FromBody] AndroidLinkedV2GrantRefreshRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (AndroidLinkedV2RequestProof.TryGetRefreshRetryResult(
                HttpContext,
                out AndroidLinkedV2GrantRotationResult? recovered))
        {
            return GrantRefreshResponse(recovered!);
        }

        if (!TryResolvePrincipal(request, out AndroidLinkedV2GrantPrincipal? principal, out _, out ObjectResult? denied))
        {
            return denied!;
        }
        if (!AndroidLinkedV2RequestProof.TryGetAuthorizedRequest(
                HttpContext,
                out AndroidLinkedV2AuthorizedRequest? authorizedRequest))
        {
            return Problem(
                statusCode: StatusCodes.Status401Unauthorized,
                detail: "linked device grant is unknown or expired.");
        }

        try
        {
            AndroidLinkedV2GrantRotationResult result = _installLinking.RefreshAndroidLinkedV2Grant(
                principal!,
                new AndroidLinkedV2GrantRefreshCommand(
                    request!.InstallationId,
                    request.HeadId,
                    request.ApplicationVersion,
                    request.ChannelId,
                    request.Platform,
                    request.Architecture,
                    request.PublicKey,
                    request.HostLabel),
                authorizedRequest!);
            return GrantRefreshResponse(result);
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(
                statusCode: ex.StatusCode,
                detail: "The installation grant could not be refreshed.");
        }
    }

    private ActionResult<AndroidLinkedV2GrantRefreshResponse> GrantRefreshResponse(
        AndroidLinkedV2GrantRotationResult result)
    {
        Response.Headers["Authorization"] = $"Bearer {result.AccessToken}";
        Response.Headers[AndroidLinkedV2RequestProof.GrantHeader] = result.Grant.GrantId;
        return Ok(new AndroidLinkedV2GrantRefreshResponse(
            result.Installation,
            result.Grant,
            Rotated: true));
    }

    [HttpPost("grants/revoke")]
    [RequestSizeLimit(InstallLinkingService.MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedV2GrantRevokeResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedV2GrantRevokeResponse> RevokeGrant(
        [FromBody] AndroidLinkedV2GrantRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolvePrincipal(request, out AndroidLinkedV2GrantPrincipal? principal, out _, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            AndroidLinkedV2GrantRevocationResult result = _installLinking.RevokeAndroidLinkedV2Grant(principal!);
            return Ok(new AndroidLinkedV2GrantRevokeResponse(result.Installation, result.Grants));
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(
                statusCode: ex.StatusCode,
                detail: "The installation grant could not be revoked.");
        }
    }

    [HttpPost("continuation/workspaces/list")]
    [RequestSizeLimit(InstallLinkingService.MaxRequestBodyBytes)]
    [ProducesResponseType<InstallLinkedWorkspaceSnapshotListResponse>(StatusCodes.Status200OK)]
    public ActionResult<InstallLinkedWorkspaceSnapshotListResponse> ListClaimedInstallWorkspaces(
        [FromBody] AndroidLinkedV2GrantRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolvePrincipal(request, out _, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        InstallLinkedWorkspaceSnapshotDto[] snapshots = _workspaceSnapshots.ListForInstallation(installation!)
            .Select(static snapshot => ToSnapshotDto(snapshot))
            .ToArray();
        return Ok(new InstallLinkedWorkspaceSnapshotListResponse(snapshots));
    }

    [HttpPost("continuation/workspaces/upsert")]
    [RequestSizeLimit(InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes)]
    [ProducesResponseType<InstallLinkedWorkspaceSnapshotUpsertResponse>(StatusCodes.Status200OK)]
    public ActionResult<InstallLinkedWorkspaceSnapshotUpsertResponse> UpsertClaimedInstallWorkspace(
        [FromBody] AndroidLinkedV2WorkspaceSnapshotUpsertRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolvePrincipal(request, out _, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            InstallLinkedWorkspaceSnapshotRecord stored = _workspaceSnapshots.UpsertForInstallation(
                installation!,
                new InstallLinkedWorkspaceSnapshotRecord(
                    OwnerKey: string.Empty,
                    WorkspaceId: request!.WorkspaceId,
                    RulesetId: request.RulesetId,
                    Format: request.Format,
                    SchemaVersion: request.SchemaVersion,
                    PayloadKind: request.PayloadKind,
                    Payload: request.Payload ?? string.Empty,
                    UpdatedAtUtc: request.UpdatedAtUtc,
                    OriginInstallationId: request.OriginInstallationId,
                    Name: request.Name,
                    Alias: request.Alias,
                    Metatype: request.Metatype,
                    BuildMethod: request.BuildMethod,
                    CreatedVersion: request.CreatedVersion,
                    AppVersion: request.AppVersion,
                    Karma: request.Karma,
                    Nuyen: request.Nuyen,
                    Created: request.Created));
            return Ok(new InstallLinkedWorkspaceSnapshotUpsertResponse(ToSnapshotDto(stored)));
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    private bool TryResolvePrincipal(
        AndroidLinkedV2GrantRequest? request,
        out AndroidLinkedV2GrantPrincipal? principal,
        out ClaimedInstallationDto? installation,
        out ObjectResult? denied)
    {
        principal = null;
        installation = null;
        denied = null;
        if (request is null)
        {
            denied = Problem(statusCode: StatusCodes.Status400BadRequest, detail: "linked device payload is required.");
            return false;
        }

        if (!AndroidLinkedV2RequestProof.TryGetPrincipal(HttpContext, out principal)
            || !string.Equals(request.InstallationId, principal!.Installation.InstallationId, StringComparison.Ordinal)
            || (installation = _installLinking.ResolveAndroidLinkedV2Principal(principal)) is null)
        {
            denied = Problem(
                statusCode: StatusCodes.Status401Unauthorized,
                detail: "linked device grant is unknown or expired.");
            return false;
        }

        return true;
    }

    private static InstallLinkedWorkspaceSnapshotDto ToSnapshotDto(InstallLinkedWorkspaceSnapshotRecord snapshot)
        => new(
            WorkspaceId: snapshot.WorkspaceId,
            RulesetId: snapshot.RulesetId,
            Format: snapshot.Format,
            SchemaVersion: snapshot.SchemaVersion,
            PayloadKind: snapshot.PayloadKind,
            Payload: snapshot.Payload,
            UpdatedAtUtc: snapshot.UpdatedAtUtc,
            OriginInstallationId: snapshot.OriginInstallationId,
            Summary: new CharacterFileSummary(
                Name: snapshot.Name ?? snapshot.WorkspaceId,
                Alias: snapshot.Alias ?? snapshot.Name ?? snapshot.WorkspaceId,
                Metatype: snapshot.Metatype ?? "Unknown",
                BuildMethod: snapshot.BuildMethod ?? "Unknown",
                CreatedVersion: snapshot.CreatedVersion ?? snapshot.RulesetId,
                AppVersion: snapshot.AppVersion ?? snapshot.RulesetId,
                Karma: snapshot.Karma,
                Nuyen: snapshot.Nuyen,
                Created: snapshot.Created));

    private void ApplyPrivateResponseHeaders()
        => AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(Response.Headers);
}

public sealed record AndroidLinkedV2GrantRefreshRequest(
    string InstallationId,
    string? HeadId = null,
    string? ApplicationVersion = null,
    string? ChannelId = null,
    string? Platform = null,
    string? Architecture = null,
    string? PublicKey = null,
    string? HostLabel = null) : AndroidLinkedV2GrantRequest(InstallationId);

public sealed record AndroidInstallLinkV2ExchangeResponse(
    ClaimedInstallationDto Installation,
    AndroidLinkedV2GrantMetadata Grant,
    bool AlreadyClaimed,
    string GrantTransport = InstallLinkingService.AndroidLinkedV2GrantTransport);

public sealed record AndroidLinkedV2GrantStatusResponse(
    string InstallationId,
    string GrantId,
    string Status,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    DateTimeOffset ObservedAtUtc);

public sealed record AndroidLinkedV2GrantRefreshResponse(
    ClaimedInstallationDto Installation,
    AndroidLinkedV2GrantMetadata Grant,
    bool Rotated,
    string GrantTransport = InstallLinkingService.AndroidLinkedV2GrantTransport);

public sealed record AndroidLinkedV2GrantRevokeResponse(
    ClaimedInstallationDto Installation,
    IReadOnlyList<AndroidLinkedV2GrantMetadata> Grants);

public sealed record AndroidLinkedV2WorkspaceSnapshotUpsertRequest(
    string InstallationId,
    string WorkspaceId,
    string RulesetId,
    string Format,
    int SchemaVersion,
    string PayloadKind,
    string Payload,
    DateTimeOffset UpdatedAtUtc,
    string? OriginInstallationId,
    string? Name,
    string? Alias,
    string? Metatype,
    string? BuildMethod,
    string? CreatedVersion,
    string? AppVersion,
    decimal Karma,
    decimal Nuyen,
    bool Created) : AndroidLinkedV2GrantRequest(InstallationId);
