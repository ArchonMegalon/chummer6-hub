# Release Build Handoff

Generated: 2026-07-12T18:47:53Z

- Stage dir: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
- Channel: `preview`
- Version: `run-20260712-174412`
- Artifact count: `2`
- Handoff only: `True`
- Handoff scope: `staged_nightly`
- Stage proof complete: `False`
- Stable release unchanged: `True`
- Separate publish lane required: `True`

## Artifacts

- `avalonia-linux-x64-installer` -> `chummer-avalonia-linux-x64-installer.deb` (linux / linux-x64)
- `avalonia-win-x64-installer` -> `chummer-avalonia-win-x64-installer.exe` (windows / win-x64)

## Startup Smoke

- `avalonia:linux:linux-x64`: `pass`
- `avalonia:windows:win-x64`: `pass`

## Windows Exit Gate Refresh

- Status: `failed`
- JSON: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json`
- Script: `/docker/chummercomplete/chummer-presentation-release-20260712/scripts/materialize-windows-desktop-exit-gate.sh`
- Blocking mode: `mixed_or_local`
- Summary: Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.; Windows installer visual proof artifactDigest does not match promoted installer bytes.

## Windows Visual Proof Handoff

- Status: `ready_for_windows_host`
- JSON: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json`
- Markdown: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.md`
- Visual proof receipt target: `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json`
- Summary: Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.; Windows installer visual proof artifactDigest does not match promoted installer bytes.

## Remaining Blockers

- Windows visual proof is still outstanding for the staged installer bytes.

## Next Actions

- Use the Windows visual-proof handoff packet to capture progress and completion screenshots for the staged installer bytes: /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json
- Keep the live downloads shelf and stable channel unchanged while this staged nightly handoff is still incomplete.
