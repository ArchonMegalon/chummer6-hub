from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_external_distribution_mirror_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_external_distribution_mirror_proof", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, *, status: int, url: str, headers: dict[str, str]) -> None:
        self.status = status
        self.url = url
        self.headers = headers

    def read(self, _size: int = -1) -> bytes:
        return b""

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    def open(self, _request, timeout: float = 0.0) -> FakeResponse:
        return self._response


def test_verify_public_edge_publishes_public_safe_urls_for_loopback_probe(monkeypatch) -> None:
    module = load_module()
    response = FakeResponse(
        status=206,
        url="http://127.0.0.1:8091/downloads/files/chummer.zip",
        headers={"Content-Range": "bytes 0-0/123"},
    )
    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *_args, **_kwargs: FakeOpener(response))

    result = module.verify_public_edge(
        "http://127.0.0.1:8091",
        [{"id": "artifact", "file_name": "chummer.zip", "size": 123, "sha256": "abc", "access_class": ""}],
        8.0,
    )

    assert result["status"] == "pass"
    assert result["base_url"] == "https://chummer.run"
    assert result["artifacts"][0]["url"] == "https://chummer.run/downloads/files/chummer.zip"
    assert result["artifacts"][0]["final_url"] == "https://chummer.run/downloads/files/chummer.zip"
