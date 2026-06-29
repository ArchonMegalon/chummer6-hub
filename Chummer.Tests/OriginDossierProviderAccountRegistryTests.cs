using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginDossierProviderAccountRegistryTests
{
    [Fact]
    public void VisualRegistryDoesNotTreatRunsiteMagicAiSceneAccountsAsOriginVisualAccounts()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "MAGICAI_RUNSITE_SCENE_01",
                      "provider": "MagicAI Runsite Scene Render",
                      "status": "available",
                      "roles": ["runsite"]
                    }
                  ]
                }
                """
            })
            .Build();

        IReadOnlyList<string> visualAliases = OriginDossierProviderAccountRegistry.ResolveAliases(
            configuration,
            "CHUMMER_ORIGIN_VISUAL_ACCOUNT_ALIASES",
            "OriginDossier:VisualAccountAliases",
            "visual");

        Assert.Empty(visualAliases);
        Assert.False(OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
            configuration,
            "CHUMMER_ORIGIN_VISUAL_ACCOUNT_ALIASES",
            "OriginDossier:VisualAccountAliases",
            "visual"));
    }

    [Fact]
    public void VisualRegistryStillAcceptsExplicitMagicfitOriginVisualAccounts()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "MAGICFIT_ORIGIN_VISUAL_01",
                      "provider": "Magicfit",
                      "status": "available",
                      "roles": ["visual", "origin_visual"]
                    }
                  ]
                }
                """
            })
            .Build();

        IReadOnlyList<string> visualAliases = OriginDossierProviderAccountRegistry.ResolveAliases(
            configuration,
            "CHUMMER_ORIGIN_VISUAL_ACCOUNT_ALIASES",
            "OriginDossier:VisualAccountAliases",
            "visual");

        Assert.Equal(["MAGICFIT_ORIGIN_VISUAL_01"], visualAliases);
        Assert.True(OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
            configuration,
            "CHUMMER_ORIGIN_VISUAL_ACCOUNT_ALIASES",
            "OriginDossier:VisualAccountAliases",
            "visual"));
    }

    [Fact]
    public void PackagingRegistryAcceptsExplicitBookArtifactAccounts()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "FLIPLINK_ORIGIN_PACKAGE_01",
                      "provider": "FlipLink",
                      "status": "available",
                      "roles": ["packaging", "book_artifact", "origin_packaging"]
                    }
                  ]
                }
                """
            })
            .Build();

        IReadOnlyList<string> packagingAliases = OriginDossierProviderAccountRegistry.ResolveAliases(
            configuration,
            "CHUMMER_ORIGIN_PACKAGING_ACCOUNT_ALIASES",
            "OriginDossier:PackagingAccountAliases",
            "packaging");

        Assert.Equal(["FLIPLINK_ORIGIN_PACKAGE_01"], packagingAliases);
        Assert.True(OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
            configuration,
            "CHUMMER_ORIGIN_PACKAGING_ACCOUNT_ALIASES",
            "OriginDossier:PackagingAccountAliases",
            "packaging"));
    }

    [Fact]
    public void PackagingRegistryDoesNotTreatFirstBookAuthoringAccountsAsPackaging()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "FIRSTBOOK_PREMIUM",
                      "provider": "First Book AI",
                      "status": "available",
                      "roles": ["premium_guided_authoring", "runner_memoir", "origin"]
                    }
                  ]
                }
                """
            })
            .Build();

        IReadOnlyList<string> packagingAliases = OriginDossierProviderAccountRegistry.ResolveAliases(
            configuration,
            "CHUMMER_ORIGIN_PACKAGING_ACCOUNT_ALIASES",
            "OriginDossier:PackagingAccountAliases",
            "packaging");

        Assert.Empty(packagingAliases);
        Assert.False(OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
            configuration,
            "CHUMMER_ORIGIN_PACKAGING_ACCOUNT_ALIASES",
            "OriginDossier:PackagingAccountAliases",
            "packaging"));
    }
}
