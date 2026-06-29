using Xunit;

namespace Chummer.Tests;

public sealed class PublicAccountCopyTests
{
    [Fact]
    public void PublicGuestAccountCopyUsesClaimAndOpenLanguage()
    {
        string manifest = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_MANIFEST.yaml"));
        string trustContent = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_TRUST_CONTENT.yaml"));
        string nowView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml"));
        string faqView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml"));
        string trustPageView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml"));
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string accountsController = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs"));
        string accountHubView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Hub.cshtml"));
        string layoutView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
        string authEntryView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Auth", "Entry.cshtml"));

        Assert.Contains("label: Open Chummer", manifest, StringComparison.Ordinal);
        Assert.Contains("label: Claim your copy", manifest, StringComparison.Ordinal);
        Assert.Contains("title: Open Chummer", manifest, StringComparison.Ordinal);
        Assert.Contains("title: Claim your copy", manifest, StringComparison.Ordinal);
        Assert.Contains("Claim your copy only when you want recovery or linked installs.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Claiming your copy gives you a recovery path and linked installs when you want them.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Discord first. Private form if needed.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Use Discord for normal questions. Use Contact for private details.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Private help stays private", trustContent, StringComparison.Ordinal);
        Assert.Contains("No. You can get help without using Participate.", trustContent, StringComparison.Ordinal);
        Assert.Contains(">Open Chummer</a>", nowView, StringComparison.Ordinal);
        Assert.Contains("\"Claim your copy\"", faqView, StringComparison.Ordinal);
        Assert.Contains("authenticated ? \"Open account\" : \"Claim your copy\"", trustPageView, StringComparison.Ordinal);
        Assert.Contains("AccountSupportLabel: authenticated ? \"Open account support\" : \"Open private form\"", controller, StringComparison.Ordinal);
        Assert.Contains("action=\"/auth/email/start\"", authEntryView, StringComparison.Ordinal);
        Assert.Contains("<p class=\"auth-panel__eyebrow\">@Model.Eyebrow</p>", authEntryView, StringComparison.Ordinal);
        Assert.Contains(">Continue with email</button>", authEntryView, StringComparison.Ordinal);
        Assert.Contains("@if (Model.GoogleAvailable)", authEntryView, StringComparison.Ordinal);
        Assert.Contains("Continue with Google", authEntryView, StringComparison.Ordinal);
        Assert.Contains("Heading: \"Account\"", accountsController, StringComparison.Ordinal);
        Assert.Contains("Summary: \"Installs, runners, help, and membership live here.\"", accountsController, StringComparison.Ordinal);
        Assert.Contains("\"Roster\"", accountsController, StringComparison.Ordinal);
        Assert.Contains("\"Installs\"", accountsController, StringComparison.Ordinal);
        Assert.Contains("<li>@Model.User.DisplayName</li>", accountHubView, StringComparison.Ordinal);
        Assert.Contains("<li>@Model.MembershipLabel · @Model.MembershipSummary</li>", accountHubView, StringComparison.Ordinal);
        Assert.Contains("<li>@Model.BookQuotaSummary</li>", accountHubView, StringComparison.Ordinal);
        Assert.Contains("<summary class=\"site-account-menu__summary\">", layoutView, StringComparison.Ordinal);
        Assert.Contains("<span class=\"site-account-menu__label\">Account</span>", layoutView, StringComparison.Ordinal);
        Assert.Contains("<p class=\"site-account-menu__meta\">@chrome.SignedInLabel</p>", layoutView, StringComparison.Ordinal);

        Assert.DoesNotContain("label: Sign in", manifest, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Create account", manifest, StringComparison.Ordinal);
        Assert.DoesNotContain("title: Sign in", manifest, StringComparison.Ordinal);
        Assert.DoesNotContain("title: Create account", manifest, StringComparison.Ordinal);
        Assert.DoesNotContain(">Sign in</a>", nowView, StringComparison.Ordinal);
        Assert.DoesNotContain("\"Create account\"", faqView, StringComparison.Ordinal);
        Assert.DoesNotContain("authenticated ? \"Open account\" : \"Create account\"", trustPageView, StringComparison.Ordinal);
        Assert.DoesNotContain("Create account for saved history", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Save support history", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Sign in when you want help history", trustContent, StringComparison.Ordinal);
        Assert.DoesNotContain("saved help history", trustContent, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Pick the page that matches the problem.", trustContent, StringComparison.Ordinal);
        Assert.DoesNotContain("Support is separate from participation", trustContent, StringComparison.Ordinal);
        Assert.DoesNotContain("Public boards are optional.", trustContent, StringComparison.Ordinal);
        Assert.DoesNotContain("Joining public boards is optional.", trustContent, StringComparison.Ordinal);
        Assert.DoesNotContain("Public requests belong on Participate.", trustContent, StringComparison.Ordinal);
        Assert.DoesNotContain("Use this page for installs, membership, and support.", accountsController, StringComparison.Ordinal);
        Assert.DoesNotContain("Open Chummer for actual character work. Stay here for recovery, billing, and help.", accountsController, StringComparison.Ordinal);
        Assert.DoesNotContain("Heading: \"Installs, billing, and help.\"", accountsController, StringComparison.Ordinal);
        Assert.DoesNotContain("Summary: \"Character work happens in Chummer. Use this page for recovery, billing, and support.\"", accountsController, StringComparison.Ordinal);
        Assert.DoesNotContain("Signed in as @Model.User.DisplayName", accountHubView, StringComparison.Ordinal);
        Assert.DoesNotContain("Plan: @Model.MembershipLabel", accountHubView, StringComparison.Ordinal);
        Assert.DoesNotContain("Signed in as @chrome.SignedInLabel", layoutView, StringComparison.Ordinal);
        Assert.DoesNotContain("<p>@chrome.SignedInLabel</p>", layoutView, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactPageStaysDiscordFirstWithoutParticipateDetour()
    {
        string trustPageView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml"));

        Assert.Contains("Title: \"Discord\"", trustPageView, StringComparison.Ordinal);
        Assert.Contains("Label: \"Open Discord\"", trustPageView, StringComparison.Ordinal);
        Assert.Contains("Title: \"Private message\"", trustPageView, StringComparison.Ordinal);
        Assert.Contains("Label: \"Open private form\"", trustPageView, StringComparison.Ordinal);

        Assert.DoesNotContain("Id: \"public-feedback\"", trustPageView, StringComparison.Ordinal);
        Assert.DoesNotContain("Title: \"Public bugs and requests\"", trustPageView, StringComparison.Ordinal);
        Assert.DoesNotContain("Label: \"Open Participate\"", trustPageView, StringComparison.Ordinal);
        Assert.DoesNotContain("Public ideas belong on <a class=\"inline-link\" href=\"/participate\">Participate</a>.", trustPageView, StringComparison.Ordinal);
    }
}
