using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class ToughTongueBuildGhostAdapterTests
{
    private const string AccountOne = "sha256:1111111111111111111111111111111111111111111111111111111111111111";
    private const string AccountTwo = "sha256:2222222222222222222222222222222222222222222222222222222222222222";
    private const string AccountThree = "sha256:3333333333333333333333333333333333333333333333333333333333333333";

    [TestMethod]
    public async Task Remote_execution_is_disabled_by_default_and_returns_audited_deterministic_fallback()
    {
        FakeTransport transport = new();
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(new Dictionary<string, string?>(), transport);

        ToughTongueBuildGhostResult result = await adapter.ExplainAsync(CreateRequest(), CancellationToken.None);

        Assert.IsTrue(result.UsedDeterministicFallback);
        Assert.AreEqual("remote-disabled", result.OutcomeStatus);
        Assert.AreEqual("Grounded local fallback.", result.SafeText);
        Assert.IsFalse(result.Receipt.RemoteExecutionEnabled);
        Assert.IsFalse(result.Receipt.RemoteAttempted);
        Assert.IsEmpty(transport.Credentials);
    }

    [TestMethod]
    public async Task Three_healthy_slots_rotate_in_order_without_exposing_credentials_in_receipts()
    {
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(RemoteConfiguration(), transport);

        ToughTongueBuildGhostResult first = await adapter.ExplainAsync(CreateRequest("request-1", "idem-1"), CancellationToken.None);
        ToughTongueBuildGhostResult second = await adapter.ExplainAsync(CreateRequest("request-2", "idem-2"), CancellationToken.None);
        ToughTongueBuildGhostResult third = await adapter.ExplainAsync(CreateRequest("request-3", "idem-3"), CancellationToken.None);

        CollectionAssert.AreEqual(new[] { "secret-one", "secret-two", "secret-three" }, transport.Credentials.ToArray());
        CollectionAssert.AreEqual(
            new[] { AccountOne, AccountTwo, AccountThree },
            new[] { first.Receipt.AccountSlotId, second.Receipt.AccountSlotId, third.Receipt.AccountSlotId });
        Assert.IsFalse(JsonSerializer.Serialize(new[] { first.Receipt, second.Receipt, third.Receipt }).Contains("secret-", StringComparison.Ordinal));
        Assert.IsTrue(new[] { first, second, third }.All(static result => !result.UsedDeterministicFallback));
    }

    [TestMethod]
    public async Task Idempotency_cache_prevents_duplicate_provider_spend()
    {
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(RemoteConfiguration(), transport);
        ToughTongueBuildGhostRequest request = CreateRequest("request-idempotent", "same-key");

        ToughTongueBuildGhostResult first = await adapter.ExplainAsync(request, CancellationToken.None);
        ToughTongueBuildGhostResult second = await adapter.ExplainAsync(request, CancellationToken.None);

        Assert.AreSame(first, second);
        Assert.HasCount(1, transport.Credentials);
    }

    [TestMethod]
    public async Task Idempotency_cache_is_scoped_to_the_opaque_owner_binding()
    {
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(RemoteConfiguration(), transport);
        ToughTongueBuildGhostRequest firstOwner = CreateRequest("request-owner", "shared-idempotency");
        ToughTongueBuildGhostRequest secondOwner = firstOwner with
        {
            OwnerScopeHash = $"sha256:{new string('b', 64)}"
        };

        ToughTongueBuildGhostResult first = await adapter.ExplainAsync(firstOwner, CancellationToken.None);
        ToughTongueBuildGhostResult second = await adapter.ExplainAsync(secondOwner, CancellationToken.None);

        Assert.AreNotSame(first, second);
        Assert.HasCount(2, transport.Credentials);
    }

    [TestMethod]
    public async Task Remote_execution_requires_exactly_three_distinct_credentials_and_opaque_account_refs()
    {
        Dictionary<string, string?>[] invalidConfigurations =
        [
            WithSlotConfiguration("secret-one;secret-two", $"{AccountOne};{AccountTwo}"),
            WithSlotConfiguration("secret-one;secret-two;secret-three;secret-four", $"{AccountOne};{AccountTwo};{AccountThree};sha256:{new string('4', 64)}"),
            WithSlotConfiguration("secret-one;secret-one;secret-three", $"{AccountOne};{AccountTwo};{AccountThree}"),
            WithSlotConfiguration("secret-one;secret-two;secret-three", "account-one;account-two;account-three"),
            WithSlotConfiguration("secret-one;secret-two;secret-three", $"{AccountOne};{AccountOne};{AccountThree}")
        ];

        foreach (Dictionary<string, string?> configuration in invalidConfigurations)
        {
            FakeTransport transport = new(request => Success(request));
            ToughTongueBuildGhostAdapter adapter = CreateAdapter(configuration, transport);

            ToughTongueBuildGhostResult result = await adapter.ExplainAsync(CreateRequest(), CancellationToken.None);

            Assert.AreEqual("credential-slot-configuration-invalid", result.OutcomeStatus);
            Assert.IsTrue(result.UsedDeterministicFallback);
            Assert.IsFalse(result.Receipt.RemoteAttempted);
            Assert.AreEqual(0, result.Receipt.HealthySlotCount);
            CollectionAssert.Contains(
                result.Receipt.ValidationReasons.ToArray(),
                "exactly-three-distinct-credentials-and-opaque-account-refs-required");
            Assert.IsEmpty(transport.Credentials);
        }
    }

    [TestMethod]
    [DataRow("en-US")]
    [DataRow("de-DE")]
    [DataRow("fr-FR")]
    [DataRow("ja-JP")]
    [DataRow("pt-BR")]
    [DataRow("zh-CN")]
    public async Task Every_materialized_locale_is_preserved_end_to_end(string locale)
    {
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(RemoteConfiguration(), transport);

        ToughTongueBuildGhostResult result = await adapter.ExplainAsync(
            CreateRequest("request-locale", "idem-locale", locale),
            CancellationToken.None);

        Assert.IsFalse(result.UsedDeterministicFallback);
        Assert.AreEqual(locale, result.ProviderAnswer!.Locale);
        Assert.AreEqual(locale, result.Receipt.Locale);
    }

    [TestMethod]
    public async Task Daily_quota_exhaustion_skips_spent_slots_and_fails_closed_after_all_three()
    {
        Dictionary<string, string?> values = RemoteConfiguration();
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_DAILY_QUOTA_PER_SLOT"] = "1";
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(values, transport);

        for (int index = 0; index < 3; index++)
        {
            ToughTongueBuildGhostResult success = await adapter.ExplainAsync(
                CreateRequest($"request-quota-{index}", $"idem-quota-{index}"),
                CancellationToken.None);
            Assert.IsFalse(success.UsedDeterministicFallback);
        }

        ToughTongueBuildGhostResult blocked = await adapter.ExplainAsync(
            CreateRequest("request-quota-blocked", "idem-quota-blocked"),
            CancellationToken.None);
        Assert.AreEqual("no-healthy-credential-slot", blocked.OutcomeStatus);
        Assert.HasCount(3, transport.Credentials);
    }

    [TestMethod]
    public async Task Circuit_breaker_cools_each_failed_slot_and_then_fails_closed()
    {
        Dictionary<string, string?> values = RemoteConfiguration();
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CIRCUIT_FAILURE_THRESHOLD"] = "1";
        FakeTransport transport = new(_ => new ToughTongueBuildGhostTransportResult(false, "temporary failure", null, Retryable: true));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(values, transport);

        ToughTongueBuildGhostResult[] results = new ToughTongueBuildGhostResult[4];
        for (int index = 0; index < results.Length; index++)
        {
            results[index] = await adapter.ExplainAsync(CreateRequest($"request-{index}", $"idem-{index}"), CancellationToken.None);
        }

        Assert.HasCount(3, transport.Credentials);
        Assert.AreEqual("no-healthy-credential-slot", results[3].OutcomeStatus);
        Assert.IsFalse(results[3].Receipt.RemoteAttempted);
        Assert.IsTrue(results.Take(3).All(static result => result.Receipt.CircuitPosture == "cooldown"));
    }

    [TestMethod]
    public async Task Provider_cannot_invent_packet_facts_actions_or_links()
    {
        FakeTransport transport = new(request =>
        {
            ToughTongueBuildGhostProviderAnswer answer = CreateAnswer(request) with
            {
                ReferencedFactIds = ["fact:invented"],
                SuggestedActionIds = ["apply-now"],
                Links = ["https://invented.invalid"]
            };
            return new ToughTongueBuildGhostTransportResult(true, "ok", JsonSerializer.Serialize(answer));
        });
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(RemoteConfiguration(), transport);

        ToughTongueBuildGhostResult result = await adapter.ExplainAsync(CreateRequest(), CancellationToken.None);

        Assert.IsTrue(result.UsedDeterministicFallback);
        Assert.AreEqual("provider-answer-rejected", result.OutcomeStatus);
        CollectionAssert.Contains(result.Receipt.ValidationReasons.ToArray(), "unsupported-fact:fact:invented");
        CollectionAssert.Contains(result.Receipt.ValidationReasons.ToArray(), "unsupported-action:apply-now");
        CollectionAssert.Contains(result.Receipt.ValidationReasons.ToArray(), "unsupported-link:https://invented.invalid");
    }

    [TestMethod]
    public async Task Provider_cannot_reference_group_members_without_authorized_visible_scope()
    {
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(RemoteConfiguration(), transport);
        ToughTongueBuildGhostRequest request = CreateRequest();
        JsonObject packet = JsonNode.Parse(request.AnalysisPacketJson)!.AsObject();
        packet["groupCapabilityPosture"]!.AsObject()["visibilityPosture"] = "consent-required";
        string digest = ComputePacketDigest(packet);
        packet["packetDigest"] = digest;
        request = request with
        {
            PacketDigest = digest,
            AnalysisPacketJson = packet.ToJsonString()
        };

        ToughTongueBuildGhostResult result = await adapter.ExplainAsync(request, CancellationToken.None);

        Assert.AreEqual("provider-answer-rejected", result.OutcomeStatus);
        CollectionAssert.Contains(result.Receipt.ValidationReasons.ToArray(), "unsupported-member:member:visible");
    }

    [TestMethod]
    public async Task Packet_digest_tampering_is_rejected_before_any_remote_call()
    {
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(RemoteConfiguration(), transport);
        ToughTongueBuildGhostRequest request = CreateRequest() with
        {
            AnalysisPacketJson = CreatePacket("en-US", "sha256:not-the-request-digest").ToJsonString()
        };

        await Assert.ThrowsAsync<InvalidDataException>(() => adapter.ExplainAsync(request, CancellationToken.None));
        Assert.IsEmpty(transport.Credentials);
    }

    [TestMethod]
    public async Task Documented_public_api_gap_fails_closed_without_calling_an_invented_explanation_route()
    {
        HttpClient client = new(new RejectNetworkHandler())
        {
            BaseAddress = new Uri("https://api.toughtongueai.com/api/public/")
        };
        ToughTongueBuildGhostHttpTransport transport = new(client);

        ToughTongueBuildGhostTransportResult result = await transport.ExplainAsync(
            new ToughTongueBuildGhostTransportRequest(
                ToughTongueBuildGhostContractVersions.RequestV1,
                "request-contract",
                $"sha256:{new string('a', 64)}",
                "en-US",
                "{}",
                "idem-contract"),
            "secret-never-sent",
            CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.AreEqual("provider-grounded-explanation-contract-unverified", result.OutcomeCode);
    }

    [TestMethod]
    public void Persona_registry_requires_Chummer_owned_verified_releases_and_synthetic_voice_provenance()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-08-19T12:00:00Z");
        BuildGhostPersonaMediaRelease avatar = Release(ToughTongueBuildGhostPersonaIds.RookAvatar, "avatar", "generated-original", now);
        BuildGhostPersonaMediaRelease unverifiedVoice = Release(ToughTongueBuildGhostPersonaIds.RookVoice, "synthetic-voice", "human-recording", now) with
        {
            ProviderVerificationState = "pending-operator"
        };
        BuildGhostPersonaReleaseProjection blocked = new BuildGhostPersonaReleaseRegistry([avatar, unverifiedVoice]).ResolveRook();

        Assert.IsTrue(blocked.AvatarReady);
        Assert.IsFalse(blocked.VoiceReady);
        Assert.AreEqual("governed-avatar-and-text-only", blocked.FallbackPosture);
        CollectionAssert.Contains(blocked.BlockingReasons.ToArray(), "voice-provenance-is-not-declared-synthetic");

        BuildGhostPersonaMediaRelease voice = Release(ToughTongueBuildGhostPersonaIds.RookVoice, "synthetic-voice", "synthetic-voice-generated-from-consented-seed", now);
        BuildGhostPersonaReleaseProjection ready = new BuildGhostPersonaReleaseRegistry([avatar, voice]).ResolveRook();
        Assert.IsTrue(ready.AvatarReady);
        Assert.IsTrue(ready.VoiceReady);
        Assert.AreEqual("governed-avatar-and-voice", ready.FallbackPosture);
    }

    private static ToughTongueBuildGhostAdapter CreateAdapter(
        IReadOnlyDictionary<string, string?> values,
        FakeTransport transport)
    {
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(values).Build();
        return new ToughTongueBuildGhostAdapter(configuration, transport, new FixedClock());
    }

    private static Dictionary<string, string?> RemoteConfiguration()
        => new(StringComparer.Ordinal)
        {
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED"] = "true",
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS"] = "secret-one;secret-two;secret-three",
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS"] = $"{AccountOne};{AccountTwo};{AccountThree}",
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID"] = "rook-private-scenario",
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID"] = ToughTongueBuildGhostPersonaIds.RookVoice
        };

    private static Dictionary<string, string?> WithSlotConfiguration(string credentials, string accountRefs)
    {
        Dictionary<string, string?> values = RemoteConfiguration();
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS"] = credentials;
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS"] = accountRefs;
        return values;
    }

    private static ToughTongueBuildGhostRequest CreateRequest(
        string requestId = "request-1",
        string idempotencyKey = "idem-1",
        string locale = "en-US")
    {
        JsonObject packet = CreatePacket(locale, string.Empty);
        string digest = ComputePacketDigest(packet);
        packet["packetDigest"] = digest;
        return new ToughTongueBuildGhostRequest(
            ToughTongueBuildGhostContractVersions.RequestV1,
            requestId,
            $"sha256:{new string('a', 64)}",
            digest,
            locale,
            packet.ToJsonString(),
            "Grounded local fallback.",
            idempotencyKey,
            DateTimeOffset.Parse("2026-08-19T12:00:00Z"));
    }

    private static JsonObject CreatePacket(string locale, string digest)
        => new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.AnalysisV1,
            ["personaId"] = ToughTongueBuildGhostPersonaIds.Rook,
            ["avatarId"] = ToughTongueBuildGhostPersonaIds.RookAvatar,
            ["voiceId"] = ToughTongueBuildGhostPersonaIds.RookVoice,
            ["locale"] = locale,
            ["localeFallbackChain"] = new JsonArray(locale, "en-US"),
            ["supportedLocales"] = new JsonArray("en-US", "de-DE", "fr-FR", "ja-JP", "pt-BR", "zh-CN"),
            ["packetDigest"] = digest,
            ["runner"] = new JsonObject
            {
                ["facts"] = new JsonArray(new JsonObject { ["factId"] = "fact:matrix" })
            },
            ["optimizationStrategies"] = new JsonArray(new JsonObject { ["strategyId"] = "strategy:matrix" }),
            ["ruleExplanations"] = new JsonArray(new JsonObject
            {
                ["explanationId"] = "rule:matrix",
                ["sourceLookupRoute"] = "/rules/matrix"
            }),
            ["variants"] = new JsonArray(new JsonObject { ["variantId"] = "variant:balanced" }),
            ["sourceAnchors"] = new JsonArray(new JsonObject { ["anchorId"] = "anchor:matrix" }),
            ["allowedSuggestedActions"] = new JsonArray(new JsonObject { ["actionId"] = "preview:balanced" }),
            ["groupCapabilityPosture"] = new JsonObject
            {
                ["visibilityPosture"] = "authorized-visible-scope",
                ["visibleMembers"] = new JsonArray(new JsonObject { ["memberRef"] = "member:visible" })
            }
        };

    private static ToughTongueBuildGhostTransportResult Success(ToughTongueBuildGhostTransportRequest request)
        => new(true, "ok", JsonSerializer.Serialize(CreateAnswer(request)));

    private static ToughTongueBuildGhostProviderAnswer CreateAnswer(ToughTongueBuildGhostTransportRequest request)
        => new(
            ToughTongueBuildGhostContractVersions.ProviderAnswerV1,
            request.RequestId,
            request.PacketDigest,
            request.Locale,
            "Grounded provider explanation.",
            ["fact:matrix"],
            ["strategy:matrix"],
            ["rule:matrix"],
            ["variant:balanced"],
            ["member:visible"],
            ["anchor:matrix"],
            ["preview:balanced"],
            ["/rules/matrix"]);

    private static BuildGhostPersonaMediaRelease Release(string assetId, string kind, string provenance, DateTimeOffset now)
        => new(
            ToughTongueBuildGhostContractVersions.PersonaReleaseV1,
            $"release:{assetId}",
            ToughTongueBuildGhostPersonaIds.Rook,
            assetId,
            kind,
            "Chummer",
            provenance,
            "sha256:asset",
            "consent:rook-synthetic",
            "chummer-owned",
            "verified",
            "approved",
            now);

    private static string ComputePacketDigest(JsonObject packet)
    {
        JsonObject clone = (JsonObject)packet.DeepClone();
        clone["packetDigest"] = string.Empty;
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream)) WriteCanonical(writer, clone);
        return $"sha256:{Convert.ToHexString(SHA256.HashData(stream.ToArray())).ToLowerInvariant()}";
    }

    private static void WriteCanonical(Utf8JsonWriter writer, JsonNode? node)
    {
        switch (node)
        {
            case null:
                writer.WriteNullValue();
                break;
            case JsonObject value:
                writer.WriteStartObject();
                foreach ((string key, JsonNode? child) in value.OrderBy(static item => item.Key, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(key);
                    WriteCanonical(writer, child);
                }
                writer.WriteEndObject();
                break;
            case JsonArray value:
                writer.WriteStartArray();
                foreach (JsonNode? child in value) WriteCanonical(writer, child);
                writer.WriteEndArray();
                break;
            default:
                node.WriteTo(writer);
                break;
        }
    }

    private sealed class FixedClock : IBuildGhostClock
    {
        public DateTimeOffset UtcNow { get; set; } = DateTimeOffset.Parse("2026-08-19T12:00:00Z");
    }

    private sealed class FakeTransport(
        Func<ToughTongueBuildGhostTransportRequest, ToughTongueBuildGhostTransportResult>? response = null) : IToughTongueBuildGhostTransport
    {
        private readonly Func<ToughTongueBuildGhostTransportRequest, ToughTongueBuildGhostTransportResult> _response = response
            ?? (_ => throw new AssertFailedException("Remote transport must not be called."));

        public List<string> Credentials { get; } = [];

        public Task<ToughTongueBuildGhostTransportResult> ExplainAsync(
            ToughTongueBuildGhostTransportRequest request,
            string credential,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Credentials.Add(credential);
            return Task.FromResult(_response(request));
        }
    }

    private sealed class RejectNetworkHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => throw new AssertFailedException($"Unexpected network request to {request.RequestUri}.");
    }
}
