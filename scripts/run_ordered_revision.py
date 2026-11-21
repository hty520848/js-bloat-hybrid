#!/usr/bin/env python3
"""Run missing revision measurements in RQ1 -> RQ2 -> RQ3 -> RQ4 order."""
import argparse,json,sys,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import ROOT,read,write,sha
from experiments import ordered_revision as phases
from run_rq1_only import admit

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime-admission',required=True);p.add_argument('--batch',required=True);p.add_argument('--start',choices=['rq1','rq2','rq3','rq4'],default='rq1');a=p.parse_args()
 if not __import__('re').fullmatch(r'[A-Za-z0-9_.-]+',a.batch):p.error('Unsafe batch')
 proof=admit(a.runtime_admission,read(ROOT/'experiments/rq1/ablation-plan-20261102.json'))
 out=ROOT/'provenance'/('ordered-'+a.batch);out.mkdir(exist_ok=False)
 record={'status':'running','startedUnix':time.time(),'runtimeAdmission':a.runtime_admission,'runtimeAdmissionSha256':sha(a.runtime_admission),'order':['rq1','rq2','rq3','rq4'],'completed':[],'manuscriptWrites':False,'retention':'Every new run ID is unique; failures and prior observations are preserved.'}
 write(out/'controller.json',record)
 try:
  for name in record['order'][record['order'].index(a.start):]:
   run_id='ordered-'+name+'-'+a.batch;record.update(phase=name,runId=run_id);write(out/'controller.json',record)
   result=getattr(phases,name)(run_id,proof);record['completed'].append({'phase':name,'output':result});write(out/'controller.json',record)
  record.update(status='completed',finishedUnix=time.time());write(out/'controller.json',record)
 except Exception:record.update(status='failed',error=traceback.format_exc(),finishedUnix=time.time());write(out/'controller.json',record);raise
if __name__=='__main__':main()
