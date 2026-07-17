#!/usr/bin/env python3
"""Declare and finalize immutable, build-bound provenance for a regular file."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT_NAME = "chummer6.build_provenance.v1"
STATE_CONTRACT_NAME = "chummer6.build_provenance_invocation_state.v1"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\\\/]")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_support(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("chummer_portable_build_provenance_support", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load build provenance support: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def exclusive_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(encoded)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def base_receipt(args: argparse.Namespace, status: str, failures: list[str]) -> dict[str, object]:
    return {
        "contract_name": CONTRACT_NAME,
        "receipt_kind": "invocation",
        "status": status,
        "builder_id": args.builder_id,
        "build_type": args.build_type,
        "invocation_id": args.invocation_id,
        "generated_at_utc": utc_now(),
        "subjects": [],
        "failures": failures,
        "assurance": (
            "structural build-invocation evidence with a pre-build authority nonce; "
            "release use requires a separate code-pinned detached builder attestation"
        ),
    }


def public_state_projection(state: dict[str, object]) -> dict[str, object]:
    """Return the receipt-safe state while the private state file retains host paths."""

    projected = json.loads(json.dumps(state))
    invocation_id = str(projected.get("invocation_id") or "unknown")
    projected["state_path"] = f"private-state/{invocation_id}.json"
    projected["output_path"] = f"proof/build-provenance/v1/invocations/{invocation_id}.json"

    source = projected.get("source") if isinstance(projected.get("source"), dict) else {}
    source_repository = str(source.get("repository") or "source")
    source["repo_root"] = f"sources/{source_repository}"

    materials = projected.get("source_materials") if isinstance(projected.get("source_materials"), list) else []
    for material in materials:
        if isinstance(material, dict):
            repository = str(material.get("repository") or "source")
            material["repo_root"] = f"sources/{repository}"

    declaration = (
        projected.get("subject_declaration")
        if isinstance(projected.get("subject_declaration"), dict)
        else {}
    )
    artifact_name = Path(str(declaration.get("artifact_name") or "artifact")).name
    if "artifact_path" in declaration:
        declaration["artifact_path"] = f"files/{artifact_name}"
    prebuild = declaration.get("prebuild") if isinstance(declaration.get("prebuild"), dict) else {}
    if "path" in prebuild:
        prebuild["path"] = f"files/{artifact_name}"

    target_id = str(declaration.get("target_id") or "target")
    sbom = projected.get("sbom") if isinstance(projected.get("sbom"), dict) else {}
    sbom["path"] = f"proof/build-provenance/v1/sbom/{target_id}.cdx.json"
    sbom["source_assets_path"] = f"build-inputs/{target_id}.project.assets.json"

    tools = projected.get("build_tools") if isinstance(projected.get("build_tools"), dict) else {}
    if "provenance_generator_path" in tools:
        tools["provenance_generator_path"] = "scripts/release/materialize_build_provenance.py"
    if "supply_chain_verifier_path" in tools:
        tools["supply_chain_verifier_path"] = "scripts/release/build_provenance_support.py"

    inputs = projected.get("build_inputs") if isinstance(projected.get("build_inputs"), list) else []
    for build_input in inputs:
        if isinstance(build_input, dict):
            label = str(build_input.get("label") or "input")
            build_input["path"] = f"build-inputs/{label}"

    validate_public_projection(projected)
    return projected


def validate_public_projection(payload: object, location: str = "receipt") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized_key in {
                "authorization",
                "bearer",
                "password",
                "private_key",
                "refresh_token",
                "access_token",
                "upload_ticket",
                "api_key",
            }:
                raise RuntimeError(f"public provenance contains a forbidden secret field at {location}")
            validate_public_projection(value, f"{location}.{key}")
        return
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            validate_public_projection(value, f"{location}[{index}]")
        return
    if not isinstance(payload, str):
        return

    value = payload.strip()
    if (
        value.startswith(("/", "~", "\\\\"))
        or WINDOWS_ABSOLUTE_PATH_RE.match(value)
        or "\\" in value
        or ".." in value.split("/")
    ):
        raise RuntimeError(f"public provenance contains an unsafe host path at {location}")


def within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def parse_named_path(raw: str, label: str) -> tuple[str, Path]:
    name, separator, value = raw.partition("=")
    if not separator or not SAFE_ID_RE.fullmatch(name) or not value.strip():
        raise RuntimeError(f"{label} must use a safe name=/absolute/path declaration")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RuntimeError(f"{label} path must be absolute: {name}")
    return name, path.resolve()


def declared_build_inputs(values: list[str], support: Any) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        name, path = parse_named_path(value, "build input")
        if name in seen or not path.is_file() or path.is_symlink():
            raise RuntimeError(f"declared build input is duplicate, unavailable, or a symlink: {name}")
        seen.add(name)
        records.append({"label": name, "path": str(path), "sha256": support.sha256_file(path)})
    return records


def source_materials(values: list[str], support: Any) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        name, path = parse_named_path(value, "source material")
        if name in seen or not path.is_dir():
            raise RuntimeError(f"source material is duplicate or unavailable: {name}")
        commit, tree, dirty = support.git_revision(path)
        if dirty:
            raise RuntimeError(f"source material has worktree changes: {name}")
        seen.add(name)
        records.append(
            {
                "repository": name,
                "repo_root": str(path),
                "commit": commit,
                "tree": tree,
                "tracked_worktree_dirty": False,
                "worktree_dirty": False,
                "untracked_build_inputs_included": True,
            }
        )
    return records


def validate_common(args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    for field in ("builder_id", "build_type", "invocation_id"):
        value = str(getattr(args, field) or "")
        if not SAFE_ID_RE.fullmatch(value):
            failures.append(f"{field} is blank or unsafe")
    return failures


def begin(args: argparse.Namespace) -> int:
    raw_output = args.output.expanduser().absolute()
    raw_state = args.state.expanduser().absolute()
    if os.path.lexists(raw_output) or os.path.lexists(raw_state):
        print("build_provenance_failure=invocation output or state already exists", file=sys.stderr)
        return 1
    output = raw_output.resolve()
    state_path = raw_state.resolve()
    authority_nonce = secrets.token_hex(32)
    pending = base_receipt(args, "initializing", [])
    pending["authority_nonce"] = authority_nonce
    try:
        exclusive_write_json(output, pending)
        exclusive_write_json(
            state_path,
            {
                "state_contract_name": STATE_CONTRACT_NAME,
                "status": "initializing",
                "invocation_id": args.invocation_id,
                "authority_nonce": authority_nonce,
            },
        )
    except OSError as exc:
        pending["status"] = "fail"
        pending["failures"] = [f"invocation reservation failed: {type(exc).__name__}"]
        if output.exists():
            atomic_write_json(output, pending)
        print(f"build_provenance_failure={pending['failures'][0]}", file=sys.stderr)
        return 1

    failures = validate_common(args)
    support_path = args.support_script.expanduser().resolve()
    try:
        support = load_support(support_path)
    except (OSError, RuntimeError) as exc:
        failures.append(str(exc))
        support = None

    source_root = args.source_repo_root.expanduser().resolve()
    build_root = args.build_root.expanduser().resolve()
    project_path = (build_root / args.project_path).resolve()
    artifact_path = args.artifact_path.expanduser().resolve()
    sbom_path = args.sbom_path.expanduser().resolve()
    if not within(build_root, project_path):
        failures.append("project path escapes the build root")
    if Path(args.artifact_name).name != args.artifact_name:
        failures.append("artifact name must be a basename")
    if not SAFE_ID_RE.fullmatch(args.artifact_id) or not SAFE_ID_RE.fullmatch(args.target_id):
        failures.append("artifact id or target id is blank or unsafe")
    if args.artifact_kind != "desktop_download":
        failures.append("portable file provenance only accepts artifact kind desktop_download")

    started_epoch_ns = time.time_ns()
    started_at = utc_now()
    commit = tree = ""
    dirty = True
    material_records: list[dict[str, object]] = []
    build_inputs: list[dict[str, object]] = []
    prebuild: dict[str, object] = {"exists": False, "path": str(artifact_path)}
    assets_path = project_path.parent / "obj" / "project.assets.json"
    assets_sha256 = inventory_sha256 = sbom_sha256 = ""
    if support is not None:
        try:
            commit, tree, dirty = support.git_revision(source_root)
            if dirty:
                failures.append(f"source repository has worktree changes: {args.source_repository}")
        except RuntimeError as exc:
            failures.append(str(exc))
        try:
            material_records = source_materials(args.source_material, support)
        except RuntimeError as exc:
            failures.append(str(exc))
        try:
            target = support.ProjectTarget(args.target_id, args.source_repository, source_root, project_path)
            assets, assets_error, assets_path = support.load_assets(target)
            if assets_error or assets is None:
                raise RuntimeError(assets_error or "restore assets are unavailable")
            assets_sha256 = support.sha256_file(assets_path)
            inventory_sha256 = support.dependency_inventory_sha256(assets)
            support.atomic_write_json(sbom_path, support.build_cyclonedx(target, assets, inventory_sha256))
            sbom_sha256 = support.sha256_file(sbom_path)
        except (OSError, RuntimeError, ValueError) as exc:
            failures.append(f"deterministic SBOM generation failed: {exc}")
        try:
            build_inputs = declared_build_inputs(args.build_input, support)
        except RuntimeError as exc:
            failures.append(str(exc))
        try:
            prebuild = support.file_snapshot(artifact_path)
        except (OSError, RuntimeError) as exc:
            failures.append(f"pre-build artifact identity capture failed: {exc}")

    state: dict[str, object] = {
        "state_contract_name": STATE_CONTRACT_NAME,
        "state_path": str(state_path),
        "output_path": str(output),
        "builder_id": args.builder_id,
        "build_type": args.build_type,
        "invocation_id": args.invocation_id,
        "authority_nonce": authority_nonce,
        "started_at_utc": started_at,
        "started_epoch_ns": started_epoch_ns,
        "source": {
            "repository": args.source_repository,
            "repo_root": str(source_root),
            "commit": commit,
            "tree": tree,
            "tracked_worktree_dirty": dirty,
            "worktree_dirty": dirty,
            "untracked_build_inputs_included": True,
        },
        "source_materials": material_records,
        "subject_declaration": {
            "artifact_id": args.artifact_id,
            "artifact_kind": args.artifact_kind,
            "artifact_name": args.artifact_name,
            "artifact_binding_type": "file",
            "artifact_path": str(artifact_path),
            "target_id": args.target_id,
            "prebuild": prebuild,
        },
        "sbom": {
            "path": str(sbom_path),
            "sha256": sbom_sha256,
            "source_assets_path": str(assets_path),
            "source_assets_sha256": assets_sha256,
            "dependency_inventory_sha256": inventory_sha256,
            "generator": "deterministic_project.assets.json_inventory.v1",
        },
        "build_tools": {
            "provenance_generator_path": str(Path(__file__).resolve()),
            "provenance_generator_sha256": support.sha256_file(Path(__file__).resolve()) if support else "",
            "supply_chain_verifier_path": str(support_path),
            "supply_chain_verifier_sha256": support.sha256_file(support_path) if support and support_path.is_file() else "",
        },
        "build_inputs": build_inputs,
    }
    if failures:
        failed = base_receipt(args, "fail", failures)
        failed["authority_nonce"] = authority_nonce
        failed["build_started_at_utc"] = started_at
        atomic_write_json(output, failed)
        state_path.unlink(missing_ok=True)
        for failure in failures:
            print(f"build_provenance_failure={failure}", file=sys.stderr)
        return 1

    support.atomic_write_json(state_path, state)
    pending["status"] = "in_progress"
    pending["authority_nonce"] = authority_nonce
    pending["build_started_at_utc"] = started_at
    pending["invocation"] = {
        "state_contract_name": STATE_CONTRACT_NAME,
        "state_sha256": support.canonical_json_sha256(state),
        "subject_declared_before_build": True,
    }
    atomic_write_json(output, pending)
    print(f"build_provenance_begin={args.invocation_id}")
    return 0


def finalize(args: argparse.Namespace) -> int:
    output = args.output.expanduser().absolute()
    state_path = args.state.expanduser().absolute()
    if output.is_symlink() or state_path.is_symlink():
        print("build_provenance_failure=invocation output and state must not be symlinks", file=sys.stderr)
        return 1
    try:
        pending = json.loads(output.read_text(encoding="utf-8"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"build_provenance_failure=invocation state is unavailable: {type(exc).__name__}", file=sys.stderr)
        return 1
    if not isinstance(pending, dict) or not isinstance(state, dict):
        print("build_provenance_failure=invocation state is malformed", file=sys.stderr)
        return 1
    authority_nonce = str(pending.get("authority_nonce") or "").lower()
    if not SHA256_RE.fullmatch(authority_nonce):
        print("build_provenance_failure=invocation authority_nonce is invalid", file=sys.stderr)
        return 1
    marker = state_path.with_name(f".{state_path.name}.finalized")
    try:
        marker.mkdir(mode=0o700)
    except OSError as exc:
        print(f"build_provenance_failure=invocation finalization already claimed: {type(exc).__name__}", file=sys.stderr)
        return 1

    failures = validate_common(args)
    for field in ("builder_id", "build_type", "invocation_id"):
        if str(state.get(field) or "") != str(getattr(args, field)):
            failures.append(f"invocation state {field} mismatch")
    if str(state.get("authority_nonce") or "").lower() != authority_nonce:
        failures.append("invocation state authority_nonce mismatch")
    if pending.get("status") != "in_progress" or pending.get("invocation_id") != args.invocation_id:
        failures.append("invocation receipt is not pending finalization")
    support_path = Path(str(((state.get("build_tools") or {}).get("supply_chain_verifier_path") or ""))).resolve()
    try:
        support = load_support(support_path)
    except (OSError, RuntimeError) as exc:
        print(f"build_provenance_failure={exc}", file=sys.stderr)
        return 1
    invocation = pending.get("invocation") if isinstance(pending.get("invocation"), dict) else {}
    if invocation.get("state_sha256") != support.canonical_json_sha256(state):
        failures.append("pending receipt belongs to a different or invalid invocation state")
    if state.get("state_contract_name") != STATE_CONTRACT_NAME:
        failures.append("invocation state contract mismatch")

    tools = state.get("build_tools") if isinstance(state.get("build_tools"), dict) else {}
    for path_field, sha_field, label in (
        ("provenance_generator_path", "provenance_generator_sha256", "provenance generator"),
        ("supply_chain_verifier_path", "supply_chain_verifier_sha256", "provenance support"),
    ):
        path = Path(str(tools.get(path_field) or ".")).resolve()
        expected = str(tools.get(sha_field) or "")
        if not path.is_file() or not SHA256_RE.fullmatch(expected) or support.sha256_file(path) != expected:
            failures.append(f"{label} changed during the build invocation")

    source = state.get("source") if isinstance(state.get("source"), dict) else {}
    source_root = Path(str(source.get("repo_root") or ".")).resolve()
    commit = tree = ""
    dirty = True
    try:
        commit, tree, dirty = support.git_revision(source_root)
    except RuntimeError as exc:
        failures.append(str(exc))
    if dirty or commit != source.get("commit") or tree != source.get("tree"):
        failures.append("source revision changed or became dirty during the build invocation")
    for material in state.get("source_materials") or []:
        if not isinstance(material, dict):
            failures.append("source material record is malformed")
            continue
        try:
            current_commit, current_tree, current_dirty = support.git_revision(Path(str(material.get("repo_root") or ".")))
        except RuntimeError as exc:
            failures.append(str(exc))
            continue
        if current_dirty or current_commit != material.get("commit") or current_tree != material.get("tree"):
            failures.append(f"source material changed or became dirty: {material.get('repository') or '<unknown>'}")

    declaration = state.get("subject_declaration") if isinstance(state.get("subject_declaration"), dict) else {}
    artifact_path = Path(str(declaration.get("artifact_path") or ".")).resolve()
    try:
        postbuild = support.file_snapshot(artifact_path)
    except (OSError, RuntimeError) as exc:
        postbuild = {"exists": False}
        failures.append(f"post-build artifact identity capture failed: {exc}")
    if not postbuild.get("exists"):
        failures.append(f"declared build artifact is unavailable: {artifact_path}")
    elif int(postbuild.get("mtime_ns") or 0) <= int(state.get("started_epoch_ns") or 0):
        failures.append("artifact was not produced after the build invocation began")
    prebuild = declaration.get("prebuild") if isinstance(declaration.get("prebuild"), dict) else {}
    if prebuild.get("exists") and postbuild.get("exists"):
        same_identity = (
            int(prebuild.get("inode") or 0) > 0
            and int(prebuild.get("inode") or 0) == int(postbuild.get("inode") or 0)
            and int(prebuild.get("device") or 0) == int(postbuild.get("device") or 0)
        )
        same_content = (
            prebuild.get("sha256") == postbuild.get("sha256")
            and prebuild.get("size_bytes") == postbuild.get("size_bytes")
        )
        if same_identity and same_content:
            failures.append("artifact identity and content are unchanged from the pre-build snapshot")

    sbom = state.get("sbom") if isinstance(state.get("sbom"), dict) else {}
    for path_field, sha_field, label in (
        ("path", "sha256", "build-time SBOM"),
        ("source_assets_path", "source_assets_sha256", "restore assets"),
    ):
        path = Path(str(sbom.get(path_field) or ".")).resolve()
        expected = str(sbom.get(sha_field) or "")
        if not path.is_file() or not SHA256_RE.fullmatch(expected) or support.sha256_file(path) != expected:
            failures.append(f"{label} changed or is unavailable")
    for build_input in state.get("build_inputs") or []:
        if not isinstance(build_input, dict):
            failures.append("declared build input record is malformed")
            continue
        path = Path(str(build_input.get("path") or ".")).resolve()
        expected = str(build_input.get("sha256") or "")
        if not path.is_file() or not SHA256_RE.fullmatch(expected) or support.sha256_file(path) != expected:
            failures.append(f"declared build input changed or is unavailable: {build_input.get('label') or '<unknown>'}")

    public_state = public_state_projection(state)
    receipt = base_receipt(args, "fail" if failures else "pass", failures)
    receipt["authority_nonce"] = authority_nonce
    receipt["build_started_at_utc"] = str(state.get("started_at_utc") or "")
    receipt["invocation"] = {
        "state_contract_name": STATE_CONTRACT_NAME,
        "state_sha256": support.canonical_json_sha256(public_state),
        "state": public_state,
        "public_projection": "portable_path_references.v1",
        "subject_declared_before_build": True,
        "source_identity_stable": not failures,
    }
    if not failures:
        receipt["subjects"] = [
            {
                "artifact_id": str(declaration.get("artifact_id") or ""),
                "artifact_kind": str(declaration.get("artifact_kind") or ""),
                "artifact_name": str(declaration.get("artifact_name") or ""),
                "artifact_sha256": str(postbuild.get("sha256") or ""),
                "artifact_size_bytes": int(postbuild.get("size_bytes") or 0),
                "artifact_built_mtime_ns": int(postbuild.get("mtime_ns") or 0),
                "target_id": str(declaration.get("target_id") or ""),
                "source_repository": str(source.get("repository") or ""),
                "source_commit": commit,
                "source_tree": tree,
                "source_tracked_worktree_dirty": False,
                "source_worktree_dirty": False,
                "source_untracked_build_inputs_included": True,
                "source_materials": public_state.get("source_materials") or [],
                "sbom_sha256": str(sbom.get("sha256") or ""),
                "sbom_generator": str(sbom.get("generator") or ""),
                "invocation_id": args.invocation_id,
                "authority_nonce": authority_nonce,
                "produced_during_invocation": True,
            }
        ]
    atomic_write_json(output, receipt)
    if failures:
        for failure in failures:
            print(f"build_provenance_failure={failure}", file=sys.stderr)
        return 1
    print(f"build_provenance_receipt={output}")
    return 0


def common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--builder-id", required=True)
    parser.add_argument("--build-type", required=True)
    parser.add_argument("--invocation-id", required=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    begin_parser = commands.add_parser("begin")
    common_arguments(begin_parser)
    begin_parser.add_argument(
        "--support-script",
        type=Path,
        default=Path(__file__).resolve().with_name("build_provenance_support.py"),
    )
    begin_parser.add_argument("--source-repository", required=True)
    begin_parser.add_argument("--source-repo-root", type=Path, required=True)
    begin_parser.add_argument("--source-material", action="append", default=[])
    begin_parser.add_argument("--build-root", type=Path, required=True)
    begin_parser.add_argument("--target-id", required=True)
    begin_parser.add_argument("--project-path", type=Path, required=True)
    begin_parser.add_argument("--artifact-id", required=True)
    begin_parser.add_argument("--artifact-kind", required=True)
    begin_parser.add_argument("--artifact-name", required=True)
    begin_parser.add_argument("--artifact-path", type=Path, required=True)
    begin_parser.add_argument("--sbom-path", type=Path, required=True)
    begin_parser.add_argument("--build-input", action="append", default=[])
    finalize_parser = commands.add_parser("finalize")
    common_arguments(finalize_parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    return begin(args) if args.command == "begin" else finalize(args)


if __name__ == "__main__":
    raise SystemExit(main())
