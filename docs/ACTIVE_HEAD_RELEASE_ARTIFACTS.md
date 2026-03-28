# Public Edge Release Artifacts

Purpose: make the hub-owned release outputs explicit, reproducible, and easy to deploy from CI without pretending this repo still source-builds the desktop heads it no longer owns.

## Workflow

Use GitHub workflow `Public Edge Release Artifacts`.

On `main`, the workflow now produces first-class artifacts for:

- API: `release-api-portable`
- public/self-hosted download shelf: `desktop-download-bundle`

## Artifact layout

`release-api-portable`

- archive: `chummer-run-api-portable.tar.gz`
- contents: published `Chummer.Run.Api` output, including static web assets and config-ready binaries
- deployment shape: extract on the target host and run `dotnet Chummer.Run.Api.dll` with the environment variables already documented in repo runbooks

`desktop-download-bundle`

- compatibility manifest `releases.json`
- registry companion manifest `RELEASE_CHANNEL.generated.json`
- self-hosted files under `files/`
- sourced from the checked-in public download mirror under `Chummer.Portal/downloads/` and restamped in CI so deploy jobs verify the same manifest shape the live shelf serves

## Deployment notes

- Use [`docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md`](SELF_HOSTED_DOWNLOADS_RUNBOOK.md) for portal/download deployment and verification.
- Use `release-api-portable` when you need to deploy the hosted API separately from the desktop shelf.
- Treat the API archive and the downloads mirror bundle as the same release-train evidence for this repo.
- Desktop binaries themselves are boundary-external inputs here: Hub serves and verifies the shelf, but it does not source-build Avalonia or Blazor desktop heads in this repo.
