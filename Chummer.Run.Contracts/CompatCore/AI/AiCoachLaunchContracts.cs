namespace Chummer.Contracts.AI;

public sealed record AiCoachLaunchContext(
    string RouteType,
    string? ConversationId = null,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    string? WorkspaceId = null,
    string? RulesetId = null,
    string? Message = null,
    string? BuildIdeaQuery = null);

public static class AiCoachLaunchQuery
{
    public const string RouteTypeKey = "routeType";
    public const string ConversationIdKey = "conversationId";
    public const string RuntimeFingerprintKey = "runtimeFingerprint";
    public const string CharacterIdKey = "characterId";
    public const string WorkspaceIdKey = "workspaceId";
    public const string RulesetIdKey = "rulesetId";
    public const string MessageKey = "message";
    public const string BuildIdeaQueryKey = "buildIdeaQuery";

    public static string BuildRelativeUri(string basePath, AiCoachLaunchContext context)
    {
        string normalizedBasePath = NormalizeBasePath(basePath);
        List<string> querySegments =
        [
            Encode(RouteTypeKey, NormalizeRequired(context.RouteType) ?? AiRouteTypes.Coach)
        ];

        AddOptional(querySegments, ConversationIdKey, context.ConversationId);
        AddOptional(querySegments, RuntimeFingerprintKey, context.RuntimeFingerprint);
        AddOptional(querySegments, CharacterIdKey, context.CharacterId);
        AddOptional(querySegments, WorkspaceIdKey, context.WorkspaceId);
        AddOptional(querySegments, RulesetIdKey, context.RulesetId);
        AddOptional(querySegments, MessageKey, context.Message);
        AddOptional(querySegments, BuildIdeaQueryKey, context.BuildIdeaQuery);

        return querySegments.Count == 0
            ? normalizedBasePath
            : $"{normalizedBasePath}?{string.Join("&", querySegments)}";
    }

    public static AiCoachLaunchContext Parse(string? queryString)
    {
        Dictionary<string, string> values = new(StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(queryString))
        {
            string trimmedQuery = queryString.Trim();
            if (trimmedQuery.StartsWith("?", StringComparison.Ordinal))
            {
                trimmedQuery = trimmedQuery[1..];
            }

            foreach (string segment in trimmedQuery.Split('&', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                int separatorIndex = segment.IndexOf('=');
                string key = separatorIndex >= 0 ? segment[..separatorIndex] : segment;
                string value = separatorIndex >= 0 ? segment[(separatorIndex + 1)..] : string.Empty;
                string decodedKey = Uri.UnescapeDataString(key);
                if (string.IsNullOrWhiteSpace(decodedKey))
                {
                    continue;
                }

                values[decodedKey] = Uri.UnescapeDataString(value);
            }
        }

        return new AiCoachLaunchContext(
            RouteType: GetRequired(values, RouteTypeKey) ?? AiRouteTypes.Coach,
            ConversationId: GetOptional(values, ConversationIdKey),
            RuntimeFingerprint: GetOptional(values, RuntimeFingerprintKey),
            CharacterId: GetOptional(values, CharacterIdKey),
            WorkspaceId: GetOptional(values, WorkspaceIdKey),
            RulesetId: GetOptional(values, RulesetIdKey),
            Message: GetOptional(values, MessageKey),
            BuildIdeaQuery: GetOptional(values, BuildIdeaQueryKey));
    }

    private static void AddOptional(List<string> querySegments, string key, string? value)
    {
        string? normalizedValue = NormalizeOptional(value);
        if (normalizedValue is null)
        {
            return;
        }

        querySegments.Add(Encode(key, normalizedValue));
    }

    private static string Encode(string key, string value)
        => $"{Uri.EscapeDataString(key)}={Uri.EscapeDataString(value)}";

    private static string NormalizeBasePath(string basePath)
    {
        string trimmedBasePath = string.IsNullOrWhiteSpace(basePath)
            ? "/coach/"
            : basePath.Trim();
        return trimmedBasePath.EndsWith("/", StringComparison.Ordinal)
            ? trimmedBasePath
            : $"{trimmedBasePath}/";
    }

    private static string? GetOptional(IReadOnlyDictionary<string, string> values, string key)
        => values.TryGetValue(key, out string? value)
            ? NormalizeOptional(value)
            : null;

    private static string? GetRequired(IReadOnlyDictionary<string, string> values, string key)
        => values.TryGetValue(key, out string? value)
            ? NormalizeRequired(value)
            : null;

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? null
            : value.Trim();

    private static string? NormalizeRequired(string? value)
        => NormalizeOptional(value);
}
