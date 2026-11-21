const path = require('path');

// Explicit deployment limitations of the reconstructed filesystem loader.
function retain(filename) {
  const roots = JSON.parse(process.env.STUBBIFIER_RETAIN_ROOTS || '[]');
  const resolved = path.resolve(filename);
  const root = roots.find(candidate => resolved === candidate || resolved.startsWith(candidate + path.sep));
  if (!root) return false;
  console.error('RETAINED_DEPLOYMENT ' + filename);
  return true;
}

module.exports = { retain };
