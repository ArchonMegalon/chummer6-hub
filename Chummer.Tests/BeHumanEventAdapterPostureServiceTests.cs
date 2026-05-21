using System;
using System.Collections.Generic;
using System.IO;
using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class BeHumanEventAdapterPostureServiceTests
{
    [Fact]
    public void Defaults_fail_closed_when_adapter_is_not_enabled()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>())
            .Build();

        BeHumanEventAdapterPosture posture = new BeHumanEventAdapterPostureService(configuration).Build();

        Assert.Equal("NOT_READY", posture.Verdict);
        Assert.False(posture.AdapterEnabled);
        Assert.False(posture.ProviderVerified);
        Assert.False(posture.CapacityClaimAllowed);
        Assert.Equal("disabled", posture.OperatingMode);
        Assert.Contains("account_identity_truth", posture.ForbiddenTruthDomains);
        Assert.Contains("black_ledger_faction_events", posture.AllowedEventFamilies);
    }

    [Fact]
    public void Enabled_adapter_without_verified_receipt_stays_not_ready()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Community:BeHuman:Enabled"] = "true",
                ["Community:BeHuman:Mode"] = "api_verified",
                ["Community:BeHuman:ProviderVerificationReceiptPath"] = "/tmp/missing-behuman-receipt.yaml",
                ["BEHUMAN_API_KEY"] = "secret"
            })
            .Build();

        BeHumanEventAdapterPosture posture = new BeHumanEventAdapterPostureService(configuration).Build();

        Assert.Equal("NOT_READY", posture.Verdict);
        Assert.True(posture.AdapterEnabled);
        Assert.False(posture.ProviderVerified);
        Assert.False(posture.CapacityClaimAllowed);
        Assert.Contains("missing or invalid", posture.FailureReason, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Verified_manual_mode_becomes_ready_without_capacity_overclaim()
    {
        string root = Path.Combine(Path.GetTempPath(), $"behuman-posture-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        string receipt = Path.Combine(root, "behuman-verification.yaml");
        File.WriteAllText(
            receipt,
            "provider: behuman.online\nverified: true\nplan: 10-keys\n",
            System.Text.Encoding.UTF8);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["Community:BeHuman:Enabled"] = "true",
                    ["Community:BeHuman:Mode"] = "manual",
                    ["Community:BeHuman:ProviderVerificationReceiptPath"] = receipt
                })
                .Build();

            BeHumanEventAdapterPosture posture = new BeHumanEventAdapterPostureService(configuration).Build();

            Assert.Equal("BEHUMAN_EVENT_ADAPTER_READY", posture.Verdict);
            Assert.True(posture.AdapterEnabled);
            Assert.True(posture.ProviderVerified);
            Assert.False(posture.SecretsConfigured);
            Assert.False(posture.CapacityClaimAllowed);
            Assert.Null(posture.VerifiedRegistrationCapacity);
        }
        finally
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }
}
