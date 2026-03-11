# Desktop Downloads Staging

This directory is mounted into `chummer-portal` at `/app/downloads`.

Expected contents:

- `releases.json`
- `files/`
- desktop artifacts under `files/` (for example `chummer-avalonia-win-x64.zip` and `chummer-blazor-desktop-linux-x64.tar.gz`)

The portal serves `/downloads/releases.json` from this directory and resolves
`/downloads/files/<artifact>` from the same root.

Published portal builds do not ship the checked-in `Chummer.Portal/downloads`
snapshot. This mounted directory is the production source of truth for
`/downloads/*`.

Populate this directory from the `desktop-download-bundle` artifact produced by
`.github/workflows/desktop-downloads-matrix.yml`, or use:

```bash
bash scripts/runbook.sh downloads-sync
```

If repository variable `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR` is configured,
Docker-branch workflow runs can publish this bundle automatically.
