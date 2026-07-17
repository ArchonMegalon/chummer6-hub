using System.Net;
using System.Net.Sockets;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Validates any obsolete public Play projection setting for readiness reporting.
/// The projection transport is retired, but strict origin and address checks remain
/// as regression guards against accidentally restoring an unsafe outbound path.
/// This type does not resolve DNS, create a client, or guard an integrated transport;
/// any future outbound design must implement and review those controls from scratch.
/// </summary>
public static class DormantPublicPlayProjectionConfigurationPolicy
{
    public const string AllowedOriginsConfigurationKey = "CHUMMER_PUBLIC_PLAY_PROXY_ALLOWED_ORIGINS";
    public const string DefaultCanonicalOrigin = "https://play.chummer.run/";

    public static bool TryResolveDormantOriginForReadiness(IConfiguration configuration, out Uri? upstream)
        => TryResolveDormantOriginForReadiness(configuration, publicCanonicalOrigin: null, out upstream);

    public static bool TryResolveDormantOriginForReadiness(
        IConfiguration configuration,
        Uri? publicCanonicalOrigin,
        out Uri? upstream)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        upstream = null;

        string configured = (configuration[PublicPlayProxyGateway.UpstreamConfigurationKey]
            ?? Environment.GetEnvironmentVariable(PublicPlayProxyGateway.UpstreamConfigurationKey)
            ?? string.Empty).Trim();
        if (!TryNormalizeHttpsOrigin(configured, out Uri? candidate) || candidate is null)
        {
            return false;
        }

        string rawAllowlist = (configuration[AllowedOriginsConfigurationKey]
            ?? Environment.GetEnvironmentVariable(AllowedOriginsConfigurationKey)
            ?? DefaultCanonicalOrigin).Trim();
        string[] allowlist = rawAllowlist.Split(
            [';', ','],
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (allowlist.Length == 0)
        {
            return false;
        }

        foreach (string rawAllowedOrigin in allowlist)
        {
            if (!TryNormalizeHttpsOrigin(rawAllowedOrigin, out Uri? allowedOrigin) || allowedOrigin is null)
            {
                return false;
            }

            if (Uri.Compare(
                    candidate,
                    allowedOrigin,
                    UriComponents.SchemeAndServer,
                    UriFormat.Unescaped,
                    StringComparison.OrdinalIgnoreCase) == 0)
            {
                if (publicCanonicalOrigin is not null && HasSameOrigin(candidate, publicCanonicalOrigin))
                {
                    return false;
                }
                upstream = candidate;
                return true;
            }
        }

        return false;
    }

    public static bool IsPublicAddressIfTransportIsEverRestored(IPAddress address)
    {
        ArgumentNullException.ThrowIfNull(address);

        if (address.IsIPv4MappedToIPv6)
        {
            address = address.MapToIPv4();
        }

        if (address.AddressFamily == AddressFamily.InterNetwork)
        {
            byte[] bytes = address.GetAddressBytes();
            byte first = bytes[0];
            byte second = bytes[1];
            byte third = bytes[2];
            return first != 0
                && first != 10
                && first != 127
                && first < 224
                && !(first == 100 && second is >= 64 and <= 127)
                && !(first == 169 && second == 254)
                && !(first == 172 && second is >= 16 and <= 31)
                && !(first == 192 && second == 0)
                && !(first == 192 && second == 2)
                && !(first == 192 && second == 88 && third == 99)
                && !(first == 192 && second == 168)
                && !(first == 198 && second is 18 or 19)
                && !(first == 198 && second == 51 && third == 100)
                && !(first == 203 && second == 0 && third == 113);
        }

        if (address.AddressFamily != AddressFamily.InterNetworkV6
            || IPAddress.IsLoopback(address)
            || address.Equals(IPAddress.IPv6Any)
            || address.Equals(IPAddress.IPv6None)
            || address.IsIPv6LinkLocal
            || address.IsIPv6SiteLocal
            || address.IsIPv6Multicast)
        {
            return false;
        }

        byte[] ipv6 = address.GetAddressBytes();
        bool uniqueLocal = (ipv6[0] & 0xfe) == 0xfc;
        bool globalUnicast = (ipv6[0] & 0xe0) == 0x20;
        return globalUnicast
            && !uniqueLocal
            && !IsInNetwork(address, "2001::", 23)
            && !IsInNetwork(address, "2001:db8::", 32)
            && !IsInNetwork(address, "2002::", 16)
            && !IsInNetwork(address, "2620:4f:8000::", 48)
            && !IsInNetwork(address, "3fff::", 20);
    }

    private static bool TryNormalizeHttpsOrigin(string value, out Uri? origin)
    {
        origin = null;
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? parsed)
            || parsed.Scheme != Uri.UriSchemeHttps
            || parsed.HostNameType != UriHostNameType.Dns
            || string.IsNullOrWhiteSpace(parsed.Host)
            || parsed.Host.EndsWith(".", StringComparison.Ordinal)
            || !string.IsNullOrEmpty(parsed.UserInfo)
            || (!string.IsNullOrEmpty(parsed.AbsolutePath) && parsed.AbsolutePath != "/")
            || !string.IsNullOrEmpty(parsed.Query)
            || !string.IsNullOrEmpty(parsed.Fragment))
        {
            return false;
        }

        origin = new UriBuilder(parsed)
        {
            Path = "/",
            Query = string.Empty,
            Fragment = string.Empty
        }.Uri;
        return true;
    }

    private static bool HasSameOrigin(Uri left, Uri right)
        => Uri.Compare(
            left,
            right,
            UriComponents.SchemeAndServer,
            UriFormat.Unescaped,
            StringComparison.OrdinalIgnoreCase) == 0;

    private static bool IsInNetwork(IPAddress address, string network, int prefixLength)
    {
        byte[] addressBytes = address.GetAddressBytes();
        byte[] networkBytes = IPAddress.Parse(network).GetAddressBytes();
        int wholeBytes = prefixLength / 8;
        int remainingBits = prefixLength % 8;
        for (int index = 0; index < wholeBytes; index += 1)
        {
            if (addressBytes[index] != networkBytes[index])
            {
                return false;
            }
        }

        if (remainingBits == 0)
        {
            return true;
        }

        int mask = 0xff << (8 - remainingBits);
        return (addressBytes[wholeBytes] & mask) == (networkBytes[wholeBytes] & mask);
    }
}
