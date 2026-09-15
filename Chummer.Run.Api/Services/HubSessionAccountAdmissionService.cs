using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Identity;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Server-local, point-in-time observation of a fresh identity session and an
/// existing Hub account. It is not a credential, an OwnerContextStamp, or proof
/// of continuing authorization or revocation state. No public route consumes it.
/// </summary>
public sealed record HubSessionAccountObservation(
    string UserId,
    string SubjectId,
    string SessionId,
    DateTimeOffset ObservedAtUtc,
    DateTimeOffset ExpiresAtUtc);

/// <summary>
/// Introspects every explicit bearer independently. Does not use identity hints,
/// cookies, cached subjects, local test seeds, profile fetches or account writes.
/// </summary>
public sealed class HubSessionAccountAdmissionService
{
    internal const int MaximumResponseBytes = 64 * 1024;
    internal static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(10);
    private const int MaximumTokenBytes = 512;
    private const int MaximumIdentifierBytes = 128;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        MaxDepth = 16,
        NumberHandling = JsonNumberHandling.Strict,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow
    };
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly AccountService _accounts;
    private readonly TimeProvider _time;
    private readonly ILogger<HubSessionAccountAdmissionService> _logger;

    public HubSessionAccountAdmissionService(
        HttpClient httpClient,
        IConfiguration configuration,
        AccountService accounts,
        TimeProvider timeProvider,
        ILogger<HubSessionAccountAdmissionService>? logger = null)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _accounts = accounts;
        _time = timeProvider;
        _logger = logger ?? NullLogger<HubSessionAccountAdmissionService>.Instance;
    }

    public async Task<HubSessionAccountObservation> RequireAccountAsync(
        HttpRequest request,
        CancellationToken cancellationToken)
    {
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            string accessToken = ReadExplicitBearer(request);
            Uri endpoint = IntrospectionEndpoint();
            // ResponseHeadersRead means HttpClient.Timeout alone does not bound
            // body reads. Bound HTTP/body I/O and recheck after account lookup.
            // The store's synchronous lock is not cancellable: this is not a
            // hard whole-method wall-time guarantee.
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            deadline.CancelAfter(RequestTimeout);
            using var message = new HttpRequestMessage(HttpMethod.Post, endpoint)
            {
                Content = JsonContent.Create(new IdentityIntrospectionRequest(accessToken), options: JsonOptions)
            };
            using HttpResponseMessage response = await _httpClient.SendAsync(
                message, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
            if (response.StatusCode != HttpStatusCode.OK)
                throw Reject(response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden
                    ? StatusCodes.Status401Unauthorized : StatusCodes.Status503ServiceUnavailable);
            string? mediaType = response.Content.Headers.ContentType?.MediaType;
            if (mediaType is null
                || !(string.Equals(mediaType, "application/json", StringComparison.OrdinalIgnoreCase)
                    || mediaType.StartsWith("application/", StringComparison.OrdinalIgnoreCase)
                        && mediaType.EndsWith("+json", StringComparison.OrdinalIgnoreCase))
                || response.Content.Headers.ContentEncoding.Count != 0
                || response.Content.Headers.ContentLength > MaximumResponseBytes)
                throw Reject(StatusCodes.Status503ServiceUnavailable);

            byte[] bytes = new byte[MaximumResponseBytes + 1];
            int length = 0;
            using (Stream body = await response.Content.ReadAsStreamAsync(deadline.Token).ConfigureAwait(false))
            {
                while (length <= MaximumResponseBytes)
                {
                    int read = await body.ReadAsync(bytes.AsMemory(length, bytes.Length - length), deadline.Token)
                        .ConfigureAwait(false);
                    if (read == 0) break;
                    length += read;
                }
            }
            if (length == 0 || length > MaximumResponseBytes)
                throw Reject(StatusCodes.Status503ServiceUnavailable);
            IdentityIntrospectionResponse session = ReadIntrospection(bytes.AsMemory(0, length));
            deadline.Token.ThrowIfCancellationRequested();
            if (!session.Active || !ValidIdentifier(session.SubjectId) || !ValidIdentifier(session.SessionId)
                || session.ExpiresAtUtc is not DateTimeOffset expires || expires <= _time.GetUtcNow())
                throw Reject(StatusCodes.Status401Unauthorized);

            string? userId = _accounts.GetExistingCanonicalUserIdBySubject(session.SubjectId!);
            if (!ValidIdentifier(userId))
                throw Reject(StatusCodes.Status403Forbidden);

            deadline.Token.ThrowIfCancellationRequested();
            DateTimeOffset observedAt = _time.GetUtcNow();
            if (expires <= observedAt)
                throw Reject(StatusCodes.Status401Unauthorized);
            return new HubSessionAccountObservation(userId!, session.SubjectId!, session.SessionId!, observedAt, expires);
        }
        catch (AdmissionRejectedException exception)
        {
            throw SafeFailure(exception.StatusCode);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Do not retain a transport exception whose message may contain secrets.
            throw new OperationCanceledException("Session account admission was canceled.", cancellationToken);
        }
        catch (Exception)
        {
            throw SafeFailure(StatusCodes.Status503ServiceUnavailable);
        }
    }

    private Uri IntrospectionEndpoint()
    {
        string configured = _configuration["IDENTITY_SERVICE_BASE_URL"] ?? "http://chummer-run-identity:8080";
        if (!string.Equals(configured, configured.Trim(), StringComparison.Ordinal)
            || !Uri.TryCreate(configured, UriKind.Absolute, out Uri? baseUri)
            || baseUri.Scheme is not ("http" or "https")
            || baseUri.UserInfo.Length != 0 || baseUri.Query.Length != 0 || baseUri.Fragment.Length != 0)
            throw Reject(StatusCodes.Status503ServiceUnavailable);
        return new Uri(configured.TrimEnd('/') + "/api/v1/identity/introspect", UriKind.Absolute);
    }

    private static string ReadExplicitBearer(HttpRequest request)
    {
        if (request is null || !request.Headers.TryGetValue("Authorization", out var values) || values.Count != 1)
            throw Reject(StatusCodes.Status401Unauthorized);
        string? header = values[0];
        if (header is null || header.Length <= 7 || header.Length > MaximumTokenBytes + 7
            || !header.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
            throw Reject(StatusCodes.Status401Unauthorized);
        ReadOnlySpan<char> token = header.AsSpan(7);
        bool padding = false;
        foreach (char character in token)
        {
            if (character == '=') padding = true;
            else if (padding || !(char.IsAsciiLetterOrDigit(character) || character is '-' or '.' or '_' or '~' or '+' or '/'))
                throw Reject(StatusCodes.Status401Unauthorized);
        }
        if (token[0] == '=') throw Reject(StatusCodes.Status401Unauthorized);
        return token.ToString();
    }

    private static IdentityIntrospectionResponse ReadIntrospection(ReadOnlyMemory<byte> bytes)
    {
        using JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
        if (document.RootElement.ValueKind != JsonValueKind.Object)
            throw Reject(StatusCodes.Status503ServiceUnavailable);
        var fields = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (JsonProperty property in document.RootElement.EnumerateObject())
        {
            if (!fields.Add(property.Name))
                throw Reject(StatusCodes.Status503ServiceUnavailable);
        }
        if (!fields.Contains("active") || !fields.Contains("subjectId")
            || !fields.Contains("sessionId") || !fields.Contains("expiresAtUtc"))
            throw Reject(StatusCodes.Status503ServiceUnavailable);
        return document.RootElement.Deserialize<IdentityIntrospectionResponse>(JsonOptions)
            ?? throw Reject(StatusCodes.Status503ServiceUnavailable);
    }

    private static bool ValidIdentifier(string? value)
        => !string.IsNullOrWhiteSpace(value) && value.Length <= MaximumIdentifierBytes
            && Encoding.UTF8.GetByteCount(value) <= MaximumIdentifierBytes
            && !value.Any(character => char.IsWhiteSpace(character) || char.IsControl(character));

    private HubRequestAuthException SafeFailure(int statusCode)
    {
        _logger.LogWarning("Hub session account admission rejected ({StatusCode}).", statusCode);
        return new HubRequestAuthException(statusCode, statusCode switch
        {
            StatusCodes.Status401Unauthorized => "An active explicit bearer session is required.",
            StatusCodes.Status403Forbidden => "An existing Hub account is required.",
            _ => "Session account admission is unavailable."
        });
    }

    private static AdmissionRejectedException Reject(int statusCode) => new(statusCode);

    private sealed class AdmissionRejectedException(int statusCode) : Exception
    {
        public int StatusCode { get; } = statusCode;
    }
}
