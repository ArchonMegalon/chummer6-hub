using System.Net;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicProgressService
{
    private const string ReportJsonRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.json";
    private const string ReportHtmlRelativePath = ".codex-design/product/PROGRESS_REPORT.generated.html";
    private const string PosterSvgRelativePath = ".codex-design/product/PROGRESS_REPORT_POSTER.svg";
    private readonly IConfiguration _configuration;
    private readonly WeeklyProductPulseArtifactService _weeklyPulse;
    private readonly IReleaseTruthProjection _releaseTruth;
    private readonly IHttpContextAccessor _httpContextAccessor;
    private readonly ILogger<PublicProgressService> _logger;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public PublicProgressService(
        IConfiguration configuration,
        WeeklyProductPulseArtifactService weeklyPulse,
        IReleaseTruthProjection releaseTruth,
        IHttpContextAccessor httpContextAccessor,
        ILogger<PublicProgressService> logger)
    {
        _configuration = configuration;
        _weeklyPulse = weeklyPulse;
        _releaseTruth = releaseTruth;
        _httpContextAccessor = httpContextAccessor;
        _logger = logger;
    }

    public string LoadReportJson()
        => AttachReleaseTruthJson(File.ReadAllText(ResolveRequiredPath(ReportJsonRelativePath)));

    public string LoadReportHtml()
        => AttachReleaseTruthHtml(File.ReadAllText(ResolveRequiredPath(ReportHtmlRelativePath)));

    public string LoadPosterSvg()
        => AttachReleaseTruthSvg(File.ReadAllText(ResolveRequiredPath(PosterSvgRelativePath)));

    public string LoadWeeklyPulseJson()
        => AttachReleaseTruthJson(_weeklyPulse.LoadWeeklyPulseJson());

    private string AttachReleaseTruthJson(string json)
    {
        PublicReleaseTruthProjectionDto projection = CurrentProjection();
        JsonNode? parsed = JsonNode.Parse(json);
        JsonObject root = parsed as JsonObject ?? new JsonObject { ["artifact"] = parsed };
        root["releaseTruth"] = JsonSerializer.SerializeToNode(projection, JsonOptions);
        return root.ToJsonString(JsonOptions);
    }

    private string AttachReleaseTruthHtml(string html)
    {
        PublicReleaseTruthProjectionDto projection = CurrentProjection();
        string projectionJson = JsonSerializer.Serialize(projection, JsonOptions);
        string banner = projection.ReviewBannerRequired
            ? $"<section data-release-truth-banner=\"{WebUtility.HtmlEncode(projection.ReleaseDecisionStatus)}\" role=\"status\"><strong>Release review required</strong><p>Release routes remain inspectable, but installer handoffs and availability or stable-release claims are withheld until immutable release authority is ready.</p></section>"
            : string.Empty;
        string marker = $"<script id=\"chummer-release-truth\" type=\"application/json\">{projectionJson}</script>{banner}";
        int bodyTag = html.IndexOf("<body", StringComparison.OrdinalIgnoreCase);
        int bodyStart = bodyTag < 0 ? -1 : html.IndexOf('>', bodyTag);
        return bodyStart >= 0
            ? html.Insert(bodyStart + 1, marker)
            : marker + html;
    }

    private string AttachReleaseTruthSvg(string svg)
    {
        PublicReleaseTruthProjectionDto projection = CurrentProjection();
        string projectionJson = JsonSerializer.Serialize(projection, JsonOptions);
        string metadata = $"<metadata id=\"chummer-release-truth\">{WebUtility.HtmlEncode(projectionJson)}</metadata>";
        int svgTag = svg.IndexOf("<svg", StringComparison.OrdinalIgnoreCase);
        int svgStart = svgTag < 0 ? -1 : svg.IndexOf('>', svgTag);
        return svgStart >= 0
            ? svg.Insert(svgStart + 1, metadata)
            : svg;
    }

    private PublicReleaseTruthProjectionDto CurrentProjection()
        => PublicReleaseTruthProjectionMiddleware.TryGet(_httpContextAccessor.HttpContext)
           ?? _releaseTruth.Capture();

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
