using Chummer.Run.Contracts.Avatar;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.AI.Services.Avatar;

public sealed record AvatarRuleAuthorityBinding(
    string ContractName,
    string CorePackageId,
    string CorePackageVersion,
    string CorePackageDigest);

public interface IAvatarRuleAuthorityClient
{
    AvatarRuleAuthorityBinding? Binding { get; }

    Task<AvatarRuleAnswerEnvelope> ResolveAsync(
        AvatarRuleAuthorityRequest request,
        CancellationToken cancellationToken);
}

public sealed class AvatarRuleAuthorityException(
    string reason,
    int statusCode = StatusCodes.Status502BadGateway) : Exception(reason)
{
    public string Reason { get; } = reason;
    public int StatusCode { get; } = statusCode;
}

public sealed class AvatarRuleAuthorityClient(
    HttpClient httpClient,
    IConfiguration configuration) : IAvatarRuleAuthorityClient
{
    public const string EndpointConfigurationKey = "CHUMMER_AVATAR_RULE_AUTHORITY_ENDPOINT";
    public const string ServiceTokenConfigurationKey = "CHUMMER_AVATAR_RULE_AUTHORITY_SERVICE_TOKEN";
    public const string CoreContractConfigurationKey = "CHUMMER_AVATAR_RULE_AUTHORITY_CORE_CONTRACT";
    public const string CorePackageIdConfigurationKey = "CHUMMER_AVATAR_RULE_AUTHORITY_CORE_PACKAGE_ID";
    public const string CorePackageVersionConfigurationKey = "CHUMMER_AVATAR_RULE_AUTHORITY_CORE_PACKAGE_VERSION";
    public const string CorePackageDigestConfigurationKey = "CHUMMER_AVATAR_RULE_AUTHORITY_CORE_PACKAGE_DIGEST";
    public const string ExactAuthorityPath = "/api/internal/avatar-rule-authority/resolve";
    public const int MaximumResponseBytes = 128 * 1024;
    public const int TimeoutSeconds = 30;

    private static readonly JsonSerializerOptions SerializerOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow
    };

    public AvatarRuleAuthorityBinding? Binding => ResolveBinding(configuration);

    public async Task<AvatarRuleAnswerEnvelope> ResolveAsync(
        AvatarRuleAuthorityRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        AvatarRuleAuthorityBinding? binding = Binding;
        if (binding is null || !IsValidAuthorityRequest(request, binding))
        {
            throw new AvatarRuleAuthorityException(
                "avatar-rule-authority-request-binding-invalid",
                StatusCodes.Status503ServiceUnavailable);
        }
        Uri endpoint = ResolveEndpoint(configuration[EndpointConfigurationKey]);
        string serviceToken = configuration[ServiceTokenConfigurationKey]?.Trim() ?? string.Empty;
        if (!AvatarGatewayInput.IsServiceCredential(serviceToken))
        {
            throw new AvatarRuleAuthorityException(
                "avatar-rule-authority-service-auth-unavailable",
                StatusCodes.Status503ServiceUnavailable);
        }

        using HttpRequestMessage upstream = new(HttpMethod.Post, endpoint)
        {
            Content = JsonContent.Create(request, options: SerializerOptions)
        };
        upstream.Headers.Authorization = new AuthenticationHeaderValue("Bearer", serviceToken);
        upstream.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };

        using CancellationTokenSource budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(TimeSpan.FromSeconds(TimeoutSeconds));
        try
        {
            using HttpResponseMessage response = await httpClient.SendAsync(
                upstream,
                HttpCompletionOption.ResponseHeadersRead,
                budget.Token).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                int status = response.StatusCode switch
                {
                    HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden => StatusCodes.Status503ServiceUnavailable,
                    HttpStatusCode.Conflict or HttpStatusCode.PreconditionFailed => StatusCodes.Status409Conflict,
                    HttpStatusCode.Gone => StatusCodes.Status410Gone,
                    _ => StatusCodes.Status502BadGateway
                };
                throw new AvatarRuleAuthorityException("avatar-rule-authority-rejected", status);
            }

            if (!string.Equals(
                    response.Content.Headers.ContentType?.MediaType,
                    "application/json",
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new AvatarRuleAuthorityException(
                    "avatar-rule-authority-content-type-invalid");
            }

            AvatarRuleAnswerEnvelope answer = await ReadBoundedAsync(response.Content, budget.Token)
                .ConfigureAwait(false);
            IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);
            if (failures.Count != 0)
            {
                throw new AvatarRuleAuthorityException("avatar-rule-answer-invalid:" + string.Join(',', failures));
            }
            return answer;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new AvatarRuleAuthorityException(
                "avatar-rule-authority-timeout",
                StatusCodes.Status504GatewayTimeout);
        }
        catch (HttpRequestException)
        {
            throw new AvatarRuleAuthorityException("avatar-rule-authority-unavailable");
        }
    }

    internal static Uri ResolveEndpoint(string? configured)
    {
        string value = configured?.Trim() ?? string.Empty;
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? endpoint)
            || !string.Equals(endpoint.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || (!string.Equals(endpoint.Host, "chummer.run", StringComparison.OrdinalIgnoreCase)
                && !endpoint.Host.EndsWith(".chummer.run", StringComparison.OrdinalIgnoreCase))
            || !string.Equals(endpoint.AbsolutePath, ExactAuthorityPath, StringComparison.Ordinal)
            || !string.IsNullOrEmpty(endpoint.UserInfo)
            || !string.IsNullOrEmpty(endpoint.Query)
            || !string.IsNullOrEmpty(endpoint.Fragment))
        {
            throw new AvatarRuleAuthorityException(
                "avatar-rule-authority-endpoint-invalid",
                StatusCodes.Status503ServiceUnavailable);
        }
        return endpoint;
    }

    internal static AvatarRuleAuthorityBinding? ResolveBinding(IConfiguration configuration)
    {
        string contractName = configuration[CoreContractConfigurationKey]?.Trim() ?? string.Empty;
        string packageId = configuration[CorePackageIdConfigurationKey]?.Trim() ?? string.Empty;
        string packageVersion = configuration[CorePackageVersionConfigurationKey]?.Trim() ?? string.Empty;
        string packageDigest = configuration[CorePackageDigestConfigurationKey]?.Trim() ?? string.Empty;
        if (!string.Equals(
                contractName,
                AvatarGatewayContractVersions.CoreTypedRuleAuthorityV1,
                StringComparison.Ordinal)
            || !AvatarGatewayInput.IsIdentifier(packageId, 128)
            || !AvatarGatewayInput.IsPackageVersion(packageVersion)
            || !AvatarGatewayInput.IsSha256(packageDigest))
        {
            return null;
        }
        return new AvatarRuleAuthorityBinding(contractName, packageId, packageVersion, packageDigest);
    }

    private static bool IsValidAuthorityRequest(
        AvatarRuleAuthorityRequest request,
        AvatarRuleAuthorityBinding binding)
        => string.Equals(
                request.ContractName,
                AvatarGatewayContractVersions.RuleAuthorityRequestV1,
                StringComparison.Ordinal)
            && AvatarGatewayInput.IsIdentifier(request.OwnerId, 128)
            && AvatarGatewayInput.IsIdentifier(request.WorkspaceId, 128)
            && request.WorkspaceRevision >= 0
            && AvatarGatewayInput.IsIdentifier(request.CharacterId, 128)
            && (request.CampaignId is null
                || AvatarGatewayInput.IsIdentifier(request.CampaignId, 128))
            && AvatarGatewayInput.IsIdentifier(request.RulesetId, 128)
            && AvatarGatewayInput.IsSha256(request.RuntimeFingerprint)
            && AvatarGatewayInput.IsSha256(request.SourceDigest)
            && AvatarGatewayInput.IsSha256(request.SourcebookFingerprint)
            && AvatarGatewayInput.IsSha256(request.CustomDataFingerprint)
            && AvatarGatewayInput.IsSha256(request.GmPolicyFingerprint)
            && AvatarGatewayInput.IsSha256(request.GatewayOperationDigest)
            && string.Equals(request.CoreAuthorityContract, binding.ContractName, StringComparison.Ordinal)
            && string.Equals(request.CorePackageId, binding.CorePackageId, StringComparison.Ordinal)
            && string.Equals(request.CorePackageVersion, binding.CorePackageVersion, StringComparison.Ordinal)
            && string.Equals(request.CorePackageDigest, binding.CorePackageDigest, StringComparison.Ordinal)
            && AvatarGatewayInput.IsIdentifier(request.Locale, 35)
            && AvatarGatewayInput.IsBoundedText(request.Question, 1, 4_000)
            && request.Question.Any(static character => !char.IsWhiteSpace(character))
            && (request.SubjectId is null
                || AvatarGatewayInput.IsIdentifier(request.SubjectId, 128))
            && AvatarGatewayInput.IsSha256(request.RequestDigest)
            && string.Equals(
                request.RequestDigest,
                AvatarRuleAuthorityRequestDigest.Compute(request),
                StringComparison.Ordinal);

    private static async Task<AvatarRuleAnswerEnvelope> ReadBoundedAsync(
        HttpContent content,
        CancellationToken cancellationToken)
    {
        if (content.Headers.ContentLength is > MaximumResponseBytes)
        {
            throw new AvatarRuleAuthorityException("avatar-rule-authority-response-too-large");
        }
        await using Stream stream = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using MemoryStream bounded = new();
        byte[] buffer = new byte[8192];
        int total = 0;
        while (true)
        {
            int read = await stream.ReadAsync(buffer.AsMemory(), cancellationToken).ConfigureAwait(false);
            if (read == 0) break;
            total += read;
            if (total > MaximumResponseBytes)
            {
                throw new AvatarRuleAuthorityException("avatar-rule-authority-response-too-large");
            }
            bounded.Write(buffer, 0, read);
        }
        try
        {
            byte[] responseBytes = bounded.ToArray();
            using JsonDocument document = JsonDocument.Parse(
                responseBytes,
                new JsonDocumentOptions
                {
                    AllowTrailingCommas = false,
                    CommentHandling = JsonCommentHandling.Disallow,
                    MaxDepth = 64
                });
            EnsureNoDuplicateProperties(document.RootElement);
            cancellationToken.ThrowIfCancellationRequested();
            return JsonSerializer.Deserialize<AvatarRuleAnswerEnvelope>(
                    responseBytes,
                    SerializerOptions)
                ?? throw new AvatarRuleAuthorityException("avatar-rule-authority-response-empty");
        }
        catch (JsonException)
        {
            throw new AvatarRuleAuthorityException("avatar-rule-authority-response-invalid");
        }
    }

    private static void EnsureNoDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            HashSet<string> properties = new(StringComparer.Ordinal);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!properties.Add(property.Name))
                {
                    throw new JsonException("duplicate-property");
                }
                EnsureNoDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in element.EnumerateArray())
            {
                EnsureNoDuplicateProperties(item);
            }
        }
    }
}

public static class AvatarRuleAnswerValidator
{
    private static readonly IReadOnlySet<string> AllowedStatuses = new HashSet<string>(StringComparer.Ordinal)
    {
        AvatarGatewayStatuses.Resolved,
        AvatarGatewayStatuses.Unresolved,
        AvatarGatewayStatuses.Stale,
        AvatarGatewayStatuses.Conflict,
        AvatarGatewayStatuses.Forbidden,
        AvatarGatewayStatuses.Unavailable
    };

    private static readonly IReadOnlySet<string> AllowedRuleActions = new HashSet<string>(StringComparer.Ordinal)
    {
        AvatarGatewayActionTypes.OpenRuleSource,
        AvatarGatewayActionTypes.OpenWorkbenchRoute
    };

    public static IReadOnlyList<string> Validate(
        AvatarRuleAnswerEnvelope? answer,
        AvatarRuleAuthorityRequest expected)
    {
        ArgumentNullException.ThrowIfNull(expected);
        if (answer is null) return ["answer-required"];

        List<string> failures = [];
        if (answer.ContractName != AvatarGatewayContractVersions.RuleAnswerV1) failures.Add("contract-invalid");
        if (!AllowedStatuses.Contains(answer.Status ?? string.Empty)) failures.Add("status-invalid");
        if (answer.WorkspaceRevision != expected.WorkspaceRevision) failures.Add("workspace-revision-drift");
        if (!string.Equals(answer.RuntimeFingerprint, expected.RuntimeFingerprint, StringComparison.Ordinal)) failures.Add("runtime-fingerprint-drift");
        if (!string.Equals(answer.SourceDigest, expected.SourceDigest, StringComparison.Ordinal)) failures.Add("source-digest-drift");
        if (!AvatarGatewayInput.IsSha256(expected.GatewayOperationDigest)
            || !AvatarGatewayInput.IsSha256(expected.RequestDigest)
            || !string.Equals(
                expected.RequestDigest,
                AvatarRuleAuthorityRequestDigest.Compute(expected),
                StringComparison.Ordinal)) failures.Add("authority-request-binding-invalid");
        if (!string.Equals(
                answer.AuthorityRequestDigest,
                expected.RequestDigest,
                StringComparison.Ordinal)) failures.Add("authority-request-digest-drift");
        if (!AvatarGatewayInput.IsBoundedText(answer.SpokenAnswer, 1, 8_000)) failures.Add("spoken-answer-invalid");
        if (!AvatarGatewayInput.IsBoundedText(answer.ShortAnswer, 1, 2_000)) failures.Add("short-answer-invalid");
        if (answer.CalculationSteps is null || answer.CalculationSteps.Count > 64) failures.Add("calculation-steps-invalid");
        if (answer.Assumptions is null || answer.Assumptions.Count > 32
            || answer.Assumptions.Any(static item => !AvatarGatewayInput.IsBoundedText(item, 1, 1_000))) failures.Add("assumptions-invalid");
        if (answer.SourceAnchors is null || answer.SourceAnchors.Count > 64) failures.Add("source-anchors-invalid");
        if (answer.AllowedActions is null || answer.AllowedActions.Count > 16) failures.Add("allowed-actions-invalid");

        if (answer.Status == AvatarGatewayStatuses.Resolved)
        {
            if (answer.CalculationSteps?.Count is not > 0) failures.Add("calculation-trace-required");
            if (answer.SourceAnchors?.Count is not > 0) failures.Add("source-anchor-required");
            if (!string.IsNullOrWhiteSpace(answer.UncertaintyReason)) failures.Add("resolved-uncertainty-forbidden");
        }
        else if (!AvatarGatewayInput.IsBoundedText(answer.UncertaintyReason, 1, 2_000))
        {
            failures.Add("uncertainty-reason-required");
        }

        HashSet<string> anchorIds = new(StringComparer.Ordinal);
        foreach (AvatarSourceAnchor anchor in answer.SourceAnchors ?? [])
        {
            if (anchor is null)
            {
                failures.Add("source-anchor-null");
                continue;
            }
            if (!AvatarGatewayInput.IsIdentifier(anchor.AnchorId, 128) || !anchorIds.Add(anchor.AnchorId)) failures.Add("source-anchor-id-invalid");
            if (!AvatarGatewayInput.IsIdentifier(anchor.SourceId, 128)) failures.Add("source-id-invalid");
            if (!AvatarGatewayInput.IsBoundedText(anchor.LocalizedSourceName, 1, 256)) failures.Add("source-name-invalid");
            if (anchor.Page is <= 0 or > 20_000) failures.Add("source-page-invalid");
            if (!AvatarGatewayInput.IsIdentifier(anchor.RuleId, 256)) failures.Add("rule-id-invalid");
            if (!IsLocalSourceRoute(anchor)) failures.Add("source-route-invalid");
        }

        HashSet<string> stepIds = new(StringComparer.Ordinal);
        foreach (AvatarCalculationStep step in answer.CalculationSteps ?? [])
        {
            if (step is null)
            {
                failures.Add("calculation-step-null");
                continue;
            }
            if (!AvatarGatewayInput.IsIdentifier(step.StepId, 128) || !stepIds.Add(step.StepId)) failures.Add("calculation-step-id-invalid");
            if (!AvatarGatewayInput.IsBoundedText(step.Expression, 1, 2_000)) failures.Add("calculation-expression-invalid");
            if (!AvatarGatewayInput.IsBoundedText(step.Result, 1, 1_000)) failures.Add("calculation-result-invalid");
            if (step.SourceAnchorIds is null || step.SourceAnchorIds.Count is 0 or > 16
                || step.SourceAnchorIds.Any(id => !anchorIds.Contains(id))) failures.Add("calculation-anchor-reference-invalid");
        }

        HashSet<string> actionIds = new(StringComparer.Ordinal);
        foreach (AvatarAllowedAction action in answer.AllowedActions ?? [])
        {
            if (action is null)
            {
                failures.Add("action-null");
                continue;
            }
            if (!AvatarGatewayInput.IsIdentifier(action.ActionId, 128) || !actionIds.Add(action.ActionId)) failures.Add("action-id-invalid");
            if (!AllowedRuleActions.Contains(action.ActionType ?? string.Empty)) failures.Add("action-type-forbidden");
            if (action.RequiresExplicitReview) failures.Add("rule-action-review-flag-invalid");
            if (action.ActionType == AvatarGatewayActionTypes.OpenRuleSource
                && (action.Route is null
                    || answer.SourceAnchors?.Any(anchor =>
                        anchor is not null
                        && StringComparer.Ordinal.Equals(anchor.LocalSourceRoute, action.Route)) is not true))
            {
                failures.Add("action-source-route-unbound");
            }
            if (action.ActionType == AvatarGatewayActionTypes.OpenWorkbenchRoute
                && !IsReadOnlyWorkbenchRoute(action.Route, expected.WorkspaceId))
            {
                failures.Add("action-workbench-route-invalid");
            }
        }

        if (!AvatarGatewayInput.IsSha256(answer.AnswerDigest)
            || !CanComputeDigest(answer)
            || !string.Equals(answer.AnswerDigest, AvatarRuleAnswerDigest.Compute(answer), StringComparison.Ordinal))
        {
            failures.Add("answer-digest-invalid");
        }
        return failures.Distinct(StringComparer.Ordinal).ToArray();
    }

    public static AvatarRuleAnswerEnvelope SafeUnavailable(
        AvatarRuleAuthorityRequest expected,
        string? reason = null)
        => SafeFailure(
            expected,
            AvatarGatewayStatuses.Unavailable,
            IsGerman(expected.Locale)
                ? "Ich kann das mit dem aktuellen Chummer-Regel- und Charakterkontext nicht zuverlässig beantworten. Öffne bitte die Regelquelle oder lade den Charakterkontext neu."
                : "I cannot answer that reliably with the current Chummer rules and character context. Open the rule source or reload the character context.",
            IsGerman(expected.Locale)
                ? "Regelantwort derzeit nicht verfügbar."
                : "Rule answer is currently unavailable.",
            reason ?? (IsGerman(expected.Locale)
                ? "Chummer Core ist für diese Regelabfrage derzeit nicht verfügbar."
                : "Chummer Core is currently unavailable for this rule question."));

    public static AvatarRuleAnswerEnvelope SafeFailure(
        AvatarRuleAuthorityRequest expected,
        string status,
        string spokenAnswer,
        string shortAnswer,
        string reason)
    {
        if (status is not (AvatarGatewayStatuses.Unresolved
            or AvatarGatewayStatuses.Stale
            or AvatarGatewayStatuses.Conflict
            or AvatarGatewayStatuses.Forbidden
            or AvatarGatewayStatuses.Unavailable))
        {
            throw new ArgumentOutOfRangeException(nameof(status));
        }
        AvatarRuleAnswerEnvelope unsigned = new(
            AvatarGatewayContractVersions.RuleAnswerV1,
            status,
            spokenAnswer,
            shortAnswer,
            [],
            [],
            false,
            [],
            [],
            expected.WorkspaceRevision,
            expected.RuntimeFingerprint,
            expected.SourceDigest,
            expected.RequestDigest,
            string.Empty,
            reason);
        return unsigned with { AnswerDigest = AvatarRuleAnswerDigest.Compute(unsigned) };
    }

    private static bool IsLocalSourceRoute(AvatarSourceAnchor anchor)
    {
        if (!Uri.TryCreate(anchor.LocalSourceRoute, UriKind.Absolute, out Uri? uri)
            || !string.Equals(uri.Scheme, "chummer", StringComparison.Ordinal)
            || !string.Equals(uri.Host, "sources", StringComparison.Ordinal)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Fragment))
        {
            return false;
        }

        string[] segments = uri.GetComponents(UriComponents.Path, UriFormat.Unescaped)
            .Split('/', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        string expectedQuery = anchor.Page.HasValue
            ? "?page=" + anchor.Page.Value.ToString(System.Globalization.CultureInfo.InvariantCulture)
            : string.Empty;
        return segments.Length == 1
            && StringComparer.Ordinal.Equals(segments[0], anchor.SourceId)
            && StringComparer.Ordinal.Equals(uri.Query, expectedQuery);
    }

    private static bool IsReadOnlyWorkbenchRoute(string? value, string workspaceId)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? uri)
            || !string.Equals(uri.Scheme, "chummer", StringComparison.Ordinal)
            || !string.Equals(uri.Host, "workspace", StringComparison.Ordinal)
            || string.IsNullOrEmpty(uri.AbsolutePath)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Query)
            || !string.IsNullOrEmpty(uri.Fragment))
        {
            return false;
        }

        string[] segments = uri.GetComponents(UriComponents.Path, UriFormat.Unescaped)
            .Split('/', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return segments.Length == 3
            && StringComparer.Ordinal.Equals(segments[0], workspaceId)
            && StringComparer.Ordinal.Equals(segments[1], "build-ghost")
            && StringComparer.Ordinal.Equals(segments[2], "workbench");
    }

    private static bool IsGerman(string? locale)
        => locale?.StartsWith("de", StringComparison.OrdinalIgnoreCase) is true;

    private static bool CanComputeDigest(AvatarRuleAnswerEnvelope answer)
        => answer.CalculationSteps is not null
            && answer.CalculationSteps.All(static step =>
                step is not null
                && step.SourceAnchorIds is not null
                && step.SourceAnchorIds.All(static anchorId => anchorId is not null))
            && answer.Assumptions is not null
            && answer.Assumptions.All(static assumption => assumption is not null)
            && answer.SourceAnchors is not null
            && answer.SourceAnchors.All(static anchor => anchor is not null)
            && answer.AllowedActions is not null
            && answer.AllowedActions.All(static action => action is not null);
}

internal static class AvatarGatewayInput
{
    public static bool IsServiceCredential(string? value)
        => value is { Length: >= 32 and <= 512 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or '.' or ':');

    public static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    public static bool IsIdentifier(string? value, int maximumLength)
        => value is { Length: > 0 }
            && value.Length <= maximumLength
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or '.' or ':');

    public static bool IsPackageVersion(string? value)
        => value is { Length: > 0 and <= 128 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or '.' or '+');

    public static bool IsBoundedText(string? value, int minimumLength, int maximumLength)
        => value is not null
            && value.Length >= minimumLength
            && value.Length <= maximumLength
            && !value.Any(static character => char.IsControl(character) && character is not '\n' and not '\r' and not '\t');
}
