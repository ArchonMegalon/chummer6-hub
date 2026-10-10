#!/usr/bin/env python3
"""Private, bounded metadata-only alerts for the canonical Hub diagnostic inbox.

No account/runner/book data, raw reports or submission IDs leave Hub storage.
The scoped Telegram recipient is provisioned from a verified live EA binding.
Unknown send outcomes are never replayed. This is not fatal-crash/ANR capture.
"""
from __future__ import annotations

import collections
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.request
import uuid

TTL = 2 * 86400
MAX_BODY = 256 * 1024 + 128
MAX_REPORTS = 512
AREA = ('Other', 'Creation', 'Life Modules', 'Book', 'Account', 'Settings', 'Career')
OPERATION = ('Opening', 'Action', 'Reload', 'Story readiness')
OUTCOME = ('Failed', 'Slow observation (not an ANR)', 'Dispatch rejected')
ERROR = ('None', 'Network', 'Storage', 'Invalid state', 'Access', 'JSON', 'Other')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('redirect_refused')


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=strict_object)


def private_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('unsafe_private_file')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('private_file_too_large')
        return raw


def atomic_state(path, state):
    raw = json.dumps(state, separators=(',', ':')).encode()
    if len(raw) > 65536:
        raise ValueError('state_too_large')
    temporary = path.with_name('.'+path.name+'.pending')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('invalid_time')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('missing_timezone')
    return parsed.timestamp()


def observations(payload, now):
    if not isinstance(payload, dict) or set(payload) != {'items'}:
        raise ValueError('invalid_readback')
    rows = payload['items']
    if not isinstance(rows, list) or len(rows) > MAX_REPORTS:
        raise ValueError('invalid_collection')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'report', 'receivedAtUtc'}:
            raise ValueError('invalid_observation')
        report = row['report']
        if not isinstance(report, dict) or set(report) != {'reportId', 'versionCode', 'observedAtUtc',
                'area', 'operation', 'outcome', 'elapsedMilliseconds', 'error'}:
            raise ValueError('invalid_report')
        identifier = str(uuid.UUID(report['reportId']))
        if identifier == str(uuid.UUID(int=0)):
            raise ValueError('empty_report_id')
        for key, minimum, maximum in (('versionCode', 1, 2100000000), ('area', 0, 6),
                ('operation', 0, 3), ('outcome', 0, 2), ('error', 0, 6), ('elapsedMilliseconds', 0, 86400000)):
            if type(report[key]) is not int or not minimum <= report[key] <= maximum:
                raise ValueError('invalid_enum_or_number')
        received = timestamp(row['receivedAtUtc'])
        observed = timestamp(report['observedAtUtc'])
        if received > now + 300 or observed > now + 300:
            raise ValueError('future_report')
        if received < now - TTL or observed < now - TTL:
            continue
        digest = hashlib.sha256(identifier.encode()).hexdigest()
        if digest in result:
            raise ValueError('duplicate_report')
        # Hashes remain only in the private, expiring Hub-side deduplication state.
        result[digest] = (received, (report['versionCode'], report['area'], report['operation'],
                                    report['outcome'], report['error']))
    return result


def validate_state(state, now):
    if not isinstance(state, dict) or set(state) != {'schema', 'seen', 'attempts', 'lastOutcome'} or state['schema'] != 1:
        raise ValueError('invalid_state')
    if not isinstance(state['seen'], dict) or len(state['seen']) > MAX_REPORTS:
        raise ValueError('invalid_seen')
    for key, value in state['seen'].items():
        if not re.fullmatch('[a-f0-9]{64}', key) or type(value) not in (int, float) or not 0 <= value <= now + 300:
            raise ValueError('invalid_seen_entry')
    if not isinstance(state['attempts'], list) or len(state['attempts']) > 12:
        raise ValueError('invalid_attempts')
    if any(type(value) not in (int, float) or not 0 <= value <= now + 300 for value in state['attempts']):
        raise ValueError('invalid_attempt_time')
    if state['lastOutcome'] not in ('baseline', 'claimed', 'sent', 'unknown'):
        raise ValueError('invalid_outcome')
    state['seen'] = {key: value for key, value in state['seen'].items() if value >= now - TTL}
    state['attempts'] = [value for value in state['attempts'] if value > now - 86400]
    return state


def summary(rows):
    counts = collections.Counter(value[1] for value in rows.values())
    lines = ['Chummer Internal: technical problems to investigate',
             f'{len(rows)} new reports (not a count of affected users).']
    for (version, area, operation, outcome, error), count in counts.most_common(8):
        lines.append(f'v{version} · {AREA[area]} · {OPERATION[operation]} · {OUTCOME[outcome]} · {ERROR[error]}: {count}')
    if len(counts) > 8:
        lines.append(f'{sum(count for _, count in counts.most_common()[8:])} reports in other categories.')
    lines.append('Investigate the affected route. No story, account, runner or device content is included.')
    return '\n'.join(lines)


def cycle(path, payload, now, verify_recipient, send):
    rows = observations(payload, now)
    if not path.exists():
        atomic_state(path, {'schema':1, 'seen':{key:value[0] for key,value in rows.items()},
                            'attempts':[], 'lastOutcome':'baseline'})
        return 'baseline'
    state = validate_state(decode(private_read(path, 65536)), now)
    fresh = {key:value for key,value in rows.items() if key not in state['seen']}
    attempts = state['attempts']
    if not fresh or (attempts and now - max(attempts) < 900) or len(attempts) >= 12 or sum(t > now - 3600 for t in attempts) >= 4:
        atomic_state(path, state)
        return 'quiet'
    # The receiver inbox is ephemeral; its current snapshot cannot revoke a
    # durable send claim. Defer the entire batch when retaining both histories
    # would exceed the existing bound. Only normal expiry may free claim slots.
    if len(state['seen']) + len(fresh) > MAX_REPORTS:
        atomic_state(path, state)
        return 'dedup_saturated_no_send'
    verify_recipient()  # Read-only probe; a failure cannot consume/lose reports.
    # Preserve original receipt times; reappearance must not extend retention.
    state['seen'].update({key:value[0] for key,value in fresh.items()})
    state['attempts'].append(now)
    state['lastOutcome'] = 'claimed'
    atomic_state(path, state)  # Durable before any external side effect.
    try:
        send(summary(fresh))
    except Exception:
        state['lastOutcome'] = 'unknown'
        atomic_state(path, state)
        return 'send_unknown_no_replay'
    state['lastOutcome'] = 'sent'
    atomic_state(path, state)
    return 'sent'


class Transport:
    def __init__(self, credentials, reader):
        self.credentials = credentials
        self.reader = reader
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.http.addheaders = []

    def request(self, url, headers, body=None, limit=16384):
        request = urllib.request.Request(url, headers=headers,
            data=None if body is None else json.dumps(body).encode())
        with self.http.open(request, timeout=15) as response:
            if response.status != 200:
                raise ValueError('unexpected_status')
            if int(response.headers.get('Content-Length', '0')) > limit:
                raise ValueError('response_too_large')
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError('response_too_large')
            return decode(raw)

    def read(self):
        return self.request('http://hub:8080/api/v1/support/android-diagnostics',
            {'Host':'chummer.run', 'Authorization':'Bearer '+self.reader, 'Accept':'application/json'}, limit=MAX_BODY)

    def telegram(self, method, body):
        result = self.request('https://api.telegram.org/bot'+self.credentials['botToken']+'/'+method,
            {'Content-Type':'application/json'}, body)
        if result.get('ok') is not True or not isinstance(result.get('result'), dict):
            raise ValueError('telegram_rejected')
        return result['result']

    def verify(self):
        bot = self.telegram('getMe', {})
        chat = self.telegram('getChat', {'chat_id':self.credentials['chatId']})
        if bot.get('id') != self.credentials['botId'] or bot.get('is_bot') is not True or chat.get('type') != 'private' or str(chat.get('id')) != self.credentials['chatId']:
            raise ValueError('recipient_mismatch')

    def send(self, message):
        receipt = self.telegram('sendMessage', {'chat_id':self.credentials['chatId'],
            'text':message, 'disable_web_page_preview':True, 'protect_content':True})
        if type(receipt.get('message_id')) is not int or receipt.get('chat', {}).get('type') != 'private' or str(receipt.get('chat', {}).get('id')) != self.credentials['chatId']:
            raise ValueError('send_receipt_mismatch')


def main():
    os.umask(0o077)
    state = Path('/state/alerts.json')
    info = state.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('unsafe_state_directory')
    lock_fd = os.open(state.parent / 'alerts.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    credentials = decode(private_read('/run/telegram/telegram.json', 8192))
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', credentials.get('botToken', '')) or not re.fullmatch('[0-9]{6,}', credentials.get('chatId', '')) or type(credentials.get('botId')) is not int:
        raise ValueError('invalid_scoped_credentials')
    reader = private_read('/run/reader/reader.token', 128).decode().strip()
    if not re.fullmatch('[a-f0-9]{64}', reader):
        raise ValueError('invalid_reader')
    transport = Transport(credentials, reader)
    transport.verify()
    while True:
        try:
            result = cycle(state, transport.read(), time.time(), transport.verify, transport.send)
            print(json.dumps({'atUtc':datetime.now(timezone.utc).isoformat(), 'status':result}), flush=True)
        except Exception:
            # No raw exception strings/tracebacks: URLs may contain the bot token.
            print(json.dumps({'status':'poll_failed_no_send'}), flush=True)
        time.sleep(60)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('{"status":"startup_failed_no_send"}', flush=True)
        raise SystemExit(1)
