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
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));

        Assert.Contains("label: Open Chummer", manifest, StringComparison.Ordinal);
        Assert.Contains("label: Claim your copy", manifest, StringComparison.Ordinal);
        Assert.Contains("Open Chummer with an account", trustContent, StringComparison.Ordinal);
        Assert.Contains("Claim your copy only when", trustContent, StringComparison.Ordinal);
        Assert.Contains(">Open Chummer</a>", nowView, StringComparison.Ordinal);
        Assert.Contains("\"Claim your copy\"", faqView, StringComparison.Ordinal);
        Assert.Contains("AccountSupportLabel: authenticated ? \"Open account support\" : \"Claim your copy\"", controller, StringComparison.Ordinal);

        Assert.DoesNotContain("label: Sign in", manifest, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Create account", manifest, StringComparison.Ordinal);
        Assert.DoesNotContain(">Sign in</a>", nowView, StringComparison.Ordinal);
        Assert.DoesNotContain("\"Create account\"", faqView, StringComparison.Ordinal);
        Assert.DoesNotContain("Create account for saved history", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Sign in when you want help history", trustContent, StringComparison.Ordinal);
    }
}
