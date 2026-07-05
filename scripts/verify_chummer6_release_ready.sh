#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
run_services_root="${CHUMMER_RUN_SERVICES_ROOT:-$(cd "$script_dir/.." && pwd)}"
workspace_root="${CHUMMER_WORKSPACE_ROOT:-$(dirname "$run_services_root")}"
public_base="${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}"

public_edge_preflight_args=()
if [[ "${public_base%/}" == "https://chummer.run" ]]; then
  public_edge_preflight_args+=(--skip-preflight)
fi

failures=()

array_count() {
  local array_name="${1:-}"
  [[ -n "$array_name" ]] || {
    printf '0\n'
    return 0
  }

  local restore_nounset=0
  case "$-" in
    *u*)
      restore_nounset=1
      set +u
      ;;
  esac

  eval "set -- \"\${${array_name}[@]}\""
  local count="$#"

  if (( restore_nounset == 1 )); then
    set -u
  fi

  printf '%s\n' "$count"
}

record_failure() {
  local name="$1"
  local log="$2"
  failures+=("$name")
  echo "FAIL $name"
  cat "$log"
  echo
}

run_gate() {
  local name="$1"
  shift
  local log="/tmp/${name}.log"
  echo "RUN $name"
  if ! "$@" >"$log" 2>&1; then
    record_failure "$name" "$log"
  fi
}

run_hub_gate() {
  local name="$1"
  shift
  local log="/tmp/${name}.log"
  echo "RUN $name"
  if ! (cd "$run_services_root" && "$@") >"$log" 2>&1; then
    record_failure "$name" "$log"
  fi
}

run_function_gate() {
  local name="$1"
  shift
  local log="/tmp/${name}.log"
  echo "RUN $name"
  if ! "$@" >"$log" 2>&1; then
    record_failure "$name" "$log"
  fi
}

verify_public_projection() {
  cd "$run_services_root"
  python3 scripts/verify_next90_m120_hub_public_launch_health.py >/dev/null
  python3 scripts/verify_next90_m125_hub_public_signal_packets.py >/dev/null
  python3 scripts/verify_next90_m126_hub_hosted_proof_contracts.py >/dev/null
  python3 scripts/verify_next90_m144_hub_release_truth_alignment.py >/dev/null
  echo "public projection ok"
}

verify_public_ui_frame_integrity() {
  cd "$run_services_root"
  local base_url="${CHUMMER_PUBLIC_BASE_URL:-${BASE_URL:-https://chummer.run}}"
  local timeout_seconds="${CHUMMER_UI_FRAME_TIMEOUT_SECONDS:-900}"
  local test_timeout_ms="${CHUMMER_UI_FRAME_TEST_TIMEOUT_MS:-$((timeout_seconds * 1000 - 30000))}"
  if [ "$test_timeout_ms" -lt 600000 ]; then
    test_timeout_ms=600000
  fi

  local attempts="${CHUMMER_UI_FRAME_ATTEMPTS:-3}"
  local last_log
  last_log="$(mktemp)"
  trap "rm -f '$last_log'" RETURN

  for attempt in $(seq 1 "$attempts"); do
    if BASE_URL="$base_url" CHUMMER_UI_FRAME_TEST_TIMEOUT_MS="$test_timeout_ms" timeout --foreground "${timeout_seconds}s" npx playwright test tests/public/ui-frame-integrity.spec.ts --reporter=line >"$last_log" 2>&1; then
      cat "$last_log"
      return 0
    fi

    if ! rg -q "Target crashed|ERR_NETWORK_CHANGED|net::ERR_|chrome-error://chromewebdata|interrupted by another navigation|HTTP 50[0-9]|Timeout" "$last_log"; then
      cat "$last_log"
      return 1
    fi

    if [ "$attempt" = "$attempts" ]; then
      cat "$last_log"
      return 1
    fi

    echo "ui-frame-integrity attempt $attempt failed with transient browser/network error; retrying"
    cat "$last_log"
  done
}

verify_public_edge_deploy_source() {
  if [[ "${CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE:-1}" =~ ^(0|false|no|off)$ ]]; then
    echo "public edge deploy source gate skipped"
    return 0
  fi

  local gate_args=(
    --repo-root "$run_services_root"
    --compose-file "$run_services_root/docker-compose.public-edge.yml"
    --compose-service chummer-portal
    --ignore-generated-proof-drift
    --json
  )
  if [[ -n "${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-}" ]]; then
    gate_args+=(--expected-head "$CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD")
  fi
  local require_upstream="${CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM:-auto}"
  if [[ "$require_upstream" =~ ^(1|true|yes|on)$ ]]; then
    gate_args+=(--require-upstream)
  elif [[ "$require_upstream" == "auto" ]]; then
    local branch_name
    branch_name="$(git -C "$run_services_root" branch --show-current 2>/dev/null || true)"
    if [[ -n "$branch_name" ]] && git -C "$run_services_root" rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
      gate_args+=(--require-upstream)
    fi
  fi

  CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$workspace_root" \
  CHUMMER_RUN_SERVICES_CONTEXT_DIR="$(basename "$run_services_root")" \
  CHUMMER_RUN_SERVICES_SOURCE="$run_services_root" \
    python3 "$run_services_root/scripts/verify_public_edge_deploy_source.py" "${gate_args[@]}"
}

verify_no_public_internal_dependencies() {
  CHUMMER_RUN_SERVICES_ROOT="$run_services_root" CHUMMER_WORKSPACE_ROOT="$workspace_root" python3 - <<'PY'
import os
import pathlib

workspace = pathlib.Path(os.environ["CHUMMER_WORKSPACE_ROOT"])
run_services = pathlib.Path(os.environ["CHUMMER_RUN_SERVICES_ROOT"])
roots = [
    run_services / "Chummer.Run.Api" / "Views",
    run_services / "Chummer.Run.Api" / "wwwroot",
    workspace / "Chummer6",
]
deny = ["localhost", "127.0.0.1", "host.docker.internal"]
failed = []
for root in roots:
    if not root.exists():
        continue
    for path in root.rglob("*"):
        if path.is_dir() or "__pycache__" in path.parts or path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".mp4", ".webm", ".pdf", ".tar", ".gz", ".woff", ".woff2"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/tests/" in str(path).replace("\\", "/"):
            continue
        for token in deny:
            if token in text:
                failed.append(f"{path}: contains {token}")
if failed:
    print("\n".join(failed))
    raise SystemExit(1)
print("no public internal dependencies detected")
PY
}

verify_repo_release_posture() {
  python3 "$workspace_root/scripts/release/_release_gate_common.py" >/dev/null
  CHUMMER_RUN_SERVICES_ROOT="$run_services_root" CHUMMER_WORKSPACE_ROOT="$workspace_root" python3 - <<'PY'
import json
import os
from pathlib import Path

workspace = Path(os.environ["CHUMMER_WORKSPACE_ROOT"])
run_services = Path(os.environ["CHUMMER_RUN_SERVICES_ROOT"])
snapshot = json.loads((workspace / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT.generated.json").read_text())
build_id = str(snapshot.get("build_id") or "").lower()
checks = [
    workspace / "Chummer6" / "README.md",
    run_services / "README.md",
    workspace / "chummer-hub-registry" / "README.md",
    workspace / "chummer-core-engine" / "README.md",
    workspace / "chummer-ui-kit" / "README.md",
]
failed = []
for path in checks:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    if "public stable" in text and snapshot.get("release_label") != "public_stable":
        failed.append(f"{path}: claims public stable while snapshot says {snapshot.get('release_label')}")
    if "github releases" in text and "chummer.run" not in text:
        failed.append(f"{path}: implies github releases without chummer.run primary-path caveat")
    if "run-" in text and build_id and build_id not in text and path.name == "README.md":
        pass
if failed:
    print("\n".join(failed))
    raise SystemExit(1)
print("repo release posture ok")
PY
}

verify_windows_installer_visual_audit_gate() {
  cd "$run_services_root"
  if python3 scripts/verify_windows_installer_visual_audit.py; then
    return 0
  fi
  python3 scripts/materialize_windows_installer_visual_audit_intake_request.py >/dev/null 2>&1 || true
  python3 scripts/auto_import_windows_installer_gold_proof.py --wait-seconds 0 >/dev/null 2>&1 || true
  python3 scripts/verify_windows_installer_visual_audit_intake_request.py >/dev/null 2>&1 || true
  return 1
}

run_function_gate verify_public_edge_deploy_source verify_public_edge_deploy_source
run_function_gate verify_windows_installer_visual_audit verify_windows_installer_visual_audit_gate
if (( $(array_count failures) > 0 )) && [[ "${CHUMMER_RELEASE_READY_STOP_ON_PRECHECK_FAILURE:-1}" =~ ^(1|true|yes|on)$ ]]; then
  echo "NOT RELEASE READY"
  printf '%s\n' "${failures[@]}"
  exit 1
fi

run_gate verify_chummer6_desktop_gold bash "$workspace_root/scripts/release/verify_chummer6_desktop_gold.sh"
run_gate verify_design_release_policy bash "$workspace_root/scripts/release/verify_design_release_policy.sh"
run_gate verify_package_boundaries bash "$workspace_root/scripts/release/verify_package_boundaries.sh"
run_gate verify_core_release_receipts bash "$workspace_root/chummer-core-engine/scripts/release/verify_core_release_receipts.sh"
run_gate verify_release_channel bash "$workspace_root/chummer-hub-registry/scripts/release/verify_release_channel.sh"
run_function_gate verify_public_projection verify_public_projection
run_function_gate verify_public_ui_frame_integrity verify_public_ui_frame_integrity
run_gate verify_public_release_snapshot_truth bash "$workspace_root/scripts/release/verify_public_release_snapshot_truth.sh"
run_hub_gate verify_public_copy_leak_gate python3 scripts/verify_public_copy_leak_gate.py --base-url "$public_base"
run_hub_gate verify_live_surface_parity python3 scripts/verify_live_surface_parity.py --base-url "$public_base"
run_hub_gate verify_live_public_windows_installer python3 scripts/verify_live_public_windows_installer.py --base-url "$public_base"
run_hub_gate verify_flagship_product_readiness python3 scripts/verify_flagship_product_readiness_gate.py
run_hub_gate verify_public_edge_postdeploy_gate python3 scripts/verify_public_edge_postdeploy_gate.py --base-url "$public_base" "${public_edge_preflight_args[@]}" --require-downloads-status-playwright --require-mobile-pwa-viewport-playwright --require-frontdoor-navigation-playwright --output .codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json
run_hub_gate verify_public_portal_e2e env CHUMMER_PORTAL_BASE_URL="$public_base" CHUMMER_PORTAL_PUBLIC_HOST= CHUMMER_PORTAL_FORWARDED_PROTO= CHUMMER_PORTAL_REQUIRE_BLAZOR="${CHUMMER_PUBLIC_REQUIRE_BLAZOR:-0}" node scripts/e2e-portal.cjs
run_hub_gate verify_partizipate_runtime_fallback node scripts/verify_partizipate_runtime_fallback.cjs --base-url "$public_base"
run_hub_gate verify_participate_billing_honesty bash -lc "python3 scripts/materialize_participate_billing_honesty.py --completion-dir .codex-studio/published && python3 scripts/verify_participate_billing_honesty.py --completion-dir .codex-studio/published"
run_hub_gate verify_account_handoff_runtime_config python3 scripts/verify_account_handoff_runtime_config.py
run_hub_gate verify_design_quality_gate python3 scripts/materialize_design_quality_gate.py
run_gate verify_mobile_release_proof bash "$workspace_root/chummer-play/scripts/release/verify_mobile_release_proof.sh"
run_gate verify_ui_kit_package_release bash "$workspace_root/chummer-ui-kit/scripts/release/verify_ui_kit_package_release.sh"
run_gate verify_media_claims bash /docker/fleet/repos/chummer-media-factory/scripts/release/verify_media_claims.sh
run_gate verify_cross_repo_receipt_consistency bash "$workspace_root/scripts/release/verify_cross_repo_receipt_consistency.sh"
run_gate verify_proof_freshness bash "$workspace_root/scripts/release/verify_proof_freshness.sh"
run_function_gate verify_no_public_internal_dependencies verify_no_public_internal_dependencies
run_gate verify_public_truth_convergence bash "$workspace_root/scripts/release/verify_public_truth_convergence.sh"
run_gate verify_guide_convergence bash "$workspace_root/Chummer6/scripts/release/verify_guide_convergence.sh"
run_function_gate verify_repo_release_posture verify_repo_release_posture
run_gate verify_platform_matrix bash "$workspace_root/scripts/release/verify_platform_matrix.sh"
run_gate crawl_public_release_surfaces bash "$workspace_root/scripts/release/crawl_public_release_surfaces.sh"
run_hub_gate verify_teable_important_work_sync python3 scripts/sync_important_work_to_teable.py --sync
run_hub_gate verify_operator_release_dashboard python3 scripts/materialize_operator_release_dashboard.py --release-ready-self-check

if [[ "${CHUMMER_PUBLIC_REQUIRE_BLAZOR:-0}" =~ ^(1|true|yes|on)$ ]]; then
  run_gate verify_chummer6_blazor_gold bash "$workspace_root/scripts/release/verify_chummer6_blazor_gold.sh"
fi

if (( $(array_count failures) > 0 )); then
  echo "NOT RELEASE READY"
  printf '%s\n' "${failures[@]}"
  exit 1
fi

echo "RELEASE READY"
