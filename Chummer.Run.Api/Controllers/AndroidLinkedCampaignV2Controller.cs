using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;
using System.Security.Cryptography;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v2/android/linked")]
public sealed class AndroidLinkedCampaignV2Controller : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;
    private readonly InstallLinkingService _installLinking;
    private readonly GroupService _groups;

    public AndroidLinkedCampaignV2Controller(InstallLinkingService installLinking, GroupService groups)
    {
        _installLinking = installLinking;
        _groups = groups;
    }

    [HttpPost("groups")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedGroupListResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedGroupListResponse> ListGroups(
        [FromBody] AndroidLinkedV2GrantRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        IReadOnlyList<AndroidLinkedGroupDto> groups = _groups.ListGroupsForUser(installation!.SubjectId!)
            .Select(group => ToAndroidGroup(group, installation))
            .ToArray();
        return Ok(new AndroidLinkedGroupListResponse(groups));
    }

    [HttpPost("groups/create")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedGroupDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedGroupDto> CreateGroup(
        [FromBody] AndroidLinkedV2GroupCreateRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            GroupDto group = _groups.CreateGroup(new CreateGroupRequest(
                installation!.SubjectId!,
                request!.Name,
                GroupType: "campaign",
                Visibility: request.Visibility,
                Capabilities: null));
            return Ok(ToAndroidGroup(group, installation));
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/update")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedGroupDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedGroupDto> UpdateGroup(
        [FromRoute] string groupId,
        [FromBody] AndroidLinkedV2GroupUpdateRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            GroupDto group = _groups.UpdateGroup(
                groupId,
                new UpdateGroupRequest(installation!.SubjectId!, request!.Name, request.Visibility));
            return Ok(ToAndroidGroup(group, installation));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException)
        {
            return Problem(
                statusCode: ex is KeyNotFoundException
                    ? StatusCodes.Status404NotFound
                    : StatusCodes.Status400BadRequest,
                detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/invites")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedInviteResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedInviteResponse> CreateInvite(
        [FromRoute] string groupId,
        [FromBody] AndroidLinkedV2GrantRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            JoinCodeDto invite = _groups.CreateJoinCode(groupId, new CreateJoinCodeRequest(
                installation!.SubjectId!,
                Role: "member",
                Ttl: TimeSpan.FromDays(7),
                MaxUses: 25));
            string inviteUrl = $"https://chummer.run/groups/join/{Uri.EscapeDataString(invite.Code)}";
            return Ok(new AndroidLinkedInviteResponse(invite.Code, inviteUrl, invite.ExpiresAtUtc));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException)
        {
            return Problem(
                statusCode: ex is KeyNotFoundException
                    ? StatusCodes.Status404NotFound
                    : StatusCodes.Status400BadRequest,
                detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleListResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleListResponse> ListChronicles(
        [FromRoute] string groupId,
        [FromBody] AndroidLinkedV2GrantRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            IReadOnlyList<AndroidLinkedChronicleDto> projects = _groups
                .ListChronicleProjects(groupId, installation!.SubjectId!)
                .Select(ToAndroidChronicle)
                .ToArray();
            return Ok(new AndroidLinkedChronicleListResponse(projects));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException)
        {
            return Problem(
                statusCode: ex is KeyNotFoundException
                    ? StatusCodes.Status404NotFound
                    : StatusCodes.Status400BadRequest,
                detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/create")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleDto> CreateChronicle(
        [FromRoute] string groupId,
        [FromBody] AndroidLinkedV2ChronicleDraftRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            ChronicleProjectDto project = _groups.CreateChronicleProject(
                groupId,
                ToCreateChronicleRequest(request!, installation!.SubjectId!));
            return Ok(ToAndroidChronicle(project));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException or OverflowException)
        {
            return Problem(
                statusCode: ex is KeyNotFoundException
                    ? StatusCodes.Status404NotFound
                    : StatusCodes.Status400BadRequest,
                detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/{chronicleProjectId}/draft")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleDto> ReviseChronicle(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] AndroidLinkedV2ChronicleDraftRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            ChronicleProjectDto project = _groups.ReviseChronicleProject(
                groupId,
                chronicleProjectId,
                ToReviseChronicleRequest(request!, installation!.SubjectId!));
            return Ok(ToAndroidChronicle(project));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException or OverflowException)
        {
            return Problem(
                statusCode: ex is KeyNotFoundException
                    ? StatusCodes.Status404NotFound
                    : StatusCodes.Status400BadRequest,
                detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/{chronicleProjectId}/actions")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleDto> AdvanceChronicle(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] AndroidLinkedV2ChronicleActionRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        try
        {
            ChronicleProjectDto project = _groups.UpdateChronicleProject(
                groupId,
                chronicleProjectId,
                new UpdateChronicleProjectRequest(
                    installation!.SubjectId!,
                    request!.Action,
                    request.ExternalProjectRef,
                    request.ArtifactUrl,
                    request.ArtifactSha256,
                    request.ExportFormat));
            return Ok(ToAndroidChronicle(project));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException)
        {
            return Problem(
                statusCode: ex is KeyNotFoundException
                    ? StatusCodes.Status404NotFound
                    : StatusCodes.Status400BadRequest,
                detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/{chronicleProjectId}/packet")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChroniclePacketResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChroniclePacketResponse> DownloadChroniclePacket(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] AndroidLinkedV2GrantRequest? request)
        => DownloadChronicleContent(groupId, chronicleProjectId, request, handoff: false);

    [HttpPost("groups/{groupId}/chronicles/{chronicleProjectId}/handoff")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChroniclePacketResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChroniclePacketResponse> DownloadChronicleHandoff(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] AndroidLinkedV2GrantRequest? request)
        => DownloadChronicleContent(groupId, chronicleProjectId, request, handoff: true);

    private ActionResult<AndroidLinkedChroniclePacketResponse> DownloadChronicleContent(
        string groupId,
        string chronicleProjectId,
        AndroidLinkedV2GrantRequest? request,
        bool handoff)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        byte[]? content = null;
        try
        {
            content = handoff
                ? _groups.GetChronicleOperatorHandoff(groupId, chronicleProjectId, installation!.SubjectId!)
                : _groups.GetChronicleSourcePacket(groupId, chronicleProjectId, installation!.SubjectId!);
            return Ok(new AndroidLinkedChroniclePacketResponse(
                handoff
                    ? $"chronicle-{chronicleProjectId}-handoff.json"
                    : $"chronicle-{chronicleProjectId}.md",
                handoff ? "application/json" : "text/markdown",
                Convert.ToBase64String(content),
                Convert.ToHexString(SHA256.HashData(content)).ToLowerInvariant()));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException)
        {
            return Problem(
                statusCode: ex is KeyNotFoundException
                    ? StatusCodes.Status404NotFound
                    : StatusCodes.Status400BadRequest,
                detail: ex.Message);
        }
        finally
        {
            if (content is not null)
            {
                CryptographicOperations.ZeroMemory(content);
            }
        }
    }

    private bool TryResolveInstallation(
        AndroidLinkedV2GrantRequest? request,
        out ClaimedInstallationDto? installation,
        out ObjectResult? denied)
    {
        installation = null;
        denied = null;
        if (request is null)
        {
            denied = Problem(statusCode: StatusCodes.Status400BadRequest, detail: "linked device payload is required.");
            return false;
        }

        if (!AndroidLinkedV2RequestProof.TryGetPrincipal(HttpContext, out AndroidLinkedV2GrantPrincipal? principal)
            || !string.Equals(request.InstallationId, principal!.Installation.InstallationId, StringComparison.Ordinal)
            || (installation = _installLinking.ResolveAndroidLinkedV2Principal(principal)) is null
            || string.IsNullOrWhiteSpace(installation.SubjectId))
        {
            denied = Problem(
                statusCode: StatusCodes.Status401Unauthorized,
                detail: "linked device grant is unknown or expired.");
            return false;
        }

        return true;
    }

    private AndroidLinkedGroupDto ToAndroidGroup(GroupDto group, ClaimedInstallationDto installation)
    {
        GroupMembershipDto? membership = group.Memberships.FirstOrDefault(item =>
            string.Equals(item.UserId, installation.UserId, StringComparison.OrdinalIgnoreCase));
        bool canManage = _groups.CanManageGroupForSubject(group.GroupId, installation.SubjectId!);
        IReadOnlyList<AndroidLinkedGroupMemberDto> members = group.Memberships
            .OrderBy(static item => item.JoinedAtUtc)
            .Select(static item => new AndroidLinkedGroupMemberDto(item.Role, item.RunnerHandle))
            .ToArray();
        return new AndroidLinkedGroupDto(
            group.GroupId,
            group.Name,
            group.GroupType,
            group.Visibility,
            membership?.Role ?? "member",
            canManage,
            membership?.RunnerDossierId,
            membership?.RunnerHandle,
            members,
            group.UpdatedAtUtc);
    }

    private static CreateChronicleProjectRequest ToCreateChronicleRequest(
        AndroidLinkedV2ChronicleDraftRequest request,
        string subjectId)
        => new(
            subjectId,
            request.Title,
            request.BookKind,
            request.Audience,
            request.SourceSummary,
            request.ModelKey,
            request.TargetChapterCount,
            request.TargetWordsPerChapter,
            request.IncludeRunnerRoster,
            request.IncludeCover,
            request.IncludeTranslation,
            request.IncludeAudiobook,
            request.ExternalProcessingConsent,
            request.ParticipantConsentConfirmed,
            request.RedactionReviewed,
            request.SourceRightsConfirmed,
            request.SpoilerReviewConfirmed);

    private static ReviseChronicleProjectRequest ToReviseChronicleRequest(
        AndroidLinkedV2ChronicleDraftRequest request,
        string subjectId)
        => new(
            subjectId,
            request.Title,
            request.BookKind,
            request.Audience,
            request.SourceSummary,
            request.ModelKey,
            request.TargetChapterCount,
            request.TargetWordsPerChapter,
            request.IncludeRunnerRoster,
            request.IncludeCover,
            request.IncludeTranslation,
            request.IncludeAudiobook,
            request.ExternalProcessingConsent,
            request.ParticipantConsentConfirmed,
            request.RedactionReviewed,
            request.SourceRightsConfirmed,
            request.SpoilerReviewConfirmed);

    private static AndroidLinkedChronicleDto ToAndroidChronicle(ChronicleProjectDto project)
        => new(
            project.ChronicleProjectId,
            project.Title,
            project.BookKind,
            project.Audience,
            project.Status,
            project.SourceSummary,
            project.ModelKey,
            project.TargetChapterCount,
            project.TargetWordsPerChapter,
            project.IncludeRunnerRoster,
            project.RunnerRoster,
            project.IncludeCover,
            project.IncludeTranslation,
            project.IncludeAudiobook,
            project.ExternalProcessingConsent,
            project.ParticipantConsentConfirmed,
            project.RedactionReviewed,
            project.SourceRightsConfirmed,
            project.SourcePacketVersion,
            project.SourcePacketSha256,
            project.EstimatedCredits,
            project.Provider,
            project.OperatorRequired,
            project.UnattendedAutomationAllowed,
            project.ExternalProjectRef,
            project.ArtifactUrl,
            project.ArtifactSha256,
            project.ExportFormat,
            project.SourceApprovedAtUtc,
            project.HandoffApprovedAtUtc,
            project.OutlineApprovedAtUtc,
            project.ArtifactImportedAtUtc,
            project.PublicationApprovedAtUtc,
            project.UpdatedAtUtc,
            project.SpoilerReviewConfirmed,
            project.GenerationApprovedAtUtc,
            project.ExternalSendApprovedAtUtc,
            project.UploadApprovedAtUtc);

    private void ApplyPrivateResponseHeaders()
        => AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(Response.Headers);
}

public record AndroidLinkedV2GrantRequest(string InstallationId);

public sealed record AndroidLinkedV2GroupCreateRequest(
    string InstallationId,
    string Name,
    string Visibility) : AndroidLinkedV2GrantRequest(InstallationId);

public sealed record AndroidLinkedV2GroupUpdateRequest(
    string InstallationId,
    string Name,
    string Visibility) : AndroidLinkedV2GrantRequest(InstallationId);

public sealed record AndroidLinkedV2ChronicleDraftRequest(
    string InstallationId,
    string Title,
    string BookKind,
    string Audience,
    string SourceSummary,
    string ModelKey,
    int TargetChapterCount,
    int TargetWordsPerChapter,
    bool IncludeRunnerRoster,
    bool IncludeCover,
    bool IncludeTranslation,
    bool IncludeAudiobook,
    bool ExternalProcessingConsent,
    bool ParticipantConsentConfirmed,
    bool RedactionReviewed,
    bool SourceRightsConfirmed,
    bool SpoilerReviewConfirmed = false) : AndroidLinkedV2GrantRequest(InstallationId);

public sealed record AndroidLinkedV2ChronicleActionRequest(
    string InstallationId,
    string Action,
    string? ExternalProjectRef = null,
    string? ArtifactUrl = null,
    string? ArtifactSha256 = null,
    string? ExportFormat = null) : AndroidLinkedV2GrantRequest(InstallationId);
