using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed record ReleaseUploadSession(
    string SessionId,
    DateTimeOffset ExpiresAtUtc,
    string BundleRoot);

public sealed record ReleaseUploadChunkResult(
    string RelativePath,
    int ChunkIndex,
    int TotalChunks,
    long BytesReceived,
    bool Completed);

public sealed class ReleaseBundleUploadSessionService
{
    private const string SessionsRootKey = "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT";
    private static readonly TimeSpan DefaultLifetime = TimeSpan.FromHours(6);

    private readonly IConfiguration _configuration;
    private readonly ILogger<ReleaseBundleUploadSessionService> _logger;

    public ReleaseBundleUploadSessionService(
        IConfiguration configuration,
        ILogger<ReleaseBundleUploadSessionService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public ReleaseUploadSession CreateSession()
    {
        PurgeExpiredSessions();

        string sessionId = Guid.NewGuid().ToString("N");
        string sessionRoot = Path.Combine(ResolveSessionsRoot(), sessionId);
        string bundleRoot = Path.Combine(sessionRoot, "bundle");
        Directory.CreateDirectory(bundleRoot);

        ReleaseUploadSession session = new(
            SessionId: sessionId,
            ExpiresAtUtc: DateTimeOffset.UtcNow.Add(DefaultLifetime),
            BundleRoot: bundleRoot);

        PersistMetadata(sessionRoot, session);
        return session;
    }

    public async Task<long> WriteFileAsync(
        string sessionId,
        string relativePath,
        Stream content,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(content);

        sessionId = CanonicalizeSessionId(sessionId);
        string targetPath = ResolveTargetPath(sessionId, relativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(targetPath)!);

        await using FileStream fileStream = new(
            targetPath,
            FileMode.Create,
            FileAccess.Write,
            FileShare.None,
            bufferSize: 81920,
            useAsync: true);
        await content.CopyToAsync(fileStream, cancellationToken);
        await fileStream.FlushAsync(cancellationToken);
        return new FileInfo(targetPath).Length;
    }

    public async Task<ReleaseUploadChunkResult> AppendChunkAsync(
        string sessionId,
        string relativePath,
        int chunkIndex,
        int totalChunks,
        Stream content,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(content);
        if (chunkIndex < 0)
        {
            throw new InvalidDataException("chunk index must be zero or greater.");
        }

        if (totalChunks <= 0)
        {
            throw new InvalidDataException("total chunks must be greater than zero.");
        }

        if (chunkIndex >= totalChunks)
        {
            throw new InvalidDataException("chunk index must be less than total chunks.");
        }

        string targetPath = ResolveTargetPath(sessionId, relativePath);
        string statePath = targetPath + ".uploadstate.json";
        string partialPath = targetPath + ".uploading";
        Directory.CreateDirectory(Path.GetDirectoryName(targetPath)!);

        ChunkUploadState state = LoadChunkState(statePath)
            ?? new ChunkUploadState(relativePath, totalChunks, 0);

        if (!string.Equals(state.RelativePath, relativePath, StringComparison.Ordinal))
        {
            throw new InvalidDataException("chunk upload state path mismatch.");
        }

        if (state.TotalChunks != totalChunks)
        {
            throw new InvalidDataException("chunk upload total mismatch.");
        }

        if (state.NextChunkIndex != chunkIndex)
        {
            throw new InvalidDataException($"expected chunk {state.NextChunkIndex} but received {chunkIndex} for {relativePath}.");
        }

        await using (FileStream fileStream = new(
            partialPath,
            FileMode.Append,
            FileAccess.Write,
            FileShare.None,
            bufferSize: 81920,
            useAsync: true))
        {
            await content.CopyToAsync(fileStream, cancellationToken);
            await fileStream.FlushAsync(cancellationToken);
        }

        long bytesReceived = new FileInfo(partialPath).Length;
        bool completed = chunkIndex + 1 == totalChunks;
        if (completed)
        {
            if (File.Exists(targetPath))
            {
                File.Delete(targetPath);
            }

            File.Move(partialPath, targetPath);
            if (File.Exists(statePath))
            {
                File.Delete(statePath);
            }
        }
        else
        {
            PersistChunkState(statePath, state with { NextChunkIndex = chunkIndex + 1 });
        }

        return new ReleaseUploadChunkResult(relativePath, chunkIndex, totalChunks, bytesReceived, completed);
    }

    public string ResolveBundleRoot(string sessionId)
        => ReadSessionMetadata(sessionId).BundleRoot;

    public void DeleteSession(string sessionId)
    {
        if (!TryCanonicalizeSessionId(sessionId, out string canonicalSessionId))
        {
            _logger.LogWarning("Release upload session delete rejected invalid session id.");
            return;
        }

        DeleteSessionPath(Path.Combine(ResolveSessionsRoot(), canonicalSessionId), canonicalSessionId);
    }

    private void DeleteSessionPath(string sessionRoot, string sessionIdForLog)
    {
        if (!Directory.Exists(sessionRoot))
        {
            return;
        }

        try
        {
            Directory.Delete(sessionRoot, recursive: true);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Release upload session cleanup failed for {SessionId}.", sessionIdForLog);
        }
    }

    private string ResolveTargetPath(string sessionId, string relativePath)
    {
        sessionId = CanonicalizeSessionId(sessionId);
        ReleaseUploadSession session = ReadSessionMetadata(sessionId);
        string sanitizedRelativePath = SanitizeRelativePath(relativePath);
        string fullPath = Path.GetFullPath(Path.Combine(session.BundleRoot, sanitizedRelativePath));
        string bundleRoot = Path.GetFullPath(session.BundleRoot);
        if (!fullPath.StartsWith(bundleRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) &&
            !string.Equals(fullPath, bundleRoot, StringComparison.Ordinal))
        {
            throw new InvalidDataException("upload path escapes the bundle root.");
        }

        return fullPath;
    }

    private string ResolveSessionsRoot()
    {
        string configured = (_configuration[SessionsRootKey] ?? string.Empty).Trim();
        string root = string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(Path.GetTempPath(), "chummer-release-upload-sessions")
            : configured;
        Directory.CreateDirectory(root);
        return root;
    }

    private static string SanitizeRelativePath(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath))
        {
            throw new InvalidDataException("upload path is required.");
        }

        string normalized = relativePath.Replace('\\', '/').Trim();
        if (normalized.StartsWith("/", StringComparison.Ordinal))
        {
            throw new InvalidDataException("upload path must be relative.");
        }

        string[] segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length == 0)
        {
            throw new InvalidDataException("upload path is required.");
        }

        if (segments.Any(segment => segment is "." or ".."))
        {
            throw new InvalidDataException("upload path contains invalid traversal segments.");
        }

        return Path.Combine(segments);
    }

    private ReleaseUploadSession ReadSessionMetadata(string sessionId)
    {
        sessionId = CanonicalizeSessionId(sessionId);

        string path = Path.Combine(ResolveSessionsRoot(), sessionId, "session.json");
        if (!File.Exists(path))
        {
            throw new InvalidDataException("upload session was not found.");
        }

        ReleaseUploadSession? session = JsonSerializer.Deserialize<ReleaseUploadSession>(File.ReadAllText(path));
        if (session is null)
        {
            throw new InvalidDataException("upload session metadata is invalid.");
        }

        if (!string.Equals(session.SessionId, sessionId, StringComparison.Ordinal))
        {
            DeleteSession(sessionId);
            throw new InvalidDataException("upload session metadata is invalid.");
        }

        if (session.ExpiresAtUtc <= DateTimeOffset.UtcNow)
        {
            try
            {
                DeleteSession(session.SessionId);
            }
            catch
            {
                // cleanup failure should not prevent caller from seeing a clear expiry error.
            }

            throw new InvalidDataException("upload session has expired.");
        }

        return session;
    }

    private void PurgeExpiredSessions()
    {
        string sessionsRoot = ResolveSessionsRoot();
        IEnumerable<string> sessionRoots;

        try
        {
            sessionRoots = Directory.EnumerateDirectories(sessionsRoot);
        }
        catch
        {
            return;
        }

        foreach (string sessionRoot in sessionRoots)
        {
            string path = Path.Combine(sessionRoot, "session.json");
            if (!File.Exists(path))
            {
                continue;
            }

            try
            {
                ReleaseUploadSession? candidate = JsonSerializer.Deserialize<ReleaseUploadSession>(File.ReadAllText(path));
                if (candidate is null)
                {
                    DeleteInvalidSessionDirectory(sessionRoot);
                    continue;
                }

                if (candidate.ExpiresAtUtc <= DateTimeOffset.UtcNow)
                {
                    DeleteInvalidSessionDirectory(sessionRoot);
                }
            }
            catch
            {
                DeleteInvalidSessionDirectory(sessionRoot);
            }
        }
    }

    private void DeleteInvalidSessionDirectory(string sessionRoot)
    {
        if (string.IsNullOrWhiteSpace(sessionRoot))
        {
            return;
        }

        if (!Directory.Exists(sessionRoot))
        {
            return;
        }

        try
        {
            Directory.Delete(sessionRoot, recursive: true);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Release upload session cleanup failed for path {SessionRoot}.", sessionRoot);
        }
    }

    private static bool TryCanonicalizeSessionId(string? sessionId, out string canonicalSessionId)
    {
        canonicalSessionId = string.Empty;
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return false;
        }

        if (!Guid.TryParse(sessionId, out Guid parsed))
        {
            return false;
        }

        canonicalSessionId = parsed.ToString("N");
        return true;
    }

    private static string CanonicalizeSessionId(string sessionId)
        => TryCanonicalizeSessionId(sessionId, out string canonical)
            ? canonical
            : throw new InvalidDataException("upload session id is required and must be a valid GUID.");

    private static void PersistMetadata(string sessionRoot, ReleaseUploadSession session)
        => File.WriteAllText(Path.Combine(sessionRoot, "session.json"), JsonSerializer.Serialize(session));

    private static ChunkUploadState? LoadChunkState(string statePath)
    {
        if (!File.Exists(statePath))
        {
            return null;
        }

        return JsonSerializer.Deserialize<ChunkUploadState>(File.ReadAllText(statePath));
    }

    private static void PersistChunkState(string statePath, ChunkUploadState state)
        => File.WriteAllText(statePath, JsonSerializer.Serialize(state));

    private sealed record ChunkUploadState(
        string RelativePath,
        int TotalChunks,
        int NextChunkIndex);
}
