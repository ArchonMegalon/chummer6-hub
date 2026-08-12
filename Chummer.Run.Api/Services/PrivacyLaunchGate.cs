using System.Text.Json.Nodes;

namespace Chummer.Run.Api.Services;

internal sealed record PrivacyLaunchGateSnapshot(
    string ContractName,
    int ContractVersion,
    string CapabilityContractName,
    int CapabilityContractVersion,
    string Status,
    bool ReviewRequired,
    string Scope,
    IReadOnlyList<string> Facts,
    IReadOnlyList<string> ProhibitedClaims,
    IReadOnlyList<string> BlockedClaims,
    string Reason)
{
    public bool BlocksReleaseSupportability =>
        ReviewRequired
        || !string.Equals(Status, "documented", StringComparison.OrdinalIgnoreCase);

    public JsonObject ToJsonObject()
        => new()
        {
            ["contractName"] = ContractName,
            ["contractVersion"] = ContractVersion,
            ["capabilityContractName"] = CapabilityContractName,
            ["capabilityContractVersion"] = CapabilityContractVersion,
            ["status"] = Status,
            ["reviewRequired"] = ReviewRequired,
            ["blocksLaunch"] = BlocksReleaseSupportability,
            ["scope"] = Scope,
            ["facts"] = new JsonArray(
                Facts.Select(static fact => JsonValue.Create(fact)).ToArray()),
            ["prohibitedClaims"] = new JsonArray(
                ProhibitedClaims.Select(static claim => JsonValue.Create(claim)).ToArray()),
            ["blockedClaims"] = new JsonArray(
                BlockedClaims.Select(static claim => JsonValue.Create(claim)).ToArray()),
            ["reason"] = Reason,
        };
}

internal static class PrivacyLaunchGate
{
    public const string ContractName = "chummer.privacy_launch_gate";
    public const int ContractVersion = 2;
    public const string HostedBuildCapabilityContractName = "chummer.hosted_build_privacy_lifecycle";
    public const int HostedBuildCapabilityContractVersion = 2;

    public const string ActiveRecordDelete = "active-record-delete";
    public const string AtomicDeletionJournal = "atomic-deletion-journal";
    public const string AutomaticDeletionReplay = "automatic-deletion-replay";
    public const string OwnerWorkspaceErasure = "owner-workspace-erasure";
    public const string MemoryOnlyRecovery = "memory-only-recovery";
    public const string ProductionRecoveryUnverified = "production-recovery-unverified";

    public const string PermanentDeleteClaim = "permanent-delete";
    public const string DurableRecoveryClaim = "durable-recovery";
    public const string AccountErasureClaim = "account-erasure";

    public static IReadOnlyList<string> HostedBuildFacts { get; } = Array.AsReadOnly(
    [
        ActiveRecordDelete,
        AtomicDeletionJournal,
        AutomaticDeletionReplay,
        OwnerWorkspaceErasure,
        MemoryOnlyRecovery,
        ProductionRecoveryUnverified
    ]);

    public static IReadOnlyList<string> HostedBuildProhibitedClaims { get; } = Array.AsReadOnly(
    [
        PermanentDeleteClaim,
        DurableRecoveryClaim,
        AccountErasureClaim
    ]);

    public const string HostedBuildReason =
        "Hosted Build now has atomic content-free deletion receipts, readiness replay, and owner-workspace erasure. Launch remains blocked until the journal is proven to survive independently across production backup recovery and whole-account erasure is implemented across every account-owned store.";

    public static PrivacyLaunchGateSnapshot Current { get; } = new(
        ContractName,
        ContractVersion,
        HostedBuildCapabilityContractName,
        HostedBuildCapabilityContractVersion,
        Status: "review_required",
        ReviewRequired: true,
        Scope: "flagship_launch_and_release_supportability",
        Facts: HostedBuildFacts,
        ProhibitedClaims: HostedBuildProhibitedClaims,
        BlockedClaims:
        [
            "flagship_launch",
            "public_release_supportability",
            "hosted_build_recovery_and_erasure"
        ],
        Reason: HostedBuildReason);

    internal static PrivacyLaunchGateSnapshot ClearForTests { get; } = new(
        ContractName,
        ContractVersion,
        HostedBuildCapabilityContractName,
        HostedBuildCapabilityContractVersion,
        Status: "documented",
        ReviewRequired: false,
        Scope: "flagship_launch_and_release_supportability",
        Facts: [],
        ProhibitedClaims: [],
        BlockedClaims: [],
        Reason: "Hosted Build privacy, retention, recovery, and erasure policy is launch-approved and production-verified.");
}
