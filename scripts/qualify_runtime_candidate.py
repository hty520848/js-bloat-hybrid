#!/usr/bin/env python3
"""Qualify a private runtime on unchanged complete suites; reuse verified V8 controls."""
import argparse,copy,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,ROOT,read,write,sha,same,clone
from experiments.rq1.run import dynamic

def require(value,message):
 if not value:raise ValueError(message)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--run-id',required=True);p.add_argument('--source-admission',required=True);p.add_argument('--runtime-build',required=True)
 a=p.parse_args();prior=Path(a.source_admission).resolve();old=read(prior);buildpath=Path(a.runtime_build).resolve();build=read(buildpath)
 require(build['status']=='smoke-passed','Runtime smoke did not pass')
 for item in list(build['runtime'].values())+[build['runtimeDependencies']['underlyingNode']]:require(sha(item['path'])==item['sha256'],'Runtime dependency differs')
 c=Context(a.run_id)
 for name,item in build['runtime'].items():c.machine[name]=item['path']
 files=['src/dynamic/dyn-with-source.js','src/dynamic/map_executed_source.js','experiments/rq1/run.py','src/transformer/nodeprofTargets.js']
 proof={'schemaVersion':1,'runId':a.run_id,'status':'running','libraries':{},'runtime':build['runtime'],'runtimeDependencies':build['runtimeDependencies'],'analysisSources':{str(ROOT/f):sha(ROOT/f) for f in files},'sourceAdmission':str(prior),'sourceAdmissionSha256':sha(prior),'runtimeBuild':str(buildpath),'runtimeBuildSha256':sha(buildpath),'policy':'Unchanged complete suites on private copies; original V8 controls reused only after source, lock and log identity validation. CSS-loader first. Any qualification failure stops the formal pipeline.'}
 write(c.out/'effective-machine.json',c.machine);write(c.out/'runtime-admission.json',proof)
 try:
  require(set(old['libraries'])=={r['library'] for r in c.manifest},'Library roster differs')
  for lib in sorted(old['libraries'],key=lambda name:(name!='css-loader',name)):
   row=old['libraries'][lib];cfg=c.machine['targets'][lib];root=Path(cfg['root'])
   require(row['sourceRoot']==str(root),'Original source root differs: '+lib)
   require(cfg['command']==row['original']['command'],'Original command differs: '+lib)
   require(sha(root/'package-lock.json')==cfg['dependencyLockSha256'],'Dependency lock differs: '+lib)
   require(all(sha(root/f)==h for f,h in row['sourceHashes'].items()),'Production scope differs: '+lib)
   require(sha(row['original']['log'])==row['original']['logSha256'] and same(row['original'],row['original']),'Original suite control is invalid')
   private=clone(root,c.work/'runtime'/lib);scope=prior.parent/'inputs'/(lib+'-scope.json')
   require(read(scope)['hashes']==row['sourceHashes'],'Scope certificate differs: '+lib)
   require(all(sha(private/f)==h for f,h in row['sourceHashes'].items()),'Private source copy differs')
   timeout=c.protocol.get('profileTimeoutByLibrary',{}).get(lib,c.protocol['profileTimeoutSeconds'])
   plain=c.run('runtime-plain-'+lib,[c.machine['graalNode']]+cfg['command'][1:],private,timeout=timeout)
   q={'root':private,'command':cfg['command'],'original':row['original'],'scope':scope}
   dg=dynamic(c,lib,q,'runtime-profile-'+lib) if same(row['original'],plain) else None
   current={'sourceRoot':str(root),'executionRoot':str(private),'sourceHashes':row['sourceHashes'],'fullSuite':True,'original':row['original'],'plainGraal':plain,'profiled':dg['stage'] if dg else None,'dynamic':dg,'mappingValid':bool(dg and dg['valid']),'traceBalanced':bool(dg and dg.get('metadata') and not dg['metadata'].get('stackMismatches') and not dg['metadata'].get('remainingUserFrames')),'productionUnchanged':all(sha(root/f)==h and sha(private/f)==h for f,h in row['sourceHashes'].items())}
   current['qualified']=bool(current['productionUnchanged'] and current['mappingValid'] and current['traceBalanced'] and same(row['original'],plain) and same(row['original'],current['profiled']))
   proof['libraries'][lib]=current;write(c.out/'runtime-admission.json',proof)
   require(current['qualified'],'Runtime qualification failed: '+lib)
  proof['status']='qualified';write(c.out/'runtime-admission.json',proof);c.record.update(status='qualified',scientificExperiment=False);c.save()
 except Exception:
  proof.update(status='not-qualified',error=traceback.format_exc());write(c.out/'runtime-admission.json',proof)
  c.record.update(status='failed',scientificExperiment=False,error=proof['error']);c.save();raise
 print(c.out/'runtime-admission.json',flush=True)
if __name__=='__main__':main()
