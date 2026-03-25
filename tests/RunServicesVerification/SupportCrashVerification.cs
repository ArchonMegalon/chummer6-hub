using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.IO;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.Contracts.InstallLinking;
using Chummer.Run.Contracts.Support;
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
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(tempRoot, "support-store.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(tempRoot, "install-linking-store.json"),
                    ["FLEET_INTERNAL_API_TOKEN"] = "verify-token",
                })
                .Build();

            InstallLinkingStore installStore = new(configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinkingService installLinking = new(installStore);
            SupportStore store = new(configuration, NullLogger<SupportStore>.Instance);
            SupportCaseService supportCases = new(store, NullLogger<SupportCaseService>.Instance);
            CrashSupportService service = new(store, supportCases, installLinking, NullLogger<CrashSupportService>.Instance);
            SeedInstallationGrant(installStore, "install-verified", "usr_linked", "subject.linked", "grant-active");

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
                    Detail: "The page should explain what was staged and whether the update already downloaded.",
                    InstallationId: "install-1",
                    ApplicationVersion: "1.1.0",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            VerificationAssert.Equal("chummer6-ui", submittedCase.CandidateOwnerRepo, "Bug reports should route to the UI owner by default.");
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

            SupportCaseListResponse reporterCases = supportCases.ListForReporter("usr_runner", "subject.runner");
            VerificationAssert.Equal(2, reporterCases.TotalCount, "Reporter-scoped support lists should include all distinct submitted cases.");

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

            SupportStore reloadedStore = new(configuration, NullLogger<SupportStore>.Instance);
            SupportCaseService reloadedSupportCases = new(reloadedStore, NullLogger<SupportCaseService>.Instance);
            InstallLinkingStore reloadedInstallStore = new(configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinkingService reloadedInstallLinking = new(reloadedInstallStore);
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
                ClaimTicketId: "ticket-1",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64",
                HostLabel: "verify-host",
                GrantId: "grant-1");
            InstallationGrantDto grant = new(
                GrantId: "grant-1",
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
