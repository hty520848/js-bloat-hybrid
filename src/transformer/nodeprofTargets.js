"use strict";
const fs = require("fs");
const path = require("path");
const parser = require("@babel/parser");
const traverse = require("@babel/traverse").default;

// Bridge the surviving legacy adjacency format to the transformer's body IDs.
// Exact AST ranges are required; unresolved/ambiguous nodes are reported.
function getNodeProfTargets(graphFile, sourceRoot, prefix, options = {}) {
  const graph = JSON.parse(fs.readFileSync(graphFile, "utf8"));
  if (!graph || Array.isArray(graph) || typeof graph !== "object") {
    throw new Error("Expected a legacy NodeProf adjacency object");
  }
  const labels = new Set(Object.keys(graph));
  for (const values of Object.values(graph)) {
    if (!Array.isArray(values) || values.some((v) => typeof v !== "string")) {
      throw new Error("Expected caller -> array of callee labels, not a Jelly graph");
    }
    for (const label of values) labels.add(label);
  }
  const root = path.resolve(sourceRoot);
  const files = new Map();
  const targets = new Set();
  const unresolved = [];
  const excluded = [];
  const retainedFiles = new Set();
  let matchedNodes = 0;
  for (const label of labels) {
    if (label.includes("(Native)")) continue;
    const moduleMatch = label.match(/ \((.*):\{\{(?:module|:program)\}\}\)$/);
    if (moduleMatch) {
      const filename = path.resolve(root, moduleMatch[1]);
      const relative = path.relative(root, filename);
      if (relative !== '..' && !relative.startsWith('..' + path.sep)
          && !path.isAbsolute(relative) && path.extname(filename) === '.js' && fs.existsSync(filename)) {
        targets.add(path.join(prefix || root, relative).split(path.sep).join('/') + ':<1,0>--<1,0>');
      } else excluded.push({label, reason:'module outside existing JavaScript input'});
      continue;
    }
    if (label.includes("{{")) { excluded.push({label, reason:'unmapped synthetic node'}); continue; }
    const match = label.match(/ \((.*):(\d+):(\d+):(\d+):(\d+)\)$/);
    if (!match) { unresolved.push({ label: label, reason: "no source range" }); continue; }
    const filename = path.resolve(root, match[1]);
    const relative = path.relative(root, filename);
    if (relative === ".." || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
      excluded.push({ label: label, reason: "outside application root" });
      continue;
    }
    if (path.extname(filename) !== '.js') {
      excluded.push({label, reason:'outside JavaScript transformation domain'});
      continue;
    }
    if (!files.has(filename)) {
      if (!fs.existsSync(filename)) { files.set(filename, null); }
      else {
        const code=fs.readFileSync(filename, "utf8");
        const {hasFlow,hasJSX}=require('./importBindings');
        if (hasFlow(code)) {
          retainedFiles.add(filename);files.set(filename,[]);
          excluded.push({label,reason:'Flow source retained unchanged'});continue;
        }
        const ast = parser.parse(code, {
          sourceType: "unambiguous", allowReturnOutsideFunction: true,
          plugins: ["jsx", "classProperties"],
        });
        if (hasJSX(ast.program)) {
          retainedFiles.add(filename);files.set(filename,[]);
          excluded.push({label,reason:'JSX source retained unchanged'});continue;
        }
        const functions = [];
        traverse(ast, { Function(p) { functions.push(p.node); } });
        files.set(filename, functions);
      }
    }
    const functions = files.get(filename);
    if (!functions) { unresolved.push({ label: label, reason: "source file missing" }); continue; }
    const [startLine, startColumn, endLine, endColumn] = match.slice(2).map(Number);
    // Expression-bodied arrows also have an exact AST body location.
    const matches = functions.filter((n) => n.body && n.body.loc
      && n.loc.start.line === startLine && n.loc.start.column + 1 === startColumn
      && n.loc.end.line === endLine && n.loc.end.column + 1 === endColumn);
    if (matches.length !== 1) {
      unresolved.push({ label: label, reason: matches.length ? "ambiguous AST range" : "no exact AST function range" });
      retainedFiles.add(filename);
      continue;
    }
    const body = matches[0].body.loc;
    const targetFile = path.join(prefix || root, relative).split(path.sep).join("/");
    targets.add(targetFile + ":<" + body.start.line + "," + body.start.column
      + ">--<" + body.end.line + "," + body.end.column + ">");
    matchedNodes++;
  }
  if (!targets.size && !options.allowEmptyStaticTargets) throw new Error("NodeProf graph matched no application functions; inspect source/version/ranges");
  return { targets: Array.from(targets).sort(), matchedNodes: matchedNodes, unresolved: unresolved, excluded: excluded,
    retainedFiles:Array.from(retainedFiles).sort(), emptyTargetSet:targets.size === 0 };
}

module.exports = { getNodeProfTargets };
if (require.main === module) {
  if (!process.argv[2] || !process.argv[3]) {
    throw new Error("Usage: node nodeprofTargets.js GRAPH_JSON APPLICATION_ROOT [TARGET_PREFIX]");
  }
  console.log(JSON.stringify(getNodeProfTargets(process.argv[2], process.argv[3], process.argv[4]), null, 2));
}
