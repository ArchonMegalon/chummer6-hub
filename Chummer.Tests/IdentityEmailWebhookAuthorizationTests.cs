using System.Text.Json;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Controllers;
using Chummer.Run.Identity.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class IdentityEmailWebhookAuthorizationTests
{
    [Fact]
    public void EmailitWebhookWithoutSecretFailsClosedInProductionEvenWhenUnsafeFlagIsSet()
    {
        using JsonDocument payload = JsonDocument.Parse("""{"event":"delivered"}""");
        IdentityController controller = BuildController(new Dictionary<string, string?>
        {
            ["ASPNETCORE_ENVIRONMENT"] = "Production",
            ["IDENTITY_UNSAFE_ALLOW_UNSIGNED_EMAILIT_WEBHOOKS"] = "true"
        });

        ActionResult<IdentityEmailWebhookAckResponse> result = controller.ReceiveEmailitWebhook(payload.RootElement);

        ObjectResult problem = Assert.IsAssignableFrom<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void EmailitWebhookUnsafeUnsignedModeIsDevelopmentOnly()
    {
        using JsonDocument payload = JsonDocument.Parse("""{"event":"delivered"}""");
        var emailDelivery = new FakeEmailDeliveryService();
        IdentityController controller = BuildController(new Dictionary<string, string?>
        {
            ["ASPNETCORE_ENVIRONMENT"] = "Development",
            ["IDENTITY_UNSAFE_ALLOW_UNSIGNED_EMAILIT_WEBHOOKS"] = "true"
        }, emailDelivery);

        ActionResult<IdentityEmailWebhookAckResponse> result = controller.ReceiveEmailitWebhook(payload.RootElement);

        OkObjectResult ok = Assert.IsAssignableFrom<OkObjectResult>(result.Result);
        var response = Assert.IsAssignableFrom<IdentityEmailWebhookAckResponse>(ok.Value);
        Assert.Equal("Emailit", response.Provider);
        Assert.Equal(1, emailDelivery.RecordedWebhookCount);
    }

    [Fact]
    public void EmailitWebhookWithConfiguredSecretRequiresMatchingHeader()
    {
        using JsonDocument payload = JsonDocument.Parse("""{"event":"delivered"}""");
        var emailDelivery = new FakeEmailDeliveryService();
        IdentityController controller = BuildController(new Dictionary<string, string?>
        {
            ["ASPNETCORE_ENVIRONMENT"] = "Production",
            ["IDENTITY_EMAILIT_WEBHOOK_SECRET"] = "expected-secret"
        }, emailDelivery);
        controller.ControllerContext.HttpContext.Request.Headers["X-Emailit-Webhook-Secret"] = "expected-secret";

        ActionResult<IdentityEmailWebhookAckResponse> result = controller.ReceiveEmailitWebhook(payload.RootElement);

        OkObjectResult ok = Assert.IsAssignableFrom<OkObjectResult>(result.Result);
        var response = Assert.IsAssignableFrom<IdentityEmailWebhookAckResponse>(ok.Value);
        Assert.Equal("accepted", response.Status);
        Assert.Equal(1, emailDelivery.RecordedWebhookCount);
    }

    private static IdentityController BuildController(
        IReadOnlyDictionary<string, string?> settings,
        FakeEmailDeliveryService? emailDelivery = null)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(settings)
            .Build();
        var controller = new IdentityController(
            new FakeIdentityAccessService(),
            emailDelivery ?? new FakeEmailDeliveryService(),
            configuration);
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        return controller;
    }

    private sealed class FakeIdentityAccessService : IIdentityAccessService
    {
        public IdentitySessionIssueResponse IssueSession(IdentitySessionIssueRequest request) => throw new NotSupportedException();

        public EmailAuthStartResponse StartEmailEntry(EmailAuthStartRequest request) => throw new NotSupportedException();

        public IdentitySessionIssueResponse CompleteEmailEntry(EmailAuthCompleteRequest request) => throw new NotSupportedException();

        public IdentitySessionRevokeResponse RevokeSession(IdentitySessionRevokeRequest request) => throw new NotSupportedException();

        public IdentitySubjectResponse SetRoles(string subjectId, IdentityRoleSetRequest request) => throw new NotSupportedException();

        public IdentitySubjectResponse? GetSubject(string subjectId) => throw new NotSupportedException();

        public IdentityIntrospectionResponse Introspect(IdentityIntrospectionRequest request) => throw new NotSupportedException();
    }

    private sealed class FakeEmailDeliveryService : IIdentityEmailDeliveryService
    {
        public int RecordedWebhookCount { get; private set; }

        public IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
            => throw new NotSupportedException();

        public IdentityEmailDeliveryStatusResponse GetStatus()
            => throw new NotSupportedException();

        public IdentityEmailWebhookAckResponse RecordEmailitWebhook(JsonElement payload)
        {
            RecordedWebhookCount++;
            return new IdentityEmailWebhookAckResponse(
                Provider: "Emailit",
                Status: "accepted",
                RecordedEvents: 1,
                ReceivedAtUtc: DateTimeOffset.UtcNow);
        }
    }
}
