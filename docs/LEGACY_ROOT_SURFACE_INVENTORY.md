# Legacy Root Surface Inventory

This inventory captures non-hosted surfaces still visible at the `run-services` root and maps each to a target boundary so extraction work can execute as queued backlog instead of recurring audit churn.

## Hosted surfaces that stay in-root

- `Chummer.Run.Api`
- `Chummer.Run.AI`
- `Chummer.Run.Contracts`
- `Chummer.Run.Identity`
- `Chummer.Play.Contracts`
- `docs/`
- `tests/`
- `scripts/`

## External owner packages consumed from sibling repos

- `Chummer.Media.Contracts` via `chummer6-media-factory`
- `Chummer.Media.Factory.Runtime` via `chummer6-media-factory`
- `Chummer.Hub.Registry.Contracts` via `chummer6-hub-registry`
- `Chummer.Run.Registry` via `chummer6-hub-registry`

## Boundary moves completed

| Surface (former root) | Current boundary location | Queue anchor |
|---|---|---|
| `Docker/` | `legacy/tooling/docker/Docker/` | WL-209 |
| `docker-compose.yml` | `legacy/tooling/docker/docker-compose.yml` | WL-209 |
| `docker-compose.dcproj` | `legacy/tooling/vs-compose/docker-compose.dcproj` | WL-210 |
| `settings/` | `legacy/interoperability/settings/` | WL-210 |
| `Plugins/` | `legacy/interoperability/plugins/` | WL-211 |
| `chummer-run-services.design.v2.md` | `legacy/architecture-archive/chummer-run-services.design.v2.md` | WL-212 |

## Non-hosted root surfaces queued for boundary moves

No queued root-surface boundary moves remain from the `WL-209` to `WL-212` execution set.

## Acceptance linkage

- `docs/HUB_EXTRACTION_ACCEPTANCE.md` tracks this inventory and the runnable queue anchors.
- `tests/RunServicesVerification/HubExtractionReadinessVerification.cs` verifies acceptance references stay in place.
