using System.IO;
using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerDispatchTests
{
    private static IConfiguration BuildSeedConfiguration()
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = Path.GetFullPath(Path.Combine(
                    "/docker/chummercomplete",
                    "chummer-hub-registry",
                    "black-ledger",
                    "worlds",
                    "emerald-sprawl-prelude.yaml")),
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(Path.GetTempPath(), $"chummer-dispatch-test-{Guid.NewGuid():N}.json"),
            })
            .Build();

    [Fact]
    public void BlackLedgerDispatch_turn_route_family_and_faction_filter_exist()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerController = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LedgerController.cs"));

        Assert.Contains("[HttpGet(\"/ledger/turns/{turn}/dispatches\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/factions/{factionId}/dispatches\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"dispatches\")]", ledgerController, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"dispatches/{dispatchId}/approve\")]", ledgerController, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerDispatch_seeded_turn_one_records_include_required_fixtures()
    {
        var service = new BlackLedgerPublicStatsService(BuildSeedConfiguration());
        var dispatches = service.ListDispatches(1);

        Assert.Contains(dispatches, item => item.DispatchId == "dispatch_turn_0001_main");
        Assert.Contains(dispatches, item => item.DispatchId == "dispatch_turn_0001_rust_market_old_favors");
        Assert.Contains(dispatches, item => item.DispatchId == "dispatch_turn_0001_ashline_source_clarity");
        Assert.Contains(dispatches, item => item.DispatchId == "dispatch_turn_0001_ghostline_rumor_suppressed");
        Assert.Contains(dispatches, item => item.DispatchId == "dispatch_turn_0001_neon_docks_drone_pressure");
        Assert.All(dispatches, item => Assert.Equal("ledger_tick_0001_preseeded", item.SourceReceiptId));
    }

    [Fact]
    public void BlackLedgerDispatch_detail_lookup_infers_turn_from_generated_dispatch_id()
    {
        var service = new BlackLedgerPublicStatsService(BuildSeedConfiguration());

        var dispatch = service.LoadDispatch("ledger_dispatch_emerald-sprawl-prelude_turn_0002");

        Assert.NotNull(dispatch);
        Assert.Equal("ledger_dispatch_emerald-sprawl-prelude_turn_0002", dispatch!.DispatchId);
        Assert.Equal(2, dispatch.Turn);
        Assert.Equal("ledger_tick_0002_flagship_seeded", dispatch.SourceReceiptId);
    }

    [Fact]
    public void BlackLedgerDispatch_faction_archive_filters_to_requested_faction()
    {
        var service = new BlackLedgerPublicStatsService(BuildSeedConfiguration());
        var dispatches = service.ListDispatches(1, "ashline-circle");

        Assert.NotEmpty(dispatches);
        Assert.All(dispatches, item => Assert.Contains(item.InvolvedFactions, faction =>
            string.Equals(faction, "Ashline Circle", StringComparison.OrdinalIgnoreCase)));
    }

    [Fact]
    public void BlackLedgerDispatch_email_digest_is_receipt_backed()
    {
        var configuration = BuildSeedConfiguration();
        var service = new BlackLedgerDispatchService(
            new CommunityStore(configuration, NullLogger<CommunityStore>.Instance),
            new BlackLedgerPublicStatsService(configuration),
            NullLogger<BlackLedgerDispatchService>.Instance);
        var digest = service.BuildDispatchEmailDigest(1);

        Assert.NotNull(digest);
        Assert.False(string.IsNullOrWhiteSpace(digest!.Title));
        Assert.Contains("/ledger/dispatches/", digest.DispatchUrl, StringComparison.Ordinal);
        Assert.Contains("/ledger/turns/1", digest.SourceReceiptUrl, StringComparison.Ordinal);
        Assert.Contains("public-safe", digest.PrivacyNote, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BlackLedgerDispatch_operator_workflow_creates_gate_and_publication_receipts()
    {
        var configuration = BuildSeedConfiguration();
        var service = new BlackLedgerDispatchService(
            new CommunityStore(configuration, NullLogger<CommunityStore>.Instance),
            new BlackLedgerPublicStatsService(configuration),
            NullLogger<BlackLedgerDispatchService>.Instance);

        BlackLedgerDispatchMutationResult draftResult = service.CreateDraft(new CreateBlackLedgerDispatchRequest(
            WorldId: "emerald-sprawl-prelude",
            Turn: 1,
            DispatchId: "dispatch_turn_0001_main",
            Adapter: "deterministic_template",
            AutoApproveSeededPreview: false,
            Reviewer: "operator"));

        Assert.Equal("draft_only", draftResult.Draft.Status);
        Assert.Equal("pass", draftResult.GateReceipt.Status);
        Assert.Null(draftResult.PublicationReceipt);

        BlackLedgerDispatchMutationResult approvalResult = service.ApproveDispatch(
            "dispatch_turn_0001_main",
            new ApproveBlackLedgerDispatchRequest("operator"));

        Assert.NotNull(approvalResult.ApprovalReceipt);
        Assert.Equal("approved", approvalResult.ApprovalReceipt!.Status);
        Assert.NotNull(approvalResult.PublicationReceipt);
        Assert.NotNull(approvalResult.PublishedDispatch);
        Assert.Equal("dispatch_turn_0001_main", approvalResult.PublishedDispatch!.DispatchId);
    }
}
