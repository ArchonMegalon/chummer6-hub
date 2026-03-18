# Hosted Boundary

`chummer6-hub` keeps its active hosted surface limited to:

- `Chummer.Play.Contracts`
- `Chummer.Run.Contracts`
- `Chummer.Run.Api`
- `Chummer.Run.Identity`
- `Chummer.Run.Registry`
- `Chummer.Run.AI`

These projects are the active hosted runtime boundary for registry, relay,
Spider, media orchestration, identity, and policy surfaces.

External owner packages consumed by this repo, but no longer treated as active
hosted projects here:

- `Chummer.Media.Contracts` from `chummer6-media-factory`
- `Chummer.Hub.Registry.Contracts` from `chummer6-hub-registry`

No legacy oracle root is preserved inside this repo anymore.

Retired roots that must stay absent:

- `Chummer`
- `Chummer.Api`
- `ChummerDataViewer`
- `ChummerHub`
- `Plugins`
- `TextblockConverter`
- `Translator`

Boundary rules:

1. Active hosted projects must be the only in-repo projects built through `Chummer.Run.sln` and the clean-room verification path; external owner packages are restored through sibling-repo assembly seams.
2. No legacy oracle/application root may be reintroduced into this repo as a compatibility anchor.
3. Retired hosted clutter must stay absent from the repository and must not be reintroduced through source roots, project references, or docker paths.
4. Registry/publication ownership now lives in `chummer6-hub-registry`, media render/job contracts live in `chummer6-media-factory`, and this repo stays the orchestrator shell around identity, relay, Spider, and policy.
