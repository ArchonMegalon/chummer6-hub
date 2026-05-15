import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const repoRoot = process.cwd();
const configuredCompletionDir = process.env.CHUMMER_COMPLETION_DIR?.trim();
const completionDir = configuredCompletionDir
  ? (path.isAbsolute(configuredCompletionDir)
      ? configuredCompletionDir
      : path.resolve(repoRoot, configuredCompletionDir))
  : path.resolve(repoRoot, '..', '_completion', 'black_ledger_command_map');

export function ensureMapCompletionDir(): string {
  mkdirSync(completionDir, { recursive: true });
  return completionDir;
}

export function mapCompletionPath(fileName: string): string {
  return path.join(ensureMapCompletionDir(), fileName);
}

export function writeMapJsonArtifact(fileName: string, payload: unknown): void {
  writeFileSync(mapCompletionPath(fileName), `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

export function writeMapMarkdownArtifact(fileName: string, content: string): void {
  writeFileSync(mapCompletionPath(fileName), content.endsWith('\n') ? content : `${content}\n`, 'utf8');
}
