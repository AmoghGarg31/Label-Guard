import { existsSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import { join } from 'node:path';

const root = process.cwd();
const windows = process.platform === 'win32';
const configuredPython = process.env.LABELGUARD_PYTHON?.trim();
const pythonCandidates = [
  configuredPython,
  join(root, 'backend', '.venv-codex', windows ? 'Scripts/python.exe' : 'bin/python'),
  join(root, 'backend', '.venv', windows ? 'Scripts/python.exe' : 'bin/python'),
].filter(Boolean);
const python = pythonCandidates.find((candidate) => existsSync(candidate)) ?? (windows ? 'python.exe' : 'python3');
const npm = windows ? (process.env.ComSpec || 'cmd.exe') : 'npm';
const npmArgs = windows ? ['/d', '/s', '/c', 'npm run dev'] : ['run', 'dev'];
const backendArgs = ['-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '8000'];
if (process.env.LABELGUARD_BACKEND_RELOAD?.trim().toLowerCase() === 'true') {
  backendArgs.push('--reload');
}

const processes = [
  spawn(python, backendArgs, {
    cwd: join(root, 'backend'),
    env: process.env,
    stdio: 'inherit',
  }),
  spawn(npm, npmArgs, {
    cwd: join(root, 'frontend'),
    env: process.env,
    stdio: 'inherit',
  }),
];

let stopping = false;
function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of processes) {
    if (child.killed || !child.pid) continue;
    if (windows) {
      spawnSync('taskkill.exe', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' });
    } else {
      child.kill('SIGINT');
    }
  }
  setTimeout(() => process.exit(exitCode), 100);
}

for (const child of processes) {
  child.on('error', (error) => {
    console.error(`Unable to start LabelGuard development service: ${error.message}`);
    stop(1);
  });
  child.on('exit', (code, signal) => {
    if (!stopping && code !== 0) {
      console.error(`A LabelGuard development service exited (${signal ?? code}).`);
      stop(code ?? 1);
    }
  });
}

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
