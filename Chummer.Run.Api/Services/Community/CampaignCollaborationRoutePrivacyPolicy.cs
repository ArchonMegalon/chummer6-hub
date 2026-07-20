using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services.Community;

internal static class CampaignCollaborationRoutePrivacyPolicy
{
    public static bool RequiresPrivateHeaders(PathString path)
        => path.StartsWithSegments("/api/v1/campaigns", StringComparison.OrdinalIgnoreCase)
            || path.Equals("/api/v1/antiforgery", StringComparison.OrdinalIgnoreCase)
            || path.StartsWithSegments("/join/campaign", StringComparison.OrdinalIgnoreCase);
}
