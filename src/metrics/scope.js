'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const productionPackages=require('../static/src/utils/dependencies').productionPackages;
const root=fs.realpathSync(process.argv[2]), own=JSON.parse(fs.readFileSync(process.argv[3]));
const semver=require('semver'),files=new Set(),dependencies=[],errors=[];
function inside(p){const q=fs.realpathSync(p);if(q!==root&&!q.startsWith(root+path.sep))throw Error('Production path leaves target: '+p);return q;}
function walk(dir){for(const item of fs.readdirSync(dir,{withFileTypes:true})){
 if(['node_modules','.git','coverage','.nyc_output'].includes(item.name))continue;
 const p=path.join(dir,item.name);inside(p);
 if(item.isDirectory())walk(p);else if(item.isFile()&&item.name.endsWith('.js')&&!p.includes('externs'))files.add(path.relative(root,p));
}}
for(const rel of own){const p=path.resolve(root,rel);inside(p);if(rel.endsWith('.js')&&!p.includes('externs'))files.add(rel);}
const packages=productionPackages(root);
for(const [p,data] of packages){inside(p);walk(p);dependencies.push({path:path.relative(root,p),name:data.name,version:data.version});}
for(const owner of [root,...packages.keys()]){
 const pkg=JSON.parse(fs.readFileSync(path.join(owner,'package.json')));
 for(const [name,range] of Object.entries(pkg.dependencies||{})){
  let dep;try{dep=require.resolve(name+'/package.json',{paths:[owner]});}catch(e){errors.push(String(e));continue;}
  const version=JSON.parse(fs.readFileSync(dep)).version;
  if(semver.validRange(range)&&!semver.satisfies(version,range))errors.push(`${owner}: ${name}@${version} does not satisfy ${range}`);
 }
}
const hashes={};for(const rel of [...files].sort())hashes[rel]=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,rel))).digest('hex');
fs.writeFileSync(process.argv[4],JSON.stringify({files:[...files].sort(),hashes,dependencies,errors},null,2));
if(errors.length)process.exitCode=1;
