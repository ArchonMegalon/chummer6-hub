using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Security.Cryptography;
using System.Reflection;
using System.Text;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class BuildGhostLiveSupportServiceTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-08-25T00:45:00Z");
    private static readonly byte[] ReceiptAuthorityKey = Enumerable.Range(1, 32).Select(static value => (byte)value).ToArray();

    [TestMethod]
    public async Task Default_is_Rook_VidBoard_and_live_support_is_fail_closed()
    {
        RecordingMeetingBroker broker = new();
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(
            new ConfigurationBuilder().AddInMemoryCollection([]).Build(),
            broker,
            bots);

        BuildGhostSupportExperienceProjection experience = service.BuildExperience();
        BuildGhostLiveSupportSessionProjection session = await service.RequestAsync(Request(), CancellationToken.None);

        Assert.AreEqual(BuildGhostSupportChannelKinds.RookVidBoard, experience.DefaultSupport.ChannelKind);
        Assert.AreEqual(ToughTongueBuildGhostPersonaIds.Rook, experience.DefaultSupport.PersonaId);
        Assert.AreEqual(ToughTongueBuildGhostPersonaIds.RookAvatar, experience.DefaultSupport.AvatarId);
        Assert.AreEqual(ToughTongueBuildGhostPersonaIds.RookVidBoardSupport, experience.DefaultSupport.MediaAssetId);
        Assert.IsFalse(experience.DefaultSupport.PreRenderedVideoReady);
        Assert.IsFalse(experience.LiveSupport.RequestAvailable);
        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, session.Status);
        Assert.IsNull(session.JoinUrl);
        CollectionAssert.Contains(session.BlockingReasons.ToArray(), "live-support-remote-execution-disabled-by-default");
        Assert.AreEqual(0, broker.CreateCalls);
        Assert.AreEqual(0, bots.Calls);
    }

    [TestMethod]
    public async Task Verified_Zoom_lane_returns_link_only_after_meeting_and_photorealistic_bot_succeed()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://chummer.zoom.us/j/123456789?pwd=opaque", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new()
        {
            Result = SuccessfulBot()
        };
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection first = await service.RequestAsync(Request(), CancellationToken.None);
        BuildGhostLiveSupportSessionProjection replay = await service.RequestAsync(Request(), CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Ready, first.Status);
        Assert.AreEqual(new Uri("https://chummer.zoom.us/j/123456789?pwd=opaque"), first.JoinUrl);
        Assert.AreEqual("photorealistic-provider-managed", first.AvatarPresentation);
        Assert.AreEqual(ToughTongueBuildGhostPersonaIds.StockDefaultAvatar, first.AvatarAlias);
        Assert.AreEqual(receipt.ReceiptDigest, first.CapabilityReceiptDigest);
        Assert.IsTrue(first.RecordingConsentGranted);
        Assert.IsTrue(first.ExternalProviderProcessingConsentGranted);
        Assert.AreEqual(BuildGhostLiveSupportDisclosureContract.CurrentVersion, first.DisclosureVersion);
        Assert.AreEqual(BuildGhostLiveSupportDisclosureContract.ComputeDigest(), first.DisclosureDigest);
        Assert.AreEqual(first, replay);
        Assert.AreEqual(1, broker.CreateCalls);
        Assert.AreEqual(1, bots.Calls);
        Assert.AreEqual(0, broker.CancelCalls);
    }

    [TestMethod]
    public async Task Durable_global_capacity_reservation_blocks_a_second_paid_meeting()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://zoom.us/j/123456789", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new() { Result = SuccessfulBot() };
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection first =
            await service.RequestAsync(Request(), CancellationToken.None);
        BuildGhostLiveSupportSessionProjection second = await service.RequestAsync(
            Request() with
            {
                RequestId = "request-live-2",
                IdempotencyKey = "idempotency-live-2"
            },
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Ready, first.Status);
        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, second.Status);
        CollectionAssert.Contains(
            second.BlockingReasons.ToArray(),
            "live-support-provider-capacity-reservation-open");
        Assert.AreEqual(1, broker.CreateCalls);
        Assert.AreEqual(1, bots.Calls);
    }

    [TestMethod]
    public async Task Consent_is_required_before_any_provider_call()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new();
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection result = await service.RequestAsync(
            Request() with { RecordingConsentGranted = false },
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, result.Status);
        Assert.IsNull(result.JoinUrl);
        CollectionAssert.Contains(result.BlockingReasons.ToArray(), "live-support-recording-consent-required");
        Assert.AreEqual(0, broker.CreateCalls);
        Assert.AreEqual(0, bots.Calls);
    }

    [TestMethod]
    public async Task Disclosure_authority_is_bound_before_any_provider_call()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new();
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection result = await service.RequestAsync(
            Request() with { DisclosureDigest = Digest("unapproved-disclosure") },
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, result.Status);
        Assert.IsNull(result.JoinUrl);
        CollectionAssert.Contains(result.BlockingReasons.ToArray(), "live-support-disclosure-digest-invalid");
        Assert.AreEqual(0, broker.CreateCalls);
        Assert.AreEqual(0, bots.Calls);
    }

    [TestMethod]
    public void Durable_request_fingerprint_binds_disclosure_version_and_digest()
    {
        MethodInfo fingerprint = typeof(BuildGhostLiveSupportService).GetMethod(
            "RequestFingerprint",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new AssertFailedException("Request fingerprint helper is unavailable.");
        BuildGhostLiveSupportRequest request = Request();

        string original = (string)fingerprint.Invoke(null, [request])!;
        string changedVersion = (string)fingerprint.Invoke(
            null,
            [request with { DisclosureVersion = "chummer.build_ghost.live_support_disclosure.v2" }])!;
        string changedDigest = (string)fingerprint.Invoke(
            null,
            [request with { DisclosureDigest = Digest("changed-disclosure") }])!;

        Assert.AreNotEqual(original, changedVersion);
        Assert.AreNotEqual(original, changedDigest);
    }

    [TestMethod]
    public async Task Provider_capability_is_independent_for_Zoom_and_Teams()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new();
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection result = await service.RequestAsync(
            Request() with { MeetingProvider = BuildGhostLiveMeetingProviders.Teams },
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, result.Status);
        Assert.IsNull(result.JoinUrl);
        CollectionAssert.Contains(result.BlockingReasons.ToArray(), "teams-live-support-capability-unverified");
        Assert.AreEqual(0, broker.CreateCalls);
        Assert.AreEqual(0, bots.Calls);
    }

    [TestMethod]
    public void Configured_meeting_bot_scenario_must_match_the_signed_capability_receipt()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBotClient bots = new() { ScenarioRefDigest = Digest("different-scenario") };
        BuildGhostLiveSupportService service = CreateService(
            Configuration(receipt.Path),
            new RecordingMeetingBroker(),
            bots);

        BuildGhostSupportExperienceProjection experience = service.BuildExperience();

        Assert.IsFalse(experience.LiveSupport.RequestAvailable);
        CollectionAssert.Contains(
            experience.LiveSupport.BlockingReasons.ToArray(),
            "live-support-meeting-bot-scenario-authority-mismatch");
    }

    [TestMethod]
    public async Task Meeting_bot_failure_cancels_the_orphan_meeting_and_never_returns_its_link()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://zoom.us/j/123456789", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new()
        {
            Result = new BuildGhostToughTongueMeetingBotResult(
                false,
                false,
                "provider-unavailable",
                string.Empty,
                string.Empty,
                string.Empty)
        };
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection result = await service.RequestAsync(Request(), CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, result.Status);
        Assert.IsNull(result.JoinUrl);
        CollectionAssert.Contains(result.BlockingReasons.ToArray(), "provider-unavailable");
        Assert.AreEqual(1, broker.CreateCalls);
        Assert.AreEqual(1, bots.Calls);
        Assert.AreEqual(1, broker.CancelCalls);
    }

    [TestMethod]
    public async Task Unverified_compensation_keeps_reconciliation_open_and_blocks_a_second_meeting()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CancelSucceeds = false,
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://zoom.us/j/123456789", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection first =
            await service.RequestAsync(Request(), CancellationToken.None);
        BuildGhostLiveSupportSessionProjection second = await service.RequestAsync(
            Request() with
            {
                RequestId = "request-live-2",
                IdempotencyKey = "idempotency-live-2"
            },
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.ProvisioningAvatar, first.Status);
        CollectionAssert.Contains(
            first.BlockingReasons.ToArray(),
            "meeting-link-compensation-unverified");
        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, second.Status);
        CollectionAssert.Contains(
            second.BlockingReasons.ToArray(),
            "live-support-provider-capacity-reservation-open");
        Assert.AreEqual(1, broker.CreateCalls);
        Assert.AreEqual(1, bots.Calls);
        Assert.AreEqual(1, broker.CancelCalls);
    }

    [TestMethod]
    public async Task Uncertain_meeting_mutation_is_journaled_and_same_request_never_repeats_it()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = new BuildGhostMeetingLinkProvisioningResult(
                false,
                true,
                "meeting-link-broker-transport-failed-redacted",
                BuildGhostLiveMeetingProviders.Zoom,
                null,
                string.Empty,
                string.Empty,
                string.Empty,
                null,
                null)
        };
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection first =
            await service.RequestAsync(Request(), CancellationToken.None);
        BuildGhostLiveSupportSessionProjection replay =
            await service.RequestAsync(Request(), CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.ProvisioningMeeting, first.Status);
        Assert.IsNull(first.JoinUrl);
        CollectionAssert.Contains(
            first.BlockingReasons.ToArray(),
            "meeting-link-provisioning-reconciliation-required");
        Assert.AreEqual(first, replay);
        Assert.AreEqual(1, broker.CreateCalls);
        Assert.AreEqual(0, bots.Calls);
    }

    [TestMethod]
    public async Task Uncertain_avatar_mutation_is_journaled_compensated_and_never_repeated()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://zoom.us/j/123456789", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new()
        {
            Result = new BuildGhostToughTongueMeetingBotResult(
                false,
                true,
                "tough-tongue-meeting-bot-response-invalid",
                string.Empty,
                string.Empty,
                Digest("ambiguous-response"))
        };
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection first =
            await service.RequestAsync(Request(), CancellationToken.None);
        BuildGhostLiveSupportSessionProjection replay =
            await service.RequestAsync(Request(), CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.ProvisioningAvatar, first.Status);
        Assert.IsNull(first.JoinUrl);
        CollectionAssert.Contains(
            first.BlockingReasons.ToArray(),
            "tough-tongue-meeting-bot-reconciliation-required");
        Assert.AreEqual(first, replay);
        Assert.AreEqual(1, broker.CreateCalls);
        Assert.AreEqual(1, bots.Calls);
        Assert.AreEqual(1, broker.CancelCalls);
    }

    [TestMethod]
    public async Task Lookalike_meeting_host_is_rejected_compensated_and_never_sent_to_Tough_Tongue()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://zoom.us.attacker.example/j/123456789", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection result = await service.RequestAsync(Request(), CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, result.Status);
        Assert.IsNull(result.JoinUrl);
        CollectionAssert.Contains(result.BlockingReasons.ToArray(), "meeting-link-url-invalid");
        Assert.AreEqual(1, broker.CancelCalls);
        Assert.AreEqual(0, bots.Calls);
    }

    [TestMethod]
    public void Recomputed_unkeyed_digest_cannot_forge_capability_authority()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        BuildGhostLiveSupportCapabilityReceipt original = JsonSerializer.Deserialize<BuildGhostLiveSupportCapabilityReceipt>(
            File.ReadAllText(receipt.Path))!;
        BuildGhostLiveSupportCapabilityReceipt forged = original with
        {
            AccountScopeRefDigest = Digest("attacker-account"),
            ReceiptDigest = string.Empty
        };
        forged = forged with
        {
            ReceiptDigest = BuildGhostLiveSupportService.DigestCapabilityReceipt(forged)
        };
        File.WriteAllText(receipt.Path, JsonSerializer.Serialize(forged));
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(receipt.Path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }

        BuildGhostLiveSupportService service = CreateService(
            Configuration(receipt.Path),
            new RecordingMeetingBroker(),
            new RecordingMeetingBotClient());

        BuildGhostSupportExperienceProjection experience = service.BuildExperience();

        Assert.IsFalse(experience.LiveSupport.RequestAvailable);
        CollectionAssert.Contains(
            experience.LiveSupport.BlockingReasons.ToArray(),
            "live-support-capability-authority-mac-invalid");
        CollectionAssert.Contains(
            experience.LiveSupport.BlockingReasons.ToArray(),
            "live-support-capability-account-scope-authority-mismatch");
    }

    [TestMethod]
    public async Task Durable_status_readback_is_owner_bound()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://zoom.us/j/123456789", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new() { Result = SuccessfulBot() };
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);
        BuildGhostLiveSupportRequest request = Request();

        BuildGhostLiveSupportSessionProjection created =
            await service.RequestAsync(request, CancellationToken.None);
        BuildGhostLiveSupportSessionProjection? sameOwner = await service.GetAsync(
            new BuildGhostLiveSupportStatusRequest(
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                request.OwnerScopeHash,
                request.RequestId,
                request.WorkspaceId,
                request.SourceDigest),
            CancellationToken.None);
        BuildGhostLiveSupportSessionProjection? wrongOwner = await service.GetAsync(
            new BuildGhostLiveSupportStatusRequest(
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                Digest("other-owner"),
                request.RequestId,
                request.WorkspaceId,
                request.SourceDigest),
            CancellationToken.None);
        BuildGhostLiveSupportSessionProjection? wrongHandoff = await service.GetAsync(
            new BuildGhostLiveSupportStatusRequest(
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                request.OwnerScopeHash,
                request.RequestId,
                "handoff-other",
                Digest("other-source")),
            CancellationToken.None);
        BuildGhostLiveSupportSessionProjection? changedContext = await service.GetAsync(
            new BuildGhostLiveSupportStatusRequest(
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                request.OwnerScopeHash,
                request.RequestId,
                request.WorkspaceId,
                Digest("changed-source")),
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Ready, created.Status);
        Assert.AreEqual(created, sameOwner);
        Assert.IsNull(wrongOwner);
        Assert.IsNull(wrongHandoff);
        Assert.IsNotNull(changedContext);
        Assert.AreEqual(created.JoinUrl, changedContext.JoinUrl);
        CollectionAssert.Contains(
            changedContext.BlockingReasons.ToArray(),
            "live-support-handoff-context-changed-after-request");
    }

    [TestMethod]
    public async Task Expired_status_preserves_request_local_source_drift_without_persisting_it()
    {
        using ReceiptFile receipt = ReceiptFile.Create([BuildGhostLiveMeetingProviders.Zoom]);
        RecordingMeetingBroker broker = new()
        {
            CreateResult = SuccessfulMeeting(
                BuildGhostLiveMeetingProviders.Zoom,
                new Uri("https://zoom.us/j/123456789", UriKind.Absolute))
        };
        RecordingMeetingBotClient bots = new() { Result = SuccessfulBot() };
        FixedClock clock = new();
        MemorySessionStore store = new();
        BuildGhostLiveSupportService service = CreateService(
            Configuration(receipt.Path),
            broker,
            bots,
            clock,
            store);
        BuildGhostLiveSupportRequest request = Request();

        BuildGhostLiveSupportSessionProjection created =
            await service.RequestAsync(request, CancellationToken.None);
        clock.UtcNow = Now.AddMinutes(46);
        BuildGhostLiveSupportSessionProjection? changedContext = await service.GetAsync(
            new BuildGhostLiveSupportStatusRequest(
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                request.OwnerScopeHash,
                request.RequestId,
                request.WorkspaceId,
                Digest("changed-source")),
            CancellationToken.None);
        BuildGhostLiveSupportSessionProjection? originalContext = await service.GetAsync(
            new BuildGhostLiveSupportStatusRequest(
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                request.OwnerScopeHash,
                request.RequestId,
                request.WorkspaceId,
                request.SourceDigest),
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Ready, created.Status);
        Assert.IsNotNull(changedContext);
        Assert.AreEqual(BuildGhostLiveSupportStatuses.Expired, changedContext.Status);
        Assert.IsNull(changedContext.JoinUrl);
        CollectionAssert.Contains(
            changedContext.BlockingReasons.ToArray(),
            "live-support-handoff-context-changed-after-request");
        CollectionAssert.Contains(
            changedContext.BlockingReasons.ToArray(),
            "live-support-meeting-link-expired");
        Assert.IsNotNull(originalContext);
        Assert.AreEqual(BuildGhostLiveSupportStatuses.Expired, originalContext.Status);
        CollectionAssert.Contains(
            originalContext.BlockingReasons.ToArray(),
            "live-support-meeting-link-expired");
        CollectionAssert.DoesNotContain(
            originalContext.BlockingReasons.ToArray(),
            "live-support-handoff-context-changed-after-request");
    }

    [TestMethod]
    public async Task Provider_minute_reserve_blocks_meeting_before_any_remote_call()
    {
        using ReceiptFile receipt = ReceiptFile.Create(
            [BuildGhostLiveMeetingProviders.Zoom],
            availableMinutes: 150m);
        RecordingMeetingBroker broker = new();
        RecordingMeetingBotClient bots = new();
        BuildGhostLiveSupportService service = CreateService(Configuration(receipt.Path), broker, bots);

        BuildGhostLiveSupportSessionProjection result =
            await service.RequestAsync(Request(), CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, result.Status);
        CollectionAssert.Contains(
            result.BlockingReasons.ToArray(),
            "live-support-provider-minute-reserve-insufficient");
        Assert.AreEqual(0, broker.CreateCalls);
        Assert.AreEqual(0, bots.Calls);
    }

    private static BuildGhostLiveSupportService CreateService(
        IConfiguration configuration,
        RecordingMeetingBroker broker,
        RecordingMeetingBotClient bots,
        FixedClock? clock = null,
        MemorySessionStore? store = null)
        => new(
            configuration,
            new StaticReleaseRegistry(),
            broker,
            bots,
            clock ?? new FixedClock(),
            store ?? new MemorySessionStore());

    private static IConfiguration Configuration(string receiptPath)
        => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostLiveSupportService.RemoteExecutionEnabledKey] = "true",
            [BuildGhostLiveSupportService.CapabilityReceiptPathKey] = receiptPath,
            [BuildGhostLiveSupportService.CapabilityReceiptHmacKey] = Convert.ToBase64String(ReceiptAuthorityKey),
            [BuildGhostLiveSupportService.ExpectedAccountScopeDigestKey] = Digest("account"),
            [BuildGhostLiveSupportService.ExpectedScenarioDigestKey] = Digest("scenario"),
            [BuildGhostLiveSupportService.ExpectedAvatarBindingDigestKey] = Digest("avatar-binding"),
            [BuildGhostLiveSupportService.RookVidBoardMediaHrefKey] = "/media/support/rook-build-ghost-v1.mp4",
            [BuildGhostLiveSupportService.RookVidBoardMediaDigestKey] = Digest("vidboard-media")
        }).Build();

    private static BuildGhostLiveSupportRequest Request()
        => new(
            ToughTongueBuildGhostContractVersions.LiveSupportRequestV1,
            "request-live-1",
            Digest("owner"),
            "workspace-1",
            17,
            Digest("source"),
            "en-US",
            BuildGhostLiveMeetingProviders.Zoom,
            true,
            true,
            BuildGhostLiveSupportDisclosureContract.CurrentVersion,
            BuildGhostLiveSupportDisclosureContract.ComputeDigest(),
            30,
            "idempotency-live-1",
            Now);

    private static BuildGhostMeetingLinkProvisioningResult SuccessfulMeeting(string provider, Uri joinUrl)
        => new(
            true,
            false,
            "created",
            provider,
            joinUrl,
            "cancel-meeting-1",
            Digest("meeting"),
            Digest("meeting-response"),
            Now,
            Now.AddMinutes(45));

    private static BuildGhostToughTongueMeetingBotResult SuccessfulBot()
        => new(
            true,
            false,
            "scheduled",
            Digest("bot"),
            Digest("session"),
            Digest("bot-response"));

    private static string Digest(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";

    private sealed class StaticReleaseRegistry : IBuildGhostPersonaReleaseRegistry
    {
        public BuildGhostPersonaReleaseProjection ResolveRook()
            => new(
                ToughTongueBuildGhostPersonaIds.Rook,
                ToughTongueBuildGhostPersonaIds.RookAvatar,
                ToughTongueBuildGhostPersonaIds.RookVoice,
                "approved",
                "approved",
                true,
                true,
                "rook-vidboard-and-synthetic-voice",
                []);

        public BuildGhostPersonaMediaRelease? ResolveRookVidBoardMedia()
            => new(
                ToughTongueBuildGhostContractVersions.PersonaReleaseV1,
                "rook-vidboard-release-1",
                ToughTongueBuildGhostPersonaIds.Rook,
                ToughTongueBuildGhostPersonaIds.RookVidBoardSupport,
                "vidboard-support-video",
                "Chummer",
                "synthetic-rook-rendered-by-vidboard",
                Digest("vidboard-media"),
                "consent-rook-1",
                "chummer-owned",
                "verified",
                "approved",
                Now);
    }

    private sealed class FixedClock : IBuildGhostClock
    {
        public DateTimeOffset UtcNow { get; set; } = Now;
    }

    private sealed class MemorySessionStore : IBuildGhostLiveSupportSessionStore
    {
        private readonly Dictionary<string, StoredBuildGhostLiveSupportSession> sessions = new(StringComparer.Ordinal);

        public IReadOnlyList<string> BlockingReasons => [];

        public Task<bool?> HasOpenReservationAsync(
            DateTimeOffset now,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult<bool?>(sessions.Values.Any(stored =>
                EncryptedFileBuildGhostLiveSupportSessionStore.ReservesProviderCapacity(
                    stored.Session,
                    now)));
        }

        public Task<StoredBuildGhostLiveSupportSession?> ReadAsync(
            string ownerScopeHash,
            string requestId,
            string workspaceId,
            string sourceDigest,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            sessions.TryGetValue(
                $"{ownerScopeHash}\n{workspaceId}\n{requestId}",
                out StoredBuildGhostLiveSupportSession? stored);
            return Task.FromResult(
                stored is not null
                    && string.Equals(stored.WorkspaceId, workspaceId, StringComparison.Ordinal)
                    ? stored
                    : null);
        }

        public Task<bool> WriteAsync(
            StoredBuildGhostLiveSupportSession stored,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            sessions[$"{stored.OwnerScopeHash}\n{stored.WorkspaceId}\n{stored.Session.RequestId}"] = stored;
            return Task.FromResult(true);
        }
    }

    private sealed class RecordingMeetingBroker : IBuildGhostMeetingLinkBroker, IBuildGhostLiveSupportDependencyReadiness
    {
        public IReadOnlyList<string> BlockingReasons => [];

        public int CreateCalls { get; private set; }
        public int CancelCalls { get; private set; }
        public bool ThrowOnCreate { get; init; }
        public bool CancelSucceeds { get; init; } = true;
        public BuildGhostMeetingLinkProvisioningResult CreateResult { get; init; } = new(
            false,
            false,
            "meeting-link-broker-disabled",
            BuildGhostLiveMeetingProviders.Zoom,
            null,
            string.Empty,
            string.Empty,
            string.Empty,
            null,
            null);

        public Task<BuildGhostMeetingLinkProvisioningResult> CreateAsync(
            BuildGhostMeetingLinkProvisioningCommand command,
            CancellationToken cancellationToken)
        {
            CreateCalls++;
            if (ThrowOnCreate)
            {
                throw new HttpRequestException("ambiguous meeting broker outcome");
            }
            return Task.FromResult(CreateResult);
        }

        public Task<BuildGhostMeetingLinkCancellationResult> CancelAsync(
            BuildGhostMeetingLinkCancellationCommand command,
            CancellationToken cancellationToken)
        {
            CancelCalls++;
            return Task.FromResult(new BuildGhostMeetingLinkCancellationResult(
                CancelSucceeds,
                CancelSucceeds ? "cancelled" : "cancellation-unverified",
                Digest("cancel-response")));
        }
    }

    private sealed class RecordingMeetingBotClient :
        IToughTongueLiveSupportMeetingClient,
        IToughTongueLiveSupportAuthorityBinding,
        IBuildGhostLiveSupportDependencyReadiness
    {
        public IReadOnlyList<string> BlockingReasons => [];

        public int Calls { get; private set; }
        public bool ThrowOnSchedule { get; init; }
        public string ScenarioRefDigest { get; init; } = Digest("scenario");
        public BuildGhostToughTongueMeetingBotResult Result { get; init; } = new(
            false,
            false,
            "tough-tongue-meeting-bot-disabled",
            string.Empty,
            string.Empty,
            string.Empty);

        public Task<BuildGhostToughTongueMeetingBotResult> ScheduleAsync(
            BuildGhostToughTongueMeetingBotCommand command,
            CancellationToken cancellationToken)
        {
            Calls++;
            if (ThrowOnSchedule)
            {
                throw new HttpRequestException("ambiguous Tough Tongue outcome");
            }
            return Task.FromResult(Result);
        }
    }

    private sealed class ReceiptFile : IDisposable
    {
        private readonly string directory;

        private ReceiptFile(string directory, string path, string receiptDigest)
        {
            this.directory = directory;
            Path = path;
            ReceiptDigest = receiptDigest;
        }

        public string Path { get; }
        public string ReceiptDigest { get; }

        public static ReceiptFile Create(
            IReadOnlyList<string> meetingProviders,
            decimal availableMinutes = 2425m)
        {
            BuildGhostLiveSupportCapabilityReceipt unsigned = new(
                ToughTongueBuildGhostContractVersions.LiveSupportCapabilityReceiptV1,
                meetingProviders,
                Digest("account"),
                Digest("scenario"),
                ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
                Digest("avatar-binding"),
                true,
                true,
                availableMinutes,
                120m,
                2m,
                "tough-tongue-meeting-bot-photorealistic-canary",
                Now,
                900,
                string.Empty,
                string.Empty);
            string digest = BuildGhostLiveSupportService.DigestCapabilityReceipt(unsigned);
            BuildGhostLiveSupportCapabilityReceipt withDigest = unsigned with { ReceiptDigest = digest };
            string authorityMac = BuildGhostLiveSupportService.ComputeCapabilityReceiptAuthorityMac(
                withDigest,
                ReceiptAuthorityKey);
            BuildGhostLiveSupportCapabilityReceipt receipt = withDigest with { AuthorityMac = authorityMac };
            string directory = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"chummer-live-support-{Guid.NewGuid():N}");
            Directory.CreateDirectory(directory);
            string path = System.IO.Path.Combine(directory, "capability-receipt.json");
            File.WriteAllText(path, JsonSerializer.Serialize(receipt));
            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            }
            return new ReceiptFile(directory, path, digest);
        }

        public void Dispose()
        {
            if (Directory.Exists(directory))
            {
                Directory.Delete(directory, recursive: true);
            }
        }
    }
}
