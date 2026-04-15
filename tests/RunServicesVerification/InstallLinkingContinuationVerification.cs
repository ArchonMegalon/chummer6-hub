using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace RunServicesVerification;

internal static class InstallLinkingContinuationVerification
{
    public static void Run()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "install-continuation", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            string downloadsRoot = Path.Combine(tempRoot, "downloads");
            Directory.CreateDirectory(downloadsRoot);
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
                Version: "0.7.1-preview",
                Channel: "preview",
                PublishedAt: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
                Downloads: [currentArtifact]);
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web)));

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(tempRoot, "install-linking-store.json"),
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(tempRoot, "support-store.json"),
                    ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "false",
                })
                .Build();

            InstallLinkingStore installStore = new(configuration, NullLogger<InstallLinkingStore>.Instance);
            SeedClaimedInstall(installStore);
            InstallLinkingService installLinking = new(installStore, configuration);
            CommunityStore communityStore = new(configuration, NullLogger<CommunityStore>.Instance);
            RewardService rewards = new(communityStore);
            SupportStore supportStore = new(configuration, NullLogger<SupportStore>.Instance);
            SupportProgressEmailWorkflowService progressEmails = new(new HttpClient(new DisabledEmailHandler()), configuration, NullLogger<SupportProgressEmailWorkflowService>.Instance);
            SupportCaseService supportCases = new(
                supportStore,
                new SupportAttachmentStorageService(configuration),
                rewards,
                progressEmails,
                NullLogger<SupportCaseService>.Instance);
            SupportCasePresentationService supportPresentation = new();
            SupportCaseProjection submitted = supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Linux update recovery",
                    Summary: "The linked install needs the reporter-ready preview.",
                    Detail: "Keep recovery on the native install rail.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ApplicationVersion: "0.7.0-preview",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Transition(
                submitted.CaseId,
                new SupportCaseTransitionRequest(
                    TargetStatus: SupportCaseStatuses.ReleasedToReporterChannel,
                    Note: "Preview 0.7.1 is ready for the reporter.",
                    FixedVersion: "0.7.1-preview",
                    FixedChannel: "preview",
                    Actor: "hub"));

            InstallLinkingController controller = new(
                identity: null!,
                accounts: null!,
                installLinking,
                new PublicReleaseManifestService(configuration),
                supportCases,
                supportPresentation)
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = new DefaultHttpContext()
                }
            };

            ActionResult<DesktopInstallNativeContinuationResponse> result = controller.ContinueClaimedInstall(
                new DesktopInstallNativeContinuationRequest("install-native", "grant-token"));
            OkObjectResult ok = result.Result as OkObjectResult
                ?? throw new InvalidOperationException("Desktop continuation should accept a valid install grant.");
            DesktopInstallNativeContinuationResponse response = ok.Value as DesktopInstallNativeContinuationResponse
                ?? throw new InvalidOperationException("Desktop continuation should return a typed continuation response.");

            VerificationAssert.Equal("install-native", response.InstallationId, "Continuation should stay bound to the claimed install.");
            VerificationAssert.True(string.Equals(response.InstalledBuildReceiptId, "receipt-old", StringComparison.Ordinal), "Continuation should cite the installed build receipt.");
            VerificationAssert.True(response.UpdateAvailable, "Continuation should mark a newer release as update-available.");
            VerificationAssert.Equal("0.7.1-preview", response.CurrentReleaseVersion, "Continuation should include current release truth.");
            VerificationAssert.True(response.SupportHref.Contains("installationId=install-native", StringComparison.Ordinal), "Support continuation should carry installation identity.");
            VerificationAssert.True(response.SupportHref.Contains("applicationVersion=0.7.1-preview", StringComparison.Ordinal), "Support continuation should carry current release version truth.");
            VerificationAssert.True(response.RollbackAction.Contains("previous installed copy", StringComparison.OrdinalIgnoreCase), "Continuation should keep rollback on the previous installed copy.");
            VerificationAssert.Equal(1, response.SupportCases.Count, "Continuation should carry linked support-case follow-through.");
            VerificationAssert.True(response.SupportCases[0].NeedsInstallUpdate, "Support follow-through should require the linked install to update before reporter verification.");

            ActionResult<DesktopInstallNativeContinuationResponse> unauthorizedResult = controller.ContinueClaimedInstall(
                new DesktopInstallNativeContinuationRequest("install-native", "wrong-token"));
            ObjectResult unauthorized = unauthorizedResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Desktop continuation should reject an invalid grant.");
            VerificationAssert.Equal(StatusCodes.Status401Unauthorized, unauthorized.StatusCode ?? 0, "Invalid desktop continuation grants should fail closed.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void SeedClaimedInstall(InstallLinkingStore store)
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-15T01:00:00Z");
        lock (store.Gate)
        {
            store.ReceiptsById["receipt-old"] = new DownloadReceiptDto(
                ReceiptId: "receipt-old",
                ArtifactId: "avalonia-linux-x64-installer",
                ArtifactLabel: "linux",
                FileName: "chummer-avalonia-linux-x64-installer.deb",
                DownloadUrl: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                Channel: "preview",
                Version: "0.7.0-preview",
                Head: "avalonia",
                Platform: "linux",
                Arch: "x64",
                Kind: "installer",
                InstallAccessClass: InstallAccessClasses.AccountRequired,
                IssuedAtUtc: now.AddHours(-4),
                UserId: "usr-native",
                SubjectId: "subject.native",
                ClaimTicketId: "ticket-native",
                ClaimCode: "AAAAA-BBBBB-CCCCC-DDDDD",
                ClaimTicketExpiresAtUtc: now.AddHours(1));
            store.InstallationsById["install-native"] = new ClaimedInstallationDto(
                InstallationId: "install-native",
                ArtifactId: "avalonia-linux-x64-installer",
                Channel: "preview",
                Version: "0.7.0-preview",
                InstallAccessClass: InstallAccessClasses.AccountRequired,
                Status: ClaimedInstallationStates.Active,
                CreatedAtUtc: now.AddHours(-3),
                UpdatedAtUtc: now.AddHours(-2),
                UserId: "usr-native",
                SubjectId: "subject.native",
                PublicKey: "public-key",
                ClaimTicketId: "ticket-native",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64",
                HostLabel: "native-linux",
                GrantId: "grant-native");
            store.GrantsById["grant-native"] = new InstallationGrantDto(
                GrantId: "grant-native",
                InstallationId: "install-native",
                Status: InstallationGrantStates.Active,
                AccessToken: "grant-token",
                IssuedAtUtc: now.AddHours(-2),
                ExpiresAtUtc: now.AddDays(1),
                UserId: "usr-native",
                SubjectId: "subject.native");
            store.PersistLocked();
        }
    }

    private sealed class DisabledEmailHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = JsonContent.Create(new { status = "disabled" })
            });
    }
}
