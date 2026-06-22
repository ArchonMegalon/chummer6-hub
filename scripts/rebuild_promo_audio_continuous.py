#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime


PIPELINE_RETIRED = True
RETIREMENT_REASON = (
    "retired_faulty_public_promo_audio_pipeline:"
    "codec_volume_notch_checks_allowed_bad_audio_to_publish"
)
RETIRED_AT_UTC = "2026-06-22T12:55:00Z"


def retirement_receipt() -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "retired",
        "pipeline": "rebuild_promo_audio_continuous",
        "retired_at_utc": RETIRED_AT_UTC,
        "reason": RETIREMENT_REASON,
        "replacement": "static_promo_poster_until_public_quality_audio_gate_exists",
    }


def main() -> int:
    print(json.dumps(retirement_receipt(), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
