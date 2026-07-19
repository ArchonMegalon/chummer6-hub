using Microsoft.AspNetCore.Http.Features;

namespace Chummer.Run.Api.Services;

public enum PublicProjectionProofRequestPathDisposition
{
    NotGoverned,
    Canonical,
    RejectVariant
}

/// <summary>
/// Keeps authenticated public-projection proofs on their controller routes.
/// Equivalent but non-canonical request targets are rejected before routing or
/// static-file lookup so path normalization cannot expose legacy bytes.
/// </summary>
public static class PublicProjectionProofRequestPathPolicy
{
    public const string CurrentProofPath =
        "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json";
    public const string LegacyCompatibilityProofPath =
        "/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json";

    private static readonly string[] CanonicalPaths =
    [
        CurrentProofPath,
        LegacyCompatibilityProofPath
    ];

    public static PublicProjectionProofRequestPathDisposition Evaluate(HttpRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string requestPath = request.Path.Value ?? string.Empty;
        string rawTarget = request.HttpContext.Features.Get<IHttpRequestFeature>()?.RawTarget
                           ?? requestPath;
        int queryIndex = rawTarget.IndexOf('?');
        string rawPath = queryIndex >= 0 ? rawTarget[..queryIndex] : rawTarget;

        string? normalizedRaw = NormalizeEquivalentPath(rawPath);
        string? normalizedRequest = NormalizeEquivalentPath(requestPath);
        string? matchedCanonical = CanonicalPaths.FirstOrDefault(
            canonical => string.Equals(normalizedRaw, canonical, StringComparison.OrdinalIgnoreCase)
                         || string.Equals(normalizedRequest, canonical, StringComparison.OrdinalIgnoreCase));
        if (matchedCanonical is null)
        {
            return PublicProjectionProofRequestPathDisposition.NotGoverned;
        }

        return string.Equals(rawPath, matchedCanonical, StringComparison.Ordinal)
               && string.Equals(requestPath, matchedCanonical, StringComparison.Ordinal)
            ? PublicProjectionProofRequestPathDisposition.Canonical
            : PublicProjectionProofRequestPathDisposition.RejectVariant;
    }

    public static bool IsCanonical(PathString path)
        => CanonicalPaths.Any(
            canonical => path.Equals(canonical, StringComparison.Ordinal));

    private static string? NormalizeEquivalentPath(string path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return null;
        }

        string decoded = path;
        try
        {
            // Decode repeatedly so double-encoded separators cannot become a
            // different route in a downstream proxy or middleware component.
            for (int iteration = 0; iteration < 4; iteration++)
            {
                string next = Uri.UnescapeDataString(decoded);
                if (string.Equals(next, decoded, StringComparison.Ordinal))
                {
                    break;
                }
                decoded = next;
            }
        }
        catch (UriFormatException)
        {
            return null;
        }

        decoded = decoded.Replace('\\', '/');
        var segments = new List<string>();
        foreach (string segment in decoded.Split('/'))
        {
            if (segment.Length == 0 || segment == ".")
            {
                continue;
            }
            if (segment == "..")
            {
                if (segments.Count == 0)
                {
                    return null;
                }
                segments.RemoveAt(segments.Count - 1);
                continue;
            }
            segments.Add(segment);
        }
        return "/" + string.Join('/', segments);
    }
}
