'use strict';
// Qualification protects immutable inputs; destructive external tools use the
// stricter allow-only mode. Never follow an output link into a protected tree.
const fs=require('fs'),path=require('path');
const allowed=JSON.parse(process.env.SQJ_ALLOWED_WRITE_ROOTS||'[]').map(p=>path.resolve(p));
const protectedRoots=JSON.parse(process.env.HYBRID_PROTECTED_ROOTS||'[]').map(p=>path.resolve(p));
if(!allowed.length&&!protectedRoots.length)throw Error('Filesystem guard policy is missing');
const exists=fs.existsSync.bind(fs),real=fs.realpathSync.bind(fs);
function resolved(p){p=path.resolve(String(p));const tail=[];while(!exists(p)){const parent=path.dirname(p);if(parent===p)break;tail.unshift(path.basename(p));p=parent;}return path.join(exists(p)?real(p):p,...tail);}
function check(p){
 if(typeof p==='number')return;
 const q=resolved(p),inside=(r)=>q===r||q.startsWith(r+path.sep);
 if(protectedRoots.some(inside)||(allowed.length&&!allowed.some(inside))){const e=Error('HYBRID_WRITE_OUTSIDE_OWNED_EXPERIMENT: '+q);e.code='EACCES';throw e;}
}
for(const name of ['writeFile','appendFile','truncate','unlink','rmdir','rm','mkdir','chmod','chown','lchown','utimes'])for(const suffix of ['','Sync']){
 const key=name+suffix;if(typeof fs[key]!=='function')continue;const fn=fs[key].bind(fs);fs[key]=function(p,...args){check(p);return fn(p,...args);};
}
for(const key of ['rename','renameSync']){const fn=fs[key].bind(fs);fs[key]=function(a,b,...args){check(a);check(b);return fn(a,b,...args);};}
for(const key of ['copyFile','copyFileSync','link','linkSync','symlink','symlinkSync']){if(typeof fs[key]!=='function')continue;const fn=fs[key].bind(fs);fs[key]=function(a,b,...args){check(b);return fn(a,b,...args);};}
for(const key of ['open','openSync']){const fn=fs[key].bind(fs);fs[key]=function(p,flags,...args){if(typeof flags==='number'?(flags&(fs.constants.O_WRONLY|fs.constants.O_RDWR|fs.constants.O_CREAT|fs.constants.O_TRUNC|fs.constants.O_APPEND))!==0:/[wa+]/.test(String(flags)))check(p);return fn(p,flags,...args);};}
const stream=fs.createWriteStream.bind(fs);fs.createWriteStream=function(p,...args){check(p);return stream(p,...args);};
if(fs.promises)for(const key of ['writeFile','appendFile','truncate','unlink','rmdir','rm','mkdir','chmod','chown','utimes']){if(typeof fs.promises[key]!=='function')continue;const fn=fs.promises[key].bind(fs.promises);fs.promises[key]=async function(p,...args){check(p);return fn(p,...args);};}
