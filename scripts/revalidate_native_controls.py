#!/usr/bin/env python3
"""Check saved native outputs with the current dependency fallback guard.

No transformations, primary timing measurements or successful table values are
resampled. Previously failed native reductions are retained in the source index.
"""
import argparse,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import ROOT,Context,read,write,sha,snapshot,same
from experiments.admission import units
from experiments.baselines import harness,cohort

p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--index',required=True);p.add_argument('--selection',choices=['validated','failed'],default='validated');p.add_argument('--libraries',nargs='+');a=p.parse_args();c=Context(a.run_id)
if a.libraries:c.manifest=[x for x in c.manifest if x['library'] in a.libraries]
try:
 units(c);rows=[];controls={};index=read(a.index);assert index['status']=='completed'
 for ref in index['rows']:
  if a.libraries and ref['library'] not in a.libraries:continue
  directory=ROOT/'runs'/ref['runId'];source=directory/'external-baselines/results.json';state=read(directory/'status.json');assert state['status'] in ['completed','completed-with-gates'] and not state.get('changedInputTrees') and not state.get('changedImplementation')
  for old in read(source):
   lib=old['library'];method=old['method'];row={'library':lib,'method':method,'sourceRun':ref['runId'],'sourceResultSha256':sha(source),'previousStatus':old['status'],'primaryExperimentsResampled':False};rows.append(row)
   selected=old['status']=='validated' if a.selection=='validated' else old['status']=='transformed-full-suite-failed'
   if not selected:row.update(status='not-selected-prior-observation-preserved');continue
   q=c.qualified[lib];target=Path(old['target']);saved=directory/'external-baselines'/(method+'-'+lib+'-after.json');assert cohort(target,read(q['scope']))==read(saved),'Saved transformed cohort changed'
   if lib not in controls:
    control=harness(c,lib,q,q['deployment'],'current-adapter-original-'+lib);controls[lib]=c.run('current-adapter-original-'+lib,q['command'],control)
   row['originalControl']=controls[lib]
   if not same(q['original'],controls[lib]):
    row.update(status='blocked-original-adapter-control');write(c.out/'external-baselines/current-guard-controls.json',rows);continue
   c.inputSnapshots[str(target)]=snapshot(target,include_all=True);c.inputSnapshotAlgorithms[str(target)]=True
   tag='guard-revalidation-'+lib+'-'+method;view=harness(c,lib,q,target,tag);stage=c.run(tag,q['command'],view)
   row.update(status='validated-current-guard' if same(q['original'],stage) else 'failed-current-guard',core=stage,cohortSha256=sha(saved),transformationsRerun=0)
   write(c.out/'external-baselines/current-guard-controls.json',rows)
 write(c.out/'external-baselines/current-guard-controls.json',rows)
 c.record['stages'].append({'name':'native-current-dependency-guard-validation','status':'passed' if all(r['status'] not in ['failed-current-guard','blocked-original-adapter-control'] for r in rows) else 'blocked','rows':len(rows),'selection':a.selection,'transformationsRerun':0,'primaryExperimentsResampled':False});c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
