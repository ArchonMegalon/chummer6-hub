# Flagship Horizons Gate

This gate keeps the public roadmap tied to deployed proof instead of aspirational labels. The aggregate verifier is `scripts/verify_public_edge_postdeploy_gate.py`; it emits a `flagshipHorizons` child receipt.

## Horizons

1. `near_term_stabilization`: downloads, navigation, PWA static assets including service-worker-declared cache/shell paths, ready mobile handoff, service-worker boundary, ProductLift iframe shell, and portal runtime image guard must pass.
2. `mid_term_pwa_session_utility`: `/mobile`, `/mobile/player`, `/mobile/gm`, `/mobile/observer`, and `/play/continuity` must be deployed; playtime tools must include inventory, health, ammo, modifiers, and quick rolls; player/gm/organizer packet roles must be present and their advertised markdown/json packet routes must load with matching role IDs.
3. `long_term_living_world_expansion`: living-world must stay opt-in by default through `/mobile/pwa/ledger.json`, private/no-store cache headers, `living_world` playtime tooling, the `shared_portal_root_worker` service-worker boundary, and an anonymous ledger payload that explicitly keeps Black Ledger heat, followed-world updates, session continuity, and private table state hidden until account opt-in.

## Release Evidence

For release claims, run the public-edge gate with all browser proofs:

```bash
python3 scripts/verify_public_edge_postdeploy_gate.py \
  --base-url https://chummer.run \
  --skip-preflight \
  --require-downloads-status-playwright \
  --require-mobile-pwa-viewport-playwright \
  --require-frontdoor-navigation-playwright \
  --expected-portal-image-id sha256:<approved-portal-image-id> \
  --portal-container chummer6-hub-chummer-portal-1 \
  --portal-image-tag chummer-run-api:local \
  --output .codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json
```

The receipt must include `flagshipHorizonsStatus=pass`, horizon ids `near_term_stabilization`, `mid_term_pwa_session_utility`, and `long_term_living_world_expansion`, and `flagshipHorizonsBrowserProofCoverage=full` when browser-backed release evidence is required.
