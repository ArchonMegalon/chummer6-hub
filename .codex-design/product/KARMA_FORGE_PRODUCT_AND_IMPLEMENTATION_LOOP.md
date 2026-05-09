# Karma Forge loop

## submission
Owner repo: chummer6-hub/chummer6-hub-registry/chummer6-core
Submission: Capture user intent and submission packet through governed route and attach immutable request IDs.
verification: `gate-karma-forge` acceptance requires submission evidence and route contract receipts.

## rules impact audit
Owner repo: chummer6-core
Rules impact audit: Compute compatibility and policy impact before package candidate generation.
verification: Keep evidence receipt per rules family and include compatibility summary in public-safe channel.

## package candidate
Owner repo: chummer6-hub-registry
Package candidate: Create candidate record, provenance pointer, and rollback status.
verification: Candidate creation requires tests, compatibility matrix, and public projection proof.

## rollback
Owner repo: chummer6-hub-registry
Rollback: Keep an explicit reverse path for package impact and compatibility failures.
verification: Every candidate path must include rollback receipt, rejection proof, and audit trail pointer.

## verification
Owner repo: chummer6-hub
Verification: Gate pass only when submission, impact, candidate, and rollback receipts exist in one evidence bundle and match active run_id.
