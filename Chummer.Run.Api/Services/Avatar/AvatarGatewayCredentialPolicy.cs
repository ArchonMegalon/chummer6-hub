using Microsoft.Extensions.Primitives;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services.Avatar;

public sealed class AvatarGatewayCredentialPolicy(IConfiguration configuration)
{
    public const string ProviderServiceTokenConfigurationKey = "CHUMMER_AVATAR_GATEWAY_SERVICE_TOKEN";
    public const string ContextMintServiceTokenConfigurationKey = "CHUMMER_AVATAR_CONTEXT_MINT_SERVICE_TOKEN";
    public const string ContextStoreModeConfigurationKey = "CHUMMER_AVATAR_GATEWAY_CONTEXT_STORE_MODE";
    public const string ReplicaCountConfigurationKey = "CHUMMER_AVATAR_GATEWAY_REPLICA_COUNT";
    public const string ProcessLocalSingleReplicaMode = "process-local-single-replica";

    public bool ProviderReady => DeploymentTopologyReady
        && ReadDistinctCredential(ProviderServiceTokenConfigurationKey) is not null;

    public bool ContextMintReady => DeploymentTopologyReady
        && ReadDistinctCredential(ContextMintServiceTokenConfigurationKey) is not null;

    public bool IsProviderAuthorized(HttpRequest request)
        => ProviderReady
            && RequestShapeIsPrivate(request)
            && FixedBearerMatches(request, ReadDistinctCredential(ProviderServiceTokenConfigurationKey));

    public bool IsContextMintAuthorized(HttpRequest request)
        => ContextMintReady
            && RequestShapeIsPrivate(request)
            && FixedBearerMatches(request, ReadDistinctCredential(ContextMintServiceTokenConfigurationKey));

    private bool DeploymentTopologyReady
        => string.Equals(
                configuration[ContextStoreModeConfigurationKey]?.Trim(),
                ProcessLocalSingleReplicaMode,
                StringComparison.Ordinal)
            && string.Equals(
                configuration[ReplicaCountConfigurationKey]?.Trim(),
                "1",
                StringComparison.Ordinal);

    private string? ReadDistinctCredential(string key)
    {
        string candidate = configuration[key]?.Trim() ?? string.Empty;
        if (!AvatarGatewayInput.IsServiceCredential(candidate)) return null;
        string otherKey = key == ProviderServiceTokenConfigurationKey
            ? ContextMintServiceTokenConfigurationKey
            : ProviderServiceTokenConfigurationKey;
        string other = configuration[otherKey]?.Trim() ?? string.Empty;
        return FixedEquals(candidate, other) ? null : candidate;
    }

    private static bool RequestShapeIsPrivate(HttpRequest request)
    {
        if (request.QueryString.HasValue || request.Headers.ContainsKey("Cookie")) return false;
        StringValues cacheControl = request.Headers.CacheControl;
        return cacheControl.Count == 1
            && string.Equals(cacheControl[0]?.Trim(), "no-store", StringComparison.OrdinalIgnoreCase);
    }

    private static bool FixedBearerMatches(HttpRequest request, string? expected)
    {
        if (expected is null) return false;
        const string prefix = "Bearer ";
        string header = request.Headers.Authorization.ToString();
        return header.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
            && FixedEquals(header[prefix.Length..].Trim(), expected);
    }

    private static bool FixedEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length
            && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }
}
