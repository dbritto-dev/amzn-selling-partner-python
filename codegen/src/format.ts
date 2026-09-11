/** Format generated Python with ruff (import sorting, unused imports, formatting): `npm run format -- <dir>...`. */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const dirs = process.argv.slice(2).map((d) => path.resolve(d));
if (dirs.length === 0) {
  process.stderr.write('usage: tsx src/format.ts <dir>...\n');
  process.exit(2);
}
const venv = path.join(ROOT, '.venv', 'bin', 'ruff');
const ruff = fs.existsSync(venv) ? venv : 'ruff';
try {
  execFileSync(ruff, ['check', '--fix', '--select', 'I,F401', '--quiet', ...dirs], { cwd: ROOT, stdio: 'inherit' });
  execFileSync(ruff, ['format', '--quiet', ...dirs], { cwd: ROOT, stdio: 'inherit' });
} catch (err) {
  process.stderr.write(`ruff failed (${String(err)}); generated files are unformatted\n`);
  process.exit(1);
}
