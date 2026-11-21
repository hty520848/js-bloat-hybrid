#!/usr/bin/env python3
"""Reuse unchanged runtime admission and rerun only failed libraries on private copies."""
import argparse,copy,json,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,ROOT,read,write,sha,clone,same,snapshot
from experiments.rq1.run import dynamic

def require(ok,message):
 if not ok:raise ValueError(message)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-id',required=True);p.add_argument('--source-admission',required=True);a=p.parse_args()
 prior=Path(a.source_admission).resolve();old=read(prior)
 for name,x in old['runtime'].items():require(sha(x['path'])==x['sha256'],'Runtime changed: '+name)
 for filename,expected in old['analysisSources'].items():require(sha(filename)==expected,'Analysis changed: '+filename)
 c=Context(a.run_id)
 for name,x in old['runtime'].items():c.machine[name]=x['path']
 proof={'schemaVersion':1,'libraries':{},'runtime':old['runtime'],'analysisSources':old['analysisSources'],'runId':a.run_id,'status':'running','sourceAdmission':str(prior),'sourceAdmissionSha256':sha(prior),'policy':'Reuse verified complete controls; failed libraries run unchanged suites on physically private source copies. Verbose reporting changes no tests or assertions.'}
 try:
  for lib,row in sorted(old['libraries'].items()):
   require(row['sourceRoot']==c.machine['targets'][lib]['root'],'Source root differs: '+lib)
   require(all(sha(Path(row['sourceRoot'])/f)==h for f,h in row['sourceHashes'].items()),'Source changed: '+lib)
   lock=Path(row['sourceRoot'])/'package-lock.json';require(sha(lock)==c.machine['targets'][lib]['dependencyLockSha256'],'Dependency lock changed: '+lib)
   require(sha(row['original']['log'])==row['original']['logSha256'],'Original control log changed: '+lib)
   if row['qualified']:
    for field in ['plainGraal','profiled']:require(sha(row[field]['log'])==row[field]['logSha256'],'Admission log changed: '+lib)
    require(same(row['original'],row['plainGraal']) and same(row['original'],row['profiled']),'Incomplete prior suite: '+lib)
    reused=copy.deepcopy(row);reused['reusedFrom']=str(prior);proof['libraries'][lib]=reused
  write(c.out/'runtime-admission.json',proof)
  for lib,row in sorted(old['libraries'].items()):
   if row['qualified']:continue
   cfg=c.machine['targets'][lib];private=clone(cfg['root'],c.work/'runtime'/lib)
   before={f:sha(private/f) for f in row['sourceHashes']};require(before==row['sourceHashes'],'Private copy source differs')
   command=cfg['command']+(['--verbose'] if 'jest' in cfg['command'][1] else [])
   limit=c.protocol.get('profileTimeoutByLibrary',{}).get(lib,c.protocol['profileTimeoutSeconds'])
   # NodeProf's classpath option selects the JVM backend. Validate the same
   # backend explicitly; Graal's default native backend can crash in Jest.
   plain=c.run('runtime-plain-'+lib,[c.machine['graalNode'],'--jvm']+command[1:],private,timeout=limit)
   q={'root':private,'command':command,'original':row['original'],'scope':prior.parent/'inputs'/(lib+'-scope.json')}
   dg=dynamic(c,lib,q,'runtime-profile-'+lib) if same(row['original'],plain) else None
   current={'sourceRoot':cfg['root'],'executionRoot':str(private),'sourceHashes':before,'fullSuite':True,'original':row['original'],'plainGraal':plain,'profiled':dg['stage'] if dg else None,'dynamic':dg,'mappingValid':bool(dg and dg['valid']),'traceBalanced':bool(dg and dg.get('metadata') and not dg['metadata'].get('stackMismatches') and not dg['metadata'].get('remainingUserFrames')),'productionUnchanged':all(sha(private/f)==before[f] and sha(Path(cfg['root'])/f)==before[f] for f in before)}
   current['plainBackend']='JVM explicitly selected with --jvm'
   current['qualified']=current['productionUnchanged'] and current['mappingValid'] and current['traceBalanced'] and same(row['original'],plain) and same(row['original'],current['profiled'])
   proof['libraries'][lib]=current;write(c.out/'runtime-admission.json',proof)
  require(set(proof['libraries'])==set(old['libraries']),'Admission roster changed')
  proof['status']='qualified' if all(x['qualified'] for x in proof['libraries'].values()) else 'not-qualified'
  write(c.out/'runtime-admission.json',proof);c.record.update(status=proof['status'],scientificExperiment=False);c.save()
 except Exception:
  c.record.update(status='failed',error=traceback.format_exc(),scientificExperiment=False);c.save();raise
 print(c.out/'runtime-admission.json')
if __name__=='__main__':main()
