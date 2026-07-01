using System.Text.Json;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ReadyForTonightServiceTests
{
    [Fact]
    public void Mobile_handoff_names_playtime_tools_and_opt_in_boundaries()
    {
        var service = new ReadyForTonightService();
        using JsonDocument document = JsonDocument.Parse(service.BuildMobileHandoffJson());
        JsonElement root = document.RootElement;

        Assert.Equal("ready_for_tonight", root.GetProperty("mode").GetString());
        Assert.Equal("ready", root.GetProperty("status").GetString());
        Assert.Equal("/mobile", root.GetProperty("next_best_screen").GetString());
        Assert.Equal("/mobile", root.GetProperty("pwa_route").GetString());
        Assert.Equal("/play/continuity", root.GetProperty("continuity_route").GetString());

        string serialized = root.GetRawText();
        Assert.Contains("character building stays before or after the session", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("account opt-in", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("followed-world selection", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("GM remains final authority", serialized, StringComparison.Ordinal);

        var toolIds = root.GetProperty("playtime_tools")
            .EnumerateArray()
            .Select(item => item.GetProperty("id").GetString())
            .ToHashSet(StringComparer.Ordinal);

        foreach (string requiredTool in new[] { "inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world" })
        {
            Assert.Contains(requiredTool, toolIds);
        }

        var roles = root.GetProperty("packet_routes")
            .EnumerateArray()
            .Select(item => item.GetProperty("roleId").GetString())
            .ToHashSet(StringComparer.Ordinal);

        foreach (string requiredRole in new[] { "player", "gm", "organizer" })
        {
            Assert.Contains(requiredRole, roles);
        }
    }
}
