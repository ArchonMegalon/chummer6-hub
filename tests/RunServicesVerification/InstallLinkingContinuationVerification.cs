using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
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
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Different desktop install",
                    Summary: "Another device should not follow this claimed install.",
                    Detail: "Support continuation should not attach unrelated install-help cases by reporter alone.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-other",
                    ApplicationVersion: "0.7.0-preview",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            SupportCaseProjection channelOnlySubmitted = supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Generic preview install help",
                    Summary: "Channel-only install help should not follow this device.",
                    Detail: "The continuation rail needs install-specific context before attaching support follow-through.",
                    ReporterEmail: "runner@example.invalid",
                    ReleaseChannel: "preview",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Transition(
                channelOnlySubmitted.CaseId,
                new SupportCaseTransitionRequest(
                    TargetStatus: SupportCaseStatuses.ReleasedToReporterChannel,
                    Note: "Generic preview help has no installed build or device truth.",
                    FixedVersion: "0.7.1-preview",
                    FixedChannel: "preview",
                    Actor: "hub"));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Generic preview build help",
                    Summary: "Version-only install help should not follow this device.",
                    Detail: "The continuation rail needs a claimed install id or device tuple before attaching support follow-through.",
                    ReporterEmail: "runner@example.invalid",
                    ApplicationVersion: "0.7.0-preview",
                    ReleaseChannel: "preview",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Install id only legacy help",
                    Summary: "A bare install id should not be enough to continue support on this claimed device.",
                    Detail: "Support continuation needs installed build and device truth before attaching follow-through.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Stale same install help",
                    Summary: "Same install id with a different installed build should not follow this device.",
                    Detail: "Support continuation should reject contradictory install truth even when the case cites the claimed install id.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ApplicationVersion: "0.6.9-preview",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Wrong platform same install help",
                    Summary: "Same install id with a different desktop platform should not follow this device.",
                    Detail: "Support continuation should reject contradictory device truth even when the case cites the claimed install id.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ApplicationVersion: "0.7.0-preview",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Head-only same install help",
                    Summary: "Same install id with only desktop head truth should not follow this device.",
                    Detail: "Support continuation should require complete desktop device truth before attaching follow-through.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ApplicationVersion: "0.7.0-preview",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Platform-only same install help",
                    Summary: "Same install id with only platform truth should not follow this device.",
                    Detail: "Support continuation should require head, platform, and architecture truth before attaching follow-through.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ApplicationVersion: "0.7.0-preview",
                    ReleaseChannel: "preview",
                    Platform: "linux",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Version-only same install help",
                    Summary: "Same install id with the full device tuple but no channel should not follow this device.",
                    Detail: "Support continuation needs both installed version and release channel before attaching follow-through.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ApplicationVersion: "0.7.0-preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.InstallHelp,
                    Title: "Channel-only same install help",
                    Summary: "Same install id with the full device tuple but no version should not follow this device.",
                    Detail: "Support continuation needs installed-build truth, not only channel and device truth.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            supportCases.Submit(
                "usr-native",
                "subject.native",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.BugReport,
                    Title: "Matching non-install desktop bug",
                    Summary: "A bug report with matching install truth should stay out of install continuation.",
                    Detail: "The desktop-native install rail must not attach non-install support kinds even when device truth matches.",
                    ReporterEmail: "runner@example.invalid",
                    InstallationId: "install-native",
                    ApplicationVersion: "0.7.0-preview",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));

            IReadOnlyList<SupportCasePresentationViewModel> accountSupportRail = supportPresentation.BuildList(
                supportCases.ListForReporter("usr-native", "subject.native").Items,
                installLinking.GetSummary("usr-native", "subject.native"));
            SupportCasePresentationViewModel channelOnlyHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Generic preview install help", StringComparison.Ordinal));
            SupportCasePresentationViewModel versionOnlyHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Generic preview build help", StringComparison.Ordinal));
            SupportCasePresentationViewModel installIdOnlyHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Install id only legacy help", StringComparison.Ordinal));
            SupportCasePresentationViewModel staleSameInstallHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Stale same install help", StringComparison.Ordinal));
            SupportCasePresentationViewModel wrongPlatformSameInstallHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Wrong platform same install help", StringComparison.Ordinal));
            SupportCasePresentationViewModel headOnlySameInstallHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Head-only same install help", StringComparison.Ordinal));
            SupportCasePresentationViewModel platformOnlySameInstallHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Platform-only same install help", StringComparison.Ordinal));
            SupportCasePresentationViewModel versionOnlySameInstallHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Version-only same install help", StringComparison.Ordinal));
            SupportCasePresentationViewModel channelOnlySameInstallHelp = accountSupportRail.First(item => string.Equals(item.Case.Title, "Channel-only same install help", StringComparison.Ordinal));
            VerificationAssert.True(channelOnlyHelp.NeedsLinkedInstall, "Account support readiness should not attach channel-only install help to the current claimed desktop install.");
            VerificationAssert.True(!channelOnlyHelp.PrimaryActionHref.StartsWith("/account/access", StringComparison.OrdinalIgnoreCase), "Channel-only install help should not route reporter-ready support follow-through into Devices and access without installed build and device truth.");
            VerificationAssert.True(versionOnlyHelp.NeedsLinkedInstall, "Account support readiness should not attach version-only install help to the current claimed desktop install.");
            VerificationAssert.True(installIdOnlyHelp.NeedsLinkedInstall, "Account support readiness should not attach install-id-only help without installed build and device truth.");
            VerificationAssert.True(staleSameInstallHelp.NeedsLinkedInstall, "Account support readiness should reject same-install support with contradictory installed-build truth.");
            VerificationAssert.True(wrongPlatformSameInstallHelp.NeedsLinkedInstall, "Account support readiness should reject same-install support with contradictory device truth.");
            VerificationAssert.True(headOnlySameInstallHelp.NeedsLinkedInstall, "Account support readiness should reject same-install support without complete desktop device truth.");
            VerificationAssert.True(platformOnlySameInstallHelp.NeedsLinkedInstall, "Account support readiness should reject platform-only support without complete desktop device truth.");
            VerificationAssert.True(versionOnlySameInstallHelp.NeedsLinkedInstall, "Account support readiness should reject same-install support that has device truth but no release channel.");
            VerificationAssert.True(channelOnlySameInstallHelp.NeedsLinkedInstall, "Account support readiness should reject same-install support that has device truth but no installed version.");

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
            VerificationAssert.True(response.InstalledBuildReceiptId != "receipt-same-artifact-newer-version", "Continuation should not attach an artifact-id receipt unless installed build truth matches.");
            VerificationAssert.True(response.InstalledBuildReceiptId != "receipt-other-platform", "Continuation should not attach a newer receipt from another desktop platform.");
            VerificationAssert.True(response.UpdateAvailable, "Continuation should mark a newer release as update-available.");
            VerificationAssert.Equal("0.7.1-preview", response.CurrentReleaseVersion, "Continuation should include current release truth.");
            VerificationAssert.True(response.FallbackPosture.Contains("Claim codes are a recovery fallback", StringComparison.Ordinal), "Continuation should expose fallback posture so desktop, support, and download surfaces agree.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", response.NativePrimaryActionHref, "Claimed desktop continuation should send update-ready follow-through directly to the grant-bound native update planner.");
            VerificationAssert.True(!response.NativePrimaryActionHref.StartsWith("/account/", StringComparison.Ordinal), "Claimed desktop continuation primary action should not send the app through the account browser rail.");
            VerificationAssert.True(!response.NativePrimaryActionHref.StartsWith("/downloads", StringComparison.Ordinal), "Claimed desktop continuation primary action should not send the app through the downloads browser rail.");
            VerificationAssert.True(!response.NativePrimaryActionHref.StartsWith("/contact", StringComparison.Ordinal), "Claimed desktop continuation primary action should not send the app through the public support browser rail.");
            VerificationAssert.True(response.SupportHref.StartsWith("/account/support?", StringComparison.Ordinal), "Claimed desktop continuation should keep support follow-through inside Account > Support.");
            VerificationAssert.True(!response.SupportHref.StartsWith("/contact", StringComparison.Ordinal), "Claimed desktop continuation should not fall back to the public contact browser ritual.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", response.NativeUpdateHref, "Claimed desktop continuation should expose a grant-bound native update planner instead of requiring a browser update ritual.");
            VerificationAssert.True(!response.NativeUpdateHref.StartsWith("/account/", StringComparison.Ordinal), "Claimed desktop continuation should not send update through the account browser rail.");
            VerificationAssert.True(!response.NativeUpdateHref.StartsWith("/downloads", StringComparison.Ordinal), "Claimed desktop continuation should not send update through the downloads browser rail.");
            VerificationAssert.True(!response.NativeUpdateHref.StartsWith("/contact", StringComparison.Ordinal), "Claimed desktop continuation should not send update through the public support browser rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", response.NativeSupportHref, "Claimed desktop continuation should expose a grant-bound native support intake instead of requiring a browser support ritual.");
            VerificationAssert.True(response.SupportHref.Contains("installationId=install-native", StringComparison.Ordinal), "Support continuation should carry installation identity.");
            VerificationAssert.True(response.SupportHref.Contains("applicationVersion=0.7.0-preview", StringComparison.Ordinal), "Support continuation should prefill the affected installed build.");
            VerificationAssert.True(response.SupportHref.Contains("installedBuildReceiptId=receipt-old", StringComparison.Ordinal), "Support continuation should prefill the affected installed-build receipt.");
            VerificationAssert.True(response.CurrentReleaseVersion == "0.7.1-preview", "Support continuation response should still carry current release version truth.");
            VerificationAssert.True(response.RollbackAction.Contains("previous installed copy", StringComparison.OrdinalIgnoreCase), "Continuation should keep rollback on the previous installed copy.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/rollback", response.NativeRollbackHref, "Claimed desktop continuation should expose a grant-bound native rollback planner instead of requiring a browser rollback ritual.");
            VerificationAssert.True(!response.NativeRollbackHref.StartsWith("/account/", StringComparison.Ordinal), "Claimed desktop continuation should not send rollback through the account browser rail.");
            VerificationAssert.True(!response.NativeRollbackHref.StartsWith("/downloads", StringComparison.Ordinal), "Claimed desktop continuation should not send rollback through the downloads browser rail.");
            VerificationAssert.True(!response.NativeRollbackHref.StartsWith("/contact", StringComparison.Ordinal), "Claimed desktop continuation should not send rollback through the public support browser rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", response.NativeRecoveryHref, "Claimed desktop continuation should keep recovery on the grant-bound continuation rail instead of a browser claim-code ritual.");
            VerificationAssert.True(response.RecoveryAction.Contains("desktop app", StringComparison.OrdinalIgnoreCase) || response.RecoveryAction.Contains("grant-bound continuation rail", StringComparison.OrdinalIgnoreCase), "Claimed desktop continuation should describe recovery as app-native continuation.");
            VerificationAssert.Equal(1, response.SupportCases.Count, "Continuation should carry linked support-case follow-through.");
            string matchingNonInstallBugCaseId = supportCases
                .ListForReporter("usr-native", "subject.native")
                .Items
                .First(supportCase => string.Equals(supportCase.Title, "Matching non-install desktop bug", StringComparison.Ordinal))
                .CaseId;
            VerificationAssert.True(
                !response.SupportCases.Any(item => string.Equals(item.CaseId, matchingNonInstallBugCaseId, StringComparison.Ordinal)),
                "Continuation should not attach non-install support kinds even when claimed install truth matches.");
            VerificationAssert.Equal("install-native", response.SupportCases[0].InstallationId, "Support follow-through should stay bound to the same claimed install.");
            VerificationAssert.Equal("0.7.0-preview", response.SupportCases[0].ApplicationVersion, "Support follow-through should expose installed build version truth.");
            VerificationAssert.Equal("preview", response.SupportCases[0].ReleaseChannel, "Support follow-through should expose installed channel truth.");
            VerificationAssert.Equal("avalonia", response.SupportCases[0].HeadId, "Support follow-through should expose installed head truth.");
            VerificationAssert.Equal("linux", response.SupportCases[0].Platform, "Support follow-through should expose installed platform truth.");
            VerificationAssert.Equal("x64", response.SupportCases[0].Arch, "Support follow-through should expose installed architecture truth.");
            VerificationAssert.True(string.Equals(response.SupportCases[0].InstalledBuildReceiptId, "receipt-old", StringComparison.Ordinal), "Support follow-through should cite the installed build receipt.");
            VerificationAssert.True(response.SupportCases[0].NeedsInstallUpdate, "Support follow-through should require the linked install to update before reporter verification.");
            VerificationAssert.True(response.SupportCases[0].NextSafeAction.Contains("grant-bound native update planner", StringComparison.Ordinal), "Native support follow-through should describe update verification as a desktop-native action.");
            VerificationAssert.True(!response.SupportCases[0].NextSafeAction.Contains("Open Devices", StringComparison.OrdinalIgnoreCase), "Native support follow-through should not tell the desktop app to open Devices and access.");
            VerificationAssert.True(!response.SupportCases[0].NextSafeAction.Contains("Open downloads", StringComparison.OrdinalIgnoreCase), "Native support follow-through should not tell the desktop app to open downloads.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", response.SupportCases[0].PrimaryActionHref, "Native support follow-through should route update-ready cases to the grant-bound native update planner.");
            VerificationAssert.True(!response.SupportCases[0].PrimaryActionHref.StartsWith("/account/", StringComparison.Ordinal), "Native support follow-through should not send the desktop app through the account browser rail.");
            VerificationAssert.True(!response.SupportCases[0].PrimaryActionHref.StartsWith("/downloads", StringComparison.Ordinal), "Native support follow-through should not send the desktop app through the downloads browser rail.");
            VerificationAssert.True(!response.SupportCases[0].PrimaryActionHref.StartsWith("/contact", StringComparison.Ordinal), "Native support follow-through should not send the desktop app through the public support browser rail.");
            VerificationAssert.Equal("0.7.1-preview", response.SupportCases[0].CurrentReleaseVersion, "Case-level support follow-through should carry current release version truth.");
            VerificationAssert.Equal("preview", response.SupportCases[0].CurrentReleaseChannel, "Case-level support follow-through should carry current release channel truth.");
            VerificationAssert.Equal("avalonia-linux-x64-installer", response.SupportCases[0].CurrentArtifactId ?? string.Empty, "Case-level support follow-through should carry current artifact truth.");
            VerificationAssert.True(response.SupportCases[0].FallbackPosture.Contains("Claim codes are a recovery fallback", StringComparison.Ordinal), "Case-level support follow-through should keep fallback posture beside the case.");
            VerificationAssert.True(response.SupportCases[0].UpdateAvailable, "Case-level support follow-through should tell the app when the linked install needs an update.");
            VerificationAssert.True(response.SupportCases[0].UpdateAction.Contains("grant-bound support follow-through", StringComparison.Ordinal), "Case-level support follow-through should keep update instructions inside the native support rail.");
            VerificationAssert.True(response.SupportCases[0].RollbackAction.Contains("previous installed copy", StringComparison.OrdinalIgnoreCase), "Case-level support follow-through should keep rollback on the previous installed copy.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", response.SupportCases[0].NativeContinuationHref, "Case-level support follow-through should return to the grant-bound continuation rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", response.SupportCases[0].NativeSupportHref, "Case-level support follow-through should keep support on the grant-bound native endpoint.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", response.SupportCases[0].NativeUpdateHref, "Case-level support follow-through should keep update on the grant-bound native planner.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/rollback", response.SupportCases[0].NativeRollbackHref, "Case-level support follow-through should keep rollback on the grant-bound native planner.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", response.SupportCases[0].NativeRecoveryHref, "Case-level support follow-through should keep recovery on the grant-bound continuation rail.");
            VerificationAssert.True(response.SupportCases[0].RecoveryAction.Contains("desktop app", StringComparison.OrdinalIgnoreCase) || response.SupportCases[0].RecoveryAction.Contains("grant-bound continuation rail", StringComparison.OrdinalIgnoreCase), "Case-level support follow-through should describe recovery without a browser ritual.");
            VerificationAssert.True(!response.SupportCases[0].NativeUpdateHref.StartsWith("/downloads", StringComparison.Ordinal), "Case-level support follow-through should not send update through the downloads browser rail.");
            VerificationAssert.True(!response.SupportCases[0].NativeSupportHref.StartsWith("/contact", StringComparison.Ordinal), "Case-level support follow-through should not send support through the public support browser rail.");
            VerificationAssert.True(!response.SupportCases[0].NativeRollbackHref.StartsWith("/account/", StringComparison.Ordinal), "Case-level support follow-through should not send rollback through the account browser rail.");

            PublicReleaseManifestDto wrongPlatformManifest = manifest with
            {
                Downloads =
                [
                    currentArtifact with
                    {
                        Id = "avalonia-win-x64-installer",
                        Platform = "windows",
                        PlatformId = "windows",
                        FileName = "chummer-avalonia-win-x64-installer.exe"
                    }
                ]
            };
            ClaimedInstallationDto claimedInstall = (installLinking.GetSummary("usr-native", "subject.native")
                .ClaimedInstallations ?? Array.Empty<ClaimedInstallationDto>())
                .First(item => string.Equals(item.InstallationId, "install-native", StringComparison.Ordinal));
            PublicReleaseArtifactDto? wrongPlatformFallback = ResolveContinuationArtifactForVerification(wrongPlatformManifest, claimedInstall with
            {
                ArtifactId = "missing-linux-artifact"
            });
            VerificationAssert.True(wrongPlatformFallback is null, "Continuation artifact fallback should not choose a same-head artifact when platform or architecture truth contradicts the claimed install.");

            ActionResult<DesktopInstallNativeSupportResponse> nativeSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app install recovery",
                    Summary: "The app needs support without opening a browser ritual.",
                    Detail: "This was filed from the claimed desktop app after continuation.",
                    RequestedActionHref: "/downloads?from=desktop-support"));
            ObjectResult nativeSupportAccepted = nativeSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, nativeSupportAccepted.StatusCode ?? 0, "Native support continuation should create a tracked support case without a browser form.");
            DesktopInstallNativeSupportResponse nativeSupport = nativeSupportAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed support response.");
            VerificationAssert.Equal("install-native", nativeSupport.InstallationId, "Native support continuation should bind the case to the claimed install.");
            VerificationAssert.Equal("0.7.0-preview", nativeSupport.ApplicationVersion, "Native support continuation should carry installed build truth.");
            VerificationAssert.Equal("preview", nativeSupport.ReleaseChannel, "Native support continuation should carry installed channel truth.");
            VerificationAssert.Equal("avalonia", nativeSupport.HeadId, "Native support continuation should carry installed head truth.");
            VerificationAssert.Equal("linux", nativeSupport.Platform, "Native support continuation should carry installed platform truth.");
            VerificationAssert.Equal("x64", nativeSupport.Arch, "Native support continuation should carry installed architecture truth.");
            VerificationAssert.True(string.Equals(nativeSupport.InstalledBuildReceiptId, "receipt-old", StringComparison.Ordinal), "Native support continuation should echo the installed-build receipt truth back to the desktop app.");
            VerificationAssert.Equal("0.7.1-preview", nativeSupport.CurrentReleaseVersion, "Native support continuation should keep current release version truth available after filing support.");
            VerificationAssert.Equal("preview", nativeSupport.CurrentReleaseChannel, "Native support continuation should keep current release channel truth available after filing support.");
            VerificationAssert.True(string.Equals(nativeSupport.CurrentArtifactId, "avalonia-linux-x64-installer", StringComparison.Ordinal), "Native support continuation should keep current artifact truth available after filing support.");
            VerificationAssert.True(nativeSupport.FallbackPosture.Contains("Claim codes are a recovery fallback", StringComparison.Ordinal), "Native support continuation should keep fallback posture available after filing support.");
            VerificationAssert.True(nativeSupport.UpdateAvailable, "Native support continuation should tell the app whether the claimed install still needs an update.");
            VerificationAssert.True(nativeSupport.UpdateAction.Contains("Update this linked install from preview 0.7.0-preview to preview 0.7.1-preview", StringComparison.Ordinal), "Native support continuation should keep update instructions on the claimed install rail after filing support.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", nativeSupport.NativeUpdateHref, "Native support continuation should keep update on the grant-bound native update planner after filing support.");
            VerificationAssert.True(!nativeSupport.NativeUpdateHref.StartsWith("/account/", StringComparison.Ordinal), "Native support continuation should not send update through the account browser rail after filing support.");
            VerificationAssert.True(!nativeSupport.NativeUpdateHref.StartsWith("/downloads", StringComparison.Ordinal), "Native support continuation should not send update through the downloads browser rail after filing support.");
            VerificationAssert.True(!nativeSupport.NativeUpdateHref.StartsWith("/contact", StringComparison.Ordinal), "Native support continuation should not send update through the public support browser rail after filing support.");
            VerificationAssert.True(nativeSupport.RollbackAction.Contains("previous installed copy", StringComparison.OrdinalIgnoreCase), "Native support continuation should keep rollback on the previous installed copy after filing support.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/rollback", nativeSupport.NativeRollbackHref, "Native support continuation should keep rollback on the grant-bound native rollback planner after filing support.");
            VerificationAssert.True(!nativeSupport.NativeRollbackHref.StartsWith("/account/", StringComparison.Ordinal), "Native support continuation should not send rollback through the account browser rail after filing support.");
            VerificationAssert.True(!nativeSupport.NativeRollbackHref.StartsWith("/downloads", StringComparison.Ordinal), "Native support continuation should not send rollback through the downloads browser rail after filing support.");
            VerificationAssert.True(!nativeSupport.NativeRollbackHref.StartsWith("/contact", StringComparison.Ordinal), "Native support continuation should not send rollback through the public support browser rail after filing support.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", nativeSupport.PrimaryActionHref, "Native support continuation should keep the immediate follow-through on the grant-bound continuation rail after filing support.");
            VerificationAssert.True(!nativeSupport.PrimaryActionHref.StartsWith("/account/", StringComparison.Ordinal), "Native support continuation should not send the desktop app through the account browser rail for the immediate follow-up action.");
            VerificationAssert.True(!nativeSupport.PrimaryActionHref.StartsWith("/downloads", StringComparison.Ordinal), "Native support continuation should not send the desktop app through the downloads browser rail for the immediate follow-up action.");
            VerificationAssert.True(!nativeSupport.PrimaryActionHref.StartsWith("/contact", StringComparison.Ordinal), "Native support continuation should not send the desktop app through the public support browser rail for the immediate follow-up action.");
            VerificationAssert.True(nativeSupport.AccountSupportHref.StartsWith("/account/support/", StringComparison.Ordinal), "Native support continuation should still provide the account timeline fallback for humans.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", nativeSupport.NativeSupportHref, "Native support continuation should keep follow-up detail on the grant-bound native support endpoint.");
            VerificationAssert.True(!nativeSupport.NativeSupportHref.StartsWith("/account/", StringComparison.Ordinal), "Native support continuation should not make the account support route the desktop app's follow-up action.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", nativeSupport.NativeContinuationHref, "Native support continuation should return the app to the grant-bound continuation rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", nativeSupport.NativeRecoveryHref, "Native support continuation should keep recovery on the grant-bound continuation rail after filing support.");
            VerificationAssert.True(nativeSupport.RecoveryAction.Contains("desktop app", StringComparison.OrdinalIgnoreCase) || nativeSupport.RecoveryAction.Contains("grant-bound continuation rail", StringComparison.OrdinalIgnoreCase), "Native support continuation should describe recovery without opening a browser ritual.");
            VerificationAssert.True(nativeSupport.NextSafeAction.Contains("grant-bound desktop continuation rail", StringComparison.Ordinal), "New native support cases should tell the desktop app to stay on the grant-bound continuation rail.");
            VerificationAssert.True(!nativeSupport.NextSafeAction.Contains("Open Devices", StringComparison.OrdinalIgnoreCase), "New native support cases should not tell the desktop app to open Devices and access.");
            VerificationAssert.True(!nativeSupport.NextSafeAction.Contains("Open downloads", StringComparison.OrdinalIgnoreCase), "New native support cases should not tell the desktop app to open downloads.");
            SupportCaseProjection? nativeSupportCase = supportCases.GetForReporter(nativeSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(nativeSupportCase is not null, "Native support continuation should create a reporter-visible support case.");
            VerificationAssert.Equal(SupportCaseKinds.InstallHelp, nativeSupportCase!.Kind, "Native support continuation should file install help.");
            VerificationAssert.Equal(SupportCaseSourceKinds.DesktopFeedback, nativeSupportCase.Source, "Native support continuation should be sourced from the desktop app, not the public web form.");
            VerificationAssert.True(string.Equals(nativeSupportCase.InstallationId, "install-native", StringComparison.Ordinal), "Native support case should keep claimed install identity.");
            VerificationAssert.True(string.Equals(nativeSupportCase.ApplicationVersion, "0.7.0-preview", StringComparison.Ordinal), "Native support case should keep installed build truth.");
            VerificationAssert.True(string.Equals(nativeSupportCase.ReleaseChannel, "preview", StringComparison.Ordinal), "Native support case should keep installed channel truth.");
            VerificationAssert.True(string.Equals(nativeSupportCase.HeadId, "avalonia", StringComparison.Ordinal), "Native support case should keep installed head truth.");
            VerificationAssert.True(string.Equals(nativeSupportCase.Platform, "linux", StringComparison.Ordinal), "Native support case should keep installed platform truth.");
            VerificationAssert.True(string.Equals(nativeSupportCase.Arch, "x64", StringComparison.Ordinal), "Native support case should keep installed architecture truth.");
            VerificationAssert.True(nativeSupportCase.Detail.Contains("Installed build receipt: receipt-old", StringComparison.Ordinal), "Native support case should keep installed-build receipt truth in the tracked case detail.");
            VerificationAssert.True(nativeSupportCase.Detail.Contains("Authoritative claimed install: install-native; build preview 0.7.0-preview; device avalonia linux x64.", StringComparison.Ordinal), "Native support case should record the grant-bound installed build and device tuple as authoritative detail.");
            VerificationAssert.True(nativeSupportCase.Detail.Contains("Native release recovery truth: current preview 0.7.1-preview; artifact avalonia-linux-x64-installer; updateAvailable true; rollback stays on the previous installed copy", StringComparison.Ordinal), "Native support case should persist current release, update, rollback, and artifact truth for support follow-through.");
            VerificationAssert.True(nativeSupportCase.Detail.Contains("Claim codes are a recovery fallback", StringComparison.Ordinal), "Native support case should persist fallback posture beside the filed support detail.");
            VerificationAssert.True(nativeSupportCase.Detail.Contains("Desktop requested action (advisory browser or external action): /downloads?from=desktop-support", StringComparison.Ordinal), "Native support case should mark desktop-supplied browser action hints as advisory support detail.");
            VerificationAssert.True(nativeSupportCase.Detail.Contains("Native continuation: grant-bound claimed install support", StringComparison.Ordinal), "Native support case should mark browser callback and claim-code payload identifiers as advisory.");

            ActionResult<DesktopInstallNativeUpdateResponse> updateResult = controller.PlanClaimedInstallUpdate(
                new DesktopInstallNativeContinuationRequest("install-native", "grant-token"));
            OkObjectResult updateOk = updateResult.Result as OkObjectResult
                ?? throw new InvalidOperationException("Native update continuation should accept a valid install grant.");
            DesktopInstallNativeUpdateResponse update = updateOk.Value as DesktopInstallNativeUpdateResponse
                ?? throw new InvalidOperationException("Native update continuation should return a typed update response.");
            VerificationAssert.Equal("install-native", update.InstallationId, "Native update should stay bound to the claimed install.");
            VerificationAssert.Equal("0.7.0-preview", update.ApplicationVersion, "Native update should preserve installed build truth.");
            VerificationAssert.Equal("preview", update.ReleaseChannel, "Native update should preserve installed channel truth.");
            VerificationAssert.Equal("avalonia", update.HeadId, "Native update should preserve installed head truth.");
            VerificationAssert.Equal("linux", update.Platform, "Native update should preserve installed platform truth.");
            VerificationAssert.Equal("x64", update.Arch, "Native update should preserve installed architecture truth.");
            VerificationAssert.True(string.Equals(update.InstalledBuildReceiptId, "receipt-old", StringComparison.Ordinal), "Native update should cite the installed-build receipt rather than a newer or wrong-platform receipt.");
            VerificationAssert.Equal("0.7.1-preview", update.CurrentReleaseVersion, "Native update should expose current release truth.");
            VerificationAssert.True(update.UpdateAvailable, "Native update should tell the app whether the claimed install is behind current release truth.");
            VerificationAssert.True(update.UpdatePlan.Contains("installed build receipt receipt-old", StringComparison.Ordinal), "Native update should tell the app which installed-build receipt anchors the update.");
            VerificationAssert.True(update.UpdatePlan.Contains("to preview 0.7.1-preview", StringComparison.Ordinal), "Native update should tell the app the target release without opening downloads.");
            VerificationAssert.True(update.UpdateAction.Contains("grant-bound update planner", StringComparison.Ordinal), "Native update should keep update follow-through on the grant-bound planner.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", update.NativePrimaryActionHref, "Native update should expose the grant-bound update planner as the primary action.");
            VerificationAssert.True(!update.NativePrimaryActionHref.StartsWith("/account/", StringComparison.Ordinal), "Native update primary action should not send the desktop app through the account browser rail.");
            VerificationAssert.True(!update.NativePrimaryActionHref.StartsWith("/downloads", StringComparison.Ordinal), "Native update primary action should not send the desktop app through the downloads browser rail.");
            VerificationAssert.True(!update.NativePrimaryActionHref.StartsWith("/contact", StringComparison.Ordinal), "Native update primary action should not send the desktop app through the public support browser rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", update.NativeContinuationHref, "Native update should return the app to the grant-bound continuation rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", update.NativeSupportHref, "Native update should keep support follow-up on the grant-bound native support endpoint.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/rollback", update.NativeRollbackHref, "Native update should keep rollback on the grant-bound native rollback planner.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", update.NativeRecoveryHref, "Native update should keep recovery on the grant-bound continuation rail.");
            VerificationAssert.True(update.RecoveryAction.Contains("desktop app", StringComparison.OrdinalIgnoreCase) || update.RecoveryAction.Contains("grant-bound continuation rail", StringComparison.OrdinalIgnoreCase), "Native update should keep recovery app-native.");
            VerificationAssert.True(!update.NativeContinuationHref.StartsWith("/account/", StringComparison.Ordinal), "Native update should not send the desktop app through the account browser rail.");
            VerificationAssert.True(!update.NativeContinuationHref.StartsWith("/downloads", StringComparison.Ordinal), "Native update should not send the desktop app through the downloads browser rail.");
            VerificationAssert.True(!update.NativeSupportHref.StartsWith("/contact", StringComparison.Ordinal), "Native update should not send the desktop app through the public support browser rail.");
            VerificationAssert.True(update.SupportHref.StartsWith("/account/support?", StringComparison.Ordinal), "Native update should still provide a human account support fallback with install truth attached.");
            VerificationAssert.True(update.SupportHref.Contains("installedBuildReceiptId=receipt-old", StringComparison.Ordinal), "Native update human fallback should carry installed-build receipt truth.");
            VerificationAssert.True(update.FallbackPosture.Contains("Claim codes are a recovery fallback", StringComparison.Ordinal), "Native update should keep fallback posture aligned with continuation, support, and rollback.");

            ActionResult<DesktopInstallNativeRollbackResponse> rollbackResult = controller.PlanClaimedInstallRollback(
                new DesktopInstallNativeContinuationRequest("install-native", "grant-token"));
            OkObjectResult rollbackOk = rollbackResult.Result as OkObjectResult
                ?? throw new InvalidOperationException("Native rollback continuation should accept a valid install grant.");
            DesktopInstallNativeRollbackResponse rollback = rollbackOk.Value as DesktopInstallNativeRollbackResponse
                ?? throw new InvalidOperationException("Native rollback continuation should return a typed rollback response.");
            VerificationAssert.Equal("install-native", rollback.InstallationId, "Native rollback should stay bound to the claimed install.");
            VerificationAssert.Equal("0.7.0-preview", rollback.ApplicationVersion, "Native rollback should preserve installed build truth.");
            VerificationAssert.Equal("preview", rollback.ReleaseChannel, "Native rollback should preserve installed channel truth.");
            VerificationAssert.Equal("avalonia", rollback.HeadId, "Native rollback should preserve installed head truth.");
            VerificationAssert.Equal("linux", rollback.Platform, "Native rollback should preserve installed platform truth.");
            VerificationAssert.Equal("x64", rollback.Arch, "Native rollback should preserve installed architecture truth.");
            VerificationAssert.True(string.Equals(rollback.InstalledBuildReceiptId, "receipt-old", StringComparison.Ordinal), "Native rollback should cite the installed-build receipt rather than a newer or wrong-platform receipt.");
            VerificationAssert.Equal("0.7.1-preview", rollback.CurrentReleaseVersion, "Native rollback should still expose current release truth.");
            VerificationAssert.True(rollback.UpdateAvailable, "Native rollback should tell the app whether the claimed install is behind current release truth.");
            VerificationAssert.True(rollback.RollbackPlan.Contains("installed build receipt receipt-old", StringComparison.Ordinal), "Native rollback should tell the app which installed-build receipt anchors the rollback.");
            VerificationAssert.True(rollback.RollbackAction.Contains("previous installed copy", StringComparison.OrdinalIgnoreCase), "Native rollback should keep rollback on the previous installed copy.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/rollback", rollback.NativePrimaryActionHref, "Native rollback should expose the grant-bound rollback planner as the primary action.");
            VerificationAssert.True(!rollback.NativePrimaryActionHref.StartsWith("/account/", StringComparison.Ordinal), "Native rollback primary action should not send the desktop app through the account browser rail.");
            VerificationAssert.True(!rollback.NativePrimaryActionHref.StartsWith("/downloads", StringComparison.Ordinal), "Native rollback primary action should not send the desktop app through the downloads browser rail.");
            VerificationAssert.True(!rollback.NativePrimaryActionHref.StartsWith("/contact", StringComparison.Ordinal), "Native rollback primary action should not send the desktop app through the public support browser rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", rollback.NativeContinuationHref, "Native rollback should return the app to the grant-bound continuation rail.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", rollback.NativeUpdateHref, "Native rollback should keep update retry on the grant-bound native update planner.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", rollback.NativeSupportHref, "Native rollback should keep support follow-up on the grant-bound native support endpoint.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", rollback.NativeRecoveryHref, "Native rollback should keep recovery on the grant-bound continuation rail.");
            VerificationAssert.True(rollback.RecoveryAction.Contains("desktop app", StringComparison.OrdinalIgnoreCase) || rollback.RecoveryAction.Contains("grant-bound continuation rail", StringComparison.OrdinalIgnoreCase), "Native rollback should keep recovery app-native.");
            VerificationAssert.True(!rollback.NativeContinuationHref.StartsWith("/account/", StringComparison.Ordinal), "Native rollback should not send the desktop app through the account browser rail.");
            VerificationAssert.True(!rollback.NativeContinuationHref.StartsWith("/downloads", StringComparison.Ordinal), "Native rollback should not send the desktop app through the downloads browser rail.");
            VerificationAssert.True(!rollback.NativeUpdateHref.StartsWith("/downloads", StringComparison.Ordinal), "Native rollback should not send update retry through the downloads browser rail.");
            VerificationAssert.True(!rollback.NativeSupportHref.StartsWith("/contact", StringComparison.Ordinal), "Native rollback should not send the desktop app through the public support browser rail.");
            VerificationAssert.True(rollback.SupportHref.StartsWith("/account/support?", StringComparison.Ordinal), "Native rollback should still provide a human account support fallback with install truth attached.");
            VerificationAssert.True(rollback.SupportHref.Contains("installedBuildReceiptId=receipt-old", StringComparison.Ordinal), "Native rollback human fallback should carry installed-build receipt truth.");
            VerificationAssert.True(rollback.FallbackPosture.Contains("Claim codes are a recovery fallback", StringComparison.Ordinal), "Native rollback should keep fallback posture aligned with continuation and support.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("https://chummer.run/account/support/case-123"), "Native support action sanitizer should treat absolute account URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("https://chummer.run/downloads"), "Native support action sanitizer should treat absolute download URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("https://chummer.run/contact?kind=install_help"), "Native support action sanitizer should treat absolute public support URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("account/support/case-123"), "Native support action sanitizer should treat bare relative account support URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("downloads?channel=preview"), "Native support action sanitizer should treat bare relative download URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("contact?kind=install_help"), "Native support action sanitizer should treat bare relative public support URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("//account/support/case-123"), "Native support action sanitizer should treat scheme-relative account support URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("///downloads?channel=preview"), "Native support action sanitizer should treat repeated-slash download URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("%2Faccount%2Fsupport%2Fcase-123"), "Native support action sanitizer should treat encoded account support URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("%252Fdownloads%253Fchannel%253Dpreview"), "Native support action sanitizer should treat double-encoded download URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("%25252Fcontact%25253Fkind%25253Dinstall_help"), "Native support action sanitizer should treat triple-encoded public support URLs as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("\\account\\support\\case-123"), "Native support action sanitizer should treat Windows-style account support paths as browser rails.");
            VerificationAssert.True(IsBrowserRailHrefForVerification("%5Cdownloads%5Cinstall%5Ccurrent"), "Native support action sanitizer should treat encoded Windows-style download paths as browser rails.");
            VerificationAssert.True(!IsBrowserRailHrefForVerification("/api/v1/install-linking/continuation"), "Native support action sanitizer should keep grant-bound API continuation URLs native.");
            VerificationAssert.True(!IsBrowserRailHrefForVerification("https://chummer.run/api/v1/install-linking/continuation/update"), "Native support action sanitizer should keep trusted absolute grant-bound API continuation URLs native.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("https://unexpected.example/support/case-123"), "Native support action sanitizer should fail closed when support presentation returns an unexpected external action.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("https://unexpected.example/api/v1/install-linking/continuation/update"), "Native support action sanitizer should fail closed instead of preserving absolute native-looking actions.");
            VerificationAssert.True(NormalizeNativeInstallRailHrefForVerification("http://chummer.run/api/v1/install-linking/continuation/update") is null, "Native support action sanitizer should fail closed instead of preserving insecure public Hub-native actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("https://chummer.run/api/v1/install-linking/continuation/update"), "Native support action sanitizer should fail closed to the continuation rail when support presentation returns an absolute Hub-native update action.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", BuildNativeSupportCaseActionHrefForVerification("https://chummer.run/api/v1/install-linking/continuation/update", needsInstallUpdate: true), "Native support action sanitizer should only use native update when install-readiness requires an update.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", BuildNativeSupportCaseActionHrefForVerification("http://127.0.0.1:47761/api/v1/install-linking/continuation/support", reporterActionNeeded: true), "Native support action sanitizer should preserve trusted app-local native support actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", NormalizeNativeInstallRailHrefForVerification("/api/v1/install-linking/continuation/support?return=%2Faccount%2Fsupport#state=%2Fdesktop"), "Native support action sanitizer should preserve native support paths when encoded slash state appears only in query or fragment context.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/update", BuildNativeSupportCaseActionHrefForVerification("/api/v1/install-linking/continuation/update?return=%2Fdownloads#state=%2Fdesktop", needsInstallUpdate: true), "Native support action sanitizer should preserve native update actions when encoded slash state appears only outside the route path.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("//api/v1/install-linking/continuation/update"), "Native support action sanitizer should fail closed instead of preserving scheme-relative native-looking actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("///api/v1/install-linking/continuation/update"), "Native support action sanitizer should fail closed instead of preserving repeated-slash native-looking actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("api/v1/install-linking/continuation/update"), "Native support action sanitizer should fail closed instead of preserving bare relative native-looking actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("%2Fapi%2Fv1%2Finstall-linking%2Fcontinuation%2Fupdate"), "Native support action sanitizer should fail closed instead of preserving encoded native-looking actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("/%252Fapi%252Fv1%252Finstall-linking%252Fcontinuation%252Fupdate"), "Native support action sanitizer should fail closed instead of preserving double-encoded native-looking actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("\\api\\v1\\install-linking\\continuation\\update"), "Native support action sanitizer should fail closed instead of preserving Windows-style native-looking actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("/%255Capi%255Cv1%255Cinstall-linking%255Ccontinuation%255Cupdate"), "Native support action sanitizer should fail closed instead of preserving double-encoded Windows-style native-looking actions.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("mailto:support@example.invalid"), "Native support action sanitizer should fail closed instead of handing the desktop app to a non-http action.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("javascript:alert(1)"), "Native support action sanitizer should fail closed instead of handing the desktop app to a script action.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("/api/v1/install-linking/continuation/update"), "Native support action sanitizer should fall back to the continuation rail when a native update href is presented without update-needed support state.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation/support", BuildNativeSupportCaseActionHrefForVerification("/api/v1/install-linking/continuation/support", reporterActionNeeded: true), "Native support action sanitizer should keep reporter-needed follow-up on the native support intake.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("/api/v1/install-linking/continuation/support"), "Native support action sanitizer should not preserve native support intake without reporter-needed support state.");
            VerificationAssert.Equal("/api/v1/install-linking/continuation", BuildNativeSupportCaseActionHrefForVerification("/api/v1/install-linking/continuation/rollback"), "Native support action sanitizer should not preserve native rollback without rollback-specific support state.");

            ActionResult<DesktopInstallNativeSupportResponse> staleReceiptLabelSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app stale receipt label",
                    Summary: "The app sent a stale receipt label while filing native support.",
                    Detail: "Desktop payload already said Installed build receipt: receipt-other-platform and callback code stale-browser-code.",
                    RequestedActionHref: "/install-link/callback?state=desktop&code=stale-browser-code&accessToken=stale-access-token&grantId=stale-grant&claimCode=stale-claim&receiptId=stale-receipt&installedBuildReceiptId=stale-installed-receipt&installationId=wrong-install"));
            ObjectResult staleReceiptLabelAccepted = staleReceiptLabelSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with stale detail.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, staleReceiptLabelAccepted.StatusCode ?? 0, "Native support continuation should still file support when the desktop detail carries stale receipt text.");
            DesktopInstallNativeSupportResponse staleReceiptLabelSupport = staleReceiptLabelAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed stale-receipt-label response.");
            SupportCaseProjection? staleReceiptLabelCase = supportCases.GetForReporter(staleReceiptLabelSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(staleReceiptLabelCase is not null, "Native support continuation should create the stale-receipt-label support case.");
            VerificationAssert.True(staleReceiptLabelCase!.Detail.Contains("Installed build receipt: receipt-old", StringComparison.Ordinal), "Native support case should append canonical installed-build receipt truth even when the desktop payload already had a stale receipt label.");
            VerificationAssert.True(staleReceiptLabelCase.Detail.Contains("Installed build receipt: receipt-other-platform", StringComparison.Ordinal), "Native support case should preserve the desktop-supplied detail for support triage.");
            VerificationAssert.True(staleReceiptLabelCase.Detail.Contains("Authoritative claimed install: install-native; build preview 0.7.0-preview; device avalonia linux x64.", StringComparison.Ordinal), "Native support case should keep authoritative grant-bound install truth beside stale desktop payload labels.");
            VerificationAssert.True(staleReceiptLabelCase.Detail.Contains("Native release recovery truth: current preview 0.7.1-preview; artifact avalonia-linux-x64-installer; updateAvailable true; rollback stays on the previous installed copy", StringComparison.Ordinal), "Native support case should append canonical release recovery truth beside stale desktop payload labels.");
            VerificationAssert.True(staleReceiptLabelCase.Detail.Contains("Native continuation: grant-bound claimed install support", StringComparison.Ordinal), "Native support case should keep stale callback or claim-code payload identifiers advisory.");
            VerificationAssert.True(staleReceiptLabelCase.Detail.Contains("Desktop requested action (advisory browser or external action): /install-link/callback?state=desktop&code=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact reserved install-link query secrets from the desktop requested action.");
            VerificationAssert.True(!staleReceiptLabelCase.Detail.Contains("accessToken=stale-access-token", StringComparison.Ordinal), "Native support case should not persist stale access tokens from desktop requested-action hints.");
            VerificationAssert.True(!staleReceiptLabelCase.Detail.Contains("grantId=stale-grant", StringComparison.Ordinal), "Native support case should not persist stale grant ids from desktop requested-action hints.");
            VerificationAssert.True(!staleReceiptLabelCase.Detail.Contains("claimCode=stale-claim", StringComparison.Ordinal), "Native support case should not persist stale claim codes from desktop requested-action hints.");
            VerificationAssert.True(!staleReceiptLabelCase.Detail.Contains("receiptId=stale-receipt", StringComparison.Ordinal), "Native support case should not persist stale receipt ids from desktop requested-action hints.");
            VerificationAssert.True(!staleReceiptLabelCase.Detail.Contains("installedBuildReceiptId=stale-installed-receipt", StringComparison.Ordinal), "Native support case should not persist stale installed-build receipt ids from desktop requested-action hints.");
            VerificationAssert.True(!staleReceiptLabelCase.Detail.Contains("installationId=wrong-install", StringComparison.Ordinal), "Native support case should not persist stale install identity from desktop requested-action hints.");

            ActionResult<DesktopInstallNativeSupportResponse> fragmentSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app fragment secret label",
                    Summary: "The app sent install-link secrets in the requested-action fragment while filing native support.",
                    Detail: "Desktop payload included fragment-carried install-link continuation state.",
                    RequestedActionHref: "/install-link/callback#state=desktop&accessToken=fragment-access-token&grantId=fragment-grant&claimCode=fragment-claim&receiptId=fragment-receipt&installedBuildReceiptId=fragment-installed-receipt&installationId=fragment-install"));
            ObjectResult fragmentSecretAccepted = fragmentSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with fragment-carried secrets.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, fragmentSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when the desktop requested action carries fragment secrets.");
            DesktopInstallNativeSupportResponse fragmentSecretSupport = fragmentSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed fragment-secret response.");
            SupportCaseProjection? fragmentSecretCase = supportCases.GetForReporter(fragmentSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(fragmentSecretCase is not null, "Native support continuation should create the fragment-secret support case.");
            VerificationAssert.True(fragmentSecretCase!.Detail.Contains("#state=desktop&accessToken=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact reserved fragment secrets from the desktop requested action.");
            VerificationAssert.True(!fragmentSecretCase.Detail.Contains("fragment-access-token", StringComparison.Ordinal), "Native support case should not persist fragment access tokens from desktop requested-action hints.");
            VerificationAssert.True(!fragmentSecretCase.Detail.Contains("fragment-grant", StringComparison.Ordinal), "Native support case should not persist fragment grant ids from desktop requested-action hints.");
            VerificationAssert.True(!fragmentSecretCase.Detail.Contains("fragment-claim", StringComparison.Ordinal), "Native support case should not persist fragment claim codes from desktop requested-action hints.");
            VerificationAssert.True(!fragmentSecretCase.Detail.Contains("fragment-receipt", StringComparison.Ordinal), "Native support case should not persist fragment receipt ids from desktop requested-action hints.");
            VerificationAssert.True(!fragmentSecretCase.Detail.Contains("fragment-installed-receipt", StringComparison.Ordinal), "Native support case should not persist fragment installed-build receipt ids from desktop requested-action hints.");
            VerificationAssert.True(!fragmentSecretCase.Detail.Contains("fragment-install", StringComparison.Ordinal), "Native support case should not persist fragment install identity from desktop requested-action hints.");

            ActionResult<DesktopInstallNativeSupportResponse> mixedQueryAndFragmentSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app mixed query and fragment label",
                    Summary: "The app kept desktop listener state in query while fragment-carried install-link secrets were present.",
                    Detail: "Desktop payload mixed listener state and fragment-carried install-link continuation state.",
                    RequestedActionHref: "/install-link/callback?state=desktop&nonce=query-proof#accessToken=fragment-access-token&grantId=fragment-grant&claimCode=fragment-claim"));
            ObjectResult mixedQueryAndFragmentAccepted = mixedQueryAndFragmentSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with mixed query and fragment continuation state.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, mixedQueryAndFragmentAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop listener query state and fragment secrets arrive together.");
            DesktopInstallNativeSupportResponse mixedQueryAndFragmentSupport = mixedQueryAndFragmentAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed mixed-query-and-fragment response.");
            SupportCaseProjection? mixedQueryAndFragmentCase = supportCases.GetForReporter(mixedQueryAndFragmentSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(mixedQueryAndFragmentCase is not null, "Native support continuation should create the mixed-query-and-fragment support case.");
            VerificationAssert.True(mixedQueryAndFragmentCase!.Detail.Contains("/install-link/callback?state=desktop&nonce=query-proof#accessToken=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should preserve app-local listener query state while redacting fragment-carried install-link secrets.");
            VerificationAssert.True(!mixedQueryAndFragmentCase.Detail.Contains("fragment-access-token", StringComparison.Ordinal), "Native support case should not persist fragment access tokens when query state is also present.");
            VerificationAssert.True(!mixedQueryAndFragmentCase.Detail.Contains("fragment-grant", StringComparison.Ordinal), "Native support case should not persist fragment grant ids when query state is also present.");
            VerificationAssert.True(!mixedQueryAndFragmentCase.Detail.Contains("fragment-claim", StringComparison.Ordinal), "Native support case should not persist fragment claim codes when query state is also present.");

            ActionResult<DesktopInstallNativeSupportResponse> encodedSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app encoded secret label",
                    Summary: "The app sent encoded install-link secret keys while filing native support.",
                    Detail: "Desktop payload carried encoded reserved callback keys.",
                    RequestedActionHref: "/install-link/callback?state=desktop&access%54oken=encoded-access-token&grant%49d=encoded-grant#claim%43ode=encoded-claim&installedBuildReceipt%49d=encoded-installed-receipt"));
            ObjectResult encodedSecretAccepted = encodedSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with encoded reserved keys.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, encodedSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action keys are encoded.");
            DesktopInstallNativeSupportResponse encodedSecretSupport = encodedSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed encoded-secret response.");
            SupportCaseProjection? encodedSecretCase = supportCases.GetForReporter(encodedSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(encodedSecretCase is not null, "Native support continuation should create the encoded-secret support case.");
            VerificationAssert.True(encodedSecretCase!.Detail.Contains("access%54oken=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact encoded query access-token keys from the requested action.");
            VerificationAssert.True(encodedSecretCase.Detail.Contains("grant%49d=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact encoded query grant-id keys from the requested action.");
            VerificationAssert.True(encodedSecretCase.Detail.Contains("claim%43ode=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact encoded fragment claim-code keys from the requested action.");
            VerificationAssert.True(encodedSecretCase.Detail.Contains("installedBuildReceipt%49d=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact encoded fragment installed-build receipt keys from the requested action.");
            VerificationAssert.True(!encodedSecretCase.Detail.Contains("encoded-access-token", StringComparison.Ordinal), "Native support case should not persist encoded access-token values from requested-action hints.");
            VerificationAssert.True(!encodedSecretCase.Detail.Contains("encoded-grant", StringComparison.Ordinal), "Native support case should not persist encoded grant values from requested-action hints.");
            VerificationAssert.True(!encodedSecretCase.Detail.Contains("encoded-claim", StringComparison.Ordinal), "Native support case should not persist encoded claim-code values from requested-action hints.");
            VerificationAssert.True(!encodedSecretCase.Detail.Contains("encoded-installed-receipt", StringComparison.Ordinal), "Native support case should not persist encoded installed-build receipt values from requested-action hints.");

            ActionResult<DesktopInstallNativeSupportResponse> doubleEncodedKeySupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app double-encoded key label",
                    Summary: "The app sent double-encoded install-link secret keys while filing native support.",
                    Detail: "Desktop payload carried double-encoded reserved callback keys.",
                    RequestedActionHref: "/install-link/callback?state=desktop&access%2554oken=double-encoded-access-token&grant%2549d=double-encoded-grant#claim%2543ode=double-encoded-claim&installedBuildReceipt%2549d=double-encoded-installed-receipt"));
            ObjectResult doubleEncodedKeyAccepted = doubleEncodedKeySupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with double-encoded reserved keys.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, doubleEncodedKeyAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action keys are double-encoded.");
            DesktopInstallNativeSupportResponse doubleEncodedKeySupport = doubleEncodedKeyAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed double-encoded-key response.");
            SupportCaseProjection? doubleEncodedKeyCase = supportCases.GetForReporter(doubleEncodedKeySupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(doubleEncodedKeyCase is not null, "Native support continuation should create the double-encoded-key support case.");
            VerificationAssert.True(doubleEncodedKeyCase!.Detail.Contains("access%2554oken=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact double-encoded query access-token keys from the requested action.");
            VerificationAssert.True(doubleEncodedKeyCase.Detail.Contains("grant%2549d=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact double-encoded query grant-id keys from the requested action.");
            VerificationAssert.True(doubleEncodedKeyCase.Detail.Contains("claim%2543ode=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact double-encoded fragment claim-code keys from the requested action.");
            VerificationAssert.True(doubleEncodedKeyCase.Detail.Contains("installedBuildReceipt%2549d=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact double-encoded fragment installed-build receipt keys from the requested action.");
            VerificationAssert.True(!doubleEncodedKeyCase.Detail.Contains("double-encoded-access-token", StringComparison.Ordinal), "Native support case should not persist double-encoded access-token values from requested-action hints.");
            VerificationAssert.True(!doubleEncodedKeyCase.Detail.Contains("double-encoded-grant", StringComparison.Ordinal), "Native support case should not persist double-encoded grant values from requested-action hints.");
            VerificationAssert.True(!doubleEncodedKeyCase.Detail.Contains("double-encoded-claim", StringComparison.Ordinal), "Native support case should not persist double-encoded claim-code values from requested-action hints.");
            VerificationAssert.True(!doubleEncodedKeyCase.Detail.Contains("double-encoded-installed-receipt", StringComparison.Ordinal), "Native support case should not persist double-encoded installed-build receipt values from requested-action hints.");

            ActionResult<DesktopInstallNativeSupportResponse> encodedEqualsSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app encoded equals secret label",
                    Summary: "The app sent install-link secrets with encoded equals separators while filing native support.",
                    Detail: "Desktop payload carried encoded equals signs between reserved callback keys and values.",
                    RequestedActionHref: "/install-link/callback?state=desktop&accessToken%3Dencoded-equals-access%26grantId%253Ddouble-encoded-equals-grant#claimCode%3Dencoded-equals-claim%2526installedBuildReceiptId%253Ddouble-encoded-equals-receipt"));
            ObjectResult encodedEqualsSecretAccepted = encodedEqualsSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with encoded equals signs.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, encodedEqualsSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action keys use encoded equals separators.");
            DesktopInstallNativeSupportResponse encodedEqualsSecretSupport = encodedEqualsSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed encoded-equals-secret response.");
            SupportCaseProjection? encodedEqualsSecretCase = supportCases.GetForReporter(encodedEqualsSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(encodedEqualsSecretCase is not null, "Native support continuation should create the encoded-equals-secret support case.");
            VerificationAssert.True(encodedEqualsSecretCase!.Detail.Contains("accessToken%3D%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact query access-token values after encoded equals separators.");
            VerificationAssert.True(encodedEqualsSecretCase.Detail.Contains("grantId%253D%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact query grant-id values after double-encoded equals separators.");
            VerificationAssert.True(encodedEqualsSecretCase.Detail.Contains("claimCode%3D%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact fragment claim-code values after encoded equals separators.");
            VerificationAssert.True(encodedEqualsSecretCase.Detail.Contains("installedBuildReceiptId%253D%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact fragment installed-build receipt values after double-encoded equals separators.");
            VerificationAssert.True(!encodedEqualsSecretCase.Detail.Contains("encoded-equals-access", StringComparison.Ordinal), "Native support case should not persist access-token values after encoded equals separators.");
            VerificationAssert.True(!encodedEqualsSecretCase.Detail.Contains("double-encoded-equals-grant", StringComparison.Ordinal), "Native support case should not persist grant-id values after double-encoded equals separators.");
            VerificationAssert.True(!encodedEqualsSecretCase.Detail.Contains("encoded-equals-claim", StringComparison.Ordinal), "Native support case should not persist claim-code values after encoded equals separators.");
            VerificationAssert.True(!encodedEqualsSecretCase.Detail.Contains("double-encoded-equals-receipt", StringComparison.Ordinal), "Native support case should not persist installed-build receipt values after double-encoded equals separators.");

            ActionResult<DesktopInstallNativeSupportResponse> htmlEqualsSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app HTML equals secret label",
                    Summary: "The app sent install-link secrets with HTML entity equals separators while filing native support.",
                    Detail: "Desktop payload carried HTML entity equals signs between reserved callback keys and values.",
                    RequestedActionHref: "/install-link/callback?state=desktop%26accessToken&equals;html-equals-access%26grantId&#61;numeric-equals-grant#state=desktop%26claimCode&#x3d;hex-equals-claim%26installedBuildReceiptId&equals;html-equals-receipt"));
            ObjectResult htmlEqualsSecretAccepted = htmlEqualsSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with HTML entity equals signs.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, htmlEqualsSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action keys use HTML entity equals separators.");
            DesktopInstallNativeSupportResponse htmlEqualsSecretSupport = htmlEqualsSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed HTML-equals-secret response.");
            SupportCaseProjection? htmlEqualsSecretCase = supportCases.GetForReporter(htmlEqualsSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(htmlEqualsSecretCase is not null, "Native support continuation should create the HTML-equals-secret support case.");
            VerificationAssert.True(htmlEqualsSecretCase!.Detail.Contains("accessToken&equals;%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact query access-token values after HTML named equals separators.");
            VerificationAssert.True(htmlEqualsSecretCase.Detail.Contains("grantId&#61;%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact query grant-id values after HTML numeric equals separators.");
            VerificationAssert.True(htmlEqualsSecretCase.Detail.Contains("claimCode&#x3d;%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact fragment claim-code values after HTML hex equals separators.");
            VerificationAssert.True(htmlEqualsSecretCase.Detail.Contains("installedBuildReceiptId&equals;%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact fragment installed-build receipt values after HTML named equals separators.");
            VerificationAssert.True(!htmlEqualsSecretCase.Detail.Contains("html-equals-access", StringComparison.Ordinal), "Native support case should not persist access-token values after HTML entity equals separators.");
            VerificationAssert.True(!htmlEqualsSecretCase.Detail.Contains("numeric-equals-grant", StringComparison.Ordinal), "Native support case should not persist grant-id values after HTML entity equals separators.");
            VerificationAssert.True(!htmlEqualsSecretCase.Detail.Contains("hex-equals-claim", StringComparison.Ordinal), "Native support case should not persist claim-code values after HTML entity equals separators.");
            VerificationAssert.True(!htmlEqualsSecretCase.Detail.Contains("html-equals-receipt", StringComparison.Ordinal), "Native support case should not persist installed-build receipt values after HTML entity equals separators.");

            ActionResult<DesktopInstallNativeSupportResponse> bootstrapTicketSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app bootstrap ticket label",
                    Summary: "The app sent a short-lived install bootstrap ticket while filing native support.",
                    Detail: "Desktop payload carried a bootstrap ticket query from the install/download handoff.",
                    RequestedActionHref: "/downloads/install/avalonia-linux-x64-installer/bootstrap.sh?ticket=bootstrap-ticket-secret&state=desktop"));
            ObjectResult bootstrapTicketAccepted = bootstrapTicketSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with a bootstrap ticket action hint.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, bootstrapTicketAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action hints carry bootstrap tickets.");
            DesktopInstallNativeSupportResponse bootstrapTicketSupport = bootstrapTicketAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed bootstrap-ticket response.");
            SupportCaseProjection? bootstrapTicketCase = supportCases.GetForReporter(bootstrapTicketSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(bootstrapTicketCase is not null, "Native support continuation should create the bootstrap-ticket support case.");
            VerificationAssert.True(bootstrapTicketCase!.Detail.Contains("ticket=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact short-lived bootstrap ticket query values from requested-action hints.");
            VerificationAssert.True(!bootstrapTicketCase.Detail.Contains("bootstrap-ticket-secret", StringComparison.Ordinal), "Native support case should not persist short-lived bootstrap ticket values from requested-action hints.");

            ActionResult<DesktopInstallNativeSupportResponse> semicolonSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app semicolon secret label",
                    Summary: "The app sent semicolon-separated install-link secrets while filing native support.",
                    Detail: "Desktop payload carried semicolon-separated reserved callback keys.",
                    RequestedActionHref: "/install-link/callback?state=desktop;accessToken=semicolon-access-token;grantId=semicolon-grant#claimCode=semicolon-claim;installedBuildReceiptId=semicolon-installed-receipt"));
            ObjectResult semicolonSecretAccepted = semicolonSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with semicolon-separated secrets.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, semicolonSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action keys use semicolon separators.");
            DesktopInstallNativeSupportResponse semicolonSecretSupport = semicolonSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed semicolon-secret response.");
            SupportCaseProjection? semicolonSecretCase = supportCases.GetForReporter(semicolonSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(semicolonSecretCase is not null, "Native support continuation should create the semicolon-secret support case.");
            VerificationAssert.True(semicolonSecretCase!.Detail.Contains("accessToken=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact semicolon-separated query access-token keys from the requested action.");
            VerificationAssert.True(semicolonSecretCase.Detail.Contains("grantId=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact semicolon-separated query grant-id keys from the requested action.");
            VerificationAssert.True(semicolonSecretCase.Detail.Contains("claimCode=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact semicolon-separated fragment claim-code keys from the requested action.");
            VerificationAssert.True(semicolonSecretCase.Detail.Contains("installedBuildReceiptId=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact semicolon-separated fragment installed-build receipt keys from the requested action.");
            VerificationAssert.True(!semicolonSecretCase.Detail.Contains("semicolon-access-token", StringComparison.Ordinal), "Native support case should not persist semicolon-separated access-token values from requested-action hints.");
            VerificationAssert.True(!semicolonSecretCase.Detail.Contains("semicolon-grant", StringComparison.Ordinal), "Native support case should not persist semicolon-separated grant values from requested-action hints.");
            VerificationAssert.True(!semicolonSecretCase.Detail.Contains("semicolon-claim", StringComparison.Ordinal), "Native support case should not persist semicolon-separated claim-code values from requested-action hints.");
            VerificationAssert.True(!semicolonSecretCase.Detail.Contains("semicolon-installed-receipt", StringComparison.Ordinal), "Native support case should not persist semicolon-separated installed-build receipt values from requested-action hints.");

            ActionResult<DesktopInstallNativeSupportResponse> encodedSeparatorSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app encoded separator secret label",
                    Summary: "The app sent encoded separators before install-link secrets while filing native support.",
                    Detail: "Desktop payload carried encoded query and fragment separators.",
                    RequestedActionHref: "/install-link/callback?state=desktop%3BaccessToken=encoded-separator-access%26grantId=encoded-separator-grant%23claimCode=encoded-hash-claim#state=desktop%253BclaimCode=double-encoded-separator-claim%2526installedBuildReceiptId=double-encoded-separator-receipt%2523receiptId=double-encoded-hash-receipt"));
            ObjectResult encodedSeparatorSecretAccepted = encodedSeparatorSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with encoded secret separators.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, encodedSeparatorSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action separators are encoded.");
            DesktopInstallNativeSupportResponse encodedSeparatorSecretSupport = encodedSeparatorSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed encoded-separator-secret response.");
            SupportCaseProjection? encodedSeparatorSecretCase = supportCases.GetForReporter(encodedSeparatorSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(encodedSeparatorSecretCase is not null, "Native support continuation should create the encoded-separator-secret support case.");
            VerificationAssert.True(encodedSeparatorSecretCase!.Detail.Contains("state=desktop%3BaccessToken=%5Bredacted-install-link-secret%5D%26grantId=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact query secrets after encoded separators.");
            VerificationAssert.True(encodedSeparatorSecretCase.Detail.Contains("%23claimCode=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact query secrets after encoded hash separators.");
            VerificationAssert.True(encodedSeparatorSecretCase.Detail.Contains("#state=desktop%253BclaimCode=%5Bredacted-install-link-secret%5D%2526installedBuildReceiptId=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact fragment secrets after double-encoded separators.");
            VerificationAssert.True(encodedSeparatorSecretCase.Detail.Contains("%2523receiptId=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact fragment secrets after double-encoded hash separators.");
            VerificationAssert.True(!encodedSeparatorSecretCase.Detail.Contains("encoded-separator-access", StringComparison.Ordinal), "Native support case should not persist access-token values after encoded separators.");
            VerificationAssert.True(!encodedSeparatorSecretCase.Detail.Contains("encoded-separator-grant", StringComparison.Ordinal), "Native support case should not persist grant values after encoded separators.");
            VerificationAssert.True(!encodedSeparatorSecretCase.Detail.Contains("encoded-hash-claim", StringComparison.Ordinal), "Native support case should not persist claim-code values after encoded hash separators.");
            VerificationAssert.True(!encodedSeparatorSecretCase.Detail.Contains("double-encoded-separator-claim", StringComparison.Ordinal), "Native support case should not persist claim-code values after double-encoded separators.");
            VerificationAssert.True(!encodedSeparatorSecretCase.Detail.Contains("double-encoded-separator-receipt", StringComparison.Ordinal), "Native support case should not persist installed-build receipt values after double-encoded separators.");
            VerificationAssert.True(!encodedSeparatorSecretCase.Detail.Contains("double-encoded-hash-receipt", StringComparison.Ordinal), "Native support case should not persist receipt values after double-encoded hash separators.");

            ActionResult<DesktopInstallNativeSupportResponse> htmlEntitySeparatorSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app HTML entity separator secret label",
                    Summary: "The app sent HTML entity separators before encoded install-link secrets while filing native support.",
                    Detail: "Desktop payload carried HTML entity query and fragment separators.",
                    RequestedActionHref: "/install-link/callback?state=desktop&amp;access%54oken=html-entity-access&#x26;grant%49d=html-entity-grant#state=desktop&semi;claim%43ode=html-entity-claim&num;receiptId=html-entity-receipt"));
            ObjectResult htmlEntitySeparatorSecretAccepted = htmlEntitySeparatorSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with HTML entity secret separators.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, htmlEntitySeparatorSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action separators are HTML entities.");
            DesktopInstallNativeSupportResponse htmlEntitySeparatorSecretSupport = htmlEntitySeparatorSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed HTML-entity-separator-secret response.");
            SupportCaseProjection? htmlEntitySeparatorSecretCase = supportCases.GetForReporter(htmlEntitySeparatorSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(htmlEntitySeparatorSecretCase is not null, "Native support continuation should create the HTML-entity-separator-secret support case.");
            VerificationAssert.True(htmlEntitySeparatorSecretCase!.Detail.Contains("&amp;access%54oken=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact encoded query access-token keys after HTML ampersand separators.");
            VerificationAssert.True(htmlEntitySeparatorSecretCase.Detail.Contains("&#x26;grant%49d=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact encoded query grant-id keys after HTML numeric ampersand separators.");
            VerificationAssert.True(htmlEntitySeparatorSecretCase.Detail.Contains("&semi;claim%43ode=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact encoded fragment claim-code keys after HTML semicolon separators.");
            VerificationAssert.True(htmlEntitySeparatorSecretCase.Detail.Contains("&num;receiptId=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact fragment receipt keys after HTML hash separators.");
            VerificationAssert.True(!htmlEntitySeparatorSecretCase.Detail.Contains("html-entity-access", StringComparison.Ordinal), "Native support case should not persist access-token values after HTML entity separators.");
            VerificationAssert.True(!htmlEntitySeparatorSecretCase.Detail.Contains("html-entity-grant", StringComparison.Ordinal), "Native support case should not persist grant values after HTML entity separators.");
            VerificationAssert.True(!htmlEntitySeparatorSecretCase.Detail.Contains("html-entity-claim", StringComparison.Ordinal), "Native support case should not persist claim-code values after HTML entity separators.");
            VerificationAssert.True(!htmlEntitySeparatorSecretCase.Detail.Contains("html-entity-receipt", StringComparison.Ordinal), "Native support case should not persist receipt values after HTML entity separators.");

            ActionResult<DesktopInstallNativeSupportResponse> numericHtmlHashSecretSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest(
                    InstallationId: "install-native",
                    AccessToken: "grant-token",
                    Title: "Native app HTML numeric hash separator secret label",
                    Summary: "The app sent HTML numeric hash separators before install-link secrets while filing native support.",
                    Detail: "Desktop payload carried HTML numeric hash separators.",
                    RequestedActionHref: "/install-link/callback?state=desktop&#35;claimCode=decimal-hash-claim&#x23;receiptId=hex-hash-receipt"));
            ObjectResult numericHtmlHashSecretAccepted = numericHtmlHashSecretSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should accept a valid install grant with HTML numeric hash separators.");
            VerificationAssert.Equal(StatusCodes.Status202Accepted, numericHtmlHashSecretAccepted.StatusCode ?? 0, "Native support continuation should still file support when desktop requested-action separators are HTML numeric hashes.");
            DesktopInstallNativeSupportResponse numericHtmlHashSecretSupport = numericHtmlHashSecretAccepted.Value as DesktopInstallNativeSupportResponse
                ?? throw new InvalidOperationException("Native support continuation should return a typed HTML-numeric-hash-separator response.");
            SupportCaseProjection? numericHtmlHashSecretCase = supportCases.GetForReporter(numericHtmlHashSecretSupport.CaseId, "usr-native", "subject.native");
            VerificationAssert.True(numericHtmlHashSecretCase is not null, "Native support continuation should create the HTML-numeric-hash-separator support case.");
            VerificationAssert.True(numericHtmlHashSecretCase!.Detail.Contains("&#35;claimCode=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact claim-code values after HTML decimal hash separators.");
            VerificationAssert.True(numericHtmlHashSecretCase.Detail.Contains("&#x23;receiptId=%5Bredacted-install-link-secret%5D", StringComparison.Ordinal), "Native support case should redact receipt values after HTML hex hash separators.");
            VerificationAssert.True(!numericHtmlHashSecretCase.Detail.Contains("decimal-hash-claim", StringComparison.Ordinal), "Native support case should not persist claim-code values after HTML decimal hash separators.");
            VerificationAssert.True(!numericHtmlHashSecretCase.Detail.Contains("hex-hash-receipt", StringComparison.Ordinal), "Native support case should not persist receipt values after HTML hex hash separators.");

            ActionResult<DesktopInstallNativeContinuationResponse> unauthorizedResult = controller.ContinueClaimedInstall(
                new DesktopInstallNativeContinuationRequest("install-native", "wrong-token"));
            ObjectResult unauthorized = unauthorizedResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Desktop continuation should reject an invalid grant.");
            VerificationAssert.Equal(StatusCodes.Status401Unauthorized, unauthorized.StatusCode ?? 0, "Invalid desktop continuation grants should fail closed.");

            ActionResult<DesktopInstallNativeSupportResponse> unauthorizedSupportResult = controller.SubmitClaimedInstallSupport(
                new DesktopInstallNativeSupportRequest("install-native", "wrong-token"));
            ObjectResult unauthorizedSupport = unauthorizedSupportResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native support continuation should reject an invalid grant.");
            VerificationAssert.Equal(StatusCodes.Status401Unauthorized, unauthorizedSupport.StatusCode ?? 0, "Invalid native support continuation grants should fail closed.");

            ActionResult<DesktopInstallNativeUpdateResponse> unauthorizedUpdateResult = controller.PlanClaimedInstallUpdate(
                new DesktopInstallNativeContinuationRequest("install-native", "wrong-token"));
            ObjectResult unauthorizedUpdate = unauthorizedUpdateResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native update continuation should reject an invalid grant.");
            VerificationAssert.Equal(StatusCodes.Status401Unauthorized, unauthorizedUpdate.StatusCode ?? 0, "Invalid native update continuation grants should fail closed.");

            ActionResult<DesktopInstallNativeRollbackResponse> unauthorizedRollbackResult = controller.PlanClaimedInstallRollback(
                new DesktopInstallNativeContinuationRequest("install-native", "wrong-token"));
            ObjectResult unauthorizedRollback = unauthorizedRollbackResult.Result as ObjectResult
                ?? throw new InvalidOperationException("Native rollback continuation should reject an invalid grant.");
            VerificationAssert.Equal(StatusCodes.Status401Unauthorized, unauthorizedRollback.StatusCode ?? 0, "Invalid native rollback continuation grants should fail closed.");

            string callbackRedirect = BuildBrowserInstallCallbackRedirectUriForVerification(
                "http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof&code=stale-browser-code&callbackCode=stale-callback-code&accessToken=stale-access-token&grantId=stale-grant&claimCode=stale-claim&claimTicketId=stale-ticket&ticketId=stale-ticket-id&receiptId=stale-receipt&installedBuildReceiptId=stale-installed-receipt&installationId=wrong-install&artifactId=wrong-artifact&channelId=wrong-channel&version=wrong-version&platformId=wrong-platform&installLinkMode=claim_code&installLinkTransport=browser_only",
                "fresh-grant-code",
                "install-native",
                "avalonia",
                "0.7.0-preview",
                "preview",
                "linux",
                "x64");
            VerificationAssert.True(callbackRedirect.Contains("state=desktop", StringComparison.Ordinal), "App-local callback redirects should preserve desktop listener state.");
            VerificationAssert.True(callbackRedirect.Contains("nonce=callback-proof", StringComparison.Ordinal), "App-local callback redirects should preserve desktop listener nonce.");
            VerificationAssert.True(callbackRedirect.Contains("code=fresh-grant-code", StringComparison.Ordinal), "App-local callback redirects should use the freshly issued grant callback code.");
            VerificationAssert.True(!callbackRedirect.Contains("code=stale-browser-code", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided callback codes.");
            VerificationAssert.True(!callbackRedirect.Contains("callbackCode=stale-callback-code", StringComparison.Ordinal), "App-local callback redirects should strip stale browser callback-code aliases.");
            VerificationAssert.True(!callbackRedirect.Contains("accessToken=stale-access-token", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided grant tokens.");
            VerificationAssert.True(!callbackRedirect.Contains("grantId=stale-grant", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided grant ids.");
            VerificationAssert.True(!callbackRedirect.Contains("claimCode=stale-claim", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided claim codes.");
            VerificationAssert.True(!callbackRedirect.Contains("claimTicketId=stale-ticket", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided claim ticket ids.");
            VerificationAssert.True(!callbackRedirect.Contains("ticketId=stale-ticket-id", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided ticket ids.");
            VerificationAssert.True(!callbackRedirect.Contains("receiptId=stale-receipt", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided receipt ids.");
            VerificationAssert.True(!callbackRedirect.Contains("installedBuildReceiptId=stale-installed-receipt", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided installed-build receipt ids.");
            VerificationAssert.True(!callbackRedirect.Contains("installationId=wrong-install", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided install identity.");
            VerificationAssert.True(!callbackRedirect.Contains("artifactId=wrong-artifact", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided artifact identity.");
            VerificationAssert.True(!callbackRedirect.Contains("channelId=wrong-channel", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided channel identity.");
            VerificationAssert.True(!callbackRedirect.Contains("version=wrong-version", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided version identity.");
            VerificationAssert.True(!callbackRedirect.Contains("platformId=wrong-platform", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-provided platform identity.");
            VerificationAssert.True(callbackRedirect.Contains("installationId=install-native", StringComparison.Ordinal), "App-local callback redirects should append authoritative claimed install identity.");
            VerificationAssert.True(!callbackRedirect.Contains("installLinkMode=claim_code", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-only install-link mode hints.");
            VerificationAssert.True(callbackRedirect.Contains("installLinkMode=browser_callback", StringComparison.Ordinal), "App-local callback redirects should append the grant callback install-link mode.");
            VerificationAssert.True(!callbackRedirect.Contains("installLinkTransport=browser_only", StringComparison.Ordinal), "App-local callback redirects should strip stale browser-only transport hints.");
            VerificationAssert.True(callbackRedirect.Contains("installLinkTransport=grant_callback", StringComparison.Ordinal), "App-local callback redirects should append the desktop-native grant callback transport.");

            string fragmentCallbackRedirect = BuildBrowserInstallCallbackRedirectUriForVerification(
                "http://127.0.0.1:47761/install-link/callback#state=desktop-fragment&nonce=fragment-proof&accessToken=fragment-access-token&grantId=fragment-grant&claimCode=fragment-claim&installLinkTransport=browser_only",
                "fresh-fragment-code",
                "install-native",
                "avalonia",
                "0.7.0-preview",
                "preview",
                "linux",
                "x64");
            VerificationAssert.True(fragmentCallbackRedirect.Contains("#state=desktop-fragment", StringComparison.Ordinal), "App-local callback redirects should preserve desktop listener fragment state.");
            VerificationAssert.True(fragmentCallbackRedirect.Contains("nonce=fragment-proof", StringComparison.Ordinal), "App-local callback redirects should preserve desktop listener fragment nonce.");
            VerificationAssert.True(fragmentCallbackRedirect.Contains("code=fresh-fragment-code", StringComparison.Ordinal), "App-local callback redirects with fragment state should use the freshly issued grant callback code.");
            VerificationAssert.True(!fragmentCallbackRedirect.Contains("accessToken=fragment-access-token", StringComparison.Ordinal), "App-local callback redirects should strip stale fragment grant tokens.");
            VerificationAssert.True(!fragmentCallbackRedirect.Contains("grantId=fragment-grant", StringComparison.Ordinal), "App-local callback redirects should strip stale fragment grant ids.");
            VerificationAssert.True(!fragmentCallbackRedirect.Contains("claimCode=fragment-claim", StringComparison.Ordinal), "App-local callback redirects should strip stale fragment claim codes.");
            VerificationAssert.True(!fragmentCallbackRedirect.Contains("installLinkTransport=browser_only", StringComparison.Ordinal), "App-local callback redirects should strip stale fragment browser-only transport hints.");
            VerificationAssert.True(fragmentCallbackRedirect.Contains("installLinkTransport=grant_callback", StringComparison.Ordinal), "App-local callback redirects should keep grant callback transport authoritative when fragment state is present.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static string BuildBrowserInstallCallbackRedirectUriForVerification(
        string callbackUri,
        string callbackCode,
        string installationId,
        string headId,
        string applicationVersion,
        string releaseChannel,
        string platform,
        string arch)
    {
        MethodInfo method = typeof(InstallLinkingController).GetMethod(
            "BuildBrowserInstallCallbackRedirectUri",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("InstallLinkingController callback redirect builder is missing.");
        return method.Invoke(
            null,
            [
                callbackUri,
                callbackCode,
                installationId,
                headId,
                applicationVersion,
                releaseChannel,
                platform,
                arch
            ]) as string
            ?? throw new InvalidOperationException("InstallLinkingController callback redirect builder returned no URI.");
    }

    private static PublicReleaseArtifactDto? ResolveContinuationArtifactForVerification(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto installation)
    {
        MethodInfo method = typeof(InstallLinkingController).GetMethod(
            "ResolveContinuationArtifact",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("InstallLinkingController continuation artifact resolver is missing.");
        return method.Invoke(null, [manifest, installation]) as PublicReleaseArtifactDto;
    }

    private static bool IsBrowserRailHrefForVerification(string href)
    {
        MethodInfo method = typeof(InstallLinkingController).GetMethod(
            "IsBrowserRailHref",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("InstallLinkingController browser rail detector is missing.");
        return method.Invoke(null, [href]) as bool?
            ?? throw new InvalidOperationException("InstallLinkingController browser rail detector returned no result.");
    }

    private static string BuildNativeSupportCaseActionHrefForVerification(
        string primaryActionHref,
        bool reporterActionNeeded = false,
        bool needsInstallUpdate = false,
        bool fixReadyOnLinkedInstall = false)
    {
        MethodInfo method = typeof(InstallLinkingController).GetMethod(
            "BuildNativeSupportCaseActionHref",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("InstallLinkingController native support action sanitizer is missing.");
        SupportCasePresentationViewModel item = new(
            Case: null!,
            StatusLabel: "Released",
            StageLabel: "Released",
            NextSafeAction: "Continue on the native rail.",
            ClosureSummary: "Closure summary",
            VerificationSummary: "Verification summary",
            DetailHref: "/account/support/case-native",
            PrimaryActionLabel: "Continue",
            PrimaryActionHref: primaryActionHref,
            UpdatedLabel: "2026-04-17 00:00 UTC",
            FixedReleaseLabel: null,
            AffectedInstallSummary: null,
            FollowUpLaneSummary: "Native install rail",
            ReleaseProgressSummary: "Release progress",
            TimelineHighlights: Array.Empty<SupportCaseTimelineHighlightViewModel>(),
            ReporterActionNeeded: reporterActionNeeded,
            CanVerifyFix: false,
            InstallReadinessSummary: "Install readiness",
            FixReadyOnLinkedInstall: fixReadyOnLinkedInstall,
            NeedsInstallUpdate: needsInstallUpdate,
            NeedsLinkedInstall: false);
        return method.Invoke(null, [item]) as string
            ?? throw new InvalidOperationException("InstallLinkingController native support action sanitizer returned no href.");
    }

    private static string? NormalizeNativeInstallRailHrefForVerification(string href)
    {
        MethodInfo method = typeof(InstallLinkingController).GetMethod(
            "NormalizeNativeInstallRailHref",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("InstallLinkingController native support action normalizer is missing.");
        return method.Invoke(null, [href]) as string;
    }


    private static void SeedClaimedInstall(InstallLinkingStore store)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
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
            store.ReceiptsById["receipt-other-platform"] = new DownloadReceiptDto(
                ReceiptId: "receipt-other-platform",
                ArtifactId: "avalonia-win-x64-installer",
                ArtifactLabel: "windows",
                FileName: "chummer-avalonia-win-x64-installer.exe",
                DownloadUrl: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                Channel: "preview",
                Version: "0.7.0-preview",
                Head: "avalonia",
                Platform: "windows",
                Arch: "x64",
                Kind: "installer",
                InstallAccessClass: InstallAccessClasses.AccountRequired,
                IssuedAtUtc: now.AddHours(-1),
                UserId: "usr-native",
                SubjectId: "subject.native",
                ClaimTicketId: "ticket-other-platform",
                ClaimCode: "ZZZZZ-YYYYY-XXXXX-WWWWW",
                ClaimTicketExpiresAtUtc: now.AddHours(1));
            store.ReceiptsById["receipt-same-artifact-newer-version"] = new DownloadReceiptDto(
                ReceiptId: "receipt-same-artifact-newer-version",
                ArtifactId: "avalonia-linux-x64-installer",
                ArtifactLabel: "linux",
                FileName: "chummer-avalonia-linux-x64-installer.deb",
                DownloadUrl: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                Channel: "preview",
                Version: "0.7.1-preview",
                Head: "avalonia",
                Platform: "linux",
                Arch: "x64",
                Kind: "installer",
                InstallAccessClass: InstallAccessClasses.AccountRequired,
                IssuedAtUtc: now.AddMinutes(-30),
                UserId: "usr-native",
                SubjectId: "subject.native",
                ClaimTicketId: "ticket-same-artifact-newer-version",
                ClaimCode: "QQQQQ-RRRRR-SSSSS-TTTTT",
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
