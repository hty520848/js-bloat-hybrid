'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm');
if(!process.env.HYBRID_TRUTH_OUT)throw Error('Missing HYBRID_TRUTH_OUT');
const hits=new Set();const collect=id=>hits.add(id);
Object.defineProperty(global,'__bloatIndependentTruth010',{value:collect,configurable:true});
function inject(obj){obj=obj||{};obj.__bloatIndependentTruth010=collect;return obj;}
const create=vm.createContext;vm.createContext=function(obj,...args){return create.call(this,inject(obj),...args);};
for(const name of ['runInNewContext']){const fn=vm[name];vm[name]=function(code,obj,...args){return fn.call(this,code,inject(obj),...args);};}
process.on('exit',code=>{
 const folder=process.env.HYBRID_TRUTH_OUT;fs.mkdirSync(folder,{recursive:true});
 fs.writeFileSync(path.join(folder,String(process.pid)+'.json'),JSON.stringify({pid:process.pid,exitCode:code,hits:[...hits].sort()}));
});
