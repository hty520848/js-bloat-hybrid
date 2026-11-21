'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm');
if(!process.env.HYBRID_ISTANBUL_OUT)throw Error('Missing HYBRID_ISTANBUL_OUT');
const coverage={};global.__coverage__=coverage;
function inject(obj){obj=obj||{};obj.__coverage__=coverage;return obj;}
const create=vm.createContext;vm.createContext=function(obj,...args){return create.call(this,inject(obj),...args);};
const run=vm.runInNewContext;vm.runInNewContext=function(code,obj,...args){return run.call(this,code,inject(obj),...args);};
process.on('exit',()=>{fs.mkdirSync(process.env.HYBRID_ISTANBUL_OUT,{recursive:true});fs.writeFileSync(path.join(process.env.HYBRID_ISTANBUL_OUT,process.pid+'.json'),JSON.stringify(coverage));});
