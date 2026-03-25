# Publish a grounded artifact

Status: preview_to_horizon

## User goal

Turn a grounded Chummer output into a durable artifact without losing manifests, previews, or provenance.

## Entry surfaces

* media render requests and preview flows
* registry publication workflows
* Hub artifact and public-shelf projections

## Happy path

1. A grounded source pack, session output, or approved content package enters a media render lane.
2. Media Factory produces the artifact, manifest, previews, and media receipts as one coherent family.
3. Hub Registry records draft, review, publication, and compatibility state for the artifact.
4. Hub or downstream public surfaces project the published artifact from registry truth rather than from render-host folklore.

## Failure modes

* If render succeeds but manifest or provenance linkage is missing, the artifact must remain non-promoted.
* If publication state is invented outside registry ownership, the flow is invalid even if the bytes exist.
* If narration, formatting, or preview generation would sever the evidence chain, the output may stay draft or preview but must not become canonical truth.

## Success evidence

* Published artifacts preserve manifest, preview, and provenance links end to end.
* Media Factory owns rendering without reclaiming publication or install truth.
* Registry owns publication state without reclaiming render execution.

## Canonical owners

* `chummer6-media-factory`
* `chummer6-hub-registry`
* `chummer6-hub`
