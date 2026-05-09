# Absolute audit codexliz task

You are executing the remaining work from:
- [ABSOLUTE_AUDIT_EXECUTION_PLAN_20260508.md](/docker/chummercomplete/chummer.run-services/ABSOLUTE_AUDIT_EXECUTION_PLAN_20260508.md)

Completion is not based on your judgment.

Completion gate:
- run `python3 scripts/check_absolute_audit_closure.py`
- only stop when `"closure_done": true`

Operating rules:
- work the highest-priority pending checks first
- if one lane is blocked, implement the next dependency or close the next pending lane instead of stopping
- do not treat partial progress as completion
- do not mint synthetic `status: pass` receipts just to satisfy the closure checker
- every new proof receipt must be backed by a real probe, script run, or existing evidence file that the receipt cites concretely
- unsupported self-authored proof JSON does not count as completion and will be rejected by the closure gate
- for SR4 and SR6, the plan explicitly allows either acceptance proof or explicit claim retirement
- for SR5, close the audit either by real acceptance proof or by an explicit claim-boundary receipt if that is the chosen product posture
- before every final answer attempt, rerun `python3 scripts/check_absolute_audit_closure.py`

Priority order:
1. live `chummer.run` proof and canonical-domain closure
2. live Google OAuth/account-linking proof
3. live support/contact proof
4. fresh desktop execution proof
5. portable receipts audit
6. SR5 closure
7. SR4 closure
8. SR6 closure

Relevant repos:
- `/docker/chummercomplete/chummer.run-services`
- `/docker/chummercomplete/chummer-presentation`
- `/docker/chummercomplete/chummer-core-engine`
- `/docker/chummercomplete/chummer-design`
- `/docker/fleet/repos/chummer-media-factory`
- `/home/tibor` if you need the source audit zip

Supervisor context:
- overwatch loop: 0
- previous codexliz exit code: 0
- closure gate script: /docker/chummercomplete/chummer.run-services/scripts/check_absolute_audit_closure.py
- pending ABS ids: ABS-004, ABS-016
- completion root: /docker/chummercomplete/_completion/chummer6_absolute_completion

Current pending checks:
- Live public route proof: route_count=63 failed_count=1 (/docker/chummercomplete/chummer.run-services/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json)

Execution plan:
# Absolute audit execution plan

Scope: close everything still open from `/home/tibor/chummer_absolute_audit_20260508_artifacts.zip` after the repo-local proof and claim-discipline work completed on `2026-05-08`.

## Current state

Closed or materially remediated locally already:
- `ABS-007` OIDC nonce and ID-token validation now exists in code.
- `ABS-008` production fail-closed behavior is implemented locally.
- `ABS-009` provider-linking docs now match controller behavior.
- `ABS-010` SR4/SR6 docs are aligned to the current baseline host code.
- `ABS-011` official download-source wording is aligned.
- `ABS-013` media-factory front door is documented as presentation-only.
- `ABS-014` local phone-layout proof now exists.
- `ABS-015` public-copy provider/LTD scan now exists and passes.

Useful receipts already in hand:
- [PUBLIC_CLAIM_SCAN.generated.json](/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_CLAIM_SCAN.generated.json)
- [PHONE_LAYOUT_PROOF.local.generated.json](/docker/chummercomplete/chummer.run-services/.codex-studio/published/PHONE_LAYOUT_PROOF.local.generated.json)
- [SUPPORT_CASE_FLOW_PROOF.local.generated.json](/docker/chummercomplete/chummer.run-services/.codex-studio/published/SUPPORT_CASE_FLOW_PROOF.local.generated.json)
- [CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json](/docker/chummercomplete/chummer-presentation/.codex-studio/published/CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json)
- [SR4_RULESET_DEPTH.generated.json](/docker/chummercomplete/chummer-core-engine/.codex-studio/published/SR4_RULESET_DEPTH.generated.json)
- [SR5_RULESET_DEPTH.generated.json](/docker/chummercomplete/chummer-core-engine/.codex-studio/published/SR5_RULESET_DEPTH.generated.json)
- [SR6_RULESET_DEPTH.generated.json](/docker/chummercomplete/chummer-core-engine/.codex-studio/published/SR6_RULESET_DEPTH.generated.json)

Still open after this local pass:
- `ABS-001` Full Chummer5A parity is still not proven by a fresh same-run desktop execution pack.
- `ABS-002` SR6 is not a serious implementation.
- `ABS-003` SR4 is not a serious implementation.
- `ABS-004` Live public site and account routes are not fully re-proven on deployed `chummer.run`.
- `ABS-005` OAuth/account linking is still not live end-to-end proven.
- `ABS-006` SR5 implementation depth is still not production-grade.
- `ABS-012` published receipts still need a systematic absolute-path portability cleanup.
- `ABS-016` canonical-domain posture needs a formal closure path for `chummer.run` as the only real public domain.
- `ABS-017` support/contact closure is proven locally but not yet re-proven on live.
- `ABS-018` desktop parity receipts still need fresh execution proof, not only derivative receipts over existing JSON.

## Non-negotiable claim posture until closure

Allowed now:
- Chummer5A parity evidence is strong locally.
- Public route, phone-layout, and support-flow proofs exist locally.
- SR5 is the strongest ruleset lane.
- SR4 and SR6 are bounded baseline hosts, not serious implementations.

Not allowed yet:
- full release-grade readiness
- live OAuth/account-linking proven
- live hosted public-route closure
- serious SR4
- serious SR6
- production-grade SR5

## Execution order

1. Hosted proof and domain closure
2. Fresh desktop execution closure
3. Proof portability cleanup
4. SR5 production-depth work
5. SR4 decision and implementation lane
6. SR6 decision and implementation lane

This order matters. The first three streams close claim and proof debt. The last three streams close capability debt.

## Workstream 1: hosted proof and domain closure

Audit items:
- `ABS-004`
- `ABS-005`
- `ABS-016`
- `ABS-017`

Repos:
- `chummer.run-services`
- deployment/infra surface that serves `https://chummer.run`

Goal:
- prove the real deployed host, real account gates, and real support/contact routes on `https://chummer.run`
- formally retire any residual `chummer6.run` expectation and make `chummer.run` the only canonical public domain

Steps:
1. Search all public docs, manifests, published receipts, and generated copy for `chummer6.run`.
2. Remove residual `chummer6.run` references or replace them with explicit `chummer.run`-only policy.
3. Publish a small canonical-domain receipt, for example `CANONICAL_DOMAIN_POLICY.generated.json`, that states:
   - `canonical_public_domain: chummer.run`
   - `deprecated_domains: []`
   - `chummer6.run: not_used`
4. Deploy the current `chummer.run-services` build to the real hosted environment.
5. Re-run the live route verifier against `https://chummer.run`.
6. Publish a fresh green [CHUMMER_PUBLIC_ROUTE_PROOF.generated.json](/docker/chummercomplete/chummer.run-services/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json) from the deployed host.
7. Add a live support proof runner that hits:
   - `/contact`
   - `/help`
   - `/faq`
   - `/home/access`
   - `/account/support`
8. Publish `SUPPORT_CASE_FLOW_PROOF.generated.json` for the live host, separate from the local-only receipt.
9. Add a live Google OAuth/account-linking verifier with a real test account and real Google credentials.
10. Publish `GOOGLE_OAUTH_LINKING_PROOF.generated.json`.

Live OAuth test cases:
1. anonymous user starts on `/login`
2. Google handoff completes and lands on signed-in state
3. existing account can link Google
4. linked account can sign back in with Google
5. linked-provider state is visible on `/account/access`
6. logout/login preserves the expected linked state
7. any unsupported unlink path fails with explicit bounded guidance rather than silent drift

Exit criteria:
- live route proof is green
- live support proof is green
- live Google OAuth/linking proof is green
- canonical-domain policy receipt exists and no public artifact expects `chummer6.run`

## Workstream 2: fresh desktop execution closure

Audit items:
- `ABS-001`
- `ABS-018`

Repos:
- `chummer-presentation`
- `chummer6-ui`
- `chummer-design`

Goal:
- replace “existing committed JSON plus derived proof” with a fresh same-run desktop execution pack

Steps:
1. Prepare a reproducible desktop proof environment for the current build.
2. Run the flagship desktop workflow execution suite again.
3. Re-run the Chummer5A screenshot review gate.
4. Re-run the visual familiarity gate.
5. Re-run the desktop workflow execution gate.
6. Re-run the ultimate and absolute parity testers in the same execution window.
7. Regenerate [CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json](/docker/chummercomplete/chummer-presentation/.codex-studio/published/CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json) so it references the fresh same-run receipts.
8. Publish one explicit “fresh execution” receipt, for example `CHUMMER5A_DESKTOP_EXECUTION_PROOF.generated.json`, that lists:
   - run timestamp
   - fixture corpus version
   - screenshot-review receipt
   - workflow-execution receipt
   - visual-familiarity receipt
   - final parity receipts

Exit criteria:
- all underlying desktop receipts are regenerated in the same execution window
- the human-parity matrix proof references those new receipts
- no remaining audit conclusion depends only on stale committed JSON

## Workstream 3: proof portability cleanup

Audit item:
- `ABS-012`

Repos:
- `chummer.run-services`
- `chummer-presentation`
- `chummer-core-engine`
- any other repo that publishes audit receipts

Goal:
- make published proof artifacts portable across machines and worktrees

Steps:
1. Define the receipt-path policy:
   - use repo-relative paths inside each repo whenever possible
   - allow local-only hostnames or ports only in explicitly local receipts
   - never require `/docker/...` or `/home/...` absolute filesystem paths in portable published proofs
2. Build a verifier, for example `verify_generated_receipts_portable.py`, that scans published JSON/MD/YAML for absolute local filesystem paths.
3. Enumerate the current offenders by repo.
4. Patch generators first, not generated outputs by hand.
5. Re-emit the affected receipts.
6. Publish `PORTABLE_RECEIPTS_AUDIT.generated.json`.

Exit criteria:
- portability verifier passes across the targeted published artifacts
- no proof required for audit closure depends on a machine-specific absolute path

## Workstream 4: SR5 production-depth lane

Audit item:
- `ABS-006`

Repo:
- `chummer-core-engine`

Goal:
- move SR5 from “strongest lane but partial” to “production-grade enough to claim serious implementation”

Required capability areas:
1. character-creation economics and validation
2. inventory, legality, and availability logic
3. qualities, augment, magic, and resonance flows
4. explainable rule execution beyond `derive.stat`
5. import/export and round-trip fidelity
6. acceptance-proof coverage over the supported SR5 workflow set

Execution steps:
1. Convert [SR5_RULESET_DEPTH.generated.json](/docker/chummercomplete/chummer-core-engine/.codex-studio/published/SR5_RULESET_DEPTH.generated.json) from a descriptive baseline receipt into an acceptance receipt with explicit required capability thresholds.
2. Inventory missing SR5 rule packs and workflow surfaces from [SR5_EXECUTION_MATRIX.md](/docker/chummercomplete/chummer-core-engine/docs/SR5_EXECUTION_MATRIX.md).
3. Implement missing rule-host capabilities in priority order:
   - chargen/build validation
   - gear/cyberware legality and totals
   - qualities/improvements interactions
   - magic/resonance subsystem coverage
4. Expand workspace codec and export bundle coverage where the current lane still falls back to thin projections.
5. Add execution tests for each newly supported capability.
6. Publish `SR5_ACCEPTANCE_PROOF.generated.json`.
7. Update `SR5_RULESET_DEPTH.generated.json` to:
   - `claim_ceiling: serious`
   - `serious_implementation_claim: allowed`

Exit criteria:
- acceptance receipt proves the supported SR5 workflow set end-to-end
- SR5 claim ceiling is upgraded by proof, not by copy

## Workstream 5: SR4 decision and implementation lane

Audit item:
- `ABS-003`

Repo:
- `chummer-core-engine`

Decision gate:
- either implement serious SR4 coverage
- or permanently retire any serious-SR4 claim from all public surfaces

If the product goal is serious SR4 support, do this:
1. Turn the current scaffold-plus baseline into a supported SR4 workflow definition.
2. Expand the SR4 workspace codec to cover all required core runner lifecycle sections.
3. Add SR4-specific validation, totals, and workflow rules beyond the current deterministic baseline host.
4. Add SR4 acceptance tests for:
   - create/edit/validate/export
   - inventory/augment/qualities
   - contacts/lifestyles/history
   - import/export continuity
5. Publish `SR4_ACCEPTANCE_PROOF.generated.json`.
6. Update `SR4_RULESET_DEPTH.generated.json` to permit a serious claim.

If the product goal is not serious SR4 support, do this instead:
1. search all public and internal product copy for serious/ready SR4 language
2. retire it explicitly
3. publish `SR4_CLAIM_RETIREMENT.generated.json`

Exit criteria:
- either the serious-SR4 claim is proven
- or the serious-SR4 claim is explicitly retired and removed everywhere

## Workstream 6: SR6 decision and implementation lane

Audit item:
- `ABS-002`

Repo:
- `chummer-core-engine`

Decision gate:
- either implement serious SR6 coverage
- or permanently retire any serious-SR6 claim from all public surfaces

If the product goal is serious SR6 support, do this:
1. replace the current stub-heavy SR6 workspace codec with real typed section coverage
2. add real SR6 validation and rule-host capabilities beyond the deterministic baseline
3. wire SR6-specific workflow surfaces to real supported behavior
4. add SR6 acceptance tests for:
   - create/edit/validate/export
   - core ruleset tabs
   - ruleset-specific subsystem behavior
5. publish `SR6_ACCEPTANCE_PROOF.generated.json`
6. update `SR6_RULESET_DEPTH.generated.json` to permit a serious claim

If the product goal is not serious SR6 support, do this instead:
1. search all public and internal product copy for serious/ready SR6 language
2. retire it explicitly
3. publish `SR6_CLAIM_RETIREMENT.generated.json`

Exit criteria:
- either the serious-SR6 claim is proven
- or the serious-SR6 claim is explicitly retired and removed everywhere

## Recommended sequencing by effort and dependency

Short cycle, mostly proof and deployment:
1. Workstream 1
2. Workstream 2
3. Workstream 3

Medium cycle, real engine deepening:
4. Workstream 4

Long cycle, major strategy decision:
5. Workstream 5
6. Workstream 6

## Expected outputs

Minimum new artifacts to publish:
- `CANONICAL_DOMAIN_POLICY.generated.json`
- refreshed `CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
- `SUPPORT_CASE_FLOW_PROOF.generated.json`
- `GOOGLE_OAUTH_LINKING_PROOF.generated.json`
- `CHUMMER5A_DESKTOP_EXECUTION_PROOF.generated.json`
- `PORTABLE_RECEIPTS_AUDIT.generated.json`
- `SR5_ACCEPTANCE_PROOF.generated.json`
- one of:
  - `SR4_ACCEPTANCE_PROOF.generated.json`
  - `SR4_CLAIM_RETIREMENT.generated.json`
- one of:
  - `SR6_ACCEPTANCE_PROOF.generated.json`
  - `SR6_CLAIM_RETIREMENT.generated.json`

## Definition of final closure

The absolute audit is only fully closed when all of these are true:
1. live `chummer.run` route proof is green
2. live Google OAuth/account-linking proof is green
3. live support/contact proof is green
4. fresh same-run desktop parity execution proof is green
5. portable-receipt audit is green
6. SR5 is either proven production-grade or public claims remain bounded accordingly
7. SR4 serious-support claim is either proven or retired
8. SR6 serious-support claim is either proven or retired
9. no public artifact expects or references a nonexistent `chummer6.run` public domain

Before you claim completion, rerun `python3 /docker/chummercomplete/chummer.run-services/scripts/check_absolute_audit_closure.py` and verify `closure_done` is true.
