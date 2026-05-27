using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ExecutiveAssistantCredentialCatalogServiceTests
{
    [Fact]
    public void GetCatalog_surfaces_magicfit_and_masks_email_without_leaking_passwords()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_DEFAULT_EMAIL"] = "default@example.com",
                ["CHUMMER_EA_DEFAULT_PASSWORD"] = "default-secret",
                ["CHUMMER_EA_DEFAULT_PASSWORD_ALT"] = "default-alt-secret",
                ["CHUMMER_EA_BLIPAI_APP_TIER"] = "4",
                ["CHUMMER_EA_BLIPAI_APP_EMAIL"] = "blip@example.com",
                ["CHUMMER_EA_BLIPAI_APP_PASSWORD"] = "blip-secret",
                ["CHUMMER_EA_MAGICFIT_TIER"] = "5",
                ["CHUMMER_EA_MAGICFIT_EMAIL"] = "tibor.girschele@gmail.com",
                ["CHUMMER_EA_MAGICFIT_PASSWORD"] = "rangersofB5"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialCatalogResult result = service.GetCatalog();

        ExecutiveAssistantCredentialEntry magicfit = Assert.Single(result.Entries, static entry => entry.ToolId == "magicfit");
        Assert.Equal("5", magicfit.Tier);
        Assert.Equal("t***@g***", magicfit.EmailMasked);
        Assert.True(magicfit.EmailConfigured);
        Assert.True(magicfit.PasswordConfigured);
        Assert.Equal("configured", magicfit.Status);

        string serialized = System.Text.Json.JsonSerializer.Serialize(result);
        Assert.DoesNotContain("rangersofB5", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("tibor.girschele@gmail.com", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public void GetCatalog_marks_partial_rows_missing()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_MAGICFIT_TIER"] = "5",
                ["CHUMMER_EA_MAGICFIT_EMAIL"] = "tibor.girschele@gmail.com"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry magicfit = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "magicfit");
        Assert.Equal("missing", magicfit.Status);
        Assert.False(magicfit.PasswordConfigured);
    }
}
