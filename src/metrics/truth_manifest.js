'use strict';
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const R = path.resolve(__dirname, '../..');
const deps = ''; 
const parser = require(deps + '@babel/parser');
const traverse = require(deps + '@babel/traverse').default;
const generate = require(deps + '@babel/generator').default;
const t = require(deps + '@babel/types');
const utils = require(R + '/src/transformer/stubUtils');
const resolveProduction = require(R + '/src/static/src/utils/dependencies').productionPackages;
const digest = code => crypto.createHash('sha256').update(code).digest('hex');
function parse(code) {
  let last;
  for (const typing of [[], ['flow'], ['typescript']]) {
    try { return parser.parse(code, {sourceType:'unambiguous', allowReturnOutsideFunction:true,
      allowAwaitOutsideFunction:true, plugins:['jsx','classProperties','classPrivateProperties','classPrivateMethods','dynamicImport'].concat(typing)}); }
    catch (error) { last = error; }
  }
  throw last;
}
function files(root) {
  if (!global.scopeFiles) throw new Error('Explicit scopeFiles required');
  return global.scopeFiles.map(rel => {
    const p=path.resolve(root,rel);
    if(!p.startsWith(root+path.sep)||!fs.existsSync(p)||!fs.realpathSync(p).startsWith(root+path.sep)) throw new Error('Invalid scope file '+rel);
    return p;
  }).sort();
}
function collect(root, variants, instrument) {
  root = fs.realpathSync(root);
  const result = {root:root, fileCohort:'Own non-test deployment .js/.mjs/.cjs and complete resolved production package JavaScript; excludes docs/build/externs; includes short and unsupported-for-stubbing functions', files:[], functions:[], errors:[], variantErrors:[]};
  for (const file of files(root)) {
    const relative = path.relative(root,file), original = fs.readFileSync(file,'utf8');
    if (!fs.realpathSync(file).startsWith(root + '/')) throw new Error('Unsafe instrument path: ' + file);
    let ast;
    try { ast = parse(original); }
    catch (error) { result.errors.push({file:relative, error:String(error)}); continue; }
    const rows = [];
    const prediction = {};
    for (const [method, variant] of Object.entries(variants)) {
      const target = path.join(variant,relative);
      const snapshot = fs.existsSync(target + '.original') ? target + '.original' : target;
      let sourceMatches = fs.existsSync(snapshot) && digest(fs.readFileSync(snapshot)) === digest(original);
      if (!sourceMatches) result.variantErrors.push({method:method,file:relative,reason:'Original source SHA differs or is missing'});
      const sidecars = fs.existsSync(target + '.dir') ? fs.readdirSync(target + '.dir').filter(n=>n.endsWith('.BIGG')) : [];
      prediction[method] = {uidGenerator: require(path.resolve(variant, '../..', 'stubUtils.js')), target:target, sourceMatches:sourceMatches, fileStub:fs.existsSync(target + '.BIGG'), sidecars:sidecars, ranges:[]};
    }
    traverse(ast, {Function(p) {
      const n = p.node;
      if (!n.body || !n.loc) return;
      const row = {id:relative+'#'+n.type+'@'+n.start+':'+n.end,file:relative,
        scope:relative.startsWith('node_modules/')?'production-dependency':'library',
        kind:n.type, start:n.start,end:n.end,loc:n.loc,bodyLoc:n.body.loc,
        lineSpan:n.loc.end.line-n.loc.start.line,async:!!n.async,generator:!!n.generator,
        predictedBloated:{}, directPayload:{}};
      for (const [method, pred] of Object.entries(prediction)) {
        const uid = pred.uidGenerator.generateNodeUID(n,pred.target,true);
        row.directPayload[method] = pred.sidecars.includes(uid+'.BIGG');
        if (row.directPayload[method]) pred.ranges.push([n.body.start,n.body.end]);
      }
      rows.push({row:row, node:n});
    }});
    for (const item of rows) {
      for (const [method,pred] of Object.entries(prediction))
        item.row.predictedBloated[method] = pred.sourceMatches ? pred.fileStub || item.row.directPayload[method] || pred.ranges.some(r=>item.row.start>=r[0] && item.row.end<=r[1]) : null;
      result.functions.push(item.row);
    }
    result.files.push({file:relative,sha256:digest(original),functions:rows.length,scriptId:'@file:'+relative});
    if (!instrument || !rows.length) continue;
    let alias, getter;
    traverse(ast, {Program(p) {
      alias=p.scope.generateUidIdentifier('bloatTruth010');
      if (!p.scope.hasBinding('globalThis',true)) getter=t.identifier('globalThis');
      else if (!p.scope.hasBinding('Function',true)) getter=t.callExpression(t.callExpression(t.identifier('Function'),[t.stringLiteral('return this')]),[]);
      else throw new Error('Both collector global entrypoints are shadowed: '+relative);
      p.stop();
    }});
    // The collector is supplied to ordinary Node globals and every VM context.
    // Missing collectors cause a test failure rather than silent false truth.
    // A hoisted forwarding function also works when a circular ESM import
    // calls a hoisted original function before this module's first statement.
    const parameter=t.identifier('truthId010');
    const init=t.functionDeclaration(t.cloneNode(alias),[parameter],t.blockStatement([
      t.returnStatement(t.callExpression(t.memberExpression(getter,t.stringLiteral('__bloatIndependentTruth010'),true),[t.cloneNode(parameter)]))
    ]));
    ast.program.body.unshift(init,t.expressionStatement(t.callExpression(t.cloneNode(alias),[t.stringLiteral('@file:'+relative)])));
    for (const item of rows) {
      const call = t.callExpression(t.cloneNode(alias),[t.stringLiteral(item.row.id)]);
      if (item.node.body.type === 'BlockStatement') item.node.body.body.unshift(t.expressionStatement(call));
      else item.node.body = t.sequenceExpression([call,item.node.body]);
    }
    const code = generate(ast,{retainLines:true,comments:true},original).code;
    fs.writeFileSync(file,code);
    result.files[result.files.length-1].instrumentedSha256=digest(code);
  }
  return result;
}
if (require.main === module) {
  const spec = JSON.parse(fs.readFileSync(process.argv[2]));
  global.scopeFiles=spec.scopeFiles;
  const result = collect(spec.root,spec.variants||{},spec.instrument!==false);
  fs.writeFileSync(spec.output,JSON.stringify(result,null,2));
  console.log(JSON.stringify({files:result.files.length,functions:result.functions.length,errors:result.errors,variantErrors:result.variantErrors.length}));
  if (result.errors.length || result.variantErrors.length) process.exitCode=1;
}
module.exports={collect:collect,parse:parse};
