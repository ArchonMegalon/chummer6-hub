# Ownership matrix

## Summary table

| Repo                    | Primary mission                    | Owns                                                                                                    | Must not own                                                                       | Key package(s)                                                                  |
| ----------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `chummer-design`        | central design governance          | canon, ownership, milestones, blockers, sync, review guidance                                           | code implementation, hidden parallel product docs                                  | none                                                                            |
| `chummer-core-engine`   | deterministic rules/runtime engine | engine truth, reducer truth, runtime bundles, explain canon, engine contracts                           | play UI, workbench UI, registry persistence, media execution, hosted orchestration | `Chummer.Engine.Contracts`                                                      |
| `chummer-presentation`  | workbench/browser/desktop UX       | builders, inspectors, compare, explain UX, admin/moderation UX                                          | play shell, rule evaluation, offline ledger, media execution                       | consumes `Chummer.Engine.Contracts`, `Chummer.Ui.Kit`                           |
| `chummer-play`          | live session/mobile/PWA shell      | player shell, GM shell, offline ledger, sync client, play-safe Coach/Spider surfaces                    | builder UX, rule evaluation, registry/moderation, provider secrets                 | consumes `Chummer.Engine.Contracts`, `Chummer.Play.Contracts`, `Chummer.Ui.Kit` |
| `chummer.run-services`  | hosted orchestration plane         | identity, relay, approvals, memory, Coach/Spider/Director orchestration, delivery, play API aggregation | duplicate mechanics, registry persistence after split, media rendering after split | `Chummer.Play.Contracts`, `Chummer.Run.Contracts`                               |
| `chummer-ui-kit`        | shared design system               | tokens, themes, shell primitives, accessibility primitives, reusable components                         | domain DTOs, HTTP clients, storage, rules math                                     | `Chummer.Ui.Kit`                                                                |
| `chummer-hub-registry`  | catalog/publication service        | artifacts, publication drafts, moderation state, installs, reviews, compatibility, runtime-bundle heads | relay, Coach/Spider, media rendering, client UX                                    | `Chummer.Hub.Registry.Contracts`                                                |
| `chummer-media-factory` | media execution plant              | render jobs, previews, manifests, asset lifecycle, provider adapters, signed asset access               | campaign truth, rules truth, approvals policy, player/client UX                    | `Chummer.Media.Contracts`                                                       |
| `chummer5a`             | legacy oracle                      | migration fixtures, regression corpus, legacy compatibility reference                                   | vNext architecture ownership                                                       | none                                                                            |

## Boundary notes

### `chummer-core-engine`

The only repo allowed to define canonical mechanics truth.

### `chummer-presentation`

The only repo allowed to define workbench/browser/desktop product UX.

### `chummer-play`

The only repo allowed to define the dedicated live play/mobile shell.

### `chummer.run-services`

The only repo allowed to own hosted orchestration, but not the only repo allowed to own hosted services.
Registry and media must remain separate service boundaries.

### `chummer-ui-kit`

The only repo allowed to own shared cross-head UI primitives.

### `chummer-hub-registry`

The only repo allowed to own immutable artifact catalog and publication/install truth.

### `chummer-media-factory`

The only repo allowed to own render execution and render-asset lifecycle.

## Ownership violations

Any of the following is an ownership violation:

* a repo introduces a shared cross-repo DTO family outside its canonical package
* run-services reintroduces media rendering or registry persistence after those splits complete
* presentation reclaims play-shell ownership
* play reimplements rules truth
* ui-kit gains domain DTOs or HTTP clients
* engine begins depending on presentation/play/service code
* design repo becomes stale enough that code repos must invent architecture locally


## External integration ownership notes

### `chummer-design`

Owns:

* external-tool classification
* approved usage policy
* system-of-record rules
* rollout and blocker publication

Must not own:

* provider SDK code
* runtime secrets
* adapter implementations

### `chummer.run-services`

Owns:

* AI/provider routing
* approval bridges
* docs/help bridges
* survey bridges
* automation bridges
* evaluation and prompt-toolchain integrations

Must not own:

* media rendering internals
* client-side provider access
* duplicate engine semantics

### `chummer-media-factory`

Owns:

* document/image/video/preview/archive adapters
* media provider receipts
* media provider provenance
* media asset lifecycle for provider-generated outputs

Must not own:

* approvals policy
* campaign/session meaning
* prompt registry canon
* client UX

### `chummer-presentation` and `chummer-play`

Must not own:

* vendor credentials
* direct provider SDK integrations
* direct third-party API orchestration

## External integration ownership

### `chummer-design`

Owns:

* external-tool classification
* approved usage policy
* system-of-record rules
* rollout governance
* provenance requirements

Must not own:

* provider SDK implementations
* runtime secrets
* vendor adapters

### `chummer.run-services`

Owns:

* orchestration-side external integrations
* reasoning-provider routing
* approval bridges
* docs/help bridges
* survey bridges
* automation bridges
* research/eval/prompt-tooling integrations

Must not own:

* media rendering internals
* client-side vendor access
* duplicate engine semantics

### `chummer-media-factory`

Owns:

* render/archive adapters
* provider-run receipts for media work
* media provenance capture
* media archive execution

Must not own:

* approvals policy
* campaign/session meaning
* client UX
* registry truth

### `chummer-presentation` and `chummer-play`

Must not own:

* vendor credentials
* direct provider SDK access
* direct third-party orchestration

