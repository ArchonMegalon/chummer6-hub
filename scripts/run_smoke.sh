#!/usr/bin/env bash
set +e

python3 -m unittest -v tests/test_stack_smoke.py
tests_rc=$?

python3 scripts/smoke_stack.py
live_rc=$?

if [ "$tests_rc" -ne 0 ] || [ "$live_rc" -ne 0 ]; then
  exit 1
fi
exit 0
