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
await SupportCrashVerification.RunAsync();
InstallLinkingContinuationVerification.Run();
await StateStoreBackupVerification.RunAsync();
CompatibilityVerification.Run();
await HubApiRuntimeGuardrailVerification.RunAsync();
await CampaignSpineRestoreVerification.RunAsync();
await WorkspaceLifecycleRetentionVerification.RunAsync();
await HubRequestObservabilityVerification.RunAsync();
HubExtractionReadinessVerification.Run();

Console.WriteLine("run-services verification passed");
