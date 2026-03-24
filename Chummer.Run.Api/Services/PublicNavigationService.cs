namespace Chummer.Run.Api.Services;

public sealed record PublicNavigationLink(
    string Label,
    string Href);

public sealed record PublicNavigationModel(
    IReadOnlyList<PublicNavigationLink> Primary,
    IReadOnlyList<PublicNavigationLink> Secondary,
    IReadOnlyList<PublicNavigationLink> Utility);

public sealed class PublicNavigationService
{
    private const string NavigationRelativePath = ".codex-design/product/PUBLIC_NAVIGATION.yaml";
    private readonly IConfiguration _configuration;

    public PublicNavigationService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public PublicNavigationModel LoadNavigation()
    {
        var path = Path.Combine(ResolveRepoRoot(), NavigationRelativePath);
        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"public navigation config not found: {path}");
        }

        var lines = File.ReadAllLines(path);
        return new PublicNavigationModel(
            Primary: ParseLinks(lines, "primary_nav"),
            Secondary: ParseLinks(lines, "secondary_nav"),
            Utility: ParseLinks(lines, "utility_nav"));
    }

    private string ResolveRepoRoot()
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
            if (File.Exists(Path.Combine(candidate, NavigationRelativePath)))
            {
                return candidate;
            }
        }

        throw new DirectoryNotFoundException("Unable to resolve a repo root that contains the public navigation config.");
    }

    private static IReadOnlyList<PublicNavigationLink> ParseLinks(IReadOnlyList<string> lines, string sectionName)
    {
        var results = new List<PublicNavigationLink>();
        var insideSection = false;
        Dictionary<string, string>? current = null;

        foreach (var rawLine in lines)
        {
            var line = StripComment(rawLine);
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            var indent = Indent(line);
            var trimmed = line.Trim();
            if (indent == 0)
            {
                if (string.Equals(trimmed, $"{sectionName}:", StringComparison.Ordinal))
                {
                    insideSection = true;
                    current = null;
                    continue;
                }

                if (insideSection)
                {
                    break;
                }
            }

            if (!insideSection)
            {
                continue;
            }

            if (indent == 2 && trimmed.StartsWith("- ", StringComparison.Ordinal))
            {
                current = new Dictionary<string, string>(StringComparer.Ordinal);
                ParseKeyValueInto(current, trimmed[2..].Trim());
                continue;
            }

            if (indent >= 4 && current is not null)
            {
                ParseKeyValueInto(current, trimmed);
                if (current.ContainsKey("label") && current.ContainsKey("href"))
                {
                    results.Add(new PublicNavigationLink(current["label"], current["href"]));
                    current = null;
                }
            }
        }

        return results;
    }

    private static void ParseKeyValueInto(Dictionary<string, string> target, string line)
    {
        var separator = line.IndexOf(':');
        if (separator <= 0)
        {
            return;
        }

        var key = line[..separator].Trim();
        var value = line[(separator + 1)..].Trim().Trim('"');
        if (!string.IsNullOrWhiteSpace(key))
        {
            target[key] = value;
        }
    }

    private static string StripComment(string line)
    {
        var index = line.IndexOf('#');
        return index >= 0 ? line[..index] : line;
    }

    private static int Indent(string line)
    {
        var count = 0;
        while (count < line.Length && line[count] == ' ')
        {
            count++;
        }

        return count;
    }
}
