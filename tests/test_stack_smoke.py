from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE_CANDIDATES = [
    REPO_ROOT / "docker-compose.public-edge.yml",
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "docker-compose.yaml",
]
DEFAULT_COMPOSE_FILE = next((item for item in COMPOSE_FILE_CANDIDATES if item.exists()), None)


def detect_compose_base():
    if shutil.which("docker"):
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return ["docker", "compose"]
        except Exception:
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise RuntimeError("docker compose (plugin) or docker-compose is required")


COMPOSE_BASE = detect_compose_base()


def compose_env():
    env = os.environ.copy()
    env.setdefault("TUNNEL_TOKEN", "dummy")
    if "COMPOSE_FILE" not in env and DEFAULT_COMPOSE_FILE is not None:
        env["COMPOSE_FILE"] = str(DEFAULT_COMPOSE_FILE.relative_to(REPO_ROOT))
    return env


def run_compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*COMPOSE_BASE, *args],
        cwd=REPO_ROOT,
        env=compose_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class StackConfigSmokeTests(unittest.TestCase):
    def test_compose_config_validates(self):
        cp = run_compose("config", "-q")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)

    def test_compose_defines_services(self):
        cp = run_compose("config", "--services")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)
        services = {line.strip() for line in cp.stdout.splitlines() if line.strip()}
        self.assertTrue(services, "docker compose config --services returned no services")
        expected_services = {"overseerr_v2", "seerr_v2", "chummer-run-identity", "chummer-portal"}
        self.assertTrue(
            bool(expected_services & services),
            "expected one of the known stack services to be present",
        )

    def test_public_edge_services_restart_unless_stopped(self):
        public_edge_path = REPO_ROOT / "docker-compose.public-edge.yml"
        if not public_edge_path.exists():
            self.skipTest("docker-compose.public-edge.yml is not present for this repository slice")

        payload = yaml.safe_load(public_edge_path.read_text(encoding="utf-8")) or {}
        services = payload.get("services") or {}

        for service_name in ("chummer-run-identity", "chummer-portal"):
            service = services.get(service_name) or {}
            self.assertEqual(
                service.get("restart"),
                "unless-stopped",
                msg=f"{service_name} should restart automatically after host or docker daemon restarts",
            )

    def test_release_upload_bootstrap_stamps_receipts_with_artifact_identity(self):
        bootstrap_path = (
            REPO_ROOT
            / "Chummer.Run.Api"
            / "wwwroot"
            / "artifacts"
            / "mac-codex-release-pipeline"
            / "bootstrap.sh"
        )
        if not bootstrap_path.exists():
            self.skipTest("mac release-upload bootstrap template is not present for this repository slice")

        bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

        self.assertIn("stamp_startup_smoke_receipt_artifact_identity()", bootstrap_text)
        self.assertIn('payload["artifactFileName"] = artifact_name', bootstrap_text)
        self.assertIn('payload["artifactRelativePath"] = artifact_relative_path', bootstrap_text)
        self.assertIn('payload["artifactSha256"] = artifact_sha', bootstrap_text)
        self.assertIn('payload["artifactDigest"] = f"sha256:{artifact_sha}"', bootstrap_text)
        self.assertIn('payload["artifactDigestSource"] = "artifact_path"', bootstrap_text)
        self.assertIn('payload["artifactId"] = f"{head}-{rid}-{artifact_kind}"', bootstrap_text)
        self.assertIn("stamp_startup_smoke_receipt_artifact_identity \\", bootstrap_text)
        self.assertIn("sync_startup_smoke_receipts_for_local_verifier()", bootstrap_text)
        self.assertIn('sync_startup_smoke_receipts_for_local_verifier "$startup_smoke_dir" "$dist_dir"', bootstrap_text)
        self.assertIn("write_manifest_validation_audit_bundle()", bootstrap_text)
        self.assertIn("manifest-validation-audit.tar.gz", bootstrap_text)
        self.assertIn("If another Codex or operator is assisting, give them this directory or tarball first.", bootstrap_text)
        self.assertIn("write_manifest_validation_audit_bundle \\", bootstrap_text)
        self.assertIn("Audit bundle: ${dist_dir}/manifest-validation-audit", bootstrap_text)
        self.assertIn('sync_startup_smoke_receipts_for_local_verifier "$startup_smoke_dir" "$audit_dir"', bootstrap_text)
        self.assertIn("startup-smoke/startup-smoke-*.receipt.json copies in verifier-compatible layout", bootstrap_text)
        self.assertIn("exposes desktop files that are not present in manifest truth", bootstrap_text)
        self.assertIn("retrying materializer with startup-smoke filter disabled", bootstrap_text)
        self.assertIn("generating fallback manifests directly from dist files", bootstrap_text)
        self.assertIn('[[ -f "$canonical_manifest_path" ]]', bootstrap_text)
        self.assertIn('log "manifest fallback completed: $canonical_manifest_path and $compatibility_manifest_path"', bootstrap_text)
        self.assertNotIn('[[ -f "$canonical_output" ]]', bootstrap_text)
        self.assertIn("materializer.desktop_tuple_coverage(", bootstrap_text)
        self.assertIn("materializer.compatibility_payload(canonical_payload)", bootstrap_text)
        self.assertIn('compatibility_downloads = compatibility_payload.get("downloads")', bootstrap_text)
        self.assertIn('"compatibility_count": len(compatibility_downloads)', bootstrap_text)
        self.assertNotIn('"compatibility_count": len(downloads)', bootstrap_text)
        self.assertNotIn('"promotedInstallerTuples": [],', bootstrap_text)
        self.assertNotIn("mapfile -t", bootstrap_text)
        self.assertNotIn("readarray -t", bootstrap_text)

    def test_shared_http_release_uploader_avoids_bash4_only_array_builtins(self):
        uploader_path = REPO_ROOT.parent / "chummer-presentation" / "scripts" / "publish-download-bundle-http.sh"
        if not uploader_path.exists():
            self.skipTest("shared HTTP release uploader is not present for this repository slice")

        uploader_text = uploader_path.read_text(encoding="utf-8")

        self.assertIn('MANIFEST_PATH="${CHUMMER_RELEASE_UPLOAD_MANIFEST_PATH:-$BUNDLE_DIR/releases.json}"', uploader_text)
        self.assertNotIn("mapfile -t", uploader_text)
        self.assertNotIn("readarray -t", uploader_text)

    def test_verify_release_manifest_scripts_guard_empty_verify_args_for_macos_bash(self):
        script_paths = [
            REPO_ROOT / "scripts" / "verify-releases-manifest.sh",
            REPO_ROOT.parent / "chummer-presentation" / "scripts" / "verify-releases-manifest.sh",
        ]

        for script_path in script_paths:
            self.assertTrue(script_path.exists(), msg=f"missing expected manifest verifier: {script_path}")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn('if [[ "${#VERIFY_ARGS[@]}" -gt 0 ]]; then', script_text)
            self.assertIn('python3 "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" "$TARGET"', script_text)

    def test_release_publish_scripts_keep_macos_artifact_gate_behavior(self):
        run_services_gate_paths = {
            REPO_ROOT / "scripts" / "generate-releases-manifest.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle.sh",
        }
        script_paths = [
            REPO_ROOT / "scripts" / "generate-releases-manifest.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle-s3.sh",
            REPO_ROOT.parent / "chummer-presentation" / "scripts" / "generate-releases-manifest.sh",
        ]

        for script_path in script_paths:
            if not script_path.exists():
                self.skipTest(f"release publish script is not present for this repository slice: {script_path}")

            script_text = script_path.read_text(encoding="utf-8")
            if script_path in run_services_gate_paths:
                self.assertIn("CHUMMER_MACOS_PUBLIC_SHELF_ENABLED", script_text)
                self.assertIn("is_public_artifact()", script_text)

    def test_run_services_release_upload_scripts_avoid_bash4_array_builtins(self):
        script_paths = [
            REPO_ROOT / "scripts" / "generate-releases-manifest.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle.sh",
        ]

        for script_path in script_paths:
            self.assertTrue(script_path.exists(), msg=f"missing expected release script: {script_path}")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertNotIn("mapfile -t", script_text, msg=f"bash 4-only mapfile found in {script_path}")
            self.assertNotIn("readarray -t", script_text, msg=f"bash 4-only readarray found in {script_path}")

    def test_release_upload_bootstrap_can_repair_missing_status_and_verify_dummy_bundle(self):
        bootstrap_path = (
            REPO_ROOT
            / "Chummer.Run.Api"
            / "wwwroot"
            / "artifacts"
            / "mac-codex-release-pipeline"
            / "bootstrap.sh"
        )
        if not bootstrap_path.exists():
            self.skipTest("mac release-upload bootstrap template is not present for this repository slice")

        registry_root = REPO_ROOT.parent / "chummer-hub-registry"
        materializer = registry_root / "scripts" / "materialize_public_release_channel.py"
        verifier = registry_root / "scripts" / "verify_public_release_channel.py"
        if not materializer.exists() or not verifier.exists():
            self.skipTest("registry materializer/verifier scripts are not present for this repository slice")
        known_good_release_channel = REPO_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
        if not known_good_release_channel.exists():
            self.skipTest("known-good release-channel fixture is not present for this repository slice")

        with tempfile.TemporaryDirectory(prefix="chummer-bootstrap-e2e-") as temp_root:
            temp_path = Path(temp_root)
            files_dir = temp_path / "files"
            startup_smoke_dir = temp_path / "startup-smoke"
            files_dir.mkdir()
            startup_smoke_dir.mkdir()
            published_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

            artifact_path = files_dir / "chummer-avalonia-osx-arm64-installer.dmg"
            artifact_path.write_bytes(b"dummy mac installer payload\n")

            receipt_path = startup_smoke_dir / "startup-smoke-avalonia-osx-arm64.receipt.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "headId": "avalonia",
                        "version": "dummy-preview",
                        "releaseVersion": "dummy-preview",
                        "channelId": "preview",
                        "platform": "macos",
                        "arch": "arm64",
                        "rid": "osx-arm64",
                        "readyCheckpoint": "pre_ui_event_loop",
                        "hostClass": "macos-host",
                        "processPath": "/tmp/Chummer.Avalonia",
                        "framework": ".NET 10.0.0",
                        "operatingSystem": "macOS Sonoma",
                        "recordedAtUtc": published_at,
                        "startedAtUtc": published_at,
                        "completedAtUtc": published_at,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            release_fixture = json.loads(known_good_release_channel.read_text(encoding="utf-8"))
            proof_path = temp_path / "release-proof.json"

            source_bootstrap_script = (
                "source <(python3 - <<'PY'\n"
                "from pathlib import Path\n"
                f"path = Path({str(bootstrap_path)!r})\n"
                "lines = path.read_text(encoding='utf-8').splitlines()\n"
                "if lines and lines[-1].strip() == 'main \"$@\"':\n"
                "    lines = lines[:-1]\n"
                "print('\\n'.join(lines))\n"
                "PY\n"
                ")\n"
            )
            stamp_command = (
                "set -euo pipefail\n"
                + source_bootstrap_script
                + f"stamp_startup_smoke_receipt_artifact_identity {shlex.quote(str(receipt_path))} {shlex.quote(str(artifact_path))} avalonia osx-arm64\n"
            )
            stamp = subprocess.run(
                ["bash", "-lc", stamp_command],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(stamp.returncode, 0, msg=stamp.stderr or stamp.stdout)

            manifest_path = temp_path / "RELEASE_CHANNEL.generated.json"
            compat_path = temp_path / "releases.json"
            release_fixture["releaseProof"]["generatedAt"] = published_at
            release_fixture["releaseProof"]["generated_at"] = published_at
            ui_gate = release_fixture["releaseProof"].get("uiLocalizationReleaseGate") or {}
            if isinstance(ui_gate, dict):
                ui_gate["generatedAt"] = published_at
                ui_gate["generated_at"] = published_at
            with proof_path.open("w", encoding="utf-8") as handle:
                json.dump(release_fixture["releaseProof"], handle, indent=2)
                handle.write("\n")

            materialize = subprocess.run(
                [
                    "python3",
                    str(materializer),
                    "--downloads-dir",
                    str(files_dir),
                    "--startup-smoke-dir",
                    str(startup_smoke_dir),
                    "--channel",
                    "preview",
                    "--version",
                    "dummy-preview",
                    "--published-at",
                    published_at,
                    "--proof",
                    str(proof_path),
                    "--output",
                    str(manifest_path),
                    "--compat-output",
                    str(compat_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(materialize.returncode, 0, msg=materialize.stderr or materialize.stdout)

            verify = subprocess.run(
                ["python3", str(verifier), str(manifest_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, msg=verify.stderr or verify.stdout)

            stamped_receipt = receipt_path.read_text(encoding="utf-8")
            self.assertIn('"status": "pass"', stamped_receipt)

    def test_haproxy_backends_reference_defined_services(self):
        cp = run_compose("config", "--services")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)
        services = {line.strip() for line in cp.stdout.splitlines() if line.strip()}
        haproxy_path = REPO_ROOT / "haproxy.cfg"
        if not haproxy_path.exists():
            self.skipTest("haproxy.cfg is not present for this repository slice")

        haproxy_cfg = haproxy_path.read_text(encoding="utf-8")
        upstreams = set(re.findall(r"server\s+\S+\s+([A-Za-z0-9_.-]+):\d+", haproxy_cfg))
        missing = sorted(upstreams - services)

        self.assertEqual(
            missing,
            [],
            msg="haproxy backends missing in compose: " + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
