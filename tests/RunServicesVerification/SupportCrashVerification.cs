using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.IO;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.AI.Services.Ops;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace RunServicesVerification;

internal static class SupportCrashVerification
{
    public static async Task RunAsync()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = Path.Combine(tempRoot, "downloads"),
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(tempRoot, "support-store.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(tempRoot, "install-linking-store.json"),
                    ["FLEET_INTERNAL_API_TOKEN"] = "verify-token",
                    ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "false",
                })
                .Build();
            Directory.CreateDirectory(configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]!);
            PublicReleaseArtifactDto currentArtifact = new(
                Id: "avalonia-linux-x64-installer",
                Platform: "linux",
                Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                Sha256: "sha-current",
                SizeBytes: 42,
                Head: "avalonia",
                PlatformId: "linux",
                Arch: "x64",
                Kind: "installer",
                FileName: "chummer-avalonia-linux-x64-installer.deb",
                InstallAccessClass: InstallAccessClasses.AccountRequired);
            PublicReleaseManifestDto manifest = new(
                Version: "1.1.1",
                Channel: "preview",
                PublishedAt: DateTimeOffset.Parse("2026-04-20T00:00:00Z"),
                Downloads: [currentArtifact]);
            File.WriteAllText(
                Path.Combine(configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]!, "releases.json"),
                JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web)));

            InstallLinkingStore installStore = new(configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinkingService installLinking = new(installStore, configuration);
            CommunityStore communityStore = new(configuration, NullLogger<CommunityStore>.Instance);
            RewardService rewards = new(communityStore);
            SupportStore store = new(configuration, NullLogger<SupportStore>.Instance);
            SupportAttachmentStorageService attachments = new(configuration);
            SupportProgressEmailWorkflowService progressEmails = new(
                new HttpClient(new FakeJsonHandler(new { status = "disabled" })),
                configuration,
                NullLogger<SupportProgressEmailWorkflowService>.Instance);
            SupportCaseService supportCases = new(store, attachments, rewards, progressEmails, NullLogger<SupportCaseService>.Instance);
            SupportCasePresentationService supportPresentation = new();
            SupportConciergePacketService conciergePackets = new(new PublicReleaseManifestService(configuration), supportPresentation);
            CrashSupportService service = new(store, supportCases, installLinking, NullLogger<CrashSupportService>.Instance);
            SeedInstallationGrant(installStore, "install-verified", "usr_linked", "subject.linked", "grant-active");
            SeedInstallationGrant(installStore, "install-1", "usr_runner", "subject.runner", "grant-runner");

            CrashIntakeAcceptedResponse first = service.Submit(CreateEnvelope("crash-1", "1.0.0", "fingerprint-a"));
            CrashIntakeAcceptedResponse second = service.Submit(CreateEnvelope("crash-2", "1.1.0", "fingerprint-a"));

            VerificationAssert.Equal(first.Cluster.ClusterId, second.Cluster.ClusterId, "Matching fingerprints should reuse the same crash cluster.");
            VerificationAssert.Equal(first.WorkItem.WorkItemId, second.WorkItem.WorkItemId, "Matching fingerprints should reuse the same crash work item.");
            VerificationAssert.Equal(2, second.Cluster.OccurrenceCount, "Cluster occurrence count should aggregate incidents.");
            VerificationAssert.True(second.WorkItem.RegressionSuspected, "Multiple versions in a cluster should mark the work item as regression suspected.");
            VerificationAssert.Equal("chummer6-ui", second.WorkItem.CandidateOwnerRepo, "Desktop crash automation should route to the UI repo.");

            SupportCrashesController controller = new(service, configuration)
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = new DefaultHttpContext()
                }
            };

            ActionResult<CrashIntakeAcceptedResponse> result = controller.Submit(CreateEnvelope("crash-3", "1.1.1", "fingerprint-b"));
            AcceptedAtActionResult accepted = result.Result as AcceptedAtActionResult
                ?? throw new InvalidOperationException("Crash intake controller should return AcceptedAtAction.");
            CrashIntakeAcceptedResponse payload = accepted.Value as CrashIntakeAcceptedResponse
                ?? throw new InvalidOperationException("Crash intake controller should return a crash intake payload.");
            VerificationAssert.Equal("queued_for_triage", payload.Incident.Status, "Accepted incidents should be queued for downstream triage.");

            ActionResult<CrashWorkItemListResponse> unauthorizedList = controller.ListWorkItems(candidateOwnerRepo: "chummer6-ui");
            ObjectResult unauthorized = unauthorizedList.Result as ObjectResult
                ?? throw new InvalidOperationException("Crash work-item list should deny unauthorized access.");
            VerificationAssert.True(unauthorized.StatusCode == StatusCodes.Status401Unauthorized, "Crash work-item list should require internal auth.");

            controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer verify-token";
            CrashClusterListResponse filteredClusters = (controller.ListClusters(fingerprint: "fingerprint-a").Result as OkObjectResult)?.Value as CrashClusterListResponse
                ?? throw new InvalidOperationException("Authorized crash cluster list should return a typed payload.");
            VerificationAssert.Equal(1, filteredClusters.TotalCount, "Fingerprint filtering should isolate the expected cluster.");

            CrashWorkItemListResponse filteredWorkItems = (controller.ListWorkItems(candidateOwnerRepo: "chummer6-ui").Result as OkObjectResult)?.Value as CrashWorkItemListResponse
                ?? throw new InvalidOperationException("Authorized crash work-item list should return a typed payload.");
            VerificationAssert.True(filteredWorkItems.TotalCount >= 2, "Owner filtering should keep desktop crash work items visible.");

            service.Submit(CreateEnvelope(
                "crash-linked",
                "1.1.2",
                "fingerprint-linked",
                installationId: "install-verified",
                installationGrantToken: "grant-active",
                userId: "usr_forged",
                subjectId: "subject.forged"));
            SupportCaseProjection linkedCrashCase = supportCases.ListForReporter("usr_linked", "subject.linked", kind: SupportCaseKinds.CrashReport).Items
                .Single(static item => string.Equals(item.ApplicationVersion, "1.1.2", StringComparison.Ordinal));
            VerificationAssert.True(string.Equals(linkedCrashCase.ReporterUserId, "usr_linked", StringComparison.Ordinal), "Crash intake should derive reporter identity from the installation grant, not the client payload.");
            VerificationAssert.True(string.Equals(linkedCrashCase.ReporterSubjectId, "subject.linked", StringComparison.Ordinal), "Crash intake should derive reporter subject from Hub install truth.");

            service.Submit(CreateEnvelope(
                "crash-forged",
                "1.1.3",
                "fingerprint-forged",
                installationId: "install-verified",
                installationGrantToken: "invalid-token",
                userId: "usr_linked",
                subjectId: "subject.linked"));
            SupportCaseProjection anonymousCrashCase = supportCases.ListForAutomation(kind: SupportCaseKinds.CrashReport).Items
                .Single(static item => string.Equals(item.ApplicationVersion, "1.1.3", StringComparison.Ordinal));
            VerificationAssert.True(string.IsNullOrWhiteSpace(anonymousCrashCase.ReporterUserId), "Crash intake should drop reporter identity when the install grant cannot be verified.");
            VerificationAssert.True(string.IsNullOrWhiteSpace(anonymousCrashCase.ReporterSubjectId), "Crash intake should drop reporter subject when the install grant cannot be verified.");
            VerificationAssert.True(string.IsNullOrWhiteSpace(anonymousCrashCase.InstallationId), "Crash intake should drop installation linkage when the install grant cannot be verified.");

            SupportCaseProjection submittedCase = supportCases.Submit(
                reporterUserId: "usr_runner",
                reporterSubjectId: "subject.runner",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.BugReport,
                    Title: "Updater note is confusing",
                    Summary: "Release copy does not explain the staged restart clearly.",
                    Detail: "The page should explain what was staged and whether the update already downloaded.\n\nInstalled build receipt: receipt-install-1",
                    InstallationId: "install-1",
                    ApplicationVersion: "1.1.0",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            VerificationAssert.Equal("chummer6-hub", submittedCase.CandidateOwnerRepo, "Install/update/account bug reports should route to the Hub-owned front door by default.");
            VerificationAssert.True(submittedCase.DesignImpactSuspected, "Confusing-copy reports should mark design-impact suspicion.");

            SupportCaseProjection distinctCase = supportCases.Submit(
                reporterUserId: "usr_runner",
                reporterSubjectId: "subject.runner",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.BugReport,
                    Title: "Updater note is confusing",
                    Summary: "The account page says apply now.",
                    Detail: "This is a different issue with the same title.",
                    InstallationId: "install-1",
                    ApplicationVersion: "1.1.1",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            VerificationAssert.True(!string.Equals(distinctCase.CaseId, submittedCase.CaseId, StringComparison.Ordinal), "Support-case clustering should not collapse distinct summaries under the same title.");

            SupportCaseProjection desktopBugCase = supportCases.Submit(
                reporterUserId: "usr_runner",
                reporterSubjectId: "subject.runner",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.BugReport,
                    Title: "Desktop save fails",
                    Summary: "Saving a character throws immediately.",
                    Detail: "The desktop editor crashes during save.",
                    InstallationId: "install-2",
                    ApplicationVersion: "1.1.2",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            VerificationAssert.Equal("chummer6-ui", desktopBugCase.CandidateOwnerRepo, "Desktop runtime bug reports should still route to the UI owner.");

            SupportCaseListResponse reporterCases = supportCases.ListForReporter("usr_runner", "subject.runner");
            VerificationAssert.Equal(3, reporterCases.TotalCount, "Reporter-scoped support lists should include all distinct submitted cases.");

            bool blockedDirectNotify = false;
            try
            {
                supportCases.Transition(
                    submittedCase.CaseId,
                    new SupportCaseTransitionRequest(
                        TargetStatus: SupportCaseStatuses.UserNotified,
                        Note: "This should fail.",
                        Actor: "fleet"));
            }
            catch (InvalidOperationException)
            {
                blockedDirectNotify = true;
            }
            VerificationAssert.True(blockedDirectNotify, "Direct transition to user_notified should be blocked; callers must use the notification hook.");

            SupportCaseProjection released = supportCases.Transition(
                submittedCase.CaseId,
                new SupportCaseTransitionRequest(
                    TargetStatus: SupportCaseStatuses.ReleasedToReporterChannel,
                    Note: "Fix landed in preview 1.1.1.",
                    FixedVersion: "1.1.1",
                    FixedChannel: "preview",
                    Actor: "fleet"));
            VerificationAssert.Equal(SupportCaseStatuses.ReleasedToReporterChannel, released.Status, "Release-to-reporter-channel should be a first-class support status.");

            SupportCaseProjection notified = supportCases.RecordNotification(
                submittedCase.CaseId,
                new SupportCaseNotificationRequest(
                    Note: "Reporter notified that preview 1.1.1 contains the fix.",
                    Actor: "hub",
                    Channel: "account_history"));
            VerificationAssert.Equal(SupportCaseStatuses.UserNotified, notified.Status, "Notification hooks should move the case into user_notified.");
            VerificationAssert.True(notified.UserNotifiedAtUtc.HasValue, "Notification hooks should stamp the notification time.");

            InstallAwareSupportConciergePacket conciergePacket = conciergePackets.Build(
                notified,
                installLinking.GetSummary("usr_runner", "subject.runner"));
            VerificationAssert.Equal("chummer6-hub.install_aware_support_concierge.v1", conciergePacket.ContractName, "M111 support concierge packet should publish a stable contract name.");
            VerificationAssert.Equal("next90-m111-hub-support-concierge", conciergePacket.PackageId, "M111 support concierge packet should cite the assigned package.");
            VerificationAssert.True(conciergePacket.IsInstallAware, "Support concierge packet should require installed build, channel, device, and support-case truth.");
            VerificationAssert.Equal("receipt-install-1", conciergePacket.InstalledBuildTruth.InstalledBuildReceiptId ?? string.Empty, "Support concierge packet should carry the installed-build receipt from support truth.");
            VerificationAssert.Equal("1.1.0", conciergePacket.InstalledBuildTruth.ApplicationVersion ?? string.Empty, "Support concierge packet should preserve the affected installed build.");
            VerificationAssert.Equal("preview", conciergePacket.InstalledBuildTruth.ReleaseChannel ?? string.Empty, "Support concierge packet should preserve the affected installed channel.");
            VerificationAssert.Equal("avalonia-linux-x64-installer", conciergePacket.ReleaseTruth.CurrentArtifactId ?? string.Empty, "Release explainer packet should resolve the current published artifact for the install.");
            VerificationAssert.True(conciergePacket.ReleaseTruth.ChannelAgreesWithInstalledBuild, "Release explainer packet should prove channel agreement before public wrapper promotion.");
            VerificationAssert.True(!conciergePacket.SupportClosure.ClosureReadiness.ReporterCanClose, "Support closure packet should not mark reporter closure ready before the fixed release is installed.");
            VerificationAssert.True(conciergePacket.SupportClosure.ClosureReadiness.ReleaseArtifactReady, "Support closure readiness should require a published artifact URL and checksum.");
            VerificationAssert.True(conciergePacket.SupportClosure.ClosureReadiness.BlockerSummary.Contains("update before trying the fix again", StringComparison.Ordinal), "Support closure readiness should explain the install update blocker as structured truth.");
            VerificationAssert.True(conciergePacket.ReleaseExplainer.InstalledToReleaseDelta.VersionChanges, "Release explainer delta should show the reporter is moving from the installed build to the fixed release.");
            VerificationAssert.True(conciergePacket.ReleaseExplainer.InstalledToReleaseDelta.ArtifactMatchesInstalledDevice, "Release explainer delta should prove the resolved artifact matches the installed head, platform, and architecture.");
            VerificationAssert.True(conciergePacket.SupportClosure.FirstPartyRoutes.Contains("/api/v1/install-linking/continuation/support"), "Support closure packet should keep native support follow-through in first-party routes.");
            VerificationAssert.True(conciergePacket.ReleaseExplainer.CorrectnessBasis.Contains("receipt-install-1", StringComparison.Ordinal), "Release explainer packet should cite installed-build receipt truth.");
            VerificationAssert.True(conciergePacket.PublicTrustWrapper.FirstPartyOnlyTruth, "Public wrapper must not become the source of installed-build or support-case truth.");

            SupportCaseProjection installBackedCase = supportCases.Submit(
                "usr_runner",
                "subject.runner",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Installer support case with claimed install tuple",
                    Summary: "Reporter attached the affected install but omitted duplicate device tuple fields.",
                    Detail: "Installed build receipt: receipt-claimed-install-only",
                    InstallationId: "install-1",
                    Source: SupportCaseSourceKinds.HubAccount));
            InstallAwareSupportConciergePacket installBackedPacket = conciergePackets.Build(
                installBackedCase,
                installLinking.GetSummary("usr_runner", "subject.runner"));
            VerificationAssert.True(installBackedPacket.IsInstallAware, "M111 concierge packets should compile install awareness from resolved claimed-install truth when the support case carries the affected installation id.");
            VerificationAssert.Equal("1.1.2", installBackedPacket.InstalledBuildTruth.ApplicationVersion ?? string.Empty, "Claimed-install truth should fill the installed version when support intake omits duplicate version fields.");
            VerificationAssert.Equal("avalonia", installBackedPacket.InstalledBuildTruth.HeadId ?? string.Empty, "Claimed-install truth should fill the desktop head when support intake omits duplicate device fields.");
            VerificationAssert.Equal("linux", installBackedPacket.InstalledBuildTruth.Platform ?? string.Empty, "Claimed-install truth should fill the platform when support intake omits duplicate device fields.");
            VerificationAssert.Equal("x64", installBackedPacket.InstalledBuildTruth.Arch ?? string.Empty, "Claimed-install truth should fill the architecture when support intake omits duplicate device fields.");
            VerificationAssert.Equal("receipt-claimed-install-only", installBackedPacket.InstalledBuildTruth.InstalledBuildReceiptId ?? string.Empty, "Claimed-install-backed concierge packets should still carry the installed-build receipt from support detail.");

            SupportCaseProjection receiptlessInstallCase = supportCases.Submit(
                "usr_runner",
                "subject.runner",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Installer support case without installed-build receipt",
                    Summary: "Reporter attached an install but the signed installed-build receipt did not arrive.",
                    Detail: "Reporter attached install context but no installed build receipt marker.",
                    InstallationId: "install-1",
                    Source: SupportCaseSourceKinds.HubAccount));
            InstallAwareSupportConciergePacket receiptlessInstallPacket = conciergePackets.Build(
                receiptlessInstallCase,
                installLinking.GetSummary("usr_runner", "subject.runner"));
            VerificationAssert.True(!receiptlessInstallPacket.IsInstallAware, "M111 concierge packets must not treat claimed install tuple fields as install-aware truth without an installed-build receipt id.");
            VerificationAssert.True(!receiptlessInstallPacket.SupportClosure.ClosureReadiness.InstalledBuildComplete, "M111 support closure must block tuple-only install context until installed-build receipt truth is present.");
            VerificationAssert.True(receiptlessInstallPacket.SupportClosure.ClosureReadiness.BlockerSummary.Contains("installed build truth is incomplete", StringComparison.Ordinal), "M111 support closure should explain receiptless installed-build truth as incomplete.");

            SupportCaseProjection placeholderReceiptCase = supportCases.Submit(
                "usr_runner",
                "subject.runner",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Installer support case with placeholder receipt",
                    Summary: "Reporter attached the affected install but the receipt id was still a placeholder.",
                    Detail: "Installed build receipt: missing-installed-build-receipt",
                    InstallationId: "install-1",
                    Source: SupportCaseSourceKinds.HubAccount));
            InstallAwareSupportConciergePacket placeholderReceiptPacket = conciergePackets.Build(
                placeholderReceiptCase,
                installLinking.GetSummary("usr_runner", "subject.runner"));
            VerificationAssert.True(!placeholderReceiptPacket.IsInstallAware, "M111 concierge packets must not treat placeholder installed-build receipt ids as signed installed-build truth.");
            VerificationAssert.True(!placeholderReceiptPacket.SupportClosure.ClosureReadiness.InstalledBuildComplete, "M111 support closure must block placeholder installed-build receipt ids.");
            VerificationAssert.True(placeholderReceiptPacket.SupportClosure.ClosureReadiness.BlockerSummary.Contains("installed build truth is incomplete", StringComparison.Ordinal), "M111 support closure should explain placeholder receipt truth as incomplete.");

            SupportCaseProjection crossChannelCase = supportCases.Transition(
                installBackedCase.CaseId,
                new SupportCaseTransitionRequest(
                    TargetStatus: SupportCaseStatuses.ReleasedToReporterChannel,
                    Note: "Fix landed in a different release channel.",
                    FixedVersion: "1.2.0",
                    FixedChannel: "stable",
                    Actor: "fleet"));
            InstallAwareSupportConciergePacket crossChannelPacket = conciergePackets.Build(
                crossChannelCase,
                installLinking.GetSummary("usr_runner", "subject.runner"));
            VerificationAssert.True(!crossChannelPacket.ReleaseTruth.ChannelAgreesWithInstalledBuild, "M111 release concierge channel agreement must compare the installed channel to fixed release truth before falling back to manifest channel.");
            VerificationAssert.True(crossChannelPacket.SupportClosure.ClosureReadiness.BlockerSummary.Contains("installed channel and release channel do not agree", StringComparison.Ordinal), "M111 support closure should block reporter closure when fixed release channel differs from the installed channel.");

            SupportCaseProjection unlinkedCase = supportCases.Submit(
                "usr_runner",
                "subject.runner",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.Feedback,
                    Title: "Release copy question",
                    Summary: "Reporter asks about release notes without attaching an install.",
                    Detail: "No installed build detail was attached.",
                    Source: SupportCaseSourceKinds.HubAccount));
            InstallAwareSupportConciergePacket unlinkedPacket = conciergePackets.Build(
                unlinkedCase,
                installLinking.GetSummary("usr_runner", "subject.runner"));
            VerificationAssert.True(!unlinkedPacket.IsInstallAware, "M111 concierge packets must not treat unknown labels or manifest fallback as installed-build truth.");
            VerificationAssert.True(!unlinkedPacket.ReleaseTruth.ChannelAgreesWithInstalledBuild, "M111 release concierge must not claim channel agreement when the installed channel is missing.");
            VerificationAssert.True(unlinkedPacket.SupportClosure.ClosureReadiness.BlockerSummary.Contains("installed build truth is incomplete", StringComparison.Ordinal), "M111 support closure should block closure when installed build truth is incomplete.");

            SupportStore reloadedStore = new(configuration, NullLogger<SupportStore>.Instance);
            SupportAttachmentStorageService reloadedAttachments = new(configuration);
            CommunityStore reloadedCommunityStore = new(configuration, NullLogger<CommunityStore>.Instance);
            RewardService reloadedRewards = new(reloadedCommunityStore);
            SupportProgressEmailWorkflowService reloadedProgressEmails = new(
                new HttpClient(new FakeJsonHandler(new { status = "disabled" })),
                configuration,
                NullLogger<SupportProgressEmailWorkflowService>.Instance);
            SupportCaseService reloadedSupportCases = new(reloadedStore, reloadedAttachments, reloadedRewards, reloadedProgressEmails, NullLogger<SupportCaseService>.Instance);
            InstallLinkingStore reloadedInstallStore = new(configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinkingService reloadedInstallLinking = new(reloadedInstallStore, configuration);
            CrashSupportService reloadedService = new(reloadedStore, reloadedSupportCases, reloadedInstallLinking, NullLogger<CrashSupportService>.Instance);
            CrashIncidentProjection? reloadedIncident = reloadedService.GetIncident(first.Incident.IncidentId);
            VerificationAssert.NotNull(reloadedIncident, "Persisted crash incidents should reload from durable storage.");
            SupportCaseProjection? reloadedSupportCase = reloadedSupportCases.GetForReporter(submittedCase.CaseId, "usr_runner", "subject.runner");
            VerificationAssert.NotNull(reloadedSupportCase, "Persisted support cases should reload from durable storage.");

            HttpClient clientHttp = new(new FakeJsonHandler(new CrashWorkItemListResponse(
                Items: [second.WorkItem],
                TotalCount: 1)))
            {
                BaseAddress = new Uri("http://hub.example/")
            };
            clientHttp.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", "verify-token");
            HubCrashAutomationClient client = new(clientHttp);
            CrashWorkItemListResponse aiProjection = await client.ListCrashWorkItemsAsync(status: null, candidateOwnerRepo: "chummer6-ui", CancellationToken.None);
            VerificationAssert.Equal(1, aiProjection.TotalCount, "AI crash automation client should parse Hub work-item projections.");
            VerificationAssert.Equal(second.WorkItem.WorkItemId, aiProjection.Items[0].WorkItemId, "AI crash automation client should preserve work-item identity.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static CrashEnvelope CreateEnvelope(
        string crashId,
        string version,
        string fingerprint,
        string? installationId = null,
        string? installationGrantToken = null,
        string? userId = null,
        string? subjectId = null)
        => new(
            CrashId: crashId,
            HeadId: "avalonia",
            ApplicationVersion: version,
            RuntimeVersion: ".NET 10",
            OperatingSystem: "Linux",
            ProcessArchitecture: "X64",
            CrashFingerprint: fingerprint,
            ExceptionType: "System.InvalidOperationException",
            ExceptionMessage: "boom",
            ExceptionDetail: "System.InvalidOperationException: boom\n   at Verification.Sample()",
            CapturedAtUtc: DateTimeOffset.UtcNow,
            ReleaseChannel: "stable",
            Platform: "linux",
            DesktopHead: "avalonia",
            RuntimeHead: "desktop-runtime",
            InstallationId: installationId,
            InstallationGrantToken: installationGrantToken,
            UserId: userId,
            SubjectId: subjectId,
            LastActionCategory: "startup",
            LogTail: ["boom", "stack line"]);

    private static void SeedInstallationGrant(
        InstallLinkingStore store,
        string installationId,
        string userId,
        string subjectId,
        string accessToken)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        lock (store.Gate)
        {
            ClaimedInstallationDto installation = new(
                InstallationId: installationId,
                ArtifactId: "artifact-linux",
                Channel: "preview",
                Version: "1.1.2",
                InstallAccessClass: InstallAccessClasses.AccountRecommended,
                Status: ClaimedInstallationStates.Active,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                UserId: userId,
                SubjectId: subjectId,
                PublicKey: "public-key",
                ClaimTicketId: $"ticket-{installationId}",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64",
                HostLabel: "verify-host",
                GrantId: $"grant-{installationId}");
            InstallationGrantDto grant = new(
                GrantId: $"grant-{installationId}",
                InstallationId: installationId,
                Status: InstallationGrantStates.Active,
                AccessToken: accessToken,
                IssuedAtUtc: now.AddMinutes(-5),
                ExpiresAtUtc: now.AddDays(1),
                UserId: userId,
                SubjectId: subjectId);
            store.InstallationsById[installationId] = installation;
            store.GrantsById[grant.GrantId] = grant;
            store.PersistLocked();
        }
    }

    private sealed class FakeJsonHandler : HttpMessageHandler
    {
        private readonly object _payload;

        public FakeJsonHandler(object payload)
        {
            _payload = payload;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string json = JsonSerializer.Serialize(_payload);
            HttpResponseMessage response = new(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            };
            return Task.FromResult(response);
        }
    }
}
