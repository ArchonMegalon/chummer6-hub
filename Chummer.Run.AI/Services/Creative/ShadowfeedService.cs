using Chummer.Run.Contracts.Media;

namespace Chummer.Run.AI.Services.Creative;

public interface IShadowfeedService
{
    Task<ShadowfeedResult> DraftAsync(
        ShadowfeedRequest request,
        CancellationToken cancellationToken = default);
}

public sealed class ShadowfeedService : IShadowfeedService
{
    public Task<ShadowfeedResult> DraftAsync(
        ShadowfeedRequest request,
        CancellationToken cancellationToken = default)
    {
        var region = string.IsNullOrWhiteSpace(request.Region) ? "Unknown District" : request.Region;
        var district = string.IsNullOrWhiteSpace(request.District) ? "Unknown Sector" : request.District;
        var hooks = request.Hooks ?? Array.Empty<string>();

        var headline = new List<string>
        {
            $"[{district}] Heat signature changes recorded near {region}.",
            $"Matrix noise suggests watchlist activity.",
            $"Rumor line: {(hooks.Count > 0 ? hooks[0] : "No additional rumor thread observed")}"
        };

        var rumors = hooks.Count == 0
            ? Array.Empty<string>()
            : hooks.Take(5).Select(hook => $"RUMOR: {hook}").ToArray();

        var police = new[]
        {
            $"Police chatter suggests 2-3 patrol route updates in {district}.",
            $"Local chatter references possible interdiction in sector {district.Split(' ', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? district}."
        };

        var matrix = new[]
        {
            $"Matrix posts flagged for {region}: unresolved signal drift in local nodes.",
            $"Ghost traffic suggests one dormant host has resumed active relay."
        };

        var result = new ShadowfeedResult(
            CampaignId: request.CampaignId,
            SceneId: request.SceneId,
            Region: region,
            District: district,
            Headline: headline,
            RumorFeed: rumors,
            PoliceChatter: police,
            MatrixPosts: matrix,
            ApprovedPayloadAssetId: null);

        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(result);
    }
}
