// Preserve lexical names used by lazily evaluated source after Babel rewrites
// import references. This is a compatibility repair, not recovered author code.
const t = require('@babel/types');

function preserveImportBindings(program) {
  const aliases = [];
  const used = new Set();
  const traverse = require('@babel/traverse').default;
  traverse({ type: 'File', program }, {
    Identifier(p) { used.add(p.node.name); }
  });
  for (const statement of program.body) {
    if (statement.type !== 'ImportDeclaration') continue;
    for (const specifier of statement.specifiers) {
      const name = specifier.local.name;
      let alias = name + '_bloatImport';
      while (used.has(alias)) alias += '_';
      used.add(alias);
      specifier.local = t.identifier(alias);
      aliases.push(t.variableDeclaration('const', [
        t.variableDeclarator(t.identifier(name), t.identifier(alias))
      ]));
    }
  }
  program.body = aliases.concat(program.body);
}

function hasJSX(program) {
  let found = false;
  require('@babel/traverse').default({ type: 'File', program }, {
    JSXElement(p) { found = true; p.stop(); },
    JSXFragment(p) { found = true; p.stop(); }
  });
  return found;
}

function hasFlow(code) {
  try {
    const program = require('@babel/parser').parse(code, {sourceType:'unambiguous', plugins:['flow','jsx','classProperties']}).program;
    let found = false;
    require('@babel/traverse').default({type:'File',program}, {
      Flow(p) {found=true; p.stop();}
    });
    return found;
  } catch (_) {return false;}
}

module.exports = { preserveImportBindings, hasJSX, hasFlow };
