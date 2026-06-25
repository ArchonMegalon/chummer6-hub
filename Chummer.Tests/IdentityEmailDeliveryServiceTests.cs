using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class IdentityEmailDeliveryServiceTests
{
    [Fact]
    public void DeliverMagicLinkUsesEmailitCompliantIdempotencyKey()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-run-identity-email-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            HttpRequestMessage? capturedRequest = null;
            string? capturedBody = null;
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["IDENTITY_PUBLIC_BASE_URL"] = "https://chummer.run",
                    ["IDENTITY_EMAILIT_API_KEY"] = "secret-emailit-key",
                    ["IDENTITY_EMAILIT_FROM_EMAIL"] = "concierge@chummer.run",
                    ["IDENTITY_EMAILIT_FROM_NAME"] = "Chummer Concierge",
                    ["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"] = Path.Combine(tempRoot, "identity-email-delivery.json")
                })
                .Build();

            var service = new IdentityEmailDeliveryService(
                configuration,
                NullLogger<IdentityEmailDeliveryService>.Instance,
                new HttpClient(new StubHttpMessageHandler(request =>
                {
                    capturedRequest = request;
                    capturedBody = request.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return new HttpResponseMessage(HttpStatusCode.Accepted)
                    {
                        Content = new StringContent("{\"data\":{\"id\":\"email_123\"}}", Encoding.UTF8, "application/json")
                    };
                })));

            var delivered = service.DeliverMagicLink(
                email: "runner@example.invalid",
                displayName: "Runner Demo",
                ticketId: "ticket-emailit-123",
                nextPath: "/home",
                expiresAtUtc: DateTimeOffset.Parse("2026-03-20T10:00:00Z"));

            Assert.True(delivered.Delivered);
            Assert.NotNull(capturedRequest);
            Assert.True(capturedRequest!.Headers.TryGetValues("Idempotency-Key", out IEnumerable<string>? values));

            string idempotencyKey = Assert.Single(values!);
            Assert.StartsWith("email_magic_link_", idempotencyKey, StringComparison.Ordinal);
            Assert.DoesNotContain("ticket-emailit-123", idempotencyKey, StringComparison.Ordinal);
            Assert.DoesNotContain(":", idempotencyKey, StringComparison.Ordinal);
            Assert.Matches(new Regex("^[A-Za-z0-9_-]+$"), idempotencyKey);

            Assert.NotNull(capturedBody);
            using JsonDocument json = JsonDocument.Parse(capturedBody!);
            JsonElement meta = json.RootElement.GetProperty("meta");
            Assert.False(meta.TryGetProperty("ticket_id", out _));
            Assert.Equal("magic_link", meta.GetProperty("purpose").GetString());
            Assert.Equal("/home", meta.GetProperty("next_path").GetString());
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void DeliverMagicLinkDoesNotPreviewInlineTicketWhenProductionFlagIsMisconfigured()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-run-identity-email-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ASPNETCORE_ENVIRONMENT"] = "Production",
                    ["IDENTITY_PUBLIC_BASE_URL"] = "https://chummer.run",
                    ["IDENTITY_UNSAFE_ALLOW_INLINE_EMAIL_PREVIEW_LINKS"] = "true",
                    ["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"] = Path.Combine(tempRoot, "identity-email-delivery.json")
                })
                .Build();

            var service = new IdentityEmailDeliveryService(
                configuration,
                NullLogger<IdentityEmailDeliveryService>.Instance,
                new HttpClient(new StubHttpMessageHandler(_ => throw new InvalidOperationException("No transport should be called."))));

            IdentityEmailDeliveryResult result = service.DeliverMagicLink(
                email: "runner@example.invalid",
                displayName: "Runner Demo",
                ticketId: "ticket-production-preview",
                nextPath: "/home",
                expiresAtUtc: DateTimeOffset.Parse("2026-03-20T10:00:00Z"));

            Assert.False(result.Delivered);
            Assert.Equal("email_delivery_unavailable", result.DeliveryMode);
            Assert.DoesNotContain("development preview callback link", result.PreviewNote, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void DeliverMagicLinkAllowsInlinePreviewOnlyForDevelopmentLoopback()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-run-identity-email-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ASPNETCORE_ENVIRONMENT"] = "Development",
                    ["IDENTITY_PUBLIC_BASE_URL"] = "http://localhost:5101",
                    ["IDENTITY_UNSAFE_ALLOW_INLINE_EMAIL_PREVIEW_LINKS"] = "true",
                    ["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"] = Path.Combine(tempRoot, "identity-email-delivery.json")
                })
                .Build();

            var service = new IdentityEmailDeliveryService(
                configuration,
                NullLogger<IdentityEmailDeliveryService>.Instance,
                new HttpClient(new StubHttpMessageHandler(_ => throw new InvalidOperationException("No transport should be called."))));

            IdentityEmailDeliveryResult result = service.DeliverMagicLink(
                email: "runner@example.invalid",
                displayName: "Runner Demo",
                ticketId: "ticket-development-preview",
                nextPath: "/home",
                expiresAtUtc: DateTimeOffset.Parse("2026-03-20T10:00:00Z"));

            Assert.False(result.Delivered);
            Assert.Equal("preview_inline_link", result.DeliveryMode);
            Assert.Contains("development preview callback link", result.PreviewNote, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void StartEmailEntryDoesNotReturnBearerTicketWhenProductionEmailDeliveryIsUnavailable()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-run-identity-email-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ASPNETCORE_ENVIRONMENT"] = "Production",
                    ["IDENTITY_PUBLIC_BASE_URL"] = "https://chummer.run",
                    ["IDENTITY_UNSAFE_ALLOW_INLINE_EMAIL_PREVIEW_LINKS"] = "true",
                    ["CHUMMER_IDENTITY_STORE_PATH"] = Path.Combine(tempRoot, "identity-store.json"),
                    ["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"] = Path.Combine(tempRoot, "identity-email-delivery.json")
                })
                .Build();
            var delivery = new IdentityEmailDeliveryService(
                configuration,
                NullLogger<IdentityEmailDeliveryService>.Instance,
                new HttpClient(new StubHttpMessageHandler(_ => throw new InvalidOperationException("No transport should be called."))));
            var access = new IdentityAccessService(
                configuration,
                NullLogger<IdentityAccessService>.Instance,
                delivery);

            EmailAuthStartResponse response = access.StartEmailEntry(new EmailAuthStartRequest(
                Email: "runner@example.invalid",
                DisplayName: "Runner Demo",
                NextPath: "/home"));

            Assert.Equal(string.Empty, response.TicketId);
            Assert.Equal("email_delivery_unavailable", response.DeliveryMode);
            Assert.Throws<ArgumentException>(() => access.CompleteEmailEntry(new EmailAuthCompleteRequest(response.TicketId)));
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void IdentityStorePersistsOnlyHashedEmailTicketsAndSessionTokens()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-run-identity-email-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            string storePath = Path.Combine(tempRoot, "identity-store.json");
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ASPNETCORE_ENVIRONMENT"] = "Development",
                    ["IDENTITY_PUBLIC_BASE_URL"] = "http://localhost:5101",
                    ["CHUMMER_IDENTITY_STORE_PATH"] = storePath
                })
                .Build();
            var delivery = new InlinePreviewDelivery();
            var access = new IdentityAccessService(
                configuration,
                NullLogger<IdentityAccessService>.Instance,
                delivery);

            EmailAuthStartResponse emailStart = access.StartEmailEntry(new EmailAuthStartRequest(
                Email: "runner@example.invalid",
                DisplayName: "Runner Demo",
                NextPath: "/home"));

            Assert.StartsWith("eml_", emailStart.TicketId, StringComparison.Ordinal);
            string pendingTicketStore = File.ReadAllText(storePath);
            Assert.Contains("\"ticketHash\"", pendingTicketStore, StringComparison.Ordinal);
            Assert.DoesNotContain("\"ticketId\"", pendingTicketStore, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(emailStart.TicketId, pendingTicketStore, StringComparison.Ordinal);

            IdentitySessionIssueResponse session = access.CompleteEmailEntry(new EmailAuthCompleteRequest(emailStart.TicketId));
            string completedStore = File.ReadAllText(storePath);

            Assert.Contains("\"accessTokenHash\"", completedStore, StringComparison.Ordinal);
            Assert.Contains("\"refreshTokenHash\"", completedStore, StringComparison.Ordinal);
            Assert.DoesNotContain("\"accessToken\"", completedStore, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("\"refreshToken\"", completedStore, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(session.AccessToken, completedStore, StringComparison.Ordinal);
            Assert.DoesNotContain(session.RefreshToken, completedStore, StringComparison.Ordinal);
            Assert.DoesNotContain(emailStart.TicketId, completedStore, StringComparison.Ordinal);
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private sealed class StubHttpMessageHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> _handler;

        public StubHttpMessageHandler(Func<HttpRequestMessage, HttpResponseMessage> handler)
        {
            _handler = handler;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(_handler(request));
    }

    private sealed class InlinePreviewDelivery : IIdentityEmailDeliveryService
    {
        public IdentityEmailDeliveryStatusResponse GetStatus() =>
            new(
                RecentDeliveries: Array.Empty<IdentityEmailDeliveryEventResponse>(),
                Recipients: Array.Empty<IdentityEmailRecipientStateResponse>(),
                GeneratedAtUtc: DateTimeOffset.UtcNow);

        public IdentityEmailDeliveryResult DeliverMagicLink(
            string email,
            string displayName,
            string ticketId,
            string? nextPath,
            DateTimeOffset expiresAtUtc) =>
            new(
                DeliveryMode: "preview_inline_link",
                PreviewNote: "development preview callback link",
                Delivered: false);

        public IdentityEmailWebhookAckResponse RecordEmailitWebhook(System.Text.Json.JsonElement payload) =>
            new(
                Provider: "test",
                Status: "accepted",
                RecordedEvents: 0,
                ReceivedAtUtc: DateTimeOffset.UtcNow);
    }
}
