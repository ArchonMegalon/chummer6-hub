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
    private const string VoiceReleaseDigest = "sha256:05ed9fff46ddb5a447e1d21cfd0f71cfb2a9286460fd112bb7514eb3eaa57e26";
    private const string CartesiaVoiceId = "f161df88-b5a0-4ea8-aa21-6be12859f761";
    private const string OtherCartesiaVoiceId = "86c6b891-3195-4e85-8be9-74f889d80620";
    private const string ProviderResponseDigest = "sha256:4e6db0b62942d0ca42575d86ac47599458190e29210e86cb503635e1f86204df";
    private const string ProviderSchemaDigest = "sha256:fe5490a49292fc33d0a8c5c52a08127c5c95f5920d8023f8d8472319e725c2dc";
    private const string VerifiedScenarioFieldPath = "provider_verified.cartesia_tts_provider";

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
    public async Task Interactive_provider_contract_fails_closed_without_calling_an_invented_explanation_route()
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
        Assert.AreEqual("provider-interactive-session-required", result.OutcomeCode);
    }

    [TestMethod]
    public void Private_scenario_candidate_binds_Rook_clone_tool_privacy_and_all_shipping_locales()
    {
        ToughTongueBuildGhostScenarioCandidate candidate = ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
            ToolDeployment(),
            new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
            RuntimeBinding(),
            ScenarioFieldReceipt());

        Assert.AreEqual(ToughTongueBuildGhostContractVersions.ScenarioContractV1, candidate.Schema);
        Assert.IsFalse(candidate.Payload["is_public"]!.GetValue<bool>());
        Assert.IsFalse(candidate.Payload["is_recording"]!.GetValue<bool>());
        Assert.AreEqual("never", candidate.Payload["analysis_access"]!.GetValue<string>());
        Assert.IsFalse(candidate.Payload["memory"]!["is_memory"]!.GetValue<bool>());
        Assert.AreEqual("Landmass", candidate.Payload["ai_model_config"]!["provider"]!.GetValue<string>());
        Assert.AreEqual("cascade", candidate.Payload["ai_model_config"]!["model"]!.GetValue<string>());
        Assert.AreEqual(CartesiaVoiceId, candidate.Payload["appearance"]!["voice"]!.GetValue<string>());
        Assert.AreEqual("Cartesia", candidate.Payload["provider_verified"]!["cartesia_tts_provider"]!.GetValue<string>());
        Assert.AreEqual(VerifiedScenarioFieldPath, candidate.TtsProviderFieldPath);
        Assert.IsTrue(candidate.ProviderSchemaReadVerified);
        Assert.IsEmpty(candidate.BlockingReasons);
        CollectionAssert.AreEqual(
            new[] { "de-DE", "en-US", "fr-FR", "ja-JP", "pt-BR", "zh-CN" },
            candidate.SupportedLocales.ToArray());
        Assert.AreEqual("get_chummer_build_analysis", candidate.Tool.Name);
        Assert.AreEqual(15_000, candidate.Tool.MaximumResponseCharacters);
        Assert.AreEqual(120, candidate.Tool.TimeoutSeconds);
        StringAssert.Contains(candidate.Tool.BodySchemaJson, "packet_access_key");
        StringAssert.Contains(candidate.Tool.BodySchemaJson, "group-gaps");
        StringAssert.StartsWith(candidate.Tool.ContractDigest, "sha256:");
        StringAssert.StartsWith(candidate.ContractDigest, "sha256:");
        StringAssert.Contains(candidate.Payload["ai_instructions"]!.GetValue<string>(), "never speak");
        Assert.AreEqual(ToolDeployment().ContractDigest, candidate.Payload["user_metadata"]!["tool_deployment_digest"]!.GetValue<string>());
        Assert.AreEqual(RuntimeBinding().ContractDigest, candidate.Payload["user_metadata"]!["runtime_binding_digest"]!.GetValue<string>());
        Assert.AreEqual("Cartesia", candidate.Payload["user_metadata"]!["tts_provider"]!.GetValue<string>());
        Assert.AreEqual("cartesia", candidate.Payload["user_metadata"]!["provider_namespace"]!.GetValue<string>());
    }

    [TestMethod]
    public void Private_tool_deployment_package_is_provider_neutral_digest_bound_and_remote_disabled()
    {
        BuildGhostPrivateToolDeploymentPackage package = ToolDeployment();

        Assert.AreEqual(ToughTongueBuildGhostContractVersions.PrivateToolDeploymentV1, package.Schema);
        Assert.IsTrue(package.ProviderNeutral);
        Assert.IsFalse(package.RemoteExecutionEnabled);
        Assert.AreEqual("ephemeral-bearer", package.AuthenticationScheme);
        Assert.AreEqual(300, package.PacketAccessTtlSeconds);
        Assert.AreEqual(ToughTongueBuildGhostContractVersions.AnalysisV1, package.ResponseSchema);
        Assert.AreEqual("https://canary.chummer.run/api/v1/ai/build-ghost/tool", package.Tool.Endpoint.AbsoluteUri);
        StringAssert.StartsWith(package.ContractDigest, "sha256:");
        Assert.ThrowsExactly<ArgumentException>(() => BuildGhostPrivateToolDeploymentContract.Create(
            new Uri("https://provider.invalid/api/v1/ai/build-ghost/tool"),
            "build-ghost-private-tool"));

        IConfiguration enabled = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostPrivateToolDeploymentContract.EndpointConfigurationKey] = package.Tool.Endpoint.AbsoluteUri,
            [BuildGhostPrivateToolDeploymentContract.AudienceConfigurationKey] = package.AuthenticationAudience,
            [BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey] = "true"
        }).Build();
        BuildGhostPrivateToolDeploymentValidation blocked = BuildGhostPrivateToolDeploymentContract.FromConfiguration(enabled);
        Assert.IsFalse(blocked.Accepted);
        CollectionAssert.Contains(blocked.RejectionReasons.ToArray(), "remote-execution-must-remain-disabled");
    }

    [TestMethod]
    public void Cascade_private_voice_binding_requires_an_exact_private_owned_Cartesia_read_receipt()
    {
        BuildGhostCascadePrivateVoiceBinding binding = RuntimeBinding();
        Assert.AreEqual("Landmass", binding.ModelProvider);
        Assert.AreEqual("cascade", binding.ModelId);
        Assert.AreEqual("Cartesia", binding.TtsProvider);
        Assert.AreEqual("cartesia", binding.ProviderNamespace);
        Assert.AreEqual(CartesiaVoiceId, binding.ProviderVoiceRef);
        Assert.AreEqual(ToughTongueBuildGhostPersonaIds.RookVoice, binding.VoiceAlias);
        Assert.AreEqual(VoiceReleaseDigest, binding.VoiceReleaseDigest);
        StringAssert.StartsWith(binding.VoiceReadReceiptDigest, "sha256:");
        StringAssert.StartsWith(binding.ContractDigest, "sha256:");
        string serialized = JsonSerializer.Serialize(binding);
        Assert.IsFalse(serialized.Contains("\"Private\":", StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains("ReadVerified", StringComparison.Ordinal));

    }

    [TestMethod]
    public void Cartesia_voice_binding_rejects_Unmixr_cross_wires_and_sha256_voice_refs()
    {
        BuildGhostCartesiaPrivateVoiceReadReceipt receipt = VoiceReadReceipt();
        AssertVoiceReceiptRejected(receipt with { ProviderNamespace = "unmixr" }, "cartesia-provider-namespace-invalid");
        AssertVoiceReceiptRejected(
            receipt with
            {
                RequestedVoiceId = $"sha256:{new string('a', 64)}",
                ReturnedVoiceId = $"sha256:{new string('a', 64)}"
            },
            "cartesia-voice-id-invalid");

        BuildGhostCascadePrivateVoiceBinding binding = RuntimeBinding();
        CollectionAssert.Contains(
            BuildGhostCascadePrivateVoiceBindingContract.Validate(binding with { TtsProvider = "Unmixr" }).ToArray(),
            "voice-binding-tts-provider-invalid");
        CollectionAssert.Contains(
            BuildGhostCascadePrivateVoiceBindingContract.Validate(binding with { ProviderNamespace = "unmixr" }).ToArray(),
            "voice-binding-provider-namespace-invalid");
    }

    [TestMethod]
    public void Cartesia_voice_binding_rejects_mismatch_nonowner_nonprivate_and_unverified_provenance()
    {
        BuildGhostCartesiaPrivateVoiceReadReceipt receipt = VoiceReadReceipt();
        AssertVoiceReceiptRejected(receipt with { ReturnedVoiceId = OtherCartesiaVoiceId }, "cartesia-voice-id-read-mismatch");
        AssertVoiceReceiptRejected(receipt with { IsOwner = false }, "cartesia-voice-owner-invalid");
        AssertVoiceReceiptRejected(receipt with { Access = "public" }, "cartesia-voice-access-not-private");
        AssertVoiceReceiptRejected(receipt with { Visibility = "shared" }, "cartesia-voice-visibility-not-owner");
        AssertVoiceReceiptRejected(receipt with { SyntheticProvenance = "caller-asserted-synthetic" }, "cartesia-voice-synthetic-provenance-invalid");
        AssertVoiceReceiptRejected(receipt with { SourceVoiceReleaseDigest = "sha256:not-a-release-digest" }, "cartesia-voice-source-release-digest-invalid");
        AssertVoiceReceiptRejected(receipt with { ReadHttpStatus = 201 }, "cartesia-voice-read-http-status-invalid");
    }

    [TestMethod]
    public void Scenario_validation_rejects_Cascade_or_private_voice_binding_drift()
    {
        ToughTongueBuildGhostScenarioCandidate candidate = ScenarioCandidate();
        JsonObject drifted = (JsonObject)candidate.Payload.DeepClone();
        drifted["id"] = "0123456789abcdef01234567";
        drifted["ai_model_config"]!["model"] = "other-model";
        drifted["provider_verified"]!["cartesia_tts_provider"] = "Unmixr";
        drifted["user_metadata"]!["runtime_binding_digest"] = $"sha256:{new string('0', 64)}";
        drifted["user_metadata"]!["voice_release_digest"] = $"sha256:{new string('1', 64)}";

        ToughTongueBuildGhostScenarioValidation validation = ToughTongueBuildGhostScenarioContract.Validate(drifted, candidate);

        Assert.IsFalse(validation.Accepted);
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "scenario-model-invalid");
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "scenario-tts-provider-mismatch");
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "runtime-binding-digest-mismatch");
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "voice-release-digest-mismatch");
    }

    [TestMethod]
    public async Task Documented_scenario_create_and_read_contract_use_only_the_official_private_API_boundary()
    {
        ToughTongueBuildGhostScenarioCandidate candidate = ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
            ToolDeployment(),
            new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
            RuntimeBinding(),
            ScenarioFieldReceipt());
        JsonObject providerScenario = (JsonObject)candidate.Payload.DeepClone();
        providerScenario["id"] = "0123456789abcdef01234567";
        RecordingHttpHandler handler = new(
            JsonResponse(providerScenario),
            JsonResponse(providerScenario));
        HttpClient client = new(handler)
        {
            BaseAddress = new Uri("https://api.toughtongueai.com/api/public/")
        };
        ToughTongueBuildGhostScenarioClient scenarios = new(
            client,
            new FixedClock(),
            ScenarioConfiguration(mutationsEnabled: true));

        (ToughTongueBuildGhostScenarioValidation created, string? scenarioId) =
            await scenarios.CreatePrivateCandidateAsync(candidate, "fresh-test-token", CancellationToken.None);
        ToughTongueBuildGhostScenarioValidation verified = await scenarios.VerifyPrivateScenarioAsync(
            scenarioId!,
            candidate,
            "fresh-test-token",
            CancellationToken.None);

        Assert.IsTrue(created.Accepted, string.Join(',', created.RejectionReasons));
        Assert.IsTrue(verified.Accepted, string.Join(',', verified.RejectionReasons));
        Assert.AreEqual("0123456789abcdef01234567", scenarioId);
        Assert.HasCount(2, handler.Requests);
        Assert.AreEqual(HttpMethod.Post, handler.Requests[0].Method);
        Assert.AreEqual("https://api.toughtongueai.com/api/public/scenarios", handler.Requests[0].Uri.AbsoluteUri);
        Assert.AreEqual(HttpMethod.Get, handler.Requests[1].Method);
        Assert.AreEqual("https://api.toughtongueai.com/api/public/scenarios/0123456789abcdef01234567", handler.Requests[1].Uri.AbsoluteUri);
        Assert.IsTrue(handler.Requests.All(static request => request.HasBearerCredential));
        JsonObject posted = JsonNode.Parse(handler.Requests[0].Body!)!.AsObject();
        Assert.IsFalse(posted["is_public"]!.GetValue<bool>());
        Assert.AreEqual(candidate.ContractDigest, posted["user_metadata"]!["scenario_contract_digest"]!.GetValue<string>());
    }

    [TestMethod]
    public async Task Documented_private_access_grant_is_one_hour_bounded_and_never_added_to_receipts()
    {
        FixedClock clock = new();
        RecordingHttpHandler handler = new(JsonResponse(new JsonObject
        {
            ["access_token"] = new string('x', 64),
            ["expires_at"] = clock.UtcNow.AddHours(1).ToString("O")
        }));
        ToughTongueBuildGhostScenarioClient scenarios = new(
            new HttpClient(handler) { BaseAddress = new Uri("https://api.toughtongueai.com/api/public/") },
            clock,
            ScenarioConfiguration(mutationsEnabled: true));

        ToughTongueBuildGhostScenarioAccessGrant grant = await scenarios.CreateAccessGrantAsync(
            "0123456789abcdef01234567",
            "fresh-test-token",
            CancellationToken.None);

        Assert.AreEqual(clock.UtcNow.AddHours(1), grant.ExpiresAtUtc);
        Assert.AreEqual("https://api.toughtongueai.com/api/public/scenario-access-token", handler.Requests.Single().Uri.AbsoluteUri);
        Assert.AreEqual("0123456789abcdef01234567", JsonNode.Parse(handler.Requests.Single().Body!)!["scenario_id"]!.GetValue<string>());
        Assert.IsFalse(JsonSerializer.Serialize(new ToughTongueBuildGhostReceipt(
            ToughTongueBuildGhostContractVersions.ReceiptV1,
            "receipt", "request", $"sha256:{new string('a', 64)}", "en-US", $"sha256:{new string('b', 64)}",
            "remote-disabled", "tough-tongue", "interactive-session", "scenario", "voice", false, false,
            null, "not-selected", 3, 3, null, null, null, "remote-disabled", [], clock.UtcNow, clock.UtcNow, 0))
            .Contains(grant.AccessToken, StringComparison.Ordinal));
    }

    [TestMethod]
    public async Task Scenario_client_rejects_nonofficial_hosts_before_sending_a_provider_credential()
    {
        RecordingHttpHandler handler = new(JsonResponse(new JsonObject()));
        ToughTongueBuildGhostScenarioClient scenarios = new(
            new HttpClient(handler) { BaseAddress = new Uri("https://attacker.invalid/api/public/") },
            new FixedClock(),
            ScenarioConfiguration(mutationsEnabled: false));

        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => scenarios.VerifyPrivateScenarioAsync(
            "0123456789abcdef01234567",
            ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
                ToolDeployment(),
                new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
                RuntimeBinding(),
                ScenarioFieldReceipt()),
            "must-not-leave-process",
            CancellationToken.None));
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    public void Scenario_client_accepts_only_the_current_exact_official_API_boundary()
    {
        Assert.IsTrue(ToughTongueBuildGhostScenarioClient.IsOfficialApiBaseAddress(
            new Uri("https://api.toughtongueai.com/api/public/")));
        Assert.IsFalse(ToughTongueBuildGhostScenarioClient.IsOfficialApiBaseAddress(
            new Uri("https://app.toughtongueai.com/api/public/")));
        Assert.IsFalse(ToughTongueBuildGhostScenarioClient.IsOfficialApiBaseAddress(
            new Uri("https://api.toughtongueai.com/other/api/public/")));
        Assert.IsFalse(ToughTongueBuildGhostScenarioClient.IsOfficialApiBaseAddress(
            new Uri("https://api.toughtongueai.com:8443/api/public/")));
    }

    [TestMethod]
    public async Task Scenario_client_rejects_the_stale_app_host_before_sending_a_provider_credential()
    {
        RecordingHttpHandler handler = new(JsonResponse(new JsonObject()));
        ToughTongueBuildGhostScenarioClient scenarios = new(
            new HttpClient(handler) { BaseAddress = new Uri("https://app.toughtongueai.com/api/public/") },
            new FixedClock(),
            ScenarioConfiguration(mutationsEnabled: true));

        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => scenarios.VerifyPrivateScenarioAsync(
            "0123456789abcdef01234567",
            ScenarioCandidate(),
            "must-not-leave-process",
            CancellationToken.None));

        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    public async Task Scenario_creation_is_blocked_without_a_provider_schema_backed_Cartesia_field_receipt()
    {
        RecordingHttpHandler handler = new(JsonResponse(new JsonObject()));
        ToughTongueBuildGhostScenarioClient scenarios = new(
            new HttpClient(handler) { BaseAddress = new Uri("https://api.toughtongueai.com/api/public/") },
            new FixedClock(),
            ScenarioConfiguration(mutationsEnabled: true));
        ToughTongueBuildGhostScenarioCandidate blockedCandidate =
            ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
                ToolDeployment(),
                new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
                RuntimeBinding());

        (ToughTongueBuildGhostScenarioValidation validation, string? scenarioId) =
            await scenarios.CreatePrivateCandidateAsync(
                blockedCandidate,
                "must-not-leave-process",
                CancellationToken.None);

        Assert.IsFalse(validation.Accepted);
        Assert.IsNull(scenarioId);
        CollectionAssert.Contains(
            validation.RejectionReasons.ToArray(),
            BuildGhostToughTongueCartesiaScenarioFieldContract.MissingOrUnverifiedBlocker);
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    public async Task Scenario_mutations_are_disabled_by_default_before_any_provider_request()
    {
        RecordingHttpHandler handler = new(JsonResponse(new JsonObject()));
        ToughTongueBuildGhostScenarioClient scenarios = new(
            new HttpClient(handler) { BaseAddress = new Uri("https://api.toughtongueai.com/api/public/") },
            new FixedClock(),
            ScenarioConfiguration(mutationsEnabled: false));
        ToughTongueBuildGhostScenarioCandidate candidate = ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
            ToolDeployment(),
            new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
            RuntimeBinding(),
            ScenarioFieldReceipt());

        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => scenarios.CreatePrivateCandidateAsync(
            candidate,
            "must-not-leave-process",
            CancellationToken.None));
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => scenarios.CreateAccessGrantAsync(
            "0123456789abcdef01234567",
            "must-not-leave-process",
            CancellationToken.None));
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    public async Task Canary_harness_defaults_closed_without_reading_a_scenario_or_creating_a_grant()
    {
        FakeScenarioClient scenarios = new();
        ToughTongueBuildGhostCanaryHarness harness = new(
            scenarios,
            new FixedClock(),
            new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>()).Build());

        ToughTongueBuildGhostCanaryReceipt receipt = await harness.RunAsync(
            "0123456789abcdef01234567",
            ScenarioCandidate(),
            "fresh-governed-test-credential",
            CancellationToken.None);

        Assert.AreEqual("blocked", receipt.OutcomeStatus);
        Assert.IsFalse(receipt.RemoteExecutionEnabled);
        Assert.IsFalse(receipt.ScenarioReadAttempted);
        Assert.IsFalse(receipt.AccessGrantAttempted);
        CollectionAssert.Contains(receipt.BlockingReasons.ToArray(), "scenario-read-canary-disabled");
        Assert.AreEqual(0, scenarios.VerifyCalls);
        Assert.AreEqual(0, scenarios.AccessGrantCalls);
        string rendered = JsonSerializer.Serialize(receipt);
        Assert.IsFalse(rendered.Contains("0123456789abcdef01234567", StringComparison.Ordinal));
        Assert.IsFalse(rendered.Contains("fresh-governed-test-credential", StringComparison.Ordinal));
    }

    [TestMethod]
    public async Task Canary_harness_allows_read_only_validation_but_blocks_access_grant_while_remote_execution_is_disabled()
    {
        FakeScenarioClient scenarios = new();
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [ToughTongueBuildGhostCanaryHarness.ReadOnlyEnabledKey] = "true",
            [ToughTongueBuildGhostCanaryHarness.AccessGrantEnabledKey] = "true",
            [BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey] = "false"
        }).Build();
        ToughTongueBuildGhostCanaryHarness harness = new(scenarios, new FixedClock(), configuration);

        ToughTongueBuildGhostCanaryReceipt receipt = await harness.RunAsync(
            "0123456789abcdef01234567",
            ScenarioCandidate(),
            "fresh-governed-test-credential",
            CancellationToken.None);

        Assert.IsTrue(receipt.ScenarioReadAttempted);
        Assert.IsTrue(receipt.ScenarioAccepted);
        Assert.IsFalse(receipt.AccessGrantAttempted);
        Assert.IsFalse(receipt.AccessGrantCreated);
        CollectionAssert.Contains(receipt.BlockingReasons.ToArray(), "access-grant-blocked-while-remote-execution-disabled");
        Assert.AreEqual(1, scenarios.VerifyCalls);
        Assert.AreEqual(0, scenarios.AccessGrantCalls);
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

    private static BuildGhostPrivateToolDeploymentPackage ToolDeployment()
        => BuildGhostPrivateToolDeploymentContract.Create(
            new Uri("https://canary.chummer.run/api/v1/ai/build-ghost/tool"),
            "build-ghost-private-tool");

    private static BuildGhostCascadePrivateVoiceBinding RuntimeBinding()
        => BuildGhostCascadePrivateVoiceBindingContract.Create(
            VoiceReadReceipt(),
            ToughTongueBuildGhostScenarioContract.CanonicalLocales);

    private static BuildGhostCartesiaPrivateVoiceReadReceipt VoiceReadReceipt()
        => new(
            ToughTongueBuildGhostContractVersions.CartesiaPrivateVoiceReadReceiptV1,
            ToughTongueBuildGhostVoiceProviders.CartesiaNamespace,
            CartesiaVoiceId,
            CartesiaVoiceId,
            200,
            true,
            "private",
            "owner",
            ToughTongueBuildGhostVoiceProviders.FullySyntheticProvenance,
            VoiceReleaseDigest,
            ProviderResponseDigest,
            DateTimeOffset.Parse("2026-08-21T08:00:00Z"));

    private static BuildGhostToughTongueCartesiaScenarioFieldReceipt ScenarioFieldReceipt()
        => new(
            ToughTongueBuildGhostContractVersions.CartesiaScenarioFieldReceiptV1,
            ToughTongueBuildGhostVoiceProviders.CartesiaNamespace,
            ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider,
            VerifiedScenarioFieldPath,
            VerifiedScenarioFieldPath,
            ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider,
            200,
            ProviderSchemaDigest,
            ProviderResponseDigest,
            DateTimeOffset.Parse("2026-08-21T08:05:00Z"));

    private static ToughTongueBuildGhostScenarioCandidate ScenarioCandidate()
        => ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
            ToolDeployment(),
            new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
            RuntimeBinding(),
            ScenarioFieldReceipt());

    private static void AssertVoiceReceiptRejected(
        BuildGhostCartesiaPrivateVoiceReadReceipt receipt,
        string expectedReason)
    {
        ArgumentException exception = Assert.ThrowsExactly<ArgumentException>(() =>
            BuildGhostCascadePrivateVoiceBindingContract.Create(
                receipt,
                ToughTongueBuildGhostScenarioContract.CanonicalLocales));
        StringAssert.Contains(exception.Message, expectedReason);
    }

    private static IConfiguration ScenarioConfiguration(bool mutationsEnabled)
        => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED"] = mutationsEnabled.ToString()
        }).Build();

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

    private sealed class FakeScenarioClient : IToughTongueBuildGhostScenarioClient
    {
        public int VerifyCalls { get; private set; }
        public int AccessGrantCalls { get; private set; }

        public Task<ToughTongueBuildGhostScenarioValidation> VerifyPrivateScenarioAsync(
            string scenarioId,
            ToughTongueBuildGhostScenarioCandidate expected,
            string credential,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            VerifyCalls++;
            return Task.FromResult(new ToughTongueBuildGhostScenarioValidation(true, scenarioId, []));
        }

        public Task<(ToughTongueBuildGhostScenarioValidation Validation, string? ScenarioId)> CreatePrivateCandidateAsync(
            ToughTongueBuildGhostScenarioCandidate candidate,
            string credential,
            CancellationToken cancellationToken)
            => throw new AssertFailedException("Canary harness must never create a scenario candidate.");

        public Task<ToughTongueBuildGhostScenarioAccessGrant> CreateAccessGrantAsync(
            string scenarioId,
            string credential,
            CancellationToken cancellationToken)
        {
            AccessGrantCalls++;
            throw new AssertFailedException("Access grant must remain fail-closed in this test.");
        }
    }

    private static HttpResponseMessage JsonResponse(JsonObject payload)
        => new(System.Net.HttpStatusCode.OK)
        {
            Content = new StringContent(payload.ToJsonString(), System.Text.Encoding.UTF8, "application/json")
        };

    private sealed class RecordingHttpHandler(params HttpResponseMessage[] responses) : HttpMessageHandler
    {
        private readonly Queue<HttpResponseMessage> _responses = new(responses);

        public List<RecordedRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            string? body = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add(new RecordedRequest(
                request.Method,
                request.RequestUri!,
                string.Equals(request.Headers.Authorization?.Scheme, "Bearer", StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(request.Headers.Authorization?.Parameter),
                body));
            if (_responses.Count == 0)
            {
                throw new AssertFailedException("Unexpected provider HTTP request.");
            }

            return _responses.Dequeue();
        }
    }

    private sealed record RecordedRequest(
        HttpMethod Method,
        Uri Uri,
        bool HasBearerCredential,
        string? Body);
}
