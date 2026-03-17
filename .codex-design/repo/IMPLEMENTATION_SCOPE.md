# Hub implementation scope

## Mission

`chummer6-hub` owns hosted orchestration, play API aggregation, identity, approvals, memory, and orchestration-side automation for Chummer6.

## Owns

* hosted orchestration and relay seams
* identity, approvals, memory, and delivery on the hosted side
* play API aggregation and hosted session coordination
* orchestration-side Coach/Spider/Director surfaces
* hosted external-integration routing that is not render-only media execution

## Must not own

* engine or reducer truth
* player/GM/mobile shell UX
* shared UI-kit primitives
* long-term registry persistence ownership after the registry split
* long-term render execution ownership after the media-factory split

## Package boundary

Canonical hosted package plane:

* `Chummer.Play.Contracts`
* `Chummer.Run.Contracts`

Mixed contract planes are temporary debt, not acceptable end state.

## Boundary truth

Closing `A2`, `A3`, `C0`, and `C1` requires physical shrinkage, not only correct README wording.

The hub boundary is only considered clean when:

* registry persistence authority is visibly owned by `chummer6-hub-registry`
* render-only media execution is visibly owned by `chummer6-media-factory`
* hub no longer reads like the hidden super-repo for every hosted concern
* active worklists highlight hosted implementation work instead of reconciliation churn

## Current reality

The mission statement is correct.
The repo body still carries more authority than the mission statement allows.

This repo should keep shrinking until the tree looks like the boundary story sounds.
