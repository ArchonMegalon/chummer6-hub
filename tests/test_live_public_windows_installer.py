from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import tempfile
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_live_public_windows_installer.py"
HUB_CLOSEOUT = Path(__file__).resolve().parents[1] / "scripts" / "ai" / "hub_closeout.sh"
FINAL_GOLD_JANITOR = Path(__file__).resolve().parents[1] / "scripts" / "final_gold_janitor.py"
VERIFY_WINDOWS_INSTALLER_PAYLOADS = Path("/docker/chummercomplete/chummer-presentation/scripts/verify-windows-installer-payloads.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_live_public_windows_installer", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minimal_windows_exe() -> bytes:
    data = bytearray(4096)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = (0x8664).to_bytes(2, "little")
    data[0x86:0x88] = (3).to_bytes(2, "little")
    return bytes(data)


def _build_payload_zip() -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Chummer.Avalonia.exe", b"placeholder")
        archive.writestr("Samples/Legacy/Soma-Career.chum5", b"sample")
        archive.writestr("runtime/chummer-runtime.pack", b"0" * 8192)
    return buffer.getvalue()


def _build_installer_stub(payload_url: str, payload_sha256: str, payload_size: int) -> bytes:
    return _minimal_windows_exe() + (
        "\nCHUMMER6_BOOTSTRAP_METADATA\n"
        f"payloadDownloadUrl={payload_url}\n"
        f"payloadSha256={payload_sha256}\n"
        f"payloadSizeBytes={payload_size}\n"
    ).encode("utf-8")


class _LiveDownloadsHandler(BaseHTTPRequestHandler):
    payload_bytes = _build_payload_zip()
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    payload_file_name = "chummer-avalonia-win-x64-payload.zip"
    payload_url = ""
    installer_file_name = "chummer-avalonia-win-x64-installer.exe"
    installer_bytes = b""
    installer_sha256 = ""
    manifest_release_version = "run-test"
    sidecar_release_version = "run-test"

    def do_GET(self):  # noqa: N802
        if self.path == "/downloads/releases.json":
            manifest = {
                "version": self.manifest_release_version,
                "releaseVersion": self.manifest_release_version,
                "channel": "public_stable",
                "downloads": [
                    {
                        "id": "avalonia-win-x64-installer",
                        "artifactId": "avalonia-win-x64-installer",
                        "fileName": self.installer_file_name,
                        "url": f"{self.payload_url.rsplit('/', 1)[0]}/{self.installer_file_name}",
                        "sha256": self.installer_sha256,
                        "sizeBytes": len(self.installer_bytes),
                        "kind": "installer",
                        "platform": "Avalonia Desktop Windows X64 Installer",
                        "platformId": "windows-x64",
                        "installerMode": "bootstrap",
                        "payloadFileName": self.payload_file_name,
                        "payloadDownloadUrl": self.payload_url,
                        "payloadSha256": self.payload_sha256,
                        "payloadSizeBytes": len(self.payload_bytes),
                        "releaseVersion": self.manifest_release_version,
                    }
                ],
            }
            body = json.dumps(manifest).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == f"/downloads/files/{self.installer_file_name}":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(self.installer_bytes)))
            self.end_headers()
            self.wfile.write(self.installer_bytes)
            return

        if self.path == f"/downloads/files/{self.payload_file_name}":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(self.payload_bytes)))
            self.end_headers()
            self.wfile.write(self.payload_bytes)
            return

        if self.path == f"/downloads/files/{self.payload_file_name}.json":
            sidecar = {
                "contractName": "chummer6-ui.windows_bootstrap_payload",
                "fileName": self.payload_file_name,
                "downloadUrl": self.payload_url,
                "sha256": self.payload_sha256,
                "sizeBytes": len(self.payload_bytes),
                "installerFileName": self.installer_file_name,
                "releaseVersion": self.sidecar_release_version,
            }
            body = json.dumps(sidecar).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


class LivePublicWindowsInstallerTests(unittest.TestCase):
    def build_stub_verify_script(self) -> Path:
        temp_dir = tempfile.mkdtemp(prefix="chummer-live-public-windows-stub-")
        script_path = Path(temp_dir) / "verify-windows-installer-payloads.py"
        script_path.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "print('windows_installer_payload_gate:ok checked=1')\n"
            "raise SystemExit(0)\n",
            encoding="utf-8",
        )
        return script_path

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), _LiveDownloadsHandler)
        payload_base = f"http://127.0.0.1:{cls.server.server_port}/downloads/files"
        _LiveDownloadsHandler.payload_url = f"{payload_base}/{_LiveDownloadsHandler.payload_file_name}"
        _LiveDownloadsHandler.installer_bytes = _build_installer_stub(
            _LiveDownloadsHandler.payload_url,
            _LiveDownloadsHandler.payload_sha256,
            len(_LiveDownloadsHandler.payload_bytes),
        )
        _LiveDownloadsHandler.installer_sha256 = hashlib.sha256(_LiveDownloadsHandler.installer_bytes).hexdigest()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_live_public_windows_installer_verifier_passes_for_matching_fixture(self) -> None:
        module = load_module()
        output_path = Path(self.id().replace(".", "_")).with_suffix(".json")
        output_path = Path("/tmp") / output_path
        verify_script = self.build_stub_verify_script()
        verifier_sha256 = hashlib.sha256(verify_script.read_bytes()).hexdigest()
        payload = module.verify(
            self.base_url,
            verify_script,
            output_path=output_path,
            expected_verify_script_sha256=verifier_sha256,
        )

        self.assertEqual("pass", payload["status"])
        self.assertEqual("LIVE_PUBLIC_WINDOWS_INSTALLER_READY", payload["verdict"])
        self.assertEqual([], payload["failures"])
        self.assertTrue(output_path.is_file())
        written = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual("chummer.live_public_windows_installer", written["contract_name"])
        self.assertEqual("pass", written["status"])
        self.assertEqual(verifier_sha256, written["verify_script_sha256"])
        self.assertTrue(
            written["verify_script_path"].startswith(
                "external://windows-installer-payload-verifier/"
            )
        )
        self.assertEqual(1, written["checked_artifact_count"])
        self.assertIsInstance(written["artifact"], dict)
        self.assertEqual(1, len(payload["checked_artifacts"]))
        artifact = payload["checked_artifacts"][0]
        self.assertEqual(artifact, payload["artifact"])
        self.assertEqual(artifact, written["artifact"])
        self.assertEqual("pass", artifact["status"])
        self.assertEqual(_LiveDownloadsHandler.installer_sha256, artifact["installer_sha256"])
        self.assertEqual(_LiveDownloadsHandler.payload_sha256, artifact["payload_sha256"])

    def test_live_public_windows_installer_verifier_fails_when_sidecar_release_version_drifts(self) -> None:
        module = load_module()
        output_path = Path(self.id().replace(".", "_")).with_suffix(".json")
        module.OUTPUT_PATH = Path("/tmp") / output_path
        verify_script = self.build_stub_verify_script()
        verifier_sha256 = hashlib.sha256(verify_script.read_bytes()).hexdigest()
        original_manifest_release_version = _LiveDownloadsHandler.manifest_release_version
        original_release_version = _LiveDownloadsHandler.sidecar_release_version
        _LiveDownloadsHandler.manifest_release_version = "run-test"
        _LiveDownloadsHandler.sidecar_release_version = "run-drifted"
        try:
            payload = module.verify(
                self.base_url,
                verify_script,
                expected_verify_script_sha256=verifier_sha256,
            )
        finally:
            _LiveDownloadsHandler.manifest_release_version = original_manifest_release_version
            _LiveDownloadsHandler.sidecar_release_version = original_release_version

        self.assertEqual("fail", payload["status"])
        self.assertIn("avalonia-win-x64-installer: payload sidecar releaseVersion does not match", payload["failures"])

    def test_fetch_bytes_retries_timeout_then_succeeds(self) -> None:
        module = load_module()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.read.return_value = b"payload"

        with (
            mock.patch.object(module.urllib.request, "urlopen", side_effect=[TimeoutError("timed out"), response]) as urlopen,
            mock.patch.object(module.time, "sleep") as sleep,
        ):
            payload = module.fetch_bytes("https://example.test/download")

        self.assertEqual(b"payload", payload)
        self.assertEqual(2, urlopen.call_count)
        sleep.assert_called_once()

    def test_tracked_release_scripts_include_live_public_windows_installer_gate(self) -> None:
        hub_closeout = HUB_CLOSEOUT.read_text(encoding="utf-8")
        final_gold = FINAL_GOLD_JANITOR.read_text(encoding="utf-8")

        self.assertIn("verify_live_public_windows_installer.py --base-url \"$HUB_LIVE_BASE_URL\"", hub_closeout)
        self.assertIn('"live_public_windows_installer"', final_gold)
        self.assertIn('PUBLISHED_ROOT / "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json"', final_gold)
        self.assertIn('["python3", "scripts/verify_live_public_windows_installer.py", "--base-url", DEFAULT_BASE_URL]', final_gold)

    def test_default_verify_script_honors_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="chummer-live-public-windows-script-") as temp_dir:
            script_path = Path(temp_dir) / "verify-windows-installer-payloads.py"
            script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

            with mock.patch.dict(
                "os.environ",
                {"CHUMMER_WINDOWS_INSTALLER_PAYLOAD_VERIFY_SCRIPT": str(script_path)},
            ):
                module = load_module()

            self.assertEqual(script_path, module.DEFAULT_VERIFY_SCRIPT)

    def test_external_verifier_requires_matching_digest_before_execution(self) -> None:
        module = load_module()
        verify_script = self.build_stub_verify_script()

        with self.assertRaisesRegex(RuntimeError, "requires .*EXPECTED_SHA256"):
            module.authenticate_verifier(verify_script, None)
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            module.authenticate_verifier(verify_script, "0" * 64)

    def test_manifest_filenames_and_urls_are_confined(self) -> None:
        module = load_module()

        for unsafe_name in (
            "../installer.exe",
            "/tmp/installer.exe",
            "folder\\installer.exe",
            "payload.zip/child",
        ):
            with self.assertRaises(ValueError):
                module.confined_file_name(
                    unsafe_name,
                    label="fixture",
                    suffix=".exe",
                )

        with self.assertRaises(ValueError):
            module.confined_download_url(
                self.base_url,
                "https://attacker.invalid/downloads/files/installer.exe",
                file_name="installer.exe",
            )
        with self.assertRaises(ValueError):
            module.confined_download_url(
                self.base_url,
                "/downloads/files/installer.exe?token=leak",
                file_name="installer.exe",
            )

    def test_child_diagnostic_redacts_credentials_and_machine_paths(self) -> None:
        module = load_module()
        secret = "eyJhbGciOiJIUzI1NiJ9.abcdefghijk.secretpart"
        unlabeled = "eyJ1bmxhYmVsZWQ.abcdefghijklmnop.qrstuvwxyz12345"
        diagnostic = module.sanitize_child_diagnostic(
            f"Authorization: Bearer {secret}\n"
            "token=plain-secret\n"
            f"child emitted {unlabeled}\n"
            "/Users/operator/work/verifier.py failed"
        )

        self.assertNotIn(secret, diagnostic)
        self.assertNotIn(unlabeled, diagnostic)
        self.assertNotIn("plain-secret", diagnostic)
        self.assertNotIn("/Users/operator", diagnostic)
        self.assertIn("<redacted>", diagnostic)
        self.assertIn("<local-path>", diagnostic)


if __name__ == "__main__":
    unittest.main()
