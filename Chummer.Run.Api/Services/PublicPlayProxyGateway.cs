using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

public enum PublicPlayProxyDisposition
{
    NotMatched,
    Handled
}

public sealed record PublicPlayProjectionReadiness(
    string Status,
    bool Ready,
    bool Enabled,
    string Detail);

/// <summary>
/// Readiness seam for the retired public Play projection. The runsite serves a
/// complete local install shell and never projects remote HTML, CSS, scripts,
/// manifests, workers, or icons into its own origin.
/// </summary>
public sealed class PublicPlayProxyGateway(
    IConfiguration configuration,
    PublicCanonicalOriginPolicy publicOrigin,
    ILogger<PublicPlayProxyGateway> logger)
{
    public const string EnabledConfigurationKey = "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED";
    public const string UpstreamConfigurationKey = "CHUMMER_PUBLIC_PLAY_PROXY_URL";

    public bool Enabled => ReadBoolean(configuration[EnabledConfigurationKey]);

    public static IReadOnlyCollection<string> PublicPaths => Array.Empty<string>();

    public PublicPlayProjectionReadiness GetReadiness()
    {
        if (!Enabled)
        {
            return new PublicPlayProjectionReadiness(
                "disabled",
                Ready: true,
                Enabled: false,
                "Remote Play projection is off; local digest-pinned install mirrors are authoritative.");
        }

        if (!DormantPublicPlayProjectionConfigurationPolicy.TryResolveDormantOriginForReadiness(
                configuration,
                publicOrigin.CanonicalOrigin,
                out _))
        {
            return new PublicPlayProjectionReadiness(
                "projection_disabled_invalid_configuration",
                Ready: false,
                Enabled: true,
                "Remote Play projection was requested with invalid or recursive configuration. No outbound projection is possible; local install mirrors remain available.");
        }

        return new PublicPlayProjectionReadiness(
            "projection_retired_local_mirror_only",
            Ready: false,
            Enabled: true,
            "Remote Play projection was requested, but this edge publishes local install mirrors only. Disable the obsolete projection flag.");
    }

    public Task<PublicPlayProxyDisposition> TryHandleAsync(
        HttpContext context,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        _ = cancellationToken;
        if (Enabled)
        {
            logger.LogError(
                "Ignored obsolete public Play projection request for {Path}; local mirrors are authoritative.",
                context.Request.Path);
        }
        return Task.FromResult(PublicPlayProxyDisposition.NotMatched);
    }

    private static bool ReadBoolean(string? value)
        => string.Equals(value?.Trim(), "true", StringComparison.OrdinalIgnoreCase)
           || string.Equals(value?.Trim(), "1", StringComparison.OrdinalIgnoreCase)
           || string.Equals(value?.Trim(), "yes", StringComparison.OrdinalIgnoreCase);
}
