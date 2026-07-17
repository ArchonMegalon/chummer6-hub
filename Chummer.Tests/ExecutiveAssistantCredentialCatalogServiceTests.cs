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
                ["CHUMMER_EA_MAGICFIT_PASSWORD"] = "magicfit-login-secret",
                ["CHUMMER_EA_MAGICAI_TIER"] = "4",
                ["MAGICAI_ACCOUNT_PRIMARY_EMAIL"] = "api.one@example.invalid",
                ["MAGICAI_ACCOUNT_PRIMARY_PASSWORD"] = "magicai-login-secret",
                ["MAGICAI_ACCOUNT_PRIMARY_API_KEY"] = "magicai-api-secret",
                ["CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL"] = "session-account@example.invalid",
                ["CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD"] = "session-login-secret",
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
                ["CHUMMER_EA_SENDR_TIER"] = "4",
                ["CHUMMER_EA_SENDR_EMAIL"] = "sendr@example.com",
                ["CHUMMER_EA_SENDR_PASSWORD"] = "sendr-login-secret",
                ["CHUMMER_EA_SENDR_API_KEY"] = "sendr-api-secret",
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

        ExecutiveAssistantCredentialEntry magicai = Assert.Single(result.Entries, static entry => entry.ToolId == "magicai");
        Assert.Equal("4", magicai.Tier);
        Assert.Equal("a***@e***", magicai.EmailMasked);
        Assert.True(magicai.EmailConfigured);
        Assert.True(magicai.PasswordConfigured);
        Assert.True(magicai.PasswordAltConfigured);
        Assert.Equal("multi_account_pool_configured", magicai.Status);
        Assert.Equal(1, magicai.DeclaredAccountCount);
        Assert.Equal(1, magicai.LoginReadyAccountCount);
        Assert.Equal(1, magicai.ApiKeyReadyAccountCount);
        Assert.Equal(0, magicai.PendingApiKeyAccountCount);
        ExecutiveAssistantCredentialSlotEntry magicaiPrimary = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<ExecutiveAssistantCredentialSlotEntry>>(magicai.CredentialSlots));
        Assert.Equal("PRIMARY", magicaiPrimary.Alias, StringComparer.OrdinalIgnoreCase);
        Assert.Equal("configured", magicaiPrimary.Status);

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

        ExecutiveAssistantCredentialEntry sendr = Assert.Single(result.Entries, static entry => entry.ToolId == "sendr");
        Assert.Equal("4", sendr.Tier);
        Assert.Equal("s***@e***", sendr.EmailMasked);
        Assert.True(sendr.EmailConfigured);
        Assert.True(sendr.PasswordConfigured);
        Assert.True(sendr.PasswordAltConfigured);
        Assert.Equal("api_configured_login_available", sendr.Status);

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
        Assert.DoesNotContain("magicfit-login-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("session-login-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("magicai-login-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("magicai-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("pa-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("pf-webhook-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("subscribr-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("subscribr-webhook-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("team-7", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("channel-integration", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("sendr-login-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("sendr-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("unmixr-login-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("unmixr-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("voice-123", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("tibor.girschele@gmail.com", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("api.one@example.invalid", serialized, StringComparison.Ordinal);
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

        ExecutiveAssistantCredentialEntry magicai = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "magicai");
        Assert.Equal("missing", magicai.Status);
        Assert.False(magicai.PasswordConfigured);
        Assert.False(magicai.PasswordAltConfigured);
        Assert.Equal(0, magicai.DeclaredAccountCount);
        Assert.Equal(0, magicai.LoginReadyAccountCount);
        Assert.Equal(0, magicai.ApiKeyReadyAccountCount);
        Assert.Equal(0, magicai.PendingApiKeyAccountCount);

        ExecutiveAssistantCredentialEntry promptArchitects = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "prompt_architects");
        Assert.Equal("missing", promptArchitects.Status);

        ExecutiveAssistantCredentialEntry payfunnels = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "payfunnels");
        Assert.Equal("missing", payfunnels.Status);

        ExecutiveAssistantCredentialEntry subscribr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "subscribr");
        Assert.Equal("missing", subscribr.Status);

        ExecutiveAssistantCredentialEntry sendr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "sendr");
        Assert.Equal("missing", sendr.Status);
        Assert.False(sendr.PasswordAltConfigured);

        ExecutiveAssistantCredentialEntry magicfitSession = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "magicfit_session");
        Assert.Equal("missing", magicfitSession.Status);
        Assert.False(magicfitSession.EmailConfigured);

        ExecutiveAssistantCredentialEntry unmixr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "unmixr");
        Assert.Equal("missing", unmixr.Status);
        Assert.False(unmixr.PasswordAltConfigured);
    }

    [Fact]
    public void GetCatalog_marks_magicai_pool_login_only_until_api_key_exists()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_MAGICAI_TIER"] = "4",
                ["MAGICAI_ACCOUNT_RUNSITE_01_EMAIL"] = "runsite@example.invalid",
                ["MAGICAI_ACCOUNT_RUNSITE_01_PASSWORD"] = "shared-password"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry magicai = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "magicai");
        Assert.Equal("4", magicai.Tier);
        Assert.Equal("r***@e***", magicai.EmailMasked);
        Assert.True(magicai.EmailConfigured);
        Assert.True(magicai.PasswordConfigured);
        Assert.False(magicai.PasswordAltConfigured);
        Assert.Equal("login_only", magicai.Status);
        Assert.Equal(1, magicai.DeclaredAccountCount);
        Assert.Equal(1, magicai.LoginReadyAccountCount);
        Assert.Equal(0, magicai.ApiKeyReadyAccountCount);
        Assert.Equal(1, magicai.PendingApiKeyAccountCount);
        ExecutiveAssistantCredentialSlotEntry runsitePoolAccount = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<ExecutiveAssistantCredentialSlotEntry>>(magicai.CredentialSlots));
        Assert.Equal("RUNSITE_01", runsitePoolAccount.Alias, StringComparer.OrdinalIgnoreCase);
        Assert.Equal("login_only", runsitePoolAccount.Status);

        string serialized = System.Text.Json.JsonSerializer.Serialize(service.GetCatalog());
        Assert.DoesNotContain("shared-password", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("runsite@example.invalid", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public void GetCatalog_tracks_magicai_pool_counts_across_multiple_declared_accounts_without_leaking_emails_or_keys()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_MAGICAI_TIER"] = "4",
                ["MAGICAI_ACCOUNT_01_EMAIL"] = "one@example.invalid",
                ["MAGICAI_ACCOUNT_01_PASSWORD"] = "pw-one",
                ["MAGICAI_ACCOUNT_02_EMAIL"] = "two@example.invalid",
                ["MAGICAI_ACCOUNT_02_PASSWORD"] = "pw-two",
                ["MAGICAI_ACCOUNT_02_API_KEY"] = "api-two",
                ["MAGICAI_ACCOUNT_03_API_KEY"] = "api-three"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry magicai = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "magicai");
        IReadOnlyList<ExecutiveAssistantCredentialSlotEntry> slots = Assert.IsAssignableFrom<IReadOnlyList<ExecutiveAssistantCredentialSlotEntry>>(magicai.CredentialSlots);

        Assert.Equal(3, magicai.DeclaredAccountCount);
        Assert.Equal(2, magicai.LoginReadyAccountCount);
        Assert.Equal(2, magicai.ApiKeyReadyAccountCount);
        Assert.Equal(1, magicai.PendingApiKeyAccountCount);
        Assert.Equal(3, slots.Count);
        Assert.Contains(slots, static slot => slot.Alias == "01" && slot.Status == "login_only");
        Assert.Contains(slots, static slot => slot.Alias == "02" && slot.Status == "configured");
        Assert.Contains(slots, static slot => slot.Alias == "03" && slot.Status == "api_key_only");

        string serialized = System.Text.Json.JsonSerializer.Serialize(service.GetCatalog());
        Assert.DoesNotContain("one@example.invalid", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("two@example.invalid", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("api-two", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("api-three", serialized, StringComparison.Ordinal);
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
    public void GetCatalog_marks_sendr_api_key_only_ready_without_leaking_key()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_SENDR_TIER"] = "4",
                ["SENDR_API_KEY"] = "sendr-fallback-api-secret"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry sendr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "sendr");
        Assert.Equal("4", sendr.Tier);
        Assert.False(sendr.EmailConfigured);
        Assert.False(sendr.PasswordConfigured);
        Assert.True(sendr.PasswordAltConfigured);
        Assert.Equal("api_configured", sendr.Status);

        string serialized = System.Text.Json.JsonSerializer.Serialize(service.GetCatalog());
        Assert.DoesNotContain("sendr-fallback-api-secret", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public void GetCatalog_marks_sendr_api_token_alias_ready_without_leaking_token()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_SENDR_TIER"] = "4",
                ["SENDR_API_TOKEN"] = "sendr-token-secret"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry sendr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "sendr");
        Assert.Equal("4", sendr.Tier);
        Assert.False(sendr.EmailConfigured);
        Assert.False(sendr.PasswordConfigured);
        Assert.True(sendr.PasswordAltConfigured);
        Assert.Equal("api_configured", sendr.Status);

        string serialized = System.Text.Json.JsonSerializer.Serialize(service.GetCatalog());
        Assert.DoesNotContain("sendr-token-secret", serialized, StringComparison.Ordinal);
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
    public void GetCatalog_marks_unmixr_api_configured_until_voice_id_is_configured()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_UNMIXR_TIER"] = "4",
                ["UNMIXR_ACCOUNT_NEW_TIER4_EMAIL"] = "voice-account@example.invalid",
                ["UNMIXR_ACCOUNT_NEW_TIER4_API_KEY"] = "generic-unmixr-api-secret",
                ["UNMIXR_ACCOUNT_NEW_TIER4_VOICE_ID"] = ""
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry unmixr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "unmixr");

        Assert.Equal("4", unmixr.Tier);
        Assert.False(unmixr.PasswordAltConfigured);
        Assert.Equal("api_configured_voice_missing", unmixr.Status);

        string serialized = System.Text.Json.JsonSerializer.Serialize(service.GetCatalog());
        Assert.DoesNotContain("generic-unmixr-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("voice-account@example.invalid", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public void GetCatalog_marks_unmixr_configured_from_generic_account_alias_without_leaking_runtime_secrets()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_EA_UNMIXR_TIER"] = "4",
                ["UNMIXR_ACCOUNT_TIBOR_CHUMMER_RUN_EMAIL"] = "tibor@chummer.run",
                ["UNMIXR_ACCOUNT_TIBOR_CHUMMER_RUN_API_KEY"] = "generic-unmixr-api-secret",
                ["UNMIXR_ACCOUNT_TIBOR_CHUMMER_RUN_VOICE_ID"] = "generic-voice-secret"
            })
            .Build();

        ExecutiveAssistantCredentialCatalogService service = new(configuration);

        ExecutiveAssistantCredentialEntry unmixr = Assert.Single(service.GetCatalog().Entries, static entry => entry.ToolId == "unmixr");

        Assert.Equal("4", unmixr.Tier);
        Assert.True(unmixr.PasswordAltConfigured);
        Assert.Equal("configured", unmixr.Status);

        string serialized = System.Text.Json.JsonSerializer.Serialize(service.GetCatalog());
        Assert.DoesNotContain("generic-unmixr-api-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("generic-voice-secret", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("tibor@chummer.run", serialized, StringComparison.Ordinal);
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
