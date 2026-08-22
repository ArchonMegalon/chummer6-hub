using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class ToughTongueBuildGhostPremiumLiveAvatarContractTests
{
    [TestMethod]
    public void Current_premium_live_avatar_schema_pins_anam_heygen_landmass_costs_and_runtime_fields()
    {
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt = CurrentReceipt();

        Assert.IsEmpty(BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Validate(receipt));
        CollectionAssert.AreEqual(
            new[]
            {
                ToughTongueBuildGhostLiveAvatarProviders.Anam,
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
    public void Anam_and_heygen_bindings_are_digest_bound_without_serializing_raw_avatar_ids()
    {
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt = CurrentReceipt();
        foreach ((string provider, string avatarId) in new[]
                 {
                     (ToughTongueBuildGhostLiveAvatarProviders.Anam, "rook-anam-persona-v1"),
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

        Assert.ThrowsExactly<ArgumentException>(() =>
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.CreateBinding(
                receipt,
                "avatario",
                "rook-avatar"));
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

        ToughTongueBuildGhostScenarioCandidate candidate =
            ToughTongueBuildGhostScenarioContract.CreatePrivateRookPremiumLiveAvatarCandidate(
                deployment,
                new Uri("https://cdn.chummer.run/build-ghost/rook.png"),
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
}
