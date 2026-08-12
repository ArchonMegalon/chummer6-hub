using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Privacy;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using System.Reflection;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkedWorkspaceSnapshotTests
{
    [Fact]
    public void Snapshot_upsert_and_list_roundtrip_across_two_installations_for_same_subject()
    {
        using Fixture fixture = new();
        fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");
        fixture.SeedClaimedInstall("ins-b", "user-archon", "subject-archon");

        fixture.Workspaces.UpsertForInstallation(
            fixture.RequireInstallation("ins-a"),
            new InstallLinkedWorkspaceSnapshotRecord(
                OwnerKey: string.Empty,
                WorkspaceId: "ws-1",
                RulesetId: "sr6",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: "<character><name>Switch</name></character>",
                UpdatedAtUtc: new DateTimeOffset(2026, 06, 03, 12, 0, 0, TimeSpan.Zero),
                OriginInstallationId: "ins-a",
                Name: "Switch",
                Alias: "Switch",
                Metatype: "Elf",
                BuildMethod: "Priority",
                CreatedVersion: "6",
                AppVersion: "6",
                Karma: 12,
                Nuyen: 5000,
                Created: true));

        IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord> visible = fixture.Workspaces.ListForInstallation(fixture.RequireInstallation("ins-b"));

        InstallLinkedWorkspaceSnapshotRecord snapshot = Assert.Single(visible);
        Assert.Equal("ws-1", snapshot.WorkspaceId);
        Assert.Equal("ins-a", snapshot.OriginInstallationId);
    }

    [Fact]
    public void Snapshot_list_is_isolated_across_different_subjects()
    {
        using Fixture fixture = new();
        fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");
        fixture.SeedClaimedInstall("ins-b", "user-rival", "subject-rival");

        fixture.Workspaces.UpsertForInstallation(
            fixture.RequireInstallation("ins-a"),
            new InstallLinkedWorkspaceSnapshotRecord(
                OwnerKey: string.Empty,
                WorkspaceId: "ws-1",
                RulesetId: "sr5",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: "<character />",
                UpdatedAtUtc: new DateTimeOffset(2026, 06, 03, 12, 0, 0, TimeSpan.Zero),
                OriginInstallationId: "ins-a",
                Name: "Neo",
                Alias: "Neo",
                Metatype: "Human",
                BuildMethod: "Priority",
                CreatedVersion: "5",
                AppVersion: "5",
                Karma: 0,
                Nuyen: 0,
                Created: true));

        Assert.Empty(fixture.Workspaces.ListForInstallation(fixture.RequireInstallation("ins-b")));
    }

    [Fact]
    public void Controller_upsert_and_list_require_valid_grant_and_share_snapshots_for_same_account()
    {
        using Fixture fixture = new();
        InstallationGrantDto grantA = fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");
        InstallationGrantDto grantB = fixture.SeedClaimedInstall("ins-b", "user-archon", "subject-archon");

        ActionResult<InstallLinkedWorkspaceSnapshotUpsertResponse> upsert = fixture.Controller.UpsertClaimedInstallWorkspace(
            new InstallLinkedWorkspaceSnapshotUpsertRequest(
                InstallationId: "ins-a",
                AccessToken: grantA.AccessToken,
                WorkspaceId: "ws-2",
                RulesetId: "sr4",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: "<character><alias>Archive</alias></character>",
                UpdatedAtUtc: new DateTimeOffset(2026, 06, 03, 13, 0, 0, TimeSpan.Zero),
                OriginInstallationId: "ins-a",
                Name: "Archive",
                Alias: "Archive",
                Metatype: "Ork",
                BuildMethod: "BP",
                CreatedVersion: "4",
                AppVersion: "4",
                Karma: 8,
                Nuyen: 2400,
                Created: true));

        InstallLinkedWorkspaceSnapshotUpsertResponse upsertPayload = Assert.IsType<OkObjectResult>(upsert.Result).Value as InstallLinkedWorkspaceSnapshotUpsertResponse
            ?? throw new Xunit.Sdk.XunitException("Expected upsert response payload.");
        Assert.Equal("ws-2", upsertPayload.Snapshot.WorkspaceId);

        ActionResult<InstallLinkedWorkspaceSnapshotListResponse> list = fixture.Controller.ListClaimedInstallWorkspaces(
            new DesktopInstallNativeContinuationRequest("ins-b", grantB.AccessToken));

        InstallLinkedWorkspaceSnapshotListResponse listPayload = Assert.IsType<OkObjectResult>(list.Result).Value as InstallLinkedWorkspaceSnapshotListResponse
            ?? throw new Xunit.Sdk.XunitException("Expected list response payload.");
        InstallLinkedWorkspaceSnapshotDto snapshot = Assert.Single(listPayload.Snapshots);
        Assert.Equal("ws-2", snapshot.WorkspaceId);
        Assert.Equal("Archive", snapshot.Summary.Name);
    }

    [Fact]
    public void Controller_workspace_routes_reject_unknown_grants()
    {
        using Fixture fixture = new();
        fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");

        ActionResult<InstallLinkedWorkspaceSnapshotListResponse> result = fixture.Controller.ListClaimedInstallWorkspaces(
            new DesktopInstallNativeContinuationRequest("ins-a", "expired-token"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
    }

    [Fact]
    public void Controller_workspace_upsert_rejects_missing_workspace_id()
    {
        using Fixture fixture = new();
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");

        ActionResult<InstallLinkedWorkspaceSnapshotUpsertResponse> result = fixture.Controller.UpsertClaimedInstallWorkspace(
            new InstallLinkedWorkspaceSnapshotUpsertRequest(
                InstallationId: "ins-a",
                AccessToken: grant.AccessToken,
                WorkspaceId: "",
                RulesetId: "sr5",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: "<character />",
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                OriginInstallationId: "ins-a",
                Name: "Broken",
                Alias: "Broken",
                Metatype: "Human",
                BuildMethod: "Priority",
                CreatedVersion: "5",
                AppVersion: "5",
                Karma: 0,
                Nuyen: 0,
                Created: true));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, problem.StatusCode);
    }

    [Fact]
    public void Controller_workspace_upsert_caps_request_body_size()
    {
        MethodInfo method = typeof(InstallLinkingController).GetMethod(nameof(InstallLinkingController.UpsertClaimedInstallWorkspace))
            ?? throw new InvalidOperationException("InstallLinkingController.UpsertClaimedInstallWorkspace was not found.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException("UpsertClaimedInstallWorkspace is missing RequestSizeLimitAttribute.");

        Assert.Equal(InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    [Fact]
    public void Controller_workspace_upsert_rejects_oversized_payload()
    {
        using Fixture fixture = new();
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");

        ActionResult<InstallLinkedWorkspaceSnapshotUpsertResponse> result = fixture.Controller.UpsertClaimedInstallWorkspace(
            new InstallLinkedWorkspaceSnapshotUpsertRequest(
                InstallationId: "ins-a",
                AccessToken: grant.AccessToken,
                WorkspaceId: "ws-oversized",
                RulesetId: "sr6",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: new string('x', InstallLinkedWorkspaceSnapshotService.MaxUpsertPayloadCharacters + 1),
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                OriginInstallationId: "ins-a",
                Name: "Archive",
                Alias: "Archive",
                Metatype: "Ork",
                BuildMethod: "BP",
                CreatedVersion: "4",
                AppVersion: "4",
                Karma: 8,
                Nuyen: 2400,
                Created: true));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, problem.StatusCode);
        ProblemDetails details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Contains("payload exceeds the maximum length", details.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Upsert_keeps_newer_existing_snapshot_when_older_payload_arrives()
    {
        using Fixture fixture = new();
        fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");
        ClaimedInstallationDto installation = fixture.RequireInstallation("ins-a");

        InstallLinkedWorkspaceSnapshotRecord newer = fixture.Workspaces.UpsertForInstallation(
            installation,
            new InstallLinkedWorkspaceSnapshotRecord(
                OwnerKey: string.Empty,
                WorkspaceId: "ws-fresh",
                RulesetId: "sr6",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: "<character><name>Fresh</name></character>",
                UpdatedAtUtc: new DateTimeOffset(2026, 06, 03, 15, 0, 0, TimeSpan.Zero),
                OriginInstallationId: "ins-a",
                Name: "Fresh",
                Alias: "Fresh",
                Metatype: "Elf",
                BuildMethod: "Priority",
                CreatedVersion: "6",
                AppVersion: "6",
                Karma: 15,
                Nuyen: 9000,
                Created: true));

        InstallLinkedWorkspaceSnapshotRecord result = fixture.Workspaces.UpsertForInstallation(
            installation,
            newer with
            {
                Payload = "<character><name>Older</name></character>",
                UpdatedAtUtc = new DateTimeOffset(2026, 06, 03, 14, 0, 0, TimeSpan.Zero),
                Name = "Older"
            });

        Assert.Equal(newer.UpdatedAtUtc, result.UpdatedAtUtc);
        Assert.Equal("Fresh", result.Name);
        Assert.Contains("Fresh", result.Payload, StringComparison.Ordinal);
    }

    [Fact]
    public void Snapshot_store_persists_and_reloads_records()
    {
        using Fixture fixture = new();
        fixture.SeedClaimedInstall("ins-a", "user-archon", "subject-archon");
        ClaimedInstallationDto installation = fixture.RequireInstallation("ins-a");

        _ = fixture.Workspaces.UpsertForInstallation(
            installation,
            new InstallLinkedWorkspaceSnapshotRecord(
                OwnerKey: string.Empty,
                WorkspaceId: "ws-persisted",
                RulesetId: "sr5",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: "<character><name>Persisted</name></character>",
                UpdatedAtUtc: new DateTimeOffset(2026, 06, 03, 16, 0, 0, TimeSpan.Zero),
                OriginInstallationId: "ins-a",
                Name: "Persisted",
                Alias: "Persisted",
                Metatype: "Human",
                BuildMethod: "Priority",
                CreatedVersion: "5",
                AppVersion: "5",
                Karma: 2,
                Nuyen: 500,
                Created: true));

        InstallLinkedWorkspaceSnapshotService reloaded = new(new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
        InstallLinkedWorkspaceSnapshotRecord snapshot = Assert.Single(reloaded.ListForInstallation(installation));

        Assert.Equal("ws-persisted", snapshot.WorkspaceId);
        Assert.Equal("Persisted", snapshot.Name);
    }

    [Fact]
    public void Snapshot_visibility_falls_back_to_user_id_when_subject_id_is_missing()
    {
        using Fixture fixture = new();
        fixture.SeedClaimedInstall("ins-a", "user-archon", subjectId: null);
        fixture.SeedClaimedInstall("ins-b", "user-archon", subjectId: null);

        fixture.Workspaces.UpsertForInstallation(
            fixture.RequireInstallation("ins-a"),
            new InstallLinkedWorkspaceSnapshotRecord(
                OwnerKey: string.Empty,
                WorkspaceId: "ws-user-fallback",
                RulesetId: "sr5",
                Format: "NativeXml",
                SchemaVersion: 1,
                PayloadKind: "workspace",
                Payload: "<character><name>UserFallback</name></character>",
                UpdatedAtUtc: new DateTimeOffset(2026, 06, 03, 17, 0, 0, TimeSpan.Zero),
                OriginInstallationId: "ins-a",
                Name: "UserFallback",
                Alias: "UserFallback",
                Metatype: "Human",
                BuildMethod: "Priority",
                CreatedVersion: "5",
                AppVersion: "5",
                Karma: 1,
                Nuyen: 100,
                Created: true));

        InstallLinkedWorkspaceSnapshotRecord snapshot = Assert.Single(fixture.Workspaces.ListForInstallation(fixture.RequireInstallation("ins-b")));
        Assert.Equal("ws-user-fallback", snapshot.WorkspaceId);
    }

    [Fact]
    public void Android_linked_campaign_roundtrips_create_update_list_and_invite()
    {
        using Fixture fixture = new();
        const string subjectId = "subject-gm";
        string userId = fixture.Accounts.EnsureUser(subjectId, "Game Master").UserId;
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-gm", userId, subjectId);

        ActionResult<AndroidLinkedGroupDto> createdResult = fixture.AndroidCampaigns.CreateGroup(
            new AndroidLinkedGroupCreateRequest("ins-gm", grant.AccessToken, "Vienna Shadows", "private"));
        AndroidLinkedGroupDto created = Assert.IsType<OkObjectResult>(createdResult.Result).Value as AndroidLinkedGroupDto
            ?? throw new Xunit.Sdk.XunitException("Expected linked group payload.");
        Assert.Equal("Vienna Shadows", created.Name);
        Assert.True(created.CanManage);
        Assert.Equal("owner", created.Role);
        Assert.DoesNotContain(userId, System.Text.Json.JsonSerializer.Serialize(created), StringComparison.Ordinal);

        ActionResult<AndroidLinkedGroupDto> updatedResult = fixture.AndroidCampaigns.UpdateGroup(
            created.GroupId,
            new AndroidLinkedGroupUpdateRequest("ins-gm", grant.AccessToken, "Vienna After Dark", "unlisted"));
        AndroidLinkedGroupDto updated = Assert.IsType<OkObjectResult>(updatedResult.Result).Value as AndroidLinkedGroupDto
            ?? throw new Xunit.Sdk.XunitException("Expected updated linked group payload.");
        Assert.Equal("Vienna After Dark", updated.Name);
        Assert.Equal("unlisted", updated.Visibility);

        ActionResult<AndroidLinkedGroupListResponse> listResult = fixture.AndroidCampaigns.ListGroups(
            new AndroidLinkedGrantRequest("ins-gm", grant.AccessToken));
        AndroidLinkedGroupListResponse list = Assert.IsType<OkObjectResult>(listResult.Result).Value as AndroidLinkedGroupListResponse
            ?? throw new Xunit.Sdk.XunitException("Expected linked group list payload.");
        Assert.Equal(created.GroupId, Assert.Single(list.Groups).GroupId);

        ActionResult<AndroidLinkedInviteResponse> inviteResult = fixture.AndroidCampaigns.CreateInvite(
            created.GroupId,
            new AndroidLinkedGrantRequest("ins-gm", grant.AccessToken));
        AndroidLinkedInviteResponse invite = Assert.IsType<OkObjectResult>(inviteResult.Result).Value as AndroidLinkedInviteResponse
            ?? throw new Xunit.Sdk.XunitException("Expected linked invite payload.");
        Assert.StartsWith("https://chummer.run/groups/join/", invite.InviteUrl, StringComparison.Ordinal);
        Assert.Equal("no-store, max-age=0", fixture.AndroidCampaigns.Response.Headers.CacheControl);
    }

    [Fact]
    public void Android_linked_campaign_rejects_unknown_grant()
    {
        using Fixture fixture = new();
        ActionResult<AndroidLinkedGroupListResponse> result = fixture.AndroidCampaigns.ListGroups(
            new AndroidLinkedGrantRequest("missing", "expired"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
    }

    [Fact]
    public async Task Android_linked_account_erasure_requires_exact_confirmation_and_uses_grant_subject()
    {
        using Fixture fixture = new();
        InstallationGrantDto grant = fixture.SeedClaimedInstall(
            "ins-delete",
            "user-delete",
            "subject-delete");

        ActionResult<CurrentAccountErasureResponse> rejected = await fixture.AndroidAccounts.Erase(
            new AndroidLinkedAccountErasureRequest("ins-delete", grant.AccessToken, "delete"),
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status400BadRequest, Assert.IsType<ObjectResult>(rejected.Result).StatusCode);
        Assert.Equal(0, fixture.AccountEraser.Calls);

        ActionResult<CurrentAccountErasureResponse> accepted = await fixture.AndroidAccounts.Erase(
            new AndroidLinkedAccountErasureRequest(
                "ins-delete",
                grant.AccessToken,
                AccountErasureConfirmation.RequiredPhrase),
            CancellationToken.None);
        CurrentAccountErasureResponse response = Assert.IsType<OkObjectResult>(accepted.Result).Value as CurrentAccountErasureResponse
            ?? throw new Xunit.Sdk.XunitException("Expected account erasure payload.");
        Assert.True(response.Erased);
        Assert.Equal("subject-delete", fixture.AccountEraser.SubjectId);
        Assert.Equal("no-store, max-age=0", fixture.AndroidAccounts.Response.Headers.CacheControl);
    }

    [Fact]
    public void Android_linked_chronicle_keeps_every_approval_boundary_native_and_explicit()
    {
        using Fixture fixture = new();
        const string subjectId = "subject-chronicle-gm";
        string userId = fixture.Accounts.EnsureUser(subjectId, "Chronicle GM").UserId;
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-chronicle", userId, subjectId);
        AndroidLinkedGroupDto group = Assert.IsType<OkObjectResult>(fixture.AndroidCampaigns.CreateGroup(
            new AndroidLinkedGroupCreateRequest("ins-chronicle", grant.AccessToken, "Book Club", "private")).Result).Value as AndroidLinkedGroupDto
            ?? throw new Xunit.Sdk.XunitException("Expected linked group payload.");
        AndroidLinkedChronicleDraftRequest draft = new(
            "ins-chronicle",
            grant.AccessToken,
            "Neon Vienna",
            "campaign_bible",
            "gm_private",
            "A source brief with private names removed.",
            "gemini",
            4,
            900,
            IncludeRunnerRoster: false,
            IncludeCover: true,
            IncludeTranslation: false,
            IncludeAudiobook: false,
            ExternalProcessingConsent: true,
            ParticipantConsentConfirmed: true,
            RedactionReviewed: true,
            SourceRightsConfirmed: true,
            SpoilerReviewConfirmed: true);

        AndroidLinkedChronicleDto project = Assert.IsType<OkObjectResult>(fixture.AndroidCampaigns.CreateChronicle(
            group.GroupId,
            draft).Result).Value as AndroidLinkedChronicleDto
            ?? throw new Xunit.Sdk.XunitException("Expected linked chronicle payload.");
        Assert.Equal("draft", project.Status);
        Assert.False(project.UnattendedAutomationAllowed);
        Assert.DoesNotContain(userId, System.Text.Json.JsonSerializer.Serialize(project), StringComparison.Ordinal);

        project = Advance("approve_source");
        Assert.Equal("source_approved", project.Status);
        project = Advance("approve_upload");
        Assert.Equal("upload_approved", project.Status);
        Assert.NotNull(project.UploadApprovedAtUtc);

        AndroidLinkedChroniclePacketResponse uploadHandoff = Assert.IsType<OkObjectResult>(fixture.AndroidCampaigns.DownloadChronicleHandoff(
            group.GroupId,
            project.ChronicleProjectId,
            new AndroidLinkedGrantRequest("ins-chronicle", grant.AccessToken)).Result).Value as AndroidLinkedChroniclePacketResponse
            ?? throw new Xunit.Sdk.XunitException("Expected operator handoff payload.");
        Assert.Equal("application/json", uploadHandoff.MediaType);
        Assert.EndsWith("-handoff.json", uploadHandoff.FileName, StringComparison.Ordinal);
        using (System.Text.Json.JsonDocument document = System.Text.Json.JsonDocument.Parse(
                   Convert.FromBase64String(uploadHandoff.ContentBase64)))
        {
            Assert.False(document.RootElement.GetProperty("creditApproval").GetProperty("approved").GetBoolean());
            Assert.True(document.RootElement.GetProperty("authorizedActions").GetProperty("sourceUpload").GetBoolean());
        }
        project = Advance("approve_generation", externalProjectRef: "aiwritebook-project-42");
        Assert.Equal("generation_approved", project.Status);
        Assert.NotNull(project.GenerationApprovedAtUtc);
        Assert.NotNull(project.UploadApprovedAtUtc);

        AndroidLinkedChroniclePacketResponse packet = Assert.IsType<OkObjectResult>(fixture.AndroidCampaigns.DownloadChroniclePacket(
            group.GroupId,
            project.ChronicleProjectId,
            new AndroidLinkedGrantRequest("ins-chronicle", grant.AccessToken)).Result).Value as AndroidLinkedChroniclePacketResponse
            ?? throw new Xunit.Sdk.XunitException("Expected source packet payload.");
        Assert.Equal(project.SourcePacketSha256, packet.Sha256);
        Assert.Contains("# Neon Vienna", System.Text.Encoding.UTF8.GetString(Convert.FromBase64String(packet.ContentBase64)), StringComparison.Ordinal);

        project = Advance("approve_outline");
        Assert.Equal("outline_approved", project.Status);
        project = Advance(
            "import_artifact",
            artifactUrl: "https://chummer.run/artifacts/neon-vienna.pdf",
            artifactSha256: new string('a', 64),
            exportFormat: "pdf");
        Assert.Equal("artifact_ready", project.Status);
        project = Advance("approve_publication");
        Assert.Equal("publication_approved", project.Status);
        project = Advance("approve_external_send");
        Assert.Equal("external_send_approved", project.Status);
        Assert.NotNull(project.ExternalSendApprovedAtUtc);

        AndroidLinkedChronicleDto Advance(
            string action,
            string? externalProjectRef = null,
            string? artifactUrl = null,
            string? artifactSha256 = null,
            string? exportFormat = null)
            => Assert.IsType<OkObjectResult>(fixture.AndroidCampaigns.AdvanceChronicle(
                group.GroupId,
                project.ChronicleProjectId,
                new AndroidLinkedChronicleActionRequest(
                    "ins-chronicle",
                    grant.AccessToken,
                    action,
                    externalProjectRef,
                    artifactUrl,
                    artifactSha256,
                    exportFormat)).Result).Value as AndroidLinkedChronicleDto
                ?? throw new Xunit.Sdk.XunitException("Expected advanced chronicle payload.");
    }

    [Fact]
    public void Android_linked_player_receives_only_publication_approved_artifact_metadata()
    {
        using Fixture fixture = new();
        const string gmSubject = "subject-chronicle-manager";
        const string playerSubject = "subject-chronicle-player";
        fixture.Accounts.EnsureUser(gmSubject, "Chronicle Manager");
        HubUserDto player = fixture.Accounts.EnsureUser(playerSubject, "Chronicle Player");
        InstallationGrantDto playerGrant = fixture.SeedClaimedInstall("ins-chronicle-player", player.UserId, playerSubject);

        GroupDto group = fixture.Groups.CreateGroup(new CreateGroupRequest(gmSubject, "Artifact Readers", "campaign", "private"));
        JoinCodeDto invite = fixture.Groups.CreateJoinCode(group.GroupId, new CreateJoinCodeRequest(gmSubject));
        var runner = fixture.Groups.CreateRunner(new CreateRunnerRequest(playerSubject, "Quiet Signal", "Quiet Signal"));
        fixture.Groups.JoinGroup(new JoinGroupByCodeRequest(playerSubject, invite.Code, runner.DossierId));

        ChronicleProjectDto project = fixture.Groups.CreateChronicleProject(
            group.GroupId,
            new CreateChronicleProjectRequest(
                gmSubject,
                "Player-safe field report",
                "player_recap",
                "player_safe",
                "Private source brief that must never reach the player response.",
                "claude",
                3,
                800,
                IncludeRunnerRoster: true,
                IncludeCover: true,
                IncludeTranslation: false,
                IncludeAudiobook: false,
                ExternalProcessingConsent: true,
                ParticipantConsentConfirmed: true,
                RedactionReviewed: true,
                SourceRightsConfirmed: true,
                SpoilerReviewConfirmed: true));
        project = fixture.Groups.UpdateChronicleProject(group.GroupId, project.ChronicleProjectId, new(gmSubject, "approve_source"));
        project = fixture.Groups.UpdateChronicleProject(group.GroupId, project.ChronicleProjectId, new(gmSubject, "approve_upload"));
        project = fixture.Groups.UpdateChronicleProject(group.GroupId, project.ChronicleProjectId, new(gmSubject, "approve_generation", "private-provider-ref"));
        project = fixture.Groups.UpdateChronicleProject(group.GroupId, project.ChronicleProjectId, new(gmSubject, "approve_outline"));
        project = fixture.Groups.UpdateChronicleProject(group.GroupId, project.ChronicleProjectId, new(
            gmSubject,
            "import_artifact",
            ArtifactUrl: "/artifacts/player-field-report.epub",
            ArtifactSha256: new string('c', 64),
            ExportFormat: "epub"));

        AndroidLinkedChronicleListResponse beforePublication = Assert.IsType<OkObjectResult>(fixture.AndroidCampaigns.ListChronicles(
            group.GroupId,
            new AndroidLinkedGrantRequest("ins-chronicle-player", playerGrant.AccessToken)).Result).Value as AndroidLinkedChronicleListResponse
            ?? throw new Xunit.Sdk.XunitException("Expected player chronicle list.");
        Assert.Empty(beforePublication.Projects);
        project = fixture.Groups.UpdateChronicleProject(
            group.GroupId,
            project.ChronicleProjectId,
            new(gmSubject, "approve_publication"));

        AndroidLinkedChronicleListResponse response = Assert.IsType<OkObjectResult>(fixture.AndroidCampaigns.ListChronicles(
            group.GroupId,
            new AndroidLinkedGrantRequest("ins-chronicle-player", playerGrant.AccessToken)).Result).Value as AndroidLinkedChronicleListResponse
            ?? throw new Xunit.Sdk.XunitException("Expected player chronicle list.");
        AndroidLinkedChronicleDto visible = Assert.Single(response.Projects);
        Assert.Equal(project.ChronicleProjectId, visible.ChronicleProjectId);
        Assert.Equal("Player-safe field report", visible.Title);
        Assert.Equal("/artifacts/player-field-report.epub", visible.ArtifactUrl);
        Assert.Equal(new string('c', 64), visible.ArtifactSha256);
        Assert.Equal("epub", visible.ExportFormat);
        Assert.Empty(visible.SourceSummary);
        Assert.Empty(visible.ModelKey);
        Assert.Empty(visible.RunnerRoster);
        Assert.Empty(visible.SourcePacketSha256);
        Assert.Empty(visible.Provider);
        Assert.Null(visible.ExternalProjectRef);
        Assert.Equal(0, visible.EstimatedCredits);

        ObjectResult packetDenied = Assert.IsType<ObjectResult>(fixture.AndroidCampaigns.DownloadChroniclePacket(
            group.GroupId,
            project.ChronicleProjectId,
            new AndroidLinkedGrantRequest("ins-chronicle-player", playerGrant.AccessToken)).Result);
        Assert.Equal(StatusCodes.Status403Forbidden, packetDenied.StatusCode);
    }

    private sealed class RecordingAccountEraser : IAccountErasureService
    {
        public int Calls { get; private set; }
        public string? SubjectId { get; private set; }

        public Task<CurrentAccountErasureResponse> EraseAsync(
            string subjectId,
            CancellationToken cancellationToken)
        {
            Calls++;
            SubjectId = subjectId;
            return Task.FromResult(new CurrentAccountErasureResponse(
                true,
                new string('a', 64),
                new string('b', 64),
                [],
                DateTimeOffset.UtcNow,
                new string('c', 64)));
        }
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-install-linked-workspace-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            string downloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(downloadsRoot);
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                """
                {
                  "version": "6.0.1-preview",
                  "channel": "preview",
                  "publishedAt": "2026-04-15T08:00:00Z",
                  "downloads": []
                }
                """);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json"),
                    ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = Path.Combine(_root, "install-linked-workspaces.json"),
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                    ["CHUMMER_DOWNLOADS_ROOT"] = downloadsRoot
                })
                .Build();

            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            InstallStore = new InstallLinkingStore(
                Configuration,
                dataProtection,
                NullLogger<InstallLinkingStore>.Instance);
            InstallLinking = new InstallLinkingService(InstallStore, Configuration);
            Workspaces = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(Configuration));
            Community = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Community);
            Groups = new GroupService(Community, Accounts);
            Controller = new InstallLinkingController(
                identity: new HubIdentityClient(new HttpClient(), Configuration),
                accounts: Accounts,
                installLinking: InstallLinking,
                desktopLaunchTickets: new AccountDesktopLaunchTicketService(dataProtection, Configuration),
                releases: new PublicReleaseManifestService(Configuration),
                supportCases: null!,
                supportPresentation: new SupportCasePresentationService(),
                configuration: Configuration,
                workspaceSnapshots: Workspaces);
            AndroidCampaigns = new AndroidLinkedCampaignController(InstallLinking, Groups)
            {
                ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() }
            };
            AccountEraser = new RecordingAccountEraser();
            AndroidAccounts = new AndroidLinkedAccountController(InstallLinking, AccountEraser)
            {
                ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() }
            };
        }

        public IConfiguration Configuration { get; }

        public InstallLinkingStore InstallStore { get; }

        public InstallLinkingService InstallLinking { get; }

        public InstallLinkedWorkspaceSnapshotService Workspaces { get; }

        public CommunityStore Community { get; }

        public AccountService Accounts { get; }

        public GroupService Groups { get; }

        public InstallLinkingController Controller { get; }

        public AndroidLinkedCampaignController AndroidCampaigns { get; }

        public RecordingAccountEraser AccountEraser { get; }

        public AndroidLinkedAccountController AndroidAccounts { get; }

        public InstallationGrantDto SeedClaimedInstall(string installationId, string userId, string? subjectId)
        {
            lock (InstallStore.Gate)
            {
                ClaimedInstallationDto installation = new(
                    InstallationId: installationId,
                    ArtifactId: "avalonia-win-x64-installer",
                    Channel: "preview",
                    Version: "6.0.1-preview",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-10),
                    UpdatedAtUtc: DateTimeOffset.UtcNow,
                    UserId: userId,
                    SubjectId: subjectId,
                    PublicKey: "public-key",
                    ClaimTicketId: $"ticket-{installationId}",
                    HeadId: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    HostLabel: "Windows Workstation",
                    GrantId: $"grant-{installationId}");
                InstallationGrantDto grant = new(
                    GrantId: $"grant-{installationId}",
                    InstallationId: installationId,
                    Status: InstallationGrantStates.Active,
                    AccessToken: $"token-{installationId}",
                    IssuedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
                    ExpiresAtUtc: DateTimeOffset.UtcNow.AddDays(7),
                    UserId: userId,
                    SubjectId: subjectId);

                InstallStore.InstallationsById[installationId] = installation;
                InstallStore.GrantsById[grant.GrantId] = grant;
                InstallStore.PersistLocked();
                return grant;
            }
        }

        public ClaimedInstallationDto RequireInstallation(string installationId)
            => InstallStore.InstallationsById[installationId];

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
