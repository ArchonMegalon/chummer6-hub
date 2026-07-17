import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const repoRoot = process.cwd();
const configuredCompletionDir = process.env.CHUMMER_COMPLETION_DIR?.trim();
const completionDir = configuredCompletionDir
  ? (path.isAbsolute(configuredCompletionDir)
      ? configuredCompletionDir
      : path.resolve(repoRoot, configuredCompletionDir))
  : path.resolve(repoRoot, '..', '_completion', 'chummer_run_redesign_closure');

export function ensureCompletionDir(): string {
  mkdirSync(completionDir, { recursive: true });
  return completionDir;
}

export function completionPath(fileName: string): string {
  return path.join(ensureCompletionDir(), fileName);
}

export function requiredProofClosureSha256(): string {
  const value = process.env.CHUMMER_FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_SHA256?.trim() || '';
  if (!/^[0-9a-f]{64}$/.test(value)) {
    throw new Error('frontdoor Playwright proof closure digest is missing or invalid');
  }
  return value;
}

export function writeJsonArtifact(fileName: string, payload: unknown): void {
  writeFileSync(completionPath(fileName), `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

export function writeMarkdownArtifact(fileName: string, content: string): void {
  writeFileSync(completionPath(fileName), content.endsWith('\n') ? content : `${content}\n`, 'utf8');
}
