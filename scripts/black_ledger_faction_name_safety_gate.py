#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_NAME_SAFETY.generated.json")


def main() -> int:
    result = subprocess.run(
        [
            "dotnet",
            "test",
            "Chummer.Run.Api.Tests/Chummer.Run.Api.Tests.csproj",
            "--filter",
            "FullyQualifiedName~FactionCharterBuilder_rejects_unsafe_public_names|FullyQualifiedName~FactionModerationLifecycle_blocks_public_projection_until_safe|FullyQualifiedName~FactionModerationLifecycle_can_approve_and_suppress_public_projection",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    payload = {
        "status": "pass" if result.returncode == 0 else "fail",
        "kind": "runtime_test",
        "command": "dotnet test Chummer.Run.Api.Tests/Chummer.Run.Api.Tests.csproj --filter FullyQualifiedName~FactionCharterBuilder_rejects_unsafe_public_names|FullyQualifiedName~FactionModerationLifecycle_blocks_public_projection_until_safe|FullyQualifiedName~FactionModerationLifecycle_can_approve_and_suppress_public_projection",
        "exit_code": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
