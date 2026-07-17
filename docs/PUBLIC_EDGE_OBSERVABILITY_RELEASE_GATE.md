# Public-edge observability release gate

`scripts/verify_public_edge_observability_release.py` is a fail-closed stable-promotion input. It proves that the checked-in telemetry contract, a real operator alert-delivery test, the current release manifest, and the current public-edge runtime sources all refer to the same candidate.

It does not configure a monitoring provider, activate alerts, or send a test alert. An operator or governed live-ops process must perform those actions and import the resulting proof at:

`chummer.run-services/.codex-studio/published/PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json`

## Required operator proof

The imported JSON must use `chummer.public_edge_observability_operator_proof.v1` and contain:

```json
{
  "contract_name": "chummer.public_edge_observability_operator_proof.v1",
  "status": "pass",
  "generated_at_utc": "<timezone-aware UTC timestamp>",
  "policy_sha256": "<SHA-256 of ops/public-edge-observability-policy.json>",
  "release_candidate": {
    "sha256": "<SHA-256 of the exact RELEASE_CHANNEL.generated.json bytes>",
    "version": "<releaseVersion/version from that manifest>",
    "channel": "<channel/channelId from that manifest>"
  },
  "runtime_source_fingerprint_sha256": "<aggregate from this gate's runtime_source_binding>",
  "monitor_backend": {
    "provider": "<provider identifier>",
    "deployment_id": "<non-secret deployment identifier>",
    "binding_status": "verified"
  },
  "sli_bindings": {
    "availability": true,
    "latency": true,
    "readiness": true
  },
  "alert_route": {
    "receiver_class": "primary_on_call",
    "binding_status": "verified",
    "delivery_tested_at_utc": "<timezone-aware UTC timestamp>",
    "delivery_test_result": "delivered"
  }
}
```

The placeholders are schema documentation, not acceptable evidence. Do not put credentials, receiver addresses, tokens, or message contents in the proof.

The proof is rejected if it is stale, future-dated beyond the five-minute clock-skew allowance, does not report a delivered test, names a different policy/candidate/runtime fingerprint, or fails any SLI/route binding. Unknown fields are rejected so credentials, receiver addresses, message content, and other private data cannot hitchhike in the canonical artifact. Symlinked, oversized, non-regular, and unstable source files are also rejected. The release manifest must itself be a published manifest with a version, channel, and timezone-aware publication timestamp.

## Guarded external-proof intake

The repository does not generate this proof: only a real monitoring-backend binding plus a delivered alert test can produce it. Place that external export at the deterministic incoming path:

`.state/incoming_public_edge_observability_operator_proof/PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json`

Materialize a current, redacted intake request before asking for proof:

```bash
python3 scripts/materialize_public_edge_observability_operator_proof_intake_request.py
```

The request is written to `.codex-studio/published/PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF_INTAKE_REQUEST.generated.json`. It records the exact policy digest, release-manifest digest/version/channel, runtime-source aggregate, deterministic drop path, and validate/import/verify commands. It is not operator proof and cannot clear the gate. Rematerialize it after any policy, release-manifest, or bound runtime-source change.

For a bounded local wait that refreshes those bindings before every poll and stops after 15 minutes by default, run:

```bash
python3 scripts/watch_public_edge_observability_operator_proof.py
```

The watcher is validate-only by default. It never generates proof, configures monitoring, sends alerts, searches broad filesystem roots, or changes the canonical proof. Its state receipt is `.state/public_edge_observability_operator_proof_watcher.generated.json`. A timeout leaves the lane in `waiting_for_external_proof`; an invalid file is rejected by the existing guarded importer.

Only after reviewing the request and intentionally authorizing canonical import may an operator opt in:

```bash
python3 scripts/watch_public_edge_observability_operator_proof.py --import-proof
```

That explicit mode still delegates validation and import to `import_public_edge_observability_operator_proof.py`, which recomputes current bindings at import time. After a successful exact-byte import it regenerates the release gate. A binding change between polling and import therefore fails closed instead of importing stale proof.

Then validate it without changing the canonical proof:

```bash
python3 scripts/import_public_edge_observability_operator_proof.py
```

A successful dry run reports `OPERATOR_PROOF_VALIDATED_NOT_IMPORTED`. Review that redacted receipt, then import the exact validated bytes:

```bash
python3 scripts/import_public_edge_observability_operator_proof.py --import-proof
```

The importer defaults to validate-only. It never configures a monitoring provider, sends an alert, repairs evidence, or updates proof timestamps. It rejects the canonical destination as its own source, refuses final-component symlinks, validates the current policy/release/runtime/freshness bindings, and preserves an existing canonical proof when validation fails. On success it atomically installs the exact source bytes and records their SHA-256 in `PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF_INTAKE.generated.json` without copying proof contents into the intake receipt.

After a successful import, regenerate the release gate. Do not edit or restamp a stale/mismatched proof; obtain a new external test for the current bindings instead.

## Gate receipt and stable-promotion validation

Run:

```bash
python3 scripts/verify_public_edge_observability_release.py
```

The receipt is written even on failure to `.codex-studio/published/PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json`. A stable-promotion consumer must fail before mutation unless all of these checks succeed:

1. `contract_name` is `chummer.public_edge_observability_release_gate.v1`, `status` is `pass`, `verdict` is `OBSERVABILITY_RELEASE_READY`, and `failures` is empty.
2. `operator_proof.path` is the expected proof path; its current file SHA-256 equals `operator_proof.sha256`; and the parsed proof's `status` and `generated_at_utc` equal the receipt fields.
3. The current release-channel manifest SHA-256, version, and channel equal `release_candidate.sha256`, `release_candidate.version`, and `release_candidate.channel`.
4. Every current source SHA-256 and the canonical aggregate equal `runtime_source_binding.sources[*].sha256` and `runtime_source_binding.aggregate_sha256`.
5. The gate is rerun immediately before promotion so proof age and alert-delivery age are evaluated at decision time.

Changing any proof byte, candidate-manifest byte, or bound runtime source invalidates the corresponding digest and requires a fresh gate receipt. A source change also requires a new real operator proof because the operator proof itself binds the runtime aggregate.
