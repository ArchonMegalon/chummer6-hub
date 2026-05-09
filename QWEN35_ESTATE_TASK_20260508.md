# QWEN35 estate completion task

You are widening the current Codex mission from the narrow run-services audit lane to the broader Chummer6 estate completion scope defined by the Qwen3.5 bundle.

Source bundle:
- original zip: `/home/tibor/chummer_qwen35_execution_plan_20260508.zip`
- extracted bundle: `/docker/chummercomplete/_completion/chummer6_absolute_completion/_inputs/chummer_qwen35_execution_plan_20260508/`

You must load and use:
- `README.md`
- `QWEN35_MASTER_PROMPT.md`
- `QWEN35_EXECUTION_PLAN.md`
- `QWEN35_OPERATOR_RUNBOOK.md`
- `FALSE_CLAIM_RISK_SEED.md`
- `COMPLETION_WORKPACKAGES.yaml`
- `LTD_COMPLETION_MAP_SEED.yaml`
- `VERIFICATION_MATRIX.yaml`
- `TARGET_PUBLIC_ROUTES.yaml`

Local estate mapping:
- `Chummer6` product repo: `/docker/chummercomplete/Chummer6`
- `executive-assistant` equivalent: `/docker/EA`
- `fleet` repo: `/docker/fleet`
- `chummer6-hub` equivalent: `/docker/chummercomplete/chummer.run-services`
- `chummer6-core` equivalent: `/docker/chummercomplete/chummer-core-engine`
- `chummer6-ui` equivalent: `/docker/chummercomplete/chummer-presentation`
- `chummer6-design` equivalent: `/docker/chummercomplete/chummer-design`
- `chummer6-hub-registry` equivalent: `/docker/chummercomplete/chummer-hub-registry`
- `chummer6-mobile` equivalent: `/docker/chummercomplete/chummer-play`
- `chummer6-ui-kit` equivalent: `/docker/chummercomplete/chummer-ui-kit`
- `chummer6-media-factory` equivalent: `/docker/fleet/repos/chummer-media-factory`
- local `chummer5a` oracle if mounted: `/docker/chummer5a`
- local `Chummer4` oracle if mounted: `/docker/fleet/repos/chummer4`
- inspect additional relevant mounted repos under `/docker/chummercomplete` and `/docker/fleet/repos`, but the inventory must explicitly cover every mounted repo above

Completion is not based on your judgment.

Completion gate:
- run `python3 scripts/check_qwen35_estate_completion.py`
- only stop when `"closure_done": true`
- a valid close now requires:
  - the strict hub substance gate green
  - the full required artifact set present
  - `REPO_INVENTORY.yaml` covering the full mounted estate above with path, branch, HEAD SHA, and dirty-state fields, plus explicit unavailable entries for any required-but-unmounted repos
  - `REPO_INVENTORY.yaml` must reconcile exactly to live `git` state for every mounted repo: inventory branch, HEAD SHA, and dirty-state must match the real repo
  - each repo inventory entry must also declare whether it is `completion_managed`; inherited dirty repos that are not completion-managed must carry a baseline-state note
  - inherited dirty/non-synced repos must also record a `baseline_owner` so inherited estate state is explicit
  - each inventory entry must also carry a semantic role:
    - `product` for `Chummer6`
    - `executive-assistant` for `/docker/EA`
    - `fleet` for `/docker/fleet`
    - `hub`, `core`, `ui`, `design`, `hub-registry`, `mobile`, `ui-kit`, `media-factory`
    - `chummer5a-oracle`, `chummer4-oracle`
  - `ABSOLUTE_RELEASE_GATES.yaml`, `VERIFICATION_COMMANDS.md`, and `VERIFICATION_RESULTS.generated.json` covering every gate in `VERIFICATION_MATRIX.yaml`, including exact command-level receipts
  - `ABSOLUTE_RELEASE_GATES.yaml` pass entries must bind to current-run proof with live repo path, commit SHA, generation time, and real evidence files; blocked entries must include the active `run_id`, `repo_path`, `commit_sha` for mounted repos, `blocked_at` or `generated_at`, `blocker`, and exact `next_action`
  - every proof-bearing receipt must carry the active overwatch `run_id`, and every evidence artifact must itself reference that same `run_id`
  - `RUN_LEDGER.jsonl` must use structured entries for the active run with `run_id`, `pass`, `phase`, `action`, `status`, timestamp, and repo/proof context
  - write `REPO_INVENTORY.yaml`, `CANON_TRUTH_MAP.md`, `FALSE_COMPLETE_REGISTER.yaml`, and structured current-run `RUN_LEDGER.jsonl` rows first; do not spend the opening pass on repeated listings or broad rereads
  - `VERIFICATION_COMMANDS.md` must contain structured gate-local sections with `Owner repo:`, `Command:`, `Evidence:`, and `Expected proof:`; copied command substrings outside the owning gate section do not count
  - `E2E_RESULTS.generated.json` must cover the major user-journey gates with concrete journey/case receipts and evidence paths, not only generic pass markers
  - each E2E journey/case entry must itself bind to live repo state and carry its own pass state and evidence
  - E2E journey names must cover the canonical required journey set for each gate:
    - `gate-auth-account-install`: Google auth, email auth, install claim, account support history
    - `gate-feedback-loop`: feedback submission, support case, Product Governor packet, Fleet workpackage, release proof before notify
    - `gate-karma-forge`: Karma Forge submit, rules impact audit, package candidate, rollback
    - `gate-package-management`: package browser, vote/follow, install/update/revoke, package impact
    - `gate-mobile-pwa`: PWA install, offline/reconnect, auth, session resume, tap target/accessibility
  - `TARGET_PUBLIC_ROUTES.yaml` fully accounted for in `ABSOLUTE_RELEASE_GATES.yaml` with structured per-route owner/state/proof-or-blocker entries; no required route may disappear from truth mapping, verification, or explicit blockers
  - `FALSE_COMPLETE_REGISTER.yaml`, `FALSE_CLAIM_RISK.md`, and the LTD artifacts explicitly covering the seed risks from the QWEN35 bundle
  - `FALSE_COMPLETE_REGISTER.yaml` must normalize each seed risk into a structured record with `risk`, `owner`, `status`, `required_for_gates`, `proof_or_blocker`, and `next_action`
  - `FALSE_CLAIM_RISK.md` must contain one section per seeded claim with `Owner:`, `Current status:`, `Blocked public wording:`, `Allowed public wording:`, and `Required proof:`
  - `LTD_COMPLETION_MAP.md` must contain one section per seeded adapter with `Status:`, `Adapter owner:`, `Required receipt:`, and `Risk:`
  - `LTD_ADAPTER_IMPLEMENTATION_GUIDE.md` must contain one section per `use_now` and `pilot` adapter with `Verification:`, `Fallback:`, `Off-switch:`, and `Required receipt:`
  - `COMPLETION_BACKLOG.yaml`, `BUG_AND_GAP_REGISTER.yaml`, and `FINAL_NEXT_ACTIONS.yaml` all clear of unresolved `P0`/`P1` work unless the item is a precisely documented external blocker
  - mounted repos aligned to `completion/absolute-product-finish`
  - mounted repos clean, committed, and fully pushed/synced with their upstreams
  - proof receipts must be fresh for the current run: bind them to repo path, commit SHA, generation time, and real evidence files
  - proof receipts must bind to live repo state, not only generated inventory metadata
  - current-run proof means generated during the active overwatch run, not an older artifact that was merely recopied or touched
  - `Chummer6/DOWNLOAD.md` and `Chummer6/STATUS.md` must be directly covered in `PUBLIC_COPY_CHANGE_GUIDE.md`, `CANON_TRUTH_MAP.md`, and `BUG_AND_GAP_REGISTER.yaml` when risky public truth remains
  - `PUBLIC_COPY_CHANGE_GUIDE.md` must include a section for each of those docs with `Current claim:`, `Target claim:`, `Owner:`, and `Proof:`
  - `CANON_TRUTH_MAP.md` must include a section for each of those docs with `Source repo:`, `Current truth:`, and `Allowed public posture:`
  - `CANON_TRUTH_MAP.md` must also map each mounted estate role with `Owner repo:`, `Implementation repo:`, `Proof:`, and `Public posture:`
  - `BUG_AND_GAP_REGISTER.yaml` must use structured entries with owner, repo path, blocked gates, and next action
  - `ABSOLUTE_COMPLETION_VERDICT.md` must include `Readiness:`, `Claim posture:`, `Top blockers:`, and `Next slice:`

Non-negotiable rules:
- do not weaken the gate
- do not narrow scope back to run-services only
- keep the strict hub substance gate green while expanding outward
- do not mint unsupported pass receipts
- do not remove required routes just to make proofs pass
- do not count design prose, route existence, screenshots, or generated JSON alone as shipped truth
- if a repo or capability is not mounted locally, record that precisely in `_completion/chummer6_absolute_completion/REPO_INVENTORY.yaml`, `BUG_AND_GAP_REGISTER.yaml`, and `FINAL_NEXT_ACTIONS.yaml`, then continue on the mounted estate instead of stopping
- do not treat artifact presence, markdown length, or generic `status: pass` fields as sufficient proof
- do not leave any `VERIFICATION_MATRIX.yaml` gate uncovered in the completion artifacts, even if the underlying repo is unavailable; unavailable gates must be explicitly inventoried as blockers with owner repo, missing mount, and next action
- do not leave any `TARGET_PUBLIC_ROUTES.yaml` route unaccounted for; every route must be implemented, verified, or explicitly blocked with owner repo and next action
- do not skip `Chummer6` or `fleet`; if they are not materially relevant to a slice, record that reasoning in the truth map and gap audit
- do not treat the seed files as informational only; you must normalize them into the completion artifacts and closure logic
- do not use nonexistent `local-fs` MCP reads for local files; use shell file reads unless a configured MCP server is actually available
- unavailable repo records must be structured, not just mentioned by name: include `status`, `reason`, `next_action`, and `required_for_gates`
- branch policy is not optional: inventory divergence as a blocker until mounted repos are on `completion/absolute-product-finish`
- proof receipts must reference real existing files; invented proof paths do not count
- do not rely on stale receipts from older runs, branches, or commits; every proof must bind to the current repo inventory state
- do not rely on repo inventory alone for truth; inventory must match live `git` state and proof must bind to live repo state
- use the git baseline only to distinguish inherited dirt from new drift; final closure still requires clean and synced repos
- inherited dirty repos that are not part of the current completion slice must be explicitly documented; do not silently treat inherited dirt as completion failure or as resolved
- do not spend the early loop only on rereading inputs; after the initial estate scan, materialize all six Pass 0 artifacts immediately
- if Pass 0 is not semantically valid early, the supervisor will recycle your loop as non-progress

Required output root:
- `/docker/chummercomplete/_completion/chummer6_absolute_completion/`

Required outcome:
- produce the full artifact set named in `QWEN35_MASTER_PROMPT.md`
- close the highest-priority real blockers from the QWEN35 bundle across the mounted local estate
- keep public claims honest
- leave exact remaining external blockers only when they are truly unavailable from local code and proof work

Operating pattern:
1. inventory the mounted local estate and map it to the QWEN35 repo model
2. complete Pass 0 first: create `REPO_INVENTORY.yaml`, `CANON_TRUTH_MAP.md`, `OWNERSHIP_TRUTH_MAP.yaml`, `FALSE_COMPLETE_REGISTER.yaml`, `BUG_AND_GAP_REGISTER.yaml`, and an initial `ABSOLUTE_COMPLETION_VERDICT.md`
3. do not start any later slice until those Pass 0 artifacts exist and classify the whole mounted estate, including unavailable-but-required repos
4. keep the existing hub strict blockers honest
5. take the highest-value unresolved P0/P1 workpackage from `COMPLETION_WORKPACKAGES.yaml`
6. update canon first where needed, implement, verify, regenerate proof, update completion artifacts
7. repeat until the estate gate turns green

Required widened verification coverage:
- `gate-public-no-overclaim`
- `gate-auth-account-install`
- `gate-feedback-loop`
- `gate-karma-forge`
- `gate-package-management`
- `gate-chummer5a-human-parity`
- `gate-rulesets`
- `gate-mobile-pwa`
- `gate-ltd-adapters`

Required widened seed coverage:
- every claim class from `FALSE_CLAIM_RISK_SEED.md`
- every false-complete risk from the Pass 0 workpackage seed
- every adapter entry from `LTD_COMPLETION_MAP_SEED.yaml`
- every route in `TARGET_PUBLIC_ROUTES.yaml`
