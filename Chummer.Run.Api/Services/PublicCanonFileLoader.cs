using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class PublicCanonFileLoader
{
    private const string DesignProductPrefix = "products/chummer/";
    private const string MirrorProductPrefix = ".codex-design/product/";
    private readonly IConfiguration _configuration;
    private readonly object _cacheLock = new();
    private readonly Dictionary<string, string> _resolvedPathCache = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, CachedTextDocument> _textCache = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, CachedYamlDocument> _yamlCache = new(StringComparer.OrdinalIgnoreCase);
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .WithDuplicateKeyChecking()
        .Build();

    public PublicCanonFileLoader(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public string ResolveRepoRoot(string requiredRelativePath)
    {
        var configured = _configuration["CHUMMER_PUBLIC_CANON_ROOT"];
        var candidates = new string?[]
        {
            configured,
            TryGetCurrentDirectory(),
            AppContext.BaseDirectory,
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..")),
            "/docker/chummercomplete/chummer.run-services",
            "/docker/chummercomplete/chummer-design",
            "/docker/chummercomplete/chummer-design-m114"
        }
        .Where(static path => !string.IsNullOrWhiteSpace(path))
        .Select(static path => Path.GetFullPath(path!))
        .Distinct(StringComparer.OrdinalIgnoreCase);

        foreach (var candidate in candidates)
        {
            foreach (string relativePathCandidate in ExpandRelativePathCandidates(requiredRelativePath))
            {
                string fullPath = Path.Combine(candidate, relativePathCandidate.Replace('/', Path.DirectorySeparatorChar));
                if (File.Exists(fullPath))
                {
                    return candidate;
                }
            }
        }

        throw new DirectoryNotFoundException($"Unable to resolve a repo root that contains '{requiredRelativePath}'.");
    }

    public string ResolveRequiredPath(string relativePath)
    {
        lock (_cacheLock)
        {
            if (_resolvedPathCache.TryGetValue(relativePath, out string? cachedPath) && File.Exists(cachedPath))
            {
                return cachedPath;
            }
        }

        string repoRoot = ResolveRepoRoot(relativePath);
        foreach (string relativePathCandidate in ExpandRelativePathCandidates(relativePath))
        {
            string fullPath = Path.Combine(repoRoot, relativePathCandidate.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(fullPath))
            {
                lock (_cacheLock)
                {
                    _resolvedPathCache[relativePath] = fullPath;
                }

                return fullPath;
            }
        }

        throw new FileNotFoundException($"required canon file not found: {relativePath}");
    }

    public T LoadRequiredYaml<T>(string relativePath)
    {
        string path = ResolveRequiredPath(relativePath);
        var info = new FileInfo(path);
        if (!info.Exists)
        {
            throw new FileNotFoundException($"required canon file not found: {path}");
        }

        string cacheKey = $"{typeof(T).AssemblyQualifiedName}\0{path}";
        lock (_cacheLock)
        {
            if (_yamlCache.TryGetValue(cacheKey, out CachedYamlDocument? cached) && cached.Matches(info))
            {
                return (T)cached.Document;
            }
        }

        try
        {
            using var reader = File.OpenText(path);
            T document = Deserializer.Deserialize<T>(reader)
                         ?? throw new InvalidOperationException($"canon file '{relativePath}' could not be deserialized.");
            lock (_cacheLock)
            {
                _yamlCache[cacheKey] = new CachedYamlDocument(info.LastWriteTimeUtc, info.Length, document);
            }

            return document;
        }
        catch (YamlDotNet.Core.YamlException ex)
        {
            throw new InvalidOperationException($"canon file '{relativePath}' is invalid: {ex.Message}", ex);
        }
    }

    public string LoadRequiredText(string relativePath)
    {
        string path = ResolveRequiredPath(relativePath);
        var info = new FileInfo(path);
        if (!info.Exists)
        {
            throw new FileNotFoundException($"required canon file not found: {path}");
        }

        lock (_cacheLock)
        {
            if (_textCache.TryGetValue(path, out CachedTextDocument? cached) && cached.Matches(info))
            {
                return cached.Text;
            }
        }

        string text = File.ReadAllText(path);
        lock (_cacheLock)
        {
            _textCache[path] = new CachedTextDocument(info.LastWriteTimeUtc, info.Length, text);
        }

        return text;
    }

    private static string? TryGetCurrentDirectory()
    {
        try
        {
            return Directory.GetCurrentDirectory();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    private static IEnumerable<string> ExpandRelativePathCandidates(string relativePath)
    {
        string normalized = relativePath.Replace('\\', '/');
        yield return normalized;

        if (normalized.StartsWith(DesignProductPrefix, StringComparison.OrdinalIgnoreCase))
        {
            yield return MirrorProductPrefix + normalized[DesignProductPrefix.Length..];
        }
        else if (normalized.StartsWith(MirrorProductPrefix, StringComparison.OrdinalIgnoreCase))
        {
            yield return DesignProductPrefix + normalized[MirrorProductPrefix.Length..];
        }
    }

    private sealed record CachedTextDocument(DateTime LastWriteUtc, long Length, string Text)
    {
        public bool Matches(FileInfo info)
            => info.LastWriteTimeUtc == LastWriteUtc && info.Length == Length;
    }

    private sealed record CachedYamlDocument(DateTime LastWriteUtc, long Length, object Document)
    {
        public bool Matches(FileInfo info)
            => info.LastWriteTimeUtc == LastWriteUtc && info.Length == Length;
    }
}
