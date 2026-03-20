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
- `/login`
- `/signup`
- `/logout`
- `/home`
- `/account`

`/participate/codex` remains the deeper preview booster flow behind the friendlier participate entry page.
Guest access to `/home`, `/account`, and `/participate/codex` should fall back to `/login?next=...` rather than asking users to paste bearer tokens into product pages.

## Source of truth

The hosted landing surface reads mirrored design canon from:

- `.codex-design/product/PUBLIC_LANDING_MANIFEST.yaml`
- `.codex-design/product/PUBLIC_FEATURE_REGISTRY.yaml`
- `.codex-design/product/PUBLIC_LANDING_ASSET_REGISTRY.yaml`
- related mirrored public-surface canon files

The hosted surface must not invent a second feature map or public route story.
The guest shell must expose both `Sign in` and `Create account`, and the media layer must come from canonical asset slots rather than raw scene-family labels.

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

The first-wave hosted shell uses a boring browser session cookie over the identity boundary so account and participation pages stop doubling as ad hoc auth entrypoints.

Thin overlays are acceptable in the POC, but the split must remain obvious.
Public cards should land on deliberate first-party routes by default; self-linking cards are only acceptable when they are explicitly teaser-only, and any external fallback should be labeled honestly.

## Public copy rules

- do not lead with repo jargon
- do not name providers or LTDs
- do not show empty placeholder boxes
- explain what is real today and what is coming next
- keep participation language user-facing (`participate`, `booster`) before operator-facing
- do not leak operator terms like `Fleet`, `device-code auth`, or `worker host` on landing-adjacent public pages
