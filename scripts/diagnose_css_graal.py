#!/usr/bin/env python3
"""Isolated CSS-loader startup probes. Diagnostic results never qualify a full suite."""
import argparse,json,sys,traceback,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,clone,read,write,sha

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-id',required=True);p.add_argument('--runtime-proof',required=True);a=p.parse_args()
 c=Context(a.run_id);proof=read(a.runtime_proof);c.machine['graalNode']=proof['runtime']['graalNode']['path']
 q=c.machine['targets']['css-loader'];target=clone(q['root'],c.work/'css-loader')
 scope=read(Path(a.runtime_proof).parent/'inputs/css-loader-scope.json');before={f:sha(target/f) for f in scope['files']}
 diagnostic={'scientificExperiment':False,'fullSuiteQualification':False,'target':str(target),'sourceHashes':before,'runtime':proof['runtime'],'probes':[]}
 write(c.out/'diagnostic.json',diagnostic)
 code="console.error('BOOT',process.version);for (const name of ['jest','webpack']) {const t=Date.now();console.error('REQUIRE_START',name);require(name);console.error('REQUIRE_DONE',name,Date.now()-t);}console.error('DONE');"
 try:
  for runtime,key,limit in [(c.machine['nodeTest'],'node-startup',60),(c.machine['graalNode'],'graal-startup',180)]:
   diagnostic['probes'].append(c.run(key,[runtime,'-e',code],target,timeout=limit));write(c.out/'diagnostic.json',diagnostic)
  diagnostic['probes'].append(c.run('graal-small-suite',[c.machine['graalNode']]+q['command'][1:]+['--runTestsByPath','test/runtime/api.test.js','--verbose'],target,timeout=240));write(c.out/'diagnostic.json',diagnostic)
  diagnostic['productionUnchanged']=all(sha(target/f)==before[f] for f in before)
  c.record.update(status='diagnostics-completed',scientificExperiment=False);write(c.out/'diagnostic.json',diagnostic);c.save()
 except Exception:
  c.record.update(status='failed',error=traceback.format_exc(),scientificExperiment=False);c.save();raise
if __name__=='__main__':main()
