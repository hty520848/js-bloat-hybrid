#!/usr/bin/env python3
"""Supplement-only qualification; never dispatch RQ1–RQ4 main result sampling."""
import argparse,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,write
from experiments.admission import units
from experiments.clients import qualify
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--library');p.add_argument('--client');p.add_argument('--reuse-baseline');p.add_argument('--unit-evidence-run');a=p.parse_args()
c=Context(a.run_id);c.record['executionPolicy']='supplement-only: no historical primary RQ result resampling'
if a.library:
 c.manifest=[x for x in c.manifest if x['library']==a.library]
 c.machine['clients']={a.library:[x for x in c.machine.get('clients',{}).get(a.library,[]) if not a.client or x['directory']==a.client]}
if a.reuse_baseline:
 assert a.library and a.client,'Baseline reuse requires one explicit library/client'
 assert len(c.machine['clients'][a.library])==1
 c.machine['clients'][a.library][0]['baselineEvidence']=a.reuse_baseline
if a.unit_evidence_run:
 for cfg in c.machine['targets'].values():cfg['unitEvidenceRun']=a.unit_evidence_run
try:
 units(c);rows=qualify(c);c.record['stages'].append({'name':'fresh-client-bindings-and-truth','status':'passed' if rows and all(x['qualified'] for x in rows) else 'blocked','qualified':sum(x['qualified'] for x in rows),'total':len(rows)})
 c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
