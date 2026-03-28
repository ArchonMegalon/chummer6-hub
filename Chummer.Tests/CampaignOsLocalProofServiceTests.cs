using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignOsLocalProofServiceTests
{
    [Fact]
    public void LoadProofReturnsCampaignOsProofFromCanonRoot()
    {
        using var fixture = new CampaignOsLocalProofFixture();
        fixture.WriteProof("chummer6-hub.campaign_os_local_proof");

        var proof = fixture.CreateService().LoadProof();

        Assert.NotNull(proof);
        Assert.Equal("passed", proof!.Status);
        Assert.Equal("tests/RunServicesSmoke/Program.cs", proof.SourceFile);
        Assert.Equal(["build_explain_publish", "campaign_session_recover_recap"], proof.JourneysPassed);
    }

    [Fact]
    public void LoadProofIgnoresUnexpectedContract()
    {
        using var fixture = new CampaignOsLocalProofFixture();
        fixture.WriteProof("unexpected.contract");

        var proof = fixture.CreateService().LoadProof();

        Assert.Null(proof);
    }

    private sealed class CampaignOsLocalProofFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _canonRoot;

        public CampaignOsLocalProofFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "campaign-os-local-proof-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(_root, "repo");
            Directory.CreateDirectory(_canonRoot);
        }

        public CampaignOsLocalProofService CreateService()
        {
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot
                })
                .Build();

            return new CampaignOsLocalProofService(configuration);
        }

        public void WriteProof(string contractName)
        {
            var proofDir = Path.Combine(_canonRoot, ".codex-studio", "published");
            Directory.CreateDirectory(proofDir);
            File.WriteAllText(
                Path.Combine(proofDir, "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = contractName,
                    ["generated_at"] = "2026-03-28T19:55:48Z",
                    ["status"] = "passed",
                    ["proof_kind"] = "source_backed_local_smoke_contract",
                    ["source_file"] = "tests/RunServicesSmoke/Program.cs",
                    ["journeys_passed"] = new[] { "build_explain_publish", "campaign_session_recover_recap" }
                }));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
