# Run a campaign and return

## Happy path

1. A runner starts as build truth, becomes a living dossier, and joins a crew or campaign without losing provenance.
2. During play, session, recap, and continuity state stay replay-safe enough that mobile, Hub, and later publication surfaces can all talk about the same run.
3. After the run, the player or organizer can return to the same dossier, understand what changed, and continue from the next useful decision point instead of re-stitching memory from exports and chat logs.
4. Publication or recap artifacts can reference the same continuity spine without becoming the system of record.

## Failure modes

* If reconnect or sync confidence breaks, the user must still recover the last stable campaign state without inventing a second truth source.
* If a recap or publication artifact disagrees with dossier or campaign state, the campaign spine must win and the artifact becomes a projection problem.
* If a migration or compatibility seam fails, the product must preserve dossier and campaign identity rather than degrading back to orphan character files.

## Owning repos

* `chummer6-hub`
* `chummer6-mobile`
* `chummer6-core`
* `chummer6-ui`
* `chummer6-media-factory`
