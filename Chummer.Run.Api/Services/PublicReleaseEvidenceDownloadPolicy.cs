using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Http.Features;

namespace Chummer.Run.Api.Services;

internal static class PublicReleaseEvidenceDownloadPolicy
{
    private const string WindowsPreviewProfile = "windows_unsigned_preview_v1";
    private const string WindowsReceipt = "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json";
    private const int MaximumReceiptBytes = 16 * 1024;

    // Inventory membership authenticates bytes; it never makes authority documents public.
    internal static bool IsPrivateAuthorityPath(string path)
    {
        string[] parts = path.Split('/');
        return parts.Any(part => part.Equals("release-evidence", StringComparison.OrdinalIgnoreCase))
            && parts[^1].ToUpperInvariant() is "CURRENT.JSON" or "SNAPSHOT.JSON" or "RELEASE_DECISION.JSON";
    }

    internal static bool RejectRequest(HttpRequest request)
    {
        string path = request.Path.Value ?? string.Empty;
        string raw = request.HttpContext.Features.Get<IHttpRequestFeature>()?.RawTarget ?? path;
        raw = raw.Split('?', 2)[0];
        if (!IsDownloadBytePath(path) && !IsDownloadBytePath(raw))
            return false;
        return UnsafePath(path) || UnsafePath(raw)
            || IsPrivateAuthorityPath(Uri.UnescapeDataString(path))
            || IsPrivateAuthorityPath(Uri.UnescapeDataString(raw));
    }

    private static bool IsDownloadBytePath(string path)
    {
        string[] parts = path.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 2 || !parts[0].Equals("downloads", StringComparison.OrdinalIgnoreCase))
            return false;
        string scope = parts[1];
        if (scope.Equals("g", StringComparison.OrdinalIgnoreCase))
        {
            if (parts.Length < 4) return false;
            scope = parts[3];
        }
        return scope.ToLowerInvariant() is "files" or "file" or "get" or "install"
            or "release-evidence" or "proof" or "startup-smoke";
    }

    private static bool UnsafePath(string path)
    {
        // Inspect the original target as well as ASP.NET's partially decoded Path.
        // Do not normalize a hostile path into an allowed artifact or authority lookup.
        foreach (string segment in path.Split('/').Skip(1))
        {
            string decoded = Uri.UnescapeDataString(segment);
            if (decoded is "." or ".."
                || decoded.Any(c => c is '/' or '\\' or '%' or '\0' || char.IsControl(c)))
                return true;
        }
        return false;
    }

    internal static IResult Serve(ReleaseShelfSnapshot snapshot, string path,
        PublicReleaseManifestService releases, HttpContext context)
    {
        if (IsPrivateAuthorityPath(path))
            return Results.NotFound();

        // Keep legacy public evidence behavior, except the permanently private authority names.
        if (snapshot.IsLegacy)
        {
            string? canonical = releases.LoadCanonicalManifestJson(snapshot);
            if (canonical is not null)
            {
                try
                {
                    using JsonDocument manifest = JsonDocument.Parse(canonical);
                    if (Text(manifest.RootElement, "publicationProfile") == WindowsPreviewProfile)
                        return Results.NotFound();
                }
                catch (JsonException) { return Results.NotFound(); }
            }
            string? legacyPath = releases.ResolveReleaseEvidenceFilePath(snapshot,
                path["release-evidence/".Length..]);
            return legacyPath is null ? Results.NotFound()
                : Results.File(legacyPath, "application/json; charset=utf-8");
        }

        byte[]? manifestBytes = releases.LoadGenerationCanonicalManifestBytes(snapshot);
        if (manifestBytes is null)
            return Results.NotFound();
        try
        {
            using JsonDocument manifest = JsonDocument.Parse(manifestBytes);
            if (Text(manifest.RootElement, "publicationProfile") == WindowsPreviewProfile
                || string.Equals(path, WindowsReceipt, StringComparison.Ordinal))
            {
                // This profile publishes exactly the selected native startup receipt, never
                // generic proof, raw native output, or any release-evidence/internal metadata.
                if (!string.Equals(path, WindowsReceipt, StringComparison.Ordinal))
                    return Results.NotFound();
                byte[]? receipt = snapshot.ReadVerifiedFileBytes(path, MaximumReceiptBytes);
                if (receipt is null)
                    return Results.NotFound();
                bool envelopeFree = PublicReleaseTruthProjectionMiddleware.HasEnvelopeFreeEvidenceSnapshot(context, snapshot);
                var projection = PublicReleaseTruthProjectionMiddleware.TryGet(context);
                bool scopedAuthority = PublicReleaseTruthProjectionMiddleware.TryGetAuthoritySnapshotSha256(context)
                        is { Length: 64 }
                    && projection is { ReviewRequiredPublicByteHandoffsAllowed: true }
                    && projection.ManifestSha256 == snapshot.CanonicalManifestSha256;
                if ((envelopeFree || scopedAuthority)
                    && IsStartupOnlyPreviewGeneration(snapshot, manifest.RootElement))
                {
                    if (!IsSafeStartupOnlyWindowsReceipt(receipt, manifest.RootElement))
                        return Results.NotFound();
                    JsonElement artifact = manifest.RootElement.GetProperty("artifacts")[0];
                    using ReleaseShelfVerifiedFile? installer = snapshot.OpenVerifiedFile(
                        $"files/{Text(artifact, "fileName")}");
                    if (installer is null || installer.ExpectedSha256 != Text(artifact, "sha256")
                        || installer.SizeBytes != artifact.GetProperty("sizeBytes").GetInt64())
                        return Results.NotFound();
                    context.Response.Headers["X-Chummer-Release-Evidence-Scope"] =
                        scopedAuthority ? "scope-approved-windows-startup-only"
                            : "non-authoritative-windows-startup-only";
                    return Results.Bytes(receipt, "application/json; charset=utf-8");
                }
                // Bootstrap artifacts retain their packaging contract. Missing,
                // partial or unsupported authority never selects either branch.
                if (PublicReleaseTruthProjectionMiddleware.TryGetAuthoritySnapshotSha256(context)
                        is not { Length: 64 }
                    || !IsSafeWindowsReceipt(receipt, manifest.RootElement))
                    return Results.NotFound();
                return Results.Bytes(receipt, "application/json; charset=utf-8");
            }
        }
        catch (JsonException)
        {
            return Results.NotFound();
        }

        // Other established public proof scopes retain inventory/digest verification.
        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile(path);
        return verified is null ? Results.NotFound()
            : Results.Stream(verified.Stream, "application/json; charset=utf-8");
    }

    private static readonly string[] StartupOnlyReceiptFields =
    [
        "status", "headId", "version", "releaseVersion", "channelId", "platform", "arch", "rid",
        "readyCheckpoint", "hostClass", "artifactDigest", "operatingSystem", "recordedAtUtc",
        "executionEnvironment", "verificationScope", "nativeHostEvidence", "artifactSha256",
        "artifactId", "artifactFileName", "fileName", "artifactRelativePath"
    ];

    private static readonly HashSet<string> PackagingAuthorityFields = new(StringComparer.OrdinalIgnoreCase)
    {
        "installerMode", "installer_mode", "artifactInstallMode", "artifact_install_mode",
        "bootstrapInstallerMode", "bootstrap_installer_mode",
        "payloadAcquisitionMode", "payload_acquisition_mode",
        "payloadFileName", "payload_file_name", "payloadSha256", "payload_sha256",
        "payloadSizeBytes", "payload_size_bytes", "payloadDownloadUrl", "payload_download_url",
        "payloadMetadataFileName", "payload_metadata_file_name",
        "bootstrapPayloadAcquisitionMode", "bootstrap_payload_acquisition_mode",
        "bootstrapPayloadFileName", "bootstrap_payload_file_name",
        "bootstrapPayloadSha256", "bootstrap_payload_sha256",
        "bootstrapPayloadSizeBytes", "bootstrap_payload_size_bytes",
        "bootstrapPayloadDownloadUrl", "bootstrap_payload_download_url"
    };

    private static bool IsStartupOnlyPreviewGeneration(ReleaseShelfSnapshot snapshot, JsonElement manifest)
    {
        if (snapshot.IsLegacy || !UniqueFields(manifest)
            || Text(manifest, "publicationProfile") != WindowsPreviewProfile
            || Text(manifest, "platformScope") != "windows_only"
            || Text(manifest, "status") != "published"
            || Text(manifest, "supportabilityState") != "review_required"
            || Text(manifest, "rolloutState") != "public_release_review_required"
            || Text(manifest, "channel") != "preview" || snapshot.Channel != "preview"
            || Text(manifest, "generationId") != snapshot.GenerationId
            || Text(manifest, "releaseVersion") != snapshot.ReleaseVersion
            || !OptionalTextMatches(manifest, "version", snapshot.ReleaseVersion)
            || !OptionalTextMatches(manifest, "channelId", snapshot.Channel)
            || !manifest.TryGetProperty("artifacts", out JsonElement artifacts)
            || artifacts.ValueKind != JsonValueKind.Array || artifacts.GetArrayLength() != 1)
            return false;
        JsonElement artifact = artifacts[0];
        string? fileName = Text(artifact, "fileName");
        if (!UniqueFields(artifact) || artifact.EnumerateObject().Any(p => PackagingAuthorityFields.Contains(p.Name))
            || !SafeLabel(fileName, allowSpaces: false) || fileName!.Contains("..", StringComparison.Ordinal)
            || !artifact.TryGetProperty("sizeBytes", out JsonElement size)
            || size.ValueKind != JsonValueKind.Number || !size.TryGetInt64(out long sizeBytes) || sizeBytes <= 0
            || !snapshot.Inventory.TryGetValue($"files/{fileName}", out ReleaseShelfInventoryEntry? entry))
            return false;
        return entry.Sha256 == Text(artifact, "sha256") && entry.SizeBytes == sizeBytes;
    }

    // This validates the public shape only; serving additionally requires the
    // trusted envelope-free snapshot or exact scope-bound authority, manifest
    // scope and verified inventory bytes. It never proves bootstrap behavior.
    internal static bool IsSafeStartupOnlyWindowsReceipt(byte[] bytes, JsonElement manifest)
    {
        using JsonDocument document = JsonDocument.Parse(bytes);
        JsonElement receipt = document.RootElement;
        if (!ExactFields(receipt, StartupOnlyReceiptFields)
            || !UniqueFields(manifest)
            || !manifest.TryGetProperty("artifacts", out JsonElement artifacts)
            || artifacts.ValueKind != JsonValueKind.Array || artifacts.GetArrayLength() != 1)
            return false;
        JsonElement artifact = artifacts[0];
        if (!UniqueFields(artifact) || Text(artifact, "artifactId") != "avalonia-win-x64-installer"
            || !OptionalTextMatches(artifact, "id", Text(artifact, "artifactId"))
            || !OptionalTextMatches(artifact, "version", Text(manifest, "releaseVersion"))
            || !OptionalTextMatches(artifact, "releaseVersion", Text(manifest, "releaseVersion"))
            || !OptionalTextMatches(artifact, "channel", Text(manifest, "channel"))
            || !OptionalTextMatches(artifact, "channelId", Text(manifest, "channel"))
            || !SafeLabel(Text(artifact, "fileName"), allowSpaces: false)
            || !SafeLabel(Text(manifest, "releaseVersion"), allowSpaces: false)
            || Text(manifest, "channel") != "preview"
            || Text(artifact, "head") != "avalonia" || Text(artifact, "platform") != "windows"
            || Text(artifact, "rid") != "win-x64" || Text(artifact, "arch") != "x64"
            || Text(artifact, "kind") != "installer" || Text(artifact, "installAccessClass") != "open_public"
            || Text(artifact, "sha256") is not { Length: 64 } digest
            || !digest.All(c => char.IsAsciiDigit(c) || c is >= 'a' and <= 'f')
            || Text(receipt, "status") != "pass"
            || Text(receipt, "headId") != Text(artifact, "head")
            || Text(receipt, "platform") != Text(artifact, "platform")
            || Text(receipt, "rid") != Text(artifact, "rid") || Text(receipt, "arch") != Text(artifact, "arch")
            || Text(receipt, "version") != Text(manifest, "releaseVersion")
            || Text(receipt, "releaseVersion") != Text(manifest, "releaseVersion")
            || Text(receipt, "channelId") != Text(manifest, "channel")
            || Text(receipt, "artifactId") != Text(artifact, "artifactId")
            || Text(receipt, "artifactFileName") != Text(artifact, "fileName")
            || Text(receipt, "fileName") != Text(artifact, "fileName")
            || Text(receipt, "artifactRelativePath") != $"files/{Text(artifact, "fileName")}"
            || Text(receipt, "artifactDigest") != $"sha256:{digest}"
            || Text(receipt, "artifactSha256") != digest
            || Text(receipt, "readyCheckpoint") != "pre_ui_event_loop"
            || Text(receipt, "executionEnvironment") != "native_windows"
            || Text(receipt, "verificationScope") != "native_windows_startup")
            return false;
        string? host = Text(receipt, "hostClass"), os = Text(receipt, "operatingSystem");
        string? timestamp = Text(receipt, "recordedAtUtc");
        if (!SafeWindowsLabel(host) || !host!.Contains("win", StringComparison.OrdinalIgnoreCase)
            || !SafeWindowsLabel(os) || !os!.Contains("windows", StringComparison.OrdinalIgnoreCase)
            || timestamp is null || timestamp.Length > 64
            || !Regex.IsMatch(timestamp, @"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})\z")
            || !DateTimeOffset.TryParse(timestamp, CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
            return false;
        JsonElement native = receipt.GetProperty("nativeHostEvidence");
        if (!ExactFields(native,
            ["contractName", "status", "isNativeWindows", "hostPlatform", "hostKernel", "runner", "evidenceSource"]))
            return false;
        string? kernel = Text(native, "hostKernel");
        return Text(native, "contractName") == "chummer6-ui.native_windows_host_evidence"
            && Text(native, "status") == "verified" && native.GetProperty("isNativeWindows").ValueKind == JsonValueKind.True
            && Text(native, "hostPlatform") == "windows" && SafeWindowsLabel(kernel)
            && Regex.IsMatch(kernel!, @"\A(?:Windows_NT|(?:MINGW32|MINGW64|MSYS)_NT-[0-9.-]+)\z")
            && (Text(native, "runner"), Text(native, "evidenceSource")) is
                ("native-msys-direct", "host_kernel_and_native_direct_selection")
                or ("pwsh", "host_kernel_and_runner_selection");
    }

    private static bool SafeWindowsLabel(string? value)
        => SafeLabel(value, allowSpaces: true) && char.IsAsciiLetterOrDigit(value![0])
            && !value.Contains("wine", StringComparison.OrdinalIgnoreCase);

    private static bool UniqueFields(JsonElement value)
        => value.ValueKind == JsonValueKind.Object
            && value.EnumerateObject().Select(p => p.Name).Distinct(StringComparer.Ordinal).Count()
                == value.EnumerateObject().Count();

    private static bool OptionalTextMatches(JsonElement value, string property, string? expected)
        => !value.TryGetProperty(property, out _) || Text(value, property) == expected;

    private static readonly string[] ReceiptFields =
    [
        "status", "headId", "version", "releaseVersion", "channelId", "platform", "arch", "rid",
        "readyCheckpoint", "hostClass", "artifactDigest", "operatingSystem", "recordedAtUtc",
        "startedAtUtc", "completedAtUtc", "executionEnvironment", "verificationScope", "nativeHostEvidence",
        "artifactId", "artifactFileName", "artifactRelativePath", "artifactInstallMode",
        "bootstrapPayloadAcquisitionMode", "bootstrapPayloadFileName", "bootstrapPayloadSha256",
        "bootstrapPayloadSizeBytes"
    ];

    private static bool IsSafeWindowsReceipt(byte[] bytes, JsonElement manifest)
    {
        using JsonDocument document = JsonDocument.Parse(bytes);
        JsonElement receipt = document.RootElement;
        if (!ExactFields(receipt, ReceiptFields)
            || !manifest.TryGetProperty("artifacts", out JsonElement artifacts)
            || artifacts.ValueKind != JsonValueKind.Array || artifacts.GetArrayLength() != 1)
            return false;
        JsonElement artifact = artifacts[0];
        if (Text(artifact, "head") != "avalonia" || Text(artifact, "platform") != "windows"
            || Text(artifact, "rid") != "win-x64" || Text(artifact, "arch") != "x64"
            || Text(artifact, "kind") != "installer" || Text(artifact, "installAccessClass") != "open_public")
            return false;
        if (Text(receipt, "status") != "pass"
            || Text(receipt, "headId") != Text(artifact, "head")
            || Text(receipt, "platform") != Text(artifact, "platform")
            || Text(receipt, "rid") != Text(artifact, "rid")
            || Text(receipt, "arch") != Text(artifact, "arch")
            || Text(receipt, "version") != Text(manifest, "releaseVersion")
            || Text(receipt, "releaseVersion") != Text(manifest, "releaseVersion")
            || Text(receipt, "channelId") != Text(manifest, "channel")
            || Text(receipt, "artifactId") != Text(artifact, "artifactId")
            || Text(receipt, "artifactFileName") != Text(artifact, "fileName")
            || Text(receipt, "artifactRelativePath") != $"files/{Text(artifact, "fileName")}"
            || Text(receipt, "artifactDigest") != $"sha256:{Text(artifact, "sha256")}")
            return false;
        if (Text(receipt, "readyCheckpoint") != "pre_ui_event_loop"
            || Text(receipt, "executionEnvironment") != "native_windows"
            || Text(receipt, "verificationScope") != "native_windows_startup"
            || Text(receipt, "artifactInstallMode") != "nsis_bootstrap_installer"
            || Text(receipt, "bootstrapPayloadAcquisitionMode") != Text(artifact, "payloadAcquisitionMode")
            || Text(receipt, "bootstrapPayloadFileName") != Text(artifact, "payloadFileName")
            || Text(receipt, "bootstrapPayloadSha256") != Text(artifact, "payloadSha256")
            || !receipt.GetProperty("bootstrapPayloadSizeBytes").TryGetInt64(out long receiptSize)
            || !artifact.TryGetProperty("payloadSizeBytes", out JsonElement payloadSize)
            || !payloadSize.TryGetInt64(out long expectedSize) || receiptSize != expectedSize || receiptSize <= 0)
            return false;
        if (!SafeLabel(Text(receipt, "hostClass"), allowSpaces: false)
            || !SafeLabel(Text(receipt, "operatingSystem"), allowSpaces: true))
            return false;
        foreach (string timestamp in new[] { "recordedAtUtc", "startedAtUtc", "completedAtUtc" })
            if (!DateTimeOffset.TryParse(Text(receipt, timestamp), CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind, out _))
                return false;
        JsonElement native = receipt.GetProperty("nativeHostEvidence");
        return ExactFields(native,
                ["contractName", "status", "isNativeWindows", "hostPlatform", "hostKernel", "runner", "evidenceSource"])
            && Text(native, "contractName") == "chummer6-ui.native_windows_host_evidence"
            && Text(native, "status") == "verified"
            && native.GetProperty("isNativeWindows").ValueKind == JsonValueKind.True
            && Text(native, "hostPlatform") == "windows" && Text(native, "hostKernel") == "Windows_NT"
            && Text(native, "runner") == "native-msys-direct"
            && Text(native, "evidenceSource") == "host_kernel_and_native_direct_selection";
    }

    private static bool ExactFields(JsonElement value, string[] fields)
        => value.ValueKind == JsonValueKind.Object
            && value.EnumerateObject().Count() == fields.Length
            && value.EnumerateObject().Select(p => p.Name).ToHashSet(StringComparer.Ordinal).SetEquals(fields);

    private static bool SafeLabel(string? value, bool allowSpaces)
        => value is { Length: > 0 and <= 128 }
            && value.All(c => char.IsAsciiLetterOrDigit(c) || c is '.' or '_' or '-'
                || (allowSpaces && c == ' '));

    private static string? Text(JsonElement value, string property)
        => value.ValueKind == JsonValueKind.Object && value.TryGetProperty(property, out JsonElement item)
            && item.ValueKind == JsonValueKind.String ? item.GetString() : null;
}
