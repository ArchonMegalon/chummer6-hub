namespace Chummer.Run.Api.Services;

public sealed class PublicProgressService
{
    private const string ReportJsonRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.json";
    private const string ReportHtmlRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.html";
    private const string PosterSvgRelativePath = ".codex-design/product/PROGRESS_REPORT_POSTER.svg";
    private readonly IConfiguration _configuration;
    private readonly WeeklyProductPulseArtifactService _weeklyPulse;
    private readonly ILogger<PublicProgressService> _logger;

    public PublicProgressService(
        IConfiguration configuration,
        WeeklyProductPulseArtifactService weeklyPulse,
        ILogger<PublicProgressService> logger)
    {
        _configuration = configuration;
        _weeklyPulse = weeklyPulse;
        _logger = logger;
    }

    public string LoadReportJson() => File.ReadAllText(ResolveRequiredPath(ReportJsonRelativePath));

    public string LoadReportHtml() => File.ReadAllText(ResolveRequiredPath(ReportHtmlRelativePath));

    public string LoadPosterSvg() => File.ReadAllText(ResolveRequiredPath(PosterSvgRelativePath));

    public string LoadWeeklyPulseJson() => _weeklyPulse.LoadWeeklyPulseJson();

    private string ResolveRequiredPath(string relativePath)
    {
        var repoRoot = ResolveRepoRoot(relativePath);
        var fullPath = PublicStrictConfiguredRoot.IsEnabled(_configuration)
            ? PublicStrictConfiguredRoot.ResolveContainedPath(repoRoot, relativePath)
            : Path.Combine(repoRoot, relativePath);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException($"public progress artifact not found: {fullPath}");
        }

        _logger.LogDebug("Loaded public progress artifact from {Path}", fullPath);
        return fullPath;
    }

    private string ResolveRepoRoot(params string[] requiredRelativePaths)
    {
        if (PublicStrictConfiguredRoot.IsEnabled(_configuration))
        {
            string strictRoot = PublicStrictConfiguredRoot.Require(_configuration);
            if (requiredRelativePaths.All(relativePath =>
                    File.Exists(PublicStrictConfiguredRoot.ResolveContainedPath(strictRoot, relativePath))))
            {
                return strictRoot;
            }

            throw new DirectoryNotFoundException(
                "Strict public canon root does not contain the mirrored public progress bundle.");
        }

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
