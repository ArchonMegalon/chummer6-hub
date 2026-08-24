# Hub package plane v5 sealing

The reviewed lock is deliberately in `awaiting-pinned-ci-byte-authority` state.
That state is not deployable: normal feed materialization fails before network
access, and only the observation mode may build the remaining owner packages.

The `Hub package plane v5 byte authority` workflow is bootstrapped by the exact
`codex/hub-package-plane-v5-20260824` branch push (and remains manually
dispatchable after the workflow reaches the default branch). This avoids
merging an unsealed lock merely to make `workflow_dispatch` visible. It imports
the eight Core packages byte-for-byte from the digest-bound public Core
handoff, then builds exactly these seven packages from clean detached owner
commits with the pinned .NET SDK and toolchain:

- `Chummer.Hub.Registry.Contracts`
- `Chummer.Run.Registry`
- `Chummer.Play.Contracts`
- `Chummer.Run.Contracts`
- `Chummer.Campaign.Contracts`
- `Chummer.Control.Contracts`
- `Chummer.World.Contracts`

Its artifact contains those seven nupkgs and
`chummer-hub-packages.observed-authority.json`. The receipt binds the candidate
lock and recipe digests, source repositories/commits/projects, licenses,
dependency graph, Core release receipt and bundle, toolchain bytes, and every
observed package hash and size.

Do not set the lock to `sealed` in the observation commit. A separate reviewed
commit must:

1. verify the Actions run belongs to the observation workflow at the reviewed
   candidate commit;
2. replay the observation and require identical seven-package bytes;
3. verify the prelocked Registry contract row still matches;
4. replace only the six `pending_pinned_ci` rows with the reviewed hashes and
   sizes, then set the lock state to `sealed`;
5. regenerate NuGet lock files from only that sealed feed; and
6. pass the full no-siblings package-plane workflow and container preflight.

Until all six steps pass, the v5 package plane is a byte-authority candidate,
not a release package plane.
