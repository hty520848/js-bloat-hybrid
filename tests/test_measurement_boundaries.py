import os,subprocess,tempfile,unittest,json
from pathlib import Path
from types import SimpleNamespace
from experiments.common import ROOT,read,write,sha,variant_directory,output_snapshot
from release_test_support import release_machine

class MeasurementBoundaries(unittest.TestCase):
 def test_arm_names_do_not_change_legacy_identifier_length(self):
  m=release_machine();c=SimpleNamespace(work=ROOT/'work/path-length-check')
  files=[str(variant_directory(c,x)/'Data/synthetic/lib.js') for x in ['hybrid','mcg-no-module-filter','sscg','sdcg']]
  code='const u=require(process.argv[1]);const n={body:{loc:{start:{line:1,column:10},end:{line:9,column:1}}}};const ids=JSON.parse(process.argv[2]).map(p=>u.generateNodeUID(n,p,true));if(new Set(ids.map(x=>x.length)).size!==1)throw Error("Arm-dependent identifier size");'
  subprocess.run([m['nodeTest'],'-e',code,str(ROOT/'src/transformer/stubUtils.js'),json.dumps(files)],env=dict(os.environ,NODE_PATH=m['transformerNodeModules']+os.pathsep+m['staticNodeModules'],NODE_OPTIONS=''),check=True)
 def test_recovery_support_cannot_supply_client_dependency_fallback(self):
  m=release_machine();base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);owned=p/'owned';owned.mkdir();tools=p/'tools/node_modules';(tools/'support').mkdir(parents=True);(tools/'support/index.js').write_text('module.exports=42;');(owned/'node_modules').symlink_to(tools)
   helper=owned/'stubbifier_cjs.cjs';helper.write_text('module.exports=require("support");');consumer=owned/'client.js';consumer.write_text('module.exports=require("support");')
   env=dict(os.environ,HYBRID_ALLOWED_MODULE_ROOTS=json.dumps([str(owned)]),HYBRID_DEPLOYMENT_BOUNDARIES='[]',HYBRID_RECOVERY_HELPERS=json.dumps([{'file':str(helper),'sha256':sha(helper)}]),HYBRID_RECOVERY_MODULE_ROOTS=json.dumps([str(tools)]),NODE_OPTIONS='--require '+str(ROOT/'scripts/harness/module_guard.js'))
   code='if(require(process.argv[1])!==42)throw Error("Verified helper support blocked");let blocked=false;try{require(process.argv[2])}catch(e){blocked=e.message.includes("HYBRID_UNQUALIFIED_EXTERNAL_MODULE")}if(!blocked)throw Error("Client dependency was supplied by analysis tools");'
   subprocess.run([m['nodeTest'],'-e',code,str(helper),str(consumer)],env=env,check=True)
 @unittest.skipUnless(hasattr(os, 'mkfifo'), 'Requires POSIX FIFO support')
 def test_generated_links_and_fifo_are_recorded_without_reading_targets(self):
  base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);root=p/'output';root.mkdir();other=p/'outside.txt';other.write_text('not followed');(root/'external').symlink_to(other);os.mkfifo(str(root/'pipe'))
   result=output_snapshot(root);self.assertEqual(result['external'],{'link':str(other)});self.assertIn('specialMode',result['pipe'])
if __name__=='__main__':unittest.main()
