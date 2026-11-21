import unittest,tempfile,subprocess,json,os
from pathlib import Path
from experiments.common import ROOT,read,write
from release_test_support import release_machine

class IstanbulProducer(unittest.TestCase):
 def test_offline_instrumentation_collects_normal_and_vm_functions(self):
  m=release_machine();modules=Path(m['targets']['css-loader']['root'])/'node_modules'
  base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);root=p/'source';root.mkdir();(root/'index.js').write_text('module.exports=function answer(x){return x?42:7;};')
   spec=p/'spec.json';initial=p/'initial.json';write(spec,{'root':str(root),'files':['index.js'],'initial':str(initial),'audit':str(p/'audit.json')})
   env=dict(os.environ,NODE_PATH=str(modules),NODE_OPTIONS='')
   subprocess.run([m['nodeTest'],str(ROOT/'src/baselines/instrument_coverage.js'),str(spec)],env=env,check=True)
   self.assertTrue(all(n==0 for v in read(initial).values() for n in v['f'].values()))
   observed=p/'observed';env.update(NODE_OPTIONS='--require '+str(ROOT/'scripts/harness/istanbul_preload.cjs'),HYBRID_ISTANBUL_OUT=str(observed))
   code='const fs=require("fs"),vm=require("vm"),file=process.argv[1];if(require(file)(true)!==42)throw Error("Normal result");const box={module:{exports:{}}};vm.runInNewContext(fs.readFileSync(file,"utf8"),box);if(box.module.exports(false)!==7)throw Error("VM result");'
   subprocess.run([m['nodeTest'],'-e',code,str(root/'index.js')],env=env,check=True)
   files=list(observed.glob('*.json'));self.assertEqual(len(files),1);coverage=read(files[0]);self.assertEqual(sum(sum(v['f'].values()) for v in coverage.values()),2)
   self.assertTrue(all(n>0 for v in coverage.values() for counts in v['b'].values() for n in counts))
if __name__=='__main__':unittest.main()
