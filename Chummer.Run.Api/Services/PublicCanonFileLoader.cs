using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class PublicCanonFileLoader
{
    private readonly IConfiguration _configuration;
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .IgnoreUnmatchedProperties()
        .Build();

    public PublicCanonFileLoader(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public string ResolveRepoRoot(string requiredRelativePath)
    {
        var configured = _configuration["CHUMMER_PUBLIC_CANON_ROOT"];
        var candidates = new[]
        {
            configured,
            Directory.GetCurrentDirectory(),
            AppContext.BaseDirectory,
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..")),
            "/docker/chummercomplete/chummer.run-services"
        }
        .Where(static path => !string.IsNullOrWhiteSpace(path))
        .Select(static path => Path.GetFullPath(path!))
        .Distinct(StringComparer.OrdinalIgnoreCase);

        foreach (var candidate in candidates)
        {
            if (File.Exists(Path.Combine(candidate, requiredRelativePath)))
            {
                return candidate;
            }
        }

        throw new DirectoryNotFoundException($"Unable to resolve a repo root that contains '{requiredRelativePath}'.");
    }

    public T LoadRequiredYaml<T>(string relativePath)
    {
        var repoRoot = ResolveRepoRoot(relativePath);
        var path = Path.Combine(repoRoot, relativePath);
        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"required canon file not found: {path}");
        }

        using var reader = File.OpenText(path);
        return Deserializer.Deserialize<T>(reader)
               ?? throw new InvalidOperationException($"canon file '{relativePath}' could not be deserialized.");
    }
}
