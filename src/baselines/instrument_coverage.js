'use strict';
// Istanbul's instrumenter is independent of the function-entry truth producer.
//
// A measured function can be absent from `fnMap` for two very different
// reasons, and the adapter must never conflate them:
//   1. the source carries an `istanbul ignore next|file` hint, so the
//      instrumenter deliberately skips the node (morgan depends on this:
//      `node_modules/on-finished/index.js` guards `defer` with
//      `/* istanbul ignore next */`);
//   2. the coverage record exists but its source location does not line up
//      with the independently parsed function, which is a real mapping loss.
//
// The second pass below re-instruments the same source with the ignore keyword
// neutralised (`istanbul ignore` -> `istanbul ignored`, which the instrumenter
// no longer recognises). Any function absent in the measured pass but present
// in that diagnostic pass is therefore *proved* to be ignored, by the
// instrumenter itself, rather than by a text heuristic.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const instrumenter=require('istanbul-lib-instrument').createInstrumenter({coverageVariable:'__coverage__',preserveComments:true,compact:false,esModules:true});
const spec=JSON.parse(fs.readFileSync(process.argv[2]));const root=fs.realpathSync(spec.root),initial={},rows=[],ignored={};
const directive=/(?:\/\*+|\/\/)[^\n]*?istanbul\s+ignore\s+(next|if|else|file)/g;
const key=loc=>loc.start.line+':'+loc.start.column+':'+loc.end.line+':'+loc.end.column;
function fnKeys(coverage){const map={};if(!coverage||!coverage.fnMap)return map;for(const id of Object.keys(coverage.fnMap))map[key(coverage.fnMap[id].loc)]=id;return map;}
function hints(text){const found=[];let m;directive.lastIndex=0;while((m=directive.exec(text))!==null)found.push(m[1]);return found;}
function emptyCoverage(file){return {path:file,statementMap:{},fnMap:{},branchMap:{},s:{},f:{},b:{}};}
for(const relative of spec.files){
 const file=path.resolve(root,relative);if(!file.startsWith(root+path.sep))throw Error('Scope escaped');
 const original=fs.readFileSync(file,'utf8');const code=instrumenter.instrumentSync(original,file);
 const coverage=instrumenter.lastFileCoverage()||emptyCoverage(file);initial[file]=coverage;fs.writeFileSync(file,code);
 const measured=fnKeys(coverage);const found=hints(original);let absent=[];
 if(found.length){
  instrumenter.instrumentSync(original.replace(/\bistanbul(\s+)ignore\b/g,'istanbul$1ignored'),file);
  const unhinted=fnKeys(instrumenter.lastFileCoverage());
  absent=Object.keys(unhinted).filter(slot=>!(slot in measured));
  if(absent.length)ignored[file]=absent.map(slot=>({key:slot,hint:found.join(',')}));
 }
 rows.push({file:relative,originalSha256:crypto.createHash('sha256').update(original).digest('hex'),instrumentedSha256:crypto.createHash('sha256').update(code).digest('hex'),functions:Object.keys(coverage.f).length,ignoreDirectives:found.length,instrumenterIgnored:absent.length});
}
fs.writeFileSync(spec.initial,JSON.stringify(initial));fs.writeFileSync(spec.audit,JSON.stringify(rows,null,2));
if(spec.ignored)fs.writeFileSync(spec.ignored,JSON.stringify(ignored,null,2));
