using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Gateway;

public interface IPromptRegistry
{
    void Register(PromptTemplate template);
    PromptTemplate? Resolve(string name, string? version = null);
    IReadOnlyList<PromptTemplate> List();
    PromptRenderResult Render(PromptRenderRequest request);
}

public sealed class PromptRegistry : IPromptRegistry
{
    private static readonly Regex PlaceholderPattern = new("{{\\s*(?<key>[\\w\\.-]+)\\s*}}", RegexOptions.Compiled);
    private readonly ConcurrentDictionary<string, List<PromptTemplate>> _templates = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _seedLock = new();
    private bool _seeded;

    public void Register(PromptTemplate template)
    {
        _templates.AddOrUpdate(
            template.Name,
            static (_, value) => [value],
            static (_, existing, value) =>
            {
                existing.RemoveAll(template => string.Equals(template.Version, value.Version, StringComparison.OrdinalIgnoreCase));
                existing.Add(value);
                existing.Sort((left, right) => string.Compare(right.Version, left.Version, StringComparison.OrdinalIgnoreCase));
                return existing;
            },
            template);
    }

    public PromptTemplate? Resolve(string name, string? version = null)
    {
        EnsureSeeded();

        if (!_templates.TryGetValue(name, out var values) || values.Count == 0)
        {
            return null;
        }

        if (string.Equals(version, "latest", StringComparison.OrdinalIgnoreCase) || string.IsNullOrWhiteSpace(version))
        {
            return values[0];
        }

        return values.FirstOrDefault(template => string.Equals(template.Version, version, StringComparison.OrdinalIgnoreCase))
               ?? values[0];
    }

    public IReadOnlyList<PromptTemplate> List()
    {
        EnsureSeeded();

        return _templates
            .SelectMany(pair => pair.Value)
            .OrderBy(template => template.Name, StringComparer.OrdinalIgnoreCase)
            .ThenByDescending(template => template.Version)
            .ToList();
    }

    public PromptRenderResult Render(PromptRenderRequest request)
    {
        var template = Resolve(request.TemplateName, request.Version) ?? throw new ArgumentException($"Prompt template '{request.TemplateName}' not found.");

        var rendered = template.Content;
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(request.Inputs))
        {
            values = JsonSerializer.Deserialize<Dictionary<string, string>>(request.Inputs)
                     ?? new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var valuePair in values)
            {
                rendered = rendered.Replace($"{{{{{valuePair.Key}}}}}", valuePair.Value, StringComparison.Ordinal);
            }
        }

        if (request.GroundingContext is not null)
        {
            UpsertValue(values, "runtimeFingerprint", request.GroundingContext.RuntimeFingerprint);
            UpsertValue(values, "packProfileIds", request.GroundingContext.PackProfileIds);
            UpsertValue(values, "evidence", request.GroundingContext.EvidencePointers);
            UpsertValue(values, "retrievalScope", request.GroundingContext.RetrievalScope);
            UpsertValue(values, "sceneId", request.GroundingContext.SceneId);

            foreach (var valuePair in values)
            {
                rendered = rendered.Replace($"{{{{{valuePair.Key}}}}}", valuePair.Value, StringComparison.Ordinal);
            }
        }

        var unresolved = PlaceholderPattern.Matches(rendered)
            .Select(match => match.Groups["key"].Value)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        var lineage = new PromptLineage(
            TemplateName: template.Name,
            TemplateVersion: template.Version,
            Feature: template.Feature,
            Persona: template.Persona,
            DraftOnly: template.DraftOnly,
            Grounding: template.Grounding,
            GroundingContext: request.GroundingContext,
            PromptHash: ComputePromptHash(template.Name, template.Version, rendered, request.GroundingContext, request.EvaluationLabel),
            RenderedAtUtc: DateTimeOffset.UtcNow,
            Tags: template.Tags?.ToArray() ?? Array.Empty<string>());

        return new PromptRenderResult(
            TemplateName: template.Name,
            Version: template.Version,
            RenderedText: rendered,
            Lineage: lineage,
            MissingInputs: unresolved.Length > 0,
            UnresolvedPlaceholders: unresolved);
    }

    private void EnsureSeeded()
    {
        if (_seeded)
        {
            return;
        }

        lock (_seedLock)
        {
            if (_seeded)
            {
                return;
            }

            Register(new PromptTemplate(
                Name: "coach.system",
                Version: "1.0.0",
                Persona: "decker_contact",
                Content: "Use evidence and project a concise, actionable recommendation. Runtime {{runtimeFingerprint}}. Evidence {{evidence}}. Query {{query}}.",
                PersonaNote: "Grounded coaching only.",
                Feature: "coach",
                DraftOnly: true,
                Grounding: PromptGroundingKind.RuntimeFacts,
                Tags: ["grounded", "coach", "draft-first"]));

            Register(new PromptTemplate(
                Name: "coach.system",
                Version: "1.1.0",
                Persona: "decker_contact",
                Content: "You are a grounded coach draft path. Runtime {{runtimeFingerprint}}. Packs {{packProfileIds}}. Evidence {{evidence}}. Retrieval scope {{retrievalScope}}. Answer query {{query}} with concise operator guidance and confidence.",
                PersonaNote: "Flavor only; truth comes from runtime and retrieval.",
                Feature: "coach",
                DraftOnly: true,
                Grounding: PromptGroundingKind.RuntimeFacts,
                Tags: ["grounded", "coach", "draft-first", "traceable"]));

            Register(new PromptTemplate(
                Name: "briefcase.template",
                Version: "1.0.0",
                Persona: "editor",
                Content: "Generate a formal in-universe document draft using heading {{title}}, evidence {{evidence}}, and body {{payload}}.",
                PersonaNote: "Draft for approval.",
                Feature: "briefcase",
                DraftOnly: true,
                Grounding: PromptGroundingKind.LoreRetrieval,
                Tags: ["briefcase", "draft-first", "grounded"]));

            Register(new PromptTemplate(
                Name: "portrait.style",
                Version: "1.0.0",
                Persona: "lore_studio",
                Content: "Style family {{style}} with narrative consistency tokens {{tokens}}.",
                PersonaNote: "Style helper only.",
                Feature: "portrait",
                DraftOnly: true,
                Grounding: PromptGroundingKind.PersonaMemory,
                Tags: ["portrait", "style"]));

            Register(new PromptTemplate(
                Name: "spider.tactical-card",
                Version: "1.1.0",
                Persona: "ops_board",
                Content: "Create a tactical card draft for scene {{sceneId}} revision {{sceneRevision}} using runtime {{runtimeFingerprint}}, evidence {{evidence}}, ledger digest {{eventDigest}}, and observation {{observation}}.",
                PersonaNote: "Ops-first tactical card generation.",
                Feature: "spider",
                DraftOnly: true,
                Grounding: PromptGroundingKind.SessionLedger,
                Tags: ["spider", "tactical-card", "draft-first", "grounded"]));

            _seeded = true;
        }
    }

    private static string ComputePromptHash(
        string templateName,
        string templateVersion,
        string rendered,
        PromptGroundingContext? groundingContext,
        string? evaluationLabel)
    {
        var payload = JsonSerializer.Serialize(new
        {
            templateName,
            templateVersion,
            rendered,
            groundingContext,
            evaluationLabel
        });
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(payload));
        return Convert.ToHexString(hash);
    }

    private static void UpsertValue(IDictionary<string, string> values, string key, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            values[key] = value;
        }
    }

    private static void UpsertValue(IDictionary<string, string> values, string key, IReadOnlyList<string>? valuesToJoin)
    {
        if (valuesToJoin is { Count: > 0 })
        {
            values[key] = string.Join(", ", valuesToJoin);
        }
    }
}
