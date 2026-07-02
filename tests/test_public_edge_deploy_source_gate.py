from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_public_edge_deploy_source.py"
SPEC = importlib.util.spec_from_file_location("verify_public_edge_deploy_source", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

GUARDED_DOCKERFILE = """
FROM scratch
RUN test -f /app/publish/wwwroot/service-worker.js \
 && grep -q 'const CACHE_NAME = "chummer-public-v4";' /app/publish/wwwroot/service-worker.js \
 && ! grep -q 'play-shell-v' /app/publish/wwwroot/service-worker.js
""".lstrip()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def make_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Chummer Tests")
    (repo / "README.md").write_text("clean deploy source\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "initial")
    return repo, git(repo, "rev-parse", "HEAD")


def make_named_repo(path: Path) -> tuple[Path, str]:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "tests@example.invalid")
    git(path, "config", "user.name", "Chummer Tests")
    (path / "README.md").write_text(f"clean deploy source at {path.name}\n", encoding="utf-8")
    (path / "Chummer.Run.Api").mkdir()
    (path / "Chummer.Run.Api" / "Dockerfile").write_text(GUARDED_DOCKERFILE, encoding="utf-8")
    git(path, "add", "README.md", "Chummer.Run.Api/Dockerfile")
    git(path, "commit", "-qm", "initial")
    return path, git(path, "rev-parse", "HEAD")


def write_compose(path: Path, context: Path, source_dir_name: str) -> Path:
    compose_path = path / "docker-compose.public-edge.yml"
    compose_path.write_text(
        f"""
services:
  chummer-portal:
    build:
      context: {context}
      dockerfile: {source_dir_name}/Chummer.Run.Api/Dockerfile
""".lstrip(),
        encoding="utf-8",
    )
    return compose_path


def test_clean_source_at_expected_head_passes() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))

        receipt = MODULE.verify(repo, expected_head=head)

    assert receipt["status"] == "pass"
    assert receipt["dirtyLineCount"] == 0
    assert receipt["head"] == head


def test_dirty_source_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))
        (repo / "README.md").write_text("dirty deploy source\n", encoding="utf-8")

        receipt = MODULE.verify(repo, expected_head=head)

    assert receipt["status"] == "fail"
    assert receipt["dirtyLineCount"] == 1
    assert any(finding["id"] == "dirty_worktree" for finding in receipt["findings"])


def test_generated_proof_drift_can_be_ignored_when_explicitly_requested() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))
        proof = repo / ".codex-studio" / "published" / "LIVE_SURFACE_PARITY.generated.json"
        proof.parent.mkdir(parents=True)
        proof.write_text("{}\n", encoding="utf-8")

        strict_receipt = MODULE.verify(repo, expected_head=head)
        relaxed_receipt = MODULE.verify(repo, expected_head=head, ignore_generated_proof_drift=True)

    assert strict_receipt["status"] == "fail"
    assert any(finding["id"] == "dirty_worktree" for finding in strict_receipt["findings"])
    assert relaxed_receipt["status"] == "pass"
    assert relaxed_receipt["totalDirtyLineCount"] == 1
    assert relaxed_receipt["dirtyLineCount"] == 0
    assert relaxed_receipt["ignoredDirtyLineCount"] == 1
    assert relaxed_receipt["ignoredDirtyLines"][0].endswith(".codex-studio/published/LIVE_SURFACE_PARITY.generated.json")


def test_tracked_generated_proof_modification_can_be_ignored_when_explicitly_requested() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, _head = make_repo(Path(temp))
        proof = repo / ".codex-studio" / "published" / "LIVE_SURFACE_PARITY.generated.json"
        proof.parent.mkdir(parents=True)
        proof.write_text("{}\n", encoding="utf-8")
        git(repo, "add", ".codex-studio/published/LIVE_SURFACE_PARITY.generated.json")
        git(repo, "commit", "-qm", "add generated proof")
        head = git(repo, "rev-parse", "HEAD")
        proof.write_text('{"status":"pass"}\n', encoding="utf-8")

        receipt = MODULE.verify(repo, expected_head=head, ignore_generated_proof_drift=True)

    assert receipt["status"] == "pass"
    assert receipt["totalDirtyLineCount"] == 1
    assert receipt["dirtyLineCount"] == 0
    assert receipt["ignoredDirtyLineCount"] == 1
    assert receipt["ignoredDirtyLines"][0].endswith(".codex-studio/published/LIVE_SURFACE_PARITY.generated.json")


def test_generated_proof_drift_ignore_does_not_hide_source_drift() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))
        proof = repo / ".codex-studio" / "published" / "LIVE_SURFACE_PARITY.generated.json"
        proof.parent.mkdir(parents=True)
        proof.write_text("{}\n", encoding="utf-8")
        (repo / "README.md").write_text("dirty deploy source\n", encoding="utf-8")

        receipt = MODULE.verify(repo, expected_head=head, ignore_generated_proof_drift=True)

    assert receipt["status"] == "fail"
    assert receipt["totalDirtyLineCount"] == 2
    assert receipt["dirtyLineCount"] == 1
    assert receipt["ignoredDirtyLineCount"] == 1
    assert any("README.md" in line for line in receipt["dirtyLines"])
    assert any(finding["id"] == "dirty_worktree" for finding in receipt["findings"])


def test_untracked_source_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))
        (repo / "untracked.txt").write_text("do not deploy me\n", encoding="utf-8")

        receipt = MODULE.verify(repo, expected_head=head)

    assert receipt["status"] == "fail"
    assert receipt["dirtyLineCount"] == 1
    assert any("untracked.txt" in line for line in receipt["dirtyLines"])


def test_wrong_expected_head_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, _head = make_repo(Path(temp))
        wrong = "0" * 40

        receipt = MODULE.verify(repo, expected_head=wrong)

    assert receipt["status"] == "fail"
    assert any(finding["id"] == "wrong_head" for finding in receipt["findings"])


def test_compose_build_source_matching_repo_passes() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        temp_root = Path(temp)
        context = temp_root / "context"
        repo, head = make_named_repo(context / "chummer.run-services")
        compose = write_compose(temp_root, context, "chummer.run-services")

        receipt = MODULE.verify(
            repo,
            expected_head=head,
            compose_file=compose,
            compose_service="chummer-portal",
        )

    assert receipt["status"] == "pass"
    assert receipt["composeBuildSource"].endswith("chummer.run-services")
    assert receipt["composeDockerfileSource"].endswith("chummer.run-services")


def test_compose_build_source_mismatch_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        temp_root = Path(temp)
        context = temp_root / "context"
        clean_repo, head = make_named_repo(context / "clean-worktree")
        actual_repo, _actual_head = make_named_repo(context / "chummer.run-services")
        compose = write_compose(temp_root, context, actual_repo.name)

        receipt = MODULE.verify(
            clean_repo,
            expected_head=head,
            compose_file=compose,
            compose_service="chummer-portal",
        )

    assert receipt["status"] == "fail"
    assert receipt["composeBuildSource"].endswith("chummer.run-services")
    assert any(finding["id"] == "compose_build_source_mismatch" for finding in receipt["findings"])


def test_compose_build_source_respects_environment_source_dir_override() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        temp_root = Path(temp)
        context = temp_root / "context"
        repo, head = make_named_repo(context / "clean-worktree")
        compose_path = temp_root / "docker-compose.public-edge.yml"
        compose_path.write_text(
            f"""
services:
  chummer-portal:
    build:
      context: ${{CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-{context}}}
      dockerfile: ${{CHUMMER_RUN_SERVICES_CONTEXT_DIR:-chummer.run-services}}/Chummer.Run.Api/Dockerfile
""".lstrip(),
            encoding="utf-8",
        )
        previous_context = os.environ.get("CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT")
        previous_source = os.environ.get("CHUMMER_RUN_SERVICES_CONTEXT_DIR")
        os.environ["CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT"] = str(context)
        os.environ["CHUMMER_RUN_SERVICES_CONTEXT_DIR"] = repo.name
        try:
            receipt = MODULE.verify(
                repo,
                expected_head=head,
                compose_file=compose_path,
                compose_service="chummer-portal",
            )
        finally:
            if previous_context is None:
                os.environ.pop("CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT", None)
            else:
                os.environ["CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT"] = previous_context
            if previous_source is None:
                os.environ.pop("CHUMMER_RUN_SERVICES_CONTEXT_DIR", None)
            else:
                os.environ["CHUMMER_RUN_SERVICES_CONTEXT_DIR"] = previous_source

    assert receipt["status"] == "pass"
    assert receipt["composeBuildSource"].endswith("clean-worktree")
    assert receipt["composeDockerfileSource"].endswith("clean-worktree")
    assert receipt["composeDockerfilePath"].endswith("clean-worktree/Chummer.Run.Api/Dockerfile")


def test_compose_build_source_requires_portal_service_worker_publish_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        temp_root = Path(temp)
        context = temp_root / "context"
        repo, head = make_named_repo(context / "clean-worktree")
        (repo / "Chummer.Run.Api" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        git(repo, "add", "Chummer.Run.Api/Dockerfile")
        git(repo, "commit", "-qm", "remove portal service worker guard")
        head = git(repo, "rev-parse", "HEAD")
        compose = write_compose(temp_root, context, repo.name)

        receipt = MODULE.verify(
            repo,
            expected_head=head,
            compose_file=compose,
            compose_service="chummer-portal",
        )

    assert receipt["status"] == "fail"
    assert any(finding["id"] == "missing_portal_service_worker_publish_guard" for finding in receipt["findings"])


def test_compose_build_source_rejects_split_additional_context_and_dockerfile_source() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        temp_root = Path(temp)
        context = temp_root / "context"
        repo, head = make_named_repo(context / "clean-worktree")
        make_named_repo(context / "chummer.run-services")
        compose_path = temp_root / "docker-compose.public-edge.yml"
        compose_path.write_text(
            f"""
services:
  chummer-portal:
    build:
      context: {context}
      dockerfile: chummer.run-services/Chummer.Run.Api/Dockerfile
      additional_contexts:
        run-services-source: ${{CHUMMER_RUN_SERVICES_SOURCE:-{context / "chummer.run-services"}}}
""".lstrip(),
            encoding="utf-8",
        )
        previous_source = os.environ.get("CHUMMER_RUN_SERVICES_SOURCE")
        os.environ["CHUMMER_RUN_SERVICES_SOURCE"] = str(repo)
        try:
            receipt = MODULE.verify(
                repo,
                expected_head=head,
                compose_file=compose_path,
                compose_service="chummer-portal",
            )
        finally:
            if previous_source is None:
                os.environ.pop("CHUMMER_RUN_SERVICES_SOURCE", None)
            else:
                os.environ["CHUMMER_RUN_SERVICES_SOURCE"] = previous_source

    assert receipt["status"] == "fail"
    assert receipt["composeBuildSource"].endswith("clean-worktree")
    assert receipt["composeDockerfileSource"].endswith("chummer.run-services")
    assert any(finding["id"] == "compose_dockerfile_source_mismatch" for finding in receipt["findings"])
    assert any(finding["id"] == "compose_split_source_mismatch" for finding in receipt["findings"])


def test_compose_build_source_accepts_matching_run_services_source_and_context_dir() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        temp_root = Path(temp)
        context = temp_root / "context"
        repo, head = make_named_repo(context / "clean-worktree")
        make_named_repo(context / "chummer.run-services")
        compose_path = temp_root / "docker-compose.public-edge.yml"
        compose_path.write_text(
            f"""
services:
  chummer-portal:
    build:
      context: {context}
      dockerfile: ${{CHUMMER_RUN_SERVICES_CONTEXT_DIR:-chummer.run-services}}/Chummer.Run.Api/Dockerfile
      additional_contexts:
        run-services-source: ${{CHUMMER_RUN_SERVICES_SOURCE:-{context / "chummer.run-services"}}}
""".lstrip(),
            encoding="utf-8",
        )
        previous_context_dir = os.environ.get("CHUMMER_RUN_SERVICES_CONTEXT_DIR")
        previous_source = os.environ.get("CHUMMER_RUN_SERVICES_SOURCE")
        os.environ["CHUMMER_RUN_SERVICES_CONTEXT_DIR"] = repo.name
        os.environ["CHUMMER_RUN_SERVICES_SOURCE"] = str(repo)
        try:
            receipt = MODULE.verify(
                repo,
                expected_head=head,
                compose_file=compose_path,
                compose_service="chummer-portal",
            )
        finally:
            if previous_context_dir is None:
                os.environ.pop("CHUMMER_RUN_SERVICES_CONTEXT_DIR", None)
            else:
                os.environ["CHUMMER_RUN_SERVICES_CONTEXT_DIR"] = previous_context_dir
            if previous_source is None:
                os.environ.pop("CHUMMER_RUN_SERVICES_SOURCE", None)
            else:
                os.environ["CHUMMER_RUN_SERVICES_SOURCE"] = previous_source

    assert receipt["status"] == "pass"
    assert receipt["composeBuildSource"].endswith("clean-worktree")
    assert receipt["composeDockerfileSource"].endswith("clean-worktree")


def test_public_edge_rebuild_scripts_call_source_gate() -> None:
    script_paths = [
        ROOT / "scripts" / "e2e-hub.sh",
        ROOT / "scripts" / "migration-loop.sh",
        ROOT / "scripts" / "ai" / "hub_closeout.sh",
    ]

    for script_path in script_paths:
        script = script_path.read_text(encoding="utf-8")
        assert "CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE" in script
        assert "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD" in script
        assert "CHUMMER_PUBLIC_EDGE_DEPLOY_REPO_ROOT" in script
        assert "scripts/verify_public_edge_deploy_source.py" in script
        assert "--expected-head" in script
        assert "--compose-file" in script
        assert "--compose-service" in script
        assert "chummer-run-identity" in script
        assert "chummer-portal" in script
        assert "docker compose" in script


def test_live_public_edge_deploy_wrapper_is_source_gated_and_image_pinned() -> None:
    script = (ROOT / "scripts" / "deploy_public_edge_portal.sh").read_text(encoding="utf-8")

    assert "scripts/verify_public_edge_deploy_source.py" in script
    assert "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD" in script
    assert "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM" in script
    assert "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT" in script
    assert "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS" in script
    assert "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_RETRY_DELAY_SECONDS" in script
    assert "CHUMMER_RUN_SERVICES_CONTEXT_DIR" in script
    assert "CHUMMER_RUN_SERVICES_SOURCE" in script
    assert "docker buildx build" in script
    assert "--build-context \"run-services-source=$SOURCE_ROOT\"" in script
    assert "--build-context \"fleet-media-factory-contracts=$FLEET_MEDIA_CONTRACTS\"" in script
    assert "--build-context \"design-product=$DESIGN_PRODUCT_ROOT\"" in script
    assert "docker image inspect \"$IMAGE_TAG\" --format '{{.Id}}'" in script
    assert "up -d --no-build --no-deps --force-recreate chummer-portal" in script
    assert "scripts/verify_public_edge_postdeploy_gate.py" in script
    assert "--expected-portal-image-id \"$image_id\"" in script
    assert "--require-downloads-status-playwright" in script
    assert "--require-mobile-pwa-viewport-playwright" in script
    assert "--require-frontdoor-navigation-playwright" in script
    assert "--playwright-artifact-dir \"$PLAYWRIGHT_ARTIFACT_DIR\"" in script
    assert "--mobile-pwa-viewport-artifact-dir" not in script
    assert "--frontdoor-navigation-artifact-dir" not in script
    assert "for ((attempt = 1; attempt <= POSTDEPLOY_ATTEMPTS; attempt++))" in script
    assert "sleep \"$POSTDEPLOY_RETRY_DELAY_SECONDS\"" in script


def test_release_ready_script_calls_public_edge_deploy_source_gate() -> None:
    script = (ROOT / "scripts" / "verify_chummer6_release_ready.sh").read_text(encoding="utf-8")

    assert "verify_public_edge_deploy_source()" in script
    assert "CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE" in script
    assert "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD" in script
    assert "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM" in script
    assert "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT" in script
    assert "CHUMMER_RUN_SERVICES_CONTEXT_DIR" in script
    assert "CHUMMER_RUN_SERVICES_SOURCE" in script
    assert "scripts/verify_public_edge_deploy_source.py" in script
    assert "--compose-file" in script
    assert "--compose-service chummer-portal" in script
    assert "--require-upstream" in script
    assert "branch --show-current" in script
    assert "--ignore-generated-proof-drift" in script
    assert "run_function_gate verify_public_edge_deploy_source" in script
    assert script.index("run_function_gate verify_public_edge_deploy_source") < script.index("run_hub_gate verify_windows_installer_visual_audit")


def test_downloads_runbook_documents_public_edge_source_and_browser_gates() -> None:
    runbook = (ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md").read_text(encoding="utf-8")

    assert "Public-edge source and browser proof gate" in runbook
    assert "scripts/deploy_public_edge_portal.sh" in runbook
    assert "Do not use raw `docker compose ... up -d --build chummer-portal` for release publication." in runbook
    assert "scripts/verify_public_edge_deploy_source.py" in runbook
    assert "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT" in runbook
    assert "CHUMMER_RUN_SERVICES_CONTEXT_DIR" in runbook
    assert "CHUMMER_RUN_SERVICES_SOURCE" in runbook
    assert "--compose-service chummer-portal" in runbook
    assert "--require-upstream" in runbook
    assert "scripts/verify_public_edge_postdeploy_gate.py" in runbook
    assert "--require-downloads-status-playwright" in runbook
    assert "--require-mobile-pwa-viewport-playwright" in runbook
    assert "--require-frontdoor-navigation-playwright" in runbook
    assert "docs/FLAGSHIP_HORIZONS_GATE.md" in runbook
    assert "flagshipHorizonsStatus=pass" in runbook
    assert "flagshipHorizonsBrowserProofCoverage=full" in runbook
    assert "shared_portal_root_worker" in runbook
    assert "--expected-portal-image-id" in runbook
    assert "--portal-container chummer6-hub-chummer-portal-1" in runbook
    assert "--portal-image-tag chummer-run-api:local" in runbook
    assert "scripts/restore_public_edge_portal_image.py" in runbook
    assert "PUBLIC_EDGE_PORTAL_IMAGE_RESTORE.generated.json" in runbook
    assert "docker compose up -d --no-build --no-deps --force-recreate" in runbook
    assert "--stability-window-seconds 120" in runbook
    assert "--require-all-browser-proofs" in runbook
    assert "public-edge-browser-proofs" in runbook
    assert "records Docker created time, tags, digests, and labels for any drifted image it replaces" in runbook
    assert "repairs bounded image drift during the optional stability window" in runbook
    assert "retries the runtime image guard plus the downloads/status, mobile viewport, and Open Chummer navigation browser proofs" in runbook


def test_flagship_horizons_gate_doc_names_the_release_horizons() -> None:
    doc = (ROOT / "docs" / "FLAGSHIP_HORIZONS_GATE.md").read_text(encoding="utf-8")

    assert "near_term_stabilization" in doc
    assert "mid_term_pwa_session_utility" in doc
    assert "long_term_living_world_expansion" in doc
    assert "flagshipHorizonsStatus=pass" in doc
    assert "flagshipHorizonsBrowserProofCoverage=full" in doc
    assert "/mobile/pwa/ledger.json" in doc
    assert "shared_portal_root_worker" in doc
