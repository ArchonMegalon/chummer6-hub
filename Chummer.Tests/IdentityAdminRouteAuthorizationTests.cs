using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Controllers;
using Chummer.Run.Identity.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class IdentityAdminRouteAuthorizationTests
{
    private const string ConfiguredKey = "test-admin-key-a";

    [Fact]
    public void IssueSessionAcceptsEqualAdminKey()
    {
        var identity = new FakeIdentityAccessService();
        IdentityController controller = BuildController(identity, ConfiguredKey, ConfiguredKey);

        ActionResult<IdentitySessionIssueResponse> result = controller.IssueSession(BuildRequest());

        Assert.IsType<CreatedAtActionResult>(result.Result);
        Assert.Equal(1, identity.IssueSessionCallCount);
    }

    [Fact]
    public void IssueSessionRejectsUnequalSameLengthAdminKeyBeforeCallingService()
    {
        var identity = new FakeIdentityAccessService();
        IdentityController controller = BuildController(identity, ConfiguredKey, "test-admin-key-b");

        ActionResult<IdentitySessionIssueResponse> result = controller.IssueSession(BuildRequest());

        AssertForbiddenWithoutServiceCall(result, identity);
    }

    [Fact]
    public void IssueSessionRejectsUnequalLengthAdminKeyBeforeCallingService()
    {
        var identity = new FakeIdentityAccessService();
        IdentityController controller = BuildController(identity, ConfiguredKey, "short-key");

        ActionResult<IdentitySessionIssueResponse> result = controller.IssueSession(BuildRequest());

        AssertForbiddenWithoutServiceCall(result, identity);
    }

    [Fact]
    public void IssueSessionRejectsMissingConfiguredAdminKeyBeforeCallingService()
    {
        var identity = new FakeIdentityAccessService();
        IdentityController controller = BuildController(identity, configuredKey: null, suppliedKey: ConfiguredKey);

        ActionResult<IdentitySessionIssueResponse> result = controller.IssueSession(BuildRequest());

        AssertForbiddenWithoutServiceCall(result, identity);
    }

    [Fact]
    public void IssueSessionRejectsMissingAdminKeyHeaderBeforeCallingService()
    {
        var identity = new FakeIdentityAccessService();
        IdentityController controller = BuildController(identity, ConfiguredKey, suppliedKey: null);

        ActionResult<IdentitySessionIssueResponse> result = controller.IssueSession(BuildRequest());

        AssertForbiddenWithoutServiceCall(result, identity);
    }

    private static IdentitySessionIssueRequest BuildRequest()
        => new("subject.test", "Test Subject", null);

    private static IdentityController BuildController(
        FakeIdentityAccessService identity,
        string? configuredKey,
        string? suppliedKey)
    {
        var settings = new Dictionary<string, string?>();
        if (configuredKey is not null)
        {
            settings["IDENTITY_ADMIN_KEY"] = configuredKey;
        }

        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(settings)
            .Build();
        var controller = new IdentityController(
            identity,
            new FakeEmailDeliveryService(),
            configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        if (suppliedKey is not null)
        {
            controller.ControllerContext.HttpContext.Request.Headers["X-Identity-Admin-Key"] = suppliedKey;
        }

        return controller;
    }

    private static void AssertForbiddenWithoutServiceCall(
        ActionResult<IdentitySessionIssueResponse> result,
        FakeIdentityAccessService identity)
    {
        ObjectResult problem = Assert.IsAssignableFrom<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status403Forbidden, problem.StatusCode);
        Assert.Equal(0, identity.IssueSessionCallCount);
    }

    private sealed class FakeIdentityAccessService : IIdentityAccessService
    {
        public int IssueSessionCallCount { get; private set; }

        public IdentitySessionIssueResponse IssueSession(IdentitySessionIssueRequest request)
        {
            IssueSessionCallCount++;
            var now = DateTimeOffset.UtcNow;
            return new IdentitySessionIssueResponse(
                SessionId: "session.test",
                SubjectId: request.SubjectId,
                DisplayName: request.DisplayName ?? request.SubjectId,
                Email: request.Email,
                Roles: Array.Empty<string>(),
                AccessToken: "test-access-token",
                RefreshToken: "test-refresh-token",
                IssuedAtUtc: now,
                ExpiresAtUtc: now.AddMinutes(5));
        }

        public EmailAuthStartResponse StartEmailEntry(EmailAuthStartRequest request) => throw new NotSupportedException();

        public IdentitySessionIssueResponse CompleteEmailEntry(EmailAuthCompleteRequest request) => throw new NotSupportedException();

        public IdentitySessionRevokeResponse RevokeSession(IdentitySessionRevokeRequest request) => throw new NotSupportedException();

        public IdentitySubjectResponse SetRoles(string subjectId, IdentityRoleSetRequest request) => throw new NotSupportedException();

        public IdentitySubjectResponse? GetSubject(string subjectId) => throw new NotSupportedException();

        public IdentityIntrospectionResponse Introspect(IdentityIntrospectionRequest request) => throw new NotSupportedException();
    }

    private sealed class FakeEmailDeliveryService : IIdentityEmailDeliveryService
    {
        public IdentityEmailDeliveryResult DeliverMagicLink(
            string email,
            string displayName,
            string ticketId,
            string? nextPath,
            DateTimeOffset expiresAtUtc)
            => throw new NotSupportedException();

        public IdentityEmailDeliveryStatusResponse GetStatus() => throw new NotSupportedException();

        public void RecordStartGuardrailBlock(string email, string deliveryMode, string previewNote)
            => throw new NotSupportedException();

        public IdentityEmailWebhookAckResponse RecordEmailitWebhook(System.Text.Json.JsonElement payload)
            => throw new NotSupportedException();
    }
}
