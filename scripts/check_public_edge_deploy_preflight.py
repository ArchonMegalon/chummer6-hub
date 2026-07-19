#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack, contextmanager
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    # Isolated-mode deploys do not inherit the repository root or PYTHONPATH.
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.strict_json_contract import (
        StrictJsonContractError,
        canonical_json_bytes,
        strict_json_object as decode_strict_json_object,
    )
    from scripts.verify_workspace_restore_receipts import check_local_release_proof
    from scripts.release.verify_public_projection import (
        ProjectionBlocked as PublicProjectionBlocked,
        resolve_current_snapshot,
    )
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from strict_json_contract import (
        StrictJsonContractError,
        canonical_json_bytes,
        strict_json_object as decode_strict_json_object,
    )
    from verify_workspace_restore_receipts import check_local_release_proof
    from release.verify_public_projection import (
        ProjectionBlocked as PublicProjectionBlocked,
        resolve_current_snapshot,
    )

try:
    import fcntl
except ImportError:  # pragma: no cover - the deploy lane is POSIX; unsupported hosts fail closed.
    fcntl = None  # type: ignore[assignment]

try:
    import resource
except ImportError:  # pragma: no cover - the deploy lane is Linux; unsupported hosts fail closed.
    resource = None  # type: ignore[assignment]


LOCK_PATTERNS = [
    "build-chummer6-linux",
    "Chummer.Presentation",
    "Chummer.Play",
    "/Roslyn/bincore/csc",
    "docker compose",
    "docker-compose",
]
STALE_LOOKING_SECONDS = 2 * 60 * 60
AUTO_IGNORE_STALE_FOREIGN_LOCK_SECONDS = 24 * 60 * 60
MAX_PUBLIC_PWA_PROOF_FAILURES = 16
MAX_PUBLIC_PWA_PROOF_DETAIL_CHARS = 320
MAX_PUBLIC_PWA_PROOF_RECEIPT_BYTES = 256 * 1024
MAX_PUBLIC_PWA_IDENTITY_FILE_BYTES = 2 * 1024 * 1024
MAX_PUBLIC_PWA_SNAPSHOT_MANIFEST_BYTES = 256 * 1024
MAX_PUBLIC_PWA_JSON_INPUT_BYTES = 2 * 1024 * 1024
MAX_PUBLIC_PWA_TEXT_INPUT_BYTES = 4 * 1024 * 1024
MAX_PUBLIC_PWA_BINARY_INPUT_BYTES = 8 * 1024 * 1024
MAX_PUBLIC_PWA_TOTAL_INPUT_BYTES = 64 * 1024 * 1024
MAX_OVERLAY_BUILD_INFO_BYTES = 1024 * 1024
MAX_RUNTIME_PROOF_BIND_BYTES = 2 * 1024 * 1024
MAX_RELEASE_CHANNEL_RECEIPT_BYTES = 2 * 1024 * 1024
RUNTIME_PROOF_MAX_AGE_SECONDS = 24 * 60 * 60
RUNTIME_PROOF_MAX_FUTURE_SKEW_SECONDS = 5 * 60
MAX_RUNTIME_PROOF_FAILURES = 16
MAX_RUNTIME_PROOF_DETAIL_CHARS = 320
RUNTIME_PROOF_RELEASE_CHANNEL_PATH = (
    "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
)
RELEASE_CHANNEL_BINDING_FIELDS = (
    "channelId",
    "channel",
    "version",
    "releaseVersion",
    "rolloutState",
    "supportabilityState",
    "publishedAt",
)
PUBLIC_PWA_PROOF_TIMEOUT_SECONDS = 20.0
PUBLIC_PWA_CHILD_ADDRESS_SPACE_BYTES = 512 * 1024 * 1024
PUBLIC_PWA_CHILD_FILE_BYTES = 16 * 1024 * 1024
PUBLIC_PWA_CHILD_CPU_SECONDS = 15
PUBLIC_PWA_CHILD_OPEN_FILES = 128
PUBLIC_PWA_CHILD_RESOURCE_LIMITS = (
    ("RLIMIT_AS", PUBLIC_PWA_CHILD_ADDRESS_SPACE_BYTES),
    ("RLIMIT_CPU", PUBLIC_PWA_CHILD_CPU_SECONDS),
    ("RLIMIT_FSIZE", PUBLIC_PWA_CHILD_FILE_BYTES),
    ("RLIMIT_NOFILE", PUBLIC_PWA_CHILD_OPEN_FILES),
)
PUBLIC_PWA_POLICY_ID = "chummer.public-play-pwa-mirror.v1"
PUBLIC_PWA_EXPECTED_ASSET_COUNT = 12
PUBLIC_PWA_EXPECTED_DEPENDENCY_COUNT = 4
PUBLIC_PWA_ASSET_DIGEST_INVENTORY_CONTRACT = "chummer.public_pwa_asset_digest_inventory.v1"
PUBLIC_PWA_ASSET_DIGEST_INVENTORY_COUNT = 14
RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
PUBLIC_PWA_PROOF_AUTHORITY_CONTRACT = "chummer.public-pwa-proof-authority.v1"
PUBLIC_PWA_PROOF_AUTHORITY_RELATIVE_PATH = "Chummer.Run.Api/public-pwa-proof-authority.json"
PUBLIC_PWA_PROOF_AUTHORITY_ROOT = RUN_SERVICES_ROOT
PUBLIC_PWA_PROOF_IDENTITY_PATHS = {
    "verifier": "scripts/verify_public_pwa_static_assets.py",
    "generator": "scripts/generate_public_play_worker_projection.py",
    "policy": "Chummer.Run.Api/play-pwa-required-inventory.json",
}
PUBLIC_PWA_PROOF_AUTHORITY_FIELDS = {
    "verifier": ("verifierPath", "verifierSha256"),
    "generator": ("generatorPath", "generatorSha256"),
    "policy": ("inventoryPath", "inventorySha256"),
}
PUBLIC_PWA_INPUT_SNAPSHOT_CONTRACT = "chummer.public-pwa-proof-input-snapshot.v1"
PUBLIC_PWA_FIXED_RUN_INPUTS = {
    "scripts/verify_public_pwa_static_assets.py",
    "scripts/generate_public_play_worker_projection.py",
    "scripts/validate_public_pwa_proof_authority.py",
    "Chummer.Run.Api/Dockerfile",
    "Chummer.Run.Api/public-pwa-proof-authority.json",
    "Chummer.Run.Api/play-pwa-required-inventory.json",
    "Chummer.Run.Api/play-pwa-mirrors.json",
    "Chummer.Run.Api/play-worker-projection.json",
    "Chummer.Run.Api/service-worker.public-edge.template.js",
    "Chummer.Run.Api/Services/PublicPlayProxyGateway.cs",
    "docker-compose.public-edge.yml",
    "Chummer.Run.Api/wwwroot/js/mobile-app-handoff.js",
    "Chummer.Run.Api/wwwroot/manifest.webmanifest",
}
PUBLIC_PWA_ASSET_INPUTS: tuple[tuple[str, str], ...] = (
    ("src/Chummer.Play.Web/wwwroot/mobile-install-shell.js", "Chummer.Run.Api/wwwroot/mobile-install-shell.js"),
    ("src/Chummer.Play.Web/wwwroot/mobile.css", "Chummer.Run.Api/wwwroot/mobile.css"),
    ("src/Chummer.Play.Web/wwwroot/manifest.webmanifest", "Chummer.Run.Api/wwwroot/manifest.play.webmanifest"),
    ("src/Chummer.Play.Web/wwwroot/manifest.player.webmanifest", "Chummer.Run.Api/wwwroot/manifest.player.webmanifest"),
    ("src/Chummer.Play.Web/wwwroot/manifest.gm.webmanifest", "Chummer.Run.Api/wwwroot/manifest.gm.webmanifest"),
    ("src/Chummer.Play.Web/wwwroot/manifest.observer.webmanifest", "Chummer.Run.Api/wwwroot/manifest.observer.webmanifest"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-192.png", "Chummer.Run.Api/wwwroot/icons/icon-192.png"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-512.png", "Chummer.Run.Api/wwwroot/icons/icon-512.png"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-192.svg", "Chummer.Run.Api/wwwroot/icons/icon-192.svg"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-512.svg", "Chummer.Run.Api/wwwroot/icons/icon-512.svg"),
    ("src/Chummer.Play.Web/wwwroot/mobile/service-worker.js", "Chummer.Run.Api/wwwroot/mobile/service-worker.js"),
    ("src/Chummer.Play.Web/wwwroot/service-worker.js", "Chummer.Run.Api/wwwroot/service-worker.js"),
)
SEALED_PYTHON_PROGRAM_WRAPPER = """
import sys

if not (
    sys.flags.isolated == 1
    and sys.flags.no_site == 1
    and sys.flags.ignore_environment == 1
    and sys.flags.safe_path
):
    raise SystemExit("public PWA verifier requires isolated, no-site, environment-ignoring, safe-path Python")

import hashlib
import os
import stat

descriptor = int(sys.argv[1])
expected_sha256 = sys.argv[2]
synthetic_file = sys.argv[3]
workspace_descriptor = int(sys.argv[4])
workspace_device = int(sys.argv[5])
workspace_inode = int(sys.argv[6])
workspace_metadata = os.fstat(workspace_descriptor)
if not stat.S_ISDIR(workspace_metadata.st_mode):
    raise SystemExit("public PWA snapshot workspace descriptor is not a directory")
if (workspace_metadata.st_dev, workspace_metadata.st_ino) != (workspace_device, workspace_inode):
    raise SystemExit("public PWA snapshot workspace descriptor identity mismatch")
os.fchdir(workspace_descriptor)
cwd_metadata = os.stat(".", follow_symlinks=False)
if (cwd_metadata.st_dev, cwd_metadata.st_ino) != (workspace_device, workspace_inode):
    raise SystemExit("public PWA snapshot workspace changed during descriptor binding")
os.lseek(descriptor, 0, os.SEEK_SET)
chunks = []
while True:
    chunk = os.read(descriptor, 1024 * 1024)
    if not chunk:
        break
    chunks.append(chunk)
program_bytes = b"".join(chunks)
actual_sha256 = hashlib.sha256(program_bytes).hexdigest()
if actual_sha256 != expected_sha256:
    raise SystemExit("sealed public PWA verifier digest mismatch")
sys.argv = [synthetic_file, *sys.argv[7:]]
namespace = {
    "__name__": "__main__",
    "__file__": synthetic_file,
    "__package__": None,
    "__builtins__": __builtins__,
}
exec(compile(program_bytes, synthetic_file, "exec"), namespace, namespace)
""".strip()
DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT = RUN_SERVICES_ROOT / ".state" / "public-edge-portal-overlay" / "app"
PUBLIC_EDGE_CANONICAL_RUN_SERVICES_ROOT = Path(
    "/docker/chummercomplete/chummer.run-services"
)
PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT = (
    PUBLIC_EDGE_CANONICAL_RUN_SERVICES_ROOT
    / ".codex-studio"
    / "published"
)
PUBLIC_EDGE_RUNTIME_PROOF_OUTPUT_NAME = "HUB_LOCAL_RELEASE_PROOF.generated.json"
PUBLIC_EDGE_RUNTIME_PROOF_BIND_MODE = 0o644
PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {
    "public_edge_main": WORKSPACE_ROOT / "chummer.run-services-public-edge-main",
    "participate_main": WORKSPACE_ROOT / "chummer.run-services-participate-main",
}
PUBLIC_EDGE_OPERATIONAL_MIRROR_SYNC_CHECK_COMMAND = (
    "python3 scripts/sync_public_edge_operational_mirrors.py"
)
PUBLIC_EDGE_OPERATIONAL_MIRROR_SYNC_APPLY_COMMAND = (
    "python3 scripts/sync_public_edge_operational_mirrors.py --apply"
)
PUBLIC_EDGE_STATUS_VIEW_RELATIVE_PATH = Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Status.cshtml"
PUBLIC_EDGE_DOWNLOADS_VIEW_RELATIVE_PATH = Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Downloads.cshtml"
PUBLIC_EDGE_LANDING_VIEW_RELATIVE_PATH = Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Landing.cshtml"
PUBLIC_EDGE_HOME_VIEW_RELATIVE_PATH = Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Home.cshtml"
PUBLIC_EDGE_HORIZONS_VIEW_RELATIVE_PATH = Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Horizons.cshtml"
PUBLIC_EDGE_STATUS_CONTROLLER_RELATIVE_PATH = Path("Chummer.Run.Api") / "Controllers" / "PublicLandingController.cs"
PUBLIC_EDGE_SERVICE_WORKER_RELATIVE_PATH = Path("Chummer.Run.Api") / "wwwroot" / "service-worker.js"
PUBLIC_EDGE_STATUS_CONTROLLER_NEEDLE = 'BuildPublicOrAuthenticatedChromeAsync("Status", "Current Chummer release status.", "/status", cancellationToken)'
PUBLIC_EDGE_STALE_STATUS_CONTROLLER_NEEDLE = 'BuildPublicOrAuthenticatedChromeAsync("Updated", "Current Chummer release status.", "/status", cancellationToken)'
PUBLIC_EDGE_OPERATIONAL_MIRROR_EXACT_PATH_SPECS: tuple[tuple[str, Path, str, str], ...] = (
    ("statusView", PUBLIC_EDGE_STATUS_VIEW_RELATIVE_PATH, "status view", "public_edge_operational_mirror_status_view"),
    ("downloadsView", PUBLIC_EDGE_DOWNLOADS_VIEW_RELATIVE_PATH, "downloads view", "public_edge_operational_mirror_downloads_view"),
    ("landingView", PUBLIC_EDGE_LANDING_VIEW_RELATIVE_PATH, "landing view", "public_edge_operational_mirror_landing_view"),
    ("homeView", PUBLIC_EDGE_HOME_VIEW_RELATIVE_PATH, "home view", "public_edge_operational_mirror_home_view"),
    ("horizonsView", PUBLIC_EDGE_HORIZONS_VIEW_RELATIVE_PATH, "horizons view", "public_edge_operational_mirror_horizons_view"),
    ("publicLandingController", PUBLIC_EDGE_STATUS_CONTROLLER_RELATIVE_PATH, "public landing controller", "public_edge_operational_mirror_status_controller"),
    ("serviceWorker", PUBLIC_EDGE_SERVICE_WORKER_RELATIVE_PATH, "service worker", "public_edge_operational_mirror_service_worker"),
)
REPO_SCOPE_MARKERS = {
    str(RUN_SERVICES_ROOT),
    str(WORKSPACE_ROOT / "chummer6-ui"),
    str(WORKSPACE_ROOT / "chummer6-ui-finish"),
    str(WORKSPACE_ROOT / "chummer-presentation"),
    str(WORKSPACE_ROOT / "chummer-presentation-clean"),
}
DOTNET_BUILD_VERBS_RE = re.compile(r"(?:^|\s)dotnet\s+(build|msbuild|pack|publish|restore|test)\b", re.IGNORECASE)
DOTNET_RUN_RE = re.compile(r"(?:^|\s)dotnet\s+run\b", re.IGNORECASE)
PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS = {
    "docker-compose.public-edge.yml": (
        'profiles: ["play-private"]',
        'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"',
        'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"',
        "${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:-/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app}:/app:ro",
        'CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT: /public-projection',
        'CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_REQUIRED: "true"',
        "${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT:?Set the authenticated public projection snapshot root}:/public-projection:ro",
        "${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE:?Set the authenticated CURRENT Hub proof output}:/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json:ro",
    ),
    "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml": (
        "Sign in first",
        'data-mobile-app-handoff="build-mobile-app-handoff"',
        'data-mobile-app-handoff="mobile-app-handoff"',
        'data-public-install-handoff="true"',
        "Target: MobileAppHandoffTarget.Build",
        "Target: MobileAppHandoffTarget.Play",
        'href="/mobile/player"',
        'data-analytics-event="@playAnalyticsEvent"',
        "#turn-runsite-card",
        'const normalizedHash = window.location.hash.split("?")[0];',
        'window.location.replace(`/mobile/player${normalizedHash}`);',
    ),
    "Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml": (
        'data-downloads-release-version="@ManifestVersionText(Model.Manifest)"',
        "ManifestVersionText",
    ),
    "Chummer.Run.Api/Views/PublicLanding/Status.cshtml": (
        'data-downloads-release-version="@ManifestVersionText(Model.Manifest)"',
        "PublicStatusText",
        'aria-label="Status next actions"',
        'href="/downloads"',
        'href="/help"',
        'return humanized.Replace("Open help", "Use Help", StringComparison.OrdinalIgnoreCase);',
    ),
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": (
        "public IActionResult PlayProjectionPage()",
        "ResolveCanonicalPlayRoleFromQuery(Request.Query)",
        'return Redirect($"/mobile/{canonicalRole}");',
        '[HttpGet("/jammer")]',
        '[HttpHead("/jammer")]',
        "public IActionResult PlayerProjectionAlias()",
        'RedirectToPrivateMobileAlias("/mobile/player")',
        'RedirectToPrivateMobileAlias("/mobile/gm")',
        'RedirectToPrivateMobileAlias("/mobile/observer")',
        'return Redirect($"{targetPath}#");',
        '"game-master"',
        '"runner"',
        '"spectator"',
        "BuildMobileInstallRoleProfile",
        'InstallTargetPath: "/mobile/player"',
        'InstallTargetPath: "/mobile/gm"',
        'InstallTargetPath: "/mobile/observer"',
    ),
    "Chummer.Run.Api/ViewModels/SiteViewModels.cs": (
        "MobileInstallRoleProfileViewModel",
        "PurposeHeading",
        "PrivacyHeading",
        "AuthorityHeading",
        "InstallTargetPath",
        "QrAriaLabel",
    ),
    "Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml": (
        'data-install-role="@roleProfile.RoleKey"',
        'data-mobile-app-path="@roleProfile.InstallTargetPath"',
        "data-mobile-app-inline-qr",
        'data-role-capabilities="@roleProfile.RoleKey"',
        'data-role-privacy-warning="@roleProfile.RoleKey"',
        'data-role-authority-warning="@roleProfile.RoleKey"',
    ),
    "Chummer.Run.Api/Services/ReadyForTonightService.cs": (
        "playtime_tools",
        "inventory",
        "health",
        "ammo",
        "modifiers",
        "quick_rolls",
        "living_world",
        'frontdoor_launch_route = "/mobile/player"',
        "role_routes = new[]",
        'route = "/mobile/player"',
        'route = "/mobile/gm"',
        'manifest_path = "/manifest.player.webmanifest"',
        'manifest_path = "/manifest.gm.webmanifest"',
        'manifest_start_url = "/mobile/player"',
        'manifest_start_url = "/mobile/gm"',
    ),
    "Chummer.Run.Api/Views/Shared/_Layout.cshtml": (
        "Sign in first",
        "site-open-chummer-menu__button--disabled",
    ),
    "Chummer.Run.Api/wwwroot/manifest.json": (
        "Installable public Chummer Play shell. Sign in and use a trusted table invitation for live sessions.",
        '"start_url": "/mobile/player"',
        '"scope": "/mobile/"',
    ),
    "Chummer.Run.Api/wwwroot/site.webmanifest": (
        "Installable public Chummer Play shell. Sign in and use a trusted table invitation for live sessions.",
        '"start_url": "/mobile/player"',
        '"scope": "/mobile/"',
    ),
    "Chummer.Run.Api/wwwroot/manifest.webmanifest": (
        "Installable public Chummer Play shell. Sign in and use a trusted table invitation for live sessions.",
        '"start_url": "/mobile/player"',
        '"scope": "/mobile/"',
    ),
    "Chummer.Run.Api/wwwroot/service-worker.js": (
        'const CACHE_VERSION = "v19";',
        'const CACHE_CONTRACT = "run-api-projection-v2";',
        "const CRITICAL_SHELL_ASSETS = [",
        '"/manifest.play.webmanifest"',
        "play_public_route_network_unavailable",
        "event.waitUntil(precacheCriticalShell());",
    ),
    "Chummer.Run.Api/service-worker.public-edge.template.js": (
        "Deterministic public-edge projection template",
        'const CACHE_CONTRACT = "run-api-projection-v2";',
        "play_public_route_network_unavailable",
    ),
    "Chummer.Run.Api/play-worker-projection.json": (
        '"contract": "play-root-worker-public-edge-projection-v2"',
        '"sourceSha256"',
        '"templateSha256"',
        '"requiredInventory": "Chummer.Run.Api/play-pwa-required-inventory.json"',
        '"requiredInventorySha256"',
        '"requiredSourceMarkers"',
        '"forbiddenProjectionMarkers"',
    ),
    "Chummer.Run.Api/play-pwa-required-inventory.json": (
        '"contract": "play-install-mirror-required-inventory-v2"',
        '"policyId": "chummer.public-play-pwa-mirror.v1"',
        '"sourceRepository": "../chummer-play"',
        '"kind": "exact"',
        '"kind": "transform"',
        '"role": "root_worker"',
        '"role": "generator_script"',
        '"role": "projection_config"',
        '"role": "projection_template"',
    ),
    "Chummer.Run.Api/public-pwa-proof-authority.json": (
        '"contractName": "chummer.public-pwa-proof-authority.v1"',
        '"policyId": "chummer.public-play-pwa-mirror.v1"',
        '"assetPolicyCount": 12',
        '"dependencyPolicyCount": 4',
        '"verifierPath": "scripts/verify_public_pwa_static_assets.py"',
        '"generatorPath": "scripts/generate_public_play_worker_projection.py"',
        '"inventoryPath": "Chummer.Run.Api/play-pwa-required-inventory.json"',
    ),
    "Chummer.Run.Api/play-pwa-mirrors.json": (
        '"contract": "play-install-mirror-v5"',
        '"inventoryContract": "play-install-mirror-required-inventory-v2"',
        '"policyId": "chummer.public-play-pwa-mirror.v1"',
        '"assetPolicyCount": 12',
        '"dependencyPolicyCount": 4',
        '"inventoryPath": "Chummer.Run.Api/play-pwa-required-inventory.json"',
        '"contract": "play-root-worker-projection-generator-v1"',
        '"command": "python3 scripts/generate_public_play_worker_projection.py"',
        '"dependencies"',
        '"scriptSha256"',
        '"configSha256"',
        '"templateSha256"',
    ),
    "scripts/generate_public_play_worker_projection.py": (
        'GENERATOR_CONTRACT = "play-root-worker-projection-generator-v1"',
        'MIRROR_CONTRACT = "play-install-mirror-v5"',
        'INVENTORY_CONTRACT = "play-install-mirror-required-inventory-v2"',
        'POLICY_ID = "chummer.public-play-pwa-mirror.v1"',
        "require_digest(source, config.get(\"sourceSha256\"), label=\"source worker\")",
        "require_markers(",
        "projected worker differs from deterministic output",
        "mirror contract differs from deterministic output",
    ),
    "scripts/validate_public_pwa_proof_authority.py": (
        'CONTRACT_NAME = "chummer.public-pwa-proof-authority.v1"',
        'POLICY_ID = "chummer.public-play-pwa-mirror.v1"',
        "object_pairs_hook=reject_duplicates",
        "is not canonical UTF-8 JSON",
        "authority fields drifted from the closed contract",
        "authority {field} does not match its exact input",
        "def validate_inventory_contract",
        "def validate_projection_contract",
        "def validate_mirror_contract",
        "required inventory ordered asset policy drifted",
        "mirror generator dependency set is not closed",
        "changed while it was read",
        'RECEIPT_CONTRACT_NAME = "chummer.public-pwa-proof-authority-receipt.v1"',
        "def write_atomic_canonical_receipt",
        "receipt output requires isolated, no-site, environment-ignoring, safe-path Python",
    ),
    "Chummer.Run.Api/Program.cs": (
        "TryResolveRoleAliasRedirectPath",
        'path.Equals("/jammer", StringComparison.OrdinalIgnoreCase)',
        'redirectPath = "/mobile/player";',
        'redirectPath = "/mobile/gm";',
        'redirectPath = "/mobile/observer";',
        'context.Response.Headers["Referrer-Policy"] = "no-referrer";',
        'context.Response.Headers.CacheControl = "private, no-store, no-cache, max-age=0";',
        'context.Response.Redirect($"{redirectPath}#", permanent: false);',
        "IPublicPlayPrivateRouteDelegator",
        "HubReadyResponse combinedReport = HubReadyResponse.Create(",
        "PortalDeploymentIdentityReadiness deploymentIdentity = deploymentIdentityReadiness.Evaluate();",
        'value.Equals("/js/mobile-app-handoff.js", StringComparison.OrdinalIgnoreCase)',
        'requestPath.Value?.EndsWith(".js", StringComparison.OrdinalIgnoreCase)',
        'fileContext.Context.Response.ContentType = "application/javascript; charset=utf-8";',
        "PublicProjectionProofRequestPathPolicy.Evaluate(context.Request)",
        "PublicProjectionProofRequestPathPolicy.IsCanonical(path)",
    ),
    "Chummer.Run.Api/Services/PublicProjectionProofRequestPathPolicy.cs": (
        "PublicProjectionProofRequestPathDisposition.RejectVariant",
        '"/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"',
        '"/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"',
        "Uri.UnescapeDataString(decoded)",
        "decoded.Replace('\\\\', '/')",
    ),
    "Chummer.Run.Api/Services/PublicProjectionSnapshotService.cs": (
        "PublicProjectionDescriptorReader.Open(root)",
        "descriptorReader.ReadRootFile(",
        "snapshot.ReadFile(",
        "snapshot.VerifyPathIdentity()",
        "descriptorReader.VerifyRootPathIdentity()",
    ),
    "Chummer.Run.Api/Services/ReleaseUploadAuthorityHandoffBuilder.cs": (
        "RequireCanonicalStringArrayWithOptionalAlias(",
        '"proof_routes"',
        '"proofRoutes"',
        "aliases disagree",
    ),
    "Chummer.Run.Api/Services/PublicProjectionDescriptorReader.cs": (
        "LinuxNative.openat(",
        "LinuxNative.OpenNoFollow",
        "LinuxNative.statx(",
        "metadata.LinkCount != 1",
        "OpenAbsoluteDirectory(",
    ),
    "Chummer.Run.Api/Dockerfile": (
        "FROM python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28 AS public-pwa-proof",
        "WORKDIR /proof",
        "RUN [\"/usr/local/bin/python3\", \"-I\", \"-S\"",
        "\"--receipt\", \"/proof/public-pwa-proof-authority.receipt.json\"",
        "COPY --from=public-pwa-proof /proof/public-pwa-proof-authority.receipt.json /tmp/public-pwa-proof-authority.receipt.json",
        "COPY --from=run-services-source Chummer.Run.Api/",
        "COPY --from=run-services-source scripts/generate_public_play_worker_projection.py scripts/generate_public_play_worker_projection.py",
        "COPY --from=run-services-source scripts/verify_public_pwa_static_assets.py scripts/verify_public_pwa_static_assets.py",
        "COPY --from=run-services-source scripts/validate_public_pwa_proof_authority.py scripts/validate_public_pwa_proof_authority.py",
        "COPY --from=run-services-source .codex-design/",
        "COPY --from=run-services-source --chmod=0555 scripts/initialize-public-edge-volumes.sh /usr/local/libexec/chummer/initialize-public-edge-volumes.sh",
        "RUN rm -rf /src/chummer.run-services/Chummer.Run.Api/bin /src/chummer.run-services/Chummer.Run.Api/obj",
        'grep -Fq \'const CACHE_VERSION = "v19";\'',
        'grep -Fq \'const CACHE_CONTRACT = "run-api-projection-v2";\'',
        "grep -Fq 'const CRITICAL_SHELL_ASSETS = ['",
        "! grep -Fq 'self.skipWaiting()'",
        "! grep -Fq 'self.clients.claim()'",
        "grep -Fq 'play_public_route_network_unavailable'",
        "mkdir -p /app/state",
    ),
    ".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml": (
        "owner: chummer6-design",
        "purpose: Shared taxonomy for ProductLift categories",
        "key: mobile_companion",
    ),
    ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml": (
        "- path: /jammer",
        "title: Jammer Companion alias",
        "guest_fallback: /jammer",
        "placeholder_requirements: no-authority Jammer Companion alias only",
    ),
    ".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml": (
        "owner: chummer6-design",
        "purpose: Machine-readable registry for public feedback, roadmap, changelog, and public-content optimization surfaces.",
        "key: productlift_public_feedback",
    ),
    ".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md": (
        "# Public signal feedback, roadmap, and changelog bridge",
        "- `/feedback` projects public ideas, votes, comments, categories, and support-boundary copy.",
    ),
    ".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md": (
        "# Public signal to canon pipeline",
        "Public signal is input. Canon is decided by Chummer.",
    ),
    ".codex-design/product/ORIGIN_BOOK_STUDIO.md": (
        "# ORIGIN BOOK STUDIO",
        "Chummer owns facts, legality, lineage, approvals, and exports.",
    ),
    ".codex-design/product/public-guides/chummer6-quickstart.md": (
        "# Chummer6 Quickstart Guide",
        "## Document boundary",
    ),
}
PUBLIC_EDGE_REQUIRED_OVERLAY_MARKERS = {
    ".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS[".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml"],
    ".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS[".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml"],
    ".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS[".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md"],
    ".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS[".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md"],
    ".codex-design/product/ORIGIN_BOOK_STUDIO.md": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS[".codex-design/product/ORIGIN_BOOK_STUDIO.md"],
    ".codex-design/product/public-guides/chummer6-quickstart.md": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS[".codex-design/product/public-guides/chummer6-quickstart.md"],
    ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json": (
        '"contractName": "chummer.public_edge_portal_overlay_publish.v1"',
        '"status": "pass"',
        '"activationStatus": "activated"',
        '"landingMarkerStatus": "pass"',
        '"landingHasTurnAnchor": true',
        '"landingHasTurnAnchorRedirect": true',
        '"landingHasBuildPublicInstallHandoff": true',
        '"landingHasPlayPublicInstallHandoff": true',
        '"landingRetiredMarkersAbsent": true',
        '"landingBrowserRedirectStatus": "pass"',
        '"landingBrowserRedirectExpectedPath": "/mobile/player"',
        '"landingBrowserRedirectExpectedHash": "#turn-runsite-card"',
        '"landingBrowserRedirectExpectedQuery": ""',
        '"landingBrowserRedirectFinalQuery": ""',
        '"landingBrowserRedirectQueryDropped": true',
        '"landingBrowserRedirectPathMatches": true',
        '"landingBrowserRedirectHashMatches": true',
        '"landingMissingMarkerCount": 0',
        '"landingForbiddenMarkerCount": 0',
    ),
    "wwwroot/manifest.json": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS["Chummer.Run.Api/wwwroot/manifest.json"],
    "wwwroot/site.webmanifest": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS["Chummer.Run.Api/wwwroot/site.webmanifest"],
    "wwwroot/manifest.webmanifest": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS["Chummer.Run.Api/wwwroot/manifest.webmanifest"],
    "wwwroot/service-worker.js": PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS["Chummer.Run.Api/wwwroot/service-worker.js"],
}
PUBLIC_EDGE_FORBIDDEN_SOURCE_MARKERS = {
    "docker-compose.public-edge.yml": (
        "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED",
        "${CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED",
        "CHUMMER_PUBLIC_PLAY_PROXY_URL:",
        "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY:",
    ),
    "Chummer.Run.Api/Program.cs": (
        "IsStrictPlayPwaProxyRequest",
        "WritePlayPwaProxyUnavailableAsync",
        "gateway.TryHandleAsync",
        "string destination = context.Request.QueryString.HasValue",
    ),
    "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml": (
        "site-open-chummer-menu__button--disabled",
        'data-disabled-target="/mobile/player"',
        'data-sign-in-href="/login?next=%2Fmobile%2Fplayer"',
    ),
    "Chummer.Run.Api/wwwroot/service-worker.js": (
        "self.skipWaiting()",
        "self.clients.claim()",
        '"/mobile-turn-companion.js"',
    ),
    "Chummer.Run.Api/Dockerfile": (
        'grep -q \'const CACHE_NAME = "chummer-public-v4";\'',
        "! grep -q 'play-shell-v'",
        'test "$(wc -l < public-pwa-proof-authority.json',
        "for authority_key in contractName policyId assetPolicyCount",
        'grep -Fq "\\"inventorySha256\\": \\"${inventory_sha}\\"" public-pwa-proof-authority.json',
        'grep -Fq "\\"generatorSha256\\": \\"${generator_sha}\\"" public-pwa-proof-authority.json',
        'grep -Fq "\\"verifierSha256\\": \\"${verifier_sha}\\"" public-pwa-proof-authority.json',
        'grep -Fq \'"contract": "play-install-mirror-required-inventory-v2"\' play-pwa-required-inventory.json',
        'grep -Fq \'"assetPolicyCount": 12\' play-pwa-mirrors.json',
        'grep -Fq \'"dependencyPolicyCount": 4\' play-pwa-mirrors.json',
        'grep -Fq "\\"templateSha256\\": \\"${template_sha}\\"" play-worker-projection.json',
        'grep -Fq "\\"projectionSha256\\": \\"${template_sha}\\"" play-pwa-mirrors.json',
    ),
}
PUBLIC_EDGE_FORBIDDEN_OVERLAY_MARKERS: dict[str, tuple[str, ...]] = {}
PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH = "Chummer.Run.Api/Dockerfile"
PUBLIC_EDGE_DOCKER_BUILD_STAGE = "build"
PUBLIC_EDGE_DOCKER_PROOF_STAGE = "public-pwa-proof"
PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE = "install-linking-postgres-tool-final"
PUBLIC_EDGE_DOCKER_FINAL_STAGE = "final"
PUBLIC_EDGE_DOCKER_BUILD_FROM = "FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build"
PUBLIC_EDGE_DOCKER_TOOL_FINAL_FROM = (
    "FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS install-linking-postgres-tool-final"
)
PUBLIC_EDGE_DOCKER_FINAL_FROM = "FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final"
PUBLIC_EDGE_DOCKER_STAGE_ORDER = (
    PUBLIC_EDGE_DOCKER_PROOF_STAGE,
    PUBLIC_EDGE_DOCKER_BUILD_STAGE,
    PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE,
    PUBLIC_EDGE_DOCKER_FINAL_STAGE,
)
PUBLIC_EDGE_DOCKER_NAMED_CONTEXTS_BY_STAGE = {
    PUBLIC_EDGE_DOCKER_PROOF_STAGE: frozenset({"run-services-source"}),
    PUBLIC_EDGE_DOCKER_BUILD_STAGE: frozenset(
        {"run-services-source", "fleet-media-factory-contracts"}
    ),
    PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE: frozenset(),
    PUBLIC_EDGE_DOCKER_FINAL_STAGE: frozenset(
        {"design-product", "run-services-source"}
    ),
}
PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE = {
    PUBLIC_EDGE_DOCKER_FINAL_STAGE: frozenset(
        {
            "COPY --from=run-services-source --chmod=0555 scripts/initialize-public-edge-volumes.sh /usr/local/libexec/chummer/initialize-public-edge-volumes.sh",
            "COPY --from=design-product products/chummer/ /app/.codex-design/product/",
        }
    ),
}
PUBLIC_EDGE_DOCKER_COPY_STAGE_REFERENCES_BY_STAGE = {
    PUBLIC_EDGE_DOCKER_PROOF_STAGE: frozenset(),
    PUBLIC_EDGE_DOCKER_BUILD_STAGE: frozenset({PUBLIC_EDGE_DOCKER_PROOF_STAGE}),
    PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE: frozenset({PUBLIC_EDGE_DOCKER_BUILD_STAGE}),
    PUBLIC_EDGE_DOCKER_FINAL_STAGE: frozenset({PUBLIC_EDGE_DOCKER_BUILD_STAGE}),
}
PUBLIC_EDGE_DOCKER_PYTHON_IMAGE = (
    "python:3.12-slim@sha256:"
    "c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28"
)
PUBLIC_EDGE_DOCKER_PROOF_RECEIPT = "/proof/public-pwa-proof-authority.receipt.json"
PUBLIC_EDGE_DOCKER_PROOF_COPY_INPUTS = (
    "scripts/validate_public_pwa_proof_authority.py",
    "scripts/verify_public_pwa_static_assets.py",
    "scripts/generate_public_play_worker_projection.py",
    "Chummer.Run.Api/public-pwa-proof-authority.json",
    "Chummer.Run.Api/play-pwa-required-inventory.json",
    "Chummer.Run.Api/play-pwa-mirrors.json",
    "Chummer.Run.Api/play-worker-projection.json",
    "Chummer.Run.Api/service-worker.public-edge.template.js",
    "Chummer.Run.Api/wwwroot/mobile-install-shell.js",
    "Chummer.Run.Api/wwwroot/mobile.css",
    "Chummer.Run.Api/wwwroot/manifest.play.webmanifest",
    "Chummer.Run.Api/wwwroot/manifest.player.webmanifest",
    "Chummer.Run.Api/wwwroot/manifest.gm.webmanifest",
    "Chummer.Run.Api/wwwroot/manifest.observer.webmanifest",
    "Chummer.Run.Api/wwwroot/icons/icon-192.png",
    "Chummer.Run.Api/wwwroot/icons/icon-512.png",
    "Chummer.Run.Api/wwwroot/icons/icon-192.svg",
    "Chummer.Run.Api/wwwroot/icons/icon-512.svg",
    "Chummer.Run.Api/wwwroot/mobile/service-worker.js",
    "Chummer.Run.Api/wwwroot/service-worker.js",
)
PUBLIC_EDGE_DOCKER_PROOF_RUN = (
    'RUN ["/usr/local/bin/python3", "-I", "-S", '
    '"scripts/validate_public_pwa_proof_authority.py", '
    '"--authority", "Chummer.Run.Api/public-pwa-proof-authority.json", '
    '"--verifier", "scripts/verify_public_pwa_static_assets.py", '
    '"--generator", "scripts/generate_public_play_worker_projection.py", '
    '"--inventory", "Chummer.Run.Api/play-pwa-required-inventory.json", '
    '"--mirror", "Chummer.Run.Api/play-pwa-mirrors.json", '
    '"--projection", "Chummer.Run.Api/play-worker-projection.json", '
    '"--template", "Chummer.Run.Api/service-worker.public-edge.template.js", '
    '"--receipt", "/proof/public-pwa-proof-authority.receipt.json"]'
)
PUBLIC_EDGE_DOCKER_PROOF_STAGE_INSTRUCTIONS = (
    f"FROM {PUBLIC_EDGE_DOCKER_PYTHON_IMAGE} AS {PUBLIC_EDGE_DOCKER_PROOF_STAGE}",
    "WORKDIR /proof",
    *(
        f"COPY --from=run-services-source {path} {path}"
        for path in PUBLIC_EDGE_DOCKER_PROOF_COPY_INPUTS
    ),
    PUBLIC_EDGE_DOCKER_PROOF_RUN,
)
PUBLIC_EDGE_DOCKER_STAGE_FROM_INSTRUCTIONS = (
    PUBLIC_EDGE_DOCKER_PROOF_STAGE_INSTRUCTIONS[0],
    PUBLIC_EDGE_DOCKER_BUILD_FROM,
    PUBLIC_EDGE_DOCKER_TOOL_FINAL_FROM,
    PUBLIC_EDGE_DOCKER_FINAL_FROM,
)
PUBLIC_EDGE_DOCKER_RECEIPT_COPY = (
    "COPY --from=public-pwa-proof "
    "/proof/public-pwa-proof-authority.receipt.json "
    "/tmp/public-pwa-proof-authority.receipt.json"
)
PUBLIC_EDGE_DOCKER_FINAL_PUBLISH_COPY = "COPY --from=build /app/publish ."
PUBLIC_EDGE_DOCKER_TOOL_PUBLISH_COPY = (
    "COPY --from=build /app/install-linking-postgres-tool ."
)
PUBLIC_EDGE_DOCKER_TOOL_PAYLOAD_MODE_RUN = (
    'RUN set -eu; link="$(find -P /app -xdev -type l -print -quit)"; '
    'test -z "$link"; find -P /app -xdev -type d -exec chmod 0755 {} +; '
    "find -P /app -xdev -type f -exec chmod 0644 {} +"
)
PUBLIC_EDGE_DOCKER_FINAL_PAYLOAD_MODE_RUN = (
    'RUN set -eu; link="$(find -P /app -xdev -type l -print -quit)"; '
    'test -z "$link"; find -P /app -xdev -type d -exec chmod 0755 {} +; '
    "find -P /app -xdev -type f -exec chmod 0644 {} +; mkdir -p /app/state; "
    'chown -R "${CHUMMER_RUNTIME_UID}:${CHUMMER_RUNTIME_GID}" /app/state; '
    "chmod -R go-rwx /app/state"
)
PUBLIC_EDGE_COMPOSE_RELATIVE_PATH = "docker-compose.public-edge.yml"
PUBLIC_EDGE_COMPOSE_PORTAL_SERVICE = "chummer-portal"
PUBLIC_EDGE_COMPOSE_BUILD_CONTEXT = (
    "${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-/docker/chummercomplete}"
)
PUBLIC_EDGE_COMPOSE_DOCKERFILE = (
    "${CHUMMER_RUN_SERVICES_CONTEXT_DIR:-chummer.run-services}/"
    "Chummer.Run.Api/Dockerfile"
)
PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS = {
    "run-services-source": (
        "${CHUMMER_RUN_SERVICES_SOURCE:-/docker/chummercomplete/chummer.run-services}"
    ),
    "fleet-media-factory-contracts": (
        "/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts"
    ),
    "design-product": "/docker/chummercomplete/chummer-design",
}
PUBLIC_EDGE_COMPOSE_BUILD_SERVICE_CONTRACTS = {
    PUBLIC_EDGE_COMPOSE_PORTAL_SERVICE: {
        "target": "",
        "namedContexts": PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS,
    },
    "chummer-install-linking-postgres-admin": {
        "target": PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE,
        "namedContexts": PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS,
    },
    "chummer-install-linking-postgres-import": {
        "target": PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE,
        "namedContexts": PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS,
    },
}
PUBLIC_EDGE_DOCKER_RESERVED_CONTEXT_NAMES = frozenset(
    {
        *PUBLIC_EDGE_DOCKER_STAGE_ORDER,
        "python:3.12-slim",
        PUBLIC_EDGE_DOCKER_PYTHON_IMAGE,
        "mcr.microsoft.com/dotnet/sdk:10.0",
        "mcr.microsoft.com/dotnet/aspnet:10.0",
        "docker/dockerfile:1.4",
    }
)
PUBLIC_EDGE_OVERLAY_SOURCE_FINGERPRINT_FILES = {
    "postdeployVerifier": Path("scripts") / "verify_public_edge_postdeploy_gate.py",
    "landing": Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Landing.cshtml",
    "downloads": Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Downloads.cshtml",
    "status": Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Status.cshtml",
    "program": Path("Chummer.Run.Api") / "Program.cs",
    "readyForTonight": Path("Chummer.Run.Api") / "Services" / "ReadyForTonightService.cs",
    "authController": Path("Chummer.Run.Api") / "Controllers" / "AuthController.cs",
    "billingAuthController": Path("Chummer.Run.Api") / "Controllers" / "BrilliantDirectoriesBillingController.cs",
    "authEntryView": Path("Chummer.Run.Api") / "Views" / "Auth" / "Entry.cshtml",
    "billingMembershipView": Path("Chummer.Run.Api") / "Views" / "Billing" / "Membership.cshtml",
    "authPolicy": Path("Chummer.Run.Api") / "Services" / "HubEmailSignInPolicy.cs",
    "siteViewModels": Path("Chummer.Run.Api") / "ViewModels" / "SiteViewModels.cs",
}
_OVERLAY_FINGERPRINT_MODULE: Any | None = None


def _is_local_scope(line: str) -> bool:
    lower_line = line.lower()
    return any(marker.lower() in lower_line for marker in REPO_SCOPE_MARKERS)


def _is_build_like_process(command: str, args: str, line: str) -> bool:
    lower_line = line.lower()
    lower_args = args.lower()
    lower_command = command.lower()
    if "docker compose" in lower_line or "docker-compose" in lower_line:
        return "--build" in lower_args and (" up " in lower_line or " build " in lower_line)
    if "build-chummer6-linux" in lower_line:
        return True
    if "/roslyn/bincore/csc" in lower_line:
        return True
    if lower_command == "dotnet":
        if DOTNET_BUILD_VERBS_RE.search(args):
            return True
        if DOTNET_RUN_RE.search(args) and "--no-build" not in lower_args:
            return True
    return False


def process_lines_from_system() -> list[str]:
    result = subprocess.run(
        ["ps", "-eo", "pid,ppid,stat,etime,comm,args", "--no-headers"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"ps failed: {detail}")
    return [line.rstrip() for line in result.stdout.splitlines() if line.strip()]


def parse_elapsed_seconds(elapsed: str) -> int | None:
    parts = elapsed.strip().split("-")
    days = 0
    time_part = parts[-1]
    if len(parts) == 2:
        try:
            days = int(parts[0])
        except ValueError:
            return None
    fields = time_part.split(":")
    try:
        if len(fields) == 3:
            hours, minutes, seconds = [int(field) for field in fields]
        elif len(fields) == 2:
            hours = 0
            minutes, seconds = [int(field) for field in fields]
        else:
            return None
    except ValueError:
        return None
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _stable_regular_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_nlink,
        stat.S_IMODE(metadata.st_mode),
    )


def _read_bounded_regular_file(path: Path, *, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise RuntimeError("JSON input byte limit must be positive")
    normalized = Path(os.path.abspath(os.fspath(path.expanduser())))
    before_path = normalized.lstat()
    if (
        not stat.S_ISREG(before_path.st_mode)
        or stat.S_ISLNK(before_path.st_mode)
        or before_path.st_nlink != 1
        or before_path.st_size > max_bytes
    ):
        raise RuntimeError("JSON input must be a bounded, regular, unaliased file")

    descriptor = os.open(
        normalized,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or _stable_regular_file_identity(before)
            != _stable_regular_file_identity(before_path)
        ):
            raise RuntimeError("JSON input changed before it was read")
        chunks: list[bytes] = []
        byte_count = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - byte_count))
            if not chunk:
                break
            chunks.append(chunk)
            byte_count += len(chunk)
            if byte_count > max_bytes:
                raise RuntimeError("JSON input exceeds its byte limit")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    if (
        _stable_regular_file_identity(before) != _stable_regular_file_identity(after)
        or byte_count != before.st_size
    ):
        raise RuntimeError("JSON input changed while it was read")
    after_path = normalized.lstat()
    if (
        not stat.S_ISREG(after_path.st_mode)
        or after_path.st_nlink != 1
        or _stable_regular_file_identity(after_path)
        != _stable_regular_file_identity(after)
    ):
        raise RuntimeError("JSON input pathname changed after it was read")
    return b"".join(chunks)


def load_json_file(
    path: Path,
    *,
    max_bytes: int = MAX_OVERLAY_BUILD_INFO_BYTES,
) -> dict[str, Any]:
    try:
        return strict_json_object(
            _read_bounded_regular_file(path, max_bytes=max_bytes),
            label=str(path),
        )
    except (OSError, RuntimeError):
        return {}


def load_overlay_fingerprint_module() -> Any:
    global _OVERLAY_FINGERPRINT_MODULE
    if _OVERLAY_FINGERPRINT_MODULE is not None:
        return _OVERLAY_FINGERPRINT_MODULE
    module_path = RUN_SERVICES_ROOT / "scripts" / "publish_public_edge_portal_overlay.py"
    spec = importlib.util.spec_from_file_location(
        "chummer_public_edge_overlay_fingerprint",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load overlay fingerprint implementation: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _OVERLAY_FINGERPRINT_MODULE = module
    return module


def overlay_source_fingerprint(source_root: Path) -> dict[str, Any]:
    return load_overlay_fingerprint_module().source_fingerprint(source_root)


def overlay_staged_payload_fingerprint(overlay_root: Path) -> dict[str, Any]:
    return load_overlay_fingerprint_module().staged_payload_fingerprint(overlay_root)


def matching_processes(process_lines: list[str]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    current_pid = str(os.getpid())
    for line in process_lines:
        parts = line.split(maxsplit=5)
        if len(parts) < 6:
            continue
        pid, ppid, stat, elapsed, command, args = parts
        if pid == current_pid:
            continue
        matched = [pattern for pattern in LOCK_PATTERNS if pattern in line]
        if not matched:
            continue
        if not _is_build_like_process(command, args, line):
            continue
        elapsed_seconds = parse_elapsed_seconds(elapsed)
        stale_looking = elapsed_seconds is not None and elapsed_seconds >= STALE_LOOKING_SECONDS and not stat.startswith("R")
        build_scope = "local" if _is_local_scope(line) else "foreign"
        matches.append(
            {
                "pid": pid,
                "ppid": ppid,
                "stat": stat,
                "elapsed": elapsed,
                "elapsedSeconds": "" if elapsed_seconds is None else str(elapsed_seconds),
                "command": command,
                "matchedPatterns": ", ".join(matched),
                "staleLooking": "true" if stale_looking else "false",
                "buildScope": build_scope,
                "args": args[:500],
            }
        )
    return matches


def resolve_default_source_root() -> Path:
    configured = (
        os.environ.get("CHUMMER_PUBLIC_EDGE_DEPLOY_REPO_ROOT")
        or os.environ.get("CHUMMER_RUN_SERVICES_SOURCE")
        or ""
    ).strip()
    return Path(configured).resolve() if configured else RUN_SERVICES_ROOT


def resolve_default_overlay_root() -> Path:
    configured = (os.environ.get("CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR") or "").strip()
    return Path(configured).resolve() if configured else DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT.resolve()


def _docker_from_instruction_parts(line: str) -> tuple[str, str]:
    match = re.fullmatch(
        r"FROM\s+([^\s]+)(?:\s+AS\s+([A-Za-z0-9_.-]+))?",
        line,
        flags=re.IGNORECASE,
    )
    if match is None:
        return "", ""
    return match.group(1), (match.group(2) or "").lower()


def _docker_logical_instructions(
    lines: list[str],
    *,
    first_line_number: int,
) -> tuple[list[tuple[int, str]], list[int]]:
    instructions: list[tuple[int, str]] = []
    malformed_continuations: list[int] = []
    pending_parts: list[str] = []
    pending_line_number = 0
    for line_number, raw_line in enumerate(lines, start=first_line_number):
        stripped = raw_line.strip()
        if not pending_parts and (not stripped or stripped.startswith("#")):
            continue
        if pending_parts and (not stripped or stripped.startswith("#")):
            malformed_continuations.append(pending_line_number)
            pending_parts = []
            pending_line_number = 0
            continue
        continued = raw_line.rstrip().endswith("\\")
        segment = raw_line.rstrip()
        if continued:
            segment = segment[:-1]
        if not pending_parts:
            pending_line_number = line_number
        pending_parts.append(segment)
        if continued:
            continue
        instructions.append((pending_line_number, "".join(pending_parts).strip()))
        pending_parts = []
        pending_line_number = 0
    if pending_parts:
        malformed_continuations.append(pending_line_number)
    return instructions, malformed_continuations


def _docker_copy_from_reference(line: str) -> tuple[str | None, bool]:
    match = re.match(r"COPY\s+(.+)", line, flags=re.IGNORECASE)
    if match is None:
        return None, False
    tokens = match.group(1).split()
    from_references: list[str] = []
    option_count = 0
    for token in tokens:
        if not token.startswith("--"):
            break
        option_count += 1
        lower_token = token.lower()
        if lower_token.startswith("--from="):
            reference = token.split("=", 1)[1]
            if not reference:
                return None, True
            from_references.append(reference)
        elif lower_token == "--from":
            return None, True
    positional_tokens = tokens[option_count:]
    if any("--from" in token.lower() for token in positional_tokens):
        return None, True
    if len(from_references) > 1:
        return None, True
    return (from_references[0] if from_references else None), False


def validate_public_pwa_docker_build_contract(path: Path) -> dict[str, Any]:
    failures: list[str] = []
    empty_result = {
        "status": "fail",
        "present": False,
        "proofStageCount": 0,
        "buildStageCount": 0,
        "toolFinalStageCount": 0,
        "finalStageCount": 0,
        "stageAliases": [],
        "stageDependencies": {},
        "copyFromReferences": [],
        "pythonInvocationCount": 0,
        "checks": {},
        "failures": ["Dockerfile is missing"],
    }
    if not path.is_file():
        return empty_result
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        return {
            **empty_result,
            "present": True,
            "failures": [f"Dockerfile could not be read as UTF-8: {exc}"],
        }

    lines = text.splitlines()
    exact_header = bool(lines) and lines[0] == "# syntax=docker/dockerfile:1.4"
    if not exact_header:
        failures.append(
            "Dockerfile must begin with the exact '# syntax=docker/dockerfile:1.4' directive"
        )

    late_directives = [
        line_number
        for line_number, line in enumerate(lines[1:], start=2)
        if re.fullmatch(
            r"\s*#\s*(?:syntax|escape|check)\s*=.*",
            line,
            flags=re.IGNORECASE,
        )
    ]
    if late_directives:
        failures.append("Dockerfile parser directives are forbidden after the exact header")

    heredoc_lines = [
        line_number
        for line_number, line in enumerate(lines, start=1)
        if "<<" in line and not line.lstrip().startswith("#")
    ]
    if heredoc_lines:
        failures.append("Dockerfile heredoc syntax is forbidden by the proof-stage contract")

    logical_instructions, malformed_continuations = _docker_logical_instructions(
        lines[1:],
        first_line_number=2,
    )
    if malformed_continuations:
        failures.append("Dockerfile contains an ambiguous or dangling line continuation")
    logical_instruction_text = [line for _, line in logical_instructions]
    stage_from_instructions = tuple(
        line
        for line in logical_instruction_text
        if re.match(r"FROM(?:\s|$)", line, flags=re.IGNORECASE)
    )
    exact_stage_headers = stage_from_instructions == PUBLIC_EDGE_DOCKER_STAGE_FROM_INSTRUCTIONS
    if not exact_stage_headers:
        failures.append("Dockerfile stage FROM instructions drifted from the exact contract")
    receipt_instruction_indexes = [
        index
        for index, line in enumerate(logical_instruction_text)
        if line == PUBLIC_EDGE_DOCKER_RECEIPT_COPY
    ]
    receipt_is_first_build_instruction = (
        len(receipt_instruction_indexes) == 1
        and receipt_instruction_indexes[0] > 0
        and logical_instruction_text[receipt_instruction_indexes[0] - 1]
        == PUBLIC_EDGE_DOCKER_BUILD_FROM
    )
    if not receipt_is_first_build_instruction:
        failures.append("exact proof receipt COPY must be the first build-stage instruction")

    instruction_lines = [line.strip() for line in lines[1:] if line.strip()]
    next_from_index = next(
        (
            index
            for index, line in enumerate(instruction_lines[1:], start=1)
            if re.match(r"FROM(?:\s|$)", line, flags=re.IGNORECASE)
        ),
        len(instruction_lines),
    )
    proof_stage_instructions = tuple(instruction_lines[:next_from_index])
    exact_proof_stage = (
        exact_header
        and proof_stage_instructions == PUBLIC_EDGE_DOCKER_PROOF_STAGE_INSTRUCTIONS
    )
    if not exact_proof_stage:
        failures.append(
            "first Docker stage must match the exact pinned public PWA proof-stage instruction whitelist"
        )

    current_stage = -1
    current_alias = ""
    proof_stage_count = 0
    build_stage_count = 0
    tool_final_stage_count = 0
    final_stage_count = 0
    stage_aliases: list[str] = []
    stage_index_by_alias: dict[str, int] = {}
    stage_dependencies: dict[str, set[str]] = {}
    copy_from_references: list[dict[str, Any]] = []
    malformed_copy_from_lines: list[int] = []
    unknown_copy_from_references: list[tuple[int, str]] = []
    invalid_named_context_copies: list[tuple[int, str, str]] = []
    named_context_copy_lines_by_stage: dict[str, list[str]] = {}
    invalid_copy_from_stages: list[tuple[int, str, str]] = []
    forward_copy_from_references: list[tuple[int, str, str]] = []
    derived_proof_stages: list[int] = []
    proof_alias_redefinitions: list[int] = []
    receipt_copy_stages: list[str] = []
    tool_publish_copy_stages: list[str] = []
    final_publish_copy_stages: list[str] = []
    tool_payload_mode_stages: list[str] = []
    final_payload_mode_stages: list[str] = []
    other_proof_copies: list[int] = []
    pre_stage_instructions: list[int] = []
    for line_number, line in logical_instructions:
        if re.match(r"FROM(?:\s|$)", line, flags=re.IGNORECASE):
            current_stage += 1
            image, alias = _docker_from_instruction_parts(line)
            current_alias = alias
            stage_aliases.append(alias)
            stage_dependencies.setdefault(alias, set())
            if alias and alias not in stage_index_by_alias:
                stage_index_by_alias[alias] = current_stage
            image_alias = image.lower()
            if image_alias in PUBLIC_EDGE_DOCKER_STAGE_ORDER:
                stage_dependencies[alias].add(image_alias)
            if alias == PUBLIC_EDGE_DOCKER_PROOF_STAGE:
                proof_stage_count += 1
                if current_stage != 0:
                    proof_alias_redefinitions.append(line_number)
            if alias == PUBLIC_EDGE_DOCKER_BUILD_STAGE:
                build_stage_count += 1
            if alias == PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE:
                tool_final_stage_count += 1
            if alias == PUBLIC_EDGE_DOCKER_FINAL_STAGE:
                final_stage_count += 1
            if current_stage > 0 and image.lower() == PUBLIC_EDGE_DOCKER_PROOF_STAGE:
                derived_proof_stages.append(line_number)
            continue
        if current_stage < 0:
            pre_stage_instructions.append(line_number)
        if line == PUBLIC_EDGE_DOCKER_RECEIPT_COPY:
            receipt_copy_stages.append(current_alias)
        elif "--from=public-pwa-proof" in line.lower():
            other_proof_copies.append(line_number)
        if line == PUBLIC_EDGE_DOCKER_TOOL_PUBLISH_COPY:
            tool_publish_copy_stages.append(current_alias)
        if line == PUBLIC_EDGE_DOCKER_FINAL_PUBLISH_COPY:
            final_publish_copy_stages.append(current_alias)
        if line == PUBLIC_EDGE_DOCKER_TOOL_PAYLOAD_MODE_RUN:
            tool_payload_mode_stages.append(current_alias)
        if line == PUBLIC_EDGE_DOCKER_FINAL_PAYLOAD_MODE_RUN:
            final_payload_mode_stages.append(current_alias)
        if not re.match(r"COPY(?:\s|$)", line, flags=re.IGNORECASE):
            continue
        copy_from_reference, malformed_copy_from = _docker_copy_from_reference(line)
        if malformed_copy_from:
            malformed_copy_from_lines.append(line_number)
            continue
        if copy_from_reference is None:
            continue
        reference = copy_from_reference.lower()
        reference_kind = "unknown"
        if reference in PUBLIC_EDGE_DOCKER_STAGE_ORDER:
            reference_kind = "stage"
            stage_dependencies.setdefault(current_alias, set()).add(reference)
            allowed_stage_references = PUBLIC_EDGE_DOCKER_COPY_STAGE_REFERENCES_BY_STAGE.get(
                current_alias,
                frozenset(),
            )
            if reference not in allowed_stage_references:
                invalid_copy_from_stages.append(
                    (line_number, current_alias, reference)
                )
            reference_stage_index = stage_index_by_alias.get(reference)
            if reference_stage_index is None or reference_stage_index >= current_stage:
                forward_copy_from_references.append(
                    (line_number, current_alias, reference)
                )
        else:
            allowed_named_contexts = PUBLIC_EDGE_DOCKER_NAMED_CONTEXTS_BY_STAGE.get(
                current_alias,
                frozenset(),
            )
            if reference in allowed_named_contexts:
                reference_kind = "named-context"
                named_context_copy_lines_by_stage.setdefault(current_alias, []).append(line)
                exact_named_context_copies = (
                    PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE.get(
                        current_alias
                    )
                )
                if (
                    exact_named_context_copies is not None
                    and line not in exact_named_context_copies
                ):
                    invalid_named_context_copies.append(
                        (line_number, current_alias, reference)
                    )
            else:
                unknown_copy_from_references.append((line_number, reference))
        copy_from_references.append(
            {
                "line": line_number,
                "stage": current_alias,
                "reference": reference,
                "kind": reference_kind,
            }
        )

    if pre_stage_instructions:
        failures.append("global instructions before the first FROM are forbidden")
    if proof_stage_count != 1:
        failures.append("Dockerfile must contain exactly one public-pwa-proof stage alias")
    if build_stage_count != 1:
        failures.append("Dockerfile must contain exactly one named build stage")
    if tool_final_stage_count != 1:
        failures.append(
            "Dockerfile must contain exactly one named install-linking-postgres-tool-final stage"
        )
    if final_stage_count != 1:
        failures.append("Dockerfile must contain exactly one named final stage")
    exact_stage_set_and_order = tuple(stage_aliases) == PUBLIC_EDGE_DOCKER_STAGE_ORDER
    if not exact_stage_set_and_order:
        failures.append(
            "Dockerfile must contain only public-pwa-proof, build, "
            "install-linking-postgres-tool-final, and final stages in that exact order"
        )
    default_stage_is_final = bool(stage_aliases) and stage_aliases[-1] == PUBLIC_EDGE_DOCKER_FINAL_STAGE
    if not default_stage_is_final:
        failures.append("Dockerfile default/last stage must be final")
    if derived_proof_stages or proof_alias_redefinitions:
        failures.append("public-pwa-proof must not be derived or redefined")
    exact_receipt_dependency = receipt_copy_stages == [PUBLIC_EDGE_DOCKER_BUILD_STAGE]
    if not exact_receipt_dependency:
        failures.append(
            "build stage must COPY the exact proof receipt from public-pwa-proof exactly once"
        )
    if other_proof_copies:
        failures.append("no other COPY from public-pwa-proof is allowed")
    exact_tool_publish_dependency = tool_publish_copy_stages == [
        PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE
    ]
    if not exact_tool_publish_dependency:
        failures.append(
            "install-linking-postgres-tool-final must COPY the exact tool publish artifact exactly once"
        )
    exact_final_publish_dependency = final_publish_copy_stages == [
        PUBLIC_EDGE_DOCKER_FINAL_STAGE
    ]
    if not exact_final_publish_dependency:
        failures.append(
            "final stage must COPY the exact build publish artifact exactly once"
        )
    exact_tool_payload_mode = tool_payload_mode_stages == [
        PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE
    ]
    if not exact_tool_payload_mode:
        failures.append(
            "install-linking-postgres-tool-final must normalize payload readability exactly once"
        )
    exact_final_payload_mode = final_payload_mode_stages == [
        PUBLIC_EDGE_DOCKER_FINAL_STAGE
    ]
    if not exact_final_payload_mode:
        failures.append(
            "final stage must normalize payload readability and isolate state exactly once"
        )
    if malformed_copy_from_lines:
        failures.append("every Docker COPY --from reference must use one exact literal value")
    if unknown_copy_from_references or invalid_named_context_copies:
        failures.append(
            "Dockerfile COPY --from references must name an allowed earlier stage or named context"
        )
    exact_required_named_context_copies = True
    for stage, expected_copies in PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE.items():
        actual_copies = named_context_copy_lines_by_stage.get(stage, [])
        if set(actual_copies) != set(expected_copies) or len(actual_copies) != len(expected_copies):
            exact_required_named_context_copies = False
            failures.append(
                f"Dockerfile {stage} stage must contain the exact required named-context COPY set"
            )
    if invalid_copy_from_stages:
        failures.append("Dockerfile COPY stage references drifted from the closed stage graph")
    if forward_copy_from_references:
        failures.append("Dockerfile COPY stage references must name an earlier stage")

    def stage_depends_on(stage: str, dependency: str) -> bool:
        if stage == dependency:
            return True
        pending = list(stage_dependencies.get(stage, set()))
        visited: set[str] = set()
        while pending:
            candidate = pending.pop()
            if candidate == dependency:
                return True
            if candidate in visited:
                continue
            visited.add(candidate)
            pending.extend(stage_dependencies.get(candidate, set()))
        return False

    build_depends_on_proof = stage_depends_on(
        PUBLIC_EDGE_DOCKER_BUILD_STAGE,
        PUBLIC_EDGE_DOCKER_PROOF_STAGE,
    )
    tool_final_depends_on_build = stage_depends_on(
        PUBLIC_EDGE_DOCKER_TOOL_FINAL_STAGE,
        PUBLIC_EDGE_DOCKER_BUILD_STAGE,
    )
    final_depends_on_build = stage_depends_on(
        PUBLIC_EDGE_DOCKER_FINAL_STAGE,
        PUBLIC_EDGE_DOCKER_BUILD_STAGE,
    )
    all_targets_proof_gated = exact_stage_set_and_order and all(
        stage_depends_on(stage, PUBLIC_EDGE_DOCKER_PROOF_STAGE)
        for stage in PUBLIC_EDGE_DOCKER_STAGE_ORDER
    )
    if not build_depends_on_proof:
        failures.append("build stage must depend on public-pwa-proof")
    if not tool_final_depends_on_build:
        failures.append(
            "install-linking-postgres-tool-final must depend transitively on build"
        )
    if not final_depends_on_build:
        failures.append("final stage must depend transitively on build")
    if not all_targets_proof_gated:
        failures.append("every selectable Docker stage must be gated by public-pwa-proof")

    checks = {
        "exactSyntaxDirective": exact_header,
        "noLateParserDirectives": not late_directives,
        "noHeredoc": not heredoc_lines,
        "validLogicalInstructions": not malformed_continuations,
        "noGlobalInstructions": not pre_stage_instructions,
        "exactProofStage": exact_proof_stage,
        "exactStageHeaders": exact_stage_headers,
        "singleProofStage": proof_stage_count == 1,
        "proofStageNotDerived": not derived_proof_stages and not proof_alias_redefinitions,
        "exactBuildStage": build_stage_count == 1,
        "exactToolFinalStage": tool_final_stage_count == 1,
        "exactFinalStage": final_stage_count == 1,
        "exactStageSetAndOrder": exact_stage_set_and_order,
        "defaultStageIsFinal": default_stage_is_final,
        "exactReceiptDependency": exact_receipt_dependency,
        "receiptIsFirstBuildInstruction": receipt_is_first_build_instruction,
        "noOtherProofCopies": not other_proof_copies,
        "exactToolPublishDependency": exact_tool_publish_dependency,
        "exactFinalPublishDependency": exact_final_publish_dependency,
        "exactToolPayloadMode": exact_tool_payload_mode,
        "exactFinalPayloadMode": exact_final_payload_mode,
        "exactCopyFromReferences": not (
            malformed_copy_from_lines
            or unknown_copy_from_references
            or invalid_named_context_copies
            or invalid_copy_from_stages
            or forward_copy_from_references
        ),
        "exactRequiredNamedContextCopies": exact_required_named_context_copies,
        "buildDependsOnProof": build_depends_on_proof,
        "toolFinalDependsOnBuild": tool_final_depends_on_build,
        "finalDependsOnBuild": final_depends_on_build,
        "allTargetsProofGated": all_targets_proof_gated,
    }
    unique_failures = list(dict.fromkeys(failures))
    return {
        "status": "pass" if not unique_failures and all(checks.values()) else "fail",
        "present": True,
        "proofStageCount": proof_stage_count,
        "buildStageCount": build_stage_count,
        "toolFinalStageCount": tool_final_stage_count,
        "finalStageCount": final_stage_count,
        "stageAliases": stage_aliases,
        "stageDependencies": {
            stage: sorted(dependencies)
            for stage, dependencies in stage_dependencies.items()
            if stage
        },
        "copyFromReferences": copy_from_references,
        "pythonInvocationCount": 1 if exact_proof_stage else 0,
        "checks": checks,
        "failures": unique_failures,
    }


def _compose_mapping_entry(raw_line: str, *, indent: int) -> tuple[str, str] | None:
    if len(raw_line) - len(raw_line.lstrip(" ")) != indent:
        return None
    text = raw_line[indent:].rstrip()
    if not text or text.startswith(("#", "-")):
        return None
    if text[0] in {"'", '"'}:
        quote = text[0]
        escaped = False
        closing_index = -1
        for index, character in enumerate(text[1:], start=1):
            if quote == '"' and character == "\\" and not escaped:
                escaped = True
                continue
            if character == quote and not escaped:
                closing_index = index
                break
            escaped = False
        if closing_index < 0:
            return None
        key_token = text[: closing_index + 1]
        remainder = text[closing_index + 1 :]
        if not remainder.startswith(":"):
            return None
        try:
            key = ast.literal_eval(key_token)
        except (SyntaxError, ValueError):
            return None
        if not isinstance(key, str):
            return None
        raw_value = remainder[1:].strip()
    elif ": " in text:
        key, raw_value = text.rsplit(": ", 1)
        key = key.strip()
        raw_value = raw_value.strip()
    elif text.endswith(":"):
        key = text[:-1].strip()
        raw_value = ""
    else:
        return None
    if not key:
        return None
    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
        try:
            parsed_value = ast.literal_eval(raw_value)
        except (SyntaxError, ValueError):
            return None
        if not isinstance(parsed_value, str):
            return None
        raw_value = parsed_value
    return key, raw_value


def _parse_public_pwa_compose_build_bindings(
    text: str,
    *,
    service_name: str = PUBLIC_EDGE_COMPOSE_PORTAL_SERVICE,
) -> tuple[str, str, str, dict[str, str], list[str]]:
    lines = text.splitlines()
    failures: list[str] = []
    service_indexes = [
        index
        for index, raw_line in enumerate(lines)
        if raw_line == f"  {service_name}:"
    ]
    if len(service_indexes) != 1:
        return "", "", "", {}, [f"Compose must declare {service_name} exactly once"]
    service_start = service_indexes[0]
    service_end = len(lines)
    for index in range(service_start + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(lines[index]) - len(lines[index].lstrip(" "))
        if indentation <= 2:
            service_end = index
            break
    build_indexes = [
        index
        for index in range(service_start + 1, service_end)
        if lines[index] == "    build:"
    ]
    if len(build_indexes) != 1:
        return "", "", "", {}, [f"Compose {service_name} must declare build exactly once"]
    build_start = build_indexes[0]
    build_end = service_end
    for index in range(build_start + 1, service_end):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(lines[index]) - len(lines[index].lstrip(" "))
        if indentation <= 4:
            build_end = index
            break
    build_entries: dict[str, tuple[int, str]] = {}
    duplicate_build_keys: set[str] = set()
    for index in range(build_start + 1, build_end):
        entry = _compose_mapping_entry(lines[index], indent=6)
        if entry is None:
            continue
        key, value = entry
        if key in build_entries:
            duplicate_build_keys.add(key)
        build_entries[key] = (index, value)
    if duplicate_build_keys:
        failures.append(f"Compose {service_name} build contains duplicate keys")
    build_context = build_entries.get("context", (-1, ""))[1]
    dockerfile = build_entries.get("dockerfile", (-1, ""))[1]
    target = build_entries.get("target", (-1, ""))[1]
    contexts_entry = build_entries.get("additional_contexts")
    if contexts_entry is None or contexts_entry[1]:
        failures.append(f"Compose {service_name} additional_contexts mapping is missing")
        return build_context, dockerfile, target, {}, failures
    contexts_start = contexts_entry[0]
    bindings: dict[str, str] = {}
    duplicate_context_names: set[str] = set()
    for index in range(contexts_start + 1, build_end):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(raw_line) - len(raw_line.lstrip(" "))
        if indentation <= 6:
            break
        entry = _compose_mapping_entry(raw_line, indent=8)
        if entry is None:
            failures.append(
                f"Compose {service_name} additional_contexts contains a non-literal entry"
            )
            continue
        name, value = entry
        if name in bindings:
            duplicate_context_names.add(name)
        bindings[name] = value
    if duplicate_context_names:
        failures.append(f"Compose {service_name} additional_contexts contains duplicate names")
    return build_context, dockerfile, target, bindings, failures


def _validate_public_pwa_compose_service_contract(
    text: str,
    *,
    service_name: str,
    expected_target: str,
    expected_bindings: dict[str, str],
) -> dict[str, Any]:
    build_context, dockerfile, target, actual_bindings, failures = (
        _parse_public_pwa_compose_build_bindings(text, service_name=service_name)
    )
    contexts_are_mapping = not any(
        "additional_contexts" in failure for failure in failures
    )
    actual_names = set(actual_bindings)
    expected_names = set(expected_bindings)
    missing_names = sorted(expected_names - actual_names)
    unexpected_names = sorted(actual_names - expected_names)
    reserved_names = sorted(
        name
        for name in actual_names
        if name.lower() in PUBLIC_EDGE_DOCKER_RESERVED_CONTEXT_NAMES
    )
    binding_matches = {
        name: actual_bindings.get(name) == expected
        for name, expected in expected_bindings.items()
    }
    exact_bindings = (
        contexts_are_mapping
        and actual_names == expected_names
        and len(actual_bindings) == len(expected_bindings)
        and all(binding_matches.values())
    )
    if build_context != PUBLIC_EDGE_COMPOSE_BUILD_CONTEXT:
        failures.append(f"Compose {service_name} build context drifted")
    if dockerfile != PUBLIC_EDGE_COMPOSE_DOCKERFILE:
        failures.append(f"Compose {service_name} Dockerfile binding drifted")
    if target != expected_target:
        failures.append(f"Compose {service_name} build target drifted")
    if not contexts_are_mapping:
        failures.append(f"Compose {service_name} additional_contexts must be a mapping")
    if not exact_bindings:
        failures.append(f"Compose {service_name} named-context bindings drifted")
    if reserved_names:
        failures.append(
            f"Compose {service_name} named contexts must not override reserved Docker references"
        )
    checks = {
        "exactBuildContext": build_context == PUBLIC_EDGE_COMPOSE_BUILD_CONTEXT,
        "exactDockerfile": dockerfile == PUBLIC_EDGE_COMPOSE_DOCKERFILE,
        "exactTarget": target == expected_target,
        "contextsAreMapping": contexts_are_mapping,
        "exactNamedContextBindings": exact_bindings,
        "noReservedContextNames": not reserved_names,
    }
    return {
        "status": "pass" if not failures and all(checks.values()) else "fail",
        "service": service_name,
        "buildContext": build_context,
        "dockerfile": dockerfile,
        "target": target,
        "expectedTarget": expected_target,
        "bindings": actual_bindings,
        "expectedBindings": expected_bindings,
        "bindingMatches": binding_matches,
        "missingContextNames": missing_names,
        "unexpectedContextNames": unexpected_names,
        "reservedContextNames": reserved_names,
        "checks": checks,
        "failures": list(dict.fromkeys(failures)),
    }


def validate_public_pwa_compose_context_contract(path: Path) -> dict[str, Any]:
    expected_bindings = dict(PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS)
    result: dict[str, Any] = {
        "status": "fail",
        "present": path.is_file(),
        "service": PUBLIC_EDGE_COMPOSE_PORTAL_SERVICE,
        "buildContext": "",
        "dockerfile": "",
        "bindings": {},
        "expectedBindings": expected_bindings,
        "bindingMatches": {name: False for name in expected_bindings},
        "missingContextNames": sorted(expected_bindings),
        "unexpectedContextNames": [],
        "reservedContextNames": [],
        "serviceContracts": {},
        "checks": {},
        "failures": [],
    }
    if not path.is_file():
        result["failures"] = ["Compose file is missing"]
        return result
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        result["failures"] = [f"Compose file could not be read as strict UTF-8: {exc}"]
        return result

    service_contracts: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for service_name, expected in PUBLIC_EDGE_COMPOSE_BUILD_SERVICE_CONTRACTS.items():
        service_contract = _validate_public_pwa_compose_service_contract(
            text,
            service_name=service_name,
            expected_target=str(expected["target"]),
            expected_bindings=dict(expected["namedContexts"]),
        )
        service_contracts[service_name] = service_contract
        failures.extend(service_contract["failures"])

    portal_contract = service_contracts[PUBLIC_EDGE_COMPOSE_PORTAL_SERVICE]
    all_service_contracts = all(
        contract["status"] == "pass" for contract in service_contracts.values()
    )
    checks = dict(portal_contract["checks"])
    checks["allServiceBuildContracts"] = all_service_contracts
    result.update(
        {
            "status": "pass" if not failures and all(checks.values()) else "fail",
            "buildContext": portal_contract["buildContext"],
            "dockerfile": portal_contract["dockerfile"],
            "bindings": portal_contract["bindings"],
            "bindingMatches": portal_contract["bindingMatches"],
            "missingContextNames": portal_contract["missingContextNames"],
            "unexpectedContextNames": portal_contract["unexpectedContextNames"],
            "reservedContextNames": portal_contract["reservedContextNames"],
            "serviceContracts": service_contracts,
            "checks": checks,
            "failures": list(dict.fromkeys(failures)),
        }
    )
    return result


def marker_findings(
    root: Path,
    *,
    required_markers: dict[str, tuple[str, ...]],
    forbidden_markers_map: dict[str, tuple[str, ...]],
    scope: str,
    missing_finding_id: str,
    forbidden_finding_id: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    root = root.resolve()
    findings: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []
    all_paths = sorted(set(required_markers) | set(forbidden_markers_map))
    for relative_path in all_paths:
        markers = required_markers.get(relative_path, ())
        forbidden_markers = forbidden_markers_map.get(relative_path, ())
        path = root / relative_path
        missing_markers: list[str] = []
        present_forbidden_markers: list[str] = []
        present = path.is_file()
        text = ""
        if present:
            text = path.read_text(encoding="utf-8", errors="replace")
            missing_markers = [marker for marker in markers if marker not in text]
            present_forbidden_markers = [marker for marker in forbidden_markers if marker in text]
        else:
            missing_markers = list(markers)
        checks.append(
            {
                "path": relative_path,
                "present": present,
                "requiredMarkers": list(markers),
                "missingMarkers": missing_markers,
                "forbiddenMarkers": list(forbidden_markers),
                "presentForbiddenMarkers": present_forbidden_markers,
            }
        )
        if missing_markers:
            findings.append(
                {
                    "id": missing_finding_id,
                    "severity": "blocker",
                    "scope": scope,
                    "detail": f"{scope} {relative_path} missing markers: {', '.join(missing_markers)}",
                }
            )
        if present_forbidden_markers:
            findings.append(
                {
                    "id": forbidden_finding_id,
                    "severity": "blocker",
                    "scope": scope,
                    "detail": f"{scope} {relative_path} contains forbidden markers: {', '.join(present_forbidden_markers)}",
                }
            )
    return findings, checks


def source_marker_findings(source_root: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    findings, checks = marker_findings(
        source_root,
        required_markers=PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS,
        forbidden_markers_map=PUBLIC_EDGE_FORBIDDEN_SOURCE_MARKERS,
        scope="source",
        missing_finding_id="public_edge_source_marker_missing",
        forbidden_finding_id="public_edge_source_marker_forbidden",
    )
    docker_contract = validate_public_pwa_docker_build_contract(
        source_root / PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    )
    docker_marker_check = next(
        (
            check
            for check in checks
            if check["path"] == PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
        ),
        None,
    )
    if docker_marker_check is not None:
        docker_marker_check["dockerBuildContract"] = docker_contract
    if docker_contract["status"] != "pass":
        findings.append(
            {
                "id": "public_edge_source_docker_contract_invalid",
                "severity": "blocker",
                "scope": "source",
                "detail": (
                    "source Chummer.Run.Api/Dockerfile violates the public PWA build contract: "
                    + "; ".join(str(item) for item in docker_contract["failures"])
                ),
            }
        )
    compose_contract = validate_public_pwa_compose_context_contract(
        source_root / PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    )
    compose_marker_check = next(
        (
            check
            for check in checks
            if check["path"] == PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
        ),
        None,
    )
    if compose_marker_check is not None:
        compose_marker_check["dockerBuildContextContract"] = compose_contract
    if compose_contract["status"] != "pass":
        findings.append(
            {
                "id": "public_edge_source_compose_context_contract_invalid",
                "severity": "blocker",
                "scope": "source",
                "detail": (
                    "source docker-compose.public-edge.yml violates the public PWA "
                    "build-context contract: "
                    + "; ".join(str(item) for item in compose_contract["failures"])
                ),
            }
        )
    return findings, checks


def sanitize_public_pwa_proof_detail(value: object, source_root: Path) -> str:
    detail = " ".join(str(value or "").split())
    for path, replacement in (
        (source_root.resolve(), "<source-root>"),
        (source_root.resolve().parent, "<workspace-root>"),
    ):
        detail = detail.replace(str(path), replacement)
    detail = re.sub(
        r"(?i)\b(secret|token|access_token|api[_-]?key|password)\b(\s*[:=]\s*)[^\s,;]+",
        r"\1\2<redacted>",
        detail,
    )
    detail = re.sub(r"(?i)(https?://[^\s?]+)\?[^\s]+", r"\1?<redacted>", detail)
    return detail[:MAX_PUBLIC_PWA_PROOF_DETAIL_CHARS]


def _lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _required_os_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or value == 0:
        raise RuntimeError(f"required POSIX open flag {name} is unavailable")
    return value


def _open_directory_no_symlinks(path: Path) -> int:
    absolute = _lexical_path(path)
    directory_flag = _required_os_flag("O_DIRECTORY")
    nofollow_flag = _required_os_flag("O_NOFOLLOW")
    try:
        descriptor = os.open(
            "/",
            os.O_RDONLY | directory_flag | getattr(os, "O_CLOEXEC", 0),
        )
    except (OSError, TypeError) as exc:
        raise RuntimeError("identity root is unreadable on this host") from exc
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | directory_flag | nofollow_flag | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except (OSError, TypeError) as exc:
        os.close(descriptor)
        raise RuntimeError("identity component contains a symlink or is unreadable") from exc


def _stable_file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_public_pwa_identity(
    source_root: Path,
    relative_path: str,
    *,
    max_bytes: int = MAX_PUBLIC_PWA_IDENTITY_FILE_BYTES,
) -> tuple[bytes, os.stat_result]:
    if max_bytes < 0:
        raise RuntimeError("identity size limit must be non-negative")
    root = _lexical_path(source_root)
    target = _lexical_path(root / relative_path)
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("identity path escapes source root") from exc
    if not relative.parts:
        raise RuntimeError("identity path must name a file")

    directory_descriptor = _open_directory_no_symlinks(root)
    nofollow_flag = _required_os_flag("O_NOFOLLOW")
    try:
        for component in relative.parts[:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY
                | _required_os_flag("O_DIRECTORY")
                | nofollow_flag
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | nofollow_flag | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_descriptor,
        )
        try:
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise RuntimeError("identity component is not a regular file")
            if before.st_size > max_bytes:
                raise RuntimeError("identity component exceeds its size limit")
            chunks: list[bytes] = []
            byte_count = 0
            while True:
                chunk = os.read(file_descriptor, min(1024 * 1024, max_bytes + 1 - byte_count))
                if not chunk:
                    break
                chunks.append(chunk)
                byte_count += len(chunk)
                if byte_count > max_bytes:
                    raise RuntimeError("identity component exceeds its size limit")
            after = os.fstat(file_descriptor)
            if _stable_file_identity(before) != _stable_file_identity(after) or byte_count != before.st_size:
                raise RuntimeError("identity component changed while it was read")
            return b"".join(chunks), after
        finally:
            os.close(file_descriptor)
    except (OSError, TypeError) as exc:
        raise RuntimeError("identity component contains a symlink or is unreadable") from exc
    finally:
        os.close(directory_descriptor)


def read_public_pwa_identity_file(
    source_root: Path,
    relative_path: str,
    *,
    max_bytes: int = MAX_PUBLIC_PWA_IDENTITY_FILE_BYTES,
) -> bytes:
    payload, _ = _read_public_pwa_identity(
        source_root,
        relative_path,
        max_bytes=max_bytes,
    )
    return payload


def strict_json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        return decode_strict_json_object(payload, label=label)
    except StrictJsonContractError as exc:
        raise RuntimeError(f"{label} is not strict JSON") from exc


def _normalized_public_pwa_relative_path(value: object) -> str:
    raw = str(value or "").strip()
    path = Path(raw)
    if (
        not raw
        or path.is_absolute()
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != raw
    ):
        raise RuntimeError("public PWA snapshot path is not normalized")
    return raw


def expected_public_pwa_input_paths() -> tuple[tuple[str, str], ...]:
    run_paths = set(PUBLIC_PWA_FIXED_RUN_INPUTS)
    run_paths.update(projection for _, projection in PUBLIC_PWA_ASSET_INPUTS)
    play_paths = {source for source, _ in PUBLIC_PWA_ASSET_INPUTS}
    return tuple(
        sorted(
            {("run-services", path) for path in run_paths}
            | {("play", path) for path in play_paths}
        )
    )


def _public_pwa_input_size_limit(root_name: str, relative_path: str) -> int:
    if root_name not in {"run-services", "play"}:
        raise RuntimeError("public PWA input root role is unsupported")
    if relative_path in {
        PUBLIC_PWA_PROOF_IDENTITY_PATHS["verifier"],
        PUBLIC_PWA_PROOF_IDENTITY_PATHS["generator"],
        "scripts/validate_public_pwa_proof_authority.py",
    }:
        return MAX_PUBLIC_PWA_IDENTITY_FILE_BYTES
    suffix = Path(relative_path).suffix.lower()
    if suffix in {".json", ".webmanifest"}:
        return MAX_PUBLIC_PWA_JSON_INPUT_BYTES
    if suffix == ".png":
        return MAX_PUBLIC_PWA_BINARY_INPUT_BYTES
    return MAX_PUBLIC_PWA_TEXT_INPUT_BYTES


def _directory_identity(metadata: os.stat_result) -> list[int]:
    return [*_stable_file_identity(metadata), metadata.st_mode, metadata.st_nlink]


def capture_public_pwa_directory_trace(path: Path) -> list[dict[str, Any]]:
    absolute = _lexical_path(path)
    directory_flag = _required_os_flag("O_DIRECTORY")
    nofollow_flag = _required_os_flag("O_NOFOLLOW")
    descriptor = os.open("/", os.O_RDONLY | directory_flag | getattr(os, "O_CLOEXEC", 0))
    trace = [{"path": "/", "identity": _directory_identity(os.fstat(descriptor))}]
    traversed = Path("/")
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | directory_flag | nofollow_flag | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
            traversed /= component
            trace.append(
                {
                    "path": str(traversed),
                    "identity": _directory_identity(os.fstat(descriptor)),
                }
            )
        return trace
    except (OSError, TypeError) as exc:
        raise RuntimeError("public PWA root path contains a symlink or unreadable component") from exc
    finally:
        os.close(descriptor)


@contextmanager
def bound_public_pwa_root(path: Path, *, role: str) -> Iterator[dict[str, Any]]:
    absolute = _lexical_path(path)
    descriptor = _open_directory_no_symlinks(absolute)
    try:
        metadata = os.fstat(descriptor)
        trace = capture_public_pwa_directory_trace(absolute)
        if trace[-1]["identity"] != _directory_identity(metadata):
            raise RuntimeError(f"{role} root changed while it was bound")
        yield {
            "role": role,
            "path": str(absolute),
            "descriptor": descriptor,
            "identity": _directory_identity(metadata),
            "pathTrace": trace,
        }
    finally:
        os.close(descriptor)


def read_public_pwa_bound_input(
    root_binding: dict[str, Any],
    relative_path: str,
) -> tuple[bytes, dict[str, Any]]:
    normalized = _normalized_public_pwa_relative_path(relative_path)
    descriptor = os.dup(int(root_binding["descriptor"]))
    directory_trace: list[dict[str, Any]] = [
        {"path": ".", "identity": _directory_identity(os.fstat(descriptor))}
    ]
    nofollow_flag = _required_os_flag("O_NOFOLLOW")
    try:
        traversed = Path(".")
        parts = Path(normalized).parts
        for component in parts[:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY
                | _required_os_flag("O_DIRECTORY")
                | nofollow_flag
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
            traversed /= component
            directory_trace.append(
                {
                    "path": traversed.as_posix(),
                    "identity": _directory_identity(os.fstat(descriptor)),
                }
            )
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | nofollow_flag | getattr(os, "O_CLOEXEC", 0),
            dir_fd=descriptor,
        )
        try:
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise RuntimeError("public PWA input is not a regular file")
            limit = _public_pwa_input_size_limit(str(root_binding["role"]), normalized)
            if before.st_size > limit:
                raise RuntimeError("public PWA input exceeds its role size limit")
            chunks: list[bytes] = []
            byte_count = 0
            while True:
                chunk = os.read(file_descriptor, min(1024 * 1024, limit + 1 - byte_count))
                if not chunk:
                    break
                chunks.append(chunk)
                byte_count += len(chunk)
                if byte_count > limit:
                    raise RuntimeError("public PWA input exceeds its role size limit")
            after = os.fstat(file_descriptor)
            if _stable_file_identity(before) != _stable_file_identity(after) or byte_count != before.st_size:
                raise RuntimeError("public PWA input changed while it was captured")
            payload = b"".join(chunks)
            return payload, {
                "root": str(root_binding["role"]),
                "path": normalized,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "byteLength": len(payload),
                "fileIdentity": [*_stable_file_identity(after), after.st_mode, after.st_nlink],
                "directoryTrace": directory_trace,
            }
        finally:
            os.close(file_descriptor)
    except (OSError, TypeError) as exc:
        raise RuntimeError("public PWA input contains a symlink or unreadable component") from exc
    finally:
        os.close(descriptor)


def load_public_pwa_proof_authority(
    authority_root: Path | None = None,
) -> dict[str, Any]:
    root = _lexical_path(authority_root or PUBLIC_PWA_PROOF_AUTHORITY_ROOT)
    authority_bytes = read_public_pwa_identity_file(
        root,
        PUBLIC_PWA_PROOF_AUTHORITY_RELATIVE_PATH,
    )
    def reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError(f"duplicate authority field: {key}")
            parsed[key] = value
        return parsed

    try:
        authority = json.loads(
            authority_bytes.decode("utf-8"),
            object_pairs_hook=reject_duplicate_fields,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("public PWA proof authority is not valid JSON") from exc
    if not isinstance(authority, dict):
        raise RuntimeError("public PWA proof authority must be a JSON object")
    canonical_authority = (
        json.dumps(authority, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if authority_bytes != canonical_authority:
        raise RuntimeError("public PWA proof authority is not canonical UTF-8 JSON")
    expected_keys = {
        "contractName",
        "policyId",
        "assetPolicyCount",
        "dependencyPolicyCount",
        "verifierPath",
        "verifierSha256",
        "generatorPath",
        "generatorSha256",
        "inventoryPath",
        "inventorySha256",
    }
    if set(authority) != expected_keys:
        raise RuntimeError("public PWA proof authority fields drifted from its closed contract")
    if authority.get("contractName") != PUBLIC_PWA_PROOF_AUTHORITY_CONTRACT:
        raise RuntimeError("public PWA proof authority contract is unsupported")
    if authority.get("policyId") != PUBLIC_PWA_POLICY_ID:
        raise RuntimeError("public PWA proof authority policy identity drifted")
    if authority.get("assetPolicyCount") != PUBLIC_PWA_EXPECTED_ASSET_COUNT:
        raise RuntimeError("public PWA proof authority asset count drifted")
    if authority.get("dependencyPolicyCount") != PUBLIC_PWA_EXPECTED_DEPENDENCY_COUNT:
        raise RuntimeError("public PWA proof authority dependency count drifted")

    pins: dict[str, tuple[str, str]] = {}
    for role, (path_field, digest_field) in PUBLIC_PWA_PROOF_AUTHORITY_FIELDS.items():
        relative_path = str(authority.get(path_field) or "")
        digest = str(authority.get(digest_field) or "").lower()
        if relative_path != PUBLIC_PWA_PROOF_IDENTITY_PATHS[role]:
            raise RuntimeError(f"public PWA proof authority {role} path drifted")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise RuntimeError(f"public PWA proof authority {role} digest is invalid")
        pins[role] = (relative_path, digest)
    return {
        "contractName": PUBLIC_PWA_PROOF_AUTHORITY_CONTRACT,
        "policyId": PUBLIC_PWA_POLICY_ID,
        "assetPolicyCount": PUBLIC_PWA_EXPECTED_ASSET_COUNT,
        "dependencyPolicyCount": PUBLIC_PWA_EXPECTED_DEPENDENCY_COUNT,
        "sha256": hashlib.sha256(authority_bytes).hexdigest(),
        "pins": pins,
    }


def _load_verified_public_pwa_proof_identities(
    source_root: Path,
    *,
    authority_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, bytes], dict[str, os.stat_result], dict[str, Any]]:
    try:
        authority = load_public_pwa_proof_authority(authority_root)
    except RuntimeError as exc:
        receipt = {
            "status": "fail",
            "checks": {},
            "sha256": {},
            "fileIdentity": {},
            "authority": {"status": "fail", "sha256": ""},
            "failures": [f"proof authority invalid: {exc}"],
        }
        return receipt, {}, {}, {}

    checks: dict[str, bool] = {}
    digests: dict[str, str] = {}
    identities: dict[str, list[int]] = {}
    payloads: dict[str, bytes] = {}
    metadata: dict[str, os.stat_result] = {}
    failures: list[str] = []
    for role, (relative_path, expected_digest) in authority["pins"].items():
        try:
            payload, file_stat = _read_public_pwa_identity(source_root, relative_path)
            actual_digest = hashlib.sha256(payload).hexdigest()
        except RuntimeError as exc:
            checks[role] = False
            digests[role] = ""
            identities[role] = []
            failures.append(f"identity {role} invalid: {exc}")
            continue
        checks[role] = actual_digest == expected_digest
        digests[role] = actual_digest
        identities[role] = list(_stable_file_identity(file_stat))
        if checks[role]:
            payloads[role] = payload
            metadata[role] = file_stat
        else:
            failures.append(f"identity {role} digest does not match the reviewed proof authority")
    status = "pass" if checks and all(checks.values()) and not failures else "fail"
    receipt = {
        "status": status,
        "checks": checks,
        "sha256": digests,
        "fileIdentity": identities,
        "authority": {
            "status": "pass",
            "contractName": authority["contractName"],
            "sha256": authority["sha256"],
        },
        "failures": failures,
    }
    return receipt, payloads, metadata, authority


def verify_public_pwa_proof_identities(
    source_root: Path,
    *,
    authority_root: Path | None = None,
) -> dict[str, Any]:
    receipt, _, _, _ = _load_verified_public_pwa_proof_identities(
        source_root,
        authority_root=authority_root,
    )
    return receipt


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise RuntimeError("descriptor write did not make progress")
        offset += written


def _required_memfd_seals() -> int:
    if fcntl is None or not hasattr(os, "memfd_create"):
        raise RuntimeError("sealed memfd execution is unavailable on this host")
    names = (
        "F_ADD_SEALS",
        "F_GET_SEALS",
        "F_SEAL_SEAL",
        "F_SEAL_SHRINK",
        "F_SEAL_GROW",
        "F_SEAL_WRITE",
    )
    if any(not hasattr(fcntl, name) for name in names):
        raise RuntimeError("sealed memfd execution is unavailable on this host")
    return int(
        fcntl.F_SEAL_SEAL
        | fcntl.F_SEAL_SHRINK
        | fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_WRITE
    )


def _create_sealed_public_pwa_memfd(name: str, payload: bytes) -> tuple[int, int]:
    required_seals = _required_memfd_seals()
    descriptor = os.memfd_create(
        name,
        flags=getattr(os, "MFD_CLOEXEC", 0) | getattr(os, "MFD_ALLOW_SEALING", 0x0002),
    )
    try:
        _write_all(descriptor, payload)
        os.lseek(descriptor, 0, os.SEEK_SET)
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, required_seals)
        actual_seals = int(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS))
        if actual_seals & required_seals != required_seals:
            raise RuntimeError("public PWA input descriptor is not fully sealed")
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != len(payload):
            raise RuntimeError("public PWA input descriptor identity is invalid")
        return descriptor, actual_seals
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def sealed_public_pwa_input_snapshot(
    run_binding: dict[str, Any],
    play_binding: dict[str, Any],
    *,
    reviewed_authority_sha256: str,
) -> Iterator[dict[str, Any]]:
    bindings = {
        "run-services": run_binding,
        "play": play_binding,
    }
    expected = expected_public_pwa_input_paths()
    descriptors: list[int] = []
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    manifest_descriptor = -1
    try:
        for index, (root_name, relative_path) in enumerate(expected):
            payload, metadata = read_public_pwa_bound_input(
                bindings[root_name],
                relative_path,
            )
            total_bytes += len(payload)
            if total_bytes > MAX_PUBLIC_PWA_TOTAL_INPUT_BYTES:
                raise RuntimeError("public PWA input snapshot exceeds its total size limit")
            if (
                root_name == "run-services"
                and relative_path == PUBLIC_PWA_PROOF_AUTHORITY_RELATIVE_PATH
                and hashlib.sha256(payload).hexdigest() != reviewed_authority_sha256
            ):
                raise RuntimeError("source proof authority differs from the reviewed authority")
            descriptor, _ = _create_sealed_public_pwa_memfd(
                f"chummer-pwa-input-{index}",
                payload,
            )
            descriptors.append(descriptor)
            rows.append(
                {
                    **metadata,
                    "descriptor": descriptor,
                }
            )

        manifest = {
            "contractName": PUBLIC_PWA_INPUT_SNAPSHOT_CONTRACT,
            "roots": [
                {
                    "role": role,
                    "path": str(bindings[role]["path"]),
                    "identity": bindings[role]["identity"],
                    "pathTrace": bindings[role]["pathTrace"],
                }
                for role in ("run-services", "play")
            ],
            "files": rows,
        }
        manifest_payload = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        if len(manifest_payload) > MAX_PUBLIC_PWA_SNAPSHOT_MANIFEST_BYTES:
            raise RuntimeError("public PWA input manifest exceeds its size limit")
        manifest_descriptor, manifest_seals = _create_sealed_public_pwa_memfd(
            "chummer-pwa-input-manifest",
            manifest_payload,
        )
        yield {
            "descriptor": manifest_descriptor,
            "sha256": hashlib.sha256(manifest_payload).hexdigest(),
            "byteLength": len(manifest_payload),
            "seals": manifest_seals,
            "files": rows,
            "fileDescriptors": tuple(descriptors),
            "totalBytes": total_bytes,
            "expectedCount": len(expected),
        }
    finally:
        if manifest_descriptor >= 0:
            os.close(manifest_descriptor)
        for descriptor in descriptors:
            os.close(descriptor)


def revalidate_public_pwa_root_binding(binding: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    try:
        metadata = os.fstat(int(binding["descriptor"]))
        path_trace = capture_public_pwa_directory_trace(Path(str(binding["path"])))
        checks = {
            "descriptorIdentity": _directory_identity(metadata) == binding.get("identity"),
            "pathTrace": path_trace == binding.get("pathTrace"),
            "pathIdentity": bool(path_trace)
            and path_trace[-1].get("identity") == binding.get("identity"),
        }
        return {
            "role": str(binding.get("role") or ""),
            "status": "pass" if all(checks.values()) else "fail",
            "checks": checks,
        }
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "role": str(binding.get("role") or ""),
            "status": "fail",
            "checks": checks,
            "error": str(exc),
        }


def revalidate_public_pwa_input_snapshot(
    snapshot: dict[str, Any],
    bindings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_rows = snapshot.get("files") if isinstance(snapshot.get("files"), list) else []
    checked: list[dict[str, Any]] = []
    failures: list[str] = []
    for expected in expected_rows:
        root_name = str(expected.get("root") or "")
        relative_path = str(expected.get("path") or "")
        try:
            payload, actual = read_public_pwa_bound_input(
                bindings[root_name],
                relative_path,
            )
        except (KeyError, RuntimeError) as exc:
            failures.append(f"{root_name}:{relative_path}: {exc}")
            continue
        comparable_keys = {
            "root",
            "path",
            "sha256",
            "byteLength",
            "fileIdentity",
            "directoryTrace",
        }
        expected_comparable = {
            key: value for key, value in expected.items() if key in comparable_keys
        }
        if actual != expected_comparable:
            failures.append(f"{root_name}:{relative_path}: identity changed")
            continue
        if hashlib.sha256(payload).hexdigest() != str(expected.get("sha256") or ""):
            failures.append(f"{root_name}:{relative_path}: digest changed")
            continue
        checked.append(actual)
    return {
        "status": (
            "pass"
            if len(checked) == len(expected_rows) and not failures
            else "fail"
        ),
        "checkedCount": len(checked),
        "expectedCount": len(expected_rows),
        "failures": failures,
    }


def snapshot_public_pwa_identity(
    role: str,
    source_path: Path,
    source_payload: bytes,
    source_stat: os.stat_result,
    expected_sha256: str,
    snapshot_root: Path,
) -> dict[str, Any]:
    actual_sha256 = hashlib.sha256(source_payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(f"{role} source bytes do not match the reviewed authority")
    snapshot_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    suffix = source_path.suffix if source_path.suffix else ".bin"
    snapshot_name = f"{role}.{expected_sha256}{suffix}"
    root_descriptor = _open_directory_no_symlinks(snapshot_root)
    try:
        descriptor = os.open(
            snapshot_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | _required_os_flag("O_NOFOLLOW")
            | getattr(os, "O_CLOEXEC", 0),
            0o400,
            dir_fd=root_descriptor,
        )
        try:
            _write_all(descriptor, source_payload)
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o444)
            snapshot_stat = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(root_descriptor)
        snapshot_directory_stat = os.fstat(root_descriptor)
    except (OSError, TypeError) as exc:
        raise RuntimeError(f"{role} content-addressed snapshot could not be materialized") from exc
    finally:
        os.close(root_descriptor)

    snapshot_payload, snapshot_stat = _read_public_pwa_identity(snapshot_root, snapshot_name)
    if snapshot_payload != source_payload or hashlib.sha256(snapshot_payload).hexdigest() != expected_sha256:
        raise RuntimeError(f"{role} content-addressed snapshot is corrupt")
    if (snapshot_stat.st_dev, snapshot_stat.st_ino) == (source_stat.st_dev, source_stat.st_ino):
        raise RuntimeError(f"{role} content-addressed snapshot shares the source inode")
    if snapshot_stat.st_nlink != 1:
        raise RuntimeError(f"{role} content-addressed snapshot has unsafe hardlinks")
    if stat.S_IMODE(snapshot_stat.st_mode) & 0o222:
        raise RuntimeError(f"{role} content-addressed snapshot is writable")
    return {
        "role": role,
        "sourcePath": str(source_path),
        "snapshotRoot": str(_lexical_path(snapshot_root)),
        "snapshotName": snapshot_name,
        "snapshotPath": str(_lexical_path(snapshot_root / snapshot_name)),
        "sha256Expected": expected_sha256,
        "sha256Actual": expected_sha256,
        "snapshotDevice": snapshot_stat.st_dev,
        "snapshotInode": snapshot_stat.st_ino,
        "snapshotFileIdentity": list(_stable_file_identity(snapshot_stat)),
        "snapshotDirectoryIdentity": list(_stable_file_identity(snapshot_directory_stat)),
        "snapshotLinkCount": snapshot_stat.st_nlink,
        "snapshotWriteBits": stat.S_IMODE(snapshot_stat.st_mode) & 0o222,
        "byteLength": len(snapshot_payload),
        "status": "pass",
    }


def refresh_public_pwa_snapshot_binding(binding: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(binding)
    try:
        directory_descriptor = _open_directory_no_symlinks(
            Path(str(binding.get("snapshotRoot") or ""))
        )
        try:
            directory_metadata = os.fstat(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        payload, metadata = _read_public_pwa_identity(
            Path(str(binding.get("snapshotRoot") or "")),
            str(binding.get("snapshotName") or ""),
        )
        digest = hashlib.sha256(payload).hexdigest()
        expected_identity = (
            int(binding.get("snapshotDevice") or -1),
            int(binding.get("snapshotInode") or -1),
        )
        actual_identity = (metadata.st_dev, metadata.st_ino)
        expected_file_identity = tuple(binding.get("snapshotFileIdentity") or ())
        expected_directory_identity = tuple(binding.get("snapshotDirectoryIdentity") or ())
        checks = {
            "digest": digest == str(binding.get("sha256Expected") or ""),
            "identity": actual_identity == expected_identity,
            "fileIdentity": _stable_file_identity(metadata) == expected_file_identity,
            "directoryIdentity": _stable_file_identity(directory_metadata)
            == expected_directory_identity,
            "linkCount": metadata.st_nlink == 1,
            "readOnly": stat.S_IMODE(metadata.st_mode) & 0o222 == 0,
            "byteLength": len(payload) == int(binding.get("byteLength") or -1),
        }
        refreshed.update(
            {
                "sha256Actual": digest,
                "snapshotDeviceActual": metadata.st_dev,
                "snapshotInodeActual": metadata.st_ino,
                "snapshotLinkCount": metadata.st_nlink,
                "snapshotWriteBits": stat.S_IMODE(metadata.st_mode) & 0o222,
                "checks": checks,
                "status": "pass" if all(checks.values()) else "fail",
                "error": "",
            }
        )
    except RuntimeError as exc:
        refreshed.update({"checks": {}, "status": "fail", "error": str(exc)})
    return refreshed


def finalize_public_pwa_snapshot_directory_bindings(
    bindings: dict[str, dict[str, Any]],
    snapshot_root: Path,
) -> None:
    directory_descriptor = _open_directory_no_symlinks(snapshot_root)
    try:
        directory_identity = list(_stable_file_identity(os.fstat(directory_descriptor)))
    finally:
        os.close(directory_descriptor)
    for binding in bindings.values():
        binding["snapshotDirectoryIdentity"] = directory_identity


@contextmanager
def sealed_public_pwa_program_execution(
    binding: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    refreshed = refresh_public_pwa_snapshot_binding(binding)
    if refreshed.get("status") != "pass":
        raise RuntimeError("public PWA program snapshot binding failed before execution")
    snapshot_payload, _ = _read_public_pwa_identity(
        Path(str(refreshed["snapshotRoot"])),
        str(refreshed["snapshotName"]),
    )
    expected_sha256 = str(refreshed["sha256Expected"])
    if hashlib.sha256(snapshot_payload).hexdigest() != expected_sha256:
        raise RuntimeError("public PWA program snapshot changed before sealed execution")
    required_seals = _required_memfd_seals()
    descriptor = os.memfd_create(
        f"chummer-pwa-{refreshed.get('role')}-{expected_sha256}",
        flags=getattr(os, "MFD_CLOEXEC", 0) | getattr(os, "MFD_ALLOW_SEALING", 0x0002),
    )
    try:
        _write_all(descriptor, snapshot_payload)
        os.lseek(descriptor, 0, os.SEEK_SET)
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, required_seals)
        actual_seals = int(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS))
        if actual_seals & required_seals != required_seals:
            raise RuntimeError("public PWA program execution memfd is not fully sealed")
        sealed_payload = os.read(descriptor, len(snapshot_payload) + 1)
        os.lseek(descriptor, 0, os.SEEK_SET)
        sealed_sha256 = hashlib.sha256(sealed_payload).hexdigest()
        if sealed_payload != snapshot_payload or sealed_sha256 != expected_sha256:
            raise RuntimeError("sealed public PWA program bytes do not match the snapshot")
        yield {
            "descriptor": descriptor,
            "sha256Expected": expected_sha256,
            "sha256Actual": sealed_sha256,
            "seals": actual_seals,
            "byteLength": len(sealed_payload),
            "mode": "sealed_memfd_from_content_addressed_snapshot",
        }
    finally:
        os.close(descriptor)


@contextmanager
def writable_public_pwa_receipt_descriptor() -> Iterator[int]:
    _required_memfd_seals()
    descriptor = os.memfd_create(
        "chummer-pwa-preflight-receipt",
        flags=getattr(os, "MFD_CLOEXEC", 0) | getattr(os, "MFD_ALLOW_SEALING", 0x0002),
    )
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def read_and_seal_public_pwa_child_receipt(descriptor: int) -> tuple[dict[str, Any], int]:
    required_seals = _required_memfd_seals()
    fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, required_seals)
    actual_seals = int(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS))
    if actual_seals & required_seals != required_seals:
        raise RuntimeError("static verifier receipt descriptor is not fully sealed")
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("static verifier receipt descriptor is not a regular file")
    if metadata.st_size > MAX_PUBLIC_PWA_PROOF_RECEIPT_BYTES:
        raise RuntimeError("static verifier receipt exceeds its size limit")
    os.lseek(descriptor, 0, os.SEEK_SET)
    payload = os.read(descriptor, MAX_PUBLIC_PWA_PROOF_RECEIPT_BYTES + 1)
    if len(payload) > MAX_PUBLIC_PWA_PROOF_RECEIPT_BYTES or len(payload) != metadata.st_size:
        raise RuntimeError("static verifier receipt exceeds its size limit")
    result = strict_json_object(payload, label="static verifier receipt")
    return result, actual_seals


def require_public_pwa_child_preexec_support() -> None:
    if sys.platform != "linux" or resource is None:
        raise RuntimeError(
            "public PWA verifier resource limits require Linux pre-exec support"
        )
    unavailable = [
        name for name, _ in PUBLIC_PWA_CHILD_RESOURCE_LIMITS
        if not hasattr(resource, name)
    ]
    if unavailable:
        raise RuntimeError(
            "required public PWA child resource limits are unavailable: "
            + ", ".join(unavailable)
        )


def install_public_pwa_child_resource_limits_before_exec() -> None:
    """Install the closed resource ceiling after fork and before Python starts."""
    if sys.platform != "linux" or resource is None:
        os._exit(126)
    try:
        for name, limit in PUBLIC_PWA_CHILD_RESOURCE_LIMITS:
            resource.setrlimit(getattr(resource, name), (limit, limit))
    except BaseException:
        # preexec_fn runs after fork, where raising through arbitrary Python state is unsafe.
        # Exit before exec instead; the parent treats the non-zero child and empty receipt as fail.
        os._exit(126)


def execute_public_pwa_static_proof(source_root: Path) -> dict[str, Any]:
    raw_failures: list[str] = []
    result: dict[str, Any] = {}
    identities, identity_payloads, identity_metadata, authority = _load_verified_public_pwa_proof_identities(
        source_root
    )
    raw_failures.extend(str(item) for item in identities.get("failures", []) if str(item).strip())
    identity_revalidated = False
    snapshot_revalidated = False
    verifier_sealed = False
    generator_sealed = False
    receipt_descriptor_bound = False
    receipt_seals = 0
    input_manifest_sha256 = ""
    input_manifest_seals = 0
    input_expected_count = len(expected_public_pwa_input_paths())
    input_total_bytes = 0
    input_snapshot_revalidated = False
    roots_revalidated = False
    root_revalidation: dict[str, dict[str, Any]] = {}
    post_run_root_bindings: dict[str, dict[str, Any]] = {}
    input_snapshot_record: dict[str, Any] = {}
    try:
        required_memfd_seals = _required_memfd_seals()
    except RuntimeError as exc:
        required_memfd_seals = 0
        raw_failures.append(f"sealed descriptor support failed: {exc}")
    snapshot_bindings: dict[str, dict[str, Any]] = {}
    refreshed_snapshots: dict[str, dict[str, Any]] = {}
    subprocess_completed = False
    subprocess_return_code: int | None = None
    if identities.get("status") == "pass":
        with tempfile.TemporaryDirectory(prefix="chummer-pwa-preflight-") as temp_dir:
            temp_root = Path(temp_dir)
            snapshot_root = temp_root / "authority"
            snapshots_ready = False
            try:
                with ExitStack() as stack:
                    workspace_binding = stack.enter_context(
                        bound_public_pwa_root(source_root.parent, role="workspace")
                    )
                    run_binding = stack.enter_context(
                        bound_public_pwa_root(source_root, role="run-services")
                    )
                    play_binding = stack.enter_context(
                        bound_public_pwa_root(source_root.parent / "chummer-play", role="play")
                    )
                    root_bindings = {
                        "workspace": workspace_binding,
                        "run-services": run_binding,
                        "play": play_binding,
                    }
                    post_run_root_bindings = {
                        role: {**binding, "descriptor": os.dup(int(binding["descriptor"]))}
                        for role, binding in root_bindings.items()
                    }
                    input_snapshot = stack.enter_context(
                        sealed_public_pwa_input_snapshot(
                            run_binding,
                            play_binding,
                            reviewed_authority_sha256=str(authority["sha256"]),
                        )
                    )
                    input_snapshot_record = input_snapshot
                    input_manifest_sha256 = str(input_snapshot["sha256"])
                    input_manifest_seals = int(input_snapshot["seals"])
                    input_total_bytes = int(input_snapshot["totalBytes"])
                    for role in ("verifier", "generator"):
                        relative_path, expected_digest = authority["pins"][role]
                        snapshot_bindings[role] = snapshot_public_pwa_identity(
                            role,
                            _lexical_path(source_root / relative_path),
                            identity_payloads[role],
                            identity_metadata[role],
                            expected_digest,
                            snapshot_root,
                        )
                    finalize_public_pwa_snapshot_directory_bindings(
                        snapshot_bindings,
                        snapshot_root,
                    )
                    snapshots_ready = True
                    with (
                        sealed_public_pwa_program_execution(snapshot_bindings["verifier"]) as verifier_execution,
                        sealed_public_pwa_program_execution(snapshot_bindings["generator"]) as generator_execution,
                        writable_public_pwa_receipt_descriptor() as receipt_descriptor,
                    ):
                        verifier_sealed = True
                        generator_sealed = True
                        command = [
                            sys.executable,
                            "-I",
                            "-S",
                            "-c",
                            SEALED_PYTHON_PROGRAM_WRAPPER,
                            str(verifier_execution["descriptor"]),
                            str(verifier_execution["sha256Expected"]),
                            str(source_root / authority["pins"]["verifier"][0]),
                            str(workspace_binding["descriptor"]),
                            str(workspace_binding["identity"][0]),
                            str(workspace_binding["identity"][1]),
                            "--source-root",
                            str(source_root),
                            "--output-fd",
                            str(receipt_descriptor),
                            "--trusted-generator-fd",
                            str(generator_execution["descriptor"]),
                            "--trusted-generator-sha256",
                            str(generator_execution["sha256Expected"]),
                            "--trusted-input-manifest-fd",
                            str(input_snapshot["descriptor"]),
                            "--trusted-input-manifest-sha256",
                            input_manifest_sha256,
                        ]
                        child_environment = {
                            "HOME": str(temp_root),
                            "TMPDIR": str(temp_root),
                            "PYTHONHASHSEED": "0",
                            "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONNOUSERSITE": "1",
                            "LANG": "C.UTF-8",
                        }
                        require_public_pwa_child_preexec_support()
                        completed = subprocess.run(
                            command,
                            cwd="/",
                            env=child_environment,
                            check=False,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            close_fds=True,
                            preexec_fn=install_public_pwa_child_resource_limits_before_exec,
                            pass_fds=(
                                int(verifier_execution["descriptor"]),
                                int(generator_execution["descriptor"]),
                                receipt_descriptor,
                                int(workspace_binding["descriptor"]),
                                int(input_snapshot["descriptor"]),
                                *tuple(int(value) for value in input_snapshot["fileDescriptors"]),
                            ),
                            timeout=PUBLIC_PWA_PROOF_TIMEOUT_SECONDS,
                        )
                        subprocess_completed = True
                        subprocess_return_code = int(completed.returncode)
                        result, receipt_seals = read_and_seal_public_pwa_child_receipt(receipt_descriptor)
                        receipt_descriptor_bound = True
                        if completed.returncode != 0:
                            raw_failures.append("static verifier subprocess failed")
            except subprocess.TimeoutExpired:
                raw_failures.append("static verifier subprocess exceeded its hard timeout")
            except (
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raw_failures.append(f"static verifier snapshot or subprocess failed: {exc}")
            finally:
                try:
                    if snapshot_bindings:
                        refreshed_snapshots = {
                            role: refresh_public_pwa_snapshot_binding(binding)
                            for role, binding in snapshot_bindings.items()
                        }
                        snapshot_revalidated = bool(refreshed_snapshots) and all(
                            binding.get("status") == "pass"
                            for binding in refreshed_snapshots.values()
                        )
                        if snapshots_ready and not snapshot_revalidated:
                            raw_failures.append(
                                "public PWA proof snapshots changed during subprocess execution"
                            )
                    if input_snapshot_record and {
                        "run-services",
                        "play",
                    }.issubset(post_run_root_bindings):
                        input_revalidation = revalidate_public_pwa_input_snapshot(
                            input_snapshot_record,
                            {
                                "run-services": post_run_root_bindings["run-services"],
                                "play": post_run_root_bindings["play"],
                            },
                        )
                        input_snapshot_revalidated = (
                            input_revalidation.get("status") == "pass"
                        )
                        if not input_snapshot_revalidated:
                            raw_failures.append(
                                "public PWA proof inputs changed during subprocess execution"
                            )
                    if post_run_root_bindings:
                        root_revalidation = {
                            role: revalidate_public_pwa_root_binding(binding)
                            for role, binding in post_run_root_bindings.items()
                        }
                        roots_revalidated = all(
                            value.get("status") == "pass"
                            for value in root_revalidation.values()
                        )
                        if not roots_revalidated:
                            raw_failures.append(
                                "public PWA proof root paths changed during subprocess execution"
                            )
                finally:
                    for binding in post_run_root_bindings.values():
                        try:
                            os.close(int(binding["descriptor"]))
                        except (OSError, TypeError, ValueError):
                            pass

            revalidated_identities, _, _, revalidated_authority = _load_verified_public_pwa_proof_identities(
                source_root
            )
            identity_revalidated = (
                revalidated_identities.get("status") == "pass"
                and revalidated_identities.get("sha256") == identities.get("sha256")
                and revalidated_identities.get("fileIdentity") == identities.get("fileIdentity")
                and revalidated_authority.get("sha256") == authority.get("sha256")
            )
            if not identity_revalidated:
                raw_failures.append("public PWA proof identities changed during subprocess execution")
    raw_failures.extend(str(item) for item in result.get("failures", []) if str(item).strip())

    mirror = result.get("mirror") if isinstance(result.get("mirror"), dict) else {}
    generator_receipt = (
        mirror.get("generatorReceipt")
        if isinstance(mirror.get("generatorReceipt"), dict)
        else {}
    )
    input_snapshot_receipt = (
        result.get("inputSnapshot")
        if isinstance(result.get("inputSnapshot"), dict)
        else {}
    )
    asset_digest_inventory = (
        result.get("assetDigestInventory")
        if isinstance(result.get("assetDigestInventory"), dict)
        else {}
    )
    expected_input_receipt_rows = [
        {
            key: row[key]
            for key in (
                "root",
                "path",
                "sha256",
                "byteLength",
                "fileIdentity",
                "directoryTrace",
            )
        }
        for row in (
            input_snapshot_record.get("files")
            if isinstance(input_snapshot_record.get("files"), list)
            else []
        )
    ]
    proof_invariants = {
        "identityPinned": identities.get("status") == "pass",
        "identityRevalidated": identity_revalidated,
        "snapshotRevalidated": snapshot_revalidated,
        "verifierSealed": verifier_sealed,
        "generatorSealed": generator_sealed,
        "inputManifestSealed": required_memfd_seals != 0
        and input_manifest_seals & required_memfd_seals == required_memfd_seals,
        "inputManifestBound": input_snapshot_receipt.get("sha256")
        == input_manifest_sha256
        and input_snapshot_receipt.get("checkedCount") == input_expected_count
        and input_snapshot_receipt.get("status") == "pass",
        "inputReceiptExact": input_snapshot_receipt.get("checked")
        == expected_input_receipt_rows
        and input_snapshot_receipt.get("stable") is True
        and input_snapshot_receipt.get("authorityMode")
        == "sealed_inherited_file_descriptors",
        "inputSnapshotRevalidated": input_snapshot_revalidated,
        "rootPathsRevalidated": roots_revalidated,
        "receiptDescriptorBound": receipt_descriptor_bound,
        "subprocessCompleted": subprocess_completed,
        "subprocessSucceeded": subprocess_return_code == 0,
        "verifierPass": result.get("status") == "pass",
        "mirrorContractV5": mirror.get("contract") == "play-install-mirror-v5",
        "inventoryContractV2": mirror.get("inventoryContract") == "play-install-mirror-required-inventory-v2",
        "policyIdentity": mirror.get("policyId") == PUBLIC_PWA_POLICY_ID,
        "exactAssetPolicyCount": mirror.get("assetPolicyCount") == PUBLIC_PWA_EXPECTED_ASSET_COUNT,
        "exactDependencyPolicyCount": mirror.get("dependencyPolicyCount") == PUBLIC_PWA_EXPECTED_DEPENDENCY_COUNT,
        "checkedAssetCount": isinstance(mirror.get("checked"), list)
        and len(mirror["checked"]) == PUBLIC_PWA_EXPECTED_ASSET_COUNT,
        "symlinkPolicy": mirror.get("symlinkPolicy") == "reject_all_components",
        "temporaryRegenerationPass": generator_receipt.get("status") == "pass",
        "generatorPolicyIdentity": generator_receipt.get("policyId") == PUBLIC_PWA_POLICY_ID,
        "generatorAssetPolicyCount": generator_receipt.get("assetPolicyCount") == PUBLIC_PWA_EXPECTED_ASSET_COUNT,
        "generatorDependencyPolicyCount": generator_receipt.get("dependencyPolicyCount") == PUBLIC_PWA_EXPECTED_DEPENDENCY_COUNT,
        "generatorSymlinkPolicy": generator_receipt.get("symlinkPolicy") == "reject_all_components",
        "generatorInputAuthority": generator_receipt.get("inputAuthorityMode")
        == "sealed_trusted_payload_provider",
        "generatorExecutionIdentity": mirror.get("trustedGeneratorSha256")
        == identities.get("sha256", {}).get("generator"),
        "siblingPlaySourceValidated": mirror.get("siblingPlaySourceValidated") is True,
        "assetDigestInventoryContract": asset_digest_inventory.get("contractName")
        == PUBLIC_PWA_ASSET_DIGEST_INVENTORY_CONTRACT,
        "assetDigestInventoryCount": asset_digest_inventory.get("assetCount")
        == PUBLIC_PWA_ASSET_DIGEST_INVENTORY_COUNT,
        "assetDigestInventorySha256": re.fullmatch(
            r"[0-9a-f]{64}",
            str(asset_digest_inventory.get("sha256") or ""),
        )
        is not None,
    }
    for name, passed in proof_invariants.items():
        if not passed:
            raw_failures.append(f"proof invariant failed: {name}")
    sanitized = [sanitize_public_pwa_proof_detail(item, source_root) for item in raw_failures]
    bounded = sanitized[:MAX_PUBLIC_PWA_PROOF_FAILURES]
    passed = all(proof_invariants.values()) and not raw_failures
    return {
        "contractName": "chummer.public_edge_pwa_static_preflight.v1",
        "status": "pass" if passed else "fail",
        "executionMode": "sealed_memfd_isolated_python_with_preexec_limits_and_descriptor_receipt",
        "checks": proof_invariants,
        "mirrorContract": str(mirror.get("contract") or ""),
        "inventoryContract": str(mirror.get("inventoryContract") or ""),
        "policyId": str(mirror.get("policyId") or ""),
        "checkedAssetCount": len(mirror.get("checked", [])) if isinstance(mirror.get("checked"), list) else 0,
        "expectedAssetCount": PUBLIC_PWA_EXPECTED_ASSET_COUNT,
        "expectedDependencyCount": PUBLIC_PWA_EXPECTED_DEPENDENCY_COUNT,
        "assetDigestInventory": asset_digest_inventory,
        "identity": identities,
        "inputSnapshot": {
            "contractName": PUBLIC_PWA_INPUT_SNAPSHOT_CONTRACT,
            "sha256": input_manifest_sha256,
            "expectedCount": input_expected_count,
            "checkedCount": input_snapshot_receipt.get("checkedCount", 0),
            "totalBytes": input_total_bytes,
            "manifestByteLimit": MAX_PUBLIC_PWA_SNAPSHOT_MANIFEST_BYTES,
            "totalByteLimit": MAX_PUBLIC_PWA_TOTAL_INPUT_BYTES,
            "manifestSeals": input_manifest_seals,
            "revalidated": input_snapshot_revalidated,
        },
        "rootRevalidation": root_revalidation,
        "snapshots": {
            role: {
                key: value
                for key, value in binding.items()
                if key
                in {
                    "role",
                    "sha256Expected",
                    "sha256Actual",
                    "snapshotLinkCount",
                    "snapshotWriteBits",
                    "byteLength",
                    "checks",
                    "status",
                    "error",
                }
            }
            for role, binding in refreshed_snapshots.items()
        },
        "subprocess": {
            "completed": subprocess_completed,
            "returnCode": subprocess_return_code,
            "timeoutSeconds": PUBLIC_PWA_PROOF_TIMEOUT_SECONDS,
            "outputMode": "discarded",
            "receiptMode": "sealed_inherited_memfd",
            "receiptSeals": receipt_seals,
            "receiptByteLimit": MAX_PUBLIC_PWA_PROOF_RECEIPT_BYTES,
            "interpreter": {
                "flags": ["-I", "-S"],
                "wrapperGate": [
                    "isolated",
                    "no_site",
                    "ignore_environment",
                    "safe_path",
                ],
                "pythonNoUserSiteEnvironment": "1",
            },
            "resourceLimits": {
                "installationPhase": "linux_preexec_before_python_interpreter_startup",
                "addressSpaceBytes": PUBLIC_PWA_CHILD_ADDRESS_SPACE_BYTES,
                "cpuSeconds": PUBLIC_PWA_CHILD_CPU_SECONDS,
                "fileBytes": PUBLIC_PWA_CHILD_FILE_BYTES,
                "openFiles": PUBLIC_PWA_CHILD_OPEN_FILES,
            },
        },
        "failureCount": len(sanitized),
        "failures": bounded,
        "failuresTruncated": len(sanitized) > len(bounded),
        "failureLimit": MAX_PUBLIC_PWA_PROOF_FAILURES,
        "detailCharacterLimit": MAX_PUBLIC_PWA_PROOF_DETAIL_CHARS,
    }


def overlay_marker_findings(overlay_root: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    return marker_findings(
        overlay_root,
        required_markers=PUBLIC_EDGE_REQUIRED_OVERLAY_MARKERS,
        forbidden_markers_map=PUBLIC_EDGE_FORBIDDEN_OVERLAY_MARKERS,
        scope="overlay",
        missing_finding_id="public_edge_overlay_marker_missing",
        forbidden_finding_id="public_edge_overlay_marker_forbidden",
    )


def overlay_build_info_source_fingerprint_check(source_root: Path, overlay_root: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    build_info_path = overlay_root / ".codex-studio" / "runtime" / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    payload = load_json_file(build_info_path)
    recorded = payload.get("sourceFingerprint") if isinstance(payload.get("sourceFingerprint"), dict) else {}
    recorded_staged_payload_fingerprint = (
        payload.get("stagedPayloadFingerprint")
        if isinstance(payload.get("stagedPayloadFingerprint"), dict)
        else {}
    )
    recorded_payload_mode_receipt = (
        payload.get("payloadModeReceipt")
        if isinstance(payload.get("payloadModeReceipt"), dict)
        else {}
    )
    recorded_full_deployment_digest = (
        payload.get("fullDeploymentDigest")
        if isinstance(payload.get("fullDeploymentDigest"), dict)
        else {}
    )
    fingerprint_module = load_overlay_fingerprint_module()
    staged_payload_error = ""
    try:
        expected_staged_payload_fingerprint = overlay_staged_payload_fingerprint(
            overlay_root
        )
    except RuntimeError as exc:
        expected_staged_payload_fingerprint = {}
        staged_payload_error = str(exc)
    payload_mode_binding: dict[str, Any] = {
        "status": "fail",
        "failures": ["payload_mode_receipt_missing"],
    }
    if recorded_payload_mode_receipt:
        try:
            payload_mode_binding = (
                fingerprint_module.validate_payload_modes_against_receipt(
                    overlay_root,
                    recorded_payload_mode_receipt,
                )
            )
        except RuntimeError as exc:
            payload_mode_binding = {
                "status": "fail",
                "failures": ["payload_mode_receipt_invalid"],
                "error": str(exc),
            }
    recorded_files = recorded.get("files") if isinstance(recorded.get("files"), dict) else {}
    expected = overlay_source_fingerprint(source_root)
    expected_full_deployment_digest = fingerprint_module.full_deployment_digest(
        expected,
        expected_staged_payload_fingerprint,
    )
    recomputed_recorded_full_deployment_digest = fingerprint_module.full_deployment_digest(
        recorded,
        recorded_staged_payload_fingerprint,
    )
    expected_files = expected["files"] if isinstance(expected.get("files"), dict) else {}
    missing_keys: list[str] = []
    mismatched_keys: list[str] = []
    semantic_mismatches: list[str] = []
    if not recorded_payload_mode_receipt:
        missing_keys.append("payloadModeReceipt")
    if staged_payload_error:
        mismatched_keys.append("stagedPayloadShapeOrMode")
    if payload_mode_binding.get("status") != "pass":
        mismatched_keys.append("payloadModeReceiptCurrentDeployment")
    required_exact_fields: dict[str, object] = {
        "contractName": "chummer.public_edge_portal_overlay_publish.v1",
        "status": "pass",
        "activationStatus": "activated",
        "landingMarkerStatus": "pass",
        "landingHasTurnAnchor": True,
        "landingHasTurnAnchorRedirect": True,
        "landingHasBuildPublicInstallHandoff": True,
        "landingHasPlayPublicInstallHandoff": True,
        "landingRetiredMarkersAbsent": True,
        "landingBrowserRedirectStatus": "pass",
        "landingBrowserRedirectExpectedPath": "/mobile/player",
        "landingBrowserRedirectExpectedHash": "#turn-runsite-card",
        "landingBrowserRedirectExpectedQuery": "",
        "landingBrowserRedirectFinalQuery": "",
        "landingBrowserRedirectQueryDropped": True,
        "landingBrowserRedirectPathMatches": True,
        "landingBrowserRedirectHashMatches": True,
        "landingMissingMarkerCount": 0,
        "landingForbiddenMarkerCount": 0,
    }
    for field, expected_value in required_exact_fields.items():
        if payload.get(field) != expected_value:
            semantic_mismatches.append(field)
    recorded_source_root = str(payload.get("sourceRoot") or "").strip()
    try:
        source_root_matches = bool(
            recorded_source_root
            and Path(recorded_source_root).resolve() == source_root.resolve()
        )
    except OSError:
        source_root_matches = False
    if not source_root_matches:
        semantic_mismatches.append("sourceRoot")

    recorded_aggregate = str(recorded.get("aggregateSha256") or "").strip()
    expected_aggregate = str(expected.get("aggregateSha256") or "").strip()
    recorded_build_inputs = (
        recorded.get("buildInputs") if isinstance(recorded.get("buildInputs"), dict) else {}
    )
    expected_build_inputs = (
        expected.get("buildInputs") if isinstance(expected.get("buildInputs"), dict) else {}
    )
    recorded_build_aggregate = str(
        recorded_build_inputs.get("aggregateSha256") or ""
    ).strip()
    expected_build_aggregate = str(
        expected_build_inputs.get("aggregateSha256") or ""
    ).strip()
    recorded_build_count = recorded_build_inputs.get("fileCount")
    expected_build_count = expected_build_inputs.get("fileCount")
    recorded_build_algorithm = str(recorded_build_inputs.get("algorithm") or "").strip()
    expected_build_algorithm = str(expected_build_inputs.get("algorithm") or "").strip()
    recorded_overlay_payload_inputs = (
        recorded.get("overlayPayloadInputs")
        if isinstance(recorded.get("overlayPayloadInputs"), dict)
        else {}
    )
    expected_overlay_payload_inputs = (
        expected.get("overlayPayloadInputs")
        if isinstance(expected.get("overlayPayloadInputs"), dict)
        else {}
    )
    recorded_overlay_payload_algorithm = str(
        recorded_overlay_payload_inputs.get("algorithm") or ""
    ).strip()
    expected_overlay_payload_algorithm = str(
        expected_overlay_payload_inputs.get("algorithm") or ""
    ).strip()
    recorded_overlay_payload_aggregate = str(
        recorded_overlay_payload_inputs.get("aggregateSha256") or ""
    ).strip()
    expected_overlay_payload_aggregate = str(
        expected_overlay_payload_inputs.get("aggregateSha256") or ""
    ).strip()
    recorded_overlay_payload_count = recorded_overlay_payload_inputs.get("fileCount")
    expected_overlay_payload_count = expected_overlay_payload_inputs.get("fileCount")
    if len(recorded_aggregate) != 64:
        missing_keys.append("sourceFingerprint.aggregateSha256")
    if recorded_build_algorithm != "sha256-canonical-path-content-size-v1":
        missing_keys.append("sourceFingerprint.buildInputs.algorithm")
    if len(recorded_build_aggregate) != 64:
        missing_keys.append("sourceFingerprint.buildInputs.aggregateSha256")
    if not isinstance(recorded_build_count, int) or isinstance(recorded_build_count, bool):
        missing_keys.append("sourceFingerprint.buildInputs.fileCount")
    if recorded_overlay_payload_algorithm != "sha256-canonical-path-content-size-v1":
        missing_keys.append("sourceFingerprint.overlayPayloadInputs.algorithm")
    if len(recorded_overlay_payload_aggregate) != 64:
        missing_keys.append("sourceFingerprint.overlayPayloadInputs.aggregateSha256")
    if not isinstance(recorded_overlay_payload_count, int) or isinstance(
        recorded_overlay_payload_count,
        bool,
    ):
        missing_keys.append("sourceFingerprint.overlayPayloadInputs.fileCount")
    recorded_staged_payload_algorithm = str(
        recorded_staged_payload_fingerprint.get("algorithm") or ""
    ).strip()
    recorded_staged_payload_aggregate = str(
        recorded_staged_payload_fingerprint.get("aggregateSha256") or ""
    ).strip()
    recorded_staged_payload_count = recorded_staged_payload_fingerprint.get("fileCount")
    recorded_staged_payload_exclusions = recorded_staged_payload_fingerprint.get(
        "excludedRelativePaths"
    )
    if (
        recorded_staged_payload_algorithm
        != fingerprint_module.STAGED_PAYLOAD_FINGERPRINT_ALGORITHM
    ):
        missing_keys.append("stagedPayloadFingerprint.algorithm")
    if len(recorded_staged_payload_aggregate) != 64:
        missing_keys.append("stagedPayloadFingerprint.aggregateSha256")
    if not isinstance(recorded_staged_payload_count, int) or isinstance(
        recorded_staged_payload_count,
        bool,
    ):
        missing_keys.append("stagedPayloadFingerprint.fileCount")
    if (
        recorded_staged_payload_exclusions
        != fingerprint_module.staged_payload_runtime_mount_exclusions()
    ):
        missing_keys.append("stagedPayloadFingerprint.excludedRelativePaths")
    recorded_full_deployment_contract = str(
        recorded_full_deployment_digest.get("contractName") or ""
    ).strip()
    recorded_full_deployment_algorithm = str(
        recorded_full_deployment_digest.get("algorithm") or ""
    ).strip()
    recorded_full_deployment_sha256 = str(
        recorded_full_deployment_digest.get("sha256") or ""
    ).strip()
    expected_full_deployment_sha256 = str(
        expected_full_deployment_digest.get("sha256") or ""
    ).strip()
    if (
        recorded_full_deployment_contract
        != fingerprint_module.FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME
    ):
        missing_keys.append("fullDeploymentDigest.contractName")
    if (
        recorded_full_deployment_algorithm
        != fingerprint_module.FULL_DEPLOYMENT_DIGEST_ALGORITHM
    ):
        missing_keys.append("fullDeploymentDigest.algorithm")
    if (
        len(recorded_full_deployment_sha256) != 64
        or any(character not in "0123456789abcdef" for character in recorded_full_deployment_sha256)
    ):
        missing_keys.append("fullDeploymentDigest.sha256")

    for key, expected_entry in expected_files.items():
        recorded_entry = recorded_files.get(key) if isinstance(recorded_files.get(key), dict) else {}
        expected_relative_path = str(expected_entry.get("relativePath") or "").strip()
        recorded_relative_path = str(recorded_entry.get("relativePath") or "").strip()
        expected_sha = str(expected_entry.get("sha256") or "").strip()
        recorded_sha = str(recorded_entry.get("sha256") or "").strip()
        if recorded_relative_path != expected_relative_path:
            missing_keys.append(f"sourceFingerprint.files.{key}.relativePath")
        if len(recorded_sha) != 64:
            missing_keys.append(f"sourceFingerprint.files.{key}.sha256")
        elif recorded_sha != expected_sha:
            mismatched_keys.append(key)

    critical_aggregate_matches = (
        len(recorded_aggregate) == 64 and recorded_aggregate == expected_aggregate
    )
    critical_file_details_match = not any(
        key in mismatched_keys
        or f"sourceFingerprint.files.{key}.relativePath" in missing_keys
        or f"sourceFingerprint.files.{key}.sha256" in missing_keys
        for key in expected_files
    )
    if len(recorded_aggregate) == 64 and expected_aggregate and not critical_aggregate_matches:
        mismatched_keys.append("aggregateSha256")
    build_inputs_match = (
        recorded_build_algorithm == "sha256-canonical-path-content-size-v1"
        and expected_build_algorithm == "sha256-canonical-path-content-size-v1"
        and len(recorded_build_aggregate) == 64
        and recorded_build_aggregate == expected_build_aggregate
        and isinstance(recorded_build_count, int)
        and not isinstance(recorded_build_count, bool)
        and recorded_build_count == expected_build_count
    )
    if len(recorded_build_aggregate) == 64 and not build_inputs_match:
        mismatched_keys.append("buildInputAggregateSha256")
    overlay_payload_inputs_match = (
        recorded_overlay_payload_algorithm == "sha256-canonical-path-content-size-v1"
        and expected_overlay_payload_algorithm == "sha256-canonical-path-content-size-v1"
        and len(recorded_overlay_payload_aggregate) == 64
        and recorded_overlay_payload_aggregate == expected_overlay_payload_aggregate
        and isinstance(recorded_overlay_payload_count, int)
        and not isinstance(recorded_overlay_payload_count, bool)
        and recorded_overlay_payload_count == expected_overlay_payload_count
    )
    if len(recorded_overlay_payload_aggregate) == 64 and not overlay_payload_inputs_match:
        mismatched_keys.append("overlayPayloadInputAggregateSha256")
    staged_payload_matches = fingerprint_module.fingerprint_envelope_matches(
        recorded_staged_payload_fingerprint,
        expected_staged_payload_fingerprint,
    )
    if len(recorded_staged_payload_aggregate) == 64 and not staged_payload_matches:
        mismatched_keys.append("stagedPayloadAggregateSha256")
    full_deployment_digest_matches_recorded_inputs = (
        recorded_full_deployment_digest
        == recomputed_recorded_full_deployment_digest
    )
    full_deployment_digest_matches_current = (
        recorded_full_deployment_digest == expected_full_deployment_digest
    )
    if (
        len(recorded_full_deployment_sha256) == 64
        and not full_deployment_digest_matches_recorded_inputs
    ):
        mismatched_keys.append("fullDeploymentDigestRecordedInputs")
    if (
        len(recorded_full_deployment_sha256) == 64
        and not full_deployment_digest_matches_current
    ):
        mismatched_keys.append("fullDeploymentDigestCurrentDeployment")
    aggregate_matches = (
        critical_aggregate_matches
        and critical_file_details_match
        and build_inputs_match
        and overlay_payload_inputs_match
        and staged_payload_matches
        and payload_mode_binding.get("status") == "pass"
        and full_deployment_digest_matches_recorded_inputs
        and full_deployment_digest_matches_current
    )

    findings: list[dict[str, str]] = []
    if missing_keys:
        findings.append(
            {
                "id": "public_edge_overlay_source_fingerprint_missing",
                "severity": "blocker",
                "scope": "overlay",
                "detail": "overlay build info is missing source fingerprint fields: " + ", ".join(sorted(set(missing_keys))),
            }
        )
    if mismatched_keys:
        findings.append(
            {
                "id": "public_edge_overlay_source_fingerprint_mismatch",
                "severity": "blocker",
                "scope": "overlay",
                "detail": "overlay build info source fingerprint does not match current source: " + ", ".join(sorted(set(mismatched_keys))),
            }
        )
    if semantic_mismatches:
        findings.append(
            {
                "id": "public_edge_overlay_build_info_contract_invalid",
                "severity": "blocker",
                "scope": "overlay",
                "detail": "overlay build info activation contract is invalid: "
                + ", ".join(sorted(set(semantic_mismatches))),
            }
        )

    return (
        findings,
        {
            "path": str(build_info_path),
            "present": build_info_path.is_file(),
            "recordedAggregateSha256": recorded_aggregate,
            "expectedAggregateSha256": expected_aggregate,
            "criticalAggregateMatchesCurrentSource": critical_aggregate_matches,
            "criticalFileDetailsMatchCurrentSource": critical_file_details_match,
            "recordedBuildInputAlgorithm": recorded_build_algorithm,
            "expectedBuildInputAlgorithm": expected_build_algorithm,
            "recordedBuildInputAggregateSha256": recorded_build_aggregate,
            "expectedBuildInputAggregateSha256": expected_build_aggregate,
            "recordedBuildInputFileCount": recorded_build_count,
            "expectedBuildInputFileCount": expected_build_count,
            "buildInputsMatchCurrentSource": build_inputs_match,
            "recordedOverlayPayloadInputAlgorithm": recorded_overlay_payload_algorithm,
            "expectedOverlayPayloadInputAlgorithm": expected_overlay_payload_algorithm,
            "recordedOverlayPayloadInputAggregateSha256": recorded_overlay_payload_aggregate,
            "expectedOverlayPayloadInputAggregateSha256": expected_overlay_payload_aggregate,
            "recordedOverlayPayloadInputFileCount": recorded_overlay_payload_count,
            "expectedOverlayPayloadInputFileCount": expected_overlay_payload_count,
            "overlayPayloadInputsMatchCurrentSource": overlay_payload_inputs_match,
            "recordedStagedPayloadFingerprint": recorded_staged_payload_fingerprint,
            "expectedStagedPayloadFingerprint": expected_staged_payload_fingerprint,
            "stagedPayloadMatchesRecordedFingerprint": staged_payload_matches,
            "recordedPayloadModeReceipt": recorded_payload_mode_receipt,
            "payloadModeBinding": payload_mode_binding,
            "stagedPayloadError": staged_payload_error,
            "recordedFullDeploymentDigest": recorded_full_deployment_digest,
            "recomputedRecordedFullDeploymentDigest": recomputed_recorded_full_deployment_digest,
            "expectedFullDeploymentDigest": expected_full_deployment_digest,
            "recordedFullDeploymentDigestSha256": recorded_full_deployment_sha256,
            "expectedFullDeploymentDigestSha256": expected_full_deployment_sha256,
            "fullDeploymentDigestMatchesRecordedInputs": full_deployment_digest_matches_recorded_inputs,
            "fullDeploymentDigestMatchesCurrentDeployment": full_deployment_digest_matches_current,
            "aggregateMatchesCurrentSource": aggregate_matches,
            "missingKeys": sorted(set(missing_keys)),
            "mismatchedKeys": sorted(set(mismatched_keys)),
            "semanticMismatches": sorted(set(semantic_mismatches)),
            "sourceRootMatches": source_root_matches,
        },
    )


def operational_mirror_root_findings() -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    findings: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []
    for mirror_name, mirror_root in PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS.items():
        resolved_root = mirror_root.resolve()
        root_present = resolved_root.is_dir()
        checks.append(
            {
                "mirror": mirror_name,
                "root": str(resolved_root),
                "rootPresent": root_present,
            }
        )
        if not root_present:
            findings.append(
                {
                    "id": "public_edge_operational_mirror_root_missing",
                    "severity": "blocker",
                    "scope": "source",
                    "detail": f"configured operational mirror {mirror_name} root is missing: {resolved_root}",
                }
            )

    return findings, checks


def operational_mirror_findings(source_root: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    canonical_sources: dict[str, str] = {}
    for field, relative_path, _, _ in PUBLIC_EDGE_OPERATIONAL_MIRROR_EXACT_PATH_SPECS:
        canonical_path = source_root / relative_path
        canonical_sources[field] = canonical_path.read_text(encoding="utf-8", errors="replace") if canonical_path.is_file() else ""

    findings, checks = operational_mirror_root_findings()
    checks_by_mirror = {check["mirror"]: check for check in checks}

    for mirror_name, mirror_root in PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS.items():
        resolved_root = mirror_root.resolve()
        check = checks_by_mirror[mirror_name]
        if not check["rootPresent"]:
            continue
        mirror_sources: dict[str, str] = {}

        for field, relative_path, label, finding_prefix in PUBLIC_EDGE_OPERATIONAL_MIRROR_EXACT_PATH_SPECS:
            canonical_source = canonical_sources[field]
            if not canonical_source:
                continue

            mirror_path = resolved_root / relative_path
            present = mirror_path.is_file()
            mirror_source = mirror_path.read_text(encoding="utf-8", errors="replace") if present else ""
            matches_canonical = present and mirror_source == canonical_source
            mirror_sources[field] = mirror_source
            check[f"{field}Present"] = present
            check[f"{field}Path"] = str(mirror_path)
            check[f"{field}MatchesCanonical"] = matches_canonical

            if not present:
                findings.append(
                    {
                        "id": f"{finding_prefix}_missing",
                        "severity": "blocker",
                        "scope": "source",
                        "detail": f"operational mirror {mirror_name} is missing {relative_path}",
                    }
                )
            elif not matches_canonical:
                findings.append(
                    {
                        "id": f"{finding_prefix}_drift",
                        "severity": "blocker",
                        "scope": "source",
                        "detail": f"operational mirror {mirror_name} {label} drifted from canonical {relative_path}",
                    }
                )

        status_view_present = bool(check.get("statusViewPresent"))
        controller_present = bool(check.get("publicLandingControllerPresent"))
        status_view_source = mirror_sources.get("statusView", "")
        controller_source = mirror_sources.get("publicLandingController", "")
        stale_status_heading_present = "<h1>Updated</h1>" in status_view_source if status_view_present else False
        status_controller_title_matches = controller_present and PUBLIC_EDGE_STATUS_CONTROLLER_NEEDLE in controller_source
        stale_status_controller_title_present = PUBLIC_EDGE_STALE_STATUS_CONTROLLER_NEEDLE in controller_source if controller_present else False
        check["staleStatusHeadingPresent"] = stale_status_heading_present
        check["controllerPresent"] = controller_present
        check["controllerPath"] = check.get("publicLandingControllerPath", str(resolved_root / PUBLIC_EDGE_STATUS_CONTROLLER_RELATIVE_PATH))
        check["statusControllerTitleMatchesCanonical"] = status_controller_title_matches
        check["staleStatusControllerTitlePresent"] = stale_status_controller_title_present
        if stale_status_heading_present:
            findings.append(
                {
                    "id": "public_edge_operational_mirror_stale_status_heading",
                    "severity": "blocker",
                    "scope": "source",
                    "detail": f"operational mirror {mirror_name} still renders the stale Updated /status heading",
                }
            )
        if controller_present and not status_controller_title_matches:
            findings.append(
                {
                    "id": "public_edge_operational_mirror_status_controller_drift",
                    "severity": "blocker",
                    "scope": "source",
                    "detail": f"operational mirror {mirror_name} lost the canonical /status chrome title contract",
                }
            )
        if stale_status_controller_title_present:
            findings.append(
                {
                    "id": "public_edge_operational_mirror_stale_status_controller_title",
                    "severity": "blocker",
                    "scope": "source",
                    "detail": f"operational mirror {mirror_name} still uses the stale Updated /status chrome title",
                }
            )

    return findings, checks


def source_requires_operational_mirror_check(source_root: Path) -> bool:
    resolved_source_root = source_root.resolve()
    if resolved_source_root == RUN_SERVICES_ROOT.resolve():
        return True
    return any(
        resolved_source_root == mirror_root.resolve()
        for mirror_root in PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS.values()
    )


def _bounded_runtime_detail(detail: object) -> str:
    normalized = str(detail or "").replace("\x00", "")
    if len(normalized) <= MAX_RUNTIME_PROOF_DETAIL_CHARS:
        return normalized
    return normalized[: MAX_RUNTIME_PROOF_DETAIL_CHARS - 3] + "..."


def _stable_bounded_file_capture(path: Path, *, max_bytes: int) -> dict[str, Any]:
    resolved_path = Path(os.path.abspath(os.fspath(path.expanduser())))
    result: dict[str, Any] = {
        "resolvedPath": resolved_path,
        "payload": b"",
        "metadata": None,
        "regularFile": False,
        "singleLink": False,
        "boundedPayload": False,
        "stableSnapshot": False,
        "pathStillBound": False,
        "failure": "",
    }
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(resolved_path, flags)
    except (OSError, ValueError) as exc:
        result["failure"] = _bounded_runtime_detail(
            f"file cannot be opened safely: {exc}"
        )
        return result

    try:
        before = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        result["failure"] = _bounded_runtime_detail(
            f"file metadata cannot be read safely: {exc}"
        )
        return result

    payload = b""
    read_failure = ""
    try:
        if stat.S_ISREG(before.st_mode) and 0 < before.st_size <= max_bytes:
            chunks: list[bytes] = []
            total = 0
            read_budget = max_bytes + 1
            while total < read_budget:
                chunk = os.read(
                    descriptor,
                    min(1024 * 1024, read_budget - total),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            payload = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        read_failure = _bounded_runtime_detail(f"file could not be read safely: {exc}")
        after = before
    finally:
        os.close(descriptor)

    stable_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    regular_file = stat.S_ISREG(after.st_mode)
    single_link = after.st_nlink == 1
    bounded_payload = (
        regular_file
        and 0 < after.st_size <= max_bytes
        and len(payload) == after.st_size
    )
    path_still_bound = False
    try:
        final_path_metadata = os.stat(resolved_path, follow_symlinks=False)
        path_still_bound = (
            final_path_metadata.st_dev,
            final_path_metadata.st_ino,
            final_path_metadata.st_mode,
            final_path_metadata.st_nlink,
            final_path_metadata.st_size,
            final_path_metadata.st_mtime_ns,
            final_path_metadata.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
    except (OSError, ValueError):
        path_still_bound = False

    result.update(
        {
            "payload": payload,
            "metadata": after,
            "regularFile": regular_file,
            "singleLink": single_link,
            "boundedPayload": bounded_payload,
            "stableSnapshot": stable_identity and not read_failure,
            "pathStillBound": path_still_bound,
            "failure": read_failure,
        }
    )
    return result


def _expected_release_channel_projection(
    receipt: dict[str, Any],
) -> dict[str, str] | None:
    if receipt.get("status") != "published":
        return None
    values = {field: receipt.get(field) for field in RELEASE_CHANNEL_BINDING_FIELDS}
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        return None
    if (
        values["channelId"] != values["channel"]
        or values["releaseVersion"] != values["version"]
    ):
        return None
    return {
        "status": "available",
        "path": RUNTIME_PROOF_RELEASE_CHANNEL_PATH,
        **values,
    }


def runtime_proof_bind_source_check(
    path: Path,
    *,
    runtime_proof_bind_source_sha256: str = "",
    release_channel_receipt: Path | None = None,
    release_channel_receipt_sha256: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    capture = _stable_bounded_file_capture(
        path,
        max_bytes=MAX_RUNTIME_PROOF_BIND_BYTES,
    )
    resolved_path = capture["resolvedPath"]
    metadata = capture.get("metadata")
    payload = capture.get("payload") or b""
    actual_mode = stat.S_IMODE(metadata.st_mode) if metadata is not None else 0
    checks = {
        "regularFile": bool(capture.get("regularFile")),
        "singleLink": bool(capture.get("singleLink")),
        "exactMode0644": (
            metadata is not None
            and actual_mode == PUBLIC_EDGE_RUNTIME_PROOF_BIND_MODE
        ),
        "boundedPayload": bool(capture.get("boundedPayload")),
        "stableSnapshot": bool(capture.get("stableSnapshot")),
        "pathStillBound": bool(capture.get("pathStillBound")),
        "digestMatchesExpected": False,
        "strictJsonObject": False,
        "canonicalJson": False,
        "semanticContract": False,
        "fresh": False,
        "releaseChannelAvailable": False,
        "releaseChannelReceiptStable": False,
        "releaseChannelReceiptDigestMatches": False,
        "releaseChannelProjectionMatches": False,
    }
    result: dict[str, Any] = {
        "status": "fail",
        "sourcePath": str(resolved_path),
        "expectedMode": f"{PUBLIC_EDGE_RUNTIME_PROOF_BIND_MODE:04o}",
        "actualMode": f"{actual_mode:04o}" if metadata is not None else "",
        "linkCount": metadata.st_nlink if metadata is not None else 0,
        "sizeBytes": metadata.st_size if metadata is not None else 0,
        "sha256": "",
        "expectedSha256": runtime_proof_bind_source_sha256,
        "generatedAt": "",
        "releaseChannelReceiptPath": (
            str(Path(os.path.abspath(os.fspath(release_channel_receipt.expanduser()))))
            if release_channel_receipt is not None
            else ""
        ),
        "releaseChannelReceiptExpectedSha256": release_channel_receipt_sha256,
        "releaseChannelReceiptActualSha256": "",
        "checks": checks,
        "failures": [],
    }
    failures: list[str] = []
    capture_failure = str(capture.get("failure") or "")
    if capture_failure:
        failures.append(f"runtime proof bind source {capture_failure}")
    if not checks["regularFile"]:
        failures.append("runtime proof bind source is not a regular file")
    if not checks["singleLink"]:
        failures.append("runtime proof bind source must have exactly one link")
    if not checks["exactMode0644"]:
        failures.append("runtime proof bind source must have exact mode 0644")
    if not checks["boundedPayload"]:
        failures.append(
            f"runtime proof bind source must contain 1..{MAX_RUNTIME_PROOF_BIND_BYTES} bytes"
        )
    if not checks["stableSnapshot"]:
        failures.append("runtime proof bind source changed while it was being captured")
    if not checks["pathStillBound"]:
        failures.append(
            "runtime proof bind source path changed after its exact bytes were validated"
        )

    expected_runtime_proof_sha256 = runtime_proof_bind_source_sha256
    if re.fullmatch(r"[0-9a-f]{64}", expected_runtime_proof_sha256) is None:
        failures.append(
            "runtime proof bind source requires an independently supplied lowercase SHA-256"
        )
    if payload and checks["boundedPayload"] and checks["stableSnapshot"]:
        result["sha256"] = hashlib.sha256(payload).hexdigest()
        checks["digestMatchesExpected"] = (
            result["sha256"] == expected_runtime_proof_sha256
        )
    if (
        re.fullmatch(r"[0-9a-f]{64}", expected_runtime_proof_sha256) is not None
        and not checks["digestMatchesExpected"]
    ):
        failures.append(
            "runtime proof bind source does not match its independently supplied SHA-256"
        )

    parsed: dict[str, Any] | None = None
    if (
        checks["boundedPayload"]
        and checks["stableSnapshot"]
        and checks["pathStillBound"]
    ):
        try:
            parsed = decode_strict_json_object(payload, label="runtime proof bind source")
            checks["strictJsonObject"] = True
        except StrictJsonContractError as exc:
            failures.append(_bounded_runtime_detail(exc))

    if parsed is not None:
        try:
            canonical_payload = canonical_json_bytes(
                parsed,
                label="runtime proof bind source",
            )
            checks["canonicalJson"] = payload == canonical_payload
        except StrictJsonContractError as exc:
            failures.append(_bounded_runtime_detail(exc))
        if not checks["canonicalJson"]:
            failures.append("runtime proof bind source must use canonical materializer JSON bytes")

        semantic_failures: list[str] = []
        try:
            with tempfile.TemporaryDirectory(
                prefix="chummer-runtime-proof-preflight-"
            ) as temp_root:
                snapshot_path = Path(temp_root) / resolved_path.name
                snapshot_path.write_bytes(payload)
                check_local_release_proof(snapshot_path, semantic_failures)
        except (OSError, UnicodeError, ValueError, OverflowError, RecursionError) as exc:
            semantic_failures.append(
                "local release proof validation could not complete safely "
                f"({type(exc).__name__})"
            )
        checks["semanticContract"] = not semantic_failures
        failures.extend(
            "runtime proof semantic contract: " + _bounded_runtime_detail(failure)
            for failure in semantic_failures[:MAX_RUNTIME_PROOF_FAILURES]
        )
        if len(semantic_failures) > MAX_RUNTIME_PROOF_FAILURES:
            failures.append(
                "runtime proof semantic contract returned "
                f"{len(semantic_failures) - MAX_RUNTIME_PROOF_FAILURES} additional failure(s)"
            )

        generated_at = parsed.get("generatedAt")
        generated_at_alias = parsed.get("generated_at")
        if (
            isinstance(generated_at, str)
            and generated_at
            and generated_at == generated_at_alias
        ):
            result["generatedAt"] = generated_at
            try:
                parsed_generated_at = datetime.fromisoformat(
                    generated_at.replace("Z", "+00:00")
                )
                if parsed_generated_at.tzinfo is None:
                    raise ValueError("timestamp has no timezone")
                age_seconds = (
                    (now or datetime.now(UTC))
                    - parsed_generated_at.astimezone(UTC)
                ).total_seconds()
                checks["fresh"] = (
                    -RUNTIME_PROOF_MAX_FUTURE_SKEW_SECONDS
                    <= age_seconds
                    <= RUNTIME_PROOF_MAX_AGE_SECONDS
                )
            except (TypeError, ValueError, OverflowError):
                checks["fresh"] = False
        if not checks["fresh"]:
            failures.append(
                "runtime proof bind source generatedAt/generated_at must match and be "
                "within the 24-hour freshness window"
            )

        release_channel = parsed.get("release_channel")
        checks["releaseChannelAvailable"] = (
            isinstance(release_channel, dict)
            and release_channel.get("status") == "available"
        )
        if not checks["releaseChannelAvailable"]:
            failures.append(
                "runtime proof bind source release_channel.status must be available"
            )

        expected_receipt_sha256 = release_channel_receipt_sha256.strip()
        if release_channel_receipt is None:
            failures.append("runtime proof requires an independently selected release-channel receipt")
        elif re.fullmatch(r"[0-9a-f]{64}", expected_receipt_sha256) is None:
            failures.append(
                "runtime proof requires an independently supplied lowercase release-channel receipt SHA-256"
            )
        else:
            receipt_capture = _stable_bounded_file_capture(
                release_channel_receipt,
                max_bytes=MAX_RELEASE_CHANNEL_RECEIPT_BYTES,
            )
            checks["releaseChannelReceiptStable"] = all(
                bool(receipt_capture.get(check_name))
                for check_name in (
                    "regularFile",
                    "singleLink",
                    "boundedPayload",
                    "stableSnapshot",
                    "pathStillBound",
                )
            )
            receipt_capture_failure = str(receipt_capture.get("failure") or "")
            if receipt_capture_failure:
                failures.append(
                    "release-channel receipt " + receipt_capture_failure
                )
            if not checks["releaseChannelReceiptStable"]:
                failures.append(
                    "release-channel receipt must remain one stable, bounded, single-link regular file"
                )
            else:
                receipt_payload = receipt_capture.get("payload") or b""
                actual_receipt_sha256 = hashlib.sha256(receipt_payload).hexdigest()
                result["releaseChannelReceiptActualSha256"] = actual_receipt_sha256
                checks["releaseChannelReceiptDigestMatches"] = (
                    actual_receipt_sha256 == expected_receipt_sha256
                )
                if not checks["releaseChannelReceiptDigestMatches"]:
                    failures.append(
                        "release-channel receipt does not match its independently supplied SHA-256"
                    )
                else:
                    try:
                        release_receipt = decode_strict_json_object(
                            receipt_payload,
                            label="release-channel receipt",
                        )
                    except StrictJsonContractError as exc:
                        failures.append(_bounded_runtime_detail(exc))
                    else:
                        expected_projection = _expected_release_channel_projection(
                            release_receipt
                        )
                        if expected_projection is None:
                            failures.append(
                                "release-channel receipt must publish one complete canonical binding"
                            )
                        else:
                            checks["releaseChannelProjectionMatches"] = (
                                release_channel == expected_projection
                            )
                            if not checks["releaseChannelProjectionMatches"]:
                                failures.append(
                                    "runtime proof release_channel must exactly match the independently selected release-channel receipt"
                                )

    result.update(
        {
            "status": "pass" if not failures else "fail",
            "failures": [_bounded_runtime_detail(failure) for failure in failures],
        }
    )
    return result


def verify(
    process_lines: list[str],
    allow_stale_foreign_build_locks: bool,
    allow_foreign_build_locks: bool = False,
    source_root: Path | None = None,
    check_source_markers: bool = True,
    overlay_root: Path | None = None,
    check_overlay_markers: bool = False,
    public_projection_snapshot_root: Path | None = None,
    runtime_proof_bind_source: Path | None = None,
    runtime_proof_bind_source_sha256: str = "",
    release_channel_receipt: Path | None = None,
    release_channel_receipt_sha256: str = "",
) -> dict[str, Any]:
    locks = matching_processes(process_lines)
    foreign_locks = [lock for lock in locks if lock.get("buildScope") == "foreign"]
    stale_looking_locks = [lock for lock in locks if lock.get("staleLooking") == "true"]
    stale_foreign_locks = [
        lock for lock in stale_looking_locks if lock.get("buildScope") == "foreign"
    ]
    auto_ignored_stale_foreign_locks = [
        lock
        for lock in stale_foreign_locks
        if (not allow_foreign_build_locks)
        and int(lock.get("elapsedSeconds") or "0") >= AUTO_IGNORE_STALE_FOREIGN_LOCK_SECONDS
    ]
    blocking_locks = [
        lock
        for lock in locks
        if not (
            (allow_foreign_build_locks and lock.get("buildScope") == "foreign")
            or lock in auto_ignored_stale_foreign_locks
            or (
                allow_stale_foreign_build_locks
                and lock.get("buildScope") == "foreign"
                and lock.get("staleLooking") == "true"
            )
        )
    ]
    ignored_foreign_locks = [lock for lock in foreign_locks if lock not in blocking_locks]
    findings = [
        {
            "id": "active_build_lane",
            "severity": "blocker",
            "detail": f"{lock['command']} pid {lock['pid']} matches {lock['matchedPatterns']}",
            "scope": lock.get("buildScope"),
            "staleLooking": lock.get("staleLooking"),
        }
        for lock in blocking_locks
    ]
    resolved_source_root = (source_root or resolve_default_source_root()).resolve()
    resolved_overlay_root = (overlay_root or resolve_default_overlay_root()).resolve() if check_overlay_markers else None
    marker_checks: list[dict[str, Any]] = []
    overlay_marker_checks: list[dict[str, Any]] = []
    overlay_build_info_source_fingerprint: dict[str, Any] = {}
    operational_mirror_checks: list[dict[str, Any]] = []
    public_pwa_static_proof: dict[str, Any] = {}
    public_pwa_docker_build_contract: dict[str, Any] = {}
    public_pwa_compose_context_contract: dict[str, Any] = {}
    public_projection_snapshot_receipt: dict[str, Any] = {}
    runtime_proof_bind_source_receipt: dict[str, Any] = {}
    if check_source_markers:
        marker_findings, marker_checks = source_marker_findings(resolved_source_root)
        findings.extend(marker_findings)
        for marker_check in marker_checks:
            if marker_check.get("path") == PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH:
                public_pwa_docker_build_contract = dict(
                    marker_check.get("dockerBuildContract") or {}
                )
            elif marker_check.get("path") == PUBLIC_EDGE_COMPOSE_RELATIVE_PATH:
                public_pwa_compose_context_contract = dict(
                    marker_check.get("dockerBuildContextContract") or {}
                )
        public_pwa_static_proof = execute_public_pwa_static_proof(resolved_source_root)
        if public_pwa_static_proof.get("status") != "pass":
            findings.append(
                {
                    "id": "public_edge_pwa_static_proof_failed",
                    "severity": "blocker",
                    "scope": "source",
                    "detail": "deterministic public PWA source proof failed; inspect the bounded preflight receipt",
                }
            )
        if source_requires_operational_mirror_check(resolved_source_root):
            mirror_findings, operational_mirror_checks = operational_mirror_findings(
                RUN_SERVICES_ROOT.resolve()
            )
        else:
            mirror_findings, operational_mirror_checks = operational_mirror_root_findings()
        findings.extend(mirror_findings)
        selected_snapshot_root = (
            public_projection_snapshot_root
            or PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT
        )
        try:
            projection_snapshot = resolve_current_snapshot(selected_snapshot_root)
        except (OSError, ValueError, PublicProjectionBlocked):
            public_projection_snapshot_receipt = {
                "contractName": "chummer.public_projection_current/v1",
                "status": "fail",
                "snapshotRoot": str(selected_snapshot_root),
                "failure": "authenticated CURRENT public projection is unavailable",
            }
            runtime_proof_bind_source_receipt = {
                "status": "fail",
                "sourcePath": "",
                "failures": [
                    "runtime proof bind source was not resolved through authenticated CURRENT"
                ],
            }
        else:
            authenticated_proof_path = projection_snapshot.outputs[
                PUBLIC_EDGE_RUNTIME_PROOF_OUTPUT_NAME
            ]
            expected_output_sha256 = projection_snapshot.output_sha256[
                PUBLIC_EDGE_RUNTIME_PROOF_OUTPUT_NAME
            ]
            public_projection_snapshot_receipt = {
                "contractName": "chummer.public_projection_current/v1",
                "status": "pass",
                "snapshotRoot": str(selected_snapshot_root),
                "snapshotId": projection_snapshot.snapshot_id,
                "snapshotSha256": projection_snapshot.snapshot_sha256,
                "runtimeProofPath": str(authenticated_proof_path),
                "runtimeProofSha256": expected_output_sha256,
            }
            runtime_proof_bind_source_receipt = runtime_proof_bind_source_check(
                authenticated_proof_path,
                runtime_proof_bind_source_sha256=runtime_proof_bind_source_sha256,
                release_channel_receipt=release_channel_receipt,
                release_channel_receipt_sha256=release_channel_receipt_sha256,
            )
            runtime_proof_bind_source_receipt.update(
                {
                    "publicProjectionSnapshotId": projection_snapshot.snapshot_id,
                    "publicProjectionSnapshotSha256": projection_snapshot.snapshot_sha256,
                    "publicProjectionRuntimeProofSha256": expected_output_sha256,
                }
            )
            if runtime_proof_bind_source is not None and (
                os.path.abspath(runtime_proof_bind_source)
                != os.path.abspath(authenticated_proof_path)
            ):
                runtime_proof_bind_source_receipt["status"] = "fail"
                runtime_proof_bind_source_receipt.setdefault("failures", []).append(
                    "runtime proof bind source override does not equal authenticated CURRENT output"
                )
        if runtime_proof_bind_source_receipt.get("status") != "pass":
            findings.append(
                {
                    "id": "public_edge_runtime_proof_bind_source_invalid",
                    "severity": "blocker",
                    "scope": "source",
                    "detail": (
                        "runtime proof bind source is not a fresh, canonical, semantically valid "
                        "single-link regular 0644 artifact bound to an available release channel "
                        "and authenticated through the atomic CURRENT public projection"
                    ),
                }
            )
    if check_overlay_markers and resolved_overlay_root is not None:
        overlay_findings, overlay_marker_checks = overlay_marker_findings(resolved_overlay_root)
        findings.extend(overlay_findings)
        overlay_build_info_findings, overlay_build_info_source_fingerprint = overlay_build_info_source_fingerprint_check(
            resolved_source_root,
            resolved_overlay_root,
        )
        findings.extend(overlay_build_info_findings)
    return {
        "contractName": "chummer.public_edge_deploy_preflight.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if not findings else "fail",
        "lockPatterns": LOCK_PATTERNS,
        "sourceRoot": str(resolved_source_root),
        "sourceMarkerChecks": marker_checks,
        "publicPwaDockerBuildContract": public_pwa_docker_build_contract,
        "publicPwaComposeContextContract": public_pwa_compose_context_contract,
        "publicPwaStaticProof": public_pwa_static_proof,
        "publicProjectionSnapshot": public_projection_snapshot_receipt,
        "runtimeProofBindSource": runtime_proof_bind_source_receipt,
        "operationalMirrorChecks": operational_mirror_checks,
        "operationalMirrorSync": {
            "checkCommand": PUBLIC_EDGE_OPERATIONAL_MIRROR_SYNC_CHECK_COMMAND,
            "applyCommand": PUBLIC_EDGE_OPERATIONAL_MIRROR_SYNC_APPLY_COMMAND,
            "applyRequiresCleanContractedTargets": True,
            "directOverlayCopyAllowed": False,
        },
        "overlayRoot": str(resolved_overlay_root) if resolved_overlay_root is not None else "",
        "overlayMarkerChecks": overlay_marker_checks,
        "overlayBuildInfoSourceFingerprint": overlay_build_info_source_fingerprint,
        "activeLockCount": len(locks),
        "foreignLockCount": len(foreign_locks),
        "ignoredForeignLockCount": len(ignored_foreign_locks),
        "autoIgnoredStaleForeignLockCount": len(auto_ignored_stale_foreign_locks),
        "staleLookingLockCount": len(stale_looking_locks),
        "staleForeignLockCount": len(stale_foreign_locks),
        "activeLocks": locks,
        "findings": findings,
        "foreignLocksIgnored": allow_foreign_build_locks,
        "allowForeignBuildLocks": allow_foreign_build_locks,
        "staleForeignLocksIgnored": allow_stale_foreign_build_locks,
        "allowStaleForeignBuildLocks": allow_stale_foreign_build_locks,
        "autoIgnoreStaleForeignLockSeconds": AUTO_IGNORE_STALE_FOREIGN_LOCK_SECONDS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail closed when public-edge rebuild would collide with active Chummer build lanes.")
    parser.add_argument("--ps-output-file", help="Read ps output from a file instead of the current system.")
    parser.add_argument(
        "--allow-stale-foreign-build-locks",
        action="store_true",
        help="Ignore stale build lanes that are not in local repository scope.",
    )
    parser.add_argument(
        "--allow-foreign-build-locks",
        action="store_true",
        help="Ignore all active build lanes that are not in local repository scope.",
    )
    parser.add_argument(
        "--source-root",
        default="",
        help="Run-services source root that the public-edge build will copy.",
    )
    parser.add_argument(
        "--skip-source-marker-check",
        action="store_true",
        help="Only check active build locks; do not validate public-edge source markers.",
    )
    parser.add_argument(
        "--overlay-root",
        default="",
        help="Mounted /app overlay root to validate alongside source markers. Defaults to the active public-edge overlay root unless skipped.",
    )
    parser.add_argument(
        "--skip-overlay-marker-check",
        action="store_true",
        help="Do not validate the active mounted /app overlay markers.",
    )
    parser.add_argument(
        "--public-projection-snapshot-root",
        default="",
        help="Root containing the authenticated atomic CURRENT public projection snapshot.",
    )
    parser.add_argument(
        "--runtime-proof-bind-source-sha256",
        default="",
        help="Independently supplied lowercase SHA-256 for the exact runtime proof bind source bytes.",
    )
    parser.add_argument(
        "--release-channel-receipt",
        default="",
        help="Independently selected canonical release-channel receipt used to bind the runtime proof projection.",
    )
    parser.add_argument(
        "--release-channel-receipt-sha256",
        default="",
        help="Independently supplied lowercase SHA-256 for --release-channel-receipt.",
    )
    parser.add_argument("--output", help="Write the JSON receipt to this path.")
    parser.add_argument("--json", action="store_true", help="Print a JSON receipt even on pass.")
    args = parser.parse_args(argv)
    if not args.skip_source_marker_check:
        if not args.public_projection_snapshot_root:
            parser.error(
                "full source preflight requires --public-projection-snapshot-root"
            )
        if re.fullmatch(
            r"[0-9a-f]{64}",
            args.runtime_proof_bind_source_sha256,
        ) is None:
            parser.error(
                "full source preflight requires --runtime-proof-bind-source-sha256 as lowercase SHA-256"
            )
        if not args.release_channel_receipt:
            parser.error(
                "full source preflight requires --release-channel-receipt"
            )
        if re.fullmatch(
            r"[0-9a-f]{64}",
            args.release_channel_receipt_sha256,
        ) is None:
            parser.error(
                "full source preflight requires --release-channel-receipt-sha256 as lowercase SHA-256"
            )

    try:
        if args.ps_output_file:
            process_lines = Path(args.ps_output_file).read_text(encoding="utf-8").splitlines()
        else:
            process_lines = process_lines_from_system()
        receipt = verify(
            process_lines,
            args.allow_stale_foreign_build_locks,
            allow_foreign_build_locks=args.allow_foreign_build_locks,
            source_root=Path(args.source_root) if args.source_root else None,
            check_source_markers=not args.skip_source_marker_check,
            overlay_root=Path(args.overlay_root) if args.overlay_root else None,
            check_overlay_markers=not args.skip_overlay_marker_check,
            public_projection_snapshot_root=(
                Path(args.public_projection_snapshot_root)
                if args.public_projection_snapshot_root
                else None
            ),
            runtime_proof_bind_source_sha256=args.runtime_proof_bind_source_sha256,
            release_channel_receipt=(
                Path(args.release_channel_receipt)
                if args.release_channel_receipt
                else None
            ),
            release_channel_receipt_sha256=args.release_channel_receipt_sha256,
        )
    except Exception as exc:
        receipt = {
            "contractName": "chummer.public_edge_deploy_preflight.v1",
            "generatedAtUtc": datetime.now(UTC).isoformat(),
            "status": "fail",
            "findings": [{"id": "verification_error", "severity": "blocker", "detail": str(exc)}],
        }

    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    if args.json or args.output or receipt["status"] != "pass":
        sys.stdout.write(rendered)
    else:
        print("public_edge_deploy_preflight:ok")
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
