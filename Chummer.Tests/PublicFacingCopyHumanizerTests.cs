using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicFacingCopyHumanizerTests
{
    [Theory]
    [InlineData("The proof trail is not copy a human would write.", "The details are not copy a human would write.")]
    [InlineData("An AI assistant generated a provider artifact receipt.", "Help prepared a service file record.")]
    [InlineData("Open the horizon-only proof page for validation checks.", "Open the private details for review.")]
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
    }
}
