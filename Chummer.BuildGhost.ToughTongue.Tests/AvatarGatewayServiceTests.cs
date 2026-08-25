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
    public async Task Idempotency_digest_includes_typed_intent_and_rejects_a_changed_intent()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);
        AvatarRuleQuestionRequest first = Question(context.ContextRef, "nonce-1", "idem-rule-1");
        await service.ResolveRuleAsync(first, CancellationToken.None);

        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> conflict =
            await service.ResolveRuleAsync(
                first with
                {
                    Nonce = "nonce-2",
                    Intent = SupportedIntent() with { IntentVersion = 2 }
                },
                CancellationToken.None);

        Assert.AreEqual(AvatarGatewayCallStatus.IdempotencyConflict, conflict.Status);
        Assert.AreEqual(1, authority.Calls);
    }

    [TestMethod]
    public async Task Missing_or_unsupported_typed_intent_is_cached_unresolved_without_calling_authority()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);
        AvatarRuleQuestionRequest missing = Question(context.ContextRef, "nonce-1", "idem-missing") with
        {
            Intent = null
        };

        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> missingResult =
            await service.ResolveRuleAsync(missing, CancellationToken.None);
        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> missingReplay =
            await service.ResolveRuleAsync(missing with { Nonce = "nonce-2" }, CancellationToken.None);
        AvatarRuleQuestionRequest unsupported = Question(context.ContextRef, "nonce-3", "idem-unsupported") with
        {
            Intent = SupportedIntent() with { IntentVersion = 2 }
        };
        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> unsupportedResult =
            await service.ResolveRuleAsync(unsupported, CancellationToken.None);

        Assert.AreEqual(AvatarGatewayStatuses.Unresolved, missingResult.Value?.Status);
        Assert.AreEqual(AvatarRuleIntentAdapter.MissingReason, missingResult.Value?.UncertaintyReason);
        Assert.AreEqual(AvatarGatewayCallStatus.IdempotentReplay, missingReplay.Status);
        Assert.AreSame(missingResult.Value, missingReplay.Value);
        Assert.AreEqual(AvatarGatewayStatuses.Unresolved, unsupportedResult.Value?.Status);
        Assert.AreEqual(AvatarRuleIntentAdapter.UnsupportedReason, unsupportedResult.Value?.UncertaintyReason);
        Assert.AreEqual(0, authority.Calls);
    }

    [TestMethod]
    public async Task Malformed_typed_argument_fails_before_nonce_or_idempotency_is_consumed()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);
        AvatarRuleQuestionRequest valid = Question(context.ContextRef, "nonce-1", "idem-rule-1");
        AvatarRuleQuestionRequest malformed = valid with
        {
            Intent = SupportedIntent() with
            {
                Arguments =
                [
                    new AvatarRuleIntentArgument(
                        "mode",
                        AvatarRuleAuthorityArgumentKinds.Boolean,
                        IdentifierValue: "invented",
                        BooleanValue: true)
                ]
            }
        };

        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> rejected =
            await service.ResolveRuleAsync(malformed, CancellationToken.None);
        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> corrected =
            await service.ResolveRuleAsync(valid, CancellationToken.None);

        Assert.AreEqual(AvatarGatewayCallStatus.InvalidRequest, rejected.Status);
        Assert.IsNull(rejected.Value);
        Assert.IsTrue(corrected.Succeeded);
        Assert.AreEqual(1, authority.Calls);
    }

    [TestMethod]
    public async Task Supported_intent_builds_exact_core_request_without_conversation_text()
    {
        ManualTimeProvider time = new(new DateTimeOffset(2026, 8, 25, 6, 0, 0, TimeSpan.Zero));
        FakeAuthority authority = new();
        AvatarGatewayService service = CreateService(time, authority);
        AvatarSessionContextProjection context = Mint(service);

        await service.ResolveRuleAsync(
            Question(context.ContextRef, "nonce-1", "idem-rule-1"),
            CancellationToken.None);

        AvatarRuleAuthorityInvocation invocation = authority.LastInvocation!;
        Assert.AreEqual(AvatarGatewayContractVersions.RuleAuthorityV1, invocation.Request.ContractVersion);
        Assert.AreEqual(AvatarRuleIntentAdapter.SupportedIntentId, invocation.Request.IntentId);
        Assert.AreEqual(AvatarRuleIntentAdapter.SupportedCapabilityId, invocation.Request.CapabilityId);
        Assert.AreEqual("session-actions", invocation.Request.SubjectId);
        Assert.IsEmpty(invocation.Request.Arguments);
        Assert.AreEqual("sr6", invocation.Request.ExpectedBinding.RulesetId);
        Assert.AreEqual("official.sr6.core", invocation.Request.ExpectedBinding.ProfileId);
        Assert.AreEqual(DigestA, invocation.Request.ExpectedBinding.SourceDigest);
        Assert.AreEqual(DigestA, invocation.Request.ExpectedBinding.SourcebookFingerprint);
        Assert.AreEqual(DigestA, invocation.Request.ExpectedBinding.CustomDataFingerprint);
        Assert.AreEqual(DigestA, invocation.Request.ExpectedBinding.GmPolicyFingerprint);
        Assert.AreEqual("workspace-1", invocation.WorkspaceId);
        Assert.ThrowsExactly<NotSupportedException>(() =>
            ((IList<AvatarRuleAuthorityArgument>)invocation.Request.Arguments).Add(
                new AvatarRuleAuthorityArgument("invented", AvatarRuleAuthorityArgumentKinds.Boolean, BooleanValue: true)));
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
            "sr6",
            AvatarRuleIntentAdapter.SupportedRulesetProfileId,
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
            "session-actions",
            SupportedIntent());

    private static AvatarRuleIntentSelection SupportedIntent() => new(
        AvatarGatewayContractVersions.RuleIntentV1,
        AvatarRuleIntentAdapter.SupportedIntentId,
        AvatarRuleIntentAdapter.SupportedIntentVersion,
        AvatarRuleIntentAdapter.SupportedCapabilityId,
        AvatarRuleIntentAdapter.SupportedInvocationKind,
        []);

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

        public AvatarRuleAuthorityInvocation? LastInvocation { get; private set; }

        public AvatarRuleAuthorityException? Failure { get; init; }

        public Task<AvatarRuleAnswerEnvelope> ResolveAsync(
            AvatarRuleAuthorityInvocation invocation,
            CancellationToken cancellationToken)
        {
            Calls++;
            LastInvocation = invocation;
            if (Failure is not null) throw Failure;
            AvatarSourceAnchor anchor = new(
                "anchor-recoil",
                "sr6-core",
                "Shadowrun Sixth World Core Rulebook",
                41,
                "session.quick-actions",
                "chummer://sources/sr6-core?page=41");
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
                invocation.Request.ExpectedBinding.WorkspaceRevision,
                invocation.Request.ExpectedBinding.RuntimeFingerprint,
                invocation.Request.ExpectedBinding.SourceDigest,
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
            AvatarRuleAuthorityInvocation invocation,
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
