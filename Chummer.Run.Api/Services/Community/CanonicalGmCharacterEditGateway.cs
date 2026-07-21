using System.Collections.Immutable;
using Chummer.Campaign.Contracts;
using Chummer.Contracts.Owners;
using Chummer.Contracts.Workspaces;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

/// <summary>
/// Safe runtime default when the durable Core workspace store has not been
/// explicitly provisioned. It implements the package-owned boundary and can
/// neither read nor mutate character state.
/// </summary>
public sealed class UnavailableCoreGmCharacterEditGateway : ICoreGmCharacterEditGateway
{
    public DelegatedGmCharacterProfileReadResult ReadCurrentProfile(
        DelegatedGmCharacterProfileReadCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        return new DelegatedGmCharacterProfileReadResult(
            DelegatedGmCharacterProfileReadOutcome.Unavailable,
            ErrorCode: "core_gm_character_edit_store_unconfigured");
    }

    public DelegatedGmCharacterEditResult Execute(DelegatedGmCharacterEditCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        return new DelegatedGmCharacterEditResult(
            DelegatedGmCharacterEditOutcome.Unavailable,
            ErrorCode: "core_gm_character_edit_store_unconfigured");
    }
}

/// <summary>
/// Hub-owned campaign authority adapter. Core calls this adapter on every
/// delegated profile read and mutation, so serialized role labels or a stale
/// prior decision can never authorize owner-scoped character access.
/// </summary>
public sealed class CommunityStoreCampaignGmCharacterEditAuthorizer
    : ICampaignGmCharacterEditAuthorizer
{
    private const string CollaborationCapability = "campaign_collaboration";
    private const string OwnerRole = "owner";
    private const string GmRole = "gm";
    private const string GmCharacterEditorAuthority = "gm_character_editor";
    private const string HubRunnerDossierAuthorityKind = "hub_runner_dossier";
    private static readonly TimeSpan DecisionLifetime = TimeSpan.FromMinutes(1);
    private static readonly ImmutableArray<string> AllowedProfilePaths =
    [
        DelegatedGmCharacterEditContract.ProfileAliasPath,
        DelegatedGmCharacterEditContract.ProfileNamePath
    ];

    private readonly CommunityStore _store;
    private readonly TimeProvider _timeProvider;

    public CommunityStoreCampaignGmCharacterEditAuthorizer(
        CommunityStore store,
        TimeProvider timeProvider)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
    }

    public CampaignGmCharacterEditAuthorization Authorize(
        CampaignGmCharacterEditAuthorizationRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        DateTimeOffset nowUtc = _timeProvider.GetUtcNow().ToUniversalTime();
        lock (_store.Gate)
        {
            return TryAuthorizeLocked(request, nowUtc, out CampaignGmCharacterEditAuthorization? authorization)
                ? authorization
                : Denied(request, nowUtc);
        }
    }

    private bool TryAuthorizeLocked(
        CampaignGmCharacterEditAuthorizationRequest request,
        DateTimeOffset nowUtc,
        out CampaignGmCharacterEditAuthorization authorization)
    {
        authorization = null!;
        string campaignId = request.CampaignId?.Trim() ?? string.Empty;
        string actorId = request.ActorId?.Trim() ?? string.Empty;
        string characterId = request.CharacterId.Value?.Trim() ?? string.Empty;
        string ownerId = request.CharacterOwner.NormalizedValue;
        if (campaignId.Length == 0
            || actorId.Length == 0
            || characterId.Length == 0
            || ownerId.Length == 0
            || request.CharacterOwner.UsesLocalSingleUserValue
            || request.RequestedPatchPaths.IsDefaultOrEmpty
            || request.RequestedPatchPaths.Any(path =>
                path is null
                || !AllowedProfilePaths.Contains(path.Trim(), StringComparer.Ordinal)))
        {
            return false;
        }

        if (!_store.CampaignSpinesById.TryGetValue(campaignId, out CampaignProjection? campaign)
            || !_store.GroupsById.TryGetValue(campaign.GroupId, out GroupDto? group)
            || !group.Capabilities.Contains(CollaborationCapability, StringComparer.Ordinal))
        {
            return false;
        }

        GroupMembershipDto? membership = group.Memberships.FirstOrDefault(member =>
            string.Equals(member.UserId, actorId, StringComparison.OrdinalIgnoreCase));
        if (membership is null
            || !(string.Equals(group.OwnerUserId, actorId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(membership.Role, GmRole, StringComparison.OrdinalIgnoreCase))
            || (string.Equals(membership.Role, OwnerRole, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(group.OwnerUserId, actorId, StringComparison.OrdinalIgnoreCase)))
        {
            return false;
        }

        CampaignCharacterBindingState? binding = _store.CampaignCharacterBindings
            .Where(item => string.Equals(
                    item.CampaignId,
                    campaign.CampaignId,
                    StringComparison.OrdinalIgnoreCase)
                && string.Equals(
                    item.AuthoritativeCharacterId,
                    characterId,
                    StringComparison.Ordinal))
            .OrderByDescending(static item => item.BindingRevision)
            .ThenByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();
        if (binding is null
            || !campaign.DossierIds.Contains(binding.DossierId, StringComparer.OrdinalIgnoreCase)
            || !_store.DossiersById.TryGetValue(binding.DossierId, out RunnerDossierProjection? dossier)
            || !string.Equals(binding.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(binding.AuthorityKind, HubRunnerDossierAuthorityKind, StringComparison.Ordinal)
            || !string.Equals(binding.AuthoritativeCharacterId, dossier.DossierId, StringComparison.Ordinal)
            || !string.Equals(binding.AuthenticatedOwnerUserId, ownerId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(dossier.OwnerUserId, ownerId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(binding.GmAuthorityRole, GmCharacterEditorAuthority, StringComparison.Ordinal)
            || !string.Equals(binding.GrantedByUserId, ownerId, StringComparison.OrdinalIgnoreCase)
            || binding.BindingRevision <= 0
            || binding.CurrentRevision <= 0
            || string.IsNullOrWhiteSpace(binding.BindingId)
            || string.IsNullOrWhiteSpace(binding.BindingVersionId)
            || binding.GrantedAtUtc.ToUniversalTime() > nowUtc
            || binding.RecordedAtUtc.ToUniversalTime() > nowUtc)
        {
            return false;
        }

        CampaignCharacterBindingState? currentBinding = _store.CampaignCharacterBindings
            .Where(item => string.Equals(
                    item.CampaignId,
                    campaign.CampaignId,
                    StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.DossierId, binding.DossierId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.BindingRevision)
            .ThenByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();
        if (currentBinding is null
            || !string.Equals(currentBinding.BindingId, binding.BindingId, StringComparison.Ordinal)
            || !string.Equals(
                currentBinding.BindingVersionId,
                binding.BindingVersionId,
                StringComparison.Ordinal)
            || currentBinding.BindingRevision != binding.BindingRevision)
        {
            return false;
        }

        authorization = new CampaignGmCharacterEditAuthorization(
            Authorized: true,
            CampaignId: campaign.CampaignId,
            ActorId: actorId,
            Role: DelegatedGmCharacterEditContract.GameMasterRole,
            Scope: DelegatedGmCharacterEditContract.CharacterEditScope,
            CharacterOwner: new OwnerScope(binding.AuthenticatedOwnerUserId),
            CharacterId: new CharacterWorkspaceId(binding.AuthoritativeCharacterId),
            DelegationId: binding.BindingId,
            GrantedByCampaignOwnerId: group.OwnerUserId,
            GrantedByCharacterOwnerId: ownerId,
            AuthorityReceiptId: binding.BindingVersionId,
            AuthorityRevision: binding.BindingRevision,
            ValidFromUtc: binding.GrantedAtUtc.ToUniversalTime(),
            ExpiresAtUtc: nowUtc.Add(DecisionLifetime),
            AllowedPatchPaths: AllowedProfilePaths);
        return true;
    }

    private static CampaignGmCharacterEditAuthorization Denied(
        CampaignGmCharacterEditAuthorizationRequest request,
        DateTimeOffset nowUtc)
        => new(
            Authorized: false,
            CampaignId: request.CampaignId?.Trim() ?? string.Empty,
            ActorId: request.ActorId?.Trim() ?? string.Empty,
            Role: string.Empty,
            Scope: string.Empty,
            CharacterOwner: request.CharacterOwner,
            CharacterId: request.CharacterId,
            DelegationId: string.Empty,
            GrantedByCampaignOwnerId: string.Empty,
            GrantedByCharacterOwnerId: string.Empty,
            AuthorityReceiptId: string.Empty,
            AuthorityRevision: 0,
            ValidFromUtc: nowUtc,
            ExpiresAtUtc: nowUtc,
            AllowedPatchPaths: ImmutableArray<string>.Empty,
            DenialReason: "current_campaign_gm_character_edit_grant_required");
}
