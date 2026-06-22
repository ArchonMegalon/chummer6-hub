#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
UNMIXR_PROVIDER = "retired"
CLEAN_SPEECH_AUDIO_GROUPS: set[str] = set()
SILENCE_GATE_DBFS = -42.0
MAX_SILENCE_SECONDS = 0.70
MAX_EDGE_SILENCE_SECONDS = 0.30
MAX_START_SILENCE_SECONDS = MAX_EDGE_SILENCE_SECONDS
NARRATION_END_BEFORE_VIDEO_SECONDS = 0.0
MIN_TAIL_SILENCE_SECONDS = 0.0
MAX_TAIL_SILENCE_SECONDS = MAX_EDGE_SILENCE_SECONDS
VIDEO_FADE_OUT_SECONDS = 0.0
VIDEO_FADE_CONTRACT = "retired"
ALICE_VOICE_POLICY = "retired"
ALICE_CLEAN_AUDIO_STYLE = "retired"
PIPELINE_RETIRED = True
RETIREMENT_REASON = (
    "retired_faulty_public_video_audio_pipeline:"
    "automated_audio_quality_receipts_were_not_sufficient_for_public_promo_audio"
)
RETIRED_AT_UTC = "2026-06-22T12:55:00Z"


def retirement_receipt() -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "retired",
        "pipeline": "rebuild_public_video_audio_unmixr",
        "retired_at_utc": RETIRED_AT_UTC,
        "reason": RETIREMENT_REASON,
        "replacement": "fail_closed_static_or_human_reviewed_video_only_publication",
    }


def probe(_path: Path) -> dict[str, Any]:
    raise RuntimeError(RETIREMENT_REASON)


def audio_quality(_path: Path, *args: object, **kwargs: object) -> dict[str, object]:
    return {"status": "fail", "reasons": [RETIREMENT_REASON]}


def main() -> int:
    print(json.dumps(retirement_receipt(), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
