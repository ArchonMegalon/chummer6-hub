# Ownership matrix

## Summary table

| Repo                    | Primary mission                    | Owns                                                                                                    | Must not own                                                                       | Key package(s)                                                                  |
| ----------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `chummer6-design`        | central design governance          | canon, ownership, milestones, blockers, sync, review guidance                                           | code implementation, hidden parallel product docs                                  | none                                                                            |
| `chummer6-core`   | deterministic rules/runtime engine | engine truth, reducer truth, runtime bundles, runtime fingerprints, explain canon, engine contracts     | play UI, workbench UI, registry persistence, media execution, hosted orchestration | `Chummer.Engine.Contracts`                                                      |
| `chummer6-ui`  | workbench/browser/desktop UX       | builders, inspectors, compare, explain UX, admin/moderation UX, desktop packaging, installer/updater recipe | play shell, rule evaluation, offline ledger, media execution, release-channel truth | consumes `Chummer.Engine.Contracts`, `Chummer.Ui.Kit`                           |
| `chummer6-mobile`          | live session/mobile/PWA shell      | player shell, GM shell, offline ledger, sync client, play-safe Coach/Spider surfaces                    | builder UX, rule evaluation, registry/moderation, provider secrets                 | consumes `Chummer.Engine.Contracts`, `Chummer.Play.Contracts`, `Chummer.Ui.Kit` |
| `chummer6-hub`  | hosted orchestration and community plane | identity, user accounts, groups, memberships, ledgers, participation UX, relay, approvals, memory, Coach/Spider/Director orchestration, delivery, play API aggregation, registry-backed downloads UX | duplicate mechanics, registry persistence after split, media rendering after split, raw participant auth caches, Fleet worker execution, release manifest generation truth | `Chummer.Play.Contracts`, `Chummer.Run.Contracts`                               |
| `chummer6-ui-kit`        | shared design system               | tokens, themes, shell primitives, accessibility primitives, reusable components                         | domain DTOs, HTTP clients, storage, rules math                                     | `Chummer.Ui.Kit`                                                                |
| `chummer6-hub-registry`  | catalog/publication service        | artifacts, publication drafts, release channels, installs, update feeds, reviews, compatibility, runtime-bundle heads | relay, Coach/Spider, media rendering, client UX, installer build execution         | `Chummer.Hub.Registry.Contracts`                                                |
| `chummer6-media-factory` | media execution plant              | render jobs, previews, manifests, asset lifecycle, provider adapters, signed asset access               | campaign truth, rules truth, approvals policy, player/client UX                    | `Chummer.Media.Contracts`                                                       |
| `fleet`                  | execution/control plane            | worker orchestration, queue policy, review/landing control, cheap-first automation, explicit premium burst lanes, lane-local auth helpers, sponsor-session receipts, release orchestration, publish/signoff evidence | product truth, contract canon, session truth, user/group/ledger truth, raw hosted identity/auth storage, installer recipe truth, canonical release-channel truth      | none                                                                            |
| `chummer5a`             | legacy oracle                      | migration fixtures, regression corpus, legacy compatibility reference                                   | vNext architecture ownership                                                       | none                                                                            |

## Boundary notes

### `chummer6-core`

The only repo allowed to define canonical mechanics truth.

### `chummer6-ui`

The only repo allowed to define workbench/browser/desktop product UX.
It is also the only repo allowed to own the desktop installer/updater recipe.

### `chummer6-mobile`

The only repo allowed to define the dedicated live play/mobile shell.

### `chummer6-hub`

The only repo allowed to own the reusable community/accounting plane and hosted orchestration, but not the only repo allowed to own hosted services.
Registry and media must remain separate service boundaries.

### `chummer6-ui-kit`

The only repo allowed to own shared cross-head UI primitives.

### `chummer6-hub-registry`

The only repo allowed to own immutable artifact catalog, publication/install/update truth, and promoted release channels.

### `chummer6-media-factory`

The only repo allowed to own render execution and render-asset lifecycle.

### `fleet`

The only adjacent repo allowed to own cross-repo worker scheduling, release orchestration, participant worker lifecycle, and landing control, but never canonical Chummer product truth.

## Ownership violations

Any of the following is an ownership violation:

* a repo introduces a shared cross-repo DTO family outside its canonical package
* hub reintroduces media rendering or registry persistence after those splits complete
* ui reclaims play-shell ownership
* mobile reimplements rules truth
* ui-kit gains domain DTOs or HTTP clients
* engine begins depending on ui/mobile/hub code
* design repo becomes stale enough that code repos must invent architecture locally
* fleet introduces execution policy that contradicts mirrored design canon


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
* raw participant Codex/OpenAI auth caches

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

### `fleet`

Owns:

* cheap-first execution policy
* jury-gated landing automation
* dynamic participant burst lanes after explicit Hub consent
* lane-local auth/cache storage on the execution host
* sponsor-session execution metadata on participant lanes
* signed contribution receipts emitted from meaningful execution events

Must not own:

* product architecture canon
* direct Hub identity/session issuance
* participant-consent UX outside the Hub boundary
* canonical user, group, reward, or entitlement ledger truth
* boost-code-first product logic that should live in Hub

Fleet must also keep guide-generation and guide-verification truth downstream of `chummer6-design` instead of hiding canonical participation semantics behind EA-side helper code.

### `chummer6-hub`

Owns:

* identity principal to product-user mapping
* user accounts and profiles
* generic groups, memberships, join codes, and boost codes
* fact ledger, reward journal, and entitlement journal
* sponsor-session UX, community visibility, badges, quests, and leaderboards

Must not own:

* raw participant Codex/OpenAI auth caches
* Fleet worker-process lifecycle or repo landing control
* provider-secret ownership or provider-runtime accounting

### Participation workflow note

The canonical sponsor/consent/device-auth/lane/receipt/revoke workflow is defined centrally in `products/chummer/PARTICIPATION_AND_BOOSTER_WORKFLOW.md`.
Hub, Fleet, EA, and `Chummer6` must compile from that workflow instead of carrying parallel product interpretations.
