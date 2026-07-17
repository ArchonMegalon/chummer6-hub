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

            CommunityStore store = new(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(store);
            Groups = new GroupService(store, Accounts);
            SupportStore supportStore = new(Configuration, NullLogger<SupportStore>.Instance);
            Service = new CampaignSpineService(
                store,
                new WorkspaceLifecyclePolicyService(Configuration),
                new CampaignArtifactRegistryBridge(store),
                supportStore);

            User = Accounts.EnsureUser("subject.guardrail", "Guardrail Operator", "guardrail@example.invalid");
            Workspace = Service.GetStarterWorkspace(User)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            Run = Workspace.Runs.First();
        }

        public IConfiguration Configuration { get; }
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
