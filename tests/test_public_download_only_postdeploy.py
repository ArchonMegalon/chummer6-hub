from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_public_download_only_postdeploy.py"
SPEC = importlib.util.spec_from_file_location("public_download_postdeploy", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
postdeploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(postdeploy)


class Response:
    def __init__(
        self,
        status: int,
        payload: dict[str, object],
        *,
        private: bool = False,
    ) -> None:
        self.status_code = status
        self._payload = payload
        self.headers = {"Content-Type": "application/json"}
        if private:
            self.headers = {
                "Content-Type": "application/problem+json; charset=utf-8",
                "Cache-Control": "private, no-store, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }

    def json(self) -> dict[str, object]:
        return self._payload


def responses() -> dict[str, Response]:
    serving = {
        "contractName": postdeploy.READINESS_CONTRACT,
        "ready": True,
        "status": "pass",
        "servingReady": True,
        "overallReady": False,
        "overallStatus": "fail",
        "publicationReady": False,
        "checks": [],
        "releaseShelf": {"servingReady": True},
    }
    result = {
        "/api/ready/public-downloads": Response(200, serving),
        **{
            path: Response(503, {"status": "fail"})
            for path in postdeploy.UNAVAILABLE_READINESS_PATHS
        },
        **{
            path: Response(503, postdeploy.PROBLEM, private=True)
            for path in postdeploy.PRIVATE_PATHS
        },
    }
    return result


def test_control_plane_accepts_serving_only_and_private_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _base, path, _timeout: fixture[path],
    )
    result = postdeploy.verify_control_plane("https://chummer.run", 1)
    assert result["privateBoundaryStatuses"] == {
        path: 503 for path in postdeploy.PRIVATE_PATHS
    }


def test_control_plane_rejects_global_readiness_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    fixture["/api/ready"] = Response(200, {"status": "pass"})
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _base, path, _timeout: fixture[path],
    )
    with pytest.raises(ValueError, match="unexpectedly claimed readiness"):
        postdeploy.verify_control_plane("https://chummer.run", 1)


def test_control_plane_rejects_private_problem_body_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    fixture["/api/v1/install-linking/me"] = Response(
        503,
        {**postdeploy.PROBLEM, "detail": "different"},
        private=True,
    )
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _base, path, _timeout: fixture[path],
    )
    with pytest.raises(ValueError, match="private 503 boundary"):
        postdeploy.verify_control_plane("https://chummer.run", 1)
