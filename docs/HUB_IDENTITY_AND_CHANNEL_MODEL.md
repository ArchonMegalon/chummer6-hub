# Hub Identity And Channel Model

`chummer6-hub` owns identity hygiene, account linking, permissions, and channel routing for public and signed-in hosted surfaces.

## Canonical split

- Hub owns accounts, linked identities, linked channels, permissions, groups, sponsorship sessions, rewards, and entitlements.
- EA remains the orchestrator brain for GM companion and assistant-style execution.
- Google, Facebook, Telegram, and email are adapters or hygiene layers. They do not become separate product pillars.
- Transactional email is a boring delivery dependency, not a reason to create a second AI/runtime stack.

## Linked identities

The hosted account plane distinguishes between:

- primary auth identities
- linked recovery identities
- linked social identities
- linked channel identities

Current supported identity families:

- `email`
- `google`
- `facebook`
- `telegram`

Current posture:

- email or magic-link signups require verification before they count as strong recovery posture
- Google is the preferred mainstream social bootstrap
- Facebook stays optional and demand-driven
- Telegram may be linked as identity, but it is not the account core

First-wave hosted-shell posture:

- `/login`, `/signup`, and `/logout` are the boring browser entry routes
- email-first entry is the currently live default
- Google routes may exist honestly before the adapter is fully configured
- Facebook and user-provided Telegram bots stay out of the first-wave account UI

## Channels versus identity

Do not conflate:

- signing in with Telegram
- talking to the official GM companion bot
- bringing a user-controlled Telegram bot

Those are different product lanes.

Current hosted posture:

- the official Telegram bot is the first-class companion channel
- bring-your-own Telegram bot is a future capability and should remain bounded until ownership verification, permissions, and auditability are stronger
- channel links are stored separately from linked identities

## EA posture

EA remains the orchestrator brain behind companion and assistant behavior because it already owns:

- principal-scoped execution
- approvals
- memory
- tool routing
- delivery policy

Hub should route channels and permissions into EA. It should not spawn a second orchestration brain for the GM companion.

## Current API surface

`Chummer.Run.Api` now exposes a minimal account-linking surface:

- `GET /api/v1/accounts/me/links`
- `POST /api/v1/accounts/me/links/email`
- `POST /api/v1/accounts/me/links/confirm`
- `/auth/google/link` for provider linking callbacks; the legacy `POST /api/v1/accounts/me/links/provider` surface remains retired and returns `410 Gone`
- `POST /api/v1/accounts/me/channels`

These endpoints define the product model first.
Actual mail delivery, provider callbacks, and channel transports remain adapter work that can land later without rewriting the account/community spine.
