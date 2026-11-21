"""Private client binding and fresh truth. Never mutate a source checkout."""
import shutil
from pathlib import Path
from .common import ROOT,clone,read,write,snapshot,same,completed,signature,sha
from .prepare import sha_bytes
def comparison_eligible(client):
 return client is None or client.get('methodComparisonEligible',True)
def client_coverage(c,lib):
 """Frozen/measured/eligible/deficit counts for one library.

 A failed original control is not interchangeable with a valid zero-hit
 observation, so the three populations are counted separately:
 'frozen' is the size of the client roster fixed in the configuration, which
 does not change when a client fails to run; 'measured' is how many of those
 produced a usable measurement; 'eligible' is how many may enter a method
 comparison. Counting the roster rather than the survivors keeps a failure
 visible as controlFailed instead of silently shrinking the cohort.
 """
 clients=c.clients.get(lib,[])
 roster=[x['directory'] for x in getattr(c,'machine',{}).get('clients',{}).get(lib,[])]
 measured=[x['name'] for x in clients]
 if not roster:roster=measured
 eligible=[x for x in clients if comparison_eligible(x)]
 return {'library':lib,'frozen':len(roster),'roster':roster,'measured':len(measured),'eligible':len(eligible),'targetUnexercised':len(measured)-len(eligible),'controlFailed':sorted(set(roster)-set(measured))}
def formal_ready(c,expected):
 # Formal mode used to require five qualifying clients per library. Four
 # original controls fail on the frozen image (astroturf and ember-cli), which
 # made formal mode structurally unreachable no matter how much data was
 # produced. The comparison now requires a stated quorum of eligible clients
 # and reports the per-library deficit, rather than demanding that a control
 # which fails on this image must pass before any client-level table exists.
 quorum=int(c.protocol.get('formalClientQuorum',3));per=int(c.protocol['clientsPerLibrary'])
 c.formalCoverage={lib:client_coverage(c,lib) for lib in expected}
 c.formalGaps=[dict(v,deficit=max(0,per-v['measured']),rosterDeficit=max(0,per-v['frozen']),quorum=quorum) for v in c.formalCoverage.values() if v['eligible']<quorum or v['measured']<per]
 return len(c.qualified)==c.protocol['formalLibraries'] and bool(expected) and all(c.formalCoverage[lib]['eligible']>=quorum for lib in expected)
def reuse(c,index_path):
 """Reconstruct the frozen client cohort from a consolidated index.

 Supplement drivers do not re-run client qualification; they consume the frozen
 cohort. Reconstructing it here - config from the machine file, baseline stage
 and signature from the per-client qualification run, hits from the truth run -
 means a supplement binds the same bytes the primary run bound, instead of
 quietly working with an empty client list and reporting "no material".
 """
 c.clients={};rows=[]
 for r in read(index_path)['rows']:
  lib,name=r['library'],r['client']
  cfg=next((x for x in c.machine.get('clients',{}).get(lib,[]) if x['directory']==name),None)
  row={'library':lib,'client':name,'runId':r['runId'],'qualified':bool(r.get('qualified'))}
  rows.append(row)
  if not cfg:row.update(status='no-machine-config');continue
  prior=ROOT/'runs'/r['runId']
  try:
   qual=read(prior/'client-qualification.json')
   hit=[x for x in qual if x['library']==lib and x['client']==name]
   assert hit,'client absent from its qualification run'
   baseline=hit[0]['baseline']
   assert sha(baseline['log'])==baseline['logSha256'],'cached client baseline changed'
   hits=prior/'client-truth'/lib/(name+'-hits.json')
   assert hits.is_file(),'client truth hits missing'
   assert sha(hits)==r['hitsSha256'],'client truth hits changed'
   c.clients.setdefault(lib,[]).append({'cfg':cfg,'baseline':baseline,'hits':str(hits),'name':name,'methodComparisonEligible':bool(r.get('qualified')),'truthRun':r['runId']})
   row.update(status='reused',eligible=bool(r.get('qualified')))
  except Exception as e:row.update(status='reuse-failed',reason=type(e).__name__+': '+str(e))
 c.clientReuse=rows
 return rows
def bind(c,cfg,target,tag):
 root=clone(cfg['root'],c.work/'client-workloads'/tag)
 groups={}
 for rel in cfg['targetBindings']:
  dest=root/rel;resolved=dest.resolve()
  if root not in resolved.parents or 'node_modules' not in Path(rel).parts:raise ValueError('Unsafe client target binding '+rel)
  if dest.is_symlink():raise ValueError('Client binding must be physical')
  if dest.exists():shutil.rmtree(str(dest))
  group=cfg.get('targetBindingGroups',{}).get(rel,rel)
  if group in groups:
   import os
   dest.symlink_to(os.path.relpath(str(groups[group]),str(dest.parent)))
  else:clone(target,dest);groups[group]=dest
 lib=cfg.get('library');q=c.qualified.get(lib) if hasattr(c,'qualified') else None
 config=read(root/'.hybrid-harness.json') if (root/'.hybrid-harness.json').is_file() else {'environment':{'NODE_PATH':''}}
 if cfg.get('fixedDateMs') is not None:
  config['environment']['HYBRID_FIXED_DATE_MS']=str(cfg['fixedDateMs'])
  config['environment']['NODE_OPTIONS']=config['environment'].get('NODE_OPTIONS','')+' --require {PACKAGE}/scripts/harness/fixed_clock.cjs'
  config['fixedCalendarSource']=cfg['fixedCalendarSource']
 # Metadata belongs outside the client source tree: added JSON can otherwise
 # enter the client's own formatter/linter globs and alter its test workload.
 if (root/'.hybrid-harness.json').exists():(root/'.hybrid-harness.json').unlink()
 if q and q.get('dependencyBoundary'):
  boundaries=[dict(q['dependencyBoundary'],root=str(p)) for p in groups.values()]
  if c.work in Path(target).resolve().parents:boundaries.append(dict(q['dependencyBoundary'],root=str(Path(target).resolve())))
  config['deploymentBoundaries']=boundaries
 if not hasattr(c,'harnesses'):c.harnesses={}
 config['recoveryHelpers']=getattr(c,'recovery_helpers',{}).get(str(Path(target)),[])
 c.harnesses[str(root)]=config
 if hasattr(c,'out'):write(c.out/'harnesses'/(tag+'.json'),config)
 return root
def qualify(c):
 c.clients={};rows=[]
 expected=read(ROOT/'datasets/manifests/clients.json')['libraries']
 for lib,configs in sorted(c.machine.get('clients',{}).items()):
  for i,cfg in enumerate(configs):
   name=cfg['directory'];row={'library':lib,'client':name,'qualified':False};rows.append(row)
   if lib not in c.qualified:
    row.update(reason='Library source/unit evidence did not qualify',status='blocked-unit-evidence');write(c.out/'client-qualification.json',rows);continue
   q=c.qualified[lib]
   if name not in [x['directory'] for x in expected[lib]]:raise ValueError('Client not frozen in candidate manifest')
   frozen=snapshot(cfg['root'],include_all=True)
   if sha_bytes(frozen)!=cfg['inputManifestSha256']:
    row['reason']='Client input manifest mismatch';continue
   c.inputSnapshots[str(cfg['root'])]=frozen;c.inputSnapshotAlgorithms[str(cfg['root'])]=True
   evidence=read(cfg['baselineEvidence']) if cfg.get('baselineEvidence') else None
   if evidence:
    assert evidence['library']==lib and evidence['client']==name and evidence['inputManifestSha256']==sha_bytes(frozen)
    baseline=dict(evidence['baseline']);assert sha(baseline['log'])==baseline['logSha256'] and baseline['command']==cfg['command']
    baseline.update(signature=signature(baseline['log']),reusedFrom=cfg['baselineEvidence']);original=Path(baseline['cwd'])
    assert completed(baseline),'Cached original suite is not complete'
    assert all((original/rel/f).is_file() and sha(original/rel/f)==h for rel in cfg['targetBindings'] for f,h in read(q['scope'])['hashes'].items()),'Cached original bound source changed'
   else:
    original=bind(c,cfg,q['deployment'],'prepare-'+lib+'-'+str(i)+'-original')
    baseline=c.run('prepare-client-'+lib+'-'+str(i),cfg['command'],original)
   row['baseline']=baseline
   if not completed(baseline):
    row.update(status='original-control-failed',reason='Complete original client test suite did not pass; independent truth was not run',inputManifestSha256=sha_bytes(frozen),targetBindings=cfg['targetBindings']);write(c.out/'client-qualification.json',rows);continue
   instrumented=bind(c,cfg,q['truthDeployment'],'prepare-'+lib+'-'+str(i)+'-truth')
   out=c.out/'client-truth'/lib/name
   truth=c.run('prepare-client-truth-'+lib+'-'+str(i),cfg['command'],instrumented,{'NODE_OPTIONS':'--require '+str(ROOT/'src/metrics/truth_preload.cjs'),'HYBRID_TRUTH_OUT':str(out)})
   hits=set()
   for p in out.glob('*.json'):hits.update(read(p)['hits'])
   universe={f['id'] for f in read(q['functions'])['functions']};unknown={x for x in hits-universe if not x.startswith('@file:')}
   own={f['id'] for f in read(q['functions'])['functions'] if f['scope']=='library'}
   baseline_intact=all((original/rel/f).is_file() and __import__('hashlib').sha256((original/rel/f).read_bytes()).hexdigest()==h for rel in cfg['targetBindings'] for f,h in read(q['scope'])['hashes'].items())
   truth_hashes={x['file']:x.get('instrumentedSha256',x['sha256']) for x in read(q['functions'])['files']}
   truth_intact=all((instrumented/rel/f).is_file() and __import__('hashlib').sha256((instrumented/rel/f).read_bytes()).hexdigest()==h for rel in cfg['targetBindings'] for f,h in truth_hashes.items())
   measured=same(baseline,truth) and not unknown and baseline_intact and truth_intact and frozen==snapshot(cfg['root'],include_all=True)
   valid=measured and bool(hits&own)
   row.update(qualified=valid,truthMeasurementValid=measured,targetExercised=bool(hits&own),status='qualified' if valid else ('target-not-exercised' if measured else 'truth-or-integrity-failed'),baseline=baseline,truth=truth,productionFunctionsExercised=len(hits&universe),ownFunctionsExercised=len(hits&own),boundOriginalSourceUnchanged=baseline_intact,boundInstrumentedSourceUnchanged=truth_intact,unknownFunctionIds=sorted(unknown),inputManifestSha256=sha_bytes(frozen),targetBindings=cfg['targetBindings'])
   hitfile=c.out/'client-truth'/lib/(name+'-hits.json');write(hitfile,sorted(hits))
   if measured:c.clients.setdefault(lib,[]).append({'cfg':cfg,'baseline':baseline,'hits':str(hitfile),'name':name,'methodComparisonEligible':valid})
   write(c.out/'client-qualification.json',rows)
 write(c.out/'client-qualification.json',rows)
 return rows
