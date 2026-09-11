const test = require('node:test');
const assert = require('node:assert/strict');
const {runtimePaths} = require('./codex-ui.cjs');
test('runtime executables use platform-specific venv locations', () => {
  assert.match(runtimePaths('/tmp/runtime', false).cli, /bin[\\/]codex-ui$/);
  assert.match(runtimePaths('/tmp/runtime', true).cli, /Scripts[\\/]codex-ui.exe$/);
});
