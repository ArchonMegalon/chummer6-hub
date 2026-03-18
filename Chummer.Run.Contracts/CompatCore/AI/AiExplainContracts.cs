using Chummer.Contracts.Rulesets;

namespace Chummer.Contracts.AI;

public static class AiExplainApiOperations
{
    public const string ExplainValue = "explain-value";
}

public static class AiExplainEntryKinds
{
    public const string DerivedValue = "derived-value";
    public const string QuickActionAvailability = "quick-action-availability";
    public const string CapabilityDescriptor = "capability-descriptor";
}

public static class AiExplainFragmentKinds
{
    public const string Input = "input";
    public const string Constant = "constant";
    public const string ProviderStep = "provider-step";
    public const string Output = "output";
    public const string Warning = "warning";
    public const string Note = "note";
}

public static class AiExplainEnvelopeSchemas
{
    public const string ProvenanceV1 = "ai.explain.provenance.v1";
    public const string EvidenceV1 = "ai.explain.evidence.v1";
}

public sealed record AiExplainEvidencePointerProjection(
    string Kind,
    string Pointer,
    string? LabelKey = null,
    IReadOnlyList<RulesetExplainParameter>? LabelParameters = null,
    string? ProviderId = null,
    string? PackId = null,
    string? RuleId = null);

public sealed record AiExplainTraceStepProjection(
    string StepId,
    string ProviderId,
    string CapabilityId,
    string? PackId,
    string Category,
    string ExplanationKey,
    IReadOnlyList<RulesetExplainParameter> ExplanationParameters,
    decimal? Modifier = null,
    bool? Certain = null,
    string? RuleId = null,
    IReadOnlyList<AiExplainEvidencePointerProjection>? Evidence = null);

public sealed record AiExplainValueProvenanceProjection(
    string RuntimeFingerprint,
    string RulesetId,
    string EngineApiVersion,
    string CatalogKind,
    string RuntimeTitle,
    string? ProfileId = null,
    string? ProfileTitle = null,
    string? ProviderId = null,
    string? PackId = null,
    IReadOnlyList<string>? RulePacks = null,
    IReadOnlyDictionary<string, string>? ProviderBindings = null);

public sealed record AiExplainValueProvenanceEnvelopeProjection(
    string Schema,
    AiExplainValueProvenanceProjection Provenance,
    string? CapabilityId = null,
    string? ProviderId = null,
    string? PackId = null);

public sealed record AiExplainEvidenceEnvelopeProjection(
    string Schema,
    IReadOnlyList<AiExplainEvidencePointerProjection> Pointers,
    string? CapabilityId = null,
    string? ProviderId = null,
    string? PackId = null,
    bool Deterministic = true);

public sealed record AiExplainValueQuery(
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    string? CapabilityId = null,
    string? ExplainEntryId = null,
    string? RulesetId = null);

public sealed record AiExplainFragmentProjection(
    string Kind,
    string Key,
    IReadOnlyList<RulesetExplainParameter> Parameters,
    RulesetCapabilityValue? Value = null);

public sealed record AiExplainValueProjection(
    string ExplainEntryId,
    string Kind,
    string TitleKey,
    IReadOnlyList<RulesetExplainParameter> TitleParameters,
    string SummaryKey,
    IReadOnlyList<RulesetExplainParameter> SummaryParameters,
    string RuntimeFingerprint,
    string RulesetId,
    string? CharacterId = null,
    string? CapabilityId = null,
    string? InvocationKind = null,
    string? ProviderId = null,
    string? PackId = null,
    bool Explainable = false,
    bool SessionSafe = false,
    int? ProviderGasBudget = null,
    int? RequestGasBudget = null,
    IReadOnlyList<AiExplainFragmentProjection>? Fragments = null,
    IReadOnlyList<RulesetCapabilityDiagnostic>? Diagnostics = null,
    AiExplainValueProvenanceProjection? Provenance = null,
    IReadOnlyList<AiExplainTraceStepProjection>? Trace = null,
    IReadOnlyList<AiExplainEvidencePointerProjection>? Evidence = null,
    AiExplainValueProvenanceEnvelopeProjection? ProvenanceEnvelope = null,
    AiExplainEvidenceEnvelopeProjection? EvidenceEnvelope = null);
