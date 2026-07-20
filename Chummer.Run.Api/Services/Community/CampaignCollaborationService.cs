using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignCollaborationService
{
    private const int MaxNameLength = 160;
    private const int MaxSummaryLength = 4000;
    private const int MaxHandleLength = 80;
    private const int MaxDisplayNameLength = 160;
    private const int MaxReasonLength = 512;
    private const int MaxSectionCount = 64;
    private const int MinInviteMinutes = 5;
    private const int MaxInviteMinutes = 30 * 24 * 60;
    private const int MaxInviteUses = 100;
    private const int MaxCampaignsPerOwner = 32;
    private const int MaxActiveInvitesPerCampaign = 32;
    private const int MaxCampaignRosterSize = 100;
    private const int MaxIdempotencyKeyLength = 128;
    private const int MaxInviteAttemptsPerWindow = 10;
    private static readonly TimeSpan InviteAttemptWindow = TimeSpan.FromMinutes(10);
    private static readonly TimeSpan InviteRetention = TimeSpan.FromDays(7);
    private const string ShortCodeAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    private const string PlayerRole = "player";
    private const string OwnerRole = "owner";
    private const string GmRole = "gm";
    private const string GmOwnerRole = "gm_owner";
    private const string GmEditorRole = "gm_editor";
    private const string GmCharacterEditorAuthority = "gm_character_editor";
    private const string NoGmCharacterAuthority = "none";
    private const string HubRunnerDossierAuthorityKind = "hub_runner_dossier";
    private const string DelegatedGmCharacterEditContract = "chummer.delegated-gm-character-edit/v1";
    private const string DelegatedGmActorRole = "game-master";
    private const string DelegatedProfileAliasPath = "/profile/alias";
    private const string DelegatedProfileNamePath = "/profile/name";
    private const int DelegatedGmMaxReasonLength = 500;

    private static readonly JsonSerializerOptions DigestJsonOptions = new(JsonSerializerDefaults.Web);

    private readonly CommunityStore _store;
    private readonly ICanonicalGmCharacterEditGateway _canonicalCharacterEdits;
    private readonly TimeProvider _timeProvider;
    private readonly Dictionary<string, CampaignInviteAttemptWindow> _inviteAttemptsByUserId = new(StringComparer.OrdinalIgnoreCase);

    public CampaignCollaborationService(CommunityStore store)
        : this(store, new UnavailableCoreDelegatedGmCharacterEditGateway(), TimeProvider.System)
    {
    }

    public CampaignCollaborationService(
        CommunityStore store,
        ICanonicalGmCharacterEditGateway canonicalCharacterEdits)
        : this(store, canonicalCharacterEdits, TimeProvider.System)
    {
    }

    internal CampaignCollaborationService(
        CommunityStore store,
        ICanonicalGmCharacterEditGateway canonicalCharacterEdits,
        TimeProvider timeProvider)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _canonicalCharacterEdits = canonicalCharacterEdits
            ?? throw new ArgumentNullException(nameof(canonicalCharacterEdits));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
    }

    public IReadOnlyList<CampaignCollaborationProjection> ListCampaigns(HubUserDto user)
    {
        ArgumentNullException.ThrowIfNull(user);

        lock (_store.Gate)
        {
            return _store.CampaignSpinesById.Values
                .Select(campaign => TryBuildCampaignProjectionLocked(user, campaign))
                .Where(static campaign => campaign is not null)
                .Select(static campaign => campaign!)
                .OrderByDescending(static campaign => campaign.UpdatedAtUtc)
                .ThenBy(static campaign => campaign.Name, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    public CampaignCollaborationProjection? GetCampaign(HubUserDto user, string campaignId)
    {
        ArgumentNullException.ThrowIfNull(user);
        string normalizedCampaignId = NormalizeRequired(campaignId, nameof(campaignId), 128);

        lock (_store.Gate)
        {
            return _store.CampaignSpinesById.TryGetValue(normalizedCampaignId, out CampaignProjection? campaign)
                ? TryBuildCampaignProjectionLocked(user, campaign)
                : null;
        }
    }

    public CampaignCollaborationProjection CreateCampaign(
        HubUserDto gm,
        CreateCampaignCollaborationRequest request)
    {
        ArgumentNullException.ThrowIfNull(gm);
        ArgumentNullException.ThrowIfNull(request);

        string name = NormalizeRequired(request.Name, nameof(request.Name), MaxNameLength);
        string summary = NormalizeOptional(request.Summary, nameof(request.Summary), MaxSummaryLength)
            ?? $"{name} campaign workspace.";
        string visibility = NormalizeVisibility(request.Visibility);
        string initialRunTitle = NormalizeOptional(request.InitialRunTitle, nameof(request.InitialRunTitle), MaxNameLength)
            ?? $"{name}: first run";

        lock (_store.Gate)
        {
            return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                int ownedCampaignCount = _store.CampaignSpinesById.Values.Count(campaign =>
                    _store.GroupsById.TryGetValue(campaign.GroupId, out GroupDto? group)
                    && IsCollaborationGroup(group)
                    && string.Equals(group.OwnerUserId, gm.UserId, StringComparison.OrdinalIgnoreCase));
                if (ownedCampaignCount >= MaxCampaignsPerOwner)
                {
                    throw new InvalidOperationException($"A GM may own at most {MaxCampaignsPerOwner} campaigns.");
                }

                DateTimeOffset now = _timeProvider.GetUtcNow();
                string campaignId = NewId("campaign");
                string groupId = NewId("group");
                string crewId = NewId("crew");
                string runId = NewId("run");
                RuleEnvironmentRef ruleEnvironment = BuildRuleEnvironment(campaignId);

                var ownerMembership = new GroupMembershipDto(
                    MembershipId: NewId("membership"),
                    GroupId: groupId,
                    UserId: gm.UserId,
                    Role: OwnerRole,
                    JoinedAtUtc: now);
                var group = new GroupDto(
                    GroupId: groupId,
                    GroupType: "campaign",
                    Name: name,
                    Visibility: visibility,
                    OwnerUserId: gm.UserId,
                    Capabilities:
                    [
                        "campaign_collaboration",
                    "can_manage_members",
                    "can_issue_campaign_invites",
                    "can_edit_shared_sheets",
                    "can_manage_runsites"
                    ],
                    Memberships: [ownerMembership],
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now);
                var crew = new CrewProjection(
                    CrewId: crewId,
                    Name: $"{name} crew",
                    Visibility: "campaign",
                    GroupId: groupId,
                    CampaignId: campaignId,
                    Members: [],
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now);
                var run = new RunProjection(
                    RunId: runId,
                    CampaignId: campaignId,
                    Title: initialRunTitle,
                    Status: RunStatuses.Planned,
                    Summary: $"GM planning space for {initialRunTitle}.",
                    ActiveSceneId: null,
                    Objectives: [],
                    Scenes: [],
                    LatestContinuity: null,
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now);
                var campaign = new CampaignProjection(
                    CampaignId: campaignId,
                    GroupId: groupId,
                    Name: name,
                    Status: CampaignStatuses.Active,
                    Visibility: visibility,
                    Summary: summary,
                    RuleEnvironment: ruleEnvironment,
                    ActiveRunId: runId,
                    CrewIds: [crewId],
                    DossierIds: [],
                    RunIds: [runId],
                    LatestContinuity: null,
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now);

                _store.GroupsById[groupId] = group;
                _store.CrewsById[crewId] = crew;
                _store.RunsById[runId] = run;
                _store.CampaignSpinesById[campaignId] = campaign;
                HubUserDto currentGm = _store.UsersById.TryGetValue(gm.UserId, out HubUserDto? storedGm)
                    ? storedGm
                    : gm;
                _store.UsersById[gm.UserId] = currentGm with
                {
                    GroupIds = currentGm.GroupIds
                        .Append(groupId)
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
                        .ToArray(),
                    UpdatedAtUtc = now
                };
                return BuildCampaignProjectionLocked(gm, campaign, group, OwnerRole);
            });
        }
    }

    public CampaignInviteSecretProjection CreateInvite(
        HubUserDto gm,
        string campaignId,
        CreateCampaignInviteRequest request)
    {
        ArgumentNullException.ThrowIfNull(gm);
        ArgumentNullException.ThrowIfNull(request);
        if (request.ExpiresInMinutes is < MinInviteMinutes or > MaxInviteMinutes)
        {
            throw new ArgumentOutOfRangeException(
                nameof(request),
                $"invite expiry must be between {MinInviteMinutes} and {MaxInviteMinutes} minutes.");
        }

        if (request.MaxUses is < 1 or > MaxInviteUses)
        {
            throw new ArgumentOutOfRangeException(
                nameof(request),
                $"invite max uses must be between 1 and {MaxInviteUses}.");
        }

        lock (_store.Gate)
        {
            return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                (CampaignProjection campaign, _, _) = RequireManagerCampaignLocked(gm, campaignId);
                DateTimeOffset now = _timeProvider.GetUtcNow();
                PruneInvitesLocked(now);
                int activeInviteCount = _store.CampaignCollaborationInvitesById.Values.Count(invite =>
                    string.Equals(invite.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                    && invite.RevokedAtUtc is null
                    && invite.ExpiresAtUtc > now
                    && invite.Uses < invite.MaxUses);
                if (activeInviteCount >= MaxActiveInvitesPerCampaign)
                {
                    throw new InvalidOperationException($"A campaign may have at most {MaxActiveInvitesPerCampaign} active invites.");
                }

                string inviteId = NewId("invite");
                string salt = Base64UrlEncode(RandomNumberGenerator.GetBytes(16));
                string linkSecret = GenerateUniqueLinkSecretLocked();
                string shortCode = GenerateUniqueShortCodeLocked();
                string shortCodeLookupSha256 = ComputeCodeLookupSha256(NormalizeShortCode(shortCode));
                var state = new CampaignCollaborationInviteState(
                    InviteId: inviteId,
                    CampaignId: campaign.CampaignId,
                    LinkSecretSha256: HashSecret("link", salt, linkSecret),
                    ShortCodeSha256: HashSecret("code", salt, NormalizeShortCode(shortCode)),
                    ShortCodeLookupSha256: shortCodeLookupSha256,
                    DigestSalt: salt,
                    CreatedByUserId: gm.UserId,
                    CreatedAtUtc: now,
                    ExpiresAtUtc: now.AddMinutes(request.ExpiresInMinutes),
                    MaxUses: request.MaxUses,
                    Uses: 0,
                    RevokedAtUtc: null,
                    RevokedByUserId: null);
                _store.CampaignCollaborationInvitesById[state.InviteId] = state;
                _store.CampaignInviteIdByCodeLookupSha256[state.ShortCodeLookupSha256] = state.InviteId;

                return new CampaignInviteSecretProjection(
                    InviteId: state.InviteId,
                    CampaignId: state.CampaignId,
                    JoinPath: $"/join/campaign/{state.InviteId}#secret={linkSecret}",
                    LinkSecret: linkSecret,
                    ShortCode: shortCode,
                    ExpiresAtUtc: state.ExpiresAtUtc,
                    MaxUses: state.MaxUses,
                    CreatedAtUtc: state.CreatedAtUtc);
            });
        }
    }

    public void RevokeInvite(HubUserDto gm, string campaignId, string inviteId)
    {
        ArgumentNullException.ThrowIfNull(gm);
        string normalizedInviteId = NormalizeRequired(inviteId, nameof(inviteId), 128);

        lock (_store.Gate)
        {
            _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                (CampaignProjection campaign, _, _) = RequireManagerCampaignLocked(gm, campaignId);
                if (!_store.CampaignCollaborationInvitesById.TryGetValue(normalizedInviteId, out CampaignCollaborationInviteState? invite)
                    || !string.Equals(invite.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase))
                {
                    throw new KeyNotFoundException("Unknown campaign invite.");
                }

                if (invite.RevokedAtUtc is null)
                {
                    _store.CampaignCollaborationInvitesById[invite.InviteId] = invite with
                    {
                        RevokedAtUtc = _timeProvider.GetUtcNow(),
                        RevokedByUserId = gm.UserId
                    };
                }

                return true;
            });
        }
    }

    public CampaignInviteRedemptionProjection RedeemInvite(
        HubUserDto player,
        string inviteId,
        RedeemCampaignInviteRequest request)
    {
        ArgumentNullException.ThrowIfNull(player);
        ArgumentNullException.ThrowIfNull(request);
        string normalizedInviteId = NormalizeRequired(inviteId, nameof(inviteId), 128);
        string secret = NormalizeInviteSecret(request.Secret);
        string dossierId = NormalizeRequired(request.DossierId, nameof(request.DossierId), 128);
        string authoritativeCharacterId = NormalizeRequired(
            request.AuthoritativeCharacterId,
            nameof(request.AuthoritativeCharacterId),
            128);
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        if (request.ExpectedCharacterRevision < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(request.ExpectedCharacterRevision));
        }

        lock (_store.Gate)
        {
            DateTimeOffset now = _timeProvider.GetUtcNow();
            EnsureInviteAttemptAllowedLocked(player.UserId, now);
            if (!_store.CampaignCollaborationInvitesById.TryGetValue(normalizedInviteId, out CampaignCollaborationInviteState? invite)
                || !SecretMatches(invite, "link", secret))
            {
                RecordInviteFailureLocked(player.UserId, now);
                throw CampaignInviteRejectedException.Create();
            }

            try
            {
                CampaignInviteRedemptionProjection result = RedeemInviteLocked(
                    player,
                    invite,
                    dossierId,
                    authoritativeCharacterId,
                    request.ExpectedCharacterRevision,
                    request.GrantGmEditAuthority,
                    idempotencyKey);
                _inviteAttemptsByUserId.Remove(player.UserId);
                return result;
            }
            catch (CampaignInviteRejectedException)
            {
                RecordInviteFailureLocked(player.UserId, now);
                throw;
            }
        }
    }

    public CampaignInviteRedemptionProjection RedeemJoinCode(
        HubUserDto player,
        RedeemCampaignJoinCodeRequest request)
    {
        ArgumentNullException.ThrowIfNull(player);
        ArgumentNullException.ThrowIfNull(request);
        string normalizedCode = NormalizeShortCode(request.Code);
        string dossierId = NormalizeRequired(request.DossierId, nameof(request.DossierId), 128);
        string authoritativeCharacterId = NormalizeRequired(
            request.AuthoritativeCharacterId,
            nameof(request.AuthoritativeCharacterId),
            128);
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        if (request.ExpectedCharacterRevision < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(request.ExpectedCharacterRevision));
        }

        lock (_store.Gate)
        {
            DateTimeOffset now = _timeProvider.GetUtcNow();
            EnsureInviteAttemptAllowedLocked(player.UserId, now);
            string lookup = ComputeCodeLookupSha256(normalizedCode);
            CampaignCollaborationInviteState? matched =
                _store.CampaignInviteIdByCodeLookupSha256.TryGetValue(lookup, out string? matchedInviteId)
                && _store.CampaignCollaborationInvitesById.TryGetValue(matchedInviteId, out CampaignCollaborationInviteState? invite)
                && SecretMatches(invite, "code", normalizedCode)
                    ? invite
                    : null;

            if (matched is null)
            {
                RecordInviteFailureLocked(player.UserId, now);
                throw CampaignInviteRejectedException.Create();
            }

            try
            {
                CampaignInviteRedemptionProjection result = RedeemInviteLocked(
                    player,
                    matched,
                    dossierId,
                    authoritativeCharacterId,
                    request.ExpectedCharacterRevision,
                    request.GrantGmEditAuthority,
                    idempotencyKey);
                _inviteAttemptsByUserId.Remove(player.UserId);
                return result;
            }
            catch (CampaignInviteRejectedException)
            {
                RecordInviteFailureLocked(player.UserId, now);
                throw;
            }
        }
    }

    public IReadOnlyList<CampaignEligibleCharacterProjection> ListEligibleCharacters(HubUserDto user)
    {
        ArgumentNullException.ThrowIfNull(user);
        lock (_store.Gate)
        {
            return _store.DossiersById.Values
                .Where(dossier => string.Equals(dossier.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .Select(dossier =>
                {
                    ValidateDossierForProjection(dossier);
                    long revision = _store.CampaignCharacterBindings
                        .Where(binding => string.Equals(binding.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase))
                        .Select(static binding => binding.CurrentRevision)
                        .DefaultIfEmpty(1)
                        .Max();
                    return new CampaignEligibleCharacterProjection(
                        dossier.DossierId,
                        HubRunnerDossierAuthorityKind,
                        dossier.DossierId,
                        dossier.RunnerHandle.Trim(),
                        dossier.DisplayName.Trim(),
                        dossier.Status,
                        revision,
                        dossier.UpdatedAtUtc);
                })
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
        }
    }

    public IReadOnlyList<CampaignRosterEntryProjection> GetRoster(HubUserDto user, string campaignId)
        => GetCampaign(user, campaignId)?.Roster
            ?? throw new KeyNotFoundException("Unknown campaign.");

    public CampaignPlayerSafeSheetProjection GetSharedSheet(
        HubUserDto user,
        string campaignId,
        string dossierId)
    {
        ArgumentNullException.ThrowIfNull(user);
        string normalizedDossierId = NormalizeRequired(dossierId, nameof(dossierId), 128);

        lock (_store.Gate)
        {
            (CampaignProjection campaign, GroupDto group, string role) = RequireMemberCampaignLocked(user, campaignId);
            return BuildSharedSheetLocked(
                campaign,
                normalizedDossierId,
                CanManage(group, user.UserId, role));
        }
    }

    public CampaignSharedSheetEditReceipt UpdateSharedSheet(
        HubUserDto gm,
        string campaignId,
        string dossierId,
        CampaignSharedSheetUpdateRequest request)
    {
        ArgumentNullException.ThrowIfNull(gm);
        ArgumentNullException.ThrowIfNull(request);
        if (request.ExpectedRevision <= 0 || request.ExpectedRevision == long.MaxValue)
        {
            throw new ArgumentOutOfRangeException(nameof(request.ExpectedRevision));
        }

        string normalizedCampaignId = NormalizeRequired(campaignId, nameof(campaignId), 128);
        string normalizedDossierId = NormalizeRequired(dossierId, nameof(dossierId), 128);
        string runnerHandle = NormalizeRequired(request.RunnerHandle, nameof(request.RunnerHandle), MaxHandleLength);
        string displayName = NormalizeRequired(request.DisplayName, nameof(request.DisplayName), MaxDisplayNameLength);
        string status = NormalizeDossierStatus(request.Status);
        string reason = NormalizeRequired(request.Reason, nameof(request.Reason), DelegatedGmMaxReasonLength);
        IReadOnlyList<PublicationSafeProjection>? requestedSections = request.Sections is null
            ? null
            : NormalizeSafeSections(request.Sections);
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        string commandKey = BuildCommandKey(gm.UserId, "sheet-edit", idempotencyKey);
        string requestSha256 = ComputeSha256(new
        {
            CampaignId = normalizedCampaignId,
            DossierId = normalizedDossierId,
            request.ExpectedRevision,
            RunnerHandle = runnerHandle,
            DisplayName = displayName,
            Status = status,
            Reason = reason,
            Sections = requestedSections
        });

        lock (_store.Gate)
        {
            (CampaignProjection campaign, GroupDto group, _) = RequireManagerCampaignLocked(gm, normalizedCampaignId);
            CampaignCharacterBindingState binding = RequireCurrentBindingLocked(campaign.CampaignId, normalizedDossierId);
            if (!_store.DossiersById.TryGetValue(normalizedDossierId, out RunnerDossierProjection? boundDossier)
                || !string.Equals(boundDossier.OwnerUserId, binding.AuthenticatedOwnerUserId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(binding.AuthorityKind, HubRunnerDossierAuthorityKind, StringComparison.Ordinal)
                || !string.Equals(binding.AuthoritativeCharacterId, boundDossier.DossierId, StringComparison.Ordinal))
            {
                throw new KeyNotFoundException("Unknown campaign sheet.");
            }

            if (!string.Equals(binding.GmAuthorityRole, GmCharacterEditorAuthority, StringComparison.Ordinal))
            {
                throw new CampaignCollaborationAccessDeniedException("The character owner has not granted GM edit authority.");
            }

            if (_store.CampaignSheetEditsByIdempotencyKey.TryGetValue(commandKey, out CampaignSheetEditIdempotencyState? replay))
            {
                if (!string.Equals(replay.RequestSha256, requestSha256, StringComparison.Ordinal))
                {
                    throw new CampaignIdempotencyConflictException();
                }

                return replay.Response;
            }

            CampaignPlayerSafeSheetProjection current = BuildSharedSheetLocked(campaign, normalizedDossierId, canManage: true);
            long currentCharacterRevision = ResolveCurrentCharacterRevisionLocked(normalizedDossierId);
            if (currentCharacterRevision != request.ExpectedRevision)
            {
                throw new CampaignRevisionConflictException(currentCharacterRevision);
            }

            // Core's v1 delegated edit contract owns only profile name and alias
            // (and, when explicitly modeled, notes). Do not let the compatibility
            // request shape turn status or publication-safe sections into a
            // successful Hub-only character mutation.
            if (!string.Equals(status, current.Status, StringComparison.Ordinal)
                || (requestedSections is not null
                    && !string.Equals(
                        ComputeSha256(requestedSections),
                        ComputeSha256(current.Sections),
                        StringComparison.Ordinal)))
            {
                throw new ArgumentException(
                    "GM character edits currently support only displayName and runnerHandle; status and sections must remain unchanged.",
                    nameof(request));
            }

            var canonicalCommand = new CanonicalGmCharacterEditCommand(
                CampaignId: campaign.CampaignId,
                ActorUserId: gm.UserId,
                CampaignOwnerUserId: group.OwnerUserId,
                CharacterOwnerUserId: binding.AuthenticatedOwnerUserId,
                DossierId: current.DossierId,
                AuthorityKind: binding.AuthorityKind,
                AuthoritativeCharacterId: binding.AuthoritativeCharacterId,
                DelegationId: binding.BindingId,
                AuthorityReceiptId: binding.BindingVersionId,
                AuthorityRevision: binding.BindingRevision,
                AuthorityGrantedAtUtc: binding.GrantedAtUtc,
                ExpectedRevision: currentCharacterRevision,
                IdempotencyKey: idempotencyKey,
                Reason: reason,
                RunnerHandle: runnerHandle,
                DisplayName: displayName);
            CanonicalGmCharacterEditResult canonicalResult;
            try
            {
                canonicalResult = _canonicalCharacterEdits.Execute(canonicalCommand);
            }
            catch (Exception exception)
            {
                throw new CampaignCanonicalEditUnavailableException(exception);
            }

            CanonicalGmCharacterEditReceipt canonicalReceipt = RequireCanonicalReceipt(
                canonicalCommand,
                canonicalResult);

            // Keep Hub authorization authoritative across the canonical call. The
            // store lock prevents normal concurrent changes; these checks also
            // fail closed against a re-entrant or defective adapter.
            (CampaignProjection verifiedCampaign, GroupDto verifiedGroup, _) =
                RequireManagerCampaignLocked(gm, normalizedCampaignId);
            CampaignCharacterBindingState verifiedBinding =
                RequireCurrentBindingLocked(verifiedCampaign.CampaignId, normalizedDossierId);
            if (!string.Equals(verifiedGroup.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(verifiedBinding.BindingVersionId, binding.BindingVersionId, StringComparison.Ordinal)
                || !string.Equals(verifiedBinding.GmAuthorityRole, GmCharacterEditorAuthority, StringComparison.Ordinal)
                || ResolveCurrentCharacterRevisionLocked(normalizedDossierId) != currentCharacterRevision)
            {
                throw new CampaignCollaborationAccessDeniedException(
                    "GM edit authority changed while the canonical edit was being reconciled.");
            }

            return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                RunnerDossierProjection dossier = _store.DossiersById[current.DossierId];
                DateTimeOffset now = _timeProvider.GetUtcNow();
                RunnerDossierProjection updatedDossier = dossier with
                {
                    RunnerHandle = canonicalCommand.RunnerHandle,
                    DisplayName = canonicalCommand.DisplayName,
                    UpdatedAtUtc = now
                };
                long nextRevision = canonicalReceipt.NewRevision;
                CampaignCharacterBindingState[] nextBindings = _store.CampaignCharacterBindings
                    .Where(item => string.Equals(item.DossierId, current.DossierId, StringComparison.OrdinalIgnoreCase))
                    .GroupBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
                    .Select(group => group.OrderByDescending(static item => item.BindingRevision).First())
                    .Select(item => item with
                    {
                        BindingVersionId = NewId("binding-version"),
                        BindingRevision = item.BindingRevision + 1,
                        CurrentRevision = nextRevision,
                        RecordedAtUtc = now
                    })
                    .ToArray();
                CampaignCharacterBindingState nextBinding = nextBindings.Single(item =>
                    string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase));
                CampaignPlayerSafeSheetProjection nextProjection = BuildSharedSheetProjection(
                    campaign,
                    updatedDossier,
                    nextBinding,
                    current.Role,
                    canManage: true);
                var audit = new CampaignSharedSheetAuditState(
                    ReceiptId: canonicalReceipt.ReceiptId,
                    CampaignId: campaign.CampaignId,
                    DossierId: current.DossierId,
                    PreviousRevision: canonicalReceipt.PreviousRevision,
                    Revision: nextRevision,
                    IdempotencyKey: idempotencyKey,
                    Reason: reason,
                    EditedByUserId: gm.UserId,
                    BeforeSha256: ComputeSha256(current),
                    AfterSha256: ComputeSha256(nextProjection),
                    EditedAtUtc: canonicalReceipt.AppliedAtUtc);

                _store.DossiersById[current.DossierId] = updatedDossier;
                _store.CampaignCharacterBindings.AddRange(nextBindings);
                _store.CampaignSharedSheetAudit.Add(audit);
                _store.CampaignSpinesById[campaign.CampaignId] = campaign with { UpdatedAtUtc = now };
                CampaignSharedSheetEditReceipt receipt = ToEditReceipt(audit);
                _store.CampaignSheetEditsByIdempotencyKey[commandKey] = new CampaignSheetEditIdempotencyState(
                    commandKey,
                    gm.UserId,
                    idempotencyKey,
                    requestSha256,
                    receipt,
                    now);
                return receipt;
            });
        }
    }

    public CampaignGmAuthorityUpdateReceipt UpdateGmAuthority(
        HubUserDto characterOwner,
        string campaignId,
        string dossierId,
        CampaignGmAuthorityUpdateRequest request)
    {
        ArgumentNullException.ThrowIfNull(characterOwner);
        ArgumentNullException.ThrowIfNull(request);
        string normalizedDossierId = NormalizeRequired(dossierId, nameof(dossierId), 128);
        string normalizedCampaignId = NormalizeRequired(campaignId, nameof(campaignId), 128);
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        string reason = NormalizeRequired(request.Reason, nameof(request.Reason), MaxReasonLength);
        if (request.ExpectedBindingRevision < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(request.ExpectedBindingRevision));
        }

        string commandKey = BuildCommandKey(characterOwner.UserId, "gm-authority", idempotencyKey);
        string requestSha256 = ComputeSha256(new
        {
            CampaignId = normalizedCampaignId,
            DossierId = normalizedDossierId,
            request.ExpectedBindingRevision,
            request.GrantGmEditAuthority,
            Reason = reason
        });

        lock (_store.Gate)
        {
            (CampaignProjection campaign, _, _) = RequireMemberCampaignLocked(characterOwner, normalizedCampaignId);
            CampaignCharacterBindingState current = RequireCurrentBindingLocked(campaign.CampaignId, normalizedDossierId);
            if (!_store.DossiersById.TryGetValue(normalizedDossierId, out RunnerDossierProjection? dossier)
                || !string.Equals(dossier.OwnerUserId, characterOwner.UserId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(current.AuthenticatedOwnerUserId, characterOwner.UserId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException("Unknown campaign sheet.");
            }

            if (_store.CampaignGmAuthorityCommandsByIdempotencyKey.TryGetValue(
                    commandKey,
                    out CampaignGmAuthorityIdempotencyState? replay))
            {
                if (!string.Equals(replay.RequestSha256, requestSha256, StringComparison.Ordinal))
                {
                    throw new CampaignIdempotencyConflictException();
                }

                return replay.Response;
            }

            if (current.BindingRevision != request.ExpectedBindingRevision)
            {
                throw new CampaignBindingRevisionConflictException(current.BindingRevision);
            }

            bool wasGranted = string.Equals(current.GmAuthorityRole, GmCharacterEditorAuthority, StringComparison.Ordinal);
            DateTimeOffset now = _timeProvider.GetUtcNow();
            bool changed = wasGranted != request.GrantGmEditAuthority;
            CampaignCharacterBindingState next = changed
                ? current with
                {
                    BindingVersionId = NewId("binding-version"),
                    BindingRevision = current.BindingRevision + 1,
                    GmAuthorityRole = request.GrantGmEditAuthority
                        ? GmCharacterEditorAuthority
                        : NoGmCharacterAuthority,
                    GrantedByUserId = characterOwner.UserId,
                    GrantedAtUtc = request.GrantGmEditAuthority ? now : current.GrantedAtUtc,
                    RecordedAtUtc = now
                }
                : current;
            var audit = new CampaignGmAuthorityAuditState(
                ReceiptId: NewId("gm-authority"),
                CampaignId: campaign.CampaignId,
                DossierId: normalizedDossierId,
                PreviousBindingRevision: current.BindingRevision,
                BindingRevision: next.BindingRevision,
                CurrentCharacterRevision: ResolveCurrentCharacterRevisionLocked(normalizedDossierId),
                WasGranted: wasGranted,
                IsGranted: request.GrantGmEditAuthority,
                Changed: changed,
                IdempotencyKey: idempotencyKey,
                Reason: reason,
                ChangedByOwnerUserId: characterOwner.UserId,
                ChangedAtUtc: now);
            CampaignGmAuthorityUpdateReceipt receipt = ToGmAuthorityReceipt(audit);

            return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                if (changed)
                {
                    _store.CampaignCharacterBindings.Add(next);
                    _store.CampaignSpinesById[campaign.CampaignId] = campaign with { UpdatedAtUtc = now };
                }

                _store.CampaignGmAuthorityAudit.Add(audit);
                _store.CampaignGmAuthorityCommandsByIdempotencyKey[commandKey] = new CampaignGmAuthorityIdempotencyState(
                    commandKey,
                    characterOwner.UserId,
                    idempotencyKey,
                    requestSha256,
                    receipt,
                    now);
                return receipt;
            });
        }
    }

    public CampaignRunsiteDraftProjection? GetRunsiteDraft(
        HubUserDto gm,
        string campaignId,
        string runId)
    {
        ArgumentNullException.ThrowIfNull(gm);

        lock (_store.Gate)
        {
            (CampaignProjection campaign, _, _) = RequireManagerCampaignLocked(gm, campaignId);
            string normalizedRunId = RequireCampaignRunLocked(campaign, runId).RunId;
            return _store.CampaignRunsitesByRunId.TryGetValue(RunsiteKey(campaign.CampaignId, normalizedRunId), out CampaignRunsiteState? state)
                ? ToDraftProjection(state)
                : null;
        }
    }

    public CampaignRunsiteDraftProjection UpsertRunsiteDraft(
        HubUserDto gm,
        string campaignId,
        string runId,
        CampaignRunsiteDraftUpdateRequest request)
    {
        ArgumentNullException.ThrowIfNull(gm);
        ArgumentNullException.ThrowIfNull(request);
        string title = NormalizeRequired(request.Title, nameof(request.Title), MaxNameLength);
        string summary = NormalizeRequired(request.Summary, nameof(request.Summary), MaxSummaryLength);
        string? gmNotes = NormalizeOptional(request.GmNotes, nameof(request.GmNotes), MaxSummaryLength);
        IReadOnlyList<RunsitePlayerSectionInput> playerSections = NormalizeRunsiteSections(request.PlayerSections);

        lock (_store.Gate)
        {
            (CampaignProjection campaign, _, _) = RequireManagerCampaignLocked(gm, campaignId);
            RunProjection run = RequireCampaignRunLocked(campaign, runId);
            string key = RunsiteKey(campaign.CampaignId, run.RunId);
            _store.CampaignRunsitesByRunId.TryGetValue(key, out CampaignRunsiteState? current);
            long currentRevision = current?.Revision ?? 0;
            if (request.ExpectedRevision != currentRevision)
            {
                throw new CampaignRevisionConflictException(currentRevision);
            }

            DateTimeOffset now = _timeProvider.GetUtcNow();
            CampaignRunsiteState next = new(
                CampaignId: campaign.CampaignId,
                RunId: run.RunId,
                Revision: currentRevision + 1,
                Title: title,
                Summary: summary,
                PlayerSections: playerSections,
                GmNotes: gmNotes,
                UpdatedByUserId: gm.UserId,
                UpdatedAtUtc: now,
                Published: current?.Published);
            return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                _store.CampaignRunsitesByRunId[key] = next;
                _store.RunsById[run.RunId] = run with { UpdatedAtUtc = now };
                _store.CampaignSpinesById[campaign.CampaignId] = campaign with { UpdatedAtUtc = now };
                return ToDraftProjection(next);
            });
        }
    }

    public CampaignRunsitePlayerProjection PublishRunsite(
        HubUserDto gm,
        string campaignId,
        string runId,
        PublishCampaignRunsiteRequest request)
    {
        ArgumentNullException.ThrowIfNull(gm);
        ArgumentNullException.ThrowIfNull(request);

        lock (_store.Gate)
        {
            (CampaignProjection campaign, _, _) = RequireManagerCampaignLocked(gm, campaignId);
            RunProjection run = RequireCampaignRunLocked(campaign, runId);
            string key = RunsiteKey(campaign.CampaignId, run.RunId);
            if (!_store.CampaignRunsitesByRunId.TryGetValue(key, out CampaignRunsiteState? current))
            {
                throw new KeyNotFoundException("Runsite draft does not exist.");
            }

            if (request.ExpectedRevision != current.Revision)
            {
                throw new CampaignRevisionConflictException(current.Revision);
            }

            if (current.Published?.Revision == current.Revision)
            {
                return ToPlayerRunsiteProjection(current.Published);
            }

            DateTimeOffset now = _timeProvider.GetUtcNow();
            var published = new CampaignRunsitePlayerProjection(
                CampaignId: current.CampaignId,
                RunId: current.RunId,
                Revision: current.Revision,
                Title: current.Title,
                Summary: current.Summary,
                Sections: current.PlayerSections.ToArray(),
                PublishedAtUtc: now);
            return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                _store.CampaignRunsitesByRunId[key] = current with
                {
                    Published = published,
                    UpdatedByUserId = gm.UserId,
                    UpdatedAtUtc = now
                };
                _store.RunsById[run.RunId] = run with { UpdatedAtUtc = now };
                _store.CampaignSpinesById[campaign.CampaignId] = campaign with { UpdatedAtUtc = now };
                return published;
            });
        }
    }

    public CampaignRunsitePlayerProjection? GetPublishedRunsite(
        HubUserDto user,
        string campaignId,
        string runId)
    {
        ArgumentNullException.ThrowIfNull(user);

        lock (_store.Gate)
        {
            (CampaignProjection campaign, _, _) = RequireMemberCampaignLocked(user, campaignId);
            RunProjection run = RequireCampaignRunLocked(campaign, runId);
            return _store.CampaignRunsitesByRunId.TryGetValue(RunsiteKey(campaign.CampaignId, run.RunId), out CampaignRunsiteState? state)
                ? state.Published is null ? null : ToPlayerRunsiteProjection(state.Published)
                : null;
        }
    }

    internal IReadOnlyList<CampaignSharedSheetEditReceipt> GetSharedSheetAuditForTests(string dossierId)
    {
        lock (_store.Gate)
        {
            return _store.CampaignSharedSheetAudit
                .Where(item => string.Equals(item.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))
                .Select(ToEditReceipt)
                .ToArray();
        }
    }

    internal IReadOnlyList<CampaignGmAuthorityUpdateReceipt> GetGmAuthorityAuditForTests(string dossierId)
    {
        lock (_store.Gate)
        {
            return _store.CampaignGmAuthorityAudit
                .Where(item => string.Equals(item.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))
                .Select(ToGmAuthorityReceipt)
                .ToArray();
        }
    }

    private CampaignInviteRedemptionProjection RedeemInviteLocked(
        HubUserDto player,
        CampaignCollaborationInviteState invite,
        string dossierId,
        string authoritativeCharacterId,
        long expectedCharacterRevision,
        bool grantGmEditAuthority,
        string idempotencyKey)
    {
        if (!_store.CampaignSpinesById.TryGetValue(invite.CampaignId, out CampaignProjection? campaign)
            || !_store.GroupsById.TryGetValue(campaign.GroupId, out GroupDto? group)
            || !IsCollaborationGroup(group)
            || campaign.CrewIds.Count == 0
            || !_store.CrewsById.TryGetValue(campaign.CrewIds[0], out CrewProjection? crew))
        {
            throw CampaignInviteRejectedException.Create();
        }

        string commandKey = BuildCommandKey(player.UserId, "invite-redeem", idempotencyKey);
        string requestSha256 = ComputeSha256(new
        {
            invite.InviteId,
            DossierId = dossierId,
            AuthoritativeCharacterId = authoritativeCharacterId,
            ExpectedCharacterRevision = expectedCharacterRevision,
            GrantGmEditAuthority = grantGmEditAuthority
        });

        _store.CampaignRedemptionsByIdempotencyKey.TryGetValue(
            commandKey,
            out CampaignRedemptionIdempotencyState? replay);
        if (replay is not null
            && !string.Equals(replay.RequestSha256, requestSha256, StringComparison.Ordinal))
        {
            throw new CampaignIdempotencyConflictException();
        }

        // Replays must not outlive the authenticated dossier ownership that authorized
        // the original join. The exact prior response may be replayed after later sheet
        // revisions, but never after the authoritative character moves to another owner.
        if (!_store.DossiersById.TryGetValue(dossierId, out RunnerDossierProjection? dossier)
            || !string.Equals(dossier.OwnerUserId, player.UserId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(authoritativeCharacterId, dossier.DossierId, StringComparison.Ordinal))
        {
            throw CampaignInviteRejectedException.Create();
        }

        ValidateDossierForProjection(dossier);
        if (replay is not null)
        {
            return replay.Response with { AlreadyJoined = true };
        }

        // Core's owner-scoped character projection/patch operations are not implemented yet.
        // Until a production adapter exists, the only supported authority here is an existing
        // owner-authenticated Hub dossier, and its authoritative id must be the dossier id.
        long currentRevision = ResolveCurrentCharacterRevisionLocked(dossier.DossierId);
        if (expectedCharacterRevision != currentRevision)
        {
            throw new CampaignRevisionConflictException(currentRevision);
        }

        DateTimeOffset now = _timeProvider.GetUtcNow();
        if (invite.RevokedAtUtc is not null
            || invite.ExpiresAtUtc <= now
            || invite.Uses >= invite.MaxUses)
        {
            throw CampaignInviteRejectedException.Create();
        }

        CrewAssignmentProjection? existingAssignment = crew.Members.FirstOrDefault(member =>
            string.Equals(member.UserId, player.UserId, StringComparison.OrdinalIgnoreCase));
        if (existingAssignment is not null
            && group.Memberships.Any(member => string.Equals(member.UserId, player.UserId, StringComparison.OrdinalIgnoreCase)))
        {
            if (!string.Equals(existingAssignment.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase))
            {
                throw CampaignInviteRejectedException.Create();
            }

            CampaignCharacterBindingState existingBinding = RequireCurrentBindingLocked(campaign.CampaignId, dossier.DossierId);
            bool existingGrant = string.Equals(existingBinding.GmAuthorityRole, GmCharacterEditorAuthority, StringComparison.Ordinal);
            if (existingGrant != grantGmEditAuthority)
            {
                throw new CampaignIdempotencyConflictException(
                    "The campaign character is already bound with a different GM authority grant.");
            }

            CampaignInviteRedemptionProjection existingResponse = new(
                CampaignId: campaign.CampaignId,
                DossierId: existingAssignment.DossierId,
                CrewId: crew.CrewId,
                Role: existingAssignment.Role,
                Binding: ToBindingProjection(existingBinding, currentRevision),
                AlreadyJoined: true,
                JoinedAtUtc: existingAssignment.AddedAtUtc);
            return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
            {
                _store.CampaignRedemptionsByIdempotencyKey[commandKey] = new CampaignRedemptionIdempotencyState(
                    commandKey,
                    player.UserId,
                    idempotencyKey,
                    requestSha256,
                    existingResponse,
                    _timeProvider.GetUtcNow());
                return existingResponse;
            });
        }

        if (crew.Members.Count >= MaxCampaignRosterSize)
        {
            throw CampaignInviteRejectedException.Create();
        }

        var assignment = new CrewAssignmentProjection(
            UserId: player.UserId,
            DossierId: dossierId,
            Role: PlayerRole,
            Availability: "active",
            AddedAtUtc: now);
        var binding = new CampaignCharacterBindingState(
            BindingId: NewId("binding"),
            BindingVersionId: NewId("binding-version"),
            CampaignId: campaign.CampaignId,
            DossierId: dossier.DossierId,
            AuthenticatedOwnerUserId: player.UserId,
            AuthorityKind: HubRunnerDossierAuthorityKind,
            AuthoritativeCharacterId: dossier.DossierId,
            BindingRevision: 1,
            CurrentRevision: currentRevision,
            GmAuthorityRole: grantGmEditAuthority ? GmCharacterEditorAuthority : NoGmCharacterAuthority,
            GrantedByUserId: player.UserId,
            GrantedAtUtc: now,
            RecordedAtUtc: now);

        if (group.Memberships.All(member => !string.Equals(member.UserId, player.UserId, StringComparison.OrdinalIgnoreCase)))
        {
            group = group with
            {
                Memberships = group.Memberships.Append(new GroupMembershipDto(
                    MembershipId: NewId("membership"),
                    GroupId: group.GroupId,
                    UserId: player.UserId,
                    Role: PlayerRole,
                    JoinedAtUtc: now)).ToArray(),
                UpdatedAtUtc = now
            };
        }

        crew = crew with
        {
            Members = crew.Members.Append(assignment).ToArray(),
            UpdatedAtUtc = now
        };
        campaign = campaign with
        {
            DossierIds = campaign.DossierIds
                .Append(dossierId)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            UpdatedAtUtc = now
        };

        CampaignInviteRedemptionProjection response = new(
            CampaignId: campaign.CampaignId,
            DossierId: dossierId,
            CrewId: crew.CrewId,
            Role: assignment.Role,
            Binding: ToBindingProjection(binding, currentRevision),
            AlreadyJoined: false,
            JoinedAtUtc: now);

        return _store.ExecuteCampaignCollaborationTransactionLocked(() =>
        {
            _store.GroupsById[group.GroupId] = group;
            _store.CrewsById[crew.CrewId] = crew;
            _store.CampaignSpinesById[campaign.CampaignId] = campaign;
            _store.CampaignCharacterBindings.Add(binding);
            _store.CampaignCollaborationInvitesById[invite.InviteId] = invite with { Uses = invite.Uses + 1 };
            HubUserDto currentPlayer = _store.UsersById.TryGetValue(player.UserId, out HubUserDto? storedPlayer)
                ? storedPlayer
                : player;
            _store.UsersById[player.UserId] = currentPlayer with
            {
                GroupIds = currentPlayer.GroupIds
                    .Append(group.GroupId)
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
                    .ToArray(),
                UpdatedAtUtc = now
            };
            _store.CampaignRedemptionsByIdempotencyKey[commandKey] = new CampaignRedemptionIdempotencyState(
                commandKey,
                player.UserId,
                idempotencyKey,
                requestSha256,
                response,
                now);
            return response;
        });
    }

    private CampaignCollaborationProjection? TryBuildCampaignProjectionLocked(HubUserDto user, CampaignProjection campaign)
    {
        if (!_store.GroupsById.TryGetValue(campaign.GroupId, out GroupDto? group)
            || !IsCollaborationGroup(group))
        {
            return null;
        }

        GroupMembershipDto? membership = group.Memberships.FirstOrDefault(member =>
            string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
        if (membership is null)
        {
            return null;
        }

        if (!IsAuthorizedCampaignMembershipLocked(user, campaign, group, membership.Role))
        {
            throw new InvalidDataException("Campaign membership does not have a valid collaboration authority binding.");
        }

        return BuildCampaignProjectionLocked(user, campaign, group, membership.Role);
    }

    private CampaignCollaborationProjection BuildCampaignProjectionLocked(
        HubUserDto user,
        CampaignProjection campaign,
        GroupDto group,
        string role)
    {
        string crewId = campaign.CrewIds.FirstOrDefault() ?? string.Empty;
        IReadOnlyList<CampaignRosterEntryProjection> roster = _store.CrewsById.TryGetValue(crewId, out CrewProjection? crew)
            ? crew.Members
                .Where(member => campaign.DossierIds.Contains(member.DossierId, StringComparer.OrdinalIgnoreCase))
                .Select(member => BuildRosterEntryLocked(campaign, member))
                .OrderBy(static member => member.RunnerHandle, StringComparer.OrdinalIgnoreCase)
                .ToArray()
            : [];

        return new CampaignCollaborationProjection(
            CampaignId: NormalizeRequired(campaign.CampaignId, nameof(campaign.CampaignId), 128),
            GroupId: NormalizeRequired(campaign.GroupId, nameof(campaign.GroupId), 128),
            Name: NormalizeRequired(campaign.Name, nameof(campaign.Name), MaxNameLength),
            Summary: NormalizeRequired(campaign.Summary, nameof(campaign.Summary), MaxSummaryLength),
            Visibility: NormalizeVisibility(campaign.Visibility),
            Role: MapCampaignRole(role),
            CanManage: CanManage(group, user.UserId, role),
            CrewId: NormalizeRequired(crewId, nameof(crewId), 128),
            RunIds: campaign.RunIds.Select(runId => NormalizeRequired(runId, nameof(runId), 128)).ToArray(),
            Roster: roster,
            CreatedAtUtc: campaign.CreatedAtUtc,
            UpdatedAtUtc: campaign.UpdatedAtUtc);
    }

    private CampaignRosterEntryProjection BuildRosterEntryLocked(
        CampaignProjection campaign,
        CrewAssignmentProjection assignment)
    {
        if (!_store.DossiersById.TryGetValue(assignment.DossierId, out RunnerDossierProjection? dossier))
        {
            throw new InvalidOperationException($"Campaign crew references missing dossier {assignment.DossierId}.");
        }

        ValidateDossierForProjection(dossier);
        CampaignCharacterBindingState binding = RequireCurrentBindingLocked(campaign.CampaignId, dossier.DossierId);
        long currentRevision = ResolveCurrentCharacterRevisionLocked(dossier.DossierId);
        return new CampaignRosterEntryProjection(
            DossierId: dossier.DossierId,
            AuthorityKind: binding.AuthorityKind,
            AuthoritativeCharacterId: binding.AuthoritativeCharacterId,
            RunnerHandle: dossier.RunnerHandle.Trim(),
            DisplayName: dossier.DisplayName.Trim(),
            Status: dossier.Status,
            Role: MapCampaignRole(assignment.Role),
            Revision: currentRevision,
            GmEditAuthorityGranted: string.Equals(binding.GmAuthorityRole, GmCharacterEditorAuthority, StringComparison.Ordinal),
            GmAuthorityBindingRevision: binding.BindingRevision,
            JoinedAtUtc: assignment.AddedAtUtc,
            UpdatedAtUtc: dossier.UpdatedAtUtc);
    }

    private CampaignPlayerSafeSheetProjection BuildSharedSheetLocked(
        CampaignProjection campaign,
        string dossierId,
        bool canManage)
    {
        if (!campaign.DossierIds.Contains(dossierId, StringComparer.OrdinalIgnoreCase)
            || !_store.DossiersById.TryGetValue(dossierId, out RunnerDossierProjection? dossier))
        {
            throw new KeyNotFoundException("Unknown campaign sheet.");
        }

        string role = campaign.CrewIds
            .Select(crewId => _store.CrewsById.TryGetValue(crewId, out CrewProjection? crew) ? crew : null)
            .Where(static crew => crew is not null)
            .SelectMany(static crew => crew!.Members)
            .FirstOrDefault(member => string.Equals(member.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))
            ?.Role
            ?? PlayerRole;
        CampaignCharacterBindingState binding = RequireCurrentBindingLocked(campaign.CampaignId, dossierId);
        ValidateDossierForProjection(dossier);
        return BuildSharedSheetProjection(campaign, dossier, binding, MapCampaignRole(role), canManage);
    }

    private (CampaignProjection Campaign, GroupDto Group, string Role) RequireMemberCampaignLocked(
        HubUserDto user,
        string campaignId)
    {
        string normalizedCampaignId = NormalizeRequired(campaignId, nameof(campaignId), 128);
        if (!_store.CampaignSpinesById.TryGetValue(normalizedCampaignId, out CampaignProjection? campaign)
            || !_store.GroupsById.TryGetValue(campaign.GroupId, out GroupDto? group)
            || !IsCollaborationGroup(group))
        {
            throw new KeyNotFoundException("Unknown campaign.");
        }

        GroupMembershipDto? membership = group.Memberships.FirstOrDefault(member =>
            string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
        if (membership is null)
        {
            throw new KeyNotFoundException("Unknown campaign.");
        }

        if (!IsAuthorizedCampaignMembershipLocked(user, campaign, group, membership.Role))
        {
            throw new CampaignCollaborationAccessDeniedException("Campaign membership is not authorized for collaboration data.");
        }

        return (campaign, group, membership.Role);
    }

    private (CampaignProjection Campaign, GroupDto Group, string Role) RequireManagerCampaignLocked(
        HubUserDto user,
        string campaignId)
    {
        (CampaignProjection campaign, GroupDto group, string role) = RequireMemberCampaignLocked(user, campaignId);
        if (!CanManage(group, user.UserId, role))
        {
            throw new CampaignCollaborationAccessDeniedException("GM campaign access is required.");
        }

        return (campaign, group, role);
    }

    private RunProjection RequireCampaignRunLocked(CampaignProjection campaign, string runId)
    {
        string normalizedRunId = NormalizeRequired(runId, nameof(runId), 128);
        if (!campaign.RunIds.Contains(normalizedRunId, StringComparer.OrdinalIgnoreCase)
            || !_store.RunsById.TryGetValue(normalizedRunId, out RunProjection? run)
            || !string.Equals(run.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase))
        {
            throw new KeyNotFoundException("Unknown campaign run.");
        }

        return run;
    }

    private static bool CanManage(GroupDto group, string userId, string role)
        => string.Equals(group.OwnerUserId, userId, StringComparison.OrdinalIgnoreCase)
            || role.Equals(GmRole, StringComparison.OrdinalIgnoreCase);

    private bool IsAuthorizedCampaignMembershipLocked(
        HubUserDto user,
        CampaignProjection campaign,
        GroupDto group,
        string role)
    {
        string normalizedRole = role.Trim().ToLowerInvariant();
        if (normalizedRole == OwnerRole)
        {
            return string.Equals(group.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase);
        }

        if (normalizedRole == GmRole)
        {
            return true;
        }

        if (normalizedRole != PlayerRole)
        {
            return false;
        }

        CrewAssignmentProjection? assignment = campaign.CrewIds
            .Select(crewId => _store.CrewsById.TryGetValue(crewId, out CrewProjection? crew) ? crew : null)
            .Where(crew => crew is not null
                && string.Equals(crew.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(crew.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
            .SelectMany(static crew => crew!.Members)
            .FirstOrDefault(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(member.Role, PlayerRole, StringComparison.Ordinal));
        if (assignment is null
            || !campaign.DossierIds.Contains(assignment.DossierId, StringComparer.OrdinalIgnoreCase)
            || !_store.DossiersById.TryGetValue(assignment.DossierId, out RunnerDossierProjection? dossier)
            || !string.Equals(dossier.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        CampaignCharacterBindingState? binding = _store.CampaignCharacterBindings
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.DossierId, assignment.DossierId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.BindingRevision)
            .ThenByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();
        return binding is not null
            && string.Equals(binding.AuthenticatedOwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(binding.AuthorityKind, HubRunnerDossierAuthorityKind, StringComparison.Ordinal)
            && string.Equals(binding.AuthoritativeCharacterId, dossier.DossierId, StringComparison.Ordinal);
    }

    private static bool IsCollaborationGroup(GroupDto group)
        => group.Capabilities.Contains("campaign_collaboration", StringComparer.Ordinal);

    private CampaignCharacterBindingState RequireCurrentBindingLocked(string campaignId, string dossierId)
    {
        CampaignCharacterBindingState? binding = _store.CampaignCharacterBindings
            .Where(item => string.Equals(item.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.BindingRevision)
            .ThenByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();
        if (binding is null)
        {
            throw new KeyNotFoundException("Unknown campaign sheet.");
        }

        return binding;
    }

    private long ResolveCurrentCharacterRevisionLocked(string dossierId)
        => _store.CampaignCharacterBindings
            .Where(item => string.Equals(item.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))
            .Select(static item => item.CurrentRevision)
            .DefaultIfEmpty(1)
            .Max();

    private CampaignPlayerSafeSheetProjection BuildSharedSheetProjection(
        CampaignProjection campaign,
        RunnerDossierProjection dossier,
        CampaignCharacterBindingState binding,
        string role,
        bool canManage)
        => new(
            CampaignId: campaign.CampaignId,
            DossierId: dossier.DossierId,
            RunnerHandle: NormalizeRequired(dossier.RunnerHandle, nameof(dossier.RunnerHandle), MaxHandleLength),
            DisplayName: NormalizeRequired(dossier.DisplayName, nameof(dossier.DisplayName), MaxDisplayNameLength),
            Status: NormalizeDossierStatus(dossier.Status),
            Role: role,
            CanManage: canManage,
            GmEditAuthorityGranted: string.Equals(binding.GmAuthorityRole, GmCharacterEditorAuthority, StringComparison.Ordinal),
            GmAuthorityBindingRevision: binding.BindingRevision,
            Revision: binding.CurrentRevision,
            RuleEnvironmentFingerprint: NormalizeRequired(
                dossier.RuleEnvironment.CompatibilityFingerprint,
                "ruleEnvironmentFingerprint",
                256),
            Sections: NormalizeSafeSections(dossier.Projections),
            UpdatedAtUtc: dossier.UpdatedAtUtc);

    private static CampaignCharacterBindingProjection ToBindingProjection(
        CampaignCharacterBindingState state,
        long currentRevision)
        => new(
            state.BindingId,
            state.CampaignId,
            state.DossierId,
            state.AuthorityKind,
            state.AuthoritativeCharacterId,
            state.BindingRevision,
            currentRevision,
            state.GmAuthorityRole,
            state.GrantedAtUtc);

    private static string MapCampaignRole(string role)
        => role.Trim().ToLowerInvariant() switch
        {
            OwnerRole => GmOwnerRole,
            GmRole => GmEditorRole,
            PlayerRole => PlayerRole,
            _ => throw new InvalidDataException("Campaign membership contains an unsupported collaboration role.")
        };

    private static CampaignSharedSheetEditReceipt ToEditReceipt(CampaignSharedSheetAuditState state)
        => new(
            ReceiptId: state.ReceiptId,
            CampaignId: state.CampaignId,
            DossierId: state.DossierId,
            PreviousRevision: state.PreviousRevision,
            Revision: state.Revision,
            IdempotencyKey: state.IdempotencyKey,
            Reason: state.Reason,
            EditedByUserId: state.EditedByUserId,
            BeforeSha256: state.BeforeSha256,
            AfterSha256: state.AfterSha256,
            EditedAtUtc: state.EditedAtUtc);

    private static CampaignGmAuthorityUpdateReceipt ToGmAuthorityReceipt(CampaignGmAuthorityAuditState state)
        => new(
            ReceiptId: state.ReceiptId,
            CampaignId: state.CampaignId,
            DossierId: state.DossierId,
            PreviousBindingRevision: state.PreviousBindingRevision,
            BindingRevision: state.BindingRevision,
            CurrentCharacterRevision: state.CurrentCharacterRevision,
            GmEditAuthorityGranted: state.IsGranted,
            Changed: state.Changed,
            IdempotencyKey: state.IdempotencyKey,
            Reason: state.Reason,
            ChangedAtUtc: state.ChangedAtUtc);

    private static CampaignRunsiteDraftProjection ToDraftProjection(CampaignRunsiteState state)
        => new(
            CampaignId: NormalizeRequired(state.CampaignId, nameof(state.CampaignId), 128),
            RunId: NormalizeRequired(state.RunId, nameof(state.RunId), 128),
            Revision: state.Revision,
            Title: NormalizeRequired(state.Title, nameof(state.Title), MaxNameLength),
            Summary: NormalizeRequired(state.Summary, nameof(state.Summary), MaxSummaryLength),
            PlayerSections: NormalizeRunsiteSections(state.PlayerSections),
            GmNotes: NormalizeOptional(state.GmNotes, nameof(state.GmNotes), MaxSummaryLength),
            PublishedRevision: state.Published?.Revision,
            UpdatedAtUtc: state.UpdatedAtUtc,
            PublishedAtUtc: state.Published?.PublishedAtUtc);

    private static CampaignRunsitePlayerProjection ToPlayerRunsiteProjection(CampaignRunsitePlayerProjection state)
        => new(
            CampaignId: NormalizeRequired(state.CampaignId, nameof(state.CampaignId), 128),
            RunId: NormalizeRequired(state.RunId, nameof(state.RunId), 128),
            Revision: state.Revision,
            Title: NormalizeRequired(state.Title, nameof(state.Title), MaxNameLength),
            Summary: NormalizeRequired(state.Summary, nameof(state.Summary), MaxSummaryLength),
            Sections: NormalizeRunsiteSections(state.Sections),
            PublishedAtUtc: state.PublishedAtUtc);

    private string GenerateUniqueLinkSecretLocked()
    {
        for (int attempt = 0; attempt < 8; attempt++)
        {
            string candidate = Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
            if (_store.CampaignCollaborationInvitesById.Values.All(invite => !SecretMatches(invite, "link", candidate)))
            {
                return candidate;
            }
        }

        throw new InvalidOperationException("Unable to allocate a unique campaign invite secret.");
    }

    private string GenerateUniqueShortCodeLocked()
    {
        for (int attempt = 0; attempt < 8; attempt++)
        {
            string compact = Base32Encode(RandomNumberGenerator.GetBytes(16));
            string formatted = $"CM-{string.Join('-', Enumerable.Range(0, (compact.Length + 4) / 5).Select(index => compact.Substring(index * 5, Math.Min(5, compact.Length - (index * 5)))))}";
            string normalized = NormalizeShortCode(formatted);
            if (!_store.CampaignInviteIdByCodeLookupSha256.ContainsKey(ComputeCodeLookupSha256(normalized)))
            {
                return formatted;
            }
        }

        throw new InvalidOperationException("Unable to allocate a unique campaign join code.");
    }

    private static bool SecretMatches(CampaignCollaborationInviteState invite, string kind, string secret)
    {
        string expected = string.Equals(kind, "link", StringComparison.Ordinal)
            ? invite.LinkSecretSha256
            : invite.ShortCodeSha256;
        try
        {
            byte[] expectedBytes = Convert.FromHexString(expected);
            byte[] actualBytes = Convert.FromHexString(HashSecret(kind, invite.DigestSalt, secret));
            return expectedBytes.Length == actualBytes.Length
                && CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static string HashSecret(string kind, string salt, string secret)
    {
        byte[] saltBytes = Base64UrlDecode(salt);
        byte[] kindBytes = Encoding.UTF8.GetBytes(kind);
        byte[] secretBytes = Encoding.UTF8.GetBytes(secret);
        byte[] input = new byte[kindBytes.Length + 1 + saltBytes.Length + secretBytes.Length];
        kindBytes.CopyTo(input, 0);
        input[kindBytes.Length] = 0;
        saltBytes.CopyTo(input, kindBytes.Length + 1);
        secretBytes.CopyTo(input, kindBytes.Length + 1 + saltBytes.Length);
        try
        {
            return Convert.ToHexString(SHA256.HashData(input)).ToLowerInvariant();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(secretBytes);
            CryptographicOperations.ZeroMemory(input);
        }
    }

    private static string ComputeSha256<T>(T value)
        => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value, DigestJsonOptions)))
            .ToLowerInvariant();

    private CanonicalGmCharacterEditReceipt RequireCanonicalReceipt(
        CanonicalGmCharacterEditCommand command,
        CanonicalGmCharacterEditResult? result)
    {
        if (result is null)
        {
            throw new CampaignCanonicalEditUnavailableException();
        }

        switch (result.Outcome)
        {
            case CanonicalGmCharacterEditOutcome.Denied:
            case CanonicalGmCharacterEditOutcome.Forbidden:
                throw new CampaignCollaborationAccessDeniedException(
                    "Core rejected the current GM character-edit delegation.");
            case CanonicalGmCharacterEditOutcome.Invalid:
                throw new ArgumentException(
                    "The requested GM edit is outside the canonical delegated character-edit contract.",
                    nameof(command));
            case CanonicalGmCharacterEditOutcome.Missing:
                throw new KeyNotFoundException("Unknown canonical character.");
            case CanonicalGmCharacterEditOutcome.Conflict:
                throw new CampaignCanonicalEditConflictException(result.CurrentRevision);
            case CanonicalGmCharacterEditOutcome.Corrupt:
            case CanonicalGmCharacterEditOutcome.Unavailable:
                throw new CampaignCanonicalEditUnavailableException();
            case CanonicalGmCharacterEditOutcome.Applied:
            case CanonicalGmCharacterEditOutcome.Replayed:
                break;
            default:
                throw new CampaignCanonicalEditUnavailableException();
        }

        CanonicalGmCharacterEditReceipt? receipt = result.Receipt;
        string expectedIdempotencySha256 = Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(command.IdempotencyKey)))
            .ToLowerInvariant();
        string expectedCommandSha256 = ComputeCanonicalCommandSha256(command);
        string expectedReceiptSeed = string.Join(
            "\n",
            expectedCommandSha256,
            command.DelegationId,
            command.AuthorityReceiptId,
            expectedIdempotencySha256);
        string expectedReceiptId = "gm-edit-" + ComputeCanonicalStringSha256(expectedReceiptSeed)[..24];
        CanonicalGmCharacterEditAuditOperation[] expectedOperations =
        [
            BuildExpectedCanonicalAuditOperation(DelegatedProfileAliasPath, command.RunnerHandle),
            BuildExpectedCanonicalAuditOperation(DelegatedProfileNamePath, command.DisplayName)
        ];
        DateTimeOffset observedAtUtc = _timeProvider.GetUtcNow().ToUniversalTime();
        if (receipt is null
            || !string.Equals(receipt.Contract, DelegatedGmCharacterEditContract, StringComparison.Ordinal)
            || !string.Equals(receipt.ReceiptId, expectedReceiptId, StringComparison.Ordinal)
            || !string.Equals(receipt.CampaignId, command.CampaignId, StringComparison.Ordinal)
            || !string.Equals(receipt.DelegationId, command.DelegationId, StringComparison.Ordinal)
            || !string.Equals(receipt.GrantedByCampaignOwnerId, command.CampaignOwnerUserId, StringComparison.Ordinal)
            || !string.Equals(
                receipt.GrantedByCharacterOwnerId,
                command.CharacterOwnerUserId.Trim().ToLowerInvariant(),
                StringComparison.Ordinal)
            || !string.Equals(receipt.AuthorityReceiptId, command.AuthorityReceiptId, StringComparison.Ordinal)
            || receipt.AuthorityRevision != command.AuthorityRevision
            || !string.Equals(receipt.ActorId, command.ActorUserId, StringComparison.Ordinal)
            || !string.Equals(receipt.ActorRole, DelegatedGmActorRole, StringComparison.Ordinal)
            || !string.Equals(
                receipt.CharacterOwnerId,
                command.CharacterOwnerUserId.Trim().ToLowerInvariant(),
                StringComparison.Ordinal)
            || !string.Equals(receipt.AuthoritativeCharacterId, command.AuthoritativeCharacterId, StringComparison.Ordinal)
            || !string.Equals(receipt.Reason, command.Reason, StringComparison.Ordinal)
            || !string.Equals(receipt.IdempotencyKeySha256, expectedIdempotencySha256, StringComparison.Ordinal)
            || !string.Equals(receipt.CommandSha256, expectedCommandSha256, StringComparison.Ordinal)
            || receipt.PreviousRevision != command.ExpectedRevision
            || receipt.NewRevision != command.ExpectedRevision + 1
            || result.CurrentRevision != receipt.NewRevision
            || receipt.AppliedAtUtc == default
            || receipt.AppliedAtUtc.ToUniversalTime() < command.AuthorityGrantedAtUtc.ToUniversalTime()
            || receipt.AppliedAtUtc.ToUniversalTime() > observedAtUtc.AddMinutes(5)
            || !CanonicalOperationsMatch(receipt.Operations, expectedOperations))
        {
            throw new CampaignCanonicalEditUnavailableException();
        }

        return receipt;
    }

    private static bool CanonicalOperationsMatch(
        IReadOnlyList<CanonicalGmCharacterEditAuditOperation>? actual,
        IReadOnlyList<CanonicalGmCharacterEditAuditOperation> expected)
    {
        if (actual is null || actual.Count != expected.Count)
        {
            return false;
        }

        for (int index = 0; index < expected.Count; index++)
        {
            CanonicalGmCharacterEditAuditOperation actualOperation = actual[index];
            CanonicalGmCharacterEditAuditOperation expectedOperation = expected[index];
            if (actualOperation is null
                || actualOperation.Operation != expectedOperation.Operation
                || !string.Equals(actualOperation.Path, expectedOperation.Path, StringComparison.Ordinal)
                || !string.Equals(actualOperation.ValueSha256, expectedOperation.ValueSha256, StringComparison.Ordinal)
                || actualOperation.ValueLength != expectedOperation.ValueLength)
            {
                return false;
            }
        }

        return true;
    }

    private static CanonicalGmCharacterEditAuditOperation BuildExpectedCanonicalAuditOperation(
        string path,
        string value)
        => new(
            CanonicalGmCharacterEditPatchOperationKind.Replace,
            path,
            ComputeCanonicalStringSha256(value),
            value.Length);

    private static string ComputeCanonicalCommandSha256(CanonicalGmCharacterEditCommand command)
    {
        StringBuilder builder = new();
        AppendCanonicalFingerprintField(builder, DelegatedGmCharacterEditContract);
        AppendCanonicalFingerprintField(builder, command.CampaignId);
        AppendCanonicalFingerprintField(builder, command.ActorUserId);
        AppendCanonicalFingerprintField(builder, command.CharacterOwnerUserId.Trim().ToLowerInvariant());
        AppendCanonicalFingerprintField(builder, command.AuthoritativeCharacterId);
        AppendCanonicalFingerprintField(
            builder,
            command.ExpectedRevision.ToString(CultureInfo.InvariantCulture));
        AppendCanonicalFingerprintField(builder, command.Reason);
        AppendCanonicalFingerprintField(
            builder,
            ((int)CanonicalGmCharacterEditPatchOperationKind.Replace).ToString(CultureInfo.InvariantCulture));
        AppendCanonicalFingerprintField(builder, DelegatedProfileAliasPath);
        AppendCanonicalFingerprintField(builder, command.RunnerHandle);
        AppendCanonicalFingerprintField(
            builder,
            ((int)CanonicalGmCharacterEditPatchOperationKind.Replace).ToString(CultureInfo.InvariantCulture));
        AppendCanonicalFingerprintField(builder, DelegatedProfileNamePath);
        AppendCanonicalFingerprintField(builder, command.DisplayName);
        return ComputeCanonicalStringSha256(builder.ToString());
    }

    private static void AppendCanonicalFingerprintField(StringBuilder builder, string value)
    {
        builder.Append(value.Length.ToString(CultureInfo.InvariantCulture))
            .Append(':')
            .Append(value)
            .Append('\n');
    }

    private static string ComputeCanonicalStringSha256(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))
            .ToLowerInvariant();

    private static string ComputeCodeLookupSha256(string normalizedCode)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"campaign-code\0{normalizedCode}")))
            .ToLowerInvariant();

    private static string BuildCommandKey(string userId, string commandKind, string idempotencyKey)
        => $"{userId.Trim().ToLowerInvariant()}:{commandKind}:{idempotencyKey}";

    private static string NormalizeIdempotencyKey(string? value)
    {
        string key = NormalizeRequired(value, nameof(value), MaxIdempotencyKeyLength);
        if (key.Any(static character => char.IsControl(character)))
        {
            throw new ArgumentException("idempotency key contains a control character.", nameof(value));
        }

        return key;
    }

    private void PruneInvitesLocked(DateTimeOffset now)
    {
        string[] expiredIds = _store.CampaignCollaborationInvitesById.Values
            .Where(invite => invite.ExpiresAtUtc.Add(InviteRetention) <= now
                || (invite.RevokedAtUtc is DateTimeOffset revokedAt && revokedAt.Add(InviteRetention) <= now))
            .Select(static invite => invite.InviteId)
            .ToArray();
        foreach (string inviteId in expiredIds)
        {
            if (_store.CampaignCollaborationInvitesById.Remove(inviteId, out CampaignCollaborationInviteState? removed))
            {
                _store.CampaignInviteIdByCodeLookupSha256.Remove(removed.ShortCodeLookupSha256);
            }
        }
    }

    private void EnsureInviteAttemptAllowedLocked(string userId, DateTimeOffset now)
    {
        if (!_inviteAttemptsByUserId.TryGetValue(userId, out CampaignInviteAttemptWindow? state))
        {
            return;
        }

        if (state.WindowStartedAtUtc.Add(InviteAttemptWindow) <= now)
        {
            _inviteAttemptsByUserId.Remove(userId);
            return;
        }

        if (state.Failures >= MaxInviteAttemptsPerWindow)
        {
            throw new CampaignInviteThrottledException(state.WindowStartedAtUtc.Add(InviteAttemptWindow));
        }
    }

    private void RecordInviteFailureLocked(string userId, DateTimeOffset now)
    {
        if (!_inviteAttemptsByUserId.TryGetValue(userId, out CampaignInviteAttemptWindow? state)
            || state.WindowStartedAtUtc.Add(InviteAttemptWindow) <= now)
        {
            _inviteAttemptsByUserId[userId] = new CampaignInviteAttemptWindow(now, 1);
            return;
        }

        _inviteAttemptsByUserId[userId] = state with { Failures = state.Failures + 1 };
    }

    private static void ValidateDossierForProjection(RunnerDossierProjection dossier)
    {
        try
        {
            NormalizeRequired(dossier.DossierId, nameof(dossier.DossierId), 128);
            NormalizeRequired(dossier.OwnerUserId, nameof(dossier.OwnerUserId), 128);
            NormalizeRequired(dossier.RunnerHandle, nameof(dossier.RunnerHandle), MaxHandleLength);
            NormalizeRequired(dossier.DisplayName, nameof(dossier.DisplayName), MaxDisplayNameLength);
            NormalizeDossierStatus(dossier.Status);
            NormalizeRequired(dossier.RuleEnvironment.CompatibilityFingerprint, "ruleEnvironmentFingerprint", 256);
            NormalizeSafeSections(dossier.Projections);
        }
        catch (ArgumentException exception)
        {
            throw new InvalidDataException("An authoritative campaign dossier failed validation.", exception);
        }
    }

    private static RuleEnvironmentRef BuildRuleEnvironment(string campaignId)
    {
        string fingerprint = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(campaignId)))
            .ToLowerInvariant()[..16];
        return new RuleEnvironmentRef(
            EnvironmentId: $"environment:{campaignId}",
            OwnerScope: $"campaign:{campaignId}",
            CompatibilityFingerprint: $"campaign-{fingerprint}",
            ApprovalState: "draft",
            SourcePacks: [],
            HouseRulePacks: [],
            OptionToggles: []);
    }

    private static IReadOnlyList<PublicationSafeProjection> NormalizeSafeSections(
        IReadOnlyList<PublicationSafeProjection>? sections)
    {
        sections ??= [];
        if (sections.Count > MaxSectionCount)
        {
            throw new ArgumentOutOfRangeException(nameof(sections), $"shared sheet supports at most {MaxSectionCount} sections.");
        }

        return sections
            .Select((section, index) =>
            {
                if (section is null)
                {
                    throw new ArgumentException($"sections[{index}] is required.", nameof(sections));
                }

                return new PublicationSafeProjection(
                    ProjectionId: NormalizeRequired(section.ProjectionId, $"sections[{index}].projectionId", 128),
                    Kind: NormalizeRequired(section.Kind, $"sections[{index}].kind", 64),
                    Label: NormalizeRequired(section.Label, $"sections[{index}].label", MaxNameLength),
                    Summary: NormalizeRequired(section.Summary, $"sections[{index}].summary", MaxSummaryLength),
                    ArtifactId: null,
                    Audience: "campaign",
                    OwnershipSummary: null,
                    PublicationState: "player_safe",
                    TrustBand: null,
                    Discoverable: false,
                    PublicationSummary: null,
                    CreatorPublicationId: null,
                    NextSafeAction: null,
                    ProvenanceSummary: null,
                    AuditSummary: null,
                    CompatibilitySummary: null,
                    LineageSummary: null);
            })
            .ToArray();
    }

    private static IReadOnlyList<RunsitePlayerSectionInput> NormalizeRunsiteSections(
        IReadOnlyList<RunsitePlayerSectionInput>? sections)
    {
        sections ??= [];
        if (sections.Count > MaxSectionCount)
        {
            throw new ArgumentOutOfRangeException(nameof(sections), $"runsite supports at most {MaxSectionCount} player sections.");
        }

        return sections
            .Select((section, index) =>
            {
                if (section is null)
                {
                    throw new ArgumentException($"playerSections[{index}] is required.", nameof(sections));
                }

                return new RunsitePlayerSectionInput(
                    Heading: NormalizeRequired(section.Heading, $"playerSections[{index}].heading", MaxNameLength),
                    Body: NormalizeRequired(section.Body, $"playerSections[{index}].body", MaxSummaryLength));
            })
            .ToArray();
    }

    private static string NormalizeVisibility(string? value)
        => (NormalizeOptional(value, nameof(value), 32) ?? "private").ToLowerInvariant() switch
        {
            "private" => "private",
            "group" => "group",
            _ => throw new ArgumentException("campaign visibility must be private or group.", nameof(value))
        };

    private static string NormalizeDossierStatus(string value)
        => NormalizeRequired(value, nameof(value), 32).ToLowerInvariant() switch
        {
            DossierStatuses.Draft => DossierStatuses.Draft,
            DossierStatuses.Active => DossierStatuses.Active,
            DossierStatuses.Archived => DossierStatuses.Archived,
            _ => throw new ArgumentException("sheet status must be draft, active, or archived.", nameof(value))
        };

    private static string NormalizeShortCode(string? code)
    {
        if (string.IsNullOrWhiteSpace(code) || code.Trim().Length > 64)
        {
            throw CampaignInviteRejectedException.Create();
        }

        string required = code.Trim().ToUpperInvariant();
        string compact = new(required.Where(static character => character != '-' && !char.IsWhiteSpace(character)).ToArray());
        if (!compact.StartsWith("CM", StringComparison.Ordinal)
            || compact.Length != 28
            || compact[2..].Any(character => ShortCodeAlphabet.IndexOf(character) < 0))
        {
            throw CampaignInviteRejectedException.Create();
        }

        return compact;
    }

    private static string NormalizeInviteSecret(string? secret)
    {
        if (string.IsNullOrWhiteSpace(secret) || secret.Trim().Length > 256)
        {
            throw CampaignInviteRejectedException.Create();
        }

        return secret.Trim();
    }

    private static string NormalizeRequired(string? value, string name, int maxLength)
        => NormalizeOptional(value, name, maxLength)
            ?? throw new ArgumentException($"{name} is required.", name);

    private static string? NormalizeOptional(string? value, string name, int maxLength)
    {
        string? normalized = string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        if (normalized is not null && normalized.Length > maxLength)
        {
            throw new ArgumentOutOfRangeException(name, $"{name} exceeds {maxLength} characters.");
        }

        return normalized;
    }

    private static string NewId(string prefix) => $"{prefix}-{Guid.NewGuid():N}";

    private static string RunsiteKey(string campaignId, string runId) => $"{campaignId}:{runId}";

    private static string Base64UrlEncode(byte[] bytes)
        => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    private static byte[] Base64UrlDecode(string value)
    {
        string padded = value.Replace('-', '+').Replace('_', '/');
        padded += (padded.Length % 4) switch
        {
            2 => "==",
            3 => "=",
            _ => string.Empty
        };
        return Convert.FromBase64String(padded);
    }

    private static string Base32Encode(byte[] bytes)
    {
        var builder = new StringBuilder((bytes.Length * 8 + 4) / 5);
        int buffer = 0;
        int bitsInBuffer = 0;
        foreach (byte value in bytes)
        {
            buffer = (buffer << 8) | value;
            bitsInBuffer += 8;
            while (bitsInBuffer >= 5)
            {
                bitsInBuffer -= 5;
                builder.Append(ShortCodeAlphabet[(buffer >> bitsInBuffer) & 31]);
            }
        }

        if (bitsInBuffer > 0)
        {
            builder.Append(ShortCodeAlphabet[(buffer << (5 - bitsInBuffer)) & 31]);
        }

        return builder.ToString();
    }
}

internal sealed record CampaignCollaborationInviteState(
    string InviteId,
    string CampaignId,
    string LinkSecretSha256,
    string ShortCodeSha256,
    string ShortCodeLookupSha256,
    string DigestSalt,
    string CreatedByUserId,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    int MaxUses,
    int Uses,
    DateTimeOffset? RevokedAtUtc,
    string? RevokedByUserId);

internal sealed record CampaignCharacterBindingState(
    string BindingId,
    string BindingVersionId,
    string CampaignId,
    string DossierId,
    string AuthenticatedOwnerUserId,
    string AuthorityKind,
    string AuthoritativeCharacterId,
    long BindingRevision,
    long CurrentRevision,
    string GmAuthorityRole,
    string GrantedByUserId,
    DateTimeOffset GrantedAtUtc,
    DateTimeOffset RecordedAtUtc);

internal sealed record CampaignSharedSheetAuditState(
    string ReceiptId,
    string CampaignId,
    string DossierId,
    long PreviousRevision,
    long Revision,
    string IdempotencyKey,
    string Reason,
    string EditedByUserId,
    string BeforeSha256,
    string AfterSha256,
    DateTimeOffset EditedAtUtc);

internal sealed record CampaignRedemptionIdempotencyState(
    string Key,
    string UserId,
    string IdempotencyKey,
    string RequestSha256,
    CampaignInviteRedemptionProjection Response,
    DateTimeOffset CreatedAtUtc);

internal sealed record CampaignSheetEditIdempotencyState(
    string Key,
    string UserId,
    string IdempotencyKey,
    string RequestSha256,
    CampaignSharedSheetEditReceipt Response,
    DateTimeOffset CreatedAtUtc);

internal sealed record CampaignGmAuthorityAuditState(
    string ReceiptId,
    string CampaignId,
    string DossierId,
    long PreviousBindingRevision,
    long BindingRevision,
    long CurrentCharacterRevision,
    bool WasGranted,
    bool IsGranted,
    bool Changed,
    string IdempotencyKey,
    string Reason,
    string ChangedByOwnerUserId,
    DateTimeOffset ChangedAtUtc);

internal sealed record CampaignGmAuthorityIdempotencyState(
    string Key,
    string UserId,
    string IdempotencyKey,
    string RequestSha256,
    CampaignGmAuthorityUpdateReceipt Response,
    DateTimeOffset CreatedAtUtc);

internal sealed record CampaignInviteAttemptWindow(
    DateTimeOffset WindowStartedAtUtc,
    int Failures);

internal sealed record CampaignRunsiteState(
    string CampaignId,
    string RunId,
    long Revision,
    string Title,
    string Summary,
    IReadOnlyList<RunsitePlayerSectionInput> PlayerSections,
    string? GmNotes,
    string UpdatedByUserId,
    DateTimeOffset UpdatedAtUtc,
    CampaignRunsitePlayerProjection? Published);

internal static class CampaignCollaborationStateValidator
{
    private const int MaxIdentifierLength = 128;
    private const int MaxTextLength = 4000;

    public static void ValidateSnapshot(
        IReadOnlyList<CampaignCollaborationInviteState> invites,
        IReadOnlyList<CampaignCharacterBindingState> bindings,
        IReadOnlyList<CampaignSharedSheetAuditState> audit,
        IReadOnlyList<CampaignRunsiteState> runsites,
        IReadOnlyList<CampaignRedemptionIdempotencyState> redemptions,
        IReadOnlyList<CampaignSheetEditIdempotencyState> edits,
        IReadOnlyList<CampaignGmAuthorityAuditState> gmAuthorityAudit,
        IReadOnlyList<CampaignGmAuthorityIdempotencyState> gmAuthorityCommands,
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignProjection> campaigns)
    {
        ArgumentNullException.ThrowIfNull(invites);
        ArgumentNullException.ThrowIfNull(bindings);
        Dictionary<string, RunnerDossierProjection> dossiersById = dossiers
            .ToDictionary(static item => item.DossierId, StringComparer.OrdinalIgnoreCase);
        HashSet<string> campaignIds = campaigns
            .Select(static item => item.CampaignId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var inviteIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var codeLookups = new HashSet<string>(StringComparer.Ordinal);
        foreach (CampaignCollaborationInviteState invite in invites)
        {
            Required(invite.InviteId, nameof(invite.InviteId));
            Required(invite.CampaignId, nameof(invite.CampaignId));
            Required(invite.CreatedByUserId, nameof(invite.CreatedByUserId));
            HexDigest(invite.LinkSecretSha256, nameof(invite.LinkSecretSha256));
            HexDigest(invite.ShortCodeSha256, nameof(invite.ShortCodeSha256));
            HexDigest(invite.ShortCodeLookupSha256, nameof(invite.ShortCodeLookupSha256));
            if (!inviteIds.Add(invite.InviteId) || !codeLookups.Add(invite.ShortCodeLookupSha256))
            {
                throw Invalid("campaign invites contain a duplicate id or lookup digest");
            }

            if (!campaignIds.Contains(invite.CampaignId)
                || invite.CreatedAtUtc >= invite.ExpiresAtUtc
                || invite.MaxUses is < 1 or > 100
                || invite.Uses < 0
                || invite.Uses > invite.MaxUses)
            {
                throw Invalid("campaign invite has invalid authority, lifetime, or use bounds");
            }

            try
            {
                _ = Convert.FromBase64String(PadBase64Url(invite.DigestSalt));
            }
            catch (FormatException exception)
            {
                throw Invalid("campaign invite digest salt is malformed", exception);
            }
        }

        var bindingVersionIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (CampaignCharacterBindingState binding in bindings)
        {
            Required(binding.BindingId, nameof(binding.BindingId));
            Required(binding.BindingVersionId, nameof(binding.BindingVersionId));
            Required(binding.CampaignId, nameof(binding.CampaignId));
            Required(binding.DossierId, nameof(binding.DossierId));
            Required(binding.AuthenticatedOwnerUserId, nameof(binding.AuthenticatedOwnerUserId));
            Required(binding.AuthorityKind, nameof(binding.AuthorityKind));
            Required(binding.AuthoritativeCharacterId, nameof(binding.AuthoritativeCharacterId));
            Required(binding.GrantedByUserId, nameof(binding.GrantedByUserId));
            if (!bindingVersionIds.Add(binding.BindingVersionId)
                || binding.BindingRevision < 1
                || binding.CurrentRevision < 1
                || !campaignIds.Contains(binding.CampaignId)
                || !dossiersById.TryGetValue(binding.DossierId, out RunnerDossierProjection? dossier)
                || !string.Equals(dossier.OwnerUserId, binding.AuthenticatedOwnerUserId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(binding.AuthenticatedOwnerUserId, binding.GrantedByUserId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(binding.AuthorityKind, "hub_runner_dossier", StringComparison.Ordinal)
                || !string.Equals(binding.AuthoritativeCharacterId, binding.DossierId, StringComparison.Ordinal)
                || (binding.GmAuthorityRole != "gm_character_editor" && binding.GmAuthorityRole != "none")
                || binding.RecordedAtUtc < binding.GrantedAtUtc)
            {
                throw Invalid("campaign character binding violates owner, authority, or revision invariants");
            }

            ValidateBoundDossier(dossier);
        }

        foreach (IGrouping<(string CampaignId, string DossierId), CampaignCharacterBindingState> group in bindings.GroupBy(
                     static item => (item.CampaignId.ToLowerInvariant(), item.DossierId.ToLowerInvariant())))
        {
            long[] revisions = group.Select(static item => item.BindingRevision).Order().ToArray();
            if (revisions.Distinct().Count() != revisions.Length)
            {
                throw Invalid("campaign character binding revisions are duplicated");
            }
        }

        foreach (IGrouping<string, CampaignCharacterBindingState> dossierGroup in bindings.GroupBy(
                     static item => item.DossierId,
                     StringComparer.OrdinalIgnoreCase))
        {
            long currentRevision = dossierGroup.Max(static item => item.CurrentRevision);
            bool latestBindingsAgree = dossierGroup
                .GroupBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
                .Select(group => group.OrderByDescending(static item => item.BindingRevision).First())
                .All(item => item.CurrentRevision == currentRevision);
            if (!latestBindingsAgree)
            {
                throw Invalid("current campaign character bindings disagree on canonical revision");
            }
        }

        foreach (CampaignSharedSheetAuditState item in audit)
        {
            Required(item.ReceiptId, nameof(item.ReceiptId));
            Required(item.CampaignId, nameof(item.CampaignId));
            Required(item.DossierId, nameof(item.DossierId));
            Required(item.IdempotencyKey, nameof(item.IdempotencyKey));
            Required(item.Reason, nameof(item.Reason), 512);
            Required(item.EditedByUserId, nameof(item.EditedByUserId));
            HexDigest(item.BeforeSha256, nameof(item.BeforeSha256));
            HexDigest(item.AfterSha256, nameof(item.AfterSha256));
            if (item.PreviousRevision < 1 || item.Revision != item.PreviousRevision + 1)
            {
                throw Invalid("campaign sheet audit revision is invalid");
            }
        }

        foreach (CampaignRunsiteState runsite in runsites)
        {
            Required(runsite.CampaignId, nameof(runsite.CampaignId));
            Required(runsite.RunId, nameof(runsite.RunId));
            Required(runsite.Title, nameof(runsite.Title), 160);
            Required(runsite.Summary, nameof(runsite.Summary), MaxTextLength);
            Required(runsite.UpdatedByUserId, nameof(runsite.UpdatedByUserId));
            if (runsite.GmNotes is not null)
            {
                Required(runsite.GmNotes, nameof(runsite.GmNotes), MaxTextLength);
            }

            if (!campaignIds.Contains(runsite.CampaignId) || runsite.Revision < 1 || runsite.PlayerSections.Count > 64)
            {
                throw Invalid("campaign runsite has invalid authority or bounds");
            }

            foreach (RunsitePlayerSectionInput section in runsite.PlayerSections)
            {
                Required(section.Heading, nameof(section.Heading), 160);
                Required(section.Body, nameof(section.Body), MaxTextLength);
            }

            if (runsite.Published is CampaignRunsitePlayerProjection published)
            {
                Required(published.CampaignId, nameof(published.CampaignId));
                Required(published.RunId, nameof(published.RunId));
                Required(published.Title, nameof(published.Title), 160);
                Required(published.Summary, nameof(published.Summary), MaxTextLength);
                if (!string.Equals(published.CampaignId, runsite.CampaignId, StringComparison.OrdinalIgnoreCase)
                    || !string.Equals(published.RunId, runsite.RunId, StringComparison.OrdinalIgnoreCase)
                    || published.Revision < 1
                    || published.Revision > runsite.Revision
                    || published.Sections.Count > 64)
                {
                    throw Invalid("published runsite disagrees with its private draft authority");
                }

                foreach (RunsitePlayerSectionInput section in published.Sections)
                {
                    Required(section.Heading, nameof(section.Heading), 160);
                    Required(section.Body, nameof(section.Body), MaxTextLength);
                }
            }
        }

        foreach (CampaignRedemptionIdempotencyState item in redemptions)
        {
            ValidateIdempotency(item.Key, item.UserId, item.IdempotencyKey, item.RequestSha256);
            CampaignInviteRedemptionProjection response = item.Response;
            Required(response.CampaignId, nameof(response.CampaignId));
            Required(response.DossierId, nameof(response.DossierId));
            Required(response.CrewId, nameof(response.CrewId));
            Required(response.Role, nameof(response.Role), 32);
            if (response.Role != "player"
                || !campaignIds.Contains(response.CampaignId)
                || !dossiersById.TryGetValue(response.DossierId, out RunnerDossierProjection? dossier)
                || !string.Equals(dossier.OwnerUserId, item.UserId, StringComparison.OrdinalIgnoreCase)
                || response.Binding is null
                || !string.Equals(response.Binding.CampaignId, response.CampaignId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(response.Binding.DossierId, response.DossierId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(response.Binding.AuthorityKind, "hub_runner_dossier", StringComparison.Ordinal)
                || !string.Equals(response.Binding.AuthoritativeCharacterId, response.DossierId, StringComparison.Ordinal)
                || response.Binding.BindingRevision < 1
                || response.Binding.CurrentRevision < 1)
            {
                throw Invalid("campaign redemption idempotency response violates owner or binding authority");
            }
        }

        foreach (CampaignSheetEditIdempotencyState item in edits)
        {
            ValidateIdempotency(item.Key, item.UserId, item.IdempotencyKey, item.RequestSha256);
            CampaignSharedSheetEditReceipt response = item.Response;
            Required(response.ReceiptId, nameof(response.ReceiptId));
            Required(response.CampaignId, nameof(response.CampaignId));
            Required(response.DossierId, nameof(response.DossierId));
            Required(response.IdempotencyKey, nameof(response.IdempotencyKey));
            Required(response.Reason, nameof(response.Reason), 512);
            Required(response.EditedByUserId, nameof(response.EditedByUserId));
            HexDigest(response.BeforeSha256, nameof(response.BeforeSha256));
            HexDigest(response.AfterSha256, nameof(response.AfterSha256));
            if (!string.Equals(response.IdempotencyKey, item.IdempotencyKey, StringComparison.Ordinal)
                || !string.Equals(response.EditedByUserId, item.UserId, StringComparison.OrdinalIgnoreCase)
                || response.PreviousRevision < 1
                || response.Revision != response.PreviousRevision + 1)
            {
                throw Invalid("campaign sheet edit idempotency response is inconsistent");
            }
        }

        foreach (CampaignGmAuthorityAuditState item in gmAuthorityAudit)
        {
            Required(item.ReceiptId, nameof(item.ReceiptId));
            Required(item.CampaignId, nameof(item.CampaignId));
            Required(item.DossierId, nameof(item.DossierId));
            Required(item.IdempotencyKey, nameof(item.IdempotencyKey));
            Required(item.Reason, nameof(item.Reason), 512);
            Required(item.ChangedByOwnerUserId, nameof(item.ChangedByOwnerUserId));
            if (item.PreviousBindingRevision < 1
                || item.BindingRevision < item.PreviousBindingRevision
                || item.BindingRevision > item.PreviousBindingRevision + 1
                || item.CurrentCharacterRevision < 1
                || item.Changed != (item.WasGranted != item.IsGranted)
                || !dossiersById.TryGetValue(item.DossierId, out RunnerDossierProjection? dossier)
                || !string.Equals(dossier.OwnerUserId, item.ChangedByOwnerUserId, StringComparison.OrdinalIgnoreCase))
            {
                throw Invalid("GM authority audit has invalid revision or transition semantics");
            }
        }

        foreach (CampaignGmAuthorityIdempotencyState item in gmAuthorityCommands)
        {
            ValidateIdempotency(item.Key, item.UserId, item.IdempotencyKey, item.RequestSha256);
            CampaignGmAuthorityUpdateReceipt response = item.Response;
            Required(response.ReceiptId, nameof(response.ReceiptId));
            Required(response.CampaignId, nameof(response.CampaignId));
            Required(response.DossierId, nameof(response.DossierId));
            Required(response.IdempotencyKey, nameof(response.IdempotencyKey));
            Required(response.Reason, nameof(response.Reason), 512);
            if (!string.Equals(response.IdempotencyKey, item.IdempotencyKey, StringComparison.Ordinal)
                || response.PreviousBindingRevision < 1
                || response.BindingRevision < response.PreviousBindingRevision
                || response.BindingRevision > response.PreviousBindingRevision + 1
                || response.CurrentCharacterRevision < 1
                || response.Changed != (response.BindingRevision == response.PreviousBindingRevision + 1)
                || !dossiersById.TryGetValue(response.DossierId, out RunnerDossierProjection? dossier)
                || !string.Equals(dossier.OwnerUserId, item.UserId, StringComparison.OrdinalIgnoreCase))
            {
                throw Invalid("GM authority idempotency response is inconsistent");
            }
        }
    }

    private static void ValidateIdempotency(string key, string userId, string idempotencyKey, string requestSha256)
    {
        Required(key, nameof(key), 512);
        Required(userId, nameof(userId));
        Required(idempotencyKey, nameof(idempotencyKey));
        HexDigest(requestSha256, nameof(requestSha256));
    }

    private static void ValidateBoundDossier(RunnerDossierProjection dossier)
    {
        Required(dossier.DossierId, nameof(dossier.DossierId));
        Required(dossier.OwnerUserId, nameof(dossier.OwnerUserId));
        Required(dossier.RunnerHandle, nameof(dossier.RunnerHandle), 80);
        Required(dossier.DisplayName, nameof(dossier.DisplayName), 160);
        Required(dossier.Status, nameof(dossier.Status), 32);
        Required(dossier.RuleEnvironment.CompatibilityFingerprint, "ruleEnvironmentFingerprint", 256);
        if (dossier.Status is not (DossierStatuses.Draft or DossierStatuses.Active or DossierStatuses.Archived)
            || dossier.Projections.Count > 64)
        {
            throw Invalid("bound dossier has invalid status or projection bounds");
        }

        foreach (PublicationSafeProjection projection in dossier.Projections)
        {
            Required(projection.ProjectionId, nameof(projection.ProjectionId));
            Required(projection.Kind, nameof(projection.Kind), 64);
            Required(projection.Label, nameof(projection.Label), 160);
            Required(projection.Summary, nameof(projection.Summary), MaxTextLength);
        }
    }

    private static void Required(string? value, string name, int maxLength = MaxIdentifierLength)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value.Length > maxLength
            || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
            || value.Any(static character => char.IsControl(character)))
        {
            throw Invalid($"{name} is missing or not normalized");
        }
    }

    private static void HexDigest(string? value, string name)
    {
        Required(value, name, 64);
        try
        {
            if (value!.Length != 64 || Convert.FromHexString(value).Length != 32)
            {
                throw Invalid($"{name} is not a SHA-256 digest");
            }
        }
        catch (FormatException exception)
        {
            throw Invalid($"{name} is not a SHA-256 digest", exception);
        }
    }

    private static string PadBase64Url(string value)
    {
        string padded = value.Replace('-', '+').Replace('_', '/');
        padded += (padded.Length % 4) switch { 2 => "==", 3 => "=", _ => string.Empty };
        return padded;
    }

    private static InvalidDataException Invalid(string message, Exception? inner = null)
        => new($"Invalid campaign collaboration snapshot: {message}.", inner);
}

public sealed class CampaignCollaborationAccessDeniedException : Exception
{
    public CampaignCollaborationAccessDeniedException(string message)
        : base(message)
    {
    }
}

public sealed class CampaignRevisionConflictException : Exception
{
    public CampaignRevisionConflictException(long currentRevision)
        : base($"The campaign resource changed; current revision is {currentRevision}.")
    {
        CurrentRevision = currentRevision;
    }

    public long CurrentRevision { get; }
}

public sealed class CampaignIdempotencyConflictException : Exception
{
    public CampaignIdempotencyConflictException(
        string message = "The idempotency key was already used for a different campaign command.")
        : base(message)
    {
    }
}

public sealed class CampaignBindingRevisionConflictException : Exception
{
    public CampaignBindingRevisionConflictException(long currentBindingRevision)
        : base($"The GM authority grant changed; current binding revision is {currentBindingRevision}.")
    {
        CurrentBindingRevision = currentBindingRevision;
    }

    public long CurrentBindingRevision { get; }
}

public sealed class CampaignCanonicalEditConflictException : Exception
{
    public CampaignCanonicalEditConflictException(long? currentRevision)
        : base(currentRevision is > 0
            ? $"The canonical character changed; current revision is {currentRevision}."
            : "The canonical character changed before the GM edit could be applied.")
    {
        CurrentRevision = currentRevision;
    }

    public long? CurrentRevision { get; }
}

public sealed class CampaignCanonicalEditUnavailableException : Exception
{
    public CampaignCanonicalEditUnavailableException(Exception? innerException = null)
        : base(
            "Canonical character editing is temporarily unavailable; no campaign projection was changed.",
            innerException)
    {
    }
}

public sealed class CampaignInviteThrottledException : Exception
{
    public CampaignInviteThrottledException(DateTimeOffset retryAtUtc)
        : base("Campaign invite redemption is temporarily throttled.")
    {
        RetryAtUtc = retryAtUtc;
    }

    public DateTimeOffset RetryAtUtc { get; }
}

public sealed class CampaignInviteRejectedException : Exception
{
    private CampaignInviteRejectedException()
        : base("Campaign invite is invalid or unavailable.")
    {
    }

    internal static CampaignInviteRejectedException Create() => new();
}
