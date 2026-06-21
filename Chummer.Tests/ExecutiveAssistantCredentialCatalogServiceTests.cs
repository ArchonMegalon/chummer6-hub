using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using System.Text.RegularExpressions;
using Xunit;

namespace Chummer.Tests;

public sealed class ExecutiveAssistantCredentialCatalogServiceTests
{
    [Fact]
    public void GetCatalog_surfaces_new_ltd_rows_and_masks_email_without_leaking_passwords()
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
                ["CHUMMER_EA_MAGICFIT_PASSWORD"] = "rangersofB5",
                ["CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL"] = "session-account@example.invalid",
                ["CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD"] = "session-rangersofB5",
                ["PROMPTING_SYSTEMS_API_KEY"] = "pa-secret",
                ["PROMPT_ARCHITECTS_TIER4_VERIFIED"] = "true",
                ["PROMPT_ARCHITECTS_API_AVAILABLE"] = "true",
                ["PROMPT_ARCHITECTS_MCP_VERIFIED"] = "true",
                ["PROMPT_ARCHITECTS_EXPORT_AVAILABLE"] = "true",
                ["PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED"] = "true",
                ["PROMPT_ARCHITECTS_TEAM_PERMISSIONS_REVIEWED"] = "true",
                ["PAYFUNNELS_WEBHOOK_SECRET"] = "pf-webhook-secret",
                ["SUBSCRIBR_API_TOKEN"] = "subscribr-api-secret",
                ["SUBSCRIBR_WEBHOOK_SECRET"] = "subscribr-webhook-secret",
                ["SUBSCRIBR_TEAM_ID"] = "team-7",
                ["SUBSCRIBR_INTEGRATION_CHANNEL_ID"] = "channel-integration",
                ["CHUMMER_EA_UNMIXR_TIER"] = "4",
                ["CHUMMER_EA_UNMIXR_EMAIL"] = "voice@example.com",
                ["CHUMMER_EA_UNMIXR_PASSWORD"] = "unmixr-login-secret",
                ["UNMIXR_API_KEY"] = "unmixr-api-secret",
                ["UNMIXR_VOICE_ID"] = "voice-123"
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

        ExecutiveAssistantCredentialEntry promptArchitects = Assert.Single(result.Entries, static entry => entry.ToolId == "prompt_architects");
        Assert.Equal("4", promptArchitects.Tier);
        Assert.True(promptArchitects.EmailConfigured);
        Assert.Equal("configured", promptArchitects.Status);

        ExecutiveAssistantCredentialEntry payFunnels = Assert.Single(result.Entries, static entry => entry.ToolId == "payfunnels");
        Assert.Equal("3", payFunnels.Tier);
        Assert.True(payFunnels.EmailConfigured);
        Assert.Equal("configured", payFunnels.Status);

        ExecutiveAssistantCredentialEntry subscribr = Assert.Single(result.Entries, static entry => entry.ToolId == "subscribr");
        Assert.Equal("7", subscribr.Tier);
        Assert.True(subscribr.EmailConfigured);
        Assert.True(subscribr.PasswordConfigured);
        Assert.True(subscribr.PasswordAltConfigured);
        Assert.Equal("tracked_video_script_preproduction_lane", subscribr.Status);

        ExecutiveAssistantCredentialEntry magicfitSession = Assert.Single(result.Entries, static entry => entry.ToolId == "magicfit_session");
        Assert.Equal("5", magicfitSession.Tier);
        Assert.Equal("s***@e***", magicfitSession.EmailMasked);
        Assert.True(magicfitSession.EmailConfigured);
        Assert.True(magicfitSession.PasswordConfigured);
        Assert.Equal("configured", magicfitSession.Status);

        ExecutiveAssistantCredentialEntry unmixr = Assert.Single(result.Entries, static entry => entry.ToolId == "unmixr");
        Assert.Equal("4", unmixr.Tier);
        Assert.Equal("v***@e***", unmixr.EmailMasked);
        Assert.True(unmixr.EmailConfigured);
        Assert.True(unmixr.PasswordConfigured);
        Assert.True(unmixr.PasswordAltConfigured);
        Assert.Equal("configured", unmixr.Status);

        string serialized = System.Text.Json.JsonSerializer.Serialize(result);
        Assert.DoesNotContain("rangersofB5", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("session-rangersofB5", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("pa-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("pf-webhook-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("subscribr-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("subscribr-webhook-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("team-7", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("channel-integration", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("unmixr-login-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("unmixr-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("voice-123", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("tibor.girschele@gmail.com", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("session-account@example.invalid", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("voice@example.com", serialized, StringComparison.Ordinal);
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

        ExecutiveAssistantCredentialEntry promptArchitects = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "prompt_architects");
        Assert.Equal("missing", promptArchitects.Status);

        ExecutiveAssistantCredentialEntry payfunnels = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "payfunnels");
        Assert.Equal("missing", payfunnels.Status);

        ExecutiveAssistantCredentialEntry subscribr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "subscribr");
        Assert.Equal("missing", subscribr.Status);

        ExecutiveAssistantCredentialEntry magicfitSession = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "magicfit_session");
        Assert.Equal("missing", magicfitSession.Status);
        Assert.False(magicfitSession.EmailConfigured);

        ExecutiveAssistantCredentialEntry unmixr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "unmixr");
        Assert.Equal("missing", unmixr.Status);
        Assert.False(unmixr.PasswordAltConfigured);
    }

    [Fact]
    public void GetCatalog_marks_magicfit_session_status_ready_but_not_isolated_when_email_matches_official_product_account()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_MAGICFIT_EMAIL"] = "official@example.invalid",
                ["CHUMMER_EA_MAGICFIT_PASSWORD"] = "prod-password",
                ["CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL"] = "official@example.invalid",
                ["CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD"] = "session-password"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry magicfitSession = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "magicfit_session");
        Assert.Equal("ready_but_not_isolated", magicfitSession.Status);
    }

    [Fact]
    public void GetCatalog_marks_unmixr_login_only_until_runtime_voice_is_configured()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_UNMIXR_EMAIL"] = "voice@example.invalid",
                ["CHUMMER_EA_UNMIXR_PASSWORD"] = "login-password"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry unmixr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "unmixr");
        Assert.Equal("login_only", unmixr.Status);
        Assert.True(unmixr.EmailConfigured);
        Assert.True(unmixr.PasswordConfigured);
        Assert.False(unmixr.PasswordAltConfigured);
    }

    [Fact]
    public void GetCatalog_tracks_icanpreneur_as_bounded_discovery_lane()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_DEFAULT_EMAIL"] = "operator@example.invalid",
                ["CHUMMER_EA_DEFAULT_PASSWORD"] = "shared-password",
                ["CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL"] = "https://discover.example.invalid/icanpreneur"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry icanpreneur = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "icanpreneur");
        Assert.Equal("3", icanpreneur.Tier);
        Assert.Equal("bounded_discovery_interview_lane", icanpreneur.Status);
        Assert.True(icanpreneur.MirrorsDefault);
        Assert.True(icanpreneur.EmailConfigured);
        Assert.True(icanpreneur.PasswordConfigured);
        Assert.True(icanpreneur.PasswordAltConfigured);
    }

    [Fact]
    public void GetCatalog_surfaces_every_explicit_ltd_inventory_credential_row()
    {
        IConfiguration configuration = new ConfigurationBuilder().Build();
        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        string[] explicitInventoryRows = Regex.Matches(
                File.ReadAllText(RepoPaths.FromRoot("ltds.md")),
                @"^###\s+(?<toolId>.+?)\s*$",
                RegexOptions.CultureInvariant | RegexOptions.Multiline)
            .Select(static match => match.Groups["toolId"].Value.Trim())
            .Where(static toolId => !string.Equals(toolId, "default", StringComparison.Ordinal))
            .OrderBy(static toolId => toolId, StringComparer.Ordinal)
            .ToArray();

        string[] catalogRows = service.GetCatalog()
            .Entries
            .Select(static entry => entry.ToolId)
            .OrderBy(static toolId => toolId, StringComparer.Ordinal)
            .ToArray();

        Assert.Contains("default", catalogRows);
        foreach (string toolId in explicitInventoryRows)
        {
            Assert.Contains(toolId, catalogRows);
        }
    }
}
