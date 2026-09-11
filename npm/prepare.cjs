// uv build creates dist/.gitignore containing '*'; override it for npm packaging.
const fs = require('node:fs');
const path = require('node:path');
const {version} = require('../package.json');
const wheel = path.join(__dirname, `../dist/ensomniac_codex_ui-${version}-py3-none-any.whl`);
if (!fs.existsSync(wheel)) throw new Error('Run uv build before npm pack; the bridge must include its release wheel.');
fs.writeFileSync(path.join(__dirname, '../dist/.npmignore'), '!*.whl\n');
