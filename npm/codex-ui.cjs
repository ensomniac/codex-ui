#!/usr/bin/env node
// A deliberately small bridge. All desktop behavior and upgrades live in Python.
const {spawnSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {version} = require('../package.json');

function invoke(command, args, options = {}) {
  return spawnSync(command, args, {stdio: ['inherit', 'inherit', 'inherit'], ...options});
}
function exists(command, args = ['--version']) {
  const result = spawnSync(command, args, {stdio: 'ignore'});
  return result.status === 0;
}
function runtimePaths(base, windows = process.platform === 'win32') {
  return {python: path.join(base, windows ? 'Scripts/python.exe' : 'bin/python'),
          cli: path.join(base, windows ? 'Scripts/codex-ui.exe' : 'bin/codex-ui')};
}
function checked(command, args) {
  const result = invoke(command, args, {stdio: ['inherit', 2, 2]});
  if (result.error || result.status !== 0) throw new Error(result.error?.message || `${command} exited ${result.status}`);
}
function main() {
  const base = process.env.CODEX_UI_NODE_RUNTIME || path.join(os.homedir(), '.local/share/codex-ui/npm-runtime');
  const runtime = runtimePaths(base);
  const hasRuntime = fs.existsSync(runtime.cli);
  const installed = hasRuntime ? spawnSync(runtime.cli, ['--version'], {encoding: 'utf8'}).stdout?.trim().split(' ').pop() : null;
  const newerBridge = installed && version.localeCompare(installed, undefined, {numeric: true}) > 0;
  if (!hasRuntime || newerBridge) {
    fs.mkdirSync(path.dirname(base), {recursive: true});
    const bundled = path.join(__dirname, `../dist/ensomniac_codex_ui-${version}-py3-none-any.whl`);
    const wheel = fs.existsSync(bundled) ? bundled :
      `https://github.com/ensomniac/codex-ui/releases/download/v${version}/ensomniac_codex_ui-${version}-py3-none-any.whl`;
    process.stderr.write('codex-ui: preparing the matching isolated Python runtime\n');
    let uv = 'uv';
    if (!exists(uv)) {
      const py = ['python3', 'python'].find(command => exists(command,
        ['-c', 'import sys; raise SystemExit(sys.version_info < (3, 11))']));
      if (py) {
        if (!hasRuntime) checked(py, ['-m', 'venv', base]);
        checked(runtime.python, ['-m', 'pip', 'install', wheel]);
      } else {
        throw new Error('Install uv or Python 3.11+, then rerun. The one-line installer at https://ensomniac.github.io/codex-ui/ supplies uv automatically.');
      }
    } else {
      if (!hasRuntime) checked(uv, ['venv', '--python', '3.12', base]);
      checked(uv, ['pip', 'install', '--python', runtime.python, wheel]);
    }
  }
  const result = invoke(runtime.cli, process.argv.slice(2));
  if (result.error) throw result.error;
  return result.status ?? 1;
}
module.exports = {runtimePaths};
if (require.main === module) {
  try { process.exitCode = main(); }
  catch (error) {
    process.stdout.write(JSON.stringify({ok: false, command: process.argv[2] || null,
      version, schema_version: 1, error: {type: 'BootstrapError', message: error.message}}) + '\n');
    process.exitCode = 1;
  }
}
