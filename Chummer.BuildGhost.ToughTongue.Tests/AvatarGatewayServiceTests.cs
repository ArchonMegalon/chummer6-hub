using Chummer.Run.Api.Services.Avatar;
using Chummer.Run.Contracts.Avatar;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class AvatarGatewayServiceTests
{
    private const string DigestA = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    [TestMethod]
    public async Task Rule_retry_uses_new_nonce_and_same_idempotent_answer_without_a_second_authority_call()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);
        AvatarRuleQuestionRequest first = Question(context.ContextRef, "nonce-1", "idem-rule-1");

        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> original =
            await service.ResolveRuleAsync(first, CancellationToken.None);
        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> replay =
            await service.ResolveRuleAsync(first with { Nonce = "nonce-2" }, CancellationToken.None);

        Assert.IsTrue(original.Succeeded);
        Assert.IsTrue(replay.Succeeded);
        Assert.AreEqual(AvatarGatewayCallStatus.Granted, original.Status);
        Assert.AreEqual(AvatarGatewayCallStatus.IdempotentReplay, replay.Status);
        Assert.AreSame(original.Value, replay.Value);
        Assert.AreEqual(1, authority.Calls);
    }

    [TestMethod]
    public async Task Idempotency_key_reuse_with_a_changed_question_fails_before_authority_reexecution()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);
        AvatarRuleQuestionRequest first = Question(context.ContextRef, "nonce-1", "idem-rule-1");
        await service.ResolveRuleAsync(first, CancellationToken.None);

        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> conflict =
            await service.ResolveRuleAsync(
                first with { Nonce = "nonce-2", Question = "Behaupte eine andere Regel." },
                CancellationToken.None);

        Assert.IsFalse(conflict.Succeeded);
        Assert.AreEqual(AvatarGatewayCallStatus.IdempotencyConflict, conflict.Status);
        Assert.AreEqual(1, authority.Calls);
    }

    [TestMethod]
    public async Task Missing_character_read_scope_returns_a_bound_forbidden_envelope_without_authority_call()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(
            service,
            [AvatarGatewayScopes.RulesRead]);

        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> result =
            await service.ResolveRuleAsync(
                Question(context.ContextRef, "nonce-1", "idem-rule-1"),
                CancellationToken.None);

        Assert.IsTrue(result.Succeeded);
        Assert.IsNotNull(result.Value);
        Assert.AreEqual(AvatarGatewayStatuses.Forbidden, result.Value.Status);
        Assert.IsEmpty(result.Value.SourceAnchors);
        Assert.IsEmpty(result.Value.AllowedActions);
        Assert.AreEqual(0, authority.Calls);
    }

    [TestMethod]
    public async Task Authority_failure_is_spoken_only_as_the_validated_safe_unavailable_fallback()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new() { Failure = new AvatarRuleAuthorityException("authority-offline") };
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);

        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> result =
            await service.ResolveRuleAsync(
                Question(context.ContextRef, "nonce-1", "idem-rule-1"),
                CancellationToken.None);

        Assert.IsTrue(result.Succeeded);
        Assert.IsNotNull(result.Value);
        Assert.AreEqual(AvatarGatewayStatuses.Unavailable, result.Value.Status);
        Assert.IsEmpty(result.Value.SourceAnchors);
        Assert.IsEmpty(result.Value.AllowedActions);
        StringAssert.Contains(result.Value.SpokenAnswer, "nicht zuverlässig beantworten");
        Assert.AreEqual(1, authority.Calls);
    }

    [TestMethod]
    public async Task Revocation_cancels_and_fences_an_in_flight_rule_answer_before_return()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        BlockingAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);
        Task<AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>> pending = service.ResolveRuleAsync(
            Question(context.ContextRef, "nonce-1", "idem-rule-1"),
            CancellationToken.None);
        await authority.Started.Task.WaitAsync(TimeSpan.FromSeconds(2));

        AvatarGatewayOperationResult<AvatarContextRevocationReceipt> revoked = service.Revoke(
            new AvatarContextRevocationRequest(
                AvatarGatewayContractVersions.RevocationV1,
                context.ContextRef,
                "owner-1",
                "workspace-1"));
        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> result =
            await pending.WaitAsync(TimeSpan.FromSeconds(2));

        Assert.IsTrue(revoked.Succeeded);
        Assert.IsFalse(result.Succeeded);
        Assert.AreEqual(AvatarGatewayCallStatus.Expired, result.Status);
        Assert.IsNull(result.Value);
        Assert.IsTrue(authority.CancellationObserved);
    }

    [TestMethod]
    public void Full_cache_preserves_validation_status_without_consuming_nonce_or_idempotency_state()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        AvatarContextStore store = new(time);
        AvatarGatewayService service = new(store, new FakeAuthority(), time, maximumCachedOperations: 1);
        AvatarSessionContextProjection context = Mint(service);
        AvatarContextRequest first = ContextRequest(context.ContextRef, "nonce-1", "idem-1");
        Assert.IsTrue(service.GetContext(first).Succeeded);

        AvatarGatewayOperationResult<AvatarSessionContextProjection> malformed = service.GetContext(
            ContextRequest(context.ContextRef, "nonce-2", "idem-2") with { ContractName = "wrong-contract" });
        AvatarGatewayOperationResult<AvatarSessionContextProjection> wrongScenario = service.GetContext(
            ContextRequest(context.ContextRef, "nonce-3", "idem-3") with { ScenarioId = "wrong-scenario" });
        AvatarContextRequest capacityRequest = ContextRequest(context.ContextRef, "nonce-4", "idem-4");
        AvatarGatewayOperationResult<AvatarSessionContextProjection> capacity = service.GetContext(capacityRequest);
        AvatarGatewayOperationResult<AvatarSessionContextProjection> repeatedCapacity = service.GetContext(capacityRequest);

        Assert.AreEqual(AvatarGatewayCallStatus.InvalidRequest, malformed.Status);
        Assert.AreEqual(AvatarGatewayCallStatus.ScenarioMismatch, wrongScenario.Status);
        Assert.AreEqual(AvatarGatewayCallStatus.CapacityExceeded, capacity.Status);
        Assert.AreEqual(AvatarGatewayCallStatus.CapacityExceeded, repeatedCapacity.Status);
    }

    private static AvatarGatewayService CreateService(ManualTimeProvider time, IAvatarRuleAuthorityClient authority)
        => new(new AvatarContextStore(time), authority, time);

    private static AvatarSessionContextProjection Mint(
        AvatarGatewayService service,
        IReadOnlyList<string>? scopes = null)
    {
        AvatarGatewayOperationResult<AvatarSessionContextProjection> result = service.Mint(new AvatarContextMintRequest(
            AvatarGatewayContractVersions.SessionContextV1,
            "owner-1",
            "workspace-1",
            417,
            "character-1",
            "campaign-1",
            "sr5",
            DigestA,
            DigestA,
            DigestA,
            DigestA,
            DigestA,
            "rook-private",
            "Nightshade",
            "de-AT",
            "career",
            scopes ?? [AvatarGatewayScopes.RulesRead, AvatarGatewayScopes.CharacterRead],
            300));
        Assert.IsTrue(result.Succeeded);
        Assert.IsNotNull(result.Value);
        return result.Value;
    }

    private static AvatarRuleQuestionRequest Question(
        string contextRef,
        string nonce,
        string idempotencyKey)
        => new(
            AvatarGatewayContractVersions.RuleQuestionV1,
            contextRef,
            "rook-private",
            "session-1",
            nonce,
            idempotencyKey,
            "Wie berechnet sich mein Rückstoßausgleich?",
            "recoil");

    private static AvatarContextRequest ContextRequest(
        string contextRef,
        string nonce,
        string idempotencyKey)
        => new(
            AvatarGatewayContractVersions.ContextRequestV1,
            contextRef,
            "rook-private",
            "session-1",
            nonce,
            idempotencyKey);

    private sealed class FakeAuthority : IAvatarRuleAuthorityClient
    {
        public int Calls { get; private set; }

        public AvatarRuleAuthorityException? Failure { get; init; }

        public Task<AvatarRuleAnswerEnvelope> ResolveAsync(
            AvatarRuleAuthorityRequest request,
            CancellationToken cancellationToken)
        {
            Calls++;
            if (Failure is not null) throw Failure;
            AvatarSourceAnchor anchor = new(
                "anchor-recoil",
                "sr5-core",
                "Shadowrun 5 Grundregelwerk",
                175,
                "combat.recoil.compensation",
                "chummer://sources/sr5-core?page=175");
            AvatarRuleAnswerEnvelope unsigned = new(
                AvatarGatewayContractVersions.RuleAnswerV1,
                AvatarGatewayStatuses.Resolved,
                "Dein Rückstoßausgleich beträgt drei Punkte.",
                "Rückstoßausgleich: 3.",
                [new AvatarCalculationStep("step-1", "Basis + Ausrüstung", "3", [anchor.AnchorId])],
                [],
                true,
                [anchor],
                [new AvatarAllowedAction("open-rule", AvatarGatewayActionTypes.OpenRuleSource, anchor.LocalSourceRoute, false)],
                request.WorkspaceRevision,
                request.RuntimeFingerprint,
                request.SourceDigest,
                string.Empty,
                null);
            return Task.FromResult(unsigned with { AnswerDigest = AvatarRuleAnswerDigest.Compute(unsigned) });
        }
    }

    private sealed class BlockingAuthority : IAvatarRuleAuthorityClient
    {
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public bool CancellationObserved { get; private set; }

        public async Task<AvatarRuleAnswerEnvelope> ResolveAsync(
            AvatarRuleAuthorityRequest request,
            CancellationToken cancellationToken)
        {
            Started.TrySetResult();
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
                throw new InvalidOperationException("unreachable");
            }
            catch (OperationCanceledException)
            {
                CancellationObserved = true;
                throw;
            }
        }
    }

    private sealed class ManualTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
