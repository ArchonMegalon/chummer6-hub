# Windows Visual Proof Handoff

Generated: 2026-07-01T23:20:48Z

- Status: `needs_review`
- Gate summary: Windows desktop exit gate passed.
- Only blocker is visual proof: `False`
- Channel: `preview`
- Version: `run-20260701-124648`
- Shelf root: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
- Handoff only: `True`
- Stable release unchanged: `True`
- Separate publish lane required: `True`

## Installer

- Artifact: `avalonia-win-x64-installer`
- File: `chummer-avalonia-win-x64-installer.exe`
- URL: `https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe`
- SHA-256: `sha256:4d14c414fcd46f4cf5d2b06ac12d02d8492431f19924bffa97390af5f1c68bf3`
- Payload: `chummer-avalonia-win-x64-payload.zip`
- Payload URL: `https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip`

### Local installer bytes found

- `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/files/chummer-avalonia-win-x64-installer.exe`
- `/docker/chummercomplete/chummer-presentation/Docker/Downloads/files/chummer-avalonia-win-x64-installer.exe`

### Local payload bytes found

- `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/files/chummer-avalonia-win-x64-payload.zip`
- `/docker/chummercomplete/chummer-presentation/Docker/Downloads/files/chummer-avalonia-win-x64-payload.zip`

## Startup smoke already present

- Status: `pass`
- Version: `run-20260701-124648`
- Release version: `run-20260701-124648`
- Receipt: `/docker/chummercomplete/chummer6-ui/Docker/Downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json`
- Host class: `local-win-x64`
- Matches release candidate: `True`
- Matches installer file: `True`
- Matches installer digest: `True`
- Progress log: `/docker/chummercomplete/chummer6-ui/Docker/Downloads/startup-smoke/windows-installer-progress-avalonia-win-x64.log`
- Progress log present: `True`

## Current visual proof state

- Exists: `True`
- Status: `pass`
- Version: `run-20260701-124648`
- Digest: `sha256:4d14c414fcd46f4cf5d2b06ac12d02d8492431f19924bffa97390af5f1c68bf3`
- Matches release candidate: `True`
- Matches installer digest: `True`
- Stale: `False`

## Required screenshots

- `progress`: `windows-installer-progress.png` -> `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/windows-installer-visual-proof/windows-installer-progress.png`
- `completion`: `windows-installer-completion.png` -> `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/windows-installer-visual-proof/windows-installer-completion.png`

## Gate reasons

- none

## Blockers

- none

## Next actions

- Refresh the existing Windows visual-proof receipt at `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json` against the staged candidate before the nightly handoff continues.
- On a real Windows host, open the repo checkout that contains the capture script and run `powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\capture-windows-installer-visual-proof.ps1 -ReleaseChannelPath "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json" -OutputPath "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"`.
- Confirm `windows-installer-progress.png` and `windows-installer-completion.png` are written under `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/windows-installer-visual-proof`.
- Confirm `WINDOWS_INSTALLER_VISUAL_PROOF.generated.json` is written under `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`.
- Rerun the Windows exit gate against the same shelf: `CHUMMER_WINDOWS_RELEASE_CHANNEL_PATH="/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json" CHUMMER_WINDOWS_LOCAL_DESKTOP_FILES_ROOT="/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/files" CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH="/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json" bash /docker/chummercomplete/chummer-presentation/scripts/materialize-windows-desktop-exit-gate.sh`.
- This packet is handoff-only for the staged nightly bytes. It does not publish the live downloads shelf or change the stable channel.
