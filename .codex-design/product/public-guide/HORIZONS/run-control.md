# RUN CONTROL

A GM can keep session board, active scene, reconnect continuity, and recap follow-through on one first-party rail instead of scattering them across notes and chat.

## Current stage

- Today: Shipped first-party GM operations lane.
- Next: Flagship depth hardening.

## Why this matters

Even when character tools are good, many campaigns still fall back to notebooks, memory, chat logs, and ad hoc recaps to actually run a session.

## What it does now

RUN CONTROL turns the existing campaign spine into a named GM operations surface.

The public lane is live at `https://chummer.run/run-control`.
The named receipt lane is live at `https://chummer.run/run-control/receipts/control-network.json`.
The signed-in control desk is live at `https://chummer.run/account/run-control`.

Public-safe packets are readable too:

* `/run-control/packets/session_board.md`
* `/run-control/packets/session_board.json`
* `/run-control/packets/continuity_board.md`
* `/run-control/packets/continuity_board.json`

Typed GM-control APIs are live:

* `/api/v1/campaign-spine/me/run-control/dashboard`
* `/api/v1/campaign-spine/me/run-control/runs/{runId}`

## Boundary

RUN CONTROL is a first-party GM operations lane.
It does not replace the rules engine, become a generic collaboration suite, or let hidden state outrank campaign truth.
