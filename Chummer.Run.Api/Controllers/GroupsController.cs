using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/groups")]
public sealed class GroupsController : Controller
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly GroupService _groups;
    private readonly HubIdentityClient _identity;
    private readonly HubPageChromeService? _chrome;

    public GroupsController(GroupService groups, HubIdentityClient identity, HubPageChromeService? chrome = null)
    {
        _groups = groups;
        _identity = identity;
        _chrome = chrome;
    }

    [HttpGet("/groups")]
    [Produces("text/html")]
    public async Task<IActionResult> GroupsPage(
        [FromQuery] string? notice,
        [FromQuery] string? focus,
        CancellationToken cancellationToken)
    {
        bool focusChronicles = string.Equals(focus, "chronicles", StringComparison.OrdinalIgnoreCase);
        string currentPath = focusChronicles ? "/groups?focus=chronicles" : "/groups";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            string signedInLabel = subject.DisplayName ?? subject.SubjectId;
            return View("~/Views/Groups/Index.cshtml", new GroupListPageViewModel(
                Chrome: BuildChrome(
                    focusChronicles ? "Chronicle Studio" : "Groups",
                    focusChronicles ? "Choose a group for its books and exports." : "Create a group, manage a roster, or open an invite.",
                    currentPath,
                    signedInLabel,
                    subject.Email),
                SignedInLabel: signedInLabel,
                Groups: _groups.ListGroupsForUser(subject.SubjectId),
                Notice: notice,
                FocusChronicles: focusChronicles));
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    [HttpGet("/groups/{groupId}")]
    [Produces("text/html")]
    public async Task<IActionResult> GroupPage(
        [FromRoute] string groupId,
        [FromQuery] string? notice,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/groups/{Uri.EscapeDataString(groupId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            GroupDto? group = _groups.ListGroupsForUser(subject.SubjectId)
                .FirstOrDefault(item => string.Equals(item.GroupId, groupId, StringComparison.OrdinalIgnoreCase));
            if (group is null)
            {
                return NotFound();
            }

            bool canManage = _groups.CanManageGroupForSubject(group.GroupId, subject.SubjectId);
            IReadOnlyList<JoinCodeDto> joinCodes = canManage
                ? _groups.ListJoinCodes(group.GroupId, subject.SubjectId).Select(WithInviteUrl).ToArray()
                : [];
            string signedInLabel = subject.DisplayName ?? subject.SubjectId;
            return View("~/Views/Groups/Detail.cshtml", new GroupDetailPageViewModel(
                Chrome: BuildChrome(group.Name, "Roster, settings, and invitation links.", currentPath, signedInLabel, subject.Email),
                Group: group,
                JoinCodes: joinCodes,
                ChronicleProjects: _groups.ListChronicleProjects(group.GroupId, subject.SubjectId),
                CanManage: canManage,
                Notice: notice));
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    [HttpGet("/groups/join/{code}")]
    [Produces("text/html")]
    public async Task<IActionResult> JoinPage(
        [FromRoute] string code,
        [FromQuery] string? dossierId,
        [FromQuery] string? notice,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/groups/join/{Uri.EscapeDataString(code)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            JoinCodeDto? invite = _groups.GetJoinCode(code);
            GroupDto? group = invite is null ? null : _groups.GetGroup(invite.GroupId);
            if (invite is null || group is null)
            {
                return NotFound();
            }

            string signedInLabel = subject.DisplayName ?? subject.SubjectId;
            return View("~/Views/Groups/Join.cshtml", new GroupJoinPageViewModel(
                Chrome: BuildChrome($"Join {group.Name}", "Choose the runner who will join this group.", currentPath, signedInLabel, subject.Email),
                Group: group,
                Invite: WithInviteUrl(invite),
                Runners: _groups.ListOwnedRunners(subject.SubjectId),
                SelectedDossierId: dossierId,
                Notice: notice));
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    [HttpPost("/groups")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> CreateFromPage(
        [FromForm] string name,
        [FromForm] string visibility,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            GroupDto group = _groups.CreateGroup(new CreateGroupRequest(
                SubjectId: subject.SubjectId,
                Name: name,
                GroupType: "campaign",
                Visibility: visibility,
                Capabilities: null));
            return Redirect($"/groups/{Uri.EscapeDataString(group.GroupId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=%2Fgroups");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException)
        {
            return Redirect($"/groups?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/{groupId}/edit")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> EditFromPage(
        [FromRoute] string groupId,
        [FromForm] string name,
        [FromForm] string visibility,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _groups.UpdateGroup(groupId, new UpdateGroupRequest(subject.SubjectId, name, visibility));
            return Redirect($"/groups/{Uri.EscapeDataString(groupId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString($"/groups/{groupId}")}");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or CommunityAccessDeniedException)
        {
            return Redirect($"/groups/{Uri.EscapeDataString(groupId)}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/{groupId}/chronicles")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> CreateChronicleFromPage(
        [FromRoute] string groupId,
        [FromForm] string title,
        [FromForm] string bookKind,
        [FromForm] string audience,
        [FromForm] string sourceSummary,
        [FromForm] string modelKey,
        [FromForm] int targetChapterCount,
        [FromForm] int targetWordsPerChapter,
        [FromForm] bool includeRunnerRoster,
        [FromForm] bool includeCover,
        [FromForm] bool includeTranslation,
        [FromForm] bool includeAudiobook,
        [FromForm] bool externalProcessingConsent,
        [FromForm] bool participantConsentConfirmed,
        [FromForm] bool redactionReviewed,
        [FromForm] bool spoilerReviewConfirmed,
        [FromForm] bool sourceRightsConfirmed,
        CancellationToken cancellationToken)
    {
        string groupPath = $"/groups/{Uri.EscapeDataString(groupId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _groups.CreateChronicleProject(groupId, new CreateChronicleProjectRequest(
                subject.SubjectId,
                title,
                bookKind,
                audience,
                sourceSummary,
                modelKey,
                targetChapterCount,
                targetWordsPerChapter,
                includeRunnerRoster,
                includeCover,
                includeTranslation,
                includeAudiobook,
                externalProcessingConsent,
                participantConsentConfirmed,
                redactionReviewed,
                sourceRightsConfirmed,
                spoilerReviewConfirmed));
            return Redirect($"{groupPath}?notice={Uri.EscapeDataString("Chronicle created.")}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(groupPath)}");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or CommunityAccessDeniedException or KeyNotFoundException)
        {
            return Redirect($"{groupPath}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/{groupId}/chronicles/{chronicleProjectId}/draft")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> ReviseChronicleFromPage(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromForm] string title,
        [FromForm] string bookKind,
        [FromForm] string audience,
        [FromForm] string sourceSummary,
        [FromForm] string modelKey,
        [FromForm] int targetChapterCount,
        [FromForm] int targetWordsPerChapter,
        [FromForm] bool includeRunnerRoster,
        [FromForm] bool includeCover,
        [FromForm] bool includeTranslation,
        [FromForm] bool includeAudiobook,
        [FromForm] bool externalProcessingConsent,
        [FromForm] bool participantConsentConfirmed,
        [FromForm] bool redactionReviewed,
        [FromForm] bool spoilerReviewConfirmed,
        [FromForm] bool sourceRightsConfirmed,
        CancellationToken cancellationToken)
    {
        string groupPath = $"/groups/{Uri.EscapeDataString(groupId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            ChronicleProjectDto project = _groups.ReviseChronicleProject(groupId, chronicleProjectId, new ReviseChronicleProjectRequest(
                subject.SubjectId,
                title,
                bookKind,
                audience,
                sourceSummary,
                modelKey,
                targetChapterCount,
                targetWordsPerChapter,
                includeRunnerRoster,
                includeCover,
                includeTranslation,
                includeAudiobook,
                externalProcessingConsent,
                participantConsentConfirmed,
                redactionReviewed,
                sourceRightsConfirmed,
                spoilerReviewConfirmed));
            return Redirect($"{groupPath}?notice={Uri.EscapeDataString($"Draft saved as packet v{project.SourcePacketVersion}.")}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(groupPath)}");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or CommunityAccessDeniedException or KeyNotFoundException or OverflowException)
        {
            return Redirect($"{groupPath}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/{groupId}/chronicles/{chronicleProjectId}/actions")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> UpdateChronicleFromPage(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromForm] string action,
        [FromForm] string? externalProjectRef,
        [FromForm] string? artifactUrl,
        [FromForm] string? artifactSha256,
        [FromForm] string? exportFormat,
        CancellationToken cancellationToken)
    {
        string groupPath = $"/groups/{Uri.EscapeDataString(groupId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _groups.UpdateChronicleProject(groupId, chronicleProjectId, new UpdateChronicleProjectRequest(
                subject.SubjectId,
                action,
                externalProjectRef,
                artifactUrl,
                artifactSha256,
                exportFormat));
            return Redirect(groupPath);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(groupPath)}");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or CommunityAccessDeniedException or KeyNotFoundException)
        {
            return Redirect($"{groupPath}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpGet("/groups/{groupId}/chronicles/{chronicleProjectId}/packet")]
    public async Task<IActionResult> DownloadChroniclePacketFromPage(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        CancellationToken cancellationToken)
    {
        string groupPath = $"/groups/{Uri.EscapeDataString(groupId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            byte[] packet = _groups.GetChronicleSourcePacket(groupId, chronicleProjectId, subject.SubjectId);
            return File(packet, "text/markdown; charset=utf-8", $"chronicle-{chronicleProjectId}.md");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(groupPath)}");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or CommunityAccessDeniedException or KeyNotFoundException)
        {
            return Redirect($"{groupPath}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/{groupId}/invites")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> CreateInviteFromPage([FromRoute] string groupId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _groups.CreateJoinCode(groupId, new CreateJoinCodeRequest(
                SubjectId: subject.SubjectId,
                Role: "member",
                Ttl: TimeSpan.FromDays(7),
                MaxUses: 25));
            return Redirect($"/groups/{Uri.EscapeDataString(groupId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString($"/groups/{groupId}")}");
        }
        catch (Exception ex) when (ex is InvalidOperationException or CommunityAccessDeniedException)
        {
            return Redirect($"/groups/{Uri.EscapeDataString(groupId)}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/{groupId}/invites/{code}/revoke")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> RevokeInviteFromPage(
        [FromRoute] string groupId,
        [FromRoute] string code,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _groups.RevokeJoinCode(groupId, code, subject.SubjectId);
            return Redirect($"/groups/{Uri.EscapeDataString(groupId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString($"/groups/{groupId}")}");
        }
        catch (Exception ex) when (ex is InvalidOperationException or CommunityAccessDeniedException or KeyNotFoundException)
        {
            return Redirect($"/groups/{Uri.EscapeDataString(groupId)}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/join/{code}/runners")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> CreateRunnerFromJoinPage(
        [FromRoute] string code,
        [FromForm] string runnerHandle,
        CancellationToken cancellationToken)
    {
        string joinPath = $"/groups/join/{Uri.EscapeDataString(code)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var runner = _groups.CreateRunner(new CreateRunnerRequest(subject.SubjectId, runnerHandle, runnerHandle));
            return Redirect($"{joinPath}?dossierId={Uri.EscapeDataString(runner.DossierId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(joinPath)}");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException)
        {
            return Redirect($"{joinPath}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpPost("/groups/join/{code}")]
    [Consumes("application/x-www-form-urlencoded")]
    public async Task<IActionResult> JoinFromPage(
        [FromRoute] string code,
        [FromForm] string dossierId,
        CancellationToken cancellationToken)
    {
        string joinPath = $"/groups/join/{Uri.EscapeDataString(code)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            GroupDto group = _groups.JoinGroup(new JoinGroupByCodeRequest(subject.SubjectId, code, dossierId));
            return Redirect($"/groups/{Uri.EscapeDataString(group.GroupId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(joinPath)}");
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or KeyNotFoundException)
        {
            return Redirect($"{joinPath}?notice={Uri.EscapeDataString(ex.Message)}");
        }
    }

    [HttpGet]
    [ProducesResponseType(typeof(IReadOnlyList<GroupDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<GroupDto>>> ListForSubject([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            return Ok(_groups.ListGroupsForUser(subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("{groupId}")]
    [ProducesResponseType<GroupDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<GroupDto>> GetGroup([FromRoute] string groupId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var group = _groups.GetGroup(groupId);
            if (group is null)
            {
                return NotFound();
            }

            var visibleGroup = _groups.ListGroupsForUser(subject.SubjectId)
                .FirstOrDefault(item => string.Equals(item.GroupId, groupId, StringComparison.OrdinalIgnoreCase));
            if (visibleGroup is null)
            {
                return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "group does not belong to the authenticated subject.");
            }

            return Ok(visibleGroup);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost]
    [ProducesResponseType<GroupDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<GroupDto>> Create([FromBody] CreateGroupRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("group payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.CreateGroup(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPut("{groupId}")]
    [ProducesResponseType<GroupDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<GroupDto>> Update(
        [FromRoute] string groupId,
        [FromBody] UpdateGroupRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("group payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.UpdateGroup(groupId, request with { SubjectId = subject.SubjectId }));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpGet("{groupId}/chronicles")]
    [ProducesResponseType<IReadOnlyList<ChronicleProjectDto>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<ChronicleProjectDto>>> ListChronicles(
        [FromRoute] string groupId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(_groups.ListChronicleProjects(groupId, subject.SubjectId));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("{groupId}/chronicles")]
    [ProducesResponseType<ChronicleProjectDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<ChronicleProjectDto>> CreateChronicle(
        [FromRoute] string groupId,
        [FromBody] CreateChronicleProjectRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("chronicle payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.CreateChronicleProject(groupId, request with { SubjectId = subject.SubjectId }));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPut("{groupId}/chronicles/{chronicleProjectId}/draft")]
    [ProducesResponseType<ChronicleProjectDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<ChronicleProjectDto>> ReviseChronicle(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] ReviseChronicleProjectRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("chronicle draft payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.ReviseChronicleProject(groupId, chronicleProjectId, request with { SubjectId = subject.SubjectId }));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException or OverflowException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("{groupId}/chronicles/{chronicleProjectId}/actions")]
    [ProducesResponseType<ChronicleProjectDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<ChronicleProjectDto>> UpdateChronicle(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        [FromBody] UpdateChronicleProjectRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("chronicle action payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.UpdateChronicleProject(groupId, chronicleProjectId, request with { SubjectId = subject.SubjectId }));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpGet("{groupId}/chronicles/{chronicleProjectId}/packet")]
    public async Task<IActionResult> DownloadChroniclePacket(
        [FromRoute] string groupId,
        [FromRoute] string chronicleProjectId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            byte[] packet = _groups.GetChronicleSourcePacket(groupId, chronicleProjectId, subject.SubjectId);
            return File(packet, "text/markdown; charset=utf-8", $"chronicle-{chronicleProjectId}.md");
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("{groupId}/join-codes")]
    [ProducesResponseType<JoinCodeDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<JoinCodeDto>> CreateJoinCode([FromRoute] string groupId, [FromBody] CreateJoinCodeRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("join-code payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(WithInviteUrl(_groups.CreateJoinCode(groupId, request with { SubjectId = subject.SubjectId })));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpGet("{groupId}/join-codes")]
    [ProducesResponseType<IReadOnlyList<JoinCodeDto>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<JoinCodeDto>>> ListJoinCodes(
        [FromRoute] string groupId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(_groups.ListJoinCodes(groupId, subject.SubjectId).Select(WithInviteUrl).ToArray());
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpDelete("{groupId}/join-codes/{code}")]
    [ProducesResponseType<JoinCodeDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<JoinCodeDto>> RevokeJoinCode(
        [FromRoute] string groupId,
        [FromRoute] string code,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(WithInviteUrl(_groups.RevokeJoinCode(groupId, code, subject.SubjectId)));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpGet("runners")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<IActionResult> ListRunners([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            return Ok(_groups.ListOwnedRunners(subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("runners")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<IActionResult> CreateRunner([FromBody] CreateRunnerRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("runner payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.CreateRunner(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("join")]
    [ProducesResponseType<GroupDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<GroupDto>> Join([FromBody] JoinGroupByCodeRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("join payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.JoinGroup(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    private JoinCodeDto WithInviteUrl(JoinCodeDto invite)
    {
        string origin = $"{Request.Scheme}://{Request.Host}{Request.PathBase}".TrimEnd('/');
        return invite with
        {
            InviteUrl = $"{origin}/groups/join/{Uri.EscapeDataString(invite.Code)}"
        };
    }

    private SiteChromeViewModel BuildChrome(
        string title,
        string description,
        string currentPath,
        string signedInLabel,
        string? signedInEmail)
        => _chrome?.BuildAuthenticatedChrome(title, description, currentPath, signedInLabel, signedInEmail)
            ?? throw new InvalidOperationException("group page chrome is unavailable.");

}
