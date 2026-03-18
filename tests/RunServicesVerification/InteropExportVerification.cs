using Chummer.Run.AI.Services.Interop;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Play.Contracts.Interop;
using Chummer.Run.Contracts.Ops;

namespace RunServicesVerification;

internal static class InteropExportVerification
{
    public static Task RunAsync()
    {
        var ledger = new SessionLedgerService();
        var outbox = new DeliveryOutboxService();
        var ops = new GmOpsBoardService(ledger, outbox);
        var interop = new InteropExportService(ops);

        ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
            CampaignId: "campaign_interop",
            SessionId: "session_interop",
            SceneId: "scene_interop",
            Title: "Interop prep checklist",
            Kind: GmPrepAssetKind.Checklist,
            Audience: GmPrepAssetAudience.GameMaster,
            Summary: "Prep for export validation",
            Body: "Confirm all assets before export.",
            Tags: ["interop", "prep"],
            ChecklistItems:
            [
                new GmPrepChecklistItem("interop-1", "Validate export manifest")
            ],
            SourceEventIds: Array.Empty<string>(),
            CreatedBy: "gm.interop",
            RuntimeFingerprint: "interop:fp"));

        var package = interop.Export(new InteropExportRequest(
            CampaignId: "campaign_interop",
            SessionId: "session_interop",
            RequestedBy: "gm.interop"));

        VerificationAssert.Equal("interop_export_v1", package.ContractFamily, "Interop export must use the canonical family.");
        VerificationAssert.True(package.Manifest.TotalCount >= 5, "Interop export should include all requested families.");
        VerificationAssert.True(package.Manifest.CharacterCount >= 1, "Interop export should include character assets.");
        VerificationAssert.True(package.Manifest.NpcCount >= 1, "Interop export should include NPC assets.");
        VerificationAssert.True(package.Manifest.SessionCount >= 1, "Interop export should include session assets.");
        VerificationAssert.True(package.Manifest.EncounterCount >= 1, "Interop export should include encounter assets.");
        VerificationAssert.True(package.Manifest.PrepCount >= 1, "Interop export should include prep assets.");

        var import = interop.Import(new InteropImportRequest(package, ImportedBy: "gm.interop"));
        VerificationAssert.Equal(package.Manifest.TotalCount, import.ImportedCount, "Interop import should accept untampered payloads.");
        VerificationAssert.Equal(0, import.RejectedCount, "Interop import should not reject untampered payloads.");
        VerificationAssert.True(import.ProvenanceRoundTrip, "Interop import should preserve round-trip provenance.");

        var tamperedFirst = package.Assets[0] with { PayloadJson = package.Assets[0].PayloadJson + " " };
        var tamperedAssets = package.Assets.ToArray();
        tamperedAssets[0] = tamperedFirst;
        var tamperedPackage = package with { Assets = tamperedAssets };

        var tamperedImport = interop.Import(new InteropImportRequest(tamperedPackage, ImportedBy: "gm.interop"));
        VerificationAssert.True(tamperedImport.RejectedCount >= 1, "Tampered interop payloads must be rejected.");
        VerificationAssert.True(!tamperedImport.ProvenanceRoundTrip, "Tampered interop payloads should fail round-trip provenance checks.");

        var roundTrip = interop.RoundTrip(new InteropRoundTripRequest(
            Export: new InteropExportRequest(
                CampaignId: "campaign_interop",
                SessionId: "session_interop",
                RequestedBy: "gm.interop"),
            ImportedBy: "gm.interop"));
        VerificationAssert.True(roundTrip.ProvenanceRoundTrip, "Round-trip endpoint should preserve provenance for canonical payloads.");

        return Task.CompletedTask;
    }
}
