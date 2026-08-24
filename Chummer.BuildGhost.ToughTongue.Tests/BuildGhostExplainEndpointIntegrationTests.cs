using Chummer.Run.AI.Controllers;
using Chummer.Run.AI.Security;
using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class BuildGhostExplainEndpointIntegrationTests
{
    private const string InternalToken = "dedicated-ai-integration-token";
    private const string WorkspaceId = "workspace:runner-alpha";
    private const long WorkspaceRevision = 17;

    private static readonly string[] ProviderExecutionGateKeys =
    [
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED"
    ];

    [TestMethod]
    public async Task Explain_accepts_the_middleware_authority_and_returns_revision_bound_local_fallback()
    {
        RejectingTransport transport = new();
        await using WebApplication app = await StartAppAsync(transport);
        using HttpClient client = CreateClient(app);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", InternalToken);
        ToughTongueBuildGhostRequest request = CreateRequest();

        using HttpResponseMessage response = await client.PostAsJsonAsync(
            "/api/v1/ai/build-ghost/explain",
            request);

        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        ToughTongueBuildGhostResult? result = await response.Content.ReadFromJsonAsync<ToughTongueBuildGhostResult>();
        Assert.IsNotNull(result);
        Assert.AreEqual("remote-disabled", result.OutcomeStatus);
        Assert.AreEqual(request.DeterministicFallbackText, result.SafeText);
        Assert.IsTrue(result.UsedDeterministicFallback);
        Assert.IsNull(result.ProviderAnswer);
        Assert.AreEqual(request.RequestId, result.Receipt.RequestId);
        Assert.AreEqual(request.PacketDigest, result.Receipt.PacketDigest);
        Assert.AreEqual(request.Locale, result.Receipt.Locale);
        Assert.IsFalse(result.Receipt.RemoteExecutionEnabled);
        Assert.IsFalse(result.Receipt.RemoteAttempted);
        Assert.AreEqual("remote-disabled", result.Receipt.FallbackReason);
        Assert.AreEqual(0, transport.Calls);

        JsonObject packet = Assert.IsInstanceOfType<JsonObject>(JsonNode.Parse(request.AnalysisPacketJson));
        Assert.AreEqual(WorkspaceId, packet["workspaceId"]?.GetValue<string>());
        Assert.AreEqual(WorkspaceRevision, packet["workspaceRevision"]?.GetValue<long>());
        Assert.AreEqual(request.PacketDigest, packet["packetDigest"]?.GetValue<string>());

        IConfiguration configuration = app.Services.GetRequiredService<IConfiguration>();
        foreach (string gateKey in ProviderExecutionGateKeys)
        {
            Assert.AreEqual("false", configuration[gateKey], $"{gateKey} must remain fail closed.");
        }

        JsonObject stalePacket = Assert.IsInstanceOfType<JsonObject>(JsonNode.Parse(request.AnalysisPacketJson));
        stalePacket["workspaceRevision"] = WorkspaceRevision + 1;
        ToughTongueBuildGhostRequest staleRevision = request with
        {
            RequestId = "request:runner-alpha:revision-18",
            AnalysisPacketJson = stalePacket.ToJsonString(),
            IdempotencyKey = "idem:runner-alpha:revision-18"
        };

        using HttpResponseMessage staleResponse = await client.PostAsJsonAsync(
            "/api/v1/ai/build-ghost/explain",
            staleRevision);

        Assert.AreEqual(HttpStatusCode.BadRequest, staleResponse.StatusCode);
        StringAssert.Contains(
            await staleResponse.Content.ReadAsStringAsync(),
            "packet-digest-verification-failed");
        Assert.AreEqual(0, transport.Calls);
    }

    [TestMethod]
    public async Task Explain_rejects_missing_and_invalid_internal_authorization()
    {
        RejectingTransport transport = new();
        await using WebApplication app = await StartAppAsync(transport);
        ToughTongueBuildGhostRequest request = CreateRequest();

        using (HttpClient anonymous = CreateClient(app))
        using (HttpResponseMessage missing = await anonymous.PostAsJsonAsync(
                   "/api/v1/ai/build-ghost/explain",
                   request))
        {
            Assert.AreEqual(HttpStatusCode.Unauthorized, missing.StatusCode);
            Assert.AreEqual("Bearer", missing.Headers.WwwAuthenticate.Single().Scheme);
        }

        using (HttpClient invalid = CreateClient(app))
        {
            invalid.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", "wrong-token");
            using HttpResponseMessage rejected = await invalid.PostAsJsonAsync(
                "/api/v1/ai/build-ghost/explain",
                request);
            Assert.AreEqual(HttpStatusCode.Unauthorized, rejected.StatusCode);
            Assert.AreEqual("Bearer", rejected.Headers.WwwAuthenticate.Single().Scheme);
        }

        Assert.AreEqual(0, transport.Calls);
    }

    private static async Task<WebApplication> StartAppAsync(RejectingTransport transport)
    {
        Dictionary<string, string?> settings = new(StringComparer.Ordinal)
        {
            [AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey] = InternalToken,
            [AiMutationAuthorizationMiddleware.FallbackTokenConfigurationKey] = string.Empty
        };
        foreach (string gateKey in ProviderExecutionGateKeys)
        {
            settings[gateKey] = "false";
        }

        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Configuration.AddInMemoryCollection(settings);
        builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
        builder.Services.AddControllers().AddApplicationPart(typeof(BuildGhostController).Assembly);
        builder.Services.AddSingleton<IToughTongueBuildGhostTransport>(transport);
        builder.Services.AddSingleton<IBuildGhostClock, FixedClock>();
        builder.Services.AddSingleton<IToughTongueBuildGhostAdapter, ToughTongueBuildGhostAdapter>();
        builder.Services.AddSingleton<IBuildGhostPersonaReleaseRegistry, StaticReleaseRegistry>();
        builder.Services.AddSingleton<IBuildGhostPrivateToolAuthorityClient, RejectingAuthority>();

        WebApplication app = builder.Build();
        app.UseMiddleware<AiMutationAuthorizationMiddleware>();
        app.MapControllers();
        await app.StartAsync();
        return app;
    }

    private static HttpClient CreateClient(WebApplication app)
    {
        IServer server = app.Services.GetRequiredService<IServer>();
        IServerAddressesFeature addresses = server.Features.Get<IServerAddressesFeature>()
            ?? throw new InvalidOperationException("Kestrel did not expose a bound address.");
        return new HttpClient { BaseAddress = new Uri(addresses.Addresses.Single()) };
    }

    private static ToughTongueBuildGhostRequest CreateRequest()
    {
        JsonObject packet = CreatePacket();
        string digest = ComputePacketDigest(packet);
        packet["packetDigest"] = digest;
        return new ToughTongueBuildGhostRequest(
            ToughTongueBuildGhostContractVersions.RequestV1,
            "request:runner-alpha:revision-17",
            $"sha256:{new string('a', 64)}",
            digest,
            "en-US",
            packet.ToJsonString(),
            "Grounded local fallback for revision 17.",
            "idem:runner-alpha:revision-17",
            DateTimeOffset.Parse("2026-08-22T13:54:00Z"));
    }

    private static JsonObject CreatePacket()
        => new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.AnalysisV1,
            ["personaId"] = ToughTongueBuildGhostPersonaIds.Rook,
            ["avatarId"] = ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
            ["voiceId"] = ToughTongueBuildGhostPersonaIds.RookVoice,
            ["workspaceId"] = WorkspaceId,
            ["workspaceRevision"] = WorkspaceRevision,
            ["locale"] = "en-US",
            ["localeFallbackChain"] = new JsonArray("en-US"),
            ["supportedLocales"] = new JsonArray("en-US", "de-DE", "fr-FR", "ja-JP", "pt-BR", "zh-CN"),
            ["packetDigest"] = string.Empty,
            ["runner"] = new JsonObject
            {
                ["facts"] = new JsonArray(new JsonObject { ["factId"] = "fact:matrix" })
            },
            ["optimizationStrategies"] = new JsonArray(new JsonObject { ["strategyId"] = "strategy:matrix" }),
            ["ruleExplanations"] = new JsonArray(new JsonObject
            {
                ["explanationId"] = "rule:matrix",
                ["sourceLookupRoute"] = "/rules/matrix"
            }),
            ["variants"] = new JsonArray(new JsonObject { ["variantId"] = "variant:balanced" }),
            ["sourceAnchors"] = new JsonArray(new JsonObject { ["anchorId"] = "anchor:matrix" }),
            ["allowedSuggestedActions"] = new JsonArray(new JsonObject { ["actionId"] = "preview:balanced" }),
            ["groupCapabilityPosture"] = new JsonObject
            {
                ["visibilityPosture"] = "authorized-visible-scope",
                ["visibleMembers"] = new JsonArray(new JsonObject { ["memberRef"] = "member:visible" })
            }
        };

    private static string ComputePacketDigest(JsonObject packet)
    {
        JsonObject clone = (JsonObject)packet.DeepClone();
        clone["packetDigest"] = string.Empty;
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream))
        {
            WriteCanonical(writer, clone);
        }

        return $"sha256:{Convert.ToHexString(SHA256.HashData(stream.ToArray())).ToLowerInvariant()}";
    }

    private static void WriteCanonical(Utf8JsonWriter writer, JsonNode? node)
    {
        switch (node)
        {
            case null:
                writer.WriteNullValue();
                break;
            case JsonObject value:
                writer.WriteStartObject();
                foreach ((string key, JsonNode? child) in value.OrderBy(static item => item.Key, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(key);
                    WriteCanonical(writer, child);
                }
                writer.WriteEndObject();
                break;
            case JsonArray value:
                writer.WriteStartArray();
                foreach (JsonNode? child in value)
                {
                    WriteCanonical(writer, child);
                }
                writer.WriteEndArray();
                break;
            default:
                node.WriteTo(writer);
                break;
        }
    }

    private sealed class FixedClock : IBuildGhostClock
    {
        public DateTimeOffset UtcNow => DateTimeOffset.Parse("2026-08-22T13:54:00Z");
    }

    private sealed class RejectingTransport : IToughTongueBuildGhostTransport
    {
        public int Calls { get; private set; }

        public Task<ToughTongueBuildGhostTransportResult> ExplainAsync(
            ToughTongueBuildGhostTransportRequest request,
            string credential,
            CancellationToken cancellationToken)
        {
            Calls++;
            throw new AssertFailedException("Remote Tough Tongue transport must remain unreachable.");
        }
    }

    private sealed class StaticReleaseRegistry : IBuildGhostPersonaReleaseRegistry
    {
        public BuildGhostPersonaReleaseProjection ResolveRook()
            => new(
                ToughTongueBuildGhostPersonaIds.Rook,
                ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
                ToughTongueBuildGhostPersonaIds.RookVoice,
                "approved",
                "disabled",
                true,
                false,
                "localized-deterministic-text-only",
                []);
    }

    private sealed class RejectingAuthority : IBuildGhostPrivateToolAuthorityClient
    {
        public Task<string> ResolveAsync(
            BuildGhostPrivateToolRequest request,
            string toolContractDigest,
            CancellationToken cancellationToken)
            => throw new AssertFailedException("Private tool authority must not be called by the explain route.");
    }
}
