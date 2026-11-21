#!/usr/bin/env python3
"""The only ordered experiment entry point. No historical scripts are imported."""
import argparse,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,write
from experiments import prepare
from experiments.rq1 import run as rq1
from experiments.rq2 import run as rq2
from experiments.rq3 import run as rq3
from experiments.rq4 import run as rq4
def main():
 p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--mode',choices=['prepare','qualification','formal'],default='qualification');p.add_argument('--skip-client-qualification',action='store_true',help='Sample only the core-pilot chain; keep frozen fifty-client evidence and its failures in their original runs');a=p.parse_args()
 c=Context(a.run_id)
 if a.skip_client_qualification:
  c.machine['clients']={};c.record['clientQualification']='skipped: frozen client evidence (including the four failed original controls) is retained in its original runs and is not resampled here'
 try:
  prepare.run(c)
  if a.mode=='prepare':c.finish();print(str(c.out/'status.json'));return
  c.record['reviewerRequirementsPending']=['Version-matched test harnesses and dependency closure for every target','Fifty freshly qualified held-out clients and branch/saturation sensitivity','Matched SSCG, SDCG, DepPrune and Mininode adapters','License audit and public immutable release']
  c.record['reviewerRequirementsResolvedInCode']={'static ablation 2x2':'four arms per library plus the multi-module scope supplement (scripts/ablate_static_module_scope.py)','edge adjudication':'scripts/adjudicate_edges.py closes the interval and reports Cohen kappa','MECS definition':'experiments/metrics.py; per-workload cells, zero is a measurement','client-level SSCG/SDCG':'scripts/qualify_stubbifier_rq2.py --clients','baseline cost incl. SSCG/SDCG':'scripts/qualify_baseline_costs.py --methods sscg sdcg','published-number reconciliation':'scripts/reconcile_stubbifier.py with datasets/manifests/stubbifier-published.json','formal-mode deadlock':'client quorum with explicit formalGaps in preparation.json'}
  for name,driver in [('rq1',rq1),('rq2',rq2),('rq3',rq3),('rq4',rq4)]:
   if a.mode=='formal' and not c.record['preparation']['formalReady']:
    c.record['stages'].append({'name':name,'status':'blocked','reason':'Full frozen ten-library/fifty-client qualification is incomplete; see preparation.json'});c.save();continue
   driver.run(c,qualification=a.mode=='qualification')
  c.finish()
 except Exception:
  c.record.update(status='failed',error=traceback.format_exc());c.save();raise
 print(str(c.out/'status.json'))
if __name__=='__main__':main()
