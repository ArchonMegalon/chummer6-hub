using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Services;

public sealed record ReleaseUploadQuotaOptions
{
    public const long MiB = 1024L * 1024L;
    public const long GiB = 1024L * 1024L * 1024L;

    public long MaxChunkBytes { get; init; } = 64L * MiB;
    public long MaxRequestBytes { get; init; } = 65L * MiB;
    public int MaxPathBytes { get; init; } = 1024;
    public long MaxFileBytes { get; init; } = 4L * GiB;
    public int MaxChunksPerFile { get; init; } = 128;
    public int MaxFilesPerSession { get; init; } = 512;
    public long MaxSessionBytes { get; init; } = 16L * GiB;
    public int MaxActiveSessions { get; init; } = 8;
    public int MaxActiveSessionsPerAuthorization { get; init; } = 2;
    public long MaxSharedBytes { get; init; } = 32L * GiB;
    public long MinimumFreeBytes { get; init; } = 10L * GiB;
    public double MinimumFreeFraction { get; init; } = 0.10d;
    public TimeSpan JanitorInterval { get; init; } = TimeSpan.FromMinutes(5);
    public TimeSpan CompletedReceiptRetention { get; init; } = TimeSpan.FromDays(7);
    public bool DirectBundleUploadEnabled { get; init; }

    public static ReleaseUploadQuotaOptions FromConfiguration(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        var options = new ReleaseUploadQuotaOptions
        {
            MaxChunkBytes = ReadLong(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_CHUNK_BYTES", 64L * MiB),
            MaxRequestBytes = ReadLong(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_REQUEST_BYTES", 65L * MiB),
            MaxPathBytes = ReadInt(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_PATH_BYTES", 1024),
            MaxFileBytes = ReadLong(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_FILE_BYTES", 4L * GiB),
            MaxChunksPerFile = ReadInt(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_CHUNKS_PER_FILE", 128),
            MaxFilesPerSession = ReadInt(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_FILES_PER_SESSION", 512),
            MaxSessionBytes = ReadLong(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_SESSION_BYTES", 16L * GiB),
            MaxActiveSessions = ReadInt(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_ACTIVE_SESSIONS", 8),
            MaxActiveSessionsPerAuthorization = ReadInt(
                configuration,
                "CHUMMER_RELEASE_UPLOAD_MAX_ACTIVE_SESSIONS_PER_AUTHORIZATION",
                2),
            MaxSharedBytes = ReadLong(configuration, "CHUMMER_RELEASE_UPLOAD_MAX_SHARED_BYTES", 32L * GiB),
            MinimumFreeBytes = ReadNonNegativeLong(
                configuration,
                "CHUMMER_RELEASE_UPLOAD_MIN_FREE_BYTES",
                10L * GiB),
            MinimumFreeFraction = ReadDouble(configuration, "CHUMMER_RELEASE_UPLOAD_MIN_FREE_FRACTION", 0.10d),
            JanitorInterval = TimeSpan.FromSeconds(ReadInt(
                configuration,
                "CHUMMER_RELEASE_UPLOAD_JANITOR_INTERVAL_SECONDS",
                300)),
            CompletedReceiptRetention = TimeSpan.FromSeconds(ReadInt(
                configuration,
                "CHUMMER_RELEASE_UPLOAD_COMPLETED_RECEIPT_RETENTION_SECONDS",
                604800)),
            DirectBundleUploadEnabled = ReadBoolean(
                configuration,
                "CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED",
                defaultValue: false)
        };
        options.Validate();
        return options;
    }

    public void Validate()
    {
        if (DirectBundleUploadEnabled
            || MaxChunkBytes <= 0
            || MaxRequestBytes <= MaxChunkBytes
            || MaxPathBytes <= 0
            || MaxFileBytes < MaxChunkBytes
            || MaxChunksPerFile <= 0
            || MaxFilesPerSession <= 0
            || MaxSessionBytes < MaxFileBytes
            || MaxActiveSessions <= 0
            || MaxActiveSessionsPerAuthorization <= 0
            || MaxActiveSessionsPerAuthorization > MaxActiveSessions
            || MaxSharedBytes < MaxSessionBytes
            || MinimumFreeBytes < 0
            || !double.IsFinite(MinimumFreeFraction)
            || MinimumFreeFraction is < 0 or > 1
            || JanitorInterval <= TimeSpan.Zero
            || CompletedReceiptRetention <= TimeSpan.Zero)
        {
            throw new InvalidOperationException("release upload quota configuration is internally inconsistent.");
        }
    }

    private static long ReadLong(IConfiguration configuration, string key, long defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!long.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out long value) || value <= 0)
        {
            throw new InvalidOperationException($"{key} must be a positive integer byte count.");
        }

        return value;
    }

    private static int ReadInt(IConfiguration configuration, string key, int defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out int value) || value <= 0)
        {
            throw new InvalidOperationException($"{key} must be a positive integer.");
        }

        return value;
    }

    private static long ReadNonNegativeLong(
        IConfiguration configuration,
        string key,
        long defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!long.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out long value)
            || value < 0)
        {
            throw new InvalidOperationException($"{key} must be a non-negative integer byte count.");
        }

        return value;
    }

    private static double ReadDouble(IConfiguration configuration, string key, double defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out double value))
        {
            throw new InvalidOperationException($"{key} must be a decimal fraction.");
        }

        return value;
    }

    private static bool ReadBoolean(IConfiguration configuration, string key, bool defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!bool.TryParse(raw, out bool value))
        {
            throw new InvalidOperationException($"{key} must be 'true' or 'false'.");
        }

        return value;
    }
}

public sealed class ReleaseUploadQuotaException : Exception
{
    public ReleaseUploadQuotaException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; }
}

public sealed record ReleaseUploadStorageSpace(long TotalBytes, long AvailableBytes);

public interface IReleaseUploadStorageProbe
{
    ReleaseUploadStorageSpace GetSpace(string path);
}

public sealed class ReleaseUploadStorageProbe : IReleaseUploadStorageProbe
{
    public ReleaseUploadStorageSpace GetSpace(string path)
    {
        string fullPath = Path.GetFullPath(path);
        string root = Path.GetPathRoot(fullPath)
            ?? throw new IOException("release upload storage root could not be resolved.");
        var drive = new DriveInfo(root);
        return new ReleaseUploadStorageSpace(drive.TotalSize, drive.AvailableFreeSpace);
    }
}

public sealed record ReleaseUploadAuthorizationContext(
    ReleaseUploadTicketClaims? UploadTicketClaims,
    string AuthorizationBinding,
    bool SingleUseAuthorization,
    string Method,
    string Path,
    DateTimeOffset? AuthorizationExpiresAtUtc = null,
    ReleaseUploadCandidateAuthority? CandidateImportAuthority = null,
    bool AllowsPrivilegedReconciliation = false)
{
    internal static readonly object HttpContextItemKey = new();

    public bool Matches(HttpRequest request)
        => string.Equals(Method, request.Method, StringComparison.Ordinal)
           && string.Equals(Path, request.Path.Value, StringComparison.Ordinal);
}

public sealed class ReleaseUploadAuthorizationEvaluator
{
    public const string CandidateManifestSha256Header =
        "X-Chummer-Candidate-Manifest-Sha256";
    public const string CandidateInventorySha256Header =
        "X-Chummer-Candidate-Inventory-Sha256";
    public const string CandidateBundleIdentitySha256Header =
        "X-Chummer-Candidate-Bundle-Identity-Sha256";

    private readonly IConfiguration _configuration;
    private readonly ReleaseUploadTicketService _releaseUploadTickets;
    private readonly ReleaseUploadSnapshotAuthorityService _snapshotAuthority;

    public ReleaseUploadAuthorizationEvaluator(
        IConfiguration configuration,
        ReleaseUploadTicketService releaseUploadTickets)
        : this(
            configuration,
            releaseUploadTickets,
            new ReleaseUploadSnapshotAuthorityService(configuration))
    {
    }

    public ReleaseUploadAuthorizationEvaluator(
        IConfiguration configuration,
        ReleaseUploadTicketService releaseUploadTickets,
        ReleaseUploadSnapshotAuthorityService snapshotAuthority)
    {
        _configuration = configuration;
        _releaseUploadTickets = releaseUploadTickets;
        _snapshotAuthority = snapshotAuthority;
    }

    public ReleaseUploadAuthorizationContext? Evaluate(HttpRequest request)
    {
        string header = request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (providedToken.Length == 0)
        {
            return null;
        }

        ReleaseUploadTicketClaims? ticketClaims = null;
        string? credentialBinding = null;
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(expectedToken) && FixedTimeEquals(providedToken, expectedToken))
        {
            credentialBinding = $"internal:{providedToken}";
        }
        else if (_releaseUploadTickets.TryValidate(
                     providedToken,
                     out ReleaseUploadTicketClaims? validatedTicket)
                 && validatedTicket is not null)
        {
            ticketClaims = validatedTicket;
            credentialBinding = $"ticket:{ticketClaims.TicketId}";
        }
        if (credentialBinding is null)
        {
            return null;
        }

        ReleaseUploadSnapshotAuthority authority = _snapshotAuthority.Load();
        if (!authority.IsValid
            || string.IsNullOrWhiteSpace(authority.SnapshotSha256))
        {
            return null;
        }

        if (authority.ReleaseUploadAuthority)
        {
            return new ReleaseUploadAuthorizationContext(
                ticketClaims,
                HashAuthorizationBinding(
                    $"{credentialBinding}|snapshot:{authority.SnapshotSha256}|release-upload"),
                SingleUseAuthorization: ticketClaims is not null,
                request.Method,
                request.Path.Value ?? string.Empty,
                AuthorizationExpiresAtUtc: ticketClaims?.ExpiresAtUtc,
                CandidateImportAuthority: null,
                AllowsPrivilegedReconciliation: ticketClaims is null);
        }

        ReleaseUploadCandidateAuthority? candidate = authority.Candidate;
        if (!authority.CandidateImportAuthority
            || candidate is null
            || !TryReadCandidateRequest(request, out CandidateRequest? requested)
            || requested is null
            || !FixedTimeEquals(
                requested.ManifestSha256,
                candidate.Candidate.CanonicalManifestSha256)
            || !FixedTimeEquals(
                requested.InventorySha256,
                candidate.Candidate.InventorySha256)
            || !FixedTimeEquals(
                requested.BundleIdentitySha256,
                candidate.Candidate.BundleIdentitySha256))
        {
            return null;
        }
        DateTimeOffset expiresAt = ticketClaims is not null
                                   && ticketClaims.ExpiresAtUtc < candidate.ExpiresAtUtc
            ? ticketClaims.ExpiresAtUtc
            : candidate.ExpiresAtUtc;
        return new ReleaseUploadAuthorizationContext(
            ticketClaims,
            HashAuthorizationBinding(
                $"{credentialBinding}|snapshot:{authority.SnapshotSha256}|candidate:{candidate.Candidate.BundleIdentitySha256}"),
            SingleUseAuthorization: true,
            request.Method,
            request.Path.Value ?? string.Empty,
            AuthorizationExpiresAtUtc: expiresAt,
            CandidateImportAuthority: candidate,
            AllowsPrivilegedReconciliation: false);
    }

    private static bool TryReadCandidateRequest(
        HttpRequest request,
        out CandidateRequest? candidate)
    {
        candidate = null;
        string[] names =
        [
            CandidateManifestSha256Header,
            CandidateInventorySha256Header,
            CandidateBundleIdentitySha256Header
        ];
        if (names.Any(name => request.Headers[name].Count != 1))
        {
            return false;
        }
        string manifest = request.Headers[CandidateManifestSha256Header].ToString();
        string inventory = request.Headers[CandidateInventorySha256Header].ToString();
        string identity = request.Headers[CandidateBundleIdentitySha256Header].ToString();
        if (!IsLowercaseSha256(manifest)
            || !IsLowercaseSha256(inventory)
            || !IsLowercaseSha256(identity))
        {
            return false;
        }
        candidate = new CandidateRequest(manifest, inventory, identity);
        return true;
    }

    private static bool IsLowercaseSha256(string value)
        => value.Length == 64
           && value.All(static character => character is >= '0' and <= '9'
               or >= 'a' and <= 'f');

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private static string HashAuthorizationBinding(string value)
        => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private sealed record CandidateRequest(
        string ManifestSha256,
        string InventorySha256,
        string BundleIdentitySha256);
}

public sealed class ReleaseUploadAdmissionService
{
    private const UnixFileMode OwnerDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode OwnerFileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
    private readonly IConfiguration _configuration;
    private readonly ReleaseUploadQuotaOptions _options;

    public ReleaseUploadAdmissionService(
        IConfiguration configuration,
        ReleaseUploadQuotaOptions options)
    {
        _configuration = configuration;
        _options = options;
    }

    public ReleaseUploadAdmissionLease? TryAcquire(string authorizationBinding)
    {
        authorizationBinding = (authorizationBinding ?? string.Empty).Trim().ToLowerInvariant();
        if (authorizationBinding.Length != 64
            || authorizationBinding.Any(static value => !Uri.IsHexDigit(value)))
        {
            throw new InvalidDataException(
                "release upload admission binding must be a SHA-256 digest.");
        }

        string sessionsRoot = ResolveSessionsRoot();
        string admissionRoot = Path.Combine(sessionsRoot, ".admission");
        string authorizationRoot = Path.Combine(admissionRoot, "authorizations", authorizationBinding);
        string globalRoot = Path.Combine(admissionRoot, "global");
        EnsureOwnerOnlyDirectory(authorizationRoot);
        EnsureOwnerOnlyDirectory(globalRoot);

        FileStream? authorizationSlot = TryAcquireSlot(
            authorizationRoot,
            _options.MaxActiveSessionsPerAuthorization);
        if (authorizationSlot is null)
        {
            return null;
        }

        FileStream? globalSlot = null;
        try
        {
            globalSlot = TryAcquireSlot(globalRoot, _options.MaxActiveSessions);
            if (globalSlot is null)
            {
                authorizationSlot.Dispose();
                return null;
            }

            return new ReleaseUploadAdmissionLease(authorizationSlot, globalSlot);
        }
        catch
        {
            globalSlot?.Dispose();
            authorizationSlot.Dispose();
            throw;
        }
    }

    private string ResolveSessionsRoot()
    {
        string configured = (_configuration["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] ?? string.Empty).Trim();
        string root = string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(Path.GetTempPath(), "chummer-release-upload-sessions")
            : configured;
        EnsureOwnerOnlyDirectory(root);
        return root;
    }

    private static FileStream? TryAcquireSlot(string root, int count)
    {
        for (int index = 0; index < count; index++)
        {
            string path = Path.Combine(root, $"{index:D4}.lock");
            try
            {
                var options = new FileStreamOptions
                {
                    Mode = FileMode.OpenOrCreate,
                    Access = FileAccess.ReadWrite,
                    Share = FileShare.None
                };
                if (!OperatingSystem.IsWindows())
                {
                    options.UnixCreateMode = OwnerFileMode;
                }

                FileStream stream = new(path, options);
                EnsureOwnerOnlyFile(path);
                return stream;
            }
            catch (IOException)
            {
                // Another process owns this slot.
            }
        }

        return null;
    }

    private static void EnsureOwnerOnlyDirectory(string path)
    {
        if (Directory.Exists(path))
        {
            FileAttributes existing = File.GetAttributes(path);
            if ((existing & FileAttributes.Directory) == 0
                || (existing & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException(
                    "release upload admission storage must be a regular directory.");
            }
        }

        Directory.CreateDirectory(path);
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerDirectoryMode);
        }
    }

    private static void EnsureOwnerOnlyFile(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerFileMode);
        }
    }
}

public sealed class ReleaseUploadAdmissionLease : IDisposable
{
    private FileStream? _authorizationSlot;
    private FileStream? _globalSlot;

    internal ReleaseUploadAdmissionLease(FileStream authorizationSlot, FileStream globalSlot)
    {
        _authorizationSlot = authorizationSlot;
        _globalSlot = globalSlot;
    }

    public void Dispose()
    {
        _globalSlot?.Dispose();
        _globalSlot = null;
        _authorizationSlot?.Dispose();
        _authorizationSlot = null;
    }
}

public sealed class ReleaseUploadRequestGateMiddleware
{
    private readonly RequestDelegate _next;

    public ReleaseUploadRequestGateMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(
        HttpContext context,
        ReleaseUploadAuthorizationEvaluator authorizationEvaluator,
        ReleaseUploadAdmissionService admission,
        ReleaseUploadQuotaOptions options)
    {
        if (!TryMatch(context.Request, out ReleaseUploadRoute route))
        {
            await _next(context);
            return;
        }

        ReleaseUploadAuthorizationContext? authorization = authorizationEvaluator.Evaluate(context.Request);
        if (authorization is null)
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status401Unauthorized,
                "Release promotion authorization required",
                "internal release promotion authorization is required.",
                "https://chummer.run/problems/release-bundle/auth-required");
            return;
        }

        context.Items[ReleaseUploadAuthorizationContext.HttpContextItemKey] = authorization;

        if (route == ReleaseUploadRoute.DirectBundle)
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status409Conflict,
                "Direct release upload disabled",
                "Direct bundle promotion is disabled. Use a bound staged upload session so publication has a durable completion receipt.",
                "https://chummer.run/problems/release-bundle/staged-session-required");
            return;
        }

        bool hasMultipartBody = HasMultipartBody(route);
        if (!hasMultipartBody
            && route is not ReleaseUploadRoute.Complete and not ReleaseUploadRoute.Reconcile)
        {
            await _next(context);
            return;
        }

        if (hasMultipartBody && context.Request.ContentLength is null)
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status411LengthRequired,
                "Release upload length required",
                "a known Content-Length is required before release upload body admission.",
                "https://chummer.run/problems/release-bundle/length-required");
            return;
        }

        if (hasMultipartBody
            && (context.Request.ContentLength <= 0
                || context.Request.ContentLength > options.MaxRequestBytes))
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status413PayloadTooLarge,
                "Release upload body too large",
                $"release upload request bodies must be between 1 and {options.MaxRequestBytes} bytes.",
                "https://chummer.run/problems/release-bundle/payload-too-large");
            return;
        }

        if (hasMultipartBody)
        {
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

        ReleaseUploadAdmissionLease? lease;
        try
        {
            lease = admission.TryAcquire(authorization.AuthorizationBinding);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException)
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status507InsufficientStorage,
                "Release upload admission unavailable",
                "release upload shared storage admission is unavailable.",
                "https://chummer.run/problems/release-bundle/storage-unavailable");
            return;
        }

        if (lease is null)
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status429TooManyRequests,
                "Release upload admission busy",
                "the authenticated release upload admission limit is currently in use.",
                "https://chummer.run/problems/release-bundle/admission-busy");
            return;
        }

        using (lease)
        {
            await _next(context);
        }
    }

    internal static ReleaseUploadAuthorizationContext? RequireAuthorization(HttpContext context)
    {
        return context.Items.TryGetValue(ReleaseUploadAuthorizationContext.HttpContextItemKey, out object? value)
               && value is ReleaseUploadAuthorizationContext authorization
               && authorization.Matches(context.Request)
            ? authorization
            : null;
    }

    internal static bool TryMatch(HttpRequest request, out ReleaseUploadRoute route)
    {
        route = default;
        if (!HttpMethods.IsPost(request.Method))
        {
            return false;
        }

        string path = (request.Path.Value ?? string.Empty).TrimEnd('/');
        if (path.Equals("/api/internal/releases/bundles", StringComparison.OrdinalIgnoreCase))
        {
            route = ReleaseUploadRoute.DirectBundle;
            return true;
        }

        if (path.Equals("/api/internal/releases/upload-sessions", StringComparison.OrdinalIgnoreCase))
        {
            route = ReleaseUploadRoute.CreateSession;
            return true;
        }

        const string prefix = "/api/internal/releases/upload-sessions/";
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
            "files" => ReleaseUploadRoute.File,
            "chunks" => ReleaseUploadRoute.Chunk,
            "complete" => ReleaseUploadRoute.Complete,
            "reconcile" => ReleaseUploadRoute.Reconcile,
            _ => default
        };
        return route != default;
    }

    private static bool HasMultipartBody(ReleaseUploadRoute route)
        => route is ReleaseUploadRoute.DirectBundle or ReleaseUploadRoute.File or ReleaseUploadRoute.Chunk;

    private static async Task WriteProblemAsync(
        HttpContext context,
        int statusCode,
        string title,
        string detail,
        string type)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/problem+json; charset=utf-8";
        var problem = new ProblemDetails
        {
            Status = statusCode,
            Title = title,
            Detail = detail,
            Type = type,
            Instance = $"{context.Request.Path}#{context.TraceIdentifier}"
        };
        await JsonSerializer.SerializeAsync(
            context.Response.Body,
            problem,
            cancellationToken: context.RequestAborted);
    }

    internal enum ReleaseUploadRoute
    {
        None,
        DirectBundle,
        CreateSession,
        File,
        Chunk,
        Complete,
        Reconcile
    }
}

public sealed class ReleaseUploadExpiryJanitor : BackgroundService
{
    private readonly ReleaseBundleUploadSessionService _sessions;
    private readonly ReleaseUploadQuotaOptions _options;
    private readonly ILogger<ReleaseUploadExpiryJanitor> _logger;

    public ReleaseUploadExpiryJanitor(
        ReleaseBundleUploadSessionService sessions,
        ReleaseUploadQuotaOptions options,
        ILogger<ReleaseUploadExpiryJanitor> logger)
    {
        _sessions = sessions;
        _options = options;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(_options.JanitorInterval);
        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            try
            {
                _sessions.PurgeExpiredSessions();
            }
            catch (Exception ex)
            {
                _logger.LogWarning(
                    "Release upload expiry reconciliation failed ({ExceptionType}).",
                    ex.GetType().Name);
            }
        }
    }
}

public sealed class ReleaseUploadStoragePublicationReadinessProbe
    : IReleaseShelfPublicationReadinessProbe
{
    private readonly ReleaseBundleUploadSessionService _sessions;

    public ReleaseUploadStoragePublicationReadinessProbe(ReleaseBundleUploadSessionService sessions)
    {
        _sessions = sessions;
    }

    public string Name => HubDeepReadinessService.StorageAdmissionProbeName;

    public ValueTask<ReleaseShelfPublicationReadinessProbeResult> EvaluateAsync(
        ReleaseShelfSnapshot snapshot,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ReleaseUploadStorageReadiness readiness = _sessions.EvaluateStorageReadiness(cancellationToken);
        if (readiness.Ready)
        {
            readiness = _sessions.EvaluatePublicationDestinationReadiness(
                snapshot,
                completionBundleRoot: null,
                cancellationToken);
        }
        return ValueTask.FromResult(new ReleaseShelfPublicationReadinessProbeResult(
            readiness.Ready,
            readiness.Code));
    }
}
