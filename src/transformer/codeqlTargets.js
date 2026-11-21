"use strict";
const fs = require("fs");
const path = require("path");
const {getNodeProfTargets} = require("./nodeprofTargets");

// CodeQL ranges cover the whole function. Reuse the audited AST range bridge
// to select the body IDs actually compared by the transformer.
function getCodeQLTargets(raw, root, prefix, outputDirectory) {
  const labels = [];
  for (const target of new Set(raw)) {
    const match = target.match(/^(.*):<(\d+),(\d+)>--<(\d+),(\d+)>$/);
    if (!match || !match[1].endsWith(".js")) continue;
    const marker = "/" + prefix + "/";
    const normalized = "/" + match[1].replace(/^\/+/, "");
    if (!normalized.startsWith(marker)) continue;
    const relative = normalized.slice(marker.length);
    // staticgetFromACG already converts the 1-based start column to 0-based.
    labels.push("codeql (" + relative + ":" + match[2] + ":" + (Number(match[3]) + 1)
      + ":" + match[4] + ":" + (Number(match[5]) + 1) + ")");
  }
  const temporary = path.join(outputDirectory, "codeql-function-ranges.json");
  fs.writeFileSync(temporary, JSON.stringify({"system (Native)": labels}));
  if (!labels.length) {
    const certificate = process.env.STUBBIFIER_EMPTY_SSCG_CERTIFICATE;
    const scopeFile = process.env.SQJ_SCOPE_FILES;
    if (!certificate || !scopeFile) throw new Error("Empty CodeQL graph lacks a source/index certificate");
    const c = JSON.parse(fs.readFileSync(certificate)), scope = JSON.parse(fs.readFileSync(scopeFile));
    const digest = x => require('crypto').createHash('sha256').update(x).digest('hex');
    if (!c.databaseQualified || !c.queryAndInventoryCompleted || !c.qualifiedEmptyGraph || c.rows !== 0 ||
        !c.indexedMeasuredFiles || c.indexedMeasuredFunctionFiles.length !== c.indexedMeasuredFiles ||
        c.scopeSha256 !== digest(fs.readFileSync(scopeFile)) ||
        !c.indexedMeasuredFunctionFiles.every(f => scope.files.includes(f)) ||
        !Object.entries(scope.hashes).every(([f,h]) => fs.existsSync(path.join(root,f)) && digest(fs.readFileSync(path.join(root,f))) === h))
      throw new Error('Empty CodeQL certificate does not match source scope/index');
    fs.writeFileSync(path.join(outputDirectory, 'static-mapping-audit.json'), JSON.stringify({targets:[],retainedFiles:[],qualifiedEmptyGraph:true,certificate:c,provenance:'Native zero-callee prediction from a verified database; no invented targets'},null,2));
    return [];
  }
  // Unlike a failed runtime capture, an unsound static query may legitimately
  // find no production callees. Database/source qualification is performed by
  // the runner; retain the empty prediction and validate the resulting stubs.
  const mapped = getNodeProfTargets(temporary, root, prefix, {allowEmptyStaticTargets:true});
  mapped.provenance = "CodeQL whole-function ranges mapped to actual AST body IDs; unresolved source files retained";
  fs.writeFileSync(path.join(outputDirectory, "static-mapping-audit.json"), JSON.stringify(mapped, null, 2));
  const retained = JSON.parse(process.env.STUBBIFIER_RETAIN_ROOTS || "[]");
  process.env.STUBBIFIER_RETAIN_ROOTS = JSON.stringify(Array.from(new Set(retained.concat(mapped.retainedFiles))));
  return mapped.targets;
}
module.exports = {getCodeQLTargets};
