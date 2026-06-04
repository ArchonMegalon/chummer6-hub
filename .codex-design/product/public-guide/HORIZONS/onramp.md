# ONRAMP

ONRAMP gives new or rusty users a real starter lane instead of dropping them into jargon, legality friction, and account recovery work with no guidance.

## Current stage

- Today: Shipped first-party starter and recovery lane.
- Next: Flagship depth hardening.

## Why this matters

The shortest path into Chummer still fails if the first session feels like setup theater, legalese, and broken recovery instead of a playable route.

## What it does now

ONRAMP turns the existing starter workspace and restore posture into a named first-party lane.

The public lane is live at `https://chummer.run/onramp`.
The named receipt lane is live at `https://chummer.run/onramp/receipts/guided-starter.json`.
The signed-in starter desk is live at `https://chummer.run/account/onramp`.

Public-safe packets are readable too:

* `/onramp/packets/starter_lane.md`
* `/onramp/packets/starter_lane.json`
* `/onramp/packets/recovery_lane.md`
* `/onramp/packets/recovery_lane.json`

Typed starter and recovery APIs are live:

* `/api/v1/campaign-spine/me/onramp/dashboard`
* `/api/v1/campaign-spine/me/onramp/starter`
* `/api/v1/campaign-spine/me/onramp/recovery`

## Boundary

ONRAMP is a first-party starter and recovery lane.
It does not auto-build characters, invent legality, or replace the deeper signed-in workbench with fake tutorial certainty.
