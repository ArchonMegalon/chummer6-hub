# Package management and public package browser

## package model:
Owner repo: chummer6-hub-registry
Design: Capture package identity, compatibility matrix, provenance, and release state in registry contracts.
Verification: `gate-package-management` command suite must pass plus compatibility and package lifecycle checks for install/update/follow/revoke with evidence binding.

## public routes:
Owner repo: chummer6-hub-registry
Scope: Keep package discovery in `/packages`, detail in `/packages/{packageId}`, and vote/follow in `/packages/{packageId}/vote` with explicit package IDs and compatibility markers.
Verification: Package browser routes must include proof receipts and must reference gate-level gate-command outputs.

## admin routes:
Owner repo: chummer6-hub-registry
Policy: Keep administrative package mutation workflows isolated behind support/gov proof and explicit release-gate checks.
Verification: Admin projection paths must fail closed if release proof or impact receipts are missing.

## verification:
Owner repo: chummer6-hub
Definition: Package claims are acceptable only when package routes and public browser proof all share the same `run_id`, evidence proof set, and compatible compatibility receipts.
Next action: Keep package claim docs in preview scope while refresh cadence remains live-bound and route-aware.
