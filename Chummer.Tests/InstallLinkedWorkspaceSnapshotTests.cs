using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
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
                    ["CHUMMER_DOWNLOADS_ROOT"] = downloadsRoot
                })
                .Build();

            InstallStore = new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinking = new InstallLinkingService(InstallStore, Configuration);
            Workspaces = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(Configuration));
            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            Controller = new InstallLinkingController(
                identity: new HubIdentityClient(new HttpClient(), Configuration),
                accounts: new AccountService(new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance)),
                installLinking: InstallLinking,
                desktopLaunchTickets: new AccountDesktopLaunchTicketService(dataProtection, Configuration),
                releases: new PublicReleaseManifestService(Configuration),
                supportCases: null!,
                supportPresentation: new SupportCasePresentationService(),
                configuration: Configuration,
                workspaceSnapshots: Workspaces);
        }

        public IConfiguration Configuration { get; }

        public InstallLinkingStore InstallStore { get; }

        public InstallLinkingService InstallLinking { get; }

        public InstallLinkedWorkspaceSnapshotService Workspaces { get; }

        public InstallLinkingController Controller { get; }

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
