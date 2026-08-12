using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Campaign.Contracts;

namespace Chummer.Run.Api.Services.Community;

public sealed class GroupService
{
    private static readonly IReadOnlySet<string> ChronicleBookKinds = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "campaign_bible", "season_chronicle", "player_recap", "adventure_booklet", "world_guide"
    };
    private static readonly IReadOnlySet<string> ChronicleAudiences = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "gm_private", "player_safe"
    };
    private static readonly IReadOnlyDictionary<string, int> ChronicleWritingCredits = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
    {
        ["gemini"] = 15,
        ["grok"] = 20,
        ["claude"] = 30
    };
    private const string DefaultCampaignProjectId = "hub";
    private static readonly TimeSpan DefaultInviteTtl = TimeSpan.FromDays(7);
    private static readonly TimeSpan MaximumInviteTtl = TimeSpan.FromDays(30);
    private static readonly IReadOnlyList<string> DefaultBoosterCapabilities =
    [
        "can_manage_members",
        "can_issue_join_codes",
        "can_issue_boost_codes",
        "can_hold_shared_entitlements",
        "can_view_private_leaderboards"
    ];

    private readonly CommunityStore _store;
    private readonly AccountService _accounts;

    public GroupService(CommunityStore store, AccountService accounts)
    {
        _store = store;
        _accounts = accounts;
    }

    public GroupDto CreateGroup(CreateGroupRequest request)
    {
        var owner = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var now = DateTimeOffset.UtcNow;
        var groupId = AccountService.NewId("grp");
        var membership = new GroupMembershipDto(
            MembershipId: AccountService.NewId("mbr"),
            GroupId: groupId,
            UserId: owner.UserId,
            Role: "owner",
            JoinedAtUtc: now);
        var group = new GroupDto(
            GroupId: groupId,
            GroupType: Limit(AccountService.NormalizeOptional(request.GroupType) ?? "booster", 32, nameof(request.GroupType)),
            Name: Limit(AccountService.NormalizeRequired(request.Name, nameof(request.Name)), 128, nameof(request.Name)),
            Visibility: NormalizeVisibility(request.Visibility),
            OwnerUserId: owner.UserId,
            Capabilities: (request.Capabilities ?? DefaultBoosterCapabilities)
                .Where(static value => !string.IsNullOrWhiteSpace(value))
                .Select(static value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            Memberships: new[] { membership },
            CreatedAtUtc: now,
            UpdatedAtUtc: now);
        lock (_store.Gate)
        {
            _store.GroupsById[group.GroupId] = group;
            _store.PersistLocked();
        }
        UpdateUserGroups(owner.UserId);
        return group;
    }

    public GroupDto EnsurePersonalBoosterGroup(HubUserDto user)
    {
        lock (_store.Gate)
        {
            var existing = _store.GroupsById.Values.FirstOrDefault(group =>
                string.Equals(group.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(group.GroupType, "booster", StringComparison.OrdinalIgnoreCase)
                && group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)));
            if (existing is not null)
            {
                return existing;
            }
        }

        return CreateGroup(new CreateGroupRequest(
            SubjectId: user.SubjectId,
            Name: $"{user.DisplayName} boosters",
            GroupType: "booster",
            Visibility: "group",
            Capabilities: DefaultBoosterCapabilities));
    }

    public GroupDto? GetGroup(string groupId)
    {
        var normalized = AccountService.NormalizeOptional(groupId);
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.GroupsById.TryGetValue(normalized, out var group) ? group : null;
        }
    }

    public IReadOnlyList<GroupDto> ListGroupsForUser(string subjectId)
    {
        var user = _accounts.EnsureUser(subjectId, subjectId);
        lock (_store.Gate)
        {
            return _store.GroupsById.Values
                .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
                .OrderBy(group => group.Name, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    public GroupDto UpdateGroup(string groupId, UpdateGroupRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        lock (_store.Gate)
        {
            if (!_store.GroupsById.TryGetValue(AccountService.NormalizeRequired(groupId, nameof(groupId)), out var group))
            {
                throw new KeyNotFoundException($"Unknown group: {groupId}");
            }

            if (!CanManageGroup(group, requester.UserId))
            {
                throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to edit the group.");
            }

            string visibility = NormalizeVisibility(request.Visibility);
            group = group with
            {
                Name = Limit(AccountService.NormalizeRequired(request.Name, nameof(request.Name)), 128, nameof(request.Name)),
                Visibility = visibility,
                UpdatedAtUtc = DateTimeOffset.UtcNow
            };
            _store.GroupsById[group.GroupId] = group;
            _store.PersistLocked();
            return group;
        }
    }

    public IReadOnlyList<JoinCodeDto> ListJoinCodes(string groupId, string subjectId)
    {
        var requester = _accounts.EnsureUser(subjectId, subjectId);
        var group = RequireGroup(groupId);
        if (!CanIssueJoinCodes(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to view join codes.");
        }

        lock (_store.Gate)
        {
            return _store.JoinCodesByValue.Values
                .Where(code => string.Equals(code.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static code => code.CreatedAtUtc)
                .ToArray();
        }
    }

    public bool CanManageGroupForSubject(string groupId, string subjectId)
    {
        var requester = _accounts.EnsureUser(subjectId, subjectId);
        var group = RequireGroup(groupId);
        return CanManageGroup(group, requester.UserId);
    }

    public IReadOnlyList<ChronicleProjectDto> ListChronicleProjects(string groupId, string subjectId)
    {
        var requester = _accounts.EnsureUser(subjectId, subjectId);
        var group = RequireGroup(groupId);
        if (!IsGroupMember(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must belong to the group.");
        }

        bool canManage = CanManageGroup(group, requester.UserId);
        lock (_store.Gate)
        {
            return _store.ChronicleProjectsById.Values
                .Where(project => string.Equals(project.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
                .Where(project => canManage || IsPlayerVisibleChronicle(project))
                .Select(project => canManage ? project : ToPlayerChronicleArtifact(project))
                .OrderByDescending(static project => project.UpdatedAtUtc)
                .ToArray();
        }
    }

    public ChronicleProjectDto CreateChronicleProject(string groupId, CreateChronicleProjectRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var group = RequireGroup(groupId);
        if (!CanManageGroup(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to create a chronicle.");
        }

        string title = Limit(AccountService.NormalizeRequired(request.Title, nameof(request.Title)), 160, nameof(request.Title));
        string sourceSummary = Limit(AccountService.NormalizeRequired(request.SourceSummary, nameof(request.SourceSummary)), 4000, nameof(request.SourceSummary));
        string bookKind = NormalizeChoice(request.BookKind, ChronicleBookKinds, nameof(request.BookKind));
        string audience = NormalizeChoice(request.Audience, ChronicleAudiences, nameof(request.Audience));
        string modelKey = NormalizeChoice(request.ModelKey, ChronicleWritingCredits.Keys, nameof(request.ModelKey));
        ValidateChronicleLength(request.TargetChapterCount, request.TargetWordsPerChapter);
        IReadOnlyList<string> roster = SnapshotRunnerRoster(
            group,
            request.IncludeRunnerRoster && request.ParticipantConsentConfirmed);
        DateTimeOffset now = DateTimeOffset.UtcNow;
        var project = new ChronicleProjectDto(
            ChronicleProjectId: AccountService.NewId("chr"),
            GroupId: group.GroupId,
            CreatedByUserId: requester.UserId,
            Title: title,
            BookKind: bookKind,
            Audience: audience,
            Status: "draft",
            SourceSummary: sourceSummary,
            ModelKey: modelKey,
            TargetChapterCount: request.TargetChapterCount,
            TargetWordsPerChapter: request.TargetWordsPerChapter,
            IncludeRunnerRoster: request.IncludeRunnerRoster,
            RunnerRoster: roster,
            IncludeCover: request.IncludeCover,
            IncludeTranslation: request.IncludeTranslation,
            IncludeAudiobook: request.IncludeAudiobook,
            ExternalProcessingConsent: request.ExternalProcessingConsent,
            ParticipantConsentConfirmed: request.ParticipantConsentConfirmed,
            RedactionReviewed: request.RedactionReviewed,
            SourceRightsConfirmed: request.SourceRightsConfirmed,
            SourcePacketVersion: 1,
            SourcePacketSha256: string.Empty,
            EstimatedCredits: EstimateChronicleCredits(request, modelKey),
            Provider: "AIWriteBook",
            OperatorRequired: true,
            UnattendedAutomationAllowed: false,
            ExternalProjectRef: null,
            ArtifactUrl: null,
            ArtifactSha256: null,
            ExportFormat: null,
            SourceApprovedAtUtc: null,
            HandoffApprovedAtUtc: null,
            OutlineApprovedAtUtc: null,
            ArtifactImportedAtUtc: null,
            PublicationApprovedAtUtc: null,
            CreatedAtUtc: now,
            UpdatedAtUtc: now)
        {
            SpoilerReviewConfirmed = request.SpoilerReviewConfirmed
        };
        string sourcePacketSha256 = ComputeSha256(BuildChronicleSourcePacket(project));
        project = project with
        {
            SourcePacketSha256 = sourcePacketSha256,
            SourcePacketRevisions = [new ChronicleSourcePacketRevisionDto(1, sourcePacketSha256, now)]
        };

        lock (_store.Gate)
        {
            _store.ChronicleProjectsById[project.ChronicleProjectId] = project;
            _store.PersistLocked();
        }

        return project;
    }

    public ChronicleProjectDto ReviseChronicleProject(
        string groupId,
        string chronicleProjectId,
        ReviseChronicleProjectRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var group = RequireGroup(groupId);
        if (!CanManageGroup(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to revise a chronicle.");
        }

        string title = Limit(AccountService.NormalizeRequired(request.Title, nameof(request.Title)), 160, nameof(request.Title));
        string sourceSummary = Limit(AccountService.NormalizeRequired(request.SourceSummary, nameof(request.SourceSummary)), 4000, nameof(request.SourceSummary));
        string bookKind = NormalizeChoice(request.BookKind, ChronicleBookKinds, nameof(request.BookKind));
        string audience = NormalizeChoice(request.Audience, ChronicleAudiences, nameof(request.Audience));
        string modelKey = NormalizeChoice(request.ModelKey, ChronicleWritingCredits.Keys, nameof(request.ModelKey));
        ValidateChronicleLength(request.TargetChapterCount, request.TargetWordsPerChapter);
        IReadOnlyList<string> roster = SnapshotRunnerRoster(
            group,
            request.IncludeRunnerRoster && request.ParticipantConsentConfirmed);

        lock (_store.Gate)
        {
            if (!_store.ChronicleProjectsById.TryGetValue(AccountService.NormalizeRequired(chronicleProjectId, nameof(chronicleProjectId)), out var project)
                || !string.Equals(project.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException($"Unknown chronicle project: {chronicleProjectId}");
            }
            if (!string.Equals(project.Status, "draft", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("only a draft chronicle can be revised.");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            int version = checked(project.SourcePacketVersion + 1);
            var revised = project with
            {
                Title = title,
                BookKind = bookKind,
                Audience = audience,
                SourceSummary = sourceSummary,
                ModelKey = modelKey,
                TargetChapterCount = request.TargetChapterCount,
                TargetWordsPerChapter = request.TargetWordsPerChapter,
                IncludeRunnerRoster = request.IncludeRunnerRoster,
                RunnerRoster = roster,
                IncludeCover = request.IncludeCover,
                IncludeTranslation = request.IncludeTranslation,
                IncludeAudiobook = request.IncludeAudiobook,
                ExternalProcessingConsent = request.ExternalProcessingConsent,
                ParticipantConsentConfirmed = request.ParticipantConsentConfirmed,
                RedactionReviewed = request.RedactionReviewed,
                SourceRightsConfirmed = request.SourceRightsConfirmed,
                SpoilerReviewConfirmed = request.SpoilerReviewConfirmed,
                SourcePacketVersion = version,
                SourcePacketSha256 = string.Empty,
                EstimatedCredits = EstimateChronicleCredits(
                    request.TargetChapterCount,
                    request.TargetWordsPerChapter,
                    modelKey,
                    request.IncludeCover,
                    request.IncludeTranslation,
                    request.IncludeAudiobook),
                UpdatedAtUtc = now
            };
            string sha256 = ComputeSha256(BuildChronicleSourcePacket(revised));
            IReadOnlyList<ChronicleSourcePacketRevisionDto> existingRevisions = project.SourcePacketRevisions ?? [];
            if (existingRevisions.Count == 0
                && project.SourcePacketVersion > 0
                && !string.IsNullOrWhiteSpace(project.SourcePacketSha256))
            {
                existingRevisions =
                [
                    new ChronicleSourcePacketRevisionDto(
                        project.SourcePacketVersion,
                        project.SourcePacketSha256,
                        project.UpdatedAtUtc)
                ];
            }
            IReadOnlyList<ChronicleSourcePacketRevisionDto> revisions = existingRevisions
                .Concat([new ChronicleSourcePacketRevisionDto(version, sha256, now)])
                .OrderBy(static revision => revision.Version)
                .ToArray();
            revised = revised with { SourcePacketSha256 = sha256, SourcePacketRevisions = revisions };
            _store.ChronicleProjectsById[project.ChronicleProjectId] = revised;
            _store.PersistLocked();
            return revised;
        }
    }

    public ChronicleProjectDto UpdateChronicleProject(
        string groupId,
        string chronicleProjectId,
        UpdateChronicleProjectRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var group = RequireGroup(groupId);
        if (!CanManageGroup(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to advance a chronicle.");
        }

        string action = AccountService.NormalizeRequired(request.Action, nameof(request.Action)).ToLowerInvariant();
        lock (_store.Gate)
        {
            if (!_store.ChronicleProjectsById.TryGetValue(AccountService.NormalizeRequired(chronicleProjectId, nameof(chronicleProjectId)), out var project)
                || !string.Equals(project.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException($"Unknown chronicle project: {chronicleProjectId}");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            ChronicleProjectDto updated = action switch
            {
                "approve_source" when string.Equals(project.Status, "draft", StringComparison.OrdinalIgnoreCase)
                    => ApproveChronicleSource(project, now),
                "approve_source" when string.Equals(project.Status, "source_approved", StringComparison.OrdinalIgnoreCase)
                    => project,
                "approve_upload" when string.Equals(project.Status, "source_approved", StringComparison.OrdinalIgnoreCase)
                    => project with { Status = "upload_approved", HandoffApprovedAtUtc = now, UploadApprovedAtUtc = now, UpdatedAtUtc = now },
                "approve_upload" when string.Equals(project.Status, "upload_approved", StringComparison.OrdinalIgnoreCase)
                    => project,
                "approve_generation" when project.Status is "upload_approved" or "handoff_ready"
                    => project with
                    {
                        Status = "generation_approved",
                        ExternalProjectRef = Limit(AccountService.NormalizeRequired(request.ExternalProjectRef ?? string.Empty, nameof(request.ExternalProjectRef)), 256, nameof(request.ExternalProjectRef)),
                        GenerationApprovedAtUtc = now,
                        UpdatedAtUtc = now
                    },
                "approve_generation" when string.Equals(project.Status, "generation_approved", StringComparison.OrdinalIgnoreCase)
                    => project,
                "approve_outline" when string.Equals(project.Status, "generation_approved", StringComparison.OrdinalIgnoreCase)
                    => project with
                    {
                        Status = "outline_approved",
                        OutlineApprovedAtUtc = now,
                        UpdatedAtUtc = now
                    },
                "approve_outline" when string.Equals(project.Status, "outline_approved", StringComparison.OrdinalIgnoreCase)
                    => project,
                "import_artifact" when string.Equals(project.Status, "outline_approved", StringComparison.OrdinalIgnoreCase)
                    => ImportChronicleArtifact(project, request, now),
                "import_artifact" when string.Equals(project.Status, "artifact_ready", StringComparison.OrdinalIgnoreCase)
                    => project,
                "approve_publication" when string.Equals(project.Status, "artifact_ready", StringComparison.OrdinalIgnoreCase)
                    => project with { Status = "publication_approved", PublicationApprovedAtUtc = now, UpdatedAtUtc = now },
                "approve_publication" when string.Equals(project.Status, "publication_approved", StringComparison.OrdinalIgnoreCase)
                    => project,
                "approve_external_send" when string.Equals(project.Status, "publication_approved", StringComparison.OrdinalIgnoreCase)
                    => project with { Status = "external_send_approved", ExternalSendApprovedAtUtc = now, UpdatedAtUtc = now },
                "approve_external_send" when string.Equals(project.Status, "external_send_approved", StringComparison.OrdinalIgnoreCase)
                    => project,
                "archive" when string.Equals(project.Status, "archived", StringComparison.OrdinalIgnoreCase)
                    => project,
                "archive" => project with { Status = "archived", UpdatedAtUtc = now },
                _ => throw new InvalidOperationException($"action '{action}' is not valid while the chronicle is {project.Status}.")
            };
            _store.ChronicleProjectsById[project.ChronicleProjectId] = updated;
            _store.PersistLocked();
            return updated;
        }
    }

    public byte[] GetChronicleSourcePacket(string groupId, string chronicleProjectId, string subjectId)
    {
        var requester = _accounts.EnsureUser(subjectId, subjectId);
        var group = RequireGroup(groupId);
        if (!CanManageGroup(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to download a source packet.");
        }

        lock (_store.Gate)
        {
            if (!_store.ChronicleProjectsById.TryGetValue(AccountService.NormalizeRequired(chronicleProjectId, nameof(chronicleProjectId)), out var project)
                || !string.Equals(project.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException($"Unknown chronicle project: {chronicleProjectId}");
            }

            if (project.Status is not ("upload_approved" or "handoff_ready" or "generation_approved" or "outline_approved" or "artifact_ready" or "publication_approved" or "external_send_approved"))
            {
                throw new InvalidOperationException("approve the source upload before downloading the packet.");
            }

            byte[] packet = BuildChronicleSourcePacket(project);
            if (!string.Equals(ComputeSha256(packet), project.SourcePacketSha256, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("the stored source-packet digest no longer matches the immutable project inputs.");
            }

            return packet;
        }
    }

    public JoinCodeDto? GetJoinCode(string code)
    {
        string? normalized = AccountService.NormalizeOptional(code)?.ToUpperInvariant();
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.JoinCodesByValue.GetValueOrDefault(normalized);
        }
    }

    public JoinCodeDto RevokeJoinCode(string groupId, string code, string subjectId)
    {
        var requester = _accounts.EnsureUser(subjectId, subjectId);
        var group = RequireGroup(groupId);
        if (!CanIssueJoinCodes(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to revoke join codes.");
        }

        string normalized = AccountService.NormalizeRequired(code, nameof(code)).ToUpperInvariant();
        lock (_store.Gate)
        {
            if (!_store.JoinCodesByValue.TryGetValue(normalized, out var joinCode)
                || !string.Equals(joinCode.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException($"Unknown join code: {normalized}");
            }

            joinCode = joinCode with { RevokedAtUtc = joinCode.RevokedAtUtc ?? DateTimeOffset.UtcNow };
            _store.JoinCodesByValue[normalized] = joinCode;
            _store.PersistLocked();
            return joinCode;
        }
    }

    public JoinCodeDto CreateJoinCode(string groupId, CreateJoinCodeRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var group = RequireGroup(groupId);
        if (!CanIssueJoinCodes(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to issue join codes.");
        }

        TimeSpan ttl = request.Ttl ?? DefaultInviteTtl;
        if (ttl < TimeSpan.FromMinutes(5) || ttl > MaximumInviteTtl)
        {
            throw new InvalidOperationException("join-code lifetime must be between five minutes and 30 days.");
        }

        int maxUses = request.MaxUses ?? 25;
        if (maxUses is < 1 or > 1000)
        {
            throw new InvalidOperationException("join-code use limit must be between one and 1,000.");
        }

        var now = DateTimeOffset.UtcNow;
        var joinCode = new JoinCodeDto(
            JoinCodeId: AccountService.NewId("jcd"),
            Code: $"JOIN-{Guid.NewGuid():N}".ToUpperInvariant(),
            GroupId: group.GroupId,
            Role: NormalizeJoinRole(request.Role),
            CreatedAtUtc: now,
            ExpiresAtUtc: now.Add(ttl),
            Uses: 0)
        {
            MaxUses = maxUses
        };
        lock (_store.Gate)
        {
            _store.JoinCodesByValue[joinCode.Code] = joinCode;
            _store.PersistLocked();
        }
        return joinCode;
    }

    public GroupDto JoinGroup(JoinGroupByCodeRequest request)
    {
        var user = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var code = AccountService.NormalizeRequired(request.Code, nameof(request.Code)).ToUpperInvariant();
        lock (_store.Gate)
        {
            if (!_store.JoinCodesByValue.TryGetValue(code, out var joinCode))
            {
                throw new KeyNotFoundException($"Unknown join code: {code}");
            }

            if (joinCode.ExpiresAtUtc is { } expiresAt && expiresAt < DateTimeOffset.UtcNow)
            {
                throw new InvalidOperationException("join code has expired.");
            }

            if (joinCode.RevokedAtUtc is not null)
            {
                throw new InvalidOperationException("join code has been revoked.");
            }

            if (joinCode.MaxUses is { } maxUses && joinCode.Uses >= maxUses)
            {
                throw new InvalidOperationException("join code has reached its use limit.");
            }

            if (!_store.GroupsById.TryGetValue(joinCode.GroupId, out var group))
            {
                throw new KeyNotFoundException($"Unknown group: {joinCode.GroupId}");
            }

            RunnerDossierProjection dossier = RequireOwnedRunnerLocked(user.UserId, request.DossierId);
            GroupMembershipDto? existingMembership = group.Memberships.FirstOrDefault(member =>
                string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
            if (existingMembership?.RunnerDossierId is not null)
            {
                return group;
            }

            DateTimeOffset joinedAt = DateTimeOffset.UtcNow;
            var runnerTicket = new RunnerTicketDto(
                RunnerTicketId: AccountService.NewId("rnt"),
                JoinCodeId: joinCode.JoinCodeId,
                GroupId: group.GroupId,
                UserId: user.UserId,
                DossierId: dossier.DossierId,
                RunnerHandle: dossier.RunnerHandle,
                Status: "consumed",
                IssuedAtUtc: joinedAt,
                ConsumedAtUtc: joinedAt);
            var membership = (existingMembership ?? new GroupMembershipDto(
                MembershipId: AccountService.NewId("mbr"),
                GroupId: group.GroupId,
                UserId: user.UserId,
                Role: joinCode.Role,
                JoinedAtUtc: joinedAt)) with
            {
                RunnerDossierId = dossier.DossierId,
                RunnerHandle = dossier.RunnerHandle,
                RunnerTicketId = runnerTicket.RunnerTicketId
            };
            var memberships = group.Memberships
                .Where(member => !string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .Append(membership)
                .OrderBy(static member => member.JoinedAtUtc)
                .ToArray();
            group = group with
            {
                Memberships = memberships,
                UpdatedAtUtc = joinedAt,
            };
            _store.GroupsById[group.GroupId] = group;
            _store.RunnerTicketsById[runnerTicket.RunnerTicketId] = runnerTicket;
            _store.JoinCodesByValue[code] = joinCode with { Uses = joinCode.Uses + 1 };
            UpdateUserGroupsLocked(user.UserId);
            _store.PersistLocked();
            return group;
        }
    }

    public IReadOnlyList<RunnerDossierProjection> ListOwnedRunners(string subjectId)
    {
        var user = _accounts.EnsureUser(subjectId, subjectId);
        lock (_store.Gate)
        {
            return _store.DossiersById.Values
                .Where(dossier => string.Equals(dossier.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(dossier.Status, DossierStatuses.Archived, StringComparison.OrdinalIgnoreCase))
                .OrderBy(static dossier => dossier.RunnerHandle, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    public RunnerDossierProjection CreateRunner(CreateRunnerRequest request)
    {
        var user = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        string handle = Limit(AccountService.NormalizeRequired(request.RunnerHandle, nameof(request.RunnerHandle)), 64, nameof(request.RunnerHandle));
        string displayName = Limit(AccountService.NormalizeOptional(request.DisplayName) ?? handle, 128, nameof(request.DisplayName));
        DateTimeOffset now = DateTimeOffset.UtcNow;
        lock (_store.Gate)
        {
            if (_store.DossiersById.Values.Any(dossier =>
                string.Equals(dossier.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(dossier.RunnerHandle, handle, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(dossier.Status, DossierStatuses.Archived, StringComparison.OrdinalIgnoreCase)))
            {
                throw new InvalidOperationException("a runner with that handle already exists.");
            }

            string dossierId = AccountService.NewId("dos");
            string snapshotId = AccountService.NewId("snap");
            var runner = new RunnerDossierProjection(
                DossierId: dossierId,
                RunnerHandle: handle,
                DisplayName: displayName,
                Status: DossierStatuses.Draft,
                OwnerUserId: user.UserId,
                CrewId: null,
                CampaignId: null,
                CurrentRunId: null,
                CurrentSceneId: null,
                RuleEnvironment: new RuleEnvironmentRef(
                    EnvironmentId: AccountService.NewId("ruleenv"),
                    OwnerScope: "person",
                    CompatibilityFingerprint: "sr6.preview.v1",
                    ApprovalState: "self_service",
                    SourcePacks: ["shadowrun-6e-core@current"],
                    HouseRulePacks: [],
                    OptionToggles: ["explain_everywhere", "campaign_continuity"]),
                LatestContinuity: new ContinuitySnapshotRef(
                    SnapshotId: snapshotId,
                    CapturedAtUtc: now,
                    Summary: "Runner created and ready for group play.",
                    RestoreState: "ready"),
                BuildReceiptIds: [],
                SnapshotIds: [snapshotId],
                Projections:
                [
                    new PublicationSafeProjection(
                        ProjectionId: AccountService.NewId("prj"),
                        Kind: "dossier_card",
                        Label: "Runner dossier",
                        Summary: "Private runner identity for group membership and live play.")
                ],
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
            _store.DossiersById[runner.DossierId] = runner;
            _store.PersistLocked();
            return runner;
        }
    }

    public BoostCodeDto CreateBoostCode(CreateBoostCodeRequest request)
    {
        var requester = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var group = RequireGroup(request.GroupId);
        if (!CanIssueBoostCodes(group, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm to issue boost codes.");
        }

        lock (_store.Gate)
        {
            var campaignId = AccountService.NormalizeOptional(request.CampaignId)
                ?? EnsureCampaignLocked(group.GroupId, AccountService.NormalizeOptional(request.ProjectId) ?? DefaultCampaignProjectId, $"{group.Name} sponsorship").CampaignId;
            var boostCode = new BoostCodeDto(
                BoostCodeId: AccountService.NewId("bcd"),
                Code: $"BOOST-{Guid.NewGuid():N}"[..14].ToUpperInvariant(),
                GroupId: group.GroupId,
                CampaignId: campaignId,
                CreatedByUserId: requester.UserId,
                Status: "active",
                CreatedAtUtc: DateTimeOffset.UtcNow,
                RedeemedAtUtc: null,
                RedeemedByUserId: null);
            _store.BoostCodesByValue[boostCode.Code] = boostCode;
            _store.PersistLocked();
            return boostCode;
        }
    }

    public BoostCodeDto RedeemBoostCode(RedeemBoostCodeRequest request)
    {
        _accounts.EnsureUser(request.SubjectId, request.SubjectId);
        var code = AccountService.NormalizeRequired(request.Code, nameof(request.Code)).ToUpperInvariant();
        lock (_store.Gate)
        {
            if (!_store.BoostCodesByValue.TryGetValue(code, out var boostCode))
            {
                throw new KeyNotFoundException($"Unknown boost code: {code}");
            }

            if (!string.Equals(boostCode.Status, "active", StringComparison.OrdinalIgnoreCase))
            {
                return boostCode;
            }

            var user = _accounts.EnsureUser(request.SubjectId, request.SubjectId);
            var redeemed = boostCode with
            {
                Status = "redeemed",
                RedeemedAtUtc = DateTimeOffset.UtcNow,
                RedeemedByUserId = user.UserId,
            };
            _store.BoostCodesByValue[code] = redeemed;
            if (_store.GroupsById.TryGetValue(redeemed.GroupId, out var group)
                && group.Memberships.All(member => !string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
            {
                var updated = group with
                {
                    Memberships = group.Memberships
                        .Concat(
                        [
                            new GroupMembershipDto(
                                MembershipId: AccountService.NewId("mbr"),
                                GroupId: group.GroupId,
                                UserId: user.UserId,
                                Role: "booster",
                                JoinedAtUtc: DateTimeOffset.UtcNow)
                        ])
                        .ToArray(),
                    UpdatedAtUtc = DateTimeOffset.UtcNow,
                };
                _store.GroupsById[group.GroupId] = updated;
                UpdateUserGroupsLocked(user.UserId);
            }

            _store.PersistLocked();

            return redeemed;
        }
    }

    public BoostCodeDto? GetBoostCode(string code)
    {
        var normalized = AccountService.NormalizeOptional(code)?.ToUpperInvariant();
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.BoostCodesByValue.TryGetValue(normalized, out var boostCode) ? boostCode : null;
        }
    }

    public BoostCampaignDto GetOrCreateCampaign(string groupId, string projectId, string title)
    {
        var group = RequireGroup(groupId);
        lock (_store.Gate)
        {
            return EnsureCampaignLocked(group.GroupId, projectId, title);
        }
    }

    public GroupDto RequireMemberGroup(string groupId, string userId)
    {
        var normalizedUserId = AccountService.NormalizeRequired(userId, nameof(userId));
        var group = RequireGroup(groupId);
        if (!IsGroupMember(group, normalizedUserId))
        {
            throw new CommunityAccessDeniedException("requester must belong to the group.");
        }

        return group;
    }

    private GroupDto RequireGroup(string groupId)
        => GetGroup(groupId) ?? throw new KeyNotFoundException($"Unknown group: {groupId}");

    private static bool IsGroupMember(GroupDto group, string userId)
        => group.Memberships.Any(member => string.Equals(member.UserId, userId, StringComparison.OrdinalIgnoreCase));

    private static bool CanIssueJoinCodes(GroupDto group, string userId)
        => HasCapability(group, "can_issue_join_codes") && CanManageGroup(group, userId);

    private static bool CanIssueBoostCodes(GroupDto group, string userId)
        => HasCapability(group, "can_issue_boost_codes") && CanManageGroup(group, userId);

    private static bool CanManageGroup(GroupDto group, string userId)
        => string.Equals(group.OwnerUserId, userId, StringComparison.OrdinalIgnoreCase)
            || group.Memberships.Any(member =>
                string.Equals(member.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && IsElevatedRole(member.Role));

    private static bool HasCapability(GroupDto group, string capability)
        => group.Capabilities.Any(existing => string.Equals(existing, capability, StringComparison.OrdinalIgnoreCase));

    private static bool IsElevatedRole(string? role)
        => string.Equals(AccountService.NormalizeOptional(role), "owner", StringComparison.OrdinalIgnoreCase)
            || string.Equals(AccountService.NormalizeOptional(role), "admin", StringComparison.OrdinalIgnoreCase)
            || string.Equals(AccountService.NormalizeOptional(role), "manager", StringComparison.OrdinalIgnoreCase)
            || string.Equals(AccountService.NormalizeOptional(role), "gm", StringComparison.OrdinalIgnoreCase);

    private static string NormalizeJoinRole(string? role)
        => (AccountService.NormalizeOptional(role) ?? "member").ToLowerInvariant() switch
        {
            "member" => "member",
            "booster" => "booster",
            _ => throw new InvalidOperationException("join codes may only grant member or booster roles.")
        };

    private RunnerDossierProjection RequireOwnedRunnerLocked(string userId, string? dossierId)
    {
        string normalized = AccountService.NormalizeRequired(dossierId ?? string.Empty, nameof(dossierId));
        if (!_store.DossiersById.TryGetValue(normalized, out var dossier)
            || !string.Equals(dossier.OwnerUserId, userId, StringComparison.OrdinalIgnoreCase)
            || string.Equals(dossier.Status, DossierStatuses.Archived, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("choose one of your available runners before joining.");
        }

        return dossier;
    }

    private static ChronicleProjectDto ApproveChronicleSource(ChronicleProjectDto project, DateTimeOffset approvedAt)
    {
        var missing = new List<string>();
        if (!project.ExternalProcessingConsent)
        {
            missing.Add("external processing consent");
        }
        if (!project.ParticipantConsentConfirmed)
        {
            missing.Add("participant consent");
        }
        if (!project.RedactionReviewed)
        {
            missing.Add("redaction review");
        }
        if (!project.SpoilerReviewConfirmed)
        {
            missing.Add("spoiler review");
        }
        if (!project.SourceRightsConfirmed)
        {
            missing.Add("source rights confirmation");
        }
        if (missing.Count > 0)
        {
            throw new InvalidOperationException($"source approval still needs: {string.Join(", ", missing)}.");
        }

        return project with
        {
            Status = "source_approved",
            SourceApprovedAtUtc = approvedAt,
            UpdatedAtUtc = approvedAt
        };
    }

    private static ChronicleProjectDto ImportChronicleArtifact(
        ChronicleProjectDto project,
        UpdateChronicleProjectRequest request,
        DateTimeOffset importedAt)
    {
        string artifactUrl = Limit(
            AccountService.NormalizeRequired(request.ArtifactUrl ?? string.Empty, nameof(request.ArtifactUrl)),
            2048,
            nameof(request.ArtifactUrl));
        if (!IsSafeArtifactUrl(artifactUrl))
        {
            throw new InvalidOperationException("artifact URL must be an HTTPS URL or a safe /artifacts/ path.");
        }

        string artifactSha256 = AccountService.NormalizeRequired(request.ArtifactSha256 ?? string.Empty, nameof(request.ArtifactSha256)).ToLowerInvariant();
        if (artifactSha256.Length != 64 || artifactSha256.Any(static value => !Uri.IsHexDigit(value)))
        {
            throw new InvalidOperationException("artifact SHA-256 must contain exactly 64 hexadecimal characters.");
        }

        string exportFormat = (AccountService.NormalizeOptional(request.ExportFormat) ?? string.Empty).ToLowerInvariant();
        if (exportFormat is not ("pdf" or "epub" or "docx"))
        {
            throw new InvalidOperationException("export format must be PDF, EPUB, or DOCX.");
        }

        return project with
        {
            Status = "artifact_ready",
            ArtifactUrl = artifactUrl,
            ArtifactSha256 = artifactSha256,
            ExportFormat = exportFormat,
            ArtifactImportedAtUtc = importedAt,
            UpdatedAtUtc = importedAt
        };
    }

    private static bool IsSafeArtifactUrl(string value)
    {
        if (value.StartsWith("/artifacts/", StringComparison.Ordinal)
            && Uri.TryCreate(value, UriKind.Relative, out _)
            && value["/artifacts/".Length..]
                .Split('/', StringSplitOptions.None)
                .All(static segment => segment.Length > 0
                    && segment is not "." and not ".."
                    && segment.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or '.')))
        {
            return true;
        }

        return Uri.TryCreate(value, UriKind.Absolute, out var uri)
            && string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && string.IsNullOrWhiteSpace(uri.UserInfo);
    }

    private static bool IsPlayerVisibleChronicle(ChronicleProjectDto project)
        => string.Equals(project.Audience, "player_safe", StringComparison.OrdinalIgnoreCase)
            && project.Status is "publication_approved" or "external_send_approved";

    private static ChronicleProjectDto ToPlayerChronicleArtifact(ChronicleProjectDto project)
        => project with
        {
            CreatedByUserId = string.Empty,
            SourceSummary = string.Empty,
            ModelKey = string.Empty,
            TargetChapterCount = 0,
            TargetWordsPerChapter = 0,
            IncludeRunnerRoster = false,
            RunnerRoster = [],
            IncludeCover = false,
            IncludeTranslation = false,
            IncludeAudiobook = false,
            ExternalProcessingConsent = false,
            ParticipantConsentConfirmed = false,
            RedactionReviewed = false,
            SourceRightsConfirmed = false,
            SpoilerReviewConfirmed = false,
            SourcePacketVersion = 0,
            SourcePacketSha256 = string.Empty,
            SourcePacketRevisions = [],
            EstimatedCredits = 0,
            Provider = string.Empty,
            OperatorRequired = false,
            UnattendedAutomationAllowed = false,
            ExternalProjectRef = null,
            SourceApprovedAtUtc = null,
            HandoffApprovedAtUtc = null,
            UploadApprovedAtUtc = null,
            GenerationApprovedAtUtc = null,
            OutlineApprovedAtUtc = null,
            ExternalSendApprovedAtUtc = null
        };

    private static void ValidateChronicleLength(int targetChapterCount, int targetWordsPerChapter)
    {
        if (targetChapterCount is < 1 or > 40)
        {
            throw new InvalidOperationException("target chapter count must be between 1 and 40.");
        }

        if (targetWordsPerChapter is < 100 or > 5000)
        {
            throw new InvalidOperationException("target words per chapter must be between 100 and 5,000.");
        }
    }

    private static IReadOnlyList<string> SnapshotRunnerRoster(GroupDto group, bool includeRunnerRoster)
        => includeRunnerRoster
            ? group.Memberships
                .Select(static member => AccountService.NormalizeOptional(member.RunnerHandle))
                .Where(static handle => handle is not null)
                .Cast<string>()
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(static handle => handle, StringComparer.OrdinalIgnoreCase)
                .ToArray()
            : [];

    private static int EstimateChronicleCredits(CreateChronicleProjectRequest request, string modelKey)
        => EstimateChronicleCredits(
            request.TargetChapterCount,
            request.TargetWordsPerChapter,
            modelKey,
            request.IncludeCover,
            request.IncludeTranslation,
            request.IncludeAudiobook);

    private static int EstimateChronicleCredits(
        int targetChapterCount,
        int targetWordsPerChapter,
        string modelKey,
        bool includeCover,
        bool includeTranslation,
        bool includeAudiobook)
    {
        int chapters = targetChapterCount;
        int total = (3 * chapters) + (ChronicleWritingCredits[modelKey] * chapters);
        if (includeCover)
        {
            total += 30;
        }
        if (includeTranslation)
        {
            total += (15 * chapters) + 30;
        }
        if (includeAudiobook)
        {
            long estimatedCharacters = (long)chapters * targetWordsPerChapter * 6;
            total += checked((int)((estimatedCharacters + 24) / 25));
        }

        return total;
    }

    private static byte[] BuildChronicleSourcePacket(ChronicleProjectDto project)
    {
        var lines = new List<string>
        {
            $"# {SingleLine(project.Title)}",
            string.Empty,
            "## Project",
            string.Empty,
            $"- Contract: chummer.chronicle.source-packet/v{project.SourcePacketVersion}",
            $"- Chronicle ID: {project.ChronicleProjectId}",
            $"- Group ID: {project.GroupId}",
            $"- Book type: {project.BookKind}",
            $"- Audience: {project.Audience}",
            $"- Created: {project.CreatedAtUtc:O}",
            string.Empty,
            "## Source brief",
            string.Empty
        };
        lines.AddRange(NormalizePacketText(project.SourceSummary)
            .Split('\n')
            .Select(static line => $"> {line}"));
        lines.AddRange(
        [
            string.Empty,
            "## Production request",
            string.Empty,
            $"- Model lane: {project.ModelKey}",
            $"- Chapters: {project.TargetChapterCount}",
            $"- Target words per chapter: {project.TargetWordsPerChapter}",
            $"- Cover: {YesNo(project.IncludeCover)}",
            $"- Translation: {YesNo(project.IncludeTranslation)}",
            $"- Audiobook: {YesNo(project.IncludeAudiobook)}",
            $"- Estimated provider credits: {project.EstimatedCredits}",
            string.Empty,
            "## Approval gates",
            string.Empty,
            $"- External processing consent: {YesNo(project.ExternalProcessingConsent)}",
            $"- Participant consent confirmed: {YesNo(project.ParticipantConsentConfirmed)}",
            $"- Redaction reviewed: {YesNo(project.RedactionReviewed)}",
            $"- Spoiler review confirmed: {YesNo(project.SpoilerReviewConfirmed)}",
            $"- Source rights confirmed: {YesNo(project.SourceRightsConfirmed)}",
            string.Empty,
            "## Runner roster"
        ]);
        if (project.IncludeRunnerRoster && project.RunnerRoster is { Count: > 0 } runnerRoster)
        {
            lines.Add(string.Empty);
            lines.AddRange(runnerRoster.Select(static handle => $"- {SingleLine(handle)}"));
        }
        else
        {
            lines.Add(string.Empty);
            lines.Add("Not included.");
        }
        lines.AddRange(
        [
            string.Empty,
            "## Handling boundaries",
            string.Empty,
            "- External processing, participant consent, source rights, redaction review, and spoiler review were approved in Chummer.",
            "- Use AIWriteBook through the account's normal operator workflow; unattended automation is not authorized.",
            "- Do not add sourcebooks, private notes, or participant data that are not in this packet.",
            "- Return a PDF, EPUB, or DOCX export to Chummer with its SHA-256 digest.",
            "- Upload, generation, outline, publication, and external-send approvals are separate Chummer decisions.",
            string.Empty
        ]);
        return Encoding.UTF8.GetBytes(string.Join('\n', lines));
    }

    private static string ComputeSha256(byte[] content)
        => Convert.ToHexString(SHA256.HashData(content)).ToLowerInvariant();

    private static string NormalizeChoice(string value, IEnumerable<string> choices, string parameterName)
    {
        string normalized = AccountService.NormalizeRequired(value, parameterName).ToLowerInvariant();
        if (!choices.Contains(normalized, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"{parameterName} must be one of: {string.Join(", ", choices)}.");
        }

        return normalized;
    }

    private static string NormalizePacketText(string value)
        => value.Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n');

    private static string SingleLine(string value)
        => NormalizePacketText(value).Replace('\n', ' ').Trim();

    private static string YesNo(bool value) => value ? "yes" : "no";

    private static string NormalizeVisibility(string? visibility)
        => (AccountService.NormalizeOptional(visibility) ?? "private").ToLowerInvariant() switch
        {
            "private" => "private",
            "group" => "group",
            "unlisted" => "unlisted",
            _ => throw new InvalidOperationException("group visibility must be private, group, or unlisted.")
        };

    private static string Limit(string value, int maxLength, string parameterName)
    {
        if (value.Length > maxLength)
        {
            throw new ArgumentException($"{parameterName} may not exceed {maxLength} characters.", parameterName);
        }

        return value;
    }

    private BoostCampaignDto EnsureCampaignLocked(string groupId, string projectId, string title)
    {
        var existing = _store.CampaignsById.Values.FirstOrDefault(campaign =>
            string.Equals(campaign.GroupId, groupId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(campaign.ProjectId, projectId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(campaign.Status, "active", StringComparison.OrdinalIgnoreCase));
        if (existing is not null)
        {
            return existing;
        }

        var created = new BoostCampaignDto(
            CampaignId: AccountService.NewId("cmp"),
            GroupId: groupId,
            ProjectId: projectId,
            Title: title,
            Status: "active",
            CreatedAtUtc: DateTimeOffset.UtcNow);
        _store.CampaignsById[created.CampaignId] = created;
        _store.PersistLocked();
        return created;
    }

    private void UpdateUserGroups(string userId)
    {
        lock (_store.Gate)
        {
            UpdateUserGroupsLocked(userId);
        }
    }

    private void UpdateUserGroupsLocked(string userId)
    {
        var groupIds = _store.GroupsById.Values
            .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, userId, StringComparison.OrdinalIgnoreCase)))
            .Select(group => group.GroupId)
            .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        _accounts.UpdateGroupMemberships(userId, groupIds);
    }
}
