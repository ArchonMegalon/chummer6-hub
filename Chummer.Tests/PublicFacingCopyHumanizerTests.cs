using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicFacingCopyHumanizerTests
{
    [Theory]
    [InlineData("The proof trail is not copy a human would write.", "The details are not copy a human would write.")]
    [InlineData("An AI assistant generated a provider artifact receipt.", "Help prepared a service file record.")]
    [InlineData("Open the horizon-only proof page for validation checks.", "Open the private details for review.")]
    [InlineData("The micro-proof exposes provenance, audit summary, and deterministic runtime state.", "The status note exposes source, review, and consistent app state.")]
    [InlineData("A bounded-failure artifact factory result remains in the publication lane.", "A not ready file builder result remains in the publishing path.")]
    public void Clean_RemovesInternalAndAiFlavoredPublicCopy(string source, string expected)
    {
        string cleaned = PublicFacingCopyHumanizer.Clean(source);

        Assert.Equal(expected, cleaned);
        Assert.DoesNotContain("proof", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("receipt", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("artifact", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("generated", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("AI", cleaned, StringComparison.Ordinal);
        Assert.DoesNotContain("assistant", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("provider", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("horizon", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("validation", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("checks", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("micro-proof", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("provenance", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("audit summary", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("deterministic", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("runtime", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("bounded-failure", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("artifact factory", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("publication lane", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("provider proof ready", "service status ready")]
    [InlineData("artifact receipt attached", "file record attached")]
    public void UndetectableHumanizerCopyAdapter_HumanizeHome_AppliesHomePreset(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizeHome(source);

        Assert.Equal(expected, cleaned);
    }

    [Theory]
    [InlineData("Product Governor review", "product decision review")]
    [InlineData("Icanpreneur through Teable", "guided request path through shared board")]
    public void UndetectableHumanizerCopyAdapter_HumanizeKarmaForgeIntake_AppliesPreset(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizeKarmaForgeIntake(source);

        Assert.Equal(expected, cleaned);
    }

    [Theory]
    [InlineData("Product Governor packet receipt", "product decision request note")]
    [InlineData("governed KarmaForgeCandidate", "guided saved request")]
    public void UndetectableHumanizerCopyAdapter_HumanizeKarmaForgeSubmitted_AppliesPreset(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizeKarmaForgeSubmitted(source);

        Assert.Equal(expected, cleaned);
    }

    [Theory]
    [InlineData("source item record", "original item update")]
    [InlineData("source details and records", "related details and updates")]
    public void UndetectableHumanizerCopyAdapter_HumanizeFeedbackOperations_AppliesPreset(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizeFeedbackOperations(source);

        Assert.Equal(expected, cleaned);
    }

    [Theory]
    [InlineData("planned work", "future work")]
    [InlineData("implementation tranche", "work item")]
    public void UndetectableHumanizerCopyAdapter_HumanizeRoadmap_AppliesPreset(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizeRoadmap(source);

        Assert.Equal(expected, cleaned);
    }

    [Theory]
    [InlineData("publication packet route", "publication page")]
    [InlineData("creator concierge provenance", "creator help origin")]
    public void UndetectableHumanizerCopyAdapter_HumanizePublication_AppliesPreset(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizePublication(source);

        Assert.Equal(expected, cleaned);
    }

    [Theory]
    [InlineData("provenance records", "history updates")]
    public void UndetectableHumanizerCopyAdapter_HumanizePackage_AppliesPreset(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizePackage(source);

        Assert.Equal(expected, cleaned);
    }

    [Theory]
    [InlineData("pending_verification", "Confirmation sent")]
    [InlineData("campaign_approved", "Campaign-approved")]
    [InlineData("review", "Needs attention")]
    [InlineData("sandbox", "Sandbox")]
    [InlineData("custom_state", "Custom State")]
    public void UndetectableHumanizerCopyAdapter_HumanizeStatusLabel_NormalizesSharedStatuses(string source, string expected)
    {
        string cleaned = UndetectableHumanizerCopyAdapter.HumanizeStatusLabel(source);

        Assert.Equal(expected, cleaned);
    }
}
