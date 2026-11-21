'use strict';
// Materialize hoisted test dependencies under their provider, without changing
// the measured production root's package.json or production dependency versions.
const fs=require('fs'),path=require('path');
const spec=JSON.parse(fs.readFileSync(process.argv[2]));const rows=[],missing=[];
function visit(source,dest,ancestors){
 if(rows.length >= (spec.maxPackages||5000)) {
  if(!missing.some(x=>x.budgetExceeded))missing.push({budgetExceeded:true,reason:'Harness closure exceeds fixed 5000-instance budget; requires a lock-preserving hoisted materializer.'});
  return;
 }
 source=fs.realpathSync(source);const pkg=JSON.parse(fs.readFileSync(path.join(source,'package.json')));
 if(ancestors.includes(source))return;
 rows.push({source,dest,name:pkg.name,version:pkg.version});
 for(const name of Object.keys(pkg.dependencies||{})){
  let dep;try{dep=path.dirname(require.resolve(name+'/package.json',{paths:[source]}));}
  catch(e){if(!(pkg.optionalDependencies||{})[name])missing.push({source,name,error:String(e)});continue;}
  visit(dep,path.join(dest,'node_modules',name),ancestors.concat(source));
 }
}
for(const p of spec.providers)visit(p.source,p.destination,[]);
fs.writeFileSync(spec.output,JSON.stringify({rows,missing},null,2));if(missing.length)process.exitCode=1;
