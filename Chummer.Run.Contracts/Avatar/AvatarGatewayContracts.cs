using System.Collections.Frozen;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;

namespace Chummer.Run.Contracts.Avatar;

public static class AvatarGatewayContractVersions
{
    public const string SessionContextV1 = "chummer.avatar-session-context/v1";
    public const string ContextRequestV1 = "chummer.avatar-context-request/v1";
    public const string ContextResponseV1 = "chummer.avatar-context/v1";
    public const string RuleQuestionV1 = "chummer.avatar-rule-question/v1";
    public const string RuleAuthorityRequestV1 = "chummer.avatar-rule-authority-request/v1";
    public const string CoreTypedRuleAuthorityV1 = "chummer.core-typed-rule-authority/v1";
    public const string RuleAnswerV1 = "chummer.avatar-rule-answer/v1";
    public const string RevocationV1 = "chummer.avatar-context-revocation/v1";
    public const string ErrorV1 = "chummer.avatar-error/v1";
}

public static class AvatarGatewayScopes
{
    public const string RulesRead = "rules:read";
    public const string CharacterRead = "character:read";
    public const string BuildAnalyze = "build:analyze";
    public const string VariantPreview = "variant:preview";

    public static IReadOnlySet<string> Allowed { get; } = new[]
    {
        RulesRead,
        CharacterRead,
        BuildAnalyze,
        VariantPreview
    }.ToFrozenSet(StringComparer.Ordinal);
}

public static class AvatarGatewayStatuses
{
    public const string Ready = "ready";
    public const string Resolved = "resolved";
    public const string Unresolved = "unresolved";
    public const string Stale = "stale";
    public const string Conflict = "conflict";
    public const string Forbidden = "forbidden";
    public const string Unavailable = "unavailable";
}

public static class AvatarGatewayActionTypes
{
    public const string OpenRuleSource = "chummer.open_rule_source";
    public const string OpenWorkbenchRoute = "chummer.open_workbench_route";
    public const string PreviewBuildVariant = "chummer.preview_build_variant";
    public const string PreviewWizardChoice = "chummer.preview_wizard_choice";
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record AvatarContextMintRequest(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("owner_id")] string OwnerId,
    [property: JsonPropertyName("workspace_id")] string WorkspaceId,
    [property: JsonPropertyName("workspace_revision")] long WorkspaceRevision,
    [property: JsonPropertyName("character_id")] string CharacterId,
    [property: JsonPropertyName("campaign_id")] string? CampaignId,
    [property: JsonPropertyName("ruleset_id")] string RulesetId,
    [property: JsonPropertyName("runtime_fingerprint")] string RuntimeFingerprint,
    [property: JsonPropertyName("source_digest")] string SourceDigest,
    [property: JsonPropertyName("sourcebook_fingerprint")] string SourcebookFingerprint,
    [property: JsonPropertyName("custom_data_fingerprint")] string CustomDataFingerprint,
    [property: JsonPropertyName("gm_policy_fingerprint")] string GmPolicyFingerprint,
    [property: JsonPropertyName("scenario_id")] string ScenarioId,
    [property: JsonPropertyName("display_name")] string DisplayName,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("creation_state")] string CreationState,
    [property: JsonPropertyName("scopes")] IReadOnlyList<string> Scopes,
    [property: JsonPropertyName("ttl_seconds")] int TtlSeconds);

public sealed record AvatarSessionContextProjection(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("context_ref")] string ContextRef,
    [property: JsonPropertyName("ruleset")] string Ruleset,
    [property: JsonPropertyName("character_display_name")] string CharacterDisplayName,
    [property: JsonPropertyName("creation_state")] string CreationState,
    [property: JsonPropertyName("workspace_revision")] long WorkspaceRevision,
    [property: JsonPropertyName("runtime_fingerprint")] string RuntimeFingerprint,
    [property: JsonPropertyName("source_digest")] string SourceDigest,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("available_modes")] IReadOnlyList<string> AvailableModes,
    [property: JsonPropertyName("spoken_summary")] string SpokenSummary,
    [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record AvatarContextRequest(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("context_ref")] string ContextRef,
    [property: JsonPropertyName("scenario_id")] string ScenarioId,
    [property: JsonPropertyName("session_id")] string SessionId,
    [property: JsonPropertyName("nonce")] string Nonce,
    [property: JsonPropertyName("idempotency_key")] string IdempotencyKey);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record AvatarRuleQuestionRequest(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("context_ref")] string ContextRef,
    [property: JsonPropertyName("scenario_id")] string ScenarioId,
    [property: JsonPropertyName("session_id")] string SessionId,
    [property: JsonPropertyName("nonce")] string Nonce,
    [property: JsonPropertyName("idempotency_key")] string IdempotencyKey,
    [property: JsonPropertyName("question")] string Question,
    [property: JsonPropertyName("subject_id")] string? SubjectId);

public sealed record AvatarCalculationStep(
    [property: JsonPropertyName("step_id")] string StepId,
    [property: JsonPropertyName("expression")] string Expression,
    [property: JsonPropertyName("result")] string Result,
    [property: JsonPropertyName("source_anchor_ids")] IReadOnlyList<string> SourceAnchorIds);

public sealed record AvatarSourceAnchor(
    [property: JsonPropertyName("anchor_id")] string AnchorId,
    [property: JsonPropertyName("source_id")] string SourceId,
    [property: JsonPropertyName("localized_source_name")] string LocalizedSourceName,
    [property: JsonPropertyName("page")] int? Page,
    [property: JsonPropertyName("rule_id")] string RuleId,
    [property: JsonPropertyName("local_source_route")] string LocalSourceRoute);

public sealed record AvatarAllowedAction(
    [property: JsonPropertyName("action_id")] string ActionId,
    [property: JsonPropertyName("action_type")] string ActionType,
    [property: JsonPropertyName("route")] string? Route,
    [property: JsonPropertyName("requires_explicit_review")] bool RequiresExplicitReview);

public sealed record AvatarRuleAnswerEnvelope(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("spoken_answer")] string SpokenAnswer,
    [property: JsonPropertyName("short_answer")] string ShortAnswer,
    [property: JsonPropertyName("calculation_steps")] IReadOnlyList<AvatarCalculationStep> CalculationSteps,
    [property: JsonPropertyName("assumptions")] IReadOnlyList<string> Assumptions,
    [property: JsonPropertyName("applies_to_current_character")] bool AppliesToCurrentCharacter,
    [property: JsonPropertyName("source_anchors")] IReadOnlyList<AvatarSourceAnchor> SourceAnchors,
    [property: JsonPropertyName("allowed_actions")] IReadOnlyList<AvatarAllowedAction> AllowedActions,
    [property: JsonPropertyName("workspace_revision")] long WorkspaceRevision,
    [property: JsonPropertyName("runtime_fingerprint")] string RuntimeFingerprint,
    [property: JsonPropertyName("source_digest")] string SourceDigest,
    [property: JsonPropertyName("authority_request_digest")] string AuthorityRequestDigest,
    [property: JsonPropertyName("answer_digest")] string AnswerDigest,
    [property: JsonPropertyName("uncertainty_reason")] string? UncertaintyReason);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record AvatarContextRevocationRequest(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("context_ref")] string ContextRef,
    [property: JsonPropertyName("owner_id")] string OwnerId,
    [property: JsonPropertyName("workspace_id")] string WorkspaceId);

public sealed record AvatarContextRevocationReceipt(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("context_ref_digest")] string ContextRefDigest,
    [property: JsonPropertyName("revoked")] bool Revoked,
    [property: JsonPropertyName("revoked_at")] DateTimeOffset RevokedAt);

public sealed record AvatarGatewayErrorEnvelope(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("reason")] string Reason,
    [property: JsonPropertyName("retryable")] bool Retryable);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record AvatarRuleAuthorityRequest(
    [property: JsonPropertyName("contract_name")] string ContractName,
    [property: JsonPropertyName("owner_id")] string OwnerId,
    [property: JsonPropertyName("workspace_id")] string WorkspaceId,
    [property: JsonPropertyName("workspace_revision")] long WorkspaceRevision,
    [property: JsonPropertyName("character_id")] string CharacterId,
    [property: JsonPropertyName("campaign_id")] string? CampaignId,
    [property: JsonPropertyName("ruleset_id")] string RulesetId,
    [property: JsonPropertyName("runtime_fingerprint")] string RuntimeFingerprint,
    [property: JsonPropertyName("source_digest")] string SourceDigest,
    [property: JsonPropertyName("sourcebook_fingerprint")] string SourcebookFingerprint,
    [property: JsonPropertyName("custom_data_fingerprint")] string CustomDataFingerprint,
    [property: JsonPropertyName("gm_policy_fingerprint")] string GmPolicyFingerprint,
    [property: JsonPropertyName("gateway_operation_digest")] string GatewayOperationDigest,
    [property: JsonPropertyName("core_authority_contract")] string CoreAuthorityContract,
    [property: JsonPropertyName("core_package_id")] string CorePackageId,
    [property: JsonPropertyName("core_package_version")] string CorePackageVersion,
    [property: JsonPropertyName("core_package_digest")] string CorePackageDigest,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("question")] string Question,
    [property: JsonPropertyName("subject_id")] string? SubjectId,
    [property: JsonPropertyName("request_digest")] string RequestDigest);

public static class AvatarRuleAuthorityRequestDigest
{
    public static string Compute(AvatarRuleAuthorityRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        StringBuilder canonical = new();
        Add(canonical, "digest_contract", "chummer.avatar-rule-authority-request-digest/v1");
        Add(canonical, "contract_name", request.ContractName);
        Add(canonical, "owner_id", request.OwnerId);
        Add(canonical, "workspace_id", request.WorkspaceId);
        Add(canonical, "workspace_revision", request.WorkspaceRevision.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Add(canonical, "character_id", request.CharacterId);
        Add(canonical, "campaign_id", request.CampaignId ?? string.Empty);
        Add(canonical, "ruleset_id", request.RulesetId);
        Add(canonical, "runtime_fingerprint", request.RuntimeFingerprint);
        Add(canonical, "source_digest", request.SourceDigest);
        Add(canonical, "sourcebook_fingerprint", request.SourcebookFingerprint);
        Add(canonical, "custom_data_fingerprint", request.CustomDataFingerprint);
        Add(canonical, "gm_policy_fingerprint", request.GmPolicyFingerprint);
        Add(canonical, "gateway_operation_digest", request.GatewayOperationDigest);
        Add(canonical, "core_authority_contract", request.CoreAuthorityContract);
        Add(canonical, "core_package_id", request.CorePackageId);
        Add(canonical, "core_package_version", request.CorePackageVersion);
        Add(canonical, "core_package_digest", request.CorePackageDigest);
        Add(canonical, "locale", request.Locale);
        Add(canonical, "question", request.Question);
        Add(canonical, "subject_id", request.SubjectId ?? string.Empty);
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(canonical.ToString()));
        return $"sha256:{Convert.ToHexString(digest).ToLowerInvariant()}";
    }

    private static void Add(StringBuilder target, string name, string? value)
    {
        value ??= string.Empty;
        target.Append(name.Length)
            .Append(':')
            .Append(name)
            .Append(':')
            .Append(value.Length)
            .Append(':')
            .Append(value)
            .Append('\n');
    }
}

public static class AvatarRuleAnswerDigest
{
    public static string Compute(AvatarRuleAnswerEnvelope answer)
    {
        ArgumentNullException.ThrowIfNull(answer);
        StringBuilder canonical = new();
        Add(canonical, "digest_contract", "chummer.avatar-rule-answer-digest/v1");
        Add(canonical, "contract_name", answer.ContractName);
        Add(canonical, "status", answer.Status);
        Add(canonical, "spoken_answer", answer.SpokenAnswer);
        Add(canonical, "short_answer", answer.ShortAnswer);
        Add(canonical, "applies_to_current_character", answer.AppliesToCurrentCharacter ? "true" : "false");
        Add(canonical, "workspace_revision", answer.WorkspaceRevision.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Add(canonical, "runtime_fingerprint", answer.RuntimeFingerprint);
        Add(canonical, "source_digest", answer.SourceDigest);
        Add(canonical, "authority_request_digest", answer.AuthorityRequestDigest);
        Add(canonical, "uncertainty_reason", answer.UncertaintyReason ?? string.Empty);
        foreach (AvatarCalculationStep step in answer.CalculationSteps)
        {
            Add(canonical, "calculation_step_id", step.StepId);
            Add(canonical, "calculation_expression", step.Expression);
            Add(canonical, "calculation_result", step.Result);
            foreach (string anchorId in step.SourceAnchorIds)
            {
                Add(canonical, "calculation_source_anchor_id", anchorId);
            }
        }
        foreach (string assumption in answer.Assumptions)
        {
            Add(canonical, "assumption", assumption);
        }
        foreach (AvatarSourceAnchor anchor in answer.SourceAnchors)
        {
            Add(canonical, "anchor_id", anchor.AnchorId);
            Add(canonical, "anchor_source_id", anchor.SourceId);
            Add(canonical, "anchor_source_name", anchor.LocalizedSourceName);
            Add(canonical, "anchor_page", anchor.Page?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty);
            Add(canonical, "anchor_rule_id", anchor.RuleId);
            Add(canonical, "anchor_route", anchor.LocalSourceRoute);
        }
        foreach (AvatarAllowedAction action in answer.AllowedActions)
        {
            Add(canonical, "action_id", action.ActionId);
            Add(canonical, "action_type", action.ActionType);
            Add(canonical, "action_route", action.Route ?? string.Empty);
            Add(canonical, "action_review", action.RequiresExplicitReview ? "true" : "false");
        }
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(canonical.ToString()));
        return $"sha256:{Convert.ToHexString(digest).ToLowerInvariant()}";
    }

    private static void Add(StringBuilder target, string name, string? value)
    {
        value ??= string.Empty;
        target.Append(name.Length)
            .Append(':')
            .Append(name)
            .Append(':')
            .Append(value.Length)
            .Append(':')
            .Append(value)
            .Append('\n');
    }
}
