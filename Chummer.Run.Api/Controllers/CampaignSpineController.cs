using Chummer.Campaign.Contracts;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/campaign-spine")]
public sealed class CampaignSpineController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;
    private readonly CampaignFederationOrchestrationService _campaignFederation;
    private readonly FlagshipReadinessArtifactService _flagshipReadiness;
    private readonly ImportRouteParityProofGuardService _importRouteParityProofGuard;
    private readonly LocalReleaseProofArtifactService _localReleaseProof;
    private readonly MediaArtifactHorizonsService? _mediaHorizons;

    public CampaignSpineController(
        HubIdentityClient identity,
        AccountService accounts,
        InstallLinkingService installLinking,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane,
        CampaignFederationOrchestrationService campaignFederation,
        IConfiguration configuration,
        MediaArtifactHorizonsService? mediaHorizons = null)
    {
        _identity = identity;
        _accounts = accounts;
        _installLinking = installLinking;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
        _campaignFederation = campaignFederation;
        _flagshipReadiness = new FlagshipReadinessArtifactService(configuration);
        _importRouteParityProofGuard = new ImportRouteParityProofGuardService(configuration);
        _localReleaseProof = new LocalReleaseProofArtifactService(configuration);
        _mediaHorizons = mediaHorizons;
    }

    [HttpGet("me")]
    [ProducesResponseType<AccountCampaignSummary>(StatusCodes.Status200OK)]
    public async Task<ActionResult<AccountCampaignSummary>> GetMyCampaignSummary(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetAccountSummary(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/quicksilver/command-deck")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<ActionResult<object>> GetMyQuicksilverCommandDeck(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();
            BuildLabHandoffProjection? leadHandoff = summary.BuildLabHandoffs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
            CreatorPublicationProjection? leadPublication = summary.CreatorPublications.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
            RulesNavigatorAnswerProjection? leadRule = summary.RulesNavigator.FirstOrDefault();

            return Ok(new
            {
                horizon = "quicksilver",
                status = "shipped_mvp",
                counts = new
                {
                    buildHandoffs = summary.BuildLabHandoffs.Count,
                    rulesAnswers = summary.RulesNavigator.Count,
                    workspaces = summary.Workspaces.Count,
                    publications = summary.CreatorPublications.Count
                },
                routes = new
                {
                    accountEntryHref = "/account/quicksilver",
                    accountRedirectHref = "/account/quicksilver/open",
                    focusHrefTemplate = "/account/quicksilver/{focus}",
                    jumpTargetsApiHref = "/api/v1/campaign-spine/me/quicksilver/jump-targets"
                },
                leadTargets = new
                {
                    builds = leadHandoff is null ? "/account/alice" : $"/account/alice/{Uri.EscapeDataString(leadHandoff.HandoffId)}",
                    rules = leadRule is null ? "/account/work" : $"/account/work/rules/{Uri.EscapeDataString(leadRule.EntryId)}",
                    runsites = leadWorkspace is null ? "/account/runsites" : $"/account/runsites/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}",
                    creator = leadPublication is null ? "/account/creator" : $"/account/creator/{Uri.EscapeDataString(leadPublication.PublicationId)}",
                    briefings = leadPublication is null ? "/account/jackpoint" : $"/account/jackpoint/{Uri.EscapeDataString(leadPublication.PublicationId)}"
                },
                boundary = new
                {
                    rulesTruth = "explainability_required",
                    bulkMutationAuthority = "not_claimed",
                    backgroundAutomation = "not_claimed",
                    cacheAuthority = "not_claimed"
                }
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/quicksilver/jump-targets")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<ActionResult<object>> GetMyQuicksilverJumpTargets(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();
            BuildLabHandoffProjection? leadHandoff = summary.BuildLabHandoffs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
            CreatorPublicationProjection? leadPublication = summary.CreatorPublications.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
            RulesNavigatorAnswerProjection? leadRule = summary.RulesNavigator.FirstOrDefault();

            return Ok(new[]
            {
                new
                {
                    focus = "builds",
                    label = "Build handoffs",
                    available = leadHandoff is not null,
                    href = leadHandoff is null ? "/account/alice" : $"/account/alice/{Uri.EscapeDataString(leadHandoff.HandoffId)}",
                    summary = leadHandoff is null ? "ALICE remains ready for the next governed build handoff." : $"{leadHandoff.Title} is the lead build handoff."
                },
                new
                {
                    focus = "rules",
                    label = "Rules answers",
                    available = leadRule is not null,
                    href = leadRule is null ? "/account/work" : $"/account/work/rules/{Uri.EscapeDataString(leadRule.EntryId)}",
                    summary = leadRule is null ? "Rules Navigator remains ready for the next typed answer." : leadRule.Question
                },
                new
                {
                    focus = "runsites",
                    label = "Prep benches",
                    available = leadWorkspace is not null,
                    href = leadWorkspace is null ? "/account/runsites" : $"/account/runsites/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}",
                    summary = leadWorkspace is null ? "RUNSITE remains ready for the next governed workspace." : leadWorkspace.CampaignName
                },
                new
                {
                    focus = "creator",
                    label = "Creator desk",
                    available = leadPublication is not null,
                    href = leadPublication is null ? "/account/creator" : $"/account/creator/{Uri.EscapeDataString(leadPublication.PublicationId)}",
                    summary = leadPublication is null ? "Creator OS remains ready for the next publication desk." : leadPublication.Title
                },
                new
                {
                    focus = "briefings",
                    label = "JACKPOINT desk",
                    available = leadPublication is not null,
                    href = leadPublication is null ? "/account/jackpoint" : $"/account/jackpoint/{Uri.EscapeDataString(leadPublication.PublicationId)}",
                    summary = leadPublication is null ? "JACKPOINT remains ready for the next publication-safe briefing desk." : leadPublication.Title
                }
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/onramp/dashboard")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<ActionResult<object>> GetMyOnrampDashboard(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();
            WorkspaceRestoreProjection restore = summary.Restore;

            return Ok(new
            {
                horizon = "onramp",
                status = "shipped_mvp",
                counts = new
                {
                    campaigns = summary.Campaigns.Count,
                    workspaces = summary.Workspaces.Count,
                    dossiers = summary.Dossiers.Count,
                    restoreArtifacts = restore.RecentArtifacts.Count,
                    restoreConflicts = restore.ConflictSummaries.Count
                },
                routes = new
                {
                    accountEntryHref = "/account/onramp",
                    accountRedirectHref = "/account/onramp/open",
                    accountStarterHref = "/account/onramp/starter",
                    dashboardApiHref = "/api/v1/campaign-spine/me/onramp/dashboard",
                    starterApiHref = "/api/v1/campaign-spine/me/onramp/starter",
                    recoveryApiHref = "/api/v1/campaign-spine/me/onramp/recovery"
                },
                starterWorkspace = starterWorkspace is null ? null : new
                {
                    starterWorkspace.WorkspaceId,
                    starterWorkspace.CampaignId,
                    starterWorkspace.CampaignName,
                    ruleEnvironment = starterWorkspace.RuleEnvironment.CompatibilityFingerprint,
                    starterWorkspace.ReturnSummary,
                    starterWorkspace.NextSafeAction,
                    accountHref = $"/account/runsites/{Uri.EscapeDataString(starterWorkspace.WorkspaceId)}",
                    apiHref = $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(starterWorkspace.WorkspaceId)}"
                },
                recovery = new
                {
                    restore.RestoreId,
                    recentArtifacts = restore.RecentArtifacts.Count,
                    recentDossiers = restore.RecentDossiers.Count,
                    claimedDevices = restore.ClaimedDevices.Count,
                    conflictCount = restore.ConflictSummaries.Count,
                    localOnlyNotes = restore.LocalOnlyNotes.Count,
                    accountHref = "/account/access",
                    apiHref = "/api/v1/campaign-spine/me/onramp/recovery"
                },
                boundary = new
                {
                    buildTruth = "core_receipts_only",
                    hiddenAutomation = "not_claimed",
                    autoBuildAuthority = "not_claimed",
                    recoveryAuthority = "signed_in_receipts"
                }
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/onramp/starter")]
    [ProducesResponseType<CampaignWorkspaceProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignWorkspaceProjection>> GetMyOnrampStarter(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? starter = _campaignSpine.GetStarterWorkspace(user, installLinking);
            return starter is null ? NotFound() : Ok(starter);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/onramp/recovery")]
    [ProducesResponseType<WorkspaceRestoreProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<WorkspaceRestoreProjection>> GetMyOnrampRecovery(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetRestoreProjection(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/edition-studio/heads")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<ActionResult<object>> GetMyEditionStudioHeads(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            EditionStudioHeadSummary[] heads = BuildEditionStudioHeadSummaries(summary);

            return Ok(new
            {
                horizon = "edition_studio",
                status = "shipped_mvp",
                routes = new
                {
                    accountEntryHref = "/account/edition-studio",
                    accountRedirectHref = "/account/edition-studio/open",
                    accountHeadHrefTemplate = "/account/edition-studio/{edition}",
                    headsApiHref = "/api/v1/campaign-spine/me/edition-studio/heads",
                    headDetailApiHrefTemplate = "/api/v1/campaign-spine/me/edition-studio/heads/{edition}"
                },
                heads
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/edition-studio/heads/{edition}")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<object>> GetMyEditionStudioHead([FromRoute] string edition, CancellationToken cancellationToken)
    {
        try
        {
            string normalizedEdition = NormalizeEditionStudioHeadId(edition);
            if (normalizedEdition is not ("sr4" or "sr5" or "sr6"))
            {
                return NotFound();
            }

            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            EditionStudioHeadSummary[] heads = BuildEditionStudioHeadSummaries(summary);
            EditionStudioHeadSummary? head = heads.FirstOrDefault(item => string.Equals(item.Edition, normalizedEdition, StringComparison.OrdinalIgnoreCase));
            return head is null
                ? NotFound()
                : Ok(new
                {
                    horizon = "edition_studio",
                    status = "shipped_mvp",
                    head
                });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/local-co-processor/capabilities")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<ActionResult<object>> GetMyLocalCoProcessorCapabilities(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);

            string preferredProfile = summary.Restore.ClaimedDevices.Count > 0
                ? "privacy_first"
                : summary.Workspaces.Count > 0 || summary.Dossiers.Count > 0
                    ? "hybrid_local"
                    : "hosted_only";

            return Ok(new
            {
                horizon = "local_co_processor",
                status = "shipped_mvp",
                counts = new
                {
                    workspaces = summary.Workspaces.Count,
                    dossiers = summary.Dossiers.Count,
                    claimedDevices = summary.Restore.ClaimedDevices.Count,
                    profiles = 3
                },
                routes = new
                {
                    accountEntryHref = "/account/local-co-processor",
                    accountRedirectHref = "/account/local-co-processor/open",
                    accountProfileHrefTemplate = "/account/local-co-processor/{profile}",
                    capabilitiesApiHref = "/api/v1/campaign-spine/me/local-co-processor/capabilities",
                    policyApiHref = "/api/v1/campaign-spine/me/local-co-processor/policy"
                },
                profiles = new[]
                {
                    new
                    {
                        profile = "hosted_only",
                        label = "Hosted only",
                        selected = string.Equals(preferredProfile, "hosted_only", StringComparison.Ordinal),
                        accountHref = "/account/local-co-processor/hosted_only",
                        apiHref = "/api/v1/campaign-spine/me/local-co-processor/policy",
                        summary = "Keep every workflow fully hosted with no local acceleration requirement."
                    },
                    new
                    {
                        profile = "hybrid_local",
                        label = "Hybrid local",
                        selected = string.Equals(preferredProfile, "hybrid_local", StringComparison.Ordinal),
                        accountHref = "/account/local-co-processor/hybrid_local",
                        apiHref = "/api/v1/campaign-spine/me/local-co-processor/capabilities",
                        summary = "Allow optional local acceleration where it improves responsiveness or cost."
                    },
                    new
                    {
                        profile = "privacy_first",
                        label = "Privacy first",
                        selected = string.Equals(preferredProfile, "privacy_first", StringComparison.Ordinal),
                        accountHref = "/account/local-co-processor/privacy_first",
                        apiHref = "/api/v1/campaign-spine/me/local-co-processor/capabilities",
                        summary = "Prefer local handling where it reduces disclosure without breaking hosted fallback."
                    }
                },
                boundary = new
                {
                    hostedFirstParity = "required",
                    localTruthAuthority = "not_claimed",
                    mandatoryRuntime = "not_claimed",
                    disableableProfiles = "required"
                }
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/local-co-processor/policy")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<ActionResult<object>> GetMyLocalCoProcessorPolicy(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);

            return Ok(new
            {
                horizon = "local_co_processor",
                status = "shipped_mvp",
                policy = new
                {
                    hostedFirstParity = true,
                    optionalLocalAcceleration = true,
                    disableableProfiles = true,
                    mandatoryRuntime = false,
                    localTruthAuthority = false,
                    failOpenFallback = true,
                    claimedDevices = summary.Restore.ClaimedDevices.Count,
                    recentRuleEnvironments = summary.Restore.RecentRuleEnvironments.Count
                },
                routes = new
                {
                    accountEntryHref = "/account/local-co-processor",
                    accountRedirectHref = "/account/local-co-processor/open",
                    capabilitiesApiHref = "/api/v1/campaign-spine/me/local-co-processor/capabilities",
                    policyApiHref = "/api/v1/campaign-spine/me/local-co-processor/policy"
                },
                boundary = new
                {
                    canonicalTruth = "hosted_first",
                    providerIndependence = "required",
                    offlineRequirement = "not_claimed",
                    hiddenDependency = "not_claimed"
                }
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/run-control/dashboard")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<ActionResult<object>> GetMyRunControlDashboard(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            RunProjection? leadRun = summary.Runs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
            CampaignWorkspaceProjection? leadWorkspace = leadRun is null
                ? _campaignSpine.GetStarterWorkspace(user, installLinking) ?? summary.Workspaces.FirstOrDefault()
                : summary.Workspaces.FirstOrDefault(item => item.Runs.Any(run => string.Equals(run.RunId, leadRun.RunId, StringComparison.OrdinalIgnoreCase)))
                    ?? _campaignSpine.GetStarterWorkspace(user, installLinking)
                    ?? summary.Workspaces.FirstOrDefault();
            RunboardContinuityProjection? continuity = leadRun?.RunboardContinuity;

            return Ok(new
            {
                horizon = "run_control",
                status = "shipped_mvp",
                counts = new
                {
                    campaigns = summary.Campaigns.Count,
                    workspaces = summary.Workspaces.Count,
                    runs = summary.Runs.Count,
                    continuityRuns = summary.Runs.Count(item => item.RunboardContinuity is not null)
                },
                routes = new
                {
                    accountEntryHref = "/account/run-control",
                    accountRedirectHref = "/account/run-control/open",
                    accountRunHrefTemplate = "/account/run-control/{runId}",
                    runIndexApiHref = "/api/v1/campaign-spine/me/runs",
                    dashboardApiHref = "/api/v1/campaign-spine/me/run-control/dashboard",
                    runDetailApiHrefTemplate = "/api/v1/campaign-spine/me/run-control/runs/{runId}"
                },
                leadRun = leadRun is null ? null : new
                {
                    leadRun.RunId,
                    leadRun.Title,
                    leadRun.Status,
                    leadRun.Summary,
                    leadRun.ActiveSceneId,
                    activeSceneTitle = leadRun.Scenes.FirstOrDefault(scene => string.Equals(scene.SceneId, leadRun.ActiveSceneId, StringComparison.OrdinalIgnoreCase))?.Title,
                    objectiveCount = leadRun.Objectives.Count,
                    sceneCount = leadRun.Scenes.Count,
                    accountHref = $"/account/run-control/{Uri.EscapeDataString(leadRun.RunId)}",
                    apiHref = $"/api/v1/campaign-spine/me/run-control/runs/{Uri.EscapeDataString(leadRun.RunId)}"
                },
                leadWorkspace = leadWorkspace is null ? null : new
                {
                    leadWorkspace.WorkspaceId,
                    leadWorkspace.CampaignId,
                    leadWorkspace.CampaignName,
                    leadWorkspace.NextSafeAction,
                    leadWorkspace.ActiveSceneSummary,
                    accountHref = $"/account/runsites/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}",
                    apiHref = $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}"
                },
                continuity = continuity is null ? null : new
                {
                    continuity.RunTitle,
                    continuity.ActiveSceneTitle,
                    continuity.Summary,
                    handoffSummary = continuity.TurnLedgerHandoff.Summary,
                    runboardSummary = continuity.RunboardState.Summary,
                    nextSafeAction = continuity.RunboardState.NextSafeAction,
                    resolutionDraftStatus = continuity.ResolutionReportDraft.Status
                },
                boundary = new
                {
                    campaignTruth = "first_party_only",
                    reconnectAuthority = "receipt_backed",
                    genericCollaborationReplacement = "not_claimed",
                    hiddenStateAuthority = "not_claimed"
                }
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/run-control/runs/{runId}")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<object>> GetMyRunControlRun([FromRoute] string runId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            RunProjection? run = _campaignSpine.GetRun(user, runId, installLinking);
            if (run is null)
            {
                return NotFound();
            }

            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? workspace = summary.Workspaces.FirstOrDefault(item => item.Runs.Any(candidate => string.Equals(candidate.RunId, run.RunId, StringComparison.OrdinalIgnoreCase)));
            SceneProjection? activeScene = run.Scenes.FirstOrDefault(scene => string.Equals(scene.SceneId, run.ActiveSceneId, StringComparison.OrdinalIgnoreCase));

            return Ok(new
            {
                horizon = "run_control",
                status = "shipped_mvp",
                run = new
                {
                    run.RunId,
                    run.CampaignId,
                    run.Title,
                    run.Status,
                    run.Summary,
                    run.ActiveSceneId,
                    activeSceneTitle = activeScene?.Title,
                    activeSceneSummary = activeScene?.Summary,
                    objectiveCount = run.Objectives.Count,
                    sceneCount = run.Scenes.Count,
                    accountHref = $"/account/run-control/{Uri.EscapeDataString(run.RunId)}"
                },
                workspace = workspace is null ? null : new
                {
                    workspace.WorkspaceId,
                    workspace.CampaignName,
                    workspace.ReturnSummary,
                    workspace.NextSafeAction,
                    workspace.ActiveSceneSummary,
                    accountHref = $"/account/runsites/{Uri.EscapeDataString(workspace.WorkspaceId)}"
                },
                continuity = run.RunboardContinuity is null ? null : new
                {
                    run.RunboardContinuity.ContinuityId,
                    run.RunboardContinuity.Summary,
                    run.RunboardContinuity.ActiveSceneTitle,
                    turnLedgerSummary = run.RunboardContinuity.TurnLedgerHandoff.Summary,
                    runboardSummary = run.RunboardContinuity.RunboardState.Summary,
                    blockers = run.RunboardContinuity.RunboardState.Blockers,
                    resolutionNextSafeAction = run.RunboardContinuity.ResolutionReportDraft.NextSafeAction
                },
                objectives = run.Objectives.Select(objective => new
                {
                    objective.ObjectiveId,
                    objective.Title,
                    objective.Status,
                    objective.Pressure,
                    objective.Summary
                }),
                scenes = run.Scenes.Select(scene => new
                {
                    scene.SceneId,
                    scene.Title,
                    scene.Status,
                    scene.Summary,
                    isActive = string.Equals(scene.SceneId, run.ActiveSceneId, StringComparison.OrdinalIgnoreCase)
                })
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/organizer-ops")]
    [ProducesResponseType<OrganizerOperationsDashboardProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<OrganizerOperationsDashboardProjection>> GetMyOrganizerOperations(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetOrganizerOperations(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/restore")]
    [ProducesResponseType<WorkspaceRestoreProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<WorkspaceRestoreProjection>> GetMyRestoreProjection(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetRestoreProjection(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}")]
    [ProducesResponseType<CampaignWorkspaceProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignWorkspaceProjection>> GetMyCampaignWorkspace([FromRoute] string workspaceId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var workspace = _campaignSpine.GetWorkspace(user, workspaceId, installLinking);
            return workspace is null ? NotFound() : Ok(workspace);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("me/workspaces/starter")]
    [ProducesResponseType<CampaignWorkspaceProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignWorkspaceProjection>> SeedStarterWorkspace(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? starter = _campaignSpine.GetStarterWorkspace(user, installLinking);
            return starter is null ? NotFound() : Ok(starter);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspace-digests")]
    [ProducesResponseType<IReadOnlyList<CampaignWorkspaceDigestProjection>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<CampaignWorkspaceDigestProjection>>> GetMyCampaignWorkspaceDigests(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetWorkspaceDigests(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/property-workspaces/{propertyId}")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<object>> GetMyPropertyquarryWorkspace([FromRoute] string propertyId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            MediaArtifactDocument property = GetPropertyquarryPropertyOrThrow(propertyId);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();

            return Ok(new
            {
                horizon = "propertyquarry",
                status = "shipped_mvp",
                property = new
                {
                    property.Id,
                    property.Label,
                    property.Style,
                    property.Summary,
                    property.MarkdownRoute,
                    property.JsonRoute,
                    accountHref = $"/account/propertyquarry/{Uri.EscapeDataString(property.Id)}",
                    prepSearchAccountHref = BuildPropertyquarryPrepSearchAccountHref(property.Label, leadWorkspace?.WorkspaceId),
                    publicTourHref = property.TourActionHref ?? property.TourHref
                },
                routes = new
                {
                    accountEntryHref = "/account/propertyquarry",
                    accountRedirectHref = "/account/propertyquarry/open",
                    accountWorkspaceHrefTemplate = "/account/propertyquarry/{propertyId}",
                    workspaceIndexApiHref = "/api/v1/campaign-spine/me/workspace-digests",
                    continuityApiHrefTemplate = "/api/v1/campaign-spine/me/property-continuity/{propertyId}"
                },
                selectedWorkspace = leadWorkspace is null ? null : new
                {
                    leadWorkspace.WorkspaceId,
                    leadWorkspace.CampaignId,
                    leadWorkspace.CampaignName,
                    leadWorkspace.ReturnSummary,
                    leadWorkspace.NextSafeAction,
                    accountHref = BuildPropertyquarryPrepSearchAccountHref(property.Label, leadWorkspace.WorkspaceId),
                    workspaceApiHref = $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}",
                    prepLibraryApiHref = BuildPropertyquarryPrepLibraryApiHref(leadWorkspace.WorkspaceId, property.Label)
                },
                boundary = new
                {
                    tacticalAuthority = "not_claimed",
                    prepTruth = "workspace_prep_library_search",
                    propertyTruth = "player_safe_property_packet_only"
                }
            });
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/property-continuity/{propertyId}")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<object>> GetMyPropertyquarryContinuity([FromRoute] string propertyId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            MediaArtifactDocument property = GetPropertyquarryPropertyOrThrow(propertyId);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();
            string prepSearchAccountHref = BuildPropertyquarryPrepSearchAccountHref(property.Label, leadWorkspace?.WorkspaceId);

            return Ok(new
            {
                horizon = "propertyquarry",
                status = "shipped_mvp",
                property = new
                {
                    property.Id,
                    property.Label,
                    property.Style,
                    accountHref = $"/account/propertyquarry/{Uri.EscapeDataString(property.Id)}",
                    prepSearchAccountHref
                },
                continuity = new
                {
                    workspaceCount = summary.Workspaces.Count,
                    runCount = summary.Runs.Count,
                    searchQuery = property.Label,
                    workspaceAvailable = leadWorkspace is not null,
                    workspaceAccountHref = prepSearchAccountHref,
                    workspaceApiHref = leadWorkspace is null ? null : $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}",
                    prepLibraryApiHref = leadWorkspace is null ? null : BuildPropertyquarryPrepLibraryApiHref(leadWorkspace.WorkspaceId, property.Label),
                    nextSafeAction = leadWorkspace?.NextSafeAction,
                    returnSummary = leadWorkspace?.ReturnSummary
                },
                boundary = new
                {
                    providerTruth = "not_exposed",
                    hiddenPropertyTruth = "not_claimed",
                    continuityTruth = "workspace_and_run_receipts"
                }
            });
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/server-plane")]
    [ProducesResponseType<CampaignWorkspaceServerPlaneProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignWorkspaceServerPlaneProjection>> GetMyCampaignWorkspaceServerPlane([FromRoute] string workspaceId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var serverPlane = _workspaceServerPlane.GetWorkspaceServerPlane(user, workspaceId, installLinking);
            return serverPlane is null ? NotFound() : Ok(serverPlane);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/consequences")]
    [ProducesResponseType<IReadOnlyList<CampaignConsequenceProjection>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<IReadOnlyList<CampaignConsequenceProjection>>> GetMyCampaignWorkspaceConsequences(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var consequences = _workspaceServerPlane.GetWorkspaceConsequences(user, workspaceId, installLinking);
            return consequences is null ? NotFound() : Ok(consequences);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/consequence-truth")]
    [ProducesResponseType<CampaignConsequenceTruthProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignConsequenceTruthProjection>> GetMyCampaignWorkspaceConsequenceTruth(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var consequenceTruth = _workspaceServerPlane.GetWorkspaceConsequenceTruth(user, workspaceId, installLinking);
            return consequenceTruth is null ? NotFound() : Ok(consequenceTruth);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/aftermath-recap-packages")]
    [ProducesResponseType<IReadOnlyList<AftermathRecapPackageProjection>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<IReadOnlyList<AftermathRecapPackageProjection>>> GetMyCampaignWorkspaceAftermathRecapPackages(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var packages = _workspaceServerPlane.GetWorkspaceAftermathRecapPackages(user, workspaceId, installLinking);
            return packages is null ? NotFound() : Ok(packages);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/downtime-aftermath")]
    [ProducesResponseType<DowntimeAftermathApiProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<DowntimeAftermathApiProjection>> GetMyCampaignWorkspaceDowntimeAftermath(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var downtimeAftermath = _workspaceServerPlane.GetWorkspaceDowntimeAftermath(user, workspaceId, installLinking);
            return downtimeAftermath is null ? NotFound() : Ok(downtimeAftermath);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/campaign-memory")]
    [ProducesResponseType<CampaignMemoryProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignMemoryProjection>> GetMyCampaignWorkspaceCampaignMemory(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var campaignMemory = _workspaceServerPlane.GetWorkspaceCampaignMemory(user, workspaceId, installLinking);
            return campaignMemory is null ? NotFound() : Ok(campaignMemory);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/next-session-carry-forward")]
    [ProducesResponseType<NextSessionCarryForwardProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<NextSessionCarryForwardProjection>> GetMyCampaignWorkspaceNextSessionCarryForward(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var carryForward = _workspaceServerPlane.GetWorkspaceNextSessionCarryForward(user, workspaceId, installLinking);
            return carryForward is null ? NotFound() : Ok(carryForward);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/runboard-continuity")]
    [ProducesResponseType<RunboardContinuityProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RunboardContinuityProjection>> GetMyCampaignWorkspaceRunboardContinuity(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var continuity = _workspaceServerPlane.GetWorkspaceRunboardContinuity(user, workspaceId, installLinking);
            return continuity is null ? NotFound() : Ok(continuity);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/open-runs")]
    [ProducesResponseType<IReadOnlyList<OpenRunListingProjection>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<OpenRunListingProjection>>> GetMyOpenRuns(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetOpenRuns(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/open-runs/{openRunId}")]
    [ProducesResponseType<OpenRunOrchestrationProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<OpenRunOrchestrationProjection>> GetMyOpenRun([FromRoute] string openRunId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var openRun = _campaignSpine.GetOpenRun(user, openRunId, installLinking);
            return openRun is null ? NotFound() : Ok(openRun);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/adoption-loop")]
    [ProducesResponseType<CampaignAdoptionLoopProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignAdoptionLoopProjection>> GetMyCampaignWorkspaceAdoptionLoop(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var adoptionLoop = _workspaceServerPlane.GetWorkspaceCampaignAdoptionLoop(user, workspaceId, installLinking);
            return adoptionLoop is null ? NotFound() : Ok(adoptionLoop);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/prep-library")]
    [ProducesResponseType<CampaignPrepLibrarySearchResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignPrepLibrarySearchResponse>> GetMyCampaignWorkspacePrepLibrary(
        [FromRoute] string workspaceId,
        [FromQuery] string? queryText,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var prepLibrary = _workspaceServerPlane.GetWorkspacePrepLibrary(user, workspaceId, installLinking, queryText);
            return prepLibrary is null ? NotFound() : Ok(prepLibrary);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/roster-transfer-plan")]
    [ProducesResponseType<RosterTransferPlannerProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RosterTransferPlannerProjection>> GetMyCampaignWorkspaceRosterTransferPlan(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var rosterTransferPlan = _campaignSpine.GetRosterTransferPlan(user, workspaceId, installLinking);
            return rosterTransferPlan is null ? NotFound() : Ok(rosterTransferPlan);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/dossier-movement-plan")]
    [ProducesResponseType<DossierMovementPlannerProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<DossierMovementPlannerProjection>> GetMyCampaignWorkspaceDossierMovementPlan(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var dossierMovementPlan = _campaignSpine.GetDossierMovementPlan(user, workspaceId, installLinking);
            return dossierMovementPlan is null ? NotFound() : Ok(dossierMovementPlan);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/dossier-movements")]
    [ProducesResponseType<IReadOnlyList<DossierMovementReceiptProjection>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<IReadOnlyList<DossierMovementReceiptProjection>>> GetMyCampaignWorkspaceDossierMovements(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var workspace = _campaignSpine.GetWorkspace(user, workspaceId, installLinking);
            return workspace is null ? NotFound() : Ok(_campaignSpine.GetDossierMovements(user, workspaceId, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("me/workspaces/{workspaceId}/prep-library/launches")]
    [ProducesResponseType<GovernedPrepLaunchProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<GovernedPrepLaunchProjection>> LaunchMyCampaignWorkspacePrepPacket(
        [FromRoute] string workspaceId,
        [FromBody] GovernedPrepLaunchRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("governed prep launch payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var launch = _workspaceServerPlane.LaunchWorkspacePrepPacket(user, workspaceId, request, installLinking);
            return launch is null ? NotFound() : Ok(launch);
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

    [HttpPost("me/workspaces/{workspaceId}/travel-prefetches")]
    [ProducesResponseType<TravelPrefetchReceiptProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<TravelPrefetchReceiptProjection>> StageMyCampaignWorkspaceTravelPrefetch(
        [FromRoute] string workspaceId,
        [FromBody] TravelPrefetchStageRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("travel-prefetch payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var receipt = _workspaceServerPlane.StageTravelPrefetch(user, workspaceId, request, installLinking);
            return receipt is null ? NotFound() : Ok(receipt);
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

    [HttpPost("me/workspaces/{workspaceId}/aftermath-recap-packages")]
    [ProducesResponseType<AftermathRecapPackageProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<AftermathRecapPackageProjection>> GenerateMyCampaignWorkspaceAftermathRecapPackage(
        [FromRoute] string workspaceId,
        [FromBody] AftermathRecapPackageRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("aftermath recap payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var package = _workspaceServerPlane.GenerateAftermathRecapPackage(user, workspaceId, request, installLinking);
            return package is null ? NotFound() : Ok(package);
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

    [HttpPost("me/workspaces/{workspaceId}/consequences")]
    [ProducesResponseType<CampaignConsequenceProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignConsequenceProjection>> UpsertMyCampaignWorkspaceConsequence(
        [FromRoute] string workspaceId,
        [FromBody] CampaignConsequenceUpdateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("campaign consequence payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var consequence = _workspaceServerPlane.UpsertCampaignConsequence(user, workspaceId, request, installLinking);
            return consequence is null ? NotFound() : Ok(consequence);
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

    [HttpPost("me/workspaces/{workspaceId}/runboard-continuity")]
    [ProducesResponseType<RunboardContinuityProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RunboardContinuityProjection>> UpsertMyCampaignWorkspaceRunboardContinuity(
        [FromRoute] string workspaceId,
        [FromBody] RunboardContinuityUpdateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("runboard continuity payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var continuity = _workspaceServerPlane.UpsertRunboardContinuity(user, workspaceId, request, installLinking);
            return continuity is null ? NotFound() : Ok(continuity);
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

    [HttpPost("me/workspaces/{workspaceId}/campaign-adoption")]
    [ProducesResponseType<CampaignAdoptionProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignAdoptionProjection>> UpsertMyCampaignWorkspaceCampaignAdoption(
        [FromRoute] string workspaceId,
        [FromBody] CampaignAdoptionUpdateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("campaign adoption payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var adoption = _workspaceServerPlane.UpsertCampaignAdoption(user, workspaceId, request, installLinking);
            return adoption is null ? NotFound() : Ok(adoption);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentOutOfRangeException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("me/workspaces/{workspaceId}/runner-goals")]
    [ProducesResponseType<RunnerGoalProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RunnerGoalProjection>> UpsertMyCampaignWorkspaceRunnerGoal(
        [FromRoute] string workspaceId,
        [FromBody] RunnerGoalUpdateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("runner goal payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var goal = _workspaceServerPlane.UpsertRunnerGoal(user, workspaceId, request, installLinking);
            return goal is null ? NotFound() : Ok(goal);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentOutOfRangeException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("me/workspaces/{workspaceId}/resolution-report-approvals")]
    [ProducesResponseType<ResolutionReportApprovalProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ResolutionReportApprovalProjection>> ApproveMyCampaignWorkspaceResolutionReport(
        [FromRoute] string workspaceId,
        [FromBody] ResolutionReportApprovalRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("resolution report approval payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var approval = _workspaceServerPlane.ApproveResolutionReport(user, workspaceId, request, installLinking);
            return approval is null ? NotFound() : Ok(approval);
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

    [HttpPost("me/workspaces/{workspaceId}/open-runs")]
    [ProducesResponseType<OpenRunListingProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<OpenRunListingProjection>> CreateMyCampaignWorkspaceOpenRun(
        [FromRoute] string workspaceId,
        [FromBody] OpenRunCreateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("open run payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.CreateOpenRun(user, workspaceId, request, installLinking));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentOutOfRangeException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("me/open-runs/{openRunId}/join-requests")]
    [ProducesResponseType<OpenRunJoinRequestProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<OpenRunJoinRequestProjection>> SubmitMyOpenRunJoinRequest(
        [FromRoute] string openRunId,
        [FromBody] OpenRunJoinRequestCommand? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("open run join request payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.SubmitOpenRunJoinRequest(user, openRunId, request, installLinking));
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

    [HttpPost("me/open-runs/{openRunId}/join-requests/{requestId}/reviews")]
    [ProducesResponseType<OpenRunJoinRequestProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<OpenRunJoinRequestProjection>> ReviewMyOpenRunJoinRequest(
        [FromRoute] string openRunId,
        [FromRoute] string requestId,
        [FromBody] OpenRunJoinReviewRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("open run join review payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.ReviewOpenRunJoinRequest(user, openRunId, requestId, request, installLinking));
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

    [HttpPost("me/open-runs/{openRunId}/schedule")]
    [ProducesResponseType<OpenRunScheduleReceiptProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<OpenRunScheduleReceiptProjection>> ScheduleMyOpenRun(
        [FromRoute] string openRunId,
        [FromBody] OpenRunScheduleRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("open run schedule payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.ScheduleOpenRun(user, openRunId, request, installLinking));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException or ArgumentOutOfRangeException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("me/open-runs/{openRunId}/meeting-handoff")]
    [ProducesResponseType<OpenRunMeetingHandoffProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<OpenRunMeetingHandoffProjection>> CreateMyOpenRunMeetingHandoff(
        [FromRoute] string openRunId,
        [FromBody] OpenRunMeetingHandoffRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("open run meeting handoff payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.CreateOpenRunMeetingHandoff(user, openRunId, request, installLinking));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException or ArgumentOutOfRangeException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("me/open-runs/{openRunId}/closeout")]
    [ProducesResponseType<OpenRunCloseoutProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<OpenRunCloseoutProjection>> CloseOutMyOpenRun(
        [FromRoute] string openRunId,
        [FromBody] OpenRunCloseoutRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("open run closeout payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.CloseOutOpenRun(user, openRunId, request, installLinking));
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

    [HttpPost("me/workspaces/{workspaceId}/federation-batches")]
    [ProducesResponseType<CampaignFederationBatchProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignFederationBatchProjection>> LaunchMyCampaignWorkspaceFederationBatch(
        [FromRoute] string workspaceId,
        [FromBody] CampaignFederationBatchRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("campaign federation payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var batch = _campaignFederation.LaunchWorkspaceFederationBatch(user, workspaceId, request, installLinking);
            if (batch is null)
            {
                return NotFound();
            }

            LocalReleaseProofLookupResult routeLookup = FindLocalReleaseProofReceipt($"/api/v1/campaign-spine/me/workspaces/{workspaceId}/federation-batches");
            RouteClaimStatus routeClaim = ResolveCampaignFederationRouteClaimStatus(
                routeLookup,
                "No current release status record is attached to this campaign federation exchange route.");

            return Ok(batch with
            {
                RouteState = routeClaim.State,
                RouteReceipt = routeClaim.RouteReceipt,
                BoundedFailureReason = routeClaim.State == "pass"
                    ? batch.BoundedFailureReason
                    : routeClaim.BoundedFailureReason,
            });
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

    [HttpPost("me/dossier-movements")]
    [ProducesResponseType<DossierMovementReceiptProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<DossierMovementReceiptProjection>> MoveMyDossier([FromBody] DossierMovementRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("dossier-movement payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_campaignSpine.MoveDossier(user, request));
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

    [HttpPost("me/roster-transfers")]
    [ProducesResponseType<RosterTransferProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<RosterTransferProjection>> TransferMyRoster([FromBody] RosterTransferRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("roster-transfer payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_campaignSpine.TransferRoster(user, request));
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

    [HttpGet("me/runs/{runId}")]
    [ProducesResponseType<RunProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RunProjection>> GetMyRun([FromRoute] string runId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var run = _campaignSpine.GetRun(user, runId, installLinking);
            return run is null ? NotFound() : Ok(run);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/runs")]
    [ProducesResponseType<IReadOnlyList<RunProjection>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<RunProjection>>> GetMyRuns(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var runs = _campaignSpine.GetAccountSummary(user, installLinking).Runs;
            return Ok(runs);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/build-handoffs")]
    [ProducesResponseType<IReadOnlyList<BuildLabHandoffProjection>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<BuildLabHandoffProjection>>> GetMyBuildLabHandoffs(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var handoffs = _campaignSpine.GetAccountSummary(user, installLinking).BuildLabHandoffs;
            return Ok(handoffs);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/build-handoffs/{handoffId}")]
    [ProducesResponseType<BuildLabHandoffProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<BuildLabHandoffProjection>> GetMyBuildLabHandoff([FromRoute] string handoffId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var handoff = _campaignSpine.GetBuildLabHandoff(user, handoffId, installLinking);
            return handoff is null ? NotFound() : Ok(handoff);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/rules/{entryId}")]
    [ProducesResponseType<RulesNavigatorAnswerProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RulesNavigatorAnswerProjection>> GetMyRulesNavigatorAnswer([FromRoute] string entryId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var answer = _campaignSpine.GetRulesNavigatorAnswer(user, entryId, installLinking);
            return answer is null ? NotFound() : Ok(answer);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/publications/{publicationId}")]
    [ProducesResponseType<CreatorPublicationProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CreatorPublicationProjection>> GetMyCreatorPublication([FromRoute] string publicationId, CancellationToken cancellationToken)
    {
        try
        {
            ApplyImportRouteParityHeaders("/api/v1/campaign-spine/me/publications/{publicationId}");
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var publication = _campaignSpine.GetCreatorPublication(user, publicationId, installLinking);
            return publication is null ? NotFound() : Ok(publication);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/publications")]
    [ProducesResponseType<IReadOnlyList<CreatorPublicationProjection>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<CreatorPublicationProjection>>> GetMyCreatorPublications(CancellationToken cancellationToken)
    {
        try
        {
            ApplyImportRouteParityHeaders("/api/v1/campaign-spine/me/publications");
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var publications = _campaignSpine.GetAccountSummary(user, installLinking).CreatorPublications;
            return Ok(publications);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    private void ApplyImportRouteParityHeaders(string route)
    {
        ImportRouteParityProofGuardSnapshot importRouteGuard = _importRouteParityProofGuard.Evaluate();
        Response.Headers["X-Chummer-Parity-Claims"] = importRouteGuard.IsCurrent ? "pass" : "review_required";
        Response.Headers["X-Chummer-Parity-Claims-Route"] = route;
        if (!importRouteGuard.IsCurrent && !string.IsNullOrWhiteSpace(importRouteGuard.ReviewRequiredReason))
        {
            Response.Headers["X-Chummer-Parity-Claims-Reason"] = importRouteGuard.ReviewRequiredReason!;
        }
    }

    private RouteClaimStatus ResolveCampaignFederationRouteClaimStatus(
        LocalReleaseProofLookupResult routeLookup,
        string boundedFailureReason)
    {
        if (!string.IsNullOrWhiteSpace(routeLookup.CurrentnessFailureReason))
        {
            return new RouteClaimStatus(
                "bounded_failure",
                null,
                $"Parity claims stay review-required because {routeLookup.CurrentnessFailureReason!.Trim().TrimEnd('.')}.");
        }

        LocalProofReceiptMatch? routeReceipt = routeLookup.ReceiptMatch;
        if (routeReceipt is null)
        {
            return new RouteClaimStatus(
                "bounded_failure",
                null,
                boundedFailureReason);
        }

        FlagshipReadinessSnapshot? readiness = _flagshipReadiness.LoadSnapshot();
        if (readiness?.MissingDesktopClientCoverage == true)
        {
            string reviewRequiredReason = readiness.DesktopClientGapSummary.Trim().TrimEnd('.');
            return new RouteClaimStatus(
                "bounded_failure",
                BuildRouteReceiptPayload(routeReceipt),
                $"Current direct route receipt is attached, but parity claims stay review-required because {reviewRequiredReason}.");
        }

        ImportRouteParityProofGuardSnapshot importRouteGuard = _importRouteParityProofGuard.Evaluate();
        if (!importRouteGuard.IsCurrent && !string.IsNullOrWhiteSpace(importRouteGuard.ReviewRequiredReason))
        {
            return new RouteClaimStatus(
                "bounded_failure",
                BuildRouteReceiptPayload(routeReceipt),
                $"Current direct route receipt is attached, but parity claims stay review-required because {importRouteGuard.ReviewRequiredReason!.Trim().TrimEnd('.')}.");
        }

        return new RouteClaimStatus(
            "pass",
            BuildRouteReceiptPayload(routeReceipt),
            null);
    }

    private MediaArtifactDocument GetPropertyquarryPropertyOrThrow(string propertyId)
    {
        if (_mediaHorizons is null)
        {
            throw new InvalidOperationException("PROPERTYQUARRY campaign-spine routes require the media artifact horizon catalog.");
        }

        return _mediaHorizons.GetPropertyquarryProperty(propertyId);
    }

    private static string BuildPropertyquarryPrepSearchAccountHref(string propertyLabel, string? workspaceId = null)
    {
        string escapedQuery = Uri.EscapeDataString(propertyLabel);
        return string.IsNullOrWhiteSpace(workspaceId)
            ? $"/account/work?prepQuery={escapedQuery}"
            : $"/account/work/workspaces/{Uri.EscapeDataString(workspaceId)}?prepQuery={escapedQuery}";
    }

    private static string BuildPropertyquarryPrepLibraryApiHref(string workspaceId, string propertyLabel)
        => $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(workspaceId)}/prep-library?queryText={Uri.EscapeDataString(propertyLabel)}";

    private static EditionStudioHeadSummary[] BuildEditionStudioHeadSummaries(AccountCampaignSummary summary)
    {
        RuleEnvironmentRef[] environments = summary.Workspaces.Select(static item => item.RuleEnvironment)
            .Concat(summary.Dossiers.Select(static item => item.RuleEnvironment))
            .Concat(summary.Restore.RecentRuleEnvironments)
            .ToArray();

        return
        [
            BuildEditionStudioHeadSummary("sr4", "SR4", "Dense veteran-first posture for legacy muscle memory and BP-era expectations.", environments),
            BuildEditionStudioHeadSummary("sr5", "SR5", "The flagship density rail where legality, explain, and veteran speed stay authored together.", environments),
            BuildEditionStudioHeadSummary("sr6", "SR6", "Campaign-approved modern rail where simplified pace stays distinct from older heads.", environments)
        ];
    }

    private static EditionStudioHeadSummary BuildEditionStudioHeadSummary(string edition, string label, string summary, IReadOnlyList<RuleEnvironmentRef> environments)
    {
        RuleEnvironmentRef[] matching = environments
            .Where(environment => string.Equals(NormalizeEditionStudioHeadId(environment.CompatibilityFingerprint), edition, StringComparison.OrdinalIgnoreCase)
                || environment.SourcePacks.Any(pack => string.Equals(NormalizeEditionStudioHeadId(pack), edition, StringComparison.OrdinalIgnoreCase)))
            .ToArray();

        return new EditionStudioHeadSummary(
            Edition: edition,
            Label: label,
            Summary: summary,
            EnvironmentCount: matching.Length,
            Fingerprints: matching.Select(static item => item.CompatibilityFingerprint).Distinct(StringComparer.OrdinalIgnoreCase).Take(3).ToArray(),
            AccountHref: $"/account/edition-studio/{edition}",
            PacketJsonHref: $"/edition-studio/packets/{edition}_head.json",
            PacketMarkdownHref: $"/edition-studio/packets/{edition}_head.md");
    }

    private static string NormalizeEditionStudioHeadId(string? candidate)
    {
        string normalized = string.IsNullOrWhiteSpace(candidate) ? string.Empty : candidate.Trim().ToLowerInvariant();
        if (normalized.Contains("sr4", StringComparison.Ordinal))
        {
            return "sr4";
        }

        if (normalized.Contains("sr5", StringComparison.Ordinal))
        {
            return "sr5";
        }

        return normalized.Contains("sr6", StringComparison.Ordinal) ? "sr6" : normalized;
    }

    private static CampaignFederationRouteReceiptProjection? BuildRouteReceiptPayload(LocalProofReceiptMatch? routeReceipt)
        => routeReceipt is null
            ? null
            : new CampaignFederationRouteReceiptProjection(
                ReceiptId: routeReceipt.ReceiptId,
                PackageId: routeReceipt.PackageId,
                MatchedRoute: routeReceipt.MatchedRoute,
                MatchMode: routeReceipt.MatchMode,
                Summary: routeReceipt.Summary,
                Envelope: ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "campaign_federation_route",
                    ownerScope: "community.campaign_federation",
                    exposureClass: ReceiptExposureClasses.PublicSafe,
                    lifecycleState: ReceiptLifecycleStates.Published,
                    evidenceRef: routeReceipt.ReceiptId,
                    reviewState: "published"));

    private LocalReleaseProofLookupResult FindLocalReleaseProofReceipt(params string?[] routeCandidates)
        => _localReleaseProof.FindReceipt(routeCandidates);

    private sealed record RouteClaimStatus(
        string State,
        CampaignFederationRouteReceiptProjection? RouteReceipt,
        string? BoundedFailureReason);

    private sealed record EditionStudioHeadSummary(
        string Edition,
        string Label,
        string Summary,
        int EnvironmentCount,
        IReadOnlyList<string> Fingerprints,
        string AccountHref,
        string PacketJsonHref,
        string PacketMarkdownHref);
}
