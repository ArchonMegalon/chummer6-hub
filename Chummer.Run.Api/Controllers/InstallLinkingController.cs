using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Contracts.Characters;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.WebUtilities;
using System.Net;
using System.Text.Json;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/install-linking")]
public sealed class InstallLinkingController : ControllerBase
{
    private const string AppLocalInstallLinkCallbackPath = "/install-link/callback";
    private const string NativeContinuationHref = "/api/v1/install-linking/continuation";
    private const string NativeSupportHref = "/api/v1/install-linking/continuation/support";
    private const string NativeUpdateHref = "/api/v1/install-linking/continuation/update";
    private const string NativeRollbackHref = "/api/v1/install-linking/continuation/rollback";
    private const string NativeRecoveryHref = NativeContinuationHref;
    private const string MissingCurrentInstallerFallbackPosture =
        "Chummer cannot confirm the current installer for this claimed copy yet. Use support recovery with this install identity attached.";
    private static readonly HashSet<string> InstallLinkCallbackReservedQueryKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        "artifactId",
        "code",
        "accessToken",
        "applicationVersion",
        "callbackCode",
        "channelId",
        "claimCode",
        "claimTicketId",
        "grantId",
        "headId",
        "hostLabel",
        "installAccessClass",
        "installationId",
        "installedBuildReceiptId",
        "releaseChannel",
        "receiptId",
        "platform",
        "platformId",
        "arch",
        "publicKey",
        "ticket",
        "ticketId",
        "version",
        "installLinkMode",
        "installLinkTransport"
    };
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;
    private readonly PublicReleaseManifestService _releases;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly InstallLinkedWorkspaceSnapshotService _workspaceSnapshots;
    private readonly FlagshipReadinessArtifactService _flagshipReadiness;
    private readonly ImportRouteParityProofGuardService _importRouteParityProofGuard;
    private readonly LocalReleaseProofArtifactService _localReleaseProof;

    public InstallLinkingController(
        HubIdentityClient identity,
        AccountService accounts,
        InstallLinkingService installLinking,
        PublicReleaseManifestService releases,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        IConfiguration configuration,
        InstallLinkedWorkspaceSnapshotService? workspaceSnapshots = null)
    {
        _identity = identity;
        _accounts = accounts;
        _installLinking = installLinking;
        _releases = releases;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _workspaceSnapshots = workspaceSnapshots ?? new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(configuration));
        _flagshipReadiness = new FlagshipReadinessArtifactService(configuration);
        _importRouteParityProofGuard = new ImportRouteParityProofGuardService(configuration);
        _localReleaseProof = new LocalReleaseProofArtifactService(configuration);
    }

    [HttpGet("me")]
    [ProducesResponseType<InstallLinkingSummaryDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<InstallLinkingSummaryDto>> GetSummary(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_installLinking.GetSummary(user.UserId, subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("redeem")]
    [ProducesResponseType<RedeemInstallClaimResponseDto>(StatusCodes.Status200OK)]
    public ActionResult<RedeemInstallClaimResponseDto> Redeem([FromBody] RedeemInstallClaimRequestDto? request)
    {
        if (request is null)
        {
            return BadRequest("claim payload is required.");
        }

        try
        {
            return Ok(_installLinking.RedeemClaim(request));
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("grants/refresh")]
    [ProducesResponseType<RefreshInstallationGrantResponseDto>(StatusCodes.Status200OK)]
    public ActionResult<RefreshInstallationGrantResponseDto> RefreshGrant([FromBody] RefreshInstallationGrantRequestDto? request)
    {
        if (request is null)
        {
            return BadRequest("grant refresh payload is required.");
        }

        try
        {
            return Ok(_installLinking.RefreshGrant(request));
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("callbacks/exchange")]
    [ProducesResponseType<ExchangeInstallBrowserCallbackResponseDto>(StatusCodes.Status200OK)]
    public ActionResult<ExchangeInstallBrowserCallbackResponseDto> ExchangeBrowserCallback([FromBody] ExchangeInstallBrowserCallbackRequestDto? request)
    {
        if (request is null)
        {
            return BadRequest("browser callback payload is required.");
        }

        try
        {
            return Ok(_installLinking.ExchangeBrowserCallback(request));
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/account/access/install-link")]
    public async Task<IActionResult> BrowserInstallLink(
        [FromQuery] string? installationId,
        [FromQuery] string? headId,
        [FromQuery] string? applicationVersion,
        [FromQuery] string? releaseChannel,
        [FromQuery] string? platform,
        [FromQuery] string? arch,
        [FromQuery] string? installLinkCallbackUri,
        CancellationToken cancellationToken)
    {
        string returnPath = $"{Request.Path}{Request.QueryString}";
        try
        {
            string? normalizedCallbackUri = NormalizeCallbackUri(installLinkCallbackUri);
            if (normalizedCallbackUri is null)
            {
                return Problem(statusCode: StatusCodes.Status400BadRequest, detail: "install-link callback uri is invalid.");
            }

            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            PublicReleaseManifestDto manifest = _releases.LoadManifest();
            PublicReleaseArtifactDto? artifact = ResolveBrowserCallbackArtifact(manifest, headId, platform, arch);
            if (artifact is null)
            {
                return BuildBrowserInstallLinkStatusPage(
                    statusCode: StatusCodes.Status404NotFound,
                    heading: "This install needs a current desktop package",
                    supportLine: "Chummer could not match this copy to a current desktop installer. Open Downloads for the current installer, or contact support with this install identity attached.",
                    primaryLabel: "Open downloads",
                    primaryHref: "/downloads",
                    secondaryLabel: "Open install support",
                    secondaryHref: BuildInstallSupportHref(installationId, applicationVersion, releaseChannel, headId, platform, arch),
                    stateLabel: "Install link not matched",
                    highlights:
                    [
                        $"Install: {NormalizeBrowserInstallLinkLabel(installationId, "unknown")}",
                        $"Requested build: {NormalizeBrowserInstallLinkLabel(applicationVersion, manifest.Version)}",
                        $"Requested target: {NormalizeBrowserInstallLinkLabel(headId, "desktop")} {NormalizeBrowserInstallLinkLabel(platform, "unknown")} {NormalizeBrowserInstallLinkLabel(arch, "unknown")}"
                    ],
                    autoOpenHref: null,
                    appLocalCallback: false);
            }

            IssueInstallBrowserCallbackResponseDto issued = _installLinking.IssueBrowserCallback(
                new IssueInstallBrowserCallbackRequestDto(
                    InstallationId: installationId ?? string.Empty,
                    ArtifactId: artifact.Id,
                    ApplicationVersion: applicationVersion ?? manifest.Version,
                    ChannelId: releaseChannel ?? manifest.Channel,
                    HeadId: headId ?? artifact.Head ?? "desktop",
                    Platform: platform ?? artifact.PlatformId ?? artifact.Platform ?? "unknown",
                    Arch: arch ?? artifact.Arch ?? "unknown",
                    CallbackUri: normalizedCallbackUri,
                    PublicKey: null,
                    HostLabel: null,
                    InstallAccessClass: artifact.InstallAccessClass),
                user.UserId,
                subject.SubjectId);

            string callbackRedirectUri = BuildBrowserInstallCallbackRedirectUri(
                normalizedCallbackUri,
                issued.Callback.CallbackCode,
                installationId ?? string.Empty,
                headId ?? artifact.Head ?? "desktop",
                applicationVersion ?? manifest.Version,
                releaseChannel ?? manifest.Channel,
                platform ?? artifact.PlatformId ?? artifact.Platform ?? "unknown",
                arch ?? artifact.Arch ?? "unknown");
            bool appLocalCallback = IsAppLocalInstallLinkCallbackUri(callbackRedirectUri);
            return BuildBrowserInstallLinkStatusPage(
                statusCode: StatusCodes.Status200OK,
                heading: appLocalCallback ? "Claim this copy" : "Claim this copy in Chummer",
                supportLine: appLocalCallback
                    ? "Your account approved this copy. Keep this tab open while the running app finishes the claim."
                    : "Your account approved this copy. If Chummer does not open automatically, use the button below from this same browser.",
                primaryLabel: "Claim this copy",
                primaryHref: callbackRedirectUri,
                secondaryLabel: "Open devices and access",
                secondaryHref: "/account/access",
                stateLabel: "Copy ready to claim",
                highlights:
                [
                    $"Install: {NormalizeBrowserInstallLinkLabel(installationId, issued.Callback.InstallationId)}",
                    $"Installer: {artifact.Id}",
                    $"Build: {NormalizeBrowserInstallLinkLabel(applicationVersion, manifest.Version)}"
                ],
                autoOpenHref: callbackRedirectUri,
                appLocalCallback: appLocalCallback);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(returnPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InstallLinkingOperationException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    private static ContentResult BuildBrowserInstallLinkStatusPage(
        int statusCode,
        string heading,
        string supportLine,
        string primaryLabel,
        string primaryHref,
        string secondaryLabel,
        string secondaryHref,
        string stateLabel,
        IReadOnlyList<string> highlights,
        string? autoOpenHref,
        bool appLocalCallback)
    {
        string clickAttemptMessage = appLocalCallback
            ? "Tried to claim this copy again. If this tab still does not finish, copy the claim link below and open it in the same browser."
            : "Tried to open Chummer again. If nothing opens, copy the claim link below and paste it into the browser address bar.";
        string copiedMessage = appLocalCallback
            ? "Claim link copied. Open it in this browser if the tab still does not finish."
            : "Claim link copied. Paste it into the browser address bar if Chummer still does not open.";
        string autoAttemptMessage = appLocalCallback
            ? "Tried to claim this copy automatically. If this tab did not finish, use the button again or copy the claim link below."
            : "Tried to open Chummer automatically. If the app did not open, use the button again or copy the claim link below.";
        string tryOpenBody = appLocalCallback
            ? """
                  try {
                    window.location.assign(href);
                  } catch {}
              """
            : """
                  try {
                    const frame = document.createElement("iframe");
                    frame.setAttribute("aria-hidden", "true");
                    frame.tabIndex = -1;
                    frame.style.position = "absolute";
                    frame.style.inlineSize = "1px";
                    frame.style.blockSize = "1px";
                    frame.style.opacity = "0";
                    frame.style.pointerEvents = "none";
                    frame.src = href;
                    document.body.appendChild(frame);
                    window.setTimeout(() => frame.remove(), 1500);
                  } catch {}

                  try {
                    window.location.assign(href);
                  } catch {}
              """;
        string autoOpenScript = string.IsNullOrWhiteSpace(autoOpenHref)
            ? string.Empty
            : $$"""
              <script>
              (() => {
                const href = {{JsonSerializer.Serialize(autoOpenHref)}};
                const primaryAction = document.getElementById("install-link-open");
                const status = document.getElementById("install-link-status");
                const manualPanel = document.getElementById("install-link-manual");
                const manualField = document.getElementById("install-link-manual-field");
                const copyAction = document.getElementById("install-link-copy");

                const markAttempted = (message) => {
                  if (status) {
                    status.textContent = message;
                  }
                  if (manualPanel) {
                    manualPanel.hidden = false;
                  }
                };

                const tryOpen = () => {
              {{tryOpenBody}}
                };

                if (primaryAction) {
                  primaryAction.addEventListener("click", (event) => {
                    event.preventDefault();
                    markAttempted({{JsonSerializer.Serialize(clickAttemptMessage)}});
                    tryOpen();
                  });
                }

                if (copyAction && manualField && navigator.clipboard?.writeText) {
                  copyAction.hidden = false;
                  copyAction.addEventListener("click", async () => {
                    try {
                      await navigator.clipboard.writeText(href);
                      if (status) {
                        status.textContent = {{JsonSerializer.Serialize(copiedMessage)}};
                      }
                    } catch {}
                  });
                }

                window.setTimeout(() => {
                  tryOpen();
                  window.setTimeout(() => {
                    markAttempted({{JsonSerializer.Serialize(autoAttemptMessage)}});
                  }, 900);
                }, 300);
              })();
              </script>
              """;
        string highlightsHtml = string.Join(
            string.Empty,
            highlights.Select(item => $"<li>{WebUtility.HtmlEncode(item)}</li>"));
        string html = $$"""
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">
              <title>{{WebUtility.HtmlEncode(heading)}} · Chummer</title>
              <link rel="stylesheet" href="/css/site.css">
            </head>
            <body class="surface-auth">
              <main class="auth-stage">
                <section class="auth-shell auth-shell--message">
                  <div class="auth-shell__story auth-visual">
                    <p class="auth-visual__eyebrow">{{WebUtility.HtmlEncode(stateLabel)}}</p>
                    <h1 class="hero-brand">CHUMMER</h1>
                    <h2 class="hero-headline">{{WebUtility.HtmlEncode(heading)}}</h2>
                    <p class="auth-visual__copy">{{WebUtility.HtmlEncode(supportLine)}}</p>
                  </div>
                  <div class="auth-panel auth-panel--message">
                    <ul class="auth-benefits auth-benefits--message">{{highlightsHtml}}</ul>
                    <div class="stacked-actions">
                      <a class="button-like button-like--primary" id="install-link-open" href="{{WebUtility.HtmlEncode(primaryHref)}}">{{WebUtility.HtmlEncode(primaryLabel)}}</a>
                      <a class="button-like button-like--secondary" href="{{WebUtility.HtmlEncode(secondaryHref)}}">{{WebUtility.HtmlEncode(secondaryLabel)}}</a>
                    </div>
                    <p id="install-link-status" class="muted-copy">{{WebUtility.HtmlEncode(appLocalCallback
                        ? "This page should claim the running Chummer app. If it does not finish, use the button again or copy the claim link below."
                        : "Chummer should open from this page. If the browser blocks it, use the button again or copy the claim link below.")}}</p>
                    <div id="install-link-manual" class="field" hidden>
                      <label for="install-link-manual-field">Claim link</label>
                      <input id="install-link-manual-field" type="text" readonly value="{{WebUtility.HtmlEncode(primaryHref)}}">
                      <button id="install-link-copy" class="button-like button-like--ghost" type="button" hidden>Copy claim link</button>
                    </div>
                  </div>
                </section>
              </main>
              {{autoOpenScript}}
            </body>
            </html>
            """;
        return new ContentResult
        {
            StatusCode = statusCode,
            ContentType = "text/html; charset=utf-8",
            Content = html
        };
    }

    private static string BuildInstallSupportHref(
        string? installationId,
        string? applicationVersion,
        string? releaseChannel,
        string? headId,
        string? platform,
        string? arch)
    {
        Dictionary<string, string?> query = new(StringComparer.Ordinal)
        {
            ["kind"] = "install_help",
            ["installationId"] = installationId,
            ["applicationVersion"] = applicationVersion,
            ["releaseChannel"] = releaseChannel,
            ["headId"] = headId,
            ["platform"] = platform,
            ["arch"] = arch
        };
        return QueryHelpers.AddQueryString("/contact", query);
    }

    private static string NormalizeBrowserInstallLinkLabel(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();

    [HttpPost("continuation")]
    [ProducesResponseType<DesktopInstallNativeContinuationResponse>(StatusCodes.Status200OK)]
    public ActionResult<DesktopInstallNativeContinuationResponse> ContinueClaimedInstall([FromBody] DesktopInstallNativeContinuationRequest? request)
    {
        if (request is null)
        {
            return BadRequest("continuation payload is required.");
        }

        ClaimedInstallationDto? installation = _installLinking.ResolveInstallationForGrant(request.InstallationId, request.AccessToken);
        if (installation is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "installation grant is unknown or expired.");
        }

        InstallLinkingSummaryDto installSummary = _installLinking.GetSummary(installation.UserId, installation.SubjectId);
        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        PublicReleaseArtifactDto? releaseArtifact = ResolveContinuationArtifact(manifest, installation);
        DownloadReceiptDto? receipt = ResolveLatestReceipt(installSummary, installation, releaseArtifact);
        DesktopInstallContinuationReceipt? continuation = releaseArtifact is null
            ? null
            : DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false);
        bool updateAvailable = IsUpdateAvailable(installation, manifest, releaseArtifact);
        IReadOnlyList<DesktopInstallSupportContinuationCase> supportCases = ResolveSupportContinuationCases(
            installation,
            installSummary,
            receipt,
            manifest,
            releaseArtifact,
            continuation,
            updateAvailable);
        DesktopInstallSupportContinuationCase? leadSupportCase = supportCases.FirstOrDefault(static item => item.ReporterActionNeeded)
            ?? supportCases.FirstOrDefault();
        NativeRouteProofStatus nativeRouteProof = BuildNativeRouteProofStatus(
            NativeContinuationHref,
            "No current release status record is attached to the native claimed-install continuation route.");
        string supportHref = DesktopInstallRail.BuildAccountSupportHref(
            installationId: installation.InstallationId,
            applicationVersion: installation.Version,
            releaseChannel: installation.Channel,
            headId: installation.HeadId,
            platform: installation.Platform,
            arch: installation.Arch,
            installedBuildReceiptId: receipt?.ReceiptId);

        return Ok(new DesktopInstallNativeContinuationResponse(
            InstallationId: installation.InstallationId,
            ArtifactId: installation.ArtifactId,
            ApplicationVersion: installation.Version,
            ReleaseChannel: installation.Channel,
            HeadId: NormalizeResponseValue(installation.HeadId),
            Platform: NormalizeResponseValue(installation.Platform),
            Arch: NormalizeResponseValue(installation.Arch),
            InstallStatus: installation.Status,
            InstalledBuildReceiptId: receipt?.ReceiptId,
            CurrentReleaseVersion: manifest.Version,
            CurrentReleaseChannel: manifest.Channel,
            CurrentArtifactId: releaseArtifact?.Id,
            RouteState: nativeRouteProof.State,
            RouteReceipt: nativeRouteProof.RouteReceipt,
            BoundedFailureReason: nativeRouteProof.BoundedFailureReason,
            FallbackPosture: continuation?.FallbackPosture ?? MissingCurrentInstallerFallbackPosture,
            UpdateAvailable: updateAvailable,
            NextSafeAction: BuildNativeNextSafeAction(updateAvailable, leadSupportCase, continuation),
            NativePrimaryActionHref: BuildNativeContinuationPrimaryActionHref(updateAvailable, leadSupportCase),
            UpdateAction: updateAvailable
                ? $"Update this linked install from {installation.Channel} {installation.Version} to {manifest.Channel} {manifest.Version}, then refresh the install grant from the app."
                : continuation?.UpdateAction ?? "Refresh the install grant from the app before starting a new install or support path.",
            RollbackAction: continuation?.RollbackAction
                ?? "If update or setup fails, keep the previous installed copy and return to this continuation endpoint before opening a new support path.",
            SupportHref: supportHref,
            NativeUpdateHref: "/api/v1/install-linking/continuation/update",
            NativeSupportHref: "/api/v1/install-linking/continuation/support",
            NativeRollbackHref: "/api/v1/install-linking/continuation/rollback",
            NativeRecoveryHref: NativeRecoveryHref,
            RecoveryAction: BuildNativeRecoveryAction(installation, continuation),
            SupportContinuation: leadSupportCase?.NextSafeAction
                ?? continuation?.SupportContinuation
                ?? "Support follow-through stays on this claimed install with the current build, channel, and device context attached.",
            SupportCases: supportCases));
    }

    [HttpPost("continuation/workspaces/list")]
    [ProducesResponseType<InstallLinkedWorkspaceSnapshotListResponse>(StatusCodes.Status200OK)]
    public ActionResult<InstallLinkedWorkspaceSnapshotListResponse> ListClaimedInstallWorkspaces([FromBody] DesktopInstallNativeContinuationRequest? request)
    {
        if (request is null)
        {
            return BadRequest("workspace snapshot list payload is required.");
        }

        ClaimedInstallationDto? installation = _installLinking.ResolveInstallationForGrant(request.InstallationId, request.AccessToken);
        if (installation is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "installation grant is unknown or expired.");
        }

        InstallLinkedWorkspaceSnapshotDto[] snapshots = _workspaceSnapshots.ListForInstallation(installation)
            .Select(static snapshot => ToSnapshotDto(snapshot))
            .ToArray();
        return Ok(new InstallLinkedWorkspaceSnapshotListResponse(snapshots));
    }

    [HttpPost("continuation/workspaces/upsert")]
    [ProducesResponseType<InstallLinkedWorkspaceSnapshotUpsertResponse>(StatusCodes.Status200OK)]
    public ActionResult<InstallLinkedWorkspaceSnapshotUpsertResponse> UpsertClaimedInstallWorkspace([FromBody] InstallLinkedWorkspaceSnapshotUpsertRequest? request)
    {
        if (request is null)
        {
            return BadRequest("workspace snapshot upsert payload is required.");
        }

        ClaimedInstallationDto? installation = _installLinking.ResolveInstallationForGrant(request.InstallationId, request.AccessToken);
        if (installation is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "installation grant is unknown or expired.");
        }

        try
        {
            InstallLinkedWorkspaceSnapshotRecord stored = _workspaceSnapshots.UpsertForInstallation(
                installation,
                new InstallLinkedWorkspaceSnapshotRecord(
                    OwnerKey: string.Empty,
                    WorkspaceId: request.WorkspaceId,
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

    [HttpPost("continuation/support")]
    [ProducesResponseType<DesktopInstallNativeSupportResponse>(StatusCodes.Status202Accepted)]
    public ActionResult<DesktopInstallNativeSupportResponse> SubmitClaimedInstallSupport([FromBody] DesktopInstallNativeSupportRequest? request)
    {
        if (request is null)
        {
            return BadRequest("native support payload is required.");
        }

        ClaimedInstallationDto? installation = _installLinking.ResolveInstallationForGrant(request.InstallationId, request.AccessToken);
        if (installation is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "installation grant is unknown or expired.");
        }

        InstallLinkingSummaryDto installSummary = _installLinking.GetSummary(installation.UserId, installation.SubjectId);
        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        PublicReleaseArtifactDto? releaseArtifact = ResolveContinuationArtifact(manifest, installation);
        DesktopInstallContinuationReceipt? continuation = releaseArtifact is null
            ? null
            : DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false);
        DownloadReceiptDto? receipt = ResolveLatestReceipt(installSummary, installation, releaseArtifact);
        bool updateAvailable = IsUpdateAvailable(installation, manifest, releaseArtifact);
        NativeRouteProofStatus nativeRouteProof = BuildNativeRouteProofStatus(
            NativeSupportHref,
            "No current release status record is attached to the native claimed-install support route.");

        SupportCaseProjection created;
        try
        {
            created = _supportCases.Submit(
                installation.UserId,
                installation.SubjectId,
                BuildNativeInstallSupportRequest(request, installation, receipt, manifest, releaseArtifact, continuation, updateAvailable));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }

        SupportCasePresentationViewModel presented = _supportPresentation.Build(created, installSummary);
        return Accepted(new DesktopInstallNativeSupportResponse(
            CaseId: created.CaseId,
            InstallationId: installation.InstallationId,
            ApplicationVersion: installation.Version,
            ReleaseChannel: installation.Channel,
            HeadId: NormalizeResponseValue(installation.HeadId),
            Platform: NormalizeResponseValue(installation.Platform),
            Arch: NormalizeResponseValue(installation.Arch),
            StatusLabel: presented.StatusLabel,
            StageLabel: presented.StageLabel,
            NextSafeAction: BuildNativeSupportNextSafeAction(presented, updateAvailable),
            PrimaryActionHref: BuildNativeSupportCaseActionHref(presented),
            AccountSupportHref: $"/account/support/{Uri.EscapeDataString(created.CaseId)}",
            NativeSupportHref: "/api/v1/install-linking/continuation/support",
            NativeContinuationHref: "/api/v1/install-linking/continuation",
            NativeUpdateHref: "/api/v1/install-linking/continuation/update",
            NativeRollbackHref: "/api/v1/install-linking/continuation/rollback",
            NativeRecoveryHref: NativeRecoveryHref,
            InstalledBuildReceiptId: receipt?.ReceiptId,
            CurrentReleaseVersion: manifest.Version,
            CurrentReleaseChannel: manifest.Channel,
            CurrentArtifactId: releaseArtifact?.Id,
            RouteState: nativeRouteProof.State,
            RouteReceipt: nativeRouteProof.RouteReceipt,
            BoundedFailureReason: nativeRouteProof.BoundedFailureReason,
            FallbackPosture: continuation?.FallbackPosture ?? MissingCurrentInstallerFallbackPosture,
            UpdateAvailable: updateAvailable,
            UpdateAction: updateAvailable
                ? $"Update this linked install from {installation.Channel} {installation.Version} to {manifest.Channel} {manifest.Version}, then refresh the install grant from the app."
                : continuation?.UpdateAction ?? "Refresh the install grant from the app before starting a new install or support path.",
            RollbackAction: "If support, update, or setup fails, keep the previous installed copy and return to Devices and access for this linked copy.",
            RecoveryAction: BuildNativeRecoveryAction(installation, continuation)));
    }

    [HttpPost("continuation/update")]
    [ProducesResponseType<DesktopInstallNativeUpdateResponse>(StatusCodes.Status200OK)]
    public ActionResult<DesktopInstallNativeUpdateResponse> PlanClaimedInstallUpdate([FromBody] DesktopInstallNativeContinuationRequest? request)
    {
        if (request is null)
        {
            return BadRequest("update payload is required.");
        }

        ClaimedInstallationDto? installation = _installLinking.ResolveInstallationForGrant(request.InstallationId, request.AccessToken);
        if (installation is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "installation grant is unknown or expired.");
        }

        InstallLinkingSummaryDto installSummary = _installLinking.GetSummary(installation.UserId, installation.SubjectId);
        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        PublicReleaseArtifactDto? releaseArtifact = ResolveContinuationArtifact(manifest, installation);
        DesktopInstallContinuationReceipt? continuation = releaseArtifact is null
            ? null
            : DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false);
        DownloadReceiptDto? receipt = ResolveLatestReceipt(installSummary, installation, releaseArtifact);
        bool updateAvailable = IsUpdateAvailable(installation, manifest, releaseArtifact);
        NativeRouteProofStatus nativeRouteProof = BuildNativeRouteProofStatus(
            NativeUpdateHref,
            "No current release status record is attached to the native claimed-install update planner route.");

        string supportHref = DesktopInstallRail.BuildAccountSupportHref(
            installationId: installation.InstallationId,
            applicationVersion: installation.Version,
            releaseChannel: installation.Channel,
            headId: installation.HeadId,
            platform: installation.Platform,
            arch: installation.Arch,
            installedBuildReceiptId: receipt?.ReceiptId);

        return Ok(new DesktopInstallNativeUpdateResponse(
            InstallationId: installation.InstallationId,
            ArtifactId: installation.ArtifactId,
            ApplicationVersion: installation.Version,
            ReleaseChannel: installation.Channel,
            HeadId: NormalizeResponseValue(installation.HeadId),
            Platform: NormalizeResponseValue(installation.Platform),
            Arch: NormalizeResponseValue(installation.Arch),
            InstalledBuildReceiptId: receipt?.ReceiptId,
            CurrentReleaseVersion: manifest.Version,
            CurrentReleaseChannel: manifest.Channel,
            CurrentArtifactId: releaseArtifact?.Id,
            RouteState: nativeRouteProof.State,
            RouteReceipt: nativeRouteProof.RouteReceipt,
            BoundedFailureReason: nativeRouteProof.BoundedFailureReason,
            UpdateAvailable: updateAvailable,
            UpdatePlan: BuildNativeUpdatePlan(installation, manifest, releaseArtifact, receipt, updateAvailable),
            UpdateAction: updateAvailable
                ? $"Update this linked copy from {installation.Channel} {installation.Version} to {manifest.Channel} {manifest.Version}, then refresh the update view from the app."
                : continuation?.UpdateAction ?? "Refresh the update view from the app before starting another install or support path.",
            NativePrimaryActionHref: NativeUpdateHref,
            SupportHref: supportHref,
            NativeContinuationHref: "/api/v1/install-linking/continuation",
            NativeSupportHref: "/api/v1/install-linking/continuation/support",
            NativeRollbackHref: "/api/v1/install-linking/continuation/rollback",
            NativeRecoveryHref: NativeRecoveryHref,
            FallbackPosture: continuation?.FallbackPosture ?? MissingCurrentInstallerFallbackPosture,
            RecoveryAction: BuildNativeRecoveryAction(installation, continuation)));
    }

    [HttpPost("continuation/rollback")]
    [ProducesResponseType<DesktopInstallNativeRollbackResponse>(StatusCodes.Status200OK)]
    public ActionResult<DesktopInstallNativeRollbackResponse> PlanClaimedInstallRollback([FromBody] DesktopInstallNativeContinuationRequest? request)
    {
        if (request is null)
        {
            return BadRequest("rollback payload is required.");
        }

        ClaimedInstallationDto? installation = _installLinking.ResolveInstallationForGrant(request.InstallationId, request.AccessToken);
        if (installation is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "installation grant is unknown or expired.");
        }

        InstallLinkingSummaryDto installSummary = _installLinking.GetSummary(installation.UserId, installation.SubjectId);
        PublicReleaseManifestDto manifest = _releases.LoadManifest();
        PublicReleaseArtifactDto? releaseArtifact = ResolveContinuationArtifact(manifest, installation);
        DesktopInstallContinuationReceipt? continuation = releaseArtifact is null
            ? null
            : DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false);
        DownloadReceiptDto? receipt = ResolveLatestReceipt(installSummary, installation, releaseArtifact);
        bool updateAvailable = IsUpdateAvailable(installation, manifest, releaseArtifact);
        NativeRouteProofStatus nativeRouteProof = BuildNativeRouteProofStatus(
            NativeRollbackHref,
            "No current release status record is attached to the native claimed-install rollback planner route.");

        string supportHref = DesktopInstallRail.BuildAccountSupportHref(
            installationId: installation.InstallationId,
            applicationVersion: installation.Version,
            releaseChannel: installation.Channel,
            headId: installation.HeadId,
            platform: installation.Platform,
            arch: installation.Arch,
            installedBuildReceiptId: receipt?.ReceiptId);

        return Ok(new DesktopInstallNativeRollbackResponse(
            InstallationId: installation.InstallationId,
            ArtifactId: installation.ArtifactId,
            ApplicationVersion: installation.Version,
            ReleaseChannel: installation.Channel,
            HeadId: NormalizeResponseValue(installation.HeadId),
            Platform: NormalizeResponseValue(installation.Platform),
            Arch: NormalizeResponseValue(installation.Arch),
            InstalledBuildReceiptId: receipt?.ReceiptId,
            CurrentReleaseVersion: manifest.Version,
            CurrentReleaseChannel: manifest.Channel,
            CurrentArtifactId: releaseArtifact?.Id,
            RouteState: nativeRouteProof.State,
            RouteReceipt: nativeRouteProof.RouteReceipt,
            BoundedFailureReason: nativeRouteProof.BoundedFailureReason,
            UpdateAvailable: updateAvailable,
            RollbackPlan: BuildNativeRollbackPlan(installation, receipt),
            RollbackAction: continuation?.RollbackAction
                ?? "Keep the previous installed copy and return to Devices and access for this linked copy before starting another recovery path.",
            NativePrimaryActionHref: NativeRollbackHref,
            SupportHref: supportHref,
            NativeContinuationHref: "/api/v1/install-linking/continuation",
            NativeUpdateHref: "/api/v1/install-linking/continuation/update",
            NativeSupportHref: "/api/v1/install-linking/continuation/support",
            NativeRecoveryHref: NativeRecoveryHref,
            FallbackPosture: continuation?.FallbackPosture ?? MissingCurrentInstallerFallbackPosture,
            RecoveryAction: BuildNativeRecoveryAction(installation, continuation)));
    }

    private static SupportCaseSubmitRequest BuildNativeInstallSupportRequest(
        DesktopInstallNativeSupportRequest request,
        ClaimedInstallationDto installation,
        DownloadReceiptDto? installedBuildReceipt,
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? releaseArtifact,
        DesktopInstallContinuationReceipt? continuation,
        bool updateAvailable)
    {
        string title = string.IsNullOrWhiteSpace(request.Title)
            ? "Install help for claimed desktop install"
            : request.Title.Trim();
        string summary = string.IsNullOrWhiteSpace(request.Summary)
            ? "The desktop app needs help with this linked copy."
            : request.Summary.Trim();
        string detail = string.IsNullOrWhiteSpace(request.Detail)
            ? "The desktop app filed this from a linked copy. Keep install, update, rollback, and follow-up on this same device."
            : request.Detail.Trim();
        string? installedBuildReceiptId = string.IsNullOrWhiteSpace(installedBuildReceipt?.ReceiptId)
            ? null
            : installedBuildReceipt.ReceiptId.Trim();
        detail = AppendInstalledBuildReceiptDetail(detail, installedBuildReceiptId);
        detail = AppendAuthoritativeNativeInstallTruthDetail(detail, installation);
        detail = AppendNativeReleaseRecoveryTruthDetail(detail, manifest, releaseArtifact, continuation, updateAvailable);
        detail = AppendNativeRequestedActionDetail(detail, request.RequestedActionHref);
        detail = AppendNativeRouteReceiptDetail(detail);
        detail = AppendNativeContinuationContextDetail(detail);

        return new SupportCaseSubmitRequest(
            Kind: SupportCaseKinds.InstallHelp,
            Title: title,
            Summary: summary,
            Detail: detail,
            ReporterEmail: string.IsNullOrWhiteSpace(request.ReporterEmail) ? null : request.ReporterEmail.Trim(),
            InstallationId: installation.InstallationId,
            ApplicationVersion: installation.Version,
            ReleaseChannel: installation.Channel,
            HeadId: installation.HeadId,
            Platform: installation.Platform,
            Arch: installation.Arch,
            Source: SupportCaseSourceKinds.DesktopFeedback);
    }

    private static string AppendInstalledBuildReceiptDetail(string detail, string? installedBuildReceiptId)
    {
        if (string.IsNullOrWhiteSpace(installedBuildReceiptId))
        {
            return detail;
        }

        string requiredLine = $"Installed build record: {installedBuildReceiptId}";
        return detail.Contains(requiredLine, StringComparison.OrdinalIgnoreCase)
            ? detail
            : $"{detail}\n\n{requiredLine}";
    }

    private static string AppendAuthoritativeNativeInstallTruthDetail(string detail, ClaimedInstallationDto installation)
    {
        string requiredLine =
            $"Authoritative claimed install: {installation.InstallationId}; build {installation.Channel} {installation.Version}; device {NormalizeResponseValue(installation.HeadId)} {NormalizeResponseValue(installation.Platform)} {NormalizeResponseValue(installation.Arch)}.";
        return detail.Contains(requiredLine, StringComparison.OrdinalIgnoreCase)
            ? detail
            : $"{detail}\n\n{requiredLine}";
    }

    private static string AppendNativeContinuationContextDetail(string detail)
    {
        const string requiredLine = "Linked copy support: browser callback, claim code, or public form identifiers in the desktop payload are advisory only.";
        return detail.Contains(requiredLine, StringComparison.OrdinalIgnoreCase)
            ? detail
            : $"{detail}\n\n{requiredLine}";
    }

    private static string AppendNativeRequestedActionDetail(string detail, string? requestedActionHref)
    {
        if (string.IsNullOrWhiteSpace(requestedActionHref))
        {
            return detail;
        }

        string trimmed = requestedActionHref.Trim();
        string safeHref = RedactNativeRequestedActionHref(trimmed);
        string posture = NormalizeNativeInstallRailHref(trimmed) is not null
            ? "linked-copy action"
            : "advisory browser or external action";
        string requiredLine = $"Desktop requested action ({posture}): {safeHref}";
        return detail.Contains(requiredLine, StringComparison.OrdinalIgnoreCase)
            ? detail
            : $"{detail}\n\n{requiredLine}";
    }

    private static string RedactNativeRequestedActionHref(string href)
    {
        string trimmed = href.Trim();
        string sanitized = trimmed;
        bool redacted = false;

        int fragmentIndex = FindNativeRequestedActionFragmentIndex(sanitized);
        string beforeFragment = fragmentIndex >= 0 ? sanitized[..fragmentIndex] : sanitized;
        string fragment = fragmentIndex >= 0 ? sanitized[fragmentIndex..] : string.Empty;
        int queryIndex = beforeFragment.IndexOf('?');
        if (queryIndex >= 0)
        {
            string query = beforeFragment[queryIndex..];
            string sanitizedQuery = SanitizeInstallLinkSecretQueryComponent(query, "?", out bool queryRedacted);
            if (queryRedacted)
            {
                beforeFragment = $"{beforeFragment[..queryIndex]}{sanitizedQuery}";
                redacted = true;
            }
        }

        if (!string.IsNullOrEmpty(fragment))
        {
            string sanitizedFragment = SanitizeInstallLinkSecretQueryComponent(fragment, "#", out bool fragmentRedacted);
            if (fragmentRedacted)
            {
                fragment = sanitizedFragment;
                redacted = true;
            }
        }

        sanitized = $"{beforeFragment}{fragment}";
        string replacement = Uri.EscapeDataString("[redacted-install-link-secret]");

        foreach (string key in InstallLinkCallbackReservedQueryKeys)
        {
            int searchIndex = 0;
            string needle = $"{key}=";
            while (searchIndex < sanitized.Length)
            {
                int keyIndex = sanitized.IndexOf(needle, searchIndex, StringComparison.OrdinalIgnoreCase);
                if (keyIndex < 0)
                {
                    break;
                }

                if (keyIndex > 0)
                {
                    char separator = sanitized[keyIndex - 1];
                    if (separator != '?' && separator != '&' && separator != '#' && separator != ';')
                    {
                        searchIndex = keyIndex + needle.Length;
                        continue;
                    }
                }

                int valueStart = keyIndex + needle.Length;
                int valueEnd = valueStart;
                while (valueEnd < sanitized.Length
                    && sanitized[valueEnd] != '&'
                    && sanitized[valueEnd] != '#'
                    && sanitized[valueEnd] != ';')
                {
                    valueEnd++;
                }

                sanitized = $"{sanitized[..valueStart]}{replacement}{sanitized[valueEnd..]}";
                redacted = true;
                searchIndex = valueStart + replacement.Length;
            }
        }

        return redacted ? sanitized : href;
    }

    private static int FindNativeRequestedActionFragmentIndex(string href)
    {
        for (int index = 0; index < href.Length; index++)
        {
            if (href[index] != '#')
            {
                continue;
            }

            if (IsHtmlNumericEntityHash(href, index))
            {
                continue;
            }

            return index;
        }

        return -1;
    }

    private static bool IsHtmlNumericEntityHash(string href, int hashIndex)
    {
        if (hashIndex <= 0 || href[hashIndex - 1] != '&')
        {
            return false;
        }

        int bodyStart = hashIndex + 1;
        if (bodyStart >= href.Length)
        {
            return false;
        }

        if (href[bodyStart] is 'x' or 'X')
        {
            bodyStart++;
            if (bodyStart >= href.Length)
            {
                return false;
            }

            int hexIndex = bodyStart;
            while (hexIndex < href.Length && Uri.IsHexDigit(href[hexIndex]))
            {
                hexIndex++;
            }

            return hexIndex > bodyStart && hexIndex < href.Length && href[hexIndex] == ';';
        }

        int digitIndex = bodyStart;
        while (digitIndex < href.Length && char.IsDigit(href[digitIndex]))
        {
            digitIndex++;
        }

        return digitIndex > bodyStart && digitIndex < href.Length && href[digitIndex] == ';';
    }

    private static string SanitizeInstallLinkSecretQueryComponent(string component, string prefix, out bool redacted)
    {
        redacted = false;
        if (string.IsNullOrEmpty(component)
            || !component.StartsWith(prefix, StringComparison.Ordinal)
            || component.Length == prefix.Length
            || !ContainsInstallLinkSecretEqualsCandidate(component))
        {
            return component;
        }

        string body = component[prefix.Length..];
        var sanitizedParts = new List<string>();
        var separators = new List<string>();
        int partStart = 0;

        while (partStart <= body.Length)
        {
            (int separatorIndex, int separatorLength) = FindNextInstallLinkSecretSeparator(body, partStart);
            string part = separatorIndex >= 0
                ? body[partStart..separatorIndex]
                : body[partStart..];
            sanitizedParts.Add(SanitizeInstallLinkSecretQueryPart(part, out bool partRedacted));
            redacted |= partRedacted;

            if (separatorIndex < 0)
            {
                break;
            }

            separators.Add(body.Substring(separatorIndex, separatorLength));
            partStart = separatorIndex + separatorLength;
        }

        if (!redacted)
        {
            return component;
        }

        string sanitizedBody = sanitizedParts[0];
        for (int index = 0; index < separators.Count; index++)
        {
            sanitizedBody = $"{sanitizedBody}{separators[index]}{sanitizedParts[index + 1]}";
        }

        return $"{prefix}{sanitizedBody}";
    }

    private static bool ContainsInstallLinkSecretEqualsCandidate(string component)
        => component.Contains('=', StringComparison.Ordinal)
           || component.Contains("%3D", StringComparison.OrdinalIgnoreCase)
           || component.Contains("%253D", StringComparison.OrdinalIgnoreCase)
           || component.Contains("&equals;", StringComparison.OrdinalIgnoreCase)
           || component.Contains("&#61;", StringComparison.OrdinalIgnoreCase)
           || component.Contains("&#x3d;", StringComparison.OrdinalIgnoreCase);

    private static (int Index, int Length) FindNextInstallLinkSecretSeparator(string body, int startIndex)
    {
        for (int index = startIndex; index < body.Length; index++)
        {
            char current = body[index];
            (bool hasHtmlEntitySeparator, int htmlEntitySeparatorLength) = MatchHtmlEntityInstallLinkSecretSeparator(body, index);
            if (hasHtmlEntitySeparator)
            {
                return (index, htmlEntitySeparatorLength);
            }

            (bool hasHtmlEntityEquals, int htmlEntityEqualsLength) = MatchHtmlEntityInstallLinkSecretEquals(body, index);
            if (hasHtmlEntityEquals)
            {
                index += htmlEntityEqualsLength - 1;
                continue;
            }

            if (current is '&' or ';')
            {
                return (index, 1);
            }

            if (index + 2 < body.Length
                && current == '%'
                && (body.AsSpan(index, 3).Equals("%26", StringComparison.OrdinalIgnoreCase)
                    || body.AsSpan(index, 3).Equals("%23", StringComparison.OrdinalIgnoreCase)
                    || body.AsSpan(index, 3).Equals("%3B", StringComparison.OrdinalIgnoreCase)))
            {
                return (index, 3);
            }

            if (index + 4 < body.Length
                && (body.AsSpan(index, 5).Equals("%2526", StringComparison.OrdinalIgnoreCase)
                    || body.AsSpan(index, 5).Equals("%2523", StringComparison.OrdinalIgnoreCase)
                    || body.AsSpan(index, 5).Equals("%253B", StringComparison.OrdinalIgnoreCase)))
            {
                return (index, 5);
            }
        }

        return (-1, 0);
    }

    private static (bool Matched, int Length) MatchHtmlEntityInstallLinkSecretSeparator(string body, int index)
    {
        string remaining = body[index..];
        if (remaining.StartsWith("&amp;", StringComparison.OrdinalIgnoreCase))
        {
            return (true, 5);
        }

        if (remaining.StartsWith("&#38;", StringComparison.OrdinalIgnoreCase)
            || remaining.StartsWith("&#35;", StringComparison.OrdinalIgnoreCase)
            || remaining.StartsWith("&#59;", StringComparison.OrdinalIgnoreCase)
            || remaining.StartsWith("&num;", StringComparison.OrdinalIgnoreCase))
        {
            return (true, 5);
        }

        if (remaining.StartsWith("&#x26;", StringComparison.OrdinalIgnoreCase)
            || remaining.StartsWith("&#x23;", StringComparison.OrdinalIgnoreCase)
            || remaining.StartsWith("&#x3b;", StringComparison.OrdinalIgnoreCase))
        {
            return (true, 6);
        }

        if (remaining.StartsWith("&semi;", StringComparison.OrdinalIgnoreCase))
        {
            return (true, 6);
        }

        return (false, 0);
    }

    private static string SanitizeInstallLinkSecretQueryPart(string part, out bool redacted)
    {
        redacted = false;
        if (string.IsNullOrEmpty(part))
        {
            return part;
        }

        (int equalsIndex, int equalsLength) = FindInstallLinkSecretEquals(part);
        string rawKey = equalsIndex >= 0
            ? part[..equalsIndex]
            : part;
        string decodedKey = DecodeInstallLinkSecretKey(rawKey);

        if (!InstallLinkCallbackReservedQueryKeys.Contains(decodedKey))
        {
            return part;
        }

        string encodedValue = Uri.EscapeDataString("[redacted-install-link-secret]");
        redacted = true;
        string separator = equalsIndex >= 0
            ? part.Substring(equalsIndex, equalsLength)
            : "=";
        return $"{rawKey}{separator}{encodedValue}";
    }

    private static (int Index, int Length) FindInstallLinkSecretEquals(string part)
    {
        int literalIndex = part.IndexOf('=');
        if (literalIndex >= 0)
        {
            return (literalIndex, 1);
        }

        for (int index = 0; index < part.Length; index++)
        {
            (bool hasHtmlEntityEquals, int htmlEntityEqualsLength) = MatchHtmlEntityInstallLinkSecretEquals(part, index);
            if (hasHtmlEntityEquals)
            {
                return (index, htmlEntityEqualsLength);
            }

            if (index + 2 < part.Length
                && part.AsSpan(index, 3).Equals("%3D", StringComparison.OrdinalIgnoreCase))
            {
                return (index, 3);
            }

            if (index + 4 < part.Length
                && part.AsSpan(index, 5).Equals("%253D", StringComparison.OrdinalIgnoreCase))
            {
                return (index, 5);
            }
        }

        return (-1, 0);
    }

    private static (bool Matched, int Length) MatchHtmlEntityInstallLinkSecretEquals(string body, int index)
    {
        string remaining = body[index..];
        if (remaining.StartsWith("&equals;", StringComparison.OrdinalIgnoreCase))
        {
            return (true, 8);
        }

        if (remaining.StartsWith("&#61;", StringComparison.OrdinalIgnoreCase))
        {
            return (true, 5);
        }

        if (remaining.StartsWith("&#x3d;", StringComparison.OrdinalIgnoreCase))
        {
            return (true, 6);
        }

        return (false, 0);
    }

    private static string DecodeInstallLinkSecretKey(string rawKey)
    {
        string decodedKey = rawKey;
        for (int index = 0; index < 4; index++)
        {
            string next;
            try
            {
                next = Uri.UnescapeDataString(decodedKey.Replace("+", "%20", StringComparison.Ordinal));
            }
            catch (UriFormatException)
            {
                return decodedKey;
            }

            if (string.Equals(next, decodedKey, StringComparison.Ordinal))
            {
                break;
            }

            decodedKey = next;
        }

        return decodedKey;
    }

    private static string AppendNativeRouteReceiptDetail(string detail)
    {
        string requiredLine =
            $"Linked copy support paths: support {NativeSupportHref}; update {NativeUpdateHref}; rollback {NativeRollbackHref}; recovery {NativeRecoveryHref}; account, downloads, and public support links are fallback only.";
        return detail.Contains(requiredLine, StringComparison.OrdinalIgnoreCase)
            ? detail
            : $"{detail}\n\n{requiredLine}";
    }

    private static string AppendNativeReleaseRecoveryTruthDetail(
        string detail,
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? releaseArtifact,
        DesktopInstallContinuationReceipt? continuation,
        bool updateAvailable)
    {
        string fallbackPosture = continuation?.FallbackPosture
            ?? MissingCurrentInstallerFallbackPosture;
        string requiredLine =
            $"Linked copy recovery status: current {manifest.Channel} {manifest.Version}; installer {NormalizeResponseValue(releaseArtifact?.Id)}; update available {updateAvailable.ToString().ToLowerInvariant()}; rollback stays on the previous installed copy; fallback {fallbackPosture}";
        return detail.Contains(requiredLine, StringComparison.OrdinalIgnoreCase)
            ? detail
            : $"{detail}\n\n{requiredLine}";
    }

    private static PublicReleaseArtifactDto? ResolveContinuationArtifact(PublicReleaseManifestDto manifest, ClaimedInstallationDto installation)
    {
        PublicReleaseArtifactDto? byArtifactId = manifest.Downloads.FirstOrDefault(item =>
            string.Equals(item.Id, installation.ArtifactId, StringComparison.OrdinalIgnoreCase));
        if (byArtifactId is not null)
        {
            return byArtifactId;
        }

        return manifest.Downloads
            .Select(item => new
            {
                Artifact = item,
                Score = ScoreArtifactMatch(item, installation)
            })
            .OrderByDescending(static item => item.Score)
            .ThenBy(static item => item.Artifact.Id, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(static item => item.Score > 0)
            ?.Artifact;
    }

    private static int ScoreArtifactMatch(PublicReleaseArtifactDto artifact, ClaimedInstallationDto installation)
    {
        int score = 0;
        if (!TryScoreArtifactField(artifact.Head, installation.HeadId, 4, ref score))
        {
            return 0;
        }

        if (!TryScoreArtifactPlatform(artifact, installation.Platform, 2, ref score))
        {
            return 0;
        }

        if (!TryScoreArtifactArch(artifact, installation.Arch, 1, ref score))
        {
            return 0;
        }

        if (string.Equals(artifact.Kind, "installer", StringComparison.OrdinalIgnoreCase)
            || artifact.Id.EndsWith("-installer", StringComparison.OrdinalIgnoreCase))
        {
            score += 3;
        }

        return score;
    }

    private static bool TryScoreArtifactField(string? artifactValue, string? installationValue, int fieldScore, ref int score)
    {
        if (string.IsNullOrWhiteSpace(installationValue))
        {
            return true;
        }

        if (!string.Equals(artifactValue, installationValue, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        score += fieldScore;
        return true;
    }

    private static bool TryScoreArtifactPlatform(PublicReleaseArtifactDto artifact, string? installationPlatform, int fieldScore, ref int score)
    {
        if (string.IsNullOrWhiteSpace(installationPlatform))
        {
            return true;
        }

        string normalizedInstallPlatform = NormalizeInstallPlatform(installationPlatform);
        string[] artifactPlatforms =
        [
            NormalizeInstallPlatform(artifact.PlatformId),
            NormalizeInstallPlatform(artifact.Platform),
            NormalizeInstallPlatform(PlatformFromRid(artifact.PlatformId)),
            NormalizeInstallPlatform(PlatformFromRid(artifact.Id))
        ];

        if (!artifactPlatforms.Any(value => string.Equals(value, normalizedInstallPlatform, StringComparison.OrdinalIgnoreCase)))
        {
            return false;
        }

        score += fieldScore;
        return true;
    }

    private static bool TryScoreArtifactArch(PublicReleaseArtifactDto artifact, string? installationArch, int fieldScore, ref int score)
    {
        if (string.IsNullOrWhiteSpace(installationArch))
        {
            return true;
        }

        string normalizedInstallArch = NormalizeInstallArch(installationArch);
        string[] artifactArchitectures =
        [
            NormalizeInstallArch(artifact.Arch),
            NormalizeInstallArch(ArchFromRid(artifact.PlatformId)),
            NormalizeInstallArch(ArchFromRid(artifact.Id))
        ];

        if (!artifactArchitectures.Any(value => string.Equals(value, normalizedInstallArch, StringComparison.OrdinalIgnoreCase)))
        {
            return false;
        }

        score += fieldScore;
        return true;
    }

    private static string NormalizeInstallPlatform(string? value)
    {
        string token = NormalizeResponseValue(value).ToLowerInvariant();
        return token switch
        {
            "win" or "win32" or "win64" or "windows-x64" or "windows-arm64" or "win-x64" or "win-arm64" => "windows",
            "osx" or "mac" or "darwin" or "macos-x64" or "macos-arm64" or "osx-x64" or "osx-arm64" => "macos",
            "linux-x64" or "linux-arm64" => "linux",
            _ when token.Contains("windows", StringComparison.OrdinalIgnoreCase) => "windows",
            _ when token.Contains("macos", StringComparison.OrdinalIgnoreCase) => "macos",
            _ when token.Contains("linux", StringComparison.OrdinalIgnoreCase) => "linux",
            _ => token
        };
    }

    private static string NormalizeInstallArch(string? value)
    {
        string token = NormalizeResponseValue(value).ToLowerInvariant();
        return token switch
        {
            "amd64" or "x86_64" or "win-x64" or "linux-x64" or "osx-x64" or "windows-x64" => "x64",
            "aarch64" or "arm64" or "win-arm64" or "linux-arm64" or "osx-arm64" or "windows-arm64" => "arm64",
            _ when token.EndsWith("-x64", StringComparison.OrdinalIgnoreCase) => "x64",
            _ when token.EndsWith("-arm64", StringComparison.OrdinalIgnoreCase) => "arm64",
            _ => token
        };
    }

    private static string? PlatformFromRid(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string token = value.Trim();
        if (token.Contains("win-x64", StringComparison.OrdinalIgnoreCase)
            || token.Contains("win-arm64", StringComparison.OrdinalIgnoreCase))
        {
            return "windows";
        }

        if (token.Contains("osx-x64", StringComparison.OrdinalIgnoreCase)
            || token.Contains("osx-arm64", StringComparison.OrdinalIgnoreCase))
        {
            return "macos";
        }

        if (token.Contains("linux-x64", StringComparison.OrdinalIgnoreCase)
            || token.Contains("linux-arm64", StringComparison.OrdinalIgnoreCase))
        {
            return "linux";
        }

        return null;
    }

    private static string? ArchFromRid(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string token = value.Trim();
        if (token.Contains("-x64", StringComparison.OrdinalIgnoreCase))
        {
            return "x64";
        }

        if (token.Contains("-arm64", StringComparison.OrdinalIgnoreCase))
        {
            return "arm64";
        }

        return null;
    }

    private IReadOnlyList<DesktopInstallSupportContinuationCase> ResolveSupportContinuationCases(
        ClaimedInstallationDto installation,
        InstallLinkingSummaryDto installSummary,
        DownloadReceiptDto? receipt,
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? releaseArtifact,
        DesktopInstallContinuationReceipt? continuation,
        bool updateAvailable)
    {
        IReadOnlyList<SupportCaseProjection> reporterCases = _supportCases.ListForReporter(installation.UserId, installation.SubjectId).Items;
        var relevantCases = reporterCases
            .Where(item => IsInstallContinuationCase(item, installation))
            .ToArray();
        return _supportPresentation.BuildList(relevantCases, installSummary)
            .Take(4)
            .Select(item => new DesktopInstallSupportContinuationCase(
                CaseId: item.Case.CaseId,
                InstallationId: installation.InstallationId,
                ApplicationVersion: installation.Version,
                ReleaseChannel: installation.Channel,
                HeadId: NormalizeResponseValue(installation.HeadId),
                Platform: NormalizeResponseValue(installation.Platform),
                Arch: NormalizeResponseValue(installation.Arch),
                InstalledBuildReceiptId: receipt?.ReceiptId,
                StatusLabel: item.StatusLabel,
                StageLabel: item.StageLabel,
                NextSafeAction: BuildNativeSupportNextSafeAction(item, updateAvailable),
                PrimaryActionHref: BuildNativeSupportCaseActionHref(item),
                FixedReleaseLabel: item.FixedReleaseLabel,
                InstallReadinessSummary: item.InstallReadinessSummary,
                ReporterActionNeeded: item.ReporterActionNeeded,
                FixReadyOnLinkedInstall: item.FixReadyOnLinkedInstall,
                NeedsInstallUpdate: item.NeedsInstallUpdate,
                NeedsLinkedInstall: item.NeedsLinkedInstall,
                CurrentReleaseVersion: manifest.Version,
                CurrentReleaseChannel: manifest.Channel,
                CurrentArtifactId: releaseArtifact?.Id,
                FallbackPosture: continuation?.FallbackPosture
                    ?? MissingCurrentInstallerFallbackPosture,
                UpdateAvailable: updateAvailable,
                UpdateAction: updateAvailable
                    ? $"Update this linked copy from {installation.Channel} {installation.Version} to {manifest.Channel} {manifest.Version}, then refresh support from the app."
                    : continuation?.UpdateAction ?? "Refresh support from the app before starting another install or support path.",
                RollbackAction: continuation?.RollbackAction
                    ?? "If support, update, or setup fails, keep the previous installed copy and return to Devices and access for this linked copy.",
                NativeContinuationHref: "/api/v1/install-linking/continuation",
                NativeSupportHref: "/api/v1/install-linking/continuation/support",
                NativeUpdateHref: "/api/v1/install-linking/continuation/update",
                NativeRollbackHref: "/api/v1/install-linking/continuation/rollback",
                NativeRecoveryHref: NativeRecoveryHref,
                RecoveryAction: BuildNativeRecoveryAction(installation, continuation)))
            .ToArray();
    }

    private static string BuildNativeSupportCaseActionHref(SupportCasePresentationViewModel item)
    {
        if (item.ReporterActionNeeded)
        {
            return NativeSupportHref;
        }

        if (item.NeedsInstallUpdate)
        {
            return NativeUpdateHref;
        }

        if (item.FixReadyOnLinkedInstall)
        {
            return NativeContinuationHref;
        }

        return NativeContinuationHref;
    }

    private static string BuildNativeSupportNextSafeAction(SupportCasePresentationViewModel item, bool updateAvailable)
    {
        if (item.ReporterActionNeeded)
        {
            return "Continue support from the desktop app for this linked copy; keep the case, install, and device together.";
        }

        if (item.NeedsInstallUpdate)
        {
            return updateAvailable
                ? "Continue with the desktop app update view for this linked copy, then return to this same support case to check the fix."
                : "Refresh this linked copy from the desktop app before checking support; do not start a separate download or browser claim path.";
        }

        if (item.FixReadyOnLinkedInstall)
        {
            return "Check the fix from this linked desktop copy; keep support attached to this install.";
        }

        string? nativeActionHref = NormalizeNativeInstallRailHref(item.PrimaryActionHref);
        bool primaryActionIsBrowserRail = IsBrowserRailHref(item.PrimaryActionHref);
        if (!primaryActionIsBrowserRail && string.Equals(nativeActionHref, NativeContinuationHref, StringComparison.Ordinal))
        {
            return "Continue in the desktop app for this linked copy.";
        }

        return "Stay with this linked desktop copy; account, downloads, and public support links are fallback only.";
    }

    private static string? NormalizeNativeInstallRailHref(string? href)
    {
        if (string.IsNullOrWhiteSpace(href))
        {
            return null;
        }

        string trimmed = href.Trim();
        if (trimmed.StartsWith("//", StringComparison.Ordinal))
        {
            return null;
        }

        if (!trimmed.StartsWith("/", StringComparison.Ordinal)
            && Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? absoluteUri))
        {
            if (!IsTrustedNativeInstallRailAbsoluteUri(absoluteUri))
            {
                return null;
            }

            trimmed = absoluteUri.AbsolutePath;
        }
        else if (!trimmed.StartsWith("/", StringComparison.Ordinal))
        {
            return null;
        }

        string pathForValidation = NativeInstallRailPathForValidation(trimmed);
        if (pathForValidation.Contains('\\')
            || ContainsEncodedPathSeparator(pathForValidation)
            || (!pathForValidation.StartsWith("/", StringComparison.Ordinal)
                && Uri.TryCreate(trimmed, UriKind.Absolute, out _)))
        {
            return null;
        }

        string path = NormalizeBrowserRailPath(pathForValidation);
        if (path.Equals(NativeContinuationHref, StringComparison.OrdinalIgnoreCase))
        {
            return NativeContinuationHref;
        }

        if (path.Equals(NativeSupportHref, StringComparison.OrdinalIgnoreCase))
        {
            return NativeSupportHref;
        }

        if (path.Equals(NativeUpdateHref, StringComparison.OrdinalIgnoreCase))
        {
            return NativeUpdateHref;
        }

        return path.Equals(NativeRollbackHref, StringComparison.OrdinalIgnoreCase)
            ? NativeRollbackHref
            : null;
    }

    private static bool IsTrustedNativeInstallRailAbsoluteUri(Uri absoluteUri)
    {
        if (IsTrustedNativeInstallRailPublicHost(absoluteUri.Host))
        {
            return string.Equals(absoluteUri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase);
        }

        return IsAppLocalCallbackHost(absoluteUri.Host)
               && (string.Equals(absoluteUri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(absoluteUri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase));
    }

    private static bool IsTrustedNativeInstallRailPublicHost(string host)
        => string.Equals(host, "chummer.run", StringComparison.OrdinalIgnoreCase)
           || string.Equals(host, "www.chummer.run", StringComparison.OrdinalIgnoreCase);

    private static string NativeInstallRailPathForValidation(string href)
    {
        int queryOrFragmentIndex = href.IndexOfAny(['?', '#']);
        return queryOrFragmentIndex >= 0 ? href[..queryOrFragmentIndex] : href;
    }

    private static bool ContainsEncodedPathSeparator(string href)
    {
        if (ContainsSingleEncodedPathSeparator(href))
        {
            return true;
        }

        string decoded = href;
        for (int index = 0; index < 4; index++)
        {
            string next;
            try
            {
                next = Uri.UnescapeDataString(decoded);
            }
            catch (UriFormatException)
            {
                return false;
            }

            if (string.Equals(next, decoded, StringComparison.Ordinal))
            {
                break;
            }

            decoded = next;
            if (ContainsSingleEncodedPathSeparator(decoded))
            {
                return true;
            }
        }

        return false;
    }

    private static bool ContainsSingleEncodedPathSeparator(string href)
        => href.Contains("%2f", StringComparison.OrdinalIgnoreCase)
           || href.Contains("%5c", StringComparison.OrdinalIgnoreCase);

    private static bool IsBrowserRailHref(string? href)
    {
        if (string.IsNullOrWhiteSpace(href))
        {
            return false;
        }

        string trimmed = href.Trim();
        string path = NormalizeBrowserRailPath(trimmed);
        return path.StartsWith("/account/", StringComparison.OrdinalIgnoreCase)
               || path.Equals("/account", StringComparison.OrdinalIgnoreCase)
               || path.StartsWith("/contact", StringComparison.OrdinalIgnoreCase)
               || path.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase);
    }

    private static string NormalizeBrowserRailPath(string href)
    {
        string trimmed = href.Trim();
        string path = trimmed.StartsWith("//", StringComparison.Ordinal)
            ? trimmed
            : Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? parsed)
            ? parsed.AbsolutePath
            : trimmed;
        int queryIndex = path.IndexOfAny(['?', '#']);
        if (queryIndex >= 0)
        {
            path = path[..queryIndex];
        }

        path = DecodeBrowserRailPath(path);
        path = NormalizeBrowserRailSeparators(path);
        path = NormalizeLeadingBrowserRailSlashes(path);
        return path.StartsWith("/", StringComparison.Ordinal)
            ? path
            : $"/{path}";
    }

    private static string DecodeBrowserRailPath(string path)
    {
        string decoded = path;
        for (int index = 0; index < 4; index++)
        {
            string next;
            try
            {
                next = Uri.UnescapeDataString(decoded);
            }
            catch (UriFormatException)
            {
                return decoded;
            }

            if (string.Equals(next, decoded, StringComparison.Ordinal))
            {
                break;
            }

            decoded = next;
        }

        return decoded;
    }

    private static string NormalizeBrowserRailSeparators(string path)
        => path.Replace('\\', '/');

    private static string NormalizeLeadingBrowserRailSlashes(string path)
    {
        string trimmed = path.TrimStart();
        int index = 0;
        while (index < trimmed.Length && trimmed[index] == '/')
        {
            index++;
        }

        return index > 1 ? $"/{trimmed[index..]}" : trimmed;
    }

    private static bool IsInstallContinuationCase(SupportCaseProjection supportCase, ClaimedInstallationDto installation)
    {
        if (!string.Equals(supportCase.Kind, SupportCaseKinds.InstallHelp, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (string.Equals(supportCase.InstallationId, installation.InstallationId, StringComparison.OrdinalIgnoreCase))
        {
            return MatchesClaimedInstallTruthWhenPresent(supportCase, installation);
        }

        if (!string.IsNullOrWhiteSpace(supportCase.InstallationId))
        {
            return false;
        }

        return MatchesClaimedInstallTruth(supportCase, installation);
    }

    private static bool MatchesClaimedInstallTruthWhenPresent(SupportCaseProjection supportCase, ClaimedInstallationDto installation)
        => HasSupportCaseInstallTruth(supportCase)
           && MatchesOptionalTruth(supportCase.ReleaseChannel, installation.Channel)
           && MatchesOptionalTruth(supportCase.ApplicationVersion, installation.Version)
           && MatchesOptionalTruth(supportCase.HeadId, installation.HeadId)
           && MatchesOptionalTruth(supportCase.Platform, installation.Platform)
           && MatchesOptionalTruth(supportCase.Arch, installation.Arch);

    private static bool MatchesOptionalTruth(string? supportValue, string? installationValue)
        => string.IsNullOrWhiteSpace(supportValue)
           || string.Equals(supportValue, installationValue, StringComparison.OrdinalIgnoreCase);

    private static bool MatchesClaimedInstallTruth(SupportCaseProjection supportCase, ClaimedInstallationDto installation)
    {
        if (!HasInstallTruth(supportCase.ApplicationVersion, supportCase.ReleaseChannel)
            || !string.Equals(supportCase.ApplicationVersion, installation.Version, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(supportCase.ReleaseChannel, installation.Channel, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        bool hasInstallSpecificContext = false;
        bool hasDeviceSpecificContext = false;
        if (!MatchesOptionalInstallTruth(supportCase.ApplicationVersion, installation.Version, ref hasInstallSpecificContext)
            || !MatchesOptionalDeviceTruth(supportCase.HeadId, installation.HeadId, ref hasInstallSpecificContext, ref hasDeviceSpecificContext)
            || !MatchesOptionalDeviceTruth(supportCase.Platform, installation.Platform, ref hasInstallSpecificContext, ref hasDeviceSpecificContext)
            || !MatchesOptionalDeviceTruth(supportCase.Arch, installation.Arch, ref hasInstallSpecificContext, ref hasDeviceSpecificContext))
        {
            return false;
        }

        return hasInstallSpecificContext && hasDeviceSpecificContext;
    }

    private static bool HasSupportCaseInstallTruth(SupportCaseProjection supportCase)
        => HasInstallTruth(supportCase.ApplicationVersion, supportCase.ReleaseChannel)
           && HasDeviceTruth(supportCase.HeadId, supportCase.Platform, supportCase.Arch);

    private static bool HasInstallTruth(string? applicationVersion, string? releaseChannel)
        => HasCompleteInstalledBuildTruth(applicationVersion, releaseChannel);

    private static bool HasCompleteInstalledBuildTruth(string? applicationVersion, string? releaseChannel)
        => !string.IsNullOrWhiteSpace(applicationVersion)
           && !string.IsNullOrWhiteSpace(releaseChannel);

    private static bool HasDeviceTruth(string? headId, string? platform, string? arch)
        => !string.IsNullOrWhiteSpace(headId)
           && !string.IsNullOrWhiteSpace(platform)
           && !string.IsNullOrWhiteSpace(arch);

    private static bool MatchesOptionalInstallTruth(string? supportValue, string? installationValue, ref bool hasInstallSpecificContext)
    {
        if (string.IsNullOrWhiteSpace(supportValue))
        {
            return true;
        }

        hasInstallSpecificContext = true;
        return string.Equals(supportValue, installationValue, StringComparison.OrdinalIgnoreCase);
    }

    private static bool MatchesOptionalDeviceTruth(
        string? supportValue,
        string? installationValue,
        ref bool hasInstallSpecificContext,
        ref bool hasDeviceSpecificContext)
    {
        if (string.IsNullOrWhiteSpace(supportValue))
        {
            return true;
        }

        hasInstallSpecificContext = true;
        hasDeviceSpecificContext = true;
        return string.Equals(supportValue, installationValue, StringComparison.OrdinalIgnoreCase);
    }

    private static DownloadReceiptDto? ResolveLatestReceipt(
        InstallLinkingSummaryDto installSummary,
        ClaimedInstallationDto installation,
        PublicReleaseArtifactDto? releaseArtifact)
        => installSummary.RecentReceipts
            .Where(item => MatchesInstalledBuildReceiptTruth(item, installation, releaseArtifact))
            .OrderByDescending(static item => item.IssuedAtUtc)
            .FirstOrDefault();

    private static bool MatchesInstalledBuildReceiptTruth(
        DownloadReceiptDto receipt,
        ClaimedInstallationDto installation,
        PublicReleaseArtifactDto? releaseArtifact)
    {
        if (!MatchesReceiptDeviceTruth(receipt, installation))
        {
            return false;
        }

        return string.Equals(receipt.ArtifactId, installation.ArtifactId, StringComparison.OrdinalIgnoreCase)
               || (releaseArtifact is not null && string.Equals(receipt.ArtifactId, releaseArtifact.Id, StringComparison.OrdinalIgnoreCase));
    }

    private static bool MatchesReceiptDeviceTruth(DownloadReceiptDto receipt, ClaimedInstallationDto installation)
        => string.Equals(receipt.Channel, installation.Channel, StringComparison.OrdinalIgnoreCase)
           && string.Equals(receipt.Version, installation.Version, StringComparison.OrdinalIgnoreCase)
           && string.Equals(receipt.Head, installation.HeadId, StringComparison.OrdinalIgnoreCase)
           && string.Equals(receipt.Platform, installation.Platform, StringComparison.OrdinalIgnoreCase)
           && string.Equals(receipt.Arch, installation.Arch, StringComparison.OrdinalIgnoreCase);

    private static bool IsUpdateAvailable(ClaimedInstallationDto installation, PublicReleaseManifestDto manifest, PublicReleaseArtifactDto? releaseArtifact)
    {
        if (releaseArtifact is null)
        {
            return false;
        }

        return !string.Equals(installation.Version, manifest.Version, StringComparison.OrdinalIgnoreCase)
               || !string.Equals(installation.Channel, manifest.Channel, StringComparison.OrdinalIgnoreCase)
               || !string.Equals(installation.ArtifactId, releaseArtifact.Id, StringComparison.OrdinalIgnoreCase);
    }

    private static string BuildNativeNextSafeAction(
        bool updateAvailable,
        DesktopInstallSupportContinuationCase? leadSupportCase,
        DesktopInstallContinuationReceipt? continuation)
    {
        if (leadSupportCase is not null)
        {
            return leadSupportCase.NextSafeAction;
        }

        if (updateAvailable)
        {
            return "Continue in the desktop app updater for this linked copy; keep support and rollback on this same device.";
        }

        return continuation?.NextSafeAction
            ?? "Continue from this claimed desktop install; use support recovery only if this app reports a recovery state.";
    }

    private static string BuildNativeContinuationPrimaryActionHref(
        bool updateAvailable,
        DesktopInstallSupportContinuationCase? leadSupportCase)
    {
        if (leadSupportCase is not null)
        {
            return BuildNativeSupportContinuationCaseActionHref(leadSupportCase);
        }

        return updateAvailable ? NativeUpdateHref : NativeContinuationHref;
    }

    private static string BuildNativeSupportContinuationCaseActionHref(DesktopInstallSupportContinuationCase item)
    {
        if (item.ReporterActionNeeded)
        {
            return NativeSupportHref;
        }

        if (item.NeedsInstallUpdate)
        {
            return NativeUpdateHref;
        }

        if (item.FixReadyOnLinkedInstall)
        {
            return NativeContinuationHref;
        }

        return NativeContinuationHref;
    }

    private static string BuildNativeRollbackPlan(ClaimedInstallationDto installation, DownloadReceiptDto? receipt)
    {
        string receiptLabel = string.IsNullOrWhiteSpace(receipt?.ReceiptId)
            ? "the installed build already linked to this grant"
            : $"installed build record {receipt.ReceiptId}";
        return $"Keep or restore {installation.Channel} {installation.Version} from {receiptLabel} on {NormalizeResponseValue(installation.HeadId)} {NormalizeResponseValue(installation.Platform)} {NormalizeResponseValue(installation.Arch)}, then refresh this linked copy before filing support.";
    }

    private static string BuildNativeUpdatePlan(
        ClaimedInstallationDto installation,
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto? releaseArtifact,
        DownloadReceiptDto? receipt,
        bool updateAvailable)
    {
        string receiptLabel = string.IsNullOrWhiteSpace(receipt?.ReceiptId)
            ? "the installed build already linked to this grant"
            : $"installed build record {receipt.ReceiptId}";
        string artifactLabel = string.IsNullOrWhiteSpace(releaseArtifact?.Id)
            ? "the matching installer"
            : releaseArtifact.Id;
        string deviceLabel = $"{NormalizeResponseValue(installation.HeadId)} {NormalizeResponseValue(installation.Platform)} {NormalizeResponseValue(installation.Arch)}";
        return updateAvailable
            ? $"Update {deviceLabel} from {installation.Channel} {installation.Version} using {receiptLabel} to {manifest.Channel} {manifest.Version} via {artifactLabel}, then refresh this linked copy before checking support."
            : $"Keep {deviceLabel} on {installation.Channel} {installation.Version} from {receiptLabel}; no newer matching installer is required, so refresh this linked copy before filing support.";
    }

    private static string BuildNativeRecoveryAction(
        ClaimedInstallationDto installation,
        DesktopInstallContinuationReceipt? continuation)
        => continuation?.NextSafeAction
           ?? $"Return {NormalizeResponseValue(installation.HeadId)} {NormalizeResponseValue(installation.Platform)} {NormalizeResponseValue(installation.Arch)} to this linked copy for recovery; claim-code and account links remain fallback context only.";

    private static PublicReleaseArtifactDto? ResolveBrowserCallbackArtifact(
        PublicReleaseManifestDto manifest,
        string? headId,
        string? platform,
        string? arch)
    {
        ClaimedInstallationDto probe = new(
            InstallationId: "browser-callback-probe",
            ArtifactId: string.Empty,
            Channel: manifest.Channel,
            Version: manifest.Version,
            InstallAccessClass: InstallAccessClasses.AccountRecommended,
            Status: ClaimedInstallationStates.Active,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow,
            UserId: null,
            SubjectId: null,
            PublicKey: null,
            ClaimTicketId: null,
            HeadId: headId,
            Platform: platform,
            Arch: arch,
            HostLabel: null,
            GrantId: null);
        return manifest.Downloads
            .Select(item => new
            {
                Artifact = item,
                Score = ScoreArtifactMatch(item, probe)
            })
            .OrderByDescending(static item => item.Score)
            .ThenBy(static item => item.Artifact.Id, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(static item => item.Score > 0)
            ?.Artifact;
    }

    private static string? NormalizeCallbackUri(string? callbackUri)
    {
        if (string.IsNullOrWhiteSpace(callbackUri))
        {
            return null;
        }

        if (!Uri.TryCreate(callbackUri.Trim(), UriKind.Absolute, out Uri? parsed))
        {
            return null;
        }

        if (string.Equals(parsed.Scheme, "chummer", StringComparison.OrdinalIgnoreCase))
        {
            bool installLinkTarget = string.Equals(parsed.Host, "install-link", StringComparison.OrdinalIgnoreCase)
                                     && (string.IsNullOrWhiteSpace(parsed.AbsolutePath)
                                         || string.Equals(parsed.AbsolutePath, "/", StringComparison.Ordinal));
            return installLinkTarget ? parsed.ToString() : null;
        }

        bool localhostHttp = (string.Equals(parsed.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
                              || string.Equals(parsed.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
                             && IsAppLocalCallbackHost(parsed.Host)
                             && IsAppLocalInstallLinkCallbackPath(parsed.AbsolutePath);
        return localhostHttp ? parsed.ToString() : null;
    }

    private static bool IsAppLocalCallbackHost(string host)
        => string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase)
           || (System.Net.IPAddress.TryParse(host, out System.Net.IPAddress? address)
               && System.Net.IPAddress.IsLoopback(address));

    private static bool IsAppLocalInstallLinkCallbackUri(string callbackUri)
    {
        if (!Uri.TryCreate(callbackUri, UriKind.Absolute, out Uri? parsed))
        {
            return false;
        }

        return (string.Equals(parsed.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
                || string.Equals(parsed.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
               && IsAppLocalCallbackHost(parsed.Host)
               && IsAppLocalInstallLinkCallbackPath(parsed.AbsolutePath);
    }

    private static bool IsAppLocalInstallLinkCallbackPath(string absolutePath)
    {
        if (string.IsNullOrWhiteSpace(absolutePath))
        {
            return false;
        }

        string normalizedPath = absolutePath.Trim();
        while (normalizedPath.Length > AppLocalInstallLinkCallbackPath.Length
               && normalizedPath.EndsWith("/", StringComparison.Ordinal))
        {
            normalizedPath = normalizedPath[..^1];
        }

        return string.Equals(normalizedPath, AppLocalInstallLinkCallbackPath, StringComparison.Ordinal);
    }

    private static string BuildBrowserInstallCallbackRedirectUri(
        string callbackUri,
        string callbackCode,
        string installationId,
        string headId,
        string applicationVersion,
        string releaseChannel,
        string platform,
        string arch)
        => QueryHelpers.AddQueryString(
            StripReservedInstallLinkCallbackState(callbackUri),
            new Dictionary<string, string?>
            {
                ["code"] = callbackCode,
                ["installationId"] = installationId,
                ["headId"] = headId,
                ["applicationVersion"] = applicationVersion,
                ["releaseChannel"] = releaseChannel,
                ["platform"] = platform,
                ["arch"] = arch,
                ["installLinkMode"] = "browser_callback",
                ["installLinkTransport"] = "grant_callback"
            });

    private static string StripReservedInstallLinkCallbackState(string callbackUri)
    {
        if (!Uri.TryCreate(callbackUri, UriKind.Absolute, out Uri? parsed)
            || (string.IsNullOrEmpty(parsed.Query) && string.IsNullOrEmpty(parsed.Fragment)))
        {
            return callbackUri;
        }

        var builder = new UriBuilder(parsed)
        {
            Query = string.Empty,
            Fragment = string.Empty
        };
        string baseUri = builder.Uri.ToString();
        string withQuery = AddPreservedInstallLinkCallbackComponent(baseUri, parsed.Query, prefix: "?");
        return AppendPreservedInstallLinkCallbackFragment(withQuery, parsed.Fragment);
    }

    private static string AddPreservedInstallLinkCallbackComponent(string baseUri, string component, string prefix)
    {
        Dictionary<string, string?> preserved = PreserveInstallLinkCallbackComponent(component, prefix);
        return preserved.Count == 0
            ? baseUri
            : QueryHelpers.AddQueryString(baseUri, preserved);
    }

    private static string AppendPreservedInstallLinkCallbackFragment(string baseUri, string fragment)
    {
        Dictionary<string, string?> preserved = PreserveInstallLinkCallbackComponent(fragment, "#");
        return preserved.Count == 0
            ? baseUri
            : $"{baseUri}#{BuildInstallLinkCallbackComponent(preserved)}";
    }

    private static Dictionary<string, string?> PreserveInstallLinkCallbackComponent(string component, string prefix)
    {
        var preserved = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        if (string.IsNullOrEmpty(component)
            || !component.StartsWith(prefix, StringComparison.Ordinal)
            || component.Length == prefix.Length
            || !component.Contains('=', StringComparison.Ordinal))
        {
            return preserved;
        }

        foreach (var item in QueryHelpers.ParseQuery(component[prefix.Length..]))
        {
            if (InstallLinkCallbackReservedQueryKeys.Contains(item.Key))
            {
                continue;
            }

            preserved[item.Key] = item.Value.ToString();
        }

        return preserved;
    }

    private static string BuildInstallLinkCallbackComponent(Dictionary<string, string?> values)
        => string.Join(
            "&",
            values.Select(static item =>
                $"{Uri.EscapeDataString(item.Key)}={Uri.EscapeDataString(item.Value ?? string.Empty)}"));

    private NativeRouteProofStatus BuildNativeRouteProofStatus(string route, string boundedFailureReason)
    {
        LocalReleaseProofLookupResult routeLookup = FindLocalReleaseProofReceipt(route);
        if (!string.IsNullOrWhiteSpace(routeLookup.CurrentnessFailureReason))
        {
            return new NativeRouteProofStatus(
                State: "bounded_failure",
                RouteReceipt: null,
                BoundedFailureReason: $"Parity claims stay review-required because {routeLookup.CurrentnessFailureReason!.Trim().TrimEnd('.')}.");
        }

        LocalProofReceiptMatch? routeReceipt = routeLookup.ReceiptMatch;
        if (routeReceipt is null)
        {
            return new NativeRouteProofStatus(
                State: "bounded_failure",
                RouteReceipt: null,
                BoundedFailureReason: boundedFailureReason);
        }

        FlagshipReadinessSnapshot? readiness = _flagshipReadiness.LoadSnapshot();
        if (readiness?.MissingDesktopClientCoverage == true)
        {
            string reviewRequiredReason = readiness.DesktopClientGapSummary.Trim().TrimEnd('.');
            return new NativeRouteProofStatus(
                State: "bounded_failure",
                RouteReceipt: BuildRouteReceiptPayload(routeReceipt),
                BoundedFailureReason: $"Current direct route is attached, but this still needs review because {reviewRequiredReason}.");
        }

        ImportRouteParityProofGuardSnapshot importRouteGuard = _importRouteParityProofGuard.Evaluate();
        if (!importRouteGuard.IsCurrent && !string.IsNullOrWhiteSpace(importRouteGuard.ReviewRequiredReason))
        {
            return new NativeRouteProofStatus(
                State: "bounded_failure",
                RouteReceipt: BuildRouteReceiptPayload(routeReceipt),
                BoundedFailureReason: $"Current direct route is attached, but this still needs review because {importRouteGuard.ReviewRequiredReason!.Trim().TrimEnd('.')}.");
        }

        return new NativeRouteProofStatus(
            State: "pass",
            RouteReceipt: BuildRouteReceiptPayload(routeReceipt),
            BoundedFailureReason: null);
    }

    private static NativeRouteReceiptDto? BuildRouteReceiptPayload(LocalProofReceiptMatch? routeReceipt)
        => routeReceipt is null
            ? null
            : new NativeRouteReceiptDto(
                ReceiptId: routeReceipt.ReceiptId,
                PackageId: routeReceipt.PackageId,
                MatchedRoute: routeReceipt.MatchedRoute,
                MatchMode: routeReceipt.MatchMode,
                Summary: routeReceipt.Summary);

    private LocalReleaseProofLookupResult FindLocalReleaseProofReceipt(params string?[] routeCandidates)
        => _localReleaseProof.FindReceipt(routeCandidates);

    private static string? NormalizeOptionalValue(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string NormalizeResponseValue(string? value)
        => string.IsNullOrWhiteSpace(value) ? "unknown" : value.Trim();

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

}

public sealed record DesktopInstallNativeContinuationRequest(
    string InstallationId,
    string AccessToken);

public sealed record DesktopInstallNativeContinuationResponse(
    string InstallationId,
    string ArtifactId,
    string ApplicationVersion,
    string ReleaseChannel,
    string HeadId,
    string Platform,
    string Arch,
    string InstallStatus,
    string? InstalledBuildReceiptId,
    string CurrentReleaseVersion,
    string CurrentReleaseChannel,
    string? CurrentArtifactId,
    string RouteState,
    NativeRouteReceiptDto? RouteReceipt,
    string? BoundedFailureReason,
    string FallbackPosture,
    bool UpdateAvailable,
    string NextSafeAction,
    string NativePrimaryActionHref,
    string UpdateAction,
    string RollbackAction,
    string SupportHref,
    string NativeUpdateHref,
    string NativeSupportHref,
    string NativeRollbackHref,
    string NativeRecoveryHref,
    string RecoveryAction,
    string SupportContinuation,
    IReadOnlyList<DesktopInstallSupportContinuationCase> SupportCases);

public sealed record DesktopInstallNativeSupportRequest(
    string InstallationId,
    string AccessToken,
    string? Title = null,
    string? Summary = null,
    string? Detail = null,
    string? ReporterEmail = null,
    string? RequestedActionHref = null);

public sealed record DesktopInstallNativeSupportResponse(
    string CaseId,
    string InstallationId,
    string ApplicationVersion,
    string ReleaseChannel,
    string HeadId,
    string Platform,
    string Arch,
    string StatusLabel,
    string StageLabel,
    string NextSafeAction,
    string PrimaryActionHref,
    string AccountSupportHref,
    string NativeSupportHref,
    string NativeContinuationHref,
    string NativeUpdateHref,
    string NativeRollbackHref,
    string NativeRecoveryHref,
    string? InstalledBuildReceiptId,
    string CurrentReleaseVersion,
    string CurrentReleaseChannel,
    string? CurrentArtifactId,
    string RouteState,
    NativeRouteReceiptDto? RouteReceipt,
    string? BoundedFailureReason,
    string FallbackPosture,
    bool UpdateAvailable,
    string UpdateAction,
    string RollbackAction,
    string RecoveryAction);

public sealed record DesktopInstallNativeUpdateResponse(
    string InstallationId,
    string ArtifactId,
    string ApplicationVersion,
    string ReleaseChannel,
    string HeadId,
    string Platform,
    string Arch,
    string? InstalledBuildReceiptId,
    string CurrentReleaseVersion,
    string CurrentReleaseChannel,
    string? CurrentArtifactId,
    string RouteState,
    NativeRouteReceiptDto? RouteReceipt,
    string? BoundedFailureReason,
    bool UpdateAvailable,
    string UpdatePlan,
    string UpdateAction,
    string NativePrimaryActionHref,
    string SupportHref,
    string NativeContinuationHref,
    string NativeSupportHref,
    string NativeRollbackHref,
    string NativeRecoveryHref,
    string FallbackPosture,
    string RecoveryAction);

public sealed record DesktopInstallNativeRollbackResponse(
    string InstallationId,
    string ArtifactId,
    string ApplicationVersion,
    string ReleaseChannel,
    string HeadId,
    string Platform,
    string Arch,
    string? InstalledBuildReceiptId,
    string CurrentReleaseVersion,
    string CurrentReleaseChannel,
    string? CurrentArtifactId,
    string RouteState,
    NativeRouteReceiptDto? RouteReceipt,
    string? BoundedFailureReason,
    bool UpdateAvailable,
    string RollbackPlan,
    string RollbackAction,
    string NativePrimaryActionHref,
    string SupportHref,
    string NativeContinuationHref,
    string NativeUpdateHref,
    string NativeSupportHref,
    string NativeRecoveryHref,
    string FallbackPosture,
    string RecoveryAction);

public sealed record DesktopInstallSupportContinuationCase(
    string CaseId,
    string InstallationId,
    string ApplicationVersion,
    string ReleaseChannel,
    string HeadId,
    string Platform,
    string Arch,
    string? InstalledBuildReceiptId,
    string StatusLabel,
    string StageLabel,
    string NextSafeAction,
    string PrimaryActionHref,
    string? FixedReleaseLabel,
    string InstallReadinessSummary,
    bool ReporterActionNeeded,
    bool FixReadyOnLinkedInstall,
    bool NeedsInstallUpdate,
    bool NeedsLinkedInstall,
    string CurrentReleaseVersion,
    string CurrentReleaseChannel,
    string? CurrentArtifactId,
    string FallbackPosture,
    bool UpdateAvailable,
    string UpdateAction,
    string RollbackAction,
    string NativeContinuationHref,
    string NativeSupportHref,
    string NativeUpdateHref,
    string NativeRollbackHref,
    string NativeRecoveryHref,
    string RecoveryAction);

public sealed record NativeRouteReceiptDto(
    string ReceiptId,
    string PackageId,
    string MatchedRoute,
    string MatchMode,
    string Summary);

public sealed record NativeRouteProofStatus(
    string State,
    NativeRouteReceiptDto? RouteReceipt,
    string? BoundedFailureReason);

public sealed record InstallLinkedWorkspaceSnapshotListResponse(
    IReadOnlyList<InstallLinkedWorkspaceSnapshotDto> Snapshots);

public sealed record InstallLinkedWorkspaceSnapshotUpsertRequest(
    string InstallationId,
    string AccessToken,
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
    bool Created);

public sealed record InstallLinkedWorkspaceSnapshotUpsertResponse(
    InstallLinkedWorkspaceSnapshotDto Snapshot);

public sealed record InstallLinkedWorkspaceSnapshotDto(
    string WorkspaceId,
    string RulesetId,
    string Format,
    int SchemaVersion,
    string PayloadKind,
    string Payload,
    DateTimeOffset UpdatedAtUtc,
    string? OriginInstallationId,
    CharacterFileSummary Summary);
