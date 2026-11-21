from pathlib import Path
from ..common import read,write,sha,same,completion_gate
from ..rq1.run import build
from ..clients import comparison_eligible
from .. import metrics
def eligible_completion_pairs(rows):
 """Coverage exclusions are not transformed-program failures.

 A cell with no eligible workload remains missing. A genuinely failed
 eligible workload makes its cell invalid. Raw skipped rows are preserved.
 """
 pairs={}
 for r in rows:
  if not r.get('eligible',True):continue
  key=(r['library'],r['arm']);pairs[key]=pairs.get(key,True) and bool(r.get('valid'))
 return pairs
def run(c,qualification=True):
 rows=[]
 for prior in c.builds:
  if not prior['valid']:continue
  lib,arm=prior['library'],prior['arm'];q=c.qualified[lib]
  workloads=[None] if qualification else c.clients[lib]
  for i,client in enumerate(workloads):
   workload='core-pilot' if client is None else client['name']
   if not comparison_eligible(client):
    rows.append({'library':lib,'arm':arm,'client':client['name'],'workload':workload,'eligible':False,'valid':None,'status':'not-run-target-unexercised','MECS':None,'MECSReason':'Target-unexercised workload is outside the comparison cohort; no run-time expansion observation exists'});write(c.out/'rq2/loading.json',{'rows':rows});continue
   tag='rq2-'+lib+'-'+arm+'-'+str(i)
   row=build(c,lib,q,arm,c.graphs[lib].get(arm,c.graphs[lib]['mcg-only']),c.dynamic[lib],tag,instrument=True,validate=qualification)
   if not row.get('lab'):
    rows.append(dict(row,valid=False,status='not-run-instrumented-build-failed',workload=workload));write(c.out/'rq2/loading.json',{'rows':rows});continue
   lab=Path(row['lab']);events=[]
   if client:
    from ..clients import bind
    target=bind(c,client['cfg'],row['target'],tag)
    row['client']=client['name'];row['clientStage']=c.run(tag+'-client',client['cfg']['command'],target,{'HYBRID_PAYLOAD_OUT':lab/'loads'/lib})
    row['valid']=row['valid'] and same(client['baseline'],row['clientStage'])
   roots=[Path(row['target'])]
   if row.get('coreValidationRoot'):roots.append(Path(row['coreValidationRoot']))
   if client:roots.append(target)
   for p in [lab/'loads'/lib/'file.log',lab/'loads'/lib/'excute_func_file.log']+[root/'file.log' for root in roots]:
    if p.is_file():events.append({'file':str(p),'sha256':sha(p),'lines':p.read_text(errors='replace').splitlines()})
   payload_events=[]
   for p in (lab/'loads'/lib).glob('payload-*.jsonl'):
    payload_events.extend(__import__('json').loads(l) for l in p.read_text().splitlines())
   unique={e['kind']+':'+e['path']:e for e in payload_events}
   loaded=metrics.loaded_bytes(payload_events)
   row.update(events=events,payloadEvents=payload_events,uniquePayloadBytes=loaded,uniqueFileExpansions=sum(e['kind']=='file' for e in unique.values()),uniqueFunctionExpansions=sum(e['kind']=='function' for e in unique.values()),workload=workload,eligible=True,MECS=metrics.mecs_kb(loaded),MECSDefinition=metrics.MECS_DEFINITION,MECSReason=None)
   rows.append(row);write(c.out/'rq2/loading.json',{'rows':rows})
 eligible=[x for x in rows if x.get('eligible',True)]
 cells=metrics.aggregate(rows)
 write(c.out/'rq2/loading-cells.json',{'scope':'core qualification' if qualification else 'held-out clients','cells':cells,'MECSDefinition':metrics.MECS_DEFINITION,'zeroIsMeasurement':'A zero cell means every eligible workload pulled back no recovery payload; it is not a missing value.'})
 pairs=eligible_completion_pairs(rows)
 gate=completion_gate(c.protocol,c.qualified,[k for k,v in pairs.items() if v],[k for k,v in pairs.items() if not v])
 gate['ineligibleWorkloadCells']=len(rows)-len(eligible)
 c.record['stages'].append(dict(gate,name='rq2',formalResult=not qualification,metricCells=len(cells)));c.save()
