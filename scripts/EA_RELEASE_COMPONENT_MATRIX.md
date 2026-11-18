# Executive Assistant Chummer release boundary

`ea_release_component_matrix.v1.json` is the closed-world policy for Executive
Assistant components that may affect a Chummer release decision. The JSON is
not self-authorizing: `ea_release_component_policy.py` pins the exact component
set, classifications, and release-gate bindings in code and rejects drift.

Only these components are release-critical:

- `release_approval_ledger`
- `publication_authorization`
- `operator_revocation_transport`

These components are explicitly record-only and have no canonical blocking
release-gate binding:

- `audiobook_providers`
- `memorial_memory_bridge`
- `black_ledger_automation`
- `travel_ooda`
- `outbound_growth`

The mixed `verify_ea_operator_readiness` gate is bound only to the three
release-critical components. MyMedia/Alexa remains an operator diagnostic, but
it is not a required readiness component and its public-surface verifier is not
part of the canonical Chummer release gate plan.

Unknown component IDs, unknown fields, classification changes, and unapproved
gate bindings fail closed. A status report cannot declare its own blocker flag;
the matrix alone supplies blocker authority. Failed or unavailable record-only
components remain visible in `non_release_critical_findings` and never appear
in `release_blockers`.

Validate the canonical policy:

```bash
python3 scripts/verify_ea_release_component_matrix.py
```

Evaluate a component report:

```bash
python3 scripts/verify_ea_release_component_matrix.py \
  --component-report /path/to/ea-component-status.json
```

The report contract is `chummer.ea_component_status_report.v1` with a
`components` list. Each row contains only `component_id`, `status`, and an
optional non-empty `detail`. Allowed statuses are `pass`, `fail`, `unavailable`,
and `unknown`. All three release-critical rows must pass; omitted critical rows
are treated as unknown and block under their pinned component IDs.
