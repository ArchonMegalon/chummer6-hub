from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LANDING = REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"
HANDOFF_PARTIAL = REPO_ROOT / "Chummer.Run.Api/Views/Shared/_MobileAppHandoff.cshtml"
HANDOFF_MODEL = REPO_ROOT / "Chummer.Run.Api/ViewModels/MobileAppHandoffViewModel.cs"
HANDOFF_SCRIPT = REPO_ROOT / "Chummer.Run.Api/wwwroot/js/mobile-app-handoff.js"
INSTALL_SCRIPT = REPO_ROOT / "Chummer.Run.Api/wwwroot/mobile-install-shell.js"
SITE_CSS = REPO_ROOT / "Chummer.Run.Api/wwwroot/css/site.css"
SITE_SCRIPT = REPO_ROOT / "Chummer.Run.Api/wwwroot/js/site.js"
ROOT_WORKER = REPO_ROOT / "Chummer.Run.Api/wwwroot/service-worker.js"
MOBILE_WORKER = REPO_ROOT / "Chummer.Run.Api/wwwroot/mobile/service-worker.js"
PUBLIC_CONTROLLER = REPO_ROOT / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
EDGE_PROGRAM = REPO_ROOT / "Chummer.Run.Api/Program.cs"
LEGACY_PROXY_CONTROLLER = REPO_ROOT / "Chummer.Run.Api/Controllers/LegacySurfaceRedirectController.cs"
PROXY_REDIRECT_POLICY = REPO_ROOT / "Chummer.Run.Api/Services/PublicProxyRedirectPolicy.cs"
FRONTDOOR_BROWSER_PROOF = REPO_ROOT / "tests/public/frontdoor-mobile-launch.spec.ts"


def _run_handoff_runtime(payloads: list[str], preference: str) -> dict[str, object]:
    probe = r"""
const fs = require("fs");
const payloads = JSON.parse(process.argv[2]);
const preference = process.argv[3];
global.HTMLElement = class HTMLElement {};
global.HTMLInputElement = class HTMLInputElement extends HTMLElement {};
global.HTMLAnchorElement = class HTMLAnchorElement extends HTMLElement {};
global.SVGElement = class SVGElement extends HTMLElement {};
global.window = {
  navigator: {
    userAgentData: { mobile: false },
    maxTouchPoints: 0,
    standalone: false
  },
  matchMedia: () => ({ matches: false }),
  localStorage: {
    getItem: () => preference,
    setItem: () => {}
  }
};
global.document = {
  readyState: "loading",
  addEventListener: () => {},
  querySelectorAll: () => []
};
eval(fs.readFileSync(process.argv[1], "utf8"));
const handoff = window.ChummerMobileAppHandoff;
process.stdout.write(JSON.stringify({
  usesMobilePresentation: handoff.usesMobilePresentation(),
  matrices: payloads.map((payload) => handoff.buildQrMatrix(payload))
}));
"""
    result = subprocess.run(
        ["node", "-e", probe, str(HANDOFF_SCRIPT), json.dumps(payloads), preference],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_landing_play_entry_uses_a_progressive_desktop_to_mobile_handoff() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    partial = HANDOFF_PARTIAL.read_text(encoding="utf-8")

    assert 'href="/mobile/player" data-mobile-app-handoff="mobile-app-handoff"' in landing
    assert 'Target: MobileAppHandoffTarget.Play' in landing
    assert 'data-public-install-handoff="true"' in landing
    assert 'data-disabled-target="/mobile/player"' not in landing
    assert 'role="dialog" aria-modal="true"' in partial
    assert 'data-mobile-app-path="@targetUrl"' in partial
    assert 'data-mobile-app-origin="@PublicOrigin.Origin"' in partial
    assert "PublicOrigin.BuildAbsolute(Model.Path)" in partial
    assert 'data-mobile-app-qr role="img"' in partial
    assert 'data-copy-mobile-app-link' in partial
    assert 'data-mobile-app-open' in partial
    assert 'data-show-mobile-app-qr' in partial
    assert 'data-mobile-app-suggestion' in partial
    assert 'readonly data-mobile-app-link' in partial
    assert 'src="~/js/mobile-app-handoff.js" asp-append-version="true"' in landing
    assert 'data-mobile-app-device-picker' in landing
    assert 'data-mobile-app-device-choice="auto"' in landing
    assert 'data-mobile-app-device-choice="mobile"' in landing
    assert 'data-mobile-app-device-choice="desktop"' in landing
    assert 'data-mobile-app-device-status' in landing
    assert 'aria-live="polite"' in landing
    assert "The link opens an installable PWA." in partial
    assert "Your phone browser decides whether and how to offer installation" in partial
    assert "installs automatically" not in partial.lower()


def test_landing_build_entry_reuses_the_same_handoff_component_for_the_builder_pwa() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    partial = HANDOFF_PARTIAL.read_text(encoding="utf-8")
    model = HANDOFF_MODEL.read_text(encoding="utf-8")
    controller = PUBLIC_CONTROLLER.read_text(encoding="utf-8")

    assert 'href="/build" data-mobile-app-handoff="build-mobile-app-handoff"' in landing
    assert 'aria-controls="build-mobile-app-handoff"' in landing
    assert 'Id: "build-mobile-app-handoff"' in landing
    assert 'Target: MobileAppHandoffTarget.Build' in landing
    assert 'Heading: "Open the character builder on your phone"' in landing
    assert '[HttpGet("/build")]' in controller
    assert landing.count('"~/Views/Shared/_MobileAppHandoff.cshtml"') == 2
    assert "@model MobileAppHandoffViewModel" in partial
    assert "public sealed record MobileAppHandoffViewModel" in model
    assert "public enum MobileAppHandoffTarget" in model
    assert 'MobileAppHandoffTarget.Build => "/build"' in model
    assert 'MobileAppHandoffTarget.Play => "/mobile/player"' in model
    assert "throw new InvalidOperationException" in model
    assert "string Path," not in model


def test_signed_out_landing_exposes_public_install_handoffs_without_granting_authority() -> None:
    landing = LANDING.read_text(encoding="utf-8")

    assert landing.count('data-public-install-handoff="true"') == 2
    assert 'href="/build" data-mobile-app-handoff="build-mobile-app-handoff"' in landing
    assert 'href="/mobile/player" data-mobile-app-handoff="mobile-app-handoff"' in landing
    assert "@if (Model.Chrome.Authenticated)\n{\n    @await Html.PartialAsync" not in landing
    assert 'data-sign-in-href="/login?next=%2Fbuild"' not in landing
    assert 'data-sign-in-href="/login?next=%2Fmobile%2Fplayer"' not in landing


def test_jammer_companion_is_a_public_alias_not_a_new_install_target_or_authority() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    model = HANDOFF_MODEL.read_text(encoding="utf-8")
    controller = PUBLIC_CONTROLLER.read_text(encoding="utf-8")
    program = EDGE_PROGRAM.read_text(encoding="utf-8")

    assert 'Eyebrow: "Chummer Play · Jammer Companion"' in landing
    assert "also known as Jammer Companion" in landing
    assert 'Target: MobileAppHandoffTarget.Play' in landing
    assert 'MobileAppHandoffTarget.Play => "/mobile/player"' in model
    assert "Jammer" not in model
    assert 'href="/jammer"' not in landing
    assert '[HttpGet("/jammer")]' in controller
    assert '[HttpHead("/jammer")]' in controller
    assert 'path.Equals("/jammer", StringComparison.OrdinalIgnoreCase)' in program
    assert 'context.Response.Redirect($"{redirectPath}#", permanent: false);' in program


def test_public_role_aliases_drop_query_state_before_routing() -> None:
    program = EDGE_PROGRAM.read_text(encoding="utf-8")
    alias_start = program.index("if ((HttpMethods.IsGet(context.Request.Method)")
    alias_end = program.index("app.UseRouting();", alias_start)
    alias_middleware = program[alias_start:alias_end]

    assert "HttpMethods.IsGet" in alias_middleware
    assert "HttpMethods.IsHead" in alias_middleware
    assert 'context.Response.Headers["Referrer-Policy"] = "no-referrer";' in alias_middleware
    assert 'context.Response.Headers.CacheControl = "private, no-store, no-cache, max-age=0";' in alias_middleware
    assert 'context.Response.Redirect($"{redirectPath}#", permanent: false);' in alias_middleware
    assert "QueryString" not in alias_middleware


def test_frontdoor_proof_cannot_write_pass_before_default_deny_assertions() -> None:
    source = FRONTDOOR_BROWSER_PROOF.read_text(encoding="utf-8")
    main_test = source.split("test('homepage legacy mobile anchors", 1)[0]
    privacy_assertion = main_test.index("expect(pageErrors.length).toBe(0);")
    first_receipt = main_test.index("writeJsonArtifact('FRONTDOOR_MOBILE_LAUNCH.generated.json'")
    catch_boundary = main_test.index("} catch (error)")

    assert privacy_assertion < first_receipt < catch_boundary
    assert "live_turn_companion_shell: false" in main_test
    assert "live_turn_companion_shell: true" not in source
    assert "privateBrowserStateKeys.length" in main_test
    assert "failure_stage: proofStage" in source
    assert "failure_type: safeErrorType(error)" in source
    assert "failure: errorMessage(error)" not in source
    assert "status: 'fail'" in main_test[catch_boundary:]

    redirect_test = source.split("test('homepage legacy mobile anchors", 1)[1]
    redirect_assertion = redirect_test.index("expect(finalUrl.hash).toBe('#turn-runsite-card');")
    redirect_receipt = redirect_test.index("writeJsonArtifact('FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json'")
    redirect_catch = redirect_test.index("} catch (error)")
    assert redirect_assertion < redirect_receipt < redirect_catch


def test_qr_handoff_is_first_party_deterministic_and_offline_safe() -> None:
    script = HANDOFF_SCRIPT.read_text(encoding="utf-8")

    assert "buildQrMatrix" in script
    assert "new TextEncoder().encode(value)" in script
    assert "new URL(configuredOrigin)" in script
    assert "target.origin !== canonicalOrigin.origin" in script
    for clean_target in ("/build", "/mobile/player", "/mobile/gm", "/mobile/observer"):
        assert f'"{clean_target}"' in script
    assert "target.search || target.hash" in script
    assert "!ALLOWED_HANDOFF_PATHS.has(target.pathname)" in script
    assert "window.location.origin" not in script
    assert 'target.search = "";' not in script
    assert 'target.hash = "";' not in script
    assert 'window.matchMedia("(pointer: coarse)").matches' in script
    assert 'window.matchMedia("(max-width:' not in script
    assert "userAgentData" in script
    assert "maxTouchPoints" in script
    assert "const usesMobilePresentation" in script
    assert 'resolveEffectiveDevice(loadDevicePreference()) === "mobile"' in script
    assert re.search(r"\.userAgent(?!Data)", script) is None
    assert 'DEVICE_PREFERENCE_KEY = "chummer.mobile-app-handoff.device.v1"' in script
    assert "window.localStorage.getItem(DEVICE_PREFERENCE_KEY)" in script
    assert "window.localStorage.setItem(DEVICE_PREFERENCE_KEY, memoryDevicePreference)" in script
    assert 'normalizeDevicePreference = (value)' in script
    assert 'if (normalizedPreference === "mobile" || normalizedPreference === "desktop")' in script
    resolver = script.split("const resolveEffectiveDevice", 1)[1].split(
        "const usesMobilePresentation", 1
    )[0]
    assert resolver.index("signals?.standalone") < resolver.index("signals?.userAgentDataMobile")
    assert resolver.index("signals?.userAgentDataMobile") < resolver.index("signals?.coarsePointer")
    assert "signals?.maxTouchPoints > 0" in resolver
    assert (
        'if (effectiveDevice === "mobile") {\n'
        "          return;\n"
        "        }\n"
        "        event.preventDefault();"
    ) in script
    assert "event.preventDefault();" in script
    assert 'dialog.dataset.mobileAppSuggestedAction = suggestedAction;' in script
    assert 'showQrButton?.addEventListener("click"' in script
    assert "setQrExpanded" in script
    assert "bindInlineHandoff" in script
    assert 'querySelectorAll("[data-mobile-app-inline-handoff]")' in script
    assert 'showQrButton.setAttribute("aria-expanded"' in script
    assert "qrCard.focus" not in script
    assert "showQrButton.focus({ preventScroll: true });" in script
    assert "ui.bindModalDialog" in script
    assert "ui.copyToClipboard" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert "api.qrserver" not in script


def test_exported_device_helper_honors_the_persisted_browser_override() -> None:
    assert _run_handoff_runtime([], "mobile")["usesMobilePresentation"] is True
    assert _run_handoff_runtime([], "desktop")["usesMobilePresentation"] is False


def test_frontdoor_qr_is_independently_decodable_for_build_and_play() -> None:
    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")
    payloads = ["https://chummer.run/build", "https://chummer.run/mobile/player"]
    result = _run_handoff_runtime(payloads, "desktop")
    decoder = cv2.QRCodeDetector()

    for payload, matrix in zip(payloads, result["matrices"], strict=True):
        modules = numpy.asarray(matrix, dtype=numpy.uint8)
        assert modules.ndim == 2
        assert modules.shape[0] == modules.shape[1]
        assert set(numpy.unique(modules)).issubset({0, 1})

        pixels = numpy.where(modules, 0, 255).astype(numpy.uint8)
        pixels = numpy.pad(pixels, 4, constant_values=255)
        image = cv2.resize(
            pixels,
            None,
            fx=12,
            fy=12,
            interpolation=cv2.INTER_NEAREST,
        )
        decoded, points, _ = decoder.detectAndDecode(image)
        assert points is not None
        assert decoded == payload


def test_projected_play_installer_recovers_to_the_same_manual_install_contract() -> None:
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "} catch {" in script
    assert "} finally {" in script
    assert "installButton.disabled = accepted || isInstalled();" in script
    assert 'displayModeQuery.addEventListener("change", handleDisplayModeChange);' in script
    assert "restoreBrowserInstallState" in script
    assert "} else if (window.navigator.standalone !== true) {" in script
    assert 'window.addEventListener("pagehide", cleanup' in script


def test_public_play_projection_is_retired_and_private_transport_is_deny_all() -> None:
    program = EDGE_PROGRAM.read_text(encoding="utf-8")
    controller = PUBLIC_CONTROLLER.read_text(encoding="utf-8")
    legacy = LEGACY_PROXY_CONTROLLER.read_text(encoding="utf-8")
    gateway = (REPO_ROOT / "Chummer.Run.Api/Services/PublicPlayProxyGateway.cs").read_text(encoding="utf-8")

    assert "AllowAutoRedirect = false" in program
    assert "gateway.TryHandleAsync" not in program
    assert "IPublicPlayPrivateRouteDelegator" in program
    assert "_privatePlayRoutes.DenyAsync" in legacy
    assert "_playUpstream" not in legacy
    assert "TryProxyPublicPlayPwaAsync" not in controller
    assert "context.Request.Headers" not in gateway
    assert "Set-Cookie" not in gateway
    assert "Array.Empty<string>()" in gateway
    assert "PublicPlayProxyDisposition.NotMatched" in gateway
    assert "IHttpClientFactory" not in gateway
    assert "HttpRequestMessage" not in gateway
    assert "projection_disabled_invalid_configuration" in gateway


def test_copy_failure_is_announced_as_an_accessibility_error() -> None:
    script = HANDOFF_SCRIPT.read_text(encoding="utf-8")

    assert (
        '"Copy is unavailable here. The mobile link is selected so you can copy it manually.",\n'
        "          true"
    ) in script
    assert "googleapis" not in script
    assert "cdn." not in script


def test_qr_modal_has_an_explicit_hidden_small_viewport_and_target_size_contract() -> None:
    css = SITE_CSS.read_text(encoding="utf-8")

    modal_button_rule = css.split(".mobile-app-handoff .button-like {", 1)[1].split("}", 1)[0]
    link_input_rule = css.split(".mobile-app-handoff__link-field input {", 1)[1].split("}", 1)[0]
    device_picker_rule = css.split(".mobile-app-device-picker label {", 1)[1].split("}", 1)[0]

    assert ".mobile-app-handoff[hidden]" in css
    assert ".mobile-app-handoff__qr-card[hidden]" in css
    assert ".mobile-app-handoff__qr" in css
    assert "shape-rendering" not in css  # The SVG owns its deterministic pixel geometry.
    assert "max-height: calc(100svh - 24px);" in css
    assert "overflow-y: auto;" in css
    assert "@media (forced-colors: active)" in css
    assert "forced-color-adjust: none;" in css
    assert ".mobile-app-device-picker" in css
    assert "min-width: 44px;" in modal_button_rule
    assert "min-height: 44px;" in modal_button_rule
    assert "min-height: 44px;" in link_input_rule
    assert "min-height: 44px;" in device_picker_rule
    assert "outline: 3px solid #f3eadb;" in css
    assert "border-color: CanvasText;" in css
    assert "color: HighlightText;" in css


def test_handoff_modal_makes_only_its_background_inert_and_restores_it() -> None:
    script = SITE_SCRIPT.read_text(encoding="utf-8")

    assert "const modalInertState = new WeakMap();" in script
    assert "const makeBackgroundInert" in script
    assert "const restoreBackground" in script
    assert "sibling.inert = true;" in script
    assert "node.inert = state.wasInert;" in script
    assert "makeBackgroundInert();" in script
    assert "restoreBackground();" in script
    assert 'setAttribute("aria-hidden"' not in script


def test_frontdoor_browser_gate_measures_targets_and_keyboard_focus_at_runtime() -> None:
    source = FRONTDOOR_BROWSER_PROOF.read_text(encoding="utf-8")
    desktop_test = source.split(
        "test('desktop Build and Play handoffs keep keyboard focus contained and expose 44px controls'",
        1,
    )[1].split("test('homepage legacy mobile anchors", 1)[0]

    assert "getBoundingClientRect()" in desktop_test
    assert "toBeGreaterThanOrEqual(44)" in desktop_test
    assert "await expect(closeButton).toBeFocused();" in desktop_test
    assert "await page.keyboard.press('Shift+Tab');" in desktop_test
    assert "await page.keyboard.press('Escape');" in desktop_test
    assert "await expect(opener).toBeFocused();" in desktop_test


def test_public_root_and_mobile_play_workers_use_exact_atomic_cache_contracts() -> None:
    worker = ROOT_WORKER.read_text(encoding="utf-8")
    mobile_wrapper = MOBILE_WORKER.read_text(encoding="utf-8")

    assert 'const CACHE_VERSION = "v19";' in worker
    assert 'const CACHE_CONTRACT = "run-api-projection-v2";' in worker
    assert 'IS_MOBILE_PLAY_SCOPE' in worker
    assert '"chummer-mobile-play"' in worker
    assert '"chummer-public-root"' in worker
    assert '`${CACHE_FAMILY}-static-${CACHE_CONTRACT}-${CACHE_VERSION}`' in worker
    assert '`${CACHE_FAMILY}-media-${CACHE_CONTRACT}-${CACHE_VERSION}`' in worker
    assert '`${CACHE_FAMILY}-media-meta-${CACHE_CONTRACT}-${CACHE_VERSION}`' in worker
    assert '"chummer-shell-play-shell-"' in worker
    assert "isLegacyPrivateCache(key)" in worker
    assert "event.waitUntil(precacheCriticalShell());" in worker
    assert "self.skipWaiting()" not in worker
    assert "self.clients.claim()" not in worker
    assert "Promise.allSettled" not in worker
    assert "PUBLIC_CACHEABLE_ASSETS = new Map" in worker
    assert "isExpectedPublicAssetResponse" in worker
    assert "chummer-build-static-" not in worker
    assert "function isBuildOwnedRequest(url)" in worker
    assert 'url.pathname === "/blazor" || url.pathname.startsWith("/blazor/")' in worker
    assert "if (isBuildOwnedRequest(url))" in worker
    assert 'importScripts("/service-worker.js")' in mobile_wrapper
    assert '"/mobile-install-shell.js"' in worker
    assert '"/manifest.observer.webmanifest"' in worker
    assert '"/mobile-turn-companion.js"' not in worker


def test_public_worker_leaves_build_navigation_and_assets_to_the_blazor_scope() -> None:
    worker = ROOT_WORKER.read_text(encoding="utf-8")
    fetch_handler = worker.split('self.addEventListener("fetch"', 1)[1]

    build_bypass = fetch_handler.index("if (isBuildOwnedRequest(url))")
    play_api_handler = fetch_handler.index('if (url.pathname.startsWith("/api/play/"))')
    navigation_handler = fetch_handler.index('if (request.mode === "navigate")')
    media_handler = fetch_handler.index("if (isMediaRequest(request, url))")
    shell_cache_handler = fetch_handler.index("caches.open(SHELL_CACHE)")

    assert build_bypass < play_api_handler
    assert build_bypass < navigation_handler
    assert build_bypass < media_handler
    assert build_bypass < shell_cache_handler
    assert fetch_handler[build_bypass:play_api_handler].count("return;") == 1


def test_public_worker_never_caches_rendered_mobile_or_credentialed_navigation() -> None:
    worker = ROOT_WORKER.read_text(encoding="utf-8")
    navigation_handler = worker.split("async function handleNavigationRequest", 1)[1].split(
        "function offlineNavigationResponse", 1
    )[0]
    runtime_cache_policy = worker.split("function isPublicRuntimeCacheableRequest", 1)[1].split(
        "function shouldCacheResponse", 1
    )[0]
    media_handler = worker.split("async function handleMediaRequest", 1)[1].split(
        "function isMediaRequest", 1
    )[0]
    media_classifier = worker.split("function isMediaRequest", 1)[1].split(
        "async function cacheWithQuotaHandling", 1
    )[0]

    assert 'if (request.mode === "navigate") return false;' in worker
    assert 'cacheControl.toLowerCase().includes("no-store")' in worker
    assert 'cacheControl.toLowerCase().includes("private")' in worker
    assert "cacheMobileNavigationPath" not in worker
    assert "cacheMobileNavigationResponse" not in worker
    assert "caches.match" not in navigation_handler
    assert "cache.put" not in navigation_handler
    assert "if (url.search)" in runtime_cache_policy
    assert "if (url.search)" in media_classifier
    assert "shouldCacheResponse(request, response)" in media_handler
    assert "if (!response.ok)" not in media_handler
