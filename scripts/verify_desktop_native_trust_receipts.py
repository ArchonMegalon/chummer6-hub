#!/usr/bin/env python3
from __future__ import annotations

import json
import html
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path


PACKAGE_ID = "next90-m102-hub-desktop-native-trust"
LANDED_COMMIT = "160af58f"
FRONTIER_ID = 2897065929
CURRENT_LOCAL_PROOF_FLOOR_COMMIT = "47a831ba"
CURRENT_LOCAL_PROOF_FLOOR_SUBJECT = "fix(hub): harden claimed install continuation actions"

REQUIRED_SOURCE_MARKERS = {
    Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"): [
        '[HttpPost("continuation")]',
        "ResolveInstallationForGrant(request.InstallationId, request.AccessToken)",
        "DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false)",
        "FallbackPosture: continuation?.FallbackPosture",
        "BuildNativeNextSafeAction(updateAvailable, leadSupportCase, continuation)",
        "NativePrimaryActionHref: BuildNativeContinuationPrimaryActionHref(updateAvailable, leadSupportCase)",
        "BuildNativeContinuationPrimaryActionHref(",
        "BuildNativeSupportContinuationCaseActionHref(leadSupportCase)",
        "ResolveSupportContinuationCases(",
        "CurrentReleaseVersion: manifest.Version",
        "CurrentReleaseChannel: manifest.Channel",
        "CurrentArtifactId: releaseArtifact?.Id",
        "Update this linked install from {installation.Channel} {installation.Version} to {manifest.Channel} {manifest.Version}, then refresh the grant-bound support follow-through from the app.",
        "applicationVersion: installation.Version",
        "releaseChannel: installation.Channel",
        "MatchesClaimedInstallTruth(supportCase, installation)",
        "MatchesClaimedInstallTruthWhenPresent(supportCase, installation)",
        "HasSupportCaseInstallTruth(supportCase)",
        "HasInstallTruth(supportCase.ApplicationVersion, supportCase.ReleaseChannel)",
        "HasDeviceTruth(supportCase.HeadId, supportCase.Platform, supportCase.Arch)",
        "&& !string.IsNullOrWhiteSpace(platform)",
        "&& !string.IsNullOrWhiteSpace(arch)",
        "MatchesOptionalTruth(supportCase.ReleaseChannel, installation.Channel)",
        "MatchesOptionalInstallTruth(supportCase.ApplicationVersion, installation.Version",
        "MatchesOptionalDeviceTruth(supportCase.HeadId, installation.HeadId",
        "hasInstallSpecificContext && hasDeviceSpecificContext",
        "InstalledBuildReceiptId: receipt?.ReceiptId",
        "MatchesInstalledBuildReceiptTruth(item, installation, releaseArtifact)",
        "private static bool MatchesInstalledBuildReceiptTruth(",
        "if (!MatchesReceiptDeviceTruth(receipt, installation))",
        "string.Equals(receipt.Platform, installation.Platform",
        "string.Equals(receipt.Arch, installation.Arch",
        "SupportCases: supportCases",
        "installedBuildReceiptId: receipt?.ReceiptId",
        "DesktopInstallRail.BuildAccountSupportHref(",
        'NativeUpdateHref: "/api/v1/install-linking/continuation/update"',
        'NativeSupportHref: "/api/v1/install-linking/continuation/support"',
        'NativeRollbackHref: "/api/v1/install-linking/continuation/rollback"',
        "NativeRecoveryHref: NativeRecoveryHref",
        "RecoveryAction: BuildNativeRecoveryAction(installation, continuation)",
        "private static string BuildNativeRecoveryAction(",
        "claim-code and account browser links remain fallback context only.",
        "BuildNativeSupportNextSafeAction(item, updateAvailable)",
        "BuildNativeSupportNextSafeAction(presented, updateAvailable)",
        "private static string BuildNativeSupportNextSafeAction(SupportCasePresentationViewModel item, bool updateAvailable)",
        "Continue on the grant-bound native update planner for this claimed install",
        "Stay on the grant-bound desktop continuation rail for this claimed install",
        "account, downloads, and public support browser links are human fallback only.",
        "BuildNativeSupportCaseActionHref(item)",
        "if (!string.Equals(supportCase.Kind, SupportCaseKinds.InstallHelp, StringComparison.OrdinalIgnoreCase))",
        "item.ReporterActionNeeded",
        "if (item.NeedsInstallUpdate)",
        "if (item.FixReadyOnLinkedInstall)",
        "IsBrowserRailHref(item.PrimaryActionHref)",
        "NormalizeNativeInstallRailHref(item.PrimaryActionHref)",
        "if (trimmed.StartsWith(\"//\", StringComparison.Ordinal))",
        "!trimmed.StartsWith(\"/\", StringComparison.Ordinal)",
        "trimmed.Contains('\\\\')",
        "ContainsEncodedPathSeparator(trimmed)",
        "private static bool ContainsEncodedPathSeparator(string href)",
        "href.Contains(\"%2f\", StringComparison.OrdinalIgnoreCase)",
        "href.Contains(\"%5c\", StringComparison.OrdinalIgnoreCase)",
        "return !primaryActionIsBrowserRail && nativeActionHref is not null",
        "Uri.TryCreate(trimmed, UriKind.Absolute, out _)",
        "Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? parsed)",
        "for (int index = 0; index < 4; index++)",
        "parsed.AbsolutePath",
        "NormalizeBrowserRailPath(trimmed)",
        "DecodeBrowserRailPath(path)",
        "Uri.UnescapeDataString(decoded)",
        "NormalizeBrowserRailSeparators(path)",
        "path.Replace('\\\\', '/')",
        "NormalizeLeadingBrowserRailSlashes(path)",
        "trimmed.StartsWith(\"//\", StringComparison.Ordinal)",
        "path.IndexOfAny(['?', '#'])",
        "path.StartsWith(\"/\", StringComparison.Ordinal)",
        "path.Equals(\"/account\", StringComparison.OrdinalIgnoreCase)",
        'path.StartsWith("/account/", StringComparison.OrdinalIgnoreCase)',
        'path.StartsWith("/contact", StringComparison.OrdinalIgnoreCase)',
        'path.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase)',
        '[HttpPost("continuation/support")]',
        "SubmitClaimedInstallSupport(",
        "DownloadReceiptDto? receipt = ResolveLatestReceipt(installSummary, installation, releaseArtifact);",
        "BuildNativeInstallSupportRequest(request, installation, receipt, manifest, releaseArtifact, continuation, updateAvailable)",
        "AppendInstalledBuildReceiptDetail(detail, installedBuildReceiptId)",
        "Installed build receipt: {installedBuildReceiptId}",
        "AppendAuthoritativeNativeInstallTruthDetail(detail, installation)",
        "Authoritative claimed install: {installation.InstallationId}; build {installation.Channel} {installation.Version}; device",
        "AppendNativeReleaseRecoveryTruthDetail(detail, manifest, releaseArtifact, continuation, updateAvailable)",
        "Native release recovery truth: current {manifest.Channel} {manifest.Version}; artifact",
        "rollback stays on the previous installed copy; fallback {fallbackPosture}",
        "AppendNativeRequestedActionDetail(detail, request.RequestedActionHref)",
        "private static string AppendNativeRequestedActionDetail(string detail, string? requestedActionHref)",
        "Desktop requested action ({posture}): {safeHref}",
        "RedactNativeRequestedActionHref(trimmed)",
        "private static string RedactNativeRequestedActionHref(string href)",
        "string sanitizedQuery = SanitizeInstallLinkSecretQueryComponent(",
        "string sanitizedFragment = SanitizeInstallLinkSecretQueryComponent(",
        'prefix: "#"',
        "if (!queryRedacted && !fragmentRedacted)",
        "private static string SanitizeInstallLinkSecretQueryComponent(string component, string prefix, out bool redacted)",
        'sanitizedQuery[item.Key] = "[redacted-install-link-secret]";',
        "advisory browser or external action",
        "AppendNativeRouteReceiptDetail(detail)",
        "private static string AppendNativeRouteReceiptDetail(string detail)",
        "Native route receipt: support {NativeSupportHref}; update {NativeUpdateHref}; rollback {NativeRollbackHref}; recovery {NativeRecoveryHref}; account, downloads, and public support links are human fallback only.",
        "AppendNativeContinuationContextDetail(detail)",
        "browser callback, claim-code, or public form identifiers in the desktop payload are advisory only.",
        "Source: SupportCaseSourceKinds.DesktopFeedback",
        "NativeSupportHref: \"/api/v1/install-linking/continuation/support\"",
        "NativeContinuationHref: \"/api/v1/install-linking/continuation\"",
        "NativeRollbackHref: \"/api/v1/install-linking/continuation/rollback\"",
        "NativeRecoveryHref: NativeRecoveryHref",
        "PrimaryActionHref: BuildNativeSupportCaseActionHref(presented)",
        "CurrentReleaseVersion: manifest.Version",
        "FallbackPosture: continuation?.FallbackPosture",
        "UpdateAvailable: updateAvailable",
        "UpdateAction: updateAvailable",
        "NativeUpdateHref: \"/api/v1/install-linking/continuation/update\"",
        "RollbackAction: \"If support, update, or setup fails, keep the previous installed copy and return to this claimed install continuation rail.\"",
        "RecoveryAction: BuildNativeRecoveryAction(installation, continuation)",
        '[HttpPost("continuation/update")]',
        "PlanClaimedInstallUpdate(",
        "DesktopInstallNativeUpdateResponse",
        "BuildNativeUpdatePlan(installation, manifest, releaseArtifact, receipt, updateAvailable)",
        "NativePrimaryActionHref: NativeUpdateHref",
        "then refresh this grant-bound update planner from the app.",
        "Update {deviceLabel} from {installation.Channel} {installation.Version}",
        "via {artifactLabel}, then refresh this grant-bound continuation rail before support verification.",
        '[HttpPost("continuation/rollback")]',
        "PlanClaimedInstallRollback(",
        "DesktopInstallNativeRollbackResponse",
        "BuildNativeRollbackPlan(installation, receipt)",
        "NativePrimaryActionHref: NativeRollbackHref",
        "NativeUpdateHref: \"/api/v1/install-linking/continuation/update\"",
        "NativeContinuationHref: \"/api/v1/install-linking/continuation\"",
        "NativeSupportHref: \"/api/v1/install-linking/continuation/support\"",
        "NativeRecoveryHref: NativeRecoveryHref",
        "Keep or restore {installation.Channel} {installation.Version}",
        "installed build receipt {receipt.ReceiptId}",
        "NormalizeCallbackUri(installLinkCallbackUri)",
        "string.Equals(parsed.Scheme, \"chummer\", StringComparison.OrdinalIgnoreCase)",
        "string.Equals(parsed.Host, \"install-link\", StringComparison.OrdinalIgnoreCase)",
        "IsAppLocalCallbackHost(parsed.Host)",
        "IsAppLocalInstallLinkCallbackPath(parsed.AbsolutePath)",
        "AppLocalInstallLinkCallbackPath = \"/install-link/callback\"",
        "System.Net.IPAddress.IsLoopback(address)",
        "string.Equals(host, \"localhost\", StringComparison.OrdinalIgnoreCase)",
        "InstallLinkCallbackReservedQueryKeys",
        '"artifactId"',
        '"accessToken"',
        '"callbackCode"',
        '"channelId"',
        '"claimCode"',
        '"claimTicketId"',
        '"grantId"',
        '"installedBuildReceiptId"',
        '"receiptId"',
        '"platformId"',
        '"ticketId"',
        '"version"',
        "StripReservedInstallLinkCallbackQuery(callbackUri)",
        "QueryHelpers.ParseQuery(parsed.Query)",
        "InstallLinkCallbackReservedQueryKeys.Contains(item.Key)",
        '["installLinkMode"] = "browser_callback"',
        "[\"installLinkTransport\"] = \"grant_callback\"",
    ],
    Path("Chummer.Run.Api/Services/DesktopInstallRail.cs"): [
        "Claim codes are a recovery fallback, not a browser redemption step.",
        "NormalizeSupportPrefill(applicationVersion) ?? manifest.Version",
        "desktop app update lane",
        "previous installed copy",
        "Support follow-through stays on the same install rail",
        "BuildAccountSupportHref(",
        "\"/account/support\"",
        "Keep the fix, update, rollback, and verification on this same linked install.",
    ],
    Path("Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs"): [
        "BuildInstallReadiness(",
        "FixReadyOnLinkedInstall",
        "NeedsInstallUpdate",
        "HasSupportCaseInstallTruth(supportCase)",
        "=> HasSupportCaseInstallTruth(supportCase);",
        "HasCompleteDeviceTruth(",
        "Follow-up stays attached to the affected claimed install.",
        "Devices & access only when you need to relink or reclaim that copy.",
    ],
    Path("Chummer.Run.Api/Controllers/PublicLandingController.cs"): [
        '"/downloads/install/{artifactId}/continue.json"',
        "DesktopInstallRail.BuildSupportHref(",
        "DesktopInstallRail.BuildContinuationReceipt(",
        "ResolveSupportIntakeRailFromQuery()",
    ],
    Path("Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml"): [
        "Automatic account linking is the default path. Use claim-code fallback only when Chummer explicitly says it is in recovery mode.",
        "Support follow-through stays on the same install rail",
    ],
    Path("Chummer.Run.Api/Views/Accounts/Account.cshtml"): [
        "The next safe action is still inside Chummer on the already-downloaded device.",
        "Only use the recovery code if that copy explicitly enters recovery mode.",
        "Claim, update, rollback, recovery, and support stay on this same account rail once the install is linked.",
        "Continue claim, update, rollback, recovery, and support follow-through from the claimed desktop install first.",
        "Use Devices & access only to relink or reclaim that copy, and keep browser routes as fallback instead of the default ritual.",
    ],
    Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"): [
        "ContinueClaimedInstall(",
        "response.FallbackPosture.Contains(\"Claim codes are a recovery fallback\"",
        "UpdateAvailable",
        "NeedsInstallUpdate",
        "response.SupportCases[0].InstalledBuildReceiptId",
        "Continuation should not attach a newer receipt from another desktop platform.",
        "Continuation should not attach an artifact-id receipt unless installed build truth matches.",
        "receipt-other-platform",
        "receipt-same-artifact-newer-version",
        "Support continuation should prefill the affected installed build.",
        "Support continuation should prefill the affected installed-build receipt.",
        "Claimed desktop continuation should keep support follow-through inside Account > Support.",
        "Claimed desktop continuation should not fall back to the public contact browser ritual.",
        "Claimed desktop continuation should expose a grant-bound native support intake instead of requiring a browser support ritual.",
        "Native support continuation should create a tracked support case without a browser form.",
        "Native support continuation should be sourced from the desktop app, not the public web form.",
        "Native support continuation should return the app to the grant-bound continuation rail.",
        "Native support continuation should keep follow-up detail on the grant-bound native support endpoint.",
        "Native support continuation should not make the account support route the desktop app's follow-up action.",
        "Native support continuation should echo the installed-build receipt truth back to the desktop app.",
        "Native support case should keep installed-build receipt truth in the tracked case detail.",
        "Native support case should record the grant-bound installed build and device tuple as authoritative detail.",
        "Native support case should persist current release, update, rollback, and artifact truth for support follow-through.",
        "Native support case should persist fallback posture beside the filed support detail.",
        "Native support case should mark desktop-supplied browser action hints as advisory support detail.",
        "Native support case should append canonical installed-build receipt truth even when the desktop payload already had a stale receipt label.",
        "Native support case should keep authoritative grant-bound install truth beside stale desktop payload labels.",
        "Native support case should append canonical release recovery truth beside stale desktop payload labels.",
        "Native support case should mark browser callback and claim-code payload identifiers as advisory.",
        "Native support case should keep stale callback or claim-code payload identifiers advisory.",
        "Native support case should redact reserved install-link query secrets from the desktop requested action.",
        "Native support case should not persist stale access tokens from desktop requested-action hints.",
        "Native support case should not persist stale grant ids from desktop requested-action hints.",
        "Native support case should not persist stale claim codes from desktop requested-action hints.",
        "Native support case should not persist stale receipt ids from desktop requested-action hints.",
        "Native support case should not persist stale installed-build receipt ids from desktop requested-action hints.",
        "Native support case should not persist stale install identity from desktop requested-action hints.",
        "Native support continuation should keep current release version truth available after filing support.",
        "Native support continuation should keep fallback posture available after filing support.",
        "Native support continuation should tell the app whether the claimed install still needs an update.",
        "Native support continuation should keep update instructions on the claimed install rail after filing support.",
        "Native support continuation should keep update on the grant-bound native update planner after filing support.",
        "Native support continuation should not send update through the downloads browser rail after filing support.",
        "Native support continuation should keep rollback on the previous installed copy after filing support.",
        "Native support continuation should keep rollback on the grant-bound native rollback planner after filing support.",
        "Native support continuation should keep recovery on the grant-bound continuation rail after filing support.",
        "Native support continuation should describe recovery without opening a browser ritual.",
        "Native support continuation should not send rollback through the account browser rail after filing support.",
        "Native support continuation should not send rollback through the downloads browser rail after filing support.",
        "Native support continuation should not send rollback through the public support browser rail after filing support.",
        "Native support action sanitizer should fail closed when support presentation returns an unexpected external action.",
        "Native support action sanitizer should fail closed instead of preserving absolute native-looking actions.",
        "Native support action sanitizer should fail closed instead of preserving scheme-relative native-looking actions.",
        "Native support action sanitizer should fail closed instead of preserving repeated-slash native-looking actions.",
        "Native support action sanitizer should fail closed instead of preserving bare relative native-looking actions.",
        "Native support action sanitizer should fail closed instead of preserving encoded native-looking actions.",
        "Native support action sanitizer should fail closed instead of preserving Windows-style native-looking actions.",
        "Native support action sanitizer should fail closed instead of handing the desktop app to a non-http action.",
        "Native support action sanitizer should preserve trusted absolute Hub-native update actions.",
        "Native support action sanitizer should preserve trusted app-local native support actions.",
        "Native support action sanitizer should preserve grant-bound native update planner actions.",
        "Native support case should redact reserved fragment secrets from the desktop requested action.",
        "Native support case should preserve app-local listener query state while redacting fragment-carried install-link secrets.",
        "Invalid native support continuation grants should fail closed.",
        "App-local callback redirects should strip stale browser-provided callback codes.",
        "App-local callback redirects should strip stale browser callback-code aliases.",
        "App-local callback redirects should strip stale browser-provided grant tokens.",
        "App-local callback redirects should strip stale browser-provided grant ids.",
        "App-local callback redirects should strip stale browser-provided claim codes.",
        "App-local callback redirects should strip stale browser-provided claim ticket ids.",
        "App-local callback redirects should strip stale browser-provided ticket ids.",
        "App-local callback redirects should strip stale browser-provided receipt ids.",
        "App-local callback redirects should strip stale browser-provided installed-build receipt ids.",
        "App-local callback redirects should strip stale browser-provided install identity.",
        "App-local callback redirects should strip stale browser-provided artifact identity.",
        "App-local callback redirects should strip stale browser-provided channel identity.",
        "App-local callback redirects should strip stale browser-provided version identity.",
        "App-local callback redirects should strip stale browser-provided platform identity.",
        "App-local callback redirects should strip stale browser-only install-link mode hints.",
        "App-local callback redirects should strip stale browser-only transport hints.",
        "installLinkMode=browser_callback",
        "App-local callback redirects should append the desktop-native grant callback transport.",
        "Support continuation response should still carry current release version truth.",
        "Support follow-through should expose installed build version truth.",
        "Native support follow-through should describe update verification as a desktop-native action.",
        "Native support follow-through should not tell the desktop app to open Devices and access.",
        "Native support follow-through should not tell the desktop app to open downloads.",
        "Native support follow-through should route update-ready cases to the grant-bound native update planner.",
        "Native support follow-through should not send the desktop app through the account browser rail.",
        "Native support follow-through should not send the desktop app through the downloads browser rail.",
        "Native support follow-through should not send the desktop app through the public support browser rail.",
        "Case-level support follow-through should carry current release version truth.",
        "Case-level support follow-through should carry current release channel truth.",
        "Case-level support follow-through should carry current artifact truth.",
        "Case-level support follow-through should keep fallback posture beside the case.",
        "Case-level support follow-through should tell the app when the linked install needs an update.",
        "Case-level support follow-through should keep update instructions inside the native support rail.",
        "Case-level support follow-through should keep rollback on the previous installed copy.",
        "Case-level support follow-through should return to the grant-bound continuation rail.",
        "Case-level support follow-through should keep support on the grant-bound native endpoint.",
        "Case-level support follow-through should keep update on the grant-bound native planner.",
        "Case-level support follow-through should keep rollback on the grant-bound native planner.",
        "Case-level support follow-through should keep recovery on the grant-bound continuation rail.",
        "Case-level support follow-through should describe recovery without a browser ritual.",
        "Case-level support follow-through should not send update through the downloads browser rail.",
        "Case-level support follow-through should not send support through the public support browser rail.",
        "Case-level support follow-through should not send rollback through the account browser rail.",
        "Native support action sanitizer should treat bare relative account support URLs as browser rails.",
        "Native support action sanitizer should treat bare relative download URLs as browser rails.",
        "Native support action sanitizer should treat bare relative public support URLs as browser rails.",
        "Native support action sanitizer should treat scheme-relative account support URLs as browser rails.",
        "Native support action sanitizer should treat repeated-slash download URLs as browser rails.",
        "Native support action sanitizer should treat encoded account support URLs as browser rails.",
        "Native support action sanitizer should treat double-encoded download URLs as browser rails.",
        "Native support action sanitizer should treat triple-encoded public support URLs as browser rails.",
        "Native support action sanitizer should treat Windows-style account support paths as browser rails.",
        "Native support action sanitizer should treat encoded Windows-style download paths as browser rails.",
        "Native support action sanitizer should keep grant-bound API continuation URLs native.",
        "Claimed desktop continuation should expose a grant-bound native rollback planner instead of requiring a browser rollback ritual.",
        "Claimed desktop continuation should keep recovery on the grant-bound continuation rail instead of a browser claim-code ritual.",
        "Claimed desktop continuation should describe recovery as app-native continuation.",
        "Claimed desktop continuation should expose a grant-bound native update planner instead of requiring a browser update ritual.",
        "Claimed desktop continuation should not send update through the downloads browser rail.",
        "Claimed desktop continuation should not send rollback through the account browser rail.",
        "Claimed desktop continuation should not send rollback through the downloads browser rail.",
        "Claimed desktop continuation should not send rollback through the public support browser rail.",
        "Native support continuation should keep update on the grant-bound native update planner after filing support.",
        "Native support continuation should not send the desktop app through the account browser rail for the immediate follow-up action.",
        "Native support continuation should not send the desktop app through the downloads browser rail for the immediate follow-up action.",
        "Native support continuation should not send the desktop app through the public support browser rail for the immediate follow-up action.",
        "New native support cases should tell the desktop app to stay on the grant-bound continuation rail.",
        "New native support cases should not tell the desktop app to open Devices and access.",
        "New native support cases should not tell the desktop app to open downloads.",
        "Native rollback continuation should accept a valid install grant.",
        "Native update continuation should accept a valid install grant.",
        "Native update should cite the installed-build receipt rather than a newer or wrong-platform receipt.",
        "Native update should tell the app the target release without opening downloads.",
        "Native update should keep update follow-through on the grant-bound planner.",
        "Native update should expose the grant-bound update planner as the primary action.",
        "Native update primary action should not send the desktop app through the downloads browser rail.",
        "Native update should return the app to the grant-bound continuation rail.",
        "Native update should keep support follow-up on the grant-bound native support endpoint.",
        "Native update should keep rollback on the grant-bound native rollback planner.",
        "Native update should keep recovery on the grant-bound continuation rail.",
        "Native update should keep recovery app-native.",
        "Native update should not send the desktop app through the downloads browser rail.",
        "Invalid native update continuation grants should fail closed.",
        "Native rollback should cite the installed-build receipt rather than a newer or wrong-platform receipt.",
        "Native rollback should expose the grant-bound rollback planner as the primary action.",
        "Native rollback primary action should not send the desktop app through the downloads browser rail.",
        "Native rollback should return the app to the grant-bound continuation rail.",
        "Native rollback should keep support follow-up on the grant-bound native support endpoint.",
        "Native rollback should keep recovery on the grant-bound continuation rail.",
        "Native rollback should keep recovery app-native.",
        "Native rollback should not send the desktop app through the account browser rail.",
        "Native rollback should not send the desktop app through the downloads browser rail.",
        "Native rollback should not send the desktop app through the public support browser rail.",
        "Invalid native rollback continuation grants should fail closed.",
        "Support continuation should not attach unrelated install-help cases by reporter alone.",
        "Support continuation should reject contradictory install truth even when the case cites the claimed install id.",
        "Support continuation should reject contradictory device truth even when the case cites the claimed install id.",
        "Continuation should not attach non-install support kinds even when claimed install truth matches.",
        "Matching non-install desktop bug",
        "Account support readiness should not attach install-id-only help without installed build and device truth.",
        "Account support readiness should reject same-install support without complete desktop device truth.",
        "Account support readiness should reject platform-only support without complete desktop device truth.",
        "Head-only same install help",
        "Platform-only same install help",
        "Install id only legacy help",
        "Channel-only install help should not follow this device.",
        "Channel-only install help should not route reporter-ready support follow-through into Devices and access without installed build and device truth.",
        "Version-only install help should not follow this device.",
        "The continuation rail needs a claimed install id or device tuple before attaching support follow-through.",
        "DateTimeOffset now = DateTimeOffset.UtcNow;",
        "Invalid desktop continuation grants should fail closed.",
    ],
    Path("Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs"): [
        "Browser_install_link_preserves_app_local_callback_targets",
        "http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof",
        "http://127.0.0.1:47761/browser-only/claim?state=desktop",
        "http://[::1]:47763/install-link/callback?state=desktop",
        "https://localhost:47762/account/access/install-link",
        "https://localhost:47762/install-link/callback",
        "The controller should emit a valid app-local callback URI.",
        'Assert.Contains("state=desktop", redirect.Url, StringComparison.Ordinal);',
        'Assert.Contains("nonce=callback-proof", redirect.Url, StringComparison.Ordinal);',
        "installLinkTransport=grant_callback",
    ],
    Path("scripts/ai/verify.sh"): [
        "python3 scripts/verify_desktop_native_trust_receipts.py",
    ],
}


REQUIRED_PROOF_RECEIPTS = {
    "desktop_native_claim_and_recovery": {
        "package_id": "next90-m102-hub-desktop-native-trust",
        "milestone_id": 102,
        "frontier_id": FRONTIER_ID,
        "summary": (
            "Claim and recovery continuation now have installer/app-native receipts: guided setup is the default, "
            "claim codes are recovery fallback only, and the claimed desktop app can call the grant-bound "
            "continuation endpoint without a browser redemption ritual."
        ),
        "surfaces": [
            "desktop_native_claim_and_recovery",
            "install_claim_restore_continue",
            "claimed_install_continuation",
        ],
        "routes": [
            "/downloads/install/avalonia-linux-x64-installer/continue.json",
            "/api/v1/install-linking/continuation",
            "/account/access",
        ],
    },
    "support_followthrough:install_truth": {
        "package_id": "next90-m102-hub-desktop-native-trust",
        "milestone_id": 102,
        "frontier_id": FRONTIER_ID,
        "summary": (
            "Support follow-through carries installed build, current release, channel, head, platform, fallback, "
            "update, and rollback truth on the same install rail used by the desktop client."
        ),
        "surfaces": [
            "support_followthrough:install_truth",
            "support_case_install_readiness",
            "desktop_update_rollback_recovery",
        ],
        "routes": [
            "/api/v1/install-linking/continuation",
            "/api/v1/install-linking/continuation/support",
            "/account/support",
            "/contact",
        ],
    },
}

REQUIRED_TOP_LEVEL_PROOF_ROUTES = [
    "/downloads/install/avalonia-linux-x64-installer/continue.json",
    "/api/v1/install-linking/continuation",
    "/api/v1/install-linking/continuation/support",
    "/account/access",
    "/account/support",
    "/contact",
]

REQUIRED_TOP_LEVEL_JOURNEYS = [
    "install_claim_restore_continue",
]


NATIVE_INSTALL_LINKING_ROUTE_PREFIX = "/api/v1/install-linking/continuation"


REQUIRED_CANONICAL_QUEUE_MARKERS = [
    "title: Unify claim, install, update, and support recovery into one desktop-native flow",
    "task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
    f"package_id: {PACKAGE_ID}",
    f"frontier_id: {FRONTIER_ID}",
    "milestone_id: 102",
    "wave: W6",
    "repo: chummer6-hub",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    "completion_action: verify_closed_package_only",
    "do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
]

REQUIRED_CANONICAL_REGISTRY_MARKERS = [
    "id: 102.1",
    "owner: chummer6-hub",
    "title: Unify account, claim, install, and support-case recovery into one desktop-native continuation flow.",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    PACKAGE_ID,
    "desktop_native_claim_and_recovery",
    "support_followthrough:install_truth",
]

REQUIRED_CANONICAL_REGISTRY_LISTS = {
    "evidence": [
        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InstallLinkingController.cs exposes /api/v1/install-linking/continuation for grant-bound claimed desktop installs with current release, update, rollback, and support continuation truth.",
        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml make guided setup/app continuation the default and keep claim codes as recovery fallback only.",
        "/docker/chummercomplete/chummer6-hub/scripts/verify_desktop_native_trust_receipts.py fail-closes missing source markers and missing successor proof receipts for desktop_native_claim_and_recovery and support_followthrough:install_truth.",
        "/docker/chummercomplete/chummer6-hub/Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs covers app-local localhost and 127.0.0.1 install-link callbacks so claimed desktop users return to the app-local continuation listener instead of browser-only continuation.",
        "/docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json carries next90-m102-hub-desktop-native-trust proof receipts for /downloads/install/avalonia-linux-x64-installer/continue.json, /api/v1/install-linking/continuation, /account/access, /account/support, and /contact.",
        "/docker/chummercomplete/chummer6-hub commit e27f24c1 tightens desktop-native continuation fallback-posture proof so claimed installs return the same fallback posture used by download and support recovery.",
        "/docker/chummercomplete/chummer6-hub commit e578a519 tightens the completed M102 proof pin so future shards verify the closed package instead of repeating it.",
        "/docker/chummercomplete/chummer6-hub commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
        "/docker/chummercomplete/chummer6-hub commit 266d526b pins the M102 queue proof hardening commit so stale queue proof cannot keep the package green.",
        "/docker/chummercomplete/chummer6-hub commit 6ea510c8 pins the M102 telemetry guard proof evidence so future shards verify the latest closed-package guard.",
        "/docker/chummercomplete/chummer6-hub commit 7a825c73 pins the M102 desktop trust guard evidence into the verifier and unit guard.",
        "/docker/chummercomplete/chummer6-hub commit aff39474 pins the M102 desktop trust latest guard.",
        "/docker/chummercomplete/chummer6-hub commit 38d50742 pins the M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit b9404a4c pins the M102 desktop trust latest proof guard.",
        "/docker/chummercomplete/chummer6-hub commit e6ae11a7 pins the M102 desktop trust guard closure.",
        "/docker/chummercomplete/chummer6-hub commit 4c542b50 pins the latest M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer6-hub commit 02bed909 pins the M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer6-hub commit 2017cdfe requires the latest M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 24432002 tightens the current M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 4afd6c3e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit d99d080e pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b5b25e98 tightens M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit d7cb9d6e pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ec81b660 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b2d5cbfc tightens M102 generated proof hygiene.",
        "/docker/chummercomplete/chummer6-hub commit 5eac0f47 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 91514d42 pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit f7031d74 pins M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit f169b4a0 requires the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer6-hub commit b473e033 pins the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer6-hub commit 782fa007 requires the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 26817b22 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 6cf10549 pins M102 desktop trust 268 proof floor.",
        "/docker/chummercomplete/chummer6-hub commit de9653ee pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
        "/docker/chummercomplete/chummer6-hub commit 0337eeb5 pins the M102 active-run casing proof guard.",
        "/docker/chummercomplete/chummer6-hub commit ad21e50f pins the M102 active-run casing proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 51c46e74 pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ed3989d9 pins the M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 653b23f0 tightens M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 1a1c5615 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ed689925 pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 461e3709 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 171c2de0 tightens M102 blocked run-helper proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 73f1ee9a pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 74dff34c tightens M102 forbidden command evidence guard.",
        "/docker/chummercomplete/chummer6-hub commit aea02326 pins the M102 forbidden command proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 2330a11c pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 99a03a04 pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 0dca4b42 pins the M102 landed proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 2c351c92 pins M102 landed proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 575daa11 pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
        "/docker/chummercomplete/chummer6-hub commit 9454feb7 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer6-hub commit f1513793 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 7ddbc973 pins M102 current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 01800bd9 pins M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit c9bbf63c tightens M102 served proof shelf route guard.",
        "/docker/chummercomplete/chummer6-hub commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
        "/docker/chummercomplete/chummer6-hub commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
        "/docker/chummercomplete/chummer6-hub commit 4fa19f0c pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
        "/docker/chummercomplete/chummer6-hub commit 4ed1f541 pins the M102 supervisor proof guard floor so future shards verify the current completed-package guard.",
        "/docker/chummercomplete/chummer6-hub commit f3300fd9 pins the M102 supervisor proof guard into the verifier and unit guard.",
        "/docker/chummercomplete/chummer6-hub commit 06fa0634 pins the M102 local proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit f23b6dc4 records the M102 proof floor in the verifier.",
        "/docker/chummercomplete/chummer6-hub commit 7cf5461b pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit cae283e9 requires the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit e908400b pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 1870132d pins the latest M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 6b811ca2 pins the latest M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit b7107364 pins the M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit f49c64a9 pins the M102 current desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit 512f3569 pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ff9c3313 pins the M102 latest desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit de158f6b tightens M102 worker-context proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 8a542230 pins the M102 worker-context proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 74c3b75b pins the M102 worker-context proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 76b350fc tightens M102 materialized proof guard.",
        "/docker/chummercomplete/chummer6-hub commit d3b19c88 pins the M102 materialized proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 39af99da pins the M102 materialized proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 7d86f38e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit c0c4dca1 records the M102 desktop trust proof citation.",
        "/docker/chummercomplete/chummer6-hub commit 42a3d5a4 pins the M102 desktop trust citation floor.",
        "/docker/chummercomplete/chummer6-hub commit af567e58 pins the M102 desktop trust verifier floor.",
        "/docker/chummercomplete/chummer6-hub commit 2620a2f4 requires the M102 desktop trust verifier floor.",
        "/docker/chummercomplete/chummer6-hub commit 5917695a pins the M102 current verifier floor.",
        "/docker/chummercomplete/chummer6-hub commit 2ded9038 tightens M102 app-local callback proof so localhost and 127.0.0.1 install-link callbacks stay desktop-native.",
        "/docker/chummercomplete/chummer6-hub commit e7b5177b tightens M102 loopback callback proof so IPv6 app-local install-link callbacks stay desktop-native.",
        "/docker/chummercomplete/chummer6-hub commit d72386ee pins the M102 loopback callback proof floor.",
        "/docker/chummercomplete/chummer6-hub commit fee0655a tightens M102 app-local callback state proof so the desktop listener's state query survives grant callback continuation.",
        "/docker/chummercomplete/chummer6-hub commit 568b8358 tightens M102 app-local callback query-context proof.",
        "/docker/chummercomplete/chummer6-hub commit e0bcd91d pins the M102 callback query proof floor.",
        "/docker/chummercomplete/chummer6-hub commit aadffb5b pins the M102 callback query proof guard.",
        "/docker/chummercomplete/chummer6-hub commit a7a5ecea tightens M102 desktop trust callback proof.",
        "/docker/chummercomplete/chummer6-hub commit 4b9c6919 pins the M102 desktop trust callback proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ea697985 tightens M102 receipt route proof so receipt routes must be served by top-level proof_routes.",
        "/docker/chummercomplete/chummer6-hub commit e9c87a3f tightens M102 served proof parity so the public proof shelf cannot drift from canonical published proof.",
        "/docker/chummercomplete/chummer6-hub commit d3c74d38 tightens M102 queue mirror proof so Fleet and design-owned successor queue rows cannot drift apart.",
        "/docker/chummercomplete/chummer6-hub commit 6b5679de tightens M102 support continuation filtering so reporter-level install-help cases cannot attach to the wrong claimed desktop install.",
        "/docker/chummercomplete/chummer6-hub commit 39c0ae8d tightens M102 app-local callback path proof so claimed desktop callbacks cannot drift to arbitrary localhost browser routes.",
        "/docker/chummercomplete/chummer6-hub commit 8e90aac9 pins the M102 app-local callback path proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b27c5142 pins the M102 app-local proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit cd392a72 pins the M102 current proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 41d7ed57 pins the M102 current desktop trust floor.",
        "/docker/chummercomplete/chummer6-hub commit bd60fc5a tightens M102 active-run evidence path guard.",
        "/docker/chummercomplete/chummer6-hub commit 2791f798 tightens M102 support intake installed-build truth.",
        "/docker/chummercomplete/chummer6-hub commit 93e5075a tightens M102 current proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 894dbedd pins M102 current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 997337a6 pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit e24162d9 requires M102 desktop trust proof citation.",
        "/docker/chummercomplete/chummer6-hub commit bb8db39c tightens M102 support install matching.",
        "/docker/chummercomplete/chummer6-hub commit 1d6c686c tightens M102 duplicate proof citations.",
        "/docker/chummercomplete/chummer6-hub commit 18902a34 pins the M102 duplicate proof citation guard.",
        "/docker/chummercomplete/chummer6-hub commit 72fa2471 tightens M102 proof anchor scope so canonical closure evidence cannot cite existing files outside the package allowed paths.",
        "/docker/chummercomplete/chummer6-hub commit c791e657 tightens M102 install receipt matching so support continuation cannot attach a newer receipt from another desktop platform.",
        "/docker/chummercomplete/chummer6-hub commit 438861f0 pins the M102 receipt matching proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 4238a88a pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b8a03984 tightens M102 encoded active-run proof marker guard.",
        "/docker/chummercomplete/chummer6-hub commit 6961320a tightens M102 installed-build receipt truth.",
        "/docker/chummercomplete/chummer6-hub commit aceef790 pins the M102 installed-build receipt proof.",
        "/docker/chummercomplete/chummer6-hub commit 5f9621c3 tightens M102 encoded proof marker guard.",
        "/docker/chummercomplete/chummer6-hub commit 4e8eb4c1 pins the M102 encoded proof marker guard.",
        "/docker/chummercomplete/chummer6-hub commit 4bede125 tightens M102 closed queue proof guard.",
        "/docker/chummercomplete/chummer6-hub commit ebfaaf36 pins the M102 closed queue proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 38eb0769 pins M102 current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ed611d1a tightens M102 support install truth matching.",
        "/docker/chummercomplete/chummer6-hub commit d9d6c9a0 pins M102 support truth proof floor.",
        "/docker/chummercomplete/chummer6-hub commit a01d80ab pins M102 support truth proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit a766e82c pins M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit d9f59d4f pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit af6a480e proves the M102 native support route receipt.",
        "/docker/chummercomplete/chummer6-hub commit a7d27da6 guards the M102 proof package repo.",
        "/docker/chummercomplete/chummer6-hub commit 0bc0c858 tightens the M102 native support proof guard.",
        "/docker/chummercomplete/chummer6-hub commit c8ec0c6a tightens the M102 handoff proof guard.",
        "/docker/chummercomplete/chummer6-hub commit e08468e2 pins the M102 handoff proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 9e7d12ef guards M102 proof receipts against browser-only route closure.",
        "/docker/chummercomplete/chummer6-hub commit 554cd159 pins M102 native receipt proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 8e0a630e pins M102 current proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 47a831ba hardens claimed install continuation action sanitization so trusted native absolute actions survive while query and fragment install-link secrets are redacted from support continuation receipts.",
        "python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest tests/test_desktop_native_trust_receipts.py exit 0.",
        'dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification|InstallLinkingControllerBrowserCallbackTests" --no-restore exits 0 for net10.0 and net10.0-windows.',
    ],
}

REQUIRED_CANONICAL_QUEUE_LISTS = {
    "proof": [
        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InstallLinkingController.cs",
        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/DesktopInstallRail.cs",
        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs",
        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml",
        "/docker/chummercomplete/chummer6-hub/scripts/verify_desktop_native_trust_receipts.py",
        "/docker/chummercomplete/chummer6-hub/tests/test_desktop_native_trust_receipts.py",
        "/docker/chummercomplete/chummer6-hub/Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs",
        "/docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
        "/docker/chummercomplete/chummer6-hub commit e27f24c1 tightens desktop-native continuation fallback-posture proof.",
        "/docker/chummercomplete/chummer6-hub commit e578a519 tightens the completed M102 proof pin.",
        "/docker/chummercomplete/chummer6-hub commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
        "/docker/chummercomplete/chummer6-hub commit 266d526b pins the M102 queue proof hardening commit.",
        "/docker/chummercomplete/chummer6-hub commit 6ea510c8 pins the M102 telemetry guard proof evidence.",
        "/docker/chummercomplete/chummer6-hub commit 7a825c73 pins the M102 desktop trust guard evidence.",
        "/docker/chummercomplete/chummer6-hub commit aff39474 pins the M102 desktop trust latest guard.",
        "/docker/chummercomplete/chummer6-hub commit 38d50742 pins the M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit b9404a4c pins the M102 desktop trust latest proof guard.",
        "/docker/chummercomplete/chummer6-hub commit e6ae11a7 pins the M102 desktop trust guard closure.",
        "/docker/chummercomplete/chummer6-hub commit 4c542b50 pins the latest M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer6-hub commit 02bed909 pins the M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer6-hub commit 2017cdfe requires the latest M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 24432002 tightens the current M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 4afd6c3e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit d99d080e pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b5b25e98 tightens M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit d7cb9d6e pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ec81b660 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b2d5cbfc tightens M102 generated proof hygiene.",
        "/docker/chummercomplete/chummer6-hub commit 5eac0f47 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 91514d42 pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit f7031d74 pins M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit f169b4a0 requires the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer6-hub commit b473e033 pins the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer6-hub commit 782fa007 requires the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 26817b22 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 6cf10549 pins M102 desktop trust 268 proof floor.",
        "/docker/chummercomplete/chummer6-hub commit de9653ee pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
        "/docker/chummercomplete/chummer6-hub commit 0337eeb5 pins the M102 active-run casing proof guard.",
        "/docker/chummercomplete/chummer6-hub commit ad21e50f pins the M102 active-run casing proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 51c46e74 pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ed3989d9 pins the M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 653b23f0 tightens M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 1a1c5615 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ed689925 pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 461e3709 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 171c2de0 tightens M102 blocked run-helper proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 73f1ee9a pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 74dff34c tightens M102 forbidden command evidence guard.",
        "/docker/chummercomplete/chummer6-hub commit aea02326 pins the M102 forbidden command proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 2330a11c pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 99a03a04 pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 0dca4b42 pins the M102 landed proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 2c351c92 pins M102 landed proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 575daa11 pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
        "/docker/chummercomplete/chummer6-hub commit 9454feb7 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer6-hub commit f1513793 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 7ddbc973 pins M102 current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 01800bd9 pins M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit c9bbf63c tightens M102 served proof shelf route guard.",
        "/docker/chummercomplete/chummer6-hub commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
        "/docker/chummercomplete/chummer6-hub commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
        "/docker/chummercomplete/chummer6-hub commit 4fa19f0c pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
        "/docker/chummercomplete/chummer6-hub commit 4ed1f541 pins the M102 supervisor proof guard floor so future shards verify the current completed-package guard.",
        "/docker/chummercomplete/chummer6-hub commit f3300fd9 pins the M102 supervisor proof guard into the verifier and unit guard.",
        "/docker/chummercomplete/chummer6-hub commit 06fa0634 pins the M102 local proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit f23b6dc4 records the M102 proof floor in the verifier.",
        "/docker/chummercomplete/chummer6-hub commit 7cf5461b pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit cae283e9 requires the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit e908400b pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 1870132d pins the latest M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 6b811ca2 pins the latest M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit b7107364 pins the M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit f49c64a9 pins the M102 current desktop trust guard floor.",
        "/docker/chummercomplete/chummer6-hub commit 512f3569 pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ff9c3313 pins the M102 latest desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit de158f6b tightens M102 worker-context proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 8a542230 pins the M102 worker-context proof guard.",
        "/docker/chummercomplete/chummer6-hub commit 74c3b75b pins the M102 worker-context proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 76b350fc tightens M102 materialized proof guard.",
        "/docker/chummercomplete/chummer6-hub commit d3b19c88 pins the M102 materialized proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 39af99da pins the M102 materialized proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 7d86f38e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit c0c4dca1 records the M102 desktop trust proof citation.",
        "/docker/chummercomplete/chummer6-hub commit 42a3d5a4 pins the M102 desktop trust citation floor.",
        "/docker/chummercomplete/chummer6-hub commit af567e58 pins the M102 desktop trust verifier floor.",
        "/docker/chummercomplete/chummer6-hub commit 2620a2f4 requires the M102 desktop trust verifier floor.",
        "/docker/chummercomplete/chummer6-hub commit 5917695a pins the M102 current verifier floor.",
        "/docker/chummercomplete/chummer6-hub commit 2ded9038 tightens M102 app-local callback proof so localhost and 127.0.0.1 install-link callbacks stay desktop-native.",
        "/docker/chummercomplete/chummer6-hub commit e7b5177b tightens M102 loopback callback proof so IPv6 app-local install-link callbacks stay desktop-native.",
        "/docker/chummercomplete/chummer6-hub commit d72386ee pins the M102 loopback callback proof floor.",
        "/docker/chummercomplete/chummer6-hub commit fee0655a tightens M102 app-local callback state proof so the desktop listener's state query survives grant callback continuation.",
        "/docker/chummercomplete/chummer6-hub commit 568b8358 tightens M102 app-local callback query-context proof.",
        "/docker/chummercomplete/chummer6-hub commit e0bcd91d pins the M102 callback query proof floor.",
        "/docker/chummercomplete/chummer6-hub commit aadffb5b pins the M102 callback query proof guard.",
        "/docker/chummercomplete/chummer6-hub commit a7a5ecea tightens M102 desktop trust callback proof.",
        "/docker/chummercomplete/chummer6-hub commit 4b9c6919 pins the M102 desktop trust callback proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ea697985 tightens M102 receipt route proof so receipt routes must be served by top-level proof_routes.",
        "/docker/chummercomplete/chummer6-hub commit e9c87a3f tightens M102 served proof parity so the public proof shelf cannot drift from canonical published proof.",
        "/docker/chummercomplete/chummer6-hub commit d3c74d38 tightens M102 queue mirror proof so Fleet and design-owned successor queue rows cannot drift apart.",
        "/docker/chummercomplete/chummer6-hub commit 6b5679de tightens M102 support continuation filtering so reporter-level install-help cases cannot attach to the wrong claimed desktop install.",
        "/docker/chummercomplete/chummer6-hub commit 39c0ae8d tightens M102 app-local callback path proof so claimed desktop callbacks cannot drift to arbitrary localhost browser routes.",
        "/docker/chummercomplete/chummer6-hub commit 8e90aac9 pins the M102 app-local callback path proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b27c5142 pins the M102 app-local proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit cd392a72 pins the M102 current proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 41d7ed57 pins the M102 current desktop trust floor.",
        "/docker/chummercomplete/chummer6-hub commit bd60fc5a tightens M102 active-run evidence path guard.",
        "/docker/chummercomplete/chummer6-hub commit 2791f798 tightens M102 support intake installed-build truth.",
        "/docker/chummercomplete/chummer6-hub commit 93e5075a tightens M102 current proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 894dbedd pins M102 current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 997337a6 pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit e24162d9 requires M102 desktop trust proof citation.",
        "/docker/chummercomplete/chummer6-hub commit bb8db39c tightens M102 support install matching.",
        "/docker/chummercomplete/chummer6-hub commit 1d6c686c tightens M102 duplicate proof citations.",
        "/docker/chummercomplete/chummer6-hub commit 18902a34 pins the M102 duplicate proof citation guard.",
        "/docker/chummercomplete/chummer6-hub commit 72fa2471 tightens M102 proof anchor scope so canonical closure evidence cannot cite existing files outside the package allowed paths.",
        "/docker/chummercomplete/chummer6-hub commit c791e657 tightens M102 install receipt matching so support continuation cannot attach a newer receipt from another desktop platform.",
        "/docker/chummercomplete/chummer6-hub commit 438861f0 pins the M102 receipt matching proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 4238a88a pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer6-hub commit b8a03984 tightens M102 encoded active-run proof marker guard.",
        "/docker/chummercomplete/chummer6-hub commit 6961320a tightens M102 installed-build receipt truth.",
        "/docker/chummercomplete/chummer6-hub commit aceef790 pins the M102 installed-build receipt proof.",
        "/docker/chummercomplete/chummer6-hub commit 5f9621c3 tightens M102 encoded proof marker guard.",
        "/docker/chummercomplete/chummer6-hub commit 4e8eb4c1 pins the M102 encoded proof marker guard.",
        "/docker/chummercomplete/chummer6-hub commit 4bede125 tightens M102 closed queue proof guard.",
        "/docker/chummercomplete/chummer6-hub commit ebfaaf36 pins the M102 closed queue proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 38eb0769 pins M102 current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit ed611d1a tightens M102 support install truth matching.",
        "/docker/chummercomplete/chummer6-hub commit d9d6c9a0 pins M102 support truth proof floor.",
        "/docker/chummercomplete/chummer6-hub commit a01d80ab pins M102 support truth proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit a766e82c pins M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit d9f59d4f pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer6-hub commit af6a480e proves the M102 native support route receipt.",
        "/docker/chummercomplete/chummer6-hub commit a7d27da6 guards the M102 proof package repo.",
        "/docker/chummercomplete/chummer6-hub commit 0bc0c858 tightens the M102 native support proof guard.",
        "/docker/chummercomplete/chummer6-hub commit c8ec0c6a tightens the M102 handoff proof guard.",
        "/docker/chummercomplete/chummer6-hub commit e08468e2 pins the M102 handoff proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 9e7d12ef guards M102 proof receipts against browser-only route closure.",
        "/docker/chummercomplete/chummer6-hub commit 554cd159 pins M102 native receipt proof floor.",
        "/docker/chummercomplete/chummer6-hub commit 8e0a630e pins M102 current proof floor guard.",
        "/docker/chummercomplete/chummer6-hub commit 47a831ba hardens claimed install continuation action sanitization so trusted native absolute actions survive while query and fragment install-link secrets are redacted from support continuation receipts.",
        "python3 scripts/verify_desktop_native_trust_receipts.py",
        "python3 -m unittest tests/test_desktop_native_trust_receipts.py",
        'dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification|InstallLinkingControllerBrowserCallbackTests" --no-restore',
    ],
    "allowed_paths": [
        "Chummer.Run.Api",
        "scripts",
        "tests",
    ],
    "owned_surfaces": [
        "desktop_native_claim_and_recovery",
        "support_followthrough:install_truth",
    ],
}

ADJACENT_PROOF_ANCHOR_PREFIXES = [
    "Chummer.Tests",
    ".codex-studio/published",
]

FORBIDDEN_PROOF_MARKERS = [
    "/var/lib/codex-fleet",
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "active-run helper",
    "active-run helper command",
    "active-run helper commands",
    "operator telemetry",
    "supervisor status",
    "status query",
    "status_query_supported",
    "polling_disabled",
    "polling disabled",
    "task-local telemetry",
    "first_commands",
    "frontier_briefs",
    "current steering focus",
    "profile focus",
    "owner focus",
    "text focus",
    "assigned successor queue package",
    "execution rules inside this run",
    "remaining milestones",
    "remaining queue items",
    "critical path",
    "successor frontier detail",
    "shard runtime handoff",
    "Run id",
    "Selected account",
    "Selected model",
    "First output at",
    "Last output at",
    "Prompt path",
    "Recent stderr tail",
    "run_ooda_design_supervisor_until_quiet",
    "ooda_design_supervisor.py",
    "operator/OODA loop",
    "design_supervisor_ooda",
]
FORBIDDEN_PROOF_FIELD_PATTERNS = [
    ("eta", re.compile(r"(?im)^\s*eta\s*:\s*\S")),
]
FORBIDDEN_PROOF_MARKER_MATCHES = [
    (marker, marker.casefold())
    for marker in FORBIDDEN_PROOF_MARKERS
]
FORBIDDEN_PROOF_MARKER_NORMALIZED_MATCHES = [
    (marker, re.sub(r"[^a-z0-9]+", "", marker.casefold()))
    for marker in FORBIDDEN_PROOF_MARKERS
]

REQUIRED_PROOF_PACKAGE = {
    "package_id": PACKAGE_ID,
    "milestone_id": 102,
    "frontier_id": FRONTIER_ID,
    "repo": "chummer6-hub",
    "status": "complete",
    "landed_commit": LANDED_COMMIT,
    "title": "Unify claim, install, update, and support recovery into one desktop-native flow",
    "allowed_paths": REQUIRED_CANONICAL_QUEUE_LISTS["allowed_paths"],
    "owned_surfaces": REQUIRED_CANONICAL_QUEUE_LISTS["owned_surfaces"],
    "exit_criterion": "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
}
REQUIRED_PROOF_PACKAGE_REPO = "chummer6-hub"

REQUIRED_RESOLVING_COMMITS = [
    LANDED_COMMIT,
    "e27f24c1",
    "0ea22419",
    "b4d761a2",
    "e75c4a97",
    "e578a519",
    "9fcec2a0",
    "266d526b",
    "6ea510c8",
    "7a825c73",
    "aff39474",
    "38d50742",
    "b9404a4c",
    "e6ae11a7",
    "4c542b50",
    "02bed909",
    "2017cdfe",
    "24432002",
    "4afd6c3e",
    "d99d080e",
    "b5b25e98",
    "d7cb9d6e",
    "ec81b660",
    "b2d5cbfc",
    "5eac0f47",
    "91514d42",
    "f7031d74",
    "f169b4a0",
    "b473e033",
    "782fa007",
    "26817b22",
    "6cf10549",
    "de9653ee",
    "3760ef63",
    "0337eeb5",
    "ad21e50f",
    "51c46e74",
    "ed3989d9",
    "653b23f0",
    "1a1c5615",
    "ed689925",
    "461e3709",
    "171c2de0",
    "73f1ee9a",
    "74dff34c",
    "aea02326",
    "2330a11c",
    "99a03a04",
    "0dca4b42",
    "2c351c92",
    "575daa11",
    "bffcad4d",
    "9454feb7",
    "f1513793",
    "7ddbc973",
    "01800bd9",
    "c9bbf63c",
    "2f7ed420",
    "15c5f0e5",
    "a270dcd0",
    "4fa19f0c",
    "6f468ee9",
    "4ed1f541",
    "f3300fd9",
    "06fa0634",
    "f23b6dc4",
    "7cf5461b",
    "cae283e9",
    "e908400b",
    "1870132d",
    "6b811ca2",
    "b7107364",
    "f49c64a9",
    "512f3569",
    "ff9c3313",
    "de158f6b",
    "8a542230",
    "74c3b75b",
    "76b350fc",
    "d3b19c88",
    "39af99da",
    "a4d16005",
    "1893a245",
    "7d86f38e",
    "c0c4dca1",
    "42a3d5a4",
    "af567e58",
    "2620a2f4",
    "5917695a",
    "2ded9038",
    "e7b5177b",
    "d72386ee",
    "fee0655a",
    "568b8358",
    "e0bcd91d",
    "aadffb5b",
    "a7a5ecea",
    "4b9c6919",
    "ea697985",
    "e9c87a3f",
    "d3c74d38",
    "6b5679de",
    "39c0ae8d",
    "8e90aac9",
    "b27c5142",
    "bc52177b",
    "cd392a72",
    "41d7ed57",
    "bd60fc5a",
    "2791f798",
    "93e5075a",
    "894dbedd",
    "997337a6",
    "e24162d9",
    "bb8db39c",
    "1d6c686c",
    "18902a34",
    "72fa2471",
    "c791e657",
    "438861f0",
    "17044a9f",
    "4238a88a",
    "b8a03984",
    "6961320a",
    "aceef790",
    "5f9621c3",
    "4e8eb4c1",
    "4bede125",
    "ebfaaf36",
    "38eb0769",
    "ed611d1a",
    "d9d6c9a0",
    "a01d80ab",
    "a766e82c",
    "d9f59d4f",
    "af6a480e",
    "a7d27da6",
    "0bc0c858",
    "c8ec0c6a",
    "e08468e2",
    "9e7d12ef",
    "554cd159",
    "8e0a630e",
    "47a831ba",
]

DEFAULT_PROOF_PATH = Path(".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json")
DEFAULT_SERVED_PROOF_PATH = Path("Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")
DEFAULT_QUEUE_STAGING_PATH = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_DESIGN_QUEUE_STAGING_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_SUCCESSOR_REGISTRY_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
ABSOLUTE_REPO_PREFIX = "/docker/chummercomplete/chummer6-hub/"
MATERIALIZER_ARGS = [
    "https://chummer.run",
    "docker-compose.yml",
    "120",
    "true",
]
COMMIT_PROOF_RE = re.compile(r"\bcommit\s+([0-9a-f]{8,40})\b", re.IGNORECASE)


def _configured_path(env_name: str, default_path: Path) -> Path:
    override = os.environ.get(env_name)
    return Path(override) if override else default_path


def _configured_repo_anchor_root(repo_root: Path) -> Path:
    override = os.environ.get("CHUMMER_RUN_SERVICES_PROOF_ANCHOR_ROOT")
    return Path(override) if override else repo_root


def _proof_path(repo_root: Path) -> Path:
    configured = _configured_path("CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH", DEFAULT_PROOF_PATH)
    return configured if configured.is_absolute() else repo_root / configured


def _served_proof_path(repo_root: Path) -> Path:
    configured = _configured_path("CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH", DEFAULT_SERVED_PROOF_PATH)
    return configured if configured.is_absolute() else repo_root / configured


def _extract_yaml_block(text: str, anchor: str) -> str | None:
    anchor_index = text.find(anchor)
    if anchor_index < 0:
        return None

    item_start = text.rfind("\n  - ", 0, anchor_index)
    start = anchor_index if item_start < 0 else item_start + 1
    next_item = text.find("\n  - ", start + 1)
    return text[start:] if next_item < 0 else text[start:next_item]


def _verify_marker_block(
    errors: list[str],
    path: Path,
    anchor: str,
    markers: list[str],
    label: str,
    required_lists: dict[str, list[str]] | None = None,
    forbidden_markers: list[str] | None = None,
) -> None:
    if not path.is_file():
        errors.append(f"missing canonical {label} file: {path}")
        return

    text = path.read_text(encoding="utf-8")
    block = _extract_yaml_block(text, anchor)
    if block is None:
        errors.append(f"canonical {label} missing block anchored by: {anchor}")
        return

    for marker in markers:
        if marker not in block:
            errors.append(f"canonical {label} block missing marker: {marker}")

    if forbidden_markers is not None:
        marker_matches = (
            _forbidden_markers_in_text(block)
            if forbidden_markers == FORBIDDEN_PROOF_MARKERS
            else [
                marker
                for marker in forbidden_markers
                if marker.casefold() in block.casefold()
            ]
        )
        for marker in marker_matches:
            errors.append(f"canonical {label} block has forbidden active-run proof marker: {marker}")

    if required_lists is not None:
        for key, expected_values in required_lists.items():
            actual_values = _extract_yaml_string_list(block, key)
            if actual_values is None:
                errors.append(f"canonical {label} block missing list: {key}")
                continue

            if actual_values != expected_values:
                errors.append(
                    f"canonical {label} block has wrong {key}: "
                    f"expected {expected_values!r}, got {actual_values!r}"
                )


def _verify_unique_yaml_anchor(errors: list[str], path: Path, anchor: str, label: str) -> None:
    if not path.is_file():
        return

    text = path.read_text(encoding="utf-8")
    count = sum(
        1
        for line in text.splitlines()
        if line.strip() == anchor or line.strip() == f"- {anchor}"
    )
    if count != 1:
        errors.append(f"canonical {label} has {count} rows anchored by: {anchor}")


def _verify_queue_mirror_block_matches(
    errors: list[str],
    queue_path: Path,
    design_queue_path: Path,
) -> None:
    if not queue_path.is_file() or not design_queue_path.is_file():
        return

    anchor = f"package_id: {PACKAGE_ID}"
    queue_block = _extract_yaml_block(queue_path.read_text(encoding="utf-8"), anchor)
    design_queue_block = _extract_yaml_block(design_queue_path.read_text(encoding="utf-8"), anchor)
    if queue_block is None or design_queue_block is None:
        return

    if queue_block != design_queue_block:
        errors.append(
            "Fleet successor queue staging block for next90-m102-hub-desktop-native-trust "
            "drifts from the design-owned successor queue source"
        )


def _extract_yaml_string_list(block: str, key: str) -> list[str] | None:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != f"{key}:":
            continue

        values: list[str] = []
        list_indent: int | None = None
        for child in lines[index + 1 :]:
            stripped = child.strip()
            if not stripped:
                continue

            indent = len(child) - len(child.lstrip(" "))
            if list_indent is None:
                list_indent = indent
            elif indent < list_indent:
                break

            if not stripped.startswith("- "):
                break

            values.append(stripped[2:].strip())

        return values

    return None


def _repo_anchor_from_proof_text(value: str) -> Path | None:
    if not value.startswith(ABSOLUTE_REPO_PREFIX):
        return None

    relative = value[len(ABSOLUTE_REPO_PREFIX) :].split(" ", 1)[0].strip()
    return Path(relative) if relative else None


def _required_repo_anchor_paths() -> list[Path]:
    anchors: list[Path] = []
    for values in (
        REQUIRED_CANONICAL_QUEUE_LISTS["proof"],
        REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"],
    ):
        for value in values:
            anchor = _repo_anchor_from_proof_text(value)
            if anchor is not None and anchor not in anchors:
                anchors.append(anchor)

    return anchors


def _proof_anchor_allowed_prefixes() -> list[Path]:
    prefixes = [Path(value) for value in REQUIRED_CANONICAL_QUEUE_LISTS["allowed_paths"]]
    prefixes.extend(Path(value) for value in ADJACENT_PROOF_ANCHOR_PREFIXES)
    return prefixes


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
    except ValueError:
        return False

    return True


def _is_allowed_repo_anchor_path(relative_path: Path) -> bool:
    return any(
        relative_path == prefix or _is_relative_to(relative_path, prefix)
        for prefix in _proof_anchor_allowed_prefixes()
    )


def _verify_required_repo_anchor_paths(errors: list[str], repo_root: Path) -> None:
    anchor_root = _configured_repo_anchor_root(repo_root)
    for relative_path in _required_repo_anchor_paths():
        if not (anchor_root / relative_path).exists():
            errors.append(f"canonical proof anchor does not resolve: {ABSOLUTE_REPO_PREFIX}{relative_path}")
        if not _is_allowed_repo_anchor_path(relative_path):
            errors.append(
                "canonical proof anchor is outside the M102 allowed paths: "
                f"{ABSOLUTE_REPO_PREFIX}{relative_path}"
            )


def _required_resolving_commits() -> list[str]:
    commits = list(REQUIRED_RESOLVING_COMMITS)
    extra_commits = os.environ.get("CHUMMER_DESKTOP_NATIVE_TRUST_EXTRA_REQUIRED_COMMITS", "")
    for commit in extra_commits.split(","):
        commit = commit.strip()
        if commit and commit not in commits:
            commits.append(commit)

    return commits


def _current_local_proof_floor_commit() -> str:
    return os.environ.get(
        "CHUMMER_DESKTOP_NATIVE_TRUST_CURRENT_PROOF_FLOOR_COMMIT",
        CURRENT_LOCAL_PROOF_FLOOR_COMMIT,
    ).strip()


def _verify_current_local_proof_floor(errors: list[str], repo_root: Path) -> None:
    commit = _current_local_proof_floor_commit()
    if not commit:
        errors.append("current M102 desktop-native trust proof floor commit is blank")
        return

    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"current M102 desktop-native trust proof floor does not resolve: {commit}")
        return

    subject_result = subprocess.run(
        ["git", "log", "-1", "--format=%s", commit],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if subject_result.returncode != 0:
        errors.append(f"current M102 desktop-native trust proof floor subject is unreadable: {commit}")
        return

    subject = subject_result.stdout.strip()
    if subject != CURRENT_LOCAL_PROOF_FLOOR_SUBJECT:
        errors.append(
            "current M102 desktop-native trust proof floor has wrong subject: "
            f"expected {CURRENT_LOCAL_PROOF_FLOOR_SUBJECT!r}, got {subject!r}"
        )

    commit = commit.lower()
    queue_commits = _extract_proof_commit_ids(REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
    registry_commits = _extract_proof_commit_ids(REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
    required_commits = {item.lower() for item in REQUIRED_RESOLVING_COMMITS}
    if commit not in queue_commits:
        errors.append(f"current M102 desktop-native trust proof floor is missing from canonical queue proof: {commit}")
    if commit not in registry_commits:
        errors.append(f"current M102 desktop-native trust proof floor is missing from canonical registry evidence: {commit}")
    if commit not in required_commits:
        errors.append(f"current M102 desktop-native trust proof floor is not enforced by resolver: {commit}")


def _extract_proof_commit_ids(values: list[str]) -> set[str]:
    commit_ids: set[str] = set()
    for value in values:
        match = COMMIT_PROOF_RE.search(value)
        if match is not None:
            commit_ids.add(match.group(1).lower())

    return commit_ids


def _verify_no_duplicate_proof_commits(errors: list[str], values: list[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        match = COMMIT_PROOF_RE.search(value)
        if match is None:
            continue

        commit = match.group(1).lower()
        if commit in seen:
            duplicates.add(commit)
        else:
            seen.add(commit)

    if duplicates:
        errors.append(f"M102 canonical {label} proof has duplicate commit citations: {sorted(duplicates)!r}")


def _verify_canonical_commit_floor_consistency(errors: list[str]) -> None:
    _verify_no_duplicate_proof_commits(errors, REQUIRED_CANONICAL_QUEUE_LISTS["proof"], "queue")
    _verify_no_duplicate_proof_commits(errors, REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"], "registry")

    queue_commits = _extract_proof_commit_ids(REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
    registry_commits = _extract_proof_commit_ids(REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
    required_commits = {commit.lower() for commit in REQUIRED_RESOLVING_COMMITS}

    if queue_commits != registry_commits:
        errors.append(
            "M102 canonical queue and registry proof commit floors differ: "
            f"queue={sorted(queue_commits)!r}, registry={sorted(registry_commits)!r}"
        )

    for commit in sorted(queue_commits | registry_commits):
        if commit not in required_commits:
            errors.append(f"M102 canonical proof cites commit not enforced by resolver: {commit}")


def _verify_required_commits(errors: list[str], repo_root: Path) -> None:
    for commit in _required_resolving_commits():
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(f"required M102 desktop-native trust proof commit does not resolve: {commit}")


def _verify_required_source_markers(errors: list[str], repo_root: Path) -> None:
    for relative_path, markers in REQUIRED_SOURCE_MARKERS.items():
        path = repo_root / relative_path
        if not path.is_file():
            errors.append(f"missing source file: {relative_path}")
            continue

        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def _stable_json_payload(path: Path, errors: list[str], label: str) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid json: {exc}")
        return None

    if not isinstance(payload, dict):
        errors.append(f"{label} is not a json object")
        return None

    stable = dict(payload)
    stable.pop("generatedAt", None)
    stable.pop("generated_at", None)
    return stable


def _materializer_args_from_payload(payload: dict) -> list[str]:
    base_url = str(payload.get("base_url") or MATERIALIZER_ARGS[0])
    compose_file = str(payload.get("compose_file") or MATERIALIZER_ARGS[1])
    timeout_seconds = str(payload.get("playwright_timeout_seconds") or MATERIALIZER_ARGS[2])
    skip_rebuild = payload.get("edge_rebuild_skipped")
    if isinstance(skip_rebuild, bool):
        skip_rebuild_arg = str(skip_rebuild).lower()
    elif skip_rebuild is None:
        skip_rebuild_arg = MATERIALIZER_ARGS[3]
    else:
        skip_rebuild_arg = str(skip_rebuild).lower()

    return [
        base_url,
        compose_file,
        timeout_seconds,
        skip_rebuild_arg,
    ]


def _forbidden_marker_text_variants(value: str) -> list[str]:
    html_decoded = html.unescape(value)
    url_decoded = urllib.parse.unquote(value)
    html_then_url_decoded = urllib.parse.unquote(html_decoded)
    url_then_html_decoded = html.unescape(url_decoded)
    variants = [
        value,
        html_decoded,
        url_decoded,
        html_then_url_decoded,
        url_then_html_decoded,
    ]
    return list(dict.fromkeys(variants))


def _normalize_forbidden_marker_text(value: str) -> str:
    normalized_variants = (
        re.sub(r"[^a-z0-9]+", "", variant.casefold())
        for variant in _forbidden_marker_text_variants(value)
    )
    return " ".join(dict.fromkeys(normalized_variants))


def _forbidden_markers_in_text(value: str) -> list[str]:
    folded_value = "\n".join(variant.casefold() for variant in _forbidden_marker_text_variants(value))
    normalized_value = _normalize_forbidden_marker_text(value)
    matches: list[str] = []
    for marker, marker_folded in FORBIDDEN_PROOF_MARKER_MATCHES:
        if marker_folded in folded_value:
            matches.append(marker)

    for marker, marker_normalized in FORBIDDEN_PROOF_MARKER_NORMALIZED_MATCHES:
        if marker in matches or not marker_normalized:
            continue
        if marker_normalized in normalized_value:
            matches.append(marker)

    for marker, pattern in FORBIDDEN_PROOF_FIELD_PATTERNS:
        if marker in matches:
            continue
        if any(pattern.search(variant) for variant in _forbidden_marker_text_variants(value)):
            matches.append(marker)

    return matches


def _verify_json_has_no_forbidden_markers(
    errors: list[str],
    value: object,
    label: str,
    path: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _verify_json_has_no_forbidden_markers(errors, child, label, f"{path}.{key}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _verify_json_has_no_forbidden_markers(errors, child, label, f"{path}[{index}]")
        return

    if not isinstance(value, str):
        return

    for marker in _forbidden_markers_in_text(value):
        errors.append(f"{label} has forbidden active-run proof marker at {path}: {marker}")


def _verify_evidence_path_has_no_forbidden_markers(errors: list[str], path: Path, label: str) -> None:
    for marker in _forbidden_markers_in_text(str(path)):
        errors.append(f"configured {label} path has forbidden active-run proof marker: {marker}")


def _verify_materialized_proof_reproducible(errors: list[str], repo_root: Path, proof_path: Path) -> None:
    materializer_path = repo_root / "scripts" / "materialize_hub_local_release_proof.py"
    if not materializer_path.is_file():
        errors.append("missing proof materializer: scripts/materialize_hub_local_release_proof.py")
        return

    published = _stable_json_payload(proof_path, errors, "published proof file")
    if published is None:
        return

    with tempfile.TemporaryDirectory() as temp_root:
        expected_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        result = subprocess.run(
            ["python3", str(materializer_path), str(expected_path), *_materializer_args_from_payload(published)],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(
                "proof materializer failed while checking reproducibility: "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )
            return

        expected = _stable_json_payload(expected_path, errors, "materialized proof file")
        if expected is None:
            return

    if published != expected:
        errors.append(
            "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from "
            "scripts/materialize_hub_local_release_proof.py for next90-m102-hub-desktop-native-trust"
        )


def _verify_unique_string_list(errors: list[str], values: list, label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue

        normalized = value.strip().casefold()
        if not normalized:
            continue

        if normalized in seen:
            duplicates.add(value.strip())
        else:
            seen.add(normalized)

    if duplicates:
        errors.append(f"{label} has duplicate entries: {', '.join(sorted(duplicates))}")


def _is_native_install_linking_route(route: str) -> bool:
    return route == NATIVE_INSTALL_LINKING_ROUTE_PREFIX or route.startswith(f"{NATIVE_INSTALL_LINKING_ROUTE_PREFIX}/")


def _verify_m102_proof_payload(errors: list[str], proof: dict, label: str) -> None:
    _verify_json_has_no_forbidden_markers(errors, proof, label)

    package_repo = proof.get("package_repo")
    if package_repo != REQUIRED_PROOF_PACKAGE_REPO:
        errors.append(
            f"{label} has wrong package_repo: expected {REQUIRED_PROOF_PACKAGE_REPO!r}, got {package_repo!r}"
        )

    proof_route_set: set[str] = set()
    known_package_ids: set[str] = set()
    proof_routes = proof.get("proof_routes")
    if not isinstance(proof_routes, list):
        errors.append(f"{label} missing list field: proof_routes")
    else:
        _verify_unique_string_list(errors, proof_routes, f"{label} proof_routes")
        proof_route_set = {item for item in proof_routes if isinstance(item, str)}
        for required in REQUIRED_TOP_LEVEL_PROOF_ROUTES:
            if required not in proof_route_set:
                errors.append(f"{label} proof_routes missing M102 route: {required}")

    journeys_passed = proof.get("journeys_passed")
    if not isinstance(journeys_passed, list):
        errors.append(f"{label} missing list field: journeys_passed")
    else:
        _verify_unique_string_list(errors, journeys_passed, f"{label} journeys_passed")
        journey_set = {item for item in journeys_passed if isinstance(item, str)}
        for required in REQUIRED_TOP_LEVEL_JOURNEYS:
            if required not in journey_set:
                errors.append(f"{label} journeys_passed missing M102 journey: {required}")

    packages = proof.get("successor_queue_packages")
    proof_package = None
    if isinstance(packages, list):
        matching_packages = [
            item
            for item in packages
            if isinstance(item, dict)
            and item.get("package_id") == PACKAGE_ID
        ]
        if len(matching_packages) != 1:
            errors.append(
                f"{label} has {len(matching_packages)} successor_queue_packages entries for {PACKAGE_ID}"
            )
        proof_package = matching_packages[0] if matching_packages else None

    if not isinstance(proof_package, dict):
        errors.append(f"{label} missing successor_queue_packages entry for next90-m102-hub-desktop-native-trust")
    else:
        for key, expected in REQUIRED_PROOF_PACKAGE.items():
            actual = proof_package.get(key)
            if actual != expected:
                errors.append(f"{label} proof package has wrong {key}: expected {expected!r}, got {actual!r}")

    if isinstance(packages, list):
        for item in packages:
            if not isinstance(item, dict):
                continue
            package_id = item.get("package_id")
            if isinstance(package_id, str) and package_id.strip():
                known_package_ids.add(package_id)

    receipt_items = proof.get("proof_receipts", [])
    if not isinstance(receipt_items, list):
        errors.append(f"{label} missing list field: proof_receipts")
        receipt_items = []

    top_level_package = proof.get("successor_queue_package")
    if isinstance(top_level_package, dict):
        top_level_package_id = top_level_package.get("package_id")
        if isinstance(top_level_package_id, str) and top_level_package_id.strip():
            if top_level_package_id not in known_package_ids:
                errors.append(
                    f"{label} top-level successor_queue_package package_id is not listed in successor_queue_packages: "
                    f"{top_level_package_id}"
                )
        else:
            errors.append(f"{label} top-level successor_queue_package has invalid package_id: {top_level_package_id!r}")

    receipts: dict[str, dict] = {}
    for receipt_id in REQUIRED_PROOF_RECEIPTS:
        matching_receipts = [
            item
            for item in receipt_items
            if isinstance(item, dict)
            and item.get("receipt_id") == receipt_id
        ]
        if len(matching_receipts) != 1:
            errors.append(f"{label} has {len(matching_receipts)} proof_receipts entries for {receipt_id}")
        if matching_receipts:
            receipts[receipt_id] = matching_receipts[0]

    receipt_package_ids: set[str] = set()
    for item in receipt_items:
        if not isinstance(item, dict):
            continue
        receipt_id = item.get("receipt_id")
        package_id = item.get("package_id")
        if not isinstance(package_id, str) or not package_id.strip():
            errors.append(f"{label} receipt has invalid package_id: {receipt_id!r}")
            continue

        receipt_package_ids.add(package_id)
        if known_package_ids and package_id not in known_package_ids:
            errors.append(
                f"{label} receipt {receipt_id!r} references package_id not listed in successor_queue_packages: "
                f"{package_id}"
            )

    if isinstance(top_level_package, dict):
        top_level_package_id = top_level_package.get("package_id")
        if isinstance(top_level_package_id, str) and top_level_package_id.strip():
            if top_level_package_id not in receipt_package_ids:
                errors.append(
                    f"{label} top-level successor_queue_package package_id has no proof_receipts: "
                    f"{top_level_package_id}"
                )

    for receipt_id, expected in REQUIRED_PROOF_RECEIPTS.items():
        receipt = receipts.get(receipt_id)
        if not isinstance(receipt, dict):
            errors.append(f"{label} missing receipt: {receipt_id}")
            continue

        for key in ("package_id", "milestone_id", "frontier_id", "summary"):
            if receipt.get(key) != expected[key]:
                errors.append(f"{label} {receipt_id} has wrong {key}: {receipt.get(key)!r}")

        for key in ("surfaces", "routes"):
            actual_values = receipt.get(key)
            if not isinstance(actual_values, list):
                errors.append(f"{label} {receipt_id} missing list field: {key}")
                continue

            _verify_unique_string_list(errors, actual_values, f"{label} {receipt_id} {key}")
            actual = {item for item in actual_values if isinstance(item, str)}
            for required in expected[key]:
                if required not in actual:
                    errors.append(f"{label} {receipt_id} missing {key[:-1]}: {required}")

            if actual_values != expected[key]:
                errors.append(
                    f"{label} {receipt_id} has wrong {key}: "
                    f"expected {expected[key]!r}, got {actual_values!r}"
                )

            if key == "routes" and proof_route_set:
                if not any(_is_native_install_linking_route(route) for route in actual):
                    errors.append(
                        f"{label} {receipt_id} routes do not include a grant-bound native install-linking route"
                    )
                for route in sorted(actual):
                    if route not in proof_route_set:
                        errors.append(
                            f"{label} {receipt_id} route is not listed in top-level proof_routes: {route}"
                        )


def _verify_static_proof_file(errors: list[str], path: Path, label: str) -> None:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return

    try:
        proof = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid json: {exc}")
        return

    if not isinstance(proof, dict):
        errors.append(f"{label} is not a json object")
        return

    _verify_m102_proof_payload(errors, proof, label)


def _verify_served_proof_matches_published(errors: list[str], proof_path: Path, served_proof_path: Path) -> None:
    if not proof_path.is_file() or not served_proof_path.is_file():
        return

    published = _stable_json_payload(proof_path, errors, "published proof file")
    served = _stable_json_payload(served_proof_path, errors, "served release proof file")
    if published is None or served is None:
        return

    if served != published:
        errors.append(
            "served HUB_LOCAL_RELEASE_PROOF.generated.json drifts from "
            "published HUB_LOCAL_RELEASE_PROOF.generated.json for next90-m102-hub-desktop-native-trust"
        )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []

    _verify_required_repo_anchor_paths(errors, repo_root)
    _verify_required_commits(errors, repo_root)
    _verify_current_local_proof_floor(errors, repo_root)
    _verify_canonical_commit_floor_consistency(errors)
    _verify_required_source_markers(errors, repo_root)

    proof_path = _proof_path(repo_root)
    _verify_evidence_path_has_no_forbidden_markers(errors, proof_path, "published proof file")
    if not proof_path.is_file():
        try:
            display_path = proof_path.relative_to(repo_root)
        except ValueError:
            display_path = proof_path
        errors.append(f"missing proof file: {display_path}")
    else:
        _verify_materialized_proof_reproducible(errors, repo_root, proof_path)
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"proof file is not valid json: {exc}")
        else:
            _verify_m102_proof_payload(errors, proof, "published proof file")

    served_proof_path = _served_proof_path(repo_root)
    _verify_evidence_path_has_no_forbidden_markers(errors, served_proof_path, "served release proof file")
    _verify_static_proof_file(errors, served_proof_path, "served release proof file")
    _verify_served_proof_matches_published(errors, proof_path, served_proof_path)

    queue_staging_path = _configured_path("CHUMMER_NEXT90_QUEUE_STAGING_PATH", DEFAULT_QUEUE_STAGING_PATH)
    design_queue_staging_path = _configured_path("CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH", DEFAULT_DESIGN_QUEUE_STAGING_PATH)
    successor_registry_path = _configured_path("CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH", DEFAULT_SUCCESSOR_REGISTRY_PATH)
    _verify_evidence_path_has_no_forbidden_markers(errors, queue_staging_path, "successor queue staging")
    _verify_evidence_path_has_no_forbidden_markers(errors, design_queue_staging_path, "design successor queue staging")
    _verify_evidence_path_has_no_forbidden_markers(errors, successor_registry_path, "successor registry")

    _verify_unique_yaml_anchor(errors, queue_staging_path, f"package_id: {PACKAGE_ID}", "successor queue staging")
    _verify_unique_yaml_anchor(errors, design_queue_staging_path, f"package_id: {PACKAGE_ID}", "design successor queue staging")
    _verify_unique_yaml_anchor(errors, successor_registry_path, "id: 102.1", "successor registry")
    _verify_queue_mirror_block_matches(errors, queue_staging_path, design_queue_staging_path)

    _verify_marker_block(
        errors,
        queue_staging_path,
        f"package_id: {PACKAGE_ID}",
        REQUIRED_CANONICAL_QUEUE_MARKERS,
        "successor queue staging",
        REQUIRED_CANONICAL_QUEUE_LISTS,
        FORBIDDEN_PROOF_MARKERS,
    )
    _verify_marker_block(
        errors,
        design_queue_staging_path,
        f"package_id: {PACKAGE_ID}",
        REQUIRED_CANONICAL_QUEUE_MARKERS,
        "design successor queue staging",
        REQUIRED_CANONICAL_QUEUE_LISTS,
        FORBIDDEN_PROOF_MARKERS,
    )
    _verify_marker_block(
        errors,
        successor_registry_path,
        "id: 102.1",
        REQUIRED_CANONICAL_REGISTRY_MARKERS,
        "successor registry",
        REQUIRED_CANONICAL_REGISTRY_LISTS,
        FORBIDDEN_PROOF_MARKERS,
    )

    if errors:
        print("desktop native trust receipt verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("desktop native trust receipts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
