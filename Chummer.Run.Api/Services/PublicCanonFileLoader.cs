using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class PublicCanonFileLoader
{
    private const string DesignProductPrefix = "products/chummer/";
    private const string MirrorProductPrefix = ".codex-design/product/";
    private readonly IConfiguration _configuration;
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
        string repoRoot = ResolveRepoRoot(relativePath);
        foreach (string relativePathCandidate in ExpandRelativePathCandidates(relativePath))
        {
            string fullPath = Path.Combine(repoRoot, relativePathCandidate.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(fullPath))
            {
                return fullPath;
            }
        }

        throw new FileNotFoundException($"required canon file not found: {relativePath}");
    }

    public T LoadRequiredYaml<T>(string relativePath)
    {
        string path = ResolveRequiredPath(relativePath);
        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"required canon file not found: {path}");
        }

        try
        {
            using var reader = File.OpenText(path);
            return Deserializer.Deserialize<T>(reader)
                   ?? throw new InvalidOperationException($"canon file '{relativePath}' could not be deserialized.");
        }
        catch (YamlDotNet.Core.YamlException ex)
        {
            throw new InvalidOperationException($"canon file '{relativePath}' is invalid: {ex.Message}", ex);
        }
    }

    public string LoadRequiredText(string relativePath)
    {
        string path = ResolveRequiredPath(relativePath);
        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"required canon file not found: {path}");
        }

        return File.ReadAllText(path);
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
}
