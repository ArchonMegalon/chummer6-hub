import { createHash } from 'node:crypto';
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { expect, test, type APIRequestContext } from 'playwright/test';
import {
  candidateBindingReceipt,
  loadUiFrameCandidateBinding,
  verifyUiFrameCandidateAuthority,
  verifyUiFrameCandidateHeaders,
  writeUiFrameCandidateJson,
} from './ui-frame-candidate-binding';

const releaseVersion = 'run-20260728-050000';
const manifestSha256 = 'a'.repeat(64);
const authoritySnapshotSha256 = 'b'.repeat(64);
const releaseDecisionSha256 = 'c'.repeat(64);

type Fixture = {
  root: string;
  env: Record<string, string>;
};

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(',')}}`;
  }
  const encoded = JSON.stringify(value);
  return encoded === undefined ? 'undefined' : encoded;
}

function fixture(mode: 'committed_public' | 'staged_private' = 'committed_public'): Fixture {
  const root = mkdtempSync(path.join(tmpdir(), 'ui-frame-candidate-binding-'));
  const outputDirectory = path.join(root, releaseVersion);
  mkdirSync(outputDirectory, { mode: 0o700 });
  const scopePath = path.join(root, 'RELEASE_SCOPE_DECISION.approved.json');
  const scopeRaw = Buffer.from(`${canonicalJson({
    contractName: 'chummer.release-scope-decision/v1',
    contractVersion: 1,
    decisionId: 'scope-run-20260728-050000',
    status: 'approved',
    approvedAtUtc: '2026-07-28T04:00:00Z',
    approvedBy: 'Release authority',
    releaseVersion,
    channel: 'preview',
    releaseTarget: 'preview',
    supportOwner: 'chummer-release-operations',
    platforms: [{
      platform: 'macos',
      rid: 'osx-arm64',
      primaryHead: 'avalonia',
      fallbackHeads: [],
      artifactAccessClass: 'open_public',
      signingRequirement: 'preview_unsigned_allowed',
    }],
  })}\n`);
  writeFileSync(scopePath, scopeRaw);
  const scopeSha256 = createHash('sha256').update(scopeRaw).digest('hex');
  const env: Record<string, string> = {
    BASE_URL: 'https://candidate.example',
    CHUMMER_UI_FRAME_VERIFICATION_MODE: mode,
    CHUMMER_UI_FRAME_AUTHORITY_ROUTE: mode === 'committed_public'
      ? '/api/v1/public/release-truth'
      : `/api/v1/public/release-truth/g/${releaseVersion}`,
    CHUMMER_UI_FRAME_EXPECTED_RELEASE_VERSION: releaseVersion,
    CHUMMER_UI_FRAME_EXPECTED_MANIFEST_SHA256: manifestSha256,
    CHUMMER_UI_FRAME_EXPECTED_AUTHORITY_SNAPSHOT_SHA256: authoritySnapshotSha256,
    CHUMMER_UI_FRAME_EXPECTED_RELEASE_DECISION_SHA256: releaseDecisionSha256,
    CHUMMER_UI_FRAME_EXPECTED_RELEASE_SCOPE_SHA256: scopeSha256,
    CHUMMER_UI_FRAME_RELEASE_SCOPE_DECISION_PATH: scopePath,
    CHUMMER_UI_FRAME_RECEIPT_PATH: path.join(outputDirectory, 'UI_FRAME_INTEGRITY.generated.json'),
  };
  if (mode === 'staged_private') {
    const tokenPath = path.join(root, 'staged-probe-token');
    writeFileSync(tokenPath, 't'.repeat(43));
    chmodSync(tokenPath, 0o600);
    env.CHUMMER_UI_FRAME_STAGED_PROBE_TOKEN_FILE = tokenPath;
  }
  return { root, env };
}

function releaseTruth() {
  return {
    contractName: 'chummer.release-truth-projection/v1',
    releaseVersion,
    manifestSha256,
    releaseDecisionSha256,
  };
}

function encodedProjection(payload = releaseTruth()): string {
  return Buffer.from(JSON.stringify(payload)).toString('base64url');
}

function authorityRequest(
  overrides: {
    status?: number;
    url?: string;
    headers?: Record<string, string>;
    body?: unknown;
  } = {},
  capture?: Record<string, unknown>,
): APIRequestContext {
  const headers = overrides.headers ?? {
    'content-type': 'application/json; charset=utf-8',
    'x-chummer-release-truth': encodedProjection(),
    'x-chummer-release-authority-snapshot-sha256': authoritySnapshotSha256,
  };
  return {
    get: async (url: string, options: unknown) => {
      if (capture) {
        capture.url = url;
        capture.options = options;
      }
      return {
        status: () => overrides.status ?? 200,
        url: () => overrides.url ?? 'https://candidate.example/api/v1/public/release-truth',
        headers: () => headers,
        body: async () => Buffer.from(JSON.stringify(
          overrides.body ?? { releaseTruth: releaseTruth() },
        )),
      };
    },
  } as unknown as APIRequestContext;
}

const roots: string[] = [];

test.afterEach(() => {
  for (const root of roots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

test('loads one exact public candidate binding and validates the approved scope bytes', () => {
  const item = fixture();
  roots.push(item.root);

  const binding = loadUiFrameCandidateBinding(item.env);

  expect(binding.releaseVersion).toBe(releaseVersion);
  expect(binding.requestHeaders).toEqual({});
  expect(candidateBindingReceipt(binding)).toEqual({
    release_version: releaseVersion,
    manifest_sha256: manifestSha256,
    authority_snapshot_sha256: authoritySnapshotSha256,
    release_decision_sha256: releaseDecisionSha256,
    release_scope_decision_sha256: item.env.CHUMMER_UI_FRAME_EXPECTED_RELEASE_SCOPE_SHA256,
    authority_route: '/api/v1/public/release-truth',
    verification_mode: 'committed_public',
  });
});

test('rejects an incomplete binding and a release-scope digest mismatch before network', () => {
  const incomplete = fixture();
  roots.push(incomplete.root);
  delete incomplete.env.CHUMMER_UI_FRAME_EXPECTED_RELEASE_SCOPE_SHA256;
  expect(() => loadUiFrameCandidateBinding(incomplete.env)).toThrow(
    'CHUMMER_UI_FRAME_EXPECTED_RELEASE_SCOPE_SHA256',
  );

  const mismatched = fixture();
  roots.push(mismatched.root);
  mismatched.env.CHUMMER_UI_FRAME_EXPECTED_RELEASE_SCOPE_SHA256 = 'f'.repeat(64);
  expect(() => loadUiFrameCandidateBinding(mismatched.env)).toThrow(
    'approved release-scope decision SHA-256 mismatch',
  );
});

test('rejects HTTP origins and output directories that are not caller-owned mode-0700', () => {
  const insecure = fixture();
  roots.push(insecure.root);
  insecure.env.BASE_URL = 'http://candidate.example';
  expect(() => loadUiFrameCandidateBinding(insecure.env)).toThrow('HTTPS origin');

  const unsafeOutput = fixture();
  roots.push(unsafeOutput.root);
  chmodSync(path.join(unsafeOutput.root, releaseVersion), 0o755);
  expect(() => loadUiFrameCandidateBinding(unsafeOutput.env)).toThrow('mode-0700');
});

test('uses a private staged GET header without exposing it in the binding receipt', () => {
  const item = fixture('staged_private');
  roots.push(item.root);

  const binding = loadUiFrameCandidateBinding(item.env);

  expect(binding.requestHeaders).toEqual({ 'X-Chummer-Staged-Release-Probe': 't'.repeat(43) });
  expect(JSON.stringify(candidateBindingReceipt(binding))).not.toContain('t'.repeat(43));
  const stagedHeaders = {
    'x-chummer-release-truth': encodedProjection(),
    'x-chummer-release-authority-snapshot-sha256': authoritySnapshotSha256,
    'cache-control': 'private, no-store',
    'x-robots-tag': 'noindex, nofollow',
    vary: 'X-Chummer-Staged-Release-Probe',
  };
  expect(() => verifyUiFrameCandidateHeaders(stagedHeaders, binding, '/downloads')).not.toThrow();
  expect(() => verifyUiFrameCandidateHeaders(
    { ...stagedHeaders, 'cache-control': 'public, max-age=60' },
    binding,
    '/downloads',
  )).toThrow('missing no-store/noindex probe isolation');
});

test('verifies authority body, header, snapshot, candidate identity, and GET-only options', async () => {
  const item = fixture();
  roots.push(item.root);
  const binding = loadUiFrameCandidateBinding(item.env);
  const capture: Record<string, unknown> = {};

  const observation = await verifyUiFrameCandidateAuthority(
    authorityRequest({}, capture),
    binding,
  );

  expect(observation.request_method).toBe('GET');
  expect(observation.authority_snapshot_sha256).toBe(authoritySnapshotSha256);
  expect(capture.url).toBe('/api/v1/public/release-truth');
  expect(capture.options).toMatchObject({
    headers: {},
    maxRedirects: 0,
    failOnStatusCode: false,
  });
});

test('fails closed on unavailable or mismatched authority and route headers', async () => {
  const item = fixture();
  roots.push(item.root);
  const binding = loadUiFrameCandidateBinding(item.env);

  await expect(verifyUiFrameCandidateAuthority(
    authorityRequest({ status: 404 }),
    binding,
  )).rejects.toThrow('HTTP 404');

  const wrongProjection = { ...releaseTruth(), manifestSha256: 'd'.repeat(64) };
  const wrongHeaders = {
    'content-type': 'application/json',
    'x-chummer-release-truth': encodedProjection(wrongProjection),
    'x-chummer-release-authority-snapshot-sha256': authoritySnapshotSha256,
  };
  await expect(verifyUiFrameCandidateAuthority(
    authorityRequest({ headers: wrongHeaders, body: { releaseTruth: wrongProjection } }),
    binding,
  )).rejects.toThrow('candidate release identity mismatch');

  expect(() => verifyUiFrameCandidateHeaders({
    'x-chummer-release-truth': encodedProjection(),
    'x-chummer-release-authority-snapshot-sha256': 'e'.repeat(64),
  }, binding, '/downloads')).toThrow('authority snapshot mismatch');
});

test('writes only once to the explicit candidate-scoped receipt path', () => {
  const item = fixture();
  roots.push(item.root);
  const binding = loadUiFrameCandidateBinding(item.env);
  const payload = {
    candidate_binding: candidateBindingReceipt(binding),
    status: 'pass',
  };

  writeUiFrameCandidateJson(binding, 'UI_FRAME_INTEGRITY.generated.json', payload);

  const receipt = path.join(item.root, releaseVersion, 'UI_FRAME_INTEGRITY.generated.json');
  expect(statSync(receipt).mode & 0o777).toBe(0o600);
  expect(readdirSync(path.dirname(receipt)).filter((name) => name.endsWith('.tmp'))).toEqual([]);

  expect(() => writeUiFrameCandidateJson(
    binding,
    'UI_FRAME_INTEGRITY.generated.json',
    payload,
  )).toThrow();
});
