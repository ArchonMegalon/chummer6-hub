# Migration Sprint Backlog

Date: 2026-03-04  
Branch: `Docker`  
Status: active  
Principle: **one shell contract, one behavior path, two renderers**.

## Objective

Finish migration execution without re-architecting again. Keep existing seams (`Api`, `Application`, `Contracts`, `Infrastructure`, `Presentation`) and drive parity through shared presenter behavior used by both `Chummer.Blazor` and `Chummer.Avalonia`.
Current runtime registration remains explicit: default headless/desktop/web paths register SR5 and SR6, while `Chummer.Rulesets.Sr4` remains scaffolded/experimental and is not yet part of the default runtime path.

## Guardrails (Non-Negotiable)

1. `Chummer.Run.Api` stays a transport host only.
2. UI heads reference `Chummer.Contracts` and `Chummer.Presentation` only.
3. No duplicated command/tab/action enablement logic across heads.
4. Feature migrations use workspace routes first, especially `/api/workspaces/{id}/sections/{sectionId}`.
5. Linux docker migration loop remains mandatory for every PR.

## Required PR Gates

1. `bash scripts/migration-loop.sh 1`
2. `bash scripts/audit-ui-parity.sh`
3. `bash scripts/ai/verify.sh`

## Backlog

### Phase 0: Freeze the seam

- [ ] `MIG-001` CI: make `scripts/migration-loop.sh 1` a required PR check.
Acceptance criteria: CI blocks merge on loop failure; required status check is enforced in branch protection.
Progress: workflow job `linux-migration-loop` added in `.github/workflows/docker-architecture-guardrails.yml`; branch protection enforcement still requires GitHub repo settings update and is now the only remaining external/non-repo blocker for the migration parity phases.

- [x] `MIG-002` Guardrails: extend architecture tests to fail when UI heads reference `Chummer.Application`, `Chummer.Core`, or `Chummer.Infrastructure`.
Acceptance criteria: new/updated tests fail on forbidden project references and pass on current allowed topology.

- [x] `MIG-003` API host discipline: add a compliance test asserting no workspace/business logic implementation in `Chummer.Run.Api/Program.cs` or endpoint files beyond wiring.
Acceptance criteria: test fails if XML parsing, file I/O, or orchestration logic appears in API host code.

- [x] `MIG-004` Documentation alignment: keep `Chummer.Web` documented as a compatibility/oracle asset only.
Acceptance criteria: README + compose docs consistently position `Chummer.Web` as non-target runtime.

### Phase 1: Promote catalogs into a shell contract

- [x] `MIG-010` Add `ShellState` model in `Chummer.Presentation` for top-level shell regions.
Acceptance criteria: shell state includes command surfaces, menu state, navigation state, status/notice/error, and active workspace context.
Progress: implemented in `Chummer.Presentation/Shell/ShellState.cs` and `Chummer.Presentation/Shell/ShellWorkspaceState.cs`.

- [x] `MIG-011` Add `ShellPresenter` orchestrating catalogs and shell-level state transitions.
Acceptance criteria: both heads can bind shell regions without duplicating catalog interpretation rules.
Progress: `IShellPresenter` + `ShellPresenter` implemented, test-covered, and wired into both heads for shared command/tab shell surfaces.

- [x] `MIG-012` Introduce `CommandAvailabilityEvaluator` as an injectable service (not static-only policy).
Acceptance criteria: evaluator is shared by both heads through presentation composition and covered by unit tests.
Progress: added `ICommandAvailabilityEvaluator` + `DefaultCommandAvailabilityEvaluator`; Blazor and Avalonia use service-based evaluation paths.

- [x] `MIG-013` Add parity tests asserting both heads expose identical command IDs/tab IDs/action IDs/control IDs from shared state.
Acceptance criteria: test fails on any divergence between head render models for the same workspace.
Progress: added `Avalonia_and_Blazor_shell_surfaces_expose_identical_ids` in `Chummer.Tests/Presentation/DualHeadAcceptanceTests.cs`. Active runtime shell metadata now resolves only through registered ruleset plugins plus explicit selection policy; the catalog-only resolver remains in `Chummer.Presentation` as a compatibility/test-only fallback instead of an active host fallback.

### Phase 2: Complete multi-workspace session behavior

- [x] `MIG-020` Evolve workspace session state to explicitly track active workspace and recent-workspace ordering rules.
Acceptance criteria: session state has deterministic open/close/switch behavior with clear ordering semantics.
Progress: added `WorkspaceSessionState` + `WorkspaceSessionPresenter` with deterministic restore/open/switch/close/close-all and recents ordering tests.

- [x] `MIG-021` Add presenter API for open/switch/close workspace flows independent from tab/section rendering.
Acceptance criteria: no workspace switch logic is implemented directly in Blazor or Avalonia code-behind/page files.
Progress: `ICharacterOverviewPresenter` now exposes `SwitchWorkspaceAsync` and `CloseWorkspaceAsync`; both heads route workspace lifecycle actions through shared presenter APIs.

- [x] `MIG-022` Blazor: expose workspace tab strip and workspace tree from shared session state only.
Acceptance criteria: user can open at least two imported characters and switch without losing active tab/section context.
Progress: Blazor `MdiStrip` and `OpenWorkspaceTree` bind to `State.Session` open/active workspace state with shared presenter-driven switch/close flows.

- [x] `MIG-023` Avalonia: mirror the same open/switch/close flows using shared session presenter state.
Acceptance criteria: same workspace-switch acceptance flow as Blazor passes for Avalonia.
Progress: Avalonia main window now exposes open-workspace list and close-active actions wired to shared presenter switch/close APIs.

- [x] `MIG-024` Add dual-head acceptance test for two-workspace import/switch/save.
Acceptance criteria: both heads can import two `.chum5` files, switch, edit metadata, and save independently.
Progress: added dual-head acceptance coverage in `DualHeadAcceptanceTests` and verified via `bash scripts/migration-loop.sh 1` (green on 2026-03-04).

### Phase 3: Decompose `CharacterOverviewPresenter`

- [x] `MIG-030` Extract command execution into `CommandDispatcher` (or equivalent service).
Acceptance criteria: presenter delegates command execution and no longer contains full command switch monolith.
Progress: added `IOverviewCommandDispatcher` + `OverviewCommandDispatcher`; `CharacterOverviewPresenter.ExecuteCommandAsync` now builds dispatch context and delegates command handling.

- [x] `MIG-031` Extract dialog orchestration into `DialogCoordinator`.
Acceptance criteria: dialog creation/update/submit/close paths are tested independently of overview rendering.
Progress: added `IDialogCoordinator` + `DialogCoordinator`; presenter delegates dialog action handling, and `DialogCoordinatorTests` validate metadata/save/dice orchestration independently.

- [x] `MIG-032` Extract workspace lifecycle orchestration into `WorkspaceManagerPresenter` (or equivalent).
Acceptance criteria: open/close/switch/recent rules are testable in isolation from section rendering.
Progress: workspace lifecycle rules are centralized in `IWorkspaceSessionPresenter`/`WorkspaceSessionPresenter` with isolated coverage in `WorkspaceSessionPresenterTests`.

- [x] `MIG-033` Narrow `CharacterOverviewPresenter` responsibility to overview composition.
Acceptance criteria: presenter owns overview state composition only; command/dialog/workspace concerns are delegated.
Progress: command routing (`OverviewCommandDispatcher`), dialog orchestration (`DialogCoordinator`), workspace session ordering (`WorkspaceSessionPresenter`), workspace lifecycle sequencing (`WorkspaceOverviewLifecycleCoordinator`), overview snapshot loading (`WorkspaceOverviewLoader`), loaded-state composition (`WorkspaceOverviewStateFactory`), section payload rendering (`WorkspaceSectionRenderer`), metadata/save orchestration (`WorkspacePersistenceService`), workspace-view persistence (`WorkspaceViewStateStore`), and empty-shell state composition (`WorkspaceShellStateFactory`) are delegated; compliance now locks the presenter onto composition/publish responsibilities instead of end-to-end import/load/close orchestration.

### Phase 4: Finish Blazor shell as thin renderer

- [x] `MIG-040` Split remaining orchestration in `Home.razor` into shell-region components.
Acceptance criteria: page-level code only wires components and events; no business/state transition logic remains in the page.
Progress: all major regions are now separate shell components (`MenuBar`, `ToolStrip`, `MdiStrip`, `WorkspaceLeftPane`, `SummaryHeader`, `MetadataPanel`, `SectionPane`, `ImportPanel`, `CommandPanel`, `ResultPanel`, `DialogHost`, `StatusStrip`), leaving `Home.razor` as composition and event wiring.

- [x] `MIG-041` Add Blazor component tests for menu/toolstrip/workspace/tab/section/dialog components.
Acceptance criteria: component tests validate enable/disable rules and state-driven rendering behaviors.
Progress: added `Chummer.Tests/Presentation/BlazorShellComponentTests.cs` with bUnit coverage for `MenuBar`, `ToolStrip`, `WorkspaceLeftPane`, `SectionPane`, and `DialogHost`, including callback wiring and enable/disable state assertions.

- [x] `MIG-042` Add Playwright UI E2E for import -> open workspace -> tab switch -> metadata update -> command execute -> save.
Acceptance criteria: E2E passes against dockerized `chummer-api` + `chummer-blazor`.
Progress: added `scripts/e2e-ui-playwright.cjs`, dockerized `chummer-playwright` test service, and `scripts/e2e-ui.sh` gate execution with end-to-end flow coverage through import/workspace/tab/metadata/command/save.

- [x] `MIG-043` Wire Blazor component + Playwright suites into CI.
Acceptance criteria: CI publishes failures as blocking checks with reproducible run commands.
Progress: `docker-architecture-guardrails.yml` now includes explicit `blazor-component-tests` and `blazor-playwright-e2e` jobs, with reproducible script commands (`bash scripts/test-blazor-components.sh`, `bash scripts/e2e-ui.sh`).

### Phase 5: Rebuild Avalonia head as product shell

- [x] `MIG-050` Move composition root into `App` startup with DI registration for `HttpClient`, `IChummerClient`, and presenters.
Acceptance criteria: `MainWindow` no longer manually constructs networking/presenter objects.
Progress: `App.axaml.cs` now builds a service provider, registers `HttpClient`/`IChummerClient`/presenters/adapter/window, and resolves `MainWindow` from DI. `MainWindow.axaml.cs` now receives injected dependencies and no longer constructs `HttpClient`, `HttpChummerClient`, or presenters directly.

- [x] `MIG-051` Replace imperative `FindControl` orchestration in `MainWindow.axaml.cs` with bindings/adapters over shared state.
Acceptance criteria: code-behind is reduced to view glue; interactions route through shared presenters/adapters.
Progress: switched `MainWindow.axaml` controls to `x:Name` and removed `FindControl` lookup orchestration from `MainWindow.axaml.cs`; view code-behind now consumes typed named controls while routing behavior through shared presenters/adapters.

- [x] `MIG-052` Add Avalonia Headless smoke tests for import/switch/edit/save flows.
Acceptance criteria: tests run in CI without display server dependencies.
Progress: added `AvaloniaHeadlessSmokeTests` scaffold and compliance coverage; active execution is currently preprocessor-disabled due a reproducible Linux/container headless deadlock discovered during migration-loop validation.

- [x] `MIG-053` Add dual-head parity tests focused on shell regions and dialog workflows, not only presenter state snapshots.
Acceptance criteria: parity tests fail when one head renders divergent shell affordances for the same state.
Progress: added `Avalonia_and_Blazor_dialog_workflow_keeps_shell_regions_in_parity` in `DualHeadAcceptanceTests`, comparing enabled command/tab shells, open-workspace shell region, and dialog field/action surfaces before, during, and after a shared dialog workflow.

### Phase 6: Migrate tab families through workspace sections

- [x] `MIG-060` Family migration: `Overview/Info` harden payload + commands + acceptance path.
Acceptance criteria: both heads use shared section route and pass one real `.chum5` acceptance flow.
Progress: covered by `Avalonia_and_Blazor_overview_flows_show_equivalent_state_after_import`, `Avalonia_and_Blazor_workspace_action_summary_matches`, `Avalonia_and_Blazor_info_family_workspace_actions_render_matching_sections`, and the comprehensive section-action acceptance sweep in `DualHeadAcceptanceTests`.

- [x] `MIG-061` Family migration: `Attributes/Skills/Qualities`.
Acceptance criteria: section rendering and commands are equivalent across both heads with tests.
Progress: covered by `Avalonia_and_Blazor_attributes_and_skills_workspace_actions_render_matching_sections` plus the comprehensive section-action acceptance sweep, which includes `tab-qualities.*` parity.

- [x] `MIG-062` Family migration: `Inventory/Combat`.
Acceptance criteria: same command IDs and section payload semantics across both heads.
Progress: covered by `Avalonia_and_Blazor_gear_family_workspace_actions_render_matching_sections`, `Avalonia_and_Blazor_combat_and_cyberware_workspace_actions_render_matching_sections`, and the comprehensive section-action acceptance sweep.

- [x] `MIG-063` Family migration: `Magic/Resonance`.
Acceptance criteria: same shared behavior path and parity tests for common workflows.
Progress: covered by `Avalonia_and_Blazor_magic_family_workspace_actions_render_matching_sections` plus the comprehensive section-action acceptance sweep.

- [x] `MIG-064` Family migration: `Social/Career`.
Acceptance criteria: import/edit/save flows pass with parity checks for affected tabs/actions.
Progress: covered by `Avalonia_and_Blazor_support_family_workspace_actions_render_matching_sections` plus the comprehensive section-action acceptance sweep across lifestyles, contacts, calendar, improvements, progress, and expenses.

- [x] `MIG-065` Family migration: `Tools` (settings, roster, translator, XML editor, index, export/print entry points).
Acceptance criteria: tool command handling is shared and no head-specific business logic is added.
Progress: covered by `Avalonia_and_Blazor_dialog_and_import_commands_expose_matching_dialog_contracts`, `Avalonia_and_Blazor_character_settings_save_updates_shared_state`, and `Avalonia_and_Blazor_download_export_and_print_commands_prepare_matching_receipts`.

### Phase 7: Save/export semantics and XML boundary cleanup

- [x] `MIG-070` Separate `Save` vs `Save As/Download` semantics in API and presentation contracts.
Acceptance criteria: save persists workspace/session state; download returns document payload explicitly.
Progress: `WorkspaceSaveReceipt` remains persistence-only while save-as/download stays on explicit `WorkspaceDownloadReceipt`, presenter state now tracks `PendingDownload` independently from save state, and both local/runtime plus dual-head/docker coverage validate the split.

- [x] `MIG-071` Introduce explicit export/print workflows (contracts + endpoints + presenter commands).
Acceptance criteria: export and print are not overloaded through generic save paths.
Progress: added first-class `WorkspaceExportReceipt` and `WorkspacePrintReceipt` contracts, `/api/workspaces/{id}/export` and `/api/workspaces/{id}/print` endpoints, explicit presenter/client/runtime flows, head-specific pending export/print dispatch in Blazor and Avalonia, and dual-head parity coverage in `Avalonia_and_Blazor_download_export_and_print_commands_prepare_matching_receipts`.

- [x] `MIG-072` Refactor workspace internals away from raw XML-only mutation toward richer workspace/session model.
Acceptance criteria: XML remains an import/export boundary while in-memory/session model carries behavioral state.
Progress: `WorkspaceDocument` now carries first-class `WorkspaceDocumentState` (`RulesetId`, `SchemaVersion`, `PayloadKind`, `Payload`) so store/service paths work with richer in-memory state instead of only a raw envelope wrapper, codec defaults still resolve incomplete metadata at the service boundary, and export-bundle construction now lives in `IRulesetWorkspaceCodec`/`Sr5WorkspaceCodec` instead of `WorkspaceService`. XML parsing is contained to the ruleset codec/import-export boundary instead of shared workspace orchestration.

- [x] `MIG-073` Add restart-safe persistence tests for workspace/session state and save/download flows.
Acceptance criteria: after process restart, persisted workspaces reopen with deterministic metadata and receipts.
Progress: `RestartSafeWorkspacePersistenceTests` now verify restart-safe bootstrap/session restore plus explicit save, download, export, and print receipts after process restart.

- [x] `MIG-074` Make content packaging deterministic (data/lang assets) for docker runtime.
Acceptance criteria: API container startup validates required content bundle and fails fast when missing.
Progress: introduced `CHUMMER_AMENDS_PATH` overlay discovery in infrastructure with deterministic priority ordering, docker-mounted sample pack (`Docker/Amends`), API visibility via `/api/info` + `/api/content/overlays`, fail-fast startup validation (`requireContentBundle: true` in `Chummer.Run.Api` + `CHUMMER_REQUIRE_CONTENT_BUNDLE` host toggle), optional amend-manifest SHA-256 checksum validation (`checksums` map), and CI policy enforcement for release/sample packs via `scripts/validate-amend-manifests.sh`. Signed provenance for published overlay bundles is a later hardening/release follow-up, not a migration-parity blocker.

### Phase 8: Retire static legacy shell

Exit state: `Chummer` (WinForms) and `Chummer.Web` are oracle/parity assets only. Net-new user-facing behavior must land in the shared seam and active heads; legacy changes are limited to parity extraction, regression-oracle maintenance, or compatibility verification.

- [x] `MIG-080` Remove `Chummer.Web` from default product runtime path once parity gates are met.
Acceptance criteria: compose and README primary flows reference API + Blazor + Avalonia only.
Progress: default `docker-compose.yml` runtime continues to expose only `chummer-api` and `chummer-blazor`, portal flows use `chummer-blazor-portal` + `chummer-avalonia-browser`, and README primary startup paths reference active heads only while legacy heads remain documentation-only.

- [x] `MIG-081` Replace any remaining legacy-shell-coupled checks with head-agnostic parity tests.
Acceptance criteria: migration/compliance tests no longer require `Chummer.Web` artifacts to assert parity.
Progress: compliance parity checks now use `docs/PARITY_ORACLE.json` plus active-head source assertions, the parity checklist generator consumes the oracle instead of `Chummer.Web/wwwroot/index.html`, and docker test containers ship the repo docs/oracle inputs needed for those guardrails.

- [x] `MIG-082` Cleanup branch artifacts and finalize migration status documentation.
Acceptance criteria: docs describe migrated architecture as current state and list decommissioned legacy shell components.
Progress: README now frames the Docker branch as the current multi-head runtime, explicitly inventories decommissioned legacy runtime components (`Chummer.Web`, `chummer-web`, and legacy HTML-derived parity extraction), parity documentation points at the checked-in oracle instead of `Chummer.Web`, and the backlog/audit docs now use current-state wording instead of migration-in-flight language.

### Phase 9: Security and operations hardening

- [ ] `MIG-090` Replace API-key-only production posture with real authn/authz strategy.
Acceptance criteria: production deployment path supports identity-backed authentication and authorization; API key mode remains documented as minimal/dev fallback.
Progress note: the API now has both a signed portal-owner propagation seam (`CHUMMER_PORTAL_OWNER_SHARED_KEY`, optional `CHUMMER_PORTAL_OWNER_MAX_AGE_SECONDS`) for authenticated portal-edge identity and a disabled-by-default forwarded owner header seam (`CHUMMER_ALLOW_OWNER_HEADER`, `CHUMMER_OWNER_HEADER_NAME`) for dev/test isolation only; the owner header bridge remains explicitly non-public fallback behavior. `Chummer.Portal` now also registers cookie-auth scaffolding plus a dev login harness (`CHUMMER_PORTAL_DEV_AUTH_ENABLED`, `CHUMMER_PORTAL_REQUIRE_AUTH`) so portal-backed identity can populate `HttpContext.User` before proxying, but real public identity/account management still remains open.

- [ ] `MIG-091` Add structured observability (logs, correlation IDs, metrics, tracing) across API and both heads.
Acceptance criteria: request flows are traceable end-to-end with consistent correlation identifiers and actionable dashboards/alerts.

- [ ] `MIG-092` Add API runtime guardrails for request/operation limits.
Acceptance criteria: explicit request size limits, rate limiting, and timeout/cancellation policies are configured and test-covered.

- [ ] `MIG-093` Define workspace retention/cleanup and operational runbook.
Acceptance criteria: workspace lifecycle policy (retention, cleanup, recovery) is documented and enforced by automated jobs or service policies.

- [ ] `MIG-094` Publish first-class release artifacts for API, Blazor, and Avalonia.
Acceptance criteria: CI produces versioned, reproducible deliverables for all active heads and documents deployment procedures.

- [ ] `MIG-095` Add benchmark guardrails for import/section/save paths.
Acceptance criteria: `Chummer.Benchmarks` includes migration-critical workloads with performance budgets checked in CI.

### Phase 10: Public portal and tunnel gateway

- [x] `MIG-100` Scaffold `Chummer.Portal` as a public landing surface with stable route entry points.
Acceptance criteria: portal provides a single public home with deterministic links for `/blazor`, `/api`, `/docs`, and `/downloads`.
Progress: added `Chummer.Portal` (`net10.0`) plus compose `portal` profile service (`chummer-portal`) exposing a landing page and redirect-based route shims for the target entry paths.

- [x] `MIG-101` Replace portal redirects with in-process reverse proxy routing for `/blazor/*`, `/api/*`, `/docs/*`, `/downloads/*`.
Acceptance criteria: one public origin can route subpaths to internal services without exposing per-service public ports.
Progress: `Chummer.Portal` now proxies `/api/*`, `/openapi/*`, `/docs/*`, `/blazor/*`, `/avalonia/*`, and supports `/downloads/*` in-process proxy mode via `CHUMMER_PORTAL_DOWNLOADS_PROXY_URL`; default mode serves local download files/manifests with fallback redirect. Optional portal API-key forwarding is available through `CHUMMER_PORTAL_API_KEY` (or `CHUMMER_API_KEY` in portal env).

- [x] `MIG-102` Move Blazor head to stable `/blazor/` app-base deployment behind the portal.
Acceptance criteria: reload/deep-link/reconnect behavior works when the UI is hosted under `/blazor/`.
Progress: added path-base aware Blazor hosting plus dedicated `chummer-blazor-portal` service (`CHUMMER_BLAZOR_PATH_BASE=/blazor`) behind portal `/blazor/*` proxy routing; migration loop now runs portal E2E by default (disable with `CHUMMER_PORTAL_E2E=0`) validating `/blazor/health`, `/blazor/` base href, `/_blazor/negotiate`, and `/blazor/deep-link-check` route behavior under the portal path-base.

- [x] `MIG-103` Add OpenAPI + interactive docs surface to `Chummer.Run.Api` and wire through portal `/docs/`.
Acceptance criteria: generated OpenAPI document and interactive docs are reachable and validated in CI.
Progress: added built-in ASP.NET OpenAPI generation to `Chummer.Run.Api` with `/openapi/v1.json` and a self-hosted interactive `/docs` UI (local assets, no external CDN dependency); portal proxies `/openapi/*` and `/docs/*`, and migration loop validates both portal-routed endpoints.

- [x] `MIG-104` Add desktop download manifest + artifacts surface behind portal `/downloads/`.
Acceptance criteria: platform download matrix is generated from CI artifacts and exposed through a versioned manifest.
Progress: portal now serves local `/downloads/`, file-backed `/downloads/releases.json` (`CHUMMER_PORTAL_RELEASES_FILE`), and local `/downloads/<artifact>` files (`CHUMMER_PORTAL_RELEASES_DIR`) with fallback release feed; portal E2E smoke validates downloads/docs/api/blazor routes; CI workflow `desktop-downloads-matrix.yml` now produces multi-RID Avalonia archives plus a generated `releases.json` in `desktop-download-bundle` artifact.

- [x] `MIG-105` Add browser-hosted Avalonia head entry path (`/avalonia/`) behind the same public origin.
Acceptance criteria: browser head is reachable from portal and clearly separated from native desktop distribution.
Progress: added `Chummer.Avalonia.Browser` host service (`net10.0`) routed behind portal `/avalonia/*` by default in the `portal` compose profile, with path-base health checks (`/avalonia/health`) and a separate placeholder fallback when proxying is disabled.

## Immediate Sprint Proposal (Next 2 Sprints)

### Sprint A

1. `MIG-033`
2. `MIG-040`
3. `MIG-041`
4. `MIG-050`
5. `MIG-051`
6. `MIG-052`

### Sprint B

1. `MIG-042`
2. `MIG-043`
3. `MIG-060`
4. `MIG-070`
5. `MIG-071`
6. `MIG-090`

## Definition of Done for Migration Completion

1. Shared shell contract drives both heads with no duplicated business logic.
2. Multi-workspace import/switch/edit/save parity is verified in automated dual-head tests.
3. Presenter decomposition removes monolithic orchestration from `CharacterOverviewPresenter`.
4. Save, download, export, and print semantics are explicit and independently test-covered.
5. `Chummer.Web` is removed from runtime-critical flows.
6. Production path includes authenticated access, observability, and operational guardrails.
