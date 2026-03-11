using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Gateway;

public interface IEvaluationStore
{
    EvaluationResult Add(EvaluationRequest request);
    EvaluationResult? TryGet(string requestId);
    IReadOnlyList<EvaluationResult> GetAll();
    PromptEvaluationRunResult Run(PromptEvaluationRunRequest request);
    PromptEvaluationRunResult? TryGetRun(string runId);
    IReadOnlyList<PromptEvaluationRunResult> GetRuns();
}

public sealed class EvaluationStore : IEvaluationStore
{
    private readonly ConcurrentDictionary<string, EvaluationResult> _results = new();
    private readonly ConcurrentDictionary<string, PromptEvaluationRunResult> _runs = new();
    private readonly IPromptRegistry _prompts;
    private readonly IProviderRouter _router;

    public EvaluationStore(IPromptRegistry prompts, IProviderRouter router)
    {
        _prompts = prompts;
        _router = router;
    }

    public EvaluationResult Add(EvaluationRequest request)
    {
        var accepted = request.Rating is >= 1 and <= 5;
        var flags = new List<string>();
        if (!accepted)
        {
            flags.Add("rating_out_of_range");
        }

        if (request.PromptLineage is null)
        {
            flags.Add("missing_prompt_lineage");
        }
        else
        {
            if (request.PromptLineage.DraftOnly)
            {
                flags.Add("draft_first_prompt");
            }

            if (request.PromptLineage.Grounding != PromptGroundingKind.None
                && string.IsNullOrWhiteSpace(request.PromptLineage.GroundingContext?.RuntimeFingerprint))
            {
                flags.Add("missing_runtime_fingerprint");
            }
        }

        var result = new EvaluationResult(
            RequestId: request.RequestId,
            Accepted: accepted,
            Flags: flags,
            PromptLineage: request.PromptLineage,
            EvaluationSuiteId: request.EvaluationSuiteId,
            Evaluator: request.Evaluator);
        _results.AddOrUpdate(request.RequestId, result, (_, _) => result);

        return result;
    }

    public EvaluationResult? TryGet(string requestId) =>
        _results.TryGetValue(requestId, out var result) ? result : null;

    public IReadOnlyList<EvaluationResult> GetAll() => _results.Values
        .OrderBy(result => result.RequestId, StringComparer.OrdinalIgnoreCase)
        .ToList();

    public PromptEvaluationRunResult Run(PromptEvaluationRunRequest request)
    {
        var cases = request.Cases?.ToArray() ?? Array.Empty<PromptEvaluationCase>();
        if (cases.Length == 0)
        {
            throw new ArgumentException("At least one evaluation case is required.");
        }

        var caseResults = new List<PromptEvaluationCaseResult>(cases.Length);
        foreach (var evaluationCase in cases)
        {
            var render = _prompts.Render(new PromptRenderRequest(
                TemplateName: evaluationCase.TemplateName,
                Inputs: evaluationCase.Inputs,
                Version: evaluationCase.Version ?? request.Version,
                GroundingContext: evaluationCase.GroundingContext,
                EvaluationLabel: request.SuiteId));
            var routeRequest = new ProviderRouteRequest(
                Purpose: $"evaluation:{request.SuiteId}:{evaluationCase.CaseId}",
                Prompt: render.RenderedText,
                StructuredOutput: request.StructuredOutput,
                MaxTokens: request.MaxTokens,
                SessionId: request.SuiteId,
                PreferredProvider: request.PreferredProvider,
                PromptLineage: render.Lineage);
            var decision = _router.Resolve(routeRequest);

            var flags = new List<string>();
            if (render.MissingInputs)
            {
                flags.AddRange(render.UnresolvedPlaceholders.Select(static placeholder => $"unresolved:{placeholder}"));
            }

            if (render.Lineage.Grounding != PromptGroundingKind.None
                && string.IsNullOrWhiteSpace(render.Lineage.GroundingContext?.RuntimeFingerprint))
            {
                flags.Add("missing_runtime_fingerprint");
            }

            var missingSignals = ResolveMissingSignals(render.RenderedText, evaluationCase.ExpectedSignals);
            flags.AddRange(missingSignals.Select(static signal => $"missing_signal:{signal}"));

            caseResults.Add(new PromptEvaluationCaseResult(
                CaseId: evaluationCase.CaseId,
                Label: evaluationCase.Label,
                Passed: flags.Count == 0,
                Flags: flags,
                Prompt: render,
                Decision: decision,
                MissingSignals: missingSignals));
        }

        var templateVersion = caseResults
            .Select(result => result.Prompt.Version)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .SingleOrDefault()
            ?? request.Version;
        var passedCases = caseResults.Count(result => result.Passed);
        var run = new PromptEvaluationRunResult(
            RunId: $"evalrun_{Guid.NewGuid():N}",
            SuiteId: request.SuiteId,
            TemplateName: request.TemplateName,
            TemplateVersion: templateVersion,
            Passed: passedCases == caseResults.Count,
            TotalCases: caseResults.Count,
            PassedCases: passedCases,
            ExecutedAtUtc: DateTimeOffset.UtcNow,
            Cases: caseResults);
        _runs[run.RunId] = run;
        return run;
    }

    public PromptEvaluationRunResult? TryGetRun(string runId) =>
        _runs.TryGetValue(runId, out var run) ? run : null;

    public IReadOnlyList<PromptEvaluationRunResult> GetRuns() => _runs.Values
        .OrderByDescending(run => run.ExecutedAtUtc)
        .ToList();

    private static IReadOnlyList<string> ResolveMissingSignals(string renderedText, string expectedSignals)
    {
        var signals = expectedSignals
            .Split([',', ';', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        if (signals.Length == 0)
        {
            return Array.Empty<string>();
        }

        return signals
            .Where(signal => renderedText.IndexOf(signal, StringComparison.OrdinalIgnoreCase) < 0)
            .ToArray();
    }
}
