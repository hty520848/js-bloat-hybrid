import random,statistics,shutil
from pathlib import Path
from ..common import write,same,output_snapshot,completion_gate
from ..clients import comparison_eligible
def run(c,qualification=True):
 rows=[];gaps=[];warmups=c.protocol['rq3']['warmups'];reps=c.protocol['rq3']['measuredRuns'];seed=c.protocol['rq3']['seed']
 for b in c.builds:
  if not b['valid']:continue
  lib,arm=b['library'],b['arm'];q=c.qualified[lib]
  workloads=[None] if qualification else c.clients[lib]
  for j,client in enumerate(workloads):
   if not comparison_eligible(client):
    gaps.append({'library':lib,'arm':arm,'client':client['name'],'status':'not-run-target-unexercised','eligible':False});continue
   sources={'original':q.get('deployment',q['root']),'transformed':b['target']};cmd=client['cfg']['command'] if client else q['command'];baseline=client['baseline'] if client else q['original']
   for i in range(warmups+reps):
    # Each pair starts from frozen client inputs/cold transformed deployment.
    # Copying and evidence hashing are outside the measured subprocess time.
    roots={}
    for mode,source in sources.items():
     tag='rq3-{}-{}-{}-{}-{}'.format(lib,arm,j,i,mode)
     if client:
      from ..clients import bind
      roots[mode]=bind(c,client['cfg'],source,tag)
     else:
      from ..baselines import harness
      roots[mode]=harness(c,lib,q,source,tag)
    # Apply the same verification apparatus to both members of the pair.
    c.harnesses[str(roots['original'])]['recoveryHelpers']=c.harnesses[str(roots['transformed'])].get('recoveryHelpers',[])
    order=['original','transformed'] if (i+j)%2==0 else ['transformed','original'];obs={}
    for mode in order:obs[mode]=c.run('rq3-{}-{}-{}-{}-{}'.format(lib,arm,j,i,mode),cmd,roots[mode])
    valid=all(same(baseline,v) for v in obs.values())
    rows.append({'library':lib,'arm':arm,'client':client['name'] if client else 'core-pilot','round':i,'warmup':i<warmups,'order':order,'original':obs['original'],'transformed':obs['transformed'],'freshInputsPerPair':True,'valid':valid,'signedSlowdownPercent':100.0*(obs['transformed']['seconds']-obs['original']['seconds'])/obs['original']['seconds'] if valid else None})
    write(c.out/'rq3/runtime.json',{'status':'running','scope':'full core workload timing qualification' if qualification else 'clients','rows':rows})
    # Thousands of full dependency clones can exceed a host's disk. Preserve
    # every failed pair; successful scratch trees may be recreated from the
    # archived inputs, implementation and generated-byte hashes below.
    if valid and not c.protocol.get('keepSuccessfulRuntimeWorkspaces',False):
     for mode,root in roots.items():
      root=Path(root);assert c.work.resolve() in root.resolve().parents and not root.is_symlink()
      evidence=c.out/'rq3/workspace-sha256'/('{}-{}-{}-{}-{}.json'.format(lib,arm,j,i,mode));write(evidence,output_snapshot(root));shutil.rmtree(str(root))
     rows[-1]['successfulScratchRemovedAfterHashing']=True
 summary=[]
 for lib,arm,client in sorted({(r['library'],r['arm'],r['client']) for r in rows}):
  cell=[r for r in rows if (r['library'],r['arm'],r['client'])==(lib,arm,client) and not r['warmup']];vals=[r['signedSlowdownPercent'] for r in cell if r['valid']]
  rng=random.Random(seed);boots=sorted(statistics.mean([rng.choice(vals) for _ in vals]) for _ in range(c.protocol['rq3']['bootstrapSamples'])) if vals else []
  planned=reps
  summary.append({'library':lib,'arm':arm,'client':client,'planned':planned,'validPairs':len(vals),'completeCell':len(vals)==planned,'mean':statistics.mean(vals) if vals else None,'median':statistics.median(vals) if vals else None,'sampleSD':statistics.stdev(vals) if len(vals)>1 else None,'descriptivePairedRoundBootstrap95':[boots[int(.025*len(boots))],boots[int(.975*len(boots))]] if boots else None,'unit':'percentage points','independence':'Rounds are technical repeats; no population inference across libraries or unseen clients.'})
 write(c.out/'rq3/runtime.json',{'status':'completed','scope':'core qualification' if qualification else 'clients','rows':rows,'summary':summary,'seed':seed,'coverageGaps':gaps})
 done={};bad=set()
 for x in summary:
  key=(x['library'],x['arm']);done[key]=done.get(key,True) and x['completeCell']
  if not x['completeCell']:bad.add(key)
 gate=completion_gate(c.protocol,c.qualified,[k for k,v in done.items() if v],[k for k in bad if not done.get(k)])
 c.record['stages'].append(dict(gate,name='rq3',formalResult=not qualification,coverageGaps=len(gaps)));c.save()
