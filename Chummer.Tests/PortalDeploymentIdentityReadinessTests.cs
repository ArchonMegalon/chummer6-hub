using System.Net;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class PortalDeploymentIdentityReadinessTests
{
    private const string Fingerprint =
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    private const string FullDeploymentDigest =
        "d18fab514e165b8aac313743f216ba1f836ccc4e6f4315cc81a6b2be4c1eaa28";
    private const string StagedPayloadFingerprint =
        "a2bded2b38854bb46591aa4a17210de8ecf91180f73fe3f21d7fa1a5f08159cd";
    private const string RuntimeProofRelativePath =
        "wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json";

    [Fact]
    public void Production_accepts_current_overlay_identity_contract()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));

        PortalDeploymentIdentityReadiness result = new PortalDeploymentIdentityReadinessService(
            new FakeHostEnvironment(Environments.Production, root.Path)).Evaluate();

        Assert.True(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.BoundCode, result.Code);
        Assert.Equal(Fingerprint, result.SourceFingerprintSha256);
        Assert.Equal(FullDeploymentDigest, result.FullDeploymentDigestSha256);
    }

    [Fact]
    public void Production_matches_python_canonical_json_for_unicode_deployment_identity()
    {
        const string pythonDigest =
            "81393cbb2442ef5f5bf8711f687b01035aded29376a210790e28a405a1b854ec";
        using var root = new TemporaryContentRoot();
        var payload = CurrentBuildInfo(Fingerprint);
        var sourceFingerprint = (Dictionary<string, object?>)payload["sourceFingerprint"]!;
        sourceFingerprint["files"] = new Dictionary<string, object?>
        {
            ["é\n"] = new Dictionary<string, object?>
            {
                ["value"] = "snowman ☃ and / < > & \u007f"
            },
            ["\U00010000"] = "astral",
            ["\uE000"] = "bmp"
        };
        ((Dictionary<string, object?>)payload["fullDeploymentDigest"]!)["sha256"] =
            pythonDigest;
        root.WriteBuildInfo(payload);

        PortalDeploymentIdentityReadiness result = EvaluateProduction(root);

        Assert.True(result.Ready);
        Assert.Equal(pythonDigest, result.FullDeploymentDigestSha256);
    }

    [Fact]
    public void Production_fails_closed_when_overlay_identity_is_missing()
    {
        using var root = new TemporaryContentRoot();

        PortalDeploymentIdentityReadiness result = new PortalDeploymentIdentityReadinessService(
            new FakeHostEnvironment(Environments.Production, root.Path)).Evaluate();

        Assert.False(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.MissingCode, result.Code);
        Assert.Null(result.SourceFingerprintSha256);
        Assert.Null(result.FullDeploymentDigestSha256);
    }

    [Fact]
    public void Production_rejects_symlinked_overlay_identity()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using var root = new TemporaryContentRoot();
        root.WriteSymlinkedBuildInfo(CurrentBuildInfo(Fingerprint));

        PortalDeploymentIdentityReadiness result = new PortalDeploymentIdentityReadinessService(
            new FakeHostEnvironment(Environments.Production, root.Path)).Evaluate();

        Assert.False(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.InvalidCode, result.Code);
        Assert.Null(result.SourceFingerprintSha256);
        Assert.Null(result.FullDeploymentDigestSha256);
    }

    [Fact]
    public void Production_accepts_opaque_state_contents_without_inspection()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.AddOpaqueStateContents();

        PortalDeploymentIdentityReadiness result = EvaluateProduction(root);

        Assert.True(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.BoundCode, result.Code);
    }

    [Fact]
    public void Production_rejects_same_mode_payload_byte_drift()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.SetPayloadContents("app.dll", "evil-app");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_accepts_runtime_proof_byte_refresh()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.SetPayloadContents(RuntimeProofRelativePath, "refreshed-runtime-proof");

        PortalDeploymentIdentityReadiness result = EvaluateProduction(root);

        Assert.True(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.BoundCode, result.Code);
    }

    [Fact]
    public void Production_rejects_missing_runtime_proof_mountpoint()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.RemovePayloadFile(RuntimeProofRelativePath);

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_runtime_proof_mode_drift()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.SetPayloadMode(RuntimeProofRelativePath, "0600");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_symlinked_runtime_proof_mountpoint()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.ReplacePayloadWithSymlink(RuntimeProofRelativePath, "app.dll");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_added_payload_entry()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.AddPayloadFile("unexpected.dll");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_removed_payload_entry()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.RemovePayloadFile("app.dll");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_setuid_payload_mode()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.SetPayloadMode("app.dll", "4755");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_symlink_inside_payload_tree()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.AddPayloadSymlink("alias.dll", "app.dll");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_payload_file_with_an_external_hardlink()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.CreateExternalHardlink("app.dll");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_build_info_with_an_external_hardlink()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        root.CreateExternalHardlink(
            ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json");

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_noncanonical_payload_mode_receipt_fields()
    {
        using var root = new TemporaryContentRoot();
        var payload = CurrentBuildInfo(Fingerprint);
        ((Dictionary<string, object?>)payload["payloadModeReceipt"]!)["unknownField"] = true;
        root.WriteBuildInfo(payload);

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_duplicate_keys_inside_ignored_build_info_fields()
    {
        using var root = new TemporaryContentRoot();
        string serialized = JsonSerializer.Serialize(CurrentBuildInfo(Fingerprint));
        string raw = serialized[..^1] + ",\"ignored\":{\"key\":1,\"key\":2}}";
        root.WriteRawBuildInfo(Encoding.UTF8.GetBytes(raw));

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_utf8_bom_in_build_info()
    {
        using var root = new TemporaryContentRoot();
        byte[] serialized = JsonSerializer.SerializeToUtf8Bytes(CurrentBuildInfo(Fingerprint));
        byte[] raw = [0xef, 0xbb, 0xbf, .. serialized];
        root.WriteRawBuildInfo(raw);

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_payload_mode_entry_binding_drift()
    {
        using var root = new TemporaryContentRoot();
        var payload = CurrentBuildInfo(Fingerprint);
        var receipt = (Dictionary<string, object?>)payload["payloadModeReceipt"]!;
        ((Dictionary<string, object?>)receipt["entryBinding"]!)["sha256"] = new string('a', 64);
        root.WriteBuildInfo(payload);

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_nonempty_executable_allowlist()
    {
        using var root = new TemporaryContentRoot();
        var payload = CurrentBuildInfo(Fingerprint);
        var receipt = (Dictionary<string, object?>)payload["payloadModeReceipt"]!;
        ((Dictionary<string, object?>)receipt["executablePolicy"]!)["relativePaths"] =
            new[] { "app.dll" };
        root.WriteBuildInfo(payload);

        AssertInvalid(EvaluateProduction(root));
    }

    [Fact]
    public void Production_rejects_claim_that_state_contents_were_inspected()
    {
        using var root = new TemporaryContentRoot();
        var payload = CurrentBuildInfo(Fingerprint);
        var receipt = (Dictionary<string, object?>)payload["payloadModeReceipt"]!;
        ((Dictionary<string, object?>)receipt["stateBoundary"]!)["stateContentsInspected"] = true;
        root.WriteBuildInfo(payload);

        AssertInvalid(EvaluateProduction(root));
    }

    [Theory]
    [InlineData("contractName", "chummer.public_edge_portal_overlay_publish.v0")]
    [InlineData("status", "fail")]
    [InlineData("activationStatus", "staged")]
    [InlineData("aggregateSha256", "not-a-sha256")]
    [InlineData("sourceFingerprint.buildInputs.algorithm", "sha256-canonical-path-content-size-posix-mode-v2")]
    [InlineData("sourceFingerprint.overlayPayloadInputs.algorithm", "sha256-canonical-path-content-size-posix-mode-v2")]
    [InlineData("stagedPayloadFingerprint.algorithm", "sha256-canonical-path-content-size-v1")]
    [InlineData("payloadModeReceipt.contractName", "chummer.public_edge_payload_modes.v0")]
    [InlineData("payloadModeReceipt.algorithm", "unknown-mode-policy")]
    [InlineData("payloadModeReceipt.status", "fail")]
    [InlineData("fullDeploymentDigest.contractName", "chummer.public_edge_full_deployment_digest.v0")]
    [InlineData("fullDeploymentDigest.algorithm", "sha256-unknown")]
    [InlineData("fullDeploymentDigest.sha256", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    public void Production_rejects_drifted_overlay_identity(
        string field,
        string driftedValue)
    {
        using var root = new TemporaryContentRoot();
        var payload = CurrentBuildInfo(Fingerprint);
        if (field == "aggregateSha256")
        {
            ((Dictionary<string, object?>)payload["sourceFingerprint"]!)[field] = driftedValue;
        }
        else if (field.StartsWith("sourceFingerprint.", StringComparison.Ordinal))
        {
            string[] parts = field.Split('.');
            ((Dictionary<string, object?>)((Dictionary<string, object?>)payload[parts[0]]!)[parts[1]]!)[
                parts[2]] = driftedValue;
        }
        else if (field.StartsWith("stagedPayloadFingerprint.", StringComparison.Ordinal))
        {
            ((Dictionary<string, object?>)payload["stagedPayloadFingerprint"]!)[
                field["stagedPayloadFingerprint.".Length..]] = driftedValue;
        }
        else if (field.StartsWith("payloadModeReceipt.", StringComparison.Ordinal))
        {
            ((Dictionary<string, object?>)payload["payloadModeReceipt"]!)[
                field["payloadModeReceipt.".Length..]] = driftedValue;
        }
        else if (field.StartsWith("fullDeploymentDigest.", StringComparison.Ordinal))
        {
            ((Dictionary<string, object?>)payload["fullDeploymentDigest"]!)[
                field["fullDeploymentDigest.".Length..]] = driftedValue;
        }
        else
        {
            payload[field] = driftedValue;
        }
        root.WriteBuildInfo(payload);

        PortalDeploymentIdentityReadiness result = new PortalDeploymentIdentityReadinessService(
            new FakeHostEnvironment(Environments.Production, root.Path)).Evaluate();

        Assert.False(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.InvalidCode, result.Code);
        Assert.Null(result.SourceFingerprintSha256);
        Assert.Null(result.FullDeploymentDigestSha256);
    }

    [Fact]
    public void Development_reports_identity_as_not_required()
    {
        using var root = new TemporaryContentRoot();

        PortalDeploymentIdentityReadiness result = new PortalDeploymentIdentityReadinessService(
            new FakeHostEnvironment(Environments.Development, root.Path)).Evaluate();

        Assert.True(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.NotRequiredCode, result.Code);
        Assert.Null(result.SourceFingerprintSha256);
        Assert.Null(result.FullDeploymentDigestSha256);
    }

    [Fact]
    public async Task Ready_route_exposes_bound_nonsecret_deployment_identity()
    {
        using var root = new TemporaryContentRoot();
        root.WriteBuildInfo(CurrentBuildInfo(Fingerprint));
        await using WebApplication app = await StartReadyRouteAsync(root.Path);
        using HttpClient client = CreateClient(app);

        using HttpResponseMessage response = await client.GetAsync("/api/ready");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        using JsonDocument document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        JsonElement body = document.RootElement;
        Assert.True(body.GetProperty("ready").GetBoolean());
        JsonElement identity = body.GetProperty("deploymentIdentity");
        Assert.Equal(4, identity.EnumerateObject().Count());
        Assert.True(identity.GetProperty("ready").GetBoolean());
        Assert.Equal("overlay_identity_bound", identity.GetProperty("code").GetString());
        Assert.Equal(Fingerprint, identity.GetProperty("sourceFingerprintSha256").GetString());
        Assert.Equal(
            FullDeploymentDigest,
            identity.GetProperty("fullDeploymentDigestSha256").GetString());
    }

    [Fact]
    public async Task Ready_route_returns_service_unavailable_without_production_identity()
    {
        using var root = new TemporaryContentRoot();
        await using WebApplication app = await StartReadyRouteAsync(root.Path);
        using HttpClient client = CreateClient(app);

        using HttpResponseMessage response = await client.GetAsync("/api/ready");

        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        using JsonDocument document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        JsonElement body = document.RootElement;
        Assert.False(body.GetProperty("ready").GetBoolean());
        JsonElement identity = body.GetProperty("deploymentIdentity");
        Assert.False(identity.GetProperty("ready").GetBoolean());
        Assert.Equal("overlay_identity_missing", identity.GetProperty("code").GetString());
        Assert.Equal(JsonValueKind.Null, identity.GetProperty("sourceFingerprintSha256").ValueKind);
        Assert.Equal(JsonValueKind.Null, identity.GetProperty("fullDeploymentDigestSha256").ValueKind);
    }

    private static async Task<WebApplication> StartReadyRouteAsync(string contentRootPath)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder(new WebApplicationOptions
        {
            EnvironmentName = Environments.Production,
            ContentRootPath = contentRootPath
        });
        builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
        builder.Services.AddSingleton<PortalDeploymentIdentityReadinessService>();

        WebApplication app = builder.Build();
        app.MapGet("/api/ready", (
            PortalDeploymentIdentityReadinessService deploymentIdentityReadiness) =>
        {
            HubReadyResponse combined = HubReadyResponse.Create(
                ReadyHubReport(),
                new PublicPlayProjectionReadiness(
                    Status: "disabled",
                    Ready: true,
                    Enabled: false,
                    Detail: "Local projection is authoritative."),
                deploymentIdentityReadiness.Evaluate());
            return Results.Json(
                combined,
                statusCode: combined.Ready
                    ? StatusCodes.Status200OK
                    : StatusCodes.Status503ServiceUnavailable);
        });
        await app.StartAsync();
        return app;
    }

    private static HubDeepReadinessReport ReadyHubReport()
        => new(
            ContractName: HubDeepReadinessService.ContractName,
            Service: "chummer.run.api",
            Ready: true,
            Status: "pass",
            ServingReady: true,
            PublicationReady: true,
            PublicationChecksConfigured: true,
            GeneratedAt: DateTimeOffset.UtcNow,
            Checks: [],
            ReleaseShelf: new ReleaseShelfReadinessState(
                Mode: "generation",
                ServingReady: true,
                PublicationReady: true,
                PublicationChecksConfigured: true,
                Status: "serving",
                Code: "generation_shelf_loaded",
                GenerationId: "generation-test",
                ActivationReceiptId: "activation-test",
                InventoryDigest: Fingerprint,
                ReleaseVersion: "run-test",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                PublicationChecks: []));

    private static HttpClient CreateClient(WebApplication app)
    {
        IServer server = app.Services.GetRequiredService<IServer>();
        IServerAddressesFeature addresses = server.Features.Get<IServerAddressesFeature>()
            ?? throw new InvalidOperationException("Kestrel did not expose a bound address.");
        return new HttpClient
        {
            BaseAddress = new Uri(addresses.Addresses.Single())
        };
    }

    private static PortalDeploymentIdentityReadiness EvaluateProduction(TemporaryContentRoot root)
        => new PortalDeploymentIdentityReadinessService(
            new FakeHostEnvironment(Environments.Production, root.Path)).Evaluate();

    private static void AssertInvalid(PortalDeploymentIdentityReadiness result)
    {
        Assert.False(result.Ready);
        Assert.Equal(PortalDeploymentIdentityReadinessService.InvalidCode, result.Code);
        Assert.Null(result.SourceFingerprintSha256);
        Assert.Null(result.FullDeploymentDigestSha256);
    }

    private static Dictionary<string, object?> CurrentBuildInfo(string fingerprint)
        => new()
        {
            ["contractName"] = PortalDeploymentIdentityReadinessService.OverlayContractName,
            ["status"] = PortalDeploymentIdentityReadinessService.OverlayStatus,
            ["activationStatus"] = PortalDeploymentIdentityReadinessService.OverlayActivationStatus,
            ["sourceFingerprint"] = new Dictionary<string, object?>
            {
                ["aggregateSha256"] = fingerprint,
                ["files"] = new Dictionary<string, object?>(),
                ["buildInputs"] = new Dictionary<string, object?>
                {
                    ["algorithm"] = PortalDeploymentIdentityReadinessService.SourceFingerprintAlgorithm,
                    ["aggregateSha256"] = new string('1', 64),
                    ["fileCount"] = 1
                },
                ["overlayPayloadInputs"] = new Dictionary<string, object?>
                {
                    ["algorithm"] = PortalDeploymentIdentityReadinessService.SourceFingerprintAlgorithm,
                    ["aggregateSha256"] = new string('2', 64),
                    ["fileCount"] = 2
                }
            },
            ["stagedPayloadFingerprint"] = new Dictionary<string, object?>
            {
                ["algorithm"] = PortalDeploymentIdentityReadinessService.StagedPayloadFingerprintAlgorithm,
                ["aggregateSha256"] = StagedPayloadFingerprint,
                ["fileCount"] = 1,
                ["excludedRelativePaths"] = new[] { RuntimeProofRelativePath }
            },
            ["payloadModeReceipt"] = CurrentPayloadModeReceipt(),
            ["fullDeploymentDigest"] = new Dictionary<string, object?>
            {
                ["contractName"] = PortalDeploymentIdentityReadinessService.FullDeploymentDigestContractName,
                ["algorithm"] = PortalDeploymentIdentityReadinessService.FullDeploymentDigestAlgorithm,
                ["sha256"] = FullDeploymentDigest
            }
        };

    private static Dictionary<string, object?> CurrentPayloadModeReceipt()
    {
        PayloadModeTestRow[] rows =
        [
            new(".", "directory", "0755"),
            new(".codex-studio", "directory", "0755"),
            new(".codex-studio/runtime", "directory", "0755"),
            new(
                ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json",
                "file",
                "0644"),
            new("app.dll", "file", "0644"),
            new("state", "state_directory", "0700"),
            new("wwwroot", "directory", "0755"),
            new("wwwroot/proofs", "directory", "0755"),
            new("wwwroot/proofs/mac-codex-release", "directory", "0755"),
            new(RuntimeProofRelativePath, "file", "0644")
        ];
        string bindingSha256 = PayloadModeBindingSha256(rows);
        return new Dictionary<string, object?>
        {
            ["contractName"] = PortalDeploymentIdentityReadinessService.PayloadModeContractName,
            ["algorithm"] = PortalDeploymentIdentityReadinessService.PayloadModeAlgorithm,
            ["status"] = "pass",
            ["checks"] = new Dictionary<string, object?>
            {
                ["exactModes"] = true,
                ["specialPermissionBitsClear"] = true
            },
            ["entryBinding"] = new Dictionary<string, object?>
            {
                ["algorithm"] = PortalDeploymentIdentityReadinessService.PayloadModeEntryBindingAlgorithm,
                ["rowCount"] = rows.Length,
                ["sha256"] = bindingSha256
            },
            ["executablePolicy"] = new Dictionary<string, object?>
            {
                ["algorithm"] = PortalDeploymentIdentityReadinessService.PayloadModeExecutablePolicyAlgorithm,
                ["relativePaths"] = Array.Empty<string>()
            },
            ["stateBoundary"] = new Dictionary<string, object?>
            {
                ["relativePath"] = "state",
                ["stateRootPresent"] = true,
                ["stateRootModeActual"] = "0700",
                ["stateRootModeExpected"] = "0700",
                ["stateRootModeMatches"] = true,
                ["stateContentsInspected"] = false
            },
            ["counts"] = new Dictionary<string, object?>
            {
                ["entryCount"] = rows.Length,
                ["directoryCount"] = 7,
                ["fileCount"] = 3,
                ["executableFileCount"] = 0,
                ["modeFailureCount"] = 0
            },
            ["entries"] = rows.Select(static row => new Dictionary<string, object?>
            {
                ["relativePath"] = row.RelativePath,
                ["kind"] = row.Kind,
                ["modeActual"] = row.Mode,
                ["modeExpected"] = row.Mode,
                ["matches"] = true,
                ["specialPermissionBitsClear"] = true
            }).ToArray(),
            ["failures"] = Array.Empty<object>()
        };
    }

    private static string PayloadModeBindingSha256(IEnumerable<PayloadModeTestRow> rows)
    {
        string canonical = "[" + string.Join(
            ",",
            rows.Select(static row =>
                $"{{\"kind\":\"{row.Kind}\",\"mode\":\"{row.Mode}\",\"relativePath\":\"{row.RelativePath}\"}}")) + "]";
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)))
            .ToLowerInvariant();
    }

    private sealed record PayloadModeTestRow(string RelativePath, string Kind, string Mode);

    private sealed class TemporaryContentRoot : IDisposable
    {
        private readonly List<string> externalHardlinks = [];

        public TemporaryContentRoot()
        {
            Path = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(),
                $"chummer-overlay-identity-{Guid.NewGuid():N}");
            Directory.CreateDirectory(Path);
            SetMode(Path, "0755");
        }

        public string Path { get; }

        public void WriteBuildInfo(object payload)
        {
            PreparePayload();
            string path = BuildInfoPath();
            File.WriteAllText(path, JsonSerializer.Serialize(payload));
            SetMode(path, "0644");
        }

        public void WriteRawBuildInfo(byte[] payload)
        {
            PreparePayload();
            string path = BuildInfoPath();
            File.WriteAllBytes(path, payload);
            SetMode(path, "0644");
        }

        public void WriteSymlinkedBuildInfo(object payload)
        {
            PreparePayload();
            string path = BuildInfoPath();
            string target = System.IO.Path.Combine(Path, "unbound-build-info.json");
            File.WriteAllText(target, JsonSerializer.Serialize(payload));
            SetMode(target, "0644");
            File.CreateSymbolicLink(path, target);
        }

        public void AddPayloadFile(string relativePath)
        {
            string path = System.IO.Path.Combine(Path, relativePath);
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!);
            File.WriteAllText(path, "drift");
            SetMode(path, "0644");
        }

        public void SetPayloadContents(string relativePath, string contents)
        {
            string path = System.IO.Path.Combine(Path, relativePath);
            File.WriteAllText(path, contents);
            SetMode(path, "0644");
        }

        public void RemovePayloadFile(string relativePath)
            => File.Delete(System.IO.Path.Combine(Path, relativePath));

        public void SetPayloadMode(string relativePath, string mode)
            => SetMode(System.IO.Path.Combine(Path, relativePath), mode);

        public void AddPayloadSymlink(string relativePath, string targetRelativePath)
            => File.CreateSymbolicLink(
                System.IO.Path.Combine(Path, relativePath),
                System.IO.Path.Combine(Path, targetRelativePath));

        public void ReplacePayloadWithSymlink(string relativePath, string targetRelativePath)
        {
            string path = System.IO.Path.Combine(Path, relativePath);
            File.Delete(path);
            File.CreateSymbolicLink(path, System.IO.Path.Combine(Path, targetRelativePath));
        }

        public void CreateExternalHardlink(string relativePath)
        {
            string source = System.IO.Path.Combine(Path, relativePath);
            string external = System.IO.Path.Combine(
                System.IO.Path.GetDirectoryName(Path)!,
                $"chummer-overlay-hardlink-{Guid.NewGuid():N}");
            if (NativeLink(source, external) != 0)
            {
                throw new IOException("Unable to create the hardlink test fixture.");
            }
            externalHardlinks.Add(external);
        }

        [DllImport("libc", EntryPoint = "link", SetLastError = true)]
        private static extern int NativeLink(string existingPath, string newPath);

        public void AddOpaqueStateContents()
        {
            string nestedDirectory = System.IO.Path.Combine(Path, "state", "private");
            Directory.CreateDirectory(nestedDirectory);
            string nestedFile = System.IO.Path.Combine(nestedDirectory, "operator-secret.bin");
            File.WriteAllText(nestedFile, "opaque");
            SetMode(nestedDirectory, "0777");
            SetMode(nestedFile, "0777");
        }

        private void PreparePayload()
        {
            string metadataDirectory = System.IO.Path.Combine(Path, ".codex-studio");
            string runtimeDirectory = System.IO.Path.Combine(metadataDirectory, "runtime");
            string stateDirectory = System.IO.Path.Combine(Path, "state");
            string runtimeProofPath = System.IO.Path.Combine(Path, RuntimeProofRelativePath);
            Directory.CreateDirectory(runtimeDirectory);
            Directory.CreateDirectory(stateDirectory);
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(runtimeProofPath)!);
            string appPath = System.IO.Path.Combine(Path, "app.dll");
            File.WriteAllText(appPath, "test-app");
            File.WriteAllText(runtimeProofPath, "runtime-proof");
            SetMode(Path, "0755");
            SetMode(metadataDirectory, "0755");
            SetMode(runtimeDirectory, "0755");
            SetMode(stateDirectory, "0700");
            SetMode(appPath, "0644");
            SetMode(System.IO.Path.Combine(Path, "wwwroot"), "0755");
            SetMode(System.IO.Path.Combine(Path, "wwwroot", "proofs"), "0755");
            SetMode(System.IO.Path.Combine(Path, "wwwroot", "proofs", "mac-codex-release"), "0755");
            SetMode(runtimeProofPath, "0644");
        }

        private static void SetMode(string path, string mode)
        {
            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(path, (UnixFileMode)Convert.ToInt32(mode, 8));
            }
        }

        private string BuildInfoPath()
            => System.IO.Path.Combine(
                Path,
                ".codex-studio",
                "runtime",
                "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json");

        public void Dispose()
        {
            foreach (string externalHardlink in externalHardlinks)
            {
                File.Delete(externalHardlink);
            }
            if (Directory.Exists(Path))
            {
                Directory.Delete(Path, recursive: true);
            }
        }
    }

    private sealed class FakeHostEnvironment(
        string environmentName,
        string contentRootPath) : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = environmentName;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = contentRootPath;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
