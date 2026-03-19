# Public user model

## Purpose

This file defines the user-facing model for `chummer.run` and adjacent public surfaces.
It is intentionally smaller than the internal identity, role, or moderation model.

## Current user classes

### Guest

A guest may:

* browse the landing page
* read the product story
* inspect what is real today
* inspect horizons
* open downloads
* view public status
* inspect featured artifacts and teasers
* open the participate entry page

### Registered user

A registered user may, in addition to guest behavior:

* access `/home`
* manage a lightweight account/profile
* follow or watch future horizons when that overlay is enabled
* raise beta-interest or waitlist intent
* enter the bounded participation / booster flow
* unlock future advisory-vote placeholders when enabled

## Profile flags

The first public profile pass should prefer flags over hard roles:

* `interested_in_play`
* `interested_in_gm_tools`
* `interested_in_creator_tools`
* `wants_horizon_updates`
* `wants_beta_invites`
* `booster_opt_in`

These flags may later inform richer roles or product lanes, but they are not a license to hardcode complex role UX into the POC.

## Future expansion

Future role expansion may introduce:

* GM
* Creator
* Moderator

That expansion must grow from the Hub account/community plane rather than from landing-page-only logic.

## Privacy rule

Public recognition remains opt-in.
Group-public and user-private combinations are allowed.
Landing and home surfaces must not force public identity merely to show interest, status, or future follow behavior.

## POC rule

The POC needs only:

* sign in
* basic profile
* follow/watchlist placeholders
* participate / booster entry
* future vote placeholder

Do not force a giant onboarding wizard or hard role selection up front.
