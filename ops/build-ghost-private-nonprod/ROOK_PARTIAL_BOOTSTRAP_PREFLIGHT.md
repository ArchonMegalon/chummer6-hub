# Partial-stack bootstrap preflight — observation only

This additive helper covers the narrow state that the prior-rollout helper must
not adopt: one retained, healthy Presentation container and no other containers
in the private Compose project, including stopped AI, Edge, initializers or
ingress containers. The historical Compose recipe may be missing. This helper
neither reconstructs it nor invents a passing historical attestation.

`preflight-provider-disabled-rook-bootstrap.py` does **not** deploy, bootstrap,
recover, reconcile, initialize a volume, activate a provider, run a canary, or
grant permission to do any of those things. Exit 0 means only that two bounded
metadata observations agreed with the explicit operator admission and that the
supplied secret formats were valid. `deploymentReady` remains false.

## Operator input contract

Use `/usr/bin/python3 -I`. Python standard library only; no package installation.
The helper trusts the installed `/usr/bin/docker` and local Docker daemon. It
pins `--host unix:///var/run/docker.sock`, supplies a minimal child environment,
and supports no CLI executable, Docker endpoint, project, recipe or provider
override. The Python dependency-injection seam is for synthetic tests only.

Supply an absolute, regular, operator-owned, non-group/world-writable JSON
admission file, at most 32 KiB. Symlinks in its path, duplicate/unknown keys,
non-JSON constants, mutable image references and malformed identifiers fail
closed. Its exact schema is illustrated below; angle-bracket values are
deliberately invalid placeholders, not observed runtime evidence.

```json
{
  "schema": "chummer.build_ghost.partial_bootstrap_admission.v1",
  "project": "chummer-build-ghost-private-nonprod",
  "presentation": {
    "containerId": "<64 lowercase hex>",
    "imageId": "sha256:<64 lowercase hex>",
    "packetVolume": "chummer-build-ghost-private-nonprod_build-ghost-packet-access",
    "packetVolumeCreatedAt": "<exact Docker CreatedAt>"
  },
  "privateNetwork": {
    "id": "<64 lowercase hex>",
    "name": "chummer-build-ghost-private-nonprod_build-ghost-private"
  },
  "caddyVolumes": {
    "caddy-data": null,
    "caddy-config": null,
    "caddy-trust": null
  },
  "images": {
    "ai": {
      "id": "sha256:<64 lowercase hex>",
      "sourceRevisions": {
        "hub": "<40 lowercase hex>",
        "core": "<40 lowercase hex>",
        "hubRegistry": "<40 lowercase hex>",
        "mediaFactory": "<40 lowercase hex>"
      }
    },
    "edge": {
      "id": "sha256:<64 lowercase hex>",
      "repoDigest": "caddy@sha256:<64 lowercase hex>"
    }
  }
}
```

Each Caddy volume must be absent when its admission is `null`. To admit an
already-existing one, replace `null` with an object containing only `name` (the
canonical project-prefixed volume name) and its exact `createdAt`. It must use
the local driver/scope with no driver options, carry matching Compose ownership
labels, and have no consumers in any container state. This admits identity and
non-use only: Caddy trust/config contents and private key custody are unexamined.
The live-support journal volume must be absent; v1 does not adopt an existing
journal under a potentially different MAC key.

The retained packet volume is never opened. Its name, creation time, driver,
scope, ownership, mount source and sole all-state consumer must agree. Its sole
mount must remain read-write at `/app/state`. Presentation must have exactly the
admitted internal, local bridge network, no published ports, no extra mounts,
and no AI/Edge/ingress-reserved aliases. The network must have only Presentation
as both its current endpoint and its all-state container consumer.

Pass a private inherited FD above 2 containing a JSON object with exactly:

- `CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN`
- `CHUMMER_AI_INTERNAL_API_TOKEN`
- `CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY`

The two tokens must be distinct printable ASCII strings of 32–4096 characters
with no whitespace. The journal key must be distinct, canonical base64 encoding
exactly 32 bytes. The input is capped at 16 KiB and three seconds; a regular-file
FD must be operator-owned and have no group/other permission bits. The FD is
consumed and closed before child execution. Values and secret digests are never
printed, persisted, or passed to Docker. Test fixture secrets are synthetic and
must never be used for deployment. Format validity is **not** proof of entropy,
custody, token compatibility with Presentation, or existing journal integrity.

For an operator-authorized observational run (not executed by this change):

```sh
/usr/bin/python3 -I ops/build-ghost-private-nonprod/preflight-provider-disabled-rook-bootstrap.py \
  --admission /operator/partial-bootstrap-admission.json \
  --secrets-fd 3 3</operator/private-bootstrap-secrets.json
```

No Docker command emits `Config.Env` or complete inspect output. Only explicit
nonsecret projections are requested; tool diagnostics are bounded and discarded.
Any nonzero Docker result, malformed output, missing pin or observation drift
blocks the preflight. Failed inspect is never treated as absence. Runtime
observations are not an atomic lock or a reusable deployment permit.

A passing report binds the exact public admission bytes using `admissionSha256`
and the selected nonsecret Docker projection using `runtimeProjectionSha256`.
Neither hash includes the private FD input. They identify what was observed;
they do not authenticate image provenance, historical authority or readiness.

## What remains unimplemented and unproven

The full private grounded four-service deployment still needs all of the
following; a passing preflight cannot substitute for any of them:

1. Authenticate staged build/source provenance, not merely compare operator pins
   with self-reported image labels. The fourth, signed-in ingress image/config
   contract is not implemented by this preflight.
2. Establish operator-controlled token compatibility with retained Presentation
   and durable journal-key custody without disclosing runtime credentials.
3. Implement an explicit bootstrap transaction/ownership journal and rollback
   contract: preserve the original Presentation container and packet volume;
   track exactly newly created resources; leave retained/admitted volumes
   untouched on failure; contain only transaction-owned additions. Do not use a
   fabricated prior recipe or loosen the repaired historical-authority helper.
4. Create and initialize the new live-support journal with the admitted key and
   correct UID/mode, and prove MAC/state integrity under that same custody.
5. Start the provider-disabled additions and independently verify all provider
   gates, immutable identities, health, mounts, internal networks, loopback-only
   ports, TLS trust and source/readback consistency after startup and failure.
6. Execute a grounded local canary proving packet/workspace readback and cleanup,
   then establish real signed-in ingress and UI routing for the fourth service.
7. Record honest disabled/unconfigured provider and team truth separately from
   service readiness. Do not satisfy the current provider-aware attester using
   invented credentials, bindings or historical deployment evidence.

The helper emits these missing-operation categories on both success and failure.
No source recipe, existing rollout helper, attester, package bytes or live
runtime is changed by this additive preflight. The protected package-plane CI
compiles this helper and executes its daemon-free tests alongside the existing
rollback checks; the source-policy test requires that exact test-module set.

## Daemon-free test command

```sh
python3 -m pytest -q tests/test_build_ghost_partial_bootstrap_preflight.py
```

The isolated test launcher injects a strict fake Docker executable. Every logged
argument vector must match the exact read-only allowlist, even on negative tests.
Tests use only temporary synthetic admission, metadata and secret inputs; they
never access a real Docker daemon, provider, credential store or package builder.

## Implementation validation receipt

The isolated implementation started at
`5cc9e6db67a5d040abefbe1439b0805da3838d55` and was fast-forwarded to protected
main `e60335553a77cb442c583aa2d5a5ad206b0ff667` before CI integration.
The first test-first RED was a new-feature preimplementation failure: the helper
did not yet exist (`1 failed in 0.11s`), not a regression in an existing lane.
The initial complete implementation reached `118 passed in 18.16s`.
Adding public observation bindings then produced a focused semantic RED
(`1 failed, 118 deselected in 0.54s`, missing `admissionSha256`) before the
binding implementation. All validation uses the synthetic test seam above.
The final frozen helper and tests passed `119 passed in 19.39s` using the
daemon-free command above. The helper's SHA256 is
`d8c7b799fa173e76720b7f60e114b9adcfd0267822e9eec84003a5372244f78a`;
the test file's SHA256 is
`85fb9b76da846985e89d9e8b8db9e50777f5b37c0601e5564962c65a9fde1bb8`.
No live readiness result is asserted by these tests or this receipt.

Root integration validation on that base: the newly required CI inclusion test
first failed because the helper was not wired into the workflow, then the
corrected workflow and helper suite passed `120 passed in 21.15s`. The exact
five-module rerun with SDK 10.0.103 on PATH passed `308 passed, 9 skipped in
71.58s`; the skipped package-integration cases are not claimed as executed.
An earlier default-PATH attempt reported `307 passed, 9 skipped, 1 failed`
because system SDK 10.0.111 cannot load this repo's exact SDK 10.0.103 policy.
No assertion or SDK policy was loosened. Independent review covered all five
changed files and found no blocker; hosted qualification remains separate.
