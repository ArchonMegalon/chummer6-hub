from __future__ import annotations

import pytest

from scripts.strict_json_contract import StrictJsonContractError, strict_json_object


def test_accepts_unambiguous_utf8_object() -> None:
    assert strict_json_object(b'{"nested":{"value":1}}', label="fixture") == {
        "nested": {"value": 1}
    }


@pytest.mark.parametrize(
    "payload",
    (
        b'{"status":"fail","status":"pass"}',
        b'{"nested":{"ready":false,"ready":true}}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'[]',
        b'\xef\xbb\xbf{}',
        b'\xff',
    ),
)
def test_rejects_ambiguous_or_non_object_contract(payload: bytes) -> None:
    with pytest.raises(StrictJsonContractError):
        strict_json_object(payload, label="fixture")
