# Generic review checklist

## Hosted boundary focus
- Flag duplicate engine event semantics or reducer truth recreated in run-services as P1.
- Flag registry persistence internals that should move to `chummer6-hub-registry` as P1.
- Flag media render internals that should move to `chummer6-media-factory` as P1.
- Flag play API changes that bypass `Chummer.Play.Contracts` ownership as P1.
- Flag service DTOs that leak provider internals, policy secrets, or approval internals as P1.
