using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ChronicleStudioTests
{
    [Fact]
    public void Gm_can_run_versioned_operator_handoff_and_persist_artifact_provenance()
    {
        using var fixture = ChronicleFixture.Create();
        ChronicleProjectDto created = fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest(
                "subject.gm",
                audience: "gm_private",
                model: "claude",
                chapters: 4,
                wordsPerChapter: 1000,
                includeRoster: true,
                includeCover: true,
                includeTranslation: true,
                includeAudiobook: true));

        Assert.Equal("draft", created.Status);
        Assert.Equal(1212, created.EstimatedCredits);
        Assert.Equal(64, created.SourcePacketSha256.Length);
        ChronicleSourcePacketRevisionDto initialRevision = Assert.Single(created.SourcePacketRevisions);
        Assert.Equal(1, initialRevision.Version);
        Assert.Equal(created.SourcePacketSha256, initialRevision.Sha256);
        Assert.True(created.OperatorRequired);
        Assert.False(created.UnattendedAutomationAllowed);
        Assert.Contains("Switchback", created.RunnerRoster);
        Assert.Throws<InvalidOperationException>(() =>
            fixture.Groups.GetChronicleSourcePacket(fixture.Group.GroupId, created.ChronicleProjectId, "subject.gm"));
        Assert.Throws<InvalidOperationException>(() =>
            fixture.Groups.GetChronicleOperatorHandoff(fixture.Group.GroupId, created.ChronicleProjectId, "subject.gm"));

        ChronicleProjectDto sourceApproved = fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_source"));
        Assert.Equal("source_approved", sourceApproved.Status);
        ChronicleProjectDto uploadApproved = fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_upload"));
        Assert.Equal("upload_approved", uploadApproved.Status);
        Assert.NotNull(uploadApproved.UploadApprovedAtUtc);

        byte[] uploadHandoff = fixture.Groups.GetChronicleOperatorHandoff(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            "subject.gm");
        Assert.Equal(
            uploadHandoff,
            fixture.Groups.GetChronicleOperatorHandoff(
                fixture.Group.GroupId,
                created.ChronicleProjectId,
                "subject.gm"));
        using (JsonDocument document = JsonDocument.Parse(uploadHandoff))
        {
            JsonElement handoff = document.RootElement;
            Assert.Equal("chummer.chronicle.operator-handoff", handoff.GetProperty("contract").GetString());
            Assert.Equal(1, handoff.GetProperty("contractVersion").GetInt32());
            Assert.Equal(created.SourcePacketSha256, handoff.GetProperty("sourcePacketSha256").GetString());
            Assert.True(handoff.GetProperty("authorizedActions").GetProperty("providerProjectCreation").GetBoolean());
            Assert.True(handoff.GetProperty("authorizedActions").GetProperty("sourceUpload").GetBoolean());
            Assert.False(handoff.GetProperty("authorizedActions").GetProperty("generation").GetBoolean());
            Assert.False(handoff.GetProperty("creditApproval").GetProperty("approved").GetBoolean());
            Assert.Equal(0, handoff.GetProperty("creditApproval").GetProperty("maximumCredits").GetInt32());
        }
        string uploadHandoffText = Encoding.UTF8.GetString(uploadHandoff);
        Assert.DoesNotContain(created.SourceSummary, uploadHandoffText, StringComparison.Ordinal);
        Assert.DoesNotContain("Switchback", uploadHandoffText, StringComparison.Ordinal);
        Assert.Contains("separate_authenticated_download", uploadHandoffText, StringComparison.Ordinal);
        Assert.Contains("unattended_automation", uploadHandoffText, StringComparison.Ordinal);

        ChronicleProjectDto generationApproved = fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_generation", ExternalProjectRef: "aiwb-project-42"));
        Assert.Equal("generation_approved", generationApproved.Status);
        Assert.NotNull(generationApproved.GenerationApprovedAtUtc);
        Assert.Equal(uploadApproved.UploadApprovedAtUtc, generationApproved.UploadApprovedAtUtc);
        using (JsonDocument document = JsonDocument.Parse(fixture.Groups.GetChronicleOperatorHandoff(
                   fixture.Group.GroupId,
                   created.ChronicleProjectId,
                   "subject.gm")))
        {
            JsonElement handoff = document.RootElement;
            Assert.True(handoff.GetProperty("authorizedActions").GetProperty("generation").GetBoolean());
            Assert.True(handoff.GetProperty("creditApproval").GetProperty("approved").GetBoolean());
            Assert.Equal(created.EstimatedCredits, handoff.GetProperty("creditApproval").GetProperty("maximumCredits").GetInt32());
            Assert.Equal("aiwb-project-42", handoff.GetProperty("externalProjectRef").GetString());
            Assert.False(handoff.GetProperty("authorizedActions").GetProperty("publication").GetBoolean());
            Assert.False(handoff.GetProperty("authorizedActions").GetProperty("externalSend").GetBoolean());
        }

        byte[] firstPacket = fixture.Groups.GetChronicleSourcePacket(fixture.Group.GroupId, created.ChronicleProjectId, "subject.gm");
        byte[] secondPacket = fixture.Groups.GetChronicleSourcePacket(fixture.Group.GroupId, created.ChronicleProjectId, "subject.gm");
        Assert.Equal(firstPacket, secondPacket);
        Assert.Equal(created.SourcePacketSha256, Convert.ToHexString(SHA256.HashData(firstPacket)).ToLowerInvariant());
        string packetText = Encoding.UTF8.GetString(firstPacket);
        Assert.Contains("Switchback", packetText);
        Assert.Contains("External processing consent: yes", packetText);
        Assert.Contains("Redaction reviewed: yes", packetText);
        Assert.Contains("Spoiler review confirmed: yes", packetText);
        Assert.Contains("unattended automation is not authorized", packetText);
        Assert.DoesNotContain(fixture.Player.UserId, packetText);

        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_publication")));
        ChronicleProjectDto outlineApproved = fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_outline"));
        Assert.Equal("outline_approved", outlineApproved.Status);

        const string artifactDigest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        ChronicleProjectDto artifactReady = fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest(
                "subject.gm",
                "import_artifact",
                ArtifactUrl: "https://downloads.example.test/chronicle.epub",
                ArtifactSha256: artifactDigest,
                ExportFormat: "epub"));
        Assert.Equal("artifact_ready", artifactReady.Status);
        Assert.Equal(artifactDigest, artifactReady.ArtifactSha256);
        Assert.Equal("epub", artifactReady.ExportFormat);
        ChronicleProjectDto publicationApproved = fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_publication"));
        Assert.Equal("publication_approved", publicationApproved.Status);
        ChronicleProjectDto externalSendApproved = fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_external_send"));
        Assert.Equal("external_send_approved", externalSendApproved.Status);
        Assert.NotNull(externalSendApproved.ExternalSendApprovedAtUtc);

        CommunityStore reloaded = new(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        ChronicleProjectDto persisted = reloaded.ChronicleProjectsById[created.ChronicleProjectId];
        Assert.Equal("external_send_approved", persisted.Status);
        Assert.Equal(artifactDigest, persisted.ArtifactSha256);
    }

    [Fact]
    public void Gm_can_revise_a_draft_with_durable_digest_history_before_approval()
    {
        using var fixture = ChronicleFixture.Create();
        ChronicleProjectDto created = fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest("subject.gm", includeRoster: true) with { ParticipantConsentConfirmed = false });
        Assert.Empty(created.RunnerRoster);

        ChronicleProjectDto revised = fixture.Groups.ReviseChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            ValidRevisionRequest(
                "subject.gm",
                title: "Vienna After Midnight — Revised",
                sourceSummary: "A player-approved account with the private fixer redacted.",
                model: "grok",
                chapters: 5,
                wordsPerChapter: 900,
                includeRoster: true,
                includeCover: true));

        Assert.Equal(2, revised.SourcePacketVersion);
        Assert.Equal("Vienna After Midnight — Revised", revised.Title);
        Assert.Equal("grok", revised.ModelKey);
        Assert.True(revised.ParticipantConsentConfirmed);
        Assert.Contains("Switchback", revised.RunnerRoster);
        Assert.NotEqual(created.SourcePacketSha256, revised.SourcePacketSha256);
        Assert.Collection(
            revised.SourcePacketRevisions,
            revision =>
            {
                Assert.Equal(1, revision.Version);
                Assert.Equal(created.SourcePacketSha256, revision.Sha256);
            },
            revision =>
            {
                Assert.Equal(2, revision.Version);
                Assert.Equal(revised.SourcePacketSha256, revision.Sha256);
            });

        fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            revised.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_source"));
        fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            revised.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_upload"));
        string packet = Encoding.UTF8.GetString(fixture.Groups.GetChronicleSourcePacket(
            fixture.Group.GroupId,
            revised.ChronicleProjectId,
            "subject.gm"));
        Assert.Contains("chummer.chronicle.source-packet/v2", packet);
        Assert.Contains("player-approved account", packet);
        Assert.DoesNotContain("last three runs", packet);

        CommunityStore reloaded = new(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        ChronicleProjectDto persisted = reloaded.ChronicleProjectsById[revised.ChronicleProjectId];
        Assert.Equal(2, persisted.SourcePacketVersion);
        Assert.Equal(revised.SourcePacketSha256, persisted.SourcePacketSha256);
        Assert.Equal(2, persisted.SourcePacketRevisions.Count);
    }

    [Fact]
    public void Draft_revision_is_manager_only_and_source_approval_freezes_the_current_version()
    {
        using var fixture = ChronicleFixture.Create();
        ChronicleProjectDto created = fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest("subject.gm"));

        Assert.Throws<CommunityAccessDeniedException>(() => fixture.Groups.ReviseChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            ValidRevisionRequest("subject.player")));

        fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_source"));
        Assert.Throws<InvalidOperationException>(() => fixture.Groups.ReviseChronicleProject(
            fixture.Group.GroupId,
            created.ChronicleProjectId,
            ValidRevisionRequest("subject.gm")));
    }

    [Fact]
    public void Members_only_see_player_safe_publication_approved_artifacts_and_cannot_manage_projects()
    {
        using var fixture = ChronicleFixture.Create();
        ChronicleProjectDto privateProject = fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest("subject.gm", audience: "gm_private"));
        ChronicleProjectDto playerProject = fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest("subject.gm", audience: "player_safe", title: "What the team knows"));

        Assert.Empty(fixture.Groups.ListChronicleProjects(fixture.Group.GroupId, "subject.player"));
        Assert.Throws<CommunityAccessDeniedException>(() => fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest("subject.player", audience: "player_safe")));
        Assert.Throws<CommunityAccessDeniedException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            playerProject.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.player", "approve_source")));

        AdvanceToArtifact(fixture.Groups, fixture.Group.GroupId, privateProject.ChronicleProjectId);
        Assert.Empty(fixture.Groups.ListChronicleProjects(fixture.Group.GroupId, "subject.player"));
        AdvanceToArtifact(fixture.Groups, fixture.Group.GroupId, playerProject.ChronicleProjectId);
        Assert.Empty(fixture.Groups.ListChronicleProjects(fixture.Group.GroupId, "subject.player"));
        fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            playerProject.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_publication"));

        ChronicleProjectDto visible = Assert.Single(fixture.Groups.ListChronicleProjects(fixture.Group.GroupId, "subject.player"));
        Assert.Equal(playerProject.ChronicleProjectId, visible.ChronicleProjectId);
        Assert.Equal("What the team knows", visible.Title);
        Assert.Equal("/artifacts/book.pdf", visible.ArtifactUrl);
        Assert.Equal(new string('b', 64), visible.ArtifactSha256);
        Assert.Equal("pdf", visible.ExportFormat);
        Assert.Empty(visible.CreatedByUserId);
        Assert.Empty(visible.SourceSummary);
        Assert.Empty(visible.ModelKey);
        Assert.Empty(visible.RunnerRoster);
        Assert.Empty(visible.SourcePacketSha256);
        Assert.Empty(visible.SourcePacketRevisions);
        Assert.Empty(visible.Provider);
        Assert.Null(visible.ExternalProjectRef);
        Assert.Equal(0, visible.EstimatedCredits);
        Assert.Null(visible.SourceApprovedAtUtc);
        Assert.Null(visible.UploadApprovedAtUtc);
        Assert.Null(visible.GenerationApprovedAtUtc);
        Assert.Null(visible.OutlineApprovedAtUtc);
        Assert.Throws<CommunityAccessDeniedException>(() => fixture.Groups.GetChronicleSourcePacket(
            fixture.Group.GroupId,
            playerProject.ChronicleProjectId,
            "subject.player"));
    }

    [Fact]
    public void Approval_and_artifact_validation_fail_closed()
    {
        using var fixture = ChronicleFixture.Create();
        ChronicleProjectDto missingConsent = fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest("subject.gm") with { ParticipantConsentConfirmed = false });
        InvalidOperationException gateError = Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            missingConsent.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_source")));
        Assert.Contains("participant consent", gateError.Message);

        ChronicleProjectDto missingSpoilerReview = fixture.Groups.CreateChronicleProject(
            fixture.Group.GroupId,
            ValidRequest("subject.gm") with { SpoilerReviewConfirmed = false });
        InvalidOperationException spoilerGateError = Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            missingSpoilerReview.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "approve_source")));
        Assert.Contains("spoiler review", spoilerGateError.Message);

        ChronicleProjectDto valid = fixture.Groups.CreateChronicleProject(fixture.Group.GroupId, ValidRequest("subject.gm"));
        fixture.Groups.UpdateChronicleProject(fixture.Group.GroupId, valid.ChronicleProjectId, new("subject.gm", "approve_source"));
        fixture.Groups.UpdateChronicleProject(fixture.Group.GroupId, valid.ChronicleProjectId, new("subject.gm", "approve_upload"));
        fixture.Groups.UpdateChronicleProject(fixture.Group.GroupId, valid.ChronicleProjectId, new("subject.gm", "approve_generation", "external-7"));
        fixture.Groups.UpdateChronicleProject(fixture.Group.GroupId, valid.ChronicleProjectId, new("subject.gm", "approve_outline"));

        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            valid.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "import_artifact", ArtifactUrl: "http://example.test/book.pdf", ArtifactSha256: new string('a', 64), ExportFormat: "pdf")));
        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            valid.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "import_artifact", ArtifactUrl: "/artifacts\\book.pdf", ArtifactSha256: new string('a', 64), ExportFormat: "pdf")));
        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            valid.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "import_artifact", ArtifactUrl: "/artifacts/../private/book.pdf", ArtifactSha256: new string('a', 64), ExportFormat: "pdf")));
        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            valid.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "import_artifact", ArtifactUrl: "/groups/private", ArtifactSha256: new string('a', 64), ExportFormat: "pdf")));
        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            valid.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "import_artifact", ArtifactUrl: "/artifacts/book.pdf?download=1", ArtifactSha256: new string('a', 64), ExportFormat: "pdf")));
        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            valid.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "import_artifact", ArtifactUrl: "/artifacts/book.pdf", ArtifactSha256: "not-a-digest", ExportFormat: "pdf")));
        Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
            fixture.Group.GroupId,
            valid.ChronicleProjectId,
            new UpdateChronicleProjectRequest("subject.gm", "import_artifact", ArtifactUrl: "/artifacts/book.pdf", ArtifactSha256: new string('a', 64), ExportFormat: "zip")));
    }

    [Fact]
    public void Every_source_approval_gate_fails_closed_individually()
    {
        using var fixture = ChronicleFixture.Create();
        CreateChronicleProjectRequest baseline = ValidRequest("subject.gm");
        (string ExpectedMessage, CreateChronicleProjectRequest Request)[] cases =
        [
            ("external processing consent", baseline with { ExternalProcessingConsent = false }),
            ("participant consent", baseline with { ParticipantConsentConfirmed = false }),
            ("redaction review", baseline with { RedactionReviewed = false }),
            ("spoiler review", baseline with { SpoilerReviewConfirmed = false }),
            ("source rights confirmation", baseline with { SourceRightsConfirmed = false })
        ];

        foreach ((string expectedMessage, CreateChronicleProjectRequest request) in cases)
        {
            ChronicleProjectDto project = fixture.Groups.CreateChronicleProject(fixture.Group.GroupId, request);
            InvalidOperationException error = Assert.Throws<InvalidOperationException>(() => fixture.Groups.UpdateChronicleProject(
                fixture.Group.GroupId,
                project.ChronicleProjectId,
                new UpdateChronicleProjectRequest("subject.gm", "approve_source")));
            Assert.Contains(expectedMessage, error.Message, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void Web_surface_names_every_gate_and_material_approval_separately()
    {
        string repositoryRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../.."));
        string view = File.ReadAllText(Path.Combine(repositoryRoot, "Chummer.Run.Api/Views/Groups/Detail.cshtml"));
        string controller = File.ReadAllText(Path.Combine(repositoryRoot, "Chummer.Run.Api/Controllers/GroupsController.cs"));

        Assert.Contains("name=\"redactionReviewed\"", view, StringComparison.Ordinal);
        Assert.Contains("name=\"spoilerReviewConfirmed\"", view, StringComparison.Ordinal);
        Assert.Contains("approve_upload", view, StringComparison.Ordinal);
        Assert.Contains("approve_generation", view, StringComparison.Ordinal);
        Assert.Contains("approve_outline", view, StringComparison.Ordinal);
        Assert.Contains("approve_publication", view, StringComparison.Ordinal);
        Assert.Contains("approve_external_send", view, StringComparison.Ordinal);
        Assert.Contains("spoilerReviewConfirmed", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("approve_handoff", view, StringComparison.Ordinal);
        Assert.Contains("string projectMeta = Model.CanManage", view, StringComparison.Ordinal);
        Assert.Contains("project.ExportFormat?.ToUpperInvariant()", view, StringComparison.Ordinal);
    }

    private static void AdvanceToArtifact(GroupService groups, string groupId, string projectId)
    {
        groups.UpdateChronicleProject(groupId, projectId, new("subject.gm", "approve_source"));
        groups.UpdateChronicleProject(groupId, projectId, new("subject.gm", "approve_upload"));
        groups.UpdateChronicleProject(groupId, projectId, new("subject.gm", "approve_generation", "aiwb-ref"));
        groups.UpdateChronicleProject(groupId, projectId, new("subject.gm", "approve_outline"));
        groups.UpdateChronicleProject(groupId, projectId, new(
            "subject.gm",
            "import_artifact",
            ArtifactUrl: "/artifacts/book.pdf",
            ArtifactSha256: new string('b', 64),
            ExportFormat: "pdf"));
    }

    private static CreateChronicleProjectRequest ValidRequest(
        string subjectId,
        string audience = "gm_private",
        string model = "gemini",
        int chapters = 3,
        int wordsPerChapter = 1200,
        bool includeRoster = false,
        bool includeCover = false,
        bool includeTranslation = false,
        bool includeAudiobook = false,
        string title = "Vienna After Midnight")
        => new(
            subjectId,
            title,
            "season_chronicle",
            audience,
            "A redaction-reviewed account of the team's last three runs.",
            model,
            chapters,
            wordsPerChapter,
            includeRoster,
            includeCover,
            includeTranslation,
            includeAudiobook,
            ExternalProcessingConsent: true,
            ParticipantConsentConfirmed: true,
            RedactionReviewed: true,
            SourceRightsConfirmed: true,
            SpoilerReviewConfirmed: true);

    private static ReviseChronicleProjectRequest ValidRevisionRequest(
        string subjectId,
        string audience = "gm_private",
        string model = "gemini",
        int chapters = 3,
        int wordsPerChapter = 1200,
        bool includeRoster = false,
        bool includeCover = false,
        bool includeTranslation = false,
        bool includeAudiobook = false,
        string title = "Vienna After Midnight",
        string sourceSummary = "A redaction-reviewed account of the team's last three runs.")
        => new(
            subjectId,
            title,
            "season_chronicle",
            audience,
            sourceSummary,
            model,
            chapters,
            wordsPerChapter,
            includeRoster,
            includeCover,
            includeTranslation,
            includeAudiobook,
            ExternalProcessingConsent: true,
            ParticipantConsentConfirmed: true,
            RedactionReviewed: true,
            SourceRightsConfirmed: true,
            SpoilerReviewConfirmed: true);

    private sealed class ChronicleFixture : IDisposable
    {
        private ChronicleFixture(
            string tempRoot,
            IConfiguration configuration,
            GroupService groups,
            GroupDto group,
            HubUserDto player)
        {
            TempRoot = tempRoot;
            Configuration = configuration;
            Groups = groups;
            Group = group;
            Player = player;
        }

        public string TempRoot { get; }
        public IConfiguration Configuration { get; }
        public GroupService Groups { get; }
        public GroupDto Group { get; }
        public HubUserDto Player { get; }

        public static ChronicleFixture Create()
        {
            string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-chronicle", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempRoot);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json")
                })
                .Build();
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            GroupService groups = new(store, accounts);
            accounts.EnsureUser("subject.gm", "GM");
            HubUserDto player = accounts.EnsureUser("subject.player", "Player");
            GroupDto group = groups.CreateGroup(new CreateGroupRequest("subject.gm", "Tuesday Shadows", "campaign", "private"));
            JoinCodeDto invite = groups.CreateJoinCode(group.GroupId, new CreateJoinCodeRequest("subject.gm"));
            var runner = groups.CreateRunner(new CreateRunnerRequest("subject.player", "Switchback", "Switchback"));
            group = groups.JoinGroup(new JoinGroupByCodeRequest("subject.player", invite.Code, runner.DossierId));
            return new ChronicleFixture(tempRoot, configuration, groups, group, player);
        }

        public void Dispose()
        {
            Directory.Delete(TempRoot, recursive: true);
        }
    }
}
