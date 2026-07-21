using System.Reflection;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Ledger;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.AspNetCore.Mvc;
using Xunit;

namespace Chummer.Tests;

public sealed class LedgerServiceTests
{
    [Fact]
    public void Controller_maps_missing_group_ingest_to_not_found()
    {
        var controller = new LedgerController(
            null!,
            null!,
            null!,
            null!,
            null!,
            null!,
            null!,
            null!,
            null!);
        var missingGroup = new KeyNotFoundException("Contribution receipt group was not found.");
        MethodInfo isMapped = typeof(LedgerController).GetMethod(
            "IsMappedIngestException",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("IsMappedIngestException was not found.");
        MethodInfo mapException = typeof(LedgerController).GetMethod(
            "MapIngestException",
            BindingFlags.NonPublic | BindingFlags.Instance)
            ?? throw new InvalidOperationException("MapIngestException was not found.");

        Assert.True(Assert.IsType<bool>(isMapped.Invoke(null, [missingGroup])));
        ActionResult result = Assert.IsAssignableFrom<ActionResult>(mapException.Invoke(controller, [missingGroup]));
        NotFoundObjectResult notFound = Assert.IsType<NotFoundObjectResult>(result);
        Assert.Equal(missingGroup.Message, notFound.Value);
    }

    [Fact]
    public void Ingest_canonicalizes_contribution_receipts_with_runtime_envelope_defaults()
    {
        CommunityStore store = CreateStore();
        AccountService accounts = new(store);
        GroupService groups = new(store, accounts);
        HubUserDto owner = accounts.EnsureUser("subject-a", "User A");
        GroupDto group = groups.CreateGroup(new CreateGroupRequest(
            SubjectId: owner.SubjectId,
            Name: "Group A",
            GroupType: "booster",
            Visibility: "group",
            Capabilities: null));
        LedgerService service = new(store, new RewardService(store), new EntitlementService(store));

        ReceiptIngestResultDto result = service.Ingest(new ContributionReceiptDto(
            ReceiptId: " rcpt-1 ",
            EventKind: " slice_landed ",
            LaneId: " lane-a ",
            ProjectId: " proj-a ",
            UserId: $" {owner.UserId} ",
            GroupId: $" {group.GroupId} ",
            SponsorSessionId: null,
            ParticipantCodexCode: null,
            AuthClass: " operator ",
            LaneType: " direct ",
            Verified: true));

        Assert.Equal("ingested", result.Status);
        ContributionReceiptDto receipt = Assert.Single(store.Receipts);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal(ReceiptProvenanceClasses.Runtime, receipt.Envelope!.ProvenanceClass);
        Assert.Equal(ReceiptExposureClasses.SignedIn, receipt.Envelope.ExposureClass);
        Assert.Equal(ReceiptLifecycleStates.Verified, receipt.Envelope.LifecycleState);
        Assert.Equal("community.group", receipt.Envelope.OwnerScope);
        Assert.Equal("community_contribution", receipt.Envelope.ReceiptKind);
        Assert.Equal("verified", receipt.Envelope.ReviewState);
        Assert.Equal("rcpt-1", receipt.Envelope.EvidenceRef);
        Assert.Equal("rcpt-1", receipt.ReceiptId);
        Assert.Equal("slice_landed", receipt.EventKind);
        Assert.Equal("lane-a", receipt.LaneId);
        Assert.Equal("proj-a", receipt.ProjectId);
        Assert.Equal(owner.UserId, receipt.UserId);
        Assert.Equal(group.GroupId, receipt.GroupId);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Ingest_rejects_missing_or_deleted_group_without_mutating_state(bool deleteExistingGroup)
    {
        CommunityStore store = CreateStore(out string storagePath);
        AccountService accounts = new(store);
        HubUserDto owner = accounts.EnsureUser("subject-a", "User A");
        string groupId = "group-missing";
        if (deleteExistingGroup)
        {
            GroupService groups = new(store, accounts);
            GroupDto group = groups.CreateGroup(new CreateGroupRequest(
                SubjectId: owner.SubjectId,
                Name: "Deleted Group",
                GroupType: "booster",
                Visibility: "group",
                Capabilities: null));
            groupId = group.GroupId;
            lock (store.Gate)
            {
                store.GroupsById.Remove(group.GroupId);
                store.PersistLocked();
            }
        }

        byte[] durableStateBefore = File.ReadAllBytes(storagePath);
        LedgerService service = new(store, new RewardService(store), new EntitlementService(store));
        var receipt = new ContributionReceiptDto(
            ReceiptId: "rcpt-rejected",
            EventKind: "slice_landed",
            LaneId: "lane-a",
            ProjectId: "proj-a",
            UserId: owner.UserId,
            GroupId: groupId,
            SponsorSessionId: null,
            ParticipantCodexCode: null,
            AuthClass: "operator",
            LaneType: "direct",
            Verified: true);

        KeyNotFoundException exception = Assert.Throws<KeyNotFoundException>(() => service.Ingest(receipt));

        Assert.Contains(groupId, exception.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Empty(store.Receipts);
        Assert.Empty(store.LedgerEntries);
        Assert.Empty(store.RewardEntries);
        Assert.Empty(store.EntitlementEntries);
        Assert.Empty(store.Badges);
        Assert.Equal(durableStateBefore, File.ReadAllBytes(storagePath));
    }

    [Fact]
    public void Ingest_rolls_back_all_derived_state_when_persistence_fails()
    {
        CommunityStore store = CreateStore(out string storagePath);
        AccountService accounts = new(store);
        GroupService groups = new(store, accounts);
        HubUserDto owner = accounts.EnsureUser("subject-a", "User A");
        GroupDto group = groups.CreateGroup(new CreateGroupRequest(
            SubjectId: owner.SubjectId,
            Name: "Group A",
            GroupType: "booster",
            Visibility: "group",
            Capabilities: null));
        byte[] durableStateBefore = File.ReadAllBytes(storagePath);
        LedgerService service = new(store, new RewardService(store), new EntitlementService(store));
        var receipt = new ContributionReceiptDto(
            ReceiptId: "rcpt-persistence-failure",
            EventKind: "slice_landed",
            LaneId: "lane-a",
            ProjectId: "proj-a",
            UserId: owner.UserId,
            GroupId: group.GroupId,
            SponsorSessionId: null,
            ParticipantCodexCode: "participant-a",
            AuthClass: "operator",
            LaneType: "direct",
            Verified: true,
            ParticipantTotalTokens: 100);
        store.LedgerPersistenceFaultInjector = () => throw new IOException("injected persistence failure");

        Assert.Throws<IOException>(() => service.Ingest(receipt));

        Assert.Empty(store.Receipts);
        Assert.Empty(store.LedgerEntries);
        Assert.Empty(store.RewardEntries);
        Assert.Empty(store.EntitlementEntries);
        Assert.Empty(store.Badges);
        Assert.Equal(durableStateBefore, File.ReadAllBytes(storagePath));

        store.LedgerPersistenceFaultInjector = null;
        ReceiptIngestResultDto retry = service.Ingest(receipt);
        Assert.Equal("ingested", retry.Status);
        Assert.Single(store.Receipts);
        Assert.Single(store.LedgerEntries);
        Assert.Single(store.RewardEntries);
        Assert.NotEmpty(store.EntitlementEntries);
        Assert.NotEmpty(store.Badges);
    }

    [Fact]
    public void Ingest_grants_threshold_entitlement_only_after_persisted_reward_total_reaches_threshold()
    {
        CommunityStore store = CreateStore();
        AccountService accounts = new(store);
        GroupService groups = new(store, accounts);
        HubUserDto owner = accounts.EnsureUser("subject-a", "User A");
        GroupDto group = groups.CreateGroup(new CreateGroupRequest(
            SubjectId: owner.SubjectId,
            Name: "Group A",
            GroupType: "booster",
            Visibility: "group",
            Capabilities: null));
        LedgerService service = new(store, new RewardService(store), new EntitlementService(store));
        var receipt = new ContributionReceiptDto(
            ReceiptId: "rcpt-landed",
            EventKind: "slice_landed",
            LaneId: "lane-a",
            ProjectId: "proj-a",
            UserId: owner.UserId,
            GroupId: group.GroupId,
            SponsorSessionId: null,
            ParticipantCodexCode: null,
            AuthClass: "operator",
            LaneType: "direct",
            Verified: true);

        service.Ingest(receipt);
        Assert.DoesNotContain(store.EntitlementEntries, entry => entry.Key == "gm-tools-waitlist-priority");
        service.Ingest(receipt with { ReceiptId = "rcpt-reviewed-1", EventKind = "slice_reviewed" });
        Assert.DoesNotContain(store.EntitlementEntries, entry => entry.Key == "gm-tools-waitlist-priority");
        service.Ingest(receipt with { ReceiptId = "rcpt-reviewed-2", EventKind = "slice_reviewed" });
        Assert.Contains(store.EntitlementEntries, entry => entry.Key == "gm-tools-waitlist-priority");
    }

    private static CommunityStore CreateStore()
        => CreateStore(out _);

    private static CommunityStore CreateStore(out string storagePath)
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-ledger-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        storagePath = Path.Combine(root, "community.json");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = storagePath
            })
            .Build();
        return new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
    }
}
