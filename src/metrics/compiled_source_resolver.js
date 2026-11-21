"use strict";
// Retain TypeScript test assertions while exercising packaged Memfs JavaScript.
const fs=require('fs'),path=require('path');
module.exports=function(request,options){
 const resolved=options.defaultResolver(request,options),root=process.cwd();
 const relative=path.relative(path.join(root,'src'),resolved);
 if(relative.startsWith('..')||path.isAbsolute(relative)||relative.split(path.sep).includes('__tests__')||!/\.ts$/.test(relative)||/\.d\.ts$/.test(relative))return resolved;
 const compiled=path.join(root,'lib',relative.replace(/\.ts$/,'.js'));
 if(!fs.existsSync(compiled))throw Error('Missing packaged production equivalent of '+relative);
 return compiled;
};
