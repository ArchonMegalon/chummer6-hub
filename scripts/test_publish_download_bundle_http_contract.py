from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class PublishDownloadBundleHttpContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = Path(__file__).with_name("publish-download-bundle-http.sh").read_text(
            encoding="utf-8"
        )

    def run_join_url(
        self, base_url: str, candidate_url: str, canonical_origin: str
    ) -> subprocess.CompletedProcess[str]:
        marker = 'python3 - "$base_url" "$maybe_relative" "$canonical_origin" <<\'PY\'\n'
        start = self.script.index(marker) + len(marker)
        end = self.script.index("\nPY\n}", start)
        return subprocess.run(
            [
                "python3",
                "-c",
                self.script[start:end],
                base_url,
                candidate_url,
                canonical_origin,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_registry_canonicalizer_prefers_verifier_payload_api(self) -> None:
        script = self.script

        self.assertIn("if callable(helper):", script)
        self.assertIn("return helper(payload)", script)
        self.assertNotIn("artifact_bound_registry_names", script)

    def test_loopback_transport_is_strict_and_curl_scoped(self) -> None:
        script = self.script

        self.assertIn("CHUMMER_RELEASE_UPLOAD_LOOPBACK_RESOLVE", script)
        self.assertIn("or not address.is_loopback", script)
        self.assertIn('request_common+=(--resolve "$CURL_LOOPBACK_RESOLVE")', script)
        self.assertNotIn("--insecure", script)

    def test_created_session_resume_is_explicit_and_does_not_create_again(self) -> None:
        script = self.script

        self.assertIn("CHUMMER_RELEASE_UPLOAD_RESUME_CREATED_HANDOFF", script)
        self.assertIn("validate-resume-created", script)
        self.assertIn("if (( RESUME_CREATED_HANDOFF == 1 )); then", script)
        self.assertIn('SESSION_CANONICAL_ORIGIN="$PUBLIC_BASE_URL"', script)
        self.assertIn("canonical public origin must be an HTTPS origin-only URL", script)

    def test_deterministic_completion_rejection_is_durably_aborted(self) -> None:
        script = self.script

        self.assertIn("is_deterministic_pre_activation_rejection", script)
        self.assertIn('[[ "$REQUEST_HTTP_STATUS" == "400" ]]', script)
        self.assertIn("record_upload_attempt_state durably_aborted", script)
        self.assertIn(
            "https://chummer.run/problems/release-bundle/rejected",
            script,
        )

    def test_canonical_urls_translate_only_to_the_same_loopback_hostname(self) -> None:
        base = "http://chummer.run:8091/api/internal/releases/upload-sessions"
        path = "/api/internal/releases/upload-sessions/" + "f" * 32 + "/files"

        translated = self.run_join_url(
            base, f"https://chummer.run{path}", "https://chummer.run"
        )
        self.assertEqual(0, translated.returncode, translated.stderr)
        self.assertEqual(f"http://chummer.run:8091{path}", translated.stdout.strip())

        escaped_host = self.run_join_url(
            base, f"https://attacker.invalid{path}", "https://chummer.run"
        )
        self.assertNotEqual(0, escaped_host.returncode)

        escaped_path = self.run_join_url(
            base,
            "https://chummer.run/api/internal/releases/upload-sessions/%2e%2e/files",
            "https://chummer.run",
        )
        self.assertNotEqual(0, escaped_path.returncode)


if __name__ == "__main__":
    unittest.main()
