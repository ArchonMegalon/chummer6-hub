# EDITION STUDIO

EDITION STUDIO keeps SR4, SR5, and SR6 readable as distinct product heads instead of flattening every ruleset into one generic shell.

## Current stage

- Today: Shipped first-party ruleset-head lane.
- Next: Flagship depth hardening.

## Why this matters

One shared shell can technically support multiple editions while still erasing the mental-model differences that make those editions usable and trustworthy.

## What it does now

EDITION STUDIO turns the existing ruleset seams into a named first-party lane.

The public lane is live at `https://chummer.run/edition-studio`.
The named receipt lane is live at `https://chummer.run/edition-studio/receipts/ruleset-heads.json`.
The signed-in edition desk is live at `https://chummer.run/account/edition-studio`.

Public-safe packets are readable too:

* `/edition-studio/packets/sr4_head.md`
* `/edition-studio/packets/sr4_head.json`
* `/edition-studio/packets/sr5_head.md`
* `/edition-studio/packets/sr5_head.json`
* `/edition-studio/packets/sr6_head.md`
* `/edition-studio/packets/sr6_head.json`

Typed edition-head APIs are live:

* `/api/v1/campaign-spine/me/edition-studio/heads`
* `/api/v1/campaign-spine/me/edition-studio/heads/{edition}`

## Boundary

EDITION STUDIO is a first-party ruleset-head lane.
It does not make styling into rules truth, split the product into three disconnected apps, or use flavor to overrule the core engine.
