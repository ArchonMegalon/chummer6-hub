# Windows Visual Proof Handoff

Generated: 2026-07-12T18:47:53Z

- Status: `ready_for_windows_host`
- Gate summary: Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.; Windows installer visual proof artifactDigest does not match promoted installer bytes.
- Only blocker is visual proof: `True`
- Channel: `preview`
- Version: `run-20260712-174412`
- Shelf root: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
- Handoff only: `True`
- Stable release unchanged: `True`
- Separate publish lane required: `True`

## Installer

- Artifact: `avalonia-win-x64-installer`
- File: `chummer-avalonia-win-x64-installer.exe`
- URL: `https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe`
- SHA-256: `sha256:d0857d0a6e5c958f34117051669373444b785f683e701c3e0ae428abef36e8ca`
- Payload: `chummer-avalonia-win-x64-payload.zip`
- Payload URL: `https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip`

### Local installer bytes found

- `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/files/chummer-avalonia-win-x64-installer.exe`

### Local payload bytes found

- `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/files/chummer-avalonia-win-x64-payload.zip`

## Startup smoke already present

- Status: `pass`
- Version: `run-20260712-174412`
- Release version: `run-20260712-174412`
- Receipt: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json`
- Host class: `local-win-x64`
- Matches release candidate: `True`
- Matches installer file: `True`
- Matches installer digest: `True`
- Progress log: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/startup-smoke/windows-installer-progress-avalonia-win-x64.log`
- Progress log present: `True`

## Current visual proof state

- Exists: `True`
- Status: `pass`
- Version: `run-20260627-005402`
- Digest: `sha256:d9d25b2c93dbd4887590b52b03431c4aba3c5614dbc4b18ec2f282222067466c`
- Matches release candidate: `False`
- Matches installer digest: `False`
- Stale: `True`

## Required screenshots

- `progress`: `windows-installer-progress.png` -> `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/windows-installer-visual-proof/windows-installer-progress.png`
- `completion`: `windows-installer-completion.png` -> `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/windows-installer-visual-proof/windows-installer-completion.png`

## Gate reasons

- Windows installer visual proof version does not match release channel.
- Windows installer visual proof artifactDigest does not match promoted installer bytes.

## Blockers

- none

## Next actions

- Overwrite the stale Windows visual-proof receipt at `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json`; its recorded release or installer digest no longer matches the staged candidate.
- On a real Windows host, open the repo checkout that contains the capture script and run `powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\capture-windows-installer-visual-proof.ps1 -ReleaseChannelPath "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json" -OutputPath "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"`.
- Confirm `windows-installer-progress.png` and `windows-installer-completion.png` are written under `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/windows-installer-visual-proof`.
- Confirm `WINDOWS_INSTALLER_VISUAL_PROOF.generated.json` is written under `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`.
- Rerun the Windows exit gate against the same shelf: `CHUMMER_WINDOWS_RELEASE_CHANNEL_PATH="/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json" CHUMMER_WINDOWS_LOCAL_DESKTOP_FILES_ROOT="/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/files" CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH="/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json" bash /docker/chummercomplete/chummer-presentation-release-20260712/scripts/materialize-windows-desktop-exit-gate.sh`.
- This packet is handoff-only for the staged nightly bytes. It does not publish the live downloads shelf or change the stable channel.
