# Absolute audit codexliz task

You are executing the remaining work from:
- [ABSOLUTE_AUDIT_EXECUTION_PLAN_20260508.md](/docker/chummercomplete/chummer.run-services/ABSOLUTE_AUDIT_EXECUTION_PLAN_20260508.md)

Completion is not based on your judgment.

Completion gate:
- run `python3 scripts/check_absolute_audit_closure.py`
- only stop when `"closure_done": true`

Operating rules:
- work the highest-priority pending checks first
- if one lane is blocked, implement the next dependency or close the next pending lane instead of stopping
- do not treat partial progress as completion
- do not mint synthetic `status: pass` receipts just to satisfy the closure checker
- every new proof receipt must be backed by a real probe, script run, or existing evidence file that the receipt cites concretely
- unsupported self-authored proof JSON does not count as completion and will be rejected by the closure gate
- for SR4 and SR6, the plan explicitly allows either acceptance proof or explicit claim retirement
- for SR5, close the audit either by real acceptance proof or by an explicit claim-boundary receipt if that is the chosen product posture
- before every final answer attempt, rerun `python3 scripts/check_absolute_audit_closure.py`

Priority order:
1. live `chummer.run` proof and canonical-domain closure
2. live Google OAuth/account-linking proof
3. live support/contact proof
4. fresh desktop execution proof
5. portable receipts audit
6. SR5 closure
7. SR4 closure
8. SR6 closure

Relevant repos:
- `/docker/chummercomplete/chummer.run-services`
- `/docker/chummercomplete/chummer-presentation`
- `/docker/chummercomplete/chummer-core-engine`
- `/docker/chummercomplete/chummer-design`
- `/docker/fleet/repos/chummer-media-factory`
- `/home/tibor` if you need the source audit zip
