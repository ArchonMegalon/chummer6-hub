# Desktop Downloads Staging

This directory is a compatibility staging area for the desktop download bundle.
Registry-owned release truth should be materialized here as `RELEASE_CHANNEL.generated.json` plus the compatibility `releases.json` when Hub needs a file-backed `/downloads` surface.

Expected contents:

- `RELEASE_CHANNEL.generated.json`
- `releases.json`
- `files/`
- desktop artifacts under `files/` (for example `chummer-avalonia-win-x64-installer.exe`, `chummer-avalonia-win-x64.exe`, and `chummer-blazor-desktop-linux-x64.tar.gz`)

Hub prefers `RELEASE_CHANNEL.generated.json` as the canonical registry-backed projection, serves `/downloads/releases.json` as the compatibility manifest, and resolves `/downloads/files/<artifact>` from the same root.

Published portal builds do not ship the checked-in `Chummer.Portal/downloads`
snapshot. This mounted directory is the deploy-time projection target for
registry-owned desktop release truth.

Populate this directory from the `desktop-download-bundle` produced by the
self-hosted release path, or use:

```bash
bash scripts/runbook.sh downloads-sync
```

If `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR` is configured, the local release
path can publish this bundle automatically.
