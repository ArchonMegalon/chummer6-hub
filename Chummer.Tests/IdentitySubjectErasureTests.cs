using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Controllers;
using Chummer.Run.Identity.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class IdentitySubjectErasureTests
{
    [Fact]
    public void EraseSubject_revokes_all_sessions_removes_subject_and_is_idempotent()
    {
        string stateRoot = Path.Combine(Path.GetTempPath(), $"chummer-identity-erasure-{Guid.NewGuid():N}");
        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_STATE_ROOT"] = stateRoot
                })
                .Build();
            var service = new IdentityAccessService(
                configuration,
                NullLogger<IdentityAccessService>.Instance);
            IdentitySessionIssueResponse first = service.IssueSession(new(
                "subject.erase-me",
                "Erase Me",
                "erase@example.invalid"));
            IdentitySessionIssueResponse second = service.IssueSession(new(
                "subject.erase-me",
                "Erase Me",
                "erase@example.invalid"));

            IdentitySubjectErasureResponse erased = service.EraseSubject("subject.erase-me");

            Assert.True(erased.Erased);
            Assert.Equal(2, erased.RevokedSessionCount);
            Assert.Equal(64, erased.SubjectKeySha256.Length);
            Assert.Null(service.GetSubject("subject.erase-me"));
            Assert.False(service.Introspect(new(first.AccessToken)).Active);
            Assert.False(service.Introspect(new(second.AccessToken)).Active);

            IdentitySubjectErasureResponse repeated = service.EraseSubject("subject.erase-me");
            Assert.False(repeated.Erased);
            Assert.Equal(erased.SubjectKeySha256, repeated.SubjectKeySha256);
            Assert.Equal(0, repeated.RevokedSessionCount);
        }
        finally
        {
            if (Directory.Exists(stateRoot))
            {
                Directory.Delete(stateRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void EraseSubject_controller_requires_the_internal_admin_key()
    {
        var service = new RecordingIdentityAccessService();
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["IDENTITY_ADMIN_KEY"] = "expected-admin-key"
            })
            .Build();
        var controller = new IdentityController(
            service,
            new NoopIdentityEmailDeliveryService(),
            configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<IdentitySubjectErasureResponse> denied = controller.EraseSubject("subject.private");

        Assert.IsType<ObjectResult>(denied.Result);
        Assert.Equal(0, service.EraseCallCount);

        controller.Request.Headers["X-Identity-Admin-Key"] = "expected-admin-key";
        ActionResult<IdentitySubjectErasureResponse> accepted = controller.EraseSubject("subject.private");
        Assert.IsType<OkObjectResult>(accepted.Result);
        Assert.Equal(1, service.EraseCallCount);
    }

    private sealed class RecordingIdentityAccessService : IIdentityAccessService
    {
        public int EraseCallCount { get; private set; }

        public IdentitySubjectErasureResponse EraseSubject(string subjectId)
        {
            EraseCallCount++;
            return new(true, new string('a', 64), 1, 0, DateTimeOffset.UtcNow);
        }

        public IdentitySessionIssueResponse IssueSession(IdentitySessionIssueRequest request) => throw new NotSupportedException();
        public EmailAuthStartResponse StartEmailEntry(EmailAuthStartRequest request) => throw new NotSupportedException();
        public IdentitySessionIssueResponse CompleteEmailEntry(EmailAuthCompleteRequest request) => throw new NotSupportedException();
        public IdentitySessionRevokeResponse RevokeSession(IdentitySessionRevokeRequest request) => throw new NotSupportedException();
        public IdentitySubjectResponse SetRoles(string subjectId, IdentityRoleSetRequest request) => throw new NotSupportedException();
        public IdentitySubjectResponse? GetSubject(string subjectId) => throw new NotSupportedException();
        public IdentityIntrospectionResponse Introspect(IdentityIntrospectionRequest request) => throw new NotSupportedException();
    }

    private sealed class NoopIdentityEmailDeliveryService : IIdentityEmailDeliveryService
    {
        public IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
            => throw new NotSupportedException();

        public IdentityEmailDeliveryStatusResponse GetStatus()
            => new([], [], DateTimeOffset.UtcNow);

        public IdentityEmailWebhookAckResponse RecordEmailitWebhook(System.Text.Json.JsonElement payload)
            => throw new NotSupportedException();

        public void RecordStartGuardrailBlock(string email, string deliveryMode, string previewNote)
        {
        }
    }
}
