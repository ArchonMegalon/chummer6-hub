# Public auth flow

## Purpose

This file defines the first-wave guest-to-registered entry flow for `chummer.run`.

It exists so the landing, Hub account shell, and participation entry do not invent contradictory auth posture.

## Canonical route split

Public auth routes:

* `/login`
* `/signup`
* `/logout`
* `/auth/email/start`
* `/auth/email/callback`
* `/auth/google/start`
* `/auth/google/callback`

Registered routes:

* `/home`
* `/account`
* `/participate/codex`

## Guest fallback rules

* guest access to `/home` must redirect or fall back to `/login?next=/home`
* guest access to `/account` must redirect or fall back to `/login?next=/account`
* guest access to `/participate/codex` must redirect or fall back to `/login?next=/participate/codex`
* `/participate` remains the public explainer and must not require sign-in

## First-wave implemented posture

Enabled now:

* email or magic-link style entry
* basic browser session for the hosted shell

Allowed next when real provider credentials exist:

* Google sign-in

Deferred from first wave:

* Facebook as a visible signup default
* arbitrary user-provided Telegram bots

## Provider language rule

Provider names do not belong on the landing hero, proof shelf, horizon cards, or generic product pitch.

Provider names may appear on:

* `/login`
* `/signup`
* `/account`
* dedicated account-security or linked-identity surfaces

## Preview honesty rule

If a provider route exists before the full adapter is configured, the route must still explain:

* what the route is for
* whether it is enabled in the current build
* what the current fallback is

The route must not pretend the provider is already live.
