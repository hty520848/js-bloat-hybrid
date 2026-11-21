#!/usr/bin/env python3
"""Index saved controls and truth without replaying any workload.

Later indexes override earlier candidates explicitly. Failed attempts remain
referenced. The input caches, original logs and truth producer are authenticated.
"""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import ROOT,read,write,sha,snapshot,same
from experiments.prepare import sha_bytes

def main():
 p=argparse.ArgumentParser();p.add_argument('--index',action='append',required=True);p.add_argument('--override-run',action='append',default=[]);p.add_argument('--output',required=True);a=p.parse_args()
 output=Path(a.output);assert not output.exists(),'Existing index is preserved'
 machine=read(ROOT/'config/machine.local.json');expected=read(ROOT/'datasets/manifests/clients.json')['libraries'];selected={};attempts={};sources=[]
 def add(ref):
  key=(ref['library'],ref['client']);directory=Path(ref.get('runDirectory',str(ROOT/'runs'/ref['runId'])));ref=dict(ref,runDirectory=str(directory));selected[key]=ref;attempts.setdefault(key,[]).append(ref)
 for path in a.index:
  data=read(path);assert data['status']=='completed','Incomplete controller index';sources.append({'file':path,'sha256':sha(path)})
  for ref in data['rows']:add(ref)
 for path in a.override_run:
  directory=Path(path);status=read(directory/'status.json')
  for row in read(directory/'client-qualification.json'):add({'library':row['library'],'client':row['client'],'runId':directory.name,'runDirectory':str(directory),'status':status['status']})
 assert set(selected)=={(lib,x['directory']) for lib,v in expected.items() for x in v},'Candidate matrix differs'
 rows=[]
 for key,ref in sorted(selected.items()):
  lib,name=key;directory=Path(ref['runDirectory']);cfg=next(x for x in machine['clients'][lib] if x['directory']==name);status=read(directory/'status.json');record=next(x for x in read(directory/'client-qualification.json') if (x['library'],x['client'])==key)
  assert status['status'] in ['completed','completed-with-gates'] and not status.get('changedInputTrees') and not status.get('changedImplementation'),'Invalid observation context'
  current=sha_bytes(snapshot(cfg['root'],include_all=True));assert current==cfg['inputManifestSha256']==record['inputManifestSha256'],'Client input changed'
  for stage in [record.get('baseline'),record.get('truth')]:
   if stage:assert sha(stage['log'])==stage['logSha256'],'Observation log changed'
  frozen=read(directory/'executed-source-sha256.json')
  for helper in ['src/metrics/truth_manifest.js','src/metrics/truth_preload.cjs','src/metrics/scope.js']:assert sha(ROOT/helper)==frozen[helper],'Truth producer changed'
  reuse=next(x for x in read(directory/'unit-evidence-reuse.json') if x['library']==lib);unit=machine['targets'][lib].get('unitEvidenceRun','formal-readiness-20261025-004');assert reuse['reused'] and reuse['sourceRun']==unit
  valid=same(record.get('baseline'),record.get('truth')) and record.get('boundOriginalSourceUnchanged') and record.get('boundInstrumentedSourceUnchanged') and not record.get('unknownFunctionIds')
  hits=directory/'client-truth'/lib/(name+'-hits.json');universe={x['id'] for x in read(ROOT/'runs'/unit/'inputs'/(lib+'-functions.json'))['functions']};own=record.get('ownFunctionsExercised',0) or 0
  if valid:assert not {x for x in set(read(hits))-universe if not x.startswith('@file:')},'Unknown truth identity'
  rows.append(dict(ref,status=status['status'],clientStatus='qualified' if valid and own else ('target-not-exercised' if valid else record['status']),qualified=bool(valid and own),truthMeasurementValid=bool(valid),ownFunctionsExercised=own if valid else None,inputManifestSha256=current,qualificationSha256=sha(directory/'client-qualification.json'),hitsSha256=sha(hits) if valid else None,unitEvidenceRun=unit,attempts=attempts[key]))
 result={'status':'completed','meaning':'All candidates indexed; this is not an all-passed certificate','sources':sources,'rows':rows,'candidates':len(rows),'qualified':sum(x['qualified'] for x in rows),'validTruth':sum(x['truthMeasurementValid'] for x in rows),'validZeroHit':sum(x['truthMeasurementValid'] and not x['qualified'] for x in rows),'invalidControlsOrTruth':sum(not x['truthMeasurementValid'] for x in rows),'workloadExecutionsRerun':0}
 write(output,result);print({k:v for k,v in result.items() if k not in ['sources','rows']})
if __name__=='__main__':main()
