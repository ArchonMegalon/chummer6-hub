using Chummer.Contracts.Content;

namespace Chummer.Contracts.Hub;

public static class HubProjectInstallPreviewStates
{
    public const string Ready = "ready";
    public const string Deferred = "deferred";
}

public static class HubProjectInstallPreviewChangeKinds
{
    public const string RuntimeLockPinned = RuleProfilePreviewChangeKinds.RuntimeLockPinned;
    public const string RulePackSelectionChanged = RuleProfilePreviewChangeKinds.RulePackSelectionChanged;
    public const string SessionReplayRequired = RuleProfilePreviewChangeKinds.SessionReplayRequired;
    public const string InstallStateChanged = RulePackInstallPreviewChangeKinds.InstallStateChanged;
    public const string RuntimeReviewRequired = RulePackInstallPreviewChangeKinds.RuntimeReviewRequired;
    public const string InstallDeferred = "install-deferred";
}

public static class HubProjectInstallPreviewDiagnosticKinds
{
    public const string Trust = "trust";
    public const string ProviderBinding = "provider-binding";
    public const string Installability = "installability";
    public const string InstallState = "install-state";
}

public static class HubProjectInstallPreviewDiagnosticSeverityLevels
{
    public const string Info = "info";
    public const string Warning = "warning";
    public const string Error = "error";
}

public sealed record HubProjectInstallPreviewChange(
    string Kind,
    string Summary,
    string SubjectId,
    bool RequiresConfirmation = false);

public sealed record HubProjectInstallPreviewDiagnostic(
    string Kind,
    string Severity,
    string Message,
    string? SubjectId = null);

public sealed record HubProjectInstallPreviewReceipt(
    string Kind,
    string ItemId,
    RuleProfileApplyTarget Target,
    string State,
    IReadOnlyList<HubProjectInstallPreviewChange> Changes,
    IReadOnlyList<HubProjectInstallPreviewDiagnostic> Diagnostics,
    string? RuntimeFingerprint = null,
    bool RequiresConfirmation = false,
    string? DeferredReason = null);
