# Hosted Boundary

`chummer6-hub` keeps its active hosted surface limited to:

- `Chummer.Play.Contracts`
- `Chummer.Media.Contracts`
- `Chummer.Run.Contracts`
- `Chummer.Run.Api`
- `Chummer.Run.Identity`
- `Chummer.Run.Registry`
- `Chummer.Run.AI`

These projects are the active hosted runtime boundary for registry, relay, Spider, media orchestration, identity, and policy surfaces.

The following roots remain outside the active hosted topology:

- Oracle root: `Chummer`
- Retired hosted clutter: `Chummer.Api`, `ChummerDataViewer`, `ChummerHub`, `Plugins/ChummerHub.Client`, `TextblockConverter`, `Translator`

Boundary rules:

1. Active hosted projects must be the only projects built through `Chummer.Run.sln` and the clean-room verification path.
2. The oracle root may remain for compatibility/reference work, but it must not re-enter `Chummer.Run.sln`.
3. Retired hosted clutter must stay absent from the repository and must not be reintroduced through source roots, project references, or docker paths.
4. Future extraction work still moves registry/publication ownership into `chummer6-hub-registry` and keeps this repo as the orchestrator shell around identity, relay, Spider, and policy.
