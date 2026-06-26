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
        string authEntryView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Auth", "Entry.cshtml"));

        Assert.Contains("label: Open Chummer", manifest, StringComparison.Ordinal);
        Assert.Contains("label: Claim your copy", manifest, StringComparison.Ordinal);
        Assert.Contains("title: Open Chummer", manifest, StringComparison.Ordinal);
        Assert.Contains("title: Claim your copy", manifest, StringComparison.Ordinal);
        Assert.Contains("Claim your copy only if you want recovery or linked installs.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Claiming your copy gives you a recovery path and linked installs when you want them.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Use Discord for normal questions and Contact for private details.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Discord for normal questions. Use the form only for private install trouble, crashes, logs, or account detail.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Use Discord for normal questions. Use the form for private details.", trustContent, StringComparison.Ordinal);
        Assert.Contains("Public boards are optional.", trustContent, StringComparison.Ordinal);
        Assert.Contains(">Open Chummer</a>", nowView, StringComparison.Ordinal);
        Assert.Contains("\"Claim your copy\"", faqView, StringComparison.Ordinal);
        Assert.Contains("authenticated ? \"Open account\" : \"Claim your copy\"", trustPageView, StringComparison.Ordinal);
        Assert.Contains("AccountSupportLabel: authenticated ? \"Open account support\" : \"Open private form\"", controller, StringComparison.Ordinal);
        Assert.Contains("action=\"/auth/email/start\"", authEntryView, StringComparison.Ordinal);
        Assert.Contains(">Continue with email</button>", authEntryView, StringComparison.Ordinal);
        Assert.Contains("@if (Model.GoogleAvailable)", authEntryView, StringComparison.Ordinal);
        Assert.Contains("Continue with Google", authEntryView, StringComparison.Ordinal);

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
        Assert.DoesNotContain("Public issue threads are optional and not the default help door.", trustContent, StringComparison.Ordinal);
        Assert.DoesNotContain("Participation is optional and separate from the normal customer help path.", trustContent, StringComparison.Ordinal);
    }
}
