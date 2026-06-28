using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Primitives;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactAccessTokenService
{
    private static readonly HashSet<string> ProtectedMediaPaths = new(StringComparer.OrdinalIgnoreCase)
    {
        "/media/horizons/jackpoint-90s-deepdive.mp4",
        "/media/horizons/runbook-press-90s-deepdive.mp4",
        "/media/horizons/origin-dossier-the-name-she-chose-20260619.mp4"
    };
    private static readonly Regex[] ProtectedMediaPathPatterns =
    [
        new(@"^/media/ledger/newsreels/turn-\d+-newsreel(?:-poster)?\.(mp4|webm|vtt|png)$", RegexOptions.IgnoreCase | RegexOptions.Compiled),
        new(@"^/media/ledger/tours/[a-z0-9-]+(?:-poster)?\.(mp4|webm|vtt|png)$", RegexOptions.IgnoreCase | RegexOptions.Compiled),
        new(@"^/media/ledger/factions/[a-z0-9-]+-promo-mobile\.mp4$", RegexOptions.IgnoreCase | RegexOptions.Compiled),
        new(@"^/media/ledger/factions/[a-z0-9-]+-promo\.webm$", RegexOptions.IgnoreCase | RegexOptions.Compiled),
        new(@"^/media/ledger/factions/[a-z0-9-]+-promo-poster\.png$", RegexOptions.IgnoreCase | RegexOptions.Compiled)
    ];

    private readonly IDataProtector _protector;
    private readonly TimeSpan _lifetime;

    public HorizonArtifactAccessTokenService(
        IDataProtectionProvider dataProtectionProvider,
        IConfiguration configuration)
    {
        _protector = dataProtectionProvider.CreateProtector("Chummer.Run.Api.HorizonArtifactAccessTokenService.v1");
        _lifetime = TimeSpan.FromMinutes(ReadPositiveInt(configuration["CHUMMER_HORIZON_ARTIFACT_ACCESS_TOKEN_LIFETIME_MINUTES"], fallback: 5));
    }

    public bool RequiresToken(PathString path)
        => RequiresToken(path.ToString());

    public bool RequiresToken(string? path)
    {
        string normalizedPath = NormalizePath(path);
        return ProtectedMediaPaths.Contains(normalizedPath)
            || ProtectedMediaPathPatterns.Any(pattern => pattern.IsMatch(normalizedPath));
    }

    public string IssueProtectedUrl(string path, DateTimeOffset? now = null)
    {
        string originalPath = string.IsNullOrWhiteSpace(path) ? string.Empty : path.Trim();
        string normalizedPath = NormalizePath(originalPath);
        if (!RequiresToken(normalizedPath))
        {
            return originalPath;
        }

        DateTimeOffset effectiveNow = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        string token = WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(_protector.Protect(JsonSerializer.Serialize(new ProtectedArtifactAccessEnvelope(
            Path: normalizedPath,
            ExpiresAtUtc: effectiveNow.Add(_lifetime))))));
        return QueryHelpers.AddQueryString(normalizedPath, "artifactAccess", token);
    }

    public bool IsAuthorized(PathString path, StringValues tokenValues, DateTimeOffset? now = null)
    {
        string normalizedPath = NormalizePath(path.ToString());
        if (!RequiresToken(normalizedPath))
        {
            return true;
        }

        string? token = tokenValues.FirstOrDefault();
        if (string.IsNullOrWhiteSpace(token))
        {
            return false;
        }

        try
        {
            string json = _protector.Unprotect(Encoding.UTF8.GetString(WebEncoders.Base64UrlDecode(token.Trim())));
            ProtectedArtifactAccessEnvelope? envelope = JsonSerializer.Deserialize<ProtectedArtifactAccessEnvelope>(json);
            if (envelope is null)
            {
                return false;
            }

            DateTimeOffset effectiveNow = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
            return string.Equals(NormalizePath(envelope.Path), normalizedPath, StringComparison.OrdinalIgnoreCase)
                && envelope.ExpiresAtUtc >= effectiveNow;
        }
        catch
        {
            return false;
        }
    }

    private static string NormalizePath(string? path)
        => string.IsNullOrWhiteSpace(path)
            ? string.Empty
            : path.Trim().Split('?', '#')[0];

    private static int ReadPositiveInt(string? value, int fallback)
        => int.TryParse(value, out int parsed) && parsed > 0 ? parsed : fallback;

    private sealed record ProtectedArtifactAccessEnvelope(
        string Path,
        DateTimeOffset ExpiresAtUtc);
}
