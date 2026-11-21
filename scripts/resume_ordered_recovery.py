#!/usr/bin/env python3
"""Preserve completed RQ1; repair matched client deadline; resume RQ2 -> RQ3 -> RQ4."""
import argparse,sys,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import ROOT,read,write,sha
from experiments import ordered_revision as phases,recovery_repair
from run_rq1_only import admit

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',required=True);p.add_argument('--runtime-admission',required=True);p.add_argument('--completed-rq1',required=True);p.add_argument('--source-rq2',required=True);a=p.parse_args()
 if not __import__('re').fullmatch(r'[A-Za-z0-9_.-]+',a.batch):p.error('Unsafe batch')
 proof=admit(a.runtime_admission,read(ROOT/'experiments/rq1/ablation-plan-20261102.json'));reused_rq1=recovery_repair.verify_preserved_rq1(a.completed_rq1,proof)
 out=ROOT/'provenance'/('ordered-'+a.batch);out.mkdir(exist_ok=False)
 record={'status':'running','startedUnix':time.time(),'phase':'rq2','completed':[dict(reused_rq1,phase='rq1')],'order':['rq2','rq3','rq4'],'manuscriptWrites':False,'sourceRQ2':a.source_rq2,'runtimeAdmission':a.runtime_admission,'runtimeAdmissionSha256':sha(a.runtime_admission),'policy':'No RQ1 replay. Preserve the original 5-second failure, qualify the same revised deadline on original/truth/all methods, reuse only exact certified completed RQ2 blocks.'};write(out/'controller.json',record)
 try:
  run_id='ordered-rq2-'+a.batch;record['runId']=run_id;write(out/'controller.json',record)
  result,certificate=recovery_repair.run(run_id,proof,a.source_rq2);record['completed'].append({'phase':'rq2','output':result});record['clientProtocol']=certificate;write(out/'controller.json',record)
  record.update(phase='rq3',runId='ordered-rq3-'+a.batch);write(out/'controller.json',record)
  result=phases.rq3(record['runId'],proof,client_protocol=certificate);record['completed'].append({'phase':'rq3','output':result});write(out/'controller.json',record)
  record.update(phase='rq4',runId='ordered-rq4-'+a.batch);write(out/'controller.json',record)
  result=phases.rq4(record['runId'],proof);record['completed'].append({'phase':'rq4','output':result});record.update(status='completed',finishedUnix=time.time());write(out/'controller.json',record)
 except Exception:record.update(status='failed',error=traceback.format_exc(),finishedUnix=time.time());write(out/'controller.json',record);raise
if __name__=='__main__':main()
