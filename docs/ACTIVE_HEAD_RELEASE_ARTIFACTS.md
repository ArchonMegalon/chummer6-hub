# Public Edge Release Files

Purpose: make the hub-owned release outputs explicit, reproducible, and easy to deploy from the self-hosted release machine without pretending this repo still source-builds the desktop heads it no longer owns.

## Build path

The release machine prepares first-class files for:

- API: `release-api-portable`
- public/self-hosted download page: `desktop-download-bundle`

## Artifact layout

`release-api-portable`

- archive: `chummer-run-api-portable.tar.gz`
- contents: published `Chummer.Run.Api` output, including static web assets and config-ready binaries
- deployment shape: extract on the target host and run `dotnet Chummer.Run.Api.dll` with the environment variables already documented in repo runbooks

`desktop-download-bundle`

- compatibility manifest `releases.json`
- registry companion manifest `RELEASE_CHANNEL.generated.json`
- self-hosted files under `files/`
- sourced from the checked-in public download mirror under `Chummer.Portal/downloads/` and restamped by the release script so deploy checks verify the same manifest shape the live download page serves

## Deployment notes

- Use [`docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md`](SELF_HOSTED_DOWNLOADS_RUNBOOK.md) for portal/download deployment and verification.
- Use `release-api-portable` when you need to deploy the hosted API separately from the desktop shelf.
- Treat the API archive and the downloads mirror bundle as the same release train for this repo.
- Desktop binaries themselves are boundary-external inputs here: Hub serves and verifies the shelf, but it does not source-build Avalonia or Blazor desktop heads in this repo.
