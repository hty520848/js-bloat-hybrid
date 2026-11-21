#!/usr/bin/env python3
"""Explicit fresh SSCG/SDCG qualification; never substitute saved old graphs."""
import argparse,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,write
from experiments.admission import units
from experiments.stubbifier_baselines import sscg,sdcg,build
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--library');p.add_argument('--methods',nargs='+',choices=['sscg','sdcg'],default=['sscg','sdcg']);a=p.parse_args()
c=Context(a.run_id);c.record['executionPolicy']='Explicit adapter qualification; no automatic historical primary table resampling'
if a.library:c.manifest=[x for x in c.manifest if x['library']==a.library]
try:
 units(c);rows=[]
 for lib,q in sorted(c.qualified.items()):
  for method in a.methods:
   try:
    analysis=(sscg if method=='sscg' else sdcg)(c,lib,q);row=build(c,lib,q,method,analysis,'stubbifier-'+method+'-'+lib)
   except Exception:row={'library':lib,'method':method,'valid':False,'status':'adapter-exception','error':traceback.format_exc()}
   rows.append(row);write(c.out/'stubbifier-baselines/results.json',rows)
 c.record['stages'].append({'name':'sscg-sdcg-adapters','status':'passed' if rows and all(r['valid'] for r in rows) else 'blocked','rows':len(rows)});c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
