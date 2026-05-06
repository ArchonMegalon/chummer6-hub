using System.Net;
using System.Text;
using System.Text.RegularExpressions;
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
            Assert.Equal("email_magic_link_ticket-emailit-123", idempotencyKey);
            Assert.DoesNotContain(":", idempotencyKey, StringComparison.Ordinal);
            Assert.Matches(new Regex("^[A-Za-z0-9_-]+$"), idempotencyKey);
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
}
