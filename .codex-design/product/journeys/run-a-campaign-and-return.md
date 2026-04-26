# Run a campaign and return

## Happy path

1. A runner starts as build truth, becomes a living dossier, and joins a crew or campaign without losing provenance.
2. During play, session, recap, and continuity state stay replay-safe enough that mobile, Hub, and later publication surfaces can all talk about the same run.
3. After the run, downtime, aftermath, heat, faction stance, contact truth, reputation movement, and next-session return actions land on the same campaign memory lane instead of splitting across recap prose, local notes, and support folklore.
4. The player or organizer can return to the same dossier, understand what changed, and continue from the next useful decision point instead of re-stitching memory from exports and chat logs.
4. Publication or recap artifacts can reference the same continuity spine without becoming the system of record.

## Product promises

Chummer treats campaign memory as first-class product truth.

That means:

* downtime is a governed action and scheduling lane, not only a diary note
* aftermath is a durable "what changed" packet, not only recap prose
* heat, faction stance, contact truth, and reputation are visible consequence state with explicit reasons
* next-session return actions compile from the same campaign memory instead of ad hoc reminders

## Truth order

When wording drifts, campaign memory outranks recap prose, publication copy, and local notes.

## Failure modes

* If reconnect or sync confidence breaks, the user must still recover the last stable campaign state without inventing a second truth source.
* If a recap or publication artifact disagrees with dossier or campaign state, the campaign spine must win and the artifact becomes a projection problem.
* If downtime, heat, faction, contact, or reputation consequences disagree across devices, the governed campaign-memory object must win and the stale surface becomes a projection problem.
* If a migration or compatibility seam fails, the product must preserve dossier and campaign identity rather than degrading back to orphan character files.

## Owning repos

* `chummer6-hub`
* `chummer6-mobile`
* `chummer6-core`
* `chummer6-ui`
* `chummer6-media-factory`
