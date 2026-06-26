# LOCAL CO-PROCESSOR

## What is ready now

LOCAL CO-PROCESSOR now ships a bounded first-party optional-acceleration lane.

The public capability route, policy record, bundle rails, signed-in profile desk, and typed capability/policy APIs are real.

## The problem

Some explain, search, and media-assist workloads would be cheaper, faster, or more private with optional local acceleration, but the product cannot require every user to run local compute.

## What it does now

Chummer allows optional local acceleration or lightweight host strategies where they improve responsiveness, privacy, or cost.
The same tasks still function in cloud-only mode, and no source state depends on local runtime availability.

It currently ships:

* a public route at `/local-co-processor`
* a named detail at `/local-co-processor/details/optional-acceleration.json`
* bundle rails for capability and policy posture
* a signed-in profile desk at `/account/local-co-processor`
* typed capability and policy APIs

The lane is cloud-first.
Optional local acceleration is a bounded profile choice, not a hidden dependency or a second product.

## Live routes

* `/local-co-processor`
* `/local-co-processor/details/optional-acceleration.json`
* `/local-co-processor/bundles/capability_matrix.md`
* `/local-co-processor/bundles/capability_matrix.json`
* `/local-co-processor/bundles/policy_boundary.md`
* `/local-co-processor/bundles/policy_boundary.json`
* `/account/local-co-processor`
* `/account/local-co-processor/open`
* `/account/local-co-processor/{profile}`
* `/api/v1/campaign-spine/me/local-co-processor/capabilities`
* `/api/v1/campaign-spine/me/local-co-processor/policy`

## Likely owners

* `chummer6-hub`
* `chummer6-core`
* `chummer6-ui`
* `chummer6-mobile`

## Key tool posture

* no mandatory external tool
* optional acceleration helpers only when they stay invisible, optional, and reversible

## What has to be true first

* portable deterministic engine host strategy
* cloud-first parity
* explicit non-mandatory local runtime policy
* disableable local acceleration paths

## Hard boundary

* not a hidden local-runtime requirement
* not a local state owner
* not a provider-dependent black box
* not a product split where cloud users lose capability
