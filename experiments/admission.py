"""Reuse identity-verified unit evidence; do not remeasure completed experiments."""
from pathlib import Path
from .common import ROOT,read,write,sha,snapshot,same
from .deployment import materialize
def units(c):
 c.qualified={};rows=[]
 for ref in c.manifest:
  lib=ref['library'];cfg=c.machine.get('targets',{}).get(lib,{});run=cfg.get('unitEvidenceRun','formal-readiness-20261025-004');prior=ROOT/'runs'/run
  row={'library':lib,'sourceRun':run,'reused':False};rows.append(row)
  try:
   r=next(x for x in read(prior/'preparation.json')['rows'] if x['library']==lib)
   assert r['status']=='qualified-for-core-pilot' and same(r['originalCore'],r['truthCore'])
   for stage in [r['originalCore'],r['truthCore']]:assert sha(stage['log'])==stage['logSha256']
   assert cfg['command']==r['originalCore']['command']
   assert sha(Path(cfg['root'])/'package-lock.json')==cfg['dependencyLockSha256']
   assert sha(ROOT/'artifacts/npm'/ref['archive'])==ref['sha256']
   scope=prior/'inputs'/(lib+'-scope.json');sc=read(scope)
   assert all(sha(Path(cfg['root'])/f)==h for f,h in sc['hashes'].items())
   frozen=read(prior/'executed-source-sha256.json')
   for f in ['src/metrics/truth_manifest.js','src/metrics/truth_preload.cjs','src/metrics/scope.js']:assert sha(ROOT/f)==frozen[f]
   q={'root':Path(cfg['root']),'command':cfg['command'],'original':r['originalCore'],'scope':scope,'allow':prior/'inputs'/(lib+'-published.json'),'functions':prior/'inputs'/(lib+'-functions.json'),'coreHits':str(prior/'truth'/(lib+'-core-hits.json')),'unitTruthRoot':str(ROOT/'work'/run/'truth'/lib)}
   ids={f['id'] for f in read(q['functions'])['functions'] if f['scope']=='library'};assert ids&set(read(q['coreHits']))
   c.inputSnapshots[str(q['root'])]=snapshot(q['root']);materialize(c,lib,q);c.qualified[lib]=q;row.update(reused=True,validatedSourceFiles=len(sc['files']),replayedCommands=0)
  except Exception as e:row.update(reason=type(e).__name__+': '+str(e))
  write(c.out/'unit-evidence-reuse.json',rows)
 c.record['stages'].append({'name':'unit-evidence-reuse','status':'passed' if len(c.qualified)==len(c.manifest) else 'blocked','qualifiedLibraries':sorted(c.qualified),'commandsRerun':0});c.save()
 return rows
