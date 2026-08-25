using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.ViewModels;
using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.BuildGhost;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/build-ghost-live-support")]
public sealed class BuildGhostLiveSupportController(
    HubIdentityClient identity,
    AccountService accounts,
    InstallLinkingService installLinking,
    CampaignSpineService campaignSpine,
    HubPageChromeService chrome,
    IBuildGhostLiveSupportGateway gateway,
    ILogger<BuildGhostLiveSupportController> logger) : Controller
{
    private const string PagePathTemplate = "/account/alice/{handoffId}/live-support";
    private static readonly Regex IdempotencyKeyPattern = new(
        "^[a-f0-9]{32}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    [HttpGet(PagePathTemplate)]
    [Produces("text/html")]
    public async Task<IActionResult> Page(
        [FromRoute] string handoffId,
        CancellationToken cancellationToken)
    {
        string pagePath = BuildPagePath(handoffId);
        try
        {
            AuthenticatedHubSubject subject = await identity.RequireSubjectAsync(Request, cancellationToken)
                .ConfigureAwait(false);
            BuildLabHandoffProjection? handoff = ResolveHandoff(subject, handoffId);
            if (handoff is null)
            {
                return NotFound();
            }
            BuildGhostSupportExperienceProjection experience =
                await gateway.GetExperienceAsync(cancellationToken).ConfigureAwait(false);
            return Render(subject, handoff, experience, null, Guid.NewGuid().ToString("N"));
        }
        catch (HubRequestAuthException exception) when (
            exception.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(pagePath)}");
        }
        catch (HubRequestAuthException exception)
        {
            logger.LogWarning(exception, "Live-support page could not confirm the signed-in identity.");
            return Problem(statusCode: exception.StatusCode, detail: exception.Message);
        }
    }

    [HttpPost(PagePathTemplate)]
    [RequestSizeLimit(16 * 1024)]
    [Produces("text/html")]
    public async Task<IActionResult> RequestMeeting(
        [FromRoute] string handoffId,
        [FromForm] BuildGhostLiveSupportForm form,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        string pagePath = BuildPagePath(handoffId);
        try
        {
            AuthenticatedHubSubject subject = await identity.RequireSubjectAsync(Request, cancellationToken)
                .ConfigureAwait(false);
            BuildLabHandoffProjection? handoff = ResolveHandoff(subject, handoffId);
            if (handoff is null)
            {
                return NotFound();
            }
            BuildGhostSupportExperienceProjection experience =
                await gateway.GetExperienceAsync(cancellationToken).ConfigureAwait(false);

            string provider = (form.MeetingProvider ?? string.Empty).Trim().ToLowerInvariant();
            List<string> localFailures = [];
            if (provider is not (BuildGhostLiveMeetingProviders.Zoom or BuildGhostLiveMeetingProviders.Teams)
                || !experience.LiveSupport.MeetingProviders.Contains(provider, StringComparer.Ordinal))
            {
                localFailures.Add("The selected meeting provider is not currently verified for live support.");
            }
            if (!experience.LiveSupport.RequestAvailable)
            {
                localFailures.Add("Live support is not currently available. Rook remains available in Chummer.");
            }
            if (!form.RecordingConsentGranted)
            {
                localFailures.Add("Recording disclosure consent is required before a live meeting can be created.");
            }
            if (!form.ExternalProviderProcessingConsentGranted)
            {
                localFailures.Add("External-provider processing consent is required before a live meeting can be created.");
            }
            if (!IdempotencyKeyPattern.IsMatch(form.IdempotencyKey ?? string.Empty))
            {
                localFailures.Add("This live-support request has expired. Reload the page and try again.");
            }

            if (localFailures.Count != 0)
            {
                return Render(
                    subject,
                    handoff,
                    experience,
                    BuildLocalFailure(provider, form, localFailures),
                    Guid.NewGuid().ToString("N"));
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            string ownerScopeHash = Digest(subject.SubjectId);
            string workspaceId = BuildWorkspaceId(handoff);
            string requestId = "live-" + Digest(
                $"{ownerScopeHash}\n{workspaceId}\n{form.IdempotencyKey}").Substring(7, 32);
            BuildGhostLiveSupportRequest request = new(
                ToughTongueBuildGhostContractVersions.LiveSupportRequestV1,
                requestId,
                ownerScopeHash,
                workspaceId,
                handoff.UpdatedAtUtc.UtcTicks,
                BuildSourceDigest(handoff),
                ResolveLocale(),
                provider,
                form.RecordingConsentGranted,
                form.ExternalProviderProcessingConsentGranted,
                BuildGhostLiveSupportDisclosureContract.CurrentVersion,
                BuildGhostLiveSupportDisclosureContract.ComputeDigest(),
                30,
                form.IdempotencyKey!,
                now);
            BuildGhostLiveSupportSessionProjection session =
                await gateway.RequestAsync(request, cancellationToken).ConfigureAwait(false);
            logger.LogInformation(
                "Build Ghost live-support request completed with status {Status} for provider {Provider}.",
                session.Status,
                provider);
            if (ShouldRedirectToDurableStatus(session))
            {
                return Redirect(BuildStatusPath(handoff.HandoffId, session.RequestId));
            }
            return Render(subject, handoff, experience, session, Guid.NewGuid().ToString("N"));
        }
        catch (HubRequestAuthException exception) when (
            exception.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(pagePath)}");
        }
        catch (HubRequestAuthException exception)
        {
            logger.LogWarning(exception, "Live-support request could not confirm the signed-in identity.");
            return Problem(statusCode: exception.StatusCode, detail: exception.Message);
        }
    }

    [HttpGet("/account/alice/{handoffId}/live-support/{requestId}")]
    [Produces("text/html")]
    public async Task<IActionResult> Status(
        [FromRoute] string handoffId,
        [FromRoute] string requestId,
        CancellationToken cancellationToken)
    {
        string pagePath = BuildStatusPath(handoffId, requestId);
        try
        {
            AuthenticatedHubSubject subject = await identity.RequireSubjectAsync(Request, cancellationToken)
                .ConfigureAwait(false);
            BuildLabHandoffProjection? handoff = ResolveHandoff(subject, handoffId);
            if (handoff is null || !Regex.IsMatch(requestId ?? string.Empty, "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"))
            {
                return NotFound();
            }

            BuildGhostLiveSupportSessionProjection? session = await gateway.GetSessionAsync(
                new BuildGhostLiveSupportStatusRequest(
                    ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                    Digest(subject.SubjectId),
                    requestId!,
                    BuildWorkspaceId(handoff),
                    BuildSourceDigest(handoff)),
                cancellationToken).ConfigureAwait(false);
            if (session is null)
            {
                return NotFound();
            }

            BuildGhostSupportExperienceProjection experience =
                await gateway.GetExperienceAsync(cancellationToken).ConfigureAwait(false);
            return Render(subject, handoff, experience, session, Guid.NewGuid().ToString("N"));
        }
        catch (HubRequestAuthException exception) when (
            exception.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(pagePath)}");
        }
        catch (HubRequestAuthException exception)
        {
            logger.LogWarning(exception, "Live-support status could not confirm the signed-in identity.");
            return Problem(statusCode: exception.StatusCode, detail: exception.Message);
        }
    }

    private IActionResult Render(
        AuthenticatedHubSubject subject,
        BuildLabHandoffProjection handoff,
        BuildGhostSupportExperienceProjection experience,
        BuildGhostLiveSupportSessionProjection? session,
        string idempotencyKey)
    {
        Response.Headers.CacheControl = "no-store";
        SiteChromeViewModel pageChrome = chrome.BuildAuthenticatedChrome(
            "Live character support",
            "Choose Zoom or Teams for an explicit, consented live-support escalation.",
            BuildPagePath(handoff.HandoffId),
            subject.DisplayName ?? subject.Email ?? subject.SubjectId,
            subject.Email);
        BuildGhostLiveSupportPageViewModel model = new(
            pageChrome,
            handoff.HandoffId,
            handoff.Title,
            experience.DefaultSupport.PreRenderedVideoReady
                ? "Rook and the approved VidBoard support clip are ready."
                : "Rook is available with deterministic text while the VidBoard clip is unavailable or stale.",
            experience.DefaultSupport.PreRenderedVideoReady
                ? experience.DefaultSupport.PreRenderedVideoHref
                : null,
            experience.LiveSupport.RequestAvailable,
            experience.LiveSupport.MeetingProviders
                .Select(provider => new BuildGhostLiveSupportProviderViewModel(
                    provider,
                    provider == BuildGhostLiveMeetingProviders.Zoom ? "Zoom" : "Microsoft Teams"))
                .ToArray(),
            experience.LiveSupport.RecordingDisclosureRequired,
            idempotencyKey,
            session);
        return View("~/Views/Accounts/BuildGhostLiveSupport.cshtml", model);
    }

    private string ResolveLocale()
    {
        string candidate = Request.GetTypedHeaders().AcceptLanguage
            .OrderByDescending(static value => value.Quality ?? 1)
            .Select(static value => value.Value.Value)
            .FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value))
            ?? "en-US";
        return Regex.IsMatch(candidate, "^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}$", RegexOptions.CultureInvariant)
            ? candidate
            : "en-US";
    }

    private static BuildGhostLiveSupportSessionProjection BuildLocalFailure(
        string provider,
        BuildGhostLiveSupportForm form,
        IReadOnlyList<string> failures)
        => new(
            ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
            "local-validation",
            BuildGhostSupportChannelKinds.LivePhotorealMeeting,
            BuildGhostLiveSupportStatuses.Unavailable,
            provider,
            null,
            null,
            string.Empty,
            "unavailable",
            form.RecordingConsentGranted,
            form.ExternalProviderProcessingConsentGranted,
            BuildGhostLiveSupportDisclosureContract.CurrentVersion,
            BuildGhostLiveSupportDisclosureContract.ComputeDigest(),
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow,
            new BuildGhostDefaultSupportProjection(
                BuildGhostSupportChannelKinds.RookVidBoard,
                ToughTongueBuildGhostPersonaIds.Rook,
                ToughTongueBuildGhostPersonaIds.RookAvatar,
                ToughTongueBuildGhostPersonaIds.RookVidBoardSupport,
                null,
                string.Empty,
                false,
                "text-fallback",
                "Rook can continue in the grounded Chummer help flow.",
                []),
            failures);

    private static string Digest(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";

    private static string BuildWorkspaceId(BuildLabHandoffProjection handoff)
        => $"handoff-{Digest(handoff.HandoffId).AsSpan(7, 24)}";

    private static string BuildSourceDigest(BuildLabHandoffProjection handoff)
        => Digest(BuildCanonicalContext(handoff));

    private BuildLabHandoffProjection? ResolveHandoff(
        AuthenticatedHubSubject subject,
        string handoffId)
    {
        if (string.IsNullOrWhiteSpace(handoffId) || handoffId.Length > 160)
        {
            return null;
        }

        HubUserDto user = accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto linking = installLinking.GetSummary(user.UserId, subject.SubjectId);
        return campaignSpine.GetBuildLabHandoff(user, handoffId, linking);
    }

    private static string BuildCanonicalContext(BuildLabHandoffProjection handoff)
        => string.Join(
            '\n',
            "chummer-build-ghost-live-support-context/v1",
            handoff.HandoffId,
            handoff.DossierId,
            handoff.CampaignId ?? string.Empty,
            handoff.ExplainEntryId,
            handoff.UpdatedAtUtc.ToUniversalTime().ToString("O"),
            handoff.VariantLabel,
            handoff.ProgressionLabel,
            handoff.RuleEnvironmentDiff?.AfterFingerprint ?? string.Empty,
            string.Join('\u001f', handoff.Outputs.Select(static output => output.ProjectionId).OrderBy(static id => id, StringComparer.Ordinal)));

    private static string BuildPagePath(string handoffId)
        => $"/account/alice/{Uri.EscapeDataString(handoffId ?? string.Empty)}/live-support";

    private static string BuildStatusPath(string handoffId, string requestId)
        => $"{BuildPagePath(handoffId)}/{Uri.EscapeDataString(requestId ?? string.Empty)}";

    private static bool ShouldRedirectToDurableStatus(BuildGhostLiveSupportSessionProjection session)
        => Regex.IsMatch(session.RequestId ?? string.Empty, "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
            && session.Status is BuildGhostLiveSupportStatuses.Ready
                or BuildGhostLiveSupportStatuses.Requested
                or BuildGhostLiveSupportStatuses.ProvisioningMeeting
                or BuildGhostLiveSupportStatuses.ProvisioningAvatar
                or BuildGhostLiveSupportStatuses.Active;
}

public sealed class BuildGhostLiveSupportForm
{
    public string? MeetingProvider { get; init; }

    public bool RecordingConsentGranted { get; init; }

    public bool ExternalProviderProcessingConsentGranted { get; init; }

    public string? IdempotencyKey { get; init; }
}
