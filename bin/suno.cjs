#!/usr/bin/env node
const { spawnSync } = require('node:child_process');
const { resolve } = require('node:path');

const python = process.env.SUNO_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const child = spawnSync(python, [resolve(__dirname, '../suno.py'), ...process.argv.slice(2)], {
  stdio: 'inherit',
});
if (child.error) {
  console.error(`Cannot start Python. Install Python 3.10+ or set SUNO_PYTHON. ${child.error.message}`);
  process.exit(1);
}
process.exit(child.status ?? 130);
