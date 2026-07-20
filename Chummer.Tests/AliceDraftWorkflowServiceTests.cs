using System.Net;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.KarmaForge;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class AliceDraftWorkflowServiceTests
{
    [Fact]
    public void Controller_AutoValidatesAntiforgeryTokensForUnsafeRequests()
    {
        Assert.Contains(
            typeof(AliceDraftWorkflowController).GetCustomAttributes(inherit: true),
            static attribute => attribute is AutoValidateAntiforgeryTokenAttribute);
    }

    [Fact]
    public void Lifecycle_RequiresCompareReceiptBeforeApplyAndEmitsPrivateAuditReceipts()
    {
        AliceDraftWorkflowService service = new();
        const string subject = "alice-owner-private-subject";
        AliceDraftProjection draft = service.Create(subject, CreateRequest("create-key-0001"));

        Assert.Equal("draft", draft.State);
        Assert.Equal(1, draft.Version);
        Assert.Equal("body", Assert.Single(draft.ProposedChanges).TraitKey);
        Assert.Equal(6, Assert.Single(draft.ProposedChanges).After);
        Assert.Throws<AliceDraftConflictException>(() => service.Apply(
            subject,
            draft.DraftId,
            new AliceDraftApplyRequest(
                draft.Version,
                new string('a', 64),
                "alice-receipt-" + new string('b', 32),
                "apply-key-0001")));

        AliceDraftProjection compared = service.Compare(
            subject,
            draft.DraftId,
            new AliceDraftCompareRequest(draft.Version, draft.DraftFingerprint, "compare-key-0001"));
        AliceDraftAuditReceipt compareReceipt = Assert.Single(
            compared.AuditReceipts,
            item => string.Equals(item.Action, "compared", StringComparison.Ordinal));

        AliceDraftProjection applied = service.Apply(
            subject,
            draft.DraftId,
            new AliceDraftApplyRequest(
                compared.Version,
                Assert.IsType<string>(compared.ComparisonSha256),
                compareReceipt.ReceiptId,
                "apply-key-0001"));

        Assert.Equal("applied", applied.State);
        Assert.Equal(3, applied.Version);
        Assert.Equal(6, Assert.Single(applied.AppliedTraits!, item => item.Key == "body").Value);
        Assert.Equal(["created", "compared", "applied"], applied.AuditReceipts.Select(static item => item.Action));
        Assert.All(applied.AuditReceipts, receipt =>
        {
            Assert.StartsWith("sha256:", receipt.ActorSubjectSha256, StringComparison.Ordinal);
            Assert.DoesNotContain(subject, receipt.ActorSubjectSha256, StringComparison.Ordinal);
            Assert.Equal(AliceDraftWorkflowService.ReceiptContract, receipt.Contract);
            Assert.Equal("draft_snapshot_only", receipt.MutationScope);
            Assert.Equal("bounded_first_party_draft_not_character_authority", receipt.Authority);
        });
        Assert.Equal("draft_snapshot_only", applied.MutationScope);
        Assert.Equal("bounded_first_party_draft_not_character_authority", applied.Authority);
        Assert.Equal("process_local_non_durable", applied.PersistencePosture);
        Assert.Contains("provider execution", applied.ProviderPosture, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ProposalsAndFingerprints_AreDeterministicAcrossServices()
    {
        AliceDraftCreateRequest request = CreateRequest("deterministic-create-key");

        AliceDraftProjection first = new AliceDraftWorkflowService().Create("subject-a", request);
        AliceDraftProjection second = new AliceDraftWorkflowService().Create("subject-a", request);

        Assert.Equal(first.DraftId, second.DraftId);
        Assert.Equal(first.DraftFingerprint, second.DraftFingerprint);
        Assert.Equal(first.ProposedChanges, second.ProposedChanges);
        Assert.Equal(first.BaselineTraits, second.BaselineTraits);
    }

    [Fact]
    public void SubjectOwnershipAndCreateIdempotency_FailClosedWithoutCrossUserLeakage()
    {
        AliceDraftWorkflowService service = new();
        AliceDraftCreateRequest request = CreateRequest("create-key-owner");
        AliceDraftProjection first = service.Create("owner-subject", request);
        AliceDraftProjection replay = service.Create("owner-subject", request);

        Assert.Equal(first.DraftId, replay.DraftId);
        Assert.Equal(first.DraftFingerprint, replay.DraftFingerprint);
        Assert.Throws<KeyNotFoundException>(() => service.Get("different-subject", first.DraftId));
        Assert.Throws<AliceDraftConflictException>(() => service.Create(
            "owner-subject",
            request with { Objective = "initiative" }));
    }

    [Fact]
    public void DraftCapacity_IsBoundedPerSubjectAndGloballyWhileReplaysRemainAvailable()
    {
        AliceDraftWorkflowService service = new(maxDraftsPerSubject: 1, maxDraftsGlobal: 2);
        AliceDraftCreateRequest firstRequest = CreateRequest("capacity-create-one");
        AliceDraftProjection first = service.Create("subject-one", firstRequest);

        AliceDraftProjection replay = service.Create("subject-one", firstRequest);

        Assert.Equal(first.DraftId, replay.DraftId);
        Assert.Throws<AliceDraftConflictException>(() => service.Create(
            "subject-one",
            CreateRequest("capacity-create-two")));
        _ = service.Discard(
            "subject-one",
            first.DraftId,
            new AliceDraftDiscardRequest(first.Version, "capacity-discard-one"));
        AliceDraftProjection replacement = service.Create(
            "subject-one",
            CreateRequest("capacity-create-two"));
        Assert.Throws<KeyNotFoundException>(() => service.Get("subject-one", first.DraftId));
        Assert.NotEqual(first.DraftId, replacement.DraftId);
        _ = service.Create("subject-two", CreateRequest("capacity-create-three"));
        Assert.Throws<AliceDraftConflictException>(() => service.Create(
            "subject-three",
            CreateRequest("capacity-create-four")));
    }

    [Fact]
    public void TransitionIdempotency_ReplaysExactResultAndRejectsChangedPayload()
    {
        AliceDraftWorkflowService service = new();
        AliceDraftProjection draft = service.Create("owner", CreateRequest("create-idempotency"));
        AliceDraftCompareRequest request = new(draft.Version, draft.DraftFingerprint, "compare-idempotency");

        AliceDraftProjection first = service.Compare("owner", draft.DraftId, request);
        AliceDraftProjection replay = service.Compare("owner", draft.DraftId, request);

        Assert.Same(first, replay);
        Assert.Throws<AliceDraftConflictException>(() => service.Compare(
            "owner",
            draft.DraftId,
            request with { DraftFingerprint = new string('c', 64) }));
    }

    [Fact]
    public void Discard_IsTerminalAndCannotBeApplied()
    {
        AliceDraftWorkflowService service = new();
        AliceDraftProjection draft = service.Create("owner", CreateRequest("create-discard"));
        AliceDraftProjection compared = service.Compare(
            "owner",
            draft.DraftId,
            new AliceDraftCompareRequest(draft.Version, draft.DraftFingerprint, "compare-discard"));
        AliceDraftProjection discarded = service.Discard(
            "owner",
            draft.DraftId,
            new AliceDraftDiscardRequest(compared.Version, "discard-key-0001"));

        Assert.Equal("discarded", discarded.State);
        Assert.Null(discarded.AppliedTraits);
        Assert.Throws<AliceDraftConflictException>(() => service.Apply(
            "owner",
            draft.DraftId,
            new AliceDraftApplyRequest(
                discarded.Version,
                compared.ComparisonSha256!,
                compared.AuditReceipts.Single(item => item.Action == "compared").ReceiptId,
                "apply-discarded")));
    }

    [Fact]
    public async Task ConcurrentApply_AllowsOneTransitionAndRejectsTheStaleWriter()
    {
        AliceDraftWorkflowService service = new();
        AliceDraftProjection draft = service.Create("owner", CreateRequest("create-concurrency"));
        AliceDraftProjection compared = service.Compare(
            "owner",
            draft.DraftId,
            new AliceDraftCompareRequest(draft.Version, draft.DraftFingerprint, "compare-concurrency"));
        AliceDraftAuditReceipt compareReceipt = compared.AuditReceipts.Single(item => item.Action == "compared");

        Task<string>[] attempts =
        [
            ApplyOutcomeAsync("apply-concurrency-a"),
            ApplyOutcomeAsync("apply-concurrency-b")
        ];

        string[] outcomes = await Task.WhenAll(attempts);

        Assert.Equal(1, outcomes.Count(static value => value == "applied"));
        Assert.Equal(1, outcomes.Count(static value => value == "conflict"));

        async Task<string> ApplyOutcomeAsync(string idempotencyKey)
        {
            await Task.Yield();
            try
            {
                return service.Apply(
                    "owner",
                    draft.DraftId,
                    new AliceDraftApplyRequest(
                        compared.Version,
                        compared.ComparisonSha256!,
                        compareReceipt.ReceiptId,
                        idempotencyKey)).State;
            }
            catch (AliceDraftConflictException)
            {
                return "conflict";
            }
        }
    }

    [Fact]
    public async Task Controller_RequiresAuthenticationAndKeepsDraftsSubjectScoped()
    {
        AliceDraftWorkflowService service = new();
        AliceDraftWorkflowController anonymous = CreateController(service, subjectId: "anonymous", token: "local-anonymous-token");
        anonymous.ControllerContext.HttpContext.Request.Headers.Authorization = string.Empty;

        ObjectResult denied = Assert.IsType<ObjectResult>(await anonymous.Create(
            CreateRequest("create-controller-denied"),
            CancellationToken.None));

        Assert.Equal(StatusCodes.Status401Unauthorized, denied.StatusCode);

        AliceDraftWorkflowController owner = CreateController(service, subjectId: "subject-owner", token: "local-owner-token");
        ObjectResult createdResult = Assert.IsType<ObjectResult>(await owner.Create(
            CreateRequest("create-controller-owner"),
            CancellationToken.None));
        AliceDraftProjection created = Assert.IsType<AliceDraftProjection>(createdResult.Value);
        Assert.Equal(StatusCodes.Status201Created, createdResult.StatusCode);

        AliceDraftWorkflowController other = CreateController(service, subjectId: "subject-other", token: "local-other-token");
        ObjectResult hidden = Assert.IsType<ObjectResult>(await other.Get(created.DraftId, CancellationToken.None));

        Assert.Equal(StatusCodes.Status404NotFound, hidden.StatusCode);
    }

    private static AliceDraftCreateRequest CreateRequest(string idempotencyKey)
        => new(
            RunnerId: "runner-001",
            ExpectedRunnerRevision: 7,
            Objective: "survivability",
            CurrentTraits:
            [
                new("reaction", 4),
                new("body", 5),
                new("logic", 3)
            ],
            IdempotencyKey: idempotencyKey);

    private static AliceDraftWorkflowController CreateController(
        AliceDraftWorkflowService service,
        string subjectId,
        string token)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = token,
                ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = subjectId
            })
            .Build();
        HubIdentityClient identity = new(new HttpClient(new RejectNetworkHandler()), configuration);
        var controller = new AliceDraftWorkflowController(identity, service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer " + token;
        return controller;
    }

    private sealed class RejectNetworkHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => throw new InvalidOperationException("unit test must not call a remote identity or provider endpoint.");
    }
}
