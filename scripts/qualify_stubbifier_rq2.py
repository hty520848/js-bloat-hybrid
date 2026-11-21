#!/usr/bin/env python3
"""Reviewer 1.13 / 2.3.2: SSCG/SDCG loading matrix, now with the client dimension.

Table 4 in the manuscript is a (library x client) matrix. The first version of
this supplement looped over libraries only, so it could not produce that table
and could not support "cases where SSCG and SDCG differ markedly" either - a
difference that only appears for one workload of a library is invisible in a
library mean.

Each (library, method, workload) cell now gets its own MECS and its own set of
recovered paths, using the definition in ``experiments/metrics.py``. Workload
payloads are written to separate directories so a client run is never added to
the core run's expansion count.
"""
import argparse,sys,traceback,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,ROOT,read,write,sha,same
from experiments.admission import units
from experiments.stubbifier_baselines import sscg,sdcg,build
from experiments import metrics
from experiments.clients import comparison_eligible
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--methods',nargs='+',choices=['sscg','sdcg'],default=['sscg','sdcg']);p.add_argument('--library');p.add_argument('--codeql-root');p.add_argument('--coverage-node-modules')
p.add_argument('--clients',type=int,default=0,help='0 keeps the library-level matrix; N adds the first N eligible clients per library')
p.add_argument('--clients-from',default=str(ROOT/'artifacts/revision-20261025b/consolidated-client-index-001.json'))
p.add_argument('--client');a=p.parse_args()
c=Context(a.run_id);c.record['executionPolicy']='Supplement: SSCG/SDCG loading-event matrix; per-workload MECS; no primary table resampling'
if a.library:c.manifest=[x for x in c.manifest if x['library']==a.library]
def ensure_cfg():
 if c.machine.get('stubbifierBaselines'):return c.machine['stubbifierBaselines']
 cfg={}
 if 'sscg' in a.methods:
  assert a.codeql_root,'--codeql-root is required when SSCG is requested and stubbifierBaselines is unconfigured'
  root=Path(a.codeql_root).resolve()
  assert (root/'codeql/codeql').is_file() and (root/'codeql-1.26.0').is_dir(),'codeql root must contain codeql/ and codeql-1.26.0/'
  cfg.update({'codeql':str(root/'codeql/codeql'),'searchPath':str(root/'codeql-1.26.0'),'querySha256':sha(ROOT/'src/baselines/stubbifier-recovery.ql')})
 cfg['coverageNodeModules']=a.coverage_node_modules or str(Path(c.machine['targets']['css-loader']['root'])/'node_modules')
 c.machine['stubbifierBaselines']=cfg;write(c.out/'stubbifier-baselines/config.json',cfg);return cfg
def collect(payload_dir,roots):
 events=[];payload=[]
 for pth in [payload_dir/'file.log',payload_dir/'excute_func_file.log']+[r/'file.log' for r in roots]:
  if pth.is_file():events.append({'file':str(pth),'sha256':sha(pth),'lines':pth.read_text(errors='replace').splitlines()})
 if payload_dir.is_dir():
  for pth in sorted(payload_dir.glob('payload-*.jsonl')):payload.extend(json.loads(line) for line in pth.read_text().splitlines())
 unique={str(e.get('kind'))+':'+str(e.get('path')):e for e in payload}
 loaded=metrics.loaded_bytes(payload)
 return {'events':events,'payloadEvents':payload,'uniquePayloadBytes':loaded,
         'uniqueFileExpansions':sum(1 for e in unique.values() if e.get('kind')=='file'),
         'uniqueFunctionExpansions':sum(1 for e in unique.values() if e.get('kind')=='function'),
         'uniqueRecoveredPaths':sorted(unique),'MECS':metrics.mecs_kb(loaded)}
try:
 ensure_cfg();units(c);rows=[]
 if a.clients and not getattr(c,'clients',None):
  from experiments.clients import reuse
  reuse(c,a.clients_from)
  write(c.out/'client-reuse.json',{'source':a.clients_from,'rows':c.clientReuse})
 for lib,q in sorted(c.qualified.items()):
  workloads=[None] if not a.clients else [x for x in c.clients.get(lib,[]) if comparison_eligible(x) and (not a.client or x['name']==a.client)][:a.clients]
  if a.clients and not workloads:
   rows.append({'library':lib,'workload':'none','status':'no-eligible-client','valid':False,'eligible':False,'MECS':None});write(c.out/'stubbifier-baselines/rq2-loading.json',{'status':'running','rows':rows});continue
  for method in a.methods:
   try:
    analysis=(sscg if method=='sscg' else sdcg)(c,lib,q)
    base=build(c,lib,q,method,analysis,'rq2-'+method+'-'+lib,instrument=True)
    if not base.get('loads'):
     rows.append(dict(base,workload='core-pilot',eligible=True,valid=False,status='instrumented-build-failed',MECS=None,MECSReason='No instrumented build to observe'));write(c.out/'stubbifier-baselines/rq2-loading.json',{'status':'running','rows':rows});continue
    lab=Path(base['lab']);loads=Path(base['loads'])
    for i,client in enumerate(workloads):
     workload='core-pilot' if client is None else client['name']
     payload_dir=loads if client is None else loads/'workloads'/(client['name'])
     roots=[Path(base['target'])]
     if base.get('coreValidationRoot'):roots.append(Path(base['coreValidationRoot']))
     row={'library':lib,'method':method,'workload':workload,'valid':bool(base.get('valid')),'eligible':True}
     if client is not None:
      from experiments.clients import bind
      target=bind(c,client['cfg'],base['target'],'rq2-'+method+'-'+lib+'-'+str(i))
      row['clientStage']=c.run('rq2-'+method+'-'+lib+'-'+str(i)+'-client',client['cfg']['command'],target,{'HYBRID_PAYLOAD_OUT':payload_dir})
      row['valid']=bool(base.get('valid')) and same(client['baseline'],row['clientStage'])
      roots.append(target)
     else:payload_dir.mkdir(parents=True,exist_ok=True)
     row.update(collect(payload_dir,roots))
     row['MECSDefinition']=metrics.MECS_DEFINITION
     rows.append(row);write(c.out/'stubbifier-baselines/rq2-loading.json',{'status':'running','scope':'library x workload','rows':rows})
   except Exception:rows.append({'library':lib,'method':method,'workload':'adapter','valid':False,'status':'adapter-exception','error':traceback.format_exc()});write(c.out/'stubbifier-baselines/rq2-loading.json',{'status':'running','rows':rows})
 cells=metrics.aggregate(rows,group_keys=('library','method'))
 write(c.out/'stubbifier-baselines/rq2-loading-cells.json',{'cells':cells,'MECSDefinition':metrics.MECS_DEFINITION,'zeroIsMeasurement':'A zero cell means no eligible workload expanded any recovery payload.'})
 diff=[];by={}
 for r in rows:
  if r.get('valid'):by.setdefault((r['library'],r.get('workload')),{})[r['method']]=r
 for (lib,workload),m in sorted(by.items(),key=lambda kv:str(kv[0])):
  if 'sscg' in m and 'sdcg' in m:
   sp=set(m['sscg'].get('uniqueRecoveredPaths') or []);dp=set(m['sdcg'].get('uniqueRecoveredPaths') or [])
   only_s=sorted(sp-dp);only_d=sorted(dp-sp)
   diff.append({'library':lib,'workload':workload,'sscgMECS':m['sscg']['MECS'],'sdcgMECS':m['sdcg']['MECS'],'mecsRatio':round(m['sscg']['MECS']/m['sdcg']['MECS'],4) if m['sdcg']['MECS'] else None,
                'sameRecoveredSet':sp==dp,'onlySSCG':only_s[:20],'onlySDCG':only_d[:20],'onlySSCGCount':len(only_s),'onlySDCGCount':len(only_d)})
 diff.sort(key=lambda d:-(d['onlySSCGCount']+d['onlySDCGCount']))
 write(c.out/'stubbifier-baselines/rq2-loading-differences.json',{'rows':diff,'ranked':'descending by symmetric difference of recovered paths; the head of this list is the candidate set for reviewer 2.3.2','note':'A marked difference is a difference in recovered path sets, not an accuracy difference.'})
 ok=sum(1 for r in rows if r.get('valid'))
 c.record['stages'].append({'name':'sscg-sdcg-rq2-loading','status':'passed' if rows and ok==len(rows) else 'completed-with-failures','rows':len(rows),'validRows':ok,'workloadsPerLibrary':a.clients or 1,'differingCells':sum(1 for d in diff if not d['sameRecoveredSet'])});c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
