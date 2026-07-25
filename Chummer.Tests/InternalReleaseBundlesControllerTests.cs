using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InternalReleaseBundlesControllerTests
{
    private static readonly IReadOnlyList<CompleteShelfArtifact> CompleteShelfArtifacts =
    [
        new(
            ArtifactId: "avalonia-linux-x64-installer",
            Platform: "linux",
            PlatformId: "linux-x64",
            PlatformLabel: "Avalonia Desktop Linux x64",
            Arch: "x64",
            Kind: "installer",
            FileName: "chummer-avalonia-linux-x64-installer.deb",
            Bytes: "linux-live"u8.ToArray(),
            SigningStatus: "not_applicable",
            NotarizationStatus: "not_applicable"),
        new(
            ArtifactId: "avalonia-win-x64-installer",
            Platform: "windows",
            PlatformId: "windows-x64",
            PlatformLabel: "Avalonia Desktop Windows x64",
            Arch: "x64",
            Kind: "installer",
            FileName: "chummer-avalonia-win-x64-installer.exe",
            Bytes: "windows-live"u8.ToArray(),
            SigningStatus: "skipped_preview",
            NotarizationStatus: "not_applicable"),
        new(
            ArtifactId: "avalonia-osx-arm64-installer",
            Platform: "macos",
            PlatformId: "macos-arm64",
            PlatformLabel: "Avalonia Desktop macOS arm64",
            Arch: "arm64",
            Kind: "dmg",
            FileName: "chummer-avalonia-osx-arm64-installer.dmg",
            Bytes: "mac-live"u8.ToArray(),
            SigningStatus: "skipped_preview",
            NotarizationStatus: "skipped_preview")
    ];

    [Fact]
    public async Task ControllerFailsClosedWhenPreBindingGateWasBypassed()
    {
        using ControllerFixture fixture = new();
        ReleaseUploadTicketIssueResult issued = fixture.ReleaseUploadTickets.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = $"Bearer {issued.Ticket}";

        ActionResult<ReleaseBundlePromotionResult> result = await fixture.Controller.UploadBundle(bundle: null, CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, badRequest.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Contains("authorization", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(
            "CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED: \"false\"",
            File.ReadAllText(RepoPaths.FromRoot("docker-compose.public-edge.yml")),
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task DirectBundleActionRemainsDisabledWhenPreBindingContextIsPresent()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        ActionResult<ReleaseBundlePromotionResult> result = await fixture.Controller.UploadBundle(
            bundle: null,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status409Conflict, blocked.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(blocked.Value);
        Assert.Contains("permanently disabled", problem.Detail ?? string.Empty, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.False(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-activation-intent.json")));
    }

    [Fact]
    public void RepairCompatibilityMirrorsRejectsSingleUseUploadTicket()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);
        fixture.Controller.Request.Method = HttpMethods.Post;
        fixture.Controller.Request.Path =
            "/api/internal/releases/repair-compatibility-mirrors";
        ReleaseUploadAuthorizationContext authorization =
            Assert.IsType<ReleaseUploadAuthorizationContext>(
                new ReleaseUploadAuthorizationEvaluator(
                    fixture.Configuration,
                    fixture.ReleaseUploadTickets)
                .Evaluate(fixture.Controller.Request));
        fixture.Controller.HttpContext.Items[
            ReleaseUploadAuthorizationContext.HttpContextItemKey] = authorization;

        ActionResult<ReleaseCompatibilityMirrorRepairResult> result =
            fixture.Controller.RepairCompatibilityMirrors(CancellationToken.None);

        ObjectResult forbidden = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status403Forbidden, forbidden.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(forbidden.Value);
        Assert.Equal(
            "https://chummer.run/problems/release-bundle/fleet-auth-required",
            problem.Type);
    }

    [Fact]
    public void ReleaseUploadGateRecognizesCompatibilityMirrorRepairRoute()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path =
            "/api/internal/releases/repair-compatibility-mirrors";

        Assert.True(ReleaseUploadRequestGateMiddleware.TryMatch(
            context.Request,
            out ReleaseUploadRequestGateMiddleware.ReleaseUploadRoute route));
        Assert.Equal(
            ReleaseUploadRequestGateMiddleware.ReleaseUploadRoute.RepairCompatibilityMirrors,
            route);
    }

    [Fact]
    public async Task UploadSessionLifecyclePromotesBundleAndReturnsSignedInClaims()
    {
        using ControllerFixture fixture = new();
        ReleaseUploadTicketIssueResult uploadAuthorization = AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);

        await UploadFileAsync(fixture.Controller, created.SessionId, "releases.json", "application/json", BuildCompatibilityManifest());
        await UploadFileAsync(fixture.Controller, created.SessionId, "RELEASE_CHANNEL.generated.json", "application/json", BuildCanonicalManifest());
        await UploadFileAsync(fixture.Controller, created.SessionId, "release-evidence/public-promotion.json", "application/json", BuildPromotionEvidence());
        await UploadFileAsync(fixture.Controller, created.SessionId, "files/chummer-avalonia-osx-arm64-installer.dmg", "application/octet-stream", "mac-live"u8.ToArray());
        await UploadGovernedBuildProvenanceAsync(
            fixture.Controller,
            created.SessionId,
            [new MacBuildProvenanceSubject(
                "avalonia-osx-arm64-dmg",
                "avalonia",
                "chummer-avalonia-osx-arm64-installer.dmg",
                "mac-live"u8.ToArray())]);
        await UploadFileAsync(fixture.Controller, created.SessionId, "startup-smoke/startup-smoke-avalonia-macos-arm64.receipt.json", "application/json", BuildStartupSmokeReceipt());

        ActionResult<ReleaseBundlePromotionResult> completeResult = await fixture.Controller.CompleteUploadSession(created.SessionId, CancellationToken.None);
        ObjectResult ok = Assert.IsAssignableFrom<ObjectResult>(completeResult.Result);
        Assert.True(
            ok.StatusCode == StatusCodes.Status200OK,
            ok.Value is ProblemDetails problem
                ? $"Expected 200 but got {ok.StatusCode}: {problem.Detail}"
                : $"Expected 200 but got {ok.StatusCode}: {ok.Value}");
        ReleaseBundlePromotionResult promoted = Assert.IsType<ReleaseBundlePromotionResult>(ok.Value);
        Assert.Contains("avalonia-osx-arm64-dmg", promoted.PromotedArtifactIds);
        Assert.NotNull(promoted.SignedInInstallClaims);
        Assert.NotEmpty(promoted.SignedInInstallClaims!);
        ReleasePromotionInstallClaim signedInClaim = Assert.Single(promoted.SignedInInstallClaims!);
        Assert.NotNull(promoted.GenerationId);
        Assert.True(
            signedInClaim.InstallDispatchUrl.StartsWith(
                $"/downloads/g/{Uri.EscapeDataString(promoted.GenerationId!)}/install/",
                StringComparison.Ordinal),
            "Signed-in install URL must bind its generation without exposing the credential URL.");
        Assert.True(
            signedInClaim.InstallDispatchUrl.Contains(
                $"claimCode={Uri.EscapeDataString(signedInClaim.ClaimCode)}",
                StringComparison.Ordinal),
            "Signed-in install URL must carry its own claim without exposing bearer values.");
        string sessionPath = Path.Combine(fixture.SessionRoot, created.SessionId, "session.json");
        string durableSessionJson = File.ReadAllText(sessionPath);
        AssertDurableSessionDoesNotExposeBearerMaterial(
            durableSessionJson,
            signedInClaim.ClaimCode,
            uploadAuthorization.Ticket);
        using (JsonDocument durableSession = JsonDocument.Parse(durableSessionJson))
        {
            JsonElement durableCompletion = durableSession.RootElement.GetProperty("CompletionResult");
            Assert.Equal(
                JsonValueKind.Null,
                durableCompletion.GetProperty("SignedInInstallClaims").ValueKind);
            Assert.Equal(promoted.GenerationId, durableCompletion.GetProperty("GenerationId").GetString());
            Assert.Equal(promoted.ActivationReceiptId, durableCompletion.GetProperty("ActivationReceiptId").GetString());
            Assert.Equal(promoted.InventoryDigest, durableCompletion.GetProperty("InventoryDigest").GetString());

            string authorizationBinding = durableSession.RootElement.GetProperty("AuthorizationBinding").GetString()!;
            Assert.Matches("^[0-9a-f]{64}$", authorizationBinding);
        }

        ActionResult<ReleaseBundlePromotionResult> retriedCompletion = await fixture.Controller.CompleteUploadSession(
            created.SessionId,
            CancellationToken.None);
        OkObjectResult retriedOk = Assert.IsType<OkObjectResult>(retriedCompletion.Result);
        ReleaseBundlePromotionResult retried = Assert.IsType<ReleaseBundlePromotionResult>(retriedOk.Value);
        Assert.Equal(promoted.Version, retried.Version);
        Assert.Equal(promoted.PublishedAt, retried.PublishedAt);
        Assert.Equal(promoted.GenerationId, retried.GenerationId);
        Assert.Equal(promoted.ActivationReceiptId, retried.ActivationReceiptId);
        Assert.Equal(promoted.ActivatedAt, retried.ActivatedAt);
        Assert.Equal(promoted.InventoryDigest, retried.InventoryDigest);
        ReleasePromotionInstallClaim retriedClaim = Assert.Single(retried.SignedInInstallClaims!);
        Assert.False(
            string.Equals(signedInClaim.ClaimCode, retriedClaim.ClaimCode, StringComparison.Ordinal),
            "Repeated completion must issue a fresh claim without exposing either bearer value.");
        string retriedSessionJson = File.ReadAllText(sessionPath);
        AssertDurableSessionDoesNotExposeBearerMaterial(
            retriedSessionJson,
            signedInClaim.ClaimCode,
            retriedClaim.ClaimCode,
            uploadAuthorization.Ticket);

        ObjectResult consumed = Assert.IsType<ObjectResult>(fixture.Controller.CreateUploadSession().Result);
        Assert.Equal(StatusCodes.Status409Conflict, consumed.StatusCode);
        ProblemDetails consumedProblem = Assert.IsType<ProblemDetails>(consumed.Value);
        Assert.Contains("already been consumed", consumedProblem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    private static void AssertDurableSessionDoesNotExposeBearerMaterial(
        string durableSessionJson,
        params string[] rawSecrets)
    {
        using JsonDocument durableSession = JsonDocument.Parse(durableSessionJson);
        JsonElement durableCompletion = durableSession.RootElement.GetProperty("CompletionResult");
        Assert.True(
            !durableCompletion.TryGetProperty("SignedInInstallClaims", out JsonElement durableClaims)
            || durableClaims.ValueKind == JsonValueKind.Null,
            "Durable completion metadata must not retain signed-in bearer claims.");

        bool containsRawBearerMaterial = rawSecrets
                                             .Where(static secret => !string.IsNullOrEmpty(secret))
                                             .Any(secret => durableSessionJson.Contains(secret, StringComparison.Ordinal))
                                         || durableSessionJson.Contains("Bearer ", StringComparison.OrdinalIgnoreCase)
                                         || durableSessionJson.Contains("claimCode=", StringComparison.OrdinalIgnoreCase)
                                         || ContainsSensitiveIdentityProperty(durableSession.RootElement);
        Assert.False(
            containsRawBearerMaterial,
            "Durable session metadata must not expose bearer or identity material.");
    }

    private static bool ContainsSensitiveIdentityProperty(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Array)
        {
            return element.EnumerateArray().Any(ContainsSensitiveIdentityProperty);
        }

        if (element.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        foreach (JsonProperty property in element.EnumerateObject())
        {
            if (property.Name.Equals("DisplayName", StringComparison.OrdinalIgnoreCase)
                || property.Name.Equals("Email", StringComparison.OrdinalIgnoreCase)
                || property.Name.Equals("AccessToken", StringComparison.OrdinalIgnoreCase)
                || property.Name.Equals("ClaimCode", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }

            if (ContainsSensitiveIdentityProperty(property.Value))
            {
                return true;
            }
        }

        return false;
    }

    [Fact]
    public async Task CompletionFailsBeforeJournalPreparationWhenDestinationDisappearsAfterUpload()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);
        string sessionId = await UploadMinimalValidSessionAsync(fixture);
        Directory.Delete(fixture.DownloadsRoot, recursive: true);

        ActionResult<ReleaseBundlePromotionResult> result = await fixture.Controller.CompleteUploadSession(
            sessionId,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, blocked.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(blocked.Value);
        Assert.Contains("publication_destination_unavailable", problem.Detail ?? string.Empty, StringComparison.Ordinal);
        Assert.False(Directory.Exists(fixture.DownloadsRoot));
    }

    [Fact]
    public async Task CompletionFailsBeforePromotionWhenAnotherActivationBecomesUnresolved()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);
        string sessionId = await UploadMinimalValidSessionAsync(fixture);
        const string blockerAuthorization =
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        ReleaseUploadSession blocker = fixture.UploadSessions.CreateSession(
            blockerAuthorization,
            singleUseAuthorization: false);
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.UploadSessions.BeginCompletion(blocker.SessionId, blockerAuthorization))
        {
            byte[] targetPointerBytes = "blocked-target-pointer"u8.ToArray();
            completion.RecordActivationIntent(new ReleaseActivationIntent(
                Operation: "promotion",
                PreviousGenerationId: null,
                PreviousPointerSha256: null,
                GenerationId: "blocked-generation",
                ActivationReceiptId: "blocked-receipt",
                ReleaseVersion: "blocked-release",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                InventoryDigest: "sha256:" + new string('a', 64),
                PointerSha256: $"sha256:{Convert.ToHexStringLower(SHA256.HashData(targetPointerBytes))}",
                PreparedAtUtc: DateTimeOffset.UtcNow,
                PreviousPointerBase64: null,
                TargetPointerBase64: Convert.ToBase64String(targetPointerBytes)));
        }

        ActionResult<ReleaseBundlePromotionResult> result = await fixture.Controller.CompleteUploadSession(
            sessionId,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, blocked.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(blocked.Value);
        Assert.Contains("activation_session_unresolved", problem.Detail ?? string.Empty, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.False(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-activation-intent.json")));
        Assert.False(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-writer-policy.json")));
    }

    [Fact]
    public async Task FirstCutoverRejectsArbitraryPreparedGenerationFootprints()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);
        string sessionId = await UploadMinimalValidSessionAsync(fixture);
        string orphan = Path.Combine(fixture.DownloadsRoot, "generations", "arbitrary-orphan");
        Directory.CreateDirectory(orphan);
        File.WriteAllText(Path.Combine(orphan, "unexpected.bin"), "orphan");

        ActionResult<ReleaseBundlePromotionResult> result = await fixture.Controller.CompleteUploadSession(
            sessionId,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, blocked.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(blocked.Value);
        Assert.Contains("release_shelf_migration_posture_invalid", problem.Detail ?? string.Empty, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        Assert.False(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-writer-policy.json")));
    }

    [Fact]
    public async Task PublishingSessionWithoutJournalIsDurablyAbortedAndCanBeRetriedAfterRestart()
    {
        bool injectedCrash = false;
        using ControllerFixture fixture = new(checkpoint =>
        {
            if (!injectedCrash
                && checkpoint == ReleaseBundlePromotionService.PromotionCheckpoint.ActivationIntentRecorded)
            {
                injectedCrash = true;
                throw new InvalidOperationException("simulated process death after durable session intent");
            }
        });
        AuthenticateController(fixture);
        string sessionId = await UploadMinimalValidSessionAsync(fixture);

        ActionResult<ReleaseBundlePromotionResult> interrupted = await fixture.Controller.CompleteUploadSession(
            sessionId,
            CancellationToken.None);

        ObjectResult unknown = Assert.IsType<ObjectResult>(interrupted.Result);
        Assert.Equal(StatusCodes.Status409Conflict, unknown.StatusCode);
        ProblemDetails unknownProblem = Assert.IsType<ProblemDetails>(unknown.Value);
        Assert.Contains("may already be live", unknownProblem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        ReleaseUploadSession interruptedSession = fixture.ReadSessionMetadata(sessionId);
        Assert.True(interruptedSession.Publishing);
        Assert.False(interruptedSession.Completed);
        Assert.NotNull(interruptedSession.ActivationIntent);
        Assert.False(File.Exists(Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-activation-intent.json")));
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));

        fixture.RestartController();
        ActionResult<ReleaseBundlePromotionResult> reconciled = await fixture.Controller.CompleteUploadSession(
            sessionId,
            CancellationToken.None);

        ObjectResult aborted = Assert.IsType<ObjectResult>(reconciled.Result);
        Assert.Equal(StatusCodes.Status409Conflict, aborted.StatusCode);
        ProblemDetails abortedProblem = Assert.IsType<ProblemDetails>(aborted.Value);
        Assert.Contains("durably proven not published", abortedProblem.Detail ?? string.Empty, StringComparison.Ordinal);
        ReleaseUploadSession repairedSession = fixture.ReadSessionMetadata(sessionId);
        Assert.False(repairedSession.Publishing);
        Assert.False(repairedSession.Completed);
        Assert.Null(repairedSession.ActivationIntent);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
        string generationsRoot = Path.Combine(fixture.DownloadsRoot, "generations");
        Assert.True(
            !Directory.Exists(generationsRoot)
            || !Directory.EnumerateFileSystemEntries(generationsRoot).Any());

        ActionResult<ReleaseBundlePromotionResult> retried = await fixture.Controller.CompleteUploadSession(
            sessionId,
            CancellationToken.None);

        OkObjectResult published = Assert.IsType<OkObjectResult>(retried.Result);
        ReleaseBundlePromotionResult result = Assert.IsType<ReleaseBundlePromotionResult>(published.Value);
        Assert.Equal("run-test", result.Version);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "current.json")));
    }

    [Fact]
    public async Task FleetReconciliationRecoversExpiredRotatedTicketSessionWithoutGrantingPublishAuthority()
    {
        bool failDurabilityConfirmationOnce = true;
        using ControllerFixture fixture = new(
            postActivationDirectoryFlush: _ =>
            {
                if (failDurabilityConfirmationOnce)
                {
                    failDurabilityConfirmationOnce = false;
                    throw new IOException(
                        "simulated process loss after pointer activation");
                }
            });
        ReleaseUploadTicketIssueResult originalTicket = AuthenticateController(fixture);
        string sessionId = await UploadMinimalValidSessionAsync(fixture);

        ActionResult<ReleaseBundlePromotionResult> interrupted =
            await fixture.Controller.CompleteUploadSession(sessionId, CancellationToken.None);

        ObjectResult unknown = Assert.IsType<ObjectResult>(interrupted.Result);
        Assert.Equal(StatusCodes.Status409Conflict, unknown.StatusCode);
        ReleaseUploadSession unresolved = fixture.ReadSessionMetadata(sessionId);
        Assert.True(unresolved.Publishing);
        Assert.NotNull(unresolved.ActivationIntent);
        fixture.ExpireSessionAuthorization(sessionId);
        fixture.Configuration["CHUMMER_RELEASE_UPLOAD_TICKET_REVOCATION_EPOCH"] = "rotated-2";
        ReleaseUploadTicketService rotatedTickets = fixture.CreateTicketServiceForCurrentEpoch();

        (ActionResult<ReleaseBundlePromotionResult>? expiredResult, int expiredStatus, bool expiredNext) =
            await InvokeThroughReleaseUploadGateAsync(
                fixture,
                rotatedTickets,
                originalTicket.Ticket,
                $"/api/internal/releases/upload-sessions/{sessionId}/complete",
                controller => controller.CompleteUploadSession(sessionId, CancellationToken.None));
        Assert.False(expiredNext);
        Assert.Null(expiredResult);
        Assert.Equal(StatusCodes.Status401Unauthorized, expiredStatus);

        ReleaseUploadTicketIssueResult unrelatedTicket = rotatedTickets.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-new-ticket",
            DisplayName: "New operator ticket",
            Email: "new-ticket@example.com",
            Roles: ["operator"],
            AccessToken: "new-token"));
        (ActionResult<ReleaseBundlePromotionResult>? hijackResult, _, bool hijackNext) =
            await InvokeThroughReleaseUploadGateAsync(
                fixture,
                rotatedTickets,
                unrelatedTicket.Ticket,
                $"/api/internal/releases/upload-sessions/{sessionId}/complete",
                controller => controller.CompleteUploadSession(sessionId, CancellationToken.None));
        Assert.True(hijackNext);
        ObjectResult hijackRejected = Assert.IsType<ObjectResult>(hijackResult!.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, hijackRejected.StatusCode);
        Assert.True(fixture.ReadSessionMetadata(sessionId).Publishing);

        const string fleetRecoveryToken =
            "fleet-recovery-token-that-is-not-an-upload-ticket";
        fixture.Configuration["FLEET_INTERNAL_API_TOKEN"] = fleetRecoveryToken;
        (ActionResult<ReleaseBundlePromotionResult>? recoveredResult, _, bool recoveredNext) =
            await InvokeThroughReleaseUploadGateAsync(
                fixture,
                rotatedTickets,
                fleetRecoveryToken,
                $"/api/internal/releases/upload-sessions/{sessionId}/reconcile",
                controller => Task.FromResult(
                    controller.ReconcileUploadSession(sessionId)));

        Assert.True(recoveredNext);
        OkObjectResult recovered = Assert.IsType<OkObjectResult>(recoveredResult!.Result);
        ReleaseBundlePromotionResult promoted =
            Assert.IsType<ReleaseBundlePromotionResult>(recovered.Value);
        Assert.Equal("run-test", promoted.Version);
        ReleaseUploadSession completed = fixture.ReadSessionMetadata(sessionId);
        Assert.True(completed.Completed);
        Assert.False(completed.Publishing);
        Assert.NotNull(completed.ActivationAcknowledgedAtUtc);

        (ActionResult<ReleaseBundlePromotionResult>? replayResult, _, bool replayNext) =
            await InvokeThroughReleaseUploadGateAsync(
                fixture,
                rotatedTickets,
                fleetRecoveryToken,
                $"/api/internal/releases/upload-sessions/{sessionId}/reconcile",
                controller => Task.FromResult(
                    controller.ReconcileUploadSession(sessionId)));
        Assert.True(replayNext);
        ObjectResult replayRejected = Assert.IsType<ObjectResult>(replayResult!.Result);
        Assert.Equal(StatusCodes.Status409Conflict, replayRejected.StatusCode);
    }

    [Fact]
    public async Task UploadSessionPrevalidationFailureLeavesSessionRepairableBeforePublication()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);

        await UploadFileAsync(fixture.Controller, created.SessionId, "releases.json", "application/json", "{}"u8.ToArray());
        await UploadFileAsync(fixture.Controller, created.SessionId, "RELEASE_CHANNEL.generated.json", "application/json", BuildCanonicalManifest());
        await UploadFileAsync(fixture.Controller, created.SessionId, "release-evidence/public-promotion.json", "application/json", BuildPromotionEvidence());
        await UploadFileAsync(fixture.Controller, created.SessionId, "files/chummer-avalonia-osx-arm64-installer.dmg", "application/octet-stream", "mac-live"u8.ToArray());
        await UploadGovernedBuildProvenanceAsync(
            fixture.Controller,
            created.SessionId,
            [new MacBuildProvenanceSubject(
                "avalonia-osx-arm64-dmg",
                "avalonia",
                "chummer-avalonia-osx-arm64-installer.dmg",
                "mac-live"u8.ToArray())]);
        await UploadFileAsync(fixture.Controller, created.SessionId, "startup-smoke/startup-smoke-avalonia-macos-arm64.receipt.json", "application/json", BuildStartupSmokeReceipt());

        ActionResult<ReleaseBundlePromotionResult> failedCompletion = await fixture.Controller.CompleteUploadSession(
            created.SessionId,
            CancellationToken.None);
        ObjectResult rejected = Assert.IsType<ObjectResult>(failedCompletion.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, rejected.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(rejected.Value);
        Assert.Equal("Upload session promotion rejected", problem.Title);
        Assert.False(File.Exists(Path.Combine(
            fixture.Configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]!,
            "current.json")));

        await UploadFileAsync(
            fixture.Controller,
            created.SessionId,
            "releases.json",
            "application/json",
            BuildCompatibilityManifest());

        ActionResult<ReleaseBundlePromotionResult> repairedCompletion = await fixture.Controller.CompleteUploadSession(
            created.SessionId,
            CancellationToken.None);
        ObjectResult repaired = Assert.IsAssignableFrom<ObjectResult>(repairedCompletion.Result);
        Assert.True(
            repaired.StatusCode == StatusCodes.Status200OK,
            repaired.Value is ProblemDetails repairedProblem
                ? $"Expected repaired session to publish but got {repaired.StatusCode}: {repairedProblem.Detail}"
                : $"Expected repaired session to publish but got {repaired.StatusCode}: {repaired.Value}");
        ReleaseBundlePromotionResult promoted = Assert.IsType<ReleaseBundlePromotionResult>(repaired.Value);
        Assert.Equal("run-test", promoted.Version);
    }

    [Fact]
    public async Task UploadSessionRejectsASecondValidTicketThatDidNotCreateIt()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);
        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);

        AuthenticateController(fixture);
        FormFile formFile = BuildTextFormFile("releases.json", "application/json", "{}");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response =
            await fixture.Controller.UploadSessionFile(
                created.SessionId,
                formFile,
                "releases.json",
                CancellationToken.None);

        ObjectResult rejected = Assert.IsType<ObjectResult>(response.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, rejected.StatusCode);
        ProblemDetails problem = Assert.IsType<ProblemDetails>(rejected.Value);
        Assert.Contains("authorization does not match", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionCompletionPreservesReviewRequiredPostureForStaleProof()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        byte[] compatibilityManifest = BuildStaleProofCompatibilityManifest();
        byte[] canonicalManifest = BuildStaleProofCanonicalManifest();
        using (JsonDocument uploaded = JsonDocument.Parse(canonicalManifest))
        {
            AssertIncomingReviewRequiredStaleProjection(uploaded.RootElement);
        }

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);

        await UploadFileAsync(fixture.Controller, created.SessionId, "releases.json", "application/json", compatibilityManifest);
        await UploadFileAsync(fixture.Controller, created.SessionId, "RELEASE_CHANNEL.generated.json", "application/json", canonicalManifest);
        await UploadFileAsync(
            fixture.Controller,
            created.SessionId,
            "release-evidence/public-promotion.json",
            "application/json",
            BuildCompleteShelfPromotionEvidence());
        foreach (CompleteShelfArtifact artifact in CompleteShelfArtifacts)
        {
            await UploadFileAsync(
                fixture.Controller,
                created.SessionId,
                $"files/{artifact.FileName}",
                "application/octet-stream",
                artifact.Bytes);
            await UploadFileAsync(
                fixture.Controller,
                created.SessionId,
                $"startup-smoke/startup-smoke-avalonia-{artifact.Platform}-{artifact.Arch}.receipt.json",
                "application/json",
                BuildCompleteShelfStartupSmokeReceipt(artifact));
        }
        await UploadGovernedBuildProvenanceAsync(
            fixture.Controller,
            created.SessionId,
            CompleteShelfArtifacts
                .Where(static artifact =>
                    MacBuildProvenanceTestFixture.IsGovernedDesktopPlatform(artifact.Platform))
                .Select(static artifact => new MacBuildProvenanceSubject(
                    artifact.ArtifactId,
                    "avalonia",
                    artifact.FileName,
                    artifact.Bytes,
                    artifact.Platform)));

        ActionResult<ReleaseBundlePromotionResult> completeResult = await fixture.Controller.CompleteUploadSession(
            created.SessionId,
            CancellationToken.None);
        ObjectResult ok = Assert.IsAssignableFrom<ObjectResult>(completeResult.Result);
        Assert.True(
            ok.StatusCode == StatusCodes.Status200OK,
            ok.Value is ProblemDetails problem
                ? $"Expected 200 but got {ok.StatusCode}: {problem.Detail}"
                : $"Expected 200 but got {ok.StatusCode}: {ok.Value}");

        using JsonDocument servedCanonical = fixture.ReadCanonicalManifest();
        AssertReviewRequiredStaleProjection(servedCanonical.RootElement);
    }

    [Fact]
    public async Task UploadSessionFileRejectsExpiredSession()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        fixture.WriteSessionMetadata(new ReleaseUploadSession(
            created.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        FormFile formFile = BuildTextFormFile("releases.json", "application/json", "{}");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await fixture.Controller.UploadSessionFile(
            created.SessionId,
            formFile,
            "releases.json",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session file rejected", problem.Title);
        Assert.Contains("upload session has expired", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionFileRejectsInvalidSessionId()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        FormFile formFile = BuildTextFormFile("releases.json", "application/json", "{}{");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await fixture.Controller.UploadSessionFile(
            "not-a-guid",
            formFile,
            "releases.json",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session file rejected", problem.Title);
        Assert.Contains("sessionId must be a valid GUID", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionChunkRejectsInvalidSessionId()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        FormFile chunk = BuildTextFormFile("chunk.bin", "application/octet-stream", "chunk");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadChunkStoredResponse> response = await fixture.Controller.UploadSessionChunk(
            "bad-session-id",
            chunk,
            "files/chummer-avalonia-win-x64.exe",
            chunkIndex: 0,
            totalChunks: 1,
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session chunk rejected", problem.Title);
        Assert.Contains("sessionId must be a valid GUID", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CompleteUploadSessionRejectsInvalidSessionId()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        ActionResult<ReleaseBundlePromotionResult> response = await fixture.Controller.CompleteUploadSession(
            "0x-not-a-guid",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session promotion rejected", problem.Title);
        Assert.Contains("sessionId must be a valid GUID", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionChunkRejectsExpiredSession()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        fixture.WriteSessionMetadata(new ReleaseUploadSession(
            created.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        FormFile formFile = BuildTextFormFile("chunk.bin", "application/octet-stream", "chunk");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadChunkStoredResponse> response = await fixture.Controller.UploadSessionChunk(
            created.SessionId,
            formFile,
            "files/chummer-avalonia-osx-arm64-installer.dmg",
            chunkIndex: 0,
            totalChunks: 1,
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session chunk rejected", problem.Title);
        Assert.Contains("upload session has expired", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CompleteUploadSessionRejectsExpiredSession()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        fixture.WriteSessionMetadata(new ReleaseUploadSession(
            created.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        ActionResult<ReleaseBundlePromotionResult> response = await fixture.Controller.CompleteUploadSession(
            created.SessionId,
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session promotion rejected", problem.Title);
        Assert.Contains("upload session has expired", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionRejectsTamperedSessionMetadata()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        string tamperedSessionId = Guid.NewGuid().ToString("N");
        fixture.WriteSessionMetadata(created.SessionId, new ReleaseUploadSession(
            tamperedSessionId,
            DateTimeOffset.UtcNow.AddHours(6),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        FormFile formFile = BuildTextFormFile("releases.json", "application/json", "{}");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await fixture.Controller.UploadSessionFile(
            created.SessionId,
            formFile,
            "releases.json",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session file rejected", problem.Title);
        Assert.Contains("metadata is invalid", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    private static async Task UploadFileAsync(
        InternalReleaseBundlesController controller,
        string sessionId,
        string relativePath,
        string contentType,
        byte[] bytes)
    {
        FormFile formFile = new(new MemoryStream(bytes), 0, bytes.Length, "file", Path.GetFileName(relativePath))
        {
            Headers = new HeaderDictionary(),
            ContentType = contentType
        };
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await controller.UploadSessionFile(
            sessionId,
            formFile,
            relativePath,
            CancellationToken.None);
        Assert.IsType<OkObjectResult>(response.Result);
    }

    private static async Task<string> UploadMinimalValidSessionAsync(ControllerFixture fixture)
    {
        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(
            fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(
            sessionResponse.Value);
        await UploadFileAsync(
            fixture.Controller,
            created.SessionId,
            "releases.json",
            "application/json",
            BuildCompatibilityManifest());
        await UploadFileAsync(
            fixture.Controller,
            created.SessionId,
            "RELEASE_CHANNEL.generated.json",
            "application/json",
            BuildCanonicalManifest());
        await UploadFileAsync(
            fixture.Controller,
            created.SessionId,
            "release-evidence/public-promotion.json",
            "application/json",
            BuildPromotionEvidence());
        await UploadFileAsync(
            fixture.Controller,
            created.SessionId,
            "files/chummer-avalonia-osx-arm64-installer.dmg",
            "application/octet-stream",
            "mac-live"u8.ToArray());
        await UploadGovernedBuildProvenanceAsync(
            fixture.Controller,
            created.SessionId,
            [new MacBuildProvenanceSubject(
                "avalonia-osx-arm64-dmg",
                "avalonia",
                "chummer-avalonia-osx-arm64-installer.dmg",
                "mac-live"u8.ToArray())]);
        await UploadFileAsync(
            fixture.Controller,
            created.SessionId,
            "startup-smoke/startup-smoke-avalonia-macos-arm64.receipt.json",
            "application/json",
            BuildStartupSmokeReceipt());
        return created.SessionId;
    }

    private static async Task UploadGovernedBuildProvenanceAsync(
        InternalReleaseBundlesController controller,
        string sessionId,
        IEnumerable<MacBuildProvenanceSubject> subjects)
    {
        foreach ((string relativePath, byte[] bytes) in MacBuildProvenanceTestFixture.CreateFiles(subjects))
        {
            await UploadFileAsync(
                controller,
                sessionId,
                relativePath,
                "application/json",
                bytes);
        }
    }

    private static FormFile BuildTextFormFile(string fileName, string contentType, string text)
    {
        return BuildByteFormFile(fileName, contentType, System.Text.Encoding.UTF8.GetBytes(text));
    }

    private static FormFile BuildByteFormFile(string fileName, string contentType, byte[] bytes)
    {
        return new FormFile(new MemoryStream(bytes), 0, bytes.Length, "file", fileName)
        {
            Headers = new HeaderDictionary(),
            ContentType = contentType
        };
    }

    private static ReleaseUploadTicketIssueResult AuthenticateController(ControllerFixture fixture)
    {
        ReleaseUploadTicketIssueResult issued = fixture.ReleaseUploadTickets.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = $"Bearer {issued.Ticket}";
        var evaluator = new ReleaseUploadAuthorizationEvaluator(
            fixture.Configuration,
            fixture.ReleaseUploadTickets);
        ReleaseUploadAuthorizationContext authorization = Assert.IsType<ReleaseUploadAuthorizationContext>(
            evaluator.Evaluate(fixture.Controller.ControllerContext.HttpContext.Request));
        fixture.Controller.ControllerContext.HttpContext.Items[
            ReleaseUploadAuthorizationContext.HttpContextItemKey] = authorization;
        return issued;
    }

    private static async Task<(
        ActionResult<ReleaseBundlePromotionResult>? Result,
        int ResponseStatus,
        bool NextCalled)> InvokeThroughReleaseUploadGateAsync(
        ControllerFixture fixture,
        ReleaseUploadTicketService ticketService,
        string bearer,
        string path,
        Func<InternalReleaseBundlesController, Task<ActionResult<ReleaseBundlePromotionResult>>> action)
    {
        ActionResult<ReleaseBundlePromotionResult>? result = null;
        bool nextCalled = false;
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Post;
        context.Request.Scheme = "https";
        context.Request.Host = new HostString("chummer.run");
        context.Request.Path = path;
        context.Request.Headers.Authorization = $"Bearer {bearer}";
        context.Response.Body = new MemoryStream();
        var middleware = new ReleaseUploadRequestGateMiddleware(async admittedContext =>
        {
            nextCalled = true;
            fixture.Controller.ControllerContext = new ControllerContext
            {
                HttpContext = admittedContext
            };
            result = await action(fixture.Controller);
        });
        var evaluator = new ReleaseUploadAuthorizationEvaluator(
            fixture.Configuration,
            ticketService);
        var admission = new ReleaseUploadAdmissionService(
            fixture.Configuration,
            fixture.UploadOptions);

        await middleware.InvokeAsync(
            context,
            evaluator,
            admission,
            fixture.UploadOptions);

        return (result, context.Response.StatusCode, nextCalled);
    }

    private static byte[] BuildCompatibilityManifest()
        => BuildManifestWithReleaseProof("""
{
  "version": "run-test",
  "channel": "preview",
  "publishedAt": "2026-04-02T06:00:00Z",
  "status": "published",
  "registryBoundaryCoverage": {
    "compatibility": {
      "compatibleArtifactCount": 1,
      "compatibleRuntimeBundleHeadCount": 0,
      "compatibleExchangeArtifactCount": 0,
      "unknownArtifactCount": 0,
      "unknownRuntimeBundleHeadCount": 0,
      "summary": "Compatibility boundary tracks 1 compatible artifact, 0 compatible runtime bundle heads, and 0 compatible exchange-lineage rows while 0 artifact rows and 0 runtime bundle heads remain unknown."
    }
  },
  "downloads": [
    {
      "id": "avalonia-osx-arm64-dmg",
      "platform": "Avalonia Desktop macOS arm64",
      "url": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
      "sha256": "6f63f1170506eaca21ee53bf90415ee7ed4f40937c505f140137259e27a65bab",
      "sizeBytes": 8,
      "head": "avalonia",
      "platformId": "macos-arm64",
      "rid": "osx-arm64",
      "arch": "arm64",
      "kind": "dmg",
      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
      "installAccessClass": "account_required"
    }
  ]
}
""");

    private static byte[] BuildCanonicalManifest()
        => BuildManifestWithReleaseProof("""
{
  "schemaVersion": 1,
  "product": "chummer",
  "channelId": "preview",
  "version": "run-test",
  "publishedAt": "2026-04-02T06:00:00Z",
  "status": "published",
  "registryBoundaryCoverage": {
    "compatibility": {
      "compatibleArtifactCount": 1,
      "compatibleRuntimeBundleHeadCount": 0,
      "compatibleExchangeArtifactCount": 0,
      "unknownArtifactCount": 0,
      "unknownRuntimeBundleHeadCount": 0,
      "summary": "Compatibility boundary tracks 1 compatible artifact, 0 compatible runtime bundle heads, and 0 compatible exchange-lineage rows while 0 artifact rows and 0 runtime bundle heads remain unknown."
    }
  },
  "artifacts": [
    {
      "artifactId": "avalonia-osx-arm64-dmg",
      "head": "avalonia",
      "platform": "macos",
      "rid": "osx-arm64",
      "arch": "arm64",
      "kind": "dmg",
      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
      "downloadUrl": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
      "sha256": "6f63f1170506eaca21ee53bf90415ee7ed4f40937c505f140137259e27a65bab",
      "sizeBytes": 8,
      "platformLabel": "Avalonia Desktop macOS arm64",
      "installAccessClass": "account_required"
    }
  ]
}
""");

    private static byte[] BuildManifestWithReleaseProof(string manifestJson)
    {
        JsonObject root = JsonNode.Parse(manifestJson)?.AsObject()
            ?? throw new InvalidDataException("Expected release manifest JSON object.");
        root["releaseProof"] = ReleaseProofEvidenceTestData.CreateReleaseProof(
            new DateTimeOffset(2026, 4, 2, 6, 0, 0, TimeSpan.Zero),
            installerRouteExtensions: ["/downloads/install/avalonia-osx-arm64-dmg"]);
        return System.Text.Encoding.UTF8.GetBytes(
            root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private static byte[] BuildStaleProofCompatibilityManifest()
    {
        JsonObject root = JsonNode.Parse(System.Text.Encoding.UTF8.GetString(BuildCompatibilityManifest()))?.AsObject()
            ?? throw new InvalidDataException("Expected compatibility manifest JSON object.");
        root["version"] = "run-20260713-113227";
        root["publishedAt"] = "2026-07-13T11:34:17Z";
        root["status"] = "published";
        root["rolloutState"] = "public_release_review_required";
        root["supportabilityState"] = "review_required";
        root["releaseProof"] = BuildStaleProofReleaseProof();
        root["downloads"] = BuildCompleteShelfCompatibilityDownloads();
        JsonObject boundary = root["registryBoundaryCoverage"]?.AsObject()
            ?? throw new InvalidDataException("Expected registry boundary coverage object.");
        JsonObject compatibility = boundary["compatibility"]?.AsObject()
            ?? throw new InvalidDataException("Expected compatibility boundary object.");
        compatibility["compatibleArtifactCount"] = CompleteShelfArtifacts.Count;
        compatibility["summary"] = "Compatibility boundary covers the complete staged Avalonia primary shelf.";
        return System.Text.Encoding.UTF8.GetBytes(root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private static byte[] BuildStaleProofCanonicalManifest()
    {
        JsonObject root = JsonNode.Parse(System.Text.Encoding.UTF8.GetString(BuildCanonicalManifest()))?.AsObject()
            ?? throw new InvalidDataException("Expected canonical manifest JSON object.");
        root["channel"] = "preview";
        root["channelId"] = "preview";
        root["version"] = "run-20260713-113227";
        root["publishedAt"] = "2026-07-13T11:34:17Z";
        root["rolloutState"] = "public_release_review_required";
        root["supportabilityState"] = "review_required";
        root["releaseProof"] = BuildStaleProofReleaseProof();
        root["artifacts"] = BuildCompleteShelfCanonicalArtifacts();
        JsonObject proofFreshness = ReleaseProofEvidenceTestData.CreateFreshnessFacts(
            BuildStaleProofReleaseProof(),
            new DateTimeOffset(2026, 7, 13, 11, 34, 17, TimeSpan.Zero));
        proofFreshness["status"] = "stale";
        root["publicTrustMetrics"] = new JsonObject
        {
            ["proofFreshness"] = proofFreshness,
            ["releaseChannel"] = new JsonObject
            {
                ["supportabilityState"] = "review_required"
            }
        };

        JsonObject boundary = root["registryBoundaryCoverage"]?.AsObject()
            ?? throw new InvalidDataException("Expected registry boundary coverage object.");
        JsonObject compatibility = boundary["compatibility"]?.AsObject()
            ?? throw new InvalidDataException("Expected compatibility boundary object.");
        compatibility["compatibleArtifactCount"] = CompleteShelfArtifacts.Count;
        compatibility["summary"] = "Compatibility boundary covers the complete staged Avalonia primary shelf.";
        boundary["releaseChannel"] = new JsonObject
        {
            ["supportabilityState"] = "review_required"
        };
        return System.Text.Encoding.UTF8.GetBytes(root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private static JsonObject BuildStaleProofReleaseProof()
        => ReleaseProofEvidenceTestData.CreateReleaseProof(
            new DateTimeOffset(2026, 7, 2, 7, 57, 5, TimeSpan.Zero),
            installerRouteExtensions: CompleteShelfArtifacts.Select(
                static artifact => $"/downloads/install/{artifact.ArtifactId}"));

    private static void AssertIncomingReviewRequiredStaleProjection(JsonElement root)
    {
        Assert.Equal("run-20260713-113227", root.GetProperty("version").GetString());
        Assert.Equal("2026-07-13T11:34:17Z", root.GetProperty("publishedAt").GetString());
        AssertReviewRequiredStaleFields(root);
    }

    private static void AssertReviewRequiredStaleProjection(JsonElement root)
    {
        Assert.Equal("run-20260713-113227", root.GetProperty("version").GetString());
        Assert.Equal("2026-07-13T11:34:17Z", root.GetProperty("publishedAt").GetString());

        JsonElement coverage = root.GetProperty("desktopTupleCoverage");
        Assert.True(coverage.GetProperty("complete").GetBoolean());
        Assert.Equal(0, coverage.GetProperty("missingRequiredPlatforms").GetArrayLength());
        Assert.Equal(0, coverage.GetProperty("missingRequiredPlatformHeadRidTuples").GetArrayLength());

        AssertReviewRequiredStaleFields(root);
    }

    private static void AssertReviewRequiredStaleFields(JsonElement root)
    {
        Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
        JsonElement metrics = root.GetProperty("publicTrustMetrics");
        Assert.Equal("stale", metrics.GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal(
            "review_required",
            metrics.GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "review_required",
            root.GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("supportabilityState")
                .GetString());
    }

    private static JsonArray BuildCompleteShelfCompatibilityDownloads()
    {
        JsonArray downloads = [];
        foreach (CompleteShelfArtifact artifact in CompleteShelfArtifacts)
        {
            downloads.Add(new JsonObject
            {
                ["id"] = artifact.ArtifactId,
                ["platform"] = artifact.PlatformLabel,
                ["url"] = $"/downloads/files/{artifact.FileName}",
                ["sha256"] = Sha256For(artifact),
                ["sizeBytes"] = artifact.Bytes.LongLength,
                ["head"] = "avalonia",
                ["platformId"] = artifact.PlatformId,
                ["rid"] = RidFor(artifact),
                ["arch"] = artifact.Arch,
                ["kind"] = artifact.Kind,
                ["fileName"] = artifact.FileName,
                ["installAccessClass"] = "account_required"
            });
        }

        return downloads;
    }

    private static JsonArray BuildCompleteShelfCanonicalArtifacts()
    {
        JsonArray artifacts = [];
        foreach (CompleteShelfArtifact artifact in CompleteShelfArtifacts)
        {
            artifacts.Add(new JsonObject
            {
                ["artifactId"] = artifact.ArtifactId,
                ["head"] = "avalonia",
                ["platform"] = artifact.Platform,
                ["rid"] = RidFor(artifact),
                ["arch"] = artifact.Arch,
                ["kind"] = artifact.Kind,
                ["fileName"] = artifact.FileName,
                ["downloadUrl"] = $"/downloads/files/{artifact.FileName}",
                ["sha256"] = Sha256For(artifact),
                ["sizeBytes"] = artifact.Bytes.LongLength,
                ["platformLabel"] = artifact.PlatformLabel,
                ["installAccessClass"] = "account_required"
            });
        }

        return artifacts;
    }

    private static string RidFor(CompleteShelfArtifact artifact)
        => artifact.PlatformId switch
        {
            "windows-x64" => "win-x64",
            "windows-arm64" => "win-arm64",
            "macos-x64" => "osx-x64",
            "macos-arm64" => "osx-arm64",
            _ => artifact.PlatformId
        };

    private static byte[] BuildCompleteShelfPromotionEvidence()
    {
        JsonArray artifacts = [];
        foreach (CompleteShelfArtifact artifact in CompleteShelfArtifacts)
        {
            artifacts.Add(new JsonObject
            {
                ["artifactId"] = artifact.ArtifactId,
                ["fileName"] = artifact.FileName,
                ["platform"] = artifact.Platform,
                ["promotionStatus"] = "pass",
                ["startupSmokeStatus"] = "pass",
                ["signingStatus"] = artifact.SigningStatus,
                ["notarizationStatus"] = artifact.NotarizationStatus
            });
        }

        JsonObject evidence = new()
        {
            ["contractName"] = "chummer.run.desktop_release_publication",
            ["generatedAt"] = "2026-07-13T11:34:17Z",
            ["artifacts"] = artifacts
        };
        return System.Text.Encoding.UTF8.GetBytes(evidence.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private static byte[] BuildCompleteShelfStartupSmokeReceipt(CompleteShelfArtifact artifact)
    {
        string recordedAtUtc = DateTimeOffset.UtcNow.ToString("O");
        string rid = RidFor(artifact);
        string hostClass = artifact.Platform switch
        {
            "windows" => "windows-x64-native",
            "macos" => "macos-arm64-host",
            _ => "linux-x64-host"
        };
        string operatingSystem = artifact.Platform switch
        {
            "windows" => "Windows 11",
            "macos" => "macOS 15",
            _ => "Linux 6.8"
        };
        JsonObject receipt = new()
        {
            ["status"] = "pass",
            ["releaseVersion"] = "run-20260713-113227",
            ["version"] = "run-20260713-113227",
            ["channel"] = "preview",
            ["channelId"] = "preview",
            ["headId"] = "avalonia",
            ["platform"] = artifact.Platform,
            ["arch"] = artifact.Arch,
            ["rid"] = rid,
            ["readyCheckpoint"] = "pre_ui_event_loop",
            ["hostClass"] = hostClass,
            ["operatingSystem"] = operatingSystem,
            ["artifactDigest"] = $"sha256:{Sha256For(artifact)}",
            ["artifactSha256"] = Sha256For(artifact),
            ["artifactId"] = artifact.ArtifactId,
            ["artifactFileName"] = artifact.FileName,
            ["fileName"] = artifact.FileName,
            ["artifactPath"] = $"files/{artifact.FileName}",
            ["artifactRelativePath"] = $"files/{artifact.FileName}",
            ["startedAtUtc"] = recordedAtUtc,
            ["recordedAtUtc"] = recordedAtUtc,
            ["completedAtUtc"] = recordedAtUtc
        };
        if (artifact.Platform == "windows")
        {
            receipt["executionEnvironment"] = "native_windows";
            receipt["nativeHostEvidence"] = new JsonObject
            {
                ["contractName"] = "chummer6-ui.native_windows_host_evidence",
                ["status"] = "verified",
                ["isNativeWindows"] = true,
                ["hostPlatform"] = "windows",
                ["hostKernel"] = "Windows NT",
                ["runner"] = "dotnet",
                ["evidenceSource"] = "native-test-host"
            };
        }

        return System.Text.Encoding.UTF8.GetBytes(receipt.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private static string Sha256For(CompleteShelfArtifact artifact)
        => Convert.ToHexString(SHA256.HashData(artifact.Bytes)).ToLowerInvariant();

    private static byte[] BuildPromotionEvidence()
        => System.Text.Encoding.UTF8.GetBytes("""
{
  "contractName": "chummer.run.desktop_release_publication",
  "generatedAt": "2026-04-02T06:00:00Z",
  "artifacts": [
    {
      "artifactId": "avalonia-osx-arm64-dmg",
      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
      "platform": "macos",
      "promotionStatus": "pass",
      "startupSmokeStatus": "pass",
      "signingStatus": "skipped_preview",
      "notarizationStatus": "skipped_preview"
    }
  ]
}
""");

    private static byte[] BuildStartupSmokeReceipt()
    {
        const string fileName = "chummer-avalonia-osx-arm64-installer.dmg";
        const string digest = "6f63f1170506eaca21ee53bf90415ee7ed4f40937c505f140137259e27a65bab";
        string recordedAtUtc = DateTimeOffset.UtcNow.ToString("O");
        JsonObject receipt = new()
        {
            ["status"] = "pass",
            ["releaseVersion"] = "run-test",
            ["version"] = "run-test",
            ["channel"] = "preview",
            ["channelId"] = "preview",
            ["headId"] = "avalonia",
            ["platform"] = "macos",
            ["arch"] = "arm64",
            ["rid"] = "osx-arm64",
            ["readyCheckpoint"] = "pre_ui_event_loop",
            ["hostClass"] = "macos-arm64-host",
            ["operatingSystem"] = "macOS 15",
            ["artifactDigest"] = $"sha256:{digest}",
            ["artifactSha256"] = digest,
            ["artifactId"] = "avalonia-osx-arm64-dmg",
            ["artifactFileName"] = fileName,
            ["fileName"] = fileName,
            ["artifactPath"] = $"files/{fileName}",
            ["artifactRelativePath"] = $"files/{fileName}",
            ["startedAtUtc"] = recordedAtUtc,
            ["recordedAtUtc"] = recordedAtUtc,
            ["completedAtUtc"] = recordedAtUtc
        };
        return System.Text.Encoding.UTF8.GetBytes(
            receipt.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private sealed record CompleteShelfArtifact(
        string ArtifactId,
        string Platform,
        string PlatformId,
        string PlatformLabel,
        string Arch,
        string Kind,
        string FileName,
        byte[] Bytes,
        string SigningStatus,
        string NotarizationStatus);

    [Fact]
    public void Fixture_teardown_does_not_traverse_reparse_targets_outside_its_unique_root()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        string externalRoot = Path.Combine(
            Path.GetTempPath(),
            $"internal-release-bundles-controller-teardown-target-{Guid.NewGuid():N}");
        Directory.CreateDirectory(externalRoot);
        string sentinelPath = Path.Combine(externalRoot, "sentinel.txt");
        File.WriteAllText(sentinelPath, "must-remain-outside-fixture-cleanup");
        const UnixFileMode externalDirectoryMode = UnixFileMode.UserRead | UnixFileMode.UserExecute;
        const UnixFileMode externalFileMode = UnixFileMode.UserRead;
        File.SetUnixFileMode(sentinelPath, externalFileMode);
        File.SetUnixFileMode(externalRoot, externalDirectoryMode);
        var fixture = new ControllerFixture();
        try
        {
            Directory.CreateDirectory(fixture.SessionRoot);
            Directory.CreateSymbolicLink(
                Path.Combine(fixture.SessionRoot, "outside-target"),
                externalRoot);

            fixture.Dispose();

            Assert.True(Directory.Exists(externalRoot));
            Assert.True(File.Exists(sentinelPath));
            Assert.Equal(externalDirectoryMode, File.GetUnixFileMode(externalRoot));
            Assert.Equal(externalFileMode, File.GetUnixFileMode(sentinelPath));
        }
        finally
        {
            fixture.Dispose();
            if (Directory.Exists(externalRoot))
            {
                File.SetUnixFileMode(
                    externalRoot,
                    UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
                if (File.Exists(sentinelPath))
                {
                    File.SetUnixFileMode(
                        sentinelPath,
                        UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }

                Directory.Delete(externalRoot, recursive: true);
            }
        }
    }

    private sealed class ControllerFixture : IDisposable
    {
        private readonly string _root;

        private readonly ReleaseUploadQuotaOptions _uploadOptions;
        private readonly PublicReleaseManifestService _manifestService;
        private readonly AccountService _accounts;
        private readonly InstallLinkingService _installLinking;
        private readonly IDataProtectionProvider _dataProtectionProvider;

        public ControllerFixture(
            Action<ReleaseBundlePromotionService.PromotionCheckpoint>? promotionCheckpoint = null,
            Action<string>? postActivationDirectoryFlush = null)
        {
            _root = Path.Combine(Path.GetTempPath(), "internal-release-bundles-controller-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = Path.Combine(_root, "downloads"),
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback",
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = Path.Combine(_root, "canon"),
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking.json"),
                    ["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] = "false",
                    ["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = "true"
                })
                .Build();
            Configuration["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions");
            Directory.CreateDirectory(Configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]!);

            _dataProtectionProvider = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(_root, "keys")));
            ReleaseUploadTickets = new ReleaseUploadTicketService(
                _dataProtectionProvider,
                Configuration);
            _uploadOptions = new ReleaseUploadQuotaOptions
            {
                MaxChunkBytes = ReleaseUploadQuotaOptions.MiB,
                MaxRequestBytes = 2L * ReleaseUploadQuotaOptions.MiB,
                MaxPathBytes = 1024,
                MaxFileBytes = 8L * ReleaseUploadQuotaOptions.MiB,
                MaxChunksPerFile = 16,
                MaxFilesPerSession = 64,
                MaxSessionBytes = 64L * ReleaseUploadQuotaOptions.MiB,
                MaxActiveSessions = 8,
                MaxActiveSessionsPerAuthorization = 2,
                MaxSharedBytes = 128L * ReleaseUploadQuotaOptions.MiB,
                MinimumFreeBytes = 0,
                MinimumFreeFraction = 0,
                JanitorInterval = TimeSpan.FromMinutes(1),
                CompletedReceiptRetention = TimeSpan.FromMinutes(1)
            };
            _manifestService = new PublicReleaseManifestService(Configuration);
            _accounts = new AccountService(new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance));
            _installLinking = new InstallLinkingService(
                new InstallLinkingStore(
                    Configuration,
                    DataProtectionProvider.Create(Path.Combine(_root, "install-linking-keys")),
                    NullLogger<InstallLinkingStore>.Instance),
                Configuration);
            (UploadSessions, Controller) = CreateController(
                promotionCheckpoint,
                postActivationDirectoryFlush);
        }

        public IConfiguration Configuration { get; }

        public ReleaseUploadTicketService ReleaseUploadTickets { get; }

        public InternalReleaseBundlesController Controller { get; private set; }

        public ReleaseBundleUploadSessionService UploadSessions { get; private set; }

        public ReleaseUploadQuotaOptions UploadOptions => _uploadOptions;

        public string SessionRoot => Path.Combine(_root, "sessions");

        public string DownloadsRoot => Configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]!;

        public JsonDocument ReadCanonicalManifest()
            => JsonDocument.Parse(File.ReadAllText(Path.Combine(_root, "downloads", "RELEASE_CHANNEL.generated.json")));

        public void WriteSessionMetadata(ReleaseUploadSession session)
            => WriteSessionMetadata(session.SessionId, session);

        public void WriteSessionMetadata(string storageSessionId, ReleaseUploadSession session)
        {
            string path = Path.Combine(SessionRoot, storageSessionId, "session.json");
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            if (File.Exists(path))
            {
                ReleaseUploadSession? existing = JsonSerializer.Deserialize<ReleaseUploadSession>(File.ReadAllText(path));
                if (existing is not null)
                {
                    session = session with
                    {
                        AuthorizationBinding = existing.AuthorizationBinding,
                        SingleUseAuthorization = existing.SingleUseAuthorization,
                        AuthorizationExpiresAtUtc = existing.AuthorizationExpiresAtUtc
                    };
                }
            }

            File.WriteAllText(path, JsonSerializer.Serialize(session));
        }

        public ReleaseUploadSession ReadSessionMetadata(string sessionId)
            => JsonSerializer.Deserialize<ReleaseUploadSession>(
                   File.ReadAllText(Path.Combine(SessionRoot, sessionId, "session.json")))
               ?? throw new InvalidDataException("release upload session metadata could not be read.");

        public void ExpireSessionAuthorization(string sessionId)
        {
            ReleaseUploadSession session = ReadSessionMetadata(sessionId);
            File.WriteAllText(
                Path.Combine(SessionRoot, sessionId, "session.json"),
                JsonSerializer.Serialize(session with
                {
                    ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-2),
                    AuthorizationExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1)
                }));
        }

        public void RestartController()
        {
            ReleaseUploadAuthorizationContext authorization = Assert.IsType<ReleaseUploadAuthorizationContext>(
                ReleaseUploadRequestGateMiddleware.RequireAuthorization(Controller.Request.HttpContext));
            (UploadSessions, Controller) = CreateController(
                promotionCheckpoint: null,
                postActivationDirectoryFlush: null);
            Controller.ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            };
            Controller.ControllerContext.HttpContext.Request.Scheme = "https";
            Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");
            Controller.ControllerContext.HttpContext.Items[
                ReleaseUploadAuthorizationContext.HttpContextItemKey] = authorization;
        }

        private (ReleaseBundleUploadSessionService Sessions, InternalReleaseBundlesController Controller) CreateController(
            Action<ReleaseBundlePromotionService.PromotionCheckpoint>? promotionCheckpoint,
            Action<string>? postActivationDirectoryFlush)
        {
            var sessions = new ReleaseBundleUploadSessionService(
                Configuration,
                NullLogger<ReleaseBundleUploadSessionService>.Instance,
                _uploadOptions,
                new ReleaseUploadStorageProbe());
            var promotion = new ReleaseBundlePromotionService(
                Configuration,
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint,
                TimeProvider.System,
                PrivacyLaunchGate.Current,
                postActivationDirectoryFlush);
            var controller = new InternalReleaseBundlesController(
                promotion,
                sessions,
                Configuration,
                ReleaseUploadTickets,
                _manifestService,
                _accounts,
                _installLinking,
                uploadOptions: _uploadOptions);
            return (sessions, controller);
        }

        public ReleaseUploadTicketService CreateTicketServiceForCurrentEpoch()
            => new(_dataProtectionProvider, Configuration);

        public void Dispose()
        {
            if (!Directory.Exists(_root))
            {
                return;
            }

            string normalizedRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(_root));
            FileAttributes rootAttributes = File.GetAttributes(normalizedRoot);
            if ((rootAttributes & FileAttributes.ReparsePoint) == 0)
            {
                RestoreOwnerDeleteAccess(normalizedRoot, normalizedRoot, isDirectory: true);
            }

            // Directory.Delete removes a reparse entry without recursing through its target.
            Directory.Delete(normalizedRoot, recursive: true);
        }

        private static void RestoreOwnerDeleteAccess(
            string normalizedRoot,
            string path,
            bool isDirectory)
        {
            string fullPath = Path.GetFullPath(path);
            if (!IsContainedPath(normalizedRoot, fullPath))
            {
                throw new InvalidOperationException("Fixture teardown path escaped its owned test root.");
            }

            FileAttributes attributes = File.GetAttributes(fullPath);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                return;
            }

            if (OperatingSystem.IsWindows())
            {
                if ((attributes & FileAttributes.ReadOnly) != 0)
                {
                    File.SetAttributes(fullPath, attributes & ~FileAttributes.ReadOnly);
                }
            }
            else if (isDirectory)
            {
                const UnixFileMode ownerDirectoryAccess =
                    UnixFileMode.UserRead |
                    UnixFileMode.UserWrite |
                    UnixFileMode.UserExecute;
                File.SetUnixFileMode(
                    fullPath,
                    File.GetUnixFileMode(fullPath) | ownerDirectoryAccess);
            }

            if (!isDirectory)
            {
                return;
            }

            foreach (string entry in Directory.EnumerateFileSystemEntries(fullPath))
            {
                string fullEntry = Path.GetFullPath(entry);
                if (!IsContainedPath(normalizedRoot, fullEntry))
                {
                    throw new InvalidOperationException("Fixture teardown entry escaped its owned test root.");
                }

                FileAttributes entryAttributes = File.GetAttributes(fullEntry);
                if ((entryAttributes & FileAttributes.ReparsePoint) != 0)
                {
                    continue;
                }

                RestoreOwnerDeleteAccess(
                    normalizedRoot,
                    fullEntry,
                    (entryAttributes & FileAttributes.Directory) != 0);
            }
        }

        private static bool IsContainedPath(string normalizedRoot, string candidate)
        {
            StringComparison comparison = OperatingSystem.IsWindows()
                ? StringComparison.OrdinalIgnoreCase
                : StringComparison.Ordinal;
            if (string.Equals(normalizedRoot, candidate, comparison))
            {
                return true;
            }

            string rootPrefix = normalizedRoot + Path.DirectorySeparatorChar;
            return candidate.StartsWith(rootPrefix, comparison);
        }
    }
}
