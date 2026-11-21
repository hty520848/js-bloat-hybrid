#!/usr/bin/env python3
"""Generate real ten-library admission records for run_rq1_only.py.

Runs unchanged complete target suites with the configured test runtime, the
candidate plain Graal runtime, and NodeProf. No RQ2/RQ3/RQ4 measurements.
Plain-runtime failures are preserved and prevent profiling that library.
"""
import argparse,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,read,write,sha,same
from experiments import prepare
from experiments.rq1.run import dynamic

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-id',required=True)
 for name in ['graal-node','nodeprof-loader','nodeprof-jar']:p.add_argument('--'+name)
 a=p.parse_args();c=Context(a.run_id)
 try:
  for field,name in [('graalNode','graal_node'),('nodeprofLoader','nodeprof_loader'),('nodeprofJar','nodeprof_jar')]:
   if getattr(a,name):c.machine[field]=str(Path(getattr(a,name)).resolve())
  c.machine['clients']={}
  write(c.out/'effective-machine.json',c.machine)
  prepare.run(c)
  source_root=Path(__file__).resolve().parents[1]
  analysis_files=['src/dynamic/dyn-with-source.js','src/dynamic/map_executed_source.js','experiments/rq1/run.py','src/transformer/nodeprofTargets.js']
  proof={'schemaVersion':1,'libraries':{},'runtime':{},'runId':a.run_id,'status':'running','analysisSources':{str(source_root/name):sha(source_root/name) for name in analysis_files}}
  for field in ['graalNode','nodeprofLoader','nodeprofJar']:
   filename=Path(c.machine[field]);proof['runtime'][field]={'path':str(filename),'sha256':sha(filename)}
  for lib,q in sorted(c.qualified.items()):
   files=read(q['scope'])['files'];before={f:sha(q['root']/f) for f in files}
   timeout=c.protocol.get('profileTimeoutByLibrary',{}).get(lib,c.protocol['profileTimeoutSeconds'])
   plain=c.run('runtime-plain-'+lib,[c.machine['graalNode']]+q['command'][1:],q['root'],timeout=timeout)
   dg=dynamic(c,lib,q,'runtime-profile-'+lib) if same(q['original'],plain) else None
   row={'sourceRoot':str(q['root']),'sourceHashes':before,'fullSuite':True,'original':q['original'],'plainGraal':plain,'profiled':dg['stage'] if dg else None,'mappingValid':bool(dg and dg['valid']),'traceBalanced':bool(dg and dg.get('metadata') and not dg['metadata'].get('stackMismatches') and not dg['metadata'].get('remainingUserFrames')),'productionUnchanged':all(sha(q['root']/f)==before[f] for f in files)}
   row['qualified']=row['productionUnchanged'] and row['mappingValid'] and row['traceBalanced'] and same(row['original'],row['plainGraal']) and same(row['original'],row['profiled'])
   proof['libraries'][lib]=row;write(c.out/'runtime-admission.json',proof)
  plan=read(Path(__file__).resolve().parents[1]/'experiments/rq1/ablation-plan-20261102.json')
  ready=set(proof['libraries'])==set(plan['libraries']) and all(r['qualified'] for r in proof['libraries'].values())
  proof['status']='qualified' if ready else 'not-qualified';write(c.out/'runtime-admission.json',proof)
  c.record.update(status=proof['status'],scientificExperiment=False,scope='runtime admission, no outcome-ranking experiments');c.save()
 except Exception:
  c.record.update(status='failed',error=traceback.format_exc());c.save();raise
 print(c.out/'runtime-admission.json')
if __name__=='__main__':main()
