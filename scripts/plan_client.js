'use strict';
// Close a copied client over its existing installed packages. Do not install,
// update, or execute package lifecycle code while constructing the input.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const spec=JSON.parse(fs.readFileSync(process.argv[2])),root=fs.realpathSync(spec.source);
const links=[],packages=new Map(),bindings=[],bindingGroups={},missing=[],pending=[];
const inside=p=>p===root||p.startsWith(root+path.sep);
const relative=p=>path.relative(root,p).split(path.sep).join('/');
const id=p=>crypto.createHash('sha256').update(p).digest('hex').slice(0,20);
function pkgAt(p){try{return JSON.parse(fs.readFileSync(path.join(p,'package.json'),'utf8'));}catch(e){return null;}}
const self=pkgAt(root);
function resolvePkg(name,owner){
 try{return path.dirname(require.resolve(name+'/package.json',{paths:[owner]}));}catch(e){}
 for(let dir=owner;;dir=path.dirname(dir)){
  const candidate=path.join(dir,'node_modules',name);if(pkgAt(candidate))return fs.realpathSync(candidate);
  if(path.dirname(dir)===dir)break;
 }
 return null;
}
function intern(source){
 source=fs.realpathSync(source);
 if(inside(source))return relative(source);
 if(!packages.has(source)){
  const pkg=pkgAt(source);if(!pkg)throw Error('External module has no package.json: '+source);
  const dest='node_modules/.hybrid-private/'+id(source);
  const row={source,dest,name:pkg.name,version:pkg.version,edges:[],binding:pkg.name===spec.library&&pkg.version===spec.version};
  packages.set(source,row);pending.push(row);if(row.binding){bindings.push(dest);bindingGroups[dest]=id(source);}
 }
 return packages.get(source).dest;
}
function link(source,rel){
 let target;
 try{target=fs.realpathSync(source);}catch(e){links.push({path:rel,target:'node_modules/.hybrid-missing/'+id(source),brokenOriginal:true,original:fs.readlinkSync(source),error:String(e)});return;}
 if(inside(target)){links.push({path:rel,target:relative(target)});return;}
 let dir=fs.statSync(target).isDirectory()?target:path.dirname(target);
 while(!pkgAt(dir)&&path.dirname(dir)!==dir)dir=path.dirname(dir);
 const pkg=pkgAt(dir);
 if(pkg){
  if(self&&pkg.name===self.name&&pkg.version===self.version&&dir===target){links.push({path:rel,target:'.',restoredSelfLink:true});return;}
  links.push({path:rel,target:intern(dir)+(dir===target?'':'/'+path.relative(dir,target).split(path.sep).join('/'))});
 }else links.push({path:rel,externalAsset:target});
}
function walk(dir){
 const pkg=pkgAt(dir);const rel=relative(dir);
 if(dir!==root&&rel.split('/').includes('node_modules')&&pkg&&pkg.name===spec.library&&pkg.version===spec.version){bindings.push(rel);bindingGroups[rel]=id(fs.realpathSync(dir));return;}
 for(const item of fs.readdirSync(dir,{withFileTypes:true})){
  if(['.git','coverage','.nyc_output'].includes(item.name))continue;
  const p=path.join(dir,item.name),r=relative(p);
  if(item.isSymbolicLink()){
   const q=pkgAt(p);
   if(r.split('/').includes('node_modules')&&q&&q.name===spec.library&&q.version===spec.version){bindings.push(r);bindingGroups[r]=id(fs.realpathSync(p));continue;}
   link(p,r);
  }else if(item.isDirectory())walk(p);
 }
}
walk(root);
for(let i=0;i<pending.length;i++){
 const row=pending[i];if(row.binding)continue;
 const pkg=pkgAt(row.source);const names=new Set([...Object.keys(pkg.dependencies||{}),...Object.keys(pkg.optionalDependencies||{}),...Object.keys(pkg.peerDependencies||{})]);
 for(const name of names){
  const source=resolvePkg(name,row.source);
  if(!source){missing.push({owner:row.source,name,optional:!!(pkg.optionalDependencies||{})[name],peer:!!(pkg.peerDependencies||{})[name]});continue;}
  row.edges.push({name,target:intern(source)});
 }
 function ownLinks(dir){
  for(const item of fs.readdirSync(dir,{withFileTypes:true})){
   if(['node_modules','.git'].includes(item.name))continue;
   const p=path.join(dir,item.name),rel=row.dest+'/'+path.relative(row.source,p).split(path.sep).join('/');
   if(item.isSymbolicLink())link(p,rel);else if(item.isDirectory())ownLinks(p);
  }
 }
 ownLinks(row.source);
}
fs.writeFileSync(spec.output,JSON.stringify({source:root,library:spec.library,version:spec.version,links,packages:[...packages.values()],bindings:[...new Set(bindings)].sort(),bindingGroups,missing},null,2));
console.log(JSON.stringify({bindings:bindings.length,externalPackages:packages.size,links:links.length,unresolvedDeclaredDependencies:missing.length}));
