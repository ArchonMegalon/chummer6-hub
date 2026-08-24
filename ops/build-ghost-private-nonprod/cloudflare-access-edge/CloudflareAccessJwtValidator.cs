using System.Buffers;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.BuildGhost.CloudflareAccessEdge;

public interface ICloudflareAccessTokenValidator
{
    ValueTask<bool> ValidateAsync(
        string assertion,
        string authenticatedEmail,
        CancellationToken cancellationToken);
}

public interface ICloudflareAccessSigningKeyProvider
{
    ValueTask<CloudflareAccessSigningKey?> GetAsync(
        string keyId,
        CancellationToken cancellationToken);
}

public sealed record CloudflareAccessSigningKey(
    string KeyId,
    byte[] Modulus,
    byte[] Exponent);

public sealed class CloudflareAccessJwtValidator : ICloudflareAccessTokenValidator
{
    public const int MaximumAssertionBytes = 16 * 1024;
    public const long MaximumTokenLifetimeSeconds = 24 * 60 * 60;

    private readonly AccessEdgeConfiguration _configuration;
    private readonly ICloudflareAccessSigningKeyProvider _keys;
    private readonly TimeProvider _timeProvider;

    public CloudflareAccessJwtValidator(
        AccessEdgeConfiguration configuration,
        ICloudflareAccessSigningKeyProvider keys,
        TimeProvider? timeProvider = null)
    {
        _configuration = configuration;
        _keys = keys;
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public async ValueTask<bool> ValidateAsync(
        string assertion,
        string authenticatedEmail,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(assertion)
            || Encoding.UTF8.GetByteCount(assertion) > MaximumAssertionBytes
            || assertion.Any(static character =>
                character > 0x7f || !(char.IsLetterOrDigit(character) || character is '-' or '_' or '.')))
        {
            return false;
        }

        string[] segments = assertion.Split('.');
        if (segments.Length != 3
            || segments.Any(static segment => segment.Length == 0)
            || !TryDecodeBase64Url(segments[0], out byte[] headerBytes)
            || !TryDecodeBase64Url(segments[1], out byte[] payloadBytes)
            || !TryDecodeBase64Url(segments[2], out byte[] signature))
        {
            return false;
        }

        try
        {
            using JsonDocument headerDocument = JsonDocument.Parse(headerBytes);
            using JsonDocument payloadDocument = JsonDocument.Parse(payloadBytes);
            JsonElement header = headerDocument.RootElement;
            JsonElement payload = payloadDocument.RootElement;
            if (header.ValueKind != JsonValueKind.Object
                || payload.ValueKind != JsonValueKind.Object
                || ContainsDuplicateProperty(header)
                || ContainsDuplicateProperty(payload)
                || !TryReadExactString(header, "alg", out string algorithm)
                || !string.Equals(algorithm, "RS256", StringComparison.Ordinal)
                || (header.TryGetProperty("typ", out JsonElement tokenType)
                    && (tokenType.ValueKind != JsonValueKind.String
                        || !string.Equals(tokenType.GetString(), "JWT", StringComparison.Ordinal)))
                || !TryReadExactString(header, "kid", out string keyId)
                || keyId.Length is < 1 or > 256
                || keyId.Any(static character =>
                    !(char.IsLetterOrDigit(character) || character is '-' or '_' or '.'))
                || !TryReadExactString(payload, "iss", out string issuer)
                || !string.Equals(issuer, _configuration.Issuer.AbsoluteUri.TrimEnd('/'), StringComparison.Ordinal)
                || !HasExactAudience(payload, _configuration.Audience)
                || !TryReadExactString(payload, "type", out string accessTokenType)
                || !string.Equals(accessTokenType, "app", StringComparison.Ordinal)
                || !TryReadExactString(payload, "email", out string tokenEmail)
                || !string.Equals(tokenEmail, authenticatedEmail, StringComparison.Ordinal)
                || !TryReadUnixTime(payload, "iat", out long issuedAt)
                || !TryReadUnixTime(payload, "exp", out long expiresAt))
            {
                return false;
            }

            long now = _timeProvider.GetUtcNow().ToUnixTimeSeconds();
            const long clockSkewSeconds = 30;
            if (issuedAt < 0
                || expiresAt < 0
                || issuedAt > now + clockSkewSeconds
                || expiresAt <= now - clockSkewSeconds
                || expiresAt <= issuedAt
                || expiresAt - issuedAt > MaximumTokenLifetimeSeconds)
            {
                return false;
            }

            if (payload.TryGetProperty("nbf", out JsonElement notBeforeElement)
                && (!TryReadUnixTime(notBeforeElement, out long notBefore)
                    || notBefore > now + clockSkewSeconds))
            {
                return false;
            }

            CloudflareAccessSigningKey? key = await _keys
                .GetAsync(keyId, cancellationToken)
                .ConfigureAwait(false);
            if (key is null || !string.Equals(key.KeyId, keyId, StringComparison.Ordinal))
            {
                return false;
            }

            byte[] signedBytes = Encoding.ASCII.GetBytes($"{segments[0]}.{segments[1]}");
            try
            {
                using RSA rsa = RSA.Create();
                rsa.ImportParameters(new RSAParameters
                {
                    Modulus = key.Modulus,
                    Exponent = key.Exponent,
                });
                return rsa.VerifyData(
                    signedBytes,
                    signature,
                    HashAlgorithmName.SHA256,
                    RSASignaturePadding.Pkcs1);
            }
            catch (CryptographicException)
            {
                return false;
            }
            finally
            {
                CryptographicOperations.ZeroMemory(signedBytes);
            }
        }
        catch (JsonException)
        {
            return false;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(headerBytes);
            CryptographicOperations.ZeroMemory(payloadBytes);
            CryptographicOperations.ZeroMemory(signature);
        }
    }

    private static bool HasExactAudience(JsonElement payload, string expected)
    {
        if (!payload.TryGetProperty("aud", out JsonElement audience))
        {
            return false;
        }

        if (audience.ValueKind == JsonValueKind.String)
        {
            return string.Equals(audience.GetString(), expected, StringComparison.Ordinal);
        }

        if (audience.ValueKind != JsonValueKind.Array)
        {
            return false;
        }

        int matches = 0;
        foreach (JsonElement candidate in audience.EnumerateArray())
        {
            if (candidate.ValueKind != JsonValueKind.String)
            {
                return false;
            }

            if (string.Equals(candidate.GetString(), expected, StringComparison.Ordinal))
            {
                matches++;
            }
        }

        return matches == 1;
    }

    private static bool TryReadExactString(
        JsonElement source,
        string propertyName,
        out string value)
    {
        value = string.Empty;
        if (!source.TryGetProperty(propertyName, out JsonElement element)
            || element.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        value = element.GetString() ?? string.Empty;
        return value.Length > 0;
    }

    private static bool TryReadUnixTime(
        JsonElement source,
        string propertyName,
        out long value)
    {
        value = 0;
        return source.TryGetProperty(propertyName, out JsonElement element)
            && TryReadUnixTime(element, out value);
    }

    private static bool TryReadUnixTime(JsonElement element, out long value)
    {
        value = 0;
        return element.ValueKind == JsonValueKind.Number
            && element.TryGetInt64(out value);
    }

    internal static bool ContainsDuplicateProperty(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            HashSet<string> names = new(StringComparer.Ordinal);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!names.Add(property.Name) || ContainsDuplicateProperty(property.Value))
                {
                    return true;
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement child in element.EnumerateArray())
            {
                if (ContainsDuplicateProperty(child))
                {
                    return true;
                }
            }
        }

        return false;
    }

    internal static bool TryDecodeBase64Url(string value, out byte[] decoded)
    {
        decoded = [];
        if (value.Length == 0
            || value.Any(static character =>
                !(char.IsLetterOrDigit(character) || character is '-' or '_')))
        {
            return false;
        }

        string padded = value.Replace('-', '+').Replace('_', '/');
        padded += (padded.Length % 4) switch
        {
            0 => string.Empty,
            2 => "==",
            3 => "=",
            _ => "!",
        };
        try
        {
            decoded = Convert.FromBase64String(padded);
            return decoded.Length > 0;
        }
        catch (FormatException)
        {
            return false;
        }
    }
}

public sealed class CloudflareAccessSigningKeyProvider : ICloudflareAccessSigningKeyProvider
{
    private const int MaximumJwksBytes = 1024 * 1024;
    private static readonly TimeSpan CacheLifetime = TimeSpan.FromMinutes(10);

    private readonly AccessEdgeConfiguration _configuration;
    private readonly HttpClient _httpClient;
    private readonly TimeProvider _timeProvider;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);
    private IReadOnlyDictionary<string, CloudflareAccessSigningKey> _keys =
        new Dictionary<string, CloudflareAccessSigningKey>(StringComparer.Ordinal);
    private DateTimeOffset _expiresAt = DateTimeOffset.MinValue;

    public CloudflareAccessSigningKeyProvider(
        AccessEdgeConfiguration configuration,
        HttpClient httpClient,
        TimeProvider? timeProvider = null)
    {
        _configuration = configuration;
        _httpClient = httpClient;
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public async ValueTask<CloudflareAccessSigningKey?> GetAsync(
        string keyId,
        CancellationToken cancellationToken)
    {
        DateTimeOffset now = _timeProvider.GetUtcNow();
        if (now < _expiresAt && _keys.TryGetValue(keyId, out CloudflareAccessSigningKey? cached))
        {
            return cached;
        }

        await _refreshLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            now = _timeProvider.GetUtcNow();
            bool cacheFresh = now < _expiresAt;
            if (cacheFresh && _keys.TryGetValue(keyId, out cached))
            {
                return cached;
            }

            IReadOnlyDictionary<string, CloudflareAccessSigningKey>? refreshed =
                await RefreshAsync(cancellationToken).ConfigureAwait(false);
            if (refreshed is null)
            {
                _keys = new Dictionary<string, CloudflareAccessSigningKey>(StringComparer.Ordinal);
                _expiresAt = DateTimeOffset.MinValue;
                return null;
            }

            _keys = refreshed;
            _expiresAt = now.Add(CacheLifetime);
            return _keys.TryGetValue(keyId, out CloudflareAccessSigningKey? found)
                ? found
                : null;
        }
        finally
        {
            _refreshLock.Release();
        }
    }

    private async Task<IReadOnlyDictionary<string, CloudflareAccessSigningKey>?> RefreshAsync(
        CancellationToken cancellationToken)
    {
        using HttpRequestMessage request = new(HttpMethod.Get, _configuration.CertificatesEndpoint);
        request.Headers.Accept.ParseAdd("application/json");
        using HttpResponseMessage response = await _httpClient.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);
        if (response.StatusCode != HttpStatusCode.OK)
        {
            return null;
        }

        byte[] body = await ReadBoundedAsync(
            response.Content,
            MaximumJwksBytes,
            cancellationToken).ConfigureAwait(false);
        try
        {
            using JsonDocument document = JsonDocument.Parse(body);
            if (document.RootElement.ValueKind != JsonValueKind.Object
                || CloudflareAccessJwtValidator.ContainsDuplicateProperty(document.RootElement)
                || !document.RootElement.TryGetProperty("keys", out JsonElement keysElement)
                || keysElement.ValueKind != JsonValueKind.Array)
            {
                return null;
            }

            Dictionary<string, CloudflareAccessSigningKey> parsed = new(StringComparer.Ordinal);
            foreach (JsonElement key in keysElement.EnumerateArray())
            {
                if (key.ValueKind != JsonValueKind.Object
                    || !TryJwkString(key, "kid", out string keyId)
                    || !TryJwkString(key, "kty", out string keyType)
                    || !string.Equals(keyType, "RSA", StringComparison.Ordinal)
                    || !TryJwkString(key, "alg", out string algorithm)
                    || !string.Equals(algorithm, "RS256", StringComparison.Ordinal)
                    || (key.TryGetProperty("use", out JsonElement use)
                        && (use.ValueKind != JsonValueKind.String
                            || !string.Equals(use.GetString(), "sig", StringComparison.Ordinal)))
                    || !TryJwkString(key, "n", out string modulusValue)
                    || !TryJwkString(key, "e", out string exponentValue)
                    || !CloudflareAccessJwtValidator.TryDecodeBase64Url(modulusValue, out byte[] modulus)
                    || !CloudflareAccessJwtValidator.TryDecodeBase64Url(exponentValue, out byte[] exponent)
                    || modulus.Length < 256
                    || exponent.Length is < 1 or > 8
                    || !parsed.TryAdd(
                        keyId,
                        new CloudflareAccessSigningKey(keyId, modulus, exponent)))
                {
                    return null;
                }
            }

            return parsed.Count > 0 ? parsed : null;
        }
        catch (JsonException)
        {
            return null;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(body);
        }
    }

    private static bool TryJwkString(JsonElement key, string propertyName, out string value)
    {
        value = string.Empty;
        if (!key.TryGetProperty(propertyName, out JsonElement element)
            || element.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        value = element.GetString() ?? string.Empty;
        return value.Length > 0;
    }

    private static async Task<byte[]> ReadBoundedAsync(
        HttpContent content,
        int maximumBytes,
        CancellationToken cancellationToken)
    {
        await using Stream source = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using MemoryStream destination = new();
        byte[] buffer = ArrayPool<byte>.Shared.Rent(16 * 1024);
        try
        {
            int total = 0;
            while (true)
            {
                int read = await source.ReadAsync(buffer.AsMemory(0, buffer.Length), cancellationToken)
                    .ConfigureAwait(false);
                if (read == 0)
                {
                    break;
                }

                total = checked(total + read);
                if (total > maximumBytes)
                {
                    throw new InvalidDataException("Cloudflare Access certificate response exceeded its bound.");
                }
                destination.Write(buffer, 0, read);
            }

            return destination.ToArray();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(buffer);
            ArrayPool<byte>.Shared.Return(buffer);
        }
    }
}
