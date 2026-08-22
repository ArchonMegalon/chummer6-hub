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
    private const string AccountFour = "sha256:4444444444444444444444444444444444444444444444444444444444444444";
    private const string VoiceReleaseDigest = "sha256:05ed9fff46ddb5a447e1d21cfd0f71cfb2a9286460fd112bb7514eb3eaa57e26";
    private const string CartesiaVoiceId = "f161df88-b5a0-4ea8-aa21-6be12859f761";
    private const string OtherCartesiaVoiceId = "86c6b891-3195-4e85-8be9-74f889d80620";
    private const string ProviderResponseDigest = "sha256:4e6db0b62942d0ca42575d86ac47599458190e29210e86cb503635e1f86204df";
    private const string CustomFunctionId = "custom-function-rook-private-v1";
    private const string CustomFunctionAccountRef = "sha256:689642aa853d240436dd28773f760a289be65a9ecf36783aae1ffe1934b74b15";

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
        Assert.IsTrue(new[] { first, second, third }.All(static result => result.Receipt.AccountSelectionPosture == "round-robin"));
        Assert.IsTrue(new[] { first, second, third }.All(static result => !result.UsedDeterministicFallback));
    }

    [TestMethod]
    public async Task Exact_preferred_account_pin_selects_one_aligned_governed_slot()
    {
        Dictionary<string, string?> values = WithSlotConfiguration(
            "secret-one;secret-two;secret-three;secret-four",
            $"{AccountOne};{AccountTwo};{AccountThree};{AccountFour}");
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF"] = AccountFour;
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(values, transport);

        ToughTongueBuildGhostResult result = await adapter.ExplainAsync(CreateRequest(), CancellationToken.None);

        CollectionAssert.AreEqual(new[] { "secret-four" }, transport.Credentials.ToArray());
        Assert.AreEqual(AccountFour, result.Receipt.AccountSlotId);
        Assert.AreEqual("exact-pin", result.Receipt.AccountSelectionPosture);
        string serialized = JsonSerializer.Serialize(result.Receipt);
        Assert.IsFalse(serialized.Contains("secret-four", StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains("@", StringComparison.Ordinal));
    }

    [TestMethod]
    public async Task Preferred_account_pin_rejects_email_ordinal_credential_and_malformed_values()
    {
        string[] invalidSelectors =
        [
            "private-account@example.test",
            "team-slot-2",
            "secret-two",
            $"sha256:{new string('A', 64)}",
            $"sha256:{new string('a', 63)}"
        ];
        foreach (string selector in invalidSelectors)
        {
            Dictionary<string, string?> values = RemoteConfiguration();
            values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF"] = selector;
            FakeTransport transport = new(request => Success(request));
            ToughTongueBuildGhostAdapter adapter = CreateAdapter(values, transport);

            ToughTongueBuildGhostResult result = await adapter.ExplainAsync(CreateRequest(), CancellationToken.None);

            Assert.AreEqual("preferred-account-ref-invalid", result.OutcomeStatus);
            Assert.AreEqual("exact-pin-invalid", result.Receipt.AccountSelectionPosture);
            Assert.IsFalse(result.Receipt.RemoteAttempted);
            Assert.IsEmpty(transport.Credentials);
            Assert.IsFalse(JsonSerializer.Serialize(result.Receipt).Contains(selector, StringComparison.Ordinal));
        }
    }

    [TestMethod]
    public async Task Preferred_account_pin_rejects_zero_and_duplicate_matches()
    {
        Dictionary<string, string?> unmatchedValues = RemoteConfiguration();
        unmatchedValues["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF"] = AccountFour;
        FakeTransport unmatchedTransport = new(request => Success(request));
        ToughTongueBuildGhostResult unmatched = await CreateAdapter(unmatchedValues, unmatchedTransport)
            .ExplainAsync(CreateRequest(), CancellationToken.None);

        Assert.AreEqual("preferred-account-ref-unmatched", unmatched.OutcomeStatus);
        Assert.AreEqual("exact-pin-unmatched", unmatched.Receipt.AccountSelectionPosture);
        Assert.IsEmpty(unmatchedTransport.Credentials);

        Dictionary<string, string?> ambiguousValues = WithSlotConfiguration(
            "secret-one;secret-two;secret-three",
            $"{AccountOne};{AccountTwo};{AccountTwo}");
        ambiguousValues["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF"] = AccountTwo;
        FakeTransport ambiguousTransport = new(request => Success(request));
        ToughTongueBuildGhostResult ambiguous = await CreateAdapter(ambiguousValues, ambiguousTransport)
            .ExplainAsync(CreateRequest(), CancellationToken.None);

        Assert.AreEqual("preferred-account-ref-ambiguous", ambiguous.OutcomeStatus);
        Assert.AreEqual("exact-pin-ambiguous", ambiguous.Receipt.AccountSelectionPosture);
        Assert.IsEmpty(ambiguousTransport.Credentials);
    }

    [TestMethod]
    public async Task Remote_disabled_keeps_exact_pin_from_calling_provider_transport()
    {
        Dictionary<string, string?> values = RemoteConfiguration();
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED"] = "false";
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF"] = AccountTwo;
        FakeTransport transport = new(request => Success(request));

        ToughTongueBuildGhostResult result = await CreateAdapter(values, transport)
            .ExplainAsync(CreateRequest(), CancellationToken.None);

        Assert.AreEqual("remote-disabled", result.OutcomeStatus);
        Assert.AreEqual("exact-pin", result.Receipt.AccountSelectionPosture);
        Assert.IsFalse(result.Receipt.RemoteAttempted);
        Assert.IsEmpty(transport.Credentials);
    }

    [TestMethod]
    public async Task Unhealthy_exact_pin_fails_closed_without_falling_back_to_other_slots()
    {
        Dictionary<string, string?> values = RemoteConfiguration();
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF"] = AccountTwo;
        values["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_DAILY_QUOTA_PER_SLOT"] = "1";
        FakeTransport transport = new(request => Success(request));
        ToughTongueBuildGhostAdapter adapter = CreateAdapter(values, transport);

        ToughTongueBuildGhostResult first = await adapter.ExplainAsync(
            CreateRequest("preferred-first", "preferred-idem-first"),
            CancellationToken.None);
        ToughTongueBuildGhostResult blocked = await adapter.ExplainAsync(
            CreateRequest("preferred-blocked", "preferred-idem-blocked"),
            CancellationToken.None);

        Assert.IsFalse(first.UsedDeterministicFallback);
        Assert.AreEqual("preferred-account-slot-unhealthy", blocked.OutcomeStatus);
        Assert.AreEqual(AccountTwo, blocked.Receipt.AccountSlotId);
        Assert.AreEqual("exact-pin", blocked.Receipt.AccountSelectionPosture);
        Assert.AreEqual("quota-exhausted", blocked.Receipt.CircuitPosture);
        Assert.IsFalse(blocked.Receipt.RemoteAttempted);
        CollectionAssert.AreEqual(new[] { "secret-two" }, transport.Credentials.ToArray());
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
    public async Task Remote_execution_requires_aligned_bounded_distinct_credentials_and_opaque_account_refs()
    {
        Dictionary<string, string?>[] invalidConfigurations =
        [
            WithSlotConfiguration("", ""),
            WithSlotConfiguration("secret-one;secret-two", $"{AccountOne};{AccountTwo}"),
            WithSlotConfiguration("secret-one;secret-two", $"{AccountOne};{AccountTwo};{AccountThree}"),
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
                "three-to-thirty-two-aligned-distinct-credentials-and-opaque-account-refs-required");
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
            ScenarioSchemaReceipt(),
            CustomFunctionBinding());

        Assert.AreEqual(ToughTongueBuildGhostContractVersions.ScenarioContractV1, candidate.Schema);
        Assert.IsFalse(candidate.Payload["is_public"]!.GetValue<bool>());
        Assert.IsFalse(candidate.Payload["is_recording"]!.GetValue<bool>());
        Assert.AreEqual("never", candidate.Payload["analysis_access"]!.GetValue<string>());
        Assert.IsFalse(candidate.Payload["memory"]!["is_memory"]!.GetValue<bool>());
        JsonObject sessionAnalysis = candidate.Payload["session_analysis"]!.AsObject();
        Assert.IsTrue(new[] { "is_auto_analysis", "is_auto_submit", "email_analysis", "email_transcript", "multimodal_analysis", "enable_extraction" }
            .All(field => sessionAnalysis[field]!.GetValue<bool>() == false));
        Assert.AreEqual("Landmass", candidate.Payload["ai_model_config"]!["provider"]!.GetValue<string>());
        Assert.AreEqual("cascade", candidate.Payload["ai_model_config"]!["model"]!.GetValue<string>());
        Assert.AreEqual(CartesiaVoiceId, candidate.Payload["appearance"]!["voice"]!.GetValue<string>());
        Assert.AreEqual("Cartesia", candidate.Payload["tts_provider"]!.GetValue<string>());
        Assert.AreEqual(CartesiaVoiceId, candidate.Payload["tts_voice_id"]!.GetValue<string>());
        Assert.AreEqual(BuildGhostToughTongueCartesiaScenarioSchemaContract.ReadTtsProviderFieldPath, candidate.TtsProviderFieldPath);
        Assert.AreEqual(BuildGhostToughTongueCartesiaScenarioSchemaContract.ReadTtsVoiceIdFieldPath, candidate.TtsVoiceIdFieldPath);
        Assert.IsTrue(candidate.ProviderSchemaReadVerified);
        Assert.IsTrue(candidate.CustomFunctionBindingReadVerified);
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
        Assert.AreEqual(CustomFunctionId, candidate.Payload["custom_function_ids"]![0]!.GetValue<string>());
        Assert.IsNull(candidate.Payload["tools_config"]!["tools"]!["custom_function"]);
        Assert.AreEqual(CustomFunctionBinding().ContractDigest, candidate.Payload["user_metadata"]!["custom_function_binding_digest"]!.GetValue<string>());
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
            [BuildGhostPrivateToolDeploymentContract.TransportModeConfigurationKey] = BuildGhostPrivateToolDeploymentContract.LegacyBearerV1TransportMode,
            [BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey] = "true"
        }).Build();
        BuildGhostPrivateToolDeploymentValidation blocked = BuildGhostPrivateToolDeploymentContract.FromConfiguration(enabled);
        Assert.IsFalse(blocked.Accepted);
        CollectionAssert.Contains(blocked.RejectionReasons.ToArray(), "remote-execution-must-remain-disabled");
    }

    [TestMethod]
    public void Provider_body_key_v2_deployment_is_explicit_provider_scoped_and_fails_closed_on_mode_drift()
    {
        BuildGhostPrivateToolDeploymentPackage package = ProviderToolDeployment();

        Assert.AreEqual(ToughTongueBuildGhostContractVersions.PrivateToolDeploymentV2, package.Schema);
        Assert.AreEqual(ToughTongueBuildGhostContractVersions.PrivateToolContractV2, package.Tool.Schema);
        Assert.AreEqual(BuildGhostPrivateToolDeploymentContract.ProviderBodyKeyAuthenticationScheme, package.AuthenticationScheme);
        Assert.IsFalse(package.ProviderNeutral);
        Assert.IsFalse(package.RemoteExecutionEnabled);
        Assert.AreEqual("https://canary.chummer.run/api/v2/ai/build-ghost/tool", package.Tool.Endpoint.AbsoluteUri);
        Assert.AreEqual("sha256:af7b643855bbc2220be40bfadc8cb1e89ecdc324a787c771a353d74e85f01104", package.Tool.ContractDigest);
        Assert.AreEqual("sha256:50707c6ba39796bad7bb1d924dfc1ab2d626b48232561c5ec98a0e72a22827a5", package.ContractDigest);
        CollectionAssert.AreEqual(
            new[] { "Cache-Control", "X-Chummer-Build-Ghost-Tool-Contract" },
            package.Tool.RequiredHeaderNames.ToArray());
        Assert.IsFalse(package.Tool.RequiredHeaderNames.Contains("Authorization", StringComparer.Ordinal));
        Assert.IsEmpty(BuildGhostPrivateToolDeploymentContract.ValidateProviderBodyCredentialDeployment(package));
        StringAssert.StartsWith(BuildGhostPrivateToolDeploymentContract.BodyCredentialEvidenceDigest(package), "sha256:");

        IConfiguration missingMode = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostPrivateToolDeploymentContract.EndpointConfigurationKey] = package.Tool.Endpoint.AbsoluteUri,
            [BuildGhostPrivateToolDeploymentContract.AudienceConfigurationKey] = package.AuthenticationAudience,
            [BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey] = "false"
        }).Build();
        CollectionAssert.Contains(
            BuildGhostPrivateToolDeploymentContract.FromConfiguration(missingMode).RejectionReasons.ToArray(),
            "private-tool-transport-mode-missing-or-invalid");

        IConfiguration crossedMode = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostPrivateToolDeploymentContract.EndpointConfigurationKey] = "https://canary.chummer.run/api/v1/ai/build-ghost/tool",
            [BuildGhostPrivateToolDeploymentContract.AudienceConfigurationKey] = package.AuthenticationAudience,
            [BuildGhostPrivateToolDeploymentContract.TransportModeConfigurationKey] = BuildGhostPrivateToolDeploymentContract.ProviderBodyKeyV2TransportMode,
            [BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey] = "false"
        }).Build();
        Assert.IsFalse(BuildGhostPrivateToolDeploymentContract.FromConfiguration(crossedMode).Accepted);
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
        JsonObject drifted = ProviderScenario(candidate);
        drifted["ai_model_config"]!["model"] = "other-model";
        drifted["ai_model_config"]!["tts_provider"] = "Unmixr";
        drifted["ai_model_config"]!["tts_voice_id"] = OtherCartesiaVoiceId;
        drifted["user_metadata"]!["runtime_binding_digest"] = $"sha256:{new string('0', 64)}";
        drifted["user_metadata"]!["voice_release_digest"] = $"sha256:{new string('1', 64)}";

        ToughTongueBuildGhostScenarioValidation validation = ToughTongueBuildGhostScenarioContract.Validate(drifted, candidate);

        Assert.IsFalse(validation.Accepted);
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "scenario-model-invalid");
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "scenario-tts-provider-mismatch");
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "scenario-tts-voice-id-mismatch");
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "runtime-binding-digest-mismatch");
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), "voice-release-digest-mismatch");
    }

    [TestMethod]
    public void Scenario_readback_rejects_every_privacy_and_custom_tool_binding_drift()
    {
        ToughTongueBuildGhostScenarioCandidate candidate = ScenarioCandidate();
        JsonObject drifted = ProviderScenario(candidate);
        drifted["is_public"] = true;
        drifted["is_recording"] = true;
        drifted["analysis_access"] = "provider";
        drifted["memory"]!["is_memory"] = true;
        JsonObject sessionAnalysis = drifted["session_analysis"]!.AsObject();
        foreach (string field in new[] { "is_auto_analysis", "is_auto_submit", "email_analysis", "email_transcript", "multimodal_analysis", "enable_extraction" })
        {
            sessionAnalysis[field] = true;
        }
        drifted["custom_function_ids"]![0] = "attacker-function";
        drifted["user_metadata"]!["tool_deployment_digest"] = $"sha256:{new string('0', 64)}";
        drifted["user_metadata"]!["tool_contract_digest"] = $"sha256:{new string('1', 64)}";
        drifted["user_metadata"]!["tool_endpoint"] = "https://attacker.invalid/tool";
        drifted["user_metadata"]!["tool_authentication_audience"] = "other-audience";

        ToughTongueBuildGhostScenarioValidation validation =
            ToughTongueBuildGhostScenarioContract.Validate(drifted, candidate);

        Assert.IsFalse(validation.Accepted);
        string[] reasons = validation.RejectionReasons.ToArray();
        foreach (string expected in new[]
        {
            "scenario-must-be-private",
            "scenario-recording-must-be-disabled",
            "scenario-analysis-access-invalid",
            "scenario-memory-must-be-disabled",
            "scenario-auto-analysis-must-be-disabled",
            "scenario-auto-submit-must-be-disabled",
            "scenario-email-analysis-must-be-disabled",
            "scenario-email-transcript-must-be-disabled",
            "scenario-multimodal-analysis-must-be-disabled",
            "scenario-extraction-must-be-disabled",
            "custom-function-scenario-attachment-mismatch",
            "tool-deployment-digest-mismatch",
            "tool-contract-digest-mismatch",
            "tool-endpoint-mismatch",
            "tool-authentication-audience-mismatch"
        })
        {
            CollectionAssert.Contains(reasons, expected);
        }
    }

    [TestMethod]
    public async Task Scenario_payload_serializes_exact_attachment_readback_is_valid_and_mutation_stays_blocked()
    {
        ToughTongueBuildGhostScenarioCandidate candidate = ScenarioCandidate();
        JsonObject providerScenario = ProviderScenario(candidate);
        RecordingHttpHandler handler = new(JsonResponse(providerScenario));
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
            "0123456789abcdef01234567",
            candidate,
            "fresh-test-token",
            CancellationToken.None);

        Assert.IsFalse(created.Accepted);
        CollectionAssert.Contains(created.RejectionReasons.ToArray(), BuildGhostToughTongueCustomFunctionContract.ScenarioMutationPublicApiBlocker);
        Assert.IsTrue(verified.Accepted, string.Join(',', verified.RejectionReasons));
        Assert.IsNull(scenarioId);
        Assert.HasCount(1, handler.Requests);
        Assert.AreEqual(HttpMethod.Get, handler.Requests[0].Method);
        Assert.AreEqual("https://api.toughtongueai.com/api/public/scenarios/0123456789abcdef01234567", handler.Requests[0].Uri.AbsoluteUri);
        Assert.IsTrue(handler.Requests.All(static request => request.HasBearerCredential));
        JsonObject posted = ToughTongueBuildGhostScenarioContract.SerializeCreatePayload(candidate);
        Assert.IsFalse(posted["is_public"]!.GetValue<bool>());
        Assert.AreEqual("Cartesia", posted["tts_provider"]!.GetValue<string>());
        Assert.AreEqual(CartesiaVoiceId, posted["tts_voice_id"]!.GetValue<string>());
        Assert.IsNull(posted["ai_model_config"]!["tts_provider"]);
        Assert.IsNull(posted["ai_model_config"]!["tts_voice_id"]);
        Assert.AreEqual(candidate.ContractDigest, posted["user_metadata"]!["scenario_contract_digest"]!.GetValue<string>());
        CollectionAssert.AreEqual(new[] { CustomFunctionId }, posted["custom_function_ids"]!.AsArray().Select(static value => value!.GetValue<string>()).ToArray());
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
            null, "round-robin", "not-selected", 3, 3, null, null, null, "remote-disabled", [], clock.UtcNow, clock.UtcNow, 0))
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
                ScenarioSchemaReceipt(),
                CustomFunctionBinding()),
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
    public async Task Scenario_creation_is_blocked_without_a_provider_schema_backed_Cartesia_bundle_receipt()
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
            BuildGhostToughTongueCartesiaScenarioSchemaContract.MissingOrUnverifiedBlocker);
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    public async Task Scenario_creation_is_blocked_without_a_read_verified_custom_function_binding()
    {
        RecordingHttpHandler handler = new(JsonResponse(new JsonObject()));
        ToughTongueBuildGhostScenarioClient scenarios = new(
            new HttpClient(handler) { BaseAddress = new Uri("https://api.toughtongueai.com/api/public/") },
            new FixedClock(),
            ScenarioConfiguration(mutationsEnabled: true));
        ToughTongueBuildGhostScenarioCandidate missing =
            ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
                ToolDeployment(),
                new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
                RuntimeBinding(),
                ScenarioSchemaReceipt());
        (ToughTongueBuildGhostScenarioValidation validation, string? scenarioId) =
            await scenarios.CreatePrivateCandidateAsync(missing, "must-not-leave-process", CancellationToken.None);
        Assert.IsFalse(validation.Accepted);
        Assert.IsNull(scenarioId);
        CollectionAssert.Contains(
            missing.BlockingReasons.ToArray(),
            BuildGhostToughTongueCustomFunctionContract.MissingBindingBlocker);
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    public void Scenario_serialization_rejects_post_construction_attachment_drift()
    {
        ToughTongueBuildGhostScenarioCandidate candidate = ScenarioCandidate();
        JsonObject tamperedPayload = (JsonObject)candidate.Payload.DeepClone();
        tamperedPayload["custom_function_ids"]![0] = "attacker-value";
        ToughTongueBuildGhostScenarioCandidate tampered = candidate with { Payload = tamperedPayload };
        Assert.ThrowsExactly<InvalidDataException>(() => ToughTongueBuildGhostScenarioContract.SerializeCreatePayload(tampered));
    }

    [TestMethod]
    public async Task Scenario_creation_rejects_bundle_deployment_digest_url_size_and_field_drift_before_transport()
    {
        BuildGhostToughTongueCartesiaScenarioSchemaReceipt receipt = ScenarioSchemaReceipt();
        BuildGhostToughTongueCartesiaScenarioSchemaReceipt[] driftedReceipts =
        [
            receipt with { DeploymentId = "dpl_other" },
            receipt with { ScenarioReadBundleDigest = $"sha256:{new string('0', 64)}" },
            receipt with { ScenarioCreateBundleDigest = $"sha256:{new string('1', 64)}" },
            receipt with { ScenarioReadBundleUrl = new Uri("https://app.toughtongueai.com/_next/static/chunks/other.js") },
            receipt with { ScenarioCreateBundleBytes = receipt.ScenarioCreateBundleBytes + 1 },
            receipt with { CreateTtsProviderFieldPath = "ai_model_config.tts_provider" },
            receipt with { ReadTtsVoiceIdFieldPath = "tts_voice_id" }
        ];
        foreach (BuildGhostToughTongueCartesiaScenarioSchemaReceipt driftedReceipt in driftedReceipts)
        {
            RecordingHttpHandler handler = new(JsonResponse(new JsonObject()));
            ToughTongueBuildGhostScenarioClient scenarios = new(
                new HttpClient(handler) { BaseAddress = new Uri("https://api.toughtongueai.com/api/public/") },
                new FixedClock(),
                ScenarioConfiguration(mutationsEnabled: true));
            ToughTongueBuildGhostScenarioCandidate blocked = ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
                ToolDeployment(),
                new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
                RuntimeBinding(),
                driftedReceipt,
                CustomFunctionBinding());

            (ToughTongueBuildGhostScenarioValidation validation, string? scenarioId) =
                await scenarios.CreatePrivateCandidateAsync(blocked, "must-not-leave-process", CancellationToken.None);

            Assert.IsFalse(validation.Accepted);
            Assert.IsNull(scenarioId);
            Assert.IsNotEmpty(validation.RejectionReasons);
            Assert.IsEmpty(handler.Requests);
        }
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
            ScenarioSchemaReceipt(),
            CustomFunctionBinding());

        (ToughTongueBuildGhostScenarioValidation validation, string? scenarioId) = await scenarios.CreatePrivateCandidateAsync(
            candidate,
            "must-not-leave-process",
            CancellationToken.None);
        Assert.IsFalse(validation.Accepted);
        Assert.IsNull(scenarioId);
        CollectionAssert.Contains(validation.RejectionReasons.ToArray(), BuildGhostToughTongueCustomFunctionContract.ScenarioMutationPublicApiBlocker);
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => scenarios.CreateAccessGrantAsync(
            "0123456789abcdef01234567",
            "must-not-leave-process",
            CancellationToken.None));
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    public void Custom_function_bundle_receipt_pins_exact_deployment_chunks_paths_fields_and_runtime_attachment()
    {
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt receipt = CustomFunctionLibrarySchemaReceipt();

        Assert.IsEmpty(BuildGhostToughTongueCustomFunctionContract.ValidateLibrarySchema(receipt));
        CollectionAssert.Contains(
            BuildGhostToughTongueCustomFunctionContract.ValidateLibrarySchema(
                receipt with { ServiceChunkDigest = $"sha256:{new string('0', 64)}" }).ToArray(),
            "custom-function-service-chunk-digest-drift");
        CollectionAssert.Contains(
            BuildGhostToughTongueCustomFunctionContract.ValidateLibrarySchema(
                receipt with { ScenarioAttachmentField = "tools" }).ToArray(),
            "custom-function-scenario-attachment-field-drift");
        CollectionAssert.Contains(
            BuildGhostToughTongueCustomFunctionContract.ValidateLibrarySchema(
                receipt with { CreateFields = receipt.CreateFields.Reverse().ToArray() }).ToArray(),
            "custom-function-create-fields-drift");
    }

    [TestMethod]
    public void Empty_authenticated_library_array_uses_pinned_schema_without_claiming_observed_row_fields()
    {
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt schemaReceipt =
            CustomFunctionLibrarySchemaReceipt();
        BuildGhostToughTongueCustomFunctionLibraryReadReceipt readReceipt =
            CustomFunctionLibraryReadReceipt(schemaObserved: false);

        Assert.AreEqual(BuildGhostToughTongueCustomFunctionContract.JsonArrayResponseShape, readReceipt.JsonResponseShape);
        Assert.AreEqual(0, readReceipt.RowCount);
        Assert.IsFalse(readReceipt.JsonSchemaObserved);
        Assert.IsEmpty(readReceipt.ReturnedFields);
        Assert.IsEmpty(BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
            readReceipt,
            schemaReceipt,
            CustomFunctionAccountRef));

        BuildGhostToughTongueCustomFunctionDefinition withoutDynamicAuthorization =
            BuildGhostToughTongueCustomFunctionContract.CreateDefinition(
                ToolDeployment(),
                schemaReceipt,
                readReceipt,
                CustomFunctionAccountRef);
        Assert.IsTrue(withoutDynamicAuthorization.AuthenticatedLibraryReadVerified);
        Assert.IsFalse(withoutDynamicAuthorization.DynamicAuthorizationVerified);
        CollectionAssert.Contains(
            withoutDynamicAuthorization.BlockingReasons.ToArray(),
            BuildGhostToughTongueCustomFunctionContract.DynamicAuthorizationBlocker);
        Assert.ThrowsExactly<InvalidDataException>(() =>
            BuildGhostToughTongueCustomFunctionContract.SerializeCreatePayload(withoutDynamicAuthorization));

        BuildGhostToughTongueCustomFunctionDefinition definition =
            BuildGhostToughTongueCustomFunctionContract.CreateDefinition(
                ToolDeployment(),
                schemaReceipt,
                readReceipt,
                CustomFunctionAccountRef,
                DynamicAuthorizationReceipt(),
                DynamicAuthorizationReceiptDigest());
        Assert.IsTrue(definition.LibrarySchemaVerified);
        Assert.IsTrue(definition.AuthenticatedLibraryReadVerified);
        Assert.IsTrue(definition.DynamicAuthorizationVerified);
        Assert.IsEmpty(definition.BlockingReasons);
        Assert.AreEqual(
            BuildGhostToughTongueCustomFunctionContract.DigestLibraryReadReceipt(readReceipt),
            definition.LibraryReadReceiptDigest);
    }

    [TestMethod]
    public void Nonempty_authenticated_library_array_requires_exact_observed_row_fields()
    {
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt schemaReceipt =
            CustomFunctionLibrarySchemaReceipt();
        BuildGhostToughTongueCustomFunctionLibraryReadReceipt readReceipt =
            CustomFunctionLibraryReadReceipt();

        Assert.AreEqual(1, readReceipt.RowCount);
        Assert.IsTrue(readReceipt.JsonSchemaObserved);
        CollectionAssert.AreEqual(
            BuildGhostToughTongueCustomFunctionContract.ReturnedFields.ToArray(),
            readReceipt.ReturnedFields.ToArray());
        Assert.IsEmpty(BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
            readReceipt,
            schemaReceipt,
            CustomFunctionAccountRef));

        IReadOnlyList<string> missingFields =
            BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
                readReceipt with { JsonSchemaObserved = false, ReturnedFields = [] },
                schemaReceipt,
                CustomFunctionAccountRef);
        CollectionAssert.Contains(
            missingFields.ToArray(),
            "custom-function-library-read-schema-unverified");
    }

    [TestMethod]
    public void Empty_library_receipt_rejects_field_claims_invalid_shape_count_and_legacy_version()
    {
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt schemaReceipt =
            CustomFunctionLibrarySchemaReceipt();
        BuildGhostToughTongueCustomFunctionLibraryReadReceipt empty =
            CustomFunctionLibraryReadReceipt(schemaObserved: false);

        IReadOnlyList<string> inventedFields =
            BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
                empty with
                {
                    JsonSchemaObserved = true,
                    ReturnedFields = BuildGhostToughTongueCustomFunctionContract.ReturnedFields
                },
                schemaReceipt,
                CustomFunctionAccountRef);
        CollectionAssert.Contains(
            inventedFields.ToArray(),
            "custom-function-library-read-empty-schema-claim-invalid");
        CollectionAssert.Contains(
            inventedFields.ToArray(),
            "custom-function-library-read-empty-fields-claim-invalid");

        CollectionAssert.Contains(
            BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
                empty with { JsonResponseShape = "object" },
                schemaReceipt,
                CustomFunctionAccountRef).ToArray(),
            "custom-function-library-read-response-shape-invalid");
        CollectionAssert.Contains(
            BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
                empty with { RowCount = -1 },
                schemaReceipt,
                CustomFunctionAccountRef).ToArray(),
            "custom-function-library-read-row-count-invalid");
        CollectionAssert.Contains(
            BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
                empty with { Schema = ToughTongueBuildGhostContractVersions.CustomFunctionLibraryReadReceiptV1 },
                schemaReceipt,
                CustomFunctionAccountRef).ToArray(),
            "custom-function-library-read-version-invalid");
    }

    [TestMethod]
    public void Empty_library_receipt_fails_closed_when_separately_pinned_schema_drifts()
    {
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt driftedSchema =
            CustomFunctionLibrarySchemaReceipt() with
            {
                ReturnedFields = BuildGhostToughTongueCustomFunctionContract.ReturnedFields.Reverse().ToArray()
            };
        BuildGhostToughTongueCustomFunctionLibraryReadReceipt empty =
            CustomFunctionLibraryReadReceipt(schemaObserved: false);

        IReadOnlyList<string> failures =
            BuildGhostToughTongueCustomFunctionContract.ValidateAuthenticatedRead(
                empty,
                driftedSchema,
                CustomFunctionAccountRef);
        CollectionAssert.Contains(
            failures.ToArray(),
            BuildGhostToughTongueCustomFunctionContract.AuthenticatedLibraryReadSchemaBlocker);

        BuildGhostToughTongueCustomFunctionDefinition definition =
            BuildGhostToughTongueCustomFunctionContract.CreateDefinition(
                ToolDeployment(),
                driftedSchema,
                empty,
                CustomFunctionAccountRef,
                DynamicAuthorizationReceipt(),
                DynamicAuthorizationReceiptDigest());
        Assert.IsFalse(definition.LibrarySchemaVerified);
        Assert.IsFalse(definition.AuthenticatedLibraryReadVerified);
        CollectionAssert.Contains(
            definition.BlockingReasons.ToArray(),
            "custom-function-returned-fields-drift");
        CollectionAssert.Contains(
            definition.BlockingReasons.ToArray(),
            BuildGhostToughTongueCustomFunctionContract.AuthenticatedLibraryReadSchemaBlocker);
        Assert.ThrowsExactly<InvalidDataException>(() =>
            BuildGhostToughTongueCustomFunctionContract.SerializeCreatePayload(definition));
    }

    [TestMethod]
    public void Sanitized_401_library_probe_and_missing_dynamic_header_semantics_block_serialization()
    {
        BuildGhostToughTongueCustomFunctionDefinition definition =
            BuildGhostToughTongueCustomFunctionContract.CreateDefinition(
                ToolDeployment(),
                CustomFunctionLibrarySchemaReceipt(),
                CustomFunctionLibraryReadReceipt(status: 401, schemaObserved: false),
                CustomFunctionAccountRef);

        CollectionAssert.Contains(
            definition.BlockingReasons.ToArray(),
            BuildGhostToughTongueCustomFunctionContract.AuthenticatedLibraryReadBlocker);
        CollectionAssert.Contains(
            definition.BlockingReasons.ToArray(),
            BuildGhostToughTongueCustomFunctionContract.DynamicAuthorizationBlocker);
        Assert.ThrowsExactly<InvalidDataException>(() =>
            BuildGhostToughTongueCustomFunctionContract.SerializeCreatePayload(definition));
        string serialized = JsonSerializer.Serialize(definition);
        Assert.IsFalse(serialized.Contains("team-slot-4", StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains(CustomFunctionId, StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains("credential", StringComparison.OrdinalIgnoreCase));
    }

    [TestMethod]
    public void Verified_custom_function_definition_serializes_exact_provider_fields_and_rejects_auth_drift()
    {
        BuildGhostToughTongueCustomFunctionDefinition definition = CustomFunctionDefinition();
        JsonObject payload = BuildGhostToughTongueCustomFunctionContract.SerializeCreatePayload(definition);

        CollectionAssert.AreEqual(
            BuildGhostToughTongueCustomFunctionContract.CreateFields.ToArray(),
            payload.Select(static pair => pair.Key).ToArray());
        Assert.AreEqual("get_chummer_build_analysis", payload["name"]!.GetValue<string>());
        Assert.AreEqual("default", payload["function_type"]!.GetValue<string>());
        Assert.AreEqual("POST", payload["method"]!.GetValue<string>());
        Assert.AreEqual("https://canary.chummer.run/api/v1/ai/build-ghost/tool", payload["url"]!.GetValue<string>());
        Assert.AreEqual(120_000, payload["timeout_ms"]!.GetValue<int>());
        Assert.AreEqual("Bearer {{packet_access_key}}", payload["headers"]!["Authorization"]!.GetValue<string>());
        Assert.AreEqual(definition.ToolContractDigest, payload["headers"]!["X-Chummer-Build-Ghost-Tool-Contract"]!.GetValue<string>());
        Assert.IsEmpty(payload["query_params"]!.AsObject());
        Assert.IsNotNull(payload["parameters"]!["properties"]!["packet_access_key"]);

        JsonObject driftedPayload = (JsonObject)definition.Payload.DeepClone();
        driftedPayload["headers"]!["Authorization"] = "Bearer static-secret";
        BuildGhostToughTongueCustomFunctionDefinition drifted = definition with { Payload = driftedPayload };
        Assert.ThrowsExactly<InvalidDataException>(() =>
            BuildGhostToughTongueCustomFunctionContract.SerializeCreatePayload(drifted));
    }

    [TestMethod]
    public void Provider_v2_custom_function_uses_only_body_credential_and_rejects_dynamic_header_ambiguity()
    {
        BuildGhostPrivateToolDeploymentPackage deployment = ProviderToolDeployment();
        BuildGhostToughTongueCustomFunctionDefinition definition =
            BuildGhostToughTongueCustomFunctionContract.CreateDefinition(
                deployment,
                CustomFunctionLibrarySchemaReceipt(),
                CustomFunctionLibraryReadReceipt(schemaObserved: false),
                CustomFunctionAccountRef);

        Assert.AreEqual(ToughTongueBuildGhostContractVersions.CustomFunctionDefinitionV2, definition.Schema);
        Assert.AreEqual(BuildGhostToughTongueCustomFunctionContract.BodyCredentialAuthenticationMode, definition.AuthenticationMode);
        Assert.IsTrue(definition.AuthenticationVerified);
        Assert.IsFalse(definition.DynamicAuthorizationVerified);
        Assert.AreEqual(string.Empty, definition.DynamicAuthorizationReceiptDigest);
        Assert.AreEqual(
            BuildGhostPrivateToolDeploymentContract.BodyCredentialEvidenceDigest(deployment),
            definition.AuthenticationEvidenceDigest);
        Assert.IsEmpty(definition.BlockingReasons);

        JsonObject payload = BuildGhostToughTongueCustomFunctionContract.SerializeCreatePayload(definition);
        JsonObject headers = payload["headers"]!.AsObject();
        Assert.AreEqual(2, headers.Count);
        Assert.IsFalse(headers.ContainsKey("Authorization"));
        Assert.AreEqual("no-store", headers["Cache-Control"]!.GetValue<string>());
        Assert.AreEqual(deployment.Tool.ContractDigest, headers["X-Chummer-Build-Ghost-Tool-Contract"]!.GetValue<string>());
        Assert.AreEqual(deployment.Tool.Endpoint.AbsoluteUri, payload["url"]!.GetValue<string>());
        Assert.AreEqual(
            ToughTongueBuildGhostContractVersions.PrivateToolRequestV2,
            payload["parameters"]!["properties"]!["schema"]!["enum"]![0]!.GetValue<string>());

        BuildGhostToughTongueCustomFunctionDefinition ambiguous =
            BuildGhostToughTongueCustomFunctionContract.CreateDefinition(
                deployment,
                CustomFunctionLibrarySchemaReceipt(),
                CustomFunctionLibraryReadReceipt(schemaObserved: false),
                CustomFunctionAccountRef,
                DynamicAuthorizationReceipt(),
                DynamicAuthorizationReceiptDigest());
        Assert.IsFalse(ambiguous.AuthenticationVerified);
        CollectionAssert.Contains(
            ambiguous.BlockingReasons.ToArray(),
            BuildGhostToughTongueCustomFunctionContract.BodyCredentialDynamicHeaderBlocker);
        Assert.ThrowsExactly<InvalidDataException>(() =>
            BuildGhostToughTongueCustomFunctionContract.SerializeCreatePayload(ambiguous));

        JsonObject stored = (JsonObject)definition.Payload.DeepClone();
        stored["id"] = CustomFunctionId;
        BuildGhostToughTongueCustomFunctionBinding binding =
            BuildGhostToughTongueCustomFunctionContract.CreateBinding(
                definition,
                CustomFunctionId,
                200,
                stored,
                $"sha256:{new string('b', 64)}",
                DateTimeOffset.Parse("2026-08-22T04:00:00Z"));
        Assert.IsEmpty(BuildGhostToughTongueCustomFunctionContract.ValidateBinding(binding, deployment));
        Assert.IsFalse(JsonSerializer.Serialize(binding).Contains(CustomFunctionId, StringComparison.Ordinal));

        ToughTongueBuildGhostScenarioCandidate candidate =
            ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
                deployment,
                new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
                RuntimeBinding(),
                ScenarioSchemaReceipt(),
                binding);
        Assert.AreEqual(ToughTongueBuildGhostContractVersions.ScenarioContractV2, candidate.Schema);
        Assert.IsEmpty(candidate.BlockingReasons);
        Assert.AreEqual(
            deployment.Tool.Endpoint.AbsoluteUri,
            candidate.Payload["user_metadata"]!["tool_endpoint"]!.GetValue<string>());
        Assert.AreEqual(
            deployment.Tool.ContractDigest,
            candidate.Payload["user_metadata"]!["tool_contract_digest"]!.GetValue<string>());
        Assert.AreEqual(
            deployment.ContractDigest,
            candidate.Payload["user_metadata"]!["tool_deployment_digest"]!.GetValue<string>());
    }

    [TestMethod]
    public void Custom_function_binding_requires_exact_stored_readback_and_serializes_only_digests()
    {
        BuildGhostToughTongueCustomFunctionDefinition definition = CustomFunctionDefinition();
        BuildGhostToughTongueCustomFunctionBinding binding = CustomFunctionBinding();

        Assert.IsEmpty(BuildGhostToughTongueCustomFunctionContract.ValidateBinding(binding, ToolDeployment()));
        string serialized = JsonSerializer.Serialize(binding);
        Assert.IsFalse(serialized.Contains(CustomFunctionId, StringComparison.Ordinal));
        StringAssert.Contains(serialized, binding.ProviderCustomFunctionIdDigest);

        JsonObject drifted = StoredCustomFunction(definition);
        drifted["url"] = "https://attacker.invalid/tool";
        Assert.ThrowsExactly<ArgumentException>(() => BuildGhostToughTongueCustomFunctionContract.CreateBinding(
            definition,
            CustomFunctionId,
            200,
            drifted,
            $"sha256:{new string('a', 64)}",
            DateTimeOffset.Parse("2026-08-21T19:05:00Z")));
    }

    [TestMethod]
    public void Custom_function_attachment_receipt_requires_both_exact_reads_and_redacts_raw_ids()
    {
        BuildGhostToughTongueCustomFunctionBinding binding = CustomFunctionBinding();
        BuildGhostToughTongueCustomFunctionDefinition definition = CustomFunctionDefinition();
        JsonObject scenario = ProviderScenario(ScenarioCandidate());
        BuildGhostToughTongueCustomFunctionAttachmentReceipt receipt =
            BuildGhostToughTongueCustomFunctionContract.CreateAttachmentReceipt(
                "0123456789abcdef01234567",
                scenario,
                200,
                new JsonArray(StoredCustomFunction(definition)),
                200,
                binding,
                definition,
                DateTimeOffset.Parse("2026-08-21T19:10:00Z"));

        Assert.IsEmpty(receipt.BlockingReasons);
        Assert.IsEmpty(BuildGhostToughTongueCustomFunctionContract.ValidateAttachmentReceipt(receipt, binding));
        string serialized = JsonSerializer.Serialize(receipt);
        Assert.IsFalse(serialized.Contains("0123456789abcdef01234567", StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains(CustomFunctionId, StringComparison.Ordinal));

        BuildGhostToughTongueCustomFunctionAttachmentReceipt mismatch =
            BuildGhostToughTongueCustomFunctionContract.CreateAttachmentReceipt(
                "0123456789abcdef01234567",
                scenario,
                200,
                new JsonArray(),
                200,
                binding,
                definition,
                DateTimeOffset.Parse("2026-08-21T19:10:00Z"));
        CollectionAssert.Contains(
            mismatch.BlockingReasons.ToArray(),
            "custom-function-by-scenario-readback-mismatch");
        JsonObject driftedFunction = StoredCustomFunction(definition);
        driftedFunction["url"] = "https://attacker.invalid/tool";
        BuildGhostToughTongueCustomFunctionAttachmentReceipt payloadDrift =
            BuildGhostToughTongueCustomFunctionContract.CreateAttachmentReceipt(
                "0123456789abcdef01234567",
                scenario,
                200,
                new JsonArray(driftedFunction),
                200,
                binding,
                definition,
                DateTimeOffset.Parse("2026-08-21T19:10:00Z"));
        CollectionAssert.Contains(
            payloadDrift.BlockingReasons.ToArray(),
            "custom-function-by-scenario-readback-mismatch");
        CollectionAssert.Contains(
            BuildGhostToughTongueCustomFunctionContract.ValidateAttachmentReceipt(
                receipt with { RawIdsExposed = true }, binding).ToArray(),
            "custom-function-attachment-redaction-invalid");
    }

    [TestMethod]
    public async Task Cartesia_voice_deletion_requires_204_404_and_complete_owner_list_absence()
    {
        const string credential = "cartesia-test-credential-must-stay-redacted";
        RecordingHttpHandler handler = new(
            new HttpResponseMessage(System.Net.HttpStatusCode.NoContent),
            new HttpResponseMessage(System.Net.HttpStatusCode.NotFound),
            JsonResponse(new JsonObject
            {
                ["data"] = new JsonArray(),
                ["has_more"] = false,
                ["next_page"] = null
            }));
        BuildGhostCartesiaVoiceDeletionClient client = CartesiaDeletionClient(handler, enabled: true);

        BuildGhostCartesiaVoiceDeletionReceipt receipt = await client.DeleteAndVerifyAsync(
            CartesiaVoiceId,
            credential,
            CancellationToken.None);

        Assert.AreEqual("deleted-and-absence-verified", receipt.OutcomeStatus);
        Assert.AreEqual(204, receipt.DeleteHttpStatus);
        Assert.AreEqual(404, receipt.ReadbackHttpStatus);
        Assert.AreEqual(200, receipt.OwnerListHttpStatus);
        Assert.IsTrue(receipt.OwnerListAbsenceVerified);
        Assert.HasCount(3, handler.Requests);
        Assert.AreEqual(HttpMethod.Delete, handler.Requests[0].Method);
        Assert.AreEqual($"https://api.cartesia.ai/voices/{CartesiaVoiceId}", handler.Requests[0].Uri.AbsoluteUri);
        Assert.AreEqual(HttpMethod.Get, handler.Requests[1].Method);
        Assert.AreEqual($"https://api.cartesia.ai/voices/{CartesiaVoiceId}", handler.Requests[1].Uri.AbsoluteUri);
        Assert.AreEqual("https://api.cartesia.ai/voices?is_owner=true&limit=100", handler.Requests[2].Uri.AbsoluteUri);
        Assert.IsTrue(handler.Requests.All(static request => request.HasBearerCredential));
        Assert.IsTrue(handler.Requests.All(static request => request.ApiVersion == BuildGhostCartesiaVoiceDeletionClient.ApiVersion));
        string rendered = JsonSerializer.Serialize(receipt);
        Assert.IsFalse(rendered.Contains(CartesiaVoiceId, StringComparison.Ordinal));
        Assert.IsFalse(rendered.Contains(credential, StringComparison.Ordinal));
    }

    [TestMethod]
    public async Task Cartesia_voice_deletion_disabled_mismatched_and_replayed_authorizations_make_zero_calls()
    {
        RecordingHttpHandler disabledHandler = new();
        BuildGhostCartesiaVoiceDeletionReceipt disabled = await CartesiaDeletionClient(disabledHandler, enabled: false)
            .DeleteAndVerifyAsync(CartesiaVoiceId, "credential", CancellationToken.None);
        Assert.AreEqual("blocked", disabled.OutcomeStatus);
        Assert.IsEmpty(disabledHandler.Requests);

        RecordingHttpHandler mismatchHandler = new();
        IConfiguration mismatchConfiguration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostCartesiaVoiceDeletionClient.ExecuteEnabledConfigurationKey] = "true",
            [BuildGhostCartesiaVoiceDeletionClient.AuthorizedVoiceDigestConfigurationKey] = $"sha256:{new string('0', 64)}"
        }).Build();
        BuildGhostCartesiaVoiceDeletionClient mismatchClient = new(
            new HttpClient(mismatchHandler) { BaseAddress = new Uri("https://api.cartesia.ai/") },
            mismatchConfiguration,
            new FixedClock());
        BuildGhostCartesiaVoiceDeletionReceipt mismatch = await mismatchClient.DeleteAndVerifyAsync(
            CartesiaVoiceId,
            "credential",
            CancellationToken.None);
        Assert.AreEqual("blocked", mismatch.OutcomeStatus);
        Assert.IsEmpty(mismatchHandler.Requests);

        RecordingHttpHandler replayHandler = new(
            new HttpResponseMessage(System.Net.HttpStatusCode.NoContent),
            new HttpResponseMessage(System.Net.HttpStatusCode.NotFound),
            JsonResponse(new JsonObject { ["data"] = new JsonArray(), ["has_more"] = false, ["next_page"] = null }));
        BuildGhostCartesiaVoiceDeletionClient replayClient = CartesiaDeletionClient(replayHandler, enabled: true);
        BuildGhostCartesiaVoiceDeletionReceipt first = await replayClient.DeleteAndVerifyAsync(
            CartesiaVoiceId,
            "credential",
            CancellationToken.None);
        BuildGhostCartesiaVoiceDeletionReceipt replay = await replayClient.DeleteAndVerifyAsync(
            CartesiaVoiceId,
            "credential",
            CancellationToken.None);
        Assert.AreEqual("deleted-and-absence-verified", first.OutcomeStatus);
        Assert.AreEqual("blocked", replay.OutcomeStatus);
        CollectionAssert.Contains(replay.BlockingReasons.ToArray(), "cartesia-voice-deletion-authorization-replay-rejected");
        Assert.HasCount(3, replayHandler.Requests);
    }

    [TestMethod]
    public async Task Cartesia_voice_deletion_errors_and_Tough_Tongue_cleanup_blocker_are_redacted()
    {
        const string credential = "cartesia-error-secret";
        HttpResponseMessage failure = new(System.Net.HttpStatusCode.InternalServerError)
        {
            Content = new StringContent($"provider leaked {credential} {CartesiaVoiceId}")
        };
        RecordingHttpHandler handler = new(failure);
        BuildGhostCartesiaVoiceDeletionReceipt receipt = await CartesiaDeletionClient(handler, enabled: true)
            .DeleteAndVerifyAsync(CartesiaVoiceId, credential, CancellationToken.None);
        string rendered = JsonSerializer.Serialize(receipt);

        Assert.AreEqual("failed", receipt.OutcomeStatus);
        Assert.HasCount(1, handler.Requests);
        Assert.IsFalse(rendered.Contains(credential, StringComparison.Ordinal));
        Assert.IsFalse(rendered.Contains(CartesiaVoiceId, StringComparison.Ordinal));
        Assert.IsFalse(receipt.RawResponseExposed);
        Assert.IsFalse(receipt.RawVoiceIdExposed);
        Assert.IsFalse(receipt.CredentialExposed);

        const string scenarioId = "0123456789abcdef01234567";
        ToughTongueBuildGhostScenarioDeletionBlockerReceipt blocker =
            ToughTongueBuildGhostScenarioCleanupContract.CreateBlockedReceipt(scenarioId, new FixedClock());
        Assert.AreEqual("blocked", blocker.OutcomeStatus);
        Assert.IsFalse(blocker.TransportAttempted);
        CollectionAssert.Contains(blocker.BlockingReasons.ToArray(),
            ToughTongueBuildGhostScenarioCleanupContract.UndocumentedDeletionBlocker);
        Assert.IsFalse(JsonSerializer.Serialize(blocker).Contains(scenarioId, StringComparison.Ordinal));
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

    private static BuildGhostPrivateToolDeploymentPackage ProviderToolDeployment()
        => BuildGhostPrivateToolDeploymentContract.CreateProviderBodyKeyV2(
            new Uri("https://canary.chummer.run/api/v2/ai/build-ghost/tool"),
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

    private static BuildGhostToughTongueCartesiaScenarioSchemaReceipt ScenarioSchemaReceipt()
        => new(
            ToughTongueBuildGhostContractVersions.CartesiaScenarioSchemaReceiptV1,
            ToughTongueBuildGhostVoiceProviders.CartesiaNamespace,
            BuildGhostToughTongueCartesiaScenarioSchemaContract.VerifiedDeploymentId,
            new Uri(BuildGhostToughTongueCartesiaScenarioSchemaContract.VerifiedScenarioReadBundleUrl),
            BuildGhostToughTongueCartesiaScenarioSchemaContract.VerifiedScenarioReadBundleDigest,
            BuildGhostToughTongueCartesiaScenarioSchemaContract.VerifiedScenarioReadBundleBytes,
            new Uri(BuildGhostToughTongueCartesiaScenarioSchemaContract.VerifiedScenarioCreateBundleUrl),
            BuildGhostToughTongueCartesiaScenarioSchemaContract.VerifiedScenarioCreateBundleDigest,
            BuildGhostToughTongueCartesiaScenarioSchemaContract.VerifiedScenarioCreateBundleBytes,
            BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsProviderFieldPath,
            BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsVoiceIdFieldPath,
            BuildGhostToughTongueCartesiaScenarioSchemaContract.ReadTtsProviderFieldPath,
            BuildGhostToughTongueCartesiaScenarioSchemaContract.ReadTtsVoiceIdFieldPath,
            ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider,
            DateTimeOffset.Parse("2026-08-21T17:21:00Z"));

    private static BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt CustomFunctionLibrarySchemaReceipt()
        => new(
            ToughTongueBuildGhostContractVersions.CustomFunctionLibrarySchemaReceiptV1,
            BuildGhostToughTongueCustomFunctionContract.ProviderNamespace,
            BuildGhostToughTongueCustomFunctionContract.VerifiedDeploymentId,
            BuildGhostToughTongueCustomFunctionContract.ServiceChunkName,
            BuildGhostToughTongueCustomFunctionContract.ServiceChunkDigest,
            BuildGhostToughTongueCustomFunctionContract.ServiceChunkBytes,
            BuildGhostToughTongueCustomFunctionContract.StudioChunkName,
            BuildGhostToughTongueCustomFunctionContract.StudioChunkDigest,
            BuildGhostToughTongueCustomFunctionContract.StudioChunkBytes,
            BuildGhostToughTongueCustomFunctionContract.ScenarioServiceChunkName,
            BuildGhostToughTongueCustomFunctionContract.ScenarioServiceChunkDigest,
            BuildGhostToughTongueCustomFunctionContract.ScenarioServiceChunkBytes,
            BuildGhostToughTongueCustomFunctionContract.RuntimeChunkName,
            BuildGhostToughTongueCustomFunctionContract.RuntimeChunkDigest,
            BuildGhostToughTongueCustomFunctionContract.RuntimeChunkBytes,
            new Uri(BuildGhostToughTongueCustomFunctionContract.ApiBaseUrl),
            BuildGhostToughTongueCustomFunctionContract.ListPath,
            BuildGhostToughTongueCustomFunctionContract.ByScenarioPathTemplate,
            BuildGhostToughTongueCustomFunctionContract.CreatePath,
            BuildGhostToughTongueCustomFunctionContract.UpdatePathTemplate,
            BuildGhostToughTongueCustomFunctionContract.ExecutePathTemplate,
            BuildGhostToughTongueCustomFunctionContract.DeletePathTemplate,
            BuildGhostToughTongueCustomFunctionContract.ScenarioUpsertPath,
            BuildGhostToughTongueCustomFunctionContract.CreateFields,
            BuildGhostToughTongueCustomFunctionContract.ReturnedFields,
            BuildGhostToughTongueCustomFunctionContract.ScenarioAttachmentField,
            BuildGhostToughTongueCustomFunctionContract.RuntimeRegistrationPrefix,
            DateTimeOffset.Parse("2026-08-21T18:45:00Z"));

    private static BuildGhostToughTongueCustomFunctionLibraryReadReceipt CustomFunctionLibraryReadReceipt(
        int status = 200,
        bool schemaObserved = true)
        => new(
            ToughTongueBuildGhostContractVersions.CustomFunctionLibraryReadReceiptV2,
            new Uri("https://api.toughtongueai.com/api/custom-functions/"),
            "GET",
            "team-slot-4",
            CustomFunctionAccountRef,
            status,
            BuildGhostToughTongueCustomFunctionContract.JsonArrayResponseShape,
            schemaObserved ? 1 : 0,
            schemaObserved,
            schemaObserved ? BuildGhostToughTongueCustomFunctionContract.ReturnedFields : [],
            status == 200 ? $"sha256:{new string('8', 64)}" : string.Empty,
            RawResponseExposed: false,
            RawIdsExposed: false,
            CredentialExposed: false,
            DateTimeOffset.Parse("2026-08-21T18:50:31Z"));

    private static BuildGhostToughTongueDynamicAuthorizationReceipt DynamicAuthorizationReceipt()
        => new(
            ToughTongueBuildGhostContractVersions.CustomFunctionDynamicAuthorizationReceiptV1,
            BuildGhostToughTongueCustomFunctionContract.ProviderNamespace,
            BuildGhostToughTongueCustomFunctionContract.VerifiedDeploymentId,
            "future-official-dynamic-header-evidence.js",
            $"sha256:{new string('9', 64)}",
            "Authorization",
            "Bearer {{packet_access_key}}",
            "packet_access_key",
            "stored-header-values-interpolate-execute-args",
            StoredHeaderValuesInterpolateToolArguments: true,
            DateTimeOffset.Parse("2026-08-21T19:00:00Z"));

    private static string DynamicAuthorizationReceiptDigest()
        => BuildGhostToughTongueCustomFunctionContract.DigestDynamicAuthorizationReceipt(DynamicAuthorizationReceipt());

    private static BuildGhostToughTongueCustomFunctionDefinition CustomFunctionDefinition(
        BuildGhostToughTongueCustomFunctionLibraryReadReceipt? readReceipt = null,
        BuildGhostToughTongueDynamicAuthorizationReceipt? dynamicReceipt = null,
        string? trustedDynamicReceiptDigest = null)
        => BuildGhostToughTongueCustomFunctionContract.CreateDefinition(
            ToolDeployment(),
            CustomFunctionLibrarySchemaReceipt(),
            readReceipt ?? CustomFunctionLibraryReadReceipt(),
            CustomFunctionAccountRef,
            dynamicReceipt ?? DynamicAuthorizationReceipt(),
            trustedDynamicReceiptDigest ?? DynamicAuthorizationReceiptDigest());

    private static JsonObject StoredCustomFunction(BuildGhostToughTongueCustomFunctionDefinition definition)
    {
        JsonObject stored = (JsonObject)definition.Payload.DeepClone();
        stored["id"] = CustomFunctionId;
        return stored;
    }

    private static BuildGhostToughTongueCustomFunctionBinding CustomFunctionBinding()
    {
        BuildGhostToughTongueCustomFunctionDefinition definition = CustomFunctionDefinition();
        return BuildGhostToughTongueCustomFunctionContract.CreateBinding(
            definition,
            CustomFunctionId,
            200,
            StoredCustomFunction(definition),
            $"sha256:{new string('a', 64)}",
            DateTimeOffset.Parse("2026-08-21T19:05:00Z"));
    }

    private static ToughTongueBuildGhostScenarioCandidate ScenarioCandidate()
        => ToughTongueBuildGhostScenarioContract.CreatePrivateRookCandidate(
            ToolDeployment(),
            new Uri("https://canary.chummer.run/assets/build-ghosts/rook-female-ork-decker-v1.png"),
            RuntimeBinding(),
            ScenarioSchemaReceipt(),
            CustomFunctionBinding());

    private static JsonObject ProviderScenario(ToughTongueBuildGhostScenarioCandidate candidate)
    {
        JsonObject scenario = (JsonObject)candidate.Payload.DeepClone();
        string ttsProvider = scenario[BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsProviderFieldPath]!.GetValue<string>();
        string ttsVoiceId = scenario[BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsVoiceIdFieldPath]!.GetValue<string>();
        scenario.Remove(BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsProviderFieldPath);
        scenario.Remove(BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsVoiceIdFieldPath);
        scenario["ai_model_config"]!["tts_provider"] = ttsProvider;
        scenario["ai_model_config"]!["tts_voice_id"] = ttsVoiceId;
        scenario["id"] = "0123456789abcdef01234567";
        return scenario;
    }

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

    private static BuildGhostCartesiaVoiceDeletionClient CartesiaDeletionClient(
        HttpMessageHandler handler,
        bool enabled)
    {
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostCartesiaVoiceDeletionClient.ExecuteEnabledConfigurationKey] = enabled.ToString(),
            [BuildGhostCartesiaVoiceDeletionClient.AuthorizedVoiceDigestConfigurationKey] =
                BuildGhostCartesiaVoiceDeletionClient.VoiceIdDigest(CartesiaVoiceId)
        }).Build();
        return new BuildGhostCartesiaVoiceDeletionClient(
            new HttpClient(handler) { BaseAddress = new Uri("https://api.cartesia.ai/") },
            configuration,
            new FixedClock());
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
                body,
                request.Headers.TryGetValues("Cartesia-Version", out IEnumerable<string>? versions)
                    ? versions.Single()
                    : string.Empty));
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
        string? Body,
        string ApiVersion);
}
