# EDITION STUDIO

## The problem

One generic shell can technically support SR4, SR5, and SR6 while still making all three feel flattened.
That loses comprehension, atmosphere, and confidence exactly where the editions most need authored help.

## What it would do

EDITION STUDIO would give each promoted ruleset a deliberately authored head:

* distinct terminology, prompts, and inspector posture where semantics diverge
* ruleset-specific interaction patterns where a shared task becomes confusing or lossy
* visual language, motion, density, and emphasis that reflect each edition's mental model without fragmenting the product into separate apps

This feature is not about skinning for its own sake.
It is about preserving meaning through authored product expression.

## Likely owners

* `chummer6-ui`
* `chummer6-ui-kit`
* `chummer6-core`

## Tool posture

Design aids may support exploration, but source edition posture stays authored in the design system and product heads.
Rules state remains downstream of core semantics, never of styling.

## What has to be true first

* edition-specific semantic seams in core and explain
* shared primitives that can host ruleset-specific composition without forked chaos
* theming, typography, and motion tokens with explicit ownership
* acceptance evidence that the release shell already preserves the important edition differences

## Hard boundary

* not three disconnected apps
* not decorative theming without semantic payoff
* not ruleset flavor that contradicts engine state

## What is ready now

EDITION STUDIO is now a shipped first-party ruleset-head lane.

The public rail exposes a named ruleset-head detail plus SR4, SR5, and SR6 head bundles:

* `/edition-studio`
* `/edition-studio/details/ruleset-heads.json`
* `/edition-studio/bundles/sr4_head.md`
* `/edition-studio/bundles/sr4_head.json`
* `/edition-studio/bundles/sr5_head.md`
* `/edition-studio/bundles/sr5_head.json`
* `/edition-studio/bundles/sr6_head.md`
* `/edition-studio/bundles/sr6_head.json`

The signed-in rail now has named edition-focus aliases:

* `/account/edition-studio`
* `/account/edition-studio/open`
* `/account/edition-studio/{edition}`

Typed edition-head APIs are first-class too:

* `/api/v1/campaign-spine/me/edition-studio/heads`
* `/api/v1/campaign-spine/me/edition-studio/heads/{edition}`

This shipped slice keeps authored SR4, SR5, and SR6 posture readable without turning styling into state authority or splitting the product into disconnected apps.
