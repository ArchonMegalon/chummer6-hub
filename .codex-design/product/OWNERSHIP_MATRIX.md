# Ownership matrix

## Summary table

| Repo                    | Primary mission                    | Owns                                                                                                    | Must not own                                                                       | Key package(s)                                                                  |
| ----------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `chummer6-design`        | central design governance          | canon, ownership, milestones, blockers, sync, review guidance                                           | code implementation, hidden parallel product docs                                  | none                                                                            |
| `chummer6-core`   | deterministic rules/runtime engine | engine truth, reducer truth, runtime bundles, explain canon, engine contracts                           | play UI, workbench UI, registry persistence, media execution, hosted orchestration | `Chummer.Engine.Contracts`                                                      |
| `chummer6-ui`  | workbench/browser/desktop UX       | builders, inspectors, compare, explain UX, admin/moderation UX                                          | play shell, rule evaluation, offline ledger, media execution                       | consumes `Chummer.Engine.Contracts`, `Chummer.Ui.Kit`                           |
| `chummer6-mobile`          | live session/mobile/PWA shell      | player shell, GM shell, offline ledger, sync client, play-safe Coach/Spider surfaces                    | builder UX, rule evaluation, registry/moderation, provider secrets                 | consumes `Chummer.Engine.Contracts`, `Chummer.Play.Contracts`, `Chummer.Ui.Kit` |
| `chummer6-hub`  | hosted orchestration plane         | identity, relay, approvals, memory, Coach/Spider/Director orchestration, delivery, play API aggregation | duplicate mechanics, registry persistence after split, media rendering after split | `Chummer.Play.Contracts`, `Chummer.Run.Contracts`                               |
| `chummer6-ui-kit`        | shared design system               | tokens, themes, shell primitives, accessibility primitives, reusable components                         | domain DTOs, HTTP clients, storage, rules math                                     | `Chummer.Ui.Kit`                                                                |
| `chummer6-hub-registry`  | catalog/publication service        | artifacts, publication drafts, moderation state, installs, reviews, compatibility, runtime-bundle heads | relay, Coach/Spider, media rendering, client UX                                    | `Chummer.Hub.Registry.Contracts`                                                |
| `chummer6-media-factory` | media execution plant              | render jobs, previews, manifests, asset lifecycle, provider adapters, signed asset access               | campaign truth, rules truth, approvals policy, player/client UX                    | `Chummer.Media.Contracts`                                                       |
| `chummer5a`             | legacy oracle                      | migration fixtures, regression corpus, legacy compatibility reference                                   | vNext architecture ownership                                                       | none                                                                            |

## Boundary notes

### `chummer6-core`

The only repo allowed to define canonical mechanics truth.

### `chummer6-ui`

The only repo allowed to define workbench/browser/desktop product UX.

### `chummer6-mobile`

The only repo allowed to define the dedicated live play/mobile shell.

### `chummer6-hub`

The only repo allowed to own hosted orchestration, but not the only repo allowed to own hosted services.
Registry and media must remain separate service boundaries.

### `chummer6-ui-kit`

The only repo allowed to own shared cross-head UI primitives.

### `chummer6-hub-registry`

The only repo allowed to own immutable artifact catalog and publication/install truth.

### `chummer6-media-factory`

The only repo allowed to own render execution and render-asset lifecycle.

## Ownership violations

Any of the following is an ownership violation:

* a repo introduces a shared cross-repo DTO family outside its canonical package
* hub reintroduces media rendering or registry persistence after those splits complete
* ui reclaims play-shell ownership
* mobile reimplements rules truth
* ui-kit gains domain DTOs or HTTP clients
* engine begins depending on ui/mobile/hub code
* design repo becomes stale enough that code repos must invent architecture locally


## External integration ownership

### `chummer6-design`

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

### `chummer6-hub`

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

### `chummer6-media-factory`

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

### `chummer6-ui` and `chummer6-mobile`

Must not own:

* vendor credentials
* direct provider SDK access
* direct third-party orchestration
