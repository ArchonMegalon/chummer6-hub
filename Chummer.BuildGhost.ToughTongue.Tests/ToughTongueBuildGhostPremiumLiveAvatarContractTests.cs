using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class ToughTongueBuildGhostPremiumLiveAvatarContractTests
{
    [TestMethod]
    public void Current_cartesia_and_custom_function_evidence_uses_the_same_verified_deployment()
    {
        const string deployment = "dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i";
        DateTimeOffset observedAtUtc = DateTimeOffset.Parse("2026-08-22T05:35:00Z");
        BuildGhostToughTongueCartesiaScenarioSchemaReceipt cartesia = new(
            "chummer.tough_tongue.cartesia_scenario_schema_receipt.v1",
            "cartesia",
            deployment,
            new Uri("https://app.toughtongueai.com/_next/static/chunks/0m4xondr3o4oe.js?dpl=dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i"),
            "sha256:7ba4d63277d18d2ff8c2ffd3128576a1ad15e4670e4f4c9921b6846de6ba71d7",
            219_531,
            new Uri("https://app.toughtongueai.com/_next/static/chunks/04i2xipv9rrh-.js?dpl=dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i"),
            "sha256:01c2f887b5970283734c086bdbf1c3ec1e6af8f6e07a62e229c0f8cd96f5c1eb",
            166_081,
            "tts_provider",
            "tts_voice_id",
            "ai_model_config.tts_provider",
            "ai_model_config.tts_voice_id",
            "Cartesia",
            observedAtUtc);
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt customFunctions = new(
            "chummer.tough_tongue.custom_function_library_schema_receipt.v1",
            "tough-tongue",
            deployment,
            "08a43for7u2by.js",
            "sha256:c82bf0103f53edbc5933f9b6b4aa8716ba05119412b8cff447c1338a22ffa1cc",
            43_729,
            "0dic_u.sbe1xm.js",
            "sha256:7e22f357c2ebe5e9f6988f6fa4cfec1c332ebf3c0f573e5dc31feaeefcf5c7e7",
            499_677,
            "06i87mpuoc~sp.js",
            "sha256:361eee45d31a83d6a5cbf1883184a92a4c873c4afaa5f0045fc5fe2dbb08bfe6",
            53_767,
            "0m4xondr3o4oe.js",
            "sha256:7ba4d63277d18d2ff8c2ffd3128576a1ad15e4670e4f4c9921b6846de6ba71d7",
            219_531,
            new Uri("https://api.toughtongueai.com/api/"),
            "custom-functions/",
            "custom-functions/by-scenario/{scenario}",
            "custom-functions/",
            "custom-functions/{id}",
            "custom-functions/{id}/execute",
            "custom-functions/{id}",
            "scenarios/upsert",
            ["name", "description", "function_type", "method", "url", "timeout_ms", "headers", "query_params", "parameters"],
            ["id", "name", "description", "function_type", "method", "url", "timeout_ms", "headers", "query_params", "parameters"],
            "custom_function_ids",
            "api_",
            observedAtUtc);

        Assert.IsEmpty(BuildGhostToughTongueCartesiaScenarioSchemaContract.Validate(cartesia));
        Assert.IsEmpty(BuildGhostToughTongueCustomFunctionContract.ValidateLibrarySchema(customFunctions));
    }

    [TestMethod]
    public void Current_premium_live_avatar_schema_pins_anam_avatario_heygen_landmass_costs_and_runtime_fields()
    {
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt = CurrentReceipt();

        Assert.IsEmpty(BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Validate(receipt));
        CollectionAssert.AreEqual(
            new[]
            {
                ToughTongueBuildGhostLiveAvatarProviders.Anam,
                ToughTongueBuildGhostLiveAvatarProviders.Avatario,
                ToughTongueBuildGhostLiveAvatarProviders.HeyGen
            },
            receipt.AllowedProviders.ToArray());
        Assert.AreEqual("appearance.live_avatar_id", receipt.ScenarioLiveAvatarIdFieldPath);
        Assert.AreEqual("appearance.live_avatar_provider", receipt.ScenarioLiveAvatarProviderFieldPath);
        Assert.AreEqual("avatar_config.enabled", receipt.RuntimeEnabledFieldPath);
        Assert.AreEqual("avatar_config.avatar_id", receipt.RuntimeAvatarIdFieldPath);
        Assert.AreEqual("avatar_config.provider", receipt.RuntimeProviderFieldPath);
        Assert.AreEqual("Landmass", receipt.RequiredModelProvider);
        Assert.AreEqual(2m, receipt.AnamMinutesMultiplier);
        Assert.AreEqual(2m, receipt.HeyGenMinutesMultiplier);
        Assert.IsTrue(receipt.ProviderManagedLipSynchronizationAdvertised);
    }

    [TestMethod]
    public void Governed_provider_bindings_are_digest_bound_without_serializing_raw_avatar_ids()
    {
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt = CurrentReceipt();
        foreach ((string provider, string avatarId) in new[]
                 {
                     (ToughTongueBuildGhostLiveAvatarProviders.Anam, "rook-anam-persona-v1"),
                     (ToughTongueBuildGhostLiveAvatarProviders.Avatario, "11111111-2222-4333-8444-555555555555"),
                     (ToughTongueBuildGhostLiveAvatarProviders.HeyGen, "1c690fe7-23e0-49f9-bfba-14344450285b")
                 })
        {
            BuildGhostToughTonguePremiumLiveAvatarBinding binding =
                BuildGhostToughTonguePremiumLiveAvatarSchemaContract.CreateBinding(
                    receipt,
                    provider,
                    avatarId);

            Assert.IsEmpty(
                BuildGhostToughTonguePremiumLiveAvatarSchemaContract.ValidateBinding(
                    binding,
                    receipt));
            Assert.AreEqual(provider, binding.Provider);
            Assert.AreEqual("Landmass", binding.RequiredModelProvider);
            Assert.AreEqual(2m, binding.MinutesMultiplier);
            Assert.IsTrue(binding.ProviderManagedLipSynchronization);
            Assert.IsTrue(binding.ProviderAvatarIdDigest.StartsWith("sha256:", StringComparison.Ordinal));
            Assert.IsTrue(binding.ContractDigest.StartsWith("sha256:", StringComparison.Ordinal));
            Assert.IsFalse(JsonSerializer.Serialize(binding).Contains(avatarId, StringComparison.Ordinal));
        }
    }

    [TestMethod]
    public void Unapproved_provider_or_bundle_drift_fails_closed()
    {
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt = CurrentReceipt();

        foreach (string provider in new[] { "avatari0", "arbitrary-provider" })
        {
            Assert.ThrowsExactly<ArgumentException>(() =>
                BuildGhostToughTonguePremiumLiveAvatarSchemaContract.CreateBinding(
                    receipt,
                    provider,
                    "rook-avatar"));
        }
        IReadOnlyList<string> failures =
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Validate(
                receipt with { StudioBundleDigest = $"sha256:{new string('0', 64)}" });
        CollectionAssert.Contains(
            failures.ToArray(),
            "premium-live-avatar-studio-bundle-digest-drift");
    }

    [TestMethod]
    public void Scenario_read_paths_are_exact_and_do_not_guess_missing_fields()
    {
        JsonObject scenario = new()
        {
            ["appearance"] = new JsonObject
            {
                ["live_avatar_id"] = "rook-anam-persona-v1",
                ["live_avatar_provider"] = "anam"
            }
        };

        Assert.AreEqual(
            "rook-anam-persona-v1",
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Read(
                scenario,
                BuildGhostToughTonguePremiumLiveAvatarSchemaContract.ScenarioLiveAvatarIdFieldPath));
        Assert.AreEqual(
            "anam",
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Read(
                scenario,
                BuildGhostToughTonguePremiumLiveAvatarSchemaContract.ScenarioLiveAvatarProviderFieldPath));
        Assert.AreEqual(
            string.Empty,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Read(
                scenario,
            "appearance.missing"));
    }

    [TestMethod]
    public void Private_rook_live_avatar_candidate_binds_provider_fields_and_defers_local_lip_sync()
    {
        BuildGhostPrivateToolDeploymentPackage deployment =
            BuildGhostPrivateToolDeploymentContract.Create(
                new Uri("https://private.chummer.run/api/v1/ai/build-ghost/tool"),
                "chummer.build-ghost.private");
        const string cartesiaVoiceId = "f161df88-b5a0-4ea8-aa21-6be12859f761";
        BuildGhostCascadePrivateVoiceBinding voiceBinding =
            BuildGhostCascadePrivateVoiceBindingContract.Create(
                new BuildGhostCartesiaPrivateVoiceReadReceipt(
                    ToughTongueBuildGhostContractVersions.CartesiaPrivateVoiceReadReceiptV1,
                    ToughTongueBuildGhostVoiceProviders.CartesiaNamespace,
                    cartesiaVoiceId,
                    cartesiaVoiceId,
                    200,
                    IsOwner: true,
                    Access: "private",
                    Visibility: "owner",
                    ToughTongueBuildGhostVoiceProviders.FullySyntheticProvenance,
                    $"sha256:{new string('1', 64)}",
                    $"sha256:{new string('2', 64)}",
                    DateTimeOffset.Parse("2026-08-22T05:35:00Z")),
                ToughTongueBuildGhostScenarioContract.CanonicalLocales);
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt = CurrentReceipt();
        BuildGhostToughTonguePremiumLiveAvatarBinding liveAvatarBinding =
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.CreateBinding(
                receipt,
                ToughTongueBuildGhostLiveAvatarProviders.Anam,
                "rook-anam-persona-v1");

        BuildGhostToughTongueStockAvatarReadbackReceipt stockReceipt =
            StockAvatarReadbackReceipt();
        ToughTongueBuildGhostScenarioCandidate candidate =
            ToughTongueBuildGhostScenarioContract.CreatePrivateRookPremiumLiveAvatarCandidate(
                deployment,
                BuildGhostToughTongueStockAvatarBindingContract.CreateReadVerified(
                    stockReceipt,
                    $"sha256:{new string('a', 64)}",
                    $"sha256:{new string('a', 64)}",
                    BuildGhostToughTongueStockAvatarBindingContract.ComputeReadbackReceiptFileDigest(
                        stockReceipt)),
                voiceBinding,
                liveAvatarBinding,
                receipt);

        JsonObject appearance = candidate.Payload["appearance"]!.AsObject();
        JsonObject metadata = candidate.Payload["user_metadata"]!.AsObject();
        Assert.AreEqual("rook-anam-persona-v1", appearance["live_avatar_id"]!.GetValue<string>());
        Assert.AreEqual("anam", appearance["live_avatar_provider"]!.GetValue<string>());
        Assert.AreEqual("provider-managed", metadata["live_avatar_render_posture"]!.GetValue<string>());
        Assert.AreEqual("deferred", metadata["local_lip_sync_posture"]!.GetValue<string>());
        Assert.AreEqual(liveAvatarBinding.ProviderAvatarIdDigest, metadata["live_avatar_id_digest"]!.GetValue<string>());
        Assert.AreEqual(liveAvatarBinding.ContractDigest, candidate.LiveAvatarBindingDigest);
        Assert.IsTrue(candidate.LiveAvatarSchemaVerified);
        Assert.AreEqual("appearance.live_avatar_id", candidate.LiveAvatarIdFieldPath);
        Assert.AreEqual("appearance.live_avatar_provider", candidate.LiveAvatarProviderFieldPath);
        Assert.IsTrue(candidate.BlockingReasons.Contains(
            BuildGhostToughTongueCustomFunctionContract.MissingBindingBlocker,
            StringComparer.Ordinal));
    }

    private static BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt CurrentReceipt()
        => new(
            ToughTongueBuildGhostContractVersions.PremiumLiveAvatarSchemaReceiptV1,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.ProviderNamespace,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedDeploymentId,
            new Uri(BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedStudioBundleUrl),
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedStudioBundleDigest,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedStudioBundleBytes,
            new Uri(BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedScenarioRuntimeBundleUrl),
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedScenarioRuntimeBundleDigest,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedScenarioRuntimeBundleBytes,
            new Uri(BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedSessionCreateBundleUrl),
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedSessionCreateBundleDigest,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.VerifiedSessionCreateBundleBytes,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.ScenarioLiveAvatarIdFieldPath,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.ScenarioLiveAvatarProviderFieldPath,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.RuntimeEnabledFieldPath,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.RuntimeAvatarIdFieldPath,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.RuntimeProviderFieldPath,
            ToughTongueBuildGhostLiveAvatarProviders.RequiredModelProvider,
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.AllowedProviders,
            ToughTongueBuildGhostLiveAvatarProviders.PremiumMinutesMultiplier,
            ToughTongueBuildGhostLiveAvatarProviders.PremiumMinutesMultiplier,
            ProviderManagedLipSynchronizationAdvertised: true,
            DateTimeOffset.Parse("2026-08-22T05:35:00Z"));

    private static BuildGhostToughTongueStockAvatarReadbackReceipt StockAvatarReadbackReceipt()
    {
        const string liveAvatarId = "11111111-2222-4333-8444-555555555555";
        const string scenarioRef = "private-stock-scenario-ref";
        BuildGhostToughTongueStockAvatarReadbackReceipt receipt = new(
            ToughTongueBuildGhostContractVersions.StockAvatarReadbackReceiptV1,
            200,
            string.Empty,
            ToughTongueBuildGhostStockAvatarSelections.ProviderNamespace,
            ToughTongueBuildGhostStockAvatarSelections.SelectedAvatarName,
            ToughTongueBuildGhostStockAvatarSelections.SelectedAvatarAssetPath,
            liveAvatarId,
            ToughTongueBuildGhostStockAvatarSelections.RequiredModelProvider,
            ToughTongueBuildGhostStockAvatarSelections.CurrentModelId,
            false,
            $"sha256:{Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(scenarioRef))).ToLowerInvariant()}",
            BuildGhostToughTongueStockAvatarBindingContract.RequiredReadbackSource,
            DateTimeOffset.UtcNow.AddMinutes(-1).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"),
            BuildGhostToughTongueStockAvatarBindingContract.MaximumPermittedAgeSeconds,
            string.Empty);
        receipt = receipt with
        {
            CanonicalWhitelistedResponseDigest =
                BuildGhostToughTongueStockAvatarBindingContract.ComputeCanonicalWhitelistedResponseDigest(receipt)
        };
        return receipt with
        {
            ReceiptDigest = BuildGhostToughTongueStockAvatarBindingContract.ComputeReadbackReceiptDigest(receipt)
        };
    }
}
