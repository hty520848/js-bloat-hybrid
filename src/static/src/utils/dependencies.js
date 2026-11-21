const fs = require('fs');
const path = require('path');

// Resolve each dependency from its actual owner, including nested versions.
function productionPackages(root) {
  const packages = new Map();
  const queue = [path.resolve(root)];
  while (queue.length) {
    const owner = queue.shift();
    const data = JSON.parse(fs.readFileSync(path.join(owner, 'package.json'), 'utf8'));
    for (const name of Object.keys(data.dependencies || {})) {
      let dir;
      try {
        dir = path.dirname(require.resolve(name + '/package.json', { paths: [owner] }));
      } catch (error) {
        if ((data.optionalDependencies || {})[name]) continue;
        throw new Error('Cannot resolve production dependency ' + name + ' from ' + owner + ': ' + error.message);
      }
      if (packages.has(dir)) continue;
      packages.set(dir, JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8')));
      queue.push(dir);
    }
  }
  return packages;
}
module.exports = { productionPackages };
