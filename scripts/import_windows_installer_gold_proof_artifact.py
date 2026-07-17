#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import ctypes
import fcntl
import hashlib
import io
import json
import math
import os
import pwd
import secrets
import shlex
import shutil
import signal
import stat as stat_module
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import zipfile
import zlib
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from writable_temp_root import configure_process_tmpdir


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOADS_ROOT = ROOT / "Chummer.Portal" / "downloads"
DEFAULT_INTAKE_REQUEST = ROOT / ".codex-studio" / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
STARTUP_RECEIPT_NAME = "startup-smoke-avalonia-win-x64.receipt.json"
VISUAL_SOURCE_NAME = "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_windows_installer_visual_audit.py"
REQUIRED_SURFACES = {"install-progress", "completion"}
PYTHON_EXECUTABLE = Path("/usr/bin/python3").resolve()
POST_IMPORT_PLAN_CONTRACT = "chummer.windows_installer_gold_proof_post_import_plan.v1"
POST_IMPORT_PLAN_AUTHORITY = "code_owned_fixed_argv"
POST_IMPORT_FIXED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
MAX_ZIP_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ZIP_MEMBER_COUNT = 128
MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 200.0
MAX_ZIP_MEMBER_PATH_BYTES = 240
MAX_ZIP_MEMBER_PATH_DEPTH = 12
ALLOWED_ZIP_COMPRESSION_TYPES = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
MAX_SCREENSHOT_COUNT = 16
MAX_SCREENSHOT_BYTES = 16 * 1024 * 1024
MIN_SCREENSHOT_WIDTH = 320
MIN_SCREENSHOT_HEIGHT = 180
MAX_SCREENSHOT_WIDTH = 7680
MAX_SCREENSHOT_HEIGHT = 4320
POST_IMPORT_LOCAL_TIMEOUT_SECONDS = 900.0
POST_IMPORT_EXTERNAL_TIMEOUT_SECONDS = 300.0
POST_IMPORT_TERMINATION_GRACE_SECONDS = 5.0
POST_IMPORT_DESCENDANT_SETTLE_SECONDS = 5.0
POST_IMPORT_STABLE_ZERO_SECONDS = 1.0
POST_IMPORT_EARLY_DESCENDANT_OBSERVATION_SECONDS = 2.0
POST_IMPORT_DESCENDANT_OBSERVATION_INTERVAL_SECONDS = 0.005
POST_IMPORT_CONTAINMENT_ENVIRONMENT_KEY = "CHUMMER_POST_IMPORT_CONTAINMENT_NONCE"
MAX_PROC_ENVIRON_BYTES = 4 * 1024 * 1024
PROOF_GENERATION_CONTRACT = "chummer.windows_installer_proof_generation.v1"
PROOF_PUBLICATION_CONTRACT = "chummer.windows_installer_proof_generation_publication.v1"
PROOF_CONTROL_DIRECTORY = ".windows-installer-proof"
PROOF_GENERATIONS_DIRECTORY = "generations"
PROOF_CURRENT_LINK = "current"
PROOF_LOCK_FILE = "publish.lock"
PROOF_RECOVERY_JOURNAL = "recovery-journal.json"
PROOF_GENERATION_MANIFEST = "generation-manifest.json"
VISUAL_PUBLIC_ANCHOR_TARGET = (
    "../.windows-installer-proof/current/visual-audit/windows-installer"
)
PYTHON_DEPENDENCY_BUNDLE_CONTRACT = "chummer.code_owned_python_dependency_bundle.v1"
SEALED_PYTHON_LAUNCHER_SOURCE = r'''
import base64
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys

logical_script = os.path.abspath(sys.argv[1])
script_fd = int(sys.argv[2])
bundle_fd = int(sys.argv[3])
script_args = sys.argv[4:]
with open(f"/proc/self/fd/{script_fd}", "rb", buffering=0) as handle:
    script_bytes = handle.read()
with open(f"/proc/self/fd/{bundle_fd}", "rb", buffering=0) as handle:
    bundle = json.loads(handle.read().decode("utf-8"))
sources = {
    os.path.abspath(path): base64.b64decode(row["source_base64"], validate=True)
    for path, row in bundle["files"].items()
}
roots = [os.path.abspath(path) for path in bundle["roots"]]

def _is_governed_path(path):
    if not path:
        return False
    candidate = os.path.abspath(path)
    for root in roots:
        try:
            if os.path.commonpath([candidate, root]) == root:
                return True
        except ValueError:
            continue
    return False

class _SealedSourceLoader(importlib.abc.Loader):
    def __init__(self, fullname, logical_path, source, is_package):
        self.fullname = fullname
        self.logical_path = logical_path
        self.source = source
        self.is_package = is_package

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = self.logical_path
        module.__cached__ = None
        if self.is_package:
            module.__package__ = self.fullname
            module.__path__ = [os.path.dirname(self.logical_path)]
        else:
            module.__package__ = self.fullname.rpartition(".")[0]
        exec(compile(self.source, self.logical_path, "exec"), module.__dict__, module.__dict__)

class _SealedSourceFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = list(path) if path is not None else list(sys.path)
        for raw_base in search_dirs:
            if not raw_base:
                continue
            base = os.path.abspath(raw_base)
            file_candidate = os.path.join(base, tail + ".py")
            package_candidate = os.path.join(base, tail, "__init__.py")
            for logical_path, is_package in (
                (file_candidate, False),
                (package_candidate, True),
            ):
                source = sources.get(logical_path)
                if source is None:
                    continue
                loader = _SealedSourceLoader(fullname, logical_path, source, is_package)
                return importlib.util.spec_from_loader(
                    fullname,
                    loader,
                    origin=logical_path,
                    is_package=is_package,
                )
        return None

class _GovernedRootBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        live_spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if live_spec is None:
            return None
        governed_locations = []
        origin = getattr(live_spec, "origin", None)
        if origin not in {None, "built-in", "frozen"} and _is_governed_path(origin):
            governed_locations.append(origin)
        for location in list(getattr(live_spec, "submodule_search_locations", None) or []):
            if _is_governed_path(location):
                governed_locations.append(location)
        if governed_locations:
            raise ImportError(
                "unsealed Python import under governed root is forbidden: "
                + fullname
                + " -> "
                + ", ".join(governed_locations)
            )
        return None

_original_spec_from_file_location = importlib.util.spec_from_file_location

def _sealed_spec_from_file_location(name, location, *args, **kwargs):
    logical_path = os.path.abspath(os.fspath(location))
    if not _is_governed_path(logical_path):
        return _original_spec_from_file_location(name, location, *args, **kwargs)
    source = sources.get(logical_path)
    if source is None:
        raise ImportError(
            "unsealed spec_from_file_location under governed root is forbidden: "
            + name
            + " -> "
            + logical_path
        )
    is_package = os.path.basename(logical_path) == "__init__.py"
    loader = _SealedSourceLoader(name, logical_path, source, is_package)
    return importlib.util.spec_from_loader(
        name,
        loader,
        origin=logical_path,
        is_package=is_package,
    )

script_dir = os.path.dirname(logical_script)
sys.meta_path[:0] = [_SealedSourceFinder(), _GovernedRootBlocker()]
importlib.util.spec_from_file_location = _sealed_spec_from_file_location
sys.path[:] = [script_dir, *[root for root in roots if root != script_dir], *sys.path]
sys.argv[:] = [logical_script, *script_args]
globals_dict = {
    "__name__": "__main__",
    "__file__": logical_script,
    "__package__": None,
    "__cached__": None,
    "__spec__": None,
}
exec(compile(script_bytes, logical_script, "exec"), globals_dict, globals_dict)
'''.strip()
SEALED_PYTHON_LAUNCHER_SHA256 = hashlib.sha256(
    SEALED_PYTHON_LAUNCHER_SOURCE.encode("utf-8")
).hexdigest().lower()

configure_process_tmpdir(workspace_root=ROOT.parent)


def load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json: {path} ({exc})") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"json root is not an object: {path}")
    return loaded


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return load_json(path)
    except SystemExit:
        return {}


def load_intake_payload_for_import(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise SystemExit(f"intake request not found: {path}")
    payload = load_json(path)
    promoted_digest = promoted_digest_from_intake(payload)
    if not promoted_digest:
        raise SystemExit(
            "intake request is missing the promoted installer digest required for proof import: "
            f"{path}"
        )
    return payload


def ensure_safe_member(member: str) -> Path:
    if not member or "\x00" in member or "\\" in member:
        raise SystemExit(f"unsafe zip member path: {member!r}")
    if len(member.encode("utf-8")) > MAX_ZIP_MEMBER_PATH_BYTES:
        raise SystemExit(f"zip member path exceeds byte bound: {member}")
    path = Path(member)
    windows_path = PureWindowsPath(member)
    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in path.parts
        or ".." in windows_path.parts
    ):
        raise SystemExit(f"unsafe zip member path: {member}")
    normalized_parts = [part for part in path.parts if part not in {"", "."}]
    if not normalized_parts:
        raise SystemExit(f"unsafe empty zip member path: {member!r}")
    if len(normalized_parts) > MAX_ZIP_MEMBER_PATH_DEPTH:
        raise SystemExit(f"zip member path exceeds depth bound: {member}")
    normalized = Path(*normalized_parts)
    if len(normalized.as_posix().encode("utf-8")) > MAX_ZIP_MEMBER_PATH_BYTES:
        raise SystemExit(f"zip member path exceeds byte bound: {member}")
    return normalized


def validate_zip_archive(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, Path]]:
    members = archive.infolist()
    if len(members) > MAX_ZIP_MEMBER_COUNT:
        raise SystemExit(
            f"proof artifact zip exceeds member-count bound: {len(members)} > {MAX_ZIP_MEMBER_COUNT}"
        )
    rows: list[tuple[zipfile.ZipInfo, Path]] = []
    seen_names: set[str] = set()
    file_names: set[str] = set()
    all_names: set[str] = set()
    total_uncompressed = 0
    for info in members:
        normalized = ensure_safe_member(info.filename)
        normalized_text = normalized.as_posix().rstrip("/")
        normalized_key = unicodedata.normalize("NFC", normalized_text).casefold()
        if normalized_key in seen_names:
            raise SystemExit(f"proof artifact zip contains duplicate member path: {info.filename}")
        seen_names.add(normalized_key)
        all_names.add(normalized_key)
        if info.flag_bits & 0x1:
            raise SystemExit(f"proof artifact zip contains encrypted member: {info.filename}")
        if info.compress_type not in ALLOWED_ZIP_COMPRESSION_TYPES:
            raise SystemExit(f"proof artifact zip uses unsupported compression: {info.filename}")
        unix_mode = (int(info.external_attr) >> 16) & 0xFFFF
        file_type = stat_module.S_IFMT(unix_mode)
        if info.is_dir():
            if file_type not in {0, stat_module.S_IFDIR}:
                raise SystemExit(f"proof artifact zip contains invalid directory member: {info.filename}")
        else:
            if file_type not in {0, stat_module.S_IFREG}:
                raise SystemExit(f"proof artifact zip contains non-regular member: {info.filename}")
            file_names.add(normalized_key)
            if int(info.file_size) > MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES:
                raise SystemExit(f"proof artifact zip member exceeds expanded-size bound: {info.filename}")
            total_uncompressed += int(info.file_size)
            if total_uncompressed > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                raise SystemExit("proof artifact zip exceeds total expanded-size bound")
            compressed_size = int(info.compress_size)
            compression_ratio = (
                float("inf")
                if int(info.file_size) > 0 and compressed_size == 0
                else int(info.file_size) / max(compressed_size, 1)
            )
            if compression_ratio > MAX_ZIP_COMPRESSION_RATIO:
                raise SystemExit(
                    f"proof artifact zip member exceeds compression-ratio bound: {info.filename}"
                )
        rows.append((info, normalized))
    for file_name in file_names:
        prefix = file_name + "/"
        if any(name.startswith(prefix) for name in all_names):
            raise SystemExit(f"proof artifact zip file/directory path collision: {file_name}")
    return rows


def extracted_or_directory(source: Path, temp_root: Path) -> Path:
    if source.is_dir():
        raise SystemExit(
            "extracted directory proof artifacts are forbidden; provide the bounded ZIP bundle"
        )
    if not source.is_file():
        raise SystemExit(f"proof artifact not found: {source}")
    if source.suffix.lower() != ".zip":
        raise SystemExit(f"proof artifact must be a .zip: {source}")

    archive_lstat = _confined_regular_file_lstat(
        source,
        source.parent,
        "Windows gold-proof zip",
    )
    if int(archive_lstat.st_size) > MAX_ZIP_ARCHIVE_BYTES:
        raise SystemExit("proof artifact zip exceeds archive-size bound")
    archive_snapshot = stable_bundle_file_snapshot(
        source,
        source.parent,
        "Windows gold-proof zip",
    )
    if len(bytes(archive_snapshot["data"])) > MAX_ZIP_ARCHIVE_BYTES:
        raise SystemExit("proof artifact zip exceeds archive-size bound")
    output = temp_root / "windows-installer-gold-proof"
    output.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(bytes(archive_snapshot["data"])))
    except zipfile.BadZipFile:
        raise
    with archive:
        rows = validate_zip_archive(archive)
        for info, normalized in rows:
            destination = output / normalized
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(info)
            if len(data) != int(info.file_size):
                raise SystemExit(f"proof artifact zip member size drifted during extraction: {info.filename}")
            copy_stable_snapshot(
                {
                    "data": data,
                    "sha256": hashlib.sha256(data).hexdigest().lower(),
                },
                destination,
            )
    return output


def find_unique(root: Path, name: str) -> Path:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if not matches:
        raise SystemExit(f"proof artifact is missing {name}")
    if len(matches) > 1:
        preferred = [path for path in matches if "Chummer.Portal" in path.parts]
        if len(preferred) == 1:
            return preferred[0]
        raise SystemExit(f"proof artifact contains multiple {name} files: {matches}")
    return matches[0]


def find_optional_unique(root: Path, name: str) -> Path | None:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if not matches:
        return None
    if len(matches) > 1:
        preferred = [path for path in matches if "Chummer.Portal" in path.parts]
        if len(preferred) == 1:
            return preferred[0]
        raise SystemExit(f"proof artifact contains multiple {name} files: {matches}")
    return matches[0]


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def normalized_surface(value: Any) -> str:
    surface = normalized(value).replace("_", "-").replace(" ", "-")
    aliases = {
        "progress": "install-progress",
        "install": "install-progress",
        "splash": "install-progress",
        "install-splash": "install-progress",
        "complete": "completion",
        "install-complete": "completion",
    }
    return aliases.get(surface, surface)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def program_file_binding(path: Path, role: str) -> dict[str, Any]:
    resolved = path.resolve()
    file_stat = resolved.stat()
    return {
        "role": role,
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "device": int(file_stat.st_dev),
        "inode": int(file_stat.st_ino),
        "size_bytes": int(file_stat.st_size),
        "mtime_ns": int(file_stat.st_mtime_ns),
        "process_id": int(os.getpid()),
    }


IMPORTER_PROGRAM_BINDING_AT_LOAD = program_file_binding(
    Path(__file__),
    "windows_installer_gold_proof_importer",
)
PYTHON_PROGRAM_BINDING_AT_LOAD = program_file_binding(
    PYTHON_EXECUTABLE,
    "code_owned_python_interpreter",
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().lower()


def redacted_stream_receipt(value: str | None) -> dict[str, Any]:
    normalized_value = value or ""
    encoded = normalized_value.encode("utf-8", errors="replace")
    return {
        "redacted": True,
        "present": bool(normalized_value),
        "byte_count": len(encoded),
        "line_count": len(normalized_value.splitlines()),
        "sha256": hashlib.sha256(encoded).hexdigest().lower(),
    }


def code_owned_post_import_environment() -> dict[str, str]:
    temp_root = ROOT.parent / ".tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(account_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OPENSSL_CONF": "/dev/null",
        "PATH": POST_IMPORT_FIXED_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(temp_root.resolve()),
        "TZ": "UTC",
    }


_PRODUCTION_DEPENDENCY_BUNDLE_CACHE: tuple[bytes, dict[str, Any]] | None = None


def build_code_owned_python_dependency_bundle(
    roots: list[Path],
) -> tuple[bytes, dict[str, Any]]:
    normalized_roots = sorted(
        {_absolute_lexical_path(root) for root in roots},
        key=str,
    )
    files: dict[str, dict[str, Any]] = {}
    manifest_rows: list[dict[str, Any]] = []
    for root in normalized_roots:
        if not root.is_dir():
            raise SystemExit(f"code-owned Python dependency root is missing: {root}")
        for path in sorted(root.rglob("*.py"), key=str):
            snapshot = stable_bundle_file_snapshot(
                path,
                root,
                "code-owned Python dependency",
            )
            logical_path = str(snapshot["path"])
            files[logical_path] = {
                "sha256": str(snapshot["sha256"]),
                "source_base64": base64.b64encode(bytes(snapshot["data"])).decode("ascii"),
            }
            manifest_rows.append(
                {
                    "path": logical_path,
                    "sha256": str(snapshot["sha256"]),
                    "identity": dict(snapshot["identity"]),
                }
            )
    manifest = {
        "contract_name": PYTHON_DEPENDENCY_BUNDLE_CONTRACT,
        "roots": [str(root) for root in normalized_roots],
        "files": manifest_rows,
    }
    payload = {
        "contract_name": PYTHON_DEPENDENCY_BUNDLE_CONTRACT,
        "roots": manifest["roots"],
        "manifest_sha256": sha256_json(manifest),
        "files": files,
    }
    bundle_bytes = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    binding = {
        "contract_name": PYTHON_DEPENDENCY_BUNDLE_CONTRACT,
        "roots": manifest["roots"],
        "file_count": len(manifest_rows),
        "manifest_sha256": payload["manifest_sha256"],
        "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest().lower(),
        "bundle_size_bytes": len(bundle_bytes),
    }
    return bundle_bytes, binding


def production_code_owned_python_dependency_bundle() -> tuple[bytes, dict[str, Any]]:
    global _PRODUCTION_DEPENDENCY_BUNDLE_CACHE
    if _PRODUCTION_DEPENDENCY_BUNDLE_CACHE is None:
        _PRODUCTION_DEPENDENCY_BUNDLE_CACHE = build_code_owned_python_dependency_bundle(
            [ROOT / "scripts", ROOT.parent / "scripts"]
        )
    bundle_bytes, binding = _PRODUCTION_DEPENDENCY_BUNDLE_CACHE
    return bundle_bytes, dict(binding)


def _code_owned_script(relative_path: str) -> Path:
    candidate = (ROOT / relative_path).resolve()
    workspace_root = ROOT.parent.resolve()
    if not candidate.is_relative_to(workspace_root):
        raise SystemExit(f"post-import plan script escapes the workspace root: {relative_path}")
    if not candidate.is_file():
        raise SystemExit(f"post-import plan script is missing: {candidate}")
    return candidate


def _post_import_step_specs(
    downloads_root: Path,
    intake_request: Path,
    *,
    handoff_timestamp: str,
) -> list[tuple[str, str, list[str]]]:
    published_root = ROOT / ".codex-studio" / "published"
    workspace_published_root = ROOT.parent / ".codex-studio" / "published"
    verifier_sha256 = sha256_file(VERIFY_SCRIPT.resolve())
    return [
        (
            "verify_windows_installer_visual_audit",
            "scripts/verify_windows_installer_visual_audit.py",
            [
                "--downloads-root",
                str(downloads_root.resolve()),
                "--expected-verifier-sha256",
                verifier_sha256,
                "--output",
                str(published_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"),
            ],
        ),
        (
            "materialize_windows_installer_visual_audit_intake_request",
            "scripts/materialize_windows_installer_visual_audit_intake_request.py",
            ["--output", str(intake_request.resolve())],
        ),
        (
            "verify_windows_installer_visual_audit_intake_request",
            "scripts/verify_windows_installer_visual_audit_intake_request.py",
            ["--receipt", str(intake_request.resolve())],
        ),
        (
            "verify_flagship_product_readiness_gate",
            "scripts/verify_flagship_product_readiness_gate.py",
            [
                "--summary-output",
                str(published_root / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"),
            ],
        ),
        (
            "materialize_google_oauth_linking_operator_evidence_request",
            "scripts/materialize_google_oauth_linking_operator_evidence_request.py",
            ["--base-url", "https://chummer.run"],
        ),
        (
            "materialize_google_oauth_linking_proof",
            "scripts/materialize_google_oauth_linking_proof.py",
            ["--base-url", "https://chummer.run"],
        ),
        (
            "verify_google_oauth_linking_proof",
            "scripts/verify_google_oauth_linking_proof.py",
            [],
        ),
        (
            "materialize_ea_operator_readiness",
            "scripts/materialize_ea_operator_readiness.py",
            [],
        ),
        (
            "verify_ea_operator_readiness",
            "scripts/verify_ea_operator_readiness.py",
            [],
        ),
        (
            "materialize_mymedia_public_surface",
            "scripts/materialize_mymedia_public_surface.py",
            [],
        ),
        (
            "verify_mymedia_public_surface",
            "scripts/verify_mymedia_public_surface.py",
            [],
        ),
        (
            "materialize_release_ready_receipt",
            "scripts/materialize_release_ready_receipt.py",
            ["--force-global-verifier"],
        ),
        (
            "materialize_operator_release_dashboard",
            "scripts/materialize_operator_release_dashboard.py",
            [],
        ),
        (
            "materialize_hub_local_release_proof",
            "scripts/materialize_hub_local_release_proof.py",
            [
                str(published_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"),
                "https://chummer.run",
                str(ROOT / "docker-compose.public-edge.yml"),
                "300",
                "true",
            ],
        ),
        (
            "final_gold_janitor",
            "scripts/final_gold_janitor.py",
            ["--skip-materializers"],
        ),
        (
            "release_gate_common",
            "../scripts/release/_release_gate_common.py",
            [],
        ),
        (
            "materialize_chummer_flagship_surface_stack",
            "../scripts/materialize_chummer_flagship_surface_stack.py",
            [
                "--output",
                str(workspace_published_root / "CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json"),
            ],
        ),
        (
            "verify_chummer_flagship_surface_stack",
            "../scripts/verify_chummer_flagship_surface_stack.py",
            [
                "--receipt",
                str(workspace_published_root / "CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json"),
                "--require-flagship-pass",
            ],
        ),
        (
            "materialize_codex_flagship_handoff",
            "../scripts/materialize_codex_flagship_handoff.py",
            ["--timestamp", handoff_timestamp],
        ),
        (
            "sync_important_work_to_teable",
            "scripts/sync_important_work_to_teable.py",
            ["--sync"],
        ),
        (
            "attempt_flagship_public_stable_promotion",
            "../scripts/attempt_flagship_public_stable_promotion.py",
            [
                "--output",
                str(workspace_published_root / "FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json"),
            ],
        ),
    ]


def build_code_owned_post_import_plan(
    downloads_root: Path,
    intake_request: Path,
    *,
    handoff_timestamp: str | None = None,
    auto_importer_program_binding: dict[str, Any] | None = None,
    authorize_external_mutations: bool = False,
) -> dict[str, Any]:
    if not PYTHON_EXECUTABLE.is_file():
        raise SystemExit(f"code-owned Python interpreter is missing: {PYTHON_EXECUTABLE}")
    authority_path = Path(__file__).resolve()
    environment = code_owned_post_import_environment()
    environment_sha256 = sha256_json(environment)
    interpreter = dict(PYTHON_PROGRAM_BINDING_AT_LOAD)
    authority = {
        "path": str(authority_path),
        "sha256": str(IMPORTER_PROGRAM_BINDING_AT_LOAD["sha256"]),
    }
    auto_program = auto_importer_program_binding or program_file_binding(
        ROOT / "scripts" / "auto_import_windows_installer_gold_proof.py",
        "windows_installer_gold_proof_auto_importer",
    )
    program_bindings = {
        "importer": dict(IMPORTER_PROGRAM_BINDING_AT_LOAD),
        "auto_importer": dict(auto_program),
    }
    _dependency_bundle_bytes, dependency_bundle_binding = (
        production_code_owned_python_dependency_bundle()
    )
    launcher_binding = {
        "role": "sealed_python_logical_path_launcher",
        "sha256": SEALED_PYTHON_LAUNCHER_SHA256,
        "size_bytes": len(SEALED_PYTHON_LAUNCHER_SOURCE.encode("utf-8")),
    }
    program_bindings["python_dependency_bundle"] = dict(
        dependency_bundle_binding
    )
    program_bindings["sealed_python_launcher"] = launcher_binding
    program_sha256s = {
        key: str(value.get("sha256") or "")
        for key, value in program_bindings.items()
    }
    steps: list[dict[str, Any]] = []
    for ordinal, (step_id, relative_script, arguments) in enumerate(
        _post_import_step_specs(
            downloads_root,
            intake_request,
            handoff_timestamp=handoff_timestamp or now_iso(),
        ),
        start=1,
    ):
        script_path = _code_owned_script(relative_script)
        argv = [str(PYTHON_EXECUTABLE), str(script_path), *arguments]
        effect_class = {
            "sync_important_work_to_teable": "external_sync",
            "attempt_flagship_public_stable_promotion": "promotion_attempt",
        }.get(step_id, "local_validation_or_receipt")
        execution_phase = (
            "external_mutation"
            if effect_class in {"external_sync", "promotion_attempt"}
            else "validation_staging"
        )
        timeout_seconds = (
            POST_IMPORT_EXTERNAL_TIMEOUT_SECONDS
            if execution_phase == "external_mutation"
            else POST_IMPORT_LOCAL_TIMEOUT_SECONDS
        )
        binding = {
            "contract_name": POST_IMPORT_PLAN_CONTRACT,
            "authority_sha256": authority["sha256"],
            "cwd": str(ROOT.resolve()),
            "environment_sha256": environment_sha256,
            "interpreter_sha256": interpreter["sha256"],
            "program_sha256s": program_sha256s,
            "dependency_bundle_sha256": dependency_bundle_binding["bundle_sha256"],
            "launcher_sha256": SEALED_PYTHON_LAUNCHER_SHA256,
            "ordinal": ordinal,
            "step_id": step_id,
            "effect_class": effect_class,
            "execution_phase": execution_phase,
            "timeout_seconds": timeout_seconds,
            "termination_grace_seconds": POST_IMPORT_TERMINATION_GRACE_SECONDS,
            "process_group_mode": "linux_child_subreaper_descendant_sweep",
            "zero_descendants_required": True,
            "script_sha256": sha256_file(script_path),
            "argv": argv,
        }
        steps.append(
            {
                **binding,
                "execution_binding_sha256": sha256_json(binding),
            }
        )

    plan_core = {
        "contract_name": POST_IMPORT_PLAN_CONTRACT,
        "authority": POST_IMPORT_PLAN_AUTHORITY,
        "authority_source": authority,
        "cwd": str(ROOT.resolve()),
        "environment": environment,
        "environment_sha256": environment_sha256,
        "interpreter": interpreter,
        "program_bindings": program_bindings,
        "process_termination_policy": {
            "mode": "linux_child_subreaper_descendant_sweep",
            "local_timeout_seconds": POST_IMPORT_LOCAL_TIMEOUT_SECONDS,
            "external_timeout_seconds": POST_IMPORT_EXTERNAL_TIMEOUT_SECONDS,
            "termination_grace_seconds": POST_IMPORT_TERMINATION_GRACE_SECONDS,
            "subreaper_required": True,
            "zero_descendants_required": True,
        },
        "external_mutation_authorization": {
            "requested": bool(authorize_external_mutations),
            "source": "code_owned_cli_opt_in" if authorize_external_mutations else "not_authorized",
            "intake_request_can_authorize": False,
        },
        "steps": steps,
    }
    return {**plan_core, "plan_sha256": sha256_json(plan_core)}


def request_post_import_gate_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    present = "post_import_gates" in payload
    requested = payload.get("post_import_gates")
    return {
        "present": present,
        "value_type": type(requested).__name__ if present else "absent",
        "item_count": len(requested) if isinstance(requested, list) else 0,
        "ignored": present,
        "authority": POST_IMPORT_PLAN_AUTHORITY,
        "reason": (
            "request-supplied post-import commands are non-authoritative metadata"
            if present
            else "no request-supplied post-import commands were present"
        ),
    }


def _plan_core(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def _step_binding(step: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in step.items()
        if key != "execution_binding_sha256"
    }


def _sealed_memfd_from_file(path: Path, expected_sha256: str, label: str) -> tuple[int, int]:
    if not hasattr(os, "memfd_create"):
        raise SystemExit("sealed memfd execution is unavailable on this host")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_descriptor = os.open(path, flags)
    try:
        before = os.fstat(source_descriptor)
        if not stat_module.S_ISREG(before.st_mode):
            raise SystemExit(f"{label} is not a regular file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(source_descriptor)
        if _stable_identity(before) != _stable_identity(after):
            raise SystemExit(f"{label} changed during sealed execution snapshot: {path}")
    finally:
        os.close(source_descriptor)
    data = b"".join(chunks)
    actual_sha256 = hashlib.sha256(data).hexdigest().lower()
    if actual_sha256 != expected_sha256:
        raise SystemExit(f"{label} SHA-256 binding drifted before sealed execution: {path}")

    memfd_flags = getattr(os, "MFD_CLOEXEC", 0) | getattr(os, "MFD_ALLOW_SEALING", 0)
    sealed_descriptor = os.memfd_create(label.replace(" ", "_"), memfd_flags)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(sealed_descriptor, data[offset:])
        os.lseek(sealed_descriptor, 0, os.SEEK_SET)
        seals = (
            getattr(fcntl, "F_SEAL_SEAL", 0)
            | getattr(fcntl, "F_SEAL_SHRINK", 0)
            | getattr(fcntl, "F_SEAL_GROW", 0)
            | getattr(fcntl, "F_SEAL_WRITE", 0)
        )
        fcntl.fcntl(sealed_descriptor, fcntl.F_ADD_SEALS, seals)
    except BaseException:
        os.close(sealed_descriptor)
        raise
    return sealed_descriptor, len(data)


def _sealed_memfd_from_bytes(data: bytes, expected_sha256: str, label: str) -> tuple[int, int]:
    actual_sha256 = hashlib.sha256(data).hexdigest().lower()
    if actual_sha256 != expected_sha256:
        raise SystemExit(f"{label} SHA-256 binding drifted before sealed execution")
    memfd_flags = getattr(os, "MFD_CLOEXEC", 0) | getattr(os, "MFD_ALLOW_SEALING", 0)
    descriptor = os.memfd_create(label.replace(" ", "_"), memfd_flags)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.lseek(descriptor, 0, os.SEEK_SET)
        seals = (
            getattr(fcntl, "F_SEAL_SEAL", 0)
            | getattr(fcntl, "F_SEAL_SHRINK", 0)
            | getattr(fcntl, "F_SEAL_GROW", 0)
            | getattr(fcntl, "F_SEAL_WRITE", 0)
        )
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, len(data)


_POST_IMPORT_EXECUTION_LOCK = threading.Lock()
_PR_SET_CHILD_SUBREAPER = 36
_PR_GET_CHILD_SUBREAPER = 37


def _require_linux_child_subreaper() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise SystemExit(
            f"Linux child-subreaper containment is unavailable: errno={error_number}"
        )
    enabled = ctypes.c_int(0)
    if libc.prctl(_PR_GET_CHILD_SUBREAPER, ctypes.byref(enabled), 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise SystemExit(
            f"Linux child-subreaper containment verification failed: errno={error_number}"
        )
    if enabled.value != 1:
        raise SystemExit("Linux child-subreaper containment did not remain enabled")


def _proc_process_table() -> dict[int, dict[str, int | str]]:
    rows: dict[int, dict[str, int | str]] = {}
    try:
        entries = os.scandir("/proc")
    except OSError as exc:
        raise SystemExit(f"process containment cannot inspect /proc: {exc}") from exc
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                stat_text = Path(entry.path, "stat").read_text(encoding="utf-8")
                close_parenthesis = stat_text.rfind(") ")
                if close_parenthesis < 0:
                    continue
                fields = stat_text[close_parenthesis + 2 :].split()
                rows[pid] = {
                    "pid": pid,
                    "state": fields[0],
                    "ppid": int(fields[1]),
                    "process_group": int(fields[2]),
                    "session": int(fields[3]),
                    "start_time_ticks": int(fields[19]),
                }
            except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError, ValueError):
                continue
    return rows


def _process_identity(row: dict[str, int | str]) -> tuple[int, int]:
    return int(row["pid"]), int(row["start_time_ticks"])


def _process_has_containment_environment_marker(
    pid: int,
    marker: bytes,
) -> bool:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            f"/proc/{pid}/environ",
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        chunks: list[bytes] = []
        remaining = MAX_PROC_ENVIRON_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_PROC_ENVIRON_BYTES:
            return False
        return marker in data.split(b"\x00")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _descendant_identities(
    table: dict[int, dict[str, int | str]],
    root_pid: int,
) -> set[tuple[int, int]]:
    descendants: set[tuple[int, int]] = set()
    frontier = {root_pid}
    while frontier:
        next_frontier: set[int] = set()
        for pid, row in table.items():
            if int(row["ppid"]) not in frontier:
                continue
            identity = _process_identity(row)
            if identity in descendants:
                continue
            descendants.add(identity)
            next_frontier.add(pid)
        frontier = next_frontier
    return descendants


def _identity_is_live(identity: tuple[int, int]) -> bool:
    pid, expected_start = identity
    row = _proc_process_table().get(pid)
    return row is not None and int(row["start_time_ticks"]) == expected_start


def _signal_identity(identity: tuple[int, int], signal_number: int) -> bool:
    pid, expected_start = identity
    row = _proc_process_table().get(pid)
    if row is None or int(row["start_time_ticks"]) != expected_start:
        return False
    try:
        os.kill(pid, signal_number)
        return True
    except ProcessLookupError:
        return False


def _signal_tracked_process_group(
    process_group: int,
    identities: set[tuple[int, int]],
    signal_number: int,
) -> bool:
    table = _proc_process_table()
    identity_set = set(identities)
    if not any(
        _process_identity(row) in identity_set
        and int(row["process_group"]) == process_group
        for row in table.values()
    ):
        return False
    try:
        os.killpg(process_group, signal_number)
        return True
    except ProcessLookupError:
        return False


def _reap_tracked_children(
    identities: set[tuple[int, int]],
    *,
    exclude_pid: int | None,
) -> int:
    reaped = 0
    for pid, _start_time in sorted(identities):
        if exclude_pid is not None and pid == exclude_pid:
            continue
        try:
            waited_pid, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            continue
        if waited_pid == pid:
            reaped += 1
    return reaped


def _contained_step_identities(
    supervisor_pid: int,
    baseline: set[tuple[int, int]],
    primary_identity: tuple[int, int],
    known: set[tuple[int, int]],
    *,
    containment_environment_marker: bytes | None = None,
    process_table_baseline: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    table = _proc_process_table()
    current_descendants = _descendant_identities(table, supervisor_pid)
    primary_pid, primary_start = primary_identity
    primary_row = table.get(primary_pid)
    if primary_row is not None and int(primary_row["start_time_ticks"]) == primary_start:
        known.add(primary_identity)
        known.update(_descendant_identities(table, primary_pid))
    known.update(identity for identity in current_descendants if identity not in baseline)
    if containment_environment_marker is not None:
        global_baseline = process_table_baseline or set()
        for pid, row in table.items():
            identity = _process_identity(row)
            if identity in global_baseline or identity in known:
                continue
            if _process_has_containment_environment_marker(
                pid,
                containment_environment_marker,
            ):
                known.add(identity)
    global_baseline = process_table_baseline or set()
    tracked_process_groups: set[int] = set()
    tracked_sessions: set[int] = set()
    for pid, row in table.items():
        if _process_identity(row) not in known:
            continue
        tracked_process_groups.add(int(row["process_group"]))
        tracked_sessions.add(int(row["session"]))
        known.update(_descendant_identities(table, pid))
    # The primary process starts a private session, and every independently
    # tracked setsid descendant owns another private session.  Expand through
    # those already-attributed groups/sessions so a child that exits between
    # ancestry scans remains attributable after it is adopted as a zombie by
    # this subreaper.  Zombie environ files are empty, so the nonce marker
    # alone cannot cover that race.
    for row in table.values():
        identity = _process_identity(row)
        if identity in global_baseline or identity in known:
            continue
        if (
            int(row["process_group"]) in tracked_process_groups
            or int(row["session"]) in tracked_sessions
        ):
            known.add(identity)
    return {
        identity
        for identity in known
        if identity not in baseline and _identity_is_live(identity)
    }


def _terminate_and_reap_contained_step(
    process: subprocess.Popen[Any],
    *,
    supervisor_pid: int,
    baseline: set[tuple[int, int]],
    primary_identity: tuple[int, int],
    termination_grace_seconds: float,
    initial_known: set[tuple[int, int]] | None = None,
    containment_environment_marker: bytes | None = None,
    process_table_baseline: set[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    known: set[tuple[int, int]] = set(initial_known or ())
    known.add(primary_identity)
    stop_signalled: set[tuple[int, int]] = set()
    term_signalled: set[tuple[int, int]] = set()
    kill_signalled: set[tuple[int, int]] = set()
    reaped_count = 0
    for _freeze_scan in range(3):
        live = _contained_step_identities(
            supervisor_pid,
            baseline,
            primary_identity,
            known,
            containment_environment_marker=containment_environment_marker,
            process_table_baseline=process_table_baseline,
        )
        _signal_tracked_process_group(process.pid, live, signal.SIGSTOP)
        for identity in sorted(live, reverse=True):
            if _signal_identity(identity, signal.SIGSTOP):
                stop_signalled.add(identity)
        time.sleep(0.01)
    live = _contained_step_identities(
        supervisor_pid,
        baseline,
        primary_identity,
        known,
        containment_environment_marker=containment_environment_marker,
        process_table_baseline=process_table_baseline,
    )
    _signal_tracked_process_group(process.pid, live, signal.SIGTERM)
    for identity in sorted(live, reverse=True):
        if _signal_identity(identity, signal.SIGTERM):
            term_signalled.add(identity)
    # Every discovered process is stopped at this point. Queue SIGKILL before
    # allowing execution again so a TERM-ignoring descendant cannot turn an
    # interrupted sleep into an immediate side effect during a grace window.
    _signal_tracked_process_group(process.pid, live, signal.SIGKILL)
    for identity in sorted(live, reverse=True):
        if _signal_identity(identity, signal.SIGKILL):
            kill_signalled.add(identity)
    _signal_tracked_process_group(process.pid, live, signal.SIGCONT)
    for identity in sorted(live, reverse=True):
        _signal_identity(identity, signal.SIGCONT)
    grace_deadline = time.monotonic() + termination_grace_seconds
    while time.monotonic() < grace_deadline:
        process.poll()
        live = _contained_step_identities(
            supervisor_pid,
            baseline,
            primary_identity,
            known,
            containment_environment_marker=containment_environment_marker,
            process_table_baseline=process_table_baseline,
        )
        for identity in sorted(live, reverse=True):
            if identity not in term_signalled and _signal_identity(identity, signal.SIGTERM):
                term_signalled.add(identity)
        reaped_count += _reap_tracked_children(known, exclude_pid=process.pid)
        if not live:
            break
        time.sleep(0.02)
    settle_seconds = max(
        termination_grace_seconds,
        POST_IMPORT_DESCENDANT_SETTLE_SECONDS,
    )
    kill_deadline = time.monotonic() + settle_seconds
    while time.monotonic() < kill_deadline:
        process.poll()
        live = _contained_step_identities(
            supervisor_pid,
            baseline,
            primary_identity,
            known,
            containment_environment_marker=containment_environment_marker,
            process_table_baseline=process_table_baseline,
        )
        for identity in sorted(live, reverse=True):
            if _signal_identity(identity, signal.SIGKILL):
                kill_signalled.add(identity)
        reaped_count += _reap_tracked_children(known, exclude_pid=process.pid)
        if not live:
            break
        time.sleep(0.02)
    try:
        process.wait(timeout=settle_seconds)
    except subprocess.TimeoutExpired:
        _signal_identity(primary_identity, signal.SIGKILL)
        process.wait(timeout=settle_seconds)
    stable_zero_since: float | None = None
    final_deadline = time.monotonic() + settle_seconds
    final_live: set[tuple[int, int]] = set()
    while time.monotonic() < final_deadline:
        final_live = _contained_step_identities(
            supervisor_pid,
            baseline,
            primary_identity,
            known,
            containment_environment_marker=containment_environment_marker,
            process_table_baseline=process_table_baseline,
        )
        reaped_count += _reap_tracked_children(known, exclude_pid=None)
        final_live = {
            identity for identity in final_live if _identity_is_live(identity)
        }
        if not final_live:
            now = time.monotonic()
            if stable_zero_since is None:
                stable_zero_since = now
            if now - stable_zero_since >= POST_IMPORT_STABLE_ZERO_SECONDS:
                break
        else:
            stable_zero_since = None
            for identity in final_live:
                if _signal_identity(identity, signal.SIGKILL):
                    kill_signalled.add(identity)
        time.sleep(0.02)
    stable_zero_observed_seconds = (
        0.0
        if stable_zero_since is None
        else max(0.0, time.monotonic() - stable_zero_since)
    )
    if (
        final_live
        or stable_zero_since is None
        or stable_zero_observed_seconds < POST_IMPORT_STABLE_ZERO_SECONDS
    ):
        raise SystemExit(
            "post-import containment could not prove zero surviving descendants"
        )
    return {
        "subreaper_enabled": True,
        "stop_signalled_count": len(stop_signalled),
        "term_signalled_count": len(term_signalled),
        "kill_signalled_count": len(kill_signalled),
        "reaped_descendant_count": reaped_count,
        "remaining_descendant_count": 0,
        "stable_zero_observed_seconds": stable_zero_observed_seconds,
        "zero_descendants_proven": True,
    }


def _emergency_kill_and_reap_primary_session(
    process: subprocess.Popen[Any],
    *,
    settle_seconds: float,
) -> None:
    # This path is deliberately independent of /proc. It cannot certify escaped
    # sessions, but it prevents a process-table failure from skipping the owned
    # session/group and primary-process kill before the caller fails closed.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        if process.poll() is None:
            process.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        process.wait(timeout=settle_seconds)
    except (subprocess.TimeoutExpired, ChildProcessError, OSError):
        pass


def run_bound_python_subprocess(
    bound_argv: list[str],
    *,
    interpreter_sha256: str,
    script_sha256: str,
    cwd: Path,
    environment: dict[str, str],
    dependency_bundle_bytes: bytes | None = None,
    dependency_bundle_binding: dict[str, Any] | None = None,
    timeout_seconds: float = POST_IMPORT_LOCAL_TIMEOUT_SECONDS,
    termination_grace_seconds: float = POST_IMPORT_TERMINATION_GRACE_SECONDS,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    if len(bound_argv) < 2:
        raise SystemExit("code-owned Python argv is missing its interpreter or script")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise SystemExit("code-owned Python timeout must be a finite positive number")
    if not math.isfinite(termination_grace_seconds) or termination_grace_seconds <= 0:
        raise SystemExit("code-owned Python termination grace must be a finite positive number")
    interpreter_path = Path(bound_argv[0])
    script_path = Path(bound_argv[1])
    interpreter_descriptor, interpreter_size = _sealed_memfd_from_file(
        interpreter_path,
        interpreter_sha256,
        "code-owned Python interpreter",
    )
    try:
        script_descriptor, script_size = _sealed_memfd_from_file(
            script_path,
            script_sha256,
            "code-owned Python script",
        )
    except BaseException:
        os.close(interpreter_descriptor)
        raise
    if dependency_bundle_bytes is None or dependency_bundle_binding is None:
        dependency_bundle_bytes, dependency_bundle_binding = (
            production_code_owned_python_dependency_bundle()
        )
    try:
        dependency_descriptor, dependency_size = _sealed_memfd_from_bytes(
            dependency_bundle_bytes,
            str(dependency_bundle_binding.get("bundle_sha256") or ""),
            "code-owned Python dependency bundle",
        )
    except BaseException:
        os.close(script_descriptor)
        os.close(interpreter_descriptor)
        raise
    try:
        execution_argv = [
            f"/proc/self/fd/{interpreter_descriptor}",
            "-I",
            "-c",
            SEALED_PYTHON_LAUNCHER_SOURCE,
            str(script_path),
            str(script_descriptor),
            str(dependency_descriptor),
            *bound_argv[2:],
        ]
        with _POST_IMPORT_EXECUTION_LOCK:
            _require_linux_child_subreaper()
            supervisor_pid = os.getpid()
            baseline_process_table = _proc_process_table()
            baseline = _descendant_identities(
                baseline_process_table,
                supervisor_pid,
            )
            process_table_baseline = {
                _process_identity(row) for row in baseline_process_table.values()
            }
            if POST_IMPORT_CONTAINMENT_ENVIRONMENT_KEY in environment:
                raise SystemExit(
                    "code-owned execution environment uses the reserved containment key"
                )
            containment_nonce = secrets.token_hex(32)
            containment_environment_marker = (
                f"{POST_IMPORT_CONTAINMENT_ENVIRONMENT_KEY}={containment_nonce}"
            ).encode("ascii")
            execution_environment = dict(environment)
            execution_environment[
                POST_IMPORT_CONTAINMENT_ENVIRONMENT_KEY
            ] = containment_nonce
            primary_identity = (-1, -1)
            timed_out = False
            stdout_bytes = b""
            stderr_bytes = b""
            communication_error: Exception | None = None
            observed_identities: set[tuple[int, int]] = set()
            observation_stop = threading.Event()
            observation_thread: threading.Thread | None = None
            observation_started = False
            process = subprocess.Popen(
                execution_argv,
                executable=execution_argv[0],
                pass_fds=(
                    interpreter_descriptor,
                    script_descriptor,
                    dependency_descriptor,
                ),
                cwd=cwd,
                env=execution_environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                shell=False,
                start_new_session=True,
            )
            try:
                primary_identity = (process.pid, -1)
                primary_row = _proc_process_table().get(process.pid)
                primary_identity = (
                    _process_identity(primary_row)
                    if primary_row is not None
                    else primary_identity
                )

                def observe_early_descendants() -> None:
                    deadline = (
                        time.monotonic()
                        + POST_IMPORT_EARLY_DESCENDANT_OBSERVATION_SECONDS
                    )
                    while True:
                        try:
                            _contained_step_identities(
                                supervisor_pid,
                                baseline,
                                primary_identity,
                                observed_identities,
                                containment_environment_marker=(
                                    containment_environment_marker
                                ),
                                process_table_baseline=process_table_baseline,
                            )
                        except BaseException:
                            return
                        if (
                            time.monotonic() >= deadline
                            or observation_stop.wait(
                                POST_IMPORT_DESCENDANT_OBSERVATION_INTERVAL_SECONDS
                            )
                        ):
                            return

                observation_thread = threading.Thread(
                    target=observe_early_descendants,
                    name="windows-proof-descendant-observer",
                    daemon=True,
                )
                try:
                    observation_thread.start()
                    observation_started = True
                except Exception as exc:
                    communication_error = exc
                if communication_error is None:
                    try:
                        stdout_bytes, stderr_bytes = process.communicate(
                            timeout=timeout_seconds
                        )
                    except subprocess.TimeoutExpired:
                        timed_out = True
                    except Exception as exc:
                        communication_error = exc
            finally:
                observation_cleanup_failed = False
                try:
                    observation_stop.set()
                    thread_was_started = bool(
                        observation_thread is not None
                        and (
                            observation_started
                            or observation_thread.ident is not None
                        )
                    )
                    if thread_was_started and observation_thread is not None:
                        try:
                            observation_thread.join(
                                timeout=max(
                                    termination_grace_seconds,
                                    POST_IMPORT_DESCENDANT_SETTLE_SECONDS,
                                )
                            )
                            observation_cleanup_failed = observation_thread.is_alive()
                        except BaseException:
                            observation_cleanup_failed = True
                finally:
                    try:
                        containment = _terminate_and_reap_contained_step(
                            process,
                            supervisor_pid=supervisor_pid,
                            baseline=baseline,
                            primary_identity=(
                                primary_identity
                                if primary_identity[0] == process.pid
                                else (process.pid, -1)
                            ),
                            termination_grace_seconds=termination_grace_seconds,
                            initial_known=set(observed_identities),
                            containment_environment_marker=(
                                containment_environment_marker
                            ),
                            process_table_baseline=process_table_baseline,
                        )
                        containment["early_observed_identity_count"] = len(
                            observed_identities
                        )
                        containment["early_observation_window_seconds"] = (
                            POST_IMPORT_EARLY_DESCENDANT_OBSERVATION_SECONDS
                        )
                        containment["environment_marker_sha256"] = hashlib.sha256(
                            containment_environment_marker
                        ).hexdigest().lower()
                    except BaseException:
                        _emergency_kill_and_reap_primary_session(
                            process,
                            settle_seconds=max(
                                termination_grace_seconds,
                                POST_IMPORT_DESCENDANT_SETTLE_SECONDS,
                            ),
                        )
                        raise SystemExit(
                            "post-import containment inspection failed after emergency session cleanup; "
                            "zero descendants could not be proven"
                        ) from None
                if observation_cleanup_failed and communication_error is None:
                    communication_error = RuntimeError(
                        "descendant observer cleanup failed"
                    )
            if timed_out or communication_error is not None:
                try:
                    stdout_bytes, stderr_bytes = process.communicate(
                        timeout=max(
                            termination_grace_seconds,
                            POST_IMPORT_DESCENDANT_SETTLE_SECONDS,
                        )
                    )
                except Exception as exc:
                    if communication_error is None:
                        communication_error = exc
            if communication_error is not None:
                raise SystemExit(
                    "post-import process communication failed after descendant containment"
                ) from None
            stdout = bytes(stdout_bytes or b"").decode("utf-8", errors="replace")
            stderr = bytes(stderr_bytes or b"").decode("utf-8", errors="replace")
            returncode = 124 if timed_out else int(process.returncode or 0)
            completed = subprocess.CompletedProcess(
                execution_argv,
                returncode,
                stdout,
                stderr,
            )
    finally:
        os.close(dependency_descriptor)
        os.close(script_descriptor)
        os.close(interpreter_descriptor)
    return completed, {
        "transport": "sealed_memfd",
        "bound_argv": list(bound_argv),
        "execution_argv": execution_argv,
        "logical_script_path": str(script_path),
        "launcher_sha256": SEALED_PYTHON_LAUNCHER_SHA256,
        "interpreter_sha256": interpreter_sha256,
        "interpreter_size_bytes": interpreter_size,
        "script_sha256": script_sha256,
        "script_size_bytes": script_size,
        "dependency_bundle_sha256": str(
            dependency_bundle_binding.get("bundle_sha256") or ""
        ),
        "dependency_bundle_size_bytes": dependency_size,
        "runtime_environment_extension": {
            "key": POST_IMPORT_CONTAINMENT_ENVIRONMENT_KEY,
            "value_sha256": hashlib.sha256(
                containment_nonce.encode("ascii")
            ).hexdigest().lower(),
            "purpose": "descendant_identity_containment",
            "base_environment_sha256": sha256_json(environment),
        },
        "timeout_seconds": timeout_seconds,
        "termination_grace_seconds": termination_grace_seconds,
        "process_group_mode": "linux_child_subreaper_descendant_sweep",
        "timed_out": timed_out,
        "containment": containment,
    }


def _blocked_post_import_result(
    *,
    plan: dict[str, Any],
    step: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    argv = [str(item) for item in step.get("argv") or []]
    return {
        "status": "blocked_plan_binding_drift",
        "plan_contract_name": POST_IMPORT_PLAN_CONTRACT,
        "plan_sha256": str(plan.get("plan_sha256") or ""),
        "step_id": str(step.get("step_id") or ""),
        "effect_class": str(step.get("effect_class") or ""),
        "ordinal": int(step.get("ordinal") or 0),
        "argv": argv,
        "argv_sha256": sha256_json(argv),
        "command": shlex.join(argv),
        "cwd": str(step.get("cwd") or ""),
        "environment_sha256": str(step.get("environment_sha256") or ""),
        "execution_binding_sha256": str(step.get("execution_binding_sha256") or ""),
        "program_bindings": dict(plan.get("program_bindings") or {}),
        "process_termination_policy": dict(plan.get("process_termination_policy") or {}),
        "timeout_seconds": step.get("timeout_seconds"),
        "termination_grace_seconds": step.get("termination_grace_seconds"),
        "process_group_mode": str(step.get("process_group_mode") or ""),
        "timed_out": False,
        "shell": False,
        "returncode": 126,
        "stdout_tail": [],
        "stderr_tail": [],
        "stdout_receipt": redacted_stream_receipt(""),
        "stderr_receipt": redacted_stream_receipt(reason),
        "binding_failure_receipt": redacted_stream_receipt(reason),
    }


def run_code_owned_post_import_step(
    plan: dict[str, Any],
    step: dict[str, Any],
) -> dict[str, Any]:
    plan_sha256 = str(plan.get("plan_sha256") or "")
    if sha256_json(_plan_core(plan)) != plan_sha256:
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import plan SHA-256 binding drifted before execution",
        )
    if sha256_json(_step_binding(step)) != str(step.get("execution_binding_sha256") or ""):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import step execution binding drifted before execution",
        )
    authority = plan.get("authority_source") if isinstance(plan.get("authority_source"), dict) else {}
    authority_path = Path(str(authority.get("path") or ""))
    if not authority_path.is_file() or sha256_file(authority_path) != str(authority.get("sha256") or ""):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import code authority bytes drifted before execution",
        )
    interpreter = plan.get("interpreter") if isinstance(plan.get("interpreter"), dict) else {}
    interpreter_path = Path(str(interpreter.get("path") or ""))
    if not interpreter_path.is_file() or sha256_file(interpreter_path) != str(interpreter.get("sha256") or ""):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import interpreter bytes drifted before execution",
        )
    argv = [str(item) for item in step.get("argv") or []]
    if len(argv) < 2 or argv[0] != str(interpreter_path):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import step argv is not bound to the code-owned interpreter",
        )
    script_path = Path(argv[1])
    if not script_path.is_file() or sha256_file(script_path) != str(step.get("script_sha256") or ""):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import step script bytes drifted before execution",
        )
    environment = plan.get("environment") if isinstance(plan.get("environment"), dict) else {}
    normalized_environment = {
        str(key): str(value)
        for key, value in environment.items()
    }
    if sha256_json(normalized_environment) != str(plan.get("environment_sha256") or ""):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import deterministic environment binding drifted before execution",
        )
    dependency_bundle_bytes, dependency_bundle_binding = (
        production_code_owned_python_dependency_bundle()
    )
    if str(dependency_bundle_binding.get("bundle_sha256") or "") != str(
        step.get("dependency_bundle_sha256") or ""
    ):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import Python dependency bundle binding drifted before execution",
        )
    if str(step.get("launcher_sha256") or "") != SEALED_PYTHON_LAUNCHER_SHA256:
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import sealed Python launcher binding drifted before execution",
        )
    try:
        timeout_seconds = float(step.get("timeout_seconds"))
        termination_grace_seconds = float(step.get("termination_grace_seconds"))
    except (TypeError, ValueError):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import timeout bounds are invalid",
        )
    if (
        str(step.get("process_group_mode") or "")
        != "linux_child_subreaper_descendant_sweep"
        or step.get("zero_descendants_required") is not True
    ):
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import process-group mode binding drifted before execution",
        )

    try:
        completed, sealed_execution = run_bound_python_subprocess(
            argv,
            interpreter_sha256=str(interpreter.get("sha256") or ""),
            script_sha256=str(step.get("script_sha256") or ""),
            cwd=Path(str(plan.get("cwd") or ROOT)),
            environment=normalized_environment,
            dependency_bundle_bytes=dependency_bundle_bytes,
            dependency_bundle_binding=dependency_bundle_binding,
            timeout_seconds=timeout_seconds,
            termination_grace_seconds=termination_grace_seconds,
        )
    except (OSError, SystemExit) as exc:
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason=f"sealed post-import execution setup failed: {exc}",
        )
    timed_out = bool(sealed_execution.get("timed_out"))
    containment = (
        sealed_execution.get("containment")
        if isinstance(sealed_execution.get("containment"), dict)
        else {}
    )
    if containment.get("zero_descendants_proven") is not True:
        return _blocked_post_import_result(
            plan=plan,
            step=step,
            reason="post-import containment did not prove zero surviving descendants",
        )
    return {
        "status": "pass" if completed.returncode == 0 else ("timeout" if timed_out else "fail"),
        "plan_contract_name": POST_IMPORT_PLAN_CONTRACT,
        "plan_sha256": plan_sha256,
        "step_id": str(step.get("step_id") or ""),
        "effect_class": str(step.get("effect_class") or ""),
        "ordinal": int(step.get("ordinal") or 0),
        "argv": argv,
        "argv_sha256": sha256_json(argv),
        "command": shlex.join(argv),
        "cwd": str(plan.get("cwd") or ROOT),
        "environment_sha256": str(plan.get("environment_sha256") or ""),
        "execution_binding_sha256": str(step.get("execution_binding_sha256") or ""),
        "sealed_execution": sealed_execution,
        "program_bindings": dict(plan.get("program_bindings") or {}),
        "timeout_seconds": timeout_seconds,
        "termination_grace_seconds": termination_grace_seconds,
        "process_group_mode": "linux_child_subreaper_descendant_sweep",
        "timed_out": timed_out,
        "containment": containment,
        "script_sha256": str(step.get("script_sha256") or ""),
        "shell": False,
        "returncode": int(completed.returncode),
        "stdout_tail": [],
        "stderr_tail": [],
        "stdout_receipt": redacted_stream_receipt(completed.stdout),
        "stderr_receipt": redacted_stream_receipt(completed.stderr),
    }


def execute_code_owned_post_import_plan(
    plan: dict[str, Any],
    *,
    external_mutation_pause_check: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    authorization = (
        plan.get("external_mutation_authorization")
        if isinstance(plan.get("external_mutation_authorization"), dict)
        else {}
    )
    external_mutations_authorized = bool(authorization.get("requested"))
    results: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if (
            str(step.get("execution_phase") or "") == "external_mutation"
            and not external_mutations_authorized
        ):
            break
        if (
            str(step.get("execution_phase") or "") == "external_mutation"
            and external_mutation_pause_check is not None
            and external_mutation_pause_check()
        ):
            blocked = _blocked_post_import_result(
                plan=plan,
                step=step,
                reason="auto-import pause interlock engaged before external mutation",
            )
            blocked["status"] = "blocked_pause_interlock"
            blocked["returncode"] = 125
            results.append(blocked)
            break
        result = run_code_owned_post_import_step(plan, step)
        results.append(result)
        if int(result.get("returncode") or 0) != 0:
            break
    return results


def post_import_plan_receipt(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    paused: bool = False,
) -> dict[str, Any]:
    failed_count = sum(int(row.get("returncode") or 0) != 0 for row in results)
    steps = [
        step
        for step in plan.get("steps") or []
        if isinstance(step, dict)
    ]
    step_count = len(steps)
    missing_step_count = max(step_count - len(results), 0)
    executed_ordinals = {
        int(row.get("ordinal") or 0)
        for row in results
    }
    missing_local_steps = [
        step
        for step in steps
        if str(step.get("execution_phase") or "") != "external_mutation"
        and int(step.get("ordinal") or 0) not in executed_ordinals
    ]
    pending_external_steps = [
        step
        for step in steps
        if str(step.get("execution_phase") or "") == "external_mutation"
        and int(step.get("ordinal") or 0) not in executed_ordinals
    ]
    authorization = (
        plan.get("external_mutation_authorization")
        if isinstance(plan.get("external_mutation_authorization"), dict)
        else {}
    )
    external_ordinals = {
        int(step.get("ordinal") or 0)
        for step in steps
        if str(step.get("execution_phase") or "") == "external_mutation"
    }
    unauthorized_external_execution_count = (
        len(executed_ordinals & external_ordinals)
        if not bool(authorization.get("requested"))
        else 0
    )
    if paused:
        status = "blocked_paused"
    elif failed_count or missing_local_steps or unauthorized_external_execution_count:
        status = "fail"
    elif pending_external_steps and not bool(authorization.get("requested")):
        status = "pending_authorized_external_mutation"
    elif pending_external_steps:
        status = "fail"
    else:
        status = "pass"
    return {
        "contract_name": POST_IMPORT_PLAN_CONTRACT,
        "authority": POST_IMPORT_PLAN_AUTHORITY,
        "status": status,
        "plan_sha256": str(plan.get("plan_sha256") or ""),
        "authority_source": dict(plan.get("authority_source") or {}),
        "cwd": str(plan.get("cwd") or ""),
        "environment": dict(plan.get("environment") or {}),
        "environment_sha256": str(plan.get("environment_sha256") or ""),
        "interpreter": dict(plan.get("interpreter") or {}),
        "program_bindings": dict(plan.get("program_bindings") or {}),
        "process_termination_policy": dict(plan.get("process_termination_policy") or {}),
        "external_mutation_authorization": dict(authorization),
        "step_count": step_count,
        "executed_step_count": len(results),
        "failed_step_count": failed_count,
        "missing_step_count": missing_step_count,
        "missing_local_step_count": len(missing_local_steps),
        "pending_external_step_count": len(pending_external_steps),
        "unauthorized_external_execution_count": unauthorized_external_execution_count,
        "pending_external_step_ids": [
            str(step.get("step_id") or "")
            for step in pending_external_steps
        ],
        "shell": False,
        "steps": [
            {
                "ordinal": int(step.get("ordinal") or 0),
                "step_id": str(step.get("step_id") or ""),
                "effect_class": str(step.get("effect_class") or ""),
                "execution_phase": str(step.get("execution_phase") or ""),
                "timeout_seconds": step.get("timeout_seconds"),
                "termination_grace_seconds": step.get("termination_grace_seconds"),
                "process_group_mode": str(step.get("process_group_mode") or ""),
                "zero_descendants_required": bool(step.get("zero_descendants_required")),
                "argv": list(step.get("argv") or []),
                "script_sha256": str(step.get("script_sha256") or ""),
                "execution_binding_sha256": str(step.get("execution_binding_sha256") or ""),
            }
            for step in plan.get("steps") or []
            if isinstance(step, dict)
        ],
    }


def promoted_digest_from_intake(payload: dict[str, Any]) -> str:
    artifact = payload.get("promoted_installer") if isinstance(payload.get("promoted_installer"), dict) else {}
    return normalized(
        payload.get("promoted_installer_sha256")
        or artifact.get("sha256")
        or artifact.get("actual_sha256")
        or ""
    ).removeprefix("sha256:")


def startup_receipt_bundle_required_from_intake(payload: dict[str, Any]) -> bool:
    artifact_intake = payload.get("artifact_intake") if isinstance(payload.get("artifact_intake"), dict) else {}
    operator_request = payload.get("operator_request") if isinstance(payload.get("operator_request"), dict) else {}
    for value in (
        artifact_intake.get("startup_receipt_bundle_required"),
        operator_request.get("startup_receipt_bundle_required"),
        payload.get("startup_receipt_bundle_required"),
    ):
        if isinstance(value, bool):
            return value
    return True


def validate_existing_startup_receipt(startup_receipt: Path, promoted_digest: str) -> None:
    if not startup_receipt.is_file():
        raise SystemExit(
            "proof artifact omitted startup receipt, but the published startup receipt is missing: "
            f"{startup_receipt}"
        )
    payload = load_json(startup_receipt)
    status = normalized(payload.get("status"))
    platform = normalized(payload.get("platform"))
    host_class = payload.get("hostClass")
    disposition = normalized(payload.get("verificationDisposition"))
    skip_class = normalized(payload.get("skipClass"))
    digest = _required_sha256(
        payload.get("artifactDigest") or payload.get("artifactSha256"),
        "published startup receipt",
    )
    if disposition == "incompatible_host" or skip_class == "incompatible_host":
        raise SystemExit(
            "proof artifact omitted startup receipt, but the published startup receipt is an incompatible-host skip: "
            f"{startup_receipt}"
        )
    if status != "pass":
        raise SystemExit(
            "proof artifact omitted startup receipt, but the published startup receipt is not pass: "
            f"{startup_receipt}"
        )
    if platform != "windows" or not _native_windows_host_class(host_class):
        raise SystemExit(
            "proof artifact omitted startup receipt, but the published startup receipt is not native Windows proof: "
            f"{startup_receipt}"
        )
    if promoted_digest and digest != promoted_digest:
        raise SystemExit(
            "proof artifact omitted startup receipt, but the published startup receipt digest does not match the promoted installer: "
            f"{startup_receipt}"
        )


def validate_bundled_startup_receipt(
    startup_receipt: Path,
    promoted_digest: str,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    payload = payload or load_json(startup_receipt)
    status = normalized(payload.get("status"))
    platform = normalized(payload.get("platform"))
    host_class = payload.get("hostClass")
    disposition = normalized(payload.get("verificationDisposition"))
    skip_class = normalized(payload.get("skipClass"))
    digest = _required_sha256(
        payload.get("artifactDigest") or payload.get("artifactSha256"),
        "bundled startup receipt",
    )
    if disposition == "incompatible_host" or skip_class == "incompatible_host":
        raise SystemExit(
            "proof artifact bundled an incompatible-host startup receipt instead of native Windows proof: "
            f"{startup_receipt}"
        )
    if status != "pass":
        raise SystemExit(
            "proof artifact bundled a startup receipt that is not pass: "
            f"{startup_receipt}"
        )
    if platform != "windows" or not _native_windows_host_class(host_class):
        raise SystemExit(
            "proof artifact bundled startup metadata that is not native Windows proof: "
            f"{startup_receipt}"
        )
    if promoted_digest and digest != promoted_digest:
        raise SystemExit(
            "proof artifact bundled a startup receipt whose digest does not match the promoted installer: "
            f"{startup_receipt}"
        )


def capture_bounds_look_like_desktop_fallback(row: dict[str, Any]) -> bool:
    mode = normalized(row.get("captureMode"))
    if mode not in {"window-bounds", "reused-same-surface"}:
        return False
    if normalized_surface(row.get("surface")) not in REQUIRED_SURFACES:
        return False

    bounds = row.get("captureBounds")
    if not isinstance(bounds, dict):
        return False
    try:
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        width = int(bounds.get("width", 0))
        height = int(bounds.get("height", 0))
    except (TypeError, ValueError):
        return False

    return left == 0 and top == 0 and width >= 1000 and height >= 700


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _stable_identity(file_stat: os.stat_result) -> tuple[int, ...]:
    return (
        int(file_stat.st_dev),
        int(file_stat.st_ino),
        int(file_stat.st_mode),
        int(file_stat.st_nlink),
        int(file_stat.st_size),
        int(file_stat.st_mtime_ns),
        int(file_stat.st_ctime_ns),
    )


def _confined_regular_file_lstat(path: Path, bundle_root: Path, label: str) -> os.stat_result:
    lexical_root = _absolute_lexical_path(bundle_root)
    lexical_path = _absolute_lexical_path(path)
    if lexical_root.resolve() != lexical_root:
        raise SystemExit(f"proof artifact root contains a symlink: {lexical_root}")
    root_stat = os.lstat(lexical_root)
    if stat_module.S_ISLNK(root_stat.st_mode) or not stat_module.S_ISDIR(root_stat.st_mode):
        raise SystemExit(f"proof artifact root is not a real directory: {lexical_root}")
    try:
        relative = lexical_path.relative_to(lexical_root)
    except ValueError as exc:
        raise SystemExit(f"{label} escapes the proof artifact root: {path}") from exc
    if not relative.parts:
        raise SystemExit(f"{label} does not name a file inside the proof artifact root: {path}")

    current = lexical_root
    for index, component in enumerate(relative.parts):
        current = current / component
        try:
            current_stat = os.lstat(current)
        except FileNotFoundError as exc:
            raise SystemExit(f"{label} is missing: {current}") from exc
        if stat_module.S_ISLNK(current_stat.st_mode):
            raise SystemExit(f"{label} uses a symlink inside the proof artifact: {current}")
        if index < len(relative.parts) - 1 and not stat_module.S_ISDIR(current_stat.st_mode):
            raise SystemExit(f"{label} has a non-directory ancestor: {current}")

    if not stat_module.S_ISREG(current_stat.st_mode):
        raise SystemExit(f"{label} is not a regular file: {lexical_path}")
    if int(current_stat.st_nlink) != 1:
        raise SystemExit(f"{label} is hard-linked and not an immutable bundle member: {lexical_path}")
    return current_stat


def stable_bundle_file_snapshot(path: Path, bundle_root: Path, label: str) -> dict[str, Any]:
    lexical_path = _absolute_lexical_path(path)
    before_lstat = _confined_regular_file_lstat(lexical_path, bundle_root, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lexical_path, flags)
    except OSError as exc:
        raise SystemExit(f"{label} could not be opened without following links: {lexical_path} ({exc})") from exc
    try:
        opened_before = os.fstat(descriptor)
        if _stable_identity(opened_before) != _stable_identity(before_lstat):
            raise SystemExit(f"{label} identity drifted before stable read: {lexical_path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after_lstat = _confined_regular_file_lstat(lexical_path, bundle_root, label)
    expected_identity = _stable_identity(before_lstat)
    if (
        _stable_identity(opened_after) != expected_identity
        or _stable_identity(after_lstat) != expected_identity
    ):
        raise SystemExit(f"{label} changed during stable read: {lexical_path}")
    data = b"".join(chunks)
    if len(data) != int(before_lstat.st_size):
        raise SystemExit(f"{label} size drifted during stable read: {lexical_path}")
    return {
        "path": lexical_path,
        "data": data,
        "sha256": hashlib.sha256(data).hexdigest().lower(),
        "identity": {
            "device": int(before_lstat.st_dev),
            "inode": int(before_lstat.st_ino),
            "mode": int(before_lstat.st_mode),
            "link_count": int(before_lstat.st_nlink),
            "size_bytes": int(before_lstat.st_size),
            "mtime_ns": int(before_lstat.st_mtime_ns),
            "ctime_ns": int(before_lstat.st_ctime_ns),
        },
    }


def load_json_snapshot(snapshot: dict[str, Any], label: str) -> dict[str, Any]:
    try:
        loaded = json.loads(bytes(snapshot["data"]).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid json in {label}: {snapshot.get('path')} ({exc})") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"json root is not an object in {label}: {snapshot.get('path')}")
    return loaded


def copy_stable_snapshot(snapshot: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temp_path = Path(temp_name)
    try:
        data = bytes(snapshot["data"])
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(temp_path) != str(snapshot.get("sha256") or ""):
            raise SystemExit(f"stable snapshot copy hash mismatch: {destination}")
        os.replace(temp_path, destination)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_dirfd_component(component: str) -> str:
    if (
        not component
        or component in {".", ".."}
        or "/" in component
        or "\\" in component
        or "\x00" in component
    ):
        raise SystemExit(f"unsafe publication path component: {component!r}")
    return component


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_directory_at(
    parent_fd: int,
    component: str,
    *,
    create: bool = False,
    mode: int = 0o755,
) -> int:
    component = _validate_dirfd_component(component)
    if create:
        try:
            os.mkdir(component, mode=mode, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
    try:
        return os.open(component, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise SystemExit(
            f"publication directory is missing, linked, or not a directory: {component} ({exc})"
        ) from exc


def _open_directory_path(
    base_fd: int,
    components: tuple[str, ...] | list[str],
    *,
    create: bool = False,
    mode: int = 0o755,
) -> int:
    current_fd = os.dup(base_fd)
    try:
        for component in components:
            next_fd = _open_directory_at(
                current_fd,
                component,
                create=create,
                mode=mode,
            )
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _open_absolute_directory_no_follow(path: Path) -> int:
    absolute = _absolute_lexical_path(path)
    if not absolute.is_absolute():
        raise SystemExit("publication root must be absolute")
    current_fd = os.open(os.sep, _directory_open_flags())
    try:
        for component in absolute.parts[1:]:
            next_fd = _open_directory_at(current_fd, component)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _optional_lstat_at(parent_fd: int, component: str) -> os.stat_result | None:
    component = _validate_dirfd_component(component)
    try:
        return os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _read_file_at(parent_fd: int, component: str, *, max_bytes: int) -> bytes:
    component = _validate_dirfd_component(component)
    descriptor = os.open(
        component,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    try:
        file_stat = os.fstat(descriptor)
        if (
            not stat_module.S_ISREG(file_stat.st_mode)
            or int(file_stat.st_nlink) != 1
            or int(file_stat.st_size) > max_bytes
        ):
            raise SystemExit(f"publication file is not a bounded regular file: {component}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise SystemExit(f"publication file exceeds its read bound: {component}")
        final_stat = os.fstat(descriptor)
        if _stable_identity(final_stat) != _stable_identity(file_stat):
            raise SystemExit(f"publication file changed while being read: {component}")
        return data
    finally:
        os.close(descriptor)


def _write_file_at(
    parent_fd: int,
    component: str,
    data: bytes,
    *,
    mode: int = 0o600,
) -> None:
    component = _validate_dirfd_component(component)
    descriptor = os.open(
        component,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        mode,
        dir_fd=parent_fd,
    )
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(parent_fd)


def _atomic_write_json_at(parent_fd: int, component: str, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temp_component = f".{component}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    _write_file_at(parent_fd, temp_component, encoded)
    try:
        os.replace(
            temp_component,
            component,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temp_component, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def _load_optional_json_at(parent_fd: int, component: str) -> dict[str, Any] | None:
    if _optional_lstat_at(parent_fd, component) is None:
        return None
    data = _read_file_at(parent_fd, component, max_bytes=1024 * 1024)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"publication recovery journal is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("publication recovery journal root is not an object")
    return payload


def _remove_tree_at(parent_fd: int, component: str) -> None:
    component = _validate_dirfd_component(component)
    file_stat = _optional_lstat_at(parent_fd, component)
    if file_stat is None:
        return
    if not stat_module.S_ISDIR(file_stat.st_mode) or stat_module.S_ISLNK(file_stat.st_mode):
        os.unlink(component, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return
    child_fd = _open_directory_at(parent_fd, component)
    try:
        for child in os.listdir(child_fd):
            _remove_tree_at(child_fd, child)
    finally:
        os.close(child_fd)
    os.rmdir(component, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _anchor_state(
    root_fd: int,
    parent_components: tuple[str, ...],
    name: str,
    expected_target: str,
) -> str:
    current_fd = os.dup(root_fd)
    try:
        for component in parent_components:
            file_stat = _optional_lstat_at(current_fd, component)
            if file_stat is None:
                return "parent_absent"
            if not stat_module.S_ISDIR(file_stat.st_mode) or stat_module.S_ISLNK(file_stat.st_mode):
                raise SystemExit(
                    f"publication anchor ancestor is linked or not a directory: {component}"
                )
            next_fd = _open_directory_at(current_fd, component)
            os.close(current_fd)
            current_fd = next_fd
        parent_fd = current_fd
        current_fd = -1
    finally:
        if current_fd >= 0:
            os.close(current_fd)
    try:
        file_stat = _optional_lstat_at(parent_fd, name)
        if file_stat is None:
            return "absent"
        if not stat_module.S_ISLNK(file_stat.st_mode):
            return "legacy_direct_path"
        actual_target = os.readlink(name, dir_fd=parent_fd)
        return "expected" if actual_target == expected_target else "unexpected_symlink"
    finally:
        os.close(parent_fd)


def _public_anchor_spec(anchor_id: str) -> tuple[tuple[str, ...], str, str]:
    if anchor_id == "visual":
        return ("visual-audit",), "windows-installer", VISUAL_PUBLIC_ANCHOR_TARGET
    if anchor_id == "startup":
        return (
            ("startup-smoke",),
            STARTUP_RECEIPT_NAME,
            f"../{PROOF_CONTROL_DIRECTORY}/{PROOF_CURRENT_LINK}/startup-smoke/{STARTUP_RECEIPT_NAME}",
        )
    raise SystemExit("unknown publication anchor id")


def _public_anchor_state(root_fd: int, anchor_id: str) -> str:
    components, name, target = _public_anchor_spec(anchor_id)
    return _anchor_state(root_fd, components, name, target)


def _assert_fixed_public_anchors(root_fd: int) -> None:
    for anchor_id in ("visual", "startup"):
        if _public_anchor_state(root_fd, anchor_id) != "expected":
            raise SystemExit(
                f"committed proof generation is missing fixed public anchor: {anchor_id}"
            )


def _assert_no_legacy_publication_layout(root_fd: int) -> None:
    startup_target = (
        f"../{PROOF_CONTROL_DIRECTORY}/{PROOF_CURRENT_LINK}/startup-smoke/{STARTUP_RECEIPT_NAME}"
    )
    states = {
        "visual-audit/windows-installer": _anchor_state(
            root_fd,
            ("visual-audit",),
            "windows-installer",
            VISUAL_PUBLIC_ANCHOR_TARGET,
        ),
        f"startup-smoke/{STARTUP_RECEIPT_NAME}": _anchor_state(
            root_fd,
            ("startup-smoke",),
            STARTUP_RECEIPT_NAME,
            startup_target,
        ),
    }
    blocked = {
        path: state
        for path, state in states.items()
        if state in {"legacy_direct_path", "unexpected_symlink"}
    }
    if blocked:
        raise SystemExit(
            "legacy Windows proof publication layout requires a separately authorized migration; "
            "the importer will not mutate it: "
            + json.dumps(blocked, sort_keys=True)
        )


def _proof_generation_manifest(
    entries: list[tuple[dict[str, Any], Path]],
    downloads_root: Path,
) -> tuple[str, dict[str, Any], bytes, list[dict[str, Any]]]:
    startup_relative = Path("startup-smoke") / STARTUP_RECEIPT_NAME
    visual_root = Path("visual-audit") / "windows-installer"
    rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    visual_basenames: list[str] = []
    for snapshot, destination in entries:
        absolute_destination = _absolute_lexical_path(destination)
        try:
            relative = absolute_destination.relative_to(downloads_root)
        except ValueError as exc:
            raise SystemExit(
                f"proof-generation destination escapes downloads root: {absolute_destination}"
            ) from exc
        relative_text = relative.as_posix()
        if relative == startup_relative:
            role = "startup_receipt"
        elif relative.parent == visual_root:
            role = "visual_source" if relative.name == VISUAL_SOURCE_NAME else "screenshot"
            visual_basenames.append(relative.name)
        else:
            raise SystemExit(
                f"proof-generation destination is outside the fixed public anchors: {relative_text}"
            )
        path_key = unicodedata.normalize("NFC", relative_text).casefold()
        if path_key in seen_paths:
            raise SystemExit(f"proof generation contains a duplicate public path: {relative_text}")
        seen_paths.add(path_key)
        data = bytes(snapshot.get("data") or b"")
        digest = hashlib.sha256(data).hexdigest().lower()
        if digest != str(snapshot.get("sha256") or ""):
            raise SystemExit(f"proof-generation snapshot hash drifted: {relative_text}")
        row: dict[str, Any] = {
            "public_relative_path": relative_text,
            "public_basename": relative.name,
            "role": role,
            "sha256": digest,
            "size_bytes": len(data),
        }
        if role == "screenshot":
            row["image"] = dict(snapshot.get("image_metadata") or {})
        rows.append(row)
    rows.sort(key=lambda row: str(row["public_relative_path"]).casefold())
    if not any(row["role"] == "startup_receipt" for row in rows):
        raise SystemExit("proof generation is missing its bundled startup receipt")
    if not any(row["role"] == "visual_source" for row in rows):
        raise SystemExit("proof generation is missing its visual source receipt")
    screenshot_count = sum(row["role"] == "screenshot" for row in rows)
    if screenshot_count <= 0:
        raise SystemExit("proof generation contains no validated screenshots")
    manifest_core = {
        "contract_name": PROOF_GENERATION_CONTRACT,
        "files": rows,
        "allowed_visual_public_basenames": sorted(visual_basenames, key=str.casefold),
        "exact_public_relative_paths": sorted(
            (str(row["public_relative_path"]) for row in rows),
            key=str.casefold,
        ),
    }
    generation_id = "generation-" + sha256_json(manifest_core)[:32]
    manifest = {**manifest_core, "generation_id": generation_id}
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return generation_id, manifest, manifest_bytes, rows


def _write_generation_file(
    generation_fd: int,
    relative_path: str,
    data: bytes,
) -> None:
    relative = Path(relative_path)
    parent_fd = _open_directory_path(
        generation_fd,
        list(relative.parent.parts) if relative.parent != Path(".") else [],
        create=True,
    )
    try:
        _write_file_at(parent_fd, relative.name, data)
    finally:
        os.close(parent_fd)


def _generation_tree_layout(
    generation_fd: int,
    prefix: str = "",
) -> tuple[list[str], list[str]]:
    files: list[str] = []
    directories: list[str] = []
    for name in sorted(os.listdir(generation_fd), key=str.casefold):
        _validate_dirfd_component(name)
        file_stat = os.stat(name, dir_fd=generation_fd, follow_symlinks=False)
        relative = f"{prefix}/{name}" if prefix else name
        if stat_module.S_ISLNK(file_stat.st_mode):
            raise SystemExit(f"proof generation contains a symlink: {relative}")
        if stat_module.S_ISDIR(file_stat.st_mode):
            directories.append(relative)
            child_fd = _open_directory_at(generation_fd, name)
            try:
                child_files, child_directories = _generation_tree_layout(child_fd, relative)
                files.extend(child_files)
                directories.extend(child_directories)
            finally:
                os.close(child_fd)
            continue
        if not stat_module.S_ISREG(file_stat.st_mode):
            raise SystemExit(f"proof generation contains a non-regular entry: {relative}")
        files.append(relative)
    return files, directories


def _generation_tree_files(generation_fd: int, prefix: str = "") -> list[str]:
    files, _directories = _generation_tree_layout(generation_fd, prefix)
    return files


def _assert_generation_tree_sealed(generation_fd: int, prefix: str = "") -> None:
    root_stat = os.fstat(generation_fd)
    if stat_module.S_IMODE(root_stat.st_mode) != 0o555:
        raise SystemExit(
            f"proof generation directory mode is not immutable: {prefix or '.'}"
        )
    for name in sorted(os.listdir(generation_fd), key=str.casefold):
        file_stat = os.stat(name, dir_fd=generation_fd, follow_symlinks=False)
        relative = f"{prefix}/{name}" if prefix else name
        if stat_module.S_ISDIR(file_stat.st_mode) and not stat_module.S_ISLNK(file_stat.st_mode):
            if stat_module.S_IMODE(file_stat.st_mode) != 0o555:
                raise SystemExit(f"proof generation directory mode is not immutable: {relative}")
            child_fd = _open_directory_at(generation_fd, name)
            try:
                _assert_generation_tree_sealed(child_fd, relative)
            finally:
                os.close(child_fd)
        elif stat_module.S_ISREG(file_stat.st_mode):
            if stat_module.S_IMODE(file_stat.st_mode) != 0o444 or int(file_stat.st_nlink) != 1:
                raise SystemExit(f"proof generation file is not private and immutable: {relative}")
        else:
            raise SystemExit(f"proof generation contains an unsafe entry: {relative}")


def _validate_generation_directory(
    generations_fd: int,
    generation_id: str,
    *,
    directory_component: str | None = None,
    expected_manifest_bytes: bytes | None = None,
) -> dict[str, Any]:
    generation_fd = _open_directory_at(
        generations_fd,
        directory_component or generation_id,
    )
    try:
        manifest_bytes = _read_file_at(
            generation_fd,
            PROOF_GENERATION_MANIFEST,
            max_bytes=1024 * 1024,
        )
        if expected_manifest_bytes is not None and manifest_bytes != expected_manifest_bytes:
            raise SystemExit("existing proof generation manifest bytes do not match")
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"proof generation manifest is invalid: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("contract_name") != PROOF_GENERATION_CONTRACT:
            raise SystemExit("proof generation manifest contract is invalid")
        canonical_manifest_bytes = (
            json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if manifest_bytes != canonical_manifest_bytes:
            raise SystemExit("proof generation manifest JSON bytes are not canonical")
        if set(manifest) != {
            "contract_name",
            "generation_id",
            "files",
            "allowed_visual_public_basenames",
            "exact_public_relative_paths",
        }:
            raise SystemExit("proof generation manifest field set is not canonical")
        if str(manifest.get("generation_id") or "") != generation_id:
            raise SystemExit("proof generation manifest id does not match its directory")
        manifest_core = {
            key: value
            for key, value in manifest.items()
            if key != "generation_id"
        }
        if "generation-" + sha256_json(manifest_core)[:32] != generation_id:
            raise SystemExit("proof generation id is not content-addressed to its manifest")
        if not isinstance(manifest.get("files"), list):
            raise SystemExit("proof generation manifest files field is not a list")
        files = manifest["files"]
        expected_paths = {PROOF_GENERATION_MANIFEST}
        visual_basenames: list[str] = []
        seen_paths: set[str] = set()
        role_counts = {"startup_receipt": 0, "visual_source": 0, "screenshot": 0}
        role_payloads: dict[str, bytes] = {}
        screenshot_public_names: list[str] = []
        for row in files:
            if not isinstance(row, dict):
                raise SystemExit("proof generation manifest contains an invalid file row")
            if set(row) not in (
                {"public_relative_path", "public_basename", "role", "sha256", "size_bytes"},
                {"public_relative_path", "public_basename", "role", "sha256", "size_bytes", "image"},
            ):
                raise SystemExit("proof generation manifest file row has a non-canonical field set")
            relative_text = str(row.get("public_relative_path") or "")
            relative = Path(relative_text)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not relative.parts
                or relative.as_posix() != relative_text
                or unicodedata.normalize("NFC", relative_text) != relative_text
            ):
                raise SystemExit("proof generation manifest contains an unsafe public path")
            path_key = unicodedata.normalize("NFC", relative_text).casefold()
            if path_key in seen_paths:
                raise SystemExit("proof generation manifest contains a duplicate public path")
            seen_paths.add(path_key)
            if str(row.get("public_basename") or "") != relative.name:
                raise SystemExit("proof generation manifest basename disagrees with its public path")
            role = str(row.get("role") or "")
            if role == "startup_receipt":
                if relative != Path("startup-smoke") / STARTUP_RECEIPT_NAME:
                    raise SystemExit("proof generation startup path is not fixed")
            elif role in {"visual_source", "screenshot"}:
                if relative.parent != Path("visual-audit") / "windows-installer":
                    raise SystemExit("proof generation visual path is not fixed")
                visual_basenames.append(relative.name)
                if role == "visual_source" and relative.name != VISUAL_SOURCE_NAME:
                    raise SystemExit("proof generation visual source basename is not fixed")
                if role == "screenshot":
                    screenshot_public_names.append(relative.name)
            else:
                raise SystemExit("proof generation manifest contains an unknown role")
            base_row_fields = {
                "public_relative_path",
                "public_basename",
                "role",
                "sha256",
                "size_bytes",
            }
            expected_row_fields = (
                base_row_fields | {"image"} if role == "screenshot" else base_row_fields
            )
            if set(row) != expected_row_fields:
                raise SystemExit("proof generation manifest role has the wrong row schema")
            role_counts[role] += 1
            digest = str(row.get("sha256") or "")
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise SystemExit("proof generation manifest contains an invalid SHA-256 digest")
            declared_size = row.get("size_bytes")
            if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size <= 0:
                raise SystemExit("proof generation manifest contains an invalid file size")
            parent_fd = _open_directory_path(
                generation_fd,
                list(relative.parent.parts) if relative.parent != Path(".") else [],
            )
            try:
                data = _read_file_at(
                    parent_fd,
                    relative.name,
                    max_bytes=max(MAX_SCREENSHOT_BYTES, MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES),
                )
            finally:
                os.close(parent_fd)
            if hashlib.sha256(data).hexdigest().lower() != digest:
                raise SystemExit(f"proof generation file hash mismatch: {relative_text}")
            if len(data) != declared_size:
                raise SystemExit(f"proof generation file size mismatch: {relative_text}")
            if role in {"startup_receipt", "visual_source"}:
                role_payloads[role] = data
            if role == "screenshot":
                image_metadata = validate_screenshot_image(
                    {
                        "data": data,
                        "destination_name": relative.name,
                        "path": relative_text,
                    }
                )
                if row.get("image") != image_metadata:
                    raise SystemExit("proof generation screenshot metadata disagrees with its bytes")
            expected_paths.add(relative_text)
        if (
            role_counts["startup_receipt"] != 1
            or role_counts["visual_source"] != 1
            or not (1 <= role_counts["screenshot"] <= MAX_SCREENSHOT_COUNT)
        ):
            raise SystemExit("proof generation manifest is not a complete proof set")
        screenshot_hashes = [
            str(row["sha256"])
            for row in files
            if str(row.get("role") or "") == "screenshot"
        ]
        if len(set(screenshot_hashes)) != len(screenshot_hashes):
            raise SystemExit("proof generation screenshots do not have distinct hashes")
        canonical_file_paths = sorted(
            (str(row["public_relative_path"]) for row in files),
            key=str.casefold,
        )
        if [str(row["public_relative_path"]) for row in files] != canonical_file_paths:
            raise SystemExit("proof generation manifest files are not canonically ordered")
        try:
            startup_payload = json.loads(role_payloads["startup_receipt"].decode("utf-8"))
            visual_payload = json.loads(role_payloads["visual_source"].decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit("proof generation native proof metadata is invalid JSON") from exc
        if not isinstance(startup_payload, dict) or not isinstance(visual_payload, dict):
            raise SystemExit("proof generation native proof metadata is not an object")
        if normalized(startup_payload.get("status")) != "pass":
            raise SystemExit("proof generation startup receipt is not passing")
        if normalized(startup_payload.get("platform")) != "windows" or not _native_windows_host_class(
            startup_payload.get("hostClass")
        ):
            raise SystemExit("proof generation startup receipt is not native Windows evidence")
        startup_digest = _required_sha256(
            startup_payload.get("artifactDigest") or startup_payload.get("artifactSha256"),
            "proof generation startup receipt",
        )
        if normalized(visual_payload.get("status")) != "pass":
            raise SystemExit("proof generation visual source is not passing")
        if normalized(visual_payload.get("platform")) != "windows" or not _native_windows_host_class(
            visual_payload.get("hostClass")
        ):
            raise SystemExit("proof generation visual source is not native Windows evidence")
        visual_digest = _required_sha256(
            visual_payload.get("artifactSha256") or visual_payload.get("artifactDigest"),
            "proof generation visual source",
        )
        if startup_digest != visual_digest:
            raise SystemExit("proof generation native proof metadata targets different artifacts")
        screenshot_rows = visual_payload.get("screenshots")
        if not isinstance(screenshot_rows, list) or len(screenshot_rows) != role_counts["screenshot"]:
            raise SystemExit("proof generation visual source screenshot inventory is incomplete")
        source_screenshot_names: list[str] = []
        for screenshot_row in screenshot_rows:
            if not isinstance(screenshot_row, dict):
                raise SystemExit("proof generation visual source screenshot row is invalid")
            raw_path = str(screenshot_row.get("path") or "")
            posix_path = Path(raw_path)
            windows_path = PureWindowsPath(raw_path)
            if (
                not raw_path
                or posix_path.is_absolute()
                or windows_path.is_absolute()
                or ".." in posix_path.parts
                or ".." in windows_path.parts
            ):
                raise SystemExit("proof generation visual source contains an unsafe screenshot path")
            source_screenshot_names.append(windows_path.name)
        if sorted(source_screenshot_names, key=str.casefold) != sorted(
            screenshot_public_names,
            key=str.casefold,
        ):
            raise SystemExit("proof generation visual source does not name the exact public screenshots")
        allowed_basenames = manifest.get("allowed_visual_public_basenames")
        exact_relative_paths = manifest.get("exact_public_relative_paths")
        if (
            not isinstance(allowed_basenames, list)
            or any(not isinstance(item, str) for item in allowed_basenames)
            or len(set(allowed_basenames)) != len(allowed_basenames)
            or allowed_basenames != sorted(allowed_basenames, key=str.casefold)
        ):
            raise SystemExit("proof generation allowed-basename manifest is not canonical")
        if (
            not isinstance(exact_relative_paths, list)
            or any(not isinstance(item, str) for item in exact_relative_paths)
            or len(set(exact_relative_paths)) != len(exact_relative_paths)
            or exact_relative_paths != sorted(exact_relative_paths, key=str.casefold)
        ):
            raise SystemExit("proof generation exact-path manifest is not canonical")
        if sorted(visual_basenames, key=str.casefold) != allowed_basenames:
            raise SystemExit("proof generation allowed-basename manifest is inconsistent")
        if sorted(expected_paths - {PROOF_GENERATION_MANIFEST}, key=str.casefold) != exact_relative_paths:
            raise SystemExit("proof generation exact-path manifest is inconsistent")
        actual_files, actual_directories = _generation_tree_layout(generation_fd)
        actual_paths = set(actual_files)
        if actual_paths != expected_paths:
            raise SystemExit(
                "proof generation contains missing or extra files: "
                + json.dumps(
                    {
                        "missing": sorted(expected_paths - actual_paths),
                        "extra": sorted(actual_paths - expected_paths),
                    },
                    sort_keys=True,
                )
            )
        expected_directories = {
            "startup-smoke",
            "visual-audit",
            "visual-audit/windows-installer",
        }
        if set(actual_directories) != expected_directories:
            raise SystemExit(
                "proof generation contains missing or extra directories: "
                + json.dumps(
                    {
                        "missing": sorted(expected_directories - set(actual_directories)),
                        "extra": sorted(set(actual_directories) - expected_directories),
                    },
                    sort_keys=True,
                )
            )
        _assert_generation_tree_sealed(generation_fd)
        return manifest
    finally:
        os.close(generation_fd)


def _seal_generation_tree(generation_fd: int) -> None:
    for name in sorted(os.listdir(generation_fd), key=str.casefold):
        file_stat = os.stat(name, dir_fd=generation_fd, follow_symlinks=False)
        if stat_module.S_ISDIR(file_stat.st_mode) and not stat_module.S_ISLNK(file_stat.st_mode):
            child_fd = _open_directory_at(generation_fd, name)
            try:
                child_stat = os.fstat(child_fd)
                if (int(child_stat.st_dev), int(child_stat.st_ino)) != (
                    int(file_stat.st_dev),
                    int(file_stat.st_ino),
                ):
                    raise SystemExit(f"generation directory changed while sealing: {name}")
                _seal_generation_tree(child_fd)
                os.fchmod(child_fd, 0o555)
                os.fsync(child_fd)
            finally:
                os.close(child_fd)
        elif stat_module.S_ISREG(file_stat.st_mode):
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=generation_fd,
            )
            try:
                descriptor_stat = os.fstat(descriptor)
                if (
                    not stat_module.S_ISREG(descriptor_stat.st_mode)
                    or int(descriptor_stat.st_nlink) != 1
                    or (int(descriptor_stat.st_dev), int(descriptor_stat.st_ino))
                    != (int(file_stat.st_dev), int(file_stat.st_ino))
                ):
                    raise SystemExit(f"generation file is not private and stable: {name}")
                os.fchmod(descriptor, 0o444)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        else:
            raise SystemExit(f"cannot seal unsafe generation entry: {name}")
    os.fchmod(generation_fd, 0o555)
    os.fsync(generation_fd)


def _current_generation_target(control_fd: int) -> str | None:
    file_stat = _optional_lstat_at(control_fd, PROOF_CURRENT_LINK)
    if file_stat is None:
        return None
    if not stat_module.S_ISLNK(file_stat.st_mode):
        raise SystemExit("proof generation current pointer is not a symlink")
    target = os.readlink(PROOF_CURRENT_LINK, dir_fd=control_fd)
    return _validated_generation_target(target, "proof generation current pointer")


def _validated_generation_target(value: Any, label: str) -> str:
    target = str(value or "")
    prefix = f"{PROOF_GENERATIONS_DIRECTORY}/generation-"
    suffix = target.removeprefix(prefix)
    if (
        not target.startswith(prefix)
        or len(suffix) != 32
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise SystemExit(f"{label} has an unsafe target")
    return target


def _install_current_pointer(control_fd: int, target: str) -> None:
    temp_name = f".current.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    os.symlink(target, temp_name, dir_fd=control_fd)
    try:
        os.replace(
            temp_name,
            PROOF_CURRENT_LINK,
            src_dir_fd=control_fd,
            dst_dir_fd=control_fd,
        )
        os.fsync(control_fd)
    finally:
        try:
            os.unlink(temp_name, dir_fd=control_fd)
        except FileNotFoundError:
            pass


def _rename_directory_no_replace(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    source_name = _validate_dirfd_component(source_name)
    destination_name = _validate_dirfd_component(destination_name)
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise SystemExit("atomic no-replace generation installation is unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    if renameat2(
        source_parent_fd,
        os.fsencode(source_name),
        destination_parent_fd,
        os.fsencode(destination_name),
        1,  # RENAME_NOREPLACE
    ) != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            destination_name,
        )
    os.fsync(source_parent_fd)
    if destination_parent_fd != source_parent_fd:
        os.fsync(destination_parent_fd)


def _remove_created_anchor(
    root_fd: int,
    anchor_id: str,
) -> None:
    components, name, target = _public_anchor_spec(anchor_id)
    state = _anchor_state(root_fd, components, name, target)
    if state in {"parent_absent", "absent"}:
        return
    if state != "expected":
        raise SystemExit(f"refusing to remove drifted publication anchor: {anchor_id}")
    parent_fd = _open_directory_path(root_fd, components)
    try:
        file_stat = _optional_lstat_at(parent_fd, name)
        if file_stat is None:
            return
        if (
            not stat_module.S_ISLNK(file_stat.st_mode)
            or os.readlink(name, dir_fd=parent_fd) != target
        ):
            raise SystemExit(f"refusing to remove drifted publication anchor: {anchor_id}")
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _ensure_public_anchor(
    root_fd: int,
    anchor_id: str,
) -> bool:
    components, name, target = _public_anchor_spec(anchor_id)
    parent_fd = _open_directory_path(root_fd, components, create=True)
    try:
        file_stat = _optional_lstat_at(parent_fd, name)
        if file_stat is not None:
            if not stat_module.S_ISLNK(file_stat.st_mode) or os.readlink(name, dir_fd=parent_fd) != target:
                raise SystemExit(
                    f"legacy publication anchor requires separately authorized migration: {anchor_id}"
                )
            return False
        os.symlink(target, name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    finally:
        os.close(parent_fd)


def _validate_publication_journal_schema(journal: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = {
        "contract_name",
        "state",
        "generation_id",
        "generation_manifest_sha256",
        "previous_target",
        "new_target",
        "created_anchors",
        "pending_anchor",
        "recovery_disposition",
        "rollback_reason_receipt",
        "rollback_failure_types",
    }
    required_fields = {
        "contract_name",
        "state",
        "generation_id",
        "generation_manifest_sha256",
        "previous_target",
        "new_target",
        "created_anchors",
    }
    if set(journal) - allowed_fields or not required_fields.issubset(journal):
        raise SystemExit("proof publication recovery journal field set is invalid")
    if journal.get("contract_name") != PROOF_PUBLICATION_CONTRACT:
        raise SystemExit("proof publication recovery journal contract is invalid")
    state = str(journal.get("state") or "")
    if state not in {
        "generation_ready",
        "anchors_ready",
        "cutover_pending",
        "committed",
        "rolled_back",
        "rollback_incomplete",
    }:
        raise SystemExit("proof publication recovery journal state is invalid")
    generation_id = str(journal.get("generation_id") or "")
    new_target = _validated_generation_target(
        journal.get("new_target"),
        "proof publication recovery journal new target",
    )
    if generation_id != new_target.removeprefix(f"{PROOF_GENERATIONS_DIRECTORY}/"):
        raise SystemExit("proof publication recovery journal generation id disagrees with its target")
    manifest_digest = str(journal.get("generation_manifest_sha256") or "")
    if len(manifest_digest) != 64 or any(
        character not in "0123456789abcdef" for character in manifest_digest
    ):
        raise SystemExit("proof publication recovery journal manifest digest is invalid")
    previous_target = journal.get("previous_target")
    if previous_target is not None:
        previous_target = _validated_generation_target(
            previous_target,
            "proof publication recovery journal previous target",
        )
    created_anchors = journal.get("created_anchors")
    if (
        not isinstance(created_anchors, list)
        or any(anchor not in {"visual", "startup"} for anchor in created_anchors)
        or len(set(created_anchors)) != len(created_anchors)
    ):
        raise SystemExit("proof publication recovery journal created-anchor list is invalid")
    if tuple(created_anchors) not in {
        (),
        ("visual",),
        ("startup",),
        ("visual", "startup"),
    }:
        raise SystemExit("proof publication recovery journal created-anchor order is invalid")
    pending_anchor = journal.get("pending_anchor")
    if pending_anchor is not None and pending_anchor not in {"visual", "startup"}:
        raise SystemExit("proof publication recovery journal pending anchor is invalid")
    if pending_anchor is not None and pending_anchor in created_anchors:
        raise SystemExit("proof publication recovery journal duplicates its pending anchor")
    if state in {"committed", "cutover_pending", "rolled_back"} and pending_anchor is not None:
        raise SystemExit("proof publication recovery journal terminal state has a pending anchor")
    if state == "generation_ready" and created_anchors:
        raise SystemExit("generation-ready proof publication journal cannot retain created anchors")
    if state == "anchors_ready" and not created_anchors:
        raise SystemExit("anchors-ready proof publication journal has no created anchor")
    if state == "anchors_ready" and pending_anchor is not None and (
        created_anchors != ["visual"] or pending_anchor != "startup"
    ):
        raise SystemExit("anchors-ready proof publication journal has an impossible pending anchor")
    if state == "rolled_back" and created_anchors:
        raise SystemExit("rolled-back proof publication journal retains created anchors")
    if "recovery_disposition" in journal and not isinstance(
        journal.get("recovery_disposition"), str
    ):
        raise SystemExit("proof publication recovery journal disposition is invalid")
    if "rollback_reason_receipt" in journal and not isinstance(
        journal.get("rollback_reason_receipt"), dict
    ):
        raise SystemExit("proof publication recovery journal rollback receipt is invalid")
    rollback_failure_types = journal.get("rollback_failure_types")
    if rollback_failure_types is not None and (
        not isinstance(rollback_failure_types, list)
        or any(not isinstance(item, str) for item in rollback_failure_types)
    ):
        raise SystemExit("proof publication recovery journal rollback failure types are invalid")
    return {
        "state": state,
        "generation_id": generation_id,
        "generation_manifest_sha256": manifest_digest,
        "previous_target": previous_target,
        "new_target": new_target,
        "created_anchors": list(created_anchors),
        "pending_anchor": pending_anchor,
    }


def _validate_journal_generation(
    generations_fd: int,
    generation_id: str,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    manifest = _validate_generation_directory(generations_fd, generation_id)
    generation_fd = _open_directory_at(generations_fd, generation_id)
    try:
        manifest_bytes = _read_file_at(
            generation_fd,
            PROOF_GENERATION_MANIFEST,
            max_bytes=1024 * 1024,
        )
    finally:
        os.close(generation_fd)
    if hashlib.sha256(manifest_bytes).hexdigest().lower() != expected_manifest_sha256:
        raise SystemExit("proof publication recovery journal manifest digest disagrees with generation")
    return manifest


def _recover_publication_journal(
    root_fd: int,
    control_fd: int,
    generations_fd: int,
) -> dict[str, Any] | None:
    journal = _load_optional_json_at(control_fd, PROOF_RECOVERY_JOURNAL)
    if journal is None:
        return None
    validated = _validate_publication_journal_schema(journal)
    state = str(validated["state"])
    generation_id = str(validated["generation_id"])
    manifest_digest = str(validated["generation_manifest_sha256"])
    previous_target = validated["previous_target"]
    new_target = str(validated["new_target"])
    if state in {"committed", "rolled_back"}:
        if state == "committed":
            if _current_generation_target(control_fd) != new_target:
                raise SystemExit("committed proof publication journal disagrees with current pointer")
            _validate_journal_generation(generations_fd, generation_id, manifest_digest)
            _assert_fixed_public_anchors(root_fd)
        elif _current_generation_target(control_fd) != previous_target:
            raise SystemExit("rolled-back proof publication journal disagrees with current pointer")
        elif previous_target is None:
            for anchor_id in ("visual", "startup"):
                if _public_anchor_state(root_fd, anchor_id) not in {"absent", "parent_absent"}:
                    raise SystemExit("rolled-back first publication retained a public anchor")
        else:
            previous_generation_id = previous_target.removeprefix(
                f"{PROOF_GENERATIONS_DIRECTORY}/"
            )
            _validate_generation_directory(generations_fd, previous_generation_id)
            _assert_fixed_public_anchors(root_fd)
        return journal
    if state == "rollback_incomplete":
        raise SystemExit(
            "proof publication has an incomplete rollback; generations and journal were retained for review"
        )
    _validate_journal_generation(generations_fd, generation_id, manifest_digest)
    current_target = _current_generation_target(control_fd)
    if state == "cutover_pending" and current_target == new_target:
        _assert_fixed_public_anchors(root_fd)
        journal["state"] = "committed"
        journal["recovery_disposition"] = "completed_atomic_cutover"
        _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
        return journal
    if current_target != previous_target:
        raise SystemExit(
            "proof publication recovery journal has ambiguous pointer state; retained without mutation"
        )
    rollback_anchors = list(validated["created_anchors"])
    pending_anchor = str(validated.get("pending_anchor") or "")
    if pending_anchor and pending_anchor not in rollback_anchors:
        rollback_anchors.append(pending_anchor)
    try:
        for anchor_id in reversed(rollback_anchors):
            _remove_created_anchor(root_fd, str(anchor_id))
    except BaseException as exc:
        journal["state"] = "rollback_incomplete"
        journal["rollback_failure_types"] = [type(exc).__name__]
        try:
            _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
        except BaseException:
            pass
        raise SystemExit(
            "proof publication recovery could not remove uncommitted anchors; journal retained"
        ) from exc
    journal["state"] = "rolled_back"
    journal["recovery_disposition"] = "removed_uncommitted_anchors"
    journal["created_anchors"] = []
    journal["pending_anchor"] = None
    _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
    return journal


def publish_proof_set_transactionally(
    entries: list[tuple[dict[str, Any], Path]],
    downloads_root: Path,
) -> dict[str, Any]:
    downloads_root = _absolute_lexical_path(downloads_root)
    generation_id, manifest, manifest_bytes, manifest_rows = _proof_generation_manifest(
        entries,
        downloads_root,
    )
    try:
        root_fd = _open_absolute_directory_no_follow(downloads_root)
    except OSError as exc:
        raise SystemExit(
            f"downloads root must already exist as a non-symlink directory: {downloads_root} ({exc})"
        ) from exc
    control_fd: int | None = None
    generations_fd: int | None = None
    lock_fd: int | None = None
    stage_name: str | None = None
    created_anchors: list[str] = []
    previous_target: str | None = None
    previous_target_captured = False
    new_target = f"{PROOF_GENERATIONS_DIRECTORY}/{generation_id}"
    journal: dict[str, Any] = {}
    try:
        _assert_no_legacy_publication_layout(root_fd)
        control_fd = _open_directory_at(
            root_fd,
            PROOF_CONTROL_DIRECTORY,
            create=True,
            mode=0o755,
        )
        lock_fd = os.open(
            PROOF_LOCK_FILE,
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=control_fd,
        )
        lock_stat = os.fstat(lock_fd)
        if not stat_module.S_ISREG(lock_stat.st_mode) or int(lock_stat.st_nlink) != 1:
            raise SystemExit("proof-generation publication lock is not a private regular file")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("another proof-generation publication currently holds the lock") from exc
        _assert_no_legacy_publication_layout(root_fd)
        generations_fd = _open_directory_at(
            control_fd,
            PROOF_GENERATIONS_DIRECTORY,
            create=True,
            mode=0o755,
        )
        recovery = _recover_publication_journal(root_fd, control_fd, generations_fd)
        previous_target = _current_generation_target(control_fd)
        previous_target_captured = True
        existing_generation = _optional_lstat_at(generations_fd, generation_id)
        if existing_generation is None:
            stage_name = f".staging-{generation_id}-{secrets.token_hex(8)}"
            os.mkdir(stage_name, mode=0o700, dir_fd=generations_fd)
            os.fsync(generations_fd)
            stage_fd = _open_directory_at(generations_fd, stage_name)
            try:
                snapshots_by_path = {
                    _absolute_lexical_path(destination)
                    .relative_to(downloads_root)
                    .as_posix(): snapshot
                    for snapshot, destination in entries
                }
                for row in manifest_rows:
                    relative_text = str(row["public_relative_path"])
                    _write_generation_file(
                        stage_fd,
                        relative_text,
                        bytes(snapshots_by_path[relative_text]["data"]),
                    )
                _write_file_at(stage_fd, PROOF_GENERATION_MANIFEST, manifest_bytes)
                staged_files, staged_directories = _generation_tree_layout(stage_fd)
                expected_files = {
                    PROOF_GENERATION_MANIFEST,
                    *(str(row["public_relative_path"]) for row in manifest_rows),
                }
                if set(staged_files) != expected_files:
                    raise SystemExit("staged proof generation has an unexpected file set")
                if set(staged_directories) != {
                    "startup-smoke",
                    "visual-audit",
                    "visual-audit/windows-installer",
                }:
                    raise SystemExit("staged proof generation has an unexpected directory set")
                _seal_generation_tree(stage_fd)
            finally:
                os.close(stage_fd)
            _validate_generation_directory(
                generations_fd,
                generation_id,
                directory_component=stage_name,
                expected_manifest_bytes=manifest_bytes,
            )
            _rename_directory_no_replace(
                generations_fd,
                stage_name,
                generations_fd,
                generation_id,
            )
            stage_name = None
            os.fsync(generations_fd)
        elif not stat_module.S_ISDIR(existing_generation.st_mode) or stat_module.S_ISLNK(
            existing_generation.st_mode
        ):
            raise SystemExit("content-addressed proof generation path is not a real directory")
        _validate_generation_directory(
            generations_fd,
            generation_id,
            expected_manifest_bytes=manifest_bytes,
        )
        journal = {
            "contract_name": PROOF_PUBLICATION_CONTRACT,
            "state": "generation_ready",
            "generation_id": generation_id,
            "generation_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest().lower(),
            "previous_target": previous_target,
            "new_target": new_target,
            "created_anchors": [],
        }
        _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
        for anchor_id in ("visual", "startup"):
            anchor_state = _public_anchor_state(root_fd, anchor_id)
            if anchor_state == "expected":
                continue
            if anchor_state not in {"absent", "parent_absent"}:
                raise SystemExit(
                    f"legacy publication anchor requires separately authorized migration: {anchor_id}"
                )
            journal["pending_anchor"] = anchor_id
            _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
            if not _ensure_public_anchor(root_fd, anchor_id):
                raise SystemExit("publication anchor appeared concurrently while holding the lock")
            created_anchors.append(anchor_id)
            journal["created_anchors"] = list(created_anchors)
            journal["state"] = "anchors_ready"
            journal["pending_anchor"] = None
            _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
        journal["state"] = "cutover_pending"
        _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
        _install_current_pointer(control_fd, new_target)
        journal["state"] = "committed"
        _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
        current_after = _current_generation_target(control_fd)
        if current_after != new_target:
            raise SystemExit("proof generation current pointer drifted after atomic cutover")
        _assert_fixed_public_anchors(root_fd)
        return {
            "contract_name": PROOF_PUBLICATION_CONTRACT,
            "status": "committed",
            "generation_id": generation_id,
            "generation_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest().lower(),
            "item_count": len(manifest_rows),
            "exact_public_relative_paths": list(manifest["exact_public_relative_paths"]),
            "allowed_visual_public_basenames": list(
                manifest["allowed_visual_public_basenames"]
            ),
            "atomic_cutover": True,
            "root_dirfd_no_follow": True,
            "interprocess_lock": "flock_exclusive_nonblocking",
            "recovery_disposition": (
                str(recovery.get("recovery_disposition") or "") if recovery else "none"
            ),
            "previous_generation_retained": previous_target is not None,
        }
    except BaseException as exc:
        rollback_failures: list[str] = []
        if control_fd is not None:
            try:
                if previous_target_captured:
                    current_target = _current_generation_target(control_fd)
                    if current_target == previous_target:
                        pass
                    elif current_target == new_target:
                        if previous_target is None:
                            os.unlink(PROOF_CURRENT_LINK, dir_fd=control_fd)
                            os.fsync(control_fd)
                        else:
                            _install_current_pointer(control_fd, previous_target)
                    else:
                        raise SystemExit(
                            "proof-generation rollback found an ambiguous current pointer"
                        )
                rollback_anchor_ids = list(created_anchors)
                pending_anchor = journal.get("pending_anchor") if journal else None
                if (
                    pending_anchor in {"visual", "startup"}
                    and pending_anchor not in rollback_anchor_ids
                ):
                    rollback_anchor_ids.append(str(pending_anchor))
                for anchor_id in reversed(rollback_anchor_ids):
                    _remove_created_anchor(root_fd, anchor_id)
                if journal:
                    journal["state"] = "rolled_back"
                    journal["created_anchors"] = []
                    journal["pending_anchor"] = None
                    journal["rollback_reason_receipt"] = redacted_stream_receipt(str(exc))
                    _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
            except BaseException as rollback_exc:
                rollback_failures.append(type(rollback_exc).__name__)
                if journal:
                    journal["state"] = "rollback_incomplete"
                    journal["rollback_failure_types"] = rollback_failures
                    try:
                        _atomic_write_json_at(control_fd, PROOF_RECOVERY_JOURNAL, journal)
                    except BaseException:
                        pass
        if rollback_failures:
            raise SystemExit(
                "proof-generation publication failed and rollback is incomplete; "
                "the recovery journal and immutable generations were retained"
            ) from exc
        raise
    finally:
        if stage_name is not None and generations_fd is not None:
            try:
                _remove_tree_at(generations_fd, stage_name)
            except BaseException:
                pass
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        if generations_fd is not None:
            os.close(generations_fd)
        if control_fd is not None:
            os.close(control_fd)
        os.close(root_fd)


def resolve_screenshot(source_root: Path, raw_path: Any, *, bundle_root: Path | None = None) -> Path:
    raw = str(raw_path or "").strip()
    if not raw:
        raise SystemExit("visual audit screenshot row has an empty path")
    if "\x00" in raw:
        raise SystemExit("visual audit screenshot path contains a null byte")
    candidate = Path(raw)
    windows_candidate = PureWindowsPath(raw)
    if candidate.is_absolute() or windows_candidate.is_absolute():
        raise SystemExit(f"visual audit screenshot path must be bundle-relative: {raw}")
    if ".." in candidate.parts or ".." in windows_candidate.parts:
        raise SystemExit(f"visual audit screenshot path contains parent traversal: {raw}")
    direct = source_root / candidate
    _confined_regular_file_lstat(
        direct,
        bundle_root or source_root,
        "visual audit screenshot",
    )
    return _absolute_lexical_path(direct)


def _png_dimensions(data: bytes) -> tuple[int, int]:
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        raise SystemExit("screenshot is not a valid PNG by magic")
    offset = len(signature)
    width = 0
    height = 0
    saw_ihdr = False
    saw_idat = False
    saw_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise SystemExit("screenshot PNG has a truncated chunk")
        chunk_length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(data):
            raise SystemExit("screenshot PNG chunk exceeds the file boundary")
        chunk_data = data[offset + 8 : offset + 8 + chunk_length]
        expected_crc = struct.unpack(">I", data[offset + 8 + chunk_length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise SystemExit("screenshot PNG chunk CRC is invalid")
        if not saw_ihdr:
            if chunk_type != b"IHDR" or chunk_length != 13:
                raise SystemExit("screenshot PNG does not begin with a valid IHDR")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if bit_depth not in {1, 2, 4, 8, 16}:
                raise SystemExit("screenshot PNG has an invalid bit depth")
            if color_type not in {0, 2, 3, 4, 6}:
                raise SystemExit("screenshot PNG has an invalid color type")
            if compression != 0 or filtering != 0 or interlace not in {0, 1}:
                raise SystemExit("screenshot PNG has unsupported encoding metadata")
            saw_ihdr = True
        elif chunk_type == b"IHDR":
            raise SystemExit("screenshot PNG contains multiple IHDR chunks")
        if chunk_type == b"IDAT":
            saw_idat = True
        if chunk_type == b"IEND":
            if chunk_length != 0 or chunk_end != len(data):
                raise SystemExit("screenshot PNG has an invalid or non-terminal IEND")
            saw_iend = True
            break
        offset = chunk_end
    if not (saw_ihdr and saw_idat and saw_iend):
        raise SystemExit("screenshot PNG is missing required image chunks")
    return width, height


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 12 or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise SystemExit("screenshot is not a valid JPEG by magic")
    offset = 2
    dimensions: tuple[int, int] | None = None
    saw_scan = False
    while offset < len(data):
        if data[offset] != 0xFF:
            raise SystemExit("screenshot JPEG has invalid marker framing")
        marker_start = offset
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise SystemExit("screenshot JPEG has a truncated marker")
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            if offset != len(data):
                raise SystemExit("screenshot JPEG has trailing bytes after EOI")
            break
        if marker in {0x01, *range(0xD0, 0xD8)}:
            continue
        if offset + 2 > len(data):
            raise SystemExit("screenshot JPEG has a truncated segment length")
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if segment_length < 2:
            raise SystemExit("screenshot JPEG has an invalid segment length")
        segment_end = offset + segment_length
        if segment_end > len(data):
            raise SystemExit("screenshot JPEG segment exceeds the file boundary")
        if marker in {0xC0, 0xC2}:
            if segment_length < 8:
                raise SystemExit("screenshot JPEG has a truncated frame header")
            height = struct.unpack(">H", data[offset + 3 : offset + 5])[0]
            width = struct.unpack(">H", data[offset + 5 : offset + 7])[0]
            dimensions = (width, height)
        offset = segment_end
        if marker != 0xDA:
            continue
        saw_scan = True
        while offset < len(data):
            marker_start = data.find(b"\xff", offset)
            if marker_start < 0 or marker_start + 1 >= len(data):
                raise SystemExit("screenshot JPEG scan is missing EOI")
            marker_offset = marker_start + 1
            while marker_offset < len(data) and data[marker_offset] == 0xFF:
                marker_offset += 1
            if marker_offset >= len(data):
                raise SystemExit("screenshot JPEG scan has a truncated marker")
            scan_marker = data[marker_offset]
            if scan_marker == 0x00 or 0xD0 <= scan_marker <= 0xD7:
                offset = marker_offset + 1
                continue
            offset = marker_start
            break
    if dimensions is None or not saw_scan:
        raise SystemExit("screenshot JPEG is missing a supported frame or scan")
    return dimensions


def validate_screenshot_image(snapshot: dict[str, Any]) -> dict[str, Any]:
    data = bytes(snapshot.get("data") or b"")
    if not data or len(data) > MAX_SCREENSHOT_BYTES:
        raise SystemExit(
            f"screenshot byte size is outside the allowed range: {snapshot.get('path')}"
        )
    suffix = Path(str(snapshot.get("destination_name") or snapshot.get("path") or "")).suffix.casefold()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if suffix != ".png":
            raise SystemExit("screenshot PNG magic does not match its filename extension")
        image_format = "png"
        width, height = _png_dimensions(data)
    elif data.startswith(b"\xff\xd8"):
        if suffix not in {".jpg", ".jpeg"}:
            raise SystemExit("screenshot JPEG magic does not match its filename extension")
        image_format = "jpeg"
        width, height = _jpeg_dimensions(data)
    else:
        raise SystemExit("screenshot must be a valid PNG or JPEG, not arbitrary content")
    if not (MIN_SCREENSHOT_WIDTH <= width <= MAX_SCREENSHOT_WIDTH):
        raise SystemExit(f"screenshot width is outside the allowed range: {width}")
    if not (MIN_SCREENSHOT_HEIGHT <= height <= MAX_SCREENSHOT_HEIGHT):
        raise SystemExit(f"screenshot height is outside the allowed range: {height}")
    return {
        "format": image_format,
        "width": width,
        "height": height,
        "size_bytes": len(data),
    }


def _native_windows_host_class(value: Any) -> bool:
    host_class = normalized(value).replace("_", "-")
    return host_class == "native-windows" or host_class.startswith("native-windows-")


def _required_sha256(value: Any, label: str) -> str:
    digest = normalized(value).removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SystemExit(f"{label} must record a full SHA-256 digest")
    return digest


def validate_visual_payload_before_import(
    visual_source: Path,
    visual_payload: dict[str, Any],
    *,
    bundle_root: Path | None = None,
) -> list[dict[str, Any]]:
    if normalized(visual_payload.get("status")) != "pass":
        raise SystemExit("visual audit source must have status='pass'")
    if normalized(visual_payload.get("platform")) != "windows":
        raise SystemExit("visual audit source platform must be windows")
    if not _native_windows_host_class(visual_payload.get("hostClass")):
        raise SystemExit("visual audit source must identify a native Windows host")
    _required_sha256(
        visual_payload.get("artifactSha256") or visual_payload.get("artifactDigest"),
        "visual audit source",
    )
    screenshots = visual_payload.get("screenshots")
    if not isinstance(screenshots, list):
        raise SystemExit(f"visual audit source has no screenshots list: {visual_source}")
    if not screenshots:
        raise SystemExit("visual audit source must contain at least one screenshot")
    if len(screenshots) > MAX_SCREENSHOT_COUNT:
        raise SystemExit(
            f"visual audit source exceeds screenshot-count bound: {len(screenshots)} > {MAX_SCREENSHOT_COUNT}"
        )

    effective_bundle_root = bundle_root or visual_source.parent
    surfaces_by_hash: dict[str, set[str]] = {}
    snapshots: list[dict[str, Any]] = []
    destination_names: dict[str, str] = {}
    screenshot_hashes: set[str] = set()
    for row in screenshots:
        if not isinstance(row, dict):
            raise SystemExit("visual audit screenshot row is not an object")
        if row.get("platform") is not None and normalized(row.get("platform")) != "windows":
            raise SystemExit("visual audit screenshot metadata targets a non-Windows platform")
        if row.get("hostClass") is not None and not _native_windows_host_class(row.get("hostClass")):
            raise SystemExit("visual audit screenshot metadata is not from a native Windows host")
        if capture_bounds_look_like_desktop_fallback(row):
            raise SystemExit(
                "visual audit screenshot used full-desktop fallback bounds instead of installer window: "
                f"{row.get('path')}"
            )
        screenshot_source = resolve_screenshot(
            visual_source.parent,
            row.get("path"),
            bundle_root=effective_bundle_root,
        )
        destination_name = screenshot_source.name
        normalized_destination = destination_name.casefold()
        if normalized_destination == VISUAL_SOURCE_NAME.casefold():
            raise SystemExit(
                "visual audit screenshot basename collides with the visual source receipt: "
                f"{destination_name}"
            )
        previous = destination_names.get(normalized_destination)
        if previous is not None:
            raise SystemExit(
                "visual audit screenshot basenames collide on the public downloads shelf: "
                f"{previous} and {row.get('path')}"
            )
        destination_names[normalized_destination] = str(row.get("path") or "")
        snapshot = stable_bundle_file_snapshot(
            screenshot_source,
            effective_bundle_root,
            "visual audit screenshot",
        )
        snapshot["destination_name"] = destination_name
        image_metadata = validate_screenshot_image(snapshot)
        declared_sha256 = normalized(row.get("sha256") or row.get("screenshotSha256")).removeprefix(
            "sha256:"
        )
        if declared_sha256 and declared_sha256 != str(snapshot["sha256"]):
            raise SystemExit(
                f"visual audit screenshot declared SHA-256 does not match its bytes: {row.get('path')}"
            )
        if str(snapshot["sha256"]) in screenshot_hashes:
            raise SystemExit(
                "visual audit screenshots must have distinct image hashes: "
                f"{row.get('path')}"
            )
        screenshot_hashes.add(str(snapshot["sha256"]))
        snapshot["image_metadata"] = image_metadata
        snapshots.append(snapshot)
        surface = normalized_surface(row.get("surface"))
        if surface in REQUIRED_SURFACES:
            surfaces_by_hash.setdefault(str(snapshot["sha256"]), set()).add(surface)

    for screenshot_sha, surfaces in sorted(surfaces_by_hash.items()):
        if len(surfaces) > 1:
            raise SystemExit(
                "visual audit screenshots for distinct required surfaces are byte-identical: "
                f"{screenshot_sha} covers {', '.join(sorted(surfaces))}"
            )
    return snapshots


def validate_visual_payload_matches_promoted_digest(
    visual_source: Path,
    visual_payload: dict[str, Any],
    promoted_digest: str,
) -> None:
    if not promoted_digest:
        return
    visual_digest = normalized(
        visual_payload.get("artifactSha256")
        or visual_payload.get("artifactDigest")
    ).removeprefix("sha256:")
    if not visual_digest:
        raise SystemExit(
            "visual audit source is missing the artifact digest required to match the promoted installer: "
            f"{visual_source}"
        )
    if visual_digest != promoted_digest:
        raise SystemExit(
            "visual audit source digest does not match the promoted installer: "
            f"{visual_source}"
        )


def import_artifact(artifact_root: Path, downloads_root: Path, *, intake_request: Path | None = None) -> dict[str, Any]:
    intake_payload = load_intake_payload_for_import(intake_request)
    startup_receipt_bundle_required = startup_receipt_bundle_required_from_intake(intake_payload)
    promoted_digest = promoted_digest_from_intake(intake_payload)
    immutable_bundle_root = _absolute_lexical_path(artifact_root)
    startup_source = find_optional_unique(artifact_root, STARTUP_RECEIPT_NAME)
    visual_source = find_unique(artifact_root, VISUAL_SOURCE_NAME)
    visual_snapshot = stable_bundle_file_snapshot(
        visual_source,
        immutable_bundle_root,
        "visual audit source receipt",
    )
    visual_payload = load_json_snapshot(
        visual_snapshot,
        "visual audit source receipt",
    )
    screenshot_snapshots = validate_visual_payload_before_import(
        visual_source,
        visual_payload,
        bundle_root=immutable_bundle_root,
    )
    validate_visual_payload_matches_promoted_digest(visual_source, visual_payload, promoted_digest)

    startup_destination = downloads_root / "startup-smoke" / STARTUP_RECEIPT_NAME
    visual_destination_root = downloads_root / "visual-audit" / "windows-installer"
    visual_destination = visual_destination_root / VISUAL_SOURCE_NAME

    startup_receipt_source = "artifact_bundle"
    startup_snapshot: dict[str, Any] | None = None
    if startup_source is not None:
        startup_snapshot = stable_bundle_file_snapshot(
            startup_source,
            immutable_bundle_root,
            "bundled startup receipt",
        )
        startup_payload = load_json_snapshot(
            startup_snapshot,
            "bundled startup receipt",
        )
        validate_bundled_startup_receipt(
            startup_source,
            promoted_digest,
            payload=startup_payload,
        )
    else:
        raise SystemExit(
            f"proof artifact is missing {STARTUP_RECEIPT_NAME}; complete generation publication "
            "requires the native startup receipt inside the bounded ZIP"
        )

    proof_set_entries: list[tuple[dict[str, Any], Path]] = []
    if startup_snapshot is not None:
        proof_set_entries.append((startup_snapshot, startup_destination))
    proof_set_entries.append((visual_snapshot, visual_destination))

    copied_screenshots: list[str] = []
    screenshot_bindings: list[dict[str, Any]] = []
    for snapshot in screenshot_snapshots:
        screenshot_destination = visual_destination_root / str(snapshot["destination_name"])
        proof_set_entries.append((snapshot, screenshot_destination))
        copied_screenshots.append(str(screenshot_destination))
        screenshot_bindings.append(
            {
                "source_path": str(snapshot["path"]),
                "destination_path": str(screenshot_destination),
                "sha256": str(snapshot["sha256"]),
                "source_identity": dict(snapshot["identity"]),
                "image": dict(snapshot["image_metadata"]),
            }
        )
    proof_set_transaction = publish_proof_set_transactionally(
        proof_set_entries,
        downloads_root,
    )

    return {
        "startupReceipt": str(startup_destination),
        "startupReceiptSource": startup_receipt_source,
        "startupReceiptBundleRequired": startup_receipt_bundle_required,
        "visualAuditSource": str(visual_destination),
        "screenshots": copied_screenshots,
        "screenshotBindings": screenshot_bindings,
        "proofSetTransaction": proof_set_transaction,
        "programBindings": {
            "importer": dict(IMPORTER_PROGRAM_BINDING_AT_LOAD),
        },
    }


def run_post_import_chain(
    intake_request: Path,
    downloads_root: Path,
    *,
    plan: dict[str, Any] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    effective_plan = plan or build_code_owned_post_import_plan(
        downloads_root,
        intake_request,
    )
    results = execute_code_owned_post_import_plan(effective_plan)
    receipt = post_import_plan_receipt(effective_plan, results)
    status = str(receipt.get("status") or "")
    return (0 if status == "pass" else (4 if status == "pending_authorized_external_mutation" else 1)), results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a windows-installer-gold-proof bundle into the downloads proof shelf.")
    parser.add_argument("artifact", type=Path, help="Exported Windows proof bundle zip.")
    parser.add_argument("--downloads-root", type=Path, default=DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--intake-request", type=Path, default=DEFAULT_INTAKE_REQUEST)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run the post-import verification chain after import, falling back to verify_windows_installer_visual_audit.py.",
    )
    parser.add_argument(
        "--authorize-external-mutations",
        action="store_true",
        help=(
            "Explicitly authorize the code-owned Teable sync and promotion-attempt phase. "
            "Intake JSON cannot grant this authority."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with tempfile.TemporaryDirectory(prefix="windows-installer-gold-proof-import-") as temp_dir:
        artifact_root = extracted_or_directory(args.artifact, Path(temp_dir))
        summary = import_artifact(artifact_root, args.downloads_root, intake_request=args.intake_request)

    result: dict[str, Any] = {
        "status": "imported",
        **summary,
        "programBindings": {
            "importer": dict(IMPORTER_PROGRAM_BINDING_AT_LOAD),
            "auto_importer": program_file_binding(
                ROOT / "scripts" / "auto_import_windows_installer_gold_proof.py",
                "windows_installer_gold_proof_auto_importer",
            ),
        },
    }
    if args.verify:
        intake_payload = load_optional_json(args.intake_request)
        plan = build_code_owned_post_import_plan(
            args.downloads_root,
            args.intake_request,
            authorize_external_mutations=bool(args.authorize_external_mutations),
        )
        returncode, command_results = run_post_import_chain(
            args.intake_request,
            args.downloads_root,
            plan=plan,
        )
        result["intakePostImportGates"] = request_post_import_gate_metadata(
            intake_payload
        )
        result["postImportPlan"] = post_import_plan_receipt(
            plan,
            command_results,
        )
        result["postImportCommands"] = command_results
        print(json.dumps(result, indent=2))
        return returncode
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
