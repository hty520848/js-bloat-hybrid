'use strict';
// Preserve the complete npm pretest + coverage workload, varying only Jest's deadline.
const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const argument = process.argv[2] || '';
if (!/^--timeout-ms=[1-9][0-9]*$/.test(argument)) throw Error('Explicit positive Jest timeout required');
const timeout = Number(argument.split('=')[1]);
if (!Number.isSafeInteger(timeout)) throw Error('Invalid Jest timeout');
const pkg = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf8'));
// This adapter is qualified for this pinned client recipe, not arbitrary npm scripts.
if (pkg.name !== 'style-loader' || pkg.version !== '1.3.0' ||
    pkg.scripts.pretest !== 'npm run lint' || pkg.scripts.test !== 'npm run test:coverage' ||
    !/^npm run test:only -- /.test(pkg.scripts['test:coverage'] || '') ||
    !/jest/.test(pkg.scripts['test:only'] || '')) throw Error('Unqualified client test recipe');
for (const args of [['run', 'pretest'], ['run', 'test:coverage', '--', '--testTimeout=' + timeout]]) {
  const result = cp.spawnSync('npm', args, {cwd: process.cwd(), env: process.env, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.signal || result.status !== 0) process.exit(result.status || 1);
}
