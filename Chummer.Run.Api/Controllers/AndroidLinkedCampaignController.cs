using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;
using System.Security.Cryptography;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/android/linked")]
public sealed class AndroidLinkedCampaignController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;
    private readonly InstallLinkingService _installLinking;
    private readonly GroupService _groups;

    public AndroidLinkedCampaignController(InstallLinkingService installLinking, GroupService groups)
    {
        _installLinking = installLinking;
        _groups = groups;
    }

    [HttpPost("groups")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedGroupListResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedGroupListResponse> ListGroups([FromBody] AndroidLinkedGrantRequest? request)
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
    public ActionResult<AndroidLinkedGroupDto> CreateGroup([FromBody] AndroidLinkedGroupCreateRequest? request)
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
        [FromBody] AndroidLinkedGroupUpdateRequest? request)
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
            return Problem(statusCode: ex is KeyNotFoundException ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/invites")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedInviteResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedInviteResponse> CreateInvite(
        [FromRoute] string groupId,
        [FromBody] AndroidLinkedGrantRequest? request)
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
            return Problem(statusCode: ex is KeyNotFoundException ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleListResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleListResponse> ListChronicles(
        [FromRoute] string groupId,
        [FromBody] AndroidLinkedGrantRequest? request)
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
            return Problem(statusCode: ex is KeyNotFoundException ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/create")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleDto> CreateChronicle(
        [FromRoute] string groupId,
        [FromBody] AndroidLinkedChronicleDraftRequest? request)
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
            return Problem(statusCode: ex is KeyNotFoundException ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/{chronicleProjectId}/draft")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleDto> ReviseChronicle(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] AndroidLinkedChronicleDraftRequest? request)
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
            return Problem(statusCode: ex is KeyNotFoundException ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/{chronicleProjectId}/actions")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChronicleDto>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChronicleDto> AdvanceChronicle(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] AndroidLinkedChronicleActionRequest? request)
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
            return Problem(statusCode: ex is KeyNotFoundException ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpPost("groups/{groupId}/chronicles/{chronicleProjectId}/packet")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<AndroidLinkedChroniclePacketResponse>(StatusCodes.Status200OK)]
    public ActionResult<AndroidLinkedChroniclePacketResponse> DownloadChroniclePacket(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] AndroidLinkedGrantRequest? request)
    {
        ApplyPrivateResponseHeaders();
        if (!TryResolveInstallation(request, out ClaimedInstallationDto? installation, out ObjectResult? denied))
        {
            return denied!;
        }

        byte[]? packet = null;
        try
        {
            packet = _groups.GetChronicleSourcePacket(groupId, chronicleProjectId, installation!.SubjectId!);
            return Ok(new AndroidLinkedChroniclePacketResponse(
                $"chronicle-{chronicleProjectId}.md",
                "text/markdown",
                Convert.ToBase64String(packet),
                Convert.ToHexString(SHA256.HashData(packet)).ToLowerInvariant()));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException)
        {
            return Problem(statusCode: ex is KeyNotFoundException ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, detail: ex.Message);
        }
        finally
        {
            if (packet is not null)
            {
                CryptographicOperations.ZeroMemory(packet);
            }
        }
    }

    private bool TryResolveInstallation(
        AndroidLinkedGrantRequest? request,
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

        installation = _installLinking.ResolveInstallationForGrant(request.InstallationId, request.AccessToken);
        if (installation is null || string.IsNullOrWhiteSpace(installation.SubjectId))
        {
            denied = Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "linked device grant is unknown or expired.");
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
        AndroidLinkedChronicleDraftRequest request,
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
        AndroidLinkedChronicleDraftRequest request,
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
    {
        Response.Headers.CacheControl = "no-store, max-age=0";
        Response.Headers.Pragma = "no-cache";
        Response.Headers["X-Content-Type-Options"] = "nosniff";
        Response.Headers["Referrer-Policy"] = "no-referrer";
    }
}

public record AndroidLinkedGrantRequest(string InstallationId, string AccessToken);

public sealed record AndroidLinkedGroupCreateRequest(
    string InstallationId,
    string AccessToken,
    string Name,
    string Visibility) : AndroidLinkedGrantRequest(InstallationId, AccessToken);

public sealed record AndroidLinkedGroupUpdateRequest(
    string InstallationId,
    string AccessToken,
    string Name,
    string Visibility) : AndroidLinkedGrantRequest(InstallationId, AccessToken);

public sealed record AndroidLinkedGroupListResponse(IReadOnlyList<AndroidLinkedGroupDto> Groups);

public sealed record AndroidLinkedGroupDto(
    string GroupId,
    string Name,
    string GroupType,
    string Visibility,
    string Role,
    bool CanManage,
    string? RunnerDossierId,
    string? RunnerHandle,
    IReadOnlyList<AndroidLinkedGroupMemberDto> Members,
    DateTimeOffset UpdatedAtUtc);

public sealed record AndroidLinkedGroupMemberDto(string Role, string? RunnerHandle);

public sealed record AndroidLinkedInviteResponse(string Code, string InviteUrl, DateTimeOffset? ExpiresAtUtc);

public sealed record AndroidLinkedChronicleDraftRequest(
    string InstallationId,
    string AccessToken,
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
    bool SpoilerReviewConfirmed = false) : AndroidLinkedGrantRequest(InstallationId, AccessToken);

public sealed record AndroidLinkedChronicleActionRequest(
    string InstallationId,
    string AccessToken,
    string Action,
    string? ExternalProjectRef = null,
    string? ArtifactUrl = null,
    string? ArtifactSha256 = null,
    string? ExportFormat = null) : AndroidLinkedGrantRequest(InstallationId, AccessToken);

public sealed record AndroidLinkedChronicleListResponse(IReadOnlyList<AndroidLinkedChronicleDto> Projects);

public sealed record AndroidLinkedChronicleDto(
    string ChronicleProjectId,
    string Title,
    string BookKind,
    string Audience,
    string Status,
    string SourceSummary,
    string ModelKey,
    int TargetChapterCount,
    int TargetWordsPerChapter,
    bool IncludeRunnerRoster,
    IReadOnlyList<string> RunnerRoster,
    bool IncludeCover,
    bool IncludeTranslation,
    bool IncludeAudiobook,
    bool ExternalProcessingConsent,
    bool ParticipantConsentConfirmed,
    bool RedactionReviewed,
    bool SourceRightsConfirmed,
    int SourcePacketVersion,
    string SourcePacketSha256,
    int EstimatedCredits,
    string Provider,
    bool OperatorRequired,
    bool UnattendedAutomationAllowed,
    string? ExternalProjectRef,
    string? ArtifactUrl,
    string? ArtifactSha256,
    string? ExportFormat,
    DateTimeOffset? SourceApprovedAtUtc,
    DateTimeOffset? HandoffApprovedAtUtc,
    DateTimeOffset? OutlineApprovedAtUtc,
    DateTimeOffset? ArtifactImportedAtUtc,
    DateTimeOffset? PublicationApprovedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    bool SpoilerReviewConfirmed = false,
    DateTimeOffset? GenerationApprovedAtUtc = null,
    DateTimeOffset? ExternalSendApprovedAtUtc = null,
    DateTimeOffset? UploadApprovedAtUtc = null);

public sealed record AndroidLinkedChroniclePacketResponse(
    string FileName,
    string MediaType,
    string ContentBase64,
    string Sha256);
