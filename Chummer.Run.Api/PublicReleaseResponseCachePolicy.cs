using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api;

internal enum VerifiedImmutableGenerationRouteKind
{
    File,
    Companion
}

internal static class PublicReleaseResponseCachePolicy
{
    internal const string ImmutableCacheControl =
        "public, max-age=31536000, immutable";

    private static readonly object VerifiedImmutableGenerationResponseKey = new();
    private static readonly string[] CredentialOrVariantRequestHeaders =
    [
        "Authorization",
        "Cookie",
        "Proxy-Authorization",
        "Range",
        "If-Match",
        "If-None-Match",
        "If-Modified-Since",
        "If-Unmodified-Since",
        "If-Range",
        PublicReleaseTruthProjectionMiddleware.StagedProbeHeaderName
    ];
    private static readonly string[] PersonalizedOrVariantResponseHeaders =
    [
        "Content-Range",
        "Location",
        "Set-Cookie",
        "WWW-Authenticate"
    ];
    private static readonly string[] ConflictingNoStoreHeaders =
    [
        "CDN-Cache-Control",
        "Cloudflare-CDN-Cache-Control",
        "Surrogate-Control",
        "Pragma",
        "Expires"
    ];

    internal static async Task InvokeNoStoreBoundaryAsync(
        HttpContext context,
        Func<Task> next,
        bool requiresNoStore)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(next);
        if (requiresNoStore)
        {
            context.Response.OnStarting(
                static state =>
                {
                    var httpContext = (HttpContext)state;
                    if (!CanPreserveVerifiedImmutableGenerationResponse(httpContext))
                    {
                        PrivateResponseCacheHeaders.Apply(httpContext.Response.Headers);
                    }

                    return Task.CompletedTask;
                },
                context);
        }

        await next();
    }

    internal static void MarkVerifiedImmutableGenerationResponse(
        HttpContext context,
        ArtifactDeliveryBinding binding,
        FileStreamResult result,
        VerifiedImmutableGenerationRouteKind routeKind)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(binding);
        ArgumentNullException.ThrowIfNull(result);

        string? generationId = binding.Snapshot.GenerationId;
        string? contentType = result.ContentType;
        if (string.IsNullOrWhiteSpace(generationId)
            || string.IsNullOrWhiteSpace(contentType)
            || binding.SizeBytes <= 0)
        {
            context.Items.Remove(VerifiedImmutableGenerationResponseKey);
            return;
        }

        context.Items[VerifiedImmutableGenerationResponseKey] =
            new VerifiedImmutableGenerationResponse(
                generationId,
                binding.ArtifactId,
                binding.Role,
                binding.FileName,
                binding.SizeBytes,
                contentType,
                routeKind);
    }

    private static bool CanPreserveVerifiedImmutableGenerationResponse(
        HttpContext context)
    {
        if (!context.Items.TryGetValue(
                VerifiedImmutableGenerationResponseKey,
                out object? value)
            || value is not VerifiedImmutableGenerationResponse proof
            || (!HttpMethods.IsGet(context.Request.Method)
                && !HttpMethods.IsHead(context.Request.Method))
            || context.Request.QueryString.HasValue
            || context.Request.Query.Count != 0
            || CredentialOrVariantRequestHeaders.Any(
                context.Request.Headers.ContainsKey)
            || context.Response.StatusCode != StatusCodes.Status200OK
            || context.Response.ContentLength != proof.SizeBytes
            || proof.SizeBytes <= 0
            || !string.Equals(
                context.Response.ContentType,
                proof.ContentType,
                StringComparison.Ordinal)
            || !HasSingleExactHeader(
                context.Response.Headers,
                "Cache-Control",
                ImmutableCacheControl)
            || !HasSingleExactHeader(
                context.Response.Headers,
                "X-Chummer-Release-Generation",
                proof.GenerationId)
            || PersonalizedOrVariantResponseHeaders.Any(
                context.Response.Headers.ContainsKey)
            || ConflictingNoStoreHeaders.Any(
                context.Response.Headers.ContainsKey))
        {
            return false;
        }

        string? rawTarget = context.Request.HttpContext.Features
            .Get<IHttpRequestFeature>()?
            .RawTarget;
        if (string.IsNullOrEmpty(rawTarget))
        {
            return false;
        }

        return proof.RouteKind switch
        {
            VerifiedImmutableGenerationRouteKind.File =>
                PublicReleaseContractRequestPolicy
                    .IsCanonicalGenerationFileRequest(
                        context.Request,
                        proof.GenerationId,
                        proof.FileName)
                && string.Equals(
                    rawTarget,
                    $"/downloads/g/{proof.GenerationId}/files/{proof.FileName}",
                    StringComparison.Ordinal),
            VerifiedImmutableGenerationRouteKind.Companion =>
                IsCanonicalGenerationCompanionResponse(
                    context.Request,
                    proof,
                    rawTarget),
            _ => false
        };
    }

    private static bool IsCanonicalGenerationCompanionResponse(
        HttpRequest request,
        VerifiedImmutableGenerationResponse proof,
        string rawTarget)
    {
        string? routeRole = proof.Role switch
        {
            ArtifactDeliveryRoles.Payload => "payload",
            ArtifactDeliveryRoles.PayloadMetadata => "metadata",
            _ => null
        };
        string? expectedContentType = proof.Role switch
        {
            ArtifactDeliveryRoles.Payload => "application/octet-stream",
            ArtifactDeliveryRoles.PayloadMetadata =>
                "application/json; charset=utf-8",
            _ => null
        };
        if (routeRole is null
            || expectedContentType is null
            || !string.Equals(
                proof.ContentType,
                expectedContentType,
                StringComparison.Ordinal)
            || request.HttpContext.Response.Headers.ContainsKey(
                "Content-Disposition"))
        {
            return false;
        }

        string expectedPath =
            $"/downloads/g/{proof.GenerationId}/install/{proof.ArtifactId}/{routeRole}";
        return PublicReleaseContractRequestPolicy
                   .IsCanonicalGenerationCompanionRequest(
                       request,
                       proof.GenerationId,
                       proof.ArtifactId,
                       proof.Role)
               && string.Equals(
                   rawTarget,
                   expectedPath,
                   StringComparison.Ordinal);
    }

    private static bool HasSingleExactHeader(
        IHeaderDictionary headers,
        string name,
        string expected)
        => headers.TryGetValue(name, out var values)
           && values.Count == 1
           && string.Equals(values[0], expected, StringComparison.Ordinal);

    private sealed record VerifiedImmutableGenerationResponse(
        string GenerationId,
        string ArtifactId,
        string Role,
        string FileName,
        long SizeBytes,
        string ContentType,
        VerifiedImmutableGenerationRouteKind RouteKind);
}
