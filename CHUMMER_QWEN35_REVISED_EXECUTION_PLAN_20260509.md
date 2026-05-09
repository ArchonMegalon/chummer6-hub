# Chummer6 Qwen3.5 Revised Execution & Implementation Plan

**Source package:** `/home/tibor/chummer_qwen35_revised_audit_20260509.zip`  
**Date discovered:** 2026-05-09  
**Scope:** Revised Qwen3.5 absolute completion packet with missed-gap addendum, delta workpackages, and verification gates (P0 priority).

## 1) Goals

1. Close all P0 gaps from the revised packet.
2. Implement design + code changes across owning repos with restart-safe proof artifacts.
3. Prove release-readiness only when all verification gates pass.

## 2) Execution order (phases)

### Phase A — Scope lock and baseline state

1. Read and extract the zip package from `/home/tibor/chummer_qwen35_revised_audit_20260509.zip`:
   - `MISSED_GAPS_ADDENDUM.md`
   - `QWEN35_MASTER_PROMPT_REVISED.md`
   - `DELTA_WORKPACKAGES.yaml`
   - `DELTA_VERIFICATION_MATRIX.yaml`
   - `OPERATOR_RUNBOOK_REVISED.md`
2. Create/confirm workspace artifacts:
   - `_completion/chummer6_absolute_completion/`
   - `RUN_STATE.yaml`, `RUN_LEDGER.jsonl`, `REPO_INVENTORY.yaml`
3. Confirm baseline status of all existing required proof outputs and capture current gate failures.

### Phase B — Design truth first

For each gap, update/author design artifacts in owning repo before implementation:

- `chummer6-design`: central manifest/feature copy, governance, package class model, mobile/PWA projection, canonical rules, media and LTD policies, claim-to-proof release gate.
- `chummer6-hub`: route projections and mirror-facing outputs.
- `chummer6-hub-registry`: package compatibility and registry model.
- `chummer6-mobile`: mobile/PWA entry projection requirements.
- `chummer6-media-factory`: boundary and provenance docs.
- `chummer6-core`: ruleset depth and seriousness boundaries.
- `executive-assistant`: LTD inventory/adaptation controls.
- `fleet`: run-state and release orchestration updates.

### Phase C — Implementation slices (vertical, blocking-order)

Implement in strict priority order, rerun gate immediately after each completed slice:

1. **DELTA-P0-001 Canon drift hardening** (Design + mirror republish + gate)
2. **DELTA-P0-002 Strict route + receipt proof split**
3. **DELTA-P0-005 Package browser + vote/follow routes + receipts**
4. **DELTA-P0-006 Mobile/PWA public route projection + PWA proofs + screenshots**
5. **DELTA-P0-007 Media Factory boundary and no media-as-truth proof**
6. **DELTA-P0-008 LTD inventory refresh + adapter verification**
7. **DELTA-P0-003 Public provider/LTD leak removal**
8. **DELTA-P0-004 Download authority correction**
9. **DELTA-P0-010 Canonical-domain handling for chummer6.run**
10. **DELTA-P0-011 Trivial ruleset-host depth gate**
11. **DELTA-P0-012 Exact Chummer5a human parity matrix**
12. **DELTA-P0-009 Claim-to-proof diff and false-claim remediation**

## 3) Owner map by package

- `DELTA-P0-001` → `chummer6-design`, `chummer6-hub`, `fleet`
- `DELTA-P0-002` → `chummer6-hub`
- `DELTA-P0-003` → `chummer6-design`, `chummer6-hub`, `Chummer6`
- `DELTA-P0-004` → `Chummer6`, `chummer6-design`, `chummer6-hub`
- `DELTA-P0-005` → `chummer6-design`, `chummer6-hub-registry`, `chummer6-hub`
- `DELTA-P0-006` → `chummer6-design`, `chummer6-hub`, `chummer6-mobile`
- `DELTA-P0-007` → `chummer6-media-factory`, `chummer6-design`
- `DELTA-P0-008` → `executive-assistant`, `chummer6-hub`, `fleet`, `chummer6-media-factory`
- `DELTA-P0-009` → `chummer6-design`, `Chummer6`, `chummer6-hub`, `fleet`
- `DELTA-P0-010` → `chummer6-hub`, `chummer6-design`
- `DELTA-P0-011` → `chummer6-core`, `chummer6-design`
- `DELTA-P0-012` → `chummer6-ui`, `chummer6-core`, `chummer6-design`

## 4) Verification gate checklist

Run in strict order after dependent artifacts are updated:

1. `python3 scripts/verify_canon_mirror_drift.py`
2. `python3 scripts/verify_public_routes_positive.py`
3. `python3 scripts/verify_receipt_routes_positive.py`
4. `python3 scripts/scan_public_forbidden_provider_ltd_names.py`
5. `python3 scripts/check_public_download_authority.py`
6. `python3 scripts/verify_package_routes_and_votes.py`
7. `python3 scripts/verify_mobile_pwa_public_projection.py`
8. `python3 scripts/capture_public_viewport_screenshots.py`
9. `python3 scripts/verify_media_factory_boundary.py`
10. `python3 scripts/refresh_ltd_inventory_and_verify_adapters.py`
11. `python3 scripts/generate_claim_to_proof_diff.py`
12. `python3 scripts/verify_domain_canonicalization.py`
13. `python3 scripts/audit_ruleset_provider_depth.py`
14. `python3 scripts/generate_chummer5a_human_parity_matrix.py`

## 5) Required output artifacts to produce

- `_completion/chummer6_absolute_completion/CANON_MIRROR_DRIFT_REPORT.md`
- `_completion/chummer6_absolute_completion/ROUTE_PROOF_STRICTNESS_REPORT.md`
- `_completion/chummer6_absolute_completion/PUBLIC_ROUTE_POSITIVE_PROOF.generated.json`
- `_completion/chummer6_absolute_completion/RECEIPT_ROUTE_POSITIVE_PROOF.generated.json`
- `_completion/chummer6_absolute_completion/PUBLIC_FORBIDDEN_STRING_SCAN.generated.json`
- `_completion/chummer6_absolute_completion/CLAIM_TO_PROOF_DIFF.generated.yaml`
- `_completion/chummer6_absolute_completion/DOMAIN_CANONICALIZATION_REPORT.md`
- `_completion/chummer6_absolute_completion/TRIVIAL_RULESET_HOST_AUDIT.md`
- `_completion/chummer6_absolute_completion/PACKAGE_ROUTE_AND_API_AUDIT.md`
- `_completion/chummer6_absolute_completion/MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.md`
- `_completion/chummer6_absolute_completion/MEDIA_FACTORY_BOUNDARY_AUDIT.md`
- `_completion/chummer6_absolute_completion/LTD_INVENTORY_REFRESH_REPORT.md`
- `_completion/chummer6_absolute_completion/LTD_VERIFICATION_STATUS.generated.yaml`
- `_completion/chummer6_absolute_completion/PUBLIC_SCREENSHOT_MANIFEST.generated.yaml`
- `_completion/chummer6_absolute_completion/CHUMMER5A_HUMAN_PARITY_MATRIX_RESULTS.generated.yaml`
- `_completion/chummer6_absolute_completion/ABSOLUTE_COMPLETION_VERDICT.md` (final state)

## 6) Completion criteria (hard stop)

Release-ready only when every P0 gate is green and no unresolved P0/P1 claim failures remain in:

- Route truth against central design and Hub mirror
- Positive route and receipt proof
- Public package browser/vote/follow flow
- Mobile/PWA projection
- Domain canonicalization (including `chummer6.run`)
- Forbidden provider/LTD public leaks
- Public download acquisition authority
- Media factory boundary
- LTD freshness + adapter verification
- Claim-to-proof diff with no unsupported top-priority claims
- Ruleset depth audit (no false-complete claims from trivial providers)
- Exact Chummer5a parity matrix rows/screenshot/receipts
