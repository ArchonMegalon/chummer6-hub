using RunServicesVerification;

await RelayVerification.RunAsync();
PublicationVerification.Run();
RuntimeBundleVerification.Run();
await ApprovalAndMediaVerification.RunAsync();
await SessionMemoryIngestionVerification.RunAsync();
await GmOpsBoardVerification.RunAsync();
await InteropExportVerification.RunAsync();
await OfflineSyncVerification.RunAsync();
await PipelineProjectionVerification.RunAsync();
await StateStoreBackupVerification.RunAsync();
CompatibilityVerification.Run();
HubExtractionReadinessVerification.Run();

Console.WriteLine("run-services verification passed");
