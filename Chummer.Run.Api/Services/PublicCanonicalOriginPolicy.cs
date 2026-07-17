using System.Globalization;
using System.Net;
using Microsoft.Extensions.Primitives;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Owns the public origin used for links and validates the host boundary before any
/// redirect, cookie, or public response can observe attacker-controlled host data.
/// </summary>
public sealed class PublicCanonicalOriginPolicy
{
    public const string CanonicalOriginConfigurationKey = "CHUMMER_PUBLIC_CANONICAL_ORIGIN";
    public const string AllowedHostsConfigurationKey = "CHUMMER_PUBLIC_ALLOWED_HOSTS";

    private readonly HashSet<string> _allowedHosts;

    private PublicCanonicalOriginPolicy(Uri canonicalOrigin, IEnumerable<string> allowedHosts)
    {
        CanonicalOrigin = canonicalOrigin;
        _allowedHosts = new HashSet<string>(allowedHosts, StringComparer.OrdinalIgnoreCase);
        AllowedHosts = _allowedHosts.OrderBy(static host => host, StringComparer.Ordinal).ToArray();
        AllowedHostsConfiguration = string.Join(';', AllowedHosts.Select(FormatAllowedHost));
    }

    public Uri CanonicalOrigin { get; }

    public string Origin => CanonicalOrigin.GetLeftPart(UriPartial.Authority).TrimEnd('/');

    public string CanonicalHost => NormalizeHost(CanonicalOrigin.Host, "canonical public origin");

    public string CanonicalAuthority => CanonicalOrigin.IsDefaultPort
        ? FormatAllowedHost(CanonicalHost)
        : $"{FormatAllowedHost(CanonicalHost)}:{CanonicalOrigin.Port.ToString(CultureInfo.InvariantCulture)}";

    public bool UsesHttps => string.Equals(CanonicalOrigin.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase);

    public IReadOnlyList<string> AllowedHosts { get; }

    public string AllowedHostsConfiguration { get; }

    public static PublicCanonicalOriginPolicy Create(
        IConfiguration configuration,
        IHostEnvironment environment)
    {
        ArgumentNullException.ThrowIfNull(environment);
        return Create(configuration, environment.IsProduction());
    }

    internal static PublicCanonicalOriginPolicy Create(
        IConfiguration configuration,
        bool production)
    {
        ArgumentNullException.ThrowIfNull(configuration);

        string rawAllowedHosts = (configuration[AllowedHostsConfigurationKey]
            ?? configuration["AllowedHosts"]
            ?? string.Empty).Trim();
        IReadOnlyList<string> allowedHosts = ParseAllowedHosts(rawAllowedHosts, production);

        string rawCanonicalOrigin = (configuration[CanonicalOriginConfigurationKey] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(rawCanonicalOrigin))
        {
            throw new InvalidOperationException(
                $"{CanonicalOriginConfigurationKey} must configure one absolute public origin.");
        }

        if (!Uri.TryCreate(rawCanonicalOrigin, UriKind.Absolute, out Uri? canonicalOrigin)
            || (canonicalOrigin.Scheme != Uri.UriSchemeHttp && canonicalOrigin.Scheme != Uri.UriSchemeHttps)
            || string.IsNullOrWhiteSpace(canonicalOrigin.Host)
            || !string.IsNullOrEmpty(canonicalOrigin.UserInfo)
            || (!string.IsNullOrEmpty(canonicalOrigin.AbsolutePath) && canonicalOrigin.AbsolutePath != "/")
            || !string.IsNullOrEmpty(canonicalOrigin.Query)
            || !string.IsNullOrEmpty(canonicalOrigin.Fragment))
        {
            throw new InvalidOperationException(
                $"{CanonicalOriginConfigurationKey} must be an HTTP(S) origin without credentials, path, query, or fragment.");
        }

        if (production && canonicalOrigin.Scheme != Uri.UriSchemeHttps)
        {
            throw new InvalidOperationException(
                $"{CanonicalOriginConfigurationKey} must use HTTPS in Production.");
        }

        string canonicalHost = NormalizeHost(canonicalOrigin.Host, "canonical public origin");
        if (!allowedHosts.Contains(canonicalHost, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                $"{CanonicalOriginConfigurationKey} host '{canonicalHost}' must be present in the public host allowlist.");
        }

        var normalizedOrigin = new UriBuilder(canonicalOrigin)
        {
            Host = canonicalHost,
            Path = "/",
            Query = string.Empty,
            Fragment = string.Empty
        }.Uri;
        return new PublicCanonicalOriginPolicy(normalizedOrigin, allowedHosts);
    }

    /// <summary>
    /// Safe compatibility default for controller-only unit tests that do not run Program startup.
    /// Runtime construction always uses <see cref="Create(IConfiguration,IHostEnvironment)"/>.
    /// </summary>
    internal static PublicCanonicalOriginPolicy CreateUnitTestDefault(IConfiguration? configuration = null)
    {
        IConfiguration resolvedConfiguration = configuration ?? new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["AllowedHosts"] = "localhost;127.0.0.1;[::1]",
                [CanonicalOriginConfigurationKey] = "http://localhost"
            })
            .Build();

        string? allowedHosts = resolvedConfiguration[AllowedHostsConfigurationKey]
            ?? resolvedConfiguration["AllowedHosts"];
        string? canonicalOrigin = resolvedConfiguration[CanonicalOriginConfigurationKey];
        if (!string.IsNullOrWhiteSpace(allowedHosts) && !string.IsNullOrWhiteSpace(canonicalOrigin))
        {
            return Create(resolvedConfiguration, production: false);
        }

        // Older controller-only tests commonly provide the fixed Google callback but do
        // not boot Program. Reuse that configured origin rather than ever consulting the
        // synthetic HttpRequest Host.
        string? configuredRedirect = resolvedConfiguration["GOOGLE_OIDC_REDIRECT_URI"]?.Trim();
        if (Uri.TryCreate(configuredRedirect, UriKind.Absolute, out Uri? redirectUri)
            && (redirectUri.Scheme == Uri.UriSchemeHttp || redirectUri.Scheme == Uri.UriSchemeHttps)
            && !string.IsNullOrWhiteSpace(redirectUri.Host))
        {
            IConfiguration redirectConfiguration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["AllowedHosts"] = FormatAllowedHost(redirectUri.Host),
                    [CanonicalOriginConfigurationKey] = redirectUri.GetLeftPart(UriPartial.Authority)
                })
                .Build();
            return Create(redirectConfiguration, production: false);
        }

        return CreateUnitTestDefault();
    }

    private static PublicCanonicalOriginPolicy CreateUnitTestDefault()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["AllowedHosts"] = "localhost;127.0.0.1;[::1]",
                [CanonicalOriginConfigurationKey] = "http://localhost"
            })
            .Build();
        return Create(configuration, production: false);
    }

    public bool TryValidateRequest(HttpRequest request, out string failure)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (!request.Host.HasValue || !TryNormalizeHost(request.Host.Host, out string? requestHost))
        {
            failure = "The request Host header is missing or invalid.";
            return false;
        }

        if (!_allowedHosts.Contains(requestHost))
        {
            failure = "The request Host header is not allowed.";
            return false;
        }

        if (!ValidateForwardedHostValues(request.Headers["X-Forwarded-Host"], out failure))
        {
            return false;
        }

        if (!ValidateForwardedHeader(request.Headers["Forwarded"], out failure))
        {
            return false;
        }

        failure = string.Empty;
        return true;
    }

    public string BuildAbsolute(string path, QueryString query = default, PathString pathBase = default)
    {
        string normalizedPath = string.IsNullOrWhiteSpace(path) ? "/" : path.Trim();
        if (!normalizedPath.StartsWith("/", StringComparison.Ordinal)
            || normalizedPath.StartsWith("//", StringComparison.Ordinal)
            || normalizedPath.Contains('\\')
            || normalizedPath.Any(char.IsControl))
        {
            throw new ArgumentException("Public absolute paths must be rooted local paths.", nameof(path));
        }

        string normalizedPathBase = pathBase.HasValue ? pathBase.Value!.TrimEnd('/') : string.Empty;
        var builder = new UriBuilder(CanonicalOrigin)
        {
            Path = $"{normalizedPathBase}{normalizedPath}",
            Query = query.HasValue ? query.Value!.TrimStart('?') : string.Empty,
            Fragment = string.Empty
        };
        return builder.Uri.AbsoluteUri;
    }

    private bool ValidateForwardedHostValues(StringValues values, out string failure)
    {
        foreach (string? headerValue in values)
        {
            foreach (string candidate in (headerValue ?? string.Empty).Split(',', StringSplitOptions.TrimEntries))
            {
                if (string.IsNullOrWhiteSpace(candidate)
                    || !TryNormalizeAuthority(candidate, out string? authority)
                    || !string.Equals(authority, CanonicalAuthority, StringComparison.OrdinalIgnoreCase))
                {
                    failure = "X-Forwarded-Host must match the configured canonical public authority.";
                    return false;
                }
            }
        }

        failure = string.Empty;
        return true;
    }

    private bool ValidateForwardedHeader(StringValues values, out string failure)
    {
        foreach (string? headerValue in values)
        {
            foreach (string forwardedElement in (headerValue ?? string.Empty).Split(',', StringSplitOptions.TrimEntries))
            {
                foreach (string parameter in forwardedElement.Split(';', StringSplitOptions.TrimEntries))
                {
                    int separator = parameter.IndexOf('=');
                    if (separator <= 0
                        || !string.Equals(parameter[..separator].Trim(), "host", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    string candidate = parameter[(separator + 1)..].Trim();
                    if (candidate.Length >= 2 && candidate[0] == '"' && candidate[^1] == '"')
                    {
                        candidate = candidate[1..^1];
                    }

                    if (!TryNormalizeAuthority(candidate, out string? authority)
                        || !string.Equals(authority, CanonicalAuthority, StringComparison.OrdinalIgnoreCase))
                    {
                        failure = "Forwarded host must match the configured canonical public authority.";
                        return false;
                    }
                }
            }
        }

        failure = string.Empty;
        return true;
    }

    private static IReadOnlyList<string> ParseAllowedHosts(string value, bool production)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException("The public host allowlist must not be missing or empty.");
        }

        string[] tokens = value.Split([';', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (tokens.Length == 0)
        {
            throw new InvalidOperationException("The public host allowlist must contain at least one explicit host.");
        }

        var hosts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string token in tokens)
        {
            if (token.Contains('*') || token.Contains('+'))
            {
                string environmentQualifier = production ? " in Production" : string.Empty;
                throw new InvalidOperationException($"Wildcard public hosts are not allowed{environmentQualifier}.");
            }

            hosts.Add(NormalizeHost(token, "public host allowlist"));
        }

        return hosts.OrderBy(static host => host, StringComparer.Ordinal).ToArray();
    }

    private static string NormalizeHost(string value, string source)
    {
        if (!TryNormalizeHost(value, out string? normalized))
        {
            throw new InvalidOperationException($"The {source} contains invalid host '{value}'.");
        }

        return normalized;
    }

    private static bool TryNormalizeHost(string? value, out string normalized)
    {
        normalized = string.Empty;
        string candidate = value?.Trim().TrimEnd('.') ?? string.Empty;
        if (string.IsNullOrWhiteSpace(candidate)
            || candidate.Contains('/')
            || candidate.Contains('\\')
            || candidate.Contains('@')
            || candidate.Any(char.IsWhiteSpace)
            || candidate.Any(char.IsControl))
        {
            return false;
        }

        if (candidate.StartsWith('[') && candidate.EndsWith(']'))
        {
            candidate = candidate[1..^1];
        }

        if (IPAddress.TryParse(candidate, out IPAddress? address))
        {
            normalized = address.ToString().ToLowerInvariant();
            return true;
        }

        if (candidate.Contains(':'))
        {
            return false;
        }

        try
        {
            candidate = new IdnMapping().GetAscii(candidate).ToLowerInvariant();
        }
        catch (ArgumentException)
        {
            return false;
        }

        if (string.Equals(candidate, "localhost", StringComparison.OrdinalIgnoreCase))
        {
            normalized = "localhost";
            return true;
        }

        if (Uri.CheckHostName(candidate) != UriHostNameType.Dns
            || candidate.Length > 253
            || candidate.Split('.').Any(static label => label.Length == 0
                || label.Length > 63
                || label.StartsWith('-')
                || label.EndsWith('-')))
        {
            return false;
        }

        normalized = candidate;
        return true;
    }

    private static bool TryNormalizeAuthority(string value, out string authority)
    {
        authority = string.Empty;
        string candidate = value.Trim();
        if (string.IsNullOrEmpty(candidate)
            || candidate.Contains('/')
            || candidate.Contains('\\')
            || candidate.Contains('@')
            || candidate.Contains('"')
            || candidate.Any(char.IsWhiteSpace)
            || candidate.Any(char.IsControl))
        {
            return false;
        }

        HostString parsed;
        try
        {
            parsed = HostString.FromUriComponent(candidate);
        }
        catch (FormatException)
        {
            return false;
        }

        if (!TryNormalizeHost(parsed.Host, out string? host))
        {
            return false;
        }

        authority = parsed.Port.HasValue
            ? $"{FormatAllowedHost(host)}:{parsed.Port.Value.ToString(CultureInfo.InvariantCulture)}"
            : FormatAllowedHost(host);
        return true;
    }

    private static string FormatAllowedHost(string host)
        => IPAddress.TryParse(host, out IPAddress? address) && address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetworkV6
            ? $"[{host}]"
            : host;
}
