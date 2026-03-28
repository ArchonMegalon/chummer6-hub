# Active Head Release Artifacts

Purpose: make the release outputs for the active Chummer heads explicit, reproducible, and easy to deploy from CI.

## Workflow

Use GitHub workflow `Desktop Downloads Matrix`.

On `main`, the workflow now produces first-class artifacts for:

- API: `release-api-portable`
- Avalonia desktop RIDs: `desktop-avalonia-*`
- Blazor desktop RIDs: `desktop-blazor-desktop-*`
- portal/self-hosted download shelf: `desktop-download-bundle`

## Artifact layout

`release-api-portable`

- archive: `chummer-run-api-portable.tar.gz`
- contents: published `Chummer.Run.Api` output, including static web assets and config-ready binaries
- deployment shape: extract on the target host and run `dotnet Chummer.Run.Api.dll` with the environment variables already documented in repo runbooks

`desktop-avalonia-*`

- one RID-specific desktop archive per target runtime
- produced from `Chummer.Avalonia/Chummer.Avalonia.csproj`

`desktop-blazor-desktop-*`

- one RID-specific desktop archive per target runtime
- produced from `Chummer.Blazor.Desktop/Chummer.Blazor.Desktop.csproj`

`desktop-download-bundle`

- compatibility manifest `releases.json`
- registry companion manifest `RELEASE_CHANNEL.generated.json`
- self-hosted files under `files/`

## Deployment notes

- Use [`docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md`](SELF_HOSTED_DOWNLOADS_RUNBOOK.md) for portal/download deployment and verification.
- Use `release-api-portable` when you need to deploy the hosted API separately from the desktop shelf.
- Treat the API archive and the desktop/download artifacts as the same release train input; do not hand-build one while promoting the other.
