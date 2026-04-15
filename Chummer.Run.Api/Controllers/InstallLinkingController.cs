using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.WebUtilities;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/install-linking")]
public sealed class InstallLinkingController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;
    private readonly PublicReleaseManifestService _releases;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;

    public InstallLinkingController(
        HubIdentityClient identity,
        AccountService accounts,
        InstallLinkingService installLinking,
        PublicReleaseManifestService releases,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation)
    {
        _identity = identity;
        _accounts = accounts;
        _installLinking = installLinking;
        _releases = releases;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
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
        IReadOnlyList<DesktopInstallSupportContinuationCase> supportCases = ResolveSupportContinuationCases(installation, installSummary);
        DesktopInstallSupportContinuationCase? leadSupportCase = supportCases.FirstOrDefault(static item => item.ReporterActionNeeded)
            ?? supportCases.FirstOrDefault();
        string supportHref = releaseArtifact is null
            ? BuildFallbackSupportHref(installation)
            : DesktopInstallRail.BuildSupportHref(releaseArtifact, manifest, installation.InstallationId, recoveryMode: false);

        return Ok(new DesktopInstallNativeContinuationResponse(
            InstallationId: installation.InstallationId,
            ArtifactId: installation.ArtifactId,
            ApplicationVersion: installation.Version,
            ReleaseChannel: installation.Channel,
            HeadId: installation.HeadId,
            Platform: installation.Platform,
            Arch: installation.Arch,
            InstallStatus: installation.Status,
            InstalledBuildReceiptId: receipt?.ReceiptId,
            CurrentReleaseVersion: manifest.Version,
            CurrentReleaseChannel: manifest.Channel,
            CurrentArtifactId: releaseArtifact?.Id,
            UpdateAvailable: updateAvailable,
            NextSafeAction: BuildNativeNextSafeAction(updateAvailable, leadSupportCase, continuation),
            UpdateAction: updateAvailable
                ? $"Update this linked install from {installation.Channel} {installation.Version} to {manifest.Channel} {manifest.Version}, then refresh the install grant from the app."
                : continuation?.UpdateAction ?? "Refresh the install grant from the app before starting a new install or support path.",
            RollbackAction: continuation?.RollbackAction
                ?? "If update or setup fails, keep the previous installed copy and return to this continuation endpoint before opening a new support path.",
            SupportHref: supportHref,
            SupportContinuation: leadSupportCase?.NextSafeAction
                ?? continuation?.SupportContinuation
                ?? "Support follow-through stays on this claimed install with the current build, channel, and device context attached.",
            SupportCases: supportCases));
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
        if (!string.IsNullOrWhiteSpace(installation.HeadId)
            && string.Equals(artifact.Head, installation.HeadId, StringComparison.OrdinalIgnoreCase))
        {
            score += 4;
        }

        if (!string.IsNullOrWhiteSpace(installation.Platform)
            && (string.Equals(artifact.PlatformId, installation.Platform, StringComparison.OrdinalIgnoreCase)
                || string.Equals(artifact.Platform, installation.Platform, StringComparison.OrdinalIgnoreCase)))
        {
            score += 2;
        }

        if (!string.IsNullOrWhiteSpace(installation.Arch)
            && string.Equals(artifact.Arch, installation.Arch, StringComparison.OrdinalIgnoreCase))
        {
            score += 1;
        }

        return score;
    }

    private IReadOnlyList<DesktopInstallSupportContinuationCase> ResolveSupportContinuationCases(
        ClaimedInstallationDto installation,
        InstallLinkingSummaryDto installSummary)
    {
        IReadOnlyList<SupportCaseProjection> reporterCases = _supportCases.ListForReporter(installation.UserId, installation.SubjectId).Items;
        var relevantCases = reporterCases
            .Where(item => IsInstallContinuationCase(item, installation))
            .ToArray();
        return _supportPresentation.BuildList(relevantCases, installSummary)
            .Take(4)
            .Select(item => new DesktopInstallSupportContinuationCase(
                CaseId: item.Case.CaseId,
                StatusLabel: item.StatusLabel,
                StageLabel: item.StageLabel,
                NextSafeAction: item.NextSafeAction,
                PrimaryActionHref: item.PrimaryActionHref,
                FixedReleaseLabel: item.FixedReleaseLabel,
                InstallReadinessSummary: item.InstallReadinessSummary,
                ReporterActionNeeded: item.ReporterActionNeeded,
                FixReadyOnLinkedInstall: item.FixReadyOnLinkedInstall,
                NeedsInstallUpdate: item.NeedsInstallUpdate,
                NeedsLinkedInstall: item.NeedsLinkedInstall))
            .ToArray();
    }

    private static bool IsInstallContinuationCase(SupportCaseProjection supportCase, ClaimedInstallationDto installation)
        => string.Equals(supportCase.InstallationId, installation.InstallationId, StringComparison.OrdinalIgnoreCase)
           || string.Equals(supportCase.Kind, SupportCaseKinds.InstallHelp, StringComparison.OrdinalIgnoreCase)
           || (!string.IsNullOrWhiteSpace(supportCase.ReleaseChannel)
               && string.Equals(supportCase.ReleaseChannel, installation.Channel, StringComparison.OrdinalIgnoreCase)
               && (string.IsNullOrWhiteSpace(supportCase.HeadId)
                   || string.Equals(supportCase.HeadId, installation.HeadId, StringComparison.OrdinalIgnoreCase)));

    private static DownloadReceiptDto? ResolveLatestReceipt(
        InstallLinkingSummaryDto installSummary,
        ClaimedInstallationDto installation,
        PublicReleaseArtifactDto? releaseArtifact)
        => installSummary.RecentReceipts
            .Where(item => string.Equals(item.ArtifactId, installation.ArtifactId, StringComparison.OrdinalIgnoreCase)
                           || (releaseArtifact is not null && string.Equals(item.ArtifactId, releaseArtifact.Id, StringComparison.OrdinalIgnoreCase))
                           || (string.Equals(item.Channel, installation.Channel, StringComparison.OrdinalIgnoreCase)
                               && string.Equals(item.Version, installation.Version, StringComparison.OrdinalIgnoreCase)
                               && string.Equals(item.Head, installation.HeadId, StringComparison.OrdinalIgnoreCase)))
            .OrderByDescending(static item => item.IssuedAtUtc)
            .FirstOrDefault();

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
            return "Continue in the desktop app update lane for this claimed install; keep support and rollback on this same install rail.";
        }

        return continuation?.NextSafeAction
            ?? "Continue from this claimed desktop install; use support recovery only if this app reports a recovery state.";
    }

    private static string BuildFallbackSupportHref(ClaimedInstallationDto installation)
        => QueryHelpers.AddQueryString(
            "/contact",
            new Dictionary<string, string?>
            {
                ["kind"] = SupportCaseKinds.InstallHelp,
                ["title"] = "Install help for claimed desktop install",
                ["summary"] = "Install, update, rollback, or support follow-through needs help on this linked device.",
                ["detail"] = "The desktop app requested continuation help from its claimed install rail.",
                ["installationId"] = installation.InstallationId,
                ["applicationVersion"] = installation.Version,
                ["releaseChannel"] = installation.Channel,
                ["headId"] = installation.HeadId,
                ["platform"] = installation.Platform,
                ["arch"] = installation.Arch
            });
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
    bool UpdateAvailable,
    string NextSafeAction,
    string UpdateAction,
    string RollbackAction,
    string SupportHref,
    string SupportContinuation,
    IReadOnlyList<DesktopInstallSupportContinuationCase> SupportCases);

public sealed record DesktopInstallSupportContinuationCase(
    string CaseId,
    string StatusLabel,
    string StageLabel,
    string NextSafeAction,
    string PrimaryActionHref,
    string? FixedReleaseLabel,
    string InstallReadinessSummary,
    bool ReporterActionNeeded,
    bool FixReadyOnLinkedInstall,
    bool NeedsInstallUpdate,
    bool NeedsLinkedInstall);
