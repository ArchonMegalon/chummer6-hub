import { createHash, randomBytes } from 'node:crypto';
import {
  closeSync,
  constants,
  fstatSync,
  fsyncSync,
  linkSync,
  lstatSync,
  openSync,
  readFileSync,
  realpathSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import { TextDecoder } from 'node:util';
import type { APIRequestContext } from 'playwright/test';

const releaseTruthContract = 'chummer.release-truth-projection/v1';
const releaseVersionPattern = /^[a-z0-9][a-z0-9._-]{0,127}$/;
const sha256Pattern = /^[0-9a-f]{64}$/;
const generationAuthorityRoutePattern = /^\/api\/v1\/public\/release-truth\/g\/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const stagedProbeHeader = 'X-Chummer-Staged-Release-Probe';
const maximumAuthorityBytes = 8 * 1024 * 1024;
const releaseScopeFields = [
  'approvedAtUtc', 'approvedBy', 'channel', 'contractName', 'contractVersion',
  'decisionId', 'platforms', 'releaseTarget', 'releaseVersion', 'status', 'supportOwner',
].sort();
const releaseScopePlatformFields = [
  'artifactAccessClass', 'fallbackHeads', 'platform', 'primaryHead', 'rid',
  'signingRequirement',
].sort();

type Environment = Record<string, string | undefined>;

export type CandidateVerificationMode = 'committed_public' | 'staged_private';

export type UiFrameCandidateBinding = {
  baseUrl: string;
  verificationMode: CandidateVerificationMode;
  authorityRoute: string;
  releaseVersion: string;
  manifestSha256: string;
  authoritySnapshotSha256: string;
  releaseDecisionSha256: string;
  releaseScopeDecisionSha256: string;
  releaseScopeDecisionPath: string;
  receiptPath: string;
  outputDirectory: string;
  outputDirectoryDevice: number;
  outputDirectoryInode: number;
  outputDirectoryUid: number;
  requestHeaders: Record<string, string>;
};

export type UiFrameAuthorityObservation = {
  observed_at_utc: string;
  request_method: 'GET';
  authority_route: string;
  verification_mode: CandidateVerificationMode;
  authority_snapshot_sha256: string;
  release_truth: Record<string, unknown>;
};

function requiredEnvironment(env: Environment, name: string): string {
  const raw = env[name];
  if (raw === undefined || raw.length === 0 || raw !== raw.trim()) {
    throw new Error(`${name} must be an explicit canonical non-empty value`);
  }
  if ([...raw].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) {
    throw new Error(`${name} contains control characters`);
  }
  return raw;
}

function requiredSha256(env: Environment, name: string): string {
  const value = requiredEnvironment(env, name);
  if (!sha256Pattern.test(value)) {
    throw new Error(`${name} must be 64 lowercase hexadecimal characters`);
  }
  return value;
}

function normalizedBaseUrl(raw: string): string {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error('BASE_URL must be an absolute HTTP(S) origin');
  }
  if (parsed.protocol !== 'https:'
      || parsed.username
      || parsed.password
      || parsed.search
      || parsed.hash
      || (parsed.pathname !== '/' && parsed.pathname !== '')) {
    throw new Error('BASE_URL must be a credential-free HTTPS origin without a path, query, or fragment');
  }
  return parsed.origin;
}

function canonicalAbsolutePath(raw: string, label: string): string {
  if (!path.isAbsolute(raw) || path.normalize(raw) !== raw) {
    throw new Error(`${label} must be a normalized absolute path`);
  }
  return raw;
}

function stableRead(
  filePath: string,
  label: string,
  maximumBytes: number,
  requiredMode?: number,
): Buffer {
  const noFollow = typeof constants.O_NOFOLLOW === 'number' ? constants.O_NOFOLLOW : 0;
  let descriptor: number;
  try {
    descriptor = openSync(filePath, constants.O_RDONLY | noFollow);
  } catch (error) {
    throw new Error(`${label} could not be opened safely: ${String(error)}`);
  }

  try {
    const before = fstatSync(descriptor);
    const effectiveUid = typeof process.geteuid === 'function' ? process.geteuid() : before.uid;
    if (!before.isFile()
        || before.nlink !== 1
        || before.uid !== effectiveUid
        || before.size < 1
        || before.size > maximumBytes) {
      throw new Error(`${label} must be a caller-owned bounded single-link regular file`);
    }
    if (requiredMode !== undefined && (before.mode & 0o777) !== requiredMode) {
      throw new Error(`${label} must have mode ${requiredMode.toString(8).padStart(4, '0')}`);
    }

    const raw = readFileSync(descriptor);
    const after = fstatSync(descriptor);
    const identity = (item: typeof before) => [
      item.dev,
      item.ino,
      item.size,
      item.mtimeMs,
      item.ctimeMs,
      item.mode,
      item.nlink,
      item.uid,
    ].join(':');
    if (raw.length !== before.size || identity(before) !== identity(after)) {
      throw new Error(`${label} changed during its stable read`);
    }
    return raw;
  } finally {
    closeSync(descriptor);
  }
}

function parseJsonObject(raw: Buffer, label: string): Record<string, unknown> {
  let text: string;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
  } catch {
    throw new Error(`${label} is not UTF-8`);
  }
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(`${label} is not JSON`);
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return payload as Record<string, unknown>;
}

function validateReleaseScopeDecision(
  filePath: string,
  expectedSha256: string,
  releaseVersion: string,
): void {
  const raw = stableRead(filePath, 'approved release-scope decision', maximumAuthorityBytes);
  const observedSha256 = createHash('sha256').update(raw).digest('hex');
  if (observedSha256 !== expectedSha256) {
    throw new Error(
      `approved release-scope decision SHA-256 mismatch: expected=${expectedSha256} actual=${observedSha256}`,
    );
  }
  const payload = parseJsonObject(raw, 'approved release-scope decision');
  if (!raw.equals(Buffer.from(`${stableJson(payload)}\n`, 'utf8'))) {
    throw new Error('release-scope decision bytes must be compact sorted UTF-8 JSON plus LF');
  }
  if (Object.keys(payload).sort().join('\0') !== releaseScopeFields.join('\0')
      || payload.contractName !== 'chummer.release-scope-decision/v1'
      || payload.contractVersion !== 1
      || payload.status !== 'approved'
      || payload.channel !== 'preview'
      || payload.releaseTarget !== 'preview'
      || payload.releaseVersion !== releaseVersion) {
    throw new Error('release-scope decision is not the exact approved v1 candidate decision');
  }
  if (typeof payload.decisionId !== 'string'
      || !releaseVersionPattern.test(payload.decisionId)
      || typeof payload.supportOwner !== 'string'
      || !releaseVersionPattern.test(payload.supportOwner)
      || typeof payload.approvedBy !== 'string'
      || !payload.approvedBy.trim()
      || typeof payload.approvedAtUtc !== 'string'
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(payload.approvedAtUtc)
      || !Array.isArray(payload.platforms)
      || payload.platforms.length < 1
      || payload.platforms.length > 16) {
    throw new Error('release-scope decision identity, owner, or platform inventory is invalid');
  }
  let previousPlatform = '';
  for (const rawRow of payload.platforms) {
    if (!rawRow || typeof rawRow !== 'object' || Array.isArray(rawRow)) {
      throw new Error('release-scope platform row must be an object');
    }
    const row = rawRow as Record<string, unknown>;
    const platform = row.platform;
    const rid = row.rid;
    const allowedRids: Record<string, string[]> = {
      linux: ['linux-arm64', 'linux-x64'],
      macos: ['osx-arm64', 'osx-x64'],
      windows: ['win-arm64', 'win-x64'],
    };
    if (Object.keys(row).sort().join('\0') !== releaseScopePlatformFields.join('\0')
        || typeof platform !== 'string'
        || !allowedRids[platform]?.includes(String(rid))
        || platform <= previousPlatform
        || !['avalonia', 'blazor-desktop'].includes(String(row.primaryHead))
        || !Array.isArray(row.fallbackHeads)
        || [...row.fallbackHeads].sort().join('\0') !== row.fallbackHeads.join('\0')
        || new Set(row.fallbackHeads).size !== row.fallbackHeads.length
        || row.fallbackHeads.includes(row.primaryHead)
        || row.fallbackHeads.some((head) => !['avalonia', 'blazor-desktop'].includes(String(head)))
        || !['open_public', 'account_required', 'support_directed'].includes(String(row.artifactAccessClass))
        || !['signed', 'preview_unsigned_allowed', 'not_applicable'].includes(String(row.signingRequirement))) {
      throw new Error('release-scope platform inventory is noncanonical or unsupported');
    }
    previousPlatform = platform;
  }
}

function validateCandidateOutput(
  receiptPath: string,
  releaseVersion: string,
): {
  receiptPath: string;
  outputDirectory: string;
  outputDirectoryDevice: number;
  outputDirectoryInode: number;
  outputDirectoryUid: number;
} {
  const canonicalReceiptPath = canonicalAbsolutePath(receiptPath, 'CHUMMER_UI_FRAME_RECEIPT_PATH');
  if (path.basename(canonicalReceiptPath) !== 'UI_FRAME_INTEGRITY.generated.json') {
    throw new Error('CHUMMER_UI_FRAME_RECEIPT_PATH must end in UI_FRAME_INTEGRITY.generated.json');
  }
  const outputDirectory = path.dirname(canonicalReceiptPath);
  if (path.basename(outputDirectory) !== releaseVersion) {
    throw new Error('UI-frame receipt directory must be named exactly for the expected release version');
  }
  let outputMetadata;
  try {
    outputMetadata = lstatSync(outputDirectory);
  } catch (error) {
    throw new Error(`candidate output directory is unavailable: ${String(error)}`);
  }
  const effectiveUid = typeof process.geteuid === 'function' ? process.geteuid() : outputMetadata.uid;
  if (!outputMetadata.isDirectory()
      || outputMetadata.isSymbolicLink()
      || outputMetadata.uid !== effectiveUid
      || (outputMetadata.mode & 0o777) !== 0o700) {
    throw new Error('candidate output directory must be a caller-owned mode-0700 real directory');
  }
  if (realpathSync.native(outputDirectory) !== outputDirectory) {
    throw new Error('candidate output directory must not traverse symbolic links');
  }
  return {
    receiptPath: canonicalReceiptPath,
    outputDirectory,
    outputDirectoryDevice: outputMetadata.dev,
    outputDirectoryInode: outputMetadata.ino,
    outputDirectoryUid: outputMetadata.uid,
  };
}

function readStagedProbeToken(env: Environment, mode: CandidateVerificationMode): Record<string, string> {
  const configuredPath = env.CHUMMER_UI_FRAME_STAGED_PROBE_TOKEN_FILE;
  if (mode === 'committed_public') {
    if (configuredPath !== undefined && configuredPath.trim()) {
      throw new Error('committed_public verification must not receive a staged probe token');
    }
    return {};
  }

  const tokenPath = canonicalAbsolutePath(
    requiredEnvironment(env, 'CHUMMER_UI_FRAME_STAGED_PROBE_TOKEN_FILE'),
    'CHUMMER_UI_FRAME_STAGED_PROBE_TOKEN_FILE',
  );
  const token = stableRead(tokenPath, 'staged probe token', 512, 0o600).toString('ascii').trim();
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(token)) {
    throw new Error('staged probe token is malformed');
  }
  return { [stagedProbeHeader]: token };
}

export function loadUiFrameCandidateBinding(env: Environment = process.env): UiFrameCandidateBinding {
  const releaseVersion = requiredEnvironment(env, 'CHUMMER_UI_FRAME_EXPECTED_RELEASE_VERSION');
  if (!releaseVersionPattern.test(releaseVersion) || releaseVersion.includes('..')) {
    throw new Error('CHUMMER_UI_FRAME_EXPECTED_RELEASE_VERSION must be a canonical lowercase safe token');
  }

  const mode = requiredEnvironment(env, 'CHUMMER_UI_FRAME_VERIFICATION_MODE');
  if (mode !== 'committed_public' && mode !== 'staged_private') {
    throw new Error('CHUMMER_UI_FRAME_VERIFICATION_MODE must be committed_public or staged_private');
  }

  const authorityRoute = requiredEnvironment(env, 'CHUMMER_UI_FRAME_AUTHORITY_ROUTE');
  if (mode === 'committed_public' && authorityRoute !== '/api/v1/public/release-truth') {
    throw new Error('committed_public verification must use the canonical current authority route');
  }
  if (mode === 'staged_private' && !generationAuthorityRoutePattern.test(authorityRoute)) {
    throw new Error('staged_private verification must use a traversal-safe generation authority route');
  }

  const manifestSha256 = requiredSha256(env, 'CHUMMER_UI_FRAME_EXPECTED_MANIFEST_SHA256');
  const authoritySnapshotSha256 = requiredSha256(
    env,
    'CHUMMER_UI_FRAME_EXPECTED_AUTHORITY_SNAPSHOT_SHA256',
  );
  const releaseDecisionSha256 = requiredSha256(
    env,
    'CHUMMER_UI_FRAME_EXPECTED_RELEASE_DECISION_SHA256',
  );
  const releaseScopeDecisionSha256 = requiredSha256(
    env,
    'CHUMMER_UI_FRAME_EXPECTED_RELEASE_SCOPE_SHA256',
  );
  const releaseScopeDecisionPath = canonicalAbsolutePath(
    requiredEnvironment(env, 'CHUMMER_UI_FRAME_RELEASE_SCOPE_DECISION_PATH'),
    'CHUMMER_UI_FRAME_RELEASE_SCOPE_DECISION_PATH',
  );
  validateReleaseScopeDecision(
    releaseScopeDecisionPath,
    releaseScopeDecisionSha256,
    releaseVersion,
  );

  const output = validateCandidateOutput(
    requiredEnvironment(env, 'CHUMMER_UI_FRAME_RECEIPT_PATH'),
    releaseVersion,
  );

  const configuredBaseUrl = env.BASE_URL ?? env.CHUMMER_PUBLIC_BASE_URL;
  if (configuredBaseUrl === undefined) {
    throw new Error('BASE_URL or CHUMMER_PUBLIC_BASE_URL must be set explicitly');
  }

  return {
    baseUrl: normalizedBaseUrl(configuredBaseUrl),
    verificationMode: mode,
    authorityRoute,
    releaseVersion,
    manifestSha256,
    authoritySnapshotSha256,
    releaseDecisionSha256,
    releaseScopeDecisionSha256,
    releaseScopeDecisionPath,
    receiptPath: output.receiptPath,
    outputDirectory: output.outputDirectory,
    outputDirectoryDevice: output.outputDirectoryDevice,
    outputDirectoryInode: output.outputDirectoryInode,
    outputDirectoryUid: output.outputDirectoryUid,
    requestHeaders: readStagedProbeToken(env, mode),
  };
}

function normalizedHeaders(headers: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]));
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    const rows = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`);
    return `{${rows.join(',')}}`;
  }
  const encoded = JSON.stringify(value);
  return encoded === undefined ? 'undefined' : encoded;
}

function projectionFromHeader(encoded: string, source: string): Record<string, unknown> {
  if (!encoded || encoded.length > 16 * 1024 || !/^[A-Za-z0-9_-]+={0,2}$/.test(encoded)) {
    throw new Error(`${source}: missing or invalid x-chummer-release-truth header`);
  }
  let raw: Buffer;
  try {
    raw = Buffer.from(encoded, 'base64url');
  } catch {
    throw new Error(`${source}: x-chummer-release-truth is not base64url`);
  }
  const projection = parseJsonObject(raw, `${source} release-truth header`);
  if (projection.contractName !== releaseTruthContract) {
    throw new Error(`${source}: release-truth header contract mismatch`);
  }
  return projection;
}

function assertProjectionIdentity(
  projection: Record<string, unknown>,
  binding: UiFrameCandidateBinding,
  source: string,
): void {
  const expected: Record<string, string> = {
    releaseVersion: binding.releaseVersion,
    manifestSha256: binding.manifestSha256,
    releaseDecisionSha256: binding.releaseDecisionSha256,
  };
  const mismatches = Object.entries(expected)
    .filter(([field, value]) => projection[field] !== value)
    .map(([field, value]) => `${field}: expected=${value} actual=${String(projection[field])}`);
  if (mismatches.length > 0) {
    throw new Error(`${source}: candidate release identity mismatch: ${mismatches.join(', ')}`);
  }
}

export function verifyUiFrameCandidateHeaders(
  rawHeaders: Record<string, string>,
  binding: UiFrameCandidateBinding,
  source: string,
): Record<string, unknown> {
  const headers = normalizedHeaders(rawHeaders);
  const projection = projectionFromHeader(headers['x-chummer-release-truth'] || '', source);
  assertProjectionIdentity(projection, binding, source);
  const authoritySnapshot = (headers['x-chummer-release-authority-snapshot-sha256'] || '').trim();
  if (!sha256Pattern.test(authoritySnapshot)
      || authoritySnapshot !== binding.authoritySnapshotSha256) {
    throw new Error(
      `${source}: authority snapshot mismatch: expected=${binding.authoritySnapshotSha256} actual=${authoritySnapshot || 'missing'}`,
    );
  }
  if (binding.verificationMode === 'staged_private') {
    const cacheControl = (headers['cache-control'] || '').toLowerCase();
    const robots = (headers['x-robots-tag'] || '').toLowerCase();
    const vary = (headers.vary || '').toLowerCase();
    if (!cacheControl.includes('no-store')
        || !robots.includes('noindex')
        || !vary.includes(stagedProbeHeader.toLowerCase())) {
      throw new Error(`${source}: staged response is missing no-store/noindex probe isolation`);
    }
  }
  return projection;
}

export async function verifyUiFrameCandidateAuthority(
  request: APIRequestContext,
  binding: UiFrameCandidateBinding,
): Promise<UiFrameAuthorityObservation> {
  const response = await request.get(binding.authorityRoute, {
    headers: binding.requestHeaders,
    maxRedirects: 0,
    timeout: 30_000,
    failOnStatusCode: false,
  });
  if (response.status() !== 200) {
    throw new Error(`${binding.authorityRoute}: authority GET returned HTTP ${response.status()}`);
  }
  const expectedUrl = new URL(binding.authorityRoute, `${binding.baseUrl}/`);
  const observedUrl = new URL(response.url());
  if (observedUrl.origin !== expectedUrl.origin
      || observedUrl.pathname !== expectedUrl.pathname
      || observedUrl.search !== expectedUrl.search) {
    throw new Error(`${binding.authorityRoute}: authority GET redirected or changed origin`);
  }
  const headers = normalizedHeaders(response.headers());
  if (!(headers['content-type'] || '').toLowerCase().includes('application/json')) {
    throw new Error(`${binding.authorityRoute}: authority response is not JSON`);
  }
  const headerProjection = verifyUiFrameCandidateHeaders(headers, binding, binding.authorityRoute);
  const rawBody = await response.body();
  if (rawBody.length < 2 || rawBody.length > maximumAuthorityBytes) {
    throw new Error(`${binding.authorityRoute}: authority response body is empty or oversized`);
  }
  const payload = parseJsonObject(rawBody, `${binding.authorityRoute} body`);
  const bodyProjection = payload.contractName === releaseTruthContract
    ? payload
    : payload.releaseTruth;
  if (!bodyProjection || typeof bodyProjection !== 'object' || Array.isArray(bodyProjection)) {
    throw new Error(`${binding.authorityRoute}: authority body is missing releaseTruth`);
  }
  if (stableJson(headerProjection) !== stableJson(bodyProjection)) {
    throw new Error(`${binding.authorityRoute}: authority body/header release truth mismatch`);
  }
  assertProjectionIdentity(bodyProjection as Record<string, unknown>, binding, binding.authorityRoute);

  return {
    observed_at_utc: new Date().toISOString(),
    request_method: 'GET',
    authority_route: binding.authorityRoute,
    verification_mode: binding.verificationMode,
    authority_snapshot_sha256: binding.authoritySnapshotSha256,
    release_truth: headerProjection,
  };
}

export function candidateBindingReceipt(binding: UiFrameCandidateBinding): Record<string, string> {
  return {
    release_version: binding.releaseVersion,
    manifest_sha256: binding.manifestSha256,
    authority_snapshot_sha256: binding.authoritySnapshotSha256,
    release_decision_sha256: binding.releaseDecisionSha256,
    release_scope_decision_sha256: binding.releaseScopeDecisionSha256,
    authority_route: binding.authorityRoute,
    verification_mode: binding.verificationMode,
  };
}

export function candidateArtifactPath(
  binding: UiFrameCandidateBinding,
  fileName: 'UI_FRAME_INTEGRITY.generated.json' | 'UI_FRAME_INTEGRITY_REPORT.md' | 'LOGIN_COMPACT_FRAME.generated.json',
): string {
  const candidatePath = path.join(binding.outputDirectory, fileName);
  if (path.dirname(candidatePath) !== binding.outputDirectory) {
    throw new Error('candidate artifact path escaped its explicit output directory');
  }
  return candidatePath;
}

function writeExclusive(
  binding: UiFrameCandidateBinding,
  fileName: 'UI_FRAME_INTEGRITY.generated.json' | 'UI_FRAME_INTEGRITY_REPORT.md' | 'LOGIN_COMPACT_FRAME.generated.json',
  content: string,
): void {
  const stagedToken = binding.requestHeaders[stagedProbeHeader];
  if (stagedToken && content.includes(stagedToken)) {
    throw new Error('candidate artifact attempted to include the private staged probe token');
  }
  const outputMetadata = lstatSync(binding.outputDirectory);
  if (!outputMetadata.isDirectory()
      || outputMetadata.isSymbolicLink()
      || outputMetadata.dev !== binding.outputDirectoryDevice
      || outputMetadata.ino !== binding.outputDirectoryInode
      || outputMetadata.uid !== binding.outputDirectoryUid
      || (outputMetadata.mode & 0o777) !== 0o700
      || realpathSync.native(binding.outputDirectory) !== binding.outputDirectory) {
    throw new Error('candidate output directory identity or permissions changed before write');
  }

  const target = candidateArtifactPath(binding, fileName);
  const temporary = path.join(
    binding.outputDirectory,
    `.${fileName}.${randomBytes(12).toString('hex')}.tmp`,
  );
  const noFollow = typeof constants.O_NOFOLLOW === 'number' ? constants.O_NOFOLLOW : 0;
  const closeOnExec = typeof constants.O_CLOEXEC === 'number' ? constants.O_CLOEXEC : 0;
  let descriptor: number | undefined;
  let linked = false;
  let published = false;
  try {
    descriptor = openSync(
      temporary,
      constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | noFollow | closeOnExec,
      0o600,
    );
    writeFileSync(descriptor, content, { encoding: 'utf8' });
    fsyncSync(descriptor);
    const staged = fstatSync(descriptor);
    if (!staged.isFile()
        || staged.nlink !== 1
        || staged.uid !== binding.outputDirectoryUid
        || (staged.mode & 0o777) !== 0o600) {
      throw new Error('candidate artifact staging file is not caller-owned mode-0600');
    }
    closeSync(descriptor);
    descriptor = undefined;
    linkSync(temporary, target);
    linked = true;
    unlinkSync(temporary);

    const finalMetadata = lstatSync(target);
    if (!finalMetadata.isFile()
        || finalMetadata.isSymbolicLink()
        || finalMetadata.nlink !== 1
        || finalMetadata.uid !== binding.outputDirectoryUid
        || (finalMetadata.mode & 0o777) !== 0o600) {
      throw new Error('candidate artifact final file is not caller-owned single-link mode-0600');
    }
    const directoryFlags = constants.O_RDONLY
      | (typeof constants.O_DIRECTORY === 'number' ? constants.O_DIRECTORY : 0)
      | noFollow
      | closeOnExec;
    const directoryDescriptor = openSync(binding.outputDirectory, directoryFlags);
    try {
      const current = fstatSync(directoryDescriptor);
      if (current.dev !== binding.outputDirectoryDevice
          || current.ino !== binding.outputDirectoryInode
          || current.uid !== binding.outputDirectoryUid
          || (current.mode & 0o777) !== 0o700) {
        throw new Error('candidate output directory changed during atomic publication');
      }
      fsyncSync(directoryDescriptor);
    } finally {
      closeSync(directoryDescriptor);
    }
    published = true;
  } finally {
    if (descriptor !== undefined) {
      closeSync(descriptor);
    }
    try {
      unlinkSync(temporary);
    } catch {
      // The exclusive staging file may not have been created or was already unlinked.
    }
    if (linked && !published) {
      try {
        unlinkSync(target);
      } catch {
        // Preserve the original publication error.
      }
    }
  }
}

export function writeUiFrameCandidateJson(
  binding: UiFrameCandidateBinding,
  fileName: 'UI_FRAME_INTEGRITY.generated.json' | 'LOGIN_COMPACT_FRAME.generated.json',
  payload: unknown,
): void {
  writeExclusive(binding, fileName, `${JSON.stringify(payload, null, 2)}\n`);
}

export function writeUiFrameCandidateReport(
  binding: UiFrameCandidateBinding,
  content: string,
): void {
  writeExclusive(
    binding,
    'UI_FRAME_INTEGRITY_REPORT.md',
    content.endsWith('\n') ? content : `${content}\n`,
  );
}
