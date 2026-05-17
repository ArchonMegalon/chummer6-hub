using System.Text.Json;
using System.Net;
using System.Net.Http.Json;
using System.Text;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicSignalOperationsServiceTests
{
    [Fact]
    public void BuildPacketDefaultsToFirstPartyWhenHostedPromotionIsMissing()
    {
        using var fixture = new PublicSignalOperationsFixture();
        fixture.WriteSupportFiles();

        var packet = fixture.CreateService().BuildPacket();

        Assert.False(packet.HostedProjectionReady);
        Assert.Equal("No hosted public-board domain configured", packet.HostedDomainLabel);
        Assert.Equal("Webhook pending", packet.WebhookStatusLabel);
        Assert.Equal("Closeout mail canonized", packet.VoterCloseoutStatusLabel);
        Assert.Equal("Recipient projection pending", packet.RecipientProjectionStatusLabel);
        Assert.Equal("Consent basis pending", packet.ConsentStatusLabel);
        Assert.Equal("Queue blocked", packet.QueueStatusLabel);
        Assert.Equal("Governor approval pending", packet.GovernorStatusLabel);
        Assert.Equal("Release proof pending", packet.ReleaseProofStatusLabel);
        Assert.Equal(0, packet.ReceiptCount);
        Assert.Equal(0, packet.RoutingReceiptCount);
        Assert.Equal(0, packet.CloseoutDeliveryReceiptCount);
        Assert.Equal(0, packet.CloseoutQueueReceiptCount);
        Assert.Equal(0, packet.CloseoutQueueReadyCount);
        Assert.Equal(0, packet.CloseoutDispatchReceiptCount);
        Assert.Equal(0, packet.CloseoutDispatchSentCount);
        Assert.Equal(0, packet.JourneyReceiptCount);
        Assert.Equal(0, packet.DeliveryOutcomeReceiptCount);
        Assert.Equal(0, packet.AutomaticRetryPendingCount);
        Assert.Equal(0, packet.ReplayCandidateCount);
        Assert.Equal(0, packet.ReconcileRunCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Equal(0, packet.SuppressedDispatchCount);
        Assert.Equal(0, packet.DeliveryRecoveryRunCount);
        Assert.Equal(0, packet.RetryExpiryCandidateCount);
        Assert.Equal(0, packet.RetryExpiryRunCount);
        Assert.Equal(4, packet.CategoryCount);
        Assert.Equal(1, packet.MisrouteLikelyCount);
        Assert.Equal(1, packet.PrivacySensitiveCount);
        Assert.Contains(packet.HostedRoutes, route => string.Equals(route.StatusLabel, "First-party only", StringComparison.Ordinal));
        Assert.Contains(packet.Categories, item => string.Equals(item.Label, "Desktop / Install / Updates", StringComparison.Ordinal) && item.SupportMisrouteLikely);
        Assert.Contains(packet.Rules, item => item.Contains("misroutes", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void BuildPacketRecognizesConsistentHostedDomainSplitAndWebhookReadiness()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] = "https://ideas.chummer.run/feedback",
            ["CHUMMER_PRODUCTLIFT_ROADMAP_URL"] = "https://ideas.chummer.run/roadmap",
            ["CHUMMER_PRODUCTLIFT_CHANGELOG_URL"] = "https://ideas.chummer.run/changelog",
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret"
        });
        fixture.WriteSupportFiles();

        var packet = fixture.CreateService().BuildPacket();

        Assert.True(packet.HostedProjectionReady);
        Assert.Equal("ideas.chummer.run", packet.HostedDomainLabel);
        Assert.Equal("Webhook configured", packet.WebhookStatusLabel);
        Assert.Equal("Recipient projection pending", packet.RecipientProjectionStatusLabel);
        Assert.Contains("ready for a bounded domain split", packet.HostedProjectionSummary, StringComparison.OrdinalIgnoreCase);
        Assert.All(packet.HostedRoutes, route => Assert.Equal("Configured", route.StatusLabel));
    }

    [Fact]
    public void RecordWebhookMaterializesBoundedReceiptMetadataAndDeduplicatesRedelivery()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key"
        });
        fixture.WriteSupportFiles();
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_001",
              "type": "idea.status_changed",
              "created_at": "2026-05-06T10:15:00Z",
              "data": {
                "board": {
                  "name": "Desktop Preview"
                },
                "category": {
                  "slug": "desktop_and_install"
                },
                "item": {
                  "id": "idea_123",
                  "slug": "faster-install-recovery",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true,
                  "title": "Do not persist this raw title",
                  "description": "Do not persist this raw description either."
                }
              }
            }
            """).RootElement.Clone();

        PublicSignalWebhookAckResponse first = service.RecordWebhook(payload);
        PublicSignalWebhookAckResponse duplicate = service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();
        string artifactJson = service.LoadArtifactJson();

        Assert.False(first.Duplicate);
        Assert.Equal("recorded_closeout_candidate", first.Status);
        Assert.True(first.RoutingReceiptRecorded);
        Assert.True(first.CloseoutReceiptRecorded);
        Assert.True(duplicate.Duplicate);
        Assert.True(duplicate.RoutingReceiptRecorded);
        Assert.True(duplicate.CloseoutReceiptRecorded);
        Assert.Equal("Webhook live", packet.WebhookStatusLabel);
        Assert.Equal(1, packet.ReceiptCount);
        Assert.Equal(1, packet.CloseoutReceiptCount);
        Assert.Equal(1, packet.RoutingReceiptCount);
        Assert.Equal(0, packet.ModerationReceiptCount);
        Assert.Equal(1, packet.CloseoutDeliveryReceiptCount);
        Assert.Equal(0, packet.CloseoutDeliveryCandidateCount);
        Assert.Equal(1, packet.CloseoutQueueReceiptCount);
        Assert.Equal(0, packet.CloseoutQueueReadyCount);
        Assert.Equal(0, packet.CloseoutDispatchReceiptCount);
        Assert.Equal(0, packet.CloseoutDispatchSentCount);
        Assert.Equal(0, packet.JourneyReceiptCount);
        Assert.Equal(0, packet.DeliveryOutcomeReceiptCount);
        Assert.Equal(0, packet.AutomaticRetryPendingCount);
        Assert.Equal(0, packet.ReplayCandidateCount);
        Assert.Equal(0, packet.ReconcileRunCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Equal(0, packet.SuppressedDispatchCount);
        Assert.Equal(0, packet.DeliveryRecoveryRunCount);
        Assert.Equal(0, packet.RetryExpiryCandidateCount);
        Assert.Equal(0, packet.RetryExpiryRunCount);
        Assert.Single(packet.RecentReceipts);
        Assert.Single(packet.RecentRoutingReceipts);
        Assert.Single(packet.RecentCloseoutReceipts);
        Assert.Single(packet.RecentQueueReceipts);
        Assert.Empty(packet.RecentDispatchReceipts);
        Assert.Empty(packet.RecentJourneyReceipts);
        Assert.Empty(packet.RecentDeliveryOutcomes);
        Assert.Empty(packet.RecentRecipientThreads);
        Assert.Empty(packet.RecentReconcileRuns);
        Assert.Empty(packet.RecentRecoveryRuns);
        Assert.Empty(packet.RecentRetryExpiryRuns);
        Assert.Equal("Desktop Preview", packet.RecentReceipts[0].BoardLabel);
        Assert.Equal("Desktop And Install", packet.RecentReceipts[0].CategoryLabel);
        Assert.Equal("faster-install-recovery", packet.RecentReceipts[0].ItemReference);
        Assert.Equal("/help#install-update", packet.RecentRoutingReceipts[0].TargetPath);
        Assert.Equal("all", packet.RecentRoutingReceipts[0].SourceHotFilterKey);
        Assert.Equal("All threads", packet.RecentRoutingReceipts[0].SourceHotFilterLabel);
        Assert.Equal(0, packet.RecentRoutingReceipts[0].SourceHotFilterCount);
        Assert.Equal("Recipient projection pending", packet.RecentCloseoutReceipts[0].StatusLabel);
        Assert.Equal("deferred", packet.RecentCloseoutReceipts[0].DeliveryState);
        Assert.Equal("productlift_voter_shipped", packet.RecentCloseoutReceipts[0].TemplateId);
        Assert.Equal("hub_follow_horizons:verified_email", packet.RecentCloseoutReceipts[0].RecipientScopeRef);
        Assert.Equal(0, packet.RecentCloseoutReceipts[0].RecipientScopeCount);
        Assert.Equal("hub_preferences:follow_horizons", packet.RecentCloseoutReceipts[0].ConsentSourceRef);
        Assert.Contains("recipient projection", packet.RecentCloseoutReceipts[0].DeliveryReason, StringComparison.OrdinalIgnoreCase);
        Assert.False(packet.RecentCloseoutReceipts[0].PublicClaimAllowed);
        Assert.Equal("all", packet.RecentCloseoutReceipts[0].SourceHotFilterKey);
        Assert.Equal("All threads", packet.RecentCloseoutReceipts[0].SourceHotFilterLabel);
        Assert.Equal(0, packet.RecentCloseoutReceipts[0].SourceHotFilterCount);
        Assert.Equal("Recipient projection pending", packet.RecentQueueReceipts[0].StatusLabel);
        Assert.Equal("blocked", packet.RecentQueueReceipts[0].QueueState);
        Assert.Equal("connector.dispatch", packet.RecentQueueReceipts[0].DispatchTool);
        Assert.Equal("delivery.send", packet.RecentQueueReceipts[0].DispatchAction);
        Assert.Equal("voter_notified", packet.RecentQueueReceipts[0].JourneyEventKey);
        Assert.Equal("/changelog", packet.RecentQueueReceipts[0].ReleaseProofRoute);
        Assert.Contains("recipient projection", packet.RecentQueueReceipts[0].QueueReason, StringComparison.OrdinalIgnoreCase);
        Assert.False(packet.RecentQueueReceipts[0].PublicClaimAllowed);
        Assert.Equal("all", packet.RecentQueueReceipts[0].SourceHotFilterKey);
        Assert.Equal("All threads", packet.RecentQueueReceipts[0].SourceHotFilterLabel);
        Assert.Equal(0, packet.RecentQueueReceipts[0].SourceHotFilterCount);
        Assert.Equal("Recipient projection pending", packet.RecipientProjectionStatusLabel);
        Assert.Equal(0, packet.ProjectedRecipientCount);
        Assert.Equal("Queue blocked", packet.QueueStatusLabel);
        Assert.Equal("Governor approval pending", packet.GovernorStatusLabel);
        Assert.Equal("Release proof pending", packet.ReleaseProofStatusLabel);
        string compactArtifactJson = artifactJson.Replace(" ", string.Empty);
        Assert.Contains("\"contractName\"", artifactJson, StringComparison.Ordinal);
        Assert.Contains("\"generatedAtUtc\"", artifactJson, StringComparison.Ordinal);
        Assert.Contains("\"counts\"", artifactJson, StringComparison.Ordinal);
        Assert.Contains("\"categoryCount\":4", compactArtifactJson, StringComparison.Ordinal);
        Assert.Contains("\"receiptCount\":1", compactArtifactJson, StringComparison.Ordinal);
        Assert.Contains("\"routingReceiptCount\":1", compactArtifactJson, StringComparison.Ordinal);
        Assert.Contains("\"closeoutReceiptCount\":1", compactArtifactJson, StringComparison.Ordinal);
        Assert.Contains("\"recipientProjectionStatusLabel\"", artifactJson, StringComparison.Ordinal);
        Assert.Contains("\"queueStatusLabel\"", artifactJson, StringComparison.Ordinal);
        Assert.Contains("\"releaseProofStatusLabel\"", artifactJson, StringComparison.Ordinal);
        Assert.DoesNotContain("Do not persist this raw title", artifactJson, StringComparison.Ordinal);
        Assert.DoesNotContain("Do not persist this raw description either.", artifactJson, StringComparison.Ordinal);
    }

    [Fact]
    public void PrivacySensitiveWebhookBuildsModerationRoutingReceiptWithoutCloseoutFollowUp()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret"
        });
        fixture.WriteSupportFiles();
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_002",
              "type": "comment.created",
              "data": {
                "board": {
                  "name": "Table Pulse"
                },
                "category": {
                  "slug": "table_pulse"
                },
                "item": {
                  "slug": "post-session-debrief"
                }
              }
            }
            """).RootElement.Clone();

        PublicSignalWebhookAckResponse ack = service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.True(ack.RoutingReceiptRecorded);
        Assert.False(ack.CloseoutReceiptRecorded);
        Assert.Equal(1, packet.RoutingReceiptCount);
        Assert.Equal(1, packet.ModerationReceiptCount);
        Assert.Equal(0, packet.CloseoutDeliveryReceiptCount);
        Assert.Single(packet.RecentRoutingReceipts);
        Assert.Equal("Moderation review required", packet.RecentRoutingReceipts[0].StatusLabel);
        Assert.Equal("/contact#support-intake", packet.RecentRoutingReceipts[0].TargetPath);
    }

    [Fact]
    public void FullCloseoutRuntimeReadinessTurnsShippedWebhookIntoDeliveryCandidate()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_004",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "phone-dash",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();
        string artifactJson = service.LoadArtifactJson();

        Assert.Equal("Recipient projection configured", packet.RecipientProjectionStatusLabel);
        Assert.Equal("Consent basis configured", packet.ConsentStatusLabel);
        Assert.Equal("Queue adapter configured", packet.QueueStatusLabel);
        Assert.Equal("Governor approval configured", packet.GovernorStatusLabel);
        Assert.Equal("Release proof current", packet.ReleaseProofStatusLabel);
        Assert.Equal(1, packet.ProjectedRecipientCount);
        Assert.Equal(1, packet.CloseoutDeliveryCandidateCount);
        Assert.Equal(1, packet.CloseoutQueueReceiptCount);
        Assert.Equal(1, packet.CloseoutQueueReadyCount);
        Assert.Equal(1, packet.CloseoutDispatchReceiptCount);
        Assert.Equal(1, packet.CloseoutDispatchSentCount);
        Assert.Equal(1, packet.JourneyReceiptCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Equal(0, packet.SuppressedDispatchCount);
        Assert.Equal(0, packet.DeliveryRecoveryRunCount);
        Assert.Single(packet.RecentCloseoutReceipts);
        Assert.Single(packet.RecentQueueReceipts);
        Assert.Single(packet.RecentDispatchReceipts);
        Assert.Single(packet.RecentJourneyReceipts);
        Assert.Equal("Delivery candidate", packet.RecentCloseoutReceipts[0].StatusLabel);
        Assert.Equal("deferred", packet.RecentCloseoutReceipts[0].DeliveryState);
        Assert.Equal("hub_follow_horizons:verified_email", packet.RecentCloseoutReceipts[0].RecipientScopeRef);
        Assert.Equal(1, packet.RecentCloseoutReceipts[0].RecipientScopeCount);
        Assert.Equal("hub_preferences:follow_horizons", packet.RecentCloseoutReceipts[0].ConsentSourceRef);
        Assert.Contains("governor closeout", packet.RecentCloseoutReceipts[0].DeliveryReason, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("Outbox candidate ready", packet.RecentQueueReceipts[0].StatusLabel);
        Assert.Equal("ready", packet.RecentQueueReceipts[0].QueueState);
        Assert.Equal("gov-2026-05-06-productlift-closeout", packet.RecentQueueReceipts[0].GovernorDecisionRef);
        Assert.Equal("/changelog", packet.RecentQueueReceipts[0].ReleaseProofRoute);
        Assert.NotNull(packet.RecentQueueReceipts[0].ReleaseProofReceiptId);
        Assert.True(packet.RecentQueueReceipts[0].ReadyForOutbox);
        Assert.Contains("governor decision", packet.RecentQueueReceipts[0].Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("without claiming the mail already sent", packet.RecentQueueReceipts[0].QueueReason, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("Sent", packet.RecentDispatchReceipts[0].StatusLabel);
        Assert.Equal("sent", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("delivery-1", packet.RecentDispatchReceipts[0].DeliveryId);
        Assert.Equal("emailit-1", packet.RecentDispatchReceipts[0].ProviderMessageId);
        Assert.StartsWith("usr-", packet.RecentDispatchReceipts[0].RecipientRef, StringComparison.Ordinal);
        Assert.Equal("productlift_voter_shipped", packet.RecentDispatchReceipts[0].TemplateId);
        Assert.False(packet.RecentDispatchReceipts[0].PublicClaimAllowed);
        Assert.Equal("voter_notified", packet.RecentJourneyReceipts[0].EventKey);
        Assert.Equal("Recorded", packet.RecentJourneyReceipts[0].StatusLabel);
        Assert.Equal("gov-2026-05-06-productlift-closeout", packet.RecentJourneyReceipts[0].GovernorDecisionRef);
        Assert.Equal("proof_001", packet.RecentJourneyReceipts[0].ReleaseProofReceiptId);
        Assert.Equal(1, packet.RecentJourneyReceipts[0].RecipientCount);
        Assert.Equal(1, packet.RecentJourneyReceipts[0].SentCount);
        Assert.False(packet.RecentJourneyReceipts[0].PublicClaimAllowed);

        Assert.Equal(3, fixture.Requests.Count);
        Assert.Contains(fixture.Requests, request => string.Equals(request.Url, "https://ea.test/v1/tools/execute", StringComparison.Ordinal));
        Assert.Contains(fixture.Requests, request => string.Equals(request.Url, "https://emailit.test/emails", StringComparison.Ordinal));
        Assert.Contains(fixture.Requests, request => string.Equals(request.Url, "https://ea.test/v1/delivery/outbox/delivery-1/sent", StringComparison.Ordinal));
    }

    [Fact]
    public void SourceLinkedAggregateCardsBiasToTheHottestSourcePivot()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_004b",
              "type": "idea.status_changed",
              "data": {
                "board": {
                  "name": "Desktop Preview"
                },
                "category": {
                  "slug": "desktop_and_install"
                },
                "item": {
                  "slug": "desktop-proof-handoff",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "type": "email.delivered",
              "data": {
                "id": "emailit-pivot-sent",
                "delivery_id": "delivery-1",
                "to": "runner@example.com",
                "created_at": "2026-05-06T13:25:00Z"
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(payload);
        service.RecordDeliveryOutcome("emailit", callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();
        string artifactJson = service.LoadArtifactJson();

        Assert.Single(packet.RecentRoutingReceipts);
        Assert.Single(packet.RecentCloseoutReceipts);
        Assert.Single(packet.RecentQueueReceipts);
        Assert.Single(packet.RecentJourneyReceipts);

        Assert.Equal("sent", packet.RecentRoutingReceipts[0].SourceHotFilterKey);
        Assert.Equal("Sent threads", packet.RecentRoutingReceipts[0].SourceHotFilterLabel);
        Assert.Equal(1, packet.RecentRoutingReceipts[0].SourceHotFilterCount);

        Assert.Equal("sent", packet.RecentCloseoutReceipts[0].SourceHotFilterKey);
        Assert.Equal("Sent threads", packet.RecentCloseoutReceipts[0].SourceHotFilterLabel);
        Assert.Equal(1, packet.RecentCloseoutReceipts[0].SourceHotFilterCount);

        Assert.Equal("sent", packet.RecentQueueReceipts[0].SourceHotFilterKey);
        Assert.Equal("Sent threads", packet.RecentQueueReceipts[0].SourceHotFilterLabel);
        Assert.Equal(1, packet.RecentQueueReceipts[0].SourceHotFilterCount);

        Assert.Equal("sent", packet.RecentJourneyReceipts[0].SourceHotFilterKey);
        Assert.Equal("Sent threads", packet.RecentJourneyReceipts[0].SourceHotFilterLabel);
        Assert.Equal(1, packet.RecentJourneyReceipts[0].SourceHotFilterCount);
        Assert.Contains("\"counts\"", artifactJson, StringComparison.Ordinal);
        Assert.Contains("\"journeyReceiptCount\":1", artifactJson.Replace(" ", string.Empty), StringComparison.Ordinal);
    }

    [Fact]
    public void ReconcilePendingCloseoutsBackfillsPreviouslyBlockedReadyAudienceAfterGovernorAndProofArrive()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.SeedVerifiedFollowRecipient();
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_006",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "late-governor-proof",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel blockedPacket = service.BuildPacket();

        Assert.Equal("Governor approval pending", blockedPacket.GovernorStatusLabel);
        Assert.Equal("Release proof pending", blockedPacket.ReleaseProofStatusLabel);
        Assert.Equal(0, blockedPacket.CloseoutDispatchReceiptCount);
        Assert.Equal(0, blockedPacket.JourneyReceiptCount);
        Assert.Equal(0, blockedPacket.ReplayCandidateCount);
        Assert.Equal(0, blockedPacket.DeliveryRecoveryCandidateCount);

        fixture.SetSetting("CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED", "true");
        fixture.SetSetting("CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF", "gov-2026-05-06-reconcile");
        fixture.WriteReleaseProofFile("/changelog");

        PublicSignalOperationsReconcileResponse replay = service.ReconcilePendingCloseouts();
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();
        PublicSignalOperationsReconcileResponse secondReplay = service.ReconcilePendingCloseouts();

        Assert.Equal("replayed", replay.Status);
        Assert.Equal(1, replay.CandidateReceiptCount);
        Assert.Equal(1, replay.ReadyCandidateCount);
        Assert.Equal(1, replay.ReplayCandidateCount);
        Assert.Equal(1, replay.DispatchReceiptsCreated);
        Assert.Equal(1, replay.JourneyReceiptsRecorded);
        Assert.Equal(1, packet.CloseoutDispatchReceiptCount);
        Assert.Equal(1, packet.CloseoutDispatchSentCount);
        Assert.Equal(1, packet.JourneyReceiptCount);
        Assert.Equal(0, packet.ReplayCandidateCount);
        Assert.Equal(1, packet.ReconcileRunCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Equal(0, packet.DeliveryRecoveryRunCount);
        Assert.Single(packet.RecentReconcileRuns);
        Assert.Equal("replayed", packet.RecentReconcileRuns[0].Status);
        Assert.Equal(1, packet.RecentReconcileRuns[0].ReplayCandidateCount);
        Assert.Equal(1, packet.RecentReconcileRuns[0].DispatchReceiptsCreated);
        Assert.Equal(1, packet.RecentReconcileRuns[0].JourneyReceiptsRecorded);
        Assert.Equal("noop", secondReplay.Status);
        Assert.Equal(0, secondReplay.ReplayCandidateCount);
        Assert.Equal(3, fixture.Requests.Count);
        Assert.Contains(fixture.Requests, request => string.Equals(request.Url, "https://ea.test/v1/tools/execute", StringComparison.Ordinal));
        Assert.Contains(fixture.Requests, request => string.Equals(request.Url, "https://emailit.test/emails", StringComparison.Ordinal));
        Assert.Contains(fixture.Requests, request => string.Equals(request.Url, "https://ea.test/v1/delivery/outbox/delivery-1/sent", StringComparison.Ordinal));
    }

    [Fact]
    public void CurrentProofWithoutGovernorKeepsOutboxCandidateBlocked()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_005",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "build_and_explain"
                },
                "item": {
                  "slug": "bounded-closeout",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.Equal("Governor approval pending", packet.GovernorStatusLabel);
        Assert.Equal("Release proof current", packet.ReleaseProofStatusLabel);
        Assert.Single(packet.RecentQueueReceipts);
        Assert.Equal("Governor approval pending", packet.RecentQueueReceipts[0].StatusLabel);
        Assert.Equal("blocked", packet.RecentQueueReceipts[0].QueueState);
        Assert.Contains("governor", packet.RecentQueueReceipts[0].QueueReason, StringComparison.OrdinalIgnoreCase);
        Assert.False(packet.RecentQueueReceipts[0].ReadyForOutbox);
        Assert.Equal(0, packet.CloseoutDispatchReceiptCount);
        Assert.Equal(0, packet.JourneyReceiptCount);
        Assert.Empty(packet.RecentDispatchReceipts);
        Assert.Empty(packet.RecentJourneyReceipts);
        Assert.Empty(fixture.Requests);
    }

    [Fact]
    public void AcceptedDispatchReceiptCanBeRecoveredIntoSentState()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { status = "ok" }));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_007",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "accepted-before-recovery",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel blockedPacket = service.BuildPacket();

        Assert.Equal(1, blockedPacket.DeliveryRecoveryCandidateCount);
        Assert.Equal("accepted", blockedPacket.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("Provider accepted", blockedPacket.RecentDispatchReceipts[0].StatusLabel);
        Assert.Equal(0, blockedPacket.JourneyReceiptCount);

        PublicSignalOperationsRecoveryResponse recovery = service.RecoverDispatchOutcomes();
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.Equal("recovered", recovery.Status);
        Assert.Equal(1, recovery.CandidateReceiptCount);
        Assert.Equal(1, recovery.RecoveredReceiptCount);
        Assert.Equal(0, recovery.SuppressedReceiptCount);
        Assert.Equal(0, recovery.BlockedReceiptCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Equal(1, packet.DeliveryRecoveryRunCount);
        Assert.Single(packet.RecentRecoveryRuns);
        Assert.Equal("recovered", packet.RecentRecoveryRuns[0].Status);
        Assert.Equal("sent", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("Sent after recovery", packet.RecentDispatchReceipts[0].StatusLabel);
        Assert.Equal(1, packet.RecentDispatchReceipts[0].RecoveryAttemptCount);
        Assert.Equal("sent_mark_recovered", packet.RecentDispatchReceipts[0].LastRecoveryStatus);
        Assert.Equal(1, packet.JourneyReceiptCount);
        Assert.Equal(4, fixture.Requests.Count);
        Assert.Contains(fixture.Requests, request => string.Equals(request.Url, "https://ea.test/v1/delivery/outbox/delivery-1/sent", StringComparison.Ordinal));
    }

    [Fact]
    public void ProviderSentCallbackFinalizesAcceptedDispatchWithoutManualRecovery()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_009",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "provider-finished-send",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "provider": "emailit",
              "event_id": "outcome_001",
              "data": {
                "item": {
                  "delivery_id": "delivery-1",
                  "provider_message_id": "emailit-1",
                  "state": "delivered",
                  "occurred_at": "2026-05-06T12:00:00Z"
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(sourcePayload);
        PublicSignalOperationsPacketViewModel blockedPacket = service.BuildPacket();
        PublicSignalDeliveryOutcomeAckResponse ack = service.RecordDeliveryOutcome(callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.False(ack.Duplicate);
        Assert.Equal("recorded", ack.Status);
        Assert.Equal(1, blockedPacket.DeliveryRecoveryCandidateCount);
        Assert.Equal("accepted", blockedPacket.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal(1, packet.DeliveryOutcomeReceiptCount);
        Assert.Equal(0, packet.AutomaticRetryPendingCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Equal(1, packet.JourneyReceiptCount);
        Assert.Single(packet.RecentDeliveryOutcomes);
        Assert.Equal("Provider confirmed sent", packet.RecentDeliveryOutcomes[0].StatusLabel);
        Assert.Equal("sent", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("Provider confirmed sent", packet.RecentDispatchReceipts[0].StatusLabel);
        Assert.Equal("Delivered", packet.RecentDispatchReceipts[0].LastProviderState);
        Assert.Null(packet.RecentDispatchReceipts[0].NextAutomaticRetryAtUtc);
        Assert.NotNull(packet.RecentDispatchReceipts[0].LastOutcomeAtUtc);
        Assert.Equal(1, fixture.Requests.Count(request => string.Equals(request.Url, "https://ea.test/v1/delivery/outbox/delivery-1/sent", StringComparison.Ordinal)));
    }

    [Fact]
    public void ProviderRetryCallbackHoldsDispatchOutOfManualRecoveryUntilRetryWindowCloses()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_010",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "provider-retry-window",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "provider": "emailit",
              "event_id": "outcome_002",
              "data": {
                "item": {
                  "delivery_id": "delivery-1",
                  "provider_message_id": "emailit-1",
                  "state": "retrying",
                  "reason": "provider throttle window",
                  "retry_in_seconds": 900,
                  "occurred_at": "2026-05-06T12:30:00Z"
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(sourcePayload);
        PublicSignalDeliveryOutcomeAckResponse ack = service.RecordDeliveryOutcome(callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.False(ack.Duplicate);
        Assert.Equal("recorded", ack.Status);
        Assert.Equal(1, packet.DeliveryOutcomeReceiptCount);
        Assert.Equal(1, packet.AutomaticRetryPendingCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Equal(0, packet.JourneyReceiptCount);
        Assert.Single(packet.RecentDeliveryOutcomes);
        Assert.Equal("Provider retry scheduled", packet.RecentDeliveryOutcomes[0].StatusLabel);
        Assert.NotNull(packet.RecentDeliveryOutcomes[0].RetryAtUtc);
        Assert.Equal("retrying", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("Provider retry scheduled", packet.RecentDispatchReceipts[0].StatusLabel);
        Assert.Equal("Retrying", packet.RecentDispatchReceipts[0].LastProviderState);
        Assert.NotNull(packet.RecentDispatchReceipts[0].NextAutomaticRetryAtUtc);
        Assert.NotNull(packet.RecentDispatchReceipts[0].LastOutcomeAtUtc);
    }

    [Fact]
    public void LateEmailitMessageIdentityCanReconcileBySourceReceiptAndDedupLaterEaDeliveryCallback()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"] = "emailit-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_EA_DELIVERY_WEBHOOK_SECRET"] = "ea-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/emails",
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_014",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "late-emailit-id",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        PublicSignalWebhookAckResponse sourceAck = service.RecordWebhook(sourcePayload);
        PublicSignalOperationsPacketViewModel blockedPacket = service.BuildPacket();
        JsonElement emailitPayload = JsonDocument.Parse(
            $$"""
            {
              "type": "email.delivered",
              "data": {
                "id": "emailit-late-1",
                "to": "runner@example.invalid",
                "meta": {
                  "source_receipt_id": "{{sourceAck.ReceiptId}}"
                },
                "created_at": "2026-05-06T13:05:00Z"
              }
            }
            """).RootElement.Clone();
        JsonElement eaPayload = JsonDocument.Parse(
            """
            {
              "event_type": "delivery.sent",
              "data": {
                "delivery_id": "delivery-1",
                "occurred_at": "2026-05-06T13:05:30Z"
              }
            }
            """).RootElement.Clone();

        PublicSignalDeliveryOutcomeAckResponse emailitAck = service.RecordDeliveryOutcome("emailit", emailitPayload);
        PublicSignalDeliveryOutcomeAckResponse eaAck = service.RecordDeliveryOutcome("ea", eaPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.Equal("accepted", blockedPacket.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("delivery-1", blockedPacket.RecentDispatchReceipts[0].ProviderMessageId);
        Assert.False(emailitAck.Duplicate);
        Assert.True(eaAck.Duplicate);
        Assert.Equal(1, packet.DeliveryOutcomeReceiptCount);
        Assert.Equal(1, packet.JourneyReceiptCount);
        Assert.Single(packet.RecentDeliveryOutcomes);
        Assert.Equal("Emailit", packet.RecentDeliveryOutcomes[0].Provider);
        Assert.Equal("Delivered", packet.RecentDeliveryOutcomes[0].ProviderState);
        Assert.Equal(packet.RecentDispatchReceipts[0].RecipientRef, packet.RecentDeliveryOutcomes[0].RecipientRef);
        Assert.Equal(packet.RecentDispatchReceipts[0].AddressHash, packet.RecentDeliveryOutcomes[0].AddressHash);
        Assert.Equal("source_receipt_unique_dispatch", packet.RecentDeliveryOutcomes[0].IdentityMatchMode);
        Assert.Equal("sent", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("emailit-late-1", packet.RecentDispatchReceipts[0].ProviderMessageId);
        Assert.Equal("Delivered", packet.RecentDispatchReceipts[0].LastProviderState);
        Assert.Equal(1, fixture.Requests.Count(request => string.Equals(request.Url, "https://ea.test/v1/delivery/outbox/delivery-1/sent", StringComparison.Ordinal)));
    }

    [Fact]
    public void RecipientThreadJoinsQueueDispatchOutcomeAndJourneyForSameRecipient()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"] = "emailit-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_EA_DELIVERY_WEBHOOK_SECRET"] = "ea-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/emails",
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_017",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "recipient-thread-proof",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "type": "email.delivered",
              "data": {
                "id": "emailit-thread-1",
                "delivery_id": "delivery-1",
                "to": "runner@example.com",
                "created_at": "2026-05-06T13:20:00Z"
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(sourcePayload);
        service.RecordDeliveryOutcome("emailit", callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();
        PublicSignalOperationsDetailViewModel? sourceDetail = service.BuildSourceReceiptDetail(packet.RecentDispatchReceipts[0].SourceReceiptId);
        PublicSignalOperationsDetailViewModel? threadDetail = service.BuildRecipientThreadDetail(packet.RecentDispatchReceipts[0].ReceiptId);
        PublicSignalOperationsDetailViewModel? filteredThreadDetail = service.BuildRecipientThreadDetail(packet.RecentDispatchReceipts[0].ReceiptId, "sent");
        string? sourceDetailJson = service.LoadSourceReceiptDetailJson(packet.RecentDispatchReceipts[0].SourceReceiptId);
        string? threadDetailJson = service.LoadRecipientThreadDetailJson(packet.RecentDispatchReceipts[0].ReceiptId);

        Assert.Single(packet.RecentRecipientThreads);
        Assert.Equal(packet.RecentDispatchReceipts[0].RecipientRef, packet.RecentRecipientThreads[0].RecipientRef);
        Assert.Equal(packet.RecentDispatchReceipts[0].AddressHash, packet.RecentRecipientThreads[0].AddressHash);
        Assert.Equal(packet.RecentQueueReceipts[0].ReceiptId, packet.RecentRecipientThreads[0].QueueReceiptId);
        Assert.Equal(packet.RecentQueueReceipts[0].StatusLabel, packet.RecentRecipientThreads[0].QueueStatusLabel);
        Assert.Equal(packet.RecentDispatchReceipts[0].ReceiptId, packet.RecentRecipientThreads[0].DispatchReceiptId);
        Assert.Equal(packet.RecentDispatchReceipts[0].StatusLabel, packet.RecentRecipientThreads[0].DispatchStatusLabel);
        Assert.Equal(packet.RecentDeliveryOutcomes[0].ReceiptId, packet.RecentRecipientThreads[0].OutcomeReceiptId);
        Assert.Equal(packet.RecentDeliveryOutcomes[0].IdentityMatchMode, packet.RecentRecipientThreads[0].OutcomeIdentityMatchMode);
        Assert.Equal(packet.RecentJourneyReceipts[0].ReceiptId, packet.RecentRecipientThreads[0].JourneyReceiptId);
        Assert.Equal(packet.RecentJourneyReceipts[0].EventKey, packet.RecentRecipientThreads[0].JourneyEventKey);
        Assert.Equal(packet.RecentJourneyReceipts[0].StatusLabel, packet.RecentRecipientThreads[0].CurrentStageLabel);
        Assert.Contains("joined", packet.RecentRecipientThreads[0].Summary, StringComparison.OrdinalIgnoreCase);
        Assert.NotNull(sourceDetail);
        Assert.Equal("Source receipt drilldown", sourceDetail!.DetailKindLabel);
        Assert.Equal(packet.RecentDispatchReceipts[0].SourceReceiptId, sourceDetail.DetailKey);
        Assert.Equal("all", sourceDetail.FilterKey);
        Assert.False(sourceDetail.FilterApplied);
        Assert.Single(sourceDetail.RecipientThreads);
        Assert.Single(sourceDetail.DispatchReceipts);
        Assert.Single(sourceDetail.DeliveryOutcomes);
        Assert.Single(sourceDetail.JourneyReceipts);
        Assert.Equal(5, sourceDetail.SavedPivots.Count);
        Assert.Equal(1, sourceDetail.SavedPivots.Single(static pivot => string.Equals(pivot.Key, "all", StringComparison.Ordinal)).Count);
        Assert.NotNull(threadDetail);
        Assert.Equal("Recipient thread drilldown", threadDetail!.DetailKindLabel);
        Assert.Equal(packet.RecentDispatchReceipts[0].ReceiptId, threadDetail.DetailKey);
        Assert.Equal("all", threadDetail.FilterKey);
        Assert.Contains("?filter=sent", threadDetail.RelatedHref, StringComparison.Ordinal);
        Assert.Equal("Open sent threads", threadDetail.RelatedLabel);
        Assert.Single(threadDetail.RecipientThreads);
        Assert.Single(threadDetail.DispatchReceipts);
        Assert.Single(threadDetail.DeliveryOutcomes);
        Assert.Single(threadDetail.JourneyReceipts);
        Assert.Equal(packet.RecentDispatchReceipts[0].ReceiptId, threadDetail.RecipientThreads[0].DispatchReceiptId);
        Assert.NotNull(filteredThreadDetail);
        Assert.Equal("sent", filteredThreadDetail!.FilterKey);
        Assert.True(filteredThreadDetail.FilterApplied);
        Assert.Contains("?filter=sent", filteredThreadDetail.RelatedHref, StringComparison.Ordinal);
        Assert.Equal("Open source drilldown with the same filter", filteredThreadDetail.RelatedLabel);
        Assert.Contains("?filter=sent", filteredThreadDetail.SavedPivots.Single(static pivot => string.Equals(pivot.Key, "sent", StringComparison.Ordinal)).ArtifactHref, StringComparison.Ordinal);
        Assert.NotNull(sourceDetailJson);
        Assert.NotNull(threadDetailJson);
        Assert.Contains("\"recipientThreads\"", sourceDetailJson, StringComparison.Ordinal);
        Assert.Contains("\"savedPivots\"", sourceDetailJson, StringComparison.Ordinal);
        Assert.Contains("\"deliveryOutcomes\"", sourceDetailJson, StringComparison.Ordinal);
        Assert.Contains("\"detailKindLabel\": \"Source receipt drilldown\"", sourceDetailJson, StringComparison.Ordinal);
        Assert.Contains("\"detailKindLabel\": \"Recipient thread drilldown\"", threadDetailJson, StringComparison.Ordinal);
        Assert.Contains("\"dispatchReceipts\"", threadDetailJson, StringComparison.Ordinal);
    }

    [Fact]
    public void SourceDrilldownCanPivotBetweenSentRetryingSuppressedAndCallbackPendingThreads()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"] = "emailit-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_EA_DELIVERY_WEBHOOK_SECRET"] = "ea-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient("subject.email.sent", "sent@example.com");
        fixture.SeedVerifiedFollowRecipient("subject.email.retry", "retry@example.com");
        fixture.SeedVerifiedFollowRecipient("subject.email.suppressed", "suppressed@example.com");
        fixture.SeedVerifiedFollowRecipient("subject.email.pending", "pending@example.com");
        fixture.SetPathResponses(
            "/emails",
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { id = "emailit-send-1" }),
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { id = "emailit-send-2" }),
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { id = "emailit-send-3" }),
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { id = "emailit-send-4" }));
        fixture.SetPathResponses(
            "/v1/tools/execute",
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { target_ref = "delivery-1" }),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { target_ref = "delivery-2" }),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { target_ref = "delivery-3" }),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { target_ref = "delivery-4" }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { status = "ok" }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-2/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { status = "ok" }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-3/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { status = "ok" }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-4/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { status = "ok" }));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_019",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "pivot-proof",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        PublicSignalWebhookAckResponse sourceAck = service.RecordWebhook(sourcePayload);
        service.RecordDeliveryOutcome(
            "emailit",
            JsonDocument.Parse(
                $$"""
                {
                  "type": "email.delivered",
                  "data": {
                    "id": "emailit-pivot-sent",
                    "to": "sent@example.com",
                    "meta": {
                      "source_receipt_id": "{{sourceAck.ReceiptId}}"
                    },
                    "created_at": "2026-05-06T13:30:00Z"
                  }
                }
                """).RootElement.Clone());
        service.RecordDeliveryOutcome(
            "emailit",
            JsonDocument.Parse(
                $$"""
                {
                  "type": "email.bounced",
                  "data": {
                    "id": "emailit-pivot-retry",
                    "to": "retry@example.com",
                    "bounce_type": "soft",
                    "retry_in_seconds": 300,
                    "reason": "mailbox full",
                    "meta": {
                      "source_receipt_id": "{{sourceAck.ReceiptId}}"
                    },
                    "created_at": "2026-05-06T13:31:00Z"
                  }
                }
                """).RootElement.Clone());
        service.RecordDeliveryOutcome(
            "emailit",
            JsonDocument.Parse(
                $$"""
                {
                  "type": "email.bounced",
                  "data": {
                    "id": "emailit-pivot-suppressed",
                    "to": "suppressed@example.com",
                    "bounce_type": "hard",
                    "reason": "unknown user",
                    "meta": {
                      "source_receipt_id": "{{sourceAck.ReceiptId}}"
                    },
                    "created_at": "2026-05-06T13:32:00Z"
                  }
                }
                """).RootElement.Clone());

        PublicSignalOperationsDetailViewModel? allDetail = service.BuildSourceReceiptDetail(sourceAck.ReceiptId);
        PublicSignalOperationsDetailViewModel? retryingDetail = service.BuildSourceReceiptDetail(sourceAck.ReceiptId, "retrying");
        PublicSignalOperationsDetailViewModel? suppressedDetail = service.BuildSourceReceiptDetail(sourceAck.ReceiptId, "suppressed");
        PublicSignalOperationsDetailViewModel? sentDetail = service.BuildSourceReceiptDetail(sourceAck.ReceiptId, "sent");
        PublicSignalOperationsDetailViewModel? callbackPendingDetail = service.BuildSourceReceiptDetail(sourceAck.ReceiptId, "callback_pending");
        string? retryingJson = service.LoadSourceReceiptDetailJson(sourceAck.ReceiptId, "retrying");
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.NotNull(allDetail);
        Assert.NotNull(retryingDetail);
        Assert.NotNull(suppressedDetail);
        Assert.NotNull(sentDetail);
        Assert.NotNull(callbackPendingDetail);

        Assert.Equal(4, allDetail!.RecipientThreads.Count);
        Assert.Equal(1, allDetail.SavedPivots.Single(static pivot => string.Equals(pivot.Key, "sent", StringComparison.Ordinal)).Count);
        Assert.Equal(1, allDetail.SavedPivots.Single(static pivot => string.Equals(pivot.Key, "retrying", StringComparison.Ordinal)).Count);
        Assert.Equal(1, allDetail.SavedPivots.Single(static pivot => string.Equals(pivot.Key, "suppressed", StringComparison.Ordinal)).Count);
        Assert.Equal(1, allDetail.SavedPivots.Single(static pivot => string.Equals(pivot.Key, "callback_pending", StringComparison.Ordinal)).Count);
        Assert.Equal("retrying", packet.RecentReceipts[0].HotFilterKey);
        Assert.Equal("Retrying threads", packet.RecentReceipts[0].HotFilterLabel);
        Assert.Equal(1, packet.RecentReceipts[0].HotFilterCount);

        Assert.Equal("retrying", retryingDetail!.FilterKey);
        Assert.True(retryingDetail.FilterApplied);
        Assert.Contains("?filter=retrying", retryingDetail.SavedPivots.Single(static pivot => string.Equals(pivot.Key, "retrying", StringComparison.Ordinal)).ArtifactHref, StringComparison.Ordinal);
        Assert.Single(retryingDetail.RecipientThreads);
        Assert.Single(retryingDetail.DispatchReceipts);
        Assert.Single(retryingDetail.DeliveryOutcomes);
        Assert.Empty(retryingDetail.JourneyReceipts);
        Assert.Equal("retrying", retryingDetail.DispatchReceipts[0].DeliveryState);

        Assert.Equal("suppressed", suppressedDetail!.FilterKey);
        Assert.Single(suppressedDetail.RecipientThreads);
        Assert.Single(suppressedDetail.DispatchReceipts);
        Assert.Single(suppressedDetail.DeliveryOutcomes);
        Assert.Equal("suppressed", suppressedDetail.DispatchReceipts[0].DeliveryState);

        Assert.Equal("sent", sentDetail!.FilterKey);
        Assert.Single(sentDetail.RecipientThreads);
        Assert.Single(sentDetail.DispatchReceipts);
        Assert.Single(sentDetail.DeliveryOutcomes);
        Assert.Empty(sentDetail.JourneyReceipts);
        Assert.Equal("sent", sentDetail.DispatchReceipts[0].DeliveryState);

        Assert.Equal("callback_pending", callbackPendingDetail!.FilterKey);
        Assert.Single(callbackPendingDetail.RecipientThreads);
        Assert.Single(callbackPendingDetail.DispatchReceipts);
        Assert.Empty(callbackPendingDetail.DeliveryOutcomes);
        Assert.Empty(callbackPendingDetail.JourneyReceipts);
        Assert.DoesNotContain(callbackPendingDetail.DispatchReceipts, static receipt => string.Equals(receipt.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(callbackPendingDetail.DispatchReceipts, static receipt => string.Equals(receipt.DeliveryState, "retrying", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(callbackPendingDetail.DispatchReceipts, static receipt => string.Equals(receipt.DeliveryState, "suppressed", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("Showing 1 of 4 retrying threads.", retryingDetail.Summary, StringComparison.Ordinal);

        Assert.NotNull(retryingJson);
        Assert.Contains("\"filterKey\": \"retrying\"", retryingJson, StringComparison.Ordinal);
        Assert.Contains("\"savedPivots\"", retryingJson, StringComparison.Ordinal);
    }

    [Fact]
    public void LookupCanSearchBoundedSourceAndThreadDrilldowns()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"] = "emailit-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_EA_DELIVERY_WEBHOOK_SECRET"] = "ea-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/emails",
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_018",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "lookup-proof",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "type": "email.delivered",
              "data": {
                "id": "emailit-lookup-1",
                "delivery_id": "delivery-1",
                "to": "runner@example.com",
                "created_at": "2026-05-06T13:25:00Z"
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(sourcePayload);
        service.RecordDeliveryOutcome("emailit", callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        PublicSignalOperationsLookupViewModel threadLookup = service.BuildLookup(packet.RecentDispatchReceipts[0].RecipientRef, "thread");
        PublicSignalOperationsLookupViewModel sourceLookup = service.BuildLookup("lookup-proof", "source");
        string lookupJson = service.LoadLookupJson(packet.RecentDispatchReceipts[0].DeliveryId, "thread");

        Assert.Equal("thread", threadLookup.Scope);
        Assert.True(threadLookup.QueryProvided);
        Assert.Single(threadLookup.Results);
        Assert.Equal("Recipient thread", threadLookup.Results[0].ResultKindLabel);
        Assert.Equal(packet.RecentDispatchReceipts[0].ReceiptId, threadLookup.Results[0].Key);
        Assert.Equal("sent", threadLookup.Results[0].FilterKey);
        Assert.Equal("Sent threads", threadLookup.Results[0].FilterLabel);
        Assert.Equal("Recipient ref", threadLookup.Results[0].MatchReason);
        Assert.Contains("?filter=sent", threadLookup.Results[0].Href, StringComparison.Ordinal);
        Assert.Contains("?filter=sent", threadLookup.Results[0].ArtifactHref, StringComparison.Ordinal);
        Assert.Equal("source", sourceLookup.Scope);
        Assert.Single(sourceLookup.Results);
        Assert.Equal("sent", sourceLookup.Results[0].FilterKey);
        Assert.Equal("Sent threads", sourceLookup.Results[0].FilterLabel);
        Assert.Equal("Source receipt", sourceLookup.Results[0].ResultKindLabel);
        Assert.Equal(packet.RecentDispatchReceipts[0].SourceReceiptId, sourceLookup.Results[0].Key);
        Assert.Equal("Item reference", sourceLookup.Results[0].MatchReason);
        Assert.Contains("?filter=sent", sourceLookup.Results[0].Href, StringComparison.Ordinal);
        Assert.Contains("?filter=sent", sourceLookup.Results[0].ArtifactHref, StringComparison.Ordinal);
        Assert.Contains("\"scope\": \"thread\"", lookupJson, StringComparison.Ordinal);
        Assert.Contains("\"resultKindLabel\": \"Recipient thread\"", lookupJson, StringComparison.Ordinal);
        Assert.Contains("\"filterKey\": \"sent\"", lookupJson, StringComparison.Ordinal);
        Assert.Contains("\"delivery-1\"", lookupJson, StringComparison.Ordinal);
    }

    [Fact]
    public void StaleAcceptedCallbackDoesNotRegressSentDispatchState()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"] = "emailit-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/emails",
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_015",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "stale-accepted",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        PublicSignalWebhookAckResponse sourceAck = service.RecordWebhook(sourcePayload);
        JsonElement deliveredPayload = JsonDocument.Parse(
            $$"""
            {
              "type": "email.delivered",
              "data": {
                "id": "emailit-stale-1",
                "to": "runner@example.invalid",
                "meta": {
                  "source_receipt_id": "{{sourceAck.ReceiptId}}"
                },
                "created_at": "2026-05-06T13:10:00Z"
              }
            }
            """).RootElement.Clone();
        JsonElement acceptedPayload = JsonDocument.Parse(
            $$"""
            {
              "type": "email.accepted",
              "data": {
                "id": "emailit-stale-1",
                "to": "runner@example.invalid",
                "meta": {
                  "source_receipt_id": "{{sourceAck.ReceiptId}}"
                },
                "created_at": "2026-05-06T13:11:00Z"
              }
            }
            """).RootElement.Clone();

        service.RecordDeliveryOutcome("emailit", deliveredPayload);
        PublicSignalDeliveryOutcomeAckResponse staleAck = service.RecordDeliveryOutcome("emailit", acceptedPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.False(staleAck.Duplicate);
        Assert.Equal(2, packet.DeliveryOutcomeReceiptCount);
        Assert.Equal("sent", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("Provider confirmed sent", packet.RecentDispatchReceipts[0].StatusLabel);
        Assert.Equal("provider_callback_stale", packet.RecentDispatchReceipts[0].LastRecoveryStatus);
        Assert.Equal("emailit-stale-1", packet.RecentDispatchReceipts[0].ProviderMessageId);
        Assert.Equal(packet.RecentDispatchReceipts[0].RecipientRef, packet.RecentDeliveryOutcomes[0].RecipientRef);
        Assert.Equal(packet.RecentDispatchReceipts[0].AddressHash, packet.RecentDeliveryOutcomes[0].AddressHash);
        Assert.Equal("provider_message_id", packet.RecentDeliveryOutcomes[0].IdentityMatchMode);
        Assert.Equal(1, packet.JourneyReceiptCount);
    }

    [Fact]
    public void EmailitCallbackProjectsBoundedRecipientIdentityWhenMatchedByAddressHash()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"] = "emailit-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/emails",
            new ScriptedResponse(HttpStatusCode.Accepted, Payload: new { }));
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_016",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "address-hash-proof",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        PublicSignalWebhookAckResponse sourceAck = service.RecordWebhook(sourcePayload);
        JsonElement callbackPayload = JsonDocument.Parse(
            $$"""
            {
              "type": "email.delivered",
              "data": {
                "id": "emailit-proof-1",
                "to": "runner@example.com",
                "meta": {
                  "source_receipt_id": "{{sourceAck.ReceiptId}}"
                },
                "created_at": "2026-05-06T13:15:00Z"
              }
            }
            """).RootElement.Clone();

        PublicSignalDeliveryOutcomeAckResponse ack = service.RecordDeliveryOutcome("emailit", callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.False(ack.Duplicate);
        Assert.Single(packet.RecentDeliveryOutcomes);
        Assert.Equal(packet.RecentDispatchReceipts[0].RecipientRef, packet.RecentDeliveryOutcomes[0].RecipientRef);
        Assert.Equal(packet.RecentDispatchReceipts[0].AddressHash, packet.RecentDeliveryOutcomes[0].AddressHash);
        Assert.Equal("source_receipt_address_hash", packet.RecentDeliveryOutcomes[0].IdentityMatchMode);
        Assert.StartsWith("usr-", packet.RecentDeliveryOutcomes[0].RecipientRef, StringComparison.Ordinal);
    }

    [Fact]
    public void EmailitSoftBounceNormalizesToRetryableProviderHold()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"] = "emailit-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_012",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "emailit-soft-bounce",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "type": "email.bounced",
              "data": {
                "id": "emailit-1",
                "delivery_id": "delivery-1",
                "to": "runner@example.invalid",
                "bounce_type": "soft",
                "retry_in_seconds": 300,
                "reason": "mailbox full",
                "created_at": "2026-05-06T12:45:00Z"
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(sourcePayload);
        PublicSignalDeliveryOutcomeAckResponse ack = service.RecordDeliveryOutcome("emailit", callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.False(ack.Duplicate);
        Assert.Equal("recorded", ack.Status);
        Assert.Equal(1, packet.DeliveryOutcomeReceiptCount);
        Assert.Equal(1, packet.AutomaticRetryPendingCount);
        Assert.Single(packet.RecentDeliveryOutcomes);
        Assert.Equal("Emailit", packet.RecentDeliveryOutcomes[0].Provider);
        Assert.Equal("Soft bounced", packet.RecentDeliveryOutcomes[0].ProviderState);
        Assert.Equal("Provider retry scheduled", packet.RecentDeliveryOutcomes[0].StatusLabel);
        Assert.Equal("retrying", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("retryable", packet.RecentDispatchReceipts[0].SuppressionCheck);
        Assert.Equal("Soft bounced", packet.RecentDispatchReceipts[0].LastProviderState);
    }

    [Fact]
    public void EaCallbackNormalizesDeadLetterSuppression()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_EA_DELIVERY_WEBHOOK_SECRET"] = "ea-webhook-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_013",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "ea-dead-letter",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "event_type": "delivery.failed",
              "data": {
                "delivery_id": "delivery-1",
                "provider_message_id": "emailit-1",
                "state": "failed",
                "dead_letter": true,
                "reason": "hard bounce unknown user",
                "occurred_at": "2026-05-06T12:55:00Z"
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(sourcePayload);
        PublicSignalDeliveryOutcomeAckResponse ack = service.RecordDeliveryOutcome("ea", callbackPayload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.False(ack.Duplicate);
        Assert.Equal("recorded", ack.Status);
        Assert.Single(packet.RecentDeliveryOutcomes);
        Assert.Equal("EA", packet.RecentDeliveryOutcomes[0].Provider);
        Assert.Equal("Suppressed", packet.RecentDeliveryOutcomes[0].ProviderState);
        Assert.Equal("Provider suppression", packet.RecentDeliveryOutcomes[0].StatusLabel);
        Assert.Equal("suppressed", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("suppressed", packet.RecentDispatchReceipts[0].SuppressionCheck);
        Assert.Equal("Suppressed", packet.RecentDispatchReceipts[0].LastProviderState);
    }

    [Fact]
    public void ExpiredProviderRetryWindowCanBeRecoveredByAutomaticSweep()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/v1/delivery/outbox/delivery-1/sent",
            new ScriptedResponse(HttpStatusCode.InternalServerError, RawBody: "{\"error\":\"transient outbox write error\"}"),
            new ScriptedResponse(HttpStatusCode.OK, Payload: new { status = "ok" }));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement sourcePayload = JsonDocument.Parse(
            """
            {
              "id": "evt_011",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "auto-retry-expiry",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();
        JsonElement callbackPayload = JsonDocument.Parse(
            """
            {
              "provider": "emailit",
              "event_id": "outcome_003",
              "data": {
                "item": {
                  "delivery_id": "delivery-1",
                  "provider_message_id": "emailit-1",
                  "state": "retrying",
                  "reason": "provider retry window elapsed",
                  "retry_at": "2026-05-05T11:00:00Z",
                  "occurred_at": "2026-05-05T10:00:00Z"
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(sourcePayload);
        service.RecordDeliveryOutcome(callbackPayload);
        PublicSignalOperationsPacketViewModel blockedPacket = service.BuildPacket();
        PublicSignalOperationsRecoveryResponse recovery = service.RecoverExpiredRetryWindows();
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.Equal(1, blockedPacket.DeliveryRecoveryCandidateCount);
        Assert.Equal(1, blockedPacket.RetryExpiryCandidateCount);
        Assert.Equal("retrying", blockedPacket.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("recovered", recovery.Status);
        Assert.Equal(1, recovery.CandidateReceiptCount);
        Assert.Equal(1, recovery.RecoveredReceiptCount);
        Assert.Equal(0, recovery.SuppressedReceiptCount);
        Assert.Equal(0, recovery.BlockedReceiptCount);
        Assert.Equal(0, packet.RetryExpiryCandidateCount);
        Assert.Equal(1, packet.RetryExpiryRunCount);
        Assert.Single(packet.RecentRetryExpiryRuns);
        Assert.Equal("recovered", packet.RecentRetryExpiryRuns[0].Status);
        Assert.Equal("sent", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("Sent after recovery", packet.RecentDispatchReceipts[0].StatusLabel);
        Assert.Equal("retry_sent", packet.RecentDispatchReceipts[0].LastRecoveryStatus);
        Assert.Equal(1, packet.JourneyReceiptCount);
    }

    [Fact]
    public void SuppressedDispatchFailureStaysOutOfAutomaticRecovery()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"] = "ops-secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS"] = "hub_transactional_follow",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID"] = "principal-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID"] = "binding-001",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED"] = "true",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF"] = "gov-2026-05-06-productlift-closeout",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL"] = "https://emailit.test",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL"] = "https://chummer.run"
        }, enableHttpCapture: true);
        fixture.WriteSupportFiles();
        fixture.WriteReleaseProofFile("/changelog");
        fixture.SeedVerifiedFollowRecipient();
        fixture.SetPathResponses(
            "/emails",
            new ScriptedResponse(HttpStatusCode.Conflict, RawBody: "{\"error\":\"suppressed recipient\"}"));
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_008",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "mobile_companion"
                },
                "item": {
                  "slug": "suppressed-recipient",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": true
                }
              }
            }
            """).RootElement.Clone();

        service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();
        PublicSignalOperationsRecoveryResponse recovery = service.RecoverDispatchOutcomes();

        Assert.Equal(1, packet.SuppressedDispatchCount);
        Assert.Equal(0, packet.DeliveryRecoveryCandidateCount);
        Assert.Single(packet.RecentDispatchReceipts);
        Assert.Equal("failed", packet.RecentDispatchReceipts[0].DeliveryState);
        Assert.Equal("suppressed", packet.RecentDispatchReceipts[0].SuppressionCheck);
        Assert.Equal("noop", recovery.Status);
        Assert.Equal(0, recovery.CandidateReceiptCount);
        Assert.Equal(0, recovery.RecoveredReceiptCount);
        Assert.Equal(3, fixture.Requests.Count);
    }

    [Fact]
    public void CloseoutTimelineStaysSuppressedWhenProviderDisallowsVoterNotification()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret",
            ["CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY"] = "emailit-api-key"
        });
        fixture.WriteSupportFiles();
        PublicSignalOperationsService service = fixture.CreateService();
        JsonElement payload = JsonDocument.Parse(
            """
            {
              "id": "evt_003",
              "type": "idea.status_changed",
              "data": {
                "category": {
                  "slug": "desktop_and_install"
                },
                "item": {
                  "slug": "blocked-closeout",
                  "status": {
                    "name": "shipped"
                  },
                  "voter_notification_allowed": false
                }
              }
            }
            """).RootElement.Clone();

        PublicSignalWebhookAckResponse ack = service.RecordWebhook(payload);
        PublicSignalOperationsPacketViewModel packet = service.BuildPacket();

        Assert.True(ack.CloseoutReceiptRecorded);
        Assert.Single(packet.RecentCloseoutReceipts);
        Assert.Equal("Notification blocked", packet.RecentCloseoutReceipts[0].StatusLabel);
        Assert.Equal("suppressed", packet.RecentCloseoutReceipts[0].DeliveryState);
        Assert.Equal("productlift_voter_shipped", packet.RecentCloseoutReceipts[0].TemplateId);
        Assert.Equal("hub_follow_horizons:verified_email", packet.RecentCloseoutReceipts[0].RecipientScopeRef);
        Assert.Equal(0, packet.CloseoutDeliveryCandidateCount);
        Assert.Equal(0, packet.CloseoutDispatchReceiptCount);
        Assert.Equal(0, packet.JourneyReceiptCount);
        Assert.Contains("does not currently allow voter notification", packet.RecentCloseoutReceipts[0].DeliveryReason, StringComparison.OrdinalIgnoreCase);
        Assert.False(packet.RecentCloseoutReceipts[0].PublicClaimAllowed);
    }

    [Fact]
    public void LoadArtifactJsonPublishesTheOperationsContract()
    {
        using var fixture = new PublicSignalOperationsFixture(new Dictionary<string, string?>
        {
            ["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] = "https://ideas.chummer.run/feedback",
            ["CHUMMER_PRODUCTLIFT_ROADMAP_URL"] = "https://ideas.chummer.run/roadmap",
            ["CHUMMER_PRODUCTLIFT_CHANGELOG_URL"] = "https://ideas.chummer.run/changelog",
            ["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"] = "secret"
        });
        fixture.WriteSupportFiles();

        string json = fixture.CreateService().LoadArtifactJson();
        using var document = JsonDocument.Parse(json);

        Assert.Equal("chummer.public_signal_operations", document.RootElement.GetProperty("contractName").GetString());
        Assert.True(document.RootElement.GetProperty("hostedProjectionReady").GetBoolean());
        Assert.True(document.RootElement.TryGetProperty("generatedAtUtc", out _));
        Assert.True(document.RootElement.TryGetProperty("hostedDomainLabel", out _));
        Assert.True(document.RootElement.TryGetProperty("hostedProjectionSummary", out _));
        Assert.True(document.RootElement.TryGetProperty("recipientProjectionStatusLabel", out _));
        Assert.True(document.RootElement.TryGetProperty("queueStatusLabel", out _));
        Assert.True(document.RootElement.TryGetProperty("releaseProofStatusLabel", out _));
        JsonElement counts = document.RootElement.GetProperty("counts");
        Assert.Equal(4, counts.GetProperty("categoryCount").GetInt32());
        Assert.Equal(0, counts.GetProperty("receiptCount").GetInt32());
        Assert.Equal(0, counts.GetProperty("routingReceiptCount").GetInt32());
        Assert.Equal(0, counts.GetProperty("closeoutReceiptCount").GetInt32());
    }

    private sealed class PublicSignalOperationsFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _canonRoot;
        private readonly IReadOnlyDictionary<string, string?> _settings;
        private readonly IConfiguration _configuration;
        private readonly CommunityStore _communityStore;
        private readonly AccountService _accounts;
        private readonly IdentityLinkService _links;
        private readonly UserExperienceService _experience;
        private readonly PublicSignalOperationsService _service;
        private readonly CapturingHttpClientFactory? _httpClientFactory;

        public PublicSignalOperationsFixture(IReadOnlyDictionary<string, string?>? settings = null, bool enableHttpCapture = false)
        {
            _root = Path.Combine(Path.GetTempPath(), "public-signal-operations-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(_root, "repo");
            Directory.CreateDirectory(_canonRoot);
            _settings = settings ?? new Dictionary<string, string?>();

            Dictionary<string, string?> configValues = new(_settings)
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot,
                ["CHUMMER_PRODUCTLIFT_OPERATIONS_STORE_PATH"] = Path.Combine(_root, "productlift-operations-store.json"),
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                ["CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE"] = Path.Combine(_root, "HUB_LOCAL_RELEASE_PROOF.generated.json")
            };

            _configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(configValues)
                .Build();
            _communityStore = new CommunityStore(_configuration, NullLogger<CommunityStore>.Instance);
            _accounts = new AccountService(_communityStore);
            _links = new IdentityLinkService(_communityStore, _accounts);
            _experience = new UserExperienceService(_communityStore, _accounts);
            _httpClientFactory = enableHttpCapture ? new CapturingHttpClientFactory() : null;
            _service = new PublicSignalOperationsService(
                new PublicCanonFileLoader(_configuration),
                _configuration,
                _communityStore,
                NullLogger<PublicSignalOperationsService>.Instance,
                _httpClientFactory);
        }

        public PublicSignalOperationsService CreateService() => _service;

        public IReadOnlyList<CapturedRequest> Requests => _httpClientFactory?.Requests ?? Array.Empty<CapturedRequest>();

        public void SetSetting(string key, string? value)
            => _configuration[key] = value;

        public void SetPathResponses(string path, params ScriptedResponse[] responses)
            => _httpClientFactory?.SetResponses(path, responses);

        public void SeedVerifiedFollowRecipient(
            string subjectId = "subject.email.runner",
            string email = "runner@example.com")
        {
            _accounts.EnsureUser(subjectId, "Runner", email);
            LinkedIdentityDto link = _links.LinkEmail(new LinkEmailIdentityRequest(subjectId, email));
            _links.ConfirmIdentityLink(new ConfirmIdentityLinkRequest(subjectId, link.IdentityLinkId));
            _experience.Upsert(new UpsertHubUserExperienceRequest(
                SubjectId: subjectId,
                FollowHorizons: true,
                OnboardingCompleted: true));
        }

        public void WriteSupportFiles()
        {
            string productRoot = Path.Combine(_canonRoot, "products", "chummer");
            Directory.CreateDirectory(productRoot);
            File.WriteAllText(
                Path.Combine(productRoot, "PUBLIC_FEEDBACK_TAXONOMY.yaml"),
                """
version: 1
categories:
  - key: desktop_and_install
    label: Desktop / Install / Updates
    owner_repo: chummer6-ui
    support_misroute_likely: true
    discovery_lane: none
  - key: build_and_explain
    label: Build & Explain
    owner_repo: chummer6-core
    discovery_lane: public_signal
  - key: mobile_companion
    label: Mobile Companion
    owner_repo: chummer6-mobile
    discovery_lane: public_signal_plus_survey
  - key: table_pulse
    label: Table Pulse / Debrief
    owner_repo: chummer6-hub
    discovery_lane: guided_follow_up
    privacy_sensitive: true
rules:
  - Public signal categories route public signal; they do not assign implementation priority.
  - Support, crash, account, install, private log, and private campaign posts are misroutes, not feature votes.
""");
            File.WriteAllText(
                Path.Combine(productRoot, "OUTBOUND_NOTIFICATION_TEMPLATE_REGISTRY.yaml"),
                """
version: 1
families:
  - key: product_feedback_closeout
    examples:
      - productlift_voter_shipped
      - discovery_followup
""");
        }

        public void WriteReleaseProofFile(params string[] routes)
        {
            string proofPath = _configuration["CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE"]!;
            string[] normalizedRoutes = routes.Length == 0 ? ["/changelog"] : routes;
            File.WriteAllText(
                proofPath,
                $$"""
                {
                  "contract_name": "chummer6-hub.local_release_proof",
                  "generatedAt": "{{DateTimeOffset.UtcNow.ToString("O")}}",
                  "status": "current",
                  "proof_routes": {{JsonSerializer.Serialize(normalizedRoutes)}},
                  "proof_receipts": [
                    {
                      "receipt_id": "proof_001",
                      "package_id": "pkg_001",
                      "summary": "Current public changelog proof is on file.",
                      "routes": {{JsonSerializer.Serialize(normalizedRoutes)}}
                    }
                  ]
                }
                """);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed record CapturedRequest(string Url, string Body);

    private sealed record ScriptedResponse(HttpStatusCode StatusCode, object? Payload = null, string? RawBody = null);

    private sealed class CapturingHandler(
        List<CapturedRequest> requests,
        Dictionary<string, Queue<ScriptedResponse>> scriptedResponses) : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            requests.Add(new CapturedRequest(request.RequestUri!.ToString(), body));

            if (scriptedResponses.TryGetValue(request.RequestUri!.AbsolutePath, out Queue<ScriptedResponse>? responses)
                && responses.Count > 0)
            {
                return BuildResponse(responses.Dequeue());
            }

            object payload = request.RequestUri!.AbsolutePath switch
            {
                "/v1/tools/execute" => new { target_ref = "delivery-1" },
                "/emails" => new { id = "emailit-1" },
                _ => new { status = "ok" }
            };

            return BuildResponse(new ScriptedResponse(HttpStatusCode.OK, Payload: payload));
        }

        private static HttpResponseMessage BuildResponse(ScriptedResponse response)
            => new(response.StatusCode)
            {
                Content = response.RawBody is not null
                    ? new StringContent(response.RawBody, Encoding.UTF8, "application/json")
                    : JsonContent.Create(response.Payload ?? new { status = "ok" })
            };
    }

    private sealed class CapturingHttpClientFactory : IHttpClientFactory
    {
        private readonly List<CapturedRequest> _requests = [];
        private readonly Dictionary<string, Queue<ScriptedResponse>> _scriptedResponses = new(StringComparer.OrdinalIgnoreCase);

        public IReadOnlyList<CapturedRequest> Requests => _requests;

        public void SetResponses(string path, params ScriptedResponse[] responses)
            => _scriptedResponses[path] = new Queue<ScriptedResponse>(responses);

        public HttpClient CreateClient(string name) => new(new CapturingHandler(_requests, _scriptedResponses));
    }
}
