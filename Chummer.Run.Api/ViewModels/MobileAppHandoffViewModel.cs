using System;

namespace Chummer.Run.Api.ViewModels;

public enum MobileAppHandoffTarget
{
    Build,
    Play
}

public sealed record MobileAppHandoffViewModel(
    string Id,
    MobileAppHandoffTarget Target,
    string Eyebrow,
    string Heading,
    string Description,
    string QrAriaLabel,
    string LinkLabel,
    string OpenLabel,
    string OpenAnalyticsEvent)
{
    public string Path => Target switch
    {
        MobileAppHandoffTarget.Build => "/build",
        MobileAppHandoffTarget.Play => "/mobile/player",
        _ => throw new InvalidOperationException("Unsupported mobile app handoff target.")
    };
}
