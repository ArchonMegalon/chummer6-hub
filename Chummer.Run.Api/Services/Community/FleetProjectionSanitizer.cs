using System.Text.Json.Nodes;

namespace Chummer.Run.Api.Services.Community;

internal static class FleetProjectionSanitizer
{
    public static object? Build(JsonObject? fleet)
    {
        var lane = fleet?["lane"] as JsonObject;
        if (lane is null)
        {
            return null;
        }

        var telemetry = lane["telemetry"] as JsonObject;
        var deviceAuth = lane["device_auth"] as JsonObject;
        var credentialHandle = ReadString(lane, "credential_handle") ?? ReadString(telemetry, "credential_handle");

        return new
        {
            laneId = ReadString(lane, "lane_id"),
            status = ReadString(lane, "status"),
            laneRole = ReadString(lane, "lane_role") ?? ReadString(telemetry, "lane_role"),
            authorizationTier = ReadString(lane, "authorization_tier") ?? ReadString(telemetry, "authorization_tier"),
            tierSource = ReadString(lane, "tier_source") ?? ReadString(telemetry, "tier_source"),
            auth = new
            {
                verificationUri = ReadString(deviceAuth, "verification_uri") ?? ReadString(telemetry, "verification_uri"),
                userCode = ReadString(deviceAuth, "user_code") ?? ReadString(telemetry, "user_code"),
                authReady = ReadBool(deviceAuth, "auth_ready") || ReadBool(telemetry, "auth_ready"),
            },
            credentialHandlePresent = !string.IsNullOrWhiteSpace(credentialHandle),
        };
    }

    private static string? ReadString(JsonObject? node, string propertyName)
        => node?[propertyName]?.GetValue<string?>();

    private static bool ReadBool(JsonObject? node, string propertyName)
        => node?[propertyName]?.GetValue<bool?>() ?? false;
}
