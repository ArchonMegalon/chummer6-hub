using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class InternalExecutiveAssistantCredentialsControllerTests
{
    [Fact]
    public void GetCatalog_returns_service_unavailable_when_internal_token_is_not_configured()
    {
        InternalExecutiveAssistantCredentialsController controller = BuildController(new Dictionary<string, string?>());

        ActionResult<ExecutiveAssistantCredentialCatalogResult> result = controller.GetCatalog();

        var objectResult = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, objectResult.StatusCode);
    }

    [Fact]
    public void GetCatalog_rejects_missing_or_invalid_bearer_token()
    {
        InternalExecutiveAssistantCredentialsController controller = BuildController(new Dictionary<string, string?>
        {
            ["FLEET_INTERNAL_API_TOKEN"] = "internal-token"
        });

        ActionResult<ExecutiveAssistantCredentialCatalogResult> missingHeader = controller.GetCatalog();
        var missingHeaderResult = Assert.IsType<ObjectResult>(missingHeader.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, missingHeaderResult.StatusCode);

        controller = BuildController(new Dictionary<string, string?>
        {
            ["FLEET_INTERNAL_API_TOKEN"] = "internal-token"
        });
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer wrong-token";

        ActionResult<ExecutiveAssistantCredentialCatalogResult> wrongToken = controller.GetCatalog();
        var wrongTokenResult = Assert.IsType<ObjectResult>(wrongToken.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, wrongTokenResult.StatusCode);
    }

    [Fact]
    public void GetCatalog_returns_masked_catalog_for_authorized_internal_caller()
    {
        InternalExecutiveAssistantCredentialsController controller = BuildController(new Dictionary<string, string?>
        {
            ["FLEET_INTERNAL_API_TOKEN"] = "internal-token",
            ["CHUMMER_EA_MAGICFIT_EMAIL"] = "media@example.invalid",
            ["CHUMMER_EA_MAGICFIT_PASSWORD"] = "media-secret",
            ["MAGICAI_ACCOUNT_01_EMAIL"] = "magicai-1@example.invalid",
            ["MAGICAI_ACCOUNT_01_PASSWORD"] = "magicai-password"
        });
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-token";

        ActionResult<ExecutiveAssistantCredentialCatalogResult> result = controller.GetCatalog();

        var ok = Assert.IsType<OkObjectResult>(result.Result);
        var catalog = Assert.IsType<ExecutiveAssistantCredentialCatalogResult>(ok.Value);
        ExecutiveAssistantCredentialEntry magicfit = Assert.Single(catalog.Entries, static entry => entry.ToolId == "magicfit");
        ExecutiveAssistantCredentialEntry magicai = Assert.Single(catalog.Entries, static entry => entry.ToolId == "magicai");
        Assert.Equal("m***@e***", magicfit.EmailMasked);
        Assert.Equal("login_only", magicai.Status);
        Assert.Equal(1, magicai.DeclaredAccountCount);
        Assert.Equal(1, magicai.PendingApiKeyAccountCount);
        Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<ExecutiveAssistantCredentialSlotEntry>>(magicai.CredentialSlots));

        string serialized = System.Text.Json.JsonSerializer.Serialize(catalog);
        Assert.DoesNotContain("media@example.invalid", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("media-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("magicai-1@example.invalid", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("magicai-password", serialized, StringComparison.Ordinal);
    }

    private static InternalExecutiveAssistantCredentialsController BuildController(Dictionary<string, string?> values)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();

        var controller = new InternalExecutiveAssistantCredentialsController(
            new ExecutiveAssistantCredentialCatalogService(configuration),
            configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        controller.ControllerContext.HttpContext.Request.Path = "/api/internal/executive-assistant/credentials";
        return controller;
    }
}
