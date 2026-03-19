# Public Landing Surface

`chummer.run` is the public product front door, proof shelf, and invitation surface for Chummer.

## Canonical split

- `chummer6-design` owns landing structure, copy constraints, route map, feature registry, user model, and media briefs.
- `chummer6-hub` projects that canon on the hosted surface.
- `Chummer6` remains the richer downstream explainer and guide.
- `fleet` may publish or synchronize downstream public artifacts, but it does not own landing meaning.

## Current hosted routes

- `/`
- `/what-is-chummer`
- `/now`
- `/horizons`
- `/downloads`
- `/participate`
- `/status`
- `/artifacts`
- `/home`
- `/account`

`/participate/codex` remains the deeper preview booster flow behind the friendlier participate entry page.

## Source of truth

The hosted landing surface reads mirrored design canon from:

- `.codex-design/product/PUBLIC_LANDING_MANIFEST.yaml`
- `.codex-design/product/PUBLIC_FEATURE_REGISTRY.yaml`
- related mirrored public-surface canon files

The hosted surface must not invent a second feature map or public route story.

## Public versus registered

Public visitors get:

- product story
- proof shelf
- horizons
- downloads
- participate entry
- public status
- featured artifacts

Registered overlays may add:

- signed-in home
- account/profile
- follow and beta-interest overlays
- bounded participation state

Thin overlays are acceptable in the POC, but the split must remain obvious.

## Public copy rules

- do not lead with repo jargon
- do not name providers or LTDs
- do not show empty placeholder boxes
- explain what is real today and what is coming next
- keep participation language user-facing (`participate`, `booster`) before operator-facing
