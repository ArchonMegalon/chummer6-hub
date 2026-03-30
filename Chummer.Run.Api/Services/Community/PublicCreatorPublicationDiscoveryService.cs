using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Registry.Services;

namespace Chummer.Run.Api.Services.Community;

public sealed class PublicCreatorPublicationDiscoveryService
{
    private readonly AccountService _accounts;
    private readonly CampaignSpineService _campaignSpine;
    private readonly IHubPublicationDraftService _drafts;

    public PublicCreatorPublicationDiscoveryService(
        AccountService accounts,
        CampaignSpineService campaignSpine,
        IHubPublicationDraftService drafts)
    {
        _accounts = accounts;
        _campaignSpine = campaignSpine;
        _drafts = drafts;
    }

    public IReadOnlyList<CreatorPublicationProjection> ListDiscoverable(int limit = 3)
    {
        if (limit <= 0)
        {
            return Array.Empty<CreatorPublicationProjection>();
        }

        HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        return _drafts.ListDrafts(state: HubPublicationStates.Published)
            .Items
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ThenBy(static item => item.DraftId, StringComparer.OrdinalIgnoreCase)
            .Select(ResolvePublication)
            .Where(static item => item is not null)
            .Select(static item => item!)
            .Where(item =>
                item.Discoverable
                && string.Equals(item.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase)
                && seen.Add(item.PublicationId))
            .Take(limit)
            .ToArray();
    }

    public CreatorPublicationProjection? GetDiscoverable(string publicationId)
    {
        if (string.IsNullOrWhiteSpace(publicationId))
        {
            return null;
        }

        HubPublishDraftReceipt? draft = _drafts.GetDraft(publicationId);
        if (draft is null || !string.Equals(draft.State, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        CreatorPublicationProjection? publication = ResolvePublication(draft);
        return publication is { Discoverable: true }
            && string.Equals(publication.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase)
            ? publication
            : null;
    }

    private CreatorPublicationProjection? ResolvePublication(HubPublishDraftReceipt draft)
    {
        HubUserDto? owner = _accounts.GetById(draft.OwnerId);
        return owner is null ? null : _campaignSpine.GetCreatorPublication(owner, draft.DraftId);
    }
}
