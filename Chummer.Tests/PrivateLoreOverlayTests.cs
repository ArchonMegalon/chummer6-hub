using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class PrivateLoreOverlayTests
{
    [Fact]
    public void PrivateLoreOverlay_route_and_public_blocking_contract_exist()
    {
        string ledgerApi = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LedgerController.cs"));
        string policy = File.ReadAllText(RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "BLACK_LEDGER_PRIVATE_LORE_OVERLAY_SPEC.md"));

        Assert.Contains("/api/v1/account/campaigns/{campaignId}/ledger/private-lore-overlay", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("public_projection_allowed = false", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("Public routes must never render them", policy, StringComparison.Ordinal);
    }
}
