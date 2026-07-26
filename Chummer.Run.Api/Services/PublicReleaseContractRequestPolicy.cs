using Microsoft.AspNetCore.Http.Features;

namespace Chummer.Run.Api.Services;

internal static class PublicReleaseContractRequestPolicy
{
    private const string CurrentInstallPrefix = "/downloads/install/";
    private const string GenerationInstallPrefix = "/downloads/g/";

    internal static bool IsCanonicalCurrentCompanionPath(string path)
    {
        if (!path.StartsWith(CurrentInstallPrefix, StringComparison.Ordinal))
        {
            return false;
        }

        string remainder = path[CurrentInstallPrefix.Length..];
        int separator = remainder.IndexOf('/');
        return separator > 0
            && remainder.IndexOf('/', separator + 1) < 0
            && IsCanonicalArtifactId(remainder[..separator])
            && IsCompanionRole(remainder[(separator + 1)..]);
    }

    internal static bool IsCanonicalCurrentCompanionRequest(
        HttpRequest request,
        string artifactId,
        string role)
    {
        string? routeRole = ToCompanionRouteRole(role);
        return routeRole is not null
               && IsCanonicalArtifactId(artifactId)
               && IsExactCompanionRequestTarget(
                   request,
                   $"{CurrentInstallPrefix}{artifactId}/{routeRole}");
    }

    internal static bool IsCanonicalGenerationCompanionRequest(
        HttpRequest request)
    {
        string[] segments = (request.Path.Value ?? string.Empty)
            .Split('/', StringSplitOptions.RemoveEmptyEntries);
        return segments.Length == 6
               && segments[0] == "downloads"
               && segments[1] == "g"
               && segments[3] == "install"
               && IsCanonicalGenerationCompanionRequest(
                   request,
                   segments[2],
                   segments[4],
                   segments[5]);
    }

    internal static bool IsCanonicalGenerationCompanionRequest(
        HttpRequest request,
        string generationId,
        string artifactId,
        string role)
    {
        string? routeRole = ToCompanionRouteRole(role);
        return routeRole is not null
               && IsCanonicalGenerationId(generationId)
               && IsCanonicalArtifactId(artifactId)
               && IsExactCompanionRequestTarget(
                   request,
                   $"{GenerationInstallPrefix}{generationId}/install/{artifactId}/{routeRole}");
    }

    internal static bool IsCanonicalGenerationFileRequest(
        HttpRequest request,
        string generationId,
        string fileName)
        => IsCanonicalGenerationId(generationId)
           && IsCanonicalPortableFileName(fileName)
           && IsExactRequestTarget(
               request,
               $"{GenerationInstallPrefix}{generationId}/files/{fileName}");

    internal static bool IsCanonicalReleaseTruthRequest(
        HttpRequest request,
        string? generationId)
    {
        if (generationId is null)
        {
            return IsExactRequestTarget(
                request,
                "/api/v1/public/release-truth",
                "/api/public/release-truth");
        }

        return IsCanonicalGenerationId(generationId)
               && IsExactRequestTarget(
                   request,
                   $"/api/v1/public/release-truth/g/{generationId}",
                   $"/api/public/release-truth/g/{generationId}");
    }

    internal static bool IsCanonicalArtifactId(string value)
        => value.Length is > 0 and <= 128
           && value[0] is >= 'a' and <= 'z' or >= '0' and <= '9'
           && value.All(static character =>
               character is >= 'a' and <= 'z'
                   or >= '0' and <= '9'
                   or '-');

    internal static bool IsCanonicalGenerationId(string value)
        => value.Length is > 0 and <= 128
           && value[0] is >= 'A' and <= 'Z'
               or >= 'a' and <= 'z'
               or >= '0' and <= '9'
           && !value.Contains("..", StringComparison.Ordinal)
           && value.All(static character =>
               char.IsAsciiLetterOrDigit(character)
               || character is '.' or '_' or '-');

    private static bool IsCanonicalPortableFileName(string value)
        => value.Length is > 0 and <= 255
           && char.IsAsciiLetterOrDigit(value[0])
           && !value.Contains("..", StringComparison.Ordinal)
           && value.All(static character =>
               char.IsAsciiLetterOrDigit(character)
               || character is '.' or '_' or '+' or '-');

    private static bool IsCompanionRole(string value)
        => value is "payload" or "metadata";

    private static string? ToCompanionRouteRole(string value)
        => value switch
        {
            "payload" => "payload",
            "metadata" or "payload_metadata" => "metadata",
            _ => null
        };

    private static bool IsExactRequestTarget(
        HttpRequest request,
        params string[] expectedPaths)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (request.QueryString.HasValue)
        {
            return false;
        }

        string requestPath = request.Path.Value ?? string.Empty;
        if (!expectedPaths.Contains(requestPath, StringComparer.Ordinal))
        {
            return false;
        }

        string? rawTarget = request.HttpContext.Features
            .Get<IHttpRequestFeature>()?
            .RawTarget;
        return string.IsNullOrEmpty(rawTarget)
               || string.Equals(rawTarget, requestPath, StringComparison.Ordinal);
    }

    private static bool IsExactCompanionRequestTarget(
        HttpRequest request,
        string expectedPath)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!string.Equals(
                request.Path.Value,
                expectedPath,
                StringComparison.Ordinal)
            || !HasCanonicalCompanionQuery(request))
        {
            return false;
        }

        string expectedRawTarget = expectedPath + request.QueryString.Value;
        string? rawTarget = request.HttpContext.Features
            .Get<IHttpRequestFeature>()?
            .RawTarget;
        return string.IsNullOrEmpty(rawTarget)
               || string.Equals(
                   rawTarget,
                   expectedRawTarget,
                   StringComparison.Ordinal);
    }

    private static bool HasCanonicalCompanionQuery(HttpRequest request)
    {
        if (!request.QueryString.HasValue)
        {
            return true;
        }

        if (request.Query.Count != 1)
        {
            return false;
        }

        KeyValuePair<string, Microsoft.Extensions.Primitives.StringValues> entry =
            request.Query.Single();
        if (entry.Key is not ("ticket" or "claimCode")
            || entry.Value.Count != 1
            || string.IsNullOrWhiteSpace(entry.Value[0]))
        {
            return false;
        }

        string prefix = $"?{entry.Key}=";
        string rawQuery = request.QueryString.Value!;
        return rawQuery.StartsWith(prefix, StringComparison.Ordinal)
               && rawQuery.Length > prefix.Length
               && !rawQuery.AsSpan(prefix.Length).Contains('&');
    }
}
