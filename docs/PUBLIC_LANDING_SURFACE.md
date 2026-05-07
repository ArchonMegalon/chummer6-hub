# Public Landing Surface

`chummer.run` is the public product front door, proof shelf, and invitation surface for Chummer.

## Canonical split

- `chummer6-design` owns landing structure, copy constraints, route map, feature registry, user model, and media briefs.
- `chummer6-hub` projects that canon on the hosted surface.
- `Chummer6` remains the richer downstream explainer and guide.
- `fleet` may publish or synchronize downstream public artifacts, but it does not own landing meaning.

## Current hosted routes

Front-door and proof rails:

- `/`
- `/what-is-chummer`
- `/now`
- `/downloads`
- `/status`
- `/progress`
- `/artifacts`

Direction, signal, and shipped-closeout rails:

- `/horizons` for the deeper readiness shelf
- `/roadmap` for milestone-backed public direction
- `/feedback` for safe public signal and votes
- `/changelog` for shipped closeout
- `/participate`
- `/participate/karma-forge`
- `/participate/karma-forge/submitted/{submissionId}`
- `/feedback/operations`
- `/feedback/operations/lookup`

Help, policy, and signed-in overlays:

- `/help`
- `/faq`
- `/privacy`
- `/terms`
- `/contact`
- `/contact/submitted/{caseId}`
- `/login`
- `/signup`
- `/logout`
- `/home`
- `/account`

`/participate/codex` remains the deeper preview booster flow behind the friendlier participate entry page.
Guest access to `/home` and `/account` should fall back to `/login?next=...` rather than asking users to paste bearer tokens into product pages.
Guest access to `/participate/codex` should fall back to `/auth/google/start?next=...` because the guided contribution console begins on the signed-in authorization rail.
`/horizons` and `/roadmap` are intentionally separate: horizons stay the deeper readiness shelf, while roadmap stays the public milestone and direction rail.
`/feedback`, `/roadmap`, and `/changelog` are also intentionally separate so public signal, projected movement, and shipped proof do not collapse into one vague route family.

## Source of truth

The hosted landing surface reads mirrored design canon from:

- `.codex-design/product/PUBLIC_LANDING_MANIFEST.yaml`
- `.codex-design/product/PUBLIC_FEATURE_REGISTRY.yaml`
- `.codex-design/product/PUBLIC_LANDING_ASSET_REGISTRY.yaml`
- `.codex-design/product/PUBLIC_PROGRESS_PARTS.yaml`
- `.codex-design/product/PROGRESS_REPORT.generated.json`
- `.codex-design/product/PROGRESS_REPORT.generated.html`
- `.codex-design/product/PROGRESS_REPORT_POSTER.svg` for the generated progress report export only
- related mirrored public-surface canon files

The hosted surface must not invent a second feature map or public route story.
The guest shell must expose both `Sign in` and `Create account`, and the media layer must come from canonical asset slots rather than raw scene-family labels.
The raster-only campaign rule applies to public front-door imagery, not to generated progress-report exports.

## Public versus registered

Public visitors get:

- product story
- proof shelf
- progress report
- shipped closeout
- horizons
- roadmap projection
- public feedback
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

Thin overlays are acceptable in the early-access shell, but the split must remain obvious.
Public cards should land on deliberate first-party routes by default; self-linking cards are only acceptable when they are explicitly teaser-only, and any external fallback should be labeled honestly.

## Public copy rules

- do not lead with repo jargon
- do not name providers or LTDs
- do not show empty placeholder boxes
- explain what is real today and what is coming next
- keep participation language user-facing (`participate`, `guided contribution`) before operator-facing
- do not leak operator terms like `Fleet`, `device-code auth`, or `worker host` on landing-adjacent public pages
