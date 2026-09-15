using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Net.Http.Headers;

namespace Chummer.Run.Api.Controllers;

/// <summary>
/// Opt-in private owner actions. Every operation supplies the original HTTP request
/// to the existing fresh bearer/account admission, never a cookie, provider packet
/// key, caller-issued owner stamp or cached principal. This does not enable ingress.
/// </summary>
[ApiController]
[Route("api/internal/rook/workspace")]
public sealed class RookWorkspaceToolController(
    IConfiguration configuration, IHostEnvironment environment, IServiceProvider services) : ControllerBase
{
    internal const int MaxRequestBytes = 8192;
    internal const int MaxResponseBytes = 64 * 1024;
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        NumberHandling = JsonNumberHandling.Strict,
        MaxDepth = 16
    };

    [HttpPost("consents")]
    [RequestSizeLimit(MaxRequestBytes)]
    public Task<IActionResult> Grant()
        => ExecuteAsync<RookWorkspaceConsentGrantRequestDto>(async (input, ct) =>
        {
            var consent = await services.GetRequiredService<RookWorkspaceReadAdmissionService>()
                .GrantAsync(Request, input.InstallationId, input.GrantId, input.WorkspaceId,
                    input.RemoteRevision, input.ServerToken, input.ContinuationDigest,
                    input.ExplicitConfirmation, input.ExpiresAtUtc, ct).ConfigureAwait(false);
            return RookWorkspaceConsentResponseDto.FromConsent(consent);
        }, HttpContext.RequestAborted);

    [HttpPost("consents/revoke")]
    [RequestSizeLimit(MaxRequestBytes)]
    public Task<IActionResult> Revoke()
        => ExecuteAsync<RookWorkspaceConsentRevokeRequestDto>(async (input, ct) =>
        {
            var consent = await services.GetRequiredService<RookWorkspaceReadAdmissionService>()
                .RevokeAsync(Request, input.ConsentId, input.ExpectedVersion, ct).ConfigureAwait(false);
            return RookWorkspaceConsentResponseDto.FromConsent(consent);
        }, HttpContext.RequestAborted);

    [HttpPost("read")]
    [RequestSizeLimit(MaxRequestBytes)]
    public Task<IActionResult> Read()
        => ExecuteAsync<RookWorkspaceRuleReadRequestDto>(async (input, ct) =>
        {
            var result = await services.GetRequiredService<RookWorkspaceRuleReadService>()
                .ResolveAsync(Request, input.InstallationId, input.GrantId, input.ConsentId,
                    input.ExpectedVersion, input.Intent, input.SavedSubjectId, input.Locale, ct)
                .ConfigureAwait(false);
            // Core disposal and final fresh admission have already completed. No
            // additional await, provider work or authority translation follows.
            return RookWorkspaceRuleReadResponseDto.FromResult(result);
        }, HttpContext.RequestAborted);

    private async Task<IActionResult> ExecuteAsync<T>(Func<T, CancellationToken, Task<object>> operation,
        CancellationToken ct) where T : class, IRookWorkspaceToolRequest
    {
        ApplyPrivateResponseHeaders();
        // Actions have no bound parameters, including CancellationToken: this also
        // avoids MVC form-value materialization before the manual media/body gate.
        // Do not resolve the runtime/admission or parse a body while disabled. The
        // production registration has already validated the private runtime inputs.
        if (configuration[PrivateRookRuntimeConfiguration.EnabledKey] != "true"
            || !environment.IsProduction()
            || configuration["CHUMMER_PUBLIC_DOWNLOAD_ONLY"] is not (null or "false")
            || services.GetService<IServiceProviderIsService>()?.IsService(typeof(RookWorkspaceRuleReadService)) != true)
            return Failure(StatusCodes.Status404NotFound);

        try
        {
            T input = await ReadBoundedRequestAsync<T>(ct).ConfigureAwait(false);
            object response = await operation(input, ct).ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            return SerializeBoundedResponse(response);
        }
        catch (RequestRejectedException exception) { return Failure(exception.StatusCode); }
        catch (HubRequestAuthException exception) { return Failure(SafeStatus(exception.StatusCode)); }
        catch (InstallLinkingOperationException exception) { return Failure(SafeStatus(exception.StatusCode)); }
        catch (BadHttpRequestException exception) { return Failure(SafeStatus(exception.StatusCode)); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            return Failure(499);
        }
        catch (JsonException) { return Failure(StatusCodes.Status400BadRequest); }
        catch (ArgumentException) { return Failure(StatusCodes.Status400BadRequest); }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException
            or InvalidOperationException or NotSupportedException)
        {
            // InvalidOperationException does not distinguish stale ownership from
            // unavailable storage. Never parse its message or reveal either detail.
            return Failure(StatusCodes.Status503ServiceUnavailable);
        }
    }

    private async Task<T> ReadBoundedRequestAsync<T>(CancellationToken ct) where T : class, IRookWorkspaceToolRequest
    {
        if (Request.QueryString.HasValue) throw new RequestRejectedException(StatusCodes.Status400BadRequest);
        if (Request.Headers.ContainsKey(HeaderNames.ContentEncoding)
            || !MediaTypeHeaderValue.TryParse(Request.ContentType, out var mediaType)
            || !string.Equals(mediaType.MediaType.Value, "application/json", StringComparison.OrdinalIgnoreCase)
            || mediaType.Parameters.Count > 1
            || mediaType.Parameters.Any(parameter =>
                !string.Equals(parameter.Name.Value, "charset", StringComparison.OrdinalIgnoreCase)
                || !string.Equals(parameter.Value.Value?.Trim('"'), "utf-8", StringComparison.OrdinalIgnoreCase)))
            throw new RequestRejectedException(StatusCodes.Status415UnsupportedMediaType);
        if (Request.ContentLength > MaxRequestBytes)
            throw new RequestRejectedException(StatusCodes.Status413PayloadTooLarge);

        byte[] bytes = new byte[MaxRequestBytes + 1];
        try
        {
            int length = 0;
            while (length < bytes.Length)
            {
                int read = await Request.Body.ReadAsync(bytes.AsMemory(length), ct).ConfigureAwait(false);
                if (read == 0) break;
                length += read;
            }
            if (length > MaxRequestBytes)
                throw new RequestRejectedException(StatusCodes.Status413PayloadTooLarge);
            using JsonDocument document = JsonDocument.Parse(bytes.AsMemory(0, length),
                new JsonDocumentOptions { MaxDepth = 4, CommentHandling = JsonCommentHandling.Disallow });
            if (document.RootElement.ValueKind != JsonValueKind.Object)
                throw new RequestRejectedException(StatusCodes.Status400BadRequest);
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (JsonProperty property in document.RootElement.EnumerateObject())
                if (!names.Add(property.Name)) throw new RequestRejectedException(StatusCodes.Status400BadRequest);
            T? input = document.RootElement.Deserialize<T>(JsonOptions);
            if (input is null || !input.IsValid()) throw new RequestRejectedException(StatusCodes.Status400BadRequest);
            return input;
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    internal FileContentResult SerializeBoundedResponse(object response)
    {
        byte[] bytes = new byte[MaxResponseBytes];
        try
        {
            // Complete serialization into a fixed-capacity buffer before any private
            // bytes reach the client. Oversized output cannot escape partially.
            using var stream = new MemoryStream(bytes, 0, bytes.Length, writable: true, publiclyVisible: false);
            stream.SetLength(0);
            using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions { MaxDepth = 16 }))
                JsonSerializer.Serialize(writer, response, response.GetType(), JsonOptions);
            return File(bytes.AsSpan(0, checked((int)stream.Length)).ToArray(), "application/json; charset=utf-8");
        }
        catch (Exception exception) when (exception is JsonException or ArgumentException or NotSupportedException)
        {
            throw new InstallLinkingOperationException(StatusCodes.Status503ServiceUnavailable,
                "The private Rook response is unavailable.");
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    private void ApplyPrivateResponseHeaders()
    {
        Response.Headers[HeaderNames.CacheControl] = "no-store, private";
        Response.Headers[HeaderNames.Pragma] = "no-cache";
        Response.Headers[HeaderNames.Expires] = "0";
        Response.Headers[HeaderNames.XContentTypeOptions] = "nosniff";
        Response.Headers["Referrer-Policy"] = "no-referrer";
    }

    private ObjectResult Failure(int status)
        => StatusCode(status, new { error = "The private Rook workspace operation could not be completed." });

    private static int SafeStatus(int status)
        => status is 400 or 401 or 403 or 404 or 409 or 413 or 415 or 429 or 503 ? status : 503;

    private sealed class RequestRejectedException(int statusCode) : Exception
    {
        internal int StatusCode { get; } = statusCode;
    }
}
