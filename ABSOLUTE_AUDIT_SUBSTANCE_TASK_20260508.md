# Absolute audit substance codexliz task

You are reopening the absolute audit because the prior green close was not accepted as substantively complete.

The prior close is specifically rejected for these reasons:
- it removed `/participate/codex` from required live proof by setting `must_exist: false`
- the Google OAuth proof script is only a shallow route probe, not a meaningful linking proof
- the SR5 acceptance packet is too thin to support a serious implementation claim on its own

Completion is not based on your judgment.

Completion gate:
- run `python3 scripts/check_absolute_audit_substance.py`
- only stop when `"closure_done": true`

Non-negotiable rules:
- do not weaken the gate
- do not lower route requirements silently
- do not mint unsupported `status: pass` receipts
- every proof must be backed by real code, real probes, or real evidence files
- if you must retire a claim instead of implementing it, do it explicitly with a dedicated claim-retirement receipt and aligned product posture
- before every final answer attempt, rerun `python3 scripts/check_absolute_audit_substance.py`

Priority order:
1. restore honest `/participate/codex` truth in live proof and manifest alignment
2. make Google OAuth/account-linking proof materially stronger than simple route GETs
3. strengthen SR5 acceptance evidence or reduce the SR5 claim ceiling honestly
4. keep the other already-green lanes green while doing the above

Relevant repos:
- `/docker/chummercomplete/chummer.run-services`
- `/docker/chummercomplete/chummer-presentation`
- `/docker/chummercomplete/chummer-core-engine`
- `/docker/chummercomplete/chummer-design`
- `/docker/fleet/repos/chummer-media-factory`
- `/home/tibor` if you need the source audit zip
