using System.Reflection;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Chummer.Run.Contracts.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignSpineGuardrailTests
{
    [Theory]
    [InlineData(nameof(CampaignSpineController.UpsertMyCampaignWorkspaceRunboardContinuity))]
    [InlineData(nameof(CampaignSpineController.UpsertMyCampaignWorkspaceCampaignAdoption))]
    [InlineData(nameof(CampaignSpineController.UpsertMyCampaignWorkspaceRunnerGoal))]
    [InlineData(nameof(CampaignSpineController.ApproveMyCampaignWorkspaceResolutionReport))]
    [InlineData(nameof(CampaignSpineController.LaunchMyCampaignWorkspacePrepPacket))]
    [InlineData(nameof(CampaignSpineController.StageMyCampaignWorkspaceTravelPrefetch))]
    [InlineData(nameof(CampaignSpineController.GenerateMyCampaignWorkspaceAftermathRecapPackage))]
    [InlineData(nameof(CampaignSpineController.UpsertMyCampaignWorkspaceConsequence))]
    [InlineData(nameof(CampaignSpineController.CreateMyCampaignWorkspaceOpenRun))]
    [InlineData(nameof(CampaignSpineController.SubmitMyOpenRunJoinRequest))]
    [InlineData(nameof(CampaignSpineController.ReviewMyOpenRunJoinRequest))]
    [InlineData(nameof(CampaignSpineController.ScheduleMyOpenRun))]
    [InlineData(nameof(CampaignSpineController.CreateMyOpenRunMeetingHandoff))]
    [InlineData(nameof(CampaignSpineController.CloseOutMyOpenRun))]
    [InlineData(nameof(CampaignSpineController.LaunchMyCampaignWorkspaceFederationBatch))]
    [InlineData(nameof(CampaignSpineController.MoveMyDossier))]
    [InlineData(nameof(CampaignSpineController.TransferMyRoster))]
    public void CampaignSpineMutationRoutesCapRequestBodySize(string methodName)
    {
        MethodInfo method = typeof(CampaignSpineController).GetMethod(methodName)
            ?? throw new InvalidOperationException($"CampaignSpineController.{methodName} was not found.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException($"{methodName} is missing RequestSizeLimitAttribute.");

        Assert.Equal(CampaignSpineService.MaxMutationRequestBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    [Fact]
    public void RecordPrepLaunchRejectsOversizedNote()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.RecordPrepLaunch(
            fixture.User,
            fixture.Workspace,
            "packet-a",
            "runbook",
            "Night market prep",
            "Prep summary",
            fixture.Run,
            fixture.Run.Scenes.First(),
            new string('n', 257)));

        Assert.Equal("note", error.ParamName);
    }

    [Fact]
    public void RecordTravelPrefetchRejectsOversizedNote()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.RecordTravelPrefetch(
            fixture.User,
            fixture.Workspace,
            new ClaimedDeviceRestoreProjection(
                InstallationId: "install-a",
                DeviceRole: "travel",
                Platform: "desktop",
                HeadId: "head-a",
                Channel: "stable",
                HostLabel: "Rig",
                RestoreSummary: "Ready"),
            "Prefetch summary",
            ["Package present."],
            ["Offline cache only."],
            new string('n', 257)));

        Assert.Equal("note", error.ParamName);
    }

    [Fact]
    public void RecordAftermathRecapPackageRejectsOversizedTitle()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.RecordAftermathRecapPackage(
            fixture.User,
            fixture.Workspace,
            fixture.Run,
            "session_recap",
            new string('t', 161),
            "Aftermath summary",
            ["Evidence line."]));

        Assert.Equal("title", error.ParamName);
    }

    [Fact]
    public void WorkspaceMutationsRejectResolvedWorkspaceAfterCampaignTeardownWithoutSideEffects()
    {
        using var fixture = new Fixture();
        string artifactRegistryPath = Path.Combine(
            Path.GetDirectoryName(fixture.StorePath)!,
            "campaign-artifact-registry.json");
        byte[]? artifactRegistryBefore = File.Exists(artifactRegistryPath)
            ? File.ReadAllBytes(artifactRegistryPath)
            : null;

        lock (fixture.Store.Gate)
        {
            fixture.Store.CampaignSpinesById.Remove(fixture.Workspace.CampaignId);
            fixture.Store.RunsById.Remove(fixture.Run.RunId);
            fixture.Store.PersistLocked();
        }
        byte[] durableStateBefore = File.ReadAllBytes(fixture.StorePath);

        Assert.Throws<KeyNotFoundException>(() => fixture.Service.RecordPrepLaunch(
            fixture.User,
            fixture.Workspace,
            "packet-stale",
            "runbook",
            "Stale prep",
            "Must not persist.",
            fixture.Run,
            fixture.Run.Scenes.First()));
        Assert.Throws<KeyNotFoundException>(() => fixture.Service.RecordTravelPrefetch(
            fixture.User,
            fixture.Workspace,
            new ClaimedDeviceRestoreProjection(
                InstallationId: "install-stale",
                DeviceRole: "travel",
                Platform: "desktop",
                HeadId: "head-stale",
                Channel: "stable",
                HostLabel: "Stale Rig",
                RestoreSummary: "Must not persist."),
            "Stale prefetch",
            ["Must not persist."],
            ["Campaign was removed."]));
        Assert.Throws<KeyNotFoundException>(() => fixture.Service.RecordAftermathRecapPackage(
            fixture.User,
            fixture.Workspace,
            fixture.Run,
            "session_recap",
            "Stale aftermath",
            "Must not persist.",
            ["Campaign was removed."]));

        Assert.Empty(fixture.Store.PrepLaunches);
        Assert.Empty(fixture.Store.TravelPrefetchReceipts);
        Assert.Empty(fixture.Store.AftermathPackages);
        Assert.Equal(durableStateBefore, File.ReadAllBytes(fixture.StorePath));
        if (artifactRegistryBefore is null)
        {
            Assert.False(File.Exists(artifactRegistryPath));
        }
        else
        {
            Assert.Equal(artifactRegistryBefore, File.ReadAllBytes(artifactRegistryPath));
        }

        CommunityStore reloaded = new(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        Assert.Empty(reloaded.PrepLaunches);
        Assert.Empty(reloaded.TravelPrefetchReceipts);
        Assert.Empty(reloaded.AftermathPackages);
        Assert.False(reloaded.CampaignSpinesById.ContainsKey(fixture.Workspace.CampaignId));
    }

    [Theory]
    [InlineData(nameof(CampaignSpineService.UpsertCampaignAdoption), true)]
    [InlineData(nameof(CampaignSpineService.UpsertCampaignAdoption), false)]
    [InlineData(nameof(CampaignSpineService.UpsertRunnerGoal), true)]
    [InlineData(nameof(CampaignSpineService.UpsertRunnerGoal), false)]
    [InlineData(nameof(CampaignSpineService.ApproveResolutionReport), true)]
    [InlineData(nameof(CampaignSpineService.ApproveResolutionReport), false)]
    [InlineData(nameof(CampaignSpineService.UpsertRunboardContinuity), true)]
    [InlineData(nameof(CampaignSpineService.UpsertRunboardContinuity), false)]
    [InlineData(nameof(CampaignSpineService.UpsertCampaignConsequence), true)]
    [InlineData(nameof(CampaignSpineService.UpsertCampaignConsequence), false)]
    public void AdjacentWorkspaceMutationsRejectResolvedWorkspaceAfterAuthorityRevocationWithoutPersistence(
        string mutationName,
        bool revokeMembership)
    {
        using var fixture = new Fixture();

        // The workspace projection was already resolved by the fixture. Revoke one of its
        // live authority inputs before the service enters the mutation lock.
        lock (fixture.Store.Gate)
        {
            CampaignProjection campaign = fixture.Store.CampaignSpinesById[fixture.Workspace.CampaignId];
            if (revokeMembership)
            {
                GroupDto group = fixture.Store.GroupsById[campaign.GroupId];
                fixture.Store.GroupsById[group.GroupId] = group with
                {
                    Memberships = group.Memberships
                        .Where(member => !string.Equals(member.UserId, fixture.User.UserId, StringComparison.OrdinalIgnoreCase))
                        .ToArray(),
                    UpdatedAtUtc = DateTimeOffset.UtcNow,
                };
            }
            else
            {
                foreach (string dossierId in campaign.DossierIds)
                {
                    if (fixture.Store.DossiersById.TryGetValue(dossierId, out RunnerDossierProjection? dossier)
                        && string.Equals(dossier.OwnerUserId, fixture.User.UserId, StringComparison.OrdinalIgnoreCase))
                    {
                        fixture.Store.DossiersById.Remove(dossierId);
                    }
                }
            }

            fixture.Store.PersistLocked();
        }

        CampaignProjection campaignBefore = fixture.Store.CampaignSpinesById[fixture.Workspace.CampaignId];
        RunProjection runBefore = fixture.Store.RunsById[fixture.Run.RunId];
        CampaignAdoptionProjection[] adoptionsBefore = fixture.Store.CampaignAdoptions.ToArray();
        RunnerGoalProjection[] goalsBefore = fixture.Store.RunnerGoals.ToArray();
        ResolutionReportApprovalProjection[] approvalsBefore = fixture.Store.ResolutionReportApprovals.ToArray();
        WorldTickProjection[] worldTicksBefore = fixture.Store.WorldTicks.ToArray();
        PlayerSafeNewsProjection[] newsBefore = fixture.Store.PlayerSafeNews.ToArray();
        byte[] durableStateBefore = File.ReadAllBytes(fixture.StorePath);

        Assert.Throws<CommunityAccessDeniedException>(() => InvokeAdjacentWorkspaceMutation(fixture, mutationName));

        Assert.Equal(campaignBefore, fixture.Store.CampaignSpinesById[fixture.Workspace.CampaignId]);
        Assert.Equal(runBefore, fixture.Store.RunsById[fixture.Run.RunId]);
        Assert.Equal(adoptionsBefore, fixture.Store.CampaignAdoptions);
        Assert.Equal(goalsBefore, fixture.Store.RunnerGoals);
        Assert.Equal(approvalsBefore, fixture.Store.ResolutionReportApprovals);
        Assert.Equal(worldTicksBefore, fixture.Store.WorldTicks);
        Assert.Equal(newsBefore, fixture.Store.PlayerSafeNews);
        Assert.Equal(durableStateBefore, File.ReadAllBytes(fixture.StorePath));
    }

    [Fact]
    public void RecordAftermathRecapPackageRollsBackRegistryAndCommunityStateWhenPersistenceFails()
    {
        using var fixture = new Fixture();
        string artifactRegistryPath = Path.Combine(
            Path.GetDirectoryName(fixture.StorePath)!,
            "campaign-artifact-registry.json");
        byte[] durableStateBefore = File.ReadAllBytes(fixture.StorePath);
        byte[]? artifactRegistryBefore = File.Exists(artifactRegistryPath)
            ? File.ReadAllBytes(artifactRegistryPath)
            : null;
        AftermathRecapPackageProjection[] packagesBefore = fixture.Store.AftermathPackages.ToArray();
        CampaignProjection campaignBefore = fixture.Store.CampaignSpinesById[fixture.Workspace.CampaignId];
        fixture.Store.AftermathPersistenceFaultInjector =
            () => throw new IOException("injected aftermath persistence failure");

        IOException failure = Assert.Throws<IOException>(() => fixture.Service.RecordAftermathRecapPackage(
            fixture.User,
            fixture.Workspace,
            fixture.Run,
            "session_recap",
            "Failed aftermath",
            "Must remain uncommitted.",
            ["Community persistence failed."]));

        Assert.Equal("injected aftermath persistence failure", failure.Message);
        Assert.Equal(packagesBefore, fixture.Store.AftermathPackages);
        Assert.Equal(campaignBefore, fixture.Store.CampaignSpinesById[fixture.Workspace.CampaignId]);
        Assert.Equal(durableStateBefore, File.ReadAllBytes(fixture.StorePath));
        if (artifactRegistryBefore is null)
        {
            Assert.False(File.Exists(artifactRegistryPath));
        }
        else
        {
            Assert.Equal(artifactRegistryBefore, File.ReadAllBytes(artifactRegistryPath));
        }

        fixture.Store.AftermathPersistenceFaultInjector = null;
        AftermathRecapPackageProjection retry = fixture.Service.RecordAftermathRecapPackage(
            fixture.User,
            fixture.Workspace,
            fixture.Run,
            "session_recap",
            "Recovered aftermath",
            "Persists after rollback.",
            ["Retry landed."]);

        Assert.Single(fixture.Store.AftermathPackages);
        Assert.Equal(retry.PackageId, fixture.Store.AftermathPackages[0].PackageId);
        Assert.True(File.Exists(artifactRegistryPath));
        Assert.Contains(retry.ArtifactId, File.ReadAllText(artifactRegistryPath), StringComparison.Ordinal);
        _ = new CampaignArtifactRegistryBridge(fixture.Store);
        CommunityStore reloaded = new(fixture.Configuration, NullLogger<CommunityStore>.Instance);
        Assert.Single(reloaded.AftermathPackages);
        Assert.Equal(retry.PackageId, reloaded.AftermathPackages[0].PackageId);
    }

    [Fact]
    public void CreateOpenRunRejectsOversizedListingTitle()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.CreateOpenRun(
            fixture.User,
            fixture.Workspace.WorkspaceId,
            new OpenRunCreateRequest(
                RunId: fixture.Run.RunId,
                ListingTitle: new string('l', 161),
                Summary: "A public listing summary.",
                Visibility: "community",
                TableContractSummary: "Reviewed table contract.",
                AdmissionMode: "request_to_join",
                SeatsTotal: 4,
                RequireRunnerDossier: true,
                AllowQuickstartRunner: true,
                SchedulingMode: "lunacal_slots",
                ExpectedDurationMinutes: 240,
                Platform: "discord",
                VoiceRequired: true,
                ObserverMode: "manual_markers",
                ReservedSeatRoles: ["decker"],
                Note: null)));

        Assert.Equal(nameof(OpenRunCreateRequest.ListingTitle), error.ParamName);
    }

    [Fact]
    public void UpsertCampaignConsequenceRejectsOversizedReturnLoopAction()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.UpsertCampaignConsequence(
            fixture.User,
            fixture.Workspace,
            new CampaignConsequenceUpdateRequest(
                Kind: "heat",
                State: "escalated",
                Summary: "Heat spikes after the run.",
                ReturnLoopAction: new string('a', 161),
                ReturnLoopRoute: null,
                Note: null)));

        Assert.Equal(nameof(CampaignConsequenceUpdateRequest.ReturnLoopAction), error.ParamName);
    }

    [Theory]
    [InlineData("heat")]
    [InlineData("faction")]
    [InlineData("contact")]
    [InlineData("reputation")]
    public void UpsertCampaignConsequenceDefaultsSharedWorkspaceReturnLoopRouteForGovernedReviewKinds(string kind)
    {
        using var fixture = new Fixture();

        CampaignConsequenceProjection consequence = fixture.Service.UpsertCampaignConsequence(
            fixture.User,
            fixture.Workspace,
            new CampaignConsequenceUpdateRequest(
                Kind: kind,
                State: "under_review",
                Summary: $"{kind} remains attached to the governed return rail.",
                ReturnLoopAction: null,
                ReturnLoopRoute: null,
                Note: null));

        CampaignConsequenceReceipt routeReceipt = Assert.Single(
            consequence.Receipts,
            receipt => string.Equals(receipt.SourceKind, "return_loop_route", StringComparison.Ordinal));

        Assert.Equal("/account/work", routeReceipt.ReceiptId);
        Assert.Equal("Return-loop route: /account/work.", routeReceipt.Summary);
    }

    [Fact]
    public void UpsertRunboardContinuityRejectsOversizedTurnLedgerSummary()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.UpsertRunboardContinuity(
            fixture.User,
            fixture.Workspace,
            new RunboardContinuityUpdateRequest(
                RunId: fixture.Run.RunId,
                ActiveSceneId: fixture.Run.ActiveSceneId,
                TurnLedgerSummary: new string('t', 4001),
                TurnLedgerEvidenceLines: null,
                RunboardStateSummary: "Runboard state stays green.",
                ObjectiveLines: null,
                Blockers: null,
                ResolutionReportStatus: "draft",
                ResolutionReportSummary: "Resolution draft remains attached to the same governed lane.",
                ResolutionNotes: null,
                NextSafeAction: null,
                Note: null)));

        Assert.Equal(nameof(RunboardContinuityUpdateRequest.TurnLedgerSummary), error.ParamName);
    }

    [Fact]
    public void UpsertCampaignAdoptionRejectsTooManyUnknowns()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.UpsertCampaignAdoption(
            fixture.User,
            fixture.Workspace,
            new CampaignAdoptionUpdateRequest(
                SafeToPlay: true,
                ConfidencePercent: 80,
                RunnerCount: fixture.Workspace.Dossiers.Count,
                ActiveJobCount: 1,
                ContactCount: 2,
                HouseRuleCount: fixture.Workspace.RuleEnvironment.HouseRulePacks.Count,
                ExplicitUnknowns:
                [
                    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"
                ],
                RecommendedNextActions: null,
                Summary: "Adoption posture remains acceptable.",
                NextSafeAction: null,
                Note: null)));

        Assert.Equal(nameof(CampaignAdoptionUpdateRequest.ExplicitUnknowns), error.ParamName);
    }

    [Fact]
    public void MoveDossierRejectsOversizedTargetRunTitle()
    {
        using var fixture = new Fixture();

        HubUserDto targetOwner = fixture.Accounts.EnsureUser("subject.outsider", "Outsider Demo", "outsider@example.invalid");
        GroupDto targetGroup = fixture.Groups.CreateGroup(new CreateGroupRequest(
            SubjectId: fixture.User.SubjectId,
            Name: "Thursday Crew Relay",
            GroupType: "campaign",
            Visibility: "group",
            Capabilities: null));

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.MoveDossier(
            fixture.User,
            new DossierMovementRequest(
                DossierId: fixture.Workspace.Dossiers.First().DossierId,
                TargetGroupId: targetGroup.GroupId,
                TargetCampaignId: null,
                TargetCampaignTitle: "Thursday Crew Relay",
                TargetRunId: null,
                TargetRunTitle: new string('r', 161),
                TargetSceneId: null,
                TargetSceneTitle: "Pier 3 exchange",
                TargetOwnerUserId: targetOwner.UserId,
                Note: null)));

        Assert.Equal(nameof(DossierMovementRequest.TargetRunTitle), error.ParamName);
    }

    [Fact]
    public void TransferRosterRejectsOversizedTargetCampaignTitle()
    {
        using var fixture = new Fixture();

        HubUserDto targetOwner = fixture.Accounts.EnsureUser("subject.outsider", "Outsider Demo", "outsider@example.invalid");
        GroupDto targetGroup = fixture.Groups.CreateGroup(new CreateGroupRequest(
            SubjectId: fixture.User.SubjectId,
            Name: "Saturday Relay Crew",
            GroupType: "campaign",
            Visibility: "group",
            Capabilities: null));

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.TransferRoster(
            fixture.User,
            new RosterTransferRequest(
                DossierId: fixture.Workspace.Dossiers.First().DossierId,
                TargetGroupId: targetGroup.GroupId,
                TargetCampaignId: null,
                TargetCampaignTitle: new string('c', 129),
                TargetOwnerUserId: targetOwner.UserId,
                Note: null)));

        Assert.Equal(nameof(RosterTransferRequest.TargetCampaignTitle), error.ParamName);
    }

    [Fact]
    public void CampaignFederationNormalizeRequestRejectsOversizedRequestedFormat()
    {
        MethodInfo method = typeof(CampaignFederationOrchestrationService).GetMethod("NormalizeRequest", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("NormalizeRequest was not found.");

        TargetInvocationException invocation = Assert.Throws<TargetInvocationException>(() => method.Invoke(
            null,
            [new CampaignFederationBatchRequest(RequestedFormats: [new string('f', 33)])]));

        ArgumentException error = Assert.IsType<ArgumentException>(invocation.InnerException);
        Assert.Equal(nameof(CampaignFederationBatchRequest.RequestedFormats), error.ParamName);
    }

    [Fact]
    public void CampaignFederationNormalizeRequestRejectsTooManySourceIds()
    {
        MethodInfo method = typeof(CampaignFederationOrchestrationService).GetMethod("NormalizeRequest", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("NormalizeRequest was not found.");

        TargetInvocationException invocation = Assert.Throws<TargetInvocationException>(() => method.Invoke(
            null,
            [new CampaignFederationBatchRequest(SourceIds:
            [
                "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"
            ])]));

        ArgumentException error = Assert.IsType<ArgumentException>(invocation.InnerException);
        Assert.Equal(nameof(CampaignFederationBatchRequest.SourceIds), error.ParamName);
    }

    [Fact]
    public void ApproveResolutionReportRejectsOversizedNewsUrl()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.ApproveResolutionReport(
            fixture.User,
            fixture.Workspace,
            new ResolutionReportApprovalRequest(
                RunId: fixture.Run.RunId,
                Summary: "Resolution approval closes the run cleanly.",
                WorldTickSummary: "World tick summary.",
                ConsequenceSummary: "Consequence summary.",
                NewsTitle: "News title",
                NewsSummary: "Player-safe news summary.",
                NewsSource: "BLACK LEDGER",
                NewsUrl: $"https://example.invalid/{new string('n', 2050)}",
                NextSafeAction: null,
                Note: null)));

        Assert.Equal(nameof(ResolutionReportApprovalRequest.NewsUrl), error.ParamName);
    }

    private static void InvokeAdjacentWorkspaceMutation(Fixture fixture, string mutationName)
    {
        switch (mutationName)
        {
            case nameof(CampaignSpineService.UpsertCampaignAdoption):
                fixture.Service.UpsertCampaignAdoption(
                    fixture.User,
                    fixture.Workspace,
                    new CampaignAdoptionUpdateRequest(
                        SafeToPlay: true,
                        ConfidencePercent: 90,
                        RunnerCount: fixture.Workspace.Dossiers.Count,
                        ActiveJobCount: 1,
                        ContactCount: 2,
                        HouseRuleCount: fixture.Workspace.RuleEnvironment.HouseRulePacks.Count,
                        ExplicitUnknowns: [],
                        RecommendedNextActions: ["Keep the governed return current."],
                        Summary: "Resolved workspace adoption must not outlive current authority.",
                        NextSafeAction: null,
                        Note: null));
                break;
            case nameof(CampaignSpineService.UpsertRunnerGoal):
                fixture.Service.UpsertRunnerGoal(
                    fixture.User,
                    fixture.Workspace,
                    new RunnerGoalUpdateRequest(
                        DossierId: fixture.Workspace.Dossiers.First().DossierId,
                        Label: "Authority race guard",
                        TargetKind: "upgrade_fund",
                        TargetReference: "authority_race_guard",
                        SavedNuyen: 100,
                        NuyenRequired: 1000,
                        KarmaReserved: 1,
                        DowntimeDays: 1,
                        ApprovalStatus: "gm_review",
                        NextSafeAction: null,
                        Note: null));
                break;
            case nameof(CampaignSpineService.ApproveResolutionReport):
                fixture.Service.ApproveResolutionReport(
                    fixture.User,
                    fixture.Workspace,
                    new ResolutionReportApprovalRequest(
                        RunId: fixture.Run.RunId,
                        Summary: "Authority race approval must not persist.",
                        WorldTickSummary: "Authority race world tick must not persist.",
                        ConsequenceSummary: "Authority race consequence must not persist.",
                        NewsTitle: "Authority race",
                        NewsSummary: "Authority race news must not persist.",
                        NewsSource: "BLACK LEDGER",
                        NewsUrl: "https://example.invalid/news/authority-race",
                        NextSafeAction: null,
                        Note: null));
                break;
            case nameof(CampaignSpineService.UpsertRunboardContinuity):
                fixture.Service.UpsertRunboardContinuity(
                    fixture.User,
                    fixture.Workspace,
                    new RunboardContinuityUpdateRequest(
                        RunId: fixture.Run.RunId,
                        ActiveSceneId: fixture.Run.ActiveSceneId,
                        TurnLedgerSummary: "Authority race turn ledger must not persist.",
                        TurnLedgerEvidenceLines: [],
                        RunboardStateSummary: "Authority race runboard must not persist.",
                        ObjectiveLines: [],
                        Blockers: [],
                        ResolutionReportStatus: "draft",
                        ResolutionReportSummary: "Authority race draft must not persist.",
                        ResolutionNotes: [],
                        NextSafeAction: null,
                        Note: null));
                break;
            case nameof(CampaignSpineService.UpsertCampaignConsequence):
                fixture.Service.UpsertCampaignConsequence(
                    fixture.User,
                    fixture.Workspace,
                    new CampaignConsequenceUpdateRequest(
                        Kind: "heat",
                        State: "blocked",
                        Summary: "Authority race consequence must not persist.",
                        ReturnLoopAction: null,
                        ReturnLoopRoute: null,
                        Note: null));
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(mutationName), mutationName, "Unknown adjacent workspace mutation.");
        }
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-campaign-spine-guardrail-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            StorePath = Path.Combine(_root, "community.json");
            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Store);
            Groups = new GroupService(Store, Accounts);
            SupportStore supportStore = new(Configuration, NullLogger<SupportStore>.Instance);
            Service = new CampaignSpineService(
                Store,
                new WorkspaceLifecyclePolicyService(Configuration),
                new CampaignArtifactRegistryBridge(Store),
                supportStore);

            User = Accounts.EnsureUser("subject.guardrail", "Guardrail Operator", "guardrail@example.invalid");
            Workspace = Service.GetStarterWorkspace(User)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            Run = Workspace.Runs.First();
        }

        public IConfiguration Configuration { get; }
        public string StorePath { get; }
        public CommunityStore Store { get; }
        public CampaignSpineService Service { get; }
        public AccountService Accounts { get; }
        public GroupService Groups { get; }
        public HubUserDto User { get; }
        public CampaignWorkspaceProjection Workspace { get; }
        public RunProjection Run { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
