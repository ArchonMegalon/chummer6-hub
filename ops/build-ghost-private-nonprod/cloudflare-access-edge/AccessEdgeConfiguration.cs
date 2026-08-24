using System.Text.RegularExpressions;

namespace Chummer.BuildGhost.CloudflareAccessEdge;

public sealed record AccessEdgeConfiguration(
    string PublicHost,
    string TeamDomain,
    string Audience,
    string ToolContractDigest,
    Uri Issuer,
    Uri CertificatesEndpoint)
{
    public const string HostEnvironmentVariable =
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_HOST";
    public const string TeamDomainEnvironmentVariable =
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_TEAM_DOMAIN";
    public const string AudienceEnvironmentVariable =
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE";
    public const string ToolContractDigestEnvironmentVariable =
        "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_CONTRACT_DIGEST";

    private static readonly Regex AudiencePattern = new(
        "^[A-Za-z0-9_-]{16,128}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    public static AccessEdgeConfiguration FromEnvironment()
        => Create(
            Environment.GetEnvironmentVariable(HostEnvironmentVariable),
            Environment.GetEnvironmentVariable(TeamDomainEnvironmentVariable),
            Environment.GetEnvironmentVariable(AudienceEnvironmentVariable),
            Environment.GetEnvironmentVariable(ToolContractDigestEnvironmentVariable));

    public static AccessEdgeConfiguration Create(
        string? publicHost,
        string? teamDomain,
        string? audience,
        string? toolContractDigest)
    {
        string host = RequireCanonicalDnsName(publicHost, HostEnvironmentVariable);
        if (string.Equals(host, "unconfigured.invalid", StringComparison.Ordinal))
        {
            throw Invalid(HostEnvironmentVariable);
        }

        string team = RequireCanonicalDnsName(teamDomain, TeamDomainEnvironmentVariable);
        if (string.Equals(team, "unconfigured.cloudflareaccess.com", StringComparison.Ordinal)
            || !team.EndsWith(".cloudflareaccess.com", StringComparison.Ordinal)
            || team.Length <= ".cloudflareaccess.com".Length)
        {
            throw Invalid(TeamDomainEnvironmentVariable);
        }

        string normalizedAudience = audience?.Trim() ?? string.Empty;
        if (!AudiencePattern.IsMatch(normalizedAudience)
            || !string.Equals(normalizedAudience, audience, StringComparison.Ordinal))
        {
            throw Invalid(AudienceEnvironmentVariable);
        }

        string normalizedToolContractDigest = toolContractDigest?.Trim() ?? string.Empty;
        if (normalizedToolContractDigest.Length != 71
            || !normalizedToolContractDigest.StartsWith("sha256:", StringComparison.Ordinal)
            || !normalizedToolContractDigest.AsSpan(7).ToString().All(
                static character => character is >= '0' and <= '9' or >= 'a' and <= 'f')
            || !string.Equals(normalizedToolContractDigest, toolContractDigest, StringComparison.Ordinal))
        {
            throw Invalid(ToolContractDigestEnvironmentVariable);
        }

        Uri issuer = new($"https://{team}", UriKind.Absolute);
        Uri certificatesEndpoint = new(
            issuer,
            "/cdn-cgi/access/certs");
        return new AccessEdgeConfiguration(
            host,
            team,
            normalizedAudience,
            normalizedToolContractDigest,
            issuer,
            certificatesEndpoint);
    }

    private static string RequireCanonicalDnsName(string? raw, string variableName)
    {
        string value = raw?.Trim() ?? string.Empty;
        if (value.Length is < 1 or > 253
            || !string.Equals(value, raw, StringComparison.Ordinal)
            || !string.Equals(value, value.ToLowerInvariant(), StringComparison.Ordinal)
            || Uri.CheckHostName(value) != UriHostNameType.Dns
            || value.Contains(':', StringComparison.Ordinal)
            || value.Contains('/', StringComparison.Ordinal))
        {
            throw Invalid(variableName);
        }

        return value;
    }

    private static InvalidOperationException Invalid(string variableName)
        => new($"Cloudflare Access ingress is blocked: {variableName} is not canonically configured.");
}
