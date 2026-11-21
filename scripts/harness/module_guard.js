'use strict';
const fs=require('fs'),path=require('path'),Module=require('module');
const real=fs.realpathSync.bind(fs);
function canonical(p){
 const tail=[];p=path.resolve(p);
 for(;;){try{return path.join(real(p),...tail);}catch(e){if(!['ENOENT','ENOTDIR'].includes(e.code))throw e;const parent=path.dirname(p);if(parent===p)throw e;tail.unshift(path.basename(p));p=parent;}}
}
const allowed=JSON.parse(process.env.HYBRID_ALLOWED_MODULE_ROOTS||'[]').map(p=>real(p));
if(!allowed.length)throw Error('Allowed module roots are missing');
const crypto=require('crypto');
const recoveryHelpers=new Set(JSON.parse(process.env.HYBRID_RECOVERY_HELPERS||'[]').map(x=>{
 const file=real(x.file);if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==x.sha256)throw Error('Recovery helper SHA differs');return file;
}));
const recoveryRoots=JSON.parse(process.env.HYBRID_RECOVERY_MODULE_ROOTS||'[]').map(p=>real(p));
const boundaries=JSON.parse(process.env.HYBRID_DEPLOYMENT_BOUNDARIES||'[]');
for(const b of boundaries){b.root=real(b.root);b.files=new Set(b.files);b.packages.sort((a,c)=>c.path.length-a.path.length);}
const original=Module._resolveFilename;
Module._resolveFilename=function(request,parent,...args){
 const result=original.call(this,request,parent,...args);if(!path.isAbsolute(result))return result;
 // Node can return a cached resolution after a fixture has been removed.
 // Preserve that resolution behavior while checking its physical ancestors.
 const actual=canonical(result);
 const owner=parent&&parent.filename;
 const recoveryParent=owner&&(recoveryHelpers.has(owner)||recoveryRoots.some(p=>owner===p||owner.startsWith(p+path.sep)));
 const supportImport=recoveryParent&&recoveryRoots.some(p=>actual===p||actual.startsWith(p+path.sep));
 if(!allowed.some(p=>actual===p||actual.startsWith(p+path.sep))&&!supportImport)throw Error('HYBRID_UNQUALIFIED_EXTERNAL_MODULE: '+actual+' from '+owner);
 if(owner&&!request.startsWith('.')&&!path.isAbsolute(request)){
  const name=request.startsWith('@')?request.split('/').slice(0,2).join('/'):request.split('/')[0];
  for(const b of boundaries){
   if(!owner.startsWith(b.root+path.sep))continue;
   const rel=path.relative(b.root,owner).split(path.sep).join('/');if(!b.files.has(rel))continue;
   const pkg=b.packages.find(p=>!p.path||rel.startsWith(p.path+'/'));
   if(pkg&&pkg.dependencies.includes(name)&&!actual.startsWith(b.root+path.sep))throw Error('HYBRID_REMOVED_PRODUCTION_DEPENDENCY_FALLBACK: '+name+' -> '+actual);
  }
 }
 return result;
};
// Node's relativeResolveCache can return a loaded module without consulting
// _resolveFilename. Check every load as well, including that fast path.
const load=Module._load;
Module._load=function(request,parent,isMain){
 Module._resolveFilename(request,parent,isMain);
 return load.apply(this,arguments);
};
