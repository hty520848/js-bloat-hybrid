"use strict";
// Resolve actual NodeProf function fragments against a single frozen source file.
// A unique, exact AST identity is required. Unresolved nodes keep the old fallback.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const parser=require('@babel/parser'),traverse=require('@babel/traverse').default;
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const graph=JSON.parse(fs.readFileSync(spec.graph,'utf8'));
const records=JSON.parse(fs.readFileSync(spec.records,'utf8'));
const remap=spec.remap||{},cache=new Map(),replacements=new Map(),audit=[];
const ignored=new Set(['start','end','loc','extra','leadingComments','trailingComments','innerComments','comments','tokens','errors']);
const jestProgramPrefix='({"Object.<anonymous>":function(module,exports,require,__dirname,__filename,global,jest){';
function clean(v){
 if(Array.isArray(v))return v.map(clean);
 if(v&&typeof v==='object'){const out={};for(const k of Object.keys(v).sort())if(!ignored.has(k))out[k]=clean(v[k]);return out;}
 return v;
}
const signature=n=>JSON.stringify(clean({params:n.params,body:n.body,async:!!n.async,generator:!!n.generator}));
const classSignature=n=>JSON.stringify(clean({superClass:n.superClass,body:n.body}));
function parse(code){
 let last;for(const typing of [[],['flow'],['typescript']]){
  try{return parser.parse(code,{sourceType:'unambiguous',allowReturnOutsideFunction:true,plugins:['jsx','classProperties','classPrivateProperties','classPrivateMethods','dynamicImport'].concat(typing)});}catch(e){last=e;}
 }throw last;
}
function index(relative){
 if(cache.has(relative))return cache.get(relative);
 const p=path.resolve(spec.originalRoot,relative);
 if(!p.startsWith(path.resolve(spec.originalRoot)+path.sep)||!fs.existsSync(p)){cache.set(relative,null);return null;}
 const source=fs.readFileSync(p,'utf8'),ast=parse(source),functions=new Map(),classes=new Map();
 traverse(ast,{Function(p){const k=signature(p.node);if(!functions.has(k))functions.set(k,[]);functions.get(k).push(p.node);},Class(p){const k=classSignature(p.node);if(!classes.has(k))classes.set(k,[]);classes.get(k).push(p.node);}});
 const result={source,functions,classes,allFunctions:Array.from(functions.values()).flat(),sha256:crypto.createHash('sha256').update(source).digest('hex')};cache.set(relative,result);return result;
}
function outerNode(code){
 for(const text of [code,'('+code+')','({'+code+'})']){
  try{const ast=parse(text);let found;
   traverse(ast,{Function(p){if(!found){found=p.node;p.stop();}},Class(p){if(!found){found=p.node;p.stop();}}});
   if(found)return found;
  }catch(e){}
 }return null;
}
function ranged(relative,n){return 'ast_'+n.start+'_'+n.end+' ('+relative+':'+n.loc.start.line+':'+(n.loc.start.column+1)+':'+n.loc.end.line+':'+(n.loc.end.column+1)+')';}
for(const r of records){
 const m=r.location.match(/^(.*):(\d+):(\d+):(\d+):(\d+)$/);if(!m)continue;
 const oldRelative=m[1],relative=remap[oldRelative]||oldRelative;
 let ix;try{ix=index(relative);}catch(e){audit.push({label:r.label,status:'parse-error-retained',error:String(e)});continue;}
 if(!ix)continue;
 const physical=path.resolve(spec.executedRoot,oldRelative),code=r.code;let replacement,kind;
 const direct=ix.allFunctions.find(n=>r.source.range&&n.start===r.source.range[0]&&n.end===r.source.range[1]
   &&ix.source.slice(n.start,n.end)===code&&n.loc.start.line===Number(m[2])&&n.loc.start.column+1===Number(m[3])
   &&n.loc.end.line===Number(m[4])&&n.loc.end.column+1===Number(m[5]));
 if(direct){replacement=ranged(relative,direct);kind='exact-original-byte-range';}
 else if(fs.existsSync(physical)&&Buffer.from(code,'utf8').equals(fs.readFileSync(physical))){replacement='anon ('+relative+':{{module}})';kind='byte-identical-module';}
 else if(r.name==='anon'&&m[2]==='1'&&m[3]==='1'&&r.source.name===oldRelative
   &&r.source.range&&r.source.range[0]===0&&r.source.range[1]===code.length
   &&code===jestProgramPrefix+ix.source+'\n}});'){
  replacement='anon ('+relative+':{{module}})';kind='byte-identical-Jest-program';
 }
 else if(r.name==='Object.<anonymous>'&&m[2]==='1'&&m[3]==='24'&&r.source.range[0]===23&&/^function\s*\(module,exports,require,__dirname,__filename(?:,\w+)*\)\s*\{/.test(code)){replacement='anon ('+relative+':{{module}})';kind='Jest-module-wrapper';}
 else if(r.source.range&&ix.source.slice(r.source.range[0],r.source.range[1])===code&&ix.allFunctions.some(n=>n.start===r.source.range[0]&&n.end===r.source.range[1])){
  replacement=ranged(relative,ix.allFunctions.find(n=>n.start===r.source.range[0]&&n.end===r.source.range[1]));kind='exact-original-byte-range';
 }else {
  const n=outerNode(code);
  if(n&&/^(?:ClassDeclaration|ClassExpression)$/.test(n.type)){
   const matches=ix.classes.get(classSignature(n))||[];
   if(matches.length===1){const ctor=matches[0].body.body.find(p=>p.kind==='constructor');replacement=ctor?ranged(relative,ctor):'anon ('+relative+':{{module}})';kind=ctor?'exact-class-constructor':'exact-class-default-constructor';}
  }else if(n){
   const matches=ix.functions.get(signature(n))||[];
   if(matches.length===1){replacement=ranged(relative,matches[0]);kind='unique-exact-function-AST';}
   else if(matches.length>1)kind='ambiguous-AST-retained';
  }
 }
 // A known transformed/ambiguous fragment must not accidentally match some
 // unrelated original function merely because line/column values coincide.
 if(!replacement)replacement='unresolved_ast ('+relative+':0:0:0:0)';
 replacements.set(r.label,replacement);
 audit.push({label:r.label,status:kind||'unresolved-retained',replacement:replacement||null,source:relative,originalFileSha256:ix.sha256,executedFragmentSha256:crypto.createHash('sha256').update(code).digest('hex')});
}
function mapped(label){
 if(replacements.has(label))return replacements.get(label);
 const m=label.match(/ \((.*):(\d+:\d+:\d+:\d+|\{\{.*\}\})\)$/);
 if(m&&remap[m[1]])return label.slice(0,m.index+2)+remap[m[1]]+':'+m[2]+')';
 return label;
}
const result={};for(const [caller,callees] of Object.entries(graph)){
 const key=mapped(caller);if(!result[key])result[key]=new Set();callees.forEach(v=>result[key].add(mapped(v)));
}
fs.writeFileSync(spec.output,JSON.stringify(Object.fromEntries(Object.keys(result).sort().map(k=>[k,Array.from(result[k]).sort()])),null,2)+'\n',{flag:'wx'});
fs.writeFileSync(spec.audit,JSON.stringify({criterion:'Actual executed source fragment has a unique, exact AST identity within the same frozen file; no nearest-range or name-only guesses',rows:audit,statusCounts:audit.reduce((a,r)=>(a[r.status]=(a[r.status]||0)+1,a),{})},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({mapped:replacements.size,records:records.length}));
