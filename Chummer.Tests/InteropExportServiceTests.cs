using Chummer.Play.Contracts.Interop;
using Chummer.Run.AI.Services.Interop;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Xunit;

namespace Chummer.Tests;

public sealed class InteropExportServiceTests
{
    [Fact]
    public void Export_campaign_scope_infers_session_binding_from_session_assets()
    {
        var service = CreateService();

        InteropExportPackage package = service.Export(new InteropExportRequest(
            CampaignId: "campaign_infer"));

        Assert.Equal("session_default", package.SessionId);
        Assert.Equal("chummer.portable-campaign-session.v1", package.Compatibility.FormatId);
        Assert.Equal(InteropCompatibilityStates.Compatible, package.Compatibility.CompatibilityState);
        Assert.Contains(package.Compatibility.Notes, static note => string.Equals(note.Code, "session-binding-inferred", StringComparison.Ordinal));
        Assert.DoesNotContain(package.Compatibility.Notes, static note => string.Equals(note.Code, "session-binding-required-for-replace", StringComparison.Ordinal));
        Assert.Contains(
            package.Assets.SelectMany(static asset => asset.Provenance.Pointers),
            static pointer => string.Equals(pointer.Kind, "session", StringComparison.Ordinal)
                && string.Equals(pointer.Reference, "session_default", StringComparison.Ordinal));
    }

    [Fact]
    public void Export_character_only_campaign_scope_keeps_unpinned_session_warning()
    {
        var service = CreateService();

        InteropExportPackage package = service.Export(new InteropExportRequest(
            CampaignId: "campaign_unbound",
            AssetKinds: [InteropAssetKind.Character]));

        Assert.Null(package.SessionId);
        Assert.Equal("chummer.portable-campaign.v1", package.Compatibility.FormatId);
        Assert.Equal(InteropCompatibilityStates.CompatibleWithWarnings, package.Compatibility.CompatibilityState);
        Assert.Contains(package.Compatibility.Notes, static note => string.Equals(note.Code, "session-binding-required-for-replace", StringComparison.Ordinal));
        Assert.DoesNotContain(package.Compatibility.Notes, static note => string.Equals(note.Code, "session-binding-inferred", StringComparison.Ordinal));
    }

    private static InteropExportService CreateService()
    {
        var opsBoard = new GmOpsBoardService(new SessionLedgerService(), new DeliveryOutboxService());
        return new InteropExportService(opsBoard);
    }
}
