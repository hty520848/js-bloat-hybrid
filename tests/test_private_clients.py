import unittest,tempfile,subprocess,json,os,shutil
from pathlib import Path
from types import SimpleNamespace
from experiments.common import ROOT,read,snapshot
from experiments.clients import bind
from release_test_support import release_machine

class PrivateClientTests(unittest.TestCase):
 def test_closed_modules_and_singleton_target_bindings(self):
  machine=release_machine();node=machine['nodeTest'];base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   temp=Path(td);source=temp/'source';source.mkdir();(source/'node_modules').mkdir();(source/'package.json').write_text('{"name":"client","version":"1.0.0"}')
   outer=temp/'external';lib=outer/'node_modules/mylib';lib.mkdir(parents=True);(lib/'package.json').write_text('{"name":"mylib","version":"1.0.0","main":"index.js"}');(lib/'index.js').write_text('module.exports={value:"old"};')
   leaf=outer/'node_modules/leaf';leaf.mkdir();(leaf/'package.json').write_text('{"name":"leaf","version":"1.0.0","main":"index.js"}');(leaf/'index.js').write_text('module.exports=7;')
   helper=outer/'node_modules/helper';helper.mkdir();(helper/'package.json').write_text('{"name":"helper","version":"1.0.0","main":"index.js","dependencies":{"mylib":"1.0.0","leaf":"1.0.0"}}');(helper/'index.js').write_text('module.exports={lib:require("mylib"),leaf:require("leaf")};')
   for name,p in [('aliasA',lib),('aliasB',lib),('helper',helper)]: (source/'node_modules'/name).symlink_to(p)
   (source/'node_modules/self').symlink_to(source)
   dest=temp/'cache';plan=temp/'plan.json'
   subprocess.run(['python3',str(ROOT/'scripts/materialize_client.py'),'--source',str(source),'--destination',str(dest),'--library','mylib','--version','1.0.0','--node',node,'--plan',str(plan)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   data=read(plan);self.assertEqual(len(data['bindings']),3);snapshot(dest,include_all=True)
   fresh=temp/'released';fresh.mkdir();(fresh/'package.json').write_text('{"name":"mylib","version":"1.0.0","main":"index.js"}');(fresh/'index.js').write_text('module.exports={value:99};')
   work=ROOT/'work'/('code-validation-'+temp.name);work.mkdir(parents=True)
   try:
    bound=bind(SimpleNamespace(work=work),{'root':str(dest),'targetBindings':data['bindings'],'targetBindingGroups':data['bindingGroups']},fresh,'client')
    code='const a=require("aliasA"),b=require("aliasB"),h=require("helper");if(a!==b||a!==h.lib||a.value!==99||h.leaf!==7)throw Error("Binding or closure mismatch");'
    subprocess.run([node,'-e',code],cwd=str(bound),env=dict(os.environ,NODE_PATH=''),check=True)
    self.assertEqual((lib/'index.js').read_text(),'module.exports={value:"old"};')
   finally:shutil.rmtree(str(work))
 def test_external_write_rejected(self):
  m=release_machine();base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);old=p/'protected';old.mkdir();(old/'original.txt').write_text('unchanged');allowed=p/'owned';allowed.mkdir()
   env=dict(os.environ,SQJ_ALLOWED_WRITE_ROOTS=json.dumps([str(allowed)]),NODE_OPTIONS='--require '+str(ROOT/'scripts/harness/fs_guard.js'))
   code='const fs=require("fs");let rejected=false;try{fs.writeFileSync(process.argv[1],"bad")}catch(e){rejected=e.code==="EACCES"}if(!rejected)process.exit(1);'
   subprocess.run([m['nodeTest'],'-e',code,str(old/'original.txt')],env=env,check=True);self.assertEqual((old/'original.txt').read_text(),'unchanged')
 def test_external_module_and_removed_dependency_fallback_rejected(self):
  m=release_machine();base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);allowed=p/'owned';allowed.mkdir();outside=p/'external.js';outside.write_text('module.exports=42;')
   app=allowed/'app';prod=app/'node_modules/prod';prod.mkdir(parents=True);fallback=app/'node_modules/dep';fallback.mkdir()
   (prod/'index.js').write_text('module.exports=require("dep");');(fallback/'index.js').write_text('module.exports=7;')
   env=dict(os.environ,HYBRID_ALLOWED_MODULE_ROOTS=json.dumps([str(allowed)]),HYBRID_DEPLOYMENT_BOUNDARIES=json.dumps([{'root':str(prod),'files':['index.js'],'packages':[{'path':'','dependencies':['dep']}]}]),NODE_OPTIONS='--require '+str(ROOT/'scripts/harness/module_guard.js'))
   code='for(const [p,expected] of [[process.argv[1],"HYBRID_UNQUALIFIED_EXTERNAL_MODULE"],[process.argv[2],"HYBRID_REMOVED_PRODUCTION_DEPENDENCY_FALLBACK"]]){let rejected=false;try{require(p)}catch(e){rejected=e.message.includes(expected)}if(!rejected)throw Error("Guard failed: "+expected)}'
   subprocess.run([m['nodeTest'],'-e',code,str(outside),str(prod/'index.js')],env=env,check=True)
 def test_cached_resolution_after_fixture_removal_matches_native_node(self):
  m=release_machine();base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);code='const fs=require("fs"),p=require("path").resolve("ephemeral.js");fs.writeFileSync(p,"module.exports=1");const first=require.resolve(p);fs.unlinkSync(p);if(require.resolve(p)!==first)throw Error("Cached resolution changed");'
   env=dict(os.environ,HYBRID_ALLOWED_MODULE_ROOTS=json.dumps([str(p)]),HYBRID_DEPLOYMENT_BOUNDARIES='[]',NODE_OPTIONS='--require '+str(ROOT/'scripts/harness/module_guard.js'))
   subprocess.run([m['nodeTest'],'-e',code],cwd=str(p),env=dict(os.environ,NODE_OPTIONS=''),check=True)
   subprocess.run([m['nodeTest'],'-e',code],cwd=str(p),env=env,check=True)
if __name__=='__main__':unittest.main()
