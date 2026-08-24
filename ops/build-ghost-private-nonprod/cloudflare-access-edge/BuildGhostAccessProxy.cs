using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.Primitives;

namespace Chummer.BuildGhost.CloudflareAccessEdge;

public enum BuildGhostAccessRouteKind
{
    WorkspaceImport,
    WorkspaceLifecycle,
    ToolAccess,
    ProviderToolV2,
}

public readonly record struct BuildGhostAccessRoute(
    BuildGhostAccessRouteKind Kind,
    long MaximumBodyBytes);

public sealed class BuildGhostAccessProxy
{
    public const string AuthenticatedEmailHeader =
        "Cf-Access-Authenticated-User-Email";
    public const string JwtAssertionHeader = "Cf-Access-Jwt-Assertion";
    public const string OwnerHeader = "X-Chummer-Owner";
    public const string PortalOwnerHeader = "X-Chummer-Portal-Owner";
    public const string PortalOwnerTimestampHeader = "X-Chummer-Portal-Owner-Timestamp";
    public const string PortalOwnerSignatureHeader = "X-Chummer-Portal-Owner-Signature";
    public const string PortalModeratorSignatureHeader = "X-Chummer-Portal-Moderator-Signature";
    public const string ToolContractHeader = "X-Chummer-Build-Ghost-Tool-Contract";

    private const long ImportBodyLimit = 64L * 1024 * 1024;
    private const long ToolAccessBodyLimit = 4 * 1024;
    private const int ToolAccessResponseBodyLimit = 16 * 1024;
    private static readonly Uri PresentationOrigin = new(
        "http://chummer-build-ghost-presentation:8080",
        UriKind.Absolute);
    private static readonly Uri AiOrigin = new(
        "http://chummer-build-ghost-ai:8080",
        UriKind.Absolute);
    private static readonly Regex WorkspaceLifecyclePath = new(
        "^/api/workspaces/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex ToolAccessPath = new(
        "^/api/workspaces/[A-Za-z0-9][A-Za-z0-9._-]{0,127}/build-ghost/tool-access$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex NormalizedEmailPattern = new(
        "^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly HashSet<string> ForbiddenOwnerHeaders = new(
        [
            OwnerHeader,
            PortalOwnerHeader,
            PortalOwnerTimestampHeader,
            PortalOwnerSignatureHeader,
            PortalModeratorSignatureHeader,
        ],
        StringComparer.OrdinalIgnoreCase);

    private readonly AccessEdgeConfiguration _configuration;
    private readonly ICloudflareAccessTokenValidator _tokenValidator;
    private readonly HttpClient _presentationUpstream;
    private readonly HttpClient _aiUpstream;
    private readonly BuildGhostOwnerBoundGrantRegistry _grantRegistry;

    public BuildGhostAccessProxy(
        AccessEdgeConfiguration configuration,
        ICloudflareAccessTokenValidator tokenValidator,
        HttpClient upstream)
        : this(
            configuration,
            tokenValidator,
            upstream,
            upstream,
            new BuildGhostOwnerBoundGrantRegistry(TimeProvider.System))
    {
    }

    public BuildGhostAccessProxy(
        AccessEdgeConfiguration configuration,
        ICloudflareAccessTokenValidator tokenValidator,
        HttpClient presentationUpstream,
        HttpClient aiUpstream,
        BuildGhostOwnerBoundGrantRegistry grantRegistry)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _tokenValidator = tokenValidator ?? throw new ArgumentNullException(nameof(tokenValidator));
        _presentationUpstream = presentationUpstream ?? throw new ArgumentNullException(nameof(presentationUpstream));
        _aiUpstream = aiUpstream ?? throw new ArgumentNullException(nameof(aiUpstream));
        _grantRegistry = grantRegistry ?? throw new ArgumentNullException(nameof(grantRegistry));
    }

    public async Task HandleAsync(HttpContext context)
    {
        ApplyNoStore(context.Response);
        if (!HasExactHost(context.Request, _configuration.PublicHost)
            || !HasCanonicalTarget(context.Request)
            || !TryMatchRoute(
                context.Request.Method,
                context.Request.Path.Value ?? string.Empty,
                out BuildGhostAccessRoute route))
        {
            context.Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }

        if (!TryReadAccessHeaders(
                context.Request,
                out string authenticatedEmail,
                out string assertion)
            || !await _tokenValidator.ValidateAsync(
                assertion,
                authenticatedEmail,
                context.RequestAborted).ConfigureAwait(false))
        {
            await WriteFixedErrorAsync(
                context.Response,
                StatusCodes.Status401Unauthorized,
                "cloudflare_access_required",
                context.RequestAborted).ConfigureAwait(false);
            return;
        }

        if (context.Request.ContentLength is long contentLength
            && contentLength > route.MaximumBodyBytes)
        {
            await WriteFixedErrorAsync(
                context.Response,
                StatusCodes.Status413PayloadTooLarge,
                "request_body_too_large",
                context.RequestAborted).ConfigureAwait(false);
            return;
        }

        if (route.Kind is BuildGhostAccessRouteKind.WorkspaceImport
                or BuildGhostAccessRouteKind.ToolAccess
                or BuildGhostAccessRouteKind.ProviderToolV2
            && !HasJsonContentType(context.Request))
        {
            await WriteFixedErrorAsync(
                context.Response,
                StatusCodes.Status415UnsupportedMediaType,
                "application_json_required",
                context.RequestAborted).ConfigureAwait(false);
            return;
        }

        try
        {
            if (route.Kind == BuildGhostAccessRouteKind.ToolAccess)
            {
                await IssueOwnerBoundGrantAsync(
                    context,
                    authenticatedEmail,
                    route.MaximumBodyBytes).ConfigureAwait(false);
                return;
            }

            if (route.Kind == BuildGhostAccessRouteKind.ProviderToolV2)
            {
                await DispatchOwnerBoundProviderToolAsync(
                    context,
                    authenticatedEmail,
                    route.MaximumBodyBytes).ConfigureAwait(false);
                return;
            }

            using HttpRequestMessage upstreamRequest = CreateUpstreamRequest(
                context.Request,
                authenticatedEmail,
                route);
            using HttpResponseMessage upstreamResponse = await _presentationUpstream.SendAsync(
                upstreamRequest,
                HttpCompletionOption.ResponseHeadersRead,
                context.RequestAborted).ConfigureAwait(false);
            await CopyResponseAsync(
                upstreamResponse,
                context.Response,
                context.RequestAborted).ConfigureAwait(false);
        }
        catch (RequestBodyLimitExceededException)
        {
            if (!context.Response.HasStarted)
            {
                await WriteFixedErrorAsync(
                    context.Response,
                    StatusCodes.Status413PayloadTooLarge,
                    "request_body_too_large",
                    context.RequestAborted).ConfigureAwait(false);
            }
        }
        catch (UpstreamResponseLimitExceededException)
        {
            if (!context.Response.HasStarted)
            {
                await WriteFixedErrorAsync(
                    context.Response,
                    StatusCodes.Status502BadGateway,
                    "private_tool_upstream_response_invalid",
                    context.RequestAborted).ConfigureAwait(false);
            }
        }
        catch (Exception exception) when (
            exception is HttpRequestException
                or IOException
                or TaskCanceledException)
        {
            if (!context.Response.HasStarted)
            {
                await WriteFixedErrorAsync(
                    context.Response,
                    StatusCodes.Status502BadGateway,
                    "private_workspace_upstream_unavailable",
                    context.RequestAborted).ConfigureAwait(false);
            }
        }
    }

    public static bool TryMatchRoute(
        string method,
        string path,
        out BuildGhostAccessRoute route)
    {
        route = default;
        if (string.Equals(method, "POST", StringComparison.Ordinal)
            && string.Equals(path, "/api/workspaces/import", StringComparison.Ordinal))
        {
            route = new BuildGhostAccessRoute(
                BuildGhostAccessRouteKind.WorkspaceImport,
                ImportBodyLimit);
            return true;
        }

        if (string.Equals(method, "POST", StringComparison.Ordinal)
            && ToolAccessPath.IsMatch(path))
        {
            route = new BuildGhostAccessRoute(
                BuildGhostAccessRouteKind.ToolAccess,
                ToolAccessBodyLimit);
            return true;
        }

        if (string.Equals(method, "POST", StringComparison.Ordinal)
            && string.Equals(path, BuildGhostProviderToolRequestContract.Path, StringComparison.Ordinal))
        {
            route = new BuildGhostAccessRoute(
                BuildGhostAccessRouteKind.ProviderToolV2,
                BuildGhostProviderToolRequestContract.MaximumBodyBytes);
            return true;
        }

        if ((string.Equals(method, "GET", StringComparison.Ordinal)
                || string.Equals(method, "DELETE", StringComparison.Ordinal))
            && WorkspaceLifecyclePath.IsMatch(path))
        {
            route = new BuildGhostAccessRoute(
                BuildGhostAccessRouteKind.WorkspaceLifecycle,
                0);
            return true;
        }

        return false;
    }

    public static bool TryReadAccessHeaders(
        HttpRequest request,
        out string authenticatedEmail,
        out string assertion)
    {
        authenticatedEmail = string.Empty;
        assertion = string.Empty;
        if (!TryReadExactlyOne(request.Headers, AuthenticatedEmailHeader, out string rawEmail)
            || !TryReadExactlyOne(request.Headers, JwtAssertionHeader, out assertion)
            || rawEmail.Length is < 3 or > 254
            || !string.Equals(rawEmail, rawEmail.Trim(), StringComparison.Ordinal)
            || !string.Equals(rawEmail, rawEmail.ToLowerInvariant(), StringComparison.Ordinal)
            || !NormalizedEmailPattern.IsMatch(rawEmail)
            || assertion.Length > CloudflareAccessJwtValidator.MaximumAssertionBytes)
        {
            return false;
        }

        authenticatedEmail = rawEmail;
        return true;
    }

    public static HttpRequestMessage CreateUpstreamRequest(
        HttpRequest request,
        string authenticatedEmail,
        BuildGhostAccessRoute route)
    {
        Uri destination = new(PresentationOrigin, request.Path.Value);
        HttpRequestMessage outgoing = new(new HttpMethod(request.Method), destination);
        outgoing.Headers.TryAddWithoutValidation(OwnerHeader, authenticatedEmail);
        outgoing.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "Accept", 1024);
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "Accept-Language", 1024);
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "If-Match", 512);
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "If-None-Match", 512);

        if (route.MaximumBodyBytes > 0)
        {
            outgoing.Content = new StreamContent(
                new BoundedReadStream(request.Body, route.MaximumBodyBytes));
            if (MediaTypeHeaderValue.TryParse(request.ContentType, out MediaTypeHeaderValue? contentType))
            {
                outgoing.Content.Headers.ContentType = contentType;
            }
        }

        return outgoing;
    }

    public static HttpRequestMessage CreateProviderToolUpstreamRequest(
        HttpRequest request,
        ReadOnlyMemory<byte> body,
        string toolContractDigest)
    {
        Uri destination = new(AiOrigin, BuildGhostProviderToolRequestContract.Path);
        HttpRequestMessage outgoing = new(HttpMethod.Post, destination);
        outgoing.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };
        outgoing.Headers.TryAddWithoutValidation(ToolContractHeader, toolContractDigest);
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "Accept", 1024);
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "Accept-Language", 1024);
        outgoing.Content = new ReadOnlyMemoryContent(body);
        outgoing.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json")
        {
            CharSet = "utf-8",
        };
        return outgoing;
    }

    private async Task IssueOwnerBoundGrantAsync(
        HttpContext context,
        string authenticatedEmail,
        long maximumBodyBytes)
    {
        byte[] requestBody = await ReadBoundedBodyAsync(
            context.Request.Body,
            maximumBodyBytes,
            context.RequestAborted).ConfigureAwait(false);
        byte[]? responseBody = null;
        try
        {
            using HttpRequestMessage upstreamRequest = CreateBufferedPresentationRequest(
                context.Request,
                authenticatedEmail,
                requestBody);
            using HttpResponseMessage upstreamResponse = await _presentationUpstream.SendAsync(
                upstreamRequest,
                HttpCompletionOption.ResponseHeadersRead,
                context.RequestAborted).ConfigureAwait(false);

            responseBody = await ReadBoundedBodyAsync(
                await upstreamResponse.Content.ReadAsStreamAsync(context.RequestAborted).ConfigureAwait(false),
                ToolAccessResponseBodyLimit,
                context.RequestAborted,
                isUpstreamResponse: true).ConfigureAwait(false);
            if (upstreamResponse.StatusCode != HttpStatusCode.OK)
            {
                await CopyBufferedResponseAsync(
                    upstreamResponse,
                    context.Response,
                    responseBody,
                    context.RequestAborted).ConfigureAwait(false);
                return;
            }

            if (!HasJsonContentType(upstreamResponse.Content.Headers.ContentType)
                || !BuildGhostProviderToolRequestContract.TryParseGrantResponse(
                    responseBody,
                    out BuildGhostToolAccessGrantResponse? grant)
                || grant is null
                || !_grantRegistry.TryRegister(
                    grant.PacketAccessKey,
                    authenticatedEmail,
                    grant.PacketDigest,
                    grant.ExpiresAtUtc))
            {
                await WriteFixedErrorAsync(
                    context.Response,
                    StatusCodes.Status502BadGateway,
                    "private_tool_grant_binding_failed",
                    context.RequestAborted).ConfigureAwait(false);
                return;
            }

            await CopyBufferedResponseAsync(
                upstreamResponse,
                context.Response,
                responseBody,
                context.RequestAborted).ConfigureAwait(false);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(requestBody);
            if (responseBody is not null)
            {
                CryptographicOperations.ZeroMemory(responseBody);
            }
        }
    }

    private async Task DispatchOwnerBoundProviderToolAsync(
        HttpContext context,
        string authenticatedEmail,
        long maximumBodyBytes)
    {
        if (context.Request.Headers.ContainsKey("Authorization")
            || context.Request.Headers.ContainsKey("Cookie")
            || !TryReadExactlyOne(
                context.Request.Headers,
                ToolContractHeader,
                out string suppliedContract)
            || !FixedEquals(suppliedContract, _configuration.ToolContractDigest)
            || !string.Equals(
                context.Request.Headers.CacheControl.ToString().Trim(),
                "no-store",
                StringComparison.OrdinalIgnoreCase))
        {
            await WriteFixedErrorAsync(
                context.Response,
                StatusCodes.Status401Unauthorized,
                "private_tool_contract_required",
                context.RequestAborted).ConfigureAwait(false);
            return;
        }

        byte[] requestBody = await ReadBoundedBodyAsync(
            context.Request.Body,
            maximumBodyBytes,
            context.RequestAborted).ConfigureAwait(false);
        byte[]? responseBody = null;
        try
        {
            if (!BuildGhostProviderToolRequestContract.TryParse(
                    requestBody,
                    out BuildGhostProviderToolRequest? providerRequest,
                    out IReadOnlyList<string> reasons)
                || providerRequest is null)
            {
                await WriteProviderValidationErrorAsync(
                    context.Response,
                    reasons,
                    context.RequestAborted).ConfigureAwait(false);
                return;
            }

            if (!_grantRegistry.TryClaim(
                    providerRequest.PacketAccessKey,
                    authenticatedEmail,
                    providerRequest.PacketDigest))
            {
                await WriteFixedErrorAsync(
                    context.Response,
                    StatusCodes.Status410Gone,
                    "private-tool-authority-rejected",
                    context.RequestAborted).ConfigureAwait(false);
                return;
            }

            using HttpRequestMessage upstreamRequest = CreateProviderToolUpstreamRequest(
                context.Request,
                requestBody,
                _configuration.ToolContractDigest);
            using HttpResponseMessage upstreamResponse = await _aiUpstream.SendAsync(
                upstreamRequest,
                HttpCompletionOption.ResponseHeadersRead,
                context.RequestAborted).ConfigureAwait(false);
            responseBody = await ReadBoundedBodyAsync(
                await upstreamResponse.Content.ReadAsStreamAsync(context.RequestAborted).ConfigureAwait(false),
                BuildGhostProviderToolRequestContract.MaximumResponseBytes,
                context.RequestAborted,
                isUpstreamResponse: true).ConfigureAwait(false);
            await CopyBufferedResponseAsync(
                upstreamResponse,
                context.Response,
                responseBody,
                context.RequestAborted).ConfigureAwait(false);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(requestBody);
            if (responseBody is not null)
            {
                CryptographicOperations.ZeroMemory(responseBody);
            }
        }
    }

    private static HttpRequestMessage CreateBufferedPresentationRequest(
        HttpRequest request,
        string authenticatedEmail,
        ReadOnlyMemory<byte> body)
    {
        Uri destination = new(PresentationOrigin, request.Path.Value);
        HttpRequestMessage outgoing = new(HttpMethod.Post, destination);
        outgoing.Headers.TryAddWithoutValidation(OwnerHeader, authenticatedEmail);
        outgoing.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "Accept", 1024);
        CopySingleSafeHeader(request.Headers, outgoing.Headers, "Accept-Language", 1024);
        outgoing.Content = new ReadOnlyMemoryContent(body);
        outgoing.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json")
        {
            CharSet = "utf-8",
        };
        return outgoing;
    }

    private static async Task<byte[]> ReadBoundedBodyAsync(
        Stream stream,
        long maximumBytes,
        CancellationToken cancellationToken,
        bool isUpstreamResponse = false)
    {
        if (maximumBytes < 0 || maximumBytes > int.MaxValue - 1)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumBytes));
        }

        byte[] buffer = new byte[checked((int)maximumBytes + 1)];
        int total = 0;
        try
        {
            while (total < buffer.Length)
            {
                int read = await stream.ReadAsync(
                    buffer.AsMemory(total, buffer.Length - total),
                    cancellationToken).ConfigureAwait(false);
                if (read == 0)
                {
                    break;
                }
                total += read;
            }

            if (total > maximumBytes)
            {
                if (isUpstreamResponse)
                {
                    throw new UpstreamResponseLimitExceededException();
                }
                throw new RequestBodyLimitExceededException();
            }

            return buffer.AsSpan(0, total).ToArray();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(buffer);
        }
    }

    private static async Task WriteProviderValidationErrorAsync(
        HttpResponse response,
        IReadOnlyList<string> reasons,
        CancellationToken cancellationToken)
    {
        response.StatusCode = StatusCodes.Status400BadRequest;
        response.ContentType = "application/json; charset=utf-8";
        ApplyNoStore(response);
        byte[] body = JsonSerializer.SerializeToUtf8Bytes(new
        {
            error = "private_tool_provider_request_invalid",
            reasons,
        });
        try
        {
            await response.Body.WriteAsync(body, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(body);
        }
    }

    private static bool FixedEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = Encoding.ASCII.GetBytes(right);
        try
        {
            return leftBytes.Length == rightBytes.Length
                && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(leftBytes);
            CryptographicOperations.ZeroMemory(rightBytes);
        }
    }

    public static bool IsForbiddenUpstreamHeader(string headerName)
        => ForbiddenOwnerHeaders.Contains(headerName)
            || string.Equals(headerName, AuthenticatedEmailHeader, StringComparison.OrdinalIgnoreCase)
            || string.Equals(headerName, JwtAssertionHeader, StringComparison.OrdinalIgnoreCase)
            || string.Equals(headerName, "Authorization", StringComparison.OrdinalIgnoreCase)
            || string.Equals(headerName, "Cookie", StringComparison.OrdinalIgnoreCase)
            || headerName.StartsWith("X-Forwarded-", StringComparison.OrdinalIgnoreCase)
            || headerName.StartsWith("Cf-", StringComparison.OrdinalIgnoreCase);

    private static bool HasExactHost(HttpRequest request, string expectedHost)
        => request.Headers.Host.Count == 1
            && string.Equals(request.Headers.Host[0], expectedHost, StringComparison.Ordinal);

    private static bool HasCanonicalTarget(HttpRequest request)
    {
        if (request.QueryString.HasValue)
        {
            return false;
        }

        string path = request.Path.Value ?? string.Empty;
        string? rawTarget = request.HttpContext.Features.Get<IHttpRequestFeature>()?.RawTarget;
        return rawTarget is not null
            && string.Equals(rawTarget, path, StringComparison.Ordinal)
            && !path.Contains('%', StringComparison.Ordinal)
            && !path.Contains('\\', StringComparison.Ordinal)
            && !path.Contains("//", StringComparison.Ordinal);
    }

    private static bool HasJsonContentType(HttpRequest request)
    {
        if (!MediaTypeHeaderValue.TryParse(request.ContentType, out MediaTypeHeaderValue? mediaType)
            || !HasJsonContentType(mediaType))
        {
            return false;
        }

        return true;
    }

    private static bool HasJsonContentType(MediaTypeHeaderValue? mediaType)
    {
        if (mediaType is null
            || !string.Equals(mediaType.MediaType, "application/json", StringComparison.OrdinalIgnoreCase)
            || mediaType.Parameters.Count > 1)
        {
            return false;
        }

        if (mediaType.Parameters.Count == 0)
        {
            return true;
        }

        NameValueHeaderValue parameter = mediaType.Parameters.Single();
        return string.Equals(parameter.Name, "charset", StringComparison.OrdinalIgnoreCase)
            && string.Equals(
                parameter.Value?.Trim('"'),
                "utf-8",
                StringComparison.OrdinalIgnoreCase);
    }

    private static bool TryReadExactlyOne(
        IHeaderDictionary headers,
        string name,
        out string value)
    {
        value = string.Empty;
        if (!headers.TryGetValue(name, out StringValues values)
            || values.Count != 1
            || string.IsNullOrWhiteSpace(values[0]))
        {
            return false;
        }

        value = values[0]!;
        return !value.Contains('\r', StringComparison.Ordinal)
            && !value.Contains('\n', StringComparison.Ordinal)
            && !value.Contains(',', StringComparison.Ordinal);
    }

    private static void CopySingleSafeHeader(
        IHeaderDictionary source,
        HttpRequestHeaders destination,
        string name,
        int maximumLength)
    {
        if (source.TryGetValue(name, out StringValues values)
            && values.Count == 1
            && values[0] is string value
            && value.Length <= maximumLength
            && !value.Contains('\r', StringComparison.Ordinal)
            && !value.Contains('\n', StringComparison.Ordinal))
        {
            destination.TryAddWithoutValidation(name, value);
        }
    }

    private static async Task CopyResponseAsync(
        HttpResponseMessage source,
        HttpResponse destination,
        CancellationToken cancellationToken)
    {
        destination.StatusCode = (int)source.StatusCode;
        ApplyNoStore(destination);
        CopyResponseHeader(source, destination, "ETag");
        CopyResponseHeader(source, destination, "Last-Modified");
        CopyResponseHeader(source, destination, "Retry-After");
        CopyResponseHeader(source, destination, "X-Chummer-Build-Ghost-Packet-Digest");
        if (source.Content.Headers.ContentType is not null)
        {
            destination.ContentType = source.Content.Headers.ContentType.ToString();
        }

        await source.Content.CopyToAsync(destination.Body, cancellationToken).ConfigureAwait(false);
    }

    private static async Task CopyBufferedResponseAsync(
        HttpResponseMessage source,
        HttpResponse destination,
        ReadOnlyMemory<byte> body,
        CancellationToken cancellationToken)
    {
        destination.StatusCode = (int)source.StatusCode;
        ApplyNoStore(destination);
        CopyResponseHeader(source, destination, "ETag");
        CopyResponseHeader(source, destination, "Last-Modified");
        CopyResponseHeader(source, destination, "Retry-After");
        CopyResponseHeader(source, destination, "X-Chummer-Build-Ghost-Packet-Digest");
        if (source.Content.Headers.ContentType is not null)
        {
            destination.ContentType = source.Content.Headers.ContentType.ToString();
        }

        await destination.Body.WriteAsync(body, cancellationToken).ConfigureAwait(false);
    }

    private static void CopyResponseHeader(
        HttpResponseMessage source,
        HttpResponse destination,
        string name)
    {
        IEnumerable<string>? values = null;
        if ((source.Headers.TryGetValues(name, out IEnumerable<string>? responseValues)
                && (values = responseValues) is not null)
            || (source.Content.Headers.TryGetValues(name, out IEnumerable<string>? contentValues)
                && (values = contentValues) is not null))
        {
            string[] materialized = values.ToArray();
            if (materialized.Length == 1)
            {
                destination.Headers[name] = materialized[0];
            }
        }
    }

    private static void ApplyNoStore(HttpResponse response)
    {
        response.Headers.CacheControl = "no-store";
        response.Headers.Pragma = "no-cache";
        response.Headers["X-Content-Type-Options"] = "nosniff";
    }

    private static async Task WriteFixedErrorAsync(
        HttpResponse response,
        int statusCode,
        string error,
        CancellationToken cancellationToken)
    {
        if (response.HasStarted)
        {
            return;
        }

        response.StatusCode = statusCode;
        response.ContentType = "application/json; charset=utf-8";
        ApplyNoStore(response);
        string body = $"{{\"error\":\"{error}\"}}";
        await response.WriteAsync(body, Encoding.UTF8, cancellationToken).ConfigureAwait(false);
    }

    private sealed class BoundedReadStream : Stream
    {
        private readonly Stream _inner;
        private readonly long _limit;
        private long _read;

        public BoundedReadStream(Stream inner, long limit)
        {
            _inner = inner;
            _limit = limit;
        }

        public override bool CanRead => _inner.CanRead;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position
        {
            get => _read;
            set => throw new NotSupportedException();
        }

        public override void Flush() => throw new NotSupportedException();
        public override int Read(byte[] buffer, int offset, int count)
        {
            int read = _inner.Read(buffer, offset, count);
            Account(read);
            return read;
        }

        public override async ValueTask<int> ReadAsync(
            Memory<byte> buffer,
            CancellationToken cancellationToken = default)
        {
            int read = await _inner.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
            Account(read);
            return read;
        }

        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        private void Account(int count)
        {
            _read = checked(_read + count);
            if (_read > _limit)
            {
                throw new RequestBodyLimitExceededException();
            }
        }
    }

    private sealed class RequestBodyLimitExceededException : IOException;
    private sealed class UpstreamResponseLimitExceededException : IOException;
}
