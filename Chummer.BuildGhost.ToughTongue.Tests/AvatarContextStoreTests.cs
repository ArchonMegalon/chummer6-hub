using System.Collections.Concurrent;
using System.Text.RegularExpressions;
using Chummer.Run.AI.Services.Avatar;
using Chummer.Run.Contracts.Avatar;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class AvatarContextStoreTests
{
    private const string DigestA = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string DigestB = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    private static readonly DateTimeOffset Start = new(2026, 8, 25, 0, 0, 0, TimeSpan.Zero);

    [TestMethod]
    public void Scope_allowlist_is_not_backed_by_a_mutable_set()
    {
        ISet<string> setView = (ISet<string>)AvatarGatewayScopes.Allowed;
        Assert.ThrowsExactly<NotSupportedException>(() => setView.Add("character:write"));
        CollectionAssert.DoesNotContain(AvatarGatewayScopes.Allowed.ToArray(), "character:write");
    }

    [TestMethod]
    public void Mint_creates_a_cryptographic_base64url_reference_and_immutable_complete_snapshot()
    {
        ManualTimeProvider time = new(Start);
        AvatarContextStore store = new(time);

        AvatarContextMintResult result = store.Mint(CreateMintRequest());

        Assert.IsTrue(result.Succeeded);
        Assert.IsNotNull(result.Context);
        AvatarContextSnapshot context = result.Context;
        Assert.AreEqual(43, context.ContextRef.Length);
        Assert.IsTrue(Regex.IsMatch(context.ContextRef, "\\A[A-Za-z0-9_-]{43}\\z"));
        Assert.HasCount(32, DecodeBase64Url(context.ContextRef));
        Assert.AreEqual("owner-1", context.OwnerId);
        Assert.AreEqual("workspace-1", context.WorkspaceId);
        Assert.AreEqual(41L, context.WorkspaceRevision);
        Assert.AreEqual("character-1", context.CharacterId);
        Assert.AreEqual("campaign-1", context.CampaignId);
        Assert.AreEqual("sr6-core", context.RulesetId);
        Assert.AreEqual(DigestA, context.RuntimeFingerprint);
        Assert.AreEqual(DigestA, context.SourceDigest);
        Assert.AreEqual(DigestA, context.SourcebookFingerprint);
        Assert.AreEqual(DigestA, context.CustomDataFingerprint);
        Assert.AreEqual(DigestA, context.GmPolicyFingerprint);
        Assert.AreEqual("scenario-private", context.ScenarioId);
        Assert.AreEqual("Rook", context.DisplayName);
        Assert.AreEqual("en-US", context.Locale);
        Assert.AreEqual("career", context.CreationState);
        CollectionAssert.AreEqual(
            new[] { AvatarGatewayScopes.RulesRead, AvatarGatewayScopes.CharacterRead },
            context.Scopes.ToArray());
        Assert.AreEqual(Start, context.CreatedAt);
        Assert.AreEqual(Start.AddMinutes(5), context.ExpiresAt);
        Assert.IsNull(context.BoundSessionId);
        Assert.ThrowsExactly<NotSupportedException>(() =>
            ((IList<string>)context.Scopes).Add(AvatarGatewayScopes.BuildAnalyze));
    }

    [TestMethod]
    public void Mint_rejects_invalid_contract_ids_fingerprints_locale_scopes_and_ttl_without_retaining_state()
    {
        AvatarContextMintRequest valid = CreateMintRequest();
        AvatarContextMintRequest[] invalid =
        [
            valid with { ContractName = AvatarGatewayContractVersions.ContextRequestV1 },
            valid with { OwnerId = "owner with space" },
            valid with { OwnerId = "owner/../other" },
            valid with { WorkspaceRevision = -1 },
            valid with { CampaignId = string.Empty },
            valid with { RuntimeFingerprint = $"sha256:{new string('A', 64)}" },
            valid with { SourceDigest = $"sha256:{new string('a', 63)}" },
            valid with { Locale = "en-us" },
            valid with { Locale = "not_a_locale" },
            valid with { DisplayName = "unsafe\nname" },
            valid with { Scopes = new[] { "character:write" } },
            valid with { Scopes = new[] { AvatarGatewayScopes.RulesRead, AvatarGatewayScopes.RulesRead } },
            valid with { Scopes = Array.Empty<string>() },
            valid with { TtlSeconds = 0 },
            valid with { TtlSeconds = AvatarContextStore.MaximumTtlSeconds + 1 }
        ];
        AvatarContextStore store = new(new ManualTimeProvider(Start));

        foreach (AvatarContextMintRequest request in invalid)
        {
            AvatarContextMintResult result = store.Mint(request);
            Assert.AreEqual(AvatarContextStoreStatus.InvalidRequest, result.Status, request.ToString());
            Assert.IsNull(result.Context);
        }

        Assert.AreEqual(0, store.Count);
    }

    [TestMethod]
    public void Authorize_binds_scenario_and_first_successful_session_and_rejects_nonce_replay()
    {
        AvatarContextStore store = new(new ManualTimeProvider(Start));
        string contextRef = Mint(store).ContextRef;

        AvatarContextAuthorizationResult wrongScenario = store.Authorize(
            CreateContextRequest(contextRef, scenarioId: "scenario-other", nonce: "nonce-wrong"),
            DigestA);
        AvatarContextAuthorizationResult first = store.Authorize(
            CreateContextRequest(contextRef, sessionId: "session-a", nonce: "nonce-1", idempotencyKey: "idem-1"),
            DigestA);
        AvatarContextAuthorizationResult wrongSession = store.Authorize(
            CreateContextRequest(contextRef, sessionId: "session-b", nonce: "nonce-2", idempotencyKey: "idem-2"),
            DigestA);
        AvatarContextAuthorizationResult replayedNonce = store.Authorize(
            CreateContextRequest(contextRef, sessionId: "session-a", nonce: "nonce-1", idempotencyKey: "idem-3"),
            DigestA);

        Assert.AreEqual(AvatarContextStoreStatus.ScenarioMismatch, wrongScenario.Status);
        Assert.AreEqual(AvatarContextStoreStatus.Granted, first.Status);
        Assert.AreEqual("session-a", first.Context?.BoundSessionId);
        Assert.AreEqual(AvatarContextStoreStatus.SessionMismatch, wrongSession.Status);
        Assert.AreEqual(AvatarContextStoreStatus.NonceReplay, replayedNonce.Status);
        Assert.IsNull(wrongScenario.Context);
        Assert.IsNull(wrongSession.Context);
        Assert.IsNull(replayedNonce.Context);
    }

    [TestMethod]
    public void Idempotency_replay_is_distinct_and_payload_conflict_consumes_its_nonce_fail_closed()
    {
        AvatarContextStore store = new(
            new ManualTimeProvider(Start),
            new AvatarContextStoreOptions
            {
                MaxIdempotencyEntriesPerContext = 2,
                MaxNoncesPerContext = 8,
                MaxRequestsPerWindow = 8
            });
        string contextRef = Mint(store).ContextRef;

        AvatarContextAuthorizationResult first = store.Authorize(
            CreateContextRequest(contextRef, nonce: "nonce-1", idempotencyKey: "idem-shared"),
            DigestA);
        AvatarContextAuthorizationResult replay = store.Authorize(
            CreateContextRequest(contextRef, nonce: "nonce-2", idempotencyKey: "idem-shared"),
            DigestA);
        AvatarContextAuthorizationResult conflict = store.Authorize(
            CreateContextRequest(contextRef, nonce: "nonce-3", idempotencyKey: "idem-shared"),
            DigestB);
        AvatarContextAuthorizationResult consumedConflictNonce = store.Authorize(
            CreateContextRequest(contextRef, nonce: "nonce-3", idempotencyKey: "idem-other"),
            DigestA);

        Assert.AreEqual(AvatarContextStoreStatus.Granted, first.Status);
        Assert.AreEqual(AvatarContextStoreStatus.IdempotentReplay, replay.Status);
        Assert.IsTrue(replay.Succeeded);
        Assert.IsTrue(replay.IsIdempotentReplay);
        Assert.AreEqual(AvatarContextStoreStatus.IdempotencyConflict, conflict.Status);
        Assert.AreEqual(AvatarContextStoreStatus.NonceReplay, consumedConflictNonce.Status);
    }

    [TestMethod]
    public void Idempotency_and_nonce_capacities_stop_without_evicting_prior_security_metadata()
    {
        AvatarContextStore store = new(
            new ManualTimeProvider(Start),
            new AvatarContextStoreOptions
            {
                MaxIdempotencyEntriesPerContext = 1,
                MaxNoncesPerContext = 3,
                MaxRequestsPerWindow = 8
            });
        string contextRef = Mint(store).ContextRef;

        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-1", idempotencyKey: "idem-1"), DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.CapacityExceeded,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-2", idempotencyKey: "idem-2"), DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.IdempotentReplay,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-3", idempotencyKey: "idem-1"), DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.CapacityExceeded,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-4", idempotencyKey: "idem-1"), DigestA).Status);
    }

    [TestMethod]
    public void Sliding_window_rate_limit_is_bounded_and_reopens_only_after_the_window()
    {
        ManualTimeProvider time = new(Start);
        AvatarContextStore store = new(
            time,
            new AvatarContextStoreOptions
            {
                MaxRequestsPerWindow = 2,
                RateLimitWindow = TimeSpan.FromMinutes(1)
            });
        string contextRef = Mint(store).ContextRef;

        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-1", idempotencyKey: "idem-1"), DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-2", idempotencyKey: "idem-2"), DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.RateLimited,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-3", idempotencyKey: "idem-3"), DigestA).Status);

        time.Advance(TimeSpan.FromMinutes(1));

        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(CreateContextRequest(contextRef, nonce: "nonce-3", idempotencyKey: "idem-3"), DigestA).Status);
    }

    [TestMethod]
    public void Expiry_removes_all_per_context_security_metadata_instead_of_leaving_checkpoints()
    {
        ManualTimeProvider time = new(Start);
        AvatarContextStore store = new(time);
        AvatarContextSnapshot context = Mint(store, CreateMintRequest() with { TtlSeconds = 1 });
        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(CreateContextRequest(context.ContextRef), DigestA).Status);

        time.Advance(TimeSpan.FromSeconds(1));
        AvatarContextAuthorizationResult expired = store.Authorize(
            CreateContextRequest(context.ContextRef, nonce: "nonce-after-expiry"),
            DigestA);

        Assert.AreEqual(AvatarContextStoreStatus.Expired, expired.Status);
        Assert.AreEqual(0, store.Count);
        Assert.AreEqual(0, store.SweepExpired());
    }

    [TestMethod]
    public void Revocation_is_exact_context_and_owner_workspace_scoped_and_returns_only_a_digest()
    {
        AvatarContextStore store = new(new ManualTimeProvider(Start));
        AvatarContextSnapshot first = Mint(store, CreateMintRequest() with { ScenarioId = "scenario-one" });
        AvatarContextSnapshot second = Mint(store, CreateMintRequest() with { CharacterId = "character-2", ScenarioId = "scenario-two" });
        AvatarContextSnapshot other = Mint(store, CreateMintRequest() with { WorkspaceId = "workspace-other" });

        AvatarContextRevocationResult result = store.Revoke(new AvatarContextRevocationRequest(
            AvatarGatewayContractVersions.RevocationV1,
            first.ContextRef,
            "owner-1",
            "workspace-1"));

        Assert.IsTrue(result.Succeeded);
        Assert.HasCount(1, result.Receipts);
        Assert.IsTrue(result.Receipts.All(receipt => receipt.Revoked));
        Assert.IsTrue(result.Receipts.All(receipt => Regex.IsMatch(
            receipt.ContextRefDigest,
            "\\Asha256:[0-9a-f]{64}\\z")));
        string receiptText = string.Join('|', result.Receipts.Select(receipt => receipt.ContextRefDigest));
        Assert.IsFalse(receiptText.Contains(first.ContextRef, StringComparison.Ordinal));
        Assert.AreEqual(2, store.Count);
        Assert.AreEqual(
            AvatarContextStoreStatus.NotFound,
            store.Authorize(CreateContextRequest(first.ContextRef), DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(
                CreateContextRequest(second.ContextRef, scenarioId: "scenario-two"),
                DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(CreateContextRequest(other.ContextRef), DigestA).Status);

        AvatarContextRevocationResult wrongOwner = store.Revoke(new AvatarContextRevocationRequest(
            AvatarGatewayContractVersions.RevocationV1,
            second.ContextRef,
            "owner-other",
            "workspace-1"));
        Assert.AreEqual(AvatarContextStoreStatus.NotFound, wrongOwner.Status);
        Assert.AreEqual(2, store.Count);
    }

    [TestMethod]
    public void Global_and_owner_workspace_capacities_fail_closed_without_evicting_live_contexts()
    {
        AvatarContextStore store = new(
            new ManualTimeProvider(Start),
            new AvatarContextStoreOptions
            {
                MaxContexts = 2,
                MaxContextsPerOwnerWorkspace = 1
            });

        AvatarContextMintResult first = store.Mint(CreateMintRequest());
        AvatarContextMintResult sameBinding = store.Mint(CreateMintRequest() with { CharacterId = "character-2" });
        AvatarContextMintResult otherBinding = store.Mint(CreateMintRequest() with { WorkspaceId = "workspace-2" });
        AvatarContextMintResult globalOverflow = store.Mint(CreateMintRequest() with { WorkspaceId = "workspace-3" });

        Assert.AreEqual(AvatarContextStoreStatus.Created, first.Status);
        Assert.AreEqual(AvatarContextStoreStatus.CapacityExceeded, sameBinding.Status);
        Assert.AreEqual(AvatarContextStoreStatus.Created, otherBinding.Status);
        Assert.AreEqual(AvatarContextStoreStatus.CapacityExceeded, globalOverflow.Status);
        Assert.AreEqual(2, store.Count);
    }

    [TestMethod]
    public void Concurrent_first_authorizations_atomically_bind_exactly_one_session()
    {
        AvatarContextStore store = new(new ManualTimeProvider(Start));
        string contextRef = Mint(store).ContextRef;
        ConcurrentBag<AvatarContextAuthorizationResult> results = new();

        Parallel.ForEach(new[] { "session-a", "session-b" }, sessionId =>
        {
            results.Add(store.Authorize(
                CreateContextRequest(
                    contextRef,
                    sessionId,
                    $"nonce-{sessionId}",
                    $"idem-{sessionId}"),
                DigestA));
        });

        Assert.AreEqual(1, results.Count(result => result.Status == AvatarContextStoreStatus.Granted));
        Assert.AreEqual(1, results.Count(result => result.Status == AvatarContextStoreStatus.SessionMismatch));
        Assert.AreEqual(1, results.Count(result => result.Context is not null));
    }

    [TestMethod]
    public void Rule_question_contract_and_payload_digest_are_validated_before_state_is_consumed()
    {
        AvatarContextStore store = new(new ManualTimeProvider(Start));
        string contextRef = Mint(store).ContextRef;
        AvatarRuleQuestionRequest valid = new(
            AvatarGatewayContractVersions.RuleQuestionV1,
            contextRef,
            "scenario-private",
            "session-1",
            "nonce-1",
            "idem-1",
            "How much karma remains?",
            "attribute-body");

        Assert.AreEqual(
            AvatarContextStoreStatus.InvalidRequest,
            store.Authorize(valid with { ContractName = AvatarGatewayContractVersions.ContextRequestV1 }, DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.InvalidRequest,
            store.Authorize(valid with { Question = " \t" }, DigestA).Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.InvalidRequest,
            store.Authorize(valid, $"sha256:{new string('A', 64)}").Status);
        Assert.AreEqual(
            AvatarContextStoreStatus.Granted,
            store.Authorize(valid, DigestA).Status);
    }

    [TestMethod]
    public void Clock_rollback_and_unreadable_time_fail_closed_without_exposing_a_snapshot()
    {
        ManualTimeProvider time = new(Start);
        AvatarContextStore store = new(time);
        string contextRef = Mint(store).ContextRef;
        time.Set(Start.AddSeconds(-1));

        AvatarContextAuthorizationResult rollback = store.Authorize(
            CreateContextRequest(contextRef),
            DigestA);

        Assert.AreEqual(AvatarContextStoreStatus.InvalidState, rollback.Status);
        Assert.IsNull(rollback.Context);
        time.Set(Start.AddSeconds(1));
        time.ThrowOnRead = true;
        AvatarContextAuthorizationResult unreadable = store.Authorize(
            CreateContextRequest(contextRef, nonce: "nonce-2", idempotencyKey: "idem-2"),
            DigestA);
        Assert.AreEqual(AvatarContextStoreStatus.InvalidState, unreadable.Status);
        Assert.IsNull(unreadable.Context);
    }

    private static AvatarContextSnapshot Mint(
        AvatarContextStore store,
        AvatarContextMintRequest? request = null)
    {
        AvatarContextMintResult result = store.Mint(request ?? CreateMintRequest());
        Assert.AreEqual(AvatarContextStoreStatus.Created, result.Status);
        Assert.IsNotNull(result.Context);
        return result.Context;
    }

    private static AvatarContextMintRequest CreateMintRequest() => new(
        AvatarGatewayContractVersions.SessionContextV1,
        "owner-1",
        "workspace-1",
        41,
        "character-1",
        "campaign-1",
        "sr6-core",
        DigestA,
        DigestA,
        DigestA,
        DigestA,
        DigestA,
        "scenario-private",
        "Rook",
        "en-US",
        "career",
        new[] { AvatarGatewayScopes.RulesRead, AvatarGatewayScopes.CharacterRead },
        300);

    private static AvatarContextRequest CreateContextRequest(
        string contextRef,
        string sessionId = "session-1",
        string nonce = "nonce-1",
        string idempotencyKey = "idem-1",
        string scenarioId = "scenario-private") => new(
            AvatarGatewayContractVersions.ContextRequestV1,
            contextRef,
            scenarioId,
            sessionId,
            nonce,
            idempotencyKey);

    private static byte[] DecodeBase64Url(string value)
    {
        string standard = value.Replace('-', '+').Replace('_', '/') + "=";
        return Convert.FromBase64String(standard);
    }

    private sealed class ManualTimeProvider(DateTimeOffset utcNow) : TimeProvider
    {
        private readonly object _gate = new();
        private DateTimeOffset _utcNow = utcNow;

        public bool ThrowOnRead { get; set; }

        public override DateTimeOffset GetUtcNow()
        {
            lock (_gate)
            {
                if (ThrowOnRead)
                {
                    throw new InvalidOperationException("clock-unreadable");
                }

                return _utcNow;
            }
        }

        public void Advance(TimeSpan amount)
        {
            lock (_gate)
            {
                _utcNow += amount;
            }
        }

        public void Set(DateTimeOffset value)
        {
            lock (_gate)
            {
                _utcNow = value;
            }
        }
    }
}
