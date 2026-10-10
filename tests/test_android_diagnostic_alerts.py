import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from datetime import datetime, timezone

SPEC = importlib.util.spec_from_file_location('alerts', Path(__file__).resolve().parents[1] / 'scripts/android_diagnostic_alerts.py')
alerts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(alerts)


class DiagnosticAlertsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'
        self.now = 1791568800.0
        self.sent = []
        self.verified = 0

    def verify(self):
        self.verified += 1

    def report(self, now=None, **changes):
        stamp = datetime.fromtimestamp(now or self.now, timezone.utc).isoformat()
        value = dict(reportId=str(uuid.uuid4()), versionCode=165, observedAtUtc=stamp,
            area=2, operation=2, outcome=0, elapsedMilliseconds=70, error=3)
        value.update(changes)
        return {'report':value, 'receivedAtUtc':stamp}

    def cycle(self, rows, now=None, send=None, verify=None):
        return alerts.cycle(self.path, {'items':rows}, now or self.now, verify or self.verify,
                            send or self.sent.append)

    def test_first_poll_baselines_existing_and_does_not_replay(self):
        row = self.report()
        self.assertEqual('baseline', self.cycle([row]))
        self.assertEqual('quiet', self.cycle([row], self.now + 60))
        self.assertEqual([], self.sent)
        self.assertEqual(0, self.verified)

    def test_only_allowlisted_summary_and_count_is_sent(self):
        self.cycle([])
        row = self.report()
        self.assertEqual('sent', self.cycle([row]))
        self.assertEqual(1, self.verified)
        self.assertIn('Life Modules', self.sent[0])
        self.assertIn('Reload', self.sent[0])
        self.assertNotIn(row['report']['reportId'], self.sent[0])
        self.assertNotIn('observedAtUtc', self.sent[0])
        self.assertNotIn(row['report']['reportId'], self.path.read_text())
        self.assertEqual('quiet', self.cycle([row], self.now + 901))
        self.assertEqual(1, len(self.sent))

    def test_unknown_send_persists_claim_before_network_and_never_replays(self):
        self.cycle([])
        row = self.report()
        def fail(_):
            self.assertEqual('claimed', json.loads(self.path.read_text())['lastOutcome'])
            raise TimeoutError('secret URL must never be surfaced')
        self.assertEqual('send_unknown_no_replay', self.cycle([row], send=fail))
        self.assertEqual('unknown', json.loads(self.path.read_text())['lastOutcome'])
        self.assertEqual('quiet', self.cycle([row], self.now + 901))
        self.assertEqual([], self.sent)

    def test_receiver_reset_preserves_sent_and_uncertain_claims_across_worker_restart(self):
        for uncertain in (False, True):
            with self.subTest(uncertain=uncertain):
                self.path = Path(self.tmp.name) / f'reset-{uncertain}.json'
                callbacks = []
                self.cycle([])
                first, second = self.report(), self.report(self.now + 901)

                def send_first(message):
                    callbacks.append(message)
                    if uncertain:
                        raise TimeoutError('synthetic uncertain result')

                expected = 'send_unknown_no_replay' if uncertain else 'sent'
                self.assertEqual(expected, self.cycle([first], send=send_first))
                self.assertEqual('quiet', self.cycle([], self.now + 60))
                self.assertEqual('sent', self.cycle([second], self.now + 901, send=callbacks.append))
                # New module, same private state: no process-local memory may
                # protect the claim after a restart and receiver resubmission.
                restarted = importlib.util.module_from_spec(SPEC)
                SPEC.loader.exec_module(restarted)
                self.assertEqual('quiet', restarted.cycle(self.path, {'items':[first]},
                    self.now + 1802, self.verify, callbacks.append))
                self.assertEqual(2, len(callbacks))
                self.assertEqual(2, len(json.loads(self.path.read_text())['seen']))

    def test_baseline_ids_survive_receiver_reset(self):
        first = self.report()
        self.cycle([first])
        self.cycle([], self.now + 60)
        self.assertEqual('sent', self.cycle([self.report(self.now + 901)], self.now + 901))
        self.assertEqual('quiet', self.cycle([first], self.now + 1802))
        self.assertEqual(1, len(self.sent))

    def test_claims_expire_only_at_retention_boundary_without_refresh_on_reappearance(self):
        self.cycle([])
        first, second = self.report(), self.report(self.now + 901)
        self.cycle([first])
        first_digest = next(iter(json.loads(self.path.read_text())['seen']))
        self.cycle([second], self.now + 901)
        # A fresh receiver receipt must not extend the worker's existing claim.
        first['receivedAtUtc'] = datetime.fromtimestamp(self.now + alerts.TTL, timezone.utc).isoformat()
        self.assertEqual('quiet', self.cycle([first], self.now + alerts.TTL))
        self.assertEqual(self.now, json.loads(self.path.read_text())['seen'][first_digest])
        self.assertEqual('quiet', self.cycle([first], self.now + alerts.TTL + 1))
        seen = json.loads(self.path.read_text())['seen']
        self.assertNotIn(first_digest, seen)
        self.assertEqual(1, len(seen))
        self.assertEqual(2, len(self.sent))

    def test_saturation_defers_batch_without_discarding_unexpired_claims(self):
        old = [self.report() for _ in range(alerts.MAX_REPORTS)]
        self.cycle(old)
        before = json.loads(self.path.read_text())
        self.assertEqual('dedup_saturated_no_send', self.cycle([self.report(self.now + 901)], self.now + 901))
        self.assertEqual(before, json.loads(self.path.read_text()))
        self.assertEqual([], self.sent)
        self.assertEqual(0, self.verified)
        self.assertEqual('quiet', self.cycle([old[0]], self.now + 1802))
        # Existing retention, not eviction or a larger bound, makes room.
        later = self.now + alerts.TTL + 1
        self.assertEqual('sent', self.cycle([self.report(later)], later))
        self.assertEqual(1, len(json.loads(self.path.read_text())['seen']))
        self.assertEqual(1, len(self.sent))

    def test_exact_capacity_claim_is_durable_before_sending(self):
        self.cycle([self.report() for _ in range(alerts.MAX_REPORTS - 1)])
        existing = json.loads(self.path.read_text())['seen']

        def send(message):
            claimed = json.loads(self.path.read_text())
            self.assertEqual('claimed', claimed['lastOutcome'])
            self.assertEqual(alerts.MAX_REPORTS, len(claimed['seen']))
            self.assertTrue(existing.items() <= claimed['seen'].items())
            self.sent.append(message)

        self.assertEqual('sent', self.cycle([self.report()], send=send))
        self.assertEqual(1, len(self.sent))

    def test_saturation_does_not_partially_claim_a_batch(self):
        self.cycle([self.report() for _ in range(alerts.MAX_REPORTS - 1)])
        before = self.path.read_bytes()
        self.assertEqual('dedup_saturated_no_send', self.cycle([self.report(), self.report()]))
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(0, self.verified)
        self.assertEqual([], self.sent)

    def test_failed_durable_claim_never_sends(self):
        self.cycle([])
        before = self.path.read_bytes()
        with patch.object(alerts, 'atomic_state', side_effect=OSError('synthetic full disk')):
            with self.assertRaises(OSError):
                self.cycle([self.report()])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([], self.sent)

    def test_unverified_recipient_never_consumes_reports(self):
        self.cycle([])
        before = self.path.read_bytes()
        def fail():
            raise ValueError('recipient_mismatch')
        with self.assertRaises(ValueError):
            self.cycle([self.report()], verify=fail)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([], self.sent)

    def test_cooldown_survives_restart_and_later_batch_aggregates(self):
        self.cycle([])
        first, second = self.report(), self.report()
        self.cycle([first])
        self.assertEqual('quiet', self.cycle([first, second], self.now + 60))
        self.assertEqual('sent', self.cycle([first, second], self.now + 901))
        self.assertIn('1 new reports', self.sent[1])

    def test_twelve_per_day_bound(self):
        self.cycle([])
        for index in range(12):
            now = self.now + index * 1000
            self.assertEqual('sent', self.cycle([self.report(now)], now))
        self.assertEqual('quiet', self.cycle([self.report(self.now+12000)], self.now+12000))
        self.assertEqual(12, len(self.sent))

    def test_raw_text_and_unknown_enums_are_rejected(self):
        for fields in ({'text':'runner story'}, {'area':99}, {'outcome':True}, {'error':'secret'}, {'reportId':str(uuid.UUID(int=0))}):
            with self.subTest(fields=fields), self.assertRaises((ValueError, TypeError)):
                alerts.observations({'items':[self.report(**fields)]}, self.now)

    def test_expiry_and_collection_bounds(self):
        self.assertEqual({}, alerts.observations({'items':[self.report(self.now-alerts.TTL-1)]}, self.now))
        with self.assertRaises(ValueError):
            alerts.observations({'items':[self.report()] * 513}, self.now)
        row = self.report()
        with self.assertRaises(ValueError):
            alerts.observations({'items':[row, row]}, self.now)

    def test_slow_is_not_called_a_crash(self):
        rows = alerts.observations({'items':[self.report(outcome=1)]}, self.now)
        text = alerts.summary(rows)
        self.assertIn('not an ANR', text)
        self.assertNotIn('crash', text)

    def test_corrupt_or_public_state_fails_closed(self):
        self.path.write_text('{}')
        os.chmod(self.path, 0o600)
        with self.assertRaises(ValueError):
            self.cycle([self.report()])
        self.path.unlink()
        self.cycle([])
        os.chmod(self.path, 0o644)
        with self.assertRaises(ValueError):
            self.cycle([self.report()])
        self.assertEqual([], self.sent)

    def test_duplicate_json_keys_and_redirects_fail(self):
        with self.assertRaises(ValueError):
            alerts.decode('{"items":[],"items":[]}')
        with self.assertRaises(ValueError):
            alerts.NoRedirect().redirect_request(None, None, None, None, None, None)


if __name__ == '__main__':
    unittest.main()
