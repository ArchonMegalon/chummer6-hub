namespace Chummer.Run.Api.Services;

public sealed class PublicProgressService
{
    private const string ReportJsonRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.json";
    private const string ReportHtmlRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.html";
    private const string PosterSvgRelativePath = ".codex-design/product/PROGRESS_REPORT_POSTER.svg";
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicProgressService> _logger;

    public PublicProgressService(IConfiguration configuration, ILogger<PublicProgressService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public string LoadReportJson() => File.ReadAllText(ResolveRequiredPath(ReportJsonRelativePath));

    public string LoadReportHtml() => File.ReadAllText(ResolveRequiredPath(ReportHtmlRelativePath));

    public string LoadPosterSvg() => File.ReadAllText(ResolveRequiredPath(PosterSvgRelativePath));

    private string ResolveRequiredPath(string relativePath)
    {
        var repoRoot = ResolveRepoRoot(relativePath);
        var fullPath = Path.Combine(repoRoot, relativePath);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException($"public progress artifact not found: {fullPath}");
        }

        _logger.LogDebug("Loaded public progress artifact from {Path}", fullPath);
        return fullPath;
    }

    private string ResolveRepoRoot(params string[] requiredRelativePaths)
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
            if (requiredRelativePaths.All(relativePath => File.Exists(Path.Combine(candidate, relativePath))))
            {
                return candidate;
            }
        }

        throw new DirectoryNotFoundException("Unable to resolve a repo root that contains the mirrored public progress bundle.");
    }
}
