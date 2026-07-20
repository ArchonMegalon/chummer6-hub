using System.Security.Cryptography;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadSnapshotAuthorityTests
{
    [Fact]
    public void RawFleetCredentialCannotBypassMissingOrReviewOnlySnapshotPolicy()
    {
        using var fixture = new SnapshotFixture();
        Assert.Null(fixture.Evaluate());

        fixture.Publish("review_required");

        Assert.Null(fixture.Evaluate());
        ReleaseUploadSnapshotAuthority review = fixture.Authority.Load();
        Assert.True(review.IsValid, review.FailureReason);
        Assert.False(review.ReleaseUploadAuthority);
        Assert.False(review.CandidateImportAuthority);
    }

    [Fact]
    public void FullPassSnapshotAuthorizesFleetCredentialAndPrivilegedReconciliation()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("pass");

        ReleaseUploadAuthorizationContext authorization = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate());

        Assert.False(authorization.SingleUseAuthorization);
        Assert.True(authorization.AllowsPrivilegedReconciliation);
        Assert.Null(authorization.CandidateImportAuthority);
        Assert.Matches("^[0-9a-f]{64}$", authorization.AuthorizationBinding);
    }

    [Fact]
    public void CandidateSnapshotRequiresExactHeadersAndForcesSingleUseFleetAuthorization()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);

        Assert.Null(fixture.Evaluate());
        ReleaseUploadAuthorizationContext exact = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate));

        Assert.True(exact.SingleUseAuthorization);
        Assert.False(exact.AllowsPrivilegedReconciliation);
        Assert.Equal(candidate.SessionBinding, exact.CandidateImportAuthority?.SessionBinding);
        Assert.Equal(candidate.ExpiresAtUtc, exact.AuthorizationExpiresAtUtc);

        ReleaseUploadCandidateIdentity mismatch = candidate.Candidate with
        {
            InventorySha256 = new string('f', 64)
        };
        Assert.Null(fixture.Evaluate(mismatch));
    }

    [Fact]
    public void CandidateAuthorityIsGloballyOneShotAcrossFleetAndRotatedTickets()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);
        ReleaseUploadAuthorizationContext fleet = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate));
        ReleaseUploadTicketIssueResult firstTicket = fixture.IssueTicket("first-operator");
        ReleaseUploadTicketIssueResult secondTicket = fixture.IssueTicket("second-operator");
        ReleaseUploadAuthorizationContext first = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate, firstTicket.Ticket));
        ReleaseUploadAuthorizationContext second = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate, secondTicket.Ticket));

        Assert.Equal(fleet.AuthorizationBinding, first.AuthorizationBinding);
        Assert.Equal(fleet.AuthorizationBinding, second.AuthorizationBinding);
        ReleaseUploadSession created = fixture.UploadSessions.CreateSession(
            fleet.AuthorizationBinding,
            fleet.SingleUseAuthorization,
            fleet.AuthorizationExpiresAtUtc,
            fleet.CandidateImportAuthority?.SessionBinding);
        Assert.Equal(
            created.SessionId,
            fixture.UploadSessions.CreateSession(
                first.AuthorizationBinding,
                first.SingleUseAuthorization,
                first.AuthorizationExpiresAtUtc,
                first.CandidateImportAuthority?.SessionBinding).SessionId);
        Assert.Equal(
            created.SessionId,
            fixture.UploadSessions.CreateSession(
                second.AuthorizationBinding,
                second.SingleUseAuthorization,
                second.AuthorizationExpiresAtUtc,
                second.CandidateImportAuthority?.SessionBinding).SessionId);

        ReleaseBundlePromotionResult result = BuildPromotionResult();
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.UploadSessions.BeginCompletion(created.SessionId, fleet.AuthorizationBinding))
        {
            completion.RecordActivationIntent(BuildActivationIntent(result));
            completion.MarkCompleted(result);
        }

        foreach (ReleaseUploadAuthorizationContext replay in new[] { fleet, first, second })
        {
            InvalidOperationException consumed = Assert.Throws<InvalidOperationException>(() =>
                fixture.UploadSessions.CreateSession(
                    replay.AuthorizationBinding,
                    replay.SingleUseAuthorization,
                    replay.AuthorizationExpiresAtUtc,
                    replay.CandidateImportAuthority?.SessionBinding));
            Assert.Contains("already been consumed", consumed.Message, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void CandidateBundleValidatorRejectsAnyExtraOrChangedStagedByte()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);
        string bundle = fixture.CreateExactBundle(candidate);

        ReleaseUploadCandidateBundleValidator.Validate(bundle, candidate);
        File.WriteAllText(Path.Combine(bundle, "unexpected.bin"), "extra");

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadCandidateBundleValidator.Validate(bundle, candidate));
        Assert.Contains("exact candidate authority inventory", rejected.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("empty_capture")]
    [InlineData("capture_actor")]
    [InlineData("capture_workflow")]
    [InlineData("capture_run_id_whitespace")]
    [InlineData("capture_artifact_identity")]
    [InlineData("stale_capture")]
    [InlineData("not_native")]
    [InlineData("wine_runner")]
    [InlineData("ready_checkpoint")]
    [InlineData("visual_contract_version")]
    [InlineData("visual_contract_type")]
    [InlineData("empty_runner")]
    [InlineData("blank_runner")]
    [InlineData("artifact_digest")]
    [InlineData("scope_widen")]
    [InlineData("scope_narrow")]
    [InlineData("candidate_artifact_name")]
    [InlineData("export_source")]
    [InlineData("export_heads")]
    [InlineData("capture_heads_empty")]
    [InlineData("capture_heads_extra")]
    [InlineData("capture_receipt_fields")]
    [InlineData("capture_progress_path")]
    [InlineData("capture_screenshot_extra")]
    [InlineData("capture_width_type")]
    [InlineData("finalization_contract_type")]
    [InlineData("capture_inventory_root_extra")]
    [InlineData("capture_inventory_empty")]
    [InlineData("finalized_inventory_extra_row")]
    [InlineData("authority_root_extra")]
    [InlineData("candidate_extra")]
    [InlineData("custody_extra")]
    [InlineData("canonical_manifest_path")]
    [InlineData("inventory_path")]
    [InlineData("inventory_root_extra")]
    [InlineData("inventory_row_extra")]
    [InlineData("embedded_entry_extra")]
    [InlineData("visual_screenshot_order")]
    [InlineData("visual_checks_extra")]
    [InlineData("visual_checks_numeric")]
    [InlineData("visual_review_extra")]
    public void RuntimeRejectsFreshlyRehashedSemanticEvidenceTamper(string tamper)
    {
        using var fixture = new SnapshotFixture();
        byte[] authority = TamperCandidateAuthority(
            SnapshotFixture.BuildCandidateAuthority(),
            tamper);

        fixture.Publish("candidate_import_ready", authority);

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();
        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Fact]
    public void MatchingAliasRejectsExplicitNullWhenCompatibilityAliasExists()
    {
        using JsonDocument document = JsonDocument.Parse(
            "{\"version\":null,\"releaseVersion\":\"run-candidate\"}");
        MethodInfo method = typeof(ReleaseUploadSnapshotAuthorityService).GetMethod(
            "RequireMatchingAlias",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("alias validator is unavailable");

        TargetInvocationException rejected = Assert.Throws<TargetInvocationException>(() =>
            method.Invoke(
                null,
                [
                    document.RootElement,
                    "version",
                    "releaseVersion",
                    "candidate release version"
                ]));

        Assert.IsType<InvalidDataException>(rejected.InnerException);
    }

    [Fact]
    public void RuntimeRejectsWidenedBlazorPromotedHeadScope()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            SnapshotFixture.BuildCandidateAuthority(
                includeUndeclaredWindowsArtifacts: true));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Fact]
    public void RuntimeRejectsExtraRootLevelCandidateInventoryRow()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            SnapshotFixture.BuildCandidateAuthority(
                includeExtraRootInventoryRow: true));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Theory]
    [InlineData("rid")]
    [InlineData("kind")]
    [InlineData("file")]
    public void RuntimeRejectsAllowedHeadWindowsScopeWidening(string drift)
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            SnapshotFixture.BuildCandidateAuthority(
                allowedHeadScopeDrift: drift));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    private static byte[] TamperCandidateAuthority(byte[] payload, string tamper)
    {
        JsonObject authority = JsonNode.Parse(payload)?.AsObject()
            ?? throw new InvalidDataException("candidate fixture authority is invalid");
        JsonObject native = authority["custody"]!["nativeWindowsFinalizedEvidence"]!.AsObject();
        const string capturePath = "WINDOWS_NATIVE_CAPTURE.generated.json";
        const string finalizationPath = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json";
        const string startupPath = "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json";
        const string visualPath =
            "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json";
        const string exportPath =
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";

        switch (tamper)
        {
            case "empty_capture":
                RewriteEmbedded(authority, capturePath, new JsonObject());
                break;
            case "capture_actor":
            {
                JsonObject source = native["captureSource"]!.AsObject();
                source["actor"] = "untrusted-capture-actor";
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["source"] = source.DeepClone();
                RewriteEmbedded(authority, capturePath, capture);
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["captureSource"] = source.DeepClone();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "capture_workflow":
            {
                JsonObject source = native["captureSource"]!.AsObject();
                source["workflow"] = ".github/workflows/untrusted.yml";
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["source"] = source.DeepClone();
                RewriteEmbedded(authority, capturePath, capture);
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["captureSource"] = source.DeepClone();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "capture_run_id_whitespace":
            case "capture_artifact_identity":
            {
                JsonObject source = native["captureSource"]!.AsObject();
                if (tamper == "capture_run_id_whitespace")
                {
                    source["runId"] = "   ";
                }
                else
                {
                    source["artifactName"] = "unbound-capture-artifact";
                }
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["source"] = source.DeepClone();
                RewriteEmbedded(authority, capturePath, capture);
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["captureSource"] = source.DeepClone();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "stale_capture":
            {
                string stale = DateTimeOffset.UtcNow.AddDays(-2).ToString("O");
                native["captureGeneratedAtUtc"] = stale;
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["generatedAt"] = stale;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "not_native":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["executionEnvironment"] = "compatibility_layer";
                startup["nativeHostEvidence"]!["isNativeWindows"] = false;
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "wine_runner":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["nativeHostEvidence"]!["runner"] = "wine64";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "ready_checkpoint":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["readyCheckpoint"] = "post_ui_event_loop";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "visual_contract_version":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["contractVersion"] = 2;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_contract_type":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["contractVersion"] = true;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "empty_runner":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["nativeHostEvidence"]!["runner"] = "";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "blank_runner":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["nativeHostEvidence"]!["runner"] = "   ";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "artifact_digest":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["artifactDigest"] = "sha256:" + new string('f', 64);
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "scope_widen":
            {
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                JsonObject existing = finalization["proofs"]![0]!.AsObject();
                finalization["proofs"]!.AsArray().Add(new JsonObject
                {
                    ["headId"] = "blazor-desktop",
                    ["path"] = existing["path"]!.GetValue<string>(),
                    ["sha256"] = existing["sha256"]!.GetValue<string>()
                });
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "scope_narrow":
            {
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["proofs"] = new JsonArray();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "candidate_artifact_name":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["candidate"]!["artifactName"] =
                    "preview-nightly-candidate-99999-1";
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "export_source":
            {
                JsonObject export = ReadEmbedded(authority, exportPath);
                export["source"]!["actor"] = "different-producer";
                RewriteEmbedded(authority, exportPath, export);
                break;
            }
            case "export_heads":
            {
                JsonObject export = ReadEmbedded(authority, exportPath);
                export["heads"]![0]!["installer"]!["sha256"] = new string('f', 64);
                RewriteEmbedded(authority, exportPath, export);
                break;
            }
            case "capture_heads_empty":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"] = new JsonArray();
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_heads_extra":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                JsonArray heads = capture["heads"]!.AsArray();
                heads.Add(heads[0]!.DeepClone());
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_receipt_fields":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"]![0]!["receipt"]!["sizeBytes"] = 1;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_progress_path":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"]![0]!["progressLog"]!["path"] = startupPath;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_screenshot_extra":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                JsonArray screenshots = capture["heads"]![0]!["screenshots"]!.AsArray();
                screenshots.Add(screenshots[0]!.DeepClone());
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_width_type":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"]![0]!["screenshots"]![0]!["width"] = true;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "finalization_contract_type":
            {
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["contractVersion"] = true;
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "capture_inventory_root_extra":
            case "capture_inventory_empty":
            {
                JsonObject captureInventory = ReadEmbedded(
                    authority,
                    "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json");
                if (tamper == "capture_inventory_root_extra")
                {
                    captureInventory["unexpected"] = true;
                }
                else
                {
                    captureInventory["files"] = new JsonArray();
                }
                RewriteEmbedded(
                    authority,
                    "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json",
                    captureInventory);
                break;
            }
            case "finalized_inventory_extra_row":
            {
                JsonObject finalizedInventory = ReadEmbedded(
                    authority,
                    "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json");
                finalizedInventory["files"]!.AsArray().Add(new JsonObject
                {
                    ["path"] = "zz-unexpected.bin",
                    ["sha256"] = new string('0', 64),
                    ["sizeBytes"] = 1
                });
                RewriteEmbedded(
                    authority,
                    "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json",
                    finalizedInventory);
                break;
            }
            case "authority_root_extra":
                authority["unexpected"] = true;
                break;
            case "candidate_extra":
                authority["candidate"]!["unexpected"] = true;
                break;
            case "custody_extra":
                authority["custody"]!["unexpected"] = true;
                break;
            case "canonical_manifest_path":
                authority["custody"]!["canonicalManifest"]!["path"] =
                    "renamed-release-channel.json";
                break;
            case "inventory_path":
                authority["custody"]!["inventory"]!["path"] =
                    "renamed-candidate-inventory.json";
                break;
            case "inventory_root_extra":
            {
                JsonObject inventory = ReadCustodyEmbedded(authority, "inventory");
                inventory["unexpected"] = true;
                RewriteCustodyEmbedded(authority, "inventory", inventory);
                break;
            }
            case "inventory_row_extra":
            {
                JsonObject inventory = ReadCustodyEmbedded(authority, "inventory");
                inventory["files"]![0]!["unexpected"] = true;
                RewriteCustodyEmbedded(authority, "inventory", inventory);
                break;
            }
            case "embedded_entry_extra":
                FindEmbedded(authority, capturePath)["unexpected"] = true;
                break;
            case "visual_screenshot_order":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                JsonArray screenshots = visual["screenshots"]!.AsArray();
                JsonNode first = screenshots[0]!.DeepClone();
                screenshots[0] = screenshots[1]!.DeepClone();
                screenshots[1] = first;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_checks_extra":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["checks"]!["unexpected"] = true;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_checks_numeric":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["checks"]!["human_review_confirmed"] = 1;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_review_extra":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["readabilityReview"]!["unexpected"] = true;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            default:
                throw new ArgumentOutOfRangeException(nameof(tamper));
        }

        RefreshEvidenceBindings(authority);
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    private static JsonObject ReadEmbedded(JsonObject authority, string path)
    {
        JsonObject entry = FindEmbedded(authority, path);
        byte[] bytes = Convert.FromBase64String(entry["base64"]!.GetValue<string>());
        return JsonNode.Parse(bytes)?.AsObject()
            ?? throw new InvalidDataException("embedded candidate fixture is invalid");
    }

    private static void RewriteEmbedded(JsonObject authority, string path, JsonObject document)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(document);
        JsonObject entry = FindEmbedded(authority, path);
        entry["base64"] = Convert.ToBase64String(bytes);
        entry["sha256"] = Convert.ToHexStringLower(SHA256.HashData(bytes));
        entry["sizeBytes"] = bytes.LongLength;
    }

    private static JsonObject ReadCustodyEmbedded(JsonObject authority, string name)
    {
        JsonObject entry = authority["custody"]![name]!.AsObject();
        byte[] bytes = Convert.FromBase64String(entry["base64"]!.GetValue<string>());
        return JsonNode.Parse(bytes)?.AsObject()
            ?? throw new InvalidDataException("embedded custody fixture is invalid");
    }

    private static void RewriteCustodyEmbedded(
        JsonObject authority,
        string name,
        JsonObject document)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(document);
        JsonObject entry = authority["custody"]![name]!.AsObject();
        entry["base64"] = Convert.ToBase64String(bytes);
        entry["sha256"] = Convert.ToHexStringLower(SHA256.HashData(bytes));
        entry["sizeBytes"] = bytes.LongLength;
    }

    private static JsonObject FindEmbedded(JsonObject authority, string path)
    {
        JsonArray files = authority["custody"]!["nativeWindowsFinalizedEvidence"]!["files"]!.AsArray();
        return files
            .Select(static node => node!.AsObject())
            .Single(entry => string.Equals(
                entry["path"]!.GetValue<string>(),
                path,
                StringComparison.Ordinal));
    }

    private static void RefreshEvidenceBindings(JsonObject authority)
    {
        const string capturePath = "WINDOWS_NATIVE_CAPTURE.generated.json";
        const string captureInventoryPath = "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json";
        const string finalizationPath = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json";
        const string finalizedInventoryPath = "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json";
        JsonArray files = authority["custody"]!["nativeWindowsFinalizedEvidence"]!["files"]!.AsArray();
        var entries = files
            .Select(static node => node!.AsObject())
            .ToDictionary(
                static entry => entry["path"]!.GetValue<string>(),
                StringComparer.Ordinal);

        JsonObject capture = ReadEmbedded(authority, capturePath);
        if (capture["candidate"] is JsonObject captureCandidate)
        {
            foreach ((string property, string path) in new[]
                     {
                         (
                             "contentInventory",
                             "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"),
                         (
                             "exportReceipt",
                             "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json")
                     })
            {
                JsonObject entry = entries[path];
                captureCandidate[property] = new JsonObject
                {
                    ["path"] = path,
                    ["sha256"] = entry["sha256"]!.GetValue<string>(),
                    ["sizeBytes"] = entry["sizeBytes"]!.GetValue<long>()
                };
                captureCandidate[$"{property}Sha256"] =
                    entry["sha256"]!.GetValue<string>();
            }
        }
        if (capture["heads"] is JsonArray captureHeads)
        {
            foreach (JsonNode? node in captureHeads)
            {
                JsonObject head = node!.AsObject();
                foreach (string property in new[] { "receipt", "progressLog" })
                {
                    if (head[property] is JsonObject reference
                        && reference["path"] is JsonValue pathValue
                        && entries.TryGetValue(
                            pathValue.GetValue<string>(),
                            out JsonObject? entry))
                    {
                        reference["sha256"] = entry["sha256"]!.GetValue<string>();
                    }
                }
                if (head["screenshots"] is JsonArray screenshots)
                {
                    foreach (JsonNode? screenshotNode in screenshots)
                    {
                        JsonObject screenshot = screenshotNode!.AsObject();
                        string path = screenshot["path"]!.GetValue<string>();
                        if (entries.TryGetValue(path, out JsonObject? entry))
                        {
                            screenshot["sha256"] = entry["sha256"]!.GetValue<string>();
                        }
                    }
                }
            }
        }
        RewriteEmbedded(authority, capturePath, capture);

        JsonObject captureInventory = ReadEmbedded(authority, captureInventoryPath);
        captureInventory["captureManifestSha256"] = entries[capturePath]["sha256"]!.GetValue<string>();
        foreach (JsonNode? node in captureInventory["files"]!.AsArray())
        {
            JsonObject row = node!.AsObject();
            string path = row["path"]!.GetValue<string>();
            if (entries.TryGetValue(path, out JsonObject? entry))
            {
                row["sha256"] = entry["sha256"]!.GetValue<string>();
                row["sizeBytes"] = entry["sizeBytes"]!.GetValue<long>();
            }
        }
        RewriteEmbedded(authority, captureInventoryPath, captureInventory);

        JsonObject finalization = ReadEmbedded(authority, finalizationPath);
        string captureInventorySha256 =
            entries[captureInventoryPath]["sha256"]!.GetValue<string>();
        finalization["captureInventorySha256"] = captureInventorySha256;
        foreach (JsonNode? node in finalization["proofs"]!.AsArray())
        {
            JsonObject proofBinding = node!.AsObject();
            string proofPath = proofBinding["path"]!.GetValue<string>();
            JsonObject proof = ReadEmbedded(authority, proofPath);
            if (capture["source"] is JsonObject refreshedCaptureSource)
            {
                proof["review"]!["captureActor"] =
                    refreshedCaptureSource["actor"]!.GetValue<string>();
                proof["captureBinding"] = new JsonObject
                {
                    ["repository"] = refreshedCaptureSource["repository"]!.GetValue<string>(),
                    ["workflow"] = refreshedCaptureSource["workflow"]!.GetValue<string>(),
                    ["runId"] = refreshedCaptureSource["runId"]!.GetValue<string>(),
                    ["runAttempt"] = refreshedCaptureSource["runAttempt"]!.GetValue<string>(),
                    ["ref"] = refreshedCaptureSource["ref"]!.GetValue<string>(),
                    ["sha"] = refreshedCaptureSource["sha"]!.GetValue<string>(),
                    ["artifactName"] = refreshedCaptureSource["artifactName"]!.GetValue<string>(),
                    ["inventorySha256"] = captureInventorySha256
                };
                RewriteEmbedded(authority, proofPath, proof);
            }
            proofBinding["sha256"] = entries[proofPath]["sha256"]!.GetValue<string>();
        }
        RewriteEmbedded(authority, finalizationPath, finalization);

        JsonObject finalizedInventory = ReadEmbedded(authority, finalizedInventoryPath);
        finalizedInventory["captureInventorySha256"] = captureInventorySha256;
        foreach (JsonNode? node in finalizedInventory["files"]!.AsArray())
        {
            JsonObject row = node!.AsObject();
            string path = row["path"]!.GetValue<string>();
            if (entries.TryGetValue(path, out JsonObject? entry))
            {
                row["sha256"] = entry["sha256"]!.GetValue<string>();
                row["sizeBytes"] = entry["sizeBytes"]!.GetValue<long>();
            }
        }
        RewriteEmbedded(authority, finalizedInventoryPath, finalizedInventory);
    }

    private sealed class SnapshotFixture : IDisposable
    {
        private static readonly byte[] InstallerBytes = "MZ-avalonia-installer"u8.ToArray();
        private static readonly byte[] PayloadBytes = "PK-avalonia-payload"u8.ToArray();
        private static readonly byte[] BlazorInstallerBytes = "MZ-blazor-installer"u8.ToArray();
        private static readonly byte[] BlazorPayloadBytes = "PK-blazor-payload"u8.ToArray();
        private static readonly string[] BaseOutputNames =
        [
            "HUB_LOCAL_RELEASE_PROOF.generated.json",
            "HUB_SERVED_RELEASE_PROOF.generated.json",
            "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
            "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
            "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
            "RELEASE_CHANNEL.generated.json",
            "FLAGSHIP_PRODUCT_READINESS.generated.json"
        ];
        private readonly string _root;
        private readonly IDataProtectionProvider _protection;

        public SnapshotFixture()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                "release-upload-snapshot-authority-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [PublicProjectionSnapshotService.SnapshotRootConfigurationKey] = _root,
                    [PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey] = "true",
                    ["FLEET_INTERNAL_API_TOKEN"] = "fleet-test-token",
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions"),
                    ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_BYTES"] = "0",
                    ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_FRACTION"] = "0"
                })
                .Build();
            _protection = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(_root, "keys")));
            Tickets = new ReleaseUploadTicketService(_protection, Configuration);
            Authority = new ReleaseUploadSnapshotAuthorityService(Configuration);
            Evaluator = new ReleaseUploadAuthorizationEvaluator(
                Configuration,
                Tickets,
                Authority);
            UploadSessions = new ReleaseBundleUploadSessionService(
                Configuration,
                NullLogger<ReleaseBundleUploadSessionService>.Instance);
        }

        public IConfiguration Configuration { get; }
        public ReleaseUploadTicketService Tickets { get; }
        public ReleaseUploadSnapshotAuthorityService Authority { get; }
        public ReleaseUploadAuthorizationEvaluator Evaluator { get; }
        public ReleaseBundleUploadSessionService UploadSessions { get; }

        public ReleaseUploadAuthorizationContext? Evaluate(
            ReleaseUploadCandidateIdentity? candidate = null,
            string bearer = "fleet-test-token")
        {
            var context = new DefaultHttpContext();
            context.Request.Method = HttpMethods.Post;
            context.Request.Path = "/api/internal/releases/upload-sessions";
            context.Request.Headers.Authorization = $"Bearer {bearer}";
            if (candidate is not null)
            {
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateManifestSha256Header] =
                    candidate.CanonicalManifestSha256;
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateInventorySha256Header] =
                    candidate.InventorySha256;
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateBundleIdentitySha256Header] =
                    candidate.BundleIdentitySha256;
            }
            return Evaluator.Evaluate(context.Request);
        }

        public ReleaseUploadTicketIssueResult IssueTicket(string subjectId)
            => Tickets.Issue(new AuthenticatedHubSubject(
                SubjectId: subjectId,
                DisplayName: subjectId,
                Email: $"{subjectId}@example.com",
                Roles: ["operator"],
                AccessToken: "identity-token"));

        public void Publish(string status, byte[]? candidateAuthority = null)
        {
            byte[] local = "{\"status\":\"projection\"}\n"u8.ToArray();
            var payloads = BaseOutputNames.ToDictionary(
                static name => name,
                _ => "{\"status\":\"test\"}\n"u8.ToArray(),
                StringComparer.Ordinal);
            payloads[BaseOutputNames[0]] = local;
            payloads[BaseOutputNames[1]] = local;
            if (status == "candidate_import_ready")
            {
                payloads[ReleaseUploadSnapshotAuthorityService.CandidateAuthorityFileName] =
                    candidateAuthority ?? BuildCandidateAuthority();
            }
            string[] outputNames = payloads.Keys.ToArray();
            var digests = payloads.ToDictionary(
                static pair => pair.Key,
                static pair => Sha256(pair.Value),
                StringComparer.Ordinal);
            string aggregate = SnapshotDigest(outputNames, digests);
            string snapshotId = $"public-projection-{aggregate}";
            string directory = Path.Combine(_root, snapshotId);
            Directory.CreateDirectory(directory);
            foreach ((string name, byte[] payload) in payloads)
            {
                File.WriteAllBytes(Path.Combine(directory, name), payload);
            }
            (string stage, bool code, bool release, bool candidate) = status switch
            {
                "pass" => ("release_upload_ready", true, true, false),
                "review_required" => ("code_deploy_review_required", true, false, false),
                "candidate_import_ready" => ("candidate_import_ready", false, false, true),
                _ => throw new ArgumentOutOfRangeException(nameof(status))
            };
            object[] findings = status switch
            {
                "pass" => [],
                "review_required" =>
                [
                    new
                    {
                        gate = "live public Windows installer",
                        status = "postdeploy_required",
                        reason = "live Windows installer proof must pass after code deployment"
                    }
                ],
                _ =>
                [
                    new
                    {
                        gate = "live release convergence after candidate import",
                        status = "postdeploy_required",
                        reason = "candidate bytes require live verification before release upload authority can be restored"
                    }
                ]
            };
            var common = new Dictionary<string, object?>
            {
                ["status"] = status,
                ["projectionStage"] = stage,
                ["codeDeploymentAuthority"] = code,
                ["releaseUploadAuthority"] = release,
                ["candidateImportAuthority"] = candidate,
                ["releaseGateFindings"] = findings,
                ["snapshotId"] = snapshotId,
                ["snapshotSha256"] = aggregate
            };
            var manifest = new Dictionary<string, object?>(common)
            {
                ["contractName"] = "chummer.public_projection_snapshot/v1",
                ["authorityInputs"] = new Dictionary<string, object?>(),
                ["outputs"] = outputNames.ToDictionary(
                    static name => name,
                    name => (object)new Dictionary<string, object?>
                    {
                        ["relativePath"] = name,
                        ["sha256"] = digests[name],
                        ["sizeBytes"] = payloads[name].LongLength
                    },
                    StringComparer.Ordinal)
            };
            byte[] manifestBytes = JsonSerializer.SerializeToUtf8Bytes(manifest);
            File.WriteAllBytes(
                Path.Combine(directory, "PUBLIC_PROJECTION_SNAPSHOT.generated.json"),
                manifestBytes);
            var pointer = new Dictionary<string, object?>(common)
            {
                ["contractName"] = "chummer.public_projection_current/v1",
                ["manifestRelativePath"] =
                    $"{snapshotId}/PUBLIC_PROJECTION_SNAPSHOT.generated.json",
                ["manifestSha256"] = Sha256(manifestBytes),
                ["outputs"] = outputNames.ToDictionary(
                    static name => name,
                    name => (object)$"{snapshotId}/{name}",
                    StringComparer.Ordinal)
            };
            File.WriteAllBytes(
                Path.Combine(_root, "CURRENT.json"),
                JsonSerializer.SerializeToUtf8Bytes(pointer));
        }

        public string CreateExactBundle(ReleaseUploadCandidateAuthority authority)
        {
            string root = Path.Combine(_root, "exact-bundle");
            Directory.CreateDirectory(root);
            JsonObject generatedAuthority = JsonNode.Parse(BuildCandidateAuthority())?.AsObject()
                ?? throw new InvalidDataException("candidate fixture authority is invalid");
            byte[] contentInventoryBytes = Convert.FromBase64String(
                FindEmbedded(
                    generatedAuthority,
                    CandidateProvenanceInventoryPath)["base64"]!.GetValue<string>());
            byte[] exportReceiptBytes = Convert.FromBase64String(
                FindEmbedded(
                    generatedAuthority,
                    CandidateProvenanceExportPath)["base64"]!.GetValue<string>());
            foreach (ReleaseUploadCandidateInventoryRow row in authority.Inventory)
            {
                string path = Path.Combine(root, row.Path.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                byte[] bytes = row.Path switch
                {
                    "RELEASE_CHANNEL.generated.json" => authority.CanonicalManifestBytes,
                    "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json" =>
                        contentInventoryBytes,
                    "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json" =>
                        exportReceiptBytes,
                    "files/chummer-avalonia-win-x64-installer.exe" => InstallerBytes,
                    "files/chummer-avalonia-win-x64-payload.zip" => PayloadBytes,
                    _ => throw new InvalidDataException("unexpected candidate fixture path")
                };
                File.WriteAllBytes(path, bytes);
            }
            return root;
        }

        public static byte[] BuildCandidateAuthority(
            bool includeUndeclaredWindowsArtifacts = false,
            string? allowedHeadScopeDrift = null,
            bool includeExtraRootInventoryRow = false)
        {
            string installerSha = Sha256(InstallerBytes);
            string payloadSha = Sha256(PayloadBytes);
            string blazorInstallerSha = Sha256(BlazorInstallerBytes);
            string blazorPayloadSha = Sha256(BlazorPayloadBytes);
            var manifestArtifacts = new List<object>
            {
                new
                {
                    artifactId = "avalonia-win-x64-installer",
                    head = "avalonia",
                    platform = "windows",
                    rid = "win-x64",
                    arch = "x64",
                    kind = "installer",
                    installerMode = "bootstrap",
                    payloadAcquisitionMode = "download",
                    fileName = "chummer-avalonia-win-x64-installer.exe",
                    sha256 = installerSha,
                    sizeBytes = InstallerBytes.LongLength,
                    payloadFileName = "chummer-avalonia-win-x64-payload.zip",
                    payloadSha256 = payloadSha,
                    payloadSizeBytes = PayloadBytes.LongLength
                }
            };
            if (includeUndeclaredWindowsArtifacts)
            {
                manifestArtifacts.Add(new
                {
                    artifactId = "blazor-desktop-win-x64-installer",
                    head = "blazor-desktop",
                    platform = "windows",
                    rid = "win-x64",
                    arch = "x64",
                    kind = "installer",
                    installerMode = "bootstrap",
                    payloadAcquisitionMode = "download",
                    fileName = "chummer-blazor-desktop-win-x64-installer.exe",
                    sha256 = blazorInstallerSha,
                    sizeBytes = BlazorInstallerBytes.LongLength,
                    payloadFileName = "chummer-blazor-desktop-win-x64-payload.zip",
                    payloadSha256 = blazorPayloadSha,
                    payloadSizeBytes = BlazorPayloadBytes.LongLength
                });
            }
            if (allowedHeadScopeDrift == "rid")
            {
                manifestArtifacts.Add(new
                {
                    artifactId = "avalonia-win-arm64-installer",
                    head = "avalonia",
                    platform = "windows",
                    rid = "win-arm64",
                    arch = "arm64",
                    kind = "installer",
                    installerMode = "bootstrap",
                    payloadAcquisitionMode = "download",
                    fileName = "chummer-avalonia-win-arm64-installer.exe",
                    sha256 = blazorInstallerSha,
                    sizeBytes = BlazorInstallerBytes.LongLength,
                    payloadFileName = "chummer-avalonia-win-arm64-payload.zip",
                    payloadSha256 = blazorPayloadSha,
                    payloadSizeBytes = BlazorPayloadBytes.LongLength
                });
            }
            else if (allowedHeadScopeDrift == "kind")
            {
                manifestArtifacts.Add(new
                {
                    artifactId = "avalonia-win-x64-symbols",
                    head = "avalonia",
                    platform = "windows",
                    rid = "win-x64",
                    arch = "x64",
                    kind = "archive",
                    fileName = "chummer-avalonia-win-x64-symbols.zip",
                    sha256 = blazorPayloadSha,
                    sizeBytes = BlazorPayloadBytes.LongLength
                });
            }
            else if (allowedHeadScopeDrift is not null and not "file")
            {
                throw new ArgumentOutOfRangeException(nameof(allowedHeadScopeDrift));
            }
            byte[] canonical = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "Chummer.Hub.Registry.Contracts",
                version = "run-candidate",
                releaseVersion = "run-candidate",
                channel = "preview",
                channelId = "preview",
                artifacts = manifestArtifacts,
                desktopTupleCoverage = new
                {
                    requiredDesktopHeads = includeUndeclaredWindowsArtifacts
                        ? new[] { "avalonia", "blazor-desktop" }
                        : new[] { "avalonia" }
                }
            });
            string canonicalSha = Sha256(canonical);
            var rows = new List<ReleaseUploadCandidateInventoryRow>
            {
                new ReleaseUploadCandidateInventoryRow(
                    "RELEASE_CHANNEL.generated.json",
                    canonical.LongLength,
                    canonicalSha),
                new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-installer.exe",
                    InstallerBytes.LongLength,
                    installerSha),
                new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-payload.zip",
                    PayloadBytes.LongLength,
                    payloadSha)
            };
            if (includeUndeclaredWindowsArtifacts)
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-blazor-desktop-win-x64-installer.exe",
                    BlazorInstallerBytes.LongLength,
                    blazorInstallerSha));
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-blazor-desktop-win-x64-payload.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            if (allowedHeadScopeDrift == "rid")
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-arm64-installer.exe",
                    BlazorInstallerBytes.LongLength,
                    blazorInstallerSha));
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-arm64-payload.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            else if (allowedHeadScopeDrift == "kind")
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-symbols.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            else if (allowedHeadScopeDrift == "file")
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-debug.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            if (includeUndeclaredWindowsArtifacts || allowedHeadScopeDrift is not null)
            {
                rows.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
            }
            string inventorySha =
                ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(rows);
            var candidate = new ReleaseUploadCandidateIdentity(
                "run-candidate",
                canonicalSha,
                inventorySha,
                rows.Count,
                rows.Sum(static row => row.SizeBytes),
                string.Empty);
            candidate = candidate with
            {
                BundleIdentitySha256 =
                    ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(candidate)
            };
            byte[] inventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-inventory/v1",
                contractVersion = 1,
                files = rows.Select(row => new
                {
                    path = row.Path,
                    sha256 = row.Sha256,
                    sizeBytes = row.SizeBytes
                })
            });
            DateTimeOffset now = DateTimeOffset.UtcNow;
            var captureSource = new Dictionary<string, object?>
            {
                ["repository"] = "ArchonMegalon/chummer6-ui",
                ["workflow"] = ".github/workflows/windows-native-evidence-capture.yml",
                ["runId"] = "12345",
                ["runAttempt"] = "1",
                ["ref"] = "refs/heads/main",
                ["sha"] = new string('a', 40),
                ["actor"] = "github-actions[bot]",
                ["artifactName"] = "windows-native-evidence-12345-1"
            };
            var finalizationSource = new Dictionary<string, object?>
            {
                ["repository"] = "ArchonMegalon/chummer6-ui",
                ["workflow"] = ".github/workflows/windows-native-evidence-finalize.yml",
                ["runId"] = "12345",
                ["runAttempt"] = "1",
                ["ref"] = "refs/heads/main",
                ["sha"] = new string('a', 40),
                ["actor"] = "accountable-reviewer",
                ["artifactName"] = "windows-native-evidence-finalized-12345-1"
            };
            object[] provenanceRows = rows.Select(row => (object)new
            {
                path = row.Path,
                sha256 = row.Sha256,
                sizeBytes = row.SizeBytes
            }).ToArray();
            byte[] provenance = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-candidate-content-inventory",
                contractVersion = 1,
                release = new { channel = "preview", version = "run-candidate" },
                manifest = new
                {
                    path = "RELEASE_CHANNEL.generated.json",
                    sha256 = canonicalSha
                },
                files = provenanceRows
            });
            byte[] startup = JsonSerializer.SerializeToUtf8Bytes(new
            {
                status = "pass",
                readyCheckpoint = "pre_ui_event_loop",
                headId = "avalonia",
                platform = "windows",
                rid = "win-x64",
                channelId = "preview",
                releaseVersion = "run-candidate",
                artifactFileName = "chummer-avalonia-win-x64-installer.exe",
                artifactDigest = $"sha256:{installerSha}",
                bootstrapPayloadAcquisitionMode = "download",
                bootstrapPayloadFileName = "chummer-avalonia-win-x64-payload.zip",
                bootstrapPayloadSha256 = payloadSha,
                bootstrapPayloadSizeBytes = PayloadBytes.LongLength,
                executionEnvironment = "native_windows",
                nativeHostEvidence = new
                {
                    contractName = "chummer6-ui.native_windows_host_evidence",
                    status = "verified",
                    isNativeWindows = true,
                    hostPlatform = "windows",
                    hostKernel = "Windows_NT",
                    runner = "powershell.exe",
                    evidenceSource = "GitHub-hosted windows-latest"
                }
            });
            byte[] progressScreenshot = "png-progress"u8.ToArray();
            byte[] completionScreenshot = "png-completion"u8.ToArray();
            byte[] progressLog = "Install complete\n"u8.ToArray();
            const string visualPath =
                "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json";
            byte[] visual = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.windows_installer_visual_proof",
                contractVersion = 1,
                status = "passed",
                generatedAt = now,
                version = "run-candidate",
                releaseVersion = "run-candidate",
                channel = "preview",
                channelId = "preview",
                platform = "windows",
                head = "avalonia",
                headId = "avalonia",
                rid = "win-x64",
                artifactFileName = "chummer-avalonia-win-x64-installer.exe",
                artifactDigest = $"sha256:{installerSha}",
                screenshots = new object[]
                {
                    new
                    {
                        role = "progress",
                        path = "screenshots/windows-installer-avalonia-win-x64-progress.png",
                        sha256 = Sha256(progressScreenshot)
                    },
                    new
                    {
                        role = "completion",
                        path = "screenshots/windows-installer-avalonia-win-x64-completion.png",
                        sha256 = Sha256(completionScreenshot)
                    }
                },
                checks = new
                {
                    capture_mode = "interactive",
                    human_review_confirmed = true
                },
                readabilityReview = new { status = "passed", reviewer = "accountable-reviewer" },
                contrastReview = new { status = "passed", reviewer = "accountable-reviewer" },
                clippingReview = new { status = "passed", reviewer = "accountable-reviewer" },
                finalizationBinding = finalizationSource
            });
            var producerSource = new Dictionary<string, object?>
            {
                ["repository"] = "ArchonMegalon/chummer6-ui",
                ["workflow"] = ".github/workflows/preview-nightly-candidate-export.yml",
                ["runId"] = "900",
                ["runAttempt"] = "1",
                ["ref"] = "refs/heads/main",
                ["sha"] = new string('a', 40),
                ["actor"] = "candidate-producer",
                ["artifactName"] = "preview-nightly-candidate-900-1"
            };
            var exportHead = new
            {
                headId = "avalonia",
                rid = "win-x64",
                installer = new
                {
                    relativePath = "files/chummer-avalonia-win-x64-installer.exe",
                    fileName = "chummer-avalonia-win-x64-installer.exe",
                    sha256 = installerSha,
                    sizeBytes = InstallerBytes.LongLength
                },
                payload = new
                {
                    relativePath = "files/chummer-avalonia-win-x64-payload.zip",
                    fileName = "chummer-avalonia-win-x64-payload.zip",
                    sha256 = payloadSha,
                    sizeBytes = PayloadBytes.LongLength
                }
            };
            var exportSource = new Dictionary<string, object?>(producerSource)
            {
                ["runnerLabel"] = "chummer-preview-nightly-export-abcdefghijkl"
            };
            byte[] export = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-candidate-export",
                contractVersion = 1,
                status = "exported",
                release = new { channel = "preview", version = "run-candidate" },
                candidateManifest = new
                {
                    path = "RELEASE_CHANNEL.generated.json",
                    sha256 = canonicalSha
                },
                contentInventory = new
                {
                    path = "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
                    sha256 = Sha256(provenance)
                },
                source = exportSource,
                heads = new[] { exportHead }
            });
            rows.Add(new ReleaseUploadCandidateInventoryRow(
                "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
                provenance.LongLength,
                Sha256(provenance)));
            rows.Add(new ReleaseUploadCandidateInventoryRow(
                "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json",
                export.LongLength,
                Sha256(export)));
            if (includeExtraRootInventoryRow)
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "UNEXPECTED.generated.json",
                    3,
                    Sha256("{}\n"u8.ToArray())));
            }
            rows.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
            inventorySha = ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(rows);
            candidate = new ReleaseUploadCandidateIdentity(
                "run-candidate",
                canonicalSha,
                inventorySha,
                rows.Count,
                rows.Sum(static row => row.SizeBytes),
                string.Empty);
            candidate = candidate with
            {
                BundleIdentitySha256 =
                    ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(candidate)
            };
            inventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-inventory/v1",
                contractVersion = 1,
                files = rows.Select(row => new
                {
                    path = row.Path,
                    sha256 = row.Sha256,
                    sizeBytes = row.SizeBytes
                })
            });
            string artifactCreatedAt = now.AddMinutes(-1).ToString(
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                System.Globalization.CultureInfo.InvariantCulture);
            string artifactExpiresAt = now.AddDays(14).ToString(
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                System.Globalization.CultureInfo.InvariantCulture);
            const string artifactId = "503";
            string artifactSha = new('d', 64);
            var handoff = new Dictionary<string, object?>(producerSource)
            {
                ["contractName"] = "chummer6-ui.preview-nightly-candidate-handoff",
                ["contractVersion"] = 1,
                ["artifactId"] = artifactId,
                ["artifactSha256"] = artifactSha,
                ["contentInventorySha256"] = Sha256(provenance)
            };
            var authenticatedApi = new Dictionary<string, object?>(producerSource)
            {
                ["contractName"] = "chummer6-ui.preview-nightly-candidate-authenticated-api",
                ["contractVersion"] = 1,
                ["artifactId"] = artifactId,
                ["artifactSha256"] = artifactSha,
                ["artifactCreatedAt"] = artifactCreatedAt,
                ["artifactExpiresAt"] = artifactExpiresAt,
                ["event"] = "workflow_dispatch",
                ["status"] = "completed",
                ["conclusion"] = "success"
            };
            var captureCandidate = new Dictionary<string, object?>(producerSource)
            {
                ["artifactId"] = artifactId,
                ["artifactSha256"] = artifactSha,
                ["artifactCreatedAt"] = artifactCreatedAt,
                ["artifactExpiresAt"] = artifactExpiresAt,
                ["manifestPath"] = "RELEASE_CHANNEL.generated.json",
                ["manifestSha256"] = canonicalSha,
                ["contentInventorySha256"] = Sha256(provenance),
                ["exportReceiptSha256"] = Sha256(export),
                ["handoffSha256"] = Sha256(JsonSerializer.SerializeToUtf8Bytes(handoff)),
                ["authenticatedApiSha256"] = Sha256(
                    JsonSerializer.SerializeToUtf8Bytes(authenticatedApi)),
                ["contentInventory"] = new
                {
                    path = CandidateProvenanceInventoryPath,
                    sha256 = Sha256(provenance),
                    sizeBytes = provenance.LongLength
                },
                ["exportReceipt"] = new
                {
                    path = CandidateProvenanceExportPath,
                    sha256 = Sha256(export),
                    sizeBytes = export.LongLength
                }
            };
            var captureHead = new
            {
                exportHead.headId,
                exportHead.rid,
                exportHead.installer,
                exportHead.payload,
                receipt = new
                {
                    path = "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                    sha256 = Sha256(startup)
                },
                progressLog = new
                {
                    path = "startup-smoke/windows-installer-progress-avalonia-win-x64.log",
                    sha256 = Sha256(progressLog)
                },
                screenshots = new object[]
                {
                    new
                    {
                        role = "progress",
                        path = "screenshots/windows-installer-avalonia-win-x64-progress.png",
                        sha256 = Sha256(progressScreenshot),
                        width = 1280,
                        height = 720
                    },
                    new
                    {
                        role = "completion",
                        path = "screenshots/windows-installer-avalonia-win-x64-completion.png",
                        sha256 = Sha256(completionScreenshot),
                        width = 1280,
                        height = 720
                    }
                }
            };
            byte[] capture = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-capture",
                contractVersion = 1,
                status = "captured",
                captureMode = "interactive",
                generatedAt = now,
                version = "run-candidate",
                channelId = "preview",
                source = captureSource,
                candidate = captureCandidate,
                heads = new[] { captureHead }
            });
            object[] captureInventoryRows = new (string Path, byte[] Bytes)[]
                {
                    ("WINDOWS_NATIVE_CAPTURE.generated.json", capture),
                    (CandidateProvenanceInventoryPath, provenance),
                    (CandidateProvenanceExportPath, export),
                    (
                        "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                        startup),
                    (
                        "startup-smoke/windows-installer-progress-avalonia-win-x64.log",
                        progressLog),
                    (
                        "screenshots/windows-installer-avalonia-win-x64-progress.png",
                        progressScreenshot),
                    (
                        "screenshots/windows-installer-avalonia-win-x64-completion.png",
                        completionScreenshot)
                }
                .OrderBy(static row => row.Path, StringComparer.Ordinal)
                .Select(row => (object)new
                {
                    path = row.Path,
                    sha256 = Sha256(row.Bytes),
                    sizeBytes = row.Bytes.LongLength
                })
                .ToArray();
            byte[] captureInventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-capture-inventory",
                contractVersion = 1,
                captureContract = "chummer6-ui.preview-nightly-native-windows-capture",
                captureManifestSha256 = Sha256(capture),
                files = captureInventoryRows
            });
            JsonObject visualDocument = JsonNode.Parse(visual)!.AsObject();
            visualDocument["review"] = JsonSerializer.SerializeToNode(new
            {
                authenticatedReviewer = "accountable-reviewer",
                captureActor = "github-actions[bot]",
                allowlistSource = "repository variable plus protected environment",
                explicitConfirmations = new
                {
                    readability = "passed",
                    contrast = "passed",
                    clipping = "passed"
                }
            });
            visualDocument["captureBinding"] = JsonSerializer.SerializeToNode(new
            {
                repository = captureSource["repository"],
                workflow = captureSource["workflow"],
                runId = captureSource["runId"],
                runAttempt = captureSource["runAttempt"],
                @ref = captureSource["ref"],
                sha = captureSource["sha"],
                artifactName = captureSource["artifactName"],
                inventorySha256 = Sha256(captureInventory)
            });
            visual = JsonSerializer.SerializeToUtf8Bytes(visualDocument);
            byte[] finalization = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-finalization",
                contractVersion = 1,
                status = "passed",
                generatedAt = now,
                captureInventorySha256 = Sha256(captureInventory),
                captureSource,
                finalizationSource,
                reviewer = "accountable-reviewer",
                reviewerWasCaptureActor = false,
                humanReviewConfirmed = true,
                proofs = new object[]
                {
                    new { headId = "avalonia", path = visualPath, sha256 = Sha256(visual) }
                }
            });
            var evidence = new Dictionary<string, byte[]>(StringComparer.Ordinal)
            {
                ["WINDOWS_NATIVE_CAPTURE.generated.json"] = capture,
                ["WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"] = captureInventory,
                ["WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"] = finalization,
                [CandidateProvenanceInventoryPath] = provenance,
                [CandidateProvenanceExportPath] = export,
                ["startup-smoke/startup-smoke-avalonia-win-x64.receipt.json"] = startup,
                [visualPath] = visual
            };
            object[] finalizedRows = evidence
                .Select(pair => (Path: pair.Key, Bytes: pair.Value))
                .Concat(
                [
                    (
                        Path: "screenshots/windows-installer-avalonia-win-x64-completion.png",
                        Bytes: completionScreenshot),
                    (
                        Path: "screenshots/windows-installer-avalonia-win-x64-progress.png",
                        Bytes: progressScreenshot),
                    (
                        Path: "startup-smoke/windows-installer-progress-avalonia-win-x64.log",
                        Bytes: progressLog)
                ])
                .OrderBy(static subject => subject.Path, StringComparer.Ordinal)
                .Select(subject => (object)new
                {
                    path = subject.Path,
                    sha256 = Sha256(subject.Bytes),
                    sizeBytes = subject.Bytes.LongLength
                })
                .ToArray();
            byte[] finalizedInventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-finalized-inventory",
                contractVersion = 1,
                captureInventorySha256 = Sha256(captureInventory),
                files = finalizedRows
            });
            evidence["WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"] = finalizedInventory;
            using JsonDocument provenanceDocument = JsonDocument.Parse(provenance);
            return JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-import-authority/v1",
                contractVersion = 1,
                status = "candidate_import_ready",
                generatedAtUtc = now,
                expiresAtUtc = now.AddHours(2),
                candidate = new
                {
                    version = candidate.Version,
                    canonicalManifestSha256 = candidate.CanonicalManifestSha256,
                    inventorySha256 = candidate.InventorySha256,
                    fileCount = candidate.FileCount,
                    totalBytes = candidate.TotalBytes,
                    bundleIdentitySha256 = candidate.BundleIdentitySha256
                },
                custody = new
                {
                    canonicalManifest = Embedded("RELEASE_CHANNEL.generated.json", canonical),
                    inventory = Embedded("CANDIDATE_UPLOAD_INVENTORY.generated.json", inventory),
                    nativeWindowsFinalizedEvidence = new
                    {
                        status = "passed",
                        captureGeneratedAtUtc = now,
                        finalizationGeneratedAtUtc = now,
                        reviewer = "accountable-reviewer",
                        captureSource,
                        finalizationSource,
                        candidateContentInventorySha256 = Sha256(provenance),
                        candidateContentInventory = provenanceDocument.RootElement.Clone(),
                        files = evidence
                            .OrderBy(static pair => pair.Key, StringComparer.Ordinal)
                            .Select(pair => Embedded(pair.Key, pair.Value))
                    }
                }
            });
        }

        private const string CandidateProvenanceInventoryPath =
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json";
        private const string CandidateProvenanceExportPath =
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";

        private static object Embedded(string path, byte[] payload)
            => new
            {
                path,
                sha256 = Sha256(payload),
                sizeBytes = payload.LongLength,
                @base64 = Convert.ToBase64String(payload)
            };

        private static string SnapshotDigest(
            IEnumerable<string> names,
            IReadOnlyDictionary<string, string> digests)
        {
            using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            foreach (string name in names)
            {
                hash.AppendData(Encoding.UTF8.GetBytes(name));
                hash.AppendData([0]);
                hash.AppendData(Encoding.ASCII.GetBytes(digests[name]));
                hash.AppendData([(byte)'\n']);
            }
            return Convert.ToHexStringLower(hash.GetHashAndReset());
        }

        private static string Sha256(byte[] payload)
            => Convert.ToHexStringLower(SHA256.HashData(payload));

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private static ReleaseBundlePromotionResult BuildPromotionResult()
        => new(
            Version: "run-candidate",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UtcNow,
            PromotedArtifactIds: [],
            DownloadsUrl: "https://chummer.run/downloads/",
            InstallDispatchUrls: [],
            DirectFileUrls: [],
            GenerationId: "candidate-generation",
            ActivationReceiptId: "candidate-activation",
            InventoryDigest: "sha256:" + new string('a', 64));

    private static ReleaseActivationIntent BuildActivationIntent(ReleaseBundlePromotionResult result)
    {
        byte[] pointer = "candidate-pointer"u8.ToArray();
        return new ReleaseActivationIntent(
            Operation: "promotion",
            PreviousGenerationId: null,
            PreviousPointerSha256: null,
            GenerationId: result.GenerationId!,
            ActivationReceiptId: result.ActivationReceiptId!,
            ReleaseVersion: result.Version,
            Channel: result.Channel,
            PublishedAt: result.PublishedAt,
            InventoryDigest: result.InventoryDigest!,
            PointerSha256: "sha256:" + Convert.ToHexStringLower(SHA256.HashData(pointer)),
            PreparedAtUtc: DateTimeOffset.UtcNow,
            PreviousPointerBase64: null,
            TargetPointerBase64: Convert.ToBase64String(pointer));
    }
}
