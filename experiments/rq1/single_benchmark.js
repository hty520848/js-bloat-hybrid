const fs = require('fs');
const path = require('path');
const [mcg, input, output] = process.argv.slice(2);
const visitor = require(path.join(mcg, 'src/graph/astVisitor'));
const binding = require(path.join(mcg, 'src/graph/binding'));
const pessimistic = require(path.join(mcg, 'src/graph/pessimistic'));
const file = path.resolve(input);
const ast = visitor.astFromFiles([file]);
if (ast.programs.size !== 1) throw new Error('Benchmark parsing failed');
for (const program of ast.programs.values()) binding.addBindings(program);
const forest = visitor.mergeAst(ast, path.dirname(file), path.basename(file), []);
if (forest.length !== 1) throw new Error('Benchmark entry resolution failed');
// Same counters as the library driver, so a zero-difference arm can be read as
// "the switch was never decisive" instead of "the switch did nothing".
if (process.env.MCG_ABLATION_STATS) {
  global.__MCG_ABLATION = {
    indexDisabled: process.env.MCG_DISABLE_INDEX,
    moduleFilterDisabled: process.env.MCG_DISABLE_MODULE_FILTER,
    scopeRestricted: Boolean(process.env.SQJ_SCOPE_FILES),
    analysedFiles: 1
  };
}
const graph = pessimistic.buildCallGraph(forest[0], [file], []);
if (process.env.MCG_ABLATION_STATS) {
  global.__MCG_ABLATION.sourceFunctionNodes = forest[0].functions.length;
  fs.writeFileSync(process.env.MCG_ABLATION_STATS, JSON.stringify(global.__MCG_ABLATION, null, 1));
}
function node(v) {
  if (v.fake) return 'toplevel:1:1';
  if (v.type === 'FuncVertex') return path.basename(v.func.attr.enclosingFile) + ':' + v.func.loc.start.line + ':' + (v.func.loc.start.column + 1);
  if (v.type === 'NativeCalleeVertex') {
    const fn = v.call.call.attr.enclosingFunction;
    return fn ? path.basename(fn.attr.enclosingFile) + ':' + fn.loc.start.line + ':' + (fn.loc.start.column + 1) : 'toplevel:1:1';
  }
  return null;
}
const edges = new Set();
const excluded = [];
graph.edges.iter((source, target) => {
  const s = node(source), t = node(target);
  if (s && t) edges.add(s + '->' + t);
  else excluded.push({ sourceType: source.type, targetType: target.type });
});
fs.writeFileSync(output, JSON.stringify({
  source: file,
  sourceFunctionNodes: forest[0].functions.length,
  functionDefinitions: forest[0].functions.map(fn => ({file: path.basename(fn.attr.enclosingFile), line: fn.loc.start.line, column: fn.loc.start.column, name: visitor.funcname(fn)})),
  edges: [...edges].sort(),
  excluded,
  identity: 'Function declaration/expression start line and one-based column; top level normalized to toplevel:1:1.'
}, null, 2));
