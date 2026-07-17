using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Services;

public sealed record WindowsProofUploadAuthorizationContext(
    WindowsProofUploadTicketClaims? TicketClaims,
    string AuthorizationBinding,
    bool SingleUseAuthorization,
    DateTimeOffset? AuthorizationExpiresAtUtc,
    string Method,
    string Path)
{
    internal static readonly object HttpContextItemKey = new();

    public bool Matches(HttpRequest request)
        => string.Equals(Method, request.Method, StringComparison.Ordinal)
           && string.Equals(Path, request.Path.Value, StringComparison.Ordinal);
}

public sealed class WindowsProofUploadAuthorizationEvaluator
{
    private readonly IConfiguration _configuration;
    private readonly WindowsProofUploadTicketService _tickets;

    public WindowsProofUploadAuthorizationEvaluator(
        IConfiguration configuration,
        WindowsProofUploadTicketService tickets)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _tickets = tickets ?? throw new ArgumentNullException(nameof(tickets));
    }

    public WindowsProofUploadAuthorizationContext? Evaluate(HttpRequest request)
    {
        string header = request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        string provided = header[bearerPrefix.Length..].Trim();
        if (provided.Length == 0)
        {
            return null;
        }

        string internalToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (internalToken.Length > 0 && FixedTimeEquals(provided, internalToken))
        {
            return Build(
                claims: null,
                bindingMaterial: $"windows-proof:internal:{provided}",
                singleUse: false,
                expiresAtUtc: null,
                request);
        }

        if (_tickets.TryValidate(provided, out WindowsProofUploadTicketClaims? claims) && claims is not null)
        {
            return Build(
                claims,
                $"windows-proof:ticket:{claims.TicketId}",
                singleUse: true,
                claims.ExpiresAtUtc,
                request);
        }

        return null;
    }

    private static WindowsProofUploadAuthorizationContext Build(
        WindowsProofUploadTicketClaims? claims,
        string bindingMaterial,
        bool singleUse,
        DateTimeOffset? expiresAtUtc,
        HttpRequest request)
        => new(
            claims,
            Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(bindingMaterial))),
            singleUse,
            expiresAtUtc,
            request.Method,
            request.Path.Value ?? string.Empty);

    private static bool FixedTimeEquals(string left, string right)
        => CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(left),
            Encoding.UTF8.GetBytes(right));
}

/// <summary>
/// Performs authorization and bounded-body admission before MVC form parsing. It
/// recognizes only the independent Windows proof API namespace.
/// </summary>
public sealed class WindowsProofUploadRequestGateMiddleware
{
    private readonly RequestDelegate _next;

    public WindowsProofUploadRequestGateMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(
        HttpContext context,
        WindowsProofUploadAuthorizationEvaluator authorizationEvaluator,
        WindowsProofUploadOptions options)
    {
        if (!TryMatch(context.Request, out WindowsProofUploadRoute route))
        {
            await _next(context);
            return;
        }

        ApplyPrivateHeaders(context.Response.Headers);
        if (!options.Enabled || !options.CfAccessGated)
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status503ServiceUnavailable,
                "Windows proof upload lane disabled",
                "The Windows proof upload lane requires explicit enablement and a confirmed Cloudflare Access gate.",
                "https://chummer.run/problems/windows-proof-upload/disabled");
            return;
        }

        WindowsProofUploadAuthorizationContext? authorization = authorizationEvaluator.Evaluate(context.Request);
        if (authorization is null)
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status401Unauthorized,
                "Windows proof upload authorization required",
                "A Windows-proof-scoped upload ticket or internal operator token is required.",
                "https://chummer.run/problems/windows-proof-upload/auth-required");
            return;
        }

        context.Items[WindowsProofUploadAuthorizationContext.HttpContextItemKey] = authorization;
        if (route is WindowsProofUploadRoute.File or WindowsProofUploadRoute.Chunk)
        {
            if (context.Request.ContentLength is null)
            {
                await WriteProblemAsync(
                    context,
                    StatusCodes.Status411LengthRequired,
                    "Windows proof upload length required",
                    "A known Content-Length is required before upload body admission.",
                    "https://chummer.run/problems/windows-proof-upload/length-required");
                return;
            }

            if (context.Request.ContentLength <= 0 || context.Request.ContentLength > options.MaxRequestBytes)
            {
                await WriteProblemAsync(
                    context,
                    StatusCodes.Status413PayloadTooLarge,
                    "Windows proof upload body too large",
                    $"Request bodies must be between 1 and {options.MaxRequestBytes} bytes.",
                    "https://chummer.run/problems/windows-proof-upload/payload-too-large");
                return;
            }

            IHttpMaxRequestBodySizeFeature? bodySize = context.Features.Get<IHttpMaxRequestBodySizeFeature>();
            if (bodySize is { IsReadOnly: false })
            {
                bodySize.MaxRequestBodySize = options.MaxRequestBytes;
            }

            context.Features.Set<IFormFeature>(new FormFeature(context.Request, new FormOptions
            {
                MultipartBodyLengthLimit = options.MaxRequestBytes,
                ValueLengthLimit = options.MaxPathBytes,
                KeyLengthLimit = 128,
                MultipartHeadersLengthLimit = options.MaxPathBytes,
                MultipartBoundaryLengthLimit = 128
            }));
        }

        await _next(context);
    }

    internal static WindowsProofUploadAuthorizationContext? RequireAuthorization(HttpContext context)
        => context.Items.TryGetValue(WindowsProofUploadAuthorizationContext.HttpContextItemKey, out object? value)
           && value is WindowsProofUploadAuthorizationContext authorization
           && authorization.Matches(context.Request)
            ? authorization
            : null;

    internal static bool TryMatch(HttpRequest request, out WindowsProofUploadRoute route)
    {
        route = WindowsProofUploadRoute.None;
        if (!HttpMethods.IsPost(request.Method))
        {
            return false;
        }

        string path = (request.Path.Value ?? string.Empty).TrimEnd('/');
        const string collection = "/api/internal/windows-proof/upload-sessions";
        if (path.Equals(collection, StringComparison.OrdinalIgnoreCase))
        {
            route = WindowsProofUploadRoute.Create;
            return true;
        }

        string prefix = collection + "/";
        if (!path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string[] suffix = path[prefix.Length..].Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (suffix.Length != 2)
        {
            return false;
        }

        route = suffix[1].ToLowerInvariant() switch
        {
            "files" => WindowsProofUploadRoute.File,
            "chunks" => WindowsProofUploadRoute.Chunk,
            "complete" => WindowsProofUploadRoute.Complete,
            "reconcile" => WindowsProofUploadRoute.Reconcile,
            _ => WindowsProofUploadRoute.None
        };
        return route != WindowsProofUploadRoute.None;
    }

    private static void ApplyPrivateHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
        headers["Referrer-Policy"] = "no-referrer";
    }

    private static async Task WriteProblemAsync(
        HttpContext context,
        int statusCode,
        string title,
        string detail,
        string type)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/problem+json; charset=utf-8";
        await JsonSerializer.SerializeAsync(
            context.Response.Body,
            new ProblemDetails
            {
                Status = statusCode,
                Title = title,
                Detail = detail,
                Type = type,
                Instance = $"{context.Request.Path}#{context.TraceIdentifier}"
            },
            cancellationToken: context.RequestAborted);
    }

    internal enum WindowsProofUploadRoute
    {
        None,
        Create,
        File,
        Chunk,
        Complete,
        Reconcile
    }
}
