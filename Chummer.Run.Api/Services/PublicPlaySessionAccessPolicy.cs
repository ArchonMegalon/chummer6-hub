using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

public sealed record PublicPlaySessionGrantRequest(
    string SubjectId,
    string Path,
    string Method,
    string? SessionId,
    PublicPlayPrivateRouteKind RouteKind = PublicPlayPrivateRouteKind.Unknown);

public enum PublicPlayPrivateRouteKind
{
    Unknown,
    BlazorCircuit,
    PlayApiRoot,
    TurnCompanion,
    TurnCompanionQueueStatus,
    TurnCompanionCommand,
    InstallRouteWithPrivateQuery
}

public sealed record PublicPlayPrivateRoute(
    PublicPlayPrivateRouteKind Kind,
    string Path,
    string? SessionId);

public interface IPublicPlayIdentityResolver
{
    Task<AuthenticatedHubSubject> RequireSubjectAsync(
        HttpRequest request,
        CancellationToken cancellationToken);
}

public sealed class HubPublicPlayIdentityResolver(HubIdentityClient identityClient) : IPublicPlayIdentityResolver
{
    public Task<AuthenticatedHubSubject> RequireSubjectAsync(
        HttpRequest request,
        CancellationToken cancellationToken)
        => identityClient.RequireSubjectAsync(request, cancellationToken);
}

public interface IPlaySessionGrantAuthorizer
{
    Task<bool> HasGrantAsync(
        PublicPlaySessionGrantRequest request,
        CancellationToken cancellationToken);
}

/// <summary>
/// Fail-closed placeholder used until Play session ids are mapped to authoritative Hub grants.
/// A shared upstream service key is deliberately not a user or session grant.
/// </summary>
public sealed class DenyAllPlaySessionGrantAuthorizer : IPlaySessionGrantAuthorizer
{
    public Task<bool> HasGrantAsync(
        PublicPlaySessionGrantRequest request,
        CancellationToken cancellationToken)
        => Task.FromResult(false);
}

public sealed class PublicPlaySessionAccessPolicy(
    IConfiguration configuration,
    IPublicPlayIdentityResolver identityResolver,
    IPlaySessionGrantAuthorizer grantAuthorizer) : IPublicPlaySessionAccessPolicy
{
    public const string LiveSessionProxyFeature = "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED";

    private static readonly HashSet<string> PublicInstallShellPaths = new(StringComparer.OrdinalIgnoreCase)
    {
        "/mobile",
        "/mobile/player",
        "/mobile/gm",
        "/mobile/observer",
        "/mobile/service-worker.js"
    };

    public bool LiveSessionProxyEnabled
        => bool.TryParse(configuration[LiveSessionProxyFeature], out bool enabled) && enabled;

    public static bool IsPublicQueryFreeInstallRequest(HttpRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (!HttpMethods.IsGet(request.Method) && !HttpMethods.IsHead(request.Method))
        {
            return false;
        }

        if (request.QueryString.HasValue || request.Query.Count != 0)
        {
            return false;
        }

        string path = NormalizePath(request.Path);
        return PublicInstallShellPaths.Contains(path);
    }

    public static bool RequiresSessionGrant(HttpRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string path = NormalizePath(request.Path);
        if (path.Equals("/_blazor", StringComparison.OrdinalIgnoreCase)
            || path.StartsWith("/_blazor/", StringComparison.OrdinalIgnoreCase)
            || path.Equals("/api/play", StringComparison.OrdinalIgnoreCase)
            || path.StartsWith("/api/play/", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (path.Equals("/mobile", StringComparison.OrdinalIgnoreCase)
            || path.StartsWith("/mobile/", StringComparison.OrdinalIgnoreCase))
        {
            return !IsPublicQueryFreeInstallRequest(request);
        }

        return false;
    }

    public async Task<bool> HasAccessAsync(HttpContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);

        if (!RequiresSessionGrant(context.Request))
        {
            return true;
        }

        // The capability is deliberately default-off. Enabling transport alone does not
        // grant access: identity and an authoritative server-side grant are still required.
        if (!LiveSessionProxyEnabled)
        {
            return false;
        }

        if (!TryResolvePrivateRoute(context.Request, out PublicPlayPrivateRoute? route) || route is null)
        {
            return false;
        }

        AuthenticatedHubSubject subject;
        try
        {
            subject = await identityResolver.RequireSubjectAsync(context.Request, cancellationToken)
                .ConfigureAwait(false);
        }
        catch (HubRequestAuthException)
        {
            return false;
        }

        var grantRequest = new PublicPlaySessionGrantRequest(
            subject.SubjectId,
            route.Path,
            context.Request.Method,
            route.SessionId,
            route.Kind);
        return await grantAuthorizer.HasGrantAsync(grantRequest, cancellationToken).ConfigureAwait(false);
    }

    public static bool TryResolvePrivateRoute(HttpRequest request, out PublicPlayPrivateRoute? route)
    {
        ArgumentNullException.ThrowIfNull(request);
        route = null;
        string path = NormalizePath(request.Path);

        if (path.Equals("/_blazor", StringComparison.OrdinalIgnoreCase)
            || path.StartsWith("/_blazor/", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (path.Equals("/mobile", StringComparison.OrdinalIgnoreCase)
            || path.StartsWith("/mobile/", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (!path.Equals("/api/play", StringComparison.OrdinalIgnoreCase)
            && !path.StartsWith("/api/play/", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (ContainsEncodedSeparatorOrTraversal(path)
            || !TryDecodeSegments(path, out string[] segments))
        {
            return false;
        }

        if (segments.Length is < 4 or > 5
            || !string.Equals(segments[2], "turn-companion", StringComparison.OrdinalIgnoreCase)
            || !IsValidSessionId(segments[3]))
        {
            return false;
        }

        string pathSessionId = segments[3];
        string? command = segments.Length == 5 ? segments[4].ToLowerInvariant() : null;
        PublicPlayPrivateRouteKind kind = command switch
        {
            null => PublicPlayPrivateRouteKind.TurnCompanion,
            "queue-status" => PublicPlayPrivateRouteKind.TurnCompanionQueueStatus,
            "replay" or "acknowledge" => PublicPlayPrivateRouteKind.TurnCompanionCommand,
            _ => PublicPlayPrivateRouteKind.Unknown
        };
        if (kind == PublicPlayPrivateRouteKind.Unknown
            || !IsAllowedMethod(kind, request.Method)
            || !HasOnlyAllowedQuery(request))
        {
            return false;
        }

        if (!TryResolveQuerySessionId(request, pathSessionId, out string? resolvedSessionId))
        {
            return false;
        }

        route = new PublicPlayPrivateRoute(kind, path, resolvedSessionId);
        return true;
    }

    public static async Task WriteUnavailableAsync(HttpContext context, CancellationToken cancellationToken)
        => await PublicPlayPrivateRouteResponse.WriteUnavailableAsync(context, cancellationToken).ConfigureAwait(false);

    private static string NormalizePath(PathString path)
    {
        string value = path.Value ?? string.Empty;
        if (value.Length > 1)
        {
            value = value.TrimEnd('/');
        }

        return string.IsNullOrEmpty(value) ? "/" : value;
    }

    private static bool TryResolveQuerySessionId(
        HttpRequest request,
        string? pathSessionId,
        out string? resolvedSessionId)
    {
        resolvedSessionId = pathSessionId;
        if (!request.Query.TryGetValue("sessionId", out var values))
        {
            return true;
        }

        if (values.Count != 1)
        {
            return false;
        }

        string querySessionId = values[0]?.Trim() ?? string.Empty;
        if (!IsValidSessionId(querySessionId))
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(pathSessionId)
            && !string.Equals(pathSessionId, querySessionId, StringComparison.Ordinal))
        {
            return false;
        }

        resolvedSessionId = querySessionId;
        return true;
    }

    private static bool ContainsEncodedSeparatorOrTraversal(string path)
        => path.Contains("%2f", StringComparison.OrdinalIgnoreCase)
           || path.Contains("%5c", StringComparison.OrdinalIgnoreCase)
           || path.Contains('\\')
           || path.Split('/', StringSplitOptions.RemoveEmptyEntries)
               .Any(static segment => segment is "." or "..");

    private static bool TryDecodeSegments(string path, out string[] segments)
    {
        try
        {
            segments = path.Split('/', StringSplitOptions.RemoveEmptyEntries)
                .Select(Uri.UnescapeDataString)
                .ToArray();
        }
        catch (UriFormatException)
        {
            segments = [];
            return false;
        }

        return segments.All(static segment => !string.IsNullOrWhiteSpace(segment)
            && !segment.Contains('/')
            && !segment.Contains('\\')
            && segment is not "." and not "..");
    }

    private static bool IsValidSessionId(string value)
        => value.Length is > 0 and <= 128
           && value.All(static character => char.IsAsciiLetterOrDigit(character)
               || character is '-' or '_' or '.');

    private static bool IsAllowedMethod(PublicPlayPrivateRouteKind kind, string method)
        => kind switch
        {
            PublicPlayPrivateRouteKind.TurnCompanion
                or PublicPlayPrivateRouteKind.TurnCompanionQueueStatus
                => HttpMethods.IsGet(method) || HttpMethods.IsHead(method),
            PublicPlayPrivateRouteKind.TurnCompanionCommand => HttpMethods.IsPost(method),
            _ => false
        };

    private static bool HasOnlyAllowedQuery(HttpRequest request)
    {
        var allowed = new HashSet<string>(["sessionId", "role", "deviceId"], StringComparer.OrdinalIgnoreCase);
        if (request.Query.Keys.Any(key => !allowed.Contains(key))
            || request.Query.Any(pair => pair.Value.Count != 1))
        {
            return false;
        }

        if (request.Query.TryGetValue("role", out var roles))
        {
            string role = roles[0]?.Trim() ?? string.Empty;
            if (role != "Player" && role != "GameMaster" && role != "Observer")
            {
                return false;
            }
        }

        if (request.Query.TryGetValue("deviceId", out var deviceIds))
        {
            string deviceId = deviceIds[0]?.Trim() ?? string.Empty;
            if (deviceId.Length is < 1 or > 128
                || deviceId.Any(static character => !char.IsAsciiLetterOrDigit(character)
                    && character != '-'
                    && character != '_'
                    && character != '.'
                    && character != ':'))
            {
                return false;
            }
        }

        return true;
    }
}
