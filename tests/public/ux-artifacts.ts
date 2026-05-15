import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const repoRoot = process.cwd();
const completionDir = path.resolve(repoRoot, '..', '_completion', 'chummer_run_redesign_closure');

export function ensureCompletionDir(): string {
  mkdirSync(completionDir, { recursive: true });
  return completionDir;
}

export function completionPath(fileName: string): string {
  return path.join(ensureCompletionDir(), fileName);
}

export function writeJsonArtifact(fileName: string, payload: unknown): void {
  writeFileSync(completionPath(fileName), `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

export function writeMarkdownArtifact(fileName: string, content: string): void {
  writeFileSync(completionPath(fileName), content.endsWith('\n') ? content : `${content}\n`, 'utf8');
}
