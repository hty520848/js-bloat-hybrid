// Replace the volatile reinstall-only prehook with validation of the frozen
// dependency snapshot. The client's build and behavioral tests still run.
const assert = require('assert');
const path = require('path');
const from = process.cwd();
const resolve = name => require.resolve(name, { paths:[from] });
const React = require(resolve('react'));
const ReactDOM = require(resolve('react-dom'));
const semver = require(resolve('semver'));
assert(semver.satisfies(React.version, '^16.0.0'), React.version);
assert.strictEqual(React.version, ReactDOM.version);
const adapterPath = resolve('enzyme-adapter-react-16/package.json');
const adapter = require(adapterPath);
for (const [name, range] of Object.entries(adapter.peerDependencies || {})) {
  const installed = require(resolve(name + '/package.json'));
  assert(semver.satisfies(installed.version, range), `${name}@${installed.version} does not satisfy ${range}`);
}
require(resolve('enzyme-adapter-react-16'));
console.log(JSON.stringify({react:React.version,reactDOM:ReactDOM.version,adapter:adapter.version,validation:'frozen peer closure; no dependency replacement'}));
