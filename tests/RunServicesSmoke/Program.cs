using Chummer.Contracts.Hub;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Booster;
using Chummer.Run.AI.Services.Creative;
using Chummer.Run.AI.Services.Gateway;
using Chummer.Run.AI.Services.Lore;
using Chummer.Run.AI.Services.Newspaper;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Interop;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.AI.Services.Transcription;
using Chummer.Run.AI.Controllers;
using Chummer.Run.Registry.Controllers;
using Chummer.Run.Registry.Services;
using Chummer.Campaign.Contracts;
using Chummer.Play.Contracts.Gateway;
using Chummer.Play.Contracts.Interop;
using Chummer.Play.Contracts.Memory;
using Chummer.Play.Contracts.Relay;
using Chummer.Play.Contracts.Spider;
using Chummer.Run.Contracts.AI.Newspaper;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Identity;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Leaderboards;
using Chummer.Run.Contracts.Ops;
using Chummer.Run.Contracts.PublicSurface;
using Chummer.Run.Contracts.Publication;
using Chummer.Run.Contracts.Registry;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Identity.Services;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Logging;
using Microsoft.Net.Http.Headers;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using LoreIngestionRequest = Chummer.Run.Contracts.AI.LoreIngestionRequest;
using LoreLensQuery = Chummer.Run.Contracts.AI.LoreLensQuery;
using LoreSearchRequest = Chummer.Run.Contracts.AI.LoreSearchRequest;
using AssetApprovalState = Chummer.Media.Contracts.AssetApprovalState;
using AssetLifecycleMutationRequest = Chummer.Media.Contracts.AssetLifecycleMutationRequest;
using AssetLifecyclePolicy = Chummer.Media.Contracts.AssetLifecyclePolicy;
using AssetRetentionState = Chummer.Media.Contracts.AssetRetentionState;
using AssetStorageClass = Chummer.Media.Contracts.AssetStorageClass;
using MediaRenderJobState = Chummer.Media.Contracts.MediaRenderJobState;
using MediaRenderJobStatus = Chummer.Media.Contracts.MediaRenderJobStatus;
using NewsBriefDeliveryRequest = Chummer.Run.Contracts.Media.NewsBriefDeliveryRequest;
using NewsItem = Chummer.Run.Contracts.Media.NewsItem;
using NewsBriefRequest = Chummer.Run.Contracts.Media.NewsBriefRequest;
using NpcVideoMessagePublishRequest = Chummer.Run.Contracts.Media.NpcVideoMessagePublishRequest;
using NpcVideoMessageRequest = Chummer.Run.Contracts.Media.NpcVideoMessageRequest;
using PacketArtifactRole = Chummer.Media.Contracts.PacketArtifactRole;
using PacketAttachmentBatchRequest = Chummer.Media.Contracts.PacketAttachmentBatchRequest;
using PacketAttachmentRequest = Chummer.Media.Contracts.PacketAttachmentRequest;
using PacketAttachmentTargetKind = Chummer.Media.Contracts.PacketAttachmentTargetKind;
using PacketFactoryRequest = Chummer.Media.Contracts.PacketFactoryRequest;
using PortraitApprovalRequest = Chummer.Run.Contracts.Media.PortraitApprovalRequest;
using PortraitForgeRequest = Chummer.Run.Contracts.Media.PortraitForgeRequest;
using RouteCinemaRequest = Chummer.Media.Contracts.RouteCinemaRequest;
using RunMemoryIngestionRequest = Chummer.Run.Contracts.Memory.SessionMemoryIngestionRequest;
using ArtifactTrustTiers = Chummer.Run.Contracts.Registry.ArtifactTrustTiers;
using ArtifactVisibilityModes = Chummer.Run.Contracts.Registry.ArtifactVisibilityModes;
using RegistryHubInstallEvent = Chummer.Run.Contracts.Registry.HubInstallEvent;
using RegistryHubReviewRequest = Chummer.Run.Contracts.Registry.HubReviewRequest;
using TranscriptionRequest = Chummer.Run.Contracts.Transcription.TranscriptionRequest;

await VerifyPublicationWorkflowAsync();
VerifyPublicationControllerHardening();
VerifyIdentityWorkflow();
VerifyIdentityEmailDeliveryProviders();
await VerifyHubCommunitySecurityAndDurabilityAsync();
await VerifyTeableUserProjectionWorkflowAsync();
await VerifyPublicLandingProjectionAsync();
VerifyRegistryWorkflow();
VerifyRegistryControllerHardening();
await VerifyAiGatewayWorkflowAsync();
await VerifyGovernedSkillRuntimeWorkflowAsync();
await VerifyNewspaperGatewayRoutingAsync();
await VerifySessionWorkflowAsync();
VerifySpiderWorkflow();
VerifyLoreAndPersonaWorkflow();
await VerifySupportCrashWorkflowAsync();
await VerifyGmOpsBoardWorkflowAsync();
VerifyInteropWorkflow();
await VerifyCreativeWorkflowAsync();

Console.WriteLine("run-services in-process smoke passed");

static bool ContainsLaunchReadinessSignal(string value)
{
    if (string.IsNullOrWhiteSpace(value))
    {
        return false;
    }

    return value.Contains("route-canary validation", StringComparison.OrdinalIgnoreCase)
        || value.Contains("ready to progress this wave", StringComparison.OrdinalIgnoreCase)
        || value.Contains("launch posture follows current governance signals", StringComparison.OrdinalIgnoreCase)
        || value.Contains("hold launch expansion", StringComparison.OrdinalIgnoreCase);
}

async Task VerifyPublicationWorkflowAsync()
{
    var workflow = new PublicationWorkflowService();
    var artifactKinds = new[]
    {
        "RulePack",
        "RuleProfile",
        "BuildKit",
        "NpcVault",
        "RuntimeBundle"
    };

    foreach (var artifactKind in artifactKinds)
    {
        var created = workflow.Submit(new PublicationSubmissionRequest(
            ArtifactId: $"artifact_{artifactKind.ToLowerInvariant()}",
            ArtifactKind: artifactKind,
            Title: $"Publication Smoke {artifactKind}",
            SubmittedBy: "author.demo",
            Notes: "initial submission"));

        Assert(created.State == PublicationState.PendingReview, "publication should begin in pending review");
        Assert(created.Version == 1, "new publications should start at version 1");
        Assert(!string.IsNullOrWhiteSpace(created.ConcurrencyToken), "new publications should expose a concurrency token");
        Assert(created.ApprovalAuditTrail.Count == 1, "new publications should expose a seeded approval audit trail");
        Assert(created.ModerationTimeline.PendingDecision == "review", "pending review publications should project review as the next decision");
        Assert(created.ModerationTimeline.NextSafeActionSummary?.Contains("approval review", StringComparison.OrdinalIgnoreCase) == true, "pending review publications should expose an explicit next safe action summary");

        var staleReview = workflow.Review(created.PublicationId, new PublicationReviewRequest(
            Reviewer: "moderator.demo",
            Approved: true,
            Notes: "stale token"), "\"pub:stale:v99\"");
        Assert(staleReview.Status == PublicationMutationStatus.PreconditionFailed, "stale review tokens should be rejected");

        var reviewed = workflow.Review(created.PublicationId, new PublicationReviewRequest(
            Reviewer: "moderator.demo",
            Approved: true,
            Notes: "clean-room ready"), created.ConcurrencyToken);
        Assert(reviewed.Status == PublicationMutationStatus.Success, "review should succeed with a current concurrency token");
        Assert(reviewed.Publication?.State == PublicationState.Approved, "review should approve publication");
        Assert(reviewed.Publication?.Version == 2, "review should advance the publication version");
        Assert(reviewed.Publication?.ApprovalAuditTrail.Any(entry => entry.Stage == "approval-review" && entry.Outcome == "approved" && entry.ApprovalBacked) == true, "review should append an approval-backed audit receipt");
        Assert(reviewed.Publication?.ModerationTimeline.PendingDecision == "publish", "approved publications should project publish as the next decision");
        Assert(reviewed.Publication?.ModerationTimeline.NextSafeActionSummary?.Contains("Publish the approved artifact", StringComparison.Ordinal) == true, "approved publications should expose an explicit publish-safe next action summary");

        var rejectedCreated = workflow.Submit(new PublicationSubmissionRequest(
            ArtifactId: $"artifact_{artifactKind.ToLowerInvariant()}_reject",
            ArtifactKind: artifactKind,
            Title: $"Publication Reject Smoke {artifactKind}",
            SubmittedBy: "author.demo",
            Notes: "rejection path"));
        var rejected = workflow.Review(rejectedCreated.PublicationId, new PublicationReviewRequest(
            Reviewer: "moderator.demo",
            Approved: false,
            Notes: "not approved until legal signoff"), rejectedCreated.ConcurrencyToken);
        Assert(rejected.Status == PublicationMutationStatus.Success, "rejected review should succeed with a current token");
        Assert(rejected.Publication?.State == PublicationState.Rejected, "review should reject publication");
        Assert(rejected.Publication?.ApprovalAuditTrail.Any(entry => entry.Stage == "approval-review" && entry.Outcome == "rejected") == true, "rejected review notes containing 'approved' should remain rejected in audit trail");

        var publishConflict = workflow.Publish(created.PublicationId, new PublicationPublishRequest(
            PublishedBy: "publisher.demo",
            Notes: "stale token"), created.ConcurrencyToken);
        Assert(publishConflict.Status == PublicationMutationStatus.PreconditionFailed, "stale publish tokens should be rejected");

        var published = workflow.Publish(created.PublicationId, new PublicationPublishRequest(
            PublishedBy: "publisher.demo",
            Notes: "live"), reviewed.Publication!.ConcurrencyToken);
        Assert(published.Status == PublicationMutationStatus.Success, "publish should succeed for approved publications");
        Assert(published.Publication?.State == PublicationState.Published, "publish should transition to published");
        Assert(published.Publication?.ImmutableRetentionRequired == true, "published artifacts should require immutable retention");
        Assert(published.Publication?.PublishedAtUtc is not null, "published artifacts should stamp publication time");
        Assert(published.Publication?.ModerationTimeline.NextSafeActionSummary?.Contains("live published artifact", StringComparison.OrdinalIgnoreCase) == true, "published artifacts should expose an explicit moderation-watch next action summary");

        var delisted = workflow.Moderate(created.PublicationId, new PublicationModerationRequest(
            Moderator: "moderator.demo",
            Action: "delist",
            Reason: "policy hold"), published.Publication!.ConcurrencyToken);
        Assert(delisted.Status == PublicationMutationStatus.Success, "delist should succeed for published artifacts");
        Assert(delisted.Publication?.State == PublicationState.Delisted, "moderation should delist published item");
        Assert(delisted.Publication?.ImmutableRetentionRequired == true, "delisted publications must remain retained");

        var deprecated = workflow.Moderate(created.PublicationId, new PublicationModerationRequest(
            Moderator: "moderator.demo",
            Action: "deprecate",
            Reason: "replace with newer build"), delisted.Publication!.ConcurrencyToken);
        Assert(deprecated.Status == PublicationMutationStatus.Success, "deprecate should succeed for delisted artifacts");
        Assert(deprecated.Publication?.State == PublicationState.Deprecated, "moderation should deprecate delisted item");

        var supersedeConflict = workflow.Moderate(created.PublicationId, new PublicationModerationRequest(
            Moderator: "moderator.demo",
            Action: "supersede",
            Reason: "missing replacement"), deprecated.Publication!.ConcurrencyToken);
        Assert(supersedeConflict.Status == PublicationMutationStatus.Conflict, "supersede should require a replacement artifact id");

        var superseded = workflow.Moderate(created.PublicationId, new PublicationModerationRequest(
            Moderator: "moderator.demo",
            Action: "supersede",
            SupersededByArtifactId: $"{created.ArtifactId}_v2",
            Reason: "new canonical version"), deprecated.Publication!.ConcurrencyToken);
        Assert(superseded.Status == PublicationMutationStatus.Success, "supersede should succeed for deprecated artifacts once replacement metadata exists");
        Assert(superseded.Publication?.State == PublicationState.Superseded, "moderation should supersede deprecated item");
        Assert(superseded.Publication?.SupersededByArtifactId == $"{created.ArtifactId}_v2", "superseded publications should carry replacement artifact id");
        Assert(superseded.Publication!.Events.Count == 6, "publication should keep append-only lifecycle events");
        Assert(superseded.Publication.ApprovalAuditTrail.Count == 6, "publication should keep append-only approval audit receipts");
        Assert(superseded.Publication.ModerationTimeline.PendingDecision == "retention-audit", "superseded publications should project retention audit follow-up");
        Assert(superseded.Publication.ModerationTimeline.NextSafeActionSummary?.Contains("install and audit history", StringComparison.OrdinalIgnoreCase) == true, "superseded publications should expose an explicit retained-history next action summary");

        var postPublishReview = workflow.Review(created.PublicationId, new PublicationReviewRequest(
            Reviewer: "moderator.demo",
            Approved: false,
            Notes: "too late"), superseded.Publication.ConcurrencyToken);
        Assert(postPublishReview.Status == PublicationMutationStatus.Conflict, "immutable lifecycle publications cannot return to review");
    }

    await Task.CompletedTask;
}

async Task VerifySupportCrashWorkflowAsync()
{
    string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-smoke", Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempRoot);

    try
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(tempRoot, "support-store.json"),
                ["CHUMMER_SUPPORT_ATTACHMENT_ROOT"] = Path.Combine(tempRoot, "support-attachments"),
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(tempRoot, "install-linking-store.json"),
                ["FLEET_INTERNAL_API_TOKEN"] = "smoke-token",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "false",
            })
            .Build();

        using ILoggerFactory loggerFactory = LoggerFactory.Create(static builder => { });
        InstallLinkingStore installLinkingStore = new(configuration, loggerFactory.CreateLogger<InstallLinkingStore>());
        InstallLinkingService installLinking = new(installLinkingStore, configuration);
        CommunityStore communityStore = new(configuration, loggerFactory.CreateLogger<CommunityStore>());
        RewardService rewards = new(communityStore);
        SupportStore store = new(configuration, loggerFactory.CreateLogger<SupportStore>());
        SupportAttachmentStorageService supportAttachments = new(configuration);
        SupportProgressEmailWorkflowService progressEmails = new(
            new HttpClient(new StubHttpMessageHandler(_ => JsonResponse(new { status = "disabled" }, HttpStatusCode.OK))),
            configuration,
            loggerFactory.CreateLogger<SupportProgressEmailWorkflowService>());
        SupportCaseService supportCases = new(store, supportAttachments, rewards, progressEmails, loggerFactory.CreateLogger<SupportCaseService>());
        CrashSupportService service = new(store, supportCases, installLinking, loggerFactory.CreateLogger<CrashSupportService>());
        SupportCrashesController controller = new(service, configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<CrashIntakeAcceptedResponse> created = controller.Submit(new CrashEnvelope(
            CrashId: "smoke-crash-1",
            HeadId: "avalonia",
            ApplicationVersion: "0.9.4",
            RuntimeVersion: ".NET 10",
            OperatingSystem: "Linux",
            ProcessArchitecture: "X64",
            CrashFingerprint: "smoke-fingerprint",
            ExceptionType: "System.Exception",
            ExceptionMessage: "smoke",
            ExceptionDetail: "System.Exception: smoke",
            CapturedAtUtc: DateTimeOffset.UtcNow,
            ReleaseChannel: "stable",
            Platform: "linux",
            DesktopHead: "avalonia",
            RuntimeHead: "desktop-runtime",
            LastActionCategory: "startup",
            LogTail: ["smoke"]));

        AcceptedAtActionResult accepted = created.Result as AcceptedAtActionResult
            ?? throw new InvalidOperationException("Support crash controller should accept valid envelopes.");
        CrashIntakeAcceptedResponse payload = accepted.Value as CrashIntakeAcceptedResponse
            ?? throw new InvalidOperationException("Support crash controller should return a typed payload.");
	        Assert(payload.ForwardedForAutomation, "support crash intake should mark envelopes as automation-ready");

	        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer smoke-token";
	        var list = controller.ListWorkItems(candidateOwnerRepo: "chummer6-ui");
	        OkObjectResult listed = list.Result as OkObjectResult
	            ?? throw new InvalidOperationException("Support crash controller should return work item projections.");
        CrashWorkItemListResponse response = listed.Value as CrashWorkItemListResponse
            ?? throw new InvalidOperationException("Support crash controller should return a typed work item response.");
        Assert(response.TotalCount == 1, "support crash work-item list should include the newly accepted crash");
    }
    finally
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    await Task.CompletedTask;
}

void VerifyPublicationControllerHardening()
{
    var workflow = new PublicationWorkflowService();
    var controller = new PublicationsController(workflow)
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };

    var submit = controller.Submit(new PublicationSubmissionRequest(
        ArtifactId: "artifact_controller",
        ArtifactKind: "NpcVault",
        Title: "Controller Smoke",
        SubmittedBy: "author.controller",
        Notes: "controller path"));

    var createdResult = submit.Result as CreatedAtActionResult;
    Assert(createdResult is not null, "submit should return CreatedAtActionResult");
    var created = createdResult!.Value as PublicationRecordResponse;
    Assert(created is not null, "submit should return a publication payload");
    Assert(controller.Response.Headers[HeaderNames.ETag] == created!.ConcurrencyToken, "submit should emit the current ETag");

    controller.ControllerContext = new ControllerContext
    {
        HttpContext = new DefaultHttpContext()
    };

    var staleReview = controller.Review(
        created.PublicationId,
        new PublicationReviewRequest("reviewer.controller", Approved: true, Notes: "stale token"),
        "\"pub:stale:v1\"");

    var staleProblem = staleReview.Result as ObjectResult;
    Assert(staleProblem?.StatusCode == StatusCodes.Status412PreconditionFailed, "stale review requests should map to HTTP 412");

    controller.ControllerContext = new ControllerContext
    {
        HttpContext = new DefaultHttpContext()
    };

    var publishConflict = controller.Publish(
        created.PublicationId,
        new PublicationPublishRequest("publisher.controller", "too early"),
        created.ConcurrencyToken);

    var conflictProblem = publishConflict.Result as ObjectResult;
    Assert(conflictProblem?.StatusCode == StatusCodes.Status409Conflict, "publishing before approval should map to HTTP 409");
}

void VerifyIdentityWorkflow()
{
    var tempRoot = Path.Combine(Path.GetTempPath(), "run-services-smoke", Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempRoot);
    using var loggerFactory = LoggerFactory.Create(static builder => builder.SetMinimumLevel(LogLevel.None));
    var configuration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_IDENTITY_STORE_PATH"] = Path.Combine(tempRoot, "identity-store.json")
        })
        .Build();
    var identity = new IdentityAccessService(configuration, loggerFactory.CreateLogger<IdentityAccessService>());
    var issued = identity.IssueSession(new IdentitySessionIssueRequest(
        SubjectId: "runner.demo",
        DisplayName: "Runner Demo",
        Email: "runner@example.invalid",
        RequestedRoles: new[] { "player", "gm" }));

    Assert(issued.Roles.SequenceEqual(new[] { "gm", "player" }), "issued session should normalize and sort roles");

    var introspection = identity.Introspect(new IdentityIntrospectionRequest(issued.AccessToken));
    Assert(introspection.Active, "introspection should mark new session active");
    Assert(introspection.Roles?.SequenceEqual(new[] { "gm", "player" }) == true, "introspection should return assigned roles");

    var updated = identity.SetRoles("runner.demo", new IdentityRoleSetRequest(new[] { "publisher" }));
    Assert(updated.Roles.SequenceEqual(new[] { "publisher" }), "role updates should replace prior role grants");

    var emailStart = identity.StartEmailEntry(new EmailAuthStartRequest(
        Email: "runner@example.invalid",
        DisplayName: "Runner Demo",
        NextPath: "/home"));
    Assert(emailStart.DeliveryMode == "preview_inline_link", "email-first entry should expose honest preview delivery mode without pretending transactional mail is configured.");

    var emailSession = identity.CompleteEmailEntry(new EmailAuthCompleteRequest(emailStart.TicketId));
    Assert(!string.IsNullOrWhiteSpace(emailSession.AccessToken), "email-first entry should complete into a real session.");

    var revoked = identity.RevokeSession(new IdentitySessionRevokeRequest(emailSession.AccessToken));
    Assert(revoked.Revoked, "identity service should revoke cookie-backed sessions.");
}

void VerifyIdentityEmailDeliveryProviders()
{
    using var loggerFactory = LoggerFactory.Create(static builder => builder.SetMinimumLevel(LogLevel.None));
    HttpRequestMessage? capturedRequest = null;
    string? capturedBody = null;
    var tempRoot = Path.Combine(Path.GetTempPath(), "run-services-smoke", Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempRoot);

    try
    {
        var emailitConfig = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["IDENTITY_PUBLIC_BASE_URL"] = "https://chummer.run",
                ["IDENTITY_EMAILIT_API_KEY"] = "secret-emailit-key",
                ["IDENTITY_EMAILIT_FROM_EMAIL"] = "god@chummer.run",
                ["IDENTITY_EMAILIT_FROM_NAME"] = "God",
                ["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"] = Path.Combine(tempRoot, "identity-email-delivery.json")
            })
            .Build();

        var emailitService = new IdentityEmailDeliveryService(
            emailitConfig,
            loggerFactory.CreateLogger<IdentityEmailDeliveryService>(),
            new HttpClient(new StubHttpMessageHandler(request =>
            {
                capturedRequest = request;
                capturedBody = request.Content?.ReadAsStringAsync().GetAwaiter().GetResult();
                return JsonResponse(new { data = new { id = "email_123" } }, HttpStatusCode.Accepted);
            })));

        var delivered = emailitService.DeliverMagicLink(
            email: "runner@example.invalid",
            displayName: "Runner Demo",
            ticketId: "ticket-emailit-123",
            nextPath: "/home",
            expiresAtUtc: DateTimeOffset.Parse("2026-03-20T10:00:00Z"));

        Assert(delivered.Delivered, $"Emailit-backed delivery should report success on a 2xx API response. mode={delivered.DeliveryMode} note={delivered.PreviewNote} request={(capturedRequest is null ? "none" : capturedRequest.RequestUri?.ToString())}");
        Assert(delivered.DeliveryMode == "emailit_api_magic_link", "Emailit-backed delivery should expose the Emailit delivery mode.");
        Assert(delivered.ProviderMessageId == "email_123", "Emailit-backed delivery should surface the provider message id when the API returns one.");
        Assert(capturedRequest is not null, "Emailit-backed delivery should issue an HTTP request.");
        Assert(capturedRequest!.RequestUri?.ToString() == "https://api.emailit.com/v2/emails", "Emailit-backed delivery should target the v2 emails endpoint.");
        Assert(capturedRequest.Headers.Authorization?.Scheme == "Bearer", "Emailit-backed delivery should send a bearer token.");
        Assert(capturedRequest.Headers.Authorization?.Parameter == "secret-emailit-key", "Emailit-backed delivery should send the configured API key.");
        Assert(capturedRequest.Headers.Contains("Idempotency-Key"), "Emailit-backed delivery should send an idempotency key.");
        Assert(!string.IsNullOrWhiteSpace(capturedBody), "Emailit-backed delivery should send a JSON payload.");

        using (var payload = JsonDocument.Parse(capturedBody!))
        {
            Assert(payload.RootElement.GetProperty("from").GetString() == "God <god@chummer.run>", "Emailit payload should preserve the configured sender label.");
            Assert(payload.RootElement.GetProperty("to").GetString() == "runner@example.invalid", "Emailit payload should target the requested email.");
            Assert(payload.RootElement.GetProperty("subject").GetString() == "Your Chummer sign-in link", "Emailit payload should keep the auth mail subject.");
            Assert(payload.RootElement.GetProperty("tracking").GetBoolean() == false, "Emailit auth mail should disable tracking.");
            Assert(payload.RootElement.GetProperty("text").GetString()?.Contains("/auth/email/callback?ticket=ticket-emailit-123", StringComparison.Ordinal) == true, "Emailit text body should contain the callback link.");
            Assert(payload.RootElement.GetProperty("html").GetString()?.Contains("Open Chummer", StringComparison.Ordinal) == true, "Emailit html body should contain the CTA.");
            Assert(payload.RootElement.GetProperty("meta").GetProperty("purpose").GetString() == "magic_link", "Emailit payload should mark the auth purpose.");
        }

        var deliveryStatus = emailitService.GetStatus();
        Assert(deliveryStatus.RecentDeliveries.Any(static item => item.TransportKey == "emailit_api" && item.ProviderMessageId == "email_123" && item.Status == "accepted"), "Email delivery status should record accepted Emailit sends.");
        Assert(deliveryStatus.Recipients.Any(static item => item.Email == "runner@example.invalid" && item.Provider == "emailit_api"), "Email delivery status should project recipient state.");

        var webhookAck = emailitService.RecordEmailitWebhook(JsonDocument.Parse("""
        {
          "type": "email.delivered",
          "data": {
            "id": "email_123",
            "to": "runner@example.invalid",
            "created_at": "2026-03-20T10:05:00Z"
          }
        }
        """).RootElement);
        Assert(webhookAck.Provider == "emailit_api", "Emailit webhook ack should identify the provider.");
        Assert(webhookAck.Status == "delivered", "Emailit webhook ack should normalize delivered events.");

        var updatedStatus = emailitService.GetStatus();
        Assert(updatedStatus.RecentDeliveries.Any(static item => item.TransportKey == "emailit_api" && item.DeliveryMode == "emailit_webhook" && item.Status == "delivered"), "Webhook delivery events should appear in email delivery history.");
        Assert(updatedStatus.Recipients.Any(static item => item.Email == "runner@example.invalid" && item.State == "delivered"), "Webhook delivery events should update recipient state.");

        var failingEmailitService = new IdentityEmailDeliveryService(
            emailitConfig,
            loggerFactory.CreateLogger<IdentityEmailDeliveryService>(),
            new HttpClient(new StubHttpMessageHandler(_ => new HttpResponseMessage(HttpStatusCode.UnprocessableEntity)
            {
                Content = new StringContent("{\"error\":\"Domain not verified\"}", Encoding.UTF8, "application/json")
            })));

        var failed = failingEmailitService.DeliverMagicLink(
            email: "runner@example.invalid",
            displayName: "Runner Demo",
            ticketId: "ticket-emailit-fail",
            nextPath: "/home",
            expiresAtUtc: DateTimeOffset.Parse("2026-03-20T10:00:00Z"));

        Assert(!failed.Delivered, "Emailit delivery failures should not pretend success.");
        Assert(failed.DeliveryMode == "preview_inline_link", "Emailit delivery failures should fall back to honest preview mode when no SMTP fallback is configured.");
    }
    finally
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }
}

async Task VerifyHubCommunitySecurityAndDurabilityAsync()
{
    var tempRoot = Path.Combine(Path.GetTempPath(), "run-services-smoke", Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempRoot);
    var configuration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
            ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(tempRoot, "support-store.json"),
            ["CHUMMER_SUPPORT_ATTACHMENT_ROOT"] = Path.Combine(tempRoot, "support-attachments"),
            ["FLEET_RECEIPT_SIGNING_SECRET"] = "smoke-secret",
            ["FLEET_INTERNAL_API_TOKEN"] = "smoke-token",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "true",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BASE_URL"] = "http://ea-smoke:8090",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_API_TOKEN"] = "ea-smoke-token",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_PRINCIPAL_ID"] = "support-progress-principal",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BINDING_ID"] = "binding-support-progress",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_API_KEY"] = "emailit-smoke-token",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_BASE_URL"] = "https://api.emailit.com/v2",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_FROM_EMAIL"] = "wageslave@chummer.run",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_FROM_NAME"] = "Wageslave",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_REPLY_TO"] = "support@chummer.run",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_PUBLIC_BASE_URL"] = "https://chummer.run",
        })
        .Build();
    using var loggerFactory = LoggerFactory.Create(static builder => builder.SetMinimumLevel(LogLevel.None));
    var store = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
    var installLinkingStore = new InstallLinkingStore(configuration, loggerFactory.CreateLogger<InstallLinkingStore>());
    var supportStore = new SupportStore(configuration, loggerFactory.CreateLogger<SupportStore>());
    var supportAttachments = new SupportAttachmentStorageService(configuration);
    var installLinking = new InstallLinkingService(installLinkingStore, configuration);
    var rewards = new RewardService(store);
    var executeRequests = new List<(string Path, string Body, string Authorization, string PrincipalId)>();
    var emailitRequests = new List<(string Path, string Body, string Authorization, string IdempotencyKey)>();
    var sentReceiptRequests = new List<(string Path, string Body)>();
    var failedReceiptRequests = new List<(string Path, string Body)>();
    var progressWorkflowHttp = new HttpClient(new StubHttpMessageHandler(request =>
    {
        var path = request.RequestUri?.AbsolutePath ?? string.Empty;
        var body = request.Content?.ReadAsStringAsync().GetAwaiter().GetResult() ?? string.Empty;
        if (string.Equals(path, "/v1/tools/execute", StringComparison.Ordinal))
        {
            executeRequests.Add((
                path,
                body,
                request.Headers.Authorization?.Parameter ?? string.Empty,
                request.Headers.TryGetValues("x-ea-principal-id", out var values) ? values.SingleOrDefault() ?? string.Empty : string.Empty));
            string deliveryId = $"delivery-{executeRequests.Count}";
            return JsonResponse(new
            {
                tool_name = "connector.dispatch",
                target_ref = deliveryId,
                output_json = new { delivery_id = deliveryId, status = "queued" },
                receipt_json = new { handler_key = "connector.dispatch", invocation_contract = "tool.v1" }
            }, HttpStatusCode.OK);
        }

        if (string.Equals(path, "/v2/emails", StringComparison.Ordinal))
        {
            emailitRequests.Add((
                path,
                body,
                request.Headers.Authorization?.Parameter ?? string.Empty,
                request.Headers.TryGetValues("Idempotency-Key", out var values) ? values.SingleOrDefault() ?? string.Empty : string.Empty));
            return JsonResponse(new { id = $"emailit-{emailitRequests.Count}" }, HttpStatusCode.Accepted);
        }

        if (path.Contains("/v1/delivery/outbox/", StringComparison.Ordinal) && path.EndsWith("/sent", StringComparison.Ordinal))
        {
            sentReceiptRequests.Add((path, body));
            return JsonResponse(new { status = "sent" }, HttpStatusCode.OK);
        }

        if (path.Contains("/v1/delivery/outbox/", StringComparison.Ordinal) && path.EndsWith("/failed", StringComparison.Ordinal))
        {
            failedReceiptRequests.Add((path, body));
            return JsonResponse(new { status = "failed" }, HttpStatusCode.OK);
        }

        return new HttpResponseMessage(HttpStatusCode.NotFound)
        {
            Content = new StringContent($"unexpected request: {path}", Encoding.UTF8, "text/plain")
        };
    }));
    var progressEmails = new SupportProgressEmailWorkflowService(
        progressWorkflowHttp,
        configuration,
        loggerFactory.CreateLogger<SupportProgressEmailWorkflowService>());
    var supportCases = new SupportCaseService(
        supportStore,
        supportAttachments,
        rewards,
        progressEmails,
        loggerFactory.CreateLogger<SupportCaseService>());
    var publicationDraftWorkflow = new HubPublicationDraftService();
    var campaignSpine = new CampaignSpineService(store, new WorkspaceLifecyclePolicyService(configuration), new CampaignArtifactRegistryBridge(store), publicationDraftWorkflow);
    var creatorPublicationRegistry = new CreatorPublicationRegistryBridge(publicationDraftWorkflow);
    var accounts = new AccountService(store);
    var groups = new GroupService(store, accounts);
    var leaderboards = new LeaderboardService(store);
    var entitlements = new EntitlementService(store);
    var ledger = new LedgerService(store, rewards, entitlements);
    var identityLinks = new IdentityLinkService(store, accounts);
    var ledgerVerifier = new FleetReceiptVerifier(configuration);
    var projectionVerifier = new BoosterReceiptVerifier(configuration);
    var projectionAccess = new BoosterProjectionAccessGuard(configuration);
    var projections = new BoosterReceiptProjectionService();
    var chrome = CreateChromeService(configuration, loggerFactory);
    var browserAuth = new HubBrowserAuthService(new HttpClient(new StubHttpMessageHandler(_ =>
        JsonResponse(new IdentitySessionIssueResponse(
            SessionId: "sid-smoke",
            SubjectId: "subject.demo",
            DisplayName: "Runner Demo",
            Email: "runner@example.invalid",
            Roles: new[] { "player" },
            AccessToken: "subject-token",
            RefreshToken: "refresh-token",
            IssuedAtUtc: DateTimeOffset.UtcNow,
            ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(1))))), configuration);
    var google = CreateGoogleService(configuration, browserAuth, identityLinks, accounts, loggerFactory, tempRoot);
    var releases = new PublicReleaseManifestService(configuration);
    var releaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
    var weeklyPulseArtifact = new WeeklyProductPulseArtifactService(configuration, loggerFactory.CreateLogger<WeeklyProductPulseArtifactService>());
    var trustPulse = new PublicTrustPulseService(weeklyPulseArtifact, configuration, loggerFactory.CreateLogger<PublicTrustPulseService>());
    var privacyBoundaries = new PublicPrivacyBoundaryService(new PublicCanonFileLoader(configuration), new PublicRouteCatalogService(new PublicCanonFileLoader(configuration)));
    var identityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(request =>
    {
        var body = request.Content is null ? string.Empty : request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        return body.Contains("subject-token", StringComparison.Ordinal)
            ? JsonResponse(new IdentityIntrospectionResponse(true, "session-subject", "subject.demo", new[] { "player" }, DateTimeOffset.UtcNow.AddHours(1)))
            : JsonResponse(new IdentityIntrospectionResponse(false, null, null, Array.Empty<string>(), null), HttpStatusCode.Unauthorized);
    })), configuration);

    var createdUser = accounts.UpsertProfile(new UpsertHubUserProfileRequest(
        SubjectId: "subject.demo",
        DisplayName: "Runner Demo",
        Handle: "runner-demo",
        Visibility: "private",
        Timezone: "UTC",
        CountryCode: "AT"));
    var experience = new UserExperienceService(store, accounts);
    var supportPresentation = new SupportCasePresentationService();
    var signedInTrustStatus = new SignedInTrustStatusService(installLinking, supportCases, supportPresentation, trustPulse);
    var workspaceServerPlane = new CampaignWorkspaceServerPlaneService(campaignSpine, supportCases, supportPresentation);
    var entitlementsController = new EntitlementsController(accounts, identityClient, entitlements, installLinking, rewards, workspaceServerPlane)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var accountController = new AccountsController(accounts, identityClient, identityLinks, experience, installLinking, supportCases, supportPresentation, campaignSpine, workspaceServerPlane, creatorPublicationRegistry, chrome, google, releases, releaseSelection, privacyBoundaries, signedInTrustStatus, loggerFactory.CreateLogger<AccountsController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var forbiddenAccount = await accountController.GetMe("other.subject", CancellationToken.None);
    var forbiddenAccountProblem = forbiddenAccount.Result as ObjectResult;
    Assert(forbiddenAccountProblem?.StatusCode == StatusCodes.Status403Forbidden, "authenticated account endpoints should reject subject mismatch.");

    var currentAccount = await accountController.GetMe("subject.demo", CancellationToken.None);
    var currentAccountResult = currentAccount.Result as OkObjectResult;
    Assert(currentAccountResult?.Value is HubUserDto { UserId: not null }, "authenticated account endpoints should allow matching subjects.");
    var currentUser = (HubUserDto)currentAccountResult!.Value!;
    var seededEntitlements = entitlements.ApplyReceipt(
        new ContributionReceiptDto(
            ReceiptId: "rcpt-entitlement-seed-001",
            EventKind: "slice_landed",
            LaneId: "entitlement-seed-01",
            ProjectId: "fleet",
            UserId: currentUser.UserId,
            GroupId: "grp-demo",
            SponsorSessionId: "sps-demo",
            AuthClass: "chatgpt_auth_json",
            LaneType: "participant_burst",
            LaneRole: "coding",
            Verified: true,
            SignedByFleet: "hmac-sha256:entitlement-seed",
            AuthorizationTierAtReceipt: "pro",
            TierSource: "fleet_detected"),
        mintedPoints: 0);
    Assert(seededEntitlements.Contains("supporter-flair", StringComparer.OrdinalIgnoreCase), "signed-in smoke setup should seed a supporter entitlement before the entitlements api is queried.");
    var entitlementSmokeManifest = new PublicReleaseManifestDto(
        Version: "0.6.0-entitlement-smoke",
        Channel: "preview",
        PublishedAt: DateTimeOffset.UtcNow,
        Downloads:
        [
            new PublicReleaseArtifactDto(
                Id: "entitlement-smoke-linux-x64",
                Platform: "Linux x64",
                Url: "https://downloads.example.invalid/entitlement-smoke-linux-x64.exe",
                Sha256: new string('a', 64),
                SizeBytes: 1024,
                Head: "avalonia",
                PlatformId: "linux",
                Arch: "x64",
                Kind: "installer",
                FileName: "entitlement-smoke-linux-x64.exe",
                InstallAccessClass: InstallAccessClasses.AccountRecommended)
        ]);
    var entitlementSmokeArtifact = entitlementSmokeManifest.Downloads[0];
    var entitlementSmokeInstallationId = $"install-entitlement-smoke-{Guid.NewGuid():N}";
    var entitlementSmokeDownload = installLinking.IssueDownload(
        entitlementSmokeManifest,
        entitlementSmokeArtifact,
        currentUser.UserId,
        currentUser.SubjectId);
    Assert(entitlementSmokeDownload.ClaimTicket is not null, "signed-in smoke setup should mint a claim ticket for entitlement-sync restore proof.");
    var entitlementSmokeRedeem = installLinking.RedeemClaim(
        new RedeemInstallClaimRequestDto(
            ClaimCode: entitlementSmokeDownload.ClaimTicket!.ClaimCode,
            InstallationId: entitlementSmokeInstallationId,
            HeadId: "avalonia",
            ApplicationVersion: "0.6.0-entitlement-smoke",
            ChannelId: "preview",
            Platform: "linux",
            Arch: "x64",
            PublicKey: "entitlement-smoke-public-key",
            HostLabel: "entitlement-smoke-host"));
    var duplicateGrantIssuedAt = DateTimeOffset.UtcNow.AddMinutes(-1);
    lock (installLinkingStore.Gate)
    {
        installLinkingStore.GrantsById["igr-entitlement-smoke-duplicate-001"] = new InstallationGrantDto(
            GrantId: "igr-entitlement-smoke-duplicate-001",
            InstallationId: entitlementSmokeRedeem.Installation.InstallationId,
            Status: InstallationGrantStates.Active,
            AccessToken: "entitlement-smoke-duplicate-token",
            IssuedAtUtc: duplicateGrantIssuedAt,
            ExpiresAtUtc: duplicateGrantIssuedAt.AddDays(14),
            UserId: currentUser.UserId,
            SubjectId: currentUser.SubjectId);
        installLinkingStore.PersistLocked();
    }
    var entitlementResult = await entitlementsController.GetMine("subject.demo", CancellationToken.None);
    var entitlementPayload = (entitlementResult.Result as OkObjectResult)?.Value as EntitlementAccountProjection ?? entitlementResult.Value;
    Assert(entitlementPayload is not null && entitlementPayload.Entitlements.Count >= 1, "entitlements api should keep the signed-in entitlement list available.");
    Assert(entitlementPayload!.Entitlements.Any(item => string.Equals(item.Key, "supporter-flair", StringComparison.OrdinalIgnoreCase)), "entitlements api should preserve the seeded supporter entitlement on the signed-in account surface.");
    Assert(entitlementPayload.SyncReceipts.ProvenanceReceipts.Count >= 1, "entitlements api should expose entitlement-sync provenance receipts alongside grants.");
    Assert(entitlementPayload.SyncReceipts.ProvenanceReceipts.All(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)), "entitlements api should isolate entitlement-sync provenance receipts instead of mixing workspace-only restore items.");
    Assert(entitlementPayload.SyncReceipts.ProvenanceRecoveryReceipts.Any(item => string.Equals(item.RecoveryRoute, "/account/access", StringComparison.Ordinal)), "entitlements api should expose recoverable account-access provenance routes for entitlement replay.");
    Assert(entitlementPayload.SyncReceipts.ConflictReceipts.Count >= 1, "entitlements api should expose explicit entitlement-sync conflict receipts when restore continuity drifts.");
    Assert(entitlementPayload.SyncReceipts.ConflictReceipts.All(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)), "entitlements api should isolate entitlement-sync conflict receipts on the standalone entitlements surface.");
    Assert(entitlementPayload.SyncReceipts.ConflictReceipts.Any(item => item.BlocksContinue && !string.IsNullOrWhiteSpace(item.RecoveryHint)), "entitlements api should keep blocking entitlement-sync conflicts recoverable on the standalone entitlements surface.");
    Assert(entitlementPayload.SyncReceipts.ReceiptStatus.EntitlementSyncConflictCount == entitlementPayload.SyncReceipts.ConflictReceipts.Count, "entitlements api should summarize the standalone entitlement conflict count without dropping receipts.");
    Assert(entitlementPayload.SyncReceipts.ReceiptStatus.WorkspaceRestoreConflictCount == 0, "entitlements api should keep workspace-only restore conflicts out of the standalone entitlement summary.");

    var emailLink = identityLinks.LinkEmail(new LinkEmailIdentityRequest(
        SubjectId: "subject.demo",
        Email: "runner@example.invalid",
        MakePrimary: true));
    Assert(string.Equals(emailLink.Status, "pending_verification", StringComparison.OrdinalIgnoreCase), "email links should begin pending verification.");

    var confirmedEmail = identityLinks.ConfirmIdentityLink(new ConfirmIdentityLinkRequest(
        SubjectId: "subject.demo",
        IdentityLinkId: emailLink.IdentityLinkId));
    Assert(string.Equals(confirmedEmail.Status, "verified", StringComparison.OrdinalIgnoreCase), "email links should become verified after confirmation.");

    var googleLink = identityLinks.LinkExternalIdentity(new LinkExternalIdentityRequest(
        SubjectId: "subject.demo",
        Provider: "google",
        ProviderSubject: "google-oauth-subject",
        DisplayLabel: "Runner Google",
        MakePrimary: true));
    Assert(string.Equals(googleLink.Status, "provider_backed", StringComparison.OrdinalIgnoreCase), "Google links should be treated as provider-backed auth.");

    var officialTelegram = identityLinks.LinkChannel(new LinkChannelRequest(
        SubjectId: "subject.demo",
        ChannelKind: "telegram_official_bot",
        ChannelHandle: "@hubbrain",
        NotificationsEnabled: true));
    Assert(string.Equals(officialTelegram.Status, "pending_verification", StringComparison.OrdinalIgnoreCase), "official Telegram companion channel should stay pending until the bot handshake verifies it.");

    var updatedTelegram = identityLinks.LinkChannel(new LinkChannelRequest(
        SubjectId: "subject.demo",
        ChannelKind: "telegram_official_bot",
        ChannelHandle: "@hubbrain-updated",
        NotificationsEnabled: false));
    Assert(string.Equals(updatedTelegram.ChannelLinkId, officialTelegram.ChannelLinkId, StringComparison.OrdinalIgnoreCase), "official Telegram companion linking should update the existing channel record instead of minting duplicates.");
    Assert(string.Equals(updatedTelegram.DisplayLabel, "@hubbrain-updated", StringComparison.OrdinalIgnoreCase), "official Telegram companion relinks should update the visible handle.");

    var byoTelegram = identityLinks.LinkChannel(new LinkChannelRequest(
        SubjectId: "subject.demo",
        ChannelKind: "telegram_user_bot",
        ChannelHandle: "@runner_sidecar",
        NotificationsEnabled: false));
    Assert(string.Equals(byoTelegram.Status, "future_capability", StringComparison.OrdinalIgnoreCase), "bring-your-own Telegram bot links should stay explicitly future-bound.");

    var linkSummary = identityLinks.GetSummary("subject.demo");
    Assert(string.Equals(linkSummary.RecommendedPrimaryAuth, "google", StringComparison.OrdinalIgnoreCase), "linked identity summary should prefer Google once provider-backed auth exists.");
    Assert(string.Equals(linkSummary.OrchestratorBrain, "EA", StringComparison.OrdinalIgnoreCase), "identity/channel summary should keep EA as the orchestrator brain.");
    Assert(linkSummary.ChannelLinks.Any(static link => string.Equals(link.ChannelKind, "telegram_official_bot", StringComparison.OrdinalIgnoreCase)), "identity/channel summary should expose the official Telegram companion link.");
    Assert(linkSummary.LinkedIdentities.Any(static link => string.Equals(link.Provider, "google", StringComparison.OrdinalIgnoreCase) && string.Equals(link.ProviderSubject, "hidden", StringComparison.OrdinalIgnoreCase)), "linked identity summary should redact raw provider subject values.");
    Assert(linkSummary.LinkedIdentities.All(static link => string.IsNullOrWhiteSpace(link.Note)), "linked identity summary should not leak provider-policy notes.");
    Assert(linkSummary.ChannelLinks.All(static link => string.IsNullOrWhiteSpace(link.Note)), "channel summary should not leak policy notes.");

    var accountLinksController = new AccountLinksController(identityLinks, identityClient, accounts, browserAuth, new HubEmailLinkVerificationService(DataProtectionProvider.Create("smoke")))
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var retiredProviderLink = accountLinksController.LinkProvider();
    Assert((retiredProviderLink as ObjectResult)?.StatusCode == StatusCodes.Status410Gone, "self-asserted provider linking should stay retired.");

    var unavailableBrowserAuth = new HubBrowserAuthService(new HttpClient(new StubHttpMessageHandler(_ =>
        new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
        {
            Content = new StringContent("{\"detail\":\"identity-mailer-secret\"}", Encoding.UTF8, "application/json")
        })), configuration);
    var unavailableRecoveryLinksController = new AccountLinksController(
        identityLinks,
        identityClient,
        accounts,
        unavailableBrowserAuth,
        new HubEmailLinkVerificationService(DataProtectionProvider.Create("smoke-recovery-failure")))
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var unavailableRecoveryStart = await unavailableRecoveryLinksController.StartRecoveryEmailLink(
        new StartRecoveryEmailLinkRequest(
            SubjectId: "subject.demo",
            Email: "recovery@example.invalid",
            NextPath: "/account"),
        CancellationToken.None);
    var unavailableRecoveryStartProblem = unavailableRecoveryStart.Result as ObjectResult;
    Assert(unavailableRecoveryStartProblem?.StatusCode == StatusCodes.Status503ServiceUnavailable, "recovery email start should report browser-auth outages as 503 instead of conflict.");
    Assert(identityLinks.FindLinkedIdentity("email", "recovery@example.invalid") is null, "failed recovery email starts should not leave behind a pending local email link.");

    var unavailableIdentityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(_ =>
        new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
        {
            Content = new StringContent("{\"detail\":\"identity-down-secret\"}", Encoding.UTF8, "application/json")
        })), configuration);
    var unavailableParticipationSessions = new BoostSessionService(
        store,
        accounts,
        groups,
        new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(_ => JsonResponse(new { detail = "unused" }, HttpStatusCode.OK))), configuration),
        rewards);
    var unavailableParticipationController = new CodexParticipationController(
        accounts,
        unavailableIdentityClient,
        leaderboards,
        unavailableParticipationSessions,
        identityLinks,
        experience,
        chrome,
        configuration,
        loggerFactory.CreateLogger<CodexParticipationController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var unavailableParticipationResult = await unavailableParticipationController.ParticipationPage(CancellationToken.None);
    var unavailableParticipationModel = (unavailableParticipationResult as ViewResult)?.Model as AuthMessagePageViewModel;
    Assert(string.Equals(unavailableParticipationModel?.Heading, "Participation is unavailable right now", StringComparison.Ordinal), "participation page should show an unavailable message when identity is down instead of redirecting to login.");

    var missingFleetTokenConfig = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json")
        })
        .Build();
    var bootstrapGroup = groups.CreateGroup(new CreateGroupRequest(
        SubjectId: "subject.demo",
        Name: "Bootstrap Group",
        GroupType: "booster",
        Visibility: "group",
        Capabilities: null));
    var unavailableBridgeSessions = new BoostSessionService(
        store,
        accounts,
        groups,
        new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(_ => JsonResponse(new { detail = "unused" }, HttpStatusCode.OK))), missingFleetTokenConfig),
        rewards);
    var unavailableBridgeSession = unavailableBridgeSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "hub",
        GroupId: bootstrapGroup.GroupId,
        SubjectLabel: "Runner Demo"));
    unavailableBridgeSessions.RecordConsent(unavailableBridgeSession.SponsorSessionId);
    var unavailableBoostSessionsController = new BoostSessionsController(accounts, identityClient, leaderboards, unavailableBridgeSessions)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var unavailableBoostStart = await unavailableBoostSessionsController.StartDeviceAuth(unavailableBridgeSession.SponsorSessionId, CancellationToken.None);
    var unavailableBoostStartProblem = unavailableBoostStart.Result as ObjectResult;
    Assert(unavailableBoostStartProblem?.StatusCode == StatusCodes.Status503ServiceUnavailable, "legacy boost-session device-auth start should report bridge outages as 503 instead of bad request.");

    var activationReceipt = new ContributionReceiptDto(
        ReceiptId: "rcpt-lane-activated-001",
        EventKind: "lane_activated",
        LaneId: "participant-activation-01",
        ProjectId: "fleet",
        UserId: createdUser.UserId,
        GroupId: "grp-demo",
        SponsorSessionId: "sps-demo",
        AuthClass: "chatgpt_auth_json",
        LaneType: "participant_burst",
        LaneRole: "coding",
        Verified: true,
        SignedByFleet: "hmac-sha256:activation",
        AuthorizationTierAtReceipt: "plus",
        TierSource: "fleet_detected");
    var activationPoints = rewards.ApplyReceipt(activationReceipt);
    Assert(activationPoints == 0, "lane activation should not mint contribution points on its own.");
    Assert(
        !rewards.ListBadgesForUser(createdUser.UserId).Any(static badge => string.Equals(badge.Key, "booster-starter", StringComparison.OrdinalIgnoreCase) && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)),
        "lane activation should not mint the old Booster Starter badge.");

    var reviewReceipt = new ContributionReceiptDto(
        ReceiptId: "rcpt-slice-reviewed-001",
        EventKind: "slice_reviewed",
        LaneId: "participant-review-01",
        ProjectId: "fleet",
        UserId: createdUser.UserId,
        GroupId: "grp-demo",
        SponsorSessionId: "sps-demo",
        AuthClass: "chatgpt_auth_json",
        LaneType: "participant_burst",
        LaneRole: "review",
        Verified: true,
        SignedByFleet: "hmac-sha256:review",
        AuthorizationTierAtReceipt: "plus",
        TierSource: "fleet_detected");
    var reviewPoints = rewards.ApplyReceipt(reviewReceipt);
    Assert(reviewPoints == 5, "verified review receipts should still mint contribution points.");
    lock (store.Gate)
    {
        store.Receipts.Add(reviewReceipt);
    }
    Assert(
        leaderboards.Quests().Any(static quest =>
            string.Equals(quest.QuestId, "quest-review-slices", StringComparison.OrdinalIgnoreCase)
            && quest.CurrentProgress == 1),
        "review quests should progress from validated review work rather than lane activation.");

    var signedLaneReceipt = BuildSignedReceiptElement("smoke-secret", new Dictionary<string, object?>
    {
        ["receipt_id"] = "rcpt-signed-001",
        ["event_kind"] = "slice_landed",
        ["lane_id"] = "participant-01",
        ["project_id"] = "fleet",
        ["user_id"] = createdUser.UserId,
        ["group_id"] = "grp-demo",
        ["sponsor_session_id"] = "sps-demo",
        ["auth_class"] = "chatgpt_auth_json",
        ["lane_type"] = "participant_burst",
        ["workflow_kind"] = "premium_burst",
        ["review_rounds_used"] = 1,
        ["accepted_on_round"] = "1",
        ["landed_sha"] = "abc123",
        ["landed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
        ["verified"] = true,
        ["cheap_loop_only"] = false,
        ["paid_lane_used"] = true,
        ["groundwork_ms"] = 0,
        ["review_ms"] = 1000,
        ["jury_ms"] = 500,
        ["core_ms"] = 2000,
        ["files_touched"] = 2,
        ["diff_size"] = 64,
        ["issue_fingerprints"] = new[] { "lint" },
        ["credit_burn_estimate"] = 0,
        ["authorization_tier_at_receipt"] = "pro",
        ["tier_source"] = "fleet_detected",
    });
    var forgedReceipt = BuildSignedReceiptElement("wrong-secret", new Dictionary<string, object?>
    {
        ["receipt_id"] = "rcpt-forged-001",
        ["event_kind"] = "slice_landed",
        ["lane_id"] = "participant-02",
        ["project_id"] = "fleet",
        ["user_id"] = createdUser.UserId,
        ["group_id"] = "grp-demo",
        ["sponsor_session_id"] = "sps-demo",
        ["auth_class"] = "chatgpt_auth_json",
        ["lane_type"] = "participant_burst",
        ["verified"] = true,
    });

    var ledgerController = new LedgerController(accounts, identityClient, ledger, ledgerVerifier, rewards)
    {
        ControllerContext = ReceiptControllerContext(signatureHeader: "hmac-sha256:forged", forgedReceipt)
    };
    var forgedLedgerResult = ledgerController.Ingest(forgedReceipt);
    var forgedLedgerProblem = forgedLedgerResult.Result as ObjectResult;
    Assert(forgedLedgerProblem?.StatusCode == StatusCodes.Status401Unauthorized, "ledger receipt ingest should reject forged signatures.");

    var signedSignature = signedLaneReceipt.GetProperty("signed_by_fleet").GetString() ?? string.Empty;
    ledgerController.ControllerContext = ReceiptControllerContext(signedSignature, signedLaneReceipt);
    var acceptedLedger = ledgerController.Ingest(signedLaneReceipt);
    var acceptedLedgerResult = acceptedLedger.Result as OkObjectResult;
    var acceptedLedgerPayload = acceptedLedgerResult?.Value as ReceiptIngestResultDto;
    Assert(acceptedLedgerPayload?.Status == "ingested", "ledger receipt ingest should accept Fleet-signed payloads.");

    var aiReceiptController = new BoosterReceiptsController(projectionAccess, projections, projectionVerifier)
    {
        ControllerContext = ReceiptControllerContext("hmac-sha256:forged", forgedReceipt)
    };
    var forgedProjectionResult = aiReceiptController.IngestReceipt(forgedReceipt);
    var forgedProjectionProblem = forgedProjectionResult.Result as ObjectResult;
    Assert(forgedProjectionProblem?.StatusCode == StatusCodes.Status401Unauthorized, "AI receipt projections should reject forged signatures.");

    aiReceiptController.ControllerContext = ReceiptControllerContext(signedSignature, signedLaneReceipt);
    var acceptedProjection = aiReceiptController.IngestReceipt(signedLaneReceipt);
    var acceptedProjectionResult = acceptedProjection.Result as OkObjectResult;
    var acceptedProjectionPayload = acceptedProjectionResult?.Value as ReceiptIngestResultDto;
    Assert(acceptedProjectionPayload?.Status == "projected", "AI receipt projections should accept Fleet-signed payloads.");

    var ownerGroup = groups.CreateGroup(new CreateGroupRequest(
        SubjectId: "subject.demo",
        Name: "Tuesday Boosters",
        GroupType: "booster",
        Visibility: "group",
        Capabilities: null));
    var ownerJoinCode = groups.CreateJoinCode(ownerGroup.GroupId, new CreateJoinCodeRequest(
        SubjectId: "subject.demo",
        Role: "member"));
    accounts.UpsertProfile(new UpsertHubUserProfileRequest(
        SubjectId: "subject.member",
        DisplayName: "Member Demo",
        Handle: "member-demo",
        Visibility: "private",
        Timezone: "UTC",
        CountryCode: "AT"));
    groups.JoinGroup(new JoinGroupByCodeRequest("subject.member", ownerJoinCode.Code));
    var memberJoinCodeBlocked = false;
    try
    {
        _ = groups.CreateJoinCode(ownerGroup.GroupId, new CreateJoinCodeRequest(
            SubjectId: "subject.member",
            Role: "member"));
    }
    catch (CommunityAccessDeniedException ex)
    {
        memberJoinCodeBlocked = ex.Message.Contains("owner, manager, admin, or gm", StringComparison.OrdinalIgnoreCase);
    }

    Assert(memberJoinCodeBlocked, "non-manager members should not be allowed to mint join codes.");

    var memberBoostCodeBlocked = false;
    try
    {
        _ = groups.CreateBoostCode(new CreateBoostCodeRequest(
            SubjectId: "subject.member",
            GroupId: ownerGroup.GroupId,
            CampaignId: null,
            ProjectId: "hub",
            Label: "beta"));
    }
    catch (CommunityAccessDeniedException ex)
    {
        memberBoostCodeBlocked = ex.Message.Contains("owner, manager, admin, or gm", StringComparison.OrdinalIgnoreCase);
    }

    Assert(memberBoostCodeBlocked, "non-manager members should not be allowed to mint boost codes.");

    var ownerRoleJoinCodeBlocked = false;
    try
    {
        _ = groups.CreateJoinCode(ownerGroup.GroupId, new CreateJoinCodeRequest(
            SubjectId: "subject.demo",
            Role: "owner"));
    }
    catch (InvalidOperationException ex)
    {
        ownerRoleJoinCodeBlocked = ex.Message.Contains("member or booster", StringComparison.OrdinalIgnoreCase);
    }

    Assert(ownerRoleJoinCodeBlocked, "join codes should not be allowed to mint owner-level roles.");

    var boostCode = groups.CreateBoostCode(new CreateBoostCodeRequest(
        SubjectId: "subject.demo",
        GroupId: ownerGroup.GroupId,
        CampaignId: null,
        ProjectId: "hub",
        Label: "alpha"));
    groups.RedeemBoostCode(new RedeemBoostCodeRequest("subject.demo", boostCode.Code));
    var reloadedStore = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
    var reloadedAccounts = new AccountService(reloadedStore);
    var reloadedGroups = new GroupService(reloadedStore, reloadedAccounts);
    var reloadedBoostCode = reloadedGroups.GetBoostCode(boostCode.Code);
    Assert(string.Equals(reloadedBoostCode?.Status, "redeemed", StringComparison.OrdinalIgnoreCase), "redeemed boost codes should stay redeemed after store reload even when the redeemer was already a member.");

    var memberIdentityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(request =>
    {
        var body = request.Content is null ? string.Empty : request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        return body.Contains("member-token", StringComparison.Ordinal)
            ? JsonResponse(new IdentityIntrospectionResponse(true, "session-member", "subject.member", new[] { "player" }, DateTimeOffset.UtcNow.AddHours(1)))
            : JsonResponse(new IdentityIntrospectionResponse(false, null, null, Array.Empty<string>(), null), HttpStatusCode.Unauthorized);
    })), configuration);
    var outsiderIdentityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(request =>
    {
        var body = request.Content is null ? string.Empty : request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        return body.Contains("outsider-token", StringComparison.Ordinal)
            ? JsonResponse(new IdentityIntrospectionResponse(true, "session-outsider", "subject.outsider", new[] { "player" }, DateTimeOffset.UtcNow.AddHours(1)))
            : JsonResponse(new IdentityIntrospectionResponse(false, null, null, Array.Empty<string>(), null), HttpStatusCode.Unauthorized);
    })), configuration);
    accounts.UpsertProfile(new UpsertHubUserProfileRequest(
        SubjectId: "subject.outsider",
        DisplayName: "Outsider Demo",
        Handle: "outsider-demo",
        Visibility: "private",
        Timezone: "UTC",
        CountryCode: "AT"));
    var memberGroupsController = new GroupsController(groups, memberIdentityClient)
    {
        ControllerContext = AuthenticatedControllerContext("member-token")
    };
    var memberJoinCodeResult = await memberGroupsController.CreateJoinCode(ownerGroup.GroupId, new CreateJoinCodeRequest(
        SubjectId: "subject.member",
        Role: "member"), CancellationToken.None);
    Assert((memberJoinCodeResult.Result as ObjectResult)?.StatusCode == StatusCodes.Status403Forbidden, "join-code creation should return 403 for non-manager members.");

    var memberBoostCodesController = new BoostCodesController(groups, memberIdentityClient)
    {
        ControllerContext = AuthenticatedControllerContext("member-token")
    };
    var memberBoostCodeResult = await memberBoostCodesController.Create(new CreateBoostCodeRequest(
        SubjectId: "subject.member",
        GroupId: ownerGroup.GroupId,
        CampaignId: null,
        ProjectId: "hub",
        Label: "beta"), CancellationToken.None);
    Assert((memberBoostCodeResult.Result as ObjectResult)?.StatusCode == StatusCodes.Status403Forbidden, "boost-code creation should return 403 for non-manager members.");

    var missingGroupJoinCodeResult = await memberGroupsController.CreateJoinCode("grp-missing", new CreateJoinCodeRequest(
        SubjectId: "subject.member",
        Role: "member"), CancellationToken.None);
    Assert((missingGroupJoinCodeResult.Result as StatusCodeResult)?.StatusCode == StatusCodes.Status404NotFound, "join-code creation should return 404 when the target group does not exist.");

    var missingGroupBoostCodeResult = await memberBoostCodesController.Create(new CreateBoostCodeRequest(
        SubjectId: "subject.member",
        GroupId: "grp-missing",
        CampaignId: null,
        ProjectId: "hub",
        Label: "missing"), CancellationToken.None);
    Assert((missingGroupBoostCodeResult.Result as StatusCodeResult)?.StatusCode == StatusCodes.Status404NotFound, "boost-code creation should return 404 when the target group does not exist.");

    var missingJoinResult = await memberGroupsController.Join(new JoinGroupByCodeRequest("subject.member", "JOIN-MISSING"), CancellationToken.None);
    Assert((missingJoinResult.Result as ObjectResult)?.StatusCode == StatusCodes.Status404NotFound, "joining with an unknown join code should return 404.");
    Assert((((missingJoinResult.Result as ObjectResult)?.Value as ProblemDetails)?.Detail ?? string.Empty).Contains("fresh join code", StringComparison.OrdinalIgnoreCase), "missing join-code errors should explain the real recovery path.");

    var missingBoostRedeemResult = await memberBoostCodesController.Redeem(new RedeemBoostCodeRequest("subject.member", "BOOST-MISSING"), CancellationToken.None);
    Assert((missingBoostRedeemResult.Result as ObjectResult)?.StatusCode == StatusCodes.Status404NotFound, "redeeming an unknown boost code should return 404.");
    Assert((((missingBoostRedeemResult.Result as ObjectResult)?.Value as ProblemDetails)?.Detail ?? string.Empty).Contains("fresh sponsorship code", StringComparison.OrdinalIgnoreCase), "missing boost-code errors should explain the real recovery path.");

    var groupsController = new GroupsController(groups, outsiderIdentityClient)
    {
        ControllerContext = AuthenticatedControllerContext("outsider-token")
    };
    var outsiderGroupAccess = await groupsController.GetGroup(ownerGroup.GroupId, CancellationToken.None);
    var outsiderGroupProblem = outsiderGroupAccess.Result as ObjectResult;
    Assert(outsiderGroupProblem?.StatusCode == StatusCodes.Status403Forbidden, "group lookup should reject authenticated outsiders.");

    var fleetCallCount = 0;
    var fleetBridge = new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(request =>
    {
        Interlocked.Increment(ref fleetCallCount);
        return JsonResponse(new { detail = "fleet should not be called" }, HttpStatusCode.InternalServerError);
    })), configuration);
    var boostSessions = new BoostSessionService(store, accounts, groups, fleetBridge, rewards);
    var pendingSession = boostSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "fleet",
        GroupId: ownerGroup.GroupId,
        SubjectLabel: "Runner Demo"));
    boostSessions.RecordConsent(pendingSession.SponsorSessionId);
    var locallyStopped = await boostSessions.StopAsync(pendingSession.SponsorSessionId, revoke: false, CancellationToken.None);
    Assert(string.Equals(locallyStopped.Session.Status, "stopped", StringComparison.OrdinalIgnoreCase), "sessions without Fleet lanes should stop locally.");
    Assert(locallyStopped.Session.ActivatedAtUtc is null, "sessions stopped before auth should never report activation.");
    Assert(
        boostSessions.ListBadgesForSessionUser(pendingSession.SponsorSessionId).Any(static badge => string.Equals(badge.Key, "chickened-out", StringComparison.OrdinalIgnoreCase) && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)),
        "stopping after consent but before activation should award the Chickened Out badge.");
    Assert(fleetCallCount == 0, "stopping a session before lane creation should not call Fleet.");

    var laterBridge = new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(request =>
    {
        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes")
        {
            return JsonResponse(new
            {
                lane = new
                {
                    lane_id = "participant-auth-success",
                    status = "pending_auth",
                    authorization_tier = "pro",
                    tier_source = "fleet_detected",
                    credential_handle = "cred-secret-123",
                    telemetry = new
                    {
                        auth_ready = false,
                        credential_handle = "cred-secret-123",
                    },
                },
            });
        }

        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes/participant-auth-success/device-auth/start")
        {
            return JsonResponse(new
            {
                lane = new
                {
                    lane_id = "participant-auth-success",
                    status = "pending_auth",
                    authorization_tier = "pro",
                    tier_source = "fleet_detected",
                    credential_handle = "cred-secret-123",
                    device_auth = new
                    {
                        verification_uri = "https://example.com/device",
                        user_code = "ABCD-EFGH",
                        auth_ready = true,
                    },
                    telemetry = new
                    {
                        auth_ready = true,
                        authorization_tier = "pro",
                        tier_source = "fleet_detected",
                        credential_handle = "cred-secret-123",
                    },
                },
            });
        }

        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes/participant-auth-success/activate")
        {
            return JsonResponse(new
            {
                lane = new
                {
                    lane_id = "participant-auth-success",
                    status = "active",
                    authorization_tier = "pro",
                    tier_source = "fleet_detected",
                    credential_handle = "cred-secret-123",
                    telemetry = new
                    {
                        auth_ready = true,
                        authorization_tier = "pro",
                        tier_source = "fleet_detected",
                        credential_handle = "cred-secret-123",
                    },
                },
            });
        }

        return JsonResponse(new { detail = "unexpected fleet call" }, HttpStatusCode.InternalServerError);
    })), configuration);
    var laterSessions = new BoostSessionService(store, accounts, groups, laterBridge, rewards);
    var laterSession = laterSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "fleet",
        GroupId: ownerGroup.GroupId,
        SubjectLabel: "Runner Demo",
        RequestedLaneRole: "deep_review",
        AuthorizationTier: "pro",
        TierSource: "user_declared"));
    laterSessions.RecordConsent(laterSession.SponsorSessionId);
    var authStarted = await laterSessions.StartDeviceAuthAsync(laterSession.SponsorSessionId, CancellationToken.None);
    Assert(authStarted.Session.AuthorizedAtUtc is not null, "auth-ready device auth should mark the sponsor session as authorized.");
    Assert(string.Equals(authStarted.Session.Status, "active", StringComparison.OrdinalIgnoreCase), "auth-ready device auth should auto-activate the contribution lane.");
    Assert(string.Equals(authStarted.Session.RequestedLaneRole, "deep_review", StringComparison.OrdinalIgnoreCase), "sponsor sessions should preserve the requested participation role.");
    Assert(string.IsNullOrWhiteSpace(authStarted.Session.DeviceAuthUserCode), "auth-ready sponsor sessions should clear the one-time device-auth code from the session snapshot.");
    Assert(string.IsNullOrWhiteSpace(authStarted.Session.DeviceAuthVerificationUri), "auth-ready sponsor sessions should clear the device-auth verification URI from the session snapshot.");
    var storeJson = File.ReadAllText(Path.Combine(tempRoot, "community-store.json"));
    Assert(!storeJson.Contains("ABCD-EFGH", StringComparison.Ordinal), "the durable community snapshot should not persist device-auth user codes.");
    Assert(!storeJson.Contains("https://example.com/device", StringComparison.Ordinal), "the durable community snapshot should not persist device-auth verification URIs.");
    var laterBadges = laterSessions.ListBadgesForSessionUser(laterSession.SponsorSessionId);
    Assert(!laterBadges.Any(static badge => string.Equals(badge.Key, "chickened-out", StringComparison.OrdinalIgnoreCase) && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)), "later successful authorization should revoke the Chickened Out badge.");
    Assert(laterBadges.Any(static badge => string.Equals(badge.Key, "contributor-ready", StringComparison.OrdinalIgnoreCase) && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)), "auth-ready contribution lanes should award the non-scoring contributor-ready badge.");
    Assert(laterBadges.Any(static badge => string.Equals(badge.Key, "pro-sponsor-active", StringComparison.OrdinalIgnoreCase) && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)), "current sponsor tier should award a transient active-tier badge.");
    var boostSessionsController = new BoostSessionsController(accounts, identityClient, leaderboards, laterSessions)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var boostedSessionPayload = await boostSessionsController.Get(laterSession.SponsorSessionId, CancellationToken.None);
    var boostedSessionJson = JsonSerializer.Serialize((boostedSessionPayload.Result as OkObjectResult)?.Value);
    Assert(!boostedSessionJson.Contains("cred-secret-123", StringComparison.Ordinal), "boost-session envelopes should not expose raw Fleet credential handles.");
    Assert(!boostedSessionJson.Contains("\"telemetry\"", StringComparison.Ordinal), "boost-session envelopes should not expose raw Fleet telemetry blobs.");
    Assert(boostedSessionJson.Contains("credentialHandlePresent", StringComparison.Ordinal), "boost-session envelopes should project only a boolean credential-handle presence flag.");
    var recognition = leaderboards.UserRecognitionSummary(createdUser.UserId);
    Assert(string.Equals(recognition.CurrentAuthorizationTier, "pro", StringComparison.OrdinalIgnoreCase), "recognition summary should report the current sponsor tier.");
    Assert(recognition.CurrentSponsorRankScore > recognition.LifetimePoints, "current sponsor rank should include a derived active-tier bonus without rewriting lifetime points.");

    var laneCreationBridge = new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(request =>
    {
        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes")
        {
            return JsonResponse(new { lane = new { } });
        }

        return JsonResponse(new { detail = "unexpected fleet call" }, HttpStatusCode.InternalServerError);
    })), configuration);
    var laneCreationSessions = new BoostSessionService(store, accounts, groups, laneCreationBridge, rewards);
    var laneCreationSession = laneCreationSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "fleet",
        GroupId: ownerGroup.GroupId,
        SubjectLabel: "Runner Demo"));
    laneCreationSessions.RecordConsent(laneCreationSession.SponsorSessionId);
    var missingLaneUnavailable = false;
    try
    {
        await laneCreationSessions.StartDeviceAuthAsync(laneCreationSession.SponsorSessionId, CancellationToken.None);
    }
    catch (ParticipationUnavailableException ex)
    {
        missingLaneUnavailable = ex.Message.Contains("Participation is unavailable", StringComparison.OrdinalIgnoreCase);
    }

    Assert(missingLaneUnavailable, "device-auth startup should treat missing Fleet lane ids as infrastructure unavailability instead of a client error.");
    var failedLaneSession = laneCreationSessions.Get(laneCreationSession.SponsorSessionId);
    Assert(string.IsNullOrWhiteSpace(failedLaneSession?.FleetLaneId), "failed lane creation should not persist an empty Fleet lane id.");

    var missingLaneController = new CodexParticipationController(
        accounts,
        identityClient,
        leaderboards,
        laneCreationSessions,
        identityLinks,
        experience,
        chrome,
        configuration,
        loggerFactory.CreateLogger<CodexParticipationController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var unavailableContributionStart = await missingLaneController.StartContribution(CancellationToken.None);
    var unavailableContributionStartProblem = unavailableContributionStart.Result as ObjectResult;
    Assert(unavailableContributionStartProblem?.StatusCode == StatusCodes.Status503ServiceUnavailable, "contribution start should report missing Fleet lane ids as 503 instead of bad request.");
    var unavailableContributionEnvelopeJson = JsonSerializer.Serialize(unavailableContributionStartProblem?.Value);
    Assert(unavailableContributionEnvelopeJson.Contains("\"lifecycle\"", StringComparison.Ordinal), "unavailable contribution envelopes should include lifecycle state details.");
    Assert(unavailableContributionEnvelopeJson.Contains("\"breadcrumbs\"", StringComparison.Ordinal), "unavailable contribution envelopes should include decision breadcrumb projections.");
    Assert(unavailableContributionEnvelopeJson.Contains("\"failureGuidance\"", StringComparison.Ordinal), "unavailable contribution envelopes should include explicit failure guidance.");

    var waitingBridge = new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(request =>
    {
        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes")
        {
            return JsonResponse(new { detail = "participant burst capacity reached for fleet" }, HttpStatusCode.Conflict);
        }

        return JsonResponse(new { detail = "unexpected fleet call" }, HttpStatusCode.InternalServerError);
    })), configuration);
    var waitingSessions = new BoostSessionService(store, accounts, groups, waitingBridge, rewards);
    var waitingSession = waitingSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "fleet",
        GroupId: ownerGroup.GroupId,
        SubjectLabel: "Runner Demo",
        RequestedLaneRole: "review",
        AuthorizationTier: "plus",
        TierSource: "user_declared"));
    waitingSessions.RecordConsent(waitingSession.SponsorSessionId);
    var waitingResult = await waitingSessions.StartDeviceAuthAsync(waitingSession.SponsorSessionId, CancellationToken.None);
    Assert(string.Equals(waitingResult.Session.Status, "waiting_for_slot", StringComparison.OrdinalIgnoreCase), "capacity pressure should move sponsor sessions into waiting_for_slot instead of throwing.");
    Assert(string.Equals(waitingResult.Session.RequestedLaneRole, "review", StringComparison.OrdinalIgnoreCase), "waiting sessions should keep the requested sponsor role.");
    var waitingController = new CodexParticipationController(
        accounts,
        identityClient,
        leaderboards,
        waitingSessions,
        identityLinks,
        experience,
        chrome,
        configuration,
        loggerFactory.CreateLogger<CodexParticipationController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var waitingEnvelopeResult = await waitingController.GetIntent(waitingSession.SponsorSessionId, CancellationToken.None);
    var waitingEnvelopePayload = waitingEnvelopeResult.Result is OkObjectResult waitingOk
        ? waitingOk.Value
        : waitingEnvelopeResult.Value;
    var waitingEnvelopeJson = JsonSerializer.Serialize(waitingEnvelopePayload);
    Assert(waitingEnvelopeJson.Contains("\"waiting_for_slot\"", StringComparison.Ordinal), "waiting contribution envelopes should preserve queue status.");

    var occupiedBridge = new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(request =>
    {
        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes")
        {
            return JsonResponse(new
            {
                lane = new
                {
                    lane_id = "participant-occupied",
                    status = "pending_auth",
                    authorization_tier = "unknown",
                    tier_source = "unknown",
                    telemetry = new
                    {
                        auth_ready = false,
                    },
                },
            });
        }

        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes/participant-occupied/device-auth/start")
        {
            return JsonResponse(new
            {
                lane = new
                {
                    lane_id = "participant-occupied",
                    status = "pending_auth",
                    device_auth = new
                    {
                        verification_uri = "https://example.com/device",
                        user_code = "OCCUPIED-CODE",
                        auth_ready = false,
                    },
                    telemetry = new
                    {
                        auth_ready = false,
                    },
                },
            });
        }

        return JsonResponse(new { detail = "unexpected fleet call" }, HttpStatusCode.InternalServerError);
    })), configuration);
    var occupiedSessions = new BoostSessionService(store, accounts, groups, occupiedBridge, rewards);
    var occupiedSession = occupiedSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "hub",
        SubjectLabel: "Runner Demo"));
    occupiedSessions.RecordConsent(occupiedSession.SponsorSessionId);
    var occupiedResult = await occupiedSessions.StartDeviceAuthAsync(occupiedSession.SponsorSessionId, CancellationToken.None);
    Assert(string.Equals(occupiedResult.Session.Status, "pending_auth", StringComparison.OrdinalIgnoreCase), "occupied project setup should keep the existing lane in pending auth.");

    var timeoutBridge = new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(_ => throw new TaskCanceledException("simulated timeout"))), configuration);
    var timeoutSessions = new BoostSessionService(store, accounts, groups, timeoutBridge, rewards);
    var timeoutSession = timeoutSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.member",
        ProjectId: "hub",
        SubjectLabel: "Member Demo"));
    timeoutSessions.RecordConsent(timeoutSession.SponsorSessionId);
    var timeoutResult = await timeoutSessions.StartDeviceAuthAsync(timeoutSession.SponsorSessionId, CancellationToken.None);
    Assert(string.Equals(timeoutResult.Session.Status, "waiting_for_slot", StringComparison.OrdinalIgnoreCase), "lane creation timeouts should fall back to waiting_for_slot when the project already has another live participant lane.");

    var outsiderSessionBlocked = false;
    try
    {
        _ = waitingSessions.Create(new CreateSponsorSessionRequest(
            SubjectId: "subject.outsider",
            ProjectId: "hub",
            GroupId: ownerGroup.GroupId,
            SubjectLabel: "Outsider Demo"));
    }
    catch (CommunityAccessDeniedException ex)
    {
        outsiderSessionBlocked = ex.Message.Contains("belong to the group", StringComparison.OrdinalIgnoreCase);
    }

    Assert(outsiderSessionBlocked, "explicit sponsor-session groups should reject outsiders.");

    var redeemedBoostCodeSessionBlocked = false;
    try
    {
        _ = waitingSessions.Create(new CreateSponsorSessionRequest(
            SubjectId: "subject.outsider",
            ProjectId: "hub",
            BoostCode: boostCode.Code,
            SubjectLabel: "Outsider Demo"));
    }
    catch (CommunityAccessDeniedException ex)
    {
        redeemedBoostCodeSessionBlocked = ex.Message.Contains("belong to the group", StringComparison.OrdinalIgnoreCase);
    }

    Assert(redeemedBoostCodeSessionBlocked, "redeemed boost codes should not let outsiders bind sponsor sessions to the original group.");

    var reuseBridge = new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(request =>
    {
        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes")
        {
            return JsonResponse(new
            {
                lane = new
                {
                    lane_id = "participant-reuse-check",
                    status = "pending_auth",
                    authorization_tier = "plus",
                    tier_source = "fleet_detected",
                    telemetry = new
                    {
                        auth_ready = false,
                    },
                },
            });
        }

        if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/api/internal/participant-lanes/participant-reuse-check/device-auth/start")
        {
            return JsonResponse(new
            {
                lane = new
                {
                    lane_id = "participant-reuse-check",
                    status = "pending_auth",
                    authorization_tier = "plus",
                    tier_source = "fleet_detected",
                    device_auth = new
                    {
                        verification_uri = "https://example.com/device",
                        user_code = "REUSE-CODE",
                        auth_ready = false,
                    },
                    telemetry = new
                    {
                        auth_ready = false,
                        authorization_tier = "plus",
                        tier_source = "fleet_detected",
                    },
                },
            });
        }

        return JsonResponse(new { detail = "unexpected fleet call" }, HttpStatusCode.InternalServerError);
    })), configuration);
    var reuseSessions = new BoostSessionService(store, accounts, groups, reuseBridge, rewards);
    var reusableSession = reuseSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "fleet",
        GroupId: ownerGroup.GroupId,
        SubjectLabel: "Runner Demo",
        RequestedLaneRole: "coding"));
    reuseSessions.RecordConsent(reusableSession.SponsorSessionId);
    var distractorSession = reuseSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "fleet",
        GroupId: ownerGroup.GroupId,
        SubjectLabel: "Runner Demo",
        RequestedLaneRole: "review",
        AuthorizationTier: "plus",
        TierSource: "user_declared"));
    reuseSessions.RecordConsent(distractorSession.SponsorSessionId);
    var reusedContribution = await reuseSessions.StartContributionAsync(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "fleet",
        GroupId: ownerGroup.GroupId,
        SubjectLabel: "Runner Demo",
        RequestedLaneRole: "coding"), CancellationToken.None);
    Assert(
        string.Equals(reusedContribution.Session.SponsorSessionId, reusableSession.SponsorSessionId, StringComparison.OrdinalIgnoreCase),
        "start contribution should reuse the matching open session even when a different-role session is more recent.");

    var invalidRoleThrown = false;
    try
    {
        _ = laterSessions.Create(new CreateSponsorSessionRequest(
            SubjectId: "subject.demo",
            ProjectId: "fleet",
            GroupId: ownerGroup.GroupId,
            RequestedLaneRole: "deep_review",
            AuthorizationTier: "free",
            TierSource: "user_declared"));
    }
    catch (InvalidOperationException ex)
    {
        invalidRoleThrown = ex.Message.Contains("deep review", StringComparison.OrdinalIgnoreCase)
            || ex.Message.Contains("pro", StringComparison.OrdinalIgnoreCase);
    }

    Assert(invalidRoleThrown, "deep review sponsor sessions should require a higher authorization tier.");
}

async Task VerifyTeableUserProjectionWorkflowAsync()
{
    var tempRoot = Path.Combine(Path.GetTempPath(), "run-services-teable-smoke", Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempRoot);
    try
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                ["FLEET_INTERNAL_API_TOKEN"] = "smoke-token",
                ["CHUMMER_TEABLE_USERS_ENABLED"] = "true",
                ["CHUMMER_TEABLE_USERS_API_KEY"] = "teable-smoke-token",
                ["CHUMMER_TEABLE_USERS_API_BASE_URL"] = "https://app.teable.ai/api",
                ["CHUMMER_TEABLE_USERS_BASE_ID"] = "base-demo",
                ["CHUMMER_TEABLE_USERS_TABLE_NAME"] = "Chummer Run Users",
                ["CHUMMER_TEABLE_USERS_RECONCILE_ENABLED"] = "false",
            })
            .Build();
        using var loggerFactory = LoggerFactory.Create(static builder => builder.SetMinimumLevel(LogLevel.None));
        var store = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
        var teableRequests = new List<(HttpMethod Method, string Path, string Body)>();
        var existingRecordIdByUserId = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var fields = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        static string? ExtractUserId(string path)
        {
            const string marker = "filterByTql=";
            var markerIndex = path.IndexOf(marker, StringComparison.Ordinal);
            if (markerIndex < 0)
            {
                return null;
            }

            var encoded = path[(markerIndex + marker.Length)..];
            var next = encoded.IndexOf('&');
            if (next >= 0)
            {
                encoded = encoded[..next];
            }

            var filter = Uri.UnescapeDataString(encoded);
            const string prefix = "{User Id} = '";
            var start = filter.IndexOf(prefix, StringComparison.Ordinal);
            if (start < 0)
            {
                return null;
            }

            start += prefix.Length;
            var end = filter.IndexOf('\'', start);
            return end <= start ? null : filter[start..end];
        }

        var teableHttp = new HttpClient(new StubHttpMessageHandler(request =>
        {
            var path = request.RequestUri?.PathAndQuery ?? string.Empty;
            var body = request.Content?.ReadAsStringAsync().GetAwaiter().GetResult() ?? string.Empty;
            teableRequests.Add((request.Method, path, body));

            if (request.Method == HttpMethod.Get && path == "/api/base/base-demo/table")
            {
                return JsonResponse(Array.Empty<object>());
            }

            if (request.Method == HttpMethod.Post && path == "/api/base/base-demo/table/")
            {
                return JsonResponse(new { id = "tbl_users" }, HttpStatusCode.Created);
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_users/field", StringComparison.Ordinal))
            {
                return JsonResponse(fields.Select(static name => new { id = $"fld_{name.Replace(" ", "_", StringComparison.Ordinal)}", name }).ToArray());
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_users/field")
            {
                using var document = JsonDocument.Parse(body);
                var name = document.RootElement.GetProperty("name").GetString() ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(name))
                {
                    fields.Add(name);
                }

                return JsonResponse(new { id = $"fld_{fields.Count}", name }, HttpStatusCode.Created);
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_users/record?", StringComparison.Ordinal))
            {
                var userId = ExtractUserId(path) ?? string.Empty;
                return existingRecordIdByUserId.TryGetValue(userId, out var recordId)
                    ? JsonResponse(new { records = new[] { new { id = recordId } } })
                    : JsonResponse(new { records = Array.Empty<object>() });
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_users/record")
            {
                return JsonResponse(new { records = new[] { new { id = "rec_created" } } }, HttpStatusCode.Created);
            }

            if (request.Method == HttpMethod.Patch && path.StartsWith("/api/table/tbl_users/record/", StringComparison.Ordinal))
            {
                return JsonResponse(new { id = "rec_existing" });
            }

            return new HttpResponseMessage(HttpStatusCode.NotFound)
            {
                Content = new StringContent($"unexpected teable request: {path}", Encoding.UTF8, "text/plain")
            };
        }));
        var teableUsers = new TeableUserProjectionService(
            store,
            configuration,
            new StubHttpClientFactory(teableHttp),
            loggerFactory.CreateLogger<TeableUserProjectionService>());
        var accounts = new AccountService(store, teableUsers, loggerFactory.CreateLogger<AccountService>());

        var user = accounts.EnsureUser("subject.demo", "Runner Demo", "runner@example.invalid");
        var controller = new InternalTeableUsersController(teableUsers, configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer smoke-token";

        var dashboardResponse = await controller.GetDashboard(sync: true, CancellationToken.None);
        var dashboard = (dashboardResponse.Result as OkObjectResult)?.Value as TeableUserProjectionDashboard;
        Assert(dashboard is not null, "internal Teable dashboard should return a payload.");
        Assert(dashboard!.Users.Any(item => string.Equals(item.UserId, user.UserId, StringComparison.Ordinal) && string.Equals(item.Email, "runner@example.invalid", StringComparison.Ordinal)), "internal Teable dashboard should expose the stored hub user projection.");
        Assert(teableRequests.Any(item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_users/record"), "Teable dashboard sync should create a record for new users.");

        teableRequests.Clear();
        existingRecordIdByUserId[user.UserId] = "rec_existing";
        var syncResponse = await controller.SyncAll(CancellationToken.None);
        var syncResult = (syncResponse.Result as OkObjectResult)?.Value as TeableUserProjectionSyncResult;
        Assert(syncResult is not null && string.Equals(syncResult.State, "passed", StringComparison.OrdinalIgnoreCase), "internal Teable sync should report success.");
        Assert(teableRequests.Any(item => item.Method == HttpMethod.Patch && item.Path == "/api/table/tbl_users/record/rec_existing"), "Teable sync should patch existing user rows instead of duplicating them.");
    }
    finally
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }
}

async Task VerifyPublicLandingProjectionAsync()
{
    var tempRoot = Path.Combine(Path.GetTempPath(), "run-services-smoke", Guid.NewGuid().ToString("N"));
    var storePath = Path.Combine(tempRoot, "community-store.json");
    var downloadsRoot = Path.Combine(tempRoot, "downloads");
    var downloadsFilesRoot = Path.Combine(downloadsRoot, "files");
    Directory.CreateDirectory(downloadsFilesRoot);
    File.WriteAllText(Path.Combine(downloadsFilesRoot, "smoke-poc-linux-x64.zip"), "smoke");
    File.WriteAllText(Path.Combine(downloadsFilesRoot, "smoke-poc-osx-arm64-installer.dmg"), "smoke-mac");
    File.WriteAllText(
        Path.Combine(downloadsRoot, "RELEASE_CHANNEL.generated.json"),
        JsonSerializer.Serialize(
            new
            {
                schemaVersion = 1,
                product = "chummer6",
                channelId = "preview",
                version = "0.6.1-smoke",
                publishedAt = "2026-03-20T12:00:00Z",
                status = "published",
                artifactSource = "ui_desktop_bundle",
                rolloutState = "local_docker_preview",
                rolloutReason = "Current release shelf was exercised by the local docker release proof harness before publication.",
                supportabilityState = "local_docker_proven",
                supportabilitySummary = "Local release proof passed for install, build/explain, campaign recovery, and support closure journeys.",
                knownIssueSummary = "Preview caveats still apply, but the current shelf has recent proof instead of only manifest presence.",
                fixAvailabilitySummary = "Only send fixed notices after the affected install can receive the published channel artifact now on the shelf.",
                releaseProof = new
                {
                    status = "passed",
                    generatedAt = "2026-03-20T12:15:00Z",
                    baseUrl = "http://127.0.0.1:8091",
                    journeysPassed = new[]
                    {
                        "install_claim_restore_continue",
                        "build_explain_publish",
                    },
                    proofRoutes = new[]
                    {
                        "/downloads/install/smoke-poc-linux-x64"
                    }
                },
                artifacts = new[]
                {
                    new
                    {
                        artifactId = "smoke-poc-linux-x64",
                        head = "avalonia",
                        platform = "linux",
                        arch = "x64",
                        kind = "archive",
                        fileName = "smoke-poc-linux-x64.zip",
                        downloadUrl = "/downloads/files/smoke-poc-linux-x64.zip",
                        sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                        sizeBytes = 4096,
                        platformLabel = "Smoke Linux x64"
                    },
                    new
                    {
                        artifactId = "smoke-poc-osx-arm64-installer",
                        head = "avalonia",
                        platform = "macOS",
                        arch = "arm64",
                        kind = "dmg",
                        fileName = "smoke-poc-osx-arm64-installer.dmg",
                        downloadUrl = "/downloads/files/smoke-poc-osx-arm64-installer.dmg",
                        sha256 = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
                        sizeBytes = 8192,
                        platformLabel = "Smoke macOS ARM64"
                    }
                }
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    File.WriteAllText(
        Path.Combine(downloadsRoot, "releases.json"),
        JsonSerializer.Serialize(
            new PublicReleaseManifestDto(
                Version: "0.6.1-smoke",
                Channel: "preview",
                PublishedAt: new DateTimeOffset(2026, 3, 20, 12, 0, 0, TimeSpan.Zero),
                Downloads:
                [
                    new PublicReleaseArtifactDto(
                        Id: "smoke-poc-linux-x64",
                        Platform: "linux-x64",
                        Url: "/downloads/files/smoke-poc-linux-x64.zip",
                        Sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                        SizeBytes: 4096),
                    new PublicReleaseArtifactDto(
                        Id: "smoke-poc-osx-arm64-installer",
                        Platform: "macOS ARM64",
                        Url: "/downloads/files/smoke-poc-osx-arm64-installer.dmg",
                        Sha256: "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
                        SizeBytes: 8192,
                        Head: "avalonia",
                        PlatformId: "osx-arm64",
                        Arch: "arm64",
                        Kind: "dmg",
                        FileName: "smoke-poc-osx-arm64-installer.dmg")
                ]),
            new JsonSerializerOptions(JsonSerializerDefaults.Web)));

    var configuration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_CANON_ROOT"] = "/docker/chummercomplete/chummer.run-services",
            ["CHUMMER_COMMUNITY_STORE_PATH"] = storePath,
            ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(tempRoot, "install-linking-store.json"),
            ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(tempRoot, "support-store.json"),
            ["CHUMMER_SUPPORT_ATTACHMENT_ROOT"] = Path.Combine(tempRoot, "support-attachments"),
            ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
            ["FLEET_INTERNAL_API_TOKEN"] = "smoke-token",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "true",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BASE_URL"] = "http://ea-smoke:8090",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_API_TOKEN"] = "ea-smoke-token",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_PRINCIPAL_ID"] = "support-progress-principal",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BINDING_ID"] = "binding-support-progress",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_API_KEY"] = "emailit-smoke-token",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_BASE_URL"] = "https://api.emailit.com/v2",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_FROM_EMAIL"] = "wageslave@chummer.run",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_FROM_NAME"] = "Wageslave",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_REPLY_TO"] = "support@chummer.run",
            ["CHUMMER_SUPPORT_PROGRESS_EMAIL_PUBLIC_BASE_URL"] = "https://chummer.run",
        })
        .Build();
    using var loggerFactory = LoggerFactory.Create(static builder => builder.SetMinimumLevel(LogLevel.None));
    var canon = new PublicCanonFileLoader(configuration);
    var routes = new PublicRouteCatalogService(canon);
    var actions = new PublicActionResolver();
    var landing = new PublicLandingService(canon, actions);
    var navigation = new PublicNavigationService(canon, routes);
    var releases = new PublicReleaseManifestService(configuration);
    var releaseSelection = new ReleaseSelectionService(canon);
    var chrome = new HubPageChromeService(landing, navigation, releases, releaseSelection, new HttpContextAccessor());
    var weeklyPulseArtifact = new WeeklyProductPulseArtifactService(configuration, loggerFactory.CreateLogger<WeeklyProductPulseArtifactService>());
    var progress = new PublicProgressService(configuration, weeklyPulseArtifact, loggerFactory.CreateLogger<PublicProgressService>());
    var trustContent = new PublicTrustContentService(canon, routes);
    var installLinkingStore = new InstallLinkingStore(configuration, loggerFactory.CreateLogger<InstallLinkingStore>());
    var supportStore = new SupportStore(configuration, loggerFactory.CreateLogger<SupportStore>());
    var supportAttachments = new SupportAttachmentStorageService(configuration);
    var installLinking = new InstallLinkingService(installLinkingStore, configuration);
    var communityStore = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
    var rewards = new RewardService(communityStore);
    var executeRequests = new List<(string Path, string Body, string Authorization, string PrincipalId)>();
    var emailitRequests = new List<(string Path, string Body, string Authorization, string IdempotencyKey)>();
    var sentReceiptRequests = new List<(string Path, string Body)>();
    var failedReceiptRequests = new List<(string Path, string Body)>();
    var progressEmails = new SupportProgressEmailWorkflowService(
        new HttpClient(new StubHttpMessageHandler(request =>
        {
            var path = request.RequestUri?.AbsolutePath ?? string.Empty;
            var body = request.Content?.ReadAsStringAsync().GetAwaiter().GetResult() ?? string.Empty;
            if (string.Equals(path, "/v1/tools/execute", StringComparison.Ordinal))
            {
                executeRequests.Add((
                    path,
                    body,
                    request.Headers.Authorization?.Parameter ?? string.Empty,
                    request.Headers.TryGetValues("x-ea-principal-id", out var values) ? values.SingleOrDefault() ?? string.Empty : string.Empty));
                string deliveryId = $"delivery-{executeRequests.Count}";
                return JsonResponse(new
                {
                    tool_name = "connector.dispatch",
                    target_ref = deliveryId,
                    output_json = new { delivery_id = deliveryId, status = "queued" },
                    receipt_json = new { handler_key = "connector.dispatch", invocation_contract = "tool.v1" }
                }, HttpStatusCode.OK);
            }

            if (string.Equals(path, "/v2/emails", StringComparison.Ordinal))
            {
                emailitRequests.Add((
                    path,
                    body,
                    request.Headers.Authorization?.Parameter ?? string.Empty,
                    request.Headers.TryGetValues("Idempotency-Key", out var values) ? values.SingleOrDefault() ?? string.Empty : string.Empty));
                return JsonResponse(new { id = $"emailit-{emailitRequests.Count}" }, HttpStatusCode.Accepted);
            }

            if (path.Contains("/v1/delivery/outbox/", StringComparison.Ordinal) && path.EndsWith("/sent", StringComparison.Ordinal))
            {
                sentReceiptRequests.Add((path, body));
                return JsonResponse(new { status = "sent" }, HttpStatusCode.OK);
            }

            if (path.Contains("/v1/delivery/outbox/", StringComparison.Ordinal) && path.EndsWith("/failed", StringComparison.Ordinal))
            {
                failedReceiptRequests.Add((path, body));
                return JsonResponse(new { status = "failed" }, HttpStatusCode.OK);
            }

            return new HttpResponseMessage(HttpStatusCode.NotFound)
            {
                Content = new StringContent($"unexpected request: {path}", Encoding.UTF8, "text/plain")
            };
        })),
        configuration,
        loggerFactory.CreateLogger<SupportProgressEmailWorkflowService>());
    var supportCases = new SupportCaseService(
        supportStore,
        supportAttachments,
        rewards,
        progressEmails,
        loggerFactory.CreateLogger<SupportCaseService>());
    var robotsPath = Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "wwwroot", "robots.txt");
    Assert(File.Exists(robotsPath), "public shell should ship a robots.txt file.");
    var robotsText = File.ReadAllText(robotsPath);
    Assert(robotsText.Contains("Disallow: /", StringComparison.Ordinal), "robots.txt should disallow crawler access.");
    Assert(robotsText.Contains("Noindex: /", StringComparison.Ordinal), "robots.txt should carry the explicit noindex directive requested for the public shell.");
    var layoutSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
    Assert(!layoutSource.Contains("site-nav-sheet", StringComparison.Ordinal), "layout should not render the old duplicate mobile nav sheet.");
    Assert(layoutSource.Contains("site-bottom-cta", StringComparison.Ordinal), "layout should keep a mobile-first sticky primary CTA for the public shell.");
    Assert(!layoutSource.Contains("Help, legal, and utility", StringComparison.Ordinal), "compact public footer should stop carrying utility links in the product-route disclosure.");
    var authEntrySource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "Auth", "Entry.cshtml"));
    Assert(!authEntrySource.Contains("auth-panel__support", StringComparison.Ordinal), "auth entry should keep one quiet support row instead of duplicating support chrome inside the panel.");
    var landingSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));
    Assert(!landingSource.Contains("artifact-gallery", StringComparison.Ordinal), "landing should keep artifact depth off the main conversion spine.");
    Assert(landingSource.Contains("proofSectionAsset", StringComparison.Ordinal), "landing should use a separate lower proof asset instead of rendering the same proof screenshot twice.");
    Assert(landingSource.Contains("scene_dossier_desk", StringComparison.Ordinal), "landing should pair the hero proof teaser with a different lower proof asset.");
    Assert(landingSource.Contains("string.Equals(proofSectionAsset.AssetSlot, heroProofAsset.AssetSlot", StringComparison.Ordinal), "landing should guard against reusing the same proof asset slot in both the hero and lower proof band.");
    Assert(landingSource.Contains("var proofNotes = Model.Workflows.Take(1).ToArray();", StringComparison.Ordinal), "landing should keep the proof band to one tighter workflow note instead of restating the whole product loop.");
    Assert(landingSource.Contains("<div class=\"release-footnote\">", StringComparison.Ordinal), "landing proof should reduce the workflow follow-through to one quieter note instead of a second full card grid.");
    Assert(!landingSource.Contains("role-matrix__grid", StringComparison.Ordinal), "landing proof should not reopen a second mini-grid once the hero already carries the main conversion story.");
    Assert(!landingSource.Contains("works-column__header", StringComparison.Ordinal), "landing should collapse the what-works-now strip instead of restating three full column headers.");
    Assert(landingSource.Contains("Preview in progress:", StringComparison.Ordinal), "landing should demote preview-in-progress copy to a quieter shelf note instead of a full third state card.");
    Assert(landingSource.Contains("Need the full picture?", StringComparison.Ordinal), "landing should route deeper proof evaluation through one quiet inline note instead of a second button stack.");
    Assert(landingSource.Contains("PublicSurfaceStatus.DisplayLabel", StringComparison.Ordinal), "landing should use the shared public status presenter instead of route-local badge labels.");
    Assert(landingSource.Contains("_PublicTrustPulseBody.cshtml", StringComparison.Ordinal), "landing should render weekly trust rows through the shared pulse body instead of duplicating the row template.");
    Assert(landingSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "landing should reuse the shared signed-in trust panel instead of inventing a landing-only trust surface.");
    Assert(landingSource.Contains("TrustRowValue(Model.SignedInStatus, \"Who can get it now\"", StringComparison.Ordinal), "landing should reuse the signed-in trust posture for live access guidance on the authenticated front door.");
    Assert(landingSource.Contains("starterFirstPlayableSession = starterWorkspace?.FirstPlayableSession", StringComparison.Ordinal), "landing should derive the signed-in starter lane from the grounded first playable session truth already attached to the campaign spine.");
    Assert(landingSource.Contains("Open starter lane on Home", StringComparison.Ordinal), "landing should keep a direct signed-in starter-lane route instead of forcing repo knowledge.");
    Assert(landingSource.Contains("Open first playable session proof", StringComparison.Ordinal), "landing should keep a direct route from the front door into the bounded first-session proof drawer.");
    Assert(landingSource.Contains("TrustRowValue(Model.SignedInStatus, \"Fix availability\"", StringComparison.Ordinal), "landing starter lane should reuse signed-in fix-availability truth instead of tutorial prose.");
    Assert(landingSource.Contains("TrustRowValue(Model.SignedInStatus, \"Current caution\"", StringComparison.Ordinal), "landing starter lane should reuse signed-in caution truth instead of tutorial prose.");
    Assert(landingSource.Contains("Open install support", StringComparison.Ordinal), "landing starter lane should keep install-support follow-through on the same governed front-door rail.");
    var trustPulseBodySource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "Shared", "_PublicTrustPulseBody.cshtml"));
    Assert(trustPulseBodySource.Contains("@if (Model.TrendSamples.Count > 1)", StringComparison.Ordinal), "shared trust pulse body should render measured progress points directly on the weekly trust pulse.");
    Assert(trustPulseBodySource.Contains("trust-pulse-trend__point", StringComparison.Ordinal), "shared trust pulse body should carry the measured-trend rail.");
    Assert(trustPulseBodySource.Contains("@foreach (var row in Model.Rows)", StringComparison.Ordinal), "shared trust pulse body should render every weekly trust row instead of binding a brittle subset.");
    Assert(trustPulseBodySource.Contains("<span>@row.Label</span>", StringComparison.Ordinal), "shared trust pulse body should project the shared weekly trust labels directly.");
    Assert(trustPulseBodySource.Contains("<strong>@row.Value</strong>", StringComparison.Ordinal), "shared trust pulse body should project the shared weekly trust values directly.");
    var storySource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "ProductStory.cshtml"));
    Assert(!storySource.Contains("One path from install to session return", StringComparison.Ordinal), "product story should not drift back into a second install/support explainer.");
    Assert(!storySource.Contains("From first install to next session", StringComparison.Ordinal), "product story should stay focused on differentiation instead of retelling the install path.");
    Assert(!storySource.Contains("Start from the lane that matches your job", StringComparison.Ordinal), "product story should not fall back to a second lane selector once landing already owns that job.");
    Assert(!storySource.Contains("product loop", StringComparison.Ordinal), "product story should avoid internal loop phrasing on the customer-facing differentiation page.");
    Assert(!storySource.Contains("story-guide-tail", StringComparison.Ordinal), "product story should not end in a second landing-style CTA band.");
    Assert(!storySource.Contains("Go deeper only where you still need proof", StringComparison.Ordinal), "product story should not end with another full-width guidance section after the differentiation grid.");
    Assert(storySource.Contains("Use this page to decide whether Chummer fits.", StringComparison.Ordinal), "product story should frame itself as a fit-and-differentiation page instead of a second action surface.");
    Assert(storySource.Contains("Need proof?", StringComparison.Ordinal), "product story should end with a quieter inline route note instead of a second hero-like CTA cluster.");
    Assert(storySource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "product story should reuse the shared signed-in trust panel instead of inventing a story-only trust surface.");
    Assert(storySource.Contains("_PublicTrustPulsePanel.cshtml", StringComparison.Ordinal), "product story should reuse the shared public trust pulse instead of duplicating weekly trust rows.");
    var nowSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml"));
    Assert(nowSource.Contains("_PublicStatusGlossary.cshtml", StringComparison.Ordinal), "now page should include the unified public status guide.");
    Assert(nowSource.Contains("Supporting proof around the core loop", StringComparison.Ordinal), "now should keep supporting proof behind a calmer secondary disclosure.");
    Assert(!nowSource.Contains("Integrity stays visible. Use downloads when you are ready to install", StringComparison.Ordinal), "now should not end with a second generic CTA band after the signed-in return callout.");
    Assert(!nowSource.Contains("static string DisplayStatus", StringComparison.Ordinal), "now should use the shared public status presenter instead of a local badge mapper.");
    Assert(!nowSource.Contains("story-guide-tail", StringComparison.Ordinal), "now should end with a quieter release footnote instead of a landing-style CTA band.");
    var shelfSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml"));
    Assert(shelfSource.Contains("_PublicStatusGlossary.cshtml", StringComparison.Ordinal), "artifact shelf should include the unified public status guide.");
    Assert(!shelfSource.Contains("static string DisplayStatus", StringComparison.Ordinal), "artifact shelf should use the shared public status presenter instead of a local badge mapper.");
    Assert(shelfSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "artifact shelf should reuse the shared signed-in trust panel instead of inventing a shelf-only trust surface.");
    Assert(shelfSource.Contains("_PublicTrustPulsePanel.cshtml", StringComparison.Ordinal), "artifact shelf should reuse the shared public trust pulse instead of duplicating weekly trust rows.");
    Assert(shelfSource.Contains("All views", StringComparison.Ordinal) && shelfSource.Contains("Personal view", StringComparison.Ordinal) && shelfSource.Contains("Campaign view", StringComparison.Ordinal) && shelfSource.Contains("Creator view", StringComparison.Ordinal), "artifact shelf should expose first-class signed-in shelf views instead of one blended overlay title.");
    Assert(shelfSource.Contains("@item.OwnershipSummary", StringComparison.Ordinal), "artifact shelf should surface signed-in artifact ownership posture directly from the shared recap shelf projection.");
    Assert(shelfSource.Contains("@item.ProvenanceSummary", StringComparison.Ordinal), "artifact shelf should surface signed-in artifact provenance directly from the shared recap shelf projection.");
    Assert(shelfSource.Contains("@item.AuditSummary", StringComparison.Ordinal), "artifact shelf should surface signed-in artifact audit posture directly from the shared recap shelf projection.");
    Assert(shelfSource.Contains("@linkedPublication.DiscoverySummary", StringComparison.Ordinal), "artifact shelf should surface linked creator-publication discovery posture on the signed-in shelf.");
    Assert(shelfSource.Contains("@linkedPublication.TrustSummary", StringComparison.Ordinal), "artifact shelf should surface linked creator-publication trust reasoning on the signed-in shelf.");
    Assert(shelfSource.Contains("@linkedPublication.ComparisonSummary", StringComparison.Ordinal), "artifact shelf should surface linked creator-publication comparison guidance on the signed-in shelf.");
    Assert(shelfSource.Contains("@linkedPublication.ModerationSummary", StringComparison.Ordinal), "artifact shelf should surface linked creator-publication moderation posture on the signed-in shelf.");
    Assert(shelfSource.Contains("@publication.TrustSummary", StringComparison.Ordinal), "artifact shelf should surface creator-publication trust reasoning directly on the signed-in creator cards.");
    Assert(shelfSource.Contains("@publication.ComparisonSummary", StringComparison.Ordinal), "artifact shelf should surface creator-publication comparison guidance directly on the signed-in creator cards.");
    Assert(shelfSource.Contains("@publication.ModerationSummary", StringComparison.Ordinal), "artifact shelf should surface creator-publication moderation posture directly on the signed-in creator cards.");
    Assert(shelfSource.Contains("Governed publication discovery", StringComparison.Ordinal), "artifact shelf should expose a first-class public publication-discovery section once shared publication is live.");
    Assert(shelfSource.Contains("Published shared publications", StringComparison.Ordinal), "artifact shelf should frame public publication discovery as a governed published shelf instead of creator-only teaser prose.");
    Assert(shelfSource.Contains("campaign, primer, dossier, recap, replay, and run-module outputs", StringComparison.Ordinal), "artifact shelf should describe primer outputs as part of the same governed shared-publication lane.");
    Assert(shelfSource.Contains("Compare at a glance", StringComparison.Ordinal), "artifact shelf should add a real compare-at-a-glance rail for public creator discovery instead of forcing card-by-card comparison.");
    Assert(shelfSource.Contains("How live publications differ", StringComparison.Ordinal), "artifact shelf should explain the public publication comparison lane in customer-facing terms.");
    Assert(shelfSource.Contains("CreatorPublicationTrustRank", StringComparison.Ordinal), "artifact shelf should order the public creator comparison lane with explicit governed trust posture instead of ad hoc card order.");
    Assert(shelfSource.Contains("rankedPublicCreatorPublications", StringComparison.Ordinal), "artifact shelf should build a ranked public creator comparison set before rendering the compare-at-a-glance lane.");
    Assert(shelfSource.Contains("HumanizeStatus(publication.PublicationStatus, \"Published\")", StringComparison.Ordinal), "artifact shelf should humanize publication state directly on the public creator-discovery cards.");
    Assert(shelfSource.Contains("Open public publication", StringComparison.Ordinal), "artifact shelf should keep a direct public inspect route on the governed publication cards.");
    Assert(shelfSource.Contains("/artifacts/publications/", StringComparison.Ordinal), "artifact shelf should deep-link public creator discovery into the shared public publication detail route.");
    Assert(shelfSource.Contains("HumanizeStatus(publication.Visibility, \"Shared\")", StringComparison.Ordinal), "artifact shelf should humanize creator-publication visibility directly on the signed-in shelf.");
    Assert(shelfSource.Contains("static bool IsDiscoverablePublicCreatorPublication", StringComparison.Ordinal), "artifact shelf should decide when a signed-in creator packet is already live enough to stay on the governed public inspect rail.");
    Assert(shelfSource.Contains("CreatorPublicationHref(linkedPublication, item.CreatorPublicationId)", StringComparison.Ordinal), "artifact shelf should route linked signed-in recap items through the public creator packet once publication is live.");
    Assert(shelfSource.Contains("CreatorPublicationHref(publication, publication.PublicationId)", StringComparison.Ordinal), "artifact shelf should route signed-in creator cards through the public creator packet once publication is live.");
    Assert(shelfSource.Contains("CreatorPublicationLinkLabel(linkedPublication)", StringComparison.Ordinal), "artifact shelf should label linked recap creator routes by live public versus private moderation posture.");
    Assert(shelfSource.Contains("CreatorPublicationLinkLabel(publication)", StringComparison.Ordinal), "artifact shelf should label signed-in creator-card routes by live public versus private moderation posture.");
    Assert(shelfSource.Contains("Open build path for @linkedPublication.Title", StringComparison.Ordinal), "artifact shelf should keep a direct route back to the linked creator-publication build path.");
    Assert(shelfSource.Contains("Open publication status", StringComparison.Ordinal), "artifact shelf should still preserve the private moderation route when a creator packet has not reached public discovery.");
    var publicCreatorSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "PublicCreatorPublication.cshtml"));
    Assert(publicCreatorSource.Contains("Why this publication is live", StringComparison.Ordinal), "public creator detail should explain the live governed publication posture on its own page.");
    Assert(publicCreatorSource.Contains("Publication kind", StringComparison.Ordinal), "public creator detail should surface the shared publication kind instead of collapsing into creator-only framing.");
    Assert(publicCreatorSource.Contains("Compare by", StringComparison.Ordinal), "public creator detail should surface creator-comparison guidance on the public inspect route.");
    Assert(publicCreatorSource.Contains("Back to publication discovery", StringComparison.Ordinal), "public publication detail should keep an explicit route back to the public discovery shelf.");
    Assert(publicCreatorSource.Contains("Public shared publication", StringComparison.Ordinal), "public publication detail should present the public route as a shared publication lane instead of a creator-only packet.");
    var campaignSpineServiceSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Services", "Community", "CampaignSpineService.cs"));
    Assert(campaignSpineServiceSource.Contains("return \"primer\";", StringComparison.Ordinal), "campaign spine service should normalize primer-like publication kinds onto a first-class shared-publication kind.");
    Assert(campaignSpineServiceSource.Contains("\"primer\" => $\"{workspace.CampaignName} campaign primer\"", StringComparison.Ordinal), "campaign spine service should give primer publications a first-class title instead of generic fallback labeling.");
    Assert(campaignSpineServiceSource.Contains("\"primer\" => \"Primer-safe onboarding, campaign continuity, and governed publication detail stay attached to one shared artifact lane.\"", StringComparison.Ordinal), "campaign spine service should give primer publications first-class shared-publication summary posture.");
    var horizonsSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Horizons.cshtml"));
    Assert(horizonsSource.Contains("_PublicStatusGlossary.cshtml", StringComparison.Ordinal), "horizons should include the unified public status guide.");
    Assert(horizonsSource.Contains("PublicSurfaceStatus.ResearchTrack", StringComparison.Ordinal), "roadmap should use the shared public status presenter for its visible maturity language.");
    Assert(horizonsSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "horizons should reuse the shared signed-in trust panel instead of inventing a roadmap-only trust surface.");
    Assert(horizonsSource.Contains("_PublicTrustPulsePanel.cshtml", StringComparison.Ordinal), "horizons should reuse the shared public trust pulse instead of duplicating weekly trust rows.");
    Assert(string.Equals(PublicSurfaceStatus.DisplayLabel("Inspectable"), PublicSurfaceStatus.AvailableToday, StringComparison.Ordinal), "inspectable proof should present as available-today proof on the public surface.");
    Assert(string.Equals(PublicSurfaceStatus.DisplayLabel("Preview"), PublicSurfaceStatus.PreviewInProgress, StringComparison.Ordinal), "preview artifact concepts should present as preview-in-progress on the public surface.");
    Assert(string.Equals(PublicSurfaceStatus.DisplayLabel("Designing"), PublicSurfaceStatus.DesigningInPublic, StringComparison.Ordinal), "designing horizons should present with the shared customer-facing roadmap label.");
    var runbookSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "scripts", "runbook.sh"));
    Assert(runbookSource.Contains("RUNBOOK_MODE=push bash \"$SCRIPT_DIR/runbook.sh\"", StringComparison.Ordinal), "hub-ship should force push mode explicitly instead of recursively inheriting RUNBOOK_MODE from the parent shell.");
    Assert(!runbookSource.Contains("bash \"$SCRIPT_DIR/runbook.sh\" push", StringComparison.Ordinal), "hub-ship should not recurse back into itself through an inherited RUNBOOK_MODE environment.");
    var homeSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml"));
    Assert(!homeSource.Contains("More in your signed-in shell", StringComparison.Ordinal), "home should not fall back to the old catch-all signed-in shell accordion.");
    Assert(!homeSource.Contains("Account state at a glance", StringComparison.Ordinal), "home should keep the overview route focused instead of adding a second top-level summary disclosure.");
    Assert(!homeSource.Contains("signed-in cockpit", StringComparison.Ordinal), "home access should avoid cockpit phrasing on the customer-facing route.");
    Assert(!homeSource.Contains("signed-in shell", StringComparison.Ordinal), "home should avoid signed-in shell wording on customer-facing routes.");
    Assert(!homeSource.Contains("Campaign workspace context", StringComparison.Ordinal), "home work should avoid internal campaign-workspace phrasing.");
    Assert(homeSource.Contains("grounded rule answers", StringComparison.OrdinalIgnoreCase), "home work should keep explicit grounded-rule evidence on the signed-in route.");
    Assert(homeSource.Contains("Open what works today", StringComparison.Ordinal), "home access should point proof needs to the dedicated now route instead of repeating proof cards inline.");
    Assert(homeSource.Contains("Need product proof before you install or return?", StringComparison.Ordinal), "home access should keep proof follow-through as a calmer note instead of a third equal-weight rail card.");
    Assert(!homeSource.Contains("Need product proof before you act?", StringComparison.Ordinal), "home access should not revive the louder proof rail copy.");
    Assert(homeSource.Contains("<summary>Release and device state</summary>", StringComparison.Ordinal), "home access should collapse secondary release and device detail under one calmer disclosure.");
    Assert(homeSource.Contains("showAccessSection && (!showOnboarding || accessSurfaceReady)", StringComparison.Ordinal), "home access should unlock when the account already has real device or support truth, even if the softer onboarding flag is still incomplete.");
    Assert(homeSource.Contains("Device roles", StringComparison.Ordinal), "home access should keep explicit device-role evidence on the signed-in route.");
    Assert(homeSource.Contains("GM-ready cues", StringComparison.Ordinal), "home work should use customer-facing continuity language instead of internal workspace wording.");
    Assert(homeSource.Contains("showWorkSection && (!showOnboarding || effectiveWorkSurfaceReady)", StringComparison.Ordinal), "home work should unlock when claimed install and return truth already exist, and also when starter lane can be seeded, instead of hiding the route behind a stale onboarding bit.");
    Assert(homeSource.Contains("seedStarterWorkspace", StringComparison.Ordinal), "home work should include starter-lane seeding on the empty workspace first-run path.");
    Assert(homeSource.Contains("/api/v1/campaign-spine/me/workspaces/starter", StringComparison.Ordinal), "home work should wire starter-lane seeding to the campaign-spine starter endpoint.");
    Assert(homeSource.Contains("Shared campaign view", StringComparison.Ordinal), "home work should surface the calmer shared campaign view card instead of hiding workspace return behind the deeper account route.");
    Assert(homeSource.Contains("Open shared campaign view", StringComparison.Ordinal), "home work should keep an explicit route back into the shared campaign view.");
    Assert(homeSource.Contains("/account/work/workspaces/", StringComparison.Ordinal), "home work should deep-link the shared campaign view instead of sending every route back to the generic work shell.");
    Assert(homeSource.Contains("@workspace.ActiveSceneSummary", StringComparison.Ordinal), "home work should surface active-scene change truth directly on the calmer shared campaign card.");
    Assert(homeSource.Contains("@workspace.NextSafeAction", StringComparison.Ordinal), "home work should surface the next safe action directly on the calmer shared campaign card.");
    Assert(homeSource.Contains("@workspace.FirstPlayableSession.CampaignStartSummary", StringComparison.Ordinal), "home work should surface first-session campaign-start proof directly on the calmer shared campaign card.");
    Assert(homeSource.Contains("@workspace.FirstPlayableSession.RuleReadySummary", StringComparison.Ordinal), "home work should surface legal-runner proof directly on the calmer shared campaign card.");
    Assert(homeSource.Contains("@workspace.FirstPlayableSession.CampaignReadySummary", StringComparison.Ordinal), "home work should surface campaign-ready proof directly on the calmer shared campaign card.");
    Assert(homeSource.Contains("What changed for me", StringComparison.Ordinal), "home work should keep the explicit what-changed-for-me packet on the signed-in route.");
    Assert(homeSource.Contains("leadWorkspaceState?.Label", StringComparison.Ordinal), "home work should surface the bounded workspace state directly from the server plane.");
    Assert(homeSource.Contains("var leadPortableExchangeNotice =", StringComparison.Ordinal), "home work should derive a dedicated portable-exchange notice from the bounded workspace server plane.");
    Assert(homeSource.Contains("Portable exchange:", StringComparison.Ordinal), "home work should surface portable exchange explicitly instead of hiding it inside a generic notice lane.");
    Assert(homeSource.Contains("Open first playable session proof", StringComparison.Ordinal), "home work should keep a direct route into the bounded first-session proof detail.");
    Assert(homeSource.Contains("@leadFirstPlayableSession.CampaignStartSummary", StringComparison.Ordinal), "home work should surface the first-session campaign-start summary directly from the server plane.");
    Assert(homeSource.Contains("@leadFirstPlayableSession.RuleReadySummary", StringComparison.Ordinal), "home work should surface legal-runner proof directly from the bounded first-session projection.");
    Assert(homeSource.Contains("@leadFirstPlayableSession.ReturnLaneSummary", StringComparison.Ordinal), "home work should surface understandable-return proof directly from the bounded first-session projection.");
    Assert(homeSource.Contains("@leadFirstPlayableSession.CampaignReadySummary", StringComparison.Ordinal), "home work should surface campaign-ready proof directly from the bounded first-session projection.");
    Assert(homeSource.Contains("Next-session carry-forward", StringComparison.Ordinal), "home work should surface a dedicated next-session carry-forward card backed by the shared workspace projection.");
    Assert(homeSource.Contains("@leadNextSessionCarryForward.Summary", StringComparison.Ordinal), "home work should surface the next-session carry-forward summary directly from the server plane.");
    Assert(homeSource.Contains("@leadNextSessionCarryForward.ReturnSummary", StringComparison.Ordinal), "home work should keep return-lane truth attached to the calmer next-session card.");
    Assert(homeSource.Contains("Campaign memory", StringComparison.Ordinal), "home work should surface a dedicated campaign-memory card instead of leaving long-lived follow-through spread across unrelated cards.");
    Assert(homeSource.Contains("@leadCampaignMemory.Summary", StringComparison.Ordinal), "home work should surface the shared campaign-memory summary directly from the server plane.");
    Assert(homeSource.Contains("@workspace.CampaignMemory.Summary", StringComparison.Ordinal), "home work should surface campaign memory directly on the calmer shared campaign card when it exists.");
    Assert(homeSource.Contains("Open campaign memory", StringComparison.Ordinal), "home work should keep a direct route into the bounded campaign-memory detail.");
    Assert(homeSource.Contains("@leadWorkspaceServerPlane.ChangePackets[0].Summary", StringComparison.Ordinal), "home work should surface the first server-plane change packet directly on the what-changed card.");
    Assert(homeSource.Contains("@leadWorkspaceServerPlane.NextSafeAction.Summary", StringComparison.Ordinal), "home work should surface the bounded next safe action directly on the what-changed card.");
    Assert(homeSource.Contains("@leadAftermathTag", StringComparison.Ordinal), "home work should label the lead aftermath card from package kind instead of hard-coding recap-only wording.");
    Assert(homeSource.Contains("@leadAftermathPackage.Title", StringComparison.Ordinal), "home work should surface the latest aftermath package title directly from the bounded server plane.");
    Assert(homeSource.Contains("@leadAftermathPackage.Summary", StringComparison.Ordinal), "home work should surface the latest aftermath package summary directly from the bounded server plane.");
    Assert(homeSource.Contains("@leadAftermathEvidence", StringComparison.Ordinal), "home work should surface one bounded aftermath evidence line on the signed-in home route.");
    Assert(homeSource.Contains("@leadAftermathRouteLabel", StringComparison.Ordinal), "home work should keep the lead aftermath route label aligned with replay or recap package kind.");
    Assert(homeSource.Contains("Replay timeline", StringComparison.Ordinal), "home work should expose replay-safe labeling once replay packages reach the same return rail.");
    Assert(homeSource.Contains("Downtime brief", StringComparison.Ordinal), "home work should surface a dedicated downtime brief card instead of leaving downtime follow-through buried inside the generic aftermath list.");
    Assert(homeSource.Contains("@leadDowntimePackage.Title", StringComparison.Ordinal), "home work should surface the latest downtime brief title directly from the bounded server plane.");
    Assert(homeSource.Contains("@leadDowntimeEvidence", StringComparison.Ordinal), "home work should surface one bounded downtime evidence line on the signed-in home route.");
    Assert(homeSource.Contains("Open downtime brief", StringComparison.Ordinal), "home work should keep a direct route into the downtime brief detail.");
    Assert(homeSource.Contains("PublicSurfaceStatus.AudienceLabel(leadAftermathShelfEntry.Audience)", StringComparison.Ordinal), "home work should humanize artifact shelf audience directly on the aftermath card.");
    Assert(homeSource.Contains("@leadAftermathShelfEntry.OwnershipSummary", StringComparison.Ordinal), "home work should surface artifact shelf ownership posture directly on the aftermath card.");
    Assert(homeSource.Contains("@leadAftermathShelfEntry.ProvenanceSummary", StringComparison.Ordinal), "home work should surface artifact shelf provenance directly on the aftermath card.");
    Assert(homeSource.Contains("@leadAftermathShelfEntry.AuditSummary", StringComparison.Ordinal), "home work should surface artifact shelf audit posture directly on the aftermath card.");
    Assert(homeSource.Contains("HumanizeStatus(leadAftermathShelfEntry.PublicationState, \"Ready\")", StringComparison.Ordinal), "home work should humanize artifact publication state directly on the aftermath card.");
    Assert(homeSource.Contains("HumanizeStatus(leadAftermathShelfEntry.TrustBand, \"Draft\")", StringComparison.Ordinal), "home work should humanize artifact trust ranking directly on the aftermath card.");
    Assert(homeSource.Contains("leadAftermathShelfEntry.Discoverable ? \"Eligible now\" : \"Still bounded\"", StringComparison.Ordinal), "home work should surface artifact discoverability posture directly on the aftermath card.");
    Assert(homeSource.Contains("@leadAftermathShelfEntry.PublicationSummary", StringComparison.Ordinal), "home work should surface artifact publication posture directly from the recap-shelf projection on the aftermath card.");
    Assert(homeSource.Contains("@leadAftermathCreatorPublication.LineageSummary", StringComparison.Ordinal), "home work should surface recap-shelf lineage by following the linked creator publication.");
    Assert(homeSource.Contains("@leadAftermathShelfEntry.NextSafeAction", StringComparison.Ordinal), "home work should surface the next artifact-shelf step directly from the recap-shelf projection on the aftermath card.");
    Assert(homeSource.Contains("CreatorPublicationHref(leadAftermathCreatorPublication, leadAftermathShelfEntry.CreatorPublicationId)", StringComparison.Ordinal), "home work should route linked aftermath publications onto the public creator packet when discovery is live, without losing the account fallback.");
    Assert(homeSource.Contains("Roster move", StringComparison.Ordinal), "home work should surface a dedicated roster-move card instead of collapsing operator actions into one-line campaign summaries.");
    Assert(homeSource.Contains("@leadRosterTransfer.RunnerHandle", StringComparison.Ordinal), "home work should surface the moved runner handle directly from the governed transfer receipt.");
    Assert(homeSource.Contains("Open governed roster moves", StringComparison.Ordinal), "home work should keep a direct route back to the governed roster-move operator rail.");
    Assert(homeSource.Contains("Operator posture", StringComparison.Ordinal), "home work should surface organizer/operator posture on the same signed-in route instead of burying it behind the deeper account panel.");
    Assert(homeSource.Contains("@leadCommunityOperation.GroupName", StringComparison.Ordinal), "home work should surface the lead governed operator group directly from the campaign spine.");
    Assert(homeSource.Contains("@leadCommunityOperation.OperationsSummary", StringComparison.Ordinal), "home work should surface the operator operations pulse directly on the calmer operator card.");
    Assert(homeSource.Contains("@leadCommunityOperation.CampaignReturnSummary", StringComparison.Ordinal), "home work should surface the operator campaign-return pulse directly on the calmer operator card.");
    Assert(homeSource.Contains("Season / event pulse", StringComparison.Ordinal), "home work should surface a first-class season and event pulse on the calmer operator card.");
    Assert(homeSource.Contains("@leadCommunityOperation.SeasonEventSummary", StringComparison.Ordinal), "home work should surface the operator season-event pulse directly from the shared projection.");
    Assert(homeSource.Contains("Latest event:", StringComparison.Ordinal), "home work should keep one bounded event receipt on the lead operator card.");
    Assert(homeSource.Contains("Board:", StringComparison.Ordinal), "home work should surface one bounded season-board entry on the lead operator card.");
    Assert(homeSource.Contains("@leadCommunityBoard.CampaignName", StringComparison.Ordinal), "home work should surface the lead season-board campaign directly from the shared operator projection.");
    Assert(homeSource.Contains("@leadCommunityBoard.RecapSummary", StringComparison.Ordinal), "home work should surface the lead season-board recap summary directly from the shared operator projection.");
    Assert(homeSource.Contains("@leadCommunityBoard.ConsequenceSummary", StringComparison.Ordinal), "home work should surface the lead season-board consequence summary directly from the shared operator projection.");
    Assert(homeSource.Contains("@leadCommunityBoard.CampaignMemorySummary", StringComparison.Ordinal), "home work should surface the lead season-board campaign-memory summary directly from the shared operator projection.");
    Assert(homeSource.Contains("@leadCommunityBoard.CampaignMemoryReturnSummary", StringComparison.Ordinal), "home work should surface the lead season-board campaign-memory return cue directly from the shared operator projection.");
    Assert(homeSource.Contains("League:", StringComparison.Ordinal), "home work should surface a bounded league-and-season operations summary on the lead operator card.");
    Assert(homeSource.Contains("@leadCommunityOperation.LeagueOperationsSummary", StringComparison.Ordinal), "home work should surface the shared league-operations summary directly from the operator projection.");
    Assert(homeSource.Contains("/account/work#community-op-league-", StringComparison.Ordinal), "home work should deep-link the operator card into the league-and-season operations rail.");
    Assert(homeSource.Contains("Open league rail", StringComparison.Ordinal), "home work should give operators a direct route to the league-and-season operations rail.");
    Assert(homeSource.Contains("/account/work#community-op-board-", StringComparison.Ordinal), "home work should deep-link the operator card into the exact season-board drawer instead of sending every organizer flow back to the generic operator shell.");
    Assert(homeSource.Contains("Open season board", StringComparison.Ordinal), "home work should keep a direct route back to the governed season board.");
    Assert(homeSource.Contains("Invites:", StringComparison.Ordinal), "home work should keep invite and sponsorship posture attached to the lead operator card.");
    Assert(homeSource.Contains("Sponsors:", StringComparison.Ordinal), "home work should keep a bounded sponsor-session pulse attached to the lead operator card.");
    Assert(homeSource.Contains("@leadCommunitySponsorSession.UserDisplayName", StringComparison.Ordinal), "home work should surface the lead sponsor-session participant directly from the shared operator projection.");
    Assert(homeSource.Contains("/account/work#community-op-invites-", StringComparison.Ordinal), "home work should deep-link the operator card into the invite and sponsorship rail.");
    Assert(homeSource.Contains("Open invite rail", StringComparison.Ordinal), "home work should give operators a direct route to the invite and sponsorship rail.");
    Assert(homeSource.Contains("/account/work#community-op-sponsor-sessions-", StringComparison.Ordinal), "home work should deep-link the operator card into the sponsor-session rail.");
    Assert(homeSource.Contains("Open sponsor rail", StringComparison.Ordinal), "home work should give operators a direct route to the sponsor-session rail.");
    Assert(homeSource.Contains("Guide: current preview, downloads, and closure posture stay on the same operator rail.", StringComparison.Ordinal), "home work should keep bounded organizer guidance attached to the lead operator card.");
    Assert(homeSource.Contains("Model.SignedInStatus", StringComparison.Ordinal), "signed-in home should project the shared signed-in trust panel instead of keeping trust posture trapped on account-only routes.");
    Assert(homeSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "signed-in home should reuse the shared signed-in trust panel instead of inventing a home-only trust surface.");
    Assert(homeSource.Contains("TrustRowValue(Model.SignedInStatus, \"Who can get it now\"", StringComparison.Ordinal), "home operator guidance should reuse the signed-in trust posture for current access guidance.");
    Assert(homeSource.Contains("TrustRowValue(Model.SignedInStatus, \"Fix availability\"", StringComparison.Ordinal), "home operator guidance should reuse the signed-in trust posture for fix guidance.");
    Assert(homeSource.Contains("TrustRowValue(Model.SignedInStatus, \"Current caution\"", StringComparison.Ordinal), "home operator guidance should reuse the signed-in trust posture for the caution lane.");
    Assert(homeSource.Contains("/account/work#community-op-guidance-", StringComparison.Ordinal), "home work should deep-link the operator card into the organizer guidance rail.");
    Assert(homeSource.Contains("Open member guidance", StringComparison.Ordinal), "home work should give operators a direct route to the member-guidance rail.");
    Assert(homeSource.Contains("Consequence watch", StringComparison.Ordinal), "home work should surface a dedicated consequence card instead of leaving consequence follow-through buried inside summary text.");
    Assert(homeSource.Contains("@leadConsequence.Label", StringComparison.Ordinal), "home work should surface the lead governed consequence directly from the workspace server plane.");
    Assert(homeSource.Contains("@leadConsequenceEvidence", StringComparison.Ordinal), "home work should surface one bounded consequence evidence line on the calmer home card.");
    Assert(homeSource.Contains("Consequence:", StringComparison.Ordinal), "home work should surface one short consequence cue directly on the shared campaign card.");
    Assert(homeSource.Contains("Build path", StringComparison.Ordinal), "home work should surface a clear build-path follow-through card instead of only roadmap copy.");
    Assert(homeSource.Contains("Grounded rule answer", StringComparison.Ordinal), "home work should surface a grounded rule-answer card instead of hiding explain value behind account-only routes.");
    Assert(homeSource.Contains("Evidence:", StringComparison.Ordinal), "home work should surface the first grounded rule evidence line instead of only a generic provenance label.");
    Assert(homeSource.Contains("@leadPrepLaunch.PacketTitle", StringComparison.Ordinal), "home work should surface the latest governed prep launch directly on the calmer prep card.");
    Assert(homeSource.Contains("@leadTravelPrefetch.DeviceRole", StringComparison.Ordinal), "home work should surface the latest staged travel-prefetch receipt directly on the calmer prep card.");
    Assert(homeSource.Contains("@handoff.CampaignReturnSummary", StringComparison.Ordinal), "home work should surface build-path return truth directly on the calmer home card.");
    Assert(homeSource.Contains("@handoff.PlannerCoverageSummary", StringComparison.Ordinal), "home work should surface build-path planner coverage directly on the calmer home card.");
    Assert(homeSource.Contains("@handoff.SupportClosureSummary", StringComparison.Ordinal), "home work should surface build-path support closure truth directly on the calmer home card.");
    Assert(homeSource.Contains("Open build path for @handoff.Title", StringComparison.Ordinal), "home work should keep the build handoff deep link specific to the visible build path instead of a generic CTA.");
    Assert(homeSource.Contains("@answer.SupportReuseHints[0]", StringComparison.Ordinal), "home work should surface grounded support-reuse hints directly from the shared rules projection.");
    Assert(homeSource.Contains("Next:", StringComparison.Ordinal), "home work should keep a short next-step cue on the calmer build follow-through card.");
    Assert(homeSource.Contains("<summary>Build, explain, and next step</summary>", StringComparison.Ordinal), "home work should collapse the secondary build and rules follow-through under one calmer disclosure.");
    Assert(homeSource.Contains("/account/work/build-handoffs/", StringComparison.Ordinal), "home work should deep-link build follow-through into the signed-in work detail route.");
    Assert(homeSource.Contains("/account/work/rules/", StringComparison.Ordinal), "home work should deep-link grounded rule answers into the signed-in work detail route.");
    Assert(homeSource.Contains("Migration return", StringComparison.Ordinal), "home work should surface migration return instead of leaving legacy carry-forward buried in the deeper work route.");
    Assert(homeSource.Contains("Open migration return", StringComparison.Ordinal), "home work should keep a direct route back into migration return.");
    Assert(homeSource.Contains("Publication status", StringComparison.Ordinal), "home work should surface creator-publication status instead of leaving publication trust buried in the deeper account route.");
    Assert(homeSource.Contains("@publication.ProvenanceSummary", StringComparison.Ordinal), "home work should surface creator-publication provenance directly from the shared projection.");
    Assert(homeSource.Contains("HumanizeStatus(publication.Visibility, \"Shared\")", StringComparison.Ordinal), "home work should humanize creator-publication visibility directly on the signed-in home route.");
    Assert(homeSource.Contains("@publication.DiscoverySummary", StringComparison.Ordinal), "home work should surface creator-publication discovery posture directly from the shared projection.");
    Assert(homeSource.Contains("@publication.TrustSummary", StringComparison.Ordinal), "home work should surface creator-publication trust reasoning directly from the shared projection.");
    Assert(homeSource.Contains("@publication.ComparisonSummary", StringComparison.Ordinal), "home work should surface creator-publication comparison guidance directly from the shared projection.");
    Assert(homeSource.Contains("@publication.ModerationSummary", StringComparison.Ordinal), "home work should surface creator-publication moderation posture directly from the shared projection.");
    Assert(homeSource.Contains("@publication.LineageSummary", StringComparison.Ordinal), "home work should surface creator-publication lineage directly from the shared projection.");
    Assert(homeSource.Contains("HumanizeStatus(publication.TrustBand, \"Draft\")", StringComparison.Ordinal), "home work should humanize creator-publication trust ranking directly on the signed-in home route.");
    Assert(homeSource.Contains("publication.Discoverable ? \"Eligible now\" : \"Still bounded\"", StringComparison.Ordinal), "home work should surface creator-publication discoverability posture directly on the signed-in home route.");
    Assert(homeSource.Contains("HumanizeStatus(publication.PublicationStatus, \"Published\")", StringComparison.Ordinal), "home work should humanize creator-publication state directly on the signed-in home route.");
    Assert(homeSource.Contains("@publication.NextSafeAction", StringComparison.Ordinal), "home work should surface the publication next step directly from the shared creator-publication projection.");
    Assert(homeSource.Contains("@publication.CampaignReturnSummary", StringComparison.Ordinal), "home work should surface creator-publication return truth directly from the shared projection.");
    Assert(homeSource.Contains("@publication.SupportClosureSummary", StringComparison.Ordinal), "home work should surface creator-publication support closure directly from the shared projection.");
    Assert(homeSource.Contains("@leadAftermathCreatorPublication.DiscoverySummary", StringComparison.Ordinal), "home aftermath shelf should surface linked creator-publication discovery posture instead of compressing recap output back to trust-only prose.");
    Assert(homeSource.Contains("@leadAftermathCreatorPublication.TrustSummary", StringComparison.Ordinal), "home aftermath shelf should surface linked creator-publication trust reasoning instead of collapsing it into trust-band shorthand.");
    Assert(homeSource.Contains("@leadAftermathCreatorPublication.ComparisonSummary", StringComparison.Ordinal), "home aftermath shelf should surface linked creator-publication comparison guidance instead of burying it in the detail route.");
    Assert(homeSource.Contains("@leadAftermathCreatorPublication.ModerationSummary", StringComparison.Ordinal), "home aftermath shelf should surface linked creator-publication moderation posture instead of dropping it outside the publication route.");
    Assert(homeSource.Contains("HumanizeStatus(leadAftermathCreatorPublication.Visibility, \"Shared\")", StringComparison.Ordinal), "home aftermath shelf should humanize linked creator-publication visibility instead of hiding it behind the detail card.");
    Assert(homeSource.Contains("@leadAftermathCreatorPublication.CampaignReturnSummary", StringComparison.Ordinal), "home aftermath shelf should surface linked creator-publication return truth instead of dropping it outside the publication detail route.");
    Assert(homeSource.Contains("@leadAftermathCreatorPublication.SupportClosureSummary", StringComparison.Ordinal), "home aftermath shelf should surface linked creator-publication support closure instead of dropping it outside the publication detail route.");
    Assert(homeSource.Contains("Open public publication", StringComparison.Ordinal), "home work should keep a direct route into the public publication once discovery is live.");
    Assert(homeSource.Contains("Open build path for @publication.Title", StringComparison.Ordinal), "home work should keep a title-specific route from publication status back into the related build follow-through.");
    Assert(homeSource.Contains("Open build path for @leadAftermathCreatorPublication.Title", StringComparison.Ordinal), "home aftermath shelf should keep a direct route back to the linked creator-publication build path.");
    Assert(homeSource.Contains("/artifacts/publications/", StringComparison.Ordinal), "home work should deep-link discoverable creator packets into the shared public publication detail route.");
    Assert(homeSource.Contains("Understandable return: @workspace.FirstPlayableSession.ReturnLaneSummary", StringComparison.Ordinal), "home work should surface understandable-return proof directly on the shared campaign card instead of compressing it away.");
    Assert(homeSource.Contains("Legal runner: @leadFirstPlayableSession.RuleReadySummary", StringComparison.Ordinal), "home work should carry legal-runner proof onto the calmer lead first-session card.");
    Assert(homeSource.Contains("Understandable return: @leadFirstPlayableSession.ReturnLaneSummary", StringComparison.Ordinal), "home work should carry understandable-return proof onto the calmer lead first-session card.");
    Assert(homeSource.Contains("Campaign-ready lane: @leadFirstPlayableSession.CampaignReadySummary", StringComparison.Ordinal), "home work should carry campaign-ready proof onto the calmer lead first-session card.");
    Assert(homeSource.Contains("Device return", StringComparison.Ordinal), "home work should surface the calmer device-return card for claimed-device continuity.");
    Assert(homeSource.Contains("Open device return", StringComparison.Ordinal), "home work should keep a direct route into the device-return lane when claimed-device continuity already exists.");
    Assert(homeSource.Contains("@supportCase.ClosureSummary", StringComparison.Ordinal), "home access should surface support-closure truth directly from the shared support presenter.");
    Assert(homeSource.Contains("@supportCase.ReleaseProgressSummary", StringComparison.Ordinal), "home access should surface release-progress truth directly from the shared support presenter.");
    Assert(homeSource.Contains("@supportCase.AffectedInstallSummary", StringComparison.Ordinal), "home access should surface affected-install truth directly from the shared support presenter.");
    Assert(homeSource.Contains("Watchout:", StringComparison.Ordinal), "home work should keep one concrete watchout instead of a long data-dump summary.");
    Assert(homeSource.Contains("Transfer:", StringComparison.Ordinal), "home work should surface a short roster-transfer cue when campaign ownership or roster placement changes.");
    Assert(!homeSource.Contains("Next safe action:", StringComparison.Ordinal), "home work should not fall back to the older verbose next-safe-action label on the short card.");
    Assert(!homeSource.Contains("Support reuse:", StringComparison.Ordinal), "home work should keep support reuse detail in the deeper work route instead of the short home card.");
    Assert(!homeSource.Contains("story-guide-tail", StringComparison.Ordinal), "home should use quieter release-footnote sections instead of the older full-width CTA band.");
    var accountSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "Accounts", "Account.cshtml"));
    Assert(!accountSource.Contains("Build Lab handoffs", StringComparison.Ordinal), "account copy should avoid internal Build Lab wording on the customer-facing surface.");
    Assert(!accountSource.Contains("Rules Navigator answers", StringComparison.Ordinal), "account copy should avoid internal Rules Navigator wording on the customer-facing surface.");
    Assert(accountSource.Contains("Build paths", StringComparison.Ordinal), "account should describe Build Lab follow-through as customer-facing build paths.");
    Assert(accountSource.Contains("Grounded rule answers", StringComparison.Ordinal), "account should describe Rules Navigator follow-through as grounded rule answers.");
    Assert(accountSource.Contains("Model.SignedInTrustStatus", StringComparison.Ordinal), "account should project the signed-in trust panel directly on the account surface.");
    Assert(accountSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "account should reuse the shared signed-in trust panel instead of a link-only trust rail.");
    Assert(accountSource.Contains("Signed-in trust snapshot", StringComparison.Ordinal), "account teams and permissions should give organizers a bounded signed-in trust snapshot on the member-guidance rail.");
    Assert(accountSource.Contains("TrustRowValue(Model.SignedInTrustStatus, \"Who can get it now\"", StringComparison.Ordinal), "account member guidance should reuse the signed-in trust posture for current access guidance.");
    Assert(accountSource.Contains("TrustRowValue(Model.SignedInTrustStatus, \"Recommended for this install\"", StringComparison.Ordinal), "account member guidance should reuse the signed-in trust posture for the promoted install path.");
    Assert(accountSource.Contains("TrustRowValue(Model.SignedInTrustStatus, \"Release proof\"", StringComparison.Ordinal), "account member guidance should reuse the signed-in trust posture for current proof.");
    Assert(accountSource.Contains("TrustRowValue(Model.SignedInTrustStatus, \"Current caution\"", StringComparison.Ordinal), "account member guidance should reuse the signed-in trust posture for the caution lane.");
    Assert(accountSource.Contains("#signed-in-trust-status", StringComparison.Ordinal), "account member guidance should deep-link back to the shared signed-in trust panel instead of inventing a second trust page.");
    Assert(accountSource.Contains("Start first playable session", StringComparison.Ordinal), "account work should offer starter-lane follow-through when the shared campaign view is still empty.");
    Assert(accountSource.Contains("seedStarterWorkspaceFromAccount", StringComparison.Ordinal), "account work should wire the starter-lane button on the empty-state route.");
    Assert(accountSource.Contains("starterWorkspaceAccountNotice", StringComparison.Ordinal), "account work should surface starter-lane feedback on the empty-state route.");
    Assert(accountSource.Contains("/api/v1/campaign-spine/me/workspaces/starter", StringComparison.Ordinal), "account work should reuse the campaign-spine starter endpoint instead of inventing a second onboarding API.");
    Assert(accountSource.Contains("selected-first-playable-session", StringComparison.Ordinal), "account work should keep a bounded first-session proof drawer on the selected shared campaign view.");
    Assert(accountSource.Contains("selectedWorkspaceFirstPlayableSession.CampaignStartSummary", StringComparison.Ordinal), "account work should surface first-session campaign-start proof directly on the selected shared campaign view.");
    Assert(accountSource.Contains("selectedWorkspaceFirstPlayableSession.RuleReadySummary", StringComparison.Ordinal), "account work should surface legal-runner proof directly on the selected shared campaign view.");
    Assert(accountSource.Contains("selectedWorkspaceFirstPlayableSession.ReturnLaneSummary", StringComparison.Ordinal), "account work should surface understandable-return proof directly on the selected shared campaign view.");
    Assert(accountSource.Contains("selectedWorkspaceFirstPlayableSession.CampaignReadySummary", StringComparison.Ordinal), "account work should surface campaign-ready proof directly on the selected shared campaign view.");
    Assert(accountSource.Contains("<p><strong>Legal runner:</strong> @selectedWorkspaceFirstPlayableSession.RuleReadySummary</p>", StringComparison.Ordinal), "account work should carry legal-runner proof into the selected-workspace summary copy.");
    Assert(accountSource.Contains("<p><strong>Understandable return:</strong> @selectedWorkspaceFirstPlayableSession.ReturnLaneSummary</p>", StringComparison.Ordinal), "account work should carry understandable-return proof into the selected-workspace summary copy.");
    Assert(accountSource.Contains("<p><strong>Campaign-ready lane:</strong> @selectedWorkspaceFirstPlayableSession.CampaignReadySummary</p>", StringComparison.Ordinal), "account work should carry campaign-ready proof into the selected-workspace summary copy.");
    Assert(accountSource.Contains("TrustRowValue(Model.SignedInTrustStatus, \"Fix availability\"", StringComparison.Ordinal), "account work should reuse signed-in fix-availability truth inside the selected first-session drawer.");
    Assert(accountSource.Contains("TrustRowValue(Model.SignedInTrustStatus, \"Current caution\"", StringComparison.Ordinal), "account work should reuse signed-in caution truth inside the selected first-session drawer.");
    Assert(accountSource.Contains("Open install support", StringComparison.Ordinal), "account work should keep install-support follow-through inside the selected first-session drawer.");
    Assert(accountSource.Contains("@workspace.FirstPlayableSession.RuleReadySummary", StringComparison.Ordinal), "account work should surface legal-runner proof directly on the broader shared campaign list.");
    Assert(accountSource.Contains("@workspace.FirstPlayableSession.ReturnLaneSummary", StringComparison.Ordinal), "account work should surface understandable-return proof directly on the broader shared campaign list.");
    Assert(accountSource.Contains("@workspace.FirstPlayableSession.CampaignReadySummary", StringComparison.Ordinal), "account work should surface campaign-ready proof directly on the broader shared campaign list.");
    Assert(accountSource.Contains("Understandable return", StringComparison.Ordinal), "account work should label first-session return proof in customer-facing onboarding language.");
    Assert(!accountSource.Contains("Workspaces and continuity", StringComparison.Ordinal), "account should avoid workspace-heavy section titles on the customer-facing route.");
    Assert(!accountSource.Contains("Campaign continuity, work-return surfaces, and team posture", StringComparison.Ordinal), "account work copy should avoid internal continuity posture phrasing.");
    Assert(!accountSource.Contains("Advanced continuity and restore", StringComparison.Ordinal), "account access should avoid internal restore drawer wording.");
    Assert(!accountSource.Contains("Claimed second-device restore posture", StringComparison.Ordinal), "account access should avoid internal second-device restore jargon.");
    Assert(!accountSource.Contains("signed-in shell", StringComparison.Ordinal), "account should avoid signed-in shell wording on customer-facing surfaces.");
    Assert(!accountSource.Contains("Campaign workspaces", StringComparison.Ordinal), "account work summary should describe shared campaign views in customer-facing language.");
    Assert(accountSource.Contains("\"work\" => \"Work\"", StringComparison.Ordinal), "account should use the calmer work section heading.");
    Assert(accountSource.Contains("Advanced device recovery", StringComparison.Ordinal), "account access should use customer-facing recovery wording for advanced device details.");
    Assert(accountSource.Contains("Offline-ready return", StringComparison.Ordinal), "account access should describe claimed-device restore details in customer-facing offline-return wording.");
    Assert(accountSource.Contains("Roster transfer audit", StringComparison.Ordinal), "account work should expose explicit roster-transfer audit language on shared campaign views.");
    Assert(accountSource.Contains("Move governed roster state", StringComparison.Ordinal), "account work should expose a real roster-transfer action instead of only historical audit receipts.");
    Assert(accountSource.Contains("Recent governed roster moves", StringComparison.Ordinal), "account work should keep recent roster moves visible on the operator rail after ownership changes.");
    Assert(accountSource.Contains("Artifact shelf posture", StringComparison.Ordinal), "account work should give the selected campaign card a first-class artifact shelf posture drawer.");
    Assert(accountSource.Contains("PublicSurfaceStatus.AudienceLabel(item.Audience)", StringComparison.Ordinal), "account work should humanize artifact shelf audiences directly on the selected campaign card.");
    Assert(accountSource.Contains("@item.OwnershipSummary", StringComparison.Ordinal), "account work should surface artifact ownership posture directly from the shared recap-shelf projection.");
    Assert(accountSource.Contains("@item.ProvenanceSummary", StringComparison.Ordinal), "account work should surface artifact provenance directly from the shared recap-shelf projection.");
    Assert(accountSource.Contains("@item.AuditSummary", StringComparison.Ordinal), "account work should surface artifact audit posture directly from the shared recap-shelf projection.");
    Assert(accountSource.Contains("@HumanizeStatus(item.PublicationState, \"Ready\")", StringComparison.Ordinal), "account work should surface artifact publication state directly from the shared recap-shelf projection.");
    Assert(accountSource.Contains("@item.PublicationSummary", StringComparison.Ordinal), "account work should surface artifact publication posture directly from the shared recap-shelf projection.");
    Assert(accountSource.Contains("@item.NextSafeAction", StringComparison.Ordinal), "account work should surface the next artifact-shelf step directly from the shared recap-shelf projection.");
    Assert(accountSource.Contains("item.CreatorPublicationId", StringComparison.Ordinal), "account work should deep-link artifact shelf entries back into creator publication status when the same truth is already published.");
    Assert(accountSource.Contains("PublicCreatorPublicationHref", StringComparison.Ordinal), "account work should expose a direct public creator-packet route once the owner is looking at a live discoverable publication.");
    Assert(accountSource.Contains("IsDiscoverablePublicCreatorPublication", StringComparison.Ordinal), "account work should gate the public creator-packet route on actual live discoverable publication posture.");
    Assert(accountSource.Contains("Transfer governed roster state", StringComparison.Ordinal), "account work should give operators a direct governed roster-transfer action.");
    Assert(accountSource.Contains("Launch governed prep packet", StringComparison.Ordinal), "account work should expose a real governed prep-launch action on the selected campaign card.");
    Assert(accountSource.Contains("Recent governed prep launches", StringComparison.Ordinal), "account work should keep recent governed prep-launch receipts visible on the selected campaign card.");
    Assert(accountSource.Contains("Stage travel prefetch", StringComparison.Ordinal), "account work should expose a real claimed-device travel-prefetch action on the selected campaign card.");
    Assert(accountSource.Contains("Recent travel prefetch receipts", StringComparison.Ordinal), "account work should keep staged travel-prefetch receipts visible on the selected campaign card.");
    Assert(accountSource.Contains("Generate aftermath or replay package", StringComparison.Ordinal), "account work should expose a real aftermath or replay packaging action on the selected campaign card.");
    Assert(accountSource.Contains("Recent aftermath and replay packages", StringComparison.Ordinal), "account work should keep generated aftermath and replay packages visible on the selected campaign card.");
    Assert(accountSource.Contains("<option value=\"replay_timeline\">Replay timeline</option>", StringComparison.Ordinal), "account work should let operators generate replay timelines from the same governed package rail.");
    Assert(shelfSource.Contains("aftermath or replay follow-through", StringComparison.Ordinal), "signed-in artifact shelf should describe the campaign lane with replay-safe follow-through instead of recap-only wording.");
    Assert(shelfSource.Contains("live aftermath, replay, and linked creator-publication record", StringComparison.Ordinal), "signed-in artifact shelf should describe the all-views lane with replay-safe outputs instead of recap-only wording.");
    var downloadDispatchSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml"));
    var supportSubmittedSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml"));
    Assert(!downloadDispatchSource.Contains("canonical", StringComparison.OrdinalIgnoreCase), "download handoff should avoid canonical jargon on the customer-facing surface.");
    Assert(!downloadDispatchSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "download handoff should stay focused on install handoff controls instead of duplicating the broader signed-in trust panel.");
    Assert(downloadDispatchSource.Contains("Current release", StringComparison.Ordinal), "download handoff should still expose current release posture directly on the handoff card.");
    Assert(downloadDispatchSource.Contains("Automatic account linking is the default path.", StringComparison.Ordinal), "download handoff should explicitly keep automatic linking as the default and reserve claim codes for recovery fallback.");
    Assert(downloadDispatchSource.Contains("Support follow-through stays on the same install rail", StringComparison.Ordinal), "download handoff should keep support recovery on the same install rail instead of splitting it into a separate browser ritual.");
    Assert(!supportSubmittedSource.Contains("signed-in shell", StringComparison.Ordinal), "support confirmation should avoid signed-in shell wording.");
    Assert(supportSubmittedSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "support confirmation should reuse the shared signed-in trust panel instead of inventing a confirmation-only trust surface.");
    Assert(supportSubmittedSource.Contains("_PublicTrustPulsePanel.cshtml", StringComparison.Ordinal), "support confirmation should reuse the shared public trust pulse instead of duplicating weekly trust rows.");
    Assert(supportSubmittedSource.Contains("TrustRowValue(Model.SignedInStatus, \"Who can get it now\"", StringComparison.Ordinal), "support confirmation should surface who-can-get-it-now posture directly on the confirmation rail.");
    Assert(supportSubmittedSource.Contains("@Model.TrackedCaseSummary.InstallReadinessSummary", StringComparison.Ordinal), "support confirmation should surface the linked-install readiness summary directly from the tracked case.");
    Assert(supportSubmittedSource.Contains("@Model.TrackedCaseSummary.VerificationSummary", StringComparison.Ordinal), "support confirmation should surface fix-verification guidance directly from the tracked case.");
    Assert(supportSubmittedSource.Contains("@Model.TrackedCaseSummary.ReleaseProgressSummary", StringComparison.Ordinal), "support confirmation should surface the release-lane summary directly from the tracked case.");
    Assert(accountSource.Contains("Recent install handoffs", StringComparison.Ordinal), "account access should describe recent downloads as install handoffs instead of raw receipts.");
    Assert(accountSource.Contains("Current install rail", StringComparison.Ordinal), "account access should lead with one current install rail instead of only counts and fallback ledgers.");
    Assert(accountSource.Contains("Recovery codes stay below as a fallback, not the first instruction.", StringComparison.Ordinal), "account access should explicitly demote recovery codes beneath the primary install rail guidance.");
    Assert(accountSource.Contains("This linked install is your default return rail", StringComparison.Ordinal), "account access should present the linked install as the default return rail when claim and support continuity already exist.");
    Assert(accountSource.Contains("Finish on another device", StringComparison.Ordinal), "account access should describe pending claim codes as the remaining device handoff step.");
    Assert(accountSource.Contains("Recovery mode only", StringComparison.Ordinal), "account access should mark pending claim codes as recovery-only fallback instead of the primary install path.");
    Assert(accountSource.Contains("Do not redeem claim codes in a browser tab.", StringComparison.Ordinal), "account access should steer claim-code use back into in-app recovery instead of browser ritual.");
    Assert(accountSource.Contains("Entitlement sync receipts", StringComparison.Ordinal), "account access should expose a dedicated entitlement-sync receipt drawer instead of leaving recovery posture buried in the API.");
    Assert(accountSource.Contains("@entitlementSyncReceipts.ReceiptStatus.RecoverySummary", StringComparison.Ordinal), "account access should render the entitlement-sync recovery summary instead of hiding it behind raw counts.");
    Assert(accountSource.Contains("DescribeRecoveryRouteAction(entitlementSyncReceipts.ReceiptStatus.RecoveryRoute)", StringComparison.Ordinal), "account access should render a direct recovery action for the standalone entitlement-sync lead receipt.");
    Assert(accountSource.Contains("@entitlementSyncReceipts.ReceiptStatus.LatestReceiptObservedAtUtc.UtcDateTime.ToString(\"u\")", StringComparison.Ordinal), "account access should surface the latest entitlement-sync receipt observation timestamp.");
    Assert(accountSource.Contains("Continue is blocked until this receipt is resolved.", StringComparison.Ordinal), "account access should make blocking entitlement-sync conflicts explicit on the device surface.");
    Assert(accountSource.Contains("Restore provenance receipts", StringComparison.Ordinal), "account work should keep restore provenance receipt counts visible on the selected workspace card.");
    Assert(accountSource.Contains("Restore conflict receipts", StringComparison.Ordinal), "account work should keep restore conflict receipt counts visible on the selected workspace card.");
    Assert(accountSource.Contains("Restore receipt posture", StringComparison.Ordinal), "account work should surface one restore receipt posture summary on the selected workspace card.");
    Assert(accountSource.Contains("Restore receipt status", StringComparison.Ordinal), "account work should render a restore receipt status summary in the dedicated restore drawer.");
    Assert(accountSource.Contains("@selectedWorkspaceServerPlane.RestoreReceiptStatus.RecoverySummary", StringComparison.Ordinal), "account work should render the restore receipt recovery summary instead of leaving recoverability implicit.");
    Assert(accountSource.Contains("DescribeRecoveryRouteAction(selectedWorkspaceServerPlane.RestoreReceiptStatus.RecoveryRoute)", StringComparison.Ordinal), "account work should expose a direct recovery-route action for the lead restore receipt instead of leaving the route as inert text.");
    Assert(accountSource.Contains("Restore provenance and conflict receipts", StringComparison.Ordinal), "account work should expose a dedicated restore provenance/conflict receipt drawer on the selected workspace card.");
    Assert(accountSource.Contains("Authority: @HumanizeStatus(receipt.Authority, \"hub\")", StringComparison.Ordinal), "account work should render restore receipt authority instead of hiding which plane issued the continuity proof.");
    Assert(accountSource.Contains("@receipt.RecoveryHint", StringComparison.Ordinal), "account work should render the concrete restore recovery hint on provenance receipts.");
    Assert(accountSource.Contains("DescribeRecoveryRouteAction(recovery.RecoveryRoute)", StringComparison.Ordinal), "account work should render a direct recovery action for each provenance recovery receipt.");
    Assert(accountSource.Contains("DescribeRecoveryRouteAction(receipt.RecoveryRoute)", StringComparison.Ordinal), "account work should render a direct recovery action for each conflict receipt.");
    Assert(accountSource.Contains("Continue is blocked until this receipt is resolved.", StringComparison.Ordinal), "account work should render the blocking-state copy for restore conflict receipts.");
    Assert(accountSource.Contains("Outcome:", StringComparison.Ordinal), "account build-path details should surface the next progression outcome rather than only the variant headline.");
    Assert(accountSource.Contains("Closure:", StringComparison.Ordinal), "account build-path details should surface support-closure truth instead of leaving the new rail data unused.");
    Assert(accountSource.Contains("Planner coverage", StringComparison.Ordinal), "account build-path details should surface planner-coverage truth instead of leaving follow-through grounding implicit.");
    Assert(accountSource.Contains("@selectedBuildLabHandoff.CampaignReturnSummary", StringComparison.Ordinal), "account build-path detail should surface build-handoff return truth directly from the shared projection.");
    Assert(accountSource.Contains("@selectedBuildLabHandoff.SupportClosureSummary", StringComparison.Ordinal), "account build-path detail should surface build-handoff support closure directly from the shared projection.");
    Assert(accountSource.Contains("@selectedBuildLabHandoff.PlannerCoverageSummary", StringComparison.Ordinal), "account build-path detail should surface planner-coverage summary directly from the shared projection.");
    Assert(accountSource.Contains("selectedBuildLabHandoff.PlannerCoverageLines", StringComparison.Ordinal), "account build-path detail should render planner-coverage lines directly from the shared projection.");
    Assert(accountSource.Contains("selectedBuildLabHandoff.ProgressionOutcomes", StringComparison.Ordinal), "account build-path detail should render progression outcomes directly from the shared projection.");
    Assert(accountSource.Contains("selectedBuildLabHandoff.Outputs.Take(3)", StringComparison.Ordinal), "account build-path detail should render bounded per-output rows so template/foundry/sheet follow-through stays visible.");
    Assert(accountSource.Contains("@output.NextSafeAction", StringComparison.Ordinal), "account build-path detail should surface per-output next-safe actions directly from the shared projection.");
    Assert(accountSource.Contains("@output.ProvenanceSummary", StringComparison.Ordinal), "account build-path detail should surface per-output provenance summaries directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.ProvenanceSummary", StringComparison.Ordinal), "account publication detail should surface creator-publication provenance directly from the shared projection.");
    Assert(accountSource.Contains("HumanizeStatus(selectedCreatorPublication.Visibility, \"Shared\")", StringComparison.Ordinal), "account publication detail should humanize creator-publication visibility directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.LineageSummary", StringComparison.Ordinal), "account publication detail should surface creator-publication lineage directly from the shared projection.");
    Assert(accountSource.Contains("HumanizeStatus(selectedCreatorPublication.TrustBand, \"Draft\")", StringComparison.Ordinal), "account publication detail should humanize creator-publication trust ranking directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.TrustSummary", StringComparison.Ordinal), "account publication detail should surface creator-publication trust reasoning directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.ComparisonSummary", StringComparison.Ordinal), "account publication detail should surface creator-publication comparison guidance directly from the shared projection.");
    Assert(accountSource.Contains("selectedCreatorPublication.Discoverable ? \"Eligible now\" : \"Still bounded\"", StringComparison.Ordinal), "account publication detail should surface creator-publication discoverability posture directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.NextSafeAction", StringComparison.Ordinal), "account publication detail should surface the next creator-publication step directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.CampaignReturnSummary", StringComparison.Ordinal), "account publication detail should surface creator-publication return truth directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.SupportClosureSummary", StringComparison.Ordinal), "account publication detail should surface creator-publication support closure directly from the shared projection.");
    Assert(accountSource.Contains("@selectedCreatorPublication.ModerationSummary", StringComparison.Ordinal), "account publication detail should surface creator-publication moderation posture directly from the shared projection.");
    Assert(accountSource.Contains("/account/work/publications/@Uri.EscapeDataString(selectedCreatorPublication.PublicationId)/publish", StringComparison.Ordinal), "account publication detail should keep an explicit publish route on the same governed account rail.");
    Assert(accountSource.Contains("Open build path for @selectedCreatorPublication.Title", StringComparison.Ordinal), "account publication detail should give the customer a title-specific path back to the related build follow-through.");
    Assert(accountSource.Contains("Open public publication", StringComparison.Ordinal), "account publication detail should expose the public inspect route alongside private moderation status once the publication is live.");
    Assert(accountSource.Contains("Publication kind", StringComparison.Ordinal), "account publication detail should surface the shared publication kind on the governed detail lane.");
    Assert(accountSource.Contains("Draft kind", StringComparison.Ordinal), "account publication detail should surface the registry draft kind on the governed detail lane.");
    Assert(accountSource.Contains("@PublicCreatorPublicationHref(selectedCreatorPublication.PublicationId)", StringComparison.Ordinal), "account publication detail should deep-link live creator packets onto the public inspect route without hiding the private moderation lane.");
    Assert(accountSource.Contains("@linkedPublication.DiscoverySummary", StringComparison.Ordinal), "account recap shelves should surface linked creator-publication discovery posture instead of compressing it away.");
    Assert(accountSource.Contains("@linkedPublication.TrustSummary", StringComparison.Ordinal), "account recap shelves should surface linked creator-publication trust reasoning instead of dropping it on the detail route.");
    Assert(accountSource.Contains("@linkedPublication.ComparisonSummary", StringComparison.Ordinal), "account recap shelves should surface linked creator-publication comparison guidance instead of compressing it away.");
    Assert(accountSource.Contains("HumanizeStatus(linkedPublication.Visibility, \"Shared\")", StringComparison.Ordinal), "account recap shelves should humanize linked creator-publication visibility instead of hiding it behind the publication detail card.");
    Assert(accountSource.Contains("@linkedPublication.LineageSummary", StringComparison.Ordinal), "account recap shelves should surface lineage by following the linked creator publication.");
    Assert(accountSource.Contains("@linkedPublication.CampaignReturnSummary", StringComparison.Ordinal), "account recap shelves should surface linked creator-publication return truth instead of dropping it outside the publication detail route.");
    Assert(accountSource.Contains("@linkedPublication.SupportClosureSummary", StringComparison.Ordinal), "account recap shelves should surface linked creator-publication support closure instead of dropping it outside the publication detail route.");
    Assert(accountSource.Contains("@linkedPublication.ModerationSummary", StringComparison.Ordinal), "account recap shelves should surface linked creator-publication moderation posture instead of dropping it outside the publication detail route.");
    Assert(accountSource.Contains("Open build path for @linkedPublication.Title", StringComparison.Ordinal), "account recap shelves should keep a direct route back to the linked creator-publication build path.");
    Assert(accountSource.Contains("@PublicCreatorPublicationHref(item.CreatorPublicationId)", StringComparison.Ordinal), "account recap shelves should offer the live public creator-packet inspect route when the linked publication is already discoverable.");
    Assert(accountSource.Contains("@publication.ProvenanceSummary", StringComparison.Ordinal), "account publication list should surface creator-publication provenance directly from the shared projection.");
    Assert(accountSource.Contains("HumanizeStatus(publication.Visibility, \"Shared\")", StringComparison.Ordinal), "account publication list should humanize creator-publication visibility directly from the shared projection.");
    Assert(accountSource.Contains("@publication.LineageSummary", StringComparison.Ordinal), "account publication list should surface creator-publication lineage directly from the shared projection.");
    Assert(accountSource.Contains("HumanizeStatus(publication.TrustBand, \"Draft\")", StringComparison.Ordinal), "account publication list should humanize creator-publication trust ranking directly from the shared projection.");
    Assert(accountSource.Contains("@publication.TrustSummary", StringComparison.Ordinal), "account publication list should surface creator-publication trust reasoning directly from the shared projection.");
    Assert(accountSource.Contains("@publication.ComparisonSummary", StringComparison.Ordinal), "account publication list should surface creator-publication comparison guidance directly from the shared projection.");
    Assert(accountSource.Contains("publication.Discoverable ? \"Eligible now\" : \"Still bounded\"", StringComparison.Ordinal), "account publication list should surface creator-publication discoverability posture directly from the shared projection.");
    Assert(accountSource.Contains("HumanizeStatus(publication.PublicationStatus, \"Published\")", StringComparison.Ordinal), "account publication list should humanize creator-publication state directly from the shared projection.");
    Assert(accountSource.Contains("@publication.ModerationSummary", StringComparison.Ordinal), "account publication list should surface creator-publication moderation posture directly from the shared projection.");
    Assert(accountSource.Contains("Open build path for @publication.Title", StringComparison.Ordinal), "account publication list should keep a title-specific route back to the related build follow-through.");
    Assert(accountSource.Contains("@PublicCreatorPublicationHref(publication.PublicationId)", StringComparison.Ordinal), "account publication list should expose the public creator-packet inspect route alongside private moderation links once the packet is live.");
    Assert(accountSource.Contains("@publication.NextSafeAction", StringComparison.Ordinal), "account publication list should surface the next creator-publication step directly from the shared projection.");
    Assert(accountSource.Contains("Recent change packets", StringComparison.Ordinal), "account work should surface recent change packets for the shared campaign view.");
    Assert(accountSource.Contains("Consequence ledger", StringComparison.Ordinal), "account work should surface the governed consequence ledger for the shared campaign view.");
    Assert(accountSource.Contains("Lead consequence", StringComparison.Ordinal), "account work should summarize the leading consequence directly on the selected campaign card.");
    Assert(!accountSource.Contains("Server-plane follow-through", StringComparison.Ordinal), "account work should avoid internal server-plane wording on the customer-facing route.");
    Assert(accountSource.Contains("What changed for me", StringComparison.Ordinal), "account work should keep the explicit what-changed-for-me packet on the selected campaign card.");
    Assert(accountSource.Contains("var selectedWorkspacePortableExchangeNotice =", StringComparison.Ordinal), "account work should derive a dedicated portable-exchange notice from the selected workspace server plane.");
    Assert(accountSource.Contains("@selectedWorkspacePortableExchangeNotice.Summary", StringComparison.Ordinal), "account work should surface portable exchange directly from the selected workspace decision notice.");
    Assert(accountSource.Contains("Next-session carry-forward", StringComparison.Ordinal), "account work should surface the shared next-session carry-forward projection on both the selected card and the workspace detail drawer.");
    Assert(accountSource.Contains("@selectedWorkspaceNextSessionCarryForward.Summary", StringComparison.Ordinal), "account work should surface the selected workspace carry-forward summary directly from the shared server-plane projection.");
    Assert(accountSource.Contains("Campaign memory", StringComparison.Ordinal), "account work should surface a first-class campaign-memory drawer on both selected and listed shared campaign views.");
    Assert(accountSource.Contains("@selectedWorkspaceCampaignMemory.Summary", StringComparison.Ordinal), "account work should surface the selected workspace campaign-memory summary directly from the shared projection.");
    Assert(accountSource.Contains("@workspace.CampaignMemory.Summary", StringComparison.Ordinal), "account work should surface campaign memory directly on the shared workspace list.");
    Assert(accountSource.Contains("@workspace.NextSessionCarryForward.Summary", StringComparison.Ordinal), "account work should surface next-session carry-forward directly on the shared workspace list.");
    Assert(accountSource.Contains("Downtime brief", StringComparison.Ordinal), "account work should surface downtime follow-through on both the selected workspace detail and the shared workspace list.");
    Assert(accountSource.Contains("@selectedWorkspaceDowntimePackage.Summary", StringComparison.Ordinal), "account work should surface the selected downtime brief summary directly from the shared server-plane projection.");
    Assert(accountSource.Contains("Operations pulse", StringComparison.Ordinal), "account teams and permissions should surface a first-class operations pulse instead of only raw counts.");
    Assert(accountSource.Contains("@op.OperationsSummary", StringComparison.Ordinal), "account teams and permissions should surface the operator operations pulse directly from the shared projection.");
    Assert(accountSource.Contains("League / season operations", StringComparison.Ordinal), "account teams and permissions should surface a first-class league-and-season operations summary on the operator rail.");
    Assert(accountSource.Contains("@op.LeagueOperationsSummary", StringComparison.Ordinal), "account teams and permissions should surface the shared league-operations summary directly from the operator projection.");
    Assert(accountSource.Contains("id=\"community-op-league-@op.GroupId\"", StringComparison.Ordinal), "account teams and permissions should give the league-and-season rail a stable deep-link target.");
    Assert(accountSource.Contains("@op.CampaignReturnSummary", StringComparison.Ordinal), "account teams and permissions should surface the campaign-return pulse directly from the shared projection.");
    Assert(accountSource.Contains("Season / event pulse", StringComparison.Ordinal), "account teams and permissions should surface a first-class season and event pulse instead of treating larger organizer work as implicit.");
    Assert(accountSource.Contains("@op.SeasonEventSummary", StringComparison.Ordinal), "account teams and permissions should surface the operator season-event pulse directly from the shared projection.");
    Assert(accountSource.Contains("<summary>Season &amp; event rail</summary>", StringComparison.Ordinal), "account teams and permissions should give the operator a dedicated auditable season and event rail.");
    Assert(accountSource.Contains("id=\"community-op-events-@op.GroupId\"", StringComparison.Ordinal), "account teams and permissions should give the season-event rail a stable deep-link target.");
    Assert(accountSource.Contains("Season board", StringComparison.Ordinal), "account teams and permissions should surface a first-class season board for multi-campaign operators.");
    Assert(accountSource.Contains("op.SeasonBoardEntries.Count == 0", StringComparison.Ordinal), "account teams and permissions should surface the season-board campaign count directly from the shared projection.");
    Assert(accountSource.Contains("id=\"community-op-board-@op.GroupId\"", StringComparison.Ordinal), "account teams and permissions should give the season board a stable deep-link target.");
    Assert(accountSource.Contains("@entry.LatestEventSummary", StringComparison.Ordinal), "account season board should surface the latest governed event summary for each campaign lane.");
    Assert(accountSource.Contains("@entry.RecapSummary", StringComparison.Ordinal), "account season board should surface the shared recap summary for each campaign lane.");
    Assert(accountSource.Contains("@entry.ConsequenceSummary", StringComparison.Ordinal), "account season board should surface the shared consequence summary for each campaign lane.");
    Assert(accountSource.Contains("@entry.CampaignMemorySummary", StringComparison.Ordinal), "account season board should surface the shared campaign-memory summary for each campaign lane.");
    Assert(accountSource.Contains("@entry.CampaignMemoryReturnSummary", StringComparison.Ordinal), "account season board should surface the shared campaign-memory return cue for each campaign lane.");
    Assert(accountSource.Contains("Open shared campaign view", StringComparison.Ordinal), "account season board should give operators a direct route from the board into the governed campaign lane.");
    Assert(accountSource.Contains("Invite / sponsorship", StringComparison.Ordinal), "account teams and permissions should keep invite and sponsorship posture visible on the same operator surface.");
    Assert(accountSource.Contains("Sponsor session rail", StringComparison.Ordinal), "account teams and permissions should keep sponsor-session posture visible on the operator summary rail.");
    Assert(accountSource.Contains("Invite &amp; sponsorship rail", StringComparison.Ordinal), "account teams and permissions should give operators a dedicated invite and sponsorship rail.");
    Assert(accountSource.Contains("Issue governed join code", StringComparison.Ordinal), "account invite rail should expose a governed join-code issuance flow.");
    Assert(accountSource.Contains("Issue governed boost code", StringComparison.Ordinal), "account invite rail should expose a governed boost-code issuance flow.");
    Assert(accountSource.Contains("Recent join codes", StringComparison.Ordinal), "account invite rail should surface recent governed join codes.");
    Assert(accountSource.Contains("Recent boost codes", StringComparison.Ordinal), "account invite rail should surface recent governed boost codes.");
    Assert(accountSource.Contains("Recent sponsor sessions", StringComparison.Ordinal), "account invite rail should surface recent governed sponsor sessions.");
    Assert(accountSource.Contains("id=\"community-op-sponsor-sessions-@op.GroupId\"", StringComparison.Ordinal), "account invite rail should give the sponsor-session drawer a stable deep-link target.");
    Assert(accountSource.Contains("If a member reports a stale join code", StringComparison.Ordinal), "account invite rail should explain stale-code recovery on the same operator surface.");
    Assert(accountSource.Contains("Launch &amp; closure", StringComparison.Ordinal), "account teams and permissions should keep organizer release and closure posture visible on the same operator surface.");
    Assert(accountSource.Contains("Member guidance rail", StringComparison.Ordinal), "account teams and permissions should provide a bounded member-guidance rail for organizer workflows.");
    Assert(accountSource.Contains("Open current release", StringComparison.Ordinal), "account organizer guidance should link operators to the current release posture.");
    Assert(accountSource.Contains("Open downloads", StringComparison.Ordinal), "account organizer guidance should link operators to the real member download handoff.");
    Assert(accountSource.Contains("Open help and trust", StringComparison.Ordinal), "account organizer guidance should link operators to the help and trust surfaces.");
    Assert(accountSource.Contains("Open support closure", StringComparison.Ordinal), "account organizer guidance should keep support follow-through on the same account backbone.");
    Assert(accountSource.Contains("Search governed prep packets", StringComparison.Ordinal), "account work should expose a real governed prep-library search flow on the selected campaign card.");
    Assert(accountSource.Contains("@selectedWorkspaceServerPlane.WorkspaceState.Label", StringComparison.Ordinal), "account work should surface the bounded workspace state directly from the server plane.");
    Assert(accountSource.Contains("@selectedWorkspaceServerPlane.WorkspaceState.Summary", StringComparison.Ordinal), "account work should explain why the bounded workspace state is active on the selected campaign card.");
    Assert(accountSource.Contains("@selectedWorkspace.NextSafeAction", StringComparison.Ordinal), "account work should surface the workspace next safe action directly on the selected campaign card.");
    Assert(accountSource.Contains("Follow-up lane", StringComparison.Ordinal), "account support detail should surface the follow-up lane instead of assuming the user remembers it.");
    Assert(accountSource.Contains("Release progress:", StringComparison.Ordinal), "account support detail should surface reporter-lane release progress instead of only the closure summary.");
    Assert(accountSource.Contains("Affected install", StringComparison.Ordinal), "account support detail should surface the install linked to the tracked case.");
    Assert(accountSource.Contains("Next safe action:", StringComparison.Ordinal), "account support detail should surface the next honest user action for a tracked case.");
    Assert(accountSource.Contains("setRateLimitNotice", StringComparison.Ordinal), "account support interactions should keep a shared rate-limit notice helper.");
    Assert(accountSource.Contains("Retry after", StringComparison.Ordinal), "account support interactions should project retry timing when pacing applies.");
    Assert(accountSource.Contains("Support intake is pacing requests to keep queue and closure timelines trustworthy.", StringComparison.Ordinal), "account support form should surface a trustworthy pacing explanation instead of a generic failure.");
    Assert(accountSource.Contains("More settings", StringComparison.Ordinal), "account should keep non-core sections behind a calmer secondary settings disclosure.");
    Assert(accountSource.Contains("Model.PrivacyBoundary", StringComparison.Ordinal), "account privacy should render the shared privacy-boundary panel on the signed-in surface.");
    Assert(accountSource.Contains("<summary>Primary sign-in</summary>", StringComparison.Ordinal), "account profile should keep primary sign-in inside a calmer drawer instead of a full stacked section.");
    Assert(!accountSource.Contains("<details class=\"details-drawer\" open>\n                <summary>Primary sign-in</summary>", StringComparison.Ordinal), "account profile should not expand the sign-in drawer by default.");
    Assert(accountSource.Contains("<summary>Recovery email</summary>", StringComparison.Ordinal), "account profile should keep recovery email inside a calmer drawer instead of stacking it inline on the main profile route.");
    Assert(accountSource.Contains("<summary>Need routing help first?</summary>", StringComparison.Ordinal), "account support should keep the grounded assistant behind a calmer disclosure so case filing stays primary.");
    Assert(accountSource.Contains("Advanced account details", StringComparison.Ordinal), "account should hide raw account identifiers behind an advanced disclosure.");
    Assert(accountSource.Contains("Cross-device recovery", StringComparison.Ordinal), "account access should describe restore state as cross-device recovery.");
    Assert(accountSource.Contains("What stays on this device", StringComparison.Ordinal), "account access should keep install-local notes in customer-facing wording.");
    Assert(accountSource.Contains("Recent recaps", StringComparison.Ordinal), "account work should describe recap counts in customer-facing language.");
    Assert(accountSource.Contains("Open support cases", StringComparison.Ordinal), "account work should describe support counts honestly instead of as blockers.");
    Assert(accountSource.Contains("var sectionTitle = Model.CurrentSection switch", StringComparison.Ordinal), "account routes should expose route-specific headings instead of one generic account title.");
    var trustSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml"));
    Assert(trustSource.Contains("supportReleaseChannel", StringComparison.Ordinal), "contact intake should keep release-channel context visible when install-aware support is available.");
    Assert(trustSource.Contains("supportHeadId", StringComparison.Ordinal), "contact intake should keep head context visible when install-aware support is available.");
    Assert(trustSource.Contains("supportArch", StringComparison.Ordinal), "contact intake should keep architecture context visible when install-aware support is available.");
    Assert(trustSource.Contains("What changed in this version", StringComparison.Ordinal), "privacy and terms should render a policy-delta block instead of leaving summary points buried in the generic hero chrome.");
    Assert(trustSource.Contains("HelpFallbackActionFor", StringComparison.Ordinal), "help should expose a deliberate fallback action per lane instead of only one outbound link.");
    Assert(trustSource.Contains("Fallback:", StringComparison.Ordinal), "help cards should render a visible fallback route under the primary next step.");
    Assert(trustSource.Contains("_PrivacyBoundaryPanel.cshtml", StringComparison.Ordinal), "help, privacy, and contact routes should render the shared privacy-boundary panel instead of ad hoc trust copy.");
    Assert(supportSubmittedSource.Contains("Watch Account > Support", StringComparison.Ordinal), "support confirmation should explain the signed-in follow-up lane instead of stopping at a generic receipt.");
    Assert(supportSubmittedSource.Contains("Watch your reply email", StringComparison.Ordinal), "support confirmation should explain the guest follow-up lane instead of assuming an account-only workflow.");
    Assert(supportSubmittedSource.Contains("Next safe action", StringComparison.Ordinal), "support confirmation should keep the tracked case next-step visible when the reporter is signed in.");
    Assert(supportSubmittedSource.Contains("Follow-up lane", StringComparison.Ordinal), "support confirmation should surface the concrete follow-up lane when tracked case truth is available.");
    Assert(supportSubmittedSource.Contains("Affected install", StringComparison.Ordinal), "support confirmation should surface the linked install when the report came from one.");
    Assert(supportSubmittedSource.Contains("Download</a>", StringComparison.Ordinal), "support confirmation should keep saved attachment downloads visible on the first confirmation screen.");
    var faqSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml"));
    Assert(faqSource.Contains("FaqActionFor", StringComparison.Ordinal), "faq should attach direct next-step routing under answers instead of stopping at a text-only sheet.");
    Assert(faqSource.Contains("Open downloads", StringComparison.Ordinal), "faq should expose a direct downloads route for install/update answers.");
    Assert(faqSource.Contains("Open support intake", StringComparison.Ordinal), "faq should expose a direct support route for help and bug-report answers.");
    Assert(faqSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "faq should reuse the shared signed-in trust panel instead of inventing a faq-only trust surface.");
    Assert(faqSource.Contains("_PublicTrustPulsePanel.cshtml", StringComparison.Ordinal), "faq should reuse the shared public trust pulse instead of duplicating weekly trust rows.");
    Assert(!faqSource.Contains("story-guide-tail", StringComparison.Ordinal), "faq should end with a quieter footnote instead of a full landing-style CTA band.");
    var siteScriptSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "wwwroot", "js", "site.js"));
    Assert(siteScriptSource.Contains("Retry-After", StringComparison.Ordinal), "shared site script should preserve Retry-After parsing for paced API responses.");
    Assert(siteScriptSource.Contains("retryAfterSeconds", StringComparison.Ordinal), "shared site script should project retryAfterSeconds into error payloads for support UX pacing notices.");
    var trustCanonSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", ".codex-design", "product", "PUBLIC_TRUST_CONTENT.yaml"));
    Assert(!trustCanonSource.Contains("signed-in shell", StringComparison.Ordinal), "public trust canon should not leak signed-in-shell language into customer copy.");
    Assert(!trustCanonSource.Contains("stays canonical", StringComparison.Ordinal), "public trust canon should not use canonical jargon on public trust surfaces.");
    Assert(trustCanonSource.Contains("The published package stays the same for everyone", StringComparison.Ordinal), "public trust canon should explain the package relationship in customer language.");
    var participateSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"));
    Assert(!participateSource.Contains("story-guide-tail", StringComparison.Ordinal), "participate should open with a quieter route intro instead of a generic CTA band.");
    Assert(participateSource.Contains("Public feedback", StringComparison.Ordinal), "participate should keep the public lane explicit.");
    Assert(participateSource.Contains("Signed-in participation", StringComparison.Ordinal), "participate should keep the signed-in lane explicit.");
    var surface = landing.LoadSurface();
    Assert(string.Equals(surface.Surface, "chummer.run", StringComparison.Ordinal), "landing surface should target chummer.run");
    Assert(surface.PublicRoutes.Any(static route => string.Equals(route.Path, "/", StringComparison.Ordinal)), "landing surface should expose the root route");
    Assert(surface.PublicRoutes.Any(static route => string.Equals(route.Path, "/participate", StringComparison.Ordinal)), "landing surface should expose the participate entry route");
    Assert(surface.AuthRoutes.Any(static route => string.Equals(route.Path, "/login", StringComparison.Ordinal)), "landing surface should expose the login route");
    Assert(surface.AuthRoutes.Any(static route => string.Equals(route.Path, "/signup", StringComparison.Ordinal)), "landing surface should expose the signup route");
    Assert(surface.GuestShellActions.Any(static action => string.Equals(action.Href, "/login?next=/home", StringComparison.Ordinal) && string.Equals(action.Label, "Sign in", StringComparison.Ordinal)), "landing guest shell should expose the sign-in action");
    Assert(surface.GuestShellActions.Any(static action => string.Equals(action.Href, "/signup?next=/home", StringComparison.Ordinal) && string.Equals(action.Label, "Create account", StringComparison.Ordinal)), "landing guest shell should expose the create-account action");
    Assert(surface.HeroCtas.Any(static action => string.Equals(action.Emphasis, "primary", StringComparison.OrdinalIgnoreCase) && string.Equals(action.Label, "Create account to install", StringComparison.Ordinal)), "landing canon should single-source the guest hero access CTA.");
    Assert(surface.Assets.Any(static asset => string.Equals(asset.AssetSlot, "section_hero", StringComparison.Ordinal)), "landing surface should load the hero asset slot");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Title, "KARMA FORGE", StringComparison.Ordinal) && string.Equals(card.Badge, "Research", StringComparison.Ordinal)), "landing feature registry should carry the updated readiness posture for KARMA FORGE");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "real_public_guide", StringComparison.Ordinal) && string.Equals(card.Href, "/what-is-chummer#public-guide", StringComparison.Ordinal) && card.ExternalOk), "landing guide card should keep a first-party route with an explicit external fallback");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "artifact_runsite_pack", StringComparison.Ordinal) && string.Equals(card.Href, "/roadmap/runsite", StringComparison.Ordinal)), "artifact cards should point at related horizon details instead of self-linking to the shelf");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && string.Equals(card.GuestHref, "/login?next=/participate/codex", StringComparison.Ordinal) && string.Equals(card.RegisteredHref, "/participate/codex", StringComparison.Ordinal)), "booster participation should split guest and registered destinations");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_beta", StringComparison.Ordinal) && string.Equals(card.GuestHref, "/signup?next=/account/settings", StringComparison.Ordinal) && string.Equals(card.RegisteredHref, "/account/settings", StringComparison.Ordinal)), "beta waitlist should split guest signup from the calmer account-settings follow-up path");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && string.Equals(card.ActionLabel, "Open guided contribution", StringComparison.Ordinal)), "guided contribution should keep an explicit signed-in action label in canon.");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_beta", StringComparison.Ordinal) && string.Equals(card.ActionLabel, "Join beta waitlist", StringComparison.Ordinal)), "beta waitlist should keep an explicit signed-in action label in canon.");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "horizon_local_co_processor", StringComparison.Ordinal) && string.Equals(card.ActionLabel, "Open the horizon page", StringComparison.Ordinal)), "local co-processor should route through its roadmap detail page instead of pretending the overview card is an install action.");
    var releaseExperienceSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", ".codex-design", "product", "PUBLIC_RELEASE_EXPERIENCE.yaml"));
    Assert(!releaseExperienceSource.Contains("canonical installer", StringComparison.OrdinalIgnoreCase), "release-experience canon should not leak canonical-installer wording into the signed-in handoff copy.");
    Assert(releaseExperienceSource.Contains("same published download", StringComparison.Ordinal), "release-experience canon should describe the signed-in handoff in customer-facing download language.");
    var downloadsSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml"));
    var publicLandingControllerSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
    var statusSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Status.cshtml"));
    var featureDetailSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "FeatureDetail.cshtml"));
    var liveProofDetailSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "_FeatureDetailLiveProof.cshtml"));
    var previewDetailSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "_FeatureDetailPreviewConcept.cshtml"));
    var roadmapDetailSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "_FeatureDetailRoadmap.cshtml"));
    Assert(downloadsSource.Contains("Advanced download options", StringComparison.Ordinal), "downloads should group advanced distribution paths under one calmer disclosure.");
    Assert(!downloadsSource.Contains("What changed and what to expect", StringComparison.Ordinal), "downloads should not carry a second release explainer block under the primary install path.");
    Assert(downloadsSource.Contains("Release notes, known issues, and requirements", StringComparison.Ordinal), "downloads should tuck release education into one calmer drawer on the primary card.");
    Assert(!downloadsSource.Contains("<summary>Package details</summary>", StringComparison.Ordinal), "downloads should keep package details inside the existing release-information drawer instead of adding a second top-card drawer.");
    Assert(downloadsSource.Contains("recommendedIsInstaller ? \"Install path\" : \"Download path\"", StringComparison.Ordinal), "downloads should keep the technical path label grounded in whether the current shelf item is an installer or a package.");
    Assert(downloadsSource.Contains("recommendedIsInstaller", StringComparison.Ordinal), "downloads should keep the top card copy grounded in whether the current shelf item is an installer or a package.");
    Assert(!downloadsSource.Contains("<p>@release.Recommended.SupportLine</p>", StringComparison.Ordinal), "downloads should not surface the technical install-path line as the primary top-card copy.");
    Assert(downloadsSource.Contains("Open current release", StringComparison.Ordinal), "downloads should route broader release posture back to the dedicated current-release page instead of turning the install card into a second status page.");
    Assert(shelfSource.Contains("PublicSurfaceStatus.AudienceLabel(card.Card.Audience)", StringComparison.Ordinal), "artifact shelf cards should humanize audience labels instead of leaking raw canon values.");
    Assert(!shelfSource.Contains("@card.Card.Audience", StringComparison.Ordinal), "artifact shelf cards should not render raw audience values.");
    Assert(publicLandingControllerSource.Contains("PublicSurfaceStatus.AudienceLabel(card.Audience)", StringComparison.Ordinal), "detail-page facts should humanize audience labels before projecting them.");
    Assert(publicLandingControllerSource.Contains("\"Who should use this now\"", StringComparison.Ordinal), "live proof details should use customer-facing audience copy.");
    Assert(!publicLandingControllerSource.Contains("signed-in shell", StringComparison.Ordinal), "controller-built landing and support copy should avoid signed-in shell wording on customer-facing routes.");
    Assert(shelfSource.Contains("ArtifactViewHref", StringComparison.Ordinal) && shelfSource.Contains("new[] { \"all\", \"personal\", \"campaign\", \"creator\" }", StringComparison.Ordinal), "artifacts shelf should expose first-class personal, campaign, and creator view filters instead of one blended signed-in overlay.");
    Assert(!publicLandingControllerSource.Contains("Redirect(\"/now\")", StringComparison.Ordinal), "status should be a first-class public surface instead of redirecting to the current-release page.");
    Assert(statusSource.Contains("_PublicTrustPulsePanel.cshtml", StringComparison.Ordinal), "status should reuse the shared public trust pulse instead of inventing a second pulse renderer.");
    Assert(statusSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "status should reuse the shared signed-in trust panel instead of inventing another install-specific rail.");
    Assert(statusSource.Contains("/api/public/progress-poster.svg", StringComparison.Ordinal), "status should surface the public progress poster directly from the hosted poster route.");
    Assert(statusSource.Contains("Open progress", StringComparison.Ordinal), "status should keep a direct route to the deeper weighted delivery report.");
    Assert(!featureDetailSource.Contains("story-guide-tail", StringComparison.Ordinal), "detail-family pages should not end with one generic shared tail after the family-specific sections.");
    Assert(!featureDetailSource.Contains("Get help with this surface", StringComparison.Ordinal), "detail-family pages should keep next-step help inside the family-specific route blocks.");
    Assert(liveProofDetailSource.Contains("Model.Chrome.Authenticated", StringComparison.Ordinal), "live proof detail should conditionally surface signed-in artifact continuity instead of treating all visitors the same.");
    Assert(previewDetailSource.Contains("/artifacts#linked-artifacts", StringComparison.Ordinal), "preview concept detail should point signed-in users back to the signed-in artifact shelf.");
    Assert(roadmapDetailSource.Contains("/artifacts#linked-artifacts", StringComparison.Ordinal), "roadmap detail should point signed-in users back to the signed-in artifact shelf.");
    Assert(featureDetailSource.Contains("_SignedInTrustStatusPanel.cshtml", StringComparison.Ordinal), "feature detail should reuse the shared signed-in trust panel instead of inventing a detail-only trust surface.");
    Assert(featureDetailSource.Contains("_PublicTrustPulsePanel.cshtml", StringComparison.Ordinal), "feature detail should reuse the shared public trust pulse instead of duplicating weekly trust rows.");
    Assert(!roadmapDetailSource.Contains("Audience impact", StringComparison.Ordinal), "roadmap detail should not repeat audience copy once the fact rail already states who should follow it.");
    Directory.CreateDirectory(Path.GetDirectoryName(storePath)!);
    var store = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
    var publicationDraftWorkflow = new HubPublicationDraftService();
    var campaignSpine = new CampaignSpineService(store, new WorkspaceLifecyclePolicyService(configuration), new CampaignArtifactRegistryBridge(store), publicationDraftWorkflow);
    var creatorPublicationRegistry = new CreatorPublicationRegistryBridge(publicationDraftWorkflow);
    var accounts = new AccountService(store);
    var identityLinks = new IdentityLinkService(store, accounts);
    var experience = new UserExperienceService(store, accounts);
    var leaderboards = new LeaderboardService(store);
    var groups = new GroupService(store, accounts);
    var identityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(_ =>
        JsonResponse(new IdentityIntrospectionResponse(false, null, null, Array.Empty<string>(), null), HttpStatusCode.Unauthorized))), configuration);
    var linkedIdentityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(request =>
    {
        var body = request.Content is null ? string.Empty : request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        return body.Contains("subject-token", StringComparison.Ordinal)
            ? JsonResponse(new IdentityIntrospectionResponse(true, "session-subject", "subject.demo", new[] { "player" }, DateTimeOffset.UtcNow.AddHours(1)))
            : JsonResponse(new IdentityIntrospectionResponse(false, null, null, Array.Empty<string>(), null), HttpStatusCode.Unauthorized);
    })), configuration);
    var authService = new HubBrowserAuthService(new HttpClient(new StubHttpMessageHandler(_ =>
        JsonResponse(new EmailAuthStartResponse(
            TicketId: "eml_demo",
            SubjectId: "subject.demo",
            Email: "runner@example.invalid",
            DisplayName: "Runner Demo",
            NextPath: "/home",
            CreatedAtUtc: DateTimeOffset.UtcNow,
            ExpiresAtUtc: DateTimeOffset.UtcNow.AddMinutes(15),
            DeliveryMode: "preview_inline_link",
            PreviewNote: "preview"), HttpStatusCode.OK))), configuration);
    var emailLinks = new HubEmailLinkVerificationService(
        DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(tempRoot, "email-links"))));
    var google = CreateGoogleService(configuration, authService, identityLinks, accounts, loggerFactory, tempRoot);
    var campaignOsProof = new CampaignOsLocalProofService(configuration);
    var trustPulse = new PublicTrustPulseService(weeklyPulseArtifact, configuration, loggerFactory.CreateLogger<PublicTrustPulseService>());
    var privacyBoundaries = new PublicPrivacyBoundaryService(canon, routes);
    var supportPresentation = new SupportCasePresentationService();
    var signedInTrustStatus = new SignedInTrustStatusService(installLinking, supportCases, supportPresentation, trustPulse);
    var workspaceServerPlane = new CampaignWorkspaceServerPlaneService(campaignSpine, supportCases, supportPresentation);
    var publicCreatorDiscovery = new PublicCreatorPublicationDiscoveryService(accounts, campaignSpine, publicationDraftWorkflow);
    var installBootstrapTickets = new InstallBootstrapTicketService(
        DataProtectionProvider.Create(Path.Combine(tempRoot, "install-bootstrap-tickets")),
        configuration);
    var personalizedInstallScripts = new PersonalizedInstallScriptService(installLinkingStore, configuration);
    var releaseUploadTickets = new ReleaseUploadTicketService(
        DataProtectionProvider.Create(Path.Combine(tempRoot, "release-upload-tickets")),
        configuration);
    var publicWebHostEnvironment = new SmokeWebHostEnvironment
    {
        EnvironmentName = "Development",
        ApplicationName = "RunServicesSmoke",
        ContentRootPath = tempRoot,
        WebRootPath = Path.Combine(tempRoot, "wwwroot")
    };
    var windowsProofInstallers = new WindowsProofInstallerService(configuration);
    var controller = new PublicLandingController(landing, releases, campaignOsProof, releaseSelection, actions, accounts, identityClient, identityLinks, experience, installLinking, campaignSpine, workspaceServerPlane, publicCreatorDiscovery, chrome, trustContent, privacyBoundaries, trustPulse, signedInTrustStatus, supportCases, supportPresentation, configuration, installBootstrapTickets, personalizedInstallScripts, releaseUploadTickets, windowsProofInstallers, publicWebHostEnvironment, loggerFactory.CreateLogger<PublicLandingController>())
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };
    var authenticatedLandingController = new PublicLandingController(landing, releases, campaignOsProof, releaseSelection, actions, accounts, linkedIdentityClient, identityLinks, experience, installLinking, campaignSpine, workspaceServerPlane, publicCreatorDiscovery, chrome, trustContent, privacyBoundaries, trustPulse, signedInTrustStatus, supportCases, supportPresentation, configuration, installBootstrapTickets, personalizedInstallScripts, releaseUploadTickets, windowsProofInstallers, publicWebHostEnvironment, loggerFactory.CreateLogger<PublicLandingController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var downloadsController = new DownloadsCompatibilityController(
        releases,
        windowsProofInstallers,
        releaseSelection,
        installLinking,
        installBootstrapTickets,
        linkedIdentityClient,
        loggerFactory.CreateLogger<DownloadsCompatibilityController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var installLinkingController = new InstallLinkingController(
        linkedIdentityClient,
        accounts,
        installLinking,
        releases,
        supportCases,
        supportPresentation)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var supportCasesController = new SupportCasesController(
        linkedIdentityClient,
        accounts,
        identityLinks,
        supportCases,
        supportPresentation,
        new SupportAssistantService(supportCases, canon, campaignSpine, installLinking, supportPresentation, loggerFactory.CreateLogger<SupportAssistantService>()),
        supportAttachments,
        installLinking,
        configuration)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var supportAutomationController = new SupportCasesController(
        linkedIdentityClient,
        accounts,
        identityLinks,
        supportCases,
        supportPresentation,
        new SupportAssistantService(supportCases, canon, campaignSpine, installLinking, supportPresentation, loggerFactory.CreateLogger<SupportAssistantService>()),
        supportAttachments,
        installLinking,
        configuration)
    {
        ControllerContext = AuthenticatedControllerContext("smoke-token")
    };
    var accountController = new AccountsController(
        accounts,
        linkedIdentityClient,
        identityLinks,
        experience,
        installLinking,
        supportCases,
        supportPresentation,
        campaignSpine,
        workspaceServerPlane,
        creatorPublicationRegistry,
        chrome,
        google,
        releases,
        releaseSelection,
        privacyBoundaries,
        signedInTrustStatus,
        loggerFactory.CreateLogger<AccountsController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var campaignSpineController = new CampaignSpineController(
        linkedIdentityClient,
        accounts,
        installLinking,
        campaignSpine,
        workspaceServerPlane)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var progressController = new PublicProgressController(
        progress,
        privacyBoundaries,
        navigation,
        chrome,
        accounts,
        identityClient,
        new NoopAntiforgery(),
        loggerFactory.CreateLogger<PublicProgressController>())
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };

    var landingView = await controller.LandingPage(CancellationToken.None) as ViewResult;
    var landingModel = landingView?.Model as LandingPageViewModel;
    Assert(landingModel is not null, "landing page should render through the MVC view layer.");
    Assert(string.Equals(landingModel!.Surface.Headline, "Shadowrun rules truth, with receipts.", StringComparison.Ordinal), "landing page should render the canonical headline");
    Assert(string.Equals(landingModel.PrimaryHeroAction.Label, "Create account to install", StringComparison.Ordinal), "landing page should source the guest-gated primary CTA from release canon.");
    Assert(landingModel.PrimaryHeroAction.Href.StartsWith("/signup?next=", StringComparison.Ordinal), "guest-gated primary CTA should route to signup through the install handoff.");
    Assert(string.Equals(landingModel.SecondaryHeroAction.Label, "See what works today", StringComparison.Ordinal), "landing page should keep the manifest-backed secondary CTA.");
    Assert(landingModel.TrustPulse is not null, "landing page should surface a compact weekly trust pulse on the front door.");
    Assert(landingModel.TrustPulse!.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "landing page should surface who can get the recommended shelf now.");
    Assert(landingModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Release proof", StringComparison.Ordinal) && row.Value.Contains("Local release proof", StringComparison.OrdinalIgnoreCase)), "landing page should surface release-proof posture on the trust pulse.");
    Assert(landingModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Adoption health", StringComparison.Ordinal) && row.Value.Contains("weekly snapshots", StringComparison.OrdinalIgnoreCase)), "landing page should surface measured adoption health on the trust pulse.");
    Assert(landingModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Closure health", StringComparison.Ordinal) && row.Value.Contains("waiting closure", StringComparison.OrdinalIgnoreCase)), "landing page should surface closure-health follow-through on the trust pulse.");
    Assert(landingModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Progress trend", StringComparison.Ordinal) && row.Value.Contains("Trend sparkline", StringComparison.OrdinalIgnoreCase)), "landing page should surface progress trend sparkline on the trust pulse.");
    Assert(landingModel.TrustPulse.TrendSamples.Count > 1, "landing page should surface measured progress points alongside the trust pulse summary.");
    Assert(landingModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Launch readiness", StringComparison.Ordinal) && ContainsLaunchReadinessSignal(row.Value)), "landing page should surface launch-readiness posture on the trust pulse.");
    Assert(landingModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Provider-route stewardship", StringComparison.Ordinal) && row.Value.Contains("Pilot defaults are governed", StringComparison.Ordinal)), "landing page should surface provider-route stewardship on the trust pulse.");
    Assert(landingModel.TrustPulse!.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && row.Value.Contains("current longest pole", StringComparison.OrdinalIgnoreCase)), "landing page should surface the current caution lane from the weekly trust pulse.");
    Assert(landingModel.SignedInStatus is null, "guest landing should not project install-specific signed-in trust posture.");
    Assert(landingModel.Workflows.Any(static card => string.Equals(card.Action.Href, "/downloads", StringComparison.Ordinal)), "landing page should keep the product-story start lane");
    Assert(landingModel.Chrome.HeaderActions.Any(static action => string.Equals(action.Label, "Create account to install", StringComparison.Ordinal) && action.Href.StartsWith("/signup?next=", StringComparison.Ordinal)), "landing page chrome should expose the release-aware signup CTA beside sign in");
    Assert(landingModel.Lanes.Any(static card => string.Equals(card.Card.Title, "Creator", StringComparison.Ordinal)), "landing page should keep the creator lane in the public entry surface");
    Assert(!string.IsNullOrWhiteSpace(landingModel.Assets.BySlot("section_hero")?.PosterUrl), "landing hero should use a non-empty media asset.");
    Assert(landingModel.AvailableToday.Any(static card => string.Equals(card.Card.Id, "real_mobile_prep", StringComparison.Ordinal)), "landing should treat inspectable continuity proof as available today instead of relegating it to a preview bucket.");
    Assert(!landingModel.PreviewItems.Any(static card => string.Equals(card.Card.Id, "real_mobile_prep", StringComparison.Ordinal)), "landing preview strip should not keep inspectable continuity proof in a second-class bucket.");

    var storyView = await controller.ProductStoryPage(CancellationToken.None) as ViewResult;
    var storyModel = storyView?.Model as StoryPageViewModel;
    Assert(storyModel is not null && storyModel.TrustPillars.Count == 3, "product story page should expose the three trust pillars.");
    Assert(storyModel!.TrustPulse is not null, "guest product story should surface the weekly public trust pulse.");
    Assert(storyModel.SignedInStatus is null, "guest product story should not project install-specific signed-in trust posture.");
    var authenticatedStoryView = await authenticatedLandingController.ProductStoryPage(CancellationToken.None) as ViewResult;
    var authenticatedStoryModel = authenticatedStoryView?.Model as StoryPageViewModel;
    Assert(authenticatedStoryModel?.TrustPulse is not null, "authenticated product story should keep the weekly public trust pulse visible.");
    Assert(authenticatedStoryModel?.SignedInStatus is not null, "authenticated product story should project the shared signed-in trust status.");
    var roadmapDetailView = await controller.RoadmapDetailPage("runsite", CancellationToken.None) as ViewResult;
    var roadmapDetailModel = roadmapDetailView?.Model as FeatureDetailPageViewModel;
    Assert(roadmapDetailModel is not null && !string.IsNullOrWhiteSpace(roadmapDetailModel.ProofNote), "roadmap detail pages should expose a verification note instead of a bare placeholder shell.");
    Assert(!string.Equals(roadmapDetailModel?.StatusEyebrow, "Current status", StringComparison.OrdinalIgnoreCase), "roadmap detail pages should project a roadmap-specific status frame.");
    Assert(roadmapDetailModel!.MicroProof.Count > 0, "roadmap detail pages should surface micro-proof markers.");
    Assert(roadmapDetailModel.TrustPulse is not null, "guest roadmap detail should surface the weekly public trust pulse.");
    Assert(roadmapDetailModel.SignedInStatus is null, "guest roadmap detail should not project install-specific signed-in trust posture.");
    Assert(roadmapDetailModel.SecondaryAction is not null, "roadmap detail pages should keep a single deeper brief action.");
    var roadmapSecondaryAction = roadmapDetailModel.SecondaryAction!;
    Assert(!string.Equals(
        PublicRouteCatalog.NormalizeRoute(roadmapDetailModel.PrimaryAction.Href),
        PublicRouteCatalog.NormalizeRoute(roadmapSecondaryAction.Href),
        StringComparison.OrdinalIgnoreCase), "roadmap detail pages should not repeat the same primary and secondary action.");
    var artifactDetailView = await controller.ArtifactDetailPage("current-preview-build", CancellationToken.None) as ViewResult;
    var artifactDetailModel = artifactDetailView?.Model as FeatureDetailPageViewModel;
    Assert(artifactDetailModel is not null && !string.IsNullOrWhiteSpace(artifactDetailModel.Payoff), "artifact detail pages should carry explicit product payoff.");
    Assert(!string.Equals(artifactDetailModel?.StatusEyebrow, "Current status", StringComparison.OrdinalIgnoreCase), "artifact detail pages should project an availability-specific status frame.");
    Assert(!string.Equals(artifactDetailModel?.PrimaryAction.Label, "Read the linked detail", StringComparison.OrdinalIgnoreCase), "artifact detail pages should not fall back to a generic linked-detail label.");
    Assert(artifactDetailModel!.TrustPulse is not null, "guest artifact detail should surface the weekly public trust pulse.");
    Assert(artifactDetailModel.SignedInStatus is null, "guest artifact detail should not project install-specific signed-in trust posture.");
    var authenticatedRoadmapDetailView = await authenticatedLandingController.RoadmapDetailPage("runsite", CancellationToken.None) as ViewResult;
    var authenticatedRoadmapDetailModel = authenticatedRoadmapDetailView?.Model as FeatureDetailPageViewModel;
    Assert(authenticatedRoadmapDetailModel?.TrustPulse is not null, "authenticated roadmap detail should keep the weekly public trust pulse visible.");
    Assert(authenticatedRoadmapDetailModel?.SignedInStatus is not null, "authenticated roadmap detail should project the shared signed-in trust status.");
    var authenticatedArtifactDetailView = await authenticatedLandingController.ArtifactDetailPage("current-preview-build", CancellationToken.None) as ViewResult;
    var authenticatedArtifactDetailModel = authenticatedArtifactDetailView?.Model as FeatureDetailPageViewModel;
    Assert(authenticatedArtifactDetailModel?.TrustPulse is not null, "authenticated artifact detail should keep the weekly public trust pulse visible.");
    Assert(authenticatedArtifactDetailModel?.SignedInStatus is not null, "authenticated artifact detail should project the shared signed-in trust status.");
    var participateView = await controller.ParticipatePage(CancellationToken.None) as ViewResult;
    var participateModel = participateView?.Model as ParticipatePageViewModel;
    Assert(participateModel is not null, "participate page should render through the MVC view layer.");
    Assert(participateModel!.TrustPulse is not null, "guest participate page should surface the weekly public trust pulse.");
    Assert(participateModel.SignedInStatus is null, "guest participate page should not project install-specific signed-in trust posture.");
    Assert(participateModel!.SignedInLane.Any(static card => string.Equals(card.Action.Label, "Open guided contribution", StringComparison.Ordinal) && string.Equals(card.Action.Href, "/login?next=/participate/codex", StringComparison.Ordinal)), "guest participate page should route guided contribution through login first.");
    Assert(participateModel.SignedInLane.Any(static card => string.Equals(card.Action.Label, "Join beta waitlist", StringComparison.Ordinal) && string.Equals(card.Action.Href, "/signup?next=/account/settings", StringComparison.Ordinal)), "guest participate page should route beta follow-up through signup first.");
    var authenticatedParticipateView = await authenticatedLandingController.ParticipatePage(CancellationToken.None) as ViewResult;
    var authenticatedParticipateModel = authenticatedParticipateView?.Model as ParticipatePageViewModel;
    Assert(authenticatedParticipateModel is not null, "authenticated participate page should render through the MVC view layer.");
    Assert(authenticatedParticipateModel!.TrustPulse is not null, "authenticated participate page should keep the weekly public trust pulse visible.");
    Assert(authenticatedParticipateModel.SignedInStatus is not null, "authenticated participate page should project the shared signed-in trust status.");
    Assert(authenticatedParticipateModel!.SignedInLane.Any(static card => string.Equals(card.Action.Label, "Open guided contribution", StringComparison.Ordinal) && string.Equals(card.Action.Href, "/participate/codex", StringComparison.Ordinal)), "signed-in participate page should keep the direct guided-contribution route.");
    Assert(authenticatedParticipateModel.SignedInLane.Any(static card => string.Equals(card.Action.Label, "Join beta waitlist", StringComparison.Ordinal) && string.Equals(card.Action.Href, "/account/settings", StringComparison.Ordinal)), "signed-in participate page should keep the direct beta waitlist route.");
    var privacyPage = trustContent.BuildPrivacyPage(chrome.BuildPublicChrome("Privacy", "What Chummer stores, and what it does not.", "/privacy"));
    Assert(privacyPage.Actions.Any(static action => string.Equals(action.Label, "Create account", StringComparison.Ordinal) && action.Href.StartsWith("/signup?next=", StringComparison.Ordinal)), "privacy page should adapt account-only actions into signup-first actions for guests.");
    var publicPrivacyView = await controller.PrivacyPage(CancellationToken.None) as ViewResult;
    var publicPrivacyModel = publicPrivacyView?.Model as TrustPageViewModel;
    Assert(publicPrivacyModel?.TrustPulse is not null, "privacy page should surface the weekly public trust pulse.");
    Assert(publicPrivacyModel?.SignedInStatus is null, "guest privacy page should not project install-specific signed-in trust posture.");
    Assert(publicPrivacyModel?.PrivacyBoundary is not null, "privacy page should surface the public privacy-boundary projection.");
    Assert(publicPrivacyModel!.PrivacyBoundary!.Domains.Count >= 4, "privacy page should keep the support, install, survey, and provider domains visible.");
    var authenticatedPrivacyView = await authenticatedLandingController.PrivacyPage(CancellationToken.None) as ViewResult;
    var authenticatedPrivacyModel = authenticatedPrivacyView?.Model as TrustPageViewModel;
    Assert(authenticatedPrivacyModel?.TrustPulse is not null, "authenticated privacy page should keep the weekly public trust pulse visible.");
    Assert(authenticatedPrivacyModel?.SignedInStatus is not null, "authenticated privacy page should project the shared signed-in trust status.");
    var publicTermsView = await controller.TermsPage(CancellationToken.None) as ViewResult;
    var publicTermsModel = publicTermsView?.Model as TrustPageViewModel;
    Assert(publicTermsModel?.TrustPulse is not null, "terms page should surface the weekly public trust pulse.");
    Assert(publicTermsModel?.SignedInStatus is null, "guest terms page should not project install-specific signed-in trust posture.");
    var authenticatedTermsView = await authenticatedLandingController.TermsPage(CancellationToken.None) as ViewResult;
    var authenticatedTermsModel = authenticatedTermsView?.Model as TrustPageViewModel;
    Assert(authenticatedTermsModel?.TrustPulse is not null, "authenticated terms page should keep the weekly public trust pulse visible.");
    Assert(authenticatedTermsModel?.SignedInStatus is not null, "authenticated terms page should project the shared signed-in trust status.");
    var publicContactView = await controller.ContactPage(CancellationToken.None) as ViewResult;
    var publicContactModel = publicContactView?.Model as TrustPageViewModel;
    Assert(publicContactModel?.TrustPulse is not null, "guest contact page should surface the weekly public trust pulse.");
    Assert(publicContactModel?.PrivacyBoundary is not null, "guest contact page should surface the same privacy-boundary panel before support intake.");
    Assert(publicContactModel?.SupportIntake is not null, "guest contact page should keep the first-party support intake available.");
    var publicFaqView = await controller.FaqPage(CancellationToken.None) as ViewResult;
    var publicFaqModel = publicFaqView?.Model as FaqPageViewModel;
    Assert(publicFaqModel?.TrustPulse is not null, "guest faq should surface the weekly public trust pulse.");
    Assert(publicFaqModel?.SignedInStatus is null, "guest faq should not project install-specific signed-in trust posture.");

    var downloadsView = await controller.DownloadsPage(CancellationToken.None) as ViewResult;
    var downloadsModel = downloadsView?.Model as DownloadsPageViewModel;
    Assert(downloadsModel?.TrustPulse is not null, "guest downloads should surface the weekly public trust pulse.");
    Assert(downloadsModel is not null && downloadsModel.Manifest.Downloads.Any(static item => string.Equals(item.Id, "smoke-poc-linux-x64", StringComparison.Ordinal)), "downloads page should render artifacts from the live release manifest");
    Assert(downloadsModel!.Manifest.Downloads.All(static item => !string.Equals(item.Id, "smoke-poc-osx-arm64-installer", StringComparison.Ordinal)), "downloads page should filter withheld macOS artifacts from the public manifest.");
    Assert(string.Equals(downloadsModel?.Manifest.Version, "0.6.1-smoke", StringComparison.Ordinal), "downloads page should surface the manifest version");
    Assert(downloadsModel!.ReleaseExperience.InstallSteps.Any(static step => step.Contains("Download the current published package for your platform.", StringComparison.OrdinalIgnoreCase)), "guest-readable releases should keep the public install steps for the current preview recommendation.");
    Assert(!downloadsModel.ReleaseExperience.InstallSteps.Any(static step => step.Contains("Create your Chummer account first.", StringComparison.OrdinalIgnoreCase)), "guest-readable releases should not pretend the current preview requires account creation before download.");
    Assert(string.Equals(downloadsModel.ReleaseExperience.GuestGatePrimaryLabel, "Create account to install", StringComparison.Ordinal), "downloads page should keep the signup-first guest gate label.");
    Assert(string.Equals(downloadsModel.ReleaseExperience.KnownIssuesLabel, "Known issues and install help", StringComparison.Ordinal), "downloads page should keep a single known-issues/install-help label for the current preview.");
    Assert(string.Equals(downloadsModel.Manifest.SupportabilityState, "local_docker_proven", StringComparison.Ordinal), "downloads page should preserve registry-owned supportability posture.");
    Assert(string.Equals(downloadsModel.Manifest.ProofStatus, "passed", StringComparison.Ordinal), "downloads page should preserve registry-owned release proof posture.");
    Assert(downloadsModel.Manifest.FixAvailabilitySummary?.Contains("affected install", StringComparison.OrdinalIgnoreCase) == true, "downloads page should preserve registry-owned fix availability guidance.");
    var runtimeManifestConfiguration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
            ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "http://registry.local/api/v1/registry/release-channel/current",
        })
        .Build();
    var runtimeManifestService = new PublicReleaseManifestService(
        runtimeManifestConfiguration,
        new HttpClient(new StubHttpMessageHandler(request =>
        {
            Assert(
                string.Equals(request.RequestUri?.AbsoluteUri, "http://registry.local/api/v1/registry/release-channel/current", StringComparison.Ordinal),
                "runtime manifest fetch should target the registry release-channel endpoint.");
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    File.ReadAllText(Path.Combine(downloadsRoot, "RELEASE_CHANNEL.generated.json")),
                    Encoding.UTF8,
                    "application/json")
            };
        })));
    var runtimeManifest = runtimeManifestService.LoadManifest();
    Assert(string.Equals(runtimeManifest.Source, "registry_runtime", StringComparison.Ordinal), "release manifest service should prefer the registry runtime endpoint when configured.");
    Assert(string.Equals(runtimeManifest.SupportabilityState, "local_docker_proven", StringComparison.Ordinal), "runtime manifest fetch should preserve supportability posture.");
    Assert(string.Equals(runtimeManifest.ProofStatus, "passed", StringComparison.Ordinal), "runtime manifest fetch should preserve proof posture.");
    controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)";
    var macDownloadsView = await controller.DownloadsPage(CancellationToken.None) as ViewResult;
    var macDownloadsModel = macDownloadsView?.Model as DownloadsPageViewModel;
    Assert(macDownloadsModel is not null, "downloads page should still render for a macOS user agent even when the platform is withheld.");
    Assert(string.Equals(macDownloadsModel!.ReleaseExperience.RequestedPlatformLabel, "macOS", StringComparison.Ordinal), "downloads page should detect the macOS user agent.");
    Assert(!macDownloadsModel.ReleaseExperience.RequestedPlatformHasPublicDownload, "downloads page should mark the requested macOS platform as unavailable when the shelf is withheld.");
    Assert(!string.IsNullOrWhiteSpace(macDownloadsModel.ReleaseExperience.PlatformShelfNoticeTitle), "downloads page should surface a shelf note when macOS is not publicly promoted.");
    Assert(
        macDownloadsModel.ReleaseExperience.PlatformShelfNoticeSummary?.Contains("macOS", StringComparison.OrdinalIgnoreCase) == true
        && macDownloadsModel.ReleaseExperience.PlatformShelfNoticeSummary.Contains("does not publish", StringComparison.OrdinalIgnoreCase),
        "downloads page should explain that the macOS build lane is not yet on the public shelf.");
    Assert(
        macDownloadsModel.ReleaseExperience.PlatformAvailability.Any(static item =>
            string.Equals(item.PlatformId, "linux", StringComparison.OrdinalIgnoreCase)
            && item.PubliclyAvailable),
        "downloads page should still surface the current public platform matrix when the requested platform is unavailable.");
    Assert(
        macDownloadsModel.ReleaseExperience.PlatformAvailability.Any(static item =>
            string.Equals(item.PlatformId, "macos", StringComparison.OrdinalIgnoreCase)
            && !item.PubliclyAvailable),
        "downloads page should explicitly mark macOS as off-shelf instead of silently falling through to another platform.");
    var authenticatedDownloadResult = await downloadsController.DownloadArtifact("smoke-poc-linux-x64", CancellationToken.None);
    var authenticatedRedirect = authenticatedDownloadResult as RedirectResult;
    Assert(authenticatedRedirect is not null && string.Equals(authenticatedRedirect.Url, "/downloads/install/smoke-poc-linux-x64", StringComparison.Ordinal), "signed-in compatibility downloads should route through the install handoff.");
    var blockedMacFile = await downloadsController.DownloadFile("smoke-poc-osx-arm64-installer.dmg", CancellationToken.None);
    Assert(blockedMacFile is NotFoundResult, "direct file routes should not serve macOS artifacts that were withheld from the public shelf.");
    var dispatchView = await authenticatedLandingController.DownloadDispatchPage("smoke-poc-linux-x64", CancellationToken.None) as ViewResult;
    var dispatchModel = dispatchView?.Model as DownloadDispatchPageViewModel;
    Assert(dispatchModel is not null && string.Equals(dispatchModel.DownloadHref, "/downloads/file/smoke-poc-linux-x64", StringComparison.Ordinal), "signed-in download handoff should expose the canonical file route.");
    Assert(!string.IsNullOrWhiteSpace(dispatchModel?.ClaimExchangeUrl) && dispatchModel.ClaimExchangeUrl!.EndsWith("/continue.json", StringComparison.Ordinal), "signed-in download handoff should expose a private continuation route for install recovery.");
    Assert(!string.IsNullOrWhiteSpace(dispatchModel?.Heading), "signed-in download handoff should expose a non-empty heading.");
    Assert(!string.IsNullOrWhiteSpace(dispatchModel?.Summary), "signed-in download handoff should expose a non-empty summary.");
    Assert(dispatchModel?.Steps.Count > 0, "signed-in download handoff should expose the signed-in install steps.");
    Assert(dispatchModel?.SupportHref.Contains("/contact?", StringComparison.Ordinal) == true, "signed-in download handoff should project install-aware support follow-through on the same rail.");
    Assert(dispatchModel?.TrustPulse is not null, "signed-in download handoff should keep the weekly public trust pulse visible.");
    Assert(dispatchModel?.SignedInStatus is not null, "signed-in download handoff should project the shared signed-in trust status.");
    var publicContactPageMethod = typeof(PublicLandingController).GetMethods()
        .Single(static method =>
            string.Equals(method.Name, nameof(PublicLandingController.ContactPage), StringComparison.Ordinal)
            && method.GetCustomAttributes(typeof(HttpGetAttribute), inherit: true).Length > 0);
    Assert(publicContactPageMethod.GetParameters().Length == 1 && publicContactPageMethod.GetParameters()[0].ParameterType == typeof(CancellationToken), "public contact page should not accept a spoofable submitted query parameter.");
    var linkedUser = accounts.EnsureUser("subject.demo", "Runner Demo", "runner@example.invalid");
    var linkedEmail = identityLinks.LinkEmail(new LinkEmailIdentityRequest(
        SubjectId: "subject.demo",
        Email: "runner@example.invalid",
        MakePrimary: true));
    identityLinks.ConfirmIdentityLink(new ConfirmIdentityLinkRequest(
        SubjectId: "subject.demo",
        IdentityLinkId: linkedEmail.IdentityLinkId));
    var operatorGroup = groups.CreateGroup(new CreateGroupRequest(
        SubjectId: "subject.demo",
        Name: "Smoke Crew Ops",
        GroupType: "campaign",
        Visibility: "group",
        Capabilities: new[] { "can_manage_members", "can_issue_join_codes", "can_issue_boost_codes", "can_hold_shared_entitlements" }));
    var seededCampaign = groups.GetOrCreateCampaign(operatorGroup.GroupId, "hub", "Smoke Campaign");
    var seededSeasonCampaign = groups.GetOrCreateCampaign(operatorGroup.GroupId, "hub-season", "Smoke Season");
    var operatorJoinCode = groups.CreateJoinCode(operatorGroup.GroupId, new CreateJoinCodeRequest(
        SubjectId: "subject.demo",
        Role: "member",
        Ttl: TimeSpan.FromDays(7)));
    var operatorBoostCode = groups.CreateBoostCode(new CreateBoostCodeRequest(
        SubjectId: "subject.demo",
        GroupId: operatorGroup.GroupId,
        CampaignId: seededCampaign.CampaignId,
        ProjectId: "hub",
        Label: "smoke_operator"));
    var operatorSponsorSessions = new BoostSessionService(
        store,
        accounts,
        groups,
        new FleetBridgeService(new HttpClient(new StubHttpMessageHandler(_ => JsonResponse(new { detail = "operator sponsor session should not hit Fleet" }, HttpStatusCode.InternalServerError))), configuration),
        new RewardService(store));
    var operatorSponsorSession = operatorSponsorSessions.Create(new CreateSponsorSessionRequest(
        SubjectId: "subject.demo",
        ProjectId: "hub",
        GroupId: operatorGroup.GroupId,
        SubjectLabel: "Runner Demo",
        CampaignId: seededCampaign.CampaignId,
        Visibility: "group",
        RequestedLaneType: "participant_burst",
        RequestedLaneRole: "coding",
        AuthorizationTier: "plus",
        TierSource: "operator_verified"));
    operatorSponsorSession = operatorSponsorSessions.RecordConsent(operatorSponsorSession.SponsorSessionId);
    Assert(string.Equals(seededCampaign.GroupId, operatorGroup.GroupId, StringComparison.Ordinal), "smoke campaign should attach to the seeded operator group.");
    Assert(string.Equals(seededSeasonCampaign.GroupId, operatorGroup.GroupId, StringComparison.Ordinal), "secondary smoke season campaign should stay on the same seeded operator group.");
    Assert(!string.IsNullOrWhiteSpace(operatorJoinCode.Code), "operator join-code issuance should produce a durable code.");
    Assert(!string.IsNullOrWhiteSpace(operatorBoostCode.Code), "operator boost-code issuance should produce a durable code.");
    Assert(string.Equals(operatorSponsorSession.Status, "consented", StringComparison.OrdinalIgnoreCase), "operator sponsor-session seeding should leave a real governed sponsor session attached to the operator group.");
    var installSummary = installLinking.GetSummary(linkedUser.UserId, "subject.demo");
    Assert(installSummary.RecentReceipts.Any(static item => string.Equals(item.ArtifactId, "smoke-poc-linux-x64", StringComparison.Ordinal)), "signed-in downloads should mint a durable download receipt.");
    Assert(installSummary.PendingClaimTickets.Any(static item => string.Equals(item.ArtifactId, "smoke-poc-linux-x64", StringComparison.Ordinal) && string.Equals(item.Status, InstallClaimTicketStates.Pending, StringComparison.Ordinal)), "signed-in downloads should mint a pending install claim ticket.");
    var pendingTicket = installSummary.PendingClaimTickets.Single(static item => string.Equals(item.ArtifactId, "smoke-poc-linux-x64", StringComparison.Ordinal));
    var redeemResult = installLinkingController.Redeem(new RedeemInstallClaimRequestDto(
        ClaimCode: pendingTicket.ClaimCode,
        InstallationId: "install-smoke-001",
        HeadId: "avalonia",
        ApplicationVersion: "0.6.1-smoke",
        ChannelId: "preview",
        Platform: "linux",
        Arch: "x64",
        PublicKey: "smoke-public-key",
        HostLabel: "smoke-host"));
    var redeemPayload = (redeemResult.Result as OkObjectResult)?.Value as RedeemInstallClaimResponseDto;
    Assert(redeemPayload is not null && !redeemPayload.AlreadyClaimed, "claim redemption should create a claimed installation on the first pass.");
    Assert(string.Equals(redeemPayload!.Installation.InstallationId, "install-smoke-001", StringComparison.Ordinal), "claim redemption should bind the requested installation id.");
    Assert(string.Equals(redeemPayload.Installation.Status, ClaimedInstallationStates.Active, StringComparison.Ordinal), "claimed installation should become active immediately.");
    Assert(string.Equals(redeemPayload.Grant.Status, InstallationGrantStates.Active, StringComparison.Ordinal), "claim redemption should issue an active installation grant.");
    var refreshResult = installLinkingController.RefreshGrant(new RefreshInstallationGrantRequestDto(
        InstallationId: redeemPayload.Installation.InstallationId,
        AccessToken: redeemPayload.Grant.AccessToken,
        HeadId: "avalonia",
        ApplicationVersion: "0.6.2-smoke",
        ChannelId: "preview",
        Platform: "linux",
        Arch: "x64",
        PublicKey: "smoke-public-key-v2",
        HostLabel: "smoke-host"));
    var refreshPayload = (refreshResult.Result as OkObjectResult)?.Value as RefreshInstallationGrantResponseDto;
    Assert(refreshPayload is not null && refreshPayload.Rotated, "grant refresh should rotate the installation grant.");
    Assert(!string.Equals(refreshPayload!.Grant.AccessToken, redeemPayload.Grant.AccessToken, StringComparison.Ordinal), "grant refresh should issue a new installation token.");
    Assert(string.Equals(refreshPayload.Installation.Version, "0.6.2-smoke", StringComparison.Ordinal), "grant refresh should update the current install version metadata.");
    string currentGrantAccessToken = refreshPayload.Grant.AccessToken;
    var linkedSummaryResult = await installLinkingController.GetSummary(CancellationToken.None);
    var linkedSummaryPayload = (linkedSummaryResult.Result as OkObjectResult)?.Value as InstallLinkingSummaryDto;
    Assert(linkedSummaryPayload is not null, "install linking summary endpoint should return the signed-in account state.");
    Assert(linkedSummaryPayload!.ClaimedInstallations?.Any(static item => string.Equals(item.InstallationId, "install-smoke-001", StringComparison.Ordinal)) == true, "account summary should surface claimed installs after redemption.");
    Assert(linkedSummaryPayload.ActiveGrants?.Any(static item => string.Equals(item.InstallationId, "install-smoke-001", StringComparison.Ordinal) && string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.Ordinal)) == true, "account summary should surface the active grant after rotation.");
    Assert(!linkedSummaryPayload.PendingClaimTickets.Any(item => string.Equals(item.TicketId, pendingTicket.TicketId, StringComparison.Ordinal)), "redeemed claim tickets should no longer appear as pending.");

    var supportSubmitResult = await supportCasesController.Submit(
        new SupportCaseSubmitRequest(
            Kind: SupportCaseKinds.BugReport,
            Title: "Restart guidance was unclear",
            Summary: "The signed-in handoff did not explain whether the update was already staged.",
            Detail: "Please make the restart/apply wording clearer on the account-aware update path.",
            InstallationId: "install-smoke-001",
            ApplicationVersion: "0.6.2-smoke",
            ReleaseChannel: "preview",
            HeadId: "avalonia",
            Platform: "linux",
            Arch: "x64",
            Source: SupportCaseSourceKinds.HubAccount),
        CancellationToken.None);
    var supportAccepted = supportSubmitResult.Result as AcceptedAtActionResult;
    var supportPayload = supportAccepted?.Value as SupportCaseProjection;
    Assert(supportPayload is not null && string.Equals(supportPayload.Status, SupportCaseStatuses.New, StringComparison.Ordinal), "support case submission should create a new support case.");
    Assert(string.Equals(supportPayload!.ReporterEmail, "runner@example.invalid", StringComparison.Ordinal), "signed-in support submission should stamp the reporter email for follow-up mail.");
    SupportCaseProjection supportCase = supportCases.Submit(
        linkedUser.UserId,
        "subject.demo",
        new SupportCaseSubmitRequest(
            Kind: supportPayload!.Kind,
            Title: supportPayload.Title,
            Summary: supportPayload.Summary,
            Detail: supportPayload.Detail,
            ReporterEmail: supportPayload.ReporterEmail,
            InstallationId: supportPayload.InstallationId,
            ApplicationVersion: supportPayload.ApplicationVersion,
            ReleaseChannel: supportPayload.ReleaseChannel,
            HeadId: supportPayload.HeadId,
            Platform: supportPayload.Platform,
            Arch: supportPayload.Arch,
            Source: supportPayload.Source),
        [new SupportAttachmentUpload("smoke-support.log", "text/plain", Encoding.UTF8.GetBytes("smoke support attachment"))]);
    Assert(string.Equals(supportCase.InstallationId, "install-smoke-001", StringComparison.Ordinal), "support case submission should retain installation linkage.");
    Assert(supportCase.Attachments?.Count == 1, "support case submission should retain uploaded attachments.");

    var myCasesResult = await supportCasesController.GetMyCases(status: null, kind: null, CancellationToken.None);
    var myCasesPayload = (myCasesResult.Result as OkObjectResult)?.Value as SupportCaseListResponse;
    Assert(myCasesPayload is not null && myCasesPayload.TotalCount >= 1, "support case list should return reporter-scoped cases.");
    Assert(myCasesPayload!.Items.Any(item => string.Equals(item.CaseId, supportCase.CaseId, StringComparison.Ordinal)), "support case list should include the newly submitted case.");
    var myPresentedCasesResult = await supportCasesController.GetMyPresentedCases(status: null, kind: null, CancellationToken.None);
    var myPresentedCasesPayload = (myPresentedCasesResult.Result as OkObjectResult)?.Value as IReadOnlyList<SupportCaseDigestViewModel>;
    var presentedCase = myPresentedCasesPayload?.FirstOrDefault(item => string.Equals(item.CaseId, supportCase.CaseId, StringComparison.Ordinal));
    Assert(presentedCase is not null, "presented support case list should include the tracked case digest.");
    Assert(!string.IsNullOrWhiteSpace(presentedCase!.NextSafeAction), "presented support case list should surface the next safe action.");
    Assert(!string.IsNullOrWhiteSpace(presentedCase.ReleaseProgressSummary), "presented support case list should surface release progress summary.");
    Assert(!string.IsNullOrWhiteSpace(presentedCase.DetailHref), "presented support case list should keep the tracked detail href.");
    var triageResult = supportAutomationController.ListForTriage(status: null, kind: null, candidateOwnerRepo: null, designImpactOnly: null);
    var triagePayload = (triageResult.Result as OkObjectResult)?.Value as SupportCaseListResponse;
    Assert(triagePayload is not null && triagePayload.Items.Any(item => string.Equals(item.CaseId, supportCase.CaseId, StringComparison.Ordinal)), "internal triage view should surface submitted support cases.");
    var assistantResult = await supportCasesController.AskAssistant(
        new SupportAssistantRequest(
            Query: "The signed-in download restart wording is still confusing after the preview install update.",
            InstallationId: "install-smoke-001"),
        CancellationToken.None);
    var assistantPayload = (assistantResult.Result as OkObjectResult)?.Value as SupportAssistantResponse;
    Assert(assistantPayload is not null && string.Equals(assistantPayload.Confidence, SupportAssistantConfidenceLevels.CaseTruth, StringComparison.Ordinal), "support assistant should ground answers on the signed-in reporter case when available.");
    Assert(assistantPayload!.Citations.Any(static item => string.Equals(item.SourceKind, "support_case", StringComparison.Ordinal)), "support assistant should cite the matching support case.");
    Assert(assistantPayload.Actions.Any(static item => string.Equals(item.ActionId, "open_account_support", StringComparison.Ordinal)), "support assistant should suggest the tracked case timeline when a matching case exists.");
    SupportAssistantService supportAssistant = new(supportCases, canon, campaignSpine, installLinking, supportPresentation, loggerFactory.CreateLogger<SupportAssistantService>());
    var canonOnlyAssistant = supportAssistant.Answer(
        reporterUserId: "usr_runner",
        reporterSubjectId: "subject.runner",
        new SupportAssistantRequest(Query: "How do I install or update the preview build?", InstallationId: null));
    Assert(canonOnlyAssistant.Citations.Any(static item => string.Equals(item.SourceKind, "canon_doc", StringComparison.Ordinal)), "support assistant should ground install/update guidance in canon documents when no matching support case exists.");
    Assert(canonOnlyAssistant.Actions.Any(static item => string.Equals(item.ActionId, "open_downloads", StringComparison.Ordinal)), "support assistant should offer the downloads surface for install/update questions.");
    var rulesAssistant = supportAssistant.Answer(
        reporterUserId: linkedUser.UserId,
        reporterSubjectId: "subject.demo",
        new SupportAssistantRequest(Query: "Why did the rule environment change for my campaign visibility posture?", InstallationId: "install-smoke-001"));
    Assert(rulesAssistant.Citations.Any(static item => string.Equals(item.SourceKind, "rules_truth", StringComparison.Ordinal)), "support assistant should reuse rules navigator truth for grounded campaign-rule questions.");
    Assert(rulesAssistant.Actions.Any(static item => string.Equals(item.ActionId, "open_home", StringComparison.Ordinal)), "support assistant should route grounded rules questions back to the signed-in home cockpit.");
    var buildAssistant = supportAssistant.Answer(
        reporterUserId: linkedUser.UserId,
        reporterSubjectId: "subject.demo",
        new SupportAssistantRequest(Query: "What is the safest build handoff before I export this dossier back into the campaign?", InstallationId: "install-smoke-001"));
    Assert(buildAssistant.Citations.Any(static item => string.Equals(item.SourceKind, "build_truth", StringComparison.Ordinal)), "support assistant should reuse build-path truth for dossier handoff questions.");
    Assert(buildAssistant.Actions.Any(static item => string.Equals(item.ActionId, "open_work", StringComparison.Ordinal)), "support assistant should route build-path questions back to the signed-in work surface.");
    SupportCaseProjection rejectedSupportCase = supportCases.Submit(
        linkedUser.UserId,
        "subject.demo",
        new SupportCaseSubmitRequest(
            Kind: SupportCaseKinds.BugReport,
            Title: "Preview note should stay unchanged",
            Summary: "The signed-in note already matches the intended recovery posture.",
            Detail: "Please keep the current wording because the release lane is already behaving as designed.",
            ReporterEmail: "runner@example.invalid",
            InstallationId: "install-smoke-001",
            ApplicationVersion: "0.6.2-smoke",
            ReleaseChannel: "preview",
            HeadId: "avalonia",
            Platform: "linux",
            Arch: "x64",
            Source: SupportCaseSourceKinds.HubAccount));
    var rejectedResult = supportAutomationController.Transition(
        rejectedSupportCase.CaseId,
        new SupportCaseTransitionRequest(
            TargetStatus: SupportCaseStatuses.Rejected,
            Note: "Rejected because the current signed-in wording already matches the intended release posture.",
            Actor: "fleet",
            DecisionOutcome: "denied",
            ImplementationPosture: "not_implemented",
            DecisionReason: "The reported issue could not be reproduced because the current release and recovery guidance already match the supported flow.",
            EtaText: "No implementation is planned for this report."));
    var rejectedPayload = (rejectedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(rejectedPayload is not null && string.Equals(rejectedPayload.Status, SupportCaseStatuses.Rejected, StringComparison.Ordinal), "rejected transition should move the case into the denied lane.");
    Assert(rewards.ListBadgesForUser(linkedUser.UserId).Any(static badge => string.Equals(badge.Key, "feedback-denied", StringComparison.OrdinalIgnoreCase) && string.Equals(badge.Label, "Denied", StringComparison.Ordinal)), "rejected audited decisions should award Denied on the reporter account.");
    var deniedRequestMail = rejectedPayload!.Timeline?.FirstOrDefault(item =>
        string.Equals(item.Metadata?.GetValueOrDefault("email_stage_id"), "request_received", StringComparison.OrdinalIgnoreCase)
        && string.Equals(item.Metadata?.GetValueOrDefault("email_state"), "sent", StringComparison.OrdinalIgnoreCase));
    Assert(deniedRequestMail is not null, "rejected workflow should still record a sent request-received mail receipt.");
    var deniedDecisionMail = rejectedPayload.Timeline?.FirstOrDefault(item =>
        string.Equals(item.Metadata?.GetValueOrDefault("email_stage_id"), "audited_decision", StringComparison.OrdinalIgnoreCase)
        && string.Equals(item.Metadata?.GetValueOrDefault("email_state"), "sent", StringComparison.OrdinalIgnoreCase));
    Assert(deniedDecisionMail is not null, "rejected workflow should record a sent audited-decision mail receipt.");
    Assert(string.Equals(deniedDecisionMail!.Metadata?.GetValueOrDefault("award_label"), "Denied", StringComparison.Ordinal), "rejected audited-decision mail should record the Denied award.");
    Assert(string.Equals(deniedDecisionMail.Metadata?.GetValueOrDefault("decision_outcome"), "denied", StringComparison.Ordinal), "rejected audited-decision mail should record the denial outcome.");
    Assert(string.Equals(deniedDecisionMail.Metadata?.GetValueOrDefault("implementation_posture"), "not_implemented", StringComparison.Ordinal), "rejected audited-decision mail should record the not-implemented posture.");
    Assert(string.Equals(deniedDecisionMail.Metadata?.GetValueOrDefault("eta_text"), "No implementation is planned for this report.", StringComparison.Ordinal), "rejected audited-decision mail should preserve the no-implementation explanation.");
    var acceptedResult = supportAutomationController.Transition(
        supportCase.CaseId,
        new SupportCaseTransitionRequest(
            TargetStatus: SupportCaseStatuses.Accepted,
            Note: "Accepted for the tracked implementation lane.",
            Actor: "fleet",
            DecisionOutcome: "approved",
            ImplementationPosture: "will_implement",
            DecisionReason: "The signed-in restart wording reproduced clearly and blocks a user-facing update path.",
            EtaText: "Within the next preview drop."));
    var acceptedPayload = (acceptedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(acceptedPayload is not null && string.Equals(acceptedPayload.Status, SupportCaseStatuses.Accepted, StringComparison.Ordinal), "accepted transition should move the case into the tracked implementation lane.");
    Assert(rewards.ListBadgesForUser(linkedUser.UserId).Any(static badge => string.Equals(badge.Key, "clad-feedbacker-accepted", StringComparison.OrdinalIgnoreCase) && string.Equals(badge.Label, "Clad Feedbacker", StringComparison.Ordinal)), "accepted audited decisions should award Clad Feedbacker on the reporter account.");
    var releasedResult = supportAutomationController.Transition(
        supportCase.CaseId,
        new SupportCaseTransitionRequest(
            TargetStatus: SupportCaseStatuses.ReleasedToReporterChannel,
            Note: "Fix is live on preview 0.6.3-smoke.",
            FixedVersion: "0.6.3-smoke",
            FixedChannel: "preview",
            Actor: "fleet"));
    var releasedPayload = (releasedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(releasedPayload is not null && string.Equals(releasedPayload.Status, SupportCaseStatuses.ReleasedToReporterChannel, StringComparison.Ordinal), "internal transition should move the case into released_to_reporter_channel.");
    var postReleaseAssistant = await supportCasesController.AskAssistant(
        new SupportAssistantRequest(
            Query: "Has the preview fix for my download handoff shipped yet?",
            InstallationId: "install-smoke-001"),
        CancellationToken.None);
    var postReleaseAssistantPayload = (postReleaseAssistant.Result as OkObjectResult)?.Value as SupportAssistantResponse;
    Assert(postReleaseAssistantPayload is not null && postReleaseAssistantPayload.Actions.Any(static item => string.Equals(item.ActionId, "open_downloads", StringComparison.Ordinal)), "support assistant should route released fixes back to the downloads surface.");
    Assert(postReleaseAssistantPayload!.Answer.Contains("Update it to preview 0.6.3-smoke first", StringComparison.Ordinal), "support assistant should explain that the linked install needs the reporter-ready build before verification.");
    var notifiedResult = supportAutomationController.NotifyReporter(
        supportCase.CaseId,
        new SupportCaseNotificationRequest(
            Note: "Reporter notified that preview 0.6.3-smoke contains the fix.",
            Actor: "hub",
            Channel: "account_history",
            DownloadUrl: "https://chummer.run/downloads"));
    var notifiedPayload = (notifiedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(notifiedPayload is not null && string.Equals(notifiedPayload.Status, SupportCaseStatuses.UserNotified, StringComparison.Ordinal), "internal notify should close the user-facing loop.");
    var requestReceivedMail = notifiedPayload!.Timeline?.FirstOrDefault(item =>
        string.Equals(item.Metadata?.GetValueOrDefault("email_stage_id"), "request_received", StringComparison.OrdinalIgnoreCase)
        && string.Equals(item.Metadata?.GetValueOrDefault("email_state"), "sent", StringComparison.OrdinalIgnoreCase));
    Assert(requestReceivedMail is not null, "support workflow should record a sent request-received mail receipt.");
    var auditedDecisionMail = notifiedPayload.Timeline?.FirstOrDefault(item =>
        string.Equals(item.Metadata?.GetValueOrDefault("email_stage_id"), "audited_decision", StringComparison.OrdinalIgnoreCase)
        && string.Equals(item.Metadata?.GetValueOrDefault("email_state"), "sent", StringComparison.OrdinalIgnoreCase));
    Assert(auditedDecisionMail is not null, "support workflow should record a sent audited-decision mail receipt.");
    Assert(string.Equals(auditedDecisionMail!.Metadata?.GetValueOrDefault("award_label"), "Clad Feedbacker", StringComparison.Ordinal), "accepted audited-decision mail should record the Clad Feedbacker award.");
    Assert(string.Equals(auditedDecisionMail.Metadata?.GetValueOrDefault("decision_outcome"), "approved", StringComparison.Ordinal), "audited-decision mail should record the approval decision.");
    Assert(string.Equals(auditedDecisionMail.Metadata?.GetValueOrDefault("eta_text"), "Within the next preview drop.", StringComparison.Ordinal), "audited-decision mail should preserve the bounded ETA text.");
    var fixAvailableMail = notifiedPayload.Timeline?.FirstOrDefault(item =>
        string.Equals(item.Metadata?.GetValueOrDefault("email_stage_id"), "fix_available", StringComparison.OrdinalIgnoreCase)
        && string.Equals(item.Metadata?.GetValueOrDefault("email_state"), "sent", StringComparison.OrdinalIgnoreCase));
    Assert(fixAvailableMail is not null, "support workflow should record a sent fix-available mail receipt.");
    Assert(string.Equals(fixAvailableMail!.Metadata?.GetValueOrDefault("download_url"), "https://chummer.run/downloads", StringComparison.Ordinal), "fix-available mail should keep the download route in the recorded receipt.");
    Assert(executeRequests.Count >= 3, "support workflow should queue staged progress mail through EA connector.dispatch.");
    Assert(emailitRequests.Count >= 3, "support workflow should send the staged progress mail through Emailit.");
    Assert(sentReceiptRequests.Count >= 3, "support workflow should mark the staged progress mail as sent in the EA outbox.");
    Assert(failedReceiptRequests.Count == 0, "support workflow should not dead-letter staged progress mail in the smoke path.");
    Assert(executeRequests.Any(item => item.Body.Contains("\"stage_id\":\"request_received\"", StringComparison.Ordinal)), "connector.dispatch payloads should include the request-received stage id.");
    Assert(executeRequests.Any(item => item.Body.Contains("\"stage_id\":\"audited_decision\"", StringComparison.Ordinal)), "connector.dispatch payloads should include the audited-decision stage id.");
    Assert(executeRequests.Any(item => item.Body.Contains("\"stage_id\":\"fix_available\"", StringComparison.Ordinal)), "connector.dispatch payloads should include the fix-available stage id.");
    Assert(executeRequests.All(item => string.Equals(item.Authorization, "ea-smoke-token", StringComparison.Ordinal)), "connector.dispatch calls should use the configured EA bearer token.");
    Assert(executeRequests.All(item => string.Equals(item.PrincipalId, "support-progress-principal", StringComparison.Ordinal)), "connector.dispatch calls should use the configured EA principal scope.");
    Assert(emailitRequests.Any(item =>
        item.Body.Contains("wageslave@chummer.run", StringComparison.OrdinalIgnoreCase)
        && item.Body.Contains("Wageslave", StringComparison.Ordinal)), "Emailit payloads should send from the Wageslave support mailbox.");
    Assert(emailitRequests.Any(item => item.Body.Contains("Your request is in.", StringComparison.Ordinal)), "request-received mail should acknowledge the submitted request.");
    Assert(emailitRequests.Any(item => item.Body.Contains("Award: Denied", StringComparison.Ordinal) && item.Body.Contains("No implementation is planned for this report.", StringComparison.Ordinal)), "rejected audited-decision mail should include the Denied award and the no-implementation explanation.");
    Assert(emailitRequests.Any(item => item.Body.Contains("Award: Clad Feedbacker", StringComparison.Ordinal) && item.Body.Contains("Within the next preview drop.", StringComparison.Ordinal)), "audited-decision mail should include the award and ETA text.");
    Assert(emailitRequests.Any(item =>
        item.Body.Contains("Open the affected claimed desktop install first", StringComparison.Ordinal)
        && item.Body.Contains("https://chummer.run/downloads", StringComparison.Ordinal)
        && item.Body.Contains("Browser fallback for relink or recovery:", StringComparison.Ordinal)), "fix-available mail should keep the claimed desktop install as the primary verification lane and include the browser fallback route.");
    Assert(emailitRequests.All(item => string.Equals(item.Authorization, "emailit-smoke-token", StringComparison.Ordinal)), "Emailit sends should use the configured provider token.");
    Assert(emailitRequests.All(item => !string.IsNullOrWhiteSpace(item.IdempotencyKey)), "Emailit sends should carry an idempotency key.");

    var accountPage = await accountController.AccountPage(section: null, caseId: null, CancellationToken.None) as ViewResult;
    var accountModel = accountPage?.Model as AccountPageViewModel;
    Assert(accountModel is not null && accountModel.SupportCases.Any(item => string.Equals(item.CaseId, supportCase.CaseId, StringComparison.Ordinal)), "account page should surface support-case history beside installs and access.");
    Assert(accountModel!.SupportCaseSummaries.Any(item => string.Equals(item.Case.CaseId, supportCase.CaseId, StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(item.ClosureSummary)), "account page should project support lifecycle and closure summaries instead of only raw case rows.");
    Assert(accountModel.SignedInTrustStatus is not null, "account page should project install-specific trust status directly on the signed-in account surface.");
    Assert(accountModel.SignedInTrustStatus!.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "account page should surface who-can-get-it-now posture inside the signed-in trust panel.");
    Assert(accountModel.SignedInTrustStatus.Rows.Any(static row => string.Equals(row.Label, "Adoption health", StringComparison.Ordinal) && row.Value.Contains("Current local edge proof passed", StringComparison.Ordinal)), "account page should surface adoption health inside the signed-in trust panel.");
    Assert(accountModel.SignedInTrustStatus.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && row.Value.Contains("Update it to preview 0.6.3-smoke first", StringComparison.Ordinal)), "account page should surface the install-specific caution lane inside the signed-in trust panel.");
    Assert(accountModel.PrivacyBoundary is not null, "account page should surface the signed-in privacy boundary next to visibility and recovery posture.");
    Assert(string.Equals(accountModel!.CurrentSection, "profile", StringComparison.Ordinal), "default account route should land on the profile section.");
    Assert(accountModel.CoreSections.Any(static section => string.Equals(section.Href, "/account/access", StringComparison.Ordinal)), "account should expose the devices-and-access section link.");
    Assert(accountModel!.CampaignSpine.Dossiers.Count >= 1, "account page should surface the living dossier summary.");
    Assert(accountModel.CampaignSpine.Runs.Count >= 1, "account page should surface the current runboard summary.");
    Assert(accountModel.CampaignSpine.Campaigns[0].Consequences?.Count >= 4, "campaign projections should persist governed faction, heat, contact, and reputation consequences as durable campaign truth.");
    Assert(accountModel.CampaignSpine.Campaigns[0].Consequences!.Any(item => string.Equals(item.Kind, "heat", StringComparison.Ordinal) && item.Receipts.Count >= 2), "campaign consequences should keep grounded heat receipts attached to the durable campaign record.");
    Assert(accountModel.CampaignSpine.Workspaces.Count >= 1, "account page should surface a first-class campaign workspace.");
    Assert(accountModel.CampaignSpine.Workspaces[0].ReadinessCues.Count >= 1, "campaign workspace should surface readiness cues.");
    Assert(accountModel.CampaignSpine.Workspaces[0].RecapShelf.Count >= 1, "campaign workspace should surface recap or publication-safe continuity outputs.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.Workspaces[0].RecapShelf[0].TrustBand), "campaign workspace should keep creator-publication trust ranking attached to the calmer recap shelf.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.Workspaces[0].RecapShelf[0].CreatorPublicationId), "campaign workspace should keep a direct creator-publication link attached to the calmer recap shelf.");
    Assert(accountModel.CampaignSpine.Workspaces[0].RecapShelf.Any(item => item.Kind.Contains("primer", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace(item.CreatorPublicationId)), "campaign workspace should project a primer-safe recap shelf entry on the same governed publication lane.");
    Assert(accountModel.CampaignSpine.Workspaces[0].Consequences?.Count >= 4, "campaign workspace should surface the governed consequence ledger directly on the shared campaign view.");
    Assert(accountModel.CampaignSpine.Workspaces[0].Consequences!.Any(item => string.Equals(item.Kind, "contact", StringComparison.Ordinal) && item.EvidenceLines.Count >= 1), "campaign workspace should keep receipt-backed contact evidence attached to the shared consequence ledger.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.Workspaces[0].ActiveSceneSummary), "campaign workspace should surface an explicit active-scene summary.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.Workspaces[0].NextSafeAction), "campaign workspace should surface an explicit next safe action.");
    Assert(accountModel.CampaignSpine.Workspaces[0].ChangePackets?.Count >= 1, "campaign workspace should surface recent change packets.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs.Count >= 1, "account page should surface Build Lab handoffs into living dossier and campaign truth.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs[0].Title.Contains("build path", StringComparison.OrdinalIgnoreCase), "account page should receive customer-facing build-path titles directly from the campaign spine service.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.BuildLabHandoffs[0].NextSafeAction), "account page should receive the next safe action directly from the campaign spine service.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.BuildLabHandoffs[0].RuntimeCompatibilitySummary), "account page should receive runtime compatibility truth for the build handoff.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.BuildLabHandoffs[0].SupportClosureSummary), "account page should receive support-closure truth for the build handoff.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.BuildLabHandoffs[0].PlannerCoverageSummary), "account page should receive planner-coverage summary for the build handoff.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs[0].PlannerCoverageLines?.Count >= 4, "account page should receive planner-coverage evidence lines for the build handoff.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs[0].TradeoffLines[0].Contains("campaign-safe output", StringComparison.OrdinalIgnoreCase), "account page should receive exact build-path output posture instead of generic tradeoff filler.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs[0].ProgressionOutcomes[0].Contains("25 / 50 / 100 Karma checkpoints", StringComparison.Ordinal), "account page should receive planner checkpoints directly on the build-path handoff.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs[0].ProgressionOutcomes[1].Contains("recap follow-through", StringComparison.Ordinal), "account page should receive export and recap follow-through posture on the build-path handoff.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs[0].PlannerCoverageLines![0].Contains("Campaign continuity:", StringComparison.Ordinal), "account page should receive campaign continuity planner coverage on the build-path handoff.");
    Assert(accountModel.CampaignSpine.RulesNavigator.Count >= 1, "account page should surface first-class rules navigator answers.");
    Assert(accountModel.CampaignSpine.RulesNavigator[0].Studio is not null, "account page should surface explicit rule-environment studio lifecycle posture.");
    Assert(string.Equals(accountModel.CampaignSpine.RulesNavigator[0].Studio!.CurrentStage, RuleEnvironmentLifecycleStages.CampaignApproved, StringComparison.Ordinal), "account page should keep the current rules studio stage on the campaign-approved rail.");
    Assert(string.Equals(accountModel.CampaignSpine.RulesNavigator[0].Studio!.PromotionTargetStage, RuleEnvironmentLifecycleStages.Published, StringComparison.Ordinal), "account page should keep the next rules studio stage on the published rail.");
    Assert(accountModel.CampaignSpine.RulesNavigator[0].Studio!.Stages.Count == 3, "account page should keep the full sandbox-to-published studio flow attached to rules answers.");
    Assert(accountModel.CampaignSpine.MigrationReceipts.Count >= 1, "account page should surface legacy migration receipts.");
    Assert(accountModel.CampaignSpine.CreatorPublications.Count >= 1, "account page should surface creator publication posture.");
    Assert(accountModel.CampaignSpine.CreatorPublications.Any(item => string.Equals(item.Kind, "primer", StringComparison.Ordinal) && item.Title.Contains("campaign primer", StringComparison.OrdinalIgnoreCase)), "account page should surface a first-class primer publication alongside the existing shared publication lanes.");
    Assert(accountModel.CampaignSpine.CreatorPublications.Any(item => string.Equals(item.Kind, "dossier", StringComparison.Ordinal) && item.Title.Contains("dossier", StringComparison.OrdinalIgnoreCase)), "account page should surface a first-class dossier publication alongside the shared publication lanes.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].TrustBand), "account page should keep creator-publication trust ranking attached.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].TrustSummary), "account page should keep creator-publication trust reasoning attached.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].ComparisonSummary), "account page should keep creator-publication comparison guidance attached.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].LineageSummary), "account page should keep creator-publication lineage attached.");
    Assert(accountModel.CampaignSpine.CreatorPublications[0].Discoverable == false, "preview-ready creator publications should stay off discoverable surfaces until they are actually published.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].NextSafeAction), "account page should keep creator-publication next-step truth attached.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].CampaignReturnSummary), "account page should keep creator-publication return truth attached.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].SupportClosureSummary), "account page should keep creator-publication support closure attached.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].ModerationSummary), "account page should keep creator-publication moderation posture attached.");
    Assert(!string.IsNullOrWhiteSpace(accountModel.CampaignSpine.CreatorPublications[0].BuildHandoffId), "account page should keep the related build handoff id attached to creator publication follow-through.");
    Assert(accountModel.CampaignSpine.Restore.RecentRuleEnvironments.Count >= 1, "account page should surface restore-ready rule environments.");
    Assert(accountModel.CampaignSpine.Restore.RecentArtifacts.Count >= 1, "account page should surface reconnectable artifact truth.");
    Assert(accountModel.CampaignSpine.Restore.Entitlements.Count >= 1, "account page should surface active entitlements in the roaming restore packet.");
    Assert(accountModel.CampaignSpine.Restore.ClaimedDevices.Count >= 1, "account page should surface claimed devices for roaming restore.");
    Assert(accountModel.CampaignSpine.Restore.ClaimedDevices.Any(item => item.RestoreSummary.Contains("bounded offline use", StringComparison.Ordinal)), "account page should expose bounded offline prefetch inventory on claimed-device restore summaries.");
    Assert(accountModel.CampaignSpine.Restore.LocalOnlyNotes.Count >= 1, "account page should keep install-local restore guardrails explicit.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.OperatorRole)), "account page should surface organizer/operator role posture.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.CampaignVisibilitySummary)), "account page should surface explicit campaign visibility posture for operator groups.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.OperationsSummary)), "account page should surface an explicit operator operations pulse for organizer groups.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.LeagueOperationsSummary)), "account page should surface an explicit league-and-season operations summary for organizer groups.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.CampaignReturnSummary)), "account page should surface campaign-return pulse for organizer groups.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.SeasonEventSummary)), "account page should surface a first-class season-event pulse for organizer groups.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.RecentEventSummaries.Count >= 1), "account page should keep at least one recent governed event receipt attached to the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.RecentLeagueAuditLines.Count >= 1), "account page should keep bounded league-and-season audit lines attached to the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.InviteCampaigns.Count >= 2), "account page should keep multi-campaign invite choices on the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.RecentJoinCodes.Any(code => string.Equals(code.Code, operatorJoinCode.Code, StringComparison.Ordinal))), "account page should keep recent governed join codes attached to the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.RecentBoostCodes.Any(code => string.Equals(code.Code, operatorBoostCode.Code, StringComparison.Ordinal))), "account page should keep recent governed boost codes attached to the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.RecentSponsorSessions.Any(session => string.Equals(session.SponsorSessionId, operatorSponsorSession.SponsorSessionId, StringComparison.Ordinal))), "account page should keep recent governed sponsor sessions attached to the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.RecentSponsorSessions.Any(session => session.StatusSummary.Contains("Consent recorded", StringComparison.OrdinalIgnoreCase))), "account page should keep sponsor-session status truth attached to the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.SeasonBoardEntries.Count >= 2), "account page should keep a multi-campaign season board attached to the operator rail.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.SeasonBoardEntries.Any(entry => !string.IsNullOrWhiteSpace(entry.RecapSummary))), "account season board should keep recap summary truth attached to at least one campaign lane.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.SeasonBoardEntries.Any(entry => !string.IsNullOrWhiteSpace(entry.ConsequenceSummary))), "account season board should keep consequence summary truth attached to at least one campaign lane.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.SeasonBoardEntries.All(entry => !string.IsNullOrWhiteSpace(entry.NextSafeAction))), "account season board should keep next-safe-action truth attached to each campaign lane.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.SeasonBoardEntries.All(entry => !string.IsNullOrWhiteSpace(entry.CampaignMemorySummary))), "account season board should keep campaign-memory summary truth attached to each campaign lane.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.ActiveCampaignCount >= 2), "account page should surface a multi-campaign operator group on the same governed backbone.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => item.SeasonEventSummary.Contains("season rail", StringComparison.OrdinalIgnoreCase)), "account page should describe the multi-campaign operator group as a governed season rail.");
    var campaignSummaryResult = await campaignSpineController.GetMyCampaignSummary(CancellationToken.None);
    var campaignSummaryPayload = (campaignSummaryResult.Result as OkObjectResult)?.Value as AccountCampaignSummary ?? campaignSummaryResult.Value;
    Assert(campaignSummaryPayload is not null, "campaign spine api should return the signed-in campaign summary.");
    var freshPreviewUser = accounts.EnsureUser("subject.preview", "Preview Bootstrap", "preview-bootstrap@example.invalid");
    var freshPreviewSummary = campaignSpine.GetAccountSummary(freshPreviewUser);
    Assert(freshPreviewSummary.Workspaces.Count >= 1, "freshly created accounts should receive a seeded preview campaign workspace instead of an empty work shell.");
    Assert(freshPreviewSummary.Workspaces[0].Consequences?.Count >= 4, "freshly created accounts should receive a seeded governed consequence ledger with the preview campaign workspace.");
    Assert(freshPreviewSummary.BuildLabHandoffs.Count >= 1, "freshly created accounts should receive a seeded build-path handoff.");
    Assert(freshPreviewSummary.RulesNavigator.Count >= 1, "freshly created accounts should receive a seeded grounded rule answer.");
    Assert(freshPreviewSummary.CreatorPublications.Count >= 1, "freshly created accounts should receive a seeded publication follow-through.");
    Assert(freshPreviewSummary.CommunityOperations.Count >= 1, "freshly created accounts should receive a seeded operator-aware campaign group.");
    Assert(!string.IsNullOrWhiteSpace(freshPreviewSummary.CommunityOperations[0].OperationsSummary), "freshly created accounts should receive a seeded operator operations pulse.");
    Assert(!string.IsNullOrWhiteSpace(freshPreviewSummary.CommunityOperations[0].LeagueOperationsSummary), "freshly created accounts should receive a seeded league-and-season operations summary.");
    Assert(!string.IsNullOrWhiteSpace(freshPreviewSummary.CommunityOperations[0].SeasonEventSummary), "freshly created accounts should receive a seeded operator season-event pulse.");
    Assert(freshPreviewSummary.CommunityOperations[0].Capabilities.Contains("can_issue_join_codes", StringComparer.OrdinalIgnoreCase), "freshly created accounts should receive invite authority on the seeded operator group.");
    Assert(freshPreviewSummary.CommunityOperations[0].Capabilities.Contains("can_issue_boost_codes", StringComparer.OrdinalIgnoreCase), "freshly created accounts should receive sponsorship authority on the seeded operator group.");
    Assert(freshPreviewSummary.CommunityOperations[0].ActiveCampaignCount >= 2, "freshly created accounts should receive a seeded multi-campaign operator group instead of a single-campaign placeholder.");
    Assert(freshPreviewSummary.CommunityOperations[0].SeasonEventSummary.Contains("season rail", StringComparison.OrdinalIgnoreCase), "freshly created accounts should receive a season-rail summary when one operator group carries multiple governed campaigns.");
    Assert(freshPreviewSummary.CommunityOperations[0].SeasonBoardEntries.Count >= 2, "freshly created accounts should receive a seeded season board with more than one governed campaign lane.");
    Assert(freshPreviewSummary.CommunityOperations[0].SeasonBoardEntries.Any(entry => !string.IsNullOrWhiteSpace(entry.RecapSummary)), "freshly created accounts should receive a recap summary on at least one seeded season-board lane.");
    Assert(freshPreviewSummary.CommunityOperations[0].SeasonBoardEntries.Any(entry => !string.IsNullOrWhiteSpace(entry.ConsequenceSummary)), "freshly created accounts should receive a consequence summary on at least one seeded season-board lane.");
    Assert(freshPreviewSummary.CommunityOperations[0].SeasonBoardEntries.All(entry => !string.IsNullOrWhiteSpace(entry.CampaignMemorySummary)), "freshly created accounts should receive campaign-memory summaries on seeded season-board lanes.");
    var restoreResult = await campaignSpineController.GetMyRestoreProjection(CancellationToken.None);
    var restorePayload = (restoreResult.Result as OkObjectResult)?.Value as WorkspaceRestoreProjection ?? restoreResult.Value;
    Assert(restorePayload is not null && restorePayload.ClaimedDevices.Count >= 1, "campaign spine api should expose the restore packet for claimed-device recovery.");
    string workspaceId = campaignSummaryPayload!.Workspaces[0].WorkspaceId;
    string rulesEntryId = campaignSummaryPayload.RulesNavigator[0].EntryId;
    var workspaceResult = await campaignSpineController.GetMyCampaignWorkspace(workspaceId, CancellationToken.None);
    var workspacePayload = (workspaceResult.Result as OkObjectResult)?.Value as CampaignWorkspaceProjection ?? workspaceResult.Value;
    Assert(workspacePayload is not null && string.Equals(workspacePayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine api should expose a stable workspace summary.");
    string runId = workspacePayload!.Runs[0].RunId;
    string handoffId = campaignSummaryPayload.BuildLabHandoffs
        .First(item => string.Equals(item.CampaignId, workspacePayload.CampaignId, StringComparison.OrdinalIgnoreCase))
        .HandoffId;
    string primerPublicationId = campaignSummaryPayload.CreatorPublications
        .First(item =>
            string.Equals(item.CampaignId, workspacePayload.CampaignId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Kind, "primer", StringComparison.Ordinal))
        .PublicationId;
    string runModulePublicationId = campaignSummaryPayload.CreatorPublications
        .First(item =>
            string.Equals(item.CampaignId, workspacePayload.CampaignId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Kind, "run_module", StringComparison.Ordinal))
        .PublicationId;
    string dossierPublicationId = campaignSummaryPayload.CreatorPublications
        .First(item =>
            string.Equals(item.CampaignId, workspacePayload.CampaignId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Kind, "dossier", StringComparison.Ordinal))
        .PublicationId;
    string publicationId = campaignSummaryPayload.CreatorPublications
        .First(item => string.Equals(item.CampaignId, workspacePayload.CampaignId, StringComparison.OrdinalIgnoreCase))
        .PublicationId;
    Assert(workspacePayload?.ReadinessCues.Count >= 1, "campaign spine workspace api should keep readiness cues attached to the workspace summary.");
    Assert(workspacePayload?.Consequences?.Count >= 4, "campaign spine workspace api should expose the governed consequence ledger.");
    Assert(workspacePayload!.Consequences!.Any(item => string.Equals(item.Kind, "reputation", StringComparison.Ordinal) && item.Receipts.Count >= 1), "campaign spine workspace api should keep grounded reputation receipts attached.");
    Assert(workspacePayload.NextSessionCarryForward is not null, "campaign spine workspace api should expose a first-class next-session carry-forward projection.");
    Assert(workspacePayload.NextSessionCarryForward!.EvidenceLines.Count >= 1, "campaign spine workspace api should attach bounded next-session evidence lines.");
    Assert(workspacePayload.FirstPlayableSession is not null, "campaign spine workspace api should expose a first-class first playable session projection before governed follow-through moves beyond onboarding.");
    Assert(workspacePayload.FirstPlayableSession!.EvidenceLines.Count >= 1, "campaign spine workspace api should attach bounded first-session evidence lines.");
    Assert(!string.IsNullOrWhiteSpace(workspacePayload.FirstPlayableSession.RuleReadySummary), "campaign spine workspace api should expose legal-runner proof on the first-session projection.");
    Assert(!string.IsNullOrWhiteSpace(workspacePayload.FirstPlayableSession.ReturnLaneSummary), "campaign spine workspace api should expose understandable-return proof on the first-session projection.");
    Assert(!string.IsNullOrWhiteSpace(workspacePayload.FirstPlayableSession.CampaignReadySummary), "campaign spine workspace api should expose campaign-ready proof on the first-session projection.");
    Assert(workspacePayload.CampaignMemory is not null, "campaign spine workspace api should expose a first-class campaign-memory projection.");
    Assert(workspacePayload.CampaignMemory!.EvidenceLines.Count >= 1, "campaign spine workspace api should attach bounded campaign-memory evidence lines.");
    Assert(!string.IsNullOrWhiteSpace(workspacePayload?.ActiveSceneSummary), "campaign spine workspace api should expose an active-scene summary.");
    Assert(!string.IsNullOrWhiteSpace(workspacePayload?.NextSafeAction), "campaign spine workspace api should expose a next safe action.");
    Assert(workspacePayload?.ChangePackets?.Count >= 1, "campaign spine workspace api should expose recent change packets.");
    var workspaceDigestsResult = await campaignSpineController.GetMyCampaignWorkspaceDigests(CancellationToken.None);
    var workspaceDigestsPayload = (workspaceDigestsResult.Result as OkObjectResult)?.Value as IReadOnlyList<CampaignWorkspaceDigestProjection> ?? workspaceDigestsResult.Value;
    Assert(workspaceDigestsPayload is not null && workspaceDigestsPayload.Count >= 1, "campaign spine api should expose workspace digests for calmer client follow-through.");
    Assert(workspaceDigestsPayload!.Any(item => string.Equals(item.WorkspaceId, workspaceId, StringComparison.Ordinal)), "campaign spine workspace digests should include the signed-in lead workspace.");
    var leadWorkspaceDigest = workspaceDigestsPayload![0];
    Assert(leadWorkspaceDigest.ReadinessHighlights.Count >= 1, "campaign spine workspace digests should preserve readiness highlights.");
    Assert(!string.IsNullOrWhiteSpace(leadWorkspaceDigest.SupportClosureSummary), "campaign spine workspace digests should preserve support-closure truth.");
    Assert(!string.IsNullOrWhiteSpace(leadWorkspaceDigest.RuleEnvironmentSummary), "campaign spine workspace digests should preserve rule-environment truth.");
    Assert(leadWorkspaceDigest.FirstPlayableSession is not null, "campaign spine workspace digests should preserve calmer first-session proof.");
    Assert(leadWorkspaceDigest.CampaignMemory is not null, "campaign spine workspace digests should preserve the calmer campaign-memory summary.");
    Assert(leadWorkspaceDigest.CampaignMemory!.EvidenceLines.Count >= 1, "campaign spine workspace digests should preserve bounded campaign-memory evidence.");
    var workspaceServerPlaneResult = await campaignSpineController.GetMyCampaignWorkspaceServerPlane(workspaceId, CancellationToken.None);
    var workspaceServerPlanePayload = (workspaceServerPlaneResult.Result as OkObjectResult)?.Value as CampaignWorkspaceServerPlaneProjection ?? workspaceServerPlaneResult.Value;
    Assert(workspaceServerPlanePayload is not null && string.Equals(workspaceServerPlanePayload.Workspace.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine server plane api should expose the same stable workspace id.");
    Assert(workspaceServerPlanePayload!.RosterReadiness.Highlights.Count >= 1, "campaign spine server plane api should expose roster readiness highlights.");
    Assert(workspaceServerPlanePayload.DossierFreshness.Count >= 1, "campaign spine server plane api should expose dossier freshness cues.");
    Assert(workspaceServerPlanePayload.RuleEnvironmentHealth.Count >= 1, "campaign spine server plane api should expose rule-environment health cues.");
    Assert(workspaceServerPlanePayload.ChangePackets.Count >= 1, "campaign spine server plane api should preserve workspace change packets.");
    Assert(workspaceServerPlanePayload.Consequences.Count >= 4, "campaign spine server plane api should preserve the governed consequence ledger.");
    Assert(workspaceServerPlanePayload.Consequences.Any(item => string.Equals(item.Kind, "faction", StringComparison.Ordinal) && item.Receipts.Count >= 1), "campaign spine server plane api should keep grounded faction receipts visible.");
    Assert(workspaceServerPlanePayload.FirstPlayableSession is not null, "campaign spine server plane api should expose the bounded first playable session proof.");
    Assert(workspaceServerPlanePayload.FirstPlayableSession!.EvidenceLines.Count >= 1, "campaign spine server plane api should attach bounded first-session evidence.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.FirstPlayableSession.RuleReadySummary), "campaign spine server plane api should carry legal-runner proof on the bounded first-session projection.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.FirstPlayableSession.ReturnLaneSummary), "campaign spine server plane api should carry understandable-return proof on the bounded first-session projection.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.FirstPlayableSession.CampaignReadySummary), "campaign spine server plane api should carry campaign-ready proof on the bounded first-session projection.");
    Assert(workspaceServerPlanePayload.NextSessionCarryForward is not null, "campaign spine server plane api should expose the bounded next-session carry-forward projection.");
    Assert(workspaceServerPlanePayload.NextSessionCarryForward!.EvidenceLines.Count >= 1, "campaign spine server plane api should attach bounded next-session evidence lines.");
    Assert(workspaceServerPlanePayload.CampaignMemory is not null, "campaign spine server plane api should expose the bounded campaign-memory projection.");
    Assert(workspaceServerPlanePayload.CampaignMemory!.EvidenceLines.Count >= 1, "campaign spine server plane api should attach bounded campaign-memory evidence.");
    Assert(workspaceServerPlanePayload.SupportClosures.Count >= 1, "campaign spine server plane api should expose install-aware support closure cues.");
    Assert(workspaceServerPlanePayload.DecisionNotices.Count >= 1, "campaign spine server plane api should expose bounded follow-through notices.");
    Assert(workspaceServerPlanePayload.DecisionNotices.Any(item => string.Equals(item.Kind, "portable_exchange", StringComparison.Ordinal)), "campaign spine server plane api should surface a first-class portable exchange notice.");
    Assert(workspaceServerPlanePayload.CampaignSummary.RestoreSummary.Contains("Prefetch inventory:", StringComparison.Ordinal), "campaign spine server plane api should make restore prefetch inventory explicit.");
    Assert(workspaceServerPlanePayload.CampaignSummary.RestoreSummary.Contains("bounded offline use", StringComparison.Ordinal), "campaign spine server plane api should keep restore posture tied to bounded offline use.");
    Assert(workspaceServerPlanePayload.RestoreProvenanceReceipts.Count == restorePayload!.ProvenanceReceipts.Count, "campaign spine server plane api should preserve restore provenance receipts without dropping account restore evidence.");
    Assert(workspaceServerPlanePayload.RestoreProvenanceRecoveryReceipts.Count == restorePayload.ProvenanceReceipts.Count, "campaign spine server plane api should expose a recovery cue for every restore provenance receipt.");
    Assert(workspaceServerPlanePayload.RestoreConflictReceipts.Count == restorePayload.ConflictReceipts.Count, "campaign spine server plane api should preserve restore conflict receipts without dropping continuity conflict evidence.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.Summary), "campaign spine server plane api should expose one restore-receipt status summary instead of only raw receipt lists.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.ProvenanceSummary), "campaign spine server plane api should expose a dedicated provenance summary on the restore receipt status.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.ConflictSummary), "campaign spine server plane api should expose a dedicated conflict summary on the restore receipt status.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.LeadReceiptId), "campaign spine server plane api should expose the lead restore receipt id.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.LeadSubjectId), "campaign spine server plane api should expose the lead restore receipt subject.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.LeadAuthority), "campaign spine server plane api should expose the lead restore receipt authority.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.LeadRecoveryHint), "campaign spine server plane api should expose the lead restore recovery hint.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.RecoveryRoute), "campaign spine server plane api should surface the lead restore recovery route.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.RestoreReceiptStatus.RecoveryActionLabel), "campaign spine server plane api should surface a direct recovery action label for the lead restore route.");
    Assert(workspaceServerPlanePayload.RestoreReceiptStatus.LeadObservedAtUtc > DateTimeOffset.MinValue, "campaign spine server plane api should expose when the lead restore receipt was observed.");
    Assert(workspaceServerPlanePayload.RestoreReceiptStatus.LatestReceiptObservedAtUtc >= workspaceServerPlanePayload.RestoreReceiptStatus.LeadObservedAtUtc, "campaign spine server plane api should expose the freshest restore-receipt observation timestamp.");
    Assert(workspaceServerPlanePayload.RestoreReceiptStatus.StaleOrDriftProvenanceReceiptCount > 0, "campaign spine server plane api should count stale-or-drift provenance receipts explicitly.");
    Assert(workspaceServerPlanePayload.RestoreReceiptStatus.CurrentProvenanceReceiptCount >= 0, "campaign spine server plane api should expose current provenance receipt counts even when every receipt is stale.");
    Assert(workspaceServerPlanePayload.RestoreReceiptStatus.SafeToContinueWithReceiptCount > 0, "campaign spine server plane api should count safe-with-receipt provenance cues explicitly.");
    Assert(workspaceServerPlanePayload.RestoreReceiptStatus.ReviewBeforeContinueConflictCount >= 0, "campaign spine server plane api should expose review-before-continue conflict counts even when every conflict is blocking.");
    Assert(
        string.Equals(workspaceServerPlanePayload.RestoreReceiptStatus.ContinuePosture, "blocked_until_receipt_resolved", StringComparison.Ordinal)
            || string.Equals(workspaceServerPlanePayload.RestoreReceiptStatus.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal)
            || string.Equals(workspaceServerPlanePayload.RestoreReceiptStatus.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal),
        "campaign spine server plane api should expose an explicit continue posture on the restore receipt status summary.");
    Assert(workspaceServerPlanePayload.RestoreProvenanceReceipts.Any(item => string.Equals(item.Surface, "workspace_restore", StringComparison.Ordinal)), "campaign spine server plane api should keep workspace-restore provenance receipts explicit on the bounded workspace projection.");
    Assert(workspaceServerPlanePayload.RestoreProvenanceReceipts.Any(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)), "campaign spine server plane api should keep entitlement-sync provenance receipts explicit on the bounded workspace projection.");
    Assert(
        workspaceServerPlanePayload.RestoreProvenanceReceipts.Any(item =>
            string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
            && !string.IsNullOrWhiteSpace(item.RecoveryHint)),
        "campaign spine server plane api should carry authority-backed entitlement provenance with a concrete recovery hint.");
    Assert(
        workspaceServerPlanePayload.RestoreProvenanceRecoveryReceipts.Any(item =>
            string.Equals(item.RecoveryRoute, "/account/access", StringComparison.Ordinal)
            && (string.Equals(item.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal)
                || string.Equals(item.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal))),
        "campaign spine server plane api should expose recoverable provenance cues with account-access routes and continue posture.");
    Assert(workspaceServerPlanePayload.RestoreConflictReceipts.All(item => !string.IsNullOrWhiteSpace(item.Surface)), "campaign spine server plane api should project a concrete surface on every restore conflict receipt.");
    Assert(
        workspaceServerPlanePayload.RestoreConflictReceipts
            .Where(item => !string.IsNullOrWhiteSpace(item.Kind) && item.Kind.StartsWith("entitlement_", StringComparison.OrdinalIgnoreCase))
            .All(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)),
        "campaign spine server plane api should classify entitlement conflict receipts under the entitlement-sync surface.");
    Assert(
        workspaceServerPlanePayload.RestoreConflictReceipts.Any(item =>
            item.BlocksContinue
            && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)),
        "campaign spine server plane api should keep at least one blocking restore conflict explicitly tied to entitlement sync when replay drift exists.");
    Assert(
        workspaceServerPlanePayload.RestoreConflictReceipts
            .Where(static item => item.BlocksContinue)
            .All(static item => !string.IsNullOrWhiteSpace(item.RecoveryHint)),
        "campaign spine server plane api should attach a concrete recovery hint to every blocking restore conflict receipt.");
    Assert(
        workspaceServerPlanePayload.RestoreConflictReceipts.Any(item =>
            string.Equals(item.Kind, "entitlement_artifact_drift", StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
            && item.BlocksContinue),
        "campaign spine server plane api should emit a blocking entitlement artifact drift receipt when claimed install metadata outruns the replayable artifact receipt.");
    if (workspaceServerPlanePayload.RestoreConflictReceipts.Any(static item => item.BlocksContinue))
    {
        Assert(string.Equals(workspaceServerPlanePayload.NextSafeAction.Label, "Review restore receipts", StringComparison.Ordinal), "campaign spine server plane api should turn blocking restore conflicts into an explicit restore-review next action.");
        Assert(string.Equals(workspaceServerPlanePayload.NextSafeAction.SourceKind, "restore", StringComparison.Ordinal), "campaign spine server plane api should classify restore-driven next actions under the restore source kind.");
    }
    Assert(
        workspaceServerPlanePayload.RestoreConflictReceipts.Count == 0
            || workspaceServerPlanePayload.ContinuityConflicts.Any(item => item.CueId.Contains("restore-conflict:", StringComparison.Ordinal)),
        "campaign spine server plane api should carry restore conflict receipts into continuity conflict cues when conflict evidence exists.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.WorkspaceState.Status), "campaign spine server plane api should expose one bounded visible workspace state.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.WorkspaceState.Label), "campaign spine server plane api should expose a customer-facing workspace-state label.");
    Assert(workspaceServerPlanePayload.WorkspaceState.EvidenceLines.Count >= 1, "campaign spine server plane api should attach evidence lines to the bounded workspace state.");
    Assert(workspaceServerPlanePayload.PrepLibrary.Packets.Count >= 3, "campaign spine server plane api should expose a governed GM prep library compiled from workspace truth.");
    Assert(workspaceServerPlanePayload.PrepLibrary.ReusablePacketCount >= 1, "campaign spine server plane api should expose reusable prep packets for campaign rebinding.");
    Assert(workspaceServerPlanePayload.PrepLibrary.SearchSummary.Contains("Search", StringComparison.Ordinal), "campaign spine server plane api should expose explicit prep-library search posture.");
    Assert(
        workspaceServerPlanePayload.PrepLibrary.Packets.Any(item =>
            item.SearchTerms.Count >= 3
            && (string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal)
                || item.SearchTerms.Any(term => string.Equals(term, "opposition", StringComparison.OrdinalIgnoreCase)))),
        "campaign spine server plane api should expose searchable governed opposition packets.");
    Assert(workspaceServerPlanePayload.PrepLibrary.Packets.Any(item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal) && item.SearchTerms.Any(term => string.Equals(term, "diary", StringComparison.OrdinalIgnoreCase))), "campaign spine server plane api should expose a dedicated diary/contact/heat return-loop packet.");
    Assert(workspaceServerPlanePayload.PrepLibrary.Packets.Any(item => string.Equals(item.Kind, "campaign_memory_packet", StringComparison.Ordinal) && item.SearchTerms.Any(term => string.Equals(term, "memory", StringComparison.OrdinalIgnoreCase))), "campaign spine server plane api should expose a dedicated campaign-memory packet for long-lived return truth.");
    Assert(workspaceServerPlanePayload.PrepLaunches.Count == 0, "campaign spine server plane api should start without any governed prep-launch receipts.");
    Assert(workspaceServerPlanePayload.TravelMode.TravelReadyDeviceCount >= 1, "campaign spine server plane api should expose safehouse/travel readiness for claimed devices.");
    Assert(workspaceServerPlanePayload.TravelMode.PrefetchInventorySummary.Contains("governed prep packet", StringComparison.Ordinal), "campaign spine server plane api should carry prep packets into the bounded prefetch inventory summary.");
    Assert(workspaceServerPlanePayload.TravelMode.Boundaries.Any(item => item.Contains("Install-local caches", StringComparison.OrdinalIgnoreCase)), "campaign spine server plane api should keep travel boundaries explicit.");
    Assert(workspaceServerPlanePayload.TravelPrefetches.Count == 0, "campaign spine server plane api should start without staged travel-prefetch receipts.");
    Assert(workspaceServerPlanePayload.AftermathPackages.Count == 0, "campaign spine server plane api should start without aftermath recap packages.");
    Assert(!string.IsNullOrWhiteSpace(workspaceServerPlanePayload.NextSafeAction.Summary), "campaign spine server plane api should expose one bounded next safe action.");
    var starterWorkspaceResult = await campaignSpineController.SeedStarterWorkspace(CancellationToken.None);
    var starterWorkspacePayload = (starterWorkspaceResult.Result as OkObjectResult)?.Value as CampaignWorkspaceProjection ?? starterWorkspaceResult.Value;
    Assert(starterWorkspacePayload is not null && !string.IsNullOrWhiteSpace(starterWorkspacePayload.WorkspaceId), "campaign spine starter api should return a starter workspace for first session onboarding.");
    Assert(starterWorkspacePayload!.FirstPlayableSession is not null, "campaign spine starter api should return first-session proof on the starter workspace payload.");
    Assert(!string.IsNullOrWhiteSpace(starterWorkspacePayload.FirstPlayableSession!.RuleReadySummary), "campaign spine starter api should return legal-runner proof on the starter workspace payload.");
    Assert(!string.IsNullOrWhiteSpace(starterWorkspacePayload.FirstPlayableSession.ReturnLaneSummary), "campaign spine starter api should return understandable-return proof on the starter workspace payload.");
    Assert(!string.IsNullOrWhiteSpace(starterWorkspacePayload.FirstPlayableSession.CampaignReadySummary), "campaign spine starter api should return campaign-ready proof on the starter workspace payload.");
    var rosterTransferPlanResult = await campaignSpineController.GetMyCampaignWorkspaceRosterTransferPlan(workspaceId, CancellationToken.None);
    var rosterTransferPlanPayload = (rosterTransferPlanResult.Result as OkObjectResult)?.Value as RosterTransferPlannerProjection ?? rosterTransferPlanResult.Value;
    Assert(rosterTransferPlanPayload is not null && string.Equals(rosterTransferPlanPayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine roster-transfer planner api should stay attached to the selected shared campaign view.");
    Assert(rosterTransferPlanPayload!.DossierOptions.Count >= 1, "campaign spine roster-transfer planner api should expose governed dossier choices for the selected workspace.");
    Assert(rosterTransferPlanPayload.TargetGroups.Count >= 1, "campaign spine roster-transfer planner api should expose operator-manageable target groups.");
    Assert(rosterTransferPlanPayload.TargetGroups.Any(item => item.OwnerOptions.Count >= 1), "campaign spine roster-transfer planner api should expose target-owner choices from operator groups.");
    var prepLibraryResult = await campaignSpineController.GetMyCampaignWorkspacePrepLibrary(workspaceId, "opposition", CancellationToken.None);
    var prepLibraryPayload = (prepLibraryResult.Result as OkObjectResult)?.Value as CampaignPrepLibrarySearchResponse ?? prepLibraryResult.Value;
    Assert(prepLibraryPayload is not null && string.Equals(prepLibraryPayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine prep-library api should expose the same stable workspace id.");
    Assert(string.Equals(prepLibraryPayload!.QueryText, "opposition", StringComparison.Ordinal), "campaign spine prep-library api should echo the normalized search query.");
    Assert(prepLibraryPayload.TotalCount >= 1, "campaign spine prep-library api should support search across governed prep packets.");
    Assert(prepLibraryPayload.Items.Any(item => item.Title.Contains("opposition", StringComparison.OrdinalIgnoreCase) || item.SearchTerms.Any(term => term.Contains("opposition", StringComparison.OrdinalIgnoreCase))), "campaign spine prep-library api should return the governed opposition packet for matching search.");
    var prepLibraryDiaryResult = await campaignSpineController.GetMyCampaignWorkspacePrepLibrary(workspaceId, "diary heat", CancellationToken.None);
    var prepLibraryDiaryPayload = (prepLibraryDiaryResult.Result as OkObjectResult)?.Value as CampaignPrepLibrarySearchResponse ?? prepLibraryDiaryResult.Value;
    Assert(prepLibraryDiaryPayload?.Items.Any(item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal)) == true, "campaign spine prep-library api should return the diary/contact/heat return-loop packet for diary+heat search.");
    var prepLibraryMemoryResult = await campaignSpineController.GetMyCampaignWorkspacePrepLibrary(workspaceId, "memory", CancellationToken.None);
    var prepLibraryMemoryPayload = (prepLibraryMemoryResult.Result as OkObjectResult)?.Value as CampaignPrepLibrarySearchResponse ?? prepLibraryMemoryResult.Value;
    Assert(prepLibraryMemoryPayload?.Items.Any(item => string.Equals(item.Kind, "campaign_memory_packet", StringComparison.Ordinal)) == true, "campaign spine prep-library api should return the campaign-memory packet for memory-focused search.");
    var prepLaunchResult = await campaignSpineController.LaunchMyCampaignWorkspacePrepPacket(
        workspaceId,
        new GovernedPrepLaunchRequest(
            PacketId: prepLibraryPayload.Items[0].PacketId,
            TargetRunId: runId,
            TargetSceneId: workspacePayload!.Runs[0].ActiveSceneId,
            Note: "Bind governed opposition truth into the active return lane."),
        CancellationToken.None);
    var prepLaunchPayload = (prepLaunchResult.Result as OkObjectResult)?.Value as GovernedPrepLaunchProjection ?? prepLaunchResult.Value;
    Assert(prepLaunchPayload is not null && string.Equals(prepLaunchPayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine prep-launch api should record a governed packet launch against the selected workspace.");
    Assert(string.Equals(prepLaunchPayload!.PacketId, prepLibraryPayload.Items[0].PacketId, StringComparison.Ordinal), "campaign spine prep-launch api should preserve the governed packet identity.");
    Assert(prepLaunchPayload.Summary.Contains("without recreating local shadow prep notes", StringComparison.OrdinalIgnoreCase), "campaign spine prep-launch api should explain that the target bind avoided local shadow prep notes.");
    var travelPrefetchResult = await campaignSpineController.StageMyCampaignWorkspaceTravelPrefetch(
        workspaceId,
        new TravelPrefetchStageRequest(
            InstallationId: workspaceServerPlanePayload.TravelMode.Devices[0].InstallationId,
            Note: "Stage the bounded offline set for the safehouse lane."),
        CancellationToken.None);
    var travelPrefetchPayload = (travelPrefetchResult.Result as OkObjectResult)?.Value as TravelPrefetchReceiptProjection ?? travelPrefetchResult.Value;
    Assert(travelPrefetchPayload is not null && string.Equals(travelPrefetchPayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine travel-prefetch api should record a claimed-device prefetch receipt against the selected workspace.");
    Assert(travelPrefetchPayload!.PrefetchSummary.Contains("exact offline prefetch set", StringComparison.OrdinalIgnoreCase), "campaign spine travel-prefetch api should describe the staged exact offline set.");
    Assert(travelPrefetchPayload.InventoryLines.Any(item => item.Contains("Governed prep packets", StringComparison.OrdinalIgnoreCase)), "campaign spine travel-prefetch api should name governed prep packets in the staged inventory.");
    var aftermathPackageResult = await campaignSpineController.GenerateMyCampaignWorkspaceAftermathRecapPackage(
        workspaceId,
        new AftermathRecapPackageRequest(
            RunId: runId,
            PackageKind: "session_recap",
            Title: null,
            Note: "Keep next-session aftermath and recap follow-through grounded on the shared return lane."),
        CancellationToken.None);
    var aftermathPackagePayload = (aftermathPackageResult.Result as OkObjectResult)?.Value as AftermathRecapPackageProjection ?? aftermathPackageResult.Value;
    Assert(aftermathPackagePayload is not null && string.Equals(aftermathPackagePayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine aftermath recap api should record a governed recap package against the selected workspace.");
    Assert(aftermathPackagePayload!.Summary.Contains("session recap package", StringComparison.OrdinalIgnoreCase), "campaign spine aftermath recap api should describe the governed recap package it generated.");
    Assert(aftermathPackagePayload.EvidenceLines.Any(item => item.Contains("Continuity:", StringComparison.OrdinalIgnoreCase)), "campaign spine aftermath recap api should carry bounded continuity evidence lines.");
    Assert(string.Equals(aftermathPackagePayload.ArtifactKind, "RecapPackage", StringComparison.Ordinal), "campaign spine aftermath recap api should register governed recap artifacts on the durable registry seam.");
    Assert(string.Equals(aftermathPackagePayload.ArtifactVisibility, "campaign-shared", StringComparison.Ordinal), "campaign spine aftermath recap api should keep campaign-shared visibility attached to recap artifacts.");
    Assert(string.Equals(aftermathPackagePayload.ArtifactTrustTier, "curated", StringComparison.Ordinal), "campaign spine aftermath recap api should keep curated trust posture attached to recap artifacts.");
    Assert(!string.IsNullOrWhiteSpace(aftermathPackagePayload.ProvenanceSummary), "campaign spine aftermath recap api should preserve artifact provenance on the generated package.");
    Assert(!string.IsNullOrWhiteSpace(aftermathPackagePayload.AuditSummary), "campaign spine aftermath recap api should preserve artifact audit posture on the generated package.");
    Assert(aftermathPackagePayload.EvidenceLines.Any(item => item.StartsWith("Registry artifact:", StringComparison.OrdinalIgnoreCase)), "campaign spine aftermath recap api should attach the durable registry artifact evidence line.");
    var downtimeBriefResult = await campaignSpineController.GenerateMyCampaignWorkspaceAftermathRecapPackage(
        workspaceId,
        new AftermathRecapPackageRequest(
            RunId: runId,
            PackageKind: "downtime_brief",
            Title: null,
            Note: "Keep downtime obligations and next-session readiness grounded on the same shared return lane."),
        CancellationToken.None);
    var downtimeBriefPayload = (downtimeBriefResult.Result as OkObjectResult)?.Value as AftermathRecapPackageProjection ?? downtimeBriefResult.Value;
    Assert(downtimeBriefPayload is not null && string.Equals(downtimeBriefPayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine downtime brief api should record a governed downtime packet against the selected workspace.");
    Assert(downtimeBriefPayload!.Summary.Contains("downtime brief", StringComparison.OrdinalIgnoreCase), "campaign spine downtime brief api should describe the governed downtime packet it generated.");
    Assert(downtimeBriefPayload.EvidenceLines.Any(item => item.Contains("Continuity:", StringComparison.OrdinalIgnoreCase)), "campaign spine downtime brief api should carry bounded continuity evidence lines.");
    Assert(string.Equals(downtimeBriefPayload.ArtifactKind, "RecapPackage", StringComparison.Ordinal), "campaign spine downtime brief api should register durable recap artifacts on the same registry seam.");
    var replayTimelineResult = await campaignSpineController.GenerateMyCampaignWorkspaceAftermathRecapPackage(
        workspaceId,
        new AftermathRecapPackageRequest(
            RunId: runId,
            PackageKind: "replay_timeline",
            Title: null,
            Note: "Keep contested-turn replay and return review grounded on the same governed package."),
        CancellationToken.None);
    var replayTimelinePayload = (replayTimelineResult.Result as OkObjectResult)?.Value as AftermathRecapPackageProjection ?? replayTimelineResult.Value;
    Assert(replayTimelinePayload is not null && string.Equals(replayTimelinePayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine replay timeline api should record a governed replay package against the selected workspace.");
    Assert(replayTimelinePayload!.Summary.Contains("replay timeline", StringComparison.OrdinalIgnoreCase), "campaign spine replay timeline api should describe the governed replay package it generated.");
    Assert(string.Equals(replayTimelinePayload.ArtifactKind, "ReplayPackage", StringComparison.Ordinal), "campaign spine replay timeline api should register governed replay artifacts on the durable registry seam.");
    Assert(replayTimelinePayload.EvidenceLines.Any(item => item.Contains("Replay posture:", StringComparison.OrdinalIgnoreCase)), "campaign spine replay timeline api should carry replay posture evidence lines.");
    Assert(!string.IsNullOrWhiteSpace(replayTimelinePayload.ProvenanceSummary), "campaign spine replay timeline api should preserve artifact provenance on the generated replay package.");
    Assert(!string.IsNullOrWhiteSpace(replayTimelinePayload.AuditSummary), "campaign spine replay timeline api should preserve artifact audit posture on the generated replay package.");
    Assert(replayTimelinePayload.EvidenceLines.Any(item => item.StartsWith("Registry artifact:", StringComparison.OrdinalIgnoreCase)), "campaign spine replay timeline api should attach the durable registry artifact evidence line.");
    var refreshedWorkspaceServerPlaneResult = await campaignSpineController.GetMyCampaignWorkspaceServerPlane(workspaceId, CancellationToken.None);
    var refreshedWorkspaceServerPlanePayload = (refreshedWorkspaceServerPlaneResult.Result as OkObjectResult)?.Value as CampaignWorkspaceServerPlaneProjection ?? refreshedWorkspaceServerPlaneResult.Value;
    Assert(refreshedWorkspaceServerPlanePayload?.PrepLaunches.Any(item => string.Equals(item.LaunchId, prepLaunchPayload.LaunchId, StringComparison.Ordinal)) == true, "campaign spine server plane api should project governed prep-launch receipts after launch.");
    Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "prep_launch", StringComparison.Ordinal)) == true, "campaign spine server plane api should add prep-launch receipts into the bounded what-changed packet rail.");
    Assert(refreshedWorkspaceServerPlanePayload?.TravelPrefetches.Any(item => string.Equals(item.ReceiptId, travelPrefetchPayload.ReceiptId, StringComparison.Ordinal)) == true, "campaign spine server plane api should project staged travel-prefetch receipts after staging.");
    Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "travel_prefetch", StringComparison.Ordinal)) == true, "campaign spine server plane api should add staged travel-prefetch receipts into the bounded what-changed packet rail.");
    Assert(refreshedWorkspaceServerPlanePayload?.AftermathPackages.Any(item => string.Equals(item.PackageId, aftermathPackagePayload.PackageId, StringComparison.Ordinal)) == true, "campaign spine server plane api should project aftermath recap packages after generation.");
    Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "aftermath_recap", StringComparison.Ordinal)) == true, "campaign spine server plane api should add aftermath recap packages into the bounded what-changed packet rail.");
    Assert(refreshedWorkspaceServerPlanePayload?.AftermathPackages.Any(item => string.Equals(item.PackageId, downtimeBriefPayload.PackageId, StringComparison.Ordinal)) == true, "campaign spine server plane api should project downtime brief packets after generation.");
    Assert(refreshedWorkspaceServerPlanePayload?.AftermathPackages.Any(item => string.Equals(item.PackageId, replayTimelinePayload.PackageId, StringComparison.Ordinal)) == true, "campaign spine server plane api should project replay timeline packages after generation.");
    Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "replay_package", StringComparison.Ordinal)) == true, "campaign spine server plane api should name replay packages explicitly on the bounded what-changed rail.");
    Assert(refreshedWorkspaceServerPlanePayload?.RecapShelf.Any(item => string.Equals(item.EntryId, replayTimelinePayload.PackageId, StringComparison.Ordinal)) == true, "campaign spine server plane api should attach replay packages to the same richer return shelf.");
    var replayShelfPayload = refreshedWorkspaceServerPlanePayload?.RecapShelf
        .FirstOrDefault(item => string.Equals(item.EntryId, replayTimelinePayload.PackageId, StringComparison.Ordinal));
    Assert(replayShelfPayload is not null, "campaign spine server plane api should project replay packages on the richer recap shelf.");
    Assert(replayShelfPayload?.Audience.Contains("creator", StringComparison.OrdinalIgnoreCase) == true, "campaign spine server plane api should keep replay packages creator-linkable on the shared return shelf.");
    Assert(!string.IsNullOrWhiteSpace(replayShelfPayload?.CreatorPublicationId), "campaign spine server plane api should carry creator-publication linkage on replay shelf entries.");
    Assert(refreshedWorkspaceServerPlanePayload?.FirstPlayableSession is null, "campaign spine server plane api should retire starter-session proof once governed prep, travel, and recap follow-through have landed.");
    Assert(refreshedWorkspaceServerPlanePayload?.NextSessionCarryForward is not null, "campaign spine server plane api should refresh the next-session carry-forward packet after the governed actions land.");
    Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "next_session_carry_forward", StringComparison.Ordinal)) == true, "campaign spine server plane api should project the next-session carry-forward packet on the bounded what-changed rail.");
    Assert(refreshedWorkspaceServerPlanePayload?.CampaignMemory is not null, "campaign spine server plane api should refresh campaign memory after governed follow-through lands.");
    Assert(refreshedWorkspaceServerPlanePayload?.CampaignMemory?.Summary.Contains("governed memory lane", StringComparison.OrdinalIgnoreCase) == true, "campaign spine server plane api should keep the long-lived campaign-memory summary explicit after governed follow-through lands.");
    var runResult = await campaignSpineController.GetMyRun(runId, CancellationToken.None);
    var runPayload = (runResult.Result as OkObjectResult)?.Value as RunProjection ?? runResult.Value;
    Assert(runPayload is not null && string.Equals(runPayload.RunId, runId, StringComparison.Ordinal), "campaign spine api should expose the active run detail.");
    var handoffResult = await campaignSpineController.GetMyBuildLabHandoff(handoffId, CancellationToken.None);
    var handoffPayload = (handoffResult.Result as OkObjectResult)?.Value as BuildLabHandoffProjection ?? handoffResult.Value;
    Assert(handoffPayload is not null && handoffPayload.Title.Contains("build path", StringComparison.OrdinalIgnoreCase), "campaign spine api should expose the customer-facing build-path handoff detail.");
    Assert(!string.IsNullOrWhiteSpace(handoffPayload!.CampaignReturnSummary), "campaign spine handoff api should keep campaign return truth attached.");
    Assert(handoffPayload.TradeoffLines[0].Contains("campaign-safe output", StringComparison.OrdinalIgnoreCase), "campaign spine handoff api should preserve exact output posture.");
    Assert(handoffPayload.ProgressionOutcomes[0].Contains("25 / 50 / 100 Karma checkpoints", StringComparison.Ordinal), "campaign spine handoff api should preserve the planner checkpoints directly on the handoff payload.");
    Assert(!string.IsNullOrWhiteSpace(handoffPayload.PlannerCoverageSummary), "campaign spine handoff api should preserve planner-coverage summary directly on the handoff payload.");
    Assert(handoffPayload.PlannerCoverageLines?.FirstOrDefault()?.Contains("Campaign continuity:", StringComparison.Ordinal) == true, "campaign spine handoff api should preserve campaign continuity planner coverage directly on the handoff payload.");
    var rulesResult = await campaignSpineController.GetMyRulesNavigatorAnswer(rulesEntryId, CancellationToken.None);
    var rulesPayload = (rulesResult.Result as OkObjectResult)?.Value as RulesNavigatorAnswerProjection ?? rulesResult.Value;
    Assert(rulesPayload is not null && rulesPayload.EvidenceLines.Count >= 1, "campaign spine api should expose grounded rule-environment evidence.");
    Assert(rulesPayload?.Diffs?.Count >= 2, "campaign spine api should expose grounded before-and-after rule-environment diffs.");
    Assert(rulesPayload?.Diffs?[0].AfterSummary.Contains(rulesPayload.ProvenanceLabel.Split(" · ").Last(), StringComparison.Ordinal) == true, "campaign spine api should keep the active compatibility fingerprint visible in the first rules diff.");
    Assert(rulesPayload?.Studio is not null, "campaign spine api should expose a first-class rule-environment studio projection.");
    Assert(string.Equals(rulesPayload?.Studio?.CurrentStage, RuleEnvironmentLifecycleStages.CampaignApproved, StringComparison.Ordinal), "campaign spine api should mark workspace rules as campaign-approved before broader promotion.");
    Assert(string.Equals(rulesPayload?.Studio?.PromotionTargetStage, RuleEnvironmentLifecycleStages.Published, StringComparison.Ordinal), "campaign spine api should keep the next workspace rules promotion on the published rail.");
    Assert(rulesPayload?.Studio?.RollbackSummary.Contains(rulesPayload.ProvenanceLabel.Split(" · ").Last(), StringComparison.Ordinal) == true, "campaign spine api should keep rollback posture tied to the same grounded compatibility fingerprint.");
    var publicationResult = await campaignSpineController.GetMyCreatorPublication(publicationId, CancellationToken.None);
    var publicationPayload = (publicationResult.Result as OkObjectResult)?.Value as CreatorPublicationProjection ?? publicationResult.Value;
    Assert(publicationPayload is not null && string.Equals(publicationPayload.PublicationId, publicationId, StringComparison.Ordinal), "campaign spine api should expose creator-publication posture from the same campaign truth.");
    Assert(!string.IsNullOrWhiteSpace(publicationPayload!.NextSafeAction), "campaign spine api should keep the creator-publication next step attached.");
    Assert(!string.IsNullOrWhiteSpace(publicationPayload.CampaignReturnSummary), "campaign spine api should keep creator-publication return truth attached.");
    Assert(!string.IsNullOrWhiteSpace(publicationPayload.SupportClosureSummary), "campaign spine api should keep creator-publication support closure attached.");
    var missingWorkspaceResult = await campaignSpineController.GetMyCampaignWorkspace("workspace-missing", CancellationToken.None);
    Assert(missingWorkspaceResult.Result is NotFoundResult, "campaign spine workspace api should return 404 when the signed-in workspace does not exist.");
    var missingWorkspaceServerPlaneResult = await campaignSpineController.GetMyCampaignWorkspaceServerPlane("workspace-missing", CancellationToken.None);
    Assert(missingWorkspaceServerPlaneResult.Result is NotFoundResult, "campaign spine server plane api should return 404 when the signed-in workspace does not exist.");
    var accountSupportPage = await accountController.AccountPage(section: "support", caseId: null, CancellationToken.None) as ViewResult;
    var accountSupportModel = accountSupportPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountSupportModel?.CurrentSection, "support", StringComparison.Ordinal), "account support route should render the support section.");
    Assert(string.Equals(accountSupportModel?.Chrome.Title, "Account · Support", StringComparison.Ordinal), "account support route should project its own chrome title.");
    Assert(accountSupportModel?.SignedInTrustStatus is not null, "account support route should keep the signed-in trust panel visible beside tracked support.");
    var accountSupportDetailPage = await accountController.AccountPage(section: "support", caseId: supportCase.CaseId, CancellationToken.None) as ViewResult;
    var accountSupportDetailModel = accountSupportDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountSupportDetailModel?.SelectedSupportCase?.CaseId, supportCase.CaseId, StringComparison.Ordinal), "account support detail route should load the selected tracked case.");
    Assert(accountSupportDetailModel?.SelectedSupportCaseSummary is not null, "account support detail route should project a support lifecycle summary for the tracked case.");
    Assert(string.Equals(accountSupportDetailModel!.SelectedSupportCaseSummary!.StatusLabel, "Notified", StringComparison.Ordinal), "account support detail should humanize notified support closure for the signed-in reporter.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.FixedReleaseLabel?.Contains("preview", StringComparison.OrdinalIgnoreCase) == true, "account support detail should tie closure truth to the released reporter channel.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.ClosureSummary.Contains("closure notice", StringComparison.OrdinalIgnoreCase), "account support detail should explain that the reporter-facing closure already went out.");
    Assert(!accountSupportDetailModel.SelectedSupportCaseSummary.CanVerifyFix, "account support detail should hold back verification until the linked install is actually on the released fix.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.VerificationSummary.Contains("Update it to preview 0.6.3-smoke first", StringComparison.Ordinal), "account support detail should explain the exact linked-install update required before verification.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.InstallReadinessSummary.Contains("preview 0.6.3-smoke", StringComparison.Ordinal), "account support detail should project the reporter-ready install target.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.FollowUpLaneSummary.Contains("Account > Support", StringComparison.Ordinal), "account support detail should keep the signed-in follow-up lane explicit.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.ReleaseProgressSummary.Contains("closure notice", StringComparison.OrdinalIgnoreCase), "account support detail should project the user-facing release progress summary.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.AffectedInstallSummary?.Contains("install-smoke-001", StringComparison.Ordinal) == true, "account support detail should keep the affected install attached to the tracked case.");
    Assert(accountSupportDetailModel.SelectedSupportCaseSummary.TimelineHighlights.Count >= 1, "account support detail should project timeline highlights through the shared presenter.");
    var authenticatedDownloadsPage = await authenticatedLandingController.DownloadsPage(CancellationToken.None) as ViewResult;
    var authenticatedDownloadsModel = authenticatedDownloadsPage?.Model as DownloadsPageViewModel;
    Assert(authenticatedDownloadsModel?.SignedInStatus is not null, "signed-in downloads should project install-specific trust status.");
    Assert(authenticatedDownloadsModel?.TrustPulse is not null, "downloads should surface the weekly public trust pulse next to the release shelf.");
    Assert(string.Equals(authenticatedDownloadsModel!.SignedInStatus!.Heading, "Update your linked install", StringComparison.Ordinal), "signed-in downloads should tell the reporter to update the linked install before verification when the fix is on a newer build.");
    Assert(authenticatedDownloadsModel.SignedInStatus.Summary.Contains("preview 0.6.3-smoke", StringComparison.Ordinal), "signed-in downloads should project the exact reporter-ready build in the trust panel.");
    Assert(authenticatedDownloadsModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Recommended for this install", StringComparison.Ordinal) && row.Value.Contains("preview 0.6.3-smoke", StringComparison.Ordinal) && row.Value.Contains("0.6.1-smoke", StringComparison.Ordinal)), "signed-in downloads should explain both the tracked fix target and the current public shelf for this linked install.");
    Assert(authenticatedDownloadsModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Install posture", StringComparison.Ordinal) && row.Value.Contains("Update it to preview 0.6.3-smoke first", StringComparison.Ordinal)), "signed-in downloads should surface the install-specific posture from the support readiness summary.");
    Assert(authenticatedDownloadsModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Fix availability", StringComparison.Ordinal) && row.Value.Contains("preview 0.6.3-smoke", StringComparison.Ordinal)), "signed-in downloads should surface fix availability for the linked install instead of leaving it implicit in prose.");
    Assert(authenticatedDownloadsModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && row.Value.Contains("Update it to preview 0.6.3-smoke first", StringComparison.Ordinal)), "signed-in downloads should surface the install-specific caution lane beside the fix target.");
    Assert(authenticatedDownloadsModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Adoption health", StringComparison.Ordinal) && row.Value.Contains("Current local edge proof passed", StringComparison.Ordinal)), "signed-in downloads should surface adoption health directly inside the install-specific trust panel.");
    Assert(authenticatedDownloadsModel.TrustPulse!.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "downloads should explain the current access posture beside the release shelf.");
    Assert(authenticatedDownloadsModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Adoption health", StringComparison.Ordinal) && row.Value.Contains("Current local edge proof passed", StringComparison.Ordinal)), "downloads should surface current adoption evidence beside the release shelf.");
    Assert(authenticatedDownloadsModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Launch readiness", StringComparison.Ordinal) && ContainsLaunchReadinessSignal(row.Value)), "downloads should surface launch-readiness posture beside the release shelf.");
    Assert(authenticatedDownloadsModel.TrustPulse!.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && row.Value.Contains("current longest pole", StringComparison.OrdinalIgnoreCase)), "downloads should surface the weekly caution lane from the trust pulse.");
    var authenticatedHelpPage = await authenticatedLandingController.HelpPage(CancellationToken.None) as ViewResult;
    var authenticatedHelpModel = authenticatedHelpPage?.Model as TrustPageViewModel;
    Assert(authenticatedHelpModel?.SignedInStatus is not null, "signed-in help should project install-specific trust status.");
    Assert(authenticatedHelpModel?.TrustPulse is not null, "help should surface the weekly public trust pulse.");
    Assert(authenticatedHelpModel?.PrivacyBoundary is not null, "help should surface the privacy-boundary projection next to the grounded help lanes.");
    Assert(authenticatedHelpModel!.SignedInStatus!.Summary.Contains("preview 0.6.3-smoke", StringComparison.Ordinal), "signed-in help should carry the same install-specific follow-through summary.");
    Assert(authenticatedHelpModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Fix availability", StringComparison.Ordinal) && row.Value.Contains("preview 0.6.3-smoke", StringComparison.Ordinal)), "signed-in help should surface install-specific fix availability next to the trust guidance.");
    Assert(authenticatedHelpModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && row.Value.Contains("Update it to preview 0.6.3-smoke first", StringComparison.Ordinal)), "signed-in help should surface install-specific caution next to the trust guidance.");
    Assert(authenticatedHelpModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Adoption health", StringComparison.Ordinal) && row.Value.Contains("weekly snapshots", StringComparison.OrdinalIgnoreCase)), "signed-in help should carry measured adoption history inside the install-specific trust panel.");
    Assert(authenticatedHelpModel.TrustPulse!.MicroProof.Any(static item => item.Contains("campaign OS indispensable", StringComparison.OrdinalIgnoreCase)), "help should surface the current next-checkpoint question in the weekly trust pulse.");
    Assert(authenticatedHelpModel.TrustPulse.TrendSamples.Count > 1, "help should surface measured progress points alongside the weekly pulse summary.");
    Assert(authenticatedHelpModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Provider-route stewardship", StringComparison.Ordinal) && row.Value.Contains("Pilot defaults are governed", StringComparison.Ordinal)), "help should surface provider-route stewardship on the weekly trust pulse.");
    Assert(authenticatedHelpModel.PrivacyBoundary!.SurfaceRules.Any(static rule => string.Equals(rule.Label, "Provider-backed help", StringComparison.Ordinal)), "help should keep the provider-backed help boundary explicit.");
    var authenticatedNowPage = await authenticatedLandingController.NowPage(CancellationToken.None) as ViewResult;
    var authenticatedNowModel = authenticatedNowPage?.Model as NowPageViewModel;
    Assert(authenticatedNowModel?.SignedInStatus is not null, "signed-in current-release page should project install-specific trust status.");
    Assert(authenticatedNowModel?.TrustPulse is not null, "current-release should surface the weekly public trust pulse.");
    Assert(authenticatedNowModel!.SignedInStatus!.Rows.Any(static row => string.Equals(row.Label, "Support follow-through", StringComparison.Ordinal) && row.Value.Contains("Closed with notice", StringComparison.Ordinal)), "signed-in current-release page should surface the current support follow-through stage.");
    Assert(authenticatedNowModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Fix availability", StringComparison.Ordinal) && row.Value.Contains("preview 0.6.3-smoke", StringComparison.Ordinal)), "signed-in current-release page should surface install-specific fix availability.");
    Assert(authenticatedNowModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && row.Value.Contains("Update it to preview 0.6.3-smoke first", StringComparison.Ordinal)), "signed-in current-release page should surface install-specific caution.");
    Assert(authenticatedNowModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Adoption health", StringComparison.Ordinal) && row.Value.Contains("trust routes", StringComparison.OrdinalIgnoreCase)), "signed-in current-release page should surface adoption health next to the install-specific trust rows.");
    Assert(authenticatedNowModel.TrustPulse!.Rows.Any(static row => string.Equals(row.Label, "Recommended now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "current-release should explain who can get the recommended build now.");
    Assert(authenticatedNowModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Closure health", StringComparison.Ordinal) && row.Value.Contains("waiting closure", StringComparison.OrdinalIgnoreCase)), "current-release should surface closure-health follow-through in the weekly trust pulse.");
    Assert(authenticatedNowModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Progress trend", StringComparison.Ordinal) && row.Value.Contains("Trend window", StringComparison.OrdinalIgnoreCase)), "current-release should surface trend window movement in the weekly trust pulse.");
    Assert(authenticatedNowModel.TrustPulse.TrendSamples.Count > 1, "current-release should surface measured progress points alongside the weekly pulse summary.");
    Assert(authenticatedNowModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Launch readiness", StringComparison.Ordinal) && ContainsLaunchReadinessSignal(row.Value)), "current-release should surface launch-readiness posture on the weekly trust pulse.");
    Assert(authenticatedNowModel.TrustPulse.Rows.Any(static row => string.Equals(row.Label, "Provider-route stewardship", StringComparison.Ordinal) && row.Value.Contains("Pilot defaults are governed", StringComparison.Ordinal)), "current-release should surface provider-route stewardship on the weekly trust pulse.");
    var fixedReadyRefreshResult = installLinkingController.RefreshGrant(new RefreshInstallationGrantRequestDto(
        InstallationId: redeemPayload.Installation.InstallationId,
        AccessToken: currentGrantAccessToken,
        HeadId: "avalonia",
        ApplicationVersion: "0.6.3-smoke",
        ChannelId: "preview",
        Platform: "linux",
        Arch: "x64",
        PublicKey: "smoke-public-key-v3",
        HostLabel: "smoke-host"));
    var fixedReadyRefreshPayload = (fixedReadyRefreshResult.Result as OkObjectResult)?.Value as RefreshInstallationGrantResponseDto;
    Assert(fixedReadyRefreshPayload is not null && fixedReadyRefreshPayload.Rotated, "linked install refresh should move the signed-in install onto the reporter-ready fix build.");
    currentGrantAccessToken = fixedReadyRefreshPayload!.Grant.AccessToken;
    var readyToVerifyAccountDetailPage = await accountController.AccountPage(section: "support", caseId: supportCase.CaseId, CancellationToken.None) as ViewResult;
    var readyToVerifyAccountDetailModel = readyToVerifyAccountDetailPage?.Model as AccountPageViewModel;
    Assert(readyToVerifyAccountDetailModel?.SelectedSupportCaseSummary?.CanVerifyFix == true, "account support detail should reopen the verification controls once the linked install reaches the fixed build.");
    Assert(readyToVerifyAccountDetailModel?.SelectedSupportCaseSummary?.FixReadyOnLinkedInstall == true, "account support detail should mark the linked install as ready to verify.");
    Assert(readyToVerifyAccountDetailModel?.SelectedSupportCaseSummary?.VerificationSummary.Contains("fix worked here", StringComparison.OrdinalIgnoreCase) == true, "account support detail should return the reporter verification loop once the linked install is current.");
    var readyToVerifyDownloadsPage = await authenticatedLandingController.DownloadsPage(CancellationToken.None) as ViewResult;
    var readyToVerifyDownloadsModel = readyToVerifyDownloadsPage?.Model as DownloadsPageViewModel;
    Assert(string.Equals(readyToVerifyDownloadsModel?.SignedInStatus?.Heading, "Your linked install can verify a fix now", StringComparison.Ordinal), "signed-in downloads should switch from update-needed to verification-ready once the linked install matches the fix build.");
    Assert(readyToVerifyDownloadsModel?.SignedInStatus?.Rows.Any(static row => string.Equals(row.Label, "Install posture", StringComparison.Ordinal) && row.Value.Contains("fix worked here", StringComparison.OrdinalIgnoreCase)) == true, "signed-in downloads should turn the install posture row into a verification-ready summary once the linked install reaches the tracked fix.");
    Assert(readyToVerifyDownloadsModel?.SignedInStatus?.Rows.Any(static row => string.Equals(row.Label, "Fix availability", StringComparison.Ordinal) && row.Value.Contains("can verify", StringComparison.OrdinalIgnoreCase)) == true, "signed-in downloads should turn fix availability into a verification-ready statement once the linked install reaches the tracked fix.");
    Assert(readyToVerifyDownloadsModel?.SignedInStatus?.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && row.Value.Contains("No extra caution", StringComparison.OrdinalIgnoreCase)) == true, "signed-in downloads should lower the caution lane once the linked install reaches the tracked fix.");
    Assert(string.Equals(readyToVerifyDownloadsModel?.SignedInStatus?.PrimaryAction.Label, "Verify fix on this install", StringComparison.Ordinal), "signed-in downloads should switch the primary trust action from a generic timeline link to a direct verify-fix action once the linked install is ready.");
    Assert(string.Equals(readyToVerifyDownloadsModel?.SignedInStatus?.PrimaryAction.Href, readyToVerifyAccountDetailModel!.SelectedSupportCaseSummary!.DetailHref, StringComparison.Ordinal), "signed-in downloads should route the verification-ready trust action straight back to the tracked case detail.");
    var readyToVerifyAssistant = await supportCasesController.AskAssistant(
        new SupportAssistantRequest(
            Query: "Can I verify the preview fix on my linked install now?",
            InstallationId: "install-smoke-001"),
        CancellationToken.None);
    var readyToVerifyAssistantPayload = (readyToVerifyAssistant.Result as OkObjectResult)?.Value as SupportAssistantResponse;
    Assert(readyToVerifyAssistantPayload is not null, "support assistant should answer verification-ready questions for signed-in reporters.");
    Assert(readyToVerifyAssistantPayload!.Answer.Contains("Use the verification buttons", StringComparison.Ordinal), "support assistant should explicitly ask the reporter to verify the fix once the linked install is ready.");
    Assert(readyToVerifyAssistantPayload.Actions.Any(static item => string.Equals(item.ActionId, "verify_fix_on_case", StringComparison.Ordinal)), "support assistant should surface a direct fix-verification action once the linked install is ready.");
    Assert(readyToVerifyAssistantPayload.Actions.Any(item => string.Equals(item.Href, readyToVerifyAccountDetailModel!.SelectedSupportCaseSummary!.DetailHref, StringComparison.Ordinal)), "support assistant should route the verification-ready action back to the tracked case detail.");
    var verifiedFixedResult = await supportCasesController.VerifyReporterFix(
        supportCase.CaseId,
        new SupportCaseVerificationRequest(
            Outcome: SupportCaseVerificationStates.ConfirmedFixed,
            Note: "Preview 0.6.3-smoke fixed it here."),
        CancellationToken.None);
    var verifiedFixedPayload = (verifiedFixedResult.Result as OkObjectResult)?.Value as SupportCaseProjection ?? verifiedFixedResult.Value;
    Assert(verifiedFixedPayload is not null && string.Equals(verifiedFixedPayload.ReporterVerificationState, SupportCaseVerificationStates.ConfirmedFixed, StringComparison.Ordinal), "reporter verification should record a confirmed-fixed outcome.");
    Assert(verifiedFixedPayload!.ReporterVerifiedAtUtc is not null, "reporter verification should stamp the verification time.");
    var verifiedFixedAccountDetailPage = await accountController.AccountPage(section: "support", caseId: supportCase.CaseId, CancellationToken.None) as ViewResult;
    var verifiedFixedAccountDetailModel = verifiedFixedAccountDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(verifiedFixedAccountDetailModel?.SelectedSupportCaseSummary?.StageLabel, "Closed and confirmed", StringComparison.Ordinal), "confirmed fixes should project a closed-and-confirmed support stage.");
    Assert(verifiedFixedAccountDetailModel?.SelectedSupportCaseSummary?.VerificationSummary.Contains("0.6.3-smoke", StringComparison.Ordinal) == true, "confirmed fixes should project the reporter-visible fixed release in the verification summary.");
    Assert(verifiedFixedAccountDetailModel?.SelectedSupportCaseSummary?.CanVerifyFix == false, "confirmed fixes should retire the reporter verification call-to-action.");

    SupportCaseProjection reopenCase = supportCases.Submit(
        linkedUser.UserId,
        "subject.demo",
        new SupportCaseSubmitRequest(
            Kind: SupportCaseKinds.BugReport,
            Title: "Campaign recap still loses roster context",
            Summary: "The recap lane still drops the active roster after the update.",
            Detail: "Returning from the update still loses the selected roster on the campaign recap screen.",
            InstallationId: "install-smoke-001",
            ApplicationVersion: "0.6.2-smoke",
            ReleaseChannel: "preview",
            HeadId: "avalonia",
            Platform: "linux",
            Arch: "x64",
            Source: SupportCaseSourceKinds.HubAccount));
    var reopenReleasedResult = supportAutomationController.Transition(
        reopenCase.CaseId,
        new SupportCaseTransitionRequest(
            TargetStatus: SupportCaseStatuses.ReleasedToReporterChannel,
            Note: "Fix is live on preview 0.6.4-smoke.",
            FixedVersion: "0.6.4-smoke",
            FixedChannel: "preview",
            Actor: "fleet"));
    var reopenReleasedPayload = (reopenReleasedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(reopenReleasedPayload is not null && string.Equals(reopenReleasedPayload.Status, SupportCaseStatuses.ReleasedToReporterChannel, StringComparison.Ordinal), "secondary support case should enter reporter-facing release state before reopen verification.");
    var reopenReadyRefreshResult = installLinkingController.RefreshGrant(new RefreshInstallationGrantRequestDto(
        InstallationId: redeemPayload.Installation.InstallationId,
        AccessToken: currentGrantAccessToken,
        HeadId: "avalonia",
        ApplicationVersion: "0.6.4-smoke",
        ChannelId: "preview",
        Platform: "linux",
        Arch: "x64",
        PublicKey: "smoke-public-key-v4",
        HostLabel: "smoke-host"));
    var reopenReadyRefreshPayload = (reopenReadyRefreshResult.Result as OkObjectResult)?.Value as RefreshInstallationGrantResponseDto;
    Assert(reopenReadyRefreshPayload is not null && reopenReadyRefreshPayload.Rotated, "secondary verification path should be able to move the linked install onto the next reporter-ready fix build.");
    currentGrantAccessToken = reopenReadyRefreshPayload!.Grant.AccessToken;
    var stillBrokenResult = await supportCasesController.VerifyReporterFix(
        reopenCase.CaseId,
        new SupportCaseVerificationRequest(
            Outcome: SupportCaseVerificationStates.StillBroken,
            Note: "The recap still drops the roster after the update."),
        CancellationToken.None);
    var stillBrokenPayload = (stillBrokenResult.Result as OkObjectResult)?.Value as SupportCaseProjection ?? stillBrokenResult.Value;
    Assert(stillBrokenPayload is not null && string.Equals(stillBrokenPayload.Status, SupportCaseStatuses.AwaitingEvidence, StringComparison.Ordinal), "still-broken verification should reopen the case into awaiting_evidence.");
    Assert(string.Equals(stillBrokenPayload!.ReporterVerificationState, SupportCaseVerificationStates.StillBroken, StringComparison.Ordinal), "still-broken verification should record the reporter outcome.");
    var reopenedAccountDetailPage = await accountController.AccountPage(section: "support", caseId: reopenCase.CaseId, CancellationToken.None) as ViewResult;
    var reopenedAccountDetailModel = reopenedAccountDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(reopenedAccountDetailModel?.SelectedSupportCaseSummary?.StageLabel, "Needs follow-up", StringComparison.Ordinal), "still-broken verification should project a follow-up stage on the account support detail.");
    Assert(reopenedAccountDetailModel?.SelectedSupportCaseSummary?.VerificationSummary.Contains("still broken", StringComparison.OrdinalIgnoreCase) == true, "still-broken verification should project the reporter note on the account support detail.");
    Assert(reopenedAccountDetailModel?.SelectedSupportCaseSummary?.CanVerifyFix == false, "reopened follow-up cases should not keep the same verification call-to-action until another fix reaches the reporter.");
    SupportCaseProjection orphanedInstallCase = supportCases.Submit(
        linkedUser.UserId,
        "subject.demo",
        new SupportCaseSubmitRequest(
            Kind: SupportCaseKinds.BugReport,
            Title: "Old beta install is no longer linked",
            Summary: "The affected install was replaced before the fix reached the reporter lane.",
            Detail: "The original beta install was retired, so this account no longer has the affected device linked.",
            InstallationId: "install-missing-404",
            ApplicationVersion: "0.5.0-smoke",
            ReleaseChannel: "beta",
            HeadId: "web",
            Platform: "windows",
            Arch: "arm64",
            Source: SupportCaseSourceKinds.HubAccount));
    var orphanedInstallReleasedResult = supportAutomationController.Transition(
        orphanedInstallCase.CaseId,
        new SupportCaseTransitionRequest(
            TargetStatus: SupportCaseStatuses.ReleasedToReporterChannel,
            Note: "Fix is ready on preview 0.6.5-smoke.",
            FixedVersion: "0.6.5-smoke",
            FixedChannel: "preview",
            Actor: "fleet"));
    var orphanedInstallReleasedPayload = (orphanedInstallReleasedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(orphanedInstallReleasedPayload is not null && string.Equals(orphanedInstallReleasedPayload.Status, SupportCaseStatuses.ReleasedToReporterChannel, StringComparison.Ordinal), "orphaned-install support case should enter the reporter release state for relink testing.");
    var orphanedInstallNotifiedResult = supportAutomationController.NotifyReporter(
        orphanedInstallCase.CaseId,
        new SupportCaseNotificationRequest(
            Note: "Closure notice sent after the preview 0.6.5-smoke release reached the reporter lane.",
            Channel: "account",
            Actor: "fleet"));
    var orphanedInstallNotifiedPayload = (orphanedInstallNotifiedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(orphanedInstallNotifiedPayload is not null && string.Equals(orphanedInstallNotifiedPayload.Status, SupportCaseStatuses.UserNotified, StringComparison.Ordinal), "orphaned-install support case should enter the reporter notification state for relink testing.");
    var orphanedAccountDetailPage = await accountController.AccountPage(section: "support", caseId: orphanedInstallCase.CaseId, CancellationToken.None) as ViewResult;
    var orphanedAccountDetailModel = orphanedAccountDetailPage?.Model as AccountPageViewModel;
    Assert(orphanedAccountDetailModel?.SelectedSupportCaseSummary?.NeedsLinkedInstall == true, "support detail should require relinking when no current install matches the affected device context.");
    Assert(orphanedAccountDetailModel?.SelectedSupportCaseSummary?.CanVerifyFix == false, "support detail should not reopen fix verification when the affected install is no longer linked.");
    Assert(orphanedAccountDetailModel?.SelectedSupportCaseSummary?.InstallReadinessSummary.Contains("not currently linked here", StringComparison.OrdinalIgnoreCase) == true, "support detail should explain that the affected install must be relinked instead of silently choosing another device.");
    var orphanedVerifyResult = await supportCasesController.VerifyReporterFix(
        orphanedInstallCase.CaseId,
        new SupportCaseVerificationRequest(
            Outcome: SupportCaseVerificationStates.ConfirmedFixed,
            Note: "Tried to verify from the wrong device."),
        CancellationToken.None);
    var orphanedVerifyProblem = orphanedVerifyResult.Result as ObjectResult;
    Assert(orphanedVerifyProblem?.StatusCode == StatusCodes.Status409Conflict, "support verification api should reject fix confirmation when the affected install is no longer linked.");
    Assert((orphanedVerifyProblem?.Value as ProblemDetails)?.Detail?.Contains("not currently linked here", StringComparison.OrdinalIgnoreCase) == true, "support verification api should explain that the affected install must be relinked before verification.");
    var accountAccessPage = await accountController.AccountPage(section: "access", caseId: null, CancellationToken.None) as ViewResult;
    var accountAccessModel = accountAccessPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountAccessModel?.CurrentSection, "access", StringComparison.Ordinal), "account access route should render the devices-and-access section.");
    Assert(string.Equals(accountAccessModel?.Chrome.Title, "Account · Devices & access", StringComparison.Ordinal), "account access route should project its own chrome title.");
    Assert(accountAccessModel?.SignedInTrustStatus is not null, "account access route should keep the install-specific trust panel visible on the device surface.");
    Assert(accountAccessModel?.SignedInTrustStatus?.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)) == true, "account access route should keep the current access posture visible next to linked-install details.");
    Assert(accountAccessModel?.EntitlementSyncReceipts is not null, "account access route should project standalone entitlement-sync receipts next to devices and access posture.");
    Assert(accountAccessModel?.EntitlementSyncReceipts?.ProvenanceRecoveryReceipts.Count >= 1, "account access route should keep entitlement-sync provenance recovery cues visible.");
    Assert(accountAccessModel?.EntitlementSyncReceipts?.ConflictReceipts.Any(item => item.BlocksContinue && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)) == true, "account access route should keep blocking entitlement-sync conflicts explicit and scoped.");
    Assert(!string.IsNullOrWhiteSpace(accountAccessModel?.EntitlementSyncReceipts?.ReceiptStatus.ProvenanceSummary), "account access route should project the entitlement-sync provenance summary.");
    Assert(!string.IsNullOrWhiteSpace(accountAccessModel?.EntitlementSyncReceipts?.ReceiptStatus.ConflictSummary), "account access route should project the entitlement-sync conflict summary.");
    Assert(!string.IsNullOrWhiteSpace(accountAccessModel?.EntitlementSyncReceipts?.ReceiptStatus.RecoverySummary), "account access route should project the entitlement-sync recovery summary.");
    Assert(!string.IsNullOrWhiteSpace(accountAccessModel?.EntitlementSyncReceipts?.ReceiptStatus.RecoveryActionLabel), "account access route should project the entitlement-sync recovery action label.");
    Assert(accountAccessModel?.EntitlementSyncReceipts?.ReceiptStatus.LatestReceiptObservedAtUtc >= accountAccessModel?.EntitlementSyncReceipts?.ReceiptStatus.LeadObservedAtUtc, "account access route should keep the latest entitlement-sync receipt observation timestamp visible.");
    var accountWorkspaceDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, workspaceId: workspaceId) as ViewResult;
    var accountWorkspaceDetailModel = accountWorkspaceDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountWorkspaceDetailModel?.CurrentSection, "work", StringComparison.Ordinal), "account workspace detail route should land inside the work section.");
    Assert(string.Equals(accountWorkspaceDetailModel?.SelectedWorkspace?.WorkspaceId, workspaceId, StringComparison.Ordinal), "account workspace detail route should load the selected shared campaign view.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane is not null, "account workspace detail route should project the bounded workspace server plane.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspace?.NextSessionCarryForward is not null, "account workspace detail route should keep the shared next-session carry-forward projection attached to the selected workspace.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.NextSessionCarryForward is not null, "account workspace detail route should project the next-session carry-forward packet through the workspace server plane.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspace?.CampaignMemory is not null, "account workspace detail route should keep the shared campaign-memory projection attached to the selected workspace.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.CampaignMemory is not null, "account workspace detail route should project the bounded campaign-memory packet through the workspace server plane.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.SupportClosures.Count >= 1, "account workspace detail route should expose support-closure cues from the workspace server plane.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.DecisionNotices.Count >= 1, "account workspace detail route should expose bounded decision notices from the workspace server plane.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.DecisionNotices.Any(item => string.Equals(item.Kind, "portable_exchange", StringComparison.Ordinal)) == true, "account workspace detail route should keep portable exchange visible on the bounded workspace server plane.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreProvenanceReceipts.Count == restorePayload!.ProvenanceReceipts.Count, "account workspace detail route should project restore provenance receipts from the same restore packet.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreProvenanceRecoveryReceipts.Count == restorePayload.ProvenanceReceipts.Count, "account workspace detail route should project recovery cues for every restore provenance receipt.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts.Count == restorePayload.ConflictReceipts.Count, "account workspace detail route should project restore conflict receipts from the same restore packet.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.LeadReceiptId), "account workspace detail route should keep the lead restore receipt id visible on the selected workspace.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.LeadSubjectId), "account workspace detail route should keep the lead restore receipt subject visible on the selected workspace.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.LeadAuthority), "account workspace detail route should keep the lead restore receipt authority visible on the selected workspace.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.LeadRecoveryHint), "account workspace detail route should keep the lead restore recovery hint visible on the selected workspace.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.ProvenanceSummary), "account workspace detail route should keep the restore provenance summary visible on the selected workspace.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.ConflictSummary), "account workspace detail route should keep the restore conflict summary visible on the selected workspace.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.RecoveryActionLabel), "account workspace detail route should keep the restore recovery action label visible on the selected workspace.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.SafeToContinueWithReceiptCount > 0, "account workspace detail route should keep safe-with-receipt provenance counts explicit on the selected workspace.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreReceiptStatus.ReviewBeforeContinueConflictCount >= 0, "account workspace detail route should keep review-before-continue conflict counts explicit on the selected workspace.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreProvenanceReceipts.Any(item => string.Equals(item.Surface, "workspace_restore", StringComparison.Ordinal)) == true, "account workspace detail route should keep workspace-restore provenance explicit.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreProvenanceReceipts.Any(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)) == true, "account workspace detail route should keep entitlement-sync provenance explicit.");
    Assert(
        accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreProvenanceReceipts.Any(item =>
            string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
            && !string.IsNullOrWhiteSpace(item.RecoveryHint)) == true,
        "account workspace detail route should keep authority-backed entitlement provenance and recovery hints visible on the selected workspace.");
    Assert(
        accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreProvenanceRecoveryReceipts.Any(item =>
            string.Equals(item.RecoveryRoute, "/account/access", StringComparison.Ordinal)
            && (string.Equals(item.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal)
                || string.Equals(item.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal))) == true,
        "account workspace detail route should keep provenance recovery routes and continue posture visible on the selected workspace.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts.All(item => !string.IsNullOrWhiteSpace(item.Surface)) == true, "account workspace detail route should keep surface classification on every restore conflict receipt.");
    Assert(
        accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts
            .Where(item => !string.IsNullOrWhiteSpace(item.Kind) && item.Kind.StartsWith("entitlement_", StringComparison.OrdinalIgnoreCase))
            .All(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)) == true,
        "account workspace detail route should keep entitlement conflict receipts on the entitlement-sync surface.");
    Assert(
        accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts.Any(item =>
            item.BlocksContinue
            && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)) == true,
        "account workspace detail route should keep blocking entitlement-sync restore conflicts visible on the selected workspace.");
    Assert(
        accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts
            .Where(static item => item.BlocksContinue)
            .All(static item => !string.IsNullOrWhiteSpace(item.RecoveryHint)) == true,
        "account workspace detail route should keep concrete recovery hints on blocking restore conflict receipts.");
    Assert(
        accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts.Any(item =>
            string.Equals(item.Kind, "entitlement_artifact_drift", StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
            && item.BlocksContinue) == true,
        "account workspace detail route should keep blocking artifact-drift receipts visible on the selected workspace.");
    if (accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts.Any(static item => item.BlocksContinue) == true)
    {
        Assert(string.Equals(accountWorkspaceDetailModel.SelectedWorkspaceServerPlane.NextSafeAction.Label, "Review restore receipts", StringComparison.Ordinal), "account workspace detail route should turn blocking restore conflicts into an explicit restore-review next action.");
        Assert(string.Equals(accountWorkspaceDetailModel.SelectedWorkspaceServerPlane.NextSafeAction.SourceKind, "restore", StringComparison.Ordinal), "account workspace detail route should classify restore-driven next actions under the restore source kind.");
    }
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RuleEnvironmentHealth.Count >= 1, "account workspace detail route should expose rule-environment health cues from the workspace server plane.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.WorkspaceState.Label), "account workspace detail route should expose one bounded workspace-state label.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.WorkspaceState.EvidenceLines.Count >= 1, "account workspace detail route should expose evidence for the bounded workspace state.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceRosterTransferPlan is not null, "account workspace detail route should expose the governed roster-transfer planner on the selected shared campaign view.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceRosterTransferPlan?.DossierOptions.Count >= 1, "account workspace detail route should keep movable governed dossiers visible on the roster-transfer planner.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceRosterTransferPlan?.TargetGroups.Count >= 1, "account workspace detail route should keep operator-manageable target groups visible on the roster-transfer planner.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.PrepLibrary.Packets.Count >= 3, "account workspace detail route should surface the governed GM prep library.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.PrepLaunches.Any(item => string.Equals(item.LaunchId, prepLaunchPayload!.LaunchId, StringComparison.Ordinal)) == true, "account workspace detail route should surface recent governed prep-launch receipts.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.TravelMode.TravelReadyDeviceCount >= 1, "account workspace detail route should surface safehouse/travel readiness.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.TravelPrefetches.Any(item => string.Equals(item.ReceiptId, travelPrefetchPayload!.ReceiptId, StringComparison.Ordinal)) == true, "account workspace detail route should surface staged travel-prefetch receipts.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.AftermathPackages.Any(item => string.Equals(item.PackageId, aftermathPackagePayload!.PackageId, StringComparison.Ordinal)) == true, "account workspace detail route should surface aftermath recap packages.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.AftermathPackages.Any(item => string.Equals(item.PackageId, downtimeBriefPayload!.PackageId, StringComparison.Ordinal)) == true, "account workspace detail route should surface downtime brief packages.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.AftermathPackages.Any(item => string.Equals(item.PackageId, replayTimelinePayload!.PackageId, StringComparison.Ordinal)) == true, "account workspace detail route should surface replay timeline packages.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf.Any(item => string.Equals(item.EntryId, replayTimelinePayload!.PackageId, StringComparison.Ordinal)) == true, "account workspace detail route should keep replay packages on the richer return shelf.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.TravelMode.PrefetchInventorySummary.Contains("governed prep packet", StringComparison.Ordinal) == true, "account workspace detail route should explain that prep packets are carried in the prefetch inventory.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf.Count >= 1, "account workspace detail route should project the richer recap shelf through the workspace server plane.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf[0].OwnershipSummary), "account workspace detail route should surface explicit ownership posture on recap-shelf entries.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf[0].PublicationState), "account workspace detail route should surface publication-state posture on recap-shelf entries.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf[0].TrustBand), "account workspace detail route should surface trust-ranking posture on recap-shelf entries when creator publication is already linked.");
    Assert(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf[0].Discoverable == false, "account workspace detail route should keep preview-ready recap entries bounded until publication is actually live.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf[0].PublicationSummary), "account workspace detail route should surface publication-summary posture on recap-shelf entries.");
    Assert(!string.IsNullOrWhiteSpace(accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RecapShelf[0].NextSafeAction), "account workspace detail route should surface next-safe-action posture on recap-shelf entries.");
    var searchableWorkspaceDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, workspaceId: workspaceId, prepQuery: "opposition") as ViewResult;
    var searchableWorkspaceDetailModel = searchableWorkspaceDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(searchableWorkspaceDetailModel?.SelectedWorkspacePrepLibrarySearch?.QueryText, "opposition", StringComparison.Ordinal), "account workspace detail search should keep the normalized governed prep-library query.");
    Assert(searchableWorkspaceDetailModel?.SelectedWorkspacePrepLibrarySearch?.TotalCount >= 1, "account workspace detail search should return matching governed prep packets.");
    Assert(searchableWorkspaceDetailModel?.SelectedWorkspacePrepLibrarySearch?.Items.Any(item => item.Title.Contains("opposition", StringComparison.OrdinalIgnoreCase) || item.SearchTerms.Any(term => term.Contains("opposition", StringComparison.OrdinalIgnoreCase))) == true, "account workspace detail search should surface the governed opposition packet.");
    Assert(searchableWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "prep_launch", StringComparison.Ordinal)) == true, "account workspace detail search should keep prep-launch receipts on the what-changed rail.");
    Assert(searchableWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "travel_prefetch", StringComparison.Ordinal)) == true, "account workspace detail search should keep travel-prefetch receipts on the what-changed rail.");
    Assert(searchableWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "aftermath_recap", StringComparison.Ordinal)) == true, "account workspace detail search should keep aftermath recap packages on the what-changed rail.");
    Assert(searchableWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "replay_package", StringComparison.Ordinal)) == true, "account workspace detail search should keep replay packages on the what-changed rail.");
    Assert(searchableWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "next_session_carry_forward", StringComparison.Ordinal)) == true, "account workspace detail search should keep the next-session carry-forward packet on the what-changed rail.");
    var accountRunDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, runId: runId) as ViewResult;
    var accountRunDetailModel = accountRunDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountRunDetailModel?.SelectedRun?.RunId, runId, StringComparison.Ordinal), "account run detail route should load the selected live run context.");
    var accountBuildHandoffDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, handoffId: handoffId) as ViewResult;
    var accountBuildHandoffDetailModel = accountBuildHandoffDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountBuildHandoffDetailModel?.SelectedBuildLabHandoff?.HandoffId, handoffId, StringComparison.Ordinal), "account build detail route should load the selected build follow-through.");
    Assert(!string.IsNullOrWhiteSpace(accountBuildHandoffDetailModel?.SelectedBuildLabHandoff?.CampaignReturnSummary), "account build detail route should keep build-handoff return truth visible.");
    Assert(!string.IsNullOrWhiteSpace(accountBuildHandoffDetailModel?.SelectedBuildLabHandoff?.SupportClosureSummary), "account build detail route should keep build-handoff support closure visible.");
    Assert(accountBuildHandoffDetailModel?.SelectedBuildLabHandoff?.ProgressionOutcomes.Count >= 1, "account build detail route should keep build-handoff progression outcomes visible.");
    var accountRulesDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, entryId: rulesEntryId) as ViewResult;
    var accountRulesDetailModel = accountRulesDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountRulesDetailModel?.SelectedRulesNavigatorAnswer?.EntryId, rulesEntryId, StringComparison.Ordinal), "account rules detail route should load the selected grounded rule answer.");
    var accountPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: publicationId) as ViewResult;
    var accountPublicationDetailModel = accountPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountPublicationDetailModel?.SelectedCreatorPublication?.PublicationId, publicationId, StringComparison.Ordinal), "account publication detail route should load the selected creator-publication follow-through.");
    Assert(!string.IsNullOrWhiteSpace(accountPublicationDetailModel?.SelectedCreatorPublication?.TrustSummary), "account publication detail route should keep creator-publication trust reasoning visible.");
    Assert(!string.IsNullOrWhiteSpace(accountPublicationDetailModel?.SelectedCreatorPublication?.ComparisonSummary), "account publication detail route should keep creator-publication comparison guidance visible.");
    Assert(!string.IsNullOrWhiteSpace(accountPublicationDetailModel?.SelectedCreatorPublication?.NextSafeAction), "account publication detail route should keep the creator-publication next step visible.");
    Assert(!string.IsNullOrWhiteSpace(accountPublicationDetailModel?.SelectedCreatorPublication?.CampaignReturnSummary), "account publication detail route should keep creator-publication return truth visible.");
    Assert(!string.IsNullOrWhiteSpace(accountPublicationDetailModel?.SelectedCreatorPublication?.SupportClosureSummary), "account publication detail route should keep creator-publication support closure visible.");
    Assert(!string.IsNullOrWhiteSpace(accountPublicationDetailModel?.SelectedCreatorPublication?.ModerationSummary), "account publication detail route should keep creator-publication moderation posture visible.");
    Assert(string.Equals(accountPublicationDetailModel?.SelectedCreatorPublication?.BuildHandoffId, handoffId, StringComparison.Ordinal), "account publication detail route should keep the related build handoff attached.");
    Assert(accountPublicationDetailModel?.SelectedCreatorPublicationDraftDetail is not null, "account publication detail route should project the registry-owned creator draft detail.");
    Assert(accountPublicationDetailModel?.SelectedCreatorPublicationReceipt is not null, "account publication detail route should project the registry-owned publication receipt.");
    Assert(!string.IsNullOrWhiteSpace(accountPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Draft.ProjectKind)
        && !string.Equals(accountPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Draft.ProjectKind, nameof(HubArtifactKind.BuildIdea), StringComparison.Ordinal),
        "account publication detail route should preserve a concrete shared project kind through the registry draft bridge instead of collapsing back to the generic build-idea fallback.");
    Assert(accountPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Description?.Contains("Publication kind:", StringComparison.Ordinal) == true, "account publication detail route should carry publication-kind evidence into the registry draft description.");
    Assert(accountPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Description?.Contains("Status:", StringComparison.Ordinal) == true, "account publication detail route should carry publication-status evidence into the registry draft description.");
    Assert(string.Equals(accountPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.NotRequired, StringComparison.Ordinal), "fresh creator publication detail should begin outside the moderation queue.");

    var submitPublicationResult = await accountController.SubmitCreatorPublication(publicationId, "Ready for governed moderation and trust review.", CancellationToken.None);
    Assert(submitPublicationResult is RedirectResult { Url: not null }, "creator publication submission should redirect back to the publication detail route.");
    var submittedPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: publicationId) as ViewResult;
    var submittedPublicationDetailModel = submittedPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(submittedPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.PendingReview, StringComparison.Ordinal), "submitted creator publications should enter the registry moderation queue.");
    Assert(string.Equals(submittedPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Moderation?.State, Chummer.Hub.Registry.Contracts.HubModerationStates.PendingReview, StringComparison.Ordinal), "submitted creator publications should surface the pending moderation case on the account detail route.");

    var approvePublicationResult = await accountController.ApproveCreatorPublication(publicationId, "Provenance and lineage verified on the governed account rail.", CancellationToken.None);
    Assert(approvePublicationResult is RedirectResult { Url: not null }, "creator publication approval should redirect back to the publication detail route.");
    var approvedPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: publicationId) as ViewResult;
    var approvedPublicationDetailModel = approvedPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(approvedPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.Approved, StringComparison.Ordinal), "approved creator publications should surface approved review posture on the account detail route.");
    Assert(approvedPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.LatestModerationNotes?.Contains("governed account rail", StringComparison.OrdinalIgnoreCase) == true, "approved creator publications should retain the latest moderation note on the account detail route.");
    Assert(string.Equals(approvedPublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "approved", StringComparison.Ordinal), "approved creator publications should replace synthetic preview status with the registry-backed approved posture on the shared projection.");
    Assert(approvedPublicationDetailModel?.SelectedCreatorPublication?.ModerationSummary?.Contains("Moderation cleared approval", StringComparison.OrdinalIgnoreCase) == true, "approved creator publications should carry approval-backed moderation summary on the shared projection.");

    var publishPublicationResult = await accountController.PublishCreatorPublication(publicationId, "Publish the governed publication onto public discovery now that review cleared.", CancellationToken.None);
    Assert(publishPublicationResult is RedirectResult { Url: not null }, "creator publication publish should redirect back to the publication detail route.");
    var publishedPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: publicationId) as ViewResult;
    var publishedPublicationDetailModel = publishedPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(publishedPublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublicationStatus, Chummer.Hub.Registry.Contracts.HubPublicationStates.Published, StringComparison.Ordinal), "published creator publications should surface the live published receipt posture on the account detail route.");
    Assert(publishedPublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublishedAtUtc is not null, "published creator publications should stamp the published timestamp on the account detail route.");
    Assert(string.Equals(publishedPublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "published", StringComparison.Ordinal), "published creator publications should project the live published posture on the shared creator-publication card.");
    Assert(publishedPublicationDetailModel?.SelectedCreatorPublication?.Discoverable == true, "published creator publications should become discoverable once the creator shelf promotion lands.");
    Assert(publishedPublicationDetailModel?.SelectedCreatorPublication?.TrustSummary?.Contains("live on governed discovery", StringComparison.OrdinalIgnoreCase) == true, "published creator publications should explain live governed discovery on the shared projection.");
    Assert(publishedPublicationDetailModel?.SelectedCreatorPublication?.ModerationSummary?.Contains("active but clear", StringComparison.OrdinalIgnoreCase) == true, "published creator publications should carry moderation-watch posture once they are live.");

    var primerPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: primerPublicationId) as ViewResult;
    var primerPublicationDetailModel = primerPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(primerPublicationDetailModel?.SelectedCreatorPublication?.PublicationId, primerPublicationId, StringComparison.Ordinal), "account publication detail route should load the selected primer publication on the shared lane.");
    Assert(string.Equals(primerPublicationDetailModel?.SelectedCreatorPublication?.Kind, "primer", StringComparison.Ordinal), "account publication detail route should preserve the primer publication kind.");
    Assert(primerPublicationDetailModel?.SelectedCreatorPublication?.Title.Contains("campaign primer", StringComparison.OrdinalIgnoreCase) == true, "account publication detail route should give primer publications a first-class title.");
    Assert(string.Equals(primerPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Draft.ProjectKind, "Primer", StringComparison.Ordinal), "account publication detail route should keep primer drafts on the shared registry primer kind instead of a fallback project kind.");
    Assert(primerPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Description?.Contains("Publication kind: Primer", StringComparison.Ordinal) == true, "account publication detail route should carry primer-specific publication kind evidence into the draft description.");

    var submitPrimerPublicationResult = await accountController.SubmitCreatorPublication(primerPublicationId, "Primer packet is grounded enough for governed moderation.", CancellationToken.None);
    Assert(submitPrimerPublicationResult is RedirectResult { Url: not null }, "primer publication submission should redirect back to the publication detail route.");
    var submittedPrimerPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: primerPublicationId) as ViewResult;
    var submittedPrimerPublicationDetailModel = submittedPrimerPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(submittedPrimerPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.PendingReview, StringComparison.Ordinal), "submitted primer publications should enter the registry moderation queue.");
    Assert(string.Equals(submittedPrimerPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Moderation?.State, Chummer.Hub.Registry.Contracts.HubModerationStates.PendingReview, StringComparison.Ordinal), "submitted primer publications should surface the pending moderation case on the account detail route.");

    var approvePrimerPublicationResult = await accountController.ApproveCreatorPublication(primerPublicationId, "Primer lineage and onboarding trust stayed grounded on the governed publication lane.", CancellationToken.None);
    Assert(approvePrimerPublicationResult is RedirectResult { Url: not null }, "primer publication approval should redirect back to the publication detail route.");
    var approvedPrimerPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: primerPublicationId) as ViewResult;
    var approvedPrimerPublicationDetailModel = approvedPrimerPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(approvedPrimerPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.Approved, StringComparison.Ordinal), "approved primer publications should surface approved review posture on the account detail route.");
    Assert(string.Equals(approvedPrimerPublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "approved", StringComparison.Ordinal), "approved primer publications should replace synthetic preview status with the registry-backed approved posture on the shared projection.");
    Assert(approvedPrimerPublicationDetailModel?.SelectedCreatorPublication?.ModerationSummary?.Contains("Moderation cleared approval", StringComparison.OrdinalIgnoreCase) == true, "approved primer publications should carry approval-backed moderation summary on the shared projection.");

    var publishPrimerPublicationResult = await accountController.PublishCreatorPublication(primerPublicationId, "Publish the campaign primer on governed public discovery now that review cleared.", CancellationToken.None);
    Assert(publishPrimerPublicationResult is RedirectResult { Url: not null }, "primer publication publish should redirect back to the publication detail route.");
    var publishedPrimerPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: primerPublicationId) as ViewResult;
    var publishedPrimerPublicationDetailModel = publishedPrimerPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(publishedPrimerPublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublicationStatus, Chummer.Hub.Registry.Contracts.HubPublicationStates.Published, StringComparison.Ordinal), "published primer publications should surface the live published receipt posture on the account detail route.");
    Assert(publishedPrimerPublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublishedAtUtc is not null, "published primer publications should stamp the published timestamp on the account detail route.");
    Assert(string.Equals(publishedPrimerPublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "published", StringComparison.Ordinal), "published primer publications should project the live published posture on the shared creator-publication card.");
    Assert(string.Equals(publishedPrimerPublicationDetailModel?.SelectedCreatorPublication?.Kind, "primer", StringComparison.Ordinal), "published primer publications should stay typed as primer on the shared projection.");
    Assert(publishedPrimerPublicationDetailModel?.SelectedCreatorPublication?.Discoverable == true, "published primer publications should become discoverable once the governed public shelf promotion lands.");
    Assert(publishedPrimerPublicationDetailModel?.SelectedCreatorPublication?.TrustSummary?.Contains("live on governed discovery", StringComparison.OrdinalIgnoreCase) == true, "published primer publications should explain live governed discovery on the shared projection.");

    var runModulePublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: runModulePublicationId) as ViewResult;
    var runModulePublicationDetailModel = runModulePublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(runModulePublicationDetailModel?.SelectedCreatorPublication?.PublicationId, runModulePublicationId, StringComparison.Ordinal), "account publication detail route should load the selected run-module publication on the shared lane.");
    Assert(string.Equals(runModulePublicationDetailModel?.SelectedCreatorPublication?.Kind, "run_module", StringComparison.Ordinal), "account publication detail route should preserve the run-module publication kind.");
    Assert(runModulePublicationDetailModel?.SelectedCreatorPublication?.Title.Contains("run module", StringComparison.OrdinalIgnoreCase) == true, "account publication detail route should give run-module publications a first-class title.");
    Assert(string.Equals(runModulePublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Draft.ProjectKind, "RunModule", StringComparison.Ordinal), "account publication detail route should keep run-module drafts on the shared registry run-module kind instead of a fallback project kind.");
    Assert(runModulePublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Description?.Contains("Publication kind: Run Module", StringComparison.Ordinal) == true, "account publication detail route should carry run-module publication kind evidence into the draft description.");

    var submitRunModulePublicationResult = await accountController.SubmitCreatorPublication(runModulePublicationId, "Run-module packet is grounded enough for governed moderation.", CancellationToken.None);
    Assert(submitRunModulePublicationResult is RedirectResult { Url: not null }, "run-module publication submission should redirect back to the publication detail route.");
    var submittedRunModulePublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: runModulePublicationId) as ViewResult;
    var submittedRunModulePublicationDetailModel = submittedRunModulePublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(submittedRunModulePublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.PendingReview, StringComparison.Ordinal), "submitted run-module publications should enter the registry moderation queue.");
    Assert(string.Equals(submittedRunModulePublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Moderation?.State, Chummer.Hub.Registry.Contracts.HubModerationStates.PendingReview, StringComparison.Ordinal), "submitted run-module publications should surface the pending moderation case on the account detail route.");

    var approveRunModulePublicationResult = await accountController.ApproveCreatorPublication(runModulePublicationId, "Run-module lineage and GM continuity stayed grounded on the governed publication lane.", CancellationToken.None);
    Assert(approveRunModulePublicationResult is RedirectResult { Url: not null }, "run-module publication approval should redirect back to the publication detail route.");
    var approvedRunModulePublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: runModulePublicationId) as ViewResult;
    var approvedRunModulePublicationDetailModel = approvedRunModulePublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(approvedRunModulePublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.Approved, StringComparison.Ordinal), "approved run-module publications should surface approved review posture on the account detail route.");
    Assert(string.Equals(approvedRunModulePublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "approved", StringComparison.Ordinal), "approved run-module publications should replace synthetic preview status with the registry-backed approved posture on the shared projection.");
    Assert(approvedRunModulePublicationDetailModel?.SelectedCreatorPublication?.ModerationSummary?.Contains("Moderation cleared approval", StringComparison.OrdinalIgnoreCase) == true, "approved run-module publications should carry approval-backed moderation summary on the shared projection.");

    var publishRunModulePublicationResult = await accountController.PublishCreatorPublication(runModulePublicationId, "Publish the run module on governed public discovery now that review cleared.", CancellationToken.None);
    Assert(publishRunModulePublicationResult is RedirectResult { Url: not null }, "run-module publication publish should redirect back to the publication detail route.");
    var publishedRunModulePublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: runModulePublicationId) as ViewResult;
    var publishedRunModulePublicationDetailModel = publishedRunModulePublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(publishedRunModulePublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublicationStatus, Chummer.Hub.Registry.Contracts.HubPublicationStates.Published, StringComparison.Ordinal), "published run-module publications should surface the live published receipt posture on the account detail route.");
    Assert(publishedRunModulePublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublishedAtUtc is not null, "published run-module publications should stamp the published timestamp on the account detail route.");
    Assert(string.Equals(publishedRunModulePublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "published", StringComparison.Ordinal), "published run-module publications should project the live published posture on the shared creator-publication card.");
    Assert(string.Equals(publishedRunModulePublicationDetailModel?.SelectedCreatorPublication?.Kind, "run_module", StringComparison.Ordinal), "published run-module publications should stay typed as run-module on the shared projection.");
    Assert(publishedRunModulePublicationDetailModel?.SelectedCreatorPublication?.Discoverable == true, "published run-module publications should become discoverable once the governed public shelf promotion lands.");
    Assert(publishedRunModulePublicationDetailModel?.SelectedCreatorPublication?.TrustSummary?.Contains("live on governed discovery", StringComparison.OrdinalIgnoreCase) == true, "published run-module publications should explain live governed discovery on the shared projection.");

    var dossierPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: dossierPublicationId) as ViewResult;
    var dossierPublicationDetailModel = dossierPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(dossierPublicationDetailModel?.SelectedCreatorPublication?.PublicationId, dossierPublicationId, StringComparison.Ordinal), "account publication detail route should load the selected dossier publication on the shared lane.");
    Assert(string.Equals(dossierPublicationDetailModel?.SelectedCreatorPublication?.Kind, "dossier", StringComparison.Ordinal), "account publication detail route should preserve the dossier publication kind.");
    Assert(dossierPublicationDetailModel?.SelectedCreatorPublication?.Title.Contains("dossier", StringComparison.OrdinalIgnoreCase) == true, "account publication detail route should give dossier publications a first-class title.");
    Assert(string.Equals(dossierPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Draft.ProjectKind, "Dossier", StringComparison.Ordinal), "account publication detail route should keep dossier drafts on the shared registry dossier kind instead of a fallback project kind.");
    Assert(dossierPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Description?.Contains("Publication kind: Dossier", StringComparison.Ordinal) == true, "account publication detail route should carry dossier publication kind evidence into the draft description.");

    var submitDossierPublicationResult = await accountController.SubmitCreatorPublication(dossierPublicationId, "Dossier packet is grounded enough for governed moderation.", CancellationToken.None);
    Assert(submitDossierPublicationResult is RedirectResult { Url: not null }, "dossier publication submission should redirect back to the publication detail route.");
    var submittedDossierPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: dossierPublicationId) as ViewResult;
    var submittedDossierPublicationDetailModel = submittedDossierPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(submittedDossierPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.PendingReview, StringComparison.Ordinal), "submitted dossier publications should enter the registry moderation queue.");
    Assert(string.Equals(submittedDossierPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Moderation?.State, Chummer.Hub.Registry.Contracts.HubModerationStates.PendingReview, StringComparison.Ordinal), "submitted dossier publications should surface the pending moderation case on the account detail route.");

    var approveDossierPublicationResult = await accountController.ApproveCreatorPublication(dossierPublicationId, "Dossier lineage and living identity stayed grounded on the governed publication lane.", CancellationToken.None);
    Assert(approveDossierPublicationResult is RedirectResult { Url: not null }, "dossier publication approval should redirect back to the publication detail route.");
    var approvedDossierPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: dossierPublicationId) as ViewResult;
    var approvedDossierPublicationDetailModel = approvedDossierPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(approvedDossierPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.Approved, StringComparison.Ordinal), "approved dossier publications should surface approved review posture on the account detail route.");
    Assert(string.Equals(approvedDossierPublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "approved", StringComparison.Ordinal), "approved dossier publications should replace synthetic preview status with the registry-backed approved posture on the shared projection.");
    Assert(approvedDossierPublicationDetailModel?.SelectedCreatorPublication?.ModerationSummary?.Contains("Moderation cleared approval", StringComparison.OrdinalIgnoreCase) == true, "approved dossier publications should carry approval-backed moderation summary on the shared projection.");

    var publishDossierPublicationResult = await accountController.PublishCreatorPublication(dossierPublicationId, "Publish the dossier on governed public discovery now that review cleared.", CancellationToken.None);
    Assert(publishDossierPublicationResult is RedirectResult { Url: not null }, "dossier publication publish should redirect back to the publication detail route.");
    var publishedDossierPublicationDetailPage = await accountController.AccountPage(section: null, caseId: null, cancellationToken: CancellationToken.None, publicationId: dossierPublicationId) as ViewResult;
    var publishedDossierPublicationDetailModel = publishedDossierPublicationDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(publishedDossierPublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublicationStatus, Chummer.Hub.Registry.Contracts.HubPublicationStates.Published, StringComparison.Ordinal), "published dossier publications should surface the live published receipt posture on the account detail route.");
    Assert(publishedDossierPublicationDetailModel?.SelectedCreatorPublicationReceipt?.PublishedAtUtc is not null, "published dossier publications should stamp the published timestamp on the account detail route.");
    Assert(string.Equals(publishedDossierPublicationDetailModel?.SelectedCreatorPublication?.PublicationStatus, "published", StringComparison.Ordinal), "published dossier publications should project the live published posture on the shared creator-publication card.");
    Assert(string.Equals(publishedDossierPublicationDetailModel?.SelectedCreatorPublication?.Kind, "dossier", StringComparison.Ordinal), "published dossier publications should stay typed as dossier on the shared projection.");
    Assert(publishedDossierPublicationDetailModel?.SelectedCreatorPublication?.Discoverable == true, "published dossier publications should become discoverable once the governed public shelf promotion lands.");
    Assert(publishedDossierPublicationDetailModel?.SelectedCreatorPublication?.TrustSummary?.Contains("live on governed discovery", StringComparison.OrdinalIgnoreCase) == true, "published dossier publications should explain live governed discovery on the shared projection.");

    var authenticatedHomePage = await authenticatedLandingController.HomePage(null, CancellationToken.None) as ViewResult;
    var authenticatedHomeModel = authenticatedHomePage?.Model as HomePageViewModel;
    Assert(authenticatedHomeModel is not null, "signed-in home page should render through the MVC view layer.");
    Assert(string.Equals(authenticatedHomeModel!.CurrentSection, "overview", StringComparison.Ordinal), "default home route should land on the overview section.");
    Assert(authenticatedHomeModel.Sections.Any(static section => string.Equals(section.Href, "/home/access", StringComparison.Ordinal)), "home should expose the dedicated access section link.");
    Assert(authenticatedHomeModel.SignedInStatus is not null, "signed-in home should project the shared signed-in trust status.");
    Assert(authenticatedHomeModel.SignedInStatus!.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "signed-in home should surface who-can-get-it-now posture directly in the shared trust panel.");
    Assert(authenticatedHomeModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Fix availability", StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(row.Value)), "signed-in home should surface a non-empty fix-availability row directly in the shared trust panel.");
    Assert(authenticatedHomeModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Current caution", StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(row.Value)), "signed-in home should surface a non-empty install-specific caution row directly in the shared trust panel.");
    var authenticatedLandingView = await authenticatedLandingController.LandingPage(CancellationToken.None) as ViewResult;
    var authenticatedLandingModel = authenticatedLandingView?.Model as LandingPageViewModel;
    Assert(authenticatedLandingModel?.SignedInStatus is not null, "authenticated landing should project the shared signed-in trust status on the front door.");
    Assert(authenticatedLandingModel!.SignedInStatus!.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "authenticated landing should surface who-can-get-it-now posture directly in the shared trust panel.");
    Assert(authenticatedLandingModel.SignedInStatus.Rows.Any(static row => string.Equals(row.Label, "Fix availability", StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(row.Value)), "authenticated landing should surface a non-empty fix-availability row directly in the shared trust panel.");
    var authenticatedFaqPage = await authenticatedLandingController.FaqPage(CancellationToken.None) as ViewResult;
    var authenticatedFaqModel = authenticatedFaqPage?.Model as FaqPageViewModel;
    Assert(authenticatedFaqModel?.SignedInStatus is not null, "authenticated faq should project the shared signed-in trust status.");
    Assert(authenticatedFaqModel?.TrustPulse is not null, "authenticated faq should keep the weekly public trust pulse visible.");
    Assert(authenticatedHomeModel!.SupportCases.Any(item => string.Equals(item.CaseId, supportCase.CaseId, StringComparison.Ordinal)), "signed-in home should surface tracked support context.");
    Assert(authenticatedHomeModel.SupportCaseSummaries.Any(item => string.Equals(item.Case.CaseId, supportCase.CaseId, StringComparison.Ordinal) && item.ClosureSummary.Contains("closure notice", StringComparison.OrdinalIgnoreCase)), "signed-in home access should surface release closure truth from the shared support presenter.");
    Assert(authenticatedHomeModel.CampaignSpine.Dossiers.Count >= 1, "signed-in home should surface living dossier continuity.");
    Assert(authenticatedHomeModel.CampaignSpine.Runs.Count >= 1, "signed-in home should surface runboard continuity.");
    Assert(authenticatedHomeModel.CampaignSpine.Workspaces.Count >= 1, "signed-in home should keep the first-class campaign workspace attached to the signed-in shell.");
    Assert(authenticatedHomeModel.CampaignSpine.Workspaces[0].Consequences?.Count >= 4, "signed-in home should keep governed faction, heat, contact, and reputation consequences attached to the shared campaign view.");
    Assert(authenticatedHomeModel.CampaignSpine.Workspaces[0].CampaignMemory is not null, "signed-in home should keep the shared campaign-memory projection attached to the shared campaign view.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.Workspaces[0].ActiveSceneSummary), "signed-in home should keep the active-scene summary attached to the shared campaign view.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.Workspaces[0].NextSafeAction), "signed-in home should keep the workspace next safe action attached to the shared campaign view.");
    Assert(authenticatedHomeModel.CampaignSpine.Workspaces.Any(item => !string.IsNullOrWhiteSpace(item.FirstPlayableSession?.RuleReadySummary)), "signed-in home should keep legal-runner proof attached to at least one shared first-session projection.");
    Assert(authenticatedHomeModel.CampaignSpine.CreatorPublications.Any(item => string.Equals(item.PublicationStatus, "published", StringComparison.Ordinal)), "signed-in home should carry registry-backed live creator-publication posture once the creator shelf promotion lands.");
    var publishedHomePublication = authenticatedHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, publicationId, StringComparison.Ordinal));
    Assert(publishedHomePublication is not null, "signed-in home should keep the explicitly published creator publication on the shared home projection.");
    var publishedHomePrimerPublication = authenticatedHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, primerPublicationId, StringComparison.Ordinal));
    Assert(publishedHomePrimerPublication is not null, "signed-in home should keep the explicitly published primer publication on the shared home projection.");
    Assert(string.Equals(publishedHomePrimerPublication?.PublicationStatus, "published", StringComparison.Ordinal), "signed-in home should carry the live published primer posture.");
    Assert(string.Equals(publishedHomePrimerPublication?.Kind, "primer", StringComparison.Ordinal), "signed-in home should preserve the primer publication kind.");
    Assert(publishedHomePrimerPublication?.Discoverable == true, "signed-in home should carry discoverable primer publication posture once publication is live.");
    var publishedHomeRunModulePublication = authenticatedHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, runModulePublicationId, StringComparison.Ordinal));
    Assert(publishedHomeRunModulePublication is not null, "signed-in home should keep the explicitly published run-module publication on the shared home projection.");
    Assert(string.Equals(publishedHomeRunModulePublication?.PublicationStatus, "published", StringComparison.Ordinal), "signed-in home should carry the live published run-module posture.");
    Assert(string.Equals(publishedHomeRunModulePublication?.Kind, "run_module", StringComparison.Ordinal), "signed-in home should preserve the run-module publication kind.");
    Assert(publishedHomeRunModulePublication?.Discoverable == true, "signed-in home should carry discoverable run-module publication posture once publication is live.");
    var publishedHomeDossierPublication = authenticatedHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, dossierPublicationId, StringComparison.Ordinal));
    Assert(publishedHomeDossierPublication is not null, "signed-in home should keep the explicitly published dossier publication on the shared home projection.");
    Assert(string.Equals(publishedHomeDossierPublication?.PublicationStatus, "published", StringComparison.Ordinal), "signed-in home should carry the live published dossier posture.");
    Assert(string.Equals(publishedHomeDossierPublication?.Kind, "dossier", StringComparison.Ordinal), "signed-in home should preserve the dossier publication kind.");
    Assert(publishedHomeDossierPublication?.Discoverable == true, "signed-in home should carry discoverable dossier publication posture once publication is live.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane is not null, "signed-in home should receive the bounded lead workspace server plane.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.LeadWorkspaceServerPlane!.WorkspaceState.Status), "signed-in home should surface one bounded workspace state on the what-changed card.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane.WorkspaceState.EvidenceLines.Count >= 1, "signed-in home should surface workspace-state evidence on the what-changed card.");
    Assert(authenticatedHomeModel.CampaignSpine.Workspaces.Any(item => !string.IsNullOrWhiteSpace(item.FirstPlayableSession?.ReturnLaneSummary)), "signed-in home should keep understandable-return proof attached to at least one shared first-session projection.");
    Assert(authenticatedHomeModel.CampaignSpine.Workspaces.Any(item => !string.IsNullOrWhiteSpace(item.FirstPlayableSession?.CampaignReadySummary)), "signed-in home should keep campaign-ready proof attached to at least one shared first-session projection.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane!.PrepLibrary.Packets.Count >= 3, "signed-in home should surface the governed GM prep library on the home cockpit.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane.PrepLaunches.Any(item => string.Equals(item.LaunchId, prepLaunchPayload!.LaunchId, StringComparison.Ordinal)) == true, "signed-in home should surface the latest governed prep-launch receipt on the same workspace spine.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane.TravelMode.TravelReadyDeviceCount >= 1, "signed-in home should surface safehouse/travel readiness on the home cockpit.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane.TravelPrefetches.Any(item => string.Equals(item.ReceiptId, travelPrefetchPayload!.ReceiptId, StringComparison.Ordinal)) == true, "signed-in home should surface the latest staged travel-prefetch receipt on the same workspace spine.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane.AftermathPackages.Any(item => string.Equals(item.PackageId, aftermathPackagePayload!.PackageId, StringComparison.Ordinal)) == true, "signed-in home should surface the latest aftermath recap package on the same workspace spine.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane.CampaignMemory is not null, "signed-in home should surface the bounded campaign-memory projection on the same workspace spine.");
    Assert(authenticatedHomeModel.LeadWorkspaceServerPlane.Consequences.Count >= 1, "signed-in home should keep governed consequence follow-through visible on the same workspace spine.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations.Count >= 1, "signed-in home should surface organizer/operator posture on the same account backbone.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].CampaignVisibilitySummary), "signed-in home should keep campaign visibility posture visible for the lead operator group.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].OperationsSummary), "signed-in home should keep the operator operations pulse visible for the lead operator group.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].LeagueOperationsSummary), "signed-in home should keep the league-and-season operations summary visible for the lead operator group.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].SeasonEventSummary), "signed-in home should keep the operator season-event pulse visible for the lead operator group.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].RecentEventSummaries.Count >= 1, "signed-in home should keep a bounded recent-event receipt attached to the lead operator group.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].RecentLeagueAuditLines.Count >= 1, "signed-in home should keep bounded league-and-season audit lines attached to the lead operator group.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].RecentJoinCodes.Any(code => string.Equals(code.Code, operatorJoinCode.Code, StringComparison.Ordinal)), "signed-in home should keep recent governed join codes attached to the lead operator group.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].RecentBoostCodes.Any(code => string.Equals(code.Code, operatorBoostCode.Code, StringComparison.Ordinal)), "signed-in home should keep recent governed boost codes attached to the lead operator group.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].RecentSponsorSessions.Any(session => string.Equals(session.SponsorSessionId, operatorSponsorSession.SponsorSessionId, StringComparison.Ordinal)), "signed-in home should keep recent governed sponsor sessions attached to the lead operator group.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].SeasonBoardEntries.Count >= 2, "signed-in home should keep the multi-campaign season board attached to the lead operator group.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].SeasonBoardEntries.Any(entry => !string.IsNullOrWhiteSpace(entry.RecapSummary)), "signed-in home should keep a season-board recap summary attached to at least one lead operator lane.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].SeasonBoardEntries.Any(entry => !string.IsNullOrWhiteSpace(entry.ConsequenceSummary)), "signed-in home should keep a season-board consequence summary attached to at least one lead operator lane.");
    Assert(authenticatedHomeModel.CampaignSpine.CommunityOperations[0].SeasonBoardEntries.All(entry => !string.IsNullOrWhiteSpace(entry.CampaignMemorySummary)), "signed-in home should keep campaign-memory summaries attached to the lead season-board lanes.");
    Assert(authenticatedHomeModel.CampaignSpine.BuildLabHandoffs.Count >= 1, "signed-in home should surface Build Lab handoff continuity.");
    Assert(authenticatedHomeModel.CampaignSpine.BuildLabHandoffs[0].Title.Contains("build path", StringComparison.OrdinalIgnoreCase), "signed-in home should receive customer-facing build-path titles directly from the campaign spine service.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.BuildLabHandoffs[0].NextSafeAction), "signed-in home should receive the next safe build action directly from the campaign spine service.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedHomeModel.CampaignSpine.BuildLabHandoffs[0].PlannerCoverageSummary), "signed-in home should receive planner-coverage summary directly from the campaign spine service.");
    var authenticatedContactPage = await authenticatedLandingController.ContactPage(CancellationToken.None) as ViewResult;
    var authenticatedContactModel = authenticatedContactPage?.Model as TrustPageViewModel;
    Assert(authenticatedContactModel?.SupportIntake is not null, "authenticated contact page should project the first-party support intake.");
    Assert(authenticatedContactModel?.SignedInStatus is not null, "authenticated contact page should project the shared signed-in trust status.");
    Assert(authenticatedContactModel?.TrustPulse is not null, "authenticated contact page should surface the weekly public trust pulse.");
    Assert(authenticatedContactModel!.SignedInStatus!.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "authenticated contact page should surface who-can-get-it-now posture next to support intake.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedContactModel!.SupportIntake!.DefaultInstallationId), "authenticated contact page should prefill install-aware support context when a linked install exists.");
    Assert(authenticatedContactModel.SupportIntake.ContextHint?.Contains("linked install", StringComparison.OrdinalIgnoreCase) == true, "authenticated contact page should explain where the prefilled install context came from.");
    Assert(string.Equals(authenticatedContactModel.SupportIntake.DefaultReleaseChannel, "preview", StringComparison.Ordinal), "authenticated contact page should prefill the install release channel.");
    Assert(string.Equals(authenticatedContactModel.SupportIntake.DefaultHeadId, "avalonia", StringComparison.Ordinal), "authenticated contact page should prefill the shipped desktop head.");
    Assert(string.Equals(authenticatedContactModel.SupportIntake.DefaultArch, "x64", StringComparison.Ordinal), "authenticated contact page should prefill the install architecture.");
    authenticatedLandingController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?kind=install_help&title=Mobile%20follow-through%20needs%20grounded%20runtime&summary=Scene%20resume%20needs%20support%20review&detail=Session%3A%20session-redmond&sessionId=session-redmond&sceneId=scene-redmond&runtime=sr6.preview.v1&bundle=bundle-redmond");
    var queryPrefilledContactPage = await authenticatedLandingController.ContactPage(CancellationToken.None) as ViewResult;
    var queryPrefilledContactModel = queryPrefilledContactPage?.Model as TrustPageViewModel;
    Assert(queryPrefilledContactModel?.SupportIntake is not null, "query-prefilled contact page should keep the first-party support intake intact.");
    Assert(queryPrefilledContactModel?.SignedInStatus is not null, "query-prefilled contact page should keep the shared signed-in trust status intact.");
    Assert(queryPrefilledContactModel?.TrustPulse is not null, "query-prefilled contact page should keep the weekly public trust pulse intact.");
    Assert(string.Equals(queryPrefilledContactModel!.SupportIntake!.DefaultKind, SupportCaseKinds.InstallHelp, StringComparison.Ordinal), "query-prefilled contact page should preserve the requested support case type.");
    Assert(string.Equals(queryPrefilledContactModel.SupportIntake.DefaultTitle, "Mobile follow-through needs grounded runtime", StringComparison.Ordinal), "query-prefilled contact page should preserve the requested support title.");
    Assert(string.Equals(queryPrefilledContactModel.SupportIntake.DefaultSummary, "Scene resume needs support review", StringComparison.Ordinal), "query-prefilled contact page should preserve the requested support summary.");
    Assert(queryPrefilledContactModel.SupportIntake.DefaultDetail?.Contains("session-redmond", StringComparison.Ordinal) == true, "query-prefilled contact page should preserve the requested support detail.");
    Assert(queryPrefilledContactModel.SupportIntake.ContextHint?.Contains("scene scene-redmond", StringComparison.OrdinalIgnoreCase) == true, "query-prefilled contact page should surface the follow-through scene context.");
    authenticatedLandingController.ControllerContext.HttpContext.Request.QueryString = QueryString.Empty;
    var contactSubmittedPage = await authenticatedLandingController.ContactSubmittedPage(supportCase.CaseId, CancellationToken.None) as ViewResult;
    var contactSubmittedModel = contactSubmittedPage?.Model as SupportSubmittedPageViewModel;
    Assert(contactSubmittedModel is not null && string.Equals(contactSubmittedModel.CaseId, supportCase.CaseId, StringComparison.Ordinal), "contact submitted route should render a stable support confirmation page.");
    Assert(contactSubmittedModel!.Attachments.Count == 1, "contact submitted route should surface saved support attachments for signed-in reporters.");
    Assert(contactSubmittedModel.TrackedCaseSummary is not null && contactSubmittedModel.TrackedCaseSummary.NextSafeAction.Contains("Update", StringComparison.OrdinalIgnoreCase), "contact confirmation should keep the next safe support action visible for signed-in reporters.");
    Assert(contactSubmittedModel.TrackedCaseSummary!.FollowUpLaneSummary.Contains("Account > Support", StringComparison.Ordinal), "contact confirmation should surface the signed-in follow-up lane.");
    Assert(contactSubmittedModel.TrackedCaseSummary.AffectedInstallSummary?.Contains("install-smoke-001", StringComparison.Ordinal) == true, "contact confirmation should keep the affected install attached to the tracked case.");
    Assert(contactSubmittedModel.TrustPulse is not null, "contact confirmation should keep the weekly public trust pulse visible after support intake.");
    Assert(contactSubmittedModel.SignedInStatus is not null, "contact confirmation should keep the shared signed-in trust status visible after support intake.");
    Assert(contactSubmittedModel.SignedInStatus!.Rows.Any(static row => string.Equals(row.Label, "Who can get it now", StringComparison.Ordinal) && row.Value.Contains("Signed-in handoff", StringComparison.Ordinal)), "contact confirmation should keep the signed-in access posture attached to the submitted case.");
    Assert(authenticatedHomeModel.CampaignSpine.RulesNavigator.Count >= 1, "signed-in home should surface grounded rules navigator answers.");
    Assert(authenticatedHomeModel.CampaignSpine.CreatorPublications.Count >= 1, "signed-in home should surface creator publication posture.");
    Assert(!string.IsNullOrWhiteSpace(publishedHomePublication?.TrustSummary), "signed-in home should keep creator-publication trust reasoning attached.");
    Assert(!string.IsNullOrWhiteSpace(publishedHomePublication?.ComparisonSummary), "signed-in home should keep creator-publication comparison guidance attached.");
    Assert(!string.IsNullOrWhiteSpace(publishedHomePublication?.NextSafeAction), "signed-in home should keep creator-publication next-step truth attached.");
    Assert(!string.IsNullOrWhiteSpace(publishedHomePublication?.CampaignReturnSummary), "signed-in home should keep creator-publication return truth attached.");
    Assert(!string.IsNullOrWhiteSpace(publishedHomePublication?.SupportClosureSummary), "signed-in home should keep creator-publication support closure attached.");
    Assert(!string.IsNullOrWhiteSpace(publishedHomePublication?.ModerationSummary), "signed-in home should keep creator-publication moderation posture attached.");
    Assert(!string.IsNullOrWhiteSpace(publishedHomePublication?.BuildHandoffId), "signed-in home should keep the related build handoff attached to creator publication follow-through.");
    Assert(authenticatedHomeModel.CampaignSpine.MigrationReceipts.Count >= 1, "signed-in home should surface migration receipt truth.");
    Assert(authenticatedHomeModel.InstallLinking.ClaimedInstallations?.Any(static item => string.Equals(item.Platform, "linux", StringComparison.OrdinalIgnoreCase)) == true, "signed-in home should surface claimed install posture.");
    var accessHomePage = await authenticatedLandingController.HomePage("access", CancellationToken.None) as ViewResult;
    var accessHomeModel = accessHomePage?.Model as HomePageViewModel;
    Assert(string.Equals(accessHomeModel?.CurrentSection, "access", StringComparison.Ordinal), "home access route should render the access section.");
    Assert(string.Equals(accessHomeModel?.Chrome.Title, "Home · Access", StringComparison.Ordinal), "home access route should project its own chrome title.");
    Assert(accessHomeModel?.SignedInStatus is not null, "home access route should keep the shared signed-in trust panel available.");
    var workHomePage = await authenticatedLandingController.HomePage("work", CancellationToken.None) as ViewResult;
    var workHomeModel = workHomePage?.Model as HomePageViewModel;
    Assert(string.Equals(workHomeModel?.CurrentSection, "work", StringComparison.Ordinal), "home work route should render the work section.");
    Assert(string.Equals(workHomeModel?.Chrome.Title, "Home · Work", StringComparison.Ordinal), "home work route should project its own chrome title.");
    Assert(workHomeModel?.SignedInStatus is not null, "home work route should keep the shared signed-in trust panel available.");
    Assert(!string.IsNullOrWhiteSpace(workHomeModel?.LeadWorkspaceServerPlane?.WorkspaceState.Label), "home work route should keep the bounded workspace state visible.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.ChangePackets.Count >= 1, "home work route should keep the what-changed packet tied to a real change packet.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "prep_launch", StringComparison.Ordinal)) == true, "home work route should keep governed prep-launch receipts on the bounded what-changed rail.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "travel_prefetch", StringComparison.Ordinal)) == true, "home work route should keep staged travel-prefetch receipts on the bounded what-changed rail.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "aftermath_recap", StringComparison.Ordinal)) == true, "home work route should keep aftermath recap packages on the bounded what-changed rail.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.ChangePackets.Any(item => string.Equals(item.Kind, "replay_package", StringComparison.Ordinal)) == true, "home work route should keep replay packages on the bounded what-changed rail.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.PrepLibrary.Packets.Count >= 3, "home work route should keep the governed prep library visible.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.TravelMode.PrefetchInventorySummary.Contains("governed prep packet", StringComparison.Ordinal) == true, "home work route should keep bounded prep-carrying travel inventory visible.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.AftermathPackages.Any(item => string.Equals(item.PackageId, aftermathPackagePayload!.PackageId, StringComparison.Ordinal)) == true, "home work route should keep aftermath recap packages visible on the lead workspace spine.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.AftermathPackages.Any(item => string.Equals(item.PackageId, replayTimelinePayload!.PackageId, StringComparison.Ordinal)) == true, "home work route should keep replay packages visible on the lead workspace spine.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.Consequences.Count >= 1, "home work route should keep governed consequence follow-through visible on the lead workspace spine.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.CampaignMemory is not null, "home work route should keep the bounded campaign-memory projection visible on the lead workspace spine.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf.Any(item => string.Equals(item.EntryId, aftermathPackagePayload!.PackageId, StringComparison.Ordinal)) == true, "home work route should keep the aftermath package attached to the bounded return shelf.");
    var recapShelfPayload = workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf
        .FirstOrDefault(item => string.Equals(item.EntryId, aftermathPackagePayload!.PackageId, StringComparison.Ordinal));
    Assert(recapShelfPayload is not null, "home work route should surface the generated aftermath package on the richer recap-shelf projection.");
    Assert(recapShelfPayload?.Audience.Contains("creator", StringComparison.OrdinalIgnoreCase) == true, "home work route should mark the lead aftermath artifact as usable from the creator shelf as well as the campaign shelf.");
    Assert(!string.IsNullOrWhiteSpace(recapShelfPayload?.OwnershipSummary), "home work route should keep explicit artifact ownership posture attached to the recap shelf.");
    Assert(recapShelfPayload?.PublicationSummary?.Contains("publication shelf", StringComparison.OrdinalIgnoreCase) == true, "home work route should explain that the same artifact already feeds shared publication posture.");
    Assert(!string.IsNullOrWhiteSpace(recapShelfPayload?.CreatorPublicationId), "home work route should keep the linked creator-publication id attached to the recap shelf entry.");
    Assert(!string.IsNullOrWhiteSpace(recapShelfPayload?.NextSafeAction), "home work route should keep the next safe shelf action attached to the recap shelf entry.");
    var publishedRecapShelfPayload = workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf
        .FirstOrDefault(item => string.Equals(item.CreatorPublicationId, publicationId, StringComparison.Ordinal));
    Assert(publishedRecapShelfPayload is not null, "home work route should keep the recap entry linked to the published shared publication on the bounded return shelf.");
    Assert(string.Equals(publishedRecapShelfPayload?.PublicationState, "published", StringComparison.Ordinal), "home work route should carry published shared-publication state on the recap entry linked to the live publication.");
    Assert(string.Equals(publishedRecapShelfPayload?.TrustBand, "curated-live", StringComparison.Ordinal), "home work route should carry live trust ranking on the recap entry linked to the published shared publication.");
    Assert(publishedRecapShelfPayload?.Discoverable == true, "home work route should keep the recap entry linked to the live publication discoverable.");
    var publishedPrimerShelfPayload = workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf
        .FirstOrDefault(item => string.Equals(item.CreatorPublicationId, primerPublicationId, StringComparison.Ordinal));
    Assert(publishedPrimerShelfPayload is not null, "home work route should keep the primer entry linked to the published shared publication on the bounded return shelf.");
    Assert(string.Equals(publishedPrimerShelfPayload?.PublicationState, "published", StringComparison.Ordinal), "home work route should carry published shared-publication state on the primer entry linked to the live publication.");
    Assert(publishedPrimerShelfPayload?.Discoverable == true, "home work route should keep the primer entry linked to the live publication discoverable.");
    var publishedRunModuleShelfPayload = workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf
        .FirstOrDefault(item => string.Equals(item.CreatorPublicationId, runModulePublicationId, StringComparison.Ordinal));
    Assert(publishedRunModuleShelfPayload is not null, "home work route should keep the run-module entry linked to the published shared publication on the bounded return shelf.");
    Assert(string.Equals(publishedRunModuleShelfPayload?.PublicationState, "published", StringComparison.Ordinal), "home work route should carry published shared-publication state on the run-module entry linked to the live publication.");
    Assert(publishedRunModuleShelfPayload?.Discoverable == true, "home work route should keep the run-module entry linked to the live publication discoverable.");
    var publishedDossierShelfPayload = workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf
        .FirstOrDefault(item => string.Equals(item.CreatorPublicationId, dossierPublicationId, StringComparison.Ordinal));
    Assert(publishedDossierShelfPayload is not null, "home work route should keep the dossier entry linked to the published shared publication on the bounded return shelf.");
    Assert(string.Equals(publishedDossierShelfPayload?.PublicationState, "published", StringComparison.Ordinal), "home work route should carry published shared-publication state on the dossier entry linked to the live publication.");
    Assert(publishedDossierShelfPayload?.Discoverable == true, "home work route should keep the dossier entry linked to the live publication discoverable.");
    Assert(workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf.Any(item => string.Equals(item.EntryId, replayTimelinePayload!.PackageId, StringComparison.Ordinal)) == true, "home work route should keep the replay package attached to the bounded return shelf.");
    var replayWorkHomeShelfPayload = workHomeModel?.LeadWorkspaceServerPlane?.RecapShelf
        .FirstOrDefault(item => string.Equals(item.EntryId, replayTimelinePayload!.PackageId, StringComparison.Ordinal));
    Assert(replayWorkHomeShelfPayload is not null, "home work route should surface the replay package on the richer recap-shelf projection.");
    Assert(replayWorkHomeShelfPayload?.Audience.Contains("creator", StringComparison.OrdinalIgnoreCase) == true, "home work route should mark replay artifacts as usable from the creator shelf as well as the campaign shelf.");
    Assert(!string.IsNullOrWhiteSpace(replayWorkHomeShelfPayload?.CreatorPublicationId), "home work route should keep the linked creator-publication id attached to replay shelf entries.");
    Assert(!string.IsNullOrWhiteSpace(recapShelfPayload?.ProvenanceSummary), "home work route should keep explicit provenance attached to the recap shelf entry.");
    Assert(!string.IsNullOrWhiteSpace(recapShelfPayload?.AuditSummary), "home work route should keep explicit audit posture attached to the recap shelf entry.");
    Assert(!string.IsNullOrWhiteSpace(workHomeModel!.CampaignSpine.Workspaces[0].ReturnSummary), "home work route should keep the shared campaign view tied to a real return summary.");
    var publishedWorkHomePublication = workHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, publicationId, StringComparison.Ordinal));
    Assert(publishedWorkHomePublication is not null, "home work route should keep the explicitly published creator publication visible on the shared home projection.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.ProvenanceSummary), "home work route should keep publication trust visible on the shared home projection.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.TrustBand), "home work route should keep publication trust ranking visible on the shared home projection.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.TrustSummary), "home work route should keep creator-publication trust reasoning visible on the shared home projection.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.ComparisonSummary), "home work route should keep creator-publication comparison guidance visible on the shared home projection.");
    Assert(publishedWorkHomePublication?.Discoverable == true, "home work route should carry discoverable creator-publication posture once publication is live.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.NextSafeAction), "home work route should keep creator-publication next-step truth visible on the shared home projection.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.CampaignReturnSummary), "home work route should keep creator-publication return truth visible on the shared home projection.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.SupportClosureSummary), "home work route should keep creator-publication support closure visible on the shared home projection.");
    Assert(!string.IsNullOrWhiteSpace(publishedWorkHomePublication?.ModerationSummary), "home work route should keep creator-publication moderation posture visible on the shared home projection.");
    var publishedPrimerWorkHomePublication = workHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, primerPublicationId, StringComparison.Ordinal));
    Assert(publishedPrimerWorkHomePublication is not null, "home work route should keep the explicitly published primer publication visible on the shared home projection.");
    Assert(string.Equals(publishedPrimerWorkHomePublication?.Kind, "primer", StringComparison.Ordinal), "home work route should preserve the primer publication kind.");
    Assert(publishedPrimerWorkHomePublication?.Discoverable == true, "home work route should carry discoverable primer publication posture once publication is live.");
    var publishedRunModuleWorkHomePublication = workHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, runModulePublicationId, StringComparison.Ordinal));
    Assert(publishedRunModuleWorkHomePublication is not null, "home work route should keep the explicitly published run-module publication visible on the shared home projection.");
    Assert(string.Equals(publishedRunModuleWorkHomePublication?.Kind, "run_module", StringComparison.Ordinal), "home work route should preserve the run-module publication kind.");
    Assert(publishedRunModuleWorkHomePublication?.Discoverable == true, "home work route should carry discoverable run-module publication posture once publication is live.");
    var publishedDossierWorkHomePublication = workHomeModel.CampaignSpine.CreatorPublications
        .FirstOrDefault(item => string.Equals(item.PublicationId, dossierPublicationId, StringComparison.Ordinal));
    Assert(publishedDossierWorkHomePublication is not null, "home work route should keep the explicitly published dossier publication visible on the shared home projection.");
    Assert(string.Equals(publishedDossierWorkHomePublication?.Kind, "dossier", StringComparison.Ordinal), "home work route should preserve the dossier publication kind.");
    Assert(publishedDossierWorkHomePublication?.Discoverable == true, "home work route should carry discoverable dossier publication posture once publication is live.");
    Assert(workHomeModel.CampaignSpine.Restore.ClaimedDevices.Count >= 1, "home work route should keep the claimed-device return packet visible on the shared home projection.");
    Assert(workHomeModel.CampaignSpine.Restore.ClaimedDevices.Any(item => item.RestoreSummary.Contains("bounded offline use", StringComparison.Ordinal)), "home work route should surface bounded offline prefetch on the claimed-device return card.");

    AftermathRecapPackageProjection? retainedAftermathPayload = null;
    for (var index = 0; index < 70; index++)
    {
        var retainedAftermathResult = await campaignSpineController.GenerateMyCampaignWorkspaceAftermathRecapPackage(
            workspaceId,
            new AftermathRecapPackageRequest(
                RunId: runId,
                PackageKind: "session_recap",
                Title: $"Retention session recap {index}",
                Note: $"Retention overflow audit {index}"),
            CancellationToken.None);
        retainedAftermathPayload = (retainedAftermathResult.Result as OkObjectResult)?.Value as AftermathRecapPackageProjection ?? retainedAftermathResult.Value;
    }
    Assert(retainedAftermathPayload is not null, "campaign spine aftermath generation should keep returning packages after the retention cap is exceeded.");
    var retainedWorkHomePage = await authenticatedLandingController.HomePage("work", CancellationToken.None) as ViewResult;
    var retainedWorkHomeModel = retainedWorkHomePage?.Model as HomePageViewModel;
    Assert(retainedWorkHomeModel?.LeadWorkspaceServerPlane?.AftermathPackages.Any(item => string.Equals(item.PackageId, retainedAftermathPayload!.PackageId, StringComparison.Ordinal)) == true, "home work route should keep the newest aftermath recap package visible after the retention cap is exceeded.");
    var reloadedCampaignStore = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
    var reloadedCampaignSpine = new CampaignSpineService(reloadedCampaignStore, new WorkspaceLifecyclePolicyService(configuration), new CampaignArtifactRegistryBridge(reloadedCampaignStore));
    var reloadedWorkspace = reloadedCampaignSpine.GetWorkspace(linkedUser, workspaceId);
    var reloadedAftermathPackage = NotNull(
        reloadedWorkspace?.AftermathPackages?.FirstOrDefault(item => string.Equals(item.PackageId, retainedAftermathPayload!.PackageId, StringComparison.Ordinal)),
        "campaign spine aftermath packages should survive a community-store reload.");
    Assert(string.Equals(reloadedAftermathPackage.ArtifactId, retainedAftermathPayload!.ArtifactId, StringComparison.Ordinal), "campaign spine aftermath packages should preserve the durable artifact id across reload.");
    Assert(!string.IsNullOrWhiteSpace(reloadedAftermathPackage.ProvenanceSummary), "campaign spine aftermath packages should preserve artifact provenance across reload.");
    Assert(!string.IsNullOrWhiteSpace(reloadedAftermathPackage.AuditSummary), "campaign spine aftermath packages should preserve artifact audit posture across reload.");

    var transferTargetUser = accounts.EnsureUser("subject.outsider", "Outsider Demo");
    var transferGroup = groups.CreateGroup(new CreateGroupRequest(
        SubjectId: "subject.demo",
        Name: "Thursday Crew Relay",
        GroupType: "campaign",
        Visibility: "group",
        Capabilities: null));
    var transferCampaign = groups.GetOrCreateCampaign(transferGroup.GroupId, "hub", "Thursday Crew Relay");
    var sourceOwnerSummary = campaignSpine.GetAccountSummary(linkedUser);
    var sourceDossier = sourceOwnerSummary.Dossiers.FirstOrDefault();
    Assert(sourceDossier is not null, "signed-in owners should have a governed dossier before a GM moves roster state.");
    var rosterTransferResult = await campaignSpineController.TransferMyRoster(
        new RosterTransferRequest(
            DossierId: sourceDossier!.DossierId,
            TargetGroupId: transferGroup.GroupId,
            TargetCampaignId: transferCampaign.CampaignId,
            TargetCampaignTitle: transferCampaign.Title,
            TargetOwnerUserId: transferTargetUser.UserId,
            Note: "GM handoff for the next run."),
        CancellationToken.None);
    var rosterTransferPayload = (rosterTransferResult.Result as OkObjectResult)?.Value as RosterTransferProjection ?? rosterTransferResult.Value;
    var rosterTransferStatusCode = (rosterTransferResult.Result as ObjectResult)?.StatusCode;
    var rosterTransferProblemDetail = ((rosterTransferResult.Result as ObjectResult)?.Value as ProblemDetails)?.Detail;
    Assert(rosterTransferPayload is not null && string.Equals(rosterTransferPayload.DossierId, sourceDossier.DossierId, StringComparison.Ordinal), $"campaign spine transfer api should return the moved dossier receipt. status={rosterTransferStatusCode?.ToString() ?? "<null>"} detail={rosterTransferProblemDetail ?? "<none>"}");
    Assert(string.Equals(rosterTransferPayload!.CurrentOwnerUserId, transferTargetUser.UserId, StringComparison.Ordinal), "campaign spine transfer api should record the new owner on the transfer receipt.");
    Assert(rosterTransferPayload.Summary.Contains("ownership transferred", StringComparison.OrdinalIgnoreCase), "transfer summary should make explicit when governed ownership changes.");
    Assert(groups.GetGroup(transferGroup.GroupId)?.Memberships.Any(item => string.Equals(item.UserId, transferTargetUser.UserId, StringComparison.OrdinalIgnoreCase)) == true, "target owner should be added to the target roster group during transfer.");

    var rosterTargetIdentityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(request =>
    {
        var body = request.Content is null ? string.Empty : request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        return body.Contains("outsider-token", StringComparison.Ordinal)
            ? JsonResponse(new IdentityIntrospectionResponse(true, "session-outsider", "subject.outsider", new[] { "player" }, DateTimeOffset.UtcNow.AddHours(1)))
            : JsonResponse(new IdentityIntrospectionResponse(false, null, null, Array.Empty<string>(), null), HttpStatusCode.Unauthorized);
    })), configuration);
    var outsiderCampaignSpineController = new CampaignSpineController(
        rosterTargetIdentityClient,
        accounts,
        installLinking,
        campaignSpine,
        workspaceServerPlane)
    {
        ControllerContext = AuthenticatedControllerContext("outsider-token")
    };
    var outsiderCampaignSummaryResult = await outsiderCampaignSpineController.GetMyCampaignSummary(CancellationToken.None);
    var outsiderCampaignSummaryPayload = (outsiderCampaignSummaryResult.Result as OkObjectResult)?.Value as AccountCampaignSummary ?? outsiderCampaignSummaryResult.Value;
    Assert(outsiderCampaignSummaryPayload is not null && outsiderCampaignSummaryPayload.Dossiers.Any(item => string.Equals(item.DossierId, sourceDossier.DossierId, StringComparison.Ordinal) && string.Equals(item.OwnerUserId, transferTargetUser.UserId, StringComparison.Ordinal)), "new owner should see the transferred dossier on their campaign summary.");
    var outsiderWorkspace = outsiderCampaignSummaryPayload!.Workspaces.FirstOrDefault(item => string.Equals(item.CampaignId, transferCampaign.CampaignId, StringComparison.OrdinalIgnoreCase));
    Assert(outsiderWorkspace is not null && outsiderWorkspace.RosterTransfers?.Any(item => string.Equals(item.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true, "target workspace should surface the roster-transfer audit receipt.");
    var outsiderWorkspaceServerPlaneResult = await outsiderCampaignSpineController.GetMyCampaignWorkspaceServerPlane(outsiderWorkspace!.WorkspaceId, CancellationToken.None);
    var outsiderWorkspaceServerPlanePayload = (outsiderWorkspaceServerPlaneResult.Result as OkObjectResult)?.Value as CampaignWorkspaceServerPlaneProjection ?? outsiderWorkspaceServerPlaneResult.Value;
    Assert(outsiderWorkspaceServerPlanePayload is not null && outsiderWorkspaceServerPlanePayload.RosterTransfers.Any(item => string.Equals(item.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)), "target workspace server plane should preserve the roster-transfer receipt.");
    Assert(outsiderWorkspaceServerPlanePayload!.ChangePackets.Any(item => string.Equals(item.Kind, "roster_transfer", StringComparison.Ordinal)), "target workspace server plane should project roster transfer as a first-class change packet.");
    var operatorWorkPage = await accountController.AccountPage(section: "work", caseId: null, CancellationToken.None) as ViewResult;
    var operatorWorkModel = operatorWorkPage?.Model as AccountPageViewModel;
    Assert(operatorWorkModel?.CampaignSpine.CommunityOperations.Any(item => item.RecentRosterTransfers?.Any(transfer => string.Equals(transfer.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true) == true, "account work should keep recent governed roster moves visible on the operator rail after a transfer.");
    var postTransferWorkHomePage = await authenticatedLandingController.HomePage("work", CancellationToken.None) as ViewResult;
    var postTransferWorkHomeModel = postTransferWorkHomePage?.Model as HomePageViewModel;
    Assert(postTransferWorkHomeModel?.LeadWorkspaceServerPlane?.RosterTransfers.Any(item => string.Equals(item.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true, "home work should keep the governed roster-transfer receipt visible on the lead workspace spine after a transfer.");
    Assert(postTransferWorkHomeModel?.CampaignSpine.CommunityOperations.Any(item => item.RecentRosterTransfers?.Any(transfer => string.Equals(transfer.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true) == true, "home work should keep the same governed roster-move audit visible on the operator posture card after a transfer.");

    var outsiderTransferDenied = await outsiderCampaignSpineController.TransferMyRoster(
        new RosterTransferRequest(
            DossierId: sourceDossier.DossierId,
            TargetGroupId: transferGroup.GroupId,
            TargetCampaignId: transferCampaign.CampaignId,
            TargetOwnerUserId: linkedUser.UserId,
            Note: "Attempted unauthorized return."),
        CancellationToken.None);
    Assert((outsiderTransferDenied.Result as ObjectResult)?.StatusCode == StatusCodes.Status403Forbidden, "non-operator target owners should not be allowed to move governed roster state.");

    var progressHtml = (await progressController.ProgressPage(CancellationToken.None)).Content ?? string.Empty;
    Assert(progressHtml.Contains("Core Rules Engine", StringComparison.Ordinal), "progress page should render the generated product-part report");
    Assert(progressHtml.Contains("/api/public/progress-poster.svg", StringComparison.Ordinal), "progress page should render against the hosted poster route");
    Assert(progressHtml.Contains("How to participate", StringComparison.Ordinal), "progress page should expose the participation section");
    Assert(progressHtml.Contains("Chummer public navigation", StringComparison.Ordinal), "progress page should render inside the shared public shell");
    Assert(progressHtml.Contains("progress-shell-nav-current", StringComparison.Ordinal) && progressHtml.Contains(">Progress<", StringComparison.Ordinal), "progress page shell should mark the progress route as current in navigation");
    Assert(progressHtml.Contains("href=\"/participate\"", StringComparison.Ordinal), "progress page navigation should link back into the public participation flow");

    var progressJson = progressController.ProgressReport().Content ?? string.Empty;
    using (var progressDocument = JsonDocument.Parse(progressJson))
    {
        Assert(progressDocument.RootElement.GetProperty("overall_progress_percent").GetInt32() > 0, "progress report JSON should expose weighted progress");
        Assert(progressDocument.RootElement.GetProperty("parts").GetArrayLength() >= 1, "progress report JSON should expose public product parts");
    }

    var progressPoster = progressController.ProgressPoster().Content ?? string.Empty;
    Assert(progressPoster.Contains("<svg", StringComparison.OrdinalIgnoreCase), "progress poster endpoint should serve SVG content");

    var weeklyPulseJson = progressController.WeeklyPulse().Content ?? string.Empty;
    using (var weeklyPulseDocument = JsonDocument.Parse(weeklyPulseJson))
    {
        Assert(string.Equals(weeklyPulseDocument.RootElement.GetProperty("contract_name").GetString(), "chummer.weekly_product_pulse", StringComparison.Ordinal), "weekly pulse endpoint should serve the mirrored weekly pulse artifact.");
        Assert(
            weeklyPulseDocument.RootElement.TryGetProperty("active_wave", out var activeWaveElement)
            && !string.IsNullOrWhiteSpace(activeWaveElement.GetString())
            && activeWaveElement.GetString()!.Contains("Wins", StringComparison.OrdinalIgnoreCase),
            "weekly pulse endpoint should expose the current active wave from the mirrored design pulse.");
        Assert(weeklyPulseDocument.RootElement.TryGetProperty("next_checkpoint_question", out JsonElement checkpointQuestion)
            && !string.IsNullOrWhiteSpace(checkpointQuestion.GetString()), "weekly pulse endpoint should keep the next checkpoint question visible for the current wave.");
        Assert(weeklyPulseDocument.RootElement.GetProperty("supporting_signals").TryGetProperty("closure_health", out JsonElement closureHealth)
            && !string.IsNullOrWhiteSpace(closureHealth.GetProperty("summary").GetString()), "weekly pulse endpoint should expose closure-health evidence in supporting signals.");
        Assert(weeklyPulseDocument.RootElement.GetProperty("supporting_signals").TryGetProperty("adoption_health", out JsonElement adoptionHealth)
            && !string.IsNullOrWhiteSpace(adoptionHealth.GetProperty("summary").GetString()), "weekly pulse endpoint should expose adoption-health evidence in supporting signals.");
        Assert(weeklyPulseDocument.RootElement.GetProperty("supporting_signals").TryGetProperty("progress_trend", out JsonElement progressTrend)
            && progressTrend.GetProperty("samples").GetArrayLength() >= 2, "weekly pulse endpoint should expose measured progress-trend samples in supporting signals.");
        Assert(!weeklyPulseDocument.RootElement.TryGetProperty("active_nine_month_checkpoint", out _), "weekly pulse endpoint should mirror the current pulse artifact without the retired nine-month checkpoint block.");
    }

    var privacyBoundaryJson = progressController.PrivacyBoundaries().Content ?? string.Empty;
    using (var privacyBoundaryDocument = JsonDocument.Parse(privacyBoundaryJson))
    {
        Assert(string.Equals(privacyBoundaryDocument.RootElement.GetProperty("contractName").GetString(), "chummer.public_privacy_boundaries", StringComparison.Ordinal), "privacy-boundary endpoint should serve the mirrored privacy-boundary artifact.");
        Assert(privacyBoundaryDocument.RootElement.GetProperty("domains").GetArrayLength() >= 4, "privacy-boundary endpoint should keep all public trust domains visible.");
        Assert(privacyBoundaryDocument.RootElement.GetProperty("surfaceRules").EnumerateArray().Any(item => string.Equals(item.GetProperty("label").GetString(), "Provider-backed help", StringComparison.Ordinal)), "privacy-boundary endpoint should keep the provider-backed help rule explicit.");
    }

    var artifactShelfReplayResult = await campaignSpineController.GenerateMyCampaignWorkspaceAftermathRecapPackage(
        workspaceId,
        new AftermathRecapPackageRequest(
            RunId: runId,
            PackageKind: "replay_timeline",
            Title: null,
            Note: "Refresh replay posture immediately before signed-in artifact shelf proof."),
        CancellationToken.None);
    var artifactShelfReplayPayload = (artifactShelfReplayResult.Result as OkObjectResult)?.Value as AftermathRecapPackageProjection ?? artifactShelfReplayResult.Value;
    Assert(artifactShelfReplayPayload is not null, "signed-in artifact shelf proof should be able to mint a fresh replay package before shelf filtering is evaluated.");
    var artifactsView = await controller.ArtifactsPage(CancellationToken.None) as ViewResult;
    var artifactsModel = artifactsView?.Model as ShelfPageViewModel;
    Assert(
        artifactsModel is not null
        && artifactsModel.Items.Any(static card =>
            string.Equals(card.Card.Id, "artifact_runsite_pack", StringComparison.Ordinal)
            && !string.Equals(card.Action.Href, "/artifacts", StringComparison.Ordinal)),
        "artifacts shelf should point teaser cards at deliberate related detail pages");
    Assert(artifactsModel!.TrustPulse is not null, "guest artifacts shelf should surface the weekly public trust pulse.");
    Assert(artifactsModel.PublicCreatorPublications?.Count > 0, "guest artifacts shelf should surface governed public creator discovery once a creator packet is actually published.");
    Assert(string.Equals(artifactsModel.PublicCreatorPublications?[0].PublicationStatus, "published", StringComparison.Ordinal), "guest artifacts shelf should carry live published creator-publication posture on the public discovery cards.");
    Assert(artifactsModel.PublicCreatorPublications?[0].Discoverable == true, "guest artifacts shelf should keep public creator discovery limited to discoverable live packets.");
    Assert(!string.IsNullOrWhiteSpace(artifactsModel.PublicCreatorPublications?[0].TrustSummary), "guest artifacts shelf should keep trust reasoning attached to public creator discovery.");
    Assert(!string.IsNullOrWhiteSpace(artifactsModel.PublicCreatorPublications?[0].ComparisonSummary), "guest artifacts shelf should keep creator-comparison guidance attached to public creator discovery.");
    Assert(!string.IsNullOrWhiteSpace(artifactsModel.PublicCreatorPublications?[0].LineageSummary), "guest artifacts shelf should keep lineage posture attached to public creator discovery.");
    Assert(!string.IsNullOrWhiteSpace(artifactsModel.PublicCreatorPublications?[0].ModerationSummary), "guest artifacts shelf should keep moderation-watch posture attached to public creator discovery.");
    var publicPrimerPublication = artifactsModel.PublicCreatorPublications?.FirstOrDefault(item => string.Equals(item.PublicationId, primerPublicationId, StringComparison.Ordinal));
    Assert(publicPrimerPublication is not null, "guest artifacts shelf should surface the published primer on governed public discovery.");
    Assert(string.Equals(publicPrimerPublication?.Kind, "primer", StringComparison.Ordinal), "guest artifacts shelf should preserve the primer publication kind on the public discovery rail.");
    Assert(publicPrimerPublication?.Discoverable == true, "guest artifacts shelf should keep the published primer discoverable on the public discovery rail.");
    var publicRunModulePublication = artifactsModel.PublicCreatorPublications?.FirstOrDefault(item => string.Equals(item.PublicationId, runModulePublicationId, StringComparison.Ordinal));
    Assert(publicRunModulePublication is not null, "guest artifacts shelf should surface the published run module on governed public discovery.");
    Assert(string.Equals(publicRunModulePublication?.Kind, "run_module", StringComparison.Ordinal), "guest artifacts shelf should preserve the run-module publication kind on the public discovery rail.");
    Assert(publicRunModulePublication?.Discoverable == true, "guest artifacts shelf should keep the published run module discoverable on the public discovery rail.");
    var publicDossierPublication = artifactsModel.PublicCreatorPublications?.FirstOrDefault(item => string.Equals(item.PublicationId, dossierPublicationId, StringComparison.Ordinal));
    Assert(publicDossierPublication is not null, "guest artifacts shelf should surface the published dossier on governed public discovery.");
    Assert(string.Equals(publicDossierPublication?.Kind, "dossier", StringComparison.Ordinal), "guest artifacts shelf should preserve the dossier publication kind on the public discovery rail.");
    Assert(publicDossierPublication?.Discoverable == true, "guest artifacts shelf should keep the published dossier discoverable on the public discovery rail.");
    var publicCreatorDetailView = await controller.CreatorPublicationDetailPage(publicationId, CancellationToken.None) as ViewResult;
    var publicCreatorDetailModel = publicCreatorDetailView?.Model as PublicCreatorPublicationPageViewModel;
    Assert(publicCreatorDetailModel is not null, "guest creator-publication detail should render through the MVC view layer.");
    Assert(string.Equals(publicCreatorDetailModel!.Publication.PublicationId, publicationId, StringComparison.Ordinal), "guest creator-publication detail should load the published creator packet from the governed discovery rail.");
    Assert(string.Equals(publicCreatorDetailModel.Publication.PublicationStatus, "published", StringComparison.Ordinal), "guest creator-publication detail should keep the live published posture.");
    Assert(!string.IsNullOrWhiteSpace(publicCreatorDetailModel.Publication.ComparisonSummary), "guest creator-publication detail should keep creator-comparison guidance visible.");
    Assert(!string.IsNullOrWhiteSpace(publicCreatorDetailModel.Publication.LineageSummary), "guest creator-publication detail should keep lineage posture visible.");
    Assert(!string.IsNullOrWhiteSpace(publicCreatorDetailModel.Publication.ModerationSummary), "guest creator-publication detail should keep moderation-watch posture visible.");
    Assert(publicCreatorDetailModel.TrustPulse is not null, "guest creator-publication detail should surface the shared public trust pulse.");
    Assert(publicCreatorDetailModel.SignedInStatus is null, "guest creator-publication detail should not project install-specific signed-in trust posture.");
    var publicPrimerDetailView = await controller.CreatorPublicationDetailPage(primerPublicationId, CancellationToken.None) as ViewResult;
    var publicPrimerDetailModel = publicPrimerDetailView?.Model as PublicCreatorPublicationPageViewModel;
    Assert(publicPrimerDetailModel is not null, "guest primer publication detail should render through the MVC view layer.");
    Assert(string.Equals(publicPrimerDetailModel!.Publication.PublicationId, primerPublicationId, StringComparison.Ordinal), "guest primer publication detail should load the published primer from the governed discovery rail.");
    Assert(string.Equals(publicPrimerDetailModel.Publication.Kind, "primer", StringComparison.Ordinal), "guest primer publication detail should preserve the primer publication kind.");
    Assert(string.Equals(publicPrimerDetailModel.Publication.PublicationStatus, "published", StringComparison.Ordinal), "guest primer publication detail should keep the live published posture.");
    var publicRunModuleDetailView = await controller.CreatorPublicationDetailPage(runModulePublicationId, CancellationToken.None) as ViewResult;
    var publicRunModuleDetailModel = publicRunModuleDetailView?.Model as PublicCreatorPublicationPageViewModel;
    Assert(publicRunModuleDetailModel is not null, "guest run-module publication detail should render through the MVC view layer.");
    Assert(string.Equals(publicRunModuleDetailModel!.Publication.PublicationId, runModulePublicationId, StringComparison.Ordinal), "guest run-module publication detail should load the published run module from the governed discovery rail.");
    Assert(string.Equals(publicRunModuleDetailModel.Publication.Kind, "run_module", StringComparison.Ordinal), "guest run-module publication detail should preserve the run-module publication kind.");
    Assert(string.Equals(publicRunModuleDetailModel.Publication.PublicationStatus, "published", StringComparison.Ordinal), "guest run-module publication detail should keep the live published posture.");
    var publicDossierDetailView = await controller.CreatorPublicationDetailPage(dossierPublicationId, CancellationToken.None) as ViewResult;
    var publicDossierDetailModel = publicDossierDetailView?.Model as PublicCreatorPublicationPageViewModel;
    Assert(publicDossierDetailModel is not null, "guest dossier publication detail should render through the MVC view layer.");
    Assert(string.Equals(publicDossierDetailModel!.Publication.PublicationId, dossierPublicationId, StringComparison.Ordinal), "guest dossier publication detail should load the published dossier from the governed discovery rail.");
    Assert(string.Equals(publicDossierDetailModel.Publication.Kind, "dossier", StringComparison.Ordinal), "guest dossier publication detail should preserve the dossier publication kind.");
    Assert(string.Equals(publicDossierDetailModel.Publication.PublicationStatus, "published", StringComparison.Ordinal), "guest dossier publication detail should keep the live published posture.");
    Assert(artifactsModel.SignedInStatus is null, "guest artifacts shelf should not project install-specific signed-in trust posture.");
    var authenticatedArtifactsView = await authenticatedLandingController.ArtifactsPage(CancellationToken.None) as ViewResult;
    var authenticatedArtifactsModel = authenticatedArtifactsView?.Model as ShelfPageViewModel;
    Assert(authenticatedArtifactsModel?.TrustPulse is not null, "authenticated artifacts shelf should keep the weekly public trust pulse visible.");
    Assert(authenticatedArtifactsModel?.SignedInStatus is not null, "authenticated artifacts shelf should project the shared signed-in trust status.");
    Assert(authenticatedArtifactsModel?.PublicCreatorPublications?.Count > 0, "authenticated artifacts shelf should keep the same public creator-discovery rail visible above the signed-in overlays.");
    var authenticatedCreatorDetailView = await authenticatedLandingController.CreatorPublicationDetailPage(publicationId, CancellationToken.None) as ViewResult;
    var authenticatedCreatorDetailModel = authenticatedCreatorDetailView?.Model as PublicCreatorPublicationPageViewModel;
    Assert(authenticatedCreatorDetailModel?.SignedInStatus is not null, "authenticated creator-publication detail should project the shared signed-in trust status.");
    Assert(authenticatedArtifactsModel?.SignedInRecapShelf?.Count > 0, "authenticated artifacts shelf should expose a signed-in recap shelf overlay instead of staying public-only.");
    Assert(authenticatedArtifactsModel?.SignedInCreatorPublications?.Count > 0, "authenticated artifacts shelf should expose linked creator-publication posture instead of forcing a separate account detour.");
    var authenticatedRecapShelf = NotNull(authenticatedArtifactsModel!.SignedInRecapShelf, "authenticated artifacts shelf should expose a non-null recap shelf collection.");
    Assert(authenticatedRecapShelf.GroupBy(static item => string.IsNullOrWhiteSpace(item.ArtifactId) ? item.EntryId : item.ArtifactId, StringComparer.OrdinalIgnoreCase).All(group => group.Count() == 1), "authenticated artifacts shelf should dedupe recap artifacts by governed artifact identity.");
    Assert(authenticatedRecapShelf.All(static item => !string.IsNullOrWhiteSpace(item.ProvenanceSummary)), "authenticated artifacts shelf should keep provenance attached to every signed-in recap artifact.");
    Assert(authenticatedRecapShelf.All(static item => !string.IsNullOrWhiteSpace(item.AuditSummary)), "authenticated artifacts shelf should keep audit posture attached to every signed-in recap artifact.");
    Assert(authenticatedRecapShelf.Any(item => string.Equals(item.EntryId, artifactShelfReplayPayload!.PackageId, StringComparison.Ordinal)), "authenticated artifacts shelf should surface replay packages on the signed-in return shelf.");
    var authenticatedReplayArtifact = authenticatedRecapShelf.FirstOrDefault(item => string.Equals(item.EntryId, artifactShelfReplayPayload!.PackageId, StringComparison.Ordinal));
    Assert(authenticatedReplayArtifact?.Audience.Contains("creator", StringComparison.OrdinalIgnoreCase) == true, "authenticated artifacts shelf should keep replay artifacts creator-linked on the shared signed-in shelf.");
    Assert(!string.IsNullOrWhiteSpace(authenticatedReplayArtifact?.CreatorPublicationId), "authenticated artifacts shelf should keep creator-publication linkage attached to replay artifacts.");
    authenticatedLandingController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?view=personal");
    var personalArtifactsView = await authenticatedLandingController.ArtifactsPage(CancellationToken.None) as ViewResult;
    var personalArtifactsModel = personalArtifactsView?.Model as ShelfPageViewModel;
    Assert(string.Equals(personalArtifactsModel?.SignedInArtifactView, "personal", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit personal view filter.");
    Assert(personalArtifactsModel?.SignedInRecapShelf?.Count > 0 && personalArtifactsModel.SignedInRecapShelf.All(static item => item.Audience.Contains("personal", StringComparison.OrdinalIgnoreCase)), "personal artifact view should keep only artifacts that are governable on the personal rail.");
    Assert(personalArtifactsModel?.SignedInCreatorPublications?.Count == 0, "personal artifact view should not blend creator-publication cards into the personal shelf.");
    authenticatedLandingController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?view=campaign");
    var campaignArtifactsView = await authenticatedLandingController.ArtifactsPage(CancellationToken.None) as ViewResult;
    var campaignArtifactsModel = campaignArtifactsView?.Model as ShelfPageViewModel;
    Assert(string.Equals(campaignArtifactsModel?.SignedInArtifactView, "campaign", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit campaign view filter.");
    Assert(campaignArtifactsModel?.SignedInRecapShelf?.Count > 0 && campaignArtifactsModel.SignedInRecapShelf.All(static item => item.Audience.Contains("campaign", StringComparison.OrdinalIgnoreCase)), "campaign artifact view should keep only artifacts that are governable on the campaign rail.");
    Assert(campaignArtifactsModel?.SignedInRecapShelf?.Any(item => string.Equals(item.EntryId, artifactShelfReplayPayload!.PackageId, StringComparison.Ordinal)) == true, "campaign artifact view should keep replay packages on the campaign rail.");
    Assert(campaignArtifactsModel?.SignedInCreatorPublications?.Count == 0, "campaign artifact view should keep creator publication cards off the campaign shelf.");
    authenticatedLandingController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?view=creator");
    var creatorArtifactsView = await authenticatedLandingController.ArtifactsPage(CancellationToken.None) as ViewResult;
    var creatorArtifactsModel = creatorArtifactsView?.Model as ShelfPageViewModel;
    Assert(string.Equals(creatorArtifactsModel?.SignedInArtifactView, "creator", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit creator view filter.");
    Assert(creatorArtifactsModel?.PublicCreatorPublications?.Count > 0, "creator artifact view should keep the public governed creator-discovery rail visible alongside the signed-in overlay.");
    Assert(creatorArtifactsModel?.SignedInCreatorPublications?.Count > 0, "creator artifact view should surface linked creator publications instead of staying empty.");
    Assert(!string.IsNullOrWhiteSpace(creatorArtifactsModel?.SignedInCreatorPublications?[0].TrustSummary), "creator artifact view should keep creator-publication trust reasoning visible.");
    Assert(!string.IsNullOrWhiteSpace(creatorArtifactsModel?.SignedInCreatorPublications?[0].ComparisonSummary), "creator artifact view should keep creator-publication comparison guidance visible.");
    Assert(!string.IsNullOrWhiteSpace(creatorArtifactsModel?.SignedInCreatorPublications?[0].ModerationSummary), "creator artifact view should keep creator-publication moderation posture visible.");
    Assert(creatorArtifactsModel?.SignedInRecapShelf?.All(static item => item.Audience.Contains("creator", StringComparison.OrdinalIgnoreCase) || !string.IsNullOrWhiteSpace(item.CreatorPublicationId)) == true, "creator artifact view should keep only creator-linked artifact lineage on the recap shelf.");
    Assert(creatorArtifactsModel?.SignedInRecapShelf?.Any(item => string.Equals(item.EntryId, artifactShelfReplayPayload!.PackageId, StringComparison.Ordinal)) == true, "creator artifact view should keep replay packages when they are linked into creator publication posture.");
    authenticatedLandingController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?view=shadow");
    var fallbackArtifactsView = await authenticatedLandingController.ArtifactsPage(CancellationToken.None) as ViewResult;
    var fallbackArtifactsModel = fallbackArtifactsView?.Model as ShelfPageViewModel;
    Assert(string.Equals(fallbackArtifactsModel?.SignedInArtifactView, "all", StringComparison.Ordinal), "unknown artifact view filters should fall back to the all-views shelf instead of breaking the route.");
    authenticatedLandingController.ControllerContext.HttpContext.Request.QueryString = QueryString.Empty;
    var statusView = await controller.StatusPage(CancellationToken.None) as ViewResult;
    var statusModel = statusView?.Model as StatusPageViewModel;
    Assert(statusModel?.TrustPulse is not null, "guest status page should surface the weekly public trust pulse.");
    Assert(statusModel?.SignedInStatus is null, "guest status page should not project install-specific signed-in trust posture.");
    Assert(statusModel?.CampaignOsProof is not null, "status page should surface the mirrored campaign-OS local proof.");
    var authenticatedStatusView = await authenticatedLandingController.StatusPage(CancellationToken.None) as ViewResult;
    var authenticatedStatusModel = authenticatedStatusView?.Model as StatusPageViewModel;
    Assert(authenticatedStatusModel?.TrustPulse is not null, "authenticated status page should keep the weekly public trust pulse visible.");
    Assert(authenticatedStatusModel?.SignedInStatus is not null, "authenticated status page should project the shared signed-in trust status.");
    var horizonsView = await controller.HorizonsPage(CancellationToken.None) as ViewResult;
    var horizonsModel = horizonsView?.Model as HorizonsPageViewModel;
    Assert(horizonsModel?.TrustPulse is not null, "guest horizons page should surface the weekly public trust pulse.");
    Assert(horizonsModel?.SignedInStatus is null, "guest horizons page should not project install-specific signed-in trust posture.");
    var authenticatedHorizonsView = await authenticatedLandingController.HorizonsPage(CancellationToken.None) as ViewResult;
    var authenticatedHorizonsModel = authenticatedHorizonsView?.Model as HorizonsPageViewModel;
    Assert(authenticatedHorizonsModel?.TrustPulse is not null, "authenticated horizons page should keep the weekly public trust pulse visible.");
    Assert(authenticatedHorizonsModel?.SignedInStatus is not null, "authenticated horizons page should project the shared signed-in trust status.");

    Assert(participateModel!.SignedInLane.Any(static card => string.Equals(card.Card.GuestHref, "/login?next=/participate/codex", StringComparison.Ordinal)), "participate page should preserve the booster guest-login handoff.");
    Assert(!participateModel.PublicLane.Any(static card => card.Card.Summary.Contains("worker host", StringComparison.OrdinalIgnoreCase)), "public participate copy should not leak worker-host jargon");

    var homeResult = await controller.HomePage(null, CancellationToken.None);
    var homeRedirect = homeResult as RedirectResult;
    Assert(homeRedirect is not null
        && homeRedirect.Url is not null
        && homeRedirect.Url.StartsWith("/login?next=", StringComparison.Ordinal)
        && Uri.UnescapeDataString(homeRedirect.Url["/login?next=".Length..]).Contains("/home", StringComparison.Ordinal),
        "home page should redirect signed-out guests to login while preserving the requested home route.");

    var authController = new AuthController(authService, identityClient, landing, chrome, google, accounts, identityLinks, emailLinks, loggerFactory.CreateLogger<AuthController>())
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };
    var loginResult = await authController.LoginPage("/home", CancellationToken.None);
    var loginModel = (loginResult as ViewResult)?.Model as AuthPageViewModel;
    Assert(loginModel is not null && loginModel.GoogleStartHref.Contains("/auth/google/start", StringComparison.Ordinal), "login page should render the Google-first auth shell.");
    Assert(string.Equals(loginModel!.NextPath, "/home", StringComparison.Ordinal), "login page should preserve the guest next path.");

    var signupResult = await authController.SignupPage("/home", CancellationToken.None);
    var signupModel = (signupResult as ViewResult)?.Model as AuthPageViewModel;
    Assert(signupModel is not null && signupModel.CreateAccount, "signup page should keep the reciprocal auth lane visible.");

    var emailStartMessage = await authController.StartEmail("runner@example.invalid", null, "/downloads", CancellationToken.None);
    var emailStartModel = (emailStartMessage as ViewResult)?.Model as AuthMessagePageViewModel;
    Assert(string.Equals(emailStartModel?.StateLabel, "Magic link sent", StringComparison.Ordinal), "email sign-in start should render the explicit magic-link-sent state.");
    Assert(emailStartModel?.Highlights?.Any(static item => item.Contains("Downloads", StringComparison.Ordinal)) == true, "email sign-in start should explain the post-verification return target.");

    var unavailableIdentityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(_ =>
        new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
        {
            Content = new StringContent("{\"detail\":\"identity-down-secret\"}", Encoding.UTF8, "application/json")
        })), configuration);
    var unavailableLandingController = new PublicLandingController(landing, releases, campaignOsProof, releaseSelection, actions, accounts, unavailableIdentityClient, identityLinks, experience, installLinking, campaignSpine, workspaceServerPlane, publicCreatorDiscovery, chrome, trustContent, privacyBoundaries, trustPulse, signedInTrustStatus, supportCases, supportPresentation, configuration, installBootstrapTickets, personalizedInstallScripts, releaseUploadTickets, windowsProofInstallers, publicWebHostEnvironment, loggerFactory.CreateLogger<PublicLandingController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    unavailableLandingController.ControllerContext.HttpContext.Request.Headers.Cookie = $"{HubBrowserAuthConstants.AccessTokenCookieName}=subject-token";
    var unavailableLandingView = await unavailableLandingController.LandingPage(CancellationToken.None) as ViewResult;
    var unavailableLandingModel = unavailableLandingView?.Model as LandingPageViewModel;
    Assert(unavailableLandingModel?.Chrome.Authenticated == true, "public landing chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableLandingModel!.Chrome.HeaderActions.Any(static action => string.Equals(action.Label, "Sign out", StringComparison.Ordinal)), "authenticated public landing chrome should keep the signed-in actions during identity outages.");
    Assert(unavailableLandingModel.SignedInStatus is null, "landing should suppress install-specific trust status when identity is temporarily unavailable.");
    var unavailableNowView = await unavailableLandingController.NowPage(CancellationToken.None) as ViewResult;
    var unavailableNowModel = unavailableNowView?.Model as NowPageViewModel;
    Assert(unavailableNowModel?.Chrome.Authenticated == true, "current-release chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableNowModel?.SignedInStatus is null, "current-release projection should suppress install-specific trust status when identity is temporarily unavailable.");
    Assert(unavailableNowModel?.TrustPulse is not null, "current-release should keep the public trust pulse even when identity lookups are temporarily unavailable.");
    Assert(unavailableNowModel!.TrustPulse!.Rows.Any(static row => string.Equals(row.Label, "Adoption health", StringComparison.Ordinal)), "current-release should keep adoption health visible even when signed-in install lookups are temporarily unavailable.");
    var unavailableDownloadsView = await unavailableLandingController.DownloadsPage(CancellationToken.None) as ViewResult;
    var unavailableDownloadsModel = unavailableDownloadsView?.Model as DownloadsPageViewModel;
    Assert(unavailableDownloadsModel?.Chrome.Authenticated == true, "downloads chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableDownloadsModel?.SignedInStatus is null, "downloads projection should suppress install-specific trust status when identity is temporarily unavailable.");
    Assert(unavailableDownloadsModel?.TrustPulse is not null, "downloads should keep the public trust pulse even when identity lookups are temporarily unavailable.");
    var unavailableHelpView = await unavailableLandingController.HelpPage(CancellationToken.None) as ViewResult;
    var unavailableHelpModel = unavailableHelpView?.Model as TrustPageViewModel;
    Assert(unavailableHelpModel?.Chrome.Authenticated == true, "help chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableHelpModel?.SignedInStatus is null, "help projection should suppress install-specific trust status when identity is temporarily unavailable.");
    Assert(unavailableHelpModel?.TrustPulse is not null, "help should keep the public trust pulse even when identity lookups are temporarily unavailable.");
    var unavailableFaqView = await unavailableLandingController.FaqPage(CancellationToken.None) as ViewResult;
    var unavailableFaqModel = unavailableFaqView?.Model as FaqPageViewModel;
    Assert(unavailableFaqModel?.Chrome.Authenticated == true, "faq chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableFaqModel?.SignedInStatus is null, "faq should suppress install-specific trust status when identity is temporarily unavailable.");
    Assert(unavailableFaqModel?.TrustPulse is not null, "faq should keep the public trust pulse even when identity lookups are temporarily unavailable.");
    var unavailablePrivacyView = await unavailableLandingController.PrivacyPage(CancellationToken.None) as ViewResult;
    var unavailablePrivacyModel = unavailablePrivacyView?.Model as TrustPageViewModel;
    Assert(unavailablePrivacyModel?.Chrome.Authenticated == true, "privacy chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailablePrivacyModel?.SignedInStatus is null, "privacy should suppress install-specific trust status when identity is temporarily unavailable.");
    Assert(unavailablePrivacyModel?.TrustPulse is not null, "privacy should keep the public trust pulse even when identity lookups are temporarily unavailable.");
    var unavailableTermsView = await unavailableLandingController.TermsPage(CancellationToken.None) as ViewResult;
    var unavailableTermsModel = unavailableTermsView?.Model as TrustPageViewModel;
    Assert(unavailableTermsModel?.Chrome.Authenticated == true, "terms chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableTermsModel?.SignedInStatus is null, "terms should suppress install-specific trust status when identity is temporarily unavailable.");
    Assert(unavailableTermsModel?.TrustPulse is not null, "terms should keep the public trust pulse even when identity lookups are temporarily unavailable.");
    var unavailableStatusView = await unavailableLandingController.StatusPage(CancellationToken.None) as ViewResult;
    var unavailableStatusModel = unavailableStatusView?.Model as StatusPageViewModel;
    Assert(unavailableStatusModel?.Chrome.Authenticated == true, "status chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableStatusModel?.SignedInStatus is null, "status should suppress install-specific trust status when identity is temporarily unavailable.");
    Assert(unavailableStatusModel?.TrustPulse is not null, "status should keep the public trust pulse even when identity lookups are temporarily unavailable.");
    var unavailableHomeResult = await unavailableLandingController.HomePage(null, CancellationToken.None);
    var unavailableHomeModel = (unavailableHomeResult as ViewResult)?.Model as AuthMessagePageViewModel;
    Assert(string.Equals(unavailableHomeModel?.Heading, "Home is unavailable right now", StringComparison.Ordinal), "home page should show an unavailable message when identity is down instead of redirecting to login.");

    var unavailableLeaderboardsController = new LeaderboardsController(leaderboards, accounts, unavailableIdentityClient, chrome, loggerFactory.CreateLogger<LeaderboardsController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    unavailableLeaderboardsController.ControllerContext.HttpContext.Request.Headers.Cookie = $"{HubBrowserAuthConstants.AccessTokenCookieName}=subject-token";
    var unavailableLeaderboardsView = await unavailableLeaderboardsController.LeaderboardsPage(CancellationToken.None) as ViewResult;
    var unavailableLeaderboardsModel = unavailableLeaderboardsView?.Model as LeaderboardsPageViewModel;
    Assert(unavailableLeaderboardsModel?.Chrome.Authenticated == true, "leaderboards chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");

    var unavailableAccountController = new AccountsController(accounts, unavailableIdentityClient, identityLinks, experience, installLinking, supportCases, supportPresentation, campaignSpine, workspaceServerPlane, creatorPublicationRegistry, chrome, google, releases, releaseSelection, privacyBoundaries, signedInTrustStatus, loggerFactory.CreateLogger<AccountsController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var unavailableAccountResult = await unavailableAccountController.AccountPage(section: null, caseId: null, CancellationToken.None);
    var unavailableAccountModel = (unavailableAccountResult as ViewResult)?.Model as AuthMessagePageViewModel;
    Assert(string.Equals(unavailableAccountModel?.Heading, "Account is unavailable right now", StringComparison.Ordinal), "account page should show an unavailable message when identity is down instead of redirecting to login.");

    var failingAuthService = new HubBrowserAuthService(new HttpClient(new StubHttpMessageHandler(_ =>
        new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
        {
            Content = new StringContent("{\"detail\":\"identity-mailer-secret\"}", Encoding.UTF8, "application/json")
        })), configuration);
    var failingEmailAuthController = new AuthController(failingAuthService, identityClient, landing, chrome, google, accounts, identityLinks, emailLinks, loggerFactory.CreateLogger<AuthController>())
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };
    var unavailableEmailStart = await failingEmailAuthController.StartEmail("runner@example.invalid", "Runner Demo", "/home", CancellationToken.None);
    var unavailableEmailStartModel = (unavailableEmailStart as ViewResult)?.Model as AuthMessagePageViewModel;
    Assert(string.Equals(unavailableEmailStartModel?.Heading, "Email sign-in is unavailable", StringComparison.Ordinal), "email sign-in start should render an unavailable message when identity mail transport is down.");
    Assert(!(unavailableEmailStartModel?.SupportLine?.Contains("identity-mailer-secret", StringComparison.OrdinalIgnoreCase) ?? false), "email sign-in start should not leak raw identity transport details.");

    var expiredAuthService = new HubBrowserAuthService(new HttpClient(new StubHttpMessageHandler(_ =>
        new HttpResponseMessage(HttpStatusCode.BadRequest)
        {
            Content = new StringContent("{\"detail\":\"Unknown or expired email entry ticket 'expired-ticket'.\"}", Encoding.UTF8, "application/json")
        })), configuration);
    var expiredEmailAuthController = new AuthController(expiredAuthService, identityClient, landing, chrome, google, accounts, identityLinks, emailLinks, loggerFactory.CreateLogger<AuthController>())
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };
    var expiredEmailResult = await expiredEmailAuthController.CompleteEmail("expired-ticket", "/downloads", CancellationToken.None);
    var expiredEmailModel = (expiredEmailResult as ViewResult)?.Model as AuthMessagePageViewModel;
    Assert(string.Equals(expiredEmailModel?.Heading, "Magic link expired", StringComparison.Ordinal), "expired email callback should render a stable expired-link state.");
    Assert(string.Equals(expiredEmailModel?.StateLabel, "Verification expired", StringComparison.Ordinal), "expired email callback should expose the verification-expired state label.");
    Assert(expiredEmailModel?.Highlights?.Any(static item => item.Contains("Downloads", StringComparison.Ordinal)) == true, "expired email callback should preserve the requested return target.");
    Assert(!(expiredEmailModel?.SupportLine?.Contains("expired-ticket", StringComparison.OrdinalIgnoreCase) ?? false), "expired email callback should not leak raw identity ticket details.");

    var googleFailureConfiguration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
            ["GOOGLE_OIDC_CLIENT_ID"] = "smoke-google-client",
            ["GOOGLE_OIDC_CLIENT_SECRET"] = "smoke-google-secret",
            ["GOOGLE_OIDC_REDIRECT_URI"] = "https://hub.example.test/auth/google/callback"
        })
        .Build();
    var failingGoogle = new HubGoogleAuthService(
        new HttpClient(new StubHttpMessageHandler(_ => new HttpResponseMessage(HttpStatusCode.InternalServerError)
        {
            Content = new StringContent("{\"error\":\"provider-secret-raw-detail\"}", Encoding.UTF8, "application/json")
        })),
        googleFailureConfiguration,
        authService,
        identityLinks,
        accounts,
        DataProtectionProvider.Create(Path.Combine(tempRoot, "google-failure")),
        loggerFactory.CreateLogger<HubGoogleAuthService>(),
        new SmokeWebHostEnvironment
        {
            EnvironmentName = "Development",
            ApplicationName = "RunServicesSmoke",
            ContentRootPath = tempRoot,
            WebRootPath = Path.Combine(tempRoot, "wwwroot")
        });
    var googleFailureContext = new DefaultHttpContext();
    googleFailureContext.Request.Scheme = "https";
    googleFailureContext.Request.Host = new HostString("hub.example.test");
    var googleChallenge = failingGoogle.CreateChallenge(googleFailureContext.Request, "/home");
    var googleState = Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(new Uri(googleChallenge.RedirectUrl).Query)["state"].ToString();
    googleFailureContext.Request.Headers.Cookie = $"{HubGoogleAuthConstants.StateCookieName}={googleChallenge.StateCookieValue}";
    googleFailureContext.Request.QueryString = new QueryString($"?state={Uri.EscapeDataString(googleState)}&code=smoke-auth-code");
    var failingGoogleAuthController = new AuthController(authService, identityClient, landing, chrome, failingGoogle, accounts, identityLinks, emailLinks, loggerFactory.CreateLogger<AuthController>())
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = googleFailureContext
        }
    };
    var unavailableGoogleResult = await failingGoogleAuthController.GoogleCallback(CancellationToken.None);
    var unavailableGoogleModel = (unavailableGoogleResult as ViewResult)?.Model as AuthMessagePageViewModel;
    Assert(string.Equals(unavailableGoogleModel?.Heading, "Google sign-in failed", StringComparison.Ordinal), "google callback should render a stable failure message when upstream token exchange fails.");
    Assert(!(unavailableGoogleModel?.SupportLine?.Contains("provider-secret-raw-detail", StringComparison.OrdinalIgnoreCase) ?? false), "google callback should not leak raw provider failure details.");
}

void VerifyRegistryWorkflow()
{
    var registry = new HubArtifactStore();
    var kinds = new[]
    {
        HubArtifactKind.RulePack,
        HubArtifactKind.RuleProfile,
        HubArtifactKind.BuildKit,
        HubArtifactKind.NpcVault,
        HubArtifactKind.RuntimeBundle
    };

    foreach (var kind in kinds)
    {
        var created = registry.UpsertArtifact(new HubArtifactCreateRequest(
            Name: $"{kind} Smoke Bundle",
            Kind: kind,
            Version: "1.0.0",
            RulesetId: "sr6",
            Visibility: ArtifactVisibilityModes.LocalOnly,
            TrustTier: ArtifactTrustTiers.LocalOnly,
            OwnerId: "hub.demo",
            PublisherId: null,
            Summary: "clean-room smoke artifact",
            Description: null,
            RuntimeFingerprint: kind == HubArtifactKind.RuntimeBundle ? "scene-ledger:v1" : null));

        var reviews = registry.AddReview(created.Id, new RegistryHubReviewRequest(
            ArtifactId: created.Id,
            Score: 8,
            Comment: "solid"));
        Assert(reviews.ReviewCount == 1 && reviews.AverageScore >= 8d, "review aggregates should update");

        var stateAfterDeprecation = registry.ChangeState(created.Id, new HubArtifactStateChangeRequest(
            RequestedBy: "publisher.demo",
            TargetState: HubArtifactState.Deprecated,
            SupersededByArtifactId: null,
            Reason: "scheduled replacement"));
        Assert(stateAfterDeprecation.State == HubArtifactState.Deprecated, "artifacts should support deprecate lifecycle state");

        var stateAfterSupersede = registry.ChangeState(created.Id, new HubArtifactStateChangeRequest(
            RequestedBy: "publisher.demo",
            TargetState: HubArtifactState.Superseded,
            SupersededByArtifactId: $"{created.Id}-v2",
            Reason: "replacement published"));
        Assert(stateAfterSupersede.State == HubArtifactState.Superseded, "artifacts should support supersede lifecycle state");
        Assert(stateAfterSupersede.SupersededByArtifactId == $"{created.Id}-v2", "superseded artifacts should expose replacement id");

        registry.RegisterInstall(created.Id, new RegistryHubInstallEvent(
            ArtifactId: created.Id,
            UserId: "runner.demo",
            InstalledAtUtc: DateTimeOffset.UtcNow,
            ActiveRuntimeRef: true));

        var deleteAttempt = registry.AttemptDelete(created.Id);
        Assert(deleteAttempt.Accepted is false, "hub artifacts should never hard-delete");

        var projection = registry.GetProjection(created.Id);
        Assert(projection is not null, "registry should expose stable artifact projections");
        Assert(projection!.State == HubArtifactState.Superseded.ToString(), "projection should reflect the lifecycle state");
        Assert(projection.SupersededByArtifactId == $"{created.Id}-v2", "projection should carry supersession metadata");
        Assert(projection.ImmutableRetentionRequired, "projection should expose retention invariants");

        var installProjection = registry.GetInstallProjection(created.Id);
        Assert(installProjection is not null, "registry should expose install projections");
        Assert(installProjection!.HasInstallReferences, "install projections should preserve install references");
        Assert(installProjection.HasRuntimeReferences, "install projections should preserve runtime references");
        Assert(!installProjection.AcceptingNewInstalls, "superseded artifacts should stop accepting new installs");
        Assert(installProjection.ImmutableRetentionRequired, "install projections should expose immutable retention invariants");
    }

    var issuedSession = registry.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
        SessionId: "session_registry",
        SceneId: "scene_issuance",
        Head: RuntimeBundleHeadKind.Session,
        SourceBundleVersion: "bundle-4-feedbeef",
        ProjectionFingerprint: "feedbeef00112233",
        ProjectionVersion: 4,
        Ready: true,
        OfflineCapable: true,
        CollaborationMode: "local-first",
        InvalidationSignals: new[] { "event-stream:session_registry:scene_issuance", "projection-version:4" },
        IncludedEventTypes: new[] { "objective.unresolved", "heat.alert" },
        SupportedExchangeFormats: new[] { "session-ledger.v1", "foundry-vtt.scene-ledger.v1" },
        RequestedBy: "ops.registry",
        OwnerId: "hub.registry",
        Summary: "Session issuance smoke"));
    Assert(issuedSession.CreatedNewArtifact, "runtime-bundle issuance should create an immutable artifact on first issue");

    var issuedOffline = registry.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
        SessionId: "session_registry",
        SceneId: "scene_issuance",
        Head: RuntimeBundleHeadKind.Offline,
        SourceBundleVersion: "bundle-4-feedbeef",
        ProjectionFingerprint: "feedbeef00112233",
        ProjectionVersion: 4,
        Ready: true,
        OfflineCapable: true,
        CollaborationMode: "local-first",
        InvalidationSignals: new[] { "event-stream:session_registry:scene_issuance", "projection-version:4" },
        IncludedEventTypes: new[] { "objective.unresolved", "heat.alert" },
        SupportedExchangeFormats: new[] { "session-ledger.v1", "offline-snapshot.v1" },
        RequestedBy: "ops.registry",
        OwnerId: "hub.registry",
        Summary: "Offline issuance smoke"));
    Assert(issuedOffline.Head.Head == RuntimeBundleHeadKind.Offline, "runtime-bundle issuance should support offline heads");

    var reissuedSession = registry.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
        SessionId: "session_registry",
        SceneId: "scene_issuance",
        Head: RuntimeBundleHeadKind.Session,
        SourceBundleVersion: "bundle-5-cafed00d",
        ProjectionFingerprint: "cafed00d44556677",
        ProjectionVersion: 5,
        Ready: true,
        OfflineCapable: true,
        CollaborationMode: "local-first",
        InvalidationSignals: new[] { "event-stream:session_registry:scene_issuance", "projection-version:5" },
        IncludedEventTypes: new[] { "objective.unresolved", "heat.alert", "relationship.shift" },
        SupportedExchangeFormats: new[] { "session-ledger.v1", "foundry-vtt.scene-ledger.v1" },
        RequestedBy: "ops.registry",
        OwnerId: "hub.registry",
        Summary: "Session issuance smoke v5"));
    Assert(reissuedSession.Projection.PreviousArtifactId == issuedSession.Artifact.Id, "runtime-bundle issuance should preserve prior artifact lineage");
    Assert(registry.GetArtifact(issuedSession.Artifact.Id)?.State == HubArtifactState.Superseded, "reissued runtime-bundle heads should supersede the previous artifact");

    var heads = registry.GetRuntimeBundleHeads("session_registry", "scene_issuance");
    Assert(heads.Heads.Count == 2, "runtime-bundle head listings should expose all issued heads for a family");
    Assert(heads.Heads.Any(head => head.Head == RuntimeBundleHeadKind.Session && head.CurrentArtifactId == reissuedSession.Artifact.Id), "head listings should surface the latest session head artifact");
    Assert(heads.Heads.Any(head => head.Head == RuntimeBundleHeadKind.Offline && head.CurrentArtifactId == issuedOffline.Artifact.Id), "head listings should preserve the offline head artifact");
}

void VerifyRegistryControllerHardening()
{
    var registry = new HubArtifactStore();
    var workflow = new PublicationWorkflowService(registry);
    var controller = new HubRegistryController(registry, new StubReleaseChannelManifestStore(), workflow)
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };

    var create = controller.CreateArtifact(new HubArtifactCreateRequest(
        Name: "Runtime Bundle Projection",
        Kind: HubArtifactKind.RuntimeBundle,
        Version: "2.0.0",
        RulesetId: "sr6",
        Visibility: ArtifactVisibilityModes.LocalOnly,
        TrustTier: ArtifactTrustTiers.LocalOnly,
        OwnerId: "hub.controller",
        PublisherId: null,
        Summary: "projection endpoint smoke",
        Description: null,
        RuntimeFingerprint: "scene-ledger:v2"));
    var createdResult = create.Result as CreatedAtActionResult;
    Assert(createdResult is not null, "registry create should return CreatedAtActionResult");
    var created = createdResult!.Value as HubArtifactMetadata;
    Assert(created is not null, "registry create should return metadata");

    var search = controller.SearchArtifacts(query: "Projection", kind: "RuntimeBundle", state: "Active", page: 1, pageSize: 10);
    var searchResult = search.Result as OkObjectResult;
    var searchPayload = searchResult?.Value as RegistrySearchResponse;
    Assert(searchPayload?.Items.Count == 1, "registry search should support kind/state filtered projections");
    Assert(searchPayload?.Items[0].ImmutableRetentionRequired == true, "registry search items should advertise immutable retention");
    Assert(searchPayload?.Items[0].Visibility == ArtifactVisibilityModes.LocalOnly, "registry search should surface artifact visibility");
    Assert(searchPayload?.Items[0].TrustTier == ArtifactTrustTiers.LocalOnly, "registry search should surface artifact trust tier");
    Assert(searchPayload?.Items[0].ShelfAudience == "owner-only", "local-only artifacts should project owner-only shelf posture");
    Assert(searchPayload?.Items[0].ShelfSummary?.Contains("owner-controlled", StringComparison.OrdinalIgnoreCase) == true, "registry search should explain owner-only shelf posture");
    Assert(searchPayload?.Items[0].ShelfOwnershipSummary?.Contains("originating account or install", StringComparison.OrdinalIgnoreCase) == true, "registry search should explain owner-only ownership posture");

    var creatorShelfCreate = controller.CreateArtifact(new HubArtifactCreateRequest(
        Name: "Creator Shelf Projection",
        Kind: HubArtifactKind.BuildIdea,
        Version: "2.0.1",
        RulesetId: "sr6",
        Visibility: ArtifactVisibilityModes.Shared,
        TrustTier: ArtifactTrustTiers.Curated,
        OwnerId: "hub.controller",
        PublisherId: "pub.creator-shelf",
        Summary: "creator shelf smoke",
        Description: null,
        RuntimeFingerprint: "creator-shelf:v1"));
    var creatorShelfCreated = (creatorShelfCreate.Result as CreatedAtActionResult)?.Value as HubArtifactMetadata;
    Assert(creatorShelfCreated is not null, "registry create should return a creator-shelf artifact");
    var campaignShelfCreate = controller.CreateArtifact(new HubArtifactCreateRequest(
        Name: "Campaign Shelf Projection",
        Kind: HubArtifactKind.BuildKit,
        Version: "2.0.1",
        RulesetId: "sr6",
        Visibility: ArtifactVisibilityModes.CampaignShared,
        TrustTier: ArtifactTrustTiers.Curated,
        OwnerId: "hub.controller",
        PublisherId: null,
        Summary: "campaign shelf smoke",
        Description: null,
        RuntimeFingerprint: "campaign-shelf:v1"));
    var campaignShelfCreated = (campaignShelfCreate.Result as CreatedAtActionResult)?.Value as HubArtifactMetadata;
    Assert(campaignShelfCreated is not null, "registry create should return a campaign-shelf artifact");
    var personalShelfCreate = controller.CreateArtifact(new HubArtifactCreateRequest(
        Name: "Personal Shelf Projection",
        Kind: HubArtifactKind.RuleProfile,
        Version: "2.0.1",
        RulesetId: "sr6",
        Visibility: ArtifactVisibilityModes.Shared,
        TrustTier: ArtifactTrustTiers.Curated,
        OwnerId: "hub.controller",
        PublisherId: null,
        Summary: "personal shelf smoke",
        Description: null,
        RuntimeFingerprint: "personal-shelf:v1"));
    var personalShelfCreated = (personalShelfCreate.Result as CreatedAtActionResult)?.Value as HubArtifactMetadata;
    Assert(personalShelfCreated is not null, "registry create should return a personal-shelf artifact");

    var creatorShelfSearch = controller.SearchArtifacts(query: "Shelf Projection", kind: null, state: null, page: 1, pageSize: 10, shelfAudience: "creator").Result as OkObjectResult;
    var creatorShelfPayload = creatorShelfSearch?.Value as RegistrySearchResponse;
    Assert(creatorShelfPayload?.Items.Count == 1 && creatorShelfPayload.Items[0].ShelfAudience == "creator" && creatorShelfPayload.Items[0].Id == creatorShelfCreated!.Id, "registry search should support creator shelf filtering on downstream hosted callers");

    var campaignShelfSearch = controller.SearchArtifacts(query: "Shelf Projection", kind: null, state: null, page: 1, pageSize: 10, shelfAudience: "campaign").Result as OkObjectResult;
    var campaignShelfPayload = campaignShelfSearch?.Value as RegistrySearchResponse;
    Assert(campaignShelfPayload?.Items.Count == 1 && campaignShelfPayload.Items[0].ShelfAudience == "campaign" && campaignShelfPayload.Items[0].Id == campaignShelfCreated!.Id, "registry search should support campaign shelf filtering on downstream hosted callers");

    var personalShelfSearch = controller.SearchArtifacts(query: "Shelf Projection", kind: null, state: null, page: 1, pageSize: 10, shelfAudience: "personal").Result as OkObjectResult;
    var personalShelfPayload = personalShelfSearch?.Value as RegistrySearchResponse;
    Assert(personalShelfPayload?.Items.Count == 1 && personalShelfPayload.Items[0].ShelfAudience == "personal" && personalShelfPayload.Items[0].Id == personalShelfCreated!.Id, "registry search should support personal shelf filtering on downstream hosted callers");

    var preview = controller.GetPreview(created!.Id).Result as OkObjectResult;
    var previewPayload = preview?.Value as RegistryPreviewResponse;
    Assert(previewPayload?.ShelfAudience == "owner-only", "registry preview should project owner-only shelf posture");
    Assert(previewPayload?.ShelfSummary?.Contains("owner-controlled", StringComparison.OrdinalIgnoreCase) == true, "registry preview should explain owner-only shelf posture");
    Assert(previewPayload?.ShelfOwnershipSummary?.Contains("originating account or install", StringComparison.OrdinalIgnoreCase) == true, "registry preview should explain owner-only ownership posture");

    var submitted = workflow.Submit(new PublicationSubmissionRequest(
        ArtifactId: created.Id,
        ArtifactKind: created.Kind.ToString(),
        Title: created.Name,
        SubmittedBy: "controller.publisher",
        Notes: "controller hardening publication"));
    var approved = workflow.Review(
        submitted.PublicationId,
        new PublicationReviewRequest("controller.reviewer", Approved: true, Notes: "approved"),
        submitted.ConcurrencyToken).Publication;
    Assert(approved is not null, "registry controller hardening should be able to approve a publication against the created artifact");
    var published = workflow.Publish(
        approved!.PublicationId,
        new PublicationPublishRequest("controller.publisher", "publish controller artifact"),
        approved.ConcurrencyToken).Publication;
    Assert(published is not null, "registry controller hardening should be able to publish the created artifact");
    var deprecated = workflow.Moderate(
        published!.PublicationId,
        new PublicationModerationRequest("controller.moderator", "deprecate", Reason: "controller replacement path"),
        published.ConcurrencyToken).Publication;
    Assert(deprecated is not null, "registry controller hardening should be able to deprecate the published artifact");

    var publishedSearch = controller.SearchArtifacts(query: "Projection", kind: "RuntimeBundle", state: "Active", page: 1, pageSize: 10).Result as OkObjectResult;
    var publishedSearchPayload = publishedSearch?.Value as RegistrySearchResponse;
    Assert(publishedSearchPayload?.Items[0].LatestPublicationState == PublicationState.Deprecated.ToString(), "registry search should surface the latest publication state");
    Assert(publishedSearchPayload?.Items[0].PublicationTrustBand == "replacement-advised", "registry search should surface the latest publication trust band");
    Assert(!string.IsNullOrWhiteSpace(publishedSearchPayload?.Items[0].PublicationTrustSummary), "registry search should surface the latest publication trust summary");
    Assert(!string.IsNullOrWhiteSpace(publishedSearchPayload?.Items[0].PublicationDiscoverySummary), "registry search should surface the latest publication discovery summary");
    Assert(!string.IsNullOrWhiteSpace(publishedSearchPayload?.Items[0].PublicationLineageSummary), "registry search should surface the latest publication lineage summary");
    Assert(publishedSearchPayload?.Items[0].PublicationDiscoverable == false, "registry search should surface the latest publication discoverability posture");
    Assert(publishedSearchPayload?.Items[0].PublicationNextSafeActionSummary?.Contains("replacement artifact", StringComparison.OrdinalIgnoreCase) == true, "registry search should surface the latest publication next-safe action");

    var publishedPreview = controller.GetPreview(created.Id).Result as OkObjectResult;
    var publishedPreviewPayload = publishedPreview?.Value as RegistryPreviewResponse;
    Assert(publishedPreviewPayload?.LatestPublicationState == PublicationState.Deprecated.ToString(), "registry preview should surface the latest publication state");
    Assert(publishedPreviewPayload?.PublicationTrustBand == "replacement-advised", "registry preview should surface the latest publication trust band");
    Assert(!string.IsNullOrWhiteSpace(publishedPreviewPayload?.PublicationTrustSummary), "registry preview should surface the latest publication trust summary");
    Assert(!string.IsNullOrWhiteSpace(publishedPreviewPayload?.PublicationDiscoverySummary), "registry preview should surface the latest publication discovery summary");
    Assert(!string.IsNullOrWhiteSpace(publishedPreviewPayload?.PublicationLineageSummary), "registry preview should surface the latest publication lineage summary");
    Assert(publishedPreviewPayload?.PublicationDiscoverable == false, "registry preview should surface the latest publication discoverability posture");
    Assert(publishedPreviewPayload?.PublicationNextSafeActionSummary?.Contains("replacement artifact", StringComparison.OrdinalIgnoreCase) == true, "registry preview should surface the latest publication next-safe action");

    controller.RegisterInstall(created!.Id, new RegistryHubInstallEvent(
        ArtifactId: created.Id,
        UserId: "runner.controller",
        InstalledAtUtc: DateTimeOffset.UtcNow,
        ActiveRuntimeRef: true));
    controller.ChangeState(created.Id, new HubArtifactStateChangeRequest(
        RequestedBy: "publisher.controller",
        TargetState: HubArtifactState.Superseded,
        SupersededByArtifactId: $"{created.Id}-replacement",
        Reason: "replacement bundle"));

    var projection = controller.GetProjection(created.Id).Result as OkObjectResult;
    var projectionPayload = projection?.Value as RegistryProjectionResponse;
    Assert(projectionPayload?.SupersededByArtifactId == $"{created.Id}-replacement", "projection endpoint should expose supersession metadata");
    Assert(projectionPayload?.RuntimeFingerprint == "scene-ledger:v2", "projection endpoint should preserve runtime fingerprint");
    Assert(projectionPayload?.Visibility == ArtifactVisibilityModes.LocalOnly, "projection endpoint should surface artifact visibility");
    Assert(projectionPayload?.TrustTier == ArtifactTrustTiers.LocalOnly, "projection endpoint should surface artifact trust tier");
    Assert(projectionPayload?.ShelfAudience == "retained-history", "superseded local-only artifacts should project retained-history shelf posture");
    Assert(projectionPayload?.LatestPublicationState == PublicationState.Deprecated.ToString(), "projection endpoint should surface the latest publication state");
    Assert(projectionPayload?.PublicationTrustBand == "replacement-advised", "projection endpoint should surface the latest publication trust band");
    Assert(!string.IsNullOrWhiteSpace(projectionPayload?.PublicationTrustSummary), "projection endpoint should surface the latest publication trust summary");
    Assert(!string.IsNullOrWhiteSpace(projectionPayload?.PublicationDiscoverySummary), "projection endpoint should surface the latest publication discovery summary");
    Assert(!string.IsNullOrWhiteSpace(projectionPayload?.PublicationLineageSummary), "projection endpoint should surface the latest publication lineage summary");
    Assert(projectionPayload?.PublicationDiscoverable == false, "projection endpoint should surface the latest publication discoverability posture");
    Assert(projectionPayload?.PublicationNextSafeActionSummary?.Contains("replacement artifact", StringComparison.OrdinalIgnoreCase) == true, "projection endpoint should surface the latest publication next-safe action");

    var installProjection = controller.GetInstallProjection(created.Id).Result as OkObjectResult;
    var installProjectionPayload = installProjection?.Value as HubArtifactInstallProjection;
    Assert(installProjectionPayload?.HasInstallReferences == true, "install projection endpoint should preserve install references");
    Assert(installProjectionPayload?.HasRuntimeReferences == true, "install projection endpoint should preserve runtime references");
    Assert(installProjectionPayload?.AcceptingNewInstalls == false, "install projection endpoint should stop new installs after supersession");

    var issued = controller.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
        SessionId: "session_controller",
        SceneId: "scene_controller",
        Head: RuntimeBundleHeadKind.Mobile,
        SourceBundleVersion: "bundle-7-1234abcd",
        ProjectionFingerprint: "1234abcd0000ffff",
        ProjectionVersion: 7,
        Ready: true,
        OfflineCapable: true,
        CollaborationMode: "local-first",
        InvalidationSignals: new[] { "event-stream:session_controller:scene_controller", "projection-version:7" },
        IncludedEventTypes: new[] { "objective.unresolved" },
        SupportedExchangeFormats: new[] { "session-ledger.v1", "mobile-bootstrap.v1" },
        RequestedBy: "ops.controller",
        OwnerId: "hub.controller",
        Summary: "Controller issuance smoke"));
    var issuedResult = issued.Result as CreatedAtActionResult;
    var issuedPayload = issuedResult?.Value as RuntimeBundleIssueResponse;
    Assert(issuedPayload?.Artifact.Kind == HubArtifactKind.RuntimeBundle, "runtime-bundle controller issue should create a runtime-bundle artifact");
    Assert(issuedPayload?.Head.Head == RuntimeBundleHeadKind.Mobile, "runtime-bundle controller issue should preserve the selected head");

    var runtimeProjection = controller.GetRuntimeBundleArtifact(issuedPayload!.Artifact.Id).Result as OkObjectResult;
    var runtimeProjectionPayload = runtimeProjection?.Value as RuntimeBundleArtifactProjection;
    Assert(runtimeProjectionPayload?.ProjectionFingerprint == "1234abcd0000ffff", "runtime-bundle projection endpoint should preserve the session projection fingerprint");

    var headProjection = controller.GetRuntimeBundleHead("session_controller", "scene_controller", RuntimeBundleHeadKind.Mobile).Result as OkObjectResult;
    var headProjectionPayload = headProjection?.Value as RuntimeBundleHeadProjection;
    Assert(headProjectionPayload?.CurrentArtifactId == issuedPayload.Artifact.Id, "runtime-bundle head endpoint should resolve the active head pointer");

    var headList = controller.GetRuntimeBundleHeads("session_controller", "scene_controller").Result as OkObjectResult;
    var headListPayload = headList?.Value as RuntimeBundleHeadListResponse;
    Assert(headListPayload?.Heads.Count == 1, "runtime-bundle head list endpoint should enumerate issued heads");

    var badStateSearch = controller.SearchArtifacts(query: null, kind: null, state: "UnknownState", page: 1, pageSize: 10);
    var badStateResult = badStateSearch.Result as BadRequestObjectResult;
    Assert(badStateResult is not null, "invalid registry state filters should fail fast");
    var badShelfAudienceSearch = controller.SearchArtifacts(query: null, kind: null, state: null, page: 1, pageSize: 10, shelfAudience: "shadow");
    var badShelfAudienceResult = badShelfAudienceSearch.Result as BadRequestObjectResult;
    Assert(badShelfAudienceResult is not null, "invalid registry shelf-audience filters should fail fast");
}

async Task VerifyAiGatewayWorkflowAsync()
{
    var configuration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["AiGateway:Providers:AiMagicx:Enabled"] = "true",
            ["AiGateway:Providers:OneMinAi:Enabled"] = "true",
            ["AiGateway:Providers:ChatPlayground:Enabled"] = "false",
            ["AiGateway:MonthlyAllowance"] = "240",
            ["AiGateway:BurstAllowancePerMinute"] = "40"
        })
        .Build();
    var router = new ProviderRouter(configuration);
    var prompts = new PromptRegistry();
    var budget = new AiBudgetService(configuration);
    var gateway = new AiGatewayService(
        router,
        new IProviderAdapter[]
        {
            new MockProviderAdapter(AiProvider.AiMagicx, enabled: true, primaryForStructuredOutput: true),
            new MockProviderAdapter(AiProvider.OneMinAi, enabled: true, primaryForStructuredOutput: true)
        },
        budget,
        prompts);
    var evaluations = new EvaluationStore(prompts, router);

    var render = prompts.Render(new PromptRenderRequest(
        TemplateName: "coach.system",
        Inputs: "{\"query\":\"best ingress\",\"packProfileIds\":\"pack_redmond\",\"retrievalScope\":\"legwork\",\"evidence\":\"camera feed\"}",
        Version: "1.1.0",
        GroundingContext: new PromptGroundingContext(
            RuntimeFingerprint: "runtime:scene_01",
            PackProfileIds: new[] { "pack_redmond" },
            EvidencePointers: new[] { "camera feed" },
            RetrievalScope: "legwork",
            SceneId: "scene_01"),
        EvaluationLabel: "smoke"));
    Assert(render.Lineage.TemplateVersion == "1.1.0", "prompt registry should resolve the requested template version");
    Assert(render.Lineage.DraftOnly, "grounded feature prompts should remain draft-first");
    Assert(render.Lineage.Grounding == PromptGroundingKind.RuntimeFacts, "coach prompt should advertise runtime grounding");
    Assert(render.UnresolvedPlaceholders.Count == 0, "render should satisfy all required placeholders for grounded prompts");

    var invocation = await gateway.ExecuteRouteAsync(new ProviderRouteRequest(
        Purpose: "coach.answer",
        Prompt: render.RenderedText,
        StructuredOutput: true,
        MaxTokens: 1200,
        SessionId: "session_ai",
        PromptLineage: render.Lineage), CancellationToken.None);
    Assert(invocation.Success, "gateway should execute routed grounded prompts");
    Assert(invocation.Prompt?.Lineage.PromptHash == render.Lineage.PromptHash, "gateway invocations should preserve prompt lineage");
    Assert(invocation.Decision.SelectedModel == "gpt-5.4", "complex grounded prompts should route to the complex model tier");

    var evaluation = evaluations.Add(new EvaluationRequest(
        RequestId: "eval_feedback_01",
        Provider: "AiMagicx",
        Prompt: render.RenderedText,
        Response: invocation.Output ?? string.Empty,
        Rating: 5,
        Notes: "grounded and traceable",
        PromptLineage: render.Lineage,
        EvaluationSuiteId: "suite_smoke"));
    Assert(evaluation.Accepted, "human evaluation feedback should accept valid ratings");
    Assert(evaluation.Flags.Contains("draft_first_prompt"), "feedback records should preserve draft-first traceability");

    var run = evaluations.Run(new PromptEvaluationRunRequest(
        SuiteId: "suite_smoke",
        TemplateName: "coach.system",
        Version: "1.1.0",
        Cases: new[]
        {
            new PromptEvaluationCase(
                CaseId: "coach_case_01",
                Label: "grounded coach baseline",
                TemplateName: "coach.system",
                Inputs: "{\"query\":\"best ingress\",\"packProfileIds\":\"pack_redmond\",\"retrievalScope\":\"legwork\",\"evidence\":\"camera feed\"}",
                ExpectedSignals: "runtime:scene_01, camera feed, best ingress",
                Version: "1.1.0",
                GroundingContext: new PromptGroundingContext(
                    RuntimeFingerprint: "runtime:scene_01",
                    PackProfileIds: new[] { "pack_redmond" },
                    EvidencePointers: new[] { "camera feed" },
                    RetrievalScope: "legwork",
                    SceneId: "scene_01"))
        }));
    Assert(run.Passed, "prompt-lab runs should pass when all expected grounded signals are present");
    Assert(run.PassedCases == 1 && run.TotalCases == 1, "evaluation runs should report pass/fail counts");
    Assert(evaluations.TryGetRun(run.RunId)?.SuiteId == "suite_smoke", "evaluation runs should be queryable after execution");

    var budgetRejected = await gateway.ExecuteRouteAsync(new ProviderRouteRequest(
        Purpose: "coach.answer.budget-limit",
        Prompt: render.RenderedText,
        StructuredOutput: false,
        MaxTokens: 300000,
        SessionId: "session_ai",
        PromptLineage: render.Lineage), CancellationToken.None);
    Assert(!budgetRejected.Success, "gateway should block routes that exceed budget allowances");

    var status = await gateway.GetStatusAsync();
    Assert(status.SelectionVisibility.TotalRoutes >= 2, "gateway status should include route selection totals");
    Assert(status.SelectionVisibility.Providers.Any(entry => entry.Provider == AiProvider.AiMagicx && entry.SuccessfulSelections >= 1), "gateway status should include successful provider selections");
    Assert(status.SelectionVisibility.Providers.Any(entry => entry.Provider == AiProvider.AiMagicx && entry.BudgetRejectedSelections >= 1), "gateway status should include budget-rejected selections");
    Assert(status.SelectionVisibility.RecentAudits.Count >= 2, "gateway status should include recent route audit entries");
    Assert(status.SelectionVisibility.RecentAudits.Any(entry => !entry.BudgetAllowed && string.Equals(entry.Purpose, "coach.answer.budget-limit", StringComparison.Ordinal)), "gateway audits should include rejected budget routes");
}

async Task VerifyGovernedSkillRuntimeWorkflowAsync()
{
    var configuration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["AiGateway:Providers:AiMagicx:Enabled"] = "true",
            ["AiGateway:MonthlyAllowance"] = "240",
            ["AiGateway:BurstAllowancePerMinute"] = "40"
        })
        .Build();
    var gateway = new AiGatewayService(
        new ProviderRouter(configuration),
        new IProviderAdapter[]
        {
            new MockProviderAdapter(AiProvider.AiMagicx, enabled: true, primaryForStructuredOutput: true)
        },
        new AiBudgetService(configuration),
        new PromptRegistry());
    var ledger = new SessionLedgerService();
    await ledger.MergeEventsAsync(new[]
    {
        new SessionEventEnvelope("session_skill_smoke", "scene_skill_smoke", "objective.unresolved", "need exit route", DateTimeOffset.UtcNow, "evt_skill_1", "scene_skill_smoke:r1", "evt_skill_1")
    });
    var lore = new LoreService();
    var runtime = new GovernedSkillRuntimeService(
        gateway,
        new ISkillToolAdapter[]
        {
            new SessionProjectionSkillToolAdapter(ledger),
            new LoreSearchSkillToolAdapter(lore)
        });

    var blocked = await runtime.ExecuteAsync(
        new GovernedSkillExecutionRequest(
            SkillId: "skill.canonize.memory",
            SessionId: "session_skill_smoke",
            Purpose: "canon.mutation",
            Prompt: "Write canon state.",
            ApprovalClass: SkillApprovalClass.CanonMutation,
            RequestedBy: "gm.skill"),
        CancellationToken.None);
    Assert(blocked.GovernanceOutcome == "approval-required", "canon-mutation skills should require explicit approval");
    Assert(!blocked.GatewayInvoked, "blocked governed skills should not invoke the gateway");

    var executed = await runtime.ExecuteAsync(
        new GovernedSkillExecutionRequest(
            SkillId: "skill.scene.brief",
            SessionId: "session_skill_smoke",
            Purpose: "coach.answer",
            Prompt: "Summarize scene risk using tool outputs.",
            ApprovalClass: SkillApprovalClass.Operational,
            RequestedBy: "gm.skill",
            ApprovalState: "approved",
            ToolCalls: new[]
            {
                new GovernedSkillToolCall("session.projection", "{\"sessionId\":\"session_skill_smoke\",\"sceneId\":\"scene_skill_smoke\"}"),
                new GovernedSkillToolCall("lore.search", "{\"query\":\"redmond\",\"scope\":\"district\",\"limit\":2}")
            }),
        CancellationToken.None);
    Assert(executed.GovernanceOutcome == "executed", "approved governed skills should execute through the gateway");
    Assert(executed.GatewayInvoked, "approved governed skills should invoke the AI gateway");
    Assert(executed.ToolResults.Count == 2, "governed skill runtime should execute configured tool adapters");
    Assert(executed.ToolResults.All(item => item.Executed), "registered skill tool adapters should execute successfully");
    Assert(executed.GovernanceFlags.Contains("gateway-governed"), "governed skill runtime should annotate gateway governance");
}

async Task VerifyGmOpsBoardWorkflowAsync()
{
    var ledger = new SessionLedgerService();
    await ledger.MergeEventsAsync(
    [
        new SessionEventEnvelope(
            SessionId: "session_ops_smoke",
            SceneId: "scene_smoke",
            EventType: "objective.unresolved",
            Payload: "Open question: who burned the safehouse?",
            AtUtc: DateTimeOffset.UtcNow.AddMinutes(-6),
            EventId: "evt_ops_smoke_01",
            SceneRevision: "scene_smoke:r2",
            IdempotencyKey: "objective:smoke"),
        new SessionEventEnvelope(
            SessionId: "session_ops_smoke",
            SceneId: "scene_smoke",
            EventType: "heat.alert",
            Payload: "Lone Star scanners are triangulating comms traffic",
            AtUtc: DateTimeOffset.UtcNow.AddMinutes(-3),
            EventId: "evt_ops_smoke_02",
            SceneRevision: "scene_smoke:r2",
            IdempotencyKey: "heat:smoke")
    ]);

    var outbox = new DeliveryOutboxService();
    var service = new GmOpsBoardService(ledger, outbox);
    var controller = new GmOpsBoardController(service)
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };

    var checklistCreate = controller.CreatePrepAsset(new GmPrepAssetCreateRequest(
        CampaignId: "campaign_smoke",
        SessionId: "session_ops_smoke",
        SceneId: "scene_smoke",
        Title: "Smoke checklist",
        Kind: GmPrepAssetKind.Checklist,
        Audience: GmPrepAssetAudience.GameMaster,
        Summary: "Keep the team moving",
        Body: "Prep checklist body",
        Tags: ["ops", "prep"],
        ChecklistItems:
        [
            new GmPrepChecklistItem("smoke-1", "Kill the exterior cameras"),
            new GmPrepChecklistItem("smoke-2", "Confirm escape vehicle", true)
        ],
        SourceEventIds: ["evt_ops_smoke_01"],
        CreatedBy: "gm.smoke",
        RuntimeFingerprint: "ops-smoke"));
    var checklistCreated = (checklistCreate.Result as CreatedAtActionResult)?.Value as GmPrepAssetRecord;
    Assert(checklistCreated is not null, "ops-board create should return a prep-asset record");

    var revealCreate = controller.CreatePrepAsset(new GmPrepAssetCreateRequest(
        CampaignId: "campaign_smoke",
        SessionId: "session_ops_smoke",
        SceneId: "scene_smoke",
        Title: "Smoke reveal",
        Kind: GmPrepAssetKind.PlayerScreen,
        Audience: GmPrepAssetAudience.Players,
        Summary: "Blue patrol lights cut across the rain.",
        Body: "Player-safe reveal body",
        Tags: ["reveal", "players"],
        SourceEventIds: ["evt_ops_smoke_02"],
        CreatedBy: "gm.smoke",
        RuntimeFingerprint: "ops-smoke"));
    var revealCreated = (revealCreate.Result as CreatedAtActionResult)?.Value as GmPrepAssetRecord;
    Assert(revealCreated is not null, "ops-board should create player reveal assets");
    var reusableNoteCreate = controller.CreatePrepAsset(new GmPrepAssetCreateRequest(
        CampaignId: "campaign_smoke",
        SessionId: null,
        SceneId: null,
        Title: "Reusable threat ladder",
        Kind: GmPrepAssetKind.Note,
        Audience: GmPrepAssetAudience.GameMaster,
        Summary: "Campaign-level reusable prep",
        Body: "Escalate to response teams if the smoke route collapses.",
        Tags: ["library", "reusable"],
        SourceEventIds: Array.Empty<string>(),
        CreatedBy: "gm.smoke",
        RuntimeFingerprint: "ops-fingerprint"));
    var reusableNote = (reusableNoteCreate.Result as CreatedAtActionResult)?.Value as GmPrepAssetRecord;
    Assert(reusableNote is not null, "ops-board should create reusable campaign prep assets");
    var governedPacketCreate = controller.CreatePrepAssetFromProject(new GmPrepAssetCatalogImportRequest(
        CampaignId: "campaign_smoke",
        SessionId: "session_ops_smoke",
        SceneId: "scene_smoke",
        Project: new HubProjectDetailProjection(
            Summary: new HubCatalogItem(
                ItemId: "renraku-checkpoint",
                Kind: HubCatalogItemKinds.EncounterPack,
                Title: "Renraku checkpoint",
                Description: "Checkpoint packet with scanner pressure and red samurai presence.",
                RulesetId: "sr5",
                Visibility: "public",
                TrustTier: "verified",
                LinkTarget: "/hub/encounters/renraku-checkpoint",
                Version: "1.0.0"),
            OwnerId: "hub:default",
            CatalogKind: "npc-vault",
            PublicationStatus: "published",
            ReviewState: "approved",
            RuntimeFingerprint: "npcvault:renraku-checkpoint:v1",
            OwnerReview: null,
            AggregateReview: null,
            Facts:
            [
                new HubProjectDetailFact("threat", "Threat", "High"),
                new HubProjectDetailFact("scene", "Scene posture", "Checkpoint 12 lockdown with scanner coverage")
            ],
            Dependencies:
            [
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "red-samurai", "1.0.0", "lead"),
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "renraku-spider", "1.0.0", "matrix-support")
            ],
            Actions:
            [
                new HubProjectAction("clone-encounter-pack", "Clone to Library", HubProjectActionKinds.CloneToLibrary),
                new HubProjectAction("open-encounter-pack", "Open Registry Entry", HubProjectActionKinds.OpenRegistry)
            ]),
        AdditionalTags: ["opposition", "packet"],
        CreatedBy: "gm.smoke",
        RuntimeFingerprint: "ops-smoke")).Result as CreatedAtActionResult;
    var governedPacket = NotNull(governedPacketCreate?.Value as GmPrepAssetRecord, "ops-board should bind governed encounter packets into campaign prep assets");
    var governedPacketReference = NotNull(governedPacket.GovernedProject, "governed prep bindings should carry structured governed-project provenance");
    Assert(governedPacketReference.ProjectId == "renraku-checkpoint", "governed prep bindings should preserve the source project id");
    Assert(governedPacket.Tags.Contains(HubCatalogItemKinds.EncounterPack, StringComparer.OrdinalIgnoreCase), "governed prep bindings should keep the source packet kind as a tag");
    Assert(governedPacket.Body.Contains("red-samurai", StringComparison.OrdinalIgnoreCase), "governed prep bindings should preserve dependency truth from the imported encounter packet");
    var governedNpcPackCreate = controller.CreatePrepAssetFromProject(new GmPrepAssetCatalogImportRequest(
        CampaignId: "campaign_smoke",
        SessionId: "session_ops_smoke",
        SceneId: "scene_smoke",
        Project: new HubProjectDetailProjection(
            Summary: new HubCatalogItem(
                ItemId: "renraku-security",
                Kind: HubCatalogItemKinds.NpcPack,
                Title: "Renraku security roster",
                Description: "Curated security roster with red samurai pressure and matrix support.",
                RulesetId: "sr5",
                Visibility: "public",
                TrustTier: "verified",
                LinkTarget: "/hub/npc-packs/renraku-security",
                Version: "1.0.0"),
            OwnerId: "hub:default",
            CatalogKind: "npc-vault",
            PublicationStatus: "published",
            ReviewState: "approved",
            RuntimeFingerprint: "npcvault:renraku-security:v1",
            OwnerReview: null,
            AggregateReview: null,
            Facts:
            [
                new HubProjectDetailFact("threat", "Threat", "High"),
                new HubProjectDetailFact("roster", "Roster posture", "Checkpoint-ready security team with matrix support")
            ],
            Dependencies:
            [
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "red-samurai", "1.0.0"),
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "renraku-spider", "1.0.0")
            ],
            Actions:
            [
                new HubProjectAction("clone-npc-pack", "Clone to Library", HubProjectActionKinds.CloneToLibrary),
                new HubProjectAction("open-npc-pack", "Open Registry Entry", HubProjectActionKinds.OpenRegistry)
            ]),
        AdditionalTags: ["opposition", "roster"],
        CreatedBy: "gm.smoke",
        RuntimeFingerprint: "ops-smoke")).Result as CreatedAtActionResult;
    var governedNpcPack = NotNull(governedNpcPackCreate?.Value as GmPrepAssetRecord, "ops-board should bind governed NPC packs into campaign prep assets");
    var governedNpcPackReference = NotNull(governedNpcPack.GovernedProject, "governed NPC pack bindings should carry structured governed-project provenance");
    Assert(governedNpcPackReference.ProjectId == "renraku-security", "governed NPC pack bindings should preserve the source project id");
    Assert(governedNpcPack.Tags.Contains(HubCatalogItemKinds.NpcPack, StringComparer.OrdinalIgnoreCase), "governed NPC pack bindings should keep the source packet kind as a tag");
    Assert(governedNpcPack.Body.Contains("renraku-spider", StringComparison.OrdinalIgnoreCase), "governed NPC pack bindings should preserve dependency truth from the imported NPC pack");

    var projection = controller.GetProjection("session_ops_smoke", "scene_smoke", "scene_smoke:r2").Result as OkObjectResult;
    var projectionPayload = projection?.Value as OpsBoardProjection;
    Assert(projectionPayload?.RecentEvents.Count == 2, "ops-board projection should include recent session events");
    Assert(projectionPayload?.UnresolvedItems.Count == 2, "ops-board projection should surface unresolved and heat items");
    Assert(projectionPayload?.PrepAssets.Count == 4, "ops-board projection should include prep assets for the scene, including governed packet bindings");

    var checklistUpdate = controller.UpdateChecklist(
        checklistCreated!.AssetId,
        new GmPrepChecklistUpdateRequest(
            UpdatedBy: "gm.smoke",
            ChecklistItems:
            [
                new GmPrepChecklistItem("smoke-1", "Kill the exterior cameras", true),
                new GmPrepChecklistItem("smoke-2", "Confirm escape vehicle", true)
            ])).Result as OkObjectResult;
    var checklistUpdatePayload = checklistUpdate?.Value as GmPrepAssetRecord;
    Assert(checklistUpdatePayload?.Status == "completed", "ops-board checklist updates should advance checklist status");

    var blockedReveal = controller.Reveal(
        revealCreated!.AssetId,
        new GmPrepAssetRevealRequest(
            SessionId: "session_ops_smoke",
            SceneId: "scene_smoke",
            SceneRevision: "scene_smoke:r2",
            RequestedBy: "gm.smoke",
            ApprovalState: "pending")).Result as OkObjectResult;
    var blockedRevealPayload = blockedReveal?.Value as GmPrepAssetRevealResult;
    Assert(blockedRevealPayload?.Outcome == "approval-required", "player reveal delivery should remain approval aware");

    var deliveredReveal = controller.Reveal(
        revealCreated.AssetId,
        new GmPrepAssetRevealRequest(
            SessionId: "session_ops_smoke",
            SceneId: "scene_smoke",
            SceneRevision: "scene_smoke:r2",
            RequestedBy: "gm.smoke",
            ApprovalState: "approved")).Result as OkObjectResult;
    var deliveredRevealPayload = deliveredReveal?.Value as GmPrepAssetRevealResult;
    Assert(deliveredRevealPayload?.Outcome == "delivered", "approved player reveal assets should deliver through the outbox");
    Assert(deliveredRevealPayload?.Message?.Card?.CardKind == "player-screen", "player-screen reveals should preserve their delivery card kind");

    var list = controller.ListPrepAssets(
        campaignId: "campaign_smoke",
        sessionId: "session_ops_smoke",
        sceneId: "scene_smoke",
        kind: null,
        includeReusableCampaignAssets: true).Result as OkObjectResult;
    var listPayload = list?.Value as GmPrepAssetListResponse;
    Assert(listPayload?.TotalCount == 5, "ops-board list endpoint should optionally include reusable campaign prep assets alongside governed packet bindings");
    Assert(listPayload?.Items.Any(item => item.AssetId == reusableNote!.AssetId) == true, "ops-board list endpoint should surface reusable campaign prep assets when requested");

    var libraryQuery = controller.ListPrepAssets(
        campaignId: "campaign_smoke",
        sessionId: "session_ops_smoke",
        sceneId: "scene_smoke",
        kind: null,
        includeReusableCampaignAssets: true,
        queryText: "reusable threat").Result as OkObjectResult;
    var libraryQueryPayload = libraryQuery?.Value as GmPrepAssetListResponse;
    Assert(libraryQueryPayload?.TotalCount == 1, "ops-board list endpoint should support reusable prep library search");
    Assert(libraryQueryPayload?.Items[0].AssetId == reusableNote!.AssetId, "ops-board search should return the reusable prep asset that matches title and tag terms");

    var checklistQuery = controller.ListPrepAssets(
        campaignId: "campaign_smoke",
        sessionId: "session_ops_smoke",
        sceneId: "scene_smoke",
        kind: null,
        includeReusableCampaignAssets: false,
        queryText: "escape vehicle").Result as OkObjectResult;
    var checklistQueryPayload = checklistQuery?.Value as GmPrepAssetListResponse;
    Assert(checklistQueryPayload?.TotalCount == 1, "ops-board list endpoint should support checklist label search");
    Assert(checklistQueryPayload?.Items[0].AssetId == checklistCreated!.AssetId, "ops-board search should find scene prep by checklist label text");

    var governedEncounterQuery = controller.ListPrepAssets(
        campaignId: "campaign_smoke",
        sessionId: "session_ops_smoke",
        sceneId: "scene_smoke",
        kind: null,
        includeReusableCampaignAssets: true,
        queryText: "checkpoint scanner").Result as OkObjectResult;
    var governedEncounterQueryPayload = governedEncounterQuery?.Value as GmPrepAssetListResponse;
    Assert(governedEncounterQueryPayload?.TotalCount == 1, "ops-board list endpoint should support governed encounter packet search by title and dependency content");
    Assert(governedEncounterQueryPayload?.Items[0].AssetId == governedPacket.AssetId, "ops-board search should find the governed encounter packet binding");
    var governedRosterQuery = controller.ListPrepAssets(
        campaignId: "campaign_smoke",
        sessionId: "session_ops_smoke",
        sceneId: "scene_smoke",
        kind: null,
        includeReusableCampaignAssets: true,
        queryText: "security roster").Result as OkObjectResult;
    var governedRosterQueryPayload = governedRosterQuery?.Value as GmPrepAssetListResponse;
    Assert(governedRosterQueryPayload?.TotalCount == 1, "ops-board list endpoint should support governed NPC pack search by title and dependency content");
    Assert(governedRosterQueryPayload?.Items[0].AssetId == governedNpcPack.AssetId, "ops-board search should find the governed NPC pack binding");
}

void VerifyInteropWorkflow()
{
    var ledger = new SessionLedgerService();
    var outbox = new DeliveryOutboxService();
    var ops = new GmOpsBoardService(ledger, outbox);
    var service = new InteropExportService(ops);
    var controller = new InteropController(service)
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };

    var prepCreate = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
        CampaignId: "campaign_interop_smoke",
        SessionId: "session_interop_smoke",
        SceneId: "scene_interop_smoke",
        Title: "Interop smoke prep",
        Kind: GmPrepAssetKind.Checklist,
        Audience: GmPrepAssetAudience.GameMaster,
        Summary: "prep surface for interop export",
        Body: "Confirm payload integrity before import",
        Tags: ["interop", "smoke"],
        ChecklistItems:
        [
            new GmPrepChecklistItem("interop-smoke-1", "Verify round-trip provenance")
        ],
        SourceEventIds: Array.Empty<string>(),
        CreatedBy: "gm.interop.smoke",
        RuntimeFingerprint: "interop-smoke"));
    Assert(prepCreate.AssetId.StartsWith("prep_", StringComparison.Ordinal), "interop smoke should seed prep assets for export.");
    var reusablePrep = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
        CampaignId: "campaign_interop_smoke",
        SessionId: null,
        SceneId: null,
        Title: "Reusable extraction ladder",
        Kind: GmPrepAssetKind.Note,
        Audience: GmPrepAssetAudience.GameMaster,
        Summary: "Campaign reusable prep",
        Body: "Escalate extraction plans if round-trip validation finds missing assets.",
        Tags: ["interop", "library"],
        ChecklistItems: Array.Empty<GmPrepChecklistItem>(),
        SourceEventIds: Array.Empty<string>(),
        CreatedBy: "gm.interop.smoke",
        RuntimeFingerprint: "interop-smoke"));
    Assert(reusablePrep.AssetId.StartsWith("prep_", StringComparison.Ordinal), "interop smoke should seed reusable campaign prep assets.");

    var exportResult = controller.Export(new InteropExportRequest(
        CampaignId: "campaign_interop_smoke",
        SessionId: "session_interop_smoke",
        RequestedBy: "gm.interop.smoke")).Result as OkObjectResult;
    var exported = exportResult?.Value as InteropExportPackage;
    Assert(exported is not null, "interop export endpoint should return an export package");
    Assert(exported!.Assets.Any(item => item.AssetKind == InteropAssetKind.Prep && item.DisplayName == "Reusable extraction ladder"), "interop export endpoint should include reusable campaign prep assets");
    Assert(exported!.ContractFamily == "interop_export_v1", "interop export should use the canonical family");
    Assert(exported.Manifest.CharacterCount >= 1, "interop export should include character assets");
    Assert(exported.Manifest.NpcCount >= 1, "interop export should include npc assets");
    Assert(exported.Manifest.SessionCount >= 1, "interop export should include session assets");
    Assert(exported.Manifest.EncounterCount >= 1, "interop export should include encounter assets");
    Assert(exported.Manifest.PrepCount >= 1, "interop export should include prep assets");
    Assert(exported.Manifest.TotalCount == exported.Assets.Count, "interop export manifest total should match exported assets");
    Assert(exported.Compatibility.FormatId == "chummer.portable-campaign-session.v1", "interop export should publish portable exchange format identity");
    Assert(exported.Compatibility.CompatibilityState == InteropCompatibilityStates.Compatible, "session-scoped interop export should be fully compatible");
    Assert(exported.Compatibility.SupportedExchangeFormats.Contains("foundry-vtt.scene-ledger.v1"), "interop export should advertise ecosystem exchange formats");
    Assert(exported.Compatibility.Notes.Any(note => note.Summary.Contains("Session session_interop_smoke is pinned", StringComparison.Ordinal)), "interop export should explain pinned-session portability");

    var importResult = controller.Import(new InteropImportRequest(exported, ImportedBy: "gm.interop.smoke")).Result as OkObjectResult;
    var imported = importResult?.Value as InteropImportResult;
    Assert(imported is not null, "interop import endpoint should return an import payload");
    Assert(imported!.ImportedCount == exported.Manifest.TotalCount, "interop import should accept untampered exports");
    Assert(imported.MutatedCount == exported.Manifest.TotalCount, "merge import should mutate every accepted asset");
    Assert(imported.RejectedCount == 0, "interop import should not reject untampered exports");
    Assert(imported.ProvenanceRoundTrip, "interop import should preserve provenance round-trip");
    Assert(imported.Compatibility.ReceiptSummary.Contains("Merge import accepted", StringComparison.Ordinal), "interop import should emit a merge receipt");

    var inspectOnlyResult = controller.Import(new InteropImportRequest(
        exported,
        ImportedBy: "gm.interop.smoke",
        Mode: InteropImportMode.InspectOnly)).Result as OkObjectResult;
    var inspectOnly = inspectOnlyResult?.Value as InteropImportResult;
    Assert(inspectOnly is not null, "interop inspect-only should return an import payload");
    Assert(inspectOnly!.ImportedCount == exported.Manifest.TotalCount, "inspect-only should validate every untampered asset");
    Assert(inspectOnly.MutatedCount == 0, "inspect-only should not mutate campaign truth");
    Assert(inspectOnly.Assets.All(item => item.Outcome == "inspected"), "inspect-only should label accepted assets as inspected");
    Assert(inspectOnly.Compatibility.ReceiptSummary.Contains("Inspect-only validated", StringComparison.Ordinal), "inspect-only should emit a no-mutation receipt");

    var roundTripResult = controller.RoundTrip(new InteropRoundTripRequest(
        Export: new InteropExportRequest(
            CampaignId: "campaign_interop_smoke",
            SessionId: "session_interop_smoke",
            RequestedBy: "gm.interop.smoke"),
        ImportedBy: "gm.interop.smoke")).Result as OkObjectResult;
    var roundTrip = roundTripResult?.Value as InteropRoundTripResult;
    Assert(roundTrip is not null, "interop round-trip endpoint should return a round-trip payload");
    Assert(roundTrip!.ProvenanceRoundTrip, "interop round-trip should preserve provenance");
    Assert(roundTrip.ExportPackage.Assets.All(asset => asset.Provenance.RoundTripId == roundTrip.RoundTripId), "interop round-trip id should remain stable across exported assets");

    var tamperedAssets = roundTrip.ExportPackage.Assets.ToArray();
    tamperedAssets[0] = tamperedAssets[0] with { PayloadJson = tamperedAssets[0].PayloadJson + " " };
    var tamperedPackage = roundTrip.ExportPackage with { Assets = tamperedAssets };
    var tamperedImportResult = controller.Import(new InteropImportRequest(tamperedPackage, ImportedBy: "gm.interop.smoke")).Result as OkObjectResult;
    var tamperedImport = tamperedImportResult?.Value as InteropImportResult;
    Assert(tamperedImport is not null, "interop import should still return a payload when detecting tampering");
    Assert(tamperedImport!.RejectedCount >= 1, "interop import should reject tampered assets");
    Assert(!tamperedImport.ProvenanceRoundTrip, "interop import should report failed provenance round-trip on tampering");
    Assert(tamperedImport.Compatibility.CompatibilityState == InteropCompatibilityStates.Incompatible, "tampered import should surface incompatible receipts");

    var tamperedReplaceResult = controller.Import(new InteropImportRequest(
        tamperedPackage,
        ImportedBy: "gm.interop.smoke",
        Mode: InteropImportMode.Replace)).Result as OkObjectResult;
    var tamperedReplace = tamperedReplaceResult?.Value as InteropImportResult;
    Assert(tamperedReplace is not null, "interop replace should still return a payload when validation fails");
    Assert(tamperedReplace!.MutatedCount == 0, "replace should not mutate campaign truth when any asset fails validation");
    Assert(tamperedReplace.Assets.Any(item => item.Outcome == "blocked"), "replace should block partial cutover when validation fails");
}

async Task VerifyNewspaperGatewayRoutingAsync()
{
    var configuration = new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["AiGateway:Providers:AiMagicx:Enabled"] = "true",
            ["AiGateway:Providers:MarkupGo:Enabled"] = "true",
            ["AiGateway:MonthlyAllowance"] = "240",
            ["AiGateway:BurstAllowancePerMinute"] = "40"
        })
        .Build();
    var gateway = new AiGatewayService(
        new ProviderRouter(configuration),
        new IProviderAdapter[]
        {
            new MockProviderAdapter(AiProvider.AiMagicx, enabled: true, primaryForStructuredOutput: true),
            new SmokeMarkupGoAdapter()
        },
        new AiBudgetService(configuration),
        new PromptRegistry());
    var renderService = new NewspaperRenderService(
        new NewspaperHtmlRenderer(new SmokeWebHostEnvironment(), new NewspaperValidationService()),
        gateway);

    var baseStory = new NewspaperIssueStory(
        Id: "story_smoke",
        Section: "must_know",
        LayoutRole: "cover_teaser",
        Headline: "Smoke Sheet Headline",
        Dek: "Gateway-routed PDF smoke",
        Summary: "A brief smoke issue validates that the newspaper render path goes through the AI gateway.",
        WhyItMatters: "Provider access stays centralized.",
        SourceLabel: "Smoke Wire",
        SourceUrl: "https://example.invalid/smoke",
        PublishedAt: DateTimeOffset.UtcNow,
        Image: new IssueStoryImage("fallback", "data:image/svg+xml;base64,PHN2Zy8+", "smoke"),
        PullQuote: null,
        Facts: new[] { "gateway", "markupgo" });
    var issue = new NewspaperIssue(
        IssueId: "issue_smoke",
        Title: "Smoke Sheet",
        Subtitle: "Gateway route",
        IssueDate: new DateOnly(2026, 3, 9),
        EditionNo: 7,
        Timezone: "UTC",
        MustKnow: new NewspaperIssueSection(new[]
        {
            baseStory with { Id = "story_smoke_1", LayoutRole = "cover_lead" },
            baseStory with { Id = "story_smoke_2" },
            baseStory with { Id = "story_smoke_3" }
        }),
        WorthKnowing: new NewspaperIssueSection(new[]
        {
            baseStory with { Id = "feature_smoke", Section = "worth_knowing", LayoutRole = "feature" }
        }),
        Agenda: new NewspaperIssueSection(Array.Empty<NewspaperIssueStory>()),
        Watchlist: new NewspaperIssueSection(new[]
        {
            baseStory with { Id = "watch_smoke", Section = "watchlist", LayoutRole = "quick_hit" }
        }),
        FooterNote: "Smoke footer");

    var result = await renderService.RenderPdfAsync(new RenderIssueHtmlRequest(issue), CancellationToken.None);
    Assert(result.Success, "newspaper PDF rendering should succeed through the AI gateway seam");
    Assert(result.Invocation.Decision.Provider == AiProvider.MarkupGo, "newspaper PDF rendering should require MarkupGo through gateway routing");
    Assert(result.Invocation.Request.RequiredProvider == AiProvider.MarkupGo, "newspaper PDF rendering should declare a required provider to avoid invalid fallbacks");
    Assert(result.Content is { Length: > 0 }, "newspaper PDF rendering should return binary content");
    Assert(Encoding.UTF8.GetString(result.Content!).Contains("Smoke Sheet", StringComparison.Ordinal), "gateway-routed PDF output should derive from rendered newspaper HTML");
}

async Task VerifySessionWorkflowAsync()
{
    var ledger = new SessionLedgerService();
    var runtimeBundles = new SessionRuntimeBundleService(ledger);
    var outbox = new DeliveryOutboxService();
    var ops = new GmOpsBoardService(ledger, outbox);
    var offlineSync = new OfflineSyncService(ledger, runtimeBundles, ops);
    var memory = new SessionMemoryService(ledger);
    var memoryIngestion = new SessionMemoryIngestionService(memory, new LocalTranscriptionProvider());
    var now = DateTimeOffset.UtcNow;

    var merge = await ledger.MergeEventsAsync(new[]
    {
        new SessionEventEnvelope("session_demo", "scene_01", "relationship.shift", "trust increased", now.AddSeconds(4), "evt_02", "rev-01", "evt_02"),
        new SessionEventEnvelope("session_demo", "scene_01", "objective.unresolved", "unresolved lead", now, "evt_01", "rev-01", "evt_01"),
        new SessionEventEnvelope("session_demo", "scene_01", "objective.unresolved", "unresolved lead", now, "evt_01", "rev-01", "evt_01"),
        new SessionEventEnvelope("session_demo", "scene_02", "objective.unresolved", "wrong scene", now.AddSeconds(9), "evt_03", "rev-02", "evt_03")
    });
    var projection = merge.Projection;

    Assert(merge.AcceptedEvents == 2, "session relay should accept only new events for the matching scene");
    Assert(merge.DuplicateEvents == 1, "session relay should report duplicate event ids");
    Assert(merge.IgnoredEvents == 1, "session relay should ignore cross-scene payloads");
    Assert(merge.Diagnostics.ContractFamily == "session_events_vnext", "session relay should report canonical contract diagnostics");
    Assert(merge.Diagnostics.SubmittedEvents == 4, "session relay diagnostics should preserve submit counts");
    Assert(merge.Diagnostics.Converged, "session relay diagnostics should report convergence after dedupe");
    Assert(projection.Version == 2, "session ledger should deduplicate repeated event ids");
    Assert(projection.Events[0].EventId == "evt_01", "session ledger should order events chronologically");
    Assert(projection.ContractFamily == "session_events_vnext", "session projections should advertise the canonical event contract family");
    Assert(projection.Events.All(evt => evt.ContractFamily == "session_events_vnext"), "session events should use the canonical envelope family");
    Assert(projection.Events.All(evt => evt.IdempotencyKey == evt.EventId), "session relay should preserve idempotency keys on the canonical envelope");
    Assert(!string.IsNullOrWhiteSpace(projection.ProjectionFingerprint) && projection.ProjectionFingerprint != "empty", "session projections should expose a stable fingerprint");

    var bundle = runtimeBundles.ResolveBundle("session_demo", "scene_01");
    Assert(bundle.Ready, "runtime bundle should become ready once events exist");
    Assert(bundle.BundleVersion.StartsWith("bundle-2-", StringComparison.Ordinal), "runtime bundle should derive a version from event history");
    Assert(bundle.ProjectionVersion == projection.Version, "runtime bundle should align to the current projection version");
    Assert(bundle.ProjectionFingerprint == projection.ProjectionFingerprint, "runtime bundle should carry the projection fingerprint");
    Assert(bundle.InvalidationSignals.Contains("event-stream:session_demo:scene_01"), "runtime bundle should emit event-stream invalidation signals");
    Assert(bundle.IncludedEventTypes.SequenceEqual(new[] { "objective.unresolved", "relationship.shift" }), "runtime bundle should expose the included event types");
    Assert(bundle.OfflineCapable, "runtime bundle should advertise offline-capable delivery");
    Assert(bundle.CollaborationMode == "local-first", "runtime bundle should advertise local-first collaboration");
    Assert(bundle.SupportedExchangeFormats.Contains("foundry-vtt.scene-ledger.v1"), "runtime bundle should advertise stable exchange seams");
    Assert(bundle.ContractFamily == "runtime_dtos_vnext", "runtime bundle should advertise the canonical runtime DTO family");
    Assert(bundle.RuntimeDtoKind == "session-runtime-bundle", "runtime bundle should advertise its DTO kind");

    var cachedBundle = runtimeBundles.ResolveBundle("session_demo", "scene_01");
    Assert(cachedBundle.GeneratedAtUtc == bundle.GeneratedAtUtc, "runtime bundle timestamps should remain stable while the projection is unchanged");

    var prep = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
        CampaignId: "campaign_demo",
        SessionId: "session_demo",
        SceneId: "scene_01",
        Title: "Offline smoke prep",
        Kind: GmPrepAssetKind.Checklist,
        Audience: GmPrepAssetAudience.GameMaster,
        Summary: "portable collaboration prep",
        Body: "validate offline sync",
        ChecklistItems:
        [
            new GmPrepChecklistItem("sync-1", "Export snapshot", true)
        ],
        CreatedBy: "gm.demo"));
    var reusablePrep = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
        CampaignId: "campaign_demo",
        SessionId: null,
        SceneId: null,
        Title: "Reusable chase ladder",
        Kind: GmPrepAssetKind.Note,
        Audience: GmPrepAssetAudience.GameMaster,
        Summary: "Campaign reusable prep",
        Body: "Escalate the chase with drones, patrols, and sealed checkpoints.",
        Tags: ["offline", "library"],
        CreatedBy: "gm.demo"));

    var snapshot = offlineSync.CreateSnapshot(new OfflineSyncSnapshotRequest(
        CampaignId: "campaign_demo",
        SessionId: "session_demo",
        SceneId: "scene_01",
        ExportedBy: "gm.demo",
        DeviceId: "tablet-smoke"));
    Assert(snapshot.ContractFamily == "offline_sync_snapshot_v1", "offline sync snapshot should use canonical family");
    Assert(snapshot.PrepAssets.Any(item => item.AssetId == prep.AssetId), "offline sync snapshot should include prep assets for collaboration surfaces");
    Assert(snapshot.PrepAssets.Any(item => item.AssetId == reusablePrep.AssetId), "offline sync snapshot should include reusable campaign prep assets");

    var reconcile = await offlineSync.ReconcileAsync(new OfflineSyncReconcileRequest(
        Snapshot: snapshot,
        ReconciledBy: "gm.demo",
        LocalPendingEvents:
        [
            new SessionEventEnvelope("session_demo", "scene_01", "offline.note", "cached", now.AddSeconds(8), "evt_04", "rev-01", "evt_04")
        ]));
    Assert(reconcile.SessionMerge.AcceptedEvents >= 1, "offline reconcile should import local pending events");
    Assert(reconcile.RuntimeBundle.OfflineCapable, "offline reconcile should resolve an offline-capable runtime bundle");

    var draft = memory.Draft(new SessionMemoryDraftRequest(
        SessionId: "session_demo",
        SceneId: "scene_01",
        Notes: "GM note",
        Transcript: "GM: Players entered the site.\nFace: unresolved lead",
        PlayerMessages: new[] { "Keep the decker covered" }));

    Assert(draft.UnresolvedHooks.Count == 1, "memory drafts should lift unresolved hooks from the event log");
    Assert(draft.RelationshipChanges.Count == 1, "memory drafts should surface relationship shifts");
    Assert(draft.RelationshipChangeDrafts.Count == 1, "memory drafts should emit structured relationship-change drafts");
    Assert(draft.RelationshipChangeDrafts[0].Evidence.Count >= 1, "relationship-change drafts should preserve evidence pointers");
    Assert(draft.RelationshipChangeDrafts[0].ProposedCanonTarget == "canon.relationship-change.v1", "relationship-change drafts should advertise a canon write-back target");
    Assert(draft.RecapDraft.DraftState == "draft", "session recap output should remain a draft until approved");
    Assert(draft.RecapDraft.Evidence.Count >= 2, "session recap drafts should carry evidence from the ledger and transcript");
    Assert(draft.UnresolvedThreadDrafts.Count == 1, "memory drafts should emit structured unresolved thread drafts");
    Assert(draft.UnresolvedThreadDrafts[0].Evidence.Count >= 2, "unresolved thread drafts should preserve both ledger and transcript evidence when available");
    Assert(draft.TimelineEntries.Any(entry => entry.SourceKind == "ledger-event"), "timeline drafts should include ledger-backed entries");
    Assert(draft.TimelineEntries.Any(entry => entry.SourceKind == "transcript"), "timeline drafts should include transcript-backed entries");
    Assert(draft.MemoryCandidateDrafts.Count >= 3, "memory drafts should project reviewable memory candidates");
    Assert(draft.MemoryCandidateDrafts.Any(candidate => candidate.Category == "relationship"), "memory candidates should include relationship review items");
    Assert(draft.MemoryCandidateDrafts.All(candidate => candidate.Evidence.Count >= 1), "memory candidates should preserve evidence for downstream review");
    Assert(draft.ProposedCanonTargets.Contains("canon.session-recap.v1"), "session memory drafts should advertise recap canon write-back targets");
    Assert(draft.ProposedCanonTargets.Contains("canon.session-timeline.v1"), "session memory drafts should advertise timeline canon write-back targets");
    Assert(draft.ProposedCanonTargets.Contains("canon.unresolved-thread.v1"), "session memory drafts should advertise unresolved-thread canon write-back targets");
    Assert(draft.ProposedCanonTargets.Contains("canon.relationship-change.v1"), "session memory drafts should advertise relationship-change canon write-back targets");
    Assert(draft.ProposedCanonTargets.Contains("canon.memory-candidate.v1"), "session memory drafts should advertise memory-candidate canon write-back targets");

    var ingested = await memoryIngestion.IngestAsync(new RunMemoryIngestionRequest(
        CampaignId: "campaign_demo",
        PrincipalId: "gm.demo",
        SessionId: "session_demo",
        SceneId: "scene_01",
        Notes: "ingest through transcription seam",
        Transcription: new TranscriptionRequest(
            Source: "GM: unresolved lead remains open",
            MimeType: "text/plain",
            LanguageHint: "en",
            PreserveSpeakerTurns: true)));

    Assert(ingested.CampaignId == "campaign_demo", "session memory ingestion should preserve campaign scope");
    Assert(ingested.PrincipalId == "gm.demo", "session memory ingestion should preserve principal scope");
    Assert(ingested.Transcription.Accepted, "session memory ingestion should call the transcription provider seam");
    Assert(ingested.Draft.TimelineEntries.Any(entry => entry.SourceKind == "transcript"), "session memory ingestion should feed transcript lines into draft outputs");
}

void VerifySpiderWorkflow()
{
    var ledger = new SessionLedgerService();
    var runtimeBundles = new SessionRuntimeBundleService(ledger);
    ledger.MergeEventsAsync(new[]
    {
        new SessionEventEnvelope("session_spider", "dockside", "matrix.heat", "overwatch building", DateTimeOffset.UtcNow, "evt_heat", "rev-7", "evt_heat"),
        new SessionEventEnvelope("session_spider", "dockside", "security.drone", "drone response converging", DateTimeOffset.UtcNow.AddSeconds(1), "evt_drone", "rev-7", "evt_drone")
    }).GetAwaiter().GetResult();

    var configuration = new ConfigurationBuilder().AddInMemoryCollection().Build();
    var promptRegistry = new PromptRegistry();
    var outbox = new DeliveryOutboxService();
    var actionService = new SpiderCardActionService(outbox, ledger);
    var controller = new SpiderController(
        new FastSignalDetector(),
        new SpiderDeepIngestionService(new AiGatewayService(
            new ProviderRouter(configuration),
            new IProviderAdapter[]
            {
                new MockProviderAdapter(AiProvider.AiMagicx, enabled: true, primaryForStructuredOutput: true),
                new MockProviderAdapter(AiProvider.OneMinAi, enabled: true, primaryForStructuredOutput: true)
            },
            new AiBudgetService(configuration),
            promptRegistry),
            promptRegistry,
            ledger),
        new DirectorPolicyEngine(),
        outbox,
        actionService,
        new InterruptionBudgetService(),
        runtimeBundles);

    var observation = new SpiderObservation(
        SessionId: "session_spider",
        Source: "ops-board",
        Payload: "scene:dockside|scene-revision:rev-7|god alert with drone response",
        ObservedAtUtc: DateTimeOffset.UtcNow,
        SceneId: "dockside",
        SceneRevision: "rev-7");

    var result = controller.Observe(observation, CancellationToken.None).GetAwaiter().GetResult();
    var delivered = result.Result as OkObjectResult;
    Assert(delivered is not null, "spider should deliver a tactical decision for elevated signals");
    var decision = delivered!.Value as PolicyDecision;
    Assert(decision is not null, "spider observe should return a policy decision payload");
    Assert(decision!.DecisionTier == "deep", "spider should escalate through the deep-ingestion tier for elevated signals");
    Assert(decision.DeepAnalysis is not null, "deep-ingestion should attach route and grounding details to the decision");
    Assert(decision.DeepAnalysis!.RouteDecision.Tier == "complex", "deep Spider routing should choose the complex tier");
    Assert(decision.DeepAnalysis.RouteDecision.SelectedModel == "gpt-5.4", "deep Spider routing should select the complex model");
    Assert(decision.DeepAnalysis.RouteDecision.ReasoningEffort == "medium", "deep Spider routing should request medium reasoning effort");
    Assert(Math.Abs(decision.DeepAnalysis.RouteDecision.EstimatedCostUsd - 0.0753d) < 0.0001d, "deep Spider routing should advertise the selected cost posture");
    Assert(decision.DeepAnalysis.PromptLineage?.TemplateName == "spider.tactical-card", "deep Spider routing should preserve prompt lineage");

    var messages = outbox.GetForScene("session_spider", "dockside", "rev-7");
    Assert(messages.Count == 1, "spider should queue exactly one tactical outbox item");

    var message = messages[0];
    Assert(message.CollaborationMode == "local-first", "spider outbox should preserve collaboration mode");
    Assert(message.ProjectionFingerprint != "empty", "spider outbox should bind cards to the session projection");
    Assert(message.Card is not null, "spider outbox should deliver tactical cards rather than plain chat");
    Assert(message.Card!.CardKind == "heat", "matrix/GOD observations should surface a heat card");
    Assert(message.Card.SceneRevision == "rev-7", "spider cards should remain bound to the current scene revision");
    Assert(message.Card.Actions.Any(action => action.ActionId == "prep-matrix-exit"), "spider cards should expose one-tap tactical actions");
    Assert(message.Card.Actions.Any(action => action.ActionId == "reveal-threat"), "deep Spider routing should preserve threat reveal actions");
    Assert(message.Card.Evidence.Any(pointer => pointer.Kind == "observation"), "spider cards should carry provenance pointers");
    Assert(message.Card.Payload is not null, "spider cards should include structured tactical payload metadata");
    Assert(message.Card.Payload!.Workflow == "ooda", "spider tactical payload should use the OODA workflow marker");
    Assert(message.Card.Payload.DecisionTier == "deep", "spider tactical payload should preserve decision tier");
    Assert(message.Card.Payload.BudgetLimitPerMinute >= 1, "spider tactical payload should include interruption budget limit");
    Assert(message.Card.Payload.BudgetRemainingThisMinute >= 0, "spider tactical payload should include remaining interruption budget");
    Assert(!message.Card.Payload.IsStaleDraft, "new spider tactical cards should start active");
    Assert(message.Content.Contains("tier=deep", StringComparison.Ordinal), "spider outbox payload should note the deep-decision tier");

    var prepResult = controller.ExecuteAction(
            message.Id,
            "prep-matrix-exit",
            new SpiderActionExecuteRequest(
                SessionId: "session_spider",
                SceneId: "dockside",
                SceneRevision: "rev-7",
                RequestedBy: "gm.ops"),
            CancellationToken.None)
        .GetAwaiter()
        .GetResult();
    var prepExecuted = prepResult.Result as OkObjectResult;
    Assert(prepExecuted is not null, "spider actions should execute through the controller surface");
    var prepPayload = prepExecuted!.Value as SpiderActionExecutionResult;
    Assert(prepPayload is not null, "spider actions should return an execution payload");
    var resolvedPrepPayload = prepPayload!;
    Assert(resolvedPrepPayload.Outcome == "executed", "non-approval spider actions should execute immediately");
    Assert(resolvedPrepPayload.AuditEventId is { Length: > 0 }, "executed spider actions should emit an audit event");
    Assert(resolvedPrepPayload.FollowUpMessage?.Card?.Title == "Matrix exit prepared", "matrix-exit actions should queue a follow-up outbox card");

    var revealPendingResult = controller.ExecuteAction(
            message.Id,
            "reveal-threat",
            new SpiderActionExecuteRequest(
                SessionId: "session_spider",
                SceneId: "dockside",
                SceneRevision: "rev-7",
                RequestedBy: "gm.ops"),
            CancellationToken.None)
        .GetAwaiter()
        .GetResult();
    var revealPending = (revealPendingResult.Result as OkObjectResult)?.Value as SpiderActionExecutionResult;
    Assert(revealPending is not null, "approval-aware spider actions should return a pending payload");
    var resolvedRevealPending = revealPending!;
    Assert(resolvedRevealPending.Outcome == "approval-required", "approval-aware spider actions should not auto-execute without approval");
    Assert(resolvedRevealPending.UpdatedMessage?.Card?.ActionExecutions?.Any(item => item.ActionId == "reveal-threat" && item.Status == "approval-required") == true, "approval-aware actions should record pending approval on the originating card");

    var revealApprovedResult = controller.ExecuteAction(
            message.Id,
            "reveal-threat",
            new SpiderActionExecuteRequest(
                SessionId: "session_spider",
                SceneId: "dockside",
                SceneRevision: "rev-7",
                RequestedBy: "gm.ops",
                ApprovalState: "approved",
                Notes: "player-safe wording confirmed"),
            CancellationToken.None)
        .GetAwaiter()
        .GetResult();
    var revealApproved = (revealApprovedResult.Result as OkObjectResult)?.Value as SpiderActionExecutionResult;
    Assert(revealApproved is not null, "approved spider actions should return an execution payload");
    var resolvedRevealApproved = revealApproved!;
    Assert(resolvedRevealApproved.Outcome == "executed", "approved spider actions should execute");
    Assert(resolvedRevealApproved.FollowUpMessage?.Card?.CardKind == "player-reveal", "approved reveal actions should queue a player reveal follow-up card");

    var actionEvents = ledger.GetEvents("session_spider", "dockside");
    Assert(actionEvents.Any(evt => evt.EventType == "spider.action.matrix-exit-prep"), "spider actions should write audit events into the session ledger");
    Assert(actionEvents.Any(evt => evt.EventType == "spider.action.threat-reveal"), "approved reveal actions should become auditable session events");
    Assert(actionEvents.Where(evt => evt.EventType.StartsWith("spider.action.", StringComparison.Ordinal)).All(evt => evt.ContractFamily == "session_events_vnext"), "spider audit events should use the canonical envelope");
    Assert(actionEvents.Where(evt => evt.EventType.StartsWith("spider.action.", StringComparison.Ordinal)).All(evt => evt.SceneRevision == "rev-7"), "spider audit events should preserve scene revision identity");

    var actionMessages = outbox.GetForScene("session_spider", "dockside", "rev-7");
    Assert(actionMessages.Count == 3, "spider action follow-ups should stay inside the scene outbox flow");
    Assert(actionMessages.Count(item => item.Card?.Tags.Contains("action-follow-up", StringComparer.Ordinal) == true) == 2, "follow-up spider actions should be represented as outbox cards");

    outbox.Enqueue(new DeliveryOutboxCreateRequest(
        SessionId: "session_spider",
        SceneId: "dockside",
        SceneRevision: "rev-8",
        Channel: "ops-board",
        Content: "manual test card for rev-8",
        ApprovalState: "pending",
        AutonomyMode: "Tactical",
        Ttl: TimeSpan.FromMinutes(8),
        Card: new SpiderTacticalCard(
            CardId: Guid.NewGuid().ToString("N"),
            SessionId: "session_spider",
            SceneId: "dockside",
            SceneRevision: "rev-8",
            CardKind: "tactical-note",
            Title: "Revision 8 note",
            Summary: "new revision note",
            InterruptionLevel: InterruptionLevel.Tactical,
            Status: "pending",
            ProjectionFingerprint: "manual",
            Tags: ["test"],
            Actions: Array.Empty<SpiderTacticalAction>(),
            Evidence: Array.Empty<EvidencePointer>(),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            ActionExecutions: Array.Empty<SpiderActionExecutionState>(),
            StaleAfterUtc: DateTimeOffset.UtcNow.AddMinutes(8),
            Payload: new SpiderTacticalPayload(DecisionTier: "test"))));

    var revisionEightMessages = outbox.GetForScene("session_spider", "dockside", "rev-8");
    Assert(revisionEightMessages.Count >= 1, "revision switch should project active messages for the newer scene revision");
    var olderRevisionMessages = outbox.GetForScene("session_spider", "dockside", "rev-7");
    Assert(olderRevisionMessages.Count == 0, "stale revision drafts should be invalidated from active outbox views");
    var staleOriginal = outbox.GetById(message.Id);
    Assert(staleOriginal?.Card?.Status == "stale", "older revision spider cards should be marked stale after invalidation");
    Assert(staleOriginal?.Card?.Payload?.IsStaleDraft == true, "stale invalidation should mark tactical payload stale state");
}

void VerifyLoreAndPersonaWorkflow()
{
    var lore = new LoreService();
    lore.Ingest(new LoreIngestionRequest(
        ChunkId: "chunk_redmond_matrix",
        Source: "grid_index",
        Jurisdiction: "Seattle Metroplex",
        District: "Redmond",
        TopicTags: "matrix,security",
        CampaignScope: "legwork",
        PackProfileLinkage: "pack_redmond",
        Content: "Matrix security chatter spikes around the Redmond exchange.",
        Region: "Barrens"));
    lore.Ingest(new LoreIngestionRequest(
        ChunkId: "chunk_bellevue_social",
        Source: "social_feed",
        Jurisdiction: "Seattle Metroplex",
        District: "Bellevue",
        TopicTags: "social,corp",
        CampaignScope: "downtime",
        PackProfileLinkage: "pack_bellevue",
        Content: "Corporate gala activity remains elevated in Bellevue."));
    lore.Ingest(new LoreIngestionRequest(
        ChunkId: "chunk_redmond_draft",
        Source: "rumor_board",
        Jurisdiction: "Seattle Metroplex",
        District: "Redmond",
        TopicTags: "matrix,gangs",
        CampaignScope: "legwork",
        PackProfileLinkage: "pack_redmond",
        Content: "Unconfirmed rumor says the exchange is quiet tonight.",
        Region: "Barrens",
        ApprovalState: "draft"));

    var loreResult = lore.Search(new LoreSearchRequest(
        District: "Redmond",
        TopicTag: "matrix",
        CampaignScope: "legwork",
        MaxItems: 2));
    Assert(loreResult.Chunks.Count == 1, "lore search should stay selective when filters are supplied");
    Assert(loreResult.Chunks[0].ChunkId == "chunk_redmond_matrix", "lore search should rank the most relevant chunk first");

    var loreLensResult = lore.QueryLoreLens(new LoreLensQuery(
        QueryText: "Redmond matrix exchange security chatter",
        Jurisdiction: "Seattle",
        District: "Redmond",
        Region: "Barrens",
        TopicTag: "matrix",
        CampaignScope: "legwork",
        PackProfileId: "pack_redmond",
        TopK: 2));
    Assert(loreLensResult.Retrieved == 1, "lore lens should default to approved-only retrieval");
    Assert(loreLensResult.Matches[0].Chunk.ChunkId == "chunk_redmond_matrix", "lore lens should return the approved vector match first");
    Assert(loreLensResult.Matches[0].MatchedTerms.Contains("matrix", StringComparer.OrdinalIgnoreCase), "lore lens should expose matched vector terms");
    Assert(loreLensResult.RuntimeFingerprint == $"lore-lens:{loreLensResult.VectorProfile}", "lore lens should expose a runtime fingerprint");
    Assert(loreLensResult.PackProfileIds.Contains("pack_redmond", StringComparer.OrdinalIgnoreCase), "lore lens should project matched pack profile ids");
    Assert(loreLensResult.SourcePointers.Contains("grid_index#chunk_redmond_matrix", StringComparer.OrdinalIgnoreCase), "lore lens should expose source pointers for matched chunks");
    Assert(loreLensResult.Matches[0].Evidence.Any(pointer => pointer.Kind == "lore-chunk"), "lore lens should surface retrieval evidence pointers");

    lore.Upsert("session_demo", new PersonaMemoryCard(
        PersonaId: "fixer_alpha",
        StaticCard: "Dockside fixer with a heavy comms footprint.",
        RelationshipState: "Trusted contact.",
        EpisodicMemory: "Helped the crew at dockside scene_01.",
        HiddenPlotMemory: "Tracking a matrix leak near Tacoma.",
        UpdatedAtUtc: DateTimeOffset.UtcNow,
        CardId: "fixer_alpha_docks",
        LocationId: "loc_tacoma_docks",
        Location: "Tacoma Docks",
        SceneIds: new[] { "scene_01", "dockside" },
        SessionContextTags: new[] { "legwork", "matrix", "ingress" }));
    lore.Upsert("session_demo", new PersonaMemoryCard(
        PersonaId: "exec_beta",
        StaticCard: "Bellevue corporate liaison.",
        RelationshipState: "Cold and transactional.",
        EpisodicMemory: "Met the team at a Bellevue gala.",
        HiddenPlotMemory: "Protecting a board seat.",
        UpdatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-10),
        CardId: "exec_beta_gala",
        LocationId: "loc_bellevue_gala",
        Location: "Bellevue Gala",
        SceneIds: new[] { "scene_02", "gala-floor" },
        SessionContextTags: new[] { "social", "corp", "cover" }));
    lore.Upsert("session_demo", new PersonaMemoryCard(
        PersonaId: "fixer_alpha",
        StaticCard: "Same fixer, different operating posture.",
        RelationshipState: "Watching the team carefully.",
        EpisodicMemory: "Brokered a quiet meet in Touristville after a messy extraction.",
        HiddenPlotMemory: "Selling selective intel to keep Knight Errant off balance.",
        UpdatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
        CardId: "fixer_alpha_touristville",
        LocationId: "loc_touristville",
        Location: "Touristville",
        SceneIds: new[] { "scene_03", "touristville-meet" },
        SessionContextTags: new[] { "heat", "cleanup", "matrix" }));

    var personaResult = lore.Search("session_demo", new PersonaMemoryQuery(
        SessionId: "session_demo",
        SceneId: "dockside scene_01",
        TopK: 1));
    Assert(personaResult.Retrieved == 1, "persona retrieval should honor top-k selection");
    Assert(personaResult.Cards[0].PersonaId == "fixer_alpha", "persona retrieval should rank scene-relevant memory first");
    Assert(personaResult.Cards[0].CardId == "fixer_alpha_docks", "persona retrieval should keep distinct scoped memories for the same NPC");

    var personaScopedByNpcAndLocation = lore.Search("session_demo", new PersonaMemoryQuery(
        SessionId: "session_demo",
        TopK: 2,
        PersonaId: "fixer_alpha",
        LocationId: "loc_touristville",
        SessionContext: new[] { "cleanup" }));
    Assert(personaScopedByNpcAndLocation.Retrieved == 1, "persona retrieval should scope by npc and location");
    Assert(personaScopedByNpcAndLocation.Cards[0].CardId == "fixer_alpha_touristville", "persona retrieval should return the matching location-scoped memory");

    var personaScopedByContext = lore.Search("session_demo", new PersonaMemoryQuery(
        SessionId: "session_demo",
        TopK: 1,
        Location: "Bellevue",
        SessionContext: new[] { "corp", "cover" }));
    Assert(personaScopedByContext.Retrieved == 1, "persona retrieval should stay selective for location and session context scope");
    Assert(personaScopedByContext.Cards[0].PersonaId == "exec_beta", "persona retrieval should favor the context-matching card");
}

async Task VerifyCreativeWorkflowAsync()
{
    var assets = new AssetLifecycleService();
    var jobs = new MediaRenderJobService(assets);
    var outbox = new DeliveryOutboxService();
    var ledger = new SessionLedgerService();
    var memory = new SessionMemoryService(ledger);
    var routeCinema = new RouteCinemaService(jobs, assets);
    var npcVideo = new NpcMessageVideoService(jobs, assets, outbox);
    var news = new NewsNetworkService(jobs, assets, ledger, memory, outbox);
    var packets = new PacketFactoryService(jobs);
    var portraits = new PortraitForgeService(assets, jobs);

    await ledger.MergeEventsAsync(new[]
    {
        new SessionEventEnvelope(
            "session_demo",
            "scene_01",
            "threat.alert",
            "Knight Errant patrols converged on the Tacoma docks after a grid flicker.",
            DateTimeOffset.UtcNow.AddMinutes(-7),
            "news_evt_01",
            "rev-news",
            "news_evt_01"),
        new SessionEventEnvelope(
            "session_demo",
            "scene_01",
            "fallout.thread",
            "The commlink courier is still missing after the handoff.",
            DateTimeOffset.UtcNow.AddMinutes(-4),
            "news_evt_02",
            "rev-news",
            "news_evt_02")
    });

    var route = await routeCinema.GenerateAsync(new RouteCinemaRequest(
        SourceNode: "Tacoma Docks",
        TargetNode: "Auburn Safehouse"));
    Assert(!string.IsNullOrWhiteSpace(route.RouteVideoJobId), "route cinema should enqueue a render job");
    Assert(!string.IsNullOrWhiteSpace(route.PreviewJobId), "route cinema should enqueue a review preview job");
    Assert(!string.IsNullOrWhiteSpace(route.RouteCinemaId), "route cinema should project a stable orchestration id");
    Assert(route.Artifacts.Count == 2, "route cinema should project preview and video travel-media outputs");
    Assert(route.ReviewState == "draft", "route cinema should begin in draft review state");

    var routeAgain = await routeCinema.GenerateAsync(new RouteCinemaRequest(
        SourceNode: "Tacoma Docks",
        TargetNode: "Auburn Safehouse"));
    Assert(route.RouteVideoJobId == routeAgain.RouteVideoJobId, "route cinema should deduplicate identical render jobs");
    Assert(route.PreviewJobId == routeAgain.PreviewJobId, "route cinema should deduplicate identical preview jobs");
    Assert(route.RouteCinemaId == routeAgain.RouteCinemaId, "route cinema should deduplicate identical orchestration records");

    var npc = await npcVideo.CreateAsync(new NpcVideoMessageRequest(
        SessionId: "session_demo",
        SceneId: "scene_01",
        NpcId: "npc_johnson",
        MessageText: "Package is live. Burn after reading.",
        Style: "cold_corporate"));
    Assert(!string.IsNullOrWhiteSpace(npc.VideoJobId), "npc messages should enqueue a render job");
    Assert(!string.IsNullOrWhiteSpace(npc.MessageId), "npc messages should project a stable orchestration id");
    Assert(npc.PublishState == "draft", "npc messages should begin as unpublished drafts");

    var npcAgain = await npcVideo.CreateAsync(new NpcVideoMessageRequest(
        SessionId: "session_demo",
        SceneId: "scene_01",
        NpcId: "npc_johnson",
        MessageText: "Package is live. Burn after reading.",
        Style: "cold_corporate"));
    Assert(npc.MessageId == npcAgain.MessageId, "npc messages should deduplicate identical orchestration requests");

    var briefing = await news.BuildNewsBriefAsync(new NewsBriefRequest(
        CampaignId: "cmp_demo",
        SessionId: "session_demo",
        SceneId: "scene_01",
        SceneRevision: "rev_02",
        Transcript: "GM: The grid flicker drew attention.\nRigger: The courier never checked in.",
        Notes: "Approved recap should stay grounded on verified patrol movement.",
        ApprovedNotes: new[] { "Err on concise public-safe phrasing." },
        SeedItems: new[]
        {
            new NewsItem(
                Title: "Grid flicker reported",
                Source: "Matrix Watch",
                Summary: "The district grid dipped for three seconds before stabilizing.",
                Url: "https://example.invalid/grid-flicker")
        }));
    Assert(!string.IsNullOrWhiteSpace(briefing.NewsBriefId), "news briefs should project a persistent brief id");
    Assert(briefing.Facts.Count >= 3, "news briefs should ground recap output on multiple facts");
    Assert(!string.IsNullOrWhiteSpace(briefing.RecapAssetId), "news briefs should store a reviewable recap asset");
    Assert(briefing.ApprovalState == AssetApprovalState.Pending, "news recap assets should begin pending approval");
    Assert(!string.IsNullOrWhiteSpace(briefing.VideoJobId), "news briefs should enqueue a render job when video is enabled");

    var pendingNewsDelivery = await news.DeliverAsync(
        briefing.NewsBriefId,
        new NewsBriefDeliveryRequest(
            SessionId: "session_demo",
            SceneId: "scene_01",
            SceneRevision: "rev_02",
            RequestedBy: "gm"));
    Assert(pendingNewsDelivery.Outcome == "approval-required", "news brief delivery should be gated on approved recap assets");

    var pendingNpcPublish = await npcVideo.PublishAsync(
        npc.MessageId,
        new NpcVideoMessagePublishRequest(
            SessionId: "session_demo",
            SceneId: "scene_01",
            SceneRevision: "rev_02",
            RequestedBy: "gm",
            Surfaces: new[] { "players" },
            Archive: false));
    Assert(pendingNpcPublish.Outcome == "approval-required", "npc video publication should be gated on approved assets");

    var packet = await packets.CreateAsync(new PacketFactoryRequest(
        Title: "Johnson Briefing Packet",
        Subject: "Recover the stolen commlink before dawn.",
        References: new[] { "npc_johnson", "cargo_manifest_a12" },
        Attachments: new[]
        {
            new PacketAttachmentRequest(PacketAttachmentTargetKind.Route, "cmp_demo", "Campaign briefcase"),
            new PacketAttachmentRequest(PacketAttachmentTargetKind.Message, "msg_0042", "Johnson ping")
        }));
    var packetArtifacts = NotNull(packet.Artifacts, "packet factory should return artifact projections");
    var packetAttachments = NotNull(packet.Attachments, "packet factory should return attachment projections");
    Assert(packetArtifacts.Count == 3, "packet factory should enqueue preview, pdf, and thumbnail jobs");
    Assert(packetAttachments.Count == 2, "packet factory should project requested attachments");
    Assert(packetArtifacts.Any(static artifact => artifact.Role == PacketArtifactRole.Pdf && !string.IsNullOrWhiteSpace(artifact.JobId)), "packet factory should route pdf generation through the shared job pipeline");

    var baselinePortrait = await portraits.ForgeAsync(new PortraitForgeRequest(
        EntityId: "npc_johnson",
        Style: "corp_clean",
        Notes: "Baseline dossier render."));
    Assert(!string.IsNullOrWhiteSpace(baselinePortrait.PortraitDraftId), "portrait forge should project a stable draft id");
    Assert(!string.IsNullOrWhiteSpace(baselinePortrait.PortraitIdentityId), "portrait forge should project a stable canonical identity id");
    Assert(baselinePortrait.CanonicalPortraitId is null, "portrait forge should not assign a canonical portrait before approval");
    Assert(baselinePortrait.DraftState == "draft", "portrait forge drafts should begin pending review");
    Assert(baselinePortrait.Variants.Count == 5, "portrait forge should enqueue all configured portrait variants");
    Assert(baselinePortrait.Variants.All(static variant => !string.IsNullOrWhiteSpace(variant.JobId)), "portrait forge should enqueue asynchronous jobs for every variant");

    foreach (var variant in baselinePortrait.Variants)
    {
        await WaitForSucceededJobAsync(jobs, variant.JobId);
    }

    var approvedBaselinePortrait = await portraits.ApproveAsync(
        baselinePortrait.PortraitDraftId,
        new PortraitApprovalRequest(
            Variant: "canonical",
            ApprovedBy: "gm",
            Notes: "Establish canon headshot."));
    Assert(approvedBaselinePortrait is not null, "portrait forge approval should return the approved draft");
    var resolvedApprovedBaselinePortrait = NotNull(approvedBaselinePortrait, "portrait forge approval should return the approved draft");
    var baselineCanonicalVariant = resolvedApprovedBaselinePortrait.Variants.First(static variant => variant.Variant == "canonical");
    Assert(resolvedApprovedBaselinePortrait.CanonicalPortraitId == baselineCanonicalVariant.AssetId, "approved baseline portrait should become canonical for the entity");
    Assert(resolvedApprovedBaselinePortrait.DraftState == "approved", "approved portrait drafts should project approved state");
    Assert(baselineCanonicalVariant.ApprovalState == AssetApprovalState.Approved, "approved canonical portrait should promote the selected asset");
    Assert(baselineCanonicalVariant.RetentionState == AssetRetentionState.Pinned, "approved canonical portrait should pin the selected asset");
    Assert(baselineCanonicalVariant.IsCanonical, "approved canonical portrait should mark the selected variant as canonical");

    var rerolledPortrait = await portraits.ForgeAsync(new PortraitForgeRequest(
        EntityId: "npc_johnson",
        Style: "corp_clean",
        Notes: "Swap to infiltration-ready face.",
        AllowUnderscover: true,
        RerollOfPortraitId: baselinePortrait.PortraitDraftId));
    Assert(rerolledPortrait.PortraitIdentityId == baselinePortrait.PortraitIdentityId, "rerolls should preserve the entity portrait identity");
    Assert(rerolledPortrait.RerollOfPortraitId == baselinePortrait.PortraitDraftId, "rerolls should record the immediate parent portrait draft");
    Assert(rerolledPortrait.RerollRootPortraitId == baselinePortrait.PortraitDraftId, "first reroll should use the original draft as its lineage root");
    Assert(rerolledPortrait.RerollDepth == 1, "first reroll should increment lineage depth");
    Assert(rerolledPortrait.CanonicalPortraitId == baselineCanonicalVariant.AssetId, "rerolls should expose the current canonical portrait while review is pending");

    foreach (var variant in rerolledPortrait.Variants)
    {
        await WaitForSucceededJobAsync(jobs, variant.JobId);
    }

    var approvedReroll = await portraits.ApproveAsync(
        rerolledPortrait.PortraitDraftId,
        new PortraitApprovalRequest(
            Variant: "undercover",
            ApprovedBy: "gm",
            Notes: "Rotate canon to the undercover look."));
    Assert(approvedReroll is not null, "approved reroll should resolve to an updated portrait draft");
    var resolvedApprovedReroll = NotNull(approvedReroll, "approved reroll should resolve to an updated portrait draft");
    var rerollCanonicalVariant = resolvedApprovedReroll.Variants.First(static variant => variant.Variant == "undercover");
    Assert(resolvedApprovedReroll.CanonicalPortraitId == rerollCanonicalVariant.AssetId, "approved reroll should replace the entity canonical portrait");
    Assert(rerollCanonicalVariant.ApprovalState == AssetApprovalState.Approved, "approved reroll should promote the selected variant");
    Assert(rerollCanonicalVariant.RetentionState == AssetRetentionState.Pinned, "approved reroll should pin the selected canonical asset");
    Assert(rerollCanonicalVariant.IsCanonical, "approved reroll should mark the selected variant as canonical");
    var rerollReviewHistory = NotNull(resolvedApprovedReroll.ReviewHistory, "approved rerolls should retain review history");
    Assert(rerollReviewHistory.Count == 1, "approved rerolls should retain review history");
    Assert(rerollReviewHistory[0].PreviousCanonicalPortraitId == baselineCanonicalVariant.AssetId, "review history should record the previous canonical portrait");

    var supersededBaselinePortrait = portraits.Get(baselinePortrait.PortraitDraftId);
    Assert(supersededBaselinePortrait is not null, "portrait drafts should remain queryable after supersession");
    Assert(supersededBaselinePortrait!.DraftState == "superseded", "previous canonical portrait draft should become superseded after a later approval");
    var supersededCanonicalVariant = supersededBaselinePortrait.Variants.First(static variant => variant.Variant == "canonical");
    Assert(supersededCanonicalVariant.ApprovalState == AssetApprovalState.Approved, "superseded canonical assets should remain approved for audit history");
    Assert(supersededCanonicalVariant.RetentionState == AssetRetentionState.Persisted, "superseded canonical assets should remain persisted but no longer pinned");

    var portraitHistory = portraits.ListForEntity("npc_johnson");
    Assert(portraitHistory.Count == 2, "portrait forge should retain full draft history per entity");
    Assert(portraitHistory[0].PortraitIdentityId == baselinePortrait.PortraitIdentityId, "portrait history should keep a stable identity across rerolls");

    var exportAttachments = await packets.AttachAsync(
        packet.PacketId,
        new PacketAttachmentBatchRequest(new[]
        {
            new PacketAttachmentRequest(PacketAttachmentTargetKind.Export, "export_bundle_01", "GM export"),
            new PacketAttachmentRequest(PacketAttachmentTargetKind.Route, "cmp_demo", "duplicate ignored")
        }));
    Assert(exportAttachments.Count == 3, "packet attachments should deduplicate repeated targets while allowing later export attachment");

    var completedRoutePreviewJob = await WaitForSucceededJobAsync(jobs, route.PreviewJobId);
    var completedRouteJob = await WaitForSucceededJobAsync(jobs, route.RouteVideoJobId);
    var completedNpcJob = await WaitForSucceededJobAsync(jobs, npc.VideoJobId);
    var completedNewsJob = await WaitForSucceededJobAsync(jobs, briefing.VideoJobId!);
    var previewPacketJob = await WaitForSucceededJobAsync(jobs, packetArtifacts.First(static artifact => artifact.Role == PacketArtifactRole.Preview).JobId);
    var pdfPacketJob = await WaitForSucceededJobAsync(jobs, packetArtifacts.First(static artifact => artifact.Role == PacketArtifactRole.Pdf).JobId);
    var thumbnailPacketJob = await WaitForSucceededJobAsync(jobs, packetArtifacts.First(static artifact => artifact.Role == PacketArtifactRole.Thumbnail).JobId);

    var routePreviewAsset = assets.Resolve(completedRoutePreviewJob.AssetId!);
    var routeAsset = assets.Resolve(completedRouteJob.AssetId!);
    var npcAsset = assets.Resolve(completedNpcJob.AssetId!);
    var newsAsset = assets.Resolve(completedNewsJob.AssetId!);
    var newsRecapAsset = assets.Resolve(briefing.RecapAssetId);
    var packetPreviewAsset = assets.Resolve(previewPacketJob.AssetId!);
    var packetPdfAsset = assets.Resolve(pdfPacketJob.AssetId!);
    var packetThumbnailAsset = assets.Resolve(thumbnailPacketJob.AssetId!);
    Assert(routePreviewAsset is not null, "route cinema preview asset should resolve before TTL expiry");
    Assert(routeAsset is not null, "route cinema asset should resolve before TTL expiry");
    Assert(npcAsset is not null, "npc video asset should resolve before TTL expiry");
    Assert(newsAsset is not null, "news asset should resolve before TTL expiry");
    Assert(newsRecapAsset is not null, "news recap asset should resolve before approval");
    Assert(packetPreviewAsset is not null, "packet preview asset should resolve before TTL expiry");
    Assert(packetPdfAsset is not null, "packet pdf asset should resolve before TTL expiry");
    Assert(packetThumbnailAsset is not null, "packet thumbnail asset should resolve before TTL expiry");
    var resolvedRoutePreviewAsset = NotNull(routePreviewAsset, "route cinema preview asset should resolve before TTL expiry");
    var resolvedRouteAsset = NotNull(routeAsset, "route cinema asset should resolve before TTL expiry");
    var resolvedNewsRecapAsset = NotNull(newsRecapAsset, "news recap asset should resolve before approval");
    var resolvedNpcAsset = NotNull(npcAsset, "npc video asset should resolve before TTL expiry");
    Assert(resolvedRoutePreviewAsset.ApprovalState == AssetApprovalState.Pending, "route cinema preview assets should begin pending approval");
    Assert(resolvedRouteAsset.StorageKey?.StartsWith("r2://creative-assets/active/", StringComparison.Ordinal) == true, "heavy assets should project object-storage keys instead of app-server blobs");
    Assert(resolvedRouteAsset.ApprovalState == AssetApprovalState.Pending, "generated heavy assets should begin pending approval");
    Assert(resolvedRouteAsset.RetentionState == AssetRetentionState.ApprovalPending, "generated heavy assets should remain evictable until approved");
    Assert(resolvedNpcAsset.ApprovalState == AssetApprovalState.Pending, "npc message videos should begin pending approval");
    Assert(resolvedNpcAsset.RetentionState == AssetRetentionState.ApprovalPending, "npc message videos should remain disposable until approved");
    Assert(resolvedNewsRecapAsset.ApprovalState == AssetApprovalState.Pending, "news recap packages should require approval before delivery");
    Assert(resolvedNewsRecapAsset.RetentionState == AssetRetentionState.ApprovalPending, "news recap packages should remain pending until approved");

    var approvedNpc = await assets.ApplyLifecycleAsync(
        completedNpcJob.AssetId!,
        new AssetLifecycleMutationRequest(ApprovalState: AssetApprovalState.Approved));
    Assert(approvedNpc?.RetentionState == AssetRetentionState.Persisted, "approved npc videos should persist for later publish surfaces");

    var approvedNewsRecap = await assets.ApplyLifecycleAsync(
        briefing.RecapAssetId,
        new AssetLifecycleMutationRequest(ApprovalState: AssetApprovalState.Approved));
    Assert(approvedNewsRecap?.RetentionState == AssetRetentionState.Persisted, "approved news recap packages should persist for later archive delivery");

    var deliveredNews = await news.DeliverAsync(
        briefing.NewsBriefId,
        new NewsBriefDeliveryRequest(
            SessionId: "session_demo",
            SceneId: "scene_01",
            SceneRevision: "rev_02",
            RequestedBy: "gm",
            Channel: "players",
            Archive: true));
    Assert(deliveredNews.Outcome == "delivered", "approved news briefs should deliver to configured channels");
    Assert(deliveredNews.Messages.Count == 2, "news brief delivery should fan out to player and archive channels");
    Assert(deliveredNews.Messages.Any(static message => message.Channel == "players"), "news brief delivery should include the player-facing recap");
    Assert(deliveredNews.Messages.Any(static message => message.Channel == "archive"), "news brief delivery should include the archive copy");
    Assert(outbox.GetForScene("session_demo", "scene_01", "rev_02").Count >= 2, "approved news brief delivery should publish outbox messages");

    var publishedNpc = await npcVideo.PublishAsync(
        npc.MessageId,
        new NpcVideoMessagePublishRequest(
            SessionId: "session_demo",
            SceneId: "scene_01",
            SceneRevision: "rev_02",
            RequestedBy: "gm",
            Surfaces: new[] { "players", "gm-ops" },
            Archive: true,
            Notes: "Release after confirming the courier handoff."));
    Assert(publishedNpc.Outcome == "published", "approved npc videos should publish to requested surfaces");
    Assert(publishedNpc.Messages.Count == 3, "npc video publication should fan out to requested surfaces plus archive");
    Assert(publishedNpc.Messages.Any(static message => message.Channel == "players"), "npc video publication should include player-facing delivery");
    Assert(publishedNpc.Messages.Any(static message => message.Channel == "gm-ops"), "npc video publication should include gm ops delivery");
    Assert(publishedNpc.Messages.Any(static message => message.Channel == "archive"), "npc video publication should include archive delivery when requested");

    var resolvedBriefing = news.Get(briefing.NewsBriefId);
    Assert(resolvedBriefing is not null, "news brief lookup should return stored draft state");
    Assert(resolvedBriefing!.DeliveryState == "delivered", "news brief lookup should reflect delivery state");
    Assert(resolvedBriefing.DeliveryMessageIds.Count == 2, "news brief lookup should project delivery message ids");

    var resolvedNpc = npcVideo.Get(npc.MessageId);
    Assert(resolvedNpc is not null, "npc video lookup should return stored orchestration state");
    Assert(resolvedNpc!.PublishState == "published", "npc video lookup should reflect publish state");
    Assert(resolvedNpc.PublishedMessageIds.Count == 3, "npc video lookup should project published message ids");

    var resolvedPacket = packets.Get(packet.PacketId);
    Assert(resolvedPacket is not null, "packet factory should retain packet projection state");
    Assert(resolvedPacket!.PreviewAssetId == previewPacketJob.AssetId, "packet projection should hydrate preview asset id after job completion");
    Assert(resolvedPacket.PdfAssetId == pdfPacketJob.AssetId, "packet projection should hydrate pdf asset id after job completion");
    Assert(resolvedPacket.ThumbnailAssetId == thumbnailPacketJob.AssetId, "packet projection should hydrate thumbnail asset id after job completion");
    var resolvedPacketAttachments = NotNull(resolvedPacket.Attachments, "packet projection should retain attachment projections");
    Assert(resolvedPacketAttachments.Count == 3, "packet projection should surface all attachment targets");
    Assert(resolvedPacketAttachments.Any(static attachment => attachment.TargetKind == PacketAttachmentTargetKind.Export), "packet projection should allow export attachments without bespoke orchestration");
    Assert(resolvedPacketAttachments.All(static attachment => attachment.Artifacts.All(artifact => artifact.JobState == MediaRenderJobState.Succeeded)), "packet attachments should track shared job completion state");

    var resolvedRoute = routeCinema.Get(route.RouteCinemaId);
    Assert(resolvedRoute is not null, "route cinema lookup should return stored orchestration state");
    Assert(resolvedRoute!.PreviewAssetId == completedRoutePreviewJob.AssetId, "route cinema lookup should hydrate preview asset id after job completion");
    Assert(resolvedRoute.RouteVideoAssetId == completedRouteJob.AssetId, "route cinema lookup should hydrate route video asset id after job completion");
    Assert(resolvedRoute.Artifacts.All(static artifact => artifact.JobState == MediaRenderJobState.Succeeded), "route cinema lookup should track preview and video job completion");
    Assert(routeCinema.List("cmp_demo").Any(item => item.RouteCinemaId == route.RouteCinemaId), "route cinema campaign listing should include the stored draft");

    await AssertThrowsInvalidOperationAsync(
        () => assets.ApplyLifecycleAsync(
            completedRouteJob.AssetId!,
            new AssetLifecycleMutationRequest(Pin: true)),
        "pinning should require prior approval");

    var approvedRoute = await assets.ApplyLifecycleAsync(
        completedRouteJob.AssetId!,
        new AssetLifecycleMutationRequest(ApprovalState: AssetApprovalState.Approved, Pin: true));
    Assert(approvedRoute is not null, "approved route asset should still be addressable");
    var resolvedApprovedRoute = NotNull(approvedRoute, "approved route asset should still be addressable");
    Assert(resolvedApprovedRoute.ApprovalState == AssetApprovalState.Approved, "approval mutation should promote the asset");
    Assert(resolvedApprovedRoute.IsPinned, "approved asset should allow pinning");
    Assert(resolvedApprovedRoute.RetentionState == AssetRetentionState.Pinned, "pinned approved asset should stop being evictable");
    Assert(resolvedApprovedRoute.StorageClass == AssetStorageClass.LongTermObjectStorage, "approved pinned assets should move to long-term object storage posture");
    Assert(assets.Resolve(completedRouteJob.AssetId!)?.RetentionState == AssetRetentionState.Pinned, "pinned assets should remain resolvable");
    Assert(routeCinema.Get(route.RouteCinemaId)?.ReviewState == "approved", "route cinema lookup should reflect approved review posture");

    var cachedPolicy = new AssetLifecyclePolicy(
        CacheTtl: TimeSpan.FromMinutes(5),
        LongTermCache: false,
        MaxBytes: 1024,
        RequiresApproval: false,
        PersistOnApproval: false,
        StorageClass: AssetStorageClass.ObjectStorage,
        AllowPersistentPinning: true);
    var cachedFirst = await assets.StoreAsync("portrait/cache", "<portrait>same</portrait>", "entity-cache", cachedPolicy);
    var cachedSecond = await assets.StoreAsync("portrait/cache", "<portrait>same</portrait>", "entity-cache", cachedPolicy);
    Assert(cachedFirst.AssetId == cachedSecond.AssetId, "asset lifecycle should reuse identical active cache entries");
    Assert(cachedSecond.CacheReused, "second store should report cache reuse");

    var shortDraftPolicy = new AssetLifecyclePolicy(
        CacheTtl: TimeSpan.FromMilliseconds(50),
        LongTermCache: false,
        MaxBytes: 2048,
        RequiresApproval: true,
        PersistOnApproval: true,
        StorageClass: AssetStorageClass.ObjectStorage,
        AllowPersistentPinning: true);
    var expiringDraft = await assets.StoreAsync("news/video", "<draft>expire</draft>", "campaign-expire", shortDraftPolicy);
    var expiringDraftCatalog = assets.Resolve(expiringDraft.AssetId);
    Assert(expiringDraftCatalog is not null, "new draft asset should resolve before sweep");
    var resolvedExpiringDraft = NotNull(expiringDraftCatalog, "new draft asset should resolve before sweep");
    var draftSweep = assets.SweepExpired(resolvedExpiringDraft.CreatedAtUtc + shortDraftPolicy.CacheTtl + TimeSpan.FromMilliseconds(1));
    Assert(draftSweep.ExpiredAssetCount >= 1, "sweep should expire draft assets once TTL elapses");
    Assert(assets.Resolve(expiringDraft.AssetId) is null, "expired draft asset should become unavailable");

    var persistentAsset = await assets.StoreAsync("packet/brief", "<html>persist</html>", "packet-demo", shortDraftPolicy);
    var persistentCatalog = assets.Resolve(persistentAsset.AssetId);
    Assert(persistentCatalog is not null, "persistent candidate should resolve before approval");
    var resolvedPersistentCatalog = NotNull(persistentCatalog, "persistent candidate should resolve before approval");
    var persisted = await assets.ApplyLifecycleAsync(
        persistentAsset.AssetId,
        new AssetLifecycleMutationRequest(ApprovalState: AssetApprovalState.Approved));
    Assert(persisted?.RetentionState == AssetRetentionState.Persisted, "approval should persist assets configured for approval-aware retention");
    assets.SweepExpired(resolvedPersistentCatalog.CreatedAtUtc + shortDraftPolicy.CacheTtl + TimeSpan.FromMilliseconds(1));
    Assert(assets.Resolve(persistentAsset.AssetId)?.ApprovalState == AssetApprovalState.Approved, "approved persisted asset should survive TTL sweep");

    var expiringNpc = await npcVideo.CreateAsync(new NpcVideoMessageRequest(
        SessionId: "session_demo",
        SceneId: "scene_01",
        NpcId: "npc_burner",
        MessageText: "This line self-destructs in fourteen days.",
        Style: "grim_warning"));
    var completedExpiringNpcJob = await WaitForSucceededJobAsync(jobs, expiringNpc.VideoJobId);
    var expiringNpcCatalog = assets.Resolve(completedExpiringNpcJob.AssetId!);
    Assert(expiringNpcCatalog is not null, "expiring npc video should resolve before sweep");
    var resolvedExpiringNpcCatalog = NotNull(expiringNpcCatalog, "expiring npc video should resolve before sweep");
    assets.SweepExpired(resolvedExpiringNpcCatalog.CreatedAtUtc + TimeSpan.FromDays(14) + TimeSpan.FromMinutes(1));
    Assert(assets.Resolve(completedExpiringNpcJob.AssetId!) is null, "draft npc video should expire after TTL when left unapproved");
    var expiredNpc = npcVideo.Get(expiringNpc.MessageId);
    Assert(expiredNpc is not null, "npc orchestration record should remain queryable after TTL expiry");
    Assert(expiredNpc!.RetentionState == AssetRetentionState.Expired, "npc orchestration should project expired retention once TTL elapses");
    Assert(expiredNpc.PublishState == "draft-expired", "npc orchestration should surface draft expiry when unpublished assets lapse");

    var expiredNpcPublish = await npcVideo.PublishAsync(
        expiringNpc.MessageId,
        new NpcVideoMessagePublishRequest(
            SessionId: "session_demo",
            SceneId: "scene_01",
            SceneRevision: "rev_02",
            RequestedBy: "gm",
            Surfaces: new[] { "players" },
            Archive: false));
    Assert(expiredNpcPublish.Outcome == "expired", "expired npc video drafts should not publish");
    Assert(jobs.List().Count >= 8, "media job service should retain job status history for route preview/video and other creative artifact types");
}

async Task<MediaRenderJobStatus> WaitForSucceededJobAsync(IMediaRenderJobService jobs, string jobId)
{
    for (var attempt = 0; attempt < 40; attempt++)
    {
        var job = jobs.Get(jobId) ?? throw new InvalidOperationException($"job '{jobId}' was not found");
        if (job.State == MediaRenderJobState.Succeeded)
        {
            Assert(!string.IsNullOrWhiteSpace(job.AssetId), $"job '{jobId}' should publish an asset id on success");
            return job;
        }

        if (job.State == MediaRenderJobState.Failed)
        {
            throw new InvalidOperationException($"job '{jobId}' failed: {job.Error}");
        }

        await Task.Delay(25);
    }

    throw new TimeoutException($"job '{jobId}' did not finish in time");
}

async Task AssertThrowsInvalidOperationAsync(Func<Task> action, string message)
{
    try
    {
        await action();
    }
    catch (InvalidOperationException)
    {
        return;
    }

    throw new InvalidOperationException(message);
}

T NotNull<T>(T? value, string message)
    where T : class
{
    if (value is null)
    {
        throw new InvalidOperationException(message);
    }

    return value;
}

ControllerContext AuthenticatedControllerContext(string accessToken)
{
    var httpContext = new DefaultHttpContext();
    httpContext.Request.Headers.Authorization = $"Bearer {accessToken}";
    return new ControllerContext
    {
        HttpContext = httpContext
    };
}

ControllerContext ReceiptControllerContext(string signatureHeader, JsonElement _)
{
    var httpContext = new DefaultHttpContext();
    httpContext.Request.Headers["X-Fleet-Receipt-Signature"] = signatureHeader;
    return new ControllerContext
    {
        HttpContext = httpContext
    };
}

HttpResponseMessage JsonResponse<T>(T payload, HttpStatusCode statusCode = HttpStatusCode.OK)
{
    return new HttpResponseMessage(statusCode)
    {
        Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
    };
}

HubPageChromeService CreateChromeService(IConfiguration configuration, ILoggerFactory loggerFactory)
{
    var canon = new PublicCanonFileLoader(configuration);
    var routes = new PublicRouteCatalogService(canon);
    var actions = new PublicActionResolver();
    var landing = new PublicLandingService(canon, actions);
    var navigation = new PublicNavigationService(canon, routes);
    var releases = new PublicReleaseManifestService(configuration);
    var releaseSelection = new ReleaseSelectionService(canon);
    return new HubPageChromeService(landing, navigation, releases, releaseSelection, new HttpContextAccessor());
}

HubGoogleAuthService CreateGoogleService(
    IConfiguration configuration,
    HubBrowserAuthService browserAuth,
    IdentityLinkService identityLinks,
    AccountService accounts,
    ILoggerFactory loggerFactory,
    string keyRoot)
{
    return new HubGoogleAuthService(
        new HttpClient(new StubHttpMessageHandler(_ => JsonResponse(new { error = "not-configured" }, HttpStatusCode.BadRequest))),
        configuration,
        browserAuth,
        identityLinks,
        accounts,
        DataProtectionProvider.Create(keyRoot),
        loggerFactory.CreateLogger<HubGoogleAuthService>(),
        new SmokeWebHostEnvironment
        {
            EnvironmentName = "Development",
            ApplicationName = "RunServicesSmoke",
            ContentRootPath = keyRoot,
            WebRootPath = Path.Combine(keyRoot, "wwwroot")
        });
}

JsonElement BuildSignedReceiptElement(string secret, IReadOnlyDictionary<string, object?> payload)
{
    using var unsignedDocument = JsonDocument.Parse(JsonSerializer.Serialize(payload));
    var signature = FleetReceiptSigning.ComputeHmacSignature(unsignedDocument.RootElement, secret);
    var signedPayload = payload.ToDictionary(static pair => pair.Key, static pair => pair.Value, StringComparer.Ordinal);
    signedPayload["signed_by_fleet"] = signature;
    using var signedDocument = JsonDocument.Parse(JsonSerializer.Serialize(signedPayload));
    return signedDocument.RootElement.Clone();
}

void Assert(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}

sealed class StubHttpMessageHandler : HttpMessageHandler
{
    private readonly Func<HttpRequestMessage, HttpResponseMessage> _handler;

    public StubHttpMessageHandler(Func<HttpRequestMessage, HttpResponseMessage> handler)
    {
        _handler = handler;
    }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        => Task.FromResult(_handler(request));
}

sealed class StubHttpClientFactory : IHttpClientFactory
{
    private readonly HttpClient _client;

    public StubHttpClientFactory(HttpClient client)
    {
        _client = client;
    }

    public HttpClient CreateClient(string name) => _client;
}

sealed class StubReleaseChannelManifestStore : IReleaseChannelManifestStore
{
    public Chummer.Hub.Registry.Contracts.ReleaseChannelHeadProjection? LoadCurrent() => null;
}

sealed class SmokeMarkupGoAdapter : IProviderAdapter
{
    public AiProvider Provider => AiProvider.MarkupGo;

    public bool Enabled => true;

    public bool PrimaryForStructuredOutput => false;

    public Task<string> GenerateAsync(ProviderRouteRequest request, CancellationToken cancellationToken)
    {
        var prompt = JsonSerializer.Deserialize<SmokeMarkupGoPrompt>(request.Prompt, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        }) ?? throw new InvalidOperationException("Smoke MarkupGo prompt was missing.");
        var bytes = Encoding.UTF8.GetBytes(prompt.Html);
        return Task.FromResult(JsonSerializer.Serialize(new GatewayBinaryArtifact(
            ContentType: "application/pdf",
            FileName: prompt.FileName,
            Base64Payload: Convert.ToBase64String(bytes))));
    }
}

sealed record SmokeMarkupGoPrompt(
    string Html,
    string FileName);

sealed class SmokeWebHostEnvironment : IWebHostEnvironment
{
    public string ApplicationName { get; set; } = "RunServicesSmoke";
    public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
    public string WebRootPath { get; set; } = string.Empty;
    public string EnvironmentName { get; set; } = "Development";
    public string ContentRootPath { get; set; } = string.Empty;
    public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
}

sealed class NoopAntiforgery : IAntiforgery
{
    private static readonly AntiforgeryTokenSet TokenSet = new("request-token", "cookie-token", "__RequestVerificationToken", "X-CSRF-TOKEN");

    public AntiforgeryTokenSet GetAndStoreTokens(HttpContext httpContext) => TokenSet;
    public AntiforgeryTokenSet GetTokens(HttpContext httpContext) => TokenSet;
    public Task<bool> IsRequestValidAsync(HttpContext httpContext) => Task.FromResult(true);
    public Task ValidateRequestAsync(HttpContext httpContext) => Task.CompletedTask;
    public void SetCookieTokenAndHeader(HttpContext httpContext) { }
}
