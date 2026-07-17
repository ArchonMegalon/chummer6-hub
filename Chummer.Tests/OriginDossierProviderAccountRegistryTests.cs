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

    [Fact]
    public void ManuscriptAndAudioRegistriesResolveOnlyEnabledRoleMatchedAccounts()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "INKFLUENCE_MANUSCRIPT_01",
                      "provider": "Inkfluence",
                      "status": "available",
                      "roles": ["manuscript", "origin"]
                    },
                    {
                      "accountAlias": "UNMIXR_AUDIO_01",
                      "provider": "Unmixr AI",
                      "status": "available",
                      "roles": ["audio", "audiobook", "origin"]
                    },
                    {
                      "accountAlias": "UNMIXR_AUDIO_RETIRED",
                      "provider": "Unmixr AI",
                      "status": "retired",
                      "roles": ["audio", "audiobook", "origin"]
                    },
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

        IReadOnlyList<string> manuscriptAliases = OriginDossierProviderAccountRegistry.ResolveAliases(
            configuration,
            "CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES",
            "OriginDossier:ManuscriptAccountAliases",
            "manuscript");
        IReadOnlyList<string> audioAliases = OriginDossierProviderAccountRegistry.ResolveAliases(
            configuration,
            "CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES",
            "OriginDossier:AudioAccountAliases",
            "audio");

        Assert.Equal(["INKFLUENCE_MANUSCRIPT_01"], manuscriptAliases);
        Assert.Equal(["UNMIXR_AUDIO_01"], audioAliases);
        Assert.True(OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
            configuration,
            "CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES",
            "OriginDossier:ManuscriptAccountAliases",
            "manuscript"));
        Assert.True(OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
            configuration,
            "CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES",
            "OriginDossier:AudioAccountAliases",
            "audio"));
    }

    [Fact]
    public void AudiobookshelfRegistryNormalizesTrustedHostsFromProviderAccounts()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "ORIGIN_AUDIOBOOKSHELF_01",
                      "provider": "Audiobookshelf",
                      "status": "available",
                      "roles": ["audiobookshelf", "book_share"],
                      "trustedHosts": [
                        "https://audio.chummer.run/share/origin",
                        "origin-shelf.example.invalid."
                      ]
                    },
                    {
                      "accountAlias": "ORIGIN_AUDIOBOOKSHELF_RETIRED",
                      "provider": "Audiobookshelf",
                      "status": "disabled",
                      "roles": ["audiobookshelf", "book_share"],
                      "trustedHosts": ["retired.example.invalid"]
                    }
                  ]
                }
                """
            })
            .Build();

        IReadOnlyList<string> hosts = OriginDossierProviderAccountRegistry.ResolveHosts(
            configuration,
            "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS",
            "OriginDossier:AudiobookshelfTrustedHosts",
            "audiobookshelf");

        Assert.Equal(["audio.chummer.run", "origin-shelf.example.invalid"], hosts);
        Assert.True(OriginDossierProviderAccountRegistry.HasConfiguredHostSource(
            configuration,
            "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS",
            "OriginDossier:AudiobookshelfTrustedHosts",
            "audiobookshelf"));
    }
}
