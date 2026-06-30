import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';

const python = existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python3';

const commands = [
  ['api', python, ['run.py']],
  ['ui', 'npx', ['vite', '--host', '0.0.0.0']]
];

const children = commands.map(([name, cmd, args]) => {
  const child = spawn(cmd, args, { stdio: 'pipe', shell: process.platform === 'win32' });
  child.stdout.on('data', data => process.stdout.write(`[${name}] ${data}`));
  child.stderr.on('data', data => process.stderr.write(`[${name}] ${data}`));
  child.on('exit', code => {
    if (code && code !== 0) console.error(`[${name}] exited with code ${code}`);
  });
  return child;
});

function shutdown() {
  for (const child of children) child.kill('SIGTERM');
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

