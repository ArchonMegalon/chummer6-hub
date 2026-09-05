using System.Buffers;
using System.Globalization;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Primitives;

namespace Chummer.Run.Api.Services.InstallLinking;

public static class AndroidInstallLinkV2BootstrapProof
{
    public const string Scheme = "chummer.install-link.remote-callback.v2";
    public const string Path = "/api/v2/install-linking/callbacks/poll";

    public static byte[] CreateCanonicalPayload(AndroidInstallLinkProofPollV2Request request)
        => Encoding.UTF8.GetBytes(string.Join(
            '\n',
            Scheme,
            HttpMethods.Post,
            Path,
            request.OperationId,
            request.InstallationId,
            request.HeadId,
            request.ApplicationVersion,
            request.ChannelId,
            request.Platform,
            request.Architecture,
            request.IssuedAtUnixSeconds.ToString(CultureInfo.InvariantCulture),
            request.Nonce,
            request.HostLabel ?? string.Empty));
}

public static class AndroidLinkedV2RequestProof
{
    public const string Scheme = "chummer.android.packet.v2";
    public const string SchemeHeader = "X-Chummer-App-Proof";
    public const string InstallationHeader = "X-Chummer-Installation";
    public const string GrantHeader = "X-Chummer-Grant";
    public const string PacketKeyHeader = "X-Chummer-Packet-Key";
    public const string IssuedHeader = "X-Chummer-Packet-Issued";
    public const string SignatureHeader = "X-Chummer-Packet-Signature";
    public const int PacketKeyBytes = 32;
    public const int OperationIdBytes = 24;
    public const int OperationIdLength = 32;
    public const int MaxBodyBytes = InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes;
    public static readonly TimeSpan MaximumClockSkew = TimeSpan.FromMinutes(2);

    private static readonly object PrincipalItemKey = new();
    private static readonly object AuthorizedRequestItemKey = new();
    private static readonly object RefreshRetryResultItemKey = new();

    public static byte[] CreateCanonicalPayload(
        string method,
        string path,
        string installationId,
        string grantId,
        long issuedAtUnixSeconds,
        string packetKey,
        ReadOnlySpan<byte> body)
    {
        string bodyDigest = Convert.ToHexString(SHA256.HashData(body)).ToLowerInvariant();
        return Encoding.UTF8.GetBytes(string.Join(
            '\n',
            Scheme,
            method.ToUpperInvariant(),
            path,
            installationId,
            grantId,
            issuedAtUnixSeconds.ToString(CultureInfo.InvariantCulture),
            packetKey,
            $"sha256:{bodyDigest}"));
    }

    public static bool IsValidPacketKey(string packetKey)
    {
        if (string.IsNullOrWhiteSpace(packetKey) || packetKey.Length > 64)
        {
            return false;
        }

        string padded = packetKey.Replace('-', '+').Replace('_', '/');
        padded += (padded.Length % 4) switch
        {
            0 => string.Empty,
            2 => "==",
            3 => "=",
            _ => "invalid"
        };
        try
        {
            byte[] decoded = Convert.FromBase64String(padded);
            bool valid = decoded.Length == PacketKeyBytes;
            CryptographicOperations.ZeroMemory(decoded);
            return valid;
        }
        catch (FormatException)
        {
            return false;
        }
    }

    public static bool IsValidOperationId(string operationId)
    {
        if (operationId.Length != OperationIdLength
            || operationId.Any(static character =>
                character is not (>= 'A' and <= 'Z'
                    or >= 'a' and <= 'z'
                    or >= '0' and <= '9'
                    or '-'
                    or '_')))
        {
            return false;
        }

        try
        {
            byte[] decoded = Convert.FromBase64String(
                operationId.Replace('-', '+').Replace('_', '/'));
            try
            {
                return decoded.Length == OperationIdBytes
                    && string.Equals(
                        Convert.ToBase64String(decoded)
                            .TrimEnd('=')
                            .Replace('+', '-')
                            .Replace('/', '_'),
                        operationId,
                        StringComparison.Ordinal);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(decoded);
            }
        }
        catch (FormatException)
        {
            return false;
        }
    }

    internal static void SetPrincipal(HttpContext context, AndroidLinkedV2GrantPrincipal principal)
        => context.Items[PrincipalItemKey] = principal;

    internal static bool TryGetPrincipal(HttpContext context, out AndroidLinkedV2GrantPrincipal? principal)
    {
        principal = context.Items.TryGetValue(PrincipalItemKey, out object? value)
            ? value as AndroidLinkedV2GrantPrincipal
            : null;
        return principal is not null;
    }

    internal static void SetAuthorizedRequest(
        HttpContext context,
        AndroidLinkedV2AuthorizedRequest authorizedRequest)
        => context.Items[AuthorizedRequestItemKey] = authorizedRequest;

    internal static bool TryGetAuthorizedRequest(
        HttpContext context,
        out AndroidLinkedV2AuthorizedRequest? authorizedRequest)
    {
        authorizedRequest = context.Items.TryGetValue(AuthorizedRequestItemKey, out object? value)
            ? value as AndroidLinkedV2AuthorizedRequest
            : null;
        return authorizedRequest is not null;
    }

    internal static void SetRefreshRetryResult(
        HttpContext context,
        AndroidLinkedV2GrantRotationResult result)
        => context.Items[RefreshRetryResultItemKey] = result;

    internal static bool TryGetRefreshRetryResult(
        HttpContext context,
        out AndroidLinkedV2GrantRotationResult? result)
    {
        result = context.Items.TryGetValue(RefreshRetryResultItemKey, out object? value)
            ? value as AndroidLinkedV2GrantRotationResult
            : null;
        return result is not null;
    }

    internal static string CreateAuthorizedRequestSha256(
        string method,
        string path,
        string installationId,
        string grantId,
        long issuedAtUnixSeconds,
        string packetKey,
        string signature,
        byte[] body)
    {
        byte[] canonical = CreateCanonicalPayload(
            method,
            path,
            installationId,
            grantId,
            issuedAtUnixSeconds,
            packetKey,
            body);
        try
        {
            return InstallLinkingService.SecretSha256(string.Join(
                '\n',
                "chummer.android.authorized-request.v2",
                Convert.ToBase64String(canonical),
                signature));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(canonical);
        }
    }

    internal static string CreateStableOperationSha256(
        string method,
        string path,
        string operationId,
        ReadOnlySpan<byte> body)
    {
        string bodySha256 = Convert.ToHexString(SHA256.HashData(body)).ToLowerInvariant();
        return InstallLinkingService.SecretSha256(string.Join(
            '\n',
            "chummer.android.stable-operation.v2",
            method.ToUpperInvariant(),
            path,
            operationId,
            $"sha256:{bodySha256}"));
    }
}

public sealed class AndroidLinkedV2RequestProofVerifier
{
    public bool Verify(
        string publicKeySpkiBase64,
        string method,
        string path,
        string installationId,
        string grantId,
        long issuedAtUnixSeconds,
        string packetKey,
        string signatureBase64,
        byte[] body,
        DateTimeOffset now)
    {
        DateTimeOffset issuedAt;
        try
        {
            issuedAt = DateTimeOffset.FromUnixTimeSeconds(issuedAtUnixSeconds);
        }
        catch (ArgumentOutOfRangeException)
        {
            return false;
        }

        if (issuedAt < now - AndroidLinkedV2RequestProof.MaximumClockSkew
            || issuedAt > now + AndroidLinkedV2RequestProof.MaximumClockSkew
            || !AndroidLinkedV2RequestProof.IsValidPacketKey(packetKey)
            || string.IsNullOrWhiteSpace(publicKeySpkiBase64))
        {
            return false;
        }

        byte[]? publicKey = null;
        byte[]? signature = null;
        byte[]? canonical = null;
        try
        {
            publicKey = Convert.FromBase64String(publicKeySpkiBase64);
            signature = Convert.FromBase64String(signatureBase64);
            canonical = AndroidLinkedV2RequestProof.CreateCanonicalPayload(
                method,
                path,
                installationId,
                grantId,
                issuedAtUnixSeconds,
                packetKey,
                body);
            using RSA rsa = RSA.Create();
            rsa.ImportSubjectPublicKeyInfo(publicKey, out int bytesRead);
            return bytesRead == publicKey.Length
                && rsa.KeySize is >= 2048 and <= 4096
                && rsa.VerifyData(canonical, signature, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        }
        catch (Exception exception) when (
            exception is FormatException or CryptographicException or ArgumentException)
        {
            return false;
        }
        finally
        {
            if (publicKey is not null)
            {
                CryptographicOperations.ZeroMemory(publicKey);
            }
            if (signature is not null)
            {
                CryptographicOperations.ZeroMemory(signature);
            }
            if (canonical is not null)
            {
                CryptographicOperations.ZeroMemory(canonical);
            }
        }
    }
}

public sealed class AndroidLinkedV2RequestProofMiddleware(
    RequestDelegate next,
    ILogger<AndroidLinkedV2RequestProofMiddleware> logger)
{
    private const string LinkedPathPrefix = "/api/v2/android/linked";
    private static readonly HashSet<string> InstallLinkingPaths = new(StringComparer.OrdinalIgnoreCase)
    {
        "/api/v2/install-linking/grants/status",
        "/api/v2/install-linking/grants/refresh",
        "/api/v2/install-linking/grants/revoke",
        "/api/v2/install-linking/continuation/workspaces/list",
        "/api/v2/install-linking/continuation/workspaces/upsert"
    };

    public async Task InvokeAsync(
        HttpContext context,
        InstallLinkingService installLinking,
        AndroidLinkedV2RequestProofVerifier verifier,
        TimeProvider timeProvider)
    {
        string path = context.Request.Path.Value ?? string.Empty;
        if (!RequiresProof(context.Request.Method, path))
        {
            await next(context);
            return;
        }

        ApplyPrivateResponseHeaders(context.Response.Headers);
        if (context.Request.QueryString.HasValue)
        {
            await DenyAsync(context, StatusCodes.Status400BadRequest, "query-not-allowed");
            return;
        }

        byte[]? body = await ReadBodyAsync(context.Request, context.RequestAborted);
        if (body is null)
        {
            await DenyAsync(context, StatusCodes.Status413PayloadTooLarge, "body-too-large");
            return;
        }

        try
        {
            bool refreshPath = string.Equals(
                path,
                "/api/v2/install-linking/grants/refresh",
                StringComparison.OrdinalIgnoreCase);
            BodyInspection bodyInspection = InspectBody(body);
            if (bodyInspection.ContainsAccessToken)
            {
                await DenyAsync(context, StatusCodes.Status400BadRequest, "body-credential-forbidden");
                return;
            }
            if (!bodyInspection.Valid || bodyInspection.InstallationId is null)
            {
                await DenyAsync(context, StatusCodes.Status400BadRequest, "body-invalid");
                return;
            }
            if (refreshPath
                && (bodyInspection.OperationId is null
                    || !AndroidLinkedV2RequestProof.IsValidOperationId(bodyInspection.OperationId)))
            {
                await DenyAsync(context, StatusCodes.Status400BadRequest, "operation-invalid");
                return;
            }

            if (!TryReadBearer(context.Request, out string accessToken)
                || !TryReadSingleHeader(context.Request, AndroidLinkedV2RequestProof.SchemeHeader, 128, out string scheme)
                || !string.Equals(scheme, AndroidLinkedV2RequestProof.Scheme, StringComparison.Ordinal)
                || !TryReadSingleHeader(context.Request, AndroidLinkedV2RequestProof.InstallationHeader, 64, out string installationId)
                || !TryReadSingleHeader(context.Request, AndroidLinkedV2RequestProof.GrantHeader, 128, out string grantId)
                || !TryReadSingleHeader(context.Request, AndroidLinkedV2RequestProof.PacketKeyHeader, 64, out string packetKey)
                || !TryReadSingleHeader(context.Request, AndroidLinkedV2RequestProof.IssuedHeader, 32, out string issuedText)
                || !long.TryParse(issuedText, NumberStyles.None, CultureInfo.InvariantCulture, out long issuedAtUnixSeconds)
                || !TryReadSingleHeader(context.Request, AndroidLinkedV2RequestProof.SignatureHeader, 1024, out string signature)
                || !string.Equals(installationId, bodyInspection.InstallationId, StringComparison.Ordinal))
            {
                await DenyAsync(context, StatusCodes.Status401Unauthorized, "proof-header-invalid");
                return;
            }

            DateTimeOffset now = timeProvider.GetUtcNow();
            DateTimeOffset replayExpiry;
            try
            {
                replayExpiry = DateTimeOffset.FromUnixTimeSeconds(issuedAtUnixSeconds)
                    + AndroidLinkedV2RequestProof.MaximumClockSkew;
            }
            catch (ArgumentOutOfRangeException)
            {
                await DenyAsync(context, StatusCodes.Status401Unauthorized, "proof-invalid");
                return;
            }

            string requestSha256 = AndroidLinkedV2RequestProof.CreateAuthorizedRequestSha256(
                context.Request.Method,
                path,
                installationId,
                grantId,
                issuedAtUnixSeconds,
                packetKey,
                signature,
                body);
            string? operationSha256 = refreshPath
                ? AndroidLinkedV2RequestProof.CreateStableOperationSha256(
                    context.Request.Method,
                    path,
                    bodyInspection.OperationId!,
                    body)
                : null;
            AndroidLinkedV2GrantPrincipal? principal = installLinking.ResolveAndroidLinkedV2Grant(
                installationId,
                grantId,
                accessToken);
            AndroidLinkedV2RefreshRetryAuthorization? refreshRetry = null;
            if (principal is null && refreshPath)
            {
                refreshRetry = installLinking.ResolveAndroidLinkedV2RefreshRetry(
                    installationId,
                    grantId,
                    accessToken,
                    bodyInspection.OperationId!,
                    operationSha256!,
                    requestSha256,
                    now);
            }

            string? proofPublicKey = principal?.Installation.PublicKey ?? refreshRetry?.ProofPublicKey;
            if (string.IsNullOrWhiteSpace(proofPublicKey)
                || !verifier.Verify(
                    proofPublicKey,
                    context.Request.Method,
                    path,
                    installationId,
                    grantId,
                    issuedAtUnixSeconds,
                    packetKey,
                    signature,
                    body,
                    now))
            {
                await DenyAsync(context, StatusCodes.Status401Unauthorized, "proof-invalid");
                return;
            }

            bool acceptedReplayReceipt;
            try
            {
                acceptedReplayReceipt = installLinking.TryUseAndroidLinkedV2Proof(
                    grantId,
                    packetKey,
                    now,
                    replayExpiry);
            }
            catch (Exception)
            {
                // Replay authority is part of authentication. Do not dispatch or include
                // persistence/authority exception text in the response or admission log.
                await DenyAsync(
                    context,
                    StatusCodes.Status503ServiceUnavailable,
                    "replay-authority-unavailable");
                return;
            }
            if (!acceptedReplayReceipt)
            {
                await DenyAsync(context, StatusCodes.Status409Conflict, "proof-replay");
                return;
            }

            if (refreshRetry is not null)
            {
                AndroidLinkedV2RequestProof.SetRefreshRetryResult(context, refreshRetry.Result);
                RemoveCredentialHeaders(context.Request.Headers);
                await next(context);
                return;
            }

            if (principal is null)
            {
                await DenyAsync(context, StatusCodes.Status401Unauthorized, "proof-invalid");
                return;
            }

            AndroidLinkedV2RequestProof.SetPrincipal(context, principal);
            AndroidLinkedV2RequestProof.SetAuthorizedRequest(
                context,
                new AndroidLinkedV2AuthorizedRequest(
                    requestSha256,
                    InstallLinkingService.SecretSha256(accessToken),
                    now + InstallLinkingService.AndroidLinkedV2ResponseRecoveryLifetime,
                    bodyInspection.OperationId ?? string.Empty,
                    operationSha256 ?? string.Empty,
                    proofPublicKey));
            RemoveCredentialHeaders(context.Request.Headers);
            await next(context);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(body);
        }
    }

    private static bool RequiresProof(string method, string path)
        => HttpMethods.IsPost(method)
            && (new PathString(path).StartsWithSegments(LinkedPathPrefix, StringComparison.OrdinalIgnoreCase)
                || InstallLinkingPaths.Contains(path));

    private static async Task<byte[]?> ReadBodyAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        if (request.ContentLength > AndroidLinkedV2RequestProof.MaxBodyBytes)
        {
            return null;
        }

        request.EnableBuffering();
        request.Body.Position = 0;
        byte[] buffer = ArrayPool<byte>.Shared.Rent(16 * 1024);
        try
        {
            using MemoryStream payload = new();
            while (true)
            {
                int read = await request.Body.ReadAsync(buffer.AsMemory(0, buffer.Length), cancellationToken);
                if (read == 0)
                {
                    break;
                }
                if (payload.Length + read > AndroidLinkedV2RequestProof.MaxBodyBytes)
                {
                    request.Body.Position = 0;
                    return null;
                }
                await payload.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
            }
            request.Body.Position = 0;
            return payload.ToArray();
        }
        catch (IOException)
        {
            request.Body.Position = 0;
            return null;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(buffer);
            ArrayPool<byte>.Shared.Return(buffer);
        }
    }

    private static BodyInspection InspectBody(byte[] body)
    {
        try
        {
            using JsonDocument document = JsonDocument.Parse(body);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                return new BodyInspection(false, false, null, null);
            }

            bool containsAccessToken = ContainsProperty(document.RootElement, "accessToken");
            string? installationId = null;
            int installationIdPropertyCount = 0;
            bool canonicalInstallationIdProperty = true;
            string? operationId = null;
            int operationIdPropertyCount = 0;
            bool canonicalOperationIdProperty = true;
            foreach (JsonProperty property in document.RootElement.EnumerateObject())
            {
                if (string.Equals(property.Name, "installationId", StringComparison.OrdinalIgnoreCase))
                {
                    installationIdPropertyCount++;
                    canonicalInstallationIdProperty &= string.Equals(
                        property.Name,
                        "installationId",
                        StringComparison.Ordinal);
                    if (property.Value.ValueKind == JsonValueKind.String)
                    {
                        string? observed = property.Value.GetString();
                        if (observed is not null
                            && string.Equals(observed, observed.Trim(), StringComparison.Ordinal))
                        {
                            installationId = observed;
                        }
                    }
                }
                if (string.Equals(property.Name, "operationId", StringComparison.OrdinalIgnoreCase))
                {
                    operationIdPropertyCount++;
                    canonicalOperationIdProperty &= string.Equals(
                        property.Name,
                        "operationId",
                        StringComparison.Ordinal);
                    if (property.Value.ValueKind == JsonValueKind.String)
                    {
                        string? observed = property.Value.GetString();
                        if (observed is not null
                            && string.Equals(observed, observed.Trim(), StringComparison.Ordinal))
                        {
                            operationId = observed;
                        }
                    }
                }
            }

            bool validInstallation = installationIdPropertyCount == 1
                && canonicalInstallationIdProperty
                && installationId is { Length: > 0 and <= 64 };
            bool validOperation = operationIdPropertyCount is 0
                || operationIdPropertyCount == 1 && canonicalOperationIdProperty;
            return new BodyInspection(
                validInstallation && validOperation,
                containsAccessToken,
                installationId,
                operationId);
        }
        catch (JsonException)
        {
            return new BodyInspection(false, false, null, null);
        }
    }

    private static bool ContainsProperty(JsonElement element, string propertyName)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (string.Equals(property.Name, propertyName, StringComparison.OrdinalIgnoreCase)
                    || ContainsProperty(property.Value, propertyName))
                {
                    return true;
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement child in element.EnumerateArray())
            {
                if (ContainsProperty(child, propertyName))
                {
                    return true;
                }
            }
        }
        return false;
    }

    private static bool TryReadBearer(HttpRequest request, out string accessToken)
    {
        accessToken = string.Empty;
        if (!request.Headers.TryGetValue("Authorization", out StringValues values)
            || values.Count != 1
            || !AuthenticationHeaderValue.TryParse(values[0], out AuthenticationHeaderValue? authorization)
            || !string.Equals(authorization.Scheme, "Bearer", StringComparison.OrdinalIgnoreCase)
            || authorization.Parameter is not { Length: > 0 and <= 256 } token
            || token.Any(char.IsWhiteSpace))
        {
            return false;
        }
        accessToken = token;
        return true;
    }

    private static bool TryReadSingleHeader(HttpRequest request, string name, int maxLength, out string value)
    {
        value = string.Empty;
        if (!request.Headers.TryGetValue(name, out StringValues values) || values.Count != 1)
        {
            return false;
        }
        value = values[0]?.Trim() ?? string.Empty;
        return value.Length is > 0 && value.Length <= maxLength;
    }

    private static void RemoveCredentialHeaders(IHeaderDictionary headers)
    {
        headers.Remove("Authorization");
        headers.Remove(AndroidLinkedV2RequestProof.SignatureHeader);
    }

    private async Task DenyAsync(HttpContext context, int statusCode, string reasonCode)
    {
        logger.LogWarning(
            "Android linked v2 request denied ({ReasonCode}, {StatusCode}, {Surface}).",
            reasonCode,
            statusCode,
            SafeSurface(context.Request.Path));
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/problem+json; charset=utf-8";
        ApplyPrivateResponseHeaders(context.Response.Headers);
        await context.Response.WriteAsJsonAsync(new ProblemDetails
        {
            Status = statusCode,
            Title = statusCode switch
            {
                StatusCodes.Status400BadRequest => "Android v2 request is invalid.",
                StatusCodes.Status409Conflict => "Android v2 request proof was already used.",
                StatusCodes.Status413PayloadTooLarge => "Android v2 request is too large.",
                StatusCodes.Status503ServiceUnavailable => "Android v2 authorization is temporarily unavailable.",
                _ => "Android v2 authorization is missing or invalid."
            }
        }, cancellationToken: context.RequestAborted);
    }

    private static string SafeSurface(PathString path)
        => path.StartsWithSegments(LinkedPathPrefix, StringComparison.OrdinalIgnoreCase)
            ? "android-linked-v2"
            : "install-linking-v2";

    internal static void ApplyPrivateResponseHeaders(IHeaderDictionary headers)
    {
        headers.CacheControl = "private, no-store, no-cache, max-age=0";
        headers.Pragma = "no-cache";
        headers.Expires = "0";
        headers["Referrer-Policy"] = "no-referrer";
        headers["X-Content-Type-Options"] = "nosniff";
    }

    private sealed record BodyInspection(
        bool Valid,
        bool ContainsAccessToken,
        string? InstallationId,
        string? OperationId);
}

public sealed record AndroidLinkedV2GrantPrincipal(
    ClaimedInstallationDto Installation,
    string GrantId,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc);

internal sealed record AndroidLinkedV2AuthorizedRequest(
    string RequestSha256,
    string AccessTokenSha256,
    DateTimeOffset RecoveryExpiresAtUtc,
    string OperationId,
    string OperationSha256,
    string ProofPublicKey);

internal sealed record AndroidLinkedV2RefreshRetryAuthorization(
    AndroidLinkedV2GrantRotationResult Result,
    string ProofPublicKey);
