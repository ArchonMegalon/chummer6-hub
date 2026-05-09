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

Supervisor context:
- overwatch loop: 0
- previous codexliz exit code: 0
- closure gate script: /docker/chummercomplete/chummer.run-services/scripts/check_qwen35_estate_completion.py
- pending ABS ids: run_ledger, release_gates_coverage, verification_results_gates, e2e_results_coverage, target_public_routes_coverage
- completion root: /docker/chummercomplete/_completion/chummer6_absolute_completion

Current pending checks:
- Run ledger: parsed_lines=36 current_run_lines=0 structured_lines=0 pass0_seen=False evidence_rows=0 total_lines=36 (/docker/chummercomplete/_completion/chummer6_absolute_completion/RUN_LEDGER.jsonl)
- Release gates coverage: present=9 missing=gate-auth-account-install, gate-chummer5a-human-parity, gate-feedback-loop, gate-karma-forge, gate-ltd-adapters, gate-mobile-pwa, gate-package-management, gate-public-no-overclaim, gate-rulesets (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_RELEASE_GATES.yaml)
- Verification results gates: gate_count=9 missing=gate-public-no-overclaim, gate-auth-account-install, gate-feedback-loop, gate-karma-forge, gate-package-management, gate-chummer5a-human-parity, gate-rulesets, gate-mobile-pwa, gate-ltd-adapters (/docker/chummercomplete/_completion/chummer6_absolute_completion/VERIFICATION_RESULTS.generated.json)
- E2E results coverage: required=5 missing=gate-auth-account-install, gate-feedback-loop, gate-karma-forge, gate-package-management, gate-mobile-pwa (/docker/chummercomplete/_completion/chummer6_absolute_completion/E2E_RESULTS.generated.json)
- Target public routes coverage: route_count=22 missing=/, /downloads, /status, /help, /contact, /feedback, /roadmap, /changelog, /packages, /packages/{packageId}, /packages/{packageId}/vote, /karma-forge, /karma-forge/submitted/{submissionId}, /mobile, /pwa, /artifacts, /login, /signup, /home, /account, /account/access, /account/support (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_RELEASE_GATES.yaml)

Execution plan:
# Qwen3.5:122B Codex Execution Plan — Chummer6 Absolute Completion

## Mission control

The completion drive must run as repeated bounded Codex passes. Each pass must:

1. Load `_completion/chummer6_absolute_completion/ABSOLUTE_COMPLETION_VERDICT.md` if present.
2. Pick the highest-priority unresolved `P0` or `P1` blocker from `BUG_AND_GAP_REGISTER.yaml`.
3. Confirm the owning repo and source-of-truth design file.
4. Update design canon first when needed.
5. Implement the slice in the owning repo.
6. Run the verification command for that blocker.
7. Regenerate proof receipts.
8. Update all completion artifacts.
9. Commit only focused changes.

Do not start a second major slice until the current slice has proof or a documented blocker.

## Recommended run pattern

### Pass 0 — Inventory and truth-map pass

Goal: establish current estate truth.

Outputs:
- `REPO_INVENTORY.yaml`
- `CANON_TRUTH_MAP.md`
- `OWNERSHIP_TRUTH_MAP.yaml`
- `FALSE_COMPLETE_REGISTER.yaml`
- `BUG_AND_GAP_REGISTER.yaml` initial
- `ABSOLUTE_COMPLETION_VERDICT.md` initial

Hard rule: this pass may not claim completion. It classifies.

### Pass 1 — Public/release/auth false-claim correction

Goal: make public and release claims honest before adding features.

Work:
- fix public copy that overclaims flagship/SR4/SR6/full parity
- ensure `chummer.run` route manifest names package/Karma/mobile paths only when implemented or preview-bounded
- ensure `Chummer6/DOWNLOAD.md` does not point users to GitHub releases as normal client download path if policy says `chummer.run` is official
- remove public provider/LTD names from feature registry/public pages
- mark SR4/SR6 as non-ready or implement gated serious proof

Verification:
- public forbidden-string scan
- route manifest validation
- docs/copy consistency scan
- YAML parse

### Pass 2 — Auth/account/install-link proof

Goal: make account and install linking safe enough for preview.

Work:
- Google OAuth/OIDC security posture
- email magic link
- secure cookies
- CSRF
- account merge/link conflict handling
- install claim/recover/update linkage
- account access/support pages

Verification:
- OAuth stub tests
- route proof
- cookie/header assertions
- CSRF tests
- install claim tests
- link conflict tests

### Pass 3 — Feedback/product-control loop

Goal: make user feedback actionable and closed-loop.

Work:
- public feedback/vote intake
- private support/bug/crash split
- EA request audit packet
- Product Governor decision packet
- Fleet workpackage generation
- release proof before closeout
- changelog/roadmap update
- transactional notification receipt

Verification:
- feedback E2E
- support E2E
- EA audit packet test
- Fleet workpackage materializer test
- notification receipt test
- privacy/no-public-leak test

### Pass 4 — Package management and public package browser

Goal: create install/rule package management layer.

Work:
- registry package model
- package compatibility matrix
- admin package manager
- public package browser
- vote/follow
- package install/update/revoke
- package provenance and impact receipts

Verification:
- registry package CRUD tests
- public route tests
- vote/follow tests
- compatibility tests
- revoke/rollback tests

### Pass 5 — Karma Forge MVP

Goal: turn house-rule/rule-pack requests into governed implementation.

Work:
- Karma Forge discovery form
- submission receipt
- vote/follow
- EA rules-impact audit
- compatibility/diff/provenance
- design petition
- Fleet workpackage
- package candidate
- release/revoke/changelog

Verification:
- Karma Forge E2E from submission to package candidate
- privacy tests
- compatibility gate tests
- rule-pack provenance tests

### Pass 6 — Desktop human parity closure

Goal: move from broad parity receipts to exact human parity.

Work:
- implement missing matrix rows
- generate per-element Chummer5a parity inventory
- capture required screenshots
- add runtime route receipts
- add veteran task-time proof
- close missing print/export/sheet/import utilities

Verification:
- human parity matrix gate
- screenshot capture
- `.chum5` import
- workflow output compare
- dual-head parity
- update/install/recovery smoke

### Pass 7 — Ruleset implementation honesty and depth

Goal: make SR5 serious and SR4/SR6 honest or implemented.

Work:
- classify SR4/SR5/SR6 by implementation depth
- add missing fixtures
- implement deterministic providers beyond trivial derive-stat
- improve codecs
- add explain receipts
- tie source/amend/package impact to ruleset runtime
- ensure UI cannot overclaim engine readiness

Verification:
- SR4/SR5/SR6 corpus tests
- mechanics tests
- import/export tests
- explain receipt tests
- runtime profile tests
- public false-claim scan

### Pass 8 — Mobile PWA

Goal: make mobile a real `chummer.run` product surface.

Work:
- PWA route under chummer.run
- manifest/service worker
- player/GM shell
- auth/account integration
- offline ledger
- reconnect/resume
- package compatibility
- mobile feedback/support
- mobile session utilities

Verification:
- PWA installability
- mobile screenshots
- offline/reconnect tests
- auth test
- tap-target/accessibility test

### Pass 9 — Media/artifact factory and LTD adapters

Goal: make artifacts and LTD leverage useful but bounded.

Work:
- media-factory README and boundary docs
- render jobs
- previews/manifests/source packets
- artifact shelf integration
- approved LTD adapters with receipts/fallbacks
- no public provider/LTD names

Verification:
- artifact render smoke
- provenance/audience/locale/retention tests
- adapter stub tests
- receipt tests
- no-secrets scan
- public forbidden-string scan

### Pass 10 — Release readiness and premium polish

Goal: release-grade package.

Work:
- run all standard verify scripts
- run E2E journeys
- release bundle/materialization smoke
- public phone/tablet/desktop proof
- polish report
- release runbook
- final verdict

Verification:
- all P0/P1 closed or explicitly non-release-scope
- `FINAL_NEXT_ACTIONS.yaml` contains no P0/P1
- `ABSOLUTE_COMPLETION_VERDICT.md` says at least `PREVIEW_READY`
- public claims match proof

Before you claim completion, rerun `python3 /docker/chummercomplete/chummer.run-services/scripts/check_qwen35_estate_completion.py` and verify `closure_done` is true.
