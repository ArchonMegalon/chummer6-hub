#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime


PIPELINE_RETIRED = True
RETIREMENT_REASON = (
    "retired_faulty_chummer6_flagship_promo_pipeline:"
    "public_video_audio_quality_was_not_reliably_verified"
)
RETIRED_AT_UTC = "2026-06-22T12:55:00Z"


def retirement_receipt() -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "retired",
        "pipeline": "build_chummer6_flagship_promo",
        "retired_at_utc": RETIRED_AT_UTC,
        "reason": RETIREMENT_REASON,
        "replacement": "static_homepage_poster_until_human_reviewed_video_pipeline_exists",
    }


def main() -> int:
    print(json.dumps(retirement_receipt(), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
