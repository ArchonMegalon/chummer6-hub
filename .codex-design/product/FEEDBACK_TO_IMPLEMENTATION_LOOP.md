# Feedback to implementation loop

## intake:
Owner repo: executive-assistant/chummer6-hub/EA
Goal: Split public ideas from private support signals and keep crash/bug support private.
Verification: Feed `/feedback` through an intake event packet that distinguishes signal from support; block public completion claims on unresolved private support cases.

## ea audit:
Owner repo: executive-assistant
Goal: Convert support/signal items into governed EA request packets with severity, scope, and acceptance evidence.
Verification: `materialize_product_governor_packet` must emit owner, scope, owner intent, and gating policy and include a stable `governor_packet_id` per intake item.

## fleet workpackage:
Owner repo: fleet
Goal: Generate workpackage artifacts only for governance-approved package decisions and track closure state.
Verification: `materialize_fleet_workpackage_from_governor_packet` must emit signed package-id, proposer, impact class, and close state in the same run proof plane.

## release proof:
Owner repo: chummer6-hub
Goal: Never notify users of closeout before release proof and support proof are both present.
Verification: `release_proof_before_notify` checks in both support automation and public docs must require `GOOGLE_OAUTH_LINKING_PROOF.generated.json`, `SUPPORT_CASE_FLOW_PROOF.generated.json`, and corresponding gate proofs.

## next action
- Keep `/feedback` as signal-only until governance + workpackage + release proof are present.
- Maintain bounded copy and keep closure events in `FEEDBACK_TO_IMPLEMENTATION_LOOP.md`, `VERIFICATION_COMMANDS.md`, and `E2E_RESULTS.generated.json`.
