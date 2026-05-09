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
- `fleet` repo: `/docker/fleet`
- `chummer6-hub` equivalent: `/docker/chummercomplete/chummer.run-services`
- `chummer6-core` equivalent: `/docker/chummercomplete/chummer-core-engine`
- `chummer6-ui` equivalent: `/docker/chummercomplete/chummer-presentation`
- `chummer6-design` equivalent: `/docker/chummercomplete/chummer-design`
- `chummer6-hub-registry` equivalent: `/docker/chummercomplete/chummer-hub-registry`
- `chummer6-mobile` equivalent: `/docker/chummercomplete/chummer-play`
- `chummer6-ui-kit` equivalent: `/docker/chummercomplete/chummer-ui-kit`
- `chummer6-media-factory` equivalent: `/docker/fleet/repos/chummer-media-factory`
- local `chummer5a` oracle if mounted: `/docker/chummercomplete/Chummer`
- local `Chummer4` oracle if mounted: `/docker/fleet/repos/chummer4`
- `executive-assistant`: not mounted locally right now; you must record it explicitly as unavailable in the inventory/gap/next-action artifacts instead of silently skipping it
- inspect additional relevant mounted repos under `/docker/chummercomplete` and `/docker/fleet/repos`, but the inventory must explicitly cover every mounted repo above

Completion is not based on your judgment.

Completion gate:
- run `python3 scripts/check_qwen35_estate_completion.py`
- only stop when `"closure_done": true`
- a valid close now requires:
  - the strict hub substance gate green
  - the full required artifact set present
  - `REPO_INVENTORY.yaml` covering the full mounted estate above with path, branch, HEAD SHA, and dirty-state fields, plus explicit unavailable entries for required-but-unmounted repos
  - `ABSOLUTE_RELEASE_GATES.yaml`, `VERIFICATION_COMMANDS.md`, and `VERIFICATION_RESULTS.generated.json` covering every gate in `VERIFICATION_MATRIX.yaml`, including exact command-level receipts
  - `E2E_RESULTS.generated.json` covering the major user-journey gates with concrete journey/case receipts and evidence paths, not only generic pass markers
  - `TARGET_PUBLIC_ROUTES.yaml` fully accounted for in `ABSOLUTE_RELEASE_GATES.yaml` with structured per-route owner/state/proof-or-blocker entries; no required route may disappear from truth mapping, verification, or explicit blockers
  - `FALSE_COMPLETE_REGISTER.yaml`, `FALSE_CLAIM_RISK.md`, and the LTD artifacts explicitly covering the seed risks from the QWEN35 bundle
  - `COMPLETION_BACKLOG.yaml`, `BUG_AND_GAP_REGISTER.yaml`, and `FINAL_NEXT_ACTIONS.yaml` all clear of unresolved `P0`/`P1` work unless the item is a precisely documented external blocker
  - mounted repos aligned to `completion/absolute-product-finish`

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
- overwatch loop: 1
- previous codexliz exit code: 0
- closure gate script: /docker/chummercomplete/chummer.run-services/scripts/check_qwen35_estate_completion.py
- pending ABS ids: strict_hub_substance, required_artifacts, pass0_control_plane, run_ledger, repo_inventory, branch_policy_alignment, unavailable_repo_documentation, OWNERSHIP_TRUTH_MAP.yaml, FALSE_COMPLETE_REGISTER.yaml, BUG_AND_GAP_REGISTER.yaml, COMPLETION_BACKLOG.yaml, ABSOLUTE_RELEASE_GATES.yaml, HORIZON_MVP_COMPLETION_MAP.yaml, E2E_RESULTS.generated.json, VERIFICATION_RESULTS.generated.json, release_gates_coverage, verification_commands_coverage, verification_results_gates, e2e_results_coverage, target_public_routes_coverage, false_complete_seed_coverage, false_claim_seed_coverage, ltd_seed_coverage, CANON_TRUTH_MAP.md, ABSOLUTE_GAP_AUDIT.md, MISSED_POTENTIAL_AUDIT.md, USER_WISH_DESIGN_EXPANSION.md, LTD_COMPLETION_MAP.md, ABSOLUTE_PRODUCT_COMPLETION_PLAN.md, FEEDBACK_TO_IMPLEMENTATION_LOOP.md, KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md, PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md, MOBILE_PWA_PRODUCT_SPEC.md, E2E_TEST_PLAN.md, VERIFICATION_COMMANDS.md, DEV_CHANGE_GUIDE.md, FALSE_CLAIM_RISK.md, PUBLIC_COPY_CHANGE_GUIDE.md, LTD_ADAPTER_IMPLEMENTATION_GUIDE.md, RELEASE_RUNBOOK.md, PREMIUM_FLAGSHIP_POLISH_REPORT.md, completion_verdict, completion_backlog_clear, final_next_actions, bug_register

Current pending checks:
- Strict hub substance gate: pending=live_route_proof, live_oauth_linking, portable_receipts_audit, sr5_closure (/docker/chummercomplete/chummer.run-services/scripts/check_absolute_audit_substance.py)
- Required completion artifacts: missing 30 artifacts: RUN_LEDGER.jsonl, REPO_INVENTORY.yaml, CANON_TRUTH_MAP.md, OWNERSHIP_TRUTH_MAP.yaml, ABSOLUTE_GAP_AUDIT.md, MISSED_POTENTIAL_AUDIT.md, USER_WISH_DESIGN_EXPANSION.md, LTD_COMPLETION_MAP.md, FALSE_COMPLETE_REGISTER.yaml, ABSOLUTE_PRODUCT_COMPLETION_PLAN.md, FEEDBACK_TO_IMPLEMENTATION_LOOP.md, KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md, PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md, MOBILE_PWA_PRODUCT_SPEC.md, HORIZON_MVP_COMPLETION_MAP.yaml, ABSOLUTE_RELEASE_GATES.yaml, COMPLETION_BACKLOG.yaml, E2E_TEST_PLAN.md, E2E_RESULTS.generated.json, VERIFICATION_COMMANDS.md, VERIFICATION_RESULTS.generated.json, BUG_AND_GAP_REGISTER.yaml, DEV_CHANGE_GUIDE.md, FALSE_CLAIM_RISK.md, PUBLIC_COPY_CHANGE_GUIDE.md, LTD_ADAPTER_IMPLEMENTATION_GUIDE.md, RELEASE_RUNBOOK.md, PREMIUM_FLAGSHIP_POLISH_REPORT.md, ABSOLUTE_COMPLETION_VERDICT.md, FINAL_NEXT_ACTIONS.yaml (/docker/chummercomplete/_completion/chummer6_absolute_completion)
- Pass 0 control-plane artifacts: missing 6 artifacts: REPO_INVENTORY.yaml, CANON_TRUTH_MAP.md, OWNERSHIP_TRUTH_MAP.yaml, FALSE_COMPLETE_REGISTER.yaml, BUG_AND_GAP_REGISTER.yaml, ABSOLUTE_COMPLETION_VERDICT.md (/docker/chummercomplete/_completion/chummer6_absolute_completion)
- Run ledger: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/RUN_LEDGER.jsonl)
- Repo inventory: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/REPO_INVENTORY.yaml)
- Branch policy alignment: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/REPO_INVENTORY.yaml)
- Unavailable repo documentation: missing=executive-assistant (/docker/chummercomplete/_completion/chummer6_absolute_completion)
- OWNERSHIP_TRUTH_MAP.yaml: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/OWNERSHIP_TRUTH_MAP.yaml)
- FALSE_COMPLETE_REGISTER.yaml: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/FALSE_COMPLETE_REGISTER.yaml)
- BUG_AND_GAP_REGISTER.yaml: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/BUG_AND_GAP_REGISTER.yaml)
- COMPLETION_BACKLOG.yaml: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/COMPLETION_BACKLOG.yaml)
- ABSOLUTE_RELEASE_GATES.yaml: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_RELEASE_GATES.yaml)
- HORIZON_MVP_COMPLETION_MAP.yaml: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/HORIZON_MVP_COMPLETION_MAP.yaml)
- E2E_RESULTS.generated.json: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/E2E_RESULTS.generated.json)
- VERIFICATION_RESULTS.generated.json: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/VERIFICATION_RESULTS.generated.json)
- Release gates coverage: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_RELEASE_GATES.yaml)
- Verification commands coverage: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/VERIFICATION_COMMANDS.md)
- Verification results gates: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/VERIFICATION_RESULTS.generated.json)
- E2E results coverage: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/E2E_RESULTS.generated.json)
- Target public routes coverage: ABSOLUTE_RELEASE_GATES.yaml missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_RELEASE_GATES.yaml)
- False-complete seed coverage: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/FALSE_COMPLETE_REGISTER.yaml)
- False-claim seed coverage: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/FALSE_CLAIM_RISK.md)
- LTD seed coverage: missing=LTD_COMPLETION_MAP.md, LTD_ADAPTER_IMPLEMENTATION_GUIDE.md (/docker/chummercomplete/_completion/chummer6_absolute_completion)
- CANON_TRUTH_MAP.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/CANON_TRUTH_MAP.md)
- ABSOLUTE_GAP_AUDIT.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_GAP_AUDIT.md)
- MISSED_POTENTIAL_AUDIT.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/MISSED_POTENTIAL_AUDIT.md)
- USER_WISH_DESIGN_EXPANSION.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/USER_WISH_DESIGN_EXPANSION.md)
- LTD_COMPLETION_MAP.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/LTD_COMPLETION_MAP.md)
- ABSOLUTE_PRODUCT_COMPLETION_PLAN.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_PRODUCT_COMPLETION_PLAN.md)
- FEEDBACK_TO_IMPLEMENTATION_LOOP.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/FEEDBACK_TO_IMPLEMENTATION_LOOP.md)
- KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md)
- PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md)
- MOBILE_PWA_PRODUCT_SPEC.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/MOBILE_PWA_PRODUCT_SPEC.md)
- E2E_TEST_PLAN.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/E2E_TEST_PLAN.md)
- VERIFICATION_COMMANDS.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/VERIFICATION_COMMANDS.md)
- DEV_CHANGE_GUIDE.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/DEV_CHANGE_GUIDE.md)
- FALSE_CLAIM_RISK.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/FALSE_CLAIM_RISK.md)
- PUBLIC_COPY_CHANGE_GUIDE.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/PUBLIC_COPY_CHANGE_GUIDE.md)
- LTD_ADAPTER_IMPLEMENTATION_GUIDE.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/LTD_ADAPTER_IMPLEMENTATION_GUIDE.md)
- RELEASE_RUNBOOK.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/RELEASE_RUNBOOK.md)
- PREMIUM_FLAGSHIP_POLISH_REPORT.md: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/PREMIUM_FLAGSHIP_POLISH_REPORT.md)
- Completion verdict: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/ABSOLUTE_COMPLETION_VERDICT.md)
- Completion backlog clear: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/COMPLETION_BACKLOG.yaml)
- Final next actions: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/FINAL_NEXT_ACTIONS.yaml)
- Bug and gap register: missing (/docker/chummercomplete/_completion/chummer6_absolute_completion/BUG_AND_GAP_REGISTER.yaml)

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
