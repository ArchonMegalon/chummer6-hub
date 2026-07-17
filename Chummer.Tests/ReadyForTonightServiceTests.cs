using System.Text.Json;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ReadyForTonightServiceTests
{
    [Fact]
    public void Mobile_handoff_names_playtime_tools_and_opt_in_boundaries()
    {
        ReadyForTonightService service = new();

        using JsonDocument document = JsonDocument.Parse(service.BuildMobileHandoffJson());
        JsonElement root = document.RootElement;

        Assert.Equal("ready_for_tonight", root.GetProperty("mode").GetString());
        Assert.Equal("ready", root.GetProperty("status").GetString());
        Assert.Equal("/mobile", root.GetProperty("next_best_screen").GetString());
        Assert.Equal("/mobile", root.GetProperty("pwa_route").GetString());
        Assert.Equal("/play/continuity", root.GetProperty("continuity_route").GetString());
        Assert.Equal("/mobile/player", root.GetProperty("frontdoor_launch_route").GetString());

        string serialized = root.GetRawText();
        foreach (string expectedTool in new[]
        {
            "inventory",
            "health",
            "ammo",
            "modifiers",
            "quick_rolls",
            "living_world"
        })
        {
            Assert.Contains(expectedTool, serialized, StringComparison.Ordinal);
        }

        Assert.Contains("account opt-in", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("followed-world", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("GM remains final authority", serialized, StringComparison.Ordinal);
        Assert.Contains("character building stays before or after the session", serialized, StringComparison.OrdinalIgnoreCase);

        HashSet<string?> toolIds = root.GetProperty("playtime_tools")
            .EnumerateArray()
            .Select(item => item.GetProperty("id").GetString())
            .ToHashSet(StringComparer.Ordinal);
        foreach (string requiredTool in new[]
        {
            "inventory",
            "health",
            "ammo",
            "modifiers",
            "quick_rolls",
            "living_world"
        })
        {
            Assert.Contains(requiredTool, toolIds);
        }

        HashSet<string?> packetRoles = root.GetProperty("packet_routes")
            .EnumerateArray()
            .Select(item => item.GetProperty("roleId").GetString())
            .ToHashSet(StringComparer.Ordinal);
        foreach (string requiredRole in new[] { "player", "gm", "organizer" })
        {
            Assert.Contains(requiredRole, packetRoles);
        }

        JsonElement roleRoutes = root.GetProperty("role_routes");
        Assert.Equal(JsonValueKind.Array, roleRoutes.ValueKind);
        JsonElement[] routes = roleRoutes.EnumerateArray().ToArray();
        Assert.Equal(2, routes.Length);

        Assert.Equal("Player", routes[0].GetProperty("role").GetString());
        Assert.Equal("player", routes[0].GetProperty("mode").GetString());
        Assert.Equal("/mobile/player", routes[0].GetProperty("route").GetString());
        Assert.Equal("/manifest.player.webmanifest", routes[0].GetProperty("manifest_path").GetString());
        Assert.Equal("/mobile/player", routes[0].GetProperty("manifest_id").GetString());
        Assert.Equal("/mobile/player", routes[0].GetProperty("manifest_start_url").GetString());
        Assert.Equal("/mobile/player?sessionId={sessionId}&role=Player", routes[0].GetProperty("session_handoff_route_template").GetString());
        Assert.True(routes[0].GetProperty("frontdoor_default").GetBoolean());

        Assert.Equal("GameMaster", routes[1].GetProperty("role").GetString());
        Assert.Equal("gm", routes[1].GetProperty("mode").GetString());
        Assert.Equal("/mobile/gm", routes[1].GetProperty("route").GetString());
        Assert.Equal("/manifest.gm.webmanifest", routes[1].GetProperty("manifest_path").GetString());
        Assert.Equal("/mobile/gm", routes[1].GetProperty("manifest_id").GetString());
        Assert.Equal("/mobile/gm", routes[1].GetProperty("manifest_start_url").GetString());
        Assert.Equal("/mobile/gm?sessionId={sessionId}&role=GameMaster", routes[1].GetProperty("session_handoff_route_template").GetString());
        Assert.False(routes[1].GetProperty("frontdoor_default").GetBoolean());
    }
}
