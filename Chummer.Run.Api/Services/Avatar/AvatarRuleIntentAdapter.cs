using Chummer.Run.Contracts.Avatar;

namespace Chummer.Run.Api.Services.Avatar;

internal enum AvatarRuleIntentDisposition
{
    Supported,
    Missing,
    Unsupported
}

internal sealed record AvatarRuleIntentDecision(
    AvatarRuleIntentDisposition Disposition,
    string? Reason)
{
    public bool Supported => Disposition == AvatarRuleIntentDisposition.Supported;
}

/// <summary>
/// Keeps the provider-facing conversation contract separate from the deterministic
/// Core authority ABI. Only explicit, versioned intents cross this adapter.
/// </summary>
internal static class AvatarRuleIntentAdapter
{
    internal const int MaximumArguments = 16;
    internal const int MaximumArgumentNameLength = 64;
    internal const int MaximumIdentifierLength = 256;
    internal const long MinimumInteger = -1_000_000;
    internal const long MaximumInteger = 1_000_000;

    internal const string SupportedRulesetId = "sr6";
    internal const string SupportedRulesetProfileId = "official.sr6.core";
    internal const string SupportedIntentId = "rules.session.quick-actions";
    internal const int SupportedIntentVersion = 1;
    internal const string SupportedCapabilityId = "session.quick-actions";
    internal const string SupportedInvocationKind = "script";

    internal const string MissingReason = "typed-intent-required";
    internal const string UnsupportedReason = "typed-intent-unsupported";

    public static bool IsStructurallyValidProviderRequest(AvatarRuleQuestionRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        AvatarRuleIntentSelection? intent = request.Intent;
        if (intent is null)
        {
            return true;
        }

        if (!IsIdentifier(request.SubjectId, MaximumIdentifierLength)
            || !IsContractName(intent.ContractName)
            || !IsIdentifier(intent.IntentId, MaximumIdentifierLength)
            || intent.IntentVersion <= 0
            || !IsIdentifier(intent.CapabilityId, MaximumIdentifierLength)
            || !IsIdentifier(intent.InvocationKind, MaximumIdentifierLength)
            || intent.Arguments is null
            || intent.Arguments.Count > MaximumArguments
            || intent.Arguments.Any(static argument => argument is null))
        {
            return false;
        }

        HashSet<string> names = new(StringComparer.Ordinal);
        foreach (AvatarRuleIntentArgument argument in intent.Arguments)
        {
            if (!IsIdentifier(argument.Name, MaximumArgumentNameLength)
                || !names.Add(argument.Name)
                || !IsValidArgument(argument))
            {
                return false;
            }
        }

        return true;
    }

    public static AvatarRuleIntentDecision Classify(
        AvatarContextSnapshot context,
        AvatarRuleQuestionRequest request)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(request);
        if (request.Intent is null)
        {
            return new AvatarRuleIntentDecision(AvatarRuleIntentDisposition.Missing, MissingReason);
        }
        if (!IsStructurallyValidProviderRequest(request))
        {
            throw new InvalidOperationException("avatar-rule-intent-structural-validation-bypassed");
        }

        AvatarRuleIntentSelection intent = request.Intent;
        bool supported = StringComparer.Ordinal.Equals(intent.ContractName, AvatarGatewayContractVersions.RuleIntentV1)
            && StringComparer.Ordinal.Equals(intent.IntentId, SupportedIntentId)
            && intent.IntentVersion == SupportedIntentVersion
            && StringComparer.Ordinal.Equals(intent.CapabilityId, SupportedCapabilityId)
            && StringComparer.Ordinal.Equals(intent.InvocationKind, SupportedInvocationKind)
            && intent.Arguments.Count == 0
            && StringComparer.Ordinal.Equals(context.RulesetId, SupportedRulesetId)
            && StringComparer.Ordinal.Equals(context.RulesetProfileId, SupportedRulesetProfileId);
        return supported
            ? new AvatarRuleIntentDecision(AvatarRuleIntentDisposition.Supported, null)
            : new AvatarRuleIntentDecision(AvatarRuleIntentDisposition.Unsupported, UnsupportedReason);
    }

    public static AvatarRuleAuthorityInvocation CreateInvocation(
        AvatarContextSnapshot context,
        AvatarRuleQuestionRequest providerRequest)
    {
        AvatarRuleIntentDecision decision = Classify(context, providerRequest);
        if (!decision.Supported || providerRequest.Intent is null || providerRequest.SubjectId is null)
        {
            throw new InvalidOperationException("avatar-rule-intent-not-supported");
        }

        AvatarRuleIntentSelection intent = providerRequest.Intent;
        AvatarRuleAuthorityRequest authorityRequest = new(
            AvatarGatewayContractVersions.RuleAuthorityV1,
            intent.IntentId,
            intent.IntentVersion,
            intent.CapabilityId,
            intent.InvocationKind,
            providerRequest.SubjectId,
            Array.AsReadOnly(intent.Arguments.Select(static argument => new AvatarRuleAuthorityArgument(
                argument.Name,
                argument.Kind,
                argument.IdentifierValue,
                argument.IntegerValue,
                argument.BooleanValue)).ToArray()),
            new AvatarRuleAuthorityBinding(
                context.RulesetId,
                context.RuntimeFingerprint,
                context.RulesetProfileId,
                context.WorkspaceRevision,
                context.SourceDigest,
                context.SourcebookFingerprint,
                context.CustomDataFingerprint,
                context.GmPolicyFingerprint));
        return new AvatarRuleAuthorityInvocation(
            authorityRequest,
            context.WorkspaceId,
            context.Locale);
    }

    public static bool IsValidAuthorityInvocation(AvatarRuleAuthorityInvocation? invocation)
    {
        if (invocation is null
            || !IsIdentifier(invocation.WorkspaceId, MaximumIdentifierLength)
            || !AvatarGatewayInput.IsBoundedText(invocation.Locale, 1, 35)
            || invocation.Request is null)
        {
            return false;
        }

        AvatarRuleAuthorityRequest request = invocation.Request;
        AvatarRuleAuthorityBinding binding = request.ExpectedBinding;
        return StringComparer.Ordinal.Equals(request.ContractVersion, AvatarGatewayContractVersions.RuleAuthorityV1)
            && StringComparer.Ordinal.Equals(request.IntentId, SupportedIntentId)
            && request.IntentVersion == SupportedIntentVersion
            && StringComparer.Ordinal.Equals(request.CapabilityId, SupportedCapabilityId)
            && StringComparer.Ordinal.Equals(request.InvocationKind, SupportedInvocationKind)
            && IsIdentifier(request.SubjectId, MaximumIdentifierLength)
            && request.Arguments is { Count: 0 }
            && binding is not null
            && StringComparer.Ordinal.Equals(binding.RulesetId, SupportedRulesetId)
            && StringComparer.Ordinal.Equals(binding.ProfileId, SupportedRulesetProfileId)
            && AvatarGatewayInput.IsSha256(binding.RuntimeFingerprint)
            && binding.WorkspaceRevision >= 0
            && AvatarGatewayInput.IsSha256(binding.SourceDigest)
            && AvatarGatewayInput.IsSha256(binding.SourcebookFingerprint)
            && AvatarGatewayInput.IsSha256(binding.CustomDataFingerprint)
            && AvatarGatewayInput.IsSha256(binding.GmPolicyFingerprint);
    }

    private static bool IsValidArgument(AvatarRuleIntentArgument argument)
        => argument.Kind switch
        {
            AvatarRuleAuthorityArgumentKinds.Identifier =>
                argument.IntegerValue is null
                && argument.BooleanValue is null
                && IsIdentifier(argument.IdentifierValue, MaximumIdentifierLength),
            AvatarRuleAuthorityArgumentKinds.Integer =>
                argument.IdentifierValue is null
                && argument.BooleanValue is null
                && argument.IntegerValue is >= MinimumInteger and <= MaximumInteger,
            AvatarRuleAuthorityArgumentKinds.Boolean =>
                argument.IdentifierValue is null
                && argument.IntegerValue is null
                && argument.BooleanValue.HasValue,
            _ => false
        };

    private static bool IsIdentifier(string? value, int maximumLength)
        => value is { Length: > 0 }
            && value.Length <= maximumLength
            && value.All(static character => char.IsAsciiLetterOrDigit(character)
                || character is '-' or '_' or '.' or ':');

    private static bool IsContractName(string? value)
        => value is { Length: > 0 and <= 128 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character)
                || character is '-' or '_' or '.' or ':' or '/');
}
