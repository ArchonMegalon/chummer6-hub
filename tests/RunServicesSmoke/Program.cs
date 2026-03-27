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
            })
            .Build();

        using ILoggerFactory loggerFactory = LoggerFactory.Create(static builder => { });
        InstallLinkingStore installLinkingStore = new(configuration, loggerFactory.CreateLogger<InstallLinkingStore>());
        InstallLinkingService installLinking = new(installLinkingStore);
        SupportStore store = new(configuration, loggerFactory.CreateLogger<SupportStore>());
        SupportAttachmentStorageService supportAttachments = new(configuration);
        SupportCaseService supportCases = new(store, supportAttachments, loggerFactory.CreateLogger<SupportCaseService>());
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
        })
        .Build();
    using var loggerFactory = LoggerFactory.Create(static builder => builder.SetMinimumLevel(LogLevel.None));
    var store = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
    var installLinkingStore = new InstallLinkingStore(configuration, loggerFactory.CreateLogger<InstallLinkingStore>());
    var supportStore = new SupportStore(configuration, loggerFactory.CreateLogger<SupportStore>());
    var supportAttachments = new SupportAttachmentStorageService(configuration);
    var installLinking = new InstallLinkingService(installLinkingStore);
    var supportCases = new SupportCaseService(supportStore, supportAttachments, loggerFactory.CreateLogger<SupportCaseService>());
    var campaignSpine = new CampaignSpineService(store);
    var accounts = new AccountService(store);
    var groups = new GroupService(store, accounts);
    var rewards = new RewardService(store);
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
    var accountController = new AccountsController(accounts, identityClient, identityLinks, experience, installLinking, supportCases, campaignSpine, chrome, google, loggerFactory.CreateLogger<AccountsController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var forbiddenAccount = await accountController.GetMe("other.subject", CancellationToken.None);
    var forbiddenAccountProblem = forbiddenAccount.Result as ObjectResult;
    Assert(forbiddenAccountProblem?.StatusCode == StatusCodes.Status403Forbidden, "authenticated account endpoints should reject subject mismatch.");

    var currentAccount = await accountController.GetMe("subject.demo", CancellationToken.None);
    var currentAccountResult = currentAccount.Result as OkObjectResult;
    Assert(currentAccountResult?.Value is HubUserDto { UserId: not null }, "authenticated account endpoints should allow matching subjects.");

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
        memberJoinCodeBlocked = ex.Message.Contains("owner or manager", StringComparison.OrdinalIgnoreCase);
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
        memberBoostCodeBlocked = ex.Message.Contains("owner or manager", StringComparison.OrdinalIgnoreCase);
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
    Assert((missingJoinResult.Result as StatusCodeResult)?.StatusCode == StatusCodes.Status404NotFound, "joining with an unknown join code should return 404.");

    var missingBoostRedeemResult = await memberBoostCodesController.Redeem(new RedeemBoostCodeRequest("subject.member", "BOOST-MISSING"), CancellationToken.None);
    Assert((missingBoostRedeemResult.Result as StatusCodeResult)?.StatusCode == StatusCodes.Status404NotFound, "redeeming an unknown boost code should return 404.");

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
    var chrome = new HubPageChromeService(landing, navigation, releases, releaseSelection);
    var progress = new PublicProgressService(configuration, loggerFactory.CreateLogger<PublicProgressService>());
    var trustContent = new PublicTrustContentService(canon, routes);
    var installLinkingStore = new InstallLinkingStore(configuration, loggerFactory.CreateLogger<InstallLinkingStore>());
    var supportStore = new SupportStore(configuration, loggerFactory.CreateLogger<SupportStore>());
    var supportAttachments = new SupportAttachmentStorageService(configuration);
    var installLinking = new InstallLinkingService(installLinkingStore);
    var supportCases = new SupportCaseService(supportStore, supportAttachments, loggerFactory.CreateLogger<SupportCaseService>());
    var robotsPath = Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "wwwroot", "robots.txt");
    Assert(File.Exists(robotsPath), "public shell should ship a robots.txt file.");
    var robotsText = File.ReadAllText(robotsPath);
    Assert(robotsText.Contains("Disallow: /", StringComparison.Ordinal), "robots.txt should disallow crawler access.");
    Assert(robotsText.Contains("Noindex: /", StringComparison.Ordinal), "robots.txt should carry the explicit noindex directive requested for the public shell.");
    var layoutSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
    Assert(!layoutSource.Contains("site-nav-sheet", StringComparison.Ordinal), "layout should not render the old duplicate mobile nav sheet.");
    Assert(layoutSource.Contains("site-bottom-cta", StringComparison.Ordinal), "layout should keep a mobile-first sticky primary CTA for the public shell.");
    var authEntrySource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "Auth", "Entry.cshtml"));
    Assert(!authEntrySource.Contains("auth-panel__support", StringComparison.Ordinal), "auth entry should keep one quiet support row instead of duplicating support chrome inside the panel.");
    var landingSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));
    Assert(!landingSource.Contains("artifact-gallery", StringComparison.Ordinal), "landing should keep artifact depth off the main conversion spine.");
    Assert(landingSource.Contains("proofSectionAsset", StringComparison.Ordinal), "landing should use a separate lower proof asset instead of rendering the same proof screenshot twice.");
    Assert(landingSource.Contains("scene_dossier_desk", StringComparison.Ordinal), "landing should pair the hero proof teaser with a different lower proof asset.");
    Assert(landingSource.Contains("var proofNotes = Model.Workflows.Take(1).ToArray();", StringComparison.Ordinal), "landing should keep the proof band to one tighter workflow note instead of restating the whole product loop.");
    Assert(!landingSource.Contains("works-column__header", StringComparison.Ordinal), "landing should collapse the what-works-now strip instead of restating three full column headers.");
    var storySource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "ProductStory.cshtml"));
    Assert(!storySource.Contains("One path from install to session return", StringComparison.Ordinal), "product story should not drift back into a second install/support explainer.");
    Assert(!storySource.Contains("From first install to next session", StringComparison.Ordinal), "product story should stay focused on differentiation instead of retelling the install path.");
    Assert(!storySource.Contains("Start from the lane that matches your job", StringComparison.Ordinal), "product story should not fall back to a second lane selector once landing already owns that job.");
    var nowSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml"));
    Assert(nowSource.Contains("Supporting proof around the core loop", StringComparison.Ordinal), "now should keep supporting proof behind a calmer secondary disclosure.");
    Assert(!nowSource.Contains("Integrity stays visible. Use downloads when you are ready to install", StringComparison.Ordinal), "now should not end with a second generic CTA band after the signed-in return callout.");
    var homeSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml"));
    Assert(!homeSource.Contains("More in your signed-in shell", StringComparison.Ordinal), "home should not fall back to the old catch-all signed-in shell accordion.");
    Assert(!homeSource.Contains("Account state at a glance", StringComparison.Ordinal), "home should keep the overview route focused instead of adding a second top-level summary disclosure.");
    Assert(homeSource.Contains("Open what works today", StringComparison.Ordinal), "home access should point proof needs to the dedicated now route instead of repeating proof cards inline.");
    var accountSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "Accounts", "Account.cshtml"));
    Assert(!accountSource.Contains("Build Lab handoffs", StringComparison.Ordinal), "account copy should avoid internal Build Lab wording on the customer-facing surface.");
    Assert(!accountSource.Contains("Rules Navigator answers", StringComparison.Ordinal), "account copy should avoid internal Rules Navigator wording on the customer-facing surface.");
    Assert(accountSource.Contains("More settings", StringComparison.Ordinal), "account should keep non-core sections behind a calmer secondary settings disclosure.");
    Assert(accountSource.Contains("Advanced account details", StringComparison.Ordinal), "account should hide raw account identifiers behind an advanced disclosure.");
    Assert(accountSource.Contains("var sectionTitle = Model.CurrentSection switch", StringComparison.Ordinal), "account routes should expose route-specific headings instead of one generic account title.");
    var surface = landing.LoadSurface();
    Assert(string.Equals(surface.Surface, "chummer.run", StringComparison.Ordinal), "landing surface should target chummer.run");
    Assert(surface.PublicRoutes.Any(static route => string.Equals(route.Path, "/", StringComparison.Ordinal)), "landing surface should expose the root route");
    Assert(surface.PublicRoutes.Any(static route => string.Equals(route.Path, "/participate", StringComparison.Ordinal)), "landing surface should expose the participate entry route");
    Assert(surface.AuthRoutes.Any(static route => string.Equals(route.Path, "/login", StringComparison.Ordinal)), "landing surface should expose the login route");
    Assert(surface.AuthRoutes.Any(static route => string.Equals(route.Path, "/signup", StringComparison.Ordinal)), "landing surface should expose the signup route");
    Assert(surface.GuestShellActions.Any(static action => string.Equals(action.Href, "/login?next=/home", StringComparison.Ordinal) && string.Equals(action.Label, "Sign in", StringComparison.Ordinal)), "landing guest shell should expose the sign-in action");
    Assert(surface.GuestShellActions.Any(static action => string.Equals(action.Href, "/signup?next=/home", StringComparison.Ordinal) && string.Equals(action.Label, "Create account", StringComparison.Ordinal)), "landing guest shell should expose the create-account action");
    Assert(surface.HeroCtas.Any(static action => string.Equals(action.Emphasis, "primary", StringComparison.OrdinalIgnoreCase) && string.Equals(action.Label, "Create account to get preview", StringComparison.Ordinal)), "landing canon should single-source the guest hero access CTA.");
    Assert(surface.Assets.Any(static asset => string.Equals(asset.AssetSlot, "section_hero", StringComparison.Ordinal)), "landing surface should load the hero asset slot");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Title, "KARMA FORGE", StringComparison.Ordinal) && string.Equals(card.Badge, "Research", StringComparison.Ordinal)), "landing feature registry should carry the updated readiness posture for KARMA FORGE");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "real_public_guide", StringComparison.Ordinal) && string.Equals(card.Href, "/what-is-chummer#public-guide", StringComparison.Ordinal) && card.ExternalOk), "landing guide card should keep a first-party route with an explicit external fallback");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "artifact_runsite_pack", StringComparison.Ordinal) && string.Equals(card.Href, "/roadmap/runsite", StringComparison.Ordinal)), "artifact cards should point at related horizon details instead of self-linking to the shelf");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && string.Equals(card.GuestHref, "/login?next=/participate/codex", StringComparison.Ordinal) && string.Equals(card.RegisteredHref, "/participate/codex", StringComparison.Ordinal)), "booster participation should split guest and registered destinations");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_beta", StringComparison.Ordinal) && string.Equals(card.GuestHref, "/signup?next=/account/settings", StringComparison.Ordinal) && string.Equals(card.RegisteredHref, "/account/settings", StringComparison.Ordinal)), "beta waitlist should split guest signup from the calmer account-settings follow-up path");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && string.Equals(card.ActionLabel, "Open guided contribution", StringComparison.Ordinal)), "guided contribution should keep an explicit signed-in action label in canon.");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "participate_beta", StringComparison.Ordinal) && string.Equals(card.ActionLabel, "Join beta waitlist", StringComparison.Ordinal)), "beta waitlist should keep an explicit signed-in action label in canon.");
    Assert(surface.FeatureCards.Any(static card => string.Equals(card.Id, "horizon_local_co_processor", StringComparison.Ordinal) && string.Equals(card.ActionLabel, "Open the horizon page", StringComparison.Ordinal)), "local co-processor should route through its roadmap detail page instead of pretending the overview card is an install action.");
    var downloadsSource = File.ReadAllText(Path.Combine("/docker/chummercomplete/chummer.run-services", "Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml"));
    Assert(downloadsSource.Contains("Advanced download options", StringComparison.Ordinal), "downloads should group advanced distribution paths under one calmer disclosure.");
    Assert(!downloadsSource.Contains("What changed and what to expect", StringComparison.Ordinal), "downloads should not carry a second release explainer block under the primary install path.");
    Assert(downloadsSource.Contains("Release notes, known issues, and requirements", StringComparison.Ordinal), "downloads should tuck release education into one calmer drawer on the primary card.");
    Directory.CreateDirectory(Path.GetDirectoryName(storePath)!);
    var store = new CommunityStore(configuration, loggerFactory.CreateLogger<CommunityStore>());
    var campaignSpine = new CampaignSpineService(store);
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
    var controller = new PublicLandingController(landing, releases, releaseSelection, actions, accounts, identityClient, identityLinks, experience, installLinking, campaignSpine, chrome, trustContent, supportCases, loggerFactory.CreateLogger<PublicLandingController>())
    {
        ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        }
    };
    var authenticatedLandingController = new PublicLandingController(landing, releases, releaseSelection, actions, accounts, linkedIdentityClient, identityLinks, experience, installLinking, campaignSpine, chrome, trustContent, supportCases, loggerFactory.CreateLogger<PublicLandingController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var downloadsController = new DownloadsCompatibilityController(
        releases,
        releaseSelection,
        installLinking,
        linkedIdentityClient,
        loggerFactory.CreateLogger<DownloadsCompatibilityController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var installLinkingController = new InstallLinkingController(
        linkedIdentityClient,
        accounts,
        installLinking)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var supportCasesController = new SupportCasesController(
        linkedIdentityClient,
        accounts,
        supportCases,
        new SupportAssistantService(supportCases, canon, campaignSpine, loggerFactory.CreateLogger<SupportAssistantService>()),
        supportAttachments,
        configuration)
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var supportAutomationController = new SupportCasesController(
        linkedIdentityClient,
        accounts,
        supportCases,
        new SupportAssistantService(supportCases, canon, campaignSpine, loggerFactory.CreateLogger<SupportAssistantService>()),
        supportAttachments,
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
        campaignSpine,
        chrome,
        google,
        loggerFactory.CreateLogger<AccountsController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    var progressController = new PublicProgressController(
        progress,
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
    Assert(string.Equals(landingModel.PrimaryHeroAction.Label, "Create account to get preview", StringComparison.Ordinal), "landing page should source the guest-gated primary CTA from release canon.");
    Assert(landingModel.PrimaryHeroAction.Href.StartsWith("/signup?next=", StringComparison.Ordinal), "guest-gated primary CTA should route to signup through the install handoff.");
    Assert(string.Equals(landingModel.SecondaryHeroAction.Label, "See what works today", StringComparison.Ordinal), "landing page should keep the manifest-backed secondary CTA.");
    Assert(landingModel.Workflows.Any(static card => string.Equals(card.Action.Href, "/downloads", StringComparison.Ordinal)), "landing page should keep the product-story start lane");
    Assert(landingModel.Chrome.HeaderActions.Any(static action => string.Equals(action.Label, "Create account to get preview", StringComparison.Ordinal) && action.Href.StartsWith("/signup?next=", StringComparison.Ordinal)), "landing page chrome should expose the release-aware signup CTA beside sign in");
    Assert(landingModel.Lanes.Any(static card => string.Equals(card.Card.Title, "Creator", StringComparison.Ordinal)), "landing page should keep the creator lane in the public entry surface");
    Assert(!string.IsNullOrWhiteSpace(landingModel.Assets.BySlot("section_hero")?.PosterUrl), "landing hero should use a non-empty media asset.");

    var storyView = await controller.ProductStoryPage(CancellationToken.None) as ViewResult;
    var storyModel = storyView?.Model as StoryPageViewModel;
    Assert(storyModel is not null && storyModel.TrustPillars.Count == 3, "product story page should expose the three trust pillars.");
    var roadmapDetailView = await controller.RoadmapDetailPage("runsite", CancellationToken.None) as ViewResult;
    var roadmapDetailModel = roadmapDetailView?.Model as FeatureDetailPageViewModel;
    Assert(roadmapDetailModel is not null && !string.IsNullOrWhiteSpace(roadmapDetailModel.ProofNote), "roadmap detail pages should expose a verification note instead of a bare placeholder shell.");
    Assert(!string.Equals(roadmapDetailModel?.StatusEyebrow, "Current status", StringComparison.OrdinalIgnoreCase), "roadmap detail pages should project a roadmap-specific status frame.");
    Assert(roadmapDetailModel!.MicroProof.Count > 0, "roadmap detail pages should surface micro-proof markers.");
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
    var participateView = await controller.ParticipatePage(CancellationToken.None) as ViewResult;
    var participateModel = participateView?.Model as ParticipatePageViewModel;
    Assert(participateModel is not null, "participate page should render through the MVC view layer.");
    Assert(participateModel!.SignedInLane.Any(static card => string.Equals(card.Action.Label, "Open guided contribution", StringComparison.Ordinal)), "participate page should render an explicit guided-contribution label.");
    Assert(participateModel.SignedInLane.Any(static card => string.Equals(card.Action.Label, "Join beta waitlist", StringComparison.Ordinal)), "participate page should render an explicit beta-waitlist label.");
    var privacyPage = trustContent.BuildPrivacyPage(chrome.BuildPublicChrome("Privacy", "What Chummer stores, and what it does not.", "/privacy"));
    Assert(privacyPage.Actions.Any(static action => string.Equals(action.Label, "Create account", StringComparison.Ordinal) && action.Href.StartsWith("/signup?next=", StringComparison.Ordinal)), "privacy page should adapt account-only actions into signup-first actions for guests.");

    var downloadsView = await controller.DownloadsPage(CancellationToken.None) as ViewResult;
    var downloadsModel = downloadsView?.Model as DownloadsPageViewModel;
    Assert(downloadsModel is not null && downloadsModel.Manifest.Downloads.Any(static item => string.Equals(item.Id, "smoke-poc-linux-x64", StringComparison.Ordinal)), "downloads page should render artifacts from the live release manifest");
    Assert(downloadsModel!.Manifest.Downloads.All(static item => !string.Equals(item.Id, "smoke-poc-osx-arm64-installer", StringComparison.Ordinal)), "downloads page should filter withheld macOS artifacts from the public manifest.");
    Assert(string.Equals(downloadsModel?.Manifest.Version, "0.6.1-smoke", StringComparison.Ordinal), "downloads page should surface the manifest version");
    Assert(downloadsModel!.ReleaseExperience.InstallSteps.Any(static step => step.Contains("Create your Chummer account first.", StringComparison.OrdinalIgnoreCase)), "account-gated releases should keep account-required install steps for the current preview recommendation.");
    Assert(string.Equals(downloadsModel.ReleaseExperience.GuestGatePrimaryLabel, "Create account to get preview", StringComparison.Ordinal), "downloads page should keep the signup-first guest gate label.");
    Assert(string.Equals(downloadsModel.ReleaseExperience.KnownIssuesLabel, "Known issues and install help", StringComparison.Ordinal), "downloads page should keep a single known-issues/install-help label for the current preview.");
    controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)";
    var macDownloadsView = await controller.DownloadsPage(CancellationToken.None) as ViewResult;
    var macDownloadsModel = macDownloadsView?.Model as DownloadsPageViewModel;
    Assert(macDownloadsModel is not null, "downloads page should still render for a macOS user agent even when the platform is withheld.");
    Assert(string.Equals(macDownloadsModel!.ReleaseExperience.RequestedPlatformLabel, "macOS", StringComparison.Ordinal), "downloads page should detect the macOS user agent.");
    Assert(!string.IsNullOrWhiteSpace(macDownloadsModel.ReleaseExperience.PlatformShelfNoticeTitle), "downloads page should surface a shelf note when macOS is not publicly promoted.");
    Assert(macDownloadsModel.ReleaseExperience.PlatformShelfNoticeSummary?.Contains("does not publish a promoted macOS installer yet", StringComparison.OrdinalIgnoreCase) == true, "downloads page should explain that the macOS build lane is not yet on the public shelf.");
    var authenticatedDownloadResult = await downloadsController.DownloadArtifact("smoke-poc-linux-x64", CancellationToken.None);
    var authenticatedRedirect = authenticatedDownloadResult as RedirectResult;
    Assert(authenticatedRedirect is not null && string.Equals(authenticatedRedirect.Url, "/downloads/install/smoke-poc-linux-x64", StringComparison.Ordinal), "signed-in compatibility downloads should route through the install handoff.");
    var blockedMacFile = await downloadsController.DownloadFile("smoke-poc-osx-arm64-installer.dmg", CancellationToken.None);
    Assert(blockedMacFile is NotFoundResult, "direct file routes should not serve macOS artifacts that were withheld from the public shelf.");
    var dispatchView = await authenticatedLandingController.DownloadDispatchPage("smoke-poc-linux-x64", CancellationToken.None) as ViewResult;
    var dispatchModel = dispatchView?.Model as DownloadDispatchPageViewModel;
    Assert(dispatchModel is not null && string.Equals(dispatchModel.DownloadHref, "/downloads/file/smoke-poc-linux-x64", StringComparison.Ordinal), "signed-in download handoff should expose the canonical file route.");
    Assert(!string.IsNullOrWhiteSpace(dispatchModel?.ClaimCode), "signed-in download handoff should expose a claim code.");
    Assert(!string.IsNullOrWhiteSpace(dispatchModel?.Heading), "signed-in download handoff should expose a non-empty heading.");
    Assert(!string.IsNullOrWhiteSpace(dispatchModel?.Summary), "signed-in download handoff should expose a non-empty summary.");
    Assert(dispatchModel?.Steps.Count > 0, "signed-in download handoff should expose the signed-in install steps.");
    var publicContactPageMethod = typeof(PublicLandingController).GetMethods()
        .Single(static method =>
            string.Equals(method.Name, nameof(PublicLandingController.ContactPage), StringComparison.Ordinal)
            && method.GetCustomAttributes(typeof(HttpGetAttribute), inherit: true).Length > 0);
    Assert(publicContactPageMethod.GetParameters().Length == 1 && publicContactPageMethod.GetParameters()[0].ParameterType == typeof(CancellationToken), "public contact page should not accept a spoofable submitted query parameter.");
    var linkedUser = accounts.EnsureUser("subject.demo", "Runner Demo", "runner@example.invalid");
    var operatorGroup = groups.CreateGroup(new CreateGroupRequest(
        SubjectId: "subject.demo",
        Name: "Smoke Crew Ops",
        GroupType: "campaign",
        Visibility: "group",
        Capabilities: new[] { "can_manage_members", "can_issue_join_codes", "can_issue_boost_codes", "can_hold_shared_entitlements" }));
    var seededCampaign = groups.GetOrCreateCampaign(operatorGroup.GroupId, "hub", "Smoke Campaign");
    Assert(string.Equals(seededCampaign.GroupId, operatorGroup.GroupId, StringComparison.Ordinal), "smoke campaign should attach to the seeded operator group.");
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
    SupportCaseProjection supportCase = supportCases.Submit(
        linkedUser.UserId,
        "subject.demo",
        new SupportCaseSubmitRequest(
            Kind: supportPayload!.Kind,
            Title: supportPayload.Title,
            Summary: supportPayload.Summary,
            Detail: supportPayload.Detail,
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
    SupportAssistantService supportAssistant = new(supportCases, canon, campaignSpine, loggerFactory.CreateLogger<SupportAssistantService>());
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
    var notifiedResult = supportAutomationController.NotifyReporter(
        supportCase.CaseId,
        new SupportCaseNotificationRequest(
            Note: "Reporter notified that preview 0.6.3-smoke contains the fix.",
            Actor: "hub",
            Channel: "account_history"));
    var notifiedPayload = (notifiedResult.Result as OkObjectResult)?.Value as SupportCaseProjection;
    Assert(notifiedPayload is not null && string.Equals(notifiedPayload.Status, SupportCaseStatuses.UserNotified, StringComparison.Ordinal), "internal notify should close the user-facing loop.");

    var accountPage = await accountController.AccountPage(section: null, caseId: null, CancellationToken.None) as ViewResult;
    var accountModel = accountPage?.Model as AccountPageViewModel;
    Assert(accountModel is not null && accountModel.SupportCases.Any(item => string.Equals(item.CaseId, supportCase.CaseId, StringComparison.Ordinal)), "account page should surface support-case history beside installs and access.");
    Assert(string.Equals(accountModel!.CurrentSection, "profile", StringComparison.Ordinal), "default account route should land on the profile section.");
    Assert(accountModel.CoreSections.Any(static section => string.Equals(section.Href, "/account/access", StringComparison.Ordinal)), "account should expose the devices-and-access section link.");
    Assert(accountModel!.CampaignSpine.Dossiers.Count >= 1, "account page should surface the living dossier summary.");
    Assert(accountModel.CampaignSpine.Runs.Count >= 1, "account page should surface the current runboard summary.");
    Assert(accountModel.CampaignSpine.Workspaces.Count >= 1, "account page should surface a first-class campaign workspace.");
    Assert(accountModel.CampaignSpine.Workspaces[0].ReadinessCues.Count >= 1, "campaign workspace should surface readiness cues.");
    Assert(accountModel.CampaignSpine.Workspaces[0].RecapShelf.Count >= 1, "campaign workspace should surface recap or publication-safe continuity outputs.");
    Assert(accountModel.CampaignSpine.BuildLabHandoffs.Count >= 1, "account page should surface Build Lab handoffs into living dossier and campaign truth.");
    Assert(accountModel.CampaignSpine.RulesNavigator.Count >= 1, "account page should surface first-class rules navigator answers.");
    Assert(accountModel.CampaignSpine.MigrationReceipts.Count >= 1, "account page should surface legacy migration receipts.");
    Assert(accountModel.CampaignSpine.CreatorPublications.Count >= 1, "account page should surface creator publication posture.");
    Assert(accountModel.CampaignSpine.Restore.RecentRuleEnvironments.Count >= 1, "account page should surface restore-ready rule environments.");
    Assert(accountModel.CampaignSpine.Restore.RecentArtifacts.Count >= 1, "account page should surface reconnectable artifact truth.");
    Assert(accountModel.CampaignSpine.Restore.Entitlements.Count >= 1, "account page should surface active entitlements in the roaming restore packet.");
    Assert(accountModel.CampaignSpine.Restore.ClaimedDevices.Count >= 1, "account page should surface claimed devices for roaming restore.");
    Assert(accountModel.CampaignSpine.Restore.LocalOnlyNotes.Count >= 1, "account page should keep install-local restore guardrails explicit.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.OperatorRole)), "account page should surface organizer/operator role posture.");
    Assert(accountModel.CampaignSpine.CommunityOperations.Any(item => !string.IsNullOrWhiteSpace(item.CampaignVisibilitySummary)), "account page should surface explicit campaign visibility posture for operator groups.");
    var accountSupportPage = await accountController.AccountPage(section: "support", caseId: null, CancellationToken.None) as ViewResult;
    var accountSupportModel = accountSupportPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountSupportModel?.CurrentSection, "support", StringComparison.Ordinal), "account support route should render the support section.");
    Assert(string.Equals(accountSupportModel?.Chrome.Title, "Account · Support", StringComparison.Ordinal), "account support route should project its own chrome title.");
    var accountSupportDetailPage = await accountController.AccountPage(section: "support", caseId: supportCase.CaseId, CancellationToken.None) as ViewResult;
    var accountSupportDetailModel = accountSupportDetailPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountSupportDetailModel?.SelectedSupportCase?.CaseId, supportCase.CaseId, StringComparison.Ordinal), "account support detail route should load the selected tracked case.");
    var accountAccessPage = await accountController.AccountPage(section: "access", caseId: null, CancellationToken.None) as ViewResult;
    var accountAccessModel = accountAccessPage?.Model as AccountPageViewModel;
    Assert(string.Equals(accountAccessModel?.CurrentSection, "access", StringComparison.Ordinal), "account access route should render the devices-and-access section.");
    Assert(string.Equals(accountAccessModel?.Chrome.Title, "Account · Devices & access", StringComparison.Ordinal), "account access route should project its own chrome title.");

    var authenticatedHomePage = await authenticatedLandingController.HomePage(null, CancellationToken.None) as ViewResult;
    var authenticatedHomeModel = authenticatedHomePage?.Model as HomePageViewModel;
    Assert(authenticatedHomeModel is not null, "signed-in home page should render through the MVC view layer.");
    Assert(string.Equals(authenticatedHomeModel!.CurrentSection, "overview", StringComparison.Ordinal), "default home route should land on the overview section.");
    Assert(authenticatedHomeModel.Sections.Any(static section => string.Equals(section.Href, "/home/access", StringComparison.Ordinal)), "home should expose the dedicated access section link.");
    Assert(authenticatedHomeModel!.SupportCases.Any(item => string.Equals(item.CaseId, supportCase.CaseId, StringComparison.Ordinal)), "signed-in home should surface tracked support context.");
    Assert(authenticatedHomeModel.CampaignSpine.Dossiers.Count >= 1, "signed-in home should surface living dossier continuity.");
    Assert(authenticatedHomeModel.CampaignSpine.Runs.Count >= 1, "signed-in home should surface runboard continuity.");
    Assert(authenticatedHomeModel.CampaignSpine.Workspaces.Count >= 1, "signed-in home should keep the first-class campaign workspace attached to the signed-in shell.");
    Assert(authenticatedHomeModel.CampaignSpine.BuildLabHandoffs.Count >= 1, "signed-in home should surface Build Lab handoff continuity.");
    var contactSubmittedPage = await authenticatedLandingController.ContactSubmittedPage(supportCase.CaseId, CancellationToken.None) as ViewResult;
    var contactSubmittedModel = contactSubmittedPage?.Model as SupportSubmittedPageViewModel;
    Assert(contactSubmittedModel is not null && string.Equals(contactSubmittedModel.CaseId, supportCase.CaseId, StringComparison.Ordinal), "contact submitted route should render a stable support confirmation page.");
    Assert(contactSubmittedModel!.Attachments.Count == 1, "contact submitted route should surface saved support attachments for signed-in reporters.");
    Assert(authenticatedHomeModel.CampaignSpine.RulesNavigator.Count >= 1, "signed-in home should surface grounded rules navigator answers.");
    Assert(authenticatedHomeModel.CampaignSpine.CreatorPublications.Count >= 1, "signed-in home should surface creator publication posture.");
    Assert(authenticatedHomeModel.CampaignSpine.MigrationReceipts.Count >= 1, "signed-in home should surface migration receipt truth.");
    Assert(authenticatedHomeModel.InstallLinking.ClaimedInstallations?.Any(static item => string.Equals(item.Platform, "linux", StringComparison.OrdinalIgnoreCase)) == true, "signed-in home should surface claimed install posture.");
    var accessHomePage = await authenticatedLandingController.HomePage("access", CancellationToken.None) as ViewResult;
    var accessHomeModel = accessHomePage?.Model as HomePageViewModel;
    Assert(string.Equals(accessHomeModel?.CurrentSection, "access", StringComparison.Ordinal), "home access route should render the access section.");
    Assert(string.Equals(accessHomeModel?.Chrome.Title, "Home · Access", StringComparison.Ordinal), "home access route should project its own chrome title.");
    var workHomePage = await authenticatedLandingController.HomePage("work", CancellationToken.None) as ViewResult;
    var workHomeModel = workHomePage?.Model as HomePageViewModel;
    Assert(string.Equals(workHomeModel?.CurrentSection, "work", StringComparison.Ordinal), "home work route should render the work section.");
    Assert(string.Equals(workHomeModel?.Chrome.Title, "Home · Work", StringComparison.Ordinal), "home work route should project its own chrome title.");

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

    var artifactsView = await controller.ArtifactsPage(CancellationToken.None) as ViewResult;
    var artifactsModel = artifactsView?.Model as ShelfPageViewModel;
    Assert(
        artifactsModel is not null
        && artifactsModel.Items.Any(static card =>
            string.Equals(card.Card.Id, "artifact_runsite_pack", StringComparison.Ordinal)
            && !string.Equals(card.Action.Href, "/artifacts", StringComparison.Ordinal)),
        "artifacts shelf should point teaser cards at deliberate related detail pages");

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

    var unavailableIdentityClient = new HubIdentityClient(new HttpClient(new StubHttpMessageHandler(_ =>
        new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
        {
            Content = new StringContent("{\"detail\":\"identity-down-secret\"}", Encoding.UTF8, "application/json")
        })), configuration);
    var unavailableLandingController = new PublicLandingController(landing, releases, releaseSelection, actions, accounts, unavailableIdentityClient, identityLinks, experience, installLinking, campaignSpine, chrome, trustContent, supportCases, loggerFactory.CreateLogger<PublicLandingController>())
    {
        ControllerContext = AuthenticatedControllerContext("subject-token")
    };
    unavailableLandingController.ControllerContext.HttpContext.Request.Headers.Cookie = $"{HubBrowserAuthConstants.AccessTokenCookieName}=subject-token";
    var unavailableLandingView = await unavailableLandingController.LandingPage(CancellationToken.None) as ViewResult;
    var unavailableLandingModel = unavailableLandingView?.Model as LandingPageViewModel;
    Assert(unavailableLandingModel?.Chrome.Authenticated == true, "public landing chrome should stay authenticated when identity is temporarily unavailable but the browser session cookie still exists.");
    Assert(unavailableLandingModel!.Chrome.HeaderActions.Any(static action => string.Equals(action.Label, "Sign out", StringComparison.Ordinal)), "authenticated public landing chrome should keep the signed-in actions during identity outages.");
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

    var unavailableAccountController = new AccountsController(accounts, unavailableIdentityClient, identityLinks, experience, installLinking, supportCases, campaignSpine, chrome, google, loggerFactory.CreateLogger<AccountsController>())
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
    var controller = new HubRegistryController(registry)
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

    var projection = controller.GetProjection("session_ops_smoke", "scene_smoke", "scene_smoke:r2").Result as OkObjectResult;
    var projectionPayload = projection?.Value as OpsBoardProjection;
    Assert(projectionPayload?.RecentEvents.Count == 2, "ops-board projection should include recent session events");
    Assert(projectionPayload?.UnresolvedItems.Count == 2, "ops-board projection should surface unresolved and heat items");
    Assert(projectionPayload?.PrepAssets.Count == 2, "ops-board projection should include prep assets for the scene");

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

    var list = controller.ListPrepAssets(campaignId: "campaign_smoke", sessionId: "session_ops_smoke", sceneId: "scene_smoke", kind: null).Result as OkObjectResult;
    var listPayload = list?.Value as GmPrepAssetListResponse;
    Assert(listPayload?.TotalCount == 2, "ops-board list endpoint should filter scene prep assets");
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

    var exportResult = controller.Export(new InteropExportRequest(
        CampaignId: "campaign_interop_smoke",
        SessionId: "session_interop_smoke",
        RequestedBy: "gm.interop.smoke")).Result as OkObjectResult;
    var exported = exportResult?.Value as InteropExportPackage;
    Assert(exported is not null, "interop export endpoint should return an export package");
    Assert(exported!.ContractFamily == "interop_export_v1", "interop export should use the canonical family");
    Assert(exported.Manifest.CharacterCount >= 1, "interop export should include character assets");
    Assert(exported.Manifest.NpcCount >= 1, "interop export should include npc assets");
    Assert(exported.Manifest.SessionCount >= 1, "interop export should include session assets");
    Assert(exported.Manifest.EncounterCount >= 1, "interop export should include encounter assets");
    Assert(exported.Manifest.PrepCount >= 1, "interop export should include prep assets");
    Assert(exported.Manifest.TotalCount == exported.Assets.Count, "interop export manifest total should match exported assets");

    var importResult = controller.Import(new InteropImportRequest(exported, ImportedBy: "gm.interop.smoke")).Result as OkObjectResult;
    var imported = importResult?.Value as InteropImportResult;
    Assert(imported is not null, "interop import endpoint should return an import payload");
    Assert(imported!.ImportedCount == exported.Manifest.TotalCount, "interop import should accept untampered exports");
    Assert(imported.RejectedCount == 0, "interop import should not reject untampered exports");
    Assert(imported.ProvenanceRoundTrip, "interop import should preserve provenance round-trip");

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

    var snapshot = offlineSync.CreateSnapshot(new OfflineSyncSnapshotRequest(
        CampaignId: "campaign_demo",
        SessionId: "session_demo",
        SceneId: "scene_01",
        ExportedBy: "gm.demo",
        DeviceId: "tablet-smoke"));
    Assert(snapshot.ContractFamily == "offline_sync_snapshot_v1", "offline sync snapshot should use canonical family");
    Assert(snapshot.PrepAssets.Any(item => item.AssetId == prep.AssetId), "offline sync snapshot should include prep assets for collaboration surfaces");

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
    return new HubPageChromeService(landing, navigation, releases, releaseSelection);
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
