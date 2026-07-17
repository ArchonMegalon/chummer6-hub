from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_mobile_pwa_public_projection.py"


def load_module():
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("verify_mobile_pwa_public_projection", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_source_reports_default_off_profile_gated_zero_outbound_contract() -> None:
    module = load_module()

    payload = module.source_topology(ROOT)

    assert payload["status"] == "pass", payload["failures"]
    assert payload["topology"] == {
        "privatePlayProfileOnly": True,
        "publicProjectionDefaultOff": True,
        "edgeServiceKeyAbsent": True,
        "edgeUpstreamAbsent": True,
        "portalHasNoPlayDependency": True,
    }
    assert payload["gateway"]["zeroPublicPaths"] is True
    assert payload["gateway"]["noHttpClient"] is True
    assert payload["gateway"]["notInRequestPipeline"] is True
    assert payload["readiness"]["combinedBodyReturned"] is True
    assert payload["roleShell"]["playAppliesPrivateHeaders"] is True
    assert payload["roleShell"]["roleFieldsInModel"] is True
    assert all(payload["retiredEnvAbsent"].values())


def test_compose_topology_rejects_default_on_dependency_and_edge_credentials(tmp_path: Path) -> None:
    module = load_module()
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(
        """services:
  chummer-play-web:
    image: play
  chummer-portal:
    depends_on:
      chummer-play-web:
        condition: service_healthy
    environment:
      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:-true}"
      CHUMMER_PUBLIC_PLAY_PROXY_URL: http://chummer-play-web:8080/
      CHUMMER_PUBLIC_PLAY_PROXY_API_KEY: secret
""",
        encoding="utf-8",
    )
    failures: list[str] = []

    result = module.compose_topology(tmp_path, failures)

    assert not any(result.values())
    assert len(failures) == len(result)


def test_compose_topology_rejects_caller_interpolated_false_defaults(
    tmp_path: Path,
) -> None:
    module = load_module()
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(
        """services:
  chummer-play-web:
    profiles: ["play-private"]
    image: play
  chummer-portal:
    image: portal
    environment:
      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:-false}"
      CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"
""",
        encoding="utf-8",
    )
    failures: list[str] = []

    result = module.compose_topology(tmp_path, failures)

    assert result["publicProjectionDefaultOff"] is False
    assert all(
        result[key]
        for key in result
        if key != "publicProjectionDefaultOff"
    )
    assert failures == ["compose topology failed: publicProjectionDefaultOff"]


def test_compose_topology_rejects_play_dependency_after_environment(
    tmp_path: Path,
) -> None:
    module = load_module()
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(
        """services:
  chummer-play-web:
    profiles: ["play-private"]
    image: play
  chummer-portal:
    image: portal
    environment:
      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"
      CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"
    depends_on:
      chummer-play-web:
        condition: service_healthy
""",
        encoding="utf-8",
    )
    failures: list[str] = []

    result = module.compose_topology(tmp_path, failures)

    assert result["portalHasNoPlayDependency"] is False
    assert all(
        result[key]
        for key in result
        if key != "portalHasNoPlayDependency"
    )
    assert failures == ["compose topology failed: portalHasNoPlayDependency"]


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", payload=None, headers=None, *, url: str = "", history=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.headers = headers or {}
        self.url = url
        self.history = history or []

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, *, readiness_status: int = 200, readiness_ready: bool = True):
        self.readiness_status = readiness_status
        self.readiness_ready = readiness_ready

    def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
        if url.endswith("/api/ready"):
            return FakeResponse(
                self.readiness_status,
                payload={
                    "ready": self.readiness_ready,
                    "status": "ready" if self.readiness_ready else "not_ready",
                    "hub": {"ready": True, "status": "pass"},
                    "playProjection": {"status": "disabled", "ready": True, "enabled": False},
                    "deploymentIdentity": {
                        "ready": True,
                        "code": "overlay_identity_bound",
                        "sourceFingerprintSha256": "ab" * 32,
                    },
                },
            )
        values = parse_qs(urlsplit(url).query, keep_blank_values=True).get("role", [])
        normalized = values[0].strip().lower() if len(values) == 1 else ""
        role = (
            "gm"
            if normalized in {"gm", "game-master", "gamemaster"}
            else "observer"
            if normalized in {"observer", "spectator", "viewer"}
            else "player"
        )
        manifest = f"/manifest.{role}.webmanifest"
        title = "Chummer Observer" if role == "observer" else "Chummer GM" if role == "gm" else "Chummer Player"
        purpose = {
            "player": "Keep your runner ready at the table.",
            "gm": "Stage the table without exposing Game Master controls.",
            "observer": "Follow the table without gaining control.",
        }[role]
        capability = {
            "player": "Runner readiness",
            "gm": "Scene pacing",
            "observer": "Read-mostly return",
        }[role]
        target = f"/mobile/{role}"
        return FakeResponse(
            200,
            text=(
                f'<title>Install {title} Companion</title>'
                f'<link rel="manifest" href="{manifest}">'
                f'<main data-install-role="{role}" data-play-surface="install-only" '
                f'data-mobile-app-path="{target}">'
                f'<h1>{purpose}</h1><h2>{capability}</h2>'
                f'<a href="{target}">Open</a><svg data-mobile-app-inline-qr></svg>'
                f'<section data-role-privacy-warning="{role}"></section>'
                f'<section data-role-authority-warning="{role}"></section>'
                f'{title}</main>'
                '<script src="/mobile-install-shell.js"></script>'
            ),
            headers={
                "Cache-Control": "private, no-store",
                "Content-Security-Policy": "default-src 'none'; connect-src 'none'",
            },
            url=f"https://example.test{target}",
            history=[FakeResponse(302, headers={"Location": target}, url=url)],
        )


class PassingStaticVerifier:
    @staticmethod
    def verify_live(base_url: str, timeout: float):
        return {"status": "pass", "failures": [], "baseUrl": base_url, "timeout": timeout}


def test_live_contract_accepts_truthful_readiness_and_role_specific_install_shells(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    payload = module.live_projection("https://example.test", session=FakeSession())

    assert payload["status"] == "pass", payload["failures"]
    assert payload["readiness"]["payload"]["ready"] is True
    assert set(payload["roleShells"]) == {"player", "gm", "observer"}
    assert all(all(checks.values()) for checks in payload["roleShells"].values())
    assert set(payload["roleProbes"]) == {probe[0] for probe in module.ROLE_PROBES}
    assert all(
        all(result["checks"].values())
        for result in payload["roleProbes"].values()
    )
    assert payload["roleProbes"]["repeated_roles"]["expectedRole"] == "player"
    assert payload["roleProbes"]["unknown_role"]["expectedRole"] == "player"
    assert payload["roleProbes"]["mixed_case_alias"]["expectedRole"] == "gm"
    assert all(
        "?" not in location and "must-not-survive" not in location
        for result in payload["roleProbes"].values()
        for location in result["redirectLocations"]
    )


def test_live_contract_rejects_readiness_body_status_contradiction(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    payload = module.live_projection(
        "https://example.test",
        session=FakeSession(readiness_status=503, readiness_ready=True),
    )

    assert payload["status"] == "fail"
    assert "/api/ready: http200 failed" in payload["failures"]


def test_live_contract_rejects_missing_failed_or_incomplete_hub_truth(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class InvalidHubSession(FakeSession):
        def __init__(self, hub_payload, *, top_status="ready"):
            super().__init__()
            self.hub_payload = hub_payload
            self.top_status = top_status

        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                response._payload["status"] = self.top_status
                if self.hub_payload is None:
                    response._payload.pop("hub", None)
                else:
                    response._payload["hub"] = self.hub_payload
            return response

    cases = (
        (None, "ready", "hubObject"),
        ({"ready": False, "status": "fail"}, "ready", "hubReady"),
        ({"ready": True}, "ready", "hubStatus"),
        ({"ready": True, "status": "pass"}, "not_ready", "bodyStatus"),
    )
    for hub_payload, top_status, failed_check in cases:
        payload = module.live_projection(
            "https://example.test",
            session=InvalidHubSession(hub_payload, top_status=top_status),
        )
        assert payload["status"] == "fail"
        assert payload["readiness"]["checks"][failed_check] is False
        assert payload["readiness"]["checks"]["combinedConsistent"] is False


def test_live_contract_rejects_unbound_deployment_identity(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class UnboundIdentitySession(FakeSession):
        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                response._payload["deploymentIdentity"] = {
                    "ready": False,
                    "code": "overlay_identity_invalid",
                    "sourceFingerprintSha256": None,
                }
            return response

    payload = module.live_projection(
        "https://example.test",
        session=UnboundIdentitySession(),
    )

    assert payload["status"] == "fail"
    assert payload["readiness"]["checks"]["deploymentIdentityReady"] is False
    assert payload["readiness"]["checks"]["deploymentIdentityCode"] is False
    assert payload["readiness"]["checks"]["deploymentIdentityFingerprint"] is False


def test_live_contract_rejects_generic_or_noncanonical_role_shell(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class GenericShellSession(FakeSession):
        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                return response
            response.text = response.text.replace("Scene pacing", "Generic companion")
            response.url = f"{url}&secret=must-not-survive"
            response.history = []
            return response

    payload = module.live_projection("https://example.test", session=GenericShellSession())

    assert payload["status"] == "fail"
    assert "gm (/play?role=gm): capability failed" in payload["failures"]
    assert "gm (/play?role=gm): exactlyOneRedirect failed" in payload["failures"]
    assert "gm (/play?role=gm): cleanFinalUrl failed" in payload["failures"]


def test_live_contract_rejects_multi_hop_or_secret_bearing_redirect_history(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class LeakyHistorySession(FakeSession):
        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                return response
            response.history = [
                FakeResponse(302, headers={"Location": "/play?token=must-not-survive"}, url=url),
                FakeResponse(302, headers={"Location": f"/mobile/{response.url.rsplit('/', 1)[-1]}"}, url=url),
            ]
            return response

    payload = module.live_projection("https://example.test", session=LeakyHistorySession())

    assert payload["status"] == "fail"
    assert "gm_secret_extra (/play?role=gm&secret=must-not-survive&extra=1): exactlyOneRedirect failed" in payload["failures"]
    assert "gm_secret_extra (/play?role=gm&secret=must-not-survive&extra=1): cleanRedirectLocations failed" in payload["failures"]


def test_run_writes_v2_audit_without_gating_on_legacy_interactive_proof(monkeypatch) -> None:
    module = load_module()
    written: list[dict] = []
    monkeypatch.setattr(module, "source_topology", lambda source_root: {
        "contractName": module.CONTRACT_NAME,
        "mode": "source",
        "status": "pass",
        "failures": [],
    })
    monkeypatch.setattr(module, "write_audit_artifacts", lambda payload, markdown: written.append(payload))
    stdout = io.StringIO()

    with redirect_stdout(stdout):
        result = module.run(mobile_release_proof_path=Path("/stale/interactive-proof.json"))

    assert result == 0
    assert stdout.getvalue().strip() == "mobile_pwa_public_projection:ok"
    assert written[0]["legacyMobileReleaseProof"]["gating"] is False


def test_release_rehearsal_uses_only_the_canonical_mobile_pwa_browser_proof() -> None:
    rehearsal = (ROOT / "scripts" / "release_dress_rehearsal.sh").read_text(encoding="utf-8")
    matching_lines = [
        line.strip().removesuffix("\\").strip()
        for line in rehearsal.splitlines()
        if "mobile-pwa-public.spec.ts" in line
    ]

    assert matching_lines == ["tests/public/mobile-pwa-public.spec.ts"]
    assert (ROOT / "tests" / "public" / "mobile-pwa-public.spec.ts").is_file()
    assert not (ROOT / "mobile-pwa-public.spec.ts").exists()
