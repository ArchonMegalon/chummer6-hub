using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class IdentityLinkServiceTests
{
    [Fact]
    public void LinkChannelAcceptsWhatsappOfficialBusiness()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.whatsapp.runner", "Runner Prime", "runner@example.com");

            ChannelLinkDto link = links.LinkChannel(new LinkChannelRequest("subject.whatsapp.runner", "whatsapp_official_business", "+436647916419", true));

            Assert.Equal("whatsapp_official_business", link.ChannelKind);
            Assert.True(link.OfficialChannel);
            Assert.Equal("linked", link.Status);
            Assert.Equal("436647916419", link.DisplayLabel);
            Assert.Contains("WhatsApp", link.Note ?? string.Empty);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void LinkChannelToExecutiveAssistantUpdatesExistingChannelToEaLinked()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.ea.runner", "Runner Prime", "runner@example.com");

            links.LinkChannel(new LinkChannelRequest("subject.ea.runner", "telegram_official_bot", "hubbrain", true));
            ChannelLinkDto updated = links.LinkChannelToExecutiveAssistant(
                "telegram_official_bot",
                new LinkChannelToExecutiveAssistantRequest("subject.ea.runner", null));

            Assert.Equal("ea_linked", updated.Status);
            Assert.Equal("hubbrain", updated.DisplayLabel);
            Assert.True(updated.OfficialChannel);
            Assert.Equal("hubbrain", store.ChannelLinks[0].DisplayLabel);
            Assert.Equal("ea_linked", store.ChannelLinks[0].Status);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void LinkChannelToExecutiveAssistantCreatesNewChannelWhenHandleProvided()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.ea.runner", "Runner Prime", "runner@example.com");

            ChannelLinkDto updated = links.LinkChannelToExecutiveAssistant(
                "whatsapp_official_business",
                new LinkChannelToExecutiveAssistantRequest("subject.ea.runner", "+43 664 791 6419"));

            Assert.Equal("whatsapp_official_business", updated.ChannelKind);
            Assert.Equal("ea_linked", updated.Status);
            Assert.Equal("436647916419", updated.DisplayLabel);
            Assert.Single(store.ChannelLinks);
            Assert.Equal(updated.ChannelLinkId, store.ChannelLinks[0].ChannelLinkId);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void LinkChannelToExecutiveAssistantNormalizesWhatsappHandle()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.ea.runner", "Runner Prime", "runner@example.com");

            links.LinkChannel(new LinkChannelRequest("subject.ea.runner", "whatsapp_official_business", "(+43) 664 791 6419", true));
            ChannelLinkDto updated = links.LinkChannelToExecutiveAssistant(
                "whatsapp_official_business",
                new LinkChannelToExecutiveAssistantRequest("subject.ea.runner", "(+43) 664 123 4455"));

            Assert.Equal("ea_linked", updated.Status);
            Assert.Equal("436641234455", updated.DisplayLabel);
            Assert.Equal("whatsapp_official_business", updated.ChannelKind);
            Assert.True(updated.OfficialChannel);
            Assert.Single(store.ChannelLinks);
            Assert.Equal("436641234455", store.ChannelLinks[0].DisplayLabel);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void LinkChannelToExecutiveAssistantRequiresChannelHandleOrExistingChannel()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.ea.runner", "Runner Prime", "runner@example.com");

            Assert.Throws<InvalidOperationException>(() => links.LinkChannelToExecutiveAssistant(
                "telegram_official_bot",
                new LinkChannelToExecutiveAssistantRequest("subject.ea.runner", null)));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void LinkChannelRejectsUnsupportedKind()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.whatsapp.runner", "Runner Prime", "runner@example.com");

            Assert.Throws<ArgumentException>(() => links.LinkChannel(new LinkChannelRequest("subject.whatsapp.runner", "signal")));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void GetSummaryIncludesWhatsappAsSupportedChannel()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.whatsapp.runner", "Runner Prime", "runner@example.com");

            AccountLinkSummaryDto summary = links.GetSummary("subject.whatsapp.runner");

            Assert.Contains("telegram_official_bot", summary.SupportedChannels);
            Assert.Contains("whatsapp_official_business", summary.SupportedChannels);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void GetChannelDeeplinkBuildsWhatsappWaMeUrlFromSavedOrOverriddenHandle()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.whatsapp.runner", "Runner Prime", "runner@example.com");

            links.LinkChannel(new LinkChannelRequest("subject.whatsapp.runner", "whatsapp_official_business", "+43 664 7916419", true));

            ChannelDeepLinkResponse first = links.GetChannelDeepLink("subject.whatsapp.runner", "whatsapp_official_business", null);
            Assert.Equal("whatsapp_official_business", first.ChannelKind);
            Assert.Equal("436647916419", first.ChannelHandle);
            Assert.Equal("https://wa.me/436647916419", first.DeepLink);
            Assert.Equal("whatsapp://send?phone=436647916419", first.AlternateDeepLink);
            Assert.Contains("api.qrserver.com", first.QrImageUrl);

            ChannelDeepLinkResponse overrideResult = links.GetChannelDeepLink("subject.whatsapp.runner", "whatsapp_official_business", "+1 206 111 3344");
            Assert.Equal("12061113344", overrideResult.ChannelHandle);
            Assert.Equal("https://wa.me/12061113344", overrideResult.DeepLink);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void GetChannelDeeplinkNormalizesTelegramHandle()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.telegram.runner", "Runner Prime", "runner@example.com");

            links.LinkChannel(new LinkChannelRequest("subject.telegram.runner", "telegram_official_bot", "@hubbrain", true));

            ChannelDeepLinkResponse response = links.GetChannelDeepLink("subject.telegram.runner", "telegram_official_bot", null);
            Assert.Equal("hubbrain", response.ChannelHandle);
            Assert.Equal("https://t.me/hubbrain", response.DeepLink);
            Assert.Equal("https://telegram.me/hubbrain", response.AlternateDeepLink);
            Assert.Contains("hubbrain", response.QrImageUrl);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void GetChannelDeeplinkRequiresHandleOrSavedChannel()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            CommunityStore store = new(BuildConfiguration(tempRoot), NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            IdentityLinkService links = new(store, accounts);
            accounts.EnsureUserWithStatus("subject.empty.runner", "Runner Prime", "runner@example.com");

            Assert.Throws<ArgumentException>(() => links.GetChannelDeepLink("subject.empty.runner", "whatsapp_official_business", null));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    private static IConfiguration BuildConfiguration(string tempRoot)
    {
        return new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json")
            })
            .Build();
    }

    private static string CreateTempRoot()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "identity-link-service-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        return tempRoot;
    }

    private static void DeleteTempRoot(string tempRoot)
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }
}
