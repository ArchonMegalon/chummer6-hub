using Xunit;

namespace Chummer.Tests;

public sealed class VerificationEntryPointTests
{
    [Fact]
    public void AuditComplianceUsesSupportedVerificationScript()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "audit-compliance.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("bash scripts/ai/verify.sh", script, StringComparison.Ordinal);
    }

    [Fact]
    public void ParityChecklistGeneratorFailClosesMalformedParityTokens()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "generate-parity-checklist.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("normalize_required_token", script, StringComparison.Ordinal);
        Assert.Contains("parse_required_token_list", script, StringComparison.Ordinal);
        Assert.Contains("parse_catalog_token_matches", script, StringComparison.Ordinal);
        Assert.Contains("must not contain blank token values", script, StringComparison.Ordinal);
        Assert.Contains("contains whitespace-padded token", script, StringComparison.Ordinal);
        Assert.Contains("contains duplicate normalized token", script, StringComparison.Ordinal);
    }

    [Fact]
    public void SupportVerificationGuardAvoidsUnmatchedInstallFallback()
    {
        string presenterPath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Support", "SupportCasePresentationService.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "SupportCasesController.cs");

        string presenter = File.ReadAllText(presenterPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("best is not null && best.Score > 0", presenter, StringComparison.Ordinal);
        Assert.Contains("AllowsReporterVerification", controller, StringComparison.Ordinal);
        Assert.Contains("presented.CanVerifyFix", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInTrustProjectionSuppressesIdentityOutages()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("TryGetOptionalPublicSurfaceSubjectAsync", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInReleaseUploadHandoffIsPublishedFromPortal()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ReleaseUpload.cshtml");
        string bootstrapPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
        string wrapperPath = RepoPaths.FromRoot("scripts", "run-mac-release-bootstrap.sh");
        string maintenanceReadmePath = RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "maintenance", "MAC_CODEX_RELEASE_TO_CHUMMER_RUN.md");
        string presentationRunbookPath = RepoPaths.FromRoot("..", "chummer-presentation", "docs", "MAC_CODEX_RELEASE_TO_CHUMMER_RUN.md");
        string publicReadmePath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "artifacts", "mac-codex-release-pipeline", "readme.md");

        string controller = File.ReadAllText(controllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string view = File.ReadAllText(viewPath);
        string bootstrap = File.ReadAllText(bootstrapPath);
        string wrapper = File.ReadAllText(wrapperPath);
        string maintenanceReadme = File.ReadAllText(maintenanceReadmePath);
        string presentationRunbook = File.ReadAllText(presentationRunbookPath);
        string publicReadme = File.ReadAllText(publicReadmePath);

        Assert.Contains("/downloads/release-upload", controller, StringComparison.Ordinal);
        Assert.Contains("/downloads/release-upload/bootstrap.sh", controller, StringComparison.Ordinal);
        Assert.Contains("bash <(curl -fsSL", controller, StringComparison.Ordinal);
        Assert.Contains("ReleaseUploadTicketService", controller, StringComparison.Ordinal);
        Assert.Contains("ReleaseUploadPageViewModel", viewModel, StringComparison.Ordinal);
        Assert.Contains("Signed-in release upload", view, StringComparison.Ordinal);
        Assert.Contains("operator source of truth", view, StringComparison.Ordinal);
        Assert.Contains("claim code", view, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_TOKEN", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_URL", bootstrap, StringComparison.Ordinal);
        Assert.Contains("log_bootstrap_identity", bootstrap, StringComparison.Ordinal);
        Assert.Contains("bootstrap source:", bootstrap, StringComparison.Ordinal);
        Assert.Contains("bootstrap template not found", wrapper, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", wrapper, StringComparison.Ordinal);
        Assert.Contains("artifacts/mac-codex-release-pipeline/bootstrap.sh", wrapper, StringComparison.Ordinal);
        Assert.DoesNotContain("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh", wrapper, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", maintenanceReadme, StringComparison.Ordinal);
        Assert.Contains("run-mac-release-bootstrap.sh", maintenanceReadme, StringComparison.Ordinal);
        Assert.DoesNotContain("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh", maintenanceReadme, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", presentationRunbook, StringComparison.Ordinal);
        Assert.Contains("run-mac-release-bootstrap.sh", presentationRunbook, StringComparison.Ordinal);
        Assert.DoesNotContain("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh", presentationRunbook, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", publicReadme, StringComparison.Ordinal);
        Assert.Contains("run-mac-release-bootstrap.sh", publicReadme, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_MAC_RELEASE_MIN_FREE_GIB", publicReadme, StringComparison.Ordinal);
    }

    [Fact]
    public void MacDownloadsUseBootstrapScriptHandoffInsteadOfRawDmgDefault()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string downloadsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "DownloadsCompatibilityController.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "ReleaseSelectionService.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string downloadsViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string dispatchViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string downloadsController = File.ReadAllText(downloadsControllerPath);
        string service = File.ReadAllText(servicePath);
        string viewModel = File.ReadAllText(viewModelPath);
        string downloadsView = File.ReadAllText(downloadsViewPath);
        string dispatchView = File.ReadAllText(dispatchViewPath);

        Assert.Contains("/downloads/install/{artifactId}/bootstrap.command", controller, StringComparison.Ordinal);
        Assert.Contains("/downloads/install/{artifactId}/bootstrap.ps1", controller, StringComparison.Ordinal);
        Assert.Contains("/downloads/install/{artifactId}/bootstrap.sh", controller, StringComparison.Ordinal);
        Assert.Contains("RenderMacInstallBootstrapScript", controller, StringComparison.Ordinal);
        Assert.Contains("RenderWindowsInstallBootstrapScript", controller, StringComparison.Ordinal);
        Assert.Contains("RenderLinuxInstallBootstrapScript", controller, StringComparison.Ordinal);
        Assert.Contains("asks which Chummer apps to install and where to put them", controller, StringComparison.Ordinal);
        Assert.Contains("The Mac setup assistant offers Auto select", controller, StringComparison.Ordinal);
        Assert.Contains("The Windows setup assistant offers Auto select", controller, StringComparison.Ordinal);
        Assert.Contains("The Linux setup assistant offers Auto select", controller, StringComparison.Ordinal);
        Assert.Contains("whether to leave quick access in Applications only or add Desktop links", controller, StringComparison.Ordinal);
        Assert.Contains("verifies that linking actually completed", controller, StringComparison.Ordinal);
        Assert.Contains("Each selected app is started once through a short-lived environment handoff", controller, StringComparison.Ordinal);
        Assert.Contains("verify_download_digest", controller, StringComparison.Ordinal);
        Assert.Contains("perform_staged_install", controller, StringComparison.Ordinal);
        Assert.Contains("launch_bundle_binary_with_claim", controller, StringComparison.Ordinal);
        Assert.Contains("ConvertFrom-Json", controller, StringComparison.Ordinal);
        Assert.Contains("--bootstrap-install", controller, StringComparison.Ordinal);
        Assert.Contains("dpkg-deb -x", controller, StringComparison.Ordinal);
        Assert.Contains("resolve_install_state_root", controller, StringComparison.Ordinal);
        Assert.Contains("build_install_state_path", controller, StringComparison.Ordinal);
        Assert.Contains("read_install_state_field", controller, StringComparison.Ordinal);
        Assert.Contains("wait_for_claim_success", controller, StringComparison.Ordinal);
        Assert.Contains("Confirmed linked installs", controller, StringComparison.Ordinal);
        Assert.Contains("create_desktop_link", controller, StringComparison.Ordinal);
        Assert.Contains("run_privileged_script", controller, StringComparison.Ordinal);
        Assert.Contains("Current Mac architecture", controller, StringComparison.Ordinal);
        Assert.Contains("open -n \\\"$target_app\\\" >/dev/null 2>&1 || true", controller, StringComparison.Ordinal);
        Assert.Contains("kill \\\"$launch_pid\\\"", controller, StringComparison.Ordinal);
        Assert.Contains("wait \\\"$launch_pid\\\" >/dev/null 2>&1 || true", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("copies them to your clipboard", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("xattr -dr com.apple.quarantine", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("--install-claim-code", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("pkill -f \"$target_app/Contents/MacOS\"", controller, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_INSTALL_CLAIM_CODE", controller, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_API_BASE_URL", controller, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_WEB_BASE_URL", controller, StringComparison.Ordinal);
        Assert.Contains("InstallBootstrapTicketService", controller, StringComparison.Ordinal);
        Assert.Contains("QueryString.Create(\"ticket\"", controller, StringComparison.Ordinal);
        Assert.Contains("invalid_or_expired_install_ticket", controller, StringComparison.Ordinal);
        Assert.Contains("claimCode", controller, StringComparison.Ordinal);
        Assert.Contains("invalid_or_expired_claim_code", downloadsController, StringComparison.Ordinal);
        Assert.Contains("UsesMacBootstrapScript", service, StringComparison.Ordinal);
        Assert.Contains("visible_as_account_gated_setup_script_preview", service, StringComparison.Ordinal);
        Assert.Contains("DetectPreferredArchitecture", service, StringComparison.Ordinal);
        Assert.Contains("guided Mac setup assistant", service, StringComparison.Ordinal);
        Assert.Contains("verifies the published DMG digest", service, StringComparison.Ordinal);
        Assert.Contains("macOS (Apple Silicon)", service, StringComparison.Ordinal);
        Assert.Contains("BootstrapScriptDownload", viewModel, StringComparison.Ordinal);
        Assert.Contains("TerminalInstallCommand", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandLabel", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandIntro", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandNote", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapFeatureCards", viewModel, StringComparison.Ordinal);
        Assert.Contains("CurrentReleaseSummary", viewModel, StringComparison.Ordinal);
        Assert.Contains("AutoStartDownload", viewModel, StringComparison.Ordinal);
        Assert.DoesNotContain("downloads-quicknav", downloadsView, StringComparison.Ordinal);
        Assert.Contains("Advanced download options", downloadsView, StringComparison.Ordinal);
        Assert.Contains("copy the Terminal command", downloadsView, StringComparison.Ordinal);
        Assert.Contains("BuildMacBootstrapTerminalCommand", controller, StringComparison.Ordinal);
        Assert.Contains("ResolveClaimTicketForDownload", controller, StringComparison.Ordinal);
        Assert.Contains("Copy install command", dispatchView, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandIntro", dispatchView, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandLabel", dispatchView, StringComparison.Ordinal);
        Assert.Contains("BootstrapFeatureCards", dispatchView, StringComparison.Ordinal);
        Assert.Contains("CurrentReleaseSummary", dispatchView, StringComparison.Ordinal);
        Assert.Contains("Fallbacks and recovery", dispatchView, StringComparison.Ordinal);
        Assert.Contains("Setup highlights", dispatchView, StringComparison.Ordinal);
        Assert.Contains("Recovery claim code", dispatchView, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicTrustPulsePanel.cshtml", dispatchView, StringComparison.Ordinal);
        Assert.Contains("if (autoStartDownload)", dispatchView, StringComparison.Ordinal);
        Assert.Contains("SecondaryDownloadLabel", dispatchView, StringComparison.Ordinal);
        Assert.Contains("RebindDownloadsHeaderActions", controller, StringComparison.Ordinal);
        Assert.Contains("GuestGateSecondaryHref", controller, StringComparison.Ordinal);
        Assert.Contains("GuestGatePrimaryHref", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void MacReleaseBootstrapSupportsCleanStockMacLayouts()
    {
        string bootstrapPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
        string bootstrap = File.ReadAllText(bootstrapPath);

        Assert.Contains("ensure_dotnet_resolver", bootstrap, StringComparison.Ordinal);
        Assert.Contains("$HOME/.dotnet", bootstrap, StringComparison.Ordinal);
        Assert.Contains("dotnet --list-sdks", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_LOCAL_CAMPAIGN_CONTRACTS_PROJECT", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_LOCAL_HUB_REGISTRY_CONTRACTS_PROJECT", bootstrap, StringComparison.Ordinal);
        Assert.Contains("chummer6-media-factory.git", bootstrap, StringComparison.Ordinal);
        Assert.Contains("validate_publish_mode", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_TOKEN", bootstrap, StringComparison.Ordinal);
        Assert.Contains("[[ \"${#app_heads[@]}\" -eq 0 ]]", bootstrap, StringComparison.Ordinal);
        Assert.Contains("upload_release_bundle_http()", bootstrap, StringComparison.Ordinal);
        Assert.Contains("write_public_promotion_evidence()", bootstrap, StringComparison.Ordinal);
        Assert.Contains("require_min_free_space_gib", bootstrap, StringComparison.Ordinal);
        Assert.Contains("log_disk_space", bootstrap, StringComparison.Ordinal);
        Assert.Contains("hdiutil create for signed repack", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_MAC_RELEASE_MIN_FREE_GIB", bootstrap, StringComparison.Ordinal);
        Assert.DoesNotContain("scripts/generate-public-promotion-evidence.py", bootstrap, StringComparison.Ordinal);
        Assert.DoesNotContain("bash scripts/publish-download-bundle-http.sh", bootstrap, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeComposePinsHttpsPortForLocalChummerRunRedirects()
    {
        string composePath = RepoPaths.FromRoot("docker-compose.public-edge.yml");
        string compose = File.ReadAllText(composePath);

        Assert.Contains("ASPNETCORE_HTTPS_PORT", compose, StringComparison.Ordinal);
        Assert.Contains("${ASPNETCORE_HTTPS_PORT:-443}", compose, StringComparison.Ordinal);
    }

    [Fact]
    public void HubLiveAuditSupportsReverseProxiedLocalEdgeMode()
    {
        string auditPath = RepoPaths.FromRoot("scripts", "hub-live-audit.py");
        string audit = File.ReadAllText(auditPath);

        Assert.Contains("--public-host", audit, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto", audit, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", audit, StringComparison.Ordinal);
        Assert.Contains("X-Forwarded-Proto", audit, StringComparison.Ordinal);
        Assert.Contains("Accept-Language", audit, StringComparison.Ordinal);
        Assert.Contains("Cache-Control", audit, StringComparison.Ordinal);
        Assert.Contains("Pragma", audit, StringComparison.Ordinal);
    }

    [Fact]
    public void HubCloseoutAndE2EUseReverseProxiedLocalEdgeAudit()
    {
        string closeoutPath = RepoPaths.FromRoot("scripts", "ai", "hub_closeout.sh");
        string e2ePath = RepoPaths.FromRoot("scripts", "e2e-hub.sh");
        string cleanupPath = RepoPaths.FromRoot("scripts", "cleanup_synthetic_support_cases.py");
        string closeout = File.ReadAllText(closeoutPath);
        string e2e = File.ReadAllText(e2ePath);
        string cleanup = File.ReadAllText(cleanupPath);

        Assert.Contains("HUB_PUBLIC_HOST", closeout, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto https", closeout, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", closeout, StringComparison.Ordinal);
        Assert.Contains("hub-live-audit.py", e2e, StringComparison.Ordinal);
        Assert.Contains("wait_for_hub_edge", e2e, StringComparison.Ordinal);
        Assert.Contains("--public-host \"$HUB_PUBLIC_HOST\"", e2e, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_HUB_PLAYWRIGHT_FORWARDED_PROTO", e2e, StringComparison.Ordinal);
        Assert.Contains("HUB_PUBLIC_HOST", e2e, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto https", e2e, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", e2e, StringComparison.Ordinal);
        Assert.Contains("--public-host", cleanup, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto", cleanup, StringComparison.Ordinal);
        Assert.Contains("X-Forwarded-Proto", cleanup, StringComparison.Ordinal);
    }

    [Fact]
    public void PortalE2EUsesReverseProxiedLocalEdgeHeaders()
    {
        string shellPath = RepoPaths.FromRoot("scripts", "e2e-portal.sh");
        string nodePath = RepoPaths.FromRoot("scripts", "e2e-portal.cjs");

        string shell = File.ReadAllText(shellPath);
        string node = File.ReadAllText(nodePath);

        Assert.Contains("wait_for_portal_edge", shell, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_PUBLIC_HOST", shell, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_FORWARDED_PROTO", shell, StringComparison.Ordinal);
        Assert.Contains("X-Forwarded-Proto", node, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_PUBLIC_HOST", node, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_FORWARDED_PROTO", node, StringComparison.Ordinal);
    }

    [Fact]
    public void HubRequestObservabilityIsWiredIntoProgramAndVerification()
    {
        string programPath = RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs");
        string identityProgramPath = RepoPaths.FromRoot("Chummer.Run.Identity", "Program.cs");
        string verificationProgramPath = RepoPaths.FromRoot("tests", "RunServicesVerification", "Program.cs");
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");
        string middlewarePath = RepoPaths.FromRoot("Chummer.Run.Api", "HubRequestObservabilityMiddleware.cs");

        string program = File.ReadAllText(programPath);
        string identityProgram = File.ReadAllText(identityProgramPath);
        string verificationProgram = File.ReadAllText(verificationProgramPath);
        string backlog = File.ReadAllText(backlogPath);
        string middleware = File.ReadAllText(middlewarePath);

        Assert.Contains("AddHubRequestObservability", program, StringComparison.Ordinal);
        Assert.Contains("UseHubRequestObservability", program, StringComparison.Ordinal);
        Assert.Contains("HubRequestObservabilityVerification.RunAsync", verificationProgram, StringComparison.Ordinal);
        Assert.Contains("MIG-091", backlog, StringComparison.Ordinal);
        Assert.Contains("Response.OnStarting", middleware, StringComparison.Ordinal);
        Assert.Contains("IDENTITY_ENABLE_HTTPS_REDIRECTION", identityProgram, StringComparison.Ordinal);
    }

    [Fact]
    public void NowPageSurfacesCampaignOsLocalProof()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string controller = File.ReadAllText(controllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("CampaignOsLocalProofService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("CampaignOsProof: _campaignOsProof.LoadProof()", controller, StringComparison.Ordinal);
        Assert.Contains("CampaignOsLocalProofSnapshot? CampaignOsProof", viewModel, StringComparison.Ordinal);
        Assert.Contains("Campaign OS local proof", view, StringComparison.Ordinal);
        Assert.Contains("Source-backed local smoke contract", view, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicTrustPagesSurfaceWeeklyPulseAndCaution()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicTrustPulseService.cs");
        string pulseArtifactServicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "WeeklyProductPulseArtifactService.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicTrustPulsePanel.cshtml");
        string bodyPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicTrustPulseBody.cshtml");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string service = File.ReadAllText(servicePath);
        string pulseArtifactService = File.ReadAllText(pulseArtifactServicePath);
        string controller = File.ReadAllText(controllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string partial = File.ReadAllText(partialPath);
        string body = File.ReadAllText(bodyPath);

        Assert.Contains("PublicTrustPulseService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("WeeklyProductPulseArtifactService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("LoadWeeklyPulseJson", service, StringComparison.Ordinal);
        Assert.Contains("WEEKLY_PRODUCT_PULSE.generated.json", pulseArtifactService, StringComparison.Ordinal);
        Assert.Contains("BuildPublicTrustPulsePanel", controller, StringComparison.Ordinal);
        Assert.Contains("PublicTrustPulsePanelViewModel? TrustPulse", viewModel, StringComparison.Ordinal);
        Assert.Contains("PublicTrustPulseTrendPointViewModel", viewModel, StringComparison.Ordinal);
        Assert.Contains("Weekly trust pulse", partial, StringComparison.Ordinal);
        Assert.Contains("trust-pulse-trend", body, StringComparison.Ordinal);
        Assert.Contains("Current caution", controller, StringComparison.Ordinal);
        Assert.Contains("Closure health", controller, StringComparison.Ordinal);
        Assert.Contains("Progress trend", controller, StringComparison.Ordinal);
        Assert.Contains("BuildTrustPulseProgressTrendSummary", controller, StringComparison.Ordinal);
        Assert.Contains("BuildTrustPulseTrendSamples", controller, StringComparison.Ordinal);
        Assert.Contains("BuildTrustPulseClosureHealthSummary", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountSurfaceReusesSignedInTrustStatusProjection()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "SignedInTrustStatusService.cs");
        string publicControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string accountViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string service = File.ReadAllText(servicePath);
        string publicController = File.ReadAllText(publicControllerPath);
        string accountController = File.ReadAllText(accountControllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string accountView = File.ReadAllText(accountViewPath);
        string landingView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));
        string faqView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml"));
        string storyView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ProductStory.cshtml"));
        string participateView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"));
        string horizonsView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Horizons.cshtml"));
        string shelfView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml"));
        string featureDetailView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeatureDetail.cshtml"));
        string downloadDispatchView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml"));
        string homeView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml"));
        string supportSubmittedView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml"));

        Assert.Contains("SignedInTrustStatusService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("Who can get it now", service, StringComparison.Ordinal);
        Assert.Contains("_signedInTrustStatus.Build", publicController, StringComparison.Ordinal);
        Assert.Contains("_signedInTrustStatus.Build", accountController, StringComparison.Ordinal);
        Assert.Contains("SignedInTrustStatusPanelViewModel? SignedInTrustStatus", viewModel, StringComparison.Ordinal);
        Assert.Contains("SignedInTrustStatusPanelViewModel? SignedInStatus", viewModel, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", accountView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", landingView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", faqView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", storyView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", participateView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", horizonsView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", shelfView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", featureDetailView, StringComparison.Ordinal);
        Assert.DoesNotContain("_SignedInTrustStatusPanel.cshtml", downloadDispatchView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", homeView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", supportSubmittedView, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicProgressControllerPublishesWeeklyPulseArtifact()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicProgressController.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicProgressService.cs");
        string auditPath = RepoPaths.FromRoot("scripts", "hub-live-audit.py");

        string controller = File.ReadAllText(controllerPath);
        string service = File.ReadAllText(servicePath);
        string audit = File.ReadAllText(auditPath);

        Assert.Contains("/api/public/weekly-pulse", controller, StringComparison.Ordinal);
        Assert.Contains("LoadWeeklyPulseJson", service, StringComparison.Ordinal);
        Assert.Contains("/api/public/weekly-pulse", audit, StringComparison.Ordinal);
        Assert.Contains("chummer.weekly_product_pulse", audit, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicTrustPagesPublishPrivacyBoundaryArtifact()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicProgressController.cs");
        string landingControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicPrivacyBoundaryService.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PrivacyBoundaryPanel.cshtml");
        string accountViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string auditPath = RepoPaths.FromRoot("scripts", "hub-live-audit.py");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string controller = File.ReadAllText(controllerPath);
        string landingController = File.ReadAllText(landingControllerPath);
        string accountController = File.ReadAllText(accountControllerPath);
        string service = File.ReadAllText(servicePath);
        string viewModel = File.ReadAllText(viewModelPath);
        string partial = File.ReadAllText(partialPath);
        string accountView = File.ReadAllText(accountViewPath);
        string audit = File.ReadAllText(auditPath);

        Assert.Contains("PublicPrivacyBoundaryService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("/api/public/privacy-boundaries", controller, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"privacy\")", landingController, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"help\")", landingController, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"contact\")", landingController, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"account\")", accountController, StringComparison.Ordinal);
        Assert.Contains("PRIVACY_AND_RETENTION_BOUNDARIES.md", service, StringComparison.Ordinal);
        Assert.Contains("PUBLIC_TRUST_CONTENT.yaml", service, StringComparison.Ordinal);
        Assert.Contains("PrivacyBoundaryPanelViewModel? PrivacyBoundary", viewModel, StringComparison.Ordinal);
        Assert.Contains("Retention window:", partial, StringComparison.Ordinal);
        Assert.Contains("Model.PrivacyBoundary", accountView, StringComparison.Ordinal);
        Assert.Contains("/api/public/privacy-boundaries", audit, StringComparison.Ordinal);
        Assert.Contains("chummer.public_privacy_boundaries", audit, StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseWorkflowPublishesApiAndDownloadsMirrorArtifacts()
    {
        string workflowPath = RepoPaths.FromRoot(".github", "workflows", "desktop-downloads-matrix.yml");
        string docsPath = RepoPaths.FromRoot("docs", "ACTIVE_HEAD_RELEASE_ARTIFACTS.md");

        string workflow = File.ReadAllText(workflowPath);
        string docs = File.ReadAllText(docsPath);

        Assert.Contains("- main", workflow, StringComparison.Ordinal);
        Assert.Contains("name: Public Edge Release Artifacts", workflow, StringComparison.Ordinal);
        Assert.Contains("name: release-api-portable", workflow, StringComparison.Ordinal);
        Assert.Contains("Stage public downloads mirror", workflow, StringComparison.Ordinal);
        Assert.Contains("desktop-download-bundle", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Avalonia/Chummer.Avalonia.csproj", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Blazor.Desktop/Chummer.Blazor.Desktop.csproj", workflow, StringComparison.Ordinal);
        Assert.Contains("release-api-portable", docs, StringComparison.Ordinal);
        Assert.Contains("checked-in public download mirror", docs, StringComparison.Ordinal);
        Assert.Contains("desktop-download-bundle", docs, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeGuardrailsDoNotReferenceMissingPortalProject()
    {
        string workflowPath = RepoPaths.FromRoot(".github", "workflows", "docker-architecture-guardrails.yml");
        string composePath = RepoPaths.FromRoot("legacy", "tooling", "docker", "docker-compose.yml");
        string runbookPath = RepoPaths.FromRoot("scripts", "runbook.sh");
        string migrationLoopPath = RepoPaths.FromRoot("scripts", "migration-loop.sh");
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");

        string workflow = File.ReadAllText(workflowPath);
        string compose = File.ReadAllText(composePath);
        string runbook = File.ReadAllText(runbookPath);
        string migrationLoop = File.ReadAllText(migrationLoopPath);
        string backlog = File.ReadAllText(backlogPath);

        Assert.DoesNotContain("Chummer.Portal/Chummer.Portal.csproj", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Portal/appsettings.json", runbook, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api/Chummer.Run.Api.csproj", workflow, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api/Dockerfile", compose, StringComparison.Ordinal);
        Assert.Contains("chummer.run:host-gateway", compose, StringComparison.Ordinal);
        Assert.Contains("PublicLandingController.cs", runbook, StringComparison.Ordinal);
        Assert.DoesNotContain("chummer-blazor", migrationLoop, StringComparison.Ordinal);
        Assert.Contains("docker-compose.public-edge.yml", migrationLoop, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PORTAL_DEV_AUTH_ENABLED", backlog, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PORTAL_REQUIRE_AUTH", backlog, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api", backlog, StringComparison.Ordinal);
    }

    [Fact]
    public void WorkspaceBenchmarkGuardrailsAreOwnedByCoreEngineRepo()
    {
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");
        string boundaryPath = RepoPaths.FromRoot("docs", "HOSTED_BOUNDARY.md");
        string coreEngineRoot = Path.GetFullPath(Path.Combine(RepoPaths.Root, "..", "chummer-core-engine"));
        string benchmarkWorkflowPath = Path.Combine(coreEngineRoot, ".github", "workflows", "benchmark-guardrails.yml");
        string benchmarkBudgetPath = Path.Combine(coreEngineRoot, "Chummer.Benchmarks", "workspace-benchmark-budgets.json");

        string backlog = File.ReadAllText(backlogPath);
        string boundary = File.ReadAllText(boundaryPath);

        Assert.Contains("- [x] `MIG-095`", backlog, StringComparison.Ordinal);
        Assert.Contains("../chummer-core-engine/Chummer.Benchmarks", backlog, StringComparison.Ordinal);
        Assert.Contains("Chummer.Benchmarks", boundary, StringComparison.Ordinal);
        Assert.True(File.Exists(benchmarkWorkflowPath), "Core engine owner repo should publish the benchmark CI workflow.");
        Assert.True(File.Exists(benchmarkBudgetPath), "Core engine owner repo should publish benchmark budgets.");
    }
}
